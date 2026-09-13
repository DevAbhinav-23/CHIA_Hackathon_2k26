# Red team — A (harness/gate) vs B (discovery loop)

Hostile review, 2026-09-11. No fixes, no praise.

Primary evidence: `examples/circt_issue_solver/README.md` (raw); arXiv 2606.27350v3 §5.5 + Table 5;
`pin-window-analysis.md`; **live execution** of the CIRCT SDK binaries at
`/home/adi/.cache/chia-pin-smoke/circt-sdk/bin/`; **re-derivation** of the 1,103/187 commit
statistics from the blobless `llvm/circt` clone (HEAD `d7e94049bde3`); GitHub search API;
arXiv 2603.20075 / 2510.03217 / 2607.00700 / 2605.10074 / 2504.01379 / 2507.19275.

---

# 1. Attacks on A — `problem-statement-A-harness.md`

## KILLS

### A-K1. The headline object does not exist, and the corpus it will be fitted on has a verified size of 1.

> "**The fit itself.** Nothing is fitted yet: feature weights, operating threshold, calibration and
> the retry budget *N* are all to be set in the pilot. Every metric here is a protocol; no target
> value is claimed."  (Appendix B)

> "**How many of the 171 genuinely satisfy fail→pass.** One (`f2b15a44ec70`) executed end to end;
> the 187 rest on a subject-keyword proxy and no diffs were read."  (Appendix B)

The contribution is "a calibrated submit/retry/abstain gate". The gate has no weights, no threshold,
no calibration, no *N*, and its training set has measured size 1 against a hoped-for 171 that rests
on a subject-keyword regex nobody has validated against a diff. Every downstream object — precision,
reliability curve, ablation, transfer — inherits that 1.

### A-K2. The circular-label kill was renamed, not escaped: the withheld test and the "tests flipped" feature are the same check.

> "Added between `verify` and `writeup`: a logistic gate over features `verify` already runs
> (repro exits 0, lit gate green, **tests flipped**)"
> "**Labels.** The fix commit's withheld test: never shown to the executor, never a gate feature."
> "The label it is fitted against is the fix commit's withheld test — not a gate feature, and never
> shown to the executor — **so the fit is not a conjunction of its own inputs**."  (Appendix C)

On a mined task the bug's reproducer *is* the test the fix commit adds. `pin-window-analysis.md` §5.3:
the exemplar `f2b15a44ec70` touches one source file and one test file, and the test command is that
file's `RUN:` line. CHIA's repro contract is literally *"exit 0 iff fixed"*. 156 of the 171 exact-match
tasks have exactly one source file (§4), so this is the normal case, not the corner case. So
"the repro exits 0" ∧ "tests flipped" and "the withheld test passes" are two names for running the
same check on the same bug. A never states any mechanism keeping the agent's repro disjoint from the
withheld test. Appendix C's last clause is the sentence a PC circles.

### A-K3. The ≈110-minute comparator is not "matched", and the study that would beat it has no stated N and an unsourced reviewer pool.

> "we report per decision, and per accepted fix against the **matched** (5×60 + 3×10)/3 ≈ 110 from
> 5 fixes, 3 PRs."

The 110 prices a human reviewing an agent patch *to the point of hand-writing a pull request that was
merged into `llvm/circt`*. A's arm prices a reviewer's accept/reject minutes on mined patches, in a lab,
with a known withheld-test answer and known-incorrect decoys mixed in, ending in no PR and no merge.
Different artifact, different reviewer, different stakes — "matched" is asserted, never argued.
A also never gives the pool size, and Appendix B concedes "Reviewer pool composition, and whether an
external CIRCT contributor takes part" is not verified. A minutes-per-decision difference across
≥2 reviewers needs tens of patches; A-K1 says the verified corpus is 1.

### A-K4. The prize sentence rewards a loop; A's own §2 and its own table say the loop is unchanged.

