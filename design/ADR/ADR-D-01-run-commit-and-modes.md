# ADR-D-01: Which CIRCT commit the probing inputs run on

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-01.

## Context

`paper/main.tex` Fig. 1 and §2 describe building CIRCT at the seed's commit; FINAL §3 says the loop
runs on release-pinned main. Both are wanted: discovery produces filable findings about today's
CIRCT, and calibration is the only mode that can validate the repair chain and the gate against a
known answer, the seed's own fix being the ground truth (FR-18.5). Unrestricted calibration is up to
38 images (PIN §4), the largest unstated item in the FRD.

## Decision

Adopt **(c) both modes, declared per run**, with **(d) calibration restricted to a named sample of
k seeds**, where **k is a `[DEFAULT]` of 20** recorded in `budget.yaml` under the calibration
sample-size key of FR-14.1, together with the SHA list of the sampled seeds. The sample is fixed by
the pre-registration commit, so it cannot be chosen after the data exists.

"The run's commit" is defined per mode exactly as FR-02.7 defines it, and by no other means:

- **Discovery mode:** `run_commit` is the release-pinned-main commit FR-02.1 selected, one value for
  the whole campaign. This is the campaign mode, and the only mode a filing may come from.
- **Calibration mode:** `run_commit` is the seed's own first-parent commit, one value per seed, and
  the `RunManifest` carries one entry per calibrated seed.

FR-10.4, FR-12.6, FR-13.2 and FR-15.5 read that field and nothing else. The mode is a required
`RunManifest` field and every results row names it.

## Consequences

- **FRD:** resolved; no requirement changes. FR-18.2's per-mode seed-set property and D-07's two
  qualifiers on every results table stand as written.
- **HLD:** the mode flows through `RunManifest` into every component; the image builder runs once per
  campaign in discovery and up to k times in calibration; the gate runs in both modes and records
  without filing in calibration.
- **Cost:** at D-01's measured 4 to 5 GB an image, k of 20 is on the order of 80 to 100 GB of disk,
  against 150 to 190 GB for the unrestricted 38.

## Follow-up measurements

**A-03** (image build cost under the three flag strings) and **A-15** (the repair chain's
fail-to-pass rate over a calibration sample), in `analysis/measurements/`.
