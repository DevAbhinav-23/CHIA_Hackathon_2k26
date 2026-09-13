#!/bin/bash
W=/home/adi/.cache/chia-pin-smoke
SRC=$W/src; OPT=$SRC/build/bin/circt-opt; FC=$W/circt-sdk/bin/FileCheck
TEST=test/Conversion/HWToLLVM/convert_aggregates.mlir
SRCF=lib/Conversion/HWToLLVM/HWToLLVM.cpp
FIX=f2b15a44ec70f99fbc2a36f0de1b99d6c0f48af3
export LD_LIBRARY_PATH=$W/circt-sdk/lib:$W/shim
cd $SRC
run(){ if $OPT $TEST --split-input-file --convert-hw-to-llvm=spill-arrays-early=false 2>$W/opt.err | $FC $TEST >$W/fc.out 2>&1; then echo "$1: PASS"; else echo "$1: FAIL"; sed -n '1,5p' $W/fc.out; fi; }
git checkout -q -- $TEST $SRCF
echo "=== source at bug parent $(git rev-parse --short HEAD); fix commit $FIX ==="
echo "[1] pass-to-pass: OLD test on BUGGY source"; run "    result"
echo "[2] fail-to-pass PRECONDITION: NEW test on BUGGY source (expect FAIL)"
git show $FIX:$TEST > $TEST; run "    result"
echo "[3] apply source fix + incremental rebuild"
git show $FIX:$SRCF > $SRCF
T0=$(date +%s); /usr/bin/ninja -C build -j6 circt-opt > $W/rebuild.log 2>&1; RC=$?
echo "    rebuild rc=$RC wall=$(( $(date +%s) - T0 ))s ; $(tail -1 $W/rebuild.log)"
echo "[4] fail-to-pass POSTCONDITION: NEW test on FIXED source (expect PASS)"; run "    result"
git checkout -q -- $TEST $SRCF
