"""The three generic CIRCT functions proposed for `chia/chipyard/circt.py`."""
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
CPU_HARD_MARGIN_SECONDS = 5

#: The three allocation-failure literals FR-06.7 names and `03-LLD.md` §3.6 fixes verbatim.
ALLOCATION_FAILURE_LITERALS = ("std::bad_alloc", "out of memory",
                               "LLVM ERROR: out of memory")

#: `RLIMIT_AS` does not kill.
_MEMORY_ERROR_LINE = "MemoryError"

#: The same failures as the LINE OPENINGS a failing runtime actually prints.
ALLOCATION_FAILURE_LINES = (
    "terminate called after throwing an instance of 'std::bad_alloc'",
    "what():  std::bad_alloc",
    "LLVM ERROR: out of memory",
    "out of memory",
    _MEMORY_ERROR_LINE,
)

#: Where the image puts the source-built binaries (`03-LLD.md` §5.1).
CIRCT_BIN_DIR = "/workspace/circt/build/bin"

#: The `in_circt_object` default, which is the image's one CIRCT root.
CIRCT_ROOTS = ("/workspace/circt/",)

#: How long the drain is allowed to continue after the wall-clock killer fires.
_POST_KILL_DRAIN_SECONDS = 2.0

#: The select() slice, which bounds how late the wall-clock killer can fire.
_POLL_SECONDS = 0.2


@ChiaFunction(resources={"circt": 1})
def circt_exec_probe(tool: str, argv: list, *, cwd: str,
                     wall_seconds: int, address_space_bytes: int,
                     cpu_seconds: int, nofile: int = 1024,
                     output_byte_cap: int = 1_000_000) -> dict:
    """Run one CIRCT binary on one input, bounded, with no shell anywhere.

    Returns:
        {"exit_status": int | None, "signal": str | None, "limit_hit": str | None, "cpu_seconds": float, "peak_rss_bytes": int, "wall_seconds": float, "stdout": str, "stderr": str, "truncated": bool, "argv": list[str], "worker_hostname": str, "worker_node_id": str, "child_pid": int}.
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
    peak_rss = rusage.ru_maxrss * 1024              # ru_maxrss is kB on Linux
    return {"exit_status": exit_status,
            "signal": sig,
            "limit_hit": _limit_hit(killed, sig, cpu_used, cpu_seconds, stderr_text,
                                    peak_rss_bytes=peak_rss,
                                    address_space_bytes=address_space_bytes),
            "cpu_seconds": cpu_used,
            "peak_rss_bytes": peak_rss,
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

    --test-must-fail is never passed: the script's polarity is exit 0 for
    interesting (FR-09.2). `output_valid` is computed once the process has
    exited, because --keep-best defaults to true and a kill can land mid-write.

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
            "log_tail": (log or b"").decode("utf-8", "backslashreplace")[-4000:]}


@ChiaFunction(resources={"circt": 1})
def circt_symbolize(frames: list, *, tool_path: str = "",
                    circt_roots: tuple = CIRCT_ROOTS,
                    symbolizer: str = "llvm-symbolizer",
                    timeout_seconds: int = 120) -> list:
    """Resolve LLVM crash-trace frames against the objects they actually lie in.

    Returns:
        one dict per input frame, in input order, with the same keys plus "in_circt_object".
    Worker:
        {"circt": 1} - the objects are the worker's.
    Raises:
        nothing.
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
            # MERGE, never replace.
            out[i].update({key: value for key, value in record.items() if value})
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


def allocation_evidence(stderr: str) -> bool:
    """Whether *stderr* REPORTS an allocation failure, rather than mentioning one."""
    return any(line.strip().startswith(ALLOCATION_FAILURE_LINES)
               for line in stderr.splitlines())


def _limit_hit(killed: bool, sig: Optional[str], cpu_used: float,
               cpu_seconds: int, stderr: str, *, peak_rss_bytes: int = 0,
               address_space_bytes: int = 0) -> Optional[str]:
    """§3.10's three rules, tested in this order, and the only place they live."""
    if killed:
        return "wall"
    if sig == "SIGXCPU" or cpu_used >= cpu_seconds:
        return "cpu"
    if allocation_evidence(stderr):
        return "address_space"
    if address_space_bytes and peak_rss_bytes >= address_space_bytes:
        return "address_space"
    return None


def _drain(fds: dict, deadline: float, cap: int, pgid: int) -> tuple:
    """Read both streams to EOF or to *deadline*, killing the group at expiry."""
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
    # backslashreplace, never replace.
    return ({key: bytes(buf).decode("utf-8", "backslashreplace")
             for key, buf in buffers.items()},
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
    """This Ray node's id, or "" outside a session."""
    ray = sys.modules.get("ray")
    if ray is None or not ray.is_initialized():
        return ""
    try:
        return ray.get_runtime_context().get_node_id()
    except Exception:                               # pragma: no cover
        return ""


__all__ = ["circt_exec_probe", "circt_reduce_run", "circt_symbolize",
           "allocation_evidence", "CPU_HARD_MARGIN_SECONDS",
           "ALLOCATION_FAILURE_LITERALS", "ALLOCATION_FAILURE_LINES",
           "CIRCT_BIN_DIR", "CIRCT_ROOTS"]
