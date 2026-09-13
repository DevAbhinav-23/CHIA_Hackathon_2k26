#!/usr/bin/env python3
"""
pin_window.py -- Measure, empirically, whether a CIRCT firtool release tarball's
prebuilt LLVM/MLIR can serve as the SDK for arbitrary historical CIRCT commits.

Question: for a historical CIRCT bug-fix commit, does a firtool release tag exist
whose `llvm` submodule pin EXACTLY matches the pin at the bug's parent commit?
If not, how far off (LLVM bumps, days)?

Usage:
    git clone --filter=blob:none https://github.com/llvm/circt circt
    python3 pin_window.py /abs/path/to/circt [--since YYYY-MM-DD]

Only local git plumbing is used (ls-tree / log / rev-list); no network, no
per-commit subprocess storm (two full-history log passes + one ls-tree per tag).
"""
import subprocess, sys, json, statistics, re
from datetime import datetime, timezone

REPO = sys.argv[1] if len(sys.argv) > 1 else "circt"
SINCE = "2024-09-11"
for i, a in enumerate(sys.argv):
    if a == "--since":
        SINCE = sys.argv[i + 1]

SUBMODULE = "llvm"  # from .gitmodules: [submodule "llvm"] path = llvm


def git(*args):
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True,
                          text=True, check=True).stdout


def ts(unix):
    return datetime.fromtimestamp(int(unix), tz=timezone.utc)


# ---------------------------------------------------------------- 1. tags
tags = []
for line in git("for-each-ref", "--format=%(refname:short)\t%(creatordate:unix)",
                "--sort=creatordate", "refs/tags/firtool-*").splitlines():
    name, date = line.split("\t")
    out = git("ls-tree", name, SUBMODULE).strip()
    if not out:
        continue
    llvm = out.split()[2]
    tags.append({"tag": name, "date": ts(date), "llvm": llvm})

# ---------------------------------------------------- 2. first-parent history
# One pass: ordered first-parent commits (newest -> oldest) with subject+date.
commits = []
for line in git("log", "--first-parent", "--format=%H\t%ct\t%s", "HEAD").splitlines():
    h, t, s = line.split("\t", 2)
    commits.append({"sha": h, "date": ts(t), "subject": s})

# One pass: every first-parent commit that CHANGED the llvm submodule, with the
# old and new gitlink sha (from `--raw`, mode 160000).
bumps = {}  # sha -> (old_llvm, new_llvm)
cur = None
for line in git("log", "--first-parent", "--raw", "--no-abbrev",
                "--format=COMMIT %H", "HEAD", "--", SUBMODULE).splitlines():
    if line.startswith("COMMIT "):
        cur = line.split()[1]
    elif line.startswith(":160000"):
        parts = line.replace("\t", " ").split()
        bumps[cur] = (parts[2], parts[3])

# Walk newest -> oldest, carrying the pin.  The pin *at* commit C is what
# `git ls-tree C llvm` would return.
head_llvm = git("ls-tree", "HEAD", SUBMODULE).split()[2]
pin = head_llvm
for c in commits:
    c["llvm"] = pin                      # pin AT this commit
    if c["sha"] in bumps:
        old, new = bumps[c["sha"]]
        assert new == pin, f"pin walk desync at {c['sha']}"
        pin = old                        # pin at this commit's first parent
    c["parent_llvm"] = pin               # pin at C^1  == the bug state

# ------------------------------------------------------------- 3. pin windows
# Maximal contiguous first-parent ranges sharing one llvm pin.  Numbered from
# oldest (0) to newest, so |window_id difference| == number of LLVM bumps apart.
windows = []
for c in reversed(commits):              # oldest -> newest
    if windows and windows[-1]["llvm"] == c["llvm"]:
        w = windows[-1]
        w["n"] += 1
        w["end"] = c["date"]
        w["end_sha"] = c["sha"]
    else:
        windows.append({"llvm": c["llvm"], "n": 1, "start": c["date"],
                        "end": c["date"], "start_sha": c["sha"],
                        "end_sha": c["sha"]})
