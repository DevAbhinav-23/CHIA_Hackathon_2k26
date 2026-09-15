"""`04-Test-Plan.md` §1.21: the three functions proposed for `chia/chipyard/circt.py`."""
from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from circt_bug_loop import circt_core
from circt_bug_loop.circt_core import (CPU_HARD_MARGIN_SECONDS, circt_exec_probe,
                                       circt_reduce_run, circt_symbolize)
from circt_bug_loop.tests.conftest import call_node

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SMOKE = Path.home() / ".cache" / "chia-pin-smoke"
SDK = SMOKE / "circt-sdk"
SYMBOLIZER = SDK / "bin" / "llvm-symbolizer"

#: The one environment the SDK's own binaries need (`docs/HANDOFF.md`).
SDK_ENV = {"LD_LIBRARY_PATH": f"{SDK / 'lib'}:{SMOKE / 'shim'}"}

_LIMITS = dict(wall_seconds=30, address_space_bytes=4 * 1024 ** 3, cpu_seconds=20)


@pytest.fixture
def sdk_env(monkeypatch) -> None:
    """Put the SDK's own libraries on the loader path for a tier-1 test."""
    monkeypatch.setenv("LD_LIBRARY_PATH", SDK_ENV["LD_LIBRARY_PATH"])


def _code_of(name: str) -> str:
    """The source of one function of `circt_core`, its docstring removed."""
    tree = ast.parse(Path(circt_core.__file__).read_text())
    node, = [n for n in tree.body
             if isinstance(n, (ast.FunctionDef,)) and n.name == name]
    body = node.body[1:] if ast.get_docstring(node) else node.body
    return "\n".join(ast.unparse(stmt) for stmt in body)


def _ray_session() -> bool:
    """Whether this process is already inside a Ray session, without starting one."""
    ray = sys.modules.get("ray")
    return bool(ray is not None and ray.is_initialized())


def _needs(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"tier-1 resource absent: {path}")


def _run(tool: str, argv: list, tmp_path: Path, **over):
    """One `circt_exec_probe` call with the campaign's shape and small limits."""
    return call_node(circt_exec_probe, tool, argv, cwd=str(tmp_path),
                     **{**_LIMITS, **over})


def _rows(name: str) -> list:
    """The tab-separated symbolisation fixtures, comments and blanks dropped."""
    out = []
    for line in (FIXTURES / "symbolize" / name).read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            out.append(line.split("\t"))
    return out


def _stub(tmp_path: Path, name: str, body: str) -> str:
    """Write an executable /bin/sh stub and return its path."""
    path = tmp_path / name
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body))
    path.chmod(0o755)
    return str(path)


# --- circt_exec_probe -------------------------------------------------------

@pytest.mark.t0
def test_u_core_01_the_prlimit_prefix(tmp_path) -> None:
    """T-U-core-01 (FR-06.2): the argv, in order, long spellings, no --rss."""
    out = _run("/bin/true", ["--x"], tmp_path, address_space_bytes=1073741824,
               cpu_seconds=5, nofile=256)
    assert out["argv"] == ["prlimit", "--as=1073741824", "--cpu=5:10",
                           "--nofile=256", "--", "/bin/true", "--x"]
    assert CPU_HARD_MARGIN_SECONDS == 5
    assert "--rss" not in " ".join(out["argv"])
    assert "--cpu=5 " not in " ".join(out["argv"]) + " "


@pytest.mark.t0
def test_u_core_02_all_three_limits_reach_the_child(tmp_path) -> None:
    """T-U-core-02 (FR-06.2): the measured probe, through this function."""
    out = _run("/bin/sh", ["-c", "ulimit -v; ulimit -t; ulimit -n"], tmp_path,
               address_space_bytes=1073741824, cpu_seconds=5, nofile=256)
    assert out["stdout"].split() == ["1048576", "5", "256"]
    assert out["exit_status"] == 0 and out["signal"] is None


