"""B8: one local report into CHIA's own phase chain, unchanged (`03-LLD.md` §3.8, F-12).

Three things happen here and nothing else. The refusals of FR-12.4 and FR-12.5
run first, so a class repair is not scoped to never reaches a model. The chain is
then handed a whole `GithubIssue`-shaped object, a pre-written `repro.sh` and the
sixteen-key `cfg` it reads, and is called **inline** by its bare name, because
`run_issue_remote` carries its own `@ChiaFunction(resources={"circt": 1})` and
dispatching it would land the chain on a `circt` worker and defeat the whole
reason `bugloop_repair` exists (§3.8, W2). Last, whatever the outcome, the worker
is restored and every tool binary re-hashed (FR-12.11).

CHIA's own worker modules, `issue_task` and `circt_util`, are shipped to the
repair worker by `bug_loop.py`'s `_PY_MODULES` (§13.1) and are therefore imported
**inside** the node rather than at module scope: this module is also imported on
the head, where CHIA's `examples/` directory is not on `sys.path`. The same lazy
shape is what lets a unit test install a recording stand-in for both.

Deviations from §3.8, each recorded in
`design/reviews/implementation-errata-log.md` rather than absorbed:

  * `local_id`, `input_path` and `created_utc` are keyword-only parameters. The
    identifier is `LOCAL_ID_BASE + <the candidate's rowid>`, which is a query
    against the head's `loop.db` and not something a `repair` worker can run, so
    `mint_local_id` below is the head's half and the node takes the minted value.
    `repro.sh` cannot be written without the probe's own input path, which no
    record in §3.8's signature carries; and `CandidateRecord` has no creation
    timestamp, although the `candidate` TABLE does.
  * FR-12.8's "stops the run" is the caller's. §3.8's `Raises` paragraph closes
    the exception set at `RepairRefused` and `LiveModelRefused`, so a lit run
    that discovered nothing is **recorded** here, `lit_unusable` true and
    `lit_ok` None, and B12 stops on the field.
"""
from __future__ import annotations

import hashlib
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import chia
from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import RunManifest
from circt_bug_loop.llm import MODEL_BACKEND, require_live_model
from circt_bug_loop.store import (CandidateRecord, OracleVerdict, ReducedCase,
                                  RepairResult, Report)

#: §9.4, FR-12.2. `RunManifest.local_id_range` is exactly this pair. The floor is
#: four orders of magnitude beyond `llvm/circt`'s own issue numbers, which are
#: five digits in 2026, so no minted identifier can collide with a real one.
LOCAL_ID_BASE = 900_000_000
LOCAL_ID_MAX = 999_999_999

#: §9.4: CHIA's own two, reused verbatim. `bugloop_repair`'s `--cpus=8` is what
#: bounds the sixteen (`chia:examples/circt_issue_solver/circt_issue_loop.py:77`,
#: `98`).
BUILD_JOBS = 16
PHASE_TIMEOUTS = {"assess": 1800, "repro": 1800, "fix": 7200,
                  "regression": 3600, "writeup": 1200}

#: FR-12.4: only these two enter repair. `fatal_error` is a deliberate refusal
#: path often enough that "what the right answer was" is the argument repair is
#: scoped to avoid, and `differential` is report-only (FR-08.10).
REPAIR_CLASSES = ("crash", "assertion")

#: §3.8's last paragraph: stage 7's tokens are unobservable because CHIA's
#: `_turn` dispatches the turn with `chia_remote`, so the LLM copy that
#: accumulates `_last_metadata` dies on the `llm` worker and `QueryResult`
#: carries no usage. Recorded as a reason, never as a zero.
TOKEN_CAPTURE = "unavailable_remote_dispatch"

#: The six prompt bodies of the `cfg`, mapped to the files they are read from.
#: The key is not the file name for `repro_prompt`, whose file is `reproduce.md`
#: (`chia:examples/circt_issue_solver/circt_issue_loop.py:88`).
PROMPT_FILES = {"system_prompt": "system.md", "assess_prompt": "assess.md",
                "repro_prompt": "reproduce.md", "fix_prompt": "fix.md",
                "regression_prompt": "regression.md",
                "writeup_prompt": "writeup.md"}

