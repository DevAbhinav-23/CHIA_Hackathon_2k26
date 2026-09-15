"""The repository's own layout properties (`03-LLD.md` §1.3)."""
import ast
import importlib
import inspect
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from circt_bug_loop import bug_loop
from circt_bug_loop.contract import schema

# Each test carries its own tier marker rather than the module carrying one.

FLOW = Path(bug_loop.FLOW_DIR)
REPO = FLOW.parent
TESTS = FLOW / "tests"
SYNC = REPO / "upstream" / "sync-to-chia.sh"
CHIA_STUB = TESTS / "fixtures" / "layout" / "chia_stub"

#: §1.3's NINETEEN source modules that hold logic, each with its test module.
SOURCE_MODULES = {
    "bug_loop.py": "test_bug_loop.py", "contract/schema.py": "test_schema.py",
    "corpus.py": "test_corpus.py", "pin_select.py": "test_pin_select.py",
    "generate_task.py": "test_generate_task.py", "llm.py": "test_llm.py",
    "mutator_synth.py": "test_mutator_synth.py",
    "mutators/__init__.py": "test_mutators.py", "probe_task.py": "test_probe_task.py",
    "ddmin.py": "test_ddmin.py", "triage_task.py": "test_triage_task.py",
    "repair_adapter.py": "test_repair_adapter.py", "gate.py": "test_gate.py",
    "approve.py": "test_approve.py", "budget.py": "test_budget.py",
    "ledger.py": "test_ledger.py", "feedback.py": "test_feedback.py",
    "store.py": "test_store.py", "results.py": "test_results.py"}

#: §1.3's one source module with no test module of its own.
NO_TEST_MODULES = ("contract/__init__.py", "__init__.py")

#: §1.3's two structural test modules.
STRUCTURAL_TESTS = ("test_layout.py", "test_fixtures.py", "test_integration.py",
                    "test_system.py")

#: §1.3's exemption list, compared for EQUALITY so neither document can grow one the other does not.
EXEMPT_TESTS = ("test_image.py", "test_prompts.py", "test_cluster_yaml.py",
                "test_submit.py", "test_budget_yaml.py", "test_tools.py",
                "test_upstream_patches.py")

#: The one test module neither §1.3 nor its exemption list names (errata row 16).
EXTRA_MODULES = {"circt_core.py": "test_circt_core.py"}

#: `02-HLD.md` §1.2's supply half, module by module.
SUPPLY_HALF = ("corpus.py", "pin_select.py", "generate_task.py", "feedback.py",
               "budget.py", "ledger.py", "mutator_synth.py", "mutators/__init__.py")

#: The one exemption from that rule, by module and by name.
SEAM_EXEMPT = {"ledger.py": ("BudgetLedger", "LoopStore")}

#: §14.5's six apparatus modules, and its three exempt by name.
APPARATUS = ("probe_task.py", "triage_task.py", "repair_adapter.py", "gate.py",
             "store.py", "ddmin.py")
ARM_EXEMPT = ("ledger.py", "results.py", "contract/schema.py")

#: §3.2's node table: every node the flow ships, with the placement its row gives it.
NODES = {
    "corpus.build_corpus": None, "corpus.resolve_sites": None,
    "pin_select.select_release_pinned_main": None,
    # Head-side since the campaign-2 gate deadlock: A3 runs no CIRCT tool.
    "generate_task.generate_seeded": None,
    "generate_task.generate_mutation": {"circt": 1},
    "llm.llm_turn": {"llm": 1.0},
    "feedback.build_feedback": None, "budget.load_budget": None,
    "ledger.accrue": None, "mutator_synth.synthesise_mutators": None,
    # Head-side since W-20b.
    "bug_loop.build_image": None,
    "probe_task.probe_execute": {"circt": 1},
    "probe_task.oracle_primary": {"circt": 1},
    "probe_task.oracle_differential": {"circt": 1},
    "probe_task.reduce_case": {"circt": 1},
    "triage_task.issue_mirror_refresh": None,
    "triage_task.dedup_and_screen": None,
    "triage_task.triage_report": {"circt": 1},
    "repair_adapter.repair_adapt": {"repair": 1},
    "gate.gate_decide": None, "gate.gate_rerun": {"circt": 1},
    "gate.gate_validate": {"circt": 1},
    "store.artefact_write": None, "results.render_results": None}

