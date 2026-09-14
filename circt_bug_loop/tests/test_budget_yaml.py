"""The committed `budget.yaml`: `04-Test-Plan.md` §1.26, `T-U-byaml-01` to `-04`."""
import math
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import budget as budget_module
from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import call_node
# The throwaway registration repository is `test_budget.py`'s.
from circt_bug_loop.tests.test_budget import _EARLY, _RUN_START, Repo

pytestmark = pytest.mark.t0

#: The committed file, at the path `budget.py` itself resolves (§1.1, §9.5).
COMMITTED = Path(budget_module.BUDGET_YAML)

#: §9.1's schema, minus the two fields the FILE does not carry.
_NOT_IN_FILE = ("contract_version", "budget_file_sha")

#: The four keys the backend decision added on 2026-09-14 (§16.5).
BACKEND_KEYS = ("model_id", "campaign_spend_cap_usd",
                "price_usd_per_m_input_tokens", "price_usd_per_m_output_tokens")

#: §9.3's seven acceptance keys and the sample size each feature-acceptance criterion names.
ACCEPTANCE = {"seed_sample": 5, "entry_tools": 3, "probe_batch": 20,
              "recorded_failures": 5, "recorded_crashes_for_reduction": 3,
              "labelled_pairs": 20, "iterations": 3}


def document() -> dict:
    """The committed file, parsed."""
    return yaml.safe_load(COMMITTED.read_text(encoding="utf-8"))


@pytest.fixture
def registered(tmp_path):
    """The committed file, landed in a throwaway repository and loaded."""
    repo = Repo(tmp_path)
    repo.commit("circt_bug_loop/budget.yaml",
                COMMITTED.read_text(encoding="utf-8"), when=_EARLY)
    return repo.load()


def test_T_U_byaml_01_the_committed_file_is_9_1s_schema(registered):
    """T-U-byaml-01 (FR-14.1): 29 keys, no key missing and none extra."""
    doc = document()
    declared = {field.name for field in schema.dataclasses.fields(schema.BudgetFile)}
    assert set(doc) == declared - set(_NOT_IN_FILE)
    assert len(doc) == 29

    for key in BACKEND_KEYS:
        assert key in doc, f"{key} is one of the four the backend decision added"
    assert doc["model_id"] == "gemini-3.8-flash"
    for price in ("price_usd_per_m_input_tokens", "price_usd_per_m_output_tokens"):
        assert isinstance(doc[price], float) and doc[price] > 0
        assert math.isfinite(doc[price])
    assert doc["campaign_spend_cap_usd"] > 0

    # W-18d: the registered tool-loop caps, which price every authorised turn.
    assert doc["max_tool_iterations"] == {"stage_1": 12, "stage_2": 12,
                                          "stage_6": 6, "stage_7": 20}

    # And it loads: the same twenty-seven values.
    assert isinstance(registered, schema.BudgetFile)
    assert registered.model_id == doc["model_id"]
    assert registered.contract_version == schema.CONTRACT_VERSION
    assert len(registered.budget_file_sha) == 40
    assert registered.max_tool_iterations == doc["max_tool_iterations"]


def test_T_U_byaml_02_every_default_that_lives_here_is_read_by_the_code(registered):
    """T-U-byaml-02 (FR-14.1): every key of the file is read by the flow."""
    from circt_bug_loop import bug_loop

    flow = Path(bug_loop.FLOW_DIR)
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(list(flow.glob("*.py")) + list(flow.glob("contract/*.py"))))
    unread = [key for key in document() if key not in sources]
    assert unread == []


def test_T_U_byaml_03_the_acceptance_block_is_9_3s_seven(registered):
    """T-U-byaml-03 (FR-14.1): the `acceptance` block carries §9.3's seven keys."""
    block = document()["acceptance"]
    assert block == ACCEPTANCE
    assert all(isinstance(value, int) and value > 0 for value in block.values())
    assert registered.acceptance == block


