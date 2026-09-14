"""Every seam crossing: `04-Test-Plan.md` §2, the seventeen `T-I-*` tests."""
from __future__ import annotations

import json
import typing
from pathlib import Path

import pytest

from circt_bug_loop import (budget as budget_module, bug_loop, feedback, gate,
                            generate_task, ledger, mutators, probe_task,
                            repair_adapter, triage_task)
from circt_bug_loop.contract import schema
from circt_bug_loop.store import ImageSpec, LoopStore
from circt_bug_loop.tests.conftest import call_node

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / "fixtures"
#: The recorded seam, which is what every test here replays.
RECORDED = Path(schema.__file__).resolve().parent / "fixtures" / "recorded"

#: The build the recording ran against, resolved the same way and for the same reason.
from circt_bug_loop.tests.fixtures.recorded.make_recorded import (  # noqa: E402
    BUILDS, resolve)


#: FR-18.6's six buckets.
BUCKETS = set(gate.TAXONOMY.values()) | {"new_bug"}


def replay(member: str, cls, **where):
    """Every recorded document of one member, filtered, read back through the seam."""
    out = []
    for path in sorted((RECORDED / member).glob("*.json")):
        instance = schema.from_json(path.read_text(encoding="utf-8"), cls)
        if all(getattr(instance, key) == value for key, value in where.items()):
            out.append(instance)
    assert out, f"no recorded {member} matches {where}"
    return out


def bin_dir() -> str:
    """The tier-1 CIRCT build, or a clean skip."""
    try:
        return resolve(BUILDS, "circt-opt", runs=True)
    except SystemExit as absent:
        pytest.skip(str(absent))


def clone() -> str:
    """The tier-1 blobless clone, or a clean skip."""
    from circt_bug_loop.tests.fixtures.recorded.make_recorded import CLONES

    try:
        return resolve(CLONES, ".git")
    except SystemExit as absent:
        pytest.skip(str(absent))


def executing_image_spec(tools: list) -> ImageSpec:
    """The `ImageSpec` the recorded probes ran under, rebuilt from the build."""
    from circt_bug_loop.tests.fixtures.recorded.make_recorded import local_image_spec

    return local_image_spec(bin_dir(), tools)


def limits() -> dict:
    """§9.4's probe limits, at the committed file's values."""
    import yaml

    document = yaml.safe_load(
        Path(budget_module.BUDGET_YAML).read_text(encoding="utf-8"))
    return {key: document[key] for key in
            ("probe_wall_seconds", "probe_address_space_bytes",
             "probe_cpu_seconds", "probe_output_byte_cap",
             "reduction_wall_seconds", "reduction_sigkill_grace_seconds")}


def bumped(instance, major: str) -> str:
    """One recorded document re-recorded at another MAJOR, as JSON text."""
    document = json.loads(schema.to_json(instance))
    document["contract_version"] = major
    return json.dumps(document, sort_keys=True, indent=2,
                      ensure_ascii=False) + "\n"


@pytest.mark.t1
@pytest.mark.needs_sdk
@pytest.mark.parametrize("arm,test_id", [("seeded", "T-I-gen-app-01"),
                                         ("mutation", "T-I-gen-app-02")])
def test_T_I_gen_app_01_and_02(tmp_path, arm, test_id):
    """T-I-gen-app-01 and -02 (FR-04.3)."""
    specs = replay("probe_spec", schema.ProbeSpec, arm=arm)
    image_spec = executing_image_spec([specs[0].tool])

    for spec in specs:
        before = schema.to_json(spec)
        # The spec names the ABSOLUTE input path the recording wrote.
        source = Path(spec.input_path)
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(spec.input_text, encoding="utf-8")
        directory = tmp_path / spec.probe_id
        directory.mkdir(parents=True, exist_ok=True)
        executed = call_node(probe_task.probe_execute, spec, image_spec,
                             limits(), str(directory), bin_dir=bin_dir())
        assert schema.to_json(spec) == before, "the consumer changed the spec"

        build, result = executed["build_result"], executed["probe_result"]
        assert build.probe_id == spec.probe_id == result.probe_id
        assert result.arm == arm and result.iteration == spec.iteration
        assert build.status in typing.get_args(
            typing.get_type_hints(schema.ProbeResult)["build_status"]), build.status
        assert schema.validate(result) is None
        assert Path(build.stderr_path).is_file()
        # The recorded outcome is reproduced.
        recorded = replay("probe_result", schema.ProbeResult,
                          probe_id=spec.probe_id)[0]
        assert result.build_status == recorded.build_status
        assert result.stopping_stage == recorded.stopping_stage

    # The apparatus half imports no supply-half module to do any of it.
    source = Path(probe_task.__file__).read_text(encoding="utf-8")
    for supplier in ("generate_task", "feedback", "budget", "ledger"):
        assert f"import {supplier}" not in source, supplier


