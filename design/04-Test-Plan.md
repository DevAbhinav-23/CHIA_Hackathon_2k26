# 04 Test Plan: the closed CIRCT bug loop

**Status: Draft.** Date: 2026-09-14. Normative for **evidence**: what is run, against which fixture,
and what result counts as the requirement holding. `01-FRD.md` is normative for behaviour, `02-HLD.md`
for component structure, `03-LLD.md` for modules, schemas and command lines. Where this document
contradicts any of the three, that document wins and the contradiction is a defect here
(`00-README.md`).

This document answers `01-FRD.md` §10.3's seventeen items. It is written against `03-LLD.md` §14.7's
module index and §3's function names **as they stand on 2026-09-14**, that is after the revision
`design/reviews/red-team-LLD-disposition.md` records and after the nine additions this plan's own §16
asked for. §16 is now the **resync log** and records what changed on each side.

**Contract 2.0.** Every version-bearing test below reads `CONTRACT_VERSION` as `2.0`: `SeedRecord`
gained the required `diff` and `test_files`, which `03-LLD.md` §2.2's own rule makes a MAJOR bump, so
the incompatible-instance fixtures are at `1.0` and `3.0` and no longer at `2.0`.

**Totals.** 456 tests: 401 unit, 17 integration, 9 system, 15 non-functional, 14 equivalence class.
No test is withdrawn by this resync and every surviving test keeps its identifier. Every module of
`03-LLD.md` §14.7 has unit tests, every function named in `03-LLD.md` §3 has at least one, and every
one of the 198 functional requirements and all 12 non-functional requirements appears in §12's
traceability table.

---

## 0. Conventions

### 0.1 Test identifiers

`T-<level>-<module>-<n>`, where `<n>` is two digits, unique within its `<level>`/`<module>` pair, and
never reused once written. A withdrawn test is struck through and marked `WITHDRAWN`, as
`01-FRD.md` does with requirements.

| Level | Meaning |
|---|---|
| `U` | Unit. One module, one behaviour, no other loop module running for real. |
| `I` | Integration. One seam crossing, one side live and the other replayed from a recorded fixture. |
| `S` | System. The single-machine cluster of `03-LLD.md` §12.1, end to end. |
| `N` | Non-functional. One NFR of `01-FRD.md` §6. |
| `E` | Equivalence class. One class of the probing-input space, driven end to end through the apparatus. |

`<module>` is a short slug, one per source artefact of `03-LLD.md` §1.1 and §1.2.

| Slug | Artefact | Test module |
|---|---|---|
| `schema` | `contract/schema.py` | `tests/test_schema.py` |
| `fixt` | `contract/fixtures/` | `tests/test_fixtures.py` |
| `layout` | the repository-wide static checks | `tests/test_layout.py` |
| `corpus` | `corpus.py` | `tests/test_corpus.py` |
| `pin` | `pin_select.py` | `tests/test_pin_select.py` |
| `gen` | `generate_task.py` | `tests/test_generate_task.py` |
| `mut` | `mutators/` | `tests/test_mutators.py` |
| `msyn` | `mutator_synth.py` | `tests/test_mutator_synth.py` |
| `probe` | `probe_task.py` | `tests/test_probe_task.py` |
| `ddmin` | `ddmin.py` | `tests/test_ddmin.py` |
| `triage` | `triage_task.py` | `tests/test_triage_task.py` |
| `repair` | `repair_adapter.py` | `tests/test_repair_adapter.py` |
| `gate` | `gate.py` | `tests/test_gate.py` |
| `appr` | `approve.py` | `tests/test_approve.py` |
| `budget` | `budget.py` | `tests/test_budget.py` |
| `ledger` | `ledger.py` | `tests/test_ledger.py` |
| `feed` | `feedback.py` | `tests/test_feedback.py` |
| `store` | `store.py` | `tests/test_store.py` |
| `results` | `results.py` | `tests/test_results.py` |
| `driver` | `bug_loop.py` | `tests/test_bug_loop.py` |
| `core` | the three functions added to `chia/chipyard/circt.py` | `chia/chipyard/test/test_circt_probe.py` |
| `image` | `dockerfiles/ChiaCirctAssertDockerfile` and the `ImageSpec` it emits | `tests/test_image_spec.py` |
| `prompt` | `prompts/` and the shared JSON-footer parser | `tests/test_prompts.py` |
| `cluster` | `cluster_single.yaml`, `cluster_gcp.yaml` | `tests/test_cluster_yaml.py` |
| `submit` | `bug_loop_submit.sh` | `tests/test_submit.py` |
| `byaml` | the committed `budget.yaml` | `tests/test_budget_yaml.py` |

Five of those test modules, `test_image_spec.py`, `test_prompts.py`, `test_cluster_yaml.py`,
`test_submit.py` and `test_budget_yaml.py`, test artefacts that are not Python modules: the
Dockerfile, `prompts/`, the two cluster YAMLs, `bug_loop_submit.sh` and the committed `budget.yaml`.
`03-LLD.md` §1.3 now names all five, gives each the test module above, and **exempts each by name**
from its source-to-test mapping, which is a rule over source modules and which none of the five is.
The earlier erratum is therefore discharged: `T-U-layout-01` compares this plan's exemption list
against the LLD's for equality rather than asserting one of its own, and the LLD's own count is
twenty-five test modules under `tests/`, eighteen plus two structural plus these five.

Integration and system slugs name the crossing or the run rather than a module: `gen-app`, `app-tri`,
`tri-rep`, `rep-gate`, `gate-appr`, `ledger`, `feed`, `version`; `disc`, `calib`, `pilot`, `isolate`,
`regen`, `submit`, `lit`, `cluster`, `artefact`. Non-functional slugs are `nfr01` to `nfr12`. The
equivalence level uses one slug, `input`.

### 0.2 What every test states

Every test carries, in its own docstring and in the tables below:

1. **FR trace.** The requirement identifiers it exercises, which is the reverse direction of §12.
2. **Pass criterion.** One assertable statement. A test whose criterion is a judgement is a defect in
   this plan, exactly as `01-FRD.md` §5's preamble forbids in an acceptance criterion.
3. **Fixture.** The named fixture directory of §13, or `none` for a test that constructs its input
   inline.
4. **Runtime tier.** One of the four of §0.5.

### 0.3 Framework

**pytest**, which is what CHIA's own tests use and the only test dependency CHIA declares
(`chia:pyproject.toml:47`, `test = ["pytest==9.0.3"]`). CHIA's `addopts = "--import-mode=importlib"`
(`chia:pyproject.toml:61-63`) is inherited, so tests import under their full package path rather than
by bare filename, which matters because this plan has two test directories with similar names.

CHIA's own conventions are followed and not reinvented:

- **Tiering by environment variable and a collection hook.** `chia/models/tests/conftest.py` skips its
  `live_remote` tests unless `CHIA_LIVE_CLUSTER=1`, through `pytest_collection_modifyitems`, and
  registers the marker in `pytest_configure`. `examples/circt_bug_loop/tests/conftest.py` does the
  same for four markers, `needs_sdk`, `needs_image`, `needs_cluster` and `live_remote`, gated by
  `BUGLOOP_SDK`, `BUGLOOP_IMAGE_TAG`, `BUGLOOP_CLUSTER` and `CHIA_LIVE_CLUSTER`.
- **A live-cluster fixture that ships this checkout.** `chia/models/tests/conftest.py`'s `ray_cluster`
  fixture calls `ray.init(address=..., runtime_env={"py_modules": [ship]})` so the worker runs the
  checkout's code rather than the image's. The `bugloop_cluster` fixture of §3 is that fixture with
  `_PY_MODULES` from `03-LLD.md` §13.1 in place of the single `chia` package path, and the same
  `CHIA_SHIP_PY_MODULES` override.
- **Tier-0 and tier-1 in one file.** `chia/database/test/test_sqlite_node_live.py` puts both tiers in
  one module and says in its own docstring which is which; the test modules here do the same, with
  the tier stated per test.
- **Real services, not mocks, where the service is the thing under test.**
  `chia/github/test/test_github_issues_e2e.py` hits `api.github.com` directly. The GitHub tests here
  mock nothing either; they replay a **recorded** response set, because NFR-04 needs a trace with no
  live requests in it and because a rate limit must not make a test flaky.

No test framework, assertion library, mocking library, HTTP-recording library or fixture library is
added. `unittest.mock.patch` is standard library and is the one substitution mechanism used.

### 0.4 How a unit test calls a `@ChiaFunction` node, with no Ray

`ChiaFunction.__call__` wraps the function in `_wrapper`, and `_wrapper` calls
`func(*args, **kwargs)` in-process, taking the profiler branch only when a profiler is enabled
(`chia:chia/base/ChiaFunction.py:107-121`). Ray appears only under `.chia_remote()`, `.options()` and
the bypass path. So:

```python
from examples.circt_bug_loop.probe_task import probe_execute

out = probe_execute(spec, image_spec, limits, artefact_dir)   # plain call, no Ray
```

Every unit test in §1 calls its node this way. No `ray.init` is issued, no cluster is needed, and the
decorator's `resources=` and `max_retries=` are inert. Three consequences the tests rely on and
assert:

- The **placement** declared by the decorator is not exercised by a plain call, so it is tested
  statically instead: `T-U-layout-06` reads `<fn>._chia_options` (which the decorator sets,
  `chia:chia/base/ChiaFunction.py:129`) for every node and compares it to `03-LLD.md` §3.2's table.
  That is how `T-U-gate-02`'s "the decision stage declares no worker resource" (FR-13.2) is asserted.
- **Head-only nodes** are plain functions under a plain call, so `budget.py`, `ledger.py`,
  `feedback.py`, `results.py` and `store.py` are wholly tier 0.
- **Worker-only nodes** are callable in-process too, but their bodies run real binaries; their tier
  is therefore set by the binary they invoke, not by Ray.

The one thing a plain call cannot exercise is the scheduling behaviour of FR-13.2, FR-12.11 and
FR-17.9. Those are system tests, and §12.3 lists them as such.

### 0.5 Runtime tiers

| Tier | Name | What it needs | Marker |
|---|---|---|---|
| **T0** | no CIRCT | Python 3.10.19 and this repository. No CIRCT binary, no clone, no network. | none |
| **T1** | SDK or a measured build | The release SDK at `~/.cache/chia-pin-smoke/circt-sdk`, the assertions-on build at `~/.cache/chia-pin-smoke/bassert_g`, or the blobless `llvm/circt` clone. No Docker. | `needs_sdk` |
| **T2** | the assertions-on image | A built `chia-circt-assert:<tag>` and a Docker daemon. | `needs_image` |
| **T3** | the single-machine cluster | `chia up cluster_single.yaml`, five worker containers, the bind-mounted artefact root. | `needs_cluster` |

A tier includes everything the tiers below it need. A test states the **lowest** tier at which it can
run; §14 is the full matrix and §15 the order.

### 0.6 How integration tests run

Two rules, and they are `02-HLD.md` §2.13's, not new.

1. **The seam rule.** Each half is exercised against **recorded fixtures of the other half**, never
   against the other half running. The supply half's test entry point replays the apparatus half's
   recorded `ProbeResult`, `LedgerEntry` and `RunManifest`; the apparatus half's replays the supply
   half's recorded `SeedRecord`, `BudgetFile`, `ProbeSpec` and `FeedbackBundle`. Each half's fixture
   set covers **all seven** members, not only the ones flowing in its own direction, because a half
   that never exercises a schema cannot discover that it broke it.
2. **Fixtures are recorded, never hand-written.** `bug_loop.py --record-fixtures <dir>` writes every
   instance a half produces, after `contract.validate` has accepted it
   (`03-LLD.md` §13.1). A fixture that does not validate is a defect in its producer, not in the
   fixture.

Integration tests are tier 0 wherever the live side is head-only, and tier 1 or tier 2 where the live
side runs a binary. **None of them starts Ray**, for the same reason §0.4 gives: a `@ChiaFunction`
called plainly runs in-process, and a seam crossing is a data crossing, not a dispatch. CHIA's own
tests do start Ray where the thing under test is dispatch itself
(`chia/base/test/test_chia_remote_blocking.py`, `chia/models/tests/conftest.py`), and this plan does
the same only at the system level, where dispatch **is** the thing under test.

### 0.7 How system tests run

On the single-machine cluster of `03-LLD.md` §12.1: head plus five worker containers on one host, two
`bugloop_llm` at `{"llm": 1}`, two `bugloop_circt` at `{"circt": 1}`, one `bugloop_repair` at
`{"repair": 1}`, `min_workers` equal to `max_workers` on all three. Brought up with
`chia up cluster_single.yaml` and driven through `bug_loop_submit.sh`, never by running the driver
directly, because driver logs are retrievable only for a submitted job
(`chia:examples/circt_issue_solver/fix_issues_submit.sh:5-9`) and NFR-09 asks for exactly that.

Every system test runs against its own `budget.yaml` under `tests/system/budget_tiny.yaml`, a
complete and valid file by `03-LLD.md` §9.1's schema whose `arm_window_seconds` is 600 `[DEFAULT]`
rather than 14,400, and which is committed so FR-14.2's pre-registration check passes on it. Nothing
else about it differs from `03-LLD.md` §9.5.

### 0.8 Number discipline

Every number here comes from `01-FRD.md`, `02-HLD.md`, `03-LLD.md`,
`analysis/measurements/2026-09-13-frd-followups.md` (M1 to M6),
`analysis/measurements/2026-09-13-slang-verilator-bugcount.md` (M7 to M9), or carries `[DEFAULT]`.
A `[DEFAULT]` that sizes a **fixture** lives here, which is the home `01-FRD.md` FR-14.1 gives it; a
`[DEFAULT]` that is a **campaign** parameter is a `budget.yaml` key and is quoted here, never
redefined. The seven `acceptance` keys of `03-LLD.md` §9.3 are the numbers those feature-acceptance
criteria place in `budget.yaml`; this plan uses those keys' values and owns the fixtures themselves.

Spelling is British. No em-dashes, here or in any string this document specifies.

---

## 1. Unit tests, module by module

One subsection per artefact of `03-LLD.md` §14.7. Columns are the same everywhere: the test, the
behaviour it pins, the fixture, the tier, and the requirements it traces to. Every test's pass
criterion is the behaviour column read as an assertion.

### 1.1 `contract/schema.py` (the seam), 23 tests

The validator's error codes are closed (`03-LLD.md` §2.1) and every one is exercised, which is
`01-FRD.md` §10.3 item 1's "the contract validator against malformed inputs for every error code".

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-schema-01` | `E001_MAJOR_MISMATCH` in **both** directions against `CONTRACT_VERSION` `2.0`: a `1.0` instance and a `3.0` instance each raise, and the message names both versions verbatim | `malformed/major_older.json`, `malformed/major_newer.json` | T0 | FR-04.3 |
| `T-U-schema-02` | `E002_MISSING_FIELD` when a required field is `None`, naming `<Class>.<field>` | `malformed/` | T0 | FR-04.3 |
| `T-U-schema-03` | `E002_MISSING_FIELD` when a `from_json` payload lacks a declared field, listing every missing name sorted | `malformed/` | T0 | FR-04.3 |
| `T-U-schema-04` | `E003_WRONG_TYPE` after `Optional` is unwrapped; and `LedgerEntry.amount` negative | `malformed/` | T0 | FR-14.4 |
| `T-U-schema-05` | `E004_BAD_ENUM` for a `build_status` outside FR-06.9's seven, an `arm` outside three, a `scope` outside two, a `mode`, `seed_set`, `deployment`, `unit`, `polarity`, `shape` and `limit_hit` outside theirs | `malformed/` | T0 | FR-06.9, FR-14.4 |
| `T-U-schema-06` | `E005_CONDITIONAL_REQUIRED`: `mutator_id`, `mutator_seed_int`, `source_test_path` null on `arm == "mutation"`; `turn_cost.metered` disagreeing with `tokens_in` | `probe_spec/mutation_*.json` | T0 | FR-05.3, FR-14.6 |
| `T-U-schema-07` | `E006_CONDITIONAL_FORBIDDEN`: the same three non-null on `arm == "seeded"`; `turn_cost.turn` non-null on the mutation arm; a timeout carrying a signal | `probe_spec/seeded_*.json` | T0 | FR-05.3, FR-06.4 |
| `T-U-schema-08` | `E007_BAD_DICT_KEYS` for each of the **eight** declared dicts of `03-LLD.md` §2.6, once with a missing key and once with an extra one; an extra key fails as loudly as a missing one. `RunManifest.model_ids` and `RunManifest.stages_metered` are the two added by this revision, and `stages_metered`'s key set is asserted to be exactly `_STAGE_IDS` | `malformed/dicts/` | T0 | FR-03.10, FR-08.3, FR-14.6, FR-14.8 |
| `T-U-schema-09` | `E008_CAP_EXCEEDED` from `bound_text` when the text is over the cap and `path` is `None` | none | T0 | FR-17.7 |
| `T-U-schema-10` | `E009_UNKNOWN_SCHEMA` from `from_json` and from `validate` for a class outside `_MEMBERS` | none | T0 | FR-04.3 |
| `T-U-schema-11` | **Serialiser determinism.** Two equal objects produce byte-identical `to_json`: keys sorted, two-space indent, `ensure_ascii=False`, one trailing newline, UTF-8, no BOM. Asserted over one instance of each of the seven members and over a 1,000-shuffle permutation of every dict field | `roundtrip/` | T0 | FR-01.6, NFR-02 |
| `T-U-schema-12` | `to_json` then `from_json` round-trips every member; `FeedbackEntry`, `RunCommit` and `LedgerSnapshot` are rebuilt as dataclasses in `__post_init__`, not left as dicts | `roundtrip/` | T0 | FR-04.3, FR-16.1 |
| `T-U-schema-13` | **The version check.** `check_version` accepts an equal MAJOR with any MINOR (`2.0` against `2.7`), rejects any other MAJOR in either direction, and never negotiates, shims or tolerates | none | T0 | FR-04.3 |
| `T-U-schema-14` | `_probe_result_conditionals`: `oracle_class` non-null exactly when `oracle_fired`; a `timeout` carries a null signal; `reduced_text` requires `reduced_path` | `probe_result/` | T0 | FR-06.4, FR-07.8, FR-17.7 |
| `T-U-schema-15` | `_manifest_conditionals`: a discovery manifest has one `run_commit` with a null `seed_sha`, a calibration manifest one per sampled seed; `arm_order` names both arms exactly once; `local_id_range` is an ordered pair | `run_manifest/` | T0 | FR-02.7, FR-12.2, FR-18.10 |
| `T-U-schema-16` | `_feedback_conditionals` (`abandon_reason` non-null exactly when `abandoned`); `SeedRecord`'s four per-run-line lists equal in length; `BudgetFile.arm_window_seconds` positive | `feedback_bundle/`, `seed_record/` | T0 | FR-01.10, FR-14.1, FR-16.6 |
| `T-U-schema-19` | **`_check_field`'s two deliberate deviations from bare `isinstance`.** An `int` satisfies a `float` annotation, because `isinstance(5, float)` is `False` and every duration the loop computes is a whole number of seconds; a `bool` does **not** satisfy an `int` annotation, because `isinstance(True, int)` is `True` and a bool where a count belongs is a defect. Both directions asserted on a real member field | none | T0 | FR-14.4 |
| `T-U-schema-20` | **Contract 2.0's two new required fields.** `SeedRecord.diff` and `SeedRecord.test_files` are required, so `None` on either raises `E002_MISSING_FIELD` naming it, and a `from_json` payload lacking either raises `E002` listing both sorted; a `1.0` payload is rejected by `check_version` **before** any key is read, so the MINOR drop rule can never lose them | `seed_record/`, `malformed/major_older.json` | T0 | FR-01.1, FR-04.3, FR-05.1 |
| `T-U-schema-21` | **`E010_TOOL_MISMATCH` is in the closed set and `validate` never raises it.** A `ProbeSpec` whose `tool` is `firtool` against a seed whose `entry_tool` is `circt-opt` is **accepted** by `contract.validate`, because `ProbeSpec.tool` is annotated `str` and not a `Literal` and because `validate` is handed one object with no access to the `SeedRecord`; the test asserts the acceptance, which is why `T-U-gen-03` puts the check in the emitter | `probe_spec/` | T0 | FR-04.2 |
| `T-U-schema-22` | **`CounterBlock` is not a member.** It is absent from `_MEMBERS`, so `validate` raises `E009_UNKNOWN_SCHEMA` on one and `from_json` refuses the class; `dataclasses.asdict` still serialises it for the driver's log; and its addition moved neither MAJOR nor MINOR, asserted by `CONTRACT_VERSION == "2.0"` beside the committed fixture set | none | T0 | FR-17.4 |
| `T-U-schema-23` | **FR-04.3's disjunction, as amended.** `_probe_spec_conditionals` accepts a spec with `input_text` `None` and `input_path` populated, accepts one with both, and raises `E002_MISSING_FIELD` naming FR-04.3 when `input_path` is empty and `input_text` is `None` | `probe_spec/` | T0 | FR-04.3, FR-17.7 |
| `T-U-schema-17` | `bound_text` returns the text at or under the cap and `None` above it with a path present; the companion path field is populated in both cases | none | T0 | FR-17.7 |
| `T-U-schema-18` | A stderr capture holding invalid UTF-8 decoded with `errors="backslashreplace"` survives `to_json` and round-trips byte for byte; `errors="replace"` is used nowhere, asserted by a source search | `probe_result/nonutf8.json` | T0 | FR-06.4, FR-07.3 |

### 1.2 `contract/fixtures/`, 3 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-fixt-01` | Every committed file under `contract/fixtures/` passes `validate` at the version it records. This is where `02-HLD.md` §2.2's compatibility rule fires: a MAJOR bump fails this test until the set is re-recorded | all | T0 | FR-04.3 |
| `T-U-fixt-02` | Each half's fixture set covers **all seven** members; a missing member fails, naming it | all | T0 | FR-16.1 |
| `T-U-fixt-03` | A fixture whose MAJOR differs from `CONTRACT_VERSION` fails rather than being silently re-recorded: injected by writing a `3.0` copy into a temporary directory and running the same walk over it | `malformed/major_newer.json` | T0 | FR-04.3 |

### 1.3 Repository-wide static checks, 7 tests

`tests/test_layout.py`. These are the four properties `03-LLD.md` §14.7 calls "properties of the
design as a whole", plus the layout rule and the placement table.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-layout-01` | The four sets of `03-LLD.md` §1.3, both directions: eighteen source modules each with a test module, one source module (`contract/__init__.py`) with none, two structural test modules with no source, and five artefact test modules exempt **by name**. The exemption list in the code is compared for **equality** against the five the LLD names, so neither document can grow one the other does not; twenty-five test modules live under `tests/` | none | T0 | FR-19.5 |
| `T-U-layout-02` | The `ast` walk of `03-LLD.md` §14.5 over `probe_task.py`, `triage_task.py`, `repair_adapter.py`, `gate.py`, `store.py` and `ddmin.py` finds no `Compare`, `If`, `Match` or `Subscript` whose operand resolves to a name or attribute ending `arm`. The exempt list is **three** names and the test asserts that: `ledger.py` and `results.py`, which FR-18.1 permits, and `contract/schema.py`, because `_probe_spec_conditionals` opens with `mutation = o.arm == "mutation"` and must, FR-16.2 and FR-05.4 making three `ProbeSpec` fields conditional on the arm; the seam is neither half | none | T0 | FR-18.1 |
| `T-U-layout-03` | Every public callable in `examples/circt_bug_loop/` and the three added to `chia/chipyard/circt.py` carries a docstring with the three named paragraphs **Returns**, **Worker**, **Raises**, in that order; a `ChiaTool` method additionally states one action, one argument and one failure | none | T0 | FR-19.4, NFR-12 |
| `T-U-layout-04` | No bare `ray.remote` in the added code; every added tool is a `ChiaTool` or `AsyncJobTool` subclass, and no added tool falls in FR-19.1's five long-work categories, so the `AsyncJobTool` rule holds vacuously and the check still runs | none | T0 | FR-19.1 |
| `T-U-layout-05` | Every import in `examples/circt_bug_loop/` is in `03-LLD.md` §0's list: the standard-library set, `yaml`, `ray`, and `chia`. No added dependency | none | T0 | FR-19.8, NFR-11 |
| `T-U-layout-06` | Every node's `_chia_options` equals `03-LLD.md` §3.2's row: the three placements and no fourth, `max_retries=0` everywhere, `{"repair": 1}` held by `repair_adapt` alone, `gate_decide` declaring no worker resource, and **A1, A1', A2 and B6b declaring none either**, which is the head move this revision made; `SourceReadTool`'s `task_options` carries the head's node id and `ProbeWriteTool`'s carries the constructing worker's | none | T0 | FR-12.11, FR-13.2, FR-19.1 |
| `T-U-layout-07` | **Every node returns a `CounterBlock`.** For every row of `03-LLD.md` §3.2 that is a node, the documented **Returns** paragraph names the key `counters`, and a call through the §0.4 plain-call path returns a dict carrying one; `CounterBlock.stage` is drawn from `_COUNTER_STAGES` and from nothing else | none | T0 | FR-17.4, FR-19.4 |

