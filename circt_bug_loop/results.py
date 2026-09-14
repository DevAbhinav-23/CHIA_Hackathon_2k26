"""B11: render the campaign's results artefact, or refuse and say what is missing.

`03-LLD.md` §3.11 and §14.4, `02-HLD.md` §1.3, F-18. `render_results` is a pure
function of `loop.db`: it opens no tool, runs no model and writes no file, so a
render can be repeated on a finished campaign and produces the same text.

**It refuses rather than omits.** The fourteen private checks of `_REFUSALS` are
§14.4's table, in §3.11's order, one per element the results artefact must
carry. `render_results` runs every one and collects every failure before it
raises, so one render names every missing element rather than the first.

**Three properties are not checks and are asserted over the output instead**
(§14.4): the render succeeds from an empty confirmation set and states the zero
(FR-18.7); the text contains no sentence comparing this loop's count to any
external yield (FR-18.9), which this module discharges by naming none of them
anywhere; and every number in the artefact traces to a tool-produced record
(NFR-03), which is why the only inputs are the store, the manifest and the
hand-labelled duplicate-pair set of FR-10.2, whose labels are the one human
judgement the artefact reports and whose fingerprints still come from the store.

`arm` is branched on here, and FR-18.1 permits exactly that: the ledger and the
results table are the two places the value of `arm` may change what the
apparatus does, and this module is the second of them.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop import ledger as ledger_module
from circt_bug_loop.contract.schema import CounterBlock, RunManifest
from circt_bug_loop.gate import TAXONOMY, decide
from circt_bug_loop.probe_task import classify_build
from circt_bug_loop.store import LoopStore
from circt_bug_loop.triage_task import labelled_fingerprint, rates

#: The two arms, in the order every table prints them. `shared` is a ledger arm
#: and never an arm of the comparison (FR-14.4).
ARMS = ("seeded", "mutation")

#: The six buckets of FR-18.6, in the order the taxonomy table prints them. The
#: mapping that produces them is `gate.TAXONOMY` and is not restated here.
BUCKETS = ("unreproducible", "not_minimal", "invalid_input", "duplicate",
           "undecided", "new_bug")

#: FR-06.9's seven build statuses, in the order the probe-outcome table prints
#: them, plus contract 2.1's `tool_unavailable`. `parse_error` is printed as two
#: rows keyed by `stopping_reason`, so the row is never read as "the tool
#: rejected the input" when it means "the loop built an argv the tool would not
#: take" (§3.6, NIT 2); `tool_unavailable` is last because it is the one row
#: that says the probe decided nothing at all (N9).
BUILD_STATUSES = ("clean_exit", "parse_error", "assertion", "fatal_error",
                  "crash", "timeout", "oom", "tool_unavailable")
PARSE_REASONS = ("tool_rejected_input", "tool_rejected_argv")

#: The stages a MODEL TURN is charged to, which are the only ones whose null
#: token counts are a missing measurement rather than an absent one: stages 1
#: and 2 are A3's two turns, stage 6 is B7's, and stage 7 is the repair chain's
#: recorded residual (ADR-D-03 addendum). An entry at any other stage has no
#: tokens because no turn ran there (K10).
MODEL_STAGES = ("stage_1", "stage_2", "stage_6", "stage_7")

#: `LedgerEntry.observed`'s declared keys (§2.7, contract 2.2). An entry whose
#: block has another key set cannot be summed under the observed heading. The
#: last four are the per-turn money row W-18b added: what the guard authorised,
#: what ceiling the backend was given, what the turn billed and how many
#: `generate_content` calls it took (errata row 38).
OBSERVED_KEYS = {"cpu_seconds", "tokens_in", "tokens_out", "cost_usd",
                 "authorised_usd", "ceiling_usd", "billed_usd", "calls"}

#: The ledger stage the offline mutator synthesis is charged to, which is where
#: FR-05.8's declaration gets its date (§3.11's counter stages).
SYNTHESIS_STAGE = "synthesis"

#: The two ways `04-Test-Plan.md` §11 lets a row fail regeneration without it
#: being a defect: a reduction the budget truncated (NFR-02 exempts it), and an
#: image digest that is no longer available, which is a retention failure.
BUDGET_TRUNCATED = "reduction_budget_truncated"
IMAGE_UNAVAILABLE = "image_unavailable"


#: FR-10.2's hand-labelled duplicate-pair set, as package DATA. It is not a
#: test fixture: `render_results` takes it on every campaign, and W-19b measured
#: what its absence cost - the driver called the node with no set at all, the
#: gap fired on every run, and a campaign ran both four-hour arm windows and
#: then died with a traceback instead of writing its artefact. `runtime_env`
#: ships the package and not `tests/`, so a set under `tests/` could not have
#: reached a worker either. `data/README.md` records what the set is.
LABELLED_PAIRS = Path(__file__).resolve().parent / "data" / "labelled_pairs.json"


def load_labelled_pairs(path=None) -> list:
    """Read FR-10.2's labelled set into the four keys `render_results` reads.

    The committed document carries the whole judgement - the rule, the
    justification, the instant, and both sides' RECORDED FAILURES - and `a` and
    `b` are those recorded failures and not two candidate ids. That is the whole
    of the fix: the set is an EXTERNAL MEASUREMENT of the project, labelled by
    hand before any fingerprint was computed, so its sides belong to no campaign
    and a renderer that required the campaign's store to hold a fingerprint for
    each of them refused at the end of every run (`T-S-regen-01`).

    Returns:
        list[dict] with keys `label`, `pair_id`, `rule`, and `a` and `b`, each
        the side's own recorded failure as `triage_task.labelled_fingerprint`
        takes it.
    Worker:
        head; one file read.
    Raises:
        OSError when the file is missing; ValueError on malformed JSON; KeyError
        when a pair carries no `label` or no side.
    """
    document = json.loads(Path(path or LABELLED_PAIRS).read_text(encoding="utf-8"))
    return [{"label": pair["label"], "pair_id": pair["pair_id"],
             "rule": pair["rule"], "a": pair["a"], "b": pair["b"]}
            for pair in document["pairs"]]


class ResultsIncomplete(Exception):
    """Raised by `render_results` when the store lacks an element §14.4 lists.

    Carries every missing element, not the first, so one render tells the
    operator everything the artefact would have had to omit.
    """

    def __init__(self, missing: list):
        self.missing = list(missing)
        super().__init__("the results artefact refuses to render; missing: "
                         + "; ".join(self.missing))


# ---------------------------------------------------------------------------
# Reading the store
# ---------------------------------------------------------------------------


def _by(rows: list, key: str) -> dict:
    """Index *rows* by one column, last write winning on a repeated key."""
    return {row[key]: row for row in rows}


def _confirmed(filing: dict) -> bool:
    """Report whether one filing carries maintainer evidence (G-27, FR-18.3).

    A maintainer acted, and the evidence is a URL: the flag alone is a claim and
    the URL is the record of it, so the headline counts a filing only where both
    are present.

    Returns:
        bool.
    Worker:
        pure.
    Raises:
        nothing.
    """
    return bool(filing["confirmed"]) and bool(filing["confirmation_url"])


def _count(number: int, noun: str) -> str:
    """Render "<n> <noun>", pluralised, so no sentence reads "1 bugs"."""
    return f"{number} {noun}" + ("" if number == 1 else "s")


def _percent(numerator: int, denominator: int) -> str:
    """Render one ratio as "n/d (p%)", or as "n/a" where the denominator is zero."""
    if denominator == 0:
        return "n/a (0 filings)"
    return f"{numerator}/{denominator} ({100.0 * numerator / denominator:.1f}%)"


def _facts(store: LoopStore, manifest: RunManifest, labelled_pairs,
           fingerprint_top_n: int) -> dict:
    """Read every number the artefact prints, and record what the store lacks.

    One pass over `loop.db` per table, joined on the ids §6.2 declares. Each
    section lands in `facts` under its own key, and a section the store cannot
    support lands as None with its reason in `facts["gaps"]`, which is what the
    fourteen checks read.

    Returns:
        dict, one key per section plus "gaps", "qualifier", "run" and
        "manifest".
    Worker:
        {"num_cpus": 0.1} per query, on the head where loop.db lives.
    Raises:
        ResultsIncomplete when the store holds no run row at all, there being
        no artefact to refuse parts of; sqlite3.Error from any query.
    """
    run_id = manifest.run_manifest_id
    run = store.query_one("SELECT * FROM run WHERE run_manifest_id = ?", (run_id,))
    if run is None:
        raise ResultsIncomplete([f"loop.db holds no run row for {run_id!r}"])

    stored = json.loads(run["manifest_json"]) if run["manifest_json"] else {}
    gaps: dict = {}
    facts: dict = {"run": run, "manifest": manifest, "stored": stored, "gaps": gaps,
                   "run_id": run_id}

    candidates = store.query(
        "SELECT * FROM candidate WHERE run_manifest_id = ? ORDER BY candidate_id",
        (run_id,))
    probe_results = store.query(
        "SELECT * FROM probe_result WHERE run_manifest_id = ?", (run_id,))
    probes = store.query("SELECT * FROM probe WHERE run_manifest_id = ?", (run_id,))
    fingerprints = _by(store.query(
        "SELECT f.* FROM fingerprint f JOIN candidate c USING (candidate_id) "
        "WHERE c.run_manifest_id = ?", (run_id,)), "candidate_id")
    dedups = _by(store.query(
        "SELECT d.* FROM dedup_verdict d JOIN candidate c USING (candidate_id) "
        "WHERE c.run_manifest_id = ?", (run_id,)), "candidate_id")
    gates = _by(store.query(
        "SELECT g.* FROM gate_decision g JOIN candidate c USING (candidate_id) "
        "WHERE c.run_manifest_id = ?", (run_id,)), "candidate_id")
    filings = store.query(
        "SELECT f.*, c.arm AS arm FROM filing f JOIN candidate c USING (candidate_id) "
        "WHERE c.run_manifest_id = ? ORDER BY f.candidate_id", (run_id,))
    repairs = store.query(
        "SELECT r.*, c.arm AS arm FROM repair r JOIN candidate c USING (candidate_id) "
        "WHERE c.run_manifest_id = ? ORDER BY r.candidate_id", (run_id,))
    reports = store.query(
        "SELECT p.*, c.arm AS arm, c.oracle_class AS oracle_class "
        "FROM report p JOIN candidate c USING (candidate_id) "
        "WHERE c.run_manifest_id = ? ORDER BY p.candidate_id", (run_id,))
    seeds = store.query(
        "SELECT * FROM seed WHERE run_manifest_id = ? ORDER BY seed_sha", (run_id,))
    differentials = _by(store.query(
        "SELECT d.* FROM differential_verdict d JOIN probe p USING (probe_id) "
        "WHERE p.run_manifest_id = ?", (run_id,)), "probe_id")
    ledger_rows = store.query(
        "SELECT * FROM ledger_entry WHERE run_manifest_id = ? "
        "ORDER BY timestamp_utc, entry_id", (run_id,))

    primary = [c for c in candidates if c["oracle_class"] != "differential"]
    facts["candidates"] = candidates
    facts["primary"] = primary
    facts["probe_results"] = probe_results
    facts["probe_rows"] = probes

    _qualifiers(facts, run, manifest, gaps)
    _headline(facts, filings, fingerprints, _by(candidates, "candidate_id"), gaps)
    _secondaries(facts, primary, dedups, filings, repairs, gaps)
    _validation(facts, seeds, probes, candidates, filings, gaps)
    _contamination(facts, primary, filings, fingerprints, _by(candidates, "candidate_id"),
                   gaps)
    _disclosures(facts, repairs, gaps)
    _lag(facts, stored, gaps)
    _cutoff(facts, stored, gaps)
    _dedup_rates(facts, labelled_pairs, fingerprints, primary,
                 fingerprint_top_n, gaps)
    _divergences(facts, candidates, reports, differentials, _by(probes, "probe_id"), gaps)
    _mutator_declaration(facts, stored, ledger_rows, gaps)
    _observed(facts, ledger_rows, gaps)
    _windows(facts, store, manifest, ledger_rows, gaps)
    _taxonomy(facts, primary, gates, repairs, probe_results)
    _regeneration(facts, store, candidates, gaps)
    return facts


def _qualifiers(facts: dict, run: dict, manifest: RunManifest, gaps: dict) -> None:
    """Fix the two qualifiers ADR-D-07 puts on every table, or record the disagreement."""
    if run["mode"] != manifest.mode or run["seed_set"] != manifest.seed_set:
        gaps["qualifiers"] = (
            f"the store's qualifiers (mode {run['mode']}, seed set {run['seed_set']}) "
            f"and the manifest's (mode {manifest.mode}, seed set {manifest.seed_set}) "
            f"disagree, so no table can be qualified")
        facts["qualifier"] = None
        return
    facts["qualifier"] = f"mode {run['mode']}, seed set {run['seed_set']}"


def _headline(facts: dict, filings: list, fingerprints: dict, candidates: dict,
              gaps: dict) -> None:
    """Count distinct confirmed bugs per arm, one per primary fingerprint (G-44)."""
    confirmed = [f for f in filings if _confirmed(f)]
    unfingerprinted = [f["candidate_id"] for f in confirmed
                       if (fingerprints.get(f["candidate_id"]) or {}).get("value") is None]
    if unfingerprinted:
        gaps["headline"] = (
            "the headline counts one bug per primary fingerprint and these "
            f"confirmed filings carry no fingerprint value: {sorted(unfingerprinted)}")
        facts["headline"] = None
        return
    facts["headline"] = {
        arm: {
            "filings": sum(1 for f in filings if f["arm"] == arm),
            "confirmed": sum(1 for f in confirmed if f["arm"] == arm),
            "distinct": len({fingerprints[f["candidate_id"]]["value"]
                             for f in confirmed if f["arm"] == arm}),
        } for arm in ARMS}
    facts["confirmed_filings"] = confirmed
    facts["fingerprints"] = fingerprints
    facts["candidate_by_id"] = candidates


def _secondaries(facts: dict, primary: list, dedups: dict, filings: list,
                 repairs: list, gaps: dict) -> None:
    """FR-18.4's five per arm, plus the repro-overwrite count FR-12.3 is reported by."""
    undeduped = [c["candidate_id"] for c in primary if c["candidate_id"] not in dedups]
    if undeduped:
        gaps["secondaries"] = (
            "candidates after dedup cannot be counted; these candidates carry no "
            f"dedup verdict: {sorted(undeduped)}")
        facts["secondaries"] = None
        return
    facts["secondaries"] = {
        arm: {
            "before_dedup": sum(1 for c in primary if c["arm"] == arm),
            "after_dedup": sum(1 for c in primary if c["arm"] == arm
                               and dedups[c["candidate_id"]]["verdict"] == "new"),
            "filings": sum(1 for f in filings if f["arm"] == arm),
            "confirmed": sum(1 for f in filings if f["arm"] == arm and _confirmed(f)),
            "merged": sum(1 for f in filings if f["arm"] == arm and _confirmed(f)
                          and f["decision"] == "report_plus_patch"),
            "repro_overwritten": sum(1 for r in repairs if r["arm"] == arm
                                     and r["repro_overwritten"]),
        } for arm in ARMS}


