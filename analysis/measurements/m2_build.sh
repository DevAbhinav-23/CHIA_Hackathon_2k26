#!/bin/bash
# M2 (A-03, D-08, K2): -O3 -UNDEBUG -gline-tables-only build of FR-03.7's target set.
set -u
SMOKE=$HOME/.cache/chia-pin-smoke
SRC=$SMOKE/src
SDK=$SMOKE/circt-sdk
B=$SMOKE/bassert_g
OUT=/home/adi/Projects/chia-hackathon/analysis/measurements/raw
JOBS=12
CXX=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang++
CC=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang
# C-02: the SDK binaries (mlir-tblgen, llvm-min-tblgen) need libz3.so.4 via the shim.
export LD_LIBRARY_PATH=$SDK/lib:$SMOKE/shim${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}

ccache -s > "$OUT/m2-ccache-before.txt" 2>&1
echo "host: $(uname -srm)  nproc=$(nproc)  jobs=$JOBS"
echo "src commit: $(git -C "$SRC" log -1 --format=%H 2>/dev/null || echo '(not a repo)')"

echo "=== configure start $(date -Is) ==="
T0=$SECONDS
cmake -G Ninja -S "$SRC" -B "$B" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER="$CXX" \
  -DCMAKE_C_COMPILER="$CC" \
  -DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
  -DCMAKE_C_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
  -DLLVM_DIR="$SDK/lib/cmake/llvm" \
  -DMLIR_DIR="$SDK/lib/cmake/mlir" \
  -DLLVM_ENABLE_ASSERTIONS=ON \
  -DLLVM_USE_LINKER=lld \
  -DLLVM_CCACHE_BUILD=ON \
  -DLLVM_PARALLEL_LINK_JOBS=2 \
  > "$OUT/m2-configure.log" 2>&1
RC=$?
echo "configure rc=$RC wall=$((SECONDS-T0))s"

echo "=== target count ==="
ninja -C "$B" -n circt-opt firtool circt-translate arcilator circt-reduce 2>/dev/null | wc -l | tee "$OUT/m2-targetcount.txt"

echo "=== build start $(date -Is) (-j$JOBS) ==="
T1=$SECONDS
ninja -C "$B" -j$JOBS circt-opt firtool circt-translate arcilator circt-reduce \
  > "$OUT/m2-build.log" 2>&1
RC=$?
echo "build rc=$RC wall=$((SECONDS-T1))s  end $(date -Is)"
ccache -s > "$OUT/m2-ccache-after.txt" 2>&1
echo "DONE total=$((SECONDS-T0))s"
