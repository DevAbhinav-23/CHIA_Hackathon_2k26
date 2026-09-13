#!/usr/bin/env python3
"""M4 (A-12, red-team WOUND 3): symbol-level contamination rate for the 187 seeds.

File-level contamination (the red team's 86.1% at 730 days) asks "was this file touched
again?".  This asks the narrower question FR-15 actually needs: "was a FUNCTION this seed
touched touched again after the seed?".

One `git log --first-parent -p` over the union of the seeds' source files supplies both
the seeds' own hunks and every later hunk.  Two symbol extractors are reported:
  ctx   -- the identifier in the `@@ ... @@ <context>` hunk header (git's funcname), precise
  crude -- every `\\b(\\w+)\\s*\\(` on a +/- line, minus C/C++ keywords (the red team's rule)

Writes raw/m4-per-seed.csv and raw/m4-summary.txt.
"""
import json, re, subprocess, os, sys, csv, collections, time

ROOT = "/home/adi/Projects/chia-hackathon"
RAW = os.path.join(ROOT, "analysis/measurements/raw")
CLONE = os.path.expanduser("~/.cache/chia-pin-smoke/circt")
SUBJ = re.compile(r"\b(fix|fixes|fixed|bug|crash|assert|assertion|segfault|"
                  r"regression|ice|infinite loop|null|uaf|use-after-free)\b", re.I)

KW = set("""if else for while switch case return sizeof alignof new delete throw catch try
do goto break continue static_cast dynamic_cast const_cast reinterpret_cast typeid
decltype noexcept and or not xor bitand bitor compl defined assert static_assert
auto void bool char int long short float double unsigned signed const constexpr
template typename class struct union enum namespace using public private protected
virtual override final explicit inline friend operator this nullptr true false""".split())

CALL = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
CTX = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@\s*(.*)$")

def ctx_symbol(ctx):
    """Last identifier that precedes a '(' in git's funcname context, else the last identifier."""
    if not ctx.strip():
        return None
    names = [m.group(1) for m in CALL.finditer(ctx) if m.group(1) not in KW]
    if names:
        return names[-1]
    ids = re.findall(r"\b([A-Za-z_]\w*)\b", ctx)
    ids = [i for i in ids if i not in KW]
    return ids[-1] if ids else None

