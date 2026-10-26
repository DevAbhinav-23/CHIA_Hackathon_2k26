# [MooreToCore] Fix overflow in moore.extract padding for extreme offsets

Fixes: <!-- fill in the issue number(s) -->

## Problem

`--convert-moore-to-core` asserts in `hw::ArrayConcatOp::build` (`Cannot build array of zero elements`) on `moore.extract %0 from -2147483648 : array<2 x i32> -> array<4 x i32>`. The integer form (`moore.extract %x from -2147483648 : i4 -> i8`) produces an `hw.bitcast` from `i0` that fails verification.

## Reproducer

```mlir
module {
  func.func private @array_slice_overflow(%arg0: !moore.i32) -> !moore.array<4 x i32> {
    %0 = moore.array_create %arg0, %arg0 : !moore.i32, !moore.i32 -> array<2 x i32>
    %1 = moore.extract %0 from -2147483648 : array<2 x i32> -> array<4 x i32>
    return %1 : !moore.array<4 x i32>
  }
}
```

```sh
circt-opt repro.mlir --convert-moore-to-core
```

- Before (main @ 4738bd2685, assertions on, `--verify-each`): exit 134, `circt-opt: src/lib/Dialect/HW/HWOps.cpp:2034: static void circt::hw::ArrayConcatOp::build(OpBuilder &, OperationState &, ValueRange): Assertion `!values.empty() && "Cannot build array of zero elements"' failed.`
- After: exit 0, valid IR, no diagnostic

## Root cause

The padding for out-of-bounds bit and array-slice extracts is `std::clamp(-low, 0, w)` and `low + w` in `int32_t`. For `lowBit = -2^31` the negation overflows (undefined behaviour; in practice it stays negative) and for offsets near 2^31 the sum does, so the computed padding and extract widths are garbage.

## Fix

Read `lowBit` as before (signed 32-bit) and do the offset arithmetic in `int64_t`. Such extracts are fully out of bounds and lower to zero, like other out-of-bounds extracts.

## Test

- `test/Conversion/MooreToCore/basic.mlir`: array slices from -2^31 and 2^31-1, integer extracts from -2^31 and 2^31-1.
- The modified test file(s) fail on unmodified main and pass with this series; the lit tests of the touched dialect/conversion directories and the full `build/test` suite (1358 pass / 68 unsupported / 6 xfail, identical to main) pass. Built and run locally only (Linux x86-64, Release + assertions, prebuilt firtool-1.162.0 LLVM; slang frontend and Python bindings off, so ImportVerilog/circt-verilog SV tests are unsupported).

## Notes for reviewers

- Touches the same function as open PR llvm/circt#11267 (range checks for dynamic accesses), but different lines; a rebase conflict, if any, is local.
- Diff: code +18/-15, tests +10/-0.
- Found by an LLM-assisted fuzzing loop; patch drafted with Claude and reviewed by the submitter (add the `Assisted-by:` trailer the LLVM AI tool policy asks for if needed).

## Commit message

```
`ExtractOpConversion` computes the zero padding for out-of-bounds bit and
array-slice extracts as `-low` and `low + resultWidth` in `int32_t`. For a
`lowBit` of -2^31 the negation overflows, and for offsets near 2^31 so
does the sum. The resulting padding widths were garbage: an array slice
ended up with nothing to concatenate and `hw::ArrayConcatOp::build`
asserted ("Cannot build array of zero elements"), and an integer extract
produced an `hw.bitcast` from `i0`, which fails verification.

Do the offset arithmetic in `int64_t`; the 32-bit `lowBit` cannot overflow
it. Such extracts are now fully out of bounds and lower to zero, like
other out-of-bounds extracts.
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
