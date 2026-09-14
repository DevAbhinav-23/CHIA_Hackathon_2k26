"""`pin_select.py` (A2): the release-pinned-main selector."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from circt_bug_loop import pin_select
from circt_bug_loop.tests.conftest import call_node

#: This module's own fixture root, reached from `__file__` and never above it.
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pin_select"

#: The pair W-04 built the image from.
W04_ORIGIN_MAIN = "eab8d18294469806fa48998f44da5c96eafe1d1b"
W04_RUN_COMMIT = "eade0de61bc5a0d2ba1b9da951b69efcab19f8ce"
W04_PIN_SHA = "6279700538792da0c5a08e17babfe9b6e824c69f"
W04_PIN_TAG = "firtool-1.159.0"
W04_TAGS = ["firtool-1.159.0", "firtool-1.158.0", "firtool-1.157.0"]
W04_LAG_COMMITS = 8
W04_LAG_DAYS = 4.807

#: The eight fields `03-LLD.md` §3.4's **Returns** paragraph names.
FIELDS = {"run_commit", "pin_sha", "pin_tag", "tags_sharing_pin", "lag_commits",
          "lag_days", "current_window_has_release", "resolved_utc", "counters"}


class _RecordedGit:
    """`corpus._Git` with the recorded stdout of one fixture in its place."""

    def __init__(self, commands: dict):
        self.commands = commands
        self.argv: list[list[str]] = []
        self.calls = 0

    def __call__(self, *args: str) -> str:
        self.calls += 1
        self.argv.append(list(args))
        key = " ".join(args)
        if key not in self.commands:
            raise AssertionError(f"the fixture recorded no `git {key}`")
        return self.commands[key]


@pytest.fixture
def replay(monkeypatch):
    """Install one recorded fixture in place of the module's git layer."""

    def install(name: str):
        data = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
        git = _RecordedGit(data["commands"])
        monkeypatch.setattr(pin_select, "_Git", lambda *a, **k: git)
        return data, git

    return install


def _select(data: dict):
    """Run the node against whatever `replay` installed, at the fixture's ref."""
    return call_node(pin_select.select_release_pinned_main, "<replayed>",
                     ref=data["ref"])


def _log(data: dict) -> list[tuple[str, int]]:
    """The fixture's own `log --first-parent` excerpt, as (sha, commit date)."""
    key = f"log --first-parent --format=%H\t%ct\t%s {data['ref']}"
    return [(line.split("\t")[0], int(line.split("\t")[1]))
            for line in data["commands"][key].splitlines()]


def _tag_pins(data: dict) -> dict[str, str]:
    """The fixture's tag map: tag name to the `llvm` gitlink its ls-tree gave."""
    return {args[1]: out.split()[2]
            for args, out in ((key.split(" "), value)
                              for key, value in data["commands"].items())
            if args[0] == "ls-tree" and args[1].startswith("firtool-")}


@pytest.mark.t0
def test_T_U_pin_01(replay):
    """T-U-pin-01 (FR-02.1): the first-parent walk, on full SHAs."""
    data, git = replay("head_pin_unreleased")
    out = _select(data)

    assert set(out) == FIELDS
    assert out["run_commit"] == W04_RUN_COMMIT
    assert out["pin_sha"] == W04_PIN_SHA and len(out["pin_sha"]) == 40

    commit_pin = data["commands"][f"ls-tree {data['ref']} llvm"].split()[2]
    assert len(commit_pin) == 40 and commit_pin != out["pin_sha"]   # head's own
    assert _tag_pins(data)[out["pin_tag"]] == out["pin_sha"]

    shas = [sha for sha, _ in _log(data)]
    assert shas.index(out["run_commit"]) == W04_LAG_COMMITS
    assert out["lag_commits"] == W04_LAG_COMMITS
    print(f"\n{len(shas)} first-parent commits replayed, {git.calls} git calls, "
          f"chosen at position {shas.index(out['run_commit'])}")


