# Evidence, not confidence: a model-agnostic repair harness for CHIA

**A CHIA repair harness whose retry/submit/abstain decision comes from executed compiler evidence, not model self-report: the executor is a parameter, and the maintainer reads an evidence bundle, not a diff.**

---

## 1. Task overview

CHIA's CIRCT loop — assess → reproduce → fix → verify → regression-repair → writeup — examined 16 issues, fixed 5, merged 3 PRs. The paper prints its dominant cost: "an hour per issue" of expert review plus "about 10 more minutes per issue" preparing PRs. Resolve-rate measures neither. A loop handing over nine patches to audit is worse than one handing over two.

The missing primitive is a runtime decision: **is this patch worth a human's hour?** Six blocks answer it around CHIA's phases, none depending on which model drives. Executor is a config line; harness is the contribution.

## 2. Methodology

**Harness** — six blocks, each upstreamable alone:

1. **Repro contract.** No model tokens until the harness holds a test failing at the bug's parent revision: precondition, not output.
2. **Evidence gate.** The doubt vector is executed, not asked: repro fails at parent; patch flips exactly that test; suite stays green; blast radius. Logistic over those features emits retry/submit/abstain. Calibrated abstention is not new; first here for compiler repair, from execution evidence, inside CHIA, with a measured review-time effect.
3. **Regression gate with blast radius.** Which lit tests, dialects and headers a patch moves: input to gate and human.
4. **Evidence bundle.** Repro script, failing test, localization, regression delta, on submit *and* abstain. It shortens the accept/reject decision; it does not replace the human who owns the PR under LLVM's AI Tool Policy.
5. **Pin-window image family.** Of 187 bug-fix-shaped `llvm/circt` commits, **171 (91.4%)** have a `firtool-*` release whose LLVM pin exactly matches the bug's parent pin, **none more than one bump away**, **38 images cover all 171**. At a parent 18 commits past its tag: `ninja -j6 circt-opt` built **1,027/1,027 in 939 s**; test red→green in 13 s; one bump off, the SDK dies at target 2/1,030. The family is a ~3-line diff to CHIA's `ChiaCirctBaseDockerfile`: `CIRCT_VER` re-pinned, clone-by-tag → fetch-by-parent-SHA.
6. **Adapter interface.** build / test-select / repro-contract / regression-gate: the four methods that must move, given `circt_issue_solver`'s "the rest of the flow still assumes CIRCT".

