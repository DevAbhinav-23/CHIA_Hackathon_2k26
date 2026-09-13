# FRD follow-up measurements, 2026-09-13

Throwaway measurements run under `00-README.md`'s stated exception to the no-code rule
("throwaway measurement scripts whose output feeds an `A-nn` or a `D-nn`"). They answer
`design/reviews/red-team-FRD.md` §7 items 1, 2, 3, 6 and 10, and feed A-01, A-03, A-04,
A-08, A-10, A-12, A-20, C-16, C-17, D-08 and D-13.

Nothing under `design/` or `paper/` is edited by this work. Scripts, logs and CSVs live
beside this file; `raw/` holds every command's output verbatim.

## 0. What ran against what

| Item | Identity |
|---|---|
| CIRCT source tree | `~/.cache/chia-pin-smoke/src`, commit `5056ff04450bc9f27a9ff0460702aee1f1afdd3f` (2026-08-31) |
| CIRCT SDK | `~/.cache/chia-pin-smoke/circt-sdk`, `firtool-1.157.0`, LLVM 24.0.0git, assertions OFF |
| CIRCT clone for history | `~/.cache/chia-pin-smoke/circt`, blobless, HEAD `b792c772819df723628d1fe6073269b85a8ade5d` (2026-09-11) |
| Host | Linux 7.2.3-1-cachyos x86_64, `nproc`=20, 15.6 GiB RAM. Every build used `-j12` (≤ `nproc`−2) |
| Host C++ compiler for the new builds | `clang version 23.0.0git (d4148a8476df)` |
| `lit` | 23.1.1, `pip install lit` into `~/.cache/chia-pin-smoke/venv` |
| Docker | client and server 29.7.2, usable without `sudo` |
| Date | 2026-09-13 |

`ccache` is **not** in play in any of these builds: `-DLLVM_CCACHE_BUILD=ON` is an
LLVM-tree option and is silently unused in a standalone CIRCT build against an installed
LLVM (`LLVM_CCACHE_BUILD:UNINITIALIZED=ON` in the cache, no `CMAKE_*_COMPILER_LAUNCHER`),
and `ccache -s` was byte-identical before and after. Every wall time below is therefore a
cold, cache-free compile. CHIA's own image *does* get ccache, by a different route: it
puts `/usr/lib/ccache` on `PATH` and passes `-DCMAKE_CXX_COMPILER=clang++` by name.

---

## M1 — corpus reach: entry tools, languages and reducibility of the 187 seeds

**Feeds A-01, D-13, red-team K1 / experiment 1.**

Scripts: `m1_runlines.py`; outputs `raw/m1-per-runline.csv`, `raw/m1-per-seed.csv`,
`raw/m1-summary.txt`, `raw/m1-lift-check.txt`.

The 187 seeds were re-derived from `analysis/pin_window_raw.json` with the rule at
`analysis/pin-window-analysis.md` §2 lines 74-79, using the regex verbatim from
`analysis/pin_window.py:107-108`. The re-derivation reproduces **187** filtered
candidates and **171** with an exact SDK match, matching PIN §4 exactly.

Each seed's touched test files were fetched at the seed commit with one batched
`git -C <clone> cat-file --batch` over 228 `<sha>:<path>` specs (125 s, blobless clone,
0 missing). 331 logical `RUN:` lines were extracted, joining lit's `\` continuations.

### Seeds per entry tool

A seed may use several tools, so this column does not sum to 187.

| Entry tool | Seeds | % of 187 |
|---|---|---|
| `circt-opt` | 136 | 72.7 |
| `circt-translate` | 39 | 20.9 |
| `circt-verilog` | 31 | 16.6 |
| other (`%python`, `cat`, `esiquery`, `split-file`, shell) | 10 | 5.3 |
| `circt-reduce` | 6 | 3.2 |
| `firtool` | 5 | 2.7 |
| `circt-synth` | 3 | 1.6 |
| `circt-lec` | 1 | 0.5 |
| `arcilator` | 1 | 0.5 |
| `circt-capi-firrtl-test` | 1 | 0.5 |

