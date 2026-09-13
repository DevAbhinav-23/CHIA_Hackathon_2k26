#!/bin/bash
# W-04b: the two lit runs, inside whichever image this is piped into.
# Identical scope, filter and -j to W-04's w04_lit_runs.sh; the only addition is
# machine-readable markers around the two failing-name sets so they can be comm'd.
set -u
SRC=/workspace/circt
B=$SRC/build
J=${LIT_JOBS:-8}

echo "### lit: $(lit --version)"
echo "### commit: $(git -C $SRC rev-parse HEAD)"
echo "### flags: ${BUGLOOP_CXX_FLAGS_RELEASE:-(unset)}"

echo
echo "=== RUN 1: the FRD slice, test/Dialect/{FIRRTL,HW,Comb,Seq} + test/Conversion ==="
SLICE=(test/Dialect/FIRRTL test/Dialect/HW test/Dialect/Comb test/Dialect/Seq test/Conversion)
T=$SECONDS
( cd "$B" && lit --no-progress-bar --filter-out=circt-tblgen -j$J "${SLICE[@]}" ) \
  > /tmp/lit-slice.txt 2>&1
echo "rc=$? wall=$((SECONDS-T))s"
sed -n '/^Testing Time/,$p' /tmp/lit-slice.txt
echo "### FAILSET-SLICE-BEGIN"
grep -E '^(FAIL|UNRESOLVED|TIMEOUT|XPASS):' /tmp/lit-slice.txt | sed 's/ ([0-9]* of [0-9]*)$//' | sort
echo "### FAILSET-SLICE-END"

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
echo "--- discovery errors (unable to parse config file) ---"
grep -c "unable to parse config file" /tmp/lit-full.txt
echo "--- UNSUPPORTED count ---"
grep -c '^UNSUPPORTED:' /tmp/lit-full.txt
echo "### FAILSET-GATE-BEGIN"
grep -E '^(FAIL|UNRESOLVED|TIMEOUT|XPASS):' /tmp/lit-full.txt | sed 's/ ([0-9]* of [0-9]*)$//' | sort
echo "### FAILSET-GATE-END"
