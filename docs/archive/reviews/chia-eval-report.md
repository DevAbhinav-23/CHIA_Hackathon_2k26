# Will "CIRCT-Bench" win the CHIA hackathon? — problem-statement evaluation

Date of analysis: 2026-09-11. Scope: problem statement / framing / deliverable choice only. Timeline, budget, team capacity deliberately ignored.

---

## A. Ground truth about the CHIA hackathon

### A.1 What CHIA is

- CHIA is "An open framework for designing and deploying custom AI-driven HW/SW co-design flows fast", BSD-3, repo `ucb-bar/chia`, created 2026-06-26, 90 stars / 18 forks / 6 open issues as of 2026-09-11. Source: https://github.com/ucb-bar/chia and GitHub API.
- Paper: "CHIA: An open-source framework for principled, agentic AI-driven hardware/software co-design research", arXiv 2606.27350. Authors: Angela Cui, Ferran Hermida-Rivera, Jack Toubes, Raghav Gupta, Jim Fang, Chengyi Lux Zhang, Ella Schwarz, Junha Kim, Yakun Sophia Shao, Borivoje Nikolic, Christopher W. Fletcher, Sagar Karandikar. Source: https://arxiv.org/abs/2606.27350
- **The acronym is never expanded** in the README, the paper title/abstract, or the hackathon page. Anyone writing "CHIA (Chip … )" is guessing. [Note: I searched the paper text and site; no expansion found.]
- Built by the SLICE lab at UC Berkeley — "the same group behind widely-used research platforms such as RISC-V, Chipyard, FireSim, BOOM, and Hammer". Source: https://agentic-arch.org/hackathon.html
- Five case studies in the paper: (1) RTL-to-gem5 alignment, (2) LLM-driven microarchitectural feature implementation, (3) IPC-aware critical-path optimization, (4) evolutionary architectural discovery, (5) maintainer-friendly agentic GitHub issue fixing (CIRCT).

### A.2 The hackathon — verbatim organizer language

Announcement (2026-08-18): https://chialoops.ai/blog/chia-hackathon-a3-micro-2026/
Full call: **https://agentic-arch.org/hackathon.html** (this is the hackathon page; it exists and I fetched it in full)

Key verbatim quotes — **this is what judges are optimizing for**:

> "Participants will use CHIA to build and share the **most novel, creative agentic loop(s)** to address challenges across HW/SW co-design."

> "Participants will make those loops **accessible to the community as composable building blocks** integrated into the open-source CHIA framework, with access to direct support from the CHIA developers."

> "Strong loops **may be upstreamed into mainline CHIA**, so the community can build on them as composable blocks."

> "Adding a new tool and demonstrating agentic capabilities within it is also welcome in the hackathon!"

From the A³ home page: https://agentic-arch.org/

> "Participants develop agentic approaches to solve real-world problems in architecture, VLSI, HW/SW co-design, **and compilers**. Solutions are built in the open-source CHIA framework to enable rapid prototyping and to foster a **reusable and composable ecosystem** of AI-driven co-design flows."

**Judging body**: "Submissions are judged by the A³ workshop's program committee." No numeric rubric, no weighted criteria, no scoring sheet is published anywhere I could find. **[UNVERIFIED: there is no public judging rubric.]** The only stated selection signal is the sentence above ("most novel, creative agentic loop(s)") plus the A³ CFP topic list.

**A³ CFP topics of interest** (https://agentic-arch.org/call-for-papers.html) — the PC's own stated interests, and this matters enormously for this proposal:

> "**Infrastructure & Methodology**: The scaffolding that lets agents do hardware/software co-design well: **benchmarks and metrics for agentic hardware-design tasks**; simulation techniques for facilitating agentic design exploration; debugging agent trajectories in design flows."

Also notable: the A³ review process is described as an "**AI-Native Review Process**, a collaboration between human experts and AI reviewers" — AI agents with different personas write reviews that inform (but do not determine) human PC decisions.

**Dates / format** (from the hackathon page):
- Proposals: **one page max**, due Aug 25 (long-term funding); short-term funding registration until Sep 13.
- Final submission Sep 24 AoE: **a 4-page paper** + "Your loop, open-sourced" with results.
- Winners Sep 26. Workshop Nov 1, MICRO 2026, Athens.
- Prizes: 1st $750 + NVIDIA RTX 5080; 2nd $500; 3rd $250; top-10 teams ~$1,500 travel funding each (IEEE CS TCMM).
- Sponsors: Google (GCP + Gemini credits + cash), NVIDIA (GPU), IEEE CS TCMM (travel).
- **UC Berkeley affiliates are not eligible to participate.**

**Suggested problem tracks** (verbatim list, condensed): architectural/microarchitectural bug discovery in BOOM; mid-level cache design in Chipyard; agentic formal verification; autonomous verification collateral (UVM/formal); agent-in-the-loop RTL-to-GDS; FPGA board porting for FireSim; power optimization; cross-SoC cache hierarchy optimization; full-stack DSA co-design; block-level microarchitecture analyses; "Add compatibility for new platforms in CHIA, e.g. Scarab, OpenPiton, etc. and demonstrate agentic capabilities"; reusable CHIA blocks on NVIDIA-accelerated infra; training/finetuning specialized models. "Submitting your own ideas is also welcome!"

**Note: "benchmark" does not appear in the hackathon's suggested problem tracks.** It appears only in the *workshop paper* CFP.

### A.3 The existing CIRCT case study (paper §5.5)

Verbatim from https://arxiv.org/html/2606.27350v3:

> "we ran the loop on **16 randomly selected GitHub issues** … Of the 16 issues the loop examined, 11 were determined to be bugs, four of which did not have unambiguous solutions, leaving seven issues entering the reproduction phase. In this stage, two of the seven could not be reproduced … Our loop successfully fixed the remaining five bugs, and **we submitted pull requests for the three of them** that were not labeled as good first issues."

> "**All three of our PRs have been merged into the main branch of the CIRCT repository.**"

> "we discussed closely with maintainers of the project to ensure our contributions were of a **reasonable quantity and quality**."

Also: a human reviewed each change (~1 hour/issue) and hand-wrote the PRs, in compliance with LLVM's AI tool policy; no PRs for "good first issues". There is a second loop for responding to PR review comments.

Docs: https://docs.chialoops.ai/en/latest/case-studies/circt-issue-solving.html (redirect target of chialoops.ai/circt-pr-fixer).
Code: https://github.com/ucb-bar/chia/tree/main/examples/circt_issue_solver

### A.4 Signals about other participants

- 18 public forks of `ucb-bar/chia`, several pushed in Sep 2026 (e.g. `zxc12523/chia`, `5ji653m6/chia`, `copparihollmann/chia`). **No public project descriptions.** [UNVERIFIED: I could find no public statement of what any other team is building.]
- Open PRs on `ucb-bar/chia` from non-Berkeley handles: #70 "feat(codex): harden restricted and resumable execution" and #69 "feat(examples): add Claude loop topology examples" (both `urd00m`), #71 (`is-hoku`). These look like community/participant contributions, i.e. **people are already upstreaming to CHIA during the hackathon window** — the "upstream PR to chia" deliverable is not itself differentiating.
- The `chialoops` Google group has only 2 threads; nothing about competing projects. https://groups.google.com/g/chialoops

---

## B. Fact-check of the proposal's claims

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| i | "existing CIRCT case study upstreamed three PRs" | **VERIFIED** | Paper §5.5: "All three of our PRs have been merged into the main branch of the CIRCT repository." Spot-check: llvm/circt PR #10648 "[FIRRTLToHW] Fix firrtl enum lowering" by `jack2bs` (a CHIA developer), merged 2026-06-17. |
| ii | "~16 issues" | **VERIFIED** | Paper Table 5 + text: "16 randomly selected CIRCT GitHub issues". |
| iii | "no public task set" | **VERIFIED** | The case-study docs describe sampling *open* issues live (`triage.py`); no fixed instance list is published. Caveat: `ucb-bar/chia` *does* have a submodule `examples/benchmarks` → `ucb-bar/chia_benchmarks`, but I inspected it: it is Embench/riscv-tests/µbench **workloads for simulation**, not an agent task set. The claim survives, but the wording invites an easy "we do have a benchmarks repo" rebuttal. |
| iv | "the adapter is CIRCT-specific" | **VERIFIED** | `examples/circt_issue_solver/README.md`: "`config.py` pins the repo… It defaults to llvm/circt; **the only supported change here is pointing it at a CIRCT fork** — the rest of the flow still assumes CIRCT." `config.py` is literally 4 lines with `GITHUB_REPO = "llvm/circt"`. |
| v | "prebuilt libLLVM/libMLIR tarballs" avoid compiling LLVM | **VERIFIED — but already done upstream** | CIRCT ships `circt-full-shared-linux-x64.tar.gz` on every `firtool-*` release (15 releases between 2026-05-25 and 2026-09-09, i.e. ~weekly). **CHIA already uses exactly this**: `dockerfiles/ChiaCirctBaseDockerfile` pins `CIRCT_VER=firtool-1.148.0`, downloads that tarball, and its own comment says "The CIRCT release tarball's **prebuilt libLLVM*/libMLIR*** require GLIBC 2.36/2.38". The proposal presents as its own enabling trick something the maintainers shipped months ago. Separately: whether a release tarball's LLVM pin ABI-matches an *arbitrary historical parent commit* is **[UNVERIFIED]** and is the real technical risk. |
| vi | "Verilator has a fast regression suite suitable as second target" | **CONTRADICTED / at best unsupported** | `verilator/verilator` `test_regress/t/` contains **4,312** Python test drivers (GitHub tree API, untruncated). Verilator docs: "There are thousands of tests"; "for faster completion you may want to run the regression tests with OBJCACHE enabled and in parallel on a machine with many cores"; "Running regression may exhaust resources on some Linux systems, particularly file handles and user processes. Increase these to respectively 16,384 and 4,096." No published wall-clock figure **[UNVERIFIED]**, but "fast" is not defensible. |
| vii | GPT-4o / Gemini 1.5 Pro as "frontier" in Sep 2026 | **CONTRADICTED** | **Gemini 1.5 Pro is gone** — not even listed on Google's deprecations page any more; `gemini-1.5-pro-002` was discontinued 2025-09-24. Google's live model list (ai.google.dev/gemini-api/docs/models) shows current ids `gemini-3.1-pro-preview` (flagship Pro, preview), `gemini-3.8-flash` (current stable Flash, "Our most intelligent Flash model"), `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-2.5-pro`. **GPT-4o is three-plus generations stale**: OpenAI's live models page lists `gpt-6-astra` as flagship ("Our most capable model") and `gpt-5.6-sol` beneath it; `gpt-4o-2024-05-13` is scheduled for shutdown 2026-10-23 and GPT-4o was retired from ChatGPT 2026-02-13. Bonus error: **`Qwen/Qwen3-32B-Instruct` does not exist** on Hugging Face (404/401); the current open-weights model a judge expects is **`Qwen/Qwen3.8-27B`** (Apache-2.0, dense 27B, Aug 2026). **Fourth error in the same table cell**: the cost table bills GPT-4o "via Google credits" — Google Cloud does not resell OpenAI models, so that line item cannot be executed as written. See §G.1 / §G.3. |
| viii | "`chia job submit` reproduces any result row" | **VERIFIED (command exists)** | CHIA CLI reference: Job Management — "`chia job <subcommand>`… Proxies to `ray job` — `submit`, `status`, `logs`, `list`, `delete`, etc. all forward." |
| ix | "SWE-bench-Lite-scale" for 40–80 tasks | **CONTRADICTED** | SWE-bench Lite = **300 test instances** (+23 dev). 40–80 is ~15–27% of Lite. |

---

## C. Landscape — what a judge already knows exists

This is the section that most changes the verdict. Three directly-adjacent benchmarks shipped in the last five months, and **none of them is cited in the proposal**:

1. **LLVM-Bench** (arXiv 2607.00700, 2026-07-01) — "the first large-scale benchmark for LLVM issue resolution, containing **423 real-world, validated tasks**", plus **LLVM-Gym**, "a scalable evaluation platform that automates issue reproduction, patch application, compiler building, and test execution." Its construction pipeline is **near-identical to CIRCT-Bench's**: mine commit pairs → split into test patch / golden patch → verify the test patch *fails at the bug commit* → verify golden patch passes the full suite with no regressions → manual quality + **leakage-prevention** pass. Results: agents ≈6.21 %Resolved; their ensemble LLVM-Ens up to 21.99%. Golden patches: mean 3.36 files, median 2. **This is CIRCT-Bench's methodology, already published, at 5–10× the scale, on the parent project.** It does not cover CIRCT (0 mentions) or MLIR meaningfully (2 mentions) — that is the only gap left.
2. **HWE-Bench** (arXiv 2604.14709, 2026-04-16) — "the first large-scale, repository-level benchmark for evaluating LLM agents on real-world hardware bug repair tasks", **417 instances**, 6 projects (ibex, cva6, caliptra, rocket-chip, XiangShan, OpenTitan), containerized, fail→pass validation. Best agent resolves **70.7%**. HDL design repos, not compiler source.
3. **Phoenix-bench** (arXiv 2605.15226, 2026-05-13) — "a synchronized corpus of **511 verified Verilator instances from 114 GitHub repositories**, each shipped with the developer patch, design-flow labels, **fail-to-pass and pass-to-pass testbenches**, and a **Docker-pinned EDA environment**."

Plus the broader cluster the CHIA paper itself cites in §6: CVDP / Comprehensive Verilog Design Problems (Pinckney et al. 2025), ChipBench (Yu et al. 2026), HSCO-bench (Tsai et al. 2026), SLDB (Alvanaki et al. 2025), ResBench (Guo & Zhao 2025), HLS-Eval (Abi-Karam & Hao 2025). Also ComBench (arXiv 2603.27333) for compilation-error repair.

**The single most useful sentence in the entire CHIA paper, for this proposal** (§6, verbatim):

> "Building these benchmark suites on top of CHIA would streamline the process of comparing different design loops, and **we are interested in integrating these suites into CHIA**."

Judge perception, net: a CIRCT-specific repair benchmark is **genuinely unoccupied** (no CIRCT/MLIR repair benchmark exists — I searched and found none). But "SWE-bench-style repair benchmark, mined commits, Docker-pinned, fail→pass, contamination-controlled" is now a **well-trodden 2026 genre with at least three recent entries**, one of them on LLVM itself. A judge who knows LLVM-Bench reads this proposal and thinks: *"this is LLVM-Bench pointed at CIRCT, at a fifth of the scale, and they didn't cite it."* That is a survivable objection — but only if the proposal preempts it, and currently it does not.

Second perception risk: the maintainers explicitly said they want *existing* suites integrated into CHIA. A proposal that builds a *new small* suite instead of integrating a *named large* one is answering a question they didn't ask.

---

## D. Scores (1–5)

### D.1 Alignment with organizer/judging criteria — **3/5**

Genuinely split. On the plus side: A³'s CFP names "**benchmarks and metrics for agentic hardware-design tasks**" as an explicit topic of interest, and the PC that judges the hackathon is the same body; the A³ home page explicitly names "**compilers**" as a target domain; "reusable and composable" is the hackathon's own stated aim and the proposal's thesis; and "Strong loops may be upstreamed into mainline CHIA" maps exactly onto the upstream-PR deliverable. On the minus side, and it's heavy: the operative prize sentence is "**the most novel, creative agentic loop(s)**", and the hackathon's 13 suggested tracks contain **zero** benchmark items. This proposal deliberately holds the loop *fixed* (it evaluates CHIA's existing CIRCT loop) and innovates on the dataset around it. On the axis the money is attached to — loop novelty — the contribution is close to zero by construction. It is aiming at the workshop's paper criteria, not the hackathon's prize criteria.

