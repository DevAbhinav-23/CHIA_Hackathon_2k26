"""`mutators/` (A4's frozen set): `04-Test-Plan.md` §1.7, `T-U-mut-01` to `-13`.

Every test runs against the committed **development** set,
`circt_bug_loop/mutators/set_dev.json`, and says so: A7 has not been run, there
is no synthesised `set_v1.json` yet, and a set nobody synthesised may not be
passed off as one. What is under test is the format, the loader's digest rule,
the determinism and the round-robin, and none of those depends on which set is
loaded, which is exactly why the format is fixed in `03-LLD.md` §8.1 and not in
the file.

No model, no network, no CIRCT tree and no git: the whole arm runs from
`SeedRecord.test_files` and one JSON document (FR-05.1, FR-05.3).
"""
import ast
import inspect
import json
from pathlib import Path

import pytest

from circt_bug_loop import generate_task, mutators
from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import call_node

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SEEDS = FIXTURES / "corpus" / "seeds"
SETS = FIXTURES / "mutators"

#: 8.1's eight per-mutator fields and their types.
FIELD_TYPES = {"id": str, "language": str, "kind": str, "mutates_argv": bool,
               "description": str, "pattern": str, "replacement": str,
               "derived_from": list}


def seed(name: str = "nine_test_files") -> schema.SeedRecord:
    """One recorded `SeedRecord` of `fixtures/corpus/seeds/`."""
    return schema.from_json((SEEDS / f"{name}.json").read_text(encoding="utf-8"),
                            schema.SeedRecord)


@pytest.fixture
def development_set() -> dict:
    """The committed development set, loaded the way the arm loads it."""
    return mutators.load_set(mutators.DEVELOPMENT_SET)


def fixture_set(name: str) -> dict:
    """One constructed set of `fixtures/mutators/`."""
    return mutators.load_set(SETS / f"{name}.json")


@pytest.mark.t0
def test_T_U_mut_01_the_digest_is_checked_before_a_mutant_is_produced(
        development_set, tmp_path):
    """T-U-mut-01 (FR-05.2): a set that is not the one the run names stops the arm.

    8.1's rule 1, and the point of it: the mutation arm is the baseline the
    head-to-head is measured against, so a set edited after the registration
    must stop the run rather than quietly change what the baseline is.
    """
    real = mutators.set_sha256(mutators.DEVELOPMENT_SET)
    assert mutators.load_set(mutators.DEVELOPMENT_SET)["sha256"] == real

    with pytest.raises(mutators.MutatorSetError) as raised:
        mutators.load_set(mutators.DEVELOPMENT_SET, expected_sha="0" * 64)
    assert real in str(raised.value) and "0" * 64 in str(raised.value)

    # And through the node: nothing is written and no mutant is produced.
    config = {"iteration": 0, "per_seed_probe_cap": 3, "run_manifest_id": "run-1",
              "artefact_dir": str(tmp_path / "iter_0"),
              "mutator_set_path": str(mutators.DEVELOPMENT_SET),
              "mutator_set_sha": "0" * 64}
    with pytest.raises(mutators.MutatorSetError):
        call_node(generate_task.generate_mutation, seed(), _feedback(),
                  _snapshot(), config)
    assert not (tmp_path / "iter_0").exists()

    # A development set cannot run a registered campaign at all, even when its
    # digest is exactly the one the run names.
    with pytest.raises(mutators.MutatorSetError) as refused:
        mutators.load_set(mutators.DEVELOPMENT_SET, expected_sha=real)
    assert "not frozen" in str(refused.value)


@pytest.mark.t0
def test_T_U_mut_02_every_mutator_is_deterministic_in_its_seed(development_set):
    """T-U-mut-02 (FR-05.3): the recorded seed integer reproduces the mutant."""
    text = "hw.module @Top(in %a: i8) {\n  %c = hw.constant 42 : i32\n}\n"
    argv = ["-lower-handshake-to-hw", "%s"]
    for mutator in development_set["mutators"]:
        seed_int = mutators.mutant_seed_int("sha", "test/a.mlir", mutator["id"], 0, 0)
        first = mutators.apply(mutator["id"], text, seed_int,
                               mutator_set=development_set, argv=argv)
        second = mutators.apply(mutator["id"], text, seed_int,
                                mutator_set=development_set, argv=argv)
        assert first == second, mutator["id"]
        # The generator the seed integer feeds is a fresh `random.Random`, so
        # nothing carries between calls and `random.seed()` is never called on
        # the module-level generator (FR-05.3).
        assert not [node for node in ast.walk(ast.parse(
            inspect.getsource(mutators)))
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "random.seed"]


