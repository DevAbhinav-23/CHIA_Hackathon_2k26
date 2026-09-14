"""The repository's own layout properties (`03-LLD.md` §1.3, §1.4, §14.5).

`04-Test-Plan.md` §1.1, the `T-U-layout-*` tests. They read the tree with `ast`
and with the imported modules; none of them runs a stage, a tool or a model, so
every one is tier 0 but `T-U-layout-10`, which runs `upstream/sync-to-chia.sh`
into a throwaway clone of a real CHIA checkout.

**Three rules fail on modules this task does not own, and each failing assertion
is `xfail`ed with the row of `design/reviews/implementation-errata-log.md` that
records why.** The rules themselves are not weakened: the assertion stays as the
design states it, and the row says what has to change for it to pass.
"""
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

# Each test carries its own tier marker rather than the module carrying one:
# T-U-layout-10 is tier 1, needing a CHIA checkout outside this repository, and
# a module-level t0 would select it into the tier-0 run (04-Test-Plan.md 0.5).

FLOW = Path(bug_loop.FLOW_DIR)
REPO = FLOW.parent
TESTS = FLOW / "tests"
SYNC = REPO / "upstream" / "sync-to-chia.sh"
CHIA_STUB = TESTS / "fixtures" / "layout" / "chia_stub"

#: §1.3's NINETEEN source modules that hold logic, each with its test
#: module: eighteen, plus `llm.py`, the join's neutral module (LLD §16.2).
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

#: §1.3's one source module with no test module of its own, plus the package
#: marker the two-tree layout needs and §1.1 does not list (errata row 14).
NO_TEST_MODULES = ("contract/__init__.py", "__init__.py")

#: §1.3's two structural test modules, which have no source counterpart.
STRUCTURAL_TESTS = ("test_layout.py", "test_fixtures.py")

#: §1.3's exemption list, compared for EQUALITY so neither document can grow
#: one the other does not: the five artefact test modules, with
#: `test_image_spec.py` renamed `test_image.py` (errata row 15), and
#: `test_tools.py` for the two `ChiaTool`s, which are not a source module
#: (LLD §16.2, 2026-09-15).
EXEMPT_TESTS = ("test_image.py", "test_prompts.py", "test_cluster_yaml.py",
                "test_submit.py", "test_budget_yaml.py", "test_tools.py")

#: The one test module neither §1.3 nor its exemption list names (errata row
#: 16): the three functions proposed for `chia/chipyard/circt.py` are developed
#: in this tree as `circt_core.py` and tested here, `chia/chipyard/test/` being
#: a CHIA path this repository does not hold.
EXTRA_MODULES = {"circt_core.py": "test_circt_core.py"}

#: `02-HLD.md` §1.2's supply half, module by module: A1, A2, A3 and A4, A5,
#: A6a, A6b and A4's frozen set. Everything else is the apparatus half or the
#: seam, and §2.9's import rule is about this list.
SUPPLY_HALF = ("corpus.py", "pin_select.py", "generate_task.py", "feedback.py",
               "budget.py", "ledger.py", "mutator_synth.py", "mutators/__init__.py")

#: The one exemption from that rule, by module and by name: `ledger.py` is A6b
#: and `BudgetLedger` and `LoopStore` are declared in `store.py`, which is where
#: the records the ledger owns the arithmetic of live (LLD §16.2, 2026-09-15).
SEAM_EXEMPT = {"ledger.py": ("BudgetLedger", "LoopStore")}

#: §14.5's six apparatus modules, and its three exempt by name.
APPARATUS = ("probe_task.py", "triage_task.py", "repair_adapter.py", "gate.py",
             "store.py", "ddmin.py")
ARM_EXEMPT = ("ledger.py", "results.py", "contract/schema.py")

