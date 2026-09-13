# Red team — `problem-statement-B-v3.md`

Hostile review, 2026-09-11. No fixes, no praise. Where an attack category yielded nothing, it says
"no flaw found".

Primary evidence: live execution of the CIRCT SDK at `/home/adi/.cache/chia-pin-smoke/circt-sdk/bin`;
a **completed 605/605 `-UNDEBUG` CIRCT build** (`scratchpad/bassert`, this session); re-derivation of the
187/171 corpus from `pin_window_raw.json`; GitHub search API (executed today); `tools/firtool/firtool.cpp`
and `tools/arcilator/arcilator.cpp` in the blobless clone at HEAD `d7e94049b`; the `circt_issue_solver`
README fetched raw today; arXiv 2605.10074 / 2504.01379 / 2507.19275 / 2510.03217 / 2603.20075 / 2510.07815;
ICSE 2026 SEIP page; `circt/arc-tests` README.

---

## 1. Ranked attacks

### KILLS

---

#### K1. The demo runs on an image this project has already measured as unbuildable.

> "**Demo.** `chia job submit` runs generate → oracle → reduce → triage → repair → gate on a
> HEAD-tracking image (fetch-by-SHA) with `-UNDEBUG`, z3, Verilator, `lit`."
> and, in the Gate: "Reproduces at `main`"

`pin-window-analysis.md` §5.5 built current `main` HEAD `d7e94049bde3` against the `firtool-1.157.0`
SDK and it **failed at build target 2 / 1030**, 1,237 llvm-project commits apart, with cmake configure
passing first so nothing catches it early. Re-derived from `pin_window_raw.json` today: **no `firtool-*`
tag carries HEAD's LLVM pin `e297b52ec9d8…`**, so today there is no release SDK that builds `main` at all.
Appendix B concedes "The HEAD-tracking image has not been built" but not that the same document *measured
that exact pairing failing* — and the only escape is compiling LLVM, which §6 of that document forbids
("Nothing in the loop ever compiles LLVM").

---

#### K2. The seed corpus and the oracle are aimed at different parts of the compiler. 94% of the seeds are invisible to the differential.

> "(ii) *Two implementations.* `arcilator` on `firtool --ir-hw` against Verilator on `firtool --verilog`,
> same stimulus"
> "**Generator (agent).** Per seed (one of the 187 mined fixes) the agent reads the diff and test, states
> the root-cause class, names sibling sites"

`tools/firtool/firtool.cpp:507–530` (read today): both output modes run the FIRRTL parser, every FIRRTL
pass and `populateLowFIRRTLToHW`; `--verilog` differs only by `populateHWToSV` + `populateExportVerilog`.
Two back ends, one shared front and middle end. Re-deriving the 187 from `pin_window_raw.json` with the
stated keyword filter (reproduces 187 and 171 exactly), by the file each fix touches:

| region | n | visible to the differential? |
|---|---|---|
| `Dialect/FIRRTL` (42), `Conversion/FIRRTLToHW` (1), `Firtool/Firtool.cpp` (1) | 44 | no — shared by both arms |
| `Dialect/HW` 3, `Comb` 8, `Seq` 2 | 13 | mostly shared |
| `Conversion/ExportVerilog` 5, `SeqToSV` 1, `Dialect/SV` 1 | 7 | yes |
| `Dialect/Arc` 3, `Conversion/ArcToLLVM` 1 | 4 | yes |
| `ImportVerilog` 31, `MooreToCore` 12, `Moore` 5, `LLHD` 12, `Synth` 9, `ESI` 5, `RTG` 4, Calyx/Handshake/AIG/BTOR2/… | **118** | **unreachable — a `.fir` input never executes this code** |

**11 of 187 seeds (5.9%)** lie in the region the differential can discriminate. **118 (63%)** are in code the
loop's own entry point cannot reach. B-W2 was not escaped; it was reworded into a stronger version of itself.

---

#### K3. The headline oracle already ships inside the CIRCT project, on real designs, and is uncited.

> "**B-W2** differential's discriminating region is thin | Addressed by construction: the primary
> differential is now two separate implementations" (Appendix D)

