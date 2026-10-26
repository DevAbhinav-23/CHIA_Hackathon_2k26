#!/usr/bin/env python3
"""T2 report: the recheck table and one issue draft per ready-to-file bug.

Reads recheck_main.py's JSON. The GitHub/commit matches are the read-only search
recorded in the report (issue list: raw/2026-10-27-circt-issues-since-0916.json;
commits: `git log --since=2026-09-16 main -- <site file>` in a full clone).
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "analysis/measurements/raw/2026-10-27-recheck-main.json"
OUT = REPO / "analysis/measurements/2026-10-27-recheck-main.md"
DRAFTS = REPO / "analysis/review/issue-drafts"
ART = str(Path.home() / "bugloop-artefacts") + "/"
MAIN_SHA = "4738bd2685a1bed0f44623ad1a800146a0d8c43c"
POINT_SHA = "eade0de61bc5a0d2ba1b9da951b69efcab19f8ce"
ISSUE = "https://github.com/llvm/circt/issues/"
PR = "https://github.com/llvm/circt/pull/"

#: candidate -> (short site, title, known match note, filing group)
META = {
 "c-p-a2cb61b8d0aa": ("HWOps.cpp ArrayConcatOp::build", "[MooreToCore] Assertion `!values.empty()` in hw::ArrayConcatOp::build lowering an out-of-range array moore.extract", "none", ""),
 "c-p-075cf1d70f3a": ("comb.extract verifier after MooreToCore", "[MooreToCore] moore.dyn_extract from an integer to an array type emits an invalid comb.extract", f"related, not same: open issue {ISSUE}11141 and open PR {PR}11142 (packed-aggregate refs)", ""),
 "c-p-356e9e6e061d": ("llhd.sig.extract verifier after MooreToCore", "[MooreToCore] moore.extract_ref from an integer ref to a struct ref emits an invalid llhd.sig.extract", f"related, not same: open issue {ISSUE}11141 covers aggregate *source* refs; this is an aggregate *result*", ""),
 "c-p-9e7eceaadf12": ("DCToHW.cpp RTLBuilder::buildNamedOp", "[DCToHW] Assertion `!empty()` building comb.and for a dc.join with no operands", "none", ""),
 "c-p-4f35dc62470e": ("BackedgeBuilder.cpp Backedge::setValue", "[DCToHW] Type-mismatch assertion in Backedge::setValue lowering dc.pack of a !dc.token", "none", ""),
 "c-p-372f1e9ed476": ("CombOps.cpp constructMuxTree", "[CombToSynth] Assertion `Index < Length` in comb::constructMuxTree lowering a 1-bit comb.shrs", "none", "CombToSynth narrow widths"),
 "c-p-3d0f9c33ee0a": ("CombToSynth.cpp createShiftLogic", "[CombToSynth] Assertion `outOfBoundsValue must be valid` lowering an i0 comb.shl", "none", "CombToSynth narrow widths"),
 "c-p-31a7a300f2e2": ("CombToSynth.cpp getFinal", "[CombToSynth] Assertion `width > 0` lowering an i0 comb.icmp ult (Kogge-Stone)", "none", "CombToSynth narrow widths"),
 "c-p-a3a1556793d7": ("OMOps.cpp ElaboratedObjectOp::verifySymbolUses", "[OM] Crash in ElaboratedObjectOp::verifySymbolUses when className names an om.class.extern", "none", ""),
 "c-p-509c5aa72a94": ("CoreToFSM.cpp -> CombFolds AndOp::fold", "[CoreToFSM] APInt width assertion in comb.and folding during -convert-core-to-fsm", "none", "CoreToFSM reset registers"),
 "c-p-4b9f84841ec3": ("MLIR verifier on CoreToFSM output", "[CoreToFSM] Segfault in the post-pass verifier after -convert-core-to-fsm", "none", "CoreToFSM reset registers"),
 "c-p-f0ca5e81cf0d": ("CombFolds.cpp applyCmpPredicate", "[CoreToFSM] APInt width assertion in comb.icmp folding during -convert-core-to-fsm", "none", "CoreToFSM reset registers"),
 "c-p-a52c6ed44c29": ("OMOps.cpp IntegerShlOp::fold", "[OM] Assertion `ShiftAmt <= BitWidth` folding om.integer.shl with a large shift amount", "none", ""),
 "c-p-4d7a36e3ce15": ("MooreToCore.cpp resolveClassStructBody", "[MooreToCore] Segfault in resolveClassStructBody for a class extending an undefined base", "none", ""),
 "c-p-8f95e19612ec": ("MooreToCore.cpp DynExtractRefOpConversion", "[MooreToCore] cast<> assertion in DynExtractRefOpConversion on a dyn_extract_ref of an open unpacked array", f"related, not same: open PR {PR}11267 (range-checks dynamic array accesses) and {ISSUE}11141", ""),
}


def same_bug(a: dict, b: dict) -> bool:
    """Same class and same assertion text / verifier op+message / signal, and same CIRCT frame."""
    head = lambda v: (v["value"] or "").split("\n")[0]
    return a["status"] == b["status"] and head(a) == head(b) and a["frame"] == b["frame"]


def outcome(entry: dict, where: str) -> str:
    run, stored = entry[where], entry["stored"]
    if run["status"] == "clean_exit":
        return "passes"
    if run["value"] == stored or (run["status"] == entry["oracle_class"] == "crash"
                                  and stored.split("\n")[0] == run["signal"]
                                  and stored.split("\n")[1].rsplit(" ", 1)[0] in run["stderr"]):
        return f"fails, same fingerprint ({run['status']})"
    if same_bug(run, entry["eade0de6"]):
        site = (run["value"] or "").split("\n")[-1]
        return f"fails, same bug, fingerprint differs (site now `{site}`)"
    return f"fails differently: {run['status']} `{(run['value'] or '').splitlines()[0][:60]}`"


PROLOGUE = ("PrintStackTrace", "RunSignalHandlers", "SignalHandler", "pthread_kill",
            "raise", "abort", "__assert_fail", "libc.so")


def trace_excerpt(stderr: str) -> str:
    """The error/assert lines and the first eight frames after the crash-handler prologue."""
    keep, frames = [], 0
    stderr = re.sub(r"\S*/reduced\.mlir", "repro.mlir", stderr)
    for line in stderr.splitlines():
        if line.lstrip().startswith("#"):
            if frames < 8 and not any(p in line for p in PROLOGUE):
                keep.append(line.strip()[:200])
                frames += 1
        elif "Assertion" in line or "error:" in line or "Stack dump" in line:
            keep.append(line[:400])
    return "\n".join(keep)


def draft(cand: str, entry: dict, title: str, group: str) -> str:
    main = entry["main"]
    reduced = Path(entry["argv"][[a.endswith("reduced.mlir") for a in entry["argv"]].index(True)])
    args = " ".join("repro.mlir" if a.endswith("reduced.mlir") else
                    (f"'{a}'" if any(c in a for c in "(){} ") else a)
                    for a in entry["argv"][1:])
    trace = trace_excerpt(main["stderr"]).replace("/workspace/circt/", "circt/")
    trace = trace.replace("/opt/circt-sdk/", "<llvm-install>/")
    note = (f"\nPossibly the same root cause as the other '{group}' drafts; consider "
            "filing them as one issue.\n" if group else "")
    return f"""# {title}

