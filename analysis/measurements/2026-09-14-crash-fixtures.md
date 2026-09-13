# W-09: the recorded real-crash fixture set, 2026-09-14

`04-Test-Plan.md` §5 asks for at least `budget.yaml`'s `acceptance.recorded_failures`
(**5**) real CIRCT failures, each recorded with its input, its argv, its commit and its
stderr, and each replayable. This file is the mining record: what was attempted, what
fired, what it cost, and the two design defects the real output exposed.

Nothing under `design/` or `paper/` was edited. The harness is committed beside this file
(`w09_lib.sh`, `w09_attempt.sh`, `w09_runner.py`, `w09_oracle.py`, `w09_mkfixture.py`,
`w09_select.py`); the fixtures are under
`circt_bug_loop/tests/fixtures/crashes/<class>_<nn>/`.

## 0. What ran against what

| Item | Identity |
|---|---|
| CIRCT clone | `~/.cache/chia-pin-smoke/circt`, blobless (`--filter=blob:none`), `https://github.com/llvm/circt` |
| Worktrees | `~/.cache/chia-pin-smoke/w09/wt143` and `wt156`, detached per attempt |
| Build directories | `~/.cache/chia-pin-smoke/w09/b143` and `b156`, one per SDK tag, reused across attempts |
| SDK, 1.143.0 | `sdk-1.143.0`, from `https://github.com/llvm/circt/releases/download/firtool-1.143.0/circt-full-shared-linux-x64.tar.gz`, 144,155,092 B |
| SDK, 1.156.0 | `sdk-1.156.0`, from `https://github.com/llvm/circt/releases/download/firtool-1.156.0/circt-full-shared-linux-x64.tar.gz`, 142,226,653 B |
| SDK strip | `include/circt` and `lib/cmake/circt` removed from both, so the source tree's own CIRCT headers and CMake package are the ones used |
| Compiler | `clang`/`clang++` and `lld` from `~/Projects/Honours/MLIR/llvm-project/build/bin` |
| Configure | `-DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" -DLLVM_ENABLE_ASSERTIONS=ON -DMLIR_DIR=<sdk>/lib/cmake/mlir -DLLVM_DIR=<sdk>/lib/cmake/llvm -DMLIR_SOURCE_DIR=<sdk> -DLLVM_USE_LINKER=lld -DLLVM_PARALLEL_LINK_JOBS=2 -DLLVM_CCACHE_BUILD=ON` (`w09_lib.sh:configure`) |
| Parallelism | `ninja -j8` |
| Run bound | `prlimit --as=8589934592 --cpu=120:125`, plus a 180 s wall bound applied by the runner rather than by `timeout(1)`, whose own message would otherwise land in a recorded stderr |
| z3 | `~/.cache/chia-pin-smoke/shim/libz3.so.4` on `LD_LIBRARY_PATH` |
| No model, no credential, no docker | host builds only |
| Date | 2026-09-14 |

**One path discrepancy, left as found and flagged rather than silently resolved.**
`04-Test-Plan.md` §5.2 and §13 both name the fixture root `fixtures/oracle/<class>_<nn>/`,
and §4's `T-E-input-02` refers to `fixtures/oracle/crash_01/` by that name. W-09's own brief
and the already-committed `crash_01` use `fixtures/crashes/<class>_<nn>/`. The directories
below are `crashes/`, so this set is self-consistent and the `<class>_<nn>` half of the
name is the plan's; the rename to `oracle/`, or the plan's amendment, is a one-line
decision for whoever owns `04-Test-Plan.md` and is **not** made here.

## 1. The attempts

Candidates come from Source A only (`04-Test-Plan.md` §5.1): the committed 187-seed corpus
`circt_bug_loop/tests/fixtures/corpus/filtered_187.json`, filtered to the seeds whose
subject names a crash, an assertion, a segfault, an `UNREACHABLE`, a verifier failure or a
null/invalid-access fix, ranked newest first, preferring `circt-opt` on a `.mlir` test with
an exact SDK pin. `w09_select.py` is that filter and that ranking; its tool, argv and shape
come from `corpus.normalise_run_line`, so a candidate it calls usable is one the runner
will execute identically. Source B (closed `label:bug` issues) was **not** needed: Source A
reached six confirmations and all three classes.

