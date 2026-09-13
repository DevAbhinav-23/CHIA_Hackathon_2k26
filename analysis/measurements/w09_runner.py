#!/usr/bin/env python3
"""W-09 attempt runner: normalise one lit RUN: line (03-LLD.md 3.3 steps 0-6 and
4.4's strip_probe_only_options), split the input on '// -----' when
--split-input-file was present, and run each piece under prlimit+timeout.

usage: w09_runner.py --input <mlir> --bin <build>/bin --sdk <sdk> --out <dir>
                     [--runline <file with the verbatim RUN: body>] [--tag label]

With no --runline the first `RUN:` line of the input file is used, which is the
seed's own test's first RUN line (04-Test-Plan.md 5.1 step 3).
"""
import argparse, json, os, re, shlex, subprocess, sys, time

PROBE_ONLY = ("--verify-diagnostics", "-verify-diagnostics",
              "--split-input-file", "-split-input-file")


def normalise(line):
    notes = {}
    toks = shlex.split(line)
    polarity = "expect_zero"
    if toks and toks[0] == "not":
        toks = toks[1:]
        polarity = "expect_nonzero"
        if toks and toks[0] == "--crash":
            toks = toks[1:]
            notes["not_crash"] = True
    env = {}
    if toks and toks[0] == "env":
        toks = toks[1:]
        while toks and "=" in toks[0] and not toks[0].startswith("-"):
            k, v = toks[0].split("=", 1)
            env[k] = v
            toks = toks[1:]
    shape = "plain"
    if toks and toks[0] == "split-file":
        shape = "split_file"
    # step 4: drop from the first unquoted '|' onwards.  shlex already removed
    # quoting, so a bare '|' token is the unquoted pipe.
    if "|" in toks:
        i = toks.index("|")
        notes["dropped_tail"] = " ".join(toks[i:])
        toks = toks[:i]
    stripped = [t for t in toks if t in PROBE_ONLY or
                any(t.startswith(p + "=") for p in PROBE_ONLY)]
    toks = [t for t in toks if t not in stripped]
    notes["stripped_probe_only"] = stripped
    notes["polarity"] = polarity
    notes["shape"] = shape
    notes["env"] = env
    return toks[0], toks[1:], notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runline")
    ap.add_argument("--input", required=True)
    ap.add_argument("--bin", required=True)
    ap.add_argument("--sdk", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="run")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    text = open(a.input, errors="backslashreplace").read()
    if a.runline:
        line = open(a.runline).read().strip()
    else:
        m = re.search(r"^(?://|;|#)\s*RUN:\s*(.*)$", text, re.M)
        if not m:
            sys.exit(f"no RUN: line in {a.input}")
        line = m.group(1).strip()
    tool, argv, notes = normalise(line)

    did_split = any(t.startswith("--split-input-file") or t.startswith("-split-input-file")
                    for t in notes["stripped_probe_only"])
    pieces = text.split("\n// -----\n") if did_split else [text]
    if did_split and len(pieces) == 1:
        pieces = text.split("// -----")

    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = (os.path.join(a.sdk, "lib") + ":" +
                              os.path.expanduser("~/.cache/chia-pin-smoke/shim"))
    env.update(notes["env"])
    results = []
    for n, piece in enumerate(pieces):
        pdir = os.path.join(a.out, f"{a.tag}-p{n:02d}")
        os.makedirs(pdir, exist_ok=True)
        ipath = os.path.join(pdir, "input" + os.path.splitext(a.input)[1])
        open(ipath, "w").write(piece)
        full = [os.path.join(a.bin, tool)] + [ipath if t == "%s" else t for t in argv]
        # 03-LLD.md 4.1: the recorded argv is the tool's own; prlimit is a prefix
        # and is not part of it.  The 180 s wall bound is applied by the caller
        # rather than by timeout(1), whose own "dumped core" line would otherwise
        # land in the stderr a fixture records character for character.
        cmd = ["prlimit", "--as=8589934592", "--cpu=120:125"] + full
        t0 = time.time()
        try:
            p = subprocess.run(cmd, capture_output=True, env=env, timeout=180)
            rc, out, err = p.returncode, p.stdout, p.stderr
            limit_hit = None
        except subprocess.TimeoutExpired as e:
            rc, out, err = None, e.stdout or b"", e.stderr or b""
            limit_hit = "wall"
        wall = time.time() - t0
        p = type("R", (), dict(returncode=rc, stdout=out, stderr=err))
        open(os.path.join(pdir, "stderr.txt"), "wb").write(p.stderr)
        open(os.path.join(pdir, "stdout.txt"), "wb").write(p.stdout)
        json.dump(dict(argv=full, prlimit_prefix=cmd[:len(cmd) - len(full)],
                       rc=p.returncode, limit_hit=limit_hit,
                       wall_seconds=round(wall, 3), piece=n, npieces=len(pieces),
                       tool=tool, notes=notes, run_line=line),
                  open(os.path.join(pdir, "run.json"), "w"), indent=1)
        results.append(dict(piece=n, rc=p.returncode, wall=round(wall, 2),
                            dir=pdir, nbytes=len(piece)))
        print(f"  piece {n:2d}  rc={p.returncode:<4} {wall:6.2f}s  "
              f"{len(piece):6d}B  {pdir}")
    json.dump(dict(tool=tool, argv=argv, notes=notes, results=results),
              open(os.path.join(a.out, f"{a.tag}-summary.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
