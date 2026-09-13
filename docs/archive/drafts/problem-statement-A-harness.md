# After verify: a calibrated submit/retry/abstain gate for CHIA's CIRCT loop

**CHIA's CIRCT loop executes everything needed to judge its own patch and never judges it: we add the post-`verify` decision, submit/retry/abstain, and the bug-parent images to fit it on.**

## 1. Problem

CHIA abstains on *issues*: `assess` skips `not_a_bug`/`unclear`, `reproduce` skips `no_repro`. Once a patch passes `verify` no decision remains: it reaches `writeup`, then a human: "an hour per issue" plus ten minutes of PR prep. `verify` is "deterministic, no LLM: rebuild, rerun repro, run the full lit gate"; nothing consumes what it computes. The image is pinned at **firtool-1.148.0**: one environment, no distribution to fit on.

## 2. The loop

Phases and `--backend`/`--model` executor choice are unchanged.

Added between `verify` and `writeup`: a logistic gate over features `verify` already runs (repro exits 0, lit gate green, tests flipped) plus **blast radius** `b`: changed-outcome lit tests, distinct dialect directories, public `include/circt` headers touched, entering as `log(1+b)` with a non-positive coefficient. It emits **submit** with the evidence record, **retry** (bounded resampling, budget *N*, failing evidence fed back), or **abstain** (nothing reaches a maintainer; the record kept for audit).

The decision is arithmetic over executed evidence, not self-report. Since "the rest of the flow still assumes CIRCT", build, test-select, repro-contract and regression-gate become four adapter methods.

## 3. Instrument and evaluation

**Environments.** ~3 lines of `ChiaCirctBaseDockerfile`: `CIRCT_VER` re-pinned, clone-by-tag becomes fetch-by-parent-SHA. Of 187 bug-fix-shaped `llvm/circt` commits, 171 have a `firtool-*` release whose LLVM pin exactly matches the bug's parent, none beyond one bump; 38 images cover them. At a parent 18 commits past its tag: 1,027/1,027 targets in 939 s, the bug's test red then green in a 13 s rebuild. One bump off, the build dies at target 2.

**Labels.** The fix commit's withheld test: never shown to the executor, never a gate feature.

**Supply.** Of 1,103 shape candidates, 84 close a GitHub issue, 76 with an exact pin. Live: 101 open `bug` issues, median age 890 days, 17 in the last year.

**Contamination.** A memorized fix is a feature-perfect positive, so mined calibration is optimistic; a per-task probe splits reported numbers.

**Transfer.** Fitted under one backend, applied unchanged under another; below 20 gate-passing patches there, insufficient rather than a number.

## 4. Expected results

**Headline: minutes per correct accept/reject decision.** Two arms, gate-plus-record and CHIA-baseline diff-only, randomized and interleaved for one pool, known-incorrect patches mixed in so the reviewer is blind to correctness; ≥2 reviewers, per-patch timing, correctness from the withheld test. CHIA's cost is per *issue* (60+10); we report per decision, and per accepted fix against the matched (5×60+3×10)/3 ≈ 110 from 5 fixes, 3 PRs.

Secondary: gate precision/recall, reliability curve with per-bin counts, gate-off ablation, task count.

## Demo

`chia job submit` replays two mined rows: submit, then abstain.

## Relation to CHIA's existing loop

| CHIA today | This work |
|---|---|
| assess→reproduce→fix→verify→regression-repair→writeup | unchanged |
| `verify`: repro, full lit gate, no LLM | gate features |
| verified patch → human | submit/retry/abstain |
| regression repair: one turn, broken tests | bounded retry, budget *N*, any failing feature |
| `--backend`/`--model` | fitted under one, applied to another |
| pinned at `firtool-1.148.0` | 38 images at mined bug parents |

## Prior art

Abstain-and-Validate (2510.03217) abstains on bugs and validates patches; LLVM-Ens (2607.00700) filters candidates by build and test; llvm-harness (2603.20075) is "the first harness designed to assist LLM agents in understanding and fixing compiler bugs", on LLVM's middle-end. Here the decision sits inside CHIA, on MLIR hardware dialects, and is itself measured.

## Non-goals

Root causes in LLVM/MLIR, scoped out by the example; no benchmark, resolve-rate ranking, finetuning, second target.

## Limitations

The 187 rest on a subject-keyword proxy, one verified fail→pass end to end; the 8.6% lacking an exact SDK are dropped. The mined distribution is narrower than live issues; the threshold is refitted before live claims.

---
---

# Appendix A — Claims and sources

Every number, quote and identifier in the body, with the loop facts they rest on.

