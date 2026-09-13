#!/bin/bash
# W-04 acceptance: every FR-03 check that can be run inside the built image.
# Runs INSIDE the container. Every check prints its own command first.
set -u
B=/workspace/circt/build
say() { echo; echo "### $*"; }
run() { echo "\$ $*"; "$@" 2>&1; echo "[rc=$?]"; }

say "IMAGE IDENTITY"
run bash -c 'echo "BUGLOOP_CIRCT_SHA=$BUGLOOP_CIRCT_SHA"; echo "BUGLOOP_CIRCT_VER=$BUGLOOP_CIRCT_VER"; echo "BUGLOOP_TOOL_TARGETS=$BUGLOOP_TOOL_TARGETS"; echo "BUGLOOP_CXX_FLAGS_RELEASE=$BUGLOOP_CXX_FLAGS_RELEASE"; echo "BUGLOOP_SLANG=$BUGLOOP_SLANG"'

say "FR-03.1  source commit, fetched by SHA"
run git -C /workspace/circt rev-parse HEAD
run git -C /workspace/circt log -1 --format='%H %cI %s'

say "FR-03.2  pin equality, re-derived inside the image"
run bash -c "git -C /workspace/circt ls-tree \$BUGLOOP_CIRCT_SHA llvm"
run bash -c "git -C /workspace/circt ls-tree \$BUGLOOP_CIRCT_VER llvm"
run bash -c 'test "$(git -C /workspace/circt ls-tree $BUGLOOP_CIRCT_SHA llvm | awk "{print \$3}")" = "$(git -C /workspace/circt ls-tree $BUGLOOP_CIRCT_VER llvm | awk "{print \$3}")" && echo EQUAL || echo DIFFERENT'
echo "--- negative control: the same check against a tag with a different pin"
run bash -c 'git -C /workspace/circt fetch -q --depth 1 origin tag firtool-1.156.0 2>/dev/null; git -C /workspace/circt ls-tree firtool-1.156.0 llvm; test "$(git -C /workspace/circt ls-tree $BUGLOOP_CIRCT_SHA llvm | awk "{print \$3}")" = "$(git -C /workspace/circt ls-tree firtool-1.156.0 llvm | awk "{print \$3}")"'

say "FR-03.3  CHIA's SDK strip retained"
run bash -c 'ls -d /opt/circt-sdk/include/circt 2>&1; ls -d /opt/circt-sdk/lib/cmake/circt 2>&1; test ! -e /opt/circt-sdk/include/circt && test ! -e /opt/circt-sdk/lib/cmake/circt && echo "BOTH ABSENT"'

say "FR-03.4  the flag string"
run bash -c 'grep -E "^CMAKE_(CXX|C)_FLAGS_RELEASE:" '"$B"'/CMakeCache.txt'
run bash -c 'grep -c -- -DNDEBUG '"$B"'/compile_commands.json'
run bash -c 'grep -c -- -UNDEBUG '"$B"'/compile_commands.json'
run bash -c 'python3 -c "import json,sys; print(len(json.load(open(\"'"$B"'/compile_commands.json\"))))" 2>/dev/null || grep -c "\"command\"" '"$B"'/compile_commands.json'
run bash -c 'readelf -S '"$B"'/bin/circt-opt | grep -c debug_line'
run bash -c 'readelf -S '"$B"'/bin/circt-opt | grep -oE "\.debug[a-z_]*" | sort -u | tr "\n" " "'

say "FR-03.5  assertions in the binaries"
run bash -c 'for t in $BUGLOOP_TOOL_TARGETS; do printf "%-18s %s\n" "$t" "$(nm -u '"$B"'/bin/$t | grep -c __assert_fail)"; done'
echo "--- obj.CIRCT objects that do NOT reference __assert_fail"
run bash -c '
tot=0; non=0; : > /tmp/nonref.txt
while read -r o; do
  tot=$((tot+1))
  if ! nm --undefined-only "$o" 2>/dev/null | grep -q __assert_fail; then
    non=$((non+1)); echo "$o" >> /tmp/nonref.txt
  fi
done < <(find '"$B"' -path "*obj.CIRCT*.dir*" -name "*.o" | sort)
echo "obj.CIRCT objects total=$tot  referencing=$((tot-non))  NOT referencing=$non"
sed "s#^'"$B"'/##" /tmp/nonref.txt'

say "FR-03.7  every target exists and runs --version"
run bash -c 'for t in $BUGLOOP_TOOL_TARGETS; do printf "== %s\n" "$t"; ls -l '"$B"'/bin/$t >/dev/null 2>&1 && '"$B"'/bin/$t --version 2>&1 | head -4 || echo "MISSING"; done'

