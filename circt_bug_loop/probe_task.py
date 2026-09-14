"""The four apparatus nodes that touch a probe: execute, judge, differential, reduce."""
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
                                       allocation_evidence, circt_exec_probe,
                                       circt_reduce_run, circt_symbolize)
from circt_bug_loop.contract import schema
from circt_bug_loop.ddmin import ddmin
from circt_bug_loop.store import (BuildResult, DifferentialVerdict, Frame,
                                  ImageSpec, OracleVerdict, ReducedCase,
                                  sha256_file)

#: `03-LLD.md` §9.4's implementation constant that belongs to this module.
PROBE_NOFILE = 1024

#: §3.6's three allocation-failure literals, under the name §3.6 gives them.
_ALLOC_LITERALS = ALLOCATION_FAILURE_LITERALS

#: The three §3.10 helpers are called IN PROCESS and never dispatched.
_exec_probe = circt_exec_probe._chia_original
_symbolize = circt_symbolize._chia_original
_reduce = circt_reduce_run._chia_original

#: The diagnostic that separates FR-06.6's two `parse_error` reasons.
_ARGV_REJECTED = "does not refer to a registered pass or pass pipeline"

#: The exit status of a tool that never started.
LOADER_FAILED_STATUS = 127


class BinaryMismatch(Exception):
    """A tool binary's SHA-256 differs from `ImageSpec.tool_hashes` (FR-06.1)."""

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

# `func` is `.+?` and not `[^:]+`.


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def probe_execute(spec, image_spec: ImageSpec, limits: dict,
                  artefact_dir: str, *, bin_dir: str = CIRCT_BIN_DIR) -> dict:
    """Run one probing input through its tool, bounded, and classify it seven ways.

    Returns:
        {"build_result": BuildResult, "probe_result": ProbeResult, "counters": CounterBlock}, the counters counting one probe at stage_3, as 3.11 requires of every node; an `internal_error` status is the failed one.
    Worker:
        {"circt": 1} - it runs the image's own CIRCT binaries.
    Raises:
        BinaryMismatch(tool, expected_sha, actual_sha) when a tool binary's SHA-256 differs from image_spec.tool_hashes.
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
    # FR-06.4: a probe the stage itself killed carries a NULL signal.
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
    """Return (status, reason) for one finished probe, by §3.6's table alone."""
    if limit_hit == "wall":
        return "timeout", "wall_limit"
    if limit_hit == "cpu":
        return "timeout", "cpu_limit"
    allocation = allocation_evidence(stderr)
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
    if rc == LOADER_FAILED_STATUS:
        return "tool_unavailable", "loader_failed"
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

#: §3.7.1's crash-handler prologue.
_PROLOGUE = ("llvm::sys::PrintStackTrace", "llvm::sys::RunSignalHandlers", "SignalHandler",
             "__restore_rt", "pthread_kill", "raise", "abort", "__assert_fail",
             "llvm::report_fatal_error", "llvm::llvm_unreachable_internal")

#: What a lambda's demangled name reduces to under `_normalise_function`.
_DEGENERATE = ("", "operator")

#: Clang's spelling of an internal-linkage qualifier.
_ANONYMOUS = "(anonymous namespace)::"

_FIRING = ("crash", "assertion", "fatal_error")


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def oracle_primary(build: BuildResult, image_spec: ImageSpec, artefact_dir: str,
                   *, circt_roots: tuple = CIRCT_ROOTS,
                   symbolizer: str = "llvm-symbolizer") -> dict:
    """Decide whether the probe found a defect, and say which kind.

    Returns:
        {"verdict": OracleVerdict, "counters": CounterBlock}, the verdict with fired False and oracle_class None when the oracle did not fire; the counters count one probe at stage_4, as 3.11 requires of every node.
    Worker:
        {"circt": 1} - it runs llvm-symbolizer against the image's own binary.
    Raises:
        nothing.
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
    """Drop the crash-handler prologue and return what is left (§3.7.1)."""
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
    """(assertion_text, assertion_site) for whichever assertion pattern fired."""
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
    """Consecutive frames sharing one address: LLVM's inlined chain, as one group."""
    groups: list = []
    for frame in frames:
        if groups and groups[-1][0].address == frame.address:
            groups[-1].append(frame)
        else:
            groups.append([frame])
    return groups


def root_in_scope(stripped: list) -> bool:
    """Whether the ROOT inlined group holds a CIRCT frame (§3.6.2 step 4)."""
    if not stripped:
        return False
    return any(frame.in_circt_object for frame in _address_groups(stripped)[0])


