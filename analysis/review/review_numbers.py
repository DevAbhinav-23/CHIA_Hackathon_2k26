#!/usr/bin/env python3
"""Workshop-review numbers (T1), read-only on loop.db. Stdlib + sqlite3 only.

Section (e) imports the loop's own fingerprint rule (circt_bug_loop.triage_task),
which needs the repo's Python env, so run it as:
  ~/.cache/chia-venv/bin/python analysis/review/review_numbers.py
Inputs besides loop.db: ~/bugloop-artefacts (artefact dirs), the parse+verify
re-run TSV from validity_rerun.py, a full llvm/circt clone (git blame, test grep).
Writes analysis/measurements/2026-10-27-review-numbers.md and prints it.
"""
import collections
import json
import os
import re
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DB = REPO / "circt_bug_loop" / "loop.db"
OUT = REPO / "analysis" / "measurements" / "2026-10-27-review-numbers.md"
VALIDITY_TSV = REPO / "analysis" / "measurements" / "raw" / "2026-10-27-validity-rerun.tsv"
CIRCT_GIT = Path(os.environ.get("CIRCT_GIT",
                                Path.home() / ".cache/review-main-build/circt-full.git"))
BUILD_POINT = "eade0de61bc5a0d2ba1b9da951b69efcab19f8ce"

#: Paper Table II: campaign -> runs, and the registration tag each ran under.
CAMPAIGNS = {
    1: {"tag": "registration/campaign-2", "mutation": "460b7b48debf47deba8a34701a8f9372",
        "seeded": ["f1e4fef5db314bef8d187bceca8f6a80", "73effefcde2a44758515ef4652d32668"]},
    2: {"tag": "registration/campaign-3", "mutation": "91e58983716b46e2902c01cc7cde10ab",
        "seeded": ["f0b2ef10e17849f4b4ae45510024f96a", "db45ab7bb42f4ca3aba5985c94468dec"]},
}
#: Campaign 2's seeded jobs were killed by the operator, so no row records the stop:
#: analysis/measurements/2026-09-16-campaign-3.md line 9 does (12:24:56 IST).
OPERATOR_STOP_UTC = {2: "2026-09-16T06:54:56+00:00"}

GATED = ["c-p-a2cb61b8d0aa", "c-p-075cf1d70f3a", "c-p-356e9e6e061d", "c-p-9e7eceaadf12",
         "c-p-4f35dc62470e", "c-p-372f1e9ed476", "c-p-3d0f9c33ee0a", "c-p-31a7a300f2e2",
         "c-p-a3a1556793d7", "c-p-509c5aa72a94", "c-p-4b9f84841ec3", "c-p-f0ca5e81cf0d",
         "c-p-a52c6ed44c29", "c-p-4d7a36e3ce15", "c-p-8f95e19612ec"]

#: (g) the pass each probe ran and the op its failing pattern rewrites, read off
#: the probe argv and the reduced case; a test "exercises" the bug's code when it
#: RUNs the same pass and contains this op. A grep proxy, not line coverage.
MOORE, DC = "lib/Conversion/MooreToCore/MooreToCore.cpp", "lib/Conversion/DCToHW/DCToHW.cpp"
SYNTH, FSM = "lib/Conversion/CombToSynth/CombToSynth.cpp", "lib/Conversion/CoreToFSM/CoreToFSM.cpp"
BUG_KEY = {"c-p-a2cb61b8d0aa": ("convert-moore-to-core", "moore.extract", MOORE),
           "c-p-075cf1d70f3a": ("convert-moore-to-core", "moore.dyn_extract", MOORE),
           "c-p-356e9e6e061d": ("convert-moore-to-core", "moore.extract_ref", MOORE),
           "c-p-9e7eceaadf12": ("lower-dc-to-hw", "dc.join", DC),
           "c-p-4f35dc62470e": ("lower-dc-to-hw", "dc.pack", DC),
           "c-p-372f1e9ed476": ("convert-comb-to-synth", "comb.shrs", SYNTH),
           "c-p-3d0f9c33ee0a": ("convert-comb-to-synth", "comb.shl", SYNTH),
           "c-p-31a7a300f2e2": ("convert-comb-to-synth", "comb.icmp", SYNTH),
           "c-p-a3a1556793d7": ("", "om.elaborated_object", "lib/Dialect/OM/OMOps.cpp"),
           "c-p-509c5aa72a94": ("convert-core-to-fsm", "comb.and", FSM),
           "c-p-4b9f84841ec3": ("convert-core-to-fsm", "seq.compreg", FSM),
           "c-p-f0ca5e81cf0d": ("convert-core-to-fsm", "comb.icmp", FSM),
           "c-p-a52c6ed44c29": ("om-elaborate-object", "om.integer.shl",
                                "lib/Dialect/OM/Transforms/ElaborateObject.cpp"),
           "c-p-4d7a36e3ce15": ("convert-moore-to-core", "moore.class.classdecl", MOORE),
           "c-p-8f95e19612ec": ("convert-moore-to-core", "moore.dyn_extract_ref", MOORE)}