**Executors and calibration order.** Two, co-equal, same harness: `gemini-3.1-pro-preview` (API) and `Qwen/Qwen3.8-27B` (local, CHIA's `VLLMDockerfile`; no 27B-specific vLLM recipe published [UNVERIFIED]). No fallback tier. The gate is fitted on the **stronger executor first** (calibration needs positives), then applied **unchanged** to the other. On-prem is a harness property, not a thesis.

**Evaluation and contamination.** Mined history is contaminated by construction; a post-cutoff hold-out is undefinable, as neither Qwen nor Gemini 3.1 Pro publishes a cutoff. We take DeepSWE's principle, not its scale: grade behaviour you execute, never a reference patch. The mined 171 are therefore the **calibration split only**; validation is **live open CIRCT issues**, whose count we do not control. Contamination inflates resolve-rate, not an executed suite-green signal. Mutation-injected HEAD bugs are a harness smoke test only.

## 3. Expected results

**Maintainer-minutes per accepted fix**, against CHIA's 60 + 10. Protocol fixed in advance: agent patches with bundle interleaved with baseline patches (same loop, gate and bundle off), blinded reviewer, per-patch minutes, ≥2 reviewers, ideally one external CIRCT contributor.

**Gate precision across two executors.** Of patches the gate passes: fraction passing ground truth (mined split) or accepted by reviewers (live split), per executor, plus the **transfer result** — the gate fitted on the stronger executor, applied unchanged to the local one. Abstention *recall* only with its caveat: on mined tasks "fixable" may be memorized. Precision is unaffected. The reliability diagram ships before the hold-out is touched; an uncalibrated gate collapses to always-submit.

**Demo.** `chia job submit` replays one row: repro contract holds, executor patches, gate fires → abstain, reason on screen. A second row → submit with bundle, red→green.

**Secondary deliverable.** Lifting the CIRCT-specific parts into those four methods drops gate, bundle and repro contract into any CHIA repair loop. No second EDA target; breadth would cost the measurement its meaning.

**Non-goals.** No feature requests, multi-file refactors, finetuning, leaderboard. Live CIRCT PRs only if one clears review in time.

**Why not already done.** LLVM-Bench (423 tasks), HWE-Bench (417) and Phoenix-bench (511) hold the loop fixed and rank models by resolve-rate; none targets a hardware-compiler source tree, none makes *whether to bother a human* a runtime decision. CHIA invites this: "Building these benchmark suites on top of CHIA would streamline the process of comparing different design loops, and we are interested in integrating these suites into CHIA."

**Tracks.** "Reusable CHIA blocks for agentic design workflows that run on NVIDIA-accelerated infrastructure and can be reused after the hackathon." And "Submitting your own ideas is also welcome!"

**Cost.** *[placeholder: GPU hours + Gemini credits, measured in the pilot.]*

---
---

# Appendix A — Author verification notes

Every factual claim in the body, with its source. Anything the team cannot defend from this table should be cut before submission.

## Claims verified by direct measurement in this session

| # | Claim in body | How verified | Evidence |
|---|---|---|---|
| 1 | 187 bug-fix-shaped `llvm/circt` commits (24 months; ≤2 files under `lib/`/`include/`, adds/modifies a test, bug-vocabulary subject); 1,103 on file-shape alone | `pin_window.py` over `llvm/circt` first-parent history, HEAD `d7e94049bde3`, 2026-09-11 | `pin-window-analysis.md` §4; `pin_window_results.txt` |
| 2 | **171/187 = 91.4%** have an exact prebuilt-LLVM pin match at the bug's parent | same | §4 |
| 3 | **0 of 187** are more than one LLVM bump away | same | §4 |
| 4 | **38 images** cover the 171 exact-match tasks | same (distinct pin windows spanned) | §4 |
| 5 | `ninja -j6 circt-opt` built **1,027/1,027 in 939 s** at parent `5056ff04450b` (configure 10 s) | executed; log retained | §5.3–5.4 |
| 6 | Parent commit is **18 commits / 11 days past** `firtool-1.157.0` | `git rev-list` / tag date | §5.3 |
| 7 | Test **red at parent, green after fix, 13 s** incremental rebuild | executed `circt-opt \| FileCheck` on `test/Conversion/HWToLLVM/convert_aggregates.mlir` for bug `f2b15a44ec70` | §5.4 |
| 8 | One bump off, the SDK **fails at target 2/1,030**, during TableGen, before any C++ object | executed; one bump = 1,237 llvm-project commits (GitHub compare API) | §5.5 |
| 9 | CHIA's `ChiaCirctBaseDockerfile` unpacks prebuilt `libLLVM*`/`libMLIR*` and pins source to the release tag — hence the ~3-line diff (`CIRCT_VER`, clone-by-tag → fetch-by-parent-SHA) | read the whole file | <https://raw.githubusercontent.com/ucb-bar/chia/main/dockerfiles/ChiaCirctBaseDockerfile> — `ARG CIRCT_VER=firtool-1.148.0`; `git clone --depth 1 --branch "${CIRCT_VER}"` |
| 10 | *(Not in body; operational, keep for the paper)* The SDK ships no `llvm-lit`, needs `libz3.so.4`, and its `include/circt` strip step is load-bearing — without it the build dies at 514/1027 (`use of undeclared identifier 'RegistryType'`) | tarball inventory (8,330 entries); executed both ways | §5.2, §5.4 |
| 11 | Release cadence median **7.0 d** vs LLVM bump cadence median **10.4 d** — the reason coverage is high *(not in body; motivates claim 2)* | same analysis (90 tags / 62 bumps in window) | §3 |

## Claims verified against primary sources

| # | Claim in body | Source |
|---|---|---|
| 12 | Human review cost — verbatim: "It took a graduate student with novice-level familiarity with CIRCT **an hour per issue** to review the agents' changes … It took **about 10 more minutes per issue** to prepare the pull requests." 60 + 10 is the **sum**, not a printed figure | <https://arxiv.org/html/2606.27350v3> §5.5 |
| 13 | CHIA's CIRCT loop: **16 issues examined, 5 fixed, 3 PRs submitted and merged** | same, §5.5 |
| 14 | Loop phases assess → reproduce → fix → verify → regression-repair → writeup | <https://github.com/ucb-bar/chia/blob/main/examples/circt_issue_solver/README.md> |
| 15 | "the rest of the flow still assumes CIRCT" (`config.py` pins `GITHUB_REPO = "llvm/circt"`) | same |
| 16 | "Building these benchmark suites on top of CHIA would streamline the process of comparing different design loops, and we are interested in integrating these suites into CHIA." | arXiv 2606.27350, related work |
| 17 | "Reusable CHIA blocks for agentic design workflows that run on NVIDIA-accelerated infrastructure and can be reused after the hackathon."; "Submitting your own ideas is also welcome!" | <https://agentic-arch.org/hackathon.html> |
| 18 | `chia job submit` exists (`chia job` proxies to `ray job`) | <https://docs.chialoops.ai/en/latest/user_guides/reference.html> |
| 19 | `dockerfiles/VLLMDockerfile` exists; takes `VLLM_MODEL` = any HF id; CUDA-first | <https://raw.githubusercontent.com/ucb-bar/chia/main/dockerfiles/VLLMDockerfile> |
| 20 | LLVM-Bench = 423 tasks (arXiv 2607.00700); HWE-Bench = 417 (2604.14709); Phoenix-bench = 511 (2605.15226); each holds the loop fixed and ranks models by resolve-rate | the three abstracts |
| 21 | `Qwen/Qwen3.8-27B` is the current Qwen open-weights id (Apache-2.0, dense 27B, Aug 2026) | <https://huggingface.co/Qwen/Qwen3.8-27B> |
| 22 | Qwen publishes **no** training cutoff for `Qwen3.8-27B` | same — no cutoff field anywhere in the card |
| 23 | `gemini-3.1-pro-preview` is the current flagship Pro id | <https://ai.google.dev/gemini-api/docs/models> |
| 24 | Gemini 3.1 Pro's model card states **no explicit knowledge cutoff** | <https://deepmind.google/models/model-cards/gemini-3-1-pro/> |
| 25 | DeepSWE's principle — "every task is authored from scratch and never merged upstream, so its reference solution is absent from the public commit and pull-request record"; verifiers "test observable software behavior rather than implementation details" | <https://arxiv.org/abs/2607.07946>, <https://deepswe.datacurve.ai/blog/deepswe> |
| 26 | LLVM's AI Tool Policy requires disclosure and a human in the loop, and bars AI on "good first issues" | <https://llvm.org/docs/AIToolPolicy.html> |

## Traps — do not write these

- **Do not write "$4.18" or "~70 minutes" as quotations.** Both are sums the authors computed: $0.40 + $0.68 + $3.01 + $0.09, and 60 + 10. v2 carries no dollar headline; if cost appears anywhere, show the addition.
- **Do not compare `Qwen3.8-27B`'s SWE-bench Pro 61.7 with Gemini 3.1 Pro's 54.2**, or quote any cross-harness score pair. Different harnesses; Qwen's ran under a Claude Code harness with baselines re-evaluated. v2 quotes **no** model benchmark score — the executors are parameters, not a comparison.
- **Do not write "SWE-bench Verified" next to any Qwen3.8-27B number** — Qwen publishes none.
- **Do not claim DeepSWE is "the standard."** Claim its *principle*, not its status.
- **Do not present the prebuilt-SDK trick as novel.** It is CHIA's own; the extension is the per-pin-window family, fetch-by-parent-SHA, and the coverage measurement.
- **Do not say "SWE-bench-Lite-scale."** Lite is 300 test instances.
- **Do not mention SpinalHDL.** It emits HDL from its own backend; zero CIRCT involvement.
- **Do not bill an OpenAI model to Google credits.** The proposal has no OpenAI dependency.
- **Do not write "novel" or "first" anywhere except block 2's single scoped sentence.**

## Not verified / open

- Whether the 187 subject-filtered commits are *genuinely* bug fixes — the keyword filter is a proxy and **no diffs were read**. Both 187 and 1,103 are reported for that reason. The pilot must hand-validate a sample.
- What fraction of the 171 exact-match tasks actually satisfy fail→pass. **One** was verified end to end (`f2b15a44ec70`); the rest are unvalidated.
- Whether vLLM serves `Qwen/Qwen3.8-27B` at a pinned version — the model card names vLLM, but the linked Qwen3.8 recipe URL 404s and vLLM's `supported_models` page lists no Qwen3.8 architecture. **Marked [UNVERIFIED] in the body.** Pin and test before relying on it.
- Whether an external CIRCT contributor will serve as a blinded reviewer. The protocol says ≥2 reviewers and "ideally"; the second may be internal.
- How many live open CIRCT issues the loop will reach. Not controlled, and said so in the body.
- Both headline metrics are **protocols, not measurements**. v2 commits to no target value for either.
- Every build number was measured on one host (20 cores, ~6 GB free RAM, `-j6`, clang 23.0.0git, lld 23, glibc 2.44, cold ccache), **not** in CHIA's Ubuntu 24.04 image.
- No published judging rubric exists for the hackathon; the A³ PC membership is not published.

---

# Appendix B — Mapping to the 4-page final paper

1. **Motivation (¾ page).** Resolve-rate is the wrong objective for a maintainer-facing repair loop; the cost CHIA printed is 60 min review + 10 min PR prep per issue. Frame the gap as a runtime retry/submit/abstain decision no current loop takes from evidence.
2. **The harness (1¼ pages — the core).** The six blocks as additions to assess→reproduce→fix→verify→regression-repair→writeup: repro contract, evidence gate, regression gate with blast radius, evidence bundle, image family, adapter. Feature set, fitting procedure, reliability diagram, and each block's CHIA interface.
3. **The instrument (½ page).** Mining shape (1,103/187); pin coverage (91.4% exact, 0 beyond one bump, 38 images, 7.0 d vs 10.4 d cadence); the ~3-line parameterization of `ChiaCirctBaseDockerfile`; the one-bump failure at 2/1,030 and the `include/circt` strip finding as evidence that exact pairing is the only viable construction.
4. **Evaluation (¾ page).** Calibration on the mined 171 with the stronger executor; validation on live open issues; mutation-injected bugs as harness smoke test only; the contamination probe as a reported measurement; the DeepSWE principle and the honest reason a fresh-authored corpus was out of reach; ablations — gate off, bundle off, threshold sweep.
5. **Results (½ page).** Maintainer-minutes per accepted fix under the blinded interleaved protocol vs 60 + 10; gate precision per executor and the transfer result; the reliability diagram; failure modes, including any regime where the gate degenerates to always-submit.
6. **Limitations and artifact (¼ page).** Single repo; keyword-proxy mining; unpublished model cutoffs; uncontrolled live-issue count; one-host build timings; and the released artifact — six blocks, adapter, 38-image family, and `chia job submit` reproduction for every row.

---

# Appendix C — Attacks pre-empted

| # | Attack | Where the body answers it |
|---|---|---|
| 1 | "You refactored CHIA's own loop and added a threshold." | §1 names CHIA's six phases and §2 frames the six blocks as additions "around CHIA's phases"; §3's first metric is measured on CHIA's own review-minutes number, not resolve-rate. |
| 2 | Self-graded, small-N maintainer minutes. | §3 metric 1 states the protocol before any number: bundle patches interleaved with gate-off baseline patches, blinded reviewer, per-patch minutes, ≥2 reviewers, ideally one external CIRCT contributor. |
| 3 | Calibration needs positives; a weak executor produces none. | §2 "Executors and calibration order" fits the gate on the stronger executor first, states why, then applies it unchanged. |
| 4 | The abstention result is contaminated. | §3 metric 2 reports precision cleanly and admits recall only with the memorization caveat; §2 adds that contamination cannot inflate an executed suite-green signal. |
| 5 | Mutation-injected bugs are a different distribution. | §2 "Evaluation and contamination" demotes them to a harness smoke test, names live open issues as validation, and states their count is not controlled. |
| 6 | Calibrated abstention is not new. | §2 block 2 concedes it in the same sentence and scopes the claim to compiler repair, execution evidence, inside CHIA, with a measured review-time effect. |
| 7 | "The bundle cuts review time" is asserted, not shown. | §2 block 4 scopes it to the accept/reject decision and says it does not replace the human who owns the PR under LLVM's AI Tool Policy; §3 metric 1 is the measurement. |
