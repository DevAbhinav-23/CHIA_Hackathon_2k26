# The CIRCT bug loop, explained

For a judge who has never used CIRCT or CHIA. Every number here carries the file it was read from.

## The problem

CIRCT is the LLVM project's open-source hardware compiler: it turns FIRRTL (what the Chisel hardware language emits) and SystemVerilog into the Verilog that synthesis and layout tools accept. A crash in it is an inconvenience, because the designer sees it and works around it. Wrong Verilog is not: the output looks well formed, passes the tools below it, and can reach fabrication before anyone notices.

CHIA is the agent framework this hackathon is built on. Its CIRCT issue solver picks an open GitHub issue and chains six phases, from assessing it to writing the pull request.

The queue is the constraint, and it is not a shortage of reported bugs. Over the past year CIRCT received 82 bug-labelled issues and closed 65; the backlog that does not drain is 101 open ones at a median age of 911 days.
<!-- 82 received, 65 closed, 101 open, median age 911 d: analysis/measurements/2026-09-13-frd-followups.md M1 -->
What is scarce is maintainer attention, so an agent that empties the queue faster creates none of it. What would help is a bug that arrives already minimised, already screened against what is known, carrying a candidate fix, from a source that files nothing else. Past fixes are the unspent information: a commit that corrects one wrong assumption inside a compiler pass usually leaves the same assumption standing at other sites, and CIRCT ships no fuzzing infrastructure to find them.

## The seven stages

1. **Seed.** Mine bug-fix-shaped commits from CIRCT's last two years and keep each one's diff and regression test: 187 of them, 171 rebuildable against a prebuilt LLVM package CIRCT itself publishes. <!-- analysis/pin-window-analysis.md, headline table and line 14 -->
2. **Generate.** Read one seed, state the class of mistake its fix corrected, name sibling sites where the same assumption still stands, and write fresh inputs in the seed's own language.
3. **Build and probe.** Run each input on the tool the seed's own test names, inside the assertions-on image, under fixed wall-clock and memory limits.
4. **Judge.** The primary oracle admits no argument: the compiler crashed, an assertion fired, or the compiler's own verifier refused output the compiler had just produced. A second oracle runs the design through CIRCT's simulator and through Verilator and flags disagreement; it reports only.
5. **Reduce.** `circt-reduce` deletes parts of a firing input and keeps each deletion while the failure survives; a textual reducer takes over where that tool dies.
6. **Triage and report.** Fingerprint the failure, screen it against a local mirror of the tracker and against commits made since the build point, and write the report a maintainer would read.
7. **Repair.** CHIA's phase chain runs unaltered, entered by a local report instead of a GitHub issue, restricted to crashes and assertion failures where nobody has to argue about the right answer.

The model runs three of those: stage 1, stage 2 and the report in stage 6. Everything that decides anything, including all four gate questions, is a fixed tool. Between the stages sit yes-or-no questions; the last gate asks whether the failure reproduces in a fresh process on another worker, whether the case is minimal, whether the input is valid, and whether it is new. Then the gate is a person, who approves each filing by name at a command line, under a cap on filings per day.

## What was measured before any model call

The loop's oracle rests on the compiler being able to complain, and it could not. Optimised builds delete assertions by defining `NDEBUG`, and CHIA's published CIRCT image is such a build: 606 of its 606 compile commands carry `-DNDEBUG` and its `circt-opt` holds no reference to the assertion handler at all.
<!-- 606 of 606 -DNDEBUG, 0 undefined __assert_fail: analysis/measurements/2026-09-13-frd-followups.md A-10 -->
An oracle waiting for an assertion under that image would have found nothing, whatever the agent wrote, and the loop would have reported a clean result that meant nothing.

We rebuilt it with one flag inverted. In the image the loop runs, 778 of 778 compile commands carry `-UNDEBUG` and the handler is back in 536 of the 555 compiler objects; the other 19 assert nothing.
<!-- 778 of 778 and 536 of 555: analysis/measurements/2026-09-14-image-build.md 4, FR-03.4 and FR-03.5 -->
Restored checks are only useful if they do not fire on correct code, so the image was built twice, differing in that flag alone, and CHIA's whole test gate was run in both: the same 1,119 tests pass and none fails, either way.
<!-- 1,119 passed / 0 failed of 1,127 considered, identical in both images: analysis/measurements/2026-09-14-image-build.md 5 run 2 and W-04b 3 -->
No test passes with the checks compiled out and fails with them in, so a probe that trips an assertion trips it because of what the probe does. The flag costs 18 % of build wall clock.
<!-- +179 s = 18.4 %: analysis/measurements/2026-09-14-image-build.md W-04b 1 -->

