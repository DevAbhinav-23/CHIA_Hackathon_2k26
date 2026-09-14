# W-19b: the system tier on the single-machine cluster, with no model

**Run date** 2026-09-14 (IST), on `cachyos-x8664`. **Scope** `04-Test-Plan.md` §3's
tier-3 tests, as far as they go without a model call, against the real
`circt_bug_loop/cluster_single.yaml` cluster brought up by W-19a's procedure. The
driver IS in this run: `bug_loop.py` drives every stage of §3.2 through Ray onto
the five workers, with a new `--generator recorded` replacing the two
model-bearing nodes.

**No model call was made.** `BUGLOOP_ALLOW_LIVE_MODEL` was never set, in this
shell or in any container. `GEMINI_API_KEY` was exported as the literal string
`placeholder-not-a-key`; `~/.config/bugloop/gemini.env` was never read, and no
value of any credential appears in this file or in the raw logs.

## 0. Verdict

The cluster runs the loop. One full discovery iteration over eight seeds and both
arms dispatches sixteen probes onto the two `bugloop_circt` workers, executes the
image's own `circt-opt` against each, classifies every one, writes every row of
§6.4's tables it can reach, leaves no `PARTIAL` marker, meters both arm windows
and synthesises no counter block. `chia job submit` carries the driver and
`chia job logs` returns its output.

It did **not** do any of that as the code stood. **Four defects had to be fixed,
and three more were found and deliberately left**, and the first of the four
means the cluster had never run a single stage of this loop before today.

| | |
|---|---|
| `chia up -y` wall | **34 s** (W-19a: 36 s) |
| whole tier-3 module, 16 tests | **26 s** |
| one full iteration, 8 seeds x 2 arms = 16 probes | **7.4 s** |
| stage 3 on the cluster, per probe | **157 ms** (2.54 s over 16) |
| `chia down -y` wall | **178 s** (W-19a: 177 s) |
| Ray worker deaths, grpc port collisions | **0** (W-19a saw 2) |

## 1. The operator's shell

```
source ~/.cache/chia-venv-py31019/bin/activate      # 3.10.19, the images' python
source ~/.config/bugloop/cluster.env                # CHIA_HEAD, BUGLOOP_*, SSH_AUTH_SOCK
export GEMINI_API_KEY=placeholder-not-a-key
unset BUGLOOP_ALLOW_LIVE_MODEL
export BUGLOOP_CLUSTER=1                            # 04-Test-Plan.md §0.4's escape
cd ~/Projects/CHIA_Hackathon_2k26
```

`cluster.env` now supplies `BUGLOOP_HEAD_ENV=/home/adi/.cache/chia-venv-py31019/bin/activate`,
which is W-19a §7.1's owed decision made: the py31019 environment IS the head
environment, and it is the activate script and not the directory. The ssh-agent
W-19a started at `/run/user/1000/w19a-ssh-agent.sock` was still running and was
reused; it is still running now.

`chia up` needs **`-y`**: without it the CLI prompts `Proceed? [y/N]` and a
non-interactive caller gets `EOFError`. W-19a ran it interactively and so did not
meet this.

## 2. What `--generator recorded` is

A driver mode, `--generator {model,recorded}`, default `model`. `recorded`
replaces exactly three of `Stages`' ten callables and keeps the other seven:

| node | replaced by | why |
|---|---|---|
| A3 `generate_seeded` | `generate_recorded_seeded` | two model turns |
| B7 `triage_report` | `recorded_report` | one model turn |
| A4 `generate_mutation` | `generate_recorded_mutation` | **not** a model; see below |

It implies `--no-repair`, stage 7 being a model turn whatever the backend, and
`repair_enabled(args)` is the single place that condition is spelled.

The recorded generator reads two sources and never `llm.build_llm`: the seam's
own recorded `ProbeSpec`s where one names the seed, then the seed's own
`test_files` replayed unchanged. Every spec is built through
`generate_task._spec`, so the filename rule, the argv rule, `check_tool` and
`contract.validate` are the real ones and the apparatus cannot tell a recorded
spec from a generated one except by reading `expected_outcome`.

`recorded_report` renders 7.4.1's template from the record - every count, size,
time, hash, SHA and verdict still read off the record, which is FR-11.4 and needs
no agent - and writes a sentence saying no turn was made where the agent's three
prose fields would be. The classification is `untriaged`, FR-11.8's answer for a
turn that produced none, and the tool verdict still wins over it (FR-11.2).

