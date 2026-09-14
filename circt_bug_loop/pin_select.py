"""A2, feature F-02: choose the release-pinned `main` commit the loop runs at."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import CounterBlock
from circt_bug_loop.corpus import (SUBMODULE, TAG_REFSPEC, CorpusError, _Git,
                                   _read_tags, _walk_pins)

#: FR-02.5's bound, in days.
WINDOW_DAYS = 730

__all__ = ["PinSelectError", "WINDOW_DAYS", "select_release_pinned_main"]


class PinSelectError(Exception):
    """Raised by select_release_pinned_main."""

    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(f"{reason}: {message}")


@ChiaFunction(max_retries=0)
def select_release_pinned_main(clone_path: str, timeout_seconds: int = 600,
                               *, ref: str = "HEAD") -> dict:
    """Return the newest first-parent main commit whose LLVM pin has a release.

    Returns:
        {"run_commit": str, "pin_sha": str, "pin_tag": str, "tags_sharing_pin": list[str], "lag_commits": int, "lag_days": float, "current_window_has_release": bool, "resolved_utc": str, "counters": CounterBlock}, where run_commit is FR-02.7's field, pin_sha is that commit's `llvm` gitlink, tags_sharing_pin is newest by tag date first and pin_tag is its head, lag_commits and lag_days are FR-02.2's pair measured from *ref*, and current_window_has_release is FR-02.4's boolean for *ref*'s own pin, and the counters count the window's commits at stage "pin" (3.11).
    Worker:
        head - it walks 24 months of main in the head's blobless clone.
    Raises:
        PinSelectError("no_tags") when the clone holds no `firtool-*` release, naming the refspec (FR-02.5).
    """
    started_at = time.monotonic()
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
        # 3.11: every node of 3.2 returns exactly one of these.
        "counters": CounterBlock(stage="pin", started=len(commits), completed=1,
                                 failed=len(commits) - 1,
                                 seconds=time.monotonic() - started_at),
    }
