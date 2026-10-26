# [DCToHW] Assertion `!empty()` building comb.and for a dc.join with no operands

**Status: draft, not filed.** Found by an LLM-assisted fuzzing loop that
writes test inputs from CIRCT regression tests; reduced automatically and
re-checked on current main. Candidate `c-p-9e7eceaadf12`.

## Reproducer (`repro.mlir`)

```mlir
module {
  hw.module private @Foo(out a : !dc.token) {
    %0 = dc.join 
    hw.output %0 : !dc.token
  }
}
```

## Command

```sh
circt-opt --lower-dc-to-hw repro.mlir
```

## Result

Reproduces on current `main` at 4738bd2685a1bed0f44623ad1a800146a0d8c43c (LLVM pin from firtool-1.162.0,
Release, assertions on) and at eade0de61bc5a0d2ba1b9da951b69efcab19f8ce (firtool-1.159.0). Class: `assertion`.

```text
circt-opt: <llvm-install>/include/llvm/ADT/STLExtras.h:1269: ReferenceT llvm::detail::indexed_accessor_range_base<mlir::ValueRange, llvm::PointerUnion<const mlir::Value *, mlir::OpOperand *, mlir::detail::OpResultImpl *, const llvm::Repeated<mlir::Value> *>, mlir::Value, mlir::Value, mlir::Value>::front() const [DerivedT = mlir::ValueRange, BaseT = llvm::PointerUnion<const mlir::Value *, mlir::OpO
Stack dump:
#9 0x0000557f3c317595 (circt/build/bin/circt-opt+0x181e595)
#10 0x0000557f3c3175ed circt::comb::AndOp::create(mlir::OpBuilder&, mlir::Location, mlir::ValueRange, bool) circt/build/include/circt/Dialect/Comb/Comb.cpp.inc:994:26
#11 0x0000557f3db4ec85 getOpResultImpl <llvm-install>/include/mlir/IR/Operation.h:1068:25
#12 0x0000557f3db4ec85 getResult <llvm-install>/include/mlir/IR/Operation.h:432:54
#13 0x0000557f3db4ec85 getResult <llvm-install>/include/mlir/IR/OpDefinition.h:708:33
#14 0x0000557f3db4ec85 operator TypedValue <llvm-install>/include/mlir/IR/OpDefinition.h:713:54
#15 0x0000557f3db4ec85 callback_fn<(lambda at circt/lib/Conversion/DCToHW/DCToHW.cpp:288:9)> <llvm-install>/include/llvm/ADT/STLFunctionalExtras.h:46:12
#16 0x0000557f3db4ec85 operator() <llvm-install>/include/llvm/ADT/STLFunctionalExtras.h:69:12
```

## CIRCT SHA

- main: `4738bd2685a1bed0f44623ad1a800146a0d8c43c` (`circt-opt --version`: CIRCT 4738bd2)
- also at: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce`
