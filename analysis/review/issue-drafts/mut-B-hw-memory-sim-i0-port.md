# [HWMemSim] -hw-memory-sim emits invalid sv.always / comb.mux for a FIRRTLMem with an i0 clock or enable port

**Status: draft, not filed.** Found by the mutation-based baseline of a fuzzing
loop (syntactic mutation of CIRCT regression tests, no LLM); reduced
automatically and re-checked on current main. Candidate `c-p-02ce3b41ed9c`
(11 candidates from one seed: 9 `sv.always`, 2 `comb.mux` with an `i0`
read-enable port). The input parses and verifies; the pass output does not.
Related but different: open issue #9998 (SIGFPE on a zero-width *data* memory).

## Reproducer (`repro.mlir`)

```mlir
module {
  hw.generator.schema @FIRRTLMem, "FIRRTL_Memory", ["depth", "numReadPorts", "numWritePorts", "numReadWritePorts", "readLatency", "writeLatency", "width", "readUnderWrite", "writeUnderWrite", "writeClockIDs", "initFilename", "initIsBinary", "initIsInline"] {sym_visibility = "private"}
  hw.module.generated private @ReadWriteWithHighReadLatency, @FIRRTLMem(in %rw_addr : i4, in %rw_en : i1, in %rw_clock : i0, in %rw_wmode : i1, in %rw_wdata : i16) attributes {depth = 16 : i64, initFilename = "", initIsBinary = false, initIsInline = false, numReadPorts = 0 : ui32, numReadWritePorts = 1 : ui32, numWritePorts = 0 : ui32, readLatency = 4 : ui32, readUnderWrite = 0 : i32, width = 16 : ui32, writeClockIDs = [], writeLatency = 3 : ui32, writeUnderWrite = 0 : i32}
}
```

## Command

```sh
circt-opt repro.mlir -hw-memory-sim
```

## Result

`circt-opt repro.mlir` alone exits 0. With `-hw-memory-sim`:

```text
repro.mlir:3:3: error: 'sv.always' op operand #0 must be variadic of 1-bit signless integer, but got 'i0'
```

`HWMemSimImpl` takes the clock and enable port types of the generated memory
on trust; it should reject non-`i1` clock/enable ports with a diagnostic.

## CIRCT SHA

- main: `4738bd2685a1bed0f44623ad1a800146a0d8c43c`, checked on a build of main plus 13 local fixes that touch none of the files involved (CombToSynth, CoreToFSM, MooreToCore, Comb, DC, Moore, OM only)
- also at: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce` (firtool-1.159.0), where it was found
