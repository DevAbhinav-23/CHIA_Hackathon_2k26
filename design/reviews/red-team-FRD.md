# Red team — `design/01-FRD.md` and `design/00-README.md`

**Date:** 2026-09-13. **Stance:** hostile. Job is to break the document before implementation starts, not to fix it.
**Targets:** `design/01-FRD.md` (1,709 lines, Draft), `design/00-README.md` (87 lines, Draft).
**Claim under attack:** that two engineers can implement independently from this with "no surprises".

**Verification performed for this review**

| What | How |
|---|---|
| CHIA citations | 41 distinct cited line ranges opened at `~/.cache/chia-src` commit `16c35e92aaaf9511c6453bf94cd5cf589698f4e3` (confirmed by `git log -1`) |
| CIRCT citations | `~/.cache/chia-pin-smoke/circt` at `b792c772819df723628d1fe6073269b85a8ade5d` (confirmed) |
| SDK tool behaviour | `circt-reduce`, `arcilator`, `firtool`, `circt-verilog`, `circt-opt` run with `LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim` |
| Corpus | `analysis/pin_window_raw.json` re-derived in Python (187 / 171 / 16-at-one-bump / 38 tags reproduced) |
| Binaries | `readelf -S`, `nm` over the SDK libs and over the completed `-UNDEBUG` build at `~/.cache/chia-pin-smoke/bassert/bin/circt-opt` |
| Churn | `git log --first-parent` over `lib/` + `include/` at CIRCT `b792c772` |

**Score: 13 KILLS, 23 WOUNDS, 11 NITs.**

What holds up, stated once so it is not re-litigated: the requirement IDs are clean (170 FRs, zero duplicates, zero gaps; NFR-01..12 complete; G-01..42 complete); every FR carries an `*AC:*` line (182 markers, 0 missing); `circt-reduce`'s polarity in FR-09.2 is **correct** (verified in `circt:lib/Reduce/Tester.cpp:57-60` — default interesting-on-zero, so no `--test-must-fail`); C-12 is correct (`--test` is demanded even with `--list` and a positional file — executed); C-05's five AIToolPolicy obligations are all at the cited lines; C-08 is correct; the model-id list in D-03 is correct at all eight cited lines; and the §4.3 absence claims (`circt-reduce`: 0 references in CHIA; `/search/`: 0 callers) are correct. The document is far above the usual standard. Every finding below is in what it left undefined, not in what it got wrong about prose.

---

## 1. KILLS

Ranked. A KILL blocks implementation or makes a reported result wrong.

---

### K1. `circt-reduce` cannot read `.fir` or `.sv`, and the FRD has no requirement for what happens then — so whole seed classes are silently gated out

**Executed**, SDK `circt-reduce`:

```
$ circt-reduce --test=ok.sh t.fir -o out.fir
Reading input
loc("…/t.fir":1:7): error: expected '{' to begin a region
$ circt-reduce --test=ok.sh t.sv  -o out.sv
Reading input
loc("…/t.sv":1:7): error: expected '{' to begin a region
```

`circt-reduce` parses MLIR generic/textual syntax only.

Now the corpus. FRD line 363 (FR-01.3) admits five entry tools including `firtool` and `circt-verilog`. PAPER §2 line 114: "About 127 of the 187 seeds sit in code that no FIRRTL input can reach." Re-derived from `pin_window_raw.json`: 31 seeds are `ImportVerilog`, 12 `MooreToCore`, 3 `Moore` — the `.sv` region, whose entry tool is `circt-verilog`, whose input language `circt-reduce` cannot open. FIRRTL seeds whose `RUN:` line feeds `firtool` a `.fir` file are in the same position.

The FRD covers neither case:

- FR-09.6 (line 773) covers "reduction makes no progress" → `reduced=false`, candidate proceeds.
- FR-09.7 (line 775) covers a failed re-check → `reduction_changed_failure`.
- Nothing covers "the reducer could not read the input at all."

Then the gate closes on it. FR-13.3 (line 963): "Question 2 shall be answered by the reducer's own record: `reduced=true` with a re-checked verdict passes; `reduction_changed_failure` fails." `reduced=false` — the FR-09.6 state the FRD explicitly says "shall still proceed" — has **no answer**. FR-13.10 (line 977): "A candidate with any unanswered question shall be refused."

So every candidate whose input language `circt-reduce` cannot parse, plus every already-minimal candidate, is refused by the gate with no recorded reason. PAPER §2 stage 5 and FINAL §2 both present reduction as universal. Two engineers will resolve this two different ways (one treats `reduced=false` as a pass, one as a fail) and the headline count differs by the size of the `.sv` region.

---

### K2. The `-UNDEBUG` build has no debug information, so FR-07.4's acceptance criterion cannot be met under FR-03.4's flag string

FR-03.4 (line 462) fixes the flag exactly: `-DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG"`, with the AC that `CMakeCache.txt` contains that literal string. No `-g`. No `-gline-tables-only`.

FR-07.4 (line 664): "the oracle shall produce symbolised stack frames using the SDK's `llvm-symbolizer` … *AC:* frames are non-empty and **name CIRCT source paths** for a crash inside CIRCT."

**Measured** on the actual completed `-UNDEBUG` build that FINAL Appendix A cites:

```
/home/adi/.cache/chia-pin-smoke/bassert/bin/circt-opt   73M   .debug_info sections: 0
/home/adi/.cache/chia-pin-smoke/src/build/bin/circt-opt 60M   .debug_info sections: 0
/home/adi/.cache/chia-pin-smoke/circt-sdk/lib/libMLIRIR.so    .debug_info sections: 0
```

No debug info anywhere. `llvm-symbolizer` can return demangled function names from `.symtab` (136,685 defined symbols in the `-UNDEBUG` binary) but **cannot return a source path or line** for any frame. FR-07.4's AC is unsatisfiable as written; FR-07.5's "top resolved frames lie in LLVM or MLIR rather than CIRCT" degrades to a symbol-name heuristic; FR-10.1 key (b) and FR-10.5's evidence field degrade with it.

The fix — add `-g` — is not in the FRD, changes the image size by roughly an order of magnitude, and lands squarely on A-03, which the FRD already marks unmeasured and D-08 already makes the first task of implementation. FR-03.4 and FR-07.4 cannot both be implemented.

---

### K3. FR-13.2's "freshly started container" fights CHIA's design and is not reachable from a CHIA node

FR-13.2 (line 961): "Question 1 shall be answered by re-running the reproducing command in a **freshly started container** from the run's `ImageSpec`, not by reusing the original container. *AC:* the re-run's container id differs from the original's."

CHIA's model, verified:

- `chia:docs/user_guides/docker_images.rst:17-26` — "At cluster start, `chia up` (over SSH to the worker's host) does roughly this: `docker run -d … <image> sleep infinity` / `docker exec -i <container> bash --login`". Containers are created once, at `chia up`.
- `chia:docs/concepts/overview.rst:59-70` — logical workers "are mapped onto machines when the cluster comes online". Long-lived.
- `chia:examples/circt_issue_solver/cluster.yaml:46-50` — `circt_worker` has `min_workers: 2`, `max_workers: 2`. Two containers, fixed.
- `grep -rn "docker.sock" ~/.cache/chia-src` → **0 hits**. No cluster YAML or Dockerfile mounts the Docker socket.
- `grep -rn "docker build\|buildx" ~/.cache/chia-src/chia` → **0 hits**. `chia:chia/cli/main.py:99-130` offers `up`, `down`, `viz`, `viz-profile`, and Ray-proxied `status`/`list`/`job`/`ray`. Nothing starts a container from inside a loop.

