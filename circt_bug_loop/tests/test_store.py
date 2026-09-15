"""`store.py`: the DDL, the write order, the PARTIAL marker, the cap rule."""
import json
import re
import sqlite3
import sys
import types
from pathlib import Path

import pytest
import yaml

import circt_bug_loop
from circt_bug_loop import store
from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import call_node

pytestmark = pytest.mark.t0

#: `design/03-LLD.md`, reached from the imported package and not by walking up from this file (03-LLD.md §1.4).
_LLD = Path(circt_bug_loop.__file__).resolve().parent.parent / "design" / "03-LLD.md"

#: The synthetic values of `fixtures/secrets/known_values.txt`.
_KNOWN_SECRETS = ("ghp_" + "A" * 36, "AQ." + "B" * 32, "AIza" + "C" * 35)

_DEDUP_EVIDENCE_NULL = {k: None for k in store._DEDUP_EVIDENCE_KEYS}


def open_store(tmp_path: Path) -> store.LoopStore:
    """A LoopStore on a temporary file, with the schema already created."""
    return store.LoopStore(str(tmp_path / "loop.db"))


def lld_sql(heading: str, following: str) -> str:
    """The one fenced SQL block of an `03-LLD.md` section, verbatim."""
    text = _LLD.read_text(encoding="utf-8")
    start = text.index(heading)
    body = text[start:text.index(following, start)]
    blocks = re.findall(r"```sql\n(.*?)```", body, re.S)
    assert len(blocks) == 1, f"{heading} holds {len(blocks)} SQL blocks"
    return blocks[0]


def candidate(**overrides) -> store.CandidateRecord:
    """A valid `assertion` candidate as it stands at the gate, before question 1."""
    fields = dict(
        candidate_id="cand-01", probe_id="probe-01", run_manifest_id="run-01",
        arm="seeded", run_commit="e" * 40, image_digest="sha256:aa",
        oracle_class="assertion", frame_tuple=["f1 A.cpp", "f2 B.cpp"],
        frames_resolved=2, frames_with_location=2, out_of_scope_root=False,
        contaminated_symbol=False, contaminated_file=True,
        contamination_lower_bound="run_commit", triage_class="bug",
        artefact_dir="/artefacts/run-01/probe-01",
        assertion_text="op->getNumResults() == 1", assertion_site="Foo.cpp:42",
        repro_command="circt-opt case.mlir", reducer="circt-reduce", reduced=True,
        fixpoint=True, budget_truncated=False, reduced_path="/artefacts/reduced.mlir",
        size_before_bytes=900, size_after_bytes=90, size_before_ops=30,
        size_after_ops=3, fingerprint="op->getNumResults() == 1 Foo.cpp:42",
        structural_hash="h" * 64, dedup_basis="assertion", dedup_verdict="new",
        dedup_evidence=dict(_DEDUP_EVIDENCE_NULL),
    )
    fields.update(overrides)
    return store.CandidateRecord(**fields)


def differential_candidate(**overrides) -> store.CandidateRecord:
    """A valid `differential` candidate: every conditional group is None (FR-09.8)."""
    fields = dict(
        candidate_id="cand-02", probe_id="probe-02", run_manifest_id="run-01",
        arm="mutation", run_commit="e" * 40, image_digest="sha256:aa",
        oracle_class="differential", frame_tuple=[], frames_resolved=0,
        frames_with_location=0, out_of_scope_root=False, contaminated_symbol=False,
        contaminated_file=False, contamination_lower_bound="seed_commit",
        triage_class="untriaged", artefact_dir="/artefacts/run-01/probe-02",
    )
    fields.update(overrides)
    return store.CandidateRecord(**fields)