> "Phases and `--backend`/`--model` executor choice are **unchanged**."  (§2)
> "| assess→reproduce→fix→verify→regression-repair→writeup | **unchanged** |"  (table, first row)

The hackathon prize is for "the most novel, creative agentic loop(s)", judged by a PC including the
people who wrote `circt_issue_solver`. A's first substantive claim to them is that their loop is
unchanged and one edge inside it gets a threshold. Red-team-v2's K1 was "you added a threshold to our
verify step"; A's Appendix C answers "the edge where `verify` succeeds and the patch proceeds to
`writeup`: today it is unconditional, and we make it a three-way decision." Same object, now called
an edge. Not escaped — reworded.

## WOUNDS

### A-W1. The supply numbers are the wrong population and are internally inconsistent.

> "**Supply.** Of 1,103 shape candidates, 84 close a GitHub issue, 76 with an exact pin."  (§3)
> "A **stricter** variant of the same pattern returns **89** of 1,103, 83 with an exact pin; the
> intersection with the bug-vocabulary 187 is 35–39 depending on variant."  (Appendix B)

A stricter pattern cannot match more commits than a looser one. 89 > 84, so one of the two labels is
wrong on the face of the document. Re-derived over the same 1,103 commits from the clone, with A's
stated pattern (`fix|fixes|fixed|closes|closed|resolves|resolved` within 20 chars of `#N` or the
issues URL): **95 matches, 86 with an exact pin**; loosening the keyword set gives 102/93. The
intersection with the bug-vocabulary 187: **42, of which 39 exact**. So the number that describes the
corpus A actually builds images for is ≈39 — and it is in the "Not verified" appendix, while the body
shows 76, drawn from the 1,103, which A never builds images for at all.

### A-W2. "Close a GitHub issue" is ~90% a merge-commit PR reference.

Appendix B concedes: "No referenced number was resolved against the API to confirm it is an issue
rather than a pull request." Measured: **853 of the 1,103** candidate subjects contain a `#N` (CIRCT's
merge convention appends the PR number), and only **11 of 1,103** commit messages contain an
`llvm/circt/issues/` URL anywhere. The body's unqualified "84 close a GitHub issue" is therefore
almost entirely unverified as *issues*, and the qualification lives two pages away.

### A-W3. Blast radius is written as a scalar and defined as three counts, with a pre-signed coefficient.

> "plus **blast radius** `b`: changed-outcome lit tests, distinct dialect directories, public
> `include/circt` headers touched, entering as `log(1+b)` with a non-positive coefficient."

`log(1+b)` takes one number; three counts are supplied with no weighting, no aggregation rule and no
units. Constraining the coefficient to be non-positive *before* fitting means the fit cannot report
evidence that blast radius matters — the sign was assumed. And on this corpus the feature is nearly
constant: 156 of 171 exact-match tasks touch exactly one source file (`pin-window-analysis.md` §4), so
"distinct dialect directories" ≈ 1 almost everywhere. The one genuinely new feature has the least
variance where it is fitted. Red-team-v2's W13 survives in a longer sentence.

### A-W4. The demo is a replay of precomputed rows through an unfitted gate.

> "`chia job submit` replays two mined rows: submit, then abstain."

Nothing is computed live; two stored rows print two words. Since A-K1 says no weights or threshold
exist, the two decisions are hand-set. This is the whole 5-minute artifact.

### A-W5. The contamination correction is one clause and the probe is unspecified.

> "A memorized fix is a feature-perfect positive, so mined calibration is optimistic; a per-task probe
> splits reported numbers."
> Appendix B: "Whether a contamination probe separates memorized from reasoned fixes at useful resolution."

The bias is conceded (correctly — red-team-v2 W3), the correction named, and the correction's validity
listed as unverified. Net effect on the reported numbers: unknown, by A's own account.

### A-W6. The transfer arm has a floor it cannot reach.

> "Fitted under one backend, applied unchanged under another; below 20 gate-passing patches there,
> insufficient rather than a number."

