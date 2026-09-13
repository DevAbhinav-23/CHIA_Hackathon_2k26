# Slang build, Verilator version and closed-bug count, 2026-09-13

Three throwaway measurements under `00-README.md`'s stated exception to the no-code rule.
They answer **D-13** (does the slang front end build, and what does it cost), **D-09** (is
the packaged Verilator good enough) and **A-21** (how many closed `label:bug` issues exist).

Nothing under `design/` or `paper/` was edited. Scripts and every command's verbatim output
live beside this file: `m7_slang_build.sh`, `m7_sv_compare.sh`, `raw/m7-*`, `raw/m8-*`,
`raw/m9-*`.

## 0. What ran against what

Same identities as `2026-09-13-frd-followups.md` §0 except where noted.

| Item | Identity |
|---|---|
| CIRCT source tree | `~/.cache/chia-pin-smoke/src`, commit `5056ff04450bc9f27a9ff0460702aee1f1afdd3f` |
| CIRCT SDK | `~/.cache/chia-pin-smoke/circt-sdk`, `firtool-1.157.0`, LLVM 24.0.0git, assertions OFF |
| Compiler | `clang version 23.0.0git (d4148a8476df)` |
| New build directory | `~/.cache/chia-pin-smoke/bslang` (fresh, empty at start) |
| Parallelism | `-j8`, not `-j12`: the host had 6 GiB available and 11 GiB of swap already in use at start |
| Minimum RAM available during the build | **3,324 MiB** at 21:03:11, well clear of the 2 GiB floor (`raw/m7-mem.log`, 46 samples at 20 s) |
| Date | 2026-09-13 |

---

## M7 — the slang build (D-13 option a)

### The two options, read from source

`~/.cache/chia-pin-smoke/circt/CMakeLists.txt:550-552`, identical in the `src` tree at the
FRD's own commit:

```
option(CIRCT_SLANG_FRONTEND_ENABLED "Enables the slang Verilog frontend." OFF)
option(CIRCT_SLANG_BUILD_FROM_SOURCE
  "Build slang from source instead of finding an installed package" ON)
```

