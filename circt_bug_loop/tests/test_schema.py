"""`contract/schema.py`: every validator error code, both serialisers.

`04-Test-Plan.md` §1.1, the 27 `T-U-schema-*` tests: its 23 plus the four that
`BudgetFile`'s 2026-09-14 keys brought (§16.7). Every one is tier 0: the
seam imports nothing outside the standard library, so nothing here forks a
compiler, opens a socket or needs a clone.

Malformed inputs are derived from a committed fixture by one edit each, which is
the derivation `04-Test-Plan.md` §13 specifies for `contract/fixtures/malformed/`;
the edit is made here rather than committed as a second document, because
`T-U-fixt-01` validates every file under `contract/fixtures/`.
"""
import dataclasses
import json
import random
from pathlib import Path

import pytest

import circt_bug_loop
from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import FIXTURES

pytestmark = pytest.mark.t0

#: the flow directory, from the package's own `__init__.py` and not by walking
#: up from this file: 03-LLD.md 1.4 forbids any longer walk.
_FLOW_DIR = Path(circt_bug_loop.__file__).resolve().parent


def load(relative_path: str, cls: type):
    """Read one committed fixture back into its dataclass."""
    return schema.from_json((FIXTURES / relative_path).read_text(encoding="utf-8"), cls)


def payload(relative_path: str) -> dict:
    """Read one committed fixture as the plain JSON document it is."""
    return json.loads((FIXTURES / relative_path).read_text(encoding="utf-8"))


def seed():
    return load("seed_record/exact_pin_01.json", schema.SeedRecord)


def budget():
    return load("budget_file/complete_01.json", schema.BudgetFile)


def seeded_spec():
    return load("probe_spec/seeded_01.json", schema.ProbeSpec)


def mutation_spec():
    return load("probe_spec/mutation_01.json", schema.ProbeSpec)


def result():
    return load("probe_result/assertion_01.json", schema.ProbeResult)


def bundle():
    return load("feedback_bundle/iteration_01.json", schema.FeedbackBundle)


def entry():
    return load("ledger_entry/arm_window_01.json", schema.LedgerEntry)


def manifest():
    return load("run_manifest/discovery_01.json", schema.RunManifest)


def every_member() -> list:
    """One valid instance of each of the seven members, in `_MEMBERS` order."""
    return [seed(), budget(), seeded_spec(), result(), bundle(), entry(), manifest()]


def raises(code: str, fn, *args, **kwargs) -> schema.ContractError:
    """Assert *fn* raises `ContractError` carrying *code*, and return it."""
    with pytest.raises(schema.ContractError) as caught:
        fn(*args, **kwargs)
    assert caught.value.code == code, caught.value
    return caught.value


def edit(obj, **one_edit):
    """One field changed on a copy of a valid instance."""
    return dataclasses.replace(obj, **one_edit)


def test_T_U_schema_01():
    """T-U-schema-01 (FR-04.3): E001_MAJOR_MISMATCH in both directions.

    A `1.0` instance and a `3.0` instance each raise against `CONTRACT_VERSION`
    `2.0`, and the message names both versions verbatim.
    """
    older = payload("seed_record/exact_pin_01.json") | {"contract_version": "1.0"}
    newer = payload("seed_record/exact_pin_01.json") | {"contract_version": "3.0"}
    for document, version in ((older, "1.0"), (newer, "3.0")):
        error = raises("E001_MAJOR_MISMATCH", schema.from_json,
                       json.dumps(document), schema.SeedRecord)
        assert repr(version) in str(error)
        assert repr(schema.CONTRACT_VERSION) in str(error)
    raises("E001_MAJOR_MISMATCH", schema.validate, edit(seed(), contract_version="1.0"))
    raises("E001_MAJOR_MISMATCH", schema.validate, edit(seed(), contract_version="3.0"))