#: Options that select no pass or translation: parse/print/IO switches.
NON_SELECTOR = {"-allow-unregistered-dialect", "-verify-roundtrip", "-split-input-file",
                "-verify-diagnostics", "-no-implicit-module", "-emit-bytecode"}
#: Command-line rejections: the argv, not the input, is what the tool refused.
#: Op-verifier messages: after an input that verifies, the pass's OUTPUT failed them.
POST_PASS_VERIFIER = re.compile(r"does not dominate this use|bitwidth of input \(\d+\) and "
                                r"result \(\d+\) don't match|Bitwidth of input must match "
                                r"result|type mismatch at index")
USAGE = re.compile(r"must be specified at least once|Too many positional arguments|"
                   r"Unknown command line argument|does not refer to a registered pass|"
                   r"Not enough positional command line arguments")
PROBE_ONLY = ("--split-input-file", "-split-input-file", "--verify-diagnostics",
              "-verify-diagnostics")


def is_selector(token: str) -> bool:
    """Whether one circt-opt/circt-translate token names a pass, pipeline or translation."""
    name = "-" + token.lstrip("-").split("=", 1)[0]
    return (token.startswith("-") and name != "-o" and not name.startswith("-mlir-")
            and name not in NON_SELECTOR)


def non_selector_options(argv: list) -> list:
    """The option tokens of *argv* that are not selectors, `-o <file>` dropped."""
    out, skip = [], False
    for token in argv:
        if skip:
            skip = False
        elif token == "-o":
            skip = True
        elif token.startswith("-") and not is_selector(token):
            out.append(token)
    return out


# --------------------------------------------------------------------------- helpers
def connect():
    return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)


def q(db, sql, *params):
    return db.execute(sql, params).fetchall()


def q1(db, sql, *params):
    return db.execute(sql, params).fetchone()[0]


def git(*args) -> str:
    return subprocess.run(["git", f"--git-dir={CIRCT_GIT}", *args], capture_output=True,
                          text=True, check=True).stdout


def table(header: list, rows: list) -> str:
    lines = ["| " + " | ".join(map(str, header)) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(map(str, r)) + " |" for r in rows]
    return "\n".join(lines)


def ts(text: str) -> datetime:
    return datetime.fromisoformat(text)


def seed_records(db, run: str) -> dict:
    return {sha: json.loads(rec) for sha, rec in
            q(db, "SELECT seed_sha, record_json FROM seed WHERE run_manifest_id=? "
                  "ORDER BY rowid", run)}


def seed_selectors(record: dict, tool: str) -> list:
    """The pass/translation selector tokens of the seed's own first RUN line."""
    if tool not in ("circt-opt", "circt-translate") or not record.get("argv_template"):
        return []
    template = [t for t in record["argv_template"][0]
                if not any(t == o or t.startswith(o + "=") for o in PROBE_ONLY)]
    return [t for t in template if is_selector(t) and "%" not in t]


def validity() -> dict:
    """probe_id -> (exit, first error) of the parse+verify re-run, if it was made."""
    if not VALIDITY_TSV.exists():
        return {}
    rows = [line.split("\t") for line in VALIDITY_TSV.read_text().splitlines()[1:]]
    return {r[1]: (r[3], r[4] if len(r) > 4 else "") for r in rows}


def stderr_of(artefact_dir: str) -> str:
    try:
        return Path(artefact_dir, "stderr.txt").read_text(errors="replace")
    except OSError:
        return ""


# --------------------------------------------------------------------------- (a)+(b)
def classify_probes(db, run: str, checks: dict) -> tuple:
    """One funnel row per probe of *run*: (category, mutator, tool, stopping detail)."""
    seeds = seed_records(db, run)
    rows = q(db, """SELECT p.probe_id, p.seed_sha, p.tool, p.argv_json, p.input_path,
                           p.mutator_id, p.artefact_dir, r.build_status, r.stopping_stage,
                           r.stopping_reason, r.oracle_class
                    FROM probe p LEFT JOIN probe_result r USING (probe_id)
                    WHERE p.run_manifest_id = ? ORDER BY p.probe_id""", run)
    out = []
    for (pid, sha, tool, argv_json, inp, mutator, adir, status, stage, reason,
         oclass) in rows:
        argv = json.loads(argv_json)
        deleted = [t for t in seed_selectors(seeds[sha], tool) if t not in argv]
        if status is None:
            partial = os.path.exists(os.path.join(adir, "PARTIAL"))
            ran = os.path.exists(os.path.join(adir, "stderr.txt"))
            cat = (f"no_result:tool={tool}:partial={partial}:executed={ran}")
        elif status == "parse_error":
            err = stderr_of(adir)
            rerun = checks.get(pid, ("not_rerun", ""))[0]
            if USAGE.search(err):
                cat = "rejected:usage_error"
            elif argv.count(inp) > 1:
                cat = "rejected:parse_verify(input overwritten by -o; own stderr)"
            elif rerun == "0" and deleted:
                cat = "rejected:by_pass_selector_deleted"
            elif rerun == "0":
                first = next((l for l in err.splitlines() if "error" in l), "")
                cat = ("rejected:by_pass:post-pass IR fails op verifier (possible missed bug)"
                       if POST_PASS_VERIFIER.search(first)
                       else "rejected:by_pass(input parses+verifies)")
            elif rerun == "not_rerun":
                cat = "rejected:not_rerun"
            else:
                cat = "rejected:parse_verify"
        elif status == "clean_exit":
            cat = "clean:selector_deleted(no intended pass ran)" if deleted else "clean:intact"
        else:
            cat = f"fired_or_limit:{status}"
        out.append((cat, mutator or "-", tool, f"{stage}:{reason}", oclass))
    return out


