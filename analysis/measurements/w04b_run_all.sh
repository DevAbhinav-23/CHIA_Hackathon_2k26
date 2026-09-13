#!/bin/bash
# W-04b driver: the same three in-image scripts against both images, then the comm.
set -u
M=/home/adi/Projects/chia-hackathon/analysis/measurements
OUT=$M/raw
ON=chia-circt-assert:eade0de61bc5      # -O3 -UNDEBUG -gline-tables-only
OFF=chia-circt-ndebug:eade0de61bc5     # -O3 -DNDEBUG -gline-tables-only
RUN="docker run --rm -i -v $OUT:/probe:ro"

for pair in "assert:$ON" "ndebug:$OFF"; do
  name=${pair%%:*}; img=${pair#*:}
  echo "=== $name ($img): sizes ==="
  $RUN "$img" bash -l -s < "$M/w04b_sizes.sh" > "$OUT/w04b-sizes-$name.txt" 2>&1
  echo "rc=$?  -> raw/w04b-sizes-$name.txt"
  echo "=== $name: lit ==="
  $RUN "$img" bash -l -s < "$M/w04b_lit_runs.sh" > "$OUT/w04b-lit-$name.txt" 2>&1
  echo "rc=$?  -> raw/w04b-lit-$name.txt"
done

# the two failing-name sets, gate scope and FRD slice
for name in assert ndebug; do
  for scope in GATE SLICE; do
    s=$(echo "$scope" | tr 'A-Z' 'a-z')
    awk "/^### FAILSET-$scope-BEGIN\$/{f=1;next} /^### FAILSET-$scope-END\$/{f=0} f" \
      "$OUT/w04b-lit-$name.txt" | sed '/^$/d' | sort > "$OUT/w04b-failset-$s-$name.txt"
  done
done

echo
echo "=== failing-name sets, CHIA gate scope ==="
for name in assert ndebug; do
  echo "$name: $(wc -l < "$OUT/w04b-failset-gate-$name.txt") entries"
done
echo "--- comm -3 --output-delimiter=| (col1 = assert-only = the false positives, col2 = ndebug-only) ---"
comm "$OUT/w04b-failset-gate-assert.txt" "$OUT/w04b-failset-gate-ndebug.txt" \
  --output-delimiter='|' | tee "$OUT/w04b-comm-gate.txt"
echo "assert-only (FR-07.9 / A-20 false-positive set): $(comm -23 "$OUT/w04b-failset-gate-assert.txt" "$OUT/w04b-failset-gate-ndebug.txt" | wc -l)"
echo "ndebug-only:                                     $(comm -13 "$OUT/w04b-failset-gate-assert.txt" "$OUT/w04b-failset-gate-ndebug.txt" | wc -l)"
echo "both:                                            $(comm -12 "$OUT/w04b-failset-gate-assert.txt" "$OUT/w04b-failset-gate-ndebug.txt" | wc -l)"

echo
echo "=== probes (serial, nothing else running) ==="
for pair in "assert:$ON" "ndebug:$OFF"; do
  name=${pair%%:*}; img=${pair#*:}
  $RUN "$img" bash -l -s < "$M/w04b_probe_speed.sh" > "$OUT/w04b-probe-$name.txt" 2>&1
  echo "$name rc=$? -> raw/w04b-probe-$name.txt"
done
echo "W04B RUN-ALL DONE $(date -Is)"
