"""`04-Test-Plan.md` §1's `gate` rows: `gate.py` (B9a), F-13 and FR-18.6."""
from __future__ import annotations

import ast
import inspect
import json
import os
from pathlib import Path

import pytest

from circt_bug_loop import gate
from circt_bug_loop.contract import schema
from circt_bug_loop.gate import (ANSWER_KEYS, DEFAULT_VALIDITY_COMMAND,
                                 PARSER_DIRS, TAXONOMY, VALIDITY_COMMANDS,
                                 answers, decide, gate_decide, gate_rerun,
                                 gate_validate, in_parser, preferred_node,
                                 rerun_options, validity_command)
from circt_bug_loop.probe_task import BinaryMismatch
from circt_bug_loop.store import (CandidateRecord, DedupVerdict, Frame,
                                  LoopStore, OracleVerdict, ReducedCase,
                                  RepairResult)
from circt_bug_loop.tests.conftest import call_node
from circt_bug_loop.triage_task import compute_fingerprint

pytestmark = pytest.mark.t0

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GATE = FIXTURES / "gate"
MANIFEST = FIXTURES / "triage" / "run_manifest" / "calibration_two.json"

ASSERT_TEXT = 'op && "null op"'
ASSERT_SITE = "/workspace/circt/lib/Dialect/HW/HWOps.cpp:412"
FRAME_FILE = "/workspace/circt/lib/Dialect/HW/HWOps.cpp"
#: Ray validates a node id's shape.
NODE_A = "a1" * 28
NODE_B = "b2" * 28
LIMITS = {"probe_wall_seconds": 60, "probe_address_space_bytes": 4 << 30,
          "probe_cpu_seconds": 45, "probe_output_byte_cap": 1_000_000}
TOP_N = 3

#: `budget.yaml`'s own `minimal_case_lines` (W-18b).
MINIMAL_CASE_LINES = 12

#: The ten keys `DedupVerdict.evidence` is closed at (§2.9).
EVIDENCE = ("matched_key", "matched_token", "issue_number", "issue_url",
            "issue_state", "issue_labels", "fixing_commit",
            "duplicate_of_candidate_id", "post_pin_file_touches",
            "rescreened_from")


def _manifest(tmp_path, bin_dir):
    manifest = schema.from_json(MANIFEST.read_text(), schema.RunManifest)
    manifest.artefact_root = str(tmp_path / "artefacts")
    manifest.image_spec["tool_hashes"] = _hashes(bin_dir)
    return manifest


def _hashes(bin_dir):
    from circt_bug_loop.probe_task import _sha256

    return {path.name: _sha256(str(path)) for path in Path(bin_dir).iterdir()}