### D.2 Clarity of the problem + why it matters — **4/5**

A judge can restate it in one sentence: "a reproducible, containerized set of CIRCT bug-fix tasks plus a repo-agnostic adapter so CHIA's repair loop can be pointed at any codebase." That is clear, and the Mine→Reconstruct→Containerize→Validate→Adapt→Evaluate spine is legible at a glance. Docked one point because the *why it matters* is asserted, not argued: the reader is told coverage is "thin" but never told what decision the benchmark would enable that cannot be made today, and the one quantitative anchor offered ("SWE-bench-Lite-scale") is wrong by ~4×, which undercuts the clarity it was meant to buy.

### D.3 Impact on CHIA specifically — **4/5**

This is the proposal's strongest axis. The maintainers wrote, in their own paper, that they are "interested in integrating these suites into CHIA", and `examples/benchmarks` is already a submodule slot in the repo — the socket exists. The adapter refactor is even more clearly wanted: the current `circt_issue_solver` is honest about being welded to one repo ("the rest of the flow still assumes CIRCT"), and generalizing the most maintainer-visible case study into `(build, test-select, repro-contract, regression-gate)` is a change a maintainer would plausibly merge on sight. Docked one point because part of the claimed infrastructure contribution (prebuilt libLLVM/libMLIR to avoid building LLVM) is **already in CHIA's own `ChiaCirctBaseDockerfile`**, and because 40–80 CIRCT tasks is narrower value to CHIA than wiring in one of the large suites its authors already named.

### D.4 Demo-ability / "wow" in a 5–10 min pitch — **2/5**

There is no demo moment in this statement. The artifacts are a funnel diagram, a task count, and a results table — the three least screenshot-able things in agentic AI. First place gives a talk at MICRO in Athens; the competing pitch is "watch the agent read a real bug report, reproduce it, patch it, and go green on the regression suite, live." Against that, "we validated 63 tasks and here is the attrition funnel" is a poster, not a keynote. The proposal has one latent demo asset it never names — `chia job submit` re-running any row of the results table to completion in front of the room — and it is buried in a parenthetical. Even that is a *reproducibility* demo, not a *capability* demo.

### D.5 Differentiation vs. the default submission — **4/5**

Strongly differentiated from "we ran CHIA on repo X and fixed N bugs" — which is almost certainly the modal submission, and which this proposal explicitly names and rejects. The problem is the *direction* of the differentiation: it differentiates by removing agentic novelty rather than adding it, which is differentiation away from the scoring axis. It will not be confused with anyone else's project; it may also not be recognized as the same kind of project the prize is for. Note also that "upstream PR against ucb-bar/chia" is not itself differentiating — non-Berkeley contributors already have PRs open on the repo during the hackathon window (#69, #70, #71).

### D.6 Credibility / rigor as perceived by judges — **3/5**

