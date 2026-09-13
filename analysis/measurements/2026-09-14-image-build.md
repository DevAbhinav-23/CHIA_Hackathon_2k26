# W-04 — the assertions-on CIRCT image: first build and F-03 acceptance

**Date** 2026-09-14. **Task** W-04 of `05-Work-Plan.md` §9. **Closes, in part** A-03, A-10, A-11,
A-16; leaves A-20 half open (below).

Everything here was executed on this host. Scripts sit beside this file as `w04_*.{sh,py}`; raw
output is under `raw/`:

| Artefact | Path |
|---|---|
| build transcript, attempt 2 (the successful one) | `raw/image-build.log` |
| build transcript, attempt 1 (failed) | `raw/image-build-attempt1-scandeps.log` |
| pin selection | `raw/w04-pin-select.txt` |
| in-image acceptance run | `raw/w04-verify.txt` |
| lit runs | `raw/w04-lit.txt` |
| per-probe cost and the symbolised frame | `raw/w04-probe-speed.txt` |
| FR-03.13 negative control | `raw/w04-neg-target.log` |
| FR-03.2 negative control | `raw/w04-neg-pin.log` |
| **hash manifest (FR-03.16)** | **`raw/image-manifest.json`** |

The Dockerfile and its workflow are in the working clone at `~/Projects/chia-bugloop`, branch
`bugloop`, cut from `ucb-bar/chia` `main` at `16c35e92`:

- `dockerfiles/ChiaCirctAssertDockerfile`
- `.github/workflows/chia-circt-assert.yml`

Nothing was pushed to any remote.

---

## 1. The commit and the tag

`03-LLD.md` §3.4's selector was run by hand against `~/.cache/chia-pin-smoke/circt` after
`git fetch --all --tags`, by `w04_select_pin.py`: the newest first-parent `origin/main` commit whose
`llvm` gitlink equals some `firtool-*` tag's `llvm` gitlink, equality of full 40-character SHAs.