## Eight pilots, eight defects

Every pilot was a capped live run whose job was to retire one defect by measuring it. None of them counts as a result.

| Pilot | What it measured, and the defect it retired |
|---|---|
| 1 | Three probes on the first seed, all three firing the Moore assertion and all three withheld as duplicates of open issue 8508. It spent USD 7.16 against a registered 5.00, 43.3 % over, because the spend guard authorised one model call while a tool-bearing turn made 14, 21 and 37. <!-- analysis/measurements/2026-09-16-pilot.md 4 and 5 --> |
| 2 | With a per-turn money ceiling in place the billed-over-authorised ratio fell to 0.50 and 0.59, but a tool-call cap of 6 exhausted both stage-1 turns, which then returned empty text and no answer, so zero probes were written. <!-- same file, P2.2 and P2.4 --> |
| 3 | The forced final answer fired after 12 calls and still returned empty text; USD 0.64, stage 2 never ran. <!-- analysis/measurements/2026-09-14-pilot-3.md --> |
| 4 | Stage 1 answered through the forced final answer, so that fix works live; stage 2 then raised after 12.4 s and the exception type was lost, because failed turns were not recorded anywhere. <!-- analysis/measurements/2026-09-14-pilot-4.md --> |
| 5 | Stage 2 spent all 12 of its calls reading compiler source, never called the tool that writes a probe, and its final answer came back as a function call despite the mode that forbids one. <!-- analysis/measurements/2026-09-14-pilot-5.md --> |
| 6 | Stage 2 was refused before dispatch: stage 1's authorisation was still held although stage 1 had billed a fifth of it, so the two together exceeded the cap. <!-- analysis/measurements/2026-09-15-pilot-6.md --> |
| 7 | USD 0.00. The run's first call met an HTTP 429 from the backend's express-mode quota, which CHIA never retries, and the arm stopped there. <!-- analysis/measurements/2026-09-15-pilot-7.md --> |
| 8 | Every stage of the seeded arm ran, for the first time, for USD 1.21; the ledger agreed with the backend's own token counts to the rounding. One reporting defect was left: three turns that were never dispatched were counted as turns whose price was unknown. <!-- analysis/measurements/2026-09-15-pilot-8.md 2, 4 and 6 --> |

## The campaign

Campaign 2 was pre-registered as an annotated tag, two hours per arm, the seeded arm split into two shards run in parallel, USD 100 cap per job. It was started three times.

**Stopped twice, both times on a defect the live run exposed.** Attempt 1 was stopped at 32 minutes: the feedback line returned to the model kept the artefact path and truncated before the compiler's actual message, so iterations 2 and 3 repeated the same error and bought nothing. Attempt 2 was stopped at 45 minutes on a scheduling deadlock: each shard's generator held one of the two CIRCT worker slots for a whole seed iteration, and the gate's re-run waited on a busy node instead of falling back, so no iteration could ever end. Attempt 3 ran both shards to their windows.
<!-- docs/HANDOFF.md 2026-09-15 06:05, 07:05 and 09:35 entries -->

**Three distinct new bugs through the gate**, all from one seed, the August fix for out-of-bounds `moore.extract` lowering, and all in the same `--convert-moore-to-core` pass:

* an extract at the most negative 32-bit offset overflows the slice bounds, so the lowering builds an array concatenation with no operands and trips `!values.empty() && "Cannot build array of zero elements"` at `HWOps.cpp:1995`;
* lowering a dynamic extract emits `comb.extract` with an aggregate result type, which MLIR's verifier refuses;
* lowering an extract of a reference emits `llhd.sig.extract` with an aggregate reference type, likewise refused.

Each reproduced in a fresh process on another worker, was minimal at the reducer's fixpoint at no more than five lines, was a valid input, and matched neither an issue in the 2,652-issue mirror nor a commit made since the pin. The model wrote the three reports; they are held for a named human.
<!-- candidates c-p-a2cb61b8d0aa, c-p-075cf1d70f3a, c-p-356e9e6e061d, seed cc71d34a: docs/HANDOFF.md 2026-09-15 08:00, 11:40 and 12:10 entries -->

