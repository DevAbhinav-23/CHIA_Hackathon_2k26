#!/bin/sh
# A stand-in CIRCT tool that refuses an op of its OWN making and exits 1, which
# is contract 2.4's `verifier_error` (D-13). Run as §4.8's parse-and-verify
# command - `-o /dev/null <case>` - it accepts the input, which is the whole
# point: the input is valid and the tool's output is not.
[ "$1" = "--version" ] && { echo "CIRCT firtool-1.143.0"; exit 0; }
[ "$1" = "-o" ] && exit 0
echo "case.mlir:2:8: error: 'comb.extract' op result #0 must be a signless integer bitvector, but got '!hw.array<2xi2>'" >&2
exit 1
