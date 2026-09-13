"""B5's textual reducer: line-level delta debugging, for what `circt-reduce` cannot open.

`03-LLD.md` §10.3 is normative for the algorithm and for the termination
argument; `01-FRD.md` FR-09.10 for the behaviour. `circt-reduce` stops at an
MLIR parse diagnostic before reduction begins on a `.fir` or a `.sv` file and
only reaches `Testing input with ...` on `.mlir` (C-17, executed), so the
languages it cannot open need a reducer of their own.

Standard library only, and in fact no import at all: this module knows nothing
about CIRCT, which is the one reason `03-LLD.md` §1.1 gives for it being a file
of its own rather than twenty lines inside `probe_task.py`. That is what lets
it be unit-tested with no CIRCT present (`04-Test-Plan.md` §1.10, wholly T0).
"""
from __future__ import annotations

from typing import Callable, Optional


def ddmin(lines: list[str], interesting: Callable[[list[str]], bool],
          max_calls: Optional[int] = None) -> tuple[list[str], int]:
    """Line-level delta debugging: the smallest 1-minimal subsequence that is interesting.

    *interesting* takes a list of lines and returns True when the recorded
    failure still reproduces; it is the same script `circt-reduce` would have
    been given (FR-09.1, FR-09.10), invoked through the same wrapper.

    The loop terminates because the pair `(len(lines), len(lines) - n)`, ordered
    lexicographically over non-negative integers, strictly decreases on every
    pass that does not break: an interesting subset or complement shortens
    `lines`, and an uninteresting pass with `n < len(lines)` grows `n`
    (`03-LLD.md` §10.3). On exit the result is 1-minimal unless *max_calls*
    truncated it, which is a budget and not a termination condition: such a
    reduction carries `fixpoint=False` and `budget_truncated=True` so NFR-02
    keeps it visible.

    Returns:
        (the reduced lines, the number of interestingness calls spent).
    Worker:
        pure; it knows nothing about CIRCT and takes no worker resource.
    Raises:
        ValueError when the input is not interesting to begin with, which is a
        defect in the caller rather than a reduction outcome.
    """
    if not interesting(lines):
        raise ValueError("ddmin: the input is not interesting to begin with")
    calls = 1
    n = 2
    while len(lines) >= 2:
        chunk = max(1, len(lines) // n)
        subsets = [lines[i:i + chunk] for i in range(0, len(lines), chunk)]
        reduced = False
        for subset in subsets:                        # first, try each subset alone
            calls += 1
            if interesting(subset):
                lines, n, reduced = subset, 2, True
                break
        if not reduced:
            for i in range(len(subsets)):             # then, try each complement
                complement = [x for j, s in enumerate(subsets) if j != i for x in s]
                calls += 1
                if complement and interesting(complement):
                    lines, n, reduced = complement, max(n - 1, 2), True
                    break
        if not reduced:
            if n >= len(lines):
                break                                 # 1-minimal: nothing more to remove
            n = min(len(lines), 2 * n)
        if max_calls is not None and calls >= max_calls:
            break
    return lines, calls
