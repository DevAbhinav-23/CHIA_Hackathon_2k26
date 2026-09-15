# Results: the closed CIRCT bug loop

Run `7c1f4a9d6e2b48c0a53f81d27e6b09c4`. Mode discovery, seed set 187. Arms run sequentially, seeded then mutation, each for 14400 wall-clock seconds.

Every table below carries the mode and the seed set it was taken under, and every number in it comes from a tool-produced record in `loop.db`.

## 1. Headline

**Distinct confirmed bugs per arm** (mode discovery, seed set 187)

| arm | distinct confirmed bugs | confirmed filings | filings | distinct excluding contaminated |
|---|---|---|---|---|
| seeded | 1 | 1 | 2 | 0 |
| mutation | 0 | 0 | 0 | 0 |

A confirmed bug is one a maintainer acted on, evidenced by a URL; distinct is one per primary fingerprint, so two filings sharing a fingerprint count once. The seeded arm confirmed 1 distinct bug. The mutation arm confirmed 0 distinct bugs.

**Contaminated candidates, counted apart (FR-15.2)** (mode discovery, seed set 187)

| arm | contaminated candidates | distinct confirmed bugs excluding them |
|---|---|---|
| seeded | 1 | 0 |
| mutation | 0 | 0 |

**Lag.** The campaign ran at a pin 41 commits and 6.0 days behind `main`, on `firtool-1.86.0`; the current pin window contains a release. A longer lag mechanically lowers the filing rate, because more candidates come back already fixed and every such candidate fails the gate's fourth question.

**Confirmation cut-off.** Maintainer confirmation lags the budget window: a filing is confirmed when a maintainer labels, comments on or fixes it, which happens after the window has closed. Confirmations recorded after 2026-09-23 are not counted in the headline above.

**Dedup rates, which qualify the headline.** Collision rate 1/11 = 0.0909; false-merge rate 1/11 = 0.0909, both measured over the hand-labelled duplicate-pair set. 1 candidate carries an unstable fingerprint, which qualifies the headline exactly as a collision does and never merges.

**Seed sets.** The seeded arm probed 2 seeds and the mutation arm 2; the two sets are identical, which FR-18.2 requires within a mode.

## 2. Secondary results

**The five secondaries per arm** (mode discovery, seed set 187)

| arm | candidates before dedup | candidates after dedup | filings | gate precision | repairs merged | repro.sh overwritten |
|---|---|---|---|---|---|---|
| seeded | 2 | 2 | 2 | 1/2 (50.0%) | 1 | 1 |
| mutation | 1 | 0 | 0 | n/a (0 filings) | 0 | 0 |

Gate precision is confirmed filings over filings. A merged repair is a filed patch a maintainer acted on, which is the same evidence the headline takes. `repro.sh overwritten` counts the repair attempts whose reproduce turn replaced the script the loop pre-wrote, so that "confirms rather than invents" is reported per attempt rather than assumed.

## 3. Failure taxonomy

**FR-18.6's mapping, from gate stopping value to bucket** (mode discovery, seed set 187)

| gate question | stopping value | bucket |
|---|---|---|
| 1 | did_not_reproduce | unreproducible |
| 1 | rerun_unscheduled | unreproducible |
| 2 | no_reducer | not_minimal |
| 2 | not_fixpoint | not_minimal |
| 2 | reduced_false | not_minimal |
| 2 | reduction_changed_failure | not_minimal |
| 3 | invalid_input | invalid_input |
| 4 | dedup_basis_insufficient | undecided |
| 4 | dedup_unavailable | undecided |
| 4 | duplicate_of_candidate | duplicate |
| 4 | fixed_post_pin | duplicate |
| 4 | known_closed_issue | duplicate |
| 4 | known_open_issue | duplicate |
| none | passed all four | new_bug |

**Candidates at the gate, one bucket each** (mode discovery, seed set 187)

| bucket | candidates |
|---|---|
| unreproducible | 0 |
| not_minimal | 0 |
| invalid_input | 0 |
| duplicate | 1 |
| undecided | 0 |
| new_bug | 2 |
| no gate decision | 0 |

