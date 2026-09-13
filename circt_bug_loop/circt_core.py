"""The three generic CIRCT functions proposed for `chia/chipyard/circt.py`.

`03-LLD.md` §3.10 is normative: `circt_exec_probe`, `circt_reduce_run` and
`circt_symbolize` know nothing about seeds, arms, budgets or gates, which is
why FR-19.2 puts them in CHIA's own `chia/chipyard/circt.py` rather than in the
example directory. `upstream/chia-chipyard-circt-additions.py` is the block that
is appended to that file, and `tests/test_circt_core.py` asserts that the two
texts are identical below their headers, so the copy cannot drift from the one
that runs.

Until CHIA carries them, `probe_task.py` imports them from here.

Three deviations from §3.10's signatures, each recorded as an erratum candidate
and each forced by a measurement rather than by taste:

* `circt_symbolize` takes the `tool_path` and the `circt_roots` its
  `in_circt_object` predicate is about. §3.6.2 spells the predicate against the
  literal `/workspace/circt/`, which is true only inside the image: every
  recorded crash fixture and every host measurement carries a different prefix,
  and a hard-coded one would make the field false for all of them. `circt_roots`
  is a tuple because a host build splits CIRCT's source tree from its generated
  `.inc` files, which the image's single root does not.
* `circt_symbolize` and `circt_reduce_run` take the binary they run. §3.10 names
  `llvm-symbolizer` on `PATH` and `/workspace/circt/build/bin/circt-reduce`;
  both remain the defaults.
* `circt_reduce_run` passes `--keep-best`. §3.10's docstring omits it and §4.7
  requires it explicitly, so that the recorded argv states the behaviour the run
  depended on rather than relying on a default that could change.
"""
from __future__ import annotations

import fnmatch
import json
import os
import select
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

#: The gap between `prlimit --cpu`'s soft and hard values (`03-LLD.md` §9.4).
#: With soft equal to hard the kernel escalates past SIGXCPU straight to
#: SIGKILL and the limit is not identifiable; measured 2026-09-14,
#: `prlimit --cpu=1 -- python3 -c 'while True: pass'` returns 137 and
#: `--cpu=1:6` returns 152, which is 128 + 24, SIGXCPU.
CPU_HARD_MARGIN_SECONDS = 5

#: The three allocation-failure literals FR-06.7 names and `03-LLD.md` §3.6
#: fixes verbatim, matched case-sensitively as substrings of any stderr line.
#: The third is a prefix-extension of the second and is listed because it is a
#: real literal in the SDK's libLLVMSupport.so and can arrive without the bare
#: phrase ever appearing on its own line.
ALLOCATION_FAILURE_LITERALS = ("std::bad_alloc", "out of memory",
                               "LLVM ERROR: out of memory")

#: `RLIMIT_AS` does not kill, it makes allocation fail, and CPython reports that
#: as this word (measured: `prlimit --as=104857600 -- python3 -c
#: 'b=bytearray(500*1024*1024)'` exits 1 with it on stderr and no signal).
_MEMORY_ERROR_LINE = "MemoryError"

#: Where the image puts the source-built binaries (`03-LLD.md` §5.1).
CIRCT_BIN_DIR = "/workspace/circt/build/bin"

#: The `in_circt_object` default, which is the image's one CIRCT root.
CIRCT_ROOTS = ("/workspace/circt/",)

#: How long the drain is allowed to continue after the wall-clock killer fires,
#: so that a killed child's last diagnostics are not lost.
_POST_KILL_DRAIN_SECONDS = 2.0

#: The select() slice, which bounds how late the wall-clock killer can fire.
_POLL_SECONDS = 0.2


