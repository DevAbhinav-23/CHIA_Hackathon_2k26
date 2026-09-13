# 05 Work Plan: the closed CIRCT bug loop

**Status: Draft.** Owner: Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla (IIIT Hyderabad).
Date: 2026-09-14.

## 0. Conventions

This document is normative for sequence. It does not restate what `01-FRD.md` requires, what
`02-HLD.md` structures or what `03-LLD.md` specifies; it says in what order those are built, by whom,
against which evidence, and by which date.

| Prefix | Meaning |
|---|---|
| `W-nn` | A work task. One task, one Opus agent, one definition of done. |
| `H-nn` | A human action the builder cannot perform. Each carries the date by which the user must act. |
| `A-nn`, `D-nn`, `F-nn`, `FR-nn.m`, `C-nn`, `NFR-nn` | As `00-README.md` fixes them. Never renumbered here. |
| `T0` to `T3` | The runtime tiers of `04-Test-Plan.md` §14. |

All dates and times are **IST (UTC+05:30)** unless marked AoE. The two fixed external dates:

| Date | What | In IST |
|---|---|---|
| 2026-09-24 AoE | Hackathon final: the 4-page paper with results, plus the open-sourced loop | **2026-09-25 17:29** |
| 2026-09-21 AoE | A³ workshop paper, the optional second venue | 2026-09-22 17:29 |

`03-LLD.md` and `04-Test-Plan.md` are being resynced in parallel (additive: signatures for seven
functions, test realignment). This plan is written against `03-LLD.md` §14.7's module index and
`04-Test-Plan.md` §14's tier matrix as they stand on 2026-09-14, and cites sections rather than line
numbers so the resync does not invalidate it.

`01-FRD.md` §10.4 item 2 names "the `ProbeSpec` and `CandidateRecord` schemas". That membership was
withdrawn on 2026-09-13; the seam is the seven-member contract package of `00-README.md`, now at
version 2.0, and §2 below is written against that. The erratum is recorded, not silently corrected.

---


> **Amendment 2026-09-14 (architect).** ADR-D-03 was superseded the same day: the user's Gemini API key works in Vertex AI express mode, so the development, test and campaign backend is CHIA's `vertex` backend (`gemini-3.8-flash` for every stage; the user ruled out `gemini-3.1-pro-preview`). **API discipline (user, 2026-09-14): the key carries a USD 300 limit; no live model call is made until tiers T0 to T2 are green with the model layer mocked and the code red team has passed; the first live call is the pilot (W-18) with its tiny budget; `budget.yaml` carries `campaign_spend_cap_usd` and the driver stops on it.** H-04 (Claude model ids in the `chia-claude-code` image) is optional. W-13 and W-23a use the `vertex` backend; the LLM worker image is `ghcr.io/ucb-bar/chia:latest`; `GEMINI_API_KEY` is set from the operator's shell at `chia up`, never in job metadata. The credential lives at `~/.config/bugloop/gemini.env` (mode 600).

## 1. Ownership and working rules

### 1.1 One builder

The user ruled on 2026-09-13 that one builder, the architect working through Opus agents, builds the
system start to finish. There is no split of work between people. Nobody else writes code, and no
task is blocked waiting for a second person.

The seam of `00-README.md` survives as a **test boundary**, not as a division of labour: the supply
half and the apparatus half are developed against recorded fixtures of each other and joined on a
named date (§3). That is what makes the seam testable when there is only one pair of hands.

### 1.2 How work is dispatched

**One Opus agent per task.** A task brief is written by the architect and contains exactly five
things, and an agent that is handed less than five is a defect in the brief:

1. the `FR-nn.m` identifiers the task implements, and the `03-LLD.md` sections that specify them;
2. the modules it may create or edit, named exhaustively, and the statement that it may touch nothing
   else;
3. the test tier that closes it, and the test identifiers within that tier;
4. the fixtures it may read, and the fixtures it must produce;
5. the measurement or assumption (`A-nn`) it closes, if any, and where the report goes.

**The architect verifies.** An agent's report that the tests pass is not evidence. The architect
reads the diff, runs the named tier from a clean checkout, and reads the artefacts the task claims to
have produced. A task is not done because an agent said so. This is the same rule the design phase
used and it is the reason three red teams found what they found.

**Parallel agents, on disjoint module sets only.** Two agents may run at once when their module sets
from `03-LLD.md` §1.1 do not intersect and neither imports the other's module. §9's table names each
task's parallel partner. Each parallel agent commits to its own short-lived branch off
`circt-bug-loop` and the architect merges both the same day. A three-way parallel run is not
attempted: the host has 20 cores and 15 GB of RAM, and the third agent would be waiting on the disk.

**One heavy job at a time.** An image build, a T2 run and a T3 run may not overlap with each other or
with anything else on this host. The measured build is 582 s for the five targets and 841 s with the
slang front end at `-j8`, both at nearly full memory; a concurrent lit run or cluster bring-up would
make every wall time in `04-Test-Plan.md` §14 meaningless. Light agent work (schema, ledger, results
rendering, prompts) may run beside a heavy job.

**A red team on the code, before the pilot.** A fresh-context Opus agent is given `01-FRD.md` through
`04-Test-Plan.md` and the code, and is given **no** access to the build transcript or to any agent's
self-report. Its brief is the one the three design red teams used: find kills, reproduce each kill
with a command, and rank the ten riskiest remaining assumptions. Its output gets a disposition table
under `design/reviews/`, in the same shape as the three that exist. This is W-20, on 2026-09-20,
before `T-S-pilot-01` and before the pre-registration commit. A red team after the campaign is
worthless.

### 1.3 The definition of done, per task

A task is done when **all five** hold:

1. every `FR-nn.m` in its brief has a module and a function in the code, and the module index of
   `03-LLD.md` §14.7 still describes the repository;
2. the task's named test tier passes from a clean checkout on this host, with its wall time recorded
   (T0 under 90 s; T1 about 25 min; T2 about 45 min after the image exists; T3 about 2 h 30 min);
3. every artefact the task produces exists at the path the brief names: a measurement goes to
   `analysis/measurements/<date>-<slug>.md` with its scripts and raw output beside it, a fixture goes
   under `tests/fixtures/` or `contract/fixtures/`, a run artefact goes under the run root;
4. the commit carries `Assisted-by:` and `Signed-off-by:` (§1.4);
5. the architect has read the diff.

Partial credit does not exist. A task that meets four of the five is escalated under §4, not
recorded as done.

### 1.4 Branch and commit conventions

