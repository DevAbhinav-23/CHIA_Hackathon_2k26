# Hostile review of `02-HLD.md`

**Date:** 2026-09-13. **Target:** `design/02-HLD.md` at 849 lines, plus the 14 files under `design/ADR/`.
**Normative upstream:** `design/01-FRD.md`, `design/00-README.md`.
**Sources of fact:** CHIA at `~/.cache/chia-src`, commit `16c35e92aaaf9511c6453bf94cd5cf589698f4e3` (verified
by `git log -1`); the release SDK at `~/.cache/chia-pin-smoke/circt-sdk/`; the CIRCT clone at
`~/.cache/chia-pin-smoke/circt/`. Every `chia:` citation below was opened at the line given.

**Verdict in one line.** The document is unusually well sourced — 40-odd CHIA citations were checked
and all but two land on the lines claimed — and it satisfies seven of FRD §10.1's eight items *in
form*. It nonetheless cannot be implemented as written: the up-flowing schema is two incompatible
objects under one name, the artefact store has producers on workers and no transport to the head,
the repair stage silently poisons the binaries every later oracle verdict is taken against, and the
one required field on `LedgerEntry` has no admissible value for a third of its producers.

**Counts.** 7 KILL, 31 WOUND, 9 NIT. 47 findings.

**Out of scope by instruction.** The "Stream A (human team) / Stream B (architect's agents)" labels
are known to be withdrawn and are not reported. The seam is judged below purely as a test boundary.

---

## 1. KILL

An implementation faithful to the HLD would violate a named FR, or would fail.

### K1. `CandidateRecord` is two incompatible objects under one name, and F-16 collapses on the difference

**Where:** §2.4 (the schema), §5.2 (the object table), §6 (the A5 row).

§5.2 says `CandidateRecord` is persisted "one row per **candidate**". `G-23` and `ADR-D-06` define a
candidate as a probing input *for which an oracle fired*, and nothing else. FR-18.4's secondary
"candidates before dedup" and FR-18.6's "the taxonomy's counts sum to the candidate count" both rest
on that definition.

But §2.4's field list is a **per-probe** record: `oracle_fired: bool` (required), `build_status`
"one of FR-06.9's seven" (required, and four of those seven — `clean_exit`, `parse_error`,
`timeout`, `oom` — are by construction non-firing), `stopping_stage` and `stopping_reason`
(required). If the row is only cut for a firing, `oracle_fired` is a constant `true` and four of the
seven `build_status` values are unreachable. If the row is cut for every probe, "candidates before
dedup" equals "probes" and the headline's denominator is wrong.

The failure is not cosmetic, because `CandidateRecord` is the **only** object that crosses the seam
upward. FR-16.1 requires the `FeedbackBundle` to carry, *per probing input of the previous
iteration*, the stage it stopped at and the reason. §5.2 gives A5 exactly one input,
`CandidateRecord`. §2.8 makes this explicit: "Stream A replays Stream B's recorded `CandidateRecord`,
`LedgerEntry` and `RunManifest` ... **with no apparatus code present**." `BuildResult` — the object
that actually records a `parse_error` or a `timeout` — is apparatus-internal by §5.2 and FR-16.1
forbids the generator half importing it.

§6's A5 row then makes the normal case fatal:

> A5 | A previous-iteration probe has no record | set difference against the iteration's probes |
> the bundle fails to build and the seed's iterations end

Under the candidate reading, *most* probes have no record — a generated MLIR file that parses and
exits 0 is the expected outcome. So under the HLD as written, the first iteration containing one
non-firing probe ends that seed's loop. F-16 is the loop's closure and the thesis; it would never
run past iteration 1 for any seed. FR-16.3's three declared terminations (iteration cap, input cap,
budget) would never be the terminating condition for any seed.

**Also broken by the same gap:** `CandidateRecord` carries neither `seed_sha` nor `iteration`, both
of which `FeedbackBundle` requires (§2.5). A5 cannot populate its own required fields from its only
declared input.

### K2. B8 leaves the worker's CIRCT binaries carrying the attempted patch, and nothing restores them

**Where:** §3 (B8 row), §6 (B8 rows), §8.1.

§3's B8 row: "**Not idempotent.** It mutates the CIRCT tree. The adapter resets to the run's commit
before starting (FR-12.6) ... so a re-run is safe."

Resetting *before starting* protects B8 from a previous B8. Nothing protects B2, B3, B5 or B9 from
B8. Read CHIA's unmodified chain, which §8.1 pins byte-for-byte:

- `run_issue_remote`'s verify step calls `circt_util.circt_ninja_build(cfg["tool_targets"], ...)`
  **with the agent's diff applied** (`chia:examples/circt_issue_solver/issue_task.py:224`). After
  that line, `/workspace/circt/build/bin/{circt-opt,firtool,circt-translate,arcilator}` on that
  container are patched binaries.
- `run_issue_remote` returns without resetting or rebuilding
  (`chia:examples/circt_issue_solver/issue_task.py:274-286`).
- The next task's reset is `git reset --hard <ref>` then `git clean -fd`, "**NOT** ``-x``, so the
  gitignored ``build/`` tree — the warm incremental build — survives"
  (`chia:examples/circt_issue_solver/circt_util.py:58-59`).
- `circt_warm_build` returns early on its sentinel and rebuilds nothing
  (`chia:chia/chipyard/circt.py:677-678`).

So on a two-worker cluster, after the first repair attempt, half the apparatus runs probes against a
binary that is not the image's. Consequences, each a named FR:

- **NFR-02** ("Stages 3 and 4 ... shall be deterministic given the same inputs and the same image"):
  violated silently, because the image is unchanged and only the container's filesystem diverged.
- **FR-06.1**'s AC ("the recorded `--version` matches the `ImageSpec`'s CIRCT SHA"): still passes. A
  source edit without a reconfigure does not change the version string, so the check the FRD relies
  on cannot detect this.