A `@ChiaFunction` running on a `circt` worker has no way to start a container and no way to read a container id. FR-13.2 requires infrastructure CHIA does not have and the FRD does not scope. Its AC cannot be executed at all.

The hostile reading is worse: the FRD's own §4.2 lists the cluster layer as "**Reused unchanged**; the loop ships its own YAMLs", so the only place this could live is outside the framework the paper claims to compose with.

---

### K4. FR-12.3's pre-written `repro.sh` systematically mis-scores the commonest CIRCT assertion fix

CHIA's contract, verified verbatim at `chia:examples/circt_issue_solver/prompts/reproduce.md:8-9` and `chia:examples/circt_issue_solver/circt_util.py:134-137`:

> repro.sh MUST exit 0 if and only if the bug is FIXED, and exit non-zero while the bug is still present.

and, at `reproduce.md:12-14`, the prescribed shape for exactly this loop's class of bug:

> Crash / assertion / "UNREACHABLE" / verifier error: just run the tool on the minimal input. Its non-zero exit (or the crash) reproduces the bug today; a clean run after the fix exits 0.

FR-12.3 (line 912) makes the adapter pre-write such a script for a generated crash input.

The contract assumes the fix makes the tool **succeed**. For an assertion fired on input the pass should have rejected — the single most common CIRCT crash class and the one the seeded generator is designed to produce — the correct fix is to emit a proper diagnostic. After that fix the tool still exits non-zero. `circt_run_script` returns non-zero, `repro_fixed = rebuild["success"] and repro_after["exit_code"] == 0` is `False` (`chia:examples/circt_issue_solver/issue_task.py:226`), `status` becomes `"attempted"` not `"fixed"` (`issue_task.py:274`), and FR-13.6 (line 969) therefore never returns `report_plus_patch`.

"Repairs merged" is one of FINAL §4's five secondaries and one of FR-18.4's five. The FRD makes it structurally unreachable for the class it scoped repair to, and never says so.

---

### K5. FR-10.2's duplicate rule is not an equivalence relation, so FR-18.3's headline number is order-dependent

FR-10.2 (line 811): "Two candidates shall be declared duplicates when **any one** of the three keys is equal between them."
FR-18.3 (line 1194): "**Distinct** means one per surviving dedup fingerprint (F-10): two filings sharing a fingerprint count once."

"Any one of three keys" is symmetric and reflexive but **not transitive**. A and B share the assertion text; B and C share the structural hash; A and C share nothing. Whether that is one bug or two depends entirely on the implementation: pairwise marking gives two, union-find gives one. The FRD picks neither. The headline metric of the whole paper differs between two engineers implementing the same FR.

Two further holes in the same requirement:

- Key (b) is "the top N symbolised frames, N configured" (line 809). `budget.yaml`'s mandatory contents (FR-14.1, line 1016) are the compute allowance, the input caps, the filing caps, and the campaign timestamps. `N` is not among them. The headline metric therefore carries a free parameter chosen *after* the data exists, which defeats the pre-registration FR-14.2 enforces.
- Given K2 (no debug info), key (b) is a tuple of function names, and two distinct bugs in one pass will routinely agree on it. Structural hashes of *reduced* cases collide for the same reason — reduction drives every case toward the same small module. The rule as written over-merges, which deflates the headline count, which is the number the paper reports.

FR-10.2's AC declines to bound this: "the acceptance is that the rates are *measured and reported*, not that they meet a threshold." Measuring a rate you then do nothing about does not make the headline number well-defined.

---

### K6. D-04's recommended budget unit is the one the FRD itself says favours the arm under test

D-04's own option table, line 1460:

> (a) **Generated inputs** … Ignores that one agent turn costs far more than one mutation, so **it favours the seeded arm on compute**.

D-04's recommendation, line 1466:

> **(e), with generated inputs as the primary and wall-clock as the secondary.**

The document names the bias and then adopts it. Under (e) the mutation arm is stopped at N inputs while having compute to spare; the secondary wall-clock cap binds on whichever arm is *slower*, which is the seeded arm, so the secondary protects the mutation arm from nothing. A mutation fuzzer's entire advantage over an agent is throughput — that is where FLEX's 80-bugs-in-30-days comes from (FINAL Appendix A). Capping inputs at what an agent can write deletes the baseline's only edge.

FINAL §4 says the budget is "GPU-hours, input cap, filing cap" — compute first. PAPER §4 line 231 says "the compute allowance and the caps on generated inputs and on filings". The FRD demotes compute to a secondary and never records that it is departing from both.

Consequence for the result: the head-to-head as specified cannot support the sentence "at equal budget the seeded arm found more", because the budget unit is not compute and the arms are not at equal compute. A reviewer who reads D-04's own option table will say so.

Secondary defect in the same decision: FR-14.5 (line 1024) is written for one unit — "The two arms' caps shall be equal on whichever unit D-04 selects, and the manifest shall name **that unit**", with a schema check "on the selected unit". Option (e) selects two. FR-14.5 and D-04's recommendation are mutually inconsistent.

---

### K7. FR-18.6's failure taxonomy cannot sum, contradicting FR-13.11

FR-18.6 (line 1200): "The failure taxonomy shall record, for every candidate reaching the gate, **exactly one** of `unreproducible`, `duplicate`, `invalid_input` or `new_bug` … *AC:* the taxonomy's counts sum to the candidate count."

FR-13's stopping points (lines 959-968) produce these outcomes:

| Gate question | Failing values | Taxonomy bucket |
|---|---|---|
| Q1 reproduce | no | `unreproducible` |
| Q2 minimal | `reduction_changed_failure` | **none** |
| Q2 minimal | `reduced=false` | **unanswered** (see K1) |
| Q3 valid | `invalid_input` | `invalid_input` |
| Q3 valid | `known_issue` | `duplicate`? undefined |
| Q3 valid | `untriaged` | **none** |
| Q4 new | `duplicate_of_candidate`, `known_open_issue`, `known_closed_issue`, `fixed_post_pin` | `duplicate` |
| Q4 new | `dedup_unavailable` | **none** |

Three FRD-defined refusal states have no bucket. FR-13.11 (line 982) requires "A candidate refused at any question shall still be persisted in full, with its failing question recorded, **so the failure taxonomy is complete**." It cannot be, under FR-18.6's four-value vocabulary. PAPER §4's "unreproducible, duplicate, invalid input or new bug" carries the same four values, so the fix touches the paper.

---

### K8. Differential candidates can never reach a human, yet F-08 and F-11 specify their report template

Chain of requirements, all in this document:

1. FR-09.8 (line 777): "The reducer shall **not** run on a `differential` candidate."
2. FR-13.3 (line 963): gate question 2 "shall be answered by the reducer's own record".
3. FR-13.10 (line 977): "A candidate with any unanswered question shall be refused."

