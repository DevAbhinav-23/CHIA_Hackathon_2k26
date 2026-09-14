"""Build `fixtures/results/`'s store: one coherent mini-campaign in one loop.db."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from circt_bug_loop.contract import schema
from circt_bug_loop.store import LoopStore

#: The run this store holds, which is the committed `run_manifest/` fixture's.
RUN = "7c1f4a9d6e2b48c0a53f81d27e6b09c4"
SEED_A = "3f9a1c0e7b4d2a68f05c9e13b7a4d820c6e5f9a1"
SEED_B = "7b2d48e1a05c93f6e28d1470bc5a93e10d4f8b26"
RUN_COMMIT = "e1d47b09c3a6f582041b9e7d63c085a4f27b1d09"
IMAGE = "sha256:" + "3" * 64
CUTOFF = "2026-09-23"

#: `contract/fixtures/`, which is where the manifest this run stamps comes from.
CONTRACT_FIXTURES = Path(schema.__file__).resolve().parent / "fixtures"
#: The recorded tool stderr of `04-Test-Plan.md` §13, one capture per outcome.
STDERR_FIXTURES = Path(__file__).resolve().parents[1] / "stderr"

#: FR-10.2's labelled set, as `render_results` takes it and as the driver passes it.
def labelled_pairs() -> list:
    """The committed FR-10.2 set, which is the one a real render is given."""
    from circt_bug_loop.results import load_labelled_pairs

    return load_labelled_pairs()

#: The six probes, in dispatch order.
PROBES = (
    ("p-0001", "seeded", SEED_A, 1, "firtool", "assert_glibc.txt", None, "SIGABRT",
     "assertion", "assertion_fired"),
    ("p-0002", "seeded", SEED_B, 1, "circt-opt", "clean.txt", 0, None,
     "clean_exit", ""),
    ("p-0003", "seeded", SEED_B, 2, "circt-opt", "segv.txt", None, "SIGSEGV",
     "crash", "died_by_signal"),
    ("p-0004", "mutation", SEED_A, 1, "firtool", "llvm_error.txt", None, "SIGABRT",
     "fatal_error", "llvm_error"),
    ("p-0005", "mutation", SEED_B, 1, "arcilator", "clean.txt", 0, None,
     "clean_exit", ""),
    ("p-0006", "mutation", SEED_B, 1, "circt-verilog", "parse_error_argv.txt", 1, None,
     "parse_error", "tool_rejected_argv"),
)

ASSERTION_TEXT = 'fieldType && "lowering a null field type"'
ASSERTION_SITE = "LowerTypes.cpp:412"
CRASH_FRAMES = ["LowerTypes::visitDecl", "FIRRTLVisitor::dispatchDeclVisitor",
                "LowerTypesPass::runOnOperation", "mlir::detail::OpToOpPassAdaptor::run",
                "mlir::PassManager::run"]


def manifest(artefact_root: str) -> schema.RunManifest:
    """The committed discovery manifest, re-rooted at *artefact_root*."""
    payload = json.loads(
        (CONTRACT_FIXTURES / "run_manifest" / "discovery_01.json").read_text())
    payload["artefact_root"] = artefact_root
    payload["confirmation_cutoff_date"] = CUTOFF
    parsed = schema.RunManifest(**payload)
    schema.validate(parsed)
    return parsed


def _seed(seed_sha: str, subject: str, *, exact: bool, tool: str) -> dict:
    """One `seed` row, as A1 writes it."""
    return {"run_manifest_id": RUN, "seed_sha": seed_sha, "parent_sha": "0" * 40,
            "subject": subject, "committed_date_utc": "2026-03-02T09:14:00+00:00",
            "llvm_pin": "9" * 40, "sdk_tag": "firtool-1.86.0" if exact else None,
            "sdk_exact": int(exact), "bumps_away": None if exact else 2,
            "entry_tool": tool, "dialect_bucket": "firrtl",
            "dialect_bucket_unmerged": "firrtl", "eligible_seeded": 1,
            "eligible_mutation": 1, "exclusion_reason": None,
            "record_json": json.dumps({"seed_sha": seed_sha})}


def _probe_rows(store: LoopStore, root: Path) -> None:
    """Write the six probes, their results and their build records."""
    for (probe_id, arm, seed_sha, iteration, tool, capture, exit_status, signal,
         status, reason) in PROBES:
        artefact_dir = root / "artefacts" / RUN / probe_id
        artefact_dir.mkdir(parents=True, exist_ok=True)
        stderr_path = artefact_dir / "stderr.txt"
        shutil.copyfile(STDERR_FIXTURES / capture, stderr_path)

        store.insert("probe", {
            "probe_id": probe_id, "run_manifest_id": RUN, "seed_sha": seed_sha,
            "arm": arm, "iteration": iteration, "tool": tool,
            "argv_json": json.dumps([tool, "--lower-types", "input.fir"]),
            "polarity": "expect_zero", "shape": "plain",
            "input_path": str(artefact_dir / "input.fir"),
            "mutator_id": "mlir.attr.int.flip_sign" if arm == "mutation" else None,
            "mutator_seed_int": 4242 if arm == "mutation" else None,
            "source_test_path": "test/Dialect/FIRRTL/lower-types.mlir"
                                if arm == "mutation" else None,
            "spec_json": json.dumps({"probe_id": probe_id}),
            "artefact_dir": str(artefact_dir)})
        store.insert("probe_result", {
            "probe_id": probe_id, "run_manifest_id": RUN, "arm": arm,
            "iteration": iteration, "build_status": status,
            "oracle_fired": int(status in ("assertion", "crash", "fatal_error")),
            "oracle_class": status if status in ("assertion", "crash", "fatal_error")
                            else None,
            "stopping_stage": "gate" if status in ("assertion", "crash", "fatal_error")
                              else "stage_3",
            "stopping_reason": reason, "result_json": json.dumps({"probe_id": probe_id}),
            "artefact_dir": str(artefact_dir)})
        store.insert("build_result", {
            "probe_id": probe_id, "run_commit": RUN_COMMIT, "image_digest": IMAGE,
            "status": status, "binary_path": f"/workspace/circt/build/bin/{tool}",
            "binary_sha256": "a" * 64, "exit_status": exit_status, "signal": signal,
            "limit_hit": None, "cpu_seconds": 3.5, "wall_seconds": 4.0,
            "peak_rss_bytes": 512 * 1024 * 1024, "worker_hostname": "bugloop-1",
            "worker_node_id": "n" * 8, "child_pid": 4100 + int(probe_id[-1]),
            "stdout_path": str(artefact_dir / "stdout.txt"),
            "stderr_path": str(stderr_path), "truncated": 0})


def _candidate(store: LoopStore, candidate_id: str, probe_id: str, arm: str, *,
               oracle_class: str, local_id: int, contaminated: bool = False,
               bucket: str = "new_bug", artefact_dir: str = "") -> None:
    """One `candidate` row, as B6b left it and the gate completed it."""
    store.insert("candidate", {
        "candidate_id": candidate_id, "local_id": local_id, "probe_id": probe_id,
        "run_manifest_id": RUN, "arm": arm, "run_commit": RUN_COMMIT,
        "image_digest": IMAGE, "oracle_class": oracle_class,
        "assertion_text": ASSERTION_TEXT if oracle_class == "assertion" else None,
        "assertion_site": ASSERTION_SITE if oracle_class == "assertion" else None,
        "frame_tuple_json": json.dumps(CRASH_FRAMES),
        "out_of_scope_root": 0, "contaminated_symbol": int(contaminated),
        "contaminated_file": 0, "contamination_lower_bound": "seed_commit",
        "triage_class": "bug", "held_reason": None, "taxonomy_bucket": bucket,
        "artefact_dir": artefact_dir, "created_utc": "2026-09-19T02:00:00+00:00"})


def _answers(**over) -> dict:
    """The fifteen gate answers of `02-HLD.md` §2.11, defaulted to four yeses."""
    from circt_bug_loop.gate import ANSWER_KEYS

    fields = dict.fromkeys(ANSWER_KEYS)
    fields.update(q1_reproduce=True, q1_original_worker="bugloop-1",
                  q1_rerun_worker="bugloop-2", q1_original_pid=4101,
                  q1_rerun_pid=4199, q1_same_worker=False, q2_minimal=True,
                  q3_valid=True, q3_validity_basis="parsed", q3_after_parse=True,
                  q3_exit_status=0, q3_stderr_path="/artefacts/validity.stderr.txt",
                  q4_new=True)
    fields.update(over)
    return fields


def _evidence(**over) -> str:
    """A `DedupVerdict.evidence` block carrying §2.9's eight keys and no others."""
    keys = ("matched_key", "matched_token", "issue_number", "issue_url", "issue_state",
            "issue_labels", "fixing_commit", "duplicate_of_candidate_id")
    block = dict.fromkeys(keys)
    block.update(over)
    return json.dumps(block, sort_keys=True)


