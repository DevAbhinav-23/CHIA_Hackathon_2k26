# Final check — `problem-statement-FINAL.md`

Executed 2026-09-11/12. Bounded scope: mechanical verification, escape check vs `red-team-v3.md`, new kills only.

---

## 1. Mechanical checks

| # | Check | Verdict | Evidence |
|---|---|---|---|
| 1 | GitHub counts 82 / 65 / 17 | **PASS** | Search API today: `repo:llvm/circt is:issue label:bug created:>2025-09-11` = **82**, `+is:closed` = **65**, `+is:open` = **17** |
| 1 | 101 open `bug`; median age **911** d | **PASS** | `is:open label:bug` = **101**; median over all 101 `created_at` vs 2026-09-11 = **911** d (min 27, max 2002) |
| 1 | 2 / 2 / 13 / 14 | **PASS** | `miscompile` 2, `miscompilation` 2, `"wrong output"` 13, `"wrong result"` 14 |
| 1 | 15 / 13 fuzz-mentioning | **PASS** | `fuzz` 15, `+is:closed` 13 (Appendix B's "13 closed fuzz-mentioning issues") |
| 2 | LLVM pin: HEAD vs `firtool-1.159.0` | **PASS** | `git fetch origin main` → HEAD **`b792c772819df723628d1fe6073269b85a8ade5d`** (exactly the SHA the FINAL names), `ls-tree` pin **`e297b52ec9d8b5c38042e53ae5650922717970cd`**. `firtool-1.159.0` and `-1.158.0` both pin **`6279700538792da0c5a08e17babfe9b6e824c69f`**. Swept all **164** `firtool-*` tags: **none** carries `e297b52…`. `firtool-1.159.0` published 2026-09-09 is the newest release. Statement still true. |
| 3 | Seed distribution | **PASS** | Re-derived from `pin_window_raw.json` with §2's regex, first `src` entry: FIRRTL **37**, ImportVerilog **31**, `include/circt/Dialect` **16**, MooreToCore **12**, LLHD **11**, Comb **7**, Synth **7**, ExportVerilog **5**, CoreToFSM **5**, ESI **5**, HWToBTOR2 **4**, RTG **4**, OM **3**, Moore **3**, tail. Exact match, all 14 buckets. |
| 3 | 187 / 171 (91.4%) / 0 beyond one bump / 38 images | **PASS** | Same re-derivation: filtered **187**, exact **171**, bumps>1 **0**, distinct windows among exact **38** |
| 3 | "~60 FIRRTL→HW→SV, ~127 unreachable" | **PASS (approximate)** | Reconstructs to **57–65 reachable / 122–130 unreachable** depending on how the 16 `include/circt/Dialect` seeds are split. `~` covers it; see nit 3. |
| — | §3 window stats: 47/63 (74.6%), 2,909/3,257 (89.3%), 7.0 d, 10.38 d | **PASS** | Quoted faithfully from `analysis/pin-window-analysis.md` §3; 63 windows / 47 tagged re-derived from the raw JSON |
| — | §5 build numbers: 1,027/1,027 in 939 s, configure 10 s, 13 s incremental, 18 commits / 11 days, target 2/1030, 10 dialects, 1,237 llvm commits | **PASS** | All match `analysis/pin-window-analysis.md` §5.3–5.5 verbatim |
| — | **§2/App-A: "649/649 CIRCT object rules compile `-DNDEBUG`"** | **FAIL** | Reference build `/home/adi/.cache/chia-pin-smoke/src/build`: `build.ninja` has **620** `.o` rules, **583** with `CIRCT` in the output path, **578** under `obj.CIRCT*`; `compile_commands.json` 620 entries, **620/620** carry `-DNDEBUG`, 0 carry `-UNDEBUG`. **649 is not derivable from any artifact in this project** (checked both build trees and all repo `.md`s — 649 appears only in the FINAL). Correct number: **583/583**. |
| — | "0 `__assert_fail` in `circt-opt`" | **PASS** | `nm -u` over all **513** built `obj.CIRCT` objects: **0**; `nm -u bin/circt-opt`: **0** |
| — | **§2/App-A: "247/264 objects carry `__assert_fail`"** | **FAIL** | Re-ran `nm -u` over the completed `-UNDEBUG` build (`scratchpad/bassert`, 605/605): **495 of 513** `obj.CIRCT` objects reference `__assert_fail`. 264 matches no subtree (lib/Dialect 410, lib/Conversion 54, lib/Support 21, lib/Transforms 11, lib/Analysis 7, lib/Tools 5, lib/Scheduling 5; tools 8). `red-team-v3.md`'s 247/264 was a mid-build snapshot; the FINAL inherited it and under-reports its own result. Correct: **495/513**. |
| — | "605/605 targets link" | **PASS** | `bassert_build.log` ends `[605/605] Linking CXX executable bin/circt-opt` |
| — | `circt-opt --version` prints "Optimized build." after `-UNDEBUG` | **PASS** | Executed on `bassert/bin/circt-opt`: `LLVM version 24.0.0git / Optimized build. / CIRCT 5056ff0` |
| — | SDK: `llvm-symbolizer`, `FileCheck`, `not`, `count`, `split-file`; **no** `lit`/`llvm-lit`; needs `libz3.so.4`; no `arcilator-header-cpp.py`; `circt-test-runner-verilator.py` drives `verilator --cc --exe --main --timing` with `.clock/.init/.done/.success` | **PASS** | `ls`/`find` over the extracted SDK; read of the runner (lines 52–53, 78–82) |
| — | `circt-reduce` refuses without `--test` | **PASS** | Executed: `circt-reduce: for the --test option: must be specified at least once!` |
| — | No in-tree fuzzing; **12** workflows, none mentions fuzzing | **PASS** | At HEAD `b792c772`: 0 `fuzz` paths, 0 `LLVMFuzzerTestOneInput`, no OSS-Fuzz/ClusterFuzz config, `.github/workflows` = **12** files, `grep -ril fuzz` = **0** |
| — | `arcilator.cpp` line 1 | **PASS** | `//===- arcilator.cpp - An experimental circuit simulator ------------------===//` |
| 4 | 2605.10074 AFuzz | **PASS** | "Agentic Fuzzing: Opportunities and Challenges", Park & Yun, 11 May 2026. Quote byte-verbatim. "for about one month, finding 40 bugs (including three duplicates)" ✓; "19 bugs (including one duplicate) in SpiderMonkey and JavaScriptCore using the seeds from V8" ✓; abstract scopes to logic bugs ✓ |
| 4 | 2510.07815 FLEX | **PASS** | Title + author list (Sun, Liang, Wang, Suo, Chen, Xu) ✓; "80 … 53 bugs (over 3.5x as many as the best baseline) … 28.2% code coverage" byte-verbatim; **ASE 2025** confirmed (conf.researchr.org ASE 2025 Research Papers) |
| 4 | 2504.01379 DESIL | **PASS** | Title ✓; "UB-elimination rules based on the MLIR documentation" ✓; "23 silent bugs and 19 crash bugs, of which 12/14 have been confirmed or fixed" ✓; CIRCT not mentioned ✓ |
| 4 | 2507.19275 Mut4All | **PASS** | Title ✓; "yielding 319 Rust and 403 C++ mutators" byte-verbatim; "finds 62 bugs in Rust compilers (38 new, 7 fixed) and 34 bugs in C++ compilers (16 new, 1 fixed)" byte-verbatim; three agents / 1000 bug reports ✓ |
| 4 | 2510.03217 Abstain-and-Validate | **PASS** | Title ✓; "up to 39 percentage points in combination" ✓; 13/15 pp individually ✓; 174 human-reported bugs + NPEs + sanitizer-reported ✓; ICSE-SEIP '26 ✓ (arXiv comment field) |
| 4 | 2603.20075 llvm-harness | **PASS** | "Agentic Harness for Real-World Compilers"; "designed to assist LLM agents in understanding and fixing compiler bugs" ✓; "Our current focus is on the middle end of LLVM" ✓; `llvm-bench` 334 reproducible bugs ✓; +62% / +22% ✓ |
| 4 | Nüwa (ICSME 2025, IEEE doc 11185938) | **PASS** | ICSME 2025 research-track abstract, final two sentences verbatim: "…detecting 2.9x more unique bugs and achieving 1.6x greater code coverage. To date, Nüwa has identified 55 bugs in the MLIR framework, with 18 confirmed or fixed." |
| 4 | ISSTA-2024 / MLIRod, DOI `10.1145/3650212.3680360` | **PASS** | 63 previously unknown bugs, 38 fixed / 48 confirmed ✓; MLIRSmith named as the grammar-based predecessor ✓ |
| 4 | CodeRover-S, DOI `10.1145/3786583.3786880` | **PASS** | 588 real-world vulnerabilities, repairs **52.4%** ✓; plausible patches for **73.3%** of unpatched (45-vuln set) ✓. (This corrects `red-team-v3.md` 4f, which read 52.4% as absent; the 61–72% figure is the separate historical OSS-Fuzz benchmark and the FINAL correctly does not use it.) |
| 5 | CHIA README quotes (9 rows) | **PASS** | Raw README fetched today. Verbatim modulo line-wrap whitespace: triage sampling sentence; `--issue 10568`; `issue_logs/issue_<N>/ (…)` + `issues.db`; "assess → reproduce → fix → verify → (regression repair) → writeup"; "the PR description it *would* submit"; "**No GitHub writes — both flows only read.**"; "Root cause in LLVM/MLIR (the prebuilt SDK / `llvm` submodule) is out of scope — only CIRCT's own tree is buildable here"; "deterministic, no LLM: rebuild, rerun repro, run the full lit gate"; "The chia-circt image is pinned at **firtool-1.148.0**"; "`--model <id>` overrides the model of whichever backend is selected". Two formatting deltas, no content delta: README italicises *exit 0 iff fixed* (FINAL bolds `iff`), and `--backend <name>` is the FINAL's own rendering of the README's `--backend` / `--backend antigravity` / `--backend opencode`. |
| 5 | `circt/arc-tests` | **PASS** | Raw README: "Lockstep Arcilator and Verilator simulation. Aborts as soon as the simulations diverge." — byte-verbatim. Repo API: org `circt`, **39** stars, pushed **2026-01-26**, description exact. Rocket Chip + BOOM + `diffvcd.py` ✓ |
| 6 | Body word count (title → Limitations, pipes stripped) | **735 words** | (was 751 at v3) |
| 7 | "first" / "novel" / uncertainty tags / placeholders / cost section / reviewer-management sentence | **PASS — none present** | Zero occurrences of `first`, `novel`, TODO/TBD/XXX/placeholder, `[UNVERIFIED]`, `$`, any GPU-hour figure, or any sentence about managing reviewers. Body names a budget *shape* ("GPU-hours, input cap, filing cap") with no number — deliberate, and Appendix B discloses the file does not exist. |
| 7 | "CHIA's image" claims vs Appendix B | **PASS — disclosed** | Three image claims: pitch ("assertions CHIA's image compiles out"), §2 ("Under CHIA's flags…"), table row ("`firtool-1.148.0`, assertions off"). Appendix B states plainly: "**The assertion finding was measured on a local build reproducing CHIA's cmake flags, not inside CHIA's published image**, which was never built or inspected", plus the causal-attribution row. §2 is correctly hedged ("under CHIA's flags"); the pitch line is the only one that reads as direct measurement, and B covers it. |

---

## 2. Escape check vs `red-team-v3.md`

| Item | Verdict | One line |
|---|---|---|
| **K1** demo on an image measured unbuildable | **escaped by design** | Body now runs on "release-pinned main: the newest `main` commit whose LLVM pin has a release SDK"; HEAD-tracking is gone and the failure is stated ("HEAD's pin has none; one bump off is a hard tblgen failure"). Re-verified: no `firtool-*` tag carries HEAD's pin. |
| **K2** seeds vs oracle mismatch (94% invisible) | **escaped by design** | Differential demoted to "Secondary, FIRRTL/HW only"; primary oracle is crash/assertion, which is language-agnostic; "Input language follows the seed" + "About 127 of 187 seeds are unreachable from `.fir`" puts the attack's own number in the body. |
| **K3** `arc-tests` uncited | **escaped** | Body: "reusing `circt/arc-tests`'s lockstep driver"; Prior art names it; Appendix A carries the verbatim quote and repo metadata. |
| **K4** "observed vs expected" vs "no claim which arm is right" | **escaped** | "observed vs expected" is gone; replaced by "Expected behaviour is agreement". The replacement clause introduces a new overclaim — see wound 1. |
| **K5** "17 filed last year" 5x off | **escaped** | §1 now reads 82 filed / 65 closed / 101 open / 911 d, and concludes "Attention, not supply, binds" — the direction the attack pointed. All four re-verified today. |
| **K6** generator is another paper's unbuilt method; FLEX/Nüwa uncited | **reworded** | FLEX, Nüwa, MLIRSmith, ISSTA-2024, `arc-tests`, `circt-fuzzer` all now cited with correct numbers; "AFuzz is the method's origin" is stated openly and Limitations concedes the generator is unwritten. Exposure disclosed, not removed — by choice. |
| **W1** budget has no number/registry/registrar | **reworded** | Registrar now exists ("pre-committed to the public loop repo; that commit is the registration") and Appendix B says the file does not exist yet. Still no number. |
| **W2** "reused, with a local-report entry point" is not one change | **escaped** | 7-row table, 6 rows "added", 1 "reused unchanged"; ID scheme, dedup and gated write all itemised. |
| **W3** repair barred from MLIR root cause (segfault half) | **escaped** | "MLIR/LLVM-core assertions stay off; a segfault rooted there is report-only (CHIA: 'out of scope')". |
| **W4** neither harness generator exists | **escaped** | Limitations + Appendix B both state it; the SDK gaps are named. |
| **W5** executed differential compares one byte | **escaped** | Appendix A states the probe's exact scope and adds "Cited only as evidence that the pipeline runs end to end on a toy — never as oracle evidence"; the body no longer cites it. |
| **W6** no UB / X-semantics policy | **still present** | Body has no X or UB policy; Appendix A only records that Verilator's `--x-initial` / `--x-assign` exist. And the body now asserts a stronger claim on top of the gap — wound 1. |
| **W7** hard measurement under the replaced flags | **escaped** | Limitations: "The one full build (1,027 targets, 939 s) was `-DNDEBUG`, `circt-opt` only"; Appendix B adds the unbuilt target set. |
| **W8** contamination covers instance, not seed | **escaped** | §3 Contamination paragraph addresses seed memorisation directly and keeps the repair-executor caveat. |
| **W9** dedup / gate precision only in the appendix | **escaped** | Gate precision is defined in the body ("maintainer-accepted reports / reports filed"); dedup rules are in §3 marked "(planned)". |
| **W10** papers cited to a private file | **still present (different rows)** | ISSTA-2024 and Abstain-and-Validate now cite the papers. But three Appendix A rows (`-UNDEBUG` build, ABI/`sizeof` check, `--version` string) cite `red-team-v3.md` — again a file a reviewer cannot open. |
| **W11** dead `circt-lec` oracle still in the spec | **escaped** | Gone from the body; Appendix B: "`circt-lec` was evaluated and dropped from the design; no claim rests on it." |
| **W12** `--version` still reports OFF | **escaped** | Body: "Reports name the `-UNDEBUG` build: `circt-opt --version` prints 'Optimized build.'" Re-measured today; true. |
| **N1** "187 pin-verified" | **escaped** | Subtitle: "187 mined CIRCT fix commits, 171 with an exact prebuilt SDK". |
| **N2** stranded "Churn is secondary." | **escaped** | Removed. |
| **N3** Mut4All yield omitted | **escaped** | Appendix A now quotes 62 Rust / 34 C++. |
| **N4** DESIL 42 summed | **escaped** | Body: "DESIL 23 silent + 19 crash". |
| **N5** "a named human approves each" | **reworded** | "named team member approves, per-day cap" — cap added, name still absent (correct: the name is the team's, not the document's). |
| **N6** "The generator agent does not exist." | **still present** | Verbatim in Appendix B. Deliberate. |
| **N7** rhetoric clean | **escaped / still clean** | No "first", no "novel", no placeholders, no uncertainty tags. 751 → **735** words. |

**Tally: escaped 19 · reworded 3 · still present 3.**

---

## 3. New KILLS

Three body sentences fail the test "false, unsupported by its cited source, or internally contradicted".

**KILL-1. "649/649 rules" is a number that does not exist.**
> §2: "Under CHIA's flags every CIRCT object compiles `-DNDEBUG` — **649/649 rules**, no `__assert_fail` in `circt-opt`."

The reference build has **583** CIRCT object rules (620 `.o` rules total, 578 under `obj.CIRCT*`). 649 appears in no build artifact, no log, and no other file in the project. Appendix A attributes it to "Reference build parsed from `build.ninja` / `compile_commands.json`" — parsing those gives 583, 578 or 620, never 649. A PC member cannot check this, but the claim is false and it is the load-bearing number of the paper's headline instrument finding.

**KILL-2. "247/264 objects carry `__assert_fail`" under-reports the completed build by half.**
> §2: "`-UNDEBUG` restores assertions: 605/605 targets link, **247/264** objects carry `__assert_fail`."

Re-run on the completed build: **495 of 513** `obj.CIRCT` objects. 264 corresponds to no subtree of that build; it is a mid-build snapshot inherited from `red-team-v3.md` spot-check 2b. The direction of the error is self-harming — the real result is stronger — but the sentence is false as written and the FINAL is the document of record.

**KILL-3. "Lag is one release at most" is an absolute bound supported only by a median, and the source data falsifies it.**
> §3: "Lag is one release at most (**median cadence 7.0 days**)."

`pin_window_raw.json`: of 63 pin windows, 16 carry no release. The worst is **window 254 (2026-01-13 → 2026-01-30): 100 commits, 16.09 days with no matching release**, and there is one run of two consecutive untagged windows. During such a stretch release-pinned main trails HEAD by 100 commits / 16 days — more than two median release cadences. "At most" is not established by a median, and the max in the cited corpus is 2.3x it. `analysis/pin-window-analysis.md` §3 reports only the untagged-window *median* (14 commits / 3.3 d), so the bound is also unsupported by the cited source.

---

## 4. Wounds / nits (5, most important first)

1. **W6 survived, and the body raised the stakes on it.** "Expected behaviour is agreement; **either arm's divergence is a CIRCT bug**, so report-only." Verilator is not CIRCT: a Verilator bug, or a legitimate X-initialisation difference between the two simulators, produces a divergence that is not a CIRCT bug. The document fixes no X or UB policy anywhere in the body (Appendix A only notes that `--x-initial` / `--x-assign` exist), and `red-team-v3.md` W6 found both arms agreeing on its two X probes only by accident of padding. An A³ PC member who owns Arcilator reads that clause first.
2. **Three Appendix A rows still cite `red-team-v3.md`** — the `-UNDEBUG` build, the 20-type ABI `sizeof`/`alignof` check, and the `--version` finding. These are the document's three strongest original measurements and they are sourced to a file no reviewer can open. Fixing KILL-1/2 is the natural moment to re-source them to the build tree.
3. **"~60 … ~127" is not reproducible to the digit.** Re-derivation gives 57–65 reachable / 122–130 unreachable depending on where the 16 `include/circt/Dialect` seeds land (they split FIRRTL 5, Moore 2, Synth 2, and one each of DC/OM/Comb/HW/Arc/SV/LLHD). The Appendix A method line says "bucketed by the first `lib/`-or-`include/` path" but does not say how `include/` seeds are assigned to the FIRRTL path. The body's "About" carries it; one clause would make it checkable.
4. **The cited source's own denominator drifts.** `analysis/pin-window-analysis.md` §3 reports 3,251 first-parent commits in the window but 2,909/**3,257** for the 89.3%. The FINAL quotes 2,909/3,257 faithfully, so this is the source's defect, not the FINAL's — but it is the one number in §3 a reviewer with the appendix open could find inconsistent.
5. **Two cosmetic quote defects in Appendix A.** The persistence row opens a parenthesis it never closes ("… `verdict.json`, per-phase `llm_*.md` + the raw session transcript"), and `--backend <name>` is presented among verbatim README items though the README spells it `--backend`, `--backend antigravity`, `--backend opencode`.

---

## 5. Verdict

**Needs 3 edits** (touching 6 lines). Everything else — 40+ mechanical checks, every quote, every arXiv pair, every corpus number — passes.

**Edit 1 — `649/649` → `583/583`**, three places:
- §2, line 13: `— 649/649 rules, no ` → `— 583/583 rules, no `
- Appendix A: `Under those flags **649/649** CIRCT object rules` → `Under those flags **583/583** CIRCT object rules`
- Appendix D §3: `(649/649, 605/605, 247/264, lit 520/523)` → `(583/583, 605/605, 495/513, lit 520/523)`

**Edit 2 — `247/264` → `495/513`**, two remaining places:
- §2, line 13: `605/605 targets link, 247/264 objects carry` → `605/605 targets link, 495/513 objects carry`
- Appendix A: `**605/605** targets, `circt-opt` links, **247/264** objects reference` → `**605/605** targets, `circt-opt` links, **495/513** objects reference`
- (Same row: change the source cell `Completed `-UNDEBUG` build, `red-team-v3.md` spot-check 2b` → `Completed `-UNDEBUG` build (`nm -u` over all 513 built `obj.CIRCT` objects); lit subset per `red-team-v3.md` spot-check 2b` — this also retires wound 2 for that row.)

**Edit 3 — the lag bound**, one place:
- §3: `Lag is one release at most (median cadence 7.0 days);` → `Lag is one pin window — 16 of 63 carry no release, worst 100 commits / 16 d (median release cadence 7.0 days);`

Optional, recommended (wound 1, one clause):
- §2: `either arm's divergence is a CIRCT bug, so report-only.` → `a divergence is a candidate, not an adjudicated CIRCT bug — no X/UB policy is fixed yet — so report-only.`

With Edits 1–3 applied, **ready to hand over**.
