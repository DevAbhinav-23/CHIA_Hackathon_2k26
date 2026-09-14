"""`feedback.py` (A5): one entry per probe, the abandonment rule, the deny-list."""
from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from circt_bug_loop import feedback as feedback_module
from circt_bug_loop.contract import schema
from circt_bug_loop.feedback import (RESULT_MISSING, TERMINATING_CONDITIONS,
                                     _FEEDBACK_DENY, build_feedback)
from circt_bug_loop.tests.conftest import FIXTURES, call_node

pytestmark = pytest.mark.t0

_RUN = "7c1f4a9d6e2b48c0a53f81d27e6b09c4"
_SEED = "3f9a1c0e7b4d2a68f05c9e13b7a4d820c6e5f9a1"

#: The generator half's modules, which FR-16.1 keeps clear of every apparatus schema.
_SUPPLY_MODULES = ("feedback.py", "generate_task.py", "budget.py", "ledger.py")

#: The three apparatus-internal schemas the supply half may not import.
_APPARATUS_SCHEMAS = ("OracleVerdict", "ReducedCase", "CandidateRecord")


def budget(**overrides) -> schema.BudgetFile:
    """The committed `budget_file/` fixture, with any key overridden."""
    payload = json.loads((FIXTURES / "budget_file" / "complete_01.json").read_text())
    payload.update(overrides)
    parsed = schema.BudgetFile(**payload)
    schema.validate(parsed)
    return parsed


def snapshot(arm: str = "seeded", spent: float = 0.0,
             cap: float = 14400.0) -> schema.LedgerSnapshot:
    """The arm's own view of its window, which is all a generator may know."""
    return schema.LedgerSnapshot(arm=arm, unit="wall_clock_seconds", spent=spent, cap=cap)


def result(probe_id: str, *, status: str = "clean_exit", reason: str = "",
           stage: str = "stage_3", arm: str = "seeded", iteration: int = 1,
           **overrides) -> schema.ProbeResult:
    """One ProbeResult, defaulted to the ordinary case: it parsed and exited 0."""
    fields = dict(probe_id=probe_id, run_manifest_id=_RUN, seed_sha=_SEED, arm=arm,
                  iteration=iteration, build_status=status, oracle_fired=False,
                  stopping_stage=stage, stopping_reason=reason,
                  artefact_dir=f"/artefacts/{_RUN}/{probe_id}")
    fields.update(overrides)
    parsed = schema.ProbeResult(**fields)
    schema.validate(parsed)
    return parsed


def assertion_result(probe_id: str, **overrides) -> schema.ProbeResult:
    """One ProbeResult whose primary oracle fired on an assertion."""
    return result(probe_id, status="assertion", reason="assertion_fired",
                  stage="gate", oracle_fired=True, oracle_class="assertion",
                  assertion_text='fieldType && "lowering a null field type"',
                  assertion_site="LowerTypes.cpp:412", signal="SIGABRT", **overrides)


def build(results, previous=None, *, iteration: int = 2, dispatched=None,
          arm: str = "seeded", funds=None, spent: float = 0.0, cap: float = 14400.0,
          probes: int = 0) -> schema.FeedbackBundle:
    """Call A5 the way the driver does, through `conftest.call_node` (§0.4)."""
    ids = dispatched if dispatched is not None else [r.probe_id for r in results]
    out = call_node(build_feedback, list(results), previous, _SEED, iteration,
                    ids, run_manifest_id=_RUN, budget=funds or budget(),
                    remaining=snapshot(arm, spent, cap), probes_this_seed=probes)
    assert out["counters"].stage == "feedback"
    return out["bundle"]


def stage_3(probe_id: str, status: str, reason: str) -> schema.ProbeResult:
    """One probe that died at stage 3, which is what FR-16.6 counts."""
    return result(probe_id, status=status, reason=reason, stage="stage_3")