@pytest.mark.t0
def test_T_U_mut_02b_a_spec_replays_from_its_recorded_seed_integer(tmp_path):
    """T-U-mut-02 (FR-05.3): byte for byte, from the `ProbeSpec` and the set alone."""
    record = seed()
    result = _run_mutation(record, tmp_path, cap=6)

    for spec in result["specs"]:
        text, _ = mutators.apply(spec.mutator_id,
                                 record.test_files[spec.source_test_path],
                                 spec.mutator_seed_int,
                                 mutator_set=mutators.load_set(mutators.DEVELOPMENT_SET),
                                 argv=generate_task.seed_argv_template(record))
        assert text == Path(spec.input_path).read_text(encoding="utf-8")


@pytest.mark.t0
def test_T_U_mut_03_a_no_op_is_counted_and_costs_no_input_budget():
    """T-U-mut-03 (FR-05.6): identical output produces no spec and is reported."""
    record = seed()
    produced, no_ops, failures = mutators.mutate_seed(record, 0, 10,
                                                      fixture_set("noop"))

    assert produced == [] and failures == {}
    assert no_ops == len([p for p in record.test_paths
                          if mutators.language_of(p) == "mlir"])
    assert no_ops > 0, "the fixture set matches nothing, so every try is a no-op"


@pytest.mark.t0
def test_T_U_mut_04_a_raising_mutator_is_attributed_and_survived():
    """T-U-mut-04 (FR-05.7): the id carries the failure and the arm continues."""
    record = seed()
    produced, no_ops, failures = mutators.mutate_seed(record, 0, 3,
                                                      fixture_set("raising"))

    # Both raising mutators sort before the working one and are tried against
    # every one of the nine test files; a failure costs no input-cap budget, so
    # the working mutator still fills the cap behind them.
    files = len(record.test_paths)
    assert failures == {"mlir.abort.pattern_uncompilable": files,
                        "mlir.abort.wrong_kind": files}
    assert len(produced) == 3
    assert {mutator_id for mutator_id, *_ in produced} == {"mlir.attr.int.off_by_one"}

    with pytest.raises(mutators.MutatorError) as raised:
        mutators.apply("mlir.abort.pattern_uncompilable", "x", 1,
                       mutator_set=fixture_set("raising"))
    assert raised.value.mutator_id == "mlir.abort.pattern_uncompilable"
    assert "will not compile" in raised.value.cause


@pytest.mark.t0
def test_T_U_mut_05_a_mutator_runs_only_against_its_own_language(development_set):
    """T-U-mut-05 (FR-05.1): the file's extension chooses, and `any` always runs."""
    for language, path in (("mlir", "test/Dialect/HW/a.mlir"),
                           ("fir", "test/firtool/b.fir"),
                           ("sv", "test/circt-verilog/c.sv")):
        assert mutators.language_of(path) == language
        chosen = mutators.eligible(development_set, language)
        assert {mutator["language"] for mutator in chosen} <= {language, "any"}
        assert [mutator["id"] for mutator in chosen] == sorted(
            mutator["id"] for mutator in chosen), "sorted by id, not by position"
        assert any(mutator["language"] == "any" for mutator in chosen)
        assert any(mutator["language"] == language for mutator in chosen)


@pytest.mark.t0
def test_T_U_mut_06_only_an_argv_mutator_may_change_the_argv(development_set,
                                                             tmp_path):
    """T-U-mut-06 (FR-05.5): declared as such, and asserted on every emitted spec."""
    for mutator in development_set["mutators"]:
        assert mutator["mutates_argv"] is (mutator["kind"] == "argv")

    record = seed()
    template = generate_task.seed_argv_template(record)
    for spec in _run_mutation(record, tmp_path, cap=8)["specs"]:
        expected = generate_task.probe_argv(record, spec.input_path)
        if spec.argv != expected:
            declared = [m for m in development_set["mutators"]
                        if m["id"] == spec.mutator_id]
            assert declared and declared[0]["mutates_argv"] is True, spec.mutator_id
            assert len(spec.argv) != len(template) + (0 if "%s" in template else 1)