def test_T_U_schema_02():
    """T-U-schema-02 (FR-04.3): E002_MISSING_FIELD on a required field set to None.

    The message names `<Class>.<field>`.
    """
    assert "ProbeSpec.tool is None" in str(
        raises("E002_MISSING_FIELD", schema.validate, edit(seeded_spec(), tool=None)))
    assert "SeedRecord.llvm_pin is None" in str(
        raises("E002_MISSING_FIELD", schema.validate, edit(seed(), llvm_pin=None)))
    assert "LedgerEntry.observed is None" in str(
        raises("E002_MISSING_FIELD", schema.validate, edit(entry(), observed=None)))


def test_T_U_schema_03():
    """T-U-schema-03 (FR-04.3): E002_MISSING_FIELD from `from_json`, names sorted.

    A payload lacking declared fields raises before the class is constructed and
    lists every missing name in sorted order.
    """
    document = payload("probe_result/assertion_01.json")
    del document["stopping_reason"]
    del document["artefact_dir"]
    error = raises("E002_MISSING_FIELD", schema.from_json,
                   json.dumps(document), schema.ProbeResult)
    assert "['artefact_dir', 'stopping_reason']" in str(error)


def test_T_U_schema_04():
    """T-U-schema-04 (FR-14.4): E003_WRONG_TYPE after Optional is unwrapped.

    And `LedgerEntry.amount` negative, which is the one numeric rule the
    conditionals carry rather than the type check.
    """
    error = raises("E003_WRONG_TYPE", schema.validate, edit(result(), exit_status="1"))
    assert "ProbeResult.exit_status is str, expected int" in str(error)
    raises("E003_WRONG_TYPE", schema.validate, edit(seed(), source_paths="lib/a.cpp"))
    raises("E003_WRONG_TYPE", schema.validate, edit(entry(), amount=-1.0))


def test_T_U_schema_05():
    """T-U-schema-05 (FR-06.9, FR-14.4): E004_BAD_ENUM for every Literal alias.

    `build_status` outside FR-06.9's seven, `arm` outside three, `scope` outside
    two, and `mode`, `seed_set`, `deployment`, `unit`, `polarity`, `shape` and
    `limit_hit` outside theirs.
    """
    cases = [
        (result(), {"build_status": "exploded"}),
        (entry(), {"arm": "both"}),
        (entry(), {"scope": "campaign"}),
        (entry(), {"unit": "cpu_seconds"}),
        (manifest(), {"mode": "pilot"}),
        (manifest(), {"seed_set": "200"}),
        (manifest(), {"deployment": "aws"}),
        (seeded_spec(), {"polarity": "expect_two"}),
        (seeded_spec(), {"shape": "exotic"}),
        (result(), {"limit_hit": "disk"}),
        (seed(), {"entry_tool": "circt-lsp-server"}),
        (result(), {"stopping_stage": "stage_9"}),
    ]
    for obj, one_edit in cases:
        raises("E004_BAD_ENUM", schema.validate, edit(obj, **one_edit))
    # every member of each Literal is accepted, `tool_unavailable` being
    # contract 2.1's own (W-20b, N9).
    for status in ("clean_exit", "parse_error", "assertion", "fatal_error",
                   "crash", "timeout", "oom", "tool_unavailable"):
        candidate = edit(result(), build_status=status, signal=None, limit_hit=None)
        schema.validate(candidate)
    for arm in ("seeded", "mutation", "shared"):
        schema.validate(edit(entry(), arm=arm))
    for scope in ("arm_window", "stage"):
        schema.validate(edit(entry(), scope=scope))
    for deployment in ("single_machine", "gcp"):
        schema.validate(edit(manifest(), deployment=deployment))
    for seed_set in ("187", "171"):
        schema.validate(edit(manifest(), seed_set=seed_set))
    for polarity in ("expect_zero", "expect_nonzero"):
        schema.validate(edit(seeded_spec(), polarity=polarity))
    for shape in ("plain", "split_file", "unsupported"):
        schema.validate(edit(seeded_spec(), shape=shape))
    for limit in ("wall", "cpu", "address_space"):
        schema.validate(edit(result(), limit_hit=limit))
    for stage in ("stage_3", "stage_4", "stage_5", "stage_6", "stage_7", "gate"):
        schema.validate(edit(result(), stopping_stage=stage))


