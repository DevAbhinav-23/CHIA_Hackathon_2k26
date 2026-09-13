# CIRCT bugs on demand: seed, generate, shrink, repair, gate

**A CHIA loop that seeds an agent with 187 pin-verified CIRCT fix commits, has it hypothesise sibling bugs elsewhere, proves each with executable oracles, shrinks it, and returns it to CHIA's issue-solver through a local-report entry point.**

## 1. Problem

Supply is whatever maintainers file: 101 open `bug` issues, median age 911 days, 17 filed last year. Wrong-output reports are rarer: `miscompile` 2, `miscompilation` 2, `"wrong output"` 13, `"wrong result"` 14. The loop makes supply a function of compute.

## 2. The loop

**Generator (agent).** Per seed (one of the 187 mined fixes) the agent reads the diff and test, states the root-cause class, names sibling sites (same pattern, other dialects or passes), and emits inputs aimed there. Churn is secondary.

**Oracles (tools).** (i) *Crash/assert.* Under CHIA's cmake flags CIRCT assertions are off: 583/583 CIRCT object rules compile `-DNDEBUG`, zero `__assert_fail`. `-DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG"` restores them. SDK LLVM/MLIR assertions stay off, so the oracle sees CIRCT asserts and segfaults. (ii) *Two implementations.* `arcilator` on `firtool --ir-hw` against Verilator on `firtool --verilog`, same stimulus; on a 12-line FIRRTL register-add both printed `o = cf` for four cycles. Arcilator's harness is `arc.sim.*` MLIR generated from the port list. (iii) A `circt-lec` self-differential, third only.

**Shrink and triage.** `circt-reduce --test=<script>`, that script being the oracle; an agent then dedups, classifies, and writes an issue-shaped report: reduced `.mlir`, command, observed vs expected.

**Repair.** CHIA's `circt_issue_solver`, entered by local report instead of issue number, scoped to crashes and assertions: expected behaviour is unambiguous, so `assess` cannot log `unclear`. Divergences are report-only.

**Gate.** Reproduces at `main`, minimal, not a duplicate against open *and* closed issues, not invalid input; then report, report+patch, or nothing. Reports carry a disclosure line; a named human approves each.

## 3. Instrument and evaluation

The 171 exact-SDK tasks are instrument: regression-testing repair, calibrating the gate. One built 1,027/1,027 targets in 939 s at a historical parent, red→green. Dedup, planned: assertion text plus `file:line`; segfault frames via the SDK's `llvm-symbolizer`; reduced cases by structural hash after `circt-opt --canonicalize --strip-debuginfo` and sequential renaming. Discovered bug *instances* are new, so discovery is contamination-free; the repair executor's training data is unchanged, so repair is not.

## 4. Expected results

**Headline: distinct, maintainer-confirmed bugs within a pre-registered budget** — GPU-hours and a generated-input cap, fixed before the run. Confirmed means a maintainer label, comment, or upstream fix; oracle agreement or independent reproduction makes a *candidate*. Also: candidates found, candidates after dedup, reports filed, accepted, repairs merged. Zero is a reportable outcome. External yield: DESIL found 42 MLIR-core bugs, the ISSTA-2024 operation-dependency fuzzer 63; CIRCT has 15 fuzz-mentioning issues, 13 closed. Seeded-bug runs validate the pipeline's stages, reported separately.

**Demo.** `chia job submit` runs generate → oracle → reduce → triage → repair → gate on a HEAD-tracking image (fetch-by-SHA) with `-UNDEBUG`, z3, Verilator, `lit`.

## Relation to CHIA's existing loop

| Stage | CHIA today | This loop |
|---|---|---|
| Supply | open GitHub issues, read-only | seeded generator |
| Oracle | `repro.sh`, *exit 0 iff fixed* | CIRCT asserts; arcilator vs Verilator |
| Minimize | — | `circt-reduce`, oracle-driven |
| Repair | assess→…→writeup phase chain | **reused, with a local-report entry point** |
| Decide | skip `not_a_bug` / `unclear` | gate: report, report+patch, nothing |
| Image | `firtool-1.148.0` | HEAD-tracking + `-UNDEBUG`, z3, Verilator, `lit` |

