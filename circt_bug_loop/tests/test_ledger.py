"""`ledger.py`: the three arms, the two scopes, the stop rule."""
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import budget as budget_module
from circt_bug_loop import ledger as ledger_module
from circt_bug_loop import store
from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import call_node
from circt_bug_loop.tests.test_store import open_store, seed_rows

pytestmark = pytest.mark.t0

#: `fixtures/ledger/`, the recorded rows of `04-Test-Plan.md` §13.
LEDGER_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ledger"

_RUN = "run-01"
_DAY = "2026-09-20"
_OBSERVED_KEYS = ("cpu_seconds", "tokens_in", "tokens_out", "cost_usd",
                  "authorised_usd", "ceiling_usd", "billed_usd", "calls")


def budget(**overrides) -> schema.BudgetFile:
    """§9.5's committed file as a BudgetFile, with any key overridden."""
    document = yaml.safe_load(Path(budget_module.BUDGET_YAML).read_text(encoding="utf-8"))
    document.update(overrides)
    parsed = schema.BudgetFile(budget_file_sha="0" * 40, **document)
    schema.validate(parsed)
    return parsed


def observed(cpu_seconds=1.0, tokens_in=None, tokens_out=None, **money) -> dict:
    """An `observed` block carrying exactly the eight keys §2.7 freezes."""
    block = {"cpu_seconds": cpu_seconds, "tokens_in": tokens_in,
             "tokens_out": tokens_out, "cost_usd": None,
             "authorised_usd": None, "ceiling_usd": None,
             "billed_usd": None, "calls": None}
    block.update(money)
    return block


def entry(entry_id: str, *, arm="seeded", scope="stage", stage="stage_3",
          amount=1.0, metered=True, at=f"{_DAY}T01:00:00+00:00",
          stop=None, **kwargs) -> schema.LedgerEntry:
    """One LedgerEntry, defaulted to a metered stage-3 charge on the seeded arm."""
    block = kwargs.pop("observed", None)
    return schema.LedgerEntry(
        entry_id=entry_id, run_manifest_id=_RUN, arm=arm, scope=scope, stage=stage,
        unit="wall_clock_seconds", amount=amount, metered=metered,
        observed=block if block is not None else observed(**kwargs),
        timestamp_utc=at, stop_reason=stop)


def accrue_all(db_path: str, entries, funds=None) -> None:
    """Append every entry of *entries* against *funds* (§9.5's file by default)."""
    for one in entries:
        call_node(ledger_module.accrue, one, db_path, funds or budget())


def test_T_U_ledger_01(tmp_path: Path):
    """T-U-ledger-01 (FR-14.4): `arm` takes exactly the three values."""
    db_path = str(tmp_path / "loop.db")
    loop = open_store(tmp_path)
    seed_rows(loop)
    for arm in ("seeded", "mutation", "shared"):
        call_node(ledger_module.accrue, entry(f"e-{arm}", arm=arm), db_path, budget())
    assert len(loop.query("SELECT 1 FROM ledger_entry")) == 3

    with pytest.raises(schema.ContractError) as caught:
        call_node(ledger_module.accrue, entry("e-4", arm="both"), db_path, budget())
    assert caught.value.code == "E004_BAD_ENUM"

    with pytest.raises(sqlite3.IntegrityError):
        loop.insert("ledger_entry", {
            "entry_id": "e-5", "run_manifest_id": _RUN, "arm": "both",
            "scope": "stage", "stage": "stage_3", "unit": "wall_clock_seconds",
            "amount": 1.0, "metered": 1, "observed_json": "{}",
            "timestamp_utc": f"{_DAY}T01:00:00+00:00", "stop_reason": None})


def test_T_U_ledger_02(tmp_path: Path):
    """T-U-ledger-02 (FR-14.4): `scope` takes exactly `arm_window` or `stage`."""
    db_path = str(tmp_path / "loop.db")
    loop = open_store(tmp_path)
    seed_rows(loop)
    call_node(ledger_module.accrue, entry("e-1", scope="arm_window", stage="stage_3",
                               amount=14400.0), db_path, budget())
    call_node(ledger_module.accrue, entry("e-2", scope="stage"), db_path, budget())
    assert sorted(r["scope"] for r in loop.query("SELECT scope FROM ledger_entry")) \
        == ["arm_window", "stage"]

    with pytest.raises(schema.ContractError) as caught:
        call_node(ledger_module.accrue, entry("e-3", scope="campaign"), db_path, budget())
    assert caught.value.code == "E004_BAD_ENUM"


