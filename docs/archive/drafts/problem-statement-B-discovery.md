# CIRCT bugs on demand: discover, shrink, repair, gate

**Pitch.** A CHIA loop that manufactures its own CIRCT compiler bugs from repo evidence, proves each with an executable oracle, shrinks it with `circt-reduce`, repairs it through CHIA's issue-solver unchanged, and gates what reaches a maintainer.

## 1. Problem

Repair loops draw from one pool: open issues. CIRCT has 101 open `bug` issues (median age 890 days, 17 filed last year), bounded by maintainer goodwill, not compute. And 0 issues match "miscompil": silent wrong-output bugs do not file themselves.

## 2. The loop

**Generator (agent).** FIRRTL/HW-dialect inputs aimed at measured weak spots: `lib/Dialect/AXI4` took 21 commits in 90 days against 3 lit test files, ESI 88 against 18, FIRRTL 86 against 213. The agent reads that gap and the diffs; a random generator spends its budget on the best-tested dialect.

**Oracles (tools).** (i) Crash/assert, assertions ON. (ii) Differential: one input through `firtool` at `-O=debug`/`-O=release` × each `--preserve-aggregate`, compared by `circt-lec --c1=M --c2=M --run --shared-libs=<libz3.so.4>`; `circt-bmc -b <cycles>` adds sequential depth. (iii) Verilator on `firtool --verilog`. Executed: `none` vs `all` gave `c1 == c2`; an unequal pair, `c1 != c2`. `circt-lec` exits 0 for *both* verdicts, so the script reads stdout; it rejects `hw.wire`, so pairs are normalized wire-free.

**Shrinker (tool).** `circt-reduce --test=<script>`; it refuses to start without one, and the oracle is that script. Executed: 67 lines to 7, a "93% reduction".

**Triage (agent).** Dedups; classifies real-bug / invalid-input / known-issue; writes the report.

**Repair.** CHIA's `circt_issue_solver` unchanged; the reduced case is its repro contract, "exit 0 when fixed".

**Gate.** From executed evidence only — reproduces, minimal, fix flips exactly the reduced case, lit gate green, blast radius — it emits report-only, report-plus-patch, or nothing, under the LLVM AI Tool Policy's disclosure and human-in-the-loop duties. Abstention prior art: arXiv 2510.03217.

## 3. Instrument and evaluation

The mined corpus is instrument, not result. Of 187 bug-fix-shaped commits over 24 months, 171 (91.4%) have an exact prebuilt-LLVM `firtool-*` SDK; 38 images cover all 171. A historical-parent build ran 1,027/1,027 targets in 939 s, red at the parent, green after the fix. Those 171 only regression-test repair and calibrate the gate. Contamination is moot: discovered bugs never existed.

## 4. Expected results

**Headline: distinct, reduced, maintainer-confirmed bugs per GPU-hour.** *Distinct*: reduced cases matching after symbol renaming (reduce renamed `@Target` to `@Foo`), or sharing a crash signature (top-3 frames plus assertion text), collapse. *Confirmed*: a maintainer label or fix, or two oracles agreeing where no open issue covers it. *Stopping rule*, fixed beforehand: a GPU-hour budget and input cap; everything inside is reported, zero included.

Secondary: gate precision, repairs merged, false-alarm rate with the gate off. Dry window: seeded bugs — a demo, not a result.

**Demo.** `chia job submit` runs generate → oracle → reduce → triage → repair → gate on one pinned image.

## Relation to CHIA's existing loop

| Stage | CHIA | Added |
|---|---|---|
| Supply | open issues | generator agent |
| Oracle | `repro.sh` | crash, `circt-lec`, `circt-bmc`, Verilator |
| Minimize | none | `circt-reduce` + oracle |
| Repair | full phase chain | reused unchanged |
| Decide | skip `not_a_bug` | gate on executed evidence |
| Image | `firtool-1.148.0` | + z3, Verilator, `lit` |

## Prior art

SynthFuzz (ICSE 2025), operation-dependency MLIR fuzzing (ISSTA 2024), LLM-driven MLIR fuzzing (2025), `drom/circt-fuzzer`, and historical firtool-vs-Scala-FIRRTL differential testing. Maintainers act: 15 CIRCT issues mention "fuzz", 13 closed. The claim is the closed loop as reusable CHIA blocks.

## Non-goals

Not a benchmark. Not Track 1 design bugs in BOOM — the target is the compiler.

## Limitations

`circt-lec` is combinational and rejects some HW constructs, so the differential oracle covers a subset of emitted IR; `circt-bmc` is bounded. Generated inputs may be invalid FIRRTL rather than bugs, hence triage. Maintainer confirmation sits outside our compute budget, so the headline metric lags.

## Appendix A — Claims to sources

