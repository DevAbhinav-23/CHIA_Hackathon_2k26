# ADR-D-04: How equal budget is measured and enforced

**Status:** Accepted, **amended 2026-09-13** after the HLD review (W1).
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-04.

## Context

D-04 lists six options for the unit the head-to-head equalises. Its own table says a cap on generated
inputs favours the seeded arm on compute, and throughput is a mutation fuzzer's entire advantage, so
budgeting inputs deletes the baseline's only edge. Tokens are unavailable on the `claude` backend and
undefined for the mutation arm at run time, and ADR-D-03 makes `claude` a live possibility.

## Decision

Adopt D-04's recommendation exactly as the FRD writes it.

- **Primary budget unit (G-48):** wall-clock seconds per arm on a declared worker type, with both
  arms run from the same cluster YAML at identical apparatus concurrency. The `RunManifest` names the
  unit, the worker type, the concurrency and the cluster YAML's commit SHA (FR-14.5).
- **Amendment, the arms run sequentially.** D-04 chose wall clock and never said whether the two arms
  are in flight at once, which is the question the HLD could not be written without. Run
  concurrently on a fixed cluster, each arm's wall clock is measured under the other's load, which
  is precisely the contamination wall clock was chosen to avoid; and summing per-node time per arm
  double-counts whenever two of one arm's stages overlap. So: **the arms run one after the other,
  each for the same fixed window `W` recorded in `budget.yaml`, in an order also recorded there.**
  One second of `LedgerEntry.amount` on the single `arm_window` entry per arm is one elapsed second
  of that arm's window, metered by the campaign driver on the head. Every other entry is
  `scope=stage` occupancy, an observation that may exceed the window where stages overlap; CPU
  seconds, tokens and cost are `observed` and never `amount`. `LedgerEntry.arm` takes a third value,
  `shared`, for the campaign-wide stages (the image, the mirror, the corpus, the pin, the offline
  mutator synthesis, the store, the renderer, the driver), which are attributable to no arm and are
  reported beside the arms rather than folded in or split.
  **Cost of the amendment:** the campaign takes two windows of wall clock rather than one, which is
  real against C-10 and is the price of a comparison a reviewer will accept.
- **Safety caps, equal for both arms:** generated inputs per day, and filings per day and in total.
  They bound damage; they do not define the experiment.
- **Reported but not budgeted:** the seeded arm's tokens and cost, available on the Gemini backends
  only (ADR-D-03), and both arms' CPU time, printed under a heading saying they are not the budget.
- **Stop rule, as amended:** each arm stops when its own window expires or one of its safety caps
  binds, and the results artefact states both windows, naming the binding cap and the unspent
  balance where one bit (FR-18.10). The original "the other arm stops at the same moment" presumed
  overlapping arms and is withdrawn with them.
- FINAL §4's word "GPU-hours" is recorded as a misnomer, not silently substituted: no stage uses a
  GPU.

## Consequences

- **FRD:** resolved. G-48, FR-14.1, FR-14.4, FR-14.5 and FR-18.10 carry the amendment as errata dated
  2026-09-13. Option (e), which selected two units for a requirement written for one, stays rejected
  in the option table.
- **HLD:** the ledger writer accrues wall clock per arm and per stage and is the one component both
  halves write to, which is why `LedgerEntry` is in the contract package; the campaign driver meters
  each arm's window on the head and owns the stop rule; the cluster topology fixes apparatus
  concurrency, since the unit means nothing without a declared one.
- **Cost:** the arms may not run at different concurrencies, and a cluster YAML change mid-campaign
  invalidates the comparison, so the YAML SHA is a manifest field.

## Follow-up measurements

None required here. **A-03**'s per-probe slowdown feeds the wall-clock allowance chosen in
`budget.yaml`, and lands in `analysis/measurements/`.