def _validation(facts: dict, seeds: list, probes: list, candidates: list,
                filings: list, gaps: dict) -> None:
    """FR-18.5's seeded-bug validation rows, which contribute nothing to the headline."""
    if not seeds:
        gaps["validation_table"] = (
            "the seeded-bug validation table is taken over the run's seed rows and "
            "the store holds none for this run")
        facts["validation"] = None
        return
    filed = {f["candidate_id"] for f in filings}
    by_seed = {}
    for seed in seeds:
        sha = seed["seed_sha"]
        seed_probes = [p["probe_id"] for p in probes if p["seed_sha"] == sha]
        seed_candidates = [c for c in candidates if c["probe_id"] in set(seed_probes)]
        by_seed[sha] = {
            "sdk_exact": bool(seed["sdk_exact"]),
            "eligible": f"{int(bool(seed['eligible_seeded']))}/"
                        f"{int(bool(seed['eligible_mutation']))}",
            "probes": len(seed_probes),
            "candidates": len(seed_candidates),
            "filings": sum(1 for c in seed_candidates if c["candidate_id"] in filed),
        }
    facts["validation"] = by_seed


def _contamination(facts: dict, primary: list, filings: list, fingerprints: dict,
                   candidates: dict, gaps: dict) -> None:
    """FR-15.2's column, and the headline printed with and without contamination."""
    unscreened = [c["candidate_id"] for c in primary
                  if c["contamination_lower_bound"] not in ("seed_commit", "run_commit")]
    if unscreened:
        gaps["contamination"] = (
            "a contaminated candidate is counted apart and these carry no "
            f"contamination lower bound: {sorted(unscreened)}")
        facts["contamination"] = None
        return

    def contaminated(candidate_id: str) -> bool:
        row = candidates.get(candidate_id) or {}
        return bool(row.get("contaminated_symbol") or row.get("contaminated_file"))

    confirmed = [f for f in filings if _confirmed(f)]
    facts["contamination"] = {
        arm: {
            "candidates": sum(1 for c in primary if c["arm"] == arm
                              and contaminated(c["candidate_id"])),
            "distinct_excluding": len({
                fingerprints[f["candidate_id"]]["value"] for f in confirmed
                if f["arm"] == arm and not contaminated(f["candidate_id"])
                and fingerprints.get(f["candidate_id"], {}).get("value") is not None}),
        } for arm in ARMS}


