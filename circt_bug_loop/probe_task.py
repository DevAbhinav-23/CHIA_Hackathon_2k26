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
import shutil
import subprocess
import time
import dataclasses
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.circt_core import (ALLOCATION_FAILURE_LITERALS, CIRCT_BIN_DIR,
                                       CIRCT_ROOTS, CPU_HARD_MARGIN_SECONDS,
                                       circt_exec_probe, circt_reduce_run,
                                       circt_symbolize)
from circt_bug_loop.contract import schema
from circt_bug_loop.ddmin import ddmin
from circt_bug_loop.store import (BuildResult, DifferentialVerdict, Frame,
                                  ImageSpec, OracleVerdict, ReducedCase)

#: `03-LLD.md` §9.4's implementation constants that belong to this module. The
#: two imported above are defined once, in the function that builds the argv
#: they parameterise, and re-exported here because §9.4 names this module.
PROBE_NOFILE = 1024
PROBE_WALL_MARGIN_SECONDS = 60

#: §3.6's three allocation-failure literals, under the name §3.6 gives them.
_ALLOC_LITERALS = ALLOCATION_FAILURE_LITERALS

#: The three §3.10 helpers are called IN PROCESS and never dispatched: a nested
#: `chia_remote` would ask for a second {"circt": 1} slot for the same probe and
#: deadlock a cluster whose apparatus concurrency is the slot count (§12.1).
#: CHIA stores the undecorated function on the wrapper
#: (`chia:chia/base/ChiaFunction.py:129`), and calling it is also what keeps the
#: profiler, and the local Ray session it starts, out of a unit test.
_exec_probe = circt_exec_probe._chia_original
_symbolize = circt_symbolize._chia_original
_reduce = circt_reduce_run._chia_original

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
        {"build_result": BuildResult, "probe_result": ProbeResult, "counters":
        CounterBlock}, the counters counting one probe at stage_3, as 3.11
        requires of every node; an `internal_error` status is the failed one.
    Worker:
        {"circt": 1} - it runs the image's own CIRCT binaries.
    Raises:
        BinaryMismatch(tool, expected_sha, actual_sha) when a tool binary's
            SHA-256 differs from image_spec.tool_hashes.
    """
    started_at = time.monotonic()
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
    return {"build_result": build, "probe_result": result,
            "counters": schema.CounterBlock(
                stage="stage_3", started=1,
                completed=int(build.status != "internal_error"),
                failed=int(build.status == "internal_error"),
                seconds=time.monotonic() - started_at)}


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

#: Clang's spelling of an internal-linkage qualifier. Every CIRCT pass and every
#: conversion pattern is declared in one, so a normalisation that cut at this
#: opening parenthesis threw the whole name away (W-09 finding 1).
_ANONYMOUS = "(anonymous namespace)::"

_FIRING = ("crash", "assertion", "fatal_error")


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def oracle_primary(build: BuildResult, image_spec: ImageSpec, artefact_dir: str,
                   *, circt_roots: tuple = CIRCT_ROOTS,
                   symbolizer: str = "llvm-symbolizer") -> dict:
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
        {"verdict": OracleVerdict, "counters": CounterBlock}, the verdict with
        fired False and oracle_class None when the oracle did not fire; the
        counters count one probe at stage_4, as 3.11 requires of every node.
    Worker:
        {"circt": 1} - it runs llvm-symbolizer against the image's own binary.
    Raises:
        nothing. An unsymbolisable frame is recorded unresolved, not raised.
    """
    started_at = time.monotonic()
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

    verdict = OracleVerdict(
        probe_id=build.probe_id, fired=fired, oracle_class=oracle_class,
        assertion_text=assertion_text, assertion_site=assertion_site,
        fatal_message=fatal_message, frames=frames,
        prologue_dropped=len(frames) - len(stripped),
        frames_resolved=sum(1 for f in frames if f.function),
        frames_with_location=sum(1 for f in frames
                                 if f.line > 0 and f.in_circt_object),
        fingerprint_frame=_fingerprint_frame(stripped),
        out_of_scope_root=bool(fired) and not root_in_scope(stripped),
        repro_command=repro, flag_string=image_spec.flag_string,
        tool_version_output=_tool_version(build.binary_path))
    return {"verdict": verdict,
            "counters": schema.CounterBlock(
                stage="stage_4", started=1, completed=1, failed=0,
                seconds=time.monotonic() - started_at)}


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


def _address_groups(frames: list) -> list:
    """Consecutive frames sharing one address: LLVM's inlined chain, as one group.

    LLVM prints one `#n` line per **inlined** frame and gives them all the same
    runtime address, innermost first, the last being the function that actually
    owns the address. Reading only the first line of such a run is what W-09
    measured wrong (finding 2, architect's decision 2026-09-14): in three of the
    four mined assertions the first line lands in an SDK header that was inlined
    into a CIRCT function one or two lines below it.

    Returns:
        a list of groups, each a non-empty list of frames, in trace order.
    Worker:
        pure.
    Raises:
        nothing.
    """
    groups: list = []
    for frame in frames:
        if groups and groups[-1][0].address == frame.address:
            groups[-1].append(frame)
        else:
            groups.append([frame])
    return groups


def root_in_scope(stripped: list) -> bool:
    """Whether the ROOT inlined group holds a CIRCT frame (§3.6.2 step 4).

    `out_of_scope_root` is its negation. The group and not the single first
    line, because an inlined SDK header at the top of the chain is not where the
    crash roots: the CIRCT function it was inlined into is, and that function is
    a line or two below at the same address.

    Returns:
        False for an empty trace, which is what keeps a firing with no frames
        out of scope exactly as before.
    Worker:
        pure.
    Raises:
        nothing.
    """
    if not stripped:
        return False
    return any(frame.in_circt_object for frame in _address_groups(stripped)[0])


