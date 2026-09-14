#!/usr/bin/env python
"""A-19: how many corpus seeds FR-08.1's applicability rule admits.

Two phases, both offline but for git's lazy blob fetches:

1. Mine the corpus at the pinned HEAD with `corpus.build_corpus` and apply
   `probe_task.differential_applicable` to every seed, exactly as the driver
   asks it (`bug_loop.py:_drive_differential`): the tool is the seed's
   `entry_tool` and the argv is `generate_task.probe_argv`, that is the FIRST
   run line's `argv_template` with the two probe-only options stripped and
   lit's substitutions bound. A second, wider reading is counted beside it -
   ANY run line of the seed, under that line's own tool - because 27 seeds
   enter through more than one tool and the driver's reading hides them.

2. For up to N applicable seeds, run the seed's own test input down the
   lifted-design path (`firtool --ir-hw`, or the seed's `circt-opt` pipeline)
   with a real build and hand the result to `probe_task.extract_port_list`,
   which is the precondition FR-08.2's two harness generators have.

No model call, no docker, no cluster, and no simulator: arcilator and Verilator
are never run here.

    python analysis/measurements/a19_applicability.py --lift 10
"""

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from circt_bug_loop import corpus, generate_task, probe_task  # noqa: E402

CORPUS_HEAD_SHA = "d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2"
SINCE = "2024-09-11"
INLINE_CAP_BYTES = 262144
DEFAULT_CLONE = "~/.cache/chia-pin-smoke/w05/corpus-head"
DEFAULT_BIN = "~/.cache/chia-pin-smoke/bassert_g/bin"
DEFAULT_OUT = REPO / "analysis" / "measurements" / "raw"
SUFFIX = {"mlir": ".mlir", "fir": ".fir", "sv": ".sv"}


def _call(node, *args):
    """The undecorated node, as `tests/conftest.py:call_node` does it."""
    return getattr(node, "_chia_original", node)(*args)


class _Spec:
    """The two fields `differential_applicable` reads off a ProbeSpec."""

    def __init__(self, tool, argv):
        self.tool, self.argv = tool, argv


def _driver_spec(seed):
    """The spec the driver would ask the rule about, for this seed.

    `generate_task.probe_argv` binds lit's substitutions to the written input
    and appends it when the template names it nowhere, so the rule sees the
    same tokens in the campaign as it sees here.
    """
    language = generate_task.seed_language(seed)
    if not seed.argv_template:              # FR-01.9: excluded from both arms,
        return None, language               # so the rule is never asked of it
    input_path = f"/artefacts/probe/input{SUFFIX.get(language, '.mlir')}"
    return _Spec(seed.entry_tool, generate_task.probe_argv(seed, input_path)), language


def _line_specs(seed):
    """One spec per run line, under that line's OWN tool (the wider reading)."""
    for line, template in zip(seed.run_lines, seed.argv_template):
        tool = corpus.classify_entry_tool(corpus.entry_tool_of_line(line))
        argv, _ = corpus.strip_probe_only_options(list(template))
        yield line, _Spec(tool, argv)


def _bump(table, key):
    table[key] = table.get(key, 0) + 1


def classify(mined):
    """Apply the rule to every seed. Returns (rows, summary)."""
    exclusions = mined["exclusions"]
    rows, summary = [], {
        "seeds": len(mined["seeds"]),
        "exact_pin": mined["counts"]["exact_pin"],
        "applicable": 0, "applicable_exact_pin": 0, "applicable_eligible": 0,
        "reason": {}, "by_entry_tool": {}, "by_language": {},
        "applicable_by_entry_tool": {}, "applicable_by_language": {},
        "any_run_line_applicable": 0, "any_run_line_only": [],
    }

    for seed in mined["seeds"]:
        spec, language = _driver_spec(seed)
        if spec is None:
            applicable, reason = False, "no_run_line"
        else:
            applicable, reason = probe_task.differential_applicable(spec)

        wider = [line for line, other in _line_specs(seed)
                 if probe_task.differential_applicable(other)[0]]

        _bump(summary["by_entry_tool"], seed.entry_tool)
        _bump(summary["by_language"], language)
        _bump(summary["reason"], reason or "applicable")
        if applicable:
            summary["applicable"] += 1
            _bump(summary["applicable_by_entry_tool"], seed.entry_tool)
            _bump(summary["applicable_by_language"], language)
            if seed.sdk_exact:
                summary["applicable_exact_pin"] += 1
            if seed.seed_sha not in exclusions:
                summary["applicable_eligible"] += 1
        if wider:
            summary["any_run_line_applicable"] += 1
            if not applicable:
                summary["any_run_line_only"].append(seed.seed_sha)

        rows.append({
            "sha": seed.seed_sha,
            "subject": seed.subject,
            "entry_tool": seed.entry_tool,
            "language": language,
            "sdk_exact": seed.sdk_exact,
            "sdk_tag": seed.sdk_tag or "",
            "dialect_bucket": seed.dialect_bucket,
            "excluded": exclusions.get(seed.seed_sha, ""),
            "run_lines": len(seed.run_lines),
            "applicable": applicable,
            "reason": reason,
            "output_mode": _output_mode(spec) if spec else "",
            "any_run_line_applicable": bool(wider),
            "driver_argv": shlex.join([seed.entry_tool] + list(spec.argv)) if spec else "",
            "first_run_line": seed.run_lines[0] if seed.run_lines else "",
        })
    return rows, summary


