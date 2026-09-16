"""Aggregate every stored run of the loop: per-arm counts, spend, and the latest verdict and decision per candidate. Usage: python campaign_aggregate.py [loop.db]."""
import sqlite3, json
import os, sys
c = sqlite3.connect(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "..", "circt_bug_loop", "loop.db"), timeout=30); c.row_factory = sqlite3.Row
runs = {"903a37c8": "c1 both(stopped)", "11f54337": "c2a s0", "81b06e65": "c2a s1", "df996900": "c2a mut",
        "f6d5148b": "c2b s0", "9748aa2b": "c2b s1", "460b7b48": "c2 mut", "f1e4fef5": "c2c s0", "73effefc": "c2c s1",
        "f0b2ef10": "c3 s0", "db45ab7b": "c3 s1", "91e58983": "c3 mut"}
print(f"{'run':10}{'label':16}{'arm':9}{'seeds':>6}{'probes':>7}{'parse':>6}{'verif':>6}{'fired':>6}{'cands':>6}{'spend':>8}{'turns':>6}")
for pref, label in runs.items():
    r = c.execute("select run_manifest_id from run where run_manifest_id like ?", (pref + "%",)).fetchone()
    if not r: print(pref, "missing"); continue
    run = r["run_manifest_id"]
    for arm in ("seeded", "mutation"):
        q = lambda s: c.execute(s, (run, arm)).fetchone()[0]
        probes = q("select count(*) from probe where run_manifest_id=? and arm=?")
        if probes == 0: continue
        seeds = q("select count(distinct seed_sha) from probe where run_manifest_id=? and arm=?")
        parse = q("select count(*) from probe_result where run_manifest_id=? and arm=? and build_status='parse_error'")
        verif = q("select count(*) from probe_result where run_manifest_id=? and arm=? and build_status='verifier_error'")
        fired = q("select count(*) from probe_result where run_manifest_id=? and arm=? and oracle_fired=1")
        cands = q("select count(*) from candidate where run_manifest_id=? and arm=?")
        spend = 0.0; turns = 0
        for row in c.execute("select observed_json from ledger_entry where run_manifest_id=? and arm=? and metered=1", (run, arm)):
            o = json.loads(row["observed_json"] or "{}")
            if o.get("calls"): turns += 1; spend += float(o.get("billed_usd") or 0)
        print(f"{pref:10}{label:16}{arm:9}{seeds:6}{probes:7}{parse:6}{verif:6}{fired:6}{cands:6}{spend:8.2f}{turns:6}")
print("\n=== latest verdict / decision per candidate, all runs ===")
for row in c.execute("select candidate_id, run_manifest_id, oracle_class, assertion_site, probe_id from candidate order by created_utc"):
    cid = row["candidate_id"]
    d = c.execute("select verdict, evidence_json from dedup_verdict where candidate_id=? order by rowid desc limit 1", (cid,)).fetchone()
    g = c.execute("select decision from gate_decision where candidate_id=? order by rowid desc limit 1", (cid,)).fetchone()
    ve = c.execute("select verifier_op from verifier_error where probe_id=?", (row["probe_id"],)).fetchone()
    ev = json.loads(d["evidence_json"] or "{}") if d else {}
    ref = ev.get("issue_number") or (ev.get("fixing_commit") or "")[:8] or (ev.get("duplicate_of_candidate_id") or "")
    what = ve["verifier_op"] if ve else (row["assertion_site"] or "")[-30:]
    print(f"{row['run_manifest_id'][:8]} {cid} {row['oracle_class']:14} {what:30} {(d['verdict'] if d else '-'):22} {(g['decision'] if g else '-'):8} {ref}")
