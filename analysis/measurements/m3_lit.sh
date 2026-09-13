#!/bin/bash
# M3 (A-04, red-team WOUND 6, FR-07.9): the whole test/ tree under CHIA's own lit
# exclusions, run against the assertions-ON build and the assertions-OFF build of the
# SAME source tree.  The difference between the two failing sets is the assertion
# false-positive set.
#
# CHIA's exclusions, from chia:examples/circt_issue_solver/circt_util.py:151-159 --
#   _LIT_GATE_EXCLUDE_DIRS = ("CAPI",)      -> drop test/CAPI entirely
#   _LIT_GATE_FILTER_OUT   = "circt-tblgen" -> lit --filter-out=circt-tblgen
# and chia:chia/chipyard/circt.py:698-762 -- lit --no-progress-bar --filter-out=... <paths>
# run with cwd = the build directory.
set -u
SMOKE=$HOME/.cache/chia-pin-smoke
SRC=$SMOKE/src
SDK=$SMOKE/circt-sdk
LIT=$SMOKE/venv/bin/lit
OUT=/home/adi/Projects/chia-hackathon/analysis/measurements/raw
JOBS=12
export LD_LIBRARY_PATH=$SDK/lib:$SMOKE/shim${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

# circt_lit_gate_paths(): every top-level test/<dir> except CAPI.
# ATTEMPT 1 (raw/m3-driver-attempt1.log) ran CHIA's rule verbatim and lit exited 2
# before running a single test: test/Tools/circt-tblgen/lit.local.cfg raises during
# DISCOVERY, and --filter-out only applies after discovery. So the second attempt
# expands test/Tools into its subdirectories minus circt-tblgen, which is the only
# way to realise CHIA's stated intent. Everything else is unchanged.
PATHS=()
for d in $(ls "$SRC/test"); do
  [ -d "$SRC/test/$d" ] || continue
  [ "$d" = "CAPI" ] && continue
  if [ "$d" = "Tools" ]; then
    for t in $(ls "$SRC/test/Tools"); do
      [ -d "$SRC/test/Tools/$t" ] || continue
      [ "$t" = "circt-tblgen" ] && continue
      PATHS+=("test/Tools/$t")
    done
    continue
  fi
  PATHS+=("test/$d")
done
echo "gate paths (${#PATHS[@]}): ${PATHS[*]}"

run_lit () {   # $1 = build dir, $2 = tag
  local B=$1 TAG=$2 T
  echo "=== lit on $B ($TAG) start $(date -Is) ==="
  T=$SECONDS
  ( cd "$B" && "$LIT" --no-progress-bar --filter-out=circt-tblgen -j$JOBS "${PATHS[@]}" ) \
    > "$OUT/m3-lit-$TAG.txt" 2>&1
  echo "lit rc=$? wall=$((SECONDS-T))s"
  grep -E '^(FAIL|UNRESOLVED|TIMEOUT|XPASS):' "$OUT/m3-lit-$TAG.txt" \
    | sed 's/^[A-Z]*: //' | sed 's/ ([0-9]* of [0-9]*)$//' | sort > "$OUT/m3-fail-$TAG.txt"
  echo "--- summary ($TAG) ---"
  sed -n '/^Testing Time/,$p' "$OUT/m3-lit-$TAG.txt" | grep -E '^[A-Za-z ]+ *:' 
  echo "failing entries: $(wc -l < "$OUT/m3-fail-$TAG.txt")"
}

echo "### commit: $(git -C "$SRC" log -1 --format=%H 2>/dev/null || echo n/a)"
echo "### lit: $($LIT --version)"

run_lit "$SMOKE/bassert_g" "bassert_g"

echo "=== building the same five targets in the assertions-OFF build $(date -Is) ==="
T=$SECONDS
ninja -C "$SMOKE/src/build" -j$JOBS circt-opt firtool circt-translate arcilator circt-reduce \
  > "$OUT/m3-ndebug-build.log" 2>&1
echo "ndebug build rc=$? wall=$((SECONDS-T))s"
grep -c '^\[' "$OUT/m3-ndebug-build.log" | sed 's/^/edges run: /'

run_lit "$SMOKE/src/build" "ndebug"

echo "=== difference ==="
comm -23 "$OUT/m3-fail-bassert_g.txt" "$OUT/m3-fail-ndebug.txt" > "$OUT/m3-fail-assert-only.txt"
comm -13 "$OUT/m3-fail-bassert_g.txt" "$OUT/m3-fail-ndebug.txt" > "$OUT/m3-fail-ndebug-only.txt"
comm -12 "$OUT/m3-fail-bassert_g.txt" "$OUT/m3-fail-ndebug.txt" > "$OUT/m3-fail-both.txt"
echo "fail on BOTH (missing-binary / pre-existing): $(wc -l < "$OUT/m3-fail-both.txt")"
echo "fail ONLY with assertions ON  (= assertion false positives): $(wc -l < "$OUT/m3-fail-assert-only.txt")"
cat "$OUT/m3-fail-assert-only.txt"
echo "fail ONLY with assertions OFF: $(wc -l < "$OUT/m3-fail-ndebug-only.txt")"
cat "$OUT/m3-fail-ndebug-only.txt"
echo "M3 DONE"
