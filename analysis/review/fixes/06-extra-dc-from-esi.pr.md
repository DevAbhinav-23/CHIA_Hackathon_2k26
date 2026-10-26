# [DC] Fix dc.from_esi type inference for non-integer channels

Fixes: <!-- fill in the issue number(s) -->

## Problem

Found while fixing the previous patch (not one of the 15 loop candidates): parsing `dc.from_esi %a : !esi.channel<!hw.struct<a: i2>>` segfaults.

## Reproducer

```mlir
hw.module @Foo(in %a : !esi.channel<!hw.struct<a: i2>>) {
  %0 = dc.from_esi %a : !esi.channel<!hw.struct<a: i2>>
}
```

```sh
circt-opt repro.mlir
```

- Before (main @ 4738bd2685): segfault in FromESIOp::inferReturnTypes (exit 139)
- After: round-trips; the type is inferred as `!dc.value<!hw.struct<a: i2>>`

## Root cause

`if (auto intType = dyn_cast<IntegerType>(innerType); intType.getWidth() == 0)` dereferences a null type for any non-integer channel payload.

## Fix

Check the cast before reading the width.

## Test

- `test/Dialect/DC/roundtrip.mlir` `@fromESIStruct`.
- The modified test file(s) fail on unmodified main and pass with this series; the lit tests of the touched dialect/conversion directories and the full `build/test` suite (1358 pass / 68 unsupported / 6 xfail, identical to main) pass. Built and run locally only (Linux x86-64, Release + assertions, prebuilt firtool-1.162.0 LLVM; slang frontend and Python bindings off, so ImportVerilog/circt-verilog SV tests are unsupported).

## Notes for reviewers

- Reproducer: `hw.module @Foo(in %a : !esi.channel<!hw.struct<a: i2>>) { %0 = dc.from_esi %a : !esi.channel<!hw.struct<a: i2>> }` with plain `circt-opt` (exit 139 on 4738bd2).
- Diff: code +2/-1, tests +6/-0.
- Found by an LLM-assisted fuzzing loop; patch drafted with Claude and reviewed by the submitter (add the `Assisted-by:` trailer the LLVM AI tool policy asks for if needed).

## Commit message

```
`FromESIOp::inferReturnTypes` called `getWidth()` on the result of
`dyn_cast<IntegerType>` without checking it, so parsing or building
`dc.from_esi` on a channel of a non-integer type (e.g. a struct)
dereferenced a null type and crashed. Check the cast before reading the
width.
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