**A4 is replaced although it reaches no model, and that is a finding.**
`mutators.load_set` refuses a set whose `frozen` field is false to any run naming
a digest (§8.1 rule 1); the committed set is `mutators/set_dev.json` with
`"frozen": false`; and every registered run names a digest, because
`build_manifest` stamps `mutator_set_sha=mutators.set_sha256()`. **The mutation
arm therefore cannot run at all until A7 synthesises and freezes `set_v1.json`**,
in any mode, with or without a model. Verified by reading the committed set.

## 3. The four defects that had to be fixed

### 3.1 `Dispatch` never dispatched: every stage ran on the head [FIXED]

`Dispatch.call`'s remote branch read `isinstance(fn, ChiaFunction)`. That is
**False for every node in the flow**. `ChiaFunction.__call__` returns a
`functools.wraps` closure carrying `_chia_original`, `_chia_options` and
`chia_remote` as attributes, merely `cast` to the `ChiaWrapped` protocol
(`chia:chia/base/ChiaFunction.py:108-129`), so `type(probe_execute)` is
`function`. Measured across seven nodes:

```
probe_execute              type=function   isinstance(ChiaFunction)=False has chia_remote=True
oracle_primary             type=function   isinstance(ChiaFunction)=False has chia_remote=True
dedup_and_screen           type=function   isinstance(ChiaFunction)=False has chia_remote=True
gate_decide                type=function   isinstance(ChiaFunction)=False has chia_remote=True
generate_mutation          type=function   isinstance(ChiaFunction)=False has chia_remote=True
ledger.accrue              type=function   isinstance(ChiaFunction)=False has chia_remote=True
generate_recorded_seeded   type=function   isinstance(ChiaFunction)=False has chia_remote=True
```

So at `remote=True` `Dispatch.call` fell through to
`getattr(fn, "_chia_original", fn)(*args, **kwargs)` and ran the node's body in
the driver process **on the head**, on a cluster whose five workers received
nothing. The fixed-size cluster, the `circt: 2` concurrency, the `llm: 1`-per-
container cap, `apparatus_concurrency` and the whole of FR-14.5's equal-wall-clock
argument were decorative.

It hid because **the head can run most nodes**: the clone, `loop.db` and the
artefact root are all on the head, and A4, A5, A6b, B6a, B6b, B9 and B11 need
nothing else. It surfaced only at the one node that needs the IMAGE:
`probe_execute` hashed `/workspace/circt/build/bin/circt-opt`, which does not
exist on the head, got `""` from `_sha256`'s `except OSError` and raised
`BinaryMismatch` for all sixteen probes - **the FR-06.1 check catching a defect
it was not written for**.

**Fix**: `hasattr(fn, "chia_remote")`, the duck test CHIA's own contract offers.
After it, the same sixteen probes land on the two `bugloop_circt` workers and
execute the image's own binary. Verified by dispatching a probe node that returns
`ray.get_runtime_context().get_node_id()` and its assigned resources: three
dispatches landed on two distinct circt node ids with
`{'CPU': 1.0, 'circt': 1.0}`.

### 3.2 `mutator_seed_int` overflows SQLite for half of A4's mutants [FOUND, NOT FIXED]

The first cluster run died with

```
ray::SQLiteNode.execute()
  OverflowError: Python int too large to convert to SQLite INTEGER
```

from `write_probe`, which is **outside** `drive_probe`'s `try`, so it propagates
out of `drive_seed` and `campaign_drive` and stops the whole campaign.

`mutators.mutant_seed_int` returns `int.from_bytes(digest[:8], "big")` - an
**unsigned** 64-bit integer. SQLite's `INTEGER` is **signed** 64-bit, so anything
above `2**63 - 1` raises. Measured:

| | |
|---|---|
| `mutant_seed_int` values over `2**63-1` | **9998 / 20000 = 50.0 %** |
| committed recorded mutation `ProbeSpec`s over it | **2 of 2** (`p-a23e35189e1c` 11630822309445067853, `p-d5e0050b5fee` 12839405957335514270) |
| plain `sqlite3` on the same value | `OverflowError` |

Expected time to failure in a pilot's mutation arm: **the second probe**.

**Not fixed here.** Masking the derivation changes every mutant the arm produces
and therefore the whole mutation baseline, so it must be decided before A7
freezes a set - which has not happened, so the timing is right. The recorded
generator masks its own seed to 63 bits (`bug_loop._seed_int`) so that this mode
does not reproduce the defect, and that is all.