def test_T_U_schema_06():
    """T-U-schema-06 (FR-05.3, FR-14.6): E005_CONDITIONAL_REQUIRED on a ProbeSpec.

    `mutator_id`, `mutator_seed_int` and `source_test_path` null on
    `arm == "mutation"`, and `turn_cost.metered` disagreeing with `tokens_in`.
    """
    for name in ("mutator_id", "mutator_seed_int", "source_test_path"):
        error = raises("E005_CONDITIONAL_REQUIRED", schema.validate,
                       edit(mutation_spec(), **{name: None}))
        assert f"ProbeSpec.{name} is required when arm is 'mutation'" in str(error)
    spec = seeded_spec()
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(spec, turn_cost=spec.turn_cost | {"metered": False}))
    unmetered = mutation_spec()
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(unmetered, turn_cost=unmetered.turn_cost | {"metered": True}))


def test_T_U_schema_07():
    """T-U-schema-07 (FR-05.3, FR-06.4): E006_CONDITIONAL_FORBIDDEN.

    The same three fields non-null on `arm == "seeded"`, `turn_cost.turn`
    non-null on the mutation arm, and a timeout carrying a signal.
    """
    for name, value in (("mutator_id", "widen-integer-width"),
                        ("mutator_seed_int", 17), ("source_test_path", "test/a.mlir")):
        error = raises("E006_CONDITIONAL_FORBIDDEN", schema.validate,
                       edit(seeded_spec(), **{name: value}))
        assert f"ProbeSpec.{name} must be None when arm is 'seeded'" in str(error)
    spec = mutation_spec()
    raises("E006_CONDITIONAL_FORBIDDEN", schema.validate,
           edit(spec, turn_cost=spec.turn_cost | {"turn": "probe_write"}))
    raises("E006_CONDITIONAL_FORBIDDEN", schema.validate,
           edit(result(), build_status="timeout", signal="SIGKILL"))


def test_T_U_schema_08():
    """T-U-schema-08 (FR-03.10, FR-08.3, FR-14.6, FR-14.8): E007_BAD_DICT_KEYS.

    Each of the eight declared dicts of `03-LLD.md` §2.6, once with a missing key
    and once with an extra one: an extra key fails as loudly as a missing one.
    `RunManifest.stages_metered`'s key set is exactly `_STAGE_IDS`.
    """
    differential = {"stimulus_id": "lfsr32-v1", "reset_protocol": "hold-8-then-release",
                    "sample_point": "pre-posedge", "cycles": 64, "port_list_sha": ""}
    owners = {
        ("BudgetFile", "max_tool_iterations"): budget(),
        ("ProbeSpec", "turn_cost"): seeded_spec(),
        ("ProbeSpec", "differential"): edit(seeded_spec(), differential=differential),
        ("LedgerEntry", "observed"): entry(),
        ("RunManifest", "image_spec"): manifest(),
        ("RunManifest", "issue_mirror"): manifest(),
        ("RunManifest", "differential_driver"): manifest(),
        ("RunManifest", "model_ids"): manifest(),
        ("RunManifest", "stages_metered"): manifest(),
    }
    assert set(owners) == set(schema._DICT_KEYS), "nine declared dicts, no more"
    for (cls_name, field), obj in owners.items():
        valid = getattr(obj, field)
        assert set(valid) == schema._DICT_KEYS[(cls_name, field)]
        schema.validate(obj)
        missing = {k: v for k, v in valid.items() if k != sorted(valid)[0]}
        raises("E007_BAD_DICT_KEYS", schema.validate, edit(obj, **{field: missing}))
        raises("E007_BAD_DICT_KEYS", schema.validate,
               edit(obj, **{field: valid | {"extra_key": None}}))
    assert schema._DICT_KEYS[("RunManifest", "stages_metered")] == set(schema._STAGE_IDS)