@pytest.mark.t0
def test_u_core_03_the_whole_process_group_dies(tmp_path) -> None:
    """T-U-core-03 (FR-06.3): no descendant of a timed-out probe survives."""
    out = _run("/bin/sh", ["-c", "sleep 30 & echo $!; sleep 30"], tmp_path,
               wall_seconds=1)
    grandchild = int(out["stdout"].split()[0])
    assert out["limit_hit"] == "wall"
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(grandchild, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"grandchild {grandchild} outlived its process group")


@pytest.mark.t0
def test_u_core_04_the_signal_is_a_field_of_its_own(tmp_path) -> None:
    """T-U-core-04 (FR-06.4): SIGABRT, a null exit status, and never 134."""
    out = _run(sys.executable,
               ["-c", "import os, signal; os.kill(os.getpid(), signal.SIGABRT)"],
               tmp_path)
    assert out["signal"] == "SIGABRT"
    assert out["exit_status"] is None
    code = _code_of("circt_exec_probe")
    for needed in ("os.fork()", "os.setsid()", "os.execvp(", "os.wait4("):
        assert needed in code + _code_of("_reap"), needed
    assert "subprocess.Popen" not in code


@pytest.mark.t0
def test_u_core_05_output_is_capped_per_call(tmp_path) -> None:
    """T-U-core-05 (FR-06.4): the byte cap and the `truncated` flag."""
    argv = ["-c", "print('a' * 100000)"]
    capped = _run(sys.executable, argv, tmp_path, output_byte_cap=1000)
    assert len(capped["stdout"]) == 1000 and capped["truncated"] is True
    whole = _run(sys.executable, argv, tmp_path, output_byte_cap=1_000_000)
    assert len(whole["stdout"]) == 100001 and whole["truncated"] is False


@pytest.mark.t0
def test_u_core_06_missing_tool_raises_and_nothing_else_does(tmp_path) -> None:
    """T-U-core-06 (FR-06.1): FileNotFoundError, and every other failure a field."""
    with pytest.raises(FileNotFoundError):
        _run(str(tmp_path / "no-such-tool"), [], tmp_path)
    # 126, not 127: the fork execs `prlimit`, which starts and then fails to exec a file it may not run, and 126 is its own "found but not executable".
    not_executable = tmp_path / "plain.txt"
    not_executable.write_text("not a program\n")
    assert _run(str(not_executable), [], tmp_path)["exit_status"] == 126


