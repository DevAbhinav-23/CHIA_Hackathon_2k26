# CIRCT LLVM pin-window analysis — empirical answer to the untested technical bet

**Date:** 2026-09-11. **Analyst:** research pass for the CHIA hackathon problem statement.
**Question being resolved:** the `chia-eval-report.md` §G.3 claim #10 — *"Whether a CIRCT release tarball's prebuilt LLVM ABI-matches an arbitrary historical parent commit"* — was flagged as **"STILL UNVERIFIED — highest technical risk in the proposal"**. This document replaces that guess with a measurement.

Everything below is computed from the real `llvm/circt` git history and the real release tarball. No estimates.

---

## 0. TL;DR

| Question | Measured answer |
|---|---|
| Does an *exact* prebuilt-LLVM SDK exist for a historical CIRCT bug-fix commit? | **Usually yes.** 171 / 187 (**91.4%**) of bug-fix-shaped commits over 24 months have a `firtool-*` release whose `llvm` submodule pin is byte-identical to the pin at the bug's parent commit. |
| How bad is the worst case? | **Never worse than one LLVM bump.** 16 / 187 (8.6%) are 1 bump away; **0 / 187 are >1 bump away.** |
| Why is coverage so high? | CIRCT ships releases **faster than it bumps LLVM**: median **7.0 days** between `firtool-*` tags vs median **10.4 days** between LLVM pin changes. |
| Does CIRCT actually build at a historical parent commit against a release SDK? | **Yes.** Configure 10 s, `ninja -j6 circt-opt` **1,027/1,027 in 939 s**, at a commit 18 commits / 11 days *past* the tag. The bug's test goes **red at the parent and green after the fix**, with a **13 s** incremental rebuild. |
| What happens one LLVM bump off? | **Hard failure at build target 2/1030.** One bump = 1,237 llvm-project commits; the SDK's `mlir-tblgen` rejects the source's `.td` files (`Variable not defined: 'SymbolName'`) across 10 dialects. cmake configure still passes, so the version check is not a safety net. |
| How many Docker images does a 171-task set need? | **38** (one per distinct pin window); median 3 tasks/image, max 27. |

The bet is **safe when the pin matches exactly, and fatal when it does not** — and
since no candidate is ever more than one bump away, exact pairing is both necessary
and (91.4% of the time) available. The measurement itself is a reportable result.

---

## 1. Method and exact commands

```bash
# 1. Blobless clone — full history, no blobs (74 MB, ~60 s)
git clone --filter=blob:none https://github.com/llvm/circt circt

# 2. Submodule path (confirms the LLVM pin lives at `llvm`)
cat circt/.gitmodules
# [submodule "llvm"]
#   path = llvm
#   url = https://github.com/llvm/llvm-project.git

# 3. Run the analysis (pure local git plumbing; no network)
python3 pin_window.py /abs/path/to/circt              # default --since 2024-09-11
python3 pin_window.py /abs/path/to/circt --since 2025-09-11   # 12-month variant
```

`pin_window.py` sits next to this file in the project. It performs exactly **three** git passes plus one
`ls-tree` per tag — no per-commit subprocess storm:

| Pass | Command | Purpose |
|---|---|---|
| tags | `git for-each-ref --format='%(refname:short)\t%(creatordate:unix)' --sort=creatordate 'refs/tags/firtool-*'` then `git ls-tree <tag> llvm` | release date + LLVM pin per release |
| pin walk | `git log --first-parent --raw --no-abbrev --format='COMMIT %H' HEAD -- llvm` | every gitlink change (`:160000 160000 <old> <new> M llvm`) → reconstructs the pin at *every* first-parent commit and at its parent |
| candidates | `git log --first-parent --name-status --format='COMMIT %H' HEAD` | one pass, parsed in Python, for the file-shape filter |

**Reproduction note:** quote the refspec. In `fish` (and `zsh`), `refs/tags/firtool-*`
is glob-expanded by the shell and `git for-each-ref` silently returns nothing.

Full stdout (including the complete 978-row exact-match table): `pin_window_results.txt`.
The script also writes a machine-readable `pin_window_raw.json` into its working directory.

**Repo state at time of analysis:** `llvm/circt` HEAD =
`d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2`, 2026-09-11T08:36:10Z.

---

## 2. Definitions

