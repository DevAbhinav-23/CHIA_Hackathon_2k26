# A-19: how many corpus seeds the differential oracle applies to

**Run date** 2026-09-14 (IST), on `cachyos-x8664`. **Scope** A-19, the measurement FR-08.1's
acceptance criterion requires and ADR-D-09 puts before any work on F-08's harness
generators: run FR-08.1's applicability rule over the 187-seed corpus and report the count
**with the rule that produced it**. Owed to `paper/main.tex` §VII and to `design/01-FRD.md`
F-08. Script: `analysis/measurements/a19_applicability.py`.

**No model call was made.** `BUGLOOP_ALLOW_LIVE_MODEL` was never set; the script refuses to
start if it is. No docker, no cluster. **Neither simulator was run**: arcilator and
Verilator are not invoked anywhere in this measurement, and §6's step stops at the port
list, which is the precondition the two harness generators have, not the harnesses
themselves.

## 0. Verdict

**Six** of the 187 seeds are differential-applicable, all six through `circt-opt`, all six
in MLIR, all six exact-pin. The count is not zero, so R-09 does not fire and the harness
generators are worth writing; it is small enough that F-08's campaign value is a handful of
seeds and not a fraction of the corpus.

| | |
|---|---|
| **Applicable seeds** | **6 of 187** (3.2%) |
| of the 171 exact-pin seeds | **6 of 171** (3.5%), every applicable seed is exact-pin |
| by entry tool | `circt-opt` 6; `firtool` 0; every other tool 0 by the rule's first clause |
| by language | `mlir` 6; `sv` 0; `fir` 0 |
| eligible as well as applicable | 6 of 6 — none is excluded by FR-01.9, FR-01.10 or the inline cap |
| under the wider "any run line" reading | **6** — the same six; no seed is applicable only on a later line |
| a port list extracted from the seed's own design | **3 of 6** (§6) |
| wall clock, whole measurement | **7.3 s** (mine 5.8 s, 358 git calls; lift-and-port-list 1.4 s) — a warm object store, every blob already in the worktree |

## 1. The rule that produced it

`circt_bug_loop/probe_task.py:differential_applicable`, FR-08.1 as amended 2026-09-15, read
off the argv and nothing else, before either simulator runs. It is two closed sets:

- **`firtool`** is applicable when the argv requests one of `--ir-hw`, `--verilog`,
  `--split-verilog`; otherwise `firtool_output_mode_not_hw`. `firtool` with **no** output
  mode emits Verilog by default and is **not** admitted, the requirement saying
  "requesting" one of three.
- **`circt-opt`** is applicable when the **last** option of the argv that is not one of
  `-o`, `--verify-diagnostics`, `--split-input-file`, `--split-file`,
  `--mlir-print-op-generic`, `--allow-unregistered-dialect` is one of the seven
  `--lower-*-to-hw` conversions: `lower-firrtl-to-hw`, `lower-hwarith-to-hw`,
  `lower-calyx-to-hw`, `lower-dc-to-hw`, `lower-esi-to-hw`, `lower-handshake-to-hw`,
  `lower-pipeline-to-hw`. Otherwise `pipeline_not_hw_terminal`. `--convert-moore-to-core` is
  deliberately absent, which is the requirement's own acceptance criterion.
- **Everything else** is `entry_tool_not_hw_capable`, which is every `circt-verilog`,
  `circt-translate`, `arcilator` and `other` seed.
- Both dash spellings are accepted; a `--pass-pipeline=` probe is refused rather than
  parsed.

All seven `--lower-*-to-hw` conversions and all three `firtool` modes are registered in the
measured build (`bassert_g`, CIRCT `5056ff0`, `circt-opt --help` / `firtool --help`,
2026-09-14), so the enumeration is not stale. Only **six** of the seven have a corpus seed:
`--lower-pipeline-to-hw` has none, and is code for no case in this corpus exactly as the
refused `--pass-pipeline=` spelling was claimed to be (§5).

## 2. How the rule was asked

Two readings, both recorded, because they could have differed and it matters which one the
count is.