### 3.3 The submitted job could not import its own package [FIXED]

`bug_loop_submit.sh` runs `python <flow dir>/bug_loop.py`, which puts the FLOW
directory on `sys.path` and not its parent. In a CHIA checkout the flow's modules
are loose files importing each other by bare name and that is enough; in the team
repository they are a **package** and every import in `bug_loop.py` is
`circt_bug_loop.<module>`. The real submitted job died with
`ModuleNotFoundError: No module named 'circt_bug_loop'` before its first line of
work.

**Fix**: `env PYTHONPATH=<flow dir's parent>` on the **entrypoint**, in the
wrapper. Not in `bug_loop.py`: FR-19.2 forbids a flow module to walk past its own
directory and `T-U-layout-09` enforces it by AST (the first attempt, two lines of
`sys.path` bootstrap at the top of `bug_loop.py`, failed that test - correctly).
Not in `--runtime-env-json` either: §11.2 fixes that key set at exactly three and
`T-S-submit-01` asserts its size. `T-U-submit-03`'s argv assertion moved by two
positions and was updated.

### 3.4 `ray.init(address="auto")` does not fail fast, so "skip cleanly" was unbounded [FIXED, in the test]

With no cluster up, `ray.init(address="auto")` reads
`/tmp/ray/ray_current_cluster` - which a `chia down` leaves behind - and retries
the GCS connection for minutes rather than raising. Measured: a stale file from
the W-19a run made a T3 collection hang past a two-minute timeout. §0.5's "skip
cleanly when `ray.init(address="auto")` fails" therefore needs a bounded check,
and `test_system._gcs_answers` resolves the address Ray's own way and probes it
with one TCP connect before `ray.init` is called at all.

Two smaller ones in the same fixture. Ray 2.54 raises **one `FutureWarning` of its
own** on every `ray.init` where `num_gpus` is unset, and `-W error` turns it into
the exception that "skips" the whole tier; it is suppressed at that one call and
nowhere wider, and Ray's alternative (`RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO=0`) was
deliberately not taken, since it opts the cluster into the future behaviour rather
than silencing the notice about it. And `conftest.no_local_ray` asserts no test
left a Ray running unless `BUGLOOP_CLUSTER` or `CHIA_LIVE_CLUSTER` is set, so the
tier-3 shell sets the first.

## 4. What the tier-3 tests could not reach, and why

§3's tests are written for `run_campaign`, whose twelve pre-flight checks stand
between argv and the first dispatch. **Four of them cannot pass on this host
today, and not one of the four is about the model.**

| check | why it cannot pass |
|---|---|
| 3, clone head | wants the clone at `budget.yaml`'s `corpus_head_sha` `d7e94049`; this host's blobless clone (`~/.cache/chia-pin-smoke/circt`) is at `b792c772`, and mining the six crash seeds' blobs is a network task |
| B1 `build_image` | **dispatched at `{"circt": 1}`, and no worker container has a Docker daemon.** `docker run --rm chia-circt-assert:eade0de61bc5 which docker` exits 1 and `/var/run/docker.sock` is not mounted by `cluster_single.yaml` on any type. The node's own docstring says "it needs a Docker daemon and the CIRCT worker type is the one that has one"; on this cluster the CIRCT worker type IS a container of the image it would build |
| 10, issue mirror | no mirror in any `loop.db` and no `~/.config/circt_bug_loop/github_token` to refresh one with |
| 11, forum post | FR-15.4's forum post has not been made |

So the tier-3 tests drive `campaign_drive` **directly**, with
`Dispatch(remote=True)` against `ray.init(address="auto")` and
`recorded_stages()`. That is the same dispatch path `run_campaign` takes after
its pre-flight - the same nodes at the same resources, the same store, the same
ledger, the same counters - with the pre-flight replaced by committed fixtures.
`T-S-submit-01` is the one test that runs the real `bug_loop.py` through the real
`chia job submit`, and it reaches exactly as far as pre-flight lets it.

`loop.db` lives **under the artefact root** in these tests and not at
`bug_loop.DB_PATH`. `ledger.accrue` and `dedup_and_screen` are
`@ChiaFunction(max_retries=0)` with **no resource**, so Ray may place either in a
worker container, where `bug_loop.FLOW_DIR` is the runtime env's own unpacked
directory (`/tmp/ray/session_*/runtime_resources/py_modules_files/_ray_pkg_*`) and
not the head's checkout. The artefact root is the one path bind-mounted
identically everywhere (FR-17.9). With 3.1 fixed this stops being theoretical.

