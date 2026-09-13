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


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """The committed contract fixture directory."""
    return FIXTURES