**The driver's reading, which is the headline.** `bug_loop.py:_drive_differential` asks the
rule about the `ProbeSpec` the emitter built, whose `tool` is the seed's `entry_tool` — the
**first** run line's tool in `test_paths` order (FR-01.3, W-05 erratum 4) — and whose `argv`
is `generate_task.probe_argv(seed, input_path)`, that is `argv_template[0]` with the two
probe-only options stripped and lit's `%S`/`%s`/`%t` bound to the written input. The
measurement builds exactly that pair and calls the same function.

**The wider reading, counted beside it.** Every run line of the seed, under **that line's**
own tool. 27 seeds enter through more than one tool, so a seed could have been applicable on
a line the driver never reaches. **None is**: the wider reading returns the same six, and the
"applicable only on a later line" list is empty. The first-line convention costs nothing
here.

Two seeds (`0da0bde46833` and `76fc7146b8e9`, both entry tool `other`) record no `RUN:` line at all; FR-01.9
excludes them from both arms, so the rule is never asked of them and they are counted
`no_run_line` rather than given a rule reason.

**One thing the count does not cover.** Arm B's argument mutator can change the argv the
probe runs. The only one in `mutators/set_dev.json` is `any.argv.option.duplicate`, and
`mutators._sequence` inserts the copy at `index + 1`, so relative order — and therefore
which option is last — is preserved. That mutator cannot make an inapplicable seed
applicable or the reverse. Any future argv mutator that reorders or appends can, and this
count would then be a count of unmutated probes only.

## 3. The counts

**By reason, over all 187:**

| Reason | Seeds |
|---|---|
| applicable | **6** |
| `pipeline_not_hw_terminal` | 123 |
| `entry_tool_not_hw_capable` | 55 |
| `no_run_line` (FR-01.9, the rule is never asked) | 2 |
| `firtool_output_mode_not_hw` | 1 |