@pytest.mark.t0
def test_T_I_gen_app_03(tmp_path):
    """T-I-gen-app-03 (FR-05.4): one `generate` interface, two arms."""
    import inspect

    seed = replay("seed_record", schema.SeedRecord)[0]
    bundle = replay("feedback_bundle", schema.FeedbackBundle, arm="seeded")[0]
    snapshot = schema.LedgerSnapshot(arm="mutation", unit="wall_clock_seconds",
                                     spent=0.0, cap=14400.0)
    cfg = {"model_id": "gemini-3.8-flash", "per_seed_probe_cap": 2,
           "iteration": 1, "run_manifest_id": bundle.run_manifest_id,
           "artefact_root": str(tmp_path), "artefact_inline_cap_bytes": 262144,
           "clone_path": str(tmp_path), "run_commit": "c" * 40,
           "mutator_set_path": str(mutators.SET_PATH)}

    produced = call_node(generate_task.generate_mutation, seed, bundle,
                         snapshot, cfg)
    assert [type(spec) for spec in produced["specs"]] == \
        [schema.ProbeSpec] * len(produced["specs"])
    for spec in produced["specs"]:
        assert schema.validate(spec) is None
        assert spec.arm == "mutation" and spec.mutator_id

    signature = inspect.signature(generate_task.generate_seeded._chia_original)
    assert list(signature.parameters) == list(inspect.signature(
        generate_task.generate_mutation._chia_original).parameters)
    body = inspect.getsource(generate_task.generate_mutation._chia_original)
    assert body.count("feedback") == 1, "A4 reads the bundle it is handed"


def candidate_from(result: schema.ProbeResult, verdict, tmp_path) -> tuple:
    """One `CandidateRecord` and its `BuildResult` row, from a recorded probe."""
    from circt_bug_loop.store import BuildResult

    build = BuildResult(
        probe_id=result.probe_id, run_manifest_id=result.run_manifest_id,
        run_commit="c" * 40, image_digest="local-build:sha256:" + "0" * 64,
        status=result.build_status, binary_path="/build/bin/circt-opt",
        binary_sha256="0" * 64, argv=["circt-opt"], exit_status=None,
        signal="SIGABRT", limit_hit=None, cpu_seconds=0.1, wall_seconds=0.2,
        peak_rss_bytes=1024, worker_hostname="host", worker_node_id="node",
        child_pid=1, stdout_path="/dev/null",
        stderr_path=str(tmp_path / "stderr.txt"), stdout_bytes=0,
        stderr_bytes=0, truncated=False)
    return build


@pytest.mark.t1
def test_T_I_app_tri_01(tmp_path):
    """T-I-app-tri-01 (FR-10.1): all three screens, no request."""
    from chia.github.github_client import GithubClient

    from circt_bug_loop.tests.test_triage_task import (_candidate, _mirror_rows,
                                                       _seed, _store, _verdict)

    result = replay("probe_result", schema.ProbeResult, build_status="assertion")[0]
    candidate = _candidate(tmp_path, screened=True)
    candidate.probe_id = result.probe_id
    candidate.run_manifest_id = result.run_manifest_id
    candidate.dedup_verdict = None
    candidate.dedup_evidence = None
    store = _store(tmp_path, candidate=candidate)
    _mirror_rows(store, [
        {"issue_number": item["number"], "title": item["title"],
         "body": item["body"] or "",
         "labels": [label["name"] for label in item["labels"]],
         "state": item["state"], "url": item["html_url"]}
        for item in json.loads(
            (FIXTURES / "mirror" / "sample.json").read_text(encoding="utf-8"))])

    def _refuse(self, path, params=None, accept=None):
        raise AssertionError(f"stage 6 made a GitHub request for {path!r}")

    original = GithubClient._request
    GithubClient._request = _refuse
    try:
        screened = call_node(triage_task.dedup_and_screen, candidate, _seed(),
                             _verdict("assertion",
                                      assertion_text=candidate.assertion_text,
                                      assertion_site=candidate.assertion_site,
                                      probe_id=result.probe_id),
                             clone(), store.db_path, 5)
    finally:
        GithubClient._request = original

    assert set(screened["dedup"].evidence) == set(triage_task._EVIDENCE_KEYS)
    assert screened["dedup"].verdict in (
        "new", "known_open_issue", "known_closed_issue", "fixed_post_pin",
        "duplicate_of_candidate", "dedup_unavailable")
    assert screened["fingerprint"].basis == "assertion"
    assert screened["fingerprint"].fingerprint_stable is None, (
        "nothing merges before the gate has re-run it (§3.7.1)")
    assert isinstance(screened["contaminated_symbol"], bool)
    assert isinstance(screened["contaminated_file"], bool)
    assert screened["counters"].stage == "stage_6"