for i, w in enumerate(windows):
    w["id"] = i
    w["days"] = (w["end"] - w["start"]).total_seconds() / 86400.0
    w["tags"] = [t["tag"] for t in tags if t["llvm"] == w["llvm"]]

pin_to_window = {}
for w in windows:
    pin_to_window.setdefault(w["llvm"], w["id"])   # first (oldest) match
win_by_id = {w["id"]: w for w in windows}
tagged_pins = {t["llvm"] for t in tags}

# ------------------------------------------------- 4. bug-fix candidate mining
# One `--name-status` pass over the whole first-parent history; parsed in-process.
SUBJ = re.compile(r"\b(fix|fixes|fixed|bug|crash|assert|assertion|segfault|"
                  r"regression|ice|infinite loop|null|uaf|use-after-free)\b", re.I)
TESTDIR = ("test/", "integration_test/")
SRCDIR = ("lib/", "include/")

files_by_sha = {}
cur = None
raw = git("log", "--first-parent", "--name-status", "--format=COMMIT %H", "HEAD")
for line in raw.splitlines():
    if line.startswith("COMMIT "):
        cur = line.split()[1]
        files_by_sha[cur] = []
    elif line and line[0] in "AMDRTC" and "\t" in line:
        parts = line.split("\t")
        status = parts[0]
        path = parts[-1]                 # for R/C, the destination path
        files_by_sha[cur].append((status, path))

by_sha = {c["sha"]: c for c in commits}
since_dt = datetime.fromisoformat(SINCE).replace(tzinfo=timezone.utc)

cands_unfiltered, cands = [], []
for c in commits:
    if c["date"] < since_dt:
        continue
    fl = files_by_sha.get(c["sha"], [])
    if not fl:
        continue
    src = [p for st, p in fl if p.startswith(SRCDIR)]
    tst = [p for st, p in fl if p.startswith(TESTDIR) and st in ("A", "M", "R", "C")]
    if not (1 <= len(src) <= 2 and len(tst) >= 1):
        continue
    rec = dict(c)
    rec["src"], rec["test"] = src, tst
    cands_unfiltered.append(rec)
    if SUBJ.search(c["subject"]):
        cands.append(rec)


def classify(rec):
    """Exact prebuilt-LLVM match for the BUG state (parent commit's pin)?"""
    p = rec["parent_llvm"]
    exact = p in tagged_pins
    wid = pin_to_window.get(p)
    if exact:
        matching = [t for t in tags if t["llvm"] == p]
        matching.sort(key=lambda t: t["date"])
        return {"exact": True, "bumps": 0, "days": 0.0,
                "tag": matching[0]["tag"], "window": wid}
    # nearest tag by |window id| distance, tie-broken by |days|
    best = None
    for t in tags:
        twid = pin_to_window.get(t["llvm"])
        if twid is None:
            continue
        d = abs(twid - wid)
        dd = abs((t["date"] - rec["date"]).total_seconds() / 86400.0)
        if best is None or (d, dd) < (best[0], best[1]):
            best = (d, dd, t["tag"])
    return {"exact": False, "bumps": best[0], "days": round(best[1], 1),
            "tag": best[2], "window": wid}


for rec in cands_unfiltered:
    rec["match"] = classify(rec)

# --------------------------------------------------------------- 5. cadence
recent_w = [w for w in windows if w["end"] >= since_dt]
bump_dates = sorted(w["start"] for w in recent_w)
bump_gaps = [(b - a).total_seconds() / 86400.0
             for a, b in zip(bump_dates, bump_dates[1:])]
tag_dates = sorted(t["date"] for t in tags if t["date"] >= since_dt)
tag_gaps = [(b - a).total_seconds() / 86400.0
            for a, b in zip(tag_dates, tag_dates[1:])]

# ---------------------------------------------------------------- 6. report
def pct(n, d):
    return f"{100.0*n/d:.1f}%" if d else "n/a"