def test_T_U_ledger_03(tmp_path: Path):
    """T-U-ledger-03 (FR-14.4): one arm_window entry per arm per run."""
    db_path = str(tmp_path / "loop.db")
    loop = open_store(tmp_path)
    seed_rows(loop)
    accrue_all(db_path, [
        entry("w-seeded", arm="seeded", scope="arm_window", amount=14400.0),
        entry("w-mutation", arm="mutation", scope="arm_window", amount=14400.0),
        entry("s-1", arm="seeded", amount=7.0)])

    with pytest.raises(schema.ContractError) as caught:
        call_node(ledger_module.accrue, entry("w-seeded-2", scope="arm_window", amount=1.0),
                             db_path, budget())
    assert caught.value.code == "E005_CONDITIONAL_REQUIRED"
    assert "w-seeded" in str(caught.value)

    aggregated = ledger_module.aggregate(_RUN, db_path, today=_DAY)
    assert aggregated.per_arm_window == {"seeded": 14400.0, "mutation": 14400.0}
    assert aggregated.per_arm_stage["seeded"] == {"stage_3": 7.0}
    assert loop.query_one("SELECT COUNT(*) c FROM ledger_entry "
                          "WHERE scope = 'arm_window'")["c"] == 2


def test_T_U_ledger_04(tmp_path: Path):
    """T-U-ledger-04 (FR-14.4): per-arm sums exclude `shared`, which is reported beside them."""
    db_path = str(tmp_path / "loop.db")
    seed_rows(open_store(tmp_path))
    shared_stages = ("image", "mirror", "corpus", "pin", "synthesis")
    accrue_all(db_path, [
        entry("w-s", arm="seeded", scope="arm_window", amount=100.0),
        entry("w-m", arm="mutation", scope="arm_window", amount=100.0),
        entry("a-1", arm="seeded", amount=10.0),
        entry("a-2", arm="mutation", amount=20.0),
    ] + [entry(f"sh-{i}", arm="shared", stage=name, amount=5.0 * (i + 1))
         for i, name in enumerate(shared_stages)])

    aggregated = ledger_module.aggregate(_RUN, db_path, today=_DAY)
    assert set(aggregated.shared_stage) == set(shared_stages)
    assert sum(aggregated.shared_stage.values()) == 5.0 + 10.0 + 15.0 + 20.0 + 25.0
    assert aggregated.per_arm_stage == {"seeded": {"stage_3": 10.0},
                                        "mutation": {"stage_3": 20.0}}
    assert "shared" not in aggregated.per_arm_window
    assert "shared" not in aggregated.per_arm_stage


def test_T_U_ledger_05(tmp_path: Path):
    """T-U-ledger-05 (FR-14.4): per-stage occupancy may exceed the window."""
    db_path = str(tmp_path / "loop.db")
    seed_rows(open_store(tmp_path))
    funds = budget(arm_window_seconds=100.0)
    accrue_all(db_path, [
        entry("w-s", scope="arm_window", amount=100.0),
        entry("o-1", stage="stage_3", amount=90.0),
        entry("o-2", stage="stage_4", amount=90.0),
        entry("o-3", stage="stage_5", amount=90.0)], funds)

    aggregated = ledger_module.aggregate(_RUN, db_path, today=_DAY)
    occupancy = sum(aggregated.per_arm_stage["seeded"].values())
    assert occupancy == 270.0 > aggregated.per_arm_window["seeded"] == 100.0
    # the observation does not stop the arm; the window does, and it is reached
    assert ledger_module.stop_reason(aggregated, "seeded", funds) == "arm_window"
    assert ledger_module.stop_reason(aggregated, "mutation", funds) is None


