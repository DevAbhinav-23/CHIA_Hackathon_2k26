"""The four apparatus nodes that touch a probe: execute, judge, differential, reduce.

Worker-side (`03-LLD.md` §3.6). It imports `contract`, `ddmin`, the three generic
CIRCT functions, and **from `store` the record dataclasses only**: never
`LoopStore`, which it could not use anyway, the store being a `SQLiteNode`
pinned to the head. Every node here returns its records and the head writes the
rows (FR-16.1, FR-17.3).

`circt_core` stands in for `chia.chipyard.circt` until CHIA carries the three
additions of §3.10; `upstream/chia-chipyard-circt-additions.py` is the block the
pull request appends, and the import moves with no other change.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.circt_core import (ALLOCATION_FAILURE_LITERALS, CIRCT_BIN_DIR,
                                       CIRCT_ROOTS, CPU_HARD_MARGIN_SECONDS,
                                       circt_exec_probe, circt_reduce_run,
                                       circt_symbolize)
from circt_bug_loop.ddmin import ddmin
from circt_bug_loop.contract import schema
from circt_bug_loop.store import (BuildResult, Frame, ImageSpec, OracleVerdict,
                                  ReducedCase)

#: `03-LLD.md` §9.4's implementation constants that belong to this module. The
#: two imported above are defined once, in the function that builds the argv
#: they parameterise, and re-exported here because §9.4 names this module.
PROBE_NOFILE = 1024
PROBE_WALL_MARGIN_SECONDS = 60

#: §3.6's three allocation-failure literals, under the name §3.6 gives them.
_ALLOC_LITERALS = ALLOCATION_FAILURE_LITERALS

#: The two §3.10 helpers are called IN PROCESS and never dispatched: a nested
#: `chia_remote` would ask for a second {"circt": 1} slot for the same probe and
#: deadlock a cluster whose apparatus concurrency is the slot count (§12.1).
#: CHIA stores the undecorated function on the wrapper
#: (`chia:chia/base/ChiaFunction.py:129`), and calling it is also what keeps the
#: profiler, and the local Ray session it starts, out of a unit test.
_exec_probe = circt_exec_probe._chia_original
_symbolize = circt_symbolize._chia_original

#: The diagnostic that separates FR-06.6's two `parse_error` reasons: a pass the
#: seed's RUN: line named and CIRCT has since renamed exits non-zero exactly as
#: a rejected input does, and only the text tells them apart (§3.6, measured).
_ARGV_REJECTED = "does not refer to a registered pass or pass pipeline"


class BinaryMismatch(Exception):
    """A tool binary's SHA-256 differs from `ImageSpec.tool_hashes` (FR-06.1).

    The caller, B12, stops the run and names the worker: the tree has been
    mutated and every verdict from that worker is suspect (§5.2).
    """

    def __init__(self, tool: str, expected_sha: Optional[str], actual_sha: str) -> None:
        super().__init__(f"{tool}: expected {expected_sha}, ran {actual_sha}")
        self.tool, self.expected_sha, self.actual_sha = tool, expected_sha, actual_sha


# --- 3.6.1 The three firing patterns, fixed verbatim ------------------------

_ASSERT_GLIBC = re.compile(
    r"^(?:.*?: )?(?P<file>[^\s:]+):(?P<line>\d+): "
    r"(?P<func>.+?): Assertion `(?P<expr>.*)' failed\.$")
_ASSERT_UNREACHABLE = re.compile(
    r"^UNREACHABLE executed(?: at (?P<file>[^\s:]+):(?P<line>\d+))?!$")
_FATAL_ERROR = re.compile(r"^LLVM ERROR: (?P<message>.*)$")

# `func` is `.+?` and not `[^:]+`, and that one character is the difference
# between classifying a CIRCT assertion and never classifying one (K1): glibc
# prints __PRETTY_FUNCTION__, which for every C++ member or namespaced function
# contains `::`, and CIRCT is C++. The lazy group is bounded on the right by the
# literal ": Assertion `", which is the one place the line can end.


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def probe_execute(spec, image_spec: ImageSpec, limits: dict,
                  artefact_dir: str, *, bin_dir: str = CIRCT_BIN_DIR) -> dict:
    """Run one probing input through its tool, bounded, and classify it seven ways.

    The body does four things and nothing else: hash the binaries the argv will
    invoke and refuse on a mismatch; execute through `circt_exec_probe`, which
    is a direct execve under the `prlimit` prefix in its own process group;
    classify into exactly one of FR-06.9's seven statuses by `classify_build`
    alone; and persist both streams, truncated at `probe_output_byte_cap`.

    *bin_dir* is §5.1's directory and defaults to the image's. It is a keyword
    because every recorded fixture and every tier-1 measurement runs a build
    outside the image, and a hard-coded path would make the node untestable
    anywhere the image is not (erratum candidate against §3.6's signature).

    Returns:
        {"build_result": BuildResult, "probe_result": ProbeResult}
    Worker:
        {"circt": 1} - it runs the image's own CIRCT binaries.
    Raises:
        BinaryMismatch(tool, expected_sha, actual_sha) when a tool binary's
            SHA-256 differs from image_spec.tool_hashes.
    """
    binary = os.path.join(bin_dir, spec.tool)
    actual = _sha256(binary)
    expected = image_spec.tool_hashes.get(spec.tool)
    if expected != actual:
        raise BinaryMismatch(spec.tool, expected, actual)

    out = _exec_probe(
        binary, list(spec.argv), cwd=artefact_dir,
        wall_seconds=limits["probe_wall_seconds"],
        address_space_bytes=limits["probe_address_space_bytes"],
        cpu_seconds=limits["probe_cpu_seconds"],
        nofile=PROBE_NOFILE,
        output_byte_cap=limits["probe_output_byte_cap"])

    status, reason = classify_build(out["exit_status"], out["signal"],
                                    out["stderr"], out["limit_hit"])
    # FR-06.4: a probe the stage itself killed carries a NULL signal, so a
    # timeout can never be read back as a crash.
    signal_name = None if status == "timeout" else out["signal"]

    directory = Path(artefact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stdout_path = directory / "stdout.txt"
    stderr_path = directory / "stderr.txt"
    stdout_path.write_text(out["stdout"], encoding="utf-8")
    stderr_path.write_text(out["stderr"], encoding="utf-8")
    (directory / "argv.json").write_text(_canonical(out["argv"]), encoding="utf-8")

    build = BuildResult(
        probe_id=spec.probe_id, run_manifest_id=spec.run_manifest_id,
        run_commit=image_spec.circt_sha, image_digest=image_spec.image_digest,
        status=status, binary_path=binary, binary_sha256=actual,
        argv=out["argv"], exit_status=out["exit_status"], signal=signal_name,
        limit_hit=out["limit_hit"], cpu_seconds=out["cpu_seconds"],
        wall_seconds=out["wall_seconds"], peak_rss_bytes=out["peak_rss_bytes"],
        worker_hostname=out["worker_hostname"], worker_node_id=out["worker_node_id"],
        child_pid=out["child_pid"], stdout_path=str(stdout_path),
        stderr_path=str(stderr_path), stdout_bytes=len(out["stdout"].encode("utf-8")),
        stderr_bytes=len(out["stderr"].encode("utf-8")), truncated=out["truncated"])

    result = schema.ProbeResult(
        probe_id=spec.probe_id, run_manifest_id=spec.run_manifest_id,
        seed_sha=spec.seed_sha, arm=spec.arm, iteration=spec.iteration,
        build_status=status, oracle_fired=False, stopping_stage="stage_3",
        stopping_reason=reason, artefact_dir=artefact_dir,
        exit_status=out["exit_status"], signal=signal_name,
        limit_hit=out["limit_hit"])
    schema.validate(result)
    return {"build_result": build, "probe_result": result}


def classify_build(rc: Optional[int], signal: Optional[str], stderr: str,
                   limit_hit: Optional[str]) -> tuple:
    """Return (status, reason) for one finished probe, by §3.6's table alone.

    The order is the table's and is not negotiable: a limit kill is never a
    crash (FR-06.4), allocation evidence outranks every firing class (FR-06.7,
    FR-07.2), and the `oom` row by evidence needs death by signal as well,
    because an ordinary diagnostic carrying the phrase "out of memory" is a
    rejected input and not an exhausted machine.

    Returns:
        status is one of FR-06.9's seven; reason is the stopping_reason the
        ProbeResult carries, and is "" for clean_exit.
    Worker:
        pure; it reads four values and runs nothing.
    Raises:
        nothing.
    """
    if limit_hit == "wall":
        return "timeout", "wall_limit"
    if limit_hit == "cpu":
        return "timeout", "cpu_limit"
    allocation = any(literal in stderr for literal in _ALLOC_LITERALS)
    if limit_hit == "address_space":
        return "oom", "address_space_limit"
    if signal is not None and allocation:
        return "oom", "allocation_failure"
    if _first_match(_ASSERT_GLIBC, stderr) or _first_match(_ASSERT_UNREACHABLE, stderr):
        return "assertion", "assertion_fired"
    if _first_match(_FATAL_ERROR, stderr):
        return "fatal_error", "llvm_error"
    if signal is not None:
        return "crash", "died_by_signal"
    if rc != 0:
        return ("parse_error",
                "tool_rejected_argv" if _ARGV_REJECTED in stderr
                else "tool_rejected_input")
    return "clean_exit", ""


# --- 3.6.2 B3, the primary oracle -------------------------------------------

_FRAME = re.compile(
    r"^\s*#(?P<i>\d+)\s+(?P<addr>0x[0-9a-f]+)\s+"
    r"(?:(?P<func>.*?)\s+)?"
    r"(?:\((?P<module>[^()]+)\+(?P<offset>0x[0-9a-f]+)\)"
    r"|(?P<file>[^\s()]+):(?P<line>\d+):(?P<col>\d+))$")

#: §3.7.1's crash-handler prologue. Every LLVM crash begins with these, so a
#: fingerprint taken from the raw trace is mostly boilerplate: measured on the
#: recorded 466-frame trace, three of the top five raw slots were constant
#: across every crash the campaign can produce.
_PROLOGUE = ("llvm::sys::PrintStackTrace", "llvm::sys::RunSignalHandlers", "SignalHandler",
             "__restore_rt", "pthread_kill", "raise", "abort", "__assert_fail",
             "llvm::report_fatal_error", "llvm::llvm_unreachable_internal")

#: What a lambda's demangled name reduces to under `_normalise_function`; never
#: a fingerprint frame, because it names no function a reader could look up.
_DEGENERATE = ("", "operator")

_FIRING = ("crash", "assertion", "fatal_error")


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def oracle_primary(build: BuildResult, image_spec: ImageSpec, artefact_dir: str,
                   *, circt_roots: tuple = CIRCT_ROOTS,
                   symbolizer: str = "llvm-symbolizer") -> OracleVerdict:
    """Decide whether the probe found a defect, and say which kind.

    A pure function of the stored `BuildResult` plus `llvm-symbolizer` on fixed
    objects, so it is fully idempotent. Four steps: fire or not; extract the
    assertion or the fatal message; symbolise every frame against the module it
    actually lies in; and decide scope, **after** the prologue strip, because
    unstripped the first frame is `llvm::sys::PrintStackTrace` for every crash
    in the campaign and every candidate would be out of scope.

    *circt_roots* and *symbolizer* are keywords for the reason `probe_execute`'s
    *bin_dir* is: §3.6.2 spells the predicate against the image's own paths, and
    every recorded fixture carries a different prefix (erratum candidate).

    Returns:
        OracleVerdict, with fired False and oracle_class None when it did not.
    Worker:
        {"circt": 1} - it runs llvm-symbolizer against the image's own binary.
    Raises:
        nothing. An unsymbolisable frame is recorded unresolved, not raised.
    """
    stderr = _read(build.stderr_path)
    fired = build.status in _FIRING
    oracle_class = build.status if fired else None

    assertion_text, assertion_site, fatal_message = None, None, None
    if oracle_class == "assertion":
        assertion_text, assertion_site = _extract_assertion(stderr)
    elif oracle_class == "fatal_error":
        found = _first_match(_FATAL_ERROR, stderr)
        fatal_message = found[1].group("message") if found else None

    frames = _parse_frames(stderr) if fired else []
    if frames:
        frames = [Frame(**record) for record in
                  _symbolize([_as_dict(f) for f in frames],
                             tool_path=build.binary_path, circt_roots=circt_roots,
                             symbolizer=symbolizer)]
    stripped = strip_prologue(frames)

    repro = shlex.join([build.binary_path, *_probe_argv(build.argv)])
    directory = Path(artefact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "frames.json").write_text(
        _canonical([_as_dict(f, resolved=True) for f in frames]), encoding="utf-8")
    repro_path = directory / "repro.sh"
    repro_path.write_text(f"#!/bin/sh\n{repro}\n", encoding="utf-8")
    repro_path.chmod(0o755)

    return OracleVerdict(
        probe_id=build.probe_id, fired=fired, oracle_class=oracle_class,
        assertion_text=assertion_text, assertion_site=assertion_site,
        fatal_message=fatal_message, frames=frames,
        prologue_dropped=len(frames) - len(stripped),
        frames_resolved=sum(1 for f in frames if f.function),
        frames_with_location=sum(1 for f in frames
                                 if f.line > 0 and f.in_circt_object),
        fingerprint_frame=_fingerprint_frame(stripped),
        out_of_scope_root=bool(fired) and not (stripped and stripped[0].in_circt_object),
        repro_command=repro, flag_string=image_spec.flag_string,
        tool_version_output=_tool_version(build.binary_path))


def strip_prologue(frames: list) -> list:
    """Drop the crash-handler prologue and return what is left (§3.7.1).

    A leading frame goes when its normalised function name is one of the ten of
    `_PROLOGUE`, or when it has no resolved function and its module is libc. The
    strip stops at the first survivor, so a frame deeper in the trace that
    happens to be named `abort` is kept.

    Returns:
        the surviving frames, in trace order; the caller takes the count it
        dropped from the two lengths, which is `prologue_dropped`.
    Worker:
        pure.
    Raises:
        nothing.
    """
    index = 0
    while index < len(frames):
        frame = frames[index]
        name = _normalise_function(frame.function)
        if name in _PROLOGUE or (not frame.function and _is_libc(frame.module)):
            index += 1
            continue
        break
    return frames[index:]


def _extract_assertion(stderr: str) -> tuple:
    """(assertion_text, assertion_site) for whichever assertion pattern fired.

    For `_ASSERT_GLIBC` both are verbatim from stderr, character for character
    (FR-07.3). For `_ASSERT_UNREACHABLE` the text is the PRECEDING stderr line,
    a newline and the matched line with its trailing `!` removed, because LLVM
    writes the message and the phrase in two separate writes with a newline
    between them, so the message is never on the same line (K16).
    """
    found = _first_match(_ASSERT_GLIBC, stderr)
    if found:
        match = found[1]
        return match.group("expr"), f"{match.group('file')}:{match.group('line')}"
    found = _first_match(_ASSERT_UNREACHABLE, stderr)
    if not found:
        return None, None
    index, match = found
    lines = stderr.splitlines()
    text = lines[index].rstrip("!")
    if index > 0:
        text = f"{lines[index - 1]}\n{text}"
    site = (f"{match.group('file')}:{match.group('line')}"
            if match.group("file") else None)
    return text, site


def _parse_frames(stderr: str) -> list:
    """Every `_FRAME` line of the trace, in trace order, both shapes (§3.6.2)."""
    frames = []
    for line in stderr.splitlines():
        match = _FRAME.match(line)
        if not match:
            continue
        module = match.group("module") or ""
        frames.append(Frame(
            index=int(match.group("i")), address=match.group("addr"),
            shape="module_offset" if module else "attributed",
            module=module, offset=match.group("offset") or "",
            function=match.group("func") or "", file=match.group("file") or "",
            line=int(match.group("line") or 0), in_circt_object=False))
    return frames


def _fingerprint_frame(stripped: list) -> Optional[str]:
    """"<function> <basename(file)>", the first stripped CIRCT frame with a line.

    No line number: a one-line edit inside the same function must not split one
    bug into two across runs (§3.7.1). A degenerate name is skipped, so the name
    in a fingerprint is always a function a reader can look up.
    """
    for frame in stripped:
        name = _normalise_function(frame.function)
        if frame.in_circt_object and frame.line > 0 and name not in _DEGENERATE:
            return f"{name} {os.path.basename(frame.file)}"
    return None


def _normalise_function(name: str) -> str:
    """§3.7.1's four steps: cut the parameter list, drop ` const`, collapse space.

    The cut is at the first `(` at bracket depth zero, so a `(` inside a
    template argument is kept. `--functions=short` would do the cut for us and
    is not used: measured on the assertions-on build it returns `??` under
    `-gline-tables-only`, a short name needing debug information the flag does
    not emit.
    """
    depth, cut = 0, len(name)
    for index, char in enumerate(name):
        if char == "<":
            depth += 1
        elif char == ">":
            depth = max(0, depth - 1)
        elif char == "(" and depth == 0:
            cut = index
            break
    trimmed = name[:cut]
    if trimmed.endswith(" const"):
        trimmed = trimmed[:-len(" const")]
    return " ".join(trimmed.split())


def _is_libc(module: str) -> bool:
    """Whether a frame's module is the C library, for §3.7.1's second rule."""
    base = os.path.basename(module)
    return base.startswith("libc.so") or base.startswith("libc-")


def _probe_argv(argv: list) -> list:
    """The probe's own argv, the `prlimit` prefix and the tool path removed.

    FR-07.6's line is for a maintainer to paste: the limits are the loop's
    concern and not the report's.
    """
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    return list(argv[1:])


def _as_dict(frame: Frame, *, resolved: bool = False) -> dict:
    """A `Frame` as the plain dict `circt_symbolize` takes and returns."""
    keys = ("index", "address", "shape", "module", "offset", "function", "file", "line")
    out = {key: getattr(frame, key) for key in keys}
    if resolved:
        out["in_circt_object"] = frame.in_circt_object
    return out


# --- 3.6.4 B5, the reducer --------------------------------------------------

#: The six output-mode flags `circt-verilog` takes (§4.4), one of which a
#: `.sv` probe's argv carries and which §4.7's third row keeps.
_OUTPUT_MODE_FLAGS = ("--lint-only", "--parse-only", "--import-only",
                      "--ir-moore", "--ir-llhd", "--ir-hw")

#: §4.7's first row: the tools whose input is MLIR text whatever its extension.
_MLIR_TOOLS = ("circt-opt", "circt-translate", "arcilator")

#: One printed MLIR operation per line: an optional result list, then a
#: dotted `dialect.op` name. `03-LLD.md` and `01-FRD.md` require an operation
#: count (FR-09.5) and neither defines one; this is that definition, fixed here.
#: For a language with no operations the count is the non-blank line count.
_OP_LINE = re.compile(r"\s*(?:%[\w$.\-]+(?:\s*,\s*%[\w$.\-]+)*\s*=\s*)?"
                      r"[a-zA-Z_]\w*\.[a-zA-Z_][\w.]*")


class _BudgetExpired(Exception):
    """The textual reduction reached `reduction_wall_seconds` (FR-09.4)."""


def select_reducer(spec) -> dict:
    """§4.7's reducer-selection table, by the probe's input language and no other.

    Returns the reducer, the lift if any, and the tool and arguments the
    interestingness test runs, with the candidate appended last because that is
    the calling convention `circt-reduce` fixes (`circt:lib/Reduce/Tester.cpp:
    42-46`) and §10.2's template follows.

    The `.sv` rows are decided by the EXTENSION before the tool, which is the one
    ambiguity §4.7 leaves: its first row claims "every `circt-translate` probe"
    and its fourth claims "`.sv` entered through `circt-translate
    --import-verilog`", and a `.sv` probe entering through `circt-translate`
    satisfies both. The fourth row is the specific one and wins (erratum
    candidate).

    Returns:
        {"reducer", "lift", "test_tool", "test_args"}.
    Worker:
        pure; it reads a `ProbeSpec` and runs nothing.
    Raises:
        nothing.
    """
    extension = os.path.splitext(spec.input_filename)[1].lower()
    args = _test_args(spec)
    if extension == ".sv" and spec.tool == "circt-verilog":
        # circt-verilog READS MLIR, through --format=mlir, so the branch's test
        # is its own tool on its own lift (§4.4, run end to end on both the SDK
        # binary and the source-built slang one). Every other token of the
        # probe's argv, the seed's own output-mode flag included, is kept.
        return {"reducer": "circt-reduce", "lift": "circt-verilog --ir-moore",
                "test_tool": "circt-verilog", "test_args": ["--format=mlir", *args]}
    if extension == ".sv" and spec.tool == "circt-translate":
        # circt-translate has no --format= at all, so it cannot be re-fed its own
        # lift; circt-opt on the Moore IR is the post-parse pipeline that entry
        # point implies, which for --import-verilog is MLIR's own verifier.
        return {"reducer": "circt-reduce", "lift": "circt-verilog --ir-moore",
                "test_tool": "circt-opt", "test_args": ["-o", "/dev/null"]}
    if extension == ".fir":
        return {"reducer": "circt-reduce", "lift": "firtool --ir-fir",
                "test_tool": spec.tool, "test_args": args}
    if extension == ".mlir" or spec.tool in _MLIR_TOOLS:
        return {"reducer": "circt-reduce", "lift": None,
                "test_tool": spec.tool, "test_args": args}
    return {"reducer": "textual-ddmin", "lift": None,
            "test_tool": spec.tool, "test_args": args}


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def reduce_case(spec, verdict: OracleVerdict, limits: dict, artefact_dir: str,
                *, bin_dir: str = CIRCT_BIN_DIR) -> ReducedCase:
    """Shrink a firing input under a firing-specific interestingness test.

    The reducer is chosen by input language, by FR-09.9's rule and no other, and
    the binary is the SOURCE-BUILT `circt-reduce`, because the reduced case must
    be parsed by the build that fired. The cost is that its own assertions are
    on and it can die on the candidate: measured 2026-09-14, the reducer itself
    took rc 139 on a parser stack overflow, because it parses the candidate with
    the same parser the candidate overflows. That is `reducer_aborted`, and it
    routes to the textual reducer on the same run, before the budget is spent.

    Returns:
        ReducedCase, naming the reducer that ran and whether it reached a
        fixpoint; reduced=False with a reason where nothing could run.
    Worker:
        {"circt": 1} - it runs the image's own source-built circt-reduce.
    Raises:
        nothing. A reducer that aborts on its own assertion is recorded
        reducer_aborted and the last valid --keep-best output is kept.
    """
    started = time.monotonic()
    directory = Path(artefact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    source = Path(spec.input_path)
    before = _read(str(source))
    if not verdict.fired or verdict.oracle_class not in _CLASS_BLOCKS:
        return _unreduced(spec, before, "oracle_did_not_fire", started)

    counter = directory / "interesting.calls"
    counter.write_text("")
    choice = select_reducer(spec)
    target, lift, reason = source, None, None

    if choice["lift"]:
        lifted, lift = _lift(choice["lift"], source, directory, bin_dir, limits)
        if lifted is None:
            choice, reason = _textual(spec), "lift_failed"
        else:
            target = lifted

    script = directory / "interesting.sh"
    _write_script(script, verdict, choice, bin_dir, limits, counter)

    if choice["reducer"] == "circt-reduce" and lift and not _interesting(script, target):
        # §4.7's fifth trigger: the lift ran and the recorded failure is not on
        # it, so the lift changed the failure. One call buys that answer.
        choice, reason, target, lift = _textual(spec), "lift_changed_failure", source, None
        _write_script(script, verdict, choice, bin_dir, limits, counter)

    out_path = directory / ("reduced" + target.suffix)
    truncated, fixpoint = False, False
    if choice["reducer"] == "circt-reduce":
        run = _reduce_run(str(target), str(script), str(out_path), limits, bin_dir)
        truncated = run["wall_seconds"] >= limits["reduction_wall_seconds"]
        fixpoint = run["success"] and not truncated
        kept = _valid_output(out_path, script, bin_dir, limits)
        if not run["success"] and not truncated:
            # reducer_aborted: keep whatever --keep-best left that still
            # validates, and hand THAT to the textual reducer on the same run.
            reason = f"reducer_aborted:{run['returncode']}"
            target = out_path if kept else target
            choice = {**choice, "reducer": "textual-ddmin"}
            _write_script(script, verdict, choice, bin_dir, limits, counter)
        elif not kept:
            reason, truncated = "output_invalid_after_exit", True
            fixpoint = False

    if choice["reducer"] == "textual-ddmin":
        text, fixpoint, expired, why = _textual_reduce(target, script, limits)
        truncated = truncated or expired
        reason = reason or why
        out_path = directory / ("reduced" + target.suffix)
        out_path.write_text(text, encoding="utf-8")

    after = _read(str(out_path)) if out_path.is_file() else before
    if not after:
        after, fixpoint = before, False
        reason = reason or "no_output"
    out_path.write_text(after, encoding="utf-8")

    reduced = len(after.encode("utf-8")) < len(before.encode("utf-8"))
    recheck = _recheck(choice, verdict, out_path, bin_dir, limits)
    return ReducedCase(
        probe_id=spec.probe_id, reducer=choice["reducer"], reduced=reduced,
        fixpoint=fixpoint, budget_truncated=truncated,
        reason=reason or (None if reduced else "no_progress"), lift=lift,
        path=str(out_path),
        size_before_bytes=len(before.encode("utf-8")),
        size_after_bytes=len(after.encode("utf-8")),
        size_before_ops=_count_ops(before), size_after_ops=_count_ops(after),
        wall_seconds=time.monotonic() - started,
        interestingness_calls=_calls(counter), **recheck)


def _textual(spec) -> dict:
    """§4.7's last row: the textual reducer on the probe's own language."""
    return {"reducer": "textual-ddmin", "lift": None,
            "test_tool": spec.tool, "test_args": _test_args(spec)}


def _test_args(spec) -> list:
    """The probe's argv with its input path removed; the candidate replaces it."""
    return [token for token in spec.argv if token != spec.input_path]


def _write_script(script: Path, verdict, choice: dict, bin_dir: str,
                  limits: dict, counter: Path) -> None:
    write_interestingness(str(script), verdict,
                          os.path.join(bin_dir, choice["test_tool"]),
                          choice["test_args"], limits, str(counter))


def _lift(lift: str, source: Path, directory: Path, bin_dir: str,
          limits: dict) -> tuple:
    """Run one of §4.7's lifts, retrying `--ir-fir` with `--parse-only`.

    FR-09.9 branch 2: where the recorded failure lies inside the pipeline the
    lift reproduces the failure instead of emitting IR, and `--parse-only` stops
    before the pipeline. Returns (path, the lift that worked) or (None, None).
    """
    attempts = [lift] + (["firtool --parse-only"] if lift == "firtool --ir-fir" else [])
    out = directory / "lifted.mlir"
    for attempt in attempts:
        tool, flag = attempt.split(" ", 1)
        try:
            run = _exec_probe(os.path.join(bin_dir, tool),
                              [flag, "-o", str(out), str(source)],
                              cwd=str(directory),
                              wall_seconds=limits["probe_wall_seconds"],
                              address_space_bytes=limits["probe_address_space_bytes"],
                              cpu_seconds=limits["probe_cpu_seconds"],
                              nofile=PROBE_NOFILE,
                              output_byte_cap=limits["probe_output_byte_cap"])
        except FileNotFoundError:
            continue
        if run["exit_status"] == 0 and out.is_file() and out.stat().st_size:
            return out, attempt
    return None, None


def _reduce_run(input_path: str, script: str, out_path: str, limits: dict,
                bin_dir: str) -> dict:
    return circt_reduce_run._chia_original(
        input_path, script, out_path,
        wall_seconds=limits["reduction_wall_seconds"],
        sigkill_grace_seconds=limits["reduction_sigkill_grace_seconds"],
        binary=os.path.join(bin_dir, "circt-reduce"))


def _interesting(script: Path, candidate: Path) -> bool:
    """One interestingness call: exit 0 means the recorded failure reproduces."""
    try:
        return subprocess.run([str(script), str(candidate)],
                              capture_output=True).returncode == 0
    except OSError:
        return False


def _valid_output(out_path: Path, script: Path, bin_dir: str, limits: dict) -> bool:
    """§10.2's post-exit validation, AFTER the reducer process has exited.

    Non-empty, parses where the language has a parser, and still satisfies the
    same script. A file a kill truncated mid-write fails one of the three and
    the previous good output is kept (FR-09.13).
    """
    if not out_path.is_file() or out_path.stat().st_size == 0:
        return False
    if out_path.suffix == ".mlir":
        try:
            parse = _exec_probe(os.path.join(bin_dir, "circt-opt"),
                                [str(out_path), "-o", os.devnull],
                                cwd=str(out_path.parent),
                                wall_seconds=limits["probe_wall_seconds"],
                                address_space_bytes=limits["probe_address_space_bytes"],
                                cpu_seconds=limits["probe_cpu_seconds"],
                                nofile=PROBE_NOFILE, output_byte_cap=65536)
        except FileNotFoundError:
            return False
        if parse["exit_status"] != 0:
            return False
    return _interesting(script, out_path)


def _textual_reduce(target: Path, script: Path, limits: dict) -> tuple:
    """ddmin over the input's lines, bounded by `reduction_wall_seconds`.

    On expiry the BEST interesting subsequence seen so far is kept rather than
    the work discarded (FR-09.4), which is what `circt-reduce`'s own
    `--keep-best` does for the other branch.
    """
    lines = target.read_text(errors="backslashreplace").splitlines(keepends=True)
    deadline = time.monotonic() + limits["reduction_wall_seconds"]
    best = [lines]
    candidate = target.parent / ("ddmin_candidate" + target.suffix)

    def interesting(subset: list) -> bool:
        if time.monotonic() >= deadline:
            raise _BudgetExpired
        candidate.write_text("".join(subset), encoding="utf-8")
        if not _interesting(script, candidate):
            return False
        if len(subset) < len(best[0]):
            best[0] = list(subset)
        return True

    try:
        out, _calls = ddmin(lines, interesting)
        return "".join(out), True, False, None
    except _BudgetExpired:
        return "".join(best[0]), False, True, "reduction_budget_expired"
    except ValueError:
        return "".join(lines), False, False, "original_not_interesting"
    finally:
        candidate.unlink(missing_ok=True)


def _recheck(choice: dict, verdict: OracleVerdict, case: Path, bin_dir: str,
             limits: dict) -> dict:
    """FR-09.3: re-run the primary oracle's rules on the reduced input.

    Equality of class, assertion text and `file:line` sets `recheck_matches`; a
    mismatch is FR-09.7's `reduction_changed_failure` and the caller carries the
    original input forward.
    """
    blank = {"recheck_class": None, "recheck_assertion_text": None,
             "recheck_assertion_site": None, "recheck_matches": False}
    try:
        run = _exec_probe(os.path.join(bin_dir, choice["test_tool"]),
                          [*choice["test_args"], str(case)],
                          cwd=str(case.parent),
                          wall_seconds=limits["probe_wall_seconds"],
                          address_space_bytes=limits["probe_address_space_bytes"],
                          cpu_seconds=limits["probe_cpu_seconds"],
                          nofile=PROBE_NOFILE,
                          output_byte_cap=limits["probe_output_byte_cap"])
    except FileNotFoundError:
        return blank
    status, _reason = classify_build(run["exit_status"], run["signal"],
                                     run["stderr"], run["limit_hit"])
    text, site = (_extract_assertion(run["stderr"])
                  if status == "assertion" else (None, None))
    return {"recheck_class": status, "recheck_assertion_text": text,
            "recheck_assertion_site": site,
            "recheck_matches": (status == verdict.oracle_class
                                and text == verdict.assertion_text
                                and site == verdict.assertion_site)}


def _unreduced(spec, before: str, reason: str, started: float) -> ReducedCase:
    """FR-09.12's row: no reducer could run, and the reason is recorded."""
    size = len(before.encode("utf-8"))
    return ReducedCase(
        probe_id=spec.probe_id, reducer="none", reduced=False, fixpoint=False,
        budget_truncated=False, reason=reason, lift=None, path=spec.input_path,
        size_before_bytes=size, size_after_bytes=size,
        size_before_ops=_count_ops(before), size_after_ops=_count_ops(before),
        wall_seconds=time.monotonic() - started, interestingness_calls=0,
        recheck_class=None, recheck_assertion_text=None,
        recheck_assertion_site=None, recheck_matches=False)


def _count_ops(text: str) -> int:
    """FR-09.5's operation count, defined by `_OP_LINE` and nowhere else."""
    operations = sum(1 for line in text.splitlines() if _OP_LINE.match(line))
    return operations or sum(1 for line in text.splitlines() if line.strip())


def _calls(counter: Path) -> int:
    """One byte per interestingness call, which the script appends itself."""
    try:
        return counter.stat().st_size
    except OSError:
        return 0


# --- 10.2 The interestingness script ----------------------------------------

#: `03-LLD.md` §10.2, with ONE addition: the counter line. `ReducedCase`
#: requires `interestingness_calls` and `circt-reduce` does not report it -
#: measured 2026-09-14, its own progress lines came to 60 for 53 actual calls -
#: so the script counts itself, one byte per call. That is a twelfth
#: placeholder, `@COUNTER@`, and an erratum candidate against §10.2's eleven.
_INTERESTING_TEMPLATE = """#!/bin/sh
# Interestingness test for one recorded CIRCT failure.
# Contract: exit 0 IFF the recorded failure still reproduces on "$1".
# circt-reduce is run WITHOUT --test-must-fail, so 0 means interesting.
set -u
printf 'x' >> @COUNTER@

# Absolutise the candidate BEFORE cd: circt-reduce passes it relative to ITS cwd.
CANDIDATE=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 1

# Bound the tool ourselves: circt-reduce imposes neither a time nor a memory
# limit on us (C-18). SIGTERM first, SIGKILL after the grace period (FR-09.13).
# The subshell with its own stderr is what keeps the shell's own
# "Segmentation fault <the whole command line>" out of circt-reduce's stderr,
# which it would otherwise print on EVERY interesting candidate.
( exec 2>"$WORK/err"
  timeout --signal=TERM --kill-after=@GRACE@ @WALL@ \\
    prlimit --as=@AS_BYTES@ --cpu=@CPU_SECONDS@ --nofile=@NOFILE@ -- \\
    @TOOL@ @ARGS@ "$CANDIDATE" >"$WORK/out" ) 2>/dev/null
RC=$?

# 124 is timeout's own "the command timed out". A reduction step that hangs is
# not interesting: it is a different failure.
[ "$RC" -ne 124 ] || exit 1

# Memory exhaustion is not the recorded failure either, whatever it looks like.
grep -qF 'std::bad_alloc' "$WORK/err" && exit 1
grep -qF 'out of memory' "$WORK/err" && exit 1

@CLASS_BLOCK@
"""

_CLASS_BLOCKS = {
    "assertion": """# --- class: assertion -------------------------------------------------------
grep -qF @ASSERT_EXPR@ "$WORK/err" || exit 1
grep -qF @ASSERT_SITE@ "$WORK/err" || exit 1
exit 0""",
    "fatal_error": """# --- class: fatal_error -----------------------------------------------------
grep -qF @FATAL_MESSAGE@ "$WORK/err" || exit 1
grep -q '^LLVM ERROR:' "$WORK/err" || exit 1
exit 0""",
    "crash": """# --- class: crash -----------------------------------------------------------
# A crash is a death by signal, which the shell reports as 128+N. Anything below
# 128, and anything that is timeout's own 124, is a different outcome.
[ "$RC" -gt 128 ] || exit 1
grep -qF @TOP_FRAME@ "$WORK/err" || exit 1
exit 0""",
}

#: Every placeholder §10.2 declares. A written script carries none of them:
#: `T-U-probe-45` asserts that no `@NAME@` survives anywhere in the file.
_PLACEHOLDERS = ("@TOOL@", "@ARGS@", "@WALL@", "@GRACE@", "@AS_BYTES@",
                 "@CPU_SECONDS@", "@NOFILE@", "@ASSERT_EXPR@", "@ASSERT_SITE@",
                 "@FATAL_MESSAGE@", "@TOP_FRAME@")


def write_interestingness(path: str, verdict: OracleVerdict, tool_path: str,
                          args: list, limits: dict, counter_path: str) -> str:
    """Write §10.2's script for ONE recorded firing and return its text.

    Exactly one class block is substituted for `@CLASS_BLOCK@`, and it is the
    block for the firing's own class: the earlier three-in-sequence version left
    two of them dead code below an `exit 0`, and `sh -n` passed on it (K15).
    Every value a `grep` compares is `shlex.quote`d, and every `grep` is `-F`,
    fixed strings: an assertion expression carries `&&`, quotation marks,
    parentheses and sometimes `*`, all regular-expression metacharacters.

    `@TOP_FRAME@` is the function-name half of the FINGERPRINT frame and not
    "the first resolved frame", which is `llvm::sys::PrintStackTrace` for every
    crash in the campaign and would match any crash at all (K3).

    Returns:
        the script text, which is also on disk at *path*, mode 0755.
    Worker:
        pure but for the one write; called inside B5, so it takes no slot.
    Raises:
        KeyError when the verdict's class has no block, which is a caller
        defect: a non-firing verdict has no interestingness test.
    """
    frame = verdict.fingerprint_frame
    cpu = limits["probe_cpu_seconds"]
    values = {
        "@TOOL@": shlex.quote(tool_path),
        "@ARGS@": " ".join(shlex.quote(token) for token in args),
        "@WALL@": str(limits["probe_wall_seconds"]),
        "@GRACE@": str(limits["reduction_sigkill_grace_seconds"]),
        "@AS_BYTES@": str(limits["probe_address_space_bytes"]),
        "@CPU_SECONDS@": f"{cpu}:{cpu + CPU_HARD_MARGIN_SECONDS}",
        "@NOFILE@": str(PROBE_NOFILE),
        "@COUNTER@": shlex.quote(counter_path),
        # A None below is a recorded absence and not a defect: an UNREACHABLE
        # with no location has no site, and a trace with no CIRCT frame has no
        # fingerprint frame. The empty string makes that one `grep` vacuous
        # rather than making it compare the four letters of "None"; such a
        # candidate fails the gate's fingerprint question anyway (FR-10.8).
        "@ASSERT_EXPR@": shlex.quote(verdict.assertion_text or ""),
        "@ASSERT_SITE@": shlex.quote(verdict.assertion_site or ""),
        "@FATAL_MESSAGE@": shlex.quote(verdict.fatal_message or ""),
        "@TOP_FRAME@": shlex.quote(frame.rsplit(" ", 1)[0] if frame else ""),
    }
    text = _INTERESTING_TEMPLATE.replace(
        "@CLASS_BLOCK@", _CLASS_BLOCKS[verdict.oracle_class])
    for name, value in values.items():
        text = text.replace(name, value)
    script = Path(path)
    script.write_text(text, encoding="utf-8")
    script.chmod(0o755)
    return text


def _canonical(obj) -> str:
    """`contract.to_json`'s canonical shape, for the lists that are not records.

    `to_json` takes a dataclass; `argv.json` and `frames.json` are a list of
    strings and a list of dicts, so the same four options are spelled here.
    """
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False,
                      separators=(",", ": ")) + "\n"


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _tool_version(binary: str) -> str:
    """The tool's own --version, which still reads "Optimized build." (FR-07.7)."""
    try:
        done = subprocess.run([binary, "--version"], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout or done.stderr


def _first_match(pattern, stderr: str):
    """The first line of *stderr* that *pattern* matches, with its index."""
    for index, line in enumerate(stderr.splitlines()):
        found = pattern.match(line)
        if found:
            return index, found
    return None


def _sha256(path: str) -> str:
    """The SHA-256 of one file, hex, or "" when it is not there (FR-06.1)."""
    try:
        with open(path, "rb") as handle:
            digest = hashlib.sha256()
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return ""


__all__ = ["BinaryMismatch", "probe_execute", "classify_build", "oracle_primary",
           "strip_prologue", "select_reducer", "reduce_case",
           "write_interestingness", "PROBE_NOFILE", "PROBE_WALL_MARGIN_SECONDS",
           "CPU_HARD_MARGIN_SECONDS"]
