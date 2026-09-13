#!/usr/bin/env python3
"""W-09 attempt runner: normalise one lit RUN: line with the flow's OWN
`corpus.normalise_run_line` and `corpus.strip_probe_only_options` (03-LLD.md 3.3
steps 0-6 and 4.4), split the input on '// -----' when --split-input-file was
present, and run each piece under prlimit+timeout.

usage: w09_runner.py --input <mlir> --bin <build>/bin --sdk <sdk> --out <dir>
                     [--runline <file with the verbatim RUN: body>] [--tag label]
                     [--repo <repository root>]

With no --runline the first `RUN:` line of the input file is used, which is the
seed's own test's first RUN line (04-Test-Plan.md 5.1 step 3).

`corpus.py` imports `chia.base.ChiaFunction` at module scope and `chia` pulls in
Ray, neither of which is installed on the mining host.  A stub decorator is put
in `sys.modules` before the import, which is exactly what the flow's own
`tests/test_store.py:193-195` does for the same reason; `normalise_run_line` and
`strip_probe_only_options` are plain functions and neither is decorated, so the
stub changes nothing about what is being exercised.
"""
import argparse, json, os, re, subprocess, sys, time, types

#: Repository root, so the mined fixtures come out of the committed normaliser.
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", ".."))


def _load_corpus(repo):
    for name, mod in (("chia", types.ModuleType("chia")),
                      ("chia.base", types.ModuleType("chia.base")),
                      ("chia.base.ChiaFunction",
                       types.ModuleType("chia.base.ChiaFunction"))):
        sys.modules.setdefault(name, mod)
    sys.modules["chia.base.ChiaFunction"].ChiaFunction = \
        lambda *a, **k: (lambda fn: fn)
    if repo not in sys.path:
        sys.path.insert(0, repo)
    from circt_bug_loop import corpus
    return corpus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runline")
    ap.add_argument("--input", required=True)
    ap.add_argument("--bin", required=True)
    ap.add_argument("--sdk", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--tag", default="run")
    ap.add_argument("--repo", default=REPO)
    a = ap.parse_args()
    corpus = _load_corpus(a.repo)
    os.makedirs(a.out, exist_ok=True)
    text = open(a.input, errors="backslashreplace").read()
    if a.runline:
        line = open(a.runline).read().strip()
    else:
        m = re.search(r"^(?://|;|#)\s*RUN:\s*(.*)$", text, re.M)
        if not m:
            sys.exit(f"no RUN: line in {a.input}")
        line = m.group(1).strip()

    # The template pass, with no bindings: it fixes the tool, the shape and the
    # probe-only tokens, and its argv still carries lit's own `%s`.
    tool, argv, polarity, shape, env_line, notes = corpus.normalise_run_line(line)
    argv, stripped = corpus.strip_probe_only_options(argv)
    if shape != "plain":
        sys.exit(f"unsupported RUN: shape {shape!r} ({notes['unsupported_construct']})")
    notes = dict(notes, polarity=polarity, shape=shape, env=env_line,
                 stripped_probe_only=stripped,
                 survived_single_dash=[t for t in argv if t in
                                       ("-verify-diagnostics", "-split-input-file")])

    did_split = any(t.startswith("--split-input-file") for t in stripped)
    pieces = text.split("\n// -----\n") if did_split else [text]
    if did_split and len(pieces) == 1:
        pieces = text.split("// -----")

    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = (os.path.join(a.sdk, "lib") + ":" +
                              os.path.expanduser("~/.cache/chia-pin-smoke/shim"))
    env.update(env_line)
    results = []
    for n, piece in enumerate(pieces):
        pdir = os.path.join(a.out, f"{a.tag}-p{n:02d}")
        os.makedirs(pdir, exist_ok=True)
        ipath = os.path.join(pdir, "input" + os.path.splitext(a.input)[1])
        open(ipath, "w").write(piece)
        # The binding pass: `%s`, `%t` and `%S` resolved against THIS piece, by
        # the same committed function, so the substitution is textual and not
        # token-wise (a `%t.dir` stays one token).
        _, bound, _, _, _, _ = corpus.normalise_run_line(
            line, subs={"s": ipath, "t": os.path.join(pdir, "t"), "S": pdir})
        bound, _ = corpus.strip_probe_only_options(bound)
        full = [os.path.join(a.bin, tool)] + bound
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
