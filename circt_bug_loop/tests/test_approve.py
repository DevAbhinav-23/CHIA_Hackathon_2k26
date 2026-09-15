"""`04-Test-Plan.md` §1's `appr` rows: `approve.py` (B9c), F-13's human half, F-20."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from circt_bug_loop import approve
from circt_bug_loop.approve import (AWAITING, PREFILL_URL_CHAR_LIMIT,
                                    REFUSED_PREFIX, issue_number, main, prefill,
                                    render_view)
from circt_bug_loop.store import LoopStore

pytestmark = pytest.mark.t0

FIXTURES = Path(__file__).resolve().parent / "fixtures"
APPROVE = FIXTURES / "approve"
BUDGET = Path(__file__).resolve().parents[1] / "budget.yaml"

FINGERPRINT = 'op && "null op"\nHWOps.cpp:412'
EVIDENCE = ("matched_key", "matched_token", "issue_number", "issue_url",
            "issue_state", "issue_labels", "fixing_commit",
            "duplicate_of_candidate_id", "post_pin_file_touches",
            "rescreened_from", "generic_text_match", "op_only_match")


def _answers(**over):
    from circt_bug_loop.gate import ANSWER_KEYS

    fields = dict.fromkeys(ANSWER_KEYS)
    fields.update(q1_reproduce=True, q1_original_worker="worker-a",
                  q1_rerun_worker="worker-b", q1_original_pid=1,
                  q1_rerun_pid=2, q1_same_worker=False, q2_minimal=True,
                  q3_valid=True, q3_validity_basis="parsed",
                  q3_after_parse=True, q3_exit_status=0,
                  q3_stderr_path="/art/gate/validity.stderr.txt", q4_new=True)
    fields.update(over)
    return fields


def _case(store, tmp_path, candidate_id, *, decision="report", report="short.md",
          labels=None, held=None, diff=None, dedup="new"):
    """One whole candidate: the rows B6b, B7, B8 and B9a would have written."""
    probe_id = f"p-{candidate_id}"
    reduced = tmp_path / f"{candidate_id}.reduced.mlir"
    reduced.write_text("hw.module @bugloop() {\n  hw.output\n}\n", encoding="utf-8")
    evidence = dict.fromkeys(EVIDENCE)
    if labels is not None:
        evidence.update(matched_token="LowerTypes", issue_number=10681,
                        issue_url="https://github.com/llvm/circt/issues/10681",
                        issue_state="open", issue_labels=labels)
    store.insert("probe", {
        "probe_id": probe_id, "run_manifest_id": "r" * 32, "seed_sha": "a" * 40,
        "arm": "seeded", "iteration": 0, "tool": "circt-opt", "argv_json": "[]",
        "polarity": "expect_zero", "shape": "plain", "input_path": "in.mlir",
        "mutator_id": None, "mutator_seed_int": None, "source_test_path": None,
        "spec_json": "{}", "artefact_dir": str(tmp_path)})
    store.insert("candidate", {
        "candidate_id": candidate_id, "local_id": None, "probe_id": probe_id,
        "run_manifest_id": "r" * 32, "arm": "seeded", "run_commit": "c" * 40,
        "image_digest": "sha256:" + "0" * 64, "oracle_class": "assertion",
        "assertion_text": 'op && "null op"',
        "assertion_site": "/workspace/circt/lib/Dialect/HW/HWOps.cpp:412",
        "frame_tuple_json": "[]", "out_of_scope_root": 0,
        "contaminated_symbol": 0, "contaminated_file": 0,
        "contamination_lower_bound": "seed_commit", "triage_class": "bug",
        "held_reason": held, "taxonomy_bucket": "new_bug",
        "artefact_dir": str(tmp_path), "created_utc": "2026-09-14T00:00:00+00:00"})
    store.insert("reduced_case", {
        "probe_id": probe_id, "reducer": "circt-reduce", "reduced": 1,
        "fixpoint": 1, "budget_truncated": 0, "reason": None, "lift": None,
        "path": str(reduced), "size_before_bytes": 200, "size_after_bytes": 60,
        "size_before_ops": 6, "size_after_ops": 2, "wall_seconds": 1.0,
        "interestingness_calls": 5, "recheck_class": "assertion",
        "recheck_assertion_text": 'op && "null op"',
        "recheck_assertion_site": "HWOps.cpp:412", "recheck_matches": 1})
    store.insert("fingerprint", {
        "candidate_id": candidate_id, "basis": "assertion", "value": FINGERPRINT,
        "fingerprint_stable": 1, "frame_tuple_json": "[]",
        "structural_hash": "0" * 64})
    store.insert("dedup_verdict", {
        "candidate_id": candidate_id, "verdict": dedup,
        "evidence_json": json.dumps(evidence, sort_keys=True)})
    store.insert("report", {
        "candidate_id": candidate_id, "path": str(APPROVE / report),
        "template": "primary",
        "title": "circt-opt crashes in LowerTypes on a zero-width aggregate",
        "classification": "bug", "classification_reason": "An assertion fired.",
        "rendered_sha256": "a" * 64,
        "assisted_by": "circt_bug_loop:vertex:gemini-3.8-flash",
        "fields_present_json": "[]"})
    store.insert("gate_decision", {
        "candidate_id": candidate_id, "answers_json": json.dumps(_answers()),
        "stopped_at_question": None, "decision": decision,
        "taxonomy_bucket": "new_bug", "decided_utc": "2026-09-14T00:00:00+00:00"})
    if diff is not None:
        patch = tmp_path / f"{candidate_id}.fix.diff"
        patch.write_text(diff, encoding="utf-8")
        store.insert("repair", {
            "candidate_id": candidate_id, "local_id": 900_000_007,
            "status": "fixed", "failing_phase": None, "reproduced": 1,
            "build_ok": 1, "fixed": 1, "lit_ok": 1, "lit_unusable": 0,
            "lit_passed": 1119, "lit_failed": 0, "lit_failures_json": "[]",
            "diff_path": str(patch), "diff_added": 2, "diff_removed": 1,
            "chia_artifact_dir": None, "chia_row_seen": 0,
            "repro_dir": str(tmp_path), "repro_overwritten": 0, "restore_ok": 1,
            "restore_hashes_match": 1, "restore_log": "",
            "backend": "vertex", "token_capture": "unavailable_remote_dispatch"})
    return candidate_id


POSTED = {"forum_post_url": "https://discourse.llvm.org/t/circt-bug-loop/0",
          "forum_post_date": "2026-09-15"}


def _store(tmp_path, posted=True, **kwargs):
    store = LoopStore(str(tmp_path / "loop.db"))
    store.insert("run", {
        "run_manifest_id": "r" * 32, "mode": "discovery", "seed_set": "187",
        "manifest_json": json.dumps(POSTED if posted else {}),
        "budget_file_sha": "x", "cluster_yaml_sha": "y",
        "artefact_root": str(tmp_path), "started_utc": "2026-09-14T00:00:00+00:00",
        "ended_utc": None})
    store.insert("image", {
        "image_digest": "sha256:" + "0" * 64, "circt_sha": "e" * 40,
        "sdk_tag": "firtool-1.143.0", "image_tag": "t", "flag_string": "-UNDEBUG",
        "targets_json": "[]", "cmake_args_json": "[]", "verilator_version": "5.028",
        "slang_enabled": 1, "lit_discovery_ok": 1, "lit_discovered_count": 1,
        "assertion_nonreferencing_json": "[]", "tool_hashes_json": "{}",
        "built_utc": "2026-09-14T00:00:00+00:00"})
    _case(store, tmp_path, "cand-0001", **kwargs)
    return store


def _budget(tmp_path, **over):
    """A copy of the committed `budget.yaml` with FR-13.8's caps overridden."""
    import yaml

    payload = yaml.safe_load(BUDGET.read_text())
    payload.update(over)
    path = tmp_path / "budget.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return str(path)


