# Disposition of `red-team-FRD.md`

**Status: Draft.** Date: 2026-09-13. This is a record of dispositions, not a design document;
`00-README.md`'s status ladder governs 00 through 05, and `01-FRD.md`'s own status is unchanged by
this file.
**Subject:** the 47 findings of `design/reviews/red-team-FRD.md` against `design/01-FRD.md` and
`design/00-README.md`.
**Rule:** every finding carries a disposition of Accepted, Accepted with change, or Rejected with
reason. Nothing is rejected without a reason grounded in a source this set already names
(`problem-statement-FINAL.md`, `paper/main.tex`, `analysis/pin-window-analysis.md`, CHIA at
`~/.cache/chia-src`, or the CIRCT clone and SDK under `~/.cache/chia-pin-smoke/`).

**Result:** 47 of 47 findings accepted, 41 as proposed and 6 with a change to the remedy the review
proposed (K1, K3, K5, K6, W15, W20). Nothing rejected. Of the review's twelve verdicts on the open
decisions, three are accepted with a change (D-03, D-04, D-05) and nine as written. The review's own numbers are cited in the FRD as RT4's measurements where they were
not re-derived here, and its bucketing tables and corpus counts were re-derived independently from
`analysis/pin_window_raw.json` on 2026-09-13 and agree.

---

## 1. KILLs

