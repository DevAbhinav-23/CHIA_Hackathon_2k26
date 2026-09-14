# Hostile code review: `circt_bug_loop/` before the first live model call

**Reviewer:** fresh-context adversary. **Date:** 2026-09-14.
**Tree reviewed:** `dcdc2af` (HEAD when this review started). `b0aab50` (W-19b:
`--generator recorded`, `BUILD_JOBS` 16 to 4) landed mid-review; every finding
below was re-verified against it and every line number cited is `b0aab50`'s.
`tests/test_system.py` and `tests/fixtures/system/` are the concurrent agent's
untracked work in progress and are out of scope.

**Normative:** `01-FRD.md` with §1.10, `03-LLD.md` §16.2, `04-Test-Plan.md`,
`design/reviews/implementation-errata-log.md`, the ADRs (D-03 superseding +
addendum). A row already in the errata log is not re-reported unless the code
contradicts its recorded resolution; where a finding restates a recorded open
item, it says so and is ranked by what it does to the campaign, not by novelty.

**Constraints honoured:** `BUGLOOP_ALLOW_LIVE_MODEL` was never set;
`~/.config/bugloop/gemini.env` was never read; no network call was made. Every
execution below is local, against
`~/.cache/chia-pin-smoke/bassert_g/bin/` with
`LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim`.

**Suite:** `~/.cache/chia-venv-py31019/bin/python -m pytest circt_bug_loop/tests
-q --strict-markers -W error -m "not t2 and not t3"` at `dcdc2af`, run twice:
`574 passed, 1 skipped, 9 deselected` in 83.88 s and 82.63 s. No flakiness. At
`b0aab50` the same command gives `1 failed, 573 passed`; the failure is
`test_T_U_layout_01_twenty_five`, whose only complaint is
`Extra items in the left set: 'test_system.py'`, i.e. the untracked file. **The
committed tree is green.**

---

## Counts

| Rank | Count |
|---|---|
| KILL | 11 |
| WOUND | 12 |
| NIT | 10 |

A green suite and eleven kills are not a contradiction: **no test in the tree
dispatches anything through Ray.** Every driver test builds
`bug_loop.Dispatch(remote=False)` (`tests/test_bug_loop.py:990`, `996`, `1077`),
the only tier-2 tests are nine docker/image tests, and there is no tier-3 test at
all. Seven of the eleven kills live exactly in the gap that leaves.

---

## KILL

### K1. `build_image` cannot succeed as the driver calls it, and it runs *before* `--dry-run` returns

Four independent failures on one call, `bug_loop.py:2918`:

```
    built = dispatch.call(build_image, pin["run_commit"], pin["pin_tag"],
                          IMAGE_TARGETS, IMAGE_FLAG_STRING,
                          str(_CHIA_ROOT / "dockerfiles" / "ChiaCirctAssertDockerfile"),
                          DEFAULT_REGISTRY, context=str(_CHIA_ROOT))
```

1. **No Docker on the worker.** `build_image` is
   `@ChiaFunction(resources={"circt": 1}, ...)` (`bug_loop.py:405`), so it runs
   *inside* a `chia-circt-assert` container. That container gets no docker
   socket and no docker binary: `cluster_single.yaml:139-163` mounts only
   `${BUGLOOP_ARTEFACTS}` and `$SSH_AUTH_SOCK`. Its first act is
   `_run(["docker", "image", "inspect", tag], ...)` (`bug_loop.py:443`), and
   `_run` (`bug_loop.py:388-396`) catches **only** `subprocess.TimeoutExpired`,
   so `FileNotFoundError` propagates out of the node.