#: §3.10's three, which are CHIA's file and not the example's.
CORE_NODES = ("circt_core.circt_exec_probe", "circt_core.circt_reduce_run",
              "circt_core.circt_symbolize")

#: §0's dependency rule: the standard library, plus these and nothing else.
THIRD_PARTY = {"yaml", "ray", "chia"}
#: CHIA's own two example modules.
CHIA_EXAMPLE_MODULES = {"issue_task", "circt_util"}


def flow_files() -> list:
    """Every Python module of the flow, in a stable order."""
    return sorted(list(FLOW.glob("*.py")) + list(FLOW.glob("contract/*.py"))
                  + list(FLOW.glob("mutators/*.py")))


def parse(path: Path) -> ast.Module:
    """One module's syntax tree."""
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def node_object(dotted: str):
    """The decorated node object named by `<module>.<callable>`."""
    module, name = dotted.split(".")
    return getattr(importlib.import_module(f"circt_bug_loop.{module}"), name)


@pytest.mark.t0
def test_T_U_layout_01_mapping():
    """T-U-layout-01 (FR-19.5): every source module that holds logic has its test module."""
    for source, test in SOURCE_MODULES.items():
        assert (FLOW / source).is_file(), source
        assert (TESTS / test).is_file(), test
    for source in NO_TEST_MODULES:
        assert (FLOW / source).is_file(), source
    assert set(flow_files()) == {
        FLOW / name for name in
        list(SOURCE_MODULES) + list(NO_TEST_MODULES) + ["circt_core.py"]}


@pytest.mark.t0
def test_T_U_layout_01_exemptions():
    """T-U-layout-01 (NFR-12): the exemption list equals the six 1.3 names."""
    assert set(EXEMPT_TESTS) == {
        "test_image.py", "test_prompts.py", "test_cluster_yaml.py",
        "test_submit.py", "test_budget_yaml.py", "test_tools.py",
        "test_upstream_patches.py"}
    for artefact, test in (
            (REPO / "upstream" / "dockerfiles" / "ChiaCirctAssertDockerfile", "test_image.py"),
            (FLOW / "prompts", "test_prompts.py"),
            (FLOW / "cluster_single.yaml", "test_cluster_yaml.py"),
            (FLOW / "bug_loop_submit.sh", "test_submit.py"),
            (FLOW / "budget.yaml", "test_budget_yaml.py"),
            (REPO / "upstream" / "vertex-usage.patch", "test_upstream_patches.py")):
        assert artefact.exists(), str(artefact)
        assert test in EXEMPT_TESTS


@pytest.mark.t0
def test_T_U_layout_01_twenty_five():
    """T-U-layout-01 (FR-19.5): the test directory holds exactly the expected modules."""
    present = {path.name for path in TESTS.glob("test_*.py")}
    expected = (set(SOURCE_MODULES.values()) | set(STRUCTURAL_TESTS)
                | set(EXEMPT_TESTS) | set(EXTRA_MODULES.values()))
    assert present == expected


@pytest.mark.t0
def test_T_U_layout_01_seam():
    """T-U-layout-01 (FR-16.1): the supply half imports no `store.py` name."""
    for name in SUPPLY_HALF:
        imported = [alias.name
                    for node in ast.walk(parse(FLOW / name))
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").endswith("store")
                    for alias in node.names]
        imported += [alias.name.split(".")[-1]
                     for node in ast.walk(parse(FLOW / name))
                     if isinstance(node, ast.Import)
                     for alias in node.names if alias.name.endswith("store")]
        allowed = SEAM_EXEMPT.get(name, ())
        assert set(imported) <= set(allowed), (name, imported)


def _branch_operands(node: ast.AST) -> list:
    """The expressions §14.5 calls a branch's operand, and no others."""
    if isinstance(node, ast.If):
        return [node.test]
    if isinstance(node, ast.Compare):
        return [node.left, *node.comparators]
    if isinstance(node, ast.Match):
        return [node.subject]
    if isinstance(node, ast.Subscript):
        return [node.slice]
    return []


