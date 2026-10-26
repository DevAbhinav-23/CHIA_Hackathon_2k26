# [DC] Reject dc.join without tokens

Fixes: <!-- fill in the issue number(s) -->

## Problem

`--lower-dc-to-hw` asserts (`!empty()` in `ValueRange::front`, via `comb::AndOp::create`) on `%0 = dc.join` with no operands.

## Reproducer

```mlir
module {
  hw.module private @Foo(out a : !dc.token) {
    %0 = dc.join 
    hw.output %0 : !dc.token
  }
}
```

```sh
circt-opt --lower-dc-to-hw repro.mlir
```

- Before (main @ 4738bd2685, assertions on, `--verify-each`): exit 134, `circt-opt: sdk/include/llvm/ADT/STLExtras.h:1269: ReferenceT llvm::detail::indexed_accessor_range_base<mlir::ValueRange, llvm::PointerUnion<const mlir::Value *, mlir::OpOperand *, mlir::detail::OpResultImpl *, const llvm`
- After: exit 1, `repro.mlir:3:10: error: 'dc.join' op expected at least one token`

## Root cause

`JoinOp`'s operand list is `Variadic<TokenType>` and its only builder asserts `ins.size() > 0`, but there was no verifier, so the parser accepted an empty join. DCToHW lowers the join's valid to the AND of the input valids, which is empty.

## Fix

Add `JoinOp::verify` requiring at least one token.

## Test

- `test/Dialect/DC/errors.mlir`: the reproducer, `expected-error {{'dc.join' op expected at least one token}}`.
- The modified test file(s) fail on unmodified main and pass with this series; the lit tests of the touched dialect/conversion directories and the full `build/test` suite (1358 pass / 68 unsupported / 6 xfail, identical to main) pass. Built and run locally only (Linux x86-64, Release + assertions, prebuilt firtool-1.162.0 LLVM; slang frontend and Python bindings off, so ImportVerilog/circt-verilog SV tests are unsupported).

## Notes for reviewers

- An alternative is to give a zero-input join `dc.source` semantics and canonicalize it away; the builder's assertion suggests the op was never meant to be empty, so this patch rejects it.
- Diff: code +7/-0, tests +8/-0.
- Found by an LLM-assisted fuzzing loop; patch drafted with Claude and reviewed by the submitter (add the `Assisted-by:` trailer the LLVM AI tool policy asks for if needed).

## Commit message

```
`dc.join` takes a variadic list of tokens and its builder asserts that the
list is non-empty, but the verifier accepted `dc.join` with no operands.
DCToHW then built a `comb.and` over the empty list of input valids and
asserted (`!empty()` in `ValueRange::front`).

Add a verifier that requires at least one token.
```

🤖 Generated with [Claude Code](https://claude.com/claude-code)