### 1.4 `corpus.py` (A1, A1'), 24 tests

The RUN-line normaliser is tested against the shape features M1 measured over 331 logical lines, which
is `01-FRD.md` §10.3's requirement that the normaliser meet the M1 shapes.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-corpus-01` | **Reproduces 187/171 at the recorded HEAD.** Mining the clone reset to `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` with `--since 2024-09-11` emits exactly 187 records, exactly 171 with a non-null tag | `corpus/clone` | T1 | FR-01.1 |
| `T-U-corpus-02` | The emitted SHA set equals the filtered candidate set derived from `analysis/pin_window_raw.json` by PIN §2's rule, compared as sets | `corpus/pin_window_raw.json` | T0 | FR-01.1 |
| `T-U-corpus-03` | The `SdkMap` has exactly 38 groups, median group size 3, maximum 27 | `corpus/pin_window_raw.json` | T0 | FR-01.5 |
| `T-U-corpus-04` | Exactly 16 seeds carry `sdk_exact=false`, every one with `bumps_away == 1` and none greater | `corpus/pin_window_raw.json` | T0 | FR-01.7 |
| `T-U-corpus-05` | Both bucketings of FR-01.4 reproduce their tables exactly: the dialect-level one (FIRRTL 42, ImportVerilog 31, MooreToCore 12, LLHD 12, Synth 9, Comb 8, Moore 5, ExportVerilog 5, CoreToFSM 5, ESI 5, OM 4, HWToBTOR2 4, RTG 4, HW 3, Arc 3, tail) and the unmerged one, including the 16-way split of `include/circt/Dialect` | `corpus/pin_window_raw.json` | T0 | FR-01.4 |
| `T-U-corpus-06` | Seed `f2b15a44ec70`'s extracted line is `circt-opt %s --split-input-file --convert-hw-to-llvm=spill-arrays-early=false | FileCheck %s` verbatim, and the classified tool is `circt-opt`, taken from the line and never inferred from a source path | `corpus/runlines/` | T0 | FR-01.2, FR-01.3 |
| `T-U-corpus-07` | **Leading `not`.** A `not`-wrapped line drops the wrapper and records `polarity=expect_nonzero`; an unwrapped line records `expect_zero`; `not --crash` also drops `--crash` and sets `notes["not_crash"]`. The corpus holds 2 such lines on 1 seed (M1), and both are in the fixture | `corpus/runlines/not_*.txt` | T0 | FR-01.10 |
| `T-U-corpus-08` | An `env` wrapper is dropped and every `NAME=VALUE` it carried is recorded in `env` | `corpus/runlines/env.txt` | T0 | FR-01.10 |
| `T-U-corpus-09` | **`split-file`.** The wrapper is dropped and `shape=split_file` recorded. The corpus holds exactly 1 such line (M1) and it is the fixture | `corpus/runlines/splitfile.txt` | T0 | FR-01.10 |
| `T-U-corpus-10` | **Pipes.** Everything from the first **unquoted** `|` is dropped and the tail recorded verbatim; a `|` inside a single- or double-quoted `FileCheck` pattern does **not** truncate. 234 of 331 lines carry a pipe (M1), so the quoted case is not hypothetical | `corpus/runlines/pipe_*.txt` | T0 | FR-01.10 |
| `T-U-corpus-11` | **`%s %t %S`.** `%s` resolves to the probe's input path and may appear more than once; `%t` to `<probe dir>/t`; `%S` to the probe directory. 52 lines use `%t` and 10 use `%S` (M1) | `corpus/runlines/subst_*.txt` | T0 | FR-01.10 |
| `T-U-corpus-12` | A line still carrying `;`, `&&`, a backtick, `$(` or `%{` after step 5 is `shape=unsupported` and its seed is excluded from both arms and counted. `%{` never occurs in the corpus (M1: 0 lines), so the fixture is constructed; `&&` occurs on 5 lines and those are real | `corpus/runlines/unsupported_*.txt` | T0 | FR-01.10 |
| `T-U-corpus-13` | Step 0 joins lit's `\` continuations into one logical line and records how many physical lines were joined; 331 logical lines come from a larger physical count (M1) | `corpus/runlines/cont.txt` | T0 | FR-01.10 |
| `T-U-corpus-14` | `strip_probe_only_options` removes `--split-input-file`, `--split-input-file=<x>`, `--verify-diagnostics` and `--verify-diagnostics=<v>`, and records the strip in `expected_outcome`. Measured reach: 29.9% and 28.3% of seeds (M1) | `corpus/runlines/` | T0 | FR-01.10 |
| `T-U-corpus-15` | `CorpusError("no_tags")` on an empty `for-each-ref` result, naming `refs/tags/firtool-*` and the quoting note; and the refspec is passed as one argument-list element, so no shell can eat it, asserted on the argv | `corpus/clone_notags` | T1 | FR-01.8 |
| `T-U-corpus-16` | `CorpusError("head_moved")` when the clone's HEAD differs from `corpus_head_sha`, naming both SHAs, and no corpus is emitted | `corpus/clone` | T1 | FR-01.11 |
| `T-U-corpus-17` | A seed whose changed tests hold no `RUN:` line is emitted with an empty `run_lines`, excluded from the seeded draw, and counted; the eligible set equals 187 minus that count | `corpus/pin_window_raw.json` | T0 | FR-01.9 |
| `T-U-corpus-18` | `test_paths` is ordered as `git` reports it and never collapsed; the recorded distribution is 162 seeds with one test file, 18 with two, 5 with three, 1 with six and 1 with nine | `corpus/pin_window_raw.json` | T0 | FR-01.12 |
| `T-U-corpus-19` | Two runs on the same clone produce byte-identical output, and the output records the clone HEAD SHA, the `--since` value and the `git` version | `corpus/clone` | T1 | FR-01.6 |
| `T-U-corpus-20` | The polarity, shape and exclusion counts are printed, and each equals the M1 row for that feature | `corpus/pin_window_raw.json` | T0 | FR-01.10 |
| `T-U-corpus-21` | **`SeedRecord.diff`, contract 2.0's first new field.** It is the output of `git -C <clone> show --format= --unified=3 --no-renames <seed_sha> -- <source_paths>`, verbatim, with the argument vector asserted on the recorded argv; the seed's **test** half is absent from it, because `test_files` already carries that text and sending it twice would double the prompt | `corpus/clone` | T1 | FR-01.1, FR-01.2 |
| `T-U-corpus-22` | **`SeedRecord.test_files`, the second.** It maps every `test_paths` entry to that file's full text at the seed commit, keyed and ordered by `test_paths`; the blobs are read by **one** batched `git -C <clone> cat-file --batch` fed `<sha>:<path>` on stdin, asserted by counting subprocess launches, and not by one `git show` per file | `corpus/clone` | T1 | FR-01.12, FR-05.1, FR-16.5 |
| `T-U-corpus-23` | **The over-cap exclusion.** A seed whose `diff`, or whose `test_files` values in total, exceed `artefact_inline_cap_bytes` (262,144) is marked ineligible for **both** arms with `exclusion_reason="seed_text_over_cap"` and counted in `counts`; neither field is truncated and neither goes through `bound_text`, which returns `None` and would make a required field null | `corpus/clone` | T1 | FR-01.9, FR-17.7 |
| `T-U-corpus-24` | **`resolve_sites`, A1's fourth callable.** Its two commands are `git -C <clone> ls-tree -- <run_commit>:<dir> <basename>` and `git -C <clone> grep -n -F -- <symbol> <run_commit> -- <file>`, both argument vectors with no shell; a site whose file and symbol both resolve stands, one whose symbol does not is rejected with `no_symbol`, one whose file does not with `no_such_file`, and a git failure rejects every site of that call rather than accepting it. It raises nothing | `corpus/clone` | T1 | FR-04.1 |

### 1.5 `pin_select.py` (A2), 8 tests

Driven offline from `analysis/pin_window_raw.json`, whose `tags` list holds 164 `(tag, date, llvm)`
triples and whose `windows` list holds 63 pin windows, so the selector's whole input is available
without a network.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-pin-01` | The first-parent walk returns the newest commit whose pin equals a published release's pin, compared as full 40-character SHAs; "newest" is first-parent position, not commit date | `pin/pin_window_raw.json` | T0 | FR-02.1 |
| `T-U-pin-02` | `lag_commits` equals `git rev-list --first-parent --count <chosen>..<head>` on the clone | `corpus/clone` | T1 | FR-02.2 |
| `T-U-pin-03` | `lag_days` is the difference of the two commit dates | `pin/pin_window_raw.json` | T0 | FR-02.2 |
| `T-U-pin-04` | A one-bump-off pair returns "no match", never a match: no tolerance, no nearest match, no version-string comparison | `pin/one_bump_off.json` | T0 | FR-02.3 |
| `T-U-pin-05` | `PinSelectError("no_match")` on an empty tag list, naming the last window examined, and the search is never widened | `pin/no_tags.json` | T0 | FR-02.5 |
| `T-U-pin-06` | Where several releases share the chosen pin, the newest by tag date is chosen and every one is recorded in `tags_sharing_pin`. The fixture is a real multi-tag pin: PIN §3 records 11 windows with 2 tags, 8 with 3 and one with 7 | `pin/multi_tag.json` | T0 | FR-02.6 |
| `T-U-pin-07` | `current_window_has_release` is a boolean and is set on every run, including the run where it is false | `pin/pin_window_raw.json` | T0 | FR-02.4 |
| `T-U-pin-08` | At clone head `b792c772` the selector refuses head, whose pin `e297b52ec9d8` has no release, and returns an older commit with a non-zero lag | `corpus/clone` | T1 | FR-02.1, FR-02.4 |

### 1.6 `generate_task.py` (A3, A4, `ProbeWriteTool`, `SourceReadTool`), 20 tests

No model runs in any of these. The seeded arm's two turns are driven by a recorded transcript replayed
through a `_turn` substitute, which is what `02-HLD.md` §2.13 and NFR-01 mean by replaying an agent
turn; the emitter, the cap and the validator are the code under test.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-gen-01` | **The tool list, after `BashTool`'s withdrawal.** The list handed to stage 1 and to stage 2 is literally `[source_read, probe_write]` and stage 6's is literally `[source_read]`; the identifier `BashTool` appears nowhere in `generate_task.py` or `triage_task.py`, asserted by a source search, and no build, lit, oracle, reducer or dedup tool appears in any of the three lists. The withdrawal is what makes FR-04.4's second clause, "shall not be able to **reach** any tool that computes a measured result", true by construction: `BashTool` had no read-only mode and its `PATH` on a `circt` worker put `/workspace/circt/build/bin` first | none | T0 | FR-04.4, NFR-03 |
| `T-U-gen-02` | **The cap.** With `per_seed_probe_cap` 3 and a transcript declaring 10 specs, exactly the first 3 in the agent's emission order are emitted, and the truncation plus the discarded count of 7 are recorded | `turns/probe_write_10.jsonl` | T0 | FR-04.5 |
| `T-U-gen-03` | A spec naming a tool other than the seed's `entry_tool` is rejected by **`emit_specs`** with `E010_TOOL_MISMATCH`, naming both tools, and counted under the rejection reason `tool_mismatch`; the same spec passed to `contract.validate` alone is **accepted**, which is the measured fact that moved the check out of the validator (`T-U-schema-21` is the other half) | `turns/probe_write_wrongtool.jsonl` | T0 | FR-04.2 |
| `T-U-gen-04` | Every emitted spec passes `contract.validate` before it leaves the node, with every field populated | `turns/probe_write_ok.jsonl` | T0 | FR-04.3 |
| `T-U-gen-05` | Sibling sites are resolved by **dispatching `corpus.resolve_sites`**, a head node, and not by running git inside A3, which sits on a `circt` worker with no clone: a `file:symbol` that resolves stands, one that does not is counted in `rejected_sites` with its reason, and the remaining sites survive. Asserted on the dispatch as well as on the outcome | `turns/seed_read_ok.jsonl`, `corpus/clone` | T1 | FR-04.1 |
| `T-U-gen-06` | A turn that times out, errors, or returns nothing records `failure` with its cause, charges the ledger for what was spent, and the iteration ends for that seed while the run continues | `turns/backend_error.jsonl` | T0 | FR-04.8 |
| `T-U-gen-07` | A stage-2 turn whose JSON footer will not parse yields **zero** `ProbeSpec`s even when files were written, and records `failure="prompt_contract:<reason>"` | `turns/probe_write_badfooter.jsonl` | T0 | FR-04.8 |
| `T-U-gen-08` | All five per-turn files are written for both stage 1 and stage 2: prompt, streamed transcript, raw session transcript, stderr, usage | `turns/` | T0 | FR-04.6 |
| `T-U-gen-09` | `generate_mutation`'s **body** does not read `feedback`: `inspect.getsource` shows the identifier exactly once, in the parameter list | none | T0 | FR-16.2 |
| `T-U-gen-10` | One `ProbeSpec` from each arm, identical in every other field, passes through the same validator and the same code path with identical handling | `probe_spec/` | T0 | FR-05.4, FR-18.1 |
| `T-U-gen-11` | `ProbeWriteTool.write_probe` refuses a name containing a path separator, `""`, `.`, `..`, and a name whose `realpath` escapes the bound probe directory through a symlink; each returns an `Error:` string and writes nothing | none | T0 | FR-06.8 |
| `T-U-gen-12` | Writing the same name twice overwrites with identical bytes; a rejected write is returned to the agent as a result string and never raised | none | T0 | FR-06.8 |
| `T-U-gen-13` | The tool is constructed per iteration with the probe directory bound, so the agent cannot name a directory at all; the constructor calls `super().__init__`, `mcp.add_tool` and `super().__post_init__()` in CHIA's order | none | T0 | FR-19.1 |
| `T-U-gen-14` | The argv of every emitted spec is built from the seed's `argv_template`, not from anything the agent wrote, asserted by feeding a transcript whose declared argv differs from the seed's | `turns/probe_write_argv.jsonl` | T0 | FR-04.2, NFR-03 |
| `T-U-gen-15` | **`SourceReadTool.read_file`.** It returns the file's text at the run's commit through `git -C <clone> show <run_commit>:<path>`, one argument vector, no shell; a path that does not exist at that commit returns a one-line string beginning `Error:` and raises nothing. Verified against the measured pair: `lib/Dialect/HW/HWTypes.cpp` returns bytes beginning `//===- HWTypes.cpp`, and `lib/Dialect/HW/NoSuch.cpp` returns git's own `does not exist in` message | `corpus/clone` | T1 | FR-04.4 |
| `T-U-gen-16` | **`SourceReadTool.grep`.** It is a **fixed-string** search, `git -C <clone> grep -n -F -- <pattern> <run_commit> -- <path_prefix>`, so a pattern carrying a regular-expression metacharacter matches literally; it returns `<path>:<line>:<text>` lines, and `Error:` when nothing matched. Verified: `parseHWArray` under `lib/Dialect/HW` returns two hits, `zzzNoSuchSymbol` returns none | `corpus/clone` | T1 | FR-04.4 |
| `T-U-gen-17` | **`SourceReadTool.list_dir`.** `git -C <clone> ls-tree --name-only <run_commit>:<path>` returns one name per line, `''` lists the repository root, and a bad path returns `Error:` | `corpus/clone` | T1 | FR-04.4 |
| `T-U-gen-18` | **Read-only by construction, not by instruction.** All three methods are argument vectors against a **fixed commit**: no method takes a shell, a write, a path outside that commit, or a ref the caller chose, asserted on the three recorded argv; every return is truncated at `artefact_inline_cap_bytes` with the truncation stated in the returned text, so one `read_file` of a large generated file cannot fill a context window or the object store | `corpus/clone` | T1 | FR-04.4, FR-17.7, NFR-03 |
| `T-U-gen-19` | **Both tools are stopped in a `finally`.** A turn that returns normally and a turn that raises both leave zero live `_ToolServerActor`s for the iteration, asserted by counting registry entries before and after; a `stop()` that itself raises is swallowed and does not mask the turn's result, which is CHIA's own choice at the same place | none | T0 | FR-19.1 |
| `T-U-gen-20` | **Placement.** `SourceReadTool` is constructed with `task_options` carrying the **head's** node id, because the clone is the head's, and `ProbeWriteTool` with the constructing worker's, because its writes must land in the filesystem namespace the probe directory lives in; the two differ in every construction | none | T0 | FR-04.4, FR-06.8 |

### 1.7 `mutators/` (A4's frozen set), 10 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-mut-01` | The digest check at import compares `sha256` of `set_v1.json`'s bytes against `RunManifest.mutator_set_sha` and raises before any mutant is produced on a mismatch | `mutators/set_v1.json` | T0 | FR-05.2 |
| `T-U-mut-02` | **Determinism.** Re-running a `ProbeSpec`'s mutator with its recorded `mutator_seed_int` reproduces the input byte for byte, over every mutator in the set | `mutators/set_v1.json` | T0 | FR-05.3 |
| `T-U-mut-03` | A mutant byte-identical to its input is counted a no-op, consumes no input-cap budget, and the no-op count is reported | `mutators/noop_case/` | T0 | FR-05.6 |
| `T-U-mut-04` | A mutator that raises is recorded against its id, the arm does not abort, and the failure count is attributed to that id | `mutators/raising.json` | T0 | FR-05.7 |
| `T-U-mut-05` | A mutator runs only against inputs whose language matches its `language`, or `any` | `mutators/set_v1.json` | T0 | FR-05.1 |
| `T-U-mut-06` | `mutates_argv` is true only for `kind: argv`; every emitted spec either matches the seed's argv exactly or names an argument mutator | `mutators/set_v1.json` | T0 | FR-05.5 |
| `T-U-mut-07` | Exactly one mutator application per mutant; a mutant is never the composition of two | `mutators/set_v1.json` | T0 | FR-05.3 |
| `T-U-mut-08` | Every changed test file of the seed supplies a starting input, in the order FR-01.12 records, and a seed with k test files yields k starting inputs; each mutant names the file it came from. The text comes from **`seed.test_files`**, which contract 2.0 added for exactly this, so FR-05.1's "the arm's input record contains only the test files and their `RUN:` lines" has an object to point at. The fixture includes the 9-test-file seed | `seed_record/multi_test.json` | T0 | FR-05.1 |
| `T-U-mut-09` | The frozen set matches `03-LLD.md` §8.1's format field by field and type by type, including the three provenance fields | `mutators/set_v1.json` | T0 | FR-05.2, FR-05.8 |
| `T-U-mut-10` | **The mutation arm touches no filesystem and no git.** An `ast` walk over `mutators/__init__.py` and `mutate_seed` finds no `open`, no `pathlib` read, no `subprocess` and no `git`; the whole arm runs from `seed.test_files` and the frozen set, which is what made moving A1 to the head affordable | none | T0 | FR-05.1, FR-05.3 |

### 1.8 `mutator_synth.py` (A7), 9 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-msyn-01` | **Step 1's refusal.** `synthesise_mutators` runs `git -C <repo_root> log -1 --format=%H -- budget.yaml` **first**, before any model turn is dispatched, and raises `MutatorSynthError("already_registered", sha)` naming the commit when one exists; the turn count for that call is zero | `repo/preregistered/` | T0 | FR-05.2 |
| `T-U-msyn-02` | `synthesis_input`'s five fields are filled from the run, never from the model: repo, query, `issues_used`, `mirror_refreshed_utc`, and a `sha256` over the sorted issue numbers | `mirror/closed_bug.jsonl` | T0 | FR-05.2, FR-05.8 |
| `T-U-msyn-03` | The declaration written into the frozen set names the synthesis input, the synthesis date and the set's SHA, and states that feeding a model bug reports at synthesis time is Mut4All's design rather than a leak | `mutators/set_v1.json` | T0 | FR-05.8 |
| `T-U-msyn-04` | The JSON-footer parse of the synthesis turn; a malformed footer raises `PromptContractError` and freezes nothing | `turns/mutator_synth_bad.jsonl` | T0 | FR-05.2 |
| `T-U-msyn-05` | The freeze writes canonical JSON by `03-LLD.md` §2.3's rule and records `issues_used`. The mirror fixture holds 487 closed and 101 open `label:bug` issues, which is A-21's measured count (M9), so `issues_used` is 487 and ADR-D-05's fallback to the 24-month fix-commit set is not taken | `mirror/closed_bug.jsonl` | T0 | FR-05.2 |
| `T-U-msyn-06` | **Step 2's input, and no network.** The query selects `number`, `title` and `body` from `issue_mirror` where the state is `closed` and the labels carry `bug`, ordered by number; the recording transport of §8 shows **zero** requests to `api.github.com` for the whole synthesis, the mirror being the only source | `mirror/closed_bug.jsonl` | T0 | FR-05.2, NFR-04 |
| `T-U-msyn-07` | **Step 4's six checks, one drop each.** A mutator whose `pattern` will not compile, whose `id` is malformed, whose `id` repeats, whose `language` or `kind` is outside its set, whose `mutates_argv` disagrees with `kind == "argv"`, or whose `replacement` is neither a literal nor one of the seven named operations, is **dropped** with its id and the failing check recorded in `dropped`, never repaired and never kept | `turns/mutator_synth_drops.jsonl` | T0 | FR-05.2, FR-05.5 |
| `T-U-msyn-08` | **The freeze is write-once.** A second call with the same `set_version` raises `MutatorSynthError("set_exists", path)` and leaves the existing file byte-identical, so the digest `RunManifest.mutator_set_sha` names can never change under a run | `mutators/set_v1.json` | T0 | FR-05.2 |
| `T-U-msyn-09` | `MutatorSynthError("empty_mirror")` when step 2 returns no row: a set synthesised from nothing would freeze successfully and measure nothing | `mirror/empty/` | T0 | FR-05.2 |

### 1.9 `probe_task.py` (B2, B3, B4, B5), 50 tests