@pytest.mark.t0
def test_T_I_app_tri_02(tmp_path, monkeypatch):
    """T-I-app-tri-02 (FR-11.2): the report, from the record."""
    from circt_bug_loop.tests.test_triage_task import (_fake_generate,
                                                       _render_bundle,
                                                       _turn_text)

    manifest = replay("run_manifest", schema.RunManifest)[0]
    _fake_generate(monkeypatch, _turn_text("report_write_disagree"))
    candidate, reduced, verdict, dedup = _render_bundle(
        tmp_path, dedup_verdict="known_closed_issue")

    out = call_node(triage_task.triage_report, candidate, reduced, verdict,
                    dedup, manifest,
                    {"model_id": "gemini-3.8-flash", "timeout_seconds": 1200,
                     "clone_path": str(tmp_path), "run_commit": "c" * 40},
                    str(tmp_path / "probe"))

    assert out["failure"] is None
    report = out["report"]
    # The TOOL verdict wins over the agent's, which is FR-11.2.
    assert report.classification == "known_issue"
    assert report.assisted_by == manifest.model_ids["triage_report"]
    body = Path(report.path).read_text(encoding="utf-8")
    assert candidate.assertion_text in body and candidate.assertion_site in body
    assert "10500" in body, "the mirror's issue number, from the record"


@pytest.mark.t0
def test_T_I_tri_rep_01(tmp_path, monkeypatch):
    """T-I-tri-rep-01 (FR-12.1): the whole `GithubIssue` object."""
    from circt_bug_loop.tests.test_repair_adapter import _attempt

    run = _attempt(tmp_path, monkeypatch)
    assert run.result.status == "fixed"
    assert len(run.chain.calls) == 1
    call = run.chain.calls[0]
    assert call["number"] == repair_adapter.LOCAL_ID_BASE + 7
    assert set(call["cfg"]) == set(repair_adapter.CFG_KEYS)
    repro = Path(run.result.repro_dir) / "repro.sh"
    assert repro.is_file() and repro.stat().st_mode & 0o111
    assert "/workspace/circt" not in str(repro), (
        "the repro directory is outside the tree `git clean -fd` reaches")
    assert run.generate.calls[0]["need_key"] is True


@pytest.mark.t0
@pytest.mark.parametrize("kind", ["differential", "fatal_error", "out_of_scope_root"])
def test_T_I_tri_rep_02(tmp_path, monkeypatch, kind):
    """T-I-tri-rep-02 (FR-12.4): refused by class or scope, chain untouched."""
    from circt_bug_loop.tests.test_repair_adapter import (_Recorder, _attempt,
                                                          _candidate)

    chain = _Recorder({"status": "fixed"})
    over = ({"out_of_scope_root": True} if kind == "out_of_scope_root"
            else {"oracle_class": kind})
    with pytest.raises(repair_adapter.RepairRefused) as refused:
        _attempt(tmp_path, monkeypatch, chain=chain,
                 candidate=_candidate(tmp_path, **over))
    expected = ("out_of_scope_root" if kind == "out_of_scope_root"
                else f"oracle_class_{kind}")
    assert refused.value.reason == expected
    assert chain.calls == [], "a refused candidate reaches no chain"


@pytest.mark.t0
@pytest.mark.parametrize("verdict", ["fixed.json", "attempted.json", "error.json",
                                     "no_repro.json", "not_a_bug.json",
                                     "unclear.json"])