## Prior art

AFuzz (2605.10074) is the method: the agent analyses a reference bug's root cause, hypothesises new scenarios sharing it elsewhere, and verifies each with generated PoCs — 40 V8 bugs, 19 more in SpiderMonkey and JavaScriptCore from V8 seeds, no repair. Different here: a hardware compiler, reference bugs rebuildable at their parent commits, repair and a filing gate inside CHIA. DESIL (2504.01379) finds silent MLIR-core bugs by differential testing with UB elimination — 23 silent, 19 crash — without CIRCT or repair. Mut4All (2507.19275) synthesises mutators from bug reports; CodeRover-S (ICSE 2026 SEIP) patches OSS-Fuzz findings; Abstain-and-Validate (2510.03217) is the gate's prior art; llvm-harness (2603.20075) an LLVM middle-end agent harness.

## Non-goals

No benchmark, no resolve-rate ranking, no second target, no claim about which divergence arm is right.

## Limitations

Oracle (iii) is inoperable: `circt-lec` is combinational, refuses `hw.wire` inner symbols, and the normalizing pass does not ship. The differential covers only designs both simulators accept. Generated inputs may be invalid FIRRTL, hence triage. Assertions-on is verified at configure and on one rebuilt object, not a full build. Maintainer confirmation lags the budget.

---

## Appendix A — Claims to sources