The largest module and the one that produces every measured verdict. Tests 01 to 15 and 40 to 43 are
B2, 16 to 26 and 39, 44 and 49 are B3, 27 to 30 and 47, 48 and 50 are B4, 31 to 38 and 45 and 46 are
B5. Tier T1 means a real CIRCT binary from the SDK or from `bassert_g`; tier T0 means
`classify_build` and the three patterns driven from recorded stderr.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-probe-01` | The hash check runs **first**: a binary whose `sha256` differs from `ImageSpec.tool_hashes` raises `BinaryMismatch(tool, expected, actual)` before anything is executed | `image_spec/ok.json` | T1 | FR-06.1, FR-03.16 |
| `T-U-probe-02` | `classify_build` returns `clean_exit` for `rc == 0` with nothing on stderr | `stderr/clean.txt` | T0 | FR-06.9 |
| `T-U-probe-03` | `parse_error` for a clean non-zero exit with a diagnostic, distinct from a crash; the primary oracle does not fire | `stderr/parse_error.txt` | T0 | FR-06.6, FR-04.9 |
| `T-U-probe-04` | `assertion` for a glibc assertion line | `stderr/assert_glibc.txt` | T0 | FR-06.9, FR-07.2 |
| `T-U-probe-05` | `fatal_error` for an `LLVM ERROR:` line with no assertion line | `stderr/llvm_error.txt` | T0 | FR-06.9, FR-07.2 |
| `T-U-probe-06` | `crash` for death by signal with neither assertion nor `LLVM ERROR:` nor allocation evidence | `stderr/segv.txt` | T0 | FR-06.9, FR-07.2 |
| `T-U-probe-07` | `timeout` when the stage itself killed the child at its wall-clock limit | none | T1 | FR-06.9 |
| `T-U-probe-08` | `oom` when `limit_hit == "address_space"` | none | T1 | FR-06.7 |
| `T-U-probe-09` | A `timeout` carries a **null** signal, so it can never be read back as a crash, and the oracle does not fire | none | T1 | FR-06.4, FR-07.8 |
| `T-U-probe-10` | **`oom` by evidence.** A probe that aborts by signal with `std::bad_alloc` on stderr is `oom`, never `crash`, and the oracle does not fire | `stderr/bad_alloc.txt` | T0 | FR-06.7, FR-07.2 |
| `T-U-probe-11` | The same for a bare `out of memory` line and for `LLVM ERROR: out of memory`, the latter classifying `oom` rather than `fatal_error` because allocation evidence is tested first | `stderr/oom_*.txt` | T0 | FR-06.7, FR-07.2 |
| `T-U-probe-12` | **The test order of `classify_build`, and the `oom` row's second conjunct.** The order is exactly: `limit_hit == "wall"`, `limit_hit == "cpu"`, then `limit_hit == "address_space"` **or** (death by signal **and** allocation evidence), then assertion line, then `LLVM ERROR:` line, then signal, then non-zero, then zero. Asserted two ways on one stderr carrying an assertion line **and** `std::bad_alloc`: with death by signal it classifies `oom`, and with a clean non-zero exit it classifies `assertion`, because FR-06.7's wording is "terminated by signal **and** its stderr carries an allocation-failure line" and an ordinary diagnostic containing the phrase is not an OOM | `stderr/both.txt` | T0 | FR-06.7, FR-07.2 |
| `T-U-probe-13` | The invocation is an argument **list** passed to `Popen` with no `shell=True` and no generated script anywhere on the measured path; asserted on the recorded `argv.json` and by a source search for `shell=True` | none | T1 | FR-06.1 |
| `T-U-probe-14` | The `prlimit` prefix is exactly `["prlimit", "--as=<bytes>", "--cpu=<soft>:<soft+CPU_HARD_MARGIN_SECONDS>", "--nofile=<n>", "--", <abs tool path>, *argv]`, long spellings only, `--rss` never passed, and the tool path is absolute and under `/workspace/circt/build/bin`. **`--cpu` carries a soft:hard pair and never a single value**, with the margin 5 from `03-LLD.md` §9.4: with soft equal to hard the kernel escalates past `SIGXCPU` straight to `SIGKILL` and `limit_hit` becomes underivable | none | T1 | FR-06.2, FR-06.1 |
| `T-U-probe-15` | stdout and stderr are captured to `stdout.txt` and `stderr.txt`, truncated at `probe_output_byte_cap` (1,000,000) with `truncated=True` recorded, and the `ProbeResult` text fields pass through `bound_text` | none | T1 | FR-06.4, FR-17.7 |
| `T-U-probe-16` | `_ASSERT_GLIBC` matches the measured line `a_assert: a.c:2: main: Assertion \`c>99 && "needs many args"' failed.` and extracts `file`, `line`, `func` and the whole `expr` including the `&& "..."` tail | `stderr/assert_glibc.txt` | T0 | FR-07.1, FR-07.3 |
| `T-U-probe-17` | **`_ASSERT_UNREACHABLE`, two-line extraction.** The pattern is anchored, has **no** `msg` group, and matches `UNREACHABLE executed` with and without the ` at <file>:<line>` tail. For this class `assertion_text` is the **preceding stderr line**, a newline, and the matched line with its trailing `!` removed; where there is no preceding line it is the matched line alone. `assertion_site` is `<file>:<line>` when the location groups matched and `None` otherwise, in which case the fingerprint falls to the frame basis. Asserted against the synthetic two-line LLVM-format sample and against both degenerate forms | `stderr/unreachable_*.txt` | T0 | FR-07.1, FR-07.3 |
| `T-U-probe-18` | `_FATAL_ERROR` matches a line beginning `LLVM ERROR: ` and captures the message after it | `stderr/llvm_error.txt` | T0 | FR-07.1 |
| `T-U-probe-19` | `fired` is true for exactly `crash`, `assertion` and `fatal_error`, and for nothing else | `stderr/` | T0 | FR-07.1 |
| `T-U-probe-20` | `assertion_text` and `assertion_site` are verbatim from stderr, character for character, and non-empty | `oracle/` | T1 | FR-07.3 |
| `T-U-probe-21` | `fatal_message` is exactly the text after `LLVM ERROR: ` | `stderr/llvm_error.txt` | T0 | FR-07.2 |
| `T-U-probe-22` | **`_FRAME` parses both measured trace shapes and records which.** The `(<module>+0x<offset>)` form yields `shape="module_offset"` with `module` and `offset` populated; the form LLVM already attributed at print time yields `shape="attributed"` with `file` and `line` populated and `module` and `offset` empty. Both occur in the one recorded 466-frame trace, so a parser handling only one loses frames, and the test asserts a non-zero count of each | `stderr/trace.txt` | T0 | FR-07.4 |
| `T-U-probe-23` | `frames_resolved` counts frames with a non-empty function name, which SDK modules do supply; `frames_with_location` counts frames that are **both** located and in a CIRCT object, that is `line > 0 and in_circt_object`, which is FR-07.4's criterion as amended. A frame resolved inside an SDK `.so` therefore raises the first count and not the second, because the SDK's prebuilt libraries carry no debug information | `oracle/` | T1 | FR-07.4 |
| `T-U-probe-24` | `out_of_scope_root` is computed **after** the crash-handler prologue strip: it is true when the first **stripped** frame is not in a CIRCT object. Asserted both ways on the recorded trace: unstripped, the first frame is `llvm::sys::PrintStackTrace` in `libLLVMSupport.so` for every crash, so every candidate would be out of scope and F-12 would never run; stripped, the field discriminates. The candidate never reaches repair when it is true | `oracle/mlir_root.json` | T0 | FR-07.5 |
| `T-U-probe-25` | `repro_command` is one `shlex.join` line naming the absolute binary path and the probe argv **without** the `prlimit` prefix, and re-running it reproduces the same exit status and assertion text | `oracle/` | T1 | FR-07.6 |
| `T-U-probe-26` | The verdict carries the literal `-UNDEBUG` and the tool's own `--version` output, which still reads "Optimized build." | `image_spec/ok.json` | T1 | FR-07.7, FR-03.11 |
| `T-U-probe-27` | Applicability is decided from the entry tool and requested output mode **before** either simulator runs: `firtool` with `--ir-hw`, `--verilog` or `--split-verilog`, and `circt-opt` whose pipeline ends in HW, are applicable; everything else is `not_applicable` with a reason | `probe_spec/` | T0 | FR-08.1 |
| `T-U-probe-28` | A harness that will not build or run is `harness_failure` with the failing arm named, never `diverge` | `differential/broken_tb/` | T2 | FR-08.8 |
| `T-U-probe-29` | A divergence confined to signals the declared `x_policy` leaves undefined is `diverge_x_policy` and is excluded from the candidate count | `differential/x_only/` | T2 | FR-08.9 |
| `T-U-probe-30` | An `ImportVerilog` or `MooreToCore` probe records `not_applicable`; both harnesses, where they run, carry the same `stimulus_id`, `reset_protocol`, `sample_point`, `cycles` and `port_list_sha`, and the recorded Verilator argv carries `--x-initial` and `--x-assign` with the policy's values. `port_list_sha` is the one key of the five the **generator** could not know: A3 and A4 emit it as the empty string and B4 writes the digest, so the test asserts the empty string on the `ProbeSpec` and a 64-character hex digest on the `DifferentialVerdict` | `differential/` | T2 | FR-08.1, FR-08.3, FR-08.4 |
| `T-U-probe-31` | **The five reducer branches**, one test each, with `ReducedCase.reducer` and `lift` recording which ran and the **interestingness argv** asserted per branch: (1) MLIR text direct, no lift, the probe's own tool and argv; (2) `.fir` lifted by `firtool --ir-fir` and retried with `--parse-only`, tested by `firtool` on MLIR input; (3) `.sv` entered through `circt-verilog`, lifted by `--ir-moore`, tested by `circt-verilog --format=mlir <candidate>` plus the seed's own output-mode flag; (4) `.sv` entered through `circt-translate --import-verilog`, lifted the same way, tested by `circt-opt <candidate> -o /dev/null`, because `circt-translate` has no `--format=` option at all; (5) everything else textual. The third branch had no statable pass criterion before this revision and now has one | `reducer/branch_*/` | T1 | FR-09.9 |
| `T-U-probe-32` | The `circt-reduce` argv is `[<abs>, <input>, "--test=<script>", "--keep-best", "-o", <out>]`; `--test-must-fail` is never passed, and no `--test-arg` is passed, so the candidate is the script's `$1` | none | T1 | FR-09.2 |
| `T-U-probe-33` | The re-check re-runs the primary oracle on the reduced input and records class, assertion text and `file:line`; equality sets `recheck_matches`, a mismatch sets `reduction_changed_failure` and carries the original input forward | `reducer/` | T1 | FR-09.3, FR-09.7 |
| `T-U-probe-34` | An already-minimal input yields `reduced=false` with the reason recorded, and the candidate still proceeds to stage 6 | `reducer/minimal/` | T1 | FR-09.12 |
| `T-U-probe-35` | **`reducer_aborted` routes to the textual reducer.** A `circt-reduce` that aborts or dies on the candidate, which is measured on a parser-overflow input where the reducer parses the candidate with the same parser the candidate overflows, records `reducer_aborted`, keeps the last valid `--keep-best` output, and then **runs `textual-ddmin` on the same run, before the budget is spent**: the resulting `ReducedCase` carries `reducer="textual-ddmin"`, `lift=null` and a `reason` naming the abort. The earlier rule stopped at `reduced=false` and left a whole class of input unreducible | `reducer/reducer_abort/` | T1 | FR-09.9, FR-09.12 |
| `T-U-probe-36` | The `-o` output is validated **after** the reducer process exits and never while it is running: non-empty, parses under `circt-opt <out> -o /dev/null`, and still satisfies the interestingness script. A file truncated by a kill is discarded and the previous good output kept | `reducer/truncated/` | T1 | FR-09.13 |
| `T-U-probe-37` | No write lands in `/workspace/circt` outside the per-probe scratch directory: `git status` in the tree is clean after a batch of 20 probes | none | T2 | FR-06.8 |
| `T-U-probe-38` | Both size pairs are recorded and the after-values are less than or equal to the before-values; `fixpoint` and `budget_truncated` are present on every `ReducedCase`, a budget-truncated reduction carrying `fixpoint=false` | `reducer/` | T1 | FR-09.5, FR-09.11, NFR-02 |

### 1.10 `ddmin.py` (B5's textual reducer), 8 tests

Wholly tier 0, which is the reason `03-LLD.md` §1.1 gives for it being a file of its own.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-ddmin-01` | **Minimality on the specified fixture.** On a 200-line input `[DEFAULT]` whose interestingness depends on 3 lines `[DEFAULT]`, `ddmin` returns exactly those three lines, in input order | `ddmin/200_3/` | T0 | FR-09.10 |
| `T-U-ddmin-02` | **Termination.** On an adversarial interestingness function that is true only for the full list, the loop exits by the `n >= len(lines)` break rather than looping; asserted by a call ceiling of `len(lines) ** 2` and by the loop-variant pair `(len(lines), len(lines) - n)` decreasing lexicographically at every pass, checked by instrumenting the loop | `ddmin/adversarial/` | T0 | FR-09.10 |
| `T-U-ddmin-03` | `ValueError` when the input is not interesting to begin with, which is a defect in the caller and not a reduction outcome | none | T0 | FR-09.10 |
| `T-U-ddmin-04` | The number of interestingness calls is returned and recorded as `interestingness_calls` | `ddmin/200_3/` | T0 | FR-09.10 |
| `T-U-ddmin-05` | **Budget truncation.** With `max_calls` set below the natural call count, the function returns early, the caller records `fixpoint=False` and `budget_truncated=True`, and the returned lines are still interesting | `ddmin/200_3/` | T0 | FR-09.10, NFR-02 |
| `T-U-ddmin-06` | On exit without truncation the result is 1-minimal: removing any single line makes it uninteresting, checked exhaustively | `ddmin/200_3/` | T0 | FR-09.10 |
| `T-U-ddmin-07` | Degenerate inputs: an empty list, a one-line list, and a list where every line is load-bearing, each terminate and return correctly | none | T0 | FR-09.10 |
| `T-U-ddmin-08` | The module imports nothing outside the standard library and knows nothing about CIRCT, asserted by an import walk; this is what makes the module tier 0 | none | T0 | FR-09.10, FR-19.8 |

### 1.11 `triage_task.py` (B6a, B6b, B7), 24 tests

Tests 01 to 09 are the fingerprint and the partition, 10 to 20 the mirror and the two screens, 21 to
24 the triage turn and the render.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-triage-01` | The assertion fingerprint is `f"{expr}\n{site}"` with runs of whitespace in `expr` collapsed to one space and the ends stripped; the `&& "message"` tail is **kept**, and two asserts differing only in that tail fingerprint differently | `fingerprint/assertion/` | T0 | FR-10.1 |
| `T-U-triage-02` | The site normalisation removes the `/workspace/circt/` prefix, keeps only the last two components of any other absolute path, and keeps the line number verbatim; two images built in different directories produce the same fingerprint | `fingerprint/assertion/` | T0 | FR-10.1, FR-10.6 |
| `T-U-triage-03` | The crash fingerprint is the ordered top-`fingerprint_top_n` (5) normalised frame **function names**, joined by newlines, skipping frames whose function is empty | `fingerprint/crash/` | T0 | FR-10.1 |
| `T-U-triage-04` | Frame-name normalisation performs the four steps and only those: take `FunctionName`, cut from the first `(` at bracket depth zero, strip a trailing ` const`, collapse whitespace. `circt::chooseName(llvm::StringRef, llvm::StringRef)` becomes `circt::chooseName` | `fingerprint/crash/` | T0 | FR-10.1 |
| `T-U-triage-05` | A candidate with no assertion text and fewer than 5 resolvable frames carries `basis=insufficient` and `value=None`, deduplicates against nothing, and fails gate question 4 with that reason; its structural hash is still recorded | `fingerprint/insufficient/` | T0 | FR-10.8 |
| `T-U-triage-06` | The structural hash normalises every SSA value name, every `loc(...)` suffix and every whitespace run before hashing; it is present on every candidate and is **never** the fingerprint, asserted by a source check that no merge path reads it | `fingerprint/structural/` | T0 | FR-10.1, FR-10.2 |
| `T-U-triage-07` | **The equivalence-relation property.** Over the labelled pair set of §10, the duplicate relation is reflexive, symmetric and transitive, checked exhaustively over all ordered triples | `dedup/pairs/` | T0 | FR-10.2 |
| `T-U-triage-08` | **Order independence.** The partition produced from 100 random shuffles of the candidate list is identical every time, compared as a set of frozensets | `dedup/pairs/` | T0 | FR-10.2 |
| `T-U-triage-09` | **The measured rates.** The collision rate and the false-merge rate over the labelled pairs are computed and printed; the test asserts that both are reported, not that either meets a threshold | `dedup/pairs/` | T0 | FR-10.2 |
| `T-U-triage-10` | The one mirror call is `GithubIssuesNode(repo, token=..., state="all").recent(n=issue_cap, fetch_comments=False)`; `fetch_comments=True` never appears, asserted on the recorded call | `mirror/` | T0 | FR-10.9 |
| `T-U-triage-11` | The mirror stores number, title, body, labels and state, and **no comments at all**; a recorded response carrying comments leaves none in `loop.db` | `mirror/with_comments.jsonl` | T0 | FR-10.9, FR-20.4 |
| `T-U-triage-12` | All six values of `RunManifest.issue_mirror` are recorded: `refreshed_utc`, `issues_mirrored`, `issue_cap`, `cap_bound`, `state`, `comments_mirrored`, the last always `false` | `mirror/` | T0 | FR-10.9 |
| `T-U-triage-13` | A `GithubRateLimitError` marks the mirror incomplete with the count reached; screening proceeds against the partial mirror and the flag reaches the manifest | `mirror/ratelimit/` | T0 | FR-10.7, FR-10.9 |
| `T-U-triage-14` | A 403 during screening yields `dedup_unavailable` for that candidate, and an empty mirror yields it for every candidate; both fail gate question 4 rather than passing it | `mirror/empty/` | T0 | FR-10.7 |
| `T-U-triage-15` | **Screening makes no GitHub request.** The recording transport of §8 shows zero requests to `api.github.com` for a whole screening pass over 50 candidates; the mirror is the only source | `mirror/`, `dedup/pairs/` | T0 | FR-10.3, NFR-04 |
| `T-U-triage-16` | A candidate seeded from a known closed CIRCT issue is reported `known_closed_issue` with that issue's number and state, and one seeded from an open one `known_open_issue` | `dedup/known_issue/` | T0 | FR-10.3 |
| `T-U-triage-17` | Every verdict other than `new` carries a populated evidence field, and `dedup_evidence` holds exactly the seven keys of `02-HLD.md` §2.11: number, URL, state and labels, and **no issue text** | `dedup/` | T0 | FR-10.5, FR-20.4 |
| `T-U-triage-18` | **The post-pin scan.** File level, lower bound the run's commit, upper bound clone head: a candidate reproducing a bug fixed inside the lag is `fixed_post_pin` with the fixing SHA | `contamination/clone` | T1 | FR-10.4 |
| `T-U-triage-19` | **The contamination scan.** Symbol level, lower bound the seed's `committed_date_utc`: the symbol is read from git's `@@ ... @@` hunk-header context, never from the crude `\b(\w+)\s*\(` rule. Over the corpus the two rules give 77.0% and 79.1% (M4), and the test asserts the ctx rule is the one that sets `contaminated_symbol` | `contamination/clone` | T1 | FR-15.1 |
| `T-U-triage-20` | Both flags are recorded, the symbol-level one is what the results artefact reports, and `contamination_lower_bound` records the run's commit for the 16 non-exact seeds so all 187 are screenable | `contamination/` | T1 | FR-15.1, FR-15.2, FR-15.5 |
| `T-U-triage-21` | A candidate whose dedup verdict is `known_open_issue`, `known_closed_issue` or `fixed_post_pin` is classified `known_issue` whatever the agent wrote; the agent's only freedom is the reason text | `turns/report_write_disagree.jsonl` | T0 | FR-11.2 |
| `T-U-triage-22` | The classification reason is capped at 4 sentences `[DEFAULT]`, counted by splitting on `.`, `!` and `?` followed by whitespace or end of string, and is **truncated with the truncation recorded**, not rejected | `turns/report_write_long.jsonl` | T0 | FR-11.1 |
| `T-U-triage-23` | **The renderer.** Every one of `03-LLD.md` §7.4.1's thirteen substitution points is present in the rendered `report.md` and equals the record field by field; a missing point fails the render. Every number in the output equals the record's, asserted by extracting each numeric substitution and comparing | `report/` | T0 | FR-11.3, FR-11.4, FR-03.11 |
| `T-U-triage-24` | Template selection by candidate class: a `differential` candidate renders with the second template, which contains neither the word "expected" nor any sentence naming a correct arm, names `circt/arc-tests`, and reaches the artefact store with no `FilingRecord`. A `fatal_error` candidate's report quotes the `LLVM ERROR:` message and contains neither "crash" nor "assertion". The `Assisted-by:` trailer is the last line and names `RunManifest.model_ids["triage_report"]` | `report/` | T0 | FR-07.10, FR-08.6, FR-08.7, FR-11.5, FR-11.6, FR-11.9 |

No further `triage` identifiers are allocated. The JSON-footer parser and the five per-turn files are
shared with A3 and A7 and are tested once, in §1.23.

### 1.12 `repair_adapter.py` (B8), 15 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-repair-01` | The local identifier is `LOCAL_ID_BASE + rowid`, inside `[900000000, 999999999]`, unique, monotonic, and disjoint from every key in the existing `issues.db`, asserted against a real `issues.db` | `repair/issues.db` | T0 | FR-12.2 |
| `T-U-repair-02` | `_as_github_issue` populates all eleven required fields of `chia:chia/github/state_def.py:11-24`; `url` is a `local://` URI and never an `https://github.com/` one | `report/` | T0 | FR-12.2 |
| `T-U-repair-03` | **Repro polarity, crashing binary.** The generated `repro.sh` exits **non-zero** against a committed fixture binary that still crashes on the reduced case | `repro_polarity/crashing/` | T1 | FR-12.3 |
| `T-U-repair-04` | **Repro polarity, diagnosing binary.** The same script exits **0** against a committed fixture binary patched to emit an ordinary diagnostic and exit non-zero, which is the case the naive script gets wrong | `repro_polarity/diagnosing/` | T1 | FR-12.3 |
| `T-U-repair-05` | `RepairRefused` for `oracle_class` of `differential` and of `fatal_error`, with the reason recorded, before the chain is invoked at all | `candidate/` | T0 | FR-08.10, FR-12.4 |
| `T-U-repair-06` | `RepairRefused` for `out_of_scope_root`, before the chain is invoked | `candidate/mlir_root.json` | T0 | FR-12.5 |
| `T-U-repair-07` | `examples/circt_issue_solver/issue_task.py` is byte-identical to CHIA at `16c35e92`, compared by `sha256` of the file | `repair/chia_baseline.json` | T0 | FR-12.1 |
| `T-U-repair-08` | All six of `prompts/{system,assess,reproduce,fix,regression,writeup}.md` are byte-identical to CHIA at `16c35e92` | `repair/chia_baseline.json` | T0 | FR-12.9 |
| `T-U-repair-09` | The chain's `cfg["tag"]` is `manifest.run_commit[0].commit` and `circt_git_reset` is called with it, never with `firtool-1.148.0` or `HEAD` | `run_manifest/` | T0 | FR-12.6 |
| `T-U-repair-10` | All six of CHIA's statuses round-trip into `RepairResult` and into the store, with the failing phase named | `repair/verdicts/` | T0 | FR-12.7 |
| `T-U-repair-11` | `lit_ok=false` with the failing test names yields a report with **no patch**, and the gate returns `report` rather than `report_plus_patch` | `repair/lit_red/` | T0 | FR-12.8, FR-13.6 |
| `T-U-repair-12` | A lit run reporting `passed == 0 and failed == 0` on a non-empty path list records `lit_unusable`, **not** `lit_ok=false`, names FR-03.17, and stops the run | `repair/lit_zero/` | T0 | FR-12.8 |
| `T-U-repair-13` | After every attempt, whatever the outcome, `circt_git_reset` at the run's commit and `circt_ninja_build` of the `ImageSpec` targets both run and both results are recorded; a failed restore records `repair_worker_dirty` and disables B8 for the rest of the run | `image_spec/ok.json` | T2 | FR-12.11 |
| `T-U-repair-14` | The loop's row is written **first**, carrying the local identifier; killing the chain between the two writes leaves the loop row present and the reconciliation marks it `repair_row_missing`, with no join key dangling unmarked | `repair/issues.db` | T0 | FR-12.10 |
| `T-U-repair-15` | `PHASE_TIMEOUTS` is CHIA's own dict verbatim, and the chain is invoked with it unaltered | none | T0 | FR-12.1 |