@ChiaFunction(resources={"circt": 1})
def circt_exec_probe(tool: str, argv: list, *, cwd: str,
                     wall_seconds: int, address_space_bytes: int,
                     cpu_seconds: int, nofile: int = 1024,
                     output_byte_cap: int = 1_000_000) -> dict:
    """Run one CIRCT binary on one input, bounded, with no shell anywhere.

    Builds ["prlimit", "--as=...", "--cpu=<soft>:<hard>", "--nofile=...", "--",
    tool, *argv], starts it in its own process group, and SIGKILLs the group on
    the wall-clock expiry. prlimit sets the limits in its own process and then
    execs the tool, so they are in force from the tool's first instruction. The
    child is reaped with os.wait4, so its rusage comes back with its status.

    `--cpu` carries a soft:hard pair, the hard value being the soft one plus
    CPU_HARD_MARGIN_SECONDS: with the two equal the kernel escalates past
    SIGXCPU straight to SIGKILL and `limit_hit` is underivable. `--rss` is never
    passed; RLIMIT_RSS has had no effect on Linux since kernel 2.4.30.

    The child is started with os.fork plus os.setsid plus os.execvp rather than
    with subprocess.Popen, for one reason: subprocess does not surface
    getrusage, and without it a CPU kill cannot be told from a wall-clock kill.

    Returns:
        {"exit_status": int | None, "signal": str | None, "limit_hit": str | None,
         "cpu_seconds": float, "peak_rss_bytes": int, "wall_seconds": float,
         "stdout": str, "stderr": str, "truncated": bool, "argv": list[str],
         "worker_hostname": str, "worker_node_id": str, "child_pid": int}
    Worker:
        {"circt": 1}.
    Raises:
        FileNotFoundError if tool does not exist; every other failure is a field.
    """
    if not os.path.isfile(tool):
        raise FileNotFoundError(tool)
    if not os.path.isdir(cwd):
        raise FileNotFoundError(cwd)
    full = ["prlimit",
            f"--as={address_space_bytes}",
            f"--cpu={cpu_seconds}:{cpu_seconds + CPU_HARD_MARGIN_SECONDS}",
            f"--nofile={nofile}",
            "--",
            tool, *argv]

    out_r, out_w = os.pipe()
    err_r, err_w = os.pipe()
    started = time.monotonic()
    pid = os.fork()
    if pid == 0:                                    # the child; never returns
        try:
            os.setsid()
            os.dup2(out_w, 1)
            os.dup2(err_w, 2)
            for fd in (out_r, out_w, err_r, err_w):
                os.close(fd)
            os.chdir(cwd)
            os.execvp(full[0], full)
        except BaseException:                       # pragma: no cover - exec failed
            os._exit(127)
    os.close(out_w)
    os.close(err_w)

    deadline = started + wall_seconds
    try:
        streams, over_cap, killed = _drain({1: out_r, 2: err_r}, deadline,
                                           output_byte_cap, pid)
        status, rusage, killed = _reap(pid, deadline, killed)
    finally:
        _killpg(pid)
    wall = time.monotonic() - started

    returncode = -os.WTERMSIG(status) if os.WIFSIGNALED(status) else os.WEXITSTATUS(status)
    sig = _signal_name(-returncode) if returncode < 0 else None
    exit_status = returncode if returncode >= 0 else None
    stderr_text = streams[2]
    cpu_used = rusage.ru_utime + rusage.ru_stime
    return {"exit_status": exit_status,
            "signal": sig,
            "limit_hit": _limit_hit(killed, sig, cpu_used, cpu_seconds, stderr_text),
            "cpu_seconds": cpu_used,
            "peak_rss_bytes": rusage.ru_maxrss * 1024,   # ru_maxrss is kB on Linux
            "wall_seconds": wall,
            "stdout": streams[1],
            "stderr": stderr_text,
            "truncated": over_cap,
            "argv": full,
            "worker_hostname": socket.gethostname(),
            "worker_node_id": _node_id(),
            "child_pid": pid}


@ChiaFunction(resources={"circt": 1})
def circt_reduce_run(input_path: str, test_script: str, output_path: str, *,
                     test_args: tuple = (), wall_seconds: int = 60,
                     sigkill_grace_seconds: int = 10,
                     binary: str = CIRCT_BIN_DIR + "/circt-reduce") -> dict:
    """Run circt-reduce with an interestingness script and an output path.

    Builds [binary, input_path, f"--test={test_script}",
    *(f"--test-arg={a}" for a in test_args), "--keep-best", "-o", output_path],
    in its own process group, SIGTERMed at wall_seconds and SIGKILLed
    sigkill_grace_seconds later. --test-must-fail is never passed: the script's
    polarity is exit 0 for interesting (FR-09.2).

    `output_valid` is the non-emptiness half of §10.2's post-exit validation and
    is computed only once the process has exited, never while it is running,
    because --keep-best defaults to true and a kill can land mid-write. The
    parse half and the re-run of the script are the caller's, which is where the
    input language is known.

    Returns:
        {"success": bool, "returncode": int, "wall_seconds": float,
         "output_valid": bool, "log_tail": str}
    Worker:
        {"circt": 1}.
    Raises:
        nothing.
    """
    argv = [binary, input_path, f"--test={test_script}",
            *(f"--test-arg={a}" for a in test_args),
            "--keep-best", "-o", output_path]
    started = time.monotonic()
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        log = proc.communicate(timeout=wall_seconds)[0]
    except subprocess.TimeoutExpired:
        _killpg(proc.pid, signal.SIGTERM)
        try:
            log = proc.communicate(timeout=sigkill_grace_seconds)[0]
        except subprocess.TimeoutExpired:
            _killpg(proc.pid, signal.SIGKILL)
            log = proc.communicate()[0]
    finally:
        _killpg(proc.pid)
    out = Path(output_path)
    return {"success": proc.returncode == 0,
            "returncode": proc.returncode,
            "wall_seconds": time.monotonic() - started,
            "output_valid": out.is_file() and out.stat().st_size > 0,
            "log_tail": (log or b"").decode("utf-8", "replace")[-4000:]}