def seed_rows(loop: store.LoopStore, *, artefact_dir: str = "/artefacts/run-01/probe-01",
              probe_id: str = "probe-01", candidate_id: str = "cand-01",
              oracle_class: str = "assertion") -> None:
    """Write the run, probe, probe_result and candidate rows one candidate needs."""
    if loop.query_one("SELECT 1 FROM run WHERE run_manifest_id = ?", ("run-01",)) is None:
        loop.insert("run", {
            "run_manifest_id": "run-01", "mode": "discovery", "seed_set": "171",
            "manifest_json": "{}", "budget_file_sha": "b" * 40,
            "cluster_yaml_sha": "c" * 40, "artefact_root": "/artefacts",
            "started_utc": "2026-09-20T00:00:00+00:00", "ended_utc": None})
    loop.insert("probe", {
        "probe_id": probe_id, "run_manifest_id": "run-01", "seed_sha": "a" * 40,
        "arm": "seeded", "iteration": 1, "tool": "circt-opt", "argv_json": "[]",
        "polarity": "expect_zero", "shape": "plain", "input_path": "/in.mlir",
        "mutator_id": None, "mutator_seed_int": None, "source_test_path": None,
        "spec_json": "{}", "artefact_dir": artefact_dir})
    loop.insert("probe_result", {
        "probe_id": probe_id, "run_manifest_id": "run-01", "arm": "seeded",
        "iteration": 1, "build_status": "assertion", "oracle_fired": 1,
        "oracle_class": oracle_class, "stopping_stage": "gate",
        "stopping_reason": "decided", "result_json": "{}",
        "artefact_dir": artefact_dir})
    loop.insert("candidate", {
        "candidate_id": candidate_id, "local_id": None, "probe_id": probe_id,
        "run_manifest_id": "run-01", "arm": "seeded", "run_commit": "e" * 40,
        "image_digest": "sha256:aa", "oracle_class": oracle_class,
        "assertion_text": "op->getNumResults() == 1" if oracle_class == "assertion" else None,
        "assertion_site": "Foo.cpp:42" if oracle_class == "assertion" else None,
        "frame_tuple_json": json.dumps(["f1 A.cpp", "f2 B.cpp"]),
        "out_of_scope_root": 0, "contaminated_symbol": 0, "contaminated_file": 1,
        "contamination_lower_bound": "run_commit", "triage_class": "bug",
        "held_reason": None, "taxonomy_bucket": None, "artefact_dir": artefact_dir,
        "created_utc": "2026-09-20T01:00:00+00:00"})


def test_T_U_store_01(tmp_path: Path):
    """T-U-store-01 (FR-17.2): `init_schema` creates §6.2 and §6.3; twice is once."""
    loop = open_store(tmp_path)
    rows = loop.query("SELECT type, name FROM sqlite_master "
                      "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")
    tables = [r["name"] for r in rows if r["type"] == "table"]
    indexes = [r["name"] for r in rows if r["type"] == "index"]
    # §6.2's twenty-one, plus the three §6.2 does NOT declare.
    assert len(tables) == 24 and "candidate" in tables and "registration" in tables
    assert len(indexes) == 9 and "ix_ledger_day" in indexes
    for late in ("registration", "turn_failure", "verifier_error"):
        assert late in tables and late not in store._DDL_TABLES

    conn = sqlite3.connect(str(tmp_path / "loop.db"))
    try:
        store.init_schema(conn)                      # the second call is a no-op
    finally:
        conn.close()
    again = loop.query("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")
    assert sorted(r["name"] for r in again) == sorted(tables + indexes)

    if not _LLD.exists():
        pytest.skip("design/03-LLD.md is not in the published tree")
    assert store._DDL_TABLES == lld_sql("### 6.2 ", "### 6.3 ")
    assert store._DDL_INDEXES == lld_sql("### 6.3 ", "### 6.4 ")


