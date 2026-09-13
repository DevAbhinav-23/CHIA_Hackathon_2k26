# ADR-D-05: What the mutation arm's mutators are, and where they come from

**Status:** Accepted, **amended 2026-09-13** after the HLD review (W18).
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-05.

## Context

The mutation arm is the baseline, and D-05's own argument against hand-written mutators is that a
weak baseline makes the head-to-head worthless. `paper/main.tex` §4 cites Mut4All's method: an LLM
synthesises mutators from past bug reports, once, offline, then the set is frozen. D-05 widens the
source from one year of closed issues to the full closed `label:bug` history, since 65 reports
against Mut4All's 1,000 is weak by D-05's own standard.

## Decision

Adopt D-05's recommendation as written: **(b) Mut4All's method over the full history of closed
`label:bug` issues in `llvm/circt`**, synthesised once offline before the pre-registration commit,
frozen, committed and versioned (FR-05.2). The synthesis prompt, its input set and the resulting set
ship in the release. The mutator file's commit SHA is in the `RunManifest` and predates the
pre-registration commit. The campaign synthesises no new mutators. Option (d), the same method over
the 24-month fix-commit set, stays as the recorded fallback if the issue set proves too small.

The synthesis-time exposure to bug reports is **not** a defect. FR-05.1 isolates the arm at run time,
which is the isolation the head-to-head needs; the exposure is Mut4All's design, happens once and
offline, and is symmetric to the seeded arm's exposure to the same project's history through its
training data, which F-15 screens for. FR-05.8 requires it stated in the results artefact and the
paper.

## Consequences

- **FRD:** resolved; FR-05.2 and FR-05.8 stand unchanged.
- **HLD:** the mutation arm has two parts with different lifetimes: an offline synthesis step run
  once before the campaign, and a run-time mutator runner that is a pure deterministic function of
  (input text, seed integer) calling no model at all (FR-05.3). Only the second is a node in the
  campaign's loop, but **both are components**: the HLD names the synthesis **A7**, with its own
  worker, timeout, retry and failure rows, because the earlier draft had only the runner and the
  synthesis therefore had no owner, no ordering and no cost. A7 charges the ledger as `shared`
  (FR-14.4) and runs before the pre-registration commit. FR-10.9's issue mirror is the synthesis input, so the mirror is built before the
  pre-registration commit, not only before the first candidate.
- **Cost:** one synthesis run, one reviewed frozen set, a declaration sentence in two artefacts.

## Follow-up measurements

**A-21**: count the closed `label:bug` issues through FR-10.9's mirror, as F-05's first task.
`[UNVERIFIED]` today, and it decides whether the fallback to (d) is taken.
In `analysis/measurements/`.

**Measured 2026-09-13** (`analysis/measurements/2026-09-13-slang-verilator-bugcount.md` M9): `llvm/circt` has **487** closed and 101 open `label:bug` issues (GitHub search API, `is:issue`). The synthesis corpus is therefore 487 reports, about half of Mut4All's 1,000 and 7.5 times the 65 an earlier draft assumed; the fallback of synthesising from fix commits is not needed. A-21 is settled.
