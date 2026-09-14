#!/bin/sh
# The same tool firing a DIFFERENT assertion: the recorded failure did not
# reproduce, which is gate question 1's `no`. 04-Test-Plan.md T-U-gate-05.
[ "$1" = "--version" ] && { echo "CIRCT firtool-1.143.0"; exit 0; }
echo "/workspace/circt/lib/Dialect/Seq/SeqOps.cpp:77: void circt::seq::check(): Assertion \`width > 0 && \"zero width\"' failed." >&2
kill -ABRT $$