2. **The reuse tag can never match the image that exists.** `image_tag`
   (`bug_loop.py:289-302`) returns
   `<registry>/chia-circt-assert:<sha256(manifest)[:12]>`. Measured:

   ```
   $ python -c '... b.image_tag(b.DEFAULT_REGISTRY, b.image_manifest(...))'
   ghcr.io/ucb-bar/chia-circt-assert:6e52a86987a7
   $ docker images --format '{{.Repository}}:{{.Tag}}' | grep circt
   chia-circt-assert:eade0de61bc5
   ghcr.io/ucb-bar/chia-circt:latest
   ```

   The Dockerfile's own header says the image is tagged
   `chia-circt-assert:<CIRCT_SHA[:12]>`; the code tags it by a manifest digest.
   Two naming schemes, and they cannot agree. Step 1 therefore always misses and
   a full rebuild is attempted, ending in `docker push` to ghcr, which W-19a
   already measured as `denied` (errata W-19a #1).
3. **The Dockerfile the driver names does not exist.** Measured:
   `/home/adi/.cache/chia-src/dockerfiles/ChiaCirctAssertDockerfile` -> `False`.
   `~/.cache/chia-src/dockerfiles/` holds CHIA's own ten and not this one;
   `upstream/sync-to-chia.sh` copies it into a *target* checkout and nothing
   runs it against `~/.cache/chia-src`.
4. **The `--image-tag` guard can never pass either.** `bug_loop.py:2923` asserts
   `image_spec.image_tag.endswith(args.image_tag)`; `${BUGLOOP_IMAGE_TAG}` is
   `eade0de61bc5` and the manifest tag ends `6e52a86987a7`.

`--dry-run` returns at `bug_loop.py:2974`, **after** all of this. So the one
command whose purpose is "confirm a cluster is ready to spend money without
spending any" (`main`'s own docstring) dies before it prints anything.

### K2. The seeded arm and stage 6 cannot reach the model: the `circt` containers carry neither the key nor the interlock

`build_llm` runs **on the calling node** (`llm.py:101-134`, "Worker: the
caller's"). Its two callers are `{"circt": 1}` nodes:

* `generate_task.py:596`, inside `generate_seeded` (`generate_task.py:643`);
* `triage_task.py:1438`, inside `_run_turn` for `triage_report`
  (`triage_task.py:1269`).

`cluster_single.yaml` passes `-e GEMINI_API_KEY` and
`-e BUGLOOP_ALLOW_LIVE_MODEL` to `bugloop_llm` (lines 101, 105) and
`bugloop_repair` (195, 196) and **not** to `bugloop_circt` (139-163). Errata
W-19a #5 measured the same thing from the other side: "measured in all three
keyed containers", which is two llm plus one repair.

So `require_live_model` (`llm.py:57-99`) raises `LiveModelRefused` on the circt
worker for **every** seeded generation and **every** triage report;
`generate_seeded`'s blanket `except Exception` (`generate_task.py:707`) turns it
into `failure="turn_failed:LiveModelRefused"` and returns zero specs, so
`drive_seed` ends the seed with `no_probe_written`. The seeded arm produces
nothing, for all 187 seeds.

Pre-flight does not catch it: `run_campaign` builds `model_resources` from
worker types carrying `llm` or `repair` only (`bug_loop.py:2937-2941`) and
`check_12_live_model` (`bug_loop.py:2943`) never asks a `circt` worker.

### K3. Stage 7 raises `KeyError: 'repair_backend'` on every candidate

`_drive_repair` hands `repair_adapt` the **generator's** cfg
(`bug_loop.py:2360-2362`). `generator_cfg` (`bug_loop.py:1905-1928`) emits
thirteen keys:

```
artefact_dir artefact_inline_cap_bytes artefact_root clone_path iteration
model_id mutator_set_sha per_seed_probe_cap price_usd_per_m_input_tokens
price_usd_per_m_output_tokens run_commit run_manifest_id timeout_seconds
```

`repair_adapt` reads `cfg["repair_backend"]` at `repair_adapter.py:406`, before
the interlock and before anything else it could survive. Verified by
construction: `"repair_backend" in generator_cfg(...)` is `False`.

`_drive_repair`'s `except Exception` (`bug_loop.py:2367`) swallows it and records
`out["verdicts"]["stage_7"] = "refused:KeyError"`. The `repair` row written at
`bug_loop.py:2349` stays at status `dispatched` for the life of the campaign, and
`reconcile` then reports it as a loop row with no CHIA counterpart. F-12 is dead
end to end and the failure is invisible in every artefact except a verdict string.

The same cfg is missing `repair_enabled`, `build_jobs`, `repro_dir`,
`repro_path`, `mutator_set_path`, `head_options` and `here_options`.
`generator_cfg`'s own docstring says "the sixteen keys A3 and A4 read".

### K4. `cfg["head_options"]` is never supplied, and `_head_options()` is dead code

`_head_options` (`bug_loop.py:199`) is the only mechanism in the tree for the
head pinning §3.2 and §3.5 require. It has **zero call sites** (`grep -rn
_head_options circt_bug_loop/*.py` returns the definition only).

Consequences, both on the `{"circt": 1}` worker:

* `generate_task._resolve_sites` (`generate_task.py:622-625`):
  `options = cfg.get("head_options")` -> `None`, so
  `if ray.is_initialized() and options:` is false and it falls through to
  `corpus.resolve_sites._chia_original(cfg["clone_path"], ...)` **in the
  container**, against the head's blobless clone at `~/.cache/circt`, which is
  not bind-mounted. FR-04.1's sibling-site resolution fails after the seed-read
  turn has already been paid for.
* `SourceReadTool(..., task_options=cfg.get("head_options"))`
  (`generate_task.py:680`, `triage_task.py:1443`) is unpinned, so the MCP server
  that is documented as "pinned by `task_options` to the HEAD, which is where
  the clone is (K5)" (`generate_task.py:113`) is placed wherever the scheduler
  likes.

### K5. Head-only nodes carry no placement and are handed head-only paths

`run_campaign` builds `dispatch = Dispatch(remote=True)` with no options
(`bug_loop.py:2908`), and `Dispatch.call` (`bug_loop.py:245-258`) dispatches
`fn.chia_remote(...)` with no `scheduling_strategy` at all. Every node whose
docstring says "on the head" is declared `@ChiaFunction(max_retries=0)` with **no
resource**: `ledger.accrue`, `triage_task.issue_mirror_refresh`,
`triage_task.dedup_and_screen`, `gate.gate_decide`, `feedback.build_feedback`,
`corpus.build_corpus`, `pin_select.select_release_pinned_main`,
`results.render_results`, `store.artefact_write`, `budget.load_budget`. Ray will
place an unresourced task on any node with free CPU, and the worker containers
advertise CPU (errata W-19a #7: "Ray advertises 80 CPU").

What they are handed is the head's filesystem:

* `self.store.db_path` -> `ledger.accrue` (`bug_loop.py:2154`, `2655`),
  `dedup_and_screen` (`2272`), `gate_decide` (`2310`),
  `issue_mirror_refresh` (`_mirror`). `DB_PATH = FLOW_DIR/"loop.db"`
  (`bug_loop.py:107`) is under the repository, which is **not** bind-mounted
  anywhere; only `${BUGLOOP_ARTEFACTS}` is.
* `campaign.clone_path` -> `dedup_and_screen`'s two contamination git scans.
* `args.github_token_file` (`~/.config/circt_bug_loop/github_token`, 0600) ->
  `issue_mirror_refresh`, which does `Path(token_path).read_text()`
  (`triage_task.py:711`).

Measured:

```
>>> LoopStore("/nonexistent-container-home/Projects/.../loop.db")
sqlite3.OperationalError: unable to open database file
```

With `max_retries=0` there is no second attempt. The failure is
non-deterministic (it depends on where Ray happens to place the task), which is
the worst shape it could have: a campaign that works for an hour and then
silently loses a stage.

### K6. The repair worker cannot find CHIA's example directory or its prompts

`issue_solver_dir()` (`repair_adapter.py:110-131`) is
`Path(chia.__path__[0]).resolve().parent / "examples" / "circt_issue_solver"`.
On the head that resolves to `~/.cache/chia-src/examples/circt_issue_solver` and
works. On a worker it cannot:

* CHIA's wheel ships the package only. `~/.cache/chia-src/pyproject.toml:68-73`:
  `include = ["chia*"]`, with the comment "without it the wheel also ships
  top-level docs/, examples/ and test/ into the installing environment". So the
  container's pip-installed `chia` has no `examples/` sibling.
* The runtime-env copy has none either: `_PY_MODULES` (`bug_loop.py:77-95`)
  ships `str(_CHIA_PKG)` (the `chia` directory), plus `issue_task.py` and
  `circt_util.py` as **loose top-level modules**. Ray places each py_module in
  its own directory, so `<py_modules>/chia`'s parent holds no `examples/`.

`build_cfg` then does
`cfg.update({key: (prompts / name).read_text(...) for ...})`
(`repair_adapter.py:308-309`) over `PROMPT_FILES`' six files, and `prompts/` is
not in `_PY_MODULES` at all. Stage 7 cannot assemble its cfg on the worker even
after K3 is fixed.

### K7. The `vertex` branch is not in the `issue_task.py` the driver ships, and nothing checks at run time

```
$ git -C ~/.cache/chia-src rev-parse HEAD
16c35e92aaaf9511c6453bf94cd5cf589698f4e3
$ grep -c 'elif backend == "vertex":' ~/.cache/chia-src/examples/circt_issue_solver/issue_task.py
0
```

`_PY_MODULES` ships exactly that file (`bug_loop.py:93`). `check_issue_solver`
(`bug_loop.py:2810-2833`) checks only that `issue_task.py` **exists**;
`issue_solver_dir` (`repair_adapter.py:124`) does the same. The patch is applied
only by `upstream/sync-to-chia.sh` into a *target* checkout, which the driver
never runs. The two tests that mention the branch
(`tests/test_layout.py:690-705`, `tests/test_repair_adapter.py:436-466`) read the
patch text and a temporary copy, never the file that ships.

Handed `cfg["backend"] = "vertex"`, CHIA's unpatched `_turn` falls through to
`else: llm = ClaudeCodeLLM(...)`. So the campaign would run stage 7 on a
different backend from the one `RunManifest.model_ids["repair_adapt"]` records
(`vertex:gemini-3.8-flash`) with `stages_metered["stage_7"] = True`, which
`bug_loop.stages_metered` (`bug_loop.py:980-1000`) derives from
`--repair-backend` alone. That is a **false statement in the manifest**, and
`repair_adapter`'s own guard (`repair_adapter.py:413`) compares the manifest
against the flag, not against the file.

The repair image is `chia-circt-assert`, which ships no Claude CLI and no
`~/.claude` mount, so the turn also fails - but the recorded provenance is wrong
either way, which is the worse half.

### K8. The mutation arm cannot run: only the unfrozen development set exists

```
>>> mutators.SET_PATH.name
'set_dev.json'
>>> mutators.load_set(expected_sha=mutators.set_sha256())
MutatorSetError: .../mutators/set_dev.json declares itself not frozen and
cannot run a registered campaign: synthesise and freeze a set first (8.3, FR-05.2)
```

`generate_mutation` raises it and `drive_seed`'s
`except Exception` (`bug_loop.py:2476-2478`) records
`generator_failed:MutatorSetError` for every one of the 187 seeds.

This is **errata W-13 #7 / test-plan §16.8 item 8**, still open, and the
concurrent agent's own W-19b comment states it (`bug_loop.py:1660-1668`: "it
CANNOT run in a registered campaign at all"). It is listed here because at
campaign time it is a kill, not a note: with K2 killing the seeded arm and this
killing the mutation arm, a live run today produces zero probes on both arms.

### K9. Any stderr containing an allocation literal is classified `oom`, and the firing is thrown away

`circt_core._limit_hit` (`circt_core.py:322-333`) returns `"address_space"`
whenever any of `ALLOCATION_FAILURE_LITERALS` (`std::bad_alloc`,
`out of memory`, `LLVM ERROR: out of memory`) is a substring of stderr, with no
requirement that the process died. `classify_build` (`probe_task.py:198`) then
takes the `limit_hit == "address_space"` row **before** its own guarded row at
`probe_task.py:200` (`if signal is not None and allocation`), whose docstring is
explicit that the guard is the point:

> the `oom` row by evidence needs death by signal as well, because an ordinary
> diagnostic carrying the phrase "out of memory" is a rejected input and not an
> exhausted machine.

The guard is unreachable from `probe_execute`, which always fills `limit_hit`
from `_limit_hit`.

Three adversarial inputs, run through `circt_exec_probe` + `classify_build`:

```
--- A timeout (wall): hang.sh under wall_seconds=3
   exit=None signal='SIGKILL' limit_hit='wall' -> ('timeout', 'wall_limit')          CORRECT
--- B address-space exhaustion: real circt-opt under --as=64MiB
   exit=127 signal=None limit_hit=None
   stderr='circt-opt: error while loading shared libraries: libMLIRLinalgDialect.so:
           failed to map segment from shared object'
   -> ('parse_error', 'tool_rejected_input')                                          WRONG (NIT N9)
--- C 'out of memory' in a diagnostic, exit 1, no signal
   exit=1 signal=None limit_hit='address_space' -> ('oom', 'address_space_limit')     WRONG
--- C2 a REAL SIGABRT assertion whose expression text contains 'out of memory'
   exit=None signal='SIGABRT' limit_hit='address_space' -> ('oom','address_space_limit') WRONG
```

C is not synthetic. MLIR echoes the offending source line in every diagnostic,
and the probing input is written by the model. Measured with the real binary:

```
$ circt-opt t4.mlir
t4.mlir:2:17: error: use of value '%a' expects different type than prior uses: 'i9' vs 'i8'
  %x = comb.add %a, %a {tag = "out of memory"} : i9
                ^
$ ...classify_build -> ('oom', 'address_space_limit')
```

`oom` is not in `_FIRING_STATUSES` (`bug_loop.py:134`), so C2's genuine assertion
never reaches stage 4 and is recorded as an exhausted machine. Both directions
are wrong numbers in the results artefact's probe-outcome table.

### K10. A failed or retried turn loses its token counts and is then priced at zero

`VertexGeminiLLM.prompt` resets `self._last_metadata = {}` at the top of **each**
attempt (`chia:chia/models/vertex.py:288`) and `_run_generate` assigns the real
counts only at its very **end** (`vertex.py:579`,
`{k: v for k, v in meta.items() if v}`). Any exception raised inside the tool
loop - `ServerError`, `MaxOutputTokensError`, `ContentBlockedError`, a translated
`google-genai` error - leaves `_last_metadata` empty, and a retry that then
succeeds reports only the successful attempt's counts.

`llm_turn` reads it with a **zero default**:

```
circt_bug_loop/llm.py:171   meta = dict(getattr(llm, "_last_metadata", {}) or {})
circt_bug_loop/llm.py:175   "usage": {"tokens_in": meta.get("input_tokens", 0),
```

and `ledger.price` (`ledger.py:76-79`) returns `None` only when a count is
`None`; `0` and `0` price to `0.0`. So a turn that made up to
`max_tool_iterations = 100` `generate_content` calls (`vertex.py:249`, `464`) and
then raised is written to `ledger_entry` as `metered=1, tokens_in=0,
tokens_out=0, cost_usd=0.0`. The module docstring's own rule - "a null token
count yields a null cost rather than a zero: a zero is a measurement and a null
is an absence (FR-14.6)" - is defeated by the default in `llm.py:175`.

`conftest.fake_vertex` never raises from `generate_content`, so no test can see
this.

### K11. Thinking tokens are not counted, so every priced turn and the USD cap are understated

`vertex.py:481-482` accumulates:

```
meta["input_tokens"]  += getattr(usage, "prompt_token_count", 0) or 0
meta["output_tokens"] += getattr(usage, "candidates_token_count", 0) or 0
```

Verified against the installed SDK (`google-genai 2.8.0`),
`GenerateContentResponseUsageMetadata` carries these fields:

```
cache_tokens_details cached_content_token_count candidates_token_count
candidates_tokens_details prompt_token_count prompt_tokens_details
thoughts_token_count tool_use_prompt_token_count tool_use_prompt_tokens_details
total_token_count traffic_type
```

`thoughts_token_count` is a **separate** field from `candidates_token_count`, and
ADR-D-03's superseding section states "thinking tokens are billed as output".
`tool_use_prompt_token_count` is likewise separate from `prompt_token_count`.
The campaign backend is `gemini-3.8-flash`, and `budget.yaml` sets no
`thinking_budget`, so whatever the model thinks is billed and not counted.

Not verified: how many thinking tokens `gemini-3.8-flash` actually emits (that
needs a live call, which is forbidden here). What *is* verified is that the field
exists, is separate, and is summed nowhere in this tree or in CHIA. The
consequence is that `campaign_spend_cap_usd` binds late by an unknown factor and
that the results artefact's USD figure is low by the same factor.
`conftest.vertex_response` (`tests/conftest.py`) builds
`GenerateContentResponseUsageMetadata(prompt_token_count=..., candidates_token_count=...,
total_token_count=...)` and never sets `thoughts_token_count`, so the suite
cannot catch it.

---

## WOUND

### W1. The USD cap is post-hoc and is consulted only between seeds

`stop_reason` (`ledger.py:231`) tests `ledger.spend_usd >= budget.campaign_spend_cap_usd`
against spend **already recorded**; there is no pre-authorisation anywhere. That
is defensible. What is not is where it is asked: `_arm_stop`
(`bug_loop.py:2574-2581`) is called once per seed in `campaign_drive`
(`bug_loop.py:2555-2556`, `2563`), and inside `drive_seed` (`bug_loop.py:2442-2517`) the
only per-iteration check is `campaign.now() >= deadline` - the wall clock, never
the money. One seed between two cap checks is up to
`per_seed_iteration_cap` (3) generation calls of two turns each, plus up to
`per_seed_probe_cap` (5) probes per iteration each with a stage-6 turn and a
stage-7 chain. The overshoot is a seed's whole spend, and it is unbounded from
above because stage 7's spend is not observed at all (recorded residual,
ADR-D-03 addendum).

### W2. Pre-flight checks 7 and 8 are tautologies; no worker is ever asked

```
circt_bug_loop/bug_loop.py:2929
    check_07_tool_hashes(image_spec=image_spec,
                         observed={cluster["worker_type"]: image_spec.tool_hashes})
    check_08_verilator_version(
        image_spec=image_spec,
        observed={cluster["worker_type"]: image_spec.verilator_version})
```

`observed` is constructed **from `image_spec`**, so both checks compare a value
to itself and can never fail. The functions themselves (`bug_loop.py:744`, `767`)
are correct; the call sites make them dead. FR-06.1's "every tool binary's
SHA-256 on every worker matches" and FR-03.15's Verilator check therefore have no
pre-flight at all, and `PREFLIGHT_CHECKS` names them anyway. The machinery to do
it properly exists three functions away: `worker_probes` (`bug_loop.py:2833`)
dispatches one node per worker type and is used for check 5 only. Today the only
real hash check is `probe_execute`'s per-probe one, which turns a wrong image
into `BinaryMismatch` on every probe rather than one refusal at start-up.

### W3. `ProbeResult.stopping_reason` is never updated, so the seeded arm is fed a false reason

The driver assigns `result.stopping_stage` five times (`bug_loop.py:2251`,
`2263`, `2290`, `2320`, `2370`) and **never** `result.stopping_reason`. The real
reason lives in the local `out["stopping_reason"]` (`bug_loop.py:2214-2215`),
which is returned to `drive_seed` and thrown away. `_close_probe`
(`bug_loop.py:2196`) writes the untouched record.

Two consequences. The `probe_result.stopping_reason` column carries stage 3's
build classification (`assertion_fired`) for a candidate that reached the gate
and was refused as `not_minimal`. And `feedback._reason`
(`feedback.py:92-93`) renders `f"{result.build_status}:{result.stopping_reason}"`
into every `FeedbackEntry`, so the model driving the seeded arm's next iteration
is told the wrong thing about what happened to its last probe - which is exactly
the signal FR-16 exists to carry.

### W4. `--generator recorded` still demands the live-model interlock and the key

The mode W-19b added exists "so that the whole of `campaign_drive` ... can be
exercised ON THE CLUSTER with no model turn and no credential"
(`bug_loop.py:1650-1655`). But `model_resources` (`bug_loop.py:2937-2941`)
includes every worker type carrying `llm` regardless of `args.generator`, and
`check_12_live_model(head=interlock_probe(), ...)` (`bug_loop.py:2943`) refuses
the run unless the head **and** both llm workers have
`BUGLOOP_ALLOW_LIVE_MODEL == "1"` and a usable `GEMINI_API_KEY`. A
no-credential dispatch rehearsal cannot start without the credential and without
arming the interlock cluster-wide, which is the opposite of what the mode is for.

### W5. FR-13.15's after-parse conjunct silently passes when it cannot be decided

`_after_parse` (`gate.py:494-514`) returns `None` when there is no in-scope frame
with a line and no pass pipeline - which is the ordinary shape of a
`fatal_error` candidate whose `frames` are empty. `gate_decide` then only
downgrades on an explicit `False`:

```
circt_bug_loop/gate.py:441   if fields["q3_valid"] and fields["q3_after_parse"] is False:
```

`decide` (`gate.py:465-489`) reads only the four `qN_*` answers, so an
undecidable second conjunct is neither a refusal nor an `undecided` bucket: it
passes question 3. FR-13.10's rule is that an unanswered question refuses.

### W6. `runtime_env()` ships the test tree, the loop database, and a namespace package

`runtime_env` (`bug_loop.py:205-228`) uploads `str(FLOW_DIR)` with
`_RUNTIME_ENV_EXCLUDES = ["**/__pycache__", "**/*.pyc"]` (`bug_loop.py:94`).
`du -sh circt_bug_loop` is 5.4 MB of which `tests/` is 3.8 MB, and that includes
`tests/fixtures/repair/issues.db`, `tests/fixtures/secrets/known_values.txt` and
- because `DB_PATH = FLOW_DIR/"loop.db"` (`bug_loop.py:107`) - the whole loop
database including the mirrored issue corpus, copied into every worker
container. `sync-to-chia.sh` already excludes `loop.db*`; `runtime_env` does not.

Separately, `_PY_MODULES` ships `str(_CHIA_PKG)` and `chia` is an **implicit
namespace package**: `~/.cache/chia-src/chia/__init__.py` does not exist and
`chia.__spec__` shows a `_NamespaceLoader`. A namespace directory uploaded as a
py_module can merge with the container's pip-installed `chia` rather than
shadowing it, so which `chia/models/vertex.py` and which `chia/base/ChiaFunction.py`
actually execute on a worker is not determined by this repository. That is also
why `chia.__path__[0]` is unreliable on a worker, which is K6.

### W7. The API key is serialised into a Ray task argument on every turn

`dispatch_turn` (`llm.py:185-197`) sends the `VertexGeminiLLM` object itself
through `chia_remote`, and that object holds
`client_kwargs={"api_key": key, ...}` (`llm.py:118-131`). The key therefore
travels through Ray's object store to the llm worker and can spill to
`/tmp/ray/session_*/` on disk. NFR-06's rule as written concerns
`chia job submit` runtime-env metadata, and `bug_loop_submit.sh` honours it
scrupulously (three non-secret keys, lines 52-61) - but the task-argument path
is a second copy nobody wrote down. It is not a leak to a third party; it is an
unrecorded persistence surface, and the mitigation is cheap (build the LLM inside
`llm_turn` from the worker's own env instead of shipping it).

### W8. `budget.yaml` still calls its own registered prices `[UNVERIFIED]`

`budget.yaml:33-36`:

> AGGREGATOR-SOURCED 2026-09-14 and **[UNVERIFIED]** against Google's own pricing
> page, which ADR-D-03 requires to be re-read and these two figures rewritten
> BEFORE the commit that lands this file.

ADR-D-03's superseding section records them "verified 2026-09-15 on Google's own
pricing page", and the last commit before this review is
`ecf4497 bugloop: ADR-D-03: Flash pricing verified on Google's page`. The
registration artefact and the ADR disagree about the provenance of the two
numbers the whole money cap is computed from, and the file cannot be edited after
its registration commit without invalidating the campaign (FR-14.7). Decide which
is true before the commit that registers the campaign, not after.

### W9. Nothing in the suite exercises the remote dispatch path

Every `Campaign` in the tests is built with `bug_loop.Dispatch(remote=False)`
(`tests/test_bug_loop.py:990`, `996`, `1077`), which runs each node's
`_chia_original` in the pytest process, on the head's filesystem, with the head's
environment. That is precisely the configuration in which K2, K4, K5, K6 and K7
cannot appear. There is no tier-3 test at all and the nine tier-2 tests are
docker/image tests. `T-U-driver-30/-32/-33` prove the *sequencing* and the *write
order*, not the deployment. The suite's greenness carries no information about
whether a campaign can run.

### W10. The generator's `LedgerSnapshot` is computed once per seed and never refreshed

`drive_seed` builds `snapshot` before the iteration loop
(`bug_loop.py:2463-2466`) and passes the same object to every iteration's
generator (`2475`) and to `_next_feedback` (`2492`). A seed's third iteration
reads a `remaining` that predates its first two, so FR-16's "how much is left"
signal is stale by up to a whole seed's spend - the same window as W1.

### W11. Filing counts are not scoped to the run, so a used-up `loop.db` stops future campaigns instantly

`ledger.aggregate` (`ledger.py:196`) runs `SELECT approved_at_utc FROM filing`
with no `run_manifest_id` predicate, and `stop_reason` (`ledger.py:237-238`)
compares `filings_total` against `budget.filings_total` (10). `loop.db` persists
across runs (`--resume` depends on that). After ten lifetime approvals, every arm
of every subsequent run returns `filings_total` from its very first `_arm_stop`
and mines nothing. Whether the caps are per-campaign or lifetime is a real
question FR-13.8 does not settle; the code has chosen lifetime by omission.

### W12. `--repair-backend claude` remains reachable and silently unmeters stage 7

`REPAIR_BACKENDS` (`bug_loop.py:129`) offers all four, and
`stages_metered` (`bug_loop.py:980`) flips `stage_7` to false for any backend but
`vertex`. `repair_adapt` then calls `require_live_model(..., need_key=False)`
(`repair_adapter.py:404-406`), so a `claude`/`antigravity`/`opencode` run reaches
a live model with **no key check at all** and no spend recorded anywhere. That is
ADR-D-03's declared fallback, so it is not a defect - but it is one flag away
from a campaign whose money is entirely invisible, and nothing warns.

---

## NIT

| # | Finding |
|---|---|
| N1 | `_head_options` (`bug_loop.py:199`) and, through it, `_head_node_id` (`181`) are dead; they are the only pinning mechanism the design names. See K4/K5. |
| N2 | `PROBE_WALL_MARGIN_SECONDS` (`probe_task.py:43`) is defined and exported in `__all__` and used nowhere. |
| N3 | Duplicated helpers: `_sha256` in `probe_task.py:1908` and `repair_adapter.py:352`; `_canonical` in `probe_task.py:1872` and `mutator_synth.py:197`; `_utc` in `approve.py:77` and `bug_loop.py:1373`. |
| N4 | `write_interestingness` (`probe_task.py:1862-1866`) substitutes placeholders in dict order, so a substituted value containing a later `@NAME@` would be rewritten. Only `@TOP_FRAME@` is at risk and its inputs come from CIRCT, not the model. |
| N5 | `ProbeWriteTool.write_probe` (`generate_task.py:230-234`) catches only `OSError`; a filename containing a NUL raises `ValueError` out of the MCP handler. The traversal defence itself (`os.path.sep` reject plus `realpath` + `commonpath`) is sound, and `SourceReadTool._outside` (`generate_task.py:99-106`) plus `git show <rev>:<path>` is sound. |
| N6 | `write_artefact` (`store.py:1152-1154`) uses `os.path.normpath` and not `realpath`, so a symlink already inside an artefact directory is followed on write. |
| N7 | The contract's run-time version check has no teeth: both halves are one installed package, so `contract_version` is always `CONTRACT_VERSION` and `check_version` (`contract/schema.py:59`) only bites on `from_json` of a recorded fixture. That is honest for a one-repo build; it should not be described as a run-time seam guard. |
| N8 | `_STAGE_OF` (`bug_loop.py:136-141`) has no entry for `gate_rerun` or `gate_validate`, so the gate's own `{"circt": 1}` occupancy is folded into `gate_decide`'s wall clock rather than charged as its own ledger entry. |
| N9 | An exit-127 dynamic-loader failure classifies as `parse_error:tool_rejected_input` (measured, case B under K9). Under a tight enough `--as` the loader dies before the tool starts and the probe is recorded as a rejected input. |
| N10 | `corpus.py:62`'s greedy `circt-capi-.*` still puts a shell fragment in a reported count key. Already recorded as A-19 finding 6; still open. |

---

## The single question to answer before the first live call

**Is there a hard, project-level spend cap on the Google Cloud project behind
`~/.config/bugloop/gemini.env`, and what is its number?**

Everything else in this report is a crash, and a crash is recoverable. This is
the only failure that spends the user's USD 300 and cannot be undone, and four
independent facts say `campaign_spend_cap_usd` will not stop it:
stage 7's tokens are unobservable by design (ADR-D-03 addendum, a recorded
residual); a turn that fails after 100 tool iterations is priced at zero (K10);
thinking tokens are not counted at all (K11); and the cap is consulted only
between seeds (W1). The ADR names the mitigation - "the operator's project-level
budget alert bounds the rest" - and **nothing in the code, the cluster YAML, the
twelve pre-flight checks or the test plan verifies that it exists.** A budget
*alert* is also not a *cap*: Google's budget alerts notify and do not stop
billing. Establish the number, and prefer `--no-repair` for the pilot, which is
the one configuration whose reported spend is complete.

---

## The ten riskiest assumptions, with the cheapest check for each

| # | Assumption | Cheapest check |
|---|---|---|
| 1 | A project-level spend cap exists on the key's GCP project. | Open the billing console for that project; write the number into `budget.yaml`'s header before the registration commit. Nothing in this repo can check it. |
| 2 | The image the cluster runs is the image the manifest records (checks 7/8, W2). | `docker exec circt_bug_loop_circt_$USER sha256sum /workspace/circt/build/bin/circt-opt` and diff against `analysis/measurements/raw/image-manifest.json`. Then make the two call sites at `bug_loop.py:2929` take real `worker_probes`-style observations. |
| 3 | The head-only nodes run on the head (K5). | Run `--generator recorded` on the live cluster and grep the driver log for `OperationalError` / `FileNotFoundError`; or add `socket.gethostname()` to `accrue`'s return for one run. |
| 4 | The circt containers can reach Vertex (K2). | `docker exec circt_bug_loop_circt_$USER env \| grep -c GEMINI_API_KEY` - expect `0` today. |
| 5 | The `issue_task.py` that ships has the vertex branch (K7). | `grep -c 'elif backend == "vertex":' $(python -c 'import chia,os;print(os.path.dirname(chia.__path__[0]))')/examples/circt_issue_solver/issue_task.py` - `0` today. Then make it a pre-flight check, not a sync-script side effect. |
| 6 | The repair worker can read its six prompts (K6). | `docker exec circt_bug_loop_repair_$USER python -c "import chia,os;print(os.path.isdir(os.path.join(os.path.dirname(chia.__path__[0]),'examples/circt_issue_solver/prompts')))"`. |
| 7 | `usage_metadata` is the billed token count (K11). | On the very first pilot turn, log `resp.usage_metadata.total_token_count` beside `prompt+candidates` and compare; then compare the ledger's USD against the project's billing page after the pilot's first hour. |
| 8 | The USD cap actually stops a run (W1). | Copy `budget.yaml` to a scratch registration with `campaign_spend_cap_usd: 1.0`, run the pilot against it, and record how far past 1.0 the ledger got before `_arm_stop` fired. |
| 9 | No genuine firing is classified `oom` (K9). | `for f in tests/fixtures/crashes/*/: classify_build(rc, sig, stderr + "\nout of memory\n", limit_hit)` - expect the assertion and crash fixtures to flip to `oom`. Ten lines, no cluster. |
| 10 | Both arms can produce a probe at all (K2, K8). | `python -c "from circt_bug_loop import mutators; mutators.load_set(expected_sha=mutators.set_sha256())"` (raises today), and one `--generator model` seed against the live cluster with `--arm seeded` before any full run. |

---

## What is solid

Recorded so the ranking above is read as a ranking and not as a verdict on the
tree.

* **The interlock holds.** `build_llm` (`llm.py:101`) is the only place in the
  flow that names `VertexGeminiLLM`, and it calls `require_live_model` first;
  `repair_adapt` checks it again before invoking CHIA's chain
  (`repair_adapter.py:397`); `conftest.no_live_model` refuses to start a test
  session with the variable set and substitutes a synthetic key. Grepping every
  `genai` / `VertexGeminiLLM` reference in the tree turns up no second path. No
  path constructs a real Vertex client without `BUGLOOP_ALLOW_LIVE_MODEL=1` and a
  non-`${`-prefixed key.
* **No shell anywhere.** `circt_exec_probe` is `fork` + `setsid` + `execvp` under
  a `prlimit` prefix with no shell; every `subprocess` call in the tree takes an
  argument list; the interestingness script `shlex.quote`s `@TOOL@`, `@ARGS@`,
  `@COUNTER@` and all four grep operands and uses `grep -F` throughout
  (`probe_task.py:1844-1860`).
* **Path traversal is closed** on both tools (`_outside`, and `realpath` +
  `commonpath` on `write_probe`), and `git show <rev>:<path>` cannot escape a
  commit tree.
* **The GitHub client is GET-only** and logs the URL and status, never the
  `Authorization` header (`chia/github/github_client.py:130-160`); the token is
  read from a 0600 file on the head and never forwarded through
  `--runtime-env-json` (`bug_loop_submit.sh:8-13`).
* **The approval CLI enforces both filing caps before the human is shown
  anything** (`approve.py:139-190`), and `issue_number` validates on the accept
  side - scheme, exact host, path prefix and a digit tail (`approve.py:258-273`).
* **Dependencies are exactly CHIA plus the standard library**: an AST walk over
  every non-test module yields `chia`, `ray`, `yaml`, `circt_util`, `issue_task`
  and the package itself. FR-19.8 holds.
* **The contract is coherent**: `validate` checks the MAJOR version, every
  required field, every declared dict's key set and the per-class conditionals;
  `from_json` drops unknown keys deliberately and refuses missing declared ones.
  No producer in the tree emits a field the validator rejects, and no consumer
  reads an optional field without a default path.
* **`classify_build`'s ordering is otherwise right**: a wall or CPU kill outranks
  everything (FR-06.4), a killed probe carries a null signal
  (`probe_task.py:137`), and the timeout case is correct on a real run.
