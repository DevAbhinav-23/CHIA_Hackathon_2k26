"""B8: one local report into CHIA's own phase chain, unchanged (`03-LLD.md` §3.8)."""
from __future__ import annotations

import hashlib
import os
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Optional

import chia
from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import CounterBlock, RunManifest
from circt_bug_loop.llm import MODEL_BACKEND, require_live_model
from circt_bug_loop.store import (CandidateRecord, OracleVerdict, ReducedCase,
                                  RepairResult, Report, sha256_file)

#: §9.4, FR-12.2.
LOCAL_ID_BASE = 900_000_000
LOCAL_ID_MAX = 999_999_999

#: §9.4 took CHIA's own two verbatim.
BUILD_JOBS = 4
PHASE_TIMEOUTS = {"assess": 1800, "repro": 1800, "fix": 7200,
                  "regression": 3600, "writeup": 1200}

#: FR-12.4: only these two enter repair.
REPAIR_CLASSES = ("crash", "assertion")

#: §3.8's last paragraph.
TOKEN_CAPTURE = "unavailable_remote_dispatch"

#: The six prompt bodies of the `cfg`, mapped to the files they are read from.
PROMPT_FILES = {"system_prompt": "system.md", "assess_prompt": "assess.md",
                "repro_prompt": "reproduce.md", "fix_prompt": "fix.md",
                "regression_prompt": "regression.md",
                "writeup_prompt": "writeup.md"}

#: Every key `run_issue_remote` reads.
CFG_KEYS = frozenset({"tag", "tool_targets", "repro_dir", "repro_path",
                      "require_repro", "backend", "model", "vertex",
                      "build_jobs", "timeouts", *PROMPT_FILES})

#: The CIRCT source tree inside the image.
CIRCT_BUILD_BIN = "/workspace/circt/build/bin"


class RepairRefused(Exception):
    """A candidate refused by class or scope, before the chain is invoked (F-12)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def issue_solver_dir() -> Path:
    """CHIA's own `examples/circt_issue_solver/`, derived from the imported package."""
    directory = Path(chia.__path__[0]).resolve().parent / "examples" / "circt_issue_solver"
    if not (directory / "issue_task.py").is_file():
        raise RuntimeError(
            f"{directory} holds no issue_task.py: stage 7 needs CHIA's own "
            f"example directory, which ships beside the package in a checkout "
            f"and not in a wheel (03-LLD.md 13.1)")
    return directory


def mint_local_id(store, candidate_id: str) -> int:
    """FR-12.2's synthetic identifier: `LOCAL_ID_BASE` plus the candidate's rowid."""
    row = store.query_one("SELECT rowid AS rid FROM candidate WHERE candidate_id = ?",
                          (candidate_id,))
    if row is None:
        raise LookupError(f"no candidate row for {candidate_id!r}")
    local_id = LOCAL_ID_BASE + int(row["rid"])
    if local_id > LOCAL_ID_MAX:
        raise OverflowError(
            f"local id {local_id} is past LOCAL_ID_MAX {LOCAL_ID_MAX}: the "
            f"declared range of FR-12.2 is exhausted")
    return local_id


def as_github_issue(report: Report, candidate: CandidateRecord, local_id: int,
                    created_utc: str) -> "object":
    """Build the `GithubIssue`-shaped object CHIA's chain and `db` both read."""
    from chia.github.state_def import GithubIssue

    return GithubIssue(
        number=local_id,
        title=report.title,
        state="open",
        author="circt_bug_loop",
        created_at=created_utc,
        updated_at=created_utc,
        closed_at=None,
        body=Path(report.path).read_text(encoding="utf-8"),
        labels=["circt-bug-loop", f"arm:{candidate.arm}"],
        url=f"local://circt_bug_loop/{candidate.run_manifest_id}/{candidate.candidate_id}",
        is_pull_request=False,
    )


#: FR-12.3's script.
_REPRO_TEMPLATE = """#!/bin/sh
# repro.sh for one recorded CIRCT failure, PRE-WRITTEN by the closed bug loop.
# Your job in the reproduce phase is to CONFIRM this, not to invent it.
#
# Contract (FR-12.3), which is the INVERSE of the interestingness script of
# 03-LLD.md section 10.2: exit 0 IFF the tool run terminates
#   * without a crash signal,
#   * without an assertion failure or an "UNREACHABLE executed" message,
#   * without an "LLVM ERROR:" abort,
# REGARDLESS of the tool's own exit status. A fix that turns this crash into an
# ordinary diagnostic therefore scores the bug as FIXED, which is the case the
# naive "exit_code == 0" script gets wrong.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ERR=$(mktemp)
trap 'rm -f "$ERR"' EXIT

@TOOL@ @ARGS@ "$HERE/@CASE@" >/dev/null 2>"$ERR"
RC=$?
cat "$ERR" >&2

# A death by signal is what the shell reports as 128+N.
[ "$RC" -le 128 ] || exit 1
grep -qF ': Assertion `' "$ERR" && exit 1
grep -q '^UNREACHABLE executed' "$ERR" && exit 1
grep -q '^LLVM ERROR:' "$ERR" && exit 1
exit 0
"""