def _ledger(store: LoopStore) -> None:
    """The ledger: both arm windows, per-stage occupancy, and two shared stages."""
    def observed(cpu=0.0, tokens_in=None, tokens_out=None, cost=None,
                 authorised=None, ceiling=None, billed=None, calls=None) -> str:
        """§2.7's eight keys (contract 2.2); the last four are the turn's money."""
        return json.dumps({"cpu_seconds": cpu, "tokens_in": tokens_in,
                           "tokens_out": tokens_out, "cost_usd": cost,
                           "authorised_usd": authorised, "ceiling_usd": ceiling,
                           "billed_usd": billed, "calls": calls}, sort_keys=True)

    rows = [
        ("l-0001", "seeded", "arm_window", "campaign", 14400.0, 1,
         observed(11827.5), "2026-09-19T04:00:00+00:00", None),
        ("l-0002", "mutation", "arm_window", "campaign", 9000.0, 1,
         observed(8100.0), "2026-09-19T08:00:00+00:00", "generated_inputs_per_day"),
        ("l-0003", "seeded", "stage", "stage_1", 120.0, 1,
         observed(90.0, 41839, 6114, 0.054, authorised=0.36, ceiling=0.36,
                  billed=0.054, calls=4), "2026-09-19T01:00:00+00:00", None),
        ("l-0004", "seeded", "stage", "stage_2", 180.0, 1,
         observed(150.0, 52310, 8820, 0.072, authorised=0.36, ceiling=0.36,
                  billed=0.072, calls=6), "2026-09-19T01:05:00+00:00", None),
        ("l-0005", "seeded", "stage", "stage_3", 12.0, 1,
         observed(9.0), "2026-09-19T01:10:00+00:00", None),
        ("l-0006", "seeded", "stage", "stage_3", 14.0, 1,
         observed(11.0), "2026-09-19T01:12:00+00:00", None),
        ("l-0007", "seeded", "stage", "stage_3", 16.0, 1,
         observed(12.0), "2026-09-19T01:14:00+00:00", None),
        ("l-0008", "seeded", "stage", "stage_7", 900.0, 1,
         observed(780.0), "2026-09-19T02:30:00+00:00", None),
        ("l-0009", "mutation", "stage", "stage_3", 11.0, 1,
         observed(8.0), "2026-09-19T05:10:00+00:00", None),
        ("l-0010", "mutation", "stage", "stage_3", 13.0, 1,
         observed(10.0), "2026-09-19T05:12:00+00:00", None),
        ("l-0011", "mutation", "stage", "stage_3", 15.0, 1,
         observed(11.0), "2026-09-19T05:14:00+00:00", None),
        ("l-0012", "shared", "stage", "image", 3600.0, 0,
         observed(28800.0), "2026-09-18T20:00:00+00:00", None),
        ("l-0013", "shared", "stage", "synthesis", 420.0, 0,
         observed(300.0, 188400, 9600, 0.177), "2026-09-17T11:00:00+00:00", None),
    ]
    store.insert_many("ledger_entry", [
        {"entry_id": entry_id, "run_manifest_id": RUN, "arm": arm, "scope": scope,
         "stage": stage, "unit": "wall_clock_seconds", "amount": amount,
         "metered": metered, "observed_json": block, "timestamp_utc": at,
         "stop_reason": stop}
        for entry_id, arm, scope, stage, amount, metered, block, at, stop in rows])