def test_T_U_feed_01():
    """T-U-feed-01 (FR-16.1): one entry per probing input, whatever its outcome."""
    results = [
        assertion_result("p-1", reduced_text="firrtl.circuit \"T\" {}\n",
                         reduced_path="/artefacts/p-1/reduced.fir"),
        result("p-2"),
        stage_3("p-3", "parse_error", "tool_rejected_input"),
        stage_3("p-4", "timeout", "wall_limit"),
        stage_3("p-5", "oom", "address_space_limit"),
    ]
    bundle = build(results)

    assert [e.probe_id for e in bundle.entries] == ["p-1", "p-2", "p-3", "p-4", "p-5"]
    fired, clean, parse, timeout, oom = bundle.entries
    assert (fired.stopped_at_stage, fired.reason) == ("gate", "assertion:assertion_fired")
    assert fired.oracle_class == "assertion"
    assert fired.oracle_summary == ('fieldType && "lowering a null field type"\n'
                                    "LowerTypes.cpp:412")
    assert fired.reduced_text == "firrtl.circuit \"T\" {}\n"
    assert fired.reduced_to_bytes == len(fired.reduced_text.encode("utf-8"))
    assert (clean.reason, clean.oracle_class, clean.reduced_text) == ("clean_exit", None, None)
    assert parse.reason == "parse_error:tool_rejected_input"
    assert timeout.reason == "timeout:wall_limit"
    assert oom.reason == "oom:address_space_limit"


def test_T_U_feed_02():
    """T-U-feed-02 (FR-16.1): a dispatched probe with no result is present, not absent."""
    bundle = build([result("p-1")], dispatched=["p-1", "p-2"])

    assert [e.probe_id for e in bundle.entries] == ["p-1", "p-2"]
    assert bundle.entries[1].reason == RESULT_MISSING
    assert bundle.entries[1].stopped_at_stage == "stage_3"

    with pytest.raises(ValueError, match="not dispatched"):
        build([result("p-9")], dispatched=["p-1"])


def test_T_U_feed_03():
    """T-U-feed-03 (FR-16.6): the abandonment rule, spelled as a multiset."""
    first = build([stage_3("p-1", "oom", "allocation_failure"),
                   stage_3("p-2", "timeout", "wall_limit")], iteration=2)
    assert first.abandoned is False

    same = build([stage_3("p-3", "oom", "allocation_failure"),
                  stage_3("p-4", "timeout", "wall_limit")], first, iteration=3)
    assert same.abandoned is True
    assert same.abandon_reason == ("stage_3:oom:allocation_failure x1, "
                                   "stage_3:timeout:wall_limit x1")
    assert same.terminating_condition == "abandoned"

    other_reason = build([stage_3("p-3", "oom", "address_space_limit"),
                          stage_3("p-4", "timeout", "wall_limit")], first, iteration=3)
    assert other_reason.abandoned is False
    assert other_reason.abandon_reason is None

    different_count = build([stage_3("p-3", "oom", "allocation_failure")],
                            first, iteration=3)
    assert different_count.abandoned is False

    got_past_stage_3 = build([assertion_result("p-3"),
                              stage_3("p-4", "timeout", "wall_limit")], first, iteration=3)
    assert got_past_stage_3.abandoned is False


def test_T_U_feed_04():
    """T-U-feed-04 (FR-16.6): `abandon_reason` is non-null exactly when abandoned."""
    previous = build([stage_3("p-1", "oom", "allocation_failure")], iteration=2)
    abandoned = build([stage_3("p-2", "oom", "allocation_failure")], previous, iteration=3)
    assert abandoned.abandoned and abandoned.abandon_reason == "stage_3:oom:allocation_failure x1"

    plain = build([result("p-3")], iteration=2)
    assert plain.abandoned is False and plain.abandon_reason is None

    for broken in (schema.FeedbackBundle(run_manifest_id=_RUN, seed_sha=_SEED,
                                         arm="seeded", iteration=2, entries=[],
                                         abandoned=True, abandon_reason=None),
                   schema.FeedbackBundle(run_manifest_id=_RUN, seed_sha=_SEED,
                                         arm="seeded", iteration=2, entries=[],
                                         abandoned=False, abandon_reason="stage_3:oom: x1")):
        with pytest.raises(schema.ContractError) as caught:
            schema.validate(broken)
        assert caught.value.code == "E005_CONDITIONAL_REQUIRED"