def _run(tmp_path, *argv, budget=None, answers=(), out=None):
    """Drive the CLI, feeding *answers* to its `input()` prompts in order."""
    import builtins
    import io

    queue = list(answers)
    printed = out if out is not None else io.StringIO()

    def _input(prompt=""):
        printed.write(prompt)
        if not queue:
            raise EOFError("the human walked away")
        return queue.pop(0)

    original = builtins.input
    builtins.input = _input
    try:
        status = main([f"--db={tmp_path / 'loop.db'}",
                       f"--budget={budget or _budget(tmp_path)}", *argv],
                      out=printed)
    finally:
        builtins.input = original
    return status, printed.getvalue()


def _digest(tmp_path):
    """The database file's bytes, for the "nothing is written" assertions."""
    return hashlib.sha256((tmp_path / "loop.db").read_bytes()).hexdigest()


def _filing(store, candidate_id="cand-0001"):
    return store.query_one("SELECT * FROM filing WHERE candidate_id = ?",
                           (candidate_id,))


def _record_filing(store, candidate_id, approved_at, *, decision="report"):
    store.insert("filing", {
        "candidate_id": candidate_id, "approver": "someone",
        "approved_at_utc": approved_at, "decision": decision,
        "licence_confirmed": None, "licence_confirmed_at_utc": None,
        "url_source": None, "issue_number": None, "issue_url": None,
        "prefill_url_length": None, "prefill_fallback_reason": None,
        "confirmed": 0, "confirmed_at_utc": None, "confirmation_url": None})