| Claim | Source |
|---|---|
| Phases assess → reproduce → fix → verify → regression repair → writeup | `examples/circt_issue_solver/README.md`, fetched raw 2026-09-11 |
| `assess` skips `not_a_bug` / `unclear`; `reproduce` skips `no_repro`; repro contract "exit 0 iff fixed" | same |
| "deterministic, no LLM: rebuild, rerun repro, run the full lit gate" | same, verbatim |
| "regression repair — if the fix broke other tests, one more turn with the failing tests to repair" | same, verbatim |
| Outputs `fix.diff`, `pr_writeup.md`, `verdict.json` | same |
| "`--model <id>` overrides the model of whichever backend is selected"; backends Claude / Antigravity (`gemini-3.1-pro-high`) / OpenCode-Vertex (default `google-vertex/gemini-3.1-pro-preview`) | same, verbatim |
| "The chia-circt image is pinned at **firtool-1.148.0**. Issues fixed upstream after that tag won't reproduce" | same, verbatim |
| "Root cause in LLVM/MLIR (the prebuilt SDK / `llvm` submodule) is out of scope" (Non-goals) | same, verbatim |
| "the rest of the flow still assumes CIRCT" | same, verbatim |
| "an hour per issue" review; "about 10 more minutes per issue" PR prep | arXiv 2606.27350v3 §5.5, verbatim |
| 16 issues, 5 fixed, 3 PRs merged; ≈110 min per accepted fix | same, §5.5 and Table 5. 60 and 10 are the paper's per-*issue* figures; (5×60 + 3×10)/3 is our arithmetic, shown in the body |
| 187 bug-fix-shaped commits; 1,103 on file shape alone (24 months; 1–2 files under `lib/`/`include/`; adds or modifies a test; bug-vocabulary subject for the 187) | `pin-window-analysis.md` §4, `pin_window_results.txt`; both counts re-derived this session from a fresh `llvm/circt` clone, HEAD `d7e94049bde3` |
| 171 of 187 have an exact prebuilt-LLVM pin at the bug's parent | `pin-window-analysis.md` §4 |
| 0 of 187 beyond one LLVM bump; the residual 16 are 8.6% | same §4 |
| 38 images cover the 171 (distinct pin windows spanned; median 3 tasks, max 27) | same §4 |
| 1,027/1,027 targets in 939 s; parent 18 commits / 11 days past `firtool-1.157.0`; configure 10 s | same §5.3–5.4, executed |
| Test red at the parent, green after the fix; 13 s is the incremental rebuild, which is what was timed | same §5.4, executed (`f2b15a44ec70`, `test/Conversion/HWToLLVM/convert_aggregates.mlir`) |
| One bump off, the build fails at target 2 of 1,030, during TableGen | same §5.5, executed; one bump = 1,237 llvm-project commits |
| ~3-line change to `ChiaCirctBaseDockerfile` (`CIRCT_VER`; `git clone --depth 1 --branch "${CIRCT_VER}"` → fetch-by-parent-SHA) | file read in full, `pin-window-analysis.md` §5.1. Its `rm -rf /opt/circt-sdk/include/circt` strip is load-bearing: without it the build dies at 514/1027 (§5.4) |
| 84 of 1,103 shape candidates close a GitHub issue; 76 of those also have an exact pin | measured this session over the full commit messages of the same 1,103: a `fix`/`fixes`/`fixed`/`close[sd]`/`resolve[sd]` keyword within 20 characters of `#N` or of an `llvm/circt/issues/N` URL. Exact-pin membership from the 978-row exact-match table in `pin_window_results.txt` |
| 101 open CIRCT issues labelled `bug`, median age 890 days, 17 in the last year | GitHub search API, `repo:llvm/circt is:issue is:open label:bug`, 2026-09-11 |
| Abstain-and-Validate = arXiv 2510.03217; LLVM-Ens = arXiv 2607.00700, filters candidates by build and test; llvm-harness = arXiv 2603.20075, quoted phrase, LLVM middle-end, five frontier models | the three papers |
| `chia job submit` exists (`chia job` proxies to `ray job`) | <https://docs.chialoops.ai/en/latest/user_guides/reference.html> |
| Release cadence median 7.0 d vs LLVM bump cadence median 10.4 d — why coverage is high (motivates 171/187) | `pin-window-analysis.md` §3 |

# Appendix B — Not verified

- **How many of the 171 genuinely satisfy fail→pass.** One (`f2b15a44ec70`) executed end to end; the 187 rest on a subject-keyword proxy and no diffs were read. The usable count is the pilot's first output.
- **The issue-reference counts are a text pattern, not a resolved link.** A stricter variant of the same pattern returns 89 of 1,103, 83 with an exact pin; the intersection with the bug-vocabulary 187 is 35–39 depending on variant. No referenced number was resolved against the API to confirm it is an issue rather than a pull request.
- **Whether a contamination probe separates memorized from reasoned fixes** at useful resolution.
- **The fit itself.** Nothing is fitted yet: feature weights, operating threshold, calibration and the retry budget *N* are all to be set in the pilot. Every metric here is a protocol; no target value is claimed.
- Build and timing numbers are from one host (20 cores, ~6 GB free RAM, `-j6`, clang 23.0.0git, lld, glibc 2.44, cold ccache), not CHIA's Ubuntu image. The SDK ships no `llvm-lit` and needs `libz3.so.4`; both are one-liners in the image.
- Reviewer pool composition, and whether an external CIRCT contributor takes part.
- No published judging rubric for the hackathon; A³ PC membership is not published.

# Appendix C — The one question

*Point at the line of CHIA's loop you change.*

The edge where `verify` succeeds and the patch proceeds to `writeup`: today it is unconditional, and we make it a three-way decision fitted on the features `verify` already prints plus blast radius. The label it is fitted against is the fix commit's withheld test — not a gate feature, and never shown to the executor — so the fit is not a conjunction of its own inputs. Running it at all requires the second change, bug-parent images, because the shipped image reproduces only what predates `firtool-1.148.0`.