def _tools(tmp_path, *, entry="assertion.sh", check="clean.sh"):
    """A bin directory of stand-in tools, named as §4.8's three commands are."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, source in (("circt-opt", check), ("firtool", check),
                         ("circt-verilog", check), ("entry-tool", entry)):
        target = bin_dir / name
        target.write_bytes((GATE / source).read_bytes())
        target.chmod(0o755)
    return str(bin_dir)


def _frames(file=FRAME_FILE):
    return [Frame(index=0, address="0x1", shape="attributed", module="",
                  offset="", function="circt::hw::verify",
                  file=file, line=412, in_circt_object=True)]


def _verdict(file=FRAME_FILE):
    return OracleVerdict(
        probe_id="p-01", fired=True, oracle_class="assertion",
        assertion_text=ASSERT_TEXT, assertion_site=ASSERT_SITE,
        fatal_message=None, frames=_frames(file), prologue_dropped=0,
        frames_resolved=1, frames_with_location=1,
        fingerprint_frame=f"circt::hw::verify {os.path.basename(file)}",
        out_of_scope_root=False, repro_command="x",
        flag_string="-UNDEBUG", tool_version_output="v")


def _fingerprint(file=FRAME_FILE):
    return compute_fingerprint(_verdict(file), "SIGABRT", "", TOP_N).value


def _candidate(tmp_path, bin_dir, *, case=None, **over):
    case = case or (tmp_path / "case.mlir")
    if not case.exists():
        case.write_bytes((GATE / "case.mlir").read_bytes())
    fields = dict(
        candidate_id="cand-0001", probe_id="p-01", run_manifest_id="r" * 32,
        arm="seeded", run_commit="c" * 40, image_digest="sha256:" + "0" * 64,
        oracle_class="assertion", frame_tuple=["circt::hw::verify"],
        frames_resolved=1, frames_with_location=1, out_of_scope_root=False,
        contaminated_symbol=False, contaminated_file=False,
        contamination_lower_bound="seed_commit", triage_class="bug",
        artefact_dir=str(tmp_path / "probe"),
        assertion_text=ASSERT_TEXT, assertion_site=ASSERT_SITE,
        repro_command=f"{bin_dir}/entry-tool --lower-seq-to-sv {case}",
        reducer="circt-reduce", reduced=True, fixpoint=True,
        budget_truncated=False, reduced_path=str(case), size_before_bytes=200,
        size_after_bytes=67, size_before_ops=6, size_after_ops=2,
        fingerprint=_fingerprint(), fingerprint_stable=None,
        structural_hash="0" * 64, dedup_basis="assertion", dedup_verdict="new",
        dedup_evidence=dict.fromkeys(EVIDENCE))
    fields.update(over)
    return CandidateRecord(**fields)


def _reduced(path, **over):
    fields = dict(
        probe_id="p-01", reducer="circt-reduce", reduced=True, fixpoint=True,
        budget_truncated=False, reason=None, lift=None, path=str(path),
        size_before_bytes=200, size_after_bytes=67, size_before_ops=6,
        size_after_ops=2, wall_seconds=1.0, interestingness_calls=5,
        recheck_class="assertion", recheck_assertion_text=ASSERT_TEXT,
        recheck_assertion_site=ASSERT_SITE, recheck_matches=True)
    fields.update(over)
    return ReducedCase(**fields)


def _dedup(verdict="new", **evidence):
    payload = dict.fromkeys(EVIDENCE)
    payload.update(evidence)
    return DedupVerdict(probe_id="p-01", verdict=verdict, evidence=payload)


def _repair(**over):
    fields = dict(
        candidate_id="cand-0001", local_id=900_000_007, status="fixed",
        failing_phase=None, reproduced=True, build_ok=True, fixed=True,
        lit_ok=True, lit_unusable=False, lit_passed=1119, lit_failed=0,
        lit_failures=[], diff_path=None, diff_added=2, diff_removed=1,
        chia_artifact_dir=None, repro_dir="/art/repair/900000007",
        repro_overwritten=False, restore_ok=True, restore_hashes_match=True,
        restore_log="", backend="vertex",
        token_capture="unavailable_remote_dispatch")
    fields.update(over)
    return RepairResult(**fields)


def _store(tmp_path, candidate, *, argv=None, frame_file=FRAME_FILE):
    """A `loop.db` carrying every row `gate_decide` reads back."""
    store = LoopStore(str(tmp_path / "loop.db"))
    store.insert("run", {
        "run_manifest_id": candidate.run_manifest_id, "mode": "calibration",
        "seed_set": "171", "manifest_json": "{}", "budget_file_sha": "x",
        "cluster_yaml_sha": "y", "artefact_root": str(tmp_path),
        "started_utc": "2026-09-14T00:00:00+00:00", "ended_utc": None})
    store.insert("probe", {
        "probe_id": candidate.probe_id, "run_manifest_id": candidate.run_manifest_id,
        "seed_sha": "a" * 40, "arm": candidate.arm, "iteration": 0,
        "tool": "circt-opt",
        "argv_json": json.dumps(argv if argv is not None
                                else ["--lower-seq-to-sv", "in.mlir"]),
        "polarity": "expect_zero", "shape": "plain", "input_path": "in.mlir",
        "mutator_id": None, "mutator_seed_int": None, "source_test_path": None,
        "spec_json": "{}", "artefact_dir": candidate.artefact_dir})
    store.insert("image", {
        "image_digest": candidate.image_digest, "circt_sha": "e" * 40,
        "sdk_tag": "firtool-1.143.0", "image_tag": "t", "flag_string": "-UNDEBUG",
        "targets_json": "[]", "cmake_args_json": "[]", "verilator_version": "5.028",
        "slang_enabled": 1, "lit_discovery_ok": 1, "lit_discovered_count": 1,
        "assertion_nonreferencing_json": "[]", "tool_hashes_json": "{}",
        "built_utc": "2026-09-14T00:00:00+00:00"})
    store.insert("build_result", {
        "probe_id": candidate.probe_id, "run_commit": candidate.run_commit,
        "image_digest": candidate.image_digest, "status": "assertion",
        "binary_path": "/workspace/circt/build/bin/circt-opt",
        "binary_sha256": "f" * 64, "exit_status": None, "signal": "SIGABRT",
        "limit_hit": None, "cpu_seconds": 0.1, "wall_seconds": 0.2,
        "peak_rss_bytes": 1, "worker_hostname": "worker-a",
        "worker_node_id": NODE_A, "child_pid": 4242, "stdout_path": "o",
        "stderr_path": "e", "truncated": 0})
    store.insert("oracle_verdict", {
        "probe_id": candidate.probe_id, "fired": 1, "oracle_class": "assertion",
        "assertion_text": ASSERT_TEXT, "assertion_site": ASSERT_SITE,
        "fatal_message": None,
        "frames_json": json.dumps([{
            "index": 0, "address": "0x1", "shape": "attributed", "module": "",
            "offset": "", "function": "circt::hw::verify", "file": frame_file,
            "line": 412, "in_circt_object": True}]),
        "prologue_dropped": 0, "frames_resolved": 1, "frames_with_location": 1,
        "fingerprint_frame": f"circt::hw::verify {os.path.basename(frame_file)}",
        "out_of_scope_root": 0, "repro_command": candidate.repro_command,
        "flag_string": "-UNDEBUG", "tool_version_output": "v"})
    store.insert("candidate", {
        "candidate_id": candidate.candidate_id, "local_id": None,
        "probe_id": candidate.probe_id,
        "run_manifest_id": candidate.run_manifest_id, "arm": candidate.arm,
        "run_commit": candidate.run_commit, "image_digest": candidate.image_digest,
        "oracle_class": candidate.oracle_class,
        "assertion_text": candidate.assertion_text,
        "assertion_site": candidate.assertion_site,
        "frame_tuple_json": json.dumps(candidate.frame_tuple),
        "out_of_scope_root": 0, "contaminated_symbol": 0, "contaminated_file": 0,
        "contamination_lower_bound": "seed_commit",
        "triage_class": candidate.triage_class,
        "held_reason": candidate.held_reason, "taxonomy_bucket": None,
        "artefact_dir": candidate.artefact_dir,
        "created_utc": "2026-09-14T00:00:00+00:00"})
    store.insert("fingerprint", {
        "candidate_id": candidate.candidate_id, "basis": candidate.dedup_basis,
        "value": candidate.fingerprint, "fingerprint_stable": None,
        "frame_tuple_json": json.dumps(candidate.frame_tuple),
        "structural_hash": "0" * 64})
    return store


def _direct(monkeypatch):
    """Replace the one dispatch seam with a direct call to each node's original."""
    seen = []

    def _run(node, options, *args, timeout=None, **kwargs):
        seen.append({"node": getattr(node, "__name__", node), "options": options,
                     "timeout": timeout})
        return call_node(node, *args, **kwargs)

    monkeypatch.setattr(gate, "_dispatch", _run)
    monkeypatch.setattr(gate, "live_circt_nodes", lambda: [])
    return seen


def _never_placed(monkeypatch, nodes=(NODE_A, NODE_B)):
    """A dispatch seam that never completes, as a held `circt` slot never does."""
    seen = []

    def _run(node, options, *args, timeout=None, **kwargs):
        seen.append({"node": node.__name__, "options": options, "timeout": timeout})
        return None

    monkeypatch.setattr(gate, "_dispatch", _run)
    monkeypatch.setattr(gate, "live_circt_nodes", lambda: list(nodes))
    return seen


