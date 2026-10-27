#!/usr/bin/env python3
"""Re-gate run da63067c (review-mutation-1), whose Q1 re-run never found a second worker.

The local run had one machine and no `circt` Ray node, so `gate._rerun` timed out and
all 45 decisions stopped at Q1 as `unscheduled`. `gate` re-asks the four questions with
`gate.gate_decide` itself, on the host (~/.cache/chia-venv), with `gate._dispatch`
swapped for one fresh `docker run --rm` of the run's image per call: Q1's `gate_rerun`
and Q3's `gate_validate` each get a new container. `bug_loop.write_gate_decision`
appends the rows; the old ones stay. `check` runs every candidate's repro command and
reduced case on the review-fixes host build (read-only). `numbers` prints the funnel
and `review_numbers.py`'s section-a measures for the run (read-only).

  ~/.cache/chia-venv/bin/python analysis/review/regate_mutation.py gate|check|numbers [TSV]
"""
import collections
import json
import os
import shlex
import signal
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
RUN = "da63067ca68e469487fd51e32b44f3ea"
DB = REPO / "circt_bug_loop" / "loop.db"
BUDGET = REPO / "circt_bug_loop" / "budget-review-mutation.yaml"
IMAGE = "chia-circt-assert:eade0de61bc5"
ART = Path.home() / "bugloop-artefacts"
IO = ART / RUN / "regate"
#: Container start-up, on top of the wait `gate._rerun` already allows.
START_S = 30
NOTE = "regate_mutation.py: Q1 and Q3 each in a fresh docker run --rm of the run's image"
OPERATOR_STOP_UTC = "2026-10-27T07:42:42+00:00"     # ~/bugloop-artefacts/review-mutation-1.status
REVIEW = Path.home() / ".cache/review-main-build"
REVIEW_ENV = {**os.environ, "LD_LIBRARY_PATH":
              f"{REVIEW}/sdk/lib:{Path.home()}/.cache/chia-pin-smoke/shim"}


def call(name: str, spec_path: str, out_path: str) -> None:
    """Container side: one gate node, unwrapped, its JSON result written to *out_path*."""
    from circt_bug_loop import gate

    spec = json.loads(Path(spec_path).read_text())
    out = getattr(gate, name)._chia_original(*spec["args"], **spec["kwargs"])
    out.pop("counters", None)
    Path(out_path).write_text(json.dumps(out))


def container_dispatch(node, options, *args, timeout=None, **kwargs):
    """`gate._dispatch` with a fresh container per call; None if *timeout* passes first."""
    name = node._chia_original.__name__
    tag = f"{kwargs['candidate_id']}.{name}.{uuid.uuid4().hex[:8]}"
    spec, out = IO / f"{tag}.in.json", IO / f"{tag}.out.json"
    spec.write_text(json.dumps({"args": args, "kwargs": kwargs}))
    container = f"regate-{tag}"
    argv = ["docker", "run", "--rm", "--name", container,
            "--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp",
            "-v", f"{ART}:{ART}", "-v", f"{REPO}:{REPO}:ro", IMAGE,
            "python3", str(Path(__file__).resolve()), "call", name, str(spec), str(out)]
    try:
        done = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                              timeout=None if timeout is None else timeout + START_S)
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", container], capture_output=True)
        return None
    if done.returncode != 0:
        raise RuntimeError(f"{container} exited {done.returncode}: {done.stderr[-2000:]}")
    return json.loads(out.read_text())


def store_and_manifest():
    from circt_bug_loop import bug_loop
    from circt_bug_loop.store import LoopStore

    store = LoopStore(str(DB))
    return store, bug_loop.manifest_of(store, RUN)


def candidates(store) -> list:
    return store.query("SELECT candidate_id, probe_id FROM candidate WHERE run_manifest_id = ? "
                       "AND oracle_class <> 'differential' ORDER BY candidate_id", (RUN,))


def regate() -> int:
    from circt_bug_loop import bug_loop, gate
    from circt_bug_loop.budget import load_budget
    from circt_bug_loop.results import _repair_view
    from circt_bug_loop.store import latest, load_candidate

    store, manifest = store_and_manifest()
    image_id = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}}", IMAGE],
                              capture_output=True, text=True, check=True).stdout.strip()
    if image_id != manifest.image_spec["image_digest"]:
        raise SystemExit(f"{IMAGE} is {image_id}, the manifest's is "
                         f"{manifest.image_spec['image_digest']}")
    budget = load_budget(str(BUDGET), str(REPO), run_start_utc=manifest.started_utc)["budget"]
    IO.mkdir(parents=True, exist_ok=True)
    gate._dispatch = container_dispatch
    for row in candidates(store):
        cid = row["candidate_id"]
        if NOTE in (latest(store, "gate_decision", cid) or {}).get("answers_json", ""):
            continue                                # already re-gated: never append twice
        decision = gate.gate_decide._chia_original(
            load_candidate(store, cid), bug_loop.reduced_case_of(store, row["probe_id"]),
            bug_loop.dedup_verdict_of(store, cid, row["probe_id"]),
            _repair_view(store.query_one("SELECT * FROM repair WHERE candidate_id = ?", (cid,))),
            manifest, str(DB), limits=bug_loop.probe_limits(budget),
            top_n=budget.fingerprint_top_n, bin_dir=bug_loop.CIRCT_BIN_DIR,
            minimal_case_lines=budget.minimal_case_lines)["decision"]
        bug_loop.write_gate_decision(store, decision, notes={"regated": NOTE})
        print(cid, decision.stopped_at_question, decision.decision, decision.taxonomy_bucket,
              decision.q1_rerun_worker, flush=True)
    return 0


