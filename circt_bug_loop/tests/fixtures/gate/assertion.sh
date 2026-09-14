#!/bin/sh
# A stand-in CIRCT tool that fires the recorded assertion and dies by SIGABRT.
# 04-Test-Plan.md T-U-gate-01, -05, -11. A shell script, not a binary: the
# question the gate asks is about the recorded class, text and site, and those
# are read off stderr whatever produced them.
[ "$1" = "--version" ] && { echo "CIRCT firtool-1.143.0"; exit 0; }
echo "/workspace/circt/lib/Dialect/HW/HWOps.cpp:412: void circt::hw::verify(mlir::Operation *): Assertion \`op && \"null op\"' failed." >&2
kill -ABRT $$