def _today():
    from circt_bug_loop.approve import _utc

    return _utc()[:10]


def test_appr_01_the_per_day_cap_is_enforced_before_the_human_is_asked(tmp_path):
    """T-U-appr-01 (FR-13.8): with `filings_per_day` 1 and one filing already recorded for the current UTC day, the second candidate is held, the refusal happens before anything is shown, and nothing is written."""
    store = _store(tmp_path)
    _case(store, tmp_path, "cand-0002")
    _record_filing(store, "cand-0001", f"{_today()}T01:00:00+00:00")
    before = _digest(tmp_path)

    status, text = _run(tmp_path, "approve", "cand-0002", "--by", "adi",
                        budget=_budget(tmp_path, filings_per_day=1))
    assert status == 2
    assert "per-UTC-day filing cap is 1" in text
    assert "--- report ---" not in text, "the human is not shown a held report"
    assert _digest(tmp_path) == before
    assert _filing(store, "cand-0002") is None


def test_appr_02_the_total_cap_is_enforced_the_same_way(tmp_path):
    """T-U-appr-02 (FR-13.8): `filings_total` refuses before presentation too."""
    store = _store(tmp_path)
    _case(store, tmp_path, "cand-0002")
    _record_filing(store, "cand-0001", "2026-01-01T01:00:00+00:00")
    status, text = _run(tmp_path, "approve", "cand-0002", "--by", "adi",
                        budget=_budget(tmp_path, filings_per_day=9,
                                       filings_total=1))
    assert status == 2 and "total filing cap is 1" in text
    assert "--- report ---" not in text


def test_appr_03_a_good_first_issue_match_is_refused(tmp_path):
    """T-U-appr-03 (FR-13.9): a candidate whose `dedup_evidence` carries `good first issue` is refused whatever the rest of the gate said, with the label named, and no filing is possible as an issue, a comment or a fix - there being exactly one writer of a `filing` row."""
    store = _store(tmp_path, labels=["bug", "good first issue"],
                   dedup="known_open_issue")
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi")
    assert status == 2
    assert "good first issue" in text and "#10681" in text
    assert "newcomers" in text
    assert _filing(store) is None

    source = Path(approve.__file__).read_text()
    assert source.count('store.insert("filing"') == 1


def test_appr_04_a_held_candidate_is_not_presented(tmp_path):
    """T-U-appr-04 (FR-11.8): `held_reason=no_report` is not presented."""
    store = _store(tmp_path, held="no_report")
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi")
    assert status == 2 and "no_report" in text and "FR-11.8" in text
    assert _filing(store) is None


def test_appr_05_a_second_approval_names_the_first(tmp_path):
    """T-U-appr-05 (FR-13.13): a second approval of an already-approved candidate is refused, naming the first approval's timestamp."""
    store = _store(tmp_path)
    _record_filing(store, "cand-0001", "2026-09-14T01:02:03+00:00")
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi")
    assert status == 2
    assert "2026-09-14T01:02:03+00:00" in text and "someone" in text