def arm_branches(path: Path) -> list:
    """Every line of *path* that branches on a name or attribute `arm`."""
    found = []
    for node in ast.walk(parse(path)):
        for operand in _branch_operands(node):
            for sub in ast.walk(operand):
                name = (sub.id if isinstance(sub, ast.Name)
                        else sub.attr if isinstance(sub, ast.Attribute) else "")
                if name == "arm" or name.endswith("_arm"):
                    found.append(node.lineno)
    return sorted(set(found))


@pytest.mark.t0
def test_T_U_layout_02():
    """T-U-layout-02 (FR-18.1): the apparatus carries `arm` and does not branch on it."""
    for name in APPARATUS:
        assert arm_branches(FLOW / name) == [], name
    assert set(ARM_EXEMPT) == {"ledger.py", "results.py", "contract/schema.py"}
    assert arm_branches(FLOW / "ledger.py"), "the exemption is used by ledger.py"
    assert arm_branches(FLOW / "results.py"), "the exemption is used by results.py"


@pytest.mark.t0
def test_T_U_layout_02_probe_task():
    """T-U-layout-02 (FR-18.1): the walk over `probe_task.py` itself."""
    assert arm_branches(FLOW / "probe_task.py") == []
    source = (FLOW / "probe_task.py").read_text(encoding="utf-8")
    assert "arm=spec.arm" in source, "the arm is carried, which is the rule"


def paragraphs(doc: str) -> list:
    """The three named paragraphs a node's docstring must carry, in order."""
    return [word for word in ("Returns:", "Worker:", "Raises:") if word in (doc or "")]


@pytest.mark.t0
def test_T_U_layout_03_nodes():
    """T-U-layout-03 (FR-19.4): every node's docstring has the three paragraphs."""
    for dotted in list(NODES) + list(CORE_NODES):
        doc = inspect.getdoc(node_object(dotted))
        assert paragraphs(doc) == ["Returns:", "Worker:", "Raises:"], dotted
        assert doc.splitlines()[0].endswith("."), dotted


@pytest.mark.t0
def test_T_U_layout_03_tools():
    """T-U-layout-03 (FR-19.4): each tool method states an action, an argument and a failure."""
    from circt_bug_loop import generate_task

    for tool in (generate_task.SourceReadTool, generate_task.ProbeWriteTool):
        methods = [(name, fn) for name, fn in vars(tool).items()
                   if callable(fn) and not name.startswith("_")]
        assert methods, tool.__name__
        for name, fn in methods:
            doc = inspect.getdoc(fn) or ""
            assert doc.splitlines()[0].endswith("."), name
            arguments = list(inspect.signature(fn).parameters)[1:]
            # ONE argument, which is the rule as the plan states it.
            assert any(argument in doc for argument in arguments), name
            assert "Error" in doc, name


@pytest.mark.t0
def test_T_U_layout_04():
    """T-U-layout-04 (FR-19.1): no bare `ray.remote`, and every tool is a `ChiaTool`."""
    for path in flow_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Attribute) and node.attr == "remote":
                assert not (isinstance(node.value, ast.Name)
                            and node.value.id == "ray"), f"{path}:{node.lineno}"
    tools = [cls for path in flow_files() for cls in parse(path).body
             if isinstance(cls, ast.ClassDef) and cls.name.endswith("Tool")
             and not cls.name.endswith("ChiaTool")]
    assert [cls.name for cls in tools] == ["SourceReadTool", "ProbeWriteTool"]
    for cls in tools:
        assert [getattr(base, "id", "") for base in cls.bases] == ["ChiaTool"], cls.name


@pytest.mark.t0
def test_T_U_layout_05():
    """T-U-layout-05 (FR-19.8): no dependency outside CHIA's own and the stdlib."""
    allowed = (THIRD_PARTY | CHIA_EXAMPLE_MODULES | {"circt_bug_loop"}
               | set(sys.stdlib_module_names))
    for path in flow_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                assert name in allowed, f"{path}:{node.lineno}: {name}"


@pytest.mark.t0
def test_T_U_layout_06():
    """T-U-layout-06 (FR-12.11): every node's `_chia_options`."""
    for dotted, resources in NODES.items():
        options = node_object(dotted)._chia_options
        assert options.get("max_retries") == 0, dotted
        assert options.get("resources") == resources, dotted
    assert [d for d, r in NODES.items() if r == {"repair": 1}] == [
        "repair_adapter.repair_adapt"]
    assert NODES["gate.gate_decide"] is None
    for dotted in CORE_NODES:
        options = node_object(dotted)._chia_options
        assert options == {"resources": {"circt": 1}}, dotted


