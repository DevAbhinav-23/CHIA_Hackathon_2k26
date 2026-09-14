#!/bin/sh
# A stand-in check that accepts its input: exit 0, which is FR-13.15's pass.
[ "$1" = "--version" ] && { echo "CIRCT firtool-1.143.0"; exit 0; }
exit 0
