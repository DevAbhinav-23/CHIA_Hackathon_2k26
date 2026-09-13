#!/bin/bash
# W-09 crash-fixture mining harness.  Host builds only: no docker, no model
# calls, no credentials.  Everything lives under $W09.
W09=${W09:-$HOME/.cache/chia-pin-smoke/w09}
SHIM=${SHIM:-$HOME/.cache/chia-pin-smoke/shim}   # holds libz3.so.4
JOBS=${JOBS:-8}

# configure <worktree> <builddir> <sdk>   (04-Test-Plan W-09 / 03-LLD 4.2)
configure() {
  local SRC=$1 B=$2 SDK=$3
  LD_LIBRARY_PATH=$SDK/lib:$SHIM \
  cmake -G Ninja -S "$SRC" -B "$B" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER=clang \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
    -DCMAKE_C_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
    -DLLVM_ENABLE_ASSERTIONS=ON \
    -DLLVM_DIR="$SDK/lib/cmake/llvm" \
    -DMLIR_DIR="$SDK/lib/cmake/mlir" \
    -DMLIR_SOURCE_DIR="$SDK" \
    -DLLVM_USE_LINKER=lld \
    -DLLVM_CCACHE_BUILD=ON \
    -DLLVM_PARALLEL_LINK_JOBS=2
}

# build <builddir> <sdk> <target...>
build() {
  local B=$1 SDK=$2; shift 2
  LD_LIBRARY_PATH=$SDK/lib:$SHIM ninja -C "$B" -j"$JOBS" "$@"
}
