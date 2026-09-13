# CHIA hackathon — handoff (state as of 2026-09-12)

Team: Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla (IIIT Hyderabad).
Event: CHIA hackathon, UC Berkeley SLICE lab, judged by the A³ workshop PC (MICRO 2026).
Prize sentence: "the most novel, creative agentic loop(s)". Final due **2026-09-24 AoE**: 4-page paper + open-sourced loop with results. Winners 2026-09-26.

## Where things stand

The original proposal (CIRCT-Bench: a mined repair benchmark + repo-agnostic adapter) was evaluated, red-teamed, and replaced. Three theses were drafted and attacked by fresh-context red teams; the surviving thesis is a **closed discovery→repair loop**:

> Seed, generate, reduce, repair, gate: a closed CIRCT bug loop.
> A CHIA loop seeded with 187 mined CIRCT fix commits (171 rebuildable from a stock prebuilt SDK). An agent reads each fix, states the root-cause class, generates inputs in the seed's own language. Oracle: crash/CIRCT assertion (assertions restored with `-UNDEBUG`), arcilator-vs-Verilator differential secondary. `circt-reduce` shrinks. CHIA's `circt_issue_solver` repairs, entered by local report. A gate decides report / report+patch / nothing. Headline: distinct, maintainer-confirmed bugs within a pre-registered budget, seeded arm vs mutation-fuzzer arm.

Rating of the final statement: 8/10 as a document; win odds now depend on campaign evidence, not wording. Every number in it has been verified against a primary source or a local measurement at least twice.

## Files

