# Repair build diagnosis, 2026-09-15: the build tree is root's, the worker is not

`2026-09-15-repair-smoke.md` §2 left the repair chain's build failing and the cause open. It is ONE cause, neither CMake
nor slang: the image bakes `/workspace/circt` as **uid 0**, every worker runs `--user $(id -u):$(id -g)` = 1000:1000, and
the closing chmod of the first `configure_file` of a re-configure is EPERM. NOTHING WAS BUILT, no live container touched.

## 1. The error

```
$ cmake -S /workspace/circt -B /workspace/circt/build   # cache present, --user 1000:1000; Call Stack headers elided
CMake Error at /usr/share/cmake-3.28/Modules/FetchContent.cmake:1653 (configure_file):
  Operation not permitted
  CMakeLists.txt:588 (FetchContent_MakeAvailable)
CMake Error at build/_deps/slang-src/cmake/gitversion.cmake:115 (configure_file):
  Operation not permitted
  build/_deps/slang-src/cmake/gitversion.cmake:133 (get_git_head_revision)
  build/_deps/slang-src/CMakeLists.txt:29 (get_git_version)
-- slang version: 11.0.+
CMake Error at build/_deps/slang-src/CMakeLists.txt:61 (project):
  VERSION "11.0." format invalid.
```

## 2. Root cause

The same command in the same image **as root**: `11.0.385+44dc55f99`, `Configuring done (1.8s)`, rc=0 — a permission cause.

**(a) `Operation not permitted` is a chmod, not a write.** `/workspace/circt` is `root:root` throughout at `0777`/`0666` —
the Dockerfile's `RUN ninja -C build … && chmod -R a+rwX /workspace/circt` — and 7820 of its files are root's. As uid 1000
on one (`_deps/slang-build/CMakeFiles/git-data/HEAD`, `-rw-rw-rw- root root`): `open(f,"a")` OK, `utime(f,None)` OK,
**`chmod(f,0o666)` EPERM**, **`utime(f,(1,1))` EPERM**. `cmMakefile::ConfigureFile` closes every `configure_file` with a
`SetPermissions` copied from the input, and chmod needs OWNERSHIP, not write permission — so the smoke's "`_deps` is
world-writable, so this is no permission bit" reads the bit right and concludes wrong. Control: `configure_file(<slang-src>/
.git/HEAD <dest> COPYONLY)` is EPERM for a root-owned 0666 `<dest>` and fine for a `<dest>` the caller owns.

**(b) `slang version: 11.0.+` is a consequence of (a).** `slang-src/CMakeLists.txt:29` → `get_git_version` →
`get_git_head_revision`, dead at gitversion.cmake:115 on `configure_file("${HEAD_SOURCE_FILE}" "${HEAD_FILE}" COPYONLY)`
onto the root-owned `git-data/HEAD`. The aborted function never reaches its `set(… PARENT_SCOPE)` lines, so
`SLANG_VERSION_PATCH`/`_HASH` stay undefined and `"${MAJOR}.${MINOR}.${PATCH}"` renders `11.0.` with `+` appended. Expected,
measured as root: patch `385`, hash `44dc55f99` → `11.0.385+44dc55f99`, exactly `raw/image-manifest.json`'s `slang_version`;
nothing is unpinned, no `SLANG_VERSION` cache variable missing. Second, independent face of the same mismatch: as uid 1000,
`git -C …/_deps/slang-src describe --tags --dirty` is `fatal: detected dubious ownership`, rc=128 —
`circt_util.circt_trust_source` names this defect in its own docstring but covers `/workspace/circt` only, `_deps/slang-src`
being a separate repository. INFERENCE, untested: fixing (a) alone leaves `_version_string` empty at gitversion.cmake:148.

**What armed the re-configure is NOT resolved.** In a pristine container the edge is clean — `build build.ninja:
RERUN_CMAKE` has 403 inputs, 0 missing and 0 newer than `build.ninja` — and `git reset --hard eade0de6` + `git clean -fd`
(what `_restore` runs first) leaves it 0 and 0, the tree being already clean at `candidate.run_commit` = the image HEAD.
But 234 of the 403 inputs sit in the tracked source tree, so any turn that edits a `CMakeLists.txt`/`*.cmake`
arms the edge, the reset rewriting it with a fresh mtime; which of the assess turn's 23 bash calls did that is unrecoverable
(the chain drops per-phase logs, smoke §3) and the fix does not depend on it. `issue_task.py:224`'s verify-step
`circt_ninja_build` is the same command, so a genuine fix touching a CMake input would be scored `repro_fixed = False`; and
`circt_warm_build`'s result is discarded at `issue_task.py:148`, so stage 7 has no signal when the warm build fails.

## 3. The fix

Ownership is the cause, so ownership is the fix. Verified: `chown -R 1000:1000 /workspace/circt` in a throwaway container is
**0.37 s** over 9702 entries / 1.8 GB, after which the same re-configure as uid 1000 succeeds (`11.0.385+44dc55f99`, rc=0)
and `git describe` works with NO `safe.directory` entry. All six tool binaries hash identically before and after and match
`raw/image-manifest.json` `tool_hashes`, so `restore_hashes_match` and the ImageSpec are unaffected. In
`upstream/dockerfiles/ChiaCirctAssertDockerfile`, for reproducibility — ALONE it means a 972 s rebuild
(`2026-09-14-image-build.md` §1), invalidating the `RUN ninja` layer:

```diff
 ARG BUILD_JOBS=8
