# [MooreToCore] Assertion `!values.empty()` in hw::ArrayConcatOp::build lowering an out-of-range array moore.extract

**Status: draft, not filed.** Found by an LLM-assisted fuzzing loop that
writes test inputs from CIRCT regression tests; reduced automatically and
re-checked on current main. Candidate `c-p-a2cb61b8d0aa`.

## Reproducer (`repro.mlir`)

```mlir
module {
  func.func private @array_slice_overflow(%arg0: !moore.i32) -> !moore.array<4 x i32> {
    %0 = moore.array_create %arg0, %arg0 : !moore.i32, !moore.i32 -> array<2 x i32>
    %1 = moore.extract %0 from -2147483648 : array<2 x i32> -> array<4 x i32>
    return %1 : !moore.array<4 x i32>
  }
}
```

## Command

```sh
circt-opt repro.mlir --convert-moore-to-core
```

## Result

Reproduces on current `main` at 4738bd2685a1bed0f44623ad1a800146a0d8c43c (LLVM pin from firtool-1.162.0,
Release, assertions on) and at eade0de61bc5a0d2ba1b9da951b69efcab19f8ce (firtool-1.159.0). Class: `assertion`.

```text
circt-opt: circt/lib/Dialect/HW/HWOps.cpp:2034: static void circt::hw::ArrayConcatOp::build(OpBuilder &, OperationState &, ValueRange): Assertion `!values.empty() && "Cannot build array of zero elements"' failed.
Stack dump:
#9 0x0000563652ac7caf circt::hw::ArrayConcatOp::build(mlir::OpBuilder&, mlir::OperationState&, mlir::ValueRange) circt/lib/Dialect/HW/HWOps.cpp:2037:3
#10 0x0000563653ad784d void mlir::OpBuilder::createOrFold<circt::hw::ArrayConcatOp, llvm::SmallVector<mlir::Value, 6u>&>(llvm::SmallVectorImpl<mlir::Value>&, mlir::Location, llvm::SmallVector<mlir::Va
#11 0x0000563653ad72dd empty <llvm-install>/include/llvm/ADT/SmallVector.h:86:46
#12 0x0000563653ad72dd front <llvm-install>/include/llvm/ADT/SmallVector.h:309:13
#13 0x0000563653ad72dd std::enable_if<circt::hw::ArrayConcatOp::hasTrait<mlir::OpTrait::OneResult>(), mlir::Value>::type mlir::OpBuilder::createOrFold<circt::hw::ArrayConcatOp, llvm::SmallVector<mlir:
#14 0x0000563653ad6fb1 (anonymous namespace)::ExtractOpConversion::matchAndRewrite(circt::moore::ExtractOp, circt::moore::ExtractOpAdaptor, mlir::ConversionPatternRewriter&) const circt/lib
#15 0x0000563653ad7ad2 _M_reset /usr/lib64/gcc/x86_64-pc-linux-gnu/16/../../../../include/c++/16/optional:360:12
#16 0x0000563653ad7ad2 ~_Optional_payload /usr/lib64/gcc/x86_64-pc-linux-gnu/16/../../../../include/c++/16/optional:484:57
```

## CIRCT SHA

- main: `4738bd2685a1bed0f44623ad1a800146a0d8c43c` (`circt-opt --version`: CIRCT 4738bd2)
- also at: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce`
