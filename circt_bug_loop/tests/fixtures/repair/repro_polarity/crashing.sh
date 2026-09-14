#!/bin/sh
# A stand-in for a CIRCT tool that STILL CRASHES on the reduced case: it prints
# glibc's own assertion line and dies by SIGABRT, which is 128+6 to the shell.
# 04-Test-Plan.md T-U-repair-03. It is a shell script and not a binary, so the
# test runs at T0; FR-12.3's acceptance asks only that the polarity is exercised
# against a still-crashing and a diagnosing tool.
[ "$1" = "--version" ] && { echo "CIRCT fixture-tool"; exit 0; }
echo "Foo.cpp:412: void circt::foo(mlir::Operation *): Assertion \`op && \"null op\"' failed." >&2
kill -ABRT $$