- **FR-06.5** / `CandidateRecord.image_digest`: the digest becomes a false statement of where the
  result was produced.
- **FR-13.2** gate question 1, "does it reproduce at the run's commit": may be answered against a
  patched binary. This is the exact state the fresh process and fresh directory exist to exclude.

No component in §1 owns restoring the build, §3 assigns it to nobody, and §6 has no row for it.

### K3. The artefact tree lives on the head; its producers are workers; CHIA has no worker-to-head file transport

**Where:** §5 (the three stores), §5.2 (persistence column), §3 (B10 row).

§5 places the artefact tree at `artifacts/<run_manifest_id>/seed_<sha>/iter_<n>/` "in the shape CHIA
already uses (`chia:examples/circt_issue_solver/circt_issue_loop.py:120-160`)", and §3 puts
`artefact_write` on the **head**. §5.2 then assigns worker-produced files to that tree: probe
`input.<ext>`, "stdout and stderr as files under the probe directory", "the symbolised frames and the
reproducing command as files", "**both raw traces as files** under the probe directory",
`reduced.<ext>`, `report.md`.

The cited CHIA shape is not a transport. `_persist` writes on the head from a task's **return
value**; the only worker-produced files that reach it are inlined in that return value and capped at
256,000 bytes each (`chia:examples/circt_issue_solver/issue_task.py:264-272`, whose own comment says
"the container's FS is ephemeral"). CHIA has no node-to-head file API: `file_mounts` is a head→worker
rsync run by `chia up` before the container starts, and it lands on the **host**, not inside the
container (`chia:docs/user_guides/cluster_config_reference.rst:115-121`, `917-925`). `rsync` and
`openssh-client` are in the image for `chia up`'s transport, not for a task's.

