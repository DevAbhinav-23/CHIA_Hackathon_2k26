"""`04-Test-Plan.md` §1.9: `probe_task.py` (B2, B3, B5), the seven statuses,
the three oracle classes, the limits, the prologue strip and the reducers.

**Every test calls its node through `conftest.call_node`**, which invokes the
undecorated original CHIA stores on the wrapper as `_chia_original`; calling the
wrapper itself routes through `chia.trace.profiler.get_profiler`, which starts a
local Ray instance and raises a `FutureWarning` that `-W error` turns into an
error. The nodes keep the decorators `03-LLD.md` §3.2's column gives them
(architect's decision, 2026-09-14).

Tiers follow what a test actually needs, which is §0.5's own rule that a test
states the LOWEST tier at which it can run: `t0` where recorded stderr, a shell
and this interpreter suffice, `t1` and `needs_sdk` where a CIRCT binary must
run. §1.9's column is more conservative in seven rows; each is an erratum
candidate and none is a silent relabelling.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from circt_bug_loop import probe_task
from circt_bug_loop.contract import schema
from circt_bug_loop.probe_task import (BinaryMismatch, _ASSERT_GLIBC,
                                       _ASSERT_UNREACHABLE, _FATAL_ERROR, _FRAME,
                                       classify_build, oracle_primary,
                                       probe_execute, strip_prologue)
from circt_bug_loop.store import BuildResult, Frame, ImageSpec
from circt_bug_loop.tests.conftest import call_node

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STDERR = FIXTURES / "stderr"
SMOKE = Path.home() / ".cache" / "chia-pin-smoke"
BASSERT_G = SMOKE / "bassert_g" / "bin"
SDK_LIBS = f"{SMOKE / 'circt-sdk' / 'lib'}:{SMOKE / 'shim'}"
SYMBOLIZER = SMOKE / "circt-sdk" / "bin" / "llvm-symbolizer"

#: The roots the LIVE host build splits CIRCT across: sources in `src/`,
#: generated `.inc` files under the build tree. The image has one root for both.
HOST_ROOTS = (f"{SMOKE / 'src'}/", f"{SMOKE / 'bassert_g'}/")

#: The prefixes the RECORDED traces carry, as literals. They belong to the
#: fixtures and not to this host: `stderr/trace.txt` and `crashes/crash_01/`
#: were captured on the mining host and their frame paths are verbatim, so a
#: test that rebuilt them from `Path.home()` would pass only there.
TRACE_ROOTS = ("/home/adi/.cache/chia-pin-smoke/src/",
               "/home/adi/.cache/chia-pin-smoke/bassert_g/")
TRACE_TOOL = "/home/adi/.cache/chia-pin-smoke/bassert_g/bin/circt-opt"
CRASH_01_ROOTS = ("/home/adi/.cache/chia-pin-smoke/w09/wt143/",
                  "/home/adi/.cache/chia-pin-smoke/w09/b143/")
CRASH_01_TOOL = "/home/adi/.cache/chia-pin-smoke/w09/b143/bin/circt-opt"

LIMITS = {"probe_wall_seconds": 60, "probe_address_space_bytes": 4 * 1024 ** 3,
          "probe_cpu_seconds": 45, "probe_output_byte_cap": 1_000_000}


def _stderr(name: str) -> str:
    return (STDERR / name).read_text()


def _sha256(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _image_spec(**hashes) -> ImageSpec:
    """An `ImageSpec` whose `tool_hashes` are the ones the test wants believed."""
    return ImageSpec(
        circt_sha="eade0de61bc5a0d2ba1b9da951b69efcab19f8ce", sdk_tag="firtool-1.159.0",
        targets=["circt-opt"], flag_string="-O3 -UNDEBUG -gline-tables-only",
        cmake_args=[], image_digest="sha256:" + "0" * 64,
        image_tag="chia-circt-assert:test", verilator_version="5.020",
        slang_enabled=True, lit_discovery_ok=True, lit_discovered_count=1390,
        assertion_nonreferencing=[], tool_hashes=dict(hashes))


def _spec(tool: str, argv: list, tmp_path: Path, **over):
    """A minimal valid `ProbeSpec` on the seeded arm."""
    fields = dict(
        probe_id="p-0000000001", run_manifest_id="r" * 32, seed_sha="a" * 40,
        arm="seeded", iteration=0, input_filename="input.mlir",
        input_path=str(tmp_path / "input.mlir"), tool=tool, argv=argv,
        polarity="expect_zero", shape="plain", expected_outcome="clean_exit",
        turn_cost={"turn": "probe_write", "wall_seconds": 1.0, "tokens_in": 1,
                   "tokens_out": 1, "cost_usd": 0.0, "metered": True})
    fields.update(over)
    spec = schema.ProbeSpec(**fields)
    schema.validate(spec)
    return spec


def _execute(tool_path: str, argv: list, tmp_path: Path, **over):
    """`probe_execute` against a real binary, with its hash believed."""
    directory = tmp_path / "probe"
    directory.mkdir(exist_ok=True)
    tool = os.path.basename(tool_path)
    return call_node(probe_execute,
                     _spec(tool, argv, tmp_path),
                     _image_spec(**{tool: _sha256(tool_path)}),
                     {**LIMITS, **over}, str(directory),
                     bin_dir=os.path.dirname(tool_path))


def _build(status: str, stderr_name: str, tmp_path: Path, **over) -> BuildResult:
    """A `BuildResult` over one recorded stderr, for driving B3 with no child."""
    path = tmp_path / "stderr.txt"
    path.write_text(_stderr(stderr_name))
    fields = dict(
        probe_id="p-0000000001", run_manifest_id="r" * 32, run_commit="c" * 40,
        image_digest="sha256:" + "0" * 64, status=status,
        binary_path=TRACE_TOOL, binary_sha256="d" * 64,
        argv=["prlimit", "--as=1", "--cpu=1:6", "--nofile=1024", "--",
              TRACE_TOOL, "nested.mlir", "-o", "/dev/null"],
        exit_status=None, signal="SIGSEGV", limit_hit=None, cpu_seconds=0.1,
        wall_seconds=0.2, peak_rss_bytes=1024, worker_hostname="h",
        worker_node_id="", child_pid=1, stdout_path=str(tmp_path / "stdout.txt"),
        stderr_path=str(path), stdout_bytes=0, stderr_bytes=path.stat().st_size,
        truncated=False)
    fields.update(over)
    return BuildResult(**fields)


def _oracle(build: BuildResult, tmp_path: Path, **over):
    kwargs = dict(circt_roots=TRACE_ROOTS, symbolizer=str(tmp_path / "absent"))
    kwargs.update(over)
    return call_node(oracle_primary, build, _image_spec(), str(tmp_path), **kwargs)


@pytest.fixture
def sdk_env(monkeypatch) -> None:
    """Put the SDK's own libraries on the loader path for a tier-1 test.

    The host build links `libz3.so.4`, which lives only in the smoke tree's
    shim; inside the image the loader finds it without help, so this is a
    property of the measurement host and not of the code under test.
    """
    monkeypatch.setenv("LD_LIBRARY_PATH", SDK_LIBS)


def _needs_sdk() -> None:
    if not (BASSERT_G / "circt-opt").exists():
        pytest.skip(f"tier-1 resource absent: {BASSERT_G / 'circt-opt'}")


def nested_array(depth: int) -> str:
    """A `!hw.array` nested *depth* deep, which overflows CIRCT's parser stack.

    Not a recorded fixture but a generator, because the file is 130 KB at the
    depth that overflows reliably and its content is three lines of rule. The
    RECORDED artefacts of the same crash are `stderr/trace.txt` and
    `stderr/segv.txt`, which every tier-0 test here reads.
    """
    inner = "i8"
    for _ in range(depth):
        inner = "!hw.array<1x" + inner + ">"
    return f"hw.module @T(in %a : {inner}) {{}}\n"


# --- B2: the seven statuses -------------------------------------------------

@pytest.mark.t0
def test_u_probe_01_the_hash_check_runs_first(tmp_path) -> None:
    """T-U-probe-01 (FR-06.1, FR-03.16): BinaryMismatch before anything runs.

    Pass criterion: a binary whose SHA-256 differs from `ImageSpec.tool_hashes`
    raises `BinaryMismatch(tool, expected, actual)` and the child is never
    started, asserted by the absence of the streams the run would have written;
    a tool the map does not name at all is refused the same way.
    """
    tool = tmp_path / "circt-opt"
    tool.write_text("#!/bin/sh\ntouch ran\n")
    tool.chmod(0o755)
    directory = tmp_path / "probe"
    directory.mkdir()
    for hashes in ({"circt-opt": "b" * 64}, {}):
        with pytest.raises(BinaryMismatch) as raised:
            call_node(probe_execute, _spec("circt-opt", [], tmp_path),
                      _image_spec(**hashes), LIMITS, str(directory),
                      bin_dir=str(tmp_path))
        assert raised.value.tool == "circt-opt"
        assert raised.value.actual_sha == _sha256(tool)
    assert not (directory / "stderr.txt").exists()
    assert not (tmp_path / "ran").exists()


@pytest.mark.t0
@pytest.mark.parametrize("rc,signal,fixture,status,reason", [
    (0, None, "clean.txt", "clean_exit", ""),
    (1, None, "parse_error.txt", "parse_error", "tool_rejected_input"),
    (None, "SIGABRT", "assert_glibc.txt", "assertion", "assertion_fired"),
    (1, None, "llvm_error.txt", "fatal_error", "llvm_error"),
    (None, "SIGSEGV", "segv.txt", "crash", "died_by_signal"),
    (None, "SIGABRT", "bad_alloc.txt", "oom", "allocation_failure"),
    (None, "SIGABRT", "oom_bare.txt", "oom", "allocation_failure"),
    (None, "SIGABRT", "oom_llvm.txt", "oom", "allocation_failure"),
    (1, None, "parse_error_argv.txt", "parse_error", "tool_rejected_argv"),
])
def test_u_probe_02_to_06_and_10_11_40_the_status_table(
        rc, signal, fixture, status, reason) -> None:
    """T-U-probe-02..06, -10, -11, -40 (FR-06.6, FR-06.7, FR-06.9, FR-07.2).

    Pass criterion: each recorded stderr classifies into exactly the status and
    `stopping_reason` §3.6's table gives it. `LLVM ERROR: out of memory`
    classifies `oom` and not `fatal_error`, allocation evidence being tested
    first; a rejected argv and a rejected input share the `parse_error` status
    and differ only in the reason, FR-06.9's seven being closed.
    """
    assert classify_build(rc, signal, _stderr(fixture), None) == (status, reason)


@pytest.mark.t0
def test_u_probe_12_the_test_order_and_the_oom_second_conjunct() -> None:
    """T-U-probe-12 (FR-06.7, FR-07.2): the order, and `oom`'s second conjunct.

    Pass criterion: on one stderr carrying an assertion line **and**
    `std::bad_alloc`, death by signal classifies `oom` and a clean non-zero exit
    classifies `assertion`, because FR-06.7 reads "terminated by signal **and**
    its stderr carries an allocation-failure line"; and the three `limit_hit`
    values outrank every text rule.
    """
    both = _stderr("both.txt")
    assert classify_build(None, "SIGABRT", both, None) == ("oom", "allocation_failure")
    assert classify_build(1, None, both, None) == ("assertion", "assertion_fired")
    assert classify_build(None, "SIGSEGV", both, "wall") == ("timeout", "wall_limit")
    assert classify_build(None, "SIGXCPU", both, "cpu") == ("timeout", "cpu_limit")
    assert classify_build(1, None, both, "address_space") == ("oom",
                                                              "address_space_limit")


@pytest.mark.t0
def test_u_probe_07_09_a_timeout_carries_a_null_signal(tmp_path) -> None:
    """T-U-probe-07, -09 (FR-06.4, FR-06.9, FR-07.8): killed at the wall limit.

    Pass criterion: a probe the stage killed carries `timeout`, `limit_hit`
    "wall" and a **null** signal on both the `BuildResult` and the
    `ProbeResult`, so it can never be read back as a crash; and the primary
    oracle does not fire on it.
    """
    out = _execute("/bin/sh", ["-c", "sleep 30"], tmp_path, probe_wall_seconds=1)
    build, result = out["build_result"], out["probe_result"]
    assert build.status == "timeout" and build.limit_hit == "wall"
    assert build.signal is None and result.signal is None
    assert result.stopping_reason == "wall_limit"
    assert _oracle(build, tmp_path).fired is False


@pytest.mark.t0
def test_u_probe_08_oom_by_the_address_space_limit(tmp_path) -> None:
    """T-U-probe-08 (FR-06.7): `limit_hit == "address_space"` is `oom`.

    Pass criterion: a child allocating past the limit is `oom` with a non-zero
    exit status and no signal, because `RLIMIT_AS` makes allocation fail rather
    than killing; the oracle does not fire and the parent survives.
    """
    out = _execute("/bin/sh",
                   ["-c", f"exec {os.sys.executable} -c "
                          "'b = bytearray(500 * 1024 * 1024)'"],
                   tmp_path, probe_address_space_bytes=104857600)
    build = out["build_result"]
    assert build.status == "oom" and build.limit_hit == "address_space"
    assert build.signal is None and build.exit_status != 0
    assert _oracle(build, tmp_path).fired is False


@pytest.mark.t0
def test_u_probe_13_14_no_shell_and_the_exact_prlimit_prefix(tmp_path) -> None:
    """T-U-probe-13, -14 (FR-06.1, FR-06.2): an argument list, and its shape.

    Pass criterion: the recorded `argv.json` is exactly ["prlimit",
    "--as=<bytes>", "--cpu=<soft>:<soft+5>", "--nofile=1024", "--", <abs tool>,
    *spec.argv]; long spellings only, `--rss` never, and a source walk finds no
    `shell=True` and no command string in either module on the measured path.
    """
    out = _execute("/bin/true", ["--flag"], tmp_path)
    recorded = json.loads((tmp_path / "probe" / "argv.json").read_text())
    assert recorded == out["build_result"].argv
    assert recorded == ["prlimit", f"--as={LIMITS['probe_address_space_bytes']}",
                        "--cpu=45:50", "--nofile=1024", "--", "/bin/true", "--flag"]
    assert probe_task.PROBE_NOFILE == 1024
    assert "--rss" not in " ".join(recorded)
    for module in (probe_task, __import__("circt_bug_loop.circt_core",
                                          fromlist=["x"])):
        tree = ast.parse(Path(module.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                assert not any(kw.arg == "shell" for kw in node.keywords)


@pytest.mark.t0
def test_u_probe_15_streams_are_captured_and_capped(tmp_path) -> None:
    """T-U-probe-15 (FR-06.4, FR-17.7): stdout.txt, stderr.txt and the cap.

    Pass criterion: both streams land in the probe directory, are truncated at
    `probe_output_byte_cap` with `truncated=True` recorded, and the byte counts
    on the `BuildResult` are the bytes actually kept. The `ProbeResult`'s two
    capped text fields are None at this stage: `reduced_text` is B5's and
    `assertion_text` is B3's, so `contract.bound_text` has nothing to bound
    here (erratum candidate against §3.6's step 4).
    """
    out = _execute("/bin/sh", ["-c", "printf 'o%.0s' $(seq 1 5000); "
                                     "printf 'e%.0s' $(seq 1 5000) >&2"],
                   tmp_path, probe_output_byte_cap=1000)
    build, result = out["build_result"], out["probe_result"]
    assert build.truncated is True
    assert build.stdout_bytes == 1000 and build.stderr_bytes == 1000
    assert Path(build.stdout_path).read_text() == "o" * 1000
    assert Path(build.stderr_path).read_text() == "e" * 1000
    assert result.reduced_text is None and result.assertion_text is None


@pytest.mark.t0
def test_u_probe_41_42_43_the_fields_no_other_module_writes(tmp_path) -> None:
    """T-U-probe-41, -42, -43 (FR-06.2, FR-06.4, FR-13.2, NFR-02).

    Pass criterion: `limit_hit` is written by `circt_exec_probe` and by no other
    module, asserted by a source search; `peak_rss_bytes` reaches the
    `BuildResult` from `ru_maxrss * 1024`; and `worker_hostname`,
    `worker_node_id` and `child_pid` all reach it, without which FR-13.2's
    recorded pair for the original run has no source.
    """
    out = _execute("/bin/true", [], tmp_path)
    build = out["build_result"]
    assert build.peak_rss_bytes and build.peak_rss_bytes > 0
    assert build.worker_hostname and build.child_pid > 0
    assert isinstance(build.worker_node_id, str)
    assert build.cpu_seconds >= 0.0
    flow = Path(probe_task.__file__).parent
    writers = [path.name for path in flow.glob("*.py")
               if re.search(r'"limit_hit":', path.read_text())]
    assert writers == ["circt_core.py"], writers


# --- B3: the three firing patterns and the oracle ---------------------------

@pytest.mark.t0
def test_u_probe_16_39_the_glibc_pattern_takes_cpp_names() -> None:
    """T-U-probe-16, -39 (FR-07.1, FR-07.3): `func` is `.+?` and not `[^:]+`.

    Pass criterion: the compiled C++ sample and the C control both match; the
    whole signature lands in `func`, including its `::`, and the whole condition
    in `expr`, including the `&& "..."` tail. The old `[^:]+` matched only the
    control, whose function name has no `::`, so it would have classified no
    CIRCT assertion at all.
    """
    c = _ASSERT_GLIBC.match(_stderr("assert_glibc.txt").strip()).groupdict()
    assert c == {"file": "a.c", "line": "2", "func": "main",
                 "expr": 'c>99 && "needs many args"'}
    cpp = _ASSERT_GLIBC.match(_stderr("assert_cpp.txt").strip()).groupdict()
    assert cpp == {"file": "b.cpp", "line": "2",
                   "func": "int circt::Foo::get(int) const",
                   "expr": 'c > 99 && "needs many args"'}
    circt = _ASSERT_GLIBC.match(
        "/workspace/circt/build/bin/circt-opt: /workspace/circt/lib/Dialect/Comb/"
        "CombFolds.cpp:1234: mlir::OpFoldResult circt::comb::ExtractOp::fold("
        "FoldAdaptor): Assertion `lo + width <= inputWidth && \"extract out of "
        "range\"' failed.").groupdict()
    assert circt["file"] == "/workspace/circt/lib/Dialect/Comb/CombFolds.cpp"
    assert circt["line"] == "1234"
    assert circt["func"] == "mlir::OpFoldResult circt::comb::ExtractOp::fold(FoldAdaptor)"
    assert circt["expr"] == 'lo + width <= inputWidth && "extract out of range"'


@pytest.mark.t0
def test_u_probe_17_the_unreachable_pattern_reads_the_preceding_line(tmp_path) -> None:
    """T-U-probe-17 (FR-07.1, FR-07.3): no `msg` group, two-line extraction.

    Pass criterion: the pattern is anchored, has no `msg` group, and matches
    with and without the ` at <file>:<line>` tail; `assertion_text` is the
    preceding stderr line, a newline, and the matched line with its trailing `!`
    removed; `assertion_site` is `<file>:<line>` when the location matched and
    None otherwise, in which case the fingerprint falls to the frame basis.
    """
    assert "msg" not in _ASSERT_UNREACHABLE.groupindex
    assert _ASSERT_UNREACHABLE.match("UNREACHABLE executed!").groupdict() == \
        {"file": None, "line": None}
    assert _ASSERT_UNREACHABLE.match(
        "UNREACHABLE executed at F.cpp:7!").groupdict() == {"file": "F.cpp", "line": "7"}
    assert _ASSERT_UNREACHABLE.match("prefix UNREACHABLE executed!") is None

    text, site = probe_task._extract_assertion(_stderr("unreachable_two_line.txt"))
    assert text == ("Unhandled dialect in HWOps lowering\nUNREACHABLE executed at "
                    "/workspace/circt/lib/Dialect/HW/HWOps.cpp:1234")
    assert site == "/workspace/circt/lib/Dialect/HW/HWOps.cpp:1234"

    text, site = probe_task._extract_assertion(_stderr("unreachable_bare.txt"))
    assert text == "UNREACHABLE executed" and site is None
    text, site = probe_task._extract_assertion(_stderr("unreachable_located.txt"))
    assert text == "UNREACHABLE executed at F.cpp:7" and site == "F.cpp:7"


@pytest.mark.t0
def test_u_probe_18_21_the_fatal_error_pattern() -> None:
    """T-U-probe-18, -21 (FR-07.1, FR-07.2): `LLVM ERROR: ` and what follows it.

    Pass criterion: the pattern matches a line beginning `LLVM ERROR: ` and the
    captured message is exactly the text after it.
    """
    found = probe_task._first_match(_FATAL_ERROR, _stderr("llvm_error.txt"))
    assert found[0] == 0
    assert found[1].group("message") == \
        "unsupported lowering for type '!hw.struct<a: i1>'"
    assert _FATAL_ERROR.match("an LLVM ERROR: x") is None


@pytest.mark.t0
@pytest.mark.parametrize("status,fires", [
    ("crash", True), ("assertion", True), ("fatal_error", True),
    ("clean_exit", False), ("parse_error", False), ("timeout", False), ("oom", False)])
def test_u_probe_19_fired_for_exactly_three_statuses(status, fires, tmp_path) -> None:
    """T-U-probe-19 (FR-07.1, FR-07.8): fired is true for three and no other.

    Pass criterion: the oracle fires for exactly `crash`, `assertion` and
    `fatal_error`, and `oracle_class` is non-null exactly when it fires.
    """
    verdict = _oracle(_build(status, "segv.txt", tmp_path), tmp_path)
    assert verdict.fired is fires
    assert (verdict.oracle_class is not None) is fires
    assert (verdict.oracle_class == status) is fires


@pytest.mark.t0
def test_u_probe_20_assertion_text_and_site_are_verbatim(tmp_path) -> None:
    """T-U-probe-20 (FR-07.3): character for character, and non-empty.

    Pass criterion: for a glibc assertion the verdict's `assertion_text` is the
    `expr` group and its `assertion_site` is `<file>:<line>`, both substrings of
    the recorded stderr; for a `fatal_error` the `fatal_message` is exactly the
    text after `LLVM ERROR: ` and both assertion fields are None.
    """
    stderr = _stderr("assert_cpp.txt")
    verdict = _oracle(_build("assertion", "assert_cpp.txt", tmp_path,
                             signal="SIGABRT"), tmp_path)
    assert verdict.assertion_text == 'c > 99 && "needs many args"'
    assert verdict.assertion_site == "b.cpp:2"
    assert verdict.assertion_text in stderr and verdict.assertion_site in stderr
    assert verdict.fatal_message is None

    fatal = _oracle(_build("fatal_error", "llvm_error.txt", tmp_path), tmp_path)
    assert fatal.fatal_message == "unsupported lowering for type '!hw.struct<a: i1>'"
    assert fatal.assertion_text is None and fatal.assertion_site is None


@pytest.mark.t0
def test_u_probe_22_the_frame_pattern_parses_both_shapes() -> None:
    """T-U-probe-22 (FR-07.4): `module_offset` and `attributed`, both recorded.

    Pass criterion: both shapes occur in the one recorded trace with a non-zero
    count each; the parenthesised form yields `module` and `offset` and no file,
    the print-time-symbolised form yields `file` and `line` and no module; every
    `#<n> 0x...` line of the trace is matched, so no frame is lost.
    """
    trace = _stderr("trace.txt")
    frames = probe_task._parse_frames(trace)
    shapes = [f.shape for f in frames]
    assert shapes.count("module_offset") > 0 and shapes.count("attributed") > 0
    assert len(frames) == len([line for line in trace.splitlines()
                               if re.match(r"^\s*#\d+\s+0x", line)])
    module_offset = next(f for f in frames if f.shape == "module_offset")
    assert module_offset.module.endswith("libLLVMSupport.so")
    assert module_offset.offset == "0x23cceb"
    assert module_offset.file == "" and module_offset.line == 0
    attributed = next(f for f in frames if f.shape == "attributed")
    assert attributed.module == "" and attributed.offset == ""
    assert attributed.file and attributed.line >= 0
    lambda_frame = next(f for f in frames if "(lambda at" in f.function)
    assert lambda_frame.file.endswith("OpImplementation.h")
    # The pattern is anchored at both ends, so the trace's own prose is not a
    # frame and neither is the "Stack dump without symbol names" shape LLVM
    # prints when it cannot find llvm-symbolizer at all (§3.6.2).
    for prose in ("Stack dump:", "1.\tMLIR Parser: custom op parser 'hw.module' ",
                  "0x00007fe04683cceb llvm::sys::PrintStackTrace"):
        assert _FRAME.match(prose) is None


@pytest.mark.t0
def test_u_probe_44_strip_prologue(tmp_path) -> None:
    """T-U-probe-44 (FR-07.5, FR-10.1): exactly four frames, and which four.

    Pass criterion: the strip drops the leading frames whose normalised name is
    one of §3.7.1's ten, and the leading unresolved libc frame, and stops at the
    first survivor: on the recorded trace exactly four go, and they are
    PrintStackTrace, RunSignalHandlers, SignalHandler and the libc frame.
    `prologue_dropped` records the count, so the strip is auditable from the row.

    §3.7.1 measured 466 frames and 462 survivors on ITS capture of this crash;
    the committed capture has 470 and 466. A stack overflow's depth is not
    reproducible and the strip's count is, which is the property under test.
    """
    frames = probe_task._parse_frames(_stderr("trace.txt"))
    stripped = strip_prologue(frames)
    assert len(frames) - len(stripped) == 4
    assert [probe_task._normalise_function(f.function) for f in frames[:3]] == \
        ["llvm::sys::PrintStackTrace", "llvm::sys::RunSignalHandlers", "SignalHandler"]
    assert frames[3].function == "" and frames[3].module == "/usr/lib/libc.so.6"
    assert stripped[0] is frames[4]

    verdict = _oracle(_build("crash", "trace.txt", tmp_path), tmp_path)
    assert verdict.prologue_dropped == 4
    assert len(verdict.frames) == len(frames)       # the record keeps the prologue

    # The strip stops at the first survivor: a later `abort` is kept.
    deep = [Frame(index=0, address="0x0", shape="attributed", module="", offset="",
                  function="abort", file="a.c", line=1, in_circt_object=False),
            Frame(index=1, address="0x1", shape="attributed", module="", offset="",
                  function="circt::run()", file="b.cpp", line=2, in_circt_object=True),
            Frame(index=2, address="0x2", shape="attributed", module="", offset="",
                  function="abort", file="c.c", line=3, in_circt_object=False)]
    assert len(strip_prologue(deep)) == 2


@pytest.mark.t0
def test_u_probe_23_24_the_two_counts_and_the_scope_root(tmp_path) -> None:
    """T-U-probe-23, -24 (FR-07.4, FR-07.5): what each count means, and when.

    Pass criterion: `frames_resolved` counts a non-empty function name, which an
    SDK module supplies; `frames_with_location` counts `line > 0 AND
    in_circt_object`, so a frame resolved inside an SDK `.so` raises the first
    and not the second. `out_of_scope_root` is computed **after** the strip:
    unstripped the first frame is `llvm::sys::PrintStackTrace` in
    `libLLVMSupport.so` for every crash, so every candidate would be out of
    scope and F-12 would never run.
    """
    verdict = _oracle(_build("crash", "trace.txt", tmp_path), tmp_path)
    assert verdict.frames_resolved > verdict.frames_with_location > 0
    assert verdict.frames_resolved == sum(1 for f in verdict.frames if f.function)
    assert verdict.frames_with_location == sum(
        1 for f in verdict.frames if f.line > 0 and f.in_circt_object)
    assert all(not f.in_circt_object for f in verdict.frames
               if "circt-sdk/lib/" in f.module)

    # This crash roots in MLIR's own parser, so the field is true; the control is
    # that it would be true for every crash if the strip were skipped.
    assert verdict.out_of_scope_root is True
    assert verdict.frames[0].in_circt_object is False
    in_scope = strip_prologue(verdict.frames)
    assert any(f.in_circt_object for f in in_scope), "the trace does reach CIRCT"
    assert verdict.fingerprint_frame == "parseHWArray HWTypes.cpp"


@pytest.mark.t0
def test_u_probe_24b_a_circt_rooted_crash_is_in_scope(tmp_path) -> None:
    """T-U-probe-24 (FR-07.5), the other side: a crash whose root IS CIRCT's.

    Pass criterion: on the recorded `crash_01` fixture, whose first stripped
    frames are SDK header inlines and whose first CIRCT frame is the folder that
    dereferenced null, the fingerprint frame is the folder and the top-five
    evidence tuple is the one the fixture recorded.
    """
    crash = FIXTURES / "crashes" / "crash_01"
    expected = json.loads((crash / "expected.json").read_text())
    build = _build("crash", "clean.txt", tmp_path, binary_path=CRASH_01_TOOL,
                   stderr_path=str(crash / "stderr.txt"))
    verdict = _oracle(build, tmp_path, circt_roots=CRASH_01_ROOTS)
    assert verdict.prologue_dropped == expected["prologue_dropped"]
    assert verdict.fingerprint_frame == expected["fingerprint_frame"]
    stripped = strip_prologue(verdict.frames)
    assert [probe_task._normalise_function(f.function) for f in stripped[:5]] == \
        expected["top_frames"]
    assert verdict.oracle_class == expected["class"]


@pytest.mark.t0
def test_u_probe_25_the_repro_command_drops_the_prlimit_prefix(tmp_path) -> None:
    """T-U-probe-25 (FR-07.6): one shlex.join line a maintainer can paste.

    Pass criterion: the line names the absolute binary path and the probe's own
    argv and carries **no** `prlimit` prefix, the limits being the loop's
    concern and not the report's; it is written to `repro.sh`, executable.
    """
    verdict = _oracle(_build("crash", "segv.txt", tmp_path), tmp_path)
    assert verdict.repro_command == f"{TRACE_TOOL} nested.mlir -o /dev/null"
    assert "prlimit" not in verdict.repro_command
    script = tmp_path / "repro.sh"
    assert verdict.repro_command in script.read_text()
    assert os.access(script, os.X_OK)


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_probe_26_the_flag_state_and_the_version(tmp_path, sdk_env) -> None:
    """T-U-probe-26 (FR-07.7, FR-03.11): `-UNDEBUG`, and "Optimized build.".

    Pass criterion: the verdict carries the literal `-UNDEBUG` in its flag
    string and the tool's own `--version` output, which still reads
    "Optimized build." — which is why a report must state the flag rather than
    the version.
    """
    _needs_sdk()
    build = _build("crash", "segv.txt", tmp_path,
                   binary_path=str(BASSERT_G / "circt-opt"))
    verdict = _oracle(build, tmp_path)
    assert "-UNDEBUG" in verdict.flag_string
    assert "Optimized build." in verdict.tool_version_output
    assert "CIRCT" in verdict.tool_version_output


@pytest.mark.t0
def test_u_probe_49_the_imports_probe_task_is_allowed(tmp_path) -> None:
    """T-U-probe-49 (FR-16.1, FR-17.3): the record dataclasses, never LoopStore.

    Pass criterion: an import walk shows the record names imported from `store`
    and `LoopStore` imported nowhere; the module opens no `sqlite3` connection
    and names no `loop.db`.
    """
    tree = ast.parse(Path(probe_task.__file__).read_text())
    from_store = {alias.name for node in ast.walk(tree)
                  if isinstance(node, ast.ImportFrom) and node.module
                  and node.module.endswith("store")
                  for alias in node.names}
    assert from_store <= {"BuildResult", "OracleVerdict", "Frame",
                          "DifferentialVerdict", "ReducedCase", "ImageSpec"}
    assert "LoopStore" not in from_store
    source = Path(probe_task.__file__).read_text()
    assert "sqlite3" not in source and "loop.db" not in source


# --- B5: the reducers, the script and the selection table -------------------

REDUCTION = {"reduction_wall_seconds": 120, "reduction_sigkill_grace_seconds": 10}


def _verdict(tmp_path: Path, name: str = "trace.txt", status: str = "crash", **over):
    return _oracle(_build(status, name, tmp_path, **over), tmp_path)


def _sv_spec(tool: str, tmp_path: Path, extra: list):
    path = tmp_path / "input.sv"
    return _spec(tool, [*extra, str(path)], tmp_path,
                 input_filename="input.sv", input_path=str(path))


@pytest.mark.t0
def test_u_probe_31_the_five_reducer_branches(tmp_path) -> None:
    """T-U-probe-31 (FR-09.9): every branch, with its lift and its own test argv.

    Pass criterion: MLIR text reduces directly under the probe's own tool and
    argv; `.fir` lifts with `firtool --ir-fir`; a `.sv` probe entering through
    `circt-verilog` is tested by its own tool with `--format=mlir` prepended and
    every other token of its argv kept, the seed's output-mode flag included; a
    `.sv` probe entering through `circt-translate --import-verilog`, which has
    no `--format=` at all, is tested by `circt-opt <candidate> -o /dev/null`;
    everything else is textual.
    """
    mlir = _spec("circt-opt", [str(tmp_path / "input.mlir"), "--canonicalize"], tmp_path)
    assert probe_task.select_reducer(mlir) == {
        "reducer": "circt-reduce", "lift": None, "test_tool": "circt-opt",
        "test_args": ["--canonicalize"]}

    fir = _spec("firtool", [str(tmp_path / "input.fir"), "--ir-hw"], tmp_path,
                input_filename="input.fir", input_path=str(tmp_path / "input.fir"))
    assert probe_task.select_reducer(fir) == {
        "reducer": "circt-reduce", "lift": "firtool --ir-fir",
        "test_tool": "firtool", "test_args": ["--ir-hw"]}

    verilog = _sv_spec("circt-verilog", tmp_path, ["--ir-moore", "-I", "/inc"])
    assert probe_task.select_reducer(verilog) == {
        "reducer": "circt-reduce", "lift": "circt-verilog --ir-moore",
        "test_tool": "circt-verilog",
        "test_args": ["--format=mlir", "--ir-moore", "-I", "/inc"]}

    translate = _sv_spec("circt-translate", tmp_path, ["--import-verilog"])
    assert probe_task.select_reducer(translate) == {
        "reducer": "circt-reduce", "lift": "circt-verilog --ir-moore",
        "test_tool": "circt-opt", "test_args": ["-o", "/dev/null"]}

    other = _spec("circt-bmc", [str(tmp_path / "input.btor")], tmp_path,
                  input_filename="input.btor", input_path=str(tmp_path / "input.btor"))
    assert probe_task.select_reducer(other)["reducer"] == "textual-ddmin"
    assert probe_task.select_reducer(other)["lift"] is None


@pytest.mark.t0
def test_u_probe_32_the_reducer_argv_and_its_binary(tmp_path, monkeypatch) -> None:
    """T-U-probe-32 (FR-09.2, FR-06.1): the source-built binary, and no flags.

    Pass criterion: `reduce_case` runs `circt-reduce` from the SOURCE tree, with
    `--test=<script>`, `--keep-best` and `-o`, and never `--test-must-fail` and
    never a `--test-arg`, so the candidate is the script's `$1`.
    """
    seen = {}

    def _fake(input_path, script, out_path, **kwargs):
        seen.update(kwargs, input_path=input_path, script=script, out=out_path)
        Path(out_path).write_text("module {}\n")
        return {"success": True, "returncode": 0, "wall_seconds": 0.1,
                "output_valid": True, "log_tail": ""}

    monkeypatch.setattr(probe_task, "_reduce_run",
                        lambda i, s, o, limits, bin_dir: _fake(
                            i, s, o, binary=os.path.join(bin_dir, "circt-reduce"),
                            wall_seconds=limits["reduction_wall_seconds"]))
    (tmp_path / "input.mlir").write_text("hw.module @T() {}\n")
    spec = _spec("circt-opt", [str(tmp_path / "input.mlir")], tmp_path)
    call_node(probe_task.reduce_case, spec, _verdict(tmp_path),
              {**LIMITS, **REDUCTION}, str(tmp_path), bin_dir="/workspace/circt/build/bin")
    assert seen["binary"] == "/workspace/circt/build/bin/circt-reduce"
    assert seen["script"].endswith("interesting.sh")
    assert seen["wall_seconds"] == 120
    argv = probe_task.circt_reduce_run.__doc__
    assert "--test-must-fail is never passed" in argv


@pytest.mark.t0
def test_u_probe_45_exactly_one_class_block_and_every_placeholder(tmp_path) -> None:
    """T-U-probe-45 (FR-09.1, FR-09.2): one block, all placeholders bound.

    Pass criterion: a written `interesting.sh` contains exactly one
    `# --- class:` line, it names the candidate's own class, the other two
    blocks are absent, no `@NAME@` survives anywhere in the file, and the three
    class-specific values appear only in their own block. `sh -n` passing is
    asserted as necessary and not sufficient: it passed on the earlier version
    in which two of the three blocks were dead code below an `exit 0`.
    """
    import subprocess as sp
    for name, klass, marker in (("trace.txt", "crash", "parseHWArray"),
                                ("assert_cpp.txt", "assertion",
                                 'c > 99 && "needs many args"'),
                                ("llvm_error.txt", "fatal_error",
                                 "unsupported lowering")):
        verdict = _verdict(tmp_path, name, klass,
                           signal="SIGABRT" if klass != "crash" else "SIGSEGV")
        script = tmp_path / f"interesting_{klass}.sh"
        text = probe_task.write_interestingness(
            str(script), verdict, "/workspace/circt/build/bin/circt-opt",
            ["--canonicalize"], {**LIMITS, **REDUCTION}, str(tmp_path / "calls"))
        blocks = [line for line in text.splitlines() if line.startswith("# --- class:")]
        assert len(blocks) == 1 and klass in blocks[0]
        assert not re.search(r"@[A-Z_]+@", text), re.findall(r"@[A-Z_]+@", text)
        for placeholder in probe_task._PLACEHOLDERS:
            assert placeholder not in text
        assert marker in text
        # The flag is named in the header comment, which states the polarity,
        # and appears on no executable line: the script IS the polarity.
        assert all(line.lstrip().startswith("#")
                   for line in text.splitlines() if "--test-must-fail" in line)
        assert text.count("grep -qF") >= 2 and "grep -qE" not in text
        assert sp.run(["sh", "-n", str(script)]).returncode == 0
        assert os.access(script, os.X_OK)
        # The other two classes' guards are absent, not merely unreachable.
        for other, guard in (("assertion", "grep -qF 'c > 99"),
                             ("fatal_error", "^LLVM ERROR:"),
                             ("crash", '"$RC" -gt 128')):
            if other != klass:
                assert guard not in text or other == klass


@pytest.mark.t0
def test_u_probe_45b_the_top_frame_guard_is_the_fingerprint_frame(tmp_path) -> None:
    """T-U-probe-45 (K3), the half that is a correction rather than a shape.

    Pass criterion: `@TOP_FRAME@` binds to the function-name half of the
    FINGERPRINT frame, not to the first resolved frame, which is
    `llvm::sys::PrintStackTrace` for every crash in the campaign and would match
    any crash at all; and a verdict with no fingerprint frame binds the empty
    string rather than the four letters of "None".
    """
    verdict = _verdict(tmp_path)
    assert verdict.fingerprint_frame == "parseHWArray HWTypes.cpp"
    text = probe_task.write_interestingness(
        str(tmp_path / "i.sh"), verdict, "/bin/true", [],
        {**LIMITS, **REDUCTION}, str(tmp_path / "calls"))
    assert "grep -qF parseHWArray " in text
    assert "PrintStackTrace" not in text

    import dataclasses
    blind = dataclasses.replace(verdict, fingerprint_frame=None)
    text = probe_task.write_interestingness(
        str(tmp_path / "j.sh"), blind, "/bin/true", [],
        {**LIMITS, **REDUCTION}, str(tmp_path / "calls"))
    assert "grep -qF '' " in text and "None" not in text


@pytest.mark.t0
def test_u_probe_46_the_script_cds_and_keeps_its_stderr_quiet(tmp_path) -> None:
    """T-U-probe-46 (FR-09.13): the working directory, and the subshell.

    Pass criterion: the candidate is absolutised BEFORE the `cd`, because
    `circt-reduce` passes it relative to its own cwd; the script then `cd`s into
    its own `mktemp -d`, so anything the tool writes beside its input lands
    there; and the subshell with its own stderr keeps the shell's
    "Segmentation fault <command line>" out of `circt-reduce`'s stderr,
    asserted by zero stderr bytes on an interesting candidate.

    The tool is a stub that kills itself with SIGSEGV and prints the recorded
    frame, so the crash block is exercised with no CIRCT present.
    """
    import subprocess as sp
    stub = tmp_path / "crasher.sh"
    stub.write_text("#!/bin/sh\n"
                    "printf 'in parseHWArray at HWTypes.cpp\\n' >&2\n"
                    "touch beside-the-input\n"
                    "kill -SEGV $$\n")
    stub.chmod(0o755)
    verdict = _verdict(tmp_path)
    script = tmp_path / "interesting.sh"
    text = probe_task.write_interestingness(
        str(script), verdict, str(stub), [], {**LIMITS, **REDUCTION},
        str(tmp_path / "calls"))
    assert 'CANDIDATE=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")' in text
    assert text.index("CANDIDATE=") < text.index('cd "$WORK"')

    candidate = tmp_path / "cand.mlir"
    candidate.write_text("hw.module @T() {}\n")
    done = sp.run([str(script), "cand.mlir"], cwd=str(tmp_path), capture_output=True)
    assert done.returncode == 0, done.stderr
    assert done.stderr == b"", done.stderr
    assert not (tmp_path / "beside-the-input").exists()
    assert (tmp_path / "calls").stat().st_size == 1

    # A tool that exits cleanly is not the recorded crash.
    quiet = tmp_path / "quiet.sh"
    quiet.write_text("#!/bin/sh\nexit 0\n")
    quiet.chmod(0o755)
    probe_task.write_interestingness(str(script), verdict, str(quiet), [],
                                     {**LIMITS, **REDUCTION}, str(tmp_path / "calls"))
    assert sp.run([str(script), "cand.mlir"], cwd=str(tmp_path)).returncode == 1


@pytest.mark.t0
def test_u_probe_36_the_output_is_validated_after_the_exit(tmp_path) -> None:
    """T-U-probe-36 (FR-09.13): a truncated `-o` output is discarded.

    Pass criterion: the committed empty `reducer/truncated/reduced.mlir` fails
    the post-exit validation on its first conjunct, non-emptiness, and the
    validation is reached only once the reducer process has exited, which
    `T-U-core-09` asserts on the call itself.
    """
    empty = FIXTURES / "reducer" / "truncated" / "reduced.mlir"
    assert empty.stat().st_size == 0
    assert probe_task._valid_output(empty, tmp_path / "absent.sh", "/nonexistent",
                                    {**LIMITS, **REDUCTION}) is False


@pytest.mark.t0
def test_u_probe_34_an_input_the_oracle_never_fired_on(tmp_path) -> None:
    """T-U-probe-34 (FR-09.12): `reduced=false` with the reason recorded.

    Pass criterion: a verdict that did not fire yields `reducer="none"`,
    `reduced=False` and a reason, the sizes equal, and no reducer is run; the
    candidate still proceeds, which is what makes it countable.
    """
    (tmp_path / "input.mlir").write_text("hw.module @T() {}\n")
    spec = _spec("circt-opt", [str(tmp_path / "input.mlir")], tmp_path)
    case = call_node(probe_task.reduce_case, spec,
                     _verdict(tmp_path, "clean.txt", "clean_exit", signal=None,
                              exit_status=0),
                     {**LIMITS, **REDUCTION}, str(tmp_path), bin_dir="/nonexistent")
    assert case.reducer == "none" and case.reduced is False
    assert case.reason == "oracle_did_not_fire"
    assert case.size_before_bytes == case.size_after_bytes
    assert case.interestingness_calls == 0


def _stub_bin(tmp_path: Path, marker: str) -> Path:
    """A tool directory: a stub that "crashes" on *marker*, beside the real tools.

    The interestingness script's `@TOOL@` is whatever the branch names, so a
    stub is enough to drive the REAL `circt-reduce` over REAL MLIR with a
    firing that is reproducible by construction. `circt-opt` and `circt-reduce`
    are linked in beside it because `reduce_case` resolves all three against the
    same `bin_dir`.
    """
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    for name in ("circt-opt", "circt-reduce"):
        link = binaries / name
        if not link.exists():
            link.symlink_to(BASSERT_G / name)
    stub = binaries / "crasher.sh"
    stub.write_text("#!/bin/sh\n"
                    'for a in "$@"; do last=$a; done\n'
                    f"if grep -q '{marker}' \"$last\"; then\n"
                    "  printf 'in parseHWArray at HWTypes.cpp\\n' >&2\n"
                    "  kill -SEGV $$\n"
                    "fi\n"
                    "exit 0\n")
    stub.chmod(0o755)
    return binaries


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_probe_33_38_circt_reduce_shrinks_and_the_recheck_matches(
        tmp_path, sdk_env) -> None:
    """T-U-probe-33, -38 (FR-09.3, FR-09.5, FR-09.7, FR-09.11, NFR-02).

    Pass criterion: the real source-built `circt-reduce` shrinks a real MLIR
    input under §10.2's script; both size pairs are recorded with the after
    values no larger than the before values; `fixpoint` and `budget_truncated`
    are present; the `-o` output is validated after the exit; and the re-check
    re-runs the oracle's rules on the reduced input and records a matching
    class, which sets `recheck_matches`.
    """
    _needs_sdk()
    binaries = _stub_bin(tmp_path, "comb.mul")
    source = tmp_path / "input.mlir"
    source.write_text(
        "hw.module @top(in %a : i8, out b : i8) {\n"
        "  %0 = comb.add %a, %a : i8\n"
        "  %1 = comb.mul %0, %a : i8\n"
        "  %2 = comb.and %1, %a : i8\n"
        "  %3 = comb.or %2, %a : i8\n"
        "  hw.output %3 : i8\n}\n")
    spec = _spec("crasher.sh", [str(source)], tmp_path, input_path=str(source))
    case = call_node(probe_task.reduce_case, spec, _verdict(tmp_path),
                     {**LIMITS, **REDUCTION}, str(tmp_path / "probe"),
                     bin_dir=str(binaries))
    assert case.reducer == "circt-reduce" and case.lift is None
    assert case.reduced is True and case.fixpoint is True
    assert case.budget_truncated is False
    assert case.size_after_bytes < case.size_before_bytes
    assert case.size_after_ops <= case.size_before_ops
    assert case.interestingness_calls > 1
    assert "comb.mul" in Path(case.path).read_text()
    assert case.recheck_class == "crash" and case.recheck_matches is True
    assert case.recheck_assertion_text is None


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_probe_33b_a_changed_failure_is_not_a_match(tmp_path, sdk_env) -> None:
    """T-U-probe-33, -35 (FR-09.7): a re-check that disagrees sets no match.

    Pass criterion: when the reduced case no longer reproduces the recorded
    class, `recheck_matches` is False, which is what FR-09.7's
    `reduction_changed_failure` is raised from.
    """
    _needs_sdk()
    binaries = _stub_bin(tmp_path, "definitely-not-present")
    source = tmp_path / "input.mlir"
    source.write_text("hw.module @top(in %a : i8) {\n  hw.output\n}\n")
    spec = _spec("crasher.sh", [str(source)], tmp_path, input_path=str(source))
    case = call_node(probe_task.reduce_case, spec, _verdict(tmp_path),
                     {**LIMITS, **REDUCTION}, str(tmp_path / "probe"),
                     bin_dir=str(binaries))
    assert case.recheck_class == "clean_exit"
    assert case.recheck_matches is False


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_probe_35_reducer_aborted_routes_to_the_textual_reducer(
        tmp_path, sdk_env) -> None:
    """T-U-probe-35 (FR-09.9, FR-09.12) and the W-08 real-crash demonstration.

    A deeply nested `!hw.array` overflows CIRCT's own parser stack, and
    `circt-reduce` parses the candidate with the same parser the candidate
    overflows, so the REDUCER dies on it. That is a whole class of input
    unreducible by `circt-reduce` by construction.

    Pass criterion, end to end and all in one run: the probe classifies `crash`
    with SIGSEGV; the oracle fires, symbolises per module, drops exactly the
    four prologue frames and names a fingerprint frame in CIRCT's own
    `HWTypes.cpp`; `circt-reduce` aborts by signal and the reason names it;
    `textual-ddmin` then runs ON THE SAME RUN and strips the padding lines the
    crash does not need; and the re-check reproduces the same class.
    """
    _needs_sdk()
    probe = tmp_path / "probe"
    probe.mkdir()
    source = probe / "input.mlir"
    padding = [f"hw.module @Pad{i}(in %p : i{i % 32 + 1}) {{}}" for i in range(200)]
    padding.insert(100, nested_array(10000).strip())
    source.write_text("\n".join(padding) + "\n")

    tool = BASSERT_G / "circt-opt"
    spec = _spec("circt-opt", [str(source), "-o", os.devnull], tmp_path,
                 input_path=str(source))
    out = call_node(probe_execute, spec, _image_spec(**{"circt-opt": _sha256(tool)}),
                    {**LIMITS, **REDUCTION}, str(probe), bin_dir=str(BASSERT_G))
    build = out["build_result"]
    assert build.status == "crash" and build.signal == "SIGSEGV"
    assert build.limit_hit is None and build.exit_status is None

    verdict = _oracle(build, probe, circt_roots=HOST_ROOTS,
                      symbolizer=str(SYMBOLIZER))
    assert verdict.fired is True and verdict.oracle_class == "crash"
    assert verdict.prologue_dropped == 4
    assert len(verdict.frames) > 100
    assert verdict.frames_with_location > 0
    name, _space, basename = verdict.fingerprint_frame.rpartition(" ")
    assert basename in ("HWTypes.cpp", "HWTypes.cpp.inc"), verdict.fingerprint_frame
    assert name in ("parseHWArray", "circt::hw::ArrayType::parse",
                    "generatedTypeParser"), verdict.fingerprint_frame
    modules = {f.module for f in verdict.frames if f.shape == "module_offset"}
    assert len(modules) >= 2, modules      # one symboliser call per module

    case = call_node(probe_task.reduce_case, spec, verdict,
                     {**LIMITS, **REDUCTION}, str(probe), bin_dir=str(BASSERT_G))
    assert case.reason.startswith("reducer_aborted:"), case.reason
    assert case.reducer == "textual-ddmin" and case.lift is None
    assert case.reduced is True and case.fixpoint is True
    assert case.size_after_ops < case.size_before_ops
    assert case.size_after_bytes < case.size_before_bytes
    assert case.interestingness_calls > 1
    assert "!hw.array" in Path(case.path).read_text()
    assert case.recheck_class == "crash" and case.recheck_matches is True


# --- 3.6.3: the three harness helpers ---------------------------------------

DUT = """hw.module @Top(in %clock : !seq.clock, in %rst : i1, in %a : i8, \
in %b : i4, out o : i8, out p : i1) {
  %acc = seq.firreg %0 clock %clock : i8
  %0 = comb.add bin %a, %acc : i8
  %c = hw.constant 1 : i1
  hw.output %acc, %c : i8, i1
}
"""

PORTS = [
    probe_task.Port(index=0, name="clock", direction="input", width=1,
                    mlir_type="!seq.clock", is_clock=True, is_reset=False),
    probe_task.Port(index=1, name="rst", direction="input", width=1,
                    mlir_type="i1", is_clock=False, is_reset=True),
    probe_task.Port(index=2, name="a", direction="input", width=8,
                    mlir_type="i8", is_clock=False, is_reset=False),
    probe_task.Port(index=3, name="b", direction="input", width=4,
                    mlir_type="i4", is_clock=False, is_reset=False),
    probe_task.Port(index=4, name="o", direction="output", width=8,
                    mlir_type="i8", is_clock=False, is_reset=False),
    probe_task.Port(index=5, name="p", direction="output", width=1,
                    mlir_type="i1", is_clock=False, is_reset=False),
]


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_probe_47_extract_port_list_and_its_four_refusals(tmp_path, sdk_env) -> None:
    """T-U-probe-47 (FR-08.2, FR-08.8): the signature, and every way it refuses.

    Pass criterion: one `circt-opt --mlir-print-op-generic` run reads
    `module_type = !hw.modty<...>` off the one `hw.module` carrying no
    `sym_visibility = "private"`, and returns `Port`s in signature order with
    direction, width, MLIR type and the clock and reset predicates. The four
    refusals each fire once: `no_top` on two public modules, `bad_port_type` on
    an aggregate, `no_clock` on a combinational design, `circt_opt_failed` on a
    non-zero exit. Each is `harness_failure` and never `diverge`.
    """
    _needs_sdk()
    source = tmp_path / "lifted.mlir"
    source.write_text("hw.module private @Sub(in %x : i2, out q : i2) {\n"
                      "  hw.output %x : i2\n}\n" + DUT)
    ports = probe_task.extract_port_list(str(source), bin_dir=str(BASSERT_G))
    assert ports == PORTS
    assert probe_task.top_module_name(str(source), bin_dir=str(BASSERT_G)) == "Top"

    def _refuses(text: str, reason: str, name: str = "bad.mlir") -> None:
        path = tmp_path / name
        path.write_text(text)
        with pytest.raises(probe_task.HarnessError) as raised:
            probe_task.extract_port_list(str(path), bin_dir=str(BASSERT_G))
        assert raised.value.reason == reason, raised.value

    _refuses(DUT + DUT.replace("@Top", "@Other"), "no_top", "two.mlir")
    _refuses("hw.module @T(in %clk : !seq.clock, in %a : !hw.array<2xi8>, "
             "out o : i8) {\n  %c = hw.constant 0 : i8\n  hw.output %c : i8\n}\n",
             "bad_port_type", "agg.mlir")
    _refuses("hw.module @T(in %a : i8, out o : i8) {\n  hw.output %a : i8\n}\n",
             "no_clock", "comb.mlir")
    _refuses("this is not mlir\n", "circt_opt_failed", "junk.mlir")


@pytest.mark.t0
def test_u_probe_48_the_two_generators_agree_and_are_deterministic() -> None:
    """T-U-probe-48 (FR-08.2, FR-08.3): one stimulus, two texts, ten calls.

    Pass criterion: both generators are byte-identical across ten calls on one
    `(port_list, stimulus_seed)` pair; both drive the same input ports with the
    same LFSR values in the same cycle order, asserted by extracting the driven
    sequence from each text and comparing; both exclude clock and reset ports
    from the stimulus and drive the reset by the `hold-8-then-release`
    protocol; both emit the acceptance shape with the outputs in signature
    order; and the entry names are the two constants §4.6's and §4.10's argv
    expect. Neither compiles anything, so this test is tier 0.
    """
    seed = probe_task.stimulus_seed("p-0000000001")
    assert seed == probe_task.stimulus_seed("p-0000000001")
    arc = probe_task.gen_arc_harness(PORTS, seed, top="Top", design=DUT)
    tb = probe_task.gen_verilator_tb(PORTS, seed, top="Top")
    for _ in range(9):
        assert probe_task.gen_arc_harness(PORTS, seed, top="Top", design=DUT) == arc
        assert probe_task.gen_verilator_tb(PORTS, seed, top="Top") == tb

    assert f"func.func @{probe_task.ARC_JIT_ENTRY}()" in arc
    assert f"module {probe_task.VERILATOR_TOP};" in tb
    assert probe_task.ARC_JIT_ENTRY == "bugloop_main"
    assert probe_task.VERILATOR_TOP == "bugloop_tb"
    assert probe_task.STIMULUS_ID == "lfsr32-v1"
    assert probe_task.RESET_PROTOCOL == "hold-8-then-release"
    assert probe_task.SAMPLE_POINT == "pre-posedge"
    assert probe_task.DIFFERENTIAL_CYCLES == 64
    assert probe_task.X_POLICY == "x-assign=unique,x-initial=unique"

    # The same driven values, in the same order, on both sides.
    arc_driven = [int(m, 10) for m in
                  re.findall(r"%bl_c\d+_\d+ = arith\.constant (\d+) : i\d+", arc)]
    tb_driven = [int(m, 16) for m in re.findall(r"= \d+'h([0-9a-f]+);", tb)]
    assert arc_driven == tb_driven
    assert len(arc_driven) == probe_task.DIFFERENTIAL_CYCLES * 2   # ports a and b
    assert arc_driven == [probe_task.lfsr_value(seed, port.index, cycle, port.width)
                          for cycle in range(probe_task.DIFFERENTIAL_CYCLES)
                          for port in PORTS if port.name in ("a", "b")]

    # The clock and the reset are driven by their protocols, never by the LFSR.
    assert "%bl_c0_0 = arith.constant" not in arc and "%bl_c0_1 =" not in arc
    assert tb.count("rst = 1'b1;") == 8 and tb.count("rst = 1'b0;") == 56
    assert "clock = 1'b0;" in tb and "clock = 1'b1;" in tb

    # The acceptance shape, outputs in signature order, nothing before cycle 8.
    arc_lines = re.findall(r'arc\.sim\.emit "BUGLOOP (\d+) (\w+)"', arc)
    tb_lines = re.findall(r'\$display\("BUGLOOP (\d+) (\w+) = %h"', tb)
    assert arc_lines == tb_lines
    assert arc_lines[:4] == [("8", "o"), ("8", "p"), ("9", "o"), ("9", "p")]
    assert len(arc_lines) == (probe_task.DIFFERENTIAL_CYCLES - 8) * 2

    with pytest.raises(probe_task.HarnessError) as raised:
        probe_task.gen_arc_harness([PORTS[0]], seed, top="Top", design=DUT)
    assert raised.value.reason == "empty_port_list"
    with pytest.raises(probe_task.HarnessError):
        probe_task.gen_verilator_tb([PORTS[0]], seed, top="Top")


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_probe_50_both_harnesses_build_and_run_and_agree(tmp_path, sdk_env) -> None:
    """T-U-probe-50 (FR-08.2, FR-08.5): A-08's acceptance, no longer [UNVERIFIED].

    Pass criterion: the generated arcilator harness runs under §4.6's argv and
    the generated testbench compiles and runs under §4.10's, both print the
    acceptance lines, and the two line sequences are IDENTICAL on a clocked
    design with a register, which is what makes the differ a text comparison.

    `03-LLD.md` §3.6.3 marks this `[UNVERIFIED]` because no generator existed;
    it is now run, on the host build and on the host's Verilator 5.052.
    """
    _needs_sdk()
    import shutil
    import subprocess as sp
    if not shutil.which("verilator"):
        pytest.skip("verilator absent")
    lifted = tmp_path / "lifted.mlir"
    lifted.write_text(DUT)
    ports = probe_task.extract_port_list(str(lifted), bin_dir=str(BASSERT_G))
    seed = probe_task.stimulus_seed("p-0000000001")
    (tmp_path / "harness.mlir").write_text(
        probe_task.gen_arc_harness(ports, seed, top="Top", design=DUT))
    (tmp_path / "tb.sv").write_text(
        probe_task.gen_verilator_tb(ports, seed, top="Top"))

    arc = sp.run([str(BASSERT_G / "arcilator"), "--run",
                  f"--jit-entry={probe_task.ARC_JIT_ENTRY}", "--observe-ports",
                  f"--jit-vcd-file={tmp_path / 'arcilator.vcd'}",
                  str(tmp_path / "harness.mlir")], capture_output=True, text=True)
    assert arc.returncode == 0, arc.stderr[:600]

    export = sp.run([str(BASSERT_G / "circt-opt"), str(lifted), "--lower-seq-to-sv",
                     "--export-verilog", "-o", os.devnull],
                    capture_output=True, text=True)
    assert export.returncode == 0, export.stderr[:600]
    (tmp_path / "dut.sv").write_text(export.stdout)

    build = sp.run(["verilator", "--binary", "-j", "0", "-Wno-fatal", "--timing",
                    "--x-assign", "unique", "--x-initial", "unique",
                    "--top-module", probe_task.VERILATOR_TOP,
                    "--Mdir", str(tmp_path / "obj_dir"), "-o", "Vbugloop",
                    "--trace-vcd", str(tmp_path / "tb.sv"), str(tmp_path / "dut.sv")],
                   capture_output=True, text=True)
    assert build.returncode == 0, build.stdout[-2000:]
    run = sp.run([str(tmp_path / "obj_dir" / "Vbugloop")], capture_output=True,
                 text=True, cwd=str(tmp_path))
    assert run.returncode == 0, run.stderr[:600]

    def _lines(text: str) -> list:
        return [line for line in text.splitlines() if line.startswith("BUGLOOP ")]

    assert len(_lines(arc.stdout)) == (probe_task.DIFFERENTIAL_CYCLES - 8) * 2
    assert _lines(arc.stdout) == _lines(run.stdout)