def signature(row: dict) -> str:
    """The text the candidate's failure prints: assertion, crashing function, or verifier line."""
    if row["oracle_class"] == "assertion":
        return row["assertion_text"]
    first, second = row["value"].splitlines()[:2]
    if row["oracle_class"] == "crash":
        return second.split()[0]
    return f"'{first}' op " + second.split(" op ", 1)[1].split(", but got")[0]


def run_review(argv: list) -> tuple:
    """(loop status, rc) of one argv on the review-fixes build, and its stderr."""
    from circt_bug_loop.probe_task import classify_build

    try:
        done = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                              env=REVIEW_ENV, timeout=120, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "timeout", None, ""
    sig = signal.Signals(-done.returncode).name if done.returncode < 0 else None
    return classify_build(done.returncode, sig, done.stderr, None)[0], done.returncode, done.stderr


def check() -> int:
    """Each candidate's original repro and reduced case on review-fixes: still the same failure?"""
    store, _ = store_and_manifest()
    rows = store.query(
        "SELECT c.candidate_id, c.oracle_class, c.assertion_text, f.value, o.repro_command, "
        "r.path FROM candidate c JOIN fingerprint f USING (candidate_id) JOIN oracle_verdict o "
        "USING (probe_id) JOIN reduced_case r USING (probe_id) WHERE c.run_manifest_id = ? "
        "ORDER BY f.value, c.candidate_id", (RUN,))
    out = []
    for row in rows:
        argv = shlex.split(row["repro_command"])
        tool = os.path.basename(argv[0])
        entry = {"candidate_id": row["candidate_id"], "tool": tool, "signature": signature(row)}
        if tool != "circt-opt":
            entry["review_fixes"] = f"not run: only circt-opt is built ({tool})"
        else:
            binary = str(REVIEW / "build/bin/circt-opt")
            for case, case_argv in (("original", [binary, *argv[1:]]),
                                    ("reduced", [binary, *argv[1:-1], row["path"]])):
                status, rc, stderr = run_review(case_argv)
                entry[case] = {"status": status, "rc": rc,
                               "same_failure": entry["signature"] in stderr}
        out.append(entry)
        print(json.dumps(entry), flush=True)
    return 0


def numbers(tsv: str) -> int:
    """The gate funnel from the latest rows, and review_numbers' section-a measures."""
    sys.path.insert(0, str(REPO / "analysis" / "review"))
    import review_numbers as rn

    db = rn.connect()
    funnel = collections.Counter()
    for (cid, answers, decision) in rn.q(db, """
            SELECT g.candidate_id, g.answers_json, g.decision FROM gate_decision g JOIN candidate c
            USING (candidate_id) WHERE c.run_manifest_id = ? AND g.rowid = (SELECT MAX(rowid)
            FROM gate_decision WHERE candidate_id = g.candidate_id) ORDER BY 1""", RUN):
        a = json.loads(answers)
        print(cid, *(a[k] for k in ("q1_reproduce", "q1_rerun_worker", "q2_minimal",
                                    "q3_valid", "q3_validity_basis", "q4_new", "q4_reason")),
              decision, sep="\t")
        funnel["candidates"] += 1
        for key in ("q1_reproduce", "q2_minimal", "q3_valid", "q4_new"):
            if not a[key]:
                break
            funnel[key] += 1
        funnel[f"decision {decision}"] += 1
    probes = rn.q1(db, "SELECT COUNT(*) FROM probe WHERE run_manifest_id = ?", RUN)
    fired = rn.q1(db, "SELECT COUNT(*) FROM probe_result WHERE run_manifest_id = ? "
                      "AND oracle_fired = 1", RUN)
    rn.VALIDITY_TSV = Path(tsv)
    cats = collections.Counter(cat for cat, *_ in rn.classify_probes(db, RUN, rn.validity()))
    reached = sum(cats[k] for k in rn.REACHED)
    started = rn.q1(db, "SELECT started_utc FROM run WHERE run_manifest_id = ?", RUN)
    hours = (datetime.fromisoformat(OPERATOR_STOP_UTC)
             - datetime.fromisoformat(started)).total_seconds() / 3600
    print(json.dumps({"probes": probes, "oracle_fired": fired, "funnel": funnel,
                      "categories": cats, "reached": reached, "reached_share": reached / probes,
                      "hours_to_operator_stop": hours, "probes_per_hour": probes / hours},
                     indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "call":
        sys.exit(call(*sys.argv[2:5]))
    sys.exit({"gate": regate, "check": check, "numbers": numbers}[mode](*sys.argv[2:]))
