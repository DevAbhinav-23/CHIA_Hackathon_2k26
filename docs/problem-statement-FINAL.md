# Seed, generate, reduce, repair, gate: a closed CIRCT bug loop

**A CHIA loop seeded with 187 mined CIRCT fix commits, 171 with an exact prebuilt SDK: it generates inputs in each seed's own language, catches them with assertions CHIA's image compiles out, reduces, repairs, gates every filing.**

## 1. Problem

Supply is not scarce: 82 `label:bug` issues filed in a year, 65 closed. Backlog: 101 open, median age 911 days. Attention, not supply, binds. Yet each past fix names a root-cause class with latent siblings, in a compiler with no in-tree fuzzing.

## 2. The loop

**Generator (agent).** Per seed (187 mined fix commits, 171 rebuildable from a stock SDK) the agent reads the diff and test, states the root-cause class, names siblings. **Input language follows the seed**: its lit `RUN:` line is the template — `circt-opt` plus a pass pipeline, `firtool`, or `circt-verilog`. About 127 of 187 seeds are unreachable from `.fir`.

**Oracle (tool).** Primary: crash or CIRCT assertion. Under CHIA's flags every CIRCT object compiles `-DNDEBUG` — 620/620 object compile commands, no `__assert_fail` in `circt-opt`. `-UNDEBUG` restores assertions: 605/605 targets link, 495/513 CIRCT objects carry `__assert_fail`. MLIR/LLVM-core assertions stay off; a segfault rooted there is report-only (CHIA: "out of scope"). Secondary, FIRRTL/HW only: arcilator versus Verilator, reusing `circt/arc-tests`'s lockstep driver. Expected behaviour is agreement; a divergence is a candidate, not an adjudicated CIRCT bug, until the X-initialisation and reset policy is fixed; report-only.

**Reduce, repair, gate.** Oracle-driven `circt-reduce`; CHIA's phase chain unchanged, entered by local report, scoped to crashes and assertions. The gate requires reproduction at the run's commit, minimality, valid input, no duplicate among open/closed issues or post-pin commits; verdict: report, report+patch, or nothing. Reports name the `-UNDEBUG` build: `circt-opt --version` prints "Optimized build."

## 3. Instrument and evaluation

The loop runs on **release-pinned main**: the newest `main` commit whose LLVM pin has a release SDK. HEAD's pin has none; one bump off is a hard tblgen failure. Lag: the loop trails `main` until a release matches the current pin. Over 24 months 16 of 63 pin windows never got one (worst 100 commits / 16 days); in tagged windows the release followed the bump by a median 3.3 days, worst 34. 89.3% of commits are buildable; dedup screens fixes inside the lag. The 171 exact-SDK tasks calibrate repair and gate. Dedup (planned): assertion text + `file:line`, symbolized frames, structural hash. **Head-to-head**: two arms, equal budget, identical tools, oracles and gate — seeded agent generator versus mutation fuzzer, same seeds. **Contamination**: a sibling reproducing a post-seed public fix is memorisation; candidates are screened against closed issues and post-seed commits, reported separately. Repair's executor is untouched, so repair is not contamination-free.

## 4. Expected results

**Headline: distinct, maintainer-confirmed bugs within the pre-registered budget, seeded arm versus mutation arm.** Confirmed = maintainer label, comment or upstream fix; oracle agreement alone = candidate. Budget (GPU-hours, input cap, filing cap) is pre-committed to the public loop repo; that commit is the registration. Secondaries: candidates before/after dedup, reports filed, **gate precision = maintainer-accepted reports / reports filed**, repairs merged; seeded-bug validation separate. Zero is reportable. External scale: FLEX 80 MLIR bugs/30 d, ISSTA-2024 63, Nüwa 55, DESIL 23 silent + 19 crash.

**Demo.** `chia job submit` runs the chain on a release-pinned-main image with `-UNDEBUG`, z3, Verilator, `lit`.

## Relation to CHIA's existing loop

