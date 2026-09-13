# ADR-D-06: The exact definitions of candidate, report, filing, confirmed and distinct

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-06.

## Context

Two red-team findings turned on loose versions of these five words. The headline metric is
"distinct, maintainer-confirmed bugs", and every word in it had to be pinned before it could be
counted. "Distinct" was defined only inside FR-18.3 and rested on a duplicate rule that was not an
equivalence relation, so "one per fingerprint" was not well defined until G-43 narrowed the merging
key to one.

## Decision

Adopt D-06 as written. The five definitions are normative and are used in exactly these senses,
nowhere loosely, in the paper and every artefact:

- **Candidate (G-23):** produced by an oracle and by nothing else. Oracle agreement with itself is a
  candidate, never a bug.
- **Report (G-25):** a local file. It exists whether or not anyone ever sees it.
- **Filing (G-26):** a GitHub issue created from a report after a named human approved that report.
- **Confirmed (G-27):** a CIRCT maintainer labelled, commented on or fixed it, evidenced by a URL.
  Maintainer action only; no self-grading.
- **Distinct (G-44):** one per primary fingerprint (G-43). Two filings whose candidates share a
  primary fingerprint count once.

The primary fingerprint is the only key with the power to merge (FR-10.1, FR-10.2): the normalised
assertion text with its `file:line` for an `assertion`, and the ordered tuple of the top N symbolised
frame function names for a `crash` or a `fatal_error`, N a `[DEFAULT]` in `budget.yaml`. String
equality is reflexive, symmetric and transitive, so the partition ignores arrival order.

## Consequences

- **FRD:** resolved; G-23, G-25, G-26, G-27 and G-44 are normative as they stand.
- **HLD:** the dedup component owns the fingerprint and the partition; the structural hash and the
  frame tuple ride as evidence fields of `CandidateRecord` and merge nothing; the results renderer
  counts the headline per fingerprint and prints the collision and false-merge rates beside it.
- **Cost:** a candidate with no assertion text and fewer than N resolvable frames has no fingerprint,
  deduplicates against nothing, and fails gate question 4 as `dedup_basis=insufficient` (FR-10.8).

## Follow-up measurements

**A-05**: the collision and false-merge rates over FR-10.2's labelled pair set, in
`analysis/measurements/`. The acceptance is that both are measured and printed.
