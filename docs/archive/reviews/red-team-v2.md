# Red team — `problem-statement-v2.md`

Hostile review, 2026-09-11. No fixes, no praise. Ranked by severity.

Primary evidence used throughout:
- `examples/circt_issue_solver/README.md` (fetched raw, 8,735 bytes) — CHIA's actual loop.
- arXiv 2606.27350v3 §5.5 + Table 5 (fetched, grepped).
- `pin-window-analysis.md`, local.
- GitHub search API, `repo:llvm/circt is:issue is:open label:bug` → **101**.

---

## KILLS

### K1. Five of the six "blocks" already ship in CHIA's `circt_issue_solver`. The contribution is a logistic regression.

> "Six blocks answer it around CHIA's phases, none depending on which model drives. Executor is a config line; harness is the contribution."

CHIA's README, verbatim: **"reproduce — write `/workspace/circt/.circtissues/repro.sh` (contract: *exit 0 iff fixed*); skip if it doesn't reproduce (`no_repro`)"** — that is block 1, named "contract" by CHIA itself. **"verify — deterministic, no LLM: rebuild, rerun repro, run the full lit gate"** — that computes block 2's entire feature vector already. **"regression repair"** + **"The regression gate runs the full lit suite minus baseline-red dirs (`CAPI`, `Tools/circt-tblgen`)"** — that is block 3. **"assess — … If not, log the reason and skip (`not_a_bug` / `unclear`)"** — that is abstention. **`verdict.json`, `fix.diff`, `pr_writeup.md`, per-phase `llm_*.md`** — that is most of block 4. The genuine delta is: fit a logistic model over features CHIA already executes, add "blast radius", and re-pin a Dockerfile. A PC member who co-wrote this example reads §2 and sees their own phase list sold back to them with a threshold on top.

### K2. Gate precision on the mined split is circular — the label is a conjunction of the features.

> "**Gate precision across two executors.** Of patches the gate passes: fraction passing ground truth (mined split)"

Gate features are "repro fails at parent; patch flips exactly that test; suite stays green; blast radius". "Ground truth" on a mined fail→pass task *is* fail→pass plus pass→pass — i.e. features 1∧2∧3. The statement forbids the only non-circular label it could have used ("grade behaviour you execute, never a reference patch"). So precision is 1.0 by construction, the fitted model is degenerate, and the "transfer result" transfers a degenerate model. No number reported here can be informative.

### K3. The blinding in the headline protocol is impossible, because the treatment is the visible artifact.

> "agent patches with bundle interleaved with baseline patches (same loop, gate and bundle off), blinded reviewer, per-patch minutes"

The treatment arm hands the reviewer a repro script, failing test, localization and regression delta; the control arm hands them a diff. The reviewer can tell which arm they are in by looking. Blinding is not merely hard — it is definitionally unavailable, and any minutes delta is confounded with the reviewer knowing which arm is the experiment.

### K4. "Model-agnostic" is a CHIA CLI flag, and both named executors are CHIA's existing backends.

> "**A CHIA repair harness whose retry/submit/abstain decision comes from executed compiler evidence, not model self-report: the executor is a parameter**"

CHIA's README: **"`--model <id>` overrides the model of whichever backend is selected"**, with `--backend` already offering Claude, Antigravity/Gemini (`gemini-3.1-pro-high`) and OpenCode/Vertex whose **default model is `google-vertex/gemini-3.1-pro-preview`** — the statement's own "Executor A". The title's differentiator is a flag that shipped before the hackathon.

### K5. Denominator mismatch in the headline metric: "per accepted fix" vs CHIA's "per issue".

> "**Maintainer-minutes per accepted fix**, against CHIA's 60 + 10."

Paper §5.5 is per *issue*: "an hour per issue to review the agents' changes" and "about 10 more minutes per issue to prepare the pull requests". Table 5: 16 issues → 5 fixed → 3 PRs. Per *accepted fix* the host's number is (5×60 + 3×10)/3 ≈ **110 min**, not 70. The statement benchmarks itself against a baseline it has deflated by ~36% through a denominator swap — and its own Appendix A "Traps" warns against exactly this arithmetic while the body commits it.

### K6. The one scoped "first" is dead on both of its qualifiers.

> "Calibrated abstention is not new; first here for compiler repair, from execution evidence, inside CHIA, with a measured review-time effect."

**LLVM-Ens** (LLVM-Bench, arXiv 2607.00700, July 2026 — a paper the statement itself cites two paragraphs later) "first filters incorrect patches using LLVM-Gym, where each candidate patch is applied to the LLVM codebase and the resulting compiler is built": execution-evidence patch filtering, for compiler repair. **"Abstain and Validate: A Dual-LLM Policy for Reducing Noise in Agentic Program Repair"** (arXiv 2510.03217, Google) does bug abstention + patch validation explicitly to stop "wasting valuable developer time" — the statement's thesis, ~11 months earlier. What survives is "inside CHIA", which is vacuous, and "with a measured review-time effect", which K3 shows cannot be measured as designed. Four qualifiers on a "first" reads to a PC as an admission.