def test_T_U_ledger_06(tmp_path: Path):
    """T-U-ledger-06 (FR-14.4): the window, the binding cap, or None."""
    db_path = str(tmp_path / "loop.db")
    seed_rows(open_store(tmp_path))
    funds = budget(generated_inputs_per_day=5)

    # One second short of the committed window, whatever the committed window is.
    accrue_all(db_path, [entry("w-s", scope="arm_window",
                               amount=funds.arm_window_seconds - 1.0)], funds)
    aggregated = ledger_module.aggregate(_RUN, db_path, today=_DAY)
    assert ledger_module.stop_reason(aggregated, "seeded", funds) is None

    accrue_all(db_path, [entry(f"i-{i}", stage="stage_3", amount=1.0)
                         for i in range(5)], funds)
    aggregated = ledger_module.aggregate(_RUN, db_path, today=_DAY)
    assert aggregated.inputs_today == {"seeded": 5, "mutation": 0}
    assert ledger_module.stop_reason(aggregated, "seeded", funds) == "generated_inputs_per_day"
    assert ledger_module.stop_reason(aggregated, "mutation", funds) is None

    # a different UTC day does not count against today's cap
    assert ledger_module.aggregate(_RUN, db_path, today="2026-09-21").inputs_today \
        == {"seeded": 0, "mutation": 0}

    window = ledger_module.aggregate(_RUN, db_path, today="2026-09-21")
    window.per_arm_window["seeded"] = 14400.0
    assert ledger_module.stop_reason(window, "seeded", funds) == "arm_window"

    with pytest.raises(schema.ContractError) as caught:
        ledger_module.stop_reason(aggregated, "shared", funds)
    assert caught.value.code == "E004_BAD_ENUM"


def test_T_U_ledger_07(tmp_path: Path):
    """T-U-ledger-07 (FR-14.4): append-only; a repeated entry_id is detected."""
    db_path = str(tmp_path / "loop.db")
    loop = open_store(tmp_path)
    seed_rows(loop)
    accrue_all(db_path, [entry("e-1", amount=3.0)])
    with pytest.raises(sqlite3.IntegrityError):
        accrue_all(db_path, [entry("e-1", amount=99.0)])
    rows = loop.query("SELECT amount FROM ledger_entry")
    assert [r["amount"] for r in rows] == [3.0], "the double charge was not absorbed"


def test_T_U_ledger_08(tmp_path: Path):
    """T-U-ledger-08 (FR-14.6): `observed`'s four keys, and stage 7's disagreement."""
    db_path = str(tmp_path / "loop.db")
    loop = open_store(tmp_path)
    seed_rows(loop)
    funds = budget()

    vertex = entry("v-1", stage="stage_2", tokens_in=1100, tokens_out=700)
    call_node(ledger_module.accrue, vertex, db_path, funds)
    assert tuple(sorted(vertex.observed)) == tuple(sorted(_OBSERVED_KEYS))
    assert vertex.observed["cost_usd"] == ledger_module.price(1100, 700, funds)
    assert vertex.metered is True

    fallback = entry("c-1", stage="stage_2", metered=False)
    call_node(ledger_module.accrue, fallback, db_path, funds)
    assert fallback.observed["tokens_in"] is None
    assert fallback.observed["cost_usd"] is None and fallback.metered is False

    stage_7 = entry("r-1", stage="stage_7", metered=True)
    call_node(ledger_module.accrue, stage_7, db_path, funds)
    assert stage_7.metered is True and stage_7.observed["tokens_in"] is None
    assert stage_7.observed["cost_usd"] is None, "a null is an absence, not a zero"

    stages = schema._DICT_KEYS[("RunManifest", "stages_metered")]
    assert "stage_7" in stages, "FR-14.8 declares it, metered or not"

    written = {r["entry_id"]: json.loads(r["observed_json"])
               for r in loop.query("SELECT entry_id, observed_json FROM ledger_entry")}
    assert set(written["v-1"]) == set(_OBSERVED_KEYS)
    assert written["r-1"]["cost_usd"] is None

    # the committed rows of 13's `fixtures/ledger/` row.
    found = sorted(LEDGER_FIXTURES.rglob("*.json"))
    assert [path.parent.name for path in found].count("vertex") == 4
    assert [path.parent.name for path in found].count("claude") == 2
    for path in found:
        text = path.read_text(encoding="utf-8")
        recorded = schema.from_json(text, schema.LedgerEntry)
        assert schema.to_json(recorded) == text, f"{path} is not canonical"
        cost = recorded.observed["cost_usd"]
        call_node(ledger_module.accrue, recorded, db_path, funds)
        assert recorded.observed["cost_usd"] == cost
        assert (cost is None) == (recorded.observed["tokens_in"] is None)
        assert recorded.metered is (recorded.observed["tokens_in"] is not None)
    assert ledger_module.aggregate(_RUN, db_path, today=_DAY).spend_usd > 0.0