#: `None` is a value question 2 must answer.
_UNSET = object()


def _decide(tmp_path, monkeypatch, *, candidate=None, reduced=_UNSET, dedup=None,
            repair=None, entry="assertion.sh", check="clean.sh", argv=None,
            frame_file=FRAME_FILE, store=None,
            minimal_case_lines=MINIMAL_CASE_LINES):
    bin_dir = _tools(tmp_path, entry=entry, check=check)
    candidate = candidate or _candidate(tmp_path, bin_dir)
    store = store or _store(tmp_path, candidate, argv=argv, frame_file=frame_file)
    seen = _direct(monkeypatch)
    # `{"decision", "counters"}` since the join (W-17).
    out = call_node(
        gate_decide, candidate,
        _reduced(candidate.reduced_path) if reduced is _UNSET else reduced,
        dedup or _dedup(), repair, _manifest(tmp_path, bin_dir),
        str(tmp_path / "loop.db"), limits=LIMITS, top_n=TOP_N, bin_dir=bin_dir,
        minimal_case_lines=minimal_case_lines)
    assert out["counters"].stage == "gate"
    return out["decision"], store, seen


def test_gate_01_four_questions_in_order_stopping_at_the_first_no(tmp_path,
                                                                  monkeypatch):
    """T-U-gate-01 (FR-13.1): all four answered in order, the stopping point recorded, and no question after the first "no" is asked at all."""
    decision, _, _ = _decide(tmp_path, monkeypatch)
    assert decision.stopped_at_question is None
    assert [decision.q1_reproduce, decision.q2_minimal, decision.q3_valid,
            decision.q4_new] == [True, True, True, True]
    assert decision.decision == "report"

    stopped, _, seen = _decide(tmp_path / "b", monkeypatch, entry="clean.sh")
    assert stopped.q1_reproduce is False
    assert stopped.stopped_at_question == 1
    assert (stopped.q2_minimal, stopped.q3_valid, stopped.q4_new) == (None, None, None)
    assert [call["node"] for call in seen] == ["gate_rerun"], (
        "question 3's command is not run once question 1 has said no")
    assert set(answers(stopped)) == set(ANSWER_KEYS) and len(ANSWER_KEYS) == 15


def test_gate_02_the_decision_stage_holds_no_worker_resource():
    """T-U-gate-02 (FR-13.2): `gate_decide` declares none, so it can never hold a `circt` slot while waiting for one; the two workers are nodes of their own."""
    assert gate_decide._chia_options == {"max_retries": 0}
    assert gate_rerun._chia_options == {"resources": {"circt": 1},
                                        "max_retries": 0}
    assert gate_validate._chia_options == {"resources": {"circt": 1},
                                           "max_retries": 0}
    for node in (gate_decide, gate_rerun, gate_validate):
        doc = inspect.getdoc(node)
        for paragraph in ("Returns:", "Worker:", "Raises:"):
            assert paragraph in doc, node


def test_gate_03_the_pin_is_soft_and_prefers_another_node():
    """T-U-gate-03 (FR-13.2): `NodeAffinitySchedulingStrategy(node_id=<other>, soft=True)`; with only one live `circt` node there is no other, the re-run still happens, and `same_worker=True` is recorded truthfully."""
    assert preferred_node([NODE_A, NODE_B], NODE_A) == NODE_B
    assert preferred_node([NODE_A], NODE_A) is None
    assert preferred_node([], None) is None

    options = rerun_options(NODE_B)
    strategy = options["scheduling_strategy"]
    assert strategy.node_id == NODE_B
    assert strategy.soft is True
    assert rerun_options(None) == {}


def test_gate_03b_the_soft_pin_is_given_up_on_and_then_the_re_run_is_too(
        tmp_path, monkeypatch):
    """T-U-gate-03 (FR-13.2): Ray's soft affinity falls back only for an infeasible or dead node, never for one whose single `circt` slot is merely held, so the gate waits out the pin itself, re-dispatches unpinned once, and - if that never lands either - answers question 1 no instead of waiting forever, as campaign 2's shard 0 did."""
    bin_dir = _tools(tmp_path)
    candidate = _candidate(tmp_path, bin_dir)
    _store(tmp_path, candidate)
    seen = _never_placed(monkeypatch)

    out = call_node(gate_decide, candidate, _reduced(candidate.reduced_path),
                    _dedup(), None, _manifest(tmp_path, bin_dir),
                    str(tmp_path / "loop.db"), limits=LIMITS, top_n=TOP_N,
                    bin_dir=bin_dir, minimal_case_lines=MINIMAL_CASE_LINES)
    decision = out["decision"]

    assert decision.q1_reproduce is False
    assert decision.q1_rerun_worker == gate.RERUN_UNSCHEDULED
    assert decision.q1_rerun_pid is None
    assert decision.q1_same_worker is None, "no worker ran, so there is nothing to compare"
    assert decision.stopped_at_question == 1
    assert decision.decision == "nothing"
    assert decision.taxonomy_bucket == "unreproducible"
    assert TAXONOMY[(1, "rerun_unscheduled")] == "unreproducible"

    # The pin once, then no pin at all, and no third attempt or later question.
    assert [call["node"] for call in seen] == ["gate_rerun", "gate_rerun"]
    assert seen[0]["options"]["scheduling_strategy"].node_id == NODE_B
    assert seen[0]["timeout"] == gate.RERUN_SCHEDULE_WAIT_S == 60
    assert seen[1]["options"] == {}
    assert seen[1]["timeout"] == LIMITS["probe_wall_seconds"] + gate.RERUN_WAIT_MARGIN_S

    # With no other live node there is no pin to give up on, and one attempt is all.
    single = _never_placed(monkeypatch, nodes=(NODE_A,))
    call_node(gate_decide, candidate, _reduced(candidate.reduced_path),
              _dedup(), None, _manifest(tmp_path, bin_dir),
              str(tmp_path / "loop.db"), limits=LIMITS, top_n=TOP_N,
              bin_dir=bin_dir, minimal_case_lines=MINIMAL_CASE_LINES)
    assert [call["options"] for call in single] == [{}]


