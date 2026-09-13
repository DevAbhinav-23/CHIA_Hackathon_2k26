#!/usr/bin/env python3
"""W-09 candidate ranking (04-Test-Plan.md 5.1, Source A).

Reads the committed 187-seed corpus, keeps the seeds whose subject names a
crash, an assertion, a segfault, an `UNREACHABLE`, a verifier failure or a
null/invalid-access fix, and prints them newest first with the RUN: line of each
test file the fix touched, read at the fix commit.  The tool and the line's
shape come from the flow's own `corpus.py`, so a line this script calls usable
is a line `w09_runner.py` will run identically.

usage: w09_select.py --clone <blobless clone or worktree> [--tag firtool-1.143.0]
                     [--tool circt-opt] [--ext .mlir] [--exact] [--limit N]
                     [--exclude <sha> ...] [--json <path>]
"""
import argparse, json, os, re, subprocess, sys

from w09_runner import REPO, _load_corpus

#: 04-Test-Plan.md 5.1's `crash|assert|segfault|verifier`, widened by W-09's own
#: brief to `UNREACHABLE` and to the null / invalid-access fixes, which is still
#: a subset of PIN 2's corpus filter (`_SUBJECT_RE` in corpus.py).
SUBJECT_RE = re.compile(
    r"\b(crash(?:es|ed|ing)?|assert(?:ion)?s?|segfault|unreachable|verifier|"
    r"null|nullptr|invalid[ -]access|use-after-free|uaf|out-of-bounds|"
    r"out of bounds|dereference)\b", re.I)

RUN_RE = re.compile(r"^[/;#*!\s]*RUN:\s*(.*(?:\\\n.*)*)$", re.M)


def first_run_line(clone, sha, path):
    """The test file's first RUN: line at *sha*, continuations joined."""
    try:
        blob = subprocess.run(["git", "-C", clone, "show", f"{sha}:{path}"],
                              capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    match = RUN_RE.search(blob)
    return match.group(1).strip() if match else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(
        REPO, "circt_bug_loop/tests/fixtures/corpus/filtered_187.json"))
    ap.add_argument("--clone", required=True)
    ap.add_argument("--tag")
    ap.add_argument("--tool", default="circt-opt")
    ap.add_argument("--ext", default=".mlir")
    ap.add_argument("--exact", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--exclude", nargs="*", default=[])
    ap.add_argument("--json")
    a = ap.parse_args()
    corpus = _load_corpus(REPO)

    rows = []
    for seed in json.load(open(a.corpus))["candidates"]:
        if not SUBJECT_RE.search(seed["subject"]):
            continue
        if any(seed["sha"].startswith(x) for x in a.exclude):
            continue
        if a.tag and seed["tag"] != a.tag:
            continue
        if a.exact and not seed["exact"]:
            continue
        for path in seed["test"]:
            if a.ext and not path.endswith(a.ext):
                continue
            line = first_run_line(a.clone, seed["sha"], path)
            if not line:
                continue
            tool, argv, _, shape, _, notes = corpus.normalise_run_line(line)
            if a.tool and tool != a.tool:
                continue
            if shape != "plain":
                continue
            kept, stripped = corpus.strip_probe_only_options(argv)
            rows.append(dict(sha=seed["sha"], date=seed["date"][:10],
                             tag=seed["tag"], exact=seed["exact"],
                             subject=seed["subject"], test=path, run_line=line,
                             tool=tool, argv=kept, stripped=stripped,
                             substitutions=notes["substitutions"]))
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows = rows[:a.limit]
    for r in rows:
        print(f'{r["sha"][:12]} {r["date"]} {r["tag"]:16s} '
              f'{"exact" if r["exact"] else "BUMP ":5s} {r["test"]}')
        print(f'    {r["subject"]}')
        print(f'    argv={r["argv"]}  stripped={r["stripped"]}')
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=1)
    print(f"-- {len(rows)} rows", file=sys.stderr)


if __name__ == "__main__":
    main()
