"""`feedback.py` (A5): one entry per probe, the abandonment rule, the deny-list.

`04-Test-Plan.md` §1.17's eight `T-U-feed-*` rows, plus three this
implementation added and §16.7 records: the cap rule of FR-17.7 as the bundle
applies it, the byte-determinism FR-16.5 rests on, and FR-16.2's empty bundle.
All tier 0: `feedback.py` is head-side and pure, and no test here opens a file,
a database or a socket.

The budget every test meters against is the committed `budget_file/` fixture,
whose per-seed caps are 3 iterations and 10 probes; the arm's own allowance
arrives as a `LedgerSnapshot`, which is the only view of the budget a generator
half ever gets (§2.5).
"""
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

#: The generator half's modules, which FR-16.1 keeps clear of every apparatus
#: schema. `mutators/` is A4's frozen set and holds no import of its own.
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
    """Call A5 the way the driver does, through `conftest.call_node` (§0.4).

    The node returns `{"bundle", "counters"}` since the join (W-17, errata row
    22); what every test below reads is the bundle, so the helper unwraps it
    and asserts the block here, at every call site.
    """
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
    """T-U-feed-01 (FR-16.1): one entry per probing input, whatever its outcome.

    Every input of the previous iteration appears exactly once, including the
    ones that exited cleanly, parsed badly, timed out or exhausted memory, and
    each carries the four things FR-16.1 lists: the stage, the reason, the
    oracle verdict where one exists and the reduced case where one exists. The
    bundle is built from `ProbeResult`s and from nothing else.
    """
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
    """T-U-feed-02 (FR-16.1): a dispatched probe with no result is present, not absent.

    The set difference is the honest one only if the bundle is keyed on what
    was dispatched rather than on what came back, so a probe whose result never
    arrived carries `result_missing` and the generator can see that it did.
    """
    bundle = build([result("p-1")], dispatched=["p-1", "p-2"])

    assert [e.probe_id for e in bundle.entries] == ["p-1", "p-2"]
    assert bundle.entries[1].reason == RESULT_MISSING
    assert bundle.entries[1].stopped_at_stage == "stage_3"

    with pytest.raises(ValueError, match="not dispatched"):
        build([result("p-9")], dispatched=["p-1"])


def test_T_U_feed_03():
    """T-U-feed-03 (FR-16.6, FR-06.6): the abandonment rule, spelled as a multiset.

    Two consecutive iterations of stage-3 deaths abandon the seed only when the
    multiset of `(build_status, stopping_reason)` pairs is equal between them.
    The negative case is the point: two iterations of `parse_error` whose
    reasons differ must NOT abandon, because `parse_error` covers both a
    rejected input and a rejected argv and abandoning for the second would hide
    an apparatus defect as a seed property.
    """
    first = build([stage_3("p-1", "parse_error", "tool_rejected_input"),
                   stage_3("p-2", "timeout", "wall_limit")], iteration=2)
    assert first.abandoned is False

    same = build([stage_3("p-3", "parse_error", "tool_rejected_input"),
                  stage_3("p-4", "timeout", "wall_limit")], first, iteration=3)
    assert same.abandoned is True
    assert same.abandon_reason == ("stage_3:parse_error:tool_rejected_input x1, "
                                  "stage_3:timeout:wall_limit x1")
    assert same.terminating_condition == "abandoned"

    other_reason = build([stage_3("p-3", "parse_error", "tool_rejected_argv"),
                          stage_3("p-4", "timeout", "wall_limit")], first, iteration=3)
    assert other_reason.abandoned is False
    assert other_reason.abandon_reason is None

    different_count = build([stage_3("p-3", "parse_error", "tool_rejected_input")],
                            first, iteration=3)
    assert different_count.abandoned is False

    got_past_stage_3 = build([assertion_result("p-3"),
                              stage_3("p-4", "timeout", "wall_limit")], first, iteration=3)
    assert got_past_stage_3.abandoned is False


def test_T_U_feed_04():
    """T-U-feed-04 (FR-16.6): `abandon_reason` is non-null exactly when abandoned.

    Enforced twice: by the builder, which writes the repeated pair and nothing
    else, and by `contract.validate`, which refuses either half alone.
    """
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
    """T-U-feed-05 (FR-16.4): the deny-list, over names and over values.

    No field name of `FeedbackBundle` or `FeedbackEntry`, at any nesting depth,
    is one of `_FEEDBACK_DENY`'s twenty-one; and a result carrying every one of
    those names as an extra attribute produces a bundle whose canonical JSON
    holds none of them. The second half is the one that matters: the deny-list
    is a rule about what A5 copies, not only about what the schema declares.
    """
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
    """T-U-feed-06 (FR-16.1): the supply half imports no apparatus schema.

    An `ast` walk over the generator half's modules: none of them imports
    `OracleVerdict`, `ReducedCase` or `CandidateRecord`, and `feedback.py`
    imports nothing of the loop but the contract package, which is what makes
    the seam one-directional rather than merely tidy.
    """
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
    """T-U-feed-07 (FR-16.3): all three terminating conditions, and the fourth.

    The per-seed iteration cap, the per-seed input cap and the arm's allowance
    on the primary unit, each exercised and recorded; abandonment is the fourth
    and takes precedence, being the one condition that is about the seed rather
    than about the budget.
    """
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
    """T-U-feed-08 (FR-16.5): the bundle replays into the same prompt bytes.

    A5's output is the only per-iteration input stage 2's prompt has, so
    replaying iteration k from its recorded `SeedRecord` and `FeedbackBundle`
    through `Template.safe_substitute` must reproduce the prompt byte for byte.
    """
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
    """T-U-feed-09 (FR-17.7): the bundle's reduced text obeys the one cap rule.

    `contract.bound_text` is the one place FR-17.7 is applied, so a reduced case
    over `artefact_inline_cap_bytes` travels as its path and not as its text,
    and a text over the cap with no companion path raises rather than being
    silently dropped.
    """
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
    """T-U-feed-10 (FR-16.5, NFR-02): the same inputs give byte-identical JSON.

    Determinism is what FR-16.5's replay rests on: two builds from one input
    set serialise to the same bytes, entry order following the dispatched order
    and not the order results happened to arrive in.
    """
    results = [stage_3("p-2", "timeout", "cpu_limit"), assertion_result("p-1")]
    dispatched = ["p-1", "p-2", "p-3"]

    first = schema.to_json(build(results, dispatched=dispatched))
    second = schema.to_json(build(list(reversed(results)), dispatched=dispatched))

    assert first == second
    assert json.loads(first)["entries"][0]["probe_id"] == "p-1"


def test_T_U_feed_11():
    """T-U-feed-11 (FR-16.2): the first iteration and the mutation arm get nothing.

    Iteration 1 has no previous iteration to report, and the mutation arm
    receives no feedback at all; both are an empty entry list rather than an
    absent bundle, because the driver's call into a generator takes one
    (`Generator`, §2.5). The stop rules still apply to both.
    """
    results = [assertion_result("p-1"), result("p-2")]

    first_iteration = build(results, iteration=1)
    assert first_iteration.entries == [] and first_iteration.arm == "seeded"

    mutation = build(results, arm="mutation", iteration=2)
    assert mutation.entries == [] and mutation.arm == "mutation"
    assert mutation.abandoned is False

    mutation_capped = build(results, arm="mutation", iteration=3)
    assert mutation_capped.terminating_condition == "iteration_cap"
