# [CombToSynth] Assertion `outOfBoundsValue must be valid` lowering an i0 comb.shl

**Status: draft, not filed.** Found by an LLM-assisted fuzzing loop that
writes test inputs from CIRCT regression tests; reduced automatically and
re-checked on current main. Candidate `c-p-3d0f9c33ee0a`.

Possibly the same root cause as the other 'CombToSynth narrow widths' drafts; consider filing them as one issue.

## Reproducer (`repro.mlir`)

```mlir
module {
  hw.module private @Foo(in %a : i0, in %b : i0) {
    %0 = comb.shl %a, %b : i0
    hw.output
  }
}
```

## Command

```sh
circt-opt repro.mlir '--pass-pipeline=builtin.module(hw.module(convert-comb-to-synth{additional-legal-ops=comb.xor,comb.or,comb.and,comb.mux},cse))'
```

## Result

Reproduces on current `main` at 4738bd2685a1bed0f44623ad1a800146a0d8c43c (LLVM pin from firtool-1.162.0,
Release, assertions on) and at eade0de61bc5a0d2ba1b9da951b69efcab19f8ce (firtool-1.159.0). Class: `assertion`.

```text
circt-opt: circt/lib/Conversion/CombToSynth/CombToSynth.cpp:101: Value createShiftLogic(ConversionPatternRewriter &, Location, Value, int64_t, llvm::function_ref<Value (int64_t)>, llvm::function_ref<Value (int64_t)>) [isLeftShift = true]: Assertion `outOfBoundsValue && "outOfBoundsValue must be valid"' failed.
Stack dump:
#9 0x0000561dd08ab920 getOpResultImpl <llvm-install>/include/mlir/IR/Operation.h:1068:5
#10 0x0000561dd08ab920 getResult <llvm-install>/include/mlir/IR/Operation.h:432:54
#11 0x0000561dd08ab920 getResult <llvm-install>/include/mlir/IR/OpDefinition.h:708:33
#12 0x0000561dd08ab920 getType <llvm-install>/include/mlir/IR/OpDefinition.h:715:35
#13 0x0000561dd08ab920 (anonymous namespace)::CombShlOpConversion::matchAndRewrite(circt::comb::ShlOp, circt::comb::ShlOpAdaptor, mlir::ConversionPatternRewriter&) const circt/lib/Conversio
#14 0x0000561dd0893d82 _M_reset /usr/lib64/gcc/x86_64-pc-linux-gnu/16/../../../../include/c++/16/optional:360:12
#15 0x0000561dd0893d82 ~_Optional_payload /usr/lib64/gcc/x86_64-pc-linux-gnu/16/../../../../include/c++/16/optional:484:57
#16 0x0000561dd0893d82 ~_Optional_base /usr/lib64/gcc/x86_64-pc-linux-gnu/16/../../../../include/c++/16/optional:508:12
```

## CIRCT SHA

- main: `4738bd2685a1bed0f44623ad1a800146a0d8c43c` (`circt-opt --version`: CIRCT 4738bd2)
- also at: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce`
