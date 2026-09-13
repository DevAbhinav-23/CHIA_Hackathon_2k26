# ADR-D-08: The assertions-on image's target set, and its unmeasured cost

**Status:** Accepted, **amended 2026-09-13** after the HLD review (W6) and the M2 measurements.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-08.

## Context

FR-03.7 asks for `circt-opt`, `firtool`, `circt-translate`, `arcilator` and `circt-reduce` under
`-O3 -UNDEBUG -gline-tables-only`. D-08's premise was that building more than `circt-opt` from source
is the new cost. C-21 corrects it: CHIA already warm-builds six targets
(`chia:examples/circt_issue_solver/circt_issue_loop.py:44-45`), and `circt_warm_build`'s docstring
calls the five beyond `circt-opt` cheap because the shared dialect libraries are already built
(`chia:chia/chipyard/circt.py:670`). The marginal new target is `circt-reduce` alone; the real
multiplier is the flag string.

## Decision

Adopt **(c): build the set, measure first, and cut only on evidence.** The measurement runs as the
first task of the implementation phase, before any apparatus work depends on the image, recorded
against A-03. The target list stays an `ImageSpec` parameter, not a constant (FR-03.7), so a cut is a
configuration change recorded in the `RunManifest`.

Option (b), `circt-opt` only from source with the other tools from the SDK, stays rejected: the SDK's
binaries are at the SDK's commit with assertions off, so a `firtool` or `circt-verilog` probe would
have no primary oracle at all, gutting the oracle for most of the corpus.

## Consequences

- **FRD:** resolved; FR-03.4, FR-03.7, C-21 and A-03 stand unchanged.
- **HLD:** the image builder is one component, `ImageSpec` in and a digest out, with the target list
  and the flag string both `ImageSpec` fields; nothing downstream reads a hard-coded target list.
- **Cost, now measured.** `analysis/measurements/2026-09-13-frd-followups.md` M2 ran all three flag
  strings, one compiler, one target set, cold and ccache-free, `-j12` on a 20-core host: the five
  tool targets build in **582 s** under `-O3 -UNDEBUG -gline-tables-only`, 676 s under `-O3 -UNDEBUG`
  and 621 s under `-O3 -DNDEBUG`, 1082 ninja edges each; the build tree is **1.3 GB**, 588 MB and
  425 MB respectively; `circt-opt` is 192 MB, 73 MB and 60 MB; and the per-probe cost of
  `-gline-tables-only` on a 4000-op probe is **+3.4%**. The published base image
  `ghcr.io/ucb-bar/chia-circt:latest` is 4.79 GB on disk in 17 layers. The assertions-on image's own
  size is still unmeasured, because no such image was built; D-08 is resolvable on the host numbers
  and cannot yet quote an image size.
- **Amendment, the image bakes the whole target set.** The published CHIA image bakes only
  `circt-opt` (M5, verified inside the image), which is why CHIA needs `circt_warm_build` at run
  time. This image bakes every target in the `ImageSpec` list, so a fresh container starts warm, no
  component calls `circt_warm_build`, and no arm is charged for another arm's warm-up. At 582 s for
  five targets, baking is cheaper than paying it once per container per run.

## Follow-up measurements

**A-03**, first task of the implementation phase, in `analysis/measurements/`: build FR-03.7's target
set under `-DNDEBUG`, under `-O3 -UNDEBUG`, and under `-O3 -UNDEBUG -gline-tables-only`, recording
for each the wall time, the binary size, the image size and a per-probe slowdown. **The size and
build-time delta of `-gline-tables-only` alone is a required output**, because FR-03.4 adds it and
this decision prices it.

**A-20**, beside it because it needs no build: FR-03.6's set-equality check over the whole `test/`
tree against the `-UNDEBUG` build already standing at `~/.cache/chia-pin-smoke/bassert`. One command.
F-12's whole verify gate depends on the answer.