REACHED = ("clean:intact", "rejected:by_pass(input parses+verifies)",
           "rejected:by_pass:post-pass IR fails op verifier (possible missed bug)")


def section_a(db, checks) -> str:
    parts = ["## a. Mutation-arm funnel per run",
             "Definition: a probe **reached the intended pass** iff it has a result row, "
             "its argv still carries every pass/pipeline/translation selector of the "
             "seed's own first RUN line (circt-opt/circt-translate; firtool and "
             "circt-verilog run their default pipeline), the tool did not refuse the "
             "command line, and either it exited 0 or its input parses and verifies "
             "on its own (re-run, no pass, same image; `validity_rerun.py`) so the "
             "error came from the pass. Parse/verify-only (`-o /dev/null`, no "
             "selector) is the re-run command for `.mlir`; `.fir`/`.sv` use the "
             "loop's 4.8 command (`firtool --parse-only`, `circt-verilog --import-only`)."]
    for c, spec in CAMPAIGNS.items():
        run = spec["mutation"]
        cats = classify_probes(db, run, checks)
        count = collections.Counter(cat for cat, *_ in cats)
        total = len(cats)
        results = q1(db, "SELECT COUNT(*) FROM probe_result WHERE run_manifest_id=?", run)
        rows = [("probes emitted", total), ("probes with a result row", results)]
        rows += sorted(((k, v) for k, v in count.items()), key=lambda kv: kv[0])
        rows.append(("**reached the intended pass**", sum(count[k] for k in REACHED)))
        rows += [(f"recorded: {s} / {st}:{r}", n) for s, st, r, n in
                 q(db, "SELECT build_status, stopping_stage, stopping_reason, COUNT(*) "
                       "FROM probe_result WHERE run_manifest_id=? GROUP BY 1,2,3", run)]
        rows.append(("oracle fired", q1(db, "SELECT COUNT(*) FROM probe_result WHERE "
                                            "run_manifest_id=? AND oracle_fired=1", run)))
        parts += [f"### Campaign {c} mutation run `{run}`", table(["measure", "probes"], rows)]
        counters = REPO_ART / run / "results" / "counters.json"
        if counters.exists():
            doc = json.loads(counters.read_text())
            s3 = doc["totals"].get("mutation/stage_3", {})
            viol = sum(1 for v in doc["violations"] if v == "counters_missing:mutation:stage_3")
            parts.append(f"`results/counters.json`: mutation/stage_3 started {s3.get('started')}, "
                         f"completed {s3.get('completed')}, failed {s3.get('failed')}; "
                         f"{viol} `counters_missing:mutation:stage_3` violations (a stage "
                         "call that raised, `bug_loop.Campaign.call` L1706-1710).")
        per_mut = collections.defaultdict(collections.Counter)
        for cat, mut, *_ in cats:
            per_mut[mut]["probes"] += 1
            per_mut[mut]["reached"] += cat in REACHED
            per_mut[mut][cat.split(":")[0]] += 1
        parts.append(table(["mutator", "probes", "no result", "rejected", "clean", "reached pass"],
                           [(m, v["probes"], v["no_result"], v["rejected"], v["clean"],
                             v["reached"]) for m, v in sorted(per_mut.items())]))
    parts.append(
        "Why the no-result probes have no row: every one has `tool='other'` (the corpus "
        "maps any RUN-line tool outside its five, e.g. circt-reduce, to `other`, "
        "`corpus.classify_entry_tool` L209-211), and `probe_task.probe_execute` L116-120 "
        "hashes `<bin>/other`, gets '' against `tool_hashes['other']` = None and raises "
        "`BinaryMismatch` before executing. `_drive_probe` L1780-1786 then stops with "
        "`stage_3_error:BinaryMismatch` and `_close_probe` L1765-1767 writes no row, "
        "leaving `PARTIAL` and no stdout/stderr (the `partial=True:executed=False` above). "
        "Reproduced in-process: `BinaryMismatch other: expected None, ran`. The "
        "`input overwritten` rows are probes whose seed RUN line has `-o %t`: "
        "`generate_task._bind` maps `%t` to the input path, so the tool wrote its "
        "output over (or, failing, deleted) its own input; 15 probes per mutation run, "
        "0 in the seeded runs.")
    return "\n\n".join(parts)