- **Pin window** — a maximal contiguous range of first-parent `main` commits that
  share one `llvm` submodule hash. Windows are numbered oldest→newest, so
  `|window_id difference|` is literally *"how many LLVM bumps apart"*.
- **Bug state** — the bug-fix commit's **first parent** (`C^1`). The SDK must match
  the pin *there*, not at `C`.
- **Exact match** — a `firtool-*` tag exists whose `llvm` pin equals the bug
  state's `llvm` pin. If so, that release's `circt-full-shared-linux-x64.tar.gz`
  ships an LLVM/MLIR built from precisely the LLVM revision the source tree expects.
- **Candidate (shape filter)** — a first-parent commit touching **1–2** files under
  `lib/` or `include/` **and** adding/modifying **≥1** file under `test/` or
  `integration_test/`.
- **Candidate (filtered)** — the above, plus the subject matching
  `fix|fixes|fixed|bug|crash|assert|assertion|segfault|regression|ice|infinite loop|null|uaf|use-after-free`
  (case-insensitive, word-boundary).

---

## 3. Results — window structure and cadence

Window: **2024-09-11 … 2026-09-11** (24 months).

| Quantity | Value |
|---|---|
| `firtool-*` tags, all time / in window | 164 / **90** |
| first-parent commits on `main` in window | **3,257** (sum of per-window `n` in `pin_window_raw.json`; an earlier line here read 3,251, corrected 2026-09-13) |
| distinct LLVM pin windows touching the window | **63** |
| window length, commits (p25 / median / p75 / max) | 18 / **37** / 81 / 174 |
| window length, days (p25 / median / p75 / max) | 3.93 / **9.77** / 16.38 / 38.68 |
| windows containing ≥1 firtool release with the same LLVM pin | **47 / 63 = 74.6%** |
| commits sitting inside such a window | **2,909 / 3,257 = 89.3%** |
| LLVM bump cadence (n=62 gaps) | median **10.38 d**, mean 11.81 d |
| firtool release cadence (n=89 gaps) | median **7.0 d**, mean 8.1 d |

**Why the coverage is high.** Releases are more frequent than LLVM bumps
(7.0 d vs 10.4 d median), so most pin windows contain at least one release. The
windows that *miss* a release are the short ones: tagged windows have a median of
47 commits / 12.7 days, untagged windows a median of **14 commits / 3.3 days**.
Multiple releases frequently share one LLVM pin — 22 tagged windows carry 1 tag,
11 carry 2, 8 carry 3, and the tail runs to 7 tags on a single pin.

---

## 4. Results — bug-fix candidates and SDK availability

| | **Unfiltered** (file shape only) | **Filtered** (shape + bug-ish subject) |
|---|---|---|
| candidates, 24 months | **1,103** | **187** |
| exact prebuilt-LLVM match at parent | 978 (**88.7%**) | 171 (**91.4%**) |
| ≤1 LLVM bump away | 125 (11.3%) | 16 (8.6%) |
| **>1 LLVM bump away** | **0 (0.0%)** | **0 (0.0%)** |
| candidates, last 12 months | 639 | 127 |
| … of which exact match | 557 (87.2%) | 116 (91.3%) |
| exact-match tasks with exactly **one** source file | — | **156** |
| distinct pin windows spanned by exact-match tasks | 45 (median 18 tasks/window, max 78) | **38** (median 3, max 27) |
| non-exact: nearest release by date | — | median **5.2 d**, max 11.7 d |

**Reading of the headline row:** a mined CIRCT repair task set of **~187 tasks**
(24 months, bug-ish subjects, ≤2 source files, ships a test) is **91.4% covered by
an exact prebuilt LLVM/MLIR**, and the residual 8.6% is *always* within a single
LLVM bump — no task in the corpus is stranded. A 24-month unfiltered corpus of
**1,103** tasks is 88.7% covered.

**Cost of the image family:** the 171 exact-match filtered tasks live in **38**
pin windows, so 38 base images (one prebuilt SDK each) cover the whole set; the
largest single window holds 27 tasks. For the unfiltered 978, 45 windows suffice
(max 78 tasks in one window).

### Sample of exact-match candidates (newest first)