| Claim | Source |
|---|---|
| 101 open `bug` issues; median age **911** days (n=101); 17 open `bug` issues created since 2025-09-11 | Executed 2026-09-11: GitHub search API `repo:llvm/circt is:issue is:open label:bug`, and `created:>2025-09-11`; median computed over all 101 `created_at` values against 2026-09-11 |
| `miscompile` 2, `miscompilation` 2, `"wrong output"` 13, `"wrong result"` 14 | Executed 2026-09-11: GitHub search API, `repo:llvm/circt is:issue <term>` |
| 15 issues mention fuzz, 13 closed | Executed 2026-09-11: `repo:llvm/circt is:issue fuzz` → 15; `+is:closed` → 13 |
| 187 bug-fix-shaped commits / 24 months; 171 (91.4%) exact prebuilt-LLVM SDK; 0 beyond one bump; 38 images | `pin-window-analysis.md` §4 |
| 1,027/1,027 targets in 939 s at a historical parent; red→green flip | `pin-window-analysis.md` §5.3–5.4 |
| SDK ships no `lit`; needs `libz3.so.4`; SDK `LLVMConfig.cmake` → `LLVM_ENABLE_ASSERTIONS OFF` | `pin-window-analysis.md` §5.2; re-confirmed by `grep LLVM_ENABLE_ASSERTIONS /home/adi/.cache/chia-pin-smoke/circt-sdk/lib/cmake/llvm/LLVMConfig.cmake` |
| CHIA's cmake passes `-DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_ASSERTIONS=ON` | `pin-window-analysis.md` §5.1 (verbatim from `dockerfiles/ChiaCirctBaseDockerfile`) |
| Under those flags, **583/583** CIRCT `.cpp.o` rules carry `-DNDEBUG`, 0 carry `-UNDEBUG`; `CombOps.cpp.o` has **0** `__assert_fail` references; `CMakeCache.txt` records `LLVM_ENABLE_ASSERTIONS:UNINITIALIZED=ON` alongside `CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -DNDEBUG` | Executed 2026-09-11: parsed `/home/adi/.cache/chia-pin-smoke/src/build/build.ninja` for every `*CIRCT*.cpp.o` rule; `nm` on `.../obj.CIRCTComb.dir/CombOps.cpp.o` |
| Adding `-DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG"` gives **583/583** `-UNDEBUG`, 0 `-DNDEBUG`; the rebuilt `CombOps.cpp.o` has 1 `__assert_fail` reference and embeds `val.getType().isInteger() && "expected integer"` | Executed 2026-09-11: fresh `cmake` configure (rc=0) into a separate build dir with CHIA's other flags unchanged, then `ninja lib/Dialect/Comb/CMakeFiles/obj.CIRCTComb.dir/CombOps.cpp.o`, then `nm`/`strings` |
| Assert source line `assert(val.getType().isInteger() && "expected integer");` | `lib/Dialect/Comb/CombOps.cpp:116` at commit `5056ff04450b` |
| `firtool tiny.fir --ir-hw` and `--verilog` both rc=0 on a 12-line FIRRTL register-add | Executed 2026-09-11, SDK `firtool-1.157.0` |
| `arcilator --run --jit-entry=main` JIT-runs firtool `--ir-hw` output against the shimmed `libz3.so.4`; printed `o = cf` four times, rc=0 | Executed 2026-09-11 |
| The arcilator harness is MLIR (`arc.sim.instantiate` / `set_input` / `step` / `get_port` / `emit`) inside the same top-level module; `om.class` must be removed and the clock port is `!seq.clock` — passing `i1` errors `'arc.sim.set_input' op mismatched types between value and model port, port expects '!seq.clock'`, fixed with `seq.to_clock` | Executed 2026-09-11; form follows `integration_test/arcilator/JIT/counter.mlir` |
| `verilator --binary --timing -Wno-fatal --top-module tb tb.sv tiny.sv -Mdir vbuild -o vtb` builds, and the binary printed `o = cf` four times, rc=0, on the same stimulus | Executed 2026-09-11 |
| Verilator `5.052 2026-09-05 rev v5.052` on the probe host | `verilator --version` |
| SDK ships `circt-test-runner-verilator.py`, which drives `verilator --cc --exe --main --timing` against a generated `testbench.sv` with a `.clock/.init/.done/.success` port convention | Read `/home/adi/.cache/chia-pin-smoke/circt-sdk/bin/circt-test-runner-verilator.py` |
| SDK does **not** ship `arcilator-header-cpp.py`; a CIRCT source build does (`build/bin/arcilator-header-cpp.py`, `arcilator-runtime.h`) | `find` over `circt-sdk` → 0 hits; `ls /home/adi/.cache/chia-pin-smoke/src2/build/bin/` |
| `circt-lec --c1 --c2 --run --shared-libs` prints `c1 == c2` and `c1 != c2` **both with rc=0**; rc=1 on tool error | Executed 2026-09-11 on a 3-module `.mlir`: `@A` vs `@B` (commuted add) → `c1 == c2`, rc=0; `@A` vs `@C` (sub) → `c1 != c2`, rc=0 |
| `circt-lec` refuses `hw.wire`: `error: failed to legalize operation 'hw.wire' that was explicitly marked illegal`, rc=1; `circt-opt --canonicalize` leaves a symbol-carrying `hw.wire` standing | Executed 2026-09-11 on `hw.module @W { %w = hw.wire %a sym @s : i4 }` |
| SDK ships `llvm-symbolizer` (LLVM 24.0.0git) | `ls`/`--version` on `circt-sdk/bin/llvm-symbolizer` |
| `circt-reduce --test=<string>` required; refuses to start without one | v2 Appendix A, executed |
| The executed 67→7-line `circt-reduce` run used the placeholder interestingness test `grep -q 'comb.mul' "$1"`, not a differential oracle | `red-team-AB.md` §B-W3 |
| `--preserve-aggregate` is not a usable differential axis: default scalarization makes the arms differ only by `sv.namehint`, and `--scalarize-public-modules=false` makes port types differ, which `circt-lec` refuses | `red-team-AB.md` §B-K1, with the quoted `circt-lec` IO-mismatch error and `docs/Tools/circt-lec.md` |
| `firtool-1.148.0` is 364 first-parent commits behind `llvm/circt` HEAD at analysis time | `red-team-AB.md` §B-W5 |
| CHIA: triage is a "head, read-only `GithubIssuesNode`" sampling "open issues that carry a code-block repro"; per-issue unit `run_issue_remote`; skip-triage path `--issue 10568`; "**No GitHub writes — both flows only read.**" | `examples/circt_issue_solver/README.md` (fetched raw, 2026-09-11) |
| CHIA `assess`: "is this actually a bug, and are the bug *and* the correct behavior clear? If not, log the reason and skip (`not_a_bug` / `unclear`)." | same README |
| CHIA `reproduce` contract: "exit 0 **iff** fixed" | same README |
| CHIA `verify`: "deterministic, no LLM: rebuild, rerun repro, run the full lit gate"; gate is "not `check-circt` (its integration tests need verilator/z3/sby, absent here)" | same README |
| "The chia-circt image is pinned at **firtool-1.148.0**." | same README |
| `chia job submit`; `--backend` / `--model <id>` | same README |
| AFuzz: "Given a reference bug, the agent analyzes its root cause, hypothesizes new scenarios elsewhere in the codebase that may share that cause, and verifies each hypothesis by generating and running proof-of-concept code"; "40 bugs" in V8; "19 bugs (including one duplicate) in SpiderMonkey and JavaScriptCore using the seeds from V8"; no repair component in the abstract | arXiv 2605.10074, "Agentic Fuzzing: Opportunities and Challenges", submitted 2026-05-11 (fetched) |
| DESIL: "DESIL: Detecting Silent Bugs in MLIR Compiler Infrastructure"; UB-elimination rules, lowering-path optimization, differential testing with operation-aware optimization recommendation; "detected 23 silent bugs and 19 crash bugs" in MLIR; CIRCT not mentioned; no repair component | arXiv 2504.01379 (fetched) |
| Mut4All: "Mut4All: Fuzzing Compilers via LLM-Synthesized Mutators Learned from Bug Reports"; three agents synthesise mutators from bug reports; 319 Rust and 403 C++ mutators | arXiv 2507.19275 (fetched) |
| CodeRover-S: "Fixing Security Vulnerabilities with Agentic AI in OSS-Fuzz", ICSE 2026 SEIP; an AutoCodeRover adaptation that, given a fuzzer's vulnerability report and exploit input, autonomously generates patches; plausible patches for 73.3% of unpatched vulnerabilities | ICSE 2026 SEIP programme page and ACM DL entry, `10.1145/3786583.3786880` (searched 2026-09-11) |
| llvm-harness: "Agentic Harness for Real-World Compilers"; a harness to help LLM agents understand and fix compiler bugs; "Our current focus is on the middle end of LLVM" | arXiv 2603.20075 (fetched) |
| Abstain-and-Validate: dual-LLM policy for bug abstention and patch validation | arXiv 2510.03217, as spot-checked in `red-team-AB.md` §A4 |
| ISSTA 2024 operation-dependency MLIR fuzzer found 63 bugs | `red-team-AB.md` §B4 |

