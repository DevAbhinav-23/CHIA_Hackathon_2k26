"""Stub of CHIA's examples/circt_issue_solver/issue_task.py.

Constructed, and it carries the `elif backend == "vertex":` line ALREADY: this
fixture exists to exercise sync-to-chia.sh's already-present guard, which is
what makes a checkout synced twice not patched twice (03-LLD.md 1.4). The
patch's own application against a real checkout is the tier-1 test.
"""


def _turn(backend: str) -> None:
    """The branch the guard looks for, and nothing around it."""
    if backend == "claude":
        return None
    elif backend == "vertex":
        return None
    return None
