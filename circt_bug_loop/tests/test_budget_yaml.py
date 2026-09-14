"""The committed `budget.yaml`: `04-Test-Plan.md` §1.26, `T-U-byaml-01` to `-04`.

The artefact under test is a **data file** and not a module, which is why
`03-LLD.md` §1.3 exempts it from the source-to-test mapping by name and why this
module exists at all (`T-U-layout-01`'s exemption list). All tier 0.

The file is read where it is committed, `budget.py:BUDGET_YAML`, and never
copied: a second copy under `fixtures/` could disagree with the
pre-registration, which is the one thing FR-14.3 exists to make impossible. The
pre-registration checks themselves need a git history that has landed the file,
so they run against a throwaway repository built here, which is `test_budget.py`'s
own `Repo` reused rather than written twice.

**One row of §1.26 is not implemented here and cannot be.** `T-U-byaml-02` asks
that every campaign `[DEFAULT]` marker of `01-FRD.md` resolve to exactly one key
of this file. That is a walk into `design/`, and §1.4 puts this package at two
different depths in two trees, so no test module here may walk there
(`T-U-layout-09` forbids the ancestor walk it would need, and `results.py`'s
erratum 7 records the same finding for §14.4's table). It is a repository-wide
check and is recorded as owed in `design/reviews/implementation-errata-log.md`.
"""
import math
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import budget as budget_module
from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import call_node
# The throwaway registration repository is `test_budget.py`'s, and one
# repository builder is enough for both modules (§13's `repo/` row).
from circt_bug_loop.tests.test_budget import _EARLY, _RUN_START, Repo

pytestmark = pytest.mark.t0

#: The committed file, at the path `budget.py` itself resolves (§1.1, §9.5).
COMMITTED = Path(budget_module.BUDGET_YAML)

#: §9.1's schema, minus the two fields the FILE does not carry: `contract_version`
#: is the seam's own and `budget_file_sha` is the registration commit, which the
#: loader reads out of git and which the file cannot state about itself.
_NOT_IN_FILE = ("contract_version", "budget_file_sha")

#: The four keys the backend decision added on 2026-09-14 (§16.5, ADR-D-03),
#: which are what took §9.1 from twenty-three keys to twenty-seven.
BACKEND_KEYS = ("model_id", "campaign_spend_cap_usd",
                "price_usd_per_m_input_tokens", "price_usd_per_m_output_tokens")

#: §9.3's seven acceptance keys and the sample size each feature-acceptance
#: criterion names, hard-coded here for the reason `results.py`'s erratum 7
#: gives: this package may not walk to `design/` (§1.4), so the numbers are
#: transcribed and a change to either side fails this test rather than passing
#: silently.
ACCEPTANCE = {"seed_sample": 5, "entry_tools": 3, "probe_batch": 20,
              "recorded_failures": 5, "recorded_crashes_for_reduction": 3,
              "labelled_pairs": 20, "iterations": 3}


def document() -> dict:
    """The committed file, parsed. Read once per test so an edit cannot hide."""
    return yaml.safe_load(COMMITTED.read_text(encoding="utf-8"))


@pytest.fixture
def registered(tmp_path):
    """The committed file, landed in a throwaway repository and loaded.

    The commit that lands `budget.yaml` **is** the registration (FR-14.3, G-32),
    so a `load_budget` with the checks live needs a history in which that
    happened; `Repo` is that history, and the bytes are the committed file's.
    Returns the `BudgetFile` the six checks of §9.2 accepted.
    """
    repo = Repo(tmp_path)
    repo.commit("circt_bug_loop/budget.yaml",
                COMMITTED.read_text(encoding="utf-8"), when=_EARLY)
    return repo.load()


def test_T_U_byaml_01_the_committed_file_is_9_1s_schema(registered):
    """T-U-byaml-01 (FR-14.1): 29 keys, no key missing and none extra.

    The key set is compared against `BudgetFile`'s own fields for **equality**,
    which is stronger than a count and is what makes a key added to one and not
    the other a failure. `model_id` is `gemini-3.8-flash` and the two prices are
    present, positive and finite, which is ADR-D-03's own requirement of the
    file. Fixture: the committed file, landed in a throwaway repository. Tier 0.
    """
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

    # And it loads: the same twenty-seven values, through the seam's validator
    # and §9.2's six pre-registration checks.
    assert isinstance(registered, schema.BudgetFile)
    assert registered.model_id == doc["model_id"]
    assert registered.contract_version == schema.CONTRACT_VERSION
    assert len(registered.budget_file_sha) == 40


def test_T_U_byaml_02_every_default_that_lives_here_is_read_by_the_code(registered):
    """T-U-byaml-02 (FR-14.1): every key of the file is read by the flow.

    §1.26's row asks that every campaign `[DEFAULT]` marker of `01-FRD.md`
    resolve to exactly one key here. That is a walk into `design/`, which §1.4
    forbids this package (see the module docstring), so the direction the code
    can check is the other one: no key of the file is dead. Every one is read by
    name somewhere in the flow, which is what a `[DEFAULT]` with a home means
    operationally, and a key nothing reads is a parameter nobody chose.
    Fixture: the committed file. Tier 0.
    """
    from circt_bug_loop import bug_loop

    flow = Path(bug_loop.FLOW_DIR)
    sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(list(flow.glob("*.py")) + list(flow.glob("contract/*.py"))))
    unread = [key for key in document() if key not in sources]
    assert unread == []