A `differential` candidate therefore has no reducer record, no answer to question 2, and is refused by the gate — always. Meanwhile FR-08.6 (line 720) specifies a no-adjudication report template for exactly this class, FR-11.9 (line 877) requires template selection by class, and FR-08.7 requires the rendered report cite `circt/arc-tests`. The FRD builds a report that nothing can emit.

FINAL §2 calls the differential "report-only", which reads as *reported but not filed*. The FRD never states where a report-only candidate goes: it is not filed (correct), it is not gated through (K8), and no requirement says a `Report` exists for it outside the gate path.

---

### K9. FR-01.1 specifies the corpus's output count without specifying the corpus's filter

FR-01.1 (line 359) lists the fields of a `SeedRecord` and then asserts (line 360) "the output has exactly 187 records, exactly 171 with a non-null tag".

Nowhere does the FRD state what "mined commit" means. The rule exists only in `analysis/pin-window-analysis.md` §2 lines 74-79 — first-parent commits touching 1–2 files under `lib/` or `include/` **and** adding/modifying ≥1 file under `test/` or `integration_test/`, with subject matching a fourteen-alternative case-insensitive word-boundary regex — and PIN is cited in the FRD only as a source of *numbers*, never as normative for the filter.

I re-derived it from `analysis/pin_window_raw.json` with that regex and it reproduces **187 / 171 / 16-at-exactly-one-bump / 38 distinct tags, median 3, max 27**, so the rule is recoverable. But an engineer building F-01 from 01-FRD.md alone cannot recover it, and the seam contract depends on it (the mutation arm consumes the seed's test file; the seeded arm consumes its diff).

This is the clearest instance of the general defect: the FRD frequently pins the *acceptance number* and leaves the *rule that produces it* to a document it does not make normative.

---

### K10. FR-01.4's acceptance criterion quotes a self-contradictory sentence and is therefore unsatisfiable; A-18 records a disagreement that does not exist

FR-01.4's AC (line 366) requires the bucket counts to "reproduce FINAL Appendix A: FIRRTL 37, ImportVerilog 31, `include/circt/Dialect` 16, MooreToCore 12, …".

FINAL Appendix A's own source cell (FINAL line 61) reads: "bucketed by the first `lib/`-or-`include/` path each commit touches; **`include/circt/Dialect/<X>` seeds are bucketed under dialect `<X>`**." Those are two different bucketings, and the printed list follows the first, not the second. You cannot simultaneously have a bucket of 16 named `include/circt/Dialect` and have those 16 filed under their dialects.

Settled here, from `pin_window_raw.json`:

| Bucketing | Result |
|---|---|
| First lib/-or-include/ path, `include/circt/Dialect` kept as its own bucket | FIRRTL 37, ImportVerilog 31, include/circt/Dialect **16**, MooreToCore 12, LLHD 11, Comb 7, Synth 7, ExportVerilog 5, CoreToFSM 5, ESI 5, HWToBTOR2 4, RTG 4, OM 3, Moore 3 — **exactly FINAL's printed list** |
| Same, but `include/circt/Dialect/<X>` merged into `<X>` | FIRRTL **42**, ImportVerilog 31, MooreToCore 12, LLHD **12**, Synth **9**, Comb **8**, Moore **5**, ExportVerilog 5, CoreToFSM 5, ESI 5, OM 4, HWToBTOR2 4, RTG 4, HW **3**, Arc **3**, Seq 2 — **exactly RT3 §1 K2's table** |

The 16 splits as FIRRTL 5, Moore 2, Synth 2, Comb 1, HW 1, Arc 1, SV 1, LLHD 1, DC 1, OM 1.

So A-18 ("Two disagreeing re-derivations", line 1390) and FR-08.1's `[UNVERIFIED]` scope note (line 711) are wrong about the nature of the disagreement: it is one dataset under two bucketing rules, not two measurements in conflict. Both are right. The FRD's prescribed settlement — "re-run FR-01.4's bucketing and compare against RT3's table" — will reproduce the difference forever and never close. Meanwhile the *substantive* question (how many seeds the differential can discriminate) stays open behind a resolved-looking flag, and it is the question that decides whether F-08 is worth building at all.

---

### K11. NFR-01's cited mechanism does the opposite of what NFR-01 requires

NFR-01 (lines 1315-1316): "Any row of any results table shall be **re-runnable** from stored artefacts … *AC:* pick any three rows at random; each **re-runs** from its artefact directory with `chia job submit` and **produces the same verdict**. CHIA's cache-and-bypass mechanism is the supported way to replay a recorded node result."

`chia:chia/base/bypass.py:3-5`, verbatim: "a function is still dispatched through Ray … but **the real computation is replaced with pre-recorded data**." `chia:chia/base/cache.py:13-24`: "The cache does *not* auto-serve. To replay a cached value, register a bypass provider that reads it back … Cache = write-through populate; bypass = read path."

Bypass returns the stored value. It does not recompute. Replaying a row through it proves nothing about reproducibility — it proves the row was stored. The evidence NFR-01 cites invalidates NFR-01's own acceptance criterion, and FR-18.11 ("A result row that cannot be regenerated … shall be marked as such") and F-17's feature acceptance ("one completed run's results table is regenerated from the artefact tree alone … and matches") both inherit the error.

Two engineers will disagree on whether "re-run" means "re-execute the tool" or "replay the cache", and only one of those supports the claim the paper makes.

---

### K12. The seam is not one contract, so the two-person split does not hold

`00-README.md` lines 74-83 commit to "**exactly one seam** … The contract is the `ProbeSpec` written across it and the `CandidateRecord` returned across it. Both are versioned."

At least four objects cross:

1. `ProbeSpec` — down. ✓
2. `CandidateRecord` — up. ✓
3. `FeedbackBundle` — **down again**. FR-16.1 (line 1103): the bundle carries, per previous-iteration input, "the stage it stopped at, the reason, **the oracle verdict** where one exists, and **the reduced case** where one exists". Both are apparatus-side objects. The generator half must now know `OracleVerdict` and `ReducedCase` schemas, which are the other half's internals.
4. `BudgetLedger` — **both directions**. FR-14.4 (line 1022) accrues "per arm and per stage"; the stages span both halves. FR-14.5's equal-cap check and FR-18.10's stop-both-arms rule read it from above and below.

Plus `RunManifest`, which FR-17.6 (line 1153) puts on "every artefact" of both halves, and whose fields are written by F-02 (below), F-03 (below), F-05 (above, the mutator-set SHA), F-14 (cross) and FR-20.1 (outside).

`00-README.md` line 85 then has `05-Work-Plan.md` state "the fixture set each half uses to test against the contract before the join". A fixture set for a two-object contract is not a fixture set for this. The one-seam property is the entire basis of the two-person rule and of the no-code rule's stated rationale ("the largest risk is two people building incompatible halves"). It is not established.

---

### K13. Gate question 3 is answered by a language model, so the gate is not mechanical and gate precision is model-dependent

F-13's opening line (line 948): "**Four mechanical questions**, then a person."
FR-13.4 (line 965): "Question 3 shall be answered by **the triage classification**: `bug` passes; `invalid_input`, `known_issue` and `untriaged` fail."
FR-11.1 (line 858): "**The agent** shall classify each candidate as `bug`, `invalid_input` or `known_issue`."
FR-11.2 (line 860) constrains the agent only for the `known_issue` case; the `bug` versus `invalid_input` call is the model's alone.

G-30 defines gate precision as confirmed filings over filings, and FR-18.4 lists it as a secondary result. Its denominator is therefore gated on an LLM judgement. PAPER's Fig. 1 caption asserts "no number in the result comes from the model", and NFR-03 asserts "No number reported as a result shall originate inside a model". Gate precision originates, in part, inside a model.

This also bears on whether a CIRCT maintainer accepts the output. "Is the input valid" is the hard question in compiler fuzzing — verifier-valid IR that violates an undocumented pass precondition is the standard rejected report — and the FRD delegates it to the component it elsewhere forbids from deciding anything.

---

## 2. WOUNDS

Ambiguities and gaps that will cause rework. Ranked.

**W1. Whether a probe runs under a shell is undefined, and the primary oracle depends on it.**
FR-06.1 (line 613) says execute "the tool and argument vector"; FR-06.4 (line 619) says capture "the signal if any"; FR-07.1 (line 658) fires when the probe "terminated by signal". F-06's reuse column names `circt_run_script` (`chia:examples/circt_issue_solver/circt_util.py:126-148`), which runs `bash <script>` — under a shell, SIGABRT surfaces as exit status **134**, not as a signal, and `circt_run_script` already returns `exit_code: -1` for a timeout (line 147), colliding with the `-1` that `Popen` uses for SIGHUP. Direct `execve` and shell invocation give different oracle verdicts for the same probe. Not stated anywhere.

**W2. lit `RUN:` line shapes are not handled, and the one AC exercises none of them.**
Measured over CIRCT `test/` at `b792c772`: **1,714** `RUN:` lines total; **81** begin with `not `; **1,302** contain a pipe; **218** use `%t`, `%S` or `%{…}`; **11** use `split-file`. FR-01.2 (line 361) extracts the line "verbatim" plus "the first CIRCT tool name"; FR-04.2 (line 517) requires the `ProbeSpec` carry "the full argument vector". The FRD never says whether `not`, `env` and `split-file` wrappers are stripped, whether the `| FileCheck %s` tail is dropped, or how lit substitutions are resolved. For a `not`-wrapped seed the oracle's exit-status polarity inverts. FR-01.2's AC uses `f2b15a44ec70`, whose line is the cleanest shape in the corpus.

**W3. FR-15.1's contamination screen is a near-constant and cannot discriminate.**
Measured at CIRCT `b792c772`, over 1,313 `.cpp/.h/.td` files under `lib/` + `include/`:

| Window | First-parent commits | Distinct source files touched | Share of tree |
|---|---|---|---|
| 30 d | 66 | 148 | 11.3% |
| 90 d | 289 | 358 | 27.3% |
| 365 d | 1,777 | 804 | 61.2% |
| 730 d | 3,245 | 1,131 | 86.1% |

FIRRTL subtree: **132 of 139 files (95%)** touched in 24 months. FR-15.1 (line 1063) flags a candidate when *any* post-seed commit touches a file named in its frames, with **the seed's commit date** as the lower bound, over a corpus spanning 24 months. The flag fires on almost everything. PAPER §4 says a match "changes what the number means" — under this rule it changes nothing, because it is nearly universal. FR-10.4 reuses the identical rule with the *run's* commit as the lower bound (a lag window of at most 16 days, so ~5-10% of the tree), where "over-inclusive by design" (line 815) is defensible; the FRD applies that one justification to both.

**W4. D-01(c) costs up to 38 images and the FRD never prices them.**
PIN §4 line 119: the 171 exact-pin seeds span **38** pin windows. Measured here: SDK 661 MB extracted; `-DNDEBUG` `circt-opt`-only build tree 355 MB; `-UNDEBUG` `circt-opt`-only build 494 MB. CHIA's own Dockerfile comment (`ChiaCirctBaseDockerfile:101`) calls `ninja circt-opt` "the slow part of the build (~30 min single-core)"; PIN §5.4 measured 939 s at `-j6` for 1,027 targets. Thirty-eight images at roughly 4-5 GB each is ~150-190 GB of disk and ≥10 hours of build before the campaign, before FR-03.7's wider target set (unmeasured, A-03) and before `-UNDEBUG`. D-01's consequence column says only "Up to 38 images (PIN §4)". Against C-10 (2026-09-24 AoE) this is the single largest unpriced item in the document.

**W5. FR-03.7 and D-08 misstate the status quo; the marginal target is `circt-reduce` alone.**
`chia:examples/circt_issue_solver/circt_issue_loop.py:44-45` already sets `TOOL_TARGETS = ("circt-opt", "firtool", "circt-translate", "arcilator", "circt-lec", "circt-bmc")`, and `circt_warm_build` (`chia:chia/chipyard/circt.py:661-695`) builds them from source at warm-up — its docstring, line 670: "The chia-circt image bakes only `circt-opt`; warming the other tool targets here is cheap (shared dialect libs are already built)." So D-08 option (b), "`circt-opt` only under `-UNDEBUG`, other tools from the SDK", is not the baseline and never was; and FR-03.7's demand to bake five targets into the image duplicates a warm-up path §4.2 simultaneously marks "**Reused unchanged**". The genuinely new target is `circt-reduce`.

**W6. FR-12's verify gate runs the whole lit suite; the `-UNDEBUG` baseline for it is unmeasured.**
`chia:examples/circt_issue_solver/issue_task.py:216-227` runs `circt_run_lit` over `circt_lit_gate_paths()` with `_LIT_GATE_FILTER_OUT`; `chia:examples/circt_issue_solver/circt_util.py:151-159` documents the two baseline-red exclusions (`test/CAPI`, `test/Tools/circt-tblgen`) measured **under `-DNDEBUG`**. FR-03.6 (line 466) measures only `test/Dialect/{FIRRTL,HW,Comb,Seq}` plus `test/Conversion` — 523 tests — under `-UNDEBUG`. If restoring assertions reddens any test outside those five directories on a clean tree, every repair records `lit_ok=false` (FR-12.8) and FR-13.6 never returns `report_plus_patch`. No requirement establishes the full-suite baseline under the flag, and the FRD does not mention the exclusion list at all.

**W7. FR-03.5 and FR-03.6 set thresholds at the measurement, rounded down.**
495/513 = 96.49% against a 96% floor; 520/523 = 99.43% against a 99% floor. The FRD justifies the rate form because "the object count changes with the commit" (line 465) — which is exactly why ~2 objects of margin is not a criterion. The 18 objects that carry no `__assert_fail` are never explained, so a drift to 20 is indistinguishable from a broken build.

**W8. FR-03.6's second clause is a judgement in a document that forbids judgements.**
"…and **every failure is attributable to a cause other than the flag**" (line 467). §5's preamble, line 335: "Where a criterion names a number, the number is measured, not judged." A tester cannot execute "attributable".

**W9. NFR-07 contradicts D-02's recommendation.**
NFR-07 (lines 1327-1328): "two distinct credentials exist; the read token fails a write attempt." D-02's recommendation is (c), which per line 1427 "needs **no** write-scoped credential (NFR-07)". Under the recommended option there is one credential and NFR-07's AC cannot be run. One of the two must be withdrawn.

**W10. FR-10.3's issue retrieval is unbounded and unspecified.**
C-04 is right that CHIA has no search call (verified: 0 `/search/` callers under `chia/github/`). What remains is `GithubIssuesNode.recent(n)` listing by recency and `_paginate` at 100 per page (`chia:chia/github/github_client.py:113-128`). Screening a candidate against `llvm/circt`'s **open and closed** issues therefore means paging thousands of issues. FR-10.3 states the requirement and calls the strategy "added work"; no requirement bounds the pool, mandates a cache, or sets a refresh interval. FR-10.7 handles the rate-limit failure but does not prevent it. The existing example's own parameter is `TRIAGE_POOL = 2000` for the *open* backlog alone (`circt_issue_loop.py:50`).

**W11. `circt-reduce` imposes no timeout and no memory limit on the interestingness script.**
`circt:lib/Reduce/Tester.cpp:50-52`, verbatim: `ExecuteAndWait(testScript, testerArgs, /*Env=*/std::nullopt, /*Redirects=*/{}, /*SecondsToWait=*/0, /*MemoryLimit=*/0, &errMsg)`. FR-09.4 (line 766) budgets the *reduction*; nothing requires the interestingness script to bound the tool it invokes, and F-06's per-probe limits (FR-06.2) do not apply because the reducer, not F-06, is the caller. A reduction step that hangs hangs `circt-reduce` until the external budget fires — and FR-09.4 gives no rule for how the external kill is delivered (SIGTERM vs SIGKILL) or how a `--keep-best` output truncated mid-write is validated. Same file, line 46, also fixes the calling convention the LLD must match: the candidate file is appended as the **last** argument after `--test-arg`s.

**W12. NFR-05 conflates container limits with per-probe limits, and container limits break the FR-06.7 `oom` classification.**
`run_options` is a `docker run` pass-through (`chia:docs/user_guides/cluster_config_reference.rst:326-329`) applied to the `sleep infinity` container that hosts the Ray worker. A `--memory` kill takes the worker down, and CHIA then re-queues the task onto another worker (`chia:docs/concepts/overview.rst:104-107`), so an OOM probe is *retried* rather than recorded `oom`. Per-probe `oom` needs rlimits on the child. NFR-05 asks for both without saying which enforces which, and FR-06.2 asks for "a CPU limit expressed as a number of cores" without saying whether that is cgroup shares, `taskset`, or `-j`.

**W13. FR-07.1 does not handle `report_fatal_error`.**
20 occurrences across 10 files under `circt/lib` at `b792c772`. Each prints `LLVM ERROR: …` and aborts, so FR-07.1 fires and FR-07.2 classifies `crash` — for what is frequently a deliberate "unsupported construct" path a maintainer will close as not-a-bug. FR-07.1's assertion patterns cover glibc `assert` and `UNREACHABLE executed`; the third abort path is unaddressed, and it is the one most likely to fire on generated input.

**W14. FR-01.1's "exactly 187" is a moving target with no pin.**
The count depends on the clone's HEAD. `pin_window_raw.json` was computed at `d7e94049` (PIN §1 line 59); the FRD's own source table (line 40) names `b792c772`, one first-parent commit later. Measured growth over the last 60 days of the window: **0.32 filtered candidates per day** — roughly four more by 2026-09-24. FR-01.6 requires the HEAD be *recorded*; FR-01.1's AC requires the *count* be 187 from "a blobless clone". The first run after a `git fetch` fails acceptance.

**W15. FINAL §2's "reusing `circt/arc-tests`'s lockstep driver" is quietly weakened to a citation.**
F-08's reuse column reads "The lockstep idea and the divergence differ from `circt/arc-tests`, **cited**"; FR-08.7 requires only that the rendered report *name* it. Nothing in F-08 reuses the driver, and A-08 already records that both harness generators are unwritten. FINAL's sentence promises reuse; the FRD delivers a footnote. The scope auditor's brief was that nothing FINAL §2 calls for may be weakened.

**W16. FINAL §4's "GPU-hours" is silently replaced.**
FR-14.1 asks for "the compute allowance"; D-04 selects inputs and wall-clock. Neither records that FINAL §4 names GPU-hours explicitly, nor the more interesting fact that the loop uses no GPU at all (CIRCT builds are CPU; every backend is an agent CLI calling a hosted API). The right move is to flag FINAL's wording as an error; the FRD instead substitutes without comment, which leaves the paper and the budget file free to disagree.

**W17. NFR-10 is scope the FRD adds.**
Neither FINAL nor PAPER mentions a cloud deployment. NFR-10 requires the loop run "on a single machine **and on a GCP cluster**, from the same loop code with a different cluster YAML", which is a second cluster configuration and a second system-test configuration eleven days from C-10's deadline. §10.1 item 4 then makes `02-HLD.md` specify the topology for both. The user's ruling was no scope *cuts*; this is a scope *addition* that competes with the Musts for the same eleven days.

**W18. FR-12.2's local identifier is constrained to an integer by code the FRD forbids changing, and the FRD does not say so; D-11 then overstates what FR-12.1 requires.**
The chain: `run_issue_remote(issue_md: str, number: int, …)` (`chia:examples/circt_issue_solver/issue_task.py:39`); `art = ARTIFACT_DIR / f"issue_{issue.number}"` (`circt_issue_loop.py:121`); `issue_number INTEGER NOT NULL` (`db.py:24`); `db.record(issue, …)` reads `issue.number`, `issue.title`, `issue.url` (`db.py:99-110`); `attempted_numbers()` returns `set[int]` (`db.py:93-96`); and `GithubIssue` is a dataclass with eleven required fields (`chia:chia/github/state_def.py:11-24`), so the adapter must construct a full issue-shaped object, not just a string and an int. FR-12.1's byte-comparison AC covers `issue_task.py` only. D-11's recommendation then claims (b) is "the only option that lets FR-12.1's byte-comparison acceptance criterion hold" for "CHIA's example" as a whole (line 1560) — which FR-12.1 does not say — while §4.1's Persistence row simultaneously plans "same shape, **new keys and new columns**" for that same example. Extend it or byte-compare it; not both.

**W19. `invalid_input` names three different things.**
A `BuildResult` status (FR-06.6, line 626), a triage classification (FR-11.1, line 858), and a failure-taxonomy bucket (FR-18.6, line 1200). FR-04.9 adds a fourth sense ("counted as an invalid input at stage 3"). The glossary (§2) defines none of them. §2's own preamble: "Every term below is used verbatim, in this sense, throughout the set."

**W20. FR-03.9 requires `openssh-client` and `rsync`; the Dockerfile it extends installs neither.**
`chia:dockerfiles/ChiaCirctBaseDockerfile:45-52` installs `ca-certificates wget curl git unzip xz-utils clang lld cmake ninja-build ccache zlib1g libxml2 libtinfo6 libz3-4 openjdk-17-jdk-headless device-tree-compiler` — no `openssh-client`, no `rsync`. `ChiaCirctDockerfile` adds only the chia pip install. (`grep -rn "openssh\|rsync" dockerfiles/*Dockerfile` finds them in `VerilatorRunDockerfile`, `EspDockerfile`, `ClaudeCodeDockerfile`, `ChipyardDockerfile`, `OpenCodeDockerfile` — not the CIRCT pair.) Either C-07's list is wrong or CHIA's own CIRCT image is non-conformant; FR-03.9's actual AC (`chia up` reaches Ready) passes today without them, so the two halves of FR-03.9 disagree.

**W21. D-02(c)'s pre-filled issue URL has an unstated size ceiling and no fallback rule.**
`llvm/circt` has no `.github/ISSUE_TEMPLATE/` directory (verified), so `?title=&body=` prefill is possible — good. But an FR-11.3-compliant body carries the reduced case verbatim, the reproducing command, the assertion text, the build identity and the dedup evidence, which will routinely exceed practical URL length. D-02 says "falling back to (a)" but sets no threshold and no detection, and FR-13.7's `FilingRecord` completion ("the human pasting the resulting issue URL back") is a manual step with no requirement anywhere in F-13.

**W22. F-05 never says which test file.**
FR-05.1 (line 567): "the seed's **changed test file**" — singular. FR-01.1 records "the changed paths under `test/` or `integration_test/`" — plural, and `pin_window_raw.json`'s `test` field is a list; the FRD's own worked example seed has two. FR-05.1's AC ("the arm's input record contains only the test file and the `RUN:` line") is not executable until someone picks a rule, and the rule determines what the baseline arm actually mutates.

**W23. A-17 is stale.**
`analysis/pin-window-analysis.md:90` now reads "**3,257** (sum of per-window `n` in `pin_window_raw.json`; an earlier line here read 3,251, **corrected 2026-09-13**)". A-17 (line 1389) still records the 3,251/3,257 discrepancy as "unresolved" and marks it `[UNVERIFIED]`. The FRD is dated the same day as the correction.

---

## 3. NITs

**N1.** G-04 (line 66) lists six firtool output modes. `circt:tools/firtool/firtool.cpp:185-202` defines nine: the six plus `--ir-verilog`, `--btor2`, `--disable-output`. The cite (`179-202`) starts inside the preceding enum, not at the option. Matters slightly because FR-08.1 decides differential applicability from "the requested output mode".

**N2.** NFR-05 (line 1324) says today's CIRCT worker "sets only `--ulimit nofile` and `--shm-size`". `chia:examples/circt_issue_solver/cluster.yaml:55-59` also passes `-v $SSH_AUTH_SOCK:/ssh-agent` and `-e SSH_AUTH_SOCK=/ssh-agent`.

**N3.** C-08's added evidence (line 1357), "confirmed on the SDK binary, which prints the same", is a non-sequitur. The SDK binary is an assertions-off release build; its version string says nothing about what `-UNDEBUG` does. (Executed: `circt-opt --version` → `LLVM version 24.0.0git / Optimized build. / CIRCT firtool-1.157.0`.) FINAL Appendix A's evidence — the completed `-UNDEBUG` build — is the only evidence for C-08.

**N4.** §4.2's Node-dispatch row cites `chia:chia/base/ChiaFunction.py:482-494` for `.options(resources=...)`. Those lines are `ChiaCallRemote`.

**N5.** §4.3 cites `VerilatorRunDockerfile:6-8`; the sentence is at lines 7-8.

**N6.** FR-19.1's AC (line 1242), "a search of the added code finds … no synchronous MCP tool **that can run for more than 120 seconds**", is not statically decidable. `BashTool`'s own default timeout is exactly 120 s (`chia:chia/base/tools/BashTool.py:23`) and `AsyncJobTool._MAX_POLL_SECONDS = 120`, so the boundary case is the framework's own default.

**N7.** F-20 omits **Inputs** and **Outputs**, which §5's per-feature template (line 338) requires of every feature. Checked mechanically: F-20 is the only one.

**N8.** FR-03.8 bakes `lit` into the image. `chia:examples/circt_issue_solver/cluster.yaml:65` already pip-installs it in `run_setup_commands`, and `circt_warm_build` installs it again if missing. Three installers for one binary.

**N9.** The FRD's own "Number discipline" rule (line 47) — "Every number in this document comes from FINAL Appendix A or PIN. Anything else is marked `[UNVERIFIED]`" — is broken by its own thresholds and sample sizes: 96% (FR-03.5), 99% (FR-03.6), "at least 5" (F-07 acceptance), "at least 3" (F-09), "at least 20" (F-10), "5 seeds … at least 3 distinct entry tools" (F-04), "a batch of 20 probes" (F-06), "60-second budget" (FR-09.4), "10 MB" (FR-17.7). None is in FINAL Appendix A or PIN; none is marked.

**N10.** PAPER §2's gate list — "does it build, does it fail, is it minimal, is it new" (main.tex line 149) — is a different four-question set from G-29 / FR-13.1's "reproduce at the run's commit, minimal, valid input, new". §9.3 maps "the gates" to F-13 and F-16 without noting the divergence, and `00-README.md` line 48 forbids renaming what comes from the paper.

**N11.** §4.3 says CHIA offers "exactly two paths, `--issue <N>` or `triage.select`", citing `circt_issue_loop.py:240-245`. Lines 209-221 add `--assess-only` and lines 228-239 add `--replay-regression`, which restores a saved `fix.diff` plus `repro_files` and jumps to a later phase. `--replay-regression` is structurally closer to F-12's local-report entry than either path the FRD cites, and F-12 does not mention it.

---

## 4. Open decisions D-01 … D-12

| ID | Verdict | Why |
|---|---|---|
| D-01 | **Right choice, unpriced** | (c) is correct — FINAL §3 does ask for both. But the recommendation carries no cost line and the cost is the biggest in the document: see W4 (38 images, ~150-190 GB, ≥10 h of build before the campaign). Missing option: **(d) calibration mode restricted to a named sample of k seeds, k fixed in `budget.yaml`.** FR-18.5 needs calibration to *exist*, not to cover all 171. Adding (d) turns the largest unpriced item into a parameter. Also missing: nothing says what "the run's commit" means in calibration mode, which FR-12.6, FR-13.2 and FR-10.4 all read. |
| D-02 | **Right, with an unstated ceiling** | (c) is the correct posture and CIRCT has no issue forms to break it (verified: no `.github/ISSUE_TEMPLATE/`). Two defects: the URL size ceiling and fallback rule are unspecified (W21), and the recommendation contradicts NFR-07 outright (W9). Missing option: **(d) the human files, and the tool reconciles the `FilingRecord` afterwards by polling the read-only `GithubIssuesNode` for a new issue matching the report's fingerprint** — this recovers the automatic `FilingRecord` link that (a) and (c) both lose, using only the GET client CHIA already has. Given FR-18.3's headline is populated from `FilingRecord`s, losing the link is not cosmetic. |
| D-03 | **Wrong on both of its own grounds** | See §5 below. Recommending `--backend claude` / `claude-opus-4-6` spends a credential the hackathon does not fund and picks the one backend that reports no per-phase usage — the FRD says so itself at line 1450 and then recommends it anyway. |
| D-04 | **Wrong; the FRD names the bias then adopts it** | K6. Also internally inconsistent with FR-14.5 (one unit vs two). Missing option: **(f) equal tool-invocation count** — the number of times a CIRCT binary is executed under the oracle. It is arm-symmetric like (a), backend-independent like (a), and unlike (a) it is not the unit that deletes the baseline's throughput advantage, because one agent-written probe and one mutant each cost one invocation while the agent additionally pays compute the ledger would then still record as a secondary. If the intent really is "equal compute" as FINAL §4 says, (b) with wall-clock normalised per-arm is the honest choice and the noise objection is answerable by running both arms on the same worker type. |
| D-05 | **Right method, wrong source, and the isolation is broken at synthesis** | (b) is right: Mut4All is the design PAPER §4 already commits to, and (a) would make the head-to-head worthless. But the recommended source — "CIRCT's own closed `label:bug` issues (65 closed in the last year)" — is **65 reports against Mut4All's 1,000** (FINAL Appendix A). D-05's own argument against (a) ("a weak baseline makes the head-to-head worthless") applies to a 65-report synthesis. Worse, and unremarked: FR-05.1 forbids the mutation arm from seeing "the seed's diff, its commit message, or the root-cause class" **at run time**, while D-05 feeds a model 65 bug reports at synthesis time. The arms' information isolation is an argument about what each arm knows, and the FRD breaks it in the decision that defines the baseline, then never mentions it. Missing option: **(d) Mut4All's method over the full 24-month fix-commit set (1,103 unfiltered candidates, PIN §4) rather than over closed issues** — same corpus both arms already share, an order of magnitude more material, and no new contamination surface. |
| D-06 | **Right; adopt as written** | The four definitions are clean and the discipline of using exactly four words is worth the ADR. One gap: it defines candidate, report, filing and confirmed but not **distinct**, which is the word the headline actually turns on and which K5 shows is undefined. Add it here, because defining it in FR-18.3 alone did not work. |
| D-07 | **Right** | (c) follows from D-01(c). Note the interaction the FRD misses: under D-01(c) + D-07(c) every results table needs *two* qualifiers (mode and seed set), and FR-18.2's AC ("the two arms' seed SHA sets are identical") is then per-mode, which it does not say. |
| D-08 | **Right recommendation, wrong premise** | (c) "measure first, cut only on evidence" is right and rightly sequenced first in §10.4 item 6. The premise is wrong (W5): CHIA already builds four of the five targets at warm-up, so the marginal question is `circt-reduce` plus the `-UNDEBUG` multiplier, not the target set. C-16's `circt-verilog` gap is correctly identified and correctly deferred to the LLD, and it is the item that most deserves promotion out of D-08 into its own decision, because 46 of 187 seeds (ImportVerilog 31 + MooreToCore 12 + Moore 3) depend on a binary that is at the SDK's commit, not the run's — which means FR-13.1 question 1 ("does it reproduce at the run's commit") cannot be answered for them at all. |
| D-09 | **Right, with a missing consequence** | (a) with escalation to (b) is proportionate. The missing consequence: the version gate is stated as "if the packaged version lacks `--x-initial` or `--x-assign`", but the real risk is not flag presence, it is behavioural difference in X propagation between the packaged version and the 5.052 the probe used — which is the axis the whole differential rides on (FR-08.4, FR-08.9). "Record the version in every differential verdict" is right and insufficient; there is no requirement that the campaign use one Verilator version throughout, so a mid-campaign image rebuild could silently change the oracle. |
| D-10 | **Right** | (c) is correct and the mechanism already exists. One consequence unstated: option (c) plus FR-10.4 plus FR-13.5 means a long lag mechanically reduces the filing rate, so the headline metric is a function of when the campaign happens to run. FR-18.8 already commits to a cut-off date for confirmations; the same disclosure is owed for the lag. |
| D-11 | **Right choice, wrong justification** | (b) is right. The justification — "the only option that lets FR-12.1's byte-comparison acceptance criterion hold" — misstates FR-12.1, which byte-compares `issue_task.py` alone, and contradicts §4.1's plan to add columns to `db.py` (W18). Missing consequence: with two SQLite files on one machine under C-14, and `SQLiteNode` opening a fresh connection per `chia_remote` call (`chia:chia/database/sqlite_node.py:21-27`), a candidate row and an attempt row cannot be written in one transaction, so the join key can dangle if a stage dies between them — which FR-17.8's `PARTIAL` marker does not cover because it is about directories, not rows. |
| D-12 | **Right** | (a) now, (b) if time allows, is proportionate for a few dozen approvals. FR-13.12's "in one view" is satisfiable by a CLI. Unstated: the approval must be recorded somewhere the gate reads back, and FR-13.7's `FilingRecord` (approver name + timestamp) plus D-02(c)'s manual URL paste means the CLI is also the place a human types a URL. That is two interactions, not one, and §10.2 does not list the approval CLI among the things the LLD must specify. |

---

## 5. D-03 in detail, weighing the credits and the usage reporting

The FRD recommends (line 1448): "**(c) with the default equal to CHIA's own issue-solver default, `--backend claude` with `claude-opus-4-6`.**"

Two facts decide this.

**Fact 1 — only `antigravity` and `opencode` report per-phase usage.** `chia:examples/circt_issue_solver/circt_issue_loop.py:132-134`, verbatim:

```python
# Per-phase token/cost usage for backends that report it (antigravity, opencode).
usage = {phase: blob["usage"] for phase, blob in (res.get("logs") or {}).items()
         if blob.get("usage")}
```

The FRD states this at line 1450 and in FR-14.6 (line 1027), then recommends the backend it excludes.

**Fact 2 — the hackathon's credits pay for Gemini through those two backends.** `chia:examples/circt_issue_solver/README.md:63-84` documents both paths: `--backend antigravity` (Google's `agy` CLI, `gemini-3.1-pro-high`, `cluster_antigravity.yaml`) and `--backend opencode` (OpenCode CLI on Vertex, `google-vertex/gemini-3.1-pro-preview`, `cluster_opencode_vertex.yaml`).