### 1.13 `gate.py` (B9a, B9b), 22 tests

`01-FRD.md` §10.3 items 16 and 17 both land here, plus the four questions and the default-refuse rule.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-gate-01` | The four questions are asked in order and the gate stops at the first "no"; each answer and the stopping point are recorded for every candidate | `candidate/` | T0 | FR-13.1 |
| `T-U-gate-02` | `gate_decide` declares no worker resource (its `_chia_options` carries none), so it can never hold a `circt` slot while waiting for one; and it dispatches `gate_rerun` as a task of its own | none | T0 | FR-13.2 |
| `T-U-gate-03` | The re-run is dispatched with `NodeAffinitySchedulingStrategy(node_id=<other>, soft=True)`; with only one live `circt` node the re-run still happens and `same_worker=True` is recorded truthfully | none | T0 | FR-13.2 |
| `T-U-gate-04` | Worker identity (hostname plus Ray node id) and process id are recorded for **both** runs, and the count of same-worker re-runs is available for the results artefact | none | T0 | FR-13.2 |
| `T-U-gate-05` | Question 1 fails when the re-run's class, assertion text or `file:line` differs from the original's; the bucket is `unreproducible` | `gate/rerun_differs/` | T0 | FR-13.1, FR-18.6 |
| `T-U-gate-06` | Question 2 passes when a reducer ran to a **fixpoint** and the re-check preserved class, text and site | `reduced_case/fixpoint.json` | T0 | FR-13.3 |
| `T-U-gate-07` | Question 2 fails as `not_minimal` for `reduced=false`, with the reason recorded | `reduced_case/not_reduced.json` | T0 | FR-09.12, FR-13.3 |
| `T-U-gate-08` | Question 2 fails as `not_minimal` for `reduction_changed_failure` | `reduced_case/changed.json` | T0 | FR-09.7, FR-13.3 |
| `T-U-gate-09` | Question 2 fails as `not_minimal` when no reducer could run at all; no input to this question is ever null | `reduced_case/none.json` | T0 | FR-13.3 |
| `T-U-gate-10` | Question 3 passes on exit 0 of the per-language check | `gate/valid/` | T1 | FR-13.15 |
| `T-U-gate-11` | Question 3 passes with `validity_basis=checker_failed` when the check itself fires the primary oracle | `gate/checker_fires/` | T1 | FR-13.15 |
| `T-U-gate-12` | Question 3 fails as `invalid_input` on a clean non-zero exit with a diagnostic; the exit status and stderr are persisted with the `GateDecision` | `gate/invalid/` | T1 | FR-13.15 |
| `T-U-gate-13` | The three check commands are exactly `circt-opt <case> -o /dev/null`, `firtool --parse-only <case>` and `circt-verilog --import-only <case>`; no pass pipeline and no `--allow-unregistered-dialect` is ever passed, asserted on the recorded argv; and the recorded failure's stage is later than the check's | `gate/` | T1 | FR-13.15 |
| `T-U-gate-14` | Question 4 passes on `new` and fails on each of the other five dedup values, `dedup_unavailable` and `dedup_basis=insufficient` included | `dedup/verdicts/` | T0 | FR-10.7, FR-10.8, FR-13.5 |
| `T-U-gate-15` | **The triage classification changes nothing.** Holding every other field fixed and setting the classification to each of `bug`, `invalid_input`, `known_issue` and `untriaged` in turn produces identical answers and an identical `GateDecision`; and no gate question reads the field, asserted by an `ast` search | `candidate/` | T0 | FR-11.8, FR-13.4, NFR-03 |
| `T-U-gate-16` | `report_plus_patch` when a `RepairResult` has `fixed=true` **and** `lit_ok=true`; `report` otherwise, both branches exercised | `repair/verdicts/` | T0 | FR-13.6 |
| `T-U-gate-17` | **The default-refuse rule.** A candidate with any null answer receives `nothing`, whatever the other three say | `candidate/null_answer.json` | T0 | FR-13.10 |
| `T-U-gate-18` | A candidate refused at any question is persisted in full with its failing question, so the taxonomy's counts sum to the candidate count | `candidate/` | T0 | FR-13.11, FR-18.6 |
| `T-U-gate-19` | The gate's input set contains no `differential` candidate; one fed deliberately is refused before question 1 and carries no `GateDecision` | `candidate/differential.json` | T0 | FR-08.10, FR-13.14 |
| `T-U-gate-20` | **The taxonomy mapping.** Every one of the twelve stopping values of FR-18.6's table is produced by some code path and lands in exactly the stated bucket; no path produces a value absent from the table, asserted by enumerating the union of every stopping value the gate can write | `candidate/taxonomy/` | T0 | FR-18.6 |
| `T-U-gate-21` | `gate_rerun` runs in a **fresh process** with a **newly created** `tempfile.mkdtemp(dir=<artefact_root>/<run>/gate/)` directory per call, never reused, and carries no state from the original run | none | T1 | FR-13.2 |
| `T-U-gate-22` | `gate_rerun` performs the same hash-manifest check as `probe_execute` and raises `BinaryMismatch` on a difference | `image_spec/ok.json` | T1 | FR-06.1 |

### 1.14 `approve.py` (B9c), 14 tests

Driven by feeding `stdin` and capturing `stdout`; the CLI is `input()` and `print()` with no
framework (ADR-D-12), so it is wholly tier 0.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-appr-01` | **The per-day cap.** With `filings_per_day` 1 and one filing already recorded for the current UTC day, the second candidate is **held** and the refusal happens **before** anything is shown to the human | `approve/store_one_filed.db` | T0 | FR-13.8 |
| `T-U-appr-02` | The total cap `filings_total` is enforced the same way, before presentation | `approve/store_at_total.db` | T0 | FR-13.8 |
| `T-U-appr-03` | **The `good first issue` refusal.** A candidate whose `dedup_evidence.issue_labels` carries `good first issue` is refused whatever the rest of the gate said, with that label named as the reason, and no filing is possible as an issue, a comment or a fix | `approve/gfi_candidate.json` | T0 | FR-13.9, FR-20.2 |
| `T-U-appr-04` | A candidate held under FR-11.8 with `held_reason=no_report` is not presented | `approve/untriaged.json` | T0 | FR-11.8 |
| `T-U-appr-05` | A second approval of an already-approved candidate is refused, naming the first approval's timestamp | `approve/store_one_filed.db` | T0 | FR-13.13 |
| `T-U-appr-06` | **Approval does not generalise.** Two pending reports require two separate approvals; approving one leaves the other pending | `approve/two_pending.db` | T0 | FR-13.13 |
| `T-U-appr-07` | The licence confirmation is taken **with the patch on screen** whenever the decision is `report_plus_patch`; a decline downgrades the decision to `report`, does not offer the patch, and records the decline | `approve/with_patch.json` | T0 | FR-20.5, NFR-11 |
| `T-U-appr-08` | **The walk-away.** Interrupting between presentation and the typed `yes` writes nothing: the candidate stays `held` with `held_reason=awaiting_approval`, the store is byte-identical, and the next invocation presents the same report | `approve/two_pending.db` | T0 | FR-13.7 |
| `T-U-appr-09` | `show` prints all four elements in one view: the full rendered report, the four gate answers with the stopping question, the repair diff if any, and the reduced case | `approve/with_patch.json` | T0 | FR-13.12 |
| `T-U-appr-10` | **The pre-filled URL.** A report under the limit produces `https://github.com/llvm/circt/issues/new?title=...&body=...`; one whose rendered URL exceeds `PREFILL_URL_CHAR_LIMIT` (6,000) produces the fallback instruction and records `prefill_fallback_reason` and `prefill_url_length` | `report/short.md`, `report/long.md` | T0 | FR-13.17 |
| `T-U-appr-11` | **The URL paste.** `url <candidate_id> <issue_url>` records against the same report id, with `url_source="pasted"`; a host other than `github.com` and a path outside `llvm/circt/issues/` are both refused | `approve/two_pending.db` | T0 | FR-13.18 |
| `T-U-appr-12` | The `filing` row carries the approver's name, the timestamp, the decision and the licence confirmation with its own timestamp; a `report_plus_patch` without a recorded confirmation is downgraded by the code path | `approve/with_patch.json` | T0 | FR-13.7, FR-20.5 |
| `T-U-appr-13` | FR-13.16's poll matches a recorded issue body carrying the report's primary fingerprint and completes the `FilingRecord` with `url_source="poll"`, using a GET only; an empty poll after `filing_poll_window_seconds` falls back to the paste and the fallback is recorded | `mirror/filed_issue.jsonl` | T0 | FR-13.16, NFR-04 |
| `T-U-appr-14` | **Nothing files by default.** No `filing` row exists without an approval, only `approve` writes one, and a full run with no approvals produces zero filings | `approve/two_pending.db` | T0 | FR-13.7, FR-20.6 |

### 1.15 `budget.py` (A6a), 10 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-budget-01` | A file missing any key of `03-LLD.md` §9.1 is rejected, naming the key; all 23 keys are exercised one at a time | `budget/missing/` | T0 | FR-14.1 |
| `T-U-budget-02` | A file carrying any other top-level key is rejected, naming it | `budget/extra_key.yaml` | T0 | FR-14.1 |
| `T-U-budget-03` | Every key's type is checked as declared; a string where a float belongs is rejected | `budget/bad_types/` | T0 | FR-14.1 |
| `T-U-budget-04` | An **uncommitted** `budget.yaml` exits non-zero naming the offending commit | `repo/uncommitted/` | T0 | FR-14.2 |
| `T-U-budget-05` | A budget file whose commit **post-dates** the run's start exits non-zero naming both timestamps | `repo/later_commit/` | T0 | FR-14.2 |
| `T-U-budget-06` | `budget_file_sha` is the SHA `git log -1 --format=%H -- budget.yaml` returns, and that SHA reaches `RunManifest.budget_file_sha` | `repo/preregistered/` | T0 | FR-14.3 |
| `T-U-budget-07` | The mutator set's last commit must predate the budget file's; a later one is refused | `repo/mutator_after/` | T0 | FR-05.2 |
| `T-U-budget-08` | **Mid-campaign change.** Amending the file after the manifest is stamped makes the next stage refuse with that message and invalidates the campaign | `repo/preregistered/` | T0 | FR-14.7 |
| `T-U-budget-09` | `snapshot` returns a `LedgerSnapshot` with exactly `arm`, `unit`, `spent` and `cap`, and the generator can reach no other budget state; asserted by the dataclass's field list | none | T0 | FR-16.4 |
| `T-U-budget-10` | `03-LLD.md` §9.5's complete file is accepted with no key missing and no key extra; equality on the unit and on both safety caps is structural, there being no per-arm value to be unequal | `budget/complete.yaml` | T0 | FR-14.1, FR-14.5 |

### 1.16 `ledger.py` (A6b), 9 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-ledger-01` | `arm` takes exactly `seeded`, `mutation` or `shared`; a fourth value is rejected by the schema | `ledger/` | T0 | FR-14.4 |
| `T-U-ledger-02` | `scope` takes exactly `arm_window` or `stage` | `ledger/` | T0 | FR-14.4 |
| `T-U-ledger-03` | Exactly one `arm_window` entry exists per arm per run, and its `amount` is that arm's spend on the primary unit | `ledger/` | T0 | FR-14.4, FR-14.5 |
| `T-U-ledger-04` | **Per-arm sums exclude `shared`.** A ledger holding the image build, the mirror, the corpus, the pin selection and the mutator synthesis as `shared` reports them beside the two arms, never folded into one and never split between them | `ledger/shared/` | T0 | FR-14.4 |
| `T-U-ledger-05` | Per-stage occupancy may exceed the window where stages overlap, and is reported as an observation rather than treated as the budget | `ledger/overlap/` | T0 | FR-14.4 |
| `T-U-ledger-06` | **The arm window.** `stop_reason` returns the window when the elapsed wall clock reaches `arm_window_seconds`, the binding cap when a safety cap binds first, and `None` otherwise; with `generated_inputs_per_day` set to 5 the arm stops after 5 inputs and the ledger shows the stop reason | `budget/complete.yaml` | T0 | FR-14.4, FR-18.10, NFR-08 |
| `T-U-ledger-07` | `accrue` is append-only; a repeated `entry_id` is **detected** rather than absorbed | `ledger/` | T0 | FR-14.4 |
| `T-U-ledger-08` | `observed` carries `cpu_seconds`, `tokens_in`, `tokens_out` and `cost_usd`, all null on the `claude` backend, where `metered` is then false and the stage is declared unmetered in the manifest | `ledger/claude/` | T0 | FR-14.6, FR-14.8 |
| `T-U-ledger-09` | A negative `amount` is rejected | `ledger/` | T0 | FR-14.4 |

### 1.17 `feedback.py` (A5), 8 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-feed-01` | **One entry per probing input.** Every input of the previous iteration appears in the bundle exactly once, including inputs that exited cleanly, parsed badly, timed out or exhausted memory; the bundle is built from `ProbeResult`s and never from `CandidateRecord`s | `probe_result/iteration/` | T0 | FR-16.1 |
| `T-U-feed-02` | A dispatched probe with no `ProbeResult` appears with `stopping_reason=result_missing` rather than being absent, which is what keeps the set difference honest | `probe_result/iteration/` | T0 | FR-16.1 |
| `T-U-feed-03` | `abandoned=true` when every probing input of this iteration **and** of the previous one stopped at stage 3 for the same reason; `abandon_reason` names it | `feedback_bundle/abandon/` | T0 | FR-16.6 |
| `T-U-feed-04` | `abandon_reason` is non-null exactly when `abandoned`, enforced by the validator and by the builder | `feedback_bundle/` | T0 | FR-16.6 |
| `T-U-feed-05` | **The deny-list.** The bundle's schema carries no candidate count, no gate precision and no bug count; a field matching the deny-list fails the check | `feedback_bundle/` | T0 | FR-16.4 |
| `T-U-feed-06` | **No apparatus imports.** The generator half's module set imports no `OracleVerdict`, `ReducedCase` or `CandidateRecord`; asserted by an import walk over `generate_task.py`, `mutators/`, `feedback.py`, `budget.py` and `ledger.py` | none | T0 | FR-16.1 |
| `T-U-feed-07` | All three terminating conditions are exercised and `terminating_condition` is recorded: the per-seed iteration cap, the per-seed input cap, and the arm's allowance on the primary unit | `feedback_bundle/` | T0 | FR-16.3 |
| `T-U-feed-08` | Replaying iteration k from its recorded `SeedRecord` plus `FeedbackBundle` through `Template.safe_substitute` reproduces the prompt **bytes** exactly | `feedback_bundle/`, `seed_record/` | T0 | FR-16.5 |

### 1.18 `store.py` (B10a, B10b), 10 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-store-01` | `init_schema` creates every table of `03-LLD.md` §6.2 and every index of §6.3; a second call is a no-op | none | T0 | FR-17.2 |
| `T-U-store-02` | `LoopStore` is constructed with `pin_to_current_node=True` and an absolute **local** path; a network path is refused | none | T0 | FR-17.3 |
| `T-U-store-03` | An artefact larger than `artefact_inline_cap_bytes` (10 MB) is written to disk and the row holds its path; nothing over the cap is inlined into a row or a task return value | none | T0 | FR-17.7 |
| `T-U-store-04` | The `PARTIAL` marker is a zero-byte file written **before** anything else in a directory and removed as the stage's last act; a killed stage leaves it, with whatever it had written, and nothing is deleted | none | T0 | FR-17.8 |
| `T-U-store-05` | `artefact_write` refuses to remove a marker for a directory whose completion record is absent from the store, so a passing stage cannot clear another stage's marker | none | T0 | FR-17.8 |
| `T-U-store-06` | `run_manifest_id` is present on every table and on every directory, so a row traces to its image, commit, budget file and arm | none | T0 | FR-17.6 |
| `T-U-store-07` | Every row's `artefact_dir` exists on disk; one row per candidate and one per probing input, with the foreign keys that join them | `probe_result/iteration/` | T0 | FR-17.2 |
| `T-U-store-08` | The two write-order rules of `03-LLD.md` §6.4 hold, including the loop-row-before-CHIA-row rule of FR-12.10 | `repair/issues.db` | T0 | FR-12.10 |
| `T-U-store-09` | `validate_candidate` enforces the per-class conditionals of `03-LLD.md` §2.9, including that a `differential` candidate carries no reduction, dedup or gate fields | `candidate/` | T0 | FR-08.10, FR-13.14 |
| `T-U-store-10` | **The secret grep.** No token, key or credential appears in any row or any file the store writes, over a full fixture run; see also `T-N-nfr06-01` | `secrets/known_values.txt` | T0 | FR-17.5, NFR-06 |

### 1.19 `results.py` (B11), 20 tests

Tests 01 to 14 are the fourteen named refusal checks of `03-LLD.md` §14.4, one each. All are tier 0:
`render_results` is a pure function of the store.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-results-01` | `_require_headline`: distinct confirmed bugs per arm, counted per primary fingerprint, populated only from `filing` rows carrying maintainer evidence with a URL; two filings sharing a fingerprint count once | `results/store_full.db` | T0 | FR-18.3 |
| `T-U-results-02` | `_require_secondaries`: all five per arm, each computable from the store alone | `results/store_full.db` | T0 | FR-18.4 |
| `T-U-results-03` | `_require_validation_table`: the seeded-bug validation table is separate and contributes nothing to the headline | `results/store_full.db` | T0 | FR-18.5 |
| `T-U-results-04` | `_require_qualifiers`: **every** table names the mode and the seed set; a table missing either fails the render, naming the missing qualifier | `results/store_full.db` | T0 | FR-18.2 |
| `T-U-results-05` | `_require_contamination`: the contamination column is present and the headline is printed both with and without contaminated candidates | `results/store_full.db` | T0 | FR-15.2 |
| `T-U-results-06` | `_require_disclosures`: both sentences are present, the screen's incompleteness and the repair stage being unscreened | `results/store_full.db` | T0 | FR-15.3, FR-15.4 |
| `T-U-results-07` | `_require_lag`: the lag the campaign ran under is printed beside the headline | `results/store_full.db` | T0 | FR-02.2 |
| `T-U-results-08` | `_require_cutoff`: the confirmation cut-off date is present, and the artefact states that maintainer confirmation lags the budget window | `results/store_full.db` | T0 | FR-18.8 |
| `T-U-results-09` | `_require_dedup_rates`: the collision and false-merge rates are printed **beside the headline they qualify** | `results/store_full.db` | T0 | FR-10.2 |
| `T-U-results-10` | `_require_divergences`: the divergences-observed list is present | `results/store_full.db` | T0 | FR-18.12 |
| `T-U-results-11` | `_require_mutator_declaration`: the declaration names the synthesis input, the synthesis date and the frozen set's SHA, and states that this is Mut4All's design | `results/store_full.db` | T0 | FR-05.8 |
| `T-U-results-12` | `_require_observed_heading`: tokens, cost and CPU time appear under a heading that states they are **not** the budget | `results/store_full.db` | T0 | FR-14.5 |
| `T-U-results-13` | `_require_both_windows`: both arms' elapsed windows are printed, with the binding cap and the unspent balance where one bit | `results/store_capped.db` | T0 | FR-18.10 |
| `T-U-results-14` | `_require_regeneration_marks`: a row that could not be regenerated is **marked** rather than reported | `results/store_marked.db` | T0 | FR-18.11 |
| `T-U-results-15` | **The empty-confirmation render (FR-18.7).** With an empty confirmation set the render **succeeds** and states the zero for both arms; every other mandatory element is still present, and no refusal fires for want of a confirmed bug | `results/store_zero.db` | T0 | FR-18.7 |
| `T-U-results-16` | No sentence compares the loop's count to FLEX, ISSTA-2024, Nuwa or DESIL; checked by a name search over the rendered text | `results/store_full.db` | T0 | FR-18.9 |
| `T-U-results-17` | The taxonomy's six buckets sum to the candidate count, and the repair-phase counts sum to the repair-attempt count; `differential` candidates appear in neither denominator | `results/store_full.db` | T0 | FR-18.6, FR-13.14 |
| `T-U-results-18` | `arm` is branched on here and in `ledger.py` only; the module is exempt from `T-U-layout-02`'s walk by name, and this test asserts the exemption is used for the results table and nothing else | none | T0 | FR-18.1 |
| `T-U-results-19` | The divergences list's length equals the number of `differential` reports in the store, and no entry carries a `GateDecision` or a `FilingRecord` | `results/store_full.db` | T0 | FR-08.10, FR-18.12 |
| `T-U-results-20` | Both arms' seed SHA sets are identical within a mode: 187 in discovery, 171 in calibration | `results/store_full.db` | T0 | FR-18.2 |

### 1.20 `bug_loop.py` (B12, and B1's driver), 20 tests

Tests 01 to 11 are the eleven pre-flight checks of `03-LLD.md` §13.1, one each, in order. Each asserts
that the check **stops the run** and names what failed.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-driver-01` | Pre-flight 1: `budget.yaml` committed and its commit earlier than the run's start | `repo/uncommitted/` | T0 | FR-14.2 |
| `T-U-driver-02` | Pre-flight 2: the mutator set's last commit predates the budget file's | `repo/mutator_after/` | T0 | FR-05.2 |
| `T-U-driver-03` | Pre-flight 3: the clone's HEAD equals `corpus_head_sha`, naming both on a difference | `corpus/clone` | T1 | FR-01.11 |
| `T-U-driver-04` | Pre-flight 4: the artefact root exists and is writable on the head | none | T0 | FR-17.9 |
| `T-U-driver-05` | Pre-flight 5: the artefact root is writable on **every worker**, checked by a trivial node per worker type; a failure is `artefact_root_unmounted`, names the worker and the path | none | T3 | FR-17.9 |
| `T-U-driver-06` | Pre-flight 6: the image exists and its `ImageSpec.lit_discovery_ok` is true | `image_spec/ok.json`, `image_spec/lit_broken.json` | T0 | FR-03.17 |
| `T-U-driver-07` | Pre-flight 7: every tool binary's `sha256` on every worker matches `ImageSpec.tool_hashes` | `image_spec/ok.json` | T2 | FR-06.1, FR-03.16 |
| `T-U-driver-08` | Pre-flight 8: `verilator --version` on every CIRCT worker equals `ImageSpec.verilator_version`; a difference exits non-zero naming both, because a changed Verilator starts a new campaign | `image_spec/ok.json` | T2 | FR-03.15 |
| `T-U-driver-09` | Pre-flight 9: the pin selector runs and all eight manifest pin fields are stamped once and never recomputed | `pin/pin_window_raw.json` | T0 | FR-02.1, FR-02.2, FR-02.3, FR-02.4 |
| `T-U-driver-10` | Pre-flight 10: the issue mirror is refreshed once per run before the first candidate is screened, or an existing one for this campaign is reused unless a refresh is asked for | `mirror/` | T0 | FR-10.9 |
| `T-U-driver-11` | Pre-flight 11: `forum_post_url` and `forum_post_date` are present in the manifest before the first filing is possible | `run_manifest/` | T0 | FR-20.1 |
| `T-U-driver-12` | Every argument of `03-LLD.md` §13.1's table parses, with the stated defaults; an unknown argument exits non-zero | none | T0 | FR-19.3 |
| `T-U-driver-13` | **One flag swaps the arm.** `--arm seeded`, `--arm mutation` and `--arm both` all run from the same entry point with no code change; `both` runs them **sequentially** in `budget.yaml`'s `arm_order` | `budget/complete.yaml` | T0 | FR-19.3, FR-18.10 |
| `T-U-driver-14` | `--dry-run` runs every pre-flight check and builds the manifest, and dispatches nothing | none | T0 | FR-19.3 |
| `T-U-driver-15` | `--record-fixtures` writes every produced instance after `validate` accepts it, named by its id, one JSON document per file | none | T0 | FR-04.3 |
| `T-U-driver-16` | `--resume` reuses a `run_manifest_id`, skips iterations whose records are complete, never re-charges the ledger, and refuses to continue if the budget file SHA no longer matches | `repo/preregistered/` | T0 | FR-14.7 |
| `T-U-driver-17` | `_PY_MODULES` holds the fourteen entries of `03-LLD.md` §13.1, including CHIA's own `issue_task.py` and `circt_util.py` from the other example directory, and `contract/` and `mutators/` as directories | none | T0 | FR-12.1 |
| `T-U-driver-18` | The end-of-run reconciliation marks every loop repair row whose CHIA counterpart never appeared as `repair_row_missing`, and no join key dangles unmarked | `repair/issues.db` | T0 | FR-12.10 |
| `T-U-driver-19` | A contract instance carrying a different MAJOR stops the run, naming both versions; the failure is hard, not a warning | `malformed/major.json` | T0 | FR-04.3 |
| `T-U-driver-20` | Per-stage counters ride home on return values and are logged on the head through `MetricsLogger`; a run produces a metrics directory with one counter per stage and `stages_metered` lists every stage as metered or unmetered | none | T0 | FR-14.8, FR-17.4, NFR-09 |

