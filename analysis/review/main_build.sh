#!/bin/bash
# T2: assertions-on circt-opt at current llvm/circt main, release SDK whose llvm pin matches.
# Same route as analysis/measurements/m2_build.sh + ChiaCirctAssertDockerfile (FR-03.2/3/4).
set -euo pipefail
SHA=${1:?circt sha}
VER=${2:?firtool tag with the same llvm pin}
R=$HOME/.cache/review-main-build
SRC=$R/src SDK=$R/sdk B=$R/build
SHIM=$HOME/.cache/chia-pin-smoke/shim   # libz3.so.4 for the SDK's tblgen (C-02)
CXX=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang++
CC=/home/adi/Projects/Honours/MLIR/llvm-project/build/bin/clang
JOBS=12
mkdir -p "$R"
if [ ! -d "$SRC/.git" ]; then
  git init -q "$SRC"
  git -C "$SRC" remote add origin https://github.com/llvm/circt
fi
git -C "$SRC" fetch -q --depth 1 origin "$SHA" "refs/tags/$VER:refs/tags/$VER"
git -C "$SRC" checkout -q --detach "$SHA"
pin_src=$(git -C "$SRC" rev-parse "$SHA:llvm")
pin_tag=$(git -C "$SRC" rev-parse "$VER^{commit}:llvm")
[ "$pin_src" = "$pin_tag" ] || { echo "FATAL pin mismatch $pin_src != $pin_tag"; exit 2; }
echo "src=$SHA ver=$VER llvm_pin=$pin_src"
if [ ! -f "$SDK/.done" ]; then
  rm -rf "$SDK"; mkdir -p "$SDK"
  curl -fsSL "https://github.com/llvm/circt/releases/download/$VER/circt-full-shared-linux-x64.tar.gz" \
    | tar -xz --strip-components=1 -C "$SDK"
  rm -rf "$SDK/include/circt" "$SDK/lib/cmake/circt"   # FR-03.3 strip
  touch "$SDK/.done"
fi
export LD_LIBRARY_PATH=$SDK/lib:$SHIM${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
T0=$SECONDS
cmake -G Ninja -S "$SRC" -B "$B" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER="$CXX" -DCMAKE_C_COMPILER="$CC" \
  -DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
  -DCMAKE_C_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
  -DLLVM_DIR="$SDK/lib/cmake/llvm" -DMLIR_DIR="$SDK/lib/cmake/mlir" -DMLIR_SOURCE_DIR="$SDK" \
  -DLLVM_ENABLE_ASSERTIONS=ON -DLLVM_USE_LINKER=lld -DLLVM_CCACHE_BUILD=ON \
  -DLLVM_PARALLEL_LINK_JOBS=2
echo "configure wall=$((SECONDS-T0))s"
T1=$SECONDS
ninja -C "$B" -j$JOBS circt-opt
echo "build wall=$((SECONDS-T1))s end $(date -u -Is)"
"$B/bin/circt-opt" --version