def main():
    cand = json.load(open(os.path.join(ROOT, "analysis/pin_window_raw.json")))["candidates"]
    seeds = [c for c in cand if SUBJ.search(c["subject"])]
    assert len(seeds) == 187
    files = sorted({f for s in seeds for f in s["src"]})
    since = min(s["date"] for s in seeds)
    head = subprocess.run(["git", "-C", CLONE, "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()

    t0 = time.time()
    cmd = ["git", "-C", CLONE, "log", "--first-parent", "-p", "--unified=0",
           "--no-renames", "--format=__C__ %H %cI", "--since", since, "--"] + files
    print("RUN: " + " ".join(cmd[:12]) + f" ... ({len(files)} paths)", file=sys.stderr)
    out = subprocess.run(cmd, capture_output=True).stdout.decode("utf-8", "replace")
    print(f"git log -p: {time.time()-t0:.1f}s, {len(out)} bytes", file=sys.stderr)
    open(os.path.join(RAW, "m4-gitlog.txt"), "w").write(out)

    # commit -> {file -> (ctx_syms, crude_syms)}
    commits = {}          # sha -> dict(date=..., files={path: [ctx set, crude set]})
    order = []
    sha = None; cur_file = None
    for line in out.splitlines():
        if line.startswith("__C__ "):
            _, sha, date = line.split(None, 2)
            commits[sha] = {"date": date, "files": {}}
            order.append(sha); cur_file = None
            continue
        if sha is None:
            continue
        if line.startswith("+++ b/"):
            cur_file = line[6:].strip()
            if cur_file == "ev/null":
                cur_file = None
            continue
        if line.startswith("--- a/") and cur_file is None:
            pass
        if cur_file is None:
            continue
        e = commits[sha]["files"].setdefault(cur_file, [set(), set()])
        m = CTX.match(line)
        if m:
            s = ctx_symbol(m.group(1))
            if s:
                e[0].add(s)
            continue
        if line[:1] in "+-" and not line.startswith(("+++", "---")):
            for mm in CALL.finditer(line[1:]):
                n = mm.group(1)
                if n not in KW:
                    e[1].add(n)

    rows = []
    n_file_hit = n_ctx_hit = n_crude_hit = 0
    n_file_hit_730 = n_ctx_hit_730 = 0
    no_syms = 0
    for s in seeds:
        ssha = s["sha"]; sdate = s["date"]
        sfiles = set(s["src"])
        rec = commits.get(ssha, {"files": {}})
        sctx = set(); scrude = set()
        for f, (a, b) in rec["files"].items():
            if f in sfiles:
                sctx |= a; scrude |= b
        later = [(c, commits[c]) for c in commits
                 if commits[c]["date"] > sdate and set(commits[c]["files"]) & sfiles]
        lctx = set(); lcrude = set(); lctx730 = set()
        import datetime
        sd = datetime.datetime.fromisoformat(sdate)
        for c, r in later:
            cd = datetime.datetime.fromisoformat(r["date"])
            for f, (a, b) in r["files"].items():
                if f in sfiles:
                    lctx |= a; lcrude |= b
                    if (cd - sd).days <= 730:
                        lctx730 |= a
        file_hit = bool(later)
        file_hit_730 = any((datetime.datetime.fromisoformat(r["date"]) - sd).days <= 730
                           for _, r in later)
        ctx_hit = bool(sctx & lctx)
        crude_hit = bool(scrude & lcrude)
        ctx_hit_730 = bool(sctx & lctx730)
        if not sctx:
            no_syms += 1
        n_file_hit += file_hit; n_ctx_hit += ctx_hit; n_crude_hit += crude_hit
        n_file_hit_730 += file_hit_730; n_ctx_hit_730 += ctx_hit_730
        rows.append(dict(sha=ssha[:12], date=sdate[:10], subject=s["subject"][:90],
                         src_files=";".join(sorted(sfiles)),
                         n_later_commits=len(later),
                         seed_ctx_syms=len(sctx), seed_crude_syms=len(scrude),
                         later_ctx_syms=len(lctx),
                         file_hit=int(file_hit), ctx_hit=int(ctx_hit),
                         crude_hit=int(crude_hit), ctx_hit_730=int(ctx_hit_730),
                         overlap_ctx=";".join(sorted(sctx & lctx))[:300]))

    with open(os.path.join(RAW, "m4-per-seed.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    n = len(seeds)
    rep = [
        f"M4 symbol-level contamination, {n} seeds, clone HEAD {head}",
        f"  distinct seed source files                 {len(files)}",
        f"  first-parent commits parsed (since {since[:10]})  {len(commits)}",
        f"  seeds whose own hunks yielded no ctx symbol {no_syms}",
        "",
        "Horizon: seed date -> clone HEAD (2026-09-11)",
        f"  FILE-level contaminated  (>=1 later first-parent commit touches a seed source file)   {n_file_hit:>4}/{n}  {100*n_file_hit/n:5.1f}%",
        f"  SYMBOL-level, ctx rule   (>=1 later commit touches a function the seed's hunks named) {n_ctx_hit:>4}/{n}  {100*n_ctx_hit/n:5.1f}%",
        f"  SYMBOL-level, crude rule (red team's ^[+-].*\\b(\\w+)\\s*\\( rule, keywords removed)     {n_crude_hit:>4}/{n}  {100*n_crude_hit/n:5.1f}%",
        "",
        "Horizon: 730 days after the seed (comparable to the red team's 86.1%)",
        f"  FILE-level contaminated   {n_file_hit_730:>4}/{n}  {100*n_file_hit_730/n:5.1f}%",
        f"  SYMBOL-level, ctx rule    {n_ctx_hit_730:>4}/{n}  {100*n_ctx_hit_730/n:5.1f}%",
    ]
    out = "\n".join(rep)
    open(os.path.join(RAW, "m4-summary.txt"), "w").write(out + "\n")
    print(out)

main()