| Id | Disposition | What changed, and where |
|---|---|---|
| K1 | **Accepted with change** | Accepted that `circt-reduce` reads MLIR text only; verified here by re-executing it on `.fir`, `.sv` and `.mlir`. Changed in scope: rather than only answering the gate, the FRD now selects a reducer by input language. New **FR-09.9** (the four-branch selection, with `firtool --ir-fir` and `circt-verilog --ir-moore` as lifts, both flags verified against `--help`), **FR-09.10** (textual ddmin, standard library only), **FR-09.11** (`ReducedCase` names the reducer and its fixpoint state), **FR-09.12** (`reduced=false` proceeds to triage and is refused at the gate with a reason). **FR-09.6 WITHDRAWN**. **FR-13.3** made total. New **C-17**. **G-24**, **G-46** define the vocabulary. |
| K2 | **Accepted** | **FR-03.4** now fixes `-O3 -UNDEBUG -gline-tables-only` and requires `readelf -S` to show `.debug_line`. **FR-07.4**'s criterion is now "name a CIRCT source file and line". **A-03** and **D-08** both require the size and build-time delta of `-gline-tables-only` as a measured output. |
| K3 | **Accepted with change** | Accepted that a CHIA node cannot start a container; verified against `docs/user_guides/docker_images.rst:17-26`, `docs/concepts/overview.rst:59-70`, `cli/main.py:99-130` and `cluster.yaml:46-50`. Changed in remedy: the review left the requirement unsatisfiable, **FR-13.2** now asks for a fresh process, a newly created working directory and a different logical worker where one exists, with `same_worker=true` recorded where it does not, evidenced by hostname plus Ray node id and process id for both runs. New **C-19**. |
| K4 | **Accepted** | **FR-12.3** now defines the generated `repro.sh` by failure mode rather than by the tool's exit status: exit 0 iff no crash signal, no assertion or `UNREACHABLE executed`, no `LLVM ERROR:`. It cites `prompts/reproduce.md:8-9` and `12-14`, and `issue_task.py:226` and `274` for what the old shape scored. Two committed fixture binaries, one still crashing and one now diagnosing, are the acceptance criterion. **FR-18.4** records that "repairs merged" is reachable only because of this. |
| K5 | **Accepted with change** | Accepted that "any one of three keys" is not transitive. Changed in remedy: rather than choosing a closure rule, the FRD narrows the merging key to one. **G-43** primary fingerprint, **G-44** distinct, **FR-10.1**, **FR-10.2** (if and only if, with an equivalence-relation test), **FR-10.8** (insufficient basis no longer merges on the hash alone), **FR-18.3**, **D-06**. N is a `[DEFAULT]` in `budget.yaml` (**FR-14.1**). |
| K6 | **Accepted with change** | Accepted that (e) adopts the bias D-04's own table names. Changed in unit: the review's preferred fallbacks were (b) or its new (f); the architect's decision is wall-clock per arm on a declared worker type with identical apparatus concurrency and one cluster YAML, which answers (b)'s noise objection directly. **G-48**, **D-04** rewritten, **FR-14.5**, **FR-18.10**. Option (f) added to the table as the review proposed it. FINAL §4's "GPU-hours" recorded as a misnomer in **FR-14.5** and **D-04** (W16). |
| K7 | **Accepted** | **FR-18.6** now has six buckets and a complete mapping table from every stopping value to exactly one of them, including `reduction_changed_failure`, `dedup_unavailable` and `dedup_basis=insufficient`. `known_issue` and `untriaged` appear in no row because K13 removed them from the gate. The paper's taxonomy sentence was edited to the same six words. |
| K8 | **Accepted** | New **FR-08.10**: a `differential` candidate produces an informational `Report`, stored and listed as "divergences observed", never reduced, never repaired, never gated, never filed. **FR-13.14** states the exclusion, **FR-11.9** keeps the template, **FR-18.12** counts them. |
| K9 | **Accepted** | **FR-01.1** now carries PIN §2 lines 74-79 in full, and §1.4 makes PIN §2 normative for the filter. The only textual change to the quoted rule is that PIN's two em-dash separators are written as colons, stated in the requirement, because this set forbids em-dashes. |
| K10 | **Accepted** | **FR-01.4** makes dialect-level bucketing normative and requires both tables; both were re-derived here from `analysis/pin_window_raw.json` and match the review exactly, including the split of the 16. **A-18** recorded as resolved with the reason that there was never a disagreement. **FR-08.1** now carries a defined applicability rule and a required measurement (**A-19**) instead of an inherited 11. |
| K11 | **Accepted** | **NFR-01** now defines "re-run": every tool stage re-executes from stored inputs, agent turns replay through bypass from stored transcripts, and the re-executed verdicts must equal the stored ones. `bypass.py:3-5` and `cache.py:13-24` are cited for what they actually do. **FR-18.11** and F-17's feature acceptance inherit the definition; §4.2's row is corrected. |
| K12 | **Accepted** | `00-README.md`'s two-person rule now defines the seam as **one versioned contract package** of exactly five schemas, `ProbeSpec`, `CandidateRecord`, `FeedbackBundle`, `LedgerEntry`, `RunManifest`, with one version number and a table saying why each crosses; each half's fixture set covers all five. **G-47**, §2.5, **FR-16.1** (the bundle declares its own fields so the generator half imports no apparatus schema), §10.1 item 2, §10.2 item 1. "Exactly one seam" is kept. |
| K13 | **Accepted** | New **FR-13.15**: gate question 3 is a per-tool parse-and-verify command (`circt-opt <case> -o /dev/null`, `firtool --parse-only`, `circt-verilog --import-only`, all three verified against `--help`), with a defined answer for the case where the check itself fires the oracle. **FR-13.4** reads only that; **FR-11.1** makes the triage classification advisory; **FR-11.8** no longer refuses at the gate; **NFR-03** and **G-29** reconciled. |

---

## 2. WOUNDs

