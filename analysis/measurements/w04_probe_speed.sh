#!/bin/bash
# W-04 / A-03: per-probe cost inside a container of the assertions-on image.
# Absolute numbers only: no -DNDEBUG image exists to take a delta against.
set -u
B=/workspace/circt/build/bin
python3 - <<'EOF' > /tmp/big.mlir
print("hw.module @t(in %a : i32, in %b : i32, out o : i32) {")
print("  %0 = comb.add %a, %b : i32")
for i in range(1, 4000):
    print("  %%%d = comb.add %%%d, %%b : i32" % (i, i-1))
print("  hw.output %3999 : i32")
print("}")
EOF
echo "input: $(wc -l < /tmp/big.mlir) lines"
best () {  # $1 = reps, rest = argv
  local reps=$1; shift
  local m=999999999 s e d
  for _ in $(seq 1 "$reps"); do
    s=$(date +%s%N); "$@" >/dev/null 2>&1; e=$(date +%s%N)
    d=$(( (e-s)/1000 )); [ $d -lt $m ] && m=$d
  done
  echo "$((m/1000)).$((m%1000)) ms"
}
echo -n "circt-opt --version, best of 15:                        "
best 15 $B/circt-opt --version
echo -n "4000 comb ops, --canonicalize --cse, best of 9:         "
best 9 $B/circt-opt --canonicalize --cse /tmp/big.mlir

echo
echo "FR-07.4: does a symbolised frame name a CIRCT source file and line?"
addr=$(nm --defined-only $B/circt-opt | grep " T _ZN5circt10chooseName" | head -1 | cut -d' ' -f1)
echo "addr=0x$addr"
echo 0x$addr | /opt/circt-sdk/bin/llvm-symbolizer --obj=$B/circt-opt --demangle