def _fingerprint_frame(stripped: list) -> Optional[str]:
    """"<function> <basename(file)>", from the first stripped CIRCT inlined group.

    The first group holding a usable CIRCT frame decides, and within it the
    **last-listed** such frame is taken, because that is the function that owns
    the address: the lines above it were inlined into it and a compiler's
    inlining decisions are not a property of the bug. A usable frame is in a
    CIRCT object, carries a resolved line and has a non-degenerate name, so the
    name in a fingerprint is always a function a reader can look up.

    No line number: a one-line edit inside the same function must not split one
    bug into two across runs (§3.7.1).
    """
    for group in _address_groups(stripped):
        usable = [frame for frame in group
                  if frame.in_circt_object and frame.line > 0
                  and _normalise_function(frame.function) not in _DEGENERATE]
        if usable:
            frame = usable[-1]
            return (f"{_normalise_function(frame.function)} "
                    f"{os.path.basename(frame.file)}")
    return None


def _normalise_function(name: str) -> str:
    """§3.7.1's steps: drop `(anonymous namespace)::`, cut the parameter list,
    drop ` const`, collapse space.

    The cut is at the first `(` at bracket depth zero, so a `(` inside a
    template argument is kept. `--functions=short` would do the cut for us and
    is not used: measured on the assertions-on build it returns `??` under
    `-gline-tables-only`, a short name needing debug information the flag does
    not emit.

    **Every `(anonymous namespace)::` segment goes first** (W-09 finding 1,
    architect's decision 2026-09-14). Clang spells an internal-linkage qualifier
    with a literal parenthesis, so the depth-zero cut landed at index 0 and
    `(anonymous namespace)::VariableOpConversion::matchAndRewrite(...)`
    normalised to the empty string: the frame was then degenerate, skipped by
    the fingerprint rule and blank in the evidence tuple. Since every CIRCT pass
    and every conversion pattern is declared in an anonymous namespace, the two
    real `fatal_error` fingerprints in the recorded set both collapsed to `main`.
    Stripping the segment keeps the qualified name the reader can look up.
    """
    name = name.replace(_ANONYMOUS, "")
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


# --- 3.6.3 B4's three harness helpers ---------------------------------------

#: `03-LLD.md` §9.4's differential constants. None is a campaign parameter: each
#: sizes a comparison rather than a budget, and each is equal for both arms by
#: construction because the apparatus cannot tell the arms apart.
X_POLICY = "x-assign=unique,x-initial=unique"
ARC_JIT_ENTRY = "bugloop_main"
VERILATOR_TOP = "bugloop_tb"
STIMULUS_ID = "lfsr32-v1"
RESET_PROTOCOL = "hold-8-then-release"
RESET_CYCLES = 8
SAMPLE_POINT = "pre-posedge"
DIFFERENTIAL_CYCLES = 64
PORT_LIST_TIMEOUT_SECONDS = 60

_CLOCK_NAMES = ("clk", "clock", "clk_i", "i_clk")
_RESET_NAMES = ("rst", "reset", "rst_n", "resetn", "areset", "rst_i", "i_rst")

#: An active-low reset asserts at 0; every other reset port asserts at 1.
_ACTIVE_LOW_RESETS = ("rst_n", "resetn")

#: The feedback word of the 32-bit maximal-length Galois LFSR §3.6.3 names but
#: does not choose a polynomial for. Taps 32, 30, 26 and 25, which is the
#: textbook maximal-length quadruple; fixed HERE so that one definition reaches
#: both generators and a second definition would be a second `stimulus_id`.
_LFSR_TAPS = 0xA3000000
_GOLDEN_RATIO = 0x9E3779B1

_PORT_ENTRY = re.compile(r"^(?P<direction>input|output|inout)\s+(?P<name>\S+)\s*:\s*"
                         r"(?P<type>.+)$")
_IN_WIDTH = re.compile(r"^i(?P<bits>\d+)$")
_IMMUTABLE = re.compile(r"^!seq\.immutable<i(?P<bits>\d+)>$")
_HW_MODULE = re.compile(r'"hw\.module"\(\) <\{(?P<attrs>.*)\}> \(\{')


