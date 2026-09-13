# Doubt: one evidence gate, two policies — escalate, or abstain

**A reusable CHIA block that scores its own patch from execution evidence, escalates from a local `Qwen/Qwen3.8-27B` to `gemini-3.1-pro-preview` only when unsure, and withholds the pull request when it is *still* unsure — fitted and measured on 171 real CIRCT bugs that replay in one command.**

---

## 1. Task overview

CHIA's CIRCT case study solved the hard part — a loop that assesses, reproduces, fixes and verifies real `llvm/circt` issues — and exposed two costs nobody has optimized. Every issue is attempted by the same expensive model regardless of difficulty — **$0.40 + $0.68 + $3.01 + $0.09 = $4.18 of tokens** for an issue that traverses all four phases (CHIA Table 6) — and every patch goes to a human, at an hour of review plus ten minutes of PR preparation. Resolve-rate measures neither. A loop that fixes nine bugs and asks a maintainer to audit nine patches is worse than one that fixes six and asks for two.

Both costs are one missing primitive: **the loop has no calibrated notion of its own doubt.** We build it once and wire it to two policies. **Escalate:** run every task on a locally-served open model; spend frontier API only where the gate flags. **Abstain:** if the gate is still unsure after escalation, withhold the PR and emit the evidence bundle instead.

## 2. Methodology

**The loop.** Doubt is not a logprob, and not a model asked "are you confident?". It is a vector the harness *executes*: does the repro fail at the parent revision, does the patch flip exactly that test, does the suite stay green, how large is the blast radius. A logistic gate over those features is fitted on a calibration split, its reliability diagram published *before* the held-out set is touched — if it is uncalibrated, both policies collapse to "always escalate", and we report that. Cost-aware cascading is a known pattern; new here is a gate built from compiler evidence, not model self-report, driving two decisions at once.

**The instrument.** Over 24 months of `llvm/circt` first-parent history, **1,103** commits touch ≤2 files under `lib/`/`include/` while adding or modifying a test; **187** carry bug-vocabulary subjects. CHIA's `ChiaCirctBaseDockerfile` already unpacks a `firtool-*` release's prebuilt `libLLVM*`/`libMLIR*` instead of compiling LLVM, but pins source to the release tag. We generalize that line into a **per-pin-window image family**, and verified it: **171 of 187 (91.4%)** candidates have a release whose `llvm` pin exactly matches the pin at the bug's parent, **none is more than one bump away**, and **38 images cover all 171** — releases (median 7.0 d) outpace LLVM bumps (median 10.4 d). Then we built it: at a parent 18 commits and 11 days past the tag, `ninja -j6 circt-opt` finished 1,027/1,027 in 939 s, and the bug's test was red at the parent, green 13 s later. One bump off, the same SDK dies at build target 2 of 1,030 — loudly, and for free.

**Evaluation and contamination.** Mined history is contaminated by construction. Post-cutoff hold-out is undefined — neither `Qwen3.8-27B` nor Gemini 3.1 Pro publishes a cutoff — and fresh authoring at DeepSWE's 113-task scale takes a company. We take DeepSWE's *principle*, not its scale: grade behavior you execute, never a reference patch, which is what CHIA's loop already does. So the mined 171 are the **calibration split only**. Contamination inflates resolve-rate; it cannot inflate the gate's features, because "the suite stayed green" is computed by running the compiler, not recalled. The gate is validated where leakage is impossible — **mutation-injected bugs on today's HEAD** and **live open CIRCT issues** judged by fail→pass plus maintainer acceptance — with a contamination probe reported as a measurement, not a defense.

## 3. Expected results