def test_T_U_schema_09():
    """T-U-schema-09 (FR-17.7): E008_CAP_EXCEEDED from `bound_text`.

    Over the cap with no companion path is the one combination that would
    silently lose an artefact.
    """
    error = raises("E008_CAP_EXCEEDED", schema.bound_text, "x" * 300, None, 256)
    assert "300 bytes" in str(error) and "256-byte cap" in str(error)


def test_T_U_schema_10():
    """T-U-schema-10 (FR-04.3): E009_UNKNOWN_SCHEMA from `from_json` and `validate`.

    A class outside `_MEMBERS` is refused by both, the nested dataclasses
    included.
    """
    raises("E009_UNKNOWN_SCHEMA", schema.from_json, "{}", schema.FeedbackEntry)
    raises("E009_UNKNOWN_SCHEMA", schema.from_json, "{}", dict)
    raises("E009_UNKNOWN_SCHEMA", schema.validate,
           schema.FeedbackEntry(probe_id="p", stopped_at_stage="gate", reason="r"))
    raises("E009_UNKNOWN_SCHEMA", schema.validate, schema.RunCommit(commit="c"))
    raises("E009_UNKNOWN_SCHEMA", schema.validate,
           schema.LedgerSnapshot(arm="seeded", unit="wall_clock_seconds",
                                 spent=0.0, cap=1.0))


def test_T_U_schema_11():
    """T-U-schema-11 (FR-01.6, NFR-02): serialiser determinism.

    Two equal objects produce byte-identical `to_json`: keys sorted, two-space
    indent, `ensure_ascii=False`, one trailing newline, UTF-8, no BOM. Asserted
    over one instance of each of the seven members and over a 1,000-shuffle
    permutation of every dict field.
    """
    rng = random.Random(0)
    for obj in every_member():
        expected = schema.to_json(obj)
        document = json.loads(expected)
        assert list(document) == sorted(document), "keys sorted"
        assert expected.endswith("\n") and not expected.endswith("\n\n")
        assert expected.encode("utf-8").decode("utf-8-sig") == expected, "no BOM"
        assert "\n  " in expected, "two-space indent"
        for _ in range(1000):
            fields = dataclasses.asdict(obj)
            shuffled = {}
            for name in rng.sample(list(fields), len(fields)):
                value = fields[name]
                if isinstance(value, dict):
                    value = {k: value[k] for k in rng.sample(list(value), len(value))}
                shuffled[name] = value
            assert schema.to_json(type(obj)(**shuffled)) == expected
    unicode_result = edit(result(), assertion_text="assert `π ≠ 3` failed.",
                          assertion_site="Unicode.cpp:1")
    assert "π ≠ 3" in schema.to_json(unicode_result), "ensure_ascii=False"


def test_T_U_schema_12():
    """T-U-schema-12 (FR-04.3, FR-16.1): `to_json` then `from_json` round-trips.

    Every member survives, and `FeedbackEntry` and `RunCommit` come back as
    dataclasses rebuilt in the owning member's `__post_init__`, not as dicts.
    `LedgerSnapshot` has no owning member, so it round-trips only as far as
    `to_json`; `from_json` refuses it, `_MEMBERS` being the closed set.
    """
    for obj in every_member():
        text = schema.to_json(obj)
        back = schema.from_json(text, type(obj))
        assert back == obj
        assert schema.to_json(back) == text
    rebuilt = schema.from_json(schema.to_json(bundle()), schema.FeedbackBundle)
    assert all(isinstance(e, schema.FeedbackEntry) for e in rebuilt.entries)
    assert rebuilt.entries[0].probe_id == "p-0000000001"
    rebuilt_manifest = schema.from_json(schema.to_json(manifest()), schema.RunManifest)
    assert all(isinstance(c, schema.RunCommit) for c in rebuilt_manifest.run_commit)
    snapshot = schema.LedgerSnapshot(arm="seeded", unit="wall_clock_seconds",
                                     spent=12.0, cap=14400.0)
    assert json.loads(schema.to_json(snapshot)) == dataclasses.asdict(snapshot)
    raises("E009_UNKNOWN_SCHEMA", schema.from_json,
           schema.to_json(snapshot), schema.LedgerSnapshot)