def build(root: Path) -> tuple:
    """Create the mini-campaign under *root* and return what a render needs."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    artefact_root = root / "artefacts"
    artefact_root.mkdir(exist_ok=True)
    run_manifest = manifest(str(artefact_root))
    store = LoopStore(str(root / "loop.db"))

    store.insert("run", {
        "run_manifest_id": RUN, "mode": "discovery", "seed_set": "187",
        "manifest_json": schema.to_json(run_manifest),
        "budget_file_sha": run_manifest.budget_file_sha,
        "cluster_yaml_sha": run_manifest.cluster_yaml_sha,
        "artefact_root": str(artefact_root), "started_utc": run_manifest.started_utc,
        "ended_utc": "2026-09-19T09:00:00+00:00"})
    store.insert_many("seed", [
        _seed(SEED_A, "[FIRRTL] fix null field type in LowerTypes", exact=True,
              tool="firtool"),
        _seed(SEED_B, "[HW] fix array index overflow in the canonicaliser", exact=False,
              tool="circt-opt")])
    store.insert("image", {
        "image_digest": IMAGE, "circt_sha": RUN_COMMIT, "sdk_tag": "firtool-1.86.0",
        "image_tag": "chia-circt-assert:fixture", "flag_string": "-O3 -UNDEBUG",
        "targets_json": json.dumps(["circt-opt", "firtool"]), "cmake_args_json": "[]",
        "verilator_version": "5.028", "slang_enabled": 1, "lit_discovery_ok": 1,
        "lit_discovered_count": 1119, "assertion_nonreferencing_json": "[]",
        "tool_hashes_json": json.dumps({"firtool": "b" * 64}),
        "built_utc": "2026-09-18T21:00:00+00:00"})

    _probe_rows(store, root)

    probe_dir = str(artefact_root / RUN)
    _candidate(store, "c-0001", "p-0001", "seeded", oracle_class="assertion",
               local_id=900_000_001, contaminated=True,
               artefact_dir=f"{probe_dir}/p-0001")
    _candidate(store, "c-0002", "p-0003", "seeded", oracle_class="crash",
               local_id=900_000_002, artefact_dir=f"{probe_dir}/p-0003")
    _candidate(store, "c-0003", "p-0004", "mutation", oracle_class="fatal_error",
               local_id=900_000_003, bucket="duplicate",
               artefact_dir=f"{probe_dir}/p-0004")
    _candidate(store, "c-0004", "p-0005", "mutation", oracle_class="differential",
               local_id=900_000_004, bucket=None,
               artefact_dir=f"{probe_dir}/p-0005")

    store.insert("differential_verdict", {
        "probe_id": "p-0005", "verdict": "diverge",
        "reason": "the two simulators disagree on one output at cycle 37",
        "verilator_version": "5.028", "x_policy": "x-assign=unique,x-initial=unique",
        "stimulus_id": "stim-0001", "port_list_sha": "c" * 64, "cycles": 128,
        "first_divergent_signal": "out_sum", "first_divergent_cycle": 37,
        "arcilator_value": "32'h0000_0010", "verilator_value": "32'h0000_0011",
        "arcilator_trace_path": f"{probe_dir}/p-0005/arcilator.vcd",
        "verilator_trace_path": f"{probe_dir}/p-0005/verilator.vcd",
        "driver_source": "circt/arc-tests"})

    for probe_id, before, after in (("p-0001", 1841, 96), ("p-0003", 2210, 140)):
        store.insert("reduced_case", {
            "probe_id": probe_id, "reducer": "circt-reduce", "reduced": 1,
            "fixpoint": 1, "budget_truncated": 0, "reason": None, "lift": None,
            "path": f"{probe_dir}/{probe_id}/reduced.fir",
            "size_before_bytes": before, "size_after_bytes": after,
            "size_before_ops": 40, "size_after_ops": 3, "wall_seconds": 180.0,
            "interestingness_calls": 56, "recheck_class": "assertion",
            "recheck_assertion_text": ASSERTION_TEXT,
            "recheck_assertion_site": ASSERTION_SITE, "recheck_matches": 1})

    store.insert_many("fingerprint", [
        {"candidate_id": "c-0001", "basis": "assertion",
         "value": f"{ASSERTION_TEXT}\n{ASSERTION_SITE}", "fingerprint_stable": 1,
         "frame_tuple_json": json.dumps(CRASH_FRAMES), "structural_hash": "1" * 64},
        {"candidate_id": "c-0002", "basis": "frames",
         "value": "SIGSEGV\nLowerTypes::visitDecl LowerTypes.cpp",
         "fingerprint_stable": 1, "frame_tuple_json": json.dumps(CRASH_FRAMES),
         "structural_hash": "2" * 64},
        {"candidate_id": "c-0003", "basis": "frames",
         "value": "SIGABRT\nHWOps::verify HWOps.cpp", "fingerprint_stable": 0,
         "frame_tuple_json": json.dumps(CRASH_FRAMES), "structural_hash": "3" * 64}])

    store.insert_many("dedup_verdict", [
        {"candidate_id": "c-0001", "verdict": "new", "evidence_json": _evidence()},
        {"candidate_id": "c-0002", "verdict": "new", "evidence_json": _evidence()},
        {"candidate_id": "c-0003", "verdict": "known_open_issue",
         "evidence_json": _evidence(matched_token="HWOps", issue_number=10681,
                                    issue_url="https://github.com/llvm/circt/issues/10681",
                                    issue_state="open", issue_labels=["bug"])}])

    store.insert_many("report", [
        {"candidate_id": candidate_id, "path": f"{probe_dir}/{probe_id}/report.md",
         "template": template, "title": title, "classification": "bug",
         "classification_reason": "An oracle fired on a reduced input.",
         "rendered_sha256": "d" * 64,
         "assisted_by": "circt_bug_loop:vertex:gemini-3.8-flash",
         "fields_present_json": json.dumps(["reduced_case", "repro_command"])}
        for candidate_id, probe_id, template, title in (
            ("c-0001", "p-0001", "primary",
             "firtool: assertion in LowerTypes on a null field type"),
            ("c-0002", "p-0003", "primary",
             "circt-opt: segmentation fault canonicalising an array index"),
            ("c-0003", "p-0004", "primary",
             "firtool: LLVM ERROR verifying a malformed hw.module"),
            ("c-0004", "p-0005", "differential",
             "arcilator and Verilator disagree on out_sum at cycle 37"))])

    store.insert_many("repair", [
        {"candidate_id": candidate_id, "local_id": local_id, "status": status,
         "failing_phase": phase, "reproduced": 1, "build_ok": 1, "fixed": fixed,
         "lit_ok": lit_ok, "lit_unusable": 0, "lit_passed": 1119, "lit_failed": 0,
         "lit_failures_json": "[]",
         "diff_path": f"{probe_dir}/repair/{local_id}/fix.diff" if fixed else None,
         "diff_added": 3 if fixed else None, "diff_removed": 1 if fixed else None,
         "chia_artifact_dir": None, "chia_row_seen": 1,
         "repro_dir": f"{probe_dir}/repair/{local_id}",
         "repro_overwritten": overwritten, "restore_ok": 1, "restore_hashes_match": 1,
         "restore_log": "reset, rebuilt and re-hashed", "backend": "vertex",
         "token_capture": "unavailable_remote_dispatch"}
        for candidate_id, local_id, status, phase, fixed, lit_ok, overwritten in (
            ("c-0001", 900_000_001, "fixed", None, 1, 1, 0),
            ("c-0002", 900_000_002, "attempted", "fix", 0, None, 1))])

    store.insert_many("gate_decision", [
        {"candidate_id": candidate_id, "answers_json": json.dumps(answers),
         "stopped_at_question": stopped, "decision": decision,
         "taxonomy_bucket": bucket, "decided_utc": "2026-09-19T03:00:00+00:00"}
        for candidate_id, answers, stopped, decision, bucket in (
            ("c-0001", _answers(), None, "report_plus_patch", "new_bug"),
            ("c-0002", _answers(), None, "report", "new_bug"),
            ("c-0003", _answers(q4_new=False, q4_reason="known_open_issue"), 4,
             "nothing", "duplicate"))])

    store.insert_many("filing", [
        {"candidate_id": "c-0001", "approver": "adi", "decision": "report_plus_patch",
         "approved_at_utc": "2026-09-19T06:00:00+00:00", "licence_confirmed": 1,
         "licence_confirmed_at_utc": "2026-09-19T06:00:00+00:00", "url_source": "poll",
         "issue_number": 10999,
         "issue_url": "https://github.com/llvm/circt/issues/10999",
         "prefill_url_length": 3120, "prefill_fallback_reason": None, "confirmed": 1,
         "confirmed_at_utc": "2026-09-21T10:00:00+00:00",
         "confirmation_url":
             "https://github.com/llvm/circt/issues/10999#issuecomment-1"},
        {"candidate_id": "c-0002", "approver": "adi", "decision": "report",
         "approved_at_utc": "2026-09-19T06:30:00+00:00", "licence_confirmed": None,
         "licence_confirmed_at_utc": None, "url_source": "pasted", "issue_number": 11000,
         "issue_url": "https://github.com/llvm/circt/issues/11000",
         "prefill_url_length": 2400, "prefill_fallback_reason": None, "confirmed": 0,
         "confirmed_at_utc": None, "confirmation_url": None}])

    store.insert_many("turn_failure", [
        {"run_manifest_id": RUN, "seed_sha": seed_sha, "arm": arm,
         "iteration": iteration, "stage": "stage_2", "kind": kind,
         "detail": detail}
        for seed_sha, arm, iteration, kind, detail in (
            (SEED_A, "seeded", 1, "prompt_contract:no_block",
             "PromptContractError: no_block"),
            (SEED_B, "seeded", 1, "prompt_contract:no_block",
             "PromptContractError: no_block"),
            (SEED_A, "mutation", 1, "stale_at_build",
             "firtool rejects this seed's own test/Dialect/FIRRTL/errors.mlir "
             f"at {RUN_COMMIT}"))])

    _ledger(store)
    return store, run_manifest, labelled_pairs()


def main(argv: list) -> int:
    """Write the store into the directory *argv*[0] names, for inspection."""
    if not argv:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    store, _, _ = build(Path(argv[0]))
    print(store.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
