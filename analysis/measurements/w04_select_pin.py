#!/usr/bin/env python3
"""LLD 3.4 / 4.3 selector, by hand: newest first-parent main commit whose
llvm gitlink equals a firtool-* tag's gitlink."""
import subprocess, sys
from datetime import datetime, timezone

REPO = sys.argv[1]
REF = sys.argv[2] if len(sys.argv) > 2 else "origin/main"

def git(*a):
    return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, check=True).stdout

def ts(u):
    return datetime.fromtimestamp(int(u), tz=timezone.utc)

# 1. tags and their pins
tags = []
for line in git("for-each-ref", "--format=%(refname:short)\t%(creatordate:unix)",
                "--sort=creatordate", "refs/tags/firtool-*").splitlines():
    name, date = line.split("\t")
    out = git("ls-tree", name, "llvm").strip()
    if not out:
        continue
    tags.append({"tag": name, "date": ts(date), "llvm": out.split()[2]})
pin_tags = {}
for t in tags:
    pin_tags.setdefault(t["llvm"], []).append(t)

# 2. first-parent history newest->oldest
commits = []
for line in git("log", "--first-parent", "--format=%H\t%ct\t%s", REF).splitlines():
    h, t, s = line.split("\t", 2)
    commits.append({"sha": h, "date": ts(t), "subject": s})

# 3. pin walk
bumps, cur = {}, None
for line in git("log", "--first-parent", "--raw", "--no-abbrev",
                "--format=COMMIT %H", REF, "--", "llvm").splitlines():
    if line.startswith("COMMIT "):
        cur = line.split()[1]
    elif line.startswith(":160000"):
        p = line.replace("\t", " ").split()
        bumps[cur] = (p[2], p[3])
pin = git("ls-tree", REF, "llvm").split()[2]
head = commits[0]
for c in commits:
    c["llvm"] = pin
    if c["sha"] in bumps:
        old, new = bumps[c["sha"]]
        assert new == pin, f"desync at {c['sha']}"
        pin = old

print(f"HEAD          {head['sha']}  {head['date'].isoformat()}  pin={head['llvm']}")
print(f"HEAD pin has release: {head['llvm'] in pin_tags}")
print()

# 4. newest commit whose pin has a release
chosen = None
for c in commits:
    if c["llvm"] in pin_tags:
        chosen = c
        break
if chosen is None:
    sys.exit("no_match")

ct = pin_tags[chosen["llvm"]]
ct_sorted = sorted(ct, key=lambda t: t["date"], reverse=True)
newest = ct_sorted[0]
lag_commits = int(git("rev-list", "--first-parent", "--count", f"{chosen['sha']}..{REF}").strip())
lag_days = (head["date"] - chosen["date"]).total_seconds() / 86400.0

print(f"CHOSEN commit {chosen['sha']}")
print(f"  date        {chosen['date'].isoformat()}")
print(f"  subject     {chosen['subject']}")
print(f"  llvm pin    {chosen['llvm']}")
print(f"  tags sharing pin (newest first): {[t['tag'] for t in ct_sorted]}")
print(f"  CIRCT_VER   {newest['tag']}   (tag date {newest['date'].isoformat()})")
print(f"  lag_commits {lag_commits}")
print(f"  lag_days    {lag_days:.3f}")
print()
print("verification, both ls-tree:")
print("  commit:", git("ls-tree", chosen["sha"], "llvm").strip())
print("  tag   :", git("ls-tree", newest["tag"], "llvm").strip())
print()
print("first 12 first-parent commits, pin and whether tagged:")
for c in commits[:12]:
    print(f"  {c['sha'][:12]} {c['date'].date()} pin={c['llvm'][:12]} tagged={c['llvm'] in pin_tags}")