### 1.21 `chia/chipyard/circt.py`, the three core additions, 13 tests

In `chia/chipyard/test/test_circt_probe.py`, which is a **separate** deliverable from the example's own
tests: a test under the example directory does not discharge a contribution to `chia/`
(`chia:AGENTS.md:122-124`).

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-core-01` | `circt_exec_probe` builds `["prlimit", "--as=", "--cpu=", "--nofile=", "--", tool, *argv]` in that order, long spellings only, and never passes `--rss` | none | T0 | FR-06.2 |
| `T-U-core-02` | All three limits reach the child, by the measured probe: `prlimit --as=1073741824 --cpu=5 --nofile=256 -- /bin/sh -c 'ulimit -v; ulimit -t; ulimit -n'` prints `1048576`, `5` and `256` | none | T1 | FR-06.2 |
| `T-U-core-03` | The child starts in its own process group (`start_new_session=True`) and the whole group is SIGKILLed on `TimeoutExpired`; no descendant survives, asserted by a process-table check | none | T1 | FR-06.3 |
| `T-U-core-04` | The signal is read from the child's **negative return code**, `-N` meaning signal N, and is recorded in a field separate from the exit status; a SIGABRT child records `SIGABRT` and a null exit status, never 134 | none | T1 | FR-06.4 |
| `T-U-core-05` | Output is capped at `output_byte_cap` with `truncated` recorded per call | none | T1 | FR-06.4 |
| `T-U-core-06` | `FileNotFoundError` when the tool does not exist; every other failure is a returned field and not an exception | none | T0 | FR-06.1 |
| `T-U-core-07` | No `shell=True` anywhere in the three functions, and no command **string** is ever constructed; asserted on the source and on the recorded argv | none | T0 | FR-06.1 |
| `T-U-core-08` | `circt_reduce_run` builds `[circt-reduce, input, --test=<script>, -o <out>]` with `--keep-best` passed explicitly and `--test-must-fail` never passed, and passes no `--test-arg`, so the candidate is the script's `$1` | none | T1 | FR-09.2 |
| `T-U-core-09` | `output_valid` is computed **after** the process exits; a `-o` file truncated mid-write is reported invalid | `reducer/truncated/` | T1 | FR-09.4, FR-09.13 |
| `T-U-core-10` | `circt_symbolize` runs `llvm-symbolizer --obj=<path> --demangle --output-style=JSON` with addresses on stdin and parses one JSON object per line; `--functions` is left at its default `linkage` and `--inlines` is never passed | none | T1 | FR-07.4 |
| `T-U-core-11` | An unparseable line yields an unresolved record with `function` and `file` empty and `line` 0, and raises nothing | none | T1 | FR-07.4 |
| `T-U-core-12` | **The symbolizer wrapper against `bassert_g`.** `0x3365f30` against `~/.cache/chia-pin-smoke/bassert_g/bin/circt-opt` resolves to `circt::chooseName(llvm::StringRef, llvm::StringRef)` and `lib/Support/Naming.cpp:47` (M2), so a frame names a CIRCT source file and a line under `-gline-tables-only` | `symbolize/bassert_g_addrs.txt` | T1 | FR-07.4, FR-03.4 |
| `T-U-core-13` | The same address against a build without `-g` returns the demangled name and an unresolved location, which is the `??:0:0` the measurement recorded; `--functions=short` returns `??` under `-gline-tables-only` and is therefore not used | `symbolize/bassert_addrs.txt` | T1 | FR-07.4 |

### 1.22 `dockerfiles/ChiaCirctAssertDockerfile` and the `ImageSpec`, 17 tests

The unit under test is the **image**, so every test here is tier 2 except those driven from a recorded
`ImageSpec`. There is no in-process substitute for an image, which is why §12.3 lists F-03's
requirements as testable only above tier 1.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-image-01` | Fetch-by-SHA, not `--branch`: built at `5056ff04450b`, `git -C /workspace/circt rev-parse HEAD` inside the image prints `5056ff04450bc9f27a9ff0460702aee1f1afdd3f` | none | T2 | FR-03.1 |
| `T-U-image-02` | A one-bump-off SDK/source pair exits non-zero **before** `ninja` starts, comparing `git ls-tree <tag> llvm` against the commit's gitlink as full 40-character SHAs | `image/one_bump_off/` | T2 | FR-03.2 |
| `T-U-image-03` | `/opt/circt-sdk/include/circt` and `/opt/circt-sdk/lib/cmake/circt` are both absent inside the built image | none | T2 | FR-03.3 |
| `T-U-image-04` | `CMakeCache.txt` holds `CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -UNDEBUG -gline-tables-only`; `grep -c -- -DNDEBUG compile_commands.json` returns 0; `readelf -S .../circt-opt` lists `.debug_line` | none | T2 | FR-03.4 |
| `T-U-image-05` | `nm -u circt-opt` shows `__assert_fail`; the emitted list of non-referencing `obj.CIRCT` objects is compared **as a set** against `assertion_baseline_count` 18, every difference named object by object, and any difference blocks publication | `image/baseline_objects.txt` | T2 | FR-03.5 |
| `T-U-image-06` | The two lit runs over the whole `test/` tree under CHIA's own exclusions produce **equal failing-name sets**; measured at `5056ff0445`, 1,127 discovered, 1,058 passed, 0 failed under either flag string (M3), so the difference is empty. Run only after `T-U-image-17` passes, since two empty sets compare equal | `image/lit_baseline/` | T2 | FR-03.6 |
| `T-U-image-07` | Each of `circt-opt`, `firtool`, `circt-translate`, `arcilator`, `circt-reduce` exists under `/workspace/circt/build/bin` and runs `--version`; the target list is read from `ImageSpec.targets` and is a parameter, not a constant | none | T2 | FR-03.7 |
| `T-U-image-08` | `lit --version`, `verilator --version` and `arcilator --version` all succeed; `ldd /opt/circt-sdk/bin/circt-opt` resolves `libz3.so.4`; `pip install lit` reports the requirement already satisfied; `lit` is at `/home/ray/anaconda3/envs/py_worker/bin/lit`, the path `circt_warm_build` checks | none | T2 | FR-03.8 |
| `T-U-image-09` | `ssh -V` and `rsync --version` both succeed inside the image, which CHIA's own CIRCT base does not satisfy; the `ImageSpec` records that it is correcting the base | none | T2 | FR-03.9 |
| `T-U-image-10` | The `ImageSpec` is emitted with every field of `03-LLD.md` §2.9 and reaches `RunManifest.image_spec` with the eight keys of §2.11 | `image_spec/ok.json` | T0 | FR-03.10 |
| `T-U-image-11` | A rendered `Report` from an image built under FR-03.4 contains both the literal `-UNDEBUG` and the tool's own `--version` output, which still reads "Optimized build." | `report/` | T0 | FR-03.11, C-08 |
| `T-U-image-12` | MLIR and LLVM assertions stay off: `/opt/circt-sdk/include/llvm/Config/abi-breaking.h` still hard-codes `#define LLVM_ENABLE_ABI_BREAKING_CHECKS 0`, and nothing in the Dockerfile attempts to enable them | none | T2 | FR-03.12 |
| `T-U-image-13` | A build with a deliberately broken target reports which targets succeeded and leaves **no image** under the requested tag | `image/broken_target/` | T2 | FR-03.13 |
| `T-U-image-14` | **Slang, both branches.** Branch (a): `circt-verilog --version` succeeds and reports the image's CIRCT SHA (measured `CIRCT 5056ff0`, M7), `circt-translate --help` carries `--import-verilog` (0 hits without slang, 1 with, M7), and `lit.site.cfg.py` reads `config.slang_frontend_enabled = 1`. Branch (b): the manifest carries the exclusion naming **36** seeds, the union of the two slang entry points (M1), and `ImageSpec.slang_enabled` is false | `image/slang/` | T2 | FR-03.14 |
| `T-U-image-15` | One Verilator version serves the campaign: the version is in the `ImageSpec`, in the `RunManifest` and in **every** `DifferentialVerdict`, and a run whose image reports a different one exits non-zero naming both. The image's packaged version is 5.020-1 (M8) and it carries `--x-initial`, `--x-assign`, `--binary` and `--timing` | `image_spec/ok.json` | T2 | FR-03.15 |
| `T-U-image-16` | `ImageSpec.tool_hashes` names every target in the target list, and re-hashing those binaries inside a **freshly started container from the published image** reproduces the map exactly | none | T2 | FR-03.16 |
| `T-U-image-17` | `grep mlir_src_root /workspace/circt/build/test/lit.site.cfg.py` prints `/opt/circt-sdk` rather than an empty string; `lit --no-progress-bar --show-tests /workspace/circt/build/test` exits 0, lists at least one test under `Tools/circt-tblgen/`, and prints no `fatal: unable to parse config file` line. A non-zero exit or any such line blocks publication | none | T2 | FR-03.17 |

### 1.23 `prompts/` and the shared footer parser, 6 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-prompt-01` | **The last block wins.** A turn output holding two fenced `json` blocks parses the **second**, which is the rule CHIA's own assess parser uses | `turns/two_blocks.md` | T0 | FR-04.8, FR-11.8 |
| `T-U-prompt-02` | **Malformed footers.** Each of `no_block`, `not_json`, `not_object` and `missing:<key>` raises `PromptContractError` with that reason; none is retried inside the turn and none is repaired by guessing | `turns/footer_*/` | T0 | FR-04.8, FR-11.8 |
| `T-U-prompt-03` | Rendering uses `Template(...).safe_substitute(**kw)` and never `str.format`: a prompt carrying MLIR braces and shell braces renders them unchanged, and an undefined `$name` survives as itself rather than raising | `prompts/` | T0 | FR-16.5 |
| `T-U-prompt-04` | Every substitution variable `03-LLD.md` §7.2, §7.3, §7.4 and §8.3 declares is present in its prompt file and is supplied by its caller; an unsupplied variable fails the test | `prompts/` | T0 | FR-04.1, FR-11.1 |
| `T-U-prompt-05` | `prompts/report_write.md` is a **separate** file from CHIA's `writeup.md` and contains no `Fixes #<number>` line, because an issue report is not a pull-request description | `prompts/` | T0 | FR-11.5 |
| `T-U-prompt-06` | The raw turn output is persisted whatever happens, so a contract failure is inspectable and not merely counted; all five per-turn files exist for stages 1, 2 and 6 | `turns/` | T0 | FR-04.6, FR-11.7 |

### 1.24 `cluster_single.yaml` and `cluster_gcp.yaml`, 6 tests

Parsed as YAML and asserted structurally; tier 0 except `T-U-cluster-01`, which needs the cluster up.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-cluster-01` | `chia up cluster_single.yaml` brings all five workers to Ready and a trivial `@ChiaFunction` runs on each of the three types; `ssh -V` and `rsync --version` succeed inside each | none | T3 | FR-03.9, NFR-10 |
| `T-U-cluster-02` | Exactly three worker types with exactly three resource names, `llm`, `circt` and `repair`; counts 2, 2 and 1; `{"llm": 1}` per container so `llm_concurrency` equals the container count | none | T0 | FR-12.11 |
| `T-U-cluster-03` | `min_workers` equals `max_workers` on all three types, so the cluster is fixed-size and `apparatus_concurrency` is exactly the `bugloop_circt` count | none | T0 | FR-14.5 |
| `T-U-cluster-04` | `run_options` on both CIRCT types carry a container CPU limit, a container memory limit, and the artefact bind mount `-v <host root>:<the same absolute path>` read-write; both limits are additions over CHIA's four | none | T0 | FR-17.9, NFR-05 |
| `T-U-cluster-05` | `run_setup_commands` carry CHIA's `/etc/passwd` and three `git config` lines and **no** `pip install lit`; and no cluster YAML mentions `GITHUB_TOKEN` or mounts a credential file | none | T0 | FR-03.8, NFR-07 |
| `T-U-cluster-06` | `cluster_gcp.yaml` declares the same three worker types, the same resource names and the same images, so no loop code changes between deployments; `RunManifest.deployment` and `cluster_yaml_sha` record which ran | none | T0 | NFR-10 |

### 1.25 `bug_loop_submit.sh`, 3 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-submit-01` | The script contains no `--runtime-env-json` and no `GITHUB_TOKEN`, anywhere, asserted by a text search; this is the one difference from CHIA's wrapper and it is what keeps the token out of job metadata | none | T0 | NFR-06, FR-17.5 |
| `T-U-submit-02` | `BUGLOOP_ARTEFACTS` and `BUGLOOP_IMAGE_TAG` are required and the script exits non-zero naming the missing one; `set -euo pipefail` is present | none | T0 | FR-17.9 |
| `T-U-submit-03` | The script `exec`s `chia job submit --address <addr> -- <python> bug_loop.py "$@"`, passing every argument through, so driver logs are retrievable by `chia job logs <id>` | none | T0 | NFR-09, FR-20.6 |

### 1.26 The committed `budget.yaml`, 3 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-byaml-01` | The committed file validates against `03-LLD.md` §9.1's schema, with no key missing and no key extra | none | T0 | FR-14.1 |
| `T-U-byaml-02` | **Every campaign `[DEFAULT]` marker in `01-FRD.md` resolves to exactly one key of this file**, checked by extracting the markers and their named homes and comparing against the key set; the two markers that are not campaign parameters resolve to `03-LLD.md` §9.4 and to §13 of this document | none | T0 | FR-14.1 |
| `T-U-byaml-03` | The `acceptance` block carries the seven keys of `03-LLD.md` §9.3, and each equals the sample size the corresponding feature-acceptance criterion names | none | T0 | FR-14.1 |

---

## 2. Integration tests: every seam crossing

Seventeen tests. Each names the recorded fixture set it replays, and how that set is produced and
frozen. The production rule is one rule for all of them, from `02-HLD.md` §2.13: a fixture is the
output of a real run under `--record-fixtures`, written after `contract.validate` accepted it, and
committed. A fixture is **frozen** by being committed under `contract/fixtures/<schema>/<id>.json`
with its `contract_version` recorded inside it; re-recording is a commit, and `T-U-fixt-01` is what
notices that the set and the package have drifted apart.

| Test | Crossing | Live side | Replayed side and fixture set | Behaviour | Tier | FR |
|---|---|---|---|---|---|---|
| `T-I-gen-app-01` | generator to apparatus | `probe_task.probe_execute` | `ProbeSpec` fixtures from the **seeded** arm, recorded by a `--record-fixtures` run of A3 over the 5-seed acceptance sample | Every recorded seeded spec is consumed with no change: the tool binary resolves, the argv executes, a `BuildResult` and a `ProbeResult` come back, and no generator code is imported | T2 | FR-04.3, FR-06.1 |
| `T-I-gen-app-02` | generator to apparatus | `probe_task.probe_execute` | `ProbeSpec` fixtures from the **mutation** arm, recorded from A4 over the same seeds | The same, with `arm=mutation`, `mutator_id`, `mutator_seed_int` and `source_test_path` populated; the apparatus's outputs are identical to `T-I-gen-app-01`'s but for the carried `arm` value | T2 | FR-05.4, FR-18.1 |
| `T-I-gen-app-03` | the `generate` interface | A3 and A4 in turn | a fixture `SeedRecord`, a fixture `FeedbackBundle` and a constructed `LedgerSnapshot` | Both implement the one signature; A4 ignores `feedback`; both return `list[ProbeSpec]` that `validate` accepts | T0 | FR-05.4, FR-16.2 |
| `T-I-app-tri-01` | apparatus to triage | `triage_task.dedup_and_screen` | recorded `CandidateRecord`s with their `ReducedCase` and `OracleVerdict`, plus a recorded issue mirror | Fingerprints computed, the partition formed, both screens run, and every verdict carries evidence; no GitHub request is made | T1 | FR-10.1, FR-10.3, FR-10.4 |
| `T-I-app-tri-02` | apparatus to triage | `triage_task.triage_report` | the same, plus a recorded stage-6 transcript | The report renders with every substitution point from the record; the tool verdict overrides the agent's class; no number originates in the transcript | T0 | FR-11.2, FR-11.3, FR-11.4 |
| `T-I-tri-rep-01` | triage to repair adapter | `repair_adapter.repair_adapt`, with CHIA's chain stubbed at `run_issue_remote` | a recorded `Report`, `ReducedCase` and `OracleVerdict` for a `crash` candidate | The adapter mints the local id, builds the whole `GithubIssue`-shaped object, pre-writes `repro.sh` and the case, and calls `run_issue_remote(issue_md, number)` with a byte-identical `issue_task.py` | T0 | FR-12.1, FR-12.2, FR-12.3 |
| `T-I-tri-rep-02` | triage to repair adapter | the same | recorded `differential`, `fatal_error` and `out_of_scope_root` candidates | Each is refused by class or scope with a recorded reason, and the chain is never invoked | T0 | FR-12.4, FR-12.5 |
| `T-I-rep-gate-01` | repair to gate | `gate.gate_decide` | recorded `RepairResult`s covering all six CHIA statuses | `report_plus_patch` only for `fixed` with `lit_ok`; `report` otherwise; `lit_unusable` stops the run rather than charging the difference to the patch | T0 | FR-12.7, FR-12.8, FR-13.6 |
| `T-I-rep-gate-02` | repair to gate | `gate.gate_decide` with `gate_rerun` live | a recorded candidate whose reproducing command still fires | All four questions answered from tool records, the decision written, and the taxonomy bucket set | T1 | FR-13.1, FR-18.6 |
| `T-I-gate-appr-01` | gate to approval | `approve.main` over a seeded store | recorded `GateDecision`s of each of the three values | Only `report` and `report_plus_patch` are presented; `nothing` is never listed; the four answers and the stopping question appear in `show` | T0 | FR-13.10, FR-13.12 |
| `T-I-gate-appr-02` | gate to approval | `approve.main` | a recorded `GateDecision` of `report_plus_patch` plus its diff | Approval writes exactly one `filing` row carrying approver, timestamp, decision, licence confirmation and URL source; a decline writes a downgrade | T0 | FR-13.7, FR-20.5 |
| `T-I-ledger-01` | ledger across the halves | `ledger.accrue` and `ledger.aggregate` | `LedgerEntry` fixtures recorded by **both** halves in one run, covering all three `arm` values and both `scope` values | The aggregate reconciles: one `arm_window` entry per arm, per-stage entries summing independently, `shared` reported beside and never folded | T0 | FR-14.4, FR-14.5 |
| `T-I-ledger-02` | ledger across the halves | `budget.snapshot` feeding A3 and A4 | the same fixtures | The `LedgerSnapshot` a generator sees carries four fields and no result field; the generator cannot reach `BudgetLedger` | T0 | FR-16.4 |
| `T-I-feed-01` | feedback bundle | `feedback.build_feedback` | `ProbeResult` fixtures for one whole iteration, including clean exits, parse errors, timeouts and OOMs | One `FeedbackEntry` per probing input, built from `ProbeResult`s alone, with no apparatus-internal schema imported | T0 | FR-16.1 |
| `T-I-feed-02` | feedback bundle back into the generator | A3 with a replayed transcript | the bundle `T-I-feed-01` produced | The next iteration's prompt bytes are reproducible from the recorded `SeedRecord` plus the bundle; the mutation arm receives a bundle whose `entries` list is empty and reads it not at all | T0 | FR-16.2, FR-16.5 |
| `T-I-version-01` | contract version, downward | the apparatus half's replay entry point | supply-half fixtures re-recorded at MAJOR `2.0` | Every consumer raises `E001_MAJOR_MISMATCH` naming both versions; the failure is hard and stops the reading stage, with no shim and no tolerance | T0 | FR-04.3 |
| `T-I-version-02` | contract version, upward | the supply half's replay entry point | apparatus-half fixtures re-recorded at MAJOR `2.0` | The same in the other direction, so a mismatch cannot be one-sided; and the driver turns the stage failure into a run stop | T0 | FR-04.3 |

---

## 3. System tests

Nine tests, all tier 3, all on the single-machine cluster of §0.7 and all submitted through
`bug_loop_submit.sh`. `tests/system/budget_tiny.yaml` is the budget for every one of them.

| Test | What it runs | Pass criterion | FR |
|---|---|---|---|
| `T-S-cluster-01` | `chia up cluster_single.yaml`, then a trivial node on each worker type | Five containers Ready; one node lands on each of `llm`, `circt` and `repair`; the artefact root is writable from all of them at the identical absolute path | FR-03.9, FR-17.9, NFR-10 |
| `T-S-disc-01` | **One full iteration in discovery mode.** `bug_loop.py --mode discovery --arm seeded` over one seed, `per_seed_iteration_cap` 1, `per_seed_probe_cap` 3 | Eleven pre-flight checks pass; the manifest carries exactly one `run_commit` with a null `seed_sha`; three probes execute, are judged, reduced where they fired, screened, triaged and gated; every stage's artefacts exist under `<root>/<run>/seed_<sha>/iter_1/probe_<id>/`; the taxonomy counts sum | FR-02.7, FR-17.1, FR-18.6 |
| `T-S-calib-01` | **One full iteration in calibration mode**, over one seed of `calibration_sample_shas`, at that seed's own parent commit | The manifest carries one `run_commit` **per sampled seed**, each with a non-null `seed_sha`; the gate's verdict is recorded and **no filing is possible**; the seeded-bug validation table is produced separately from the discovery table | FR-02.7, FR-18.5 |
| `T-S-pilot-01` | **One pilot campaign**, both arms, `--arm both`, `arm_window_seconds` 600 `[DEFAULT]` each, sequential, in `arm_order`, from one cluster YAML at one concurrency | The two arms run one after the other, never overlapping, each metered on the head; each stops at its own window or at a binding safety cap; the results artefact prints **both** windows with the binding cap and the unspent balance; the failure taxonomy and the seeded-bug validation table are complete; every table names its mode and seed set | FR-14.5, FR-18.1, FR-18.2, FR-18.4, FR-18.10 |
| `T-S-isolate-01` | **The repair-worker isolation test.** Hash every tool binary on both `bugloop_circt` workers, run one full repair attempt on `bugloop_repair`, re-hash | The `bugloop_circt` hash manifest is **unchanged** and still equals `ImageSpec.tool_hashes`; the `bugloop_repair` worker's binaries are restored by `circt_git_reset` plus `circt_ninja_build` and match the manifest again; `restore_ok` is recorded; a deliberately failed restore records `repair_worker_dirty` and disables B8 for the rest of the run | FR-03.16, FR-06.1, FR-12.11 |
| `T-S-regen-01` | **The artefact regeneration check over every row of the pilot** (§11) | Every tool stage of every row re-executes from its stored inputs and produces the stored verdict; every agent turn replays from its stored transcript through CHIA's bypass; a row that cannot be regenerated is **marked**, not reported; replaying a tool stage through bypass is never accepted as evidence | FR-17.1, FR-18.11, NFR-01 |
| `T-S-lit-01` | **The control run of FR-07.9** (§9) | The whole lit suite runs inside the image at the run's commit and the assertion false-positive set is reported | FR-07.9 |
| `T-S-artefact-01` | A probe-bearing node writes a file under the recorded artefact root; the head reads it by the **same** path with no copy step. Then the bind mount is removed from one worker type and the run restarted | The head reads the worker's file by the identical path; with the mount absent the run exits non-zero as `artefact_root_unmounted`, naming the worker and the path, rather than writing elsewhere | FR-17.9 |
| `T-S-submit-01` | **The `chia job submit` wrapper.** `bug_loop_submit.sh --mode discovery --dry-run`, then a real submission | `chia job logs <id>` returns the driver's output **during** the run; the metrics directory shows per-stage counters during the run; `chia job` output and the dashboard carry no token in the job's `runtime_env`; `chia job stop --kill-tracked-pids` leaves no orphaned probe | NFR-06, NFR-09 |