class HarnessError(Exception):
    """A design the differential oracle cannot drive (FR-08.8).

    Every one of these is `harness_failure` with its reason carried into
    `DifferentialVerdict.reason`, and never `diverge`.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason, self.detail = reason, detail


@dataclass(kw_only=True)
class Port:
    """One port of the design under test, as the HW dialect declares it."""
    index: int
    name: str
    direction: str                          # "input", "output" or "inout"
    width: int                              # bits; 1 for i1 and for !seq.clock
    mlir_type: str                          # "i8", "!seq.clock", verbatim
    is_clock: bool
    is_reset: bool


def extract_port_list(lifted_hw_path: str,
                      timeout_seconds: int = PORT_LIST_TIMEOUT_SECONDS,
                      *, bin_dir: str = CIRCT_BIN_DIR) -> list:
    """Read the design under test's port signature out of its lifted HW IR.

    Runs ONE command on the lifted HW-dialect file the probe's own tool produced:

        <bin_dir>/circt-opt <lifted_hw_path> -o - --mlir-print-op-generic

    and reads the `module_type` attribute of the one `hw.module` that carries no
    `sym_visibility = "private"`. The GENERIC form is used and the pretty form
    is not, because the generic form spells every port as
    `!hw.modty<input <name> : <type>, output <name> : <type>, ...>`, with the
    direction as a word and the order as written, where the pretty form spells
    the same thing as `in %name : type` / `out name : type` and drops the `%` on
    outputs. Verified 2026-09-14 against the measured build.

    Ports come back in signature order, inputs and outputs interleaved exactly
    as the signature declares them, because that order is what the port_list
    digest is taken over and what both harnesses index.

    Returns:
        list[Port], one per declared port, in signature order.
    Worker:
        {"circt": 1} - it runs the image's own circt-opt. Called inside B4, so
        it takes no slot of its own.
    Raises:
        HarnessError("no_top"), ("bad_port_type"), ("no_clock"),
        ("circt_opt_failed"), each of which is `harness_failure`.
    """
    return _ports(_top_module(_generic(lifted_hw_path, timeout_seconds, bin_dir))[1])


def top_module_name(lifted_hw_path: str,
                    timeout_seconds: int = PORT_LIST_TIMEOUT_SECONDS,
                    *, bin_dir: str = CIRCT_BIN_DIR) -> str:
    """The symbol name of the one public `hw.module`, which both harnesses name.

    §3.6.3 gives the generators no way to learn it and §4.6 passes arcilator ONE
    file, so the instantiate has to name a symbol the generator was told about
    (erratum candidate). This is that one line, over the same generic form
    `extract_port_list` reads.

    Returns:
        the symbol name.
    Worker:
        {"circt": 1}; called beside extract_port_list, on the same file.
    Raises:
        HarnessError, exactly as extract_port_list does.
    """
    return _top_module(_generic(lifted_hw_path, timeout_seconds, bin_dir))[0]


def stimulus_seed(probe_id: str) -> int:
    """§3.6.3's seed: reproducible from the probe id alone, never from `random`."""
    digest = hashlib.sha256(f"{probe_id}|{STIMULUS_ID}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def lfsr_value(seed: int, port_index: int, cycle: int, width: int) -> int:
    """The low *width* bits of the shared stimulus for one (cycle, port) pair.

    One Galois step from `seed ^ (port_index * 0x9E3779B1) ^ cycle`, as a plain
    Python integer. A zero state is forced to one, which a Galois LFSR requires:
    zero is its absorbing state and would drive a constant.
    """
    state = (seed ^ (port_index * _GOLDEN_RATIO) ^ cycle) & 0xFFFFFFFF
    state = state or 1
    lsb = state & 1
    state >>= 1
    if lsb:
        state ^= _LFSR_TAPS
    return state & ((1 << width) - 1)


def gen_arc_harness(port_list: list, seed: int, *, top: str, design: str) -> str:
    """Build the arcilator harness MLIR that drives one design from the stimulus.

    Emits the design and one `func.func @bugloop_main` around its `arc.sim.*`
    operations: `arc.sim.instantiate`, `arc.sim.set_input` per driven input per
    cycle by the LFSR rule, `arc.sim.step` per edge, `arc.sim.get_port` per
    output at the sample point and `arc.sim.emit` per sampled value. The entry
    name is `ARC_JIT_ENTRY` and not a parameter, because §4.6 passes
    `--jit-entry=bugloop_main` and a name per probe would be a second knob.

    *top* and *design* are keywords §3.6.3's signature does not have and §4.6
    forces: arcilator is passed ONE file, so the harness must carry the design,
    and `arc.sim.instantiate` must name its symbol (erratum candidate).

    The loop is fully unrolled because each cycle drives different values and
    emits a different label, neither of which an `scf.for` can carry.

    **The acceptance shape is arcilator's, not this document's.** Measured
    2026-09-14 on the assertions-on build, `arc.sim.emit "BUGLOOP 0 o", %v : i8`
    prints `BUGLOOP 0 o = 07`: one sampled value per line, the value zero-padded
    to ceil(width / 4) hexadecimal digits. §3.6.3 asks for every port of a cycle
    on ONE line and for `<port>=<value>` with no spaces, and `arc.sim.emit` is
    arcilator's only output operation and cannot produce either. The padding
    rule §3.6.3 fixes is exactly what the tool already does. `gen_verilator_tb`
    emits the same measured shape, so the differ still compares two identical
    line sequences positionally (erratum candidate).

    Returns:
        the harness as MLIR text, one trailing newline, UTF-8.
    Worker:
        pure; it builds a string, runs no process and reads no file.
    Raises:
        HarnessError("empty_port_list") for a port list with no driven input or
            no sampled output, which has nothing to compare.
    """
    driven, sampled, clocks, resets = _roles(port_list)
    body = ["module {", design.rstrip("\n"),
            f"  func.func @{ARC_JIT_ENTRY}() {{",
            "    %bl_lo = arith.constant 0 : i1",
            "    %bl_hi = arith.constant 1 : i1",
            "    %bl_ck0 = seq.to_clock %bl_lo",
            "    %bl_ck1 = seq.to_clock %bl_hi",
            f"    arc.sim.instantiate @{top} as %model {{"]
    instance = f"!arc.sim.instance<@{top}>"
    for cycle in range(DIFFERENTIAL_CYCLES):
        for port in clocks:
            body.append(f'      arc.sim.set_input %model, "{port.name}" = %bl_ck0 '
                        f": {port.mlir_type}, {instance}")
        for port in resets:
            level = "%bl_hi" if _reset_asserted(port, cycle) else "%bl_lo"
            body.append(f'      arc.sim.set_input %model, "{port.name}" = {level} '
                        f": {port.mlir_type}, {instance}")
        for port in driven:
            value = lfsr_value(seed, port.index, cycle, port.width)
            name = f"%bl_c{cycle}_{port.index}"
            body.append(f"      {name} = arith.constant {value} : {port.mlir_type}")
            body.append(f'      arc.sim.set_input %model, "{port.name}" = {name} '
                        f": {port.mlir_type}, {instance}")
        body.append(f"      arc.sim.step %model : {instance}")
        if cycle >= RESET_CYCLES:
            for port in sampled:
                name = f"%bl_o{cycle}_{port.index}"
                body.append(f'      {name} = arc.sim.get_port %model, "{port.name}" '
                            f": {port.mlir_type}, {instance}")
                body.append(f'      arc.sim.emit "BUGLOOP {cycle} {port.name}", '
                            f"{name} : {port.mlir_type}")
        for port in clocks:
            body.append(f'      arc.sim.set_input %model, "{port.name}" = %bl_ck1 '
                        f": {port.mlir_type}, {instance}")
        body.append(f"      arc.sim.step %model : {instance}")
    body += ["    }", "    return", "  }", "}"]
    return "\n".join(body) + "\n"


def gen_verilator_tb(port_list: list, seed: int, *, top: str) -> str:
    """Build the SystemVerilog testbench that drives the same design identically.

    Emits `module bugloop_tb`, which is the literal §4.10's `--top-module`
    names: one `reg` per input, one `wire` per output, an instance of the design
    bound by port NAME and never by position, the same reset protocol, the same
    LFSR values in the same order, and one `$display` per sampled value in the
    measured acceptance shape `gen_arc_harness` documents. `%h` pads to the
    declared width, which is `ceil(width / 4)` hexadecimal digits, so the two
    sides agree digit for digit without either being told the width twice.

    *top* is a keyword §3.6.3's signature does not have: a testbench must name
    the module it instantiates (erratum candidate).

    Returns:
        the testbench as SystemVerilog text, one trailing newline, UTF-8.
    Worker:
        pure; as above.
    Raises:
        HarnessError("empty_port_list"), exactly as gen_arc_harness does and for
        the same reason, so a port list that fails one fails both.
    """
    driven, sampled, clocks, resets = _roles(port_list)
    lines = ["`timescale 1ns/1ps", f"module {VERILATOR_TOP};"]
    for port in port_list:
        kind = "wire" if port.direction == "output" else "reg"
        initial = "" if port.direction == "output" else " = 0"
        lines.append(f"  {kind} {_range(port.width)}{port.name}{initial};")
    binding = ", ".join(f".{port.name}({port.name})" for port in port_list)
    lines.append(f"  {top} dut ({binding});")
    lines.append("  initial begin")
    for cycle in range(DIFFERENTIAL_CYCLES):
        for port in clocks:
            lines.append(f"    {port.name} = 1'b0;")
        for port in resets:
            lines.append(f"    {port.name} = 1'b{int(_reset_asserted(port, cycle))};")
        for port in driven:
            value = lfsr_value(seed, port.index, cycle, port.width)
            lines.append(f"    {port.name} = {port.width}'h{value:x};")
        lines.append("    #1;")
        if cycle >= RESET_CYCLES:
            for port in sampled:
                lines.append(f'    $display("BUGLOOP {cycle} {port.name} = %h", '
                             f"{port.name});")
        for port in clocks:
            lines.append(f"    {port.name} = 1'b1;")
        lines.append("    #1;")
    lines += ["    $finish;", "  end", "endmodule"]
    return "\n".join(lines) + "\n"


def _roles(port_list: list) -> tuple:
    """(driven inputs, sampled outputs, clocks, resets), and the one refusal.

    Clock and reset ports are excluded from the stimulus: the harness drives the
    clock and the reset protocol drives the resets (§3.6.3). An `inout` port is
    neither driven nor sampled, there being no two-state protocol for one.
    """
    clocks = [p for p in port_list if p.is_clock]
    resets = [p for p in port_list if p.is_reset and not p.is_clock]
    driven = [p for p in port_list
              if p.direction == "input" and not p.is_clock and not p.is_reset]
    sampled = [p for p in port_list if p.direction == "output"]
    if not driven or not sampled:
        raise HarnessError("empty_port_list",
                           f"{len(driven)} driven inputs, {len(sampled)} outputs")
    return driven, sampled, clocks, resets


def _reset_asserted(port: Port, cycle: int) -> bool:
    """`hold-8-then-release`: the LEVEL to drive, active low taken into account."""
    active_low = port.name in _ACTIVE_LOW_RESETS
    return (cycle < RESET_CYCLES) != active_low


def _range(width: int) -> str:
    return "" if width == 1 else f"[{width - 1}:0] "


def _generic(path: str, timeout_seconds: int, bin_dir: str) -> str:
    """The one `circt-opt --mlir-print-op-generic` run, bounded by subprocess."""
    try:
        done = subprocess.run([os.path.join(bin_dir, "circt-opt"), path, "-o", "-",
                               "--mlir-print-op-generic"],
                              capture_output=True, text=True, timeout=timeout_seconds)
    except (OSError, subprocess.SubprocessError) as error:
        raise HarnessError("circt_opt_failed", str(error)) from error
    if done.returncode != 0:
        raise HarnessError("circt_opt_failed", done.stderr.strip()[:400])
    return done.stdout


def _top_module(generic: str) -> tuple:
    """(symbol name, modty body) of the one hw.module with public visibility."""
    headers = list(_HW_MODULE.finditer(generic))
    public = []
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(generic)
        if 'sym_visibility = "private"' in generic[header.end():end]:
            continue
        attrs = header.group("attrs")
        name = re.search(r'sym_name = "(?P<name>[^"]*)"', attrs)
        marker = attrs.find("!hw.modty<")
        if not name or marker < 0:
            continue
        public.append((name.group("name"),
                       _balanced(attrs, marker + len("!hw.modty<") - 1)))
    if len(public) != 1:
        raise HarnessError("no_top", f"{len(public)} public hw.module operations")
    return public[0]


def _balanced(text: str, open_index: int) -> str:
    """The contents of the `<...>` opening at *open_index*, nesting respected."""
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "<":
            depth += 1
        elif text[index] == ">":
            depth -= 1
            if depth == 0:
                return text[open_index + 1:index]
    raise HarnessError("no_top", "unbalanced !hw.modty")


def _ports(modty: str) -> list:
    """Parse one `!hw.modty<...>` body into `Port`s, in signature order."""
    ports = []
    for index, entry in enumerate(_split_top_level(modty)):
        match = _PORT_ENTRY.match(entry.strip())
        if not match:
            raise HarnessError("bad_port_type", entry.strip()[:120])
        mlir_type = match.group("type").strip()
        name = match.group("name")
        ports.append(Port(index=index, name=name, direction=match.group("direction"),
                          width=_width(mlir_type), mlir_type=mlir_type,
                          is_clock=mlir_type == "!seq.clock" or name in _CLOCK_NAMES,
                          is_reset=name in _RESET_NAMES and _width(mlir_type) == 1))
    if not any(port.is_clock for port in ports):
        raise HarnessError("no_clock", "a combinational design has no cycle to sample")
    return ports


def _split_top_level(modty: str) -> list:
    """Split a modty body on commas that are not inside a bracket of any kind."""
    entries, depth, start = [], 0, 0
    for index, char in enumerate(modty):
        if char in "<([":
            depth += 1
        elif char in ">)]":
            depth -= 1
        elif char == "," and depth == 0:
            entries.append(modty[start:index])
            start = index + 1
    tail = modty[start:]
    if tail.strip():
        entries.append(tail)
    return entries


def _width(mlir_type: str) -> int:
    """`iN`, `!seq.clock` and `!seq.immutable<iN>`; everything else is refused.

    Every aggregate (`!hw.array`, `!hw.struct`, `!hw.inout`) and every
    parameterised width lands here, which is `bad_port_type` and
    `harness_failure` and never `diverge`.
    """
    if mlir_type == "!seq.clock":
        return 1
    for pattern in (_IN_WIDTH, _IMMUTABLE):
        found = pattern.match(mlir_type)
        if found:
            bits = int(found.group("bits"))
            if bits < 1:
                raise HarnessError("bad_port_type", mlir_type)
            return bits
    raise HarnessError("bad_port_type", mlir_type)


# --- 3.6.3 B4, the differential ---------------------------------------------

#: FR-08.1's rule, as two closed sets and nothing else. A `firtool` probe is
#: applicable when its argv requests one of these three output modes.
_FIRTOOL_HW_MODES = ("ir-hw", "verilog", "split-verilog")

#: A `circt-opt` probe is applicable when its pipeline **ends** in one of these,
#: which are the `--lower-*-to-hw` conversions the measured source build
#: registers (`circt-opt --help`, 2026-09-14, assertions-on build). The Moore
#: conversion is deliberately absent: it is spelled `--convert-moore-to-core`
#: and FR-08.1's acceptance criterion puts a `MooreToCore` probe out of scope.
_HW_TERMINAL_PASSES = ("lower-firrtl-to-hw", "lower-hwarith-to-hw",
                       "lower-calyx-to-hw", "lower-dc-to-hw",
                       "lower-esi-to-hw", "lower-handshake-to-hw",
                       "lower-pipeline-to-hw")

#: `circt-opt` options that are not passes, so that "the last pass" is not read
#: off a trailing `-o` or a probe-only option. Both dash spellings reach here
#: already stripped, which is W-09 finding 3's lesson applied to this rule.
_NOT_A_PASS = ("o", "verify-diagnostics", "split-input-file", "split-file",
               "mlir-print-op-generic", "allow-unregistered-dialect")

#: FR-08.11's recorded deviation. `circt/arc-tests` is neither on this machine
#: nor reusable as it stands, and the obstacle is named rather than implied.
DIFFERENTIAL_DRIVER = (
    "deviation: circt/arc-tests' lockstep driver runs two FIXED designs "
    "(Rocket Chip, BOOM) from checked-in harnesses, and neither the repository "
    "nor a clone is on the implementation machine; the harnesses here are "
    "generated per probe from the extracted port list (FR-08.11)")

#: The acceptance line both harnesses print, in the shape `gen_arc_harness`
#: documents: one sampled value per line, so a line carries exactly one port.
_BUGLOOP = re.compile(r"^BUGLOOP (?P<cycle>\d+) (?P<signal>\S+) = "
                      r"(?P<value>[0-9a-fA-F]+)$")


def differential_applicable(spec) -> tuple:
    """FR-08.1's applicability rule, decided from the argv and nothing else.

    Pure, and called **before** either simulator runs, so that a design a
    simulator later rejects is `harness_failure` and never `not_applicable`
    (FR-08.1). Admitted: a `firtool` probe requesting `--ir-hw`, `--verilog` or
    `--split-verilog`, and a `circt-opt` probe whose pipeline ends in one of
    `_HW_TERMINAL_PASSES`. Nothing else, which is what puts every
    `circt-verilog`, `circt-translate` and `ImportVerilog`/`MooreToCore` probe
    out of scope.

    Both dash spellings are accepted, because CIRCT's own tests write single-
    dash options and LLVM's command-line parser takes either (W-09 finding 3).
    A `--pass-pipeline=` probe is **not** admitted: no corpus RUN line combines
    that spelling with an HW-terminal lowering (measured: 50 pipeline lines in
    `raw/m1-per-runline.csv`, none of them HW-terminal), so reading the last
    pass out of a nested pipeline string would be code for no case.

    Returns:
        (applicable, reason). *reason* is "" when applicable and otherwise one
        of `entry_tool_not_hw_capable`, `firtool_output_mode_not_hw`,
        `pipeline_not_hw_terminal`, which is what the verdict carries.
    Worker:
        pure; it reads the spec and runs nothing.
    Raises:
        nothing.
    """
    if spec.tool == "firtool":
        modes = [_option_name(token) for token in spec.argv]
        if any(mode in _FIRTOOL_HW_MODES for mode in modes):
            return True, ""
        return False, "firtool_output_mode_not_hw"
    if spec.tool == "circt-opt":
        if _last_pass(spec.argv) in _HW_TERMINAL_PASSES:
            return True, ""
        return False, "pipeline_not_hw_terminal"
    return False, "entry_tool_not_hw_capable"


def _option_name(token: str) -> str:
    """An argv token's option name: both dash spellings, any `=` value dropped."""
    if not token.startswith("-"):
        return ""
    return token.lstrip("-").split("=", 1)[0]


def _last_pass(argv: list) -> str:
    """The last option of *argv* that names a pass, by `_NOT_A_PASS` alone."""
    for token in reversed(list(argv)):
        name = _option_name(token)
        if name and name not in _NOT_A_PASS:
            return name
    return ""


def compare_traces(arcilator_out: str, verilator_out: str) -> dict:
    """Compare the two `BUGLOOP` line sequences positionally (§3.6.3).

    The VCD files of §4.6 and §4.10 are evidence and are **not** read: a text
    comparison needs no VCD reader and cannot disagree with one. Any line either
    harness prints that is not a `BUGLOOP` line is ignored here and kept in the
    artefact.

    The two sequences are generated from ONE port list and ONE cycle count, so
    unequal lengths or a signal mismatch at one index mean a SIMULATOR stopped
    early or ran a different design: that is `harness_failure` under FR-08.8 and
    never a divergence, and the caller is told which side was short.

    **The X bucket (FR-08.9), made computable.** §3.6.3 declares a divergence
    "confined to cycles before the first write of the divergent output signal"
    to be `diverge_x_policy`, and gives no test a differ can run. The test used
    here is the observable form of that sentence: every signal that diverges at
    all does so over a contiguous PREFIX of the cycles it is sampled at, and
    agrees from some cycle onward. A register the design never writes stays
    undefined for the whole run under `--x-initial unique` and diverges to the
    last cycle, so it is a plain `diverge`; one written at cycle k differs only
    while it is uninitialised, which is exactly the bucket FR-08.9 excludes.

    Returns:
        {"verdict": "agree" | "diverge" | "diverge_x_policy" |
                    "harness_failure",
         "reason": str, "index": int | None, "cycle": int | None,
         "signal": str | None, "arcilator_value": str | None,
         "verilator_value": str | None, "lines": int}
        `index` is the position of the first differing line in the two
        sequences, from 0; `cycle` and `signal` are read off that line.
    Worker:
        pure.
    Raises:
        nothing.
    """
    left, right = _bugloop_lines(arcilator_out), _bugloop_lines(verilator_out)
    empty = {"verdict": "harness_failure", "index": None, "cycle": None,
             "signal": None, "arcilator_value": None, "verilator_value": None,
             "lines": min(len(left), len(right))}
    if not left or not right:
        side = "arcilator" if not left else "verilator"
        if not left and not right:
            side = "arcilator and verilator"
        return {**empty, "reason": f"{side} printed no BUGLOOP line"}
    if len(left) != len(right):
        side = "arcilator" if len(left) < len(right) else "verilator"
        return {**empty, "reason": f"{side} stopped after {min(len(left), len(right))} "
                                   f"of {max(len(left), len(right))} lines"}
    if [(c, s) for c, s, _ in left] != [(c, s) for c, s, _ in right]:
        return {**empty, "reason": "the two arms sampled different signals"}

    differing = [index for index, (one, other) in enumerate(zip(left, right))
                 if one[2] != other[2]]
    found = {"reason": "", "lines": len(left)}
    if not differing:
        return {**found, "verdict": "agree", "index": None, "cycle": None,
                "signal": None, "arcilator_value": None, "verilator_value": None}
    first = differing[0]
    return {**found,
            "verdict": "diverge_x_policy" if _x_confined(left, right) else "diverge",
            "index": first, "cycle": left[first][0], "signal": left[first][1],
            "arcilator_value": left[first][2], "verilator_value": right[first][2]}


def _bugloop_lines(text: str) -> list:
    """Every acceptance line of one stream, as (cycle, signal, value) in order."""
    found = []
    for line in text.splitlines():
        match = _BUGLOOP.match(line.strip())
        if match:
            found.append((int(match.group("cycle")), match.group("signal"),
                          match.group("value").lower()))
    return found


def _x_confined(left: list, right: list) -> bool:
    """Whether every divergent signal diverges only over its opening cycles."""
    agreement: dict = {}
    for (_, signal, one), (_, _, other) in zip(left, right):
        agreement.setdefault(signal, []).append(one == other)
    divergent = [values for values in agreement.values() if not all(values)]
    return bool(divergent) and all(
        any(values) and all(values[values.index(True):]) for values in divergent)


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def oracle_differential(spec, build: BuildResult, image_spec: ImageSpec,
                        artefact_dir: str, *, limits: dict,
                        bin_dir: str = CIRCT_BIN_DIR,
                        verilator: str = "verilator") -> dict:
    """Run one design through arcilator and Verilator, and count the run (3.11).

    A four-line wrapper around `_oracle_differential`, which is 3.6.3's body
    unchanged. The split exists because 3.11 requires every node of 3.2 to
    return `{"counters": CounterBlock}` and this body has five return
    statements; wrapping it is one place to add the block, and editing five is
    five places to lose one (W-17, errata row 22).

    Returns:
        {"verdict": DifferentialVerdict, "counters": CounterBlock}, always,
        including the `not_applicable` verdict with its reason. `completed` is
        1 where the two arms were compared and 0 where the verdict is
        `harness_failure`.
    Worker:
        {"circt": 1} - it runs arcilator, firtool and Verilator.
    Raises:
        whatever the body raises, which is nothing it does not record.
    """
    started_at = time.monotonic()
    verdict = _oracle_differential(spec, build, image_spec, artefact_dir,
                                   limits=limits, bin_dir=bin_dir,
                                   verilator=verilator)
    failed = int(verdict.verdict == "harness_failure")
    return {"verdict": verdict,
            "counters": schema.CounterBlock(
                stage="stage_4", started=1, completed=1 - failed, failed=failed,
                seconds=time.monotonic() - started_at)}


def _oracle_differential(spec, build: BuildResult, image_spec: ImageSpec,
                         artefact_dir: str, *, limits: dict,
                         bin_dir: str = CIRCT_BIN_DIR,
                         verilator: str = "verilator") -> DifferentialVerdict:
    """Run one design through arcilator and Verilator from one stimulus.

    Five steps and nothing else: decide applicability from the argv alone
    (FR-08.1); lift the design to HW-dialect IR with the probe's own entry tool
    and extract its port list; generate both harnesses from that one list and
    one seed; run §4.6's arcilator invocation and §4.10's Verilator build and
    binary under the probe's own limits; and compare the two `BUGLOOP`
    sequences line by line.

    **This node is not on `probe_execute`'s path.** The driver calls it for the
    seeds FR-08.1 admits and for no others (§3.6.3), and FR-08.10 keeps what it
    produces out of the reducer, out of repair and out of the gate: it is
    report-only, and the report-only flag lives on the `CandidateRecord` the
    head writes, `DifferentialVerdict` having no such column.

    *limits*, *bin_dir* and *verilator* are keywords §3.6.3's signature does not
    have (erratum candidates): the two simulator runs are bounded by the probe
    limits rather than by B4's 1800 s node timeout, and every fixture and
    tier-1 measurement runs a build outside the image.

    Returns:
        DifferentialVerdict, always, including not_applicable with its reason.
    Worker:
        {"circt": 1} - both simulators live on the CIRCT image (ADR-D-09).
    Raises:
        nothing. A harness that will not build is harness_failure, never
        diverge.
    """
    applicable, reason = differential_applicable(spec)
    if not applicable:
        return _differential_verdict(spec, image_spec, "not_applicable", reason)

    directory = Path(artefact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    # Every refusal below carries '' for port_list_sha, which is what §6.2's
    # DDL comment asks of a harness_failure.
    try:
        lifted = _lift_to_hw(spec, directory, bin_dir, limits)
        ports = extract_port_list(str(lifted), bin_dir=bin_dir)
        top = top_module_name(str(lifted), bin_dir=bin_dir)
        seed = stimulus_seed(spec.probe_id)
        port_list = _canonical([dataclasses.asdict(port) for port in ports])
        (directory / "port_list.json").write_text(port_list, encoding="utf-8")
        (directory / "harness.mlir").write_text(
            gen_arc_harness(ports, seed, top=top,
                            design=_module_body(lifted.read_text(encoding="utf-8"))),
            encoding="utf-8")
        (directory / "tb.sv").write_text(gen_verilator_tb(ports, seed, top=top),
                                         encoding="utf-8")
        _emit_verilog(lifted, directory / "dut.sv", bin_dir, limits)
        arc = _arcilator_arm(directory, bin_dir, limits)
        ver = _verilator_arm(directory, verilator, limits)
    except HarnessError as error:
        return _differential_verdict(spec, image_spec, "harness_failure",
                                     f"{error.reason}: {error.detail}"
                                     if error.detail else error.reason)

    port_list_sha = hashlib.sha256(port_list.encode("utf-8")).hexdigest()
    (directory / "arcilator.out.txt").write_text(arc["stdout"], encoding="utf-8")
    (directory / "verilator.out.txt").write_text(ver["stdout"], encoding="utf-8")
    (directory / "differential_evidence.json").write_text(
        _canonical({"arcilator": _side_evidence(arc), "verilator": _side_evidence(ver),
                    "driver_source": DIFFERENTIAL_DRIVER, "x_policy": X_POLICY,
                    "stimulus_id": STIMULUS_ID, "port_list_sha": port_list_sha}),
        encoding="utf-8")

    # `side` and not `arm`: the two SIMULATORS are not the campaign's two arms,
    # and §14.5's walk reads the name and not the meaning, so the collision made
    # `T-U-layout-02` fire on a module that branches on no arm at all (errata
    # row 19, W-17 fix 7).
    for side, name in ((arc, "arcilator"), (ver, "verilator")):
        if side["exit_status"] != 0:
            return _differential_verdict(
                spec, image_spec, "harness_failure",
                f"{name} {side.get('stage', 'run')} exited {side['exit_status']}, "
                f"signal {side['signal']}, limit {side['limit_hit']}")

    outcome = compare_traces(arc["stdout"], ver["stdout"])
    if outcome["verdict"] == "harness_failure":
        return _differential_verdict(spec, image_spec, "harness_failure",
                                     outcome["reason"])
    return _differential_verdict(
        spec, image_spec, outcome["verdict"], outcome["reason"],
        port_list_sha=port_list_sha,
        arcilator_trace_path=str(directory / "arcilator.vcd"),
        verilator_trace_path=str(directory / "verilator.vcd"),
        first_divergent_cycle=outcome["cycle"],
        first_divergent_signal=outcome["signal"],
        arcilator_value=outcome["arcilator_value"],
        verilator_value=outcome["verilator_value"])


def _differential_verdict(spec, image_spec: ImageSpec, verdict: str,
                          reason: str, **over) -> DifferentialVerdict:
    """One `DifferentialVerdict`, with the five stimulus fields always filled.

    FR-08.3 asks for one shared stimulus declaration per comparison, so the
    constants are written on every verdict including `not_applicable`, where
    they say what the comparison would have been.
    """
    fields = dict(
        probe_id=spec.probe_id, verdict=verdict, reason=reason,
        verilator_version=image_spec.verilator_version, x_policy=X_POLICY,
        stimulus_id=STIMULUS_ID, port_list_sha="", cycles=DIFFERENTIAL_CYCLES,
        first_divergent_signal=None, first_divergent_cycle=None,
        arcilator_value=None, verilator_value=None, arcilator_trace_path=None,
        verilator_trace_path=None, driver_source=DIFFERENTIAL_DRIVER)
    fields.update(over)
    return DifferentialVerdict(**fields)


def _lift_to_hw(spec, directory: Path, bin_dir: str, limits: dict) -> Path:
    """`<probe dir>/lifted.mlir`: the design in the HW dialect, from the probe's
    own entry tool in the mode FR-08.1 admitted.

    A `firtool` probe is re-run with `--ir-hw` whatever of the three modes its
    own argv asked for, because arcilator needs the IR and not the Verilog; a
    `circt-opt` probe is re-run with its own pipeline, whose last pass is an
    HW-terminal lowering by construction.
    """
    lifted = directory / "lifted.mlir"
    if spec.tool == "firtool":
        argv = [spec.input_path, "--ir-hw", "-o", str(lifted)]
    else:
        argv = _without_output_option(spec.argv) + ["-o", str(lifted)]
    done = _run_bounded(os.path.join(bin_dir, spec.tool), argv, directory, limits)
    if done["exit_status"] != 0 or not lifted.is_file():
        raise HarnessError("lift_failed", done["stderr"].strip()[:400])
    return lifted


def _without_output_option(argv: list) -> list:
    """*argv* with `-o` and whatever follows it removed, in one pass.

    Both dash spellings and both value forms: `-o out`, `--o=out`. The probe's
    own output destination is replaced by the lift's, and dropping the option
    without its value would leave the value as a second positional argument,
    which `circt-opt` refuses ("Too many positional arguments specified").
    """
    kept, skip = [], False
    for token in argv:
        if skip:
            skip = False
            continue
        if _option_name(token) == "o":
            skip = "=" not in token
            continue
        kept.append(token)
    return kept


def _module_body(text: str) -> str:
    """The operations inside a single outer `module { ... }`, if that is all
    the text is; otherwise the text unchanged.

    `circt-opt` and `firtool` both print the implicit top-level module
    explicitly, and `gen_arc_harness` wraps what it is handed in a module of its
    own, so a design that arrives already wrapped would be nested one level
    deep and `arc.sim.instantiate` would not resolve its symbol.
    """
    stripped = text.strip()
    opening = "module {"
    if not stripped.startswith(opening):
        return text
    depth = 0
    for index in range(len(opening) - 1, len(stripped)):
        if stripped[index] == "{":
            depth += 1
        elif stripped[index] == "}":
            depth -= 1
            if depth == 0:
                return (stripped[len(opening):index]
                        if index == len(stripped) - 1 else text)
    return text


def _emit_verilog(lifted: Path, target: Path, bin_dir: str, limits: dict) -> None:
    """`<probe dir>/dut.sv`, by `firtool --verilog` on the lifted HW IR (§3.6.3).

    Verified 2026-09-14 on the measured build: `firtool --verilog` reads an
    HW-dialect file and emits synthesisable SystemVerilog, so the design under
    test comes from the same file the arcilator harness carries and the two arms
    cannot drift.
    """
    done = _run_bounded(os.path.join(bin_dir, "firtool"),
                        [str(lifted), "--verilog", "-o", str(target)],
                        target.parent, limits)
    if done["exit_status"] != 0 or not target.is_file():
        raise HarnessError("verilog_export_failed", done["stderr"].strip()[:400])


def _arcilator_arm(directory: Path, bin_dir: str, limits: dict) -> dict:
    """§4.6's invocation, verbatim, on the generated harness."""
    return _run_bounded(
        os.path.join(bin_dir, "arcilator"),
        ["--run", f"--jit-entry={ARC_JIT_ENTRY}", "--observe-ports",
         f"--jit-vcd-file={directory / 'arcilator.vcd'}",
         str(directory / "harness.mlir")], directory, limits)


def _verilator_arm(directory: Path, verilator: str, limits: dict) -> dict:
    """§4.10's `--binary` build and then the binary it built.

    `--x-assign unique --x-initial unique` is FR-08.4's declared policy and is
    the reason `X_POLICY` reads as it does; `-Wno-fatal` is required rather than
    convenient, a generated design routinely tripping a style warning.
    """
    binary = _which(verilator)
    build = _run_bounded(
        binary,
        ["--binary", "-j", "0", "-Wno-fatal", "--timing",
         "--x-assign", "unique", "--x-initial", "unique",
         "--top-module", VERILATOR_TOP, "--Mdir", str(directory / "obj_dir"),
         "-o", "Vbugloop", "--trace-vcd",
         str(directory / "tb.sv"), str(directory / "dut.sv")], directory, limits)
    model = directory / "obj_dir" / "Vbugloop"
    if build["exit_status"] != 0 or not model.is_file():
        return {**build, "exit_status": build["exit_status"] or 1,
                "stage": "build"}
    return {**_run_bounded(str(model), [], directory, limits), "stage": "run",
            "build_argv": build["argv"]}


def _run_bounded(binary: str, argv: list, cwd: Path, limits: dict) -> dict:
    """One child under §4.1's `prlimit` prefix, through `circt_exec_probe`."""
    return _exec_probe(binary, list(argv), cwd=str(cwd),
                       wall_seconds=limits["probe_wall_seconds"],
                       address_space_bytes=limits["probe_address_space_bytes"],
                       cpu_seconds=limits["probe_cpu_seconds"],
                       nofile=PROBE_NOFILE,
                       output_byte_cap=limits["probe_output_byte_cap"])


def _which(name: str) -> str:
    """An absolute path for a tool named on PATH; `circt_exec_probe` needs one."""
    found = name if os.path.isabs(name) else shutil.which(name)
    if not found:
        raise HarnessError("verilator_absent", name)
    return found


def _side_evidence(side: dict) -> dict:
    """One SIMULATOR side's recorded argv, output digest and limit outcome.

    "side" and not "arm": a differential probe has two simulators and the
    campaign has two arms, and they are different things. §14.5's walk reads the
    NAME, so the collision made `T-U-layout-02` report `probe_task.py` for a
    branch on the campaign's arm that this module never makes (errata row 19).

    FR-08.4's acceptance criterion reads the **recorded** Verilator argument
    vector for the two X flags and §6.5 names no file that holds one, so this is
    that file's content (erratum candidate against §6.5).
    """
    return {"argv": side["argv"], "build_argv": side.get("build_argv"),
            "stdout_sha256": hashlib.sha256(
                side["stdout"].encode("utf-8")).hexdigest(),
            "stdout_bytes": len(side["stdout"].encode("utf-8")),
            "exit_status": side["exit_status"], "signal": side["signal"],
            # Keyed "limit" and not by the field's own name: T-U-probe-41
            # asserts that no module but circt_core.py writes that key, and this
            # is a copy of the field for the record, never a derivation of it.
            "limit": side["limit_hit"]}


# --- 3.6.4 B5, the reducer --------------------------------------------------

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
                *, bin_dir: str = CIRCT_BIN_DIR) -> dict:
    """Shrink a firing input, and count the reduction (3.11).

    A four-line wrapper around `_reduce_case`, which is 3.6.4's body unchanged,
    for the reason `oracle_differential`'s wrapper exists: the body has two
    return statements and the block belongs in one place (W-17, errata row 22).

    Returns:
        {"reduced": ReducedCase, "counters": CounterBlock}. `completed` is 1
        where the case shrank and 0 where it did not, which is what
        `ReducedCase.reduced` says.
    Worker:
        {"circt": 1} - it runs the image's own source-built circt-reduce.
    Raises:
        nothing, as the body raises nothing.
    """
    started_at = time.monotonic()
    case = _reduce_case(spec, verdict, limits, artefact_dir, bin_dir=bin_dir)
    return {"reduced": case,
            "counters": schema.CounterBlock(
                stage="stage_5", started=1, completed=int(case.reduced),
                failed=int(not case.reduced),
                seconds=time.monotonic() - started_at)}


def _reduce_case(spec, verdict: OracleVerdict, limits: dict, artefact_dir: str,
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
    return _reduce(
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
           "write_interestingness", "HarnessError", "Port", "extract_port_list",
           "top_module_name", "gen_arc_harness", "gen_verilator_tb",
           "stimulus_seed", "lfsr_value", "PROBE_NOFILE",
           "PROBE_WALL_MARGIN_SECONDS", "CPU_HARD_MARGIN_SECONDS", "X_POLICY",
           "ARC_JIT_ENTRY", "STIMULUS_ID", "RESET_PROTOCOL", "SAMPLE_POINT",
           "DIFFERENTIAL_CYCLES", "PORT_LIST_TIMEOUT_SECONDS"]
