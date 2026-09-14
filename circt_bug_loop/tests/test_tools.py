"""The two agent-facing tools of `generate_task.py` (03-LLD.md 3.5)."""
import ast
import os
import subprocess
from pathlib import Path

import pytest

from chia.base.tools.ChiaTool import ChiaTool, ToolInfo

from circt_bug_loop import generate_task
from circt_bug_loop.generate_task import ProbeWriteTool, SourceReadTool

#: The commit §3.5's table verified its three argument vectors against.
MEASURED_COMMIT = "b792c772819d"
MEASURED_FILE = "lib/Dialect/HW/HWTypes.cpp"

#: `ChiaTool.__init__` constructs a `FastMCP`.
pytestmark = pytest.mark.filterwarnings(
    "ignore::pydantic_settings.exceptions.IncompleteFieldDefinitionWarning")


@pytest.fixture
def tool_servers(monkeypatch):
    """Construct `ChiaTool`s with no Ray actor behind them (04-Test-Plan.md 0.4)."""
    built = []

    def _post_init(self):
        built.append(self)
        self.hostname, self.port, self.node_id = "127.0.0.1", 9001, "node-fake"
        self.tool_info = ToolInfo(name=self.name, port=self.port,
                                  node_id=self.node_id)
        ChiaTool._tool_registry.append(self.tool_info)

    monkeypatch.setattr(ChiaTool, "__post_init__", _post_init)
    yield built
    for tool in built:
        if tool.tool_info in ChiaTool._tool_registry:
            ChiaTool._tool_registry.remove(tool.tool_info)


@pytest.fixture(scope="module")
def throwaway_repo(tmp_path_factory) -> tuple:
    """A two-file git repository, so the real git commands run with no clone."""
    root = tmp_path_factory.mktemp("source")
    (root / "lib" / "Dialect" / "HW").mkdir(parents=True)
    (root / "lib" / "Dialect" / "HW" / "HWTypes.cpp").write_text(
        "//===- HWTypes.cpp - HW types code defs ---===//\n"
        "Type parseHWArray(AsmParser &p) { return {}; }\n", encoding="utf-8")
    (root / "lib" / "Dialect" / "HW" / "CMakeLists.txt").write_text(
        "add_circt_dialect_library(CIRCTHW)\n", encoding="utf-8")
    (root / "README.md").write_text("circt\n", encoding="utf-8")
    for argv in (["init", "-q"],
                 ["add", "-A"],
                 ["-c", "user.name=bugloop", "-c", "user.email=b@l",
                  "commit", "-q", "-m", "one"]):
        subprocess.run(["git", "-C", str(root), *argv], check=True,
                       capture_output=True, text=True, timeout=60)
    head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True,
                          timeout=60).stdout.strip()
    return str(root), head


@pytest.fixture
def source_tool(tool_servers, throwaway_repo) -> SourceReadTool:
    """A `SourceReadTool` bound to the throwaway repository's one commit."""
    path, head = throwaway_repo
    return SourceReadTool(name="src_test", clone_path=path, run_commit=head,
                          cap_bytes=262144, task_options=None)


