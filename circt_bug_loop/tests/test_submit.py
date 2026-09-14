"""`bug_loop_submit.sh` (`03-LLD.md` §13.3), the `T-U-submit-*` tests of §1.25.

All tier 0. Two of the four read the script; the other two RUN it, with a stub
`chia` on `PATH` that prints its own argv and exits, so the `exec` line and the
JSON it builds are asserted on what the wrapper actually passes rather than on
a regular expression over its text. Nothing is submitted and no cluster is
touched: the stub is the whole of `chia` for the length of the test.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from circt_bug_loop import bug_loop

pytestmark = pytest.mark.t0

SUBMIT = Path(bug_loop.FLOW_DIR) / "bug_loop_submit.sh"


def run_submit(tmp_path: Path, env: dict, *args) -> subprocess.CompletedProcess:
    """Run the wrapper with a stub `chia` that records its argv and exits 0.

    `BUGLOOP_CHIA` and `BUGLOOP_PY` are the script's own two overrides, so the
    stub needs no `PATH` surgery and the Python that builds the JSON is this
    interpreter.
    """
    stub = tmp_path / "chia-stub"
    stub.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n', encoding="utf-8")
    stub.chmod(0o755)
    return subprocess.run(
        ["bash", str(SUBMIT), *args], capture_output=True, text=True,
        env={"PATH": os.environ["PATH"], "HOME": str(tmp_path),
             "BUGLOOP_CHIA": str(stub), "BUGLOOP_PY": sys.executable, **env})


def test_T_U_submit_01():
    """T-U-submit-01 (NFR-06, FR-17.5, FR-17.9): no credential of either kind, flag kept.

    The three names are looked for as SHELL text: `GITHUB_TOKEN` and
    `GEMINI_API_KEY` may not be read, expanded or forwarded anywhere in the
    script, and neither may the interlock. `--runtime-env-json` itself stays,
    because a submitted job inherits none of the submitting shell's environment.
    Fixture: none. Tier 0.
    """
    text = SUBMIT.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    for forbidden in ("GITHUB_TOKEN", "GEMINI_API_KEY", bug_loop.LIVE_MODEL_ENV):
        assert forbidden not in code, forbidden
    assert "--runtime-env-json" in code
    assert code.count("GOOGLE_CLOUD_PROJECT") == 2       # the get and the key


def test_T_U_submit_02(tmp_path: Path):
    """T-U-submit-02 (FR-17.9): the two required variables, each named on its absence.

    Fixture: none. Tier 0.
    """
    assert "set -euo pipefail" in SUBMIT.read_text(encoding="utf-8")
    for missing, present in (("BUGLOOP_ARTEFACTS", {"BUGLOOP_IMAGE_TAG": "t"}),
                             ("BUGLOOP_IMAGE_TAG", {"BUGLOOP_ARTEFACTS": "/a"})):
        done = run_submit(tmp_path, present, "--mode", "discovery")
        assert done.returncode != 0, missing
        assert missing in done.stderr, (missing, done.stderr)


def test_T_U_submit_03(tmp_path: Path):
    """T-U-submit-03 (NFR-09, FR-20.6): the `exec`ed command line, argument for argument.

    Every argument of the wrapper reaches `bug_loop.py`, which is what makes
    `chia job logs <id>` show the driver's own output. Fixture: none. Tier 0.
    """
    done = run_submit(tmp_path, {"BUGLOOP_ARTEFACTS": str(tmp_path),
                                 "BUGLOOP_IMAGE_TAG": "eade0de61bc5"},
                      "--mode", "discovery", "--arm", "seeded")
    assert done.returncode == 0, done.stderr
    argv = done.stdout.splitlines()
    assert argv[:2] == ["job", "submit"]
    assert argv[2] == "--address" and argv[3].startswith("http")
    assert argv[4] == "--runtime-env-json"
    assert argv[6] == "--"
    assert argv[7] == sys.executable
    assert argv[8].endswith("bug_loop.py")
    assert argv[9:] == ["--mode", "discovery", "--arm", "seeded"]
    assert "--no-wait" not in argv

    waited = run_submit(tmp_path, {"BUGLOOP_ARTEFACTS": str(tmp_path),
                                   "BUGLOOP_IMAGE_TAG": "t", "NO_WAIT": "1"},
                        "--mode", "discovery")
    assert "--no-wait" in waited.stdout.splitlines()


def test_T_U_submit_04(tmp_path: Path):
    """T-U-submit-04 (FR-17.9): the JSON is built by Python and survives a hostile path.

    A root with a space and a root with a double quote both arrive as ONE
    argument that `json.loads` reads back, which string concatenation would not
    manage; `GOOGLE_CLOUD_PROJECT` appears only where the environment sets it.
    Fixture: none. Tier 0.
    """
    for root in (str(tmp_path / "a root"), str(tmp_path / 'a"root')):
        done = run_submit(tmp_path, {"BUGLOOP_ARTEFACTS": root,
                                     "BUGLOOP_IMAGE_TAG": "t"}, "--mode", "discovery")
        assert done.returncode == 0, done.stderr
        env_json = json.loads(done.stdout.splitlines()[5])
        assert env_json == {"env_vars": {"BUGLOOP_ARTEFACTS": root,
                                         "BUGLOOP_IMAGE_TAG": "t"}}

    with_gcp = run_submit(tmp_path, {"BUGLOOP_ARTEFACTS": str(tmp_path),
                                     "BUGLOOP_IMAGE_TAG": "t",
                                     "GOOGLE_CLOUD_PROJECT": "bugloop-project"},
                          "--mode", "discovery")
    assert json.loads(with_gcp.stdout.splitlines()[5])["env_vars"][
        "GOOGLE_CLOUD_PROJECT"] == "bugloop-project"

    empty = run_submit(tmp_path, {"BUGLOOP_ARTEFACTS": str(tmp_path),
                                  "BUGLOOP_IMAGE_TAG": "t",
                                  "GOOGLE_CLOUD_PROJECT": ""},
                       "--mode", "discovery")
    assert "GOOGLE_CLOUD_PROJECT" not in json.loads(
        empty.stdout.splitlines()[5])["env_vars"]