def test_T_U_schema_13():
    """T-U-schema-13 (FR-04.3): the version check, and nothing else.

    `check_version` accepts an equal MAJOR with any MINOR and rejects any other
    MAJOR in either direction. It never negotiates, shims or tolerates.
    """
    for accepted in ("2.0", "2.7", "2.13", "2.0.1"):
        assert schema.check_version(accepted) is None
    for rejected in ("1.0", "1.9", "3.0", "10.0", "0.1"):
        raises("E001_MAJOR_MISMATCH", schema.check_version, rejected)


def test_T_U_schema_14():
    """T-U-schema-14 (FR-06.4, FR-07.8, FR-17.7): `_probe_result_conditionals`.

    `oracle_class` non-null exactly when `oracle_fired`; a `timeout` carries a
    null signal; `reduced_text` requires `reduced_path`.
    """
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(result(), oracle_fired=False))
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(result(), oracle_class=None))
    schema.validate(edit(result(), build_status="timeout", signal=None,
                         limit_hit="wall"))
    raises("E006_CONDITIONAL_FORBIDDEN", schema.validate,
           edit(result(), build_status="timeout", signal="SIGTERM"))
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(result(), reduced_path=None))
    schema.validate(edit(result(), reduced_text=None, reduced_path=None))
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(result(), oracle_class="crash"))


def test_T_U_schema_15():
    """T-U-schema-15 (FR-02.7, FR-12.2, FR-18.10): `_manifest_conditionals`.

    A discovery manifest has one `run_commit` with a null `seed_sha`, a
    calibration manifest one per sampled seed; `arm_order` names both arms
    exactly once; `local_id_range` is an ordered pair.
    """
    discovery = manifest()
    schema.validate(discovery)
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(discovery, run_commit=list(discovery.run_commit) * 2))
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(discovery, run_commit=[schema.RunCommit(commit="a" * 40,
                                                        seed_sha="b" * 40)]))
    sample = ["c" * 40, "d" * 40]
    calibration = edit(
        discovery, mode="calibration", calibration_sample=sample,
        run_commit=[schema.RunCommit(commit="e" * 40, seed_sha=sample[0]),
                    schema.RunCommit(commit="f" * 40, seed_sha=sample[1])])
    schema.validate(calibration)
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(calibration, calibration_sample=[sample[0]]))
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(calibration, run_commit=[schema.RunCommit(commit="e" * 40)]))
    raises("E004_BAD_ENUM", schema.validate,
           edit(discovery, arm_order=["seeded", "seeded"]))
    raises("E004_BAD_ENUM", schema.validate,
           edit(discovery, arm_order=["seeded", "mutation", "seeded"]))
    raises("E003_WRONG_TYPE", schema.validate,
           edit(discovery, local_id_range=[999999999, 900000000]))
    raises("E003_WRONG_TYPE", schema.validate, edit(discovery, local_id_range=[1]))


def test_T_U_schema_16():
    """T-U-schema-16 (FR-01.10, FR-14.1, FR-16.6): the three remaining conditionals.

    `FeedbackBundle.abandon_reason` non-null exactly when `abandoned`;
    `SeedRecord`'s four per-run-line lists equal in length;
    `BudgetFile.arm_window_seconds` positive.
    """
    raises("E005_CONDITIONAL_REQUIRED", schema.validate, edit(bundle(), abandoned=True))
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(bundle(), abandon_reason="no_new_fingerprints"))
    schema.validate(edit(bundle(), abandoned=True, abandon_reason="no_new_fingerprints"))
    one = seed()
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(one, run_lines=one.run_lines * 2))
    raises("E005_CONDITIONAL_REQUIRED", schema.validate,
           edit(one, polarity=one.polarity * 2))
    for bad in (0, -1.0):
        raises("E003_WRONG_TYPE", schema.validate, edit(budget(), arm_window_seconds=bad))


