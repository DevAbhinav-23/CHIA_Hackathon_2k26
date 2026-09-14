"""The bundle the seeded arm reads at the start of its next iteration."""
from __future__ import annotations

import time
from collections import Counter
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import (BudgetFile, CounterBlock,
                                            FeedbackBundle, FeedbackEntry,
                                            LedgerSnapshot, ProbeResult,
                                            bound_text, validate)

#: FR-16.4's deny-list, `03-LLD.md` §3.11 verbatim.
_FEEDBACK_DENY = ("candidate_id", "candidate_count", "candidates", "fingerprint",
                  "dedup_verdict", "dedup_basis", "gate_answers", "gate_decision",
                  "taxonomy_bucket", "q1_reproduce", "q2_minimal", "q3_valid",
                  "q4_new", "precision", "bug_count", "confirmed", "filing",
                  "issue_number", "issue_url", "repair_status", "triage_class")

#: FR-16.6's three build statuses.
_ABANDON_STATUSES = frozenset({"parse_error", "timeout", "oom"})

#: The stage FR-16.6 counts over.
_ABANDON_STAGE = "stage_3"

#: The reason an entry carries when the probe was dispatched and no `ProbeResult` came back (`04-Test-Plan.md` T-U-feed-02).
RESULT_MISSING = "result_missing"

#: FR-16.3's three terminating conditions and FR-16.6's.
TERMINATING_CONDITIONS = ("abandoned", "iteration_cap", "probe_cap",
                          "arm_allowance")


def _reason(result: ProbeResult) -> str:
    """Render one result's `(build_status, stopping_reason)` pair as the entry's reason."""
    return (f"{result.build_status}:{result.stopping_reason}"
            if result.stopping_reason else result.build_status)


def _summary(result: ProbeResult) -> Optional[str]:
    """Render the oracle summary FR-16.1 asks for, from the result alone."""
    if not result.oracle_fired:
        return None
    if result.oracle_class == "assertion" and result.assertion_text:
        site = result.assertion_site or ""
        return f"{result.assertion_text}\n{site}" if site else result.assertion_text
    return f"died by {result.signal}" if result.signal else None


def _entry(result: Optional[ProbeResult], probe_id: str, cap: int) -> FeedbackEntry:
    """Build one entry for one dispatched probe, present or missing."""
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
    """Count one iteration's stage-3 failure pairs, or report that it has none."""
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
    """Decide which of FR-16.3's conditions, or FR-16.6's, ends this seed."""
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

    Returns:
        {"bundle": FeedbackBundle, "counters": CounterBlock}.
    Worker:
        `@ChiaFunction(max_retries=0)` on the head, 120 s `[DEFAULT]` enforced by the driver (§3.2).
    Raises:
        ContractError from `contract.validate` on a malformed bundle.
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