**Committed headline: frontier-API spend per accepted CIRCT fix falls ≥ 3× against the same loop with the gate forced to "always escalate", under identical accounting** — the saving comes from the routing decision, not from a cheaper model, and local GPU-seconds are reported alongside. External reference from CHIA's own run: 16 issues assessed, 7 reproduced, 5 fixed (Table 5) at the Table 6 stage costs is roughly $27–$67 of tokens for 5 fixes, i.e. **$5–$13 per fixed bug**, depending on whether the per-stage averages are read over issues reaching that stage or over all 16. Secondary: share of accepted fixes that never left the local GPU (target ≥ 60%); maintainer-minutes per accepted fix against CHIA's 60 + 10; the gate's reliability diagram.

**Demo.** `chia job submit` replays one results row live: the local 27B attempts the bug, the gate fires on a thin repro, the task escalates to `gemini-3.1-pro-preview`, red→green on screen. Then the row it *abstained* on, reason readable.

**Secondary deliverable.** `examples/circt_issue_solver/README.md` says "the rest of the flow still assumes CIRCT". We lift the repo-specific parts into a four-method adapter — build, test-select, repro-contract, regression-gate — making the gate repo-agnostic, CIRCT the reference implementation. No second EDA target; breadth would cost the measurement its meaning.

**Non-goals.** No feature requests, multi-file refactors, finetuning, or leaderboard. Live CIRCT PRs reported only if one clears human review in time.

**Why not already done.** LLVM-Bench (arXiv 2607.00700, 423 tasks), HWE-Bench (2604.14709, 417) and Phoenix-bench (2605.15226, 511) hold the loop fixed and rank models by resolve-rate; none targets a hardware-compiler source tree, and none makes *which model to spend, and whether to ask a human at all*, a decision the loop makes. CHIA invites exactly this: "Building these benchmark suites on top of CHIA would streamline the process of comparing different design loops, and we are interested in integrating these suites into CHIA."

**Tracks.** "Reusable CHIA blocks for agentic design workflows that run on NVIDIA-accelerated infrastructure and can be reused after the hackathon." And "Submitting your own ideas is also welcome!"