def test_T_U_byaml_04_the_calibration_sample_is_drawn(registered):
    """T-U-byaml-04 (FR-14.1): the sample agrees with its size, and is real."""
    doc = document()
    sample = doc["calibration_sample_shas"]
    assert len(sample) == doc["calibration_sample_size"] == 0
    assert registered.calibration_sample_shas == sample

    # The draw is re-derivable from this file alone.
    import json

    from circt_bug_loop import bug_loop

    mined = json.loads(
        (Path(__file__).resolve().parent / "fixtures" / "corpus"
         / "filtered_187.json").read_text(encoding="utf-8"))
    assert mined["corpus_head_sha"] == doc["corpus_head_sha"]
    exact = [c["sha"] for c in mined["candidates"] if c.get("exact")]
    assert len(exact) == 171, "FR-01.1's exact-pin count, at the corpus head"
    assert bug_loop.draw_calibration(corpus_head_sha=doc["corpus_head_sha"],
                                     sample_size=0, exact_pin_shas=exact) == []
    twenty = bug_loop.draw_calibration(corpus_head_sha=doc["corpus_head_sha"],
                                       sample_size=20, exact_pin_shas=exact)
    assert len(twenty) == len(set(twenty)) == 20
    assert set(twenty) <= set(exact), "check 5: every entry is an exact-pin seed"
    for sha in twenty:
        assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)
    assert twenty == bug_loop.draw_calibration(
        corpus_head_sha=doc["corpus_head_sha"], sample_size=20,
        exact_pin_shas=exact), "the draw is reproducible"


def test_T_U_byaml_05_the_registration_rule_holds_on_the_committed_bytes(tmp_path):
    """T-U-byaml-05 (FR-14.3): an edit after the commit is refused."""
    repo = Repo(tmp_path)
    repo.commit("circt_bug_loop/budget.yaml",
                COMMITTED.read_text(encoding="utf-8"), when=_EARLY)
    assert repo.load(run_start_utc=_RUN_START).budget_file_sha

    repo.budget.write_text(
        COMMITTED.read_text(encoding="utf-8").replace(
            "fingerprint_top_n: 5", "fingerprint_top_n: 6"), encoding="utf-8")
    with pytest.raises(budget_module.BudgetError) as refused:
        call_node(budget_module.load_budget, str(repo.budget), str(repo.root),
                  run_start_utc=_RUN_START)
    assert "budget.yaml" in str(refused.value)


#: The pilot pre-registration, beside the campaign's (§1.1).
PILOT = COMMITTED.with_name("budget-pilot.yaml")

#: The eight values the pilot changes, and the whole of what it changes.
PILOT_CHANGES = {"arm_window_seconds": 900.0, "campaign_spend_cap_usd": 3.0,
                 "generated_inputs_per_day": 200, "filings_per_day": 0,
                 "filings_total": 0, "per_seed_probe_cap": 3,
                 "per_seed_iteration_cap": 1}


def test_T_U_byaml_06_the_pilot_file_is_the_campaigns_less_seven_values(tmp_path):
    """T-U-byaml-06 (FR-14.1): a COPY with seven values changed."""
    campaign = document()
    pilot = yaml.safe_load(PILOT.read_text(encoding="utf-8"))

    assert set(pilot) == set(campaign), "9.1's key set is closed (check 2)"
    changed = {key: value for key, value in pilot.items() if value != campaign[key]}
    assert changed == PILOT_CHANGES
    assert pilot["filings_per_day"] == 0 and pilot["filings_total"] == 0
    assert len(pilot["calibration_sample_shas"]) == pilot["calibration_sample_size"]
    for key in ("price_usd_per_m_input_tokens", "price_usd_per_m_output_tokens",
                "corpus_head_sha", "model_id", "fingerprint_top_n",
                # The fix under measurement, which the pilot may not shrink.
                "max_tool_iterations", "minimal_case_lines"):
        assert pilot[key] == campaign[key], key

    # And it LOADS as a campaign would.
    repo = Repo(tmp_path)
    repo.commit("circt_bug_loop/budget.yaml", PILOT.read_text(encoding="utf-8"),
                when=_EARLY)
    repo.register()
    loaded = call_node(budget_module.load_budget, str(repo.budget), str(repo.root),
                       run_start_utc=_RUN_START, campaign=True)
    assert loaded["budget"].campaign_spend_cap_usd == 3.0
    assert loaded["budget"].arm_window_seconds == 900.0
    assert loaded["registration"]["tag"] == "registration/campaign-01"
