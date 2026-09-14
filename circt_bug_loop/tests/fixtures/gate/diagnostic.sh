#!/bin/sh
# A stand-in check that rejects its input with an ordinary diagnostic and a
# clean non-zero exit, which is FR-13.15's `invalid_input`.
[ "$1" = "--version" ] && { echo "CIRCT firtool-1.143.0"; exit 0; }
echo "error: expected SSA operand" >&2
exit 1