def test_appr_05b_a_refused_candidate_cannot_be_approved(tmp_path):
    """§13.2's `refuse`: a human rejection is recorded and no filing follows."""
    store = _store(tmp_path)
    status, _ = _run(tmp_path, "refuse", "cand-0001", "--reason", "not a bug")
    assert status == 0
    held = store.query_one("SELECT held_reason FROM candidate WHERE candidate_id = ?",
                           ("cand-0001",))["held_reason"]
    assert held == f"{REFUSED_PREFIX} not a bug"

    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi")
    assert status == 2 and "not a bug" in text
    assert _filing(store) is None


def test_appr_06_approval_does_not_generalise(tmp_path):
    """T-U-appr-06 (FR-13.13): two pending reports need two approvals; approving one leaves the other pending and `list` still shows it."""
    store = _store(tmp_path)
    _case(store, tmp_path, "cand-0002")
    status, _ = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                     answers=["yes"])
    assert status == 0
    assert _filing(store) is not None
    assert _filing(store, "cand-0002") is None

    status, listing = _run(tmp_path, "list")
    assert status == 0
    assert "cand-0002" in listing and "cand-0001" not in listing
    assert "1 pending" in listing


def test_appr_09_show_prints_all_four_in_one_view(tmp_path):
    """T-U-appr-09 (FR-13.12): the full rendered report, the four gate answers with the stopping question, the repair diff, and the reduced case."""
    store = _store(tmp_path, decision="report_plus_patch",
                   diff="--- a/lib/Dialect/HW/HWOps.cpp\n+  return failure();\n")
    before = _digest(tmp_path)
    status, text = _run(tmp_path, "show", "cand-0001")

    assert status == 0
    for heading in ("--- report ---", "--- the four gate answers ---",
                    "--- repair diff ---", "--- reduced case ---"):
        assert heading in text
    assert "circt-opt crashes in LowerTypes" in text
    for key in ("q1_reproduce", "q2_minimal", "q3_valid", "q4_new"):
        assert key in text
    assert "stopped at question: none, all four passed" in text
    assert "return failure();" in text
    assert "hw.module @bugloop" in text
    assert _digest(tmp_path) == before, "show is read-only"


def test_appr_07_the_licence_is_taken_with_the_patch_on_screen(tmp_path):
    """T-U-appr-07 (FR-20.5): the confirmation is asked for only where the decision is `report_plus_patch`, with the patch already on screen, and a decline downgrades the decision to `report` and is recorded."""
    store = _store(tmp_path, decision="report_plus_patch",
                   diff="--- a/lib/Dialect/HW/HWOps.cpp\n+  return failure();\n")
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                        answers=["yes", "yes"])
    assert status == 0
    assert text.index("return failure();") < text.index("Apache-2.0")
    row = _filing(store)
    assert row["decision"] == "report_plus_patch"
    assert row["licence_confirmed"] == 1
    assert row["licence_confirmed_at_utc"].endswith("+00:00")


def test_appr_07b_a_declined_licence_downgrades_the_decision(tmp_path):
    """FR-20.5: a `report_plus_patch` without a recorded confirmation is downgraded by the code path, and the decline itself is recorded."""
    store = _store(tmp_path, decision="report_plus_patch", diff="--- a/x\n+y\n")
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                        answers=["yes", "no"])
    assert status == 0 and "downgraded to 'report'" in text
    row = _filing(store)
    assert row["decision"] == "report"
    assert row["licence_confirmed"] == 0
    assert row["licence_confirmed_at_utc"] is not None


def test_appr_07c_no_licence_is_asked_for_a_report_without_a_patch(tmp_path):
    """FR-20.5 is about a patch; a plain `report` is never asked and the field stays NULL, which is what "never defaulted" means in both directions."""
    store = _store(tmp_path)
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                        answers=["yes"])
    assert status == 0 and "Apache-2.0" not in text
    assert _filing(store)["licence_confirmed"] is None


def test_appr_08_walking_away_writes_nothing(tmp_path):
    """T-U-appr-08 (FR-13.7): interrupting between presentation and the typed `yes` leaves the candidate held with `held_reason=awaiting_approval`, no `filing` row, and the next invocation presenting the same report."""
    store = _store(tmp_path)
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                        answers=["no"])
    assert status == 1 and "nothing written" in text
    assert _filing(store) is None
    assert store.query_one("SELECT held_reason FROM candidate WHERE "
                           "candidate_id = ?", ("cand-0001",))["held_reason"] == AWAITING

    status, again = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                         answers=["yes"])
    assert status == 0, "an awaiting_approval hold does not refuse the re-ask"
    assert "circt-opt crashes in LowerTypes" in again
    assert _filing(store) is not None
    assert store.query_one("SELECT held_reason FROM candidate WHERE "
                           "candidate_id = ?", ("cand-0001",))["held_reason"] is None