| File | What |
|---|---|
| `problem-statement-FINAL.md` | The finalized problem statement. Appendix A = every claim with its source. Appendix B = everything not yet built/verified (use as threats-to-validity). Appendix D = 4-page paper outline. |
| `circt-bug-loop-proposal.html` | The FINAL rendered in the team's one-page proposal format (same CSS as the old CIRCT-Bench proposal). Print to PDF. Cost table figures are estimates. |
| `abstract.md` | Abstract for A³ HotCRP registration (Sep 14 AoE) + ≤100-word and form-field versions; where-it-goes header with all deadlines. |
| `explainer.md` | From-basics explainer of the problem and the loop for a reader without compiler/hardware/agent background. |
| `paper/` | **The 4-page paper, v3** (2026-09-13): `main.tex` (IEEEtran conference, pdflatex+bibtex via `build.sh`), `fig-loop.tex` (full-width TikZ figure, original "attrition ribbon" concept: agent band above, Sankey-style ribbon pinched by four gate bars with discard peels, human gate at the end; the user rejected an earlier imitation of their reference image, so keep designs original), `fig-timeline.tex` (release-pinned main), `refs.bib` (every author list fetched from arXiv/Crossref), output `circt-bug-loop-paper-v3.pdf`. Replaces v2 (`~/Downloads/circt-bug-loop-paper-v2.pdf`, LaTeX source lost; had fabricated refs for FLEX/AFuzz/SyzVegas). Abstract 148 words, no digits; body ~2,050 words. |
| `design/` | **Formal design set (2026-09-13, gated: user approves each before the next).** `00-README.md` (ID scheme, no-code rule, one-seam two-person rule), `01-FRD.md` (features and requirements; red-teamed in `design/reviews/red-team-FRD.md`, disposition in `red-team-FRD-disposition.md`), then `02-HLD.md`, `03-LLD.md`, `04-Test-Plan.md`, `05-Work-Plan.md`, `ADR/`. CHIA source for citations: `~/.cache/chia-src` (commit 16c35e92). |
| `analysis/measurements/` | **FRD follow-up measurements (2026-09-13)**, report `2026-09-13-frd-followups.md` + scripts + `raw/`. Settled: 98.9% of the 187 seeds reducible (146 MLIR direct, 39 via `firtool --parse-only` / `circt-verilog --ir-moore` lift, 2 textual); `-gline-tables-only` costs ~0 build time, +324 MiB binaries, symbolizer resolves file:line; assertion false-positive set over 1,127 lit tests = 0; CHIA's published `chia-circt:latest` is assertions-off (0 `__assert_fail`, 606/606 `-DNDEBUG`), depth-1 clone at firtool-1.148.0, `circt-opt` only, no slang, no Verilator; **CHIA's lit exclusion (`--filter-out`) cannot exclude `test/Tools/circt-tblgen` at commits after 2026-07-16 because its `lit.local.cfg` raises at discovery under an SDK build** (remedy: point `mlir_src_root`/include at the SDK's `include/`, which ships `OpBase.td`); slang-dependent seeds = 36 (not 46), entering via `circt-verilog` and `circt-translate --import-verilog`; `--split-input-file` (56 seeds) and `--verify-diagnostics` (53) must be stripped from probe argv; contamination flag rate 96.3% file-level, 77.0% symbol-level. No Claude Code CLI on this host (it lives in the `chia-claude-code` image). **Second report `2026-09-13-slang-verilator-bugcount.md`:** slang front end builds from source against the SDK (`CIRCT_SLANG_FRONTEND_ENABLED=ON`, FetchContent pin 44dc55f9, configure 19 s, build 841 s at -j8, +16.8% CPU, `circt-verilog` 71 MB, `circt-translate` +51 MB), IR byte-identical to the SDK's on a seed `.sv`; from-source binaries need the z3 shim at run time too. Ubuntu 24.04 apt Verilator = 5.020-1 with `--x-initial --x-assign --binary --timing` all present (host has 5.052). `llvm/circt` closed `label:bug` issues = 487, open = 101 (2026-09-13 21:00 IST). Build dir `~/.cache/chia-pin-smoke/bslang/`. |
| `final-check.md` | The last verification pass: 40+ mechanical checks, escape table vs the previous red team, the three arithmetic kills that were fixed. |
| `analysis/pin-window-analysis.md` | Empirical basis: 187 bug-fix-shaped commits / 24 mo; 171 have an exact prebuilt-LLVM `firtool-*` SDK; 0 beyond one bump; 38 images; build at a historical parent 1,027/1,027 in 939 s; red→green flip; one bump off fails at tblgen. SDK gotchas: no `lit`, needs `libz3.so.4`, CHIA's `include/circt` strip is load-bearing. |
| `analysis/pin_window.py`, `pin_window_raw.json`, `pin_window_results.txt` | Re-runnable analysis (`python3 analysis/pin_window.py /path/to/circt-clone`; clone with `git clone --filter=blob:none https://github.com/llvm/circt`). Quote the refspec `'refs/tags/firtool-*'` in fish/zsh. |
| `analysis/pin_window_flip_smoketest.sh` | The fail→pass flip test as run (bug `f2b15a44ec70`, parent `5056ff04450b`, SDK `firtool-1.157.0`). |
| `analysis/undebug_build.log` | Log of the completed assertions-on build (605/605). |
| `analysis/probe/` | Hand-written FIRRTL/MLIR/SV probes: arcilator `arc.sim.*` harness (`tiny_arc.mlir`), Verilator testbench (`tb.sv`), `circt-reduce` placeholder oracle (`oracle.sh`). |
| `analysis/lec/` | `circt-lec` probes (equal / unequal / `hw.wire` rejection). `circt-lec` was dropped from the design. |
| `circt-bench-proposal.html(.pdf)` | The ORIGINAL proposal, superseded. Kept as format template. |
| `archive/drafts/` | v1 (CIRCT-Bench reframe), v2 (harness), A (harness, honest diff), B (discovery), B-v3. Superseded. |
| `archive/reviews/` | `chia-eval-report.md` (first evaluation of the original, hackathon ground truth in §A), `red-team-v2.md`, `red-team-AB.md` (A vs B), `red-team-v3.md`. |

- **Gemini credential (2026-09-14):** the user supplied a Google Cloud API key (project 581346760254). Stored at `~/.config/bugloop/gemini.env` (mode 600, `GEMINI_API_KEY=...`); the copy the user left at `api.md` in the project was removed so it cannot ship with the open-sourced loop. Never print it; pass it via `x-goog-api-key` header or `{env:GEMINI_API_KEY}`, never in a URL. Verification 2026-09-14 00:5x IST: `generativelanguage.googleapis.com` returned 403 PERMISSION_DENIED "Gemini API has not been used in project 581346760254 before or it is disabled"; the user must enable the Generative Language API on that project (console link in the error) or point us at the credits project. **Superseded 2026-09-14 by ADR-D-03's superseding decision:** Vertex AI express mode accepts the key (`genai.Client(vertexai=True, api_key=...)`, 200 on `gemini-3.8-flash` and `gemini-3.1-pro-preview`), so the backend is CHIA's `vertex` backend, model **`gemini-3.8-flash` for every stage** (user's instruction; no 3.1 Pro). **API discipline (user): USD 300 credit; no live model call until tiers T0 to T2 are green with the model layer mocked and the code red team has passed; first live call is the pilot; `budget.yaml` carries `campaign_spend_cap_usd`.** Probes made so far: three one-word calls (~24 tokens). Pricing recorded in ADR-D-03 (USD 0.75 / 3.75 per M tokens, aggregator-sourced, re-verify). Earlier note kept for history: backend path via CHIA `opencode` with `AdditionalModelProvider(id="google", npm="@ai-sdk/google", api_key="{env:GEMINI_API_KEY}")` or `openai_compat` against Gemini's OpenAI-compatible endpoint; CHIA's `vertex.py` needs ADC and a project, not an API key.

## Local build artifacts (outside the repo)

`~/.cache/chia-venv/` — Python 3.10.21 (`uv venv --python 3.10`) with CHIA installed editable from `~/.cache/chia-src` (Ray 2.54.0, `chia` CLI works). Head-node environment for the loop; host Python is 3.14 and unsuitable for Ray 2.54.0. Docker 29.7 works without sudo; 20 cores, 15 GB RAM (cap builds at -j8), 466 GB free. Images pulled: `ghcr.io/ucb-bar/chia-circt:latest` (4.79 GB, assertions-off, depth-1 clone at firtool-1.148.0) and `ghcr.io/ucb-bar/chia-claude-code:latest` (2.05 GB, 2026-09-01; contains Claude Code 2.1.252 at `/usr/bin/claude`, Python 3.10.19, Ray 2.54.0). Model-id acceptance (`claude-opus-5`, `claude-sonnet-5`) still untested: needs `~/.claude` mounted and consumes the user's subscription.

`~/.cache/chia-pin-smoke/` (~1.3 GB): `circt-full-1.157.0.tar.gz` (SDK), extracted `circt-sdk/`, `src/` = CIRCT at parent `5056ff04450b` built with CHIA's flags (`-DNDEBUG`), `src2/` = HEAD one bump off (fails), `shim/libz3.so.4` symlink, build logs, `flip.sh`.
`~/.cache/chia-pin-smoke/bassert/` (~0.5 GB, copied from the session scratchpad): the completed `-UNDEBUG` build — `bin/circt-opt` with CIRCT assertions on.
`~/.cache/chia-pin-smoke/circt/` (~80 MB): blobless `llvm/circt` clone used by `pin_window.py`.
`~/.cache/chia-pin-smoke/bassert_g/` (~1.3 GB): five tool targets built `-O3 -UNDEBUG -gline-tables-only` (measurement M2; symbolizer resolves file:line). `~/.cache/chia-pin-smoke/bslang/` (~1.4 GB): same plus slang front end from source, `circt-verilog` and `circt-translate --import-verilog` present (M7). `~/.cache/chia-pin-smoke/venv/`: throwaway venv with `lit` (M3). All from-source binaries need the z3 shim on `LD_LIBRARY_PATH` at run and build time.
Delete all with `rm -rf ~/.cache/chia-pin-smoke` if disk matters; rebuilding costs a 142 MB download + ~16 min at `-j6`.

Run SDK binaries with: `export LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim`.

## Decisions taken (don't relitigate without new evidence)

1. Benchmark/dataset is NOT the headline (prize is for loops). Mined corpus is the instrument.
2. Model choice is a config line (`--backend`/`--model` exist in CHIA). No SLM thesis, no frontier fallback tier, no dollar headline.
3. Harness-only thesis rejected: CHIA's README already has repro contract, deterministic verify, regression repair, assess-skip; llvm-harness (2603.20075) and Abstain-and-Validate (2510.03217) are prior art.
4. Discovery loop chosen. Generation method credited to AFuzz (2605.10074); FLEX (2510.07815) is the non-agent baseline class; the head-to-head answers "does the agent add anything to generation".
5. Repair scoped to crashes/assertions (unambiguous expected behaviour). Differential divergences are report-only until an X-initialisation/reset policy is fixed.
6. "Release-pinned main" not HEAD: HEAD's LLVM pin currently has no release SDK; one bump off is a hard build failure.
7. Confirmed = maintainer-confirmed only. Budget pre-registered by a commit in the loop repo.

## Verified facts worth remembering

- CHIA's own image compiles out CIRCT assertions (620/620 compile commands `-DNDEBUG` under its cmake flags). `-DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG"` restores them: 605/605 targets, 495/513 CIRCT objects with `__assert_fail`, lit 520/523, no ABI issue (`LLVM_ENABLE_ABI_BREAKING_CHECKS 0` in SDK). `circt-opt --version` still says "Optimized build." — reports must state the flag.
- CIRCT `label:bug` issues: 82 filed in the last year (65 closed, 17 open); 101 open total, median age 911 d; `miscompile` 2, `"wrong output"` 13, `"wrong result"` 14; 15 issues mention fuzz, 13 closed. No in-tree fuzzing.
- Seeds by first source dir: FIRRTL 37, ImportVerilog 31, include/Dialect 16, MooreToCore 12, LLHD 11, Comb 7, Synth 7, … ~127 of 187 unreachable from a `.fir` input → input language must follow the seed.
- `circt/arc-tests` already ships lockstep arcilator-vs-Verilator on Rocket/BOOM. `arcilator.cpp` calls itself "An experimental circuit simulator".
- `circt-lec` prints `c1 == c2` / `c1 != c2` with rc=0 both ways; rejects `hw.wire`; `--preserve-aggregate` is not a usable differential axis.
- `$4.18` and `~70 min` from the CHIA paper are sums (0.40+0.68+3.01+0.09; 60+10), not printed figures.
- Stale model ids in the old proposal (GPT-4o, Gemini 1.5 Pro, nonexistent Qwen3-32B-Instruct). Current: `gemini-3.1-pro-preview`, `gemini-3.8-flash`, `Qwen/Qwen3.8-27B`, `gpt-6-astra`.

## Open items (nothing below has been built)

- Generator agent (seeded, AFuzz-style) and the mutation-fuzzer baseline arm.
- Release-pinned-main image builder (`ChiaCirctBaseDockerfile` parameterised: `CIRCT_VER`, fetch-by-SHA, `-UNDEBUG`, z3, Verilator, `lit`).
- Local-report entry into `circt_issue_solver` (supply node, ID scheme, report-writer prompt, dedup over open/closed issues + post-pin commits, gated filing with per-day cap).
- Oracle scripts + `circt-reduce` interestingness test; arcilator/Verilator harness generators from port lists; X/reset policy.
- Dedup rules (assert text+file:line; symbolized frames; structural hash) — planned, unexecuted.
- `budget.yaml` with GPU-hours, input cap, filing cap — commit before the campaign.
- Only 1 of the 171 tasks has been validated fail→pass end to end; the 187 rest on a subject-keyword proxy.
- **Ownership (user, 2026-09-13): the architect (this session, via Opus agents) builds the entire project start to end, ready for submission; no two-person split. The seam in `00-README.md` remains as a test boundary only. GCP is deferred: the user supplies it when the loop is ready; single machine until then.**
- Design set: `design/01-FRD.md` is Draft, red-teamed and revised (2026-09-13); D-01..D-14 resolved (14 ADRs). `02-HLD.md` written, red-teamed (`reviews/red-team-HLD.md`: 7 kills, 31 wounds, 9 nits) and revised with 21 FRD errata (`01-FRD.md` §1.5). `03-LLD.md` written (35.8k words, 330 verified citations; every FR traced to a module), red-teamed (`reviews/red-team-LLD.md`: 16 kills, 28 wounds, 17 nits; all empirical kills reproduced by the reviewer with commands) and the fix round is complete (`reviews/red-team-LLD-disposition.md`; LLD now 50k words, contract package **2.0**: `SeedRecord` carries `diff` and `test_files`; A1/A2/B6b head-side; `SourceReadTool` replaces `BashTool` for agent stages; FRD errata §1.7). Extra finding: `circt-reduce` itself dies on a stack-overflow input (`reducer_aborted` routes to the textual reducer). Resync of LLD and test plan, and `05-Work-Plan.md`, in progress (2026-09-14). Key kills: glibc assertion regex rejected C++ `::` names; symbolizer must be fed module+offset, not runtime addresses; crash fingerprints need the signal-handler prologue stripped; image fetch-by-SHA left no tag for the pin check; generators had no path to the seed diff (fix: A1/A2/B6b head-side, `SeedRecord` carries diff and test-file text, contract 2.0); `git clean -fd` deletes `.circtissues` (fix: repro dir outside the tree). ADRs D-05/D-09/D-13 carry the 2026-09-13 measurements. `04-Test-Plan.md` written (25.5k words, 384 tests: 329 unit, 17 integration, 9 system, 15 NFR, 14 equivalence-class; all 198 FRs traced; 31 FRs system-level only). Its §16 lists seven LLD functions too vague to test and two LLD defects, to be folded in at the resync after the LLD fix round. Next: LLD fix round, test-plan resync, `05-Work-Plan.md` (each becomes an `ADR/` file) before `02-HLD.md` starts. No code until 01-05 Approved.
- 4-page paper: v3 built in `paper/` (2026-09-13); vocabulary fixed to CHIA's terms (nodes and tools, not "blocks"). Remaining: co-author read-through, replace "expected" wording with results once the campaign runs, decide whether the same paper goes to A³ (HotCRP abstract Sep 14 AoE, paper Sep 21 AoE) and the hackathon (Sep 24 AoE).

## Process lessons (from this session)

- "Review" must include a fresh-context adversarial pass on the DESIGN, not only fact-checking. Read the host project's README in full before claiming any addition.
- Every red team finds kills; after three rounds the kills were at the evidence boundary, not the wording. Next value is a bounded discovery pilot, not more prose.
- Numbers: derive from artifacts in the same script that writes them (two arithmetic errors slipped in from mid-build snapshots).
