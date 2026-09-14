#!/usr/bin/env python3
"""Record the five `pin_select` fixtures from the blobless `llvm/circt` clone.

`04-Test-Plan.md` §13's rule for this directory: the fixtures are derived by
selecting rows from real git output and the derivation script is committed
beside them. Nothing here is hand-written. Each fixture is a replay of the
six git commands `03-LLD.md` §4.11.1's table gives `pin_select.py`, keyed by
the argument vector the module passes, so the tier-0 tests drive the real
`select_release_pinned_main` body against recorded bytes and no clone.

Usage:
    python3 make_fixtures.py [<clone>]        # default ~/.cache/chia-pin-smoke/circt

The clone must have `origin/main` and `refs/tags/firtool-*` fetched. Re-running
it against a moved `main` rewrites `head_pin_unreleased.json` and the numbers
the tests assert; that is deliberate, and the fixture records the `origin/main`
head it was taken at so a rewrite is visible in the diff.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

CLONE = os.path.expanduser(
    sys.argv[1] if len(sys.argv) > 1 else "~/.cache/chia-pin-smoke/circt")
HERE = os.path.dirname(os.path.abspath(__file__))
SUBMODULE = "llvm"
TAG_REFSPEC = "refs/tags/firtool-*"
TAG_FORMAT = "--format=%(refname:short)\t%(creatordate:unix)"
LOG_FORMAT = "--format=%H\t%ct\t%s"


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", CLONE, *args], capture_output=True,
                          text=True, check=True).stdout


def record(commands: dict, *args: str) -> str:
    """Run one git command and store its stdout under the argv the module uses."""
    out = git(*args)
    commands[" ".join(args)] = out
    return out


def build(name: str, ref: str, commits: int, tags: list[str], note: str) -> None:
    """Write one fixture: *commits* first-parent commits of *ref*, *tags* only."""
    commands: dict[str, str] = {}

    listing = git("for-each-ref", TAG_FORMAT, "--sort=creatordate", TAG_REFSPEC)
    kept = [line for line in listing.splitlines()
            if tags is None or line.split("\t")[0] in tags]
    commands[" ".join(("for-each-ref", TAG_FORMAT, "--sort=creatordate",
                       TAG_REFSPEC))] = "".join(line + "\n" for line in kept)
    for line in kept:
        record(commands, "ls-tree", line.split("\t")[0], SUBMODULE)

    log = git("log", "--first-parent", LOG_FORMAT, ref).splitlines()[:commits]
    commands[" ".join(("log", "--first-parent", LOG_FORMAT, ref))] = \
        "".join(line + "\n" for line in log)
    shas = {line.split("\t")[0] for line in log}

    raw = git("log", "--first-parent", "--raw", "--no-abbrev",
              "--format=COMMIT %H", ref, "--", SUBMODULE).splitlines()
    kept_raw, current = [], None
    for line in raw:
        if line.startswith("COMMIT "):
            current = line.split()[1]
        if current in shas:
            kept_raw.append(line)
    commands[" ".join(("log", "--first-parent", "--raw", "--no-abbrev",
                       "--format=COMMIT %H", ref, "--", SUBMODULE))] = \
        "".join(line + "\n" for line in kept_raw)

    record(commands, "ls-tree", ref, SUBMODULE)

    # The lag call, for whichever commit of the excerpt the selector will choose.
    pins = {line.split("\t")[0]: None for line in log}
    tag_pins = {commands[f"ls-tree {tag} {SUBMODULE}"].split()[2]
                for tag in (t.split("\t")[0] for t in kept)}
    pin = commands[f"ls-tree {ref} {SUBMODULE}"].split()[2]
    bumps = {}
    for i, line in enumerate(kept_raw):
        if line.startswith("COMMIT "):
            current = line.split()[1]
        elif line.startswith(":160000"):
            parts = line.replace("\t", " ").split()
            bumps[current] = (parts[2], parts[3])
    for sha in list(pins):
        pins[sha] = pin
        if sha in bumps:
            pin = bumps[sha][0]
    for sha, commit_pin in pins.items():
        if commit_pin in tag_pins:
            record(commands, "rev-list", "--first-parent", "--count",
                   f"{sha}..{ref}")
            break

    path = os.path.join(HERE, f"{name}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({
            "recorded_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "clone": "~/.cache/chia-pin-smoke/circt",
            "origin_main": git("rev-parse", "origin/main").strip(),
            "ref": ref,
            "note": note,
            "commands": commands,
        }, handle, indent=1, sort_keys=False)
        handle.write("\n")
    print(f"{name}.json: {len(commands)} commands, {len(log)} commits, "
          f"{len(kept)} tags")


W4_HEAD = "d6e1fc8eddd5dc296a3d326dc6b02beffba620b7"

build("head_pin_unreleased", "origin/main", 12, None,
      "The real 2026-09-14 state: origin/main's own pin e297b52ec9d8 has no "
      "firtool release, so the selector walks back eight first-parent commits "
      "to eade0de61bc5, whose pin 6279700538 three releases share. The full "
      "164-tag map is recorded; the first-parent log is cut at twelve commits, "
      "which is four past the match. This is the pair W-04 built the image from "
      "(analysis/measurements/2026-09-14-image-build.md §1).")

build("head_pin_released", "eade0de61bc5a0d2ba1b9da951b69efcab19f8ce", 8,
      ["firtool-1.157.0", "firtool-1.158.0", "firtool-1.159.0"],
      "The same history read from eade0de61bc5 instead: the ref's own pin has "
      "a release, so the selector stops at the ref and the lag is zero.")

build("all_windows_released", W4_HEAD, 33,
      ["firtool-1.155.0", "firtool-1.156.0"],
      "Two adjacent released pin windows, 44a65223cc4b (firtool-1.156.0) and "
      "f1ba92abeffc (firtool-1.155.0): every commit of the excerpt has a "
      "release, so the walk never leaves its first commit.")

build("no_tags", "origin/main", 12, [],
      "The same twelve commits with an empty for-each-ref, which is a clone "
      "holding no firtool release at all (FR-02.5's unit case).")

build("one_bump_off", "origin/main", 8, ["firtool-1.159.0"],
      "The eight commits of the untagged window e297b52ec9d8 with only "
      "firtool-1.159.0 in the tag map, whose pin 6279700538 is exactly one "
      "LLVM bump older: no commit of the excerpt matches, and a one-bump-off "
      "pair is not a match (FR-02.3).")