## 5. The results

`pytest circt_bug_loop/tests/test_system.py -q --strict-markers -W error`, with
the cluster up: **15 passed, 1 xfailed, 26 s**. Ten of the fifteen are the
tier-0 tests of the mode; the six tier-3 rows are below.

| Test | Outcome | Evidence |
|---|---|---|
| `T-S-disc-01` (a) one discovery iteration | **pass** | 16 probes (8 seeds x 2 arms), 7.4 s; both arms' `arm_window` ledger entries present with stop reasons; 16 `probe` and 16 `probe_result` rows; **0 `PARTIAL` markers left**; `counters.json` carries a block per arm per stage and `violations == []`, so **no block was synthesised** - every node returned its own |
| `T-S-calib-01` (b) calibration mode | **xfail** | the manifest carries one `run_commit` per sampled seed with a non-null `seed_sha` (`1728445e7e57`, `5481d1901ca0`, `87f131c0af7f` - each seed's own parent); **all three builds executed at `eade0de61bc5`**, the run's image commit. FR-02.7 is unsatisfiable with a fixed image; see §6 |
| (c) the equal-window stop | **pass** | two 1.0 s windows: seeded **1.0317 s**, mutation **1.0103 s**, both `stop_reason="arm_window"`, both `metered`, 4 seeds and 4 probes each. The arms are sequential and the window is the binding stop rather than the seed set |
| `T-S-isolate-01` (d) precondition | **pass** | all six tool binaries on **both** `bugloop_circt` containers hash to `ImageSpec.tool_hashes` before the run and again after it. The repair attempt itself needs a model and is the pilot's |
| `T-S-regen-01` (e) regeneration + render | **pass (as a pin)** | the regeneration check ran and left no gap: 0 rows over 0 candidates, the zero being the answer and not a refusal. `render_results` **refuses with exactly one complaint**, FR-10.2's labelled duplicate-pair set; see §6 |
| `T-S-submit-01` (f) the wrapper | **pass** | `bug_loop_submit.sh --mode discovery --generator recorded --print-config` submits `raysubmit_*`, the job succeeds, `chia job logs <id>` returns the driver's own JSON, the driver resolved `artefact_root` and `image_tag` from the forwarded values, and none of `GEMINI_API_KEY`, `GITHUB_TOKEN` or `BUGLOOP_ALLOW_LIVE_MODEL` appears in `chia job status` or in the logs |

### 5.1 What the sixteen probes did

| outcome | n | reading |
|---|---|---|
| `parse_error`, `tool_rejected_input`, stops at stage 3 | 12 | W-09's six inputs each fired at **their own seed's parent commit**, and the image is at `eade0de61bc5`. Two of the six are a split PIECE of their test file and carry no RUN: line of their own. A rejection here is the expected answer, not a failure |
| `clean_exit` at stage 3, differential not applicable | 2 | FR-08.1's screen said no |
| `differential:harness_failure` at stage 4 | 2 | the differential oracle was reached, ran and **recorded its own failure** - `counters` show `stage_4 started=1 failed=1` per arm with no synthesised block, so this is a reported outcome and not a crash |

No probe fired the primary oracle, so the run produced **no candidate**, and
stages 5, 6 and the gate were never reached. That is the honest consequence of
running W-09's failures against an image at a different commit and is exactly
what `T-S-calib-01` xfails about.

### 5.2 `loop.db` after the five campaigns the module drives

| table | rows |
|---|---|
| `run` | 5 |
| `image` | 1 |
| `seed` | 29 |
| `probe` | 45 |
| `build_result` | 45 |
| `probe_result` | 45 |
| `feedback` | 45 |
| `differential_verdict` | 4 |
| `ledger_entry` | 112 |

Empty, all for the same reason - no probe fired the primary oracle:
`candidate`, `oracle_verdict`, `reduced_case`, `fingerprint`, `dedup_verdict`,
`report`, `gate_decision`, `repair`, `filing`. `issue_mirror` and
`issue_mirror_meta` are empty because these runs do not refresh a mirror;
`sdk_map` because the seeds come from a fixture and not from A1.

The ledger's 112 entries break down as 45 stage-2, 45 stage-3 and 4 stage-4 stage
occupancies, 8 `arm_window` entries (one per arm per campaign), and 10 `shared`
entries (the image and the synthesis occupancies, two per campaign).

### 5.3 Timings

| | |
|---|---|
| `chia up -y` | 34 s |
| whole `test_system.py` (16 tests, 5 campaigns, 45 probes, 1 job submission) | 26 s |
| one full iteration, 16 probes, both arms | 7.4 s |
| stage 2, per seed (recorded generator, on a circt worker) | 0.8 ms |
| **stage 3, per probe, on the cluster** | **157 ms** |
| stage 4 (differential oracle), per probe reached | 24 ms |
| `chia job submit` round trip, `--print-config` | ~6 s |
| `chia down -y` | 178 s |

Stage 3 to stage 6 is **not** measurable from this run beyond stage 4: no probe
reached stage 5 or 6. The 157 ms is a parse-error's wall, which is a floor and
not a representative probe.

### 5.4 Memory, against the new limits

`docker stats --no-stream` sampled every 10 s, 97 samples across the whole
session.

| container | limit | peak |
|---|---|---|
| `circt_bug_loop_circt_adi-0` | 5 g | **386 MiB** |
| `circt_bug_loop_circt_adi-1` | 5 g | **348 MiB** |
| `circt_bug_loop_repair_adi-0` | 4 g | **211 MiB** |
| `circt_bug_loop_llm_adi-0` | none | 95 MiB |
| `circt_bug_loop_llm_adi-1` | none | 98 MiB |
| host | 15,597 MiB | 11,909 MiB used, 13,266 MiB swap |

**These are not a workload's figures and must not be read as headroom.** Every
probe was a parse error that exited in milliseconds; nothing compiled, nothing
linked and nothing reduced. What they do show is that a worker's RESIDENT cost -
the raylet, the Python runtime and the runtime-env unpack - is about 350 MiB, so
the 5 g and 4 g limits leave roughly 4.6 g and 3.8 g for the actual work. The
host figures are dominated by processes that predate the cluster. Ray advertised
**76 CPU and 34.86 GiB** against a 20-core, 15.23 GiB machine, which is W-19a
§7.4's finding unchanged in kind and smaller in degree (it was 80 and 57.62 GiB
before the limits came down).