| Date | Commit | firtool tag (exact LLVM) | Source file(s) | Test file(s) |
|---|---|---|---|---|
| 2026-09-01 | `f2b15a44ec70` | firtool-1.157.0 | `lib/Conversion/HWToLLVM/HWToLLVM.cpp` | `test/Conversion/HWToLLVM/convert_aggregates.mlir` |
| 2026-08-29 | `c69a15e18d55` | firtool-1.157.0 | `lib/Dialect/FIRRTL/Transforms/LowerXMR.cpp` | `test/Dialect/FIRRTL/lowerXMR.mlir` |
| 2026-08-17 | `cc71d34ab52f` | firtool-1.156.0 | `lib/Conversion/MooreToCore/MooreToCore.cpp` | `test/Conversion/MooreToCore/basic.mlir` |
| 2026-08-13 | `4ac632ae7dd8` | firtool-1.156.0 | `lib/Dialect/OM/Transforms/ElaborateObject.cpp` | `test/Dialect/OM/elaborate-object-errors-unevaluated.mlir` |
| 2026-07-22 | `42d11d06acf7` | firtool-1.154.0 | `lib/Dialect/FIRRTL/Transforms/InferDomains.cpp` | `test/Dialect/FIRRTL/infer-domains-check-errors.mlir` |

(Full table: `pin_window_results.txt`.)

### Caveats on the numbers

- The subject-keyword filter is a proxy for "this is a bug fix". `[MooreToCore]
  Lower moore.null …` matches on the word `null` without being a crash fix;
  conversely many real fixes have neutral subjects. Both the filtered (187) and
  unfiltered (1,103) counts are reported for that reason. **Neither number has been
  validated by reading the diffs** — that is the pilot's job.
- 2 of the 63 in-window pin windows share their LLVM hash with another window (a
  revert/re-pin). For those, "bumps apart" is measured against the *oldest* window
  carrying that pin, which can understate distance. It affects at most 2 windows
  and does not change the 0%-beyond-one-bump result for the candidate set.
- "Exact LLVM pin match" guarantees the **LLVM revision** is identical. It does
  **not** by itself guarantee the release was configured with the same cmake
  options as the source tree expects. §5 resolves that empirically.

---

## 5. Task C — build smoke test (does the SDK actually work at a historical commit?)

### 5.1 CHIA's own recipe (`dockerfiles/ChiaCirctBaseDockerfile`)

Source: <https://raw.githubusercontent.com/ucb-bar/chia/main/dockerfiles/ChiaCirctBaseDockerfile>

CHIA already does prebuilt-SDK CIRCT builds. Verbatim, the load-bearing parts:

```dockerfile
ARG CIRCT_VER=firtool-1.148.0
ARG CIRCT_PKG=circt-full-shared-linux-x64.tar.gz
RUN mkdir -p /opt/circt-sdk \
 && wget -qO- \
      "https://github.com/llvm/circt/releases/download/${CIRCT_VER}/${CIRCT_PKG}" \
        | tar -xz --strip-components=1 -C /opt/circt-sdk \
 && rm -rf /opt/circt-sdk/include/circt /opt/circt-sdk/lib/cmake/circt

# CIRCT source matching the SDK ABI (no submodules — we use installed MLIR)
RUN git clone --depth 1 --branch "${CIRCT_VER}" \
      https://github.com/llvm/circt.git circt

RUN cmake -B build -S . -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DLLVM_ENABLE_ASSERTIONS=ON \
      -DMLIR_DIR=/opt/circt-sdk/lib/cmake/mlir \
      -DLLVM_DIR=/opt/circt-sdk/lib/cmake/llvm \
      -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
      -DLLVM_USE_LINKER=lld -DLLVM_CCACHE_BUILD=ON

RUN ninja -C build circt-opt
```

Its own comments, verbatim and quotable:

> `# The CIRCT release tarball's prebuilt libLLVM*/libMLIR* require GLIBC 2.36/2.38`
> `# CIRCT source matching the SDK ABI (no submodules — we use installed MLIR)`
> `# Bake circt-opt (and its full dependency closure) into the image. This is the slow part of the build (~30 min single-core)`

**The gap this analysis closes.** CHIA clones `--branch "${CIRCT_VER}"` — i.e. the
source tree is pinned to *the release tag itself*. Nothing in CHIA moves the
source to an arbitrary historical commit. §5.3 is the first test of that.

### 5.2 What is actually inside `circt-full-shared-linux-x64.tar.gz` (firtool-1.157.0)

Downloaded 142,818,645 bytes; 8,330 entries; **704 MB** extracted; root dir
`firtool-1.157.0/`; top-level `bin/ include/ lib/ python_packages/ share/ src/`.

