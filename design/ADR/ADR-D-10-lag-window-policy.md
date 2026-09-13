# ADR-D-10: What the loop does inside a lag window

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-10.

## Context

Release-pinned main trails `main`'s head, because head's pin has no release SDK and one LLVM bump off
is a hard build failure at target 2 of 1030 (C-01). FINAL Appendix A records 16 of 63 pin windows
over 24 months never receiving a matching release, in 15 runs, the worst lasting 100 commits and
16.1 days. D-10 asks what the loop does inside such a window.

## Decision

Adopt **(c): run at the newest first-parent commit whose pin has a release, however old, with the lag
recorded and every candidate screened against fixes made after it.** Option (b), pausing until a
release matches, is rejected against C-10: a 16-day pause is fatal eleven days from the deadline.

The mechanism already exists and this decision only fixes the policy: FR-02.2 reports the lag in
commits and days, FR-02.4 records whether the current pin window contains a release at all, and
FR-10.4 scans commits made on `main` after the run's commit and records a match as `fixed_post_pin`.

D-10's missing consequence is binding: (c) with FR-10.4 and FR-13.5 means **a long lag mechanically
lowers the filing rate**, because more candidates come back `fixed_post_pin` and every value other
than `new` fails gate question 4. The headline is therefore partly a function of when the campaign
ran. **The results artefact shall state the lag the campaign ran under, beside the headline**, as
FR-18.8 already commits to a confirmation cut-off date.

## Consequences

- **FRD:** resolved; FR-02.2, FR-02.4 and FR-10.4 stand, and the lag disclosure joins the results
  artefact's mandatory statements.
- **HLD:** the release-pinned-main selector emits the lag as `RunManifest` fields the results renderer
  prints; the dedup component owns the post-pin commit scan, whose window is bounded below by
  `run_commit` and is therefore the lag itself, which is why FR-10.4 may match at file level where
  FR-15.1 may not.
- **Cost:** one more disclosure sentence, and a headline a reviewer can discount by the lag.

## Follow-up measurements

None. F-02 measures the lag on every run into the `RunManifest`, so there is no separate task.

**First application (2026-09-14).** `origin/main` HEAD `eab8d182` (2026-09-12) carries LLVM pin `e297b52e`, which has no `firtool-*` release. The selector chose the newest commit whose pin has one: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce` (2026-09-07), pin `62797005`, tags `firtool-1.159.0` / `1.158.0` / `1.157.0`; lag 8 first-parent commits, 4.807 days, recorded for the manifest. Option (c) behaved as specified.
