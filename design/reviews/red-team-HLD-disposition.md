# Disposition of `red-team-HLD.md`

**Date:** 2026-09-13. **Target of the review:** `02-HLD.md` at 849 lines plus `design/ADR/`.
**Findings:** 47 (7 KILL, 31 WOUND, 9 NIT). **Dispositioned:** 47. **Accepted:** 43.
**Accepted with a different remedy:** 3 (W3, W23, W29). **Rejected on the facts:** 1 (W24).
**No action required:** 2 confirmations (N8, N9).

Every row names the `02-HLD.md` sections the fix landed in and the `01-FRD.md` IDs it moved. Every
FRD change is an erratum at its own ID, struck in place and listed in `01-FRD.md` §1.5, "Errata from
the HLD review".

**Vocabulary.** The two-stream ownership is gone from every document: one builder, and the two halves
survive only as the **supply half** and the **apparatus half**, a test boundary
(`00-README.md` §"The seam rule"). `grep -i "stream a\|stream b\|human team\|architect's agents"`
over `design/*.md` and `design/ADR/*.md` returns nothing.

---

## 1. The one question

**Do the arms run concurrently or sequentially, and what does one wall-clock second of
`LedgerEntry.amount` measure?**

**Answered.** The arms run **sequentially**, each for the same fixed wall-clock window `W` recorded
in `budget.yaml`, on the same fixed-size cluster, in an order also recorded in `budget.yaml`. One
second of `amount` on the single `arm_window` entry per arm is one elapsed second of that arm's
window, metered by the campaign driver on the head. Per-stage entries carry `scope=stage` and are
occupancy; CPU seconds, tokens and cost are `observed` and never `amount`.

| Where | What carries it |
|---|---|
| `02-HLD.md` §2.9 | `LedgerEntry`'s `scope` field, the three-valued `arm`, and the paragraph "The answer to the review's one question" |
| `02-HLD.md` §3 | "How B12 sequences the campaign"; the B12 row's timeout column reads "the two arm windows, which it meters" |
| `02-HLD.md` §2.10 | `arm_window_seconds` and `arm_order` as manifest fields |
| `02-HLD.md` §6 | B12's window row: both windows reported |
| `01-FRD.md` G-48 | Rewritten; the old "wall-clock seconds per arm" wording struck |
| `01-FRD.md` FR-18.10 | Rewritten; "the other arm shall stop at the same moment" struck |
| `01-FRD.md` FR-14.1, FR-14.4, FR-14.5 | The window, the arm order, `scope`, the `shared` arm value |
| `ADR/ADR-D-04-budget-unit.md` | Amended, with the cost of the second window stated |

---

## 2. KILL