def _output_mode(spec):
    """What made the seed applicable, in the rule's own vocabulary."""
    if spec.tool == "firtool":
        modes = [probe_task._option_name(t) for t in spec.argv]
        hit = [m for m in modes if m in probe_task._FIRTOOL_HW_MODES]
        return f"--{hit[0]}" if hit else ""
    if spec.tool == "circt-opt":
        last = probe_task._last_pass(spec.argv)
        return f"--{last}" if last in probe_task._HW_TERMINAL_PASSES else ""
    return ""


# --- phase 2, the lifted-design path ----------------------------------------

def _run_line_source(seed, blob):
    """The test path run line 0 came from, `build_corpus`'s own order."""
    for path in seed.test_paths:
        if corpus.extract_run_lines(blob(path)):
            return path
    return ""


def _lift_argv(seed, tool_bin, input_path, out_path):
    """The lifted-design command for one seed (LLD 3.6.3, 4.13)."""
    if seed.entry_tool == "firtool":
        return [tool_bin, input_path, "--ir-hw", "-o", out_path]
    argv, _ = corpus.strip_probe_only_options(list(seed.argv_template[0]))
    bound, skip = [], False
    for token in argv:
        if skip:
            skip = False
            continue
        if token in ("-o", "--o"):
            skip = True
            continue
        for placeholder in ("%S", "%s", "%t"):
            token = token.replace(placeholder, input_path)
        bound.append(token)
    if input_path not in bound:
        bound.append(input_path)
    return [tool_bin] + bound + ["-o", out_path]


def _one_lift(seed, source, lifted, bin_dir):
    """Lift one file and try to read a port list off it. Returns a record."""
    argv = _lift_argv(seed, os.path.join(bin_dir, seed.entry_tool),
                      str(source), str(lifted))
    record = {"lift_argv": shlex.join(argv)}
    started = time.monotonic()
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        record["lift_returncode"] = done.returncode
        record["lift_stderr"] = done.stderr.strip()[:600]
    except (OSError, subprocess.SubprocessError) as error:
        record["lift_returncode"] = None
        record["lift_stderr"] = str(error)[:600]
    record["lift_seconds"] = round(time.monotonic() - started, 2)

    if record["lift_returncode"] != 0 or not Path(lifted).exists():
        record["outcome"] = "lift_failed"
        return record
    record["lifted_bytes"] = Path(lifted).stat().st_size
    try:
        ports = probe_task.extract_port_list(str(lifted), bin_dir=bin_dir)
        record["outcome"] = "port_list"
        record["top"] = probe_task.top_module_name(str(lifted), bin_dir=bin_dir)
        record["ports"] = [{"index": p.index, "name": p.name,
                            "direction": p.direction, "width": p.width,
                            "type": p.mlir_type, "clock": p.is_clock,
                            "reset": p.is_reset} for p in ports]
    except probe_task.HarnessError as error:
        record["outcome"] = f"harness_error:{error.reason}"
        record["detail"] = error.detail[:400]
    return record


def _chunks(text):
    """A lit `--split-input-file` file's independent chunks, in file order.

    The corpus strips `--split-input-file` from every probe argv (FR-01.10), so
    the WHOLE seed test file reaches one `circt-opt` run and a file holding
    fourteen designs has no single top. B4's own input is one generated design,
    so the chunk is the honest unit to ask the port-list question of.
    """
    out, current = [], []
    for line in text.splitlines(keepends=True):
        if line.startswith("// -----"):
            out.append("".join(current))
            current = []
        else:
            current.append(line)
    out.append("".join(current))
    return [c for c in out if c.strip()]