#: Every key `run_issue_remote` reads: ten values and the six prompt bodies
#: (§3.8's table, grepped from `issue_task.py` and assembled at
#: `circt_issue_loop.py:84-96`).
CFG_KEYS = frozenset({"tag", "tool_targets", "repro_dir", "repro_path",
                      "require_repro", "backend", "model", "vertex",
                      "build_jobs", "timeouts", *PROMPT_FILES})

#: The CIRCT source tree inside the image, which is where `circt_git_reset` and
#: `circt_ninja_build` work and where the restored binaries are re-hashed.
CIRCT_BUILD_BIN = "/workspace/circt/build/bin"


class RepairRefused(Exception):
    """A candidate refused by class or scope, before the chain is invoked (F-12).

    The caller records `reason` and counts it; nothing has been written and no
    model has been reached.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def issue_solver_dir() -> Path:
    """CHIA's own `examples/circt_issue_solver/`, derived from the imported package.

    `chia.__path__[0]` and never `chia.__file__`, which is None for a namespace
    package, and never a walk up from this file: the flow lives at two different
    depths in two trees (§1.4), so `Path(__file__).parents[2]` is a CHIA checkout
    in one and the team repository's root in the other.

    Returns:
        Path to the directory holding `issue_task.py` and `prompts/`.
    Worker:
        pure; it reads `chia.__path__` and one `os.path.isfile`.
    Raises:
        RuntimeError when the directory is absent, which is what a wheel install
        of CHIA gives: `examples/` ships beside the package only in a checkout.
    """
    directory = Path(chia.__path__[0]).resolve().parent / "examples" / "circt_issue_solver"
    if not (directory / "issue_task.py").is_file():
        raise RuntimeError(
            f"{directory} holds no issue_task.py: stage 7 needs CHIA's own "
            f"example directory, which ships beside the package in a checkout "
            f"and not in a wheel (03-LLD.md 13.1)")
    return directory


def mint_local_id(store, candidate_id: str) -> int:
    """FR-12.2's synthetic identifier: `LOCAL_ID_BASE` plus the candidate's rowid.

    Unique by construction, monotonic, and reproducible from the store, which is
    what makes it a key rather than a nonce. The head's half of B8: a `repair`
    worker holds no `loop.db` handle, so `repair_adapt` takes the minted value.

    Returns:
        int, in `[LOCAL_ID_BASE, LOCAL_ID_MAX]`.
    Worker:
        head; one `{"num_cpus": 0.1}` query through the store.
    Raises:
        LookupError when no candidate row carries *candidate_id*; OverflowError
        when the range is exhausted, which is a hundred million candidates and
        is raised rather than silently colliding with the tracker.
    """
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
    """Build the `GithubIssue`-shaped object CHIA's chain and `db` both read.

    Every one of `state_def.GithubIssue`'s eleven required fields is populated;
    `comments` is left at its default empty list, which is the only field with a
    default and the only one no CHIA caller reads for this flow. `url` is a
    `local://` URI and deliberately not an `https://` one: it is written into
    CHIA's `issues.db` and into artefacts, and a plausible-looking GitHub URL for
    an issue that does not exist is the kind of thing that later gets pasted
    somewhere.

    Returns:
        chia.github.state_def.GithubIssue.
    Worker:
        pure but for one read of the rendered report.
    Raises:
        OSError when `report.path` cannot be read.
    """
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


#: FR-12.3's script. The polarity is the INVERSE of §10.2's interestingness
#: test, and it is not the naive one: exit 0 iff the run terminates without a
#: crash signal, without an assertion or `UNREACHABLE executed` message and
#: without an `LLVM ERROR:` abort, WHATEVER the tool's own exit status, so that a
#: fix which turns a crash into a proper diagnostic scores as fixed.
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
    """Render FR-12.3's `repro.sh` for one recorded firing.

    The tool and its arguments come from `OracleVerdict.repro_command`, which B3
    built as `shlex.join([binary_path, *argv])` with the `prlimit` prefix already
    removed; *input_path* is the probe's own input, dropped from the arguments so
    that the reduced case beside the script takes its place, which is
    `probe_task._test_args`' rule and `circt-reduce`'s own calling convention.

    Returns:
        the script text. The caller writes it, because `circt_write_files` is
        what chmods it 0755 (`chia:examples/circt_issue_solver/circt_util.py:107-123`).
    Worker:
        pure; it renders a string and runs nothing.
    Raises:
        ValueError on an empty `repro_command`, which would leave the script with
        no tool to run.
    """
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
    """Assemble every one of the sixteen keys `run_issue_remote` reads (§3.8).

    The backend and the model id are one recorded pair,
    `RunManifest.model_ids["repair_adapt"]`, spelled `"<backend>:<model id>"`,
    which on a default run is `vertex:gemini-3.8-flash`; splitting it here is
    what keeps `cfg["backend"]` and the ledger's `stages_metered["stage_7"]`
    from ever disagreeing. `tag` is `candidate.run_commit` and never
    `manifest.run_commit[0]`, which in calibration mode is an arbitrary sampled
    seed's (K14, FR-12.6). `repro_dir` is under the artefact root and OUTSIDE
    `/workspace/circt`, which the chain's own `git clean -fd` would delete (K9).

    Returns:
        dict whose key set is exactly `CFG_KEYS`.
    Worker:
        pure but for six prompt reads from CHIA's own directory, which is what
        makes FR-12.9's byte comparison one of the file actually passed.
    Raises:
        RuntimeError from `issue_solver_dir`; KeyError when the manifest carries
        no `repair_adapt` model id; OSError from a prompt read.
    """
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
        # Read only on the `opencode` backend (`circt_issue_loop.py:71-72`). The
        # `vertex` arm does not read it at all: express mode takes an API key and
        # no project and no location, and the branch nulls both.
        "vertex": {"project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
                   "location": "global"},
        "build_jobs": BUILD_JOBS,
        "timeouts": dict(PHASE_TIMEOUTS),
    }
    cfg.update({key: (prompts / name).read_text(encoding="utf-8")
                for key, name in PROMPT_FILES.items()})
    return cfg


def failing_phase(logs: dict) -> Optional[str]:
    """The first phase CHIA's chain recorded as unsuccessful, or None (FR-12.7).

    `logs` is CHIA's own per-phase dict, insertion-ordered by the order the
    phases ran (`chia:examples/circt_issue_solver/issue_task.py:125-137`).

    Returns:
        the phase name, or None when every phase that ran succeeded.
    Worker:
        pure.
    Raises:
        nothing.
    """
    for phase, entry in (logs or {}).items():
        if not (entry or {}).get("success"):
            return phase
    return None


def stage7_observed(elapsed: float) -> dict:
    """The stage-7 `LedgerEntry.observed`, whose three money fields are NULL (§3.8).

    Null and never zero: zero is a number a reader will add up, and the counts
    are not merely zero but unobserved. The reason lives on `RepairResult`, not
    here: `_DICT_KEYS[("LedgerEntry", "observed")]` is exactly these four keys
    and a fifth fails validation as loudly as a missing one (§2.2, §2.6).

    Returns:
        {"cpu_seconds": float, "tokens_in": None, "tokens_out": None,
         "cost_usd": None}.
    Worker:
        pure.
    Raises:
        nothing.
    """
    return {"cpu_seconds": elapsed, "tokens_in": None, "tokens_out": None,
            "cost_usd": None}


def _sha256(path: str) -> str:
    """SHA-256 of one file, hex, streamed."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@ChiaFunction(resources={"repair": 1}, max_retries=0)
