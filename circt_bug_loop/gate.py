"""B9a and B9b: the four mechanical questions, asked in order (`03-LLD.md` §3.9)."""
from __future__ import annotations

import json
import os
import shlex
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.circt_core import CIRCT_ROOTS, circt_exec_probe
from circt_bug_loop.contract.schema import CounterBlock, RunManifest
from circt_bug_loop.probe_task import (PROBE_NOFILE, BinaryMismatch, _last_pass,
                                       _sha256, classify_build, oracle_primary)
from circt_bug_loop.store import (BuildResult, CandidateRecord, DedupVerdict,
                                  GateDecision, LoopStore, ReducedCase,
                                  RepairResult, validate_candidate)
from circt_bug_loop.triage_task import compute_fingerprint

#: §4.8's three parse-and-verify commands, by the reduced case's own extension.
VALIDITY_COMMANDS = {
    ".fir": ("firtool", ["--parse-only"]),
    ".sv": ("circt-verilog", ["--import-only"]),
}
DEFAULT_VALIDITY_COMMAND = ("circt-opt", ["-o", "/dev/null"])

#: FR-13.15's second conjunct.
PARSER_DIRS = ("lib/Parser/", "lib/AsmParser/", "tools/circt-translate/")

#: FR-18.6's table, as the mapping it is.
TAXONOMY = {
    (1, "did_not_reproduce"): "unreproducible",
    (2, "reduced_false"): "not_minimal",
    (2, "reduction_changed_failure"): "not_minimal",
    (2, "no_reducer"): "not_minimal",
    (2, "not_fixpoint"): "not_minimal",
    (3, "invalid_input"): "invalid_input",
    (4, "duplicate_of_candidate"): "duplicate",
    (4, "known_open_issue"): "duplicate",
    (4, "known_closed_issue"): "duplicate",
    (4, "fixed_post_pin"): "duplicate",
    (4, "dedup_unavailable"): "undecided",
    (4, "dedup_basis_insufficient"): "undecided",
}

#: The fifteen answer keys of `02-HLD.md` §2.11.
ANSWER_KEYS = ("q1_reproduce", "q1_original_worker", "q1_rerun_worker",
               "q1_original_pid", "q1_rerun_pid", "q1_same_worker",
               "q2_minimal", "q2_reason", "q3_valid", "q3_validity_basis",
               "q3_after_parse", "q3_exit_status", "q3_stderr_path",
               "q4_new", "q4_reason")


def answers(decision: GateDecision) -> dict:
    """The fifteen recorded answers of one decision, for `answers_json` (§6.2)."""
    return {key: getattr(decision, key) for key in ANSWER_KEYS}


def validity_command(case_path: str) -> tuple:
    """§4.8's command for one reduced case, chosen by its extension alone."""
    return VALIDITY_COMMANDS.get(os.path.splitext(case_path)[1].lower(),
                                 DEFAULT_VALIDITY_COMMAND)


def in_parser(path: str) -> bool:
    """Whether a frame's file is the parser's own (FR-13.15's second conjunct)."""
    normalised = path.replace(os.sep, "/")
    return (any(directory in normalised for directory in PARSER_DIRS)
            or "Parser" in os.path.basename(normalised))


def live_circt_nodes() -> list:
    """Every alive Ray node holding the `circt` resource, as CHIA enumerates them."""
    import ray

    if not ray.is_initialized():
        return []
    return [node["NodeID"] for node in ray.nodes()
            if node.get("Alive") and "circt" in (node.get("Resources") or {})]


def preferred_node(node_ids: list, original: Optional[str]) -> Optional[str]:
    """The node FR-13.2 prefers for the re-run: any live `circt` node but *original*."""
    return next((node for node in node_ids if node != original), None)


def rerun_options(node_id: Optional[str]) -> dict:
    """FR-13.2's **soft** node affinity, as the task options a dispatch takes."""
    if node_id is None:
        return {}
    from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

    return {"scheduling_strategy": NodeAffinitySchedulingStrategy(node_id=node_id,
                                                                 soft=True)}


def _dispatch(node, options: dict, *args, **kwargs):
    """Run one `@ChiaFunction` as a task of its own, with *options*."""
    from chia.base.ChiaFunction import get

    target = node.options(**options) if options else node
    return get(target.chia_remote(*args, **kwargs))


def _work_dir(artefact_root: str, run_manifest_id: str, candidate_id: str,
              stage: str) -> str:
    """A per-call directory under the artefact root, created and never reused."""
    parent = Path(artefact_root, run_manifest_id, stage)
    parent.mkdir(parents=True, exist_ok=True)
    return tempfile.mkdtemp(prefix=f"{candidate_id}-", dir=str(parent))