| Expected | Present? | Detail |
|---|---|---|
| `include/llvm/` | **yes** | 2,479 entries |
| `include/mlir/` | **yes** | 2,319 entries |
| `include/circt/` | **yes** | 999 entries (CHIA deletes this so the source tree wins) |
| `lib/cmake/llvm/` | **yes** | 45 entries incl. `LLVMConfig.cmake`, `AddLLVM.cmake` |
| `lib/cmake/mlir/` | **yes** | 8 entries: `MLIRConfig.cmake`, `MLIRConfigVersion.cmake`, `MLIRTargets.cmake`, `MLIRTargets-release.cmake`, `AddMLIR.cmake`, `AddMLIRPython.cmake`, `IRDLToCpp.cmake`, `MLIRDetectPythonEnv.cmake` |
| `lib/cmake/circt/` | **yes** | 5 entries (CHIA deletes this too) |
| `lib/libLLVM*.so` | **yes** | **112** shared objects |
| `lib/libMLIR*.so` | **yes** | **442** shared objects |
| `bin/FileCheck` | **yes** | also `bin/not`, `bin/count`, `bin/split-file` |
| `bin/llvm-lit` or `bin/lit` | **NO — absent** | no `llvm-lit`, no `lit.py`, no `lit` python package anywhere in the tarball |

SDK identity: `llvm-config --version` → **24.0.0git**;
`LLVMConfig.cmake` → `LLVM_ENABLE_ASSERTIONS OFF`, `LLVM_ENABLE_RTTI OFF`,
`LLVM_ENABLE_EH OFF`.

**Two operational findings the image family must handle:**

1. **`lit` is not shipped.** CMake emits, verbatim:
   > `LLVM_EXTERNAL_LIT set to /opt/circt-sdk/bin/llvm-lit, but the path does not exist.`

   Consequence: `ninja check-circt` cannot run out of the box. Fix is one line —
   `pip install lit` and pass `-DLLVM_EXTERNAL_LIT=$(command -v lit)`. `FileCheck`,
   `not`, `count`, `split-file` *are* shipped, so a single test can also be run
   directly from its `RUN:` line without `lit` at all.
2. **`libz3.so.4` is a runtime dependency of the SDK binaries.** CHIA's Dockerfile
   installs `libz3-4` for this. On a distro shipping a different soname
   (`libz3.so.4.16`), the SDK binaries fail with
   `error while loading shared libraries: libz3.so.4`. A symlink fixes it; the
   image family should pin the z3 package as CHIA does.

### 5.3 Build at an arbitrary historical parent commit

**Chosen pair** (newest exact-match pair from §4):

| | |
|---|---|
| Bug-fix commit | `f2b15a44ec70f99fbc2a36f0de1b99d6c0f48af3` — *"[HWToLLVM] Use correctly typed constant attributes (#11068)"*, 2026-08-31 |
| **Parent (the bug state)** | `5056ff04450bc9f27a9ff0460702aee1f1afdd3f`, 2026-08-31 |
| LLVM pin at parent | `6279700538792da0c5a08e17babfe9b6e824c69f` |
| LLVM pin at `firtool-1.157.0` | `6279700538792da0c5a08e17babfe9b6e824c69f` — **identical** |
| Diff | `lib/Conversion/HWToLLVM/HWToLLVM.cpp` (1 file, +3/−3) and `test/Conversion/HWToLLVM/convert_aggregates.mlir` (+2/−2) |
| Test command | `circt-opt %s --split-input-file --convert-hw-to-llvm=spill-arrays-early=false \| FileCheck %s` |

Note the parent commit is **18 commits and 11 days later** than the
`firtool-1.157.0` tag — this is genuinely *not* the tag CHIA clones.

Exact commands used:

```bash
W=/home/adi/.cache/chia-pin-smoke

# SDK
curl -sL -o circt-full-1.157.0.tar.gz \
  https://github.com/llvm/circt/releases/download/firtool-1.157.0/circt-full-shared-linux-x64.tar.gz
mkdir -p $W/circt-sdk && tar -xzf circt-full-1.157.0.tar.gz --strip-components=1 -C $W/circt-sdk
ln -sf /usr/lib/libz3.so.4.16 $W/shim/libz3.so.4          # distro soname shim
export LD_LIBRARY_PATH=$W/circt-sdk/lib:$W/shim

# Source at the BUG'S PARENT, fetched by SHA (GitHub allows want-by-sha)
mkdir -p $W/src && cd $W/src && git init -q .
git remote add origin https://github.com/llvm/circt
git fetch -q --depth 1 origin 5056ff04450bc9f27a9ff0460702aee1f1afdd3f
git checkout -q FETCH_HEAD

# Configure with CHIA's exact flags
cmake -B build -S . -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DLLVM_ENABLE_ASSERTIONS=ON \
  -DMLIR_DIR=$W/circt-sdk/lib/cmake/mlir \
  -DLLVM_DIR=$W/circt-sdk/lib/cmake/llvm \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
  -DLLVM_USE_LINKER=lld -DLLVM_CCACHE_BUILD=ON

/usr/bin/ninja -C build -j6 circt-opt
```

**Measured outcomes** (host: 20 cores, ~6 GB free RAM, `-j6`, clang 23.0.0git,
lld 23, glibc 2.44, cold ccache):

| Step | Result | Wall clock |
|---|---|---|
| Shallow fetch of the parent commit by SHA (51 MB) | **OK** | **6 s** |
| `cmake` configure against the prebuilt SDK | **OK, rc=0**, zero errors | **9–10 s** |
| `ninja -j6 circt-opt` (1,027 targets) | **OK** — see §5.4 | **939 s** |

The configure step is the one that would have exposed a version/ABI refusal
(`MLIRConfigVersion.cmake` does an exact-version check, and CIRCT's
`CMakeLists.txt` validates the MLIR install). It passed at a commit **18 commits
downstream of the tag**, with `LLVM_ENABLE_ASSERTIONS=ON` against an
assertions-OFF SDK — exactly the configuration CHIA ships.

### 5.4 Build and test-flip outcome — **SUCCESS**

**First attempt failed, and the failure is worth reporting**, because it isolates
which part of CHIA's recipe is load-bearing. I initially skipped this line:

```dockerfile
&& rm -rf /opt/circt-sdk/include/circt /opt/circt-sdk/lib/cmake/circt
```

The build then died at target **514/1027**:

```
FAILED: lib/Dialect/FIRRTL/.../FIRRTLTypes.cpp.o
FIRRTLTypes.cpp:156:13: error: use of undeclared identifier 'RegistryType'
FIRRTLTypes.cpp:544:14: error: use of undeclared identifier 'RegistryType'
```

Cause, confirmed directly: `RegistryType` is defined in the *source tree's*
`include/circt/Dialect/FIRRTL/FIRRTLTypes.td` but is **absent** from the SDK's
prebuilt `include/circt/Dialect/FIRRTL/FIRRTLTypes.h.inc` (grep count 0), and the
SDK's include directory precedes the source tree's on the compiler command line.
The SDK's own CIRCT headers — 11 days stale relative to the parent commit —
shadowed the source. **CHIA's strip step is not hygiene; it is the mechanism that
makes a historical checkout work against a release SDK.** With the strip applied,
the build completed.

**Final measured outcomes** (host: 20 cores, ~6 GB free RAM, `-j6`, clang 23.0.0git / lld, glibc 2.44, cold ccache, `LLVM_EXTERNAL_LIT=/usr/bin/lit`):

| Step | Result | Wall clock |
|---|---|---|
| Shallow fetch of parent commit by SHA (51 MB) | **OK** | **6 s** |
| `cmake` configure against prebuilt SDK | **OK, rc=0, 0 errors** | **10 s** |
| `ninja -j6 circt-opt` — **1,027 / 1,027 targets** | **OK, 0 failures** | **939 s (15 min 39 s)** |
| Resulting `build/bin/circt-opt` | 62,084,272 bytes | — |
| **Incremental rebuild after applying the 1-file source fix** | **OK** (3 targets) | **13 s** |

**fail→pass contract, executed end to end:**

```
[1] pass-to-pass : OLD test on BUGGY source ............... PASS
[2] fail-to-pass PRECONDITION : NEW test on BUGGY source .. FAIL   <-- red
    convert_aggregates.mlir:51:17: error: CHECK-NEXT: is not on the line after the previous match
     // CHECK-NEXT: %[[MAX1:.*]] = llvm.mlir.constant(1 : i2) : i2
[3] apply source fix; incremental rebuild ................. rc=0, 13 s
[4] fail-to-pass POSTCONDITION : NEW test on FIXED source . PASS   <-- green
```