def test_gate_03c_a_dispatch_that_never_completes_is_force_cancelled(monkeypatch):
    """T-U-gate-03 (FR-13.2): `_dispatch` bounds its own wait and force-cancels what it gives up on, so a re-run left in `PENDING_NODE_ASSIGNMENT` cannot hold `gate_decide` open for a whole seed iteration."""
    import chia.base.ChiaFunction as chia_function
    import ray

    class _Node:
        """A node whose dispatch produces a ref and never a result."""

        def options(self, **options):
            return self

        def chia_remote(self, *args, **kwargs):
            return "ref"

    cancelled = []
    monkeypatch.setattr(ray, "wait", lambda refs, timeout=None: ([], list(refs)))
    monkeypatch.setattr(ray, "cancel",
                        lambda ref, force=False: cancelled.append((ref, force)))
    assert gate._dispatch(_Node(), {}, timeout=0.01) is None
    assert cancelled == [("ref", True)], "force, because the probe may be running"

    # A cancel that itself fails is swallowed: the gate still answers.
    def _angry_cancel(ref, force=False):
        raise RuntimeError("the raylet is wedged")

    monkeypatch.setattr(ray, "cancel", _angry_cancel)
    assert gate._dispatch(_Node(), {}, timeout=0.01) is None

    # And a ref that IS ready inside the timeout is fetched, not cancelled.
    monkeypatch.setattr(ray, "wait", lambda refs, timeout=None: (list(refs), []))
    monkeypatch.setattr(chia_function, "get", lambda ref: {"worker": ref})
    assert gate._dispatch(_Node(), {}, timeout=1) == {"worker": "ref"}


def test_gate_04_both_worker_identities_are_recorded(tmp_path, monkeypatch):
    """T-U-gate-04 (FR-13.2): the original half from `BuildResult`'s three recorded fields and the re-run half from `gate_rerun`'s own return, with `q1_same_worker` computable from the two node ids."""
    decision, _, _ = _decide(tmp_path, monkeypatch)
    assert decision.q1_original_worker == "worker-a"
    assert decision.q1_original_pid == 4242
    assert decision.q1_rerun_worker and decision.q1_rerun_pid
    assert decision.q1_rerun_pid != decision.q1_original_pid
    assert decision.q1_same_worker is False, (
        "outside a Ray session the re-run's node id is not the recorded one")


def test_gate_05_question_one_fails_on_a_different_failure(tmp_path, monkeypatch):
    """T-U-gate-05 (FR-13.1): a re-run whose class, text or site differs fails question 1 and buckets as `unreproducible`."""
    decision, _, _ = _decide(tmp_path, monkeypatch, entry="other_assertion.sh")
    assert decision.q1_reproduce is False
    assert decision.stopped_at_question == 1
    assert decision.taxonomy_bucket == "unreproducible"
    assert decision.decision == "nothing"


def test_gate_21_the_rerun_gets_a_fresh_directory_every_call(tmp_path, monkeypatch):
    """T-U-gate-21 (FR-13.2): `mkdtemp` under `<artefact_root>/<run>/gate/`, one per call and never reused, carrying no state from the original run."""
    bin_dir = _tools(tmp_path)
    manifest = _manifest(tmp_path, bin_dir)
    candidate = _candidate(tmp_path, bin_dir)
    runs = [call_node(gate_rerun, candidate.repro_command, manifest.image_spec,
                      LIMITS, manifest.artefact_root,
                      run_manifest_id=candidate.run_manifest_id,
                      candidate_id=candidate.candidate_id, top_n=TOP_N)
            for _ in range(2)]
    parent = Path(manifest.artefact_root, candidate.run_manifest_id, "gate")
    directories = sorted(parent.iterdir())

    assert len(directories) == 2 and directories[0] != directories[1]
    assert all(path.name.startswith("cand-0001-") for path in directories)
    for path in directories:
        assert (path / "rerun.stderr.txt").read_text().count("Assertion") == 1
    assert runs[0]["pid"] != runs[1]["pid"], "a fresh process every time"
    assert runs[0]["oracle_class"] == "assertion"


def test_gate_22_the_rerun_checks_the_hash_manifest(tmp_path, monkeypatch):
    """T-U-gate-22 (FR-06.1): `gate_rerun` raises `BinaryMismatch` exactly as `probe_execute` does, for the same reason: a mutated tree makes every verdict from that worker suspect."""
    bin_dir = _tools(tmp_path)
    manifest = _manifest(tmp_path, bin_dir)
    manifest.image_spec["tool_hashes"]["entry-tool"] = "0" * 64
    candidate = _candidate(tmp_path, bin_dir)
    with pytest.raises(BinaryMismatch) as mismatch:
        call_node(gate_rerun, candidate.repro_command, manifest.image_spec,
                  LIMITS, manifest.artefact_root,
                  run_manifest_id=candidate.run_manifest_id,
                  candidate_id=candidate.candidate_id, top_n=TOP_N)
    assert mismatch.value.tool == "entry-tool"
    assert mismatch.value.expected_sha == "0" * 64


def test_gate_24_the_rerun_sets_fingerprint_stable(tmp_path, monkeypatch):
    """T-U-gate-24 (FR-10.1): the fingerprint is recomputed from the re-run's own stderr and compared; a difference records `false` and does NOT fail question 1, which asks only whether the failure reproduces."""
    decision, store, _ = _decide(tmp_path, monkeypatch)
    row = store.query_one("SELECT fingerprint_stable FROM fingerprint "
                          "WHERE candidate_id = ?", ("cand-0001",))
    assert row["fingerprint_stable"] == 1
    assert decision.q1_reproduce is True

    bin_dir = _tools(tmp_path / "b")
    drifted = _candidate(tmp_path / "b", bin_dir, fingerprint="something else")
    other, store2, _ = _decide(tmp_path / "b", monkeypatch, candidate=drifted)
    assert store2.query_one("SELECT fingerprint_stable FROM fingerprint "
                            "WHERE candidate_id = ?", ("cand-0001",))[
        "fingerprint_stable"] == 0
    assert other.q1_reproduce is True, "an unstable fingerprint is not a no"