def returns_counters(dotted: str) -> bool:
    """Whether this node's documented **Returns** paragraph names `counters`."""
    return "counters" in (inspect.getdoc(node_object(dotted)) or "")


@pytest.mark.t0
def test_T_U_layout_07():
    """T-U-layout-07 (FR-17.4): every node returns a `CounterBlock`."""
    missing = [dotted for dotted in NODES if not returns_counters(dotted)]
    assert missing == []
    bare = [dotted for dotted in NODES
            if inspect.signature(
                getattr(node_object(dotted), "_chia_original",
                        node_object(dotted))).return_annotation != "dict"]
    assert bare == []


@pytest.mark.t0
def test_T_U_layout_07_stages():
    """T-U-layout-07 (FR-17.4): `CounterBlock.stage` is drawn from `_COUNTER_STAGES`."""
    assert set(schema._COUNTER_STAGES) == set(schema._STAGE_IDS) | {
        "image", "corpus", "pin", "mirror", "synthesis",
        # Five added at the join (W-17).
        "feedback", "budget", "ledger", "artefact", "results"}
    log = bug_loop.CounterLog("run", None)
    # "feedback" was the invented name here until the join made it a real stage (errata row 22).
    with pytest.raises(ValueError):
        log.record("seeded", schema.CounterBlock(stage="stage_9", started=1,
                                                 completed=1, failed=0, seconds=0.0))


def interlock_setters(path: Path) -> list:
    """Every line of a test module that puts the interlock into the environment."""
    receivers = {"setenv": "monkeypatch", "setdefault": "environ", "putenv": "os"}
    found = []
    for node in ast.walk(parse(path)):
        name_expr = None
        if isinstance(node, ast.Call):
            called = getattr(node.func, "attr", "")
            if (called in receivers and node.args
                    and ast.unparse(node.func.value).endswith(receivers[called])):
                name_expr = node.args[0]
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Subscript)
                        and getattr(target.value, "attr", "") == "environ"):
                    name_expr = target.slice
        if name_expr is None:
            continue
        if isinstance(name_expr, ast.Constant):
            if name_expr.value == bug_loop.LIVE_MODEL_ENV:
                found.append(node.lineno)
        elif isinstance(name_expr, (ast.Name, ast.Attribute)):
            resolved = getattr(name_expr, "id", getattr(name_expr, "attr", ""))
            if resolved.endswith("LIVE_MODEL_ENV"):
                found.append(node.lineno)
        else:
            found.append(node.lineno)
    return sorted(set(found))


@pytest.mark.t0
def test_T_U_layout_08_no_test_sets_it():
    """T-U-layout-08 (NFR-06): no test module puts the interlock in the environment."""
    setters = {path.name: interlock_setters(path)
               for path in sorted(TESTS.glob("test_*.py"))}
    assert {name: lines for name, lines in setters.items() if lines} == {}


@pytest.mark.t0
def test_T_U_layout_08_one_construction_path():
    """T-U-layout-08 (NFR-06): two construction paths, both behind the same refusal."""
    owners = []
    for path in flow_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, (ast.Name, ast.Attribute)):
                if getattr(node, "id", getattr(node, "attr", "")) == "VertexGeminiLLM":
                    owners.append(path.name)
    assert owners == ["llm.py"] * len(owners) and owners

    source = (FLOW / "llm.py").read_text(encoding="utf-8")
    build_llm = source.split("def build_llm")[1].split("\ndef ")[0]
    assert "VertexGeminiLLM" in build_llm
    assert "require_live_model" in build_llm

    patch = (REPO / "upstream" / "issue_task-vertex-branch.patch").read_text(encoding="utf-8")
    assert patch.count("VertexGeminiLLM") >= 1
    repair = (FLOW / "repair_adapter.py").read_text(encoding="utf-8")
    assert "require_live_model" in repair
    assert "VertexGeminiLLM" not in repair