def test_T_U_schema_17():
    """T-U-schema-17 (FR-17.7): `bound_text`'s cap, on both sides of it.

    The text comes back at or under the cap and `None` above it with a path
    present; the companion path field is populated in both cases.
    """
    path = "/artefacts/run/probe/stderr.txt"
    assert schema.bound_text("x" * 256, path, 256) == "x" * 256
    assert schema.bound_text("x" * 255, path, 256) == "x" * 255
    assert schema.bound_text("x" * 257, path, 256) is None
    assert schema.bound_text(None, path, 256) is None
    assert schema.bound_text("π" * 128, path, 256) == "π" * 128   # cap is in bytes
    assert schema.bound_text("π" * 129, path, 256) is None


def test_T_U_schema_18():
    """T-U-schema-18 (FR-06.4, FR-07.3): a non-UTF-8 capture survives the seam.

    Stderr decoded with `errors="backslashreplace"` round-trips byte for byte
    through `to_json` and `from_json`, and the destructive decoder is used
    nowhere in the flow, asserted by a source search.
    """
    raw = b"circt-opt: assertion `name == \xff\xfe' failed.\n"
    decoded = raw.decode("utf-8", errors="backslashreplace")
    assert "\\xff\\xfe" in decoded
    assert decoded.encode("utf-8").decode("utf-8", errors="backslashreplace") == decoded
    carried = edit(result(), assertion_text=decoded, assertion_site="Name.cpp:1")
    back = schema.from_json(schema.to_json(carried), schema.ProbeResult)
    assert back.assertion_text == decoded
    # Both spellings, the keyword AND the POSITIONAL: `decode("utf-8",
    # "replace")` passed the keyword-only search for a week and is what W-08's
    # erratum 20 found in `corpus.py`, so the check is now an `ast` walk over
    # every `decode` and `decode_bytes` call in the flow rather than a grep.
    import ast

    offenders = []
    for source in sorted(_FLOW_DIR.rglob("*.py")):
        # `_shipped/` is the staged package the workers import (W-20b): a copy
        # of CHIA patched at start-up, not this repository's code, and not
        # always even parseable by this interpreter.
        if "_shipped" in source.parts:
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "attr", "") not in ("decode", "decode_bytes"):
                continue
            given = [ast.literal_eval(a) for a in node.args
                     if isinstance(a, ast.Constant)]
            given += [ast.literal_eval(k.value) for k in node.keywords
                      if k.arg == "errors" and isinstance(k.value, ast.Constant)]
            if "replace" in given:
                offenders.append(f"{source}:{node.lineno}")
    assert offenders == [], f"the destructive decoder is used at {offenders}"


def test_T_U_schema_19():
    """T-U-schema-19 (FR-14.4): `_check_field`'s two deviations from isinstance.

    An `int` satisfies a `float` annotation, because `isinstance(5, float)` is
    `False` and every duration the loop computes is a whole number of seconds; a
    `bool` does not satisfy an `int` annotation, because `isinstance(True, int)`
    is `True` and a bool where a count belongs is a defect.
    """
    assert isinstance(5, float) is False and isinstance(True, int) is True
    schema.validate(edit(entry(), amount=5))
    schema.validate(edit(manifest(), lag_days=6, arm_window_seconds=14400))
    schema.validate(edit(budget(), arm_window_seconds=600))
    raises("E003_WRONG_TYPE", schema.validate, edit(entry(), amount=True))
    error = raises("E003_WRONG_TYPE", schema.validate, edit(manifest(), lag_commits=True))
    assert "RunManifest.lag_commits is bool, expected int" in str(error)
    raises("E003_WRONG_TYPE", schema.validate, edit(seeded_spec(), iteration=False))


