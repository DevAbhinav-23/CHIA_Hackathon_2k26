"""The bundle the seeded arm reads at the start of its next iteration.

A5 (`03-LLD.md` §3.11, F-16). Head-side and pure: it takes the previous
iteration's `ProbeResult`s and returns a `FeedbackBundle`, touching no database,
no file and no model.

Three rules live here and nowhere else.

  * **FR-16.1's contents.** One entry per *dispatched* probe id, carrying the
    stage the probe stopped at, the reason it stopped, the oracle verdict where
    one exists and the reduced case where one exists. A dispatched probe with no
    `ProbeResult` appears with `reason=result_missing` rather than being absent,
    which is what keeps A5's set difference honest and is why the dispatched
    list is a parameter.
  * **FR-16.4's deny-list**, `_FEEDBACK_DENY`. The bundle carries verdicts and
    reasons and no number the agent could restate as a result: no candidate
    count, no gate precision, no bug count, no filing. It is a deny-list of
    field NAMES rather than a schema because that is what FR-16.4's own
    criterion asks for, and it is asserted over the built bundle at every
    nesting depth by `tests/test_feedback.py`.
  * **FR-16.6's abandonment.** A seed is abandoned when, for two consecutive
    iterations, every probe of the iteration stopped at stage 3 with a
    `build_status` in `{parse_error, timeout, oom}` and the multiset of
    `(build_status, stopping_reason)` pairs is equal between the two. "The same
    reason" is the pair and not the status alone, because `parse_error` covers
    both a rejected input and a rejected argv (§3.6) and abandoning a seed for
    the second would hide an apparatus defect as a seed property.

This module imports the contract package and nothing else of the loop
(`04-Test-Plan.md` T-U-feed-06): `OracleVerdict`, `ReducedCase` and
`CandidateRecord` are apparatus internals and the generator half neither sees
them nor needs them (FR-16.1).
"""
from __future__ import annotations

import time
from collections import Counter
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import (BudgetFile, CounterBlock,
                                            FeedbackBundle, FeedbackEntry,
                                            LedgerSnapshot, ProbeResult,
                                            bound_text, validate)

#: FR-16.4's deny-list, `03-LLD.md` §3.11 verbatim: the twenty-one result-field
#: names no field of `FeedbackBundle` or `FeedbackEntry` may carry, at any
#: nesting depth. Its three clusters are the criterion's own three examples,
#: candidate counts, gate precision and bug counts.
_FEEDBACK_DENY = ("candidate_id", "candidate_count", "candidates", "fingerprint",
                  "dedup_verdict", "dedup_basis", "gate_answers", "gate_decision",
                  "taxonomy_bucket", "q1_reproduce", "q2_minimal", "q3_valid",
                  "q4_new", "precision", "bug_count", "confirmed", "filing",
                  "issue_number", "issue_url", "repair_status", "triage_class")

#: FR-16.6's three build statuses. A seed is abandoned over these and no others:
#: a probe that reached an oracle, however badly, told the generator something.
_ABANDON_STATUSES = frozenset({"parse_error", "timeout", "oom"})

#: The stage FR-16.6 counts over. A probe that got past it is not a candidate
#: for abandonment whatever it did afterwards.
_ABANDON_STAGE = "stage_3"

#: The reason an entry carries when the probe was dispatched and no
#: `ProbeResult` came back (`04-Test-Plan.md` T-U-feed-02).
RESULT_MISSING = "result_missing"

#: FR-16.3's three terminating conditions and FR-16.6's, named once and in the
#: order `build_feedback` decides them. The order is fixed rather than
#: temporal: the bundle is built once, at the end of an iteration, and cannot
#: know which condition bound first in time.
TERMINATING_CONDITIONS = ("abandoned", "iteration_cap", "probe_cap",
                          "arm_allowance")