---

## 4. Equivalence-class partitioning of the probing-input space

Fourteen classes: the ten `01-FRD.md` §10.3 item 4 names, plus the four-way language partition M1
measured over the corpus (`.mlir` 146 seeds, `.sv` 36, `.fir` 8, other 7; by best reduction path,
146 direct, 35 via the `circt-verilog` lift, 4 via the `firtool` lift, 2 textual only). Every class
has one concrete constructed input, committed under `fixtures/equivalence/<class>/`, and is driven end
to end through the apparatus. The partition is over **outcomes**, so the classes are disjoint by
construction: `ProbeResult.build_status` takes one of seven values, `oracle_fired` one of two, and no
input can be in two rows.

| Test | Class | Constructed input | Expected `ProbeResult` | Reducer path | Gate outcome |
|---|---|---|---|---|---|
| `T-E-input-01` | valid input that passes | a well-formed `hw.module` with two ports, run under `circt-opt --canonicalize` | `build_status=clean_exit`, `exit_status=0`, `signal=null`, `oracle_fired=false`, `stopping_stage=stage_4`, `stopping_reason=oracle_did_not_fire` | none; B5 is not dispatched | never reaches the gate; counted in the feedback bundle |
| `T-E-input-02` | valid input that crashes | an MLIR module driving a null dereference in a CIRCT pass, reduced from the recorded crash of `fixtures/oracle/crash_01/` | `build_status=crash`, `exit_status=null`, `signal=SIGSEGV`, `oracle_fired=true`, `oracle_class=crash` | `circt-reduce`, no lift | passes questions 1 to 3; question 4 by the dedup verdict |
| `T-E-input-03` | valid input that fires an assertion | an MLIR module violating a documented pass precondition, from `fixtures/oracle/assert_01/` | `build_status=assertion`, `signal=SIGABRT`, `exit_status=null`, `assertion_text` and `assertion_site` non-empty and verbatim, `oracle_class=assertion` | `circt-reduce`, no lift | the same; the fingerprint basis is `assertion` |
| `T-E-input-04` | input rejected by the parser | an `.mlir` file whose first token is `%%%` | `build_status=parse_error`, `exit_status` non-zero, `signal=null`, `oracle_fired=false` | none | never reaches the gate; PAPER §2's "does it build" bar; the reason returns in the bundle |
| `T-E-input-05` | input that times out | a module whose canonicalisation does not terminate inside `probe_wall_seconds` (60) | `build_status=timeout`, `signal=null`, `limit_hit=wall`, `oracle_fired=false` | none | never fires; counted separately in the taxonomy, never as a crash |
| `T-E-input-06` | input that exhausts memory | a module allocating past `probe_address_space_bytes` (4 GiB) | `build_status=oom`, `limit_hit=address_space`, `oracle_fired=false`, **and the worker survives** | none | never fires; the worker still answers a trivial node afterwards |
| `T-E-input-07` | input whose crash roots in MLIR, not CIRCT | a module crashing inside MLIR's own verifier, from `fixtures/oracle/mlir_root/` | `build_status=crash`, `oracle_fired=true`, `oracle_class=crash`, `out_of_scope_root=true` | `circt-reduce` runs normally | report-only: never reaches repair; reaches the gate and is reported |
| `T-E-input-08` | input that reduces | the 4,000-op `comb` module of M2's probe-speed measurement, carrying one crashing operation | `oracle_fired=true`; `ReducedCase.reduced=true`, `fixpoint=true`, `size_after_bytes < size_before_bytes` | `circt-reduce` to a fixpoint | question 2 passes |
| `T-E-input-09` | input that does not reduce | the already-minimal output of `T-E-input-08`, fed again | `ReducedCase.reduced=false`, `reason` recorded, `fixpoint=true` | `circt-reduce` making no progress | refused at question 2 as `not_minimal`, with the reason recorded, and still persisted and counted |
| `T-E-input-10` | input that duplicates another | a byte-different module producing the same assertion expression at the same `file:line` as `T-E-input-03` | `oracle_fired=true`, `oracle_class=assertion`; the same primary fingerprint | `circt-reduce` | refused at question 4 as `duplicate_of_candidate`, naming the first candidate's id |
| `T-E-input-11` | **M1 language partition: MLIR direct** | a `.mlir` probe entering through `circt-opt`, which is 146 of 187 seeds (78.1%) | any firing class; `ProbeSpec.tool=circt-opt` | `circt-reduce`, `lift=null` | as its class dictates; question 3 checked by `circt-opt <case> -o /dev/null` |
| `T-E-input-12` | **M1 language partition: `.fir` lift** | a `.fir` probe entering through `firtool`, 4 of 187 by best path | firing class; `ProbeSpec.tool=firtool` | `circt-reduce` on the lift `firtool --ir-fir`, retried with `--parse-only` where the failure is inside the pipeline; `ReducedCase.lift` records which | question 3 checked by `firtool --parse-only <case>` |
| `T-E-input-13` | **M1 language partition: `.sv` lift** | a `.sv` probe entering through `circt-verilog`, 35 of 187 by best path. Under ADR-D-13 branch (b) this class is empty and the 36 slang-entry seeds are excluded by configuration | firing class; `ProbeSpec.tool=circt-verilog` or `circt-translate` | `circt-reduce` on the lift `circt-verilog --ir-moore`; `ReducedCase.lift` records it | question 3 checked by `circt-verilog --import-only <case>` |
| `T-E-input-14` | **M1 language partition: textual only** | a `.fir` probe whose failure is in the `.fir` **parser**, so no MLIR ever exists; 2 of 187 seeds are textual-only | firing class; both lifts fail and the failure is recorded | `textual-ddmin` over the input's lines, driven by the same interestingness script | question 3 by the language's own check; question 2 passes if ddmin reached 1-minimality |

`T-E-input-14` is also `01-FRD.md` §10.3 item 13's fourth branch, the `.fir` input whose failure is in
the parser and which therefore reaches the textual reducer; the other three branches are
`T-E-input-11`, `T-E-input-12` and `T-E-input-13`, and `T-U-probe-31` exercises all four as a unit
test of the selection rule alone.

Every row's tier is T2, because each drives a real binary from the assertions-on image. Each is run
twice, once with `arm=seeded` and once with `arm=mutation` on an otherwise identical `ProbeSpec`, and
the apparatus's outputs must be identical but for the carried `arm` value (FR-18.1).

---

## 5. The oracle against recorded real crashes

`01-FRD.md` §10.3 item 5 and F-07's feature acceptance both ask for at least
`budget.yaml`'s `acceptance.recorded_failures`, which is 5 `[DEFAULT]`, real CIRCT crashes, assertion
failures and `LLVM ERROR:` aborts, recorded with their inputs and their commits, and replayed.

### 5.1 The procedure that builds the set

Two candidate sources, in this order, and both are used because neither alone is guaranteed to yield
five.

**Source A, the 187 seeds.** For every seed whose commit subject matches `crash`, `assert`,
`segfault` or `verifier`, case-insensitively on word boundaries, which is a subset of the corpus
filter PIN §2 already applies:

1. Take the seed's **first parent**, which is the commit immediately before the fix.
2. Build the assertions-on image at that parent, against the `firtool-*` release whose pin matches it.
   Only the 171 exact-pin seeds are eligible, because a one-bump-off pairing is a hard build failure
   at target 2 of 1030 (C-01), not a degradation.
3. Run the seed's **own test's** `RUN:` line, normalised by `corpus.normalise_run_line`, against the
   test file the fix's commit **added or modified**, taken at the fix commit, so the input is the one
   the fix was written to make pass.
4. Keep the pair when the run fires the primary oracle at the parent. A seed whose test passes at the
   parent is discarded and the discard is recorded, because the corpus filter is a subject-keyword
   proxy and A-02 records that neither 187 nor 171 was validated by reading diffs.

**Source B, closed `label:bug` issues with reproducers.** From the mirror, which holds 487 closed and
101 open `label:bug` issues (M9), take closed issues whose body carries a fenced code block and a tool
name, which is the shape CHIA's own triage already selects on
(`chia:examples/circt_issue_solver/triage.py:20-85`). Resolve the linked fix commit through
`GithubIssuesNode.linked_pull_requests`, take its first parent, and run the body's reproducer there.
Source B is used to fill any shortfall and to reach classes Source A underproduces, in particular
`fatal_error`, which is a deliberate refusal path and is unlikely to be the subject of a fix commit.

**The target composition** is at least one of each of the three classes: `assertion`, `crash` and
`fatal_error`. That is F-07's feature acceptance read literally, "classifies each into the right one
of the three classes".

### 5.2 The acceptance: what a fixture directory holds

One directory per recorded failure, under `fixtures/oracle/<class>_<nn>/`, committed, each holding
exactly these files and no others:

| File | Content |
|---|---|
| `input.<ext>` | the input, verbatim, extension by language |
| `argv.json` | the full argument vector, tool first, `prlimit` prefix excluded |
| `commit.json` | `{"circt_sha", "parent_of", "sdk_tag", "llvm_pin", "source"}`, where `source` is `seed` or `issue:<number>` |
| `expected.json` | `{"class", "assertion_text", "assertion_site", "top_frames", "exit_status", "signal"}` |
| `stderr.txt` | the recorded stderr, verbatim, decoded with `errors="backslashreplace"` |
| `README.md` | one paragraph: where it came from, why it is in the set, and which class it covers |

`expected.json`'s `assertion_text` and `assertion_site` are present for the `assertion` class and null
otherwise; `top_frames` holds the `fingerprint_top_n` (5) normalised frame function names for the
`crash` and `fatal_error` classes and is recorded as evidence for `assertion` too.

### 5.3 The tests

| Test | Behaviour | Tier | FR |
|---|---|---|---|
| the oracle tests of §1.9, `T-U-probe-19` through `T-U-probe-26` | no new identifier: each is run once per fixture directory, parameterised by `pytest.mark.parametrize` over the set, so the set's size is a count of parameter cases and not of tests | T2 | FR-07.1 to FR-07.7 |

The parameterised run asserts, per fixture: the oracle **fires**; the class equals `expected.class`;
for an `assertion` the extracted text and `file:line` equal `expected`'s character for character; for
a `crash` or `fatal_error` the top-5 normalised frame names equal `expected.top_frames`; and
`repro_command`, re-run inside the same image, reproduces the same exit status and the same assertion
text.

### 5.4 Re-verification when the image changes

The fixtures are pinned to **commits**, not to the campaign's image, so they are re-verified rather
than re-recorded whenever the image changes. The rule, run as part of tier 2:

1. A fixture is valid only inside an image built at its own `commit.json.circt_sha` against its own
   `sdk_tag`. `T-U-probe-19`'s parameterised run **skips** a fixture whose commit is not the running
   image's, and records the skip, rather than passing vacuously.
2. When the campaign's image commit changes, every fixture is re-run at its own commit in its own
   image; the set's five images are built once and cached by digest, which is B1's idempotency key.
3. A fixture that no longer fires at its own commit is a defect in the fixture or in the oracle, never
   in the image, and it blocks the tier-2 suite until the cause is named.
4. `expected.json` is **never** edited to match a new observation. A changed observation is recorded as
   a new fixture directory beside the old one, and the old one is struck through in this document's
   §13 inventory with the date and the reason.

---

## 6. The reducer against the same fixtures

Every fixture of §5 is also a reducer fixture, which is `01-FRD.md` §10.3 item 6. F-09's feature
acceptance asks for at least `acceptance.recorded_crashes_for_reduction`, which is 3 `[DEFAULT]`,
covering at least one MLIR-text probe and one `.fir` probe.

| Test | Behaviour | Tier | FR |
|---|---|---|---|
| the reducer tests of §1.9, `T-U-probe-31` through `T-U-probe-38` | no new identifier: each is run once per §5 fixture, parameterised over the set | T2 | FR-09.1 to FR-09.13 |

Per fixture, the parameterised run asserts:

- **The class is preserved.** The reduced case's re-checked `OracleVerdict.oracle_class` equals the
  original's.
- **The assertion text and `file:line` are preserved**, character for character, where the class is
  `assertion`; and the top-5 frame names where it is `crash` or `fatal_error`.
- **A fixpoint is reached.** `ReducedCase.fixpoint` is true and `budget_truncated` false, with
  `reduction_wall_seconds` raised for the fixture run where 60 s is not enough; the raised value is a
  fixture parameter and is recorded in the fixture's `README.md`, never in `budget.yaml`.
- **Size decreases.** `size_after_bytes < size_before_bytes` and `size_after_ops <= size_before_ops`.
- **The lift path is exercised** for `.fir` and `.sv` fixtures: `ReducedCase.lift` names
  `firtool --ir-fir`, `firtool --parse-only` or `circt-verilog --ir-moore`, and the lift's output is
  the file `circt-reduce` actually read, asserted on the recorded argv. At least one `.fir` and one
  `.sv` fixture is in the set for this reason.
- **The textual reducer on a parser-stage crash.** One fixture is a `.fir` input whose failure is in
  the `.fir` parser, so both lifts fail and no MLIR ever exists; `ReducedCase.reducer` is
  `textual-ddmin`, `lift` is null, the same interestingness script drives it, and
  `interestingness_calls` is recorded. This is the fixture `T-E-input-14` also uses.

The interestingness script is the one `03-LLD.md` §10.2 fixes, written per fixture with its own
`@ASSERT_EXPR@`, `@ASSERT_SITE@`, `@FATAL_MESSAGE@` or `@TOP_FRAME@` substituted and shell-quoted; the
script's own polarity, `timeout` wrapper and `prlimit` prefix are asserted on the written file before
the reduction runs.

---

## 7. A test for every error and edge requirement of `01-FRD.md` §5, by ID

Sixty-nine requirements sit in the "Error and edge requirements" block of a feature; F-20 has no such
block. One is withdrawn, so sixty-eight are live and each has at least one test. The behaviour column
is the edge, not the requirement's whole text.

| FR | The edge | Test |
|---|---|---|
| FR-01.8 | clone lacks the `firtool-*` tags; the refspec is named and is passed as an argv element | `T-U-corpus-15` |
| FR-01.9 | a seed with no `RUN:` line: empty list, excluded from the seeded draw, counted | `T-U-corpus-17` |
| FR-01.10 | the six normalisation steps and the `unsupported` exclusion | `T-U-corpus-07` to `T-U-corpus-14`, `T-U-corpus-20` |
| FR-01.11 | clone HEAD moved: exit non-zero naming both SHAs | `T-U-corpus-16`, `T-U-driver-03` |
| FR-01.12 | ordered test paths, never collapsed | `T-U-corpus-18` |
| FR-02.5 | no match in 24 months: exit non-zero, never widen | `T-U-pin-05` |
| FR-02.6 | several tags share a pin: newest by tag date, all recorded | `T-U-pin-06` |
| FR-02.7 | `run_commit` per mode, one field and no other | `T-U-schema-15`, `T-S-disc-01`, `T-S-calib-01` |
| FR-03.11 | the report states the flag, because `--version` still says "Optimized build." | `T-U-image-11` |
| FR-03.12 | MLIR and LLVM assertions stay off | `T-U-image-12` |
| FR-03.13 | a broken target publishes no partial image | `T-U-image-13` |
| FR-03.14 | both slang entry points, or the 36-seed exclusion recorded | `T-U-image-14` |
| FR-03.15 | one Verilator version; a change starts a new campaign | `T-U-image-15`, `T-U-driver-08` |
| FR-03.16 | tool hashes from the published image | `T-U-image-16`, `T-U-probe-01` |
| FR-03.17 | `MLIR_SOURCE_DIR` and zero lit discovery errors | `T-U-image-17`, `T-U-driver-06` |
| FR-04.7 | a non-exact seed generates but is never a build commit | `T-U-driver-09`, `T-S-calib-01` |
| FR-04.8 | a failed turn is recorded, charged and survived | `T-U-gen-06`, `T-U-gen-07` |
| FR-04.9 | stage 2 does not validate syntax; stage 3 records `parse_error` | `T-U-probe-03` |
| FR-05.6 | a no-op mutant costs no input-cap budget | `T-U-mut-03` |
| FR-05.7 | a raising mutator is attributed and survived | `T-U-mut-04` |
| FR-05.8 | the synthesis declaration, in the artefact and the paper | `T-U-msyn-03`, `T-U-results-11` |
| FR-06.6 | `parse_error` distinct from a crash | `T-U-probe-03` |
| FR-06.7 | `oom` by evidence, never `crash` | `T-U-probe-08`, `T-U-probe-10`, `T-U-probe-11`, `T-U-probe-12` |
| FR-06.8 | side-effect free with respect to the CIRCT tree | `T-U-probe-37`, `T-U-gen-11` |
| FR-06.9 | exactly seven statuses and no other | `T-U-probe-02` to `T-U-probe-08`, `T-U-schema-05` |
| FR-07.8 | a timeout or an OOM never fires | `T-U-probe-09`, `T-U-probe-19` |
| FR-07.9 | the control set and its false-positive rate | `T-S-lit-01` (§9) |
| FR-07.10 | a `fatal_error` is worded as a refusal, never a crash | `T-U-triage-24` |
| FR-08.8 | `harness_failure` names the failing arm | `T-U-probe-28` |
| FR-08.9 | `diverge_x_policy` excluded from the count | `T-U-probe-29` |
| FR-08.10 | the informational report; no gate, no filing, no reducer | `T-U-triage-24`, `T-U-gate-19`, `T-U-results-19` |
| FR-08.11 | the reused driver or a recorded deviation with its obstacle | `T-U-schema-08` (the `differential_driver` key set), `T-U-probe-30` |
| ~~FR-09.6~~ | **WITHDRAWN** in `01-FRD.md`; replaced by FR-09.12 | none |
| FR-09.7 | `reduction_changed_failure`, original carried forward | `T-U-probe-33`, `T-U-gate-08` |
| FR-09.8 | no reducer for a `differential` candidate | `T-U-store-09`, `T-U-gate-19` |
| FR-09.9 | the four-branch selection rule | `T-U-probe-31`, `T-E-input-11` to `T-E-input-14` |
| FR-09.10 | the textual ddmin reducer | `T-U-ddmin-01` to `T-U-ddmin-08` |
| FR-09.11 | the reducer named and the fixpoint flag | `T-U-probe-38` |
| FR-09.12 | `reduced=false` proceeds, is counted, and is refused at question 2 | `T-U-probe-34`, `T-U-gate-07` |
| FR-09.13 | the script's own `timeout` and rlimits; post-exit output validation | `T-U-probe-36`, `T-U-core-09` |
| FR-10.7 | `dedup_unavailable` fails question 4 | `T-U-triage-14`, `T-U-gate-14` |
| FR-10.8 | `dedup_basis=insufficient` merges nothing | `T-U-triage-05`, `T-U-gate-14` |
| FR-10.9 | the once-per-run bounded mirror, `fetch_comments=False` | `T-U-triage-10` to `T-U-triage-13`, `T-U-driver-10` |
| FR-11.8 | `untriaged` still receives four answers, then is held | `T-U-gate-15`, `T-U-appr-04` |
| FR-11.9 | the differential template, stored and never filed | `T-U-triage-24` |
| FR-12.8 | `lit_ok=false` attaches no patch; zero discovered is `lit_unusable` | `T-U-repair-11`, `T-U-repair-12` |
| FR-12.9 | the six prompts byte-identical | `T-U-repair-08` |
| FR-12.10 | loop row first; `repair_row_missing` on reconciliation | `T-U-repair-14`, `T-U-driver-18` |
| FR-12.11 | a repair-only worker, restored after every attempt | `T-U-repair-13`, `T-S-isolate-01` |
| FR-13.11 | a refused candidate is persisted in full | `T-U-gate-18` |
| FR-13.12 | the four elements in one view | `T-U-appr-09` |
| FR-13.13 | approval per report, never generalised | `T-U-appr-05`, `T-U-appr-06` |
| FR-13.14 | a `differential` candidate never enters the gate | `T-U-gate-19` |
| FR-13.15 | the three parse-and-verify commands and the three outcomes | `T-U-gate-10` to `T-U-gate-13` |
| FR-13.16 | the poll on the fingerprint, falling back to the paste | `T-U-appr-13` |
| FR-13.17 | the 6,000-character limit and the fallback | `T-U-appr-10` |
| FR-13.18 | one interface owns both the approval and the URL | `T-U-appr-11`, `T-U-appr-12` |
| FR-14.7 | a mid-campaign budget change invalidates the campaign | `T-U-budget-08`, `T-U-driver-16` |
| FR-14.8 | an unmeterable stage is declared, never omitted | `T-U-ledger-08`, `T-U-driver-20` |
| FR-15.5 | the 16 non-exact seeds are still screenable | `T-U-triage-20` |
| FR-16.6 | abandonment after two identical stage-3 iterations | `T-U-feed-03`, `T-U-feed-04` |
| FR-17.7 | over the cap goes to disk and is referenced by path | `T-U-store-03`, `T-U-schema-09`, `T-U-schema-17` |
| FR-17.8 | the `PARTIAL` marker, never deleted | `T-U-store-04`, `T-U-store-05` |
| FR-17.9 | one identical absolute path on head and workers | `T-U-driver-05`, `T-S-artefact-01` |
| FR-18.10 | each arm stops at its own window or cap; both windows reported | `T-U-ledger-06`, `T-U-results-13`, `T-S-pilot-01` |
| FR-18.11 | a non-regenerable row is marked, not reported | `T-U-results-14`, `T-S-regen-01` |
| FR-18.12 | the divergences-observed list | `T-U-results-10`, `T-U-results-19` |
| FR-19.8 | no dependency added without a licence check | `T-U-layout-05` |
| FR-19.9 | no governance file touched | `T-N-nfr11-01` |

---

## 8. A test for every non-functional requirement, by ID

Fifteen tests over twelve requirements.