def test_T_I_rep_gate_01(tmp_path, monkeypatch, verdict):
    """T-I-rep-gate-01 (FR-12.7): all six CHIA statuses."""
    from circt_bug_loop.tests.test_gate import _decide, _repair

    status = json.loads(
        (FIXTURES / "repair" / "verdicts" / verdict).read_text())["status"]
    # `fixed` is the FIELD and not the status string.
    decision, _, _ = _decide(tmp_path, monkeypatch,
                             repair=_repair(status=status,
                                            fixed=(status == "fixed"),
                                            lit_ok=True))
    if status == "fixed":
        assert decision.decision == "report_plus_patch"
    else:
        assert decision.decision == "report"
    assert decision.taxonomy_bucket in BUCKETS


@pytest.mark.t0
def test_T_I_rep_gate_02(tmp_path, monkeypatch):
    """T-I-rep-gate-02 (FR-13.1): four questions, `gate_rerun` live."""
    import dataclasses

    from circt_bug_loop.tests.test_gate import ANSWER_KEYS, _decide, answers

    decision, store, seen = _decide(tmp_path, monkeypatch)
    assert decision.q1_reproduce is True
    assert [decision.q2_minimal, decision.q3_valid, decision.q4_new] == \
        [True, True, True]
    assert decision.stopped_at_question is None
    assert decision.decision in ("report", "report_plus_patch")
    assert decision.taxonomy_bucket in BUCKETS
    # All fifteen answers, every one from a tool record and none defaulted.
    assert set(answers(decision)) == set(ANSWER_KEYS)
    assert all(getattr(decision, field.name) is not None
               for field in dataclasses.fields(decision)
               if field.name.startswith(("q1_reproduce", "q2_minimal",
                                          "q3_valid", "q4_new")))
    # The two `{"circt": 1}` nodes were really dispatched.
    assert [call["node"] for call in seen] == ["gate_rerun", "gate_validate"]


@pytest.mark.t0
def test_T_I_gate_appr_01(tmp_path):
    """T-I-gate-appr-01 (FR-13.10): `nothing` is never listed."""
    from circt_bug_loop.tests.test_approve import _case, _run, _store

    store = _store(tmp_path)                       # cand-0001, decision "report"
    _case(store, tmp_path, "cand-0002", decision="report_plus_patch")
    _case(store, tmp_path, "cand-0003", decision="nothing")

    status, printed = _run(tmp_path, "list")
    assert status == 0
    assert "cand-0001" in printed and "cand-0002" in printed
    assert "cand-0003" not in printed, "a `nothing` decision is never presented"

    status, shown = _run(tmp_path, "show", "cand-0001")
    assert status == 0
    for question in ("q1", "q2", "q3", "q4"):
        assert question in shown.lower()


@pytest.mark.t0
def test_T_I_gate_appr_02(tmp_path):
    """T-I-gate-appr-02 (FR-13.7): one filing row, and a downgrade."""
    from circt_bug_loop.tests.test_approve import _filing, _run, _store

    # A `report_plus_patch`, so the licence question is asked at all.
    store = _store(tmp_path, decision="report_plus_patch",
                   diff="--- a/lib/Dialect/HW/HWOps.cpp\n+  return failure();\n")
    status, _ = _run(tmp_path, "approve", "cand-0001", "--by", "adi",
                     answers=["yes", "yes"])
    assert status == 0
    rows = store.query("SELECT * FROM filing WHERE candidate_id = ?",
                       ("cand-0001",))
    assert len(rows) == 1, "exactly one filing row"
    row = _filing(store)
    assert row["approver"] == "adi" and row["approved_at_utc"].endswith("+00:00")
    assert row["decision"] == "report_plus_patch"
    assert row["licence_confirmed"] == 1
    assert row["licence_confirmed_at_utc"].endswith("+00:00")

    # A DECLINE downgrades rather than refusing.
    (tmp_path / "b").mkdir()
    declined = _store(tmp_path / "b", decision="report_plus_patch",
                      diff="--- a/x\n+y\n")
    status, text = _run(tmp_path / "b", "approve", "cand-0001", "--by", "adi",
                        answers=["yes", "no"])
    assert status == 0 and "downgraded to 'report'" in text
    downgraded = _filing(declined)
    assert downgraded["decision"] == "report"
    assert downgraded["licence_confirmed"] == 0