A pre-registered floor is an improvement on v2's W8. But 20 gate-passing patches on a second backend
means ≳20 successful repairs there; CHIA's own published rate (§5.5, Table 5) is 5 fixes from 16 issues.
Reaching 20 needs ~64 tasks run twice, against a verified corpus of 1.

### A-W7. The adapter refactor — the one thing a CHIA maintainer would merge on sight — is a subordinate clause with one implementation.

> "Since 'the rest of the flow still assumes CIRCT', build, test-select, repro-contract and
> regression-gate become four adapter methods."
> Non-goals: "no benchmark, resolve-rate ranking, finetuning, **second target**."

An abstraction with exactly one implementation is a rename. A declares the second target out of scope
in the same document, so nothing in the submission can show the adapter adapts.

## NITs

- **A-N1.** "CHIA's CIRCT loop executes everything needed to judge its own patch and never judges it" —
  the opening bold sentence concedes that CHIA already computes the feature vector.
- **A-N2.** A section headed "**Appendix B — Not verified**" with seven confessions including "Nothing is
  fitted yet". Reviewer-management notation promoted to a heading.
- **A-N3.** "No published judging rubric for the hackathon; A³ PC membership is not published." — a claim
  about the judges, inside the document the judges read.
- **A-N4.** Non-goals lists five exclusions before a single result, and one of them ("Root causes in
  LLVM/MLIR, scoped out by the example") is CHIA's non-goal, not A's contribution.
- **A-N5.** "Live: 101 open `bug` issues, median age 890 days, 17 in the last year." A never runs on live
  issues — an open issue has no fix-parent, hence no pin-window image. Orphan statistic.
- **A-N6.** The "regression repair" quote is labelled verbatim but cut mid-sentence with no ellipsis; the
  README continues "…to repair **without un-fixing the bug**."
- **A-N7.** "below 20 gate-passing patches there, insufficient rather than a number" and "the threshold is
  refitted before live claims" — two sentences written to pre-answer a reviewer.

---

# 2. Attacks on B — `problem-statement-B-discovery.md`

## KILLS

### B-K1. One axis of the differential grid is dead: `--preserve-aggregate` either changes nothing or produces pairs `circt-lec` refuses. The single executed differential compares a circuit with itself.

> "(ii) Differential: one input through `firtool` at `-O=debug`/`-O=release` **× each
> `--preserve-aggregate`**, compared by `circt-lec` … Executed: `none` vs `all` gave `c1 == c2`"

Executed today on the same SDK, on B's own `probe/agg.fir`:
- Default (public modules scalarized): `--preserve-aggregate=none` vs `=all` differ **only** in
  `hw.wire` placement; the dataflow (`hw.array_create` + `hw.array_get`) is identical. B's own saved
  probe files `agg_none.mlir` / `agg_all.mlir` differ by exactly one token —
  `{sv.namehint = "v"}`. The recorded `c1 == c2` proves two identical circuits equivalent.
- With `--scalarize-public-modules=false`, the flag finally bites — and `circt-lec` refuses:
  `error: module's IO types don't match second modules: '!hw.modty<input v : !hw.array<4xi4>, input i : i2, output o : i4>' vs '!hw.modty<input v_0 : i4, input v_1 : i4, input v_2 : i4, input v_3 : i4, input i : i2, output o : i4>'`
  — consistent with `docs/Tools/circt-lec.md`: "The number of inputs and outputs and their types must
  match between the first and second circuit."

So the cross-product B advertises has no operating point: where it differs, the oracle cannot run.

### B-K2. "CHIA's `circt_issue_solver` unchanged" is contradicted by CHIA's README twice: the loop's input is a GitHub issue, and its first phase abstains on exactly B's supply.

> "**Repair.** CHIA's `circt_issue_solver` **unchanged**; the reduced case is its repro contract,
> 'exit 0 when fixed'."
> Table: "| Repair | full phase chain | **reused unchanged** |"

README, verbatim: triage is a "head, read-only `GithubIssuesNode`" that samples **open issues** that
"carry a code-block repro"; the per-issue unit is `run_issue_remote`; "**No GitHub writes — both flows
only read.**"; even the skip-triage path is `--issue 10568`, a GitHub issue number. A manufactured bug
has no issue number, so the entry point must change — "unchanged" is false.

Worse, the first phase is: "**assess** — is this actually a bug, and are the bug *and the correct
behavior* clear? If not, log the reason and skip (`not_a_bug` / `unclear`)." For a divergence between
two optimization levels, *which side is correct* is precisely the open question. CHIA's unchanged loop
logs `unclear` and skips B's own output.

(Also: B quotes the contract as "exit 0 **when** fixed". The README says "exit 0 **iff** fixed".
Not verbatim, and the dropped half is the load-bearing direction.)

### B-K3. The motivating sentence is a search-engine artifact, and the correct queries contradict its inference.

> "And **0 issues match 'miscompil'**: silent wrong-output bugs do not file themselves."

GitHub search tokenizes; "miscompil" is not a token and cannot prefix-match. Queried today against
`llvm/circt`: `miscompile type:issue` → **2**; `miscompilation type:issue` → **2**;
`"wrong output" type:issue` → **13**; `miscompile` (all items) → **8**. The zero is an artifact of a
truncated search term, and B's Appendix A sources it to "provided, task brief" rather than to a query
B ran. The premise of the entire proposal — that wrong-output bugs go unreported — is unsupported by
the evidence B cites for it.

### B-K4. "Maintainer-confirmed" contains a clause that removes the maintainer; the denominator is self-set.

> "**Headline: distinct, reduced, maintainer-confirmed bugs per GPU-hour.** … *Confirmed*: a maintainer
> label or fix, **or two oracles agreeing where no open issue covers it**."
> Limitations: "Maintainer confirmation sits outside our compute budget, so the headline metric lags."

The disjunct lets the team confirm its own bugs; for a crash, "two oracles agreeing" is a crash plus a
crash. The numerator is self-graded, the denominator is a GPU-hour budget the team chooses, and B
concedes the only external part lags past the deadline. That is not a measurement — it is a count with
a scale factor, comparable to nothing in the literature.

### B-K5. B's two claimed contributions — the targeting agent and the closed discover→repair loop — are both published, at scale, and uncited.

> Appendix C: "**Targeting and judgment**, at the two ends where a script has nothing to offer … the
> agent reads the diffs and the coverage gap and aims the budget"

- **AFuzz — "Agentic Fuzzing: Opportunities and Challenges", arXiv 2605.10074 (2026-05-11).** The agent
  takes a reference bug, analyses its root cause, hypothesises new sites elsewhere in the codebase that
  share that cause, and verifies each by generating and running PoCs. **40 bugs in V8** ($35,000 bounty,
  2 CVEs) plus **19 in SpiderMonkey/JavaScriptCore from V8 seeds.** That is B's front end, four months
  earlier, with an evaluation B does not have.
- **Mut4All, arXiv 2507.19275** — LLM agents crawl bug reports, identify error-prone features and
  synthesise mutators (319 Rust / 403 C++). That is "reads the repo evidence", already done.
- **CodeRover-S (ICSE 2026 SEIP, OSS-Fuzz)** — autonomously generates patches fixing vulnerabilities
  found by a fuzzing campaign. The discover→repair closed loop, in production.
- **DESIL, arXiv 2504.01379 (PACMPL)** — "Detecting **Silent** Bugs in MLIR Compiler Infrastructure",
  differential testing with UB elimination and optimization-recommendation; **23 silent + 19 crash bugs**
  in MLIR. B's exact premise and oracle class, already named for MLIR.

B's prior-art paragraph cites SynthFuzz, ISSTA-2024 ODA, "LLM-driven MLIR fuzzing (2025)",
`drom/circt-fuzzer` and firtool-vs-Scala-FIRRTL — none of the four above. A prior-art hunter on the PC
finds AFuzz in one search and B's Appendix C reads as its abstract.

## WOUNDS

### B-W1. "Normalized wire-free" names no mechanism, and the only shipped candidate does not do it.

> "it rejects `hw.wire`, so **pairs are normalized wire-free**."

Executed: `firtool -O=debug --ir-hw` emits every wire carrying an inner symbol
(`%s = hw.wire %2 sym @sym : i9`). `circt-opt --canonicalize` on that output leaves **all 6** `hw.wire`
ops standing; a wire *without* a symbol does fold. So normalization requires stripping inner symbols
first — no shipped pass does that, B names none, and inner symbols are exactly what hierarchical
references bind to. (After stripping by hand, `circt-lec` runs and returns `c1 == c2`, rc=0 — so the
oracle is operable; the step B states as already done is simply not implemented.)

### B-W2. The oracle's discriminating region is a thin slice, and the biggest bug classes are in *both* arms.

`-O=debug` is, per `firtool --help`, "Compile with only necessary optimizations" — both arms run the
whole FIRRTL import and LowerToHW pipeline, which is the bulk of CIRCT. The differential cannot see:
(i) front-end bugs (`ImportVerilog`, FIRRTL parsing) — shared by both arms; (ii) bugs inside the
"necessary" passes — shared; (iii) bugs in `circt-lec`'s own HW/Comb→SMT encoding — the oracle grading
itself; (iv) sequential behaviour past the `circt-bmc` bound; (v) anything outside HW/Comb/Seq.
B's Limitations admit (iv) and (v) only.

### B-W3. The "93% reduction" was driven by `grep`.

> "`circt-reduce --test=<script>`; it refuses to start without one, **and the oracle is that script**.
> Executed: 67 lines to 7, a '93% reduction'."

The executed reduction's interestingness test is `probe/oracle.sh`, whose entire body is
`grep -q 'comb.mul' "$1"`. Placing "the oracle is that script" immediately before the executed number
invites the reader to believe the differential oracle drove the reduction. A text search for an opcode
drove it. Appendix A discloses only "Executed, 2026-09-11".

### B-W4. The crash oracle needs an assertions-ON build the SDK is not, and the dedup key needs frames a Release build will not give.

> "(i) Crash/assert, **assertions ON**." / "sharing a crash signature (**top-3 frames** plus assertion text)"

`pin-window-analysis.md` §5.2: the prebuilt SDK's `LLVMConfig.cmake` reports
`LLVM_ENABLE_ASSERTIONS OFF`, and B's own Appendix A repeats "assertions OFF" as a known fact of the
image while the body asserts the opposite as a property of the oracle. MLIR/LLVM assertions will not
fire; top-3 frames from an unsymbolised Release build is not a stable dedup key.

### B-W5. The demo runs against a compiler 110 days and 364 commits stale, and the dedup rule cannot catch bugs already fixed upstream.

> "**Demo.** `chia job submit` runs generate → oracle → reduce → triage → repair → gate **on one
> pinned image**." / Table: "| Image | `firtool-1.148.0` | + z3, Verilator, `lit` |"

`firtool-1.148.0` is tagged **2026-05-24**; `llvm/circt` HEAD at analysis time is **364 first-parent
commits later** (measured). CHIA's README: "Issues fixed upstream after that tag won't reproduce."
B's confirmation test is "no **open** issue covers it", which does not exclude a bug fixed in those 364
commits. The loop's output can be a stream of already-fixed bugs delivered to maintainers whose
goodwill §1 identifies as the binding constraint.

### B-W6. Blast radius is a gate input that B's own appendix says does not exist.

> "**Gate.** From executed evidence only — reproduces, minimal, fix flips exactly the reduced case,
> lit gate green, **blast radius** — it emits report-only, report-plus-patch, or nothing"
> Appendix B: "**'Blast radius' has no scalar definition yet.**"

Same defect as A-W3 with less written down: A at least lists three counts.

### B-W7. The generator's entire justification is a ratio of two things that measure neither churn risk nor coverage.

> "`lib/Dialect/AXI4` took 21 commits in 90 days against 3 lit test files, ESI 88 against 18, FIRRTL 86
> against 213. The agent reads that gap"
> Appendix B: "Lit file counts are per-dialect file counts under `test/Dialect`, **not coverage
> measurements**; a dialect may be tested elsewhere in the tree."

A file count is not coverage — one lit file holds many `RUN:` lines — and conversion tests live under
`test/Conversion`, which the count excludes. Appendix B also concedes the churn counts "were not
cross-checked against release notes". The one quantitative argument for the agent existing rests on
both halves of a ratio the appendix disowns.

### B-W8. Structural dedup is evidenced by a single observed rename.

> "*Distinct*: reduced cases matching after symbol renaming (reduce renamed `@Target` to `@Foo`) …
> collapse."

One rename observed in one reduction. Canonical dedup of reduced MLIR needs hashing modulo SSA value
names, attribute order and operation order; "matching after symbol renaming" is textual equality with
one substitution and will collapse almost nothing in practice.

## NITs

- **B-N1.** "**Pitch.**" as a section label in a document a program committee reads.
- **B-N2.** "Not Track 1 design bugs in BOOM — the target is the compiler." Volunteers that B misses the
  one suggested track it superficially resembles.
- **B-N3.** "under the LLVM AI Tool Policy's disclosure and human-in-the-loop duties" — a compliance
  sentence standing in for a mechanism; no disclosure text, no human step is described.
- **B-N4.** Appendix B's first three bullets: "No end-to-end run of the full loop has been executed",
  "No bug has been discovered by this loop yet", "**The generator agent does not exist.**"
- **B-N5.** "Contamination is moot: discovered bugs never existed." Not moot — the repair stage is a model
  whose CIRCT training data is unchanged; only the bug *instance* is new, not the fix vocabulary.
- **B-N6.** "a '93% reduction'" in scare quotes: the tool's own stdout quoted as though it were a result.
- **B-N7.** "Dry window: seeded bugs — a demo, not a result." B states in advance that its fallback is
  not a result.

---

# 3. Mechanical spot-checks

## A

| # | Check | Verdict | Evidence |
|---|---|---|---|
| A1 | "76 of 84" derivation stated, internally consistent with 1,103/187/171 | **FAIL** | Derivation *is* stated (Appendix A: keyword within 20 chars of `#N` or issues URL). But Appendix B's "**stricter** variant returns **89**" exceeds the body's 84 — strictly impossible. Re-derived over the same 1,103 commits from the clone with A's stated pattern: **95 / 86 exact**; looser keyword set: 102 / 93. Intersection with the 187: **42 / 39 exact**. The body's 76 is drawn from the 1,103, not from the 171 A images. |
| A2 | Every README quote verbatim | **PASS (one silent truncation)** | "deterministic, no LLM: rebuild, rerun repro, run the full lit gate"; "`--model <id>` overrides the model of whichever backend is selected"; "The chia-circt image is pinned at **firtool-1.148.0**. Issues fixed upstream after that tag won't reproduce"; "Root cause in LLVM/MLIR (the prebuilt SDK / `llvm` submodule) is out of scope"; "the rest of the flow still assumes CIRCT"; backends Claude / `gemini-3.1-pro-high` / `google-vertex/gemini-3.1-pro-preview` — all byte-exact. The "regression repair" quote stops before "without un-fixing the bug" with no ellipsis. |
| A3 | ≈110 min arithmetic | **PASS** | (5×60 + 3×10)/3 = 330/3 = 110.0. 16 issues / 5 fixed / 3 merged matches §5.5 + Table 5. Labelled "our arithmetic" in Appendix A. Validity of the *comparison* is A-K3, not arithmetic. |
| A4 | llvm-harness and Abstain-and-Validate cited accurately | **PASS** | 2603.20075 abstract: "we introduce llvm-harness, **the first harness designed to assist LLM agents in understanding and fixing compiler bugs**"; "Our current focus is on the middle end of LLVM"; "We evaluate five frontier models." All three of A's qualifiers correct, name correct. 2510.03217 = "Abstain and Validate: A Dual-LLM Policy…", bug abstention + patch validation — A's one-liner correct. LLVM-Ens (2607.00700) "filters incorrect and redundant candidates" via LLVM-Gym build+test — A's "filters candidates by build and test" fair. |
| A5 | Blast radius = scalar with units, entry into model | **FAIL** | Three distinct counts supplied for a single `b` in `log(1+b)`; no aggregation rule, no units. The coefficient's sign is fixed a priori ("non-positive"), so the fit cannot report evidence about it. Near-constant on the corpus (156/171 single-source-file tasks). |

## B

| # | Check | Verdict | Evidence |
|---|---|---|---|
| B1 | `circt-lec` behaviour (rc=0 both verdicts; rejects `hw.wire`) | **PASS** | Executed on the SDK: equal pair → `c1 == c2`, **rc=0**; unequal pair → `c1 != c2`, **rc=0**; `hw.wire` → `error: failed to legalize operation 'hw.wire' that was explicitly marked illegal`, **rc=1**. Matches `docs/Tools/circt-lec.md`, which also states the IO-signature precondition B's grid violates (B-K1). |
| B2 | "15 fuzz issues, 13 closed" | **PASS** | GitHub search API: `repo:llvm/circt fuzz type:issue` → **15**; `+state:closed` → **13**. (Narrowing to `in:title,body` gives 4 / 3 — B's number is the broad query, which is the generous reading and the one B implies by "mention".) |
| B3 | Dedup rule and "confirmed" operational? | **FAIL** | "Confirmed" contains a self-grading disjunct (B-K4). Dedup's crash signature needs assertion text and top-3 frames the assertions-OFF Release SDK will not produce (B-W4); its structural key is textual equality modulo one symbol rename (B-W8). Neither is executable as written. |
| B4 | Prior-art citations accurate | **PARTIAL PASS on accuracy, FAIL on completeness** | SynthFuzz = "Fuzzing MLIR Compilers with Custom Mutation Synthesis", ICSE 2025 (correct); ISSTA 2024 = "Fuzzing MLIR Compiler Infrastructure via Operation Dependency Analysis", 63 bugs (correct); `drom/circt-fuzzer` unverifiable here but immaterial. Missing, all directly on B's pitch: AFuzz 2605.10074, DESIL 2504.01379, Mut4All 2507.19275, CodeRover-S / OSS-Fuzz (B-K5). |
| B5 | Headline metric's denominator team-controlled? | **PASS — and that is the flaw** | The denominator is a GPU-hour budget B chooses, so the ratio is executable but unanchored: no prior number uses it, and the numerator is self-gradable (B-K4). Fully team-controlled on both sides. |

---

# 4. Comparative scorecard (1–5, higher is better)

| Criterion | A | Justification (A) | B | Justification (B) |
|---|---|---|---|---|
| Prize-sentence fit — "most novel, creative agentic loop(s)" | **2** | §2 opens "Phases … are unchanged" and the table's first row says "unchanged"; the delta is a decision on one edge, sold to the people who own that edge. | **4** | Four new stages and two agents (generate → oracle → reduce → triage), visibly a loop; the pitch survives one sentence. |
| Upstreamability as a CHIA block | **3** | The four adapter methods are the one thing the README begs for ("the rest of the flow still assumes CIRCT") — but they get half a sentence and Non-goals bar a second target, so nothing shows they adapt. | **4** | A reducer block, a differential-oracle block, and z3/Verilator/lit in the image are things CHIA's README says it lacks; but the block boundary at Repair is wrong (B-K2), so the composition does not compose. |
| Demo strength in 5 minutes | **1** | "replays two mined rows: submit, then abstain" — two stored rows print two words through a gate with no fitted weights. | **4** | Live generate→shrink→repair→gate ending in a minimal `.mlir` is watchable and self-explaining; docked because no end-to-end run has ever happened and the generator does not exist. |
| Measurement validity of the headline | **3** | Minutes-per-correct-decision is externally meaningful, has a real blinding trick (decoys blind the reviewer to correctness) and an external label — but the label is entangled with a feature (A-K2), the ≈110 comparator is unmatched (A-K3) and N is never stated. | **2** | Numerator self-gradable, denominator self-set, and B concedes the external half "lags" past the deadline; the honest fallback (zero) is honest but measures nothing. |
| Prior-art exposure (5 = least exposed) | **3** | Abstain-and-Validate, LLVM-Ens and calibrated-confidence-for-code-revision (2604.06723) all sit on the gate; what is genuinely unoccupied is *measured human review minutes* as the outcome, and A claims no "first". | **2** | AFuzz (agentic targeted bug discovery), DESIL (MLIR silent bugs by differential testing), Mut4All (agent-synthesised mutators from bug reports) and CodeRover-S (fuzz→repair in production) all land inside the pitch; none cited. |
| Feasibility as stated | **3** | Every mechanism is arithmetic over values `verify` already prints plus a 3-line Dockerfile edit *measured* to work at a historical parent (1,027/1,027 in 939 s, red→green). The human study and the corpus size are the unfeasible parts. | **2** | One differential axis is dead (B-K1), the normalization step is unimplemented (B-W1), `circt-bmc --run` and Verilator are untested, the crash oracle needs a build the image is not (B-W4), and Repair does not accept the input (B-K2). |
| Resilience if the main bet fails | **4** | A weak model means fewer gate-passing patches, but the pin-window measurement (171/187, 38 images, one executed fail→pass, hard failure one bump off) is itself a reportable result, and a degenerate gate is a finding about the label. | **2** | Dry fuzzing ⇒ headline = 0, and B's stated fallback is "seeded bugs — a demo, **not a result**". A 4-page paper reporting nothing found, against a prize for the most creative loop. |
| **Total** | **19** | | **20** | |

---

# 5. Verdict

**The A³ PC ranks B higher. Confidence 65%.**

**Decisive reason.** The money sentence is "the most novel, creative agentic **loop(s)**", and the panel
contains the authors of `circt_issue_solver`. A's §2 opens by telling them their loop is unchanged and
its table repeats "unchanged" in row one; the contribution is a logistic regression over numbers their
own `verify` phase already prints, on an edge they already own. B hands the same panel four stages they
do not have and a demo that explains itself in one sentence. B's technical flaws are worse and more
numerous — the differential oracle's `--preserve-aggregate` axis is dead, the repair stage does not
accept the input, the motivating statistic is a search artifact, and the nearest prior art (AFuzz) is a
four-month-old paper with 40 V8 bugs — but those are flaws a PC finds only if a compiler-testing
specialist and a prior-art hunter both read carefully. A's flaw is visible in its first two sentences
and cannot be read past.

The 35% on the other side: an AI reviewer persona scoring evidence density and internal consistency
will prefer A, whose appendix is tighter and whose single enabling measurement (the pin window) is
genuinely executed; and if B shows up on Sep 24 with zero discovered bugs, A's small measured result
beats B's ambitious nothing.

**Single change to A that flips it.** Promote the adapter to the headline and add the second target.
Retarget the loop at a second MLIR-based compiler, and show the gate fitted on CIRCT transferring to it
unchanged. That converts "we put a threshold on your verify step" into "your CIRCT-welded case study is
now a compiler-repair loop with a portable decision layer" — a composable block the README itself says
CHIA does not have, and it makes the transfer claim about *repositories* rather than about a `--backend`
flag that shipped before the hackathon. A's Non-goals currently forbid exactly this.