Partitioned by **primary** entry tool (first match in FR-03.7's order), which does sum
to 187: `circt-opt` 136, `circt-verilog` 30, `circt-translate` 9, `circt-reduce` 6,
`firtool` 2, `arcilator` 1, `circt-synth` 1, none 2.

### Seeds per input language, and reduction path

Language is the extension of the test file the seed's commit touched. 9 seeds touch test
files in more than one language, so the first table does not sum to 187; the second
partitions each seed by the **best** path available to it and does.

| Language | Seeds | % | Reduction path |
|---|---|---|---|
| `.mlir` | 146 | 78.1 | `circt-reduce` directly |
| `.sv` | 36 | 19.3 | lift with `circt-verilog --ir-moore` |
| `.fir` | 8 | 4.3 | lift with `firtool --parse-only` |
| other (`.py` 5, `.aig` 1, `.c` 1) | 7 | 3.7 | textual only |

| Best path available to the seed | Seeds | % of 187 |
|---|---|---|
| `circt-reduce` directly (MLIR) | 146 | 78.1 |
| via lift, `circt-verilog --ir-moore` | 35 | 18.7 |
| via lift, `firtool --parse-only` | 4 | 2.1 |
| textual only | 2 | 1.1 |
| **total** | **187** | **100** |

### The two lift flags, verified twice

Both flags exist in the SDK binaries' `--help`: `firtool --parse-only` ("Emit FIR dialect
after parsing, verification, and annotation lowering") and `circt-verilog --ir-moore`
("Run the entire pass manager to just before MooreToCore conversion, and emit the
resulting Moore dialect IR").

They were also run end to end, which is stronger than the `--help` check the task asked
for (`raw/m1-lift-check.txt`). On `analysis/probe/tiny.fir` and `analysis/probe/tiny.sv`:

- `firtool --parse-only` → `firrtl.circuit` MLIR; `circt-reduce --test=/bin/true` on the
  result reaches `Testing input with /bin/true`, `Initial module has size 634`.
- `circt-verilog --ir-moore` → `moore.module` MLIR; `circt-reduce` reaches
  `Initial module has size 765`.
- The raw files still fail, confirming C-17: `.fir` → `error: custom op 'FIRRTL' is
  unknown`, `.sv` → `error: unexpected character`. (C-17 records different diagnostic
  text for both, which is consistent with C-17's own statement that the text depends on
  the input's first token; the *behaviour* — reject before reduction — is identical.)

So **lift is a working reduction path, not a hypothesis**, and 185 of 187 seeds (98.9%)
have some `circt-reduce` path. The cost is that the `.sv` lift tool is exactly the tool
D-13 is about; see below.

### `RUN:` line shape features

The red team named leading `not`, pipes, `%t`/`%S`/`%{` and `split-file`. Measured over
331 lines:

| Feature | Lines | % of 331 | Seeds | % of 187 |
|---|---|---|---|---|
| pipe `\|` | 234 | 70.7 | 164 | 87.7 |
| `--split-input-file` † | 70 | 21.1 | 56 | 29.9 |
| `--verify-diagnostics` † | 61 | 18.4 | 53 | 28.3 |
| `%t` | 52 | 15.7 | 10 | 5.3 |
| `%S` | 10 | 3.0 | 4 | 2.1 |
| output redirect `>` | 10 | 3.0 | 4 | 2.1 |
| `&&` | 5 | 1.5 | 3 | 1.6 |
| leading `not` | 2 | 0.6 | 1 | 0.5 |
| `split-file` | 1 | 0.3 | 1 | 0.5 |
| `%{` | **0** | 0 | **0** | 0 |

† not on the red team's list; added because they matter more than the ones that are.

**The red team's shape worry is largely misplaced, and it missed the one that bites.**
`%{` never appears. Leading `not` appears on 2 lines in the whole corpus. `split-file`
appears once. What actually appears, on nearly a third of seeds, is
`--split-input-file`: one test file holding many independent modules separated by
`// -----`. A probing input derived from such a seed is not one program, and an
interestingness script that runs the whole file will keep every split alive, so
`circt-reduce` has nothing to remove. `--verify-diagnostics` is the second one: 53 seeds
carry tests whose *expected* behaviour is a diagnostic, so "the tool exited non-zero" is
not evidence of anything for them. Both belong in F-09's interestingness contract.

### D-13 cross-check: the `.sv` region is bigger than `circt-verilog`

| Question | Seeds |
|---|---|
| touch an `ImportVerilog` / `Moore` / `MooreToCore` source file | 48 |
| touch a `.sv` test file | 36 |
| have a `RUN:` line entering via `circt-verilog` | 31 |
| have a `RUN:` line entering via `circt-translate --import-verilog` | 34 |
| union of the two slang entry points | **36** |
| slang-entry seeds whose source files are outside the `.sv` region | 0 |

D-13 says "46 of the 187 seeds depend on it" and calls them "the 46 `.sv`-region seeds".
Neither number reproduces here: the source-file region holds **48** seeds, and the seeds
that actually need a slang-enabled binary number **36**. The 12-seed gap is
`MooreToCore` work whose tests are `.mlir` and whose entry tool is `circt-opt` — those
seeds are first-class in a slang-less build.

**D-13 understates its own scope in a second, more important way.** It is written as if
`circt-verilog` were the only affected binary. It is not: 34 of the 36 seeds enter
through `circt-translate --import-verilog`, and that translation is registered only under
`#ifdef CIRCT_SLANG_FRONTEND_ENABLED` (`tools/circt-translate/circt-translate.cpp:31-32`,
gated by `tools/circt-translate/CMakeLists.txt:4-5`). Verified on the binaries:

```
bassert_g/bin/circt-translate --help | grep -c import-verilog   → 0
circt-sdk/bin/circt-translate --help | grep -c import-verilog   → 1
bassert_g/bin/circt-verilog                                     → does not exist
```

So D-13 option (b), "exclude the 46 `.sv`-region seeds", excludes 36 seeds, not 46; and
D-13 option (a)'s slang build is what restores **both** entry points, not one. A build
that skipped slang would lose `--import-verilog` from a `circt-translate` that FR-03.7
otherwise builds from source — a hole D-13 does not currently describe.

---

## M2 — the `-O3 -UNDEBUG -gline-tables-only` build

**Feeds A-03, D-08, red-team K2 / experiment 2 and 4.**

Scripts: `m2_build.sh` (the build M2 asked for), `m2_three_flags.sh` (the three flag
strings A-03 asks for, under one compiler and one target set), `m2_probe_speed.sh`.
Outputs `raw/m2-*.log`, `raw/m2-sizes.txt`, `raw/m2-symbolizer.txt`,
`raw/m2-threeflags.log`, `raw/m2-probe-speed.txt`.

### The build M2 specified

```
cmake -G Ninja -S ~/.cache/chia-pin-smoke/src -B ~/.cache/chia-pin-smoke/bassert_g \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=<clang-23> -DCMAKE_C_COMPILER=<clang-23> \
  -DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
  -DCMAKE_C_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
  -DLLVM_DIR=<sdk>/lib/cmake/llvm -DMLIR_DIR=<sdk>/lib/cmake/mlir \
  -DLLVM_ENABLE_ASSERTIONS=ON -DLLVM_USE_LINKER=lld \
  -DLLVM_CCACHE_BUILD=ON -DLLVM_PARALLEL_LINK_JOBS=2
ninja -C ~/.cache/chia-pin-smoke/bassert_g -j12 \
  circt-opt firtool circt-translate arcilator circt-reduce
```

| Quantity | Value |
|---|---|
| configure wall (fresh dir) | **3 s** |
| build wall, `-j12`, cold, no ccache | **582 s** (9 min 42 s), rc=0 |
| ninja edges in the target set | **1082** for a fresh tree (confirmed by the two clean builds below); this particular run executed 1076, six tablegen outputs having survived an aborted first attempt |
| `du -sh` of the build directory | **1.3 G** |
| `readelf -S bin/circt-opt \| grep -c debug_line` | **2** (`.debug_line`, `.debug_line_str`) |
| `.debug*` sections present | 8 (`abbrev addr info line line_str rnglists str str_offsets`) |

**One correction to C-02's reach.** The build fails at the first tablegen edge without
the z3 shim on `LD_LIBRARY_PATH`: `mlir-tblgen: error while loading shared libraries:
libz3.so.4`. C-02 records this as a *run-time* need of the SDK; it is also a *build-time*
need, because the SDK's `mlir-tblgen` is what generates CIRCT's `.inc` files. Any
requirement that sets `LD_LIBRARY_PATH` only for probe execution builds nothing.

### K2: does a symbolised frame name a CIRCT source path?

```
nm --defined-only bassert_g/bin/circt-opt | grep _ZN5circt | head -1
  → 0000000003365f30 T _ZN5circt10chooseNameEN4llvm9StringRefES1_
echo 0x3365f30 | circt-sdk/bin/llvm-symbolizer --obj=bassert_g/bin/circt-opt --demangle
  → circt::chooseName(llvm::StringRef, llvm::StringRef)
    /home/adi/.cache/chia-pin-smoke/src/lib/Support/Naming.cpp:47:0
```

The same probe against the existing no-`-g` `-UNDEBUG` build (`bassert`) returns the
demangled name and `??:0:0`.

**K2 is retired.** `-gline-tables-only` gives `file:line` from the SDK's own
`llvm-symbolizer` (LLVM 24.0.0git), so FR-07.4's acceptance criterion is reachable under
FR-03.4's flag string. K2's premise — that the `-UNDEBUG` build carries no debug info —
is confirmed for the build that existed when the red team wrote it, and is fixed by the
flag FR-03.4 already specifies.

### A-03's three flag strings, one compiler, one target set

M2 as specified produces one build, which prices `-gline-tables-only` only against
`bassert`, a build of a *different* target set (`circt-opt`'s closure alone) — and the
`-DNDEBUG` tree on this disk was built by a *different compiler* (`/usr/bin/clang++`
22.1.8). Neither delta would have been clean. So two more builds were run
(`m2_three_flags.sh`), from the same source tree and SDK, the same clang-23, the same
five targets, each from an empty directory:

| | `-O3 -DNDEBUG` | `-O3 -UNDEBUG` | `-O3 -UNDEBUG -gline-tables-only` |
|---|---|---|---|
| build directory | `bassert_n` | `bassert_u` | `bassert_g` |
| configure wall | 4 s | 4 s | 3 s |
| build wall, `-j12`, cold | 621 s | 676 s | **582 s** |
| ninja edges | 1082 | 1082 | 1082 (1076 executed) |
| build dir, `du -sb` | 441,075,357 (420.6 MiB) | 612,299,950 (583.9 MiB) | 1,362,790,328 (1.27 GiB) |
| `circt-opt` | 59,249,008 | 76,316,792 | 200,343,024 |
| `firtool` | 26,410,704 | 34,153,216 | 89,204,048 |
| `circt-translate` | 15,334,272 | 21,442,016 | 68,826,840 |
| `arcilator` | 10,327,504 | 14,247,008 | 45,663,872 |
| `circt-reduce` | 26,243,344 | 36,806,584 | 118,362,200 |
| **five binaries, total** | **137,564,832 (131.2 MiB)** | **182,965,616 (174.5 MiB)** | **522,399,984 (498.2 MiB)** |
| `readelf -S bin/circt-opt \| grep -c debug_line` | 0 | 0 | **2** |
| `nm -u bin/circt-opt \| grep -c __assert_fail` | **0** | **1** | **1** |

The `__assert_fail` row is A-10's own test applied locally, and it is the cleanest
statement of what `-UNDEBUG` buys: the flag is what puts the symbol in the binary.

### The deltas A-03 asks for

| Delta | Binaries (5 tools) | Build directory | `circt-opt` alone |
|---|---|---|---|
| `-UNDEBUG` over `-DNDEBUG` | +45,400,784 B (**+33.0%**) | +171,224,593 B (+38.8%) | +28.8% |
| **`-gline-tables-only` over `-UNDEBUG`** | **+339,434,368 B (+185.5%)** | **+750,490,378 B (+122.6%)** | **+162.5%** |
| both, over `-DNDEBUG` | +384,835,152 B (+279.7%) | +921,714,971 B (+209.0%) | +238.1% |

**Build time is not the cost; size is.** The three wall times, 621 / 676 / 582 s, are not
ordered by flag — the heaviest flag string produced the *fastest* build — so the 16%
spread is background load on a shared desktop, not a flag effect, at n=1 per cell.
`-gline-tables-only` costs essentially nothing in compile time and **nearly triples the
binaries**: the five tools go from 131 MiB to 498 MiB, +324 MiB per image.

### Per-probe slowdown

`m2_probe_speed.sh`, best-of-N on an otherwise idle machine (`raw/m2-probe-speed.txt`):

| Probe | `-DNDEBUG` | `-UNDEBUG` | `-UNDEBUG -gline-tables-only` |
|---|---|---|---|
| 4,000 `comb` ops, `--canonicalize --cse`, best of 9 | 29.63 ms | 29.75 ms (+0.4%) | 30.65 ms (**+3.4%**) |
| `analysis/probe/big.mlir`, `--canonicalize`, best of 15 | 18.17 ms | 18.22 ms (+0.3%) | 18.88 ms (**+3.9%**) |
| `--version` only (start-up), best of 15 | 5.90 ms | 6.18 ms | 5.99 ms |

**The per-probe slowdown A-03 asks for is at most about 4%, and restoring assertions
alone costs under 1%.** The start-up row is flat, so the larger binary does not cost page
faults at these sizes. D-08's "possible per-probe slowdown" under option (a) is real and
negligible.

### What D-08 now has to decide

Not a target set, and not a build budget: a **disk budget**. On host numbers, FR-03.7's
five targets under FR-03.4's flag string cost 582 s and a 1.27 GiB build directory
against 621 s and 421 MiB for the `-DNDEBUG` baseline. What is *not* measured is the
image: no assertions-on image was built, so no `docker save` figure exists, and D-01(c)'s
×38 multiplication cannot yet be priced. For scale, the published `chia-circt` image
already occupies 4.79 GB on disk with a single `-DNDEBUG` `circt-opt` baked in (M5).

---

## M3 — the whole `test/` tree under CHIA's exclusions, assertions on and off

**Feeds A-04, A-20, FR-07.9, red-team W6 / experiment 3.**

Script `m3_lit.sh`; outputs `raw/m3-driver.log`, `raw/m3-driver-attempt1.log`,
`raw/m3-lit-*.txt`, `raw/m3-fail-*.txt`, `raw/m3-unsupported-bassert_g.txt`,
`raw/m3-toolcoverage.txt`.

CHIA's exclusions were read from source: `_LIT_GATE_EXCLUDE_DIRS = ("CAPI",)` and
`_LIT_GATE_FILTER_OUT = "circt-tblgen"` at
`chia:examples/circt_issue_solver/circt_util.py:151-159` (the constants sit at 158-159 in
this checkout, with `circt_lit_gate_paths()` just below), and the invocation shape
`lit --no-progress-bar --filter-out=<re> <paths>` with `cwd` = the build directory at
`chia:chia/chipyard/circt.py:698-762`.

### Attempt 1 ran CHIA's rule verbatim, and lit refused to start

`circt_lit_gate_paths()` yields 22 paths, `test/Tools` among them. lit exited **2 after
0 s with zero tests run**:

```
lit: .../TestingConfig.py:164: fatal: unable to parse config file
  '.../src/test/Tools/circt-tblgen/lit.local.cfg' ...
ValueError: cannot locate MLIR TableGen includes. Have tried:
  include
  /home/adi/.cache/chia-pin-smoke/mlir/include
  /home/adi/.cache/chia-pin-smoke/src/llvm/mlir/include
```

`lit.local.cfg` raises during **discovery**, and `--filter-out` is applied **after**
discovery, so CHIA's documented way of dropping the red `circt-tblgen` directory cannot
work. The cause is that an SDK-based configure leaves `config.mlir_src_root` empty, so
none of the resolver's three candidates exists.

**This is a live defect in CHIA's regression gate, and it is dated.**
`test/Tools/circt-tblgen/lit.local.cfg` landed in CIRCT on **2026-07-16**, commit
`4de8f9882ca1`, "[TableGen] Make dialect TableGen files self-contained (#10724)". It is
absent from the published `chia-circt:latest` image, whose CIRCT tree is pinned at
`5dc7f103d714` (2026-05-24) — verified inside the image. So CHIA's gate works today only
because its image is two months stale; at the FRD's own commit `5056ff04450b` it aborts.
Since F-12's verify gate runs `circt_run_lit` over `circt_lit_gate_paths()`, and a lit
exit of 2 with zero tests is not "green", **every repair would record `lit_ok=false` and
FR-13.6 would never return `report_plus_patch`** — which is precisely the failure mode
A-20 was written to catch, arriving by a different route than A-20 predicted.
A one-line remedy exists and is verified present: the SDK ships
`<sdk>/include/mlir/IR/OpBase.td`, so passing `MLIR_MAIN_SRC_DIR` (or setting
`config.mlir_src_root`) to the SDK's `include` directory satisfies the resolver's first
candidate.

### Attempt 2: `test/Tools` expanded to its subdirectories minus `circt-tblgen`

This is the only way to realise CHIA's stated intent. 25 paths; everything else
unchanged, `--filter-out=circt-tblgen` still passed.

| | assertions ON (`bassert_g`) | assertions OFF (`src/build`) |
|---|---|---|
| flags | `-O3 -UNDEBUG -gline-tables-only` | `-O3 -DNDEBUG` |
| lit wall | 10.06 s | 10.21 s |
| discovered | 1127 | 1127 |
| Passed | 1058 (93.88%) | 1058 (93.88%) |
| Unsupported | 63 (5.59%) | 63 (5.59%) |
| Expectedly Failed (XFAIL) | 6 (0.53%) | 6 (0.53%) |
| **Failed / UNRESOLVED / TIMEOUT / XPASS** | **0** | **0** |
| lit exit code | 0 | 0 |

**Both failing sets are empty, so their difference is empty: the assertion
false-positive set is zero over 1,127 tests.** Files `raw/m3-fail-bassert_g.txt`,
`raw/m3-fail-ndebug.txt`, `raw/m3-fail-assert-only.txt` and `raw/m3-fail-ndebug-only.txt`
are all zero-length.

The assertions-off comparison build was brought to the same five targets first:
`ninja -C ~/.cache/chia-pin-smoke/src/build -j12 circt-opt firtool circt-translate
arcilator circt-reduce` ran 1082 edges in **401 s** (`raw/m3-driver-attempt1.log`).
That 401 s is **not** comparable to M2's 582 s: `src/build` uses `/usr/bin/clang++`
22.1.8, `bassert_g` uses clang-23. The clean three-flag comparison is in M2 above.

**What the zero does and does not cover.** 1050 of the 1127 discovered tests (93.2%)
name at least one binary built from source with assertions on; 75 name only tools that
resolve from the SDK, where assertions are off and nothing can fire; 2 name no recognised
tool (`raw/m3-toolcoverage.txt`). Tool-substitution order is
`[<build>/bin, <mlir tools>, <sdk>/bin]` (`test/lit.cfg.py:61-62`), which is CHIA's own
fallback behaviour, so this is the gate CHIA would actually run and not a local artefact.

**62 of the 63 unsupported tests are `REQUIRES: slang`** (the 63rd is `REQUIRES: zlib`):
36 in `Conversion/ImportVerilog`, 17 in `circt-verilog/`, 9 in
`Tools/circt-verilog-lsp-server`, 1 in `Dialect/ESI`. That is the whole SystemVerilog
frontend surface, skipped rather than run — D-13's cost, measured at the lit level.

---

## M4 — symbol-level contamination

**Feeds A-12, FR-15, red-team W3 / experiment 6.**

Script `m4_contamination.py`; outputs `raw/m4-per-seed.csv`, `raw/m4-summary.txt`,
`raw/m4-gitlog.txt`.

Method. The 187 seeds touch **109** distinct source files under `lib/` and `include/`.
One command supplies both sides of the comparison:

```
git -C <clone> log --first-parent -p --unified=0 --no-renames \
  --format='__C__ %H %cI' --since 2024-09-20T02:42:30+00:00 -- <the 109 paths>
```

488 s, 7.5 MB, **1650** first-parent commits. (On a blobless clone this fetches one blob
per round trip. `git backfill --sparse` over a throwaway sparse worktree bulk-fetches the
same objects in 7 s and is the right tool if this is ever repeated.) Two symbol
extractors are reported, because the red team's rule is crude and the crude rule is the
one the FRD would inherit:

- **ctx** — the identifier git puts in the `@@ … @@ <context>` hunk header. Precise.
- **crude** — every `\b(\w+)\s*\(` on a `+`/`-` line, minus C/C++ keywords. The red team's
  `^[+-].*\b(\w+)\s*\(` rule. Catches callees as well as the enclosing definition.

A seed is contaminated at symbol level if any post-seed first-parent commit that touches
one of the seed's source files also touches one of the seed's functions.

| Rule | Contaminated seeds | Rate |
|---|---|---|
| **file** level — a later commit touches a seed source file at all | 180 / 187 | **96.3%** |
| **symbol** level, ctx rule | 144 / 187 | **77.0%** |
| **symbol** level, crude rule | 148 / 187 | **79.1%** |

Supporting distribution: later first-parent commits per seed — min 0, p25 4, **median
10**, p75 25, max 140; 7 seeds have none. Of the 109 seed source files, **101 (92.7%)**
are touched again, against the red team's 86.1% over all of `lib/`+`include/` — the seeds
sit in busier files than the tree average, as expected.

The 730-day horizon the red team used is not separable here: the corpus is a 24-month
window ending 2026-08-17 and the clone head is 2026-09-11, so every seed's full horizon
is already under 730 days and the two rows are identical.

**Reading.** Narrowing FR-15's screen from file to symbol moves the flag rate from 96.3%
to 77.0% — it clears **36 seeds**, a fifth of the corpus, and leaves three quarters of it
flagged. So symbol-level matching is a real improvement and is **not** a rescue: A-12's
"incomplete by construction" verdict stands, and FR-15.3's mandatory disclosure is still
doing the load-bearing work.

**One honest bound.** 16 seeds yielded no ctx symbol from their own hunks (header-only or
table-only diffs), and all 16 are file-contaminated. They are counted symbol-*clean*,
which is the optimistic direction. The true ctx-rule rate therefore lies in
**[77.0%, 85.6%]**.

---

## M5 — the published CHIA image

**Feeds A-10, A-11, C-13, D-09, D-13, red-team experiment 10.**

Docker is installed and usable without `sudo` (client and server 29.7.2), so this ran.
Output `raw/m5-pull.log`, `raw/m5-image.txt`, `raw/m5-image-lit.txt`.

```
docker pull ghcr.io/ucb-bar/chia-circt:latest
docker run --rm --entrypoint bash ghcr.io/ucb-bar/chia-circt:latest -lc '...'
```

| Quantity | Value |
|---|---|
| digest | `sha256:866aa160d6e40b05a9df538e7fd7e1d914229618b73e82759d7db4879f97b939` |
| created | 2026-09-01T01:15:56Z |
| size on disk (`docker system df`) | **4.79 GB**, 17 layers (`docker image inspect .Size` reports 1,092,058,003 B; the two disagree under docker 29's containerd store — the 4.79 GB figure is the one that costs disk) |
| `nm -u .../bin/circt-opt \| grep -c __assert_fail` | **0** |
| `grep -c NDEBUG .../build/compile_commands.json` | **606**, every one of them `-DNDEBUG` |
| `CMAKE_CXX_FLAGS_RELEASE` in the image's cache | `-O3 -DNDEBUG` |
| `LLVM_ENABLE_ASSERTIONS` in the image's cache | `UNINITIALIZED=ON` (passed, and overridden) |
| SDK's `LLVMConfig.cmake` | `set(LLVM_ENABLE_ASSERTIONS OFF)` |
| `circt-opt --version` | `LLVM version 23.0.0git / Optimized build. / CIRCT 5dc7f10` |

**A-10 is verified on the real artefact and the local reproduction was right.** The
published image's `circt-opt` has no undefined reference to `__assert_fail`: CIRCT's own
assertions are compiled out, exactly as the local reproduction of CHIA's flags predicted.
The `-DLLVM_ENABLE_ASSERTIONS=ON` on the command line is present and ineffective, which
is the observation A-11 rests on (A-11 still lacks its `cmake --trace-expand`, so it
remains an inference about *why*).

Four further facts the image settles, none of them in the FRD:

1. **The image's CIRCT tree is a shallow clone at a release tag, not main.**
   `git clone --depth 1 --branch firtool-1.148.0 https://github.com/llvm/circt.git`, giving
   commit `5dc7f103d714` of 2026-05-24 — 3½ months behind the image's own build date and
   9 releases behind the `firtool-1.157.0` SDK these measurements use. A `--depth 1
   --branch <tag>` clone cannot check out an arbitrary commit without refetching, which
   bears directly on FR-02/FR-03's "build at the run's commit".
2. **Only `circt-opt` is baked in.** `/workspace/circt/build/bin/` holds `circt-opt`,
   `circt-tblgen` and four scripts — nothing else. C-21's six warm-built targets are a
   *run-time* warm-up, not an image layer, so FR-03.7's five targets are five cold builds
   in a fresh container, not one marginal one.
3. **`config.slang_frontend_enabled = 0` in the image's `lit.site.cfg.py`** — D-13's gap
   exists in the published image exactly as C-16 describes.
4. **`config.verilator_path = ""`** — no Verilator in the image, confirming §4.3 and
   D-09's premise directly rather than by absence of a Dockerfile line.

---

## M6 — is a Claude Code CLI installed?

**Feeds D-03.** Nothing was installed and no credential was entered.

| Probe | Result |
|---|---|
| `command -v claude` | not found (exit 1) |
| `~/.claude` | exists, but holds configuration only (`CLAUDE.md`, `plugins`, `projects`, `sessions`, `skills`, …); no binary |
| `~/.local/bin` | no `claude` |
| `~/.npm-global` | does not exist; `npm root -g` = `/usr/lib/node_modules`, which holds `@earendil-works`, `@just-every`, `@openai`, `opencode-ai`, `npm`, `node-gyp`, `nopt`, `semver` — no Anthropic package |
| `find / -xdev -name claude -type f -perm -u+x` | no hits |
| desktop app bundle `/usr/lib/claude-desktop` | `claude-desktop` (Electron) plus `resources/`; no bundled CLI, no `cli.js`, no `claude-code` path |

**No Claude Code CLI is installed on this machine**, so `claude --version` and the two
`--model` acceptance probes could not run and **the acceptance of the model ids
`claude-sonnet-5` and `claude-opus-5` is untested**. D-03's backend question is untouched
by this measurement; C-20 (a backend is a cluster, not a flag) is unaffected either way.

---

## Note on `design/ADR/`, written in parallel with this work

`design/ADR/` did not exist when these measurements started and held fourteen accepted
ADRs by the time they finished; `design/02-HLD.md` appeared in the same window. Nothing
under `design/` or `paper/` was read for input after §7 and §8 of the FRD and §7 of the
red team, and nothing under either was written. Three points of contact, stated here and
**not** applied to those documents:

- **ADR-D-08** names as its follow-up exactly the three-flag build above, and adds A-20's
  set-equality run "against the `-UNDEBUG` build already standing at
  `~/.cache/chia-pin-smoke/bassert`". M3 ran it against `bassert_g` instead, which is the
  same `-UNDEBUG` semantics plus `-gline-tables-only`, and against the `-DNDEBUG` tree for
  the set difference the ADR is actually after. `bassert` itself could not have been used:
  it holds `circt-opt` alone, so most of the suite would have resolved to SDK binaries.
- **ADR-D-13** is Accepted with "a manifest exclusion naming **46** seeds" in its
  acceptance criterion, and derives the 46 from a source-file bucketing (ImportVerilog 31
  + MooreToCore 12 + Moore 3). M1 measures the seeds that actually need a slang-enabled
  binary at **36**; the 12 MooreToCore seeds have `.mlir` tests entering through
  `circt-opt` and are first-class without slang. If the ADR's fallback branch (b) is ever
  taken, the number it should name is 36.
- **ADR-D-13**'s decision and consequences are written around `circt-verilog` alone. 34 of
  the 36 affected seeds enter through `circt-translate --import-verilog`, which is gated by
  the same `CIRCT_SLANG_FRONTEND_ENABLED` and is absent from a slang-less build — verified
  on the binaries. Branch (b) would therefore also change what a from-source
  `circt-translate` can do, which the ADR does not currently say.

Neither the slang build nor any image build was attempted here, so ADR-D-13's timeboxed
question — does slang come up, and what does it add — remains open.

---

## What each assumption or decision now stands on

| ID | Settled | Not settled |
|---|---|---|
| **A-01** | The corpus's *reachability* is now exact: 187 seeds, 331 `RUN:` lines, 72.7% entering via `circt-opt`, 78.1% pure MLIR, 98.9% reducible directly or after a verified lift. F-04's pilot has a measured surface to aim at and a per-seed CSV to draw its 5 seeds from. | Whether an agent turns a seed diff into a *firing* probe. Not touched: this measures the corpus, not the generator. A-01 stays **Unverified**; only red-team experiment 7 retires it. |
| **A-03** | Wall time, edge count, directory size, per-binary size, debug-section count and per-probe cost for all three flag strings, one compiler, one target set, cold and ccache-free. The `-gline-tables-only` delta A-03 calls a required output is measured in isolation. | Image size and per-probe cost *inside a container*, and the ×38 multiplication D-01(c) would need. These are host numbers; a `docker save` was not taken because no assertions-on image was built. |
| **A-04** | Zero assertion false positives over the whole `test/` tree at `5056ff04450b`: 1127 discovered, 1058 pass, 0 fail, identical to the assertions-off build. FR-07.9's control run has its number. | The 75 tests entering only through SDK binaries could not fire a CIRCT assertion, and the SystemVerilog surface (62 tests) was skipped entirely. "No spurious firing on ordinary input" is established for 1050 tests on one commit, not for probing inputs, which are not ordinary. |
| **A-10** | Verified on `ghcr.io/ucb-bar/chia-circt:latest` itself: `nm -u circt-opt \| grep -c __assert_fail` = 0, `-DNDEBUG` on all 606 compile commands, SDK `LLVM_ENABLE_ASSERTIONS OFF`. A-10 moves from **Not inspected** to **verified**, and FR-03's premise holds against the real artefact. | Why the override happens (A-11's `cmake --trace-expand` was not run). And the image is pinned at `firtool-1.148.0` / commit `5dc7f103d714`, so this is verified for *that* tree, not for whatever the campaign's image would be built from. |
| **A-12** | The screen's discrimination is quantified: symbol-level matching flags 77.0% of seeds against file-level 96.3%, clearing 36 seeds. Both rules, both horizons, per-seed CSV. | A-12's actual claim — that siblings fixed in commits with unrelated subjects are missed — is untouched, because this measures *files and functions*, not subjects. A-12 stays **Incomplete by construction**; FR-15.3's disclosure is still required. |
| **D-08** | The decision shrinks to a priced choice: the three flag strings' wall times, sizes and probe costs are in M2's table, and the marginal cost of FR-03.4's `-gline-tables-only` is isolated. D-08's own reframing (C-21: the new target is `circt-reduce` alone) is confirmed against the image, which bakes only `circt-opt`. | The image-level numbers (`docker save`, layer size) and any per-probe cost measured inside a container. D-08 can be resolved on host numbers; it cannot yet quote an image size. |
| **D-13** | Its scope is corrected and measured: **36** seeds need slang, not 46; the region by source file holds 48; and the affected binary is **both** `circt-verilog` *and* `circt-translate --import-verilog`, verified absent from a slang-less build. Option (b)'s cost is 36 seeds (19.3% of the corpus) and 62 lit tests. | Whether option (a)'s slang build comes up, and what it costs. No slang build was attempted here — FR-03.14's timebox is untouched, and D-13's recommendation still rests on an unbuilt assumption. |