Sum check: 3 bucketed = 3 candidates reaching the gate. 1 differential candidate excluded by construction: they never enter the gate and are counted in the divergences list instead.

**Repair attempts, by the phase that failed** (mode discovery, seed set 187)

| failing phase | attempts |
|---|---|
| fix | 1 |
| none (the attempt ran to the end) | 1 |

Sum check: 2 = 2 repair attempts.

**Probe outcomes, by build status** (mode discovery, seed set 187)

| outcome | seeded | mutation |
|---|---|---|
| clean_exit | 1 | 1 |
| parse_error:tool_rejected_input | 0 | 0 |
| parse_error:tool_rejected_argv | 0 | 1 |
| assertion | 1 | 0 |
| fatal_error | 0 | 1 |
| crash | 1 | 0 |
| timeout | 0 | 0 |
| oom | 0 | 0 |
| tool_unavailable | 0 | 0 |

`parse_error` is printed as two rows: `tool_rejected_input` is the tool refusing the probing input, and `tool_rejected_argv` is the tool refusing the argument vector the loop built, which is an apparatus defect and not a property of the input. They sum to the `parse_error` total.

**Turns that produced nothing** (mode discovery, seed set 187)

| arm | stage | kind | turns | first detail |
|---|---|---|---|---|
| mutation | stage_2 | `stale_at_build` | 1 | firtool rejects this seed's own test/Dialect/FIRRTL/errors.mlir at e1d47b09c3a6f582041b9e7d63c085a4f27b1d09 |
| seeded | stage_2 | `prompt_contract:no_block` | 2 | PromptContractError: no_block |

3 turns produced no probing input at all. Such a turn appears in no other table, nothing downstream of stage 2 having run for it: it raised, its output failed the footer contract, or its seed's own test is one the entry tool no longer accepts at the run commit. The detail is the first 120 characters of the first such turn's own record.

## 4. Seeded-bug validation, reported separately

**Seeded-bug validation, which contributes nothing to the headline** (mode discovery, seed set 187)

| seed | sdk exact | eligible seeded/mutation | probes | candidates | filings |
|---|---|---|---|---|---|
| `3f9a1c0e7b4d` | True | 1/1 | 2 | 2 | 1 |
| `7b2d48e1a05c` | False | 1/1 | 4 | 2 | 1 |

This table is separate from the discovery result above and contributes nothing to it: validation establishes that the apparatus finds a bug it was pointed at, and the headline counts bugs nobody pointed it at.

## 5. Divergences observed

**Divergences observed, counted apart from the candidate count** (mode discovery, seed set 187)

| candidate | arm | seed | verdict | first divergent signal | cycle | report |
|---|---|---|---|---|---|---|
| `c-0004` | mutation | `7b2d48e1a05c` | diverge | out_sum | 37 | arcilator and Verilator disagree on out_sum at cycle 37 |

1 divergence observed. A divergence produces an informational report and nothing else: it enters no gate, is never filed, and is counted neither in the candidate count nor in the headline.

## 6. The budget: both windows and the campaign's spend

**Both arm windows, on the primary budget unit** (mode discovery, seed set 187)

| arm | window (s) | elapsed (s) | unspent (s) | stopped by | spend (USD) |
|---|---|---|---|---|---|
| seeded | 14400 | 14400 | 0 | its own window | 1.93 |
| mutation | 14400 | 9000 | 5400 | generated_inputs_per_day | 0.00 |

The campaign spent USD 2.10 in total, both arms and the shared stages together, against the pre-registered cap. Where an arm was stopped by a safety cap rather than by its window, the unspent balance above is what it did not get to use, and the comparison is qualified by exactly that much.

**Shared stages, charged to no arm** (mode discovery, seed set 187)

| stage | seconds |
|---|---|
| image | 3600 |
| synthesis | 420 |

## 7. Observed, and not the budget

**Tokens, money and CPU time: observations, NOT the budget** (mode discovery, seed set 187)