def test_appr_12_the_filing_row_carries_the_approver_and_the_timestamp(tmp_path):
    """T-U-appr-12 (FR-13.7): the row names who approved, when, what was approved, and the licence confirmation with its own timestamp."""
    store = _store(tmp_path)
    _run(tmp_path, "approve", "cand-0001", "--by", "Adithya J", answers=["yes"])
    row = _filing(store)
    assert row["approver"] == "Adithya J"
    assert row["approved_at_utc"].startswith(_today())
    assert row["approved_at_utc"].endswith("+00:00")
    assert row["decision"] == "report"
    assert row["confirmed"] == 0 and row["issue_url"] is None


def test_appr_14_nothing_files_by_default(tmp_path):
    """T-U-appr-14 (FR-13.7): every command but `approve` leaves the `filing` table empty, and a walkthrough with no approval produces zero."""
    store = _store(tmp_path)
    _case(store, tmp_path, "cand-0002")
    before = _digest(tmp_path)
    for argv in (["list"], ["show", "cand-0001"], ["url", "cand-0001"]):
        assert _run(tmp_path, *argv)[0] == 0
    assert store.query_one("SELECT COUNT(*) AS n FROM filing")["n"] == 0
    assert _digest(tmp_path) == before


def test_appr_14b_the_gate_decides_who_reaches_a_human(tmp_path):
    """FR-13.10: only `report` and `report_plus_patch` reach a human; a candidate the gate decided `nothing` about is refused and never listed."""
    store = _store(tmp_path, decision="nothing")
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi")
    assert status == 2 and "'nothing'" in text
    assert _run(tmp_path, "list")[1].startswith("0 pending")
    assert _filing(store) is None


def test_appr_10_the_prefilled_url_is_measured_before_it_is_offered(tmp_path):
    """T-U-appr-10 (FR-13.17): a report under the limit produces the pre-filled link; one over it produces the hand-filing instruction and records both the length and the reason."""
    short = APPROVE / "short.md"
    url, length, reason = prefill("t", short.read_text())
    assert url.startswith("https://github.com/llvm/circt/issues/new?title=")
    assert "body=" in url and length == len(url) <= PREFILL_URL_CHAR_LIMIT
    assert reason is None

    title = "circt-opt crashes in LowerTypes on a zero-width aggregate"
    nothing, over, why = prefill(title, (APPROVE / "long.md").read_text())
    assert nothing is None and over > PREFILL_URL_CHAR_LIMIT
    assert why == f"prefill_url_{over}_chars_over_{PREFILL_URL_CHAR_LIMIT}"

    store = _store(tmp_path, report="long.md")
    _run(tmp_path, "approve", "cand-0001", "--by", "adi", answers=["yes"])
    text = _run(tmp_path, "url", "cand-0001")[1]
    assert "File it by hand" in text and "paste the whole of" in text
    row = _filing(store)
    assert row["prefill_url_length"] == over
    assert row["prefill_fallback_reason"] == why


def test_appr_10b_the_approval_prints_the_url_it_recorded(tmp_path):
    """FR-13.18: one interface owns both halves, so the approval ends with the link rather than sending the human to a second tool."""
    store = _store(tmp_path)
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                        answers=["yes"])
    assert status == 0
    assert "https://github.com/llvm/circt/issues/new?title=" in text
    assert _filing(store)["prefill_url_length"] > 0