def _disclosures(facts: dict, repairs: list, gaps: dict) -> None:
    """FR-15.3's and FR-15.4's two sentences, and what the second one has to name."""
    nameless = [r["candidate_id"] for r in repairs if not (r["backend"] or "").strip()]
    if nameless:
        gaps["disclosures"] = (
            "the repair stage is declared unscreened and these attempts name no "
            f"backend to declare it of: {sorted(nameless)}")
        facts["disclosures"] = None
        return
    facts["disclosures"] = {
        "attempts": len(repairs),
        "backends": sorted({r["backend"] for r in repairs}),
    }


def _lag(facts: dict, stored: dict, gaps: dict) -> None:
    """ADR-D-10's lag disclosure, beside the headline it qualifies."""
    missing = [key for key in ("lag_commits", "lag_days", "current_window_has_release",
                               "pin_tag") if stored.get(key) is None]
    if missing:
        gaps["lag"] = ("the lag the campaign ran under is stated beside the headline "
                       f"and the stored manifest lacks {sorted(missing)}")
        facts["lag"] = None
        return
    facts["lag"] = {key: stored[key] for key in
                    ("lag_commits", "lag_days", "current_window_has_release", "pin_tag")}


def _cutoff(facts: dict, stored: dict, gaps: dict) -> None:
    """FR-18.8's confirmation cut-off date, which the whole headline is taken before."""
    date = (stored.get("confirmation_cutoff_date") or "").strip()
    if not date:
        gaps["cutoff"] = ("the confirmation cut-off date is mandatory and the stored "
                          "manifest carries none")
        facts["cutoff"] = None
        return
    facts["cutoff"] = date


def _dedup_rates(facts: dict, labelled_pairs, fingerprints: dict, primary: list,
                 top_n: int, gaps: dict) -> None:
    """FR-10.2's two measured rates, and the unstable fingerprints that qualify them.

    The rates come from the LABELLED SET'S OWN RECORD and not from the store.
    They are an external measurement of the project (`04-Test-Plan.md` §10,
    A-05): the pairs were labelled by hand before any fingerprint was computed,
    over recorded failures that belong to no campaign, and requiring the store
    to carry a fingerprint for each side made the rates unreportable by exactly
    the runs that most need them - a campaign that confirms nothing has no such
    candidate, so `render_results` refused at the end of every run
    (`T-S-regen-01`'s one remaining refusal).

    The one refusal that stays is a set that is not there at all: a rate the
    renderer invented for itself would be worse than a named gap.

    `fingerprints` and `primary` are still the STORE's, and are still what
    `facts["unstable"]` counts: an unstable fingerprint qualifies this run's
    headline exactly as a collision does, and that is a fact about this run.
    """
    facts["unstable"] = sum(1 for c in primary
                            if (fingerprints.get(c["candidate_id"]) or {})
                            .get("fingerprint_stable") == 0)
    if not labelled_pairs:
        gaps["dedup_rates"] = (
            "the collision and false-merge rates are measured over the labelled "
            "duplicate-pair set of FR-10.2 and none was supplied")
        facts["dedup_rates"] = None
        return
    facts["dedup_rates"] = rates(
        [{"label": pair["label"],
          "a": labelled_fingerprint(pair["a"], top_n),
          "b": labelled_fingerprint(pair["b"], top_n)}
         for pair in labelled_pairs])


def _divergences(facts: dict, candidates: list, reports: list, differentials: dict,
                 probes: dict, gaps: dict) -> None:
    """FR-18.12's list, counted apart from the candidate count and from the headline."""
    differential_candidates = [c for c in candidates if c["oracle_class"] == "differential"]
    reported = {r["candidate_id"] for r in reports if r["template"] == "differential"}
    unreported = [c["candidate_id"] for c in differential_candidates
                  if c["candidate_id"] not in reported]
    if unreported:
        gaps["divergences"] = (
            "every divergence is listed through its informational report and these "
            f"differential candidates have none: {sorted(unreported)}")
        facts["divergences"] = None
        return
    listed = []
    for report in reports:
        if report["template"] != "differential":
            continue
        candidate = next(c for c in candidates if c["candidate_id"] == report["candidate_id"])
        verdict = differentials.get(candidate["probe_id"], {})
        listed.append({
            "candidate_id": candidate["candidate_id"],
            "arm": candidate["arm"],
            "seed_sha": (probes.get(candidate["probe_id"]) or {}).get("seed_sha", ""),
            "verdict": verdict.get("verdict", "unrecorded"),
            "signal": verdict.get("first_divergent_signal") or "",
            "cycle": verdict.get("first_divergent_cycle"),
            "title": report["title"],
        })
    facts["divergences"] = listed


