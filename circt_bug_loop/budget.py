"""budget.yaml: load it, enforce the pre-registration, hand out snapshots."""
from __future__ import annotations

import dataclasses
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop import mutators
from circt_bug_loop.contract.schema import (Arm, BudgetFile, ContractError,
                                            CounterBlock,
                                            LedgerSnapshot, validate)

#: The committed pre-registration.
BUDGET_YAML = str(Path(__file__).resolve().parent / "budget.yaml")

#: 8.1 rule 2's file, relative to the flow directory.
MUTATOR_SET = os.path.join("mutators", mutators.SET_PATH.name)

#: THE PRE-REGISTRATION, since W-12 (architect decision).
REGISTRATION_TAGS = "refs/tags/registration/*"

#: 9.2's six, named so `len(_CHECKS) == 6` is assertable.
_CHECKS = ("committed_and_earlier", "complete_and_closed", "equal_on_the_unit",
           "unchanged_mid_campaign", "calibration_sample", "prices_and_caps")

#: Every key 9.1 declares: BudgetFile's fields less the two the file does not carry.
_NOT_IN_FILE = ("contract_version", "budget_file_sha")
_KEYS = tuple(f.name for f in dataclasses.fields(BudgetFile)
              if f.name not in _NOT_IN_FILE)

#: 9.3's acceptance block, key for key.
_ACCEPTANCE_KEYS = frozenset({"seed_sample", "entry_tools", "probe_batch",
                              "recorded_failures", "recorded_crashes_for_reduction",
                              "labelled_pairs", "iterations"})

_GIT_FORMAT = "%H%x09%cI"
_HEX40 = frozenset("0123456789abcdef")


class BudgetError(Exception):
    """Raised by load_budget."""


def _git(repo_root: str, *args: str) -> str:
    """Run one read-only `git` command in *repo_root* and return its stdout."""
    done = subprocess.run(("git", "-C", repo_root, *args), capture_output=True,
                          text=True)
    if done.returncode != 0:
        raise BudgetError(f"git {' '.join(args)} in {repo_root!r} failed: "
                          f"{done.stderr.strip()}")
    return done.stdout


def _last_commit(repo_root: str, relative_path: str) -> tuple:
    """Return (sha, committed datetime) of the last commit touching *relative_path*."""
    line = _git(repo_root, "log", "-1", f"--format={_GIT_FORMAT}", "--",
                relative_path).strip()
    if not line:
        return (None, None)
    sha, _, when = line.partition("\t")
    return (sha, _iso(when))


def registration(repo_root: str) -> tuple:
    """Return (tag, commit) of the newest `registration/*` tag, or ("", "")."""
    tag = _git(repo_root, "for-each-ref", "--sort=-creatordate", "--count=1",
               "--format=%(refname:short)", REGISTRATION_TAGS).strip()
    if not tag:
        return ("", "")
    return (tag, _git(repo_root, "rev-parse", f"{tag}^{{commit}}").strip())


def _descends_from(repo_root: str, ancestor: str, descendant: str) -> bool:
    """True when *ancestor* IS *descendant* or one of its ancestors."""
    done = subprocess.run(("git", "-C", repo_root, "merge-base", "--is-ancestor",
                           ancestor, descendant), capture_output=True)
    if done.returncode not in (0, 1):       # 1 is the answer "no", not a failure
        raise BudgetError(
            f"git merge-base --is-ancestor {ancestor} {descendant} in "
            f"{repo_root!r} failed: "
            f"{done.stderr.decode('utf-8', errors='backslashreplace').strip()}")
    return done.returncode == 0


def _iso(text: str) -> datetime:
    """Parse an ISO 8601 instant, including the trailing Z git writes for UTC."""
    return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)


def _relative(path: str, repo_root: str) -> str:
    """The pathspec *path* has inside *repo_root*, as git wants it."""
    relative = os.path.relpath(os.path.abspath(path), os.path.abspath(repo_root))
    if relative.startswith(os.pardir):
        raise BudgetError(f"{path!r} is outside the repository {repo_root!r}")
    return relative


