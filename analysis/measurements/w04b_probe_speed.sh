#!/bin/bash
# W-04b: per-probe cost on M2's 4,000-operation probe, 20 reps, MEDIAN wall time.
# The probe is bind-mounted at /probe/bench-big.mlir; it is byte-identical to
# M2's raw/bench-big.mlir (w04b_gen_probe.py regenerates it).
set -u
B=/workspace/circt/build/bin
IN=/probe/bench-big.mlir
REPS=${REPS:-20}
echo "### flags: ${BUGLOOP_CXX_FLAGS_RELEASE:-(unset)}"
echo "### input: $(wc -l < $IN) lines, sha256 $(sha256sum $IN | cut -d' ' -f1)"
echo "### circt-opt: $(stat -c %s $B/circt-opt) bytes"
run () {   # $1 = label, rest = argv
  local label=$1; shift
  local us=() s e i
  for i in $(seq 1 "$REPS"); do
    s=$(date +%s%N); "$@" >/dev/null 2>&1; e=$(date +%s%N)
    us+=( $(( (e-s)/1000 )) )
  done
  printf '%s\n' "${us[@]}" | sort -n > /tmp/reps.txt
  local med min max
  med=$(awk 'NR==FNR{n++;next}{a[FNR]=$1}END{print (n%2)?a[(n+1)/2]:int((a[n/2]+a[n/2+1])/2)}' /tmp/reps.txt /tmp/reps.txt)
  min=$(head -1 /tmp/reps.txt); max=$(tail -1 /tmp/reps.txt)
  printf "%-46s reps=%d median=%d us  min=%d us  max=%d us\n" "$label" "$REPS" "$med" "$min" "$max"
  echo "  all (sorted, us): $(tr '\n' ' ' < /tmp/reps.txt)"
}
run "circt-opt --canonicalize --cse bench-big.mlir" $B/circt-opt --canonicalize --cse "$IN"
run "circt-opt --version" $B/circt-opt --version