@pytest.mark.parametrize("over,passes,reason", [
    ({}, True, None),
    # W-18b: a fixpoint with NO progress on a case at or below the threshold is the reducer proving the case minimal, and passes.
    ({"reduced": False, "reason": "no_progress"}, True, "already_minimal"),
    ({"recheck_matches": False}, False, "reduction_changed_failure"),
    ({"reducer": "none", "reduced": False}, False, "no_reducer"),
    ({"fixpoint": False}, False, "not_fixpoint"),
    # No fixpoint AND no progress keeps the reducer's own free text (FR-09.12).
    ({"reduced": False, "fixpoint": False, "reason": "budget_truncated"},
     False, "budget_truncated"),
])
def test_gate_06_to_09_question_two_is_total(tmp_path, monkeypatch, over, passes,
                                             reason):
    """T-U-gate-06 to -09 (FR-09.7): a fixpoint with a preserved re-check passes, and so does a fixpoint that removed nothing from a case already at or below `minimal_case_lines` (W-18b); `reduction_changed_failure`, no reducer at all, no fixpoint and a truncated reduction each fail as `not_minimal` with the reason recorded, and no input to this question is ever null."""
    bin_dir = _tools(tmp_path)
    candidate = _candidate(tmp_path, bin_dir)
    decision, _, _ = _decide(tmp_path, monkeypatch, candidate=candidate,
                             reduced=_reduced(candidate.reduced_path, **over))
    assert decision.q2_minimal is passes
    assert decision.q2_reason == reason
    if not passes:
        assert decision.stopped_at_question == 2
        assert decision.taxonomy_bucket == "not_minimal"
        assert decision.q3_valid is None and decision.q4_new is None


def test_gate_09c_the_threshold_is_what_decides_an_unshrunk_case(tmp_path,
                                                                 monkeypatch):
    """W-18b, errata row 46: the pilot's own case passes, and a big one does not."""
    # Two roots, because each `_decide` builds a `loop.db` with its own run row.
    small, large = tmp_path / "small", tmp_path / "large"
    small.mkdir(), large.mkdir()
    unshrunk = dict(reduced=False, reason="no_progress", fixpoint=True,
                    interestingness_calls=20, size_before_ops=3, size_after_ops=3)

    pilot = small / "pilot.mlir"
    pilot.write_text("module {\n"
                     "  moore.module private @net_open_uarray() {\n"
                     "    %0 = moore.net wire : <open_uarray<i32>>\n"
                     "    moore.output\n"
                     "  }\n"
                     "}\n")
    assert len(pilot.read_text().splitlines()) == 6 <= MINIMAL_CASE_LINES
    candidate = _candidate(small, _tools(small), case=pilot)
    decision, _, _ = _decide(small, monkeypatch, candidate=candidate,
                             reduced=_reduced(pilot, **unshrunk))
    assert (decision.q2_minimal, decision.q2_reason) == (True, "already_minimal")

    big = large / "big.mlir"
    big.write_text("".join(f"// line {n}\n" for n in range(40)))
    assert len(big.read_text().splitlines()) > MINIMAL_CASE_LINES
    other = _candidate(large, _tools(large), case=big)
    decision, _, _ = _decide(large, monkeypatch, candidate=other,
                             reduced=_reduced(big, **unshrunk))
    assert (decision.q2_minimal, decision.q2_reason) == (False, "no_progress")
    assert decision.taxonomy_bucket == "not_minimal"

    # A case that cannot be READ is not a case the gate calls minimal.
    assert gate.case_lines(_reduced(tmp_path / "absent.mlir")) is None


def test_gate_09b_no_reduced_case_at_all_is_still_an_answer(tmp_path, monkeypatch):
    """FR-13.3's "no reducer could run at all", in its extreme form: a candidate with no `ReducedCase` row is refused with a reason and not with a crash."""
    decision, _, _ = _decide(tmp_path, monkeypatch, reduced=None)
    assert (decision.q2_minimal, decision.q2_reason) == (False, "no_reducer")
    assert decision.taxonomy_bucket == "not_minimal"


def test_gate_13_the_three_check_commands_are_exactly_section_4_8():
    """T-U-gate-13 (FR-13.15): `circt-opt <case> -o /dev/null`, `firtool --parse-only <case>` and `circt-verilog --import-only <case>`; no pass pipeline and no `--allow-unregistered-dialect` anywhere."""
    assert validity_command("x.mlir") == ("circt-opt", ["-o", "/dev/null"])
    assert validity_command("x.fir") == ("firtool", ["--parse-only"])
    assert validity_command("x.sv") == ("circt-verilog", ["--import-only"])
    assert validity_command("x.SV") == ("circt-verilog", ["--import-only"])
    assert validity_command("noextension") == DEFAULT_VALIDITY_COMMAND

    every = [DEFAULT_VALIDITY_COMMAND, *VALIDITY_COMMANDS.values()]
    flat = [token for _, options in every for token in options]
    assert "--allow-unregistered-dialect" not in flat
    assert "--parse-only" not in VALIDITY_COMMANDS[".sv"][1], (
        "--import-only, which elaborates, and not --parse-only, which does not")
    assert "/dev/null" in DEFAULT_VALIDITY_COMMAND[1]


def test_gate_10_question_three_passes_on_exit_zero(tmp_path, monkeypatch):
    """T-U-gate-10 (FR-13.15): exit 0 passes, with `validity_basis=parsed`, and the recorded argv carries the `prlimit` prefix a probe carries."""
    decision, _, _ = _decide(tmp_path, monkeypatch)
    assert (decision.q3_valid, decision.q3_validity_basis) == (True, "parsed")
    assert decision.q3_exit_status == 0
    assert Path(decision.q3_stderr_path).exists()