@pytest.mark.t0
def test_T_U_mut_07_one_mutator_application_per_mutant(tmp_path):
    """T-U-mut-07 (FR-05.3): a mutant is never the composition of two.

    Proved rather than asserted: applying the recorded mutator to the SOURCE
    text reproduces the mutant exactly, so no second mutator can have run.
    """
    record = seed()
    development = mutators.load_set(mutators.DEVELOPMENT_SET)
    produced, _, _ = mutators.mutate_seed(record, 0, 8, development,
                                          generate_task.seed_argv_template(record))

    for mutator_id, path, text, seed_int, argv in produced:
        once, once_argv = mutators.apply(
            mutator_id, record.test_files[path], seed_int,
            mutator_set=development, argv=generate_task.seed_argv_template(record))
        assert (once, once_argv) == (text, argv)
        # A mutant differs from its source in the text or, for an argument
        # mutator, in the argv; a mutant that differs in neither is a no-op and
        # never reaches this list (FR-05.6).
        assert text != record.test_files[path] or argv is not None


@pytest.mark.t0
def test_T_U_mut_08_every_changed_test_file_supplies_a_starting_input():
    """T-U-mut-08 (FR-05.1): nine test files, nine sources, each mutant named.

    The text comes from `seed.test_files`, which contract 2.0 added for exactly
    this: paths are not contents and the arm mutates bytes (K6). The cap is
    taken round-robin across the files, so a seed with nine does not spend its
    whole cap on the first.
    """
    record = seed()
    assert len(record.test_paths) == 9
    development = mutators.load_set(mutators.DEVELOPMENT_SET)
    produced, _, _ = mutators.mutate_seed(record, 0, 9, development)

    assert len(produced) == 9
    sources = [path for _, path, *_ in produced]
    assert set(sources) == set(record.test_paths), "every file supplied one"
    assert sources == record.test_paths, "in the order FR-01.12 records them"


@pytest.mark.t0
def test_T_U_mut_09_the_set_matches_8_1s_format_field_by_field(development_set):
    """T-U-mut-09 (FR-05.2, FR-05.8): the document, the provenance and the types."""
    document = json.loads(mutators.DEVELOPMENT_SET.read_text(encoding="utf-8"))

    assert document["format_version"] == 1
    assert isinstance(document["set_version"], str) and document["set_version"]
    assert document["set_version"] in mutators.DEVELOPMENT_SET.name
    for field in ("synthesised_utc", "synthesis_model"):
        assert isinstance(document[field], str)
    assert set(document["synthesis_input"]) == {
        "repo", "query", "issues_used", "mirror_refreshed_utc",
        "issue_numbers_sha256"}
    # The development set declares itself unfrozen; a synthesised one does not
    # carry the field at all, and 8.1's provenance is filled from the run.
    assert document["frozen"] is False
    assert document["synthesis_input"]["issues_used"] == 0

    identifiers = [mutator["id"] for mutator in document["mutators"]]
    assert len(identifiers) == len(set(identifiers))
    for mutator in document["mutators"]:
        assert set(mutator) == set(FIELD_TYPES)
        for field, kind in FIELD_TYPES.items():
            assert isinstance(mutator[field], kind), (mutator["id"], field)
        assert mutators.ID.match(mutator["id"]), mutator["id"]
        assert mutator["language"] in mutators.LANGUAGES
        assert mutator["kind"] in mutators.KINDS
        assert (mutator["replacement"] in mutators.NAMED_OPERATIONS
                or not mutator["replacement"].startswith("\\"))