**Cost.** *[placeholder — GPU hours + Gemini credits, from the pilot's measured per-task rate.]*

---
---

# Appendix — Author verification notes

Every factual claim in the body, with its source. Anything the team cannot defend from this table should be cut before submission.

## Claims verified by direct measurement in this session

| # | Claim in body | How verified | Evidence |
|---|---|---|---|
| 1 | 1,103 shape-filtered candidates; 187 with bug-vocabulary subjects, 24 months | `pin_window.py` over `llvm/circt` first-parent history, HEAD `d7e94049bde3`, 2026-09-11 | `pin-window-analysis.md` §4; `pin_window_results.txt` |
| 2 | **171/187 = 91.4%** have an exact prebuilt-LLVM pin match at the bug's parent | same | §4 |
| 3 | **0 of 187** are more than one LLVM bump away | same | §4 |
| 4 | **38 images** cover the 171 exact-match tasks | same (distinct pin windows spanned) | §4 |
| 5 | firtool release cadence median **7.0 d**; LLVM bump cadence median **10.4 d** | same (90 tags / 62 bumps in window) | §3 |
| 6 | Configure **10 s**; `ninja -j6 circt-opt` **1,027/1,027 in 939 s** at parent `5056ff04450b` | executed; log retained | §5.3–5.4 |
| 7 | Parent commit is **18 commits / 11 days past** `firtool-1.157.0` | `git rev-list`/tag date | §5.3 |
| 8 | Test **red at parent, green after fix, 13 s** incremental rebuild | executed `circt-opt \| FileCheck` on `test/Conversion/HWToLLVM/convert_aggregates.mlir` for bug `f2b15a44ec70` | §5.4 |
| 9 | One bump off **fails at target 2/1030**; one bump = **1,237** llvm-project commits | executed; GitHub compare API on `llvm/llvm-project` | §5.5 |
| 10 | CHIA's `ChiaCirctBaseDockerfile` unpacks prebuilt `libLLVM*`/`libMLIR*` and pins source to the release tag | read the whole file | <https://raw.githubusercontent.com/ucb-bar/chia/main/dockerfiles/ChiaCirctBaseDockerfile> — `ARG CIRCT_VER=firtool-1.148.0`; `git clone --depth 1 --branch "${CIRCT_VER}"` |

## Claims verified against primary sources

| # | Claim in body | Source |
|---|---|---|
| 11 | **$4.18/issue** — *derived*: it is the **sum** of CHIA Table 6's per-phase costs (Assess 0.40 + Reproduce 0.68 + Fix 3.01 + Writeup 0.09). The string "$4.18" does **not** appear in the paper. Always show the sum. | <https://arxiv.org/html/2606.27350v3>, Table 6, "Average LLM token usage and cost for each agent stage in our issue fixing loop." |
| 12 | Human review cost — verbatim: "It took a graduate student with novice-level familiarity with CIRCT **an hour per issue** to review the agents' changes … It took **about 10 more minutes per issue** to prepare the pull requests." ~70 min is the **sum**, not a printed figure. | same, §5.5 |
| 13 | "Building these benchmark suites on top of CHIA would streamline the process of comparing different design loops, and we are interested in integrating these suites into CHIA." | same, related work |
| 14 | "the rest of the flow still assumes CIRCT" | <https://github.com/ucb-bar/chia/blob/main/examples/circt_issue_solver/README.md> |
| 15 | "Reusable CHIA blocks for agentic design workflows that run on NVIDIA-accelerated infrastructure and can be reused after the hackathon." and "Submitting your own ideas is also welcome!" | <https://agentic-arch.org/hackathon.html> |
| 16 | Prize criterion "the most novel, creative agentic loop(s)" | same |
| 17 | `chia job submit` exists (`chia job` proxies to `ray job`) | <https://docs.chialoops.ai/en/latest/user_guides/reference.html> |
| 18 | LLVM-Bench = 423 tasks (arXiv 2607.00700); HWE-Bench = 417 (2604.14709); Phoenix-bench = 511 (2605.15226) | the three abstracts |
| 19 | `Qwen/Qwen3.8-27B` is Apache-2.0, dense 27B; model card reports SWE-bench **Pro** 61.7, Terminal-Bench 2.1 73.0, **DeepSWE 1.1 42.2** | <https://huggingface.co/Qwen/Qwen3.8-27B> (README read directly) |
| 20 | Qwen publishes **no** training cutoff for `Qwen3.8-27B` | same — no cutoff field anywhere in the card |
| 21 | `gemini-3.1-pro-preview` is the current flagship Pro id | <https://ai.google.dev/gemini-api/docs/models> |
| 22 | Gemini 3.1 Pro's model card states **no explicit knowledge cutoff**; reports SWE-bench Verified 80.6, SWE-bench Pro (Public) 54.2, Terminal-Bench 2.0 68.5; **does not report DeepSWE** | <https://deepmind.google/models/model-cards/gemini-3-1-pro/> |
| 23 | DeepSWE = 113 original tasks, 91 repos, 5 languages; "every task is authored from scratch and never merged upstream, so its reference solution is absent from the public commit and pull-request record"; verifiers "test observable software behavior rather than implementation details" | <https://arxiv.org/abs/2607.07946>, <https://deepswe.datacurve.ai/blog/deepswe> |
| 24 | The verifier-disagreement audit: an independent judge disagreed with the **SWE-Bench Pro** verifier on "67 (false-positive) and 189 (false-negative) of 789 rollouts, 32.4% overall" vs "2 and 8 of 735 rollouts, or 1.4% overall" for DeepSWE | arXiv 2607.07946 (HTML) |
| 25 | CHIA's CIRCT loop ran on 16 issues, fixed 5, submitted and merged 3 PRs | arXiv 2606.27350 §5.5 |

## Traps — do not write these

- **Do not compare `Qwen3.8-27B`'s SWE-bench Pro 61.7 with Gemini 3.1 Pro's 54.2.** Different harnesses; Qwen's was run under a Claude Code harness with "problematic tasks corrected and all baseline models re-evaluated". Quoting them side by side is a fabricated comparison.
- **Do not write "SWE-bench Verified" next to any Qwen3.8-27B number** — Qwen does not publish one.
- **Do not write "$4.18" or "~70 minutes" as quotations.** Both are sums the authors computed (see #11, #12). Show the addition.
- **Do not claim DeepSWE is "the standard."** It is *rising*: it appears in `Qwen3.8-27B`'s own launch model card (42.2) and ranks #6 in a 2026 roundup that puts SWE-bench #1, Terminal-Bench #2 and SWE-bench Pro #3, and Google's Gemini 3.1 Pro card does not report it at all. Claim its *principle*, not its status.
- **Do not present the prebuilt-SDK trick as novel.** It is CHIA's own; the extension is the per-pin-window family and the empirical pin-coverage measurement.
- **Do not say "SWE-bench-Lite-scale."** Lite is 300 test instances.
- **Do not mention SpinalHDL.** It emits HDL from its own backend; zero CIRCT involvement.
- **Do not bill an OpenAI model to Google credits.** The proposal has no OpenAI dependency.

## Not verified / open

- Whether the 187 subject-filtered commits are *genuinely* bug fixes — the keyword filter is a proxy and **no diffs were read**. Both 187 and 1,103 are reported for that reason. The pilot must hand-validate a sample.
- What fraction of the 171 exact-match tasks actually satisfy fail→pass. **One** was verified end to end (`f2b15a44ec70`). The rest are unvalidated.
- The ≥ 3× target is a commitment, not a measurement. The paper's per-stage costs are averages whose denominator (issues reaching the stage vs all 16) is not stated, hence the $5–$13 range; the always-escalate ablation removes that ambiguity.
- Whether `vLLM` serves `Qwen3.8-27B` at a pinned version — the model card names vLLM, but no 27B-specific recipe page was found. Pin and test before relying on it.
- Every build number here was measured on one host (20 cores, ~6 GB free RAM, `-j6`, clang 23.0.0git, glibc 2.44, cold ccache), **not** in CHIA's Ubuntu 24.04 image.
- No published judging rubric exists for the hackathon.

---

# Mapping to the 4-page final paper

1. **Motivation (¾ page).** Resolve-rate is the wrong objective for a maintainer-facing repair loop; the two real costs are dollars per accepted fix and maintainer minutes per accepted fix, both quantified from CHIA's own CIRCT case study ($0.40+$0.68+$3.01+$0.09 per full-pipeline issue; 60 min + 10 min review). Frame the missing primitive as calibrated doubt.
2. **The gate (1 page — the paper's core).** Feature set drawn from execution evidence; the fitting procedure; the reliability diagram on the calibration split; the two policies (escalate, abstain) derived from one threshold sweep; the block's CHIA interface and how it composes into any repair loop.
3. **The instrument (¾ page).** Mining shape; the pin-window measurement (1,103/187 candidates, 91.4% exact coverage, 0 beyond one bump, 38 images, 7.0 d vs 10.4 d cadence); the per-pin-window image family as a parameterization of `ChiaCirctBaseDockerfile`; the one-bump failure at target 2/1030 as evidence that exact pairing is the only viable construction.
4. **Evaluation (1 page).** Calibration on mined history; validation on mutation-injected HEAD bugs and live open issues; the contamination probe as a reported measurement; the DeepSWE principle (execute behavior, never match a reference patch) and the honest reason a fresh-authored corpus was out of reach; ablations — gate off, always-escalate, always-local.
5. **Results (½ page).** Frontier spend per accepted fix vs the always-escalate ablation (and vs the paper-derived $5–$13); share of accepted fixes never leaving the local GPU; maintainer-minutes per accepted fix vs ~70; the failure modes, including any regime where the gate degenerates.
6. **Limitations and artifact (¼ page).** Single repo; keyword-proxy mining; unpublished model cutoffs; one-host build timings; and the released artifact — the gate block, the adapter, the image family, and `chia job submit` reproduction for every row.
