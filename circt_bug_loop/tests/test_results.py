"""`results.py` (B11): the fourteen refusals, the headline, and the regeneration check."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from circt_bug_loop.gate import TAXONOMY
from circt_bug_loop.results import (ARMS, BUCKETS, OBSERVED_KEYS,
                                    TURN_FAILURE_DETAIL_CAP,
                                    _facts, _REFUSALS, _require_qualifiers,
                                    ResultsIncomplete, render_results)
from circt_bug_loop.tests.conftest import call_node
from circt_bug_loop.tests.fixtures.results import make_store

pytestmark = pytest.mark.t0

#: The render committed beside the generator.
EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "results" / "example.md"

#: The recorded tool stderr the mini-campaign is built from.
FIXTURES_STDERR = Path(__file__).resolve().parent / "fixtures" / "stderr"

#: `03-LLD.md` §14.4's table, in §3.11's order.
REFUSAL_NAMES = (
    "_require_headline", "_require_secondaries", "_require_validation_table",
    "_require_qualifiers", "_require_contamination", "_require_disclosures",
    "_require_lag", "_require_cutoff", "_require_dedup_rates",
    "_require_divergences", "_require_mutator_declaration",
    "_require_observed_heading", "_require_both_windows",
    "_require_regeneration_marks")

#: FR-18.9's four external yields.
EXTERNAL_YIELDS = ("FLEX", "ISSTA", "Nüwa", "Nuwa", "DESIL")

_RUN = make_store.RUN


def campaign(tmp_path, name: str = "full"):
    """Regenerate the fixture mini-campaign under *tmp_path*/*name*."""
    return make_store.build(Path(tmp_path) / name)


def render(store, manifest, pairs) -> str:
    """Call B11 the way the driver does, through `conftest.call_node` (§0.4)."""
    out = call_node(render_results, store, manifest, labelled_pairs=pairs)
    assert out["counters"].stage == "results"
    return out["rendered"]


def refuse(store, manifest, pairs) -> list:
    """Render, expect a refusal, and return every element it named."""
    with pytest.raises(ResultsIncomplete) as raised:
        render(store, manifest, pairs)
    return raised.value.missing


def only(missing: list, *needles: str) -> str:
    """Assert exactly one element was refused and that it names every *needle*."""
    assert len(missing) == 1, missing
    for needle in needles:
        assert needle in missing[0], missing[0]
    return missing[0]


def delete(store, sql: str, params: tuple = ()) -> None:
    """One DELETE through the store's own batching member, foreign keys on."""
    store.transaction([(sql, params)])


def restate(store, **overrides) -> None:
    """Rewrite the stored `RunManifest` with *overrides* applied."""
    row = store.query_one("SELECT manifest_json FROM run WHERE run_manifest_id = ?",
                          (_RUN,))
    stored = json.loads(row["manifest_json"])
    stored.update(overrides)
    store.update("run", {"run_manifest_id": _RUN},
                 {"manifest_json": json.dumps(stored, sort_keys=True)})


def tables(text: str) -> list:
    """Every Markdown table in *text*, as `{"header": [...], "rows": [[...]]}`."""
    blocks, current = [], []
    for line in text.splitlines():
        if line.startswith("|"):
            current.append([cell.strip() for cell in line.strip("|").split("|")])
        elif current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return [{"header": block[0], "rows": block[2:]} for block in blocks]


def arm_tables(text: str) -> list:
    """Every table whose first column is the arm, as `{arm: rest of the row}`."""
    return [{row[0]: row[1:] for row in table["rows"]}
            for table in tables(text) if table["header"][0] == "arm"]


def section(text: str, heading: str) -> str:
    """One `## ` section of the artefact, heading included."""
    body = text.split(f"\n## {heading}", 1)
    assert len(body) == 2, f"no section {heading!r} in the artefact"
    return "## " + heading + body[1].split("\n## ", 1)[0]


def test_T_U_results_01(tmp_path):
    """T-U-results-01 (FR-18.3): the headline, per arm, one bug per fingerprint."""
    store, manifest, pairs = campaign(tmp_path)
    headline = arm_tables(render(store, manifest, pairs))[0]
    # c-0001 is confirmed with a URL; c-0002 is filed and not confirmed.
    assert headline["seeded"][:3] == ["1", "1", "2"]
    assert headline["mutation"][:3] == ["0", "0", "0"]

    # A second confirmed filing on the same fingerprint counts once.
    store.update("filing", {"candidate_id": "c-0002"},
                 {"confirmed": 1, "confirmed_at_utc": "2026-09-22T10:00:00+00:00",
                  "confirmation_url": "https://github.com/llvm/circt/issues/11000#c-1"})
    store.update("fingerprint", {"candidate_id": "c-0002"},
                 {"basis": "assertion",
                  "value": store.query_one(
                      "SELECT value FROM fingerprint WHERE candidate_id = 'c-0001'"
                  )["value"]})
    headline = arm_tables(render(store, manifest, pairs))[0]
    assert headline["seeded"][:3] == ["1", "2", "2"], "two filings, one fingerprint"

    # The refusal: a confirmed filing with no fingerprint value.
    store.update("fingerprint", {"candidate_id": "c-0001"},
                 {"basis": "insufficient", "value": None})
    only(refuse(store, manifest, pairs), "one bug per primary fingerprint", "c-0001")


def test_T_U_results_02(tmp_path):
    """T-U-results-02 (FR-18.4): the five secondaries, and the overwrites."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    secondaries = arm_tables(text)[2]
    assert secondaries["seeded"] == ["2", "2", "2", "1/2 (50.0%)", "1", "1"]
    assert secondaries["mutation"] == ["1", "0", "0", "n/a (0 filings)", "0", "0"]
    assert "repro.sh overwritten" in text

    delete(store, "DELETE FROM dedup_verdict WHERE candidate_id = ?", ("c-0002",))
    only(refuse(store, manifest, pairs), "candidates after dedup cannot be counted",
         "c-0002")


def test_T_U_results_03(tmp_path):
    """T-U-results-03 (FR-18.5): validation is a separate table, feeding nothing."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    validation = section(text, "4. Seeded-bug validation, reported separately")
    rows = tables(validation)[0]["rows"]
    assert len(rows) == 2 and [row[-1] for row in rows] == ["1", "1"]
    assert "contributes nothing to the headline" in validation
    headline = arm_tables(text)[0]
    assert sum(int(row[-1]) for row in rows) == 2
    assert sum(int(headline[arm][0]) for arm in ARMS) == 1

    delete(store, "DELETE FROM seed WHERE run_manifest_id = ?", (_RUN,))
    only(refuse(store, manifest, pairs), "the store holds none for this run")


def test_T_U_results_04(tmp_path):
    """T-U-results-04 (FR-18.2): the mode and the seed set, on every table."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert text.count("(mode discovery, seed set 187)") == len(tables(text))

    facts = _facts(store, manifest, pairs, 5)
    stripped = text.replace("**Distinct confirmed bugs per arm** "
                            "(mode discovery, seed set 187)",
                            "**Distinct confirmed bugs per arm**")
    complaints = _require_qualifiers(stripped, facts)
    assert len(complaints) == 1 and "carries no mode and seed set" in complaints[0]

    store.update("run", {"run_manifest_id": _RUN}, {"seed_set": "171"})
    only(refuse(store, manifest, pairs), "disagree", "no table can be qualified")


def test_T_U_results_05(tmp_path):
    """T-U-results-05 (FR-15.2): contamination counted apart, headline both ways."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert "distinct confirmed bugs excluding them" in text
    headline, contamination = arm_tables(text)[0], arm_tables(text)[1]
    assert headline["seeded"][0] == "1" and headline["seeded"][-1] == "0"
    assert contamination["seeded"] == ["1", "0"]
    assert contamination["mutation"] == ["0", "0"]

    store.update("candidate", {"candidate_id": "c-0002"},
                 {"contamination_lower_bound": "not_screened"})
    only(refuse(store, manifest, pairs), "no contamination lower bound", "c-0002")


def test_T_U_results_06(tmp_path):
    """T-U-results-06 (FR-15.3): both disclosure sentences, and the backend."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert "**The contamination screen is incomplete.**" in text
    assert "**The repair stage is unscreened.**" in text
    assert "2 repair attempts on vertex" in text

    store.update("repair", {"candidate_id": "c-0001"}, {"backend": "  "})
    only(refuse(store, manifest, pairs), "name no backend", "c-0001")


def test_T_U_results_07(tmp_path):
    """T-U-results-07 (FR-02.2): the lag, printed beside the headline."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    lag = next(line for line in text.splitlines() if line.startswith("**Lag.**"))
    assert "41 commits" in lag and "6.0 days" in lag and "`firtool-1.86.0`" in lag
    assert "contains a release" in lag
    assert "mechanically lowers the filing rate" in lag
    assert text.index("**Lag.**") < text.index("## 2. Secondary results")

    restate(store, lag_days=None)
    only(refuse(store, manifest, pairs), "stated beside the headline", "lag_days")


def test_T_U_results_08(tmp_path):
    """T-U-results-08 (FR-18.8): the cut-off date, and why there has to be one."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    cutoff = next(line for line in text.splitlines()
                  if line.startswith("**Confirmation cut-off.**"))
    assert "lags the budget window" in cutoff
    assert "after 2026-09-23 are not counted in the headline" in cutoff

    restate(store, confirmation_cutoff_date="")
    only(refuse(store, manifest, pairs), "confirmation cut-off date is mandatory")


def test_T_U_results_09(tmp_path):
    """T-U-results-09 (FR-10.1): both rates, and the unstable fingerprints."""
    store, manifest, pairs = campaign(tmp_path)
    rates = next(line for line in render(store, manifest, pairs).splitlines()
                 if line.startswith("**Dedup rates"))
    assert "Collision rate 1/11 = 0.0909" in rates
    assert "false-merge rate 1/11 = 0.0909" in rates
    assert "1 candidate carries an unstable fingerprint" in rates

    # The one refusal that stays: no set at all.
    only(refuse(store, manifest, None), "none was supplied")
    # A side the store has never fingerprinted is rendered, not refused.
    unknown = [dict(pair, a=dict(pair["a"], candidate_id="c-9999")) for pair in pairs]
    assert "Collision rate" in next(
        line for line in render(store, manifest, unknown).splitlines()
        if line.startswith("**Dedup rates"))


def test_T_U_results_10(tmp_path):
    """T-U-results-10 (FR-18.12): the divergences-observed list."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert "## 5. Divergences observed" in text
    row = tables(section(text, "5. Divergences observed"))[0]["rows"][0]
    assert row[0] == "`c-0004`" and row[1] == "mutation"
    assert row[3] == "diverge" and row[4] == "out_sum" and row[5] == "37"

    delete(store, "DELETE FROM report WHERE candidate_id = ?", ("c-0004",))
    only(refuse(store, manifest, pairs), "differential candidates have none", "c-0004")


def test_T_U_results_11(tmp_path):
    """T-U-results-11 (FR-05.8): the synthesis declaration, with all three facts."""
    store, manifest, pairs = campaign(tmp_path)
    declaration = next(line for line in render(store, manifest, pairs).splitlines()
                       if line.startswith("**The mutator synthesis"))
    assert "the one place the mutation arm sees bug reports" in declaration
    assert "`" + "1" * 64 + "`" in declaration
    assert "synthesised at 2026-09-17T11:00:00+00:00" in declaration
    assert "refreshed at 2026-09-19T00:00:00+00:00 (588 issues" in declaration
    assert "Mut4All's design" in declaration

    delete(store, "DELETE FROM ledger_entry WHERE stage = 'synthesis'")
    only(refuse(store, manifest, pairs), "names its input, its date",
         "carries the synthesis date")


def test_T_U_results_12(tmp_path):
    """T-U-results-12 (FR-14.5): tokens, money and CPU, and not the budget."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    observed = arm_tables(text)[-1]
    assert observed["seeded"] == ["94149", "14934", "8192", "0.1260", "12880", "5"]
    assert observed["mutation"] == ["0", "0", "0", "0.0000", "8129", "4"]
    assert observed["shared"] == ["188400", "9600", "0", "0.1770", "29100", "1"]
    assert "NOT the budget" in text
    assert "lower bound excluding stage 7" in text
    # W-23: the cached count, and the direction it moves the USD total in.
    assert "**Cached prompt tokens: 8192.**" in text
    assert "UPPER BOUND" in text and "registered list input rate" in text

    store.update("ledger_entry", {"entry_id": "l-0003"},
                 {"observed_json": json.dumps({"cpu_seconds": 90.0, "tokens_in": 1,
                                               "tokens_out": 1, "cost_usd": 0.1,
                                               "authorised_usd": None,
                                               "ceiling_usd": None,
                                               "billed_usd": None, "calls": None,
                                               "price_usd": 0.1}, sort_keys=True)})
    only(refuse(store, manifest, pairs), "do not carry", "l-0003")


def test_T_U_results_13(tmp_path):
    """T-U-results-13 (FR-18.10): both windows, the binding cap, the unspent balance."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    windows = arm_tables(text)[-2]
    assert windows["seeded"] == ["14400", "14400", "0", "its own window", "1.93"]
    assert windows["mutation"] == ["14400", "9000", "5400",
                                   "generated_inputs_per_day", "0.00"]
    assert "The campaign spent USD 2.10 in total" in text


def test_T_U_results_13a(tmp_path):
    """T-U-results-13a (W-18e): an arm that never started renders, and says why."""
    store, manifest, pairs = campaign(tmp_path)
    # Pilot 3's shape: the campaign's spend cap bit inside the first arm, so the
    # second one never opened a window at all.
    delete(store, "DELETE FROM ledger_entry WHERE scope = 'arm_window' AND arm = ?",
           ("mutation",))
    store.transaction([("UPDATE ledger_entry SET stop_reason = ? WHERE arm = ? "
                        "AND scope = 'arm_window'", ("campaign_spend_cap", "seeded"))])

    text = render(store, manifest, pairs)
    windows = arm_tables(text)[-2]
    assert windows["seeded"] == ["14400", "14400", "0", "campaign_spend_cap", "1.93"]
    assert windows["mutation"] == ["14400", "not started", "not started",
                                   "not started", "0.00"]
    assert ("mutation never opened a window: the seeded arm stopped on "
            "`campaign_spend_cap`" in text)
    assert "no comparison between the arms in this run" in text.lower()


def test_T_U_results_14(tmp_path):
    """T-U-results-14 (FR-18.11): a row that will not regenerate is marked."""
    store, manifest, pairs = campaign(tmp_path)
    regeneration = tables(section(render(store, manifest, pairs), "9. Regeneration"))
    assert [row[2] for row in regeneration[0]["rows"]] == ["yes"] * 4

    # The artefact p-0001 kept is a different capture from the one it was classified `assertion` on.
    build = store.query_one("SELECT stderr_path FROM build_result WHERE probe_id = ?",
                            ("p-0001",))
    Path(build["stderr_path"]).write_text(
        (FIXTURES_STDERR / "llvm_error.txt").read_text(encoding="utf-8"),
        encoding="utf-8")
    # And one candidate's image is no longer in the store at all.
    store.update("candidate", {"candidate_id": "c-0003"},
                 {"image_digest": "sha256:" + "e" * 64})
    text = render(store, manifest, pairs)
    marked = {row[0]: row[3] for row in tables(section(text, "9. Regeneration"))[0]["rows"]
              if row[2] == "**MARKED**"}
    assert set(marked) == {"`c-0001`", "`c-0003`"}
    assert marked["`c-0001`"] == "build_classification_differs:fatal_error:llvm_error"
    assert marked["`c-0003`"] == "image_unavailable"
    assert "2 rows regenerated and 2 marked" in text
    assert "not reported as a result" in text

    delete(store, "DELETE FROM probe_result WHERE probe_id = ?", ("p-0005",))
    only(refuse(store, manifest, pairs), "no probe_result to do either from", "c-0004")


def test_T_U_results_15(tmp_path):
    """T-U-results-15 (FR-18.7): zero is renderable, and is stated."""
    store, manifest, pairs = campaign(tmp_path)
    store.transaction([("UPDATE filing SET confirmed = 0, confirmed_at_utc = NULL, "
                        "confirmation_url = NULL", ())])
    text = render(store, manifest, pairs)

    headline = arm_tables(text)[0]
    assert [headline[arm][:2] for arm in ARMS] == [["0", "0"], ["0", "0"]]
    assert "The seeded arm confirmed 0 distinct bugs." in text
    assert "The mutation arm confirmed 0 distinct bugs." in text
    # The filings are still counted; it is the confirmations that are empty.
    assert headline["seeded"][2] == "2"
    for needle in ("Distinct confirmed bugs per arm", "The five secondaries per arm",
                   "**Lag.**", "**Confirmation cut-off.**", "false-merge rate",
                   "Divergences observed", "NOT the budget", "Both arm windows",
                   "regenerated from its recorded artefacts",
                   "The repair stage is unscreened"):
        assert needle in text, needle
    assert "n/a (0 filings)" in text, "gate precision over zero filings is not 0%"


def test_T_U_results_16(tmp_path):
    """T-U-results-16 (FR-18.9): no external yield is named anywhere."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    for name in EXTERNAL_YIELDS:
        assert name.lower() not in text.lower(), name
    assert EXAMPLE.exists()
    for name in EXTERNAL_YIELDS:
        assert name.lower() not in EXAMPLE.read_text(encoding="utf-8").lower(), name


def test_T_U_results_17(tmp_path):
    """T-U-results-17 (FR-06.6): every sum, and the split row."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    taxonomy = section(text, "3. Failure taxonomy")

    mapping, buckets, phases, outcomes, failures = tables(taxonomy)
    # The mapping printed is `gate.TAXONOMY` itself.
    printed = {(row[0], row[1]): row[2] for row in mapping["rows"]}
    assert printed.pop(("none", "passed all four")) == "new_bug"
    assert printed == {(str(question), value): bucket
                       for (question, value), bucket in TAXONOMY.items()}
    assert set(printed.values()) <= set(BUCKETS)

    counts = {row[0]: int(row[1]) for row in buckets["rows"]}
    assert set(counts) == set(BUCKETS) | {"no gate decision"}
    assert counts["duplicate"] == 1 and counts["new_bug"] == 2
    assert sum(counts.values()) == 3
    assert "Sum check: 3 bucketed = 3 candidates reaching the gate." in taxonomy
    assert "1 differential candidate excluded by construction" in taxonomy

    assert sum(int(row[1]) for row in phases["rows"]) == 2
    assert "Sum check: 2 = 2 repair attempts." in taxonomy

    split = {row[0]: [int(cell) for cell in row[1:]] for row in outcomes["rows"]}
    assert split["parse_error:tool_rejected_input"] == [0, 0]
    assert split["parse_error:tool_rejected_argv"] == [0, 1]
    stored = store.query("SELECT arm, build_status FROM probe_result "
                         "WHERE build_status = 'parse_error'")
    assert (sum(split["parse_error:tool_rejected_input"])
            + sum(split["parse_error:tool_rejected_argv"])) == len(stored)

    # D-3 (pilot 5): the turns that produced nothing, counted by kind.
    assert failures["header"] == ["arm", "stage", "kind", "turns",
                                  "first detail"]
    counted = {(row[0], row[2]): int(row[3]) for row in failures["rows"]}
    assert counted == {("mutation", "`stale_at_build`"): 1,
                       ("seeded", "`prompt_contract:no_block`"): 2}
    assert sum(counted.values()) == len(store.query("SELECT 1 FROM turn_failure"))
    assert "3 turns produced no probing input at all." in taxonomy
    # The detail is the stored one, cut at the cap and never beyond it.
    for row in failures["rows"]:
        assert len(row[4]) <= TURN_FAILURE_DETAIL_CAP
    assert "PromptContractError: no_block" in taxonomy


def test_the_turn_failure_table_renders_for_a_store_with_no_rows(tmp_path):
    """D-3 (pilot 5): a run in which every turn answered still renders section 3."""
    store, manifest, pairs = campaign(tmp_path)
    store.transaction([("DELETE FROM turn_failure", ())])
    taxonomy = section(render(store, manifest, pairs), "3. Failure taxonomy")

    failures = tables(taxonomy)[-1]
    assert failures["rows"] == [["none", "", "", "0", ""]]
    assert "0 turns produced no probing input at all." in taxonomy


def test_a_never_dispatched_turn_is_refused_and_not_unpriced(tmp_path):
    """D-9 (pilot 8): the three rows of a turn that never happened, counted apart."""
    store, manifest, pairs = campaign(tmp_path)
    before = _facts(store, manifest, pairs, 5)
    observed = section(render(store, manifest, pairs), "7. Observed, and not the budget")
    assert "**Unpriced turns: 1.**" in observed, "stage 7 is dispatched and unpriced"
    assert "**Turns refused before dispatch: 0.**" in observed

    # Pilot 8's shape: a stage 6 the duplicate verdict skipped, twice, and the
    # mutation arm's `stale_at_build`. Metered, and every money field null.
    store.insert_many("ledger_entry", [
        {"entry_id": entry_id, "run_manifest_id": _RUN, "arm": arm, "scope": "stage",
         "stage": stage, "unit": "wall_clock_seconds", "amount": 0.19,
         "metered": 1,
         "observed_json": json.dumps(dict.fromkeys(OBSERVED_KEYS), sort_keys=True),
         "timestamp_utc": "2026-09-19T03:00:00+00:00", "stop_reason": None}
        for entry_id, arm, stage in (("l-0014", "seeded", "stage_6"),
                                     ("l-0015", "seeded", "stage_6"),
                                     ("l-0016", "mutation", "stage_2"))])

    facts = _facts(store, manifest, pairs, 5)
    assert facts["refused_turns"] == 3 and facts["unpriced_turns"] == 1
    text = render(store, manifest, pairs)
    assert "**Turns refused before dispatch: 3.**" in text
    assert "**Unpriced turns: 1.**" in text, "a refused turn is not an unpriced one"
    assert all(facts["observed"][arm]["cost_usd"] == before["observed"][arm]["cost_usd"]
               for arm in ARMS), "a turn that never happened moved no money"


def test_T_U_results_18(tmp_path):
    """T-U-results-18 (FR-18.1): `arm` picks the row and never the computation."""
    store, manifest, pairs = campaign(tmp_path)
    before = arm_tables(render(store, manifest, pairs))

    swap = ("UPDATE {} SET arm = CASE arm WHEN 'seeded' THEN 'mutation' "
            "WHEN 'mutation' THEN 'seeded' ELSE arm END")
    store.transaction([(swap.format(table), ())
                       for table in ("probe", "probe_result", "candidate",
                                     "ledger_entry", "turn_failure")])
    after = arm_tables(render(store, manifest, pairs))

    assert len(before) == len(after) == 6
    for original, swapped in zip(before, after):
        assert swapped["seeded"] == original["mutation"]
        assert swapped["mutation"] == original["seeded"]
        assert set(swapped) == set(original), "no arm appeared or vanished"
    assert "shared" in after[-1], "`shared` is a ledger arm and is not swapped"


def test_T_U_results_19(tmp_path):
    """T-U-results-19 (FR-08.10): the list is exactly the differentials."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    listed = tables(section(text, "5. Divergences observed"))[0]["rows"]
    reports = store.query("SELECT candidate_id FROM report WHERE template = ?",
                          ("differential",))
    assert len(listed) == len(reports) == 1
    assert "1 divergence observed." in text
    for row in listed:
        candidate_id = row[0].strip("`")
        assert candidate_id in {r["candidate_id"] for r in reports}
        assert store.query_one("SELECT 1 FROM gate_decision WHERE candidate_id = ?",
                               (candidate_id,)) is None
        assert store.query_one("SELECT 1 FROM filing WHERE candidate_id = ?",
                               (candidate_id,)) is None


def test_T_U_results_20(tmp_path):
    """T-U-results-20 (FR-18.2): the two arms' seed sets are identical in a mode."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert "The seeded arm probed 2 seeds and the mutation arm 2" in text
    assert "the two sets are identical" in text

    probed = {arm: {row["seed_sha"] for row in store.query(
        "SELECT seed_sha FROM probe WHERE arm = ?", (arm,))} for arm in ARMS}
    assert probed["seeded"] == probed["mutation"]
    assert store.query_one("SELECT seed_set FROM run")["seed_set"] == manifest.seed_set


def test_T_U_results_21(tmp_path):
    """T-U-results-21: fourteen checks, in one order, and every failure collected."""
    assert len(_REFUSALS) == 14
    assert tuple(check.__name__ for check in _REFUSALS) == REFUSAL_NAMES

    store, manifest, pairs = campaign(tmp_path)
    delete(store, "DELETE FROM seed WHERE run_manifest_id = ?", (_RUN,))
    delete(store, "DELETE FROM dedup_verdict WHERE candidate_id = ?", ("c-0002",))
    delete(store, "DELETE FROM report WHERE candidate_id = ?", ("c-0004",))
    missing = refuse(store, manifest, pairs)

    assert len(missing) == 3, missing
    assert any("the store holds none for this run" in m for m in missing)
    assert any("candidates after dedup cannot be counted" in m for m in missing)
    assert any("differential candidates have none" in m for m in missing)
    with pytest.raises(ResultsIncomplete) as raised:
        render(store, manifest, pairs)
    assert str(raised.value).startswith("the results artefact refuses to render;")


def test_T_U_results_22(tmp_path):
    """The committed `fixtures/results/example.md` is this store's own render."""
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert text == EXAMPLE.read_text(encoding="utf-8"), (
        "fixtures/results/example.md is stale; re-render it with "
        "`python -m circt_bug_loop.tests.fixtures.results.make_store <dir>` "
        "and render_results over the result")
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert str(tmp_path) not in text, "the artefact carries an absolute path"
