"""Pilot 8's fired candidate through the driver's own stage 7, once, live."""
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

from circt_bug_loop import bug_loop
from circt_bug_loop.contract import schema
from circt_bug_loop.store import (LoopStore, OracleVerdict, ReducedCase, Report,
                                  load_candidate)

RUN = "138400b18e44411c94f7d6344fa19286"
CANDIDATE = "c-p-4b1c72262db2"
REPO = Path(__file__).resolve().parents[2]
DB = REPO / "circt_bug_loop" / "loop.db"

#: This step's own cap, which is not the pilot's registered 6.00.
CAP_USD = 10.0


def _record(row: dict, cls):
    """Rebuild one stored dataclass from its row, JSON columns included."""
    return cls(**{field.name: (row[field.name] if field.name in row
                               else json.loads(row[f"{field.name}_json"]))
                  for field in dataclasses.fields(cls)})


def _load(store: LoopStore) -> tuple:
    """Pilot 8's manifest, candidate, spec, reduced case, verdict and report."""
    run = store.query_one("SELECT * FROM run WHERE run_manifest_id = ?", (RUN,))
    manifest = schema.from_json(run["manifest_json"], schema.RunManifest)
    candidate = load_candidate(store, CANDIDATE)
    probe = store.query_one("SELECT * FROM probe WHERE probe_id = ?",
                            (candidate.probe_id,))
    one = store.query_one
    return (manifest, candidate,
            schema.from_json(probe["spec_json"], schema.ProbeSpec),
            _record(one("SELECT * FROM reduced_case WHERE probe_id = ?",
                        (candidate.probe_id,)), ReducedCase),
            _record(one("SELECT * FROM oracle_verdict WHERE probe_id = ?",
                        (candidate.probe_id,)), OracleVerdict),
            _record(one("SELECT * FROM report WHERE candidate_id = ?",
                        (CANDIDATE,)), Report))


def _budget(manifest, budget_file_sha: str):
    """The budget pilot 8 ran with, from its own copy, capped at this step's own."""
    document = yaml.safe_load((Path(manifest.artefact_root) / RUN / "budget.yaml")
                              .read_text(encoding="utf-8"))
    budget = schema.BudgetFile(budget_file_sha=budget_file_sha, **document)
    schema.validate(budget)
    return dataclasses.replace(budget, campaign_spend_cap_usd=CAP_USD)


def _ledger(store: LoopStore) -> list:
    """Every stage-7 ledger row this smoke wrote, money block included."""
    return [dict(row, observed=json.loads(row.pop("observed_json")))
            for row in store.query(
                "SELECT * FROM ledger_entry WHERE run_manifest_id = ? "
                "AND stage = 'stage_7'", (RUN,))]


def main(argv=None) -> int:
    """Copy the store, build the driver's own context, run stage 7 once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", required=True,
                        help="a directory for the store copy and the counters")
    parser.add_argument("--dedup-verdict", default="new",
                        help="what the screen said; 'new' is what stage 7 needs")
    args = parser.parse_args(argv)

    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    # The pilot's own record is read-only here: stage 7 writes to a COPY.
    shutil.copyfile(DB, work / "loop.db")
    store = LoopStore(str(work / "loop.db"))
    manifest, candidate, spec, reduced, verdict, report = _load(store)
    budget = _budget(manifest, manifest.budget_file_sha)

    shipped = bug_loop.stage_shipped()
    ray.init(address="auto", runtime_env=bug_loop.runtime_env(shipped),
             ignore_reinit_error=True)
    dispatch = bug_loop.Dispatch(remote=True,
                                 head_node_id=bug_loop._head_node_id())
    campaign = bug_loop.Campaign(
        manifest=manifest, budget=budget, store=store,
        stages=bug_loop.default_stages(), dispatch=dispatch,
        counters=bug_loop.CounterLog(RUN, str(work / "results")),
        repair_enabled=True, head_options=dispatch.head_options())

    out = {"verdicts": {}, "stages": []}
    started = time.monotonic()
    repair = bug_loop._drive_repair(
        campaign, spec, candidate, reduced, verdict,
        SimpleNamespace(verdict=args.dedup_verdict), {"report": report}, out,
        SimpleNamespace(stopping_stage="gate"))
    print(json.dumps({
        "wall_seconds": round(time.monotonic() - started, 3),
        "dedup_verdict": args.dedup_verdict,
        "cap_usd": CAP_USD,
        "stage_7_tool_iterations": budget.max_tool_iterations.get("stage_7"),
        "out": out,
        "repair": None if repair is None else dataclasses.asdict(repair),
        "ledger": _ledger(store),
        "counters": campaign.counters.totals,
        "counter_violations": campaign.counters.violations,
    }, indent=2, sort_keys=True))
    return 0 if repair is not None and repair.status != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
