# ADR-D-09: How Verilator reaches the image

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-09.

## Context

No CHIA image installs Verilator: `chia:dockerfiles/VerilatorRunDockerfile:7-8` installs the runtime
dependencies of already-compiled simulator binaries, not the simulator (§4.3). The secondary
differential oracle needs one. The probe host has Verilator 5.052, where FINAL Appendix A records
`--x-initial` and `--x-assign` as present. D-09 recommends apt with escalation.

## Decision

Adopt **(a): `apt-get install verilator` in the assertions-on image**, with the installed version
recorded in the `ImageSpec`, in the `RunManifest` and in every `DifferentialVerdict`, escalating to
**(b) a pinned source build** only if the packaged version lacks `--x-initial` or `--x-assign`.

D-09's missing consequence is binding and is already FR-03.15: flag presence is the small risk, and
the real one is that X propagation itself differs between Verilator versions, the axis the whole
differential rides on (FR-08.4, FR-08.9). **One Verilator version therefore serves the whole
campaign.** An image rebuild that changes it starts a new campaign, and a run whose image's
`verilator --version` differs from the manifest's exits non-zero naming both.

Option (c), a separate `verilator` worker type, is rejected: a cluster edge and a data transfer per
comparison, for an image-size saving D-08's measurement has not shown to matter.

## Consequences

- **FRD:** resolved; FR-03.8 and FR-03.15 stand unchanged.
- **HLD:** the differential oracle and its two harness generators run on the same `circt` worker and
  image as the build stage and the primary oracle, with no second worker type and no cross-worker
  transfer; the Verilator version is an `ImageSpec` field and a mandatory field of every
  `DifferentialVerdict`.
- **Cost:** one apt line, a version equality check at run start, and a campaign restart if the image
  is ever rebuilt with a different Verilator.

## Follow-up measurements

**A-19**, before any work on F-08's harness generators: run FR-08.1's applicability rule over the
corpus and report the count of differential-applicable seeds with the rule that produced it.
`[UNVERIFIED]` today, and it decides whether F-08 is worth building at all.

**A-08**, after it: FR-08.2's acceptance on the recorded 12-line FIRRTL register-add, the only
evidence that either harness generator is feasible from a port list. Both in
`analysis/measurements/`.

**Measured 2026-09-13** (M8): Ubuntu 24.04 packages Verilator **5.020-1**; `--x-initial`, `--x-assign`, `--binary` and `--timing` are all present with help text identical to the host's 5.052. The escalation trigger is not met; option (a) stands. Cost: one apt line, 27 MB download, 123 MB on disk. Residual risk unchanged: the image's Verilator is 20 months behind the version the X-propagation evidence was taken on, so the campaign records its version in every differential verdict (FR-03.15).