def repair_adapt(report: Report, candidate: CandidateRecord, reduced: ReducedCase,
                 verdict: OracleVerdict, manifest: RunManifest, cfg: dict, *,
                 local_id: int, input_path: str, created_utc: Optional[str] = None,
                 issue_solver: Optional[Path] = None,
                 bin_dir: str = CIRCT_BUILD_BIN) -> RepairResult:
    """Present one local report to CHIA's chain, then restore the worker.

    Returns:
        RepairResult, for every one of CHIA's six statuses, with the failing
        phase named, plus the post-attempt restore result.
    Worker:
        {"repair": 1} - its own worker type, because the chain rebuilds with the
        agent's diff applied and returns without restoring (FR-12.11).
    Raises:
        RepairRefused(reason) for a candidate refused by class or scope, and for
        a run started with --no-repair, before the chain is invoked at all. The
        caller records the reason and counts it.
        LiveModelRefused when the interlock of 3.5.1 is not set, or when the
        repair backend is vertex and GEMINI_API_KEY is unusable. Checked here
        because CHIA's _turn builds its own backend and cannot carry the loop's
        refusal (3.5.1, 2026-09-14). The caller stops the run.
    """
    if not cfg.get("repair_enabled", True):
        raise RepairRefused("repair_disabled")
    if candidate.oracle_class not in REPAIR_CLASSES:
        raise RepairRefused(f"oracle_class_{candidate.oracle_class}")
    if candidate.out_of_scope_root:
        raise RepairRefused("out_of_scope_root")

    # The interlock, unconditionally and BEFORE the cfg is built: CHIA's _turn
    # builds its own backend inside CHIA's file, which cannot carry the loop's
    # refusal, so stage 7 would otherwise be the one path to a model that the
    # gate of 3.5.1 does not cover (3.8, T-U-layout-08). It is `llm.py`'s and is
    # imported at module scope: that module is neither half (architect decision
    # 3), so reaching it crosses no seam.
    require_live_model(
        f"stage 7 repair of {candidate.candidate_id}",
        need_key=(cfg["repair_backend"] == MODEL_BACKEND))

    import circt_util

    solver = issue_solver or issue_solver_dir()
    chain_cfg = build_cfg(candidate, manifest, local_id=local_id,
                          issue_solver=solver)
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

    # Measured rather than assumed (FR-12.3, W3): the reproduce turn's prompt
    # tells the agent to write <repro_path> itself and the prompt may not be
    # edited, so whether our script survived is reported per attempt.
    before = _sha256(chain_cfg["repro_path"])
    Path(repro_dir, "repro.sh.sha256.before").write_text(before + "\n", encoding="utf-8")

    issue = as_github_issue(report, candidate, local_id,
                            created_utc or datetime.now(timezone.utc).isoformat())
    issue_md = issue.to_markdown()

    from issue_task import run_issue_remote

    try:
        result = run_issue_remote(issue_md, local_id, chain_cfg)
    finally:
        after = _sha256(chain_cfg["repro_path"]) if os.path.isfile(
            chain_cfg["repro_path"]) else ""
        Path(repro_dir, "repro.sh.sha256.after").write_text(after + "\n",
                                                            encoding="utf-8")
        restore = _restore(candidate, manifest, chain_cfg, circt_util, bin_dir)

    return _as_repair_result(result, candidate, local_id, repro_dir,
                             chain_cfg["backend"], before != after, restore, solver)