| Claim | Source |
|---|---|
| 101 open `bug` issues, median age 890 days, 17 in last year | GitHub search API, 2026-09-11 (provided, task brief) |
| 0 CIRCT issues match "miscompil"; 15 mention "fuzz", 13 closed | GitHub search API, 2026-09-11 (provided, task brief) |
| AXI4 21 commits/90 d vs 3 lit files; ESI 88 vs 18; FIRRTL 86 vs 213 | Executed on local blobless clone: `git log --since=90.days --name-only ... -- lib/` and `git ls-tree -r --name-only HEAD test/Dialect`, 2026-09-11 |
| `firtool` `-O=<value>` with `=debug` "Compile with only necessary optimizations", `=release` "Compile with optimizations"; `--disable-opt` "Disable optimizations" | `firtool --help`, SDK `firtool-1.157.0` |
| `--preserve-aggregate` values `none`, `1d-vec`, `vec`, `all`; `--ir-hw`, `--verilog` | `firtool --help`, same SDK |
| `circt-lec` flags `--c1=<module name>`, `--c2=<module name>`, `--run`, `--shared-libs` | `circt-lec --help` |
| `circt-lec` prints `c1 == c2` / `c1 != c2`, **rc=0 in both cases**; rc=1 on legalize error | Executed: equivalent pair, unequal pair, and `hw.wire` legalize failure, 2026-09-11 |
| `circt-lec` rejects `hw.wire`: "failed to legalize operation 'hw.wire' that was explicitly marked illegal" | Executed on `firtool -O=debug --ir-hw` output |
| Differential pair executed green: `--preserve-aggregate=none` vs `=all` → `c1 == c2` | Executed, SDK binaries + `libz3.so.4` |
| `circt-bmc` flags `-b <clock cycle count>`, `--module=<module name>`, `--run`, `--shared-libs`, `--rising-clocks-only` | `circt-bmc --help` |
| `circt-lec`/`circt-bmc` need Z3; docs state `--shared-libs=<path-to-libz3.so.4>` | `docs/Tools/circt-lec.md`, `docs/Tools/circt-bmc.md` at clone HEAD |
| `circt-reduce --test=<string>` "A command or script to check if output is interesting"; also `--test-must-fail`, `--include`/`--exclude` | `circt-reduce --help` |
| `circt-reduce` refuses to run without `--test`: "for the --test option: must be specified at least once!" | Executed |
| Reduction executed: 67 lines → 7, "Final size: 143 (93% reduction)", `@Target` renamed `@Foo` | Executed, 2026-09-11 |
| SDK binaries present: `firtool`, `circt-lec`, `circt-bmc`, `circt-reduce`, `circt-test`, `circt-verilog`, `arcilator`, `circt-opt`, `FileCheck` | `ls /home/adi/.cache/chia-pin-smoke/circt-sdk/bin/` |
| SDK ships no `lit`; needs `libz3.so.4`; assertions OFF | `pin-window-analysis.md` §5.2 |
| 187 candidates, 171 (91.4%) exact SDK, 0 beyond one bump, 38 images | `pin-window-analysis.md` §4 |
| 1,027/1,027 targets in 939 s at a historical parent; red→green flip executed | `pin-window-analysis.md` §5.3–5.4 |
| One bump off fails at tblgen | `pin-window-analysis.md` §5.5 |
| CHIA phases assess→reproduce→fix→verify→regression repair→writeup; repro contract "exit 0 when fixed" | `examples/circt_issue_solver/README.md` |
| Image pinned `firtool-1.148.0`; lit gate "not `check-circt` (its integration tests need verilator/z3/sby, absent here)" | same README |
| `chia job submit`; `--backend` / `--model <id>` | same README |
| CHIA samples open issues with a code-block repro | same README |
| `drom/circt-fuzzer` "Generator of random circuits", JS, 6 stars, pushed 2026-03-31 | provided, task brief |
| SynthFuzz (ICSE 2025); ISSTA 2024 operation-dependency MLIR fuzzing; 2025 LLM-driven MLIR fuzzing; firtool vs Scala FIRRTL differential testing | provided, task brief |
| Abstain-and-Validate, arXiv 2510.03217 | provided, task brief |
| LLVM AI Tool Policy: disclosure + human in the loop, applies to bug reports and PRs | https://llvm.org/docs/AIToolPolicy.html (provided, task brief) |
| Verilator available at v5.052 on the probe host | `verilator --version` |

## Appendix B — Not verified

- No end-to-end run of the full loop has been executed; stages were verified individually.
- No bug has been discovered by this loop yet. The differential oracle has been exercised only on hand-written designs, both arms, with no genuine divergence found.
- `circt-bmc --run` was not executed; only its flags and docs were read. Whether the SDK's `circt-bmc` JITs correctly against the shimmed `libz3.so.4` is untested.
- Verilator was not driven against `firtool --verilog` output here; only its presence and version were checked. It is absent from CHIA's image.
- The generator agent does not exist. The churn-to-coverage numbers show the signal is measurable, not that an agent exploits it well.
- The gate's feature set is proposed, not fitted; no threshold, calibration data, or precision figure exists yet.
- "Blast radius" has no scalar definition yet.
- Bugs-per-GPU-hour has no prior estimate. The discovery rate for this generator on this compiler is unknown, which is why the stopping rule is a fixed budget and zero is a reportable outcome.
- Whether CIRCT maintainers will accept machine-generated reduced test cases at any volume is unknown; the 13 closed "fuzz" issues are evidence of past receptiveness, not of consent to a stream.
- Lit file counts are per-dialect file counts under `test/Dialect`, not coverage measurements; a dialect may be tested elsewhere in the tree.
- The 90-day churn counts come from `lib/Dialect/*` and `lib/Conversion/*` path prefixes on first-parent history at clone HEAD; they were not cross-checked against release notes.

## Appendix C — The one question

**What does the agent add over an existing fuzzer + `circt-reduce` + a shell script?**

Targeting and judgment, at the two ends where a script has nothing to offer: the middle — oracles and shrinker — is exactly a shell script, and we say so. At the front, a random generator has no reason to prefer AXI4 (21 commits, 3 test files) over FIRRTL (86 commits, 213 test files), while the agent reads the diffs and the coverage gap and aims the budget — the difference between finding a regression and re-finding known-good paths. At the back, `circt-reduce` yields a minimal case but cannot say whether it is a real bug, an invalid input, or an already-open issue, nor write the report a maintainer reads; the gate then decides, from executed evidence, whether a human sees it at all.
