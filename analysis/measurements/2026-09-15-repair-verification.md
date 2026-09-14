# Repair verification, 2026-09-15: the tree builds as uid 1000, and the node ran out of memory

ONE live run, cap USD 10.00, wall bound 2400 s, cluster `cluster_single.yaml` with `bugloop_repair` on the chowned image.
Pilot 8's candidate `c-p-4b1c72262db2` down `bug_loop._drive_repair` itself, dedup verdict forced `new`, store COPIED first.
**THE RE-CONFIGURE AND THE BUILD SUCCEEDED AS UID 1000** — `2026-09-15-repair-build-diagnosis.md` §3's fix holds. The
attempt still returned nothing: Ray killed the repair task inside `_restore`'s rebuild, the node being low on memory.

## 1. The image

| | parent | variant |
|---|---|---|
| tag | `chia-circt-assert:eade0de61bc5` | `chia-circt-assert:eade0de61bc5-u1000` |
| `image_id` | `sha256:8ac3cb311851…` | `sha256:538aba96cbe4…` |
| `image_size_bytes` | 1,912,742,097 | 2,400,008,980 |
| `layer_count` | 23 | 24 |

One child layer, `RUN chown -R 1000:1000 /workspace/circt`, built in **30.7 s**; both entries are in
`raw/image-manifest.json`, the variant under `variants`. `chia up` started `bugloop_repair` from the variant and both
`bugloop_circt` containers from the parent, which is the image every other artefact of this project records. In the LIVE
repair container as uid 1000, before a turn was paid for: `/workspace/circt` is `1000:1000`, **0** of its 9,702 entries
are owned by anyone else, and `git -C build/_deps/slang-src describe --tags` answers `v10.0-385-g44dc55f99` with no
`safe.directory` entry — §2(b)'s second symptom. Both of the old symptoms are gone.

## 2. The run

| UTC | |
|---|---|
| 23:02:35 | driver starts; local id 900000004; `repro.sh` and `case.mlir` written |
| 23:02–23:2x | `circt_warm_build`, `circt_git_reset`, then CHIA's phase chain; 5 × 429, all waited out |
| 23:2x | chain returns; `bash_`/`build_`/`lit_900000004` shut down |
| 23:08 | `repro.sh` re-hashed: `065b7771…` before and after, UNCHANGED |
| 23:32:48–23:33:03 | `_restore`'s `ninja -j 4` COMPILES AND LINKS `circt-translate`, `circt-reduce`, `arcilator` |
| 23:33:12 | Ray: `Task was killed due to the node running low on memory` |
| 23:33:15 | driver returns; stage-7 call 1,833.75 s of its 2,400 |

## 3. The build, which is the thing this run existed to test

`_restore` ran `git reset --hard eade0de6`, `git clean -fd`, then `ninja -C build -j 4 <six targets>`. It **re-configured
and compiled**: `.ninja_log`'s last three edges are `bin/circt-reduce`, `arcilator.cpp.o`, `bin/arcilator`, and three
binaries carry link times of 23:32–23:33. The old failure was `configure_file … Operation not permitted` in **1.7 s**;
nothing past it could have compiled at all. All six targets still hash EXACTLY to `raw/image-manifest.json` after the
partial rebuild, so what ninja reproduced is the image's own build: `circt-opt dcb9599a…`, `firtool 9ca9b3ba…`,
`circt-translate f59b0f93…`, `arcilator 96a4144e…`, `circt-reduce 4c8d4479…`, `circt-verilog 53c3cbd5…`.

## 4. What was lost, and why

Ray's memory monitor killed the worker mid-`ninja`: a NODE-level kill, not the container's `--memory=4g` cgroup — the
host has 15 GiB and held five workers plus four concurrent LLVM link jobs. `_drive_repair` caught it and recorded
`stage_7 = refused:OutOfMemoryError`; `repair` is `None`, so `_as_repair_result` never ran and **the chain's status, its
diff, and the per-phase logs and assess `REASON:` this round added, all died with the worker**. No `fix.diff` was
written and the vertex backend writes no `issue_logs/`, so whether the chain produced a patch is UNRECOVERABLE. The
ledger row is all nulls for the same reason — `stage7_observed` is computed on the return path — and `metered = 0`, so
no figure here reaches a campaign cap.

## 5. The money

| | this run | the 2026-09-15 smoke |
|---|---|---|
| cap | 10.000000 | 10.000000 |
| ledger spend at the start | 1.206442 | 0 (unread) |
| ceiling, ONE phase | **1.758712** | 6.484763 |
| 5 × ceiling | **8.793560** | 32.423815 |

The clamp of step 7 binds: `min(6.484763, (10.000000 − 1.206442) / 5)`. Five phases now fit the cap that was registered
for them; the smoke authorised 3.2× its own cap. No `TurnBudgetExceeded`, no `MaxOutputTokensError`, 5 × HTTP 429 each
cleared on retry 1 of 6 after 16.3–21.7 s. **BILLING IS STILL UNOBSERVABLE FOR THIS STAGE**
(`token_capture = unavailable_remote_dispatch`): the architect must read Google's billing page for what this cost.

## 6. Not established

* Whether the chain would have said `fixed`, `attempted` or `unclear`, and whether it wrote a patch: killed before the
  result was mapped, and NO SECOND RUN was made, as instructed.
* `restore_ok` / `restore_hashes_match` for this attempt: `_restore` never returned. §3's hashes are this measurement's
  own `docker exec`, taken after the kill and before `chia down`.
* That 4 GiB and `-j 4` are right for `bugloop_repair`: the rebuild is the memory peak of the whole loop and it ran
  against a host also holding two `--memory=5g` probe containers and two LLM containers.

`chia down` ran; no container and no raylet is left, and the `/tmp/ray/ray_current_cluster` it leaves behind is what
`bug_loop.clear_stale_ray_cluster` removes at the next start (errata row 37). Ray interleaves worker stdout into the
driver's, so `repair_smoke.py`'s JSON is preceded by log lines and must be cut at its first `{` before it parses.