| Item | Value |
|---|---|
| Upstream | `github.com/ucb-bar/chia`, branch `main`, base commit `16c35e92aaaf9511c6453bf94cd5cf589698f4e3` (2026-09-04) |
| Fork | The user's own fork of `ucb-bar/chia`, kept at the GitHub default name `chia`. Its URL is supplied by H-03; this plan does not invent an account name |
| Working branch | `circt-bug-loop`, cut from upstream `main` at `16c35e92` |
| New code | `examples/circt_bug_loop/` only, plus the four CHIA additions of `03-LLD.md` §1.2 |
| Commit message | CHIA's own format (`chia:AGENTS.md`): `<type>(<scope>): <short summary>`, types `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`; scope is the module basename, for example `feat(contract): the seven schemas and the validator` |
| Trailers | `Assisted-by: Claude Code:<the model id H-04 confirms>` and `Signed-off-by: <the named approver>` on every commit, with no exception, because FR-20.3 requires the trailer on filed text and a repository that carries it everywhere cannot omit it where it matters |
| Force-push | Permitted on a task branch before merge. **Forbidden on `circt-bug-loop` from the pre-registration commit onward** (2026-09-20 20:00), because FR-14.2 resolves the registration by `git log -1 --format=%H%x09%cI -- budget.yaml` and a rewritten history changes the answer |
| Upstream PR target | `ucb-bar/chia`, branch `main`, opened from `circt-bug-loop` on 2026-09-23. The three generic functions proposed for `chia/chipyard/circt.py` are separated in the pull request's file list, per `03-LLD.md` §14.6 |
| Governance files | Untouched, per FR-19.9 and `chia:AGENTS.md` |

---

## 2. The contract-first sequence

**The contract package is written, tested and frozen before any other module exists.** This is the
first rule of the plan and the one that cannot be traded away, because the seam is the only thing
that makes two independently developed halves joinable by one person working sequentially.

### 2.1 What is built, and in what order inside the task

`W-02`, on 2026-09-14, builds `contract/schema.py` and `contract/__init__.py` in full: the
`CONTRACT_VERSION` constant at `2.0`, the seven dataclasses (`SeedRecord`, `BudgetFile`, `ProbeSpec`,
`ProbeResult`, `FeedbackBundle`, `LedgerEntry`, `RunManifest`), the three nested dataclasses, the
`Generator` protocol carrying `generate(seed, feedback, remaining) -> list[ProbeSpec]` with its
read-only `LedgerSnapshot` argument view, `validate`, `to_json`, `from_json` and every error code. It
imports nothing outside the standard library, which `04-Test-Plan.md` relies on to keep the whole of
tier 0 free of CIRCT.

Then the fixtures. `contract/fixtures/` has three subtrees and only one of them can be recorded
today:

- `malformed/` is **hand-derived**, one deliberately invalid instance per error code by one edit each
  from a valid instance, plus the `dicts/` bad key sets and the MAJOR-mismatch document. It is
  written now, in full.
- `roundtrip/` is one instance of each of the seven members plus the permutation driver. Written now,
  **constructed** rather than recorded, because no run exists.
- `<schema>/` is the recorded set, produced by `bug_loop.py --record-fixtures` on a real run. It
  cannot exist on 2026-09-14. It is produced at the join (W-17, 2026-09-19) and the constructed
  instances are **replaced** by recorded ones in a commit of its own.

That replacement is the one wrinkle in a contract-first plan and it is stated rather than hidden:
**the replacement commit may change fixture contents and may not change the schema**. If recording
reveals that a schema field is wrong, that is a MAJOR bump under the package's own rule, it invalidates
every task built against the old version, and it escalates under §4 rather than being absorbed.

### 2.2 The freeze

`W-03`, the same day, is the freeze commit: `chore(contract): freeze contract package 2.0`. After it:

- the contract's commit SHA is recorded in this document's §11 table, in every task brief, and in
  `RunManifest.contract_version` at run time;
- any change to a member or to the `generate` interface is a version bump, a new freeze commit, and a
  re-record of every fixture;
- `T-U-fixt-01` is the tripwire: it fails at the commit that lets the package and the fixture set
  drift apart, which is why tier 0 runs on every commit (§10).

### 2.3 Each half develops against the other's recorded fixtures

From the freeze until the join, neither half imports the other. `tests/test_layout.py`'s second job
enforces the sharp edge of this, that no `store.py` name is imported by any supply-half module, and
that check runs in tier 0 from the day `store.py` exists.

| Half | Modules | Develops against |
|---|---|---|
| Supply | `corpus.py`, `pin_select.py`, `generate_task.py`, `mutator_synth.py`, `mutators/`, `feedback.py`, `budget.py`, `ledger.py`, `prompts/` | recorded `ProbeResult` and `LedgerSnapshot` fixtures; a constructed `RunManifest` |
| Apparatus | `probe_task.py`, `ddmin.py`, `triage_task.py`, `repair_adapter.py`, `gate.py`, `approve.py`, `store.py`, `results.py`, `bug_loop.py`, the Dockerfile, the core additions | recorded `ProbeSpec` fixtures from both arms, a recorded `SeedRecord`, a recorded `BudgetFile` |

The apparatus half is built first in calendar order, because F-03's image blocks it entirely and the
image is the longest unattended job in the plan.

---

## 3. The join

**The join is 2026-09-19.** On that date `bug_loop.py`, `cluster_single.yaml`, `bug_loop_submit.sh`
and the example's `README.md` land, and the two halves are wired together for the first time.

What is tested at the join, in this order:

1. **The integration tier of `04-Test-Plan.md` §2, all seventeen tests.** Thirteen run at T0, two at
   T1 (`T-I-app-tri-01`, `T-I-rep-gate-02`) and two at T2 (`T-I-gen-app-01`, `T-I-gen-app-02`). Every
   seam crossing is covered: generator to apparatus in both arms and through the `generate`
   interface; apparatus to triage; triage to repair; repair to gate; gate to approval; the ledger
   across the halves; the feedback bundle out and back; and the two contract-version tests, which
   must fail hard in both directions with the MAJOR-mismatch error code and no shim.
2. **`bug_loop.py --record-fixtures`**, which produces the recorded `contract/fixtures/<schema>/` set
   and retires §2.1's constructed instances.
3. **T0, then T1, then T2, each in full**, in that order, from a clean checkout: 90 s, then about
   25 min, then about 45 min.
4. **`T-S-cluster-01` and `T-S-disc-01`** on the single-machine cluster, in the evening. These two are
   pulled forward out of the T3 block for one reason: `T-S-disc-01` green is the user's stated trigger
   for the GCP hand-over (§12.1), and the trigger has to fire before the hand-over has anywhere to go.

**The join's pass criterion** is that all seventeen integration tests are green, the recorded fixture
set validates at version 2.0, and `T-S-disc-01` produces a complete artefact tree under
`<root>/<run>/seed_<sha>/iter_1/probe_<id>/` with the taxonomy counts summing. A join that is not
green by 2026-09-19 23:59 escalates under §4; it does not roll silently into the 20th, because the
20th is the red team, the full T3 block, the pre-registration commit and the campaign start.

---

## 4. No scope reduction, and the escalation rule

**Every Must in `01-FRD.md` is built.** All twenty features F-01 through F-20 are Priority: Must, and
all twenty are in this plan. Nothing is deferred, stubbed, or replaced by a note in the paper. The
GCP deployment is not an exception to this rule, because NFR-10 makes it a Should and ADR-D-14 already
downgraded it; `00-README.md` forbids scope cuts and does not protect scope additions.

**The escalation rule.** A task that will not finish does not cut itself down. The builder escalates
to the user, in the daily status of §14 or immediately if the date is within 24 hours, with four
things:

1. the task id, the `FR-nn.m` identifiers at risk, and what is actually blocked;
2. the evidence that it will not finish, which is a measured wall time or a reproduced failure, never
   a feeling;
3. **the specific cut proposed**, named from §12's ordered list and no other, with what it costs in
   the results;
4. the date by which the user's answer is needed for the cut still to help.

The builder never applies a cut on its own judgement. An agent that silently narrows a requirement to
make its tier pass has produced a defect, not a deliverable, and the architect's diff read is where
that is caught.

---

## 5. Decision ordering

Every `D-nn` is resolved in `ADR/`. What remains is each ADR's follow-up measurement or check. **No
task starts before its decision's checks are done**, and the table below is ordered so that the
gating checks land before the tasks they gate.

| Decision | Follow-up check | Owner | Date | Tasks it gates |
|---|---|---|---|---|
| D-08 | A-03: build FR-03.7's target set under the three flag strings; host part measured 2026-09-13 (M2); the **image** part is the first image build: `docker save` size, layer cost, per-probe cost inside the container | builder | 2026-09-15 | W-08 and every T2 test |
| D-08 | A-20: FR-03.6's set-equality run over the whole `test/` tree; measured 2026-09-13 on the host build (M3, 1,127 discovered, 0 failed on both sides); **re-run inside the image**, where the 62 `REQUIRES: slang` tests are no longer skipped | builder | 2026-09-15 | W-14's repair adapter, whose verify gate depends on the answer |
| D-13 | A-03's slang half: branch (a) proven on the host 2026-09-13 (M7, 841 s at `-j8`); the image-level cost closes with the first image build | builder | 2026-09-15 | W-08's `.sv` probe path, W-13's slang-entry seeds |
| D-09 | A-19: run FR-08.1's applicability rule over the corpus and report the count **with the rule that produced it**. Verilator's packaged version settled 2026-09-13 (M8, 5.020-1, all four flags present) and is re-recorded in the `ImageSpec` | builder | 2026-09-15 | all F-08 work; a count of zero drops the harness generators to a documented non-applicability, not to silence |
| D-07 | A-02: read the diffs of a random sample of 30 seeds and report the precision of the 187 and 171 counts | builder | 2026-09-15 | nothing; it qualifies the corpus and belongs beside the headline as a threat to validity |
| D-03 | The two Claude model ids: `claude --print --model claude-opus-5 -p - <<< 'reply ok'`, repeated for `claude-sonnet-5`, inside the `chia-claude-code` image with `~/.claude` mounted | **user (H-04)** | 2026-09-14 | W-10's B7 turn, W-13's A3 turns, W-14's B8 chain |
| D-05 | A-21: counted 2026-09-13 (M9, 487 closed and 101 open `label:bug`), so the fallback to fix-commit synthesis is not needed. What remains is sufficiency, answered by the synthesis itself | builder | 2026-09-17 | W-13's mutation arm, and the pre-registration commit, which records the frozen set's digest |
| D-06 | A-05: the collision and false-merge rates over the twenty labelled pairs | builder | 2026-09-17 | W-23's headline, which prints both rates |
| D-11 | No measurement. FR-12.10's acceptance is a test: kill the chain between the two writes and assert the reconciliation names the loop row | builder | 2026-09-18 | nothing |
| D-02 | No measurement. FR-13.17's URL-length branch is exercised by its own acceptance criterion in `test_approve.py` | builder | 2026-09-18 | nothing |
| D-12 | No measurement. FR-13.18's acceptance is one manual walkthrough completing both the approval and the URL without a second tool. Dry walkthrough 2026-09-18, live 2026-09-21 | builder, then **user (H-08)** | 2026-09-18 | nothing |
| D-10 | No measurement. F-02 records the lag into the `RunManifest` on every run; first recorded run 2026-09-16 | builder | 2026-09-16 | nothing |
| D-04 | No measurement. A-03's per-probe slowdown (+3.4% under `-gline-tables-only`) feeds the wall-clock allowance `W`, which is fixed in `budget.yaml` at the pre-registration commit and never afterwards | builder | 2026-09-20 | the campaign |
| D-01 | A-03 (above) and A-15: the repair chain's fail-to-pass rate over the calibration sample, in calibration mode | builder | 2026-09-20 | W-23's seeded-bug validation table |
| D-14 | No measurement. The gating item is a date, and §12.1 names it | **user (H-07)** | 2026-09-20 09:00 | `cluster_gcp.yaml` beyond the skeleton |

---

## 6. The measurement tasks that close A-01 to A-21

Statuses below are as `01-FRD.md` §7.2 records them, updated by the two reports in
`analysis/measurements/`. **A-03's image cost is first** because F-03 blocks the apparatus half
entirely, and it is the longest unattended job in the plan, so it starts on the evening of the first
legal day and finishes overnight.