slang is fetched by `FetchContent` (`CMakeLists.txt:563-567`) from
`https://github.com/MikePopoloski/slang.git` at the **pinned commit**
`44dc55f99b9c64971893013e7931e643fbedcf23`, commented `# June 19, 2026: v11.0 + ~85 commits`.
`GIT_SHALLOW ON` is commented out with a TODO, so this is a **full clone**, not a shallow one.
The checkout was verified after configure: `44dc55f9`, 2026-06-19, *"Improve boost detection
(#1879)"*. `_deps/slang-src` is 50 MB; `_deps` as a whole is 215,699,596 B.

`lib/Conversion/ImportVerilog/CMakeLists.txt` confirms the coupling: `CIRCTImportVerilog`
lists `slang_slang` in both `DEPENDS` and `LINK_LIBS PRIVATE`, and the whole directory is
built to C++20 via `include(SlangCompilerOptions)`.

### Configure

Flags are M2's `bassert_g` string verbatim plus the two options (`m7_slang_build.sh`):

```
-DCMAKE_BUILD_TYPE=Release
-DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only"   (and the C equivalent)
-DLLVM_DIR=<sdk>/lib/cmake/llvm  -DMLIR_DIR=<sdk>/lib/cmake/mlir
-DLLVM_ENABLE_ASSERTIONS=ON -DLLVM_USE_LINKER=lld -DLLVM_PARALLEL_LINK_JOBS=2
-DCIRCT_SLANG_FRONTEND_ENABLED=ON -DCIRCT_SLANG_BUILD_FROM_SOURCE=ON
```

`LD_LIBRARY_PATH` carried the SDK's `lib` and the z3 shim, per M2's C-02 correction.

Configure **succeeded, rc=0, wall 19 s** — the full slang clone included. Its slang lines
verbatim (`raw/m7-configure-slang.txt`):

```
-- slang Verilog frontend is enabled
-- Building slang from source
-- slang version: 11.0.0+0
-- Installing slang dependency fmt
-- Installing slang dependency boost_unordered
```

### Build

`ninja -C bslang -j8 circt-verilog circt-translate circt-opt`.

| Quantity | Value |
|---|---|
| build wall, `-j8`, cold, no ccache | **841 s** (14 min 1 s), **rc=0**, zero `error` lines in the log |
| ninja edges | **1339** (ninja's own `[1339/1339]`; `.ninja_log` has 1913 output lines, 1339 distinct edges once multi-output tablegen edges are deduplicated) |
| `du -sh` of `bslang` | **1.4 G** (`du -sb` 1,434,197,304) |
| `du -sb` of `_deps` | 215,699,596 |

Binary sizes, against M2's `bassert_g` — same source tree, same SDK, same compiler, same
flag string, **no** slang:

| Binary | `bassert_g` (no slang) | `bslang` (slang) | Delta |
|---|---|---|---|
| `circt-verilog` | **does not exist** | **71,310,864** | new binary |
| `circt-translate` | 68,826,840 | **120,014,768** | **+51,187,928 (+74.4%)** |
| `circt-opt` | 200,343,024 | 200,331,232 | −11,792 (−0.006%, noise) |

`circt-opt` is unmoved because it does not link `CIRCTImportVerilog`. The slang cost lands
entirely on the two binaries that carry the front end, and it is a **static** cost: the
CMake block forces `BUILD_SHARED_LIBS OFF` for slang so `slang_slang` is embedded in each.

### What slang actually costs inside that 841 s

From `.ninja_log`, deduplicated (`raw/m7-cost-breakdown.txt`):

| Bucket | Edges | CPU-seconds | % of build CPU |
|---|---|---|---|
| rest of CIRCT | 1050 | 5444.9 | 83.2 |
| slang + fmt (`_deps`) | 275 | 889.4 | 13.6 |
| `CIRCTImportVerilog` | 12 | 195.3 | 3.0 |
| `circt-verilog` tool | 2 | 11.7 | 0.2 |
| **total** | **1339** | **6541.3** | **100** |

**The slang front end is 289 edges and 1,096 CPU-seconds — 16.8% of this build's CPU.** At
the 7.8× parallelism actually achieved, that is about **141 s of the 841 s wall**. The single
longest compile in the whole build is slang's own
`_deps/slang-build/.../syntax/SyntaxRewriter.cpp.o` at **101.3 s**, ahead of CIRCT's heaviest
(`MooreToCore.cpp.o`, 83.7 s), so slang also sets the critical path's tallest edge.

The 841 s is **not** comparable to M2's 582 s: different target set (3 vs 5) and different
parallelism (`-j8` vs `-j12`). The CPU-second split above is the clean isolation.

### The front end is present — three independent proofs

```
$ bslang/bin/circt-translate --help | grep -i verilog
      --import-verilog                                    - import Verilog or SystemVerilog
$ bassert_g/bin/circt-translate --help | grep -ci verilog
0
$ bslang/bin/circt-verilog --version
LLVM (http://llvm.org/):
  LLVM version 24.0.0git
  Optimized build.
CIRCT 5056ff0
slang version 11.0.0+0
```

and in the build's own lit config:

```
bassert_g/test/lit.site.cfg.py : config.slang_frontend_enabled = 0
bslang/test/lit.site.cfg.py    : config.slang_frontend_enabled = 1
```

**`CIRCT 5056ff0` is FR-03.14's first acceptance branch, satisfied directly**: `circt-verilog
--version` reports the source tree's own commit, not the SDK's release tag. The SDK's binary
reports `CIRCT firtool-1.157.0` for the same field, which is exactly the mismatch D-13 option
(c) was rejected over.

One inherited caveat: the from-source binaries need the z3 shim on `LD_LIBRARY_PATH` at **run**
time as well as build time. Without it, verbatim:

```
bslang/bin/circt-translate: error while loading shared libraries: libz3.so.4:
cannot open shared object file: No such file or directory
```

### SDK `circt-verilog --ir-moore` vs the new build's, on one `.sv` seed

Seed file `test/circt-verilog/roundtrip-oob-reads.sv` at seed commit `cc71d34ab52f`
("[MooreToCore] Fix out-of-bounds and aggregate `moore.extract` lowering (#10993)",
2026-08-17, the first row of `raw/m1-per-seed.csv`), fetched to `raw/m7-seed.sv`, 26 lines.
Its own `RUN:` line is `circt-verilog -Wno-error=range-oob %s | ...`.

| Invocation | SDK `circt-verilog` | `bslang` `circt-verilog` |
|---|---|---|
| `--ir-moore <seed>` | rc=1, 0 B stdout, 457 B stderr | rc=1, 0 B stdout, 457 B stderr |
| stderr | `error: cannot select range of [3:-1] from 'bit[1:0]' [-Wrange-oob]` | **byte-identical** (`cmp` clean) |
| `--ir-moore -Wno-error=range-oob <seed>` | rc=0, 682 B stdout, 3 `moore.module` | rc=0, 682 B stdout, 3 `moore.module` |
| the Moore IR | — | **byte-identical** (`cmp` clean) |
| `--version` CIRCT field | `firtool-1.157.0` | `5056ff0` |

Both binaries reject the raw seed identically, because the diagnostic is an error unless the
seed's own `-Wno-error=range-oob` is passed; with that flag both lift it to identical Moore IR.
**The two differ in exactly one respect that matters — the commit they were built from — and
in no respect that changes this input's output.** That is the cleanest possible statement of
why option (c) is not a substitute for (a): the SDK binary is behaviourally fine here and is
still at the wrong commit with assertions off.

---

## M8 — Verilator's packaged version (D-09)

Nothing was installed on the host. `raw/m8-verilator.txt`.

| Quantity | Value |
|---|---|
| `ubuntu:24.04` pulled fresh (no local copy existed) | digest `sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254`, created 2026-09-07 |
| image size on disk | **29,772,417 B (28.4 MiB)**, a single `RootFS` layer |
| `apt-cache policy verilator` | Installed: (none) / **Candidate: 5.020-1** / table `5.020-1 500` |
| packaged `verilator --version` (installed in the throwaway container) | **`Verilator 5.020 2024-01-01 rev (Debian 5.020-1)`** |
| host `verilator --version` | `Verilator 5.052 2026-09-05 rev v5.052` |
| apt footprint, `--no-install-recommends` | 26 new packages, **27.4 MB to download, 123 MB on disk** |
| apt footprint, default | 31 new packages (adds `libsystemc-dev` and four others) |

The four flags D-09's escalation rule turns on, checked in both:

| Flag | host 5.052 | packaged 5.020-1 |
|---|---|---|
| `--x-initial` | present | present |
| `--x-assign` | present | present |
| `--binary` | present | present |
| `--timing` | present | present |

The help text is identical string-for-string in both versions, e.g.
`--x-assign <mode>   Assign non-initial Xs to this value` and
`--x-initial <mode>  Assign initial Xs to this value`.

**The flags are not the gap; the age is.** Ubuntu 24.04 ships 5.020 of 2024-01-01 — 32 minor
versions and 20 months behind the host's 5.052. D-09's escalation trigger ("escalating to (b) a pinned
source build only if the packaged version lacks `--x-initial` or `--x-assign`") is **not
tripped**; but D-09's own binding consequence, FR-03.15, is about X-propagation *behaviour*
differing between versions, and the 20-month gap between what the host measured and what the
image would install is exactly that risk, not the flag-presence risk.

---

## Note on `design/`, edited in parallel with this work

Nothing under `design/` or `paper/` was written by this measurement; `design/01-FRD.md`,
`design/02-HLD.md` and `design/ADR/ADR-D-13-circt-verilog-slang.md` were nevertheless modified
at 21:12-21:13 while the M7 build was running, by other work in the same window. The D-13
reading above was taken against the pre-21:13 text and re-checked against the post-21:13 text:
the amended ADR now defines branch (b) by **entry point** at **36** seeds rather than by source
region at 46, which changes nothing in M7's result — branch (a) came up, so (b) is not taken.

---

## M9 — closed `label:bug` issues in `llvm/circt` (A-21)

One unauthenticated GitHub search request per state, no pagination, no loop. Raw JSON kept at
`raw/m9-closed.json` and `raw/m9-open.json`; `raw/m9-github-bugcount.txt` has the parse.

| Query | `total_count` |
|---|---|
| `repo:llvm/circt is:issue label:bug is:closed` | **487** |
| `repo:llvm/circt is:issue label:bug is:open` | **101** |
| total, both states | 588 |

Timestamp **2026-09-13T21:00:38+05:30**. `incomplete_results: false` for both. No rate-limit
message was returned; the queries were not repeated beyond one retry whose only purpose was to
save the raw JSON to disk (the first parse died on a control character inside an issue body,
which `json.load(..., strict=False)` handles).

Two honest caveats:

1. The search API's `total_count` is exact below the 1,000-result pagination cap; 487 and 101
   are both below it, so neither figure is truncated.
2. This counts **issues only** (`is:issue` excludes pull requests). FR-10.9's mirror is
   specified as `GET /repos/llvm/circt/issues?state=all`, which returns pull requests as well
   unless they are filtered out. The mirror's raw row count will therefore be **larger** than
   487 + 101, and A-21's number is the one above, not the mirror's length.

---

## What each decision now stands on

| ID | Settled | Not settled |
|---|---|---|
| **D-13** | **Option (a) works.** The slang front end configures in 19 s and builds clean in 841 s at `-j8` under FR-03.4's exact flag string, at the FRD's own commit, from the pinned slang `44dc55f9`; `circt-verilog --version` reports `CIRCT 5056ff0`, satisfying FR-03.14's first acceptance branch, and `circt-translate --import-verilog` and `config.slang_frontend_enabled = 1` both come back with it. Cost is 289 edges, 1,096 CPU-seconds (16.8% of the build, ~141 s of wall at `-j8`), +51.2 MB on `circt-translate` and a new 71.3 MB `circt-verilog`; `circt-opt` is untouched. The fallback branch (b) does not need to be taken. | The **image**: these are host numbers under `-O3 -UNDEBUG -gline-tables-only`, and no image was built, so `docker save` and the layer cost of +122 MB of front-end binaries are still unpriced (the same hole D-08 has). Whether the 62 `REQUIRES: slang` lit tests now pass was not run — only that the gate that skipped them is now open. |
| **D-09** | **Option (a) holds; no escalation.** Ubuntu 24.04's packaged Verilator is 5.020-1, and it has all four of `--x-initial`, `--x-assign`, `--binary`, `--timing`, with help text identical to the host's 5.052. D-09's stated escalation trigger to a pinned source build is not met. The image cost is one apt line: 26 packages, 27.4 MB downloaded, 123 MB on disk. | Whether 5.020 and 5.052 **propagate X identically** — the axis FR-08.4 and FR-08.9 actually ride on. The packaged version is 20 months and 32 releases behind the host where FINAL Appendix A's X-propagation evidence was taken, so FR-03.15's "one Verilator version serves the whole campaign" now has a concrete version to name (5.020-1) and a concrete reason to re-run any host-measured X behaviour inside the image before trusting it. |
| **A-21** | **Counted: 487 closed `label:bug` issues, 101 open, at 2026-09-13T21:00:38+05:30.** That is 7.5× the 65 closed issues D-05's earlier draft synthesised from, and about half of Mut4All's 1,000 reports. FR-05.2's "full history of closed `label:bug` issues" is a real corpus, so **ADR-D-05's fallback (d), the 24-month fix-commit set, is not needed** and HLD risk A7 does not fire. A-21 moves from **Uncounted** to counted. | Whether 487 reports synthesise a *strong* mutator set — A-21's wording is about sufficiency, and only F-05's synthesis answers that. Also unchecked: how many of the 487 carry enough body text to be usable input, and the mirror-vs-search denominator gap in caveat 2 above. |