def test_T_U_store_02(tmp_path: Path, monkeypatch):
    """T-U-store-02 (FR-17.3): `pin_to_current_node=True`, absolute, local."""
    with pytest.raises(ValueError, match="absolute"):
        store.LoopStore("relative/loop.db")

    mounts = tmp_path / "mountinfo"
    mounts.write_text(
        "24 0 0:22 / / rw - ext4 /dev/sda1 rw\n"
        f"31 24 0:33 / {tmp_path}/nfs rw - nfs4 head:/export rw\n", encoding="utf-8")
    monkeypatch.setattr(store, "_MOUNTINFO", str(mounts))
    with pytest.raises(ValueError, match="network storage"):
        store.LoopStore(str(tmp_path / "nfs" / "loop.db"))

    seen = {}

    class _Member:
        def chia_remote(self, *args):
            seen["script"] = args[0]
            return "ref"

    class _SQLiteNode:
        def __init__(self, db_path, **kwargs):
            seen["db_path"], seen["kwargs"] = db_path, kwargs
            self.init_schema = _Member()

    monkeypatch.setitem(sys.modules, "chia.database.sqlite_node",
                        types.SimpleNamespace(SQLiteNode=_SQLiteNode))
    monkeypatch.setitem(sys.modules, "chia.base.ChiaFunction",
                        types.SimpleNamespace(get=lambda ref: ref))
    monkeypatch.setattr(store, "_ray_initialised", lambda: True)
    loop = store.LoopStore(str(tmp_path / "loop.db"))
    assert seen["kwargs"] == {"pin_to_current_node": True}
    assert seen["db_path"] == str(tmp_path / "loop.db")
    assert seen["script"] == store._SCHEMA
    assert loop.node is not None


def test_T_U_store_03(tmp_path: Path):
    """T-U-store-03 (FR-17.7): over the cap goes to disk and the row holds a path."""
    committed = Path(circt_bug_loop.__file__).resolve().parent / "budget.yaml"
    cap = yaml.safe_load(committed.read_text(encoding="utf-8"))["artefact_inline_cap_bytes"]
    assert cap == 262144

    artefact_dir = str(tmp_path / "probe-01")
    big = "x" * (cap + 1)
    written = call_node(store.artefact_write, artefact_dir, "input.mlir", big)
    path = written["path"]
    assert written["counters"].stage == "artefact"
    assert Path(path).stat().st_size == cap + 1
    assert schema.bound_text(big, path, cap) is None       # the row holds the path
    assert schema.bound_text("x" * cap, path, cap) is not None
    with pytest.raises(schema.ContractError) as caught:
        schema.bound_text(big, None, cap)
    assert caught.value.code == "E008_CAP_EXCEEDED"


def test_T_U_store_04(tmp_path: Path):
    """T-U-store-04 (FR-17.8): the marker is first in and last out, and survives a kill."""
    artefact_dir = tmp_path / "probe-01"
    marker = artefact_dir / store.PARTIAL
    call_node(store.artefact_write, str(artefact_dir), store.PARTIAL, b"")
    assert marker.is_file() and marker.stat().st_size == 0

    call_node(store.artefact_write, str(artefact_dir), "stdout.txt", "boom\n")
    assert marker.is_file(), "a killed stage leaves the marker and its output"
    assert (artefact_dir / "stdout.txt").read_text() == "boom\n"

    other = tmp_path / "probe-02"
    call_node(store.artefact_write, str(other), "stderr.txt", b"")
    assert (other / store.PARTIAL).is_file(), "written before anything else"

    loop = open_store(tmp_path)
    seed_rows(loop, artefact_dir=str(artefact_dir))
    call_node(store.artefact_write, str(artefact_dir), store.PARTIAL, None, store=loop)
    assert not marker.exists()
    assert (artefact_dir / "stdout.txt").is_file(), "nothing else is deleted"


def test_T_U_store_05(tmp_path: Path):
    """T-U-store-05 (FR-17.8): no completion record, no marker removal."""
    loop = open_store(tmp_path)
    artefact_dir = tmp_path / "probe-01"
    call_node(store.artefact_write, str(artefact_dir), store.PARTIAL, b"")

    with pytest.raises(ValueError, match="no completion record"):
        call_node(store.artefact_write, str(artefact_dir), store.PARTIAL, None, store=loop)
    with pytest.raises(ValueError, match="no completion record"):
        call_node(store.artefact_write, str(artefact_dir), store.PARTIAL, None)
    assert (artefact_dir / store.PARTIAL).is_file()

    seed_rows(loop, artefact_dir=str(artefact_dir))
    call_node(store.artefact_write, str(artefact_dir), store.PARTIAL, None, store=loop)
    assert not (artefact_dir / store.PARTIAL).exists()