| ID | Status on 2026-09-14 | Task | Owner | Date |
|---|---|---|---|---|
| A-03 | Host part **measured** 2026-09-13 (M2, M7). Image part open: no assertions-on image has ever been built | **W-04**, the first image build. Wall time, layer count, `docker save` size, per-probe cost inside the container, the `-gline-tables-only` delta re-confirmed at image level | builder | **2026-09-14 21:00 start, 2026-09-15 by 12:00 reported** |
| A-20 | **Settled on the host** (M3): 1,127 discovered, 1,058 passed, 0 failed on both builds. The 62 `REQUIRES: slang` tests were skipped there | W-04b, inside the image where slang is on: the same set-equality, with the 62 now running | builder | 2026-09-15 |
| A-10 | **Verified** 2026-09-13 (M5) against `ghcr.io/ucb-bar/chia-circt:latest` | W-04c re-asserts it against the loop's own image: `nm -u circt-opt \| grep -c __assert_fail` must now be **non-zero**, which is the inverse assertion and the one that matters | builder | 2026-09-15 |
| A-11 | **Inference** | W-04d: `cmake --trace-expand` on the image's configure step, recorded. Gates nothing; it explains why the SDK's `LLVMConfig.cmake` wins | builder | 2026-09-15 |
| A-16 | **Never executed** | W-04e: `circt-bmc --run` once inside the image against the shimmed `libz3.so.4`. Gates nothing; it stops the image's z3 handling from being assumed fully exercised | builder | 2026-09-15 |
| A-02 | **Unverified**: subject-keyword proxy | W-05b: read the diffs of 30 randomly sampled seeds, report the precision, record the sample | builder | 2026-09-15 |
| A-19 | **Unmeasured** | W-05c: run FR-08.1's applicability rule over the corpus; report the count **and the rule**. Scheduled before any F-08 work, as ADR-D-09 requires | builder | 2026-09-15 |
| A-17 | **Resolved** 2026-09-13: one denominator, 3,257 | No task | n/a | 2026-09-13 |
| A-18 | **Resolved** 2026-09-13: there was never a disagreement, two bucketings of one dataset | No task; FR-01.4 emits both and the dialect-level one is normative | n/a | 2026-09-13 |
| A-09 | **Unbuilt**: the pin window was measured at a historical parent, not at a moving `main` | W-07: F-02's acceptance, pin selection run against live `main` with the lag recorded into the `RunManifest` | builder | 2026-09-16 |
| A-21 | **Counted** 2026-09-13 (M9): 487 closed, 101 open | W-12 answers the sufficiency half: the synthesis over 487 reports, reporting how many carry enough body text to be usable input | builder | 2026-09-17 |
| A-05 | **Unexecuted** | W-11: build the twenty labelled pairs of `04-Test-Plan.md` §10, at least four of them R4 pairs, **labelled before the fingerprint is computed**; report the collision and false-merge rates | builder | 2026-09-17 |
| A-01 | **Unverified**, and it is the thesis | W-18: five seeds, one generator turn each, against the assertions-on image; count the probing inputs that fire the primary oracle. Zero out of five is a reportable result | builder | 2026-09-19 |
| A-08 | **Unwritten** | W-18b: FR-08.2's acceptance on the recorded 12-line FIRRTL register-add, regenerating both harnesses from the port list with no hand editing. Timeboxed to one day. Runs only if A-19's count is above zero | builder | 2026-09-19 |
| A-04 | **Zero over 1,127 lit tests** on the host build (M3), on one commit, for ordinary input | W-19a: `T-S-lit-01`, the control run of FR-07.9 inside the image at the run's own commit; the false-positive set is reported as measured | builder | 2026-09-20 |
| A-15 | **One data point** of 171 | W-21: calibration-mode run over the drawn sample; report the fail-to-pass rate and the CHIA status distribution | builder | 2026-09-20 |
| A-13 | **Procedure, not fact** | W-22: the pre-registration commit. It becomes fact when the commit lands | builder | 2026-09-20 20:00 |
| A-06 | **Uncalibrated**, and stays so by ADR-D-06 | W-23 reports gate precision as measured, with FR-18.8's cut-off date printed beside it. **No threshold is fitted**; fitting one after the data exists is the error the pre-registration exists to prevent | builder | 2026-09-24 09:00 |
| A-12 | **Incomplete by construction** | No verification exists and none is invented. FR-15.3's mandatory disclosure is the whole mitigation, and W-23 renders it beside the headline; M4's 96.3% file-level and 77.0% symbol-level flag rates are reported as the screen's discrimination, not as its correctness | builder | 2026-09-21 |
| A-14 | **No prior estimate**; zero is a possible and reportable outcome | W-23: the campaign's own count, rendered by `results.py`, which refuses to render without the zero-bug path being exercised | builder | 2026-09-21 |
| A-07 | **Unknown** | H-06's forum post and the response to it, read continuously; the post's URL and date go into the `RunManifest`, and any objection stops filing (§13, R-10) | **user (H-06)** posts 2026-09-17; response read to 2026-09-24 09:00 | 2026-09-17 to 2026-09-24 |

---

## 7. The pre-registration commit (F-14)

**Date: 2026-09-20, 20:00 IST.** One commit on `circt-bug-loop`,
`chore(budget): pre-register the CIRCT bug-loop campaign`, with both trailers. It lands one hour
before the campaign starts and is never amended, rebased or force-pushed afterwards.

### 7.1 What must exist before it

| Precondition | Produced by | Date |
|---|---|---|
| The corpus built, and its clone HEAD SHA recorded, so `corpus_head_sha` is measured rather than chosen | W-05 | 2026-09-15 |
| The assertions-on image built, with its `ImageSpec` and every tool binary's SHA-256 recorded | W-04 | 2026-09-15 |
| The issue mirror refreshed at least once, because A7's synthesis input is the mirror | W-10 | 2026-09-17 |
| **The mutator set frozen**, `mutators/set_v1.json` committed with its digest, and `mutator_synth.py` refusing to run again after registration | W-12 | 2026-09-17 |
| The twenty calibration SHAs drawn by `bug_loop.py --draw-calibration`, sampling the 171 exact-pin seeds with `random.Random(corpus_head_sha)` | W-22 | 2026-09-20 |
| `reduction_wall_seconds` settled against R-03's evidence from the pilot, because the value cannot be changed after this commit | W-19, W-20 | 2026-09-20 |

The draw is a **step of the pre-registration, not of the run**. A sample drawn after the commit
invalidates the campaign under FR-14.3 and FR-14.7, and `budget.py`'s fifth check asserts
`len(calibration_sample_shas) == calibration_sample_size`.

### 7.2 What the commit contains

