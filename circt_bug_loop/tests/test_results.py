"""`results.py` (B11): the fourteen refusals, the headline, and the regeneration check.

`04-Test-Plan.md` §1.19's twenty-one `T-U-results-*` rows, plus one this
implementation added: the committed `fixtures/results/example.md` is a render of
the fixture store and is compared against a fresh one, so a change to either the
renderer or the fixture generator that nobody meant shows up as a diff of the
artefact a reader will actually read.

All tier 0. `render_results` is a pure function of `loop.db` and of the artefact
tree it points at: nothing here opens a tool, a socket or a model, and every
store is regenerated into `tmp_path` by `fixtures/results/make_store.py` rather
than committed, §13's `store_full.db` being the pilot's own database and the
pilot being W-18. The three variants §13 names are one edit each on that store,
which is exactly how §13 describes them, and each refusal test makes the one
edit that removes the one element the check under test demands.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from circt_bug_loop.gate import TAXONOMY
from circt_bug_loop.results import (ARMS, BUCKETS, _facts, _REFUSALS,
                                    _require_qualifiers, ResultsIncomplete,
                                    render_results)
from circt_bug_loop.tests.conftest import call_node
from circt_bug_loop.tests.fixtures.results import make_store

pytestmark = pytest.mark.t0

#: The render committed beside the generator, which `T-U-results-22` holds this
#: module to. It is path-free by construction: no absolute path appears in the
#: artefact, so a render from a temporary directory compares byte for byte.
EXAMPLE = Path(__file__).resolve().parent / "fixtures" / "results" / "example.md"

#: The recorded tool stderr the mini-campaign is built from, which is also where
#: `T-U-results-14` takes the capture it swaps in to break a regeneration.
FIXTURES_STDERR = Path(__file__).resolve().parent / "fixtures" / "stderr"

#: `03-LLD.md` §14.4's table, in §3.11's order. Hard-coded rather than parsed out
#: of the design file: `03-LLD.md` §1.4 puts this package at two different depths
#: in two trees, so no test here walks past its own directory.
REFUSAL_NAMES = (
    "_require_headline", "_require_secondaries", "_require_validation_table",
    "_require_qualifiers", "_require_contamination", "_require_disclosures",
    "_require_lag", "_require_cutoff", "_require_dedup_rates",
    "_require_divergences", "_require_mutator_declaration",
    "_require_observed_heading", "_require_both_windows",
    "_require_regeneration_marks")

#: FR-18.9's four external yields. The artefact names none of them, so no
#: sentence in it can compare this loop's count to one.
EXTERNAL_YIELDS = ("FLEX", "ISSTA", "Nüwa", "Nuwa", "DESIL")

_RUN = make_store.RUN


# ---------------------------------------------------------------------------
# The mini-campaign, and the one edit each refusal needs
# ---------------------------------------------------------------------------


def campaign(tmp_path, name: str = "full"):
    """Regenerate the fixture mini-campaign under *tmp_path*/*name*.

    Returns the `(store, manifest, labelled_pairs)` triple `render` takes, which
    is what `make_store.build` returns.
    """
    return make_store.build(Path(tmp_path) / name)


def render(store, manifest, pairs) -> str:
    """Call B11 the way the driver does, through `conftest.call_node` (§0.4).

    The node returns `{"rendered", "counters"}` since the join (W-17, errata row
    22); what every test below reads is the artefact, so the helper unwraps it
    and asserts the block here, at every call site.
    """
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
    """Rewrite the stored `RunManifest` with *overrides* applied.

    Three of the fourteen elements are read off the manifest the run recorded
    rather than off the one the caller passes, because the artefact reports the
    campaign that ran and not the campaign that was asked for.
    """
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


# ---------------------------------------------------------------------------
# The fourteen refusals, one test each, in _REFUSALS' order
# ---------------------------------------------------------------------------


def test_T_U_results_01(tmp_path):
    """T-U-results-01 (FR-18.3): the headline, per arm, one bug per fingerprint.

    Counted from `filing` rows carrying maintainer evidence with a URL and from
    nothing else, and two confirmed filings sharing a primary fingerprint count
    once. The refusal is a confirmed filing whose candidate carries no
    fingerprint value, which leaves the count undefined rather than low.
    """
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
    """T-U-results-02 (FR-18.4, FR-12.3): the five secondaries, and the overwrites.

    All five per arm come out of the store alone, and beside them the count of
    repair attempts whose reproduce turn overwrote the pre-written `repro.sh`,
    which is how "confirms rather than invents" is reported per attempt. The
    refusal is a candidate with no dedup verdict: "after dedup" has no value.
    """
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
    """T-U-results-03 (FR-18.5): validation is a separate table, feeding nothing.

    The two seeds' filings total two and the headline totals one distinct
    confirmed bug, so the validation rows are demonstrably not summed into the
    headline; and the table says so in its own words. The refusal is a run with
    no seed rows, over which the table cannot be taken at all.
    """
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
    """T-U-results-04 (FR-18.2, ADR-D-07): the mode and the seed set, on every table.

    Every table in the artefact carries both, counted rather than sampled: the
    number of qualified captions equals the number of tables. The refusal is a
    store and a manifest that disagree about either, after which no table can be
    qualified at all; and a table that loses its qualifier is named by its line.
    """
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
    """T-U-results-05 (FR-15.2): contamination counted apart, headline both ways.

    The one contaminated candidate is counted in its own column, and the
    headline prints the distinct count both with it and without it: one and
    zero, which is the whole point of printing both. The refusal is a candidate
    the screen never reached, whose lower bound is neither of the two the screen
    can leave behind.
    """
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
    """T-U-results-06 (FR-15.3, FR-15.4): both disclosure sentences, and the backend.

    The screen's incompleteness and the repair stage being unscreened are two
    separate sentences and both are mandatory; the second names the backend the
    attempts ran on, so "unscreened" has something to be true of. The refusal is
    a repair attempt naming no backend.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert "**The contamination screen is incomplete.**" in text
    assert "**The repair stage is unscreened.**" in text
    assert "2 repair attempts on vertex" in text

    store.update("repair", {"candidate_id": "c-0001"}, {"backend": "  "})
    only(refuse(store, manifest, pairs), "name no backend", "c-0001")


def test_T_U_results_07(tmp_path):
    """T-U-results-07 (ADR-D-10, FR-02.2): the lag, printed beside the headline.

    The commits, the days, the pin tag and whether the current window holds a
    release, followed by the direction of the bias: a longer lag lowers the
    filing rate mechanically. The refusal is a stored manifest missing any one
    of the four, since a partial lag disclosure is a misleading one.
    """
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
    """T-U-results-08 (FR-18.8): the cut-off date, and why there has to be one.

    The artefact states that maintainer confirmation lags the budget window and
    names the date after which a confirmation is not counted. The refusal is a
    stored manifest with no cut-off, which would leave the headline defined over
    an open-ended future.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    cutoff = next(line for line in text.splitlines()
                  if line.startswith("**Confirmation cut-off.**"))
    assert "lags the budget window" in cutoff
    assert "after 2026-09-23 are not counted in the headline" in cutoff

    restate(store, confirmation_cutoff_date="")
    only(refuse(store, manifest, pairs), "confirmation cut-off date is mandatory")


def test_T_U_results_09(tmp_path):
    """T-U-results-09 (FR-10.1, FR-10.2): both rates, and the unstable fingerprints.

    The collision and false-merge rates are printed beside the headline they
    qualify, each as its own numerator and denominator so a zero denominator is
    visible, and beside them the count of candidates whose fingerprint the gate
    re-run found unstable, which qualifies the headline exactly as a collision
    does. The refusal is the labelled pair set not being supplied at all: the
    rates are a measurement of the project, not a row of the campaign.

    **W-12: the set is external, and the store is not asked about it.** The
    pairs are `data/labelled_pairs.json`'s own recorded failures, labelled by
    hand before any fingerprint was computed, and the renderer fingerprints
    them from the file. The numbers below are therefore the project's measured
    rates and are the same for every run; a set whose sides the campaign's store
    has never heard of renders, which is what it must do, a campaign that
    confirms nothing having no such candidate. Before this the renderer demanded
    a store fingerprint per side and refused at the end of EVERY run, which is
    the one refusal `T-S-regen-01` recorded.
    """
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
    """T-U-results-10 (FR-18.12): the divergences-observed list.

    Headed exactly that, one row per informational differential report, with the
    verdict and the first divergent signal and cycle the driver recorded. The
    refusal is a differential candidate with no report: it would then be
    counted nowhere, being excluded from the candidate count by construction.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert "## 5. Divergences observed" in text
    row = tables(section(text, "5. Divergences observed"))[0]["rows"][0]
    assert row[0] == "`c-0004`" and row[1] == "mutation"
    assert row[3] == "diverge" and row[4] == "out_sum" and row[5] == "37"

    delete(store, "DELETE FROM report WHERE candidate_id = ?", ("c-0004",))
    only(refuse(store, manifest, pairs), "differential candidates have none", "c-0004")


def test_T_U_results_11(tmp_path):
    """T-U-results-11 (FR-05.8): the synthesis declaration, with all three facts.

    The one place the mutation arm sees bug reports, naming the synthesis input,
    the synthesis date and the frozen set's SHA, and saying that this is
    Mut4All's design rather than a leak. The refusal is the `shared` ledger
    entry the synthesis is charged to being absent, which is where the date
    comes from.
    """
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
    """T-U-results-12 (FR-14.5, FR-14.6): tokens, money and CPU, and not the budget.

    Under a heading that says they are not the budget, per arm and for the
    shared stages, summed from the ledger's observed blocks; the entries whose
    token counts are null are counted rather than read as zero, and the USD
    total is declared a lower bound excluding stage 7. The refusal is an
    observed block carrying a key §2.7 does not declare, which cannot be summed.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    observed = arm_tables(text)[-1]
    assert observed["seeded"] == ["94149", "14934", "0.1260", "12880", "5"]
    assert observed["mutation"] == ["0", "0", "0.0000", "8129", "4"]
    assert observed["shared"] == ["188400", "9600", "0.1770", "29100", "1"]
    assert "NOT the budget" in text
    assert "lower bound excluding stage 7" in text

    store.update("ledger_entry", {"entry_id": "l-0003"},
                 {"observed_json": json.dumps({"cpu_seconds": 90.0, "tokens_in": 1,
                                               "tokens_out": 1, "cost_usd": 0.1,
                                               "price_usd": 0.1}, sort_keys=True)})
    only(refuse(store, manifest, pairs), "do not carry", "l-0003")


def test_T_U_results_13(tmp_path):
    """T-U-results-13 (FR-18.10): both windows, the binding cap, the unspent balance.

    Both arms' elapsed wall clock against the same window, and for the arm a
    safety cap stopped early, which cap bound and how much of its window went
    unused; beside them the campaign's spend in USD over both arms and the
    shared stages. The refusal is an arm with no `arm_window` entry, which is
    the one arm whose window could then not be printed.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    windows = arm_tables(text)[-2]
    assert windows["seeded"] == ["14400", "14400", "0", "its own window", "0.13"]
    assert windows["mutation"] == ["14400", "9000", "5400",
                                   "generated_inputs_per_day", "0.00"]
    assert "The campaign spent USD 0.30 in total" in text

    delete(store, "DELETE FROM ledger_entry WHERE scope = 'arm_window' AND arm = ?",
           ("mutation",))
    only(refuse(store, manifest, pairs), "both arms' windows", "['mutation']")


def test_T_U_results_14(tmp_path):
    """T-U-results-14 (FR-18.11): a row that will not regenerate is marked.

    The deterministic head-side stages are re-run from the stored inputs, over
    every row and not a sample: `classify_build` over the recorded stderr and
    `decide` over the recorded gate answers. A row whose re-run disagrees, or
    whose image is gone, is marked and is not reported as a result. The refusal
    is a candidate with no `probe_result`, which can be neither regenerated nor
    marked.
    """
    store, manifest, pairs = campaign(tmp_path)
    regeneration = tables(section(render(store, manifest, pairs), "9. Regeneration"))
    assert [row[2] for row in regeneration[0]["rows"]] == ["yes"] * 4

    # The artefact p-0001 kept is a different capture from the one it was
    # classified `assertion` on, so the re-run disagrees with the record.
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


# ---------------------------------------------------------------------------
# The seven properties asserted over the output
# ---------------------------------------------------------------------------


def test_T_U_results_15(tmp_path):
    """T-U-results-15 (FR-18.7): zero is renderable, and is stated.

    With no confirmed filing at all the render succeeds, states the zero for
    both arms, and no refusal fires for want of a confirmed bug: every other
    mandatory element is still there. Zero is a result, not a missing element.
    """
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
    """T-U-results-16 (FR-18.9): no external yield is named anywhere.

    A name search over the rendered text, which is the check `03-LLD.md` §14.4
    prescribes: the module names none of the four, so no sentence in the
    artefact can compare this loop's count to one.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    for name in EXTERNAL_YIELDS:
        assert name.lower() not in text.lower(), name
    assert EXAMPLE.exists()
    for name in EXTERNAL_YIELDS:
        assert name.lower() not in EXAMPLE.read_text(encoding="utf-8").lower(), name


def test_T_U_results_17(tmp_path):
    """T-U-results-17 (FR-06.6, FR-18.6, FR-13.14): every sum, and the split row.

    The six buckets plus the ungated row sum to the candidates reaching the
    gate; the repair phases sum to the repair attempts; `differential`
    candidates are in neither denominator. `parse_error` is two rows keyed by
    the stopping reason, and they sum to the `parse_error` total.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    taxonomy = section(text, "3. Failure taxonomy")

    mapping, buckets, phases, outcomes = tables(taxonomy)
    # The mapping printed is `gate.TAXONOMY` itself, plus the row for a
    # candidate that answered all four, and it invents no seventh bucket.
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


def test_T_U_results_18(tmp_path):
    """T-U-results-18 (FR-18.1): `arm` picks the row and never the computation.

    This module is exempt by name from `T-U-layout-02`'s walk, and the exemption
    is used for the results table and nothing else. The check is behavioural
    rather than syntactic: relabel every row of the store with the other arm and
    re-render, and every arm-keyed table comes back exactly transposed. If any
    branch on `arm` changed what was computed rather than where it was printed,
    some cell would differ.
    """
    store, manifest, pairs = campaign(tmp_path)
    before = arm_tables(render(store, manifest, pairs))

    swap = ("UPDATE {} SET arm = CASE arm WHEN 'seeded' THEN 'mutation' "
            "WHEN 'mutation' THEN 'seeded' ELSE arm END")
    store.transaction([(swap.format(table), ())
                       for table in ("probe", "probe_result", "candidate",
                                     "ledger_entry")])
    after = arm_tables(render(store, manifest, pairs))

    assert len(before) == len(after) == 5
    for original, swapped in zip(before, after):
        assert swapped["seeded"] == original["mutation"]
        assert swapped["mutation"] == original["seeded"]
        assert set(swapped) == set(original), "no arm appeared or vanished"
    assert "shared" in after[-1], "`shared` is a ledger arm and is not swapped"


def test_T_U_results_19(tmp_path):
    """T-U-results-19 (FR-08.10, FR-18.12): the list is exactly the differentials.

    Its length equals the number of `differential` reports in the store, and no
    entry in it carries a gate decision or a filing: a divergence is
    informational, enters no gate and is never filed.
    """
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
    """T-U-results-20 (FR-18.2): the two arms' seed sets are identical in a mode.

    Read off the probes the campaign actually dispatched rather than off the
    seed table, because what FR-18.2 constrains is what each arm was given.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert "The seeded arm probed 2 seeds and the mutation arm 2" in text
    assert "the two sets are identical" in text

    probed = {arm: {row["seed_sha"] for row in store.query(
        "SELECT seed_sha FROM probe WHERE arm = ?", (arm,))} for arm in ARMS}
    assert probed["seeded"] == probed["mutation"]
    assert store.query_one("SELECT seed_set FROM run")["seed_set"] == manifest.seed_set


def test_T_U_results_21(tmp_path):
    """T-U-results-21: fourteen checks, in one order, and every failure collected.

    `len(_REFUSALS) == 14`, the names are `03-LLD.md` §14.4's table rows in
    §3.11's order, and one render names every missing element rather than the
    first: a store missing three reports three.
    """
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
    """The committed `fixtures/results/example.md` is this store's own render.

    Added by the implementation, not by `04-Test-Plan.md` §1.19. The artefact is
    the thing a reader reads, and the generator and the renderer are two files
    that can drift apart quietly; comparing them byte for byte is what makes a
    drift a diff. The render carries no absolute path, so a store built in a
    temporary directory renders the committed text exactly.
    """
    store, manifest, pairs = campaign(tmp_path)
    text = render(store, manifest, pairs)
    assert text == EXAMPLE.read_text(encoding="utf-8"), (
        "fixtures/results/example.md is stale; re-render it with "
        "`python -m circt_bug_loop.tests.fixtures.results.make_store <dir>` "
        "and render_results over the result")
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert str(tmp_path) not in text, "the artefact carries an absolute path"
