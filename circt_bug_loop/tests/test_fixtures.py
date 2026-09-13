"""`contract/fixtures/`: every committed fixture validates at its version.

`04-Test-Plan.md` §1.2, the three `T-U-fixt-*` tests. This is where
`02-HLD.md` §2.2's compatibility rule fires: a MAJOR bump fails the set until it
is re-recorded, and the failing test is what says so.
"""
import json
from pathlib import Path

import pytest

from circt_bug_loop.contract import schema
from circt_bug_loop.tests.conftest import FIXTURES

pytestmark = pytest.mark.t0

#: one fixture directory per contract member, which is the set `T-U-fixt-02`
#: requires each half's fixture set to cover.
_MEMBER_DIRS = {
    "seed_record": schema.SeedRecord,
    "budget_file": schema.BudgetFile,
    "probe_spec": schema.ProbeSpec,
    "probe_result": schema.ProbeResult,
    "feedback_bundle": schema.FeedbackBundle,
    "ledger_entry": schema.LedgerEntry,
    "run_manifest": schema.RunManifest,
}


def walk(root: Path) -> list[tuple[Path, type]]:
    """Every fixture document under *root*, paired with the class it records."""
    found = []
    for path in sorted(root.rglob("*.json")):
        member = path.relative_to(root).parts[0]
        assert member in _MEMBER_DIRS, f"{path} is in no member directory"
        found.append((path, _MEMBER_DIRS[member]))
    return found


def test_T_U_fixt_01():
    """T-U-fixt-01 (FR-04.3): every committed fixture passes `validate`.

    At the version it records, which is where `02-HLD.md` §2.2's compatibility
    rule fires: a MAJOR bump fails this test until the set is re-recorded.
    """
    found = walk(FIXTURES)
    assert found, "the fixture set is not empty"
    for path, cls in found:
        text = path.read_text(encoding="utf-8")
        assert not text.startswith("﻿"), f"{path} carries a BOM"
        document = json.loads(text)
        schema.check_version(document["contract_version"])
        instance = schema.from_json(text, cls)
        assert schema.validate(instance) is None
        assert schema.to_json(instance) == text, f"{path} is not canonical"


def test_T_U_fixt_02():
    """T-U-fixt-02 (FR-16.1): the fixture set covers all seven members.

    A half that never exercises a schema cannot discover that it broke it, so a
    missing member fails, naming it.
    """
    covered = {path.relative_to(FIXTURES).parts[0] for path, _ in walk(FIXTURES)}
    missing = sorted(set(_MEMBER_DIRS) - covered)
    assert not missing, f"no fixture for {missing}"
    assert set(_MEMBER_DIRS.values()) == set(schema._MEMBERS)


def test_T_U_fixt_03(tmp_path: Path):
    """T-U-fixt-03 (FR-04.3): a MAJOR mismatch fails rather than being re-recorded.

    Injected by writing a `3.0` copy into a temporary directory and running the
    same walk over it.
    """
    source, cls = walk(FIXTURES)[0]
    injected = tmp_path / source.relative_to(FIXTURES)
    injected.parent.mkdir(parents=True)
    document = json.loads(source.read_text(encoding="utf-8"))
    document["contract_version"] = "3.0"
    injected.write_text(json.dumps(document, sort_keys=True, indent=2,
                                   ensure_ascii=False) + "\n", encoding="utf-8")
    walked = walk(tmp_path)
    assert [p.name for p, _ in walked] == [injected.name]
    with pytest.raises(schema.ContractError) as caught:
        for path, member in walked:
            schema.from_json(path.read_text(encoding="utf-8"), member)
    assert caught.value.code == "E001_MAJOR_MISMATCH"
    assert cls is walked[0][1]