### K7. "Why not already done" surveys the wrong literature and misses the nearest neighbour.

> "LLVM-Bench (423 tasks), HWE-Bench (417) and Phoenix-bench (511) hold the loop fixed and rank models by resolve-rate; none targets a hardware-compiler source tree, none makes *whether to bother a human* a runtime decision."

Three benchmarks are surveyed; the *harness* literature is not. **arXiv 2603.20075 — "llvm-harness … the first harness designed to assist LLM agents in understanding and fixing compiler bugs"**, with agent-friendly tools + 334-bug benchmark + mini agent, evaluating **five frontier models** — is uncited. It already claims "first harness for compiler bugs" and already demonstrates model-agnosticism across five executors. The statement's headline noun and its framing were both taken six months ago. Also, LLVM-Bench does not merely "rank models by resolve-rate" — it contributes LLVM-Ens, the filtering method of K6; the statement mischaracterises its own cited source in the sentence that claims the gap.

---

## WOUNDS

### W1. The repro contract and the image family are both undefined on the validation split.

> "**Repro contract.** No model tokens until the harness holds a test failing at the bug's parent revision: precondition, not output."

An *open* issue has no fix commit, therefore no "bug's parent revision". Block 1 as written is satisfiable only on the mined split — which §2 demotes to "the **calibration split only**". Same for block 5: a pin-window image is keyed to a bug's parent pin, which does not exist for a live issue. The two most heavily evidenced blocks apply exclusively to the split the statement says is not the evaluation.

### W2. The live split's supply is a stale backlog, and the statement never counts it.

> "validation is **live open CIRCT issues**, whose count we do not control."

Measured today: **101** open issues labeled `bug`; 83 carry a code block; **median age 912 days**, p75 1,275 d, max 1,981 d; only **17** created in the last year; **4** labeled "good first issue" and therefore barred by the LLVM AI Tool Policy the statement itself cites (claim 26). These are the issues CIRCT maintainers have declined to fix for 2.5 years — the residue after CHIA's own loop already sampled this pool. "We do not control the count" is not a limitation, it is the absence of a denominator for the headline metric.

### W3. The contamination pre-emption is false as applied to *calibration*.

> "Contamination inflates resolve-rate, not an executed suite-green signal."

True per patch, false per fitting procedure. A model that memorised the fix emits the golden patch, which flips the test and keeps the suite green — a feature-perfect positive. Contaminated positives therefore cluster at the feature ceiling, and the only negatives left in the calibration set are patches that fail to build. The gate is fitted on a trivially separable distribution and its threshold carries no information to the live split. Appendix C attack #4 does not survive.

### W4. "Abstain" ships a bundle, which contradicts the premise.

> "Repro script, failing test, localization, regression delta, on submit *and* abstain."

The thesis is "is this patch worth a human's hour?". If abstention still hands the maintainer a bundle, the human still triages it and no minutes are saved; if the human never sees it, shipping a bundle on abstain is dead weight. The statement never says which, and the headline metric ("per accepted fix") cannot price abstentions either way.

### W5. The retry branch has nothing to retry with.

> "Logistic over those features emits retry/submit/abstain."

Executor is fixed, "**No fallback tier**", no prompt mutation, no budget, no stopping rule stated. Retry therefore means resampling the same model at the same temperature. CHIA already has this: **"regression repair — if the fix broke other tests, one more turn with the failing tests to repair"**. Third of the three outputs is either undefined or pre-existing.

### W6. The calibration set's real size is unknown and may be ~1.

Appendix A, "Not verified / open": "What fraction of the 171 exact-match tasks actually satisfy fail→pass. **One** was verified end to end (`f2b15a44ec70`); the rest are unvalidated." A task that is not genuinely fail→pass yields undefined gate features. So the statement's calibration split has a measured size of 1 and a hoped-for size of 171, and every downstream object — logistic fit, threshold, reliability diagram, transfer — inherits that.

### W7. The reliability diagram is fitted-set fit, with unstated bins.

> "The reliability diagram ships before the hold-out is touched; an uncalibrated gate collapses to always-submit."

No held-out calibration set is described anywhere — the gate is fitted on the mined split and validated on live issues, so the diagram can only be drawn on the data it was fitted to. Number of bins, points per bin, and confidence intervals are unspecified. With K2's degenerate label the diagram is a single point at p≈1.

### W8. The transfer claim names no test and no N.

> "the **transfer result** — the gate fitted on the stronger executor, applied unchanged to the local one."

