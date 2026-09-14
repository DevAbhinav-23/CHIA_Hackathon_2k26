"""Shared configuration for the flow's tests (04-Test-Plan.md 0.3, 0.5).

The four tier markers are declared in the repository's pytest.ini and applied per
module with `pytestmark`; a test states the LOWEST tier it can run at.
"""
import os
from pathlib import Path

import pytest

from circt_bug_loop.contract import schema

#: `contract/fixtures/`, reached through the imported package rather than by
#: walking up from __file__: the flow lives at two different depths in two trees
#: (03-LLD.md 1.4), so no module here may walk past its own directory.
FIXTURES = Path(schema.__file__).resolve().parent / "fixtures"

_INTERLOCK = "BUGLOOP_ALLOW_LIVE_MODEL"


def call_node(fn, *args, **kwargs):
    """Call a `@ChiaFunction`-decorated node's undecorated original, with no Ray.

    `04-Test-Plan.md` §0.4 calls the wrapper itself, which routes through
    `chia.trace.profiler.get_profiler` (`chia:chia/base/ChiaFunction.py:110-120`);
    `get_profiler` starts a local Ray instance, which is slow and which raises a
    `FutureWarning` that `-W error` turns into an error. CHIA stores the
    undecorated function on the wrapper as `_chia_original`
    (`chia:chia/base/ChiaFunction.py:129`), so a unit test calls that and every
    node keeps the decorator `03-LLD.md` §3.2's column gives it. The placement
    the decorator declares is asserted statically instead, off `_chia_options`.

    A plain function passes through unchanged, so a test need not know whether
    what it is calling is a node. (Architect's decision, 2026-09-14.)
    """
    return getattr(fn, "_chia_original", fn)(*args, **kwargs)


@pytest.fixture(scope="session", autouse=True)
def no_live_model() -> None:
    """Refuse to run T0 to T2 with the live-model interlock set (04-Test-Plan.md 0.5).

    T3 is the one tier that sets it, and even there only the pilot does. A tier-0
    run that reached a model would spend money and would make a recorded fixture
    that no other run can reproduce, so the assertion is session-scoped and hard:
    no test sets the variable, and a caller's environment must not either.
    """
    assert _INTERLOCK not in os.environ, (
        f"{_INTERLOCK} is set; tiers T0 to T2 may not reach a model "
        "(04-Test-Plan.md 0.5). Unset it, or run the tier-3 suite deliberately.")


@pytest.fixture(scope="session", autouse=True)
def no_local_ray():
    """Assert that no test of tiers T0 to T2 started a local Ray (0.4).

    `call_node` exists so that every node keeps `03-LLD.md` §3.2's decorator
    while a unit test stays in-process, and the way that stops being true is
    quiet: one test that calls the wrapper instead starts a local Ray through
    the profiler, costs seconds, and leaks the warnings `-W error` then turns
    into a failure somewhere else. This is the check that names it here. The
    two cluster tiers legitimately hold a Ray, so it is skipped when either of
    `04-Test-Plan.md` §0.3's cluster variables is set.
    """
    yield
    if os.environ.get("BUGLOOP_CLUSTER") or os.environ.get("CHIA_LIVE_CLUSTER"):
        return
    import ray

    assert not ray.is_initialized(), (
        "a test started a local Ray: call every @ChiaFunction node through "
        "conftest.call_node (04-Test-Plan.md 0.4), which calls its "
        "_chia_original and leaves the decorator in place.")


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """The committed contract fixture directory."""
    return FIXTURES
