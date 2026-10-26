#!/usr/bin/env python3
"""Parse+verify re-run of every probe input the tool rejected (T1a/b evidence).

Runs INSIDE chia-circt-assert:eade0de61bc5 (the campaigns' image), read-only on
loop.db and the artefacts. For each probe with build_status
parse_error it runs the input with the probe's own non-selector options and NO
pass (circt-opt on .mlir), or the loop's 4.8 validity command
(.fir: firtool --parse-only, .sv: circt-verilog --import-only).
Writes TSV: run, probe_id, command, exit, first error line.

  docker run --rm --user 1000:1000 -v $HOME/bugloop-artefacts:$HOME/bugloop-artefacts:ro \
    -v $REPO:$REPO chia-circt-assert:eade0de61bc5-u1000 \
    python3 $REPO/analysis/review/validity_rerun.py $REPO/circt_bug_loop/loop.db OUT.tsv RUN...
"""
import json
import os
import sqlite3
import subprocess
import sys

from review_numbers import non_selector_options

BIN = "/workspace/circt/build/bin"


def command(tool: str, argv: list, input_path: str) -> list:
    ext = os.path.splitext(input_path)[1]
    if ext == ".fir":
        return [f"{BIN}/firtool", "--parse-only", input_path]
    if ext in (".sv", ".v"):
        return [f"{BIN}/circt-verilog", "--import-only", input_path]
    keep = non_selector_options([t for t in argv if t != input_path])
    return [f"{BIN}/circt-opt", *keep, input_path, "-o", "/dev/null"]


def main(db_path: str, out: str, runs: list) -> int:
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    rows = db.execute(
        "SELECT p.run_manifest_id, p.probe_id, p.tool, p.argv_json, p.input_path "
        "FROM probe p JOIN probe_result r USING (probe_id) "
        f"WHERE p.run_manifest_id IN ({','.join('?' * len(runs))}) "
        "AND r.build_status = 'parse_error' "
        "ORDER BY p.run_manifest_id, p.probe_id", runs).fetchall()
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("run\tprobe_id\tcommand\texit\tfirst_error\n")
        for run, pid, tool, argv_json, input_path in rows:
            cmd = command(tool, json.loads(argv_json), input_path)
            if not os.path.isfile(input_path):     # `-o %t` bound to the input path
                fh.write(f"{run}\t{pid}\t-\tmissing_input\t\n")
                continue
            try:
                done = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                      errors="replace")
                rc, err = done.returncode, done.stderr
            except subprocess.TimeoutExpired:
                rc, err = "timeout", ""
            first = next((l for l in err.splitlines() if "error" in l), "")
            first = first.replace(input_path, "<input>").replace("\t", " ")[:200]
            fh.write(f"{run}\t{pid}\t{' '.join(cmd[1:]).replace(input_path, '<input>')}"
                     f"\t{rc}\t{first}\n")
    print(f"{len(rows)} rows -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3:]))
