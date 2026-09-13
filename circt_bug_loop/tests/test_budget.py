"""`budget.py`: the schema, the pre-registration rule, the six checks.

`04-Test-Plan.md` §1.15, the thirteen `T-U-budget-*` tests. All tier 0: the
module is head-side and its one external read is `git` against a throwaway
repository this file builds in a temporary directory (§13's `repo/` row, whose
repositories are produced at test time and never committed).

The complete file of `03-LLD.md` §9.5 is the repository's own committed
`budget.yaml`, read rather than copied: a second copy under `fixtures/budget/`
could disagree with the pre-registration, and the malformed variants below are
each that file with **one** edit, which is the derivation §13 specifies.
"""
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import budget as budget_module
from circt_bug_loop import store
from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import FIXTURES

pytestmark = pytest.mark.t0

#: `03-LLD.md` §9.5's complete file, as committed.
COMPLETE = Path(budget_module.BUDGET_YAML)

_EARLY = datetime(2026, 9, 1, tzinfo=timezone.utc)
_RUN_START = datetime(2026, 9, 20, tzinfo=timezone.utc)
_IDENTITY = {"GIT_AUTHOR_NAME": "bugloop", "GIT_AUTHOR_EMAIL": "bugloop@invalid",
             "GIT_COMMITTER_NAME": "bugloop", "GIT_COMMITTER_EMAIL": "bugloop@invalid"}


class Repo:
    """A throwaway git repository holding one `circt_bug_loop/budget.yaml`."""

    def __init__(self, root: Path):
        self.root = root
        (root / "circt_bug_loop").mkdir(parents=True)
        self.budget = root / "circt_bug_loop" / "budget.yaml"
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, when: datetime = None) -> str:
        environment = {**os.environ, **_IDENTITY}
        if when is not None:
            environment["GIT_AUTHOR_DATE"] = environment["GIT_COMMITTER_DATE"] = \
                when.isoformat()
        done = subprocess.run(("git", "-C", str(self.root), *args), text=True,
                              capture_output=True, env=environment)
        assert done.returncode == 0, done.stderr
        return done.stdout

    def commit(self, relative: str, text: str, when: datetime = _EARLY) -> str:
        """Write *text* to *relative*, commit it at *when*, return the commit SHA."""
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        self.git("add", "--", relative)
        self.git("commit", "-q", "-m", f"land {relative}", when=when)
        return self.git("log", "-1", "--format=%H", "--", relative).strip()

    def load(self, **kwargs):
        """`load_budget` against this repository's budget file."""
        kwargs.setdefault("run_start_utc", _RUN_START)
        return budget_module.load_budget(str(self.budget), str(self.root), **kwargs)