def _run_command(binary: str, args: list, image_spec: dict, limits: dict,
                 cwd: str) -> dict:
    """Hash-check one tool binary, then run it bounded, exactly as a probe is."""
    actual = _sha256(binary)
    expected = image_spec["tool_hashes"].get(os.path.basename(binary))
    if expected != actual:
        raise BinaryMismatch(os.path.basename(binary), expected, actual)
    out = circt_exec_probe._chia_original(
        binary, list(args), cwd=cwd,
        wall_seconds=limits["probe_wall_seconds"],
        address_space_bytes=limits["probe_address_space_bytes"],
        cpu_seconds=limits["probe_cpu_seconds"], nofile=PROBE_NOFILE,
        output_byte_cap=limits["probe_output_byte_cap"])
    out["binary_sha256"] = actual
    return out


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def gate_rerun(repro_command: str, image_spec: dict, limits: dict,
               artefact_root: str, *, run_manifest_id: str, candidate_id: str,
               top_n: int, circt_roots: tuple = CIRCT_ROOTS,
               symbolizer: str = "llvm-symbolizer") -> dict:
    """Re-run one reproducing command in a fresh process and a new directory.

    Returns:
        {"status": str, "oracle_class": str | None, "assertion_text": str | None, "assertion_site": str | None, "fingerprint": str | None, "worker": str, "node_id": str, "pid": int, "counters": CounterBlock}, the counters counting one re-run at stage "gate" (3.11).
    Worker:
        {"circt": 1}.
    Raises:
        BinaryMismatch, exactly as probe_execute does and for the same reason.
    """
    from types import SimpleNamespace

    started_at = time.monotonic()
    argv = shlex.split(repro_command)
    work = _work_dir(artefact_root, run_manifest_id, candidate_id, "gate")
    out = _run_command(argv[0], argv[1:], image_spec, limits, work)

    status, _ = classify_build(out["exit_status"], out["signal"], out["stderr"],
                               out["limit_hit"])
    signal_name = None if status == "timeout" else out["signal"]
    stdout_path = Path(work, "rerun.stdout.txt")
    stderr_path = Path(work, "rerun.stderr.txt")
    stdout_path.write_text(out["stdout"], encoding="utf-8")
    stderr_path.write_text(out["stderr"], encoding="utf-8")

    build = BuildResult(
        probe_id=candidate_id, run_manifest_id=run_manifest_id,
        run_commit=image_spec["circt_sha"], image_digest=image_spec["image_digest"],
        status=status, binary_path=argv[0], binary_sha256=out["binary_sha256"],
        argv=out["argv"], exit_status=out["exit_status"], signal=signal_name,
        limit_hit=out["limit_hit"], cpu_seconds=out["cpu_seconds"],
        wall_seconds=out["wall_seconds"], peak_rss_bytes=out["peak_rss_bytes"],
        worker_hostname=out["worker_hostname"], worker_node_id=out["worker_node_id"],
        child_pid=out["child_pid"], stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        stdout_bytes=len(out["stdout"].encode("utf-8")),
        stderr_bytes=len(out["stderr"].encode("utf-8")), truncated=out["truncated"])

    # oracle_primary reads exactly one field off its image_spec, flag_string, and RunManifest.image_spec is a dict.
    verdict = oracle_primary._chia_original(
        build, SimpleNamespace(flag_string=image_spec["flag_string"]), work,
        circt_roots=circt_roots, symbolizer=symbolizer)["verdict"]
    finger = compute_fingerprint(verdict, signal_name, "", top_n)

    return {"status": status, "oracle_class": verdict.oracle_class,
            "assertion_text": verdict.assertion_text,
            "assertion_site": verdict.assertion_site,
            "fingerprint": finger.value,
            "worker": out["worker_hostname"], "node_id": out["worker_node_id"],
            "pid": out["child_pid"],
            "counters": CounterBlock(
                stage="gate", started=1, completed=1, failed=0,
                seconds=time.monotonic() - started_at)}


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def gate_validate(case_path: str, image_spec: dict, limits: dict,
                  artefact_root: str, *, run_manifest_id: str, candidate_id: str,
                  bin_dir: str) -> dict:
    """Run §4.8's parse-and-verify command for one reduced case (FR-13.15).

    Returns:
        {"argv": list[str], "exit_status": int | None, "stderr_path": str, "checker_fired": bool, "oracle_class": str | None, "counters": CounterBlock}, the counters counting one validity check at stage "gate" (3.11).
    Worker:
        {"circt": 1}; the binaries are the source tree's.
    Raises:
        BinaryMismatch, as probe_execute does.
    """
    started_at = time.monotonic()
    tool, options = validity_command(case_path)
    work = _work_dir(artefact_root, run_manifest_id, candidate_id, "gate")
    out = _run_command(os.path.join(bin_dir, tool), [*options, case_path],
                       image_spec, limits, work)
    status, _ = classify_build(out["exit_status"], out["signal"], out["stderr"],
                               out["limit_hit"])
    stderr_path = Path(work, "validity.stderr.txt")
    stderr_path.write_text(out["stderr"], encoding="utf-8")
    fired = status in ("assertion", "fatal_error", "crash")
    return {"argv": out["argv"], "exit_status": out["exit_status"],
            "stderr_path": str(stderr_path), "checker_fired": fired,
            "oracle_class": status if fired else None,
            "counters": CounterBlock(
                stage="gate", started=1, completed=1, failed=0,
                seconds=time.monotonic() - started_at)}