def section_b(db, checks) -> str:
    parts = ["## b. Seeded-arm funnel (same categories) per campaign",
             "`rejected:*` = `parse_error/tool_rejected_input`, which the loop books as "
             "the model's fault; the re-run splits off inputs that parse and verify "
             "and were refused by the pass itself."]
    for c, spec in CAMPAIGNS.items():
        count, oracle = collections.Counter(), collections.Counter()
        for run in spec["seeded"]:
            cats = classify_probes(db, run, checks)
            count.update(cat for cat, *_ in cats)
            oracle.update(o for *_, o in cats if o)
        rows = [("probes", sum(count.values()))]
        rows += sorted(count.items())
        rows.append(("**reached the intended pass** (clean + pass-time rejections; fired "
                     "probes counted separately)", sum(count[k] for k in REACHED)))
        rows += [(f"oracle fired: {k}", v) for k, v in sorted(oracle.items())]
        runs = ",".join("?" * len(spec["seeded"]))
        rows.append(("candidates", q1(db, f"SELECT COUNT(*) FROM candidate WHERE "
                                          f"run_manifest_id IN ({runs})", *spec["seeded"])))
        rows.append(("gate `report` (latest decision per candidate)", q1(db, f"""
            SELECT COUNT(*) FROM gate_decision g JOIN candidate c USING (candidate_id)
            WHERE c.run_manifest_id IN ({runs}) AND g.decision='report'
              AND g.rowid = (SELECT MAX(rowid) FROM gate_decision WHERE
                             candidate_id = g.candidate_id)""", *spec["seeded"])))
        parts += [f"### Campaign {c} seeded ({', '.join(r[:8] for r in spec['seeded'])})",
                  table(["measure", "probes"], rows)]
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- (c)
def reached_seeds(db, run: str, arm: str) -> set:
    found = set()
    for t in ("probe", "turn_failure", "feedback"):
        found |= {r[0] for r in q(db, f"SELECT DISTINCT seed_sha FROM {t} WHERE "
                                      "run_manifest_id=? AND arm=?", run, arm)}
    return found


def section_c(db) -> str:
    any_run = CAMPAIGNS[1]["mutation"]
    order = [r[0] for r in q(db, "SELECT seed_sha FROM seed WHERE run_manifest_id=? "
                                 "ORDER BY rowid", any_run)]
    same = all([r[0] for r in q(db, "SELECT seed_sha FROM seed WHERE run_manifest_id=? "
                                     "ORDER BY rowid", run)] == order
               for spec in CAMPAIGNS.values() for run in [spec["mutation"], *spec["seeded"]])
    mined, es, em = q(db, "SELECT COUNT(*), SUM(eligible_seeded), SUM(eligible_mutation) "
                          "FROM seed WHERE run_manifest_id=?", any_run)[0]
    excl = q(db, "SELECT exclusion_reason, COUNT(*) FROM seed WHERE run_manifest_id=? AND "
                 "exclusion_reason IS NOT NULL GROUP BY 1", any_run)
    parts = ["## c. Corpus and ordering",
             f"Mined seeds {mined}; eligible seeded {es}, eligible mutation {em}; excluded "
             f"{dict(excl)}. Seed table rowid order identical in all six runs: {same}.",
             "Order rule (both arms): `corpus.build_corpus` walks `git log --first-parent "
             "HEAD` from corpus head d7e94049 newest-first (`_walk_pins` L328, loop L425) "
             "and appends seeds in that order; `bug_loop.campaign_drive` L2112 iterates "
             "that list unchanged for every arm. The seeded arm ran as two jobs, "
             "`--shard 0/2` and `1/2`, which keep corpus positions `i % 2 == K` "
             "(`seed_shard` L2742-2747); the mutation job ran unsharded over all seeds."]
    pos = {sha: i for i, sha in enumerate(order)}
    rows = []
    for c, spec in CAMPAIGNS.items():
        mut_reached = reached_seeds(db, spec["mutation"], "mutation")
        mut_probed = {r[0] for r in q(db, "SELECT DISTINCT seed_sha FROM probe WHERE "
                                          "run_manifest_id=?", spec["mutation"])}
        sd_reached, sd_probed = set(), set()
        for run in spec["seeded"]:
            r = reached_seeds(db, run, "seeded")
            sd_reached |= r
            sd_probed |= {x[0] for x in q(db, "SELECT DISTINCT seed_sha FROM probe WHERE "
                                              "run_manifest_id=?", run)}
            rows.append((c, f"seeded {run[:8]}", len(r),
                         len({x[0] for x in q(db, 'SELECT DISTINCT seed_sha FROM probe '
                                                  'WHERE run_manifest_id=?', run)}),
                         max(pos[s] for s in r) + 1, "-"))
        rows.append((c, "seeded, both shards", len(sd_reached), len(sd_probed),
                     max(pos[s] for s in sd_reached) + 1,
                     f"probed by both arms: {len(sd_probed & mut_probed)} of {len(sd_probed)}; "
                     f"mutation reached all {len(sd_reached & mut_reached)} seeded-reached seeds"))
        stale_seeds = [r[0] for r in q(db, "SELECT DISTINCT seed_sha FROM turn_failure WHERE "
                                           "run_manifest_id=? AND kind='stale_at_build'",
                                           spec["mutation"])]
        stale = len(stale_seeds)
        lines = [" ".join(json.loads(q1(db, "SELECT record_json FROM seed WHERE run_manifest_id=? "
                                            "AND seed_sha=?", spec["mutation"], sha))["run_lines"][:1])
                 for sha in stale_seeds]
        vd = sum("verify-diagnostics" in l for l in lines)
        sp = sum("split-input-file" in l for l in lines)
        either = sum("verify-diagnostics" in l or "split-input-file" in l for l in lines)
        dirs = len(list((REPO_ART / spec["mutation"]).glob("seed_*")))
        rows.append((c, f"mutation {spec['mutation'][:8]}", f"{len(mut_reached)} in DB, "
                     f"{dirs} seed dirs", len(mut_probed), max(pos[s] for s in mut_reached) + 1,
                     f"{stale} stale_at_build: first RUN line has --verify-diagnostics {vd}, "
                     f"--split-input-file {sp}, either {either} (both stripped from probe argv, "
                     "corpus.py L51-52)"))
    parts.append(table(["campaign", "arm/run", "seeds reached", "seeds with >=1 probe",
                        "deepest corpus position reached", "overlap / notes"], rows))
    parts.append("Seeds reached = distinct seeds with a probe, turn_failure or feedback "
                 "row for that run and arm. A seed whose mutants were all no-ops writes "
                 "none of those, hence the seed-dir count beside it.")
    return "\n\n".join(parts)


