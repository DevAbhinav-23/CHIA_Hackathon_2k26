#!/bin/bash
# M7 part 2: SDK circt-verilog --ir-moore vs the new slang build's, on one .sv seed test file.
# Seed file: test/circt-verilog/roundtrip-oob-reads.sv at seed commit cc71d34ab52f
# (first row of raw/m1-per-seed.csv), fetched into raw/m7-seed.sv.
set -u
SMOKE=$HOME/.cache/chia-pin-smoke
SDK=$SMOKE/circt-sdk
B=$SMOKE/bslang
OUT=/home/adi/Projects/chia-hackathon/analysis/measurements/raw
SEED=$OUT/m7-seed.sv
export LD_LIBRARY_PATH=$SDK/lib:$SMOKE/shim${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

run () {  # $1 = label, $2 = binary
  echo "=== $1 : $2 ==="
  if [ ! -x "$2" ]; then echo "  MISSING BINARY"; return; fi
  "$2" --ir-moore "$SEED" > "$OUT/m7-irmoore-$1.mlir" 2> "$OUT/m7-irmoore-$1.err"
  echo "  rc=$?  stdout_bytes=$(stat -c %s "$OUT/m7-irmoore-$1.mlir")  stderr_bytes=$(stat -c %s "$OUT/m7-irmoore-$1.err")"
  echo "  moore.module count: $(grep -c 'moore.module' "$OUT/m7-irmoore-$1.mlir")"
  echo "  first 3 stdout lines:"; head -3 "$OUT/m7-irmoore-$1.mlir" | sed 's/^/    /'
  echo "  first 5 stderr lines:"; head -5 "$OUT/m7-irmoore-$1.err" | sed 's/^/    /'
}

echo "seed: $SEED ($(wc -l < "$SEED") lines)"
run sdk "$SDK/bin/circt-verilog"
run bslang "$B/bin/circt-verilog"
echo "=== diff of the two Moore IRs ==="
if [ -s "$OUT/m7-irmoore-sdk.mlir" ] && [ -s "$OUT/m7-irmoore-bslang.mlir" ]; then
  if diff -q "$OUT/m7-irmoore-sdk.mlir" "$OUT/m7-irmoore-bslang.mlir" >/dev/null; then
    echo "  byte-identical"
  else
    echo "  differ; $(diff "$OUT/m7-irmoore-sdk.mlir" "$OUT/m7-irmoore-bslang.mlir" | wc -l) diff lines"
    diff "$OUT/m7-irmoore-sdk.mlir" "$OUT/m7-irmoore-bslang.mlir" | head -20 | sed 's/^/    /'
  fi
fi
echo "M7 COMPARE DONE $(date -Is)"