def case_lines(reduced: Optional[ReducedCase]) -> Optional[int]:
    """The lines of the reduced case on disk, or None when it cannot be read."""
    try:
        return len(Path(reduced.path).read_text(errors="backslashreplace")
                   .splitlines())
    except (OSError, AttributeError, TypeError):
        return None


def _question_2(reduced: Optional[ReducedCase], minimal_case_lines: int) -> tuple:
    """FR-13.3, total over every reducer record F-09 can produce."""
    if reduced is None or reduced.reducer == "none":
        return False, "no_reducer"
    if not reduced.recheck_matches:
        return False, "reduction_changed_failure"
    if not reduced.fixpoint:
        return False, ("not_fixpoint" if reduced.reduced
                       else (reduced.reason or "reduced_false"))
    if not reduced.reduced:
        lines = case_lines(reduced)
        if lines is None or lines > minimal_case_lines:
            return False, reduced.reason or "reduced_false"
        return True, "already_minimal"
    return True, None


def _question_4(candidate: CandidateRecord, dedup: DedupVerdict) -> tuple:
    """FR-13.5: `new` passes, every other value fails, `dedup_unavailable` too."""
    if candidate.dedup_basis == "insufficient":
        return False, "dedup_basis_insufficient"
    if dedup.verdict == "new":
        return True, None
    return False, dedup.verdict


def _q2_stopping_value(reason: Optional[str]) -> str:
    """The reason question 2 recorded, mapped onto FR-18.6's own vocabulary."""
    return reason if (2, reason) in TAXONOMY else "reduced_false"