# --------------------------------------------------------------------------- (d)
def section_d(db) -> str:
    rows = []
    for c, spec in CAMPAIGNS.items():
        for run, arm in [(r, "seeded") for r in spec["seeded"]] + [(spec["mutation"], "mutation")]:
            started, ended, manifest = q(db, "SELECT started_utc, ended_utc, manifest_json "
                                             "FROM run WHERE run_manifest_id=?", run)[0]
            window = json.loads(manifest)["arm_window_seconds"]
            aw = q(db, "SELECT amount, stop_reason FROM ledger_entry WHERE run_manifest_id=? "
                       "AND scope='arm_window' AND arm=?", run, arm)
            last = q1(db, "SELECT MAX(timestamp_utc) FROM ledger_entry WHERE "
                          "run_manifest_id=? AND arm=? AND scope='stage' AND "
                          "timestamp_utc <= COALESCE(?, '9')", run, arm, ended)
            if aw:
                elapsed, reason = f"{aw[0][0]:.0f}", aw[0][1]
            else:
                stop = OPERATOR_STOP_UTC[c]
                elapsed = f"{(ts(stop) - ts(started)).total_seconds():.0f} (to operator stop)"
                reason = "operator stop (no arm_window row; ended_utc NULL)"
            lower = (ts(last) - ts(started)).total_seconds()
            rows.append((c, arm, run[:8], window, started, ended or "NULL", elapsed,
                         f"{lower:.0f}", reason))
    return "\n\n".join([
        "## d. Elapsed wall-clock per arm",
        table(["campaign", "arm", "run", "registered window s", "started_utc", "ended_utc",
               "elapsed s (arm_window row)", "last stage-ledger entry − start, s",
               "stop reason"], rows),
        "All three jobs of a campaign ran concurrently on one machine (campaign 2: all "
        "started 19:01 UTC; campaign 1's mutation job ran 00:49-01:03, before the seeded "
        "shards at 01:54). FR-14.5's 'same window W' is a deadline, not a duration: the "
        "mutation arm stopped on `seed_set_exhausted` after 775 s / 266 s while each "
        "seeded shard ran to its 7,200 s deadline (campaign 1) or was stopped by the "
        "operator at 42,836 s of a 150,000 s window (campaign 2). The window therefore "
        "never bound the mutation arm, and campaign 2's operator stop bound only the "
        "seeded arm: its seeded result is a 42,836 s x 2-shard measurement, its "
        "mutation result a 266 s one. Campaign 2 elapsed uses the operator stop recorded "
        "in `analysis/measurements/2026-09-16-campaign-3.md` L9; the DB's own lower "
        "bound is the last stage-ledger entry (column 8)."])