print(f"# CIRCT pin-window analysis  (window: {SINCE} .. {commits[0]['date'].date()})")
print(f"repo HEAD: {commits[0]['sha']}  {commits[0]['date'].isoformat()}")
print(f"submodule path: {SUBMODULE}  (url llvm/llvm-project)")
print()
print(f"firtool tags total: {len(tags)}; in window: {len(tag_dates)}")
print(f"first-parent commits in window: "
      f"{len([c for c in commits if c['date'] >= since_dt])}")
print(f"pin windows total: {len(windows)}; touching window: {len(recent_w)}")
print()
wl = [w["n"] for w in recent_w]
wd = [w["days"] for w in recent_w]
print(f"window length (commits): min {min(wl)} median {statistics.median(wl):.0f} "
      f"mean {statistics.mean(wl):.1f} max {max(wl)}")
print(f"window length (days):    min {min(wd):.2f} median {statistics.median(wd):.2f} "
      f"mean {statistics.mean(wd):.2f} max {max(wd):.2f}")
tagged_w = [w for w in recent_w if w["tags"]]
print(f"windows with >=1 firtool tag sharing their LLVM pin: "
      f"{len(tagged_w)}/{len(recent_w)} ({pct(len(tagged_w), len(recent_w))})")
print(f"commits inside a tagged window: "
      f"{sum(w['n'] for w in tagged_w)}/{sum(w['n'] for w in recent_w)} "
      f"({pct(sum(w['n'] for w in tagged_w), sum(w['n'] for w in recent_w))})")
print()
print(f"LLVM bump cadence  (n={len(bump_gaps)}): median {statistics.median(bump_gaps):.2f} d, "
      f"mean {statistics.mean(bump_gaps):.2f} d")
print(f"firtool release cadence (n={len(tag_gaps)}): median {statistics.median(tag_gaps):.1f} d, "
      f"mean {statistics.mean(tag_gaps):.1f} d")
print()
for label,group in (("UNFILTERED (shape only)", cands_unfiltered),
                 ("FILTERED (shape + bug-ish subject)", cands)):
    n = len(group)
    ex = [r for r in group if r["match"]["exact"]]
    b1 = [r for r in group if not r["match"]["exact"] and r["match"]["bumps"] <= 1]
    bm = [r for r in group if not r["match"]["exact"] and r["match"]["bumps"] > 1]
    print(f"## {label}: {n} candidates")
    print(f"   exact prebuilt-LLVM match at parent: {len(ex)} ({pct(len(ex), n)})")
    print(f"   <=1 LLVM bump away:                  {len(b1)} ({pct(len(b1), n)})")
    print(f"   >1 LLVM bump away:                   {len(bm)} ({pct(len(bm), n)})")
    if bm:
        print(f"   bumps-away distribution (non-exact): "
              f"median {statistics.median([r['match']['bumps'] for r in group if not r['match']['exact']])}, "
              f"max {max(r['match']['bumps'] for r in group if not r['match']['exact'])}")
    print()

print("## exact-match candidates (newest first)")
print("| date | commit | firtool tag (exact LLVM) | src files | test files | subject |")
print("|---|---|---|---|---|---|")
for r in [x for x in cands_unfiltered if x["match"]["exact"]]:
    print(f"| {r['date'].date()} | `{r['sha'][:12]}` | {r['match']['tag']} | "
          f"{'; '.join(r['src'])} | {'; '.join(r['test'][:2])} | "
          f"{r['subject'][:70].replace('|','/')} |")

json.dump({"windows": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                        for k, v in w.items()} for w in recent_w],
           "candidates": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                           for k, v in r.items()} for r in cands_unfiltered],
           "tags": [{k: (v.isoformat() if isinstance(v, datetime) else v)
                     for k, v in t.items()} for t in tags]},
          open("pin_window_raw.json", "w"), indent=1)
print("\n(raw data -> pin_window_raw.json)")
