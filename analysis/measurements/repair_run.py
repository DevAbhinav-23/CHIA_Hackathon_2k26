"""The gate-passed candidate through the driver's own stage 7, once, live.

`repair_smoke.py` with the verdict forcing removed: the dedup verdict is READ
from the store, so `_drive_repair`'s own `!= "new"` guard is what admits the
chain, and the budget is the registered `circt_bug_loop/budget.yaml`.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import ray
import yaml

from circt_bug_loop import bug_loop, ledger
from circt_bug_loop.contract import schema
from circt_bug_loop.store import (LoopStore, OracleVerdict, ReducedCase, Report,
                                  latest, load_candidate)

RUN = "f1e4fef5db314bef8d187bceca8f6a80"
CANDIDATE = "c-p-a2cb61b8d0aa"
REPO = Path(__file__).resolve().parents[2]
DB = REPO / "circt_bug_loop" / "loop.db"
BUDGET = REPO / "circt_bug_loop" / "budget.yaml"
CAP_USD = None     #: None: the run's REGISTERED campaign_spend_cap_usd applies (architect, 2026-09-15)


def _record(row: dict, cls):
    """Rebuild one stored dataclass from its row, JSON columns included.

    A field with no column keeps its default: `OracleVerdict` carries contract
    2.4's `verifier_message`/`verifier_op`, columns of `verifier_error`.
    """
    return cls(**{f.name: (row[f.name] if f.name in row
                           else json.loads(row[f"{f.name}_json"]))
                  for f in dataclasses.fields(cls)
                  if f.name in row or f"{f.name}_json" in row})


def _load(store: LoopStore) -> tuple:
    """The run's manifest, candidate, spec, reduced case, verdict, report, dedup."""
    run = store.query_one("SELECT * FROM run WHERE run_manifest_id = ?", (RUN,))
    candidate = load_candidate(store, CANDIDATE)
    probe = store.query_one("SELECT * FROM probe WHERE probe_id = ?",
                            (candidate.probe_id,))
    one = store.query_one
    return (schema.from_json(run["manifest_json"], schema.RunManifest), candidate,
            schema.from_json(probe["spec_json"], schema.ProbeSpec),
            _record(one("SELECT * FROM reduced_case WHERE probe_id = ?",
                        (candidate.probe_id,)), ReducedCase),
            _record(one("SELECT * FROM oracle_verdict WHERE probe_id = ?",
                        (candidate.probe_id,)), OracleVerdict),
            _record(one("SELECT * FROM report WHERE candidate_id = ?",
                        (CANDIDATE,)), Report),
            SimpleNamespace(verdict=latest(store, "dedup_verdict",
                                           CANDIDATE)["verdict"]))


def _budget(budget_file_sha: str):
    """The REGISTERED budget file, capped at this step's own money cap."""
    budget = schema.BudgetFile(budget_file_sha=budget_file_sha,
                               **yaml.safe_load(BUDGET.read_text(encoding="utf-8")))
    schema.validate(budget)
    if CAP_USD is None:
        return budget
    return dataclasses.replace(budget, campaign_spend_cap_usd=CAP_USD)


def main(argv=None) -> int:
    """Copy the store, build the driver's own context, run stage 7 once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True, help="store copy, counters")
    work = Path(parser.parse_args(argv).work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    # The run's own record is read-only here: stage 7 writes to a COPY.
    shutil.copyfile(DB, work / "loop.db")
    store = LoopStore(str(work / "loop.db"))
    manifest, candidate, spec, reduced, verdict, report, dedup = _load(store)
    budget = _budget(manifest.budget_file_sha)

    ray.init(address="auto", ignore_reinit_error=True,
             runtime_env=bug_loop.runtime_env(bug_loop.stage_shipped()))
    dispatch = bug_loop.Dispatch(remote=True,
                                 head_node_id=bug_loop._head_node_id())
    campaign = bug_loop.Campaign(
        manifest=manifest, budget=budget, store=store,
        stages=bug_loop.default_stages(), dispatch=dispatch,
        counters=bug_loop.CounterLog(RUN, str(work / "results")),
        repair_enabled=True, head_options=dispatch.head_options())

    out = {"verdicts": {}, "stages": []}
    spend_at_start = campaign.spend_usd()
    started = time.monotonic()
    repair = bug_loop._drive_repair(
        campaign, spec, candidate, reduced, verdict, dedup, {"report": report},
        out, SimpleNamespace(stopping_stage="gate"))
    print(json.dumps({
        "wall_seconds": round(time.monotonic() - started, 3),
        "dedup_verdict": dedup.verdict,
        "cap_usd": CAP_USD,
        "spend_usd_at_start": spend_at_start,
        "stage_7_tool_iterations": budget.max_tool_iterations.get("stage_7"),
        "out": out,
        "repair": None if repair is None else dataclasses.asdict(repair),
        # Every stage-7 ledger row this attempt wrote, money block included.
        "ledger": [dict(r, observed=json.loads(r.pop("observed_json")))
                   for r in store.query(
                       "SELECT * FROM ledger_entry WHERE run_manifest_id = ? "
                       "AND stage = 'stage_7'", (RUN,))],
        "counters": campaign.counters.totals,
        "counter_violations": campaign.counters.violations,
    }, indent=2, sort_keys=True))
    return 0 if repair is not None and repair.status != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
