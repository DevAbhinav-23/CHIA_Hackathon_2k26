#!/usr/bin/env python3
"""M1 (A-01 corpus reach, D-13, red-team experiment 1).

For each of the 187 subject-filtered seeds in analysis/pin_window_raw.json, fetch the
test file(s) the seed's commit touched, extract every lit RUN: line, and classify the
entry tool, the input language and the RUN-line shape features the red team named.

Writes:  raw/m1-per-runline.csv, raw/m1-per-seed.csv, raw/m1-summary.txt
"""
import json, re, subprocess, sys, os, collections, csv, time

ROOT = "/home/adi/Projects/chia-hackathon"
RAW = os.path.join(ROOT, "analysis/measurements/raw")
CLONE = os.path.expanduser("~/.cache/chia-pin-smoke/circt")

# analysis/pin_window.py:107-108, verbatim.
SUBJ = re.compile(r"\b(fix|fixes|fixed|bug|crash|assert|assertion|segfault|"
                  r"regression|ice|infinite loop|null|uaf|use-after-free)\b", re.I)

TOOLS = ["circt-opt", "firtool", "circt-verilog", "circt-translate", "arcilator",
         "circt-reduce", "circt-lec", "circt-bmc", "circt-test", "circt-synth",
         "circt-as", "circt-dis", "circt-lsp-server", "hlstool", "kanagawatool",
         "esi-tester", "om-linker", "firld", "circt-capi-.*", "handshake-runner",
         "ibistool", "circt-cocotb-driver.py", "circt-rtl-sim.py"]
TOOL_RX = re.compile(r"(?<![\w./-])(" + "|".join(TOOLS) + r")(?![\w-])")
PRIMARY = {"circt-opt", "firtool", "circt-verilog", "circt-translate", "arcilator"}

LANG = {".mlir": ".mlir", ".fir": ".fir", ".sv": ".sv", ".v": ".sv", ".svh": ".sv",
        ".vh": ".sv"}

def lang_of(path):
    ext = os.path.splitext(path)[1]
    return LANG.get(ext, "other:" + (ext or "(none)"))

def reducibility(lang):
    if lang == ".mlir":
        return "direct"          # circt-reduce parses MLIR (C-17)
    if lang == ".fir":
        return "lift-firtool"    # firtool --parse-only
    if lang == ".sv":
        return "lift-circt-verilog"  # circt-verilog --ir-moore
    return "textual-only"

def run_lines(text):
    """Yield logical RUN: lines, joining lit's backslash continuations."""
    out, cur = [], None
    for raw in text.splitlines():
        if cur is not None:
            cur += " " + raw.strip().lstrip("/;#*! ").strip()
            if not cur.endswith("\\"):
                out.append(cur); cur = None
            else:
                cur = cur[:-1].strip()
            continue
        m = re.search(r"RUN:\s*(.*)$", raw)
        if not m:
            continue
        body = m.group(1).strip()
        if body.endswith("\\"):
            cur = body[:-1].strip()
        else:
            out.append(body)
    if cur is not None:
        out.append(cur)
    return out

def entry_tool(line):
    """First CIRCT tool in the first pipeline segment; fall back to whole line."""
    head = line.split("|")[0]
    m = TOOL_RX.search(head)
    if m:
        return m.group(1)
    m = TOOL_RX.search(line)
    if m:
        return m.group(1) + " (downstream)"
    return "other"