def edited(**changes) -> str:
    """§9.5's file with one edit each, as YAML text.

    A key set to the sentinel `_DROP` is removed rather than changed, which is
    how the 27 one-key-short copies of `fixtures/budget/missing/` are made.
    """
    document = yaml.safe_load(COMPLETE.read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is _DROP:
            document.pop(key)
        else:
            document[key] = value
    return yaml.safe_dump(document, sort_keys=True)


_DROP = object()


@pytest.fixture()
def repo(tmp_path: Path) -> Repo:
    """A repository whose `budget.yaml` is §9.5's file, committed before the run."""
    made = Repo(tmp_path / "preregistered")
    made.commit("circt_bug_loop/budget.yaml", COMPLETE.read_text(encoding="utf-8"))
    return made


def test_T_U_budget_01(repo: Repo):
    """T-U-budget-01 (FR-14.1): a file missing any key of §9.1 is rejected, naming it.

    All 27 keys one at a time, the four of 2026-09-14 included.
    """
    assert len(budget_module._KEYS) == 27
    for key in budget_module._KEYS:
        repo.commit("circt_bug_loop/budget.yaml", edited(**{key: _DROP}))
        with pytest.raises((budget_module.BudgetError, schema.ContractError)) as caught:
            repo.load()
        assert key in str(caught.value), f"the refusal does not name {key}"
    for key in ("model_id", "campaign_spend_cap_usd", "price_usd_per_m_input_tokens",
                "price_usd_per_m_output_tokens"):
        assert key in budget_module._KEYS


def test_T_U_budget_02(repo: Repo):
    """T-U-budget-02 (FR-14.1): any other top-level key is rejected, naming it."""
    repo.commit("circt_bug_loop/budget.yaml", edited(gpu_hours=12))
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load()
    assert "gpu_hours" in str(caught.value)


def test_T_U_budget_03(repo: Repo):
    """T-U-budget-03 (FR-14.1): every key's type is checked as declared."""
    for key, wrong in (("arm_window_seconds", "14400"), ("fingerprint_top_n", "five"),
                       ("probe_wall_seconds", "60"), ("arm_order", "seeded"),
                       ("calibration_sample_shas", "0" * 40),
                       ("campaign_start_utc", 2026)):
        repo.commit("circt_bug_loop/budget.yaml", edited(**{key: wrong}))
        with pytest.raises(schema.ContractError) as caught:
            repo.load()
        assert caught.value.code == "E003_WRONG_TYPE" and key in str(caught.value)

    repo.commit("circt_bug_loop/budget.yaml", edited(acceptance={"seed_sample": 5}))
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load()
    assert "acceptance" in str(caught.value)

    # An int where a float belongs is accepted, per 2.3's float rule.
    repo.commit("circt_bug_loop/budget.yaml", edited(arm_window_seconds=14400))
    assert repo.load().arm_window_seconds == 14400


def test_T_U_budget_04(tmp_path: Path):
    """T-U-budget-04 (FR-14.2): an uncommitted budget.yaml exits non-zero, naming it."""
    made = Repo(tmp_path / "uncommitted")
    made.commit("README.md", "the repository exists\n")
    made.budget.write_text(COMPLETE.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(budget_module.BudgetError) as caught:
        made.load()
    assert "not committed" in str(caught.value)
    assert "circt_bug_loop/budget.yaml" in str(caught.value)

    # committed, then edited in the working tree: the commit no longer registers it
    sha = made.commit("circt_bug_loop/budget.yaml", COMPLETE.read_text(encoding="utf-8"))
    made.budget.write_text(edited(filings_total=99), encoding="utf-8")
    with pytest.raises(budget_module.BudgetError) as caught:
        made.load()
    assert sha in str(caught.value)


def test_T_U_budget_05(tmp_path: Path):
    """T-U-budget-05 (FR-14.2): a commit that post-dates the run's start is refused."""
    made = Repo(tmp_path / "later_commit")
    later = _RUN_START + timedelta(days=1)
    sha = made.commit("circt_bug_loop/budget.yaml",
                      COMPLETE.read_text(encoding="utf-8"), when=later)
    with pytest.raises(budget_module.BudgetError) as caught:
        made.load()
    message = str(caught.value)
    assert sha in message
    assert later.isoformat() in message and _RUN_START.isoformat() in message


def test_T_U_budget_06(repo: Repo):
    """T-U-budget-06 (FR-14.3): the SHA is git's, and it reaches the manifest."""
    expected = repo.git("log", "-1", "--format=%H", "--",
                        "circt_bug_loop/budget.yaml").strip()
    loaded = repo.load()
    assert loaded.budget_file_sha == expected

    document = (FIXTURES / "run_manifest" / "discovery_01.json").read_text(encoding="utf-8")
    manifest = schema.from_json(document, schema.RunManifest)
    manifest.budget_file_sha = loaded.budget_file_sha
    schema.validate(manifest)
    assert manifest.budget_file_sha == expected


def test_T_U_budget_07(repo: Repo):
    """T-U-budget-07 (FR-05.2): a mutator set committed after the budget file is refused."""
    repo.commit("circt_bug_loop/mutators/set_v1.json", '{"set_version": "v1"}\n',
                when=_EARLY + timedelta(days=1))
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load()
    assert "mutators/set_v1.json" in str(caught.value)
    assert "FR-05.2" in str(caught.value)

    repo.commit("circt_bug_loop/mutators/set_v1.json", '{"set_version": "v2"}\n',
                when=_EARLY - timedelta(days=1))
    assert repo.load().budget_file_sha, "a set frozen before the registration passes"


def test_T_U_budget_08(repo: Repo):
    """T-U-budget-08 (FR-14.7): a change after the manifest is stamped invalidates it."""
    stamped = repo.load().budget_file_sha
    assert repo.load(manifest_budget_file_sha=stamped).budget_file_sha == stamped

    amended = repo.commit("circt_bug_loop/budget.yaml", edited(filings_total=99))
    assert amended != stamped
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load(manifest_budget_file_sha=stamped)
    assert stamped in str(caught.value) and amended in str(caught.value)


def test_T_U_budget_09(repo: Repo):
    """T-U-budget-09 (FR-16.4): `snapshot` is four fields and the generator sees no more."""
    fields = [f.name for f in __import__("dataclasses").fields(schema.LedgerSnapshot)]
    assert fields == ["arm", "unit", "spent", "cap"]

    loaded = repo.load()
    ledger = store.BudgetLedger(
        run_manifest_id="run-01", per_arm_window={"seeded": 3600.0},
        per_arm_stage={}, shared_stage={}, inputs_today={}, filings_today=0,
        filings_total=0, spend_usd=12.5, per_arm_spend_usd={"seeded": 12.5},
        stop_reason={"seeded": None})
    view = budget_module.snapshot(ledger, "seeded", loaded)
    assert view == schema.LedgerSnapshot(arm="seeded", unit="wall_clock_seconds",
                                         spent=3600.0, cap=14400.0)
    assert budget_module.snapshot(ledger, "mutation", loaded).spent == 0.0
    assert not hasattr(view, "spend_usd")
    with pytest.raises(schema.ContractError) as caught:
        budget_module.snapshot(ledger, "shared", loaded)
    assert caught.value.code == "E004_BAD_ENUM"


def test_T_U_budget_10(repo: Repo):
    """T-U-budget-10 (FR-14.1, FR-14.5): §9.5's file is accepted, complete and closed.

    Equality on the unit and on both safety caps is structural: one value per
    key, and no per-arm value to be unequal. The two figures this revision moved
    are asserted at their new values.
    """
    document = yaml.safe_load(COMPLETE.read_text(encoding="utf-8"))
    assert sorted(document) == sorted(budget_module._KEYS)

    loaded = repo.load()
    assert loaded.reduction_wall_seconds == 600
    assert loaded.artefact_inline_cap_bytes == 262144
    assert loaded.arm_order == ["seeded", "mutation"]
    assert isinstance(loaded.arm_window_seconds, float) and loaded.arm_window_seconds == 14400.0
    assert set(loaded.acceptance) == budget_module._ACCEPTANCE_KEYS

    repo.commit("circt_bug_loop/budget.yaml", edited(arm_order=["seeded", "seeded"]))
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load()
    assert "exactly once" in str(caught.value)


def test_T_U_budget_11(repo: Repo):
    """T-U-budget-11 (FR-14.1, FR-14.2): check 5, the calibration sample.

    The sample is part of the pre-registration, so a file whose declared size
    and drawn list disagree is refused, and the empty list §9.5 once shipped is
    refused with them.
    """
    drawn = yaml.safe_load(COMPLETE.read_text(encoding="utf-8"))["calibration_sample_shas"]
    assert len(drawn) == 20

    repo.commit("circt_bug_loop/budget.yaml", edited(calibration_sample_shas=[]))
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load()
    assert "calibration_sample_size" in str(caught.value)

    repo.commit("circt_bug_loop/budget.yaml", edited(calibration_sample_shas=drawn[:19]))
    with pytest.raises(budget_module.BudgetError):
        repo.load()

    repo.commit("circt_bug_loop/budget.yaml",
                edited(calibration_sample_shas=drawn[:19] + ["not-a-sha"]))
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load()
    assert "40 hex" in str(caught.value)

    repo.commit("circt_bug_loop/budget.yaml",
                edited(calibration_sample_shas=drawn[:19] + [drawn[0]]))
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load()
    assert "repeat" in str(caught.value)

    repo.commit("circt_bug_loop/budget.yaml", COMPLETE.read_text(encoding="utf-8"))
    assert repo.load(exact_pin_shas=set(drawn)).calibration_sample_shas == drawn
    with pytest.raises(budget_module.BudgetError) as caught:
        repo.load(exact_pin_shas=set(drawn[:19]))
    assert "exact-pin" in str(caught.value)


def test_T_U_budget_12(repo: Repo):
    """T-U-budget-12 (FR-14.1, FR-14.6, NFR-08): check 6, the pair of prices.

    The pair is the point: a file carrying one price and not the other would
    value half the campaign's tokens at zero, so the ledger would under-report
    the spend it is meant to stop on. `budget.py` makes six checks and the count
    is asserted here.
    """
    assert len(budget_module._CHECKS) == 6

    prices = ("price_usd_per_m_input_tokens", "price_usd_per_m_output_tokens")
    for key in prices:
        repo.commit("circt_bug_loop/budget.yaml", edited(**{key: _DROP}))
        with pytest.raises(budget_module.BudgetError) as caught:
            repo.load()
        assert key in str(caught.value)
        for bad in (0, -1.5, float("nan"), float("inf")):
            repo.commit("circt_bug_loop/budget.yaml", edited(**{key: bad}))
            with pytest.raises(schema.ContractError) as caught:
                repo.load()
            assert caught.value.code == "E003_WRONG_TYPE" and key in str(caught.value)
        repo.commit("circt_bug_loop/budget.yaml", edited(**{key: "0.75"}))
        with pytest.raises(schema.ContractError) as caught:
            repo.load()
        assert caught.value.code == "E003_WRONG_TYPE" and key in str(caught.value)
        repo.commit("circt_bug_loop/budget.yaml", COMPLETE.read_text(encoding="utf-8"))

    for value in (0, -200.0):
        repo.commit("circt_bug_loop/budget.yaml", edited(campaign_spend_cap_usd=value))
        with pytest.raises(schema.ContractError) as caught:
            repo.load()
        assert "campaign_spend_cap_usd" in str(caught.value)

    repo.commit("circt_bug_loop/budget.yaml", edited(model_id="  "))
    with pytest.raises(schema.ContractError) as caught:
        repo.load()
    assert caught.value.code == "E002_MISSING_FIELD" and "model_id" in str(caught.value)


def test_T_U_budget_13(repo: Repo):
    """T-U-budget-13 (FR-14.1, FR-14.6): the four keys of 2026-09-14 reach consumers.

    `model_id` is the model half of the `vertex:<id>` pair `RunManifest.model_ids`
    records; `campaign_spend_cap_usd` is what `ledger.stop_reason` compares
    against; the two prices are what `ledger.price` multiplies by. `build_llm`,
    the fourth consumer, is `generate_task.py`'s and is W-07's to land.
    """
    ledger_module = pytest.importorskip("circt_bug_loop.ledger")
    loaded = repo.load()

    assert loaded.model_id == "gemini-3.8-flash"
    manifest = schema.from_json(
        (FIXTURES / "run_manifest" / "discovery_01.json").read_text(encoding="utf-8"),
        schema.RunManifest)
    assert all(value == f"{manifest.backend}:{loaded.model_id}"
               for value in manifest.model_ids.values())

    assert ledger_module.price(1_000_000, 1_000_000, loaded) == 4.5
    assert ledger_module.price(11, 7, loaded) == 0.000034

    ledger = store.BudgetLedger(
        run_manifest_id="run-01", per_arm_window={"seeded": 1.0},
        per_arm_stage={}, shared_stage={}, inputs_today={}, filings_today=0,
        filings_total=0, spend_usd=loaded.campaign_spend_cap_usd,
        per_arm_spend_usd={"seeded": loaded.campaign_spend_cap_usd},
        stop_reason={"seeded": None, "mutation": None})
    assert ledger_module.stop_reason(ledger, "seeded", loaded) == "campaign_spend_cap"
    assert ledger_module.stop_reason(ledger, "mutation", loaded) == "campaign_spend_cap"