@pytest.mark.t0
def test_T_U_pin_03(replay):
    """T-U-pin-03 (FR-02.2): lag_days is the difference of the two commit dates."""
    data, _ = replay("head_pin_unreleased")
    out = _select(data)

    log = dict(_log(data))
    head_at = _log(data)[0][1]
    expected = (head_at - log[out["run_commit"]]) / 86400.0
    assert out["lag_days"] == pytest.approx(expected)
    assert round(out["lag_days"], 3) == W04_LAG_DAYS


@pytest.mark.t0
def test_T_U_pin_04(replay):
    """T-U-pin-04 (FR-02.3): a one-bump-off pair is not a match, ever."""
    data, _ = replay("one_bump_off")
    head_pin = data["commands"][f"ls-tree {data['ref']} llvm"].split()[2]
    tag_pins = _tag_pins(data)
    assert list(tag_pins) == ["firtool-1.159.0"]
    assert tag_pins["firtool-1.159.0"] != head_pin

    with pytest.raises(pin_select.PinSelectError) as caught:
        _select(data)
    assert caught.value.reason == "no_match"
    assert head_pin in str(caught.value)                 # the last window
    assert "not widened" in str(caught.value)


@pytest.mark.t0
def test_T_U_pin_05(replay):
    """T-U-pin-05 (FR-02.5): an empty tag list refuses and walks nothing."""
    data, git = replay("no_tags")
    with pytest.raises(pin_select.PinSelectError) as caught:
        _select(data)
    assert caught.value.reason == "no_tags"
    assert "refs/tags/firtool-*" in str(caught.value)
    assert git.calls == 1 and git.argv[0][0] == "for-each-ref"


@pytest.mark.t0
def test_T_U_pin_06(replay):
    """T-U-pin-06 (FR-02.6): the newest by tag date wins and all are recorded."""
    data, _ = replay("head_pin_unreleased")
    out = _select(data)

    assert out["tags_sharing_pin"] == W04_TAGS
    assert out["pin_tag"] == W04_PIN_TAG == out["tags_sharing_pin"][0]
    tag_pins = _tag_pins(data)
    assert all(tag_pins[tag] == out["pin_sha"] for tag in out["tags_sharing_pin"])

    key = ("for-each-ref --format=%(refname:short)\t%(creatordate:unix) "
           "--sort=creatordate refs/tags/firtool-*")
    dates = {line.split("\t")[0]: int(line.split("\t")[1])
             for line in data["commands"][key].splitlines()}
    ordered = [dates[tag] for tag in out["tags_sharing_pin"]]
    assert ordered == sorted(ordered, reverse=True)
    assert len(dates) == 164                   # the whole tag map, not a slice


@pytest.mark.t0
@pytest.mark.parametrize("fixture,expected", [("head_pin_unreleased", False),
                                              ("head_pin_released", True),
                                              ("all_windows_released", True)])
def test_T_U_pin_07(replay, fixture: str, expected: bool):
    """T-U-pin-07 (FR-02.4): current_window_has_release is set on every run."""
    data, _ = replay(fixture)
    out = _select(data)
    assert out["current_window_has_release"] is expected
    assert (out["lag_commits"] == 0) is expected
    if expected:
        assert out["run_commit"] == data["ref"]
        assert out["lag_days"] == 0.0


@pytest.mark.t0
def test_T_U_pin_09(replay):
    """T-U-pin-09 (FR-02.1): every window released, so the walk stops."""
    data, git = replay("all_windows_released")
    out = _select(data)

    assert out["run_commit"] == data["ref"]
    assert out["lag_commits"] == 0 and out["lag_days"] == 0.0
    assert out["tags_sharing_pin"] == ["firtool-1.156.0"]
    assert len(set(_tag_pins(data).values())) == 2
    assert len(_log(data)) == 33                # both windows are in the excerpt