**Status: draft, not filed.** Found by an LLM-assisted fuzzing loop that
writes test inputs from CIRCT regression tests; reduced automatically and
re-checked on current main. Candidate `{cand}`.
{note}
## Reproducer (`repro.mlir`)

```mlir
{reduced.read_text().rstrip()}
```

## Command

```sh
circt-opt {args}
```

## Result

Reproduces on current `main` at {MAIN_SHA} (LLVM pin from firtool-1.162.0,
Release, assertions on) and at {POINT_SHA} (firtool-1.159.0). Class: `{main['status']}`.

```text
{trace}
```

## CIRCT SHA

- main: `{MAIN_SHA}` (`circt-opt --version`: CIRCT 4738bd2)
- also at: `{POINT_SHA}`
"""


def main() -> int:
    data = json.loads(RAW.read_text())
    DRAFTS.mkdir(parents=True, exist_ok=True)
    rows = []
    for cand, entry in data["candidates"].items():
        site, title, match, group = META[cand]
        point, now = outcome(entry, "eade0de6"), outcome(entry, "main")
        ready = now != "passes" and entry["eade0de6"]["status"] != "clean_exit"
        rows.append(f"| `{cand}` | {site} | {point} | {now} | {match} | "
                    f"{'yes' + (f' (group: {group})' if group else '') if ready else 'no'} |")
        if ready:
            (DRAFTS / f"{cand}.md").write_text(draft(cand, entry, title, group))
    doc = f"""# Re-check of the 15 gated candidates on CIRCT main, 2026-10-27