**By entry tool** (the seed's `entry_tool`, one per seed, summing to 187):

| Entry tool | Seeds | Applicable | Reason for the rest |
|---|---|---|---|
| `circt-opt` | 129 | **6** | 123 `pipeline_not_hw_terminal` |
| `circt-translate` | 35 | 0 | `entry_tool_not_hw_capable` |
| `other` | 18 | 0 | 16 `entry_tool_not_hw_capable`, 2 `no_run_line` |
| `circt-verilog` | 3 | 0 | `entry_tool_not_hw_capable` |
| `arcilator` | 1 | 0 | `entry_tool_not_hw_capable` |
| `firtool` | 1 | 0 | 1 `firtool_output_mode_not_hw` |

The `firtool` row is the one that looks like an accident and is not: exactly one seed of the
187 enters through `firtool`, and its only run line is
`firtool -disable-annotation-unknown %s | FileCheck %s`, which requests no output mode.
`firtool` appears on some run line of **5** seeds (`counts["entry_tool_seeds"]`), and none of
those nine lines requests `--ir-hw`, `--verilog` or `--split-verilog` either: the modes are
`-repl-seq-mem`, `-disable-annotation-unknown`, `-extract-test-code`, `-ir-verilog`,
`--parse-only`, and twice nothing at all. **The `firtool` half of FR-08.1's rule matches no
corpus seed under any reading.** The whole count is the `circt-opt` half.

**By language** (`generate_task.seed_language`, the first test path's extension, one per
seed):

| Language | Seeds | Applicable |
|---|---|---|
| `mlir` | 148 | **6** |
| `sv` | 35 | 0 (all 35 are `entry_tool_not_hw_capable`) |
| `fir` | 4 | 0 (3 `entry_tool_not_hw_capable`, 1 `firtool_output_mode_not_hw`) |

## 4. The six applicable seeds

| Seed SHA | Subject | Tool | Output mode | Dialect bucket | SDK tag | RUN lines |
|---|---|---|---|---|---|---|
| `23abfba6006b9581a537632ab31f162f0213d3dd` | `[DCToHW] Fix invalid ESI connections from Unpack(pack()) (#10649)` | `circt-opt` | `--lower-dc-to-hw` | DC | `firtool-1.150.0` | 2 |
| `73e28e09a3b5ba17ab4eba999d5bbff7031b11ee` | `[CalyxToHW] Fix missing i1-to-clock conversion in convertPipelineOp (#9715)` | `circt-opt` | `--lower-calyx-to-hw` | CalyxToHW | `firtool-1.141.0` | 1 |
| `3b30c823b82916627d62f59d4e6e8e520f8b530d` | `[HandshakeToHW] Fix crashes when multiple syncs with different numbers of ...` | `circt-opt` | `--lower-handshake-to-hw` | HandshakeToHW | `firtool-1.141.0` | 9 |
| `91872b228b74931e77419e7b6c36a4bbf8cc0431` | `Fix inout port lowering for sv.verbatim.module (#9209)` | `circt-opt` | `--lower-firrtl-to-hw` | SV | `firtool-1.137.0` | 1 |
| `3f0aa622f0ca59877dececf8631bf7028b59b051` | `[ESI] Fix assert on lower unwrap value from block arg` | `circt-opt` | `--lower-esi-to-hw` | ESI | `firtool-1.107.0` | 1 |
| `99826b849987b38b8590ad70cc45efd02dce2c35` | `[HWArith] Fix lowering to HW with type aliases` | `circt-opt` | `--lower-hwarith-to-hw` | HWArithToHW | `firtool-1.99.0` | 1 |

Six seeds, six **distinct** conversions and six distinct dialect buckets: the applicable set
is one seed per HW-terminal lowering that the corpus exercises, not a cluster. Four of the
six spell the option with a single dash, which is why W-09 finding 3's both-spellings rule
is load-bearing here and not decorative: **without it the count would be 2.**

Each seed's own probe argv, as the driver would build it (input path elided):

```
circt-opt --lower-dc-to-hw INPUT
circt-opt -lower-calyx-to-hw INPUT
circt-opt -lower-handshake-to-hw INPUT
circt-opt -lower-firrtl-to-hw INPUT
circt-opt --lower-esi-to-hw INPUT
circt-opt -lower-hwarith-to-hw INPUT
```

## 5. What each unmeasured clause of the rule costs

FR-08.1 states three exclusions as deliberate. Two of the three cost seeds, and one of the
two was justified by a measurement that is **wrong** (§7, erratum 1).

| Relaxation | Driver reading | Any-run-line reading |
|---|---|---|
| the rule as shipped | **6** | 6 |
| + parse `--pass-pipeline=` for an HW-terminal lowering | **7** | 7 |
| + treat `--verify-roundtrip` as not-a-pass | 6 | 6 |
| + admit `firtool` with no explicit output mode (default Verilog) | **7** | 10 |
| all three | **8** | 11 |

- **`--pass-pipeline=` costs exactly one seed**, `3f65acfd617b` (`[FIRRTLToHW] Fix firrtl enum
  lowering (#10648)`, exact-pin, one run line):
  `circt-opt -pass-pipeline="builtin.module(lower-firrtl-to-hw)" -verify-diagnostics %s --split-input-file | FileCheck %s`.
  It is line 29 of `raw/m1-per-runline.csv`.
- **`--verify-roundtrip` costs nothing here.** `351189822e33` (`[ESI] Window lowered type fix
  (#9243)`) has `circt-opt %s --lower-esi-ports --lower-esi-to-hw --lower-esi-types --verify-roundtrip`
  on its second run line, and `--verify-roundtrip` is a registered `circt-opt` pass, so
  treating it as one is not itself wrong; the last **lowering** on that line is
  `--lower-esi-types`, which is not HW-terminal, so the seed is refused for the right reason
  by the wrong route. A latent shape, not a live defect.
- **`firtool`'s default-Verilog exclusion costs one seed in the reading that counts** and
  four in the wider one. It is already flagged as an erratum candidate in
  `test_probe_task.py:test_u_probe_27`; this is its price.

## 6. The port list, on the applicable seeds' own designs

FR-08.2's two harness generators are fed by `probe_task.extract_port_list`, so whether a real
corpus design gets that far is the next question after the count. For each of the six
applicable seeds the seed's own test file at the seed commit was lifted with the seed's
`circt-opt` pipeline and the result handed to `extract_port_list` and `top_module_name`,
against the measured build at `~/.cache/chia-pin-smoke/bassert_g/bin` with
`LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim`.

The command is `<bin>/circt-opt <input> <the seed's HW-terminal option> -o <lifted>`, with
the seed's own `-o` dropped and lit's substitutions bound; `--split-input-file` is already
stripped by FR-01.10's normalisation, which is why the **whole** lit file reaches one run.
Because that puts many designs in one module, each file was also split on lit's `// -----`
and every chunk lifted separately — B4's own input is one generated design, so the chunk is
the honest unit.

| Seed | Whole-file outcome | Chunks | Per-chunk outcomes |
|---|---|---|---|
| `23abfba6006b` (DC) | `no_top` — lift rc 0, 7447 B, **14 public `hw.module`** | 1 | `no_top` 1 |
| `73e28e09a3b5` (Calyx) | **port list** — top `main`, **7 ports** | 1 | `port_list` 1 |
| `3b30c823b829` (Handshake) | lift failed rc 1: `'builtin.module' op multiple candidate top-level modules detected` | 3 | `no_top` 3 |
| `91872b228b74` (FIRRTL) | **port list** — top `VerbatimBlackBoxTest`, **4 ports** | 1 | `port_list` 1 |
| `3f0aa622f0ca` (ESI) | lift failed rc 1: `lower-esi-to-hw left behind a channel operation` | 1 | `lift_failed` 1 |
| `99826b849987` (HWArith) | `no_top` — lift rc 0, 7980 B, **12 public `hw.module`** | 13 | `no_clock` 9, `bad_port_type` 2, **`port_list` 1**, `no_top` 1 |

**Three of the six** yield a port list from a design of their own seed: two whole-file, and
HWArith's chunk 7. The three port lists:

| Seed | Top | Ports (name : type, direction) |
|---|---|---|
| `73e28e09a3b5` | `main` | `in0 : i32` in, `in1 : i32` in, `clk : i1` in **(clock)**, `reset : i1` in **(reset)**, `go : i1` in, `out0 : i32` out, `done : i1` out |
| `91872b228b74` | `VerbatimBlackBoxTest` | `clk : !seq.clock` in **(clock)**, `rst : i1` in **(reset)**, `data : i8` in, `result : i1` out |
| `99826b849987` chunk 7 | `sigAndOps` | `a : i8` in, `b : i8` in, `cond : i1` in, `clk : !seq.clock` in **(clock)**, `out : i8` out |

Three things worth keeping:

1. **`_CLOCK_NAMES` earns its place.** The Calyx design's clock is `clk : i1`, not
   `!seq.clock`; `is_clock` is true only because `"clk"` is in `_CLOCK_NAMES`. On a real
   corpus design, the type test alone would have produced `no_clock` and no harness. The
   `[DEFAULT]` name list of LLD §9.4 is doing work.
2. **`no_clock` is the dominant design-level refusal.** 9 of HWArith's 13 chunks are purely
   combinational. Whatever the seed count is, the design-level yield is thinned again by
   FR-08.3 having no cycle to sample at.
3. **`no_top` is an artefact of the seed's own file, not of the design.** Two seeds' lit
   files declare 12 and 14 public `hw.module`s in one file; the campaign's probe input is one
   generated design, so this failure mode is not the one B4 will meet. It is recorded because
   it is what running the seed's **recorded** input actually does.

## 7. Errata found in the rule, on real records

1. **FR-08.1's `--pass-pipeline=` justification is contradicted by the corpus.** Both the
   requirement and `differential_applicable`'s docstring say "**50** of M1's corpus `RUN:`
   lines use that spelling and **none** of them is HW-terminal, so reading the last pass out
   of a nested pipeline string would be code for no case". The line count is right — 50 — but
   **one of the 50 is HW-terminal**: `raw/m1-per-runline.csv` line 29, seed
   `3f65acfd617b`, whose only `RUN:` line is

   ```
   circt-opt -pass-pipeline="builtin.module(lower-firrtl-to-hw)" -verify-diagnostics %s --split-input-file | FileCheck %s
   ```

   The refusal is a defensible design choice, but its stated reason is false and its price is
   one seed out of six — a sixth of the whole applicable set. FR-08.1, the docstring and
   `test_u_probe_27`'s comment are all owed the correction.
2. **`entry_tool_of_line`'s `circt-capi-.*` is still greedy in `corpus.py`.** The mine's
   `counts["entry_tool_seeds"]` carries the literal key `"circt-capi-firrtl-test 2>&1 "`.
   W-05 erratum 14 fixed exactly this in `analysis/measurements/m1_runlines.py` and not in
   `circt_bug_loop/corpus.py:62`. It changes no verdict — `classify_entry_tool` maps anything
   outside the five names to `other` — and it changes nothing in this measurement, but it
   puts a shell fragment in a reported count's key.
3. **The seventh HW-terminal pass is code for no case.** `--lower-pipeline-to-hw` is
   registered in the measured build and matches no corpus seed, which is the same charge the
   rule levels at `--pass-pipeline=`. Keeping it is right — the rule must outlive this corpus
   — but the enumeration should not be described as measured-from-the-corpus.

Nothing in `differential_applicable` mis-classified a record it was handed: every one of the
187 verdicts is the verdict the stated rule gives, and the six agree with a hand read of the
six `RUN:` lines.

## 8. What A-19 now says, and what stays open

**A-19 is closed by measurement.** Six of the 187 seeds are differential-applicable under
FR-08.1's rule as amended (six of the 171 exact-pin seeds; all six `circt-opt`, all six MLIR,
one per HW-terminal lowering the corpus exercises), so the count is above zero, R-09 does not
fire, and F-08's harness generators and `T-U-probe-50` are worth writing; the eleven of RT3
§1 K2 is not the same quantity and is not carried forward.