def test_T_U_byaml_03_the_acceptance_block_is_9_3s_seven(registered):
    """T-U-byaml-03 (FR-14.1): the `acceptance` block carries §9.3's seven keys.

    Each is a sample size a feature-acceptance criterion names, and each is a
    positive integer: a sample size of zero is a criterion that cannot fail.
    §10's own denominator, `labelled_pairs`, is one of them and is what
    `T-U-triage-09` measures against. Fixture: the committed file. Tier 0.
    """
    block = document()["acceptance"]
    assert block == ACCEPTANCE
    assert all(isinstance(value, int) and value > 0 for value in block.values())
    assert registered.acceptance == block


def test_T_U_byaml_04_the_calibration_sample_is_drawn(registered):
    """T-U-byaml-04 (FR-14.1, FR-14.3): the sample agrees with its size, and is real.

    **THE COMMITTED SAMPLE IS EMPTY, and that is a measurement** (W-22): a seed
    is calibratable only when its parent's `llvm` gitlink IS the run's pin, and
    0 of the 187 seed parents carry this deployment's pin, the 187 being spread
    over 44 distinct pins (`bug_loop.calibratable`, measured 2026-09-15). A
    sample of twenty would name twenty seeds calibration mode refuses to probe.
    So the file declares a size of zero and an empty list, check 5 agrees them,
    and the campaign is registered as discovery mode.

    The draw itself is still asserted, here over the size the file USED to
    carry, so that `draw_calibration` remains pinned to
    `random.Random(corpus_head_sha)` and to the committed corpus measurement.
    Fixture: the committed file and the 187-seed corpus. Tier 0.
    """
    doc = document()
    sample = doc["calibration_sample_shas"]
    assert len(sample) == doc["calibration_sample_size"] == 0
    assert registered.calibration_sample_shas == sample

    # The draw is re-derivable from this file alone: `random.Random` is seeded
    # by `corpus_head_sha`, which is a value the file carries.
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
    """T-U-byaml-05 (FR-14.3, FR-14.7): an edit after the commit is refused.

    New id, and the reason it is here rather than in `test_budget.py`: §1.15's
    checks are about the loader and this is about the committed FILE, that a
    campaign started from the bytes in the repository is registered and that the
    same bytes edited after the commit are not. Fixture: the committed file in a
    throwaway repository. Tier 0.
    """
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


#: The pilot pre-registration, beside the campaign's (§1.1). A separate FILE and
#: not an edit, FR-14.7 forbidding an edit to a registered one.
PILOT = COMMITTED.with_name("budget-pilot.yaml")

#: The eight values the pilot changes, and the whole of what it changes. The
#: window and the cap are PILOT 2's (`registration/pilot-2`, W-18b): pilot 1
#: registered 900 s and USD 5.00 and spent 7.163957 of it, so the run that
#: measures the fix gets a shorter window and a smaller cap. The two keys
#: contract 2.2 added are NOT in this map, and must not be: they are the fix
#: under measurement and the pilot must carry the campaign's own values for
#: them or it measures something else.
PILOT_CHANGES = {"arm_window_seconds": 600.0, "campaign_spend_cap_usd": 3.0,
                 "generated_inputs_per_day": 200, "filings_per_day": 0,
                 "filings_total": 0, "per_seed_probe_cap": 3,
                 "per_seed_iteration_cap": 1}


def test_T_U_byaml_06_the_pilot_file_is_the_campaigns_less_seven_values(tmp_path):
    """T-U-byaml-06 (W-18, FR-14.1, FR-14.7): a COPY with seven values changed.

    New id, W-18. The pilot is its own pre-registration with its own tag, so it
    is a second file and never an edit of the first. Its key set is §9.1's to the
    letter - a key the pilot added would be a key check 2 refuses - and every
    value it does not change is byte-for-byte the campaign's, including both
    verified prices, the corpus head and the model id, so the pilot measures the
    campaign's own parameters wherever it is not deliberately smaller. It files
    NOTHING: both filing caps are zero. Fixture: both committed files, the pilot
    landed in a throwaway repository. Tier 0.
    """
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

    # And it LOADS as a campaign would: §9.2's six checks against a history that
    # landed it and a `registration/*` tag that reaches that commit.
    repo = Repo(tmp_path)
    repo.commit("circt_bug_loop/budget.yaml", PILOT.read_text(encoding="utf-8"),
                when=_EARLY)
    repo.register()
    loaded = call_node(budget_module.load_budget, str(repo.budget), str(repo.root),
                       run_start_utc=_RUN_START, campaign=True)
    assert loaded["budget"].campaign_spend_cap_usd == 3.0
    assert loaded["budget"].arm_window_seconds == 600.0
    assert loaded["registration"]["tag"] == "registration/campaign-01"