`repair_adapter.BUILD_JOBS` is **4**, down from 16, and `bugloop_repair`'s
`--cpus` is 4 to match. The bound that binds on a 15 GiB host is memory, not
cores: a `ninja -j16` link of the CIRCT targets peaks far past that container's
4 g, and an OOM-killed link fails the `fix` phase with a build error that is not
the agent's diff's fault - the one failure mode `FR-12.7`'s `failing_phase`
cannot tell apart from a real one. **Not measured**: no repair chain ran, because
a repair attempt is a model turn.

### 5.5 Ray health

Six active nodes throughout (head plus five workers), `Recent failures: (no
failures)`, all five containers `Up 14 minutes` with no restart, and **zero**
`Failed to start the grpc server ... Address already in use` lines in the
session's logs. W-19a saw two such collisions at a concurrency of one task per
type; this run drove 45 probes and saw none. That is **not** evidence the
`--net=host` port-range collision of W-19a §7.3 is gone - the loop's concurrency
here is at most 2 and the worker ports are prestarted - only that it did not
recur at this load.

Teardown is clean: 0 `circt_bug_loop*` containers, 0 Ray processes, 6379 and 8265
free, and the ssh-agent left running.

## 6. What this run found and did not fix

### 6.1 FR-02.7's calibration mode cannot be satisfied by a fixed image [owed]

The requirement wants each sampled seed probed at **its own parent commit**, and
the manifest duly carries one `run_commit` per sampled seed with a non-null
`seed_sha`. But a run has ONE image, built at ONE commit, and `probe_execute`
runs `/workspace/circt/build/bin/<tool>` from that image and hashes it against
`ImageSpec.tool_hashes`. Measured: three calibration seeds whose manifest names
`1728445e7e57`, `5481d1901ca0` and `87f131c0af7f` produced three `build_result`
rows all recording `run_commit = eade0de61bc5`. The driver does not lie - it
records the commit it ran - but the manifest and the build rows then disagree,
and FR-18.5's seeded-bug validation table would be a table of results taken at
the wrong commits.

