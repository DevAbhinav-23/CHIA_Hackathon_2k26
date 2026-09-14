"""ledger_entry: append one charge, aggregate them, decide when an arm stops."""
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

#: The one stage whose entries count a generated probing input.
_INPUT_STAGE = "stage_3"

#: The two arms a stop rule applies to.
_ARMS = ("seeded", "mutation")

#: The stop reasons, named once.
STOP_REASONS = ("campaign_spend_cap", "arm_window", "generated_inputs_per_day",
                "filings_total", "filings_per_day")


def price(tokens_in: Optional[int], tokens_out: Optional[int],
          budget: BudgetFile) -> Optional[float]:
    """Return the USD a turn cost, from budget.yaml's two prices, or None."""
    if tokens_in is None or tokens_out is None:
        return None
    return round(tokens_in / 1e6 * budget.price_usd_per_m_input_tokens
                 + tokens_out / 1e6 * budget.price_usd_per_m_output_tokens, 6)


@ChiaFunction(max_retries=0)
def accrue(entry: LedgerEntry, db_path: str, budget: BudgetFile) -> dict:
    """Price *entry* and append it to ledger_entry.

    Returns:
        {"counters": CounterBlock}, one entry appended at stage "ledger".
    Worker:
        {"num_cpus": 0.1} per statement, on the head where loop.db lives.
    Raises:
        ContractError from contract.validate on a malformed entry.
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
    """Sum one run's ledger into the aggregate A6b maintains."""
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
        if cost is None:
            # A turn the loop cannot meter counts at what it was authorised for,
            # which is the only bound the campaign cap has on it (§3.8).
            cost = observed.get("authorised_usd")
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

    # THIS RUN's filings (W11).
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
    """Return the cap or window that stops *arm*, or None."""
    if arm not in _ARMS:
        raise ContractError("E004_BAD_ENUM",
                            f"stop_reason takes an arm, not {arm!r}")
    if ledger.spend_usd >= budget.campaign_spend_cap_usd:
        return "campaign_spend_cap"
    if ledger.per_arm_window.get(arm, 0.0) >= budget.arm_window_seconds:
        return "arm_window"
    if ledger.inputs_today.get(arm, 0) >= budget.generated_inputs_per_day:
        return "generated_inputs_per_day"
    # A cap of ZERO means "this run files nothing".
    if budget.filings_total and ledger.filings_total >= budget.filings_total:
        return "filings_total"
    if budget.filings_per_day and ledger.filings_today >= budget.filings_per_day:
        return "filings_per_day"
    return None
