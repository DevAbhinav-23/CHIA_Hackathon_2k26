# ADR-D-07: Which seed set the campaign draws from

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-07.

## Context

The corpus is 187 mined seeds over 24 months, of which 171 have an exact-pin release SDK (PIN §4).
The 16 without one can seed hypotheses but can never be built at their own commit, so they are
unusable in the calibration mode ADR-D-01 keeps. D-07 offers all 187, the 171 only, or a per-mode
split, and recommends the split.

## Decision

Adopt **(c): 187 in discovery mode, 171 in calibration mode.** Discovery runs every probing input at
one commit, ADR-D-01's release-pinned-main commit, so exactness of a seed's own SDK is irrelevant
there and excluding 16 seeds, 8.6% of the corpus, would buy nothing. Calibration builds at each
sampled seed's own first-parent commit and cannot work without an exact-pin SDK, so its draw, and its
sample of k, come from the 171.

FR-04.7 stands: a seed whose `sdk_exact` is false is usable for generation and is never the run's
build commit.

## Consequences

- **FRD:** resolved. D-07's stated consequence is binding: taken with ADR-D-01's two modes, **every
  results table carries two qualifiers, the mode and the seed set**, and a table missing either fails
  the render (FR-18.2). "The two arms' seed SHA sets are identical" is a per-mode property, not a
  global one.
- **HLD:** the seed corpus component emits both sets from one mined corpus and tags each seed with
  `sdk_exact`; the evaluation driver selects the set from the mode; the results renderer refuses a
  table that does not name both qualifiers.
- **Cost:** two qualifiers on every table, and a per-mode rather than global equality check.

## Follow-up measurements

**A-02**: the 187 and 171 counts rest on a subject-keyword proxy, and PIN §4 states plainly that
neither was validated by reading diffs. Read the diffs of a random sample of 30 seeds and report the
precision. Recorded in `analysis/measurements/`. The result does not change this decision; it
qualifies what the corpus is, and belongs beside the headline as a threat to validity.
