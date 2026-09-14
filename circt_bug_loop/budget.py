"""budget.yaml: load it, enforce the pre-registration, hand out snapshots.

A6a. Head-side and pure but for one `git` read (03-LLD.md 3.11). The file this
module loads is the campaign's pre-registration, and every rule here is about
refusing a file that could have been chosen after the data existed. WHICH commit
registers it changed at W-12: it is the commit an annotated `registration/*` tag
names, not the first commit that ever landed the file (`REGISTRATION_TAGS`
below, and errata rows 30 and 31). `budget_file_sha` is unchanged and is still
the run's identity (G-32, FR-14.3).

03-LLD.md 9.2's SIX checks, in order, each of which stops a run:

  1. committed, and its commit earlier than the run's start (FR-14.2), the
     working tree still equal to that commit, and - for a campaign - registered
     by a tag the file's own commit is an ancestor of (FR-14.3, FR-14.7);
  2. complete and closed: every key of 9.1, no other, every type as declared;
  3. equal on the unit and on both safety caps, which is structural: there is
     one value per key and arm_order names each arm exactly once (FR-14.5);
  4. unchanged mid-campaign: the SHA still equal to the manifest's (FR-14.7);
  5. the calibration sample is drawn, and is the declared size (ADR-D-01);
  6. both prices present, positive and finite; the spend cap positive; the model
     id non-blank (NFR-08).

Check 1 also carries 8.1's frozen-set rule, which is FR-05.2's and not one of
the six: a mutator set the registration tag cannot reach would be a campaign
parameter chosen after the registration.
"""
from __future__ import annotations

import dataclasses
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import (Arm, BudgetFile, ContractError,
                                            CounterBlock,
                                            LedgerSnapshot, validate)

#: The committed pre-registration, beside this module in the flow directory
#: (03-LLD.md 1.1). Derived from this file's own directory and no further:
#: 1.4 forbids a longer walk, the flow living at two depths in two trees.
BUDGET_YAML = str(Path(__file__).resolve().parent / "budget.yaml")

#: 8.1 rule 2's file, relative to the flow directory.
MUTATOR_SET = os.path.join("mutators", "set_v1.json")

#: THE PRE-REGISTRATION, since W-12 (architect decision, 2026-09-16): an
#: ANNOTATED git tag `registration/<campaign-id>` on the commit that lands the
#: FINAL budget.yaml, and not the first commit that ever touched the file.
#: 8.3 step 1 and 9.2 check 1 both read "the commit that lands budget.yaml",
#: which made W-06's own landing commit the registration of a campaign that has
#: not been registered yet, refused every later edit of the file, and stopped
#: A7 - whose whole job is to run BEFORE the registration - from running at all.
#: A tag is the one thing an operator can place deliberately, after the file is
#: final; the newest tag wins, so a re-registration adds a tag rather than
#: rewriting one. Erratum rows 30 and 31.
REGISTRATION_TAGS = "refs/tags/registration/*"

#: 9.2's six, named so `len(_CHECKS) == 6` is assertable. The count was five
#: before 2026-09-14 and six after; 9.2's own heading still says five.
_CHECKS = ("committed_and_earlier", "complete_and_closed", "equal_on_the_unit",
           "unchanged_mid_campaign", "calibration_sample", "prices_and_caps")

#: Every key 9.1 declares: BudgetFile's fields less the two the file does not
#: carry. contract_version is the package's and budget_file_sha is check 1's
#: output, so a file carrying either would be declaring what it cannot know.
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
    """Raised by load_budget. The message names the offending key or commit."""


def _git(repo_root: str, *args: str) -> str:
    """Run one read-only `git` command in *repo_root* and return its stdout.

    Raises:
        BudgetError when git itself fails, naming the command and its stderr.
    """
    done = subprocess.run(("git", "-C", repo_root, *args), capture_output=True,
                          text=True)
    if done.returncode != 0:
        raise BudgetError(f"git {' '.join(args)} in {repo_root!r} failed: "
                          f"{done.stderr.strip()}")
    return done.stdout


def _last_commit(repo_root: str, relative_path: str) -> tuple:
    """Return (sha, committed datetime) of the last commit touching *relative_path*.

    (None, None) when the path has never been committed, which is what makes
    FR-14.2's refusal a refusal and not a crash.
    """
    line = _git(repo_root, "log", "-1", f"--format={_GIT_FORMAT}", "--",
                relative_path).strip()
    if not line:
        return (None, None)
    sha, _, when = line.partition("\t")
    return (sha, _iso(when))


def registration(repo_root: str) -> tuple:
    """Return (tag, commit) of the newest `registration/*` tag, or ("", "").

    ("", "") is "this repository holds no pre-registration". That is a STATE and
    not a failure: A7 synthesises only in it (8.1 rule 3), a dry run and a
    `--generator recorded` run read the budget file in it, and only a campaign
    is refused (FR-14.3).

    Returns:
        tuple[str, str], the short tag name and the commit it names. An
        annotated tag is dereferenced, so the second member is a commit and
        never the tag object.
    Worker:
        none; head-side, two `git` reads and no write.
    Raises:
        BudgetError when `git` itself fails.
    """
    tag = _git(repo_root, "for-each-ref", "--sort=-creatordate", "--count=1",
               "--format=%(refname:short)", REGISTRATION_TAGS).strip()
    if not tag:
        return ("", "")
    return (tag, _git(repo_root, "rev-parse", f"{tag}^{{commit}}").strip())


