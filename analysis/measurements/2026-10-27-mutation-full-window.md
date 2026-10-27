# Mutation arm, stopped full-window run: re-gate of its 45 candidates, 2026-10-27

Run `da63067ca68e469487fd51e32b44f3ea` (tag `registration/review-mutation-1`, mutation arm only,
one machine, image `chia-circt-assert:eade0de61bc5`, CIRCT eade0de6, assertions on), started
2026-10-26T20:34:02Z, stopped by the operator 2026-10-27T07:42:42Z (40,120 s of a 42,836 s
window). Its 45 gate rows all stopped at Q1 with `q1_rerun_worker: unscheduled`: no second
`circt` worker existed, so they were never judged.

## Method

`analysis/review/regate_mutation.py gate` ran `gate.gate_decide` unchanged on all 45, with
`gate._dispatch` swapped so that each worker call (Q1's `gate_rerun` of the original repro
command, Q3's `gate_validate` of the reduced case) ran in its own fresh `docker run --rm`
container of the run's image (id checked against the manifest digest, `sha256:8ac3cb31…`),
and appended the decisions through `bug_loop.write_gate_decision` (45 new `gate_decision`
rows carrying an `answers_json.regated` note; the 45 `unscheduled` rows stay). Each
candidate's original repro and reduced case were then run on the `review-fixes` host build
(CIRCT main 4738bd26 + 13 fixes for the 15 registered bugs, assertions on) by
`regate_mutation.py check`, and `review_numbers.py`'s section-a probe classification was
applied to the run by `regate_mutation.py numbers` over a fresh `validity_rerun.py` pass.

## Funnel

| stage | count |
|---|---|
| probes | 115,869 |
| oracle fired | 45 (30 crash, 11 verifier_error, 4 assertion) |
| candidates | 45 |
| passed Q1 (reproduces, fresh container) | 45 |
| passed Q2 (minimal at reducer fixpoint) | 45 |
| passed Q3 (input valid) | 45 (29 `parsed`, 16 `checker_failed`) |
| passed Q4 (new) | 27 (18 stopped: 14 `fixed_post_pin`, 4 `duplicate_of_candidate`) |
| **gated** (`report`) | **27** |

Q1: every re-run matched class, assertion text and site, and the fingerprint (all 45
`fingerprint_stable = 1`). Every re-run ran on a new host name (a container id), but one
row says `q1_same_worker = 1`: that probe's original `worker_node_id` was `""` (recorded
before the run's local Ray started) and a container has no Ray node, so `"" == ""`.

## Gated survivors, by root cause

| group | candidates | site (pin eade0de6) | class | mutator | duplicate of the 15? | fails on review-fixes? |
|---|---|---|---|---|---|---|
| A | 16 (4 seeds) | `lib/Dialect/FIRRTL/FIRRTLOps.cpp:6966` `RWProbeOp::verifyInnerRefs`: `getParentOfType<FModuleLike>()` is null for an rwprobe outside a module, then `getModuleNameAttr()` | crash (SIGSEGV) | `mlir.op.line_swap` | no (no FIRRTL bug among the 15; no fingerprint match) | yes, 16/16 original and reduced (same frame, FIRRTLOps.cpp:6997 at main) |
| B1 | 9 (1 seed) | `-hw-memory-sim` output fails `sv.always` verifier: operand #0 must be 1-bit, got `i0` (an `i0` clock port on a `FIRRTLMem` generated module) | verifier_error | `mlir.type.i0_zero` | no | yes, 9/9 |
| B2 | 2 (same seed) | `-hw-memory-sim` output fails `comb.mux` verifier: operand #0 must be 1-bit, got `i0` (an `i0` read-enable port) | verifier_error | `mlir.type.i0_zero` | no | yes, 2/2 |

Distinct gated bugs: 3 by fingerprint, 2 by root cause (inference, no patch written): B1 and
B2 are one missing check, `HWMemSimImpl` taking the clock and enable port types of the
generated memory on trust. None is a duplicate of the 15 and all are circt-opt only, so the
review-fixes check ran for every one. Group A never reaches `--firrtl-dedup`: it crashes in
the verifier the parser calls (`mlir::parseAsmSourceFile` → `verifyInnerRefNamespace`), on a
line-swapped input that is invalid IR; Q3 passes it because the checker itself crashed
(`checker_failed`) and the frame is not a parser file. A verifier segfault on invalid IR is
still a bug, but not one in the pass the seed targeted.

Upstream: neither group matched the loop's issue mirror (2,652 issues, refreshed
2026-09-14) nor a title in the local 2026-09-16..10-27 snapshot
(`raw/2026-10-27-circt-issues-since-0916.json`). Nearest open issue: #9998,
`HWMemSimImplPass` SIGFPE on a zero-width *data* memory, a different failure.

