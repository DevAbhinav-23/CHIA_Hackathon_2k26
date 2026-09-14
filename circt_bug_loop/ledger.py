"""ledger_entry: append one charge, aggregate them, decide when an arm stops.

A6b. Head-side and pure but for the store (03-LLD.md 3.11). The primary budget
unit is one elapsed wall-clock second of an arm's fixed window W (G-48); every
other entry is per-stage occupancy and is an observation, not the budget, which
is what `scope` records.

Three things this module owns and no other does:

  * `price` turns tokens into money. The backend reports usage_metadata token
    counts and no price at all (`chia:chia/models/vertex.py:479-482`), so the
    arithmetic is the ledger's, over the two committed prices of budget.yaml,
    and a null token count yields a null cost rather than a zero: a zero is a
    measurement and a null is an absence (FR-14.6).
  * `accrue` prices the entry before it writes it, so no row is ever stored with
    tokens and no money, and it refuses a second arm_window entry for an arm,
    FR-14.4's "exactly one per arm per run" having had no enforcement point.
  * `stop_reason` is FR-18.10's three stop conditions. The USD cap is
    campaign-wide and not per-arm, deliberately: the window and the safety caps
    are per-arm and equal, which is what makes the head-to-head fair, while the
    money cap protects a credit balance and not the comparison, so it returns
    `campaign_spend_cap` for BOTH arms at once (3.11, NFR-08).

It imports `BudgetLedger` and `LoopStore` from store.py and no other name there:
FR-16.1's rule keeps the apparatus's records about candidates out of the supply
half, and `BudgetLedger` is the aggregate this module itself maintains.
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import (BudgetFile, ContractError,
                                            CounterBlock, LedgerEntry,
                                            validate)
from circt_bug_loop.store import BudgetLedger, LoopStore

#: The one stage whose entries count a generated probing input, which is what
#: FR-14.1's per-UTC-day input cap is counted in. One entry per probe, because
#: 3.11 fixes a probe as stage_3's unit of work.
_INPUT_STAGE = "stage_3"

#: The two arms a stop rule applies to. `shared` is a ledger arm and never an
#: arm that stops (FR-14.4).
_ARMS = ("seeded", "mutation")

#: The stop reasons, named once. `campaign_spend_cap` is 3.11's spelling; the
#: other four take the budget key they bind on, so a results table can print the
#: reason and the number side by side.
STOP_REASONS = ("campaign_spend_cap", "arm_window", "generated_inputs_per_day",
                "filings_total", "filings_per_day")


def price(tokens_in: Optional[int], tokens_out: Optional[int],
          budget: BudgetFile) -> Optional[float]:
    """Return the USD a turn cost, from budget.yaml's two prices, or None.

    tokens_in / 1e6 * price_usd_per_m_input_tokens
      + tokens_out / 1e6 * price_usd_per_m_output_tokens,
    rounded to six decimal places. The money comes from the committed file and
    never from the backend, which reports counts and no price, so a usage dict
    carrying a cost of its own is ignored here by construction.

    Returns:
        float, rounded to six decimal places; None when either count is None.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        TypeError when a count is neither an int nor None.
    """
    if tokens_in is None or tokens_out is None:
        return None
    return round(tokens_in / 1e6 * budget.price_usd_per_m_input_tokens
                 + tokens_out / 1e6 * budget.price_usd_per_m_output_tokens, 6)


@ChiaFunction(max_retries=0)
def accrue(entry: LedgerEntry, db_path: str, budget: BudgetFile) -> dict:
    """Price *entry* and append it to ledger_entry. Nothing ever updates a row.

    `observed.cost_usd` is overwritten with `price`'s answer before the write,
    so the ledger's money is always its own arithmetic over budget.yaml's two
    prices. `metered` is left as the caller set it: it is FR-14.8's flag, "is
    this stage on the primary unit", and not FR-14.6's, "are this stage's tokens
    observed". Stage 7 is the one stage where the two disagree, being metered
    with null tokens because CHIA's `_turn` dispatches remotely and the counting
    copy of the LLM dies on the worker.

    Returns:
        {"counters": CounterBlock}, one entry appended at stage "ledger". The
        node has nothing else to return, and 3.11 requires the block of every
        node of 3.2, so the block is the whole return.
    Worker:
        {"num_cpus": 0.1} per statement, on the head where loop.db lives.
    Raises:
        ContractError from contract.validate on a malformed entry, and E005 on
        a second arm_window entry for one arm of one run; sqlite3.IntegrityError
        on a repeated entry_id, which is how a double charge is detected rather
        than absorbed (6.4 rule 3).
    """
    started_at = time.monotonic()
    entry.observed = dict(entry.observed)
    entry.observed["cost_usd"] = price(entry.observed.get("tokens_in"),
                                       entry.observed.get("tokens_out"), budget)
    validate(entry)
    store = LoopStore(db_path)
    if entry.scope == "arm_window":
        existing = store.query_one(
            "SELECT entry_id FROM ledger_entry WHERE run_manifest_id = ? "
            "AND arm = ? AND scope = 'arm_window'",
            (entry.run_manifest_id, entry.arm))
        if existing is not None:
            raise ContractError(
                "E005_CONDITIONAL_REQUIRED",
                f"exactly one arm_window entry exists per arm per run "
                f"(FR-14.4); {entry.arm!r} already has {existing['entry_id']!r}")
    store.insert("ledger_entry", {
        "entry_id": entry.entry_id,
        "run_manifest_id": entry.run_manifest_id,
        "arm": entry.arm,
        "scope": entry.scope,
        "stage": entry.stage,
        "unit": entry.unit,
        "amount": entry.amount,
        "metered": int(entry.metered),
        "observed_json": json.dumps(entry.observed, sort_keys=True),
        "timestamp_utc": entry.timestamp_utc,
        "stop_reason": entry.stop_reason,
    })
    return {"counters": CounterBlock(
        stage="ledger", started=1, completed=1, failed=0,
        seconds=time.monotonic() - started_at)}


def aggregate(run_manifest_id: str, db_path: str, *, today: str = None) -> BudgetLedger:
    """Sum one run's ledger into the aggregate A6b maintains.

    A view over ledger_entry, plus the two filing counts, which live in the
    `filing` table because that is where a filing is recorded. Per-arm sums take
    the arm-specific entries only: `shared` spend, which is the image build, the
    mirror, the corpus, the pin selection and the mutator synthesis, is reported
    beside the two arms, never folded into one and never split between them
    (FR-14.4). `spend_usd` is campaign-wide and sums both arms AND `shared`,
    because the money cap protects a credit balance rather than the comparison.

    *today* is the UTC calendar day the per-day caps are counted over, as
    YYYY-MM-DD; it defaults to the day this call is made, the caps being counted
    by calendar day and not by rolling window (FR-13.8, FR-14.1).

    Returns:
        BudgetLedger, every field populated, stop_reason per arm from the
        entries that recorded one.
    Worker:
        {"num_cpus": 0.1} per query, on the head.
    Raises:
        sqlite3.Error from either query.
    """
    day = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    store = LoopStore(db_path)
    rows = store.query("SELECT * FROM ledger_entry WHERE run_manifest_id = ? "
                       "ORDER BY timestamp_utc, entry_id", (run_manifest_id,))

    per_arm_window: dict = {}
    per_arm_stage: dict = {arm: {} for arm in _ARMS}
    shared_stage: dict = {}
    inputs_today: dict = {arm: 0 for arm in _ARMS}
    per_arm_spend_usd: dict = {}
    stops: dict = {arm: None for arm in _ARMS}
    spend_usd = 0.0

    for row in rows:
        arm, stage, amount = row["arm"], row["stage"], float(row["amount"])
        observed = json.loads(row["observed_json"])
        cost = observed.get("cost_usd")
        if cost is not None:
            spend_usd += float(cost)
            per_arm_spend_usd[arm] = per_arm_spend_usd.get(arm, 0.0) + float(cost)
        if row["scope"] == "arm_window":
            per_arm_window[arm] = amount
        elif arm == "shared":
            shared_stage[stage] = shared_stage.get(stage, 0.0) + amount
        else:
            bucket = per_arm_stage.setdefault(arm, {})
            bucket[stage] = bucket.get(stage, 0.0) + amount
        if (row["scope"] == "stage" and stage == _INPUT_STAGE and arm in inputs_today
                and row["timestamp_utc"][:10] == day):
            inputs_today[arm] += 1
        if row["stop_reason"] is not None and arm in stops:
            stops[arm] = row["stop_reason"]

    # THIS RUN's filings (W11). `filing` is keyed by candidate and carries no
    # run id of its own, so the predicate is the join. A lifetime count here is
    # what made `stop_reason` return `filings_total` from the very first
    # `_arm_stop` of every campaign after the tenth approval: `loop.db` persists
    # across runs and `--resume` depends on that.
    filings = store.query(
        "SELECT filing.approved_at_utc FROM filing "
        "JOIN candidate ON candidate.candidate_id = filing.candidate_id "
        "WHERE candidate.run_manifest_id = ?", (run_manifest_id,))
    lifetime = store.query("SELECT approved_at_utc FROM filing")
    return BudgetLedger(
        filings_lifetime_total=len(lifetime),
        run_manifest_id=run_manifest_id,
        per_arm_window=per_arm_window,
        per_arm_stage=per_arm_stage,
        shared_stage=shared_stage,
        inputs_today=inputs_today,
        filings_today=sum(1 for f in filings if f["approved_at_utc"][:10] == day),
        filings_total=len(filings),
        spend_usd=round(spend_usd, 6),
        per_arm_spend_usd={a: round(v, 6) for a, v in per_arm_spend_usd.items()},
        stop_reason=stops)


def stop_reason(ledger: BudgetLedger, arm: str, budget: BudgetFile) -> Optional[str]:
    """Return the cap or window that stops *arm*, or None.

    FR-18.10's three stop conditions, in a fixed order because the function is a
    pure predicate over an aggregate and cannot know which bound first in time:
    the campaign-wide USD cap, then the arm's window on the primary unit, then
    the three safety caps. The USD cap is first because it is the only one that
    stops the OTHER arm too: the driver stops the arm in flight and never starts
    the other (3.11).

    Returns:
        one of STOP_REASONS, or None when nothing binds.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ContractError (E004) when *arm* is not one of the two arms; `shared` is
        a ledger arm and never an arm that stops.
    """
    if arm not in _ARMS:
        raise ContractError("E004_BAD_ENUM",
                            f"stop_reason takes an arm, not {arm!r}")
    if ledger.spend_usd >= budget.campaign_spend_cap_usd:
        return "campaign_spend_cap"
    if ledger.per_arm_window.get(arm, 0.0) >= budget.arm_window_seconds:
        return "arm_window"
    if ledger.inputs_today.get(arm, 0) >= budget.generated_inputs_per_day:
        return "generated_inputs_per_day"
    # A cap of ZERO means "this run files nothing", and not "this run does
    # nothing" (W-18). `0 >= 0` is true before a single probe is written, so a
    # pilot registered with both filing caps at zero - which is how a run is
    # registered as unable to file at all - stopped its first arm in 18
    # milliseconds with `stop_reason="filings_total"` and never generated
    # anything. Nothing is lost by the exemption: `approve.py` enforces both
    # caps independently at the one place a report is filed, and refuses every
    # filing at a cap of zero. A POSITIVE cap stops the arm exactly as before.
    if budget.filings_total and ledger.filings_total >= budget.filings_total:
        return "filings_total"
    if budget.filings_per_day and ledger.filings_today >= budget.filings_per_day:
        return "filings_per_day"
    return None