## Appendix B — Not verified

- No end-to-end run of the loop. Stages are verified individually.
- No bug has been discovered by this loop. The `arcilator`-vs-Verilator differential was executed once, on a hand-written 12-line FIRRTL design, and the two arms agreed; it has never been run on a generated input and has never produced a divergence.
- The generator agent does not exist. That an agent can turn a fix diff into productive sibling hypotheses on *CIRCT* is assumed from AFuzz's V8 result, not measured here.
- The assertions-on configuration was verified at cmake-configure time (all 583 CIRCT object rules) and by rebuilding one object. A full 1,027-target assertions-on build was not run, and no CIRCT assertion has been observed firing at runtime.
- The causal attribution — that the prebuilt SDK's `LLVMConfig.cmake` is what overrides the command-line `-DLLVM_ENABLE_ASSERTIONS=ON` — is inference from three observed facts (cache says ON, SDK config says OFF, output flags say `-DNDEBUG`), not from reading cmake's variable-resolution order in this build.
- `-UNDEBUG` changes the shipped binary's behaviour and cost; the slowdown and any newly-firing assertions in the CHIA image are unmeasured.
- The assertion finding was measured on a local build reproducing CHIA's cmake flags at commit `5056ff04450b`, not inside CHIA's published image; the image was not built or inspected.
- The dedup rules (assertion text + `file:line`, symbolized top frames, structural hash after canonicalize/strip-debuginfo/renaming) are planned. None has been executed on real duplicate pairs, and no collision rate is known.
- `circt-bmc --run` was never executed against the shimmed `libz3.so.4`.
- The `circt-lec` normalization pass that would strip `hw.wire` inner symbols does not exist and has not been written.
- The HEAD-tracking image has not been built. The pin-window method was measured at a historical parent, not at moving `main`.
- Bugs per unit of budget has no prior estimate for this generator on this compiler, which is why the budget is pre-registered and zero is reportable.
- Whether CIRCT maintainers will accept machine-generated reduced test cases at any volume is unknown. The 13 closed fuzz-mentioning issues show past receptiveness, not consent to a stream.
- Gate precision has no fitted threshold or calibration data.
- The 187/171 corpus rests on a subject-keyword proxy; no diffs were read to confirm each is a bug fix (`pin-window-analysis.md` §4 caveats).