#: §3.2's node table: every node the flow ships, with the placement its row
#: gives it. `llm.llm_turn` is §3.5.1's own node and its `{"llm": 1}`
#: is a FOURTH placement that §3.2's table never gained (errata row 17);
#: `gate.gate_validate` is the third gate node of the architect's decision 6.
NODES = {
    "corpus.build_corpus": None, "corpus.resolve_sites": None,
    "pin_select.select_release_pinned_main": None,
    "generate_task.generate_seeded": {"circt": 1},
    "generate_task.generate_mutation": {"circt": 1},
    "llm.llm_turn": {"llm": 1.0},
    "feedback.build_feedback": None, "budget.load_budget": None,
    "ledger.accrue": None, "mutator_synth.synthesise_mutators": None,
    "bug_loop.build_image": {"circt": 1},
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

#: §3.10's three, which are CHIA's file and not the example's: `{"circt": 1}`
#: and, as §3.10 spells them, no `max_retries`.
CORE_NODES = ("circt_core.circt_exec_probe", "circt_core.circt_reduce_run",
              "circt_core.circt_symbolize")

#: §0's dependency rule: the standard library, plus these and nothing else.
THIRD_PARTY = {"yaml", "ray", "chia"}
#: CHIA's own two example modules, which §13.1 ships through `py_modules` and
#: `repair_adapter` imports on the worker (FR-12.1 forbids copying them).
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


# ---------------------------------------------------------------------------
# T-U-layout-01: the four sets of 1.3, both directions
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_layout_01_mapping():
    """T-U-layout-01 (FR-19.5): every source module that holds logic has its test module.

    Both directions: no source module without a test module, and no test module
    naming a source module that does not exist. Fixture: none. Tier 0.
    """
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
    """T-U-layout-01 (NFR-12): the exemption list equals the six 1.3 names.

    Five of the six are a Dockerfile, a prompt directory, two YAMLs, a shell
    script and a YAML data file, and the sixth is a pair of `ChiaTool`s inside
    another module; none of them is a source module, so none can have a
    `test_<module>.py` counterpart under the mapping rule. The list is compared
    for equality so neither document can grow one the other does not; the one
    rename is recorded in the errata log. Fixture: none. Tier 0.
    """
    assert set(EXEMPT_TESTS) == {
        "test_image.py", "test_prompts.py", "test_cluster_yaml.py",
        "test_submit.py", "test_budget_yaml.py", "test_tools.py"}
    for artefact, test in (
            (REPO / "upstream" / "dockerfiles" / "ChiaCirctAssertDockerfile", "test_image.py"),
            (FLOW / "prompts", "test_prompts.py"),
            (FLOW / "cluster_single.yaml", "test_cluster_yaml.py"),
            (FLOW / "bug_loop_submit.sh", "test_submit.py"),
            (FLOW / "budget.yaml", "test_budget_yaml.py")):
        assert artefact.exists(), str(artefact)
        assert test in EXEMPT_TESTS


@pytest.mark.xfail(reason="errata row 18: tests/test_prompts.py and "
                          "tests/test_budget_yaml.py are not written yet; "
                          "the prompts are W-13's and budget.yaml is W-06's")
@pytest.mark.t0
def test_T_U_layout_01_twenty_five():
    """T-U-layout-01 (FR-19.5): the test directory holds exactly the expected modules.

    Nineteen for the source modules that hold logic, `llm.py` included, two
    structural, six on the exemption list and one the implementation added
    (errata row 16). Fixture: none. Tier 0.
    """
    present = {path.name for path in TESTS.glob("test_*.py")}
    expected = (set(SOURCE_MODULES.values()) | set(STRUCTURAL_TESTS)
                | set(EXEMPT_TESTS) | set(EXTRA_MODULES.values()))
    assert present == expected


# ---------------------------------------------------------------------------
# 1.3's rule (2): no store.py name reaches a supply-half module
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_layout_01_seam():
    """T-U-layout-01 (FR-16.1, §2.9): the supply half imports no `store.py` name.

    The fourteen apparatus-internal records live beside their DDL and cross
    nothing; a supply-half module that imported one would have the apparatus's
    result shapes in the half that proposes work, which is what FR-16.1 exists
    to stop. `ledger.py` is exempt and by exactly two names: `BudgetLedger` and
    `LoopStore` are declared in `store.py` and A6b owns the arithmetic over
    them, so the rule as first written was false of the design it describes.
    Fixture: none. Tier 0.
    """
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


# ---------------------------------------------------------------------------
# T-U-layout-02: 14.5's walk, where `arm` may be branched on
# ---------------------------------------------------------------------------


def _branch_operands(node: ast.AST) -> list:
    """The expressions §14.5 calls a branch's operand, and no others.

    An `If`'s TEST and not its body, a `Compare`'s left and comparators, a
    `Match`'s subject and a `Subscript`'s slice. Walking a whole `If` instead,
    as the section's wording invites, reports every mention of `arm` inside the
    branch, which is carrying it and is what FR-18.1 permits.
    """
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
    """Every line of *path* that branches on a name or attribute `arm`.

    "Ending in arm" is read as `arm` itself or a `_arm` suffix: the literal
    reading also matches `warm`, and `circt_warm_build` is a name this tree uses
    (errata row 19).
    """
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
    """T-U-layout-02 (FR-18.1): the apparatus carries `arm` and does not branch on it.

    Fixture: none. Tier 0.
    """
    for name in APPARATUS:
        if name == "probe_task.py":
            continue                      # its own assertion below, errata row 19
        assert arm_branches(FLOW / name) == [], name
    assert set(ARM_EXEMPT) == {"ledger.py", "results.py", "contract/schema.py"}
    assert arm_branches(FLOW / "ledger.py"), "the exemption is used by ledger.py"
    assert arm_branches(FLOW / "results.py"), "the exemption is used by results.py"


@pytest.mark.xfail(reason="errata row 19: probe_task.oracle_differential names "
                          "its two SIMULATOR sides `arm`, so 14.5's walk fires "
                          "on a name collision and not on a campaign arm")
@pytest.mark.t0
def test_T_U_layout_02_probe_task():
    """T-U-layout-02 (FR-18.1): the walk over `probe_task.py` itself.

    Fixture: none. Tier 0.
    """
    assert arm_branches(FLOW / "probe_task.py") == []


# ---------------------------------------------------------------------------
# T-U-layout-03, -04, -05: docstrings, tools, dependencies
# ---------------------------------------------------------------------------


def paragraphs(doc: str) -> list:
    """The three named paragraphs a node's docstring must carry, in order."""
    return [word for word in ("Returns:", "Worker:", "Raises:") if word in (doc or "")]


@pytest.mark.t0
def test_T_U_layout_03_nodes():
    """T-U-layout-03 (FR-19.4, NFR-12): every node's docstring has the three paragraphs.

    The rule is narrowed to the nodes and the two tools, which is the
    architect's instruction and errata row 20: as `03-LLD.md` §3.1 states it, it
    covers every public callable, and 45 of the flow's 184 public functions
    across seven modules do not carry all three. Every node and every tool
    method does. Fixture: none. Tier 0.
    """
    for dotted in list(NODES) + list(CORE_NODES):
        doc = inspect.getdoc(node_object(dotted))
        assert paragraphs(doc) == ["Returns:", "Worker:", "Raises:"], dotted
        assert doc.splitlines()[0].endswith("."), dotted


@pytest.mark.t0
def test_T_U_layout_03_tools():
    """T-U-layout-03 (FR-19.4): each tool method states an action, an argument and a failure.

    An MCP method's docstring is what the model reads, so it is checked against
    what a caller needs rather than against the node paragraphs. Fixture: none.
    Tier 0.
    """
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
            # `write_probe` names `filename` and not `content` (errata row 24).
            assert any(argument in doc for argument in arguments), name
            assert "Error" in doc, name


@pytest.mark.t0
def test_T_U_layout_04():
    """T-U-layout-04 (FR-19.1): no bare `ray.remote`, and every tool is a `ChiaTool`.

    FR-19.1's five long-work categories are the `AsyncJobTool` rule's trigger
    and neither tool falls in one, so that half holds vacuously and the check
    still runs. Fixture: none. Tier 0.
    """
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
    """T-U-layout-05 (FR-19.8, NFR-11): no dependency outside CHIA's own and the stdlib.

    The permitted non-standard imports are `yaml`, `ray` and `chia`, the flow's
    own package, and CHIA's two example modules, which §13.1 ships through
    `py_modules` because FR-12.1 forbids copying them. §0's own list of
    standard-library modules is five short of what the implementation uses and
    that is recorded rather than asserted here (errata row 21). Fixture: none.
    Tier 0.
    """
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


# ---------------------------------------------------------------------------
# T-U-layout-06, -07: the decorators, and the counters
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_layout_06():
    """T-U-layout-06 (FR-12.11, FR-13.2, FR-19.1): every node's `_chia_options`.

    `max_retries=0` on every node of the flow; `{"repair": 1}` held by
    `repair_adapt` alone; `gate_decide` and the four head nodes declaring no
    worker resource at all, which is the head move of the LLD's own revision.
    Fixture: none. Tier 0.
    """
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
    """T-U-layout-07 (FR-17.4, FR-19.4): every node returns a `CounterBlock`.

    §3.11 makes it every node of §3.2. Two halves, both static: the documented
    **Returns** paragraph names the key `counters`, and the node's own return
    annotation is `dict`, because a node returning a bare record has nowhere to
    put the block. Errata row 22 recorded nine node modules that returned none;
    the join gave every one of them the block, and `_COUNTER_STAGES` gained the
    five names none of them had (feedback, budget, ledger, artefact, results).
    Fixture: none. Tier 0.
    """
    missing = [dotted for dotted in NODES if not returns_counters(dotted)]
    assert missing == []
    bare = [dotted for dotted in NODES
            if inspect.signature(
                getattr(node_object(dotted), "_chia_original",
                        node_object(dotted))).return_annotation != "dict"]
    assert bare == []


@pytest.mark.t0
def test_T_U_layout_07_stages():
    """T-U-layout-07 (FR-17.4): `CounterBlock.stage` is drawn from `_COUNTER_STAGES`.

    The half of the rule that holds: the driver refuses a block naming anything
    else, whoever produced it. Fixture: none. Tier 0.
    """
    assert set(schema._COUNTER_STAGES) == set(schema._STAGE_IDS) | {
        "image", "corpus", "pin", "mirror", "synthesis",
        # Five added at the join (W-17, errata row 22): 3.11 requires a block of
        # EVERY node of 3.2 and none of these five had a stage to name.
        "feedback", "budget", "ledger", "artefact", "results"}
    log = bug_loop.CounterLog("run", None)
    # "feedback" was the invented name here until the join made it a real stage
    # (errata row 22); the rule is unchanged and the name that is not a stage is.
    with pytest.raises(ValueError):
        log.record("seeded", schema.CounterBlock(stage="stage_9", started=1,
                                                 completed=1, failed=0, seconds=0.0))


# ---------------------------------------------------------------------------
# T-U-layout-08: nothing below T3 can reach a model
# ---------------------------------------------------------------------------


def interlock_setters(path: Path) -> list:
    """Every line of a test module that puts the interlock into the environment.

    `monkeypatch.setenv`, `os.environ[...] = `, `os.environ.setdefault` and
    `os.putenv`, with the name read as a literal or as any attribute or name
    ending `LIVE_MODEL_ENV`; a name the walk cannot resolve to a literal is a
    failure, because "a computed name does not pass it".

    The RECEIVER is read as well as the method name, which the first version did
    not do: a bare `setdefault` is `dict.setdefault` far more often than it is
    `os.environ`'s, and `by_rule.setdefault(raw["rule"], [])` is a computed key
    on a plain dict that the unqualified rule reported as an interlock write.
    """
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
    """T-U-layout-08 (NFR-06, NFR-08): no test module puts the interlock in the environment.

    An `ast` walk and not a grep, so a docstring naming the variable does not
    fail and a computed name does not pass. `tests/system/` is the one directory
    the rule exempts and it does not exist yet. Fixture: none. Tier 0.
    """
    setters = {path.name: interlock_setters(path)
               for path in sorted(TESTS.glob("test_*.py"))}
    assert {name: lines for name, lines in setters.items() if lines} == {}


@pytest.mark.t0
def test_T_U_layout_08_one_construction_path():
    """T-U-layout-08 (NFR-06): two construction paths, both behind the same refusal.

    `VertexGeminiLLM` is named in exactly one function of the loop's own
    modules, `llm.build_llm`; the second path is the `vertex` arm of
    `upstream/issue_task-vertex-branch.patch`, which is CHIA's file and cannot
    carry the interlock, so `repair_adapter.repair_adapt` calls
    `require_live_model` before it invokes the chain. There is no third.
    Fixture: none. Tier 0.
    """
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
    """T-U-layout-08 (NFR-08): `conftest.py`'s own fixture is the session's refusal.

    It asserts the variable's absence rather than deleting it, which is the
    stronger form the test plan's §17 anticipated, and this test reads that
    effect: the interlock is absent for every test in this run. Fixture: none.
    Tier 0.
    """
    from circt_bug_loop.tests import conftest

    assert bug_loop.LIVE_MODEL_ENV not in os.environ
    assert conftest._INTERLOCK == bug_loop.LIVE_MODEL_ENV
    assert conftest.no_live_model.__wrapped__() is None


# ---------------------------------------------------------------------------
# T-U-layout-09, -10: the two-tree layout and the sync script
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_layout_09_no_module_walks_up():
    """T-U-layout-09 (FR-19.2): no flow module walks past its own directory.

    `circt_bug_loop/` in the team repository and `examples/circt_bug_loop/` in a
    CHIA checkout have different ancestors, so a module that derived CHIA's
    package directory from its own location would be right in one tree and
    wrong in the other. `chia.__path__[0]` and never `chia.__file__`, which is
    `None` for a namespace package. Fixture: none. Tier 0.
    """
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
    """T-U-layout-09 (FR-19.5): the sync script refuses a non-checkout and repeats cleanly.

    Run twice into a copy of the stub checkout, the second run leaves it
    byte-identical: the appended functions are guarded by their marker and the
    vertex branch by the branch itself. `--dry-run` changes nothing at all.
    Fixture: `layout/chia_stub/`. Tier 0.
    """
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
    """T-U-layout-10 (FR-19.5, FR-12.1): the sync into a throwaway clone of CHIA.

    The stub cannot exercise step 4: it carries the `vertex` branch already, so
    the guard skips the patch. This runs the whole script against a real CHIA
    checkout, cloned locally from `~/.cache/chia-src` so that nothing is
    fetched, and asserts that the patch applies, that the example lands beside
    CHIA's own, and that a second run is a no-op. Tier 1.
    """
    source = Path.home() / ".cache" / "chia-src"
    if not (source / ".git").is_dir():
        pytest.skip(f"no CHIA checkout at {source}")
    target = tmp_path / "chia-src"
    clone = subprocess.run(["git", "clone", "--quiet", "--depth", "1",
                            f"file://{source}", str(target)],
                           capture_output=True, text=True)
    assert clone.returncode == 0, clone.stderr

    issue_task = target / "examples" / "circt_issue_solver" / "issue_task.py"
    assert 'elif backend == "vertex":' not in issue_task.read_text(encoding="utf-8")

    first = sync(target)
    assert first.returncode == 0, first.stderr
    assert 'elif backend == "vertex":' in issue_task.read_text(encoding="utf-8")
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