## Rejected at Q4, but the review-fixes run contradicts the reason

Outside the gate's rules, for the record (`raw/2026-10-27-mutation-full-window-review-fixes.jsonl`):

- **14 `fixed_post_pin`** (Seq `RUWAttr`/`WUWAttr::getValue` SIGSEGV, 9 + 5, `i0_zero`):
  `seq::FirMemory::FirMemory` (`lib/Dialect/Seq/SeqOps.cpp:1138/1139`) calls
  `getAttrOfType<seq::RUWAttr|WUWAttr>(...).getValue()` unchecked, and the mutant's
  `readUnderWrite = 0 : i0` is no `RUWAttr`. The named fix, ddb3d1bd ("Bump LLVM"), only adds
  a `sym_visibility` argument in `HWMemSimImpl.cpp`; all 14 still crash on main 4738bd26,
  which contains it, and the unchecked lines are unchanged there (SeqOps.cpp:1138/1140).
  A third likely-real bug the gate drops.
- **4 `duplicate_of_candidate` c-p-509c5aa72a94** (`APInt.h:678` "Bit widths must be the
  same"): the assertion-basis fingerprint is text + header site only. The calling frames
  differ (`HWMemSimImpl.cpp:380`, a write-enable `comb.and` built from an `i0` port, versus
  `CoreToFSM.cpp:903`); on review-fixes c-p-509c5aa72a94's reduced case exits 0 (patch 12
  fixes it) while all 4 still assert. A false merge; most likely the same root cause as B.

## Probe measures (review_numbers.py section a, same rule)

`review_numbers.classify_probes` and `REACHED`, imported unchanged; the parse+verify re-run
(`validity_rerun.py`, `-u1000` image, 2026-10-27 07:56-08:09 UTC) covered all 40,284
`parse_error` probes (`raw/2026-10-27-mutation-full-window-validity.tsv.gz`). Rate is over
the 40,120 s from start to the operator stop (no `arm_window` row; `ended_utc` NULL).

| measure | probes | share |
|---|---|---|
| probes | 115,869 | |
| **reached the intended pass** (clean:intact 39,090 + rejected by the pass on an input that parses and verifies 468) | 39,558 | 34.1 % |
| **rejected by parser/verifier** (input fails parse+verify on its own) | 37,129 | 32.0 % |
| … plus `-o %t` overwrote the input (own stderr) | 477 | 0.4 % |
| clean, selector deleted (no intended pass ran) | 20,367 | 17.6 % |
| no result row (`tool=other`, never executed) | 16,083 | 13.9 % |
| command line refused (usage error) | 2,210 | 1.9 % |
| oracle fired (counted apart, as in section b) | 45 | 0.04 % |
| **probes per hour** | 10,397 | |

## Reproduce

```
~/.cache/chia-venv/bin/python analysis/review/regate_mutation.py gate    # appends rows (skips re-gated)
~/.cache/chia-venv/bin/python analysis/review/regate_mutation.py check   # > raw/...-review-fixes.jsonl
gunzip -k analysis/measurements/raw/2026-10-27-mutation-full-window-validity.tsv.gz
~/.cache/chia-venv/bin/python analysis/review/regate_mutation.py numbers \
    analysis/measurements/raw/2026-10-27-mutation-full-window-validity.tsv
```

`loop.db` was backed up to `circt_bug_loop/loop.db.bak-2026-10-27b` before the writes (not
committed). Work dirs: `~/bugloop-artefacts/<run>/gate/` (79 gate calls, plus 2 Q1 smoke
re-runs that wrote no row) and `<run>/regate/` (each call's JSON in and out).