def _descends_from(repo_root: str, ancestor: str, descendant: str) -> bool:
    """True when *ancestor* IS *descendant* or one of its ancestors.

    ANCESTRY and not a comparison of two commit dates, which is the second half
    of W-12's decision: `%cI` is metadata a rebase rewrites and a skewed clock
    can order either way, while "the set's commit is reachable from the
    registration tag" is a property of the history the tag actually names.
    """
    done = subprocess.run(("git", "-C", repo_root, "merge-base", "--is-ancestor",
                           ancestor, descendant), capture_output=True)
    if done.returncode not in (0, 1):       # 1 is the answer "no", not a failure
        raise BudgetError(
            f"git merge-base --is-ancestor {ancestor} {descendant} in "
            f"{repo_root!r} failed: "
            f"{done.stderr.decode('utf-8', errors='backslashreplace').strip()}")
    return done.returncode == 0


def _iso(text: str) -> datetime:
    """Parse an ISO 8601 instant, including the trailing Z git writes for UTC.

    Python 3.10's fromisoformat refuses 'Z' (3.11 accepts it), and `git log
    --format=%cI` emits exactly that for a commit made at offset zero, which is
    what every test repository here and every CI checkout produces.
    """
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

    *path* is the file, *repo_root* the repository whose history registers it.
    The three keyword arguments are the parts of checks 1, 4 and 5 that need a
    fact from outside the file: the run's start instant (now, by default), the
    SHA the RunManifest was stamped with, and the exact-pin seed set the
    calibration sample must be drawn from. Each is optional, and each check
    that has no fact to compare against is the driver's pre-flight to make
    (13.1's checks 1 and 3).

    *campaign* is the caller saying that this run is one whose result will be
    reported, and it is the ONLY thing that makes an absent `registration/*`
    tag fatal (W-12). It is false by default because the callers that read the
    file outside a campaign - `--draw-calibration`, which produces a number the
    registration is then made FROM, a dry run and a `--generator recorded` run -
    outnumber the one that starts a campaign, and that one names itself:
    `bug_loop.check_01_budget_registered` passes it.

    Returns:
        {"budget": BudgetFile, "counters": CounterBlock,
         "registration": {"tag": str, "commit": str}}, the BudgetFile with
        budget_file_sha set to the commit that landed the file, which stays the
        run's identity (FR-14.3, G-32); the registration pair is empty when the
        repository holds no tag. The counters count 9.2's six checks at stage
        "budget", which 3.11 requires of every node of 3.2.
    Worker:
        none; head-side, one subprocess per `git` read.
    Raises:
        BudgetError on any of the six checks, naming the key, the commit or the
        pair of timestamps; ContractError (E002, E003, E004) from
        contract.validate on a key whose type or value the seam refuses;
        OSError when *path* cannot be read.
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
    # Structural: one value per key, applying to both arms by construction. The
    # one thing that can still be wrong is the arm list itself.
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
    # contract.validate has already refused a non-positive or non-finite price,
    # spend cap or window and a blank model id (2.4's _budget_conditionals),
    # which is check 6 discharged at the seam so both halves get the same rule.
    return {"budget": budget,
            "registration": {"tag": tag, "commit": registered},
            "counters": CounterBlock(
                stage="budget", started=len(_CHECKS), completed=len(_CHECKS),
                failed=0, seconds=time.monotonic() - started_at)}


def _check_frozen_set(repo_root: str, flow_dir: str, tag: str,
                      registered: str) -> None:
    """Refuse a mutator set whose commit the registration tag does not reach.

    FR-05.2 and 8.1 rule 2, as amended by W-12: "before the pre-registration" is
    ancestry under the tag and no longer a comparison of two commit dates. The
    set is checked only where it exists - before A7 freezes one there is nothing
    to place in the history, and 13.1's pre-flight check 2 owns the harder rule
    that the campaign must have one - and only where a tag exists, an
    unregistered repository having nothing to be earlier than.
    """
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
    """Return the four numbers a generator may know about its own budget.

    Four fields and no fifth: the generator cannot reach BudgetLedger, cannot
    read the other arm's spend, cannot read spend_usd, and cannot read any
    result field (FR-16.4, 2.5).

    Returns:
        LedgerSnapshot(arm, unit, spent, cap).
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ContractError (E004) when *arm* is not one of the two arms; KeyError
        never, an arm with no window entry yet having spent nothing.
    """
    if arm not in ("seeded", "mutation"):
        raise ContractError("E004_BAD_ENUM",
                            f"snapshot takes an arm, not {arm!r}")
    return LedgerSnapshot(arm=arm, unit="wall_clock_seconds",
                          spent=float(ledger.per_arm_window.get(arm, 0.0)),
                          cap=float(budget.arm_window_seconds))