`examples/circt_bug_loop/budget.yaml`, complete by `03-LLD.md` §9.1 and closed to any other top-level
key: `arm_window_seconds` (§11.2's W), `arm_order: [seeded, mutation]`, the three safety caps
(`generated_inputs_per_day`, `filings_per_day`, `filings_total`), `campaign_start_utc` and
`campaign_end_utc`, the measured `corpus_head_sha`, `fingerprint_top_n`, `calibration_sample_size`
with its twenty drawn SHAs, the two per-seed caps, the four per-probe limits, the two reduction keys,
`issue_mirror_issue_cap`, `filing_poll_window_seconds`, `artefact_inline_cap_bytes`, and the
`acceptance` block's seven sizes.

Nothing else is in the commit. A code change riding along would make the registration's SHA ambiguous
about what was registered.

---

## 8. The forum post (FR-20.1)

**Date: 2026-09-17, by 18:00 IST. Posted by the user**, who is the named approver, under their own
account. It must precede the campaign start (FR-20.1) and therefore also the first filing (its
acceptance criterion), and three days of lead time is deliberate: an objection that arrives after the
campaign has run cannot change what the campaign did.

**Where:** CIRCT's forum, in the CIRCT category, as a new topic. The URL and date are recorded in the
`RunManifest` and checked before the first filing.

**Content outline**, nine points, in this order:

1. What the loop is: a CHIA loop seeded with mined `llvm/circt` fix commits that generates probing
   inputs, judges them with a crash-or-assertion oracle against an assertions-on build, reduces,
   deduplicates against the open and closed issue history, and stops at a human.
2. What the oracle is, and what it is not: CIRCT assertions restored with `-UNDEBUG`, so a report
   must state the flag because `circt-opt --version` still prints "Optimized build."; the
   arcilator-versus-Verilator differential is **report-only** and never filed as a bug.
3. What will be filed: reduced, deduplicated crash and assertion reports with a reproducing command,
   the commit they reproduce at, and the reduced case inline.
4. The caps, stated as numbers: at most three filings per day and ten per campaign, from a budget
   file committed before the campaign began.
5. That a named human reads and approves every report and files it in their own browser session under
   their own account; the loop makes no GitHub write of any kind.
6. That every filed text carries an `Assisted-by:` trailer naming the tool and the model.
7. That issues labelled `good first issue` are left to human newcomers, and that maintainer feedback
   is never fed back into a model without a human first understanding and addressing it.
8. The repository URL and the pre-registration commit, so the caps can be checked rather than taken
   on trust.
9. **An explicit invitation to object**, with the statement that filing stops on any objection, and a
   named person to reply to.

---

## 9. The build order, task by task

Dependency order, with the parallel partner named. "Tier" is the tier that closes the task.

| Task | What | Depends on | Parallel with | Tier | Date |
|---|---|---|---|---|---|
| W-01 | Repository skeleton in the fork: branch, `examples/circt_bug_loop/`, `pyproject.toml` with the `bugloop-approve` entry point, `.gitignore`, `env.yml`, README stub, `tests/` layout | H-01, H-03 | none | none | 09-14 |
| **W-02** | **The contract package 2.0**: `schema.py`, `__init__.py`, the validator, the error codes, the hand-derived malformed set, the constructed roundtrip set | W-01 | none | T0 | 09-14 |
| **W-03** | **The freeze commit** | W-02 | none | T0 | 09-14 |
| W-04 | `ChiaCirctAssertDockerfile` and its workflow; the first image build; A-03, A-20, A-10, A-11, A-16 | W-03, D-08, D-13 | W-05 | T2 (after) | 09-14 evening to 09-15 |
| W-05 | `corpus.py` (A1): the mine, the `RUN:` normalisation, `SeedRecord` with diff and test files, the `SdkMap`; A-02, A-19 | W-03 | W-04, W-06 | T0, T1 | 09-15 |
| W-06 | `store.py` (B10a, B10b), `budget.py` (A6a), `ledger.py` (A6b) | W-03 | W-05 | T0 | 09-15 |
| W-07 | `pin_select.py` (A2); A-09 | W-05 | W-08 | T0, T1 | 09-16 |
| W-08 | `probe_task.py` (B2, B3, B4, B5), `ddmin.py`, and the three additions to `chia/chipyard/circt.py` with their tests under `chia/chipyard/test/` | W-04, W-06, A-19 | W-07 | T0, T1, T2 | 09-16 |
| W-09 | Fixture mining: the five recorded real failures of `04-Test-Plan.md` §5 with their inputs, argv, commits and stderr; the seven reducer branch fixtures derived from them; the symbolize and stderr fixtures | W-04, W-05 | W-08 | T2 | 09-16 |
| W-10 | `triage_task.py` (B6a, B6b, B7): the issue mirror, the fingerprint and both screens, the triage turn, the report render | W-08, W-09, H-05, D-03 | W-11 | T0, T1, T2 | 09-17 |
| W-11 | The twenty labelled duplicate pairs of §10, labelled before fingerprinting; A-05's two rates | W-09 | W-10 | T0, T1 | 09-17 |
| W-12 | `mutator_synth.py` (A7) and `mutators/`; **run the synthesis** over the 487 closed reports; freeze `set_v1.json` and record its digest; A-21's sufficiency half | W-10's mirror, D-05 | none | T0 | 09-17 |
| W-13 | `generate_task.py` (A3, A4, `ProbeWriteTool`, `SourceReadTool`) and the four prompts | W-12, W-05, D-03 | W-14 | T0, T2 | 09-18 |
| W-14 | `repair_adapter.py` (B8), `gate.py` (B9a, B9b), `approve.py` (B9c, the `bugloop-approve` CLI); the dry approval walkthrough | W-10, A-20 | W-13 | T0, T1 | 09-18 |
| W-15 | `feedback.py` (A5), `results.py` (B11) | W-06, W-08 | W-13, W-14 | T0 | 09-18 |
| W-16 | `bug_loop.py` (B12), `cluster_single.yaml`, `bug_loop_submit.sh`, the example README | W-13, W-14, W-15 | none | T0 | 09-19 |
| **W-17** | **The join**: the seventeen integration tests, `--record-fixtures`, then T0, T1, T2 in full | W-16 | none | T0, T1, T2 | 09-19 |
| W-18 | A-01's five-seed generator pilot; A-08's harness acceptance if A-19 permits | W-17 | none | T2 | 09-19 |
| W-19 | The T3 block: cluster, isolation, discovery, calibration, artefact, submit, lit control, pilot, regeneration | W-17, W-18 | none | T3 | 09-20 |
| **W-20** | **The code red team**, fresh context, plus the disposition table and the fixes it forces | W-19 | none | T0 to T2 re-run | 09-20 |
| W-21 | A-15: the calibration-mode run over the drawn sample | W-19 | W-20 | T3 | 09-20 |
| **W-22** | **The pre-registration commit** | W-12, W-19, W-20, W-21 | none | T0 | 09-20 20:00 |
| W-23 | The campaign, both arms; then the results render, the reconciliation and every mandatory disclosure | W-22 | none | T3 | 09-20 21:00 to 09-21 |
| W-24 | The live approval walkthrough and the filings, one report at a time, behind H-08 | W-23, H-06 | W-25 | none | 09-21 |
| W-25 | The paper's results section and its results figure, from the rendered tables only | W-23 | W-24 | none | 09-21 to 09-22 |
| W-26 | The upstream pull request against `ucb-bar/chia` `main` | W-20, W-23 | W-27 | T0 to T3 green | 09-23 |
| W-27 | The released archive: corpus, artefact trees, results tables, database export | W-23 | W-26 | none | 09-23 |
| W-28 | Final paper build, artefact freeze, submission package | W-25, W-26, W-27 | none | none | 09-24 |

The GCP Should, if H-07 confirms it, is W-29 on 2026-09-21 to 2026-09-22: `cluster_gcp.yaml` with the
same three worker types and resource names, plus a shared bucket at `artefact_root`, exercised by one
`T-S-cluster-01` equivalent. It is not on the critical path and §12 drops it first.

---

## 10. The test tiers in the plan

`04-Test-Plan.md` §15 owns the order and its reasons. This section owns when each tier runs and what
it costs in wall time.

| Tier | Tests | Wall time | When it runs |
|---|---|---|---|
| **T0**, no CIRCT | 275 | **under 90 s** | On every commit, from W-02 onward. It is the pre-commit gate, and the contract fixtures' compatibility check lives in it, so a MAJOR bump is caught at the commit that makes it rather than at the join |
| **T1**, the SDK or a measured build | 49 | **about 25 min**, dominated by the batched `cat-file` over 228 blobs at 125 s and the contamination `log -p` over 109 paths at 488 s | On every push, from W-05 onward. Both git walks key on the clone HEAD, so a second run the same day is seconds |
| **T2**, the assertions-on image | 40 | **about 45 min** after the image exists; the image build itself is **582 s** for the five targets, or **841 s** with the slang front end at `-j8`, plus two lit runs at 10.06 s and 10.21 s | On every image change, from W-04 onward. `T-U-image-17` runs before `T-U-image-06`; the §5 fixtures are re-verified at their own commits before §6's reducer tests read them |
| **T3**, the single-machine cluster | 20 | **about 2 h 30 min** | Nightly from 2026-09-19. `T-S-isolate-01` runs before `T-S-pilot-01`, because a repair worker that does not restore itself would corrupt every verdict the pilot then produces |

The four counts sum to 384, each test counted once at the lowest tier it can run at. **No tier is
skipped because the tier above it passed.** A green pilot proves nothing about the taxonomy mapping,
the fingerprint's transitivity or the validator's error codes, and those are where a silent defect
would change a headline.

---

## 11. The critical path

### 11.1 The dated path

Times are the end of the task on that date unless stated.

| Date | Task | What it delivers | Tier and wall time |
|---|---|---|---|
| 2026-09-14 12:00 | H-01, H-03 | Design set Approved; fork URL and approver identity in hand. Nothing before this is legal under the no-code rule | none |
| 2026-09-14 18:00 | H-04, W-01, **W-02**, **W-03** | Model ids confirmed; repository skeleton; **the contract package 2.0 written and frozen** | T0, under 90 s |
| 2026-09-14 21:00 to 2026-09-15 12:00 | **W-04** | Environment and **the first assertions-on image build**; A-03's image cost, A-20 inside the image, A-10 inverted, A-11, A-16 | image 841 s with slang, then T2 about 45 min |
| 2026-09-15 | W-05, W-06 | Corpus and `SeedRecord`s; A-02's precision; **A-19's applicability count**; store, budget and ledger | T0 90 s, T1 about 25 min |
| 2026-09-16 | W-07, W-08, W-09 | Pin selector and A-09; **the apparatus probe path**, the four probe nodes, `ddmin`, the three core additions; **the five recorded real crashes and the reducer fixtures** | T0, T1, T2 |
| 2026-09-17 | W-10, W-11, W-12 | Mirror, fingerprint, both screens, triage report; **A-05's two rates**; **the mutator synthesis run and the frozen set** | T0, T1, T2 |
| 2026-09-17 18:00 | **H-06** | **The forum post**, three days before the campaign | none |
| 2026-09-18 | W-13, W-14, W-15 | **Both generators and the four prompts**; repair adapter, gate, `bugloop-approve`; feedback and results | T0 90 s, T1 about 25 min |
| 2026-09-19 | W-16, **W-17**, W-18 | Driver, cluster YAML, submit wrapper; **the join**: 17 integration tests, recorded fixtures, then T0, T1, T2 in full; `T-S-cluster-01` and `T-S-disc-01` in the evening; **A-01's five-seed pilot** | T0 90 s + T1 25 min + T2 45 min, then about 40 min of cluster |
| 2026-09-20 09:00 to 18:00 | **W-19**, **W-20**, W-21 | **The full T3 block**, the pilot and the regeneration check; **the code red team** and its fixes; A-15's fail-to-pass rate | T3 about 2 h 30 min, then T0 to T2 re-run |
| 2026-09-20 20:00 | **W-22** | **The pre-registration commit** | T0 |
| 2026-09-20 21:00 to 2026-09-21 06:00 | **W-23a** | **The campaign**: seeded arm for W, then mutation arm for W, sequential, one cluster, one concurrency | 2 × W + about 1 h fixed |
| 2026-09-21 09:00 to 18:00 | W-23b, W-24 | **The results render** and every disclosure; the live approval walkthrough; the first filings behind H-08 | none |
| 2026-09-21 to 2026-09-22 | W-25 | **The paper's results section and its results figure** | none |
| 2026-09-22 17:29 | H-09 | A³ submission, the optional second venue | none |
| 2026-09-23 | **W-26**, W-27 | **The upstream pull request** against `ucb-bar/chia` `main`; the released archive | T0 to T3 green |
| 2026-09-24 09:00 | A-06's reading | FR-18.8's confirmation cut-off; gate precision reported as measured | none |
| 2026-09-24 18:00 | W-28, **H-10** | Final paper build, artefact freeze, **submission** | none |
| **2026-09-25 17:29** | **Deadline** | 2026-09-24 AoE | n/a |

### 11.2 The window `W`, and why

**Proposed `arm_window_seconds`: 14,400.0, four hours per arm, eight hours for the campaign.** This
is the value `03-LLD.md` §9.5's complete example already carries, and keeping it means no new number
enters the design in its last week.

Four reasons, in order of weight:

1. **It fits three spare attempts.** Two arms at four hours plus about an hour of fixed cost
   (manifest, pre-flight, image verification, mirror refresh, end-of-run reconciliation, render) is a
   nine-hour overnight job. The planned attempt is the night of 20 to 21 September. Three further
   nights are free: 21 to 22, 22 to 23, and 23 to 24, the last ending at 06:00 on the 24th with
   twelve hours still in hand. At eight hours per arm only one spare night fits, and a single failed
   campaign would end the project. The campaign is the one thing in this plan with no second source
   of evidence.
2. **The machine is also the builder.** The campaign holds all five containers and the whole of 15 GB
   of RAM. Every hour of `W` is an hour in which no image can be rebuilt, no tier can run and no
   defect found during the campaign can be fixed and retried.
3. **The arithmetic leaves the window binding, which is what FR-14.5 needs.** Apparatus concurrency
   is two `bugloop_circt` containers, so each arm has 28,800 apparatus-seconds. Under
   `probe_wall_seconds` of 60 that is an upper bound of 480 probe executions if every probe ran to its
   wall; in practice most exit far below it, M2 having measured a 4,000-operation probe at 30.6 ms,
   and the real consumer is reduction at up to 600 s per firing candidate. Either way the arm is
   stopped by its window, not by `generated_inputs_per_day` of 2,000, which is the shape the
   equal-budget claim depends on. These are bounds from measured quantities, not a yield prediction;
   A-14 records that the yield has no prior estimate.
4. **It leaves a maintainer-confirmation window.** Filings begin on 21 September and the FR-18.8
   cut-off is 24 September 09:00, giving roughly three days. A campaign pushed to the last spare night
   forfeits that window entirely, and the results would then report zero confirmed with the cut-off
   stated, which is honest but is not the result anyone wants.

`W` is the **last** thing dropped if a date slips (§12), because shortening it is the only cut that
directly shrinks the evidence the headline rests on.

### 11.3 The slack

| Quantity | Value |
|---|---|
| Planned submission | 2026-09-24 18:00 IST |
| Hard deadline | 2026-09-25 17:29 IST (2026-09-24 AoE) |
| **Slack at the end of the path** | **23 h 29 min** |
| Spare campaign attempts inside the path | 3 (nights of 21 to 22, 22 to 23, 23 to 24 September) |
| Latest useful campaign start | 2026-09-23 21:00, ending 2026-09-24 06:00 |
| Slack before the A³ optional venue | 2026-09-22 17:29 IST, reached with the campaign already run on the 20th |

The slack is deliberately at the end and not distributed through the build, because the build's tasks
are serial in their dependencies and an idle afternoon on the 17th cannot be spent on the 23rd. The
three spare campaign nights are the real buffer.

---

## 12. What is dropped if a date slips

**Nothing is ever dropped from the build.** Every Must in `01-FRD.md` is implemented and tested. What
can be dropped is what the **campaign** does, in this order and no other. Each drop is proposed by the
builder under §4's escalation rule and applied only on the user's answer.

| Order | Dropped | What it costs | Latest moment it can be dropped |
|---|---|---|---|
| **1** | **GCP.** `cluster_gcp.yaml` ships as the documented skeleton ADR-D-14 already permits, and the `RunManifest` records `deployment: single_machine` | NFR-10's Should, which neither FINAL nor PAPER asks for. The Must is untouched | 2026-09-22 18:00 |
| **2** | **The differential oracle's campaign run.** F-08 is still built, still unit-tested and still exercised against its recorded fixtures; it is simply not dispatched during the campaign, and the results artefact's "divergences observed" list is empty with the reason stated | FR-18.12's list becomes empty. No headline number moves, because the differential is report-only by design and ADR-D-06 excludes it from "confirmed" | 2026-09-20 20:00, because the decision is a `budget.yaml` value and cannot follow the registration |
| **3** | **The calibration sample size**, 20 reduced toward 10 | A-15's fail-to-pass rate gets a smaller denominator and the seeded-bug validation table gets fewer rows. ADR-D-01's mode survives; its precision falls | 2026-09-20 20:00, same reason |
| **4** | **`W`.** 14,400 s reduced, both arms equally, never one arm only | The evidence the headline rests on shrinks directly. Equality across arms is structural in the schema and survives any value | 2026-09-20 20:00, same reason |

Three of the four must be decided **before** the pre-registration commit, which is why W-22 sits at
20:00 on the 20th with the red team and the pilot already behind it. A cut decided after the
registration invalidates the campaign under FR-14.7 rather than saving it.

---

## 13. Risk register

The ten riskiest items that remain open, drawn from the three red teams' "riskiest assumptions"
tables, ordered by expected damage. Items those tables carried that have since been settled are not
repeated: reducibility (M1, 98.9%), symbolised frames naming CIRCT paths (M2), the full lit suite
under `-UNDEBUG` (M3), the assertion finding inside the published image (M5), the slang build (M7),
Verilator's flags (M8), the closed-bug count (M9), and the two Claude model ids, which H-04 settles on
the first day.

| ID | Risk | Source | Trigger | Mitigation | Resolve by |
|---|---|---|---|---|---|
| **R-01** | The seeded agent never turns a fix diff into a firing probe. A-01 is the thesis | RT-FRD 7 | Fewer than one firing probe across the five-seed pilot | None that rescues the thesis. The mitigations are honesty and coverage: FR-18.7 makes zero a reportable outcome, the head-to-head still runs and still answers whether the agent beats mutation, and the entry-tool mix is widened to the three measured tools before concluding | 2026-09-19 |
| **R-02** | The repair chain scores `attempted` rather than `fixed` on a generated crash, so no patch is ever offered | RT-FRD 8, A-15 | Zero `fixed` with `lit_ok` across the calibration sample | The gate returns `report` instead of `report_plus_patch`; the headline counts confirmed bugs, not patches, so it does not move. FR-18.5's validation table reports the rate as measured | 2026-09-20 |
| **R-03** | `circt-reduce` gets too few interestingness calls inside `reduction_wall_seconds`, so every candidate fails gate question 2 as `not_minimal` | RT-LLD 10, LLD §15.5 | More than half the pilot's `ReducedCase` rows come back `fixpoint=false` | `budget_truncated` makes it visible in the results either way. `reduction_wall_seconds` is raised on the pilot's evidence **before** the registration; after it, the value is frozen and the shortfall is disclosed | 2026-09-20 20:00 |
| **R-04** | `limit_hit` is not observable, so an out-of-memory probe is recorded as a crash and pollutes the oracle | RT-LLD 7, RT-HLD 1 | `T-E-input-06` records `crash` rather than `oom` | `CPU_HARD_MARGIN_SECONDS` and the `prlimit` soft-versus-hard gap are the designed remedy. If the limit still cannot be identified, `limit_hit=unknown` is recorded and those probes are excluded from the headline with a disclosure rather than being counted as crashes | 2026-09-16 |
| **R-05** | A revert-and-rebuild does not reproduce the published binaries, so the repair worker silently drifts from the `ImageSpec` | RT-LLD 9, LLD §15.4 | `restore_hashes_match=false` in `T-S-isolate-01` | The recorded consequence is a single-use repair worker per run, which the campaign can pay for; `repair_worker_dirty` disables B8 for the rest of the run. The failure mode the design refuses is a silent mismatch, and the re-hash is what refuses it | 2026-09-20 |
| **R-06** | A file written on a `circt:1` worker does not reach the head's artefact tree at the identical path | RT-HLD 3 | `T-S-artefact-01` fails, or the pre-flight writability check fails on any worker | `--user $(id -u):$(id -g)` on both CIRCT worker types plus the identical-path bind mount. If it still fails, the run exits non-zero as `artefact_root_unmounted` naming the worker and the path, rather than writing somewhere else. A two-minute check runs on 2026-09-15, well before the join depends on it | 2026-09-19 |
| **R-07** | Two concurrent gate re-runs deadlock on `soft=False` node affinity | RT-HLD 5 | The two-task probe hangs rather than returning | Fall back to `soft=True` and record in the `GateDecision` that the re-run may have landed on the worker that produced the verdict, which weakens question 1's independence and is disclosed rather than hidden. The probe runs **before** `gate.py` is written | 2026-09-18 |
| **R-08** | The dedup partition merges distinct bugs or splits one, so "distinct" in the headline is not what it says | RT-FRD 5, A-05 | Any false merge across the twenty labelled pairs | FR-10.2 prints the collision and false-merge rates beside the headline, and ADR-D-06 narrows the merging key to one primary fingerprint so the relation is an equivalence relation. The headline is reported with the rates, never without | 2026-09-17 |
| **R-09** | No seed is differential-applicable, or the two harness generators cannot be written from a port list | RT-FRD 9, RT-HLD 9, A-19 and A-08 | A-19's count is zero, or FR-08.2's acceptance has not passed by 2026-09-19 18:00 | F-08 is built and tested against its recorded fixtures regardless; only its campaign dispatch is at risk, and it is the second thing dropped (§12). Nothing in the headline depends on it, because the differential is report-only | 2026-09-19 |
| **R-10** | CIRCT maintainers object to machine-generated reports at the loop's rate | RT-FRD 7 context, A-07 | Any objection on the forum topic or on a filed issue | Filing stops at the objection, immediately and without argument; the caps are already three per day and ten per campaign; the results report the filings actually made. There is no mitigation for reputational damage already done, which is why the post precedes the campaign by three days and invites objection explicitly | continuous from 2026-09-17; last read 2026-09-24 09:00 |

**Three risks have no mitigation that removes them**, and this is stated rather than papered over.
R-01's only answer is to report zero; A-12's actual claim, that siblings fixed in commits with
unrelated subjects escape the contamination screen, has no verification and only FR-15.3's
disclosure; and A-06's gate precision has no fitted threshold by deliberate choice, so it is reported
as measured with a cut-off date and nothing more.

---

## 14. The daily cadence

### 14.1 What is checked, and when

| Cadence | Check |
|---|---|
| Every commit | T0, under 90 s. A red T0 blocks the commit |
| Every push to `circt-bug-loop` | T0 then T1, about 25 min |
| Every image change | T2, about 45 min, after the build's 582 s or 841 s |
| Every night from 2026-09-19 | T3, about 2 h 30 min, unattended |
| Every morning, 09:00 | The status of §14.2 |
| Every task completion | The architect reads the diff and re-runs the named tier from a clean checkout |

### 14.2 What the user sees

One screen at 09:00 IST, every day from 2026-09-14 to 2026-09-24, containing exactly six things:

1. yesterday's tasks, each with its tier verdict and that tier's measured wall time;
2. today's tasks and their parallel pairing;
3. **the critical-path date the project is now on**, against §11.1, and the slack remaining;
4. every `H-nn` due within the next 48 hours, restated with its date and what it blocks;
5. any escalation under §4, with the specific cut proposed;
6. from 2026-09-19, the path to last night's artefact tree; from 2026-09-21, the rendered results
   artefact.

Nothing else. The user does not read build logs, and a status that needs a build log to be
understood is a defective status.

---

## 15. The artefact list at submission

Delivered by 2026-09-24 18:00, frozen, and referenced from the paper.

| # | Artefact | Where | Produced by |
|---|---|---|---|
| 1 | **The loop repository**: `examples/circt_bug_loop/` in full, plus the four CHIA additions (`ChiaCirctAssertDockerfile`, its workflow, the three functions appended to `chia/chipyard/circt.py`, and their tests under `chia/chipyard/test/`) | the fork's `circt-bug-loop` branch, tagged at submission | W-01 to W-16 |
| 2 | **The seed corpus** with its commit-to-release map: the `SeedRecord` set, including each seed's diff and test-file text, and the `SdkMap` | the released archive | W-05 |
| 3 | **`budget.yaml`** and its registration commit SHA | the repository, at the pre-registration commit | W-22 |
| 4 | **The pilot artefact tree**: `T-S-pilot-01`'s full run root | the released archive | W-19 |
| 5 | **The campaign artefact tree**, both arms: every generated input, every oracle verdict, every reduced case, every repair transcript, every gate decision | the released archive | W-23 |
| 6 | **The results tables**: the headline with and without contaminated candidates, the five secondaries per arm, the separate seeded-bug validation table, the failure taxonomy, the divergences list, the contamination columns, the collision and false-merge rates, the lag disclosure, the two mandatory disclosure sentences, and FR-18.8's cut-off date | the results artefact, rendered by `results.py` | W-23 |
| 7 | **The database export**: `loop.db`'s DDL and a row export, since `loop.db` itself is gitignored | the released archive | W-27 |
| 8 | **The paper PDF**, four pages, with the results section and the results figure | `paper/` | W-25, W-28 |
| 9 | **The pull request link** against `ucb-bar/chia` `main` | GitHub | W-26 |
| 10 | **The forum post URL and date**, and the `FilingRecord`s: approver, timestamp, gate answers, licence confirmation and issue URL for every filing | the `RunManifest` and the results artefact | H-06, W-24 |

`04-Test-Plan.md` §13's committed fixture set ships inside artefact 1 and is bounded at about 60 MB;
the issue mirror at about 30 MB and the results stores at about 20 MB dominate it.

---

## 16. Human actions, collected

Every action the builder cannot perform, with the date by which the user must act and what it blocks.
Six of the ten are on or before 2026-09-17.

| ID | Action | Due (IST) | Blocks if late |
|---|---|---|---|
| **H-01** | Approve `01-FRD.md` through `05-Work-Plan.md`, moving each to Approved | **2026-09-14 12:00** | **Everything.** The no-code rule permits no implementation before it |
| **H-02** | Confirm the A³ HotCRP abstract registration is lodged | 2026-09-15 12:00, against a hard deadline of 2026-09-15 17:29 (2026-09-14 AoE) | The optional second venue only |
| **H-03** | Create the fork of `ucb-bar/chia`, supply its URL, and name the approver whose identity goes in every `Signed-off-by:` and every `FilingRecord` | **2026-09-14 12:00** | W-01, and therefore the whole build |
| **H-04** | Confirm the two model ids inside the `chia-claude-code` image: `claude --print --model claude-opus-5 -p - <<< 'reply ok'`, repeated for `claude-sonnet-5`, with `~/.claude` mounted. It consumes the user's subscription, which is why it is a human action | **2026-09-14 18:00** | W-10's B7 turn, W-13's A3 turns, W-14's B8 chain, that is every agent stage |
| **H-05** | Place a **read-only** `GITHUB_TOKEN` in one file on the head machine, mode 0600, outside the repository. No write scope anywhere, per NFR-07 | **2026-09-16 12:00** | W-10's issue-mirror test, and through it W-12's synthesis and the pre-registration commit |
| **H-06** | **Post the method to CIRCT's forum**, §8's nine points, and return the URL and date | **2026-09-17 18:00** | The campaign start (FR-20.1) and the first filing |
| **H-07** | The GCP hand-over decision: supply the project and credits, or say GCP is dropped. Trigger already met by `T-S-disc-01` green on 2026-09-19 | 2026-09-20 09:00, latest useful 2026-09-22 18:00 | The NFR-10 Should only. §12 drops it first |
| **H-08** | Approve each report in `bugloop-approve`, confirm the Apache-2.0-with-LLVM-exceptions licence for any patch, file it in your own browser session under your own account, and return the issue URL where the poll did not find it | from 2026-09-21 09:00, at most 3 per day and 10 in total | Every filing, and therefore the confirmed count |
| **H-09** | A³ submission, the optional second venue | 2026-09-22 17:29 (2026-09-21 AoE) | The second venue only |
| **H-10** | **Hackathon submission**: paper PDF, repository link, released archive | **2026-09-24 18:00**, hard deadline 2026-09-25 17:29 (2026-09-24 AoE) | Everything |

### 16.1 The GCP trigger, stated once

The user deferred GCP until the loop runs end to end on the single machine. **The trigger is
`T-S-disc-01` green**, one full iteration in discovery mode on `cluster_single.yaml`, expected
2026-09-19 at about 21:00. The hand-over is then wanted by **2026-09-20 09:00**, and the **latest
useful date is 2026-09-22 18:00**: after that, the remaining days belong to the pull request, the
archive and the paper, and `cluster_gcp.yaml` ships as the skeleton ADR-D-14 already permits with the
`RunManifest` recording `deployment: single_machine`. GCP is a Should, it is first in the drop order,
and no Must depends on it.

---

## 17. What this document leaves open

Three things, named so that silence is not mistaken for a decision.

1. **The fork's account name.** H-03 supplies it. This plan names the upstream, the branch, the base
   commit and the conventions, and declines to invent a GitHub handle.
2. **Whether the recorded fixture set changes any schema.** §2.1 states the rule: recording may change
   fixture contents and may not change a schema, and a schema change discovered at the join is a MAJOR
   bump that escalates rather than being absorbed. Whether it happens is unknown until 2026-09-19.
3. **Every wall time after the join is planned, not measured.** T0 through T3 carry measured or
   `[DEFAULT]` figures from `04-Test-Plan.md` §14; the campaign's fixed overhead of about one hour, the
   red team's afternoon and the paper's day are estimates by the architect. If any of them doubles,
   §12's drop order is what absorbs it, and §4 is how the user hears about it.