def test_gate_11_the_checker_firing_is_still_a_pass(tmp_path, monkeypatch):
    """T-U-gate-11 (FR-13.15): where the check itself fires the primary oracle the candidate is a parser or verifier bug, so it passes with `validity_basis=checker_failed`."""
    decision, _, _ = _decide(tmp_path, monkeypatch, check="assertion.sh")
    assert (decision.q3_valid, decision.q3_validity_basis) == (True, "checker_failed")
    assert decision.q3_exit_status is None, "it died by signal"
    assert "Assertion" in Path(decision.q3_stderr_path).read_text()


def test_gate_12_a_clean_non_zero_exit_is_invalid_input(tmp_path, monkeypatch):
    """T-U-gate-12 (FR-13.15): a clean non-zero exit with a diagnostic fails as `invalid_input`, and the exit status and stderr are persisted."""
    decision, _, _ = _decide(tmp_path, monkeypatch, check="diagnostic.sh")
    assert decision.q3_valid is False
    assert decision.q3_exit_status == 1
    assert "error: expected SSA operand" in Path(decision.q3_stderr_path).read_text()
    assert decision.stopped_at_question == 3
    assert decision.taxonomy_bucket == "invalid_input"
    assert decision.q4_new is None


def test_gate_23_the_second_conjunct_after_parse(tmp_path, monkeypatch):
    """T-U-gate-23 (FR-13.15): `q3_after_parse` is answered from the record and runs **no fourth command**."""
    assert in_parser("/w/circt/lib/Parser/Parser.cpp") is True
    assert in_parser("/w/circt/lib/AsmParser/AsmParser.cpp") is True
    assert in_parser("/w/circt/tools/circt-translate/circt-translate.cpp") is True
    assert in_parser("/w/circt/lib/Dialect/FIRRTL/FIRParser.cpp") is True
    assert in_parser("/w/circt/lib/Dialect/HW/HWOps.cpp") is False
    assert all(directory.endswith("/") for directory in PARSER_DIRS)

    outside, _, _ = _decide(tmp_path, monkeypatch)
    assert outside.q3_after_parse is True and outside.q3_valid is True

    inside, _, _ = _decide(
        tmp_path / "b", monkeypatch, argv=["-o", "/dev/null"],
        frame_file="/workspace/circt/lib/Parser/Parser.cpp")
    assert inside.q3_after_parse is False
    assert inside.q3_valid is False, "the conjunct fails question 3"
    assert inside.taxonomy_bucket == "invalid_input"

    # The same parser frame.
    pipeline, _, _ = _decide(
        tmp_path / "c", monkeypatch, argv=["--lower-seq-to-sv", "in.mlir"],
        frame_file="/workspace/circt/lib/Parser/Parser.cpp")
    assert pipeline.q3_after_parse is True and pipeline.q3_valid is True


def test_gate_23b_no_frame_and_no_pipeline_refuses_as_undecided(tmp_path,
                                                                monkeypatch):
    """W5, FR-13.10: an undecidable conjunct leaves question 3 UNANSWERED."""
    bin_dir = _tools(tmp_path)
    candidate = _candidate(tmp_path, bin_dir)
    store = _store(tmp_path, candidate, argv=["-o", "/dev/null"])
    store.update("oracle_verdict", {"probe_id": "p-01"}, {"frames_json": "[]"})
    decision, _, _ = _decide(tmp_path, monkeypatch, candidate=candidate,
                             store=store)
    assert decision.q3_after_parse is None
    assert decision.q3_valid is None
    assert decision.stopped_at_question == 3
    assert decision.decision == "nothing"
    assert decision.taxonomy_bucket == "undecided"
    # The CHECK itself passed, which is why the refusal has to come from the conjunct.
    assert decision.q3_validity_basis in ("parsed", "checker_failed")
    assert decision.q4_new is None, "question 4 is not reached"


def test_gate_26_question_three_runs_at_the_candidates_own_commit(tmp_path,
                                                                  monkeypatch):
    """T-U-gate-26 (FR-02.7): against a calibration manifest with two entries, the check runs against the candidate's own commit's binaries and never `manifest.run_commit[0]`'s, which is another seed's (K14)."""
    bin_dir = _tools(tmp_path)
    manifest = _manifest(tmp_path, bin_dir)
    candidate = _candidate(tmp_path, bin_dir)
    assert manifest.run_commit[0].commit != candidate.run_commit

    source = Path(gate.__file__).read_text()
    assert "run_commit[0]" not in source
    assert "manifest.run_commit" not in source, (
        "the checks run against the worker's own tree, which the driver has "
        "already reset to the CANDIDATE's commit; reading the manifest's list "
        "would take an arbitrary sampled seed's in calibration mode (K14)")
    decision, _, _ = _decide(tmp_path, monkeypatch, candidate=candidate)
    assert decision.q3_valid is True


@pytest.mark.parametrize("verdict,passes", [
    ("new", True), ("duplicate_of_candidate", False), ("known_open_issue", False),
    ("known_closed_issue", False), ("fixed_post_pin", False),
    ("dedup_unavailable", False)])
def test_gate_14_question_four_reads_the_dedup_verdict(tmp_path, monkeypatch,
                                                       verdict, passes):
    """T-U-gate-14 (FR-10.7): `new` passes and every other value fails, `dedup_unavailable` included."""
    decision, _, _ = _decide(tmp_path, monkeypatch, dedup=_dedup(verdict))
    assert decision.q4_new is passes
    if not passes:
        assert decision.q4_reason == verdict
        assert decision.stopped_at_question == 4
        assert decision.decision == "nothing"


def test_gate_14b_an_insufficient_basis_fails_question_four(tmp_path, monkeypatch):
    """FR-10.8: a fingerprint of basis `insufficient` merges nothing, so it can never be `new`, and it buckets as `undecided` rather than as a duplicate."""
    bin_dir = _tools(tmp_path)
    candidate = _candidate(tmp_path, bin_dir, dedup_basis="insufficient",
                           fingerprint=None)
    decision, _, _ = _decide(tmp_path, monkeypatch, candidate=candidate)
    assert decision.q4_new is False
    assert decision.q4_reason == "dedup_basis_insufficient"
    assert decision.taxonomy_bucket == "undecided"


