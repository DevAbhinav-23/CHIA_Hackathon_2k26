# `crash_01`

A null-pointer dereference in CIRCT's own `circt::sim::StringConcatOp::fold`: the folder cast every operand to `mlir::StringAttr` without first checking that the operand folded to a constant at all, so a `sim.string.concat` whose operand is a block argument or an unfoldable value reaches `cast<StringAttr>(nullptr)` and segfaults. It covers the `crash` class: the process dies by `SIGSEGV` with no assertion line and no `LLVM ERROR:` line, so the oracle can only fire on the signal, and the fingerprint has to come from the stack trace rather than from any text.

Mined by `analysis/measurements/w09_attempt.sh` on 2026-09-14 from seed `564e07083c52` (`test/Dialect/Sim/dynamic-strings.mlir`), observed at its first parent `2f46bdfae165` built against `firtool-1.143.0`; the same input at the seed commit does not fire. Tool `circt-opt`, class `crash`, signal `SIGSEGV`.

`stderr.txt`, `expected.json:assertion_site` and the frame paths carry the mining host's build prefix (`/home/adi/.cache/chia-pin-smoke/w09/wt143` for CIRCT sources, `/home/adi/.cache/chia-pin-smoke/w09/sdk-1.143.0` for the SDK), not the image's `/workspace/circt/` and `/opt/circt-sdk/`. 03-LLD.md 3.7.1 strips the build prefix before the site enters a fingerprint, so the prefix is evidence and never a compared value; the relative site is `circt::sim::StringConcatOp::fold lib/Dialect/Sim/SimOps.cpp:541`.