| Id | Finding | Disposition | HLD sections | FRD IDs |
|---|---|---|---|---|
| K1 | `CandidateRecord` is two objects under one name; F-16 collapses | **Accepted.** Split into `ProbeResult`, one per probe, always produced, the only object crossing the seam upward, and `CandidateRecord`, one per candidate, apparatus-internal and persisted, referencing `probe_id`. §6's A5 row is inverted back: a missing record is recorded, not fatal. | §1.1, §2.1, §2.7, §5.2, §5.3, §6 (A5 rows), §10 | G-47, §2.5, FR-16.1; `00-README.md` seam list |
| K2 | B8 leaves the worker's binaries patched | **Accepted, both measures.** (i) B8 runs on its own worker type `bugloop_repair`, `{"repair": 1}`, count 1, same image, so no verdict-producing node ever lands on a worker that built a patch. (ii) B8 runs `circt_git_reset` then `circt_ninja_build` of the tool targets after every attempt, and B2 checks each tool binary's SHA-256 against the image manifest before every probe. Cited at `circt_util.py:52-62`, `issue_task.py:216-230`, `circt.py:672-680`, all verified. | §3 ("Why `repair` is a separate worker type"), §4.1, §6 (B2 and B8 rows), §8.1, §9 | **FR-03.16 new**, FR-06.1 (the `--version` criterion struck), **FR-12.11 new** |
| K3 | No worker-to-head file transport | **Accepted.** The artefact tree is one host directory bind-mounted into every worker container at the identical absolute path, using the `run_options` `-v` mechanism `cluster.yaml:55-59` already uses; the head driver runs on that host. Small results still ride home in return values. GCP needs a shared bucket mounted at the same path and is deferred with GCP. | §4.1 (the artefact mount), §4.2, §5 (opening), §5.2, §6 (B10b row), §2.10 (`artefact_root`) | **FR-17.9 new**; `ADR-D-14` amended |
| K3a | The report's "256 KB return-value cap" | **Rejected as stated, and corrected in place.** There is no framework cap. The number is one line of CHIA's own example, `os.path.getsize(p) <= 256_000` at `issue_task.py:268`, choosing which repro files to inline in its return dict. No such constant exists under `chia/`. §5 says so explicitly and the loop's own cap is FR-17.7's artefact cap. | §5 (opening) | none |
| K4 | `LedgerEntry.arm` has no admissible value for a third of its producers | **Accepted.** `arm` takes `seeded`, `mutation` or `shared`. Per-arm sums are over arm-specific entries; `shared` is reported beside them, never folded in and never split. | §2.9, §6 (A7, B1, B6a rows) | FR-14.4 |
| K5 | The gate's cross-worker re-run deadlocks the two-worker cluster | **Accepted.** `gate_decide` (B9a) holds **no** `circt` resource and moves to the head; it dispatches the re-run as a separate `circt` node (B9b) with `NodeAffinitySchedulingStrategy(..., soft=True)` preferring a node other than the original, and records `same_worker` truthfully either way. The live-node enumeration uses `ray.nodes()` filtered to `Alive`, which CHIA itself does (see W24). | §1.1, §1.3, §3 (the B9 rows and "How B9a lands question 1"), §6 (B9b rows), §9 | FR-13.2 |
| K6 | `oom` unproducible; the failure mode is a false `crash` candidate | **Accepted.** The memory limit is `RLIMIT_AS` on the child; `RLIMIT_RSS` is dropped. Classification is by evidence: an abort whose stderr carries `std::bad_alloc`, `out of memory` or `LLVM ERROR: out of memory`, or whose limit was hit, is `oom` and never `crash`, and `oom` takes precedence over all three firing classes. | §2.7 (`limit_hit`), §6 (three B2 rows, the B3 `LLVM ERROR:` row), §9 (B2) | FR-06.2, FR-06.7, FR-07.2 |
| K7 | Not one seam: two objects and one control edge cross outside the package | **Accepted.** The package becomes seven schemas, `SeedRecord`, `BudgetFile`, `ProbeSpec`, `ProbeResult`, `FeedbackBundle`, `LedgerEntry`, `RunManifest`, plus one interface, `generate(seed, feedback, remaining) -> list[ProbeSpec]`, with `LedgerSnapshot` (arm, unit, spent, cap) defined in the package as its read-only argument view. | §2.1, §2.3, §2.4, §2.5, §2.13, §1.1 diagram | G-47, §2.5, §10.1 item 2; `00-README.md` |

---

## 3. WOUND