def _mutator_declaration(facts: dict, stored: dict, ledger_rows: list,
                         gaps: dict) -> None:
    """FR-05.8's declaration: the synthesis input, its date and the frozen set's SHA.

    The date is the `shared` ledger entry the offline synthesis is charged to,
    which is where FR-14.4's acceptance puts it; the input is the issue mirror
    the synthesis read, as the manifest records it.
    """
    charged = [row for row in ledger_rows
               if row["stage"] == SYNTHESIS_STAGE and row["arm"] == "shared"]
    mirror = stored.get("issue_mirror") or {}
    missing = []
    if not (stored.get("mutator_set_sha") or "").strip():
        missing.append("mutator_set_sha")
    if not charged:
        missing.append(f"a shared ledger entry at stage {SYNTHESIS_STAGE!r}, which "
                       "carries the synthesis date")
    if not mirror.get("refreshed_utc"):
        missing.append("issue_mirror.refreshed_utc, the synthesis input's own date")
    if missing:
        gaps["mutator_declaration"] = (
            "the mutator-synthesis declaration names its input, its date and the "
            f"frozen set's SHA, and the store lacks {missing}")
        facts["mutator_declaration"] = None
        return
    facts["mutator_declaration"] = {
        "set_sha": stored["mutator_set_sha"],
        "synthesised_utc": charged[0]["timestamp_utc"],
        "model": (stored.get("model_ids") or {}).get("mutator_synthesis", "unrecorded"),
        "issues": mirror.get("issues_mirrored"),
        "mirror_refreshed_utc": mirror["refreshed_utc"],
        "mirror_state": mirror.get("state", ""),
    }


def _observed(facts: dict, ledger_rows: list, gaps: dict) -> None:
    """FR-14.5's observations: tokens, money and CPU time, which are not the budget."""
    malformed = [row["entry_id"] for row in ledger_rows
                 if set(json.loads(row["observed_json"])) != OBSERVED_KEYS]
    if malformed:
        gaps["observed_heading"] = (
            "tokens, cost and CPU time are summed from every entry's observed block "
            f"and these blocks do not carry §2.7's four keys: {sorted(malformed)}")
        facts["observed"] = None
        return
    totals = {arm: {"cpu_seconds": 0.0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                    "null_token_entries": 0}
              for arm in ARMS + ("shared",)}
    unpriced = 0
    for row in ledger_rows:
        block = json.loads(row["observed_json"])
        bucket = totals[row["arm"]]
        bucket["cpu_seconds"] += float(block["cpu_seconds"] or 0.0)
        bucket["cost_usd"] += float(block["cost_usd"] or 0.0)
        if block["tokens_in"] is None or block["tokens_out"] is None:
            bucket["null_token_entries"] += 1
            # K10: an entry the manifest says is METERED and whose tokens are
            # null is a turn the run paid for and did not observe. It is the
            # count that makes the USD total a lower bound by a stated amount
            # rather than by an unstated one.
            if row["metered"] and row["stage"] in MODEL_STAGES:
                unpriced += 1
        else:
            bucket["tokens_in"] += int(block["tokens_in"])
            bucket["tokens_out"] += int(block["tokens_out"])
    facts["observed"] = totals
    facts["unpriced_turns"] = unpriced
    facts["authorisation"] = _authorisation(ledger_rows)


def _authorisation(ledger_rows: list) -> dict:
    """How close the pre-authorisation came to what the turns actually billed.

    The one number errata row 38 exists for. `SpendGuard` authorises a turn
    before it is sent and the ledger records what it billed; until W-18b the
    two were 19.7x to 64.1x apart and NOTHING printed the ratio, so the
    campaign's own artefact could not say the control was broken. A ratio ABOVE
    1.0 is a turn that cost more than it was authorised for, which is the
    campaign spending money the cap did not stop.

    Returns:
        {"turns", "max_ratio", "mean_ratio", "over_authorised", "hit_ceiling"};
        the two ratios are None when no turn carried both figures.
    Worker:
        pure; it reads the rows it is handed.
    Raises:
        nothing.
    """
    ratios, ceiling_hits = [], 0
    for row in ledger_rows:
        block = json.loads(row["observed_json"])
        authorised, billed = block.get("authorised_usd"), block.get("billed_usd")
        if not authorised or billed is None:
            continue
        ratios.append(billed / authorised)
        if block.get("ceiling_usd") and billed >= float(block["ceiling_usd"]):
            ceiling_hits += 1
    return {"turns": len(ratios),
            "max_ratio": max(ratios) if ratios else None,
            "mean_ratio": sum(ratios) / len(ratios) if ratios else None,
            "over_authorised": sum(1 for r in ratios if r > 1.0),
            "hit_ceiling": ceiling_hits}


def _windows(facts: dict, store: LoopStore, manifest: RunManifest, ledger_rows: list,
             gaps: dict) -> None:
    """FR-18.10's two windows, the binding cap and the unspent balance where one bit."""
    aggregate = ledger_module.aggregate(manifest.run_manifest_id, store.db_path)
    absent = [arm for arm in ARMS if arm not in aggregate.per_arm_window]
    if absent:
        gaps["both_windows"] = (
            "both arms' windows are printed beside the headline and no arm_window "
            f"entry exists for {absent}")
        facts["windows"] = None
        return
    facts["ledger"] = aggregate
    facts["windows"] = {
        arm: {
            "elapsed": aggregate.per_arm_window[arm],
            "window": manifest.arm_window_seconds,
            "unspent": max(0.0, manifest.arm_window_seconds
                           - aggregate.per_arm_window[arm]),
            "stop_reason": aggregate.stop_reason.get(arm),
            "spend_usd": aggregate.per_arm_spend_usd.get(arm, 0.0),
        } for arm in ARMS}
    facts["shared_stage"] = aggregate.shared_stage
    facts["spend_usd"] = aggregate.spend_usd


def _taxonomy(facts: dict, primary: list, gates: dict, repairs: list,
              probe_results: list) -> None:
    """FR-18.6's three counts: the gate's buckets, the repair phases, the probe outcomes.

    No gap of its own: a candidate the gate never reached is counted in the
    `no gate decision` row rather than dropped, which is what makes the sum
    check meaningful.
    """
    buckets = {bucket: 0 for bucket in BUCKETS}
    undecided_rows = 0
    for candidate in primary:
        gate = gates.get(candidate["candidate_id"])
        bucket = (gate or {}).get("taxonomy_bucket") or candidate["taxonomy_bucket"]
        if bucket in buckets:
            buckets[bucket] += 1
        else:
            undecided_rows += 1
    facts["taxonomy"] = {"buckets": buckets, "ungated": undecided_rows,
                         "candidates": len(primary),
                         "differential": len(facts["candidates"]) - len(primary)}

    phases: dict = {}
    for repair in repairs:
        phases[repair["failing_phase"] or "none (the attempt ran to the end)"] = \
            phases.get(repair["failing_phase"] or "none (the attempt ran to the end)", 0) + 1
    facts["repair_phases"] = {"phases": phases, "attempts": len(repairs)}

    outcomes = {arm: {} for arm in ARMS}
    for row in probe_results:
        if row["arm"] not in outcomes:
            continue
        # `stopping_reason` is the reason the PROBE stopped since W3, so it is
        # stage 3's own only while stage 3 is where the probe stopped; a
        # `parse_error` that went on to the differential carries that verdict
        # instead and is printed as the plain status rather than as a third
        # `parse_error:` row that means something else.
        key = (f"parse_error:{row['stopping_reason']}"
               if row["build_status"] == "parse_error"
               and row["stopping_reason"] in PARSE_REASONS else row["build_status"])
        outcomes[row["arm"]][key] = outcomes[row["arm"]].get(key, 0) + 1
    facts["outcomes"] = outcomes