| Id | Disposition | What changed, and where |
|---|---|---|
| W1 | **Accepted** | **FR-06.1** requires direct `execve` with an argument list and no shell; **FR-06.4** reads the signal from the negative return code and gives `timeout` its own status with a null signal; F-06's reuse table drops `circt_run_script` and says why, while F-12's repro path keeps it. |
| W2 | **Accepted** | New **FR-01.10**: a six-step `RUN:`-line normalisation that strips `not` recording polarity, strips `env` and `split-file`, drops the pipe tail, resolves `%s %t %S`, and marks and counts unsupported shapes. **FR-01.2** keeps the verbatim line and points at it. The review's 1,714 / 81 / 1,302 / 218 / 11 counts are cited as RT4's. |
| W3 | **Accepted** | **FR-15.1** matches at symbol level and records both bounds; **FR-10.4** keeps file level explicitly and only for the lag window, with the reason stated in both places. The review's tree-churn table is cited as RT4's. |
| W4 | **Accepted** | **D-01** now prices option (c) with the review's numbers, marked as RT4's, and adds option (d), calibration over a named sample of k seeds with k a `[DEFAULT]` in `budget.yaml`. The recommendation is (c) with (d) as the calibration policy. "The run's commit" is defined per mode by new **FR-02.7**. |
| W5 | **Accepted** | **FR-03.7**, **D-08** and new **C-21** all record that CHIA already warm-builds six targets and that the marginal target is `circt-reduce`, the multiplier being the flag string. §4.2's warm-up row carries the same correction. |
| W6 | **Accepted** | **FR-03.6** now runs over the whole `test/` tree with CHIA's own exclusion list (`circt_util.py:151-159`), twice, and requires set equality of failing test names. New **A-20** records that this baseline has never been run and that F-12's verify gate depends on it. |
| W7 | **Accepted** | The 96% and 99% floors are struck in **FR-03.5** and **FR-03.6**. FR-03.5 now emits the non-referencing object list by name and compares it as a set against the recorded baseline of 18; FR-03.6 uses failing-set equality against the `-DNDEBUG` baseline on the same commit. |
| W8 | **Accepted** | "Attributable" is struck from **FR-03.6**, with §5's preamble cited as the reason. |
| W9 | **Accepted** | **NFR-07** rewritten for one read-only credential, its two-credential criterion struck; **D-02**'s recommendation states the consequence explicitly. |
| W10 | **Accepted** | New **FR-10.9**: mirror open and closed issues once per run, `state="all"`, a `[DEFAULT]` page cap in `budget.yaml`, with the refresh time, page count, issue count and cap-bound flag recorded. **FR-10.3** reads the mirror and makes no request of its own. §4.2's row carries the pagination fact and CHIA's own `TRIAGE_POOL = 2000`. |
| W11 | **Accepted** | New **FR-09.13**: the interestingness script wraps the tool in `timeout` and the per-probe rlimits, SIGTERM then SIGKILL after a `[DEFAULT]` grace, and validates the `-o` output only after the reducer exits. New **C-18** records `Tester.cpp:50-52`'s zero limits and `Tester.cpp:44-46`'s last-argument convention; **FR-09.2** carries the convention. |
| W12 | **Accepted** | **FR-06.2** applies memory and CPU-time limits to the child by `setrlimit` or `prlimit` and replaces "a number of cores" with CPU-time seconds; **NFR-05** separates the two levels and cites the re-queue behaviour that would otherwise turn an OOM into a silent retry. |
| W13 | **Accepted** | New class throughout: **G-45**, **FR-06.9** (seven `BuildResult` statuses), **FR-07.1**, **FR-07.2**, new **FR-07.10** (report wording that does not call a deliberate refusal a crash), **FR-12.4** (no repair), **G-22**. The 20-occurrences-in-10-files count was re-verified here. |
| W14 | **Accepted** | New **FR-01.11**: the corpus HEAD SHA lives in `budget.yaml`, the clone is reset to it before mining, and a mismatch exits non-zero. **FR-01.1**'s acceptance states that 187 and 171 are the counts at `d7e94049`. **FR-14.1** lists the field. |
| W15 | **Accepted with change** | The `circt/arc-tests` repository is not on this machine, so whether its driver generalises from Rocket Chip and BOOM to a generated design cannot be decided here. New **FR-08.11** therefore requires **either** reuse of that driver and its `diffvcd.py` differ **or** a named deviation with the obstacle stated, recorded in the `RunManifest` and the results artefact. That is the review's second branch, made testable rather than left as an intention. |
| W16 | **Accepted** | **FR-14.5** and **D-04** both record that FINAL §4's "GPU-hours" is a misnomer, with the reason: no stage uses a GPU. |
| W17 | **Accepted** | New **D-14**: single machine is the Must, GCP a Should kept only if credits are confirmed by a date `05-Work-Plan.md` names. **NFR-10** downgraded accordingly, with the note that this trims a scope *addition*, which `00-README.md`'s no-cuts rule does not protect. §10.1 item 4 and §10.4 item 10 follow. |
| W18 | **Accepted** | **FR-12.2** requires an integer identifier from a declared synthetic range and a full `GithubIssue`-shaped object, citing all five places the integer is load-bearing and `state_def.py:11-24` for the eleven fields. §4.1's Persistence row now says **Not extended**, so `issues.db` keeps its schema and the loop's rows live in the loop's database. **D-11**'s justification corrected. New **FR-12.10** fixes the two-row write order and adds an end-of-run reconciliation. |
| W19 | **Accepted** | The build status is renamed `parse_error` (**G-49**, **FR-06.6**, **FR-04.9**); **G-50** defines the two remaining senses and ties the taxonomy bucket to FR-13.15's mechanical check alone. |
| W20 | **Accepted with change** | The review offered "either C-07's list is wrong or CHIA's image is non-conformant". Checked: `docs/user_guides/docker_images.rst:35` requires both packages verbatim, so the list is right and the image is non-conformant. `openssh-client` and `rsync` therefore **stay** in **FR-03.9**, which gains an executable criterion (`ssh -V`, `rsync --version`) and records that it is correcting CHIA's base image; **C-07** carries the same. |
| W21 | **Accepted** | New **FR-13.17**: the pre-filled URL is measured against a `[DEFAULT]` character limit fixed in `03-LLD.md`, with D-02(a) as the recorded fallback. **D-02** states the rule. |
| W22 | **Accepted** | **FR-05.1** now mutates **every** changed test file, k files giving k starting inputs. **FR-01.12** requires the ordered list and forbids collapsing it. Re-derived here: 162 seeds changed one test file, 18 changed two, 5 changed three, 1 changed six, 1 changed nine. |
| W23 | **Accepted** | **A-17** recorded as resolved, quoting PIN's own correction at `analysis/pin-window-analysis.md:90` and noting that 89.3% is 2,909 of 3,257. |

