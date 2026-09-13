#!/bin/bash
# M7 (D-13 option a): does the slang Verilog frontend actually build, and what does it cost?
# Same source tree, SDK, compiler and flag string as M2's bassert_g, plus:
#   -DCIRCT_SLANG_FRONTEND_ENABLED=ON   (CMakeLists.txt:550)
#   -DCIRCT_SLANG_BUILD_FROM_SOURCE=ON  (CMakeLists.txt:551, default ON; passed explicitly)
# slang is fetched by FetchContent from https://github.com/MikePopoloski/slang.git at the
# pinned commit 44dc55f99b9c64971893013e7931e643fbedcf23 (CMakeLists.txt:566), NOT shallow.
set -u
SMOKE=$HOME/.cache/chia-pin-smoke
SRC=$SMOKE/src
SDK=$SMOKE/circt-sdk
B=$SMOKE/bslang
OUT=/home/adi/Projects/chia-hackathon/analysis/measurements/raw
JOBS=${JOBS:-8}
CXX=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang++
CC=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang
# C-02 / M2: the SDK's mlir-tblgen needs libz3.so.4 via the shim at BUILD time.
export LD_LIBRARY_PATH=$SDK/lib:$SMOKE/shim${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
TARGETS="circt-verilog circt-translate circt-opt"

echo "host: $(uname -srm)  nproc=$(nproc)  jobs=$JOBS  $(date -Is)"
echo "src commit: $(git -C "$SRC" log -1 --format=%H 2>/dev/null || echo '(not a repo)')"
echo "compiler: $($CXX --version | head -1)"
free -g | sed -n '1,2p'

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
  -DLLVM_PARALLEL_LINK_JOBS=2 \
  -DCIRCT_SLANG_FRONTEND_ENABLED=ON \
  -DCIRCT_SLANG_BUILD_FROM_SOURCE=ON \
  > "$OUT/m7-configure.log" 2>&1
RC=$?
CFG_WALL=$((SECONDS-T0))
echo "configure rc=$RC wall=${CFG_WALL}s"
grep -i -n "slang" "$OUT/m7-configure.log" | tee "$OUT/m7-configure-slang.txt"
[ $RC -ne 0 ] && { echo "CONFIGURE FAILED; first error:"; grep -m1 -i -A5 "error" "$OUT/m7-configure.log"; exit 1; }

echo "=== ninja dry-run edge count ==="
ninja -C "$B" -n $TARGETS 2>/dev/null | wc -l | tee "$OUT/m7-targetcount.txt"

echo "=== build start $(date -Is) (-j$JOBS) ==="
T1=$SECONDS
ninja -C "$B" -j$JOBS $TARGETS > "$OUT/m7-build.log" 2>&1
RC=$?
BLD_WALL=$((SECONDS-T1))
echo "build rc=$RC wall=${BLD_WALL}s  end $(date -Is)"
if [ $RC -ne 0 ]; then
  echo "=== BUILD FAILED: first error verbatim ==="
  grep -m1 -B2 -A20 -E "(FAILED:|error:)" "$OUT/m7-build.log"
  exit 1
fi

echo "=== sizes ==="
echo "du -sh  $B : $(du -sh "$B" | cut -f1)   du -sb: $(du -sb "$B" | cut -f1)"
echo "du -sh  _deps (slang etc): $(du -sh "$B/_deps" 2>/dev/null | cut -f1)"
for b in $TARGETS; do printf "  %-18s %12d bytes\n" "$b" "$(stat -c %s "$B/bin/$b" 2>/dev/null || echo -1)"; done
echo "=== frontend present? ==="
echo "\$ circt-translate --help | grep -i verilog"
"$B/bin/circt-translate" --help 2>&1 | grep -i verilog
echo "\$ circt-verilog --version"
"$B/bin/circt-verilog" --version 2>&1
echo "M7 BUILD DONE $(date -Is)"
