# [Seq] FirMemory segfaults on a FIRRTLMem whose readUnderWrite is not a RUWAttr

**Status: draft, not filed.** Found by the mutation-based baseline of a fuzzing
loop (syntactic mutation of CIRCT regression tests, no LLM); reduced
automatically and re-checked on current main. Probe `p-1a505efbec1f` (14
candidates, 9 `readUnderWrite` + 5 `writeUnderWrite`). The loop's gate
dropped these as fixed after its build point, citing ddb3d1bd ("Bump LLVM"),
which does not change SeqOps.cpp; all 14 still crash on main. The input parses
and verifies; the pass crashes.

## Reproducer (`repro.mlir`)

```mlir
module {
  hw.generator.schema @FIRRTLMem, "FIRRTL_Memory", ["depth", "numReadPorts", "numWritePorts", "numReadWritePorts", "readLatency", "writeLatency", "width", "readUnderWrite", "writeUnderWrite", "writeClockIDs", "initFilename", "initIsBinary", "initIsInline"] {sym_visibility = "private"}
  hw.module.generated private @FIRRTLMem_1_1_0_32_16_1_1_0_1_a, @FIRRTLMem() attributes {depth = 16 : i64, initFilename = "", initIsBinary = false, initIsInline = false, maskGran = 8 : ui32, numReadPorts = 1 : ui32, numReadWritePorts = 0 : ui32, numWritePorts = 1 : ui32, readLatency = 1 : ui32, readUnderWrite = 0 : i0, width = 32 : ui32, writeClockIDs = [0 : i32], writeLatency = 1 : ui32, writeUnderWrite = 1 : i32}
}
```

## Command

```sh
circt-opt repro.mlir -hw-memory-sim
```

## Result

`circt-opt repro.mlir` alone exits 0. With `-hw-memory-sim`, a segmentation
fault: `seq::FirMemory::FirMemory` calls
`getAttrOfType<seq::RUWAttr>("readUnderWrite").getValue()` (and the same for
`WUWAttr`) without checking for null; `0 : i0` is no `RUWAttr`.

```text
 #6 circt::seq::RUWAttr::getValue() const
 #7 circt::seq::FirMemory::FirMemory(circt::hw::HWModuleGeneratedOp) lib/Dialect/Seq/SeqOps.cpp:1138
```

## CIRCT SHA

- main: `4738bd2685a1bed0f44623ad1a800146a0d8c43c`, checked on a build of main plus 13 local fixes that touch none of the files involved (CombToSynth, CoreToFSM, MooreToCore, Comb, DC, Moore, OM only)
- also at: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce` (firtool-1.159.0), where it was found