So there is no stated mechanism by which a Verilator VCD trace or a multi-megabyte stderr produced on
`bugloop_circt` becomes a file under the head's artefact tree. FR-17.1's acceptance ("the directory
for one iteration contains the probe input, the argument vector, the build log, the oracle verdict,
the reduced case ...") and NFR-01's regeneration both depend on it. §5's closing rule —
"Anything larger than the artefact cap ... is written to disk and referenced by path" — names a disk
without naming a machine, and the two machines are not the same.

### K4. `LedgerEntry.arm` is required and has no admissible value for a third of its producers

**Where:** §2.6.

`arm: str, required`. §2.6's own text: "Produced by **every node in both streams**." The arm
vocabulary everywhere else in the package is `seeded | mutation` (`ProbeSpec.arm` §2.3,
`CandidateRecord.arm` §2.4).

These producers are not attributable to an arm:

| Producer | Why it has no arm |
|---|---|
| B1 `image_build` | one image per campaign, shared; §3 gives it 10800 s, the largest single charge in the run |
| B6 `issue_mirror_refresh` | "refreshed **once per run**" (§3, FR-10.9) |
| A1 `seed_corpus_build`, A2 `pinned_main_select` | one corpus and one pin per campaign |
| B10, B11, B12 | store, renderer, driver |

Three ways out, all defects: charge them to one arm (FR-14.5's equality is then false by
construction, and B1 alone can exceed a small per-arm allowance); split them 50/50 (an invented rule
in no FR); or add a third `arm` value (a change to a contract member, which by §2.1 is a MAJOR bump,
and the HLD declares the package at 1.0 with the vocabulary fixed). FR-14.4 ("the ledger shall accrue
spend per arm and per stage") and FR-14.5's equality check cannot be implemented from this schema.

### K5. B9's cross-worker re-run deadlocks the two-worker cluster

**Where:** §3, third note ("how B9 lands question 1 on a different worker"); §4.1.

The mechanism is `NodeAffinitySchedulingStrategy(node_id=<other>, soft=False)`. I verified the
premise: two `bugloop_circt` containers on one host **are** two Ray nodes — `chia up` suffixes the
container name per worker index (`chia:chia/cluster/node_setup.py:622`) and runs
`worker_start_ray_commands` (`ray start --address=...`) inside each
(`chia:examples/circt_issue_solver/cluster.yaml:94-96`;
`chia:chia/cluster/node_setup.py:544`). So the pin is expressible.

The deadlock is in the holding pattern. §3 puts `gate_decide` itself on `{"circt": 1}`, and §4.1
fixes `bugloop_circt` at 2 with `min_workers == max_workers`. A gate instance therefore holds one of
the two `circt` slots while dispatching a task that requires the *other* node's slot, with
`soft=False`, i.e. no fallback and no timeout. Two candidates gating concurrently — the expected
state at `apparatus_concurrency: 2` — hold one slot each and each wait on the other's. Neither can
progress. `max_retries=0` means Ray will not break it, and §3's own text rules out the only escape:
`chia_wait` "re-dispatches a task that never started" but classifies a task as stuck only when
`available[r] / cluster_total[r] >= min_free_fraction`, default 0.5
(`chia:chia/base/chia_wait.py:56-57`, `267-291`) — with both `circt` slots held, `available/total` is
0, so the deadlock is never even detected.

§6 has no row for it. FR-13.2 is unimplementable as designed on the Must configuration.

### K6. `oom` cannot be produced by the stated mechanism, and the failure mode is a false candidate

**Where:** §3 (B2 row), §6 (B2 OOM row), §9 (B2 row).

FR-06.2 requires "a **resident-memory** limit in bytes", applied to the child. §9's B2 row elects
"`prlimit` on the spawned child". On Linux, `RLIMIT_RSS` — the resident-set limit, and the one both
`prlimit --rss` and `resource.RLIMIT_RSS` set — has had no effect since kernel 2.4.30. It cannot kill
anything, so §6's "Probe exhausts memory | child rlimit, not the container's | `oom`" never fires.

The available substitute is `RLIMIT_AS` (address space), and it changes the observable behaviour in
the direction that costs the most. `RLIMIT_AS` does not kill; it makes `mmap`/`brk` fail, so a C++
compiler throws `std::bad_alloc`, which is uncaught, which calls `std::terminate`, which raises
**SIGABRT**. FR-07.2 classifies a firing with a signal and no assertion line and no `LLVM ERROR:`
line as **`crash`**. So under the HLD, a probe that merely exhausts memory becomes a `crash`
candidate, gets a frame-tuple fingerprint (FR-10.1), passes gate questions 1 and 3, and is presented
to a human as a CIRCT crash.

This falsifies FR-06.9's acceptance directly — "the batch of this feature's acceptance produces all
seven ... with **no misclassification**" — and it spends exactly the maintainer tolerance A-07
records as unknown. `CandidateRecord.limit_hit` exists (§2.4) but the HLD names no mechanism that can
populate it, because with `RLIMIT_AS` there is no kill signal to observe and no exit status that
distinguishes memory exhaustion from a real abort. Distinguishing them requires matching stderr
(`std::bad_alloc`, `Allocation failed`, `LLVM ERROR: out of memory`), which the HLD never specifies
and which collides with FR-07.2's `LLVM ERROR:` rule.

### K7. It is not one seam: two objects and one control edge cross it outside the contract package

**Where:** §2 opening; §5.2; §1.1 diagram.

`00-README.md` (as revised 2026-09-13) keeps the seam as a test boundary and names the two halves.
FRD §10.1 item 2 requires "**exactly one** seam ... the contract package of G-47 ... five members".
§2's first sentence repeats it: "holding exactly five schemas and no others".

Three things cross anyway.

1. **`SeedRecord`.** §5.2: produced by A1 (above), "Consumed by A3, A4, **B6 contamination**, B12"
   (both below). FR-15.1's screen needs the seed's commit date, which lives only on `SeedRecord`. Not
   a package member, so it is versionless and uncontracted.
2. **`BudgetFile`.** §5.2: consumed by "A6, **B12**". `00-README.md` places the budget ledger writer
   above the line; §1.3 places B12 below. FR-14.7's mid-campaign SHA check and FR-18.10's
   stop-both-arms rule both read it from below.
3. **A control edge.** §1.1's diagram draws `B12 --> A3` and `B12 --> A4`: the campaign driver, below
   the line, invokes the two generator nodes above it. Nothing in the five schemas describes that
   call's arguments, so the one interface the test boundary exists to freeze does not cover the
   dispatch that starts every iteration.

§2.8's join story fails on the same three. "The join is therefore a substitution, not an integration"
holds only if the five recorded schemas are the complete interface; they are not, so the half-level
fixture runs cannot exercise what actually crosses.

---

## 2. WOUND

Rework needed before the LLD. Ranked.

### Ordering, placement and scheduling

**W1. Do the two arms run concurrently or sequentially?** §1.3's B12 line says only "per-seed
iterations for both arms". Nothing in §3, §4 or §6 says whether both arms are in flight at once. The
answer determines whether G-48 is measurable at all. Concurrently on two `circt` slots, each arm gets
about one slot and each arm's wall-clock is measured under the other's interference, so the number
FR-14.5 equalises is contaminated by exactly the variable D-04 chose wall-clock to avoid.
Sequentially, the arms are clean but the campaign is twice as long against C-10. A third reading —
the ledger sums per-node wall time per arm — double-counts whenever two stages of one arm overlap.
`LedgerEntry.amount` (§2.6) is a per-entry float with no statement of what it measures. This is the
question the LLD cannot start without.

**W2. Every component has a timeout; nothing enforces one.** §3's Timeout column gives 14
`[DEFAULT]` values. `@ChiaFunction` accepts only "keyword arguments supported by
``ray.remote().options()``" (`chia:chia/base/ChiaFunction.py:97-106`), and Ray has no per-task
timeout. The two enforcement points CHIA actually uses are a `timeout_seconds` parameter inside the
node body (`chia:chia/chipyard/circt.py:617-620`) and `get(ref, timeout=...)`, which raises on the
caller but does not stop the worker. The HLD picks neither. §6 has **no failure row for a timeout**
on A1, A2, A3, A4, A5, A6, B1, B3, B4, B6-dedup, B7, B9, B10 or B11 — no detection, no recorded
status, no effect. FRD §10.1 items 3 and 6 are both only half met here.

**W3. `chia_wait` will not fire at the Must concurrency.** §3 and §6 rely on it for stalled
dispatches. Its stuck classifier requires `available[r]/total[r] >= min_free_fraction`, default 0.5
(`chia:chia/base/chia_wait.py:56-57`, `267-291`). With `circt` total 2, that needs a whole free slot.
At `apparatus_concurrency: 2` with both arms in flight, it is 0 almost always. The retry rail the HLD
declares is inert in the configuration the HLD specifies.

**W4. "Head" is not a placement.** §3 defines head as "a node or program with no resource tag,
running in the driver's own process on the head machine." Those are two different things and CHIA
says so: a `@ChiaFunction` called directly "just runs in the caller's own process and **isn't a
node**" (`chia:docs/concepts/overview.rst:36-37`), while one dispatched with `chia_remote` and no
resource tag is schedulable on any node with free CPU — including a `bugloop_circt` or `bugloop_llm`
container. A5, A6, B10's `artefact_write` and B11 are all labelled "node, head". Two implementations
diverge: one makes them plain function calls (and FR-19.1's "every added stage shall be a
`@ChiaFunction` node" is then arguable), the other dispatches them and they land on workers, where
B11 cannot read the head's artefact tree and A6's accruals perturb the wall-clock unit they are
measuring.

**W5. Container-level OOM has no path through the design.** §4.1 argues the two-level limit by
saying a container kill "removes the worker and CHIA re-queues the task onto another one
(`chia:docs/concepts/overview.rst:104-107`), which is a silent retry rather than an `oom` record".
Verified at those lines. But §3 sets B2 to `max_retries=0`, under which Ray does **not** re-queue —
the task fails with a worker-died error. So the hazard §4.1 describes does not exist as described,
and the hazard that does exist — a probe killing its worker and failing its task with no status —
appears nowhere in §6.

**W6. Nobody owns warming the build.** §4.1 says `bugloop_circt` "Owns a `/workspace/circt` checkout
at the run's commit **with a warm build**". §9's B1 row calls CHIA's six-target warm build "reuse".
No component in §1 or §3 calls `circt_warm_build`, and B1 builds an *image*, not a container's tree.
If the image bakes the full target set, `circt_warm_build` is dead weight; if not, some node must
call it and pay for it, and its cost lands on whichever arm charged the ledger at that moment.

### The contract

**W7. Ten untyped `dict`s carry the load-bearing fields.** §2.3–§2.7 declare `turn_cost`,
`differential`, `observed`, `dedup_evidence`, `gate_answers`, `image_spec`, `stages_metered`,
`model_ids`, `issue_mirror` and `differential_driver` as `dict` with no key list. These are not
peripheral: `gate_answers` is where FR-13.2's two worker identities and pids, FR-13.3's failing
reason, FR-13.15's `validity_basis` and exit status all have to live; `image_spec` is where FR-03.15's
Verilator version lives; `dedup_evidence` is FR-10.5's entire requirement. §2 states its own job as
"this section fixes the names, the types and what is required", and for a third of the payload it
fixes none of the three. Every one of these is a divergence point between two implementations and a
place FR-18.11's regeneration check cannot be written.

**W8. The compatibility rule has no enforcement point.** §2.1 states a MAJOR-equality rule and calls a
mismatch "a hard failure". §2.2 puts `CONTRACT_VERSION = "1.0"` in one module both halves import. With
one repository and one builder, `validate` compares a constant to itself; the rule can never fire in a
live run. The only place a stale version could appear is a committed fixture (§2.8), and §2.8 never
says fixtures are re-validated after a bump — it says the opposite, that "a fixture that does not
validate is a defect in the producer". So the seam's whole safety mechanism is unreachable.

**W9. Unbounded text inlined into contract objects contradicts FR-17.7 and §5's own rule.**
`ProbeSpec.input_text` (required), `CandidateRecord.reduced_text`, `FeedbackEntry.reduced_text` are
plain `str` with no cap. These objects are task return values and database rows. §5's own closing
sentence: "Anything larger than the artefact cap `[DEFAULT]` of FR-17.7 is written to disk and
referenced by path, **never inlined into a row or a task return value**
(`chia:chia/database/sqlite_node.py:35-38`)" — verified at those lines, which say "Store large
artifacts as files and put *paths* in the DB". The contract member and the persistence rule are in
direct conflict, and the contract is the one the code will follow.

**W10. `mutator_id` / `mutator_seed_int` are optional but "required in practice".** §2.3's prose:
"required in practice for `arm=mutation` and absent for `arm=seeded`". A validator cannot enforce "in
practice". FR-05.3's acceptance — "re-running a `ProbeSpec`'s mutator with its recorded seed integer
reproduces the input byte for byte" — is not checkable against a schema that permits their absence.
The same shape recurs on `turn_cost`, which is **required** on every `ProbeSpec` but has no defined
value for `arm=mutation`, where FR-05 forbids a model at run time; FR-05.4 requires both arms to pass
"through the same code path".

**W11. A `differential` `CandidateRecord` cannot be valid.** §2.4's note excuses `gate_decision` and
`taxonomy_bucket` for a differential candidate. It does not excuse `reducer`, `reduced`, `fixpoint`,
`budget_truncated`, `size_before_bytes`, `size_after_bytes`, `size_before_ops`, `size_after_ops`,
`dedup_basis`, `dedup_verdict`, `dedup_evidence` or `triage_class` — all required, and all produced
by stages FR-09.8, FR-10 and FR-13.14 forbid a differential candidate from entering. Either the
schema rejects every differential candidate or the LLD invents a dozen sentinels.

**W12. The manifest is missing fields named FRs require.**
- FR-14.5's acceptance: "the manifest names all **four** identifying fields" — unit, worker type,
  concurrency, cluster YAML SHA. §2.7 carries `worker_type`, `apparatus_concurrency`,
  `cluster_yaml_sha` and **not the unit**. `LedgerEntry.unit` is per entry, not the manifest.
- FR-18.8's confirmation **cut-off date**: nowhere in §2.7 or §1.3's B11.
- FR-03.5's 18-object assertion baseline, which §6's B1 row compares against: nowhere.
- FR-08.4's declared X-initialisation and reset **policy**: `ProbeSpec.differential` is said to carry
  stimulus, reset protocol and sampling point; the X policy is campaign-wide and appears in neither
  the manifest nor the `ImageSpec`.
- `mutator_set_sha` is marked **optional**; FR-05.2 requires it on every run and requires its commit
  to predate the pre-registration commit. The mutation arm is a Must (FR-18.1), so it is never
  legitimately null.

**W13. `FilingRecord` has no licence confirmation.** FR-20.5: "A patch offered with a report shall be
licensable under Apache-2.0 with LLVM exceptions. *AC:* the contributor confirms it **at approval
time**." §5.2's `FilingRecord` carries "the approver, the timestamp, the issue number and the URL".
ADR-D-12's list of what the CLI enforces before presenting omits it too. The FR has no home.

### Components that do not exist, and components that should not

**W14. The component count in §1's first sentence contradicts §1.2 and §1.3.** "Eighteen components.
Twelve are nodes ...; four are ChiaTools ...; two are head-side programs." Counting the tables: A6 is
two nodes, B6 is two nodes, B10 is two nodes, so Stream A has 7 nodes and Stream B has 13 — twenty.
Five ChiaTools are named (`SeedReadTool`, `ProbeWriteTool`, `ProbeRunTool`, `ReduceTool`,
`IssueMirrorTool`), not four. Eighteen is the count of *ids*, not of components, and the LLD will be
written from the tables.

**W15. The five ChiaTools get no row in §3.** FRD §10.1 item 3: "For **every component**: the worker
resource it needs, the image it runs on, its timeout, and its retry behaviour." §3's table has rows
only for nodes and the two head programs. A `ChiaTool` is a server placed by its own `task_options`
and can host its tools on a different worker than itself
(`chia:docs/concepts/overview.rst:42-50`), so its placement is a real decision, not an inherited one.
`AsyncJobTool._MAX_POLL_SECONDS = 120` and its "One job runs at a time per tool instance" rule
(`chia:chia/base/tools/AsyncJobTool.py:34-37`, `47`) are placement-visible constraints the HLD never
prices.

**W16. Three of the five ChiaTools have no agent that may call them.** A `ChiaTool` is, in the HLD's
own §0 vocabulary, "the agentic edges a model may call". The model stages are A3 (stages 1–2), B7
(triage) and B8 (repair). FR-04.4 forbids A3 any tool that computes a measured result and limits it
to read-only source access and a file write. FR-11.1/NFR-03 make B7 advisory and forbid it computing
numbers. B8 runs CHIA's unmodified chain with CHIA's own `BashTool`, `BuildTool` and `LitTool`. So
`ProbeRunTool`, `ReduceTool` and `IssueMirrorTool` have no legal caller. Each is a Ray actor plus a
uvicorn server for nothing. §1's claim that "no component is here that no functional requirement asks
for" is false for three of eighteen. FR-19.1's list of "the five long ones" is a *conditional* — if
such a tool is agent-facing, it must be an `AsyncJobTool` — and the HLD reads it as a mandate to
create them.

**W17. `SeedReadTool` duplicates `BashTool`, which §9 claims to reuse for the same job.** §1.2 gives
A3 both `SeedReadTool` and `ProbeWriteTool`; §9's A3 row lists "`BashTool` for read-only source
access" under **Reuses**. FR-04.4 asks for exactly two capabilities. One of the two is built twice.

**W18. The offline mutator synthesis is not a component.** `ADR-D-05` states it plainly: "the
mutation arm has two parts with different lifetimes: an offline synthesis step run once before the
campaign, and a run-time mutator runner". §1 has only A4, the runner. The synthesis has no id, no
worker, no timeout, no failure mode, and no place in §8.2's layout beyond `mutators/`, which is its
output. It also has a hard ordering constraint the HLD never draws: ADR-D-05 says "FR-10.9's issue
mirror is the synthesis input, so the mirror is built **before the pre-registration commit**", which
puts B6 — an apparatus component with a `circt` worker and a GitHub credential — on the critical path
*before* the budget file exists and therefore before FR-14.2 permits a run to start.

**W19. Two FRs have no owner.** FR-16.6 ("A seed whose every probing input failed at stage 3 for the
same reason in two consecutive iterations shall be abandoned, and the abandonment recorded") is
assigned to no component in §1, has no row in §6, and has no field in `FeedbackBundle` beyond the
free-text `terminating_condition`. FR-15.5 ("A candidate whose seed is one of the 16 non-exact seeds
shall still be screened, using the run's commit as the lower bound") appears nowhere in §1, §3, §5 or
§6.

**W20. B11 is under-specified against F-18.** §1.3 gives it "the results table, the failure taxonomy,
the divergences list and the mandatory disclosures". Missing: FR-18.5's **separate seeded-bug
validation table**; ADR-D-07's binding consequence that "the results renderer **refuses** a table that
does not name both qualifiers" (mode and seed set), which FR-18.2 makes a render failure; FR-15.2's
contamination column and the headline reported both with and without contaminated candidates;
ADR-D-10's lag disclosure beside the headline.

### CHIA fit

**W21. The GitHub mirror as designed will exhaust the rate limit, which zeroes the filing count.**
§1.3's B6 "Mirror CIRCT's open and closed issues once per run". The reusable API is
`GithubIssuesNode.recent(n, after, fetch_comments=True)`, whose default costs "one extra paginated
request **per issue that has comments**" (`chia:chia/github/github_issues_node.py:67-71`). CHIA's own
example therefore passes `fetch_comments=False` for its 2000-issue pool
(`chia:examples/circt_issue_solver/triage.py:61`; `chia:examples/circt_issue_solver/circt_issue_loop.py:50`,
whose comment sizes the open backlog at ~857). Open plus closed on `llvm/circt` is thousands. With
comments on, the mirror is thousands of extra GETs against a 5,000/hour authenticated budget. The
consequence is not a slow mirror: FR-10.7 turns a rate-limit error into `dedup_unavailable`, FR-13.5
fails gate question 4 for `dedup_unavailable`, and the campaign files nothing. The HLD never mentions
`fetch_comments`, and it needs to decide both ways at once — FR-10.3 screens "the candidate's
assertion text and its reduced case's distinctive tokens" against issues, and an assertion string is
as likely to sit in a comment as in a body.

**W22. FR-10.9's cap is in pages; the reusable API is in issues.** FR-10.9 and §6's B6 row count
pages. `GithubIssuesNode.recent` takes `n` issues; `_list` does its own paging internally
(`chia:chia/github/github_issues_node.py:139-175`) and `_paginate`
(`chia:chia/github/github_client.py:113-128`) is private and not what `_list` calls. An implementer
must either call a private method, convert pages to `n` by an unstated factor, or write a new pager.
Three outcomes, one requirement.

**W23. `GithubIssuesNode` is documented head-node-only; the HLD runs it on a `circt` worker.** §4.3
item 3: "B6's mirror and B9's reconciliation poll, **both of which run as nodes on
`bugloop_circt`**". The class docstring: "**Service-pattern node (head-node only, not a Ray task).**"
(`chia:chia/github/github_issues_node.py:31`). It will work — it is a plain `requests` client — but
the design choice is made against CHIA's stated intent without acknowledging it, and it is the choice
that forces the credential onto the worker in the first place (§4.3). Running both on the head, where
CHIA puts them and where B10 and B12 already are, would delete the bind-mount, the GCP `file_mounts`
question, and half of §4.3.

**W24. §3's stated mechanism for enumerating workers does not exist.** "B9 therefore enumerates the
live `circt` worker node ids **from the Ray runtime context**". `ray.get_runtime_context()` yields the
*current* node id and nothing else — which is exactly how CHIA uses it
(`chia:examples/circt_issue_solver/issue_task.py:66-67`, the cited 60-68). Enumerating live nodes and
their resources requires `ray.nodes()`, which appears **nowhere** in CHIA. The HLD cites CHIA's
same-node pin as precedent for a different-node pin and inherits an API that cannot do it.

**W25. `prlimit` is neither standard library nor race-free as described.** §9's B2 row: "the limits
take FR-06.2's second route, `prlimit` on the spawned child, rather than `preexec_fn` ... **both
routes are standard library**". `/usr/bin/prlimit` is util-linux, not the standard library, and it is
not in `ChiaCirctBaseDockerfile`'s apt set (`chia:dockerfiles/ChiaCirctBaseDockerfile:45-52`).
`resource.prlimit(pid, ...)` is standard library but must be called on an already-started child,
which races the child's `exec` and its first allocations — precisely the window a memory-bomb probe
occupies. The race-free options are `preexec_fn` (which the HLD rejects for good reason) and a
`prlimit` **wrapper binary** in `argv[0]`, which collides with FR-06.1's "execute the `ProbeSpec`'s
tool and argument vector directly, as an argument list passed to `execve`". The HLD does not notice
the collision.

**W26. How the loop's modules reach the workers is unstated, and §8.2's layout creates a
cross-example dependency.** CHIA ships worker modules through the **driver's** `ray.init`, not through
`chia job submit`: `_PY_MODULES = [circt_util.py, issue_task.py, <repo>/chia]` passed as
`runtime_env={"py_modules": ...}` (`chia:examples/circt_issue_solver/circt_issue_loop.py:108-113`,
`204-206`); the submit wrapper passes only `env_vars`
(`chia:examples/circt_issue_solver/fix_issues_submit.sh:46-50`). §8.2 describes
`bug_loop_submit.sh` only as "the `chia job submit` wrapper, **without the token**". It never says
which of its fifteen modules ship, how `contract/` and `mutators/` ship as packages rather than
files, or — the sharp one — that B8 needs `examples/circt_issue_solver/issue_task.py` and
`circt_util.py`, from a **different example directory**, on the worker's `sys.path`. §8.2's own
argument for a separate directory ("Sharing it would also put the loop's files beside the files
FR-12.1 and FR-12.9 pin byte for byte") creates a one-example-imports-another's-worker-modules
pattern that has no precedent in CHIA's `examples/`.

**W27. FR-18.1's acceptance criterion is falsified by the HLD's own schemas.** "The only permitted
reads of `arm` below the seam are the budget ledger (F-14) and the results table (FR-18.4). *AC:* a
search of the apparatus for the field name finds it in exactly those two places and nowhere else."
§2.3 makes `arm` a required `ProbeSpec` field consumed by B2, B4 and B5; §2.4 makes it a required
`CandidateRecord` field written by B2–B9; §5.2 gives `loop.db` a `probe` and a `candidate` table
carrying it. The literal search finds `arm` across the whole apparatus. Either the AC is withdrawn in
the FRD or the schemas stop carrying it and the ledger derives it from `probe_id`.

**W28. FR-20.4's prohibition has no enforcing boundary.** "Maintainer feedback on a filing shall not
be passed to a model without a human first understanding and addressing it. *AC:* **no automated path
exists** from a maintainer comment into a prompt." B6 mirrors issues (with comments, if W21 resolves
that way) into `loop.db`; `CandidateRecord.dedup_evidence` is an undeclared dict that FR-10.5 says
carries "the issue number and URL for a known issue"; B7's triage prompt reads the
`CandidateRecord`. Whether a maintainer's words can reach a prompt depends entirely on what goes in
that dict, which W7 says nobody has decided. No component in §1 owns the boundary.

**W29. §4.1's `llm` concurrency is ambiguous and is not the declared one.** The table gives
`bugloop_llm` resources `{"llm": 2}`, count 2, and says "The resource count is the cap on concurrent
prompts". Two containers at 2 each is four concurrent prompts; CHIA's own comment for the identical
shape says "2 chia-claude-code containers, llm:2 each (**2 concurrent prompts**)"
(`chia:examples/circt_issue_solver/cluster.yaml:3-4`), which is itself either wrong or means something
the HLD has not restated. It matters: the seeded arm's throughput is bounded by `llm` slots, not by
`circt` slots, and FR-14.5 requires the manifest to name "the concurrency" — §2.7 names
`apparatus_concurrency` only.

**W30. The GCP credential path does not reach the container.** §4.3: "On GCP the same file is
delivered by `file_mounts` with mode 0600 rather than by a bind mount from the operator's home
directory." `file_mounts` is "``{remote_path: local_path}`` directories **rsync'd to each node**
before the main script" (`chia:docs/user_guides/cluster_config_reference.rst:115-121`), and the order
of operations on a containerised worker is "2. file_mounts rsync ← **HOST** ... 3. docker setup"
(`chia:docs/user_guides/cluster_config_reference.rst:917-925`). The file lands on the host outside the
container; a bind mount in `run_options` is still required. §4.2's claim that the GCP YAML's "only
differences are a `gcp_nodes` section ... and the credentials handling of §4.3" therefore
under-describes both.

**W31. §8.3 counts three CHIA core changes and needs at least four.** The three new functions
appended to `chia/chipyard/circt.py` are contributions to `chia`, and CHIA requires
"Contributions to ``chia`` should have tests in the corresponding ``chia/subfolder/tests`` folder"
(`chia:AGENTS.md:122`), which FR-19.5 restates. §8.2 puts `tests/` under the **example** directory.
No addition under `chia/chipyard/test/` is proposed. (CHIA's actual directory is `test`, singular —
`chia/chipyard/test/` — not `tests`.)

---

## 3. NIT

**N1.** §8.3 item 3 cites `chia:examples/circt_issue_solver/README.md:101-102` for "the split CHIA
documents". Those two lines are table rows for `chia/chipyard/circt.py` and `prompts/`. The split is
actually stated at README lines 107-110 ("`circt_util.py` (and the chia package itself) ship to
workers via `runtime_env` `py_modules` ... The general build/test primitives it re-exports live in
`chia.chipyard.circt`").

**N2.** §6's B12 contract-mismatch row says the effect is both "iteration ends" and "**stops the
run**"; §2.1 says only "a hard failure of the stage that read it". Pick one.

**N3.** §5.1's diagram contradicts §5.2 twice: it draws `DV --> CR`, while §5.2 lists
`DifferentialVerdict` as consumed by B6, B7 and B11 only; and it draws `RC --> FP` with no
`OV --> FP`, while FR-10.1 computes the primary fingerprint from the oracle verdict (assertion text
or frame names) and takes only the structural hash from the reduced case.

**N4.** §0 narrows a logical worker to "a resource-bearing **container** a node can land on". CHIA and
G-39 both say container *or host process* (`chia:docs/concepts/overview.rst:59-70`, `72-75`). The
narrowing is what makes §3's "head" rows read as containers.

**N5.** §4.1's claim that `lit` is baked once and "`circt_warm_build`'s conditional install then
finds it present and does nothing" depends on one exact path: the check is
`os.path.isfile(_LIT_BIN)` where `_LIT_BIN = os.path.join(_PY_WORKER_BIN, "lit")`
(`chia:chia/chipyard/circt.py:608`, `680`). FR-03.8's acceptance (`lit --version` succeeds;
`pip install lit` reports already satisfied) does not imply lit is at that path. State the path.

**N6.** §9's B5 row says "`circt-reduce` as supplied, unmodified" without saying which binary. The SDK
ships one (verified: `~/.cache/chia-pin-smoke/circt-sdk/bin/circt-reduce`) and FR-03.7 builds one
from source under `-UNDEBUG`. The source-built one has CIRCT assertions on in its own MLIR parsing and
may abort mid-reduction. FRD §10.2 item 4 defers binary resolution to the LLD, but the reducer is the
one case where the answer changes the component's failure model.

**N7.** §3's B9-CLI row gives Timeout "none" and Retry "none" for an interactive program that,
per ADR-D-12, enforces the per-day cap, the `good first issue` refusal and FR-11.8's hold before
presenting. A human walking away mid-approval is a state the store has to survive; §6 has no row.

**N8.** §8.2's counting of `examples/` checks out: six named plus "ten more" is exactly the 16
directories present at `16c35e92`.

**N9.** The following citations were opened and are correct at the lines given, and should not be
re-litigated: `chia/base/ChiaFunction.py:66-96`; `chia/base/tools/ChiaTool.py:20-40`;
`chia/base/tools/AsyncJobTool.py:10-20`; `docs/concepts/overview.rst:19-37, 39-50, 59-70, 89-97,
104-107`; `chia/chipyard/circt.py:616, 628-631, 648-658, 661, 670, 680-686, 698`;
`chia/database/sqlite_node.py:13-19, 21-27, 29-33, 35-38, 40-43`; `chia/trace/metrics.py:14-17`;
`chia/github/github_client.py:33-39, 85, 113-128, 130-134`; `chia/base/bypass.py:3-5`;
`chia/base/cache.py:13-24`; `chia/base/chia_wait.py:1-13`;
`examples/circt_issue_solver/issue_task.py:38, 44-48, 60-68, 71-136, 124, 138-141`;
`examples/circt_issue_solver/circt_issue_loop.py:40-45, 44-45, 50, 77, 120-160, 132-136, 263-273`;
`examples/circt_issue_solver/cluster.yaml:1-19, 36, 46-50, 55-59, 65`;
`examples/circt_issue_solver/fix_issues_submit.sh:21-24, 46-50`;
`examples/circt_issue_solver/README.md:8-9, 59-61, 63-84, 152-154`;
`examples/circt_issue_solver/db.py:27`; `dockerfiles/ChiaCirctBaseDockerfile:45-52, 69-75, 85-86,
92-98, 101, 109, 147, 155, 163-165`; `docs/user_guides/docker_images.rst:17-40`;
`docs/user_guides/cluster_config_reference.rst:326-329, 445-460`; `chia/cluster/gcp_nodes.py:1-30`;
`AGENTS.md:82, 122, 124`. The reuse claims in §9 hold at the lines they cite; §8's byte-identical
list is accurate. This is the strongest part of the document.

---

## 4. Completeness against FRD §10.1

Eight items required for Approved. All eight are present. One fully satisfies.

| # | Item | Present | Satisfies | Why not |
|---|---|---|---|---|
| 1 | Component diagram, CHIA nodes and ChiaTools, never "blocks" | yes | **partly** | Vocabulary correct and "block" absent. Component arithmetic wrong (W14); five tools missing from §3 (W15); three of them have no caller (W16). |
| 2 | Exactly one seam: the five-member package, one version field, one compatibility rule | yes | **no** | Two objects and one control edge cross outside the package (K7); the compatibility rule has no enforcement point (W8). |
| 3 | Per component: worker resource, image, timeout, retry | yes | **no** | Twenty node rows, complete on worker/image/retry. Timeouts have no enforcement mechanism and no failure rows (W2). "Head" is not a placement (W4). No rows for the five tools (W15). |
| 4 | Cluster topology for single machine; GCP only if D-14's date is met; one backend per run | yes | **partly** | Correct in shape, and the D-14 skeleton treatment is right. `llm` concurrency ambiguous and undeclared (W29); GCP credential path does not reach the container (W30). |
| 5 | Data-flow diagram naming every object of §2.5 | yes | **partly** | All twenty objects appear in both §5.1 and §5.2 — this is done properly. But no transport exists for the worker-produced half (K3), and the diagram contradicts the table twice (N3). |
| 6 | Failure model mapped to the error requirements of §5 | yes | **no** | Every component id has at least one row, and most §5 error requirements are mapped. But the A5 row inverts the normal case (K1), fourteen components have no timeout row (W2), worker death has none (W5), and FR-15.5 and FR-16.6 have none (W19). |
| 7 | Decision log referencing every `D-nn` with its ADR file | yes | **yes** | All fourteen, each with its `ADR/` path and the components it shapes. No defects found. |
| 8 | Which CHIA files are touched and which are byte-identical | yes | **partly** | Accurate and checkable as far as it goes. Misses the required `chia/chipyard/test/` additions (W31) and does not address how any of it reaches a worker (W26). |

**FRD §2.4/§2.5 objects in the data-flow section:** all twenty named, in both the diagram and the
table. No omissions.

**Components across §1, §3, §6 and §9:** every id A1–A6 and B1–B12 appears in all four sections. The
gaps are the five ChiaTools (absent from §3 and §9), the offline mutator synthesis (absent from all
four, W18), and the arithmetic in §1's opening sentence (W14).

---

## 5. The one question the HLD must answer before the LLD

**Do the two arms run concurrently or sequentially, and what exactly does one wall-clock second of
`LedgerEntry.amount` measure?**

Everything downstream turns on it. It decides whether `apparatus_concurrency: 2` means one slot per
arm or two slots per arm in turn; whether a stage's charge is elapsed time, worker-occupancy time, or
a sum that double-counts overlap; what `arm` means on the shared, once-per-campaign components (K4);
whether FR-14.5's equality and FR-18.10's stop-both-arms rule are computable at all; how long the
campaign takes against C-10; and whether the gate deadlock of K5 is a certainty or a rarity. G-48 is
the headline's denominator. The HLD defines the unit and never defines the measurement.

---

## 6. The ten riskiest assumptions, with the cheapest check for each

| # | Assumption the HLD relies on | Cheapest check |
|---|---|---|
| 1 | A child rlimit can produce a distinguishable `oom` rather than a `crash` (K6) | No cluster. On the probe host: `bash -c 'ulimit -v 262144; exec circt-opt big.mlir'`, then the same with an `RLIMIT_RSS` cap. Record exit status, signal and the first stderr line for each. Ten minutes; settles FR-06.7 and FR-06.9. |
| 2 | `/workspace/circt/build/bin` survives a repair attempt unchanged (K2) | `md5sum /workspace/circt/build/bin/circt-opt` inside a `circt` container before and after one `run_issue_remote` on CHIA's own example. One run of an example that already works. |
| 3 | A task on a `circt` worker can put a file into the head's artefact tree (K3) | One `@ChiaFunction(resources={"circt":1})` that writes `/tmp/probe_trace.vcd` and returns its path; then `os.path.exists(path)` on the head. Two minutes. |
| 4 | Two `bugloop_circt` containers are two Ray nodes with distinct ids (K5's premise) | `chia up cluster.yaml`, then `python -c "import ray;ray.init(address='auto');print([(n['NodeID'],n['Resources'].get('circt')) for n in ray.nodes() if n['Alive']])"`. **Already verified by source read** (`node_setup.py:622`, `cluster.yaml:94-96`); the command confirms it on the actual host. |
| 5 | Two concurrent gates do not deadlock on `soft=False` (K5) | Two tasks, each `{"circt":1}`, each dispatching an inner `{"circt":1}` task pinned to the other node with `soft=False`. Runs in a minute and either returns or hangs. Do this before writing `gate.py`. |
| 6 | A resource-tagless `@ChiaFunction(...).chia_remote()` lands on the head (W4) | Return `socket.gethostname()` and `ray.get_runtime_context().get_node_id()` from a tagless node; compare against the head's. Two minutes. |
| 7 | The open-plus-closed issue mirror fits inside the GitHub rate limit (W21, and A-21 needs the number anyway) | One authenticated `GET /repos/llvm/circt/issues?state=all&per_page=100&page=1` and read the `Link` last-page header plus `X-RateLimit-Remaining`. One request. Then decide `fetch_comments`. |
| 8 | `-UNDEBUG` leaves the **full** lit suite no redder than `-DNDEBUG` (A-20; F-12's whole verify gate) | Already scheduled by ADR-D-08 and needs no build: run FR-03.6's set-equality check over the whole `test/` tree against the standing build at `~/.cache/chia-pin-smoke/bassert`. One command. |
| 9 | The differential can discriminate a useful share of the corpus (A-19; decides whether B4, `ReduceTool`'s sibling and two harness generators are written at all) | Run FR-08.1's applicability rule over `analysis/pin_window_raw.json` + the extracted `RUN:` lines. No cluster, no build. Do it before any F-08 work, as ADR-D-09 already says. |
| 10 | `claude-opus-5` and `claude-sonnet-5` are ids the CLI accepts (ADR-D-03 marks both `[UNVERIFIED]`, and D-03 blocks F-04, F-11, F-12, F-14) | `claude --print --model claude-opus-5 -p - <<< 'reply ok'`, repeated for `claude-sonnet-5`. One command each, already written into ADR-D-03's follow-up section and not yet run. |

---

## 7. Counts

| Severity | Count |
|---|---|
| KILL | 7 |
| WOUND | 31 |
| NIT | 9 |
| **Total** | **47** |

FRD §10.1 items present: 8 of 8. Fully satisfied: 1 of 8 (item 7, the decision log).
CHIA citations opened and confirmed correct: 40+ across 20 files. Citations found materially
off-target: 2 (N1, W24). Reuse claims in §9 that do not hold at the cited lines: 0.