**The campaign forced a new verdict class.** Ten probes of that seed were booked as the loop's own fault, an input the tool rejected, when the messages named ops that do not appear in the input at all: the pass had created them with aggregate types and MLIR's generated verifier refused the compiler's own output. The oracle now separates that case, and needs both conditions, since a pass may legitimately complain about a valid input. Re-judging every stored probe moved 10 of 53 in that run and 0 of the mutation arm's 400, so the rest really were bad inputs.
<!-- D-13 and the reclassification: docs/HANDOFF.md 2026-09-15 07:55 and 09:50 entries; design/01-FRD.md FR-06.9 erratum -->

**Four deduplication rules were corrected, each on a real candidate.** A commit after the pin counted as a fix if it touched the crash's file, so an LLVM version bump touching 87 files silenced the first find; it must now touch a frame symbol. A generic MLIR assertion text matched an open issue on the text alone; it now also needs a CIRCT frame token in the issue. A verifier failure matched an issue on the op name alone; it now needs the constraint as well. And two candidates sharing a fingerprint were each the other's duplicate, so thirteen candidates had no representative; the duplicate is now of the earliest. Because every verdict is recomputed from stored evidence, correcting a rule re-judges every stored candidate and costs no model turn.
<!-- D-11, D-16, D-17, D-18: docs/HANDOFF.md 2026-09-15 06:45, 08:35, 09:50 and 11:40 entries -->

**The mutation baseline.** The control arm shares the harness, the oracles, the reducer and the gate, and differs only in its generator: it rewrites the same seed tests syntactically, without seeing the diff or the root-cause class. Of 187 seeds, 87 were skipped because their own test no longer parses at the build commit; the remaining 96 produced 1,154 mutants, of which 400 were rejected by the parser and 754 ran. It fired nothing, produced no candidate, cost USD 0 and finished in 13 minutes.
<!-- run 460b7b48: docs/HANDOFF.md 2026-09-15 06:50 and 12:10 entries -->

## Money

The campaign's seeded arm cost USD 44.49 at list price, the eight pilots USD 13 between them, and every live model call of the project USD 66.
<!-- docs/HANDOFF.md 2026-09-15 12:10 entry; paper/main.tex V and VII -->

Three things qualify that figure. **List is not billed:** the ledger prices every input token at the registered list rate, because the budget file registers exactly two rates and a third added after the registration commit would no longer be the file the campaign was registered against. At pilot 8 the operator read about USD 5 on Google's billing page against a ledger of 13.6. **The cause is caching:** 37.7 million of the campaign's 55.6 million input tokens, 68 %, were served from the backend's context cache, which Google prices lower, so the ledger is an upper bound and the count is recorded so the size of the overstatement can be computed rather than guessed. **The guard errs in the safe direction:** over 55 turns the campaign billed on average 0.18 of what was authorised before the first call and never more than 0.41, and no turn billed more than its authorisation.
<!-- ledger 13.6 vs billing page ~5: docs/HANDOFF.md 2026-09-15 03:05 entry; 37.7 M of 55.6 M cached and the 0.18 mean: 12:10 entry and ~/bugloop-artefacts/f1e4fef5.../results/results.md 7 -->

## What is not done

**Nothing is filed.** All three reports sit behind the approval command, which refuses until the method has been posted to CIRCT's forum and a named person approves each candidate. The forum post is drafted and unposted.
<!-- docs/forum-post.md; FR-20.1 in circt_bug_loop/approve.py -->

**Repair was attempted once and produced no patch.** On the assertion candidate, CHIA's chain diagnosed the cause precisely, a 32-bit overflow in the slice bounds leaving an empty operand list, and judged the issue clear; its reproduce phase then wrote its own variant instead of confirming the script the loop had pre-written, scored no reproduction, and the fix, regression and writeup phases never ran.
<!-- analysis/measurements/2026-09-15-repair-run.md, attempt 2 -->

**One gate call is still unbounded.** The gate's re-run of a candidate now waits a bounded time and falls back to any worker, but `gate_validate` has no such bound and can still wait on a busy cluster.
<!-- docs/HANDOFF.md 2026-09-15 07:25 entry -->