| Id | Disposition | HLD sections | FRD IDs |
|---|---|---|---|
| W1 | **Accepted.** See §1 above. | §2.9, §3, §2.10, §6 | G-48, FR-14.1, FR-14.4, FR-14.5, FR-18.10 |
| W2 | **Accepted.** Three enforcement points named, and every row in §3 says which it uses: `subprocess` (`communicate(timeout=)` plus killpg, CHIA's own pattern), `turn` (the phase timeout or the client's), `driver` (`chia_wait(timeout=)` then `ray.cancel(force=True)`). §6 gains a single generic timeout row covering every node. | §3 (the timeout paragraph and every row), §6 (first generic row) | none |
| W3 | **Accepted, different remedy.** `chia_wait`'s stuck test requires the resource to be **available** (`chia_wait.py:69-80`, `238-241`), so no parameter change makes it fire on a saturated cluster. Lowering `min_free_fraction` would not have worked either. The HLD instead states what the rail is for, a wedged raylet with the resource free, and states that a probe queued behind a busy slot is ordinary queuing bounded by the arm window `W`. §6 has a row for each case. | §3 (retry policy), §6 (last two B12 rows) | none |
| W4 | **Accepted.** "Head" is now a placement with a mechanism: a `@ChiaFunction` dispatched with `NodeAffinitySchedulingStrategy(node_id=<head>, soft=False)`, which CHIA already uses at `cache.py:356-357` and `bypass.py:226-228`. It is therefore a node (FR-19.1) and it lands on the head. B12 and B9c are programs, not nodes, and are labelled as such. | §3 (the head paragraph), §1.2, §1.3 | none |
| W5 | **Accepted.** §4.1's claim is corrected: under `max_retries=0` Ray does **not** re-queue, so the hazard is a task failing with no probe status. §6 gains a generic worker-death row that completes the `ProbeResult` from the driver. | §4.1 ("The two levels of limit, corrected"), §6 (second generic row) | none |
| W6 | **Accepted.** B1 bakes the whole `ImageSpec` target set, so nothing calls `circt_warm_build` and no arm pays another arm's warm-up. §9's reuse claim is explicitly withdrawn. Measured: the published CHIA image bakes only `circt-opt` (M5), which is why CHIA needs the warm-up and this design does not. | §4.1, §9 (B1) | none; `ADR-D-08` amended |
| W7 | **Accepted.** All ten dicts get a closed key list in one table, checked by `validate`; adding a key is a MINOR bump, removing one a MAJOR. | §2.11 | none |
| W8 | **Accepted.** The enforcement point is the committed fixture set: every fixture carries its recorded `contract_version` and the half-level replay validates all of them, so a MAJOR bump fails the test until the fixtures are re-recorded. | §2.2, §2.13 | none |
| W9 | **Accepted.** One rule for all three text fields: the text is carried when at or under FR-17.7's cap and is null otherwise, with the companion path field the only reference. `ProbeSpec.input_path` and `ProbeResult.reduced_path` are added. | §2.6, §2.7, §2.8, §2.12 | none |
| W10 | **Accepted.** The conditionals are enforced by `validate`, not described in prose: `mutator_id`, `mutator_seed_int` and `source_test_path` non-null when `arm == "mutation"` and null otherwise. `turn_cost` has a declared shape for each arm, with `turn: null` on the mutation arm, so both arms pass the same field through the same code path. | §2.6 | none |
| W11 | **Accepted.** `CandidateRecord` is apparatus-internal and its required set is conditional on `oracle_class`: a `differential` candidate has every reducer, dedup and gate field null and `validate` requires them null, rather than inventing a dozen sentinels. | §5.3 | none |
| W12 | **Accepted, all five.** Added to the manifest: `budget_unit` (completes FR-14.5's four fields), `confirmation_cutoff_date` (FR-18.8), `assertion_baseline_count` (FR-03.5), `x_policy` (FR-08.4); `mutator_set_sha` becomes required (FR-05.2). | §2.10 | FR-14.5 |
| W13 | **Accepted.** `FilingRecord` gains the licence confirmation, the confirming approver and the timestamp; B9c asks for it with the patch on screen and a decline downgrades to `report`. | §5.2, §6 (B9c row) | FR-20.5; `ADR-D-12` amended |
| W14 | **Accepted.** The count is restated as twenty-five components, counted as rows: twenty-one nodes, one `SQLiteNode`, one `ChiaTool`, two head-side programs. A6, B6, B9 and B10 have one row per component. | §1 (opening), §1.2, §1.3 | none |
| W15 | **Accepted.** With four of the five tools deleted (W16, W17), the remaining `ProbeWriteTool` gets its own row in §3 with its placement and the reason for it, citing `overview.rst:42-50`. | §3 (last table row and the paragraph after it) | none |
| W16 | **Accepted.** `ProbeRunTool`, `ReduceTool` and `IssueMirrorTool` are **deleted**: no model stage may legally call them. FR-19.1's `AsyncJobTool` rule is a conditional and is now satisfied vacuously, its check still running. `[ARCHITECT-CHECK]` | §1.4, §3, §9 (B2, B5, B6a) | none |
| W17 | **Accepted.** `SeedReadTool` is **deleted**; A3 uses the `BashTool` §9 already claimed as reuse. | §1.4, §9 (A3) | none |
| W18 | **Accepted.** The offline mutator synthesis becomes component **A7**, with worker, timeout, retry, idempotency and two failure rows, and its ordering constraint is drawn: B6a's mirror is its input, so the mirror runs before the pre-registration commit, and A7 refuses to run after it. A7 charges `shared`. | §1.2, §1.3, §3, §6, §8.2, §9 | none; `ADR-D-05` amended |
| W19 | **Accepted, both.** FR-16.6 is owned by A5 and has fields, `abandoned` and `abandon_reason`, on `FeedbackBundle`. FR-15.5 is owned by B6b and has a field, `contamination_lower_bound`, on `CandidateRecord`. Each has a §6 row. | §1.2, §1.3, §2.8, §5.3, §6 | none |
| W20 | **Accepted.** B11's output is enumerated in full, and a missing mode or seed-set qualifier is a render failure with its own §6 row. | §1.3 (the paragraph after the table), §6 (B11 rows) | none |
| W21 | **Accepted.** The mirror calls `recent(n, fetch_comments=False)`, as CHIA's own example does at `triage.py:61`, with an issue cap rather than a page cap. The cost, a known-issue match existing only in a comment is missed, is recorded as `comments_mirrored=false` and disclosed. `[ARCHITECT-CHECK]` | §1.3, §2.11, §6 (B6a rows), §9 (B6a) | FR-10.9 |
| W22 | **Accepted.** The cap becomes an issue count `n`, which is what `recent` takes; the page count is struck. No private method is called and no second pager is written. | §2.5, §2.11, §6 | FR-10.9 |
| W23 | **Accepted, different remedy.** Rather than acknowledging the deviation, B6a and B9a's poll **move to the head**, where CHIA documents `GithubIssuesNode` as belonging. That deletes the worker bind-mount, the GCP `file_mounts` question and half of §4.3, and it resolves W30 entirely. | §1.1, §1.3, §3, §4.3 | none |
| W24 | **Rejected on the facts.** `ray.nodes()` does **not** appear nowhere in CHIA: `chia/base/dispatch_proxy.py:85-94` caches alive `ray.nodes()` entries for exactly this purpose. The HLD now cites that precedent instead of the same-node pin, so the mechanism is CHIA's own. The finding's underlying point, that `get_runtime_context()` cannot enumerate, is correct and the text no longer claims it can. | §3 ("How B9a lands question 1"), §9 (B9) | none |
| W25 | **Accepted.** B2 takes FR-06.2's **first** route, `resource.setrlimit` in the child before `exec` from a module-level `preexec_fn` that binds its references at import and calls nothing else. `prlimit` is rejected on two grounds now stated: util-linux is absent from the image's apt set and adding it is a dependency FR-19.8 prices, and `resource.prlimit(pid, ...)` races the child's first allocations. The false claim that "both routes are standard library" is removed. `[ARCHITECT-CHECK]` | §9 (B2) | FR-06.2 |
| W26 | **Accepted.** §8.2 states the driver's `_PY_MODULES` list in full, including `contract/` and `mutators/` as package directories and, explicitly, CHIA's own `issue_task.py` and `circt_util.py` from the other example directory, which B8 needs on the worker's `sys.path` and FR-12.1 forbids copying. The cross-example dependency is named as the price of running the chain byte-identical. | §8.2 | none |
| W27 | **Accepted.** The AC becomes a search for a **branch** on `arm`, not for the field name, plus a test that two otherwise-identical `ProbeSpec`s produce identical apparatus output. | §2.6, §5.3 | FR-18.1 |
| W28 | **Accepted.** The boundary is owned by B6a and B6b and is structural: the mirror stores no comments at all, and `dedup_evidence`'s declared keys carry an issue's number, URL, state and labels and never its text. A §6 row records it. | §2.11, §6 (B6a row) | FR-10.9 |
| W29 | **Accepted, different remedy.** Rather than restating CHIA's ambiguous comment, `bugloop_llm` is declared `{"llm": 1}` on each of two containers, so the concurrent-prompt cap is unambiguously the container count, and the manifest records `llm_concurrency`. `[ARCHITECT-CHECK]` | §4.1, §2.10 | none |
| W30 | **Accepted, dissolved by W23.** With the token on the head and no worker holding it, there is no credential to deliver to a container on GCP. §4.3 states why `file_mounts` could never have done it. | §4.3 | none |
| W31 | **Accepted.** A fourth CHIA core change: tests under `chia/chipyard/test/`, the directory's real name, singular, distinct from the example's own `tests/`. | §8.3 item 4 | FR-19.5 |

---

## 4. NIT

| Id | Disposition | Where |
|---|---|---|
| N1 | **Accepted.** The citation moves to `README.md:107-110`, and the HLD states what those lines say. | §8.3 item 3 |
| N2 | **Accepted.** One reading: the mismatch is a hard failure of the reading stage, which B12 turns into a run stop. The row says exactly that. | §6 (B12 contract row), §2.2 |
| N3 | **Accepted, both.** `DifferentialVerdict` feeds the informational `Report`, not `CandidateRecord`; `OracleVerdict` feeds `Fingerprint` alongside `ReducedCase`. The corrections are called out under the diagram. | §5.1 |
| N4 | **Accepted.** A logical worker is "a resource-bearing container **or host process**", per `overview.rst:59-70`, `72-75` and G-39. | §0 |
| N5 | **Accepted.** The lit path is stated: `/home/ray/anaconda3/envs/py_worker/bin/lit`, which is `_LIT_BIN` at `circt.py:608`. | §4.1, §8.3 item 1 |
| N6 | **Accepted.** B5 uses the **source-built** `circt-reduce` from the image, because FR-06.1 forbids SDK binaries on the measured path and the reduced case must be parsed by the build that fired. The consequence, that its own assertions are on and it can abort mid-reduction, gets a §6 row. `[ARCHITECT-CHECK]` | §6 (B5 `reducer_aborted` row), §9 (B5) |
| N7 | **Accepted.** A §6 row: nothing is written until an approval is complete, so a human who walks away leaves the candidate `held` with `held_reason=awaiting_approval` and the next invocation presents the same report. | §6 (B9c row) |
| N8 | **Confirmation, no action.** The `examples/` count stands. | §8.2 |
| N9 | **Confirmation, no action.** The 40-odd verified citations are carried forward unchanged. | throughout |

---

## 5. `[ARCHITECT-CHECK]` items

Ten choices this revision made because a finding demanded one and neither `01-FRD.md` nor the review
determined it. Each is the smallest choice consistent with Ponytail. Each is marked in `02-HLD.md` at
the point it is made.

| # | Choice | Section | Why this one |
|---|---|---|---|
| 1 | Four of the five MCP tools are deleted, leaving `ProbeWriteTool` | §1.4 | Three had no legal caller and one duplicated `BashTool`; deleting is cheaper than inventing callers |
| 2 | The mutation arm receives an empty `FeedbackBundle` through the one `generate` signature, and ignores it, asserted by a test on A4's body | §2.1 | FR-16.2 wants no feedback parameter and FR-05.4 wants one code path; one signature with an asserted non-read satisfies both without a second interface |
| 3 | `turn_cost` is required on both arms with `turn: null` on the mutation arm | §2.6 | Keeps FR-04.3's field on every `ProbeSpec` without a mutation-arm branch |
| 4 | `preexec_fn` calling only `resource.setrlimit`, rather than `prlimit` | §9 (B2) | FR-06.2 names this route first; `prlimit` is a dependency and `resource.prlimit` races |
| 5 | The issue mirror fetches no comments | §9 (B6a), FR-10.9 | Keeps the mirror inside the rate limit and makes FR-20.4 true by construction; the cost is a missed comment-only match |
| 6 | `bugloop_llm` declared `{"llm": 1}` on two containers | §4.1 | Makes the concurrent-prompt cap unambiguous; CHIA's own `llm:2` comment contradicts itself |
| 7 | `LedgerEntry.scope` added to separate the arm window from per-stage occupancy | §2.9 | Lets FR-14.4 keep per-stage accrual without the per-stage sums becoming the budget |
| 8 | B5 uses the source-built `circt-reduce`, not the SDK's | §9 (B5) | FR-06.1's rule about which binaries measure; the cost is a reducer that can abort on its own assertions |
| 9 | A7 created as a component, charging `shared`, refusing to run after the pre-registration commit | §1.2, §3 | ADR-D-05 describes it; without an id it had no owner, no ordering and no cost |
| 10 | B6a and B9a's poll move to the head rather than keeping the worker-side credential | §4.3 | Follows CHIA's documented placement and deletes the bind mount, the GCP credential path and half of §4.3 |

---

## 6. Completeness re-check against FRD §10.1

| # | Item | Status after this revision |
|---|---|---|
| 1 | Component diagram, CHIA nodes and ChiaTools, never "blocks" | **Satisfied.** Arithmetic restated (W14), the one tool has a row (W15), the four with no caller are gone (W16, W17), the missing component is added (W18) |
| 2 | Exactly one seam | **Satisfied.** Seven schemas plus the interface (K7), and the compatibility rule has a place where it can fire (W8) |
| 3 | Per component: worker resource, image, timeout, retry | **Satisfied.** Timeouts have three named enforcement points and a failure row (W2); "head" is a placement (W4); the tool has a row (W15) |
| 4 | Cluster topology | **Satisfied.** Three worker types, the `llm` cap declared (W29), the credential on the head (W23, W30), GCP's deferral stated in terms of the artefact mount (K3) |
| 5 | Data-flow diagram naming every object of §2.5 | **Satisfied.** Twenty-one objects including `ProbeResult`; the transport exists (K3); the two diagram contradictions fixed (N3) |
| 6 | Failure model mapped to §5's error requirements | **Satisfied.** The A5 row is inverted back (K1), timeouts and worker death have generic rows (W2, W5), FR-15.5 and FR-16.6 have rows (W19) |
| 7 | Decision log referencing every `D-nn` | **Satisfied**, as before, with four ADRs marked amended |
| 8 | Which CHIA files are touched and which are byte-identical | **Satisfied.** Four core changes not three (W31), and how the modules reach a worker (W26) |