# --------------------------------------------------------------------------- (e)
def section_e() -> str:
    sys.path.insert(0, str(REPO))
    from circt_bug_loop import results, triage_task          # the loop's own rule
    top_n = int(re.search(r"^fingerprint_top_n:\s*(\d+)",
                          (REPO / "circt_bug_loop/budget.yaml").read_text(), re.M).group(1))
    m = collections.Counter()
    wrong = []
    for pair in results.load_labelled_pairs():
        a = triage_task.labelled_fingerprint(pair["a"], top_n)
        b = triage_task.labelled_fingerprint(pair["b"], top_n)
        merged = triage_task.is_duplicate(a, b)
        m[(pair["label"], merged)] += 1
        if merged != (pair["label"] == "duplicate"):
            wrong.append(f"{pair['a']['candidate_id']}/{pair['b']['candidate_id']} "
                         f"(label {pair['label']}, basis {a.basis}/{b.basis})")
    shipped = triage_task.rates([{"label": p["label"],
                                  "a": triage_task.labelled_fingerprint(p["a"], top_n),
                                  "b": triage_task.labelled_fingerprint(p["b"], top_n)}
                                 for p in results.load_labelled_pairs()])
    return "\n\n".join([
        "## e. Dedup confusion matrix (22 labelled pairs, shipped rule)",
        f"`triage_task.labelled_fingerprint` + `triage_task.is_duplicate`, top_n={top_n} "
        "(budget.yaml), over `circt_bug_loop/data/labelled_pairs.json`.",
        table(["label \\ verdict", "merged (same fingerprint)", "split"],
              [("duplicate", f"{m[('duplicate', True)]} correct merges",
                f"{m[('duplicate', False)]} **false split**"),
               ("distinct", f"{m[('distinct', True)]} **false merge**",
                f"{m[('distinct', False)]} correct splits")]),
        f"Misjudged pairs: {'; '.join(wrong)}.",
        f"`triage_task.rates` returns collisions={shipped['collisions']} (a distinct pair "
        f"merged = false merge) and `false_merges`={shipped['false_merges']}, which counts "
        "duplicate pairs NOT merged, i.e. false splits: the key is misnamed in "
        "`triage_task.rates` (L174-183) and the paper's 'falsely merges 1 of the 11 "
        "duplicate pairs' inherits the misnomer. Correct: falsely merges 1 of 11 "
        "distinct pairs and falsely splits 1 of 11 duplicate pairs."])


# --------------------------------------------------------------------------- (f)
def registered_prices(tag: str) -> tuple:
    text = subprocess.run(["git", "-C", str(REPO), "show", f"{tag}:circt_bug_loop/budget.yaml"],
                          capture_output=True, text=True, check=True).stdout
    found = {}
    for n, line in enumerate(text.splitlines(), 1):
        match = re.match(r"(price_usd_per_m_(input|output)_tokens):\s*([\d.]+)", line)
        if match:
            found[match.group(2)] = (float(match.group(3)), n)
    return found


def section_f(db) -> str:
    rows, stage_rows = [], []
    for c, spec in CAMPAIGNS.items():
        prices = registered_prices(spec["tag"])
        pin, pout = prices["input"][0], prices["output"][0]
        for when in ("during run", "after run end"):
            tin = tcache = tout = calls = 0
            usd = 0.0
            for run in spec["seeded"] + [spec["mutation"]]:
                started, ended = q(db, "SELECT started_utc, ended_utc FROM run WHERE "
                                       "run_manifest_id=?", run)[0]
                end = ended or OPERATOR_STOP_UTC.get(c)
                for obs, stamp in q(db, "SELECT observed_json, timestamp_utc FROM ledger_entry "
                                        "WHERE run_manifest_id=? AND scope='stage'", run):
                    if (stamp <= end) != (when == "during run"):
                        continue
                    o = json.loads(obs)
                    tin += o.get("tokens_in") or 0
                    tcache += o.get("cached_tokens") or 0
                    tout += o.get("tokens_out") or 0
                    calls += o.get("calls") or 0
                    usd += o.get("cost_usd") or 0.0
            recomputed = tin / 1e6 * pin + tout / 1e6 * pout
            rows.append((c, when, f"{tin:,}", f"{tcache:,} ({100 * tcache / tin:.1f} %)"
                         if tin else "0", f"{tout:,}", calls, f"{usd:.2f}", f"{recomputed:.2f}"))
        stage = collections.defaultdict(float)
        for run in spec["seeded"] + [spec["mutation"]]:
            for arm, st, secs in q(db, "SELECT arm, stage, SUM(amount) FROM ledger_entry WHERE "
                                       "run_manifest_id=? AND scope='stage' GROUP BY 1,2", run):
                stage[(arm, st)] += secs
        for (arm, st), secs in sorted(stage.items()):
            stage_rows.append((c, arm, st, f"{secs:,.1f}"))
    p1 = registered_prices(CAMPAIGNS[1]["tag"])
    return "\n\n".join([
        "## f. Cost split",
        "Prices: `circt_bug_loop/budget.yaml` at the registration tag, "
        f"`price_usd_per_m_input_tokens: {p1['input'][0]}` (L{p1['input'][1]}) and "
        f"`price_usd_per_m_output_tokens: {p1['output'][0]}` (L{p1['output'][1]}), same in "
        "both tags; `ledger.price` (ledger.py L28-34) prices every input token, cached "
        "or not, at the input list price (`llm.py` L131-133 says so); thinking tokens "
        "are in tokens_out. USD below is that list price, not the bill.",
        table(["campaign", "ledger entries", "input tokens", "of which cached", "output tokens",
               "calls", "USD list (ledger cost_usd)", "USD recomputed from tokens"], rows),
        "'after run end' = stage entries timestamped after `ended_utc` (campaign 2: after "
        "the operator stop), i.e. later `--report-turns`/`--reclassify` passes charged "
        "to the same run id.",
        "Compute wall-clock per stage (sum of `stage` ledger entries; the model stages' "
        "seconds include model latency and 429 back-off). `shared/image` is the image "
        "inspection at launch, not the build: the image build was 972 s once "
        "(`analysis/measurements/2026-09-14-image-build.md`). stage_1/2 = seed read / "
        "probe write (model turns; mutation arm: mutator), stage_3 = probe, stage_4 = "
        "oracles, stage_5 = reduce, stage_6 = dedup + report, gate = gate.",
        table(["campaign", "arm", "stage", "seconds"], stage_rows)])


