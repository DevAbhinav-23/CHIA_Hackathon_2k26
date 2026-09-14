"""B5's textual reducer: line-level delta debugging, for what `circt-reduce` cannot open."""
from __future__ import annotations

from typing import Callable, Optional


def ddmin(lines: list[str], interesting: Callable[[list[str]], bool],
          max_calls: Optional[int] = None) -> tuple[list[str], int]:
    """Line-level delta debugging: the smallest 1-minimal subsequence that is interesting."""
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