def main():
    cand = json.load(open(os.path.join(ROOT, "analysis/pin_window_raw.json")))["candidates"]
    seeds = [c for c in cand if SUBJ.search(c["subject"])]
    assert len(seeds) == 187, len(seeds)

    # Batch every <sha>:<path> through one git cat-file so the blobless clone does
    # one lazy fetch pass instead of 280.
    specs, index = [], []
    for s in seeds:
        for p in s["test"]:
            specs.append(f"{s['sha']}:{p}")
            index.append((s["sha"], p))
    t0 = time.time()
    proc = subprocess.run(["git", "-C", CLONE, "cat-file", "--batch"],
                          input=("\n".join(specs) + "\n").encode(), capture_output=True)
    print(f"git cat-file --batch: {len(specs)} specs, {time.time()-t0:.1f}s, rc={proc.returncode}",
          file=sys.stderr)
    blob = {}
    buf = proc.stdout
    pos = 0
    for (sha, path) in index:
        nl = buf.index(b"\n", pos)
        hdr = buf[pos:nl].decode("utf-8", "replace")
        pos = nl + 1
        parts = hdr.split()
        if len(parts) == 3 and parts[1] == "blob":
            n = int(parts[2])
            blob[(sha, path)] = buf[pos:pos + n].decode("utf-8", "replace")
            pos += n + 1
        else:                                   # "missing" / "dangling"
            blob[(sha, path)] = None

    rl_rows, seed_rows = [], []
    tool_seeds = collections.defaultdict(set)
    lang_seeds = collections.defaultdict(set)
    red_seeds = collections.defaultdict(set)
    feat_counts = collections.Counter()
    feat_seeds = collections.defaultdict(set)
    n_rl = 0
    missing = []

    for s in seeds:
        sha = s["sha"]
        s_tools, s_langs, s_reds = set(), set(), set()
        n_lines_seed = 0
        for p in s["test"]:
            text = blob[(sha, p)]
            if text is None:
                missing.append((sha, p)); continue
            lang = lang_of(p)
            s_langs.add(lang)
            s_reds.add(reducibility(lang))
            for line in run_lines(text):
                n_rl += 1; n_lines_seed += 1
                tool = entry_tool(line)
                s_tools.add(tool)
                feats = {
                    "lead_not": bool(re.match(r"^(not|env\s+\S+=\S+\s+not)\b", line)),
                    "pipe": "|" in line,
                    "pct_t": "%t" in line,
                    "pct_S": "%S" in line,
                    "pct_brace": "%{" in line,
                    "split_file": "split-file" in line,
                    # not named by the red team, but decisive for F-09: a
                    # --split-input-file test is many probes in one file.
                    "split_input_file": "split-input-file" in line,
                    "verify_diagnostics": "verify-diagnostics" in line,
                    "shell_and": "&&" in line,
                    "redirect": ">" in line and "->" not in line.replace(">", "", 0),
                }
                for k, v in feats.items():
                    if v:
                        feat_counts[k] += 1; feat_seeds[k].add(sha)
                rl_rows.append(dict(sha=sha[:12], date=s["date"][:10], test_file=p,
                                    lang=lang, entry_tool=tool,
                                    reducibility=reducibility(lang),
                                    **{k: int(v) for k, v in feats.items()},
                                    run_line=line))
        for t in s_tools: tool_seeds[t].add(sha)
        for l in s_langs: lang_seeds[l].add(sha)
        for r in s_reds:  red_seeds[r].add(sha)
        seed_rows.append(dict(sha=sha[:12], date=s["date"][:10],
                              exact=int(s["match"]["exact"]),
                              subject=s["subject"],
                              src_files=";".join(s["src"]),
                              test_files=";".join(s["test"]),
                              n_run_lines=n_lines_seed,
                              entry_tools=";".join(sorted(s_tools)) or "(none)",
                              langs=";".join(sorted(s_langs)),
                              reducibility=";".join(sorted(s_reds))))

    os.makedirs(RAW, exist_ok=True)
    with open(os.path.join(RAW, "m1-per-runline.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rl_rows[0].keys())); w.writeheader(); w.writerows(rl_rows)
    with open(os.path.join(RAW, "m1-per-seed.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(seed_rows[0].keys())); w.writeheader(); w.writerows(seed_rows)

    def tbl(title, d, unit="seeds"):
        lines = [f"\n{title}", "-" * len(title)]
        for k, v in sorted(d.items(), key=lambda kv: -len(kv[1]) if isinstance(kv[1], set) else -kv[1]):
            n = len(v) if isinstance(v, set) else v
            lines.append(f"  {k:<34} {n:>5}  ({100*n/187:5.1f}% of 187 {unit})")
        return "\n".join(lines)

    rep = []
    rep.append(f"M1 seeds={len(seeds)}  test files={len(specs)}  RUN: lines={n_rl}  missing blobs={len(missing)}")
    rep.append(f"clone HEAD={subprocess.run(['git','-C',CLONE,'rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()}")
    rep.append(tbl("Seeds per entry tool (a seed may use several)", tool_seeds))
    rep.append(tbl("Seeds per input language (of the touched test files)", lang_seeds))
    rep.append(tbl("Seeds per circt-reduce reachability class", red_seeds))
    rep.append(tbl("RUN-line shape features, seeds with >=1 such line", feat_seeds))
    # D-13 cross-check: the ".sv region" by SOURCE bucket vs by test-file language.
    SVSRC = re.compile(r"(ImportVerilog|MooreToCore|Dialect/Moore|circt-verilog)")
    sv_src = {c["sha"][:12] for c in seeds if any(SVSRC.search(f) for f in c["src"])}
    sv_test = {x[:12] for x in lang_seeds[".sv"]}
    cv = {r["sha"] for r in rl_rows if r["entry_tool"] == "circt-verilog"}
    ctiv = {r["sha"] for r in rl_rows
            if r["entry_tool"] == "circt-translate" and "import-verilog" in r["run_line"]}
    rep.append("\nD-13 cross-check: which seeds need a slang-enabled build")
    rep.append(f"  seeds touching an ImportVerilog/Moore/MooreToCore source file        {len(sv_src):>4}")
    rep.append(f"  seeds touching a .sv test file                                       {len(sv_test):>4}")
    rep.append(f"  seeds with >=1 RUN line entering via circt-verilog                   {len(cv):>4}")
    rep.append(f"  seeds with >=1 RUN line entering via circt-translate --import-verilog {len(ctiv):>4}")
    rep.append(f"  union of the two slang entry points                                  {len(cv | ctiv):>4}")
    rep.append(f"  union of slang entry points with .sv-test seeds                      {len(cv | ctiv | sv_test):>4}")
    rep.append(f"  slang-entry seeds whose source files are NOT in the .sv region       {len((cv | ctiv) - sv_src):>4}")
    rep.append("\nRUN-line shape features, raw line counts (of %d lines)" % n_rl)
    for k, v in feat_counts.most_common():
        rep.append(f"  {k:<34} {v:>5}  ({100*v/n_rl:5.1f}%)")
    # Per-tool x per-language cross tab at RUN-line level
    ct = collections.Counter((r["entry_tool"], r["lang"]) for r in rl_rows)
    rep.append("\nRUN-line cross tab (entry tool x test-file language)")
    for (t, l), n in ct.most_common():
        rep.append(f"  {t:<26} {l:<12} {n:>5}")
    if missing:
        rep.append("\nMissing blobs (file not present at the seed commit):")
        for sha, p in missing: rep.append(f"  {sha[:12]} {p}")
    out = "\n".join(rep)
    open(os.path.join(RAW, "m1-summary.txt"), "w").write(out + "\n")
    print(out)

main()