No statistical test, no N of positives on the weaker executor, no minimum below which the comparison is abandoned. If `Qwen3.8-27B` produces three gate-passing patches, "transfer" is a statement about three points — and the statement separately admits vLLM may not serve that model at all (`[UNVERIFIED]` in the body).

### W9. "Maintainer-minutes" are not measured on maintainers, and the anchor is a novice.

> "blinded reviewer, per-patch minutes, ≥2 reviewers, ideally one external CIRCT contributor."

The metric is named for maintainers and delivered by whoever is available. Worse, it forks: match CHIA's anchor (a "graduate student with novice-level familiarity") and the external-contributor credibility evaporates; use the external CIRCT expert and the 60-minute comparison is confounded by expertise, not by the bundle. Appendix A concedes "the second may be internal".

### W10. The "CHIA invites this" quote is verbatim but misapplied.

> "CHIA invites this: 'Building these benchmark suites on top of CHIA would streamline the process of comparing different design loops, and we are interested in integrating these suites into CHIA.'"

Fetched in context: "these benchmark suites" refers to the *hardware* suites named in the preceding sentence — agentic co-design (Tsai, Alvanaki), RTL generation (Lu, Pinckney, Yu, Guo & Zhao), HLS (Abi-Karam & Hao). The authors are inviting benchmark suites. The statement's Non-goals say "No … leaderboard" and §2 demotes its corpus to "the calibration split only". It cites an invitation to do X as evidence that the PC wants Y, where the statement has declared X a non-goal. The people who wrote that sentence are on the PC.

### W11. The motivating scenario is contradicted by the host's own funnel.

> "A loop handing over nine patches to audit is worse than one handing over two."

Paper Table 5: of 16 issues, 9 were "Not a bug"/"Fix unclear" and 2 "Already fixed" — **11 of 16 never produced a patch**. CHIA's existing assess+reproduce phases already abstain at a 69% rate. The nine-junk-patches world the harness is built to prevent is not the world CHIA's data describes.

### W12. Distribution shift between calibration and validation is unmanaged.

Calibration = commits touching 1–2 files under `lib/`/`include/` that ship a test, bug-ish subject. Validation = arbitrary open issues. A threshold fitted on the easiest definable slice of CIRCT history is applied to a 2.5-year-old backlog with no file-count bound. The statement notes neither the shift nor a re-calibration step.

### W13. "Blast radius" is never defined.

Named three times — a gate feature, block 3's title, and "Which lit tests, dialects and headers a patch moves" — but never reduced to a scalar, never given units, never said how it enters a logistic model. For a ≤2-file patch under `lib/`, it is also near-constant on the calibration split, i.e. the one genuinely new feature is the one with least variance where it is fitted.

---

## NITs

- **N1.** "test red→green in 13 s" — `pin-window-analysis.md` §5.4 times the *incremental rebuild* at 13 s ("OK (3 targets)"). The test flip was not separately timed. Compression that a mechanical checker will flag.
- **N2.** "**171 (91.4%)** … **none more than one bump away**" — the antecedent of "none" is the 16 non-exact tasks, not the 171 (which are 0 bumps away by definition). Reads as a claim about the 171.
- **N3.** "*[placeholder: GPU hours + Gemini credits, measured in the pilot.]*" left in the submitted body.
- **N4.** "`Qwen/Qwen3.8-27B` (local, CHIA's `VLLMDockerfile`; no 27B-specific vLLM recipe published [UNVERIFIED])" — an inline `[UNVERIFIED]` tag in a submission is reviewer-management notation leaking into the artifact; it also advertises that a named deliverable may not run.
- **N5.** "On-prem is a harness property, not a thesis." / "breadth would cost the measurement its meaning." / "It shortens the accept/reject decision; it does not replace the human who owns the PR" — three sentences written to pre-answer a reviewer rather than to describe the work. A PC reads pre-emptive defensiveness as awareness of weakness.
- **N6.** "**Cost.**" section with no cost, next to a "Non-goals" section — the statement spends its scarce page telling the reader what it will not do (five items) before it has shown one result.

---

## The rival statement (hat 2)

**"Adversarial CIRCT: a discovery→repair→upstream loop that manufactures its own bugs."** A generator agent mutates FIRRTL/HW-dialect inputs and differential-tests `firtool` against its own `-O0` lowering and against Verilator simulation, a triage agent shrinks each divergence to a minimal `.mlir` reducer case, and the existing CHIA repair loop fixes it — closing discovery and repair in one loop that ships new upstream bug reports as its output.