def test_T_U_schema_20():
    """T-U-schema-20 (FR-01.1, FR-04.3, FR-05.1): contract 2.0's two new fields.

    `SeedRecord.diff` and `SeedRecord.test_files` are required, so `None` on
    either raises `E002_MISSING_FIELD` naming it, and a payload lacking either
    raises `E002` listing both sorted. A `1.0` payload is rejected by
    `check_version`, so the MINOR drop rule can never lose them.
    """
    assert schema.CONTRACT_VERSION == "2.2"
    for name in ("diff", "test_files"):
        error = raises("E002_MISSING_FIELD", schema.validate, edit(seed(), **{name: None}))
        assert f"SeedRecord.{name} is None" in str(error)
    document = payload("seed_record/exact_pin_01.json")
    del document["diff"]
    del document["test_files"]
    error = raises("E002_MISSING_FIELD", schema.from_json,
                   json.dumps(document), schema.SeedRecord)
    assert "['diff', 'test_files']" in str(error)
    older = payload("seed_record/exact_pin_01.json") | {"contract_version": "1.0"}
    raises("E001_MAJOR_MISMATCH", schema.from_json, json.dumps(older), schema.SeedRecord)
    # the MINOR drop rule: an unknown key is dropped, the declared ones survive
    newer = payload("seed_record/exact_pin_01.json") | {"contract_version": "2.9",
                                                        "field_from_the_future": 1}
    survived = schema.from_json(json.dumps(newer), schema.SeedRecord)
    assert survived.diff and survived.test_files
    assert not hasattr(survived, "field_from_the_future")


def test_T_U_schema_21():
    """T-U-schema-21 (FR-04.2): E010_TOOL_MISMATCH is in the closed set, unraised here.

    A `ProbeSpec` whose `tool` is `firtool` against a seed whose `entry_tool` is
    `circt-opt` is accepted by `validate`: `ProbeSpec.tool` is annotated `str`
    and `validate` is handed one object with no access to the `SeedRecord` the
    comparison needs. `T-U-gen-03` puts the check in the emitter instead.
    """
    assert seed().entry_tool == "circt-opt"
    mismatched = edit(seeded_spec(), tool="firtool")
    assert schema.validate(mismatched) is None
    assert "E010_TOOL_MISMATCH" in schema.ERROR_CODES
    assert len(schema.ERROR_CODES) == 10
    assert [code.split("_")[0] for code in schema.ERROR_CODES] == [
        f"E{n:03d}" for n in range(1, 11)]


def test_T_U_schema_22():
    """T-U-schema-22 (FR-17.4): `CounterBlock` is not a contract member.

    It is absent from `_MEMBERS`, so `validate` raises `E009_UNKNOWN_SCHEMA` on
    one and `from_json` refuses the class; `dataclasses.asdict` still serialises
    it for the driver's log; and its addition moved neither MAJOR nor MINOR.
    """
    block = schema.CounterBlock(stage="stage_2", started=10, completed=9, failed=1,
                                seconds=41.5)
    assert schema.CounterBlock not in schema._MEMBERS
    raises("E009_UNKNOWN_SCHEMA", schema.validate, block)
    raises("E009_UNKNOWN_SCHEMA", schema.from_json, schema.to_json(block),
           schema.CounterBlock)
    assert json.loads(schema.to_json(block)) == dataclasses.asdict(block)
    assert block.started == block.completed + block.failed
    assert block.stage in schema._COUNTER_STAGES
    assert set(schema._COUNTER_STAGES) == set(schema._STAGE_IDS) | {
        "image", "corpus", "pin", "mirror", "synthesis",
        # Five added at the join (W-17, errata row 22): 3.11 requires a block of
        # EVERY node of 3.2 and none of these five had a stage to name.
        "feedback", "budget", "ledger", "artefact", "results"}
    assert schema.CONTRACT_VERSION == "2.2"


def test_T_U_schema_23():
    """T-U-schema-23 (FR-04.3, FR-17.7): FR-04.3's disjunction, as amended.

    `_probe_spec_conditionals` accepts a spec with `input_text` `None` and
    `input_path` populated, accepts one with both, and raises
    `E002_MISSING_FIELD` naming FR-04.3 when `input_path` is empty and
    `input_text` is `None`.
    """
    spec = seeded_spec()
    assert spec.input_text and spec.input_path
    schema.validate(spec)
    schema.validate(edit(spec, input_text=None))
    error = raises("E002_MISSING_FIELD", schema.validate,
                   edit(spec, input_text=None, input_path=""))
    assert "FR-04.3" in str(error)
    schema.validate(edit(spec, input_path=""))