@pytest.mark.parametrize("url", [
    "https://github.com/llvm/circt/pulls/1",
    "https://github.com/other/repo/issues/1",
    "http://github.com/llvm/circt/issues/1",
    "https://github.com.evil.example/llvm/circt/issues/1",
    "https://github.com/llvm/circt/issues/new",
    "https://github.com/llvm/circt/issues/1/comments",
])
def test_appr_11_the_url_conjunction_is_on_the_accept_side(tmp_path, url):
    """T-U-appr-11 (FR-13.18): a URL is accepted only when its scheme **is** https, its host **is** exactly github.com, its path **begins** `/llvm/circt/issues/` and it **ends in digits**."""
    assert issue_number(url) is None
    store = _store(tmp_path)
    _run(tmp_path, "approve", "cand-0001", "--by", "adi", answers=["yes"])
    status, text = _run(tmp_path, "filed", "cand-0001", url)
    assert status == 2 and "refused" in text
    assert _filing(store)["issue_url"] is None


def test_appr_11b_a_pasted_url_is_recorded_against_the_same_report(tmp_path):
    """T-U-appr-11 (FR-13.18): `filed` records the URL where the poll found nothing, with `url_source="pasted"`, against the same report id."""
    store = _store(tmp_path)
    assert issue_number("https://github.com/llvm/circt/issues/11200") == 11200

    status, text = _run(tmp_path, "filed", "cand-0001",
                        "https://github.com/llvm/circt/issues/11200")
    assert status == 2 and "no approval" in text

    _run(tmp_path, "approve", "cand-0001", "--by", "adi", answers=["yes"])
    status, text = _run(tmp_path, "filed", "cand-0001",
                        "https://github.com/llvm/circt/issues/11200")
    assert status == 0 and "#11200" in text
    row = _filing(store)
    assert row["issue_number"] == 11200
    assert row["issue_url"] == "https://github.com/llvm/circt/issues/11200"
    assert row["url_source"] == "pasted"


def _fake_issues(monkeypatch, issues):
    """A stand-in `GithubIssuesNode` that lists and nothing else (NFR-04)."""
    import chia.github.github_issues_node as module

    calls = []

    class _Node:
        def __init__(self, repo, token=None, state="all"):
            calls.append({"repo": repo, "state": state})

        def recent(self, n, fetch_comments=True):
            calls[-1].update({"n": n, "fetch_comments": fetch_comments})
            return issues

    monkeypatch.setattr(module, "GithubIssuesNode", _Node)
    return calls


def test_appr_13_the_poll_matches_on_the_primary_fingerprint(tmp_path, monkeypatch):
    """T-U-appr-13 (FR-13.16): a filed issue whose body carries the report's primary fingerprint completes the `FilingRecord` with `url_source="poll"`, using a GET listing only; an empty poll falls back to the paste and says so."""
    store = _store(tmp_path)
    token = tmp_path / "token"
    token.write_text("synthetic-not-a-real-token")
    os.chmod(token, 0o600)
    _run(tmp_path, "approve", "cand-0001", "--by", "adi", answers=["yes"])

    miss = types.SimpleNamespace(number=1, url="u", body="an unrelated issue")
    calls = _fake_issues(monkeypatch, [miss])
    status, text = _run(tmp_path, f"--github-token-file={token}", "poll")
    assert status == 0 and "no issue carries its fingerprint" in text
    assert "0 of 1 completed" in text
    assert _filing(store)["issue_url"] is None

    hit = types.SimpleNamespace(
        number=11200, url="https://github.com/llvm/circt/issues/11200",
        body=f"## Fingerprint\n{FINGERPRINT}\n")
    _fake_issues(monkeypatch, [miss, hit])
    status, text = _run(tmp_path, f"--github-token-file={token}", "poll")
    assert status == 0 and "matched issue #11200" in text
    row = _filing(store)
    assert row["issue_number"] == 11200 and row["url_source"] == "poll"

    assert all(call["fetch_comments"] is False for call in calls), (
        "no maintainer's words are fetched (FR-20.4)")
    assert all(call["repo"] == "llvm/circt" for call in calls)

    status, text = _run(tmp_path, f"--github-token-file={token}", "poll")
    assert "no filing awaits a URL" in text


def test_appr_15_the_module_entry_runs_as_a_program(tmp_path):
    """T-U-appr-15 (FR-13.12): §13.2's entry, exercised as a program."""
    _store(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-m", "circt_bug_loop.approve",
         f"--db={tmp_path / 'loop.db'}", f"--budget={BUDGET}", "list"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[2]))
    assert completed.returncode == 0, completed.stderr
    assert "cand-0001" in completed.stdout and "1 pending" in completed.stdout

    usage = subprocess.run(
        [sys.executable, "-m", "circt_bug_loop.approve", "--help"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[2]))
    for command in ("list", "show", "approve", "refuse", "url", "filed", "poll"):
        assert command in usage.stdout, command