@ChiaFunction(max_retries=0)
def load_budget(path: str, repo_root: str, *, run_start_utc=None,
                manifest_budget_file_sha: str = None,
                exact_pin_shas=None, campaign: bool = False) -> dict:
    """Parse, validate and pre-registration-check one budget.yaml.

    Returns:
        {"budget": BudgetFile, "counters": CounterBlock, "registration": {"tag": str, "commit": str}}, the BudgetFile with budget_file_sha set to the commit that landed the file, which stays the run's identity (FR-14.3); the registration pair is empty when the repository holds no tag.
    Worker:
        none; head-side, one subprocess per `git` read.
    Raises:
        BudgetError on any of the six checks, naming the key, the commit or the pair of timestamps.
    """
    started_at = time.monotonic()
    text = Path(path).read_text(encoding="utf-8")
    document = yaml.safe_load(text)
    if not isinstance(document, dict):
        raise BudgetError(f"{path!r} does not parse to a mapping")

    # --- check 1: committed, and earlier, and unedited since -----------------
    relative = _relative(path, repo_root)
    sha, committed_at = _last_commit(repo_root, relative)
    if sha is None:
        raise BudgetError(
            f"{relative} is not committed in {repo_root!r}: the commit that "
            f"lands it is the pre-registration (FR-14.2, FR-14.3)")
    dirty = _git(repo_root, "status", "--porcelain", "--", relative).strip()
    if dirty:
        raise BudgetError(
            f"{relative} differs from its commit {sha}: editing it invalidates "
            f"the campaign (FR-14.7)")
    started = run_start_utc or datetime.now(timezone.utc)
    if isinstance(started, str):
        started = _iso(started)
    if committed_at >= started:
        raise BudgetError(
            f"{relative}'s commit {sha} is dated {committed_at.isoformat()}, "
            f"which does not precede the run's start {started.isoformat()} "
            f"(FR-14.2)")
    tag, registered = registration(repo_root)
    if not tag and campaign:
        raise BudgetError(
            f"{repo_root!r} carries no {REGISTRATION_TAGS} tag: a campaign is "
            f"pre-registered by an annotated tag on the commit that lands "
            f"{relative}, and this repository has not been registered "
            f"(FR-14.2, FR-14.3). A --dry-run and a --generator recorded run "
            f"need no registration.")
    if tag:
        if not _descends_from(repo_root, sha, registered):
            raise BudgetError(
                f"{relative}'s commit {sha} is neither {tag} ({registered}) nor "
                f"an ancestor of it: the file was edited after the "
                f"pre-registration, which invalidates the campaign (FR-14.7)")
        _check_frozen_set(repo_root, os.path.dirname(relative), tag, registered)

    # --- check 2: complete and closed ---------------------------------------
    missing = sorted(set(_KEYS) - set(document))
    if missing:
        raise BudgetError(f"{relative} lacks {missing} (9.1, FR-14.1)")
    extra = sorted(set(document) - set(_KEYS))
    if extra:
        raise BudgetError(f"{relative} carries {extra}, which 9.1 does not "
                          f"declare (FR-14.1)")
    budget = BudgetFile(budget_file_sha=sha, **document)
    validate(budget)                      # E003 and E004 per key, then check 6
    if not isinstance(budget.acceptance, dict) or set(budget.acceptance) != _ACCEPTANCE_KEYS:
        raise BudgetError(
            f"{relative}'s acceptance keys "
            f"{sorted(budget.acceptance) if isinstance(budget.acceptance, dict) else budget.acceptance} "
            f"differ from 9.3's {sorted(_ACCEPTANCE_KEYS)}")

    # --- check 3: equal on the unit and on both safety caps ------------------
    if sorted(budget.arm_order) != ["mutation", "seeded"]:
        raise BudgetError(
            f"{relative}'s arm_order {budget.arm_order} must name each arm "
            f"exactly once (FR-14.5)")

    # --- check 4: unchanged mid-campaign -------------------------------------
    if manifest_budget_file_sha is not None and manifest_budget_file_sha != sha:
        raise BudgetError(
            f"{relative}'s commit is {sha} and the RunManifest was stamped with "
            f"{manifest_budget_file_sha}: a budget change mid-campaign "
            f"invalidates the campaign (FR-14.7)")

    # --- check 5: the calibration sample -------------------------------------
    sample = budget.calibration_sample_shas
    if len(sample) != budget.calibration_sample_size:
        raise BudgetError(
            f"{relative} declares calibration_sample_size "
            f"{budget.calibration_sample_size} and carries {len(sample)} "
            f"calibration_sample_shas: the sample is drawn BEFORE the "
            f"registration commit (ADR-D-01, FR-14.3)")
    malformed = sorted(s for s in sample
                       if not (isinstance(s, str) and len(s) == 40
                               and set(s.lower()) <= _HEX40))
    if malformed:
        raise BudgetError(f"{relative}'s calibration_sample_shas {malformed} "
                          f"are not 40 hex characters")
    if len(set(sample)) != len(sample):
        raise BudgetError(f"{relative}'s calibration_sample_shas repeat a seed")
    if exact_pin_shas is not None:
        outside = sorted(set(sample) - set(exact_pin_shas))
        if outside:
            raise BudgetError(
                f"{relative}'s calibration_sample_shas {outside} are not "
                f"exact-pin seeds (ADR-D-01(d))")

    # --- check 6: the pair of prices, the cap, the model ---------------------
    # contract.validate has already refused a bad price, cap, window or model id.
    return {"budget": budget,
            "registration": {"tag": tag, "commit": registered},
            "counters": CounterBlock(
                stage="budget", started=len(_CHECKS), completed=len(_CHECKS),
                failed=0, seconds=time.monotonic() - started_at)}


def _check_frozen_set(repo_root: str, flow_dir: str, tag: str,
                      registered: str) -> None:
    """Refuse a mutator set whose commit the registration tag does not reach."""
    relative = os.path.join(flow_dir, MUTATOR_SET) if flow_dir else MUTATOR_SET
    if not os.path.exists(os.path.join(repo_root, relative)):
        return
    sha, _ = _last_commit(repo_root, relative)
    if sha is None:
        raise BudgetError(f"{relative} is not committed: the mutator set is "
                          f"frozen and versioned before the campaign (FR-05.2)")
    if not _descends_from(repo_root, sha, registered):
        raise BudgetError(
            f"{relative}'s commit {sha} is neither {tag} ({registered}) nor an "
            f"ancestor of it: the mutator set is frozen before the "
            f"pre-registration (FR-05.2, 8.1)")


def snapshot(ledger, arm: Arm, budget: BudgetFile) -> LedgerSnapshot:
    """Return the four numbers a generator may know about its own budget."""
    if arm not in ("seeded", "mutation"):
        raise ContractError("E004_BAD_ENUM",
                            f"snapshot takes an arm, not {arm!r}")
    return LedgerSnapshot(arm=arm, unit="wall_clock_seconds",
                          spent=float(ledger.per_arm_window.get(arm, 0.0)),
                          cap=float(budget.arm_window_seconds))