def _repair_view(row: Optional[dict]):
    """The two fields `gate.decide` reads off a repair, from its stored row.

    `decide` asks a repair whether it `fixed` the bug and whether `lit_ok`, and
    nothing else; regenerating a gate decision therefore needs those two and not
    a whole `RepairResult`, whose other twenty-odd fields the decision does not
    read.

    Returns:
        an object carrying `fixed` and `lit_ok`, or None where no repair ran.
    Worker:
        pure.
    Raises:
        nothing.
    """
    return None if row is None else SimpleNamespace(fixed=row["fixed"],
                                                    lit_ok=row["lit_ok"])


def _regeneration(facts: dict, store: LoopStore, candidates: list, gaps: dict) -> None:
    """FR-18.11: re-derive every row from its recorded artefacts, and mark what will not.

    The deterministic head-side stages are re-run here, from the store and from
    the artefact tree: `probe_task.classify_build` over the recorded stderr, and
    `gate.decide` over the recorded answers. Re-executing the tool stages inside
    an image of the recorded digest is `04-Test-Plan.md` §11's system half and
    is not attempted here; a row whose image is gone is marked
    `image_unavailable`, which §11 calls a retention failure and not a
    reproducibility one.
    """
    rows = []
    missing_results = []
    for candidate in candidates:
        probe_id = candidate["probe_id"]
        result = store.query_one("SELECT * FROM probe_result WHERE probe_id = ?",
                                 (probe_id,))
        if result is None:
            missing_results.append(candidate["candidate_id"])
            continue
        marks = []
        if store.query_one("SELECT 1 FROM image WHERE image_digest = ?",
                           (candidate["image_digest"],)) is None:
            marks.append(IMAGE_UNAVAILABLE)

        build = store.query_one("SELECT * FROM build_result WHERE probe_id = ?",
                                (probe_id,))
        if build is None:
            marks.append("build_result_missing")
        elif not Path(build["stderr_path"]).is_file():
            marks.append(f"artefact_missing:{build['stderr_path']}")
        else:
            stderr = Path(build["stderr_path"]).read_text(
                encoding="utf-8", errors="backslashreplace")
            # Against the BUILD's own status and not the ProbeResult's pair:
            # since W3 `probe_result.stopping_reason` is the reason the PROBE
            # stopped, wherever it stopped, and stage 3's own reason is not
            # stored beside the status it refines. `build_result.status` is
            # stage 3's record, written once and never updated, which is what
            # FR-18.7's regeneration is about.
            again = classify_build(build["exit_status"], build["signal"], stderr,
                                   build["limit_hit"])
            if again[0] != build["status"]:
                marks.append(f"build_classification_differs:{again[0]}:{again[1]}")

        reduced = store.query_one("SELECT * FROM reduced_case WHERE probe_id = ?",
                                  (probe_id,))
        if reduced is not None and reduced["budget_truncated"]:
            marks.append(BUDGET_TRUNCATED)

        gate = store.query_one("SELECT * FROM gate_decision WHERE candidate_id = ?",
                               (candidate["candidate_id"],))
        if gate is not None:
            repair = store.query_one("SELECT * FROM repair WHERE candidate_id = ?",
                                     (candidate["candidate_id"],))
            decision, stopped, bucket = decide(json.loads(gate["answers_json"]),
                                               _repair_view(repair))
            if (decision, stopped, bucket) != (gate["decision"],
                                               gate["stopped_at_question"],
                                               gate["taxonomy_bucket"]):
                marks.append(f"gate_decision_differs:{decision}:{bucket}")
        rows.append({"candidate_id": candidate["candidate_id"], "arm": candidate["arm"],
                     "regenerated": not marks, "marks": marks})
    if missing_results:
        gaps["regeneration_marks"] = (
            "every results row is regenerated or marked, and these candidates have "
            f"no probe_result to do either from: {sorted(missing_results)}")
        facts["regeneration"] = None
        return
    facts["regeneration"] = rows


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _table(lines: list, caption: str, header: list, rows: list, qualifier: str) -> None:
    """Append one qualified Markdown table; ADR-D-07 puts the qualifiers on every one."""
    lines += [f"**{caption}** ({qualifier or 'UNQUALIFIED'})", ""]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join("---" for _ in header) + "|")
    for row in rows:
        lines.append("| " + " | ".join("" if cell is None else str(cell)
                                       for cell in row) + " |")
    lines.append("")