+# The uid/gid the cluster runs every worker with. chmod is not enough: configure_file ends in SetPermissions.
+ARG RUNTIME_UID=1000
+ARG RUNTIME_GID=1000
@@ RUN ninja -C build -j ${BUILD_JOBS} ${TOOL_TARGETS} \
- && chmod -R a+rwX /workspace/circt
+ && chmod -R a+rwX /workspace/circt \
+ && chown -R ${RUNTIME_UID}:${RUNTIME_GID} /workspace/circt
```

To fix THE IMAGE THAT EXISTS with no ninja and no cmake, the same chown as one child layer, re-tagged in place (a single
`RUN` on an existing image cannot cache-miss into a source build):

```sh
docker build -t chia-circt-assert:eade0de61bc5 - <<'EOF'
FROM chia-circt-assert:eade0de61bc5
USER root
RUN chown -R 1000:1000 /workspace/circt
EOF
```

The chown is 0.37 s but the layer commit copies up ~1.8 GB, so the image goes from 8.44 GB to roughly 10.2 GB of disk and
`image_id`, `image_digest`, `image_size_bytes`, `layer_count` in `raw/image-manifest.json` must be re-derived. The TAG does
not change, so `cluster_single.yaml` and the `image_tag.endswith(…)` pre-flight are untouched. NOT while campaign 1 is up.

Zero-image fallback, rejected as primary: drop `- "--user $(id -u):$(id -g)"` from `bugloop_repair.run_options` in
`circt_bug_loop/cluster_single.yaml`. Verified to fix both symptoms (§1, as root), but every artefact the repair worker
writes into `${BUGLOOP_ARTEFACTS}` then lands root-owned on the host — the condition FR-17.9 and that file's own `--user`
comment exist to prevent. Nothing is proposed in `repair_adapter.py`: `_restore` already records `build_ok`, and the
unchecked warm build is CHIA's `issue_task.py:148`, not ours.

## 4. Not tested — every probe ran in a throwaway `docker run --rm --cpus 2 --memory 3g` off the image, and built nothing

* That `ninja -C build -j4 <targets>` SUCCEEDS after the chown. Only the configure step was reproduced; ninja was never
  invoked, not even `-n`, and the edge analysis above is mtime arithmetic, not a ninja run.
* The child-image `docker build`: wall time and image size are estimates from the 1.8 GB copy-up. And no repair chain, no
  `chia up`, no Ray job, no model call.