An attempt is confirmed when the seed's own test input, run through its own normalised
`RUN:` line, fires the primary oracle at the seed's **first parent** and does **not** fire
at the seed. Both runs are recorded either way.

| # | Attempt | Seed | Parent | Tag | Tool | Configure | Parent build | Seed build | Result |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `v1-simstrconcat` | `564e07083c52` `[Sim] Fix null dereference in StringConcatOp::fold` | `2f46bdfae165` | 1.143.0 | `circt-opt --canonicalize` | b143, 1 configure for all of 1 to 4 | 14 s / 6 edges | 13 s / 6 | **confirmed** `crash_01` |
| 2 | `v2-dynarray` | `b3b407b37bb2` `[MooreToCore] Fix crash on dynamic array variable conversion` | `87f131c0af7f` | 1.143.0 | `circt-opt --convert-moore-to-core` | reused | 68 s / 42 | 24 s / 6 | **confirmed** `assertion_01` (piece 1 of 9) |
| 3 | `v3-classnew` | `c3e2100d37ca` `[MooreToCore] Fix crash on class new with unsupported member types` | `6fc9ee90ddad` | 1.143.0 | `circt-opt --convert-moore-to-core` | reused | 601 s / 567 | 38 s / 6 | **confirmed** `fatal_error_01` (piece 8 of 19) |
| 4 | `v4-instancegraph` | `88d9a5ad7a3a` `[InstanceGraph] Relax assertion failure condition` | `5481d1901ca0` | 1.143.0 | `circt-opt --sv-trace-iverilog` | reused | 59 s / 16 | 5 s / 5 | **confirmed** `assertion_02` |
| 5 | `v5-mooreextract` | `cc71d34ab52f` `[MooreToCore] Fix out-of-bounds and aggregate moore.extract lowering` | `454f38652dea` | 1.156.0 | `circt-opt --convert-moore-to-core` | b156, 1 configure for 5 to 7 | 427 s / 420 (after 606 edges of cold pre-warm) | 33 s / 6 | **discarded**: exits 0 at the parent |
| 6 | `v6-omassert` | `4ac632ae7dd8` `[OM] Fix crash in assert w/ block arg message` | `1728445e7e57` | 1.156.0 | `circt-opt -om-elaborate-object` | reused | 589 s / 529 | 5 s / 6 | **confirmed** `assertion_03` |
| 7 | `v7-omnonconst` | `56f16468bccf` `[OM] Fix OM evaluator assert w/ non-constant msg` | `4ac632ae7dd8` | 1.156.0 | `circt-opt -om-elaborate-object` | reused | 0 s / 0 (the parent is attempt 6's seed) | 4 s / 6 | **confirmed** `assertion_04` |

Six confirmed of seven attempted; the budget was eight. The one discard is recorded because
`04-Test-Plan.md` §5.1 step 4 requires it: the corpus filter is a subject-keyword proxy and
A-02 already records that neither 187 nor 171 was validated by reading diffs, so a seed
whose test passes at its parent is evidence about the filter, not a failure of the method.
`cc71d34ab52f`'s other test file is `test/circt-verilog/roundtrip-oob-reads.sv`, which needs
the slang front end; it was not built, so the discard is only about the `.mlir` half.

Two configures, one per SDK tag, both from `w09_lib.sh:configure`; every attempt after the
first on a tag reuses its build directory, which is why attempt 7 rebuilt nothing at all.
Attempts 1 to 4 share one worktree and one build directory and were run in commit order, so
each parent build is an increment on the previous attempt's seed build; the 601 s of attempt
3 is the one large jump in that chain.

## 2. The fixtures

`fixtures/crashes/<class>_<nn>/`, six directories, each holding exactly the six files of
`04-Test-Plan.md` §5.2, all produced by `w09_mkfixture.py` from the recorded run rather than
hand-written.

| Fixture | Class | Signal | What fires | Site or message | Fingerprint frame |
|---|---|---|---|---|---|
| `crash_01` | `crash` | `SIGSEGV` | no text at all; the signal only | `lib/Dialect/Sim/SimOps.cpp:541` (frame) | `circt::sim::StringConcatOp::fold SimOps.cpp` |
| `assertion_01` | `assertion` | `SIGABRT` | `_ASSERT_GLIBC` | `isa<To>(Val) && "cast<Ty>() argument of incompatible type!"` at `include/llvm/Support/Casting.h:566` | `main circt-opt.cpp` (see §3.2) |
| `assertion_02` | `assertion` | `SIGABRT` | `_ASSERT_GLIBC` | `!candidateTopLevels.empty() && "if non-cyclic, there should be at least 1 candidate top level"` at `lib/Support/InstanceGraph.cpp:230` | `circt::igraph::InstanceGraph::getInferredTopLevelNodes InstanceGraph.cpp` |
| `assertion_03` | `assertion` | `SIGABRT` | `_ASSERT_GLIBC` | `detail::isPresent(Val) && "dyn_cast on a non-existent value"` at `include/llvm/Support/Casting.h:656` | `verifyResult ElaborateObject.cpp` |
| `assertion_04` | `assertion` | `SIGABRT` | `_ASSERT_GLIBC` | `isa<To>(Val) && "cast<Ty>() argument of incompatible type!"` at `include/llvm/Support/Casting.h:560` | `verifyResult ElaborateObject.cpp` |
| `fatal_error_01` | `fatal_error` | `SIGABRT` | `_FATAL_ERROR` | `neither the scoping op nor the type class provide data layout information for !sim.dstring` | `main circt-opt.cpp` (see §3.2) |

`04-Test-Plan.md` §5's **target composition is met**: at least one `assertion`, one `crash`
and one `fatal_error`, and six against `budget.yaml`'s `acceptance.recorded_failures` of 5.
Two SDK tags are represented, so §5.4's per-fixture image rule has more than one image to
build. `_ASSERT_UNREACHABLE` is **not** represented: no seed in the filtered set produced an
`UNREACHABLE executed` firing, which is consistent with §5.1's own expectation that Source A
underproduces the deliberate-refusal paths, and it remains the one §3.6.1 pattern tested
only against the document's constructed sample.

`assertion_03` and `assertion_04` are a deliberate near-pair: two distinct upstream bugs,
two distinct fix commits, one identical `fingerprint_frame`, separated only by the assertion
basis. §3.2 and §3.4 below are what they and the other four exposed.

## 3. What the real output did to the design's own rules

Three things were measured against real stderr rather than against a constructed sample.
The first is a confirmation; the second and third are defects, and the fixtures record
what the rules actually produce rather than what they were meant to produce (§5.4: an
`expected.json` is never edited to match a wish).

### 3.1 `_FRAME` matched every frame-shaped line, in both shapes (confirmation)

`03-LLD.md` §3.6.2's `_FRAME` was applied to every line of the recorded traces that begins
with the crash handler's `#<n> ` prefix. Both shapes of §3.6.2 occur in each trace, and
none failed:

| Fixture | frame-shaped lines | matched | failed |
|---|---|---|---|
| `crash_01` | 36 | 36 | 0 |
| `assertion_01` | 38 | 38 | 0 |
| `fatal_error_01` | 44 | 44 | 0 |
| `assertion_02` | 25 | 25 | 0 |

The C++-aware `_ASSERT_GLIBC` of §3.6.1 is also confirmed on real output rather than on the
document's own two compiled samples. `assertion_01`'s line is

```
circt-opt: <sdk>/include/llvm/Support/Casting.h:566: decltype(auto) llvm::cast(From &) [To = circt::llhd::RefType, From = mlir::Type]: Assertion `isa<To>(Val) && "cast<Ty>() argument of incompatible type!"' failed.
```

whose `func` group holds two `::` pairs and a bracketed template argument list; the old
`[^:]+` spelling K1 replaced would not have matched it, and the probe would have been
classified `crash` on the signal instead of `assertion`.

### 3.2 **Defect.** §3.7.1's normalisation erases every anonymous-namespace frame

§3.7.1 step 2 is *"cutting everything from the first `(` that is at bracket depth zero,
which removes the parameter list"*. A CIRCT pass or conversion pattern is almost always in
an anonymous namespace, and `llvm-symbolizer` demangles such a frame as
`(anonymous namespace)::VariableOpConversion::matchAndRewrite(...)`. Its **first**
character is a depth-zero `(`, so step 2 cuts at offset 0 and the normalised name is the
empty string. §3.7.1 then says *"A frame whose normalised function name is empty or the
degenerate `operator` ... is skipped"*, so the fingerprint walks straight past the frame
that names the bug.

Measured across the four recorded traces, every one loses at least one frame this way, and
in each case it is the frame a maintainer would name as the location:

| Trace | frames erased to `""` |
|---|---|
| `crash_01` | `(anonymous namespace)::GreedyPatternRewriteDriver::processWorklist`, `(anonymous namespace)::Canonicalizer::runOnOperation` |
| `assertion_01` | `(anonymous namespace)::VariableOpConversion::matchAndRewrite`, `(anonymous namespace)::OperationLegalizer::legalize`, `(anonymous namespace)::MooreToCorePass::runOnOperation` |
| `fatal_error_01` | `(anonymous namespace)::ClassNewOpConversion::matchAndRewrite`, `(anonymous namespace)::OperationLegalizer::legalize`, `(anonymous namespace)::MooreToCorePass::runOnOperation` |
| `assertion_02` | `(anonymous namespace)::SVTraceIVerilogPass::runOnOperation` |

`crash_01` survives it by luck: `circt::sim::StringConcatOp::fold` is a named-namespace
frame and is the one below the erasure, so its `fingerprint_frame` is the right one. The
others do not. **The cost is worst for the class that has no other basis.** For a `crash`
or a `fatal_error` §3.7.1's primary fingerprint is `f"{signal_name}\n{fingerprint_frame}"`
and there is nothing else, so an erased frame moves the fingerprint to whatever the next
qualifying frame is, which in a `circt-opt` trace is `main` in `circt-opt.cpp`: every such
candidate in a campaign would then carry one of a handful of identical fingerprints, which
is exactly the collapse K3 introduced the prologue strip to prevent.

**This is now live, not only textual.** `circt_bug_loop/probe_task.py`, committed by W-08
at `de43f65` while this set was being mined, implements the rule as written:
`_normalise_function` cuts *"at the first `(` at bracket depth zero"*
(`probe_task.py:376-391`). So the apparatus reproduces the defect, and `assertion_02`'s and
`fatal_error_01`'s `expected.json` are what it will produce.

The fix is one clause, and belongs in `03-LLD.md` §3.7.1 rather than here: step 2 should
skip a leading `(anonymous namespace)` (and the `::` after it) before looking for the first
depth-zero `(`, or equivalently cut at the first depth-zero `(` that is **not** at offset 0
with `anonymous namespace` inside it. W-09 does not edit the design; the defect is recorded
in each affected fixture's `README.md` and its consequence is visible in
`expected.json:fingerprint_frame`.

### 3.3 **Defect.** `strip_probe_only_options` misses CIRCT's own single-dash spelling

`circt_bug_loop/corpus.py:77` is

```python
_PROBE_ONLY_OPTIONS = ("--split-input-file", "--verify-diagnostics")
```

and `strip_probe_only_options` removes a token equal to one of those or beginning with one
of them plus `=`. That is faithful to `03-LLD.md` §3.3 and §4.2, whose *"both spellings"*
means **bare and `=`-valued**. But `circt-opt` is an LLVM `cl::opt` tool and accepts one
dash as readily as two, and CIRCT's own tests write it that way: the seed of
`assertion_02`, `test/Dialect/SV/sv-trace-iverilog-errors.mlir`, has

```
// RUN: circt-opt --sv-trace-iverilog %s -verify-diagnostics
```

so `-verify-diagnostics` survives normalisation and lands in the probe argv, where §3.3
says it means nothing and must not be. It is recorded in `assertion_02/argv.json` because
the fixture records what the committed function produces. Two consequences, both measured
on `b143/bin/circt-opt` at `2026-09-14`:

1. The surviving option changes the **polarity** of a probe. The flag makes the tool exit 0
   when the emitted diagnostics match the input's `expected-*` comments, so a generated
   probe that legitimately fails to parse would be scored as a clean run.
2. Stripping the flag does **not** silence the diagnostic verifier, which is a separate
   surprise worth recording. With no `--verify-diagnostics` anywhere on the command line,
   an input carrying an `expected-error` comment still draws
   `error: expected error "..." was not produced` on stderr; the flag governs only whether
   that verdict reaches the exit status:

   ```
   $ cat vd2.mlir
   // expected-error @below {{nothing at all}}
   func.func @ok() { return }
   $ circt-opt vd2.mlir                       # no flag at all
   vd2.mlir:1:4: error: expected error "nothing at all" was not produced
   ...
   rc=0
   $ circt-opt <errors.mlir piece 1> --convert-moore-to-core                     ; echo rc=$?
   ... error: failed to legalize operation 'moore.variable' ...
   ... error: expected error "failed to legalize..." was not produced
   rc=1
   $ circt-opt <errors.mlir piece 1> --convert-moore-to-core --verify-diagnostics; echo rc=$?
   rc=0
   ```

   For a *generated* probe this is moot, because a generated input carries no `expected-*`
   comment. For a *mined* fixture, whose input is a real test file, it means the recorded
   `stderr.txt` of a **non**-firing run carries a line that neither the tool nor the loop
   asked for. No fixture in this set is affected: in every recorded firing the tool dies
   before the verifier reports.

### 3.4 **Defect.** `out_of_scope_root` reads an inlined frame, not the physical one

`03-LLD.md` §3.6.2 step 4 makes `out_of_scope_root` true *"when, after §3.7.1's crash-handler
prologue is stripped, the first remaining frame is not in a CIRCT object"*, and FR-07.5
makes that the gate on whether F-12 tries to repair the bug at all. LLVM's crash handler
prints **inlined** frames as separate `#n` lines that share one address. In an
`-O3 -gline-tables-only` build the physical frame that crashes is almost always CIRCT's,
while the topmost inlined line inside it is an SDK header — `Diagnostics.h` for the
`operator<<` that builds an assertion message, `AttributeSupport.h` for the `cast<>` that
segfaults. Reading only the first line therefore answers a different question than the one
asked.

Measured over the four fixtures mined here:

| Fixture | frames dropped | first line after the strip | physical frame | `out_of_scope_root` |
|---|---|---|---|---|
| `crash_01` | 4 | `getAbstractAttribute`, `mlir/IR/AttributeSupport.h` | `circt::sim::StringConcatOp::fold`, `SimOps.cpp:541` | **true** |
| `assertion_01` | 9 | `createZeroValue`, `MooreToCore.cpp` | same | false |
| `fatal_error_01` | 8 | unresolved SDK frame | MLIR's `getDefaultTypeSizeInBits` | **true** (correctly) |
| `assertion_02` | 9 | `append<const char (&)[68]>`, `mlir/IR/Diagnostics.h` | `circt::igraph::InstanceGraph::getInferredTopLevelNodes`, `InstanceGraph.cpp:221` | **true** |

`assertion_02` is the clearest case: frames `#9`, `#10` and `#11` all carry the address
`0x00005587daf8f82b`, and `#11` is `InstanceGraph.cpp:221`. The bug is entirely CIRCT's — a
CIRCT assertion, in a CIRCT file, fixed by a CIRCT commit — and the design as written puts
it out of scope. `crash_01` is the same shape: `#4` through `#10` share
`0x0000561553f7dfd5` and `#10` is `SimOps.cpp:541`.

This too is live: `probe_task.py:287` is
`out_of_scope_root=bool(fired) and not (stripped and stripped[0].in_circt_object)`, the
first stripped frame and nothing else.

So three of the four real bugs are out of scope under the rule as written, and only
`fatal_error_01`'s `true` is the answer the rule wanted. The fix is again one clause for
`03-LLD.md` §3.6.2: group the stripped frames by address and take the **last** (innermost
caller, outermost source) line of the first group, or equivalently make the predicate
`any(f.in_circt_object for f in first_address_group)`. As with §3.2 this is recorded, not
applied; `out_of_scope_root` is not one of §5.2's `expected.json` keys, so no fixture
hard-codes the wrong answer, but `T-U-probe-24`'s scope assertions will land on it.

---

## 4. What it cost

| Item | Size |
|---|---|
| `~/.cache/chia-pin-smoke/w09` total | **3.4 GB** |
| `b143` (1.143.0 build dir, `circt-opt` only) | 876 MB |
| `b156` (1.156.0 build dir, `circt-opt` only) | 947 MB |
| `sdk-1.143.0` extracted | 632 MB |
| `sdk-1.156.0` extracted | 659 MB |
| the two SDK tarballs, kept | 138 MB + 136 MB |
| `wt143` + `wt156` worktrees | 32 MB + 40 MB |
| `attempts/` (every recorded run, both sides, all pieces) | 2.6 MB |
| the shared blobless clone `~/.cache/chia-pin-smoke/circt` | 118 MB |
| `~/.cache/chia-pin-smoke` whole (W-04's and W-05's caches included) | 9.0 GB |
| **the committed fixtures** | **63,585 B in 36 files** |

`04-Test-Plan.md` §13 budgets this row at "5 directories, 30 files, under 1 MB"; six
directories and 36 files at 62 kB are inside it. No binary is committed: every fixture file
is text or JSON.

Wall time was dominated by two cold-ish builds, attempt 3's 601 s and attempt 6's 589 s on
top of a 606-edge pre-warm; the other five parent builds together cost 568 s. `ninja -j8`
(`-j10` for the 1.156.0 attempts) with `ccache` on, on a 20-core host with 15 GiB of RAM,
most of the swap already committed by unrelated processes, which is why parallelism was held
well below the core count and the two build directories were never driven at once.

## 5. Re-deriving the set

The fixtures are pinned to commits, not to this host. To re-derive one from scratch:

```
$ analysis/measurements/w09_select.py --clone <blobless clone> --exact --limit 25
$ analysis/measurements/w09_attempt.sh <name> <seed> <parent> <test path> <tag> \
      <worktree> <build dir> <sdk dir> circt-opt
$ analysis/measurements/w09_mkfixture.py --attempt <attempt dir> --piece parent-pNN \
      --name <class>_<nn> --dest circt_bug_loop/tests/fixtures/crashes --why "<paragraph>"
```

`w09_oracle.py` is `03-LLD.md` §3.6.1, §3.6.2 and §3.7.1 transcribed verbatim and is the
reference the fixtures were classified with; no apparatus code existed when they were mined,
so it is committed beside them and is what a later `probe_task.py` must agree with, file by
file, on `expected.json`. `w09_runner.py` does **not** transcribe §3.3: it imports
`corpus.normalise_run_line` and `corpus.strip_probe_only_options` from the flow itself, so
the argv in every `argv.json` is the argv the committed normaliser produces, defects
(§3.3) and all.

Three host-specific strings survive in the recorded evidence and are **not** compared
values: the build prefix `~/.cache/chia-pin-smoke/w09/wt143` (or `wt156`) for CIRCT sources,
`~/.cache/chia-pin-smoke/w09/sdk-1.143.0` (or `-1.156.0`) for the SDK, and
`~/.cache/chia-pin-smoke/w09/b143` (or `b156`) for the binary, in place of the image's
`/workspace/circt/` and `/opt/circt-sdk/`. §3.7.1 strips the build prefix before a site
enters a fingerprint, so the prefix is evidence only; each fixture's `README.md` records its
own relative site.