def repro_script(verdict: OracleVerdict, *, input_path: str, case_name: str) -> str:
    """Render FR-12.3's `repro.sh` for one recorded firing."""
    argv = shlex.split(verdict.repro_command)
    if not argv:
        raise ValueError("OracleVerdict.repro_command is empty: no tool to run")
    args = [token for token in argv[1:] if token != input_path]
    return (_REPRO_TEMPLATE
            .replace("@TOOL@", shlex.quote(argv[0]))
            .replace("@ARGS@", " ".join(shlex.quote(token) for token in args))
            .replace("@CASE@", case_name))


def build_cfg(candidate: CandidateRecord, manifest: RunManifest, *,
              local_id: int, issue_solver: Optional[Path] = None) -> dict:
    """Assemble every one of the sixteen keys `run_issue_remote` reads (§3.8)."""
    prompts = (issue_solver or issue_solver_dir()) / "prompts"
    backend, _, model = manifest.model_ids["repair_adapt"].partition(":")
    repro_dir = os.path.join(manifest.artefact_root, manifest.run_manifest_id,
                             "repair", str(local_id))
    cfg = {
        "tag": candidate.run_commit,
        "tool_targets": tuple(manifest.image_spec["targets"]),
        "repro_dir": repro_dir,
        "repro_path": os.path.join(repro_dir, "repro.sh"),
        "require_repro": True,
        "backend": backend,
        "model": model,
        # Read only on the `opencode` backend (`circt_issue_loop.py:71-72`).
        "vertex": {"project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
                   "location": "global"},
        "build_jobs": BUILD_JOBS,
        "timeouts": dict(PHASE_TIMEOUTS),
    }
    cfg.update({key: (prompts / name).read_text(encoding="utf-8")
                for key, name in PROMPT_FILES.items()})
    return cfg


def failing_phase(logs: dict) -> Optional[str]:
    """The first phase CHIA's chain recorded as unsuccessful, or None (FR-12.7)."""
    for phase, entry in (logs or {}).items():
        if not (entry or {}).get("success"):
            return phase
    return None


def stage7_observed(elapsed: float) -> dict:
    """The stage-7 `LedgerEntry.observed`, whose three money fields are NULL (§3.8)."""
    return {"cpu_seconds": elapsed, "tokens_in": None, "tokens_out": None,
            "cost_usd": None, "authorised_usd": None, "ceiling_usd": None,
            "billed_usd": None, "calls": None}


@ChiaFunction(resources={"repair": 1}, max_retries=0)
def repair_adapt(report: Report, candidate: CandidateRecord, reduced: ReducedCase,
                 verdict: OracleVerdict, manifest: RunManifest, cfg: dict, *,
                 local_id: int, input_path: str, created_utc: Optional[str] = None,
                 chia_artifact_dir: str = "",
                 bin_dir: str = CIRCT_BUILD_BIN,
                 env: Optional[Mapping[str, str]] = None) -> dict:
    """Present one local report to CHIA's chain, then restore the worker (FR-12.7).

    Returns:
        {"result": RepairResult, "counters": CounterBlock}, one attempt at stage_7.
    Worker:
        {"repair": 1}, because the chain rebuilds with the agent's diff applied.
    Raises:
        RepairRefused for a candidate refused by class or scope, ValueError for a
        *cfg* `run_issue_remote` cannot read, LiveModelRefused for an unset interlock.
    """
    started_at = time.monotonic()
    if not cfg.get("repair_enabled", True):
        raise RepairRefused("repair_disabled")
    if candidate.oracle_class not in REPAIR_CLASSES:
        raise RepairRefused(f"oracle_class_{candidate.oracle_class}")
    if candidate.out_of_scope_root:
        raise RepairRefused("out_of_scope_root")

    # The interlock, unconditionally and BEFORE the chain is reached.
    require_live_model(
        f"stage 7 repair of {candidate.candidate_id}",
        need_key=(cfg["repair_backend"] == MODEL_BACKEND), env=env)

    import circt_util

    chain_cfg = {key: value for key, value in cfg.items() if key in CFG_KEYS}
    missing = CFG_KEYS - set(chain_cfg)
    if missing:
        raise ValueError(
            f"cfg is missing {sorted(missing)}: `run_issue_remote` reads all "
            f"{len(CFG_KEYS)} keys and `repair_adapter.build_cfg` on the head "
            f"is what assembles them (K3, K6)")
    if chain_cfg["backend"] != cfg["repair_backend"]:
        raise ValueError(
            f"RunManifest.model_ids['repair_adapt'] names backend "
            f"{chain_cfg['backend']!r} and cfg['repair_backend'] is "
            f"{cfg['repair_backend']!r}: stages_metered['stage_7'] would be a "
            f"false statement (FR-14.8)")

    repro_dir = chain_cfg["repro_dir"]
    case_name = f"case{os.path.splitext(reduced.path)[1]}"
    script = repro_script(verdict, input_path=input_path, case_name=case_name)
    circt_util.circt_write_files(
        {"repro.sh": script,
         case_name: Path(reduced.path).read_text(encoding="utf-8")}, repro_dir)

    # Measured rather than assumed (FR-12.3).
    before = sha256_file(chain_cfg["repro_path"])
    Path(repro_dir, "repro.sh.sha256.before").write_text(before + "\n", encoding="utf-8")

    issue = as_github_issue(report, candidate, local_id,
                            created_utc or datetime.now(timezone.utc).isoformat())
    issue_md = issue.to_markdown()

    from issue_task import run_issue_remote

    try:
        result = run_issue_remote(issue_md, local_id, chain_cfg)
    finally:
        after = sha256_file(chain_cfg["repro_path"]) if os.path.isfile(
            chain_cfg["repro_path"]) else ""
        Path(repro_dir, "repro.sh.sha256.after").write_text(after + "\n",
                                                            encoding="utf-8")
        restore = _restore(candidate, manifest, chain_cfg, circt_util, bin_dir)

    attempt = _as_repair_result(result, candidate, local_id, repro_dir,
                                chain_cfg["backend"], before != after, restore,
                                chia_artifact_dir)
    fixed = int(attempt.status == "fixed")
    return {"result": attempt,
            "counters": CounterBlock(
                stage="stage_7", started=1, completed=fixed, failed=1 - fixed,
                seconds=time.monotonic() - started_at)}