def _restore(candidate: CandidateRecord, manifest: RunManifest, chain_cfg: dict,
             circt_util, bin_dir: str) -> dict:
    """FR-12.11's restore: reset, rebuild, and RE-HASH every tool binary.

    A successful `ninja` is not evidence of bit-identity: the `ImageSpec` hashes
    are computed from a freshly started container (§5.2) while the restore
    rebuilds locally, so whether a revert-and-rebuild reproduces the published
    binaries byte for byte is `[UNVERIFIED]` (§15). Doing the comparison is what
    makes the answer a recorded fact rather than an assumption.
    """
    targets = tuple(manifest.image_spec["targets"])
    reset = circt_util.circt_git_reset(candidate.run_commit)
    build = circt_util.circt_ninja_build(targets, num_cpus=chain_cfg["build_jobs"])
    after, unreadable = {}, []
    for tool in targets:
        try:
            after[tool] = _sha256(os.path.join(bin_dir, tool))
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
                      restore: dict, solver: Path) -> RepairResult:
    """Map CHIA's own result dict onto `RepairResult`, unchanged in shape (FR-12.7).

    FR-12.8's erratum is applied here and nowhere else: a `lit` run reporting
    zero passed and zero failed over a non-empty path list did not discover a
    suite, and an absent gate is not a red one. Such an attempt records
    `lit_unusable` with `lit_ok` NULL, so no patch can be attached to it and no
    red gate is charged to the agent's diff; B12 stops the run on the field,
    naming FR-03.17.
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
        chia_artifact_dir=str(solver / "issue_logs" / f"issue_{local_id}"),
        repro_dir=repro_dir,
        repro_overwritten=overwritten,
        restore_ok=bool(restore["reset_ok"] and restore["build_ok"]
                        and restore["hashes_match"]),
        restore_hashes_match=bool(restore["hashes_match"]),
        restore_log=restore["log"],
        backend=backend,
        token_capture=TOKEN_CAPTURE,
    )