@pytest.mark.t0
def test_T_U_layout_08_conftest_refuses():
    """T-U-layout-08 (NFR-08): `conftest.py`'s own fixture, both halves of §0.5."""
    from circt_bug_loop.tests import conftest

    assert bug_loop.LIVE_MODEL_ENV not in os.environ
    assert conftest._INTERLOCK == bug_loop.LIVE_MODEL_ENV

    values = conftest.known_values()
    assert set(values) == {"GITHUB_TOKEN", "GEMINI_API_KEY", "GOOGLE_API_KEY"}
    assert os.environ["GEMINI_API_KEY"] == values["GEMINI_API_KEY"]
    # Each has the SHAPE the secret grep looks for and authenticates against nothing.
    assert values["GITHUB_TOKEN"].startswith("ghp_") and len(values["GITHUB_TOKEN"]) == 40
    assert values["GEMINI_API_KEY"].startswith("AQ.") and len(values["GEMINI_API_KEY"]) == 35
    assert values["GOOGLE_API_KEY"].startswith("AIza") and len(values["GOOGLE_API_KEY"]) == 39
    assert all(set(value[4:]) <= {"0"} for value in values.values())


@pytest.mark.t0
def test_T_U_layout_09_no_module_walks_up():
    """T-U-layout-09 (FR-19.2): no flow module walks past its own directory."""
    for path in flow_files():
        for node in ast.walk(parse(path)):
            if isinstance(node, ast.Attribute) and node.attr == "parent":
                assert getattr(node.value, "attr", "") != "parent", f"{path}:{node.lineno}"
            if isinstance(node, ast.Subscript):
                value = node.value
                if isinstance(value, ast.Attribute) and value.attr == "parents":
                    index = node.slice
                    assert isinstance(index, ast.Constant) and index.value < 2, \
                        f"{path}:{node.lineno}"
            if isinstance(node, ast.Attribute) and node.attr == "__file__":
                assert getattr(node.value, "id", "") != "chia", f"{path}:{node.lineno}"
    assert bug_loop._CHIA_PKG == Path(
        importlib.import_module("chia").__path__[0]).resolve()


def sync(target: Path, *flags) -> subprocess.CompletedProcess:
    """Run `upstream/sync-to-chia.sh` against *target* and return the result."""
    return subprocess.run(["bash", str(SYNC), *flags, str(target)],
                          capture_output=True, text=True)