def _fingerprint_frame(stripped: list) -> Optional[str]:
    """"<function> <basename(file)>", from the first stripped CIRCT inlined group."""
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
    """§3.7.1's steps: drop `(anonymous namespace)::`, cut the parameter list, drop ` const`, collapse space."""
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
    """The probe's own argv, the `prlimit` prefix and the tool path removed."""
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

#: `03-LLD.md` §9.4's differential constants.
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

#: The feedback word of the 32-bit maximal-length Galois LFSR of §3.6.3.
_LFSR_TAPS = 0xA3000000
_GOLDEN_RATIO = 0x9E3779B1

_PORT_ENTRY = re.compile(r"^(?P<direction>input|output|inout)\s+(?P<name>\S+)\s*:\s*"
                         r"(?P<type>.+)$")
_IN_WIDTH = re.compile(r"^i(?P<bits>\d+)$")
_IMMUTABLE = re.compile(r"^!seq\.immutable<i(?P<bits>\d+)>$")
_HW_MODULE = re.compile(r'"hw\.module"\(\) <\{(?P<attrs>.*)\}> \(\{')


class HarnessError(Exception):
    """A design the differential oracle cannot drive (FR-08.8)."""

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
    """Read the design under test's port signature out of its lifted HW IR."""
    return _ports(_top_module(_generic(lifted_hw_path, timeout_seconds, bin_dir))[1])


def top_module_name(lifted_hw_path: str,
                    timeout_seconds: int = PORT_LIST_TIMEOUT_SECONDS,
                    *, bin_dir: str = CIRCT_BIN_DIR) -> str:
    """The symbol name of the one public `hw.module`, which both harnesses name."""
    return _top_module(_generic(lifted_hw_path, timeout_seconds, bin_dir))[0]


