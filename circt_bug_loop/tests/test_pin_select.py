"""`pin_select.py` (A2, F-02): the release-pinned-main selector.

`04-Test-Plan.md` §1.5's `pin` table. The tier-0 half replays the six git
commands `03-LLD.md` §4.11.1's table gives this module, recorded from the
blobless clone by `fixtures/pin_select/make_fixtures.py` and cut to an excerpt;
the real `select_release_pinned_main` body runs against those bytes, so the
walk, the equality rule, the multi-tag rule and both refusals are the code
under test and only git is replayed. The tier-1 half runs the same body
against the live clone and reproduces W-04's own pair.

The plan drives its tier-0 tests from `analysis/pin_window_raw.json`, which is
that file's *derived* form: windows, candidates and a tag list. Recorded git
output is used here instead because it exercises `corpus._read_tags` and
`corpus._walk_pins`, which is what §3.4 says A2 shares with A1 and what a
fixture of already-parsed windows would step over. The four recorded shapes
are the ones the walk can meet: head pin unreleased, head pin released, every
window released, and no release at all.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

from circt_bug_loop import pin_select
from circt_bug_loop.tests.conftest import call_node

#: This module's own fixture root, reached from `__file__` and never above it.
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "pin_select"

#: The pair W-04 built the image from, on 2026-09-14, at `origin/main`
#: `eab8d18294469806fa48998f44da5c96eafe1d1b`
#: (`analysis/measurements/2026-09-14-image-build.md` §1). The tier-1 test
#: asserts these only while `main` still ends at that commit, and asserts the
#: mechanical invariants either way.
W04_ORIGIN_MAIN = "eab8d18294469806fa48998f44da5c96eafe1d1b"
W04_RUN_COMMIT = "eade0de61bc5a0d2ba1b9da951b69efcab19f8ce"
W04_PIN_SHA = "6279700538792da0c5a08e17babfe9b6e824c69f"
W04_PIN_TAG = "firtool-1.159.0"
W04_TAGS = ["firtool-1.159.0", "firtool-1.158.0", "firtool-1.157.0"]
W04_LAG_COMMITS = 8
W04_LAG_DAYS = 4.807

#: The eight fields `03-LLD.md` §3.4's **Returns** paragraph names.
FIELDS = {"run_commit", "pin_sha", "pin_tag", "tags_sharing_pin", "lag_commits",
          "lag_days", "current_window_has_release", "resolved_utc"}


class _RecordedGit:
    """`corpus._Git` with the recorded stdout of one fixture in its place.

    It answers only the argument vectors the fixture recorded, so a change to
    a command line fails the test by name rather than by a wrong answer, and
    it counts and keeps every call, which is what the argv test asserts on.
    """

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


# --------------------------------------------------------------------------
# Tier 0: the four recorded shapes, plus the one-bump-off refusal.
# --------------------------------------------------------------------------

@pytest.mark.t0
def test_T_U_pin_01(replay):
    """T-U-pin-01 (FR-02.1, FR-02.3): the first-parent walk, on full SHAs.

    The chosen commit is the FIRST line of the recorded first-parent log whose
    pin has a release, and every line above it has a pin that has none, which
    is what makes "newest" first-parent position rather than commit date. The
    equality asserted is between the two recorded `ls-tree` outputs, 40
    characters each, and not between the returned field and itself.
    """
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
    """T-U-pin-03 (FR-02.2): lag_days is the difference of the two commit dates.

    Recomputed from the `%ct` fields of the fixture's own log excerpt, so the
    assertion is against git's seconds and not against the node's arithmetic
    restated. W-04 recorded 4.807 days for this pair.
    """
    data, _ = replay("head_pin_unreleased")
    out = _select(data)

    log = dict(_log(data))
    head_at = _log(data)[0][1]
    expected = (head_at - log[out["run_commit"]]) / 86400.0
    assert out["lag_days"] == pytest.approx(expected)
    assert round(out["lag_days"], 3) == W04_LAG_DAYS


@pytest.mark.t0
def test_T_U_pin_04(replay):
    """T-U-pin-04 (FR-02.3): a one-bump-off pair is not a match, ever.

    The fixture is the untagged window `e297b52ec9d8` with exactly one release
    in its tag map, `firtool-1.159.0`, whose pin is the next window back. The
    two pins differ, so the answer is a refusal: no tolerance, no nearest
    match, no version-string comparison. C-01 is why: one bump off fails the
    build at target 2 of 1030 and cmake's configure passes anyway.
    """
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
    """T-U-pin-05 (FR-02.5): an empty tag list refuses and walks nothing.

    `03-LLD.md` §3.4 names one reason, `no_match`; this is the case the shared
    `corpus._read_tags` already separates, so it is raised as `no_tags` with
    the refspec named, and the walk never starts: exactly one git call is
    made, which is `for-each-ref` itself. The search is not widened, and no
    other refspec is tried.
    """
    data, git = replay("no_tags")
    with pytest.raises(pin_select.PinSelectError) as caught:
        _select(data)
    assert caught.value.reason == "no_tags"
    assert "refs/tags/firtool-*" in str(caught.value)
    assert git.calls == 1 and git.argv[0][0] == "for-each-ref"


@pytest.mark.t0
def test_T_U_pin_06(replay):
    """T-U-pin-06 (FR-02.6): the newest by tag date wins and all are recorded.

    `6279700538` is a real three-release pin. `tags_sharing_pin` is ordered
    newest first, every entry's own recorded `ls-tree` gives the chosen pin,
    and `pin_tag` is the head of that list. The order is by the tag's creation
    date, which the fixture records in seconds beside each name.
    """
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
    """T-U-pin-07 (FR-02.4): current_window_has_release is set on every run.

    It is a `bool` in all three shapes, including the one where it is false,
    which is what makes a run inside a lag window visibly different from a run
    at head. `head_pin_released` reads the same history from `eade0de61bc5`,
    the commit the unreleased shape walks back to, so the two differ in the
    ref and in nothing else.
    """
    data, _ = replay(fixture)
    out = _select(data)
    assert out["current_window_has_release"] is expected
    assert (out["lag_commits"] == 0) is expected
    if expected:
        assert out["run_commit"] == data["ref"]
        assert out["lag_days"] == 0.0


@pytest.mark.t0
def test_T_U_pin_09(replay):
    """T-U-pin-09 (FR-02.1, FR-02.4): every window released, so the walk stops.

    Two adjacent released windows, `44a65223cc4b` (`firtool-1.156.0`) and
    `f1ba92abeffc` (`firtool-1.155.0`): the excerpt carries both pins and both
    have a release, so the first commit examined is the one returned and the
    lag is zero. It is the shape ADR-D-10 says the loop would have if CIRCT
    tagged every bump, and the selector must not walk past the ref in it.
    """
    data, git = replay("all_windows_released")
    out = _select(data)

    assert out["run_commit"] == data["ref"]
    assert out["lag_commits"] == 0 and out["lag_days"] == 0.0
    assert out["tags_sharing_pin"] == ["firtool-1.156.0"]
    assert len(set(_tag_pins(data).values())) == 2
    assert len(_log(data)) == 33                # both windows are in the excerpt


@pytest.mark.t0
def test_T_U_pin_10(replay):
    """T-U-pin-10 (FR-19.1, FR-19.4): the decorator, the argv and the docstring.

    Three static facts, asserted where a plain call cannot reach them.
    `_chia_options` is `03-LLD.md` §3.2's A2 row: head placement, which is no
    resource at all, and `max_retries=0`. The git argument vectors are
    §4.11.1's table rows, each one element per argument with no shell. The
    docstring carries §3.1's three named paragraphs in order.
    """
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


# --------------------------------------------------------------------------
# Tier 1: the live clone.
# --------------------------------------------------------------------------

def _clone() -> str:
    """The first candidate path that is a clone with an `origin/main`, or "".

    `03-LLD.md` §13.1's `--clone` default is `~/.cache/circt`; this host's
    blobless clone is `~/.cache/chia-pin-smoke/circt`, which is where W-04 ran
    the selector by hand.
    """
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
    """T-U-pin-08, and T-U-pin-02's criterion with it (FR-02.1 to FR-02.4).

    The one tier-1 test: the selector against the live blobless clone at
    `origin/main`. Three things are asserted mechanically and hold whatever
    `main` has done since W-04: the chosen commit's `llvm` gitlink equals the
    named tag's, read back by two fresh `ls-tree` calls; `lag_commits` equals
    `git rev-list --first-parent --count <chosen>..origin/main`, which is
    T-U-pin-02's own criterion; and `lag_days` is the two commit dates apart.
    W-04's pair is asserted on top of those only while `main` still ends at
    the commit W-04 measured, and the current pair is printed either way.
    """
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
