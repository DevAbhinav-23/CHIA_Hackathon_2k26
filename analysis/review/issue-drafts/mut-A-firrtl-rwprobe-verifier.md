# [FIRRTL] Verifier segfault in RWProbeOp::verifyInnerRefs when a firrtl.ref.rwprobe sits outside a module

**Status: draft, not filed.** Found by the mutation-based baseline of a fuzzing
loop (syntactic mutation of CIRCT regression tests, no LLM); reduced
automatically and re-checked on current main. Candidate `c-p-f7f76df77af7`
(16 candidates from 4 seeds share this crash). The input is invalid IR (the
rwprobe is outside any module); the verifier should reject it with a
diagnostic instead of crashing.

## Reproducer (`repro.mlir`)

```mlir
firrtl.circuit "InnerSymPortTarget" {
  firrtl.module private @Foo0(in %in : !firrtl.uint<1> sym @sym) {
  }
    %0 = firrtl.ref.rwprobe <@Foo1::@sym>: !firrtl.rwprobe<uint<1>>
  firrtl.module @InnerSymPortTarget() {
  }
}
```

## Command

```sh
circt-opt repro.mlir
```

(Parsing alone crashes: the parser's verification calls `verifyInnerRefNamespace`.)

## Result

Segmentation fault. `RWProbeOp::verifyInnerRefs` calls
`getParentOfType<FModuleLike>()`, which is null here, then `getModuleNameAttr()` on it.

```text
 #4 circt::firrtl::FModuleLike::getModuleNameAttr()
 #8 circt::firrtl::RWProbeOp::verifyInnerRefs(circt::hw::InnerRefNamespace&) lib/Dialect/FIRRTL/FIRRTLOps.cpp:6997
 #9 ...InnerRefUserOpInterfaceInterfaceTraits::Model<circt::firrtl::RWProbeOp>::verifyInnerRefs
```

## CIRCT SHA

- main: `4738bd2685a1bed0f44623ad1a800146a0d8c43c`, checked on a build of main plus 13 local fixes that touch none of the files involved (CombToSynth, CoreToFSM, MooreToCore, Comb, DC, Moore, OM only)
- also at: `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce` (firtool-1.159.0), where it was found