def test_T_U_store_06(tmp_path: Path):
    """T-U-store-06 (FR-17.6): every table traces to its run, by column or by key."""
    loop = open_store(tmp_path)
    tables = [r["name"] for r in loop.query(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    traced, campaign_wide = [], []
    for table in tables:
        columns = {r["name"] for r in loop.query(f"PRAGMA table_info({table})")}
        if columns & {"run_manifest_id", "probe_id", "candidate_id"}:
            traced.append(table)
        else:
            campaign_wide.append(table)
    assert campaign_wide == ["image", "issue_mirror"]
    # 19 of §6.2, plus W-12's `registration`, D-3's `turn_failure` and D-13's
    # `verifier_error`.
    assert len(traced) == 22

    seed_rows(loop)
    row = loop.query_one("SELECT artefact_dir, run_manifest_id FROM candidate")
    assert row["run_manifest_id"] == "run-01"
    assert row["artefact_dir"].startswith("/artefacts/run-01/")


def test_a_turn_that_produced_nothing_is_written_and_kept(tmp_path: Path):
    """D-3 (pilot 5): the failure log is appended to, and one seed can fill it twice."""
    loop = open_store(tmp_path)
    seed_rows(loop)

    for iteration, kind, detail in (
            (1, "prompt_contract:no_block", "PromptContractError: no_block"),
            (2, "turn_failed:TurnBudgetExceeded", "refusing call 13 of this turn"),
            (2, "stale_at_build", None)):
        store.write_turn_failure(loop, "run-01", "a" * 40, "seeded", iteration,
                                 "stage_2", kind, detail)

    rows = loop.query("SELECT * FROM turn_failure ORDER BY iteration, kind")
    assert [r["kind"] for r in rows] == [
        "prompt_contract:no_block", "stale_at_build",
        "turn_failed:TurnBudgetExceeded"]
    assert rows[1]["detail"] is None, "a failure with no detail is still a row"
    assert {r["run_manifest_id"] for r in rows} == {"run-01"}
    assert rows[0]["seed_sha"] == "a" * 40 and rows[0]["arm"] == "seeded"
    assert rows[0]["stage"] == "stage_2" and rows[0]["iteration"] == 1


def test_T_U_store_07(tmp_path: Path):
    """T-U-store-07 (FR-17.2): one row per probe and per candidate, joined, on disk."""
    loop = open_store(tmp_path)
    artefact_dir = tmp_path / "probe-01"
    call_node(store.artefact_write, str(artefact_dir), "stdout.txt", "")
    seed_rows(loop, artefact_dir=str(artefact_dir))

    joined = loop.query(
        "SELECT c.candidate_id, p.probe_id, r.build_status "
        "FROM candidate c JOIN probe p ON p.probe_id = c.probe_id "
        "JOIN probe_result r ON r.probe_id = p.probe_id")
    assert len(joined) == 1 and joined[0]["build_status"] == "assertion"
    for table in ("probe", "probe_result", "candidate"):
        for row in loop.query(f"SELECT artefact_dir FROM {table}"):
            assert Path(row["artefact_dir"]).is_dir()

    with pytest.raises(sqlite3.IntegrityError):
        loop.insert("candidate", {
            "candidate_id": "cand-02", "probe_id": "probe-01",
            "run_manifest_id": "run-01", "arm": "seeded", "run_commit": "e" * 40,
            "image_digest": "sha256:aa", "oracle_class": "crash",
            "frame_tuple_json": "[]", "out_of_scope_root": 0,
            "contaminated_symbol": 0, "contaminated_file": 0,
            "contamination_lower_bound": "run_commit", "triage_class": "bug",
            "artefact_dir": str(artefact_dir), "created_utc": "2026-09-20T02:00:00+00:00"})


def test_T_U_store_08(tmp_path: Path):
    """T-U-store-08 (FR-12.10): the loop's row before CHIA's, the candidate before its verdicts."""
    loop = open_store(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        loop.insert("fingerprint", {
            "candidate_id": "cand-01", "basis": "assertion", "value": "v",
            "fingerprint_stable": None, "frame_tuple_json": "[]",
            "structural_hash": "h" * 64})

    seed_rows(loop)
    local_id = 900_000_001
    loop.update("candidate", {"candidate_id": "cand-01"}, {"local_id": local_id})
    loop.insert("repair", {
        "candidate_id": "cand-01", "local_id": local_id, "status": "attempted",
        "failing_phase": None, "reproduced": 1, "build_ok": 1, "fixed": 0,
        "lit_ok": None, "lit_unusable": 0, "lit_passed": None, "lit_failed": None,
        "lit_failures_json": "[]", "diff_path": None, "diff_added": None,
        "diff_removed": None, "chia_artifact_dir": None, "chia_row_seen": 0,
        "repro_dir": "/artefacts/run-01/repair/900000001", "repro_overwritten": 0,
        "restore_ok": 1, "restore_hashes_match": 1, "restore_log": "",
        "backend": "vertex", "token_capture": "unavailable_remote_dispatch"})
    assert loop.query_one("SELECT chia_row_seen FROM repair")["chia_row_seen"] == 0

    issues = sqlite3.connect(str(tmp_path / "issues.db"))          # CHIA's own file
    try:
        issues.execute("CREATE TABLE attempts (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                       "issue_number INTEGER NOT NULL, status TEXT)")
        issues.execute("INSERT INTO attempts (issue_number, status) VALUES (?, ?)",
                       (local_id, "attempted"))
        issues.commit()
        seen = issues.execute("SELECT 1 FROM attempts WHERE issue_number = ?",
                              (local_id,)).fetchone() is not None
    finally:
        issues.close()
    loop.update("repair", {"candidate_id": "cand-01"}, {"chia_row_seen": int(seen)})
    assert loop.query_one("SELECT chia_row_seen FROM repair")["chia_row_seen"] == 1

    loop.transaction([
        ("INSERT INTO gate_decision (candidate_id, answers_json, stopped_at_question, "
         "decision, taxonomy_bucket, decided_utc) VALUES (?, ?, ?, ?, ?, ?)",
         ("cand-01", "{}", None, "report", "new_bug", "2026-09-20T03:00:00+00:00")),
        ("UPDATE candidate SET taxonomy_bucket = ? WHERE candidate_id = ?",
         ("new_bug", "cand-01"))])
    assert loop.query_one("SELECT taxonomy_bucket FROM candidate")["taxonomy_bucket"] == "new_bug"

    with pytest.raises(sqlite3.IntegrityError):
        loop.transaction([
            ("UPDATE candidate SET triage_class = ? WHERE candidate_id = ?",
             ("invalid_input", "cand-01")),
            ("INSERT INTO report (candidate_id, path, template, title, classification, "
             "classification_reason, rendered_sha256, assisted_by, fields_present_json) "
             "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
             ("absent", "/r.md", "primary", "t", "bug", "r", "s", "a", "[]"))])
    assert loop.query_one("SELECT triage_class FROM candidate")["triage_class"] == "bug"


def test_T_U_store_09():
    """T-U-store-09 (FR-08.10): §2.9's class table, row by row."""
    assert validate_is_none(candidate())
    assert validate_is_none(differential_candidate())

    for group in (store._REDUCTION_FIELDS, store._DEDUP_FIELDS, store._GATE_FIELDS):
        for name in group:
            populated = differential_candidate(**{name: _a_value_for(name)})
            with pytest.raises(schema.ContractError) as caught:
                store.validate_candidate(populated)
            assert caught.value.code == "E006_CONDITIONAL_FORBIDDEN"
            assert name in str(caught.value)

    for name in store._REDUCTION_FIELDS + store._DEDUP_REQUIRED:
        with pytest.raises(schema.ContractError) as caught:
            store.validate_candidate(candidate(**{name: None}))
        assert caught.value.code == "E005_CONDITIONAL_REQUIRED"
        assert name in str(caught.value)

    # the gate group is accepted on both sides of gate_decide
    assert validate_is_none(candidate(gate_answers={"q1": True},
                                      gate_decision="report",
                                      taxonomy_bucket="new_bug"))
    # and fingerprint_stable is null until the gate's re-run has run (K3)
    assert validate_is_none(candidate(fingerprint_stable=True))

    for name in ("assertion_text", "assertion_site"):
        with pytest.raises(schema.ContractError) as caught:
            store.validate_candidate(candidate(**{name: None}))
        assert caught.value.code == "E005_CONDITIONAL_REQUIRED"
    assert validate_is_none(candidate(
        oracle_class="crash", dedup_basis="frames", assertion_text=None,
        assertion_site=None, fingerprint="SIGSEGV lowerToHW Foo.cpp"))
    with pytest.raises(schema.ContractError) as caught:
        store.validate_candidate(candidate(oracle_class="crash", dedup_basis="frames"))
    assert caught.value.code == "E006_CONDITIONAL_FORBIDDEN"

    for name in store._ALWAYS_REQUIRED:
        for shape in (candidate, differential_candidate):
            with pytest.raises(schema.ContractError) as caught:
                store.validate_candidate(shape(**{name: None}))
            assert caught.value.code == "E005_CONDITIONAL_REQUIRED"
    assert differential_candidate().frame_tuple == [], "a value, not a None"

    once = candidate()
    for _ in range(4):
        assert store.validate_candidate(once) is None
    assert once == candidate(), "validate_candidate mutates nothing"


#: One admissible value per conditional field.
_ADMISSIBLE = {
    "reducer": "circt-reduce", "reduced": True, "fixpoint": True,
    "budget_truncated": False, "reduced_path": "/artefacts/reduced.mlir",
    "size_before_bytes": 900, "size_after_bytes": 90, "size_before_ops": 30,
    "size_after_ops": 3, "fingerprint": "v", "fingerprint_stable": True,
    "structural_hash": "h" * 64, "dedup_basis": "frames", "dedup_verdict": "new",
    "dedup_evidence": dict(_DEDUP_EVIDENCE_NULL), "gate_answers": {},
    "gate_decision": "report", "taxonomy_bucket": "new_bug",
}


def _a_value_for(name: str):
    """One admissible value for *name*, from the table above."""
    return _ADMISSIBLE[name]


def validate_is_none(record: store.CandidateRecord) -> bool:
    """Run `validate_candidate` and report that it returned None."""
    return store.validate_candidate(record) is None


def test_T_U_store_10(tmp_path: Path):
    """T-U-store-10 (FR-17.5): no credential in any row or any file."""
    loop = open_store(tmp_path)
    artefact_dir = tmp_path / "probe-01"
    call_node(store.artefact_write, str(artefact_dir), "stdout.txt", "assertion failed\n")
    call_node(store.artefact_write, str(artefact_dir), "repro.sh", "#!/bin/sh\ncirct-opt case.mlir\n")
    seed_rows(loop, artefact_dir=str(artefact_dir))

    haystack = [json.dumps(row) for table in
                ("run", "seed", "probe", "probe_result", "candidate", "ledger_entry")
                for row in loop.query(f"SELECT * FROM {table}")]
    haystack += [p.read_text(encoding="utf-8", errors="backslashreplace")
                 for p in tmp_path.rglob("*")
                 if p.is_file() and not p.name.startswith("loop.db")]
    haystack.append(Path(store.__file__).read_text(encoding="utf-8"))
    for secret in _KNOWN_SECRETS:
        assert not any(secret in text for text in haystack), "a credential reached the tree"
    assert not re.search(r"AQ\.[A-Za-z0-9_-]{30,}|AIza[0-9A-Za-z_-]{30,}",
                         "\n".join(haystack))


def test_T_U_store_11(tmp_path: Path):
    """T-U-store-11 (FR-10.5): `load_candidate` joins the six tables back."""
    loop = open_store(tmp_path)
    for i, oracle_class in enumerate(("assertion", "fatal_error", "crash", "differential")):
        probe_id, candidate_id = f"probe-{i}", f"cand-{i}"
        seed_rows(loop, probe_id=probe_id, candidate_id=candidate_id,
                  oracle_class=oracle_class, artefact_dir=f"/artefacts/run-01/{probe_id}")
        loop.insert("oracle_verdict", {
            "probe_id": probe_id, "fired": 1, "oracle_class": oracle_class,
            "assertion_text": "op->getNumResults() == 1" if oracle_class == "assertion" else None,
            "assertion_site": "Foo.cpp:42" if oracle_class == "assertion" else None,
            "fatal_message": None, "frames_json": "[]", "prologue_dropped": 3,
            "frames_resolved": 2, "frames_with_location": 2,
            "fingerprint_frame": "lowerToHW Foo.cpp", "out_of_scope_root": 0,
            "repro_command": "circt-opt case.mlir", "flag_string": "-O3 -UNDEBUG",
            "tool_version_output": "Optimized build."})
        if oracle_class == "differential":
            continue
        loop.insert("reduced_case", {
            "probe_id": probe_id, "reducer": "circt-reduce", "reduced": 1,
            "fixpoint": 1, "budget_truncated": 0, "reason": None, "lift": None,
            "path": "/artefacts/reduced.mlir", "size_before_bytes": 900,
            "size_after_bytes": 90, "size_before_ops": 30, "size_after_ops": 3,
            "wall_seconds": 12.5, "interestingness_calls": 56, "recheck_class": oracle_class,
            "recheck_assertion_text": None, "recheck_assertion_site": None,
            "recheck_matches": 1})
        loop.insert("fingerprint", {
            "candidate_id": candidate_id,
            "basis": "assertion" if oracle_class == "assertion" else "frames",
            "value": "op->getNumResults() == 1 Foo.cpp:42" if oracle_class == "assertion"
                     else "SIGSEGV lowerToHW Foo.cpp",
            "fingerprint_stable": None, "frame_tuple_json": json.dumps(["f1 A.cpp"]),
            "structural_hash": "h" * 64})
        loop.insert("dedup_verdict", {
            "candidate_id": candidate_id, "verdict": "new",
            "evidence_json": json.dumps(_DEDUP_EVIDENCE_NULL)})

        record = store.load_candidate(loop, candidate_id)
        assert record.oracle_class == oracle_class
        assert record.frames_resolved == 2 and record.repro_command == "circt-opt case.mlir"
        assert record.reduced_path == "/artefacts/reduced.mlir"
        assert record.dedup_verdict == "new" and record.dedup_basis in ("assertion", "frames")
        assert record.frame_tuple == ["f1 A.cpp", "f2 B.cpp"]
        assert store.validate_candidate(record) is None

    record = store.load_candidate(loop, "cand-3")
    assert record.oracle_class == "differential"
    assert all(getattr(record, name) is None for name in
               store._REDUCTION_FIELDS + store._DEDUP_FIELDS + store._GATE_FIELDS)
    assert store.validate_candidate(record) is None
    with pytest.raises(LookupError):
        store.load_candidate(loop, "absent")


def test_T_U_store_12():
    """T-U-store-12 (FR-10.5): the three codes `store.py` adds, and no other."""
    extra = dict(_DEDUP_EVIDENCE_NULL)
    extra["cost"] = None
    with pytest.raises(schema.ContractError) as caught:
        store.validate_candidate(candidate(dedup_evidence=extra))
    assert caught.value.code == "E011_BAD_EVIDENCE_KEYS" and "cost" in str(caught.value)

    short = dict(_DEDUP_EVIDENCE_NULL)
    short.pop("issue_url")
    with pytest.raises(schema.ContractError) as caught:
        store.validate_candidate(candidate(dedup_evidence=short))
    assert caught.value.code == "E011_BAD_EVIDENCE_KEYS" and "issue_url" in str(caught.value)

    with pytest.raises(schema.ContractError) as caught:
        store.validate_candidate(candidate(dedup_basis="insufficient"))
    assert caught.value.code == "E012_FINGERPRINT_BASIS"
    with pytest.raises(schema.ContractError) as caught:
        store.validate_candidate(candidate(fingerprint=None))
    assert caught.value.code == "E012_FINGERPRINT_BASIS"
    assert validate_is_none(candidate(fingerprint=None, dedup_basis="insufficient"))

    for verdict, required in store._DEDUP_EVIDENCE_REQUIRED.items():
        evidence = dict(_DEDUP_EVIDENCE_NULL)
        for key in required:
            evidence[key] = "recorded"
        assert validate_is_none(candidate(dedup_verdict=verdict, dedup_evidence=evidence))
        if not required:
            continue
        evidence[required[0]] = None
        with pytest.raises(schema.ContractError) as caught:
            store.validate_candidate(candidate(dedup_verdict=verdict, dedup_evidence=evidence))
        assert caught.value.code == "E013_MISSING_EVIDENCE"
        assert verdict in str(caught.value) and required[0] in str(caught.value)

    with pytest.raises(schema.ContractError) as caught:
        store.validate_candidate(candidate(arm="third"))
    assert caught.value.code == "E004_BAD_ENUM"
    with pytest.raises(schema.ContractError) as caught:
        store.validate_candidate(candidate(frames_resolved="two"))
    assert caught.value.code == "E003_WRONG_TYPE"

    raised = set()
    for broken in (candidate(dedup_evidence=extra), candidate(fingerprint=None),
                   candidate(arm="third"), differential_candidate(reduced=True)):
        try:
            store.validate_candidate(broken)
        except schema.ContractError as error:
            raised.add(error.code)
    assert raised.isdisjoint({"E001_MAJOR_MISMATCH", "E007_BAD_DICT_KEYS",
                              "E008_CAP_EXCEEDED", "E009_UNKNOWN_SCHEMA",
                              "E010_TOOL_MISMATCH"})


def test_T_U_store_13(tmp_path: Path):
    """T-U-store-13 (FR-10.8): the DDL enforces the fingerprint rule too."""
    loop = open_store(tmp_path)
    seed_rows(loop)
    row = {"candidate_id": "cand-01", "fingerprint_stable": None,
           "frame_tuple_json": "[]", "structural_hash": "h" * 64}
    with pytest.raises(sqlite3.IntegrityError):
        loop.insert("fingerprint", {**row, "basis": "insufficient", "value": "set"})
    with pytest.raises(sqlite3.IntegrityError):
        loop.insert("fingerprint", {**row, "basis": "frames", "value": None})
    loop.insert("fingerprint", {**row, "basis": "frames", "value": "SIGSEGV f Foo.cpp"})
    assert loop.query_one("SELECT value FROM fingerprint")["value"] == "SIGSEGV f Foo.cpp"


def test_T_U_store_14(tmp_path: Path):
    """T-U-store-14 (D-11): `make_appendable` frees the two rescreened tables of `candidate_id`'s PRIMARY KEY, once and without losing a row, and `latest` reads the newest row of each."""
    loop = open_store(tmp_path)
    seed_rows(loop)
    first = {"candidate_id": "cand-01", "verdict": "fixed_post_pin",
             "evidence_json": json.dumps({**_DEDUP_EVIDENCE_NULL,
                                          "fixing_commit": "d" * 40})}
    loop.insert("dedup_verdict", first)
    with pytest.raises(sqlite3.IntegrityError):
        loop.insert("dedup_verdict", {**first, "verdict": "new"})

    assert store.make_appendable(loop) == ["dedup_verdict", "gate_decision"]
    assert store.make_appendable(loop) == [], "the second call is a no-op"
    assert store.latest(loop, "dedup_verdict", "cand-01")["verdict"] == "fixed_post_pin"

    loop.insert("dedup_verdict", {**first, "verdict": "new",
                                  "evidence_json": json.dumps(_DEDUP_EVIDENCE_NULL)})
    rows = loop.query("SELECT verdict FROM dedup_verdict ORDER BY rowid")
    assert [row["verdict"] for row in rows] == ["fixed_post_pin", "new"]
    assert store.latest(loop, "dedup_verdict", "cand-01")["verdict"] == "new"
    assert store.latest(loop, "dedup_verdict", "cand-99") is None

    loop.insert("fingerprint", {
        "candidate_id": "cand-01", "basis": "assertion", "value": "v",
        "fingerprint_stable": None, "frame_tuple_json": "[]",
        "structural_hash": "h" * 64})
    assert store.load_candidate(loop, "cand-01").dedup_verdict == "new"
