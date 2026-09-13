#!/bin/bash
# One W-09 attempt (04-Test-Plan.md 5.1): build the RUN line's tool at the
# seed's first parent, run the seed's own test input there, classify with
# w09_oracle.py while the binary is still at the parent, then rebuild at the
# seed and run again.  Confirmed = fires at the parent, does not at the seed.
#
#   w09_attempt.sh <name> <seed> <parent> <testpath> <tag> <wt> <build> <sdk> [tool-target]
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
source "$HERE/w09_lib.sh"
NAME=$1 SEED=$2 PARENT=$3 TESTPATH=$4 TAG=$5 WT=$6 B=$7 SDK=$8
TARGET=${9:-circt-opt}
A=$W09/attempts/$NAME
mkdir -p "$A"

EXT=${TESTPATH##*.}
INPUT=$A/input.$EXT
git -C "$WT" show "$SEED:$TESTPATH" > "$INPUT" || { echo "no $TESTPATH at $SEED"; exit 1; }
cat > "$A/meta.json" <<EOF
{"name": "$NAME", "seed": "$SEED", "parent": "$PARENT", "test_path": "$TESTPATH",
 "sdk_tag": "$TAG", "target": "$TARGET", "worktree": "$WT", "build": "$B", "sdk": "$SDK"}
EOF

echo "=== attempt $NAME  seed=${SEED:0:12} parent=${PARENT:0:12} tag=$TAG target=$TARGET"
: > "$A/timings.txt"
for WHICH in parent seed; do
  SHA=$PARENT; [ "$WHICH" = seed ] && SHA=$SEED
  git -C "$WT" checkout --detach -q "$SHA" || { echo "checkout FAILED $SHA"; exit 1; }
  T0=$SECONDS
  build "$B" "$SDK" "$TARGET" > "$A/build-$WHICH.log" 2>&1
  RC=$?
  echo "$WHICH build rc=$RC wall=$((SECONDS-T0))s edges=$(grep -c '^\[' "$A/build-$WHICH.log")" \
    | tee -a "$A/timings.txt"
  [ $RC -ne 0 ] && { echo "BUILD FAILED at $WHICH"; tail -20 "$A/build-$WHICH.log"; exit 1; }
  python3 "$HERE/w09_runner.py" --input "$INPUT" --bin "$B/bin" --sdk "$SDK" \
          --out "$A" --tag "$WHICH" || exit 1
  # Symbolise only while the binary is the one that produced the trace.
  for D in "$A/$WHICH"-p*/; do
    python3 "$HERE/w09_oracle.py" "$D/stderr.txt" "$D/run.json" \
      --sdk "$SDK" --build "$B" --src "$WT" > "$D/oracle.json"
  done
done
python3 - "$A" <<'EOF'
import json, sys, glob, os
a = sys.argv[1]
for d in sorted(glob.glob(os.path.join(a, "*-p*/"))):
    o = json.load(open(os.path.join(d, "oracle.json")))
    print(f"  {os.path.basename(d.rstrip('/')):14s} fired={str(o['fired']):5s} "
          f"class={o['status']:12s} sig={o['signal']} frame={o['fingerprint_frame']}")
EOF
echo "=== $NAME done"