Under the recommendation the campaign runs on a credential the event does not fund **and** produces no token figure, which is precisely why D-04 then has to reject option (c) tokens as "unavailable on the Claude backend". The FRD manufactures D-04's constraint in D-03 and then treats it as given.

The stated reason for `claude` — "Matching CHIA's default means the repair chain runs exactly as CHIA measured it, so F-12's results are comparable with CHIA's own" — buys a comparison that FINAL and PAPER never make, that §1.2 puts explicitly out of scope ("a repair benchmark or leaderboard"), and that is worthless anyway because F-12 runs on generated crashes, not on the 16 GitHub issues CHIA measured.

**Correct recommendation: (c) per-stage configurable, defaulting to `--backend opencode` with `google-vertex/gemini-3.1-pro-preview`**, or `antigravity` with `gemini-3.1-pro-high` if ADC setup proves slower than `agy` sign-in. That is funded, and it restores the per-phase token ledger FR-14.6 asks for, which in turn makes D-04's option (c) live again and gives the paper a compute number that is not wall-clock.

**Missing option and missing consequence, both material:**

- **Missing option (d): one backend, one model, chosen for cost reporting, with the Claude path kept only as a fallback for a backend outage.** The FRD's option (a) is "one backend and model for all three agent stages" and its consequence is "Confounds nothing, because both arms share it" — which is true and is the strongest argument in the decision, yet (c) is recommended instead for a knob D-03 itself says "nobody has to use". Simplicity has a real value eleven days out.
- **Missing consequence: a backend is a cluster, not a flag.** `README.md:63-88` and `circt_issue_loop.py:176-180` make each backend require its own cluster YAML — `cluster.yaml`, `cluster_antigravity.yaml`, `cluster_opencode_vertex.yaml` — because the LLM containers differ (`chia-claude-code`, `chia-antigravity`, `chia-opencode`) and different host directories are mounted (`~/.claude`, `~/.gemini`, `~/.config/gcloud`). D-03's option (c), "per-stage configurable", therefore cannot be one config knob across backends: it needs two LLM worker types in one YAML with two distinct resource names, since `resources: {"llm": 2}` is shared today (`cluster.yaml:24`). That is real work, and D-03 prices it at zero.

