# Design document set: the closed CIRCT bug loop

**Status: Draft.** Owner: Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla (IIIT Hyderabad).
Date: 2026-09-13.

## Purpose

`problem-statement-FINAL.md` states a thesis. `paper/main.tex` states it publicly. Neither is
buildable. This set turns the thesis into a specification precise enough that it can be built without
re-deriving any decision, and precise enough that a tester can say whether what they built is
what was specified.

The subject is one system: a CHIA loop that seeds an agent with mined CIRCT fix commits, generates
probing inputs, judges them with a crash-or-assertion oracle, reduces, deduplicates, attempts repair
through CHIA's existing phase chain, and gates every filing behind a named human.

## The documents and their order

| # | Document | Answers | Status |
|---|---|---|---|
| 00 | `00-README.md` | What this set is, how it is numbered, when code may start | Draft |
| 01 | `01-FRD.md` | What the system shall do, testably | Draft |
| 02 | `02-HLD.md` | What the parts are, what each owns, where the seam is | Draft, revised after its red-team review |
| 03 | `03-LLD.md` | Every module, class, schema, file format, command line | Draft, revised after its red-team review |
| 04 | `04-Test-Plan.md` | How each requirement is shown to hold | Not started |
| 05 | `05-Work-Plan.md` | Who builds which half, in what order, against which contract | Not started |
| n/a | `ADR/` | One file per resolved open decision, named `ADR-D-nn-<slug>.md` | 14 files |
| n/a | `reviews/` | One hostile review per document, plus its disposition table. `red-team-FRD.md` and `red-team-FRD-disposition.md` are the pair for 01; `red-team-HLD.md` and `red-team-HLD-disposition.md` the pair for 02; `red-team-LLD.md` and `red-team-LLD-disposition.md` the pair for 03 | Current |

Read them in that order. 01 is normative for behaviour; 02 and 03 are normative for structure; 04
is normative for evidence; 05 is normative for sequence. Where 02 or 03 contradicts 01, 01 wins and
the contradiction is a defect in 02 or 03.

## ID scheme

| Prefix | Meaning | Example |
|---|---|---|
| `F-nn` | Feature: a named capability, owned by one or more loop stages | `F-07` |
| `FR-nn.m` | Functional requirement, `nn` = its feature | `FR-07.3` |
| `NFR-nn` | Non-functional requirement | `NFR-05` |
| `C-nn` | Constraint: a fact of CHIA, CIRCT or the environment that the design may not change | `C-01` |
| `A-nn` | Assumption: something the design relies on that is not yet verified | `A-02` |
| `D-nn` | Open decision: a genuine choice, with options, consequences and a recommendation | `D-01` |
| `G-nn` | Glossary term | `G-14` |

IDs are permanent. A withdrawn requirement is struck through and marked `WITHDRAWN`, never reused
and never renumbered. A new requirement takes the next free number in its feature.

Stage numbers come from `paper/main.tex` and are fixed: 1 read the seed, 2 write probing inputs,
3 build, 4 judge, 5 reduce, 6 triage and report, 7 repair, then the human gate. No document in this
set may rename or renumber a stage.

## Status conventions

| Status | Meaning |
|---|---|
| Draft | Being written. No downstream document may depend on it. |
| Reviewed | Read end to end by a team member who did not write it, with every comment resolved or recorded as a `D-nn`. |
| Approved | Reviewed, plus every `D-nn` it raises is either resolved in `ADR/` or explicitly deferred with a named owner and a date. |

A document's status is the first line of the document. Changing it is a commit of its own.

## The no-code rule

**No implementation code is written until 01 through 05 are all Approved.** Exceptions, and only
these: throwaway measurement scripts whose output feeds an `A-nn` or a `D-nn`, and the `budget.yaml`
pre-registration commit, which by definition must land before the campaign and may land before the
documents.

The rule exists because the deadline is 2026-09-24 AoE and the largest risk is building against
an interface that was never written down.

## The seam rule (formerly the two-person rule)

The user ruled on 2026-09-13 that one builder, the architect working through Opus agents, builds the
entire system start to finish. No work is split between people. The seam survives as a **test
boundary**: `02-HLD.md` exposes exactly one seam, a versioned contract package that splits the
system into two halves that are tested independently against recorded fixtures before they are
joined. The **supply half** is everything that proposes work: the seed corpus, the seeded generator,
the mutation generator and its offline mutator synthesis, the feedback loop, the budget ledger
writer. The **apparatus half** is everything that measures: the image, the build, the oracles, the
reducers, the dedup and contamination screen, the repair adapter, the gate, the store, the renderer,
the driver.

The contract is the package of **seven schemas** (`SeedRecord`, `BudgetFile`, `ProbeSpec`,
`ProbeResult`, `FeedbackBundle`, `LedgerEntry`, `RunManifest`) **plus one interface**, the driver's
call into a generator, `generate(seed, feedback, remaining) -> list[ProbeSpec]`, with its read-only
`LedgerSnapshot` argument view. A change to any member or to the interface is a version bump.
Revised 2026-09-13 after the HLD review: the earlier list of five carried `CandidateRecord`, which
cannot be the up-flowing member because a candidate exists only where an oracle fired while FR-16.1
needs a record per probing input, and it left `SeedRecord`, the budget file and the generator call
crossing the line uncontracted.

**The contract is at version 2.0**, revised 2026-09-14 after the LLD review. The seven members and
the one interface are unchanged; `SeedRecord` gained two **required** fields, `diff` (the seed
commit's diff of its `lib/` and `include/` paths) and `test_files` (each changed test path to its full
text at the seed commit), which by the package's own rule is a MAJOR bump. They exist because neither
generator arm could otherwise reach its seed's contents: both arms run on worker containers whose only
CIRCT tree is a one-commit checkout and whose only bind mount is the artefact root, so the seeded
arm's `$diff` and the mutation arm's starting inputs had no source at all. With them the record is
self-contained and neither arm needs git. `03-LLD.md` §2.1 and §2.4 carry the detail.

`05-Work-Plan.md` is a single-track, dated plan for the one builder. It may not reduce scope: everything
`01-FRD.md` marks Must is built. Human actions the plan schedules but cannot perform (the forum post,
any filing, the GCP hand-over) are listed with the date by which the user must act.