---

## 3. NITs

| Id | Disposition | What changed, and where |
|---|---|---|
| N1 | **Accepted** | **G-04** lists all nine firtool output modes and cites `firtool.cpp:185-202`. The two MLIR-emitting modes are named there because **FR-09.9** uses them as lifts. |
| N2 | **Accepted** | **NFR-05** now names all four `run_options` the CIRCT worker sets today, including the SSH agent mount and environment variable. |
| N3 | **Accepted** | **C-08**'s "confirmed on the SDK binary" clause is withdrawn in place, with the reason: the SDK binary is an assertions-off release build and its version string is silent about `-UNDEBUG`. FINAL Appendix A's completed build is left as the sole evidence. |
| N4 | **Accepted** | §4.2's Node-dispatch row cites `ChiaFunction.py:66-107` and `228-231`, and records that `482-494` is `ChiaCallRemote`. |
| N5 | **Accepted** | §4.3 cites `chia:dockerfiles/VerilatorRunDockerfile:7-8`. |
| N6 | **Accepted** | **FR-19.1**'s undecidable criterion is struck and replaced by a class check over five named long-running tool categories, with the note that 120 s is CHIA's own default. |
| N7 | **Accepted** | F-20 gains **Preconditions**, **Inputs** and **Outputs**, so §5's per-feature template holds for every feature. |
| N8 | **Accepted** | **FR-03.8** requires exactly one `lit` installer, in the image, and adds `pip install lit` reporting "already satisfied" as the criterion. |
| N9 | **Accepted** | §1.4's number-discipline rule gains the `[DEFAULT]` marker, defined as a value chosen by design, recorded in `budget.yaml` and fixed by the pre-registration commit. Every sample size, threshold and limit the review listed is now marked, and **FR-14.1** enumerates the `budget.yaml` keys they resolve to. A number with neither marker and neither source is declared a defect in the document. |
| N10 | **Accepted** | §9.3 gains a mapping paragraph and table: the paper's four between-stage bars are not the final gate's four questions, both are kept unrenamed as `00-README.md` requires, and each bar is mapped to the requirement that implements it. |
| N11 | **Accepted** | §4.1's Skip-triage row and §4.3's supply row both name all four entries, and §4.1 records that `--replay-regression`'s restore-then-re-enter shape, not `--issue`'s, is the nearer model for FR-12.3's pre-written repro. |