@ChiaFunction(max_retries=0)
def gate_decide(candidate: CandidateRecord, reduced: Optional[ReducedCase],
                dedup: DedupVerdict, repair: Optional[RepairResult],
                manifest: RunManifest, db_path: str, *, limits: dict,
                top_n: int, bin_dir: str, minimal_case_lines: int) -> dict:
    """Ask the four mechanical questions in order and stop at the first no.

    Returns:
        {"decision": GateDecision, "counters": CounterBlock}, the decision defaulting to "nothing" for any unanswered question and the counters counting one candidate at stage "gate" (3.11); a candidate the gate decided nothing about is the failed one.
    Worker:
        head - and it holds NO circt resource.
    Raises:
        nothing.
    """
    started_at = time.monotonic()
    if candidate.oracle_class == "differential":
        raise ValueError(
            f"{candidate.candidate_id}: a 'differential' candidate does not "
            f"enter the gate at all (FR-13.14); it terminates at FR-08.10's "
            f"informational report")
    validate_candidate(candidate)

    store = LoopStore(db_path)
    fields = {key: None for key in ANSWER_KEYS}

    # --- 1. does it reproduce at candidate.run_commit? ----------------------
    original = store.query_one(
        "SELECT worker_hostname, worker_node_id, child_pid FROM build_result "
        "WHERE probe_id = ?", (candidate.probe_id,)) or {}
    fields["q1_original_worker"] = original.get("worker_hostname")
    fields["q1_original_pid"] = original.get("child_pid")
    rerun = _dispatch(
        gate_rerun, rerun_options(preferred_node(live_circt_nodes(),
                                                 original.get("worker_node_id"))),
        candidate.repro_command, manifest.image_spec, limits,
        manifest.artefact_root, run_manifest_id=candidate.run_manifest_id,
        candidate_id=candidate.candidate_id, top_n=top_n)
    fields["q1_rerun_worker"] = rerun["worker"]
    fields["q1_rerun_pid"] = rerun["pid"]
    fields["q1_same_worker"] = original.get("worker_node_id") == rerun["node_id"]
    fields["q1_reproduce"] = bool(
        rerun["oracle_class"] == candidate.oracle_class
        and rerun["assertion_text"] == candidate.assertion_text
        and rerun["assertion_site"] == candidate.assertion_site)
    # FR-10.1: recorded, printed beside the headline, and never a merge key.
    store.update("fingerprint", {"candidate_id": candidate.candidate_id},
                 {"fingerprint_stable": int(rerun["fingerprint"] == candidate.fingerprint)})

    if fields["q1_reproduce"]:
        # --- 2. is the case minimal? ---------------------------------------
        fields["q2_minimal"], fields["q2_reason"] = _question_2(
            reduced, minimal_case_lines)
        if fields["q2_minimal"]:
            # --- 3. is the input valid? ------------------------------------
            check = _dispatch(
                gate_validate, {}, reduced.path, manifest.image_spec, limits,
                manifest.artefact_root, run_manifest_id=candidate.run_manifest_id,
                candidate_id=candidate.candidate_id, bin_dir=bin_dir)
            fields["q3_exit_status"] = check["exit_status"]
            fields["q3_stderr_path"] = check["stderr_path"]
            fields["q3_after_parse"] = _after_parse(store, candidate, check)
            if check["checker_fired"]:
                fields["q3_valid"], fields["q3_validity_basis"] = True, "checker_failed"
            elif check["exit_status"] == 0:
                fields["q3_valid"], fields["q3_validity_basis"] = True, "parsed"
            else:
                fields["q3_valid"], fields["q3_validity_basis"] = False, "parsed"
            # FR-13.15's second conjunct, and FR-13.10 for its third case.
            if fields["q3_valid"] and fields["q3_after_parse"] is False:
                fields["q3_valid"] = False
            elif fields["q3_valid"] and fields["q3_after_parse"] is None:
                fields["q3_valid"] = None
            if fields["q3_valid"]:
                # --- 4. is it new? -----------------------------------------
                fields["q4_new"], fields["q4_reason"] = _question_4(candidate, dedup)

    decision, stopped, bucket = decide(fields, repair)
    verdict = GateDecision(candidate_id=candidate.candidate_id, **fields,
                           stopped_at_question=stopped, decision=decision,
                           taxonomy_bucket=bucket,
                           held_reason=candidate.held_reason)
    return {"decision": verdict,
            "counters": CounterBlock(
                stage="gate", started=1, completed=int(decision != "nothing"),
                failed=int(decision == "nothing"),
                seconds=time.monotonic() - started_at)}


#: The four questions in the order FR-13.1 fixes.
QUESTIONS = ((1, "q1_reproduce"), (2, "q2_minimal"), (3, "q3_valid"),
             (4, "q4_new"))


def decide(fields: dict, repair: Optional[RepairResult]) -> tuple:
    """Turn the fifteen answers into the decision, the stopping point and the bucket."""
    for number, key in QUESTIONS:
        answer = fields.get(key)
        if answer is None:
            return "nothing", number, "undecided"
        if answer is False:
            value = {1: "did_not_reproduce",
                     2: _q2_stopping_value(fields.get("q2_reason")),
                     3: "invalid_input",
                     4: fields.get("q4_reason")}[number]
            return "nothing", number, TAXONOMY.get((number, value), "undecided")
    fixed = bool(repair is not None and repair.fixed and repair.lit_ok)
    return ("report_plus_patch" if fixed else "report"), None, "new_bug"


def _after_parse(store: LoopStore, candidate: CandidateRecord,
                 check: dict) -> Optional[bool]:
    """FR-13.15's second conjunct, answered from the record and no fourth command."""
    frame_file = _fingerprint_frame_file(store, candidate.probe_id)
    if frame_file and not in_parser(frame_file):
        return True
    argv = store.query_one("SELECT argv_json FROM probe WHERE probe_id = ?",
                           (candidate.probe_id,))
    pipeline = bool(argv and _last_pass(json.loads(argv["argv_json"])))
    if check["exit_status"] == 0 and pipeline:
        return True
    return False if frame_file else None


def _fingerprint_frame_file(store: LoopStore, probe_id: str) -> Optional[str]:
    """The file of the frame §3.7.1 fingerprints on, full path, or None."""
    row = store.query_one("SELECT frames_json FROM oracle_verdict WHERE probe_id = ?",
                          (probe_id,))
    if row is None:
        return None
    from circt_bug_loop.probe_task import strip_prologue
    from circt_bug_loop.store import Frame

    frames = strip_prologue([Frame(**frame) for frame in json.loads(row["frames_json"])])
    return next((frame.file for frame in frames
                 if frame.in_circt_object and frame.line > 0 and frame.file), None)


def decided_utc() -> str:
    """The decision's own timestamp, UTC, as the `gate_decision` row records it."""
    return datetime.now(timezone.utc).isoformat()
