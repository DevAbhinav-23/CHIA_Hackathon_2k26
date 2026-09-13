#!/bin/bash
# W-04: the two lit runs, inside the image.
#   1. the assertions-on slice the FRD names (FR-03.6's reference measurement)
#   2. CHIA's own gate scope, verbatim from circt_lit_gate_paths() (FR-07.9)
set -u
SRC=/workspace/circt
B=$SRC/build
J=${LIT_JOBS:-8}

echo "### lit: $(lit --version)"
echo "### commit: $(git -C $SRC rev-parse HEAD)"

echo
echo "=== RUN 1: the FRD slice, test/Dialect/{FIRRTL,HW,Comb,Seq} + test/Conversion ==="
SLICE=(test/Dialect/FIRRTL test/Dialect/HW test/Dialect/Comb test/Dialect/Seq test/Conversion)
T=$SECONDS
( cd "$B" && lit --no-progress-bar --filter-out=circt-tblgen -j$J "${SLICE[@]}" ) \
  > /tmp/lit-slice.txt 2>&1
echo "rc=$? wall=$((SECONDS-T))s"
sed -n '/^Testing Time/,$p' /tmp/lit-slice.txt
echo "--- failing entries ---"
grep -E '^(FAIL|UNRESOLVED|TIMEOUT|XPASS):' /tmp/lit-slice.txt | sed 's/ ([0-9]* of [0-9]*)$//' | sort

echo
echo "=== RUN 2: CHIA's gate scope verbatim (circt_lit_gate_paths + --filter-out=circt-tblgen) ==="
PATHS=()
for d in $(ls "$SRC/test"); do
  [ -d "$SRC/test/$d" ] || continue
  [ "$d" = "CAPI" ] && continue
  PATHS+=("test/$d")
done
echo "gate paths (${#PATHS[@]}): ${PATHS[*]}"
T=$SECONDS
( cd "$B" && lit --no-progress-bar --filter-out=circt-tblgen -j$J "${PATHS[@]}" ) \
  > /tmp/lit-full.txt 2>&1
echo "rc=$? wall=$((SECONDS-T))s"
sed -n '/^Testing Time/,$p' /tmp/lit-full.txt
echo "--- discovery errors ---"
grep -c "unable to parse config file" /tmp/lit-full.txt
echo "--- failing entries ---"
grep -E '^(FAIL|UNRESOLVED|TIMEOUT|XPASS):' /tmp/lit-full.txt | sed 's/ ([0-9]* of [0-9]*)$//' | sort
echo "--- unsupported, by reason head ---"
grep -c '^UNSUPPORTED:' /tmp/lit-full.txt
