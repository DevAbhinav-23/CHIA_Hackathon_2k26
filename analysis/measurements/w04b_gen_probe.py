#!/usr/bin/env python3
"""W-04b: regenerate M2's 4,000-operation probe (raw/bench-big.mlir).

No generator script was stored with M2; this one reproduces the artefact
byte for byte (verified by sha256 against raw/bench-big.mlir).
"""
import sys
OPS = ["add", "mul", "and", "or", "xor"]
out = ["hw.module @Big(in %a : i32, in %b : i32, out z : i32) {"]
out.append("  %0 = comb.add %a, %b : i32")
for i in range(1, 4000):
    out.append("  %%%d = comb.%s %%%d, %%b : i32" % (i, OPS[i % 5], i - 1))
out.append("  hw.output %3999 : i32")
out.append("}")
sys.stdout.write("\n".join(out) + "\n")