| Test | NFR | What is run | Pass criterion | Tier |
|---|---|---|---|---|
| `T-N-nfr01-01` | NFR-01 re-run equality | Three rows `[DEFAULT]` drawn at random from the pilot's results table are re-run through `chia job submit` under NFR-01's definition | Every **tool** stage re-executes from its stored inputs; every **agent turn** replays from its stored transcript through CHIA's bypass; every re-executed verdict equals the stored one; the run record names which stages were re-executed and which turns were replayed; a tool stage served from bypass fails the test | T3 |
| `T-N-nfr02-01` | NFR-02 determinism, stages 3 and 4 | One probe re-run ten times `[DEFAULT]` in the same image | `BuildResult.status`, `OracleVerdict.oracle_class`, the assertion text and `file:line`, the primary fingerprint and both evidence fields are identical every time; `wall_seconds` and `peak_rss_bytes` are exempt and are recorded as non-deterministic | T2 |
| `T-N-nfr02-02` | NFR-02 determinism, stage 5 | One reduction that completes inside its budget, re-run ten times `[DEFAULT]` | The reduced case is byte-identical every time; a budget-truncated reduction carries `budget_truncated=true` and `fixpoint=false` and is **not** required to be reproducible | T2 |
| `T-N-nfr03-01` | NFR-03 isolation, the tool list | The tool list handed to every model turn | Stage 1 and stage 2 receive literally `[bash, probe_write]`; stage 6 receives no tool that computes a measured result; no build, lit, oracle, reducer or dedup tool appears in any list, asserted by grepping the constructed lists | T0 |
| `T-N-nfr03-02` | NFR-03 isolation, the numbers | Every numeric field of the rendered results artefact and of every rendered report | Each traces, field by field, to a tool-produced record in `loop.db`; the check walks `results.json` and `report.md`'s substitution points and asserts that no value's provenance is a model transcript. Gate precision's denominator is tool-derived because no gate question reads the triage class (`T-U-gate-15`) | T0 |
| `T-N-nfr04-01` | NFR-04 GitHub access | A full dry-run campaign under a **recording HTTP layer**: a `requests` transport adapter mounted by the test harness on `GithubClient._session`, through `unittest.mock.patch` of the constructor, which appends `(method, url, status)` to `<artefact_root>/<run>/github_trace.jsonl` before delegating. Both GitHub-touching components, B6a's mirror and B9a's poll, are head nodes, so one adapter covers the whole loop | The trace contains **only** `GET` requests to `api.github.com`, and none at all during screening; and a corroborating `ast` search over the loop's modules finds no `requests` verb other than `get` and no `GithubClient` method outside the read list. The adapter is test-harness code, so no production dependency and no production change is introduced | T3 |
| `T-N-nfr05-01` | NFR-05 isolation and limits | A probe that exceeds its own address-space rlimit, on a worker whose container also carries CPU and memory limits | The cluster YAML's `run_options` for both CIRCT types carry the container CPU and memory flags; the probe's own `prlimit` limits are set in the child; the probe is recorded `oom` **and the worker stays up**, answering a trivial `@ChiaFunction` afterwards; the task is not silently re-queued, `max_retries=0` making a worker death a task failure with a driver-written `ProbeResult` | T3 |
| `T-N-nfr06-01` | NFR-06 no secrets | A `grep` of the whole artefact tree, every prompt file, every transcript, `loop.db`, `issues.db` and the job's metadata for the `GITHUB_TOKEN` value and for any model API key | Zero hits everywhere, including `chia job` output and the dashboard's `runtime_env`; the token's only home is one 0600 file on the head, read by two head nodes and passed as `GithubClient(token=...)`; no worker container mounts it and no cluster YAML mentions it | T3 |
| `T-N-nfr07-01` | NFR-07 least privilege | The loop's environment and its code | Exactly **one** GitHub credential exists, it carries public read scope only, a write attempt with it fails, and a search of the loop's code finds no non-GET call to `api.github.com`. No write-scoped credential exists anywhere | T3 |
| `T-N-nfr08-01` | NFR-08 cost caps | The pilot's ledger against the cluster's own accounting | Neither arm exceeds `arm_window_seconds` on the primary unit, nor either safety cap; the post-run reconciliation of the ledger against the cluster's accounting closes; tokens and money are reported beside the result and are not what the campaign is capped on | T3 |
| `T-N-nfr09-01` | NFR-09 observability | `chia job logs <id>` and the metrics directory **during** a running pilot | Driver output is retrievable while the run is in flight, the metrics directory shows per-stage counters while the run is in flight, and every stage has emitted at least one log and one counter; inspecting neither stops the run | T3 |
| `T-N-nfr10-01` | NFR-10 single machine, the Must | The whole pilot on `cluster_single.yaml` | The loop's entry point runs end to end on one host, and `RunManifest.deployment` records `single_machine` | T3 |
| `T-N-nfr10-02` | NFR-10 GCP, the Should | `cluster_gcp.yaml`, **only** where ADR-D-14's named date is met | The same three worker types, resource names and images; no loop code differs; `deployment` records `gcp`. Skipped, with the skip recorded, where the credits were not confirmed | T3 |
| `T-N-nfr11-01` | NFR-11 licensing | The pull request and the approval record | The pull request states BSD-3-Clause for code contributed to CHIA and touches none of `STEERING_COMMITTEE.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `README.md`, `SECURITY.md`, `CONTRIBUTING.md`; the approval step records Apache-2.0 with LLVM exceptions for any offered patch; the Python dependency list is unchanged and util-linux is invoked as a process, never imported or linked | T0 |
| `T-N-nfr12-01` | NFR-12 documentation | Every added node, tool, prompt and Dockerfile | `T-U-layout-03`'s docstring check passes, `T-U-layout-01`'s test-layout check passes, the commits carry `Assisted-by:` and `Signed-off-by:`, and the example directory carries a README of the same shape as CHIA's | T0 |

---

## 9. The control run of FR-07.9

`T-S-lit-01`. The whole lit suite, under the assertions-on image, at the run's commit, reporting the
assertion false-positive set.

**What is run.** `lit --no-progress-bar --filter-out=circt-tblgen <paths>` with `cwd` the build
directory, which is the invocation shape `chia:chia/chipyard/circt.py:698-762` already uses, over
CHIA's own exclusions: `test/CAPI` dropped wholesale and `--filter-out=circt-tblgen`
(`chia:examples/circt_issue_solver/circt_util.py:151-159`). It runs **twice**, against two builds of
the same source tree differing only in the flag string of FR-03.4.

**The precondition.** `T-U-image-17` must pass first. Two empty failing sets compare equal, so a
discovery abort would make this run report a false zero. That is not hypothetical: M3's first attempt
ran CHIA's rule verbatim and lit exited **2 after 0 s with zero tests run**, because
`test/Tools/circt-tblgen/lit.local.cfg` raises during discovery and `--filter-out` is applied after
it. `-DMLIR_SOURCE_DIR=/opt/circt-sdk` is the fix and FR-03.17 is the requirement.

**What is reported**, into `<artefact_root>/<run>/image/`:

| Reported | Measured at `5056ff0445` (M3) |
|---|---|
| tests discovered | 1,127 |
| passed | 1,058 (93.88%) |
| unsupported | 63 (5.59%), of which **62 are `REQUIRES: slang`** and 1 `REQUIRES: zlib` |
| expectedly failed | 6 (0.53%) |
| **failed, unresolved, timed out or unexpectedly passed** | **0 under either flag string** |
| **the assertion false-positive set** | **empty**: 0 of 1,127 |
| lit exit code | 0 |

**The plan re-runs it inside the image at the run's commit.** M3's zero was measured on the host, at
commit `5056ff04450b`, against `bassert_g` and a `-DNDEBUG` tree; it is not the campaign's commit and
not the campaign's image. `T-S-lit-01` therefore repeats it, and its pass criterion is that the set is
**reported**, not that it is zero. A non-empty set names every test in it and blocks publication of
the image (FR-03.6).

**What the zero does not cover**, recorded beside it because A-04's status depends on it: of the 1,127
discovered, 1,050 (93.2%) name at least one binary built from source with assertions on, 75 name only
tools resolving from the SDK, where assertions are off and nothing can fire, and 2 name no recognised
tool. Under ADR-D-13 branch (a) the 62 `REQUIRES: slang` tests become runnable and the counts move;
the run records both the discovered count and the unsupported count, so the movement is visible.

---

## 10. The labelled duplicate-pair set of FR-10.2

At least `budget.yaml`'s `acceptance.labelled_pairs`, which is 20 `[DEFAULT]`, hand-labelled pairs.

**How they are constructed.** From the §5 fixture set and from the probes the pilot's own runs
produce, never synthesised from scratch, so the pairs are drawn from the distribution the metric is
computed over. Four construction rules, each producing at least four pairs:

| Rule | Construction | Label |
|---|---|---|
| R1, same bug, different input | Take one recorded failure, reduce it, then re-derive a byte-different input that fires the same assertion at the same `file:line` by renaming SSA values and reordering independent operations | **duplicate** |
| R2, same bug, different arm | The same failure reached once from a seeded probe and once from a mutation probe | **duplicate** |
| R3, different bug, same file | Two failures whose assertion sites are different lines of one source file, or whose top frame is one function but whose second frame differs | **distinct** |
| R4, different bug, colliding structure | Two failures whose reduced cases share a structural hash because reduction drove both towards the same small module, but whose assertion text or frame tuple differs | **distinct** |

R4 is the rule that earns its place: it is the case FR-10.8's rationale names, where the structural
hash alone would have merged distinct bugs. At least four of the twenty are R4 pairs.

**Labelling.** Each pair is labelled by reading both failures' root cause from the CIRCT source at the
recorded commit, and the label plus its one-sentence justification is committed in
`fixtures/dedup/pairs/<nn>.json` beside the two candidate ids. The label is a human judgement recorded
**before** the fingerprint is computed, and the file records the labelling date; that ordering is what
makes the rates a measurement rather than a restatement.

**What is reported.** `T-U-triage-09` computes and prints, and `T-U-results-09` asserts they appear
beside the headline they qualify:

- **collision rate**: pairs labelled **distinct** whose primary fingerprints are equal, over all
  distinct-labelled pairs;
- **false-merge rate**: pairs labelled **duplicate** whose primary fingerprints differ, over all
  duplicate-labelled pairs.

Neither rate is known today (A-05). The acceptance is that both are measured and reported, with the
labelled set committed, and **not** that either meets a threshold.

---

## 11. The regeneration check of FR-18.11, over every results row

`T-S-regen-01`, run over **every** row of the pilot's results table, not a sample. NFR-01's definition
of re-running is the definition used, and the two halves of it are not interchangeable.

| Stage kind | How it is regenerated | Why |
|---|---|---|
| Tool stage: B2, B3, B4, B5, B6b, B9a, B9b | **Re-executed** from its stored inputs: the probe input, `argv.json`, the `ImageSpec` and the limits, inside an image of the recorded digest | Bypass "replaces the real computation with pre-recorded data" (`chia:chia/base/bypass.py:3-5`), so a bypassed tool stage evidences that the row was **stored**, not that it **reproduces** |
| Agent turn: A3's two, B7's one, B8's chain | **Replayed** from its stored transcript through CHIA's bypass, with a bypass provider registered against the turn's cache tag | A model turn is not deterministic and NFR-01 asks for a deterministic replay, which is exactly what bypass gives |

**The procedure.** For each row: read its `run_manifest_id`, `artefact_dir` and stage records; start
the image at the recorded digest; re-execute every tool stage in order; replay every agent turn;
compare each regenerated verdict to the stored one by the fields NFR-02 declares deterministic, which
excludes `wall_seconds` and `peak_rss_bytes`. A row whose every comparison holds is **regenerated**; a
row with any failure is **marked** in the results artefact and its reason recorded, and it is not
reported as a result.

**The two ways a row legitimately fails**, both marked rather than treated as defects: a reduction
carrying `budget_truncated=true`, which NFR-02 explicitly exempts; and a row whose image digest is no
longer available, which is recorded as `image_unavailable` and is a retention failure rather than a
reproducibility one.

**The acceptance.** The check runs over every row, the marked count is printed beside the table, and a
test asserts that a row served from bypass on a tool stage is never counted as regenerated.
`T-U-results-14` is the unit half, driven from a store fixture with one deliberately unregenerable
row; `T-S-regen-01` is the live half.

---

## 12. Traceability

### 12.1 Every functional requirement to at least one test

All 198 requirement identifiers of `01-FRD.md`, in order. `T-U-` prefixes are dropped inside the
cells; a `T-I-`, `T-S-`, `T-N-` or `T-E-` id is written in full. An FR with no test would be a defect
in this plan; there is none.

| FR | Tests | FR | Tests |
|---|---|---|---|
| FR-01.1 | corpus-01, corpus-02 | FR-01.2 | corpus-06 |
| FR-01.3 | corpus-06 | FR-01.4 | corpus-05 |
| FR-01.5 | corpus-03 | FR-01.6 | corpus-19, schema-11 |
| FR-01.7 | corpus-04 | FR-01.8 | corpus-15 |
| FR-01.9 | corpus-17 | FR-01.10 | corpus-07 to corpus-14, corpus-20, schema-16 |
| FR-01.11 | corpus-16, driver-03 | FR-01.12 | corpus-18, mut-08 |
| FR-02.1 | pin-01, pin-08, driver-09 | FR-02.2 | pin-02, pin-03, results-07 |
| FR-02.3 | pin-04, driver-09 | FR-02.4 | pin-07, pin-08 |
| FR-02.5 | pin-05 | FR-02.6 | pin-06 |
| FR-02.7 | schema-15, T-S-disc-01, T-S-calib-01 | FR-03.1 | image-01 |
| FR-03.2 | image-02 | FR-03.3 | image-03 |
| FR-03.4 | image-04, core-12 | FR-03.5 | image-05 |
| FR-03.6 | image-06, T-S-lit-01 | FR-03.7 | image-07 |
| FR-03.8 | image-08, cluster-05 | FR-03.9 | image-09, cluster-01, T-S-cluster-01 |
| FR-03.10 | image-10 | FR-03.11 | image-11, triage-23 |
| FR-03.12 | image-12 | FR-03.13 | image-13 |
| FR-03.14 | image-14 | FR-03.15 | image-15, driver-08 |
| FR-03.16 | image-16, probe-01, driver-07, T-S-isolate-01 | FR-03.17 | image-17, driver-06 |
| FR-04.1 | gen-05, prompt-04 | FR-04.2 | gen-03, gen-14 |
| FR-04.3 | gen-04, schema-01 to schema-03, schema-10, schema-12, driver-15, T-I-gen-app-01 | FR-04.4 | gen-01, T-N-nfr03-01 |
| FR-04.5 | gen-02 | FR-04.6 | gen-08, prompt-06 |
| FR-04.7 | driver-09, T-S-calib-01 | FR-04.8 | gen-06, gen-07, prompt-01, prompt-02 |
| FR-04.9 | probe-03 | FR-05.1 | mut-05, mut-08 |
| FR-05.2 | mut-01, mut-09, msyn-01, msyn-02, msyn-04, msyn-05, budget-07, driver-02 | FR-05.3 | mut-02, mut-07, schema-06 |
| FR-05.4 | gen-10, T-I-gen-app-02, T-I-gen-app-03 | FR-05.5 | mut-06 |
| FR-05.6 | mut-03 | FR-05.7 | mut-04 |
| FR-05.8 | msyn-03, mut-09, results-11 | FR-06.1 | probe-01, probe-13, probe-14, core-01, core-06, core-07, gate-22, driver-07 |
| FR-06.2 | probe-14, core-01, core-02, T-N-nfr05-01 | FR-06.3 | core-03 |
| FR-06.4 | probe-09, probe-15, core-04, core-05, schema-07, schema-14 | FR-06.5 | probe-26, store-07 |
| FR-06.6 | probe-03 | FR-06.7 | probe-08, probe-10, probe-11, probe-12 |
| FR-06.8 | probe-37, gen-11, gen-12 | FR-06.9 | probe-02 to probe-08, schema-05 |
| FR-07.1 | probe-16, probe-17, probe-18, probe-19 | FR-07.2 | probe-04, probe-05, probe-06, probe-12, probe-21 |
| FR-07.3 | probe-16, probe-20, schema-18 | FR-07.4 | probe-22, probe-23, core-10 to core-13 |
| FR-07.5 | probe-24 | FR-07.6 | probe-25 |
| FR-07.7 | probe-26 | FR-07.8 | probe-09, probe-19 |
| FR-07.9 | T-S-lit-01 | FR-07.10 | triage-24 |
| FR-08.1 | probe-27, probe-30 | FR-08.2 | probe-30 (see §16 item 2) |
| FR-08.3 | probe-30, schema-08 | FR-08.4 | probe-30 |
| FR-08.5 | repair-05, store-09 | FR-08.6 | triage-24 |
| FR-08.7 | triage-24 | FR-08.8 | probe-28 |
| FR-08.9 | probe-29 | FR-08.10 | triage-24, gate-19, results-19, repair-05, store-09 |
| FR-08.11 | schema-08, probe-30 | FR-09.1 | probe-33, §6's parameterised run |
| FR-09.2 | probe-32, core-08 | FR-09.3 | probe-33 |
| FR-09.4 | probe-38, core-09 | FR-09.5 | probe-38 |
| ~~FR-09.6~~ | **WITHDRAWN** | FR-09.7 | probe-33, gate-08 |
| FR-09.8 | store-09, gate-19 | FR-09.9 | probe-31, T-E-input-11 to T-E-input-14 |
| FR-09.10 | ddmin-01 to ddmin-08 | FR-09.11 | probe-38 |
| FR-09.12 | probe-34, probe-35, gate-07 | FR-09.13 | probe-36, core-09 |
| FR-10.1 | triage-01 to triage-06 | FR-10.2 | triage-06 to triage-09, results-09 |
| FR-10.3 | triage-15, triage-16, T-I-app-tri-01 | FR-10.4 | triage-18 |
| FR-10.5 | triage-17 | FR-10.6 | triage-02, store-01 |
| FR-10.7 | triage-13, triage-14, gate-14 | FR-10.8 | triage-05, gate-14 |
| FR-10.9 | triage-10 to triage-13, driver-10 | FR-11.1 | triage-22, prompt-04 |
| FR-11.2 | triage-21, T-I-app-tri-02 | FR-11.3 | triage-23, T-I-app-tri-02 |
| FR-11.4 | triage-23, T-N-nfr03-02 | FR-11.5 | prompt-05 |
| FR-11.6 | triage-24 | FR-11.7 | prompt-06 |
| FR-11.8 | gate-15, appr-04, prompt-01, prompt-02 | FR-11.9 | triage-24 |
| FR-12.1 | repair-07, repair-15, driver-17, T-I-tri-rep-01 | FR-12.2 | repair-01, repair-02, schema-15 |
| FR-12.3 | repair-03, repair-04, T-I-tri-rep-01 | FR-12.4 | repair-05, T-I-tri-rep-02 |
| FR-12.5 | repair-06, T-I-tri-rep-02 | FR-12.6 | repair-09 |
| FR-12.7 | repair-10, T-I-rep-gate-01 | FR-12.8 | repair-11, repair-12, T-I-rep-gate-01 |
| FR-12.9 | repair-08 | FR-12.10 | repair-14, store-08, driver-18 |
| FR-12.11 | repair-13, cluster-02, layout-06, T-S-isolate-01 | FR-13.1 | gate-01, gate-05, T-I-rep-gate-02 |
| FR-13.2 | gate-02, gate-03, gate-04, gate-21 | FR-13.3 | gate-06 to gate-09 |
| FR-13.4 | gate-15 | FR-13.5 | gate-14 |
| FR-13.6 | gate-16, repair-11, T-I-rep-gate-01 | FR-13.7 | appr-08, appr-12, appr-14 |
| FR-13.8 | appr-01, appr-02 | FR-13.9 | appr-03 |
| FR-13.10 | gate-17, T-I-gate-appr-01 | FR-13.11 | gate-18 |
| FR-13.12 | appr-09, T-I-gate-appr-01 | FR-13.13 | appr-05, appr-06 |
| FR-13.14 | gate-19, results-17 | FR-13.15 | gate-10 to gate-13 |
| FR-13.16 | appr-13, triage-23 | FR-13.17 | appr-10 |
| FR-13.18 | appr-11, appr-12, T-I-gate-appr-02 | FR-14.1 | budget-01 to budget-03, budget-10, byaml-01 to byaml-03 |
| FR-14.2 | budget-04, budget-05, driver-01 | FR-14.3 | budget-06 |
| FR-14.4 | ledger-01 to ledger-07, ledger-09, T-I-ledger-01 | FR-14.5 | budget-10, ledger-03, cluster-03, results-12, T-S-pilot-01 |
| FR-14.6 | ledger-08, schema-06 | FR-14.7 | budget-08, driver-16 |
| FR-14.8 | ledger-08, driver-20, schema-08 | FR-15.1 | triage-19, triage-20 |
| FR-15.2 | triage-20, results-05 | FR-15.3 | results-06 |
| FR-15.4 | results-06 | FR-15.5 | triage-20 |
| FR-16.1 | feed-01, feed-02, feed-06, fixt-02, schema-12, T-I-feed-01 | FR-16.2 | gen-09, T-I-feed-02, T-I-gen-app-03 |
| FR-16.3 | feed-07 | FR-16.4 | feed-05, budget-09, T-I-ledger-02 |
| FR-16.5 | feed-08, prompt-03, T-I-feed-02 | FR-16.6 | feed-03, feed-04 |
| FR-17.1 | store-01, store-07, T-S-disc-01 | FR-17.2 | store-01, store-07 |
| FR-17.3 | store-02 | FR-17.4 | driver-20 |
| FR-17.5 | store-10, submit-01, T-N-nfr06-01 | FR-17.6 | store-06 |
| FR-17.7 | store-03, schema-09, schema-17 | FR-17.8 | store-04, store-05 |
| FR-17.9 | driver-04, driver-05, cluster-04, submit-02, T-S-artefact-01 | FR-18.1 | layout-02, results-18, T-I-gen-app-02 |
| FR-18.2 | results-04, results-20, T-S-pilot-01 | FR-18.3 | results-01 |
| FR-18.4 | results-02, T-S-pilot-01 | FR-18.5 | results-03, T-S-calib-01 |
| FR-18.6 | gate-18, gate-20, results-17, T-S-disc-01 | FR-18.7 | results-15 |
| FR-18.8 | results-08 | FR-18.9 | results-16 |
| FR-18.10 | ledger-06, results-13, driver-13, T-S-pilot-01 | FR-18.11 | results-14, T-S-regen-01 |
| FR-18.12 | results-10, results-19 | FR-19.1 | layout-04, layout-06, gen-13 |
| FR-19.2 | core-01, core-08, core-10 | FR-19.3 | driver-12, driver-13, driver-14 |
| FR-19.4 | layout-03 | FR-19.5 | layout-01, the whole `core` module |
| FR-19.6 | T-N-nfr12-01 | FR-19.7 | store-07, T-N-nfr12-01 |
| FR-19.8 | layout-05 | FR-19.9 | T-N-nfr11-01 |
| FR-20.1 | driver-11 | FR-20.2 | appr-03, results-06 |
| FR-20.3 | triage-24, appr-12 | FR-20.4 | triage-11, triage-17 |
| FR-20.5 | appr-07, appr-12, T-N-nfr11-01 | FR-20.6 | appr-14, submit-03 |

### 12.2 Every non-functional requirement, and the reverse index

| NFR | Tests |
|---|---|
| NFR-01 | `T-N-nfr01-01`, `T-S-regen-01` |
| NFR-02 | `T-N-nfr02-01`, `T-N-nfr02-02`, `T-U-schema-11`, `T-U-probe-38` |
| NFR-03 | `T-N-nfr03-01`, `T-N-nfr03-02`, `T-U-gen-01`, `T-U-gen-14`, `T-U-gate-15`, `T-U-triage-23` |
| NFR-04 | `T-N-nfr04-01`, `T-U-triage-15`, `T-U-appr-13` |
| NFR-05 | `T-N-nfr05-01`, `T-U-cluster-04`, `T-U-probe-08` |
| NFR-06 | `T-N-nfr06-01`, `T-U-store-10`, `T-U-submit-01`, `T-S-submit-01` |
| NFR-07 | `T-N-nfr07-01`, `T-U-cluster-05` |
| NFR-08 | `T-N-nfr08-01`, `T-U-ledger-06` |
| NFR-09 | `T-N-nfr09-01`, `T-U-submit-03`, `T-U-driver-20`, `T-S-submit-01` |
| NFR-10 | `T-N-nfr10-01`, `T-N-nfr10-02`, `T-U-cluster-01`, `T-U-cluster-06` |
| NFR-11 | `T-N-nfr11-01`, `T-U-layout-05`, `T-U-appr-07` |
| NFR-12 | `T-N-nfr12-01`, `T-U-layout-01`, `T-U-layout-03` |

**The reverse index** is the FR column of every table in §1 to §8 read as a mapping from test to
requirements, and `tests/test_traceability.py` generates it from this document and asserts three
things: every test id in this document is unique; every test id carries at least one FR or NFR;
and every FR of `01-FRD.md` other than the withdrawn FR-09.6 appears in §12.1. Nine tests trace to an
NFR and to no FR, and they are listed explicitly so the assertion can exempt them:
`T-N-nfr01-01`, `T-N-nfr02-01`, `T-N-nfr02-02`, `T-N-nfr03-01`, `T-N-nfr03-02`, `T-N-nfr04-01`,
`T-N-nfr05-01`, `T-N-nfr07-01`, `T-N-nfr08-01`.

### 12.3 Requirements testable only at system level

Thirty-one requirements cannot be discharged below tier 2, and the reason is stated for each rather
than implied. Two kinds appear: an **image** is the unit under test and has no in-process substitute,
or the property is about **scheduling, placement or a whole campaign** and a plain call to a
`@ChiaFunction` cannot exhibit it (§0.4).

| Requirement | Lowest tier | Why no unit test can discharge it |
|---|---|---|
| FR-03.1 to FR-03.17 (17 requirements) | T2 | The unit under test is a built image: a fetch-by-SHA, a cmake flag string, a stripped include tree, a linked `__assert_fail`, a lit discovery, an apt set and a published digest exist only once a Docker build has run. `T-U-image-10` and `T-U-image-11` are the two exceptions and are tier 0, because they read a recorded `ImageSpec` rather than an image |
| FR-03.9 | T3 | `chia up` bringing a worker to Ready and running a trivial node is a cluster property |
| FR-06.1, FR-06.2, FR-06.3 | T1 | A process group, an rlimit and an `execve` need a real child; `T-U-core-01` tests the argv construction at T0, but the limits reaching the child do not |
| FR-07.4 | T1 | Symbolisation needs a binary with `.debug_line` and the SDK's `llvm-symbolizer` |
| FR-07.9 | T2 | The control run is the whole lit suite inside the image |
| FR-12.11 | T3 | Isolating one worker type from another is a scheduling property: it needs two `bugloop_circt` workers and one `bugloop_repair` worker to exist at once |
| FR-13.2 | T3 | "A logical worker other than the one that produced the verdict, where the scheduler can grant it" needs a scheduler with more than one live `circt` node; `T-U-gate-03` tests the soft-pin construction and the truthful `same_worker=true` fallback at T0, but the granted case needs the cluster |
| FR-14.5 | T3 | Equal budget is an equality between two arms' elapsed windows, which exist only in a campaign |
| FR-17.9 | T3 | One identical absolute path on the head and on a worker is a bind-mount property of the running cluster |
| FR-18.2, FR-18.4, FR-18.5, FR-18.10 | T3 | Each is a property of a completed two-arm campaign; `results.py`'s refusal checks are unit-tested from a store fixture, but the store fixture itself comes from a campaign |
| FR-18.11 | T3 | Regeneration re-executes every tool stage of every row, which needs the image and the cluster |
| FR-20.1 | T3, and human | The forum post is an act a person performs; the loop can only check that the manifest records its URL and date, which `T-U-driver-11` does. The act itself is scheduled by `05-Work-Plan.md` |

Two further limits are recorded here rather than hidden. **FR-18.3's headline is not testable at all
by this plan**: "confirmed" is a maintainer's action (G-27), so `T-U-results-01` tests the counting
rule against a synthetic `FilingRecord` carrying a URL, and the real numerator depends on people
outside the system and on FR-18.8's cut-off date. And **FR-13.16's poll is tested against a recorded
issue body**, because a live test would require a real filing, which FR-13.7 forbids without a named
human's approval of that specific report.

---

## 13. Fixtures inventory

Every fixture directory, what it holds, how it is produced, its size and whether it is committed.
Sizes marked `[DEFAULT]` are chosen here, which is the home FR-14.1 gives a fixture size. The root is
`examples/circt_bug_loop/tests/fixtures/`, except the contract fixtures, which live under
`contract/fixtures/` because `02-HLD.md` §2.13 puts them there.

| Directory | Contents | Produced by | Size | Committed |
|---|---|---|---|---|
| `contract/fixtures/<schema>/` | one recorded instance per schema per shape: `seed_record/`, `budget_file/`, `probe_spec/` (seeded and mutation), `probe_result/`, `feedback_bundle/`, `ledger_entry/`, `run_manifest/` | `bug_loop.py --record-fixtures` on a pilot run; never hand-written | about 40 files, under 2 MB | yes |
| `contract/fixtures/malformed/` | one deliberately invalid instance per error code, plus `dicts/` with one bad key set per declared dict, plus `major.json` at MAJOR `2.0` | hand-derived from a valid fixture by one edit each, which is the one place a fixture is edited rather than recorded | about 25 files, under 200 kB | yes |
| `contract/fixtures/roundtrip/` | one instance of each of the seven members, plus a permutation driver | recorded | 7 files | yes |
| `fixtures/corpus/clone` | a blobless `llvm/circt` clone reset to `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` | `git clone --filter=blob:none`, then `git checkout --detach <sha>`, then `git fetch 'refs/tags/firtool-*'` with the refspec **quoted** | about 400 MB | **no**: fetched by `tests/fixtures/fetch_clone.sh`, whose expected HEAD SHA is committed |
| `fixtures/corpus/clone_notags` | the same clone with the tag refs removed | the same script with `--no-tags` | shares the object store | no |
| `fixtures/corpus/pin_window_raw.json` | `analysis/pin_window_raw.json`, verbatim: 63 windows, 1,103 shape candidates, 164 tags | copied from `analysis/`, never regenerated by a test | 687 kB | yes |
| `fixtures/corpus/runlines/` | one `RUN:` line per shape of FR-01.10: `not_*.txt` (the corpus's 2 real ones), `env.txt`, `splitfile.txt` (the corpus's 1), `pipe_*.txt` (one plain, one quoted), `subst_*.txt`, `unsupported_*.txt` (`;`, `&&`, backtick, `$(`, and a constructed `%{`), `cont.txt` | extracted from the clone by `m1_runlines.py`'s method, except the `%{` case, which is constructed because M1 measured zero occurrences | 14 files, under 10 kB | yes |
| `fixtures/pin/` | `pin_window_raw.json` (shared), plus `one_bump_off.json`, `no_tags.json`, `multi_tag.json` | derived from `pin_window_raw.json` by selecting rows; the derivation script is committed beside them | 4 files | yes |
| `fixtures/seed_record/` | one `SeedRecord` per shape, including the 9-test-file seed and one `sdk_exact=false` seed | recorded | 5 files | yes |
| `fixtures/turns/` | recorded agent transcripts: `seed_read_ok`, `probe_write_ok`, `probe_write_10`, `probe_write_wrongtool`, `probe_write_argv`, `probe_write_badfooter`, `backend_error`, `report_write_disagree`, `report_write_long`, `mutator_synth_bad`, `two_blocks.md`, `footer_*` | captured from real turns during the pilot, then **redacted** of nothing, because no turn ever sees a credential | 15 files, under 5 MB | yes |
| `fixtures/mutators/` | `set_v1.json`, a `raising.json` set holding one deliberately raising mutator, and `noop_case/` | `mutator_synth.py` for the real set; hand-written for the two test sets | 3 files, under 200 kB | yes |
| `fixtures/stderr/` | one recorded stderr per `classify_build` row: `clean`, `parse_error`, `assert_glibc`, `unreachable_*`, `llvm_error`, `segv`, `bad_alloc`, `oom_*`, `both`, `trace` | captured from real tool runs; `assert_glibc.txt` is the measured three-line C programme's output | 12 files, under 100 kB | yes |
| `fixtures/oracle/<class>_<nn>/` | **the five recorded real failures of §5**: `input.<ext>`, `argv.json`, `commit.json`, `expected.json`, `stderr.txt`, `README.md` | the procedure of §5.1, from the 187 seeds and from closed `label:bug` issues | 5 directories `[DEFAULT]`, 30 files, under 1 MB | yes |
| `fixtures/reducer/` | `branch_mlir/`, `branch_fir/`, `branch_sv/`, `branch_textual/`, `minimal/`, `reducer_abort/`, `truncated/` | each derived from an `fixtures/oracle/` failure; `truncated/` is produced by killing a reduction mid-write | 7 directories, under 2 MB | yes |
| `fixtures/ddmin/200_3/` | a 200-line input `[DEFAULT]` whose interestingness depends on exactly 3 lines `[DEFAULT]`, plus the interestingness function as a Python callable | constructed: 197 filler lines and 3 load-bearing ones, with the expected answer committed beside it | 2 files, under 20 kB | yes |
| `fixtures/ddmin/adversarial/` | an input whose interestingness function is true only for the full list | constructed | 2 files | yes |
| `fixtures/dedup/pairs/` | **the 20 labelled pairs of §10**, `<nn>.json`, each with two candidate ids, the label, the one-sentence justification and the labelling date; at least four are R4 pairs | the four construction rules of §10, labelled before the fingerprint is computed | 20 files, under 500 kB | yes |
| `fixtures/dedup/known_issue/`, `fixtures/dedup/verdicts/` | one candidate per `DedupVerdict` value | recorded | 8 files | yes |
| `fixtures/mirror/` | recorded GitHub responses: `closed_bug.jsonl` (487 closed and 101 open `label:bug` issues, M9), `with_comments.jsonl`, `ratelimit/`, `empty/`, `filed_issue.jsonl` | one `GithubIssuesNode.recent` call captured through the recording adapter of §8, then committed; no test ever calls GitHub | 5 files, about 30 MB | yes, and it is the largest committed fixture |
| `fixtures/contamination/clone` | the clone of `fixtures/corpus/clone`, reused | shared | shared | no |
| `fixtures/image_spec/` | `ok.json`, `lit_broken.json` | recorded from a real image build; `lit_broken.json` is `ok.json` with `lit_discovery_ok` false | 2 files | yes |
| `fixtures/image/` | `one_bump_off/`, `broken_target/`, `slang/`, `baseline_objects.txt` (FR-03.5's 18 named objects), `lit_baseline/` | build-time fixtures: each is a Dockerfile argument set plus the expected failure, not an image | 5 items, under 100 kB | yes |
| `fixtures/symbolize/` | `bassert_g_addrs.txt` and `bassert_addrs.txt`, each one address per line with its expected resolution | taken from M2's measured probe | 2 files | yes |
| `fixtures/repro_polarity/crashing/`, `.../diagnosing/` | **the two `repro.sh` polarity fixture binaries of FR-12.3**: a tiny C programme that aborts on its input, and the same programme patched to print a diagnostic and exit 1 | built from committed C source by `tests/fixtures/build_polarity.sh`; the **source** is committed and the binaries are built at test time, so no ELF is in the repository | 2 source files, under 5 kB | source yes, binaries no |
| `fixtures/repair/` | `issues.db` (a real CHIA database with existing keys), `chia_baseline.json` (the `sha256` of `issue_task.py` and the six prompts at `16c35e92`), `verdicts/`, `lit_red/`, `lit_zero/` | `issues.db` copied from a CHIA run; the baseline hashes computed once | 5 items, under 2 MB | yes |
| `fixtures/candidate/`, `fixtures/reduced_case/`, `fixtures/report/` | one record per branch each stage can take, including `differential.json`, `mlir_root.json`, `null_answer.json`, `taxonomy/` (one per stopping value), `short.md`, `long.md` | recorded | about 30 files, under 1 MB | yes |
| `fixtures/approve/` | `store_one_filed.db`, `store_at_total.db`, `two_pending.db`, `gfi_candidate.json`, `untriaged.json`, `with_patch.json` | built by running the loop to the gate and stopping, then copying `loop.db` | 6 files, under 2 MB | yes |
| `fixtures/results/` | `store_full.db`, `store_zero.db`, `store_capped.db`, `store_marked.db` | `store_full.db` is the pilot's own database; the other three are it with one property changed | 4 files, about 20 MB | yes |
| `fixtures/budget/`, `fixtures/repo/` | `complete.yaml`, `missing/` (23 one-key-short copies), `extra_key.yaml`, `bad_types/`; and four throwaway git repositories: `uncommitted/`, `later_commit/`, `mutator_after/`, `preregistered/` | the YAMLs are derived from `03-LLD.md` §9.5 by one edit each; the repositories are built by `tests/fixtures/make_repos.sh` at test time | 30 files, under 100 kB | YAMLs yes, repositories no |
| `fixtures/equivalence/<class>/` | **the fourteen constructed inputs of §4**, one directory each, with the input, the argv and the expected `ProbeResult` fields | constructed by hand, except `T-E-input-02`, `T-E-input-03`, `T-E-input-07` and `T-E-input-08`, which are derived from `fixtures/oracle/` | 14 directories, under 2 MB | yes |
| `fixtures/differential/` | `broken_tb/`, `x_only/`, plus the 12-line FIRRTL register-add of FINAL Appendix A | the register-add is recorded; the other two are constructed. **Blocked on A-19 and on the harness generators** (§16 item 2) | 3 directories | yes |
| `fixtures/secrets/known_values.txt` | the literal strings the secret grep searches for: a synthetic token of the shape `ghp_` plus 36 characters, and a synthetic model key | constructed; **no real credential is ever committed** | 1 file | yes |
| `tests/system/budget_tiny.yaml` | the system tests' budget file, complete by `03-LLD.md` §9.1 with `arm_window_seconds` 600 `[DEFAULT]` | derived from §9.5 by one edit | 1 file | yes, and it must be committed for FR-14.2 to pass on it |

**Total committed fixture weight** is dominated by three items: the issue mirror at about 30 MB, the
results stores at about 20 MB, and the transcripts at under 5 MB. Everything else is under 10 MB
together. The clone, the polarity binaries and the throwaway git repositories are **not** committed
and are produced by three committed scripts, which keeps the repository under 60 MB `[DEFAULT]` and
keeps every binary out of it.

---

## 14. The runtime-tier matrix

| Tier | Tests | Which | Expected wall time |
|---|---|---|---|
| **T0**, no CIRCT | 275 | Every test of `schema`, `fixt`, `layout`, `gen`, `mut`, `msyn`, `ddmin`, `budget`, `ledger`, `feed`, `store`, `results`, `appr`, `prompt`, `submit`, `byaml`, `cluster` (bar `cluster-01`); the pure-logic half of `corpus`, `pin`, `probe`, `triage`, `repair`, `gate`, `driver`, `core`; `image-10` and `image-11`; 13 of the 17 integration tests; `T-N-nfr03-01`, `T-N-nfr03-02`, `T-N-nfr11-01`, `T-N-nfr12-01` | **under 90 s** `[DEFAULT]` for the whole tier, given that nothing forks a compiler |
| **T1**, the SDK or a measured build | 49 | `corpus-01`, `corpus-15`, `corpus-16`, `corpus-19`; `pin-02`, `pin-08`; `probe-01`, `probe-07` to `probe-09`, `probe-13` to `probe-15`, `probe-20`, `probe-23`, `probe-25`, `probe-26`, `probe-31` to `probe-36`, `probe-38`; `triage-18` to `triage-20`; `repair-03`, `repair-04`; `gate-10` to `gate-13`, `gate-21`, `gate-22`; `driver-03`; `core-02` to `core-05`, `core-08` to `core-13`; `T-I-app-tri-01`, `T-I-rep-gate-02` | **about 25 min** `[DEFAULT]`, dominated by two measured git walks: the batched `cat-file` over 228 blobs at **125 s** (M1) and the contamination `log -p` over 109 paths at **488 s** (M4). Everything else in the tier is seconds |
| **T2**, the assertions-on image | 40 | Every `image` test bar `image-10` and `image-11`; `probe-28` to `probe-30`, `probe-37`; `repair-13`; `driver-07`, `driver-08`; the §5 and §6 parameterised runs; `T-I-gen-app-01`, `T-I-gen-app-02`; all 14 `T-E-input-*`; `T-N-nfr02-01`, `T-N-nfr02-02` | **about 45 min** `[DEFAULT]` **after** the image exists. The image build itself is separate and measured: **582 s** for the five targets under `-O3 -UNDEBUG -gline-tables-only` at `-j12` (M2), or **841 s** with the slang front end at `-j8` (M7), plus the two lit runs at **10.06 s** and **10.21 s** (M3) |
| **T3**, the single-machine cluster | 20 | All 9 system tests; `cluster-01`; `driver-05`; `T-N-nfr01-01`, `T-N-nfr04-01` to `T-N-nfr10-02`; the §5 fixtures' five cached images are reused rather than rebuilt | **about 2 h 30 min** `[DEFAULT]`: `chia up` and image pulls, then `T-S-pilot-01`'s two 600 s `[DEFAULT]` arm windows, then the regeneration check over the pilot's rows, which re-executes every tool stage |

The four counts sum to 384, which is every test identifier in this document, each counted once at the
**lowest** tier it can run at. Sixteen identifiers do more work than that count suggests: the oracle
and reducer tests `T-U-probe-19` to `T-U-probe-26` and `T-U-probe-31` to `T-U-probe-38` are counted
once at their tier, and are additionally run as the tier-2 parameterised sweeps of §5.3 and §6, once
per recorded failure. That is a count of parameter cases, not of tests, and it is why the T2 wall time
above is dominated by them rather than by the image tests.

---

## 15. The order the tiers run in the work plan

Four gates, each of which must be green before the next begins. `05-Work-Plan.md` owns the dates; this
section owns the order and the reason for it.

1. **T0 first, and on every commit.** It needs nothing but the repository, runs in under 90 s, and
   covers 275 of 384 tests, including the whole contract, the whole taxonomy mapping, the whole gate
   logic and every render refusal. It is the only tier cheap enough to be a pre-commit gate, and the
   contract fixtures' compatibility check lives in it, so a MAJOR bump is caught at the commit that
   makes it rather than at the join.
2. **T1 next, and on every push.** It needs the SDK, the `bassert_g` build and the clone, all of which
   exist on the implementation machine today, and it is where the corpus numbers, the pin selection,
   the oracle patterns against real binaries and the symbolizer wrapper are pinned. Its 25 minutes are
   dominated by two git walks that are cacheable: the corpus mine and the contamination scan both key
   on the clone HEAD, so a second run in the same day is seconds.
3. **T2 after the image builds, and on every image change.** It cannot start before F-03 produces an
   image, which `05-Work-Plan.md` schedules first because F-03 blocks the apparatus half entirely.
   Two orderings inside the tier are not optional: `T-U-image-17` runs **before** `T-U-image-06`,
   because two empty failing sets compare equal and a discovery abort would report a false zero; and
   the §5 fixtures are re-verified at their own commits before §6's reducer runs read them, because a
   reducer test that starts from a fixture that no longer fires proves nothing.
4. **T3 last, and before the campaign.** It needs the cluster, and its two long tests, the pilot and
   the regeneration check, are the evidence FR-18.11 and NFR-01 ask for. `T-S-isolate-01` runs
   **before** `T-S-pilot-01`, because a repair worker that does not restore itself would corrupt every
   verdict the pilot then produces, and the point of the isolation test is to find that before the
   data exists rather than after.

One rule cuts across all four: **no tier is skipped because the tier above it passed.** A tier-3 pilot
that produces a plausible results table proves nothing about the taxonomy mapping, the fingerprint's
transitivity or the validator's error codes, all of which are tier 0 and all of which are where a
silent defect would change a headline.

---

## 16. Resync

`03-LLD.md` is under red-team review in parallel with this document. This plan was written against its
§14.7 module index and its §3 function names as they stood on 2026-09-13. When the LLD changes, these
sections must be re-checked, in this order.

1. **§0.1's slug table and §1's subsection list**, against `03-LLD.md` §1.1, §1.2 and §14.7. A module
   added, removed or renamed changes a slug and therefore every test id under it. **Already an
   erratum:** `03-LLD.md` §1.3 lists twenty test modules and asserts a one-to-one source-to-test
   mapping, but five artefacts of §1.1 and §1.2 are not Python modules and have no test module in that
   list, namely `ChiaCirctAssertDockerfile`, `prompts/`, the two cluster YAMLs, `bug_loop_submit.sh`
   and `budget.yaml`. §0.1 adds five test modules for them and exempts them by name in
   `T-U-layout-01`. The LLD's §1.3 needs the same exemption stated, or this plan's five test modules
   fail its own layout assertion.
2. **§1.9's B4 rows, §4's `T-E-input-13`, §6's lift assertions and `fixtures/differential/`**, against
   whatever the LLD says about the differential. `03-LLD.md` §15 item 1 records that the two harness
   generators are specified as argv and not as code: there is no function name, no signature and no
   port-list extraction rule anywhere in §3.6.3, §4.6 or §4.10. **FR-08.2 therefore has no
   specification a unit test can be written against**, and `T-U-probe-30` currently asserts only the
   shared-stimulus and X-policy fields, not that a harness is generated. A-19's applicability count
   decides whether the generators are written at all, so this section may become empty rather than
   larger.
3. **§1.9's reducer rows and §4's `T-E-input-13`**, against `03-LLD.md` §4.7's selection table. Its
   third row states that the `.sv` branch's interestingness test is "the probe's own tool and argv, on
   the lifted MLIR", and `circt-verilog` cannot read MLIR: the `.fir` row correctly says "`firtool` on
   MLIR input", which `firtool` can do, but the `.sv` row has no equivalent. Either the table means
   `circt-opt` on the lifted Moore IR, or the branch needs a different test; as written,
   `T-U-probe-31`'s third branch cannot be given a pass criterion.
4. **§1.22 and §12.3's F-03 block**, against the LLD's `build_image`. `03-LLD.md` names
   `bug_loop.py:build_image` in §3.2 and §14.1 and gives it a timeout and an idempotency key, but no
   signature, no **Returns**, no **Worker** and no **Raises** paragraph anywhere in §3. Every test in
   §1.22 is therefore written against the **image** and the **Dockerfile**, which are specified, and
   none against the callable, which is not. `T-U-layout-03`'s docstring check will fail on it until
   the LLD gives it one.
5. **§1.8**, against `mutator_synth.synthesise_mutators`, which is named in `03-LLD.md` §3.2 and §14.1
   with only its prompt specified in §8.3 and no signature, returns or raises. `T-U-msyn-01` to
   `T-U-msyn-05` are written against the **frozen set's format** and the **three enforcement points**
   of §8.1, which are specified, rather than against the callable.
6. **§1.18's `T-U-store-09`**, against `store.validate_candidate`, which `03-LLD.md` §3.11 lists as a
   public callable and §2.9 describes only as enforcing "the conditionals on `CandidateRecord` by
   class". It has no signature and no error vocabulary, so the test asserts the two conditionals §2.9
   states and nothing more.
7. **§1.19's count**, against `results.py`. `03-LLD.md` §3.11 says "nine private refusal checks" and
   §14.4 names **fourteen**. This plan follows §14.4 and writes fourteen tests. One of the two
   statements is wrong and the LLD should say which.
8. **§1.9's `T-U-probe-15`**, against `BuildResult.peak_rss_bytes`. The field exists in `03-LLD.md`
   §2.9 and in the DDL at §6.2, but `circt_exec_probe`'s documented return (§3.10) has no key that
   could populate it. The test currently asserts only that the field is present and declared
   non-deterministic; if the LLD names a source, the test should assert it.
9. **§1.20's `T-U-driver-20`**, against FR-17.4's counters. `03-LLD.md` §14.3 says "every node returns
   a counter dict the driver logs on the head" and names no counter and no schema, so the test asserts
   one counter per stage and nothing about what it counts.
10. **§12.1 in full**, against `03-LLD.md` §14.2 and §14.7. Any FR that moves module changes a test id
    in its row, and any FR the LLD withdraws must be struck through here in the same commit.
11. **§13's fixture list**, against `03-LLD.md` §6.5's artefact tree and §2.13's fixture layout. A
    changed artefact path changes what `--record-fixtures` writes and therefore what is committed.
12. **§14's counts and §15's timings**, against any change to the module set or the tier markers.

Nothing in §5, §9, §10 or §11 depends on the LLD's function names: those four sections are procedures
over recorded data and over the requirements themselves, and they survive a rename.