Test executed directly from its `RUN:` line (no `lit` needed):
`circt-opt <test> --split-input-file --convert-hw-to-llvm=spill-arrays-early=false | FileCheck <test>`
using the SDK's `bin/FileCheck` and the freshly built `circt-opt`.

**Conclusion: the bet holds.** A stock `firtool-1.157.0` release tarball builds
CIRCT at a historical commit **18 commits and 11 days downstream of the tag**, and
reproduces that commit's bug as a red test that the real fix turns green. Nothing
in the loop ever compiles LLVM.

### 5.5 Task C.4 — the one-LLVM-bump-away (ABI/API mismatch) test: **FAILS, fast and loud**

Probe: current `main` HEAD `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` (pin window
274, `llvm` pin `e297b52ec9d8…`) built against the **same** `firtool-1.157.0` SDK
(`llvm` pin `6279700538792…`). That is exactly **one** LLVM bump.

Size of one bump, via the GitHub compare API on `llvm/llvm-project`:

```
6279700538792da0c5a08e17babfe9b6e824c69f ... e297b52ec9d8b5c38042e53ae5650922717970cd
status: ahead   ahead_by: 1237   total_commits: 1237
```

| Step | Result |
|---|---|
| `cmake` configure | **PASSES** — rc=0, 0 CMake errors. `MLIRConfigVersion.cmake` compares only the version *string* (`24.0.0git` both sides), so it cannot see a 1,237-commit gap. |
| `ninja -j6 -k 20 circt-opt` | **FAILS at target 2 / 1030**, before any C++ object is produced |

Every one of the 20 recorded failures is the same signature, from the SDK's
`mlir-tblgen` refusing the source tree's `.td` files:

```
circt/include/circt/Dialect/HW/HWStructure.td:37:7:
  error: Variable not defined: 'SymbolName'
```

It hits 10 dialects (`HW`, `FIRRTL`, `RTG`, `OM`, `Arc`, `ESI`, `LLHD`,
`Handshake`, `Verif`, `SystemC`). `SymbolName` is an MLIR TableGen definition
introduced in llvm-project between the two pins.

**Three consequences, all good for the design:**

1. **Pin discipline is binary, not best-effort.** One bump off does not degrade —
   it does not build at all. There is no "mostly works" zone to reason about.
2. **The failure is cheap and unambiguous.** It surfaces in seconds during
   TableGen generation, not as a silent miscompile or a runtime ABI crash. A
   harness can detect a mis-paired image before spending any agent tokens; the
   check costs ~2 build steps.
3. **This is why §4's 0%-beyond-one-bump result matters.** Since no candidate is
   more than one bump from a release, and one bump is already fatal, the
   *only* viable construction is exact-pin pairing — and §4 shows exact pairing is
   available for 91.4% of filtered candidates. The remaining 8.6% must be dropped
   or built from source; they cannot be approximated.



---

## 6. What this means for the problem statement

1. **The pin-window bet is not a risk, it is a feature.** 91.4% exact coverage and
   a worst case of one LLVM bump means a mined CIRCT task set is buildable from
   stock release artifacts. No LLVM compile, ever.
2. **The image family is small.** 38 base images cover 171 tasks. Each is CHIA's
   `ChiaCirctBaseDockerfile` with `CIRCT_VER` re-parameterised and the
   `git clone --branch "${CIRCT_VER}"` line replaced by a fetch of the task's
   parent SHA. That is a ~3-line diff to an existing CHIA Dockerfile, which is the
   right way to describe it in front of its authors.
3. **Task supply is not the bottleneck.** 187 filtered / 1,103 unfiltered
   candidates over 24 months — an order of magnitude more than the "40–80" the
   earlier draft projected. The bottleneck is *validating* fail→pass, not *finding*
   candidates.
4. **Two concrete gaps to state honestly:** the SDK ships no `lit`, and it needs a
   `libz3.so.4`. Both are one-liners; naming them is cheap credibility.

---

## 7. Files

| File | What |
|---|---|
| `pin-window-analysis.md` | this document |
| `pin_window.py` | the analysis script (re-runnable, no network): `python3 pin_window.py /path/to/circt` |
| `pin_window_results.txt` | full stdout incl. the complete 978-row exact-match table |
| `pin_window_flip_smoketest.sh` | the fail→pass smoke test of §5.4, as run |
| `/home/adi/.cache/chia-pin-smoke/` | SDK, source worktree, build dir, logs (delete when done) |
