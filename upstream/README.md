# Files proposed to CHIA core (upstream PR to ucb-bar/chia)

| File | Purpose |
|---|---|
| `dockerfiles/ChiaCirctAssertDockerfile` | Assertions-on CIRCT image: release-pinned commit, matching `firtool-*` SDK, `-O3 -UNDEBUG -gline-tables-only`, slang front end, `circt-reduce`, Verilator, `lit`, pin-equality check that fails the build on mismatch. Built and verified 2026-09-14 (see `analysis/measurements/2026-09-14-image-build.md`). |
| `.github/workflows/chia-circt-assert.yml` | The workflow CHIA requires for every new Dockerfile (`AGENTS.md`). |
| `chia/chipyard/circt.py` additions | Three generic CIRCT helpers (`circt_reduce_run`, `circt_exec_probe`, `circt_symbolize`); arrive with the loop code. |

`sync-to-chia.sh` (arrives with the loop code) copies `circt_bug_loop/` into a CHIA checkout as `examples/circt_bug_loop/` and applies these files. Working CHIA checkout for the PR: a clone of `ucb-bar/chia` at commit 16c35e92, branch `bugloop`.