@pytest.mark.parametrize("verdict", ["known_open_issue", "known_closed_issue"])
def test_gate_25_both_mirror_verdicts_fail_with_the_issue_number(tmp_path,
                                                                 monkeypatch,
                                                                 verdict):
    """T-U-gate-25 (FR-10.3): both of §3.7.3's mirror verdicts fail question 4, and the evidence that names the issue is carried into the record's own reason through the `DedupVerdict`."""
    dedup = _dedup(verdict, matched_token="LowerTypes", issue_number=10681,
                   issue_url="https://github.com/llvm/circt/issues/10681",
                   issue_state=verdict.split("_")[1], issue_labels=["bug"])
    decision, _, _ = _decide(tmp_path, monkeypatch, dedup=dedup)
    assert decision.q4_new is False and decision.q4_reason == verdict
    assert decision.taxonomy_bucket == "duplicate"
    assert dedup.evidence["issue_number"] == 10681


@pytest.mark.parametrize("triage_class",
                         ["bug", "invalid_input", "known_issue", "untriaged"])
def test_gate_15_the_triage_classification_changes_nothing(tmp_path, monkeypatch,
                                                           triage_class):
    """T-U-gate-15 (FR-11.8): every other field held fixed, the four classifications produce identical answers and an identical decision, and no gate question reads the field, asserted by an `ast` search."""
    bin_dir = _tools(tmp_path)
    candidate = _candidate(tmp_path, bin_dir, triage_class=triage_class)
    decision, _, _ = _decide(tmp_path / triage_class, monkeypatch,
                             candidate=candidate)
    assert decision.decision == "report"
    assert answers(decision)["q3_valid"] is True
    assert decision.taxonomy_bucket == "new_bug"

    tree = ast.parse(Path(gate.__file__).read_text())
    read = [node for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "triage_class"]
    assert read == [], "no gate question may read the triage classification"


def test_gate_16_report_plus_patch_needs_fixed_and_lit_ok(tmp_path, monkeypatch):
    """T-U-gate-16 (FR-13.6): `report_plus_patch` when a `RepairResult` has `fixed=true` AND `lit_ok=true`; `report` otherwise."""
    good, _, _ = _decide(tmp_path, monkeypatch, repair=_repair())
    assert good.decision == "report_plus_patch"

    for index, over in enumerate(({"fixed": False}, {"lit_ok": False},
                                  {"lit_ok": None, "lit_unusable": True})):
        withheld, _, _ = _decide(tmp_path / f"b{index}", monkeypatch,
                                 repair=_repair(**over))
        assert withheld.decision == "report", over

    none, _, _ = _decide(tmp_path / "c", monkeypatch, repair=None)
    assert none.decision == "report"


def test_gate_17_any_null_answer_refuses(tmp_path, monkeypatch):
    """T-U-gate-17 (FR-13.10): the gate defaults to `nothing`, so a candidate with any unanswered question is refused whatever the other three say."""
    passing = dict.fromkeys(ANSWER_KEYS)
    passing.update(q1_reproduce=True, q2_minimal=True, q3_valid=True, q4_new=True)
    assert decide(passing, None) == ("report", None, "new_bug")

    for key, number in (("q1_reproduce", 1), ("q2_minimal", 2),
                        ("q3_valid", 3), ("q4_new", 4)):
        null = dict(passing, **{key: None})
        assert decide(null, _repair()) == ("nothing", number, "undecided"), key


def test_gate_18_a_refused_candidate_is_persisted_in_full(tmp_path, monkeypatch):
    """T-U-gate-18 (FR-13.11): a candidate refused at any question still carries all fifteen answers, its failing question and exactly one bucket, so the taxonomy's counts sum to the candidate count."""
    for entry, check, expected in (("clean.sh", "clean.sh", "unreproducible"),
                                   ("assertion.sh", "diagnostic.sh", "invalid_input")):
        decision, _, _ = _decide(tmp_path / expected, monkeypatch, entry=entry,
                                 check=check)
        recorded = answers(decision)
        assert set(recorded) == set(ANSWER_KEYS)
        assert decision.stopped_at_question in (1, 2, 3, 4)
        assert decision.taxonomy_bucket == expected
        assert decision.decision == "nothing"


def test_gate_19_a_differential_candidate_never_enters_the_gate(tmp_path,
                                                                monkeypatch):
    """T-U-gate-19 (FR-08.10): one fed deliberately is refused before question 1 and carries no `GateDecision` at all."""
    bin_dir = _tools(tmp_path)
    differential = CandidateRecord(
        candidate_id="cand-diff", probe_id="p-01", run_manifest_id="r" * 32,
        arm="seeded", run_commit="c" * 40, image_digest="sha256:" + "0" * 64,
        oracle_class="differential", frame_tuple=[], frames_resolved=0,
        frames_with_location=0, out_of_scope_root=False,
        contaminated_symbol=False, contaminated_file=False,
        contamination_lower_bound="seed_commit", triage_class="untriaged",
        artefact_dir=str(tmp_path))
    _direct(monkeypatch)
    with pytest.raises(ValueError, match="FR-13.14"):
        call_node(gate_decide, differential, None, _dedup(), None,
                  _manifest(tmp_path, bin_dir), str(tmp_path / "loop.db"),
                  limits=LIMITS, top_n=TOP_N, bin_dir=bin_dir,
                  minimal_case_lines=MINIMAL_CASE_LINES)