`circt/arc-tests` — a repo in the `circt` GitHub organisation, the Arcilator team's own benchmark harness —
states verbatim: "**Lockstep Arcilator and Verilator simulation. Aborts as soon as the simulations diverge.**"
It runs on Rocket Chip and BOOM and ships a VCD-differ for the hierarchy-name mismatch. v3's version of the
same oracle was executed once on a 12-line design. The A³ PC includes CHIA's authors, i.e. the people who
built it. Prior art is cited for AFuzz, DESIL, Mut4All and CodeRover-S but not for the one oracle v3 executed.

---

#### K4. "Observed vs expected" and "no claim about which divergence arm is right" are in the same document.

> §2: "an agent then dedups, classifies, and writes an issue-shaped report: reduced `.mlir`, command,
> **observed vs expected**."
> Non-goals: "**no claim about which divergence arm is right**."

You cannot fill in "expected" while disclaiming which arm is correct. Worse, `tools/arcilator/arcilator.cpp:1`
describes itself verbatim as "**An experimental circuit simulator**", and `llvm/circt` carries 26 open / 49
total arcilator issues (queried today). A divergence against an experimental simulator, with the adjudication
rule explicitly declared out of scope, is not a filable report — it is a ticket that says "these two disagree,
you figure out which".

---

#### K5. The motivating supply number is wrong in the body, correct in the appendix, and 5x off.

> §1: "101 open `bug` issues, median age 911 days, **17 filed last year**."
> Appendix A: "17 **open** `bug` issues created since 2025-09-11"

