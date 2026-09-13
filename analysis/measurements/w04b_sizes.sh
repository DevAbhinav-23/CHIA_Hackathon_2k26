#!/bin/bash
# W-04b: the in-image half of the size/flag comparison. Runs INSIDE a container
# of either image; every line is the same in both, so the two outputs diff.
set -u
B=/workspace/circt/build
say() { echo; echo "### $*"; }
run() { echo "\$ $*"; "$@" 2>&1; echo "[rc=$?]"; }

say "IDENTITY"
run bash -c 'echo "BUGLOOP_CIRCT_SHA=$BUGLOOP_CIRCT_SHA"; echo "BUGLOOP_CIRCT_VER=$BUGLOOP_CIRCT_VER"; echo "BUGLOOP_TOOL_TARGETS=$BUGLOOP_TOOL_TARGETS"; echo "BUGLOOP_CXX_FLAGS_RELEASE=$BUGLOOP_CXX_FLAGS_RELEASE"; echo "BUGLOOP_SLANG=$BUGLOOP_SLANG"'
run git -C /workspace/circt rev-parse HEAD

say "THE FLAG STRING, as the build actually saw it"
run bash -c 'grep -E "^CMAKE_(CXX|C)_FLAGS_RELEASE:" '"$B"'/CMakeCache.txt'
run bash -c 'echo -n "compile commands: "; python3 -c "import json;print(len(json.load(open(\"'"$B"'/compile_commands.json\")))) "'
run bash -c 'echo -n "-DNDEBUG occurrences: "; grep -c -- -DNDEBUG '"$B"'/compile_commands.json'
run bash -c 'echo -n "-UNDEBUG occurrences: "; grep -c -- -UNDEBUG '"$B"'/compile_commands.json'

say "ASSERTIONS IN THE BINARIES (FR-03.5)"
run bash -c 'for t in $BUGLOOP_TOOL_TARGETS; do printf "%-18s __assert_fail undefined: %s\n" "$t" "$(nm -u '"$B"'/bin/$t | grep -c __assert_fail)"; done'
run bash -c '
tot=0; non=0
while read -r o; do
  tot=$((tot+1))
  nm --undefined-only "$o" 2>/dev/null | grep -q __assert_fail || non=$((non+1))
done < <(find '"$B"' -path "*obj.CIRCT*.dir*" -name "*.o" | sort)
echo "obj.CIRCT objects total=$tot  referencing=$((tot-non))  NOT referencing=$non"'

say "DEBUG INFO (FR-03.4 half that is the SAME in both images)"
run bash -c 'readelf -S '"$B"'/bin/circt-opt | grep -c debug_line'
run bash -c 'readelf -S '"$B"'/bin/circt-opt | grep -oE "\.debug[a-z_]*" | sort -u | tr "\n" " "; echo'

say "SIZES"
run bash -c 'for t in $BUGLOOP_TOOL_TARGETS; do printf "%-18s %12d\n" "$t" "$(du -sb '"$B"'/bin/$t | cut -f1)"; done'
run bash -c 'tot=0; for t in $BUGLOOP_TOOL_TARGETS; do tot=$((tot+$(du -sb '"$B"'/bin/$t | cut -f1))); done; echo "six targets total: $tot bytes"'
run bash -c 'du -sb '"$B"'; du -sh '"$B"''
run bash -c 'du -sb /opt/circt-sdk; du -sh /opt/circt-sdk'
run bash -c 'circt-opt --version 2>/dev/null | head -3 || '"$B"'/bin/circt-opt --version | head -3'