#: the four keys the 2026-09-14 backend decision added to `budget.yaml`, three of
#: which are money (`03-LLD.md` §9.1, `01-FRD.md` §1.8).
_MONEY = ("campaign_spend_cap_usd", "price_usd_per_m_input_tokens",
          "price_usd_per_m_output_tokens")
_NEW_BUDGET_KEYS = ("model_id",) + _MONEY


def test_T_U_schema_24():
    """T-U-schema-24 (FR-14.1, NFR-08): the four 2026-09-14 keys are REQUIRED.

    `model_id` and the three money figures are what NFR-08's USD cap and
    FR-14.6's cost arithmetic are computed from, so each is `None`-rejected by
    name and a payload lacking all four raises `E002` listing all four sorted.
    """
    for name in _NEW_BUDGET_KEYS:
        error = raises("E002_MISSING_FIELD", schema.validate,
                       edit(budget(), **{name: None}))
        assert f"BudgetFile.{name} is None" in str(error)
    document = payload("budget_file/complete_01.json")
    for name in _NEW_BUDGET_KEYS:
        del document[name]
    error = raises("E002_MISSING_FIELD", schema.from_json,
                   json.dumps(document), schema.BudgetFile)
    assert str(sorted(_NEW_BUDGET_KEYS)) in str(error)


def test_T_U_schema_25():
    """T-U-schema-25 (FR-14.1, NFR-08): `model_id` names a model, or raises.

    One model id serves every agent stage, so an empty or blank one is a
    campaign with no model rather than a campaign with a default; it raises
    `E002_MISSING_FIELD`. A non-string raises `E003` from the type check first.
    """
    assert budget().model_id == "gemini-3.8-flash"
    for blank in ("", "   ", "\t\n"):
        error = raises("E002_MISSING_FIELD", schema.validate,
                       edit(budget(), model_id=blank))
        assert "BudgetFile.model_id must name a model" in str(error)
    raises("E003_WRONG_TYPE", schema.validate, edit(budget(), model_id=7))


def test_T_U_schema_26():
    """T-U-schema-26 (FR-14.1, NFR-08): the cap and both prices are POSITIVE.

    A zero or negative spend cap would stop the campaign before its first turn
    and a zero price would report a spend of nothing against NFR-08's cap, so
    each of the three raises `E003_WRONG_TYPE` naming itself.
    """
    for name in _MONEY:
        for bad in (0, 0.0, -1, -0.75):
            error = raises("E003_WRONG_TYPE", schema.validate,
                           edit(budget(), **{name: bad}))
            assert f"BudgetFile.{name} must be positive and finite" in str(error)
    assert (budget().campaign_spend_cap_usd, budget().price_usd_per_m_input_tokens,
            budget().price_usd_per_m_output_tokens) == (200.0, 0.75, 3.75)


def test_T_U_schema_27():
    """T-U-schema-27 (FR-14.1, NFR-08): the three are FINITE, and an int is one.

    An infinite or NaN cap is a cap that never binds and an infinite price makes
    every `cost_usd` infinite, so both raise `E003_WRONG_TYPE`; an `int` is
    accepted for all three, which is `03-LLD.md` §2.3's float rule.
    """
    for name in _MONEY:
        for bad in (float("inf"), float("-inf"), float("nan")):
            raises("E003_WRONG_TYPE", schema.validate, edit(budget(), **{name: bad}))
        assert schema.validate(edit(budget(), **{name: 1})) is None
    assert schema.validate(edit(budget(), campaign_spend_cap_usd=200,
                                price_usd_per_m_input_tokens=1,
                                price_usd_per_m_output_tokens=4)) is None