The *design* choices read as rigorous and would score 5 in isolation: a temporal hold-out and a contamination probe are exactly right for a 2026 repair benchmark (LLVM-Bench had to do leakage prevention by hand; doing it programmatically is a real improvement), and the "honest yield funnel" with all attrition reported is the kind of methodological honesty PCs reward. But credibility is a function of *execution details*, and the details leak badly: three wrong model identifiers in one paragraph (Gemini 1.5 Pro is fully shut down; GPT-4o is three generations past frontier, with `gpt-6-astra` now listed as OpenAI's flagship; `Qwen3-32B-Instruct` does not exist, while the model a judge would actually expect — `Qwen/Qwen3.8-27B`, Apache-2.0, dense 27B — shipped in Aug 2026), a budget line that bills an OpenAI model to Google credits, a 4× error on SWE-bench Lite's size, an unsupported "SpinalHDL → CIRCT" claim in the opening sentence (§G.3), an "enabling trick" that is already in the host's Dockerfile, and zero citations to the three closest 2026 benchmarks. A reviewer — human or, in A³'s AI-native process, an AI persona that will absolutely check model names — reads those and downgrades everything else. Net: the rigor is real but the surface says otherwise.

### D.7 Over-promise / kitchen-sink risk — **2/5 (high risk)**

Counting the promises: a mining pipeline, 40–80 validated tasks, a Docker image family, a repo-agnostic adapter interface, a second repo (Verilator), a frontier-vs-open-weights evaluation, a temporal hold-out, a contamination probe, a per-phase failure taxonomy, one-command reproduction, an upstream PR to `ucb-bar/chia`, **and** live-backlog PRs to CIRCT itself. That is five deliverable classes across two repos and two model families, plus PRs to two upstream projects, one of which (LLVM/CIRCT) has an AI tool policy requiring disclosure, human-in-the-loop review, and no work on "good first issues" — i.e. an outcome the team does not control. Any one slip turns "we shipped the benchmark" into "we shipped part of everything." Judges read a list this long as a team that has not chosen, and the 4-page final paper cannot do justice to all of it.

**Unweighted mean: 3.1/5.**

---

## E. Concrete weaknesses in the statement itself

1. **The headline object is not the judged object.** The prize sentence says "most novel, creative agentic **loop(s)**." CIRCT-Bench's headline is a dataset + harness, with the loop held constant as a control. This is the single biggest problem and everything else is secondary.

2. **"Reframing the contribution from a one-off model result to reusable infrastructure" is a story judges *partially* reward — and it is aimed at the wrong critic.** "Reusable and composable" is verbatim the hackathon's aim, so the *value* lands. But the sentence positions the project as a corrective to the organizers' own paper, and the specific correction is wrong on the facts: the paper says the 16-issue scope was chosen *deliberately*, in consultation with maintainers, "to ensure our contributions were of a reasonable quantity and quality." Calling that "thin benchmark coverage" mischaracterizes a maintainer-friendliness decision as an oversight, in front of the people who made it. Same story, reframed as "you wrote that you want benchmark suites integrated into CHIA — here is the first one," costs nothing and removes the edge.

3. **Verilator as second target is a dilution, on three counts.** (a) It is already a first-class CHIA-supported tool (listed on the hackathon page; `dockerfiles/VerilatorRunDockerfile`, `examples/common/verilator.py`), so "we added Verilator" reads as less than it is. (b) It is another C++/CMake compiler — proving a CIRCT adapter also drives Verilator proves very little about repo-agnosticism; the interesting generality is a differently-shaped repo. (c) Its suite is 4,312 test drivers and the docs warn about exhausting file handles and process limits — not the "fast regression suite" the statement implies. Meanwhile **gem5 — the genuinely different target, already a CHIA case study — is deferred to future work**, which is exactly backwards. The organizers' own track list even hands you the better answer: "Add compatibility for new platforms in CHIA, e.g. Scarab, OpenPiton."

4. **The ≤2-source-file filter will read as a triviality filter, even though it isn't.** LLVM-Bench's golden patches average 3.36 files with a median of 2, so ≤2 sits right at the median — defensible. But nothing in the statement says that, so the judge supplies their own prior: "≤2 files + must add a lit test = they kept the easy ones." Combine with "40–80 tasks" and the unstated expected resolve-rate, and the reader cannot tell whether the result will be 20% (interesting, like LLVM-Bench) or 85% (a saturated benchmark nobody needs). One sentence citing the LLVM-Bench distribution would flip this from a weakness to a strength.

5. **No headline number a judge can carry out of the room.** Every memorable hackathon pitch has one integer. This statement's numbers are all ranges and all about the *apparatus*: 40–80 tasks, ≤2 files, 2 repos. There is no "X% → Y%", no "N bugs the loop found that humans hadn't", no "$Z per fix". Compare what is already sitting in the CHIA paper unexploited: 16 issues in **under 45 minutes**, **$4.18** of tokens per issue across four phases, and a human review cost of **~70 minutes per issue** — that last number is a ready-made denominator for a "we cut maintainer review time by X%" headline.

6. **The title is accurate and forgettable.** "CIRCT-Bench: A Reproducible Repair Benchmark and Repo-Agnostic Adapter for CHIA" has two nouns joined by "and" — the classic signature of a project that hasn't chosen. It also collides conceptually with `ucb-bar/chia_benchmarks`, an existing submodule in the repo that means something else entirely (simulation workloads).

7. **"Doing this deliberately reads as rigor; omitting it reads as naivety" must be deleted.** It is a note-to-self about how the reviewer will perceive the authors, left inside the document the reviewer is reading. It converts a genuine methodological strength (contamination control) into visible reviewer-management, and in A³'s AI-native review process it is exactly the sort of sentence an AI reviewer persona will quote back. One line of self-inflicted damage.

8. **Stale and nonexistent model names, in a hackathon whose prize sponsor is Google.** Gemini 1.5 Pro has been shut down for a year; the sponsor is handing out Gemini and GCP credits and CHIA ships `cluster_antigravity.yaml` and `cluster_opencode_vertex.yaml` in the very example being extended. Proposing GPT-4o (an OpenAI model, three generations stale — OpenAI's own models page now lists `gpt-6-astra` as flagship) plus a dead Gemini plus a Qwen id that does not exist signals that the authors have not run the thing they are proposing to evaluate. Worse, the cost table proposes to pay for **GPT-4o "via Google credits"**, which is not a purchasable configuration. And the open-weights slot is filled by a phantom id at a moment when a genuinely strong, Apache-2.0, single-GPU open model exists (`Qwen/Qwen3.8-27B`) — so the error costs the proposal its best available story, not just its accuracy. See §G.

9. **"SWE-bench-Lite-scale" is a 4× overclaim in the first paragraph.** Lite is 300 instances; the target is 40–80. Any reviewer who knows SWE-bench — i.e. all of them — catches this in the first ten seconds.

10. **Three closely-adjacent 2026 benchmarks go uncited.** LLVM-Bench (423 tasks, same pipeline, parent project, July 2026), HWE-Bench (417 tasks, April 2026), Phoenix-bench (511 Verilator instances, Docker-pinned, fail-to-pass + pass-to-pass, May 2026). Their absence doesn't just look like a literature gap — it makes the "honest yield funnel is itself a methodological contribution" claim indefensible, since LLVM-Gym already automates the same four stages.

11. **"Attempted live-backlog PRs to CIRCT" is an uncontrollable deliverable with a policy surface.** LLVM's AI Tool Policy requires disclosure, a human able to answer review questions, and forbids AI work on "good first issues"; the CHIA team budgeted ~70 minutes of expert human review per PR. Promising upstream PRs to a third party inside a scoring window means promising something reviewers may simply not merge in time — and the maintainer-burden angle is the one thing the CHIA authors were most careful about.

12. **Format compliance.** The hackathon asks for a **one-page maximum** proposal (task overview, methodology, expected results, cost estimate); this is two pages. The final submission is a **4-page paper** plus the open-sourced loop. Minor relative to everything above, but a proposal arguing for methodological rigor should not overrun the stated limit.

---

## F. Verdict + rewrite

### F.1 One-line verdict

**NEEDS REFRAMING** — confidence **medium-high (~75%)**. Single biggest reason: the prize is awarded for "the most novel, creative agentic **loop(s)**", and this proposal's headline deliverable is a dataset built *around* a loop it deliberately holds fixed. As written it is a strong A³ *workshop paper* in the "Infrastructure & Methodology" track and a middling *hackathon* entry. It is very likely to place top-10 (travel funding, poster); it is unlikely to take top-3 (cash, GPU, talk) without a loop-first reframe.

Residual uncertainty is real and worth stating: there is **no published rubric**, the PC's own CFP explicitly lists "benchmarks and metrics for agentic hardware-design tasks" as a topic of interest, and the CHIA authors wrote that they want benchmark suites integrated into CHIA. If the PC judges on workshop-paper criteria rather than hackathon-prize criteria, this proposal's ceiling rises sharply. That is the bet the current framing makes, and it is not a crazy bet — just an avoidable one, since the reframe below keeps the entire benchmark and adds the loop back.

### F.2 Proposed sharper title + one-liner

**Title:** `CIRCT-Gym: a self-scoring repair loop for CHIA`

**One-liner a judge can repeat:**
> "They built the scoreboard for CHIA's repair loops — 60-odd verified CIRCT bug-fix tasks that replay in one command — and then used it as a fitness function: the loop reads its own failure taxonomy, rewrites its own prompts and tool contracts, and goes from X% to Y% on held-out post-cutoff bugs. Same loop, no code changes, then pointed at a second repo."

The benchmark is unchanged. It has been demoted from *the deliverable* to *the instrument*, and an agentic loop has been promoted into the headline. That single move fixes D.1 (alignment), D.4 (demo), and D.7 (focus) simultaneously.

### F.3 CUT

- The phrase "**Doing this deliberately reads as rigor; omitting it reads as naivety.**" — unconditionally, first edit.
- "**SWE-bench-Lite-scale**" — replace with the literal number ("~60 tasks") or a correct comparator.
- **GPT-4o, Gemini 1.5 Pro, Qwen3-32B-Instruct** — replace with exactly these three ids: frontier = **`gemini-3.1-pro-preview`** (sponsor's flagship Pro, and the only one the Google credits can actually buy) with **`gemini-3.8-flash`** as the cheap-tier comparator; open-weights = **`Qwen/Qwen3.8-27B`** (Apache-2.0, dense 27B, single A100-80GB in BF16). Drop the OpenAI column entirely, or budget it separately — `gpt-6-astra` / `gpt-5.6-sol` cannot be billed to Google credits. See §G.1.
- **Verilator as the headline second target** — demote to a stretch goal, or swap for a differently-shaped repo (gem5, or OpenPiton/Scarab per the organizers' own track list).
- **"Live-backlog PRs to CIRCT" as a promised deliverable** — keep as "if one clears human review in time, we'll report it"; do not list it as an expected result.
- The **frontier-vs-open-weights matrix** as a headline result — one strong model plus one open-weights model is enough; the 2×2 is apparatus, not insight. **[AMENDED 2026-09-11 — see §G.2: the comparison should not be cut, it should be converted into the loop's decision variable. A table of models × resolve-rate is still apparatus; a loop that *decides at runtime* whether to stay on the local open model or escalate to the sponsor's API is not.]**
- The claim that **prebuilt libLLVM/libMLIR** is a novel enabler — state it as "we reuse CHIA's existing `chia-circt-base` approach, generalized to a per-pin-window image family." Credits the hosts and shows you read their code.

### F.4 ADD

- **Quote the CHIA paper's own §6 sentence**: "we are interested in integrating these suites into CHIA." One line converts the entire framing from critique-of-hosts to executing-hosts'-roadmap.
- **Cite LLVM-Bench, HWE-Bench, Phoenix-bench in one sentence** with the differentiator: *none targets a hardware-compiler source tree; LLVM-Bench covers LLVM but not CIRCT/MLIR hardware dialects; HWE-Bench and Phoenix-bench cover HDL designs, not the compiler that lowers them.* This turns the biggest "already exists" objection into evidence of taste.
- **One headline number, committed to up front.** Best available anchor from the CHIA paper itself: ~70 minutes of expert human review per issue, and $4.18 of tokens. "We cut maintainer review time per accepted fix from ~70 min to N" is a number a judge repeats at dinner.
- **An explicit demo moment**, named in the proposal: `chia job submit` replaying a failing row live, red → green, in front of the room; plus the before/after score jump from the self-tuning pass.
- **One sentence defending the ≤2-file filter** with the LLVM-Bench distribution (mean 3.36, median 2), plus a stated expected resolve-rate band so the result is interpretable in advance.
- **A named non-goal**: e.g. "we do not attempt feature requests or multi-file refactors." Naming what you will not do is the cheapest possible antidote to kitchen-sink perception.

### F.5 REFRAME

- **From** "your benchmark coverage is thin and your adapter is CIRCT-specific" **to** "your paper says you want benchmark suites in CHIA; your `circt_issue_solver` README says the flow assumes CIRCT; we're doing both."
- **From** "benchmark + adapter" (two nouns, no verb) **to** "a loop that measures and then improves itself, and the harness that makes that possible."
- **From** "frontier vs open-weights on a temporal hold-out" as a headline result **to** one line of methods under a contamination footnote. **[AMENDED 2026-09-11 — §G.2 supersedes this: promote it to the loop's routing policy instead of demoting it to a footnote.]**
- **From** "the funnel is itself a methodological contribution" **to** "the funnel is how we prove the tasks are real" — the funnel is evidence, not a contribution, and LLVM-Gym already automates the same stages.

### F.6 A different problem statement that would likely beat this one

**"The loop that knows when to shut up."** CHIA's CIRCT case study is explicitly about *not* extracting work from maintainers — it filters 16 issues down to 3 PRs, and still needs ~70 minutes of expert human review per PR. Build a CHIA loop whose objective is not resolve-rate but **maintainer-minutes-per-accepted-fix**: a calibrated self-assessment stage that outputs a confidence score and abstains below threshold, a reviewer-simulator agent that pre-runs the objections a CIRCT maintainer would raise, and an evidence bundle (repro script, lit test, regression delta, blast-radius diff) that makes a human's accept/reject decision a 5-minute read instead of a 70-minute audit.

Why it would beat CIRCT-Bench on this hackathon's axes: it is unambiguously **a loop** (the prize noun), it inherits CHIA's own most sympathetic framing (LLVM's AI policy, maintainer burden, "no slop") so it flatters rather than corrects the hosts, it demos beautifully (side-by-side: naive agent floods 9 PRs, calibrated loop submits 2 and abstains on 7, with the abstention reasons readable on screen), it produces a single memorable number (70 min → N min), and it is composable in exactly the sense the hackathon asks for — an "abstain + evidence-bundle" block drops into *any* CHIA repair loop, for any repo. Crucially, **it needs a held-out task set to measure any of that** — so the CIRCT-Bench work becomes the load-bearing infrastructure underneath it rather than a competing headline. Same team, same pipeline, same 40–80 tasks; a loop on top, and a story judges can retell.

---

## G. Addendum (2026-09-11): current open-weights model, story impact, LLM-drafted-proposal checklist

Trigger: the proposal's open-weights slot names `Qwen3-32B-Instruct`, an id that does not exist. The current Qwen open-weights model is **`Qwen/Qwen3.8-27B`**. That is not a trivial correction — it changes what the open-weights column *means*, and therefore what story the proposal can tell. This addendum re-derives the model landscape from primary sources, re-examines §F.3's "the 2×2 is apparatus, not insight" ruling in light of it, and converts "the proposal was drafted without fact-checking" into a pre-submission checklist.

### G.1 The model landscape a judge assumes in Sep 2026

#### G.1.a `Qwen/Qwen3.8-27B` — verified specification

All from the official Hugging Face model card and its `config.json` unless marked otherwise.

| Property | Value | Source |
|---|---|---|
| HF id | `Qwen/Qwen3.8-27B` (FP8 sibling: `Qwen/Qwen3.8-27B-FP8`) | model card / Qwen org page |
| License | `apache-2.0` | model card |
| Architecture | **Dense**, not MoE. 64 layers, `hidden_size` 5120, 24 attention heads, **4 KV heads**, `head_dim` 256, `torch_dtype` bfloat16, `vocab_size` 248320 | `config.json` |
| Attention | **Hybrid**: 3 linear-attention (Gated DeltaNet) layers to 1 full-attention layer, repeated 16× → **16 full-attention layers out of 64**. `linear_num_key_heads` 16, `linear_num_value_heads` 48, `linear_key_head_dim`/`linear_value_head_dim` 128, `linear_conv_kernel_dim` 4 | `config.json` |
| Context | 262,144 native (`max_position_embeddings`), extensible to ~1,000,000 via YaRN/RoPE scaling | model card |
| Instruct/Thinking split | **No split — one unified model.** Thinking mode is on by default and disabled per request with `"enable_thinking": False`. Recommended sampling differs per mode (thinking: `temp=1.0, top_p=0.95, top_k=20`; instruct: `temp=0.7, top_p=0.80, top_k=20`) | model card |
| Modality | Vision-language — native image and video understanding | model card |
| Release | Citation block in the model card gives `month = {August}, year = {2026}`. The exact day **2026-08-14** appears only in secondary/aggregator write-ups — *aggregator-sourced, treat as approximate* | model card (month); aggregators (day) |

**Published scores (official model card table; comparator column is Qwen3.6-27B):**

| Benchmark | Qwen3.8-27B | Qwen3.6-27B |
|---|---|---|
| SWE-bench **Pro** | 61.7 | 53.5 |
| Terminal-Bench 2.1 | 73.0 | 63.4 |
| QwenSWEBench (in-house) | 79.0 | 49.3 |
| LiveCodeBench v6 | 90.3 | 83.9 |
| GPQA Diamond | 89.2 | — |
| IFBench | 79.5 | — |
| OSWorld-Verified / WebArena-Verified / AndroidWorld | 84.3 / 64.8 / 81.9 | — |

**Important for the proposal**: Qwen publishes **SWE-bench Pro**, not SWE-bench **Verified**, for this model. Any sentence in the 4-page paper that writes "SWE-bench Verified" next to a Qwen3.8-27B number is a fabricated figure. The card also states SWE-bench Pro was run under the Claude Code harness at `temp=1.0, top_p=0.95`, 256K context, with "problematic tasks corrected and all baseline models re-evaluated" — i.e. the number is **not** directly comparable to a third party's SWE-bench Pro leaderboard entry. Cite the harness with the number or don't cite the number.

**Larger open-weight Qwen3.8 models exist, and neither substitutes for the 27B here** (Qwen HF org listing):
- `Qwen/Qwen3.8-2.4T-A95B` (+ `-FP8`): 2.4T total / 95B active MoE, 512 experts (10 routed + 1 shared). **License is `qwen3.8-max`, NOT Apache-2.0.** Scores Terminal-Bench 2.1 86.6, SWE-bench Pro 67.7. vLLM's own release post says inference needs "at least two NVIDIA B300 / AMD MI355X nodes (or a single node for the FP4 quantized version)" — irrelevant to a single-GPU story.
- `Qwen/Qwen3.8-Flash-Next` (+ `-FP8`): 180B, listed on the Qwen org page. License not checked this session **[UNVERIFIED]**.

**vLLM support**: the model card names vLLM (and SGLang, TokenSpeed) as official serving frameworks and links a "vLLM: Qwen3.8 Recipe". vLLM's release post (2026-08-12) states the Qwen3.8 family "reuses the Qwen 3.5 architecture and runs on vLLM from day one, with no architecture changes required" — that statement is made explicitly about `Qwen3.8-2.4T-A95B`. I could **not** find a 27B-specific vLLM recipe page (the obvious URL 404s) and the `supported_models` page I fetched lists only `Qwen3ForCausalLM` / `Qwen3MoeForCausalLM` / `Qwen3NextForCausalLM`. **Pin and test an exact vLLM version before promising this in the paper.**

**Single A100-80GB in BF16 — computed, and the answer is yes:**
- Weights: 27B × 2 B = **54 GB** (the HF org page displays "28B", i.e. up to **56 GB** including the 248320 × 5120 ≈ 1.27B-parameter embedding).
- KV cache: only the **16 full-attention** layers grow with sequence length. 2 (K+V) × 4 KV heads × 256 head_dim × 2 B = 4,096 B per token per layer × 16 layers = **65,536 B = 64 KiB per token**. → 32K ctx ≈ **2 GiB**; 128K ctx ≈ **8 GiB**; 262K ctx ≈ **16 GiB**.
- The 48 linear-attention layers carry a *constant-size* recurrent state per sequence (order 10¹ MB), not a per-token cache.
- **Totals: ~62–64 GB at 128K context, ~70–72 GB at full 262K.** 128K comfortably fits 80 GB with headroom for activations and CUDA graphs; 262K is nominally within budget but tight at any concurrency. 128K is far more context than a CIRCT repair task needs. **Verdict: yes, one A100-80GB, BF16, no quantization required.**
- Caveat: A100 is Ampere. The `-FP8` checkpoint halves the weight footprint but Ampere has no native FP8 tensor cores, so on an A100 FP8 buys memory, not throughput. **[hardware generalization, not re-verified against an NVIDIA page this session]**
- Worth knowing: the **1st-place prize GPU is an RTX 5080 with "16 GB GDDR7"** (nvidia.com). The winning team cannot run this model on its own prize in BF16, and a 4-bit quant (~17 GB per aggregator reports) is marginal at best. Do not build a pitch line around "runs on the prize."

#### G.1.b Other credible open-weight candidates (Sep 2026)

Ids and licenses verified via the Hugging Face API this session; parameter counts from `safetensors` totals.

| Model | Size / type | License | Verdict for this proposal |
|---|---|---|---|
| **`Qwen/Qwen3.8-27B`** | 27B dense, VL, 262K | **apache-2.0** | **Pick this.** Only current candidate that is simultaneously frontier-adjacent on coding, genuinely permissive, and single-GPU. |
| `Qwen/Qwen3.8-2.4T-A95B` | 2.4T total / 95B active MoE | `qwen3.8-max` (conditional) | No. Multi-node, non-Apache — kills both the on-prem and the license story. |
| `deepseek-ai/DeepSeek-V4-Pro` | ~1.60T params, `DeepseekV4ForCausalLM` MoE, created 2026-04-22 | **MIT** | Best license in the field, but ~1.6T — multi-node. `DeepSeek-V4-Flash` / `-Flash-0731` / `V4.1-Flash` are the deployable tier; sizes not checked **[UNVERIFIED]**. A credible alternative *only* if you drop the single-GPU claim. |
| `zai-org/GLM-5.3` (also `-Flash`, `-Flash-BF16`) | ~753B MoE, `GlmMoeDsaForCausalLM`, created 2026-08-25 | `other` / `glm-5.3` | Strong coder, but bespoke license + 753B. Wrong shape for an on-prem single-GPU argument. |
| `moonshotai/Kimi-K3` | exists on HF; size/license not checked **[UNVERIFIED]** | — | Agentic-orchestration reputation, but unverified license and large. Skip. |
| `Qwen/Qwen3-Coder-30B-A3B-Instruct` | 30B MoE / 3B active | Qwen (Apache for this line, **not re-verified**) | The cheap fallback if 27B dense is too slow — but it is a *previous-generation* coder model, and a judge will ask why you didn't use 3.8. |
| `Qwen/Qwen3-Coder-Next`, `Qwen/Qwen3-Coder-480B-A35B-Instruct` | Next-gen coder; 480B MoE | — **[UNVERIFIED]** | 480B is multi-GPU; `Coder-Next` is plausible but less well-known than 3.8-27B. |
| `openai/gpt-oss-120b` | ~117B MoE, MXFP4, created 2025-08-04 | **apache-2.0** | "Fits into an H100" per OpenAI's docs, so nearly single-GPU — but it is a **2025** model. Naming it in Sep 2026 reads almost as stale as naming GPT-4o. |
| Llama 4.x / Mistral | — | — | Not checked this session **[UNVERIFIED]**. Neither is the model a hardware-agentics judge would expect in Sep 2026; do not spend words on them. |

**Which single open-weight model would a knowledgeable judge expect?** `Qwen/Qwen3.8-27B`. Reasoning a judge would accept in one sentence: it is the newest genuinely *permissive* (Apache-2.0) release, it is **dense** so there is no expert-routing serving complexity, it fits **one** 80 GB GPU in BF16, CHIA's own `VLLMDockerfile` serves any HF id on CUDA out of the box, and its published coding numbers (SWE-bench Pro 61.7, Terminal-Bench 2.1 73.0) put it in the range where "local vs frontier" is an *open* question rather than a foregone conclusion. Every other open-weight contender fails at least one of those four tests.

#### G.1.c Correct current API ids

| Provider | Current ids (exact) | Source |
|---|---|---|
| **Google (sponsor)** | Flagship Pro: **`gemini-3.1-pro-preview`** (preview). Current stable Flash: **`gemini-3.8-flash`** ("Our most intelligent Flash model"). Also stable: `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-pro`, `gemini-2.5-flash`. | ai.google.dev/gemini-api/docs/models |
| **OpenAI** | **`gpt-6-astra` is in the API** — "Our most capable model, built for the hardest end-to-end work"; set `model` to `gpt-6-astra` in a Responses API request. Beneath it: `gpt-5.6-sol` (flagship for complex professional work), `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.6-cyber`, `gpt-5.5`, `gpt-5.3-codex` ("the most capable agentic coding model to date"). Open-weight: `gpt-oss-120b`, `gpt-oss-20b`. | developers.openai.com/api/docs/models |
| **Anthropic** | `claude-opus-5` (recommended default), `claude-fable-5-1` (demanding reasoning / long-horizon agentic), `claude-sonnet-5`, `claude-haiku-4-5`. All dateless ids are pinned snapshots. Reliable knowledge cutoffs: Fable 5.1 **Jun 2026**, Opus 5 **May 2026**, Sonnet 5 **Jan 2026**. | platform.claude.com models overview |

**Consequence for the cost table**: the proposal bills "GPT-4o / Gemini 1.5 Pro via Google credits", $500. Google Cloud does not resell OpenAI models. Either the frontier column is Gemini-only (and then the budget works), or the OpenAI column needs its own billing line. Anthropic models *are* available on Google Cloud (`claude-opus-5` etc. carry Google Cloud IDs), so if a second frontier vendor is wanted, Claude on Vertex is the one that Google credits can actually reach — that is a checkable, defensible substitution.

### G.2 Does the corrected model change the story?

**The case that it does (and it is stronger than §F.3 allowed).**

1. **The comparison stopped being rhetorical.** In the world the proposal was drafted in — GPT-4o vs a 32B — "open-weights baseline" meant "the small model scores near zero and we report it for completeness." With SWE-bench Pro 61.7 and Terminal-Bench 2.1 73.0 on a **27B dense Apache-2.0** model, the outcome of "can it fix a real CIRCT bug" is genuinely unknown in advance. A benchmark whose result is unknown in advance is worth running; one whose result is obvious is not. This is the single biggest change.
2. **The on-prem argument is real and judge-legible.** CIRCT itself is open source, so *this* corpus is not secret — but the audience is hardware companies whose RTL and internal compiler forks are trade secret and who cannot paste them into a frontier API. "Here is the measured gap between what you can run inside your own firewall and what you can only rent" is a question that room actually has. Note the honest limit: the benchmark demonstrates the *method* on public code; the IP claim is about transfer, and should be stated as such rather than overclaimed.
3. **CHIA already has the plumbing — verified, not assumed.** `ucb-bar/chia/dockerfiles/` contains **`VLLMDockerfile`** and **`OllamaDockerfile`** (alongside `OpenCodeDockerfile`, `AntigravityDockerfile`, `ClaudeCodeDockerfile`, `Gem5Dockerfile`, `VerilatorRunDockerfile`, `ChiaCirctBaseDockerfile`). The vLLM image builds on `vllm/vllm-openai`, takes **`VLLM_MODEL` = any Hugging Face model id**, serves on port 8200, and its own comment says "vLLM is GPU-first. The default base (`vllm/vllm-openai`) is CUDA/NVIDIA." So a local-open-weights executor is a **first-class, already-supported CHIA path**, and the team's contribution is a loop that *uses* it well rather than infrastructure it has to invent. That is the good kind of unglamorous.
4. **Sponsor and track fit is exact, not approximate.** Verbatim from the hackathon page, two of the thirteen suggested tracks name NVIDIA:
   > "Reusable CHIA blocks for agentic design workflows that run on NVIDIA-accelerated infrastructure and can be reused after the hackathon"
   > "Training or finetuning of specialized AI models on NVIDIA platforms to improve architecture/design agent performance"
   
   A vLLM-served open model on an NVIDIA GPU, wrapped in a reusable CHIA block, is the first of those read literally. And a loop that escalates to `gemini-3.1-pro-preview` spends Google's credits on Google's model — both sponsors are flattered by the same artifact, which is rare and worth engineering for deliberately.

**The counter, which still stands.** None of the above makes a *table* into a *loop*. "Model A resolves 34%, Model B resolves 41%, here is $/fix" is an eval result. The prize sentence has not moved: "the most novel, creative agentic **loop(s)**." A judge who reads a model-comparison table sees a well-executed experiment and awards it a poster. §E.1 is unchanged: the headline object must be the judged object.

**Therefore: make it loop-shaped. Three variants considered.**

**Variant A — confidence-gated cost-aware cascade ("stay local unless you're unsure").** `Qwen/Qwen3.8-27B` on vLLM is the *default executor* for every task. A calibrated self-assessment stage — grounded, not vibes: does the reproduction test actually fail at the parent revision, does the candidate patch flip it, does the regression gate stay green, how large is the blast radius — emits a confidence score. Below threshold the loop escalates that task to `gemini-3.1-pro-preview`. Headline metrics: **% of fixes that never left the local GPU**, and **$/accepted-fix** against the CHIA paper's own **$4.18/issue** baseline.
- *For*: unambiguously a loop; the escalation router is a genuinely composable block that drops into any CHIA repair loop for any repo (the hackathon's literal ask); needs the benchmark as its fitness function, so CIRCT-Bench becomes load-bearing infrastructure instead of a competing headline; demos in 90 seconds (local model attempts → gate fires → escalation → red-to-green, live); produces one integer a judge repeats.
- *Against*: cost-aware cascading is a known pattern in the serving literature. **Say so in the paper.** The novelty claim must be the *domain-grounded gate* (a compiler-repair confidence signal built from repro/regression evidence, not from token logprobs), not the idea of routing.
- *Risk*: if the 27B's confidence is uncalibrated, the policy collapses to "always escalate" and there is no result. Mitigation is a reliability diagram on the train split before the hold-out is touched — and that is itself a reportable figure.

**Variant B — distill frontier trajectories into the 27B (finetune).** Run a frontier model on the train split, collect successful trajectories, SFT/LoRA the 27B, measure lift on held-out post-cutoff tasks.
- *For*: hits the "Training or finetuning of specialized AI models on NVIDIA platforms" track verbatim — the most under-served of the thirteen.
- *Against*: **reject.** With 40–80 tasks *total*, there is no split that both holds out a test set and yields enough trajectories to move a 27B; LLVM-Bench has 423 tasks and even that is thin for SFT. Full SFT of 27B does not fit one A100-80GB (LoRA does, but on long agentic trajectories it is painful). Most likely outcome is a lift indistinguishable from noise, presented as a result — which is exactly the failure mode a rigorous PC punishes hardest. Also: a training run is not a loop either.

**Variant C — the self-scoring loop of §F.2 ("CIRCT-Gym"), with the 27B as the tunable target.** The loop reads its own per-phase failure taxonomy and rewrites its own prompts and tool contracts.
- *For*: self-improvement is the flashiest reading of "agentic loop"; retains the prior recommendation unchanged.
- *Against*: at 40–80 tasks, prompt self-rewriting overfits and the before/after delta is uninterpretable; the demo is a number moving, which is weak; and it needs the hold-out spent on tuning validation rather than on the headline claim.

**Pick: Variant A — and note it converges with §F.6.** §F.6 already proposed "the loop that knows when to shut up": a calibrated gate that **abstains** rather than burning maintainer minutes on a doubtful PR. Variant A proposes a calibrated gate that **escalates** rather than burning money on a doubtful local attempt. *These are one primitive with two consumers.* Build **one confidence gate** and wire it to two policies:
- **route**: local `Qwen/Qwen3.8-27B` → `gemini-3.1-pro-preview` only when the gate is unsure → metric **$/accepted-fix** vs the paper's $4.18, plus "% fixed without a token leaving the GPU";
- **abstain**: withhold the PR entirely when the gate is still unsure after escalation → metric **maintainer-minutes/accepted-fix** vs the paper's ~70 min.

That is a strictly better submission than either half: it is one reusable CHIA block, it demonstrates two policies on one mechanism (which is what "composable" means to these organizers), it is measured on a benchmark only this team has, it spends both sponsors' resources on their own products, and it reads as taste rather than as a model-comparison table. §F.2's "CIRCT-Gym" survives as the *name of the harness*, demoted from headline to instrument — which is what §F.2 wanted anyway.

**Updated verdict: NEEDS REFRAMING, confidence ~75–80%. Unchanged in direction; slightly firmer.**

Reasoning, stated plainly so this does not read as flip-flopping:
- The **diagnosis is identical** to §F.1. The prize is for loops; the proposal's headline is a dataset; correcting three model ids does not touch that. Nothing found today argues the current draft wins as written.
- Confidence moves up a few points, not down, because the drafting errors turned out to be **worse** than §B(vii) knew: it is not three stale ids but three stale ids **plus** a budget line that cannot be executed (OpenAI on Google credits) **plus** an unsupported technical claim in the opening sentence (SpinalHDL → CIRCT, §G.3). A reviewer who checks one of these checks all of them.
- What **does** change is the *prescription*. §F.3 said cut the frontier-vs-open-weights matrix and §F.5 said demote it to a methods footnote. Both are superseded: with a single-GPU Apache-2.0 model that is actually competitive, that axis is now the cheapest available way to buy simultaneously (a) loop shape, (b) NVIDIA-track alignment, (c) a dollar-denominated headline number, and (d) a reason the benchmark must exist. Deleting it would be throwing away the best asset the corrected facts created. Promote it — but promote it as a **decision the loop makes at runtime**, never as a table.

### G.3 LLM-drafted-proposal risk: the full checkable-claim inventory

Working assumption (per the request): the draft was produced without verification. No inference about *which* system produced it, and none is needed — the remedy is the same either way.

**Every checkable factual claim in the proposal text:**

| # | Claim (as written) | Status | Note |
|---|---|---|---|
| 1 | "LLVM/CIRCT transforms generator-based hardware descriptions (**Chisel**, …)" | **VERIFIED TRUE** | Chisel → FIRRTL → firtool/CIRCT is the canonical path. |
| 2 | "… (**SpinalHDL**) into optimized, synthesizable SystemVerilog" | **FALSE / unsupported — NEW FINDING** | SpinalHDL's own docs describe direct emission from its own backend: `SpinalConfig(mode=Verilog, …)` / `mode=VHDL`, and it also emits SystemVerilog — no CIRCT in the path. A GitHub issue/PR search over `llvm/circt` for "SpinalHDL" returns **`total_count: 0`**. This is the **first sentence of the proposal** and it is wrong. |
| 3 | "C++/MLIR/TableGen codebase" | **Needs human verification** | Almost certainly true (CIRCT is an LLVM/MLIR subproject) but not separately checked here; trivially confirmable from the repo's language stats. |
| 4 | "existing CIRCT case study that upstreamed **three PRs**" | **VERIFIED TRUE** | §B(i). All three merged per paper §5.5; PR llvm/circt#10648 spot-checked, merged 2026-06-17. |
| 5 | "**~16 issues**" | **VERIFIED TRUE** | §B(ii). Paper: "16 randomly selected GitHub issues". |
| 6 | "**no public task set**" | **VERIFIED TRUE**, with a caveat to preempt | §B(iii). `examples/benchmarks` → `ucb-bar/chia_benchmarks` exists but is simulation workloads, not an agent task set. Say so in one clause or invite the rebuttal. |
| 7 | "the adapter is **CIRCT-specific**" | **VERIFIED TRUE** | §B(iv). Verbatim in the example's own README. |
| 8 | "**SWE-bench-Lite-scale**" / "SWE-bench Lite scale for a hardware compiler" for 40–80 tasks | **FALSE** | §B(ix). Lite = 300 test instances (+23 dev). ~4× overclaim, in the first paragraph. |
| 9 | "A per-LLVM-pin-window Docker image using **prebuilt libLLVM/libMLIR tarballs** avoids compiling LLVM from source entirely" — framed as an architectural innovation | **TRUE but NOT NOVEL** | §B(v). CHIA's own `dockerfiles/ChiaCirctBaseDockerfile` already does exactly this and names "prebuilt libLLVM*/libMLIR*" in its comments. Presenting the hosts' trick as yours in front of the hosts. |
| 10 | Implicit: a CIRCT release tarball's prebuilt LLVM **ABI-matches an arbitrary historical parent commit** inside a pin window | **STILL UNVERIFIED — highest technical risk in the proposal** | The whole containerization plan rests on it. Resolve empirically in the W1 pilot; report the width of the usable pin window as a finding either way. |
| 11 | "Verilator (**fast regression suite**; second target)" | **CONTRADICTED** | §B(vi). 4,312 test drivers in `test_regress/t/`; docs warn about exhausting file handles and process limits. |
| 12 | "gem5 identified as **future work due to build cost**" | **Needs human verification** | Plausible, unmeasured. Note CHIA ships a `Gem5Dockerfile`, which weakens "too costly to build" as a reason. |
| 13 | "Every merged bug-fix commit that touches **≤2 source files and adds a lit/FIR/SV test**" | **Needs human verification — and it is the feasibility question** | Nobody has published what fraction of CIRCT bug-fix commits add a lit/FIR/SV test. If it is low, 40–80 is unreachable. §E.4's defense (LLVM-Bench golden patches: mean 3.36 files, median 2) makes ≤2 defensible, but only if cited. |
| 14 | "**Target: 40–80 validated tasks**" | **Needs human verification** | A projection, not a measurement. The W1 20-task pilot the proposal already schedules produces the real number; replace the range with it. |
| 15 | "`chia job submit` reproduces any result row" | **Command VERIFIED**, claim is a promise | §B(viii). `chia job <subcommand>` proxies to `ray job`. |
| 16 | "Frontier-model API … **GPT-4o / Gemini 1.5 Pro** via Google credits" | **FALSE ×3** | Gemini 1.5 Pro shut down; GPT-4o three generations stale (`gpt-6-astra` is now OpenAI's flagship); **and Google credits cannot buy an OpenAI model**. §G.1.c. |
| 17 | "Open-weights inference … **Qwen3-32B-Instruct**, 4-bit" | **FALSE (id does not exist)** | Replace with `Qwen/Qwen3.8-27B` — and drop "4-bit": it fits one A100-80GB in **BF16** at 128K context (§G.1.a). |
| 18 | "on **A100 spot** … **~40 GPU-hrs**" | **Needs human verification** | An estimate. Make it reproducible: state model, context length, concurrency, and tasks/hour measured in the pilot. |
| 19 | "**vLLM/OpenCode**" as the open-weights serving path | **VERIFIED TRUE** | `dockerfiles/VLLMDockerfile` (takes `VLLM_MODEL` = any HF id, CUDA-first) and `dockerfiles/OpenCodeDockerfile` both exist in `ucb-bar/chia`. |
| 20 | "Temporal hold-out (tasks **post model training cutoff**)" | **Partly unverifiable as designed — NEW FINDING** | Cutoffs are published for Anthropic (`claude-opus-5` May 2026, `claude-fable-5-1` Jun 2026). **Qwen does not publish a training cutoff for `Qwen/Qwen3.8-27B`** (none in the model card). So the hold-out cannot be defined *per model* for the open-weights arm. Fix: define the split by a single stated calendar date, justify it as post-dating every model's *release*, and say plainly that per-model cutoffs are unpublished for the open model — the contamination probe then carries the weight it was designed to carry. |
| 21 | Cost table sums to **$1,300** | **VERIFIED TRUE** | 500 + 300 + 250 + 250 = 1300. |
| 22 | Execution plan "Aug 29 – Sep 20" | **Consistent** | Final submission is Sep 24 AoE; the plan lands inside it. |
| 23 | Proposal is **two pages** | **NON-COMPLIANT** | §E.12. Hackathon asks for "one page max". |
| 24 | "Doing this deliberately reads as rigor; omitting it reads as naivety." | **Must be deleted** | §E.7. Reviewer-management text left inside the reviewed document. |

Tally: **7 verified true, 5 verified false or contradicted, 1 true-but-not-novel, 1 non-compliant, 1 must-delete, 8 still needing human verification.** Five of the six errors are in claims that take under sixty seconds each to check.

**Implication of A³'s AI-native review process.** A³ describes its review as an "AI-Native Review Process, a collaboration between human experts and AI reviewers" in which agents with different personas write reviews that inform human PC decisions. Checking a model identifier against a vendor's live models page is the cheapest, most mechanical, most reliably-executed check such a persona can run — it costs one fetch and returns a binary answer, and it is exactly the kind of check a human reviewer skims past. On the current draft it returns **four** hits clustered in the single paragraph that describes the experiment (`GPT-4o`, `Gemini 1.5 Pro`, `Qwen3-32B-Instruct`, and OpenAI-billed-to-Google-credits), plus a fifth in the opening sentence (SpinalHDL). The damage is not "stale citation" — it is that a reviewer reading errors concentrated in the *methods* concludes the experiment was never run, and every downstream claim (the yield funnel, the contamination probe, the temporal hold-out) inherits that doubt. A human reviewer forgives a stale id; a persona instructed to verify claims files it as a factual error, and that filed error is the first thing the human PC reads. **The asymmetry is brutal and the fix is an afternoon.**

**Pre-submission verification checklist (for the 4-page paper, Sep 24 AoE).** Assign an owner and a date to each line; nothing ships unchecked.

1. **Model ids, from the vendor's own live docs page, on submission day.** Every id pasted, not recalled: `gemini-3.1-pro-preview` / `gemini-3.8-flash` (ai.google.dev), `Qwen/Qwen3.8-27B` (the HF model card). For each id also record **who can bill it** — Google credits buy Gemini (and Claude on Vertex); they do not buy OpenAI.
2. **Every benchmark name, size, and score, from the primary artifact.** SWE-bench Lite = 300 (+23 dev) from the dataset card. Qwen3.8-27B = **SWE-bench Pro 61.7** and **Terminal-Bench 2.1 73.0** from the model card, *with the harness caveat quoted* — never "SWE-bench Verified", which Qwen does not publish for this model. LLVM-Bench = 423, HWE-Bench = 417, Phoenix-bench = 511, from their abstracts.
3. **Replace every projected number with the measured one from the W1 20-task pilot**: real task yield (not "40–80"), real per-task wall-clock and cost (not "~40 GPU-hrs"), and the measured width of the libLLVM/libMLIR ABI pin window (claim #10) — the one technical bet nobody has tested.
4. **Re-verify every claim about someone else's repo by opening it**: SpinalHDL's generation backends (claim #2 — as written it is wrong, fix or delete), `ucb-bar/chia/dockerfiles/` contents before claiming any Docker trick is new (claim #9), Verilator's `test_regress/t/` count before the word "fast" (claim #11), and `ucb-bar/chia_benchmarks` before "no public task set" (claim #6).
5. **State the temporal-hold-out cutoff as a single calendar date**, cite the published cutoff for each closed model used, and say explicitly that Qwen publishes none for `Qwen3.8-27B` (claim #20). Turning that gap into a stated limitation is worth more than pretending it isn't there.
6. **Grep the final PDF** for: every model id, every benchmark name, every number, every "first / novel / only / fast", and every claim containing another project's name. Each hit must have a URL in an author's notes. This is a 20-minute pass and it would have caught five of the six errors.
7. **Delete the two self-inflicted lines**: the "reads as rigor … reads as naivety" sentence (#24) and "SWE-bench-Lite-scale" (#8). Cut before anything else; they cost nothing to remove.
8. **Format compliance**: 4 pages for the final submission, and the accompanying loop actually open-sourced — the hackathon asks for both.

---

## Sources

| URL | What it supported |
|---|---|
| https://github.com/ucb-bar/chia | CHIA repo identity, description, license, README link set; repo tree (examples/circt_issue_solver, dockerfiles, examples/benchmarks submodule); issues/PRs/forks via GitHub API |
| https://arxiv.org/abs/2606.27350 and https://arxiv.org/html/2606.27350v3 | CHIA paper: authors, five case studies, §5.5 CIRCT case study (16 issues, 5 fixed, 3 PRs merged, Table 5/6 costs, ~70 min human review), §6 related work + "we are interested in integrating these suites into CHIA" |
| https://chialoops.ai/blog/chia-hackathon-a3-micro-2026/ | Hackathon announcement, Aug 18 2026, 1-page proposal, Aug 25 deadline, link to hackathon page, lead developers/PI |
| https://agentic-arch.org/hackathon.html | **Primary judging-criteria source**: "most novel, creative agentic loop(s)", "composable building blocks", "Strong loops may be upstreamed into mainline CHIA", full timeline, prizes, 13 suggested problem tracks, 4-page final paper + open-sourced loop, "judged by the A³ workshop's program committee", Berkeley ineligibility, supported tools incl. Verilator and CIRCT |
| https://agentic-arch.org/ | A³ scope; "real-world problems in architecture, VLSI, HW/SW co-design, and compilers"; "reusable and composable ecosystem"; organizers (Gonzalez/Google, Huang/NVIDIA, Jain/Google, Karandikar/Berkeley, Skarlatos/CMU, Yazdanbakhsh/GDM) |
| https://agentic-arch.org/call-for-papers.html | A³ topics incl. "Infrastructure & Methodology: … benchmarks and metrics for agentic hardware-design tasks"; 2–4 page format; AI-Native Review Process; dates |
| https://docs.chialoops.ai/en/latest/case-studies/circt-issue-solving.html | CIRCT loop is repo-pinned; no public task set; `fix_issues_submit.sh`, `review_submit.sh`, `chia up`/`chia down` |
| https://github.com/ucb-bar/chia/blob/main/examples/circt_issue_solver/README.md and config.py | Verbatim "the only supported change here is pointing it at a CIRCT fork — the rest of the flow still assumes CIRCT"; `GITHUB_REPO = "llvm/circt"`; loop phases (assess→reproduce→fix→verify→regression repair→writeup); "No GitHub writes" |
| https://docs.chialoops.ai/en/latest/user_guides/reference.html | CHIA CLI: `chia job <subcommand>` "Proxies to `ray job` — `submit`, `status`, `logs`, `list`, `delete`" → `chia job submit` exists |
| https://github.com/ucb-bar/chia/blob/main/dockerfiles/ChiaCirctBaseDockerfile | CHIA already downloads `circt-full-shared-linux-x64.tar.gz` for its "prebuilt libLLVM*/libMLIR*"; pins `firtool-1.148.0` |
| https://github.com/llvm/circt/releases (GitHub API) | 15 releases 2026-05-25 → 2026-09-09, each shipping `circt-full-shared-linux-x64.tar.gz` → ~weekly cadence |
| https://circt.llvm.org/docs/GettingStarted/ | CIRCT pins LLVM via git submodule; docs describe source builds, no official prebuilt path |
| https://github.com/ucb-bar/chia_benchmarks | `examples/benchmarks` submodule is Embench/riscv-tests/µbench simulation workloads, **not** an agent task set |
| https://arxiv.org/abs/2607.00700 and https://arxiv.org/html/2607.00700 | LLVM-Bench: 423 tasks, LLVM-Gym, construction pipeline, leakage prevention, models used (deepseek-v3.2, qwen3-coder-plus, gemini-3-flash, grok-code-fast-1), 21.99% LLVM-Ens, golden-patch file distribution |
| https://arxiv.org/abs/2604.14709 | HWE-Bench: 417 tasks, 6 HDL repos, containerized, 70.7% best agent, April 2026 |
| https://arxiv.org/abs/2605.15226 | Phoenix-bench: 511 verified Verilator instances, 114 repos, fail-to-pass + pass-to-pass, Docker-pinned EDA, May 2026 |
| https://huggingface.co/datasets/princeton-nlp/SWE-bench_Lite | SWE-bench Lite = 300 test + 23 dev instances |
| https://ai.google.dev/gemini-api/docs/deprecations | Gemini 1.5 Pro absent from deprecation tables (already shut down); current models incl. gemini-3.8-flash; gemini-2.0-* shutdown 2026-06-01 |
| https://developers.openai.com/api/docs/deprecations | `gpt-4o-2024-05-13` shutdown 2026-10-23, replacement `gpt-5.6-sol` |
| https://help.openai.com/en/articles/20001051-retiring-gpt-4o-and-other-chatgpt-models (via search) | GPT-4o retired from ChatGPT 2026-02-13 |
| https://huggingface.co/api/models/Qwen/Qwen3-32B[-Instruct] | `Qwen3-32B` exists (200); `Qwen3-32B-Instruct` does not (401) |
| https://github.com/verilator/verilator (tree API) + https://github.com/verilator/verilator/blob/master/docs/internals.rst | 4,312 test drivers in `test_regress/t/`; "thousands of tests"; parallelism and file-handle/process-limit warnings |
| https://llvm.org/docs/AIToolPolicy.html (via search) | LLVM AI Tool Use Policy: disclosure, human-in-the-loop, no AI on "good first issues" |
| https://api.github.com/repos/llvm/circt/pulls/10648 | PR "[FIRRTLToHW] Fix firrtl enum lowering" by `jack2bs`, merged 2026-06-17 — spot-check of the three merged CHIA PRs |
| https://groups.google.com/g/chialoops | CHIA mailing list: only 2 threads, no competitor signals |

**Sources added 2026-09-11 for §G:**

| URL | What it supported |
|---|---|
| https://huggingface.co/Qwen/Qwen3.8-27B and https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/README.md | `Qwen/Qwen3.8-27B`: `apache-2.0`, dense 27B, 262,144 native context extensible to ~1M, unified model with thinking on by default (`enable_thinking: False` to disable), vision-language; SWE-bench **Pro** 61.7, Terminal-Bench 2.1 73.0, QwenSWEBench 79.0, LiveCodeBench v6 90.3, GPQA-D 89.2, IFBench 79.5, OSWorld 84.3 / WebArena 64.8 / AndroidWorld 81.9; Qwen3.6-27B comparator column; SWE-bench Pro run under the Claude Code harness at temp=1.0/top_p=0.95/256K; vLLM + SGLang + TokenSpeed named as official serving frameworks; citation block `month = {August}, year = {2026}` |
| https://huggingface.co/Qwen/Qwen3.8-27B/raw/main/config.json | 64 layers, hidden 5120, 24 attn heads, **4 KV heads**, head_dim 256, bfloat16, vocab 248320, max_position_embeddings 262144; hybrid 3 linear (Gated DeltaNet) : 1 full attention repeated 16× → 16 full-attention layers; linear_num_key_heads 16 / linear_num_value_heads 48 / linear_*_head_dim 128 / conv kernel 4. Basis for the KV-cache arithmetic (64 KiB/token) and the single-A100 fit |
| https://huggingface.co/Qwen | Qwen3.8 family on the org page: `Qwen3.8-27B` (+`-FP8`), `Qwen3.8-Flash-Next` 180B (+`-FP8`), `Qwen3.8-2.4T-A95B` (+`-FP8`) |
| https://huggingface.co/Qwen/Qwen3.8-2.4T-A95B | 2.4T total / 95B active MoE, 512 experts (10 routed + 1 shared), **license `qwen3.8-max` (not Apache-2.0)**, Terminal-Bench 2.1 86.6, SWE-bench Pro 67.7, GPQA-D 92.6 |
| https://raw.githubusercontent.com/vllm-project/vllm-project.github.io/main/_posts/2026-08-12-qwen3.8.md | vLLM release post (2026-08-12): Qwen3.8-2.4T-A95B "reuses the Qwen 3.5 architecture and runs on vLLM from day one"; "requires at least two NVIDIA B300 / AMD MI355X nodes (or a single node for the FP4 quantized version)" |
| https://docs.vllm.ai/en/latest/models/supported_models.html | Lists `Qwen3ForCausalLM`, `Qwen3MoeForCausalLM`, `Qwen3NextForCausalLM` — **no Qwen3.8-specific entry found**; basis for "pin and test an exact vLLM version" |
| https://huggingface.co/api/models/deepseek-ai/DeepSeek-V4-Pro | **MIT**, ~1.598T params, `DeepseekV4ForCausalLM` MoE (6 experts/token), created 2026-04-22 |
| https://huggingface.co/api/models?search=DeepSeek-V4 | deepseek-ai ids: `DeepSeek-V4-Pro`, `-Pro-0813`, `DeepSeek-V4-Flash`, `-Flash-0731`, `-Flash-Base`, `-Flash-Vision-Exp`, `DeepSeek-V4.1-Flash` |
| https://huggingface.co/api/models/zai-org/GLM-5.3 | license `other`/`glm-5.3`, ~753.3B params, `GlmMoeDsaForCausalLM`, created 2026-08-25; org also has `GLM-5.3-Flash`, `GLM-5.3-Flash-BF16`, `GLM-5.2` |
| https://huggingface.co/api/models?search=Kimi-K3 | `moonshotai/Kimi-K3` exists (size/license not checked) |
| https://huggingface.co/api/models?search=Qwen3-Coder | Qwen-org coder ids: `Qwen3-Coder-30B-A3B-Instruct` (+FP8), `Qwen3-Coder-Next` (+FP8), `Qwen3-Coder-480B-A35B-Instruct` (+FP8) |
| https://huggingface.co/api/models/openai/gpt-oss-120b | **apache-2.0**, ~116.8B params, `GptOssForCausalLM` MoE (4 experts/token), MXFP4, created 2025-08-04 |
| https://ai.google.dev/gemini-api/docs/models | Current Gemini ids: flagship Pro `gemini-3.1-pro-preview`; current stable Flash `gemini-3.8-flash` ("Our most intelligent Flash model"); also `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-pro`, `gemini-2.5-flash` |
| https://developers.openai.com/api/docs/models and https://developers.openai.com/api/docs/models/gpt-6-astra | **`gpt-6-astra` is live in the API** ("Our most capable model"; set `model` to `gpt-6-astra` in a Responses API request); below it `gpt-5.6-sol`, `gpt-5.6-terra`, `gpt-5.6-luna`, `gpt-5.6-cyber`, `gpt-5.5`, `gpt-5.3-codex`; open-weight `gpt-oss-120b` / `gpt-oss-20b` |
| https://platform.claude.com/docs/en/about-claude/models/overview | Current Claude ids `claude-opus-5`, `claude-fable-5-1`, `claude-sonnet-5`, `claude-haiku-4-5`; Google Cloud IDs listed for each (so Google credits *can* reach Claude on Vertex); reliable knowledge cutoffs Fable 5.1 Jun 2026 / Opus 5 May 2026 / Sonnet 5 Jan 2026 |
| https://api.github.com/repos/ucb-bar/chia/contents/dockerfiles | CHIA dockerfiles: **`VLLMDockerfile`** and **`OllamaDockerfile`** both present, alongside `OpenCodeDockerfile`, `AntigravityDockerfile`, `ClaudeCodeDockerfile`, `Gem5Dockerfile`, `VerilatorRunDockerfile`, `ChiaCirctBaseDockerfile`, `ChipyardDockerfile`, `EspDockerfile`, `FireMarshalDockerfile`, `CactiDockerfile`, `ChampSimDockerfile`, `RiscvCrossDockerfile`, `RiscvDvDockerfile` |
| https://raw.githubusercontent.com/ucb-bar/chia/main/dockerfiles/VLLMDockerfile | Base `vllm/vllm-openai:latest`; `VLLM_MODEL` = any Hugging Face model id (required to auto-serve); port 8200; comment "vLLM is GPU-first. The default base (vllm/vllm-openai) is CUDA/NVIDIA" → open-weights-on-NVIDIA is a first-class CHIA path |
| https://spinalhdl.github.io/SpinalDoc-RTD/master/SpinalHDL/Other%20language%20features/vhdl_generation.html | SpinalHDL emits VHDL/Verilog/SystemVerilog from its own backend (`SpinalConfig(mode=Verilog\|VHDL, …)`) — no CIRCT in the path |
| https://api.github.com/search/issues?q=repo:llvm/circt+SpinalHDL | `total_count: 0` — zero SpinalHDL mentions in llvm/circt issues or PRs |
| https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5080/ | 1st-prize GPU is "16 GB GDDR7", 256-bit — cannot host Qwen3.8-27B in BF16 |
| https://agentic-arch.org/hackathon.html (re-fetched) | Verbatim NVIDIA tracks: "Reusable CHIA blocks for agentic design workflows that run on NVIDIA-accelerated infrastructure and can be reused after the hackathon" and "Training or finetuning of specialized AI models on NVIDIA platforms to improve architecture/design agent performance" |

### Claims I could NOT verify

- **No published judging rubric exists.** Organizers state only "judged by the A³ workshop's program committee." All alignment scoring is against organizer *stated goals* plus the A³ CFP topic list, not a scoring sheet.
- **The A³ program committee membership is not published** on either the CFP or home page.
- **What other hackathon teams are building.** 18 forks, three community PRs on `ucb-bar/chia`, but no public project descriptions.
- **Whether the CHIA acronym expands to anything.** Never stated in the README, paper, or site.
- **Whether a CIRCT release tarball's prebuilt LLVM ABI-matches an arbitrary historical parent commit** within a pin window. This is the proposal's core technical bet and I found no evidence either way.
- **Verilator full-regression wall-clock time.** No published figure; I inferred difficulty from test count (4,312) and the docs' resource warnings.
- **Exact current frontier-model rankings for Sep 2026.** Model *id* and *deprecation* facts come from Google's, OpenAI's and Anthropic's official pages and are solid; the ranking claims I saw (Claude Fable 5 / GPT-5.x / Gemini 3.x SWE-bench numbers) came only from SEO aggregator sites and are **not** relied on in this report.

**Added 2026-09-11 (§G):**

- **The exact release *day* of `Qwen/Qwen3.8-27B`.** The model card's citation block gives only `month = {August}, year = {2026}`. "2026-08-14" appears consistently across secondary write-ups but I found no official page stating it — **aggregator-sourced**.
- **vLLM's support status for `Qwen3.8-27B` specifically.** The model card names vLLM as an official framework and links a "Qwen3.8 Recipe"; the obvious recipe URL 404s, the `supported_models` page I fetched lists no Qwen3.8 architecture, and vLLM's own release post makes its day-0 claim about `Qwen3.8-2.4T-A95B`, not the 27B. Likely fine, **not proven** — pin a version and test.
- **Licenses/sizes for `moonshotai/Kimi-K3`, `Qwen/Qwen3.8-Flash-Next`, `Qwen/Qwen3-Coder-Next`, the DeepSeek-V4-Flash tier, Llama 4.x and Mistral.** Existence confirmed via the HF API for the first four; specs not checked.
- **That an A100 (Ampere) lacks native FP8 tensor cores.** Stated as a hardware generalization; not re-verified against an NVIDIA page this session.
- **Whether CIRCT bug-fix commits routinely add a `lit`/FIR/SV test**, and at what rate. Nobody publishes this, and it determines whether 40–80 tasks is reachable. Only the team's own pilot can answer it.
- **`Qwen/Qwen3.8-27B`'s training-data cutoff.** Not published in the model card, so a per-model temporal hold-out cannot be defined for the open-weights arm. Anthropic publishes cutoffs; Google's and OpenAI's I did not check this session.
- **Whether gem5 is genuinely more expensive to containerize than Verilator or CIRCT** (the proposal's stated reason for deferring it). Unmeasured — and CHIA already ships a `Gem5Dockerfile`.
- **PR numbers of two of the three merged CIRCT PRs.** The paper states all three merged; I confirmed one (#10648) directly.
