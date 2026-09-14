#!/bin/sh
# The same tool PATCHED so that the crash became an ordinary diagnostic: it
# rejects the input with an error message and exits 1. FR-12.3 scores this as
# FIXED, which is exactly the case the naive `exit_code == 0` script gets wrong.
# 04-Test-Plan.md T-U-repair-04.
[ "$1" = "--version" ] && { echo "CIRCT fixture-tool"; exit 0; }
echo "$1:1:1: error: 'foo.bar' op operand #0 must be a signless integer" >&2
exit 1