def _render(facts: dict) -> str:
    """Render the artefact from the facts, leaving out only what the store lacks.

    A section whose fact is None prints the reason the store could not support
    it, so the text and the refusal say the same thing; the refusal is what
    stops the artefact being published with the hole in it.
    """
    qualifier = facts["qualifier"]
    manifest: RunManifest = facts["manifest"]
    gaps = facts["gaps"]
    lines = [
        "# Results: the closed CIRCT bug loop",
        "",
        f"Run `{facts['run_id']}`. {(qualifier or 'UNQUALIFIED').capitalize()}. "
        f"Arms run sequentially, {' then '.join(manifest.arm_order)}, "
        f"each for {manifest.arm_window_seconds:.0f} wall-clock seconds.",
        "",
        "Every table below carries the mode and the seed set it was taken under, "
        "and every number in it comes from a tool-produced record in `loop.db`.",
        "",
        "## 1. Headline",
        "",
    ]

    if facts["headline"] is None:
        lines += [f"REFUSED: {gaps['headline']}", ""]
    else:
        _table(lines, "Distinct confirmed bugs per arm",
               ["arm", "distinct confirmed bugs", "confirmed filings", "filings",
                "distinct excluding contaminated"],
               [[arm, facts["headline"][arm]["distinct"],
                 facts["headline"][arm]["confirmed"], facts["headline"][arm]["filings"],
                 (facts["contamination"] or {}).get(arm, {}).get("distinct_excluding")]
                for arm in ARMS], qualifier)
        lines += [
            "A confirmed bug is one a maintainer acted on, evidenced by a URL; "
            "distinct is one per primary fingerprint, so two filings sharing a "
            "fingerprint count once. "
            + " ".join("The {} arm confirmed {}.".format(
                arm, _count(facts["headline"][arm]["distinct"], "distinct bug"))
                for arm in ARMS),
            "",
        ]

    if facts["contamination"] is None:
        lines += [f"REFUSED: {gaps['contamination']}", ""]
    else:
        _table(lines, "Contaminated candidates, counted apart (FR-15.2)",
               ["arm", "contaminated candidates", "distinct confirmed bugs excluding them"],
               [[arm, facts["contamination"][arm]["candidates"],
                 facts["contamination"][arm]["distinct_excluding"]] for arm in ARMS],
               qualifier)

    if facts["lag"] is None:
        lines += [f"REFUSED: {gaps['lag']}", ""]
    else:
        lag = facts["lag"]
        lines += [
            f"**Lag.** The campaign ran at a pin {lag['lag_commits']} commits and "
            f"{lag['lag_days']} days behind `main`, on `{lag['pin_tag']}`; the current "
            "pin window "
            f"{'contains a release' if lag['current_window_has_release'] else 'contains no release'}"
            ". A longer lag mechanically lowers the filing rate, because more "
            "candidates come back already fixed and every such candidate fails the "
            "gate's fourth question.",
            "",
        ]

    if facts["cutoff"] is None:
        lines += [f"REFUSED: {gaps['cutoff']}", ""]
    else:
        lines += [
            "**Confirmation cut-off.** Maintainer confirmation lags the budget window: "
            "a filing is confirmed when a maintainer labels, comments on or fixes it, "
            "which happens after the window has closed. Confirmations recorded after "
            f"{facts['cutoff']} are not counted in the headline above.",
            "",
        ]

    if facts["dedup_rates"] is None:
        lines += [f"REFUSED: {gaps['dedup_rates']}", ""]
    else:
        measured = facts["dedup_rates"]
        lines += [
            "**Dedup rates, which qualify the headline.** Collision rate "
            f"{measured['collisions']}/{measured['distinct_pairs']} = "
            f"{measured['collision_rate']:.4f}; false-merge rate "
            f"{measured['false_merges']}/{measured['duplicate_pairs']} = "
            f"{measured['false_merge_rate']:.4f}, both measured over the "
            "hand-labelled duplicate-pair set. "
            f"{_count(facts['unstable'], 'candidate')} "
            f"{'carries' if facts['unstable'] == 1 else 'carry'} an unstable "
            "fingerprint, which qualifies the headline exactly as a collision does "
            "and never merges.",
            "",
        ]

    seeded_seeds = {p["seed_sha"] for p in facts["probe_rows"] if p["arm"] == "seeded"}
    mutation_seeds = {p["seed_sha"] for p in facts["probe_rows"]
                      if p["arm"] == "mutation"}
    lines += [
        f"**Seed sets.** The seeded arm probed {len(seeded_seeds)} seeds and the "
        f"mutation arm {len(mutation_seeds)}; the two sets are "
        f"{'identical' if seeded_seeds == mutation_seeds else 'NOT identical'}, which "
        "FR-18.2 requires within a mode.",
        "",
        "## 2. Secondary results",
        "",
    ]

    if facts["secondaries"] is None:
        lines += [f"REFUSED: {gaps['secondaries']}", ""]
    else:
        _table(lines, "The five secondaries per arm",
               ["arm", "candidates before dedup", "candidates after dedup", "filings",
                "gate precision", "repairs merged", "repro.sh overwritten"],
               [[arm, facts["secondaries"][arm]["before_dedup"],
                 facts["secondaries"][arm]["after_dedup"],
                 facts["secondaries"][arm]["filings"],
                 _percent(facts["secondaries"][arm]["confirmed"],
                          facts["secondaries"][arm]["filings"]),
                 facts["secondaries"][arm]["merged"],
                 facts["secondaries"][arm]["repro_overwritten"]] for arm in ARMS],
               qualifier)
        lines += [
            "Gate precision is confirmed filings over filings. A merged repair is a "
            "filed patch a maintainer acted on, which is the same evidence the "
            "headline takes. `repro.sh overwritten` counts the repair attempts whose "
            "reproduce turn replaced the script the loop pre-wrote, so that "
            "\"confirms rather than invents\" is reported per attempt rather than "
            "assumed.",
            "",
        ]

    lines += ["## 3. Failure taxonomy", ""]
    taxonomy = facts["taxonomy"]
    _table(lines, "FR-18.6's mapping, from gate stopping value to bucket",
           ["gate question", "stopping value", "bucket"],
           [[question, value, bucket]
            for (question, value), bucket in sorted(TAXONOMY.items())]
           + [["none", "passed all four", "new_bug"]], qualifier)
    _table(lines, "Candidates at the gate, one bucket each",
           ["bucket", "candidates"],
           [[bucket, taxonomy["buckets"][bucket]] for bucket in BUCKETS]
           + [["no gate decision", taxonomy["ungated"]]], qualifier)
    lines += [
        f"Sum check: {sum(taxonomy['buckets'].values()) + taxonomy['ungated']} bucketed "
        f"= {_count(taxonomy['candidates'], 'candidate')} reaching the gate. "
        f"{_count(taxonomy['differential'], 'differential candidate')} "
        "excluded by construction: they never enter the gate and are counted in the "
        "divergences list instead.",
        "",
    ]
    phases = facts["repair_phases"]
    _table(lines, "Repair attempts, by the phase that failed",
           ["failing phase", "attempts"],
           sorted(phases["phases"].items()) or [["none", 0]], qualifier)
    lines += [f"Sum check: {sum(phases['phases'].values())} = {phases['attempts']} "
              "repair attempts.", ""]
    _table(lines, "Probe outcomes, by build status",
           ["outcome"] + list(ARMS),
           [[key] + [facts["outcomes"][arm].get(key, 0) for arm in ARMS]
            for key in _outcome_keys(facts)], qualifier)
    lines += [
        "`parse_error` is printed as two rows: `tool_rejected_input` is the tool "
        "refusing the probing input, and `tool_rejected_argv` is the tool refusing "
        "the argument vector the loop built, which is an apparatus defect and not a "
        "property of the input. They sum to the `parse_error` total.",
        "",
        "## 4. Seeded-bug validation, reported separately",
        "",
    ]

    if facts["validation"] is None:
        lines += [f"REFUSED: {gaps['validation_table']}", ""]
    else:
        _table(lines, "Seeded-bug validation, which contributes nothing to the headline",
               ["seed", "sdk exact", "eligible seeded/mutation", "probes", "candidates",
                "filings"],
               [[f"`{sha[:12]}`", row["sdk_exact"], row["eligible"], row["probes"],
                 row["candidates"], row["filings"]]
                for sha, row in facts["validation"].items()], qualifier)
        lines += [
            "This table is separate from the discovery result above and contributes "
            "nothing to it: validation establishes that the apparatus finds a bug it "
            "was pointed at, and the headline counts bugs nobody pointed it at.",
            "",
        ]

    lines += ["## 5. Divergences observed", ""]
    if facts["divergences"] is None:
        lines += [f"REFUSED: {gaps['divergences']}", ""]
    else:
        _table(lines, "Divergences observed, counted apart from the candidate count",
               ["candidate", "arm", "seed", "verdict", "first divergent signal",
                "cycle", "report"],
               [[f"`{row['candidate_id']}`", row["arm"], f"`{row['seed_sha'][:12]}`",
                 row["verdict"], row["signal"], row["cycle"], row["title"]]
                for row in facts["divergences"]] or [["none", "", "", "", "", "", ""]],
               qualifier)
        lines += [
            f"{_count(len(facts['divergences']), 'divergence')} observed. A "
            "divergence produces "
            "an informational report and nothing else: it enters no gate, is never "
            "filed, and is counted neither in the candidate count nor in the headline.",
            "",
        ]

    lines += ["## 6. The budget: both windows and the campaign's spend", ""]
    if facts["windows"] is None:
        lines += [f"REFUSED: {gaps['both_windows']}", ""]
    else:
        _table(lines, "Both arm windows, on the primary budget unit",
               ["arm", "window (s)", "elapsed (s)", "unspent (s)", "stopped by",
                "spend (USD)"],
               [[arm, f"{facts['windows'][arm]['window']:.0f}",
                 f"{facts['windows'][arm]['elapsed']:.0f}",
                 f"{facts['windows'][arm]['unspent']:.0f}",
                 facts["windows"][arm]["stop_reason"] or "its own window",
                 f"{facts['windows'][arm]['spend_usd']:.2f}"] for arm in ARMS],
               qualifier)
        lines += [
            f"The campaign spent USD {facts['spend_usd']:.2f} in total, both arms and "
            "the shared stages together, against the pre-registered cap. Where an arm "
            "was stopped by a safety cap rather than by its window, the unspent "
            "balance above is what it did not get to use, and the comparison is "
            "qualified by exactly that much.",
            "",
        ]
        _table(lines, "Shared stages, charged to no arm",
               ["stage", "seconds"],
               sorted((stage, f"{seconds:.0f}")
                      for stage, seconds in facts["shared_stage"].items())
               or [["none", "0"]], qualifier)

    lines += ["## 7. Observed, and not the budget", ""]
    if facts["observed"] is None:
        lines += [f"REFUSED: {gaps['observed_heading']}", ""]
    else:
        _table(lines, "Tokens, money and CPU time: observations, NOT the budget",
               ["arm", "prompt tokens", "output tokens", "USD", "CPU seconds",
                "entries with null token counts"],
               [[arm, facts["observed"][arm]["tokens_in"],
                 facts["observed"][arm]["tokens_out"],
                 f"{facts['observed'][arm]['cost_usd']:.4f}",
                 f"{facts['observed'][arm]['cpu_seconds']:.0f}",
                 facts["observed"][arm]["null_token_entries"]]
                for arm in ARMS + ("shared",)], qualifier)
        lines += [
            "None of these four is the budget. The budget is one elapsed wall-clock "
            "second of an arm's fixed window, and the table above is what the run was "
            "observed to consume while spending it. The USD total is a **lower bound "
            "excluding stage 7**, whose per-turn token counts the repair chain does "
            "not return: its turns are dispatched remotely and the counting copy of "
            "the model object dies with the worker.",
            "",
            f"**Unpriced turns: {facts['unpriced_turns']}.** That is the number of "
            "metered model-stage entries whose token counts were never observed, so "
            "they carry a null cost rather than a zero and the USD total above "
            "excludes every one of them. A turn that raised inside the tool loop "
            "reports nothing at all, however many model calls it had already made, "
            "and so does every stage-7 attempt by construction; the figure is what "
            "the lower bound is a lower bound BY, counted rather than described.",
            "",
        ]
        authorisation = facts["authorisation"]
        if authorisation["turns"]:
            lines += [
                f"**Billed against authorised, over {authorisation['turns']} "
                f"turn(s): max {authorisation['max_ratio']:.3f}x, mean "
                f"{authorisation['mean_ratio']:.3f}x; "
                f"{authorisation['over_authorised']} turn(s) billed more than "
                f"they were authorised for and {authorisation['hit_ceiling']} "
                "reached the backend's own per-turn ceiling.** `SpendGuard` "
                "authorises a turn before it is sent and this is how close the "
                "estimate came. A ratio above 1.0 is money the cap did not "
                "stop: W-18 measured 19.7x, 32.3x and 64.1x, because the "
                "authorisation bounded one model call and a turn with tools "
                "makes up to `max_tool_iterations` of them (errata row 38).",
                "",
            ]
        else:
            lines += [
                "**Billed against authorised: no turn carried both figures.** "
                "Either no model turn ran or every one of them raised before it "
                "was billed; the pre-authorisation cannot be checked against a "
                "measurement here.",
                "",
            ]

    lines += ["## 8. Declarations and disclosures", ""]
    if facts["mutator_declaration"] is None:
        lines += [f"REFUSED: {gaps['mutator_declaration']}", ""]
    else:
        declaration = facts["mutator_declaration"]
        lines += [
            "**The mutator synthesis is the one place the mutation arm sees bug "
            f"reports.** The frozen mutator set `{declaration['set_sha']}` was "
            f"synthesised at {declaration['synthesised_utc']} by "
            f"{declaration['model']} from the mirrored issue set refreshed at "
            f"{declaration['mirror_refreshed_utc']} ({declaration['issues']} issues, "
            f"{declaration['mirror_state']}). That is Mut4All's design, which this "
            "arm reimplements, and not a leak in the experiment: the arm reads no report "
            "during the campaign, and the set was frozen and committed before the "
            "pre-registration.",
            "",
        ]

    if facts["disclosures"] is None:
        lines += [f"REFUSED: {gaps['disclosures']}", ""]
    else:
        disclosures = facts["disclosures"]
        lines += [
            "**The contamination screen is incomplete.** It matches a candidate "
            "against the commits that touched the seed's files and symbols, and a "
            "seed's siblings may be fixed in commits whose subjects do not name them; "
            "a candidate this screen calls clean may still be one the upstream "
            "history knows about.",
            "",
            "**The repair stage is unscreened.** CHIA's executor runs unchanged, so "
            "the repair agent sees whatever its own chain shows it, and this run made "
            f"{disclosures['attempts']} repair attempts on "
            f"{', '.join(disclosures['backends']) or 'no backend'}. Nothing in the "
            "screen above applies to them.",
            "",
        ]

    lines += ["## 9. Regeneration", ""]
    if facts["regeneration"] is None:
        lines += [f"REFUSED: {gaps['regeneration_marks']}", ""]
    else:
        marked = [row for row in facts["regeneration"] if not row["regenerated"]]
        _table(lines, "Every results row, regenerated from its recorded artefacts",
               ["candidate", "arm", "regenerated", "marks"],
               [[f"`{row['candidate_id']}`", row["arm"],
                 "yes" if row["regenerated"] else "**MARKED**", ", ".join(row["marks"])]
                for row in facts["regeneration"]] or [["none", "", "", ""]], qualifier)
        lines += [
            f"{len(facts['regeneration']) - len(marked)} rows regenerated and "
            f"{len(marked)} marked. A marked row is **not reported as a result**: the "
            "deterministic stages were re-run from the stored inputs and disagreed "
            "with the record, or the artefacts they need are gone. Replaying a stored "
            "value through the bypass is never accepted as evidence for a tool stage.",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _outcome_keys(facts: dict) -> list:
    """Every probe-outcome row, with `parse_error` split into its two reasons."""
    seen = {key for arm in ARMS for key in facts["outcomes"][arm]}
    ordered = []
    for status in BUILD_STATUSES:
        if status == "parse_error":
            ordered += [f"parse_error:{reason}" for reason in PARSE_REASONS]
            ordered += sorted(key for key in seen if key.startswith("parse_error:")
                              and key.split(":", 1)[1] not in PARSE_REASONS)
        else:
            ordered.append(status)
    return ordered


# ---------------------------------------------------------------------------
# The fourteen refusals (03-LLD.md 3.11, 14.4)
# ---------------------------------------------------------------------------


def _element(facts: dict, key: str, text: str, needle: str, element: str) -> list:
    """Refuse when the store could not support an element, or the text lacks it."""
    gap = facts["gaps"].get(key)
    if gap is not None:
        return [gap]
    if needle not in text:
        return [f"{element} is absent from the rendered artefact"]
    return []


def _require_headline(text: str, facts: dict) -> list:
    """FR-18.3: distinct confirmed bugs per arm, from filings carrying a URL."""
    return _element(facts, "headline", text, "Distinct confirmed bugs per arm",
                    "the headline")


def _require_secondaries(text: str, facts: dict) -> list:
    """FR-18.4, FR-12.3: the five secondaries per arm, and the repro-overwrite count."""
    return _element(facts, "secondaries", text, "The five secondaries per arm",
                    "the secondary results")


def _require_validation_table(text: str, facts: dict) -> list:
    """FR-18.5: the seeded-bug validation table, separate from discovery."""
    return _element(facts, "validation_table", text,
                    "contributes nothing to the headline",
                    "the seeded-bug validation table")


def _require_qualifiers(text: str, facts: dict) -> list:
    """FR-18.2, ADR-D-07: the mode and the seed set, on every table."""
    gap = facts["gaps"].get("qualifiers")
    if gap is not None:
        return [gap]
    qualifier = facts["qualifier"]
    missing = []
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("|") or (index and lines[index - 1].startswith("|")):
            continue
        caption = next((lines[back] for back in range(index - 1, -1, -1)
                        if lines[back].strip()), "")
        if qualifier not in caption:
            missing.append(f"a table at line {index + 1} carries no mode and seed set")
    return missing


def _require_contamination(text: str, facts: dict) -> list:
    """FR-15.2: the contamination column, and the headline with and without it."""
    return _element(facts, "contamination", text,
                    "distinct confirmed bugs excluding them",
                    "the contamination column")


def _require_disclosures(text: str, facts: dict) -> list:
    """FR-15.3, FR-15.4: the two disclosure sentences."""
    missing = _element(facts, "disclosures", text,
                       "The contamination screen is incomplete",
                       "the incompleteness disclosure")
    if "The repair stage is unscreened" not in text and not missing:
        missing.append("the unscreened-repair disclosure is absent from the artefact")
    return missing


def _require_lag(text: str, facts: dict) -> list:
    """ADR-D-10: the lag the campaign ran under, beside the headline."""
    return _element(facts, "lag", text, "**Lag.**", "the lag disclosure")


def _require_cutoff(text: str, facts: dict) -> list:
    """FR-18.8: the confirmation cut-off date, and the lag it exists for."""
    return _element(facts, "cutoff", text, "**Confirmation cut-off.**",
                    "the confirmation cut-off date")


def _require_dedup_rates(text: str, facts: dict) -> list:
    """FR-10.2: the collision and false-merge rates, and the unstable fingerprints."""
    return _element(facts, "dedup_rates", text, "false-merge rate",
                    "the collision and false-merge rates")


def _require_divergences(text: str, facts: dict) -> list:
    """FR-18.12: the divergences-observed list."""
    return _element(facts, "divergences", text, "Divergences observed",
                    "the divergences-observed list")


def _require_mutator_declaration(text: str, facts: dict) -> list:
    """FR-05.8: the synthesis declaration, with its input, date and frozen-set SHA."""
    return _element(facts, "mutator_declaration", text,
                    "the one place the mutation arm sees bug reports",
                    "the mutator-synthesis declaration")


def _require_observed_heading(text: str, facts: dict) -> list:
    """FR-14.5, FR-14.6: tokens, money and CPU under a heading saying they are not it."""
    missing = _element(facts, "observed_heading", text, "NOT the budget",
                       "the observed-and-not-the-budget heading")
    if not missing and "lower bound" not in text:
        missing.append("the sentence that the USD total is a lower bound excluding "
                       "stage 7 is absent from the artefact")
    return missing


def _require_both_windows(text: str, facts: dict) -> list:
    """FR-18.10: both arm windows, the binding cap and the unspent balance."""
    return _element(facts, "both_windows", text, "Both arm windows",
                    "both arms' windows")


def _require_regeneration_marks(text: str, facts: dict) -> list:
    """FR-18.11: every row that could not be regenerated, marked rather than reported."""
    return _element(facts, "regeneration_marks", text,
                    "regenerated from its recorded artefacts",
                    "the regeneration check")


#: §3.11's tuple, in §14.4's order. `len(_REFUSALS) == 14` is asserted by
#: `tests/test_results.py`, and a fifteenth name in either document fails it.
_REFUSALS = (_require_headline, _require_secondaries, _require_validation_table,
             _require_qualifiers, _require_contamination, _require_disclosures,
             _require_lag, _require_cutoff, _require_dedup_rates,
             _require_divergences, _require_mutator_declaration,
             _require_observed_heading, _require_both_windows,
             _require_regeneration_marks)


@ChiaFunction(max_retries=0)
def render_results(store: LoopStore, manifest: RunManifest, *,
                   labelled_pairs: Optional[list] = None,
                   fingerprint_top_n: int = 5) -> dict:
    """Render one run's results artefact as Markdown, or refuse and name what is missing.

    Every number is read from `loop.db` and from the artefact tree it points at.
    *labelled_pairs* is FR-10.2's hand-labelled duplicate-pair set, each entry
    `{"label": "duplicate"|"distinct", "a": side, "b": side}` where a side is
    the RECORDED FAILURE `data/labelled_pairs.json` carries. Both the labels and
    the failures are the project's, recorded before any fingerprint was
    computed, and the fingerprints are computed FROM THEM by
    `triage_task.labelled_fingerprint` rather than looked up in this run's
    store: the set is a committed measurement of the project and not a row of
    the campaign, and requiring the store to hold a fingerprint per side made
    the rates unreportable by every campaign that confirms nothing, which is the
    refusal `T-S-regen-01` recorded at the end of every run.

    *fingerprint_top_n* is `budget.yaml`'s registered `fingerprint_top_n`
    (G-43), which is the N the labelled set was measured at; the driver passes
    the run's own and the default is the registered `[DEFAULT]` of 5.

    The render succeeds from an empty confirmation set and states the zero
    (FR-18.7), and it names no external bug yield anywhere, so no sentence in
    it can compare this loop's count to one (FR-18.9).

    Returns:
        {"rendered": str, "counters": CounterBlock}, the Markdown artefact
        ending in exactly one newline, and one artefact counted at stage
        "results", which 3.11 requires of every node of 3.2.
    Worker:
        `@ChiaFunction(max_retries=0)` on the head, 600 s `[DEFAULT]` enforced
        by the driver (§3.2); a pure function of the store, so a re-render is a
        no-op.
    Raises:
        ResultsIncomplete carrying every element the store cannot support, with
        no partial artefact returned; sqlite3.Error from any query.
    """
    started_at = time.monotonic()
    facts = _facts(store, manifest, labelled_pairs, fingerprint_top_n)
    text = _render(facts)
    missing = [complaint for check in _REFUSALS for complaint in check(text, facts)]
    if missing:
        raise ResultsIncomplete(missing)
    return {"rendered": text,
            "counters": CounterBlock(
                stage="results", started=1, completed=1, failed=0,
                seconds=time.monotonic() - started_at)}


__all__ = ["render_results", "ResultsIncomplete", "ARMS", "BUCKETS",
           "LABELLED_PAIRS", "load_labelled_pairs"]
