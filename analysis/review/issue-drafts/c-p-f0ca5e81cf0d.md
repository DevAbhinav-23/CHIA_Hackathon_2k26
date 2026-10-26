# [CoreToFSM] APInt width assertion in comb.icmp folding during -convert-core-to-fsm

**Status: draft, not filed.** Found by an LLM-assisted fuzzing loop that
writes test inputs from CIRCT regression tests; reduced automatically and
re-checked on current main. Candidate `c-p-f0ca5e81cf0d`.

Possibly the same root cause as the other 'CoreToFSM reset registers' drafts; consider filing them as one issue.

## Reproducer (`repro.mlir`)

```mlir
module {
  hw.module private @Foo(in %a : !seq.clock, in %b : i1, out c : i1) {
    %c0_i2 = hw.constant 0 : i2
    %false = hw.constant false
    %state = seq.compreg %state, %a reset %b, %c0_i2 : i2  
    %0 = comb.icmp eq %b, %false : i1
    hw.output %0 : i1
  }
}
```

## Command

```sh
circt-opt -convert-core-to-fsm repro.mlir
```

## Result

Reproduces on current `main` at 4738bd2685a1bed0f44623ad1a800146a0d8c43c (LLVM pin from firtool-1.162.0,
Release, assertions on) and at eade0de61bc5a0d2ba1b9da951b69efcab19f8ce (firtool-1.159.0). Class: `assertion`.

```text
circt-opt: <llvm-install>/include/llvm/ADT/APInt.h:1061: bool llvm::APInt::operator==(const APInt &) const: Assertion `BitWidth == RHS.BitWidth && "Comparison requires equal bit widths"' failed.
Stack dump:
#9 0x0000555b68af2095 applyCmpPredicate circt/lib/Dialect/Comb/CombFolds.cpp:3041:3
#10 0x0000555b68af2095 circt::comb::ICmpOp::fold(circt::comb::ICmpOpGenericAdaptor<llvm::ArrayRef<mlir::Attribute>>) circt/lib/Dialect/Comb/CombFolds.cpp:3080:11
#11 0x0000555b68b10173 isNull <llvm-install>/include/llvm/ADT/PointerUnion.h:289:38
#12 0x0000555b68b10173 operator bool <llvm-install>/include/llvm/ADT/PointerUnion.h:296:44
#13 0x0000555b68b10173 llvm::LogicalResult mlir::Op<circt::comb::ICmpOp, mlir::OpTrait::ZeroRegions, mlir::OpTrait::OneResult, mlir::OpTrait::OneTypedResult<mlir::IntegerType>::Impl, mlir::OpTrait::Ze
#14 0x00007f850d3d93b3 mlir::Operation::fold(llvm::SmallVectorImpl<mlir::OpFoldResult>&) (<llvm-install>/lib/libMLIRIR.so+0x16b3b3)
#15 0x00007f850ec3fbef (anonymous namespace)::GreedyPatternRewriteDriver::processWorklist() GreedyPatternRewriteDriver.cpp:0:0
#16 0x00007f850ec3e5af mlir::applyOpPatternsGreedily(llvm::ArrayRef<mlir::Operation*>, mlir::FrozenRewritePatternSet const&, mlir::GreedyRewriteConfig, bool*, bool*) (<llvm-install>/lib/libMLIRTransfo
```

## CIRCT SHA

- main: `4738bd2685a1bed0f44623ad1a800146a0d8c43c` (`circt-opt --version`: CIRCT 4738bd2)
- also at: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce`