def stimulus_seed(probe_id: str) -> int:
    """§3.6.3's seed: reproducible from the probe id alone, never from `random`."""
    digest = hashlib.sha256(f"{probe_id}|{STIMULUS_ID}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def lfsr_value(seed: int, port_index: int, cycle: int, width: int) -> int:
    """The low *width* bits of the shared stimulus for one (cycle, port) pair."""
    state = (seed ^ (port_index * _GOLDEN_RATIO) ^ cycle) & 0xFFFFFFFF
    state = state or 1
    lsb = state & 1
    state >>= 1
    if lsb:
        state ^= _LFSR_TAPS
    return state & ((1 << width) - 1)


def gen_arc_harness(port_list: list, seed: int, *, top: str, design: str) -> str:
    """Build the arcilator harness MLIR that drives one design from the stimulus."""
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
    """Build the SystemVerilog testbench that drives the same design identically."""
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
    """(driven inputs, sampled outputs, clocks, resets), and the one refusal."""
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
    """`iN`, `!seq.clock` and `!seq.immutable<iN>`; everything else is refused."""
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

#: FR-08.1's rule, as two closed sets and nothing else.
_FIRTOOL_HW_MODES = ("ir-hw", "verilog", "split-verilog")

#: A `circt-opt` probe is applicable when its pipeline **ends** in one of these.
_HW_TERMINAL_PASSES = ("lower-firrtl-to-hw", "lower-hwarith-to-hw",
                       "lower-calyx-to-hw", "lower-dc-to-hw",
                       "lower-esi-to-hw", "lower-handshake-to-hw",
                       "lower-pipeline-to-hw")

#: `circt-opt` options that are not passes.
_NOT_A_PASS = ("o", "verify-diagnostics", "split-input-file", "split-file",
               "mlir-print-op-generic", "allow-unregistered-dialect")

#: FR-08.11's recorded deviation.
DIFFERENTIAL_DRIVER = (
    "deviation: circt/arc-tests' lockstep driver runs two FIXED designs "
    "(Rocket Chip, BOOM) from checked-in harnesses, and neither the repository "
    "nor a clone is on the implementation machine; the harnesses here are "
    "generated per probe from the extracted port list (FR-08.11)")

#: The acceptance line both harnesses print, in the shape `gen_arc_harness` documents.
_BUGLOOP = re.compile(r"^BUGLOOP (?P<cycle>\d+) (?P<signal>\S+) = "
                      r"(?P<value>[0-9a-fA-F]+)$")


def differential_applicable(spec) -> tuple:
    """FR-08.1's applicability rule, decided from the argv and nothing else."""
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
    """Compare the two `BUGLOOP` line sequences positionally (§3.6.3)."""
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

    Returns:
        {"verdict": DifferentialVerdict, "counters": CounterBlock}, always, including the `not_applicable` verdict with its reason.
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
    """Run one design through arcilator and Verilator from one stimulus."""
    applicable, reason = differential_applicable(spec)
    if not applicable:
        return _differential_verdict(spec, image_spec, "not_applicable", reason)

    directory = Path(artefact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    # Every refusal below carries '' for port_list_sha.
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

    # `side` and not `arm`.
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
    """One `DifferentialVerdict`, with the five stimulus fields always filled."""
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
    """`<probe dir>/lifted.mlir`: the design in the HW dialect, from the probe's own entry tool in the mode FR-08.1 admitted."""
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
    """*argv* with `-o` and whatever follows it removed, in one pass."""
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
    """The operations inside a single outer `module { ... }`, if that is all the text is; otherwise the text unchanged."""
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
    """`<probe dir>/dut.sv`, by `firtool --verilog` on the lifted HW IR (§3.6.3)."""
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
    """§4.10's `--binary` build and then the binary it built."""
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
    """One SIMULATOR side's recorded argv, output digest and limit outcome."""
    return {"argv": side["argv"], "build_argv": side.get("build_argv"),
            "stdout_sha256": hashlib.sha256(
                side["stdout"].encode("utf-8")).hexdigest(),
            "stdout_bytes": len(side["stdout"].encode("utf-8")),
            "exit_status": side["exit_status"], "signal": side["signal"],
            # Keyed "limit" and not by the field's own name.
            "limit": side["limit_hit"]}


# --- 3.6.4 B5, the reducer --------------------------------------------------

#: §4.7's first row: the tools whose input is MLIR text whatever its extension.
_MLIR_TOOLS = ("circt-opt", "circt-translate", "arcilator")

#: One printed MLIR operation per line.
_OP_LINE = re.compile(r"\s*(?:%[\w$.\-]+(?:\s*,\s*%[\w$.\-]+)*\s*=\s*)?"
                      r"[a-zA-Z_]\w*\.[a-zA-Z_][\w.]*")


class _BudgetExpired(Exception):
    """The textual reduction reached `reduction_wall_seconds` (FR-09.4)."""


def select_reducer(spec) -> dict:
    """§4.7's reducer-selection table, by the probe's input language and no other."""
    extension = os.path.splitext(spec.input_filename)[1].lower()
    args = _test_args(spec)
    if extension == ".sv" and spec.tool == "circt-verilog":
        # circt-verilog READS MLIR.
        return {"reducer": "circt-reduce", "lift": "circt-verilog --ir-moore",
                "test_tool": "circt-verilog", "test_args": ["--format=mlir", *args]}
    if extension == ".sv" and spec.tool == "circt-translate":
        # circt-translate has no --format= at all, so it cannot be re-fed its own lift.
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

    Returns:
        {"reduced": ReducedCase, "counters": CounterBlock}.
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
    """Shrink a firing input under a firing-specific interestingness test."""
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
        # §4.7's fifth trigger.
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
            # reducer_aborted: keep whatever --keep-best left that still validates.
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
    """Run one of §4.7's lifts, retrying `--ir-fir` with `--parse-only`."""
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
    """§10.2's post-exit validation, AFTER the reducer process has exited."""
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
    """ddmin over the input's lines, bounded by `reduction_wall_seconds`."""
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
    """FR-09.3: re-run the primary oracle's rules on the reduced input."""
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

#: `03-LLD.md` §10.2, with ONE addition: the counter line.
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

#: Every placeholder §10.2 declares.
_PLACEHOLDERS = ("@TOOL@", "@ARGS@", "@WALL@", "@GRACE@", "@AS_BYTES@",
                 "@CPU_SECONDS@", "@NOFILE@", "@ASSERT_EXPR@", "@ASSERT_SITE@",
                 "@FATAL_MESSAGE@", "@TOP_FRAME@")


def write_interestingness(path: str, verdict: OracleVerdict, tool_path: str,
                          args: list, limits: dict, counter_path: str) -> str:
    """Write §10.2's script for ONE recorded firing and return its text."""
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
        # A None below is a recorded absence and not a defect.
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


#: `contract.to_json`'s canonical shape for the values that are not records.
_canonical = schema.canonical_json


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
        return sha256_file(path)
    except OSError:
        return ""


__all__ = ["BinaryMismatch", "probe_execute", "classify_build", "oracle_primary",
           "strip_prologue", "select_reducer", "reduce_case",
           "write_interestingness", "HarnessError", "Port", "extract_port_list",
           "top_module_name", "gen_arc_harness", "gen_verilator_tb",
           "stimulus_seed", "lfsr_value", "PROBE_NOFILE",
           "CPU_HARD_MARGIN_SECONDS", "X_POLICY",
           "ARC_JIT_ENTRY", "STIMULUS_ID", "RESET_PROTOCOL", "SAMPLE_POINT",
           "DIFFERENTIAL_CYCLES", "PORT_LIST_TIMEOUT_SECONDS"]