def test_T_U_ledger_09(tmp_path: Path):
    """T-U-ledger-09 (FR-14.4): a negative amount is rejected, by the seam and by the table."""
    db_path = str(tmp_path / "loop.db")
    loop = open_store(tmp_path)
    seed_rows(loop)
    with pytest.raises(schema.ContractError) as caught:
        accrue_all(db_path, [entry("e-1", amount=-1.0)])
    assert caught.value.code == "E003_WRONG_TYPE"
    with pytest.raises(sqlite3.IntegrityError):
        loop.insert("ledger_entry", {
            "entry_id": "e-2", "run_manifest_id": _RUN, "arm": "seeded",
            "scope": "stage", "stage": "stage_3", "unit": "wall_clock_seconds",
            "amount": -1.0, "metered": 1, "observed_json": "{}",
            "timestamp_utc": f"{_DAY}T01:00:00+00:00", "stop_reason": None})


def test_T_U_ledger_10(tmp_path: Path):
    """T-U-ledger-10 (FR-14.6): `price`, the ledger's own arithmetic."""
    funds = budget()
    assert funds.price_usd_per_m_input_tokens == 0.75
    assert funds.price_usd_per_m_output_tokens == 3.75
    assert ledger_module.price(1_000_000, 1_000_000, funds) == 4.5
    assert ledger_module.price(11, 7, funds) == 0.000034
    assert ledger_module.price(0, 0, funds) == 0.0
    assert ledger_module.price(None, 7, funds) is None
    assert ledger_module.price(11, None, funds) is None

    dearer = budget(price_usd_per_m_input_tokens=1.5, price_usd_per_m_output_tokens=7.5)
    assert ledger_module.price(1_000_000, 1_000_000, dearer) == 9.0

    db_path = str(tmp_path / "loop.db")
    seed_rows(open_store(tmp_path))
    backend_usage = {"prompt_token_count": 11, "candidates_token_count": 7,
                     "cost": 99.0}                       # the backend reports no price
    charged = entry("v-1", stage="stage_1", observed=observed(
        cpu_seconds=0.5, tokens_in=backend_usage["prompt_token_count"],
        tokens_out=backend_usage["candidates_token_count"], cost_usd=99.0))
    call_node(ledger_module.accrue, charged, db_path, funds)
    assert charged.observed["cost_usd"] == 0.000034, "the backend's cost is ignored"

    unmetered = entry("c-1", stage="stage_1", metered=False)
    call_node(ledger_module.accrue, unmetered, db_path, funds)
    assert unmetered.observed["cost_usd"] is None
    aggregated = ledger_module.aggregate(_RUN, db_path, today=_DAY)
    assert aggregated.spend_usd == 0.000034


def test_T_U_ledger_11(tmp_path: Path):
    """T-U-ledger-11 (FR-18.10): the USD cap is campaign-wide, and third."""
    db_path = str(tmp_path / "loop.db")
    seed_rows(open_store(tmp_path))
    funds = budget(campaign_spend_cap_usd=0.01)
    accrue_all(db_path, [
        entry("v-1", arm="seeded", stage="stage_2", tokens_in=4000, tokens_out=1000),
        entry("v-2", arm="mutation", stage="stage_6", tokens_in=1000, tokens_out=500),
        entry("v-3", arm="shared", stage="synthesis", tokens_in=1000, tokens_out=500),
    ], funds)

    aggregated = ledger_module.aggregate(_RUN, db_path, today=_DAY)
    assert aggregated.spend_usd == pytest.approx(
        sum(ledger_module.price(i, o, funds) for i, o in
            ((4000, 1000), (1000, 500), (1000, 500))))
    assert set(aggregated.per_arm_spend_usd) == {"seeded", "mutation", "shared"}
    assert aggregated.spend_usd > funds.campaign_spend_cap_usd
    assert max(aggregated.per_arm_spend_usd.values()) < funds.campaign_spend_cap_usd

    assert aggregated.per_arm_window == {}, "neither window is bound"
    assert ledger_module.stop_reason(aggregated, "seeded", funds) == "campaign_spend_cap"
    assert ledger_module.stop_reason(aggregated, "mutation", funds) == "campaign_spend_cap"

    generous = budget(campaign_spend_cap_usd=200.0, arm_window_seconds=1.0)
    aggregated.per_arm_window["seeded"] = 2.0
    assert ledger_module.stop_reason(aggregated, "seeded", generous) == "arm_window"
    assert ledger_module.stop_reason(aggregated, "mutation", generous) is None
    tight = budget(campaign_spend_cap_usd=0.001, arm_window_seconds=1.0)
    assert ledger_module.stop_reason(aggregated, "seeded", tight) == "campaign_spend_cap"