Generated by `analysis/review/recheck_main.py` (re-runs, raw record
`raw/2026-10-27-recheck-main.json`) and `analysis/review/recheck_report.py`.
Nothing was filed or posted.

**Builds.** Build point: `chia-circt-assert:eade0de61bc5-u1000` (CIRCT {POINT_SHA[:12]},
SDK firtool-1.159.0, `-O3 -UNDEBUG -gline-tables-only`). Main: `llvm/circt` main
**{MAIN_SHA}** (2026-10-26, "[Seq] Add UnrollMemoryLatencies Pass (#11308)"), whose
`llvm` gitlink a17069fe equals the gitlink of release **firtool-1.162.0**, so its
prebuilt SDK was used (exact pin match, no fallback commit); built on this host
by `analysis/review/main_build.sh` into `~/.cache/review-main-build/` with the
same flags and `LLVM_ENABLE_ASSERTIONS=ON`, target `circt-opt` only (all 15
reproducers are `circt-opt`), 531 s at -j12. Assertions verified compiled in
(the reproducers below hit them).

**Runs.** Each candidate's `repro.sh` argv with its `input.mlir` replaced by the
gate's `reduced.mlir`, one fresh process per run, 60 s wall and 4 GiB address
space (`run_bounded.py`), classified with the loop's own `probe_task`/`triage_task`
parsers (D-13 verifier check included); main's source paths are mapped to
`/workspace/circt/` before fingerprinting so only real differences count.
"Same fingerprint" = the loop's stored fingerprint value; "same bug" = same
class, same assertion text / verifier op+message / signal and same first CIRCT
frame as at the build point, with only the site line moved.

**Search (read-only).** Every llvm/circt issue and PR updated since 2026-09-16
(277, `GET /repos/llvm/circt/issues?state=all&since=2026-09-16`, saved trimmed
as `raw/2026-10-27-circt-issues-since-0916.json`) grepped for each bug's
symbols and messages; `git log --since=2026-09-16 main` over each site file
and over commit messages in a full clone. `gh` is not installed here, so the
REST API was queried with curl, unauthenticated. Commits since 2026-09-16 touch
MooreToCore.cpp (4), HWOps.cpp (3), CombToSynth.cpp (1), OMOps.cpp (2),
CombFolds.cpp (4); none fixes any of the 15, which all still reproduce.

| candidate | site | repro on eade0de6 | repro on main@{MAIN_SHA[:10]} | known issue/commit match | ready to file |
|---|---|---|---|---|---|
""" + "\n".join(rows) + """

Fingerprint differences on main are line moves only: CIRCT source lines shifted
(HWOps.cpp 1995→2034, CombToSynth.cpp 98→101 and 756→836) and the LLVM bump
moved header asserts (APInt.h, STLExtras.h) by 1-16 lines. The loop's assertion
fingerprint includes the line, so it would call these new bugs; the
same-bug check above does not.

Drafts: `analysis/review/issue-drafts/<candidate>.md`. Suspected shared root
causes (not verified): the three `CoreToFSM reset registers` drafts all reduce
to a module with a 2-bit `seq.compreg` state register with reset feeding a 1-bit
op, and the three `CombToSynth narrow widths` drafts to i0/i1 operands.
"""
    OUT.write_text(doc)
    print(doc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