| Stage | CHIA today | This loop |
|---|---|---|
| Supply | `GithubIssuesNode`, open issues | **added** local-report node, ID scheme |
| Oracle | `repro.sh`, "exit 0 **iff** fixed" | **added** `-UNDEBUG` assertions; arcilator/Verilator 2nd |
| Minimize | — | **added** oracle-driven `circt-reduce` |
| Repair | `assess → … → (regression repair)` | **reused unchanged**; new entry point only |
| Writeup | PR description it *would* submit | **added** report prompt, dedup open/closed/post-pin |
| Filing | "No GitHub writes" | **added** gated write, named team member approves, per-day cap |
| Image | `firtool-1.148.0`, assertions off | **added** release-pinned main, `-UNDEBUG`, Verilator, z3 |

## Prior art

AFuzz is the method's origin: reference-bug root cause → sibling hypotheses → generated PoCs; 40 V8 bugs, 19 in SpiderMonkey/JSC; logic bugs; no repair. FLEX is the baseline class: neural, non-agentic MLIR fuzzing, 80 unknown bugs/30 days. Mut4All's LLM-synthesised mutators are the mutation arm's design. Nüwa, DESIL, MLIRSmith and the ISSTA-2024 dependency fuzzer complete the field; none repairs, files or withholds. CodeRover-S, Abstain-and-Validate and llvm-harness cover repair and gating; `circt/arc-tests` is the lockstep differential, `drom/circt-fuzzer` a FIRRTL generator.

## Non-goals

No benchmark, no resolve-rate ranking, no second target, no claim the agent beats the mutation arm, no filing at volume.

## Limitations

Nothing has run end to end. The generator agent and both differential harnesses are unwritten; AFuzz's V8 result is the only evidence such hypotheses transfer. The differential covers only designs both simulators accept, against a tool its own source calls "An experimental circuit simulator". The 187/171 corpus rests on a subject-keyword proxy. The one full build (1,027 targets, 939 s) was `-DNDEBUG`, `circt-opt` only. Maintainer tolerance is unknown.

---

## Appendix A — Claims to sources