@pytest.mark.t0
def test_T_U_ledger_15_filing_caps_are_per_run(tmp_path: Path):
    """T-U-ledger-15 (FR-13.8): the caps count THIS run's filings."""
    loop = open_store(tmp_path)
    seed_rows(loop)                                  # run-01, one candidate
    caps = budget(filings_total=2, filings_per_day=2)

    def approve(candidate_id: str, when: str) -> None:
        loop.insert("filing", {
            "candidate_id": candidate_id, "approver": "adi",
            "approved_at_utc": when, "decision": "report",
            "licence_confirmed": 1, "licence_confirmed_at_utc": when,
            "url_source": "pasted", "issue_number": None, "issue_url": None,
            "prefill_url_length": None, "prefill_fallback_reason": None,
            "confirmed": 0, "confirmed_at_utc": None, "confirmation_url": None})

    # Another run's candidates, and two filings approved against them.
    loop.insert("run", {
        "run_manifest_id": "run-02", "mode": "discovery", "seed_set": "171",
        "manifest_json": "{}", "budget_file_sha": "b" * 40,
        "cluster_yaml_sha": "c" * 40, "artefact_root": "/artefacts",
        "started_utc": "2026-09-20T00:00:00+00:00", "ended_utc": None})
    for index in range(2):
        probe_id, candidate_id = f"probe-o{index}", f"cand-o{index}"
        loop.insert("probe", {
            "probe_id": probe_id, "run_manifest_id": "run-02", "seed_sha": "a" * 40,
            "arm": "seeded", "iteration": 1, "tool": "circt-opt", "argv_json": "[]",
            "polarity": "expect_zero", "shape": "plain", "input_path": "/in.mlir",
            "mutator_id": None, "mutator_seed_int": None, "source_test_path": None,
            "spec_json": "{}", "artefact_dir": "/artefacts/run-02"})
        loop.insert("candidate", {
            "candidate_id": candidate_id, "local_id": None, "probe_id": probe_id,
            "run_manifest_id": "run-02", "arm": "seeded", "run_commit": "e" * 40,
            "image_digest": "sha256:aa", "oracle_class": "assertion",
            "assertion_text": "x", "assertion_site": "A.cpp:1",
            "frame_tuple_json": "[]", "out_of_scope_root": 0,
            "contaminated_symbol": 0, "contaminated_file": 0,
            "contamination_lower_bound": "seed_commit", "triage_class": "bug",
            "held_reason": None, "taxonomy_bucket": None,
            "artefact_dir": "/artefacts/run-02",
            "created_utc": "2026-09-20T01:00:00+00:00"})
        approve(candidate_id, f"{_DAY}T00:00:00+00:00")

    # This run has none of them.
    ledger = ledger_module.aggregate(_RUN, loop.db_path, today=_DAY)
    assert ledger.filings_total == 0 and ledger.filings_today == 0
    assert ledger.filings_lifetime_total == 2
    assert ledger_module.stop_reason(ledger, "seeded", caps) is None

    # One of its own is counted, and the second binds the cap.
    approve("cand-01", f"{_DAY}T00:00:00+00:00")
    ledger = ledger_module.aggregate(_RUN, loop.db_path, today=_DAY)
    assert (ledger.filings_total, ledger.filings_lifetime_total) == (1, 3)
    assert ledger_module.stop_reason(ledger, "seeded", caps) is None

    seed_rows(loop, probe_id="probe-02", candidate_id="cand-02",
              artefact_dir="/artefacts/run-01/probe-02")
    approve("cand-02", f"{_DAY}T00:00:00+00:00")
    ledger = ledger_module.aggregate(_RUN, loop.db_path, today=_DAY)
    assert (ledger.filings_total, ledger.filings_lifetime_total) == (2, 4)
    assert ledger_module.stop_reason(ledger, "seeded", caps) == "filings_total"

    # W-18: a cap of ZERO means "this run files nothing", not "this run does nothing".
    files_nothing = budget(filings_total=0, filings_per_day=0)
    assert ledger_module.stop_reason(ledger, "seeded", files_nothing) is None
    fresh = ledger_module.aggregate("no-such-run", loop.db_path, today=_DAY)
    assert fresh.filings_total == 0
    assert ledger_module.stop_reason(fresh, "seeded", files_nothing) is None
    assert ledger_module.stop_reason(
        fresh, "seeded", budget(filings_total=1, filings_per_day=0)) is None
    assert ledger_module.stop_reason(
        fresh, "seeded", budget(filings_total=0, filings_per_day=1)) is None