@ChiaFunction(resources={"circt": 1})
def circt_symbolize(frames: list, *, tool_path: str = "",
                    circt_roots: tuple = CIRCT_ROOTS,
                    symbolizer: str = "llvm-symbolizer",
                    timeout_seconds: int = 120) -> list:
    """Resolve LLVM crash-trace frames against the objects they actually lie in.

    Each input frame is {"index", "address", "shape", "module", "offset",
    "function", "file", "line"} as `03-LLD.md` §3.6.2's _FRAME parsed it. Frames
    whose shape is "module_offset" are GROUPED BY MODULE and resolved with one
    llvm-symbolizer --obj=<module> --demangle --output-style=JSON call per
    module, that module's offsets on stdin; frames whose shape is "attributed"
    are returned unchanged, because LLVM already resolved them at print time and
    there is no module to ask.

    Feeding runtime addresses with --obj=<the tool> asks the symboliser about an
    object those addresses are not in and resolves nothing at all (§3.6.2,
    measured). The offset from the parentheses is the value it wants.

    JSON is used rather than the default line format because the default emits a
    two-line record per address separated by blank lines. --functions is left at
    its default, linkage, because --functions=short returns "??" under
    -gline-tables-only; --inlines is not passed, an inlined frame changing a
    frame tuple's length without changing the bug.

    `in_circt_object` is computed for both shapes: a module_offset frame is in a
    CIRCT object when its module is *tool_path* or its basename matches
    libCIRCT*.so*, and an attributed frame when its file lies under one of
    *circt_roots*, which covers the generated .inc files as well as the sources.

    Returns:
        one dict per input frame, in input order, with the same keys plus
        "in_circt_object"; unresolved fields are "" and 0.
    Worker:
        {"circt": 1} - the objects are the worker's.
    Raises:
        nothing. An unparseable line yields an unresolved record.
    """
    out = [dict(f) for f in frames]
    by_module: dict = {}
    for i, frame in enumerate(out):
        if frame.get("shape") == "module_offset" and frame.get("module"):
            by_module.setdefault(frame["module"], []).append(i)
    for module, indexes in by_module.items():
        records = _symbolize_module(symbolizer, module,
                                    [out[i].get("offset", "") for i in indexes],
                                    timeout_seconds)
        for i, record in zip(indexes, records):
            out[i].update(record)
    for frame in out:
        frame["in_circt_object"] = _in_circt_object(frame, tool_path, circt_roots)
    return out


# --- the parts, which are not nodes and take no worker resource -------------

def _symbolize_module(symbolizer: str, module: str, offsets: list,
                      timeout_seconds: int) -> list:
    """One llvm-symbolizer call for one module; one record per offset, in order."""
    blank = {"function": "", "file": "", "line": 0}
    if not offsets:
        return []
    try:
        proc = subprocess.run(
            [symbolizer, f"--obj={module}", "--demangle", "--output-style=JSON"],
            input="\n".join(offsets) + "\n", capture_output=True, text=True,
            timeout=timeout_seconds)
    except (OSError, subprocess.SubprocessError):
        return [dict(blank) for _ in offsets]
    records = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            symbol = (json.loads(line).get("Symbol") or [{}])[0]
        except (ValueError, AttributeError, IndexError):
            records.append(dict(blank))
            continue
        records.append({"function": symbol.get("FunctionName", "") or "",
                        "file": symbol.get("FileName", "") or "",
                        "line": int(symbol.get("Line") or 0)})
    records.extend(dict(blank) for _ in range(len(offsets) - len(records)))
    return records[:len(offsets)]