def _pinned_clone() -> str:
    """The blobless `llvm/circt` clone the measured pair needs, or ""."""
    for candidate in (os.environ.get("BUGLOOP_CORPUS_CLONE"),
                      "~/.cache/chia-pin-smoke/circt", "~/.cache/circt"):
        if not candidate:
            continue
        path = os.path.expanduser(candidate)
        try:
            subprocess.run(["git", "-C", path, "cat-file", "-e",
                            f"{MEASURED_COMMIT}^{{commit}}"], check=True,
                           capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        return path
    return ""


@pytest.mark.t0
def test_T_U_gen_13_the_tool_is_constructed_with_its_directory_bound(
        tool_servers, tmp_path):
    """T-U-gen-13 (FR-19.1): the probe directory is bound, not named by the agent."""
    tool = ProbeWriteTool(name="probe_x", probe_dir=str(tmp_path / "probes"))
    assert tool.probe_dir == os.path.realpath(str(tmp_path / "probes"))
    assert tool_servers == [tool], "the server is started exactly once"

    body = ast.parse(generate_task.__file__ and
                     Path(generate_task.__file__).read_text(encoding="utf-8"))
    init = [node for node in ast.walk(body)
            if isinstance(node, ast.ClassDef) and node.name == "ProbeWriteTool"]
    calls = [ast.unparse(node.func) for node in ast.walk(init[0])
             if isinstance(node, ast.Call)]
    assert calls.index("super().__init__") < calls.index("self.mcp.add_tool")
    assert calls.index("self.mcp.add_tool") < calls.index("super().__post_init__")


@pytest.mark.t0
@pytest.mark.parametrize("filename", [
    "sub/probe.mlir", "", ".", "..", "/etc/passwd", "../escape.mlir",
])
def test_T_U_gen_11_write_probe_refuses_every_name_that_is_not_bare(
        tool_servers, tmp_path, filename):
    """T-U-gen-11 (FR-06.8): a name with a path in it is refused and writes nothing."""
    probe_dir = tmp_path / "probes"
    tool = ProbeWriteTool(name="probe_x", probe_dir=str(probe_dir))
    before = sorted(probe_dir.iterdir())
    answer = tool.write_probe(filename, "firrtl.circuit\n")
    assert answer.startswith("Error:"), answer
    assert sorted(probe_dir.iterdir()) == before, "a rejected write wrote a file"


@pytest.mark.t0
def test_T_U_gen_11b_a_symlink_out_of_the_probe_directory_is_refused(
        tool_servers, tmp_path):
    """T-U-gen-11 (FR-06.8): a bare name whose realpath escapes is refused too."""
    probe_dir = tmp_path / "probes"
    probe_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (probe_dir / "escape.mlir").symlink_to(outside / "target.mlir")
    tool = ProbeWriteTool(name="probe_x", probe_dir=str(probe_dir))

    answer = tool.write_probe("escape.mlir", "hw.module @x() {}\n")
    assert answer.startswith("Error:") and "outside" in answer
    assert not (outside / "target.mlir").exists()


@pytest.mark.t0
def test_T_U_gen_12_a_second_write_of_one_name_is_byte_identical(
        tool_servers, tmp_path):
    """T-U-gen-12 (FR-06.8): rewriting is idempotent and no refusal ever raises."""
    tool = ProbeWriteTool(name="probe_x", probe_dir=str(tmp_path / "probes"))
    text = "hw.module @Top() {}\n"

    first = tool.write_probe("probe.mlir", text)
    second = tool.write_probe("probe.mlir", text)
    assert first == second
    assert Path(first).read_bytes() == text.encode("utf-8")
    # The refusal is a RESULT, not an exception.
    assert tool.write_probe("a/b", text).startswith("Error:")


@pytest.mark.t0
def test_T_U_gen_15_read_file_returns_the_text_at_the_run_commit(source_tool):
    """T-U-gen-15 (FR-04.4): `git show <commit>:<path>`, and `Error:` for a miss."""
    text = source_tool.read_file(MEASURED_FILE)
    assert text.startswith("//===- HWTypes.cpp")

    missing = source_tool.read_file("lib/Dialect/HW/NoSuch.cpp")
    assert missing.startswith("Error:") and "\n" not in missing.rstrip("\n")


@pytest.mark.t0
def test_T_U_gen_16_grep_is_a_fixed_string_search(source_tool):
    """T-U-gen-16 (FR-04.4): `-F`, so a metacharacter matches literally."""
    hits = source_tool.grep("parseHWArray", "lib/Dialect/HW")
    assert hits.splitlines()[0].startswith(f"{MEASURED_FILE}:")
    assert ":2:" in hits

    assert source_tool.grep("zzzNoSuchSymbol", "lib").startswith("Error:")
    # A regular expression is not one: `.*` matches only a literal `.*`.
    assert source_tool.grep("parseHW.*", "lib").startswith("Error:")


@pytest.mark.t0
def test_T_U_gen_17_list_dir_lists_one_directory(source_tool):
    """T-U-gen-17 (FR-04.4): `ls-tree --name-only`, and `''` is the root."""
    assert source_tool.list_dir("lib/Dialect/HW").split() == [
        "CMakeLists.txt", "HWTypes.cpp"]
    assert "README.md" in source_tool.list_dir("").split()
    assert source_tool.list_dir("lib/NoSuch").startswith("Error:")


@pytest.mark.t0
def test_T_U_gen_18_read_only_by_construction(source_tool, throwaway_repo,
                                              monkeypatch):
    """T-U-gen-18 (FR-04.4): three argument vectors, one commit."""
    path, head = throwaway_repo
    recorded = []
    original = SourceReadTool._git

    def _record(self, *args):
        recorded.append(["git", "-C", self.clone_path, *args])
        return original(self, *args)

    monkeypatch.setattr(SourceReadTool, "_git", _record)
    source_tool.read_file(MEASURED_FILE)
    source_tool.grep("parseHWArray", "lib/Dialect/HW")
    source_tool.list_dir("lib")

    assert recorded == [
        ["git", "-C", path, "show", f"{head}:{MEASURED_FILE}"],
        ["git", "-C", path, "grep", "-n", "-F", "--", "parseHWArray", head,
         "--", "lib/Dialect/HW"],
        ["git", "-C", path, "ls-tree", "--name-only", f"{head}:lib"]]
    assert all(any(head in token for token in vector)
               for vector in recorded), "the commit is bound"

    # Nothing outside the commit, refused before git ever sees it.
    for argument in ("/etc/passwd", "../outside", "lib/../../outside"):
        assert source_tool.read_file(argument).startswith("Error:")
        assert source_tool.list_dir(argument).startswith("Error:")

    source_tool.cap_bytes = 20
    capped = source_tool.read_file(MEASURED_FILE)
    assert "truncated at 20 bytes of" in capped


@pytest.mark.t0
def test_T_U_gen_18b_neither_tool_can_reach_a_shell():
    """T-U-gen-18 (NFR-03): no shell, no `BashTool`, in the module that owns them."""
    source = Path(generate_task.__file__).read_text(encoding="utf-8")
    assert "BashTool" not in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = ast.unparse(node.func)
            assert name not in ("os.system", "os.popen", "subprocess.Popen")
            for keyword in node.keywords:
                assert keyword.arg != "shell", "a shell in the read-only tool"


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_T_U_gen_15b_the_measured_pair_of_the_real_clone(tool_servers):
    """T-U-gen-15b (FR-04.4): §3.5's measured pair, against the real clone."""
    clone = _pinned_clone()
    if not clone:
        pytest.skip(f"no clone holding {MEASURED_COMMIT}; see "
                    "circt_bug_loop/tests/fixtures/corpus/README.md")
    tool = SourceReadTool(name="src_live", clone_path=clone,
                          run_commit=MEASURED_COMMIT, cap_bytes=262144)

    assert tool.read_file(MEASURED_FILE).startswith("//===- HWTypes.cpp")
    missing = tool.read_file("lib/Dialect/HW/NoSuch.cpp")
    assert missing.startswith("Error:") and "does not exist in" in missing
    hits = tool.grep("parseHWArray", "lib/Dialect/HW").splitlines()
    assert len(hits) == 2 and all(line.startswith("lib/Dialect/HW/") for line in hits)
    assert "HWTypes.cpp" in tool.list_dir("lib/Dialect/HW")