## Appendix C — The one question

**What does the agent add over an existing fuzzer + `circt-reduce` + a shell script?**

The middle — oracle and shrinker — *is* a shell script, and it is written as one here. The agent is at the two ends: at the front it turns a specific past fix into a specific hypothesis about a sibling site, which a random generator cannot do and which is where AFuzz's 40 V8 bugs came from; at the back it decides whether a reduced case is a real bug, an invalid input, or an already-closed issue, and writes the report a maintainer will read.

## Appendix D — Red-team map

| Attack | Where v3 answers it |
|---|---|
| **B-K1** dead `--preserve-aggregate` axis; self-comparison | Axis dropped. The differential is now two independent implementations (`arcilator` vs Verilator), executed. `circt-lec` demoted to a third oracle, stated inoperable pending a normalization pass. |
| **B-K2** "`circt_issue_solver` unchanged" is false; `assess` skips divergences as `unclear` | §2 Repair and the table row name a local-report entry point as the one change. Repair scoped to crashes/assertions where expected behaviour is unambiguous; divergences are report-only. Contract quoted as "exit 0 **iff** fixed". |
| **B-K3** "0 issues match miscompil" is a search artifact | Dropped. §1 gives the four real counts, measured today, and rests the motivation on backlog age and supply-side economics instead. |
| **B-K4** self-grading "confirmed"; self-set denominator | Confirmed = maintainer label, comment, or upstream fix only. Oracle agreement makes a *candidate*. Denominator is a pre-registered budget; DESIL's 42 and ISSTA-2024's 63 are the external reference points. |
| **B-K5** AFuzz, DESIL, Mut4All, CodeRover-S uncited | All four cited in Prior art, with what each did and what differs here. |
| **B-W1** "normalized wire-free" names no mechanism | Limitations states it plainly: the normalizing pass does not ship, so oracle (iii) is inoperable. |
| **B-W2** differential's discriminating region is thin | Addressed by construction: the primary differential is now two separate implementations, not two flag settings of one pipeline. |
| **B-W3** the 93% reduction was `grep`-driven | The number is not cited in the body. Appendix A records that the executed reduction used `grep -q 'comb.mul'` as its interestingness test. |
| **B-W4** crash oracle needs assertions the SDK lacks; frames unusable | Measured and fixed: `-UNDEBUG` restores CIRCT assertions (583/583 rules, one object rebuilt and checked). Scope stated — CIRCT asserts and segfaults, not MLIR-core asserts. Frames symbolized with the SDK's `llvm-symbolizer` against the CIRCT build. |
| **B-W5** stale pinned image; dedup misses upstream-fixed bugs | HEAD-tracking image, built fetch-by-SHA. Gate requires reproduction at current `main` and a search of open **and** closed issues. |
| **B-W6** blast radius undefined | Removed from the gate. The gate's inputs are reproduces-at-HEAD, minimal, not a duplicate, not invalid input. |
| **B-W7** churn/test-file ratio justifies nothing | Replaced. The generator is seeded by the 187 mined fixes per AFuzz's method; churn survives only as a labelled secondary ranking signal. |
| **B-W8** structural dedup evidenced by one rename | Rewritten as an operational rule — canonicalize, strip debug info, sequential symbol/SSA renaming, then hash — and labelled planned in §3 and Appendix B. |
| **B-N1**…**B-N7** | "Pitch." label removed; "Not Track 1…" removed; the AI-policy sentence replaced by its mechanism (disclosure line in every report, a named human approves every filing); no scare-quoted tool stdout; seeded-bug runs described as stage validation reported separately; contamination stated precisely in §3. |