**What stays open:** whether a generated harness runs on a real corpus **design**. This
measurement reaches the port list and stops there — three of the six seeds produce one, the
commonest refusal on a real design being `no_clock` — and neither arcilator nor Verilator was
invoked. A-08 is closed on the recorded 12-line FIRRTL register-add (errata W-17 row 14) and
not on anything mined; W-18's pilot is what will show whether a harness generated from one of
these six port lists builds and runs.

## 9. Reproduction

```sh
source ~/.cache/chia-venv-py31019/bin/activate
export LD_LIBRARY_PATH=$HOME/.cache/chia-pin-smoke/circt-sdk/lib:$HOME/.cache/chia-pin-smoke/shim
unset BUGLOOP_ALLOW_LIVE_MODEL
cd ~/Projects/CHIA_Hackathon_2k26
python analysis/measurements/a19_applicability.py --lift 10
```

Defaults: `--clone ~/.cache/chia-pin-smoke/w05/corpus-head` (the W-05 worktree, HEAD
`d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2`, every blob already present — `missing_blobs` was
0 and no lazy fetch was needed), `--bin-dir ~/.cache/chia-pin-smoke/bassert_g/bin`,
`--out analysis/measurements/raw`, and `--work` a fresh temporary directory for the lifted
IR — the raw output records each command, not its intermediates. Two consecutive runs gave
the same counts and 6.4 s and 7.3 s of wall clock; the figure in §0 is the second.
The mine is `corpus.build_corpus(clone, d7e94049…,
"2024-09-11", 262144)`, the call `test_corpus.py`'s tier-1 `mined` fixture makes, invoked
through the node's `_chia_original` so no local Ray starts.

Environment: Python 3.10.19, git 2.55.0, CIRCT `5056ff0` / LLVM 24.0.0git optimized
(`bassert_g`, `circt-opt` sha256 `08258f6f2a3492f05…`).

Raw output:

| File | What it is |
|---|---|
| `raw/a19-summary.json` | every count in §0, §3 and §5, plus the rule's three constant lists as the run saw them |
| `raw/a19-per-seed.csv` | one row per seed: SHA, subject, entry tool, language, exact-pin, dialect bucket, exclusion, applicability, reason, output mode, the wider reading, the driver's argv, the first `RUN:` line |
| `raw/a19-lift.json` | §6 in full: per seed the lift argv, return code, stderr, byte count, the port list, and every chunk's outcome |
