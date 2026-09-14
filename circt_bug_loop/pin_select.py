"""A2, feature F-02: choose the release-pinned `main` commit the loop runs at.

`03-LLD.md` §3.4 is normative for the callable, §4.11.1's table for the git
commands and `01-FRD.md` F-02 for the behaviour. ADR-D-10 is the decision this
module implements: CIRCT's `main` head usually pins an LLVM the release
tarballs do not carry (C-01 makes one bump off a hard build failure), so the
loop runs at the newest first-parent commit whose pin a `firtool-*` release
shares, and reports how far behind `main` that leaves it.

**What is reused and how.** `corpus.py` already walks the pins and reads the
tag map for A1, against the same blobless clone with the same commands, and
§4.11.1 lists those commands once for both modules. They are therefore
**imported** and not copied: `_Git`, `_read_tags` and `_walk_pins`. The leading
underscore is `corpus.py`'s own marker for "not part of A1's interface", which
these three are not; they are the shared git layer §4.11.1's table describes,
and a second copy of a pin walk is the one thing this module must not carry.

The one thing this module does that A1 does not is refuse: A1 pairs every seed
with its nearest release and records the distance (FR-01.7), while A2 takes an
exact pin or nothing at all (FR-02.3), because a one-bump-off pairing builds
nothing and cmake's configure step is not a safety net (C-01, PIN §5.5).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.corpus import (SUBMODULE, TAG_REFSPEC, CorpusError, _Git,
                                   _read_tags, _walk_pins)

#: FR-02.5's bound, in days: the selector examines 24 months of `main` and
#: **widens no further**, which is the requirement's own word. 730 days is two
#: years counted the way `analysis/pin_window.py`'s `--since` counts them, and
#: it is measured from the head commit's own date rather than from now, so the
#: window a run examines does not depend on the day the run happens.
WINDOW_DAYS = 730

__all__ = ["PinSelectError", "WINDOW_DAYS", "select_release_pinned_main"]


class PinSelectError(Exception):
    """Raised by select_release_pinned_main. Carries a stable reason.

    The two reasons are `no_tags`, when the clone holds no `firtool-*` release
    at all, and `no_match`, when it holds releases but no first-parent commit
    inside `WINDOW_DAYS` shares a pin with one (FR-02.5). Both stop the run:
    every probe, every gate question and every filing is taken against the
    commit this node chooses, so a run without one is meaningless
    (`02-HLD.md` §6, A2's row).

    `03-LLD.md` §3.4 names only `no_match`. `no_tags` is separated from it
    because the shared `corpus._read_tags` already distinguishes the two and
    because the operator's next action differs: an empty tag map is a clone
    that was never fetched with `--tags`, not a `main` that has drifted.
    """

    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(f"{reason}: {message}")


@ChiaFunction(max_retries=0)
def select_release_pinned_main(clone_path: str, timeout_seconds: int = 600,
                               *, ref: str = "HEAD") -> dict:
    """Return the newest first-parent main commit whose LLVM pin has a release.

    The walk is `ref` towards the past in first-parent order, and the first
    commit it meets whose `llvm` gitlink equals some `firtool-*` tag's `llvm`
    gitlink wins (FR-02.1). Equality is of full 40-character SHAs: no
    tolerance, no nearest match, no version string (FR-02.3). "Newest" is
    first-parent position and not commit date, which is the order the log
    already returns. Where several releases share the chosen pin the newest by
    tag date is the one named and every one is recorded (FR-02.6).

    *ref* defaults to `HEAD` and is `03-LLD.md` §4.11.1's own spelling; the
    caller passes `origin/main` when the clone is detached, as the head's
    blobless clone is while A1 holds it at `corpus_head_sha` (FR-01.11).

    Returns:
        {"run_commit": str, "pin_sha": str, "pin_tag": str,
         "tags_sharing_pin": list[str], "lag_commits": int, "lag_days": float,
         "current_window_has_release": bool, "resolved_utc": str}, where
        run_commit is FR-02.7's field, pin_sha is that commit's `llvm` gitlink,
        tags_sharing_pin is newest by tag date first and pin_tag is its head,
        lag_commits and lag_days are FR-02.2's pair measured from *ref*, and
        current_window_has_release is FR-02.4's boolean for *ref*'s own pin.
    Worker:
        head - it walks 24 months of main in the head's blobless clone, which
        no worker container mounts (K5). No CIRCT binary, no model.
    Raises:
        PinSelectError("no_tags") when the clone holds no `firtool-*` release,
            naming the refspec (FR-02.5);
        PinSelectError("no_match") when releases exist but no first-parent
            commit inside WINDOW_DAYS shares a pin with one, naming the last
            window examined and not widening the search (FR-02.5);
        subprocess.CalledProcessError or subprocess.TimeoutExpired when git
            itself fails, which is a broken clone and not a selection result.
    """
    git = _Git(clone_path, timeout_seconds)
    try:
        tags = _read_tags(git)
    except CorpusError as exc:                    # FR-01.8's reason, A2's words
        raise PinSelectError(
            "no_tags",
            f"the clone at {clone_path!r} holds no {TAG_REFSPEC} tag, so no "
            f"pin can have a release: fetch the clone with --tags. ({exc})"
        ) from exc

    pin_tags: dict[str, list[dict]] = {}
    for tag in tags:
        pin_tags.setdefault(tag["llvm"], []).append(tag)

    commits = _walk_pins(git, ref)
    if not commits:
        raise PinSelectError(
            "no_match",
            f"git log --first-parent {ref} in {clone_path!r} returned no "
            "commit at all, so there is no window to examine.")

    head = commits[0]
    bound = head["date"] - timedelta(days=WINDOW_DAYS)
    chosen, last = None, head
    for commit in commits:
        if commit["date"] < bound:
            break                                 # FR-02.5: never widen
        last = commit
        if commit["llvm"] in pin_tags:
            chosen = commit
            break

    if chosen is None:
        raise PinSelectError(
            "no_match",
            f"no first-parent commit of {ref} within {WINDOW_DAYS} days of "
            f"{head['date'].isoformat()} shares its {SUBMODULE} pin with a "
            f"{TAG_REFSPEC} release. The last window examined was pin "
            f"{last['llvm']} at {last['sha']} ({last['date'].isoformat()}), "
            f"{len(pin_tags)} distinct release pins were known, and the search "
            "was not widened past the window.")

    sharing = sorted(pin_tags[chosen["llvm"]], key=lambda tag: tag["date"],
                     reverse=True)
    lag_commits = int(git("rev-list", "--first-parent", "--count",
                          f"{chosen['sha']}..{ref}").strip())
    return {
        "run_commit": chosen["sha"],
        "pin_sha": chosen["llvm"],
        "pin_tag": sharing[0]["tag"],
        "tags_sharing_pin": [tag["tag"] for tag in sharing],
        "lag_commits": lag_commits,
        "lag_days": (head["date"] - chosen["date"]).total_seconds() / 86400.0,
        "current_window_has_release": head["llvm"] in pin_tags,
        "resolved_utc": datetime.now(timezone.utc).isoformat(),
    }