say "FR-03.8  lit, libz3, Verilator; lit installed exactly once"
run bash -c 'command -v lit; lit --version'
run ls -l /home/ray/anaconda3/envs/py_worker/bin/lit
run bash -c 'verilator --version'
run bash -c "$B/bin/arcilator --version | head -3"
run bash -c 'ldd /opt/circt-sdk/bin/circt-opt | grep z3'
run bash -c '/home/ray/anaconda3/envs/py_worker/bin/pip install lit 2>&1 | tail -3'

say "FR-03.9  CHIA compatibility"
run bash -c 'python --version; python -c "import sys; print(sys.executable)"'
run bash -c 'python -c "import ray; print(ray.__version__)"'
run bash -c 'python -c "import chia; print(chia.__file__)" 2>&1 | tail -1'
run bash -c 'echo $SHELL; readlink -f /bin/sh; bash --version | head -1'
run bash -c 'ssh -V'
run bash -c 'rsync --version | head -1'

say "FR-03.11  version string after -UNDEBUG"
run bash -c "$B/bin/circt-opt --version"

say "FR-03.12  MLIR/LLVM assertions stay off"
run bash -c 'grep -n "LLVM_ENABLE_ABI_BREAKING_CHECKS" /opt/circt-sdk/include/llvm/Config/abi-breaking.h'
run bash -c 'grep -n "LLVM_ENABLE_ASSERTIONS" /opt/circt-sdk/lib/cmake/llvm/LLVMConfig.cmake | head -3'

say "FR-03.14  both slang entry points"
run bash -c "$B/bin/circt-verilog --version"
run bash -c "$B/bin/circt-translate --help 2>&1 | grep -c import-verilog"
run bash -c "$B/bin/circt-translate --help 2>&1 | grep -i import-verilog"
run bash -c 'grep -E "^CIRCT_SLANG" '"$B"'/CMakeCache.txt'

say "FR-03.15  Verilator version, one for the campaign"
run bash -c 'verilator --version'
run bash -c 'verilator --help 2>&1 | grep -E -- "--x-initial|--x-assign" | head -4'

say "FR-03.16  SHA-256 of every published tool binary"
run bash -c 'for t in $BUGLOOP_TOOL_TARGETS; do sha256sum '"$B"'/bin/$t; done'
run bash -c 'sha256sum /opt/circt-sdk/bin/llvm-symbolizer /usr/bin/verilator'

say "FR-03.17  MLIR_SOURCE_DIR and lit discovery"
run bash -c 'grep mlir_src_root '"$B"'/test/lit.site.cfg.py'
run bash -c 'cd '"$B"' && lit --no-progress-bar --show-tests '"$B"'/test > /tmp/lit-show-tests.txt 2>&1; echo "rc=$?"; echo "discovered=$(grep -c "^    " /tmp/lit-show-tests.txt)"; echo "parse-errors=$(grep -c "unable to parse config file" /tmp/lit-show-tests.txt)"; grep -c "Tools/circt-tblgen" /tmp/lit-show-tests.txt'
run bash -c 'head -3 /tmp/lit-show-tests.txt; grep "Tools/circt-tblgen" /tmp/lit-show-tests.txt | head -2'

say "OTHER TOOLING"
run bash -c 'prlimit --version'
run bash -c '/opt/circt-sdk/bin/llvm-symbolizer --version | head -2'
run bash -c 'command -v FileCheck not count split-file'
run bash -c 'clang --version | head -1; ninja --version; cmake --version | head -1; git --version'
run bash -c 'du -sh '"$B"'; du -sh /opt/circt-sdk; du -sb '"$B"'/bin/* | sort -k2'

say "A-11  why -DLLVM_ENABLE_ASSERTIONS=ON is ineffective"
run bash -c 'grep -n "LLVM_ENABLE_ASSERTIONS" /opt/circt-sdk/lib/cmake/llvm/LLVMConfig.cmake'
run bash -c 'grep -n "^LLVM_ENABLE_ASSERTIONS" '"$B"'/CMakeCache.txt'
run bash -c 'grep -rn "LLVM_ENABLE_ABI_BREAKING_CHECKS" /opt/circt-sdk/include/llvm/Config/abi-breaking.h'

say "A-16  the SDK's z3 path, exercised once"
run bash -c 'ls -l /opt/circt-sdk/bin/circt-bmc 2>&1'
run bash -c 'printf "hw.module @t(in %%a : i1, out o : i1) { hw.output %%a : i1 }\n" > /tmp/bmc.mlir; /opt/circt-sdk/bin/circt-bmc /tmp/bmc.mlir --module=t -b 1 --shared-libs=/opt/circt-sdk/lib/libCIRCTSMTToZ3LLVM.so 2>&1 | head -10'
