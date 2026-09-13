#!/bin/bash
# M2 follow-on (A-03's "per-probe slowdown"): one circt-opt probe under each of the three
# flag strings.  Same input, same pipeline, same compiler, same machine; best of N, which
# is the right statistic for a lower bound on cost.
set -u
SMOKE=$HOME/.cache/chia-pin-smoke
export LD_LIBRARY_PATH=$SMOKE/circt-sdk/lib:$SMOKE/shim
IN=${1:?usage: m2_probe_speed.sh <input.mlir> [circt-opt args...]}
shift
REPS=${REPS:-9}
for tag in bassert_n:'-O3 -DNDEBUG' bassert_u:'-O3 -UNDEBUG' bassert_g:'-O3 -UNDEBUG -gline-tables-only'; do
  d=${tag%%:*}; label=${tag#*:}
  bin=$SMOKE/$d/bin/circt-opt
  [ -x "$bin" ] || { echo "$label: no binary at $bin"; continue; }
  best=99999999
  for i in $(seq $REPS); do
    s=$(date +%s%N); "$bin" "$@" "$IN" > /dev/null 2>&1; e=$(date +%s%N)
    us=$(( (e-s)/1000 )); [ $us -lt $best ] && best=$us
  done
  printf "%-34s %-20s best-of-%d %8d us\n" "$label" "$(basename "$IN")" "$REPS" "$best"
done
