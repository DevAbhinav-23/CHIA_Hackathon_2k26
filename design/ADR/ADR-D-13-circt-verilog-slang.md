# ADR-D-13: How `circt-verilog` reaches the run's commit

**Status:** Accepted, **amended 2026-09-13** after the M1 measurements.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-13.

The title keeps D-13's own wording, because IDs and their headings are stable across this set. Read
it as "how the **slang front end** reaches the run's commit": the amendment below establishes that
the decision governs two binaries rather than one, and the narrower reading was part of the error.

## Context

C-16, as amended: a slang-less build loses **two** entry points into SystemVerilog, and one cmake
option gates both.

- `circt-verilog` has no ninja target at all in an SDK-based build, which is why CHIA omits it
  (`chia:examples/circt_issue_solver/circt_issue_loop.py:40-45`).
- `circt-translate --import-verilog` is registered only under `#ifdef CIRCT_SLANG_FRONTEND_ENABLED`
  (`circt:tools/circt-translate/circt-translate.cpp:31-33`, whose define comes from
  `circt:tools/circt-translate/CMakeLists.txt:4-6`), so a `circt-translate` that CHIA **does** build
  from source still cannot read SystemVerilog.

Verified on the binaries on 2026-09-13: `bassert_g/bin/circt-translate --help | grep -c
import-verilog` returns 0 against the SDK's 1, and `bassert_g/bin/circt-verilog` does not exist. The
SDK ships both capabilities at the SDK's commit for read-only use.

**36** of the 187 seeds need a slang-enabled binary: 31 have a `RUN:` line entering via
`circt-verilog`, 34 via `circt-translate --import-verilog`, and their union is 36. Without one at the
run's commit, gate question 1 is unanswerable for all 36.

~~The previous context, "46 of the 187 seeds sit in the `.sv` region: FR-01.4's ImportVerilog 31,
MooreToCore 12 and Moore 3",~~ is **WITHDRAWN** 2026-09-13
(`analysis/measurements/2026-09-13-frd-followups.md` M1). It was wrong twice. The rule it used,
bucketing by the **source file** a seed's fix touched, does not answer which binary a seed's probes
need; and under that rule the count is 48, not 46. The 12-seed difference between 48 and 36 is
`MooreToCore` work whose tests are `.mlir` and whose entry tool is `circt-opt`, which is first-class
in a slang-less build and must not be excluded. No slang-entry seed lies outside the source region,
so 36 is a subset of 48 and the correction only removes seeds from the affected set.

## Decision

Adopt **(a): build slang from source in the image**, `-DCIRCT_SLANG_FRONTEND_ENABLED=ON` with
`-DCIRCT_SLANG_BUILD_FROM_SOURCE=ON` (`circt:CMakeLists.txt:550-551`, both verified present at
`b792c772`; the first defaults `OFF`, the second `ON`), **with (b) exclusion of the 36 slang-entry
seeds as the recorded fallback, measured first.** Under (a) both entry points come back, and they
come back together, because one option gates both.

The slang build is the first thing F-03's implementation attempts, timeboxed against A-03's
measurement task. If it does not come up, FR-03.14 falls to (b): the seeds whose `RUN:` lines enter
through either slang entry point are excluded from discovery **by configuration**, and the exclusion,
with its size, is recorded in the `RunManifest`, the results artefact and the paper. The exclusion is
defined by **entry point**, never by source region, which is the rule the withdrawn 46 got wrong.

Option (c), running those probes on the SDK's own binaries, is rejected. They have assertions off and
are at the wrong commit, so the primary oracle cannot fire in them and nothing found there can be
filed: a class that adds a table row and nothing to the experiment.

## Consequences

- **FRD:** resolved. FR-03.14 stands, with its acceptance criterion amended 2026-09-13 to name **36**
  excluded seeds selected by entry point; C-16 and D-13 carry the same correction as errata in
  `01-FRD.md` §1.6.
- **The fallback's cost is larger than the seed count says.** Branch (b) also removes
  `--import-verilog` from a `circt-translate` the image otherwise builds in full, so a tool the
  corpus reaches by two routes would work by one. That was not stated before this amendment.
- **HLD:** the exclusion is an `ImageSpec` and `RunManifest` field the seed corpus component and the
  evaluation driver both read, not a branch inside any oracle; under branch (a) every entry tool
  resolves to `/workspace/circt/build/bin`, which is what the LLD must record (C-16, FR-06.1).
- **Cost:** slang is a substantial C++ dependency on an image whose cost A-03 has not measured, and
  the fallback cuts 19.3% of the corpus. Measured at the lit level (M3): 62 of the image's 63
  unsupported tests are `REQUIRES: slang`, spread over `Conversion/ImportVerilog` 36,
  `circt-verilog/` 17, `Tools/circt-verilog-lsp-server` 9 and `Dialect/ESI` 1, so branch (b) also
  means the whole SystemVerilog surface is skipped rather than run.

## Follow-up measurements

**A-03**, timeboxed with the slang build attempt, in `analysis/measurements/`: whether slang builds
under FR-03.4's flag string, and what it adds to wall time and image size. The answer selects branch
(a) or (b), and is needed before the seeded arm draws any slang-entry seed. M1 measured the scope of
the question and did not attempt the build, so the timebox is untouched.

**Measured 2026-09-13** (M7): option (a) is proven. With `-DCIRCT_SLANG_FRONTEND_ENABLED=ON` (and CIRCT's default `CIRCT_SLANG_BUILD_FROM_SOURCE=ON`, FetchContent pin `44dc55f9`), configure takes 19 s and `ninja -j8 circt-verilog circt-translate circt-opt` completes in 841 s (1,339 edges) under the FR-03.4 flag string; the front end costs 16.8% of build CPU, `circt-verilog` is 71 MB, `circt-translate` grows by 51 MB, `circt-opt` is unchanged. `circt-verilog --version` reports the CIRCT commit and `slang version 11.0.0+0`; on a seed `.sv` the from-source `--ir-moore` output is byte-identical to the SDK's. Fallback (b) is not taken. From-source binaries need the z3 shim on the loader path at run time as well as build time (C-02).