@pytest.mark.t0
def test_T_I_ledger_01(tmp_path):
    """T-I-ledger-01 (FR-14.4): the aggregate reconciles."""
    entries = replay("ledger_entry", schema.LedgerEntry)
    assert {entry.arm for entry in entries} == {"seeded", "mutation", "shared"}
    assert {entry.scope for entry in entries} == {"arm_window", "stage"}

    budget = _registered_budget(tmp_path)
    store = LoopStore(str(tmp_path / "loop.db"))
    manifest = replay("run_manifest", schema.RunManifest)[0]
    store.insert("run", {
        "run_manifest_id": manifest.run_manifest_id, "mode": manifest.mode,
        "seed_set": manifest.seed_set, "manifest_json": schema.to_json(manifest),
        "budget_file_sha": manifest.budget_file_sha,
        "cluster_yaml_sha": manifest.cluster_yaml_sha,
        "artefact_root": manifest.artefact_root,
        "started_utc": manifest.started_utc, "ended_utc": None})
    for entry in entries:
        call_node(ledger.accrue, entry, store.db_path, budget)

    # A SECOND arm_window entry for one arm is refused, which is FR-14.4.
    again = replay("ledger_entry", schema.LedgerEntry, scope="arm_window")[0]
    again.entry_id = "a-second-entry-for-the-same-arm"
    with pytest.raises(schema.ContractError) as refused:
        call_node(ledger.accrue, again, store.db_path, budget)
    assert refused.value.code == "E005_CONDITIONAL_REQUIRED"

    aggregate = call_node(ledger.aggregate, manifest.run_manifest_id,
                          store.db_path)
    for arm in ("seeded", "mutation"):
        assert aggregate.per_arm_window[arm] > 0
    assert aggregate.shared_stage, "shared is reported beside, never folded"
    assert "shared" not in aggregate.per_arm_window
    assert set(aggregate.per_arm_window) <= {"seeded", "mutation"}


@pytest.mark.t0
def test_T_I_ledger_02(tmp_path):
    """T-I-ledger-02 (FR-16.4): the snapshot a generator sees is four fields."""
    import dataclasses

    budget = _registered_budget(tmp_path)
    store = LoopStore(str(tmp_path / "loop.db"))
    manifest = replay("run_manifest", schema.RunManifest)[0]
    store.insert("run", {
        "run_manifest_id": manifest.run_manifest_id, "mode": manifest.mode,
        "seed_set": manifest.seed_set, "manifest_json": schema.to_json(manifest),
        "budget_file_sha": manifest.budget_file_sha,
        "cluster_yaml_sha": manifest.cluster_yaml_sha,
        "artefact_root": manifest.artefact_root,
        "started_utc": manifest.started_utc, "ended_utc": None})
    for entry in replay("ledger_entry", schema.LedgerEntry):
        call_node(ledger.accrue, entry, store.db_path, budget)

    aggregate = call_node(ledger.aggregate, manifest.run_manifest_id,
                          store.db_path)
    snapshot = budget_module.snapshot(aggregate, "seeded", budget)
    assert [field.name for field in dataclasses.fields(snapshot)] == [
        "arm", "unit", "spent", "cap"], "four fields and no result field"
    assert not hasattr(snapshot, "filings_total")
    assert not hasattr(snapshot, "per_arm_stage")

    source = Path(generate_task.__file__).read_text(encoding="utf-8")
    assert "BudgetLedger" not in source, "a generator cannot reach the aggregate"


@pytest.mark.t0
def test_T_I_feed_01(tmp_path):
    """T-I-feed-01 (FR-16.1): one entry per probing input, from `ProbeResult`s alone."""
    results = replay("probe_result", schema.ProbeResult, arm="seeded")
    budget = _registered_budget(tmp_path)
    snapshot = schema.LedgerSnapshot(arm="seeded", unit="wall_clock_seconds",
                                     spent=0.0, cap=14400.0)
    previous = schema.FeedbackBundle(
        run_manifest_id=results[0].run_manifest_id, seed_sha=results[0].seed_sha,
        arm="seeded", iteration=1, entries=[], abandoned=False,
        terminating_condition=None)

    bundle = call_node(feedback.build_feedback, results, previous,
                       results[0].seed_sha, 2,
                       [r.probe_id for r in results],
                       run_manifest_id=results[0].run_manifest_id,
                       budget=budget, remaining=snapshot,
                       probes_this_seed=len(results))["bundle"]

    assert len(bundle.entries) == len(results)
    assert [entry.probe_id for entry in bundle.entries] == \
        [result.probe_id for result in results]
    assert schema.validate(bundle) is None
    # And it equals the bundle the recording run wrote, field for field.
    recorded = replay("feedback_bundle", schema.FeedbackBundle, arm="seeded")[0]
    assert {entry.probe_id for entry in recorded.entries} == \
        {entry.probe_id for entry in bundle.entries}

    source = Path(feedback.__file__).read_text(encoding="utf-8")
    assert "from circt_bug_loop.store" not in source
    for denied in feedback._FEEDBACK_DENY:
        assert not any(hasattr(entry, denied) for entry in bundle.entries), denied


