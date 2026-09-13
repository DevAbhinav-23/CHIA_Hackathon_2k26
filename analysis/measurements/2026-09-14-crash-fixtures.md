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

---

_(Sections 1, 2, 4 and 5 are filled in as the attempts complete.)_