| arm | prompt tokens | output tokens | cached prompt tokens | USD | CPU seconds | entries with null token counts |
|---|---|---|---|---|---|---|
| seeded | 94149 | 14934 | 8192 | 0.1260 | 12880 | 5 |
| mutation | 0 | 0 | 0 | 0.0000 | 8129 | 4 |
| shared | 188400 | 9600 | 0 | 0.1770 | 29100 | 1 |

**Cached prompt tokens: 8192.** Those are prompt tokens the backend served from its context cache, already counted inside the prompt-token column and priced by this ledger at the registered list input rate, because `budget.yaml` registers exactly two rates and a third one added after the registration would not be the file the campaign was registered against (FR-14.7). Google prices cached input lower, so **the USD total above is an UPPER BOUND by that difference on these tokens** - which is the safe direction for a cap, and the count is here so the size of the overstatement can be computed rather than guessed.

None of these four is the budget. The budget is one elapsed wall-clock second of an arm's fixed window, and the table above is what the run was observed to consume while spending it. The USD total is a **lower bound excluding stage 7**, whose per-turn token counts the repair chain does not return: its turns are dispatched remotely and the counting copy of the model object dies with the worker.

**Unpriced turns: 1.** That is the number of metered model-stage entries for turns that WERE dispatched, carrying an authorisation, a bill or a call count, and whose token counts were never observed, so they hold a null cost rather than a zero and the USD total above excludes every one of them. A turn that raised inside the tool loop reports nothing at all, however many model calls it had already made, and so does every stage-7 attempt by construction; the figure is what the lower bound is a lower bound BY, counted rather than described.

**Turns refused before dispatch: 0.** Those entries are metered model stages whose turn never reached the backend: no authorisation, no bill and no call count, because a screen or a stop rule ran in its place, as a stage 6 the duplicate verdict skips does, an arm that ends at `stale_at_build`, or a turn the pre-authorisation refuses. They consumed no tokens, so they are not money the lower bound is missing and they are counted here rather than above (D-9).

**Billed against authorised, over 2 turn(s): max 0.200x, mean 0.175x; 0 turn(s) billed more than they were authorised for and 0 reached the backend's own per-turn ceiling.** `SpendGuard` authorises a turn before it is sent and this is how close the estimate came. A ratio above 1.0 is money the cap did not stop: W-18 measured 19.7x, 32.3x and 64.1x, because the authorisation bounded one model call and a turn with tools makes up to `max_tool_iterations` of them (errata row 38).

## 8. Declarations and disclosures

**The mutator synthesis is the one place the mutation arm sees bug reports.** The frozen mutator set `1111111111111111111111111111111111111111111111111111111111111111` was synthesised at 2026-09-17T11:00:00+00:00 by vertex:gemini-3.8-flash from the mirrored issue set refreshed at 2026-09-19T00:00:00+00:00 (588 issues, all). That is Mut4All's design, which this arm reimplements, and not a leak in the experiment: the arm reads no report during the campaign, and the set was frozen and committed before the pre-registration.

**The contamination screen is incomplete.** It matches a candidate against the commits that touched the seed's files and symbols, and a seed's siblings may be fixed in commits whose subjects do not name them; a candidate this screen calls clean may still be one the upstream history knows about.

**The repair stage is unscreened.** CHIA's executor runs unchanged, so the repair agent sees whatever its own chain shows it, and this run made 2 repair attempts on vertex. Nothing in the screen above applies to them.

## 9. Regeneration

**Every results row, regenerated from its recorded artefacts** (mode discovery, seed set 187)

| candidate | arm | regenerated | marks |
|---|---|---|---|
| `c-0001` | seeded | yes |  |
| `c-0002` | seeded | yes |  |
| `c-0003` | mutation | yes |  |
| `c-0004` | mutation | yes |  |

4 rows regenerated and 0 marked. A marked row is **not reported as a result**: the deterministic stages were re-run from the stored inputs and disagreed with the record, or the artefacts they need are gone. Replaying a stored value through the bypass is never accepted as evidence for a tool stage.