---

## 6. The single question the FRD most needs answered before HLD

> **For each of the five entry tools FR-01.3 admits, which binary executes the probe, whether `circt-reduce` can read that probe's input language, and what the gate answers for a candidate that cannot be reduced.**

One question because the answer moves everything downstream at once:

- It resolves **K1** (the `.sv` and `.fir` reduction hole) and therefore whether the gate can pass anything outside the MLIR region.
- It resolves **C-16** (`circt-verilog` has no ninja target in an SDK-based build), and therefore whether FR-13.1 question 1 — "does it reproduce at the run's commit" — is even answerable for the 46 seeds in the `.sv` region.
- It fixes the effective corpus size, which is D-07's real subject and which decides whether the head-to-head has 187 seeds, 171, or the ~60 on the FIRRTL→HW→SV path.
- It fixes the `ReducedCase` schema, which is half the `CandidateRecord` seam contract that `00-README.md` says must be frozen before either engineer starts.

Until it is answered, `02-HLD.md` cannot draw the seam and `05-Work-Plan.md` cannot split the work.

---

## 7. The ten riskiest assumptions, and the cheapest experiment that settles each

Ordered by expected damage. "Cost" is engineer-hours against the 2026-09-24 deadline.

| # | Assumption | Where | Cheapest experiment that settles it | Cost |
|---|---|---|---|---|
| 1 | Every firing input can be reduced | F-09, FR-13.3, PAPER §2 stage 5 | Take the 187 seeds' extracted `RUN:` lines (F-01 already produces them), classify each entry tool, and run `circt-reduce --test=/bin/true <one input of that language>` once per language. Already done for `.fir` and `.sv` in this review: both fail. Remaining work is only to count the affected seeds. | **<1 h** |
| 2 | Symbolised frames name CIRCT source paths | FR-07.4, FR-10.1(b) | `readelf -S` the existing `-UNDEBUG` build for `.debug_info` — done here, zero sections. Then rebuild `circt-opt` alone with `-O3 -UNDEBUG -gline-tables-only` and record the wall-time delta and the binary-size delta. That single number also retires part of A-03. | **1 build (~16 min at `-j6`) + 15 min** |
| 3 | `-UNDEBUG` leaves the full lit suite green on a clean tree | FR-12.8, FR-13.6, A-04 | Run `lit` over the whole `test/` tree with CHIA's own exclusions (`--filter-out=circt-tblgen`, drop `test/CAPI`) against the `-UNDEBUG` build already sitting at `~/.cache/chia-pin-smoke/bassert`. One command. Doubles as FR-07.9's control run and the assertion false-positive rate. | **~1 h, no build** |
| 4 | The image cost is acceptable (A-03) | FR-03.7, D-08, D-01 | Build `circt-opt firtool circt-translate arcilator circt-reduce` once under `-UNDEBUG` at `5056ff04450b` against the `firtool-1.157.0` SDK already extracted. Record wall time, `du -sh build`, and the `docker save` size. Multiply by 38 to price D-01(c). | **1 build (2-4 h wall, unattended)** |
| 5 | The dedup rule produces stable distinct-bug classes | FR-10.2, FR-18.3 (K5) | No experiment needed first: pick the closure rule (union-find or pairwise) and the frame count `N` on paper, write both into `budget.yaml`, and only then measure collision and false-merge rates on the labelled pairs. Measuring an undefined metric is the error. | **2 h of decision, 0 h of compute** |
| 6 | The contamination screen discriminates | FR-15.1, A-12 | Already measured here: 86.1% of `lib/`+`include/` source files were touched in 24 months, 95% inside FIRRTL. Re-run the same one-liner with the intended lower bounds to get the per-seed flag rate, then decide whether to narrow the rule to *symbol*-level rather than *file*-level matching. | **<1 h** |
| 7 | An agent turns a CIRCT fix diff into a firing probe (A-01) | F-04, the whole thesis | Five seeds, one agent turn each, against the `-UNDEBUG` `circt-opt` already built. Count probes that fire the primary oracle. Zero out of five is itself the most valuable number in the project and it arrives before any infrastructure exists. | **3-4 h** |
| 8 | The repair chain works on a generated crash, not just a mined issue (A-15) | F-12, K4 | Hand-write one crash input, hand-write the `repro.sh` FR-12.3 would generate, and run CHIA's unmodified chain with `--issue`-shaped input against it. Watch specifically whether a "reject the input properly" fix scores `fixed` or `attempted`. | **2-3 h** |
| 9 | Both differential harness generators are feasible from a port list (A-08) | F-08, FR-08.2 | Regenerate the recorded 12-line FIRRTL probe's two harnesses from its port list alone, with no hand editing, using `analysis/probe/tiny_arc.mlir` and `tb.sv` as the targets to reproduce. If that cannot be automated in a day, F-08 is a paper section, not a feature. | **1 day, timeboxed** |
| 10 | The assertion finding holds in CHIA's published image (A-10) | C-13, F-03's premise | `docker pull ghcr.io/ucb-bar/chia-circt:latest` and `nm -u /workspace/circt/build/bin/circt-opt \| grep -c assert_fail`. One command against the real artefact, replacing the local reproduction of CHIA's flags. | **20 min** |

Items 1, 2, 3, 6 and 10 together cost under a day and retire two KILLs and three assumptions. They should precede `02-HLD.md`, not follow it — which contradicts `00-README.md`'s no-code rule only on its own terms, since all five fall under its stated exception for "throwaway measurement scripts whose output feeds an `A-nn` or a `D-nn`".

---

## 8. Counts

| Class | Count |
|---|---|
| **KILL** | **13** |
| **WOUND** | **23** |
| **NIT** | **11** |
| Total | 47 |

KILLs by feature: F-01 (2), F-03/F-07 (1 shared), F-09/F-13 (2), F-10/F-18 (2), F-11/F-13 (1), F-12 (1), F-13 (1), F-14/F-18 (1), F-16/00-README (1), NFR-01 (1), F-08/F-13 (1).

Three KILLs are settleable in under an hour each with artefacts already on this disk (K1, K2, K10). Four are design contradictions internal to the document and cost only a decision (K5, K7, K8, K13). Three are genuine framework or tool constraints that change the architecture (K3, K4, K12). Two change the experiment's meaning (K6, K11). One is a missing specification (K9).