Three ways out, and the choice is the architect's: build one image per calibration
seed (twenty images, ADR-D-13's cost times twenty); run calibration as a separate
campaign per seed; or amend FR-02.7 to say the calibration measures **detection at
the run's commit** of a bug whose fix is known, which is a weaker and still useful
claim. `T-S-calib-01` is xfailed until one is made.

### 6.2 `render_results` refuses at the end of every campaign [owed]

Thirteen of §14.4's fourteen refusals are satisfied by a real run's store. The
fourteenth is FR-10.2's collision and false-merge rates, measured over a
**hand-labelled** duplicate-pair set; `render_results` takes it as a parameter,
correctly, because the labels are a measurement of the project and not a row of
the campaign. **`run_campaign` calls the node with no such parameter and offers no
way to pass one** (`results_module.render_results(store, manifest)`), so
`_dedup_rates`'s `if not labelled_pairs` gap fires on every run.
`ResultsIncomplete` is a bare `Exception` and `main` catches only
`(ImageBuildError, BuildTimeout, OSError, ValueError)`, so a campaign runs both
four-hour arm windows to the end and then **dies with a traceback instead of
writing its results artefact**. The measured refusal, over a real run's store:

```
the results artefact refuses to render; missing: the collision and false-merge
rates are measured over the labelled duplicate-pair set of FR-10.2 and none was
supplied
```

There is a second half to it: a labelled set may only name candidates the store
has fingerprints for, so a run that confirms nothing cannot supply one either.
The driver needs a `--labelled-pairs <path>` and a decision about what the
artefact says when the set is empty.

### 6.3 B1 is placed where no Docker daemon is [owed]

§4 above. `build_image` is `@ChiaFunction(resources={"circt": 1})` and no worker
container on `cluster_single.yaml` has a daemon or a socket. Either the circt
type mounts `/var/run/docker.sock` - which gives every probe root on the host and
is a poor trade for a node that runs untrusted generated input - or B1 moves to
the head, which is where the daemon actually is and where `docker build`'s context
lives. The second is the smaller change and is what this run's own
`--generator recorded` path sidesteps by not dispatching B1 at all.

### 6.4 The store and the clone are head paths reached from anywhere [owed]

`ledger.accrue`, `dedup_and_screen` and `render_results` take `db_path` or
`clone_path` and are decorated `@ChiaFunction(max_retries=0)` with **no
resource**. Until §3.1 was fixed this never mattered, because nothing was
dispatched. Now it does: Ray places such a task on any node with a free CPU, and
`bug_loop.DB_PATH` is `FLOW_DIR / "loop.db"`, which inside a container is the
runtime env's unpacked package directory - a different file per worker, created
empty on first write. Either those nodes are pinned to the head (`_head_options()`
already exists for exactly this), or `DB_PATH` moves under the artefact root,
which is the one path FR-17.9 makes identical everywhere. The tier-3 tests take
the second route for their own store and assert nothing about the driver's.

### 6.5 Smaller observations

- **`chia up` needs `-y`** from any non-interactive caller; without it the CLI
  raises `EOFError` at its `Proceed? [y/N]` prompt.
- **The recorded report's `Assisted-by:` trailer names a model that did not run.**
  `triage_task.render_report` reads it off `manifest.model_ids['triage_report']`
  in three places rather than taking it as a parameter, so a report whose first
  line is `NO MODEL TURN WAS MADE` still ends `Assisted-by: vertex:gemini-3.8-flash`.
  The `Report` record was left agreeing with the artefact rather than introducing
  a second disagreement; the one-line fix belongs to `triage_task.py`.
- **`runtime_env()` ships the whole `circt_bug_loop` directory** (2.53 MiB as
  measured by Ray's own packaging line) with excludes `**/__pycache__` and
  `**/*.pyc` only. `loop.db` at `FLOW_DIR` would be shipped to every worker on
  every `ray.init` if it existed there; §6.4's move would fix that too.
- `ray status` still warns `Found multiple active Ray instances` and connects by
  IP, as W-19a recorded. Harmless; every dispatch landed.
- `chia down` (178 s) still takes five times `chia up` (34 s).

## 7. Raw logs

Under the run's scratch directory, not committed: `chia up` and `chia down`, the
per-test pytest logs, the `docker stats` sample log (97 samples), and the four
diagnostic scripts that located §3.1. The two commands worth repeating are the
`isinstance` probe in §3.1 and the overflow count in §3.2, both of which are
three lines and run at tier 0 with no cluster.
