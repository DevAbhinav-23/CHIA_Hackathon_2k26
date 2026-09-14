# circt-opt crashes in LowerTypes on a zero-width aggregate

## What happens
`circt-opt --lower-seq-to-sv` fails an assertion on the reduced input below.

## Reduced input
```mlir
hw.module @bugloop(in %a : i4, out b : i4) {
  hw.output %a : i4
}
```

## Build identity
Built with -UNDEBUG, so the compiler's internal checks are on.

## Fingerprint
op && "null op"
LowerTypes.cpp:412

Assisted-by: circt_bug_loop:vertex:gemini-3.8-flash