def tree_state(root: Path) -> dict:
    """Every file under *root* with its bytes, for a byte-identical comparison."""
    return {str(path.relative_to(root)): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.t0
def test_T_U_layout_09_sync_is_idempotent(tmp_path: Path):
    """T-U-layout-09 (FR-19.5): the sync script refuses a non-checkout and repeats cleanly."""
    refused = sync(tmp_path / "not-a-checkout")
    assert refused.returncode == 3 and "chia" in refused.stderr

    target = tmp_path / "chia"
    shutil.copytree(CHIA_STUB, target)
    before = tree_state(target)
    dry = sync(target, "--dry-run")
    assert dry.returncode == 0 and "would run" in dry.stdout
    assert tree_state(target) == before

    first = sync(target)
    assert first.returncode == 0, first.stderr
    once = tree_state(target)
    assert "examples/circt_bug_loop/bug_loop.py" in once
    assert b"firtool_lower_chirrtl_to_hw" in once["chia/chipyard/circt.py"]
    assert b"circt_exec_probe" in once["chia/chipyard/circt.py"]

    second = sync(target)
    assert second.returncode == 0, second.stderr
    assert tree_state(target) == once


@pytest.mark.t1
def test_T_U_layout_10_sync_into_a_real_checkout(tmp_path: Path):
    """T-U-layout-10 (FR-19.5): the sync into a throwaway clone of CHIA."""
    source = Path.home() / ".cache" / "chia-src"
    if not (source / ".git").is_dir():
        pytest.skip(f"no CHIA checkout at {source}")
    target = tmp_path / "chia-src"
    clone = subprocess.run(["git", "clone", "--quiet", "--depth", "1",
                            f"file://{source}", str(target)],
                           capture_output=True, text=True)
    assert clone.returncode == 0, clone.stderr

    issue_task = target / "examples" / "circt_issue_solver" / "issue_task.py"
    vertex = target / "chia" / "models" / "vertex.py"
    assert 'elif backend == "vertex":' not in issue_task.read_text(encoding="utf-8")
    assert "thoughts_token_count" not in vertex.read_text(encoding="utf-8")

    first = sync(target)
    assert first.returncode == 0, first.stderr
    assert 'elif backend == "vertex":' in issue_task.read_text(encoding="utf-8")
    # BOTH patches, since W-20b.
    assert "thoughts_token_count" in vertex.read_text(encoding="utf-8")
    assert (target / "examples" / "circt_bug_loop" / "bug_loop.py").is_file()
    assert (target / "dockerfiles" / "ChiaCirctAssertDockerfile").is_file()
    circt_py = (target / "chia" / "chipyard" / "circt.py").read_text(encoding="utf-8")
    assert "circt_exec_probe" in circt_py and circt_py.count("circt_exec_probe") >= 1

    once = tree_state(target / "examples" / "circt_bug_loop")
    second = sync(target)
    assert second.returncode == 0, second.stderr
    assert tree_state(target / "examples" / "circt_bug_loop") == once
    assert issue_task.read_text(encoding="utf-8").count(
        'elif backend == "vertex":') == 1


@pytest.mark.t0
def test_T_U_layout_11_head_nodes_match_the_docstrings():
    """T-U-layout-11 (K4): `HEAD_NODES` is exactly the nodes that say head."""
    import re

    unresourced = set()
    for path in flow_files():
        for node in parse(path).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            decorators = [ast.unparse(d) for d in node.decorator_list]
            chia = [d for d in decorators if "ChiaFunction" in d]
            if chia and "resources=" not in chia[0]:
                unresourced.add(f"circt_bug_loop.{path.stem}.{node.name}")

    assert bug_loop.HEAD_NODES == unresourced

    for dotted in sorted(bug_loop.HEAD_NODES):
        node = node_object(dotted.split("circt_bug_loop.")[1])
        assert node._chia_options == {"max_retries": 0}, dotted
        assert bug_loop.node_key(node) == dotted
        worker = re.search(r"Worker:\s*\n(.+?)(?:\n\s*Raises:|\Z)",
                           node._chia_original.__doc__ or "", re.DOTALL)
        assert worker and "head" in worker.group(1).lower(), dotted


@pytest.mark.t0
def test_T_U_layout_11_dispatch_pins_them_and_nothing_else(monkeypatch):
    """T-U-layout-11 (K4): the affinity is hard, and only head nodes get one."""
    from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

    HEAD_ID = "ab" * 28          # Ray validates the length of a node id

    from circt_bug_loop import ledger as ledger_module
    from circt_bug_loop import probe_task

    seen = {}
    monkeypatch.setattr(bug_loop, "get", lambda ref: ref)

    def stand_in(fn):
        """A node with *fn*'s identity, recording the options it is dispatched at."""
        class _Node:
            __module__, __name__ = fn.__module__, fn.__name__

            def __init__(self, options=None):
                self._options = options or {}

            def options(self, **options):
                return _Node(options)

            def chia_remote(self, *args, **kwargs):
                seen[bug_loop.node_key(self)] = self._options
                return "collected"

        return _Node()

    dispatch = bug_loop.Dispatch(remote=True, head_node_id=HEAD_ID)
    assert dispatch.call(stand_in(ledger_module.accrue)) == "collected"
    assert dispatch.call(stand_in(probe_task.probe_execute)) == "collected"

    assert set(seen) == {"circt_bug_loop.ledger.accrue",
                         "circt_bug_loop.probe_task.probe_execute"}
    strategy = seen["circt_bug_loop.ledger.accrue"]["scheduling_strategy"]
    assert isinstance(strategy, NodeAffinitySchedulingStrategy)
    assert strategy.node_id == HEAD_ID and strategy.soft is False
    assert seen["circt_bug_loop.probe_task.probe_execute"] == {}

    # W-18: A NODE DEFINED IN THIS FILE REPORTS `__main__` when the driver is run as a script.
    def as_script():
        """`build_image` as the submitted entrypoint's own process sees it."""
    as_script.__module__, as_script.__name__ = "__main__", "build_image"

    assert bug_loop.node_key(as_script) == "circt_bug_loop.bug_loop.build_image"
    assert bug_loop.node_key(as_script) in bug_loop.HEAD_NODES
    seen.clear()
    assert dispatch.call(stand_in(as_script)) == "collected"
    pinned = seen["circt_bug_loop.bug_loop.build_image"]["scheduling_strategy"]
    assert pinned.node_id == HEAD_ID and pinned.soft is False
