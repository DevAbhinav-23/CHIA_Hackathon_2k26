#!/usr/bin/env python3
"""T3: drive the mutation arm alone, in rounds, locally: one process, no Ray, no model.

Runs INSIDE the campaigns' image (chia-circt-assert:eade0de61bc5, the manifest's
image digest) with the repo, the artefact root and the corpus clone mounted at
their host paths. Everything a campaign job did is reused: the registered
budget (check 1), campaign 2's recorded seed records, image, pin and mirror
(the same corpus head and seed order), the frozen mutator set, and
`campaign_drive`. Two substitutions, both because no model may run: stage 6 is
`recorded_report` (no turn) and stage 7 is off.
"""
import argparse
import dataclasses
import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from circt_bug_loop import bug_loop, mutators  # noqa: E402
from circt_bug_loop.contract import schema  # noqa: E402
from circt_bug_loop.store import (ImageSpec, LoopStore, add_probe_mutation_round,  # noqa: E402
                                  widen_fingerprint_basis)

#: Campaign 2's mutation job: its manifest, seeds, image and mirror are this run's.
SOURCE_RUN = "91e58983716b46e2902c01cc7cde10ab"
LOCAL = "none: local in-process run (analysis/review/run_review_mutation.py), no Ray cluster"


def utc(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def source_rows(db_path: str) -> dict:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    one = lambda sql: dict(db.execute(sql, (SOURCE_RUN,)).fetchone())
    rows = {"manifest": one("SELECT manifest_json FROM run WHERE run_manifest_id=?"),
            "mirror": one("SELECT * FROM issue_mirror_meta WHERE run_manifest_id=?"),
            "seeds": [dict(r) for r in db.execute(
                "SELECT record_json, exclusion_reason FROM seed WHERE run_manifest_id=? "
                "ORDER BY rowid", (SOURCE_RUN,))],
            "sdk_map": [dict(r) for r in db.execute(
                "SELECT sdk_tag, seed_shas_json FROM sdk_map WHERE run_manifest_id=?",
                (SOURCE_RUN,))]}
    manifest = json.loads(rows["manifest"]["manifest_json"])
    image = dict(db.execute("SELECT * FROM image WHERE image_digest=?",
                            (manifest["image_spec"]["image_digest"],)).fetchone())
    rows["image"] = ImageSpec(
        circt_sha=image["circt_sha"], sdk_tag=image["sdk_tag"],
        targets=json.loads(image["targets_json"]), flag_string=image["flag_string"],
        cmake_args=json.loads(image["cmake_args_json"]), image_digest=image["image_digest"],
        image_tag=image["image_tag"], verilator_version=image["verilator_version"],
        slang_enabled=bool(image["slang_enabled"]),
        lit_discovery_ok=bool(image["lit_discovery_ok"]),
        lit_discovered_count=image["lit_discovered_count"],
        assertion_nonreferencing=json.loads(image["assertion_nonreferencing_json"]),
        tool_hashes=json.loads(image["tool_hashes_json"]))
    db.close()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", required=True)
    parser.add_argument("--db", default=bug_loop.DB_PATH)
    parser.add_argument("--artefact-root", required=True)
    parser.add_argument("--clone", required=True)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--window-seconds", type=float, default=None,
                        help="smoke only: override the registered window")
    args = parser.parse_args()

    started = datetime.now(timezone.utc)
    budget = bug_loop.check_01_budget_registered(
        budget_path=args.budget, repo_root=str(REPO), run_start_utc=utc(started),
        campaign=True)
    tag, commit = bug_loop.budget_module.registration(str(REPO))
    if args.window_seconds is not None:
        budget = dataclasses.replace(budget, arm_window_seconds=args.window_seconds)
    rows = source_rows(args.db)
    image = rows["image"]
    # Check 7's question, asked here: these binaries are the manifest's.
    for tool, expected in sorted(image.tool_hashes.items()):
        actual = hashlib.sha256(Path(bug_loop.CIRCT_BIN_DIR, tool).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit(f"{tool} hashes to {actual}, the manifest says {expected}")
    source = schema.from_json(rows["manifest"]["manifest_json"], schema.RunManifest)
    if mutators.set_sha256() != source.mutator_set_sha:
        raise SystemExit("the mutator set on disk is not campaign 2's")
    seeds = [schema.from_json(r["record_json"], schema.SeedRecord) for r in rows["seeds"]]
    if {s.corpus_head_sha for s in seeds} != {budget.corpus_head_sha}:
        raise SystemExit("the recorded seeds are not at the budget's corpus head")

    run_id = uuid.uuid4().hex
    manifest = dataclasses.replace(
        source, run_manifest_id=run_id, started_utc=utc(started), ended_utc=None,
        arm_window_seconds=budget.arm_window_seconds, budget_file_sha=budget.budget_file_sha,
        artefact_root=args.artefact_root, cluster_yaml_sha=LOCAL, apparatus_concurrency=1,
        llm_concurrency=0, shard=None,
        stages_metered=bug_loop.stages_metered(arms=("mutation",), repair_backend="vertex",
                                               repair_enabled=False, model_turns=False))
    schema.validate(manifest)

    store = LoopStore(args.db)
    widen_fingerprint_basis(store)
    add_probe_mutation_round(store)
    mirror = {k: rows["mirror"][k] for k in ("refreshed_utc", "issues_mirrored",
                                              "issue_cap", "cap_bound", "state",
                                              "comments_mirrored")}
    bug_loop.write_run_rows(
        store, manifest, image_spec=image,
        mined={"seeds": seeds,
               "sdk_map": {r["sdk_tag"]: json.loads(r["seed_shas_json"])
                           for r in rows["sdk_map"]},
               "exclusions": {s.seed_sha: r["exclusion_reason"]
                              for s, r in zip(seeds, rows["seeds"]) if r["exclusion_reason"]},
               "sv_seeds": []},
        mirror=mirror, registration=(tag, commit))
    dispatch = bug_loop.Dispatch(remote=False)
    bug_loop.accrue_offline(store, manifest, budget, dispatch=dispatch)
    run_root = Path(args.artefact_root) / run_id
    (run_root / "results").mkdir(parents=True, exist_ok=True)
    (run_root / "manifest.json").write_text(schema.to_json(manifest), encoding="utf-8")
    (run_root / "budget.yaml").write_text(Path(args.budget).read_text(), encoding="utf-8")
    deadline = started + timedelta(seconds=budget.arm_window_seconds)
    Path(args.status_file).write_text(
        f"run_manifest_id: {run_id}\nstarted_utc: {utc(started)}\n"
        f"deadline_utc: {utc(deadline)}\narm_window_seconds: {budget.arm_window_seconds}\n"
        f"registration: {tag} {commit}\nbudget_file_sha: {budget.budget_file_sha}\n"
        f"db: {args.db}\nartefact_root: {args.artefact_root}\n", encoding="utf-8")
    print(f"run {run_id} started {utc(started)} deadline {utc(deadline)} "
          f"({len(seeds)} seeds, registration {tag})", flush=True)

    stages = dataclasses.replace(bug_loop.default_stages(),
                                 triage_report=bug_loop.recorded_report)
    # counters.json is written once at the end: CounterLog rewrites it on every
    # stage call, and its violations list grows by 162 per round here.
    counters = bug_loop.CounterLog(run_id, None)
    campaign = bug_loop.Campaign(
        manifest=manifest, budget=budget, store=store, stages=stages, dispatch=dispatch,
        counters=counters, clone_path=args.clone, image_spec=image,
        repair_enabled=False, mutation_rounds=True)
    try:
        outcome = bug_loop.campaign_drive(campaign, seeds, arms=["mutation"])
    finally:
        counters.results_dir = str(run_root / "results")
        counters.write()
    bug_loop.finish_run(store, manifest, bug_loop.utc_now())
    print(json.dumps(outcome["arms"], sort_keys=True, indent=2), flush=True)
    with open(args.status_file, "a", encoding="utf-8") as status:
        status.write(f"ended_utc: {bug_loop.utc_now()}\n"
                     f"outcome: {json.dumps(outcome['arms'], sort_keys=True)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