def test_appr_16_an_unknown_candidate_is_a_lookup_error(tmp_path):
    """T-U-appr-16 (FR-13.12): a typo in a candidate id is refused loudly rather than writing nothing quietly, which is the failure mode a human would not notice."""
    _store(tmp_path)
    with pytest.raises(LookupError, match="cand-9999"):
        _run(tmp_path, "show", "cand-9999")


def test_appr_17_the_view_survives_a_missing_patch_and_a_missing_report(tmp_path):
    """T-U-appr-17 (FR-13.12): the view is rendered for every candidate that reaches it, held ones included, so a hold is visible rather than being a blank screen."""
    store = _store(tmp_path, held="no_report")
    store.update("report", {"candidate_id": "cand-0001"}, {"path": "/nonexistent"})
    store.transaction([("DELETE FROM report WHERE candidate_id = ?", ("cand-0001",))])
    text = render_view(approve.load_case(store, "cand-0001"))
    assert "no report was rendered" in text
    assert "no repair attempt" in text
    assert "hw.module @bugloop" in text


def test_appr_15_no_filing_before_the_forum_post(tmp_path):
    """T-U-appr-15 (FR-20.1): a run whose manifest records no forum post cannot approve a filing."""
    store = _store(tmp_path, posted=False)
    status, text = _run(tmp_path, "approve", "cand-0001", "--by", "adi", answers=["yes"])
    assert status == 2 and "FR-20.1" in text and "--forum-post-url" in text
    assert _filing(store) is None


def test_appr_15b_the_post_is_recorded_at_approval_and_the_filing_proceeds(tmp_path):
    """T-U-appr-15b (FR-20.1): the approver records the post's URL and date on the run, and the same invocation approves."""
    from circt_bug_loop import approve

    store = _store(tmp_path, posted=False)
    status, _ = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                     "--forum-post-url", POSTED["forum_post_url"],
                     "--forum-post-date", POSTED["forum_post_date"], answers=["yes"])
    assert status == 0 and _filing(store) is not None
    manifest = approve.run_manifest(store, "r" * 32)
    assert manifest["forum_post_url"] == POSTED["forum_post_url"]
    assert manifest["forum_post_date"] == POSTED["forum_post_date"]
    assert approve.forum_posted(manifest)
    assert not approve.forum_posted({"forum_post_url": "none: not posted", "forum_post_date": "none: not posted"})


def test_appr_16_the_newest_screen_and_gate_rows_are_the_ones_read(tmp_path):
    """T-U-appr-16 (D-11): `--rescreen` appends its rows, and both the view and `list` read the newest of each, once."""
    from circt_bug_loop.store import make_appendable

    store = _store(tmp_path, dedup="fixed_post_pin", decision="nothing")
    _case(store, tmp_path, "cand-0002")
    make_appendable(store)
    evidence = dict.fromkeys(EVIDENCE)
    evidence["rescreened_from"] = "1"
    store.insert("dedup_verdict", {
        "candidate_id": "cand-0001", "verdict": "new",
        "evidence_json": json.dumps(evidence, sort_keys=True)})
    for candidate_id in ("cand-0001", "cand-0002"):
        store.insert("gate_decision", {
            "candidate_id": candidate_id,
            "answers_json": json.dumps({**_answers(), "rescreened_from": "1"}),
            "stopped_at_question": None, "decision": "report",
            "taxonomy_bucket": "new_bug",
            "decided_utc": "2026-09-20T00:00:00+00:00"})

    case = approve.load_case(store, "cand-0001")
    assert case["dedup"]["verdict"] == "new", "the rescreened verdict, not the old one"
    assert case["gate"]["decision"] == "report"
    assert json.loads(case["dedup"]["evidence_json"])["rescreened_from"] == "1"

    status, listing = _run(tmp_path, "list")
    assert status == 0 and "2 pending" in listing
    for candidate_id in ("cand-0001", "cand-0002"):
        assert listing.count(candidate_id) == 1, "one line per candidate"