def test_gate_20_every_stopping_value_lands_in_its_stated_bucket():
    """T-U-gate-20 (FR-18.6): every one of the table's stopping values is produced by some path and buckets as stated, no path produces a value absent from the table, and the six buckets are exactly the six FR-18.6 names."""
    six = {"unreproducible", "not_minimal", "invalid_input", "duplicate",
           "undecided", "new_bug"}
    assert set(TAXONOMY.values()) | {"new_bug"} == six

    for (number, value), bucket in TAXONOMY.items():
        fields = dict.fromkeys(ANSWER_KEYS)
        fields.update(q1_reproduce=True, q2_minimal=True, q3_valid=True,
                      q4_new=True)
        fields[{1: "q1_reproduce", 2: "q2_minimal", 3: "q3_valid",
                4: "q4_new"}[number]] = False
        if number == 1:
            fields["q1_rerun_worker"] = (
                gate.RERUN_UNSCHEDULED if value == "rerun_unscheduled"
                else "worker-a")
        if number == 2:
            fields["q2_reason"] = value
        if number == 4:
            fields["q4_reason"] = value
        assert decide(fields, None) == ("nothing", number, bucket), value

    # A question-2 reason FR-09.12 lets B5 write freely still buckets.
    free = dict.fromkeys(ANSWER_KEYS)
    free.update(q1_reproduce=True, q2_minimal=False, q2_reason="already_minimal")
    assert decide(free, None) == ("nothing", 2, "not_minimal")


#: D-13's pass, as the probe's argv and the repro command name it.
MOORE_PASS = "--convert-moore-to-core"


def _verifier_candidate(tmp_path, bin_dir, case):
    """A `verifier_error` candidate, fingerprinted the way stage 6 fingerprints it."""
    from circt_bug_loop.store import OracleVerdict

    verdict = OracleVerdict(
        probe_id="p-01", fired=True, oracle_class="verifier_error",
        assertion_text=None, assertion_site=None, fatal_message=None, frames=[],
        prologue_dropped=0, frames_resolved=0, frames_with_location=0,
        fingerprint_frame=None, out_of_scope_root=False, repro_command="x",
        flag_string="-UNDEBUG", tool_version_output="v",
        verifier_message="error: 'comb.extract' op result #0 must be a signless "
                         "integer bitvector, but got '!hw.array<2xi2>'",
        verifier_op="comb.extract")
    fingerprint = compute_fingerprint(verdict, None, "", TOP_N,
                                      pass_name="convert-moore-to-core")
    return _candidate(
        tmp_path, bin_dir, case=case, oracle_class="verifier_error",
        assertion_text=None, assertion_site=None, frame_tuple=[],
        frames_resolved=0, frames_with_location=0,
        repro_command=f"{bin_dir}/entry-tool {MOORE_PASS} {case}",
        fingerprint=fingerprint.value, dedup_basis="verifier")


def test_gate_28_question_3_reads_stage_3s_own_parse_and_verify_run(tmp_path,
                                                                   monkeypatch):
    """D-13: the validity command already ran on this input, and is not run twice."""
    bin_dir = _tools(tmp_path, entry="verifier.sh", check="clean.sh")
    case = tmp_path / "case.mlir"
    candidate = _verifier_candidate(tmp_path, bin_dir, case)
    store = _store(tmp_path, candidate, argv=[MOORE_PASS, "in.mlir"])
    store.update("oracle_verdict", {"probe_id": candidate.probe_id},
                 {"oracle_class": "verifier_error", "assertion_text": None,
                  "assertion_site": None, "frames_json": "[]",
                  "fingerprint_frame": None})
    verify_stderr = Path(candidate.artefact_dir, "verify.stderr.txt")
    verify_stderr.parent.mkdir(parents=True, exist_ok=True)
    verify_stderr.write_text("")

    decision, _, seen = _decide(
        tmp_path, monkeypatch, candidate=candidate, store=store,
        reduced=_reduced(case, recheck_class="verifier_error",
                         recheck_assertion_text=None, recheck_assertion_site=None),
        entry="verifier.sh")
    assert [call["node"] for call in seen] == ["gate_rerun"], (
        "gate_validate is not dispatched: stage 3 already ran §4.8's command")
    assert (decision.q1_reproduce, decision.q2_minimal, decision.q3_valid,
            decision.q4_new) == (True, True, True, True)
    assert decision.q3_validity_basis == "parsed"
    assert decision.q3_exit_status == 0
    assert decision.q3_stderr_path == str(verify_stderr)
    # The failure IS after parsing: the input verified and the pass made the op.
    assert decision.q3_after_parse is True
    assert decision.decision == "report" and decision.taxonomy_bucket == "new_bug"
    # It is not invalid input, and the re-run agreed it is the same failure.
    assert store.query_one(
        "SELECT fingerprint_stable FROM fingerprint WHERE candidate_id = ?",
        (candidate.candidate_id,))["fingerprint_stable"] == 1


def test_gate_29_the_rerun_judges_a_verifier_error_by_the_same_rule(tmp_path,
                                                                   monkeypatch):
    """D-13: `gate_rerun` runs §4.8's command too, or question 1 always says no."""
    bin_dir = _tools(tmp_path, entry="verifier.sh", check="clean.sh")
    case = tmp_path / "case.mlir"
    case.write_bytes((GATE / "case.mlir").read_bytes())
    out = call_node(gate_rerun, f"{bin_dir}/entry-tool {MOORE_PASS} {case}",
                    _manifest(tmp_path, bin_dir).image_spec, LIMITS,
                    str(tmp_path / "artefacts"), run_manifest_id="r" * 32,
                    candidate_id="cand-0001", top_n=TOP_N)
    assert out["status"] == "verifier_error"
    assert out["oracle_class"] == "verifier_error"
    assert out["fingerprint"].startswith("comb.extract\n")
    assert "convert-moore-to-core" in out["fingerprint"]

    # The same tool with §4.8's command refusing the input is a parse error.
    refusing = _tools(tmp_path / "b", entry="verifier.sh", check="diagnostic.sh")
    out = call_node(gate_rerun, f"{refusing}/entry-tool {MOORE_PASS} {case}",
                    _manifest(tmp_path / "b", refusing).image_spec, LIMITS,
                    str(tmp_path / "artefacts"), run_manifest_id="r" * 32,
                    candidate_id="cand-0001", top_n=TOP_N)
    assert out["status"] == "parse_error" and out["oracle_class"] is None