def _reason(result: ProbeResult) -> str:
    """Render one result's `(build_status, stopping_reason)` pair as the entry's reason.

    The pair and not the status alone, because FR-16.6 compares pairs and
    `FeedbackEntry` has one reason field to compare them in; `clean_exit`
    carries no reason and renders as itself.

    Returns:
        str, "<build_status>:<stopping_reason>", or "<build_status>" when the
        result carries no stopping reason.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
    return (f"{result.build_status}:{result.stopping_reason}"
            if result.stopping_reason else result.build_status)


def _summary(result: ProbeResult) -> Optional[str]:
    """Render the oracle summary FR-16.1 asks for, from the result alone.

    An assertion carries its normalised text and its `file:line`, which is what
    the generator needs to write a different input. A crash or a fatal error
    carries the signal that killed the probe: the symbolised frames live on
    `OracleVerdict`, an apparatus internal this half may not import (FR-16.1).

    Returns:
        str, or None when the oracle did not fire or nothing is recorded.
    Worker:
        pure.
    Raises:
        nothing.
    """
    if not result.oracle_fired:
        return None
    if result.oracle_class == "assertion" and result.assertion_text:
        site = result.assertion_site or ""
        return f"{result.assertion_text}\n{site}" if site else result.assertion_text
    return f"died by {result.signal}" if result.signal else None


def _entry(result: Optional[ProbeResult], probe_id: str, cap: int) -> FeedbackEntry:
    """Build one entry for one dispatched probe, present or missing.

    Returns:
        FeedbackEntry, with `reduced_text` bounded by `contract.bound_text` and
        `reduced_to_bytes` its length in bytes; `reduced_from_bytes` is None,
        the pre-reduction size living on `ReducedCase` and not on the result.
    Worker:
        pure.
    Raises:
        ContractError (E008) when a reduced text is over the cap and the result
        names no companion path, which is the one combination that would lose
        an artefact silently.
    """
    if result is None:
        return FeedbackEntry(probe_id=probe_id, stopped_at_stage=_ABANDON_STAGE,
                             reason=RESULT_MISSING)
    text = bound_text(result.reduced_text, result.reduced_path, cap)
    return FeedbackEntry(
        probe_id=probe_id,
        stopped_at_stage=result.stopping_stage,
        reason=_reason(result),
        oracle_class=result.oracle_class,
        oracle_summary=_summary(result),
        reduced_text=text,
        reduced_to_bytes=len(text.encode("utf-8")) if text is not None else None)


def _abandon_multiset(entries: list) -> Optional[Counter]:
    """Count one iteration's stage-3 failure pairs, or report that it has none.

    Returns:
        Counter over each entry's reason, or None when the iteration is not one
        FR-16.6 counts: an empty iteration, a probe that got past stage 3, a
        dispatched probe with no result, or a status outside the three.
    Worker:
        pure.
    Raises:
        nothing.
    """
    if not entries:
        return None
    pairs: Counter = Counter()
    for entry in entries:
        status = entry.reason.split(":", 1)[0]
        if entry.stopped_at_stage != _ABANDON_STAGE or status not in _ABANDON_STATUSES:
            return None
        pairs[entry.reason] += 1
    return pairs


def _terminating_condition(abandoned: bool, iteration: int, probes_this_seed: int,
                           budget: BudgetFile,
                           remaining: LedgerSnapshot) -> Optional[str]:
    """Decide which of FR-16.3's conditions, or FR-16.6's, ends this seed.

    Returns:
        one of TERMINATING_CONDITIONS, or None while the seed continues.
    Worker:
        pure.
    Raises:
        nothing.
    """
    if abandoned:
        return "abandoned"
    if iteration >= budget.per_seed_iteration_cap:
        return "iteration_cap"
    if probes_this_seed >= budget.per_seed_probe_cap:
        return "probe_cap"
    if remaining.spent >= remaining.cap:
        return "arm_allowance"
    return None


@ChiaFunction(max_retries=0)
def build_feedback(results: list, previous: Optional[FeedbackBundle], seed_sha: str,
                   iteration: int, dispatched_probe_ids: list, *,
                   run_manifest_id: str, budget: BudgetFile,
                   remaining: LedgerSnapshot,
                   probes_this_seed: int) -> dict:
    """Build one seed's feedback bundle for *iteration* from the previous one's results.

    One entry per dispatched probe id, in the dispatched order, carrying only
    what FR-16.1 lists and nothing `_FEEDBACK_DENY` names. The bundle is empty
    on the first iteration, which has no previous one, and empty on the
    mutation arm, which receives no feedback at all (FR-16.2): the arm is read
    from *remaining*, the snapshot being the arm's own view of its budget.

    FR-16.6's abandonment is decided by comparing this iteration's multiset of
    `(build_status, stopping_reason)` pairs against the previous bundle's. The
    mutation arm's bundle carries no entries, so that multiset does not exist
    for it and a mutation-arm seed is never abandoned here; the asymmetry is
    FR-16.2's and not this function's.

    Returns:
        {"bundle": FeedbackBundle, "counters": CounterBlock}. §3.11 requires a
        block of every node of §3.2 and §2.5's stage list named none a bundle
        belongs to, which errata row 22 called A5's real obstacle; "feedback" is
        that name, added to `_COUNTER_STAGES` at the join. The bundle is
        validated, with `entries` one per dispatched probe id
        (empty on iteration 1 and on the mutation arm), `abandoned` and its
        `abandon_reason` per FR-16.6, and `terminating_condition` one of
        TERMINATING_CONDITIONS or None.
    Worker:
        `@ChiaFunction(max_retries=0)` on the head, 120 s `[DEFAULT]` enforced
        by the driver (§3.2); no worker resource, no database handle.
    Raises:
        ContractError from `contract.validate` on a malformed bundle, E008 from
        `bound_text` on a reduced text over the cap with no companion path, and
        ValueError when *results* holds two results for one probe id or a
        result for a probe that was never dispatched.
    """
    started_at = time.monotonic()
    by_id: dict = {}
    for result in results:
        if result.probe_id in by_id:
            raise ValueError(f"two ProbeResults for probe {result.probe_id!r}")
        by_id[result.probe_id] = result
    unknown = sorted(set(by_id) - set(dispatched_probe_ids))
    if unknown:
        raise ValueError(f"ProbeResults for probes that were not dispatched: {unknown}")

    cap = budget.artefact_inline_cap_bytes
    entries = [_entry(by_id.get(probe_id), probe_id, cap)
               for probe_id in dispatched_probe_ids]
    if iteration <= 1 or remaining.arm == "mutation":
        entries = []

    this_iteration = _abandon_multiset(entries)
    last_iteration = _abandon_multiset(previous.entries) if previous is not None else None
    abandoned = (this_iteration is not None and this_iteration == last_iteration)
    reason = ", ".join(f"{_ABANDON_STAGE}:{pair} x{count}"
                       for pair, count in sorted(this_iteration.items())
                       ) if abandoned else None

    bundle = FeedbackBundle(
        run_manifest_id=run_manifest_id, seed_sha=seed_sha, arm=remaining.arm,
        iteration=iteration, entries=entries, abandoned=abandoned,
        terminating_condition=_terminating_condition(
            abandoned, iteration, probes_this_seed, budget, remaining),
        abandon_reason=reason)
    validate(bundle)
    return {"bundle": bundle,
            "counters": CounterBlock(
                stage="feedback", started=len(dispatched_probe_ids),
                completed=len(entries),
                failed=len(dispatched_probe_ids) - len(entries),
                seconds=time.monotonic() - started_at)}


__all__ = ["build_feedback", "RESULT_MISSING", "TERMINATING_CONDITIONS"]