| Claim | Source |
|---|---|
| 82 `label:bug` issues created since 2025-09-11 (all states); 65 closed, 17 open; 101 open `bug` total; median open-`bug` age **911** days | Executed 2026-09-11, GitHub search API: `repo:llvm/circt is:issue label:bug created:>2025-09-11` = 82, `+is:closed` = 65, `+is:open` = 17; `repo:llvm/circt is:issue is:open label:bug` = 101; median computed over all 101 `created_at` values against 2026-09-11 |
| `miscompile` 2, `miscompilation` 2, `"wrong output"` 13, `"wrong result"` 14 | Executed 2026-09-11, GitHub search API, `repo:llvm/circt is:issue <term>` |
| CIRCT ships no in-tree fuzzing infrastructure | Blobless clone at HEAD: no `fuzz` directory, no `LLVMFuzzerTestOneInput`, no OSS-Fuzz config, and none of the 12 `.github/workflows` mentions fuzzing |
| 187 bug-subject fix commits / 24 months; **171 (91.4%)** with an exact prebuilt-LLVM SDK; 0 beyond one bump; 38 distinct images cover the 171 | `analysis/pin-window-analysis.md` §4, re-derived from `pin_window_raw.json` |
| Seed distribution by first source directory: FIRRTL 37, ImportVerilog 31, `include/circt/Dialect` 16, MooreToCore 12, LLHD 11, Comb 7, Synth 7, ExportVerilog 5, CoreToFSM 5, ESI 5, HWToBTOR2 4, RTG 4, OM 3, Moore 3, tail; ~60 on the FIRRTL→HW→SV path, ~127 unreachable from a `.fir` input | Re-derivation of the 187 from `pin_window_raw.json`, bucketed by the first `lib/`-or-`include/` path each commit touches; `include/circt/Dialect/<X>` seeds are bucketed under dialect `<X>` |
| 47/63 pin windows (74.6%) contain a release with the same LLVM pin; 2,909/3,257 commits (89.3%) sit in such a window; `firtool-*` release cadence median **7.0 d**, LLVM bump cadence median 10.38 d | `analysis/pin-window-analysis.md` §3 |
| Release-pinned-main lag: 16 of 63 pin windows (24 months) never received a matching release, in 15 runs; worst run 100 commits / 16.1 days (window 254, 2026-01-13 → 2026-01-30). Within tagged windows the first matching release followed the LLVM bump by a median **3.3 d**, p75 8.9 d, max **33.5 d** | Computed 2026-09-12 from `pin_window_raw.json` `windows[]` (window `start`/`end` dates, commit counts, and the earliest `firtool-*` tag date sharing the window's `llvm` pin); script alongside `analysis/pin_window.py` |
| HEAD has no release SDK today: `llvm/circt` HEAD LLVM pin `e297b52ec9d8b5c38042e53ae5650922717970cd`; `firtool-1.159.0` (published 2026-09-09, the newest release) and `firtool-1.158.0` both pin `6279700538792da0c5a08e17babfe9b6e824c69f` | Executed 2026-09-11, GitHub contents API on `llvm` at each ref, plus `/releases?per_page=5`. Architect's earlier check was at HEAD `d7e94049`; re-checked today at HEAD `b792c772` — HEAD had advanced, the LLVM pin and the conclusion are unchanged |
| One LLVM bump off is a hard failure, not a degradation: `ninja circt-opt` fails at target **2/1030** with the SDK's `mlir-tblgen` emitting `error: Variable not defined: 'SymbolName'` across 10 dialects; cmake configure passes first; the bump spans 1,237 llvm-project commits | `analysis/pin-window-analysis.md` §5.5 |
| A stock `firtool-1.157.0` SDK builds CIRCT at a historical parent 18 commits / 11 days downstream of the tag: configure 10 s, `ninja -j6 circt-opt` **1,027/1,027 targets in 939 s**, then the bug's test red at the parent and green after the fix with a 13 s incremental rebuild | `analysis/pin-window-analysis.md` §5.3–5.4 |
| CHIA's cmake passes `-DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_ASSERTIONS=ON`; the SDK's `LLVMConfig.cmake` sets `LLVM_ENABLE_ASSERTIONS OFF`; the recipe strips `/opt/circt-sdk/include/circt` and `lib/cmake/circt` | `dockerfiles/ChiaCirctBaseDockerfile`, quoted in `analysis/pin-window-analysis.md` §5.1; SDK config re-grepped in §5.2 |
| Under those flags **620/620** object compile commands (`compile_commands.json`, all CIRCT: LLVM/MLIR are prebuilt) carry `-DNDEBUG`, and the built `circt-opt` contains **0** `__assert_fail` references | Reference build parsed from `build.ninja` / `compile_commands.json`; `nm` over the built CIRCT objects and the linked binary |
| `-DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG"` restores CIRCT assertions: **605/605** targets, `circt-opt` links, **495/513** `obj.CIRCT` objects reference `__assert_fail`, `lit` over `test/Dialect/{FIRRTL,HW,Comb,Seq}` + `test/Conversion` = **520/523** pass, the 3 failures tracing to a stale SDK `circt-translate` (`type identifier 'Registry' is not declared`), not to the flag | Completed `-UNDEBUG` build of CIRCT `5056ff04450b` against the `firtool-1.157.0` SDK (`circt-opt` closure, 605 targets), 2026-09-11/12; `nm -u` over every built `obj.CIRCT` object; `lit` run on the listed test dirs |
| No ABI hazard from mixing NDEBUG modes: the SDK's `include/llvm/Config/abi-breaking.h` hard-codes `#define LLVM_ENABLE_ABI_BREAKING_CHECKS 0`, and `sizeof`/`alignof` of 20 LLVM/MLIR types (`mlir::Operation`, `Block`, `Region`, `Value`, `OpBuilder`, `RewriterBase`, `PatternRewriter`, `RewritePattern`, `Pass`, `OperationName`, `OperationState`, `Diagnostic`, `InFlightDiagnostic`, `FrozenRewritePatternSet`, `DialectRegistry`, `llvm::SmallVector`, `DenseMap`, `StringMap`, `SmallPtrSet`, `DenseMap::iterator`) are byte-identical under both flags | SDK `include/llvm/Config/abi-breaking.h` read directly; a probe TU compiled twice (`-DNDEBUG` / `-UNDEBUG`) against the SDK headers printing `sizeof`/`alignof` of the 20 types; the completed `-UNDEBUG` build linking and passing lit |
| After `-UNDEBUG`, `bin/circt-opt --version` still prints "Optimized build." — the version string reads `LLVM_ENABLE_ASSERTIONS` out of the SDK's `llvm-config.h`, not CIRCT's `NDEBUG` | Executed on the completed `-UNDEBUG` build: `bin/circt-opt --version` → `LLVM version 24.0.0git / Optimized build. / CIRCT 5056ff0` |
| SDK ships `llvm-symbolizer` (LLVM 24.0.0git), `FileCheck`, `not`, `count`, `split-file`; ships **no** `lit`/`llvm-lit`; needs `libz3.so.4` at runtime | `analysis/pin-window-analysis.md` §5.2 |
| SDK does **not** ship `arcilator-header-cpp.py`; the shipped `circt-test-runner-verilator.py` drives `verilator --cc --exe --main --timing` against a generated `testbench.sv` with a `.clock/.init/.done/.success` port convention | `find` over the extracted SDK (0 hits); read of `circt-sdk/bin/circt-test-runner-verilator.py` |
| `circt-reduce` requires `--test=<string>` and refuses to start without one | Executed against the SDK binary |
| `circt/arc-tests` is in the `circt` GitHub organisation, 39 stars, last pushed 2026-01-26, described as "A collection of tests and benchmarks for the Arc simulation backend of CIRCT"; its README states verbatim: "Lockstep Arcilator and Verilator simulation. Aborts as soon as the simulations diverge.", on Rocket Chip and BOOM, with a `diffvcd.py` divergence differ | Fetched 2026-09-11: GitHub repository API and raw README |
| `tools/arcilator/arcilator.cpp` line 1: "An experimental circuit simulator" | Blobless clone of `llvm/circt`, read at HEAD |
| Verilator X-policy flags `--x-initial` and `--x-assign` | Verilator 5.052 on the probe host, `verilator --help` |
| The executed arcilator-vs-Verilator probe is a 12-line FIRRTL register-add with constant stimulus (`a=8'd7, b=8'd200`), no reset, one 8-bit output, four samples, both harnesses hand-written; both arms printed `o = cf` and agreed | Executed 2026-09-11 and re-run independently during the final check. Cited only as evidence that the pipeline runs end to end on a toy — never as oracle evidence |
| CHIA: triage is a read-only `GithubIssuesNode` that samples "open issues that carry a code-block repro, aren't obvious feature requests, aren't already attempted by the flow, and have no open PR attached"; skip-triage path `--issue 10568`; persistence "issue_logs/issue_<N>/ (`fix.diff`, `pr_writeup.md`, `verdict.json`, per-phase `llm_*.md` + the raw session transcript…)"; plus a row in `issues.db` | `examples/circt_issue_solver/README.md`, fetched raw 2026-09-11 |
| CHIA phase chain: "assess → reproduce → fix → verify → (regression repair) → writeup"; `writeup` produces "the PR description it *would* submit" | same README |
| "**No GitHub writes — both flows only read.**" | same README |
| "Root cause in LLVM/MLIR (the prebuilt SDK / `llvm` submodule) is out of scope — only CIRCT's own tree is buildable here" | same README |
| `reproduce` contract "exit 0 **iff** fixed"; `verify` is "deterministic, no LLM: rebuild, rerun repro, run the full lit gate" | same README |
| "The chia-circt image is pinned at **firtool-1.148.0**" | same README |
| `chia job submit`; `--backend` (`antigravity`, `opencode`); "`--model <id>` overrides the model of whichever backend is selected" | same README |
| AFuzz: "Given a reference bug, the agent analyzes its root cause, hypothesizes new scenarios elsewhere in the codebase that may share that cause, and verifies each hypothesis by generating and running proof-of-concept code"; ran on V8 "for about one month, finding 40 bugs (including three duplicates)"; "19 bugs (including one duplicate) in SpiderMonkey and JavaScriptCore using the seeds from V8"; abstract scopes to logic bugs; no repair component | Park & Yun, "Agentic Fuzzing: Opportunities and Challenges", arXiv 2605.10074, 11 May 2026 (fetched) |
| FLEX: "In a 30-day campaign, FLEX discovers 80 previously unknown bugs … while in 24-hour fixed-revision comparisons, it detects 53 bugs (over 3.5x as many as the best baseline) and achieves 28.2% code coverage"; neural program generation, no LLM agent | Sun, Liang, Wang, Suo, Chen & Xu, "Interleaved Learning and Exploration: A Self-Adaptive Fuzz Testing Framework for MLIR" (FLEX), arXiv 2510.07815, ASE 2025 (fetched) |
| Nüwa, an LLM-based MLIR fuzzer: "outperforms the state-of-the-art tools MLIRSmith and MLIRod, detecting 2.9x more unique bugs and achieving 1.6x greater code coverage. To date, Nüwa has identified 55 bugs in the MLIR framework, with 18 confirmed or fixed" | "Nüwa: Enhancing MLIR Fuzzing with LLM-Driven Generation and Adaptive Mutation", ICSME 2025 (research-track abstract fetched; IEEE Xplore doc 11185938) |
| DESIL: UB-elimination rules "based on the MLIR documentation" plus lowering-path optimization and differential testing; detected **23 silent bugs** and **19 crash bugs**, 12/14 confirmed or fixed; CIRCT not mentioned; no repair component | "DESIL: Detecting Silent Bugs in MLIR Compiler Infrastructure", arXiv 2504.01379 (fetched) |
| ISSTA-2024 operation-dependency fuzzer (MLIRod): operation dependency graph plus dependency-targeted mutation rules; 63 previously unknown bugs, 38 fixed / 48 confirmed; MLIRSmith is the grammar-based predecessor it builds on | "Fuzzing MLIR Compiler Infrastructure via Operation Dependency Analysis", ISSTA 2024, DOI `10.1145/3650212.3680360` |
| Mut4All: three LLM agents synthesise mutators from 1000 bug reports, "yielding 319 Rust and 403 C++ mutators"; the resulting fuzzer "finds 62 bugs in Rust compilers (38 new, 7 fixed) and 34 bugs in C++ compilers (16 new, 1 fixed)" | "Mut4All: Fuzzing Compilers via LLM-Synthesized Mutators Learned from Bug Reports", arXiv 2507.19275 (fetched) |
| CodeRover-S: AutoCodeRover adapted to security; on 588 real-world vulnerabilities repairs 52.4%, and generates plausible patches for 73.3% of unpatched vulnerabilities | "Fixing Security Vulnerabilities with Agentic AI in OSS-Fuzz", ICSE 2026 SEIP, DOI `10.1145/3786583.3786880` |
| Abstain-and-Validate: dual-LLM policy — bug abstention and patch validation — raising success rates by up to 13 and 15 percentage points individually and "up to 39 percentage points in combination", on 174 human-reported bugs plus NPEs and sanitizer-reported bugs | "Abstain and Validate: A Dual-LLM Policy for Reducing Noise in Agentic Program Repair", arXiv 2510.03217, ICSE-SEIP '26 |
| llvm-harness: a harness "designed to assist LLM agents in understanding and fixing compiler bugs"; "Our current focus is on the middle end of LLVM"; ships `llvm-bench` (334 reproducible bugs) and `llvm-autofix-mini`; +62% and +22% | "Agentic Harness for Real-World Compilers", arXiv 2603.20075 (fetched) |
| `drom/circt-fuzzer`: "Generator of random FIRRTL circuits for testing CIRCT and other FIRRTL-based tools" | github.com/drom/circt-fuzzer (fetched 2026-09-11) |

## Appendix B — Not built / not verified

- **Nothing has run end to end.** Stages are verified individually; no composed run of supply → generate → oracle → reduce → triage → repair → gate exists.
- **The generator agent does not exist.** That an agent can turn a CIRCT fix diff into productive sibling hypotheses is assumed from AFuzz's V8 and SpiderMonkey/JSC results, not measured on this compiler.
- **No bug has been discovered by this loop.** No CIRCT assertion has been observed firing at runtime on a generated input, and the arcilator-vs-Verilator differential has never produced a divergence — it has been run once, on a hand-written 12-line design with constant stimulus, where both arms agreed.
- **Neither harness generator exists.** Both harnesses in the executed probe were hand-written. The port-list-driven generators for `arc.sim.*` MLIR and for the Verilator testbench, the shared stimulus and reset protocol, the sampling point, and the X policy are all unwritten work. The SDK does not ship `arcilator-header-cpp.py`, and the shipped `circt-test-runner-verilator.py` expects a port convention a generated design will not satisfy.
- **The mutation-fuzzer baseline arm does not exist.** Its mutator set, its budget accounting, and the equal-budget protocol are undesigned.
- **The release-pinned-main image has not been built.** The pin-window method was measured at a historical parent, not at a moving `main` pointer, and no automation selects the release-pinned commit yet.
- **`-UNDEBUG` cost is unmeasured.** The slowdown, the image size, and any assertions that fire spuriously on ordinary CIRCT input under CHIA's image are unknown. The completed `-UNDEBUG` build was 605 targets for `circt-opt` alone; the `firtool`/`arcilator`/`circt-reduce` target set was never built under either flag, and the one full-closure timing (1,027 targets, 939 s) is `-DNDEBUG`.
- **The assertion finding was measured on a local build reproducing CHIA's cmake flags, not inside CHIA's published image**, which was never built or inspected.
- **The causal attribution** — that the SDK's `LLVMConfig.cmake` is what overrides the command-line `-DLLVM_ENABLE_ASSERTIONS=ON` — is inference from three observed facts, not from reading cmake's variable-resolution order in this build.
- **Dedup is planned, not executed.** None of the three rules has been run on real duplicate pairs; no collision rate, no false-merge rate.
- **Gate precision has no fitted threshold and no calibration data**, and its numerator depends on maintainer response, which lags any budget window.
- **The budget file does not exist yet.** "Pre-registered" is a procedure, not an accomplished fact, until that commit lands.
- **Bugs per unit of budget has no prior estimate** for this generator on this compiler. Zero is a possible and reportable outcome.
- **Maintainer tolerance is unknown.** 13 closed fuzz-mentioning issues show past receptiveness, not consent to a stream of machine-generated reports.
- **The 187/171 corpus rests on a subject-keyword proxy.** No diffs were read to confirm each commit is a bug fix; `analysis/pin-window-analysis.md` §4 states plainly that "Neither number has been validated by reading the diffs".
- **The seed-contamination check is specified, not implemented**, and cannot be complete: a seed's siblings may be fixed in commits whose subjects do not name them.
- **`circt-bmc --run` was never executed** against the shimmed `libz3.so.4`. `circt-lec` was evaluated and dropped from the design; no claim rests on it.

## Appendix C — The one question

**What does the agent add over FLEX-style fuzzing plus `circt-reduce` plus a shell script?**

For generation, honestly: that is the experiment's question, which is why the head-to-head runs a mutation baseline at equal budget and why either outcome is reportable. What is certain is the rest of the loop — a fuzzer plus a reducer produces an unattributed crash pile, whereas this one reproduces at a buildable commit, deduplicates against open issues, closed issues, and post-pin commits, attempts a repair through CHIA's existing phase chain, and withholds everything that fails the gate. CHIA has none of those stages today — its README states "No GitHub writes — both flows only read" — and they are what a 911-day backlog needs.

## Appendix D — Mapping to the 4-page paper

- **§1 Problem and framing** — the backlog-versus-supply argument from §1, with the four measured issue counts and the 911-day median; the constraint is attention, so the contribution is a loop that withholds.
- **§2 The loop** — the stages, the agent/tool split, and the "input language follows the seed" rule with the seed distribution as its justification; the honest exists/added table against `circt_issue_solver`.
- **§3 Instrument** — the pin-window measurement (187/171, 47/63 windows, 89.3% of commits, one-bump-is-fatal), release-pinned main, and the `-DNDEBUG` → `-UNDEBUG` assertion finding (620/620, 605/605, 495/513, lit 520/523) and the ABI check.
- **§4 Evaluation design** — the head-to-head protocol, the pre-registered budget file and its registering commit, the gate-precision definition, the dedup rules, and the contamination procedure.
- **§5 Results** — headline bug counts per arm, secondaries, stage-validation runs reported separately, and the external yield references (FLEX 80/30 d, ISSTA-2024 63, Nüwa 55, DESIL 23+19) as scale context rather than as a comparison claim.
- **§6 Artifact and limitations** — the open-sourced loop as composable CHIA blocks (report-supply node, assertions-on image builder, reduce block, gate block), plus Appendix B carried forward as the paper's threats-to-validity section.