def test_T_U_feed_05():
    """T-U-feed-05 (FR-16.4): the deny-list, over names and over values."""
    assert len(_FEEDBACK_DENY) == 21
    declared = set()
    for cls in (schema.FeedbackBundle, schema.FeedbackEntry):
        declared |= {f.name for f in dataclasses.fields(cls)}
    assert declared.isdisjoint(_FEEDBACK_DENY)

    forbidden = assertion_result("p-1")
    for name in _FEEDBACK_DENY:
        setattr(forbidden, name, f"leaked-{name}")
    forbidden.candidate_count = 7
    forbidden.precision = 1.0

    bundle = build([forbidden])
    text = schema.to_json(bundle)
    for name in _FEEDBACK_DENY:
        assert name not in text, f"{name} reached the bundle"
        assert f"leaked-{name}" not in text
    assert all(not hasattr(entry, name)
               for entry in bundle.entries for name in _FEEDBACK_DENY)


def test_T_U_feed_06():
    """T-U-feed-06 (FR-16.1): the supply half imports no apparatus schema."""
    root = Path(feedback_module.__file__).resolve().parent
    for name in _SUPPLY_MODULES:
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported = {alias.name for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) for alias in node.names}
        imported |= {alias.name for node in ast.walk(tree)
                     if isinstance(node, ast.Import) for alias in node.names}
        assert imported.isdisjoint(_APPARATUS_SCHEMAS), name

    tree = ast.parse((root / "feedback.py").read_text(encoding="utf-8"))
    loop_modules = {node.module for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom)
                    and (node.module or "").startswith("circt_bug_loop")}
    assert loop_modules == {"circt_bug_loop.contract.schema"}


def test_T_U_feed_07():
    """T-U-feed-07 (FR-16.3): all three terminating conditions, and the fourth."""
    assert TERMINATING_CONDITIONS == ("abandoned", "iteration_cap", "probe_cap",
                                      "arm_allowance")
    caps = budget(per_seed_iteration_cap=3, per_seed_probe_cap=5)

    assert build([result("p-1")], iteration=2, funds=caps).terminating_condition is None
    assert build([result("p-1")], iteration=3,
                 funds=caps).terminating_condition == "iteration_cap"
    assert build([result("p-1")], iteration=2, funds=caps,
                 probes=5).terminating_condition == "probe_cap"
    assert build([result("p-1")], iteration=2, funds=caps, spent=14400.0,
                 cap=14400.0).terminating_condition == "arm_allowance"


def test_T_U_feed_08():
    """T-U-feed-08 (FR-16.5): the bundle replays into the same prompt bytes."""
    from circt_bug_loop.generate_task import render_feedback

    results = [assertion_result("p-1", reduced_text="hw.module @t() {}\n",
                                reduced_path="/artefacts/p-1/reduced.mlir"),
               stage_3("p-2", "parse_error", "tool_rejected_argv")]
    once = build(results)
    again = build(results)

    assert render_feedback(once) == render_feedback(again)
    assert render_feedback(schema.from_json(schema.to_json(once),
                                            schema.FeedbackBundle)) == render_feedback(once)
    assert "p-1: stopped at gate, assertion:assertion_fired" in render_feedback(once)


