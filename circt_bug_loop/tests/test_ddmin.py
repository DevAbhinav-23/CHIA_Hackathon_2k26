"""`04-Test-Plan.md` §1.10: the eight tests of `ddmin.py` (B5's textual reducer)."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from circt_bug_loop.ddmin import ddmin

pytestmark = pytest.mark.t0

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ddmin"


def _lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


@pytest.fixture
def case_200_3() -> tuple[list[str], list[str]]:
    """The 200-line input whose interestingness depends on 3 lines (FR-09.10)."""
    return (_lines(FIXTURES / "200_3" / "input.mlir"),
            _lines(FIXTURES / "200_3" / "expected.mlir"))


def _counting(predicate):
    """Wrap *predicate* so a test can assert on the number of invocations."""
    calls = []

    def wrapped(lines: list[str]) -> bool:
        calls.append(len(lines))
        return predicate(lines)

    wrapped.calls = calls
    return wrapped


def test_u_ddmin_01_minimality_on_the_specified_fixture(case_200_3) -> None:
    """T-U-ddmin-01 (FR-09.10): exactly the three lines, in input order."""
    lines, expected = case_200_3
    needed = set(expected)
    out, _ = ddmin(lines, lambda ls: needed <= set(ls))
    assert out == expected


def test_u_ddmin_02_termination_on_an_adversarial_predicate() -> None:
    """T-U-ddmin-02 (FR-09.10): the loop exits by the `n >= len(lines)` break."""
    lines = _lines(FIXTURES / "adversarial" / "input.txt")
    whole = list(lines)
    predicate = _counting(lambda ls: ls == whole)

    pairs: list[tuple[int, int]] = []

    def trace_lines(frame, event, arg):
        if event == "line":
            local = frame.f_locals
            if isinstance(local.get("lines"), list) and isinstance(local.get("n"), int):
                pair = (len(local["lines"]), len(local["lines"]) - local["n"])
                if not pairs or pairs[-1] != pair:
                    pairs.append(pair)
        return trace_lines

    def trace_calls(frame, event, arg):
        return trace_lines if frame.f_code is ddmin.__code__ else None

    previous = sys.gettrace()
    sys.settrace(trace_calls)
    try:
        out, calls = ddmin(lines, predicate)
    finally:
        sys.settrace(previous)

    assert out == whole
    assert calls <= len(lines) ** 2
    assert len(pairs) > 1, "the variant was never observed"
    assert all(b < a for a, b in zip(pairs, pairs[1:])), pairs


def test_u_ddmin_03_uninteresting_input_raises() -> None:
    """T-U-ddmin-03 (FR-09.10): a caller defect, not a reduction outcome."""
    with pytest.raises(ValueError, match="not interesting to begin with"):
        ddmin(["a", "b"], lambda ls: False)


def test_u_ddmin_04_call_count_is_returned(case_200_3) -> None:
    """T-U-ddmin-04 (FR-09.10): `interestingness_calls` has a source."""
    lines, expected = case_200_3
    needed = set(expected)
    predicate = _counting(lambda ls: needed <= set(ls))
    _, calls = ddmin(lines, predicate)
    assert calls == len(predicate.calls)
    assert calls > 1


def test_u_ddmin_05_budget_truncation(case_200_3) -> None:
    """T-U-ddmin-05 (FR-09.10): `max_calls` stops it, still interesting."""
    lines, expected = case_200_3
    needed = set(expected)
    _, natural = ddmin(lines, lambda ls: needed <= set(ls))

    budget = natural // 4
    out, calls = ddmin(lines, lambda ls: needed <= set(ls), max_calls=budget)
    assert calls < natural
    assert calls >= budget          # it stops at the first check at or over the budget
    assert needed <= set(out)
    assert len(out) > len(expected), "a truncated reduction is not the fixpoint"


def test_u_ddmin_06_result_is_one_minimal(case_200_3) -> None:
    """T-U-ddmin-06 (FR-09.10): 1-minimality, checked exhaustively."""
    lines, expected = case_200_3
    needed = set(expected)
    out, _ = ddmin(lines, lambda ls: needed <= set(ls))
    for i in range(len(out)):
        assert not needed <= set(out[:i] + out[i + 1:])


def test_u_ddmin_07_degenerate_inputs() -> None:
    """T-U-ddmin-07 (FR-09.10): empty, single-line, and all-load-bearing."""
    assert ddmin([], lambda ls: True) == ([], 1)
    assert ddmin(["only"], lambda ls: ls == ["only"]) == (["only"], 1)
    every = ["a", "b", "c", "d"]
    out, calls = ddmin(every, lambda ls: len(ls) == 4)
    assert out == every
    assert calls > 1


def test_u_ddmin_08_standard_library_only_and_no_circt() -> None:
    """T-U-ddmin-08 (FR-09.10): the import walk that makes it tier 0."""
    source = (Path(__file__).resolve().parents[1] / "ddmin.py").read_text()
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add((node.module or "").split(".")[0])
    assert imported <= set(sys.stdlib_module_names), imported
    assert "circt_bug_loop" not in imported
    assert not {"subprocess", "os", "shutil"} & imported
