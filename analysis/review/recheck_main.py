#!/usr/bin/env python3
"""T2: re-run the 15 gated reduced reproducers at the build point and on CIRCT main.

Build point: the campaigns' image (docker, eade0de6). Main: the host build from
main_build.sh. Each run is a fresh process, 60 s / 4 GiB (run_bounded.py).
Classified with the loop's own parsers (probe_task, triage_task), so run with
~/.cache/chia-venv/bin/python. Read-only on loop.db; writes a JSON record.
"""
import json
import os
import shlex
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from circt_bug_loop.probe_task import (_extract_assertion, _normalise_function,  # noqa: E402
                                       _parse_frames, classify_build, generalise_types,
                                       verifier_detail)
from circt_bug_loop.triage_task import normalise_expr, normalise_site  # noqa: E402

ART = Path.home() / "bugloop-artefacts"
IMAGE = "chia-circt-assert:eade0de61bc5-u1000"
MAIN = Path.home() / ".cache/review-main-build"
MAIN_BIN = MAIN / "build/bin/circt-opt"
MAIN_ENV = {**os.environ, "LD_LIBRARY_PATH": f"{MAIN / 'sdk/lib'}:"
            f"{Path.home() / '.cache/chia-pin-smoke/shim'}"}
#: Host paths in main's traces, mapped to the image's so sites compare.
PREFIXES = {f"{MAIN}/src/": "/workspace/circt/", f"{MAIN}/sdk/": "/opt/circt-sdk/",
            f"{MAIN}/build/": "/workspace/circt/build/"}
RUNNER = Path(__file__).with_name("run_bounded.py")
GATED = ["c-p-a2cb61b8d0aa", "c-p-075cf1d70f3a", "c-p-356e9e6e061d", "c-p-9e7eceaadf12",
         "c-p-4f35dc62470e", "c-p-372f1e9ed476", "c-p-3d0f9c33ee0a", "c-p-31a7a300f2e2",
         "c-p-a3a1556793d7", "c-p-509c5aa72a94", "c-p-4b9f84841ec3", "c-p-f0ca5e81cf0d",
         "c-p-a52c6ed44c29", "c-p-4d7a36e3ce15", "c-p-8f95e19612ec"]


def run(where: str, argv: list) -> dict:
    if where == "eade0de6":
        cmd = ["docker", "run", "--rm", "--user", "1000:1000", "-v", f"{ART}:{ART}:ro",
               "-v", f"{RUNNER.parent}:/review:ro", IMAGE, "python3", "/review/run_bounded.py",
               *argv]
        env = None
    else:
        argv = [str(MAIN_BIN), *argv[1:]]
        cmd, env = [sys.executable, str(RUNNER), *argv], MAIN_ENV
    out = json.loads(subprocess.run(cmd, capture_output=True, text=True, check=True,
                                    env=env).stdout)
    for host, image in PREFIXES.items():
        out["stderr"] = out["stderr"].replace(host, image)
    out["argv"] = argv
    return out


def first_circt_frame(stderr: str) -> str:
    for frame in _parse_frames(stderr):
        if "/workspace/circt/" in frame.file:
            return f"{_normalise_function(frame.function)} {os.path.basename(frame.file)}"
    return ""


def verdict(where: str, argv: list, input_path: str, pass_name: str) -> dict:
    """The loop's classification of one re-run, and its fingerprint value."""
    out = run(where, argv)
    status, _ = classify_build(out["exit_status"], out["signal"], out["stderr"],
                               out["limit_hit"])
    op, message, _ = verifier_detail(out["stderr"])
    if status == "parse_error" and op:
        check = run(where, [argv[0], input_path, "-o", "/dev/null"])
        if check["exit_status"] == 0:            # D-13: the input verifies, the output does not
            status = "verifier_error"
    if status == "assertion":
        text, site = _extract_assertion(out["stderr"])
        value = f"{normalise_expr(text)}\n{normalise_site(site or '')}"
    elif status == "verifier_error":
        value = f"{op}\n{generalise_types(message)}\n{pass_name}"
    elif status in ("crash", "fatal_error"):
        value = f"{out['signal'] or ''}\n{first_circt_frame(out['stderr'])}"
    else:
        value = None
    first = next((l for l in out["stderr"].splitlines()
                  if "Assertion" in l or "error:" in l or "Stack dump" in l), "")
    return {"status": status, "value": value, "exit_status": out["exit_status"],
            "signal": out["signal"], "limit_hit": out["limit_hit"],
            "first_line": first.replace(str(ART) + "/", "")[:300],
            "frame": first_circt_frame(out["stderr"]), "stderr": out["stderr"]}


def main(out_path: str) -> int:
    db = sqlite3.connect(f"file:{REPO / 'circt_bug_loop/loop.db'}?mode=ro", uri=True)
    record = {"main_version": subprocess.run([str(MAIN_BIN), "--version"], capture_output=True,
                                             text=True, env=MAIN_ENV).stdout, "candidates": {}}
    for cand in GATED:
        probe = cand[2:]
        stored, oclass, reduced, inp = db.execute(
            "SELECT f.value, c.oracle_class, r.path, p.input_path FROM candidate c "
            "JOIN probe p USING (probe_id) JOIN reduced_case r USING (probe_id) "
            "JOIN fingerprint f USING (candidate_id) WHERE c.candidate_id=? "
            "ORDER BY f.rowid DESC LIMIT 1", (cand,)).fetchone()
        repro = next(ART.glob(f"*/gate/{cand}-*/repro.sh"))
        argv = shlex.split(repro.read_text().splitlines()[1])
        argv = [reduced if a == inp else a for a in argv]
        pass_name = stored.split("\n")[2] if oclass == "verifier_error" else ""
        entry = {"repro_sh": str(repro), "argv": argv, "stored": stored,
                 "oracle_class": oclass, "probe": probe}
        for where in ("eade0de6", "main"):
            entry[where] = verdict(where, argv, reduced, pass_name)
        record["candidates"][cand] = entry
        print(cand, entry["eade0de6"]["status"], entry["eade0de6"]["value"] == stored,
              "|", entry["main"]["status"], entry["main"]["value"] == stored,
              entry["main"]["first_line"][:120], flush=True)
    Path(out_path).write_text(json.dumps(record, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