| Quantity | Value |
|---|---|
| clone `origin/main` HEAD | `eab8d18294469806fa48998f44da5c96eafe1d1b`, 2026-09-12 |
| HEAD's `llvm` pin | `e297b52ec9d8b5c38042e53ae5650922717970cd` |
| **HEAD's pin has a release** | **no** — so ADR-D-10's rule applies and the newest commit that does is used |
| **`CIRCT_SHA`** | **`eade0de61bc5a0d2ba1b9da951b69efcab19f8ce`**, 2026-09-07, *[HW] Preserve attributes in PortConverter (#11082)* |
| its `llvm` pin | `6279700538792da0c5a08e17babfe9b6e824c69f` |
| tags sharing that pin, newest first | `firtool-1.159.0`, `firtool-1.158.0`, `firtool-1.157.0` |
| **`CIRCT_VER`** | **`firtool-1.159.0`** (newest by tag date, per FR-02.6; all three recorded) |
| **lag, commits** | **8** first-parent commits behind `main` |
| **lag, days** | **4.807** |

The eight commits between the chosen one and HEAD all sit in the same untagged pin window, which is
why the lag is exactly the width of that window and not a search artefact
(`raw/w04-pin-select.txt` prints the per-commit pin for the newest twelve).

`firtool-1.159.0` happens to *point at* `eade0de6`, so source commit and release commit coincide
here. That is a property of this window, not of the selector: the selector compares gitlinks and
never tag identity, and FR-03.1's fetch-by-SHA is exercised either way.

---

## 2. The build

```
docker build -f dockerfiles/ChiaCirctAssertDockerfile \
  -t chia-circt-assert:eade0de61bc5 \
  --build-arg CIRCT_SHA=eade0de61bc5a0d2ba1b9da951b69efcab19f8ce \
  --build-arg CIRCT_VER=firtool-1.159.0 \
  --build-arg BUILD_JOBS=8 .
```

| Quantity | Value |
|---|---|
| attempt 0 | **rejected by the CLI**, rc=125, 0 s: `--progress` is a BuildKit flag (§3, failure 0) |
| attempt 1 | **failed**, rc=1, 268 s (§3, failure 1) |
| **attempt 2, wall** | **972 s (16 min 12 s)**, rc=0, 01:00:25 → 01:16:37 +05:30 |
| ninja edges | **1371**, all executed, cold, ccache empty |
| ninja parallelism | `-j8`, link jobs capped at 2 |
| `du -sh /workspace/circt/build` | **1.7 G** |
| `du -sh /opt/circt-sdk` | 661 M |
| six tool binaries, total | **703,211,208 B (670.6 MiB)** |
| `docker image inspect --format '{{.Size}}'` | **1,912,742,097 B** (Docker's content size) |
| `docker images` disk usage | **8.44 GB**, which counts the shared base layers |
| **layers** (`len .RootFS.Layers`) | **23** |
| the same two numbers for the base `ghcr.io/ucb-bar/chia-circt:latest` | 1,092,058,003 B content, 4.79 GB disk, **17** layers |
| image ID | `sha256:8ac3cb311851ab5af1b21925b579f6b770346148cd3c6012e45b3b9d8256cf9e` |
| RepoDigest | **none** — the image was not pushed, so `.RepoDigests` is empty; the manifest records the ID instead and says so |

Per-binary, from `du -sb` inside the image:

| Binary | Bytes | M2/M7 host reference (different commit) |
|---|---|---|
| `circt-opt` | 217,251,208 | 200,343,024 (M2, no slang) |
| `circt-reduce` | 132,128,112 | 118,362,200 (M2) |
| `circt-translate` | 130,715,592 | 120,014,768 (M7, slang) |
| `firtool` | 97,039,424 | 89,204,048 (M2) |
| `circt-verilog` | 75,559,336 | 71,310,864 (M7, slang) |
| `arcilator` | 50,517,536 | 45,663,872 (M2) |

Each is 7–9% larger than its host reference. The references are a different CIRCT commit (`5056ff04`,
eight first-parent commits earlier) built with a different compiler (clang-23 there, Ubuntu clang
18.1.3 here), so this is not a clean delta and is not offered as one. **The `-gline-tables-only`
delta itself is not re-measured here**: doing that at image level needs a second image differing only
in the flag string, which is the same second build FR-03.6 needs (§7).

**A-03's image half, stated plainly.** 972 s of wall, 1.7 GB of build tree, 670.6 MiB of binaries,
3.65 GB of image on disk over CHIA's own CIRCT image, 6 added layers. The cost is disk, as M2
predicted; the build time is not the problem.

Per-probe cost, inside a container of this image, best-of-N
(`w04_probe_speed.sh`, `raw/w04-probe-speed.txt`):

| Probe | This image |
|---|---|
| `circt-opt --version`, best of 15 | 18.55 ms |
| 4,000 `comb` ops, `--canonicalize --cse`, best of 9 | 91.28 ms |

These are **absolute in-container numbers, not a delta**: M2's host figures (5.90 ms and 30.65 ms)
were taken outside a container, on a different compiler, at a different commit, on a generated input
this run did not reproduce byte for byte. A per-probe *slowdown* at image level remains unmeasured;
M2's host measurement of at most about 4% is the only figure this design has.

---

## 3. Every failure, and its fix

**Failure 0 — `docker build --progress=plain` is not available on this host.**

```
DEPRECATED: The legacy builder is deprecated ... Install the buildx component
unknown flag: --progress                                              rc=125
```

`docker buildx version` prints `docker: unknown command: docker buildx`, and no CLI-plugin directory
exists (`~/.docker/cli-plugins`, `/usr/lib/docker/cli-plugins`, `/usr/libexec/docker/cli-plugins` all
absent; `pacman -Q docker-buildx` reports the package is not installed). **Fix:** drop the flag and
use the legacy builder, whose output is already per-step plain text — `raw/image-build.log` carries
every `Step n/20` header and every command's full output, which is what the flag was asked for. No
system package was installed to work around this.

**Failure 1 — the slang build has no dependency scanner.** Attempt 1 stopped at ninja edge 280 of
1371, 268 s in:

```
FAILED: _deps/slang-build/source/CMakeFiles/slang_slang.dir/AllSyntax.cpp.o.ddi
"CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS-NOTFOUND" -format=p1689 -- ...
/bin/sh: 1: CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS-NOTFOUND: not found
```

on every `_deps/slang-build` `.ddi` edge. CMake scans C++20 targets for module dependencies, slang is
built to C++20 (`include(SlangCompilerOptions)`), and CHIA's base installs `clang` but not the
package carrying `clang-scan-deps`. **Turning the slang front end on (FR-03.14) is what creates this
dependency**, which is why no CHIA image has ever needed it and why M7 did not hit it: M7's compiler
was a full LLVM build tree that ships the scanner next to `clang++`.

**Fix:** add `clang-tools` to the apt line. Verified independently before rebuilding, on a throwaway
container: with `clang-tools` installed, a minimal C++20 CMake project resolves
`CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS:FILEPATH=/usr/bin/clang-scan-deps-18`. Ubuntu's package ships
**only** the version-suffixed binary — there is no unversioned `/usr/bin/clang-scan-deps` — and CMake
finds it anyway because it searches the compiler's major version suffix first. Attempt 2 then ran all
1371 edges to completion.

No other failure occurred. The Dockerfile was edited once.

---

## 4. FR-03 acceptance

Numbering is the FRD's. The task brief's numbering runs one lower from FR-03.3 onward; the mapping is
noted where it differs.

| ID | Verdict | Evidence |
|---|---|---|
| FR-03.1 fetch by SHA | **PASS** | `git -C /workspace/circt rev-parse HEAD` → `eade0de61bc5a0d2ba1b9da951b69efcab19f8ce`; `git log -1` → `2026-09-08T00:08:17+08:00 [HW] Preserve attributes in PortConverter (#11082)` |
| FR-03.2 pin equality, tag independent of commit | **PASS**, both directions | In-image: `ls-tree eade0de6 llvm` and `ls-tree firtool-1.159.0 llvm` both print `160000 commit 6279700538792da0c5a08e17babfe9b6e824c69f`; the `test` prints `EQUAL`. Build log line 226–227: `PIN CHECK source=6279…9f sdk=6279…9f` / `PIN CHECK PASSED`. **Negative control, end to end**: the same build with `CIRCT_VER=firtool-1.156.0` (pin `44a65223cc4ba384d231f33aa9121c3fef37d435`) exits rc=1 at Step 15/20 printing `PIN CHECK FAILED`; `grep -c "ninja: Entering"` over that log is **0**, so it failed *before* ninja started, and no image exists under the tag (`raw/w04-neg-pin.log`) |
| FR-03.3 SDK strip retained | **PASS** | `/opt/circt-sdk/include/circt` and `/opt/circt-sdk/lib/cmake/circt` both `No such file or directory`; the guard prints `BOTH ABSENT` |
| FR-03.4 the flag string *(brief's "FR-03.3"/"FR-03.4")* | **PASS** | `CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -UNDEBUG -gline-tables-only` and the C equivalent in `CMakeCache.txt`; `grep -c -- -DNDEBUG compile_commands.json` = **0**; `grep -c -- -UNDEBUG compile_commands.json` = **778** = the compile-command count (`len(json.load(...))` = 778), so **every** compile command carries it; `readelf -S bin/circt-opt \| grep -c debug_line` = **2**, sections `.debug_abbrev .debug_addr .debug_info .debug_line .debug_line_str .debug_rnglists .debug_str .debug_str_offsets` |
| FR-03.5 assertions in the binaries | **PASS, new baseline recorded** | `nm -u \| grep -c __assert_fail` = **1** for all six targets. `obj.CIRCT` objects: **555 total, 536 referencing (96.58%), 19 not**, named in `raw/w04-verify.txt`. This is a **new** baseline, not a drift: FINAL Appendix A's 18-object list is a different commit *and* a different target set (five targets, no slang). The 19 are interface/registration/pipeline translation units plus `Support/{APInt,Debug,Passes,ProceduralRegionTrait,Version}` and `Tools/arcilator/pipelines` — the same shape as the recorded 18 |
| FR-03.6 lit no redder than `-DNDEBUG` | **NOT CHECKED** | Needs two images differing only in the flag string; one exists. What *is* measured is the assertions-on half: **zero** Failed / UNRESOLVED / TIMEOUT / XPASS over CHIA's whole gate scope (§5). A-20's image half stays open; the closing command is §7 |
| FR-03.7 target list, as a parameter | **PASS** | All six exist under `/workspace/circt/build/bin` and run `--version`; all print `LLVM version 24.0.0git` and the four that carry a CIRCT version string print `CIRCT eade0de`. The list is `ARG TOOL_TARGETS`, and the FR-03.13 control below proves it is read |
| FR-03.8 lit, libz3, Verilator; lit once | **PASS** | `command -v lit` → `/home/ray/anaconda3/envs/py_worker/bin/lit`, `lit 23.1.1` — the exact path `chia/chipyard/circt.py:608` checks; `verilator --version` → `Verilator 5.020 2024-01-01 rev (Debian 5.020-1)`; `arcilator --version` runs; `ldd /opt/circt-sdk/bin/circt-opt \| grep z3` → `libz3.so.4 => /lib/x86_64-linux-gnu/libz3.so.4`; a second `pip install lit` prints `Requirement already satisfied: lit in .../site-packages (23.1.1)` and installs nothing, which is FR-03.8's AC verbatim |
| FR-03.9 CHIA compatibility | **PASS** inside the image; **the `chia up` half is untested** | `Python 3.10.19` at `/home/ray/anaconda3/envs/py_worker/bin/python`; `ray 2.54.0`; `chialoops 1.0.1` installed, `chia.chipyard.circt` imports from `/workspace/chia/chia/chipyard/circt.py`; `bash 5.2.21`, login shell; `ssh -V` → `OpenSSH_9.6p1 Ubuntu-3ubuntu13.19`; `rsync --version` → `rsync version 3.2.7 protocol version 31`. The requirement's own AC also asks for a `chia up` bringing a worker Ready — that is a cluster action and is W-08/W-16's, not this task's |
| FR-03.10 emit the `ImageSpec` | **PARTIAL** | The inputs an `ImageSpec` is built from are emitted, as `raw/image-manifest.json` and as `BUGLOOP_*` environment variables inside the image. The `ImageSpec` object itself is `bug_loop.build_image`'s (`03-LLD.md` §4.11.1), which is W-16's code and does not exist yet |
| FR-03.11 reports state the flag | **N/A here**, precondition confirmed | `circt-opt --version` still prints `Optimized build.` after `-UNDEBUG` (C-08 holds at this commit and this SDK). Whether a generated `Report` carries the literal `-UNDEBUG` is F-10's, not F-03's |
| FR-03.12 MLIR/LLVM assertions stay off | **PASS** | `/opt/circt-sdk/include/llvm/Config/abi-breaking.h:19` → `#define LLVM_ENABLE_ABI_BREAKING_CHECKS 0` |
| FR-03.13 no partial image under the tag | **PASS** | A build with `TOOL_TARGETS="circt-opt no-such-target"` exits rc=1 at Step 17/20 with `ninja: error: unknown target 'no-such-target'`, and `docker image inspect chia-circt-assert:broken-target-test` finds nothing (`raw/w04-neg-target.log`). The "report which targets succeeded" half belongs to `build_image` step 2, not to the Dockerfile |
| FR-03.14 both slang entry points | **PASS** | `circt-verilog --version` → `CIRCT eade0de` **and** `slang version 11.0.385+44dc55f99`, so it names the image's CIRCT commit and its slang; `circt-translate --help \| grep -c import-verilog` = **1**, the line being `--import-verilog  - import Verilog or SystemVerilog`; `CIRCT_SLANG_FRONTEND_ENABLED:BOOL=ON` and `CIRCT_SLANG_BUILD_FROM_SOURCE:BOOL=ON` in `CMakeCache.txt`. **ADR-D-13 resolves to branch (a); no seed exclusion is needed** |
| FR-03.15 one Verilator version | **PASS** | `Verilator 5.020 2024-01-01 rev (Debian 5.020-1)`, exactly what M8 predicted apt would give; `--x-assign` and `--x-initial` both present. Recorded in the manifest as `verilator_version` with the binary's SHA-256 |
| FR-03.16 hash manifest from the published image | **PASS** | `raw/image-manifest.json` names all six targets with path and SHA-256, plus `llvm-symbolizer` and `verilator`. Computed in a **freshly started container**, and reproduced: two independent `docker run --rm` invocations produced identical hashes, e.g. `circt-opt` = `dcb9599a27a063a1d604873bb20daae29a0a1960a145073973b56b496b51d042` |
| FR-03.17 `MLIR_SOURCE_DIR` and lit discovery | **PASS** | `grep mlir_src_root build/test/lit.site.cfg.py` → `config.mlir_src_root = "/opt/circt-sdk"`; `lit --no-progress-bar --show-tests /workspace/circt/build/test` exits **0**, discovers **1,390** tests, prints **zero** `unable to parse config file` lines, and lists **253** tests under `Tools/circt-tblgen/` — the directory whose `lit.local.cfg` aborted discovery in M3 |

Other tooling the task asked for, all inside the image:

| Command | Output |
|---|---|
| `prlimit --version` | `prlimit from util-linux 2.39.3` |
| `python -c "import ray; print(ray.__version__)"` (py_worker env) | `2.54.0` |
| `ssh -V` | `OpenSSH_9.6p1 Ubuntu-3ubuntu13.19, OpenSSL 3.0.13 30 Jan 2024` |
| `rsync --version \| head -1` | `rsync  version 3.2.7  protocol version 31` |
| `command -v FileCheck not count split-file` | all four from `/opt/circt-sdk/bin` |
| toolchain | Ubuntu clang 18.1.3, ninja 1.11.1, cmake 3.28.3, git 2.43.0 |

**A-11 (why `-DLLVM_ENABLE_ASSERTIONS=ON` is ineffective), settled by reading both sides.**
`CMakeCache.txt:474` records `LLVM_ENABLE_ASSERTIONS:UNINITIALIZED=ON` — CHIA's value, accepted into
the cache — and `/opt/circt-sdk/lib/cmake/llvm/LLVMConfig.cmake:173` executes
`set(LLVM_ENABLE_ASSERTIONS OFF)` when `find_package(LLVM)` runs, which is after the cache is read
and which therefore wins in the directory scope every CIRCT target is configured in. The flag is kept
because removing a line CHIA passes would be a change to CHIA's base rather than an addition to it.
No `cmake --trace-expand` was run: the two lines above are the whole mechanism, and a trace would
restate them at the cost of a second configure.

**A-16 (the SDK's z3 path, exercised once).** `/opt/circt-sdk/bin/circt-bmc` exists and runs against
the image's `libz3.so.4`:

```
$ circt-bmc /tmp/bmc.mlir --module=t -b 1 --shared-libs=/opt/circt-sdk/lib/libCIRCTSMTToZ3LLVM.so
/tmp/bmc.mlir:0:0: warning: no property provided to check in module - will trivially find no violations.
Bound reached with no violations!                                      rc=0
```

so the image's z3 handling is exercised rather than assumed. It gates nothing.

**FR-07.4's precondition, confirmed at image level.** `llvm-symbolizer` resolves a source-built frame
to a file and a line inside the image:

```
$ echo 0x34fe940 | /opt/circt-sdk/bin/llvm-symbolizer --obj=.../bin/circt-opt --demangle
circt::chooseName(llvm::StringRef, llvm::StringRef)
/workspace/circt/lib/Support/Naming.cpp:47:0
```

---

## 5. lit

Both runs are inside the image, `cwd` the build directory, `-j8`, `lit 23.1.1`, at `eade0de6`
(`raw/w04-lit.txt`).

**Run 1 — the slice FR-03.6 names**, `test/Dialect/{FIRRTL,HW,Comb,Seq}` and `test/Conversion`,
with `--filter-out=circt-tblgen`:

| | Value |
|---|---|
| exit code | **0** |
| wall | 5.77 s |
| discovered | **523** |
| **Passed** | **519 (99.24%)** |
| Expectedly Failed (XFAIL) | 4 |
| **Failed / UNRESOLVED / TIMEOUT / XPASS** | **0** |

The FRD's reference measurement over the same five directories at `5056ff04` is 520 of 523 under
`-UNDEBUG`, its three failures traced to a stale SDK `circt-translate`. This image has **zero**, and
the mechanism is consistent with that attribution: `circt-translate` here is built from source **with
the slang front end**, so the tests that resolved to the SDK's stale binary now resolve to the
image's own. Consistent with, not proof of — the two runs are eight first-parent commits apart.

**Run 2 — CHIA's own gate scope, verbatim** (`circt_lit_gate_paths()`: every top-level `test/<dir>`
except `CAPI`, 22 paths, plus `--filter-out=circt-tblgen`). This is the FR-07.9 control run:

| | Value |
|---|---|
| exit code | **0** |
| wall | 9.78 s |
| discovered | **1380** |
| Excluded by `--filter-out=circt-tblgen` | 253 |
| **actually considered** | **1127** |
| **Passed** | **1119 (81.09% of discovered, 99.29% of considered)** |
| Unsupported | **1** |
| Expectedly Failed (XFAIL) | 7 |
| **Failed / UNRESOLVED / TIMEOUT / XPASS** | **0** |
| `unable to parse config file` lines | **0** |

Two things in that table are the point of this whole image.

**CHIA's rule now runs at all.** M3 ran `circt_lit_gate_paths()` verbatim on the host at `5056ff04`
and lit exited **2 after 0 s with zero tests**, because `test/Tools/circt-tblgen/lit.local.cfg` raises
during discovery and `--filter-out` is applied after discovery. Here the same 22 paths discover 1380
tests and the 253 `circt-tblgen` tests are dropped by the exclusion CHIA declares, which is exactly
what FR-03.17 was added to restore. FR-12.8's `lit_unusable` branch is, on this image, unreachable.

**The 62 `REQUIRES: slang` tests are running.** M3 recorded 63 Unsupported on the host, 62 of them
`REQUIRES: slang`; this image has **1** (the `REQUIRES: zlib` one). The considered set is 1127 in
both runs and the arithmetic lines up exactly: 1058 Passed + 63 Unsupported + 6 XFAIL there against
1119 + 1 + 7 here, so 61 tests moved from Unsupported to Passed and one to XFAIL. **The whole
SystemVerilog front-end surface is now exercised, and it is green.**

---

## 6. Deviations from `03-LLD.md` §4.11, with reasons

1. **The image is `FROM ghcr.io/ucb-bar/chia-circt:latest` and re-installs the SDK at
   `${CIRCT_VER}`.** §4.11 and §1.2 describe an image built on CHIA's base layers, which implies the
   base's own `CIRCT_VER`. Measured: the published base's SDK is **`firtool-1.148.0`, LLVM 23.0.0git**
   and its source tree is `5dc7f103d714` (2026-05-24). FR-03.2 requires the SDK tag to be a parameter
   of *this* image, so the SDK must be re-installed here; rebuilding CHIA's base with the right
   `CIRCT_VER` instead would add its own `ninja circt-opt` (~30 min by CHIA's own comment) plus the
   sbt/JDK/Python/Ray downloads, and would not fit the task's 90-minute cap. The child image is used
   rather than the base because FR-03.9 wants the `chia` package installed and the child is the layer
   that installs it. CHIA's strip (FR-03.3) is re-applied to the re-installed SDK, and is verified
   absent above. `BASE_IMAGE` is an `ARG`, so a correctly-pinned base can be substituted later with
   no Dockerfile edit.
2. **`-DLLVM_PARALLEL_LINK_JOBS=2` added to the configure line.** §4.11's block is twelve lines and
   does not carry it; the *measured* recipe does (`m2_build.sh`, `m7_slang_build.sh`). Reason:
   `-gline-tables-only` nearly triples the binaries — `circt-opt` is 217 MB here — and eight
   concurrent `lld` links of binaries that size do not fit in a 15 GB host that already has 10 GB in
   use. It constrains ninja's scheduling only and never reaches the compiler, so no binary differs
   because of it. **`03-LLD.md` §4.11's block should gain this line.**
3. **`clang-tools` added to the apt line**, making it five additions rather than §4.11's four.
   Reason: failure 1 of §3. This is a consequence of FR-03.14, not of anything §4.11 got wrong, and
   §4.11's apt paragraph should name it for the same reason it names `util-linux`.
4. **`rm -rf /workspace/circt/build` immediately before `cmake -B build -S .`.** §4.11 gives the
   configure line and is silent on the base's existing build directory. That directory was configured
   against a different SDK (LLVM 23) and a different source commit, and every object in it would be
   rebuilt anyway because the flag string changed, so removing it costs nothing in image size (the
   base's copy stays in a lower layer either way) and removes a class of stale-cache failure. Folded
   into the same `RUN` as the configure.
5. **`--progress=plain` dropped from the `docker build` command.** Host has no BuildKit/buildx;
   failure 0 of §3. Not a Dockerfile change.
6. **`chmod -R a+rwX /workspace/circt` is folded into the ninja `RUN`, not a layer of its own.** A
   recursive chmod in a separate layer copies every file of a freshly written 1.7 GB tree up and
   would roughly double the image. §4.11 does not mention the chmod at all; CHIA's base has it as its
   own layer, where it is correct because the tree below it is in a lower layer.
7. **An `ENV BUGLOOP_*` block records the commit, tag, target list, flag string and slang setting.**
   An addition, not a change: it is what makes FR-03.10 and FR-03.11 answerable from inside a running
   worker without re-deriving anything, and it is the last layer so it invalidates nothing.

Two things §4.11 leaves as parameters and this build simply names: `<jobs>` is `ARG BUILD_JOBS=8`,
and `CIRCT_PKG` keeps CHIA's own default `circt-full-shared-linux-x64.tar.gz`.

---

## 7. What is still open

- **FR-03.6 / A-20's image half.** One command away, and it is a second image:
  `docker build ... -t chia-circt-assert:ndebug-eade0de61bc5 --build-arg
  CXX_FLAGS_RELEASE="-O3 -DNDEBUG -gline-tables-only" ...`, then `w04_lit_runs.sh` inside it and
  `comm` over the two sorted failing-name sets. Both sets are expected to be empty, since the
  assertions-on set measured here already is; the criterion is set equality, so an empty pair
  satisfies it. Budget: ~16 min and ~2.5 GB. This is W-04b in `05-Work-Plan.md` §6.
- **The `-gline-tables-only` size and time delta at image level** falls out of that same second
  build for free.
- **FR-03.9's `chia up` half**, which needs a cluster YAML that does not exist until W-16.
- **FR-03.10's `ImageSpec`**, which is `bug_loop.build_image`'s object and is W-16's code. The
  manifest written here is its input, not its replacement.
- **A per-probe slowdown at image level.** §2's two numbers are absolute, not a delta; the delta
  needs the same second image.
- **The image is not published.** No registry, no push, so `RepoDigests` is empty and the manifest
  records the image ID. `bug_loop.build_image` step 8 is what fills that field.

---

# W-04b — the assertions-off twin, and what the flag string costs

**Date** 2026-09-14. **Task** W-04b of `05-Work-Plan.md` §6, the item §7 above left open.
**Closes** FR-03.6, A-20's image half, and A-03's flag-string cost at image level.

Scripts sit beside this file as `w04b_*.{sh,py}`; raw output is under `raw/`:

| Artefact | Path |
|---|---|
| build transcript | `raw/w04b-image-build.log`, `raw/w04b-image-build.rc` |
| in-image size/flag report, both images | `raw/w04b-sizes-assert.txt`, `raw/w04b-sizes-ndebug.txt` |
| lit, both images | `raw/w04b-lit-assert.txt`, `raw/w04b-lit-ndebug.txt` |
| the two failing-name sets and the `comm` | `raw/w04b-failset-{gate,slice}-{assert,ndebug}.txt`, `raw/w04b-comm-gate.txt` |
| per-probe cost, both images | `raw/w04b-probe-assert.txt`, `raw/w04b-probe-ndebug.txt` |
| driver | `w04b_run_all.sh` |

**No Dockerfile change was needed and nothing was committed.** `ChiaCirctAssertDockerfile:52`
already reads `ARG CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only"` — the flag string is
already a build arg with the assertions-on default — so the twin is one `--build-arg` away and
the default build is byte-identical in behaviour by construction, not by re-verification.

---

## 1. The build

```
docker build -f dockerfiles/ChiaCirctAssertDockerfile \
  -t chia-circt-ndebug:eade0de61bc5 \
  --build-arg CIRCT_SHA=eade0de61bc5a0d2ba1b9da951b69efcab19f8ce \
  --build-arg CIRCT_VER=firtool-1.159.0 \
  --build-arg CXX_FLAGS_RELEASE="-O3 -DNDEBUG -gline-tables-only" \
  --build-arg BUILD_JOBS=8 .
```

`CIRCT_SHA`, `CIRCT_VER`, `TOOL_TARGETS`, `SLANG`, `BUILD_JOBS` and
`-DLLVM_PARALLEL_LINK_JOBS=2` are all W-04's; `CXX_FLAGS_RELEASE` is the only difference.

| Quantity | assertions on (W-04) | assertions off (W-04b) |
|---|---|---|
| tag | `chia-circt-assert:eade0de61bc5` | **`chia-circt-ndebug:eade0de61bc5`** |
| exit code | 0 | **0** |
| **wall** | **972 s** | **793 s (13 min 13 s)**, 01:37:05 → 01:50:18 +05:30 |
| ninja edges | 1371, all executed | **1371, all executed** |
| ccache hits during the build | cold | **2 of 1262 cacheable calls (0.16%)** — cold |
| Docker steps served from cache | 8 (`SHELL` + the seven `ARG`s) | **the same 8** |
| Docker steps re-run | 11–20 (apt, pip, SDK, fetch, configure, ninja, env) | **the same 11–20** |
| image ID | `sha256:8ac3cb3118…` | `sha256:ee370a126d0d…` |
| layers | 23 | **23** |

The two builds therefore ran the *same* work: the legacy builder invalidates at the first `RUN`
below the changed `ARG`, so apt, pip, the SDK download and the fetch re-ran in both, and neither
build got a warm ccache. **The 179 s (−18.4%) is the assertions' share of build time**, not a
caching artefact.

---

## 2. Size — what `-UNDEBUG` costs the image

Per-binary, `du -sb` inside each image (`raw/w04b-sizes-*.txt`):

| Binary | `-UNDEBUG` | `-DNDEBUG` | delta | |
|---|---|---|---|---|
| `circt-opt` | 217,251,208 | 173,725,000 | +43,526,208 | **+25.05%** |
| `circt-reduce` | 132,128,112 | 103,471,496 | +28,656,616 | +27.70% |
| `circt-translate` | 130,715,592 | 107,050,024 | +23,665,568 | +22.11% |
| `firtool` | 97,039,424 | 76,580,664 | +20,458,760 | +26.72% |
| `circt-verilog` | 75,559,336 | 64,265,208 | +11,294,128 | +17.57% |
| `arcilator` | 50,517,536 | 39,810,936 | +10,706,600 | +26.89% |
| **six targets, total** | **703,211,208** | **564,903,328** | **+138,307,880** | **+24.48%** |

| Quantity | `-UNDEBUG` | `-DNDEBUG` | delta |
|---|---|---|---|
| `du -sb /workspace/circt/build` | 1,796,502,200 | 1,441,126,307 | **+355,375,893 (+24.66%)** |
| the ninja layer (`docker history`) | 1.94 GB | 1.57 GB | +0.37 GB |
| `docker system df` unique size | 3.656 GB | 3.179 GB | +0.477 GB |
| `docker image inspect .Size` (content, compressed) | 1,912,742,097 | 1,809,494,659 | +103,247,438 (+5.71%) |
| `du -sb /opt/circt-sdk` | 677,901,751 | 677,901,751 | 0 |

The two size columns measure different things and both are reported because they differ by more
than rounding: this host's Docker uses the containerd image store, where `.Size` is the sum of the
**compressed** blobs and `docker system df`'s unique size is the **unpacked** bytes on disk. The
unpacked delta (0.477 GB) is the one that matters for a worker's disk and it agrees with the layer
delta (0.37 GB) and the build-tree delta (0.355 GB) to within what `du` and layer tar accounting
differ by anyway.

Everything else in the two reports is identical (`diff -u` over `raw/w04b-sizes-*.txt` shows only
the flag string, the assertion counts and the sizes). In particular **the debug sections are the
same in both**: `readelf -S bin/circt-opt | grep -c debug_line` = 2 and the same eight `.debug_*`
sections, because `-gline-tables-only` is in *both* flag strings. That is what makes the delta
above the assertions' cost and nothing else's.

The flag reached every compile command in both images: 778 compile commands, **778** carrying
`-DNDEBUG` and 0 carrying `-UNDEBUG` in the twin, exactly inverted from W-04.

`__assert_fail`, the mechanical statement of what this whole image is for:

| | `-UNDEBUG` | `-DNDEBUG` |
|---|---|---|
| the six targets with an undefined `__assert_fail` | **6 of 6** | **0 of 6** |
| `obj.CIRCT` objects referencing `__assert_fail` | **536 of 555 (96.58%)** | **0 of 555** |

---

## 3. lit, in both images — the assertion false-positive set

Both runs use `w04b_lit_runs.sh`, which is W-04's `w04_lit_runs.sh` plus machine-readable markers
around the failing-name sets. Same scope, same `--filter-out=circt-tblgen`, same `-j8`, same
`lit 23.1.1`, same commit `eade0de6`, run back to back with nothing else on the host.

**Run 1 — the FRD slice**, `test/Dialect/{FIRRTL,HW,Comb,Seq}` + `test/Conversion`:

| | `-UNDEBUG` | `-DNDEBUG` |
|---|---|---|
| exit code | 0 | **0** |
| wall | 5.91 s | 5.83 s |
| **Discovered** | **523** | **523** |
| **Passed** | **519 (99.24%)** | **519 (99.24%)** |
| Expectedly Failed | 4 | 4 |
| **Failed / UNRESOLVED / TIMEOUT / XPASS** | **0** | **0** |

**Run 2 — CHIA's gate scope verbatim** (`circt_lit_gate_paths()`, 22 paths, `--filter-out=circt-tblgen`):

| | `-UNDEBUG` | `-DNDEBUG` |
|---|---|---|
| exit code | 0 | **0** |
| wall | 9.82 s | 9.68 s |
| **Discovered** | **1380** | **1380** |
| Excluded by `--filter-out` | 253 | 253 |
| **considered** | **1127** | **1127** |
| **Passed** | **1119 (99.29% of considered)** | **1119 (99.29% of considered)** |
| Unsupported | 1 | 1 |
| Expectedly Failed | 7 | 7 |
| **Failed / UNRESOLVED / TIMEOUT / XPASS** | **0** | **0** |
| `unable to parse config file` | 0 | 0 |

The two failing-name sets, from the markers, sorted:

```
$ wc -l raw/w04b-failset-gate-assert.txt raw/w04b-failset-gate-ndebug.txt
0 raw/w04b-failset-gate-assert.txt
0 raw/w04b-failset-gate-ndebug.txt
$ comm raw/w04b-failset-gate-assert.txt raw/w04b-failset-gate-ndebug.txt
                                        (no output)
assert-only  0
ndebug-only  0
both         0
```

**The assertion false-positive set is empty.** Not "small", not "tractable" — there is no test in
CHIA's gate scope that this CIRCT commit passes with assertions compiled out and fails with them
compiled in. The FRD slice gives the same answer. Both sets are empty, so set equality holds and
FR-03.6's criterion — *lit no redder than under `-DNDEBUG`* — is satisfied in its strongest form.

This is the FR-07.9 control run the seed corpus needs: a seed that trips an assertion on this image
trips it because of what the seed does, not because the image's own test suite is already red.

---

## 4. Per-probe cost — the first image-level delta this design has

The probe is **M2's**, `raw/bench-big.mlir`: one `hw.module`, 4,000 `comb` operations cycling
add/mul/and/or/xor, 4,003 lines. No generator script was stored with M2, so `w04b_gen_probe.py`
reconstructs it and is verified byte-identical —
`sha256 ed5ead0c3d0ded1e9bf8bbc80522076f12c12bda4f696dfb7c93273148d3cfb1` for both the stored
artefact and the regenerated one. It is bind-mounted read-only into each container, so both images
see the same bytes. 20 repetitions each, **median**, `circt-opt --canonicalize --cse`:

| | `-UNDEBUG` | `-DNDEBUG` | **ratio** |
|---|---|---|---|
| **median of 20** | **29.375 ms** | **28.020 ms** | **1.048 (+4.84%)** |
| min of 20 | 26.590 ms | 25.571 ms | 1.040 (+3.98%) |
| max of 20 | 40.137 ms | 34.435 ms | |
| `circt-opt --version`, median of 20 | 17.968 ms | 18.491 ms | **0.972** |

**About 4%, and the caveat is stated rather than buried.** The two distributions overlap heavily —
the assertions-on minimum (26.59 ms) is below the assertions-off median (28.02 ms) — so 4.8% is a
median difference across 20 noisy in-container samples, not a tight bound. The min-of-20 statistic
M2 used gives 4.0% on the same data. Both land in the same place: **the assertions cost single-digit
percent per probe, and the answer at image level agrees with M2's host-level bound of at most about
4%.** The `--version` row is the control and behaves like one: the ratio is *below* 1, which is only
possible if start-up is dominated by process creation and dynamic linking rather than by anything
the flag changes.

---

## 5. What FR-03.6, A-03 and A-20 now say

- **FR-03.6 — PASS.** Two images differing only in `-UNDEBUG` / `-DNDEBUG` produce the same lit
  result over CHIA's gate scope at `eade0de6` — 1119 passed, 7 XFAIL, 1 unsupported, **0 failures
  in both** — so the assertions-on image is not one test redder than the assertions-off one.
- **A-03 — closed at image level.** The flag string costs **+24.5% of binary bytes (+138 MB over
  six targets), +24.7% of build tree (+355 MB), +0.48 GB of unpacked image, +179 s of build wall
  (+22.6%), and ~4% per probe.** The cost is disk and build time; the per-probe cost is small enough
  that the loop's throughput is not set by it.
- **A-20 — closed.** The assertion false-positive set over CHIA's gate scope is **empty**. No test
  needs excluding from the gate, no allow-list is required, and FR-07.9's control run is a
  single `comm` that produces nothing.

---

## 6. One correction to §7 above, and what is still open

§7 said the `-gline-tables-only` size and time delta "falls out of that same second build for
free." **It does not.** The twin's flag string is `-O3 -DNDEBUG -gline-tables-only`: it differs
from the assertions-on image in `NDEBUG` alone, which is what FR-03.6 requires and is why the
debug sections are identical in both. What this build measures is the **assertions** delta at image
level. A `-gline-tables-only` delta at image level would need a *third* image at
`-O3 -UNDEBUG`, and nothing in F-03 needs one — M2's host measurement of that delta stands and is
not contradicted by anything here.

Still open, unchanged by W-04b: FR-03.9's `chia up` half (W-08/W-16), FR-03.10's `ImageSpec`
object (W-16), and publication — neither image has been pushed, so both `.RepoDigests` are empty.