def test_T_U_feed_09():
    """T-U-feed-09 (FR-17.7): the bundle's reduced text obeys the one cap rule."""
    small = budget(artefact_inline_cap_bytes=64)
    big = "x" * 100

    bundle = build([assertion_result("p-1", reduced_text=big,
                                     reduced_path="/artefacts/p-1/reduced.mlir")],
                   funds=small)
    assert bundle.entries[0].reduced_text is None
    assert bundle.entries[0].reduced_to_bytes is None

    over = assertion_result("p-1", reduced_text=big,
                            reduced_path="/artefacts/p-1/reduced.mlir")
    over.reduced_path = None
    with pytest.raises(schema.ContractError) as caught:
        build([over], funds=small)
    assert caught.value.code == "E008_CAP_EXCEEDED"


def test_T_U_feed_10():
    """T-U-feed-10 (FR-16.5): the same inputs give byte-identical JSON."""
    results = [stage_3("p-2", "timeout", "cpu_limit"), assertion_result("p-1")]
    dispatched = ["p-1", "p-2", "p-3"]

    first = schema.to_json(build(results, dispatched=dispatched))
    second = schema.to_json(build(list(reversed(results)), dispatched=dispatched))

    assert first == second
    assert json.loads(first)["entries"][0]["probe_id"] == "p-1"


def test_T_U_feed_11():
    """T-U-feed-11 (FR-16.2): the first iteration and the mutation arm get nothing."""
    results = [assertion_result("p-1"), result("p-2")]

    first_iteration = build(results, iteration=1)
    assert first_iteration.entries == [] and first_iteration.arm == "seeded"

    mutation = build(results, arm="mutation", iteration=2)
    assert mutation.entries == [] and mutation.arm == "mutation"
    assert mutation.abandoned is False

    mutation_capped = build(results, arm="mutation", iteration=3)
    assert mutation_capped.terminating_condition == "iteration_cap"


def test_T_U_feed_12(tmp_path):
    """T-U-feed-12 (W-23): a parse error carries its own diagnostic and is repairable."""
    from circt_bug_loop.generate_task import render_feedback

    assert "parse_error" not in feedback_module._ABANDON_STATUSES
    assert feedback_module._ABANDON_STATUSES == {"timeout", "oom"}

    directory = tmp_path / "probe_p-1"
    directory.mkdir()
    (directory / "stderr.txt").write_text(
        "loading the input\n"
        "probe.mlir:3:8: error: unknown type 'string' in dialect 'sim'\n"
        "probe.mlir:9:1: error: a second one, which is not carried\n",
        encoding="utf-8")
    rejected = stage_3("p-1", "parse_error", "tool_rejected_input")
    rejected = dataclasses.replace(rejected, artefact_dir=str(directory))

    # Two iterations of the SAME parse error no longer end the seed.
    first = build([rejected], iteration=2)
    again = build([rejected], first, iteration=3)
    assert first.abandoned is False and again.abandoned is False
    assert again.terminating_condition == "iteration_cap"

    entry = first.entries[0]
    assert entry.error_line == \
        "probe.mlir:3:8: error: unknown type 'string' in dialect 'sim'"
    rendered = render_feedback(first)
    assert entry.error_line in rendered
    assert "FIX this input's syntax against the build commit, or replace it" \
        in rendered

    # Bounded, and only for the statuses that feed back.
    (directory / "stderr.txt").write_text(
        "probe.mlir:3:8: error: " + "x" * 500 + "\n", encoding="utf-8")
    long_line = build([rejected], iteration=2).entries[0].error_line
    assert len(long_line) == feedback_module.ERROR_LINE_CAP == 200

    (directory / "stderr.txt").write_text("no diagnostic here\n", encoding="utf-8")
    assert build([rejected], iteration=2).entries[0].error_line is None

    timed_out = dataclasses.replace(
        stage_3("p-2", "timeout", "wall_limit"), artefact_dir=str(directory))
    assert build([timed_out], iteration=2).entries[0].error_line is None

    # An unreadable artefact directory is not a failure of the bundle.
    missing = dataclasses.replace(rejected, artefact_dir=str(tmp_path / "gone"))
    assert build([missing], iteration=2).entries[0].error_line is None