Why it beats v2 on "the most novel, creative agentic loop(s)": (1) it is visibly a **loop** with three interacting agents, where v2 is a threshold bolted onto CHIA's existing loop — the prize sentence rewards loops, not harnesses; (2) it **creates** task supply instead of competing for a 912-day-old backlog of 101 issues, so its evaluation scales with compute rather than with maintainer goodwill; (3) it hits suggested track #1 verbatim ("Discovery and resolution of architectural and microarchitectural bugs"), which v2 reaches only through the catch-all "Submitting your own ideas is also welcome!"; (4) its deliverable — a fuzzer block, a reducer block, a differential-oracle block — is three composable blocks CHIA visibly lacks, versus v2's blocks that CHIA's README shows it already has; (5) a judge grasps it in one sentence, whereas v2 requires accepting a contested claim about what CHIA's loop does *not* do before its contribution exists at all.

---

## The one question this statement cannot answer

**"Your appendix cites our README for the phase list. That same README says `reproduce` already writes a repro contract that exits 0 iff fixed and skips on `no_repro`, `verify` is already deterministic with no LLM and already runs the full lit gate, `regression repair` already exists, `assess` already skips on `not_a_bug`/`unclear`, and `--model` already makes the executor a parameter. Point at the line of our loop your harness changes, other than fitting a logistic regression to the numbers `verify` already prints — and then tell us what that regression's precision is on a label that is a conjunction of its own input features."**

There is no answer in the document. §2 asserts the six blocks are "additions"; Appendix C attack #1 defends only that the statement *names* CHIA's phases. Neither establishes a delta.

---

## Factual spot-checks

| # | Claim | Source checked | Verdict |
|---|---|---|---|
| 1 | "an hour per issue" / "about 10 more minutes per issue" quoted verbatim | arXiv 2606.27350v3 §5.5, grepped raw HTML | **PASS** — exact match |
| 2 | "16 issues, fixed 5, merged 3 PRs" | same, Table 5 + text | **PASS** — table shows 16 rows, 5 "Fixed Yes", 3 "Yes (Merged)" |
| 3 | 60 + 10 compared against "per accepted fix" | same | **FAIL** — paper's figures are per *issue*; per accepted fix ≈ 110 min (K5) |
| 4 | "171 (91.4%)" of 187 exact pin match | `pin-window-analysis.md` §4 | **PASS** |
| 5 | "none more than one bump away" | same §4 (">1 LLVM bump away: 0 (0.0%)") | **PASS** (ambiguous antecedent, N2) |
| 6 | "38 images cover all 171" | same §4 ("38 (median 3, max 27)") | **PASS** |
| 7 | "built 1,027/1,027 in 939 s" | same §5.4 | **PASS** |
| 8 | "At a parent 18 commits past its tag" | same §5.3 ("18 commits and 11 days later") | **PASS** |
| 9 | "test red→green in 13 s" | same §5.4 | **PARTIAL** — 13 s is the incremental rebuild, not the test (N1) |
| 10 | "one bump off, the SDK dies at target 2/1,030" | same §5.5 ("FAILS at target 2 / 1030") | **PASS** |
| 11 | Track quote "Reusable CHIA blocks … and can be reused after the hackathon." | agentic-arch.org/hackathon.html, raw | **PASS** — verbatim |
| 12 | "Submitting your own ideas is also welcome!" | same | **PASS** — verbatim |
| 13 | "Building these benchmark suites on top of CHIA…" | arXiv 2606.27350v3, related work, grepped | **PASS verbatim / FAIL in context** — refers to hardware benchmark suites; statement's Non-goals exclude benchmarks (W10) |
| 14 | "the rest of the flow still assumes CIRCT" | `circt_issue_solver/README.md`, raw | **PASS** — verbatim |
| 15 | Loop phases assess→reproduce→fix→verify→regression-repair→writeup | same | **PASS** — verbatim, *and* the README shows each phase already does what blocks 1–4 claim to add (K1) |
| 16 | "LLVM-Bench … hold[s] the loop fixed and rank[s] models by resolve-rate" | arXiv 2607.00700 | **FAIL** — LLVM-Bench also contributes LLVM-Ens, an execution-based patch filter (K6/K7) |
| 17 | "first here for compiler repair, from execution evidence" | 2607.00700 (LLVM-Ens), 2510.03217 (Abstain & Validate) | **FAIL** — both predate |
| 18 | "none targets a hardware-compiler source tree" | 2603.20075, 2607.00700, 2604.14709, 2605.15226 | **PASS**, but the moat is one hyphenated adjective, and llvm-harness is uncited |
| 19 | Live open CIRCT issues available for validation | GitHub search API, 2026-09-11 | **101** labeled `bug`; 83 with code blocks; median age **912 d**; 17 < 1 yr; 4 good-first-issue (policy-barred). Statement gives no count (W2) |
| 20 | `gemini-3.1-pro-preview` as "Executor A" is a differentiator | `circt_issue_solver/README.md` | **FAIL** — it is already the OpenCode/Vertex backend's default model in CHIA (K4) |