@pytest.mark.t0
def test_T_U_mut_10_the_mutation_arm_touches_no_filesystem_and_no_git():
    """T-U-mut-10 (FR-05.1, FR-05.3): the pure half is pure, and the loader is the only read.

    §1.7's row says the walk finds no `open` and no `pathlib` read anywhere in
    the module; §8.1's rule 1 requires this module to hash the set's own bytes
    at load, which is a read. The rule as implemented is therefore: no
    `subprocess` and no `git` anywhere, and no read at all inside `apply`,
    `mutate_seed` or anything they call except `load_set`, which reads the one
    committed set and nothing else (erratum).
    """
    source = Path(mutators.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "subprocess" not in source and "git" not in source

    readers = {"open", "read_text", "read_bytes", "iterdir", "glob"}
    for function in ("apply", "mutate_seed", "eligible", "mutant_seed_int"):
        body = ast.parse(inspect.getsource(getattr(mutators, function)))
        for node in ast.walk(body):
            if isinstance(node, ast.Call):
                assert ast.unparse(node.func).split(".")[-1] not in readers, function

    # THREE reads in the whole module, and this test names which function each
    # is in rather than only how many there are: two that read the committed
    # set's bytes, and W-12c's one directory LISTING, which resolves which
    # `set_v<n>.json` is newest and opens none of them.
    where = {name: sorted(ast.unparse(node.func).split(".")[-1]
                          for node in ast.walk(function)
                          if isinstance(node, ast.Call)
                          and ast.unparse(node.func).split(".")[-1] in readers)
             for function in tree.body if isinstance(function, ast.FunctionDef)
             for name in [function.name]}
    assert {name: calls for name, calls in where.items() if calls} == {
        "frozen_sets": ["glob"], "set_sha256": ["read_bytes"],
        "load_set": ["read_bytes"]}
    loaders = [node for node in ast.walk(tree)
               if isinstance(node, ast.Call)
               and ast.unparse(node.func).split(".")[-1] in readers]
    assert len(loaders) == 3, "load_set, set_sha256, and frozen_sets' listing"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _feedback() -> schema.FeedbackBundle:
    """The empty bundle A4 is handed and never reads (FR-16.2)."""
    return schema.FeedbackBundle(run_manifest_id="run-1", seed_sha=seed().seed_sha,
                                 arm="mutation", iteration=0, entries=[],
                                 abandoned=False)


def _snapshot() -> schema.LedgerSnapshot:
    """The four numbers a generator may know about its own budget (2.5)."""
    return schema.LedgerSnapshot(arm="mutation", unit="wall_clock_seconds",
                                 spent=0.0, cap=14400.0)


def _run_mutation(record: schema.SeedRecord, tmp_path, cap: int) -> dict:
    """One A4 iteration against the development set, through the node."""
    return call_node(generate_task.generate_mutation, record, _feedback(),
                     _snapshot(),
                     {"iteration": 0, "per_seed_probe_cap": cap,
                      "run_manifest_id": "run-1",
                      "artefact_dir": str(tmp_path / "iter_0"),
                      "mutator_set_path": str(mutators.DEVELOPMENT_SET)})


@pytest.mark.t0
def test_T_U_mut_11_the_seed_int_fits_a_signed_sqlite_integer():
    """T-U-mut-11 (W-19b #2, §8.2 rule 5): the derivation is masked to 63 bits.

    New id, W-20b. `int.from_bytes(digest[:8], "big")` is an UNSIGNED 64-bit
    integer and SQLite's INTEGER is SIGNED, so `write_probe` raised
    `OverflowError` out of `SQLiteNode.execute` - OUTSIDE `drive_probe`'s try,
    so it propagated through `drive_seed` and `campaign_drive` and stopped the
    whole campaign. Measured then: 9998 of 20000 derivations exceeded
    `2**63 - 1`, and the expected time to failure in a pilot's mutation arm was
    the second probe.

    Pass criterion: over the same 20000 derivations, none exceeds it; each is
    still deterministic in its five inputs and distinct across them; and a real
    `sqlite3` accepts the largest one this function can now produce.

    Fixture: none. Tier 0.
    """
    import sqlite3

    seen = set()
    for index in range(20000):
        value = mutators.mutant_seed_int("a" * 40, f"test/{index}.mlir",
                                         "mlir.text.int.flip", 1, index)
        assert 0 <= value <= mutators.SEED_INT_MASK, (index, value)
        seen.add(value)
    assert len(seen) == 20000, "the mask did not collapse two derivations into one"
    assert mutators.SEED_INT_MASK == 2 ** 63 - 1

    # Deterministic in all five inputs, and different in each of them.
    first = mutators.mutant_seed_int("a" * 40, "t.mlir", "m.t.i.flip", 1, 0)
    assert first == mutators.mutant_seed_int("a" * 40, "t.mlir", "m.t.i.flip", 1, 0)
    for changed in (("b" * 40, "t.mlir", "m.t.i.flip", 1, 0),
                    ("a" * 40, "u.mlir", "m.t.i.flip", 1, 0),
                    ("a" * 40, "t.mlir", "m.t.i.zero", 1, 0),
                    ("a" * 40, "t.mlir", "m.t.i.flip", 2, 0),
                    ("a" * 40, "t.mlir", "m.t.i.flip", 1, 1)):
        assert mutators.mutant_seed_int(*changed) != first

    # The bound is SQLite's own, asserted against SQLite and not against a
    # comment: the mask's value stores and the next integer up does not.
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE t (v INTEGER)")
    connection.execute("INSERT INTO t VALUES (?)", (mutators.SEED_INT_MASK,))
    with pytest.raises(OverflowError):
        connection.execute("INSERT INTO t VALUES (?)", (mutators.SEED_INT_MASK + 1,))
    connection.close()


@pytest.mark.t0
def test_T_U_mut_12_every_committed_mutation_spec_fits():
    """T-U-mut-12 (W-19b #2): no committed `ProbeSpec` carries an unstorable seed.

    New id, W-20b. Both recorded mutation fixtures were over `2**63 - 1` when
    the defect was found; they were re-recorded by the masked derivation.
    Fixture: `contract/fixtures/**/probe_spec/*.json`. Tier 0.
    """
    import json as _json
    from pathlib import Path as _Path

    from circt_bug_loop.contract import schema as _schema

    root = _Path(_schema.__file__).resolve().parent / "fixtures"
    specs = sorted(root.rglob("probe_spec/*.json"))
    assert specs, "no committed ProbeSpec fixture"
    mutation = 0
    for path in specs:
        value = _json.loads(path.read_text(encoding="utf-8"))["mutator_seed_int"]
        if value is None:
            continue
        mutation += 1
        assert 0 <= value <= mutators.SEED_INT_MASK, (path.name, value)
    assert mutation >= 2, "the mutation arm's fixtures are the ones at risk"


@pytest.mark.t0
def test_T_U_mut_13_the_newest_frozen_set_wins_and_the_dev_set_never_does(tmp_path,
                                                                         monkeypatch):
    """T-U-mut-13 (FR-05.2, §8.1): `SET_PATH` resolves to the NEWEST frozen set.

    New id, W-12c. A7's freeze is write-once, so a second synthesis writes a
    second file rather than editing the first, and the campaign must draw from
    the later one: `set_v1.json` stays committed because it is the record of
    what the first synthesis produced, not because any run should still use it.
    The ordering is by the INTEGER in the name, so `set_v10.json` sorts after
    `set_v9.json`; `set_dev.json` matches no version at all and can therefore
    never win a comparison, which is the property FR-05.2 needs. Fixture: files
    written into a temporary directory. Tier 0.
    """
    monkeypatch.setattr(mutators, "DIRECTORY", tmp_path)
    assert mutators.frozen_sets() == [], "no frozen set before A7 has run"

    for name in ("set_dev.json", "set_v2.json", "set_v10.json", "set_v1.json",
                 "set_v9.json", "set_vx.json", "set_v2.json.bak"):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    assert [path.name for path in mutators.frozen_sets()] == [
        "set_v1.json", "set_v2.json", "set_v9.json", "set_v10.json"]

    # And the committed tree's own resolution, which is what a run reads.
    assert mutators.SET_PATH == mutators.FROZEN_SET
    assert mutators.FROZEN_SET == mutators.FROZEN_SETS[-1]
    assert mutators.SET_PATH != mutators.DEVELOPMENT_SET, \
        "a frozen set exists, so the development set is out of reach"
    assert mutators.load_set()["frozen"] is True