def _restore(candidate: CandidateRecord, manifest: RunManifest, chain_cfg: dict,
             circt_util, bin_dir: str) -> dict:
    """FR-12.11's restore: reset, rebuild, and RE-HASH every tool binary."""
    targets = tuple(manifest.image_spec["targets"])
    reset = circt_util.circt_git_reset(candidate.run_commit)
    build = circt_util.circt_ninja_build(targets, num_cpus=chain_cfg["build_jobs"])
    after, unreadable = {}, []
    for tool in targets:
        try:
            after[tool] = sha256_file(os.path.join(bin_dir, tool))
        except OSError as error:
            unreadable.append(f"{tool}: {error}")
    expected = {tool: manifest.image_spec["tool_hashes"].get(tool) for tool in targets}
    hashes_match = not unreadable and after == expected
    log = "\n".join(
        [f"git reset --hard {candidate.run_commit}: "
         f"{'ok' if reset.get('success') else 'FAILED'}",
         reset.get("log", ""),
         f"ninja {' '.join(targets)}: {'ok' if build.get('success') else 'FAILED'}",
         build.get("log_tail", build.get("log", "")),
         f"re-hash against ImageSpec.tool_hashes: "
         f"{'match' if hashes_match else 'MISMATCH'}",
         *unreadable,
         *[f"{tool}: expected {expected[tool]} got {after.get(tool)}"
           for tool in sorted(targets) if after.get(tool) != expected[tool]]]).strip()
    return {"reset_ok": bool(reset.get("success")),
            "build_ok": bool(build.get("success")),
            "hashes_match": bool(hashes_match), "log": log}


def _as_repair_result(result: dict, candidate: CandidateRecord, local_id: int,
                      repro_dir: str, backend: str, overwritten: bool,
                      restore: dict, chia_artifact_dir: str) -> RepairResult:
    """Map CHIA's own result dict onto `RepairResult`, unchanged in shape (FR-12.7).

    A lit run that discovered no suite records `lit_unusable` with `lit_ok` NULL,
    and B12 stops the run on the field, naming FR-03.17.
    """
    passed, failed = result.get("lit_passed"), result.get("lit_failed")
    unusable = bool(result.get("test_paths") and passed == 0 and failed == 0)
    diff_path = None
    if result.get("diff"):
        diff_path = os.path.join(repro_dir, "fix.diff")
        Path(diff_path).write_text(result["diff"], encoding="utf-8")
    return RepairResult(
        candidate_id=candidate.candidate_id,
        local_id=local_id,
        status=result["status"],
        failing_phase=failing_phase(result.get("logs")),
        reproduced=result.get("reproduced"),
        build_ok=result.get("build_ok"),
        fixed=result.get("fixed"),
        lit_ok=None if unusable else result.get("lit_ok"),
        lit_unusable=unusable,
        lit_passed=passed,
        lit_failed=failed,
        lit_failures=list(result.get("lit_failures") or []),
        diff_path=diff_path,
        diff_added=result.get("added"),
        diff_removed=result.get("removed"),
        chia_artifact_dir=chia_artifact_dir,
        repro_dir=repro_dir,
        repro_overwritten=overwritten,
        restore_ok=bool(restore["reset_ok"] and restore["build_ok"]
                        and restore["hashes_match"]),
        restore_hashes_match=bool(restore["hashes_match"]),
        restore_log=restore["log"],
        backend=backend,
        token_capture=TOKEN_CAPTURE,
    )