@pytest.mark.t0
def test_u_core_07_no_shell_and_no_command_string() -> None:
    """T-U-core-07 (FR-06.1): no `shell=True` and no constructed command string."""
    tree = ast.parse(Path(circt_core.__file__).read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        assert not any(kw.arg == "shell" for kw in node.keywords), ast.dump(node)
        target = getattr(node.func, "attr", "")
        if target in ("run", "Popen", "call", "check_output"):
            assert not isinstance(node.args[0], ast.Constant), ast.dump(node)


# --- circt_reduce_run -------------------------------------------------------

@pytest.mark.t0
def test_u_core_08_the_reducer_argv(tmp_path, monkeypatch) -> None:
    """T-U-core-08 (FR-09.2): --keep-best explicit, --test-must-fail never."""
    seen, signalled = [], []

    class _Popen:
        returncode = 0
        pid = os.getpid()                   # the reducer's `finally` signals this group

        def __init__(self, argv, **kwargs):
            seen.append(argv)
            assert kwargs["start_new_session"] is True

        def communicate(self, timeout=None):
            return (b"", None)

    monkeypatch.setattr(circt_core.subprocess, "Popen", _Popen)
    monkeypatch.setattr(circt_core, "_killpg",
                        lambda pgid, *sig: signalled.append(pgid))
    call_node(circt_reduce_run, "in.mlir", "interesting.sh", "out.mlir",
              binary="/workspace/circt/build/bin/circt-reduce")
    assert signalled == [os.getpid()], "the stub is what keeps the suite alive here"
    assert seen == [["/workspace/circt/build/bin/circt-reduce", "in.mlir",
                     "--test=interesting.sh", "--keep-best", "-o", "out.mlir"]]
    assert not any(a.startswith("--test-arg") for a in seen[0])
    assert "--test-must-fail" not in seen[0]


@pytest.mark.t0
def test_u_core_09_output_valid_is_computed_after_the_exit(tmp_path) -> None:
    """T-U-core-09 (FR-09.4): the post-exit validation of `-o`."""
    empty = FIXTURES / "reducer" / "truncated" / "reduced.mlir"
    assert empty.read_bytes() == b""
    out = call_node(circt_reduce_run, "in.mlir", "t.sh", str(empty),
                    binary="/bin/true")
    assert out["output_valid"] is False and out["success"] is True

    late = _stub(tmp_path, "late-reduce.sh", """
        sleep 0.3
        printf 'reduced\\n' > "$5"
    """)
    target = tmp_path / "reduced.mlir"
    out = call_node(circt_reduce_run, "in.mlir", "t.sh", str(target), binary=late)
    assert out["output_valid"] is True and out["wall_seconds"] >= 0.3


# --- circt_symbolize --------------------------------------------------------

@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_core_10_one_call_per_module_with_offsets(tmp_path, sdk_env) -> None:
    """T-U-core-10 (FR-07.4): grouped by module, offsets on stdin, JSON out."""
    _needs(SYMBOLIZER)
    rows = _rows("module_offsets.txt")
    frames = [{"index": i, "address": "0x0", "shape": "module_offset",
               "module": str(SMOKE / "circt-sdk" / rel), "offset": offset,
               "function": "", "file": "", "line": 0}
              for i, (_, rel, offset, *_rest) in enumerate(rows)]

    log = tmp_path / "calls.log"
    wrapper = _stub(tmp_path, "sym-wrapper.sh", f"""
        printf '%s\\n' "$*" >> {log}
        cat >> {log}
        printf -- '---\\n' >> {log}
        exec {SYMBOLIZER} "$@" < /dev/null
    """)
    # The wrapper cannot both tee stdin and pass it on.
    call_node(circt_symbolize, frames, symbolizer=wrapper)
    calls = log.read_text().split("---\n")[:-1]
    modules = {row[1] for row in rows}
    assert len(calls) == len(modules), calls
    for call in calls:
        header, *offsets = [line for line in call.splitlines() if line]
        module = header.split("--obj=")[1].split()[0]
        assert "--demangle" in header and "--output-style=JSON" in header
        assert set(offsets) == {r[2] for r in rows
                                if str(SMOKE / "circt-sdk" / r[1]) == module}

    out = call_node(circt_symbolize, frames, symbolizer=str(SYMBOLIZER))
    for frame, row in zip(out, rows):
        assert frame["function"] == row[3], row
        assert frame["file"] == (str(SMOKE / row[4]) if row[4] else "")
        assert frame["line"] == int(row[5])

    runtime = [dict(f, offset=a) for f, a in zip(frames, ("0x00007fe0485611b5",))]
    stale = call_node(circt_symbolize, runtime, symbolizer=str(SYMBOLIZER),
                      tool_path=str(SMOKE / "bassert_g" / "bin" / "circt-opt"))
    assert all(f["function"] == "" and f["line"] == 0 for f in stale)


@pytest.mark.t0
def test_u_core_11_an_unparseable_line_is_unresolved(tmp_path) -> None:
    """T-U-core-11 (FR-07.4): garbage on stdout yields a record, never a raise."""
    frames = [{"index": 0, "address": "0x1", "shape": "module_offset",
               "module": "/lib/libX.so", "offset": "0x10",
               "function": "", "file": "", "line": 0}]
    garbage = _stub(tmp_path, "garbage.sh", """
        cat > /dev/null
        printf 'not json at all\\n'
    """)
    for symbolizer in (garbage, str(tmp_path / "absent")):
        out = call_node(circt_symbolize, frames, symbolizer=symbolizer)
        assert out[0]["function"] == "" and out[0]["file"] == ""
        assert out[0]["line"] == 0 and out[0]["in_circt_object"] is False


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_core_12_a_circt_frame_names_a_file_and_a_line(sdk_env) -> None:
    """T-U-core-12 (FR-07.4): `bassert_g` under -gline-tables-only."""
    _needs(SYMBOLIZER)
    (_, rel, offset, function, file_rel, line), = _rows("bassert_g_addrs.txt")
    module = SMOKE / "bassert_g" / rel
    _needs(module)
    frame = {"index": 0, "address": "0x0", "shape": "module_offset",
             "module": str(module), "offset": offset,
             "function": "", "file": "", "line": 0}
    out, = call_node(circt_symbolize, [frame], symbolizer=str(SYMBOLIZER),
                     tool_path=str(module))
    assert out["function"] == function
    assert out["file"] == str(SMOKE / file_rel)
    assert out["line"] == int(line)
    assert out["in_circt_object"] is True


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_u_core_13_without_line_tables_the_location_is_lost(sdk_env) -> None:
    """T-U-core-13 (FR-07.4): the same address in a build without -g."""
    _needs(SYMBOLIZER)
    (_, rel, offset, function, file_rel, line), = _rows("bassert_addrs.txt")
    module = SMOKE / "bassert" / rel
    _needs(module)
    frame = {"index": 0, "address": "0x0", "shape": "module_offset",
             "module": str(module), "offset": offset,
             "function": "", "file": "", "line": 0}
    out, = call_node(circt_symbolize, [frame], symbolizer=str(SYMBOLIZER))
    assert out["function"] == function
    assert out["file"] == "" and out["line"] == 0

    g_module = SMOKE / "bassert_g" / rel
    _needs(g_module)
    short = subprocess.run([str(SYMBOLIZER), f"--obj={g_module}",
                            "--functions=short", "--demangle",
                            "--output-style=JSON"],
                           input=f"{offset}\n", capture_output=True, text=True,
                           env={**os.environ, **SDK_ENV})
    symbol = json.loads(short.stdout.splitlines()[0])["Symbol"][0]
    assert symbol["FunctionName"] == ""
    argv = _code_of("_symbolize_module")
    assert "--functions" not in argv and "--inlines" not in argv


# --- the derived figures ----------------------------------------------------

@pytest.mark.t0
def test_u_core_14_wait4_supplies_cpu_and_peak_rss(tmp_path) -> None:
    """T-U-core-14 (FR-06.4): ru_utime + ru_stime, and ru_maxrss * 1024."""
    out = _run(sys.executable, ["-c", "b = bytearray(300 * 1024 * 1024); b[0] = 1"],
               tmp_path)
    assert 200 * 1024 ** 2 < out["peak_rss_bytes"] < 700 * 1024 ** 2
    busy = _run(sys.executable,
                ["-c", "import time\nt=time.time()\nwhile time.time()-t<0.4: pass"],
                tmp_path)
    assert busy["cpu_seconds"] >= 0.2
    assert "ru_maxrss * 1024" in Path(circt_core.__file__).read_text()


@pytest.mark.t0
def test_u_core_15_limit_hit_against_measured_prlimit(tmp_path) -> None:
    """T-U-core-15 (FR-06.2): the three rules and the controls."""
    spin = _run(sys.executable, ["-c", "while True: pass"], tmp_path,
                cpu_seconds=1, wall_seconds=60)
    assert spin["signal"] == "SIGXCPU" and spin["limit_hit"] == "cpu"
    assert spin["exit_status"] is None

    control = subprocess.run(["prlimit", "--cpu=1", "--", sys.executable,
                              "-c", "while True: pass"])
    assert control.returncode == -signal.SIGKILL

    hog = _run(sys.executable, ["-c", "b = bytearray(500 * 1024 * 1024)"],
               tmp_path, address_space_bytes=104857600)
    assert hog["signal"] is None and hog["exit_status"] == 1
    assert "MemoryError" in hog["stderr"]
    assert hog["limit_hit"] == "address_space"

    clean = _run("/bin/true", [], tmp_path)
    assert clean["limit_hit"] is None


@pytest.mark.t0
def test_u_core_16_the_worker_identity_fields(tmp_path) -> None:
    """T-U-core-16 (FR-13.2): hostname, node id and child pid on every call."""
    before = _ray_session()
    out = _run("/bin/true", [], tmp_path)
    assert out["worker_hostname"]
    assert out["child_pid"] > 0
    # Empty exactly when there is no session to ask, and asking started none.
    assert (out["worker_node_id"] == "") is not before
    assert _ray_session() is before
    assert "ray.get_runtime_context().get_node_id()" in \
        Path(circt_core.__file__).read_text()


@pytest.mark.t0
def test_u_core_17_an_attributed_frame_is_not_symbolised(tmp_path) -> None:
    """T-U-core-17 (FR-07.4): both shapes, and `in_circt_object`."""
    tool = "/workspace/circt/build/bin/circt-opt"
    frames = [
        {"index": 0, "address": "0x1", "shape": "attributed", "module": "",
         "offset": "", "function": "parseHWArray(mlir::AsmParser&)",
         "file": "/workspace/circt/lib/Dialect/HW/HWTypes.cpp", "line": 723},
        {"index": 1, "address": "0x2", "shape": "attributed", "module": "",
         "offset": "", "function": "generatedTypeParser",
         "file": "/workspace/circt/build/include/circt/HWTypes.cpp.inc", "line": 34},
        {"index": 2, "address": "0x3", "shape": "attributed", "module": "",
         "offset": "", "function": "SignalHandler(int)",
         "file": "Signals.cpp", "line": 0},
        {"index": 3, "address": "0x4", "shape": "module_offset", "module": tool,
         "offset": "0x10", "function": "", "file": "", "line": 0},
        {"index": 4, "address": "0x5", "shape": "module_offset",
         "module": "/workspace/circt/build/lib/libCIRCTHW.so.20",
         "offset": "0x20", "function": "", "file": "", "line": 0},
        {"index": 5, "address": "0x6", "shape": "module_offset",
         "module": "/opt/circt-sdk/lib/libMLIRAsmParser.so",
         "offset": "0x30", "function": "", "file": "", "line": 0},
    ]
    out = call_node(circt_symbolize, frames, tool_path=tool,
                    symbolizer=str(tmp_path / "absent"))
    for before, after in zip(frames[:3], out[:3]):
        assert (after["function"], after["file"], after["line"]) == \
            (before["function"], before["file"], before["line"])
    assert [f["in_circt_object"] for f in out] == \
        [True, True, False, True, True, False]


@pytest.mark.t0
def test_u_core_18_the_upstream_copy_has_not_drifted() -> None:
    """T-U-core-18 (FR-19.2): `upstream/` carries the same code that runs here."""
    here = Path(circt_core.__file__).resolve()
    upstream = here.parents[1] / "upstream" / "chia-chipyard-circt-additions.py"
    if not upstream.is_file():
        pytest.skip("no upstream/ beside the flow: this is the published tree, "
                    "where the code lives in chia/chipyard/circt.py instead")

    def _body(path: Path) -> str:
        text = path.read_text()
        tree = ast.parse(text)
        first = tree.body[1]          # everything after the module docstring
        return "\n".join(text.splitlines()[first.lineno - 1:]).rstrip() + "\n"

    assert _body(upstream) == _body(here)
    assert "circt_bug_loop" not in _body(upstream)