Queried today, `repo:llvm/circt is:issue label:bug created:>2025-09-11`, **all states = 82**. Eighty-two bug
reports were filed; 17 are the ones still open. The body converts a survivorship-filtered residue into a
filing rate, and the load-bearing scarcity claim ("Supply is whatever maintainers file") is off by ~5x.
The 101/911 pair points the other way too: a 911-day median on an open backlog is evidence that *maintainer
attention*, not bug supply, is the binding constraint — which is an argument against manufacturing more
reports. Limitations half-notices this ("Whether CIRCT maintainers will accept machine-generated reduced
test cases at any volume is unknown") without letting it touch §1.

---

#### K6. The novel component is another paper's method, does not exist, and the deadline is 13 days.

> "AFuzz (2605.10074) **is the method**: the agent analyses a reference bug's root cause, hypothesises new
> scenarios sharing it elsewhere, and verifies each with generated PoCs"
> Appendix B: "**The generator agent does not exist.** That an agent can turn a fix diff into productive
> sibling hypotheses on *CIRCT* is assumed from AFuzz's V8 result, not measured here."

Against a prize for "the most novel, creative agentic loop(s)", the statement concedes its generator is
someone else's published method, unbuilt, and unvalidated on this target. AFuzz ran "for about one month"
on V8 for 40 bugs; the final submission is Sep 24 (13 days). And AFuzz's own abstract scopes agentic
fuzzing to **logic** bugs — "Fuzzers and static analyzers find many bugs but struggle with logic bugs …
Triggering such a bug often requires multi-step reasoning that produces no distinctive execution feedback" —
while v3 scopes *repair* to "crashes and assertions: expected behaviour is unambiguous" and makes
divergences report-only. The agent is pointed at the class where a crash oracle already gives feedback,
and demoted to report-only in the class where AFuzz says the agent matters.

Missing from Prior art, all findable in one search: **FLEX** (ASE 2025, arXiv 2510.07815) — 80 previously
unknown MLIR bugs in a 30-day campaign, 53 in 24 h, "over 3.5x the best baseline", no agent; **Nüwa**
(ICSME 2025, LLM-driven MLIR fuzzing); `drom/circt-fuzzer`. FLEX is worse than uncited — it dissolves the
premise, because a non-agentic adaptive generator already makes MLIR bug supply a function of compute,
and it sets an external bar (80/30 days) beside which v3's unstated budget will look small.

---

### WOUNDS

**W1. The "pre-registered budget" has no number, no registry and no registrar.**
> "**Headline: distinct, maintainer-confirmed bugs within a pre-registered budget** — GPU-hours and a
> generated-input cap, fixed before the run."

No GPU-hour figure, no cap, no statement of where it is registered or by whom, and the paper is the first
public artifact (Sep 24), so "pre-registered" is unverifiable by construction. Limitations then says
"Maintainer confirmation lags the budget" — so the headline metric's numerator cannot be reported on the
day it is due. B-K4 survives intact; only the self-grading disjunct was removed.

**W2. "Reused, with a local-report entry point" is not one change.**
> Table: "| Repair | assess→…→writeup phase chain | **reused, with a local-report entry point** |"

README, fetched today: triage is a read-only `GithubIssuesNode` sampling **open** issues that "carry a
code-block repro … and have no open PR attached"; persistence is `issue_logs/issue_<N>/` plus
`verdict.json` and "a row in `issues.db`"; the skip-triage path is `--issue 10568`; `GITHUB_TOKEN` is
required; `writeup` produces "the PR description it *would* submit"; and "**No GitHub writes — both flows
only read.**" v3's gate *files* reports (a write), needs a duplicate search over open **and closed**
issues (CHIA's triage searches neither), and needs a different terminal artifact (an issue report, not a
PR description). That is a new supply node, an ID-minting scheme for the log/DB keys, a new writeup
prompt, and a dedup capability CHIA does not have — described as "the one change" in front of the people
who wrote it.

**W3. The repair stage is contractually barred from the crash oracle's most likely root cause.**
README: "**Root cause in LLVM/MLIR (the prebuilt SDK / `llvm` submodule) is out of scope** — only CIRCT's
own tree is buildable here". v3's oracle (i) is "CIRCT asserts **and segfaults**". A segfault reached from
generated IR frequently lands in MLIR. v3 scopes the *assert* half correctly ("SDK LLVM/MLIR assertions
stay off") and says nothing about the segfault half.

**W4. Neither harness generator exists, and the statement says so in two different places without joining them.**
> "Arcilator's harness is `arc.sim.*` MLIR **generated from the port list**."

Appendix A: the SDK "does **not** ship `arcilator-header-cpp.py`", and the shipped
`circt-test-runner-verilator.py` "drives `verilator --cc --exe --main --timing` against a generated
`testbench.sv` with a `.clock/.init/.done/.success` port convention" — a convention a generated FIRRTL
design will not satisfy. Both harnesses in the executed probe were hand-written
(`probe/harness2.mlir`, `probe/tb.sv`). The differential needs two generators that agree on stimulus,
reset protocol and sampling point; neither is named as work.

**W5. The executed differential compares one byte.**
Re-run today from `probe/`: `tiny.fir` is 12 lines, `acc <= a + b`, no feedback; stimulus is the
**constant** pair `a=7, b=200` held for all four cycles; one 8-bit output port is sampled. Both arms print
`o = cf` four times because the design produces `0xcf` and nothing else can happen. Signals compared: 1.
Distinct values compared: 1. Random stimulus: none. Reset: none. The body's "on a 12-line FIRRTL
register-add both printed `o = cf` for four cycles" is accurate and is worth nothing as oracle evidence.

**W6. No UB or X-semantics policy, while citing the paper whose contribution is exactly that.**
DESIL is cited; its method is "UB-elimination rules based on the MLIR documentation". v3 adopts none, and
the executed probe pins neither Verilator's `--x-initial` nor `--x-assign`. *Honest note:* I built two
probes designed to break the arms apart — a register read before any clock edge, and an out-of-range
dynamic vector index — and **both arms agreed** (`00`/`2a`; firtool pads the array so index 3 returns
element 0 in both). So this is an unstated-policy gap, not a demonstrated false-positive rate.

**W7. The one hard measurement was taken under the flags the proposal replaces, on the tool the oracle does not use.**
> "One built 1,027/1,027 targets in 939 s at a historical parent, red→green."

That build is `-DNDEBUG` and covers `circt-opt`'s dependency closure only — which is exactly what CHIA's
Dockerfile bakes ("Bake circt-opt (and its full dependency closure)"). The oracle drives `firtool`,
`arcilator`, `circt-reduce`, plus Verilator, z3 and `lit`. Build time and image size for that target set
are unmeasured. (My own `-UNDEBUG` build was 605 targets for `circt-opt` alone.)

**W8. "Contamination-free" covers the instance and not the seed.**
> "Discovered bug *instances* are new, so discovery is contamination-free"

The 187 seeds are public `llvm/circt` commits with public fixes, inside the generator's training window.
A "sibling hypothesis" that reproduces a later public fix is memorisation, not discovery. The statement
handles the repair executor's contamination and skips the generator's.

**W9. Dedup and gate precision exist only in the appendix of things not done.**
> §3: "Dedup, planned: assertion text plus `file:line`; segfault frames via the SDK's `llvm-symbolizer`;
> reduced cases by structural hash…"

Appendix B: "None has been executed on real duplicate pairs, and no collision rate is known" and "Gate
precision has no fitted threshold or calibration data." Gate precision is never defined in the body at all;
its only appearance in the document is as an absence. B-W8 was rewritten, not retired.

**W10. Two Appendix A rows cite published papers to a private file.**
"ISSTA 2024 operation-dependency MLIR fuzzer found 63 bugs | `red-team-AB.md` §B4" and
"Abstain-and-Validate … as spot-checked in `red-team-AB.md` §A4". Both numbers are correct (I verified
them independently), but a reviewer is being pointed at a document they cannot open, for two of the four
external anchors the evaluation section rests on.

**W11. A dead oracle is still in the loop spec.**
§2 lists "(iii) A `circt-lec` self-differential, third only"; Limitations says "Oracle (iii) is inoperable".
Shipping a component in the architecture and killing it four paragraphs later reads as a spec nobody pruned.

**W12. After `-UNDEBUG`, the standard assertions check still reports OFF.**
Measured on my completed build: `bin/circt-opt --version` prints "Optimized build." — not "with assertions"
— because the version string reads `LLVM_ENABLE_ASSERTIONS` out of the SDK's `llvm-config.h`, not CIRCT's
`NDEBUG`. Every report this loop files will misdescribe the build it was produced on unless the loop says so.

---

### NITs

- **N1.** Subtitle: "seeds an agent with **187 pin-verified** CIRCT fix commits". Only **171** have an exact
  prebuilt-LLVM pin; the other 16 are one bump away, and §5.5 measured one bump as a hard build failure at
  target 2/1030. "Pin-verified" is also not "verified to be bug fixes" — `pin-window-analysis.md` §4:
  "**Neither number has been validated by reading the diffs**."
- **N2.** "Churn is secondary." An orphan clause left behind by B-W7's removal; it defends a signal the
  document no longer uses.
- **N3.** Mut4All is cited for its mutator counts (319/403) but not its yield (62 Rust, 34 C++ bugs) — the
  omitted number is the one a PC uses to price the "a mutator seeded with the same diffs" baseline.
- **N4.** "DESIL found 42 MLIR-core bugs" sums the paper's "23 silent bugs and 19 crash bugs"; the paper
  reports them separately with 12/14 confirmed or fixed.
- **N5.** "a named human approves each" — no name, no rate, no volume cap, in a design whose headline
  metric is a count of filings and whose Limitations identify maintainer goodwill as the binding constraint.
- **N6.** Appendix B still opens with "The generator agent does not exist." Correct and admirable; also the
  first thing an AI-persona reviewer scoring completeness will quote.
- **N7.** No "first", no "novel", no buzzwords, no placeholders; body is 751 words. **No flaw found** on
  rhetoric proper — the problems are in the claims, not the prose.

---

## 2. Escape table — `red-team-AB.md` §2 attacks on B

| Attack | Verdict | One line |
|---|---|---|
| **B-K1** dead `--preserve-aggregate` axis, self-comparison | **escaped** | Axis dropped; oracle replaced by two implementations and executed. (The replacement carries K2/K3/K4 above, but the original attack is answered.) |
| **B-K2** "`circt_issue_solver` unchanged" false; `assess` logs `unclear` | **reworded** | The `unclear` half is genuinely escaped by scoping repair to crashes/asserts; the "one change" half survives — README shows `GithubIssuesNode`, `issue_logs/issue_<N>`, `issues.db`, `verdict.json`, `--issue <N>`, a PR-description writeup and "No GitHub writes". |
| **B-K3** "0 issues match miscompil" search artifact | **escaped** | Four real counts; all four re-verified today (2 / 2 / 13 / 14). |
| **B-K4** self-graded "confirmed"; self-set denominator | **reworded** | Numerator fixed (maintainer only). Denominator is still team-set, has no number, and Limitations still concede confirmation "lags the budget". |
| **B-K5** AFuzz/DESIL/Mut4All/CodeRover-S uncited | **reworded** | All four now cited and accurately described — at the cost of the sentence "AFuzz … **is the method**". New misses: FLEX (80 MLIR bugs/30 d), Nüwa, `circt/arc-tests`. |
| **B-W1** "normalized wire-free" names no mechanism | **escaped** | Conceded in Limitations: the pass does not ship, oracle (iii) inoperable. |
| **B-W2** discriminating region is thin | **still present** | `firtool.cpp:507–530`: both arms share the FIRRTL pipeline and `LowFIRRTLToHW`; 11/187 seeds are discriminable, 118/187 are unreachable. |
| **B-W3** the 93% reduction was `grep`-driven | **escaped** | Number removed from body; Appendix A discloses `grep -q 'comb.mul'`. |
| **B-W4** crash oracle needs assertions the SDK lacks | **escaped, and verified further** | I completed the build the statement did not: 605/605, `circt-opt` linked, 247/264 objects carry `__assert_fail`, lit subset 520/523. See spot-check 2. |
| **B-W5** stale image; dedup misses upstream-fixed bugs | **still present, worse** | "HEAD-tracking image" is the pairing §5.5 measured failing at target 2/1030; no tag shares HEAD's LLVM pin today. |
| **B-W6** blast radius undefined | **escaped** | Removed from the gate. |
| **B-W7** churn/test-file ratio justifies nothing | **escaped** | Replaced by the 187 seeds; only the stranded clause "Churn is secondary." remains. |
| **B-W8** structural dedup evidenced by one rename | **reworded** | Now an operational rule, labelled planned; Appendix B: "None has been executed on real duplicate pairs, and no collision rate is known." |
| **B-N1** "Pitch." label | **escaped** | Removed. |
| **B-N2** "Not Track 1…" | **escaped** | Removed. |
| **B-N3** AI-policy sentence with no mechanism | **escaped** | Replaced by disclosure line + named human approver (the approver is now N5). |
| **B-N4** "the generator agent does not exist" | **still present** | Verbatim in Appendix B. Deliberate, and still the sentence a completeness-scoring reviewer quotes. |
| **B-N5** "contamination is moot" | **reworded** | Repair contamination now stated correctly; seed contamination introduced and unaddressed (W8). |
| **B-N6** scare-quoted tool stdout | **escaped** | Gone. |
| **B-N7** "seeded bugs — a demo, not a result" | **escaped** | Now "Seeded-bug runs validate the pipeline's stages, reported separately." |

**Tally: escaped 12 · reworded 5 · still present 3.**

---

## 3. Mechanical spot-checks

| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | arcilator-vs-Verilator "both arms printed the same output" | **PASS as executed / FAIL as evidence** | Re-ran both arms today. `arcilator tiny_arc.mlir --run --jit-entry=main` → `o = cf` ×4, rc=0; `./vbuild/vtb` → `o = cf` ×4, rc=0, Verilator 5.052. What was compared: **1 output port, 8 bits, 1 distinct value, 4 samples**. Stimulus is **constant** (`a=8'd7, b=8'd200` fixed in both harnesses), no reset, no randomness; `tiny.fir` is 12 lines and its register has no feedback, so `0xcf` is the only value it can ever hold. Both harnesses are hand-written. |
| 2a | "583/583 CIRCT object rules compile `-DNDEBUG`, zero `__assert_fail`" | **PASS (stronger than claimed)** | `build.ninja`: 610 `CXX` `*.cpp.o` build lines, **583** whose output path matches `CIRCT`, 578 under `obj.CIRCT*`; `compile_commands.json`: 578/578 carry `-DNDEBUG`, 0 carry `-UNDEBUG`. `nm -u` over **all 513** built CIRCT objects: **0** reference `__assert_fail` (Appendix A only claims this for `CombOps.cpp.o`). `CMakeCache.txt`: `CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -DNDEBUG` alongside `LLVM_ENABLE_ASSERTIONS:UNINITIALIZED=ON`. |
| 2b | "`-UNDEBUG` fixes it" — is the fix as stated? | **PASS, and I completed the build the statement did not run** | `scratchpad/bassert`: `CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -UNDEBUG`, 578/578 obj.CIRCT entries `-UNDEBUG`, 0 `-DNDEBUG`. `ninja -j8 circt-opt` → **605/605 targets, 0 errors, `bin/circt-opt` linked**. `nm -u` over 264 built objects: **247** reference `__assert_fail`; the linked binary does too. `lit` over `test/Dialect/{FIRRTL,HW,Comb,Seq}` + `test/Conversion`: **520/523 pass**; all 3 failures trace to lit falling back to the SDK's 11-day-stale `circt-translate` (`type identifier 'Registry' is not declared`), not to `-UNDEBUG`. |
| 2c | ABI mismatch from mixing NDEBUG modes against an assertions-OFF SDK | **no flaw found — hypothesis refuted** | The SDK's generated `include/llvm/Config/abi-breaking.h` hard-codes `#define LLVM_ENABLE_ABI_BREAKING_CHECKS 0`, so every NDEBUG-sensitive *layout* member in LLVM/MLIR is gated on a macro `-UNDEBUG` does not touch (111 header uses of `LLVM_ENABLE_ABI_BREAKING_CHECKS` in the SDK). Compiled one TU against SDK headers twice and diffed `sizeof`/`alignof` for `mlir::Operation, Block, Region, Value, OpBuilder, RewriterBase, PatternRewriter, RewritePattern, Pass, OperationName, OperationState, Diagnostic, InFlightDiagnostic, FrozenRewritePatternSet, DialectRegistry, llvm::SmallVector, DenseMap, StringMap, SmallPtrSet, DenseMap::iterator` — **byte-identical**. `llvm::DebugFlag` / `isCurrentDebugType` are exported unconditionally by the SDK's `libLLVMSupport.so`, so `LLVM_DEBUG` links. Confirmed end-to-end by 2b. This was the prompt's candidate kill; it is not one. |
| 3 | Every GitHub count | **PASS on all appendix numbers, FAIL on one body paraphrase** | Executed today: open `label:bug` = **101**; median age over all 101 `created_at` vs 2026-09-11 = **911 d** (min 27, max 2002); open `label:bug created:>2025-09-11` = **17**; `miscompile` **2**; `miscompilation` **2**; `"wrong output"` **13**; `"wrong result"` **14**; `fuzz` **15**, `+is:closed` **13**. **FAIL:** the body's "17 filed last year" — `label:bug created:>2025-09-11` across **all states = 82**. |
| 4a | AFuzz described accurately, incl. "generalize root cause of reference bugs" | **PASS** | Abstract verbatim: "Given a reference bug, the agent analyzes its root cause, hypothesizes new scenarios elsewhere in the codebase that may share that cause, and verifies each hypothesis by generating and running proof-of-concept code." 40 V8 bugs (3 dup), $35,000, 2 CVEs; 19 in SpiderMonkey/JSC (1 dup) from V8 seeds; no repair component. Title "Agentic Fuzzing: Opportunities and Challenges", Park & Yun, 11 May 2026. v3's one-line description is faithful. |
| 4b | DESIL | **PASS** | "DESIL: Detecting Silent Bugs in MLIR Compiler Infrastructure"; UB-elimination rules + lowering-path optimization + differential testing; "23 silent bugs and 19 crash bugs, of which 12/14 have been confirmed or fixed"; CIRCT not mentioned; no repair. |
| 4c | Abstain-and-Validate | **PASS** | "Abstain and Validate: A Dual-LLM Policy for Reducing Noise in Agentic Program Repair"; bug abstention + patch validation; 174 human-reported bugs, +13/+15/+39 pp. v3's one-liner correct. |
| 4d | llvm-harness | **PASS** | "Agentic Harness for Real-World Compilers"; tool named `llvm-harness`; "Our current focus is on the middle end of LLVM"; 334 reproducible LLVM middle-end bugs, +62% / +22%. |
| 4e | Mut4All | **PASS** | Title exact; three agents (invention / implementation-synthesis / refinement); "319 Rust and 403 C++ mutators" from 1000 bug reports. (Yield 62 Rust + 34 C++ omitted by v3 — see N3.) |
| 4f | CodeRover-S | **PASS** | ICSE 2026 SEIP "Fixing Security Vulnerabilities with Agentic AI in OSS-Fuzz", AutoCodeRover adapted to security and named CodeRover-S; plausible patches for **33/45 = 73.3%** of real-world *unpatched* vulnerabilities (the SEIP abstract's "61% to 72%" is the separate 588-bug historical benchmark). v3's phrasing "unpatched vulnerabilities" is the right one. |
| 4g | ISSTA-2024 63 bugs | **PASS** | "Fuzzing MLIR Compiler Infrastructure via Operation Dependency Analysis", ISSTA 2024: 63 previously unknown bugs, 48 confirmed, 38 fixed. |
| 4h | Prior-art **completeness** | **FAIL** | Uncited and directly on the pitch: **FLEX** (ASE 2025, arXiv 2510.07815) — 80 previously unknown MLIR bugs in 30 days, 53 in 24 h, no agent; **Nüwa** (ICSME 2025, LLM-driven MLIR fuzzing); **`circt/arc-tests`** — "Lockstep Arcilator and Verilator simulation. Aborts as soon as the simulations diverge", on Rocket Chip and BOOM; `drom/circt-fuzzer`. |
| 5 | `pin-window-analysis.md` numbers quoted faithfully | **PASS except the subtitle** | Re-derived from `pin_window_raw.json` with the stated filter: 1,103 candidates, **187** filtered, **171** exact (91.4%) — exact match to the document. 0 beyond one bump, 38 images, 1,027/1,027 in 939 s, no `lit`, `libz3.so.4`, `LLVM_ENABLE_ASSERTIONS OFF` in the SDK's `LLVMConfig.cmake` (re-grepped: `set(LLVM_ENABLE_ASSERTIONS OFF)`) — all faithful. **FAIL:** the subtitle's "**187 pin-verified**" — 171 are pin-verified; the remaining 16 are one bump away, which §5.5 measured as a hard build failure. |
| — | CIRCT fuzzing infrastructure (does "lightly fuzzed target" hold?) | **holds** | Clone at HEAD `d7e94049b`: no `fuzz` directory, no `LLVMFuzzerTestOneInput`, no OSS-Fuzz config, and none of the 12 `.github/workflows` mentions fuzzing. **No flaw found** — the yield inference is the one part of §4 that survives scrutiny intact. |
| — | arcilator mature enough to be a reference? | **FAIL** | `tools/arcilator/arcilator.cpp:1` — "An **experimental** circuit simulator". No `docs/Tools/arcilator.md` exists (the directory documents circt-bmc, circt-lec, circt-synth, circt-verilog, handshake-runner). 26 open / 49 total arcilator issues on `llvm/circt`. `lib/Dialect/Arc/Transforms/LowerState.cpp` emits "latencies > 1 not supported yet" in two places. |

---

## 4. Verdict

**Would the A³ PC rank this in the top 3? No. Confidence 70%.**

**Decisive reason.** The panel contains the people who wrote Arcilator. They read
"`arcilator` on `firtool --ir-hw` against Verilator on `firtool --verilog`, same stimulus" and recognise
their own `arc-tests` lockstep harness — which runs the same two simulators against each other on Rocket
Chip and BOOM and aborts on divergence — then they look for the number and find one 8-bit constant on a
12-line design. A second reader with `firtool.cpp` open sees that both arms share the FIRRTL pipeline, so
the oracle is discriminating over `ExportVerilog` against an "experimental circuit simulator", which is
11 of the statement's own 187 seeds. Everything else the statement earns — and it earns a lot: the
`-UNDEBUG` finding is real, I rebuilt and linked it, and the appendix discipline is better than anything
else in this repo — is spent defending a discovery headline whose numerator ("maintainer-confirmed")
cannot exist by Sep 24 and whose demo image is measured unbuildable.

**The 30% on the other side.** It is visibly a *loop* — five stages CHIA does not have — against a prize
sentence that says "loop(s)". The reducer block, the differential-oracle block and the `-UNDEBUG` image
are three composable things the CHIA README says it lacks, and Appendix B is the most honest document a
PC will read that week. An AI-persona reviewer scoring evidence density and calibration may reward exactly
that.

**The single change that most raises the ceiling.** Demote discovery to the second half and make the
**image the contribution**: a CHIA block that turns `circt_issue_solver`'s silently-assertions-off image
into an assertions-on image at a caller-chosen commit — 583/583 `-DNDEBUG` → 605/605 built and linked with
`-UNDEBUG`, 0 → 247 objects carrying `__assert_fail`, lit still green — and then re-run CHIA's own §5.5
experiment (16 issues, 2 `no_repro`) on it and report how many verdicts move. That is measured, upstreamable,
composable, needs no maintainer confirmation, is testable against the authors' own published baseline, and
is finishable in 13 days. Keep the seeded generator, label it AFuzz-on-CIRCT explicitly, and let zero be
the reported outcome.

**The one question this statement cannot answer.**

> Your differential can only discriminate `ExportVerilog`/`HWToSV` against Arcilator's lowering — 11 of your
> own 187 seeds, with 118 of them in code a `.fir` input never executes. What is the other 94% of the seed
> corpus seeding? And name one bug class this finds that `circt/arc-tests` running Rocket and BOOM in
> lockstep does not.