@pytest.mark.t0
def test_T_U_pin_10(replay):
    """T-U-pin-10 (FR-19.1): the decorator, the argv and the docstring."""
    node = pin_select.select_release_pinned_main
    assert node._chia_options == {"max_retries": 0}

    data, git = replay("head_pin_unreleased")
    out = _select(data)
    shapes = [argv[0] for argv in git.argv]
    assert shapes[0] == "for-each-ref" and shapes[-1] == "rev-list"
    assert git.argv[0] == ["for-each-ref",
                           "--format=%(refname:short)\t%(creatordate:unix)",
                           "--sort=creatordate", "refs/tags/firtool-*"]
    assert ["log", "--first-parent", "--format=%H\t%ct\t%s",
            data["ref"]] in git.argv
    assert ["log", "--first-parent", "--raw", "--no-abbrev",
            "--format=COMMIT %H", data["ref"], "--", "llvm"] in git.argv
    assert ["ls-tree", data["ref"], "llvm"] in git.argv
    assert git.argv[-1] == ["rev-list", "--first-parent", "--count",
                            f"{out['run_commit']}..{data['ref']}"]

    doc = node.__doc__ or ""
    assert doc.splitlines()[0].endswith(".")
    for paragraph in ("Returns:", "Worker:", "Raises:"):
        assert f"\n    {paragraph}\n" in doc, paragraph
    assert doc.index("Returns:") < doc.index("Worker:") < doc.index("Raises:")


def _clone() -> str:
    """The first candidate path that is a clone with an `origin/main`, or ""."""
    for candidate in (os.environ.get("BUGLOOP_PIN_CLONE"),
                      "~/.cache/chia-pin-smoke/circt", "~/.cache/circt"):
        if not candidate:
            continue
        path = os.path.expanduser(candidate)
        try:
            subprocess.run(["git", "-C", path, "rev-parse", "origin/main"],
                           capture_output=True, text=True, check=True,
                           timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        return path
    return ""


@pytest.mark.t1
@pytest.mark.needs_sdk
def test_T_U_pin_08():
    """T-U-pin-08, and T-U-pin-02's criterion with it (FR-02.1 to FR-02.4)."""
    clone = _clone()
    if not clone:
        pytest.skip("no llvm/circt clone with an origin/main; see "
                    "circt_bug_loop/tests/fixtures/pin_select/make_fixtures.py")

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", clone, *args], capture_output=True,
                              text=True, check=True, timeout=300).stdout

    out = call_node(pin_select.select_release_pinned_main, clone,
                    ref="origin/main")
    head = git("rev-parse", "origin/main").strip()
    print(f"\norigin/main {head}\n  run_commit {out['run_commit']}"
          f"\n  pin_tag    {out['pin_tag']}  of {out['tags_sharing_pin']}"
          f"\n  pin_sha    {out['pin_sha']}"
          f"\n  lag        {out['lag_commits']} commits, "
          f"{out['lag_days']:.3f} days"
          f"\n  current_window_has_release {out['current_window_has_release']}")

    assert set(out) == FIELDS
    assert git("ls-tree", out["run_commit"], "llvm").split()[2] == out["pin_sha"]
    assert git("ls-tree", out["pin_tag"], "llvm").split()[2] == out["pin_sha"]
    assert out["lag_commits"] == int(git(
        "rev-list", "--first-parent", "--count",
        f"{out['run_commit']}..origin/main").strip())
    assert out["lag_days"] == pytest.approx(
        (int(git("log", "-1", "--format=%ct", "origin/main"))
         - int(git("log", "-1", "--format=%ct", out["run_commit"]))) / 86400.0)
    assert out["current_window_has_release"] is (
        out["lag_commits"] == 0 and out["run_commit"] == head)

    if head != W04_ORIGIN_MAIN:
        pytest.skip(f"main moved from {W04_ORIGIN_MAIN} to {head}; the "
                    "invariants above held and the new pair is printed")
    assert out["run_commit"] == W04_RUN_COMMIT
    assert out["pin_sha"] == W04_PIN_SHA
    assert out["pin_tag"] == W04_PIN_TAG
    assert out["tags_sharing_pin"] == W04_TAGS
    assert out["lag_commits"] == W04_LAG_COMMITS
    assert round(out["lag_days"], 3) == W04_LAG_DAYS
    assert out["current_window_has_release"] is False