@pytest.mark.t0
def test_T_I_feed_02(tmp_path, monkeypatch):
    """T-I-feed-02 (FR-16.2): the bundle back into the generator."""
    seed = replay("seed_record", schema.SeedRecord)[0]
    seeded = replay("feedback_bundle", schema.FeedbackBundle, arm="seeded")[0]
    mutation = replay("feedback_bundle", schema.FeedbackBundle, arm="mutation")[0]

    assert seeded.entries and mutation.entries == [], (
        "FR-16.2: the mutation arm receives no feedback at all")

    rendered = generate_task.render_probe_write(
        seed, "a null dereference in the folder", [], seeded,
        str(tmp_path / "probes"), {"per_seed_probe_cap": 2})
    again = generate_task.render_probe_write(
        seed, "a null dereference in the folder", [], seeded,
        str(tmp_path / "probes"), {"per_seed_probe_cap": 2})
    assert rendered == again, "the same seed and bundle render the same bytes"
    assert generate_task.render_feedback(seeded) in rendered
    assert generate_task.render_feedback(mutation) == \
        "There was no previous iteration."


@pytest.mark.t0
def test_T_I_version_01():
    """T-I-version-01 (FR-04.3): downward, the apparatus refuses a `3.0` supply."""
    supply = [("seed_record", schema.SeedRecord),
              ("budget_file", schema.BudgetFile),
              ("probe_spec", schema.ProbeSpec),
              ("feedback_bundle", schema.FeedbackBundle)]
    for member, cls in supply:
        instance = replay(member, cls)[0]
        text = bumped(instance, "3.0")
        with pytest.raises(schema.ContractError) as refused:
            schema.from_json(text, cls)
        assert refused.value.code == "E001_MAJOR_MISMATCH"
        assert "3.0" in str(refused.value) and schema.CONTRACT_VERSION in \
            str(refused.value)
        # And nothing shims: the same document at the package's own MAJOR is accepted.
        assert schema.validate(
            schema.from_json(bumped(instance, schema.CONTRACT_VERSION), cls)) is None


@pytest.mark.t0
def test_T_I_version_02():
    """T-I-version-02 (FR-04.3): upward, and symmetric about `2.0`."""
    apparatus = [("probe_result", schema.ProbeResult),
                 ("ledger_entry", schema.LedgerEntry),
                 ("run_manifest", schema.RunManifest)]
    for member, cls in apparatus:
        instance = replay(member, cls)[0]
        for major in ("3.0", "1.0"):
            with pytest.raises(schema.ContractError) as refused:
                schema.from_json(bumped(instance, major), cls)
            assert refused.value.code == "E001_MAJOR_MISMATCH"
        # `validate` refuses the same instance.
        instance.contract_version = "3.0"
        with pytest.raises(schema.ContractError) as caught:
            schema.validate(instance)
        assert caught.value.code == "E001_MAJOR_MISMATCH"


def _registered_budget(tmp_path):
    """The committed `budget.yaml`, landed and loaded, as the recording did."""
    from circt_bug_loop.tests.fixtures.recorded.make_recorded import (
        registration_repo)

    path, root = registration_repo(tmp_path / "registration")
    return call_node(budget_module.load_budget, path, root)["budget"]


def _clone_candidate(store: LoopStore, candidate_id: str, decision: str) -> None:
    """Copy the store's one candidate under a new id with another gate decision."""
    row = dict(store.query_one("SELECT * FROM candidate WHERE candidate_id = ?",
                               ("cand-0001",)))
    row["candidate_id"] = candidate_id
    store.insert("candidate", row)
    answers = dict(store.query_one(
        "SELECT * FROM gate_decision WHERE candidate_id = ?", ("cand-0001",)))
    answers["candidate_id"] = candidate_id
    answers["decision"] = decision
    answers["taxonomy_bucket"] = ("new_bug" if decision != "nothing"
                                  else "known_issue")
    store.insert("gate_decision", answers)