# --------------------------------------------------------------------------- (g)
def circt_site(frames: list) -> tuple:
    """(path under the CIRCT tree, line, function) of the first CIRCT lib frame with a line."""
    for f in frames:
        path = f.get("file") or ""
        if path.startswith("/workspace/circt/lib/") and int(f.get("line") or 0) > 0:
            return path[len("/workspace/circt/"):], int(f["line"]), f.get("function", "")
    return None, None, ""


def blame_age(path: str, line: int) -> str:
    out = git("blame", "-w", "--porcelain", "-L", f"{line},{line}", BUILD_POINT, "--", path)
    commit = out.split()[0]
    when = int(re.search(r"^committer-time (\d+)", out, re.M).group(1))
    point = int(git("log", "-1", "--format=%ct", BUILD_POINT).strip())
    return f"{(point - when) / 86400:.0f} d ({commit[:10]})"


def bucket(path: str) -> str:
    """corpus.dialect_buckets (FR-01.4): include/circt/Dialect/<X>, else lib/<kind>/<X>."""
    parts = path.split("/")
    if path.startswith("include/circt/Dialect/") and len(parts) > 3:
        return parts[3]
    return parts[2] if len(parts) > 3 else parts[1]


def distance(path: str, fixes: list) -> str:
    if not path:
        return "n/a"
    if path in fixes:
        return "same file"
    if bucket(path) in {bucket(f) for f in fixes}:
        return f"same dialect ({bucket(path)})"
    return f"different ({bucket(path)} vs {','.join(sorted({bucket(f) for f in fixes}))})"


def tests_exercising(pass_name: str, op: str, seed_tests: list) -> str:
    """Test files at the build point that RUN *pass_name* (any, if none) and contain *op*."""
    pattern = f"RUN:.*{pass_name}" if pass_name else "RUN:"
    files = [h.split(":", 1)[1] for h in
             git("grep", "-l", "-E", pattern, BUILD_POINT, "--", "test").splitlines()]
    has_op = re.compile(re.escape(op) + r"(?![\w.])")
    with_op = [f for f in files if has_op.search(git("show", f"{BUILD_POINT}:{f}"))]
    seed_hit = [t for t in seed_tests if t in with_op]
    scope = f"RUN `{pass_name}`" if pass_name else "are lit tests"
    return (f"{len(files)} {scope}, {len(with_op)} contain `{op}`; seed test "
            f"{'among them' if seed_hit else 'not among them'}")


def seed_tokens(db, run: str, seed: str) -> tuple:
    tin = tout = 0
    for stage in ("stage_1", "stage_2"):
        for it in range(1, 4):
            eid = uuid.uuid5(uuid.NAMESPACE_URL,
                             f"{run}/seeded/stage/{stage}/generate_seeded/{seed}:{it}").hex
            row = db.execute("SELECT observed_json FROM ledger_entry WHERE entry_id=?",
                             (eid,)).fetchone()
            if row:
                o = json.loads(row[0])
                tin += o.get("tokens_in") or 0
                tout += o.get("tokens_out") or 0
    return tin, tout


def mutation_on_seed(db, campaign: int, seed: str) -> str:
    """What the same campaign's mutation run did with this seed."""
    run = CAMPAIGNS[campaign]["mutation"]
    stale = q1(db, "SELECT COUNT(*) FROM turn_failure WHERE run_manifest_id=? AND "
                   "seed_sha=? AND kind='stale_at_build'", run, seed)
    if stale:
        return "stale_at_build (seed test rejected)"
    counts = q(db, "SELECT COALESCE(r.build_status, 'no_result'), COUNT(*) FROM probe p "
                   "LEFT JOIN probe_result r USING (probe_id) WHERE p.run_manifest_id=? "
                   "AND p.seed_sha=? GROUP BY 1", run, seed)
    return ", ".join(f"{n} {k}" for k, n in counts) or "no probe"


