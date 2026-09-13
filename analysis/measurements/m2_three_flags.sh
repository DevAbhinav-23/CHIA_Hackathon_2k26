#!/bin/bash
# M2 follow-on for A-03: the SAME five targets, the SAME source tree, the SAME compiler,
# built under the three flag strings A-03 names, so the -gline-tables-only delta is not
# confounded by a different compiler or a different target set.
set -u
SMOKE=$HOME/.cache/chia-pin-smoke
SRC=$SMOKE/src; SDK=$SMOKE/circt-sdk
OUT=/home/adi/Projects/chia-hackathon/analysis/measurements/raw
JOBS=12
CXX=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang++
CC=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang
export LD_LIBRARY_PATH=$SDK/lib:$SMOKE/shim${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
TARGETS="circt-opt firtool circt-translate arcilator circt-reduce"

build () {   # $1 = dir suffix, $2 = flags
  local B=$SMOKE/$1 F=$2 T
  echo "=== $1 : CMAKE_CXX_FLAGS_RELEASE='$F' ==="
  rm -rf "$B"
  T=$SECONDS
  cmake -G Ninja -S "$SRC" -B "$B" -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_COMPILER="$CC" \
    -DCMAKE_CXX_FLAGS_RELEASE="$F" -DCMAKE_C_FLAGS_RELEASE="$F" \
    -DLLVM_DIR="$SDK/lib/cmake/llvm" -DMLIR_DIR="$SDK/lib/cmake/mlir" \
    -DLLVM_ENABLE_ASSERTIONS=ON -DLLVM_USE_LINKER=lld -DLLVM_PARALLEL_LINK_JOBS=2 \
    > "$OUT/m2-$1-configure.log" 2>&1
  echo "  configure rc=$? wall=$((SECONDS-T))s"
  T=$SECONDS
  ninja -C "$B" -j$JOBS $TARGETS > "$OUT/m2-$1-build.log" 2>&1
  echo "  build rc=$? wall=$((SECONDS-T))s  edges=$(grep -c '^\[' "$OUT/m2-$1-build.log")"
  echo "  du -sb build: $(du -sb "$B" | cut -f1)  ($(du -sh "$B" | cut -f1))"
  for b in $TARGETS; do
    printf "  %-18s %12d bytes\n" "$b" "$(stat -c %s "$B/bin/$b")"
  done
  echo "  readelf -S bin/circt-opt | grep -c debug_line: $(readelf -S "$B/bin/circt-opt" | grep -c debug_line)"
  echo "  nm -u bin/circt-opt | grep -c __assert_fail: $(nm -u "$B/bin/circt-opt" | grep -c __assert_fail)"
}

echo "commit $(git -C "$SRC" log -1 --format=%H 2>/dev/null) ; SDK firtool-1.157.0 ; jobs=$JOBS ; $(date -Is)"
echo "compiler: $($CXX --version | head -1)"
build bassert_n "-O3 -DNDEBUG"
build bassert_u "-O3 -UNDEBUG"
echo "=== already built: bassert_g (-O3 -UNDEBUG -gline-tables-only) ==="
echo "  du -sb: $(du -sb $SMOKE/bassert_g | cut -f1)"
for b in $TARGETS; do printf "  %-18s %12d bytes\n" "$b" "$(stat -c %s $SMOKE/bassert_g/bin/$b)"; done
echo "  nm -u bin/circt-opt | grep -c __assert_fail: $(nm -u $SMOKE/bassert_g/bin/circt-opt | grep -c __assert_fail)"
echo "THREEFLAGS DONE $(date -Is)"