def _in_circt_object(frame: dict, tool_path: str, circt_roots: tuple) -> bool:
    """§3.6.2's predicate, one line per shape."""
    if frame.get("shape") == "module_offset":
        module = frame.get("module", "")
        return bool(module) and (module == tool_path
                                 or fnmatch.fnmatch(os.path.basename(module),
                                                    "libCIRCT*.so*"))
    path = frame.get("file", "")
    return bool(path) and any(path.startswith(root) for root in circt_roots)


def _limit_hit(killed: bool, sig: Optional[str], cpu_used: float,
               cpu_seconds: int, stderr: str) -> Optional[str]:
    """§3.10's three rules, tested in this order, and the only place they live."""
    if killed:
        return "wall"
    if sig == "SIGXCPU" or cpu_used >= cpu_seconds:
        return "cpu"
    if any(literal in stderr for literal in ALLOCATION_FAILURE_LITERALS):
        return "address_space"
    if any(line.strip() == _MEMORY_ERROR_LINE for line in stderr.splitlines()):
        return "address_space"
    return None


def _drain(fds: dict, deadline: float, cap: int, pgid: int) -> tuple:
    """Read both streams to EOF or to *deadline*, killing the group at expiry.

    Returns ({stream number: text}, whether either stream passed *cap*, whether
    the wall-clock killer fired). Reading concurrently is not an optimisation: a
    child that fills a pipe the parent is not reading deadlocks before it can be
    timed out.
    """
    buffers = {key: bytearray() for key in fds}
    seen = {key: 0 for key in fds}
    open_fds = {fd: key for key, fd in fds.items()}
    killed, grace_end = False, 0.0
    try:
        while open_fds:
            now = time.monotonic()
            if not killed and now >= deadline:
                _killpg(pgid)
                killed, grace_end = True, now + _POST_KILL_DRAIN_SECONDS
            if killed and now >= grace_end:
                break
            budget = (grace_end if killed else deadline) - now
            ready = select.select(list(open_fds), [], [],
                                  max(0.0, min(budget, _POLL_SECONDS)))[0]
            for fd in ready:
                chunk = os.read(fd, 65536)
                if not chunk:
                    del open_fds[fd]
                    continue
                key = open_fds[fd]
                seen[key] += len(chunk)
                room = cap - len(buffers[key])
                if room > 0:
                    buffers[key] += chunk[:room]
    finally:
        for fd in fds.values():
            try:
                os.close(fd)
            except OSError:                         # pragma: no cover
                pass
    return ({key: bytes(buf).decode("utf-8", "replace") for key, buf in buffers.items()},
            any(seen[key] > cap for key in fds),
            killed)


def _reap(pid: int, deadline: float, killed: bool) -> tuple:
    """os.wait4 the child, killing the group if it outlives *deadline* anyway."""
    while True:
        done, status, rusage = os.wait4(pid, os.WNOHANG)
        if done:
            return status, rusage, killed
        if not killed and time.monotonic() >= deadline:
            _killpg(pid)
            killed = True
        time.sleep(0.01)


def _signal_name(number: int) -> str:
    """"SIGABRT" for 6, and the bare number for a signal outside the enum."""
    try:
        return signal.Signals(number).name
    except ValueError:                              # pragma: no cover
        return f"SIG{number}"


def _killpg(pgid: int, sig: int = signal.SIGKILL) -> None:
    """Signal the whole group, and say nothing when it has already gone."""
    try:
        os.killpg(pgid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _node_id() -> str:
    """This Ray node's id, or "" outside a session.

    ray.get_runtime_context() STARTS a local Ray instance when none is running,
    which a unit test must not pay for, so the session is read out of
    sys.modules exactly as store.py reads it.
    """
    ray = sys.modules.get("ray")
    if ray is None or not ray.is_initialized():
        return ""
    try:
        return ray.get_runtime_context().get_node_id()
    except Exception:                               # pragma: no cover
        return ""


__all__ = ["circt_exec_probe", "circt_reduce_run", "circt_symbolize",
           "CPU_HARD_MARGIN_SECONDS", "ALLOCATION_FAILURE_LITERALS",
           "CIRCT_BIN_DIR", "CIRCT_ROOTS"]