---

## 4. The review's verdicts on D-01 to D-12, and the two decisions added

| Id | Review's verdict | Disposition |
|---|---|---|
| D-01 | Right choice, unpriced | **Accepted.** Option (d) added; (c) recommended with (d) as the calibration policy; priced with RT4's W4 numbers; "the run's commit" defined per mode by FR-02.7. |
| D-02 | Right, with an unstated ceiling | **Accepted.** Option (d) added; (c) plus (d) recommended, (a) as the fallback above the URL limit; NFR-07 fixed. |
| D-03 | Wrong on both of its own grounds | **Accepted with change.** The review recommended (c) per-stage configurable defaulting to `opencode`. The decision taken is its own missing option (d): one backend and one model per run, set by the cluster YAML, defaulting to `opencode` with `google-vertex/gemini-3.1-pro-preview`, `antigravity` with `gemini-3.1-pro-high` as the alternative, `claude` only as an outage fallback. Per-stage configurability is dropped because a backend is a cluster, not a flag (new **C-20**), which the review itself established. |
| D-04 | Wrong; names the bias then adopts it | **Accepted with change.** Option (f) added as proposed. The unit chosen is wall-clock per arm on a declared worker type with identical concurrency and one cluster YAML, which is the review's own answer to option (b)'s noise objection; inputs and filings become equal safety caps; tokens, cost and CPU time are reported and not budgeted. |
| D-05 | Right method, wrong source, isolation broken at synthesis | **Accepted with change.** The source widens to the **full** closed `label:bug` history rather than the review's option (d), the fix-commit set, because Mut4All's input is bug reports and staying with reports keeps the method intact; option (d) is added to the table as the fallback if the widened set is still too small. The synthesis-time exposure is not treated as a defect: **FR-05.8** requires it to be declared in the results artefact and the paper as Mut4All's design, symmetric to the seeded arm's exposure, with FR-05.1's run-time isolation standing. |
| D-06 | Right; add "distinct" | **Accepted.** "Distinct" added as the fifth definition, resting on G-43 and G-44. |
| D-07 | Right; two qualifiers | **Accepted.** The consequence is stated in D-07 and enforced in **FR-18.2**. |
| D-08 | Right recommendation, wrong premise | **Accepted.** Premise corrected per W5; C-16 promoted to new **D-13** with the three options named, recommending (a) slang from source with (b) exclusion of the 46 seeds as the fallback, measured first, implemented by **FR-03.14**. |
| D-09 | Right, with a missing consequence | **Accepted.** New **FR-03.15** pins one Verilator version for the whole campaign, because the risk is X-propagation behaviour and not flag presence. |
| D-10 | Right | **Accepted.** The lag's effect on the filing rate is now disclosed beside the headline. |
| D-11 | Right choice, wrong justification | **Accepted.** Justification rewritten to separation rather than FR-12.1; the dangling-join-key consequence becomes **FR-12.10**. |
| D-12 | Right | **Accepted.** The approval CLI is also where the issue URL is recorded (**FR-13.18**), and it is named in §10.2 and §10.4 as a deliverable. |
| D-13 | (new) | Added: how `circt-verilog` reaches the run's commit. |
| D-14 | (new) | Added: deployment scope, per W17. |

---

## 5. Section 6 of the review

The review's single question before HLD, "for each entry tool, which binary executes the probe,
whether `circt-reduce` can read that language, and what the gate answers when it cannot", is answered
by **FR-09.9** (which reducer, per language), **FR-03.14** with **D-13** (which binary, for the `.sv`
region), **FR-13.3** (what the gate answers) and **FR-06.1** with §10.2 item 4 (which binary, in
general). The review's §7 experiment list is adopted in **§10.4 item 6**, which schedules A-03 and
A-20 first and puts A-19 before any work on F-08's harness generators.