def section_g(db) -> str:
    rows = []
    for cand in GATED:
        (run, probe, oclass, site, frames_json, seed, reduced_path) = q(db, """
            SELECT c.run_manifest_id, c.probe_id, c.oracle_class, c.assertion_site,
                   v.frames_json, p.seed_sha, r.path
            FROM candidate c JOIN probe p USING (probe_id)
            JOIN oracle_verdict v USING (probe_id) JOIN reduced_case r USING (probe_id)
            WHERE c.candidate_id = ?""", cand)[0]
        campaign = next(c for c, spec in CAMPAIGNS.items() if run in spec["seeded"])
        record = json.loads(q1(db, "SELECT record_json FROM seed WHERE run_manifest_id=? "
                                   "AND seed_sha=?", run, seed))
        pass_name, op, pass_file = BUG_KEY[cand]
        path, line, function = circt_site(json.loads(frames_json))
        function = function.replace("(anonymous namespace)::", "").split("(")[0][-50:]
        if oclass == "assertion" and site.startswith("/workspace/circt/lib/"):
            path, line = site[len("/workspace/circt/"):].rsplit(":", 1)
            line = int(line)
        if oclass == "verifier_error":
            vop, msg = q(db, "SELECT verifier_op, verifier_message FROM verifier_error "
                             "WHERE probe_id=?", probe)[0]
            where = f"`{vop}` verifier on `{pass_name}` output: {msg.split(' op ', 1)[-1][:50]}"
        elif path:
            where = f"`{path}:{line}` {function}"
            if oclass == "assertion" and not site.startswith("/workspace/circt/lib/"):
                where += f" (assert in `{site.rsplit('/', 1)[-1]}`)"
        else:
            where = f"segfault in MLIR's verifier on `{pass_name}` output (no CIRCT frame)"
        fixes = record["source_paths"]
        red_lines = len(Path(reduced_path).read_text().splitlines())
        seed_lines = sum(len(t.splitlines()) for t in record["test_files"].values())
        tin, tout = seed_tokens(db, run, seed)
        rows.append((cand, oclass, where, blame_age(path, line) if path else "n/a",
                     distance(path, fixes), distance(pass_file, fixes),
                     f"{red_lines} / {seed_lines}", f"{tin:,} / {tout:,}",
                     tests_exercising(pass_name, op, record["test_paths"]),
                     mutation_on_seed(db, campaign, seed)))
    return "\n\n".join([
        "## g. Per-bug hardness (the 15 through the gate)",
        "Site = the assertion's own file:line when it is in CIRCT's `lib/`, else the first "
        "frame under `/workspace/circt/lib/` with a line (header asserts named after it). "
        f"Line age = build point {BUILD_POINT[:10]} committer time minus the committer "
        "time of the commit `git blame -w` gives for that line at the build point (last "
        "change, not creation). Distance compares the site file, and the source of the "
        "pass the probe ran, with the seed fix's `source_paths` (dialect = FR-01.4's "
        "bucket, `corpus.dialect_buckets`). Sizes: lines of `reduced.mlir` vs all of the "
        "seed's test files. Tokens: the seed's stage 1+2 turns, all iterations (ledger "
        "rows re-keyed by `Campaign.charge`'s uuid5); seeds with several candidates repeat "
        "it. Tests: files under `test/` at the build point that RUN the pass and contain "
        "the failing pattern's op (a grep proxy, not line coverage). Last column: the "
        "same campaign's mutation run on the same seed.",
        table(["candidate", "class", "site", "line last changed before build point",
               "site vs seed fix", "pass source vs seed fix", "reduced / seed test lines",
               "seed tokens in / out", "CIRCT tests (grep proxy)", "mutation arm on this seed"],
              rows)])


REPO_ART = Path.home() / "bugloop-artefacts"


def main() -> int:
    db = connect()
    checks = validity()
    doc = "\n\n".join([
        "# Review numbers, 2026-10-27",
        "Generated by `analysis/review/review_numbers.py` (read-only on "
        "`circt_bug_loop/loop.db`); every number below comes from a query or file read "
        "in that script. Campaign 1 = registration/campaign-2 runs, campaign 2 = "
        "registration/campaign-3 runs (paper Table II). Regenerate: run "
        "`analysis/review/validity_rerun.py` in the campaigns' image (command in its "
        "docstring), then `~/.cache/chia-venv/bin/python analysis/review/review_numbers.py`.",
        section_a(db, checks), section_b(db, checks), section_c(db), section_d(db),
        section_e(), section_f(db), section_g(db)]) + "\n"
    OUT.write_text(doc, encoding="utf-8")
    print(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