def lift(rows, mined, clone, bin_dir, work, limit):
    """Run up to *limit* applicable seeds down the lifted-design path."""
    by_sha = {s.seed_sha: s for s in mined["seeds"]}
    out = []
    for row in [r for r in rows if r["applicable"]][:limit]:
        seed = by_sha[row["sha"]]
        record = {"sha": seed.seed_sha, "entry_tool": seed.entry_tool,
                  "subject": seed.subject}

        def blob(path, sha=seed.seed_sha):
            done = subprocess.run(["git", "-C", clone, "show", f"{sha}:{path}"],
                                  capture_output=True, text=True, timeout=300)
            return done.stdout if done.returncode == 0 else ""

        path = _run_line_source(seed, blob)
        record["test_path"] = path
        if not path:
            record["outcome"] = "no_test_blob"
            out.append(record)
            continue

        directory = Path(work) / seed.seed_sha
        directory.mkdir(parents=True, exist_ok=True)
        text = blob(path)
        source = directory / Path(path).name
        source.write_text(text)
        record.update(_one_lift(seed, source, directory / "lifted.mlir", bin_dir))

        chunks = _chunks(text)
        record["chunks"] = len(chunks)
        record["chunk_outcomes"] = {}
        for index, chunk in enumerate(chunks):
            piece = directory / f"chunk{index:02d}{source.suffix}"
            piece.write_text(chunk)
            one = _one_lift(seed, piece, directory / f"chunk{index:02d}.hw.mlir",
                            bin_dir)
            _bump(record["chunk_outcomes"], one["outcome"])
            if one["outcome"] == "port_list" and "first_chunk_port_list" not in record:
                record["first_chunk_port_list"] = {
                    "chunk": index, "top": one["top"], "ports": one["ports"]}
        out.append(record)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clone", default=DEFAULT_CLONE)
    parser.add_argument("--bin-dir", default=DEFAULT_BIN)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--lift", type=int, default=0,
                        help="run at most this many applicable seeds down the "
                             "lifted-design path (phase 2)")
    parser.add_argument("--work", default="",
                        help="scratch directory for phase 2's lifted IR "
                             "(default: a fresh temporary directory; the raw "
                             "output records the argv, not these files)")
    args = parser.parse_args()

    if os.environ.get("BUGLOOP_ALLOW_LIVE_MODEL"):
        print("refusing: BUGLOOP_ALLOW_LIVE_MODEL is set", file=sys.stderr)
        return 2

    clone = os.path.expanduser(args.clone)
    bin_dir = os.path.expanduser(args.bin_dir)
    out = Path(os.path.expanduser(args.out))
    out.mkdir(parents=True, exist_ok=True)
    work = (os.path.expanduser(args.work) if args.work
            else tempfile.mkdtemp(prefix="a19-lift-"))

    started = time.monotonic()
    mined = _call(corpus.build_corpus, clone, CORPUS_HEAD_SHA, SINCE, INLINE_CAP_BYTES)
    mine_seconds = time.monotonic() - started
    if mined["counts"]["missing_blobs"]:
        print(f"warning: {mined['counts']['missing_blobs']} test blobs missing",
              file=sys.stderr)

    rows, summary = classify(mined)
    summary["mine_seconds"] = round(mine_seconds, 1)
    summary["missing_blobs"] = mined["counts"]["missing_blobs"]
    summary["git_calls"] = mined["counts"]["git_calls"]
    summary["corpus_head_sha"] = CORPUS_HEAD_SHA
    summary["clone"] = clone
    summary["entry_tool_seeds"] = mined["counts"]["entry_tool_seeds"]
    summary["rule"] = {
        "firtool_hw_modes": list(probe_task._FIRTOOL_HW_MODES),
        "hw_terminal_passes": list(probe_task._HW_TERMINAL_PASSES),
        "not_a_pass": list(probe_task._NOT_A_PASS),
    }

    with (out / "a19-per-seed.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    if args.lift:
        lift_started = time.monotonic()
        lifted = lift(rows, mined, clone, bin_dir, work, args.lift)
        summary["lift_seconds"] = round(time.monotonic() - lift_started, 1)
        summary["lift_bin_dir"] = bin_dir
        (out / "a19-lift.json").write_text(json.dumps(lifted, indent=2) + "\n")
        summary["lift_outcomes"] = {}
        for record in lifted:
            _bump(summary["lift_outcomes"], record["outcome"])

    summary["wall_seconds"] = round(time.monotonic() - started, 1)
    (out / "a19-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
