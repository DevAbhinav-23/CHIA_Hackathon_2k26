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

**The backend, 2026-09-14.** This plan is also resynced against the superseding section of
`design/ADR/ADR-D-03-model-backend.md`: CHIA's **`vertex`** backend in Vertex AI express mode,
`gemini-3.8-flash` at every agent stage, tokens and money in the ledger, and a **live-call
interlock**. §16.5 is that log. Two rules follow and both are asserted rather than assumed. **No test
in tiers T0, T1 or T2 sets `BUGLOOP_ALLOW_LIVE_MODEL`**, so no test can reach Vertex; and every test
that exercises a model turn does so through the mock recipe of §0.3, which is CHIA's own
`chia/models/tests/test_vertex.py`. The first live model request the project makes is the pilot,
`05-Work-Plan.md` W-18.

**Totals.** **477** tests: **420** unit, 17 integration, 9 system, 17 non-functional, 14 equivalence
class. ~~473: 416 unit~~ is corrected by §16.6, which added four, `T-U-repair-21` to `T-U-repair-23`
and `T-U-image-19`. No test is withdrawn by any resync and every surviving test keeps its identifier. Every module of
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

**How the model layer is mocked, and why it is CHIA's recipe and not a new one** (2026-09-14). CHIA
already has an offline harness for exactly this backend and the tests here use it verbatim rather
than inventing a double. `chia/models/tests/test_vertex.py` monkeypatches `google.genai.Client` to a
fake whose `models.generate_content` returns pre-built **real** `types.GenerateContentResponse`
objects in order, capturing the client kwargs and every request
(`chia:chia/models/tests/test_vertex.py:78-97`), builds each response from real `types.Part`,
`types.Candidate` and `types.GenerateContentResponseUsageMetadata` so the token counts are the
genuine field names (`chia:chia/models/tests/test_vertex.py:56-75`), and fakes the MCP transport and
`ClientSession` so the whole tool round trip runs with no server
(`chia:chia/models/tests/test_vertex.py:100-145`). Its two loop tests then assert exactly what this
plan needs to assert: that the client was built for Vertex with the expected kwargs, that the
request carried the namespaced function declarations, that a `function_call` came back as a
`function_response`, and that `_last_metadata` holds the accumulated `input_tokens` and
`output_tokens` (`chia:chia/models/tests/test_vertex.py:238-306`).
`examples/circt_bug_loop/tests/conftest.py` exposes that recipe as one fixture, `fake_vertex`, which
yields `(install(responses), capture)`; every test below that runs a turn uses it. Nothing about the
loop's own code is faked: `build_llm`, `llm_turn`, the prompts, the emitter and the two `ChiaTool`s
all run for real.

No test framework, assertion library, mocking library, HTTP-recording library or fixture library is
added. `unittest.mock.patch` is standard library and is the one substitution mechanism used, and
`monkeypatch` is pytest's own.

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
  `feedback.py`, `results.py` and `store.py` are wholly tier 0. `corpus.py`, `pin_select.py` and
  B6b joined the head in the LLD revision and are **not** wholly tier 0 for a different reason: their
  placement is now trivially satisfied, but their bodies run `git` against the blobless clone, so
  their tier is set by the clone exactly as a worker node's is set by the binary it invokes.
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

**One rule cuts across T0, T1 and T2, added 2026-09-14: none of them may reach a model.**
`conftest.py` deletes `BUGLOOP_ALLOW_LIVE_MODEL` from the environment for every test outside T3 and
sets `GEMINI_API_KEY` to the synthetic value in `fixtures/secrets/known_values.txt`, so
`generate_task.build_llm` raises `LiveModelRefused` if any code path ever reaches it unmocked, which
is a loud failure and not a silent HTTPS call. `T-U-layout-08` asserts the rule over the test tree
itself. T3 is where the interlock is set, and even there only `T-S-pilot-01` and the tests that
depend on its store set it; the other T3 tests run the cluster with the model layer mocked the same
way.

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

**Callables covered:** `validate`, `check_version`, `to_json`, `from_json`, `bound_text`,
`_check_field` and the five `_*_conditionals`.

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

### 1.3 Repository-wide static checks, 9 tests

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
| `T-U-layout-08` | **Nothing below T3 can reach a model.** Three assertions over the repository itself. (1) `BUGLOOP_ALLOW_LIVE_MODEL` is assigned, `setenv`'d or `monkeypatch.setenv`'d in **no** test module outside `tests/system/`, asserted by an `ast` walk over every `tests/` file rather than by a grep, so a string in a docstring does not fail it and a computed name does not pass it. (2) The identifier `VertexGeminiLLM` appears in exactly one function of the **loop's own modules**, `generate_task.build_llm`, and in no other one of them. **Amended 2026-09-14**: there is exactly one further construction path, the `elif backend == "vertex":` arm of `upstream/issue_task-vertex-branch.patch` in CHIA's `issue_task.py`, which is CHIA's file and cannot carry the loop's interlock; the test asserts that it is **gated** instead, `repair_adapter.repair_adapt` calling `generate_task.require_live_model` before it invokes the chain, asserted on the source, and that no **third** occurrence of the identifier exists anywhere the loop ships. Two construction paths, both behind the same refusal. (3) `conftest.py` deletes the variable and sets the synthetic key for every non-T3 test, asserted by reading the fixture's own effect inside a test | `secrets/known_values.txt` | T0 | NFR-06, NFR-08 |
| `T-U-layout-09` | **The two-tree layout of `03-LLD.md` §1.4.** No module in the flow walks further than its own directory to find anything: an `ast` walk finds no `Path(__file__).parents[n]` with `n >= 2` and no `.parent.parent`, because `circt_bug_loop/` in the team repository and `examples/circt_bug_loop/` in a CHIA checkout have different ancestors; `_CHIA_PKG` is derived from `chia.__path__[0]` and **not** from `chia.__file__`, which is `None` for a namespace package and would raise. `upstream/sync-to-chia.sh` is run twice into a temporary copy of a stub CHIA checkout and the second run leaves it byte-identical, and it refuses a target holding no `chia/` | `repo/chia_stub/` | T0 | FR-19.2, FR-19.5 |

### 1.4 `corpus.py` (A1, A1'), 24 tests

**Callables covered:** `build_corpus`, `normalise_run_line`, `strip_probe_only_options`,
`resolve_sites`.

The RUN-line normaliser is tested against the shape features M1 measured over 331 logical lines, which
is `01-FRD.md` §10.3's requirement that the normaliser meet the M1 shapes.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-corpus-01` | **Reproduces 187/171 at the recorded HEAD.** Mining the clone reset to `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` with `--since 2024-09-11` emits exactly 187 records, exactly 171 with a non-null tag | `corpus/clone` | T1 | FR-01.1 |
| `T-U-corpus-02` | The emitted SHA set equals the filtered candidate set derived from `analysis/pin_window_raw.json` by PIN §2's rule, compared as sets | `corpus/pin_window_raw.json` | T0 | FR-01.1 |
| `T-U-corpus-03` | The `SdkMap` has exactly 38 groups, median group size 3, maximum 27 | `corpus/pin_window_raw.json` | T0 | FR-01.5 |
| `T-U-corpus-04` | Exactly 16 seeds carry `sdk_exact=false`, every one with `bumps_away == 1` and none greater | `corpus/pin_window_raw.json` | T0 | FR-01.7 |
| `T-U-corpus-05` | Both bucketings of FR-01.4 reproduce their tables exactly: the dialect-level one (FIRRTL 42, ImportVerilog 31, MooreToCore 12, LLHD 12, Synth 9, Comb 8, Moore 5, ExportVerilog 5, CoreToFSM 5, ESI 5, OM 4, HWToBTOR2 4, RTG 4, HW 3, Arc 3, tail) and the unmerged one, including the 16-way split of `include/circt/Dialect` | `corpus/pin_window_raw.json` | T0 | FR-01.4 |
| `T-U-corpus-06` | Seed `f2b15a44ec70`'s extracted line is `circt-opt %s --split-input-file --convert-hw-to-llvm=spill-arrays-early=false \| FileCheck %s` verbatim, and the classified tool is `circt-opt`, taken from the line and never inferred from a source path | `corpus/runlines/` | T0 | FR-01.2, FR-01.3 |
| `T-U-corpus-07` | **Leading `not`.** A `not`-wrapped line drops the wrapper and records `polarity=expect_nonzero`; an unwrapped line records `expect_zero`; `not --crash` also drops `--crash` and sets `notes["not_crash"]`. The corpus holds 2 such lines on 1 seed (M1), and both are in the fixture | `corpus/runlines/not_*.txt` | T0 | FR-01.10 |
| `T-U-corpus-08` | An `env` wrapper is dropped and every `NAME=VALUE` it carried is recorded in `env` | `corpus/runlines/env.txt` | T0 | FR-01.10 |
| `T-U-corpus-09` | **`split-file`.** The wrapper is dropped and `shape=split_file` recorded. The corpus holds exactly 1 such line (M1) and it is the fixture | `corpus/runlines/splitfile.txt` | T0 | FR-01.10 |
| `T-U-corpus-10` | **Pipes.** Everything from the first **unquoted** `\|` is dropped and the tail recorded verbatim; a `\|` inside a single- or double-quoted `FileCheck` pattern does **not** truncate. 234 of 331 lines carry a pipe (M1), so the quoted case is not hypothetical | `corpus/runlines/pipe_*.txt` | T0 | FR-01.10 |
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

**Callable covered:** `select_release_pinned_main`.

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

### 1.6 `generate_task.py` (A3, A4, `ProbeWriteTool`, `SourceReadTool`, the backend glue), 25 tests

**Callables covered:** `generate_seeded`, `generate_mutation`, `emit_specs`,
`ProbeWriteTool.write_probe`, `SourceReadTool.read_file`, `.grep` and `.list_dir`, and, from
2026-09-14, `build_llm` and `llm_turn`.

No model runs in any of these, and from 2026-09-14 that is enforced rather than intended: the five
backend tests use the `fake_vertex` fixture of §0.3, which is CHIA's own
`chia/models/tests/test_vertex.py` recipe, and `BUGLOOP_ALLOW_LIVE_MODEL` is deleted from the
environment for all of them except where a test sets it itself, inside `monkeypatch`, to exercise the
allow path against the fake. The seeded arm's two turns are driven by a recorded transcript replayed
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
| `T-U-gen-21` | **The interlock refuses without the variable.** With `BUGLOOP_ALLOW_LIVE_MODEL` unset, set to `""`, set to `0`, set to `true`, and set to the unexpanded literal `${BUGLOOP_ALLOW_LIVE_MODEL}`, `build_llm` raises `LiveModelRefused` in all five cases and constructs **nothing**: `google.genai.Client` is patched to a sentinel that fails the test if it is called at all, so the assertion is that no client was built rather than that no request was sent. Only the exact string `1` proceeds. The message names the variable and points at `03-LLD.md` §3.5.1 | none | T0 | NFR-08, NFR-06 |
| `T-U-gen-22` | **The interlock refuses without a usable key.** With `BUGLOOP_ALLOW_LIVE_MODEL=1` and `GEMINI_API_KEY` unset, empty, whitespace, or the unexpanded literal `${GEMINI_API_KEY}`, `build_llm` raises `LiveModelRefused` naming the variable and the hostname and builds nothing. The unexpanded-reference case is the one that matters operationally: CHIA's config loader leaves `${VAR}` as literal text when the variable is unset, so a container brought up without the key holds the reference as its value, and without this branch the failure would surface as an authentication error from Vertex instead of a refusal on the head. **The key is never printed**: the test asserts the raised message does **not** contain the key value it set | `secrets/known_values.txt` | T0 | NFR-06, NFR-08 |
| `T-U-gen-23` | **Express-mode construction.** With both variables set and the fake in place, `build_llm` returns a `VertexGeminiLLM` whose `model` is `budget.yaml`'s `model_id`, whose `project` and `location` are **both `None`** after construction, and whose `client_kwargs` carries the key and `http_options={"timeout": timeout_seconds * 1000}`. The captured `genai.Client` kwargs are then `vertexai=True, project=None, location=None, api_key=<key>, http_options=...`. The negative half is the point: a `VertexGeminiLLM` constructed **without** the two assignments has `location == "us-central1"`, and building a real `genai.Client` from it raises `ValueError` naming "mutually exclusive", which the test asserts against `google-genai` itself so that a CHIA release fixing the default makes this test fail loudly rather than silently | none | T0 | FR-14.6 |
| `T-U-gen-24` | **`llm_turn` brings the usage home.** Driving one turn whose fake response carries `prompt_token_count=11` and `candidates_token_count=7`, the returned dict's `usage` is `{"tokens_in": 11, "tokens_out": 7, "num_turns": 1, "model": "<the model id>"}`, and `result`, `stream`, `stderr` and `success` are the `QueryResult`'s. Two assertions pin **why** the node exists: `QueryResult`'s field list is exactly `result, returncode, stderr, stream_result, success`, so `getattr(cli, "usage", None)` is `None` on this backend; and `llm_turn`'s body calls `llm.prompt(...)` directly rather than `llm.prompt.options(...).chia_remote(...)`, asserted on the source, because a remote dispatch serialises the LLM object and the counts would never return. `_chia_options` is `{"resources": {"llm": 1.0}, "max_retries": 0}` | none | T0 | FR-14.6, FR-14.8 |
| `T-U-gen-25` | **The tool loop, offline.** With the fake `genai.Client` and the fake MCP transport of §0.3, a stage-2 turn given `[source_read, probe_write]` declares both tools to the model as `<tool name>__<function name>`, executes a `function_call` against the fake session and feeds a `function_response` back, and the second request carries that response; the loop ends when the model returns no more calls. The declarations are asserted to have had `$schema`, `additionalProperties` and `title` stripped, because the backend removes them and a tool that relied on one to constrain the model would be relying on nothing | none | T0 | FR-04.4, FR-19.1 |

### 1.7 `mutators/` (A4's frozen set), 10 tests

**Callables covered:** `mutate_seed` and `mutators.apply`.

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

**Callable covered:** `synthesise_mutators`.

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

**Callables covered:** `probe_execute`, `classify_build`, `oracle_primary`, `strip_prologue`,
`oracle_differential`, `extract_port_list`, `gen_arc_harness`, `gen_verilator_tb` and `reduce_case`.

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
| `T-U-probe-39` | **`_ASSERT_GLIBC`'s `func` group is `.+?` and not `[^:]+`.** The compiled C++ sample `b_assert: b.cpp:2: int circt::Foo::get(int) const: Assertion \`c > 99 && "needs many args"' failed.` matches and yields `func` as the whole signature and `expr` as the whole condition including the `&& "..."` tail; so does the shape a CIRCT probe produces, an absolute binary path and an absolute source path on one line. The old `[^:]+` matched only the C control, whose function name has no `::`, so it would have classified no CIRCT assertion at all. `func` is captured and is **not** part of the fingerprint | `stderr/assert_cpp.txt`, `stderr/assert_glibc.txt` | T0 | FR-07.1, FR-07.3 |
| `T-U-probe-40` | **`parse_error` split by `stopping_reason`.** A stderr carrying the literal `does not refer to a registered pass or pass pipeline` records `tool_rejected_argv`; any other clean non-zero exit records `tool_rejected_input`. `build_status` stays `parse_error` in both, FR-06.9's seven being closed, and `results.py` prints the two counts separately so an apparatus misconfiguration is never read as a rejected input | `stderr/parse_error_argv.txt`, `stderr/parse_error.txt` | T0 | FR-06.6, FR-06.9 |
| `T-U-probe-41` | **`limit_hit`, derived in one place.** `wall` when the caller's own wall-clock killer reached `os.killpg`; `cpu` when the child's signal is `SIGXCPU` **or** its rusage CPU is at or above `cpu_seconds`; `address_space` when stderr carries one of the three allocation literals or the line `MemoryError`; `None` otherwise. `classify_build` then maps `wall` and `cpu` to `timeout` and `address_space` to `oom`, and a limit kill is **never** `crash`. A source search asserts that no module other than `circt_exec_probe` writes the field | none | T1 | FR-06.2, FR-06.4, FR-06.7 |
| `T-U-probe-42` | **`peak_rss_bytes` has a producer.** `probe_execute` fills it from `circt_exec_probe`'s return, which is `os.wait4`'s `ru_maxrss` multiplied by 1,024 because `ru_maxrss` is in kilobytes on Linux; it is non-null on every probe whose child started, null otherwise, and is declared non-deterministic in `BuildResult` beside `wall_seconds`, so `T-N-nfr02-01` and §11's regeneration check both exclude it | none | T1 | FR-06.4, NFR-02 |
| `T-U-probe-43` | **The worker identity fields.** `probe_execute` writes `worker_hostname` from `socket.gethostname()`, `worker_node_id` from `ray.get_runtime_context().get_node_id()` and `child_pid` from the pid `os.fork` returned, and all three reach the `build_result` row; without them FR-13.2's recorded pair for the **original** run had no source and `q1_same_worker` was not computable | none | T1 | FR-13.2 |
| `T-U-probe-44` | **`strip_prologue`.** It drops leading frames whose normalised function name is one of the ten of `03-LLD.md` §3.7.1, and leading unresolved frames whose module is libc, and stops at the first survivor. On the recorded 466-frame trace it removes exactly **four** and leaves 462, and the dropped list is `PrintStackTrace`, `RunSignalHandlers`, `SignalHandler` and one libc frame. `prologue_dropped` records the count, so the strip is auditable from the row | `stderr/trace.txt` | T0 | FR-07.5, FR-10.1 |
| `T-U-probe-45` | **The interestingness script emits exactly one class block.** A written `interesting.sh` contains exactly one `# --- class:` line, that line names the candidate's own oracle class, and the other two blocks are absent; all **eleven** placeholders of `03-LLD.md` §10.2 are substituted, so no `@NAME@` survives anywhere in the file, and the three class-specific ones are present only in their own block. `sh -n` passing is asserted as necessary and not sufficient, because it passed on the earlier three-blocks-in-sequence version in which two blocks were dead code | none | T1 | FR-09.1, FR-09.2 |
| `T-U-probe-46` | **The script's working directory and its stderr.** `CANDIDATE` is absolutised **before** the `cd`, because `circt-reduce` passes the candidate path relative to its own cwd; the script then `cd`s into its own `mktemp -d`, so anything the tool writes beside its input lands there and is removed by the `trap`; and the subshell with its own stderr keeps the shell's `Segmentation fault <command line>` line out of `circt-reduce`'s stderr, asserted by zero stderr bytes on an interesting candidate | none | T1 | FR-09.13 |
| `T-U-probe-47` | **`extract_port_list`.** It runs one `circt-opt <lifted> -o - --mlir-print-op-generic` and reads `module_type = !hw.modty<...>` off the one `hw.module` carrying no `sym_visibility = "private"`, returning `Port`s in signature order with direction, width, MLIR type and the clock and reset predicates. The four refusals each fire once: `no_top` on zero or two public modules, `bad_port_type` on an aggregate or a parameterised width, `no_clock` on a purely combinational design, `circt_opt_failed` on a non-zero exit, and each is `harness_failure` and never `diverge` | `differential/port_lists/` | T1 | FR-08.2, FR-08.8 |
| `T-U-probe-48` | **The two generators, deterministically.** `gen_arc_harness` and `gen_verilator_tb` are byte-identical across ten calls on one `(port_list, stimulus_seed)` pair; both drive the **same** input ports with the **same** LFSR values in the same cycle order, asserted by extracting the driven sequence from each text and comparing; both exclude clock and reset ports from the stimulus; both emit the `BUGLOOP <cycle> <port>=<hex>` acceptance shape with outputs in signature order and each value zero-padded to `ceil(width / 4)` digits; and `gen_arc_harness` names `bugloop_main` and `gen_verilator_tb` names `bugloop_tb`, which is what §4.6's and §4.10's argv expect. Neither compiles anything, so this test is tier 0 | `differential/port_lists/` | T0 | FR-08.2, FR-08.3 |
| `T-U-probe-49` | **`probe_task.py` imports the record dataclasses and never `LoopStore`.** An import walk shows `BuildResult`, `OracleVerdict`, `Frame`, `DifferentialVerdict`, `ReducedCase` and `ImageSpec` imported from `store`, and `LoopStore` imported nowhere; the module opens no `loop.db` and no `sqlite3` connection, which it could not do anyway, the store being a `SQLiteNode` pinned to the head | none | T0 | FR-16.1, FR-17.3 |
| `T-U-probe-50` | **A-08's acceptance, and what it is blocked on.** The generated harnesses are built and run for real: `gen_verilator_tb`'s output compiles under `03-LLD.md` §4.10's argv, `gen_arc_harness`'s runs under §4.6's, both print `BUGLOOP` lines, and the differ reads them. Driven by the recorded 12-line FIRRTL register-add of FINAL Appendix A. **Marked `[UNVERIFIED]` and skipped, with the skip recorded**, until A-19's count says at least one seed is differential-applicable; the skip is reported, never passed vacuously | `differential/register_add/` | T2 | FR-08.2, FR-08.5 |

### 1.10 `ddmin.py` (B5's textual reducer), 8 tests

**Callable covered:** `ddmin`.

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

### 1.11 `triage_task.py` (B6a, B6b, B7), 34 tests

**Callables covered:** `issue_mirror_refresh`, `dedup_and_screen`, `triage_report` and
`render_report`.

Tests 01 to 09 and 25 to 27 are the fingerprint and the partition, 10 to 20 and 28 to 33 the mirror
and the two screens, 21 to 24 and 34 the triage turn and the render.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-triage-01` | The assertion fingerprint is `f"{expr}\n{site}"` with runs of whitespace in `expr` collapsed to one space and the ends stripped; the `&& "message"` tail is **kept**, and two asserts differing only in that tail fingerprint differently | `fingerprint/assertion/` | T0 | FR-10.1 |
| `T-U-triage-02` | The site normalisation removes the `/workspace/circt/` prefix, keeps only the last two components of any other absolute path, and keeps the line number verbatim; two images built in different directories produce the same fingerprint | `fingerprint/assertion/` | T0 | FR-10.1, FR-10.6 |
| `T-U-triage-03` | **The crash and fatal-error fingerprint is the signal plus one frame, and is no longer the top-N tuple.** It is `f"{signal_name}\n{fingerprint_frame}"`, where `signal_name` is `BuildResult.signal` and `fingerprint_frame` is the first frame **after the prologue strip** that is in a CIRCT object with a resolved line, written as its normalised function name and the **basename** of its file with **no line number**, so a one-line edit inside the same function does not split one bug across runs. The measured reason is asserted as a property of the fixture set, not merely quoted: over ten recorded runs of one input the top-5 stripped tuple takes nine distinct values and the fingerprint frame takes three | `fingerprint/crash/` | T0 | FR-10.1 |
| `T-U-triage-04` | Frame-name normalisation performs the four steps and only those: take `FunctionName`, cut from the first `(` at bracket depth zero, strip a trailing ` const`, collapse whitespace. `circt::chooseName(llvm::StringRef, llvm::StringRef)` becomes `circt::chooseName` | `fingerprint/crash/` | T0 | FR-10.1 |
| `T-U-triage-05` | A candidate with no assertion text and fewer than 5 resolvable frames carries `basis=insufficient` and `value=None`, deduplicates against nothing, and fails gate question 4 with that reason; its structural hash is still recorded | `fingerprint/insufficient/` | T0 | FR-10.8 |
| `T-U-triage-06` | The structural hash normalises every SSA value name, every **`@symbol` name**, every `loc(...)` suffix and every whitespace run before hashing; it is present on every candidate and is **never** the fingerprint, asserted by a source check that no merge path reads it. The symbol clause is load-bearing: `circt-reduce` renames modules during reduction, `hw.module @top` becoming `hw.module private @Foo`, so without it the same reduced case hashed differently depending on how far the reducer got. The fixture is that observed pair | `fingerprint/structural/` | T0 | FR-10.1, FR-10.2 |
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
| `T-U-triage-17` | Every verdict other than `new` carries a populated evidence field, and `dedup_evidence` holds exactly the **eight** keys of `_DEDUP_EVIDENCE_KEYS`: `matched_key`, `matched_token`, `issue_number`, `issue_url`, `issue_state`, `issue_labels`, `fixing_commit` and `duplicate_of_candidate_id`, and **no issue text**. The per-verdict required subset is `_DEDUP_EVIDENCE_REQUIRED`, and `store.validate_candidate` is the enforcement point (`T-U-store-12`) | `dedup/` | T0 | FR-10.5, FR-20.4 |
| `T-U-triage-18` | **The post-pin scan.** File level, lower bound **`candidate.run_commit`**, upper bound clone head: a candidate reproducing a bug fixed inside the lag is `fixed_post_pin` with the fixing SHA | `contamination/clone` | T1 | FR-10.4 |
| `T-U-triage-19` | **The contamination scan.** Symbol level, lower bound the seed's `committed_date_utc`: the symbol is read from git's `@@ ... @@` hunk-header context, never from the crude `\b(\w+)\s*\(` rule. Over the corpus the two rules give 77.0% and 79.1% (M4), and the test asserts the ctx rule is the one that sets `contaminated_symbol` | `contamination/clone` | T1 | FR-15.1 |
| `T-U-triage-20` | Both flags are recorded, the symbol-level one is what the results artefact reports, and `contamination_lower_bound` records the run's commit for the 16 non-exact seeds so all 187 are screenable | `contamination/` | T1 | FR-15.1, FR-15.2, FR-15.5 |
| `T-U-triage-21` | A candidate whose dedup verdict is `known_open_issue`, `known_closed_issue` or `fixed_post_pin` is classified `known_issue` whatever the agent wrote; the agent's only freedom is the reason text | `turns/report_write_disagree.jsonl` | T0 | FR-11.2 |
| `T-U-triage-22` | The classification reason is capped at 4 sentences `[DEFAULT]`, counted by splitting on `.`, `!` and `?` followed by whitespace or end of string, and is **truncated with the truncation recorded**, not rejected | `turns/report_write_long.jsonl` | T0 | FR-11.1 |
| `T-U-triage-23` | **The renderer.** Every one of `03-LLD.md` §7.4.1's thirteen substitution points is present in the rendered `report.md` and equals the record field by field; a missing point fails the render. Every number in the output equals the record's, asserted by extracting each numeric substitution and comparing | `report/` | T0 | FR-11.3, FR-11.4, FR-03.11 |
| `T-U-triage-24` | Template selection by candidate class: a `differential` candidate renders with the second template, which contains neither the word "expected" nor any sentence naming a correct arm, names `circt/arc-tests`, and reaches the artefact store with no `FilingRecord`. A `fatal_error` candidate's report quotes the `LLVM ERROR:` message and contains neither "crash" nor "assertion". The `Assisted-by:` trailer is the last line and names `RunManifest.model_ids["triage_report"]` | `report/` | T0 | FR-07.10, FR-08.6, FR-08.7, FR-11.5, FR-11.6, FR-11.9 |
| `T-U-triage-25` | **The strip precedes every use of a frame.** `fingerprint_frame` is computed from the stripped list, and a frame whose normalised function name is empty or the degenerate `operator`, which is what a lambda reduces to under step 2 of the name normalisation, is **skipped**, so the name in a fingerprint is always a real function. Asserted on a trace whose first stripped CIRCT frame is a lambda | `fingerprint/crash/` | T0 | FR-10.1 |
| `T-U-triage-26` | **`fingerprint_stable`, reported and never merged.** A candidate whose gate re-run produced a different fingerprint string carries `fingerprint_stable=false`, is placed in **no** partition with any other candidate, and is counted for the results artefact; a candidate whose re-run has not happened carries `None` and is likewise not merged. `false` does not fail gate question 1, which asks only whether the recorded failure reproduces | `fingerprint/unstable/` | T0 | FR-10.1, FR-10.2 |
| `T-U-triage-27` | **The two fallbacks.** Where no stripped frame is in a CIRCT object with a resolved line, the basis falls to the top-`fingerprint_top_n` tuple of normalised names joined by newlines; where fewer than `fingerprint_top_n` frames resolve at all, the basis is `insufficient`. The top-N tuple is recorded as `Fingerprint.frame_tuple` **evidence in every case**, including when the primary basis is `assertion` | `fingerprint/crash/`, `fingerprint/insufficient/` | T0 | FR-10.1, FR-10.8 |
| `T-U-triage-28` | **The mirror screen's token set, one case per oracle class.** `assertion` yields two tokens, the `expr` exactly as `assertion_text` records it and the `file:line` exactly as `assertion_site` records it; `crash` yields one, the fingerprint frame's **function name** without its file; `fatal_error` yields two, that function name and `fatal_message` verbatim; `differential` yields **none**, and such a candidate never reaches this stage at all | `dedup/known_issue/` | T0 | FR-10.3 |
| `T-U-triage-29` | A token shorter than `MIRROR_TOKEN_MIN_CHARS` (8, `03-LLD.md` §9.4) is dropped before the query runs, so `fold` and `parse` alone cannot match hundreds of issues and answer `known_issue` for every candidate; a candidate all of whose tokens are dropped reaches the screen with none and matches nothing | `dedup/known_issue/` | T0 | FR-10.3 |
| `T-U-triage-30` | **Open beats closed.** The query is `instr(title \|\| ' ' \|\| body, :token) > 0` over `issue_mirror`, run once per token, case-sensitively, with **any** token matching **any** issue producing a hit; the verdict is `known_open_issue` for an open issue and `known_closed_issue` for a closed one, and where tokens match issues in both states the **open** one wins. `evidence` carries `matched_token`, `issue_number`, `issue_url`, `issue_state` and `issue_labels` | `dedup/known_issue/` | T0 | FR-10.3, FR-10.5 |
| `T-U-triage-31` | **No match is not a verdict.** A candidate whose tokens match no mirrored issue leaves the mirror screen contributing nothing, so the dedup verdict is decided by the candidate-to-candidate partition and the post-pin scan alone and may be `new`; the screen does not invent `dedup_unavailable` for a clean miss, which would fail gate question 4 for every candidate in a quiet week | `dedup/known_issue/` | T0 | FR-10.3, FR-10.7 |
| `T-U-triage-32` | **The scans bound on `candidate.run_commit`, never on `manifest.run_commit[0]`.** Built against a **calibration** manifest carrying two `run_commit` entries, a candidate from the second seed scans from its own commit; index 0 is an arbitrary sampled seed's and is this candidate's only by accident. Asserted on both the post-pin scan's lower bound and the contamination scan's | `contamination/clone`, `run_manifest/calibration_two.json` | T1 | FR-02.7, FR-10.4, FR-15.1 |
| `T-U-triage-33` | **B6b is a head node.** `dedup_and_screen` declares no `circt` resource, so it can never hold an apparatus slot while walking 24 months of `main`; it reads the head's blobless clone and the head-pinned `issue_mirror` table, and takes `clone_path` as a parameter rather than assuming `/workspace/circt`, which inside a worker is a one-commit fetch | none | T0 | FR-10.3, FR-10.4, FR-15.1 |
| `T-U-triage-34` | **Two templates, two substitution lists, no leaked `$`.** The primary template's **thirteen** points and the `differential` template's **twelve** are enforced **separately** and not as one superset: `render_report` raises `ReportIncomplete(point)` for a point missing from the template it was given, and accepts the other template's absent points. Both fillings render with `Template.safe_substitute` and **no `$name` survives in either**, because for a `differential` candidate the six primary variables are bound to the literal `not applicable to a differential candidate` and the three differential variables are bound from the `DifferentialVerdict` | `report/` | T0 | FR-08.6, FR-11.3, FR-11.9 |

The JSON-footer parser and the five per-turn files are shared with A3 and A7 and are tested once, in
§1.23. The earlier "no further `triage` identifiers are allocated" is withdrawn: this resync allocated
ten, `T-U-triage-25` to `T-U-triage-34`.

### 1.12 `repair_adapter.py` (B8), 23 tests

**Callables covered:** `repair_adapt` and `_as_github_issue`.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-repair-01` | The local identifier is `LOCAL_ID_BASE + rowid`, inside `[900000000, 999999999]`, unique, monotonic, and disjoint from every key in the existing `issues.db`, asserted against a real `issues.db` | `repair/issues.db` | T0 | FR-12.2 |
| `T-U-repair-02` | `_as_github_issue` populates all eleven required fields of `chia:chia/github/state_def.py:11-24`; `url` is a `local://` URI and never an `https://github.com/` one | `report/` | T0 | FR-12.2 |
| `T-U-repair-03` | **Repro polarity, crashing binary.** The generated `repro.sh` exits **non-zero** against a committed fixture binary that still crashes on the reduced case | `repro_polarity/crashing/` | T1 | FR-12.3 |
| `T-U-repair-04` | **Repro polarity, diagnosing binary.** The same script exits **0** against a committed fixture binary patched to emit an ordinary diagnostic and exit non-zero, which is the case the naive script gets wrong | `repro_polarity/diagnosing/` | T1 | FR-12.3 |
| `T-U-repair-05` | `RepairRefused` for `oracle_class` of `differential` and of `fatal_error`, with the reason recorded, before the chain is invoked at all | `candidate/` | T0 | FR-08.10, FR-12.4 |
| `T-U-repair-06` | `RepairRefused` for `out_of_scope_root`, before the chain is invoked | `candidate/mlir_root.json` | T0 | FR-12.5 |
| `T-U-repair-07` | **Hunk equality, not byte equality** (rewritten 2026-09-14, `01-FRD.md` §1.9). `git diff` of `examples/circt_issue_solver/issue_task.py` against CHIA at `16c35e92` yields **exactly one hunk**, **19 insertions and 0 deletions**, and that hunk is byte-for-byte `upstream/issue_task-vertex-branch.patch`'s. Asserted three ways so that no one of them can pass alone: the diff is parsed and its hunk count, insertion count and deletion count are checked; the added lines are compared to the patch file's `+` lines; and the resulting file is `ast.parse`d. A second hunk, any deletion, or an altered line fails. ~~byte-identical to CHIA at `16c35e92`, compared by `sha256` of the file~~ is **withdrawn**: it forbade the one addition that puts stage 7 on the campaign backend | `repair/chia_baseline.json` | T0 | FR-12.1 |
| `T-U-repair-08` | All six of `prompts/{system,assess,reproduce,fix,regression,writeup}.md` are byte-identical to CHIA at `16c35e92` | `repair/chia_baseline.json` | T0 | FR-12.9 |
| `T-U-repair-09` | The chain's `cfg["tag"]` is **`candidate.run_commit`** and `circt_git_reset` is called with it, never with `manifest.run_commit[0].commit`, never with `firtool-1.148.0` and never with `HEAD`. Asserted against a **calibration** manifest carrying two entries, where index 0 is another seed's commit | `run_manifest/calibration_two.json` | T0 | FR-02.7, FR-12.6 |
| `T-U-repair-10` | All six of CHIA's statuses round-trip into `RepairResult` and into the store, with the failing phase named | `repair/verdicts/` | T0 | FR-12.7 |
| `T-U-repair-11` | `lit_ok=false` with the failing test names yields a report with **no patch**, and the gate returns `report` rather than `report_plus_patch` | `repair/lit_red/` | T0 | FR-12.8, FR-13.6 |
| `T-U-repair-12` | A lit run reporting `passed == 0 and failed == 0` on a non-empty path list records `lit_unusable`, **not** `lit_ok=false`, names FR-03.17, and stops the run | `repair/lit_zero/` | T0 | FR-12.8 |
| `T-U-repair-13` | **The restore is three things, not two.** After every attempt, whatever the outcome, `circt_git_reset(candidate.run_commit)` runs, `circt_ninja_build` of the `ImageSpec` targets runs, **and every tool binary is re-hashed against `ImageSpec.tool_hashes`**, recording `restore_hashes_match`; `restore_ok` is the conjunction of all three. A successful `ninja` is not evidence of bit-identity, the `ImageSpec` hashes being computed from a freshly started container while the restore rebuilds locally. A failure of any of the three records `repair_worker_dirty` and disables B8 for the rest of the run. Whether the re-hash comes back true is `03-LLD.md` §15 item 4 and is `[UNVERIFIED]`; the test asserts that the comparison is **made and recorded**, not that it passes | `image_spec/ok.json` | T2 | FR-12.11 |
| `T-U-repair-16` | **All sixteen `cfg` keys.** Each is populated with the value `03-LLD.md` §3.8's table gives: the ten values and the six prompt bodies, the latter read from **CHIA's own** `examples/circt_issue_solver/prompts/` so FR-12.9's byte comparison is of the file the adapter actually passed. `timeouts` is `PHASE_TIMEOUTS` verbatim, `build_jobs` is 16, `require_repro` is `True`, and `vertex` carries `GOOGLE_CLOUD_PROJECT` where set | `report/` | T0 | FR-12.1, FR-12.6 |
| `T-U-repair-17` | **The chain is called inline.** The call site is the bare name `run_issue_remote(issue_md, local_id, cfg)` and **not** `.chia_remote`, asserted on the source: `run_issue_remote` carries its own `@ChiaFunction(resources={"circt": 1})`, so dispatching it would land the chain on a `circt` worker and defeat the whole reason `bugloop_repair` exists. Called directly it runs in the caller's own process, so the chain and the three tools it stands up all land on the `repair:1` worker B8 is already on | none | T0 | FR-12.1, FR-12.11 |
| `T-U-repair-18` | **The repro directory is outside the CIRCT tree.** `cfg["repro_dir"]` is `<artefact_root>/<run>/repair/<local_id>/` and `cfg["repro_path"]` is `repro.sh` in it; neither path lies under `/workspace/circt`. Driven end to end: `git clean -fd` in the tree, which is the chain's own first action and which deletes CHIA's default `/workspace/circt/.circtissues` because that directory is untracked and matches nothing in CIRCT's `.gitignore`, leaves both files present. `issue_task.py` is untouched by this, the directory being read at four points and every one being `cfg["repro_dir"]` or `cfg["repro_path"]`; its only change is the additive `vertex` arm of `T-U-repair-07`, which is in `_turn` | `repair/` | T1 | FR-12.3, FR-12.1 |
| `T-U-repair-19` | **`repro_overwritten` is measured, not assumed.** B8 takes `sha256` of `repro.sh` before the chain starts and again after the reproduce turn's `circt_run_script` has run, writes both to `repro.sh.sha256.before` and `.after` beside it, and sets `repro_overwritten` on a difference. Both branches are exercised, with a stubbed turn that rewrites the script and one that does not. FR-12.3's "confirms rather than invents" is thereby **reported per attempt**; its polarity half stays guaranteed, because `require_repro` is `True` and the first run on the clean tree must exit non-zero for the chain to continue | `repair/` | T0 | FR-12.3 |
| `T-U-repair-20` | **Stage 7 is handed the campaign backend** (rewritten 2026-09-14). `cfg["backend"]` is `cfg["repair_backend"]`, which **defaults to `vertex`**, so on a default run it equals `manifest.backend`; `cfg["model"]` is the model-id half of `manifest.model_ids["repair_adapt"]`, which is `vertex:<budget.yaml's model_id>`, and its backend half equals `cfg["repair_backend"]`; and `stages_metered["stage_7"]` is **true**. Both directions are exercised: under `--repair-backend claude` the pair diverges, `model_ids["repair_adapt"]` reads `claude:<the passed model>`, and `stages_metered["stage_7"]` goes **false**, which is FR-14.8's rule and not an exception to it. `--no-repair` leaves F-12's rows empty with `repair_disabled` recorded and changes no gate answer. ~~with `manifest.backend == "vertex"` the value passed is one of `claude`, `antigravity` or `opencode` and never `vertex`~~ is **withdrawn**: `vertex` is now a value the chain implements | `run_manifest/` | T0 | FR-12.1, FR-14.8 |
| `T-U-repair-21` | **The patch applies to CHIA and only to `_turn`.** `upstream/issue_task-vertex-branch.patch` applies to a checkout at `16c35e92` with `git apply --check` and then with `git apply`, both exiting 0; the patched file parses; `git diff --numstat` reads `19 0`; and `git diff` touches **one** path, `examples/circt_issue_solver/issue_task.py`. The negative control is the second application: `sync-to-chia.sh` run twice leaves the checkout byte-identical, the already-present guard of `03-LLD.md` §1.4 stopping the second apply rather than doubling the branch or failing the sync | `repair/chia_baseline.json` | T1 | FR-12.1, FR-19.2 |
| `T-U-repair-22` | **The branch builds the express client, mocked.** With CHIA's own fake `genai.Client` (`chia:chia/models/tests/test_vertex.py:78-97`, the `fake_vertex` fixture), `_turn` called with `cfg["backend"] == "vertex"` constructs a `VertexGeminiLLM` whose `project` **is `None`** and whose `location` **is `None`** after construction, whose `client_kwargs["api_key"]` is `$GEMINI_API_KEY`, and whose `client_kwargs["http_options"]["timeout"]` is `cfg["timeouts"][phase] * 1000`, in **milliseconds**; the built client's `_http_options.timeout` carries that number and its `project` and `location` are both `None`. Three negative controls: without the two nulling assignments the real `google-genai` raises `ValueError: Project/location and API key are mutually exclusive in the client initializer.`, asserted with the real library and no network; with `cfg["backend"]` unset the `else` arm still builds a `ClaudeCodeLLM`, so CHIA's default is untouched; and with `cfg["backend"] == "antigravity"` or `"opencode"` the existing arms are taken unchanged. `GEMINI_API_KEY` is a dummy and no request is made: tier T0, `BUGLOOP_ALLOW_LIVE_MODEL` unset throughout, `_turn` being exercised directly rather than through `repair_adapt`. **The interlock half is asserted on `repair_adapt` itself**: with `BUGLOOP_ALLOW_LIVE_MODEL` unset it raises `LiveModelRefused` and **never calls `run_issue_remote`**, asserted with the chain patched to a sentinel that fails the test if called; with the variable set to `1` and `GEMINI_API_KEY` unusable it refuses on the key half when the repair backend is `vertex` and proceeds when it is `claude`. Without that call stage 7 would be the one path to a model the interlock does not cover | `vertex/` | T0 | FR-12.1, NFR-08 |
| `T-U-repair-23` | **Stage 7's tokens are null, and the reason is recorded rather than zero.** The stage-7 `LedgerEntry` carries `observed.tokens_in`, `observed.tokens_out` and `observed.cost_usd` **null** with `metered` **true**, and `RepairResult.token_capture` reads `unavailable_remote_dispatch` with `RepairResult.backend` reading `vertex`. Asserted that the reason is **not** a key of `observed`: the four declared keys of `_DICT_KEYS[("LedgerEntry", "observed")]` are unchanged and a fifth fails validation, so the contract stays at **2.0**. Asserted that zero is never written for an unobserved count. The mechanism is asserted on the source too, so the gap cannot be closed by accident and then silently reopened: `issue_task.py:124` is still `get(llm.prompt.options(...).chia_remote(llm, prompt, tools))`, which is what makes `_last_metadata` unreachable, and `results.py` prints the USD total as a lower bound excluding stage 7 | `ledger/vertex/`, `repair/` | T0 | FR-12.1, FR-14.6, FR-14.8 |
| `T-U-repair-14` | The loop's row is written **first**, carrying the local identifier; killing the chain between the two writes leaves the loop row present and the reconciliation marks it `repair_row_missing`, with no join key dangling unmarked | `repair/issues.db` | T0 | FR-12.10 |
| `T-U-repair-15` | `PHASE_TIMEOUTS` is CHIA's own dict verbatim, and the chain is invoked with it unaltered | none | T0 | FR-12.1 |

### 1.13 `gate.py` (B9a, B9b), 26 tests

**Callables covered:** `gate_decide` and `gate_rerun`.

`01-FRD.md` §10.3 items 16 and 17 both land here, plus the four questions and the default-refuse rule.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-gate-01` | The four questions are asked in order and the gate stops at the first "no"; each answer and the stopping point are recorded for every candidate | `candidate/` | T0 | FR-13.1 |
| `T-U-gate-02` | `gate_decide` declares no worker resource (its `_chia_options` carries none), so it can never hold a `circt` slot while waiting for one; and it dispatches `gate_rerun` as a task of its own | none | T0 | FR-13.2 |
| `T-U-gate-03` | The re-run is dispatched with `NodeAffinitySchedulingStrategy(node_id=<other>, soft=True)`; with only one live `circt` node the re-run still happens and `same_worker=True` is recorded truthfully | none | T0 | FR-13.2 |
| `T-U-gate-04` | Worker identity (hostname plus Ray node id) and process id are recorded for **both** runs: the original half is read from `BuildResult.worker_hostname`, `worker_node_id` and `child_pid`, which `probe_execute` wrote (`T-U-probe-43`), and the re-run half from `gate_rerun`'s own return; `q1_same_worker` is `original_node_id == rerun_node_id` and is computable, which it was not before those three fields existed. The count of same-worker re-runs is available for the results artefact | none | T0 | FR-13.2 |
| `T-U-gate-05` | Question 1 fails when the re-run's class, assertion text or `file:line` differs from the original's; the bucket is `unreproducible` | `gate/rerun_differs/` | T0 | FR-13.1, FR-18.6 |
| `T-U-gate-06` | Question 2 passes when a reducer ran to a **fixpoint** and the re-check preserved class, text and site | `reduced_case/fixpoint.json` | T0 | FR-13.3 |
| `T-U-gate-07` | Question 2 fails as `not_minimal` for `reduced=false`, with the reason recorded | `reduced_case/not_reduced.json` | T0 | FR-09.12, FR-13.3 |
| `T-U-gate-08` | Question 2 fails as `not_minimal` for `reduction_changed_failure` | `reduced_case/changed.json` | T0 | FR-09.7, FR-13.3 |
| `T-U-gate-09` | Question 2 fails as `not_minimal` when no reducer could run at all; no input to this question is ever null | `reduced_case/none.json` | T0 | FR-13.3 |
| `T-U-gate-10` | Question 3 passes on exit 0 of the per-language check | `gate/valid/` | T1 | FR-13.15 |
| `T-U-gate-11` | Question 3 passes with `validity_basis=checker_failed` when the check itself fires the primary oracle | `gate/checker_fires/` | T1 | FR-13.15 |
| `T-U-gate-12` | Question 3 fails as `invalid_input` on a clean non-zero exit with a diagnostic; the exit status and stderr are persisted with the `GateDecision` | `gate/invalid/` | T1 | FR-13.15 |
| `T-U-gate-13` | The three check commands are exactly `circt-opt <case> -o /dev/null`, `firtool --parse-only <case>` and `circt-verilog --import-only <case>`; no pass pipeline and no `--allow-unregistered-dialect` is ever passed, asserted on the recorded argv; `-o /dev/null` is passed so the check writes nothing; and `--import-only` is used for `.sv` rather than `--parse-only`, which stops before elaboration and would accept SystemVerilog that elaboration rejects. Each runs under the same `prlimit` prefix as a probe | `gate/` | T1 | FR-13.15 |
| `T-U-gate-14` | Question 4 passes on `new` and fails on each of the other five dedup values, `dedup_unavailable` and `dedup_basis=insufficient` included | `dedup/verdicts/` | T0 | FR-10.7, FR-10.8, FR-13.5 |
| `T-U-gate-15` | **The triage classification changes nothing.** Holding every other field fixed and setting the classification to each of `bug`, `invalid_input`, `known_issue` and `untriaged` in turn produces identical answers and an identical `GateDecision`; and no gate question reads the field, asserted by an `ast` search | `candidate/` | T0 | FR-11.8, FR-13.4, NFR-03 |
| `T-U-gate-16` | `report_plus_patch` when a `RepairResult` has `fixed=true` **and** `lit_ok=true`; `report` otherwise, both branches exercised | `repair/verdicts/` | T0 | FR-13.6 |
| `T-U-gate-17` | **The default-refuse rule.** A candidate with any null answer receives `nothing`, whatever the other three say | `candidate/null_answer.json` | T0 | FR-13.10 |
| `T-U-gate-18` | A candidate refused at any question is persisted in full with its failing question, so the taxonomy's counts sum to the candidate count | `candidate/` | T0 | FR-13.11, FR-18.6 |
| `T-U-gate-19` | The gate's input set contains no `differential` candidate; one fed deliberately is refused before question 1 and carries no `GateDecision` | `candidate/differential.json` | T0 | FR-08.10, FR-13.14 |
| `T-U-gate-20` | **The taxonomy mapping.** Every one of the twelve stopping values of FR-18.6's table is produced by some code path and lands in exactly the stated bucket; no path produces a value absent from the table, asserted by enumerating the union of every stopping value the gate can write | `candidate/taxonomy/` | T0 | FR-18.6 |
| `T-U-gate-21` | `gate_rerun` runs in a **fresh process** with a **newly created** `tempfile.mkdtemp(dir=<artefact_root>/<run>/gate/)` directory per call, never reused, and carries no state from the original run | none | T1 | FR-13.2 |
| `T-U-gate-22` | `gate_rerun` performs the same hash-manifest check as `probe_execute` and raises `BinaryMismatch` on a difference | `image_spec/ok.json` | T1 | FR-06.1 |
| `T-U-gate-23` | **FR-13.15's second conjunct, `q3_after_parse`.** It is answered from fields the record already has and runs **no fourth command**: the recorded failure occurred after parsing exactly when `OracleVerdict.fingerprint_frame`'s file is not under `lib/Parser/`, `lib/AsmParser/`, `tools/circt-translate/` and does not match CIRCT's own `*Parser*.cpp`, **or** when the check's own exit was 0 while the probe's argv carried a pass pipeline. `False` fails question 3 as `invalid_input` with text naming the parser frame; `True` and `None` are both exercised. Before this revision the conjunct had no field, no record and no check anywhere | `gate/` | T1 | FR-13.15 |
| `T-U-gate-24` | **The re-run sets `fingerprint_stable`.** Question 1 recomputes the fingerprint from the re-run's own stderr by the rule of `03-LLD.md` §3.7.1 and compares the string; equality sets `true`, a difference sets `false`. `false` does **not** fail question 1, which asks only whether the recorded failure reproduces, and both branches are asserted to leave `q1_reproduce` unchanged | `gate/rerun_differs/`, `fingerprint/unstable/` | T0 | FR-10.1, FR-13.1 |
| `T-U-gate-25` | **The two mirror verdicts are reachable and both fail question 4.** A candidate carrying `known_open_issue` and one carrying `known_closed_issue`, each produced by §3.7.3's screen rather than constructed, each fails question 4 with the issue number in the reason; both values were unreachable before the screen was defined, so this test could not have been written against the earlier LLD | `dedup/known_issue/` | T0 | FR-10.3, FR-13.5 |
| `T-U-gate-26` | **Question 3 runs at `candidate.run_commit`.** Against a calibration manifest with two entries, the three check commands execute against the binaries of the candidate's **own** commit and never `manifest.run_commit[0]`'s, asserted on the recorded working tree and the recorded argv | `run_manifest/calibration_two.json` | T1 | FR-02.7, FR-13.15 |

### 1.14 `approve.py` (B9c), 14 tests

**Callable covered:** `approve.main`.

Driven by feeding `stdin` and capturing `stdout`; the CLI is `input()` and `print()` with no
framework (ADR-D-12), so it is wholly tier 0.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-appr-01` | **The per-day cap.** With `filings_per_day` 1 and one filing already recorded for the current UTC day, the second candidate is **held** and the refusal happens **before** anything is shown to the human | `approve/store_one_filed.db` | T0 | FR-13.8 |
| `T-U-appr-02` | The total cap `filings_total` is enforced the same way, before presentation | `approve/store_at_total.db` | T0 | FR-13.8 |
| `T-U-appr-03` | **The `good first issue` refusal.** A candidate whose `dedup_evidence.issue_labels` carries `good first issue` is refused whatever the rest of the gate said, with that label named as the reason, and no filing is possible as an issue, a comment or a fix. The labels come from §3.7.3's mirror screen, which is what gives this refusal a producer for the first time: before the screen was defined, `issue_labels` was populated by nothing | `approve/gfi_candidate.json` | T0 | FR-13.9, FR-20.2 |
| `T-U-appr-04` | A candidate held under FR-11.8 with `held_reason=no_report` is not presented | `approve/untriaged.json` | T0 | FR-11.8 |
| `T-U-appr-05` | A second approval of an already-approved candidate is refused, naming the first approval's timestamp | `approve/store_one_filed.db` | T0 | FR-13.13 |
| `T-U-appr-06` | **Approval does not generalise.** Two pending reports require two separate approvals; approving one leaves the other pending | `approve/two_pending.db` | T0 | FR-13.13 |
| `T-U-appr-07` | The licence confirmation is taken **with the patch on screen** whenever the decision is `report_plus_patch`; a decline downgrades the decision to `report`, does not offer the patch, and records the decline | `approve/with_patch.json` | T0 | FR-20.5, NFR-11 |
| `T-U-appr-08` | **The walk-away.** Interrupting between presentation and the typed `yes` writes nothing: the candidate stays `held` with `held_reason=awaiting_approval`, the store is byte-identical, and the next invocation presents the same report | `approve/two_pending.db` | T0 | FR-13.7 |
| `T-U-appr-09` | `show` prints all four elements in one view: the full rendered report, the four gate answers with the stopping question, the repair diff if any, and the reduced case | `approve/with_patch.json` | T0 | FR-13.12 |
| `T-U-appr-10` | **The pre-filled URL.** A report under the limit produces `https://github.com/llvm/circt/issues/new?title=...&body=...`; one whose rendered URL exceeds `PREFILL_URL_CHAR_LIMIT` (6,000) produces the fallback instruction and records `prefill_fallback_reason` and `prefill_url_length` | `report/short.md`, `report/long.md` | T0 | FR-13.17 |
| `T-U-appr-11` | **The URL paste, with the conjunction on the accept side.** `url <candidate_id> <issue_url>` records against the same report id with `url_source="pasted"`. A URL is accepted only when its scheme **is** `https`, its host **is** exactly `github.com`, its path **begins** `/llvm/circt/issues/` and it **ends in digits**; four refusal cases are exercised, including `https://github.com/llvm/circt/pulls/1` and `https://github.com/other/repo/issues/1`. The earlier wording put the conjunction on the refuse side and would have accepted a `github.com` URL with any path at all | `approve/two_pending.db` | T0 | FR-13.18 |
| `T-U-appr-12` | The `filing` row carries the approver's name, the timestamp, the decision and the licence confirmation with its own timestamp; a `report_plus_patch` without a recorded confirmation is downgraded by the code path | `approve/with_patch.json` | T0 | FR-13.7, FR-20.5 |
| `T-U-appr-13` | FR-13.16's poll matches a recorded issue body carrying the report's primary fingerprint and completes the `FilingRecord` with `url_source="poll"`, using a GET only; an empty poll after `filing_poll_window_seconds` falls back to the paste and the fallback is recorded | `mirror/filed_issue.jsonl` | T0 | FR-13.16, NFR-04 |
| `T-U-appr-14` | **Nothing files by default.** No `filing` row exists without an approval, only `approve` writes one, and a full run with no approvals produces zero filings | `approve/two_pending.db` | T0 | FR-13.7, FR-20.6 |

### 1.15 `budget.py` (A6a), 13 tests

**Callables covered:** `load_budget` and `snapshot`.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-budget-01` | A file missing any key of `03-LLD.md` §9.1 is rejected, naming the key; all **27** keys are exercised one at a time, the four added on 2026-09-14 included | `budget/missing/` | T0 | FR-14.1 |
| `T-U-budget-02` | A file carrying any other top-level key is rejected, naming it | `budget/extra_key.yaml` | T0 | FR-14.1 |
| `T-U-budget-03` | Every key's type is checked as declared; a string where a float belongs is rejected | `budget/bad_types/` | T0 | FR-14.1 |
| `T-U-budget-04` | An **uncommitted** `budget.yaml` exits non-zero naming the offending commit | `repo/uncommitted/` | T0 | FR-14.2 |
| `T-U-budget-05` | A budget file whose commit **post-dates** the run's start exits non-zero naming both timestamps | `repo/later_commit/` | T0 | FR-14.2 |
| `T-U-budget-06` | `budget_file_sha` is the SHA `git log -1 --format=%H -- budget.yaml` returns, and that SHA reaches `RunManifest.budget_file_sha` | `repo/preregistered/` | T0 | FR-14.3 |
| `T-U-budget-07` | The mutator set's last commit must predate the budget file's; a later one is refused | `repo/mutator_after/` | T0 | FR-05.2 |
| `T-U-budget-08` | **Mid-campaign change.** Amending the file after the manifest is stamped makes the next stage refuse with that message and invalidates the campaign | `repo/preregistered/` | T0 | FR-14.7 |
| `T-U-budget-09` | `snapshot` returns a `LedgerSnapshot` with exactly `arm`, `unit`, `spent` and `cap`, and the generator can reach no other budget state; asserted by the dataclass's field list | none | T0 | FR-16.4 |
| `T-U-budget-10` | `03-LLD.md` §9.5's complete file is accepted with no key missing and no key extra; equality on the unit and on both safety caps is structural, there being no per-arm value to be unequal. The two values this revision moved are asserted at their new figures: `reduction_wall_seconds` 600, not 60, and `artefact_inline_cap_bytes` 262,144, not 10,485,760 | `budget/complete.yaml` | T0 | FR-14.1, FR-14.5 |
| `T-U-budget-11` | **Check 5, the calibration sample.** `budget.py` refuses a file where `len(calibration_sample_shas) != calibration_sample_size`, and refuses one whose entries are not all drawn from the 171 exact-pin seeds. The check exists because the sample is part of the pre-registration: the commit that lands `budget.yaml` **is** the registration and FR-14.7 invalidates the campaign on any later edit, so a sample drawn afterwards invalidates the campaign and a sample drawn before must be in the file. The empty-list case, which the earlier §9.5 shipped, is refused | `budget/empty_sample.yaml`, `budget/complete.yaml` | T0 | FR-14.1, FR-14.2 |
| `T-U-budget-12` | **Check 6, the pair of prices.** A file whose `price_usd_per_m_input_tokens` or `price_usd_per_m_output_tokens` is absent, zero, negative, `nan`, `inf` or a string is refused naming which; so is a non-positive `campaign_spend_cap_usd` and an empty `model_id`. The **pair** is the point and the test says so: a file carrying one price and not the other would value half the campaign's tokens at zero, so the ledger would under-report the spend it is meant to stop on, and check 2's "every key present" is not the same assertion as "both prices usable". `budget.py` makes **six** checks from 2026-09-14 and the test asserts the count | `budget/bad_prices/` | T0 | FR-14.1, FR-14.6, NFR-08 |
| `T-U-budget-13` | **The four keys of 2026-09-14 reach their consumers.** `BudgetFile.model_id` is what `build_llm` is called with and what `RunManifest.model_ids` records as the model half of `vertex:<id>`; `campaign_spend_cap_usd` is what `ledger.stop_reason` compares against; the two prices are what `ledger.price` multiplies by. Asserted by loading `03-LLD.md` §9.5's complete file and following each value to the one call site that reads it, so a key that is declared and never consumed fails | `budget/complete.yaml` | T0 | FR-14.1, FR-14.6 |

### 1.16 `ledger.py` (A6b), 11 tests

**Callables covered:** `accrue`, `aggregate`, `stop_reason` and, from 2026-09-14, `price`.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-ledger-01` | `arm` takes exactly `seeded`, `mutation` or `shared`; a fourth value is rejected by the schema | `ledger/` | T0 | FR-14.4 |
| `T-U-ledger-02` | `scope` takes exactly `arm_window` or `stage` | `ledger/` | T0 | FR-14.4 |
| `T-U-ledger-03` | Exactly one `arm_window` entry exists per arm per run, and its `amount` is that arm's spend on the primary unit | `ledger/` | T0 | FR-14.4, FR-14.5 |
| `T-U-ledger-04` | **Per-arm sums exclude `shared`.** A ledger holding the image build, the mirror, the corpus, the pin selection and the mutator synthesis as `shared` reports them beside the two arms, never folded into one and never split between them | `ledger/shared/` | T0 | FR-14.4 |
| `T-U-ledger-05` | Per-stage occupancy may exceed the window where stages overlap, and is reported as an observation rather than treated as the budget | `ledger/overlap/` | T0 | FR-14.4 |
| `T-U-ledger-06` | **The arm window.** `stop_reason` returns the window when the elapsed wall clock reaches `arm_window_seconds`, the binding cap when a safety cap binds first, and `None` otherwise; with `generated_inputs_per_day` set to 5 the arm stops after 5 inputs and the ledger shows the stop reason | `budget/complete.yaml` | T0 | FR-14.4, FR-18.10, NFR-08 |
| `T-U-ledger-07` | `accrue` is append-only; a repeated `entry_id` is **detected** rather than absorbed | `ledger/` | T0 | FR-14.4 |
| `T-U-ledger-08` | `observed` carries `cpu_seconds`, `tokens_in`, `tokens_out` and `cost_usd`. **On the campaign's `vertex` backend all four are populated**: a `LedgerEntry` accrued from an `llm_turn` return carries the turn's prompt and output tokens and a `cost_usd` the ledger computed, `metered` is true, and `stages_metered` declares the stage metered. They are null, `metered` false and the stage declared unmetered only on the `claude` fallback, which reports no per-phase usage. ~~and `stage_7` is declared unmetered whenever the repair backend differs from `RunManifest.backend`, which under this decision it does~~ is **rewritten 2026-09-14**: stage 7 now runs on `vertex` too, so it is declared **metered**, and it is the one stage on the campaign backend whose four are nevertheless **null**, because CHIA's `_turn` dispatches remotely and the counts die with the worker copy. The test asserts that disagreement explicitly, `metered` true beside null tokens, so that "populated on the campaign backend" is not read as a rule stage 7 violates silently; `T-U-repair-23` owns the reason field | `ledger/vertex/`, `ledger/claude/` | T0 | FR-14.6, FR-14.8 |
| `T-U-ledger-09` | A negative `amount` is rejected | `ledger/` | T0 | FR-14.4 |
| `T-U-ledger-10` | **`price`, the ledger's own arithmetic.** `price(tokens_in, tokens_out, budget)` is `tokens_in / 1e6 * price_usd_per_m_input_tokens + tokens_out / 1e6 * price_usd_per_m_output_tokens`, rounded to six decimal places: at the committed 0.75 and 3.75, one million prompt tokens and one million output tokens cost 4.50, and 11 prompt plus 7 output tokens cost 0.000034. `price` returns `None` when either count is `None`, and `accrue` then writes `cost_usd` null with `metered` false rather than writing a zero, because a zero is a measurement and a null is an absence. **The money comes from `budget.yaml` and never from the backend**, which reports token counts and no price at all, asserted by feeding a fake usage dict carrying an extra `cost` key and showing it is ignored | `budget/complete.yaml` | T0 | FR-14.6 |
| `T-U-ledger-11` | **The USD cap is a third stop condition, and it is campaign-wide.** With `campaign_spend_cap_usd` 0.01 and entries summing past it, `stop_reason` returns `campaign_spend_cap` for **both** arms, whichever arm the entries were charged to and including `shared` entries, while the arm window and both safety caps are still unbound. The precedence is asserted in both directions: a window that expires first returns the window, a spend that crosses first returns `campaign_spend_cap`. `BudgetLedger.spend_usd` is the campaign-wide sum and `per_arm_spend_usd` is the per-arm split reported beside each window, and the cap is compared against the former, never the latter, because the money cap protects a credit balance rather than the comparison | `ledger/shared/`, `budget/complete.yaml` | T0 | FR-18.10, NFR-08 |

### 1.17 `feedback.py` (A5), 8 tests

**Callable covered:** `build_feedback`.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-feed-01` | **One entry per probing input.** Every input of the previous iteration appears in the bundle exactly once, including inputs that exited cleanly, parsed badly, timed out or exhausted memory; the bundle is built from `ProbeResult`s and never from `CandidateRecord`s | `probe_result/iteration/` | T0 | FR-16.1 |
| `T-U-feed-02` | A dispatched probe with no `ProbeResult` appears with `stopping_reason=result_missing` rather than being absent, which is what keeps the set difference honest | `probe_result/iteration/` | T0 | FR-16.1 |
| `T-U-feed-03` | **The abandonment rule, spelled as a multiset.** `abandoned=true` when, for **two consecutive iterations**, every `ProbeResult` has `build_status` in `{parse_error, timeout, oom}` **and** the multiset of `(build_status, stopping_reason)` pairs is equal between the two. "The same reason" is the **pair** and not the status alone, because `parse_error` covers both a rejected input and a rejected argv, and abandoning a seed for the second would hide an apparatus defect as a seed property; the negative case, two iterations of `parse_error` with different `stopping_reason` multisets, is exercised and must **not** abandon. `abandon_reason` is the repeated pair rendered `"stage_3:<status>:<reason> x<n>"` | `feedback_bundle/abandon/` | T0 | FR-16.6, FR-06.6 |
| `T-U-feed-04` | `abandon_reason` is non-null exactly when `abandoned`, enforced by the validator and by the builder | `feedback_bundle/` | T0 | FR-16.6 |
| `T-U-feed-05` | **The deny-list, as `_FEEDBACK_DENY`.** No field name of `FeedbackBundle` or `FeedbackEntry`, at any nesting depth, is one of its twenty-one names, and no **value** in a built bundle is a `CandidateRecord`, `DedupVerdict` or `GateDecision`. The tuple is a deny-list of names rather than a schema because FR-16.4's own criterion names three groups, candidate counts, gate precision and bug counts, and those are its three clusters | `feedback_bundle/` | T0 | FR-16.4 |
| `T-U-feed-06` | **No apparatus imports.** The generator half's module set imports no `OracleVerdict`, `ReducedCase` or `CandidateRecord`; asserted by an import walk over `generate_task.py`, `mutators/`, `feedback.py`, `budget.py` and `ledger.py` | none | T0 | FR-16.1 |
| `T-U-feed-07` | All three terminating conditions are exercised and `terminating_condition` is recorded: the per-seed iteration cap, the per-seed input cap, and the arm's allowance on the primary unit | `feedback_bundle/` | T0 | FR-16.3 |
| `T-U-feed-08` | Replaying iteration k from its recorded `SeedRecord` plus `FeedbackBundle` through `Template.safe_substitute` reproduces the prompt **bytes** exactly | `feedback_bundle/`, `seed_record/` | T0 | FR-16.5 |

### 1.18 `store.py` (B10a, B10b), 13 tests

**Callables covered:** `LoopStore` and its seven members, `init_schema`, `artefact_write`,
`validate_candidate` and `load_candidate`.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-store-01` | `init_schema` creates every table of `03-LLD.md` §6.2 and every index of §6.3; a second call is a no-op | none | T0 | FR-17.2 |
| `T-U-store-02` | `LoopStore` is constructed with `pin_to_current_node=True` and an absolute **local** path; a network path is refused | none | T0 | FR-17.3 |
| `T-U-store-03` | An artefact larger than `artefact_inline_cap_bytes` (**262,144**, which is 256 KiB and was 10,485,760) is written to disk and the row holds its path; nothing over the cap is inlined into a row or a task return value. The old figure contradicted `SQLiteNode`'s own guidance that `03-LLD.md` §6.5 quotes: a 9 MB `input_text` would have passed `bound_text`, ridden the Ray object store and landed in `probe.spec_json`. The same number caps a `SourceReadTool` return and a `SeedRecord`'s `diff` and `test_files`, and the test asserts one constant serves all three | none | T0 | FR-17.7 |
| `T-U-store-04` | The `PARTIAL` marker is a zero-byte file written **before** anything else in a directory and removed as the stage's last act; a killed stage leaves it, with whatever it had written, and nothing is deleted | none | T0 | FR-17.8 |
| `T-U-store-05` | `artefact_write` refuses to remove a marker for a directory whose completion record is absent from the store, so a passing stage cannot clear another stage's marker | none | T0 | FR-17.8 |
| `T-U-store-06` | `run_manifest_id` is present on every table and on every directory, so a row traces to its image, commit, budget file and arm | none | T0 | FR-17.6 |
| `T-U-store-07` | Every row's `artefact_dir` exists on disk; one row per candidate and one per probing input, with the foreign keys that join them | `probe_result/iteration/` | T0 | FR-17.2 |
| `T-U-store-08` | The two write-order rules of `03-LLD.md` §6.4 hold, including the loop-row-before-CHIA-row rule of FR-12.10 | `repair/issues.db` | T0 | FR-12.10 |
| `T-U-store-09` | **`validate_candidate`'s class table, row by row.** Every row of `03-LLD.md` §2.9's table is exercised in both columns: a `differential` candidate carrying any reduction, dedup or gate field raises `E006_CONDITIONAL_FORBIDDEN` naming the field and the class; any other class reaching the gate with one of them `None` raises `E005_CONDITIONAL_REQUIRED`; `assertion_text` and `assertion_site` are non-null exactly on `oracle_class == "assertion"`; and the contamination and frame fields are required in **both** columns, a `differential` candidate's `frame_tuple` being the empty list, which is a value and not a `None`. The function is asserted idempotent and side-effect free, four calls on one object behaving as one | `candidate/` | T0 | FR-08.10, FR-10.5, FR-13.14 |
| `T-U-store-10` | **The secret grep.** No token, key or credential appears in any row or any file the store writes, over a full fixture run; see also `T-N-nfr06-01` | `secrets/known_values.txt` | T0 | FR-17.5, NFR-06 |
| `T-U-store-11` | **`load_candidate` reassembles.** `candidate` persists twenty of `CandidateRecord`'s forty-one fields and the rest live in `oracle_verdict`, `reduced_case`, `fingerprint`, `dedup_verdict` and `gate_decision`; `load_candidate` joins all six back into the object `validate_candidate` checks, and one candidate of **every** oracle class round-trips through it unchanged. It is the only reader of those five tables that returns a `CandidateRecord` | `candidate/` | T0 | FR-10.5, FR-17.2 |
| `T-U-store-12` | **The three codes `store.py` adds.** `E011_BAD_EVIDENCE_KEYS` when `dedup_evidence`'s key set differs from `_DEDUP_EVIDENCE_KEYS`, with the symmetric difference listed so a missing key and an extra one are distinguishable; `E012_FINGERPRINT_BASIS` when `(fingerprint is None) != (dedup_basis == "insufficient")`; `E013_MISSING_EVIDENCE` when a key `_DEDUP_EVIDENCE_REQUIRED[dedup_verdict]` names is present and `None`, naming the verdict and every missing key. All three are `contract.ContractError`, so a caller catches one class across both validators, and none of `E001`, `E007`, `E008`, `E009` or `E010` is ever raised from here | `candidate/`, `dedup/verdicts/` | T0 | FR-10.5, FR-10.8 |
| `T-U-store-13` | **The DDL enforces the fingerprint rule too.** `INSERT INTO fingerprint` with a non-null `value` and `basis = 'insufficient'`, and with a null `value` and `basis = 'frames'`, are both rejected by the table's `CHECK ((value IS NULL) = (basis = 'insufficient'))`, so FR-10.8 holds once in Python (`E012`) and once in SQL and a writer that bypasses either still meets the other | none | T0 | FR-10.8 |

### 1.19 `results.py` (B11), 21 tests

**Callables covered:** `render_results` and the fourteen `_require_*` checks.

Tests 01 to 14 are the fourteen named refusal checks, one each, in the order `03-LLD.md` §3.11's
`_REFUSALS` tuple gives and §14.4's table repeats. All are tier 0: `render_results` is a pure function
of the store.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-results-01` | `_require_headline`: distinct confirmed bugs per arm, counted per primary fingerprint, populated only from `filing` rows carrying maintainer evidence with a URL; two filings sharing a fingerprint count once | `results/store_full.db` | T0 | FR-18.3 |
| `T-U-results-02` | `_require_secondaries`: all five per arm, each computable from the store alone, **plus the count of repair attempts whose `repro_overwritten` is true**, because FR-12.3's "confirms rather than invents" is reported per attempt rather than guaranteed | `results/store_full.db` | T0 | FR-12.3, FR-18.4 |
| `T-U-results-03` | `_require_validation_table`: the seeded-bug validation table is separate and contributes nothing to the headline | `results/store_full.db` | T0 | FR-18.5 |
| `T-U-results-04` | `_require_qualifiers`: **every** table names the mode and the seed set; a table missing either fails the render, naming the missing qualifier | `results/store_full.db` | T0 | FR-18.2 |
| `T-U-results-05` | `_require_contamination`: the contamination column is present and the headline is printed both with and without contaminated candidates | `results/store_full.db` | T0 | FR-15.2 |
| `T-U-results-06` | `_require_disclosures`: both sentences are present, the screen's incompleteness and the repair stage being unscreened | `results/store_full.db` | T0 | FR-15.3, FR-15.4 |
| `T-U-results-07` | `_require_lag`: the lag the campaign ran under is printed beside the headline | `results/store_full.db` | T0 | FR-02.2 |
| `T-U-results-08` | `_require_cutoff`: the confirmation cut-off date is present, and the artefact states that maintainer confirmation lags the budget window | `results/store_full.db` | T0 | FR-18.8 |
| `T-U-results-09` | `_require_dedup_rates`: the collision and false-merge rates are printed **beside the headline they qualify**, **and so is the count of candidates whose `fingerprint_stable` is false**, because an unstable fingerprint qualifies the headline exactly as a collision does | `results/store_full.db` | T0 | FR-10.1, FR-10.2 |
| `T-U-results-10` | `_require_divergences`: the divergences-observed list is present | `results/store_full.db` | T0 | FR-18.12 |
| `T-U-results-11` | `_require_mutator_declaration`: the declaration names the synthesis input, the synthesis date and the frozen set's SHA, and states that this is Mut4All's design | `results/store_full.db` | T0 | FR-05.8 |
| `T-U-results-12` | `_require_observed_heading`: tokens, cost and CPU time appear under a heading that states they are **not** the budget | `results/store_full.db` | T0 | FR-14.5 |
| `T-U-results-13` | `_require_both_windows`: both arms' elapsed windows are printed, with the binding cap and the unspent balance where one bit | `results/store_capped.db` | T0 | FR-18.10 |
| `T-U-results-14` | `_require_regeneration_marks`: a row that could not be regenerated is **marked** rather than reported | `results/store_marked.db` | T0 | FR-18.11 |
| `T-U-results-15` | **The empty-confirmation render (FR-18.7).** With an empty confirmation set the render **succeeds** and states the zero for both arms; every other mandatory element is still present, and no refusal fires for want of a confirmed bug | `results/store_zero.db` | T0 | FR-18.7 |
| `T-U-results-16` | No sentence compares the loop's count to FLEX, ISSTA-2024, Nuwa or DESIL; checked by a name search over the rendered text | `results/store_full.db` | T0 | FR-18.9 |
| `T-U-results-17` | The taxonomy's six buckets sum to the candidate count, and the repair-phase counts sum to the repair-attempt count; `differential` candidates appear in neither denominator. The `parse_error` row is printed as **two** counts, `tool_rejected_input` and `tool_rejected_argv`, so the row is never read as "the tool rejected the input" when it means "the loop built an argv the tool would not take"; the two sum to the `parse_error` total | `results/store_full.db` | T0 | FR-06.6, FR-18.6, FR-13.14 |
| `T-U-results-18` | `arm` is branched on here and in `ledger.py` only; the module is exempt from `T-U-layout-02`'s walk by name, and this test asserts the exemption is used for the results table and nothing else | none | T0 | FR-18.1 |
| `T-U-results-19` | The divergences list's length equals the number of `differential` reports in the store, and no entry carries a `GateDecision` or a `FilingRecord` | `results/store_full.db` | T0 | FR-08.10, FR-18.12 |
| `T-U-results-20` | Both arms' seed SHA sets are identical within a mode: 187 in discovery, 171 in calibration | `results/store_full.db` | T0 | FR-18.2 |
| `T-U-results-21` | **The count is fourteen, in both places.** `len(_REFUSALS) == 14`, the tuple's names are exactly the fourteen `_require_*` names `03-LLD.md` §14.4's table rows carry, in the same order, and `render_results` calls **every** one and collects every failure before raising, so a store missing three elements reports three rather than the first. A fifteenth name in either document, or a thirteenth, fails this test | `results/store_zero.db` | T0 | FR-18.2 |

### 1.20 `bug_loop.py` (B12, and B1's driver), 28 tests

**Callables covered:** `main`, `build_image`, `_head_node_id` and `_head_options`.

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
| `T-U-driver-20` | **FR-17.4's counters, named and summed.** Every collected return carries a `CounterBlock` under the key `counters`; its four counters are `started`, `completed`, `failed` and `seconds` and there is no fifth; `stage` is drawn from `_COUNTER_STAGES`, the eight `_STAGE_IDS` plus `image`, `corpus`, `pin`, `mirror` and `synthesis`, and a block naming anything else fails. B12 checks `started == completed + failed` per block and **logs a named violation** rather than repairing it; it hands each block to `MetricsLogger` keyed by `(run_manifest_id, arm, stage)` and rewrites `<root>/<run>/results/counters.json` on every aggregation, so a campaign stopped mid-window still leaves a complete count. Two nodes of one stage **sum**, asserted by driving two probes through `stage_3` and reading one total. `stages_metered` separately lists every stage as metered or unmetered | none | T0 | FR-14.8, FR-17.4, NFR-09 |
| `T-U-driver-21` | **`--draw-calibration`.** It prints `calibration_sample_size` SHAs sampled from the **exact-pin** set with `random.Random(corpus_head_sha)`, writes nothing at all, and exits; two invocations at one `corpus_head_sha` print the same twenty, which is what makes the draw reproducible from a value already in the file. It is a step of the pre-registration and not of the run, so the test also asserts that no `run` row is created | `corpus/pin_window_raw.json` | T0 | FR-14.1, FR-14.3 |
| `T-U-driver-22` | **`--refresh-mirror`.** Without it, a second run in the same campaign **reuses** the existing mirror and B6a is not dispatched; with it, B6a runs, `issue_mirror` is rewritten and a new `issue_mirror_meta` row is stamped, and the manifest records which run's mirror each candidate was screened against. FR-10.9's acceptance says "unless the operator asks for a refresh" and before this flag there was no asking | `mirror/` | T0 | FR-10.9 |
| `T-U-driver-23` | **`--print-config`.** It prints the resolved paths, **both** database paths, the clone, the model-credential directory §11.2 mounts, the artefact root and the image tag, and exits without dispatching. The credential directory is printed because `run_setup_commands` write `skipDangerousModePermissionPrompt` into the operator's **real** `~/.claude/settings.json` and that change outlives the campaign | none | T0 | FR-19.3, NFR-12 |
| `T-U-driver-24` | **`build_image`'s tag is the manifest's digest.** The tag is `<registry>/chia-circt-assert:<first 12 hex of sha256 over the canonical JSON of (circt_sha, sdk_tag, sorted(targets), flag_string, slang)>`; two calls agreeing on all five name the same tag and the second returns `reused=True` with **no `docker build` launched**, asserted by counting subprocess launches; changing any one of the five, `slang` included, changes the tag, so a branch-(b) image can never answer for a branch-(a) run. The **unsorted** target list is what the build receives and what `ImageSpec.targets` records | `image_spec/ok.json` | T0 | FR-03.7, FR-03.10, FR-03.13 |
| `T-U-driver-25` | **`build_image`'s eight steps and their refusals.** Each of steps 2 to 8 raises `ImageBuildError(step, detail)` naming the step and carrying the command's stderr tail, and **nothing is pushed** for any of them; the local tag is removed on `BuildTimeout` so a later run cannot reuse a half-built image under the key it would have matched. Step 3 fails when the pin check **did not run**, which is distinct from the check failing; step 4 sets `lit_discovery_ok` false and blocks publication on a non-zero `lit` exit or any `fatal: unable to parse config file` line; step 6 hashes in a **freshly started container** and not in the build tree; step 7 compares the non-referencing object list **as a set** against the committed baseline and names every difference | `image/broken_target/`, `image_spec/lit_broken.json` | T0 | FR-03.2, FR-03.5, FR-03.13, FR-03.16, FR-03.17 |
| `T-U-driver-26` | **The blobless backfill runs once, and is recorded.** B12 runs `git -C <clone> backfill --sparse` **before** the first screen and before the first seeded turn, and records that it did; the earlier "may run" left it optional, and with `SourceReadTool` and the seed diffs reading the same clone the cold-store cost would otherwise be paid by the agent's first `read_file`. Measured: the contamination scan fetched one blob per round trip at 488 s over 1,650 commits against 7 s for the bulk backfill | `corpus/clone` | T1 | FR-10.4, FR-15.1 |
| `T-U-driver-27` | **Pre-flight check 12, the interlock and the key.** The driver refuses to start when `BUGLOOP_ALLOW_LIVE_MODEL` is not exactly `1` on the head or on any `bugloop_llm` worker, and when `GEMINI_API_KEY` is empty or an unexpanded `${...}` on either, naming the worker and the variable in each of the four cases. The per-worker probe returns **two booleans and never a value**, asserted on the probe's own return type, so a check that reports a misconfiguration cannot leak the thing it is checking. `--dry-run` runs check 12 like every other check and dispatches no turn, which is how an operator confirms a cluster is ready to spend money without spending any | none | T0 | NFR-06, NFR-08, FR-17.9 |
| `T-U-driver-28` | **The manifest tells the truth about the backend.** `RunManifest.backend` is the constant `vertex` and comes from `generate_task.MODEL_BACKEND`, not from argv, there being no `--backend` flag any more; `model_ids` has four keys, each spelled `"<backend>:<model id>"`, three of them `vertex:<budget.yaml's model_id>` and the fourth the repair pair, which on a default run is **the same value**, `--repair-backend` defaulting to `vertex` since 2026-09-14; `stages_metered` has one bool per `_STAGE_IDS` entry, false for `stage_1` and `stage_2` on the mutation arm and **true for `stage_7` by default**, false for it only under `--repair-backend` naming one of the three fallbacks. A `model_ids` value with no colon, or whose model half is empty, fails the manifest build rather than the campaign | `run_manifest/` | T0 | FR-14.8, FR-18.2 |

### 1.21 `chia/chipyard/circt.py`, the three core additions, 17 tests

In `chia/chipyard/test/test_circt_probe.py`, which is a **separate** deliverable from the example's own
tests: a test under the example directory does not discharge a contribution to `chia/`
(`chia:AGENTS.md:122-124`).

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-core-01` | `circt_exec_probe` builds `["prlimit", "--as=<bytes>", "--cpu=<soft>:<hard>", "--nofile=<n>", "--", tool, *argv]` in that order, long spellings only, and never passes `--rss`, which has had no effect on Linux since kernel 2.4.30. `--cpu`'s hard value is the soft value plus `CPU_HARD_MARGIN_SECONDS`, 5, and a single-valued `--cpu` appears nowhere | none | T0 | FR-06.2 |
| `T-U-core-02` | All three limits reach the child, by the measured probe: `prlimit --as=1073741824 --cpu=5 --nofile=256 -- /bin/sh -c 'ulimit -v; ulimit -t; ulimit -n'` prints `1048576`, `5` and `256` | none | T1 | FR-06.2 |
| `T-U-core-03` | The child starts in its own process group (`start_new_session=True`) and the whole group is SIGKILLed on `TimeoutExpired`; no descendant survives, asserted by a process-table check | none | T1 | FR-06.3 |
| `T-U-core-04` | The signal is read from the child's **negative return code**, `-N` meaning signal N, and is recorded in a field separate from the exit status; a SIGABRT child records `SIGABRT` and a null exit status, never 134. The child is started with `os.fork` plus `os.setsid` plus `os.execvp` and reaped with `os.wait4` rather than through `subprocess.Popen`, for the one reason that `subprocess` does not surface `getrusage`; the process-group discipline is unchanged | none | T1 | FR-06.4 |
| `T-U-core-05` | Output is capped at `output_byte_cap` with `truncated` recorded per call | none | T1 | FR-06.4 |
| `T-U-core-06` | `FileNotFoundError` when the tool does not exist; every other failure is a returned field and not an exception | none | T0 | FR-06.1 |
| `T-U-core-07` | No `shell=True` anywhere in the three functions, and no command **string** is ever constructed; asserted on the source and on the recorded argv | none | T0 | FR-06.1 |
| `T-U-core-08` | `circt_reduce_run` builds `[circt-reduce, input, --test=<script>, -o <out>]` with `--keep-best` passed explicitly and `--test-must-fail` never passed, and passes no `--test-arg`, so the candidate is the script's `$1` | none | T1 | FR-09.2 |
| `T-U-core-09` | `output_valid` is computed **after** the process exits; a `-o` file truncated mid-write is reported invalid | `reducer/truncated/` | T1 | FR-09.4, FR-09.13 |
| `T-U-core-10` | **`circt_symbolize` groups by module and feeds offsets, not runtime addresses.** It makes **one** `llvm-symbolizer --obj=<module> --demangle --output-style=JSON` call **per module named in the trace**, with that module's **file offsets** from the `(<module>+0x<offset>)` tail on stdin, and parses one JSON object per line. The old recipe, one call with `--obj=<the tool>` and the runtime addresses, is asserted to resolve nothing: measured against a real `circt-opt` segfault, all six frames came back `FunctionName:"" FileName:"" Line:0`, while the same frames against their own modules and offsets came back named. `--functions` is left at its default `linkage` and `--inlines` is never passed, an inlined frame changing a frame tuple's length without changing the bug | `symbolize/module_offsets.txt` | T1 | FR-07.4 |
| `T-U-core-11` | An unparseable line yields an unresolved record with `function` and `file` empty and `line` 0, and raises nothing | none | T1 | FR-07.4 |
| `T-U-core-12` | **The symbolizer wrapper against `bassert_g`.** `0x3365f30` against `~/.cache/chia-pin-smoke/bassert_g/bin/circt-opt` resolves to `circt::chooseName(llvm::StringRef, llvm::StringRef)` and `lib/Support/Naming.cpp:47` (M2), so a frame names a CIRCT source file and a line under `-gline-tables-only` | `symbolize/bassert_g_addrs.txt` | T1 | FR-07.4, FR-03.4 |
| `T-U-core-13` | The same address against a build without `-g` returns the demangled name and an unresolved location, which is the `??:0:0` the measurement recorded; `--functions=short` returns `??` under `-gline-tables-only` and is therefore not used | `symbolize/bassert_addrs.txt` | T1 | FR-07.4 |
| `T-U-core-14` | **`os.wait4` supplies both derived figures.** `cpu_seconds` is the child's `ru_utime + ru_stime` and `peak_rss_bytes` is `ru_maxrss * 1024`, because `ru_maxrss` is in **kilobytes** on Linux: measured on 2026-09-14, a child allocating a 300 MiB `bytearray` returned `ru_maxrss` 312,064, which is 304.75 MiB read as kilobytes and 0.30 MiB read as bytes. Both are returned on every reaped child and `peak_rss_bytes` is null only when no child started | none | T1 | FR-06.4, NFR-02 |
| `T-U-core-15` | **`limit_hit`'s three rules, against the measured `prlimit` behaviour.** `prlimit --cpu=1 -- python3 -c 'while True: pass'` returns 137, which is 128 + 9, SIGKILL, and the limit is **not** identifiable; `--cpu=1:3` and `--cpu=1:6` both return 152, which is 128 + 24, SIGXCPU, and the signal names the limit; `--cpu=1:6 -- /bin/sh -c 'ulimit -t; ulimit -H -t'` prints `1` and `6`; and `prlimit --as=104857600 -- python3 -c 'b=bytearray(500*1024*1024)'` exits **1** with `MemoryError` on stderr and **no signal**, because `RLIMIT_AS` makes allocation fail rather than killing. The parent's own view through `os.fork` plus `os.wait4` is asserted for all three | none | T1 | FR-06.2, FR-06.4, FR-06.7 |
| `T-U-core-16` | `circt_exec_probe` returns `worker_hostname` from `socket.gethostname()`, `worker_node_id` from `ray.get_runtime_context().get_node_id()` and `child_pid` from the pid `os.fork` returned; all three are non-empty on every call and are what FR-13.2's recorded pair is built from | none | T1 | FR-13.2 |
| `T-U-core-17` | **An attributed frame is not symbolised.** `circt_symbolize` returns a `shape="attributed"` frame unchanged, LLVM having resolved it at print time and there being no module to ask, and computes `in_circt_object` for **both** shapes: a `module_offset` frame is in a CIRCT object when its module is `/workspace/circt/build/bin/<tool>` or matches `/workspace/circt/build/lib/libCIRCT*.so*`, and an attributed frame when its file lies under `/workspace/circt/`, which covers the generated `.inc` files under `build/` as well as the source tree | `stderr/trace.txt` | T1 | FR-07.4, FR-07.5 |

### 1.22 `dockerfiles/ChiaCirctAssertDockerfile` and the `ImageSpec`, 19 tests

The unit under test is the **image**, so every test here is tier 2 except those driven from a recorded
`ImageSpec`. There is no in-process substitute for an image, which is why §12.3 lists F-03's
requirements as testable only above tier 1.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-image-01` | **Fetch-by-SHA into the repository the base already cloned.** The recipe is three commands and no `git init` and no `git remote add`: `git -C /workspace/circt fetch --depth 1 origin ${CIRCT_SHA}`, `git -C /workspace/circt fetch --depth 1 origin tag ${CIRCT_VER}`, `git -C /workspace/circt checkout --detach ${CIRCT_SHA}`. Built at `5056ff04450b`, `git -C /workspace/circt rev-parse HEAD` inside the image prints `5056ff04450bc9f27a9ff0460702aee1f1afdd3f`. The withdrawn `git init` line is asserted absent: run on the base's populated directory it prints `Reinitialized existing Git repository` and the next line fails with `error: remote origin already exists.` rc 3, aborting the `RUN` layer | none | T2 | FR-03.1 |
| `T-U-image-02` | A one-bump-off SDK/source pair exits non-zero **before** `ninja` starts, comparing `git ls-tree <tag> llvm` against the commit's gitlink as full 40-character SHAs. The check is **reachable**, which it was not before `T-U-image-18`'s second fetch: without the tag object `${CIRCT_VER}` is not a name `ls-tree` can resolve and the check fatalled every time rather than comparing. Both outcomes are exercised, a matching pair passing and a mismatched pair exiting 1 | `image/one_bump_off/` | T2 | FR-03.2 |
| `T-U-image-03` | `/opt/circt-sdk/include/circt` and `/opt/circt-sdk/lib/cmake/circt` are both absent inside the built image | none | T2 | FR-03.3 |
| `T-U-image-04` | `CMakeCache.txt` holds `CMAKE_CXX_FLAGS_RELEASE:STRING=-O3 -UNDEBUG -gline-tables-only`; `grep -c -- -DNDEBUG compile_commands.json` returns 0; `readelf -S .../circt-opt` lists `.debug_line` | none | T2 | FR-03.4 |
| `T-U-image-05` | `nm -u` shows `__assert_fail` in **all six** targets, count 1 each; `ImageSpec.assertion_nonreferencing`, the list of non-referencing `obj.CIRCT` objects, is compared **as a set** against the committed baseline in `image/baseline_objects.txt`, every difference named object by object, and any difference blocks publication. **The baseline is the 19 objects measured on the image at `eade0de6`, 536 of 555 referencing** (2026-09-14, W-04, `01-FRD.md` §1.9); ~~18 named objects~~ is superseded, that list being a different commit **and** a different target set, five targets without slang, so a set comparison against it would raise nineteen false differences on the first run. The baseline is that **file**, not `RunManifest.assertion_baseline_count`, which is a different number: FR-07.9's control run counts **firings** over the lit corpus and is expected to be zero, and conflating a count of objects with a count of firings was an error of this plan's earlier draft | `image/baseline_objects.txt` | T2 | FR-03.5 |
| `T-U-image-06` | The two lit runs over the whole `test/` tree under CHIA's own exclusions produce **equal failing-name sets**. The assertions-on half is measured **inside the image** at `eade0de6` (2026-09-14, W-04): 1380 discovered, 253 excluded, 1127 considered, **1119 passed**, 1 Unsupported, 7 XFAIL, **0 failed**, exit 0, with **61** `REQUIRES: slang` tests moved from Unsupported to Passed and one to XFAIL, so the SystemVerilog surface is exercised. The `-DNDEBUG` half needs the second image and is **W-04b**; until it exists this test is **skipped with the skip recorded**, never reported as a pass. The host figures at `5056ff0445`, 1,127 discovered and 1,058 passed under either flag string (M3), are the earlier measurement and are not this image's. Run only after `T-U-image-17` passes, since two empty sets compare equal | `image/lit_baseline/` | T2 | FR-03.6, A-20 |
| `T-U-image-07` | Each of `circt-opt`, `firtool`, `circt-translate`, `arcilator`, `circt-reduce` and, under ADR-D-13 branch (a), `circt-verilog` exists under `/workspace/circt/build/bin` and runs `--version`; the target list is read from `ImageSpec.targets` and is a parameter, not a constant, which `T-U-image-13`'s broken-target control proves is actually read. Measured 2026-09-14: all six run, all print `LLVM version 24.0.0git`, and the four carrying a CIRCT version string print `CIRCT eade0de`, this campaign's pin being **`eade0de61bc5`** with **`firtool-1.159.0`** | none | T2 | FR-03.7 |
| `T-U-image-08` | `lit --version`, `verilator --version` and `arcilator --version` all succeed; `ldd /opt/circt-sdk/bin/circt-opt` resolves `libz3.so.4`; `pip install lit` reports the requirement already satisfied; `lit` is at `/home/ray/anaconda3/envs/py_worker/bin/lit`, the path `circt_warm_build` checks | none | T2 | FR-03.8 |
| `T-U-image-09` | `ssh -V` and `rsync --version` both succeed inside the image, which CHIA's own CIRCT base does not satisfy; the `ImageSpec` records that it is correcting the base | none | T2 | FR-03.9 |
| `T-U-image-10` | The `ImageSpec` is emitted with every field of `03-LLD.md` §2.9 and reaches `RunManifest.image_spec` with the eight keys of §2.11 | `image_spec/ok.json` | T0 | FR-03.10 |
| `T-U-image-11` | A rendered `Report` from an image built under FR-03.4 contains both the literal `-UNDEBUG` and the tool's own `--version` output, which still reads "Optimized build." | `report/` | T0 | FR-03.11, C-08 |
| `T-U-image-12` | MLIR and LLVM assertions stay off: `/opt/circt-sdk/include/llvm/Config/abi-breaking.h` still hard-codes `#define LLVM_ENABLE_ABI_BREAKING_CHECKS 0`, and nothing in the Dockerfile attempts to enable them | none | T2 | FR-03.12 |
| `T-U-image-13` | A build with a deliberately broken target reports which targets succeeded and leaves **no image** under the requested tag | `image/broken_target/` | T2 | FR-03.13 |
| `T-U-image-14` | **Slang, both branches.** Branch (a): `circt-verilog --version` succeeds and reports the image's CIRCT SHA (measured `CIRCT 5056ff0`, M7), `circt-translate --help` carries `--import-verilog` (0 hits without slang, 1 with, M7), and `lit.site.cfg.py` reads `config.slang_frontend_enabled = 1`. Branch (b): the manifest carries the exclusion naming **36** seeds, the union of the two slang entry points (M1), and `ImageSpec.slang_enabled` is false | `image/slang/` | T2 | FR-03.14 |
| `T-U-image-15` | One Verilator version serves the campaign: the version is in the `ImageSpec`, in the `RunManifest` and in **every** `DifferentialVerdict`, and a run whose image reports a different one exits non-zero naming both. The image's packaged version is 5.020-1 (M8) and it carries `--x-initial`, `--x-assign`, `--binary` and `--timing` | `image_spec/ok.json` | T2 | FR-03.15 |
| `T-U-image-16` | `ImageSpec.tool_hashes` names every target in the target list, and re-hashing those binaries inside a **freshly started container from the published image** reproduces the map exactly | none | T2 | FR-03.16 |
| `T-U-image-17` | `grep mlir_src_root /workspace/circt/build/test/lit.site.cfg.py` prints `/opt/circt-sdk` rather than an empty string; `lit --no-progress-bar --show-tests /workspace/circt/build/test` exits 0, lists at least one test under `Tools/circt-tblgen/`, and prints no `fatal: unable to parse config file` line. A non-zero exit or any such line blocks publication, which is `build_image` step 4 and `T-U-driver-25`'s other half | none | T2 | FR-03.17 |
| `T-U-image-18` | **The tag fetch, and why there are two.** `git fetch --depth 1 origin <sha>` fetches one commit and **no tags**, so `git tag --list` afterwards shows none and `${CIRCT_VER}` resolves to nothing; `git fetch --depth 1 origin tag <name>` then prints `[new tag] <name> -> <name>` and `git tag --list` shows it. `checkout --detach ${CIRCT_SHA}` is used rather than `checkout --detach FETCH_HEAD`, which names the same object after the first fetch and the **tag** after the second. Reproduced against a purpose-built upstream of the same shape, an `llvm` gitlink and two `firtool-*` tags, shallow-cloned at the older tag exactly as CHIA's base does; the real clone is a `blob:none` partial clone whose promisor is unreachable offline and cannot serve a shallow clone, so what is run against it is the two `ls-tree` commands of `T-U-image-02` and the fetch semantics are run against the synthetic upstream, `git`'s behaviour not depending on which repository it is pointed at | `image/fetch_upstream/` | T2 | FR-03.1, FR-03.2 |
| `T-U-image-19` | **The seven deviations of `03-LLD.md` §4.11, added 2026-09-14 (W-04).** Read off the Dockerfile and the built image, not off the design: (1) the first line is `ARG BASE_IMAGE` with `FROM ${BASE_IMAGE}`, the SDK is re-installed at `${CIRCT_VER}` inside this file, and FR-03.3's strip is re-applied, both stripped paths absent; (2) the configure line carries `-DLLVM_PARALLEL_LINK_JOBS=2` and 13 lines in total, 7 CHIA's and 6 added; (3) the apt line names **five** additions including `clang-tools`, and the negative control is the recorded failure without it, every `_deps/slang-build` `.ddi` edge dying on `CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS-NOTFOUND` at ninja edge 280 of 1371; (4) `rm -rf /workspace/circt/build` is in the **same `RUN`** as `cmake -B build`, asserted on the layer and not only on the text; (5) `chmod -R a+rwX` is in the **same `RUN`** as `ninja`, no chmod layer of its own, `len .RootFS.Layers` being 23 and not 24; (6) the **last** layer is the `ENV BUGLOOP_*` block and all five variables are readable from inside a running container, which is what makes FR-03.10 and FR-03.11 answerable there; (7) the build command carries **no** `--progress=plain`, a BuildKit flag the legacy builder rejects with rc 125 before anything runs, asserted on `build_image`'s argument list and not on a shell string | `image/` | T2 | FR-03.3, FR-03.4, FR-03.10, FR-03.11, FR-03.14 |

### 1.23 `prompts/` and the shared footer parser, 8 tests

**Callable covered:** `parse_json_footer`.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-prompt-01` | **The last block wins.** A turn output holding two fenced `json` blocks parses the **second**, which is the rule CHIA's own assess parser uses | `turns/two_blocks.md` | T0 | FR-04.8, FR-11.8 |
| `T-U-prompt-02` | **Malformed footers.** Each of `no_block`, `not_json`, `not_object` and `missing:<key>` raises `PromptContractError` with that reason; none is retried inside the turn and none is repaired by guessing | `turns/footer_*/` | T0 | FR-04.8, FR-11.8 |
| `T-U-prompt-03` | Rendering uses `Template(...).safe_substitute(**kw)` and never `str.format`: a prompt carrying MLIR braces and shell braces renders them unchanged, and an undefined `$name` survives as itself rather than raising | `prompts/` | T0 | FR-16.5 |
| `T-U-prompt-04` | Every substitution variable `03-LLD.md` §7.2, §7.3, §7.4 and §8.3 declares is present in its prompt file and is supplied by its caller; an unsupplied variable fails the test. §7.2's seven are asserted to come **entirely from the `SeedRecord`**, `$diff` from `seed.diff` and `$test_files` from `seed.test_files` rendered as one `==> <path> <==`-headed block per entry in `test_paths` order, which is what makes FR-16.5's prompt-byte replay true by construction; before contract 2.0 neither had a source in either object | `prompts/`, `seed_record/` | T0 | FR-04.1, FR-11.1, FR-16.5 |
| `T-U-prompt-05` | `prompts/report_write.md` is a **separate** file from CHIA's `writeup.md` and contains no `Fixes #<number>` line, because an issue report is not a pull-request description | `prompts/` | T0 | FR-11.5 |
| `T-U-prompt-06` | The raw turn output is persisted whatever happens, so a contract failure is inspectable and not merely counted; all five per-turn files exist for stages 1, 2 and 6 | `turns/` | T0 | FR-04.6, FR-11.7 |
| `T-U-prompt-07` | **The stage-6 prompt's two fillings.** Rendered for a primary candidate and for a `differential` one, **no `$name` survives in either**: for a `differential` candidate the six primary variables, `$oracle_class`, `$assertion_text`, `$assertion_site`, `$frames`, `$repro_command` and `$reduced_case`, are bound to the literal `not applicable to a differential candidate`, and `$arcilator_behaviour`, `$verilator_behaviour` and `$stimulus` are bound from the `DifferentialVerdict`. `safe_substitute` leaves an unbound `$name` in place rather than raising, which is why an unbound `$frames` in a prompt is a defect and not a blank | `prompts/`, `report/` | T0 | FR-08.6, FR-11.9, FR-16.5 |
| `T-U-prompt-08` | **No prompt offers a shell.** The stage-1 and stage-2 prompts describe `read_file(path)`, `grep(pattern, path_prefix)` and `list_dir(path)` and state that there is no shell, no build tool and no test tool; the string `bash` appears in none of the four prompt files; and stage 2's rule 5 says the agent cannot run the compiler, which is now true by construction rather than by instruction. §7.3's earlier rule 5 was the only thing forbidding it and prose is the weakest enforcement there is | `prompts/` | T0 | FR-04.4, NFR-03 |

### 1.24 `cluster_single.yaml` and `cluster_gcp.yaml`, 8 tests

Parsed as YAML and asserted structurally; tier 0 except `T-U-cluster-01`, which needs the cluster up.

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-cluster-01` | `chia up cluster_single.yaml` brings all five workers to Ready and a trivial `@ChiaFunction` runs on each of the three types; `ssh -V` and `rsync --version` succeed inside each | none | T3 | FR-03.9, NFR-10 |
| `T-U-cluster-02` | Exactly three worker types with exactly three resource names, `llm`, `circt` and `repair`; counts 2, 2 and 1; `{"llm": 1}` per container so `llm_concurrency` equals the container count | none | T0 | FR-12.11 |
| `T-U-cluster-03` | `min_workers` equals `max_workers` on all three types, so the cluster is fixed-size and `apparatus_concurrency` is exactly the `bugloop_circt` count | none | T0 | FR-14.5 |
| `T-U-cluster-04` | `run_options` on both CIRCT types carry a container CPU limit, a container memory limit, and the artefact bind mount `-v <host root>:<the same absolute path>` read-write; both limits are additions over CHIA's four. **`--user $(id -u):$(id -g)` is on every one of the three worker types** and not only on `bugloop_llm`: the artefact root is a host directory the operator owns, and a container running as the image's own user writes into it as that user, failing pre-flight check 5 on the first worker that tries. `bugloop_llm` carrying **no** `--cpus` and no `--memory` is asserted as deliberate and the YAML's own comment says why: it runs a network-bound model CLI and holds no CIRCT tree, so NFR-05's outer level has nothing to protect | none | T0 | FR-17.9, NFR-05 |
| `T-U-cluster-05` | `run_setup_commands` on the two CIRCT types carry CHIA's `/etc/passwd` and three `git config` lines and **no** `pip install lit`; `bugloop_llm`'s carry the `/etc/passwd` and `ssh-keyscan` lines and **nothing else**, the `.claude.json` copy and the `skipDangerousModePermissionPrompt` write having gone with the CLI. No cluster YAML mentions `GITHUB_TOKEN`, mounts `~/.claude`, `~/.gemini` or `~/.config/gcloud`, or carries any credential **value**: the one credential reference in either file is the literal text `${GEMINI_API_KEY}`, asserted as a reference by pattern and never resolved by the test | none | T0 | FR-03.8, NFR-06, NFR-07 |
| `T-U-cluster-06` | `cluster_gcp.yaml` declares the same three worker types, the same resource names and the same images, so no loop code changes between deployments; `RunManifest.deployment` and `cluster_yaml_sha` record which ran | none | T0 | NFR-10 |
| `T-U-cluster-07` | **Both files load.** `chia.cluster.config.load_config` returns a `ClusterConfig` for `cluster_single.yaml` with `CHIA_HEAD`, `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG`, `USER`, `GEMINI_API_KEY` and `BUGLOOP_ALLOW_LIVE_MODEL` set to dummies, and for `cluster_gcp.yaml` with `BUGLOOP_GCP_HEAD_IP` and `BUGLOOP_GCP_PROJECT` set. The GCP file is still **deferred** and still parses: `provider.head_ip` is required and `load_config` raises `KeyError 'head_ip'` without it, so the placeholder is present and resolves from the environment as `CHIA_HEAD` does in the single-machine file. Parsing is not readiness, and the shared-artefact-store question ADR-D-14 defers is unaffected | none | T0 | NFR-10 |
| `T-U-cluster-08` | **The LLM worker type after the backend decision.** `bugloop_llm`'s image is `ghcr.io/ucb-bar/chia:latest` and not any `chia-claude-code`, `chia-antigravity` or `chia-opencode` tag; its `run_options` carry exactly two `-e` lines of its own, `GEMINI_API_KEY=${GEMINI_API_KEY}` and `BUGLOOP_ALLOW_LIVE_MODEL=${BUGLOOP_ALLOW_LIVE_MODEL}`, besides the SSH agent variable, and **no** `-v ~/.claude` and no `--cpus` or `--memory`; and `${GEMINI_API_KEY}` is expanded by `load_raw_config` from the environment, asserted by loading the file twice, once with the variable set to a synthetic value and once with it unset, and showing the value substituted in the first and the literal `${GEMINI_API_KEY}` surviving in the second. That second half is why `build_llm` rejects a key beginning `${`: an unexpanded reference reaches the container as its value | `secrets/known_values.txt` | T0 | NFR-06, FR-12.11 |

### 1.25 `bug_loop_submit.sh`, 4 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-submit-01` | **No credential of either kind, and the flag is kept.** The strings `GITHUB_TOKEN`, `GEMINI_API_KEY` and `BUGLOOP_ALLOW_LIVE_MODEL` appear nowhere in the script: the GitHub token is read from a 0600 file by two head nodes, the model key reaches the `llm` workers through `docker run -e` at `chia up`, and the interlock is a cluster-level setting that a job must not be able to flip. The string `GITHUB_TOKEN` appears nowhere in the script, which is the one difference from CHIA's wrapper and what keeps the value out of the job's `runtime_env` metadata, out of `chia job` output and out of the dashboard. **`--runtime-env-json` itself is present**, carrying exactly `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG` and, only where the environment sets it, `GOOGLE_CLOUD_PROJECT`, and no fourth key: a submitted job inherits none of the submitting shell's environment, which is precisely why CHIA's wrapper forwards anything at all, and removing the flag along with the token would leave `--artefact-root` and `--image-tag` resolving to nothing inside the job process and pre-flight checks 4 and 5 checking the wrong path. None of the three is a secret | none | T0 | NFR-06, FR-17.5, FR-17.9 |
| `T-U-submit-02` | `BUGLOOP_ARTEFACTS` and `BUGLOOP_IMAGE_TAG` are required and the script exits non-zero naming the missing one; `set -euo pipefail` is present | none | T0 | FR-17.9 |
| `T-U-submit-03` | The script `exec`s `chia job submit --address <addr> --runtime-env-json <json> [--no-wait] -- <python> bug_loop.py "$@"`, passing every argument through, so driver logs are retrievable by `chia job logs <id>`; running the driver directly registers a DRIVER-type job whose stdout the job server does not capture | none | T0 | NFR-09, FR-20.6 |
| `T-U-submit-04` | **The JSON is built by Python, not by string concatenation.** An artefact root containing a space and one containing a double quote both survive into a single well-formed `--runtime-env-json` argument, asserted by parsing the emitted argument back with `json.loads`; and `GOOGLE_CLOUD_PROJECT` is present only when the environment sets it, an empty value making `--repair-backend opencode` fail later rather than at submission | none | T0 | FR-17.9 |

### 1.26 The committed `budget.yaml`, 4 tests

| Test | Behaviour | Fixture | Tier | FR |
|---|---|---|---|---|
| `T-U-byaml-01` | The committed file validates against `03-LLD.md` §9.1's schema, with no key missing and no key extra, **27 keys** from 2026-09-14; `model_id` is `gemini-3.8-flash`, and the two prices are present, positive and finite | none | T0 | FR-14.1 |
| `T-U-byaml-02` | **Every campaign `[DEFAULT]` marker in `01-FRD.md` resolves to exactly one key of this file**, checked by extracting the markers and their named homes and comparing against the key set; the two markers that are not campaign parameters resolve to `03-LLD.md` §9.4 and to §13 of this document | none | T0 | FR-14.1 |
| `T-U-byaml-03` | The `acceptance` block carries the seven keys of `03-LLD.md` §9.3, and each equals the sample size the corresponding feature-acceptance criterion names | none | T0 | FR-14.1 |
| `T-U-byaml-04` | **The calibration sample is drawn and is in the file.** `calibration_sample_shas` holds exactly `calibration_sample_size` entries, each a 40-character hex SHA and each one of the 171 exact-pin seeds, and the list is **not** the twenty illustrative placeholders `03-LLD.md` §9.5 ships, which the test names and rejects. The committed file's own commit is the registration, so a sample drawn afterwards would invalidate the campaign | none | T0 | FR-14.1, FR-14.3 |

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
| `T-I-gen-app-02` | generator to apparatus | `probe_task.probe_execute` | `ProbeSpec` fixtures from the **mutation** arm, recorded from A4 over the same seeds, whose mutants come from `seed.test_files` and from no filesystem | The same, with `arm=mutation`, `mutator_id`, `mutator_seed_int` and `source_test_path` populated; the apparatus's outputs are identical to `T-I-gen-app-01`'s but for the carried `arm` value | T2 | FR-05.4, FR-18.1 |
| `T-I-gen-app-03` | the `generate` interface | A3 and A4 in turn | a fixture `SeedRecord`, a fixture `FeedbackBundle` and a constructed `LedgerSnapshot` | Both implement the one signature; A4 ignores `feedback`; both return `list[ProbeSpec]` that `validate` accepts | T0 | FR-05.4, FR-16.2 |
| `T-I-app-tri-01` | apparatus to triage | `triage_task.dedup_and_screen`, a **head** node reading the head's clone | recorded `CandidateRecord`s with their `ReducedCase` and `OracleVerdict`, plus a recorded issue mirror | Fingerprints computed after the prologue strip, the partition formed over stable fingerprints only, **all three** screens run, the candidate-to-candidate partition, the post-pin scan and the issue-mirror token match, and every verdict carries the evidence keys `_DEDUP_EVIDENCE_REQUIRED` names for it; no GitHub request is made | T1 | FR-10.1, FR-10.3, FR-10.4 |
| `T-I-app-tri-02` | apparatus to triage | `triage_task.triage_report` | the same, plus a recorded stage-6 transcript | The report renders with every substitution point from the record; the tool verdict overrides the agent's class; no number originates in the transcript | T0 | FR-11.2, FR-11.3, FR-11.4 |
| `T-I-tri-rep-01` | triage to repair adapter | `repair_adapter.repair_adapt`, with CHIA's chain stubbed at `run_issue_remote` | a recorded `Report`, `ReducedCase` and `OracleVerdict` for a `crash` candidate | The adapter mints the local id, builds the whole `GithubIssue`-shaped object, pre-writes `repro.sh` and the case **under `<artefact_root>/<run>/repair/<local_id>/`**, outside the tree `git clean -fd` reaches, fills all sixteen `cfg` keys, and calls `run_issue_remote(issue_md, local_id, cfg)` **inline** with a byte-identical `issue_task.py` | T0 | FR-12.1, FR-12.2, FR-12.3 |
| `T-I-tri-rep-02` | triage to repair adapter | the same | recorded `differential`, `fatal_error` and `out_of_scope_root` candidates | Each is refused by class or scope with a recorded reason, and the chain is never invoked | T0 | FR-12.4, FR-12.5 |
| `T-I-rep-gate-01` | repair to gate | `gate.gate_decide` | recorded `RepairResult`s covering all six CHIA statuses | `report_plus_patch` only for `fixed` with `lit_ok`; `report` otherwise; `lit_unusable` stops the run rather than charging the difference to the patch | T0 | FR-12.7, FR-12.8, FR-13.6 |
| `T-I-rep-gate-02` | repair to gate | `gate.gate_decide` with `gate_rerun` live | a recorded candidate whose reproducing command still fires | All four questions answered from tool records, the decision written, and the taxonomy bucket set | T1 | FR-13.1, FR-18.6 |
| `T-I-gate-appr-01` | gate to approval | `approve.main` over a seeded store | recorded `GateDecision`s of each of the three values | Only `report` and `report_plus_patch` are presented; `nothing` is never listed; the four answers and the stopping question appear in `show` | T0 | FR-13.10, FR-13.12 |
| `T-I-gate-appr-02` | gate to approval | `approve.main` | a recorded `GateDecision` of `report_plus_patch` plus its diff | Approval writes exactly one `filing` row carrying approver, timestamp, decision, licence confirmation and URL source; a decline writes a downgrade | T0 | FR-13.7, FR-20.5 |
| `T-I-ledger-01` | ledger across the halves | `ledger.accrue` and `ledger.aggregate` | `LedgerEntry` fixtures recorded by **both** halves in one run, covering all three `arm` values and both `scope` values | The aggregate reconciles: one `arm_window` entry per arm, per-stage entries summing independently, `shared` reported beside and never folded | T0 | FR-14.4, FR-14.5 |
| `T-I-ledger-02` | ledger across the halves | `budget.snapshot` feeding A3 and A4 | the same fixtures | The `LedgerSnapshot` a generator sees carries four fields and no result field; the generator cannot reach `BudgetLedger` | T0 | FR-16.4 |
| `T-I-feed-01` | feedback bundle | `feedback.build_feedback` | `ProbeResult` fixtures for one whole iteration, including clean exits, parse errors, timeouts and OOMs | One `FeedbackEntry` per probing input, built from `ProbeResult`s alone, with no apparatus-internal schema imported | T0 | FR-16.1 |
| `T-I-feed-02` | feedback bundle back into the generator | A3 with a replayed transcript | the bundle `T-I-feed-01` produced | The next iteration's prompt bytes are reproducible from the recorded `SeedRecord` plus the bundle; the mutation arm receives a bundle whose `entries` list is empty and reads it not at all | T0 | FR-16.2, FR-16.5 |
| `T-I-version-01` | contract version, downward | the apparatus half's replay entry point | supply-half fixtures re-recorded at MAJOR `3.0`, the package being at `2.0` | Every consumer raises `E001_MAJOR_MISMATCH` naming both versions; the failure is hard and stops the reading stage, with no shim and no tolerance | T0 | FR-04.3 |
| `T-I-version-02` | contract version, upward | the supply half's replay entry point | apparatus-half fixtures re-recorded at MAJOR `3.0` | The same in the other direction, so a mismatch cannot be one-sided; and the driver turns the stage failure into a run stop. A `1.0` fixture is exercised too, so the rejection is symmetric about `2.0` and not merely forward-looking | T0 | FR-04.3 |

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
| `T-S-isolate-01` | **The repair-worker isolation test.** Hash every tool binary on both `bugloop_circt` workers, run one full repair attempt on `bugloop_repair`, re-hash | The `bugloop_circt` hash manifest is **unchanged** and still equals `ImageSpec.tool_hashes`; the `bugloop_repair` worker is restored by `circt_git_reset(candidate.run_commit)` plus `circt_ninja_build` plus a **re-hash of every tool binary**, and `restore_ok`, `restore_hashes_match` and `restore_log` are all recorded. Whether the re-hash comes back true is `03-LLD.md` §15 item 4 and is `[UNVERIFIED]`; this test is the experiment that settles it, and its pass criterion is that the comparison is made, recorded and **reported**, a routinely false result meaning the repair worker is single-use per run. A deliberately failed restore records `repair_worker_dirty` and disables B8 for the rest of the run | FR-03.16, FR-06.1, FR-12.11 |
| `T-S-regen-01` | **The artefact regeneration check over every row of the pilot** (§11) | Every tool stage of every row re-executes from its stored inputs and produces the stored verdict; every agent turn replays from its stored transcript through CHIA's bypass; a row that cannot be regenerated is **marked**, not reported; replaying a tool stage through bypass is never accepted as evidence | FR-17.1, FR-18.11, NFR-01 |
| `T-S-lit-01` | **The control run of FR-07.9** (§9) | The whole lit suite runs inside the image at the run's commit and the assertion false-positive set is reported | FR-07.9 |
| `T-S-artefact-01` | A probe-bearing node writes a file under the recorded artefact root; the head reads it by the **same** path with no copy step. Then the bind mount is removed from one worker type and the run restarted | The head reads the worker's file by the identical path; with the mount absent the run exits non-zero as `artefact_root_unmounted`, naming the worker and the path, rather than writing elsewhere | FR-17.9 |
| `T-S-submit-01` | **The `chia job submit` wrapper.** `bug_loop_submit.sh --mode discovery --dry-run`, then a real submission | `chia job logs <id>` returns the driver's output **during** the run; `<root>/<run>/results/counters.json` shows per-stage `CounterBlock`s during the run, one per stage reached; the job's `runtime_env` carries exactly `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG` and, where set, `GOOGLE_CLOUD_PROJECT`, and **no token**, in `chia job` output and in the dashboard alike; the driver resolves its artefact root and image tag from those forwarded values, which it could not do had the flag been dropped; `chia job stop --kill-tracked-pids` leaves no orphaned probe | FR-17.4, FR-17.9, NFR-06, NFR-09 |

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
| `T-E-input-05` | input that times out | a module whose canonicalisation does not terminate inside `probe_wall_seconds` (60) | `build_status=timeout`, `signal=null`, `limit_hit=wall`, `oracle_fired=false`. The sibling case, a module that exhausts `probe_cpu_seconds` (45) first, is `build_status=timeout` with `limit_hit=cpu` and `stopping_reason=cpu_limit`, and is run as a second parameter case of this class: `probe_cpu_seconds` sits **below** `probe_wall_seconds`, so for any compute-heavy probe the CPU limit binds first and this is the common path rather than an edge | none | never fires; counted separately in the taxonomy, never as a crash |
| `T-E-input-06` | input that exhausts memory | a module allocating past `probe_address_space_bytes` (4 GiB) | `build_status=oom`, `limit_hit=address_space`, `signal=null` and `exit_status` non-zero, because `RLIMIT_AS` makes allocation fail rather than killing; `oracle_fired=false`, **and the worker survives** | none | never fires; the worker still answers a trivial node afterwards |
| `T-E-input-07` | input whose crash roots in MLIR, not CIRCT | a module crashing inside MLIR's own verifier, from `fixtures/oracle/mlir_root/` | `build_status=crash`, `oracle_fired=true`, `oracle_class=crash`, `out_of_scope_root=true` | `circt-reduce` runs normally | report-only: never reaches repair; reaches the gate and is reported |
| `T-E-input-08` | input that reduces | the 4,000-op `comb` module of M2's probe-speed measurement, carrying one crashing operation | `oracle_fired=true`; `ReducedCase.reduced=true`, `fixpoint=true`, `size_after_bytes < size_before_bytes` | `circt-reduce` to a fixpoint | question 2 passes |
| `T-E-input-09` | input that does not reduce | the already-minimal output of `T-E-input-08`, fed again | `ReducedCase.reduced=false`, `reason` recorded, `fixpoint=true` | `circt-reduce` making no progress | refused at question 2 as `not_minimal`, with the reason recorded, and still persisted and counted |
| `T-E-input-10` | input that duplicates another | a byte-different module producing the same assertion expression at the same `file:line` as `T-E-input-03` | `oracle_fired=true`, `oracle_class=assertion`; the same primary fingerprint | `circt-reduce` | refused at question 4 as `duplicate_of_candidate`, naming the first candidate's id |
| `T-E-input-11` | **M1 language partition: MLIR direct** | a `.mlir` probe entering through `circt-opt`, which is 146 of 187 seeds (78.1%) | any firing class; `ProbeSpec.tool=circt-opt` | `circt-reduce`, `lift=null` | as its class dictates; question 3 checked by `circt-opt <case> -o /dev/null` |
| `T-E-input-12` | **M1 language partition: `.fir` lift** | a `.fir` probe entering through `firtool`, 4 of 187 by best path | firing class; `ProbeSpec.tool=firtool` | `circt-reduce` on the lift `firtool --ir-fir`, retried with `--parse-only` where the failure is inside the pipeline; `ReducedCase.lift` records which | question 3 checked by `firtool --parse-only <case>` |
| `T-E-input-13` | **M1 language partition: `.sv` lift** | a `.sv` probe entering through `circt-verilog`, 35 of 187 by best path. Under ADR-D-13 branch (b) this class is empty and the 36 slang-entry seeds are excluded by configuration | firing class; `ProbeSpec.tool=circt-verilog` or `circt-translate` | `circt-reduce` on the lift `circt-verilog --ir-moore`; `ReducedCase.lift` records it; the interestingness test is `circt-verilog --format=mlir <candidate>` plus the seed's own output-mode flag for a `circt-verilog` probe, and `circt-opt <candidate> -o /dev/null` for a `circt-translate --import-verilog` probe, which has no `--format=` option. Both are run as parameter cases of this class | question 3 checked by `circt-verilog --import-only <case>` |
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
| `expected.json` | `{"class", "assertion_text", "assertion_site", "fingerprint_frame", "prologue_dropped", "top_frames", "exit_status", "signal"}` |
| `stderr.txt` | the recorded stderr, verbatim, decoded with `errors="backslashreplace"` |
| `README.md` | one paragraph: where it came from, why it is in the set, and which class it covers |

`expected.json`'s `assertion_text` and `assertion_site` are present for the `assertion` class and null
otherwise; `top_frames` holds the `fingerprint_top_n` (5) normalised frame function names **after the
prologue strip**, for every class, and is **evidence** rather than a fingerprint. It gains two keys
with this resync, because the fingerprint rule changed: `fingerprint_frame`, the
`<function> <basename>` pair the primary rule uses for a `crash` or a `fatal_error`, and
`prologue_dropped`, how many leading frames the strip removed, so a fixture whose strip changes is
visible rather than silently re-fingerprinted. `signal` was already present and is what the crash and
fatal-error fingerprint's first half is taken from.

### 5.3 The tests

| Test | Behaviour | Tier | FR |
|---|---|---|---|
| the oracle tests of §1.9, `T-U-probe-19` through `T-U-probe-26` | no new identifier: each is run once per fixture directory, parameterised by `pytest.mark.parametrize` over the set, so the set's size is a count of parameter cases and not of tests | T2 | FR-07.1 to FR-07.7 |

The parameterised run asserts, per fixture: the oracle **fires**; the class equals `expected.class`;
for an `assertion` the extracted text and `file:line` equal `expected`'s character for character, with
an `UNREACHABLE executed` firing compared against the two-line pair rather than against an `expr`
group that class does not have; for a `crash` or `fatal_error` the **`fingerprint_frame`** equals
`expected.fingerprint_frame` and `prologue_dropped` equals `expected.prologue_dropped`, the top-5
normalised names being compared as evidence and allowed to differ, which is what the ten-run stability
measurement says they will; and `repro_command`, re-run inside the same image, reproduces the same
exit status and the same assertion text.

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
  `.sv` fixture is in the set for this reason. For a `.sv` fixture the **interestingness argv** is
  asserted too, `circt-verilog --format=mlir <candidate>` plus the seed's own output-mode flag, which
  is the branch that had no statable pass criterion before this resync.
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
| FR-01.9 | a seed with no `RUN:` line: empty list, excluded from the seeded draw, counted; a seed whose `diff` or `test_files` exceed the inline cap, excluded from both arms | `T-U-corpus-17`, `T-U-corpus-23` |
| FR-01.10 | the six normalisation steps and the `unsupported` exclusion | `T-U-corpus-07` to `T-U-corpus-14`, `T-U-corpus-20` |
| FR-01.11 | clone HEAD moved: exit non-zero naming both SHAs | `T-U-corpus-16`, `T-U-driver-03` |
| FR-01.12 | ordered test paths, never collapsed; `test_files` keyed and ordered by them | `T-U-corpus-18`, `T-U-corpus-22` |
| FR-02.5 | no match in 24 months: exit non-zero, never widen | `T-U-pin-05` |
| FR-02.6 | several tags share a pin: newest by tag date, all recorded | `T-U-pin-06` |
| FR-02.7 | `run_commit` per mode, one field and no other | `T-U-schema-15`, `T-S-disc-01`, `T-S-calib-01` |
| FR-03.11 | the report states the flag, because `--version` still says "Optimized build." | `T-U-image-11` |
| FR-03.12 | MLIR and LLVM assertions stay off | `T-U-image-12` |
| FR-03.13 | a broken target publishes no partial image | `T-U-image-13` |
| FR-03.14 | both slang entry points, or the 36-seed exclusion recorded | `T-U-image-14` |
| FR-03.15 | one Verilator version; a change starts a new campaign | `T-U-image-15`, `T-U-driver-08` |
| FR-03.16 | tool hashes from a freshly started container of the published image | `T-U-image-16`, `T-U-probe-01`, `T-U-driver-25` |
| FR-03.17 | `MLIR_SOURCE_DIR` and zero lit discovery errors | `T-U-image-17`, `T-U-driver-06` |
| FR-04.7 | a non-exact seed generates but is never a build commit | `T-U-driver-09`, `T-S-calib-01` |
| FR-04.8 | a failed turn is recorded, charged and survived | `T-U-gen-06`, `T-U-gen-07` |
| FR-04.9 | stage 2 does not validate syntax; stage 3 records `parse_error` | `T-U-probe-03` |
| FR-05.6 | a no-op mutant costs no input-cap budget | `T-U-mut-03` |
| FR-05.7 | a raising mutator is attributed and survived | `T-U-mut-04` |
| FR-05.8 | the synthesis declaration, in the artefact and the paper | `T-U-msyn-03`, `T-U-results-11` |
| FR-06.6 | `parse_error` distinct from a crash, and split by reason into `tool_rejected_argv` and `tool_rejected_input` | `T-U-probe-03`, `T-U-probe-40` |
| FR-06.7 | `oom` by evidence **and** death by signal, never `crash`; `address_space` keeps its own row because `RLIMIT_AS` does not kill | `T-U-probe-08`, `T-U-probe-10`, `T-U-probe-11`, `T-U-probe-12`, `T-U-probe-41`, `T-U-core-15` |
| FR-06.8 | side-effect free with respect to the CIRCT tree | `T-U-probe-37`, `T-U-gen-11` |
| FR-06.9 | exactly seven statuses and no other | `T-U-probe-02` to `T-U-probe-08`, `T-U-schema-05` |
| FR-07.8 | a timeout or an OOM never fires; a CPU-limit kill is a `timeout` and not a `crash` | `T-U-probe-09`, `T-U-probe-19`, `T-U-probe-41` |
| FR-07.9 | the control set and its false-positive rate | `T-S-lit-01` (§9) |
| FR-07.10 | a `fatal_error` is worded as a refusal, never a crash | `T-U-triage-24` |
| FR-08.8 | `harness_failure` names the failing arm | `T-U-probe-28` |
| FR-08.9 | `diverge_x_policy` excluded from the count | `T-U-probe-29` |
| FR-08.10 | the informational report; no gate, no filing, no reducer | `T-U-triage-24`, `T-U-gate-19`, `T-U-results-19` |
| FR-08.11 | the reused driver or a recorded deviation with its obstacle | `T-U-schema-08` (the `differential_driver` key set), `T-U-probe-30` |
| ~~FR-09.6~~ | **WITHDRAWN** in `01-FRD.md`; replaced by FR-09.12 | none |
| FR-09.7 | `reduction_changed_failure`, original carried forward | `T-U-probe-33`, `T-U-gate-08` |
| FR-09.8 | no reducer for a `differential` candidate | `T-U-store-09`, `T-U-gate-19` |
| FR-09.9 | the **five**-branch selection rule, and the `reducer_aborted` route to the textual reducer | `T-U-probe-31`, `T-U-probe-35`, `T-E-input-11` to `T-E-input-14` |
| FR-09.10 | the textual ddmin reducer | `T-U-ddmin-01` to `T-U-ddmin-08` |
| FR-09.11 | the reducer named and the fixpoint flag | `T-U-probe-38` |
| FR-09.12 | `reduced=false` proceeds, is counted, and is refused at question 2 | `T-U-probe-34`, `T-U-gate-07` |
| FR-09.13 | the script's own `timeout` and rlimits; post-exit output validation | `T-U-probe-36`, `T-U-core-09` |
| FR-10.7 | `dedup_unavailable` fails question 4, and a clean mirror miss is not `dedup_unavailable` | `T-U-triage-14`, `T-U-triage-31`, `T-U-gate-14` |
| FR-10.8 | `dedup_basis=insufficient` merges nothing, enforced in Python by `E012` and in the DDL by the `fingerprint` `CHECK` | `T-U-triage-05`, `T-U-triage-27`, `T-U-gate-14`, `T-U-store-12`, `T-U-store-13` |
| FR-10.9 | the once-per-run bounded mirror, `fetch_comments=False` | `T-U-triage-10` to `T-U-triage-13`, `T-U-driver-10` |
| FR-11.8 | `untriaged` still receives four answers, then is held | `T-U-gate-15`, `T-U-appr-04` |
| FR-11.9 | the differential template's own twelve points, stored and never filed | `T-U-triage-24`, `T-U-triage-34`, `T-U-prompt-07` |
| FR-12.8 | `lit_ok=false` attaches no patch; zero discovered is `lit_unusable` | `T-U-repair-11`, `T-U-repair-12` |
| FR-12.9 | the six prompts byte-identical, read from CHIA's own directory | `T-U-repair-08`, `T-U-repair-16` |
| FR-12.10 | loop row first; `repair_row_missing` on reconciliation | `T-U-repair-14`, `T-U-driver-18` |
| FR-12.11 | a repair-only worker, restored by reset, rebuild **and** re-hash after every attempt | `T-U-repair-13`, `T-U-repair-17`, `T-S-isolate-01` |
| FR-13.11 | a refused candidate is persisted in full | `T-U-gate-18` |
| FR-13.12 | the four elements in one view | `T-U-appr-09` |
| FR-13.13 | approval per report, never generalised | `T-U-appr-05`, `T-U-appr-06` |
| FR-13.14 | a `differential` candidate never enters the gate | `T-U-gate-19` |
| FR-13.15 | the three parse-and-verify commands, the three outcomes, and the second conjunct `q3_after_parse` | `T-U-gate-10` to `T-U-gate-13`, `T-U-gate-23`, `T-U-gate-26` |
| FR-13.16 | the poll on the fingerprint, falling back to the paste | `T-U-appr-13` |
| FR-13.17 | the 6,000-character limit and the fallback | `T-U-appr-10` |
| FR-13.18 | one interface owns both the approval and the URL | `T-U-appr-11`, `T-U-appr-12` |
| FR-14.7 | a mid-campaign budget change invalidates the campaign | `T-U-budget-08`, `T-U-driver-16` |
| FR-14.8 | an unmeterable stage is declared, never omitted | `T-U-ledger-08`, `T-U-driver-20` |
| FR-15.5 | the 16 non-exact seeds are still screenable | `T-U-triage-20` |
| FR-16.6 | abandonment after two iterations with an equal `(build_status, stopping_reason)` multiset | `T-U-feed-03`, `T-U-feed-04` |
| FR-17.7 | over the cap goes to disk and is referenced by path; one 262,144-byte constant does three jobs | `T-U-store-03`, `T-U-schema-09`, `T-U-schema-17`, `T-U-schema-23`, `T-U-gen-18` |
| FR-17.8 | the `PARTIAL` marker, never deleted | `T-U-store-04`, `T-U-store-05` |
| FR-17.9 | one identical absolute path on head and workers | `T-U-driver-05`, `T-S-artefact-01` |
| FR-18.10 | each arm stops at its own window or cap; both windows reported | `T-U-ledger-06`, `T-U-results-13`, `T-S-pilot-01` |
| FR-18.11 | a non-regenerable row is marked, not reported | `T-U-results-14`, `T-S-regen-01` |
| FR-18.12 | the divergences-observed list | `T-U-results-10`, `T-U-results-19` |
| FR-19.8 | no dependency added without a licence check | `T-U-layout-05` |
| FR-19.9 | no governance file touched | `T-N-nfr11-01` |

---

## 8. A test for every non-functional requirement, by ID

Seventeen tests over twelve requirements.

| Test | NFR | What is run | Pass criterion | Tier |
|---|---|---|---|---|
| `T-N-nfr01-01` | NFR-01 re-run equality | Three rows `[DEFAULT]` drawn at random from the pilot's results table are re-run through `chia job submit` under NFR-01's definition | Every **tool** stage re-executes from its stored inputs; every **agent turn** replays from its stored transcript through CHIA's bypass; every re-executed verdict equals the stored one; the run record names which stages were re-executed and which turns were replayed; a tool stage served from bypass fails the test | T3 |
| `T-N-nfr02-01` | NFR-02 determinism, stages 3 and 4 | One probe re-run ten times `[DEFAULT]` in the same image | `BuildResult.status`, `OracleVerdict.oracle_class` and, for an `assertion`, the text and `file:line` are identical every time. **The crash fingerprint is not asserted identical and the frame tuple is not asserted at all**: the ten-run measurement of a stack overflow gives nine distinct top-5 tuples and three distinct fingerprint frames, so what is asserted is that a difference sets `fingerprint_stable=false`, that such a candidate is merged with nothing, and that the count is printed beside the headline. `wall_seconds` and `peak_rss_bytes` are exempt and are recorded as non-deterministic in `BuildResult` itself | T2 |
| `T-N-nfr02-02` | NFR-02 determinism, stage 5 | One reduction that completes inside its budget, re-run ten times `[DEFAULT]` | The reduced case is byte-identical every time; a budget-truncated reduction carries `budget_truncated=true` and `fixpoint=false` and is **not** required to be reproducible | T2 |
| `T-N-nfr03-01` | NFR-03 isolation, the tool list | The tool list handed to every model turn, and what those tools can reach | Stage 1 and stage 2 receive literally `[source_read, probe_write]` and stage 6 literally `[source_read]`; no build, lit, oracle, reducer or dedup tool appears in any list; **`BashTool` appears in none of the three and the identifier is absent from the loop's own modules**, asserted by grepping the constructed lists and by a source search. That is NFR-03's second clause made structural: `SourceReadTool`'s three methods are `git` argument vectors against a fixed commit with no shell anywhere, so there is no path from a turn to a binary, a build or a write, where `BashTool` had no read-only mode and put `/workspace/circt/build/bin` first on `PATH` | T0 |
| `T-N-nfr03-02` | NFR-03 isolation, the numbers | Every numeric field of the rendered results artefact and of every rendered report | Each traces, field by field, to a tool-produced record in `loop.db`; the check walks `results.json` and `report.md`'s substitution points and asserts that no value's provenance is a model transcript. Gate precision's denominator is tool-derived because no gate question reads the triage class (`T-U-gate-15`) | T0 |
| `T-N-nfr04-01` | NFR-04 GitHub access | A full dry-run campaign under a **recording HTTP layer**: a `requests` transport adapter mounted by the test harness on `GithubClient._session`, through `unittest.mock.patch` of the constructor, which appends `(method, url, status)` to `<artefact_root>/<run>/github_trace.jsonl` before delegating. Both GitHub-touching components, B6a's mirror and B9a's poll, are head nodes, so one adapter covers the whole loop | The trace contains **only** `GET` requests to `api.github.com`, and none at all during screening; and a corroborating `ast` search over the loop's modules finds no `requests` verb other than `get` and no `GithubClient` method outside the read list. The adapter is test-harness code, so no production dependency and no production change is introduced | T3 |
| `T-N-nfr05-01` | NFR-05 isolation and limits | A probe that exceeds its own address-space rlimit, on a worker whose container also carries CPU and memory limits | The cluster YAML's `run_options` for both CIRCT types carry the container CPU and memory flags; the probe's own `prlimit` limits are set in the child; the probe is recorded `oom` **and the worker stays up**, answering a trivial `@ChiaFunction` afterwards; the task is not silently re-queued, `max_retries=0` making a worker death a task failure with a driver-written `ProbeResult` | T3 |
| `T-N-nfr06-01` | NFR-06 no secrets | A `grep` of the whole artefact tree, every prompt file, every transcript, `loop.db`, `issues.db` and the job's metadata for the `GITHUB_TOKEN` value and for any model API key | Zero hits everywhere, including `chia job` output and the dashboard's `runtime_env`; the token's only home is one 0600 file on the head, read by two head nodes and passed as `GithubClient(token=...)`; no worker container mounts it and no cluster YAML mentions it. The job's `runtime_env` **is** inspected rather than assumed empty, because `bug_loop_submit.sh` does pass `--runtime-env-json`: it must carry exactly `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG` and, where set, `GOOGLE_CLOUD_PROJECT`, a path, a tag and a project id, and no fourth key | T3 |
| `T-N-nfr06-02` | NFR-06 the **model** credential | The same grep, extended for the API key: `grep -E 'AQ\.[A-Za-z0-9_-]{30,}\|AIza[0-9A-Za-z_-]{30,}'` over the whole artefact tree, every prompt file, every turn transcript and `usage.json`, `loop.db`, `issues.db`, both cluster YAMLs, `bug_loop_submit.sh`, the job's `runtime_env` as `chia job` and the dashboard show it, and the driver's own log. Run against a synthetic key of that shape, injected through the environment for the run, so a hit is a real leak and not a pattern false positive | Zero hits everywhere. `--runtime-env-json` carries exactly `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG` and, where set, `GOOGLE_CLOUD_PROJECT`, and no fourth key: neither `GEMINI_API_KEY` nor `BUGLOOP_ALLOW_LIVE_MODEL` is forwarded. The key's only homes are one 0600 file on the head, the operator's shell, the host's `docker run` command line and the two `llm` containers' environment, and `docker inspect` showing it there is the disclosed cost rather than a failure. `bug_loop.py --print-config` prints whether each variable is set and never a value | T3 |
| `T-N-nfr07-01` | NFR-07 least privilege | The loop's environment and its code | Exactly **one** GitHub credential exists, it carries public read scope only, a write attempt with it fails, and a search of the loop's code finds no non-GET call to `api.github.com`. No write-scoped credential exists anywhere | T3 |
| `T-N-nfr08-01` | NFR-08 cost caps | The pilot's ledger against the cluster's own accounting | Neither arm exceeds `arm_window_seconds` on the primary unit, nor either safety cap, **nor does the campaign exceed `campaign_spend_cap_usd`**; the post-run reconciliation of the ledger against the cluster's accounting closes; tokens and money are reported beside the result. The **primary unit** is still the arm window: the USD figure is a cap that bounds damage, exactly as the per-day input cap is, and FR-14.5's equality is on the window | T3 |
| `T-N-nfr08-02` | NFR-08 the money cap, and the interlock that precedes it | A pilot run with `campaign_spend_cap_usd` set to a figure the first few turns will cross, then a second run with the cap at its committed value and the interlock unset | The first run stops **both** arms with `stop_reason = campaign_spend_cap`, stops the arm in flight, never starts the other, and the results artefact prints the spend, which arm was running, and how much of the other arm's window went unspent. The second run refuses at pre-flight check 12 and dispatches **no turn at all**, which is the interlock's whole purpose: the code cannot spend the user's credit until an operator says so, and `04-Test-Plan.md`'s tiers T0 to T2 are green first. The spend the ledger reports is `tokens x budget.yaml prices` and the results artefact prints the two prices it used beside it, because they are `[UNVERIFIED]` against Google's page | T3 |
| `T-N-nfr09-01` | NFR-09 observability | `chia job logs <id>`, the metrics directory and `<root>/<run>/results/counters.json` **during** a running pilot | Driver output is retrievable while the run is in flight; `counters.json` shows one `CounterBlock` per stage reached, with `started`, `completed`, `failed` and `seconds`, rewritten on every aggregation so a mid-window read is complete; every stage that ran has emitted at least one log and one block; `started == completed + failed` holds on every block or the violation is itself logged; and inspecting none of the three stops the run | T3 |
| `T-N-nfr10-01` | NFR-10 single machine, the Must | The whole pilot on `cluster_single.yaml` | The loop's entry point runs end to end on one host, and `RunManifest.deployment` records `single_machine` | T3 |
| `T-N-nfr10-02` | NFR-10 GCP, the Should | `cluster_gcp.yaml`, **only** where ADR-D-14's named date is met | The same three worker types, resource names and images; no loop code differs; `deployment` records `gcp`. Skipped, with the skip recorded, where the credits were not confirmed | T3 |
| `T-N-nfr11-01` | NFR-11 licensing | The pull request and the approval record | The pull request states BSD-3-Clause for code contributed to CHIA and touches none of `STEERING_COMMITTEE.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `README.md`, `SECURITY.md`, `CONTRIBUTING.md`; the approval step records Apache-2.0 with LLVM exceptions for any offered patch; the Python dependency list is unchanged, and `prlimit` and `timeout` are invoked as processes, never imported or linked, so FR-19.8's list is unchanged | T0 |
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
| FR-01.1 | corpus-01, corpus-02, corpus-21, corpus-23, schema-20 | FR-01.2 | corpus-06, corpus-21 |
| FR-01.3 | corpus-06 | FR-01.4 | corpus-05 |
| FR-01.5 | corpus-03 | FR-01.6 | corpus-19, schema-11 |
| FR-01.7 | corpus-04 | FR-01.8 | corpus-15 |
| FR-01.9 | corpus-17, corpus-23 | FR-01.10 | corpus-07 to corpus-14, corpus-20, schema-16 |
| FR-01.11 | corpus-16, driver-03 | FR-01.12 | corpus-18, corpus-22, mut-08 |
| FR-02.1 | pin-01, pin-08, driver-09 | FR-02.2 | pin-02, pin-03, results-07 |
| FR-02.3 | pin-04, driver-09 | FR-02.4 | pin-07, pin-08 |
| FR-02.5 | pin-05 | FR-02.6 | pin-06 |
| FR-02.7 | schema-15, triage-32, repair-09, gate-26, T-S-disc-01, T-S-calib-01 | FR-03.1 | image-01, image-18 |
| FR-03.2 | image-02, image-18, driver-25 | FR-03.3 | image-03, image-19 |
| FR-03.4 | image-04, image-19, core-12 | FR-03.5 | image-05, driver-25 |
| FR-03.6 | image-06, T-S-lit-01 | FR-03.7 | image-07, driver-24 |
| FR-03.8 | image-08, cluster-05 | FR-03.9 | image-09, cluster-01, T-S-cluster-01 |
| FR-03.10 | image-10, image-19, driver-24 | FR-03.11 | image-11, image-19, triage-23 |
| FR-03.12 | image-12 | FR-03.13 | image-13, driver-24, driver-25 |
| FR-03.14 | image-14, image-19 | FR-03.15 | image-15, driver-08 |
| FR-03.16 | image-16, probe-01, driver-07, driver-25, T-S-isolate-01 | FR-03.17 | image-17, driver-06, driver-25 |
| FR-04.1 | gen-05, corpus-24, prompt-04 | FR-04.2 | gen-03, gen-14, schema-21 |
| FR-04.3 | gen-04, schema-01 to schema-03, schema-10, schema-12, schema-20, schema-23, driver-15, T-I-gen-app-01 | FR-04.4 | gen-01, gen-15 to gen-20, gen-25, prompt-08, T-N-nfr03-01 |
| FR-04.5 | gen-02 | FR-04.6 | gen-08, prompt-06 |
| FR-04.7 | driver-09, T-S-calib-01 | FR-04.8 | gen-06, gen-07, prompt-01, prompt-02 |
| FR-04.9 | probe-03 | FR-05.1 | mut-05, mut-08, mut-10, corpus-22 |
| FR-05.2 | mut-01, mut-09, msyn-01, msyn-02, msyn-04 to msyn-09, budget-07, driver-02 | FR-05.3 | mut-02, mut-07, mut-10, schema-06 |
| FR-05.4 | gen-10, T-I-gen-app-02, T-I-gen-app-03 | FR-05.5 | mut-06 |
| FR-05.6 | mut-03 | FR-05.7 | mut-04 |
| FR-05.8 | msyn-03, mut-09, results-11 | FR-06.1 | probe-01, probe-13, probe-14, probe-49, core-01, core-06, core-07, gate-22, driver-07 |
| FR-06.2 | probe-14, probe-41, core-01, core-02, core-15, T-N-nfr05-01 | FR-06.3 | core-03 |
| FR-06.4 | probe-09, probe-15, probe-41, probe-42, core-04, core-05, core-14, core-15, schema-07, schema-14 | FR-06.5 | probe-26, store-07 |
| FR-06.6 | probe-03, probe-40, results-17, feed-03 | FR-06.7 | probe-08, probe-10 to probe-12, probe-41, core-15 |
| FR-06.8 | probe-37, gen-11, gen-12, gen-20 | FR-06.9 | probe-02 to probe-08, probe-40, schema-05 |
| FR-07.1 | probe-16 to probe-19, probe-39 | FR-07.2 | probe-04, probe-05, probe-06, probe-12, probe-21 |
| FR-07.3 | probe-16, probe-17, probe-20, probe-39, schema-18 | FR-07.4 | probe-22, probe-23, core-10 to core-13, core-17 |
| FR-07.5 | probe-24, probe-44, core-17 | FR-07.6 | probe-25 |
| FR-07.7 | probe-26 | FR-07.8 | probe-09, probe-19, probe-41 |
| FR-07.9 | T-S-lit-01 | FR-07.10 | triage-24 |
| FR-08.1 | probe-27, probe-30 | FR-08.2 | probe-47, probe-48, probe-50 |
| FR-08.3 | probe-30, probe-48, schema-08 | FR-08.4 | probe-30 |
| FR-08.5 | repair-05, store-09, probe-50 | FR-08.6 | triage-24, triage-34, prompt-07 |
| FR-08.7 | triage-24 | FR-08.8 | probe-28, probe-47 |
| FR-08.9 | probe-29 | FR-08.10 | triage-24, gate-19, results-19, repair-05, store-09 |
| FR-08.11 | schema-08, probe-30 | FR-09.1 | probe-33, probe-45, §6's parameterised run |
| FR-09.2 | probe-32, probe-45, core-08 | FR-09.3 | probe-33 |
| FR-09.4 | probe-38, core-09 | FR-09.5 | probe-38 |
| ~~FR-09.6~~ | **WITHDRAWN** | FR-09.7 | probe-33, gate-08 |
| FR-09.8 | store-09, gate-19 | FR-09.9 | probe-31, probe-35, T-E-input-11 to T-E-input-14 |
| FR-09.10 | ddmin-01 to ddmin-08 | FR-09.11 | probe-38 |
| FR-09.12 | probe-34, probe-35, gate-07 | FR-09.13 | probe-36, probe-46, core-09 |
| FR-10.1 | triage-01 to triage-06, triage-25 to triage-27, probe-44, gate-24, results-09, triage-03, triage-25 | FR-10.2 | triage-06 to triage-09, triage-26, results-09 |
| FR-10.3 | triage-15, triage-16, triage-28 to triage-31, triage-33, gate-25, T-I-app-tri-01 | FR-10.4 | triage-18, triage-32, triage-33, driver-26 |
| FR-10.5 | triage-17, triage-30, store-09, store-11, store-12 | FR-10.6 | triage-02, store-01 |
| FR-10.7 | triage-13, triage-14, triage-31, gate-14 | FR-10.8 | triage-05, triage-27, gate-14, store-12, store-13 |
| FR-10.9 | triage-10 to triage-13, driver-10, driver-22 | FR-11.1 | triage-22, prompt-04 |
| FR-11.2 | triage-21, T-I-app-tri-02 | FR-11.3 | triage-23, triage-34, T-I-app-tri-02 |
| FR-11.4 | triage-23, T-N-nfr03-02 | FR-11.5 | prompt-05 |
| FR-11.6 | triage-24 | FR-11.7 | prompt-06 |
| FR-11.8 | gate-15, appr-04, prompt-01, prompt-02 | FR-11.9 | triage-24, triage-34, prompt-07 |
| FR-12.1 | repair-07, repair-15 to repair-18, repair-20 to repair-23, driver-17, T-I-tri-rep-01 | FR-12.2 | repair-01, repair-02, schema-15 |
| FR-12.3 | repair-03, repair-04, repair-18, repair-19, results-02, T-I-tri-rep-01 | FR-12.4 | repair-05, T-I-tri-rep-02 |
| FR-12.5 | repair-06, T-I-tri-rep-02 | FR-12.6 | repair-09, repair-16 |
| FR-12.7 | repair-10, T-I-rep-gate-01 | FR-12.8 | repair-11, repair-12, T-I-rep-gate-01 |
| FR-12.9 | repair-08, repair-16 | FR-12.10 | repair-14, store-08, driver-18 |
| FR-12.11 | repair-13, repair-17, cluster-02, layout-06, T-S-isolate-01 | FR-13.1 | gate-01, gate-05, gate-24, T-I-rep-gate-02 |
| FR-13.2 | gate-02 to gate-04, gate-21, probe-43, core-16 | FR-13.3 | gate-06 to gate-09 |
| FR-13.4 | gate-15 | FR-13.5 | gate-14, gate-25 |
| FR-13.6 | gate-16, repair-11, T-I-rep-gate-01 | FR-13.7 | appr-08, appr-12, appr-14 |
| FR-13.8 | appr-01, appr-02 | FR-13.9 | appr-03 |
| FR-13.10 | gate-17, T-I-gate-appr-01 | FR-13.11 | gate-18 |
| FR-13.12 | appr-09, T-I-gate-appr-01 | FR-13.13 | appr-05, appr-06 |
| FR-13.14 | gate-19, results-17, store-09 | FR-13.15 | gate-10 to gate-13, gate-23, gate-26 |
| FR-13.16 | appr-13, triage-23 | FR-13.17 | appr-10 |
| FR-13.18 | appr-11, appr-12, T-I-gate-appr-02 | FR-14.1 | budget-01 to budget-03, budget-10 to budget-13, byaml-01 to byaml-04, driver-21 |
| FR-14.2 | budget-04, budget-05, budget-11, driver-01 | FR-14.3 | budget-06, byaml-04, driver-21 |
| FR-14.4 | ledger-01 to ledger-07, ledger-09, T-I-ledger-01 | FR-14.5 | budget-10, ledger-03, cluster-03, results-12, T-S-pilot-01 |
| FR-14.6 | ledger-08, ledger-10, gen-23, gen-24, budget-12, budget-13, repair-23, schema-06 | FR-14.7 | budget-08, driver-16 |
| FR-14.8 | ledger-08, driver-20, driver-28, gen-24, repair-20, repair-23, schema-08 | FR-15.1 | triage-19, triage-20, triage-32, triage-33, driver-26 |
| FR-15.2 | triage-20, results-05 | FR-15.3 | results-06 |
| FR-15.4 | results-06 | FR-15.5 | triage-20 |
| FR-16.1 | feed-01, feed-02, feed-06, fixt-02, schema-12, T-I-feed-01, probe-49 | FR-16.2 | gen-09, T-I-feed-02, T-I-gen-app-03 |
| FR-16.3 | feed-07 | FR-16.4 | feed-05, budget-09, T-I-ledger-02 |
| FR-16.5 | feed-08, prompt-03, prompt-04, prompt-07, corpus-22, T-I-feed-02 | FR-16.6 | feed-03, feed-04 |
| FR-17.1 | store-01, store-07, T-S-disc-01 | FR-17.2 | store-01, store-07, store-11 |
| FR-17.3 | store-02, probe-49 | FR-17.4 | driver-20, layout-07, schema-22, T-S-submit-01 |
| FR-17.5 | store-10, submit-01, T-N-nfr06-01 | FR-17.6 | store-06 |
| FR-17.7 | store-03, schema-09, schema-17, schema-23, gen-18, corpus-23 | FR-17.8 | store-04, store-05 |
| FR-17.9 | driver-04, driver-05, driver-27, cluster-04, submit-01, submit-02, submit-04, T-S-artefact-01, T-S-submit-01 | FR-18.1 | layout-02, results-18, T-I-gen-app-02 |
| FR-18.2 | results-04, results-20, results-21, driver-28, T-S-pilot-01 | FR-18.3 | results-01 |
| FR-18.4 | results-02, T-S-pilot-01 | FR-18.5 | results-03, T-S-calib-01 |
| FR-18.6 | gate-18, gate-20, results-17, T-S-disc-01 | FR-18.7 | results-15 |
| FR-18.8 | results-08 | FR-18.9 | results-16 |
| FR-18.10 | ledger-06, ledger-11, results-13, driver-13, T-S-pilot-01, T-N-nfr08-02 | FR-18.11 | results-14, T-S-regen-01 |
| FR-18.12 | results-10, results-19 | FR-19.1 | layout-04, layout-06, gen-13, gen-19, gen-25 |
| FR-19.2 | core-01, core-08, core-10, layout-09 | FR-19.3 | driver-12, driver-13, driver-14, driver-23 |
| FR-19.4 | layout-03, layout-07 | FR-19.5 | layout-01, layout-09, the whole `core` module |
| FR-19.6 | T-N-nfr12-01 | FR-19.7 | store-07, T-N-nfr12-01 |
| FR-19.8 | layout-05 | FR-19.9 | T-N-nfr11-01 |
| FR-20.1 | driver-11 | FR-20.2 | appr-03, results-06 |
| FR-20.3 | triage-24, appr-12 | FR-20.4 | triage-11, triage-17 |
| FR-20.5 | appr-07, appr-12, T-N-nfr11-01 | FR-20.6 | appr-14, submit-03 |

### 12.2 Every non-functional requirement, and the reverse index

| NFR | Tests |
|---|---|
| NFR-01 | `T-N-nfr01-01`, `T-S-regen-01` |
| NFR-02 | `T-N-nfr02-01`, `T-N-nfr02-02`, `T-U-schema-11`, `T-U-probe-38`, `T-U-probe-42`, `T-U-triage-26` |
| NFR-03 | `T-N-nfr03-01`, `T-N-nfr03-02`, `T-U-gen-01`, `T-U-gen-14`, `T-U-gen-18`, `T-U-gate-15`, `T-U-triage-23`, `T-U-prompt-08` |
| NFR-04 | `T-N-nfr04-01`, `T-U-triage-15`, `T-U-appr-13`, `T-U-msyn-06` |
| NFR-05 | `T-N-nfr05-01`, `T-U-cluster-04`, `T-U-probe-08` |
| NFR-06 | `T-N-nfr06-01`, `T-N-nfr06-02`, `T-U-store-10`, `T-U-submit-01`, `T-U-cluster-05`, `T-U-cluster-08`, `T-U-layout-08`, `T-U-gen-21`, `T-U-gen-22`, `T-U-driver-27`, `T-S-submit-01` |
| NFR-07 | `T-N-nfr07-01`, `T-U-cluster-05` |
| NFR-08 | `T-N-nfr08-01`, `T-N-nfr08-02`, `T-U-ledger-06`, `T-U-ledger-11`, `T-U-budget-12`, `T-U-gen-21`, `T-U-gen-22`, `T-U-layout-08`, `T-U-repair-22`, `T-U-driver-27` |
| NFR-09 | `T-N-nfr09-01`, `T-U-submit-03`, `T-U-driver-20`, `T-U-layout-07`, `T-S-submit-01` |
| NFR-10 | `T-N-nfr10-01`, `T-N-nfr10-02`, `T-U-cluster-01`, `T-U-cluster-06`, `T-U-cluster-07` |
| NFR-11 | `T-N-nfr11-01`, `T-U-layout-05`, `T-U-appr-07` |
| NFR-12 | `T-N-nfr12-01`, `T-U-layout-01`, `T-U-layout-03`, `T-U-driver-23` |

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
| FR-13.2 | T3 | "A logical worker other than the one that produced the verdict, where the scheduler can grant it" needs a scheduler with more than one live `circt` node; `T-U-gate-03` tests the soft-pin construction and the truthful `same_worker=true` fallback at T0, and `T-U-probe-43` and `T-U-core-16` pin the three recorded identity fields at T1, but the granted case needs the cluster |
| FR-14.5 | T3 | Equal budget is an equality between two arms' elapsed windows, which exist only in a campaign |
| FR-17.9 | T3 | One identical absolute path on the head and on a worker is a bind-mount property of the running cluster |
| FR-18.2, FR-18.4, FR-18.5, FR-18.10 | T3 | Each is a property of a completed two-arm campaign; `results.py`'s refusal checks are unit-tested from a store fixture, but the store fixture itself comes from a campaign |
| FR-18.11 | T3 | Regeneration re-executes every tool stage of every row, which needs the image and the cluster |
| FR-20.1 | T3, and human | The forum post is an act a person performs; the loop can only check that the manifest records its URL and date, which `T-U-driver-11` does. The act itself is scheduled by `05-Work-Plan.md` |

**FR-08.2 is a third limit of the same kind, and it is new.** `03-LLD.md` §3.6.3 now specifies the two
harness generators and the port-list rule as code, so `T-U-probe-47` and `T-U-probe-48` discharge the
extraction, the determinism and the acceptance shape at tiers 1 and 0. What no test can discharge
today is A-08, whether a **generated** testbench compiles and runs against a **generated** design:
`T-U-probe-50` is written, is tier 2, and is **skipped with the skip recorded** until A-19's count says
at least one seed is differential-applicable. A skip that is reported is not a pass.

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
| `contract/fixtures/malformed/` | one deliberately invalid instance per error code, `E001` to `E010`, plus `dicts/` with one bad key set per **declared dict, now eight**, plus `major_older.json` at MAJOR `1.0` and `major_newer.json` at MAJOR `3.0`, the package being at `2.0` | hand-derived from a valid fixture by one edit each, which is the one place a fixture is edited rather than recorded | about 30 files, under 250 kB | yes |
| `contract/fixtures/roundtrip/` | one instance of each of the seven members, plus a permutation driver | recorded | 7 files | yes |
| `fixtures/corpus/clone` | a blobless `llvm/circt` clone reset to `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` | `git clone --filter=blob:none`, then `git checkout --detach <sha>`, then `git fetch 'refs/tags/firtool-*'` with the refspec **quoted** | about 400 MB | **no**: fetched by `tests/fixtures/fetch_clone.sh`, whose expected HEAD SHA is committed |
| `fixtures/corpus/clone_notags` | the same clone with the tag refs removed | the same script with `--no-tags` | shares the object store | no |
| `fixtures/corpus/pin_window_raw.json` | `analysis/pin_window_raw.json`, verbatim: 63 windows, 1,103 shape candidates, 164 tags | copied from `analysis/`, never regenerated by a test | 687 kB | yes |
| `fixtures/corpus/runlines/` | one `RUN:` line per shape of FR-01.10: `not_*.txt` (the corpus's 2 real ones), `env.txt`, `splitfile.txt` (the corpus's 1), `pipe_*.txt` (one plain, one quoted), `subst_*.txt`, `unsupported_*.txt` (`;`, `&&`, backtick, `$(`, and a constructed `%{`), `cont.txt` | extracted from the clone by `m1_runlines.py`'s method, except the `%{` case, which is constructed because M1 measured zero occurrences | 14 files, under 10 kB | yes |
| `fixtures/pin/` | `pin_window_raw.json` (shared), plus `one_bump_off.json`, `no_tags.json`, `multi_tag.json` | derived from `pin_window_raw.json` by selecting rows; the derivation script is committed beside them | 4 files | yes |
| `fixtures/run_manifest/` | one manifest per mode, including `calibration_two.json`, a **calibration** manifest carrying two `run_commit` entries whose index 0 is a different seed's commit from the candidate's, which is what `T-U-triage-32`, `T-U-repair-09` and `T-U-gate-26` need to catch a reader that uses `manifest.run_commit[0]` | recorded, `calibration_two.json` by a two-seed calibration run | 3 files | yes |
| `fixtures/seed_record/` | one `SeedRecord` per shape at contract **2.0**, including the 9-test-file seed, one `sdk_exact=false` seed, and one whose `diff` sits just under `artefact_inline_cap_bytes` and one just over, for `T-U-corpus-23` | recorded | 7 files, under 2 MB | yes |
| `fixtures/turns/` | recorded agent transcripts: `seed_read_ok`, `probe_write_ok`, `probe_write_10`, `probe_write_wrongtool`, `probe_write_argv`, `probe_write_badfooter`, `backend_error`, `report_write_disagree`, `report_write_long`, `mutator_synth_bad`, `two_blocks.md`, `footer_*` | captured from real turns during the pilot, then **redacted** of nothing, because no turn ever sees a credential: the key lives in the LLM object's `client_kwargs` and in the container's environment, neither of which is in a transcript | 15 files, under 5 MB | yes |
| `fixtures/vertex/` | the fake responses the `fake_vertex` fixture replays, as **response builders** rather than as recorded bytes: one plain text turn with `prompt_token_count` and `candidates_token_count` set, one `function_call` turn followed by its text turn, one `MAX_TOKENS` turn, and one blocked turn. They are built from `google.genai.types` at test time, exactly as CHIA's own `_resp` does (`chia:chia/models/tests/test_vertex.py:64-75`), so a `google-genai` upgrade that renames a field fails the tests loudly instead of replaying stale JSON | a committed Python module, not data; no recorded HTTP anywhere | 1 file, under 10 kB | yes |
| `fixtures/ledger/vertex/` | `LedgerEntry` rows whose `observed` is populated: tokens from a mocked turn and a `cost_usd` the ledger computed from `budget/complete.yaml`'s two prices | recorded through `accrue` in a test, then committed | 4 files, under 20 kB | yes |
| `fixtures/mutators/` | `set_v1.json`, a `raising.json` set holding one deliberately raising mutator, and `noop_case/` | `mutator_synth.py` for the real set; hand-written for the two test sets | 3 files, under 200 kB | yes |
| `fixtures/stderr/` | one recorded stderr per `classify_build` row: `clean`, `parse_error`, `parse_error_argv`, `assert_glibc`, `assert_cpp`, `unreachable_*`, `llvm_error`, `segv`, `bad_alloc`, `oom_*`, `both`, `trace` | captured from real tool runs; `assert_glibc.txt` is the measured three-line C programme's output and `assert_cpp.txt` the measured namespaced C++ member function's, which is the shape `_ASSERT_GLIBC`'s `.+?` exists for; `parse_error_argv.txt` carries the literal `does not refer to a registered pass or pass pipeline`; `trace.txt` is the recorded 466-frame `!hw.array` overflow and carries **both** `_FRAME` shapes | 15 files, under 150 kB | yes |
| `fixtures/oracle/<class>_<nn>/` | **the five recorded real failures of §5**: `input.<ext>`, `argv.json`, `commit.json`, `expected.json`, `stderr.txt`, `README.md` | the procedure of §5.1, from the 187 seeds and from closed `label:bug` issues | 5 directories `[DEFAULT]`, 30 files, under 1 MB | yes |
| `fixtures/reducer/` | `branch_mlir/`, `branch_fir/`, `branch_sv_verilog/`, `branch_sv_translate/`, `branch_textual/`, `minimal/`, `reducer_abort/`, `truncated/` | each derived from a `fixtures/oracle/` failure; the `.sv` branch splits in two because `circt-verilog` takes `--format=mlir` and `circt-translate` has no such option; `reducer_abort/` is the measured parser-overflow input on which `circt-reduce` itself died with rc 139, which must now route to `textual-ddmin`; `truncated/` is produced by killing a reduction mid-write | 8 directories, under 2 MB | yes |
| `fixtures/ddmin/200_3/` | a 200-line input `[DEFAULT]` whose interestingness depends on exactly 3 lines `[DEFAULT]`, plus the interestingness function as a Python callable | constructed: 197 filler lines and 3 load-bearing ones, with the expected answer committed beside it | 2 files, under 20 kB | yes |
| `fixtures/ddmin/adversarial/` | an input whose interestingness function is true only for the full list | constructed | 2 files | yes |
| `fixtures/dedup/pairs/` | **the 20 labelled pairs of §10**, `<nn>.json`, each with two candidate ids, the label, the one-sentence justification and the labelling date; at least four are R4 pairs | the four construction rules of §10, labelled before the fingerprint is computed | 20 files, under 500 kB | yes |
| `fixtures/fingerprint/` | `assertion/`, `crash/`, `structural/`, `insufficient/` and `unstable/` | `unstable/` is the **ten recorded runs of one `!hw.array` stack overflow** whose top-5 stripped tuple takes nine distinct values and whose fingerprint frame takes three, which is what `T-U-triage-03`, `T-U-triage-26` and `T-N-nfr02-01` are written against; `structural/` holds the observed `hw.module @top` and `hw.module private @Foo` pair | 5 directories, under 500 kB | yes |
| `fixtures/dedup/known_issue/`, `fixtures/dedup/verdicts/` | one candidate per `DedupVerdict` value, including **both** `known_open_issue` and `known_closed_issue`, which §3.7.3's screen makes reachable for the first time; plus one candidate per oracle class carrying the tokens §3.7.3 draws, one whose only token is under the 8-character floor, and one matching issues in both states | recorded, except the token cases, which are derived from a recorded candidate by one edit each | 14 files | yes |
| `fixtures/mirror/` | recorded GitHub responses: `closed_bug.jsonl` (487 closed and 101 open `label:bug` issues, M9), `with_comments.jsonl`, `ratelimit/`, `empty/`, `filed_issue.jsonl` | one `GithubIssuesNode.recent` call captured through the recording adapter of §8, then committed; no test ever calls GitHub. `closed_bug.jsonl` is also `synthesise_mutators`' whole input, so `T-U-msyn-05` and `T-U-msyn-06` read the same file the campaign would | 5 files, about 30 MB | yes, and it is the largest committed fixture |
| `fixtures/contamination/clone` | the clone of `fixtures/corpus/clone`, reused | shared | shared | no |
| `fixtures/image_spec/` | `ok.json`, `lit_broken.json` | recorded from a real image build; `lit_broken.json` is `ok.json` with `lit_discovery_ok` false | 2 files | yes |
| `fixtures/image/fetch_upstream/` | a purpose-built upstream shaped like `llvm/circt`: an `llvm` gitlink and two `firtool-*` tags, plus the script that shallow-clones it at the older tag exactly as CHIA's base does | `tests/fixtures/make_fetch_upstream.sh` at test time; the real clone is `blob:none` and cannot serve a shallow clone offline, so the fetch semantics of `T-U-image-18` are exercised here and the two `ls-tree` commands of `T-U-image-02` against the real clone | 1 script | script yes, repository no |
| `fixtures/image/` | `one_bump_off/`, `broken_target/`, `slang/`, `baseline_objects.txt` (FR-03.5's **19** named objects, re-based on the image at `eade0de6` on 2026-09-14; ~~18~~ was a different commit and a different target set), `lit_baseline/` | build-time fixtures: each is a Dockerfile argument set plus the expected failure, not an image | 5 items, under 100 kB | yes |
| `fixtures/symbolize/` | `bassert_g_addrs.txt`, `bassert_addrs.txt` and `module_offsets.txt`, each one address or offset per line with its expected resolution | the first two from M2's measured probe; `module_offsets.txt` from the recorded 466-frame trace, one `(<module>, <offset>)` pair per line grouped by module, which is what `circt_symbolize` actually feeds `llvm-symbolizer` and what `T-U-core-10` asserts resolves where the runtime addresses do not | 3 files | yes |
| `fixtures/repro_polarity/crashing/`, `.../diagnosing/` | **the two `repro.sh` polarity fixture binaries of FR-12.3**: a tiny C programme that aborts on its input, and the same programme patched to print a diagnostic and exit 1 | built from committed C source by `tests/fixtures/build_polarity.sh`; the **source** is committed and the binaries are built at test time, so no ELF is in the repository | 2 source files, under 5 kB | source yes, binaries no |
| `fixtures/repair/` | `issues.db` (a real CHIA database with existing keys), `chia_baseline.json` (the `sha256` of the **six prompts** at `16c35e92`, plus, since 2026-09-14, `issue_task.py`'s `sha256` at `16c35e92` **and** the `sha256` of `upstream/issue_task-vertex-branch.patch`, which is what `T-U-repair-07` and `T-U-repair-21` compare against instead of a hash of the working file), `verdicts/`, `lit_red/`, `lit_zero/` | `issues.db` copied from a CHIA run; the baseline hashes computed once | 5 items, under 2 MB | yes |
| `fixtures/candidate/`, `fixtures/reduced_case/`, `fixtures/report/` | one record per branch each stage can take, including `differential.json`, `mlir_root.json`, `null_answer.json`, `taxonomy/` (one per stopping value), `short.md`, `long.md`, plus one `CandidateRecord` per row of `03-LLD.md` §2.9's class table in both columns and one per `E011`, `E012` and `E013` | recorded, the three malformed ones derived by one edit each | about 40 files, under 1 MB | yes |
| `fixtures/approve/` | `store_one_filed.db`, `store_at_total.db`, `two_pending.db`, `gfi_candidate.json`, `untriaged.json`, `with_patch.json` | built by running the loop to the gate and stopping, then copying `loop.db` | 6 files, under 2 MB | yes |
| `fixtures/results/` | `store_full.db`, `store_zero.db`, `store_capped.db`, `store_marked.db` | `store_full.db` is the pilot's own database; the other three are it with one property changed | 4 files, about 20 MB | yes |
| `fixtures/budget/`, `fixtures/repo/` | `complete.yaml`, `missing/` (**27** one-key-short copies), `extra_key.yaml`, `bad_types/`, `empty_sample.yaml`, **`bad_prices/`** (one copy per refusal of check 6: each price absent, zero, negative, `nan`, `inf` and a string, plus a non-positive `campaign_spend_cap_usd` and an empty `model_id`); and **five** throwaway git repositories: `uncommitted/`, `later_commit/`, `mutator_after/`, `preregistered/`, **`chia_stub/`** (a directory holding an empty `chia/` and `examples/circt_issue_solver/`, which is all `sync-to-chia.sh` checks before it writes) | the YAMLs are derived from `03-LLD.md` §9.5 by one edit each, `empty_sample.yaml` being the file with `calibration_sample_shas` emptied, which is what §9.5 itself used to ship; the repositories are built by `tests/fixtures/make_repos.sh` at test time | 44 files, under 120 kB | YAMLs yes, repositories no |
| `fixtures/equivalence/<class>/` | **the fourteen constructed inputs of §4**, one directory each, with the input, the argv and the expected `ProbeResult` fields | constructed by hand, except `T-E-input-02`, `T-E-input-03`, `T-E-input-07` and `T-E-input-08`, which are derived from `fixtures/oracle/` | 14 directories, under 2 MB | yes |
| `fixtures/differential/` | `broken_tb/`, `x_only/`, `port_lists/` and `register_add/` | `port_lists/` holds one lifted HW-dialect file per `extract_port_list` outcome: a clean two-port clocked module, a two-module file whose submodule is `private`, a file with no public module and one with two, a file with an `!hw.array` port, and a purely combinational file. Those five are constructed and drive `T-U-probe-47` and `T-U-probe-48` at tiers 1 and 0, so the generator tests are **no longer blocked**. `register_add/` is the recorded 12-line FIRRTL register-add of FINAL Appendix A and drives `T-U-probe-50`, which stays **blocked on A-19** and is skipped with the skip recorded | 4 directories, under 100 kB | yes |
| `fixtures/secrets/known_values.txt` | the literal strings the secret grep searches for: a synthetic token of the shape `ghp_` plus 36 characters, and **two** synthetic model keys, one of each Google shape, `AQ.` plus 32 characters and `AIza` plus 35, which are what `T-N-nfr06-02`'s regular expression is written against. It is also the value `conftest.py` puts in `GEMINI_API_KEY` for every test below T3, so a test that somehow reached the network would present a key that cannot authenticate | constructed; **no real credential is ever committed**, and no test reads `~/.config/bugloop/gemini.env` | 1 file | yes |
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
| **T0**, no CIRCT | 337 | Every test of `schema`, `fixt`, `layout`, `mut`, `msyn`, `ddmin`, `budget`, `ledger`, `feed`, `store`, `results`, `appr`, `prompt`, `submit`, `byaml`, `cluster` (bar `cluster-01`); the pure-logic half of `corpus`, `pin`, `gen`, `probe`, `triage`, `repair`, `gate`, `driver`, `core`; `image-10` and `image-11`; 13 of the 17 integration tests; `T-N-nfr03-01`, `T-N-nfr03-02`, `T-N-nfr11-01`, `T-N-nfr12-01`. The LLD resync added 47 of them, the largest groups being the ten mirror-screen and fingerprint tests of `triage`, the five `build_image` and CLI tests of `driver`, and the five contract tests of `schema`; the backend fold-in added 15, of which the five `gen` tests run the whole Gemini agent loop against CHIA's own fake `genai.Client` and fake MCP transport and so still fork nothing | **under 130 s** `[DEFAULT]` for the whole tier, given that nothing forks a compiler and nothing opens a socket. It was 90 s for 275 tests and the added 62 are pure-logic |
| **T1**, the SDK or a measured build | 72 | `corpus-01`, `corpus-15`, `corpus-16`, `corpus-19`, `corpus-21` to `corpus-24`; `pin-02`, `pin-08`; `gen-05`, `gen-15` to `gen-18`; `probe-01`, `probe-07` to `probe-09`, `probe-13` to `probe-15`, `probe-20`, `probe-23`, `probe-25`, `probe-26`, `probe-31` to `probe-36`, `probe-38`, `probe-41` to `probe-43`, `probe-45` to `probe-47`; `triage-18` to `triage-20`, `triage-32`; `repair-03`, `repair-04`, `repair-18`; `gate-10` to `gate-13`, `gate-21` to `gate-23`, `gate-26`; `driver-03`, `driver-26`; `core-02` to `core-05`, `core-08` to `core-17`; `T-I-app-tri-01`, `T-I-rep-gate-02` | **about 30 min** `[DEFAULT]`, still dominated by two measured git walks: the batched `cat-file` over 228 blobs at **125 s** (M1) and the contamination `log -p` over 109 paths at **488 s** (M4), the latter now run once after `driver-26`'s backfill rather than cold. The 23 tests the resync added are seconds each: four `git` reads for `SourceReadTool`, four `prlimit` and `os.wait4` probes, and one `circt-opt --mlir-print-op-generic` |
| **T2**, the assertions-on image | 42 | Every `image` test bar `image-10` and `image-11`, `image-18` included; `probe-28` to `probe-30`, `probe-37`, `probe-50`; `repair-13`; `driver-07`, `driver-08`; the §5 and §6 parameterised runs; `T-I-gen-app-01`, `T-I-gen-app-02`; all 14 `T-E-input-*`; `T-N-nfr02-01`, `T-N-nfr02-02` | **about 45 min** `[DEFAULT]` **after** the image exists, unchanged: `image-18` runs against a synthetic upstream in seconds and `probe-50` is skipped until A-19 answers. The image build itself is separate and measured: **582 s** for the five targets under `-O3 -UNDEBUG -gline-tables-only` at `-j12` (M2), or **841 s** with the slang front end at `-j8` (M7), plus the two lit runs at **10.06 s** and **10.21 s** (M3) |
| **T3**, the single-machine cluster | 22 | All 9 system tests; `cluster-01`; `driver-05`; `T-N-nfr01-01`, `T-N-nfr04-01` to `T-N-nfr10-02`, `T-N-nfr06-02` and `T-N-nfr08-02` among them; the §5 fixtures' five cached images are reused rather than rebuilt | **about 2 h 30 min** `[DEFAULT]`: `chia up` and image pulls, then `T-S-pilot-01`'s two 600 s `[DEFAULT]` arm windows, then the regeneration check over the pilot's rows, which re-executes every tool stage |

The four counts sum to **473**, which is every test identifier in this document, each counted once at
the **lowest** tier it can run at. The LLD resync added 72, 47 at T0, 23 at T1 and 2 at T2, and the
backend fold-in of 2026-09-14 added 17 more, **15 at T0** (`layout-08`, `layout-09`, `gen-21` to
`gen-25`, `budget-12`, `budget-13`, `ledger-10`, `ledger-11`, `repair-20`, `driver-27`, `driver-28`,
`cluster-08`) and **2 at T3** (`T-N-nfr06-02`, `T-N-nfr08-02`). Neither withdrew any.
Sixteen identifiers do more work than that count suggests: the oracle and reducer tests
`T-U-probe-19` to `T-U-probe-26` and `T-U-probe-31` to `T-U-probe-38` are counted once at their tier,
and are additionally run as the tier-2 parameterised sweeps of §5.3 and §6, once per recorded failure.
That is a count of parameter cases, not of tests, and it is why the T2 wall time above is dominated by
them rather than by the image tests. Two further identifiers are parameterised the same way and are
likewise counted once: `T-E-input-05`, which runs a wall case and a CPU case, and `T-E-input-13`,
which runs a `circt-verilog` case and a `circt-translate` case.

---

## 15. The order the tiers run in the work plan

Four gates, each of which must be green before the next begins. `05-Work-Plan.md` owns the dates; this
section owns the order and the reason for it.

1. **T0 first, and on every commit.** It needs nothing but the repository, runs in under 120 s, and
   covers **339** of **477** tests, including the whole contract, the whole taxonomy mapping, the whole gate
   logic, every render refusal and, since this resync, the whole issue-mirror screen and the two
   harness generators. It is the only tier cheap enough to be a pre-commit gate, and the
   contract fixtures' compatibility check lives in it, so a MAJOR bump is caught at the commit that
   makes it rather than at the join.
2. **T1 next, and on every push.** It needs the SDK, the `bassert_g` build, the `bslang` build and the
   clone, all of which exist on the implementation machine today, and it is where the corpus numbers,
   the pin selection, the oracle patterns against real binaries, the `prlimit` and `os.wait4`
   behaviour, the `SourceReadTool` commands and the symbolizer wrapper are pinned. Its 30 minutes are
   dominated by two git walks that are cacheable: the corpus mine and the contamination scan both key
   on the clone HEAD, so a second run in the same day is seconds. One ordering inside the tier is not
   optional: `T-U-driver-26`'s backfill runs **before** `T-U-triage-18` to `T-U-triage-20`, because a
   cold blobless store makes the contamination scan 488 s rather than seconds and the test would be
   measuring the object store rather than the scan.
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

**A fifth gate, before any of T3 spends money** (2026-09-14, the user's rule). `T-S-pilot-01` is the
**first live model request the project makes** beyond the three one-word key probes of 2026-09-14.
It may not be started until T0, T1 and T2 are green with the model layer mocked and the code red team
has passed, which is exactly what `BUGLOOP_ALLOW_LIVE_MODEL` enforces mechanically: unset, the loop
refuses to construct a backend at all (`T-U-gen-21`), and no test below T3 sets it
(`T-U-layout-08`). Every other T3 test, `T-S-cluster-01`, `T-S-artefact-01`, `T-S-submit-01`,
`T-S-isolate-01`, `T-S-lit-01` and the four NFR runs that do not need a turn, runs on the cluster
with the model layer mocked the same way, so the order inside T3 is: everything that does not need a
model, then `T-N-nfr08-02`'s deliberately tiny cap, then the pilot. `05-Work-Plan.md` W-18 owns the
date and the operator sets the variable in their own shell, never a script.

One rule cuts across all four: **no tier is skipped because the tier above it passed.** A tier-3 pilot
that produces a plausible results table proves nothing about the taxonomy mapping, the fingerprint's
transitivity or the validator's error codes, all of which are tier 0 and all of which are where a
silent defect would change a headline.

---

## 16. Resync log

**2026-09-14.** `03-LLD.md` and this plan were revised in parallel: the LLD against
`design/reviews/red-team-LLD.md`, dispositioned in `design/reviews/red-team-LLD-disposition.md`, and
this plan against its own §16, which listed twelve sections to re-check and named seven
under-specified LLD functions and two LLD defects. Both halves are now resynced. This section records
what each side did, so that a reader who has only one of the two documents can tell what moved.

### 16.1 What the LLD added, and what this plan now tests

The nine items this plan's earlier §16 raised. Each is now specified in `03-LLD.md` with a signature,
a docstring, a timeout, its exceptions, its idempotency and its FR ids, and each has at least one test
here.

| # | The earlier gap | Where the LLD settles it | Tests added |
|---|---|---|---|
| 1 | **FR-08.2 had no specification a unit test could be written against**: the two harness generators were fixed as argv and never as code, with no name, no signature and no port-list extraction rule anywhere | `03-LLD.md` §3.6.3: `extract_port_list`, `gen_arc_harness`, `gen_verilator_tb`, the port-list rule with its `circt-opt --mlir-print-op-generic` command, the five-field stimulus protocol, the X-policy asymmetry and the `BUGLOOP` acceptance shape | `T-U-probe-47`, `T-U-probe-48`, `T-U-probe-50`; `T-U-probe-30` extended with `port_list_sha`'s two-sided life |
| 2 | **`bug_loop.build_image` had a timeout and an idempotency key and no signature**, so every §1.22 test was written against the image and none against the callable, and `T-U-layout-03`'s docstring check would have failed on it | `03-LLD.md` §4.11.1: the eight steps, the `docker build` arguments, the hash manifest, the lit-discovery check, the tool-version checks, `ImageBuildError` and `BuildTimeout`, and the tag as the digest of the five-field manifest | `T-U-driver-24`, `T-U-driver-25` |
| 3 | **`mutator_synth.synthesise_mutators` was named with only its prompt specified** | `03-LLD.md` §8.3: the five steps, the 487-issue input, §8.1's output format, the write-once freeze and four named errors | `T-U-msyn-06` to `T-U-msyn-09`; `T-U-msyn-01` and `T-U-msyn-05` rewritten |
| 4 | **`store.validate_candidate` had no signature and no error vocabulary**, so `T-U-store-09` asserted the two conditionals §2.9 stated and nothing more | `03-LLD.md` §2.9: the per-class table, the seven codes, `E011` to `E013` extending §2.1's scheme, and the idempotence statement | `T-U-store-09` rewritten; `T-U-store-11` to `T-U-store-13` |
| 5 | **`results.py` said nine refusal checks in §3.11 and fourteen in §14.4** | Fourteen. `03-LLD.md` §3.11 names them once, as the `_REFUSALS` tuple in §14.4's order, and §14.4 keeps the element-and-requirement mapping | `T-U-results-21`; `T-U-results-02`, `-09` and `-17` extended with the three columns the revision added |
| 6 | **`BuildResult.peak_rss_bytes` had no producer**: the field was in §2.9 and in the DDL and no documented return could fill it | `03-LLD.md` §3.10: `os.wait4`'s `ru_maxrss`, in **kilobytes** on Linux, multiplied by 1,024, with the measurement that establishes the unit | `T-U-probe-42`, `T-U-core-14` |
| 7 | **FR-17.4's counters were one sentence naming no counter and no schema** | `03-LLD.md` §2.5's `CounterBlock`, four counters and a stage drawn from `_COUNTER_STAGES`, returned by every node and logged by B12 on the head into `counters.json` | `T-U-driver-20` rewritten; `T-U-layout-07`, `T-U-schema-22` |
| 8 | **§1.3 asserted a one-to-one source-to-test mapping that five artefacts break**, so this plan's own five artefact test modules failed the LLD's own rule | `03-LLD.md` §1.3: the four sets, the five artefacts named with their test modules, and the exemption stated by name | `T-U-layout-01` rewritten to compare the two exemption lists for equality; the §0.1 erratum is discharged |
| 9 | **§4.7's `.sv` row said "the probe's own tool and argv, on the lifted MLIR" and `circt-verilog` was assumed unable to read MLIR**, so `T-U-probe-31`'s third branch had no pass criterion | `03-LLD.md` §4.4 and §4.7: `circt-verilog --format=<value>` with `=sv` and `=mlir`, verified by `--help` on both the SDK binary and the source-built slang binary and exercised on a lifted Moore IR file; the row splits in two, `circt-verilog` re-fed through `--format=mlir` and `circt-translate --import-verilog` checked with `circt-opt`, `circt-translate` having no `--format=` at all | `T-U-probe-31` rewritten to five branches; `T-E-input-13` and §6 spelled with the new argv |

### 16.2 What the LLD revision changed, and every test it moved

Read against the disposition's own list of changed sections. A test whose **behaviour** changed keeps
its identifier; nothing is withdrawn.

| The change | Disposition | Tests changed |
|---|---|---|
| Contract **2.0**, `SeedRecord.diff` and `test_files` required | K6 | `T-U-schema-01`, `-13`, `-16`, `-20`; `T-U-fixt-03`; `T-U-corpus-21` to `-23`; `T-U-mut-08`; `T-U-prompt-04`; `T-I-version-01`, `-02`; the `malformed/` and `seed_record/` fixture rows |
| `E010_TOOL_MISMATCH` moves to `emit_specs` | K10 | `T-U-gen-03`, `T-U-schema-21` |
| `SourceReadTool` replaces `BashTool` at stages 1, 2 and 6 | W10 | `T-U-gen-01`, `-15` to `-20`; `T-U-prompt-08`; `T-N-nfr03-01` |
| A1, A2, B6b move to the head; `corpus.resolve_sites` is added | K5 | `T-U-layout-06`; `T-U-corpus-24`; `T-U-gen-05`; `T-U-triage-33`; `T-I-app-tri-01` |
| `BuildResult` gains `worker_hostname`, `worker_node_id`, `child_pid` | K12 | `T-U-probe-43`, `T-U-core-16`, `T-U-gate-04` |
| `peak_rss_bytes` gains a producer | §16 item 8 above | `T-U-probe-42`, `T-U-core-14` |
| `limit_hit` derived via `SIGXCPU` and `os.wait4` | K8 | `T-U-probe-14`, `-41`; `T-U-core-01`, `-04`, `-15`; `T-E-input-05`, `T-E-input-06` |
| The prologue strip, and the signal-plus-frame fingerprint with `fingerprint_stable` | K3 | `T-U-probe-24`, `-44`; `T-U-triage-03`, `-25` to `-27`; `T-U-gate-24`; `T-U-results-09`; `T-N-nfr02-01`; §5.2's `expected.json`; the `fingerprint/unstable/` fixture |
| The issue-mirror screen of §3.7.3 | K7 | `T-U-triage-28` to `T-U-triage-31`; `T-U-gate-25`; `T-U-appr-03`; the `dedup/known_issue/` fixture |
| `reducer_aborted` routes to the textual reducer | W13's observation | `T-U-probe-31`, `T-U-probe-35`; the `reducer/` fixture row |
| The repro directory under the artefact root, and `repro_overwritten` | K9, W3 | `T-U-repair-18`, `-19`; `T-U-results-02`; `T-I-tri-rep-01` |
| The image recipe's tag fetch and the now-reachable pin check | K4 | `T-U-image-01`, `-02`, `-18`; the `image/fetch_upstream/` fixture |
| `--user` on every worker type | W20 | `T-U-cluster-04` |
| The interestingness template's one-block emission and eleven bound placeholders | K15, W14 | `T-U-probe-45`, `T-U-probe-46` |
| `_ASSERT_UNREACHABLE`'s two-line extraction | K16 | `T-U-probe-17`; §5.3's parameterised assertions |
| `_ASSERT_GLIBC`'s `func` group becomes `.+?` | K1 | `T-U-probe-39`; the `stderr/assert_cpp.txt` fixture |
| `_FRAME`'s two shapes and symbolisation by module and offset | K2 | `T-U-probe-22`, `-23`; `T-U-core-10`, `-17`; the `symbolize/module_offsets.txt` fixture |
| `candidate.run_commit` replaces `manifest.run_commit[0]` in every reader | K14 | `T-U-triage-18`, `-32`; `T-U-repair-09`; `T-U-gate-26`; the `run_manifest/calibration_two.json` fixture |
| `q3_after_parse`, FR-13.15's second conjunct | W15 | `T-U-gate-13`, `T-U-gate-23` |
| The restore re-hashes; `restore_hashes_match` | W21 | `T-U-repair-13`, `T-S-isolate-01` |
| B8 calls the chain inline; all sixteen `cfg` keys | W1, W2 | `T-U-repair-16`, `T-U-repair-17` |
| `_DICT_KEYS` gains `model_ids` and `stages_metered` | W8 | `T-U-schema-08` |
| `_check_field`'s int-for-float and bool-not-int rules | W24 | `T-U-schema-19` |
| `_FEEDBACK_DENY`, and FR-16.6's `(build_status, stopping_reason)` multiset | W16 | `T-U-feed-03`, `T-U-feed-05` |
| `_DEDUP_EVIDENCE_KEYS` is eight keys, enforced by `validate_candidate` | W22 | `T-U-triage-17`, `T-U-store-12` |
| The structural hash normalises symbol names | NIT 9 | `T-U-triage-06` |
| `reduction_wall_seconds` 600 and `artefact_inline_cap_bytes` 262,144 | W13, W26 | `T-U-store-03`, `T-U-budget-10` |
| The drawn calibration sample, and `budget.py`'s fifth check | W12 | `T-U-budget-11`, `T-U-byaml-04`, `T-U-driver-21` |
| `--refresh-mirror` | W25 | `T-U-driver-22` |
| `--runtime-env-json` is restored, carrying three non-secret variables | K13 | `T-U-submit-01`, `-03`, `-04`; `T-N-nfr06-01`; `T-S-submit-01` |
| The `oom` row requires death by signal; `parse_error` splits by reason | NIT 1, NIT 2 | `T-U-probe-12`, `T-U-probe-40`, `T-U-results-17` |
| The URL refusal moves to the accept side | NIT 14 | `T-U-appr-11` |
| The `fingerprint` `CHECK`, and `load_candidate` | NIT 3, NIT 4 | `T-U-store-11`, `T-U-store-13` |
| `cluster_gcp.yaml` parses through `load_config` | W28 | `T-U-cluster-06`, `T-U-cluster-07` |
| The `ast` walk's exempt list becomes three names | NIT 7 | `T-U-layout-02` |
| `git backfill --sparse` runs once, not "may run" | §4.12 | `T-U-driver-26` |

### 16.3 Two defects this resync found in **this** document, and fixed

Neither came from the LLD review and both would have made a test assert the wrong thing.

1. **§16's own item 8 named the wrong test.** It said `T-U-probe-15` was written against
   `BuildResult.peak_rss_bytes` and asserted only that the field was present; `T-U-probe-15` is and
   was the stdout and stderr capping test, and **no** test named the field at all. The field's tests
   are now `T-U-probe-42` and `T-U-core-14`, and `T-U-probe-15` is unchanged but for the cap figure.
2. **`T-U-image-05` compared a list of objects against a count of firings.** It compared
   `ImageSpec.assertion_nonreferencing`, a set of non-referencing `obj.CIRCT` object names, against
   `assertion_baseline_count` 18, which is `RunManifest`'s record of how many firings FR-07.9's
   control run over the lit corpus produced and is expected to be **zero**. The comparison is now
   against the committed `image/baseline_objects.txt`, which is where the 18 named objects live.

### 16.4 What is still open

Unchanged in kind, with one exception noted at its own row. Every item is a **measurement that has
not run**, not a specification that is missing. One was withdrawn on 2026-09-14 and two were added by
the backend fold-in; later the same day the image build **closed** one and the repair-backend decision
added two more, of which the second, stage 7's tokens, is the exception: it is a design limitation
with a named cause, not a measurement anyone can run (§16.6, `03-LLD.md` §15 item 9).

| Open | Where | What settles it |
|---|---|---|
| **A-08**, whether a generated harness compiles and runs against a generated design | `03-LLD.md` §3.6.3, §4.13, §15 item 1 | `T-U-probe-50`, tier 2, **skipped with the skip recorded** until A-19 answers |
| **A-19**, how many corpus seeds are differential-applicable | `03-LLD.md` §3.6.3 | F-08's first implementation task, running §3.6.3's applicability rule over the 187 seeds |
| **A-05**, the collision and false-merge rates | §10 | `T-U-triage-09` measures and prints them; the acceptance is that both are reported, not that either meets a threshold |
| Whether a revert-and-rebuild is bit-identical | `03-LLD.md` §15 item 4 | `T-S-isolate-01`, whose pass criterion is that the comparison is made and recorded |
| What 600 s of reduction budget buys | `03-LLD.md` §15 item 5 | `T-U-probe-38`'s `interestingness_calls` and `budget_truncated`, over the §6 sweep |
| ~~The two Claude model ids~~ **withdrawn 2026-09-14** | `03-LLD.md` §15 item 3 | nothing waits on them: no Claude model id is a default anywhere, and the ids matter only to an operator who runs `--repair-backend claude`, who passes one |
| ~~The slang build's wall time and image size~~ **closed 2026-09-14** | `03-LLD.md` §15 item 2 | W-04 built it: six targets, **972 s** at `-j8`, 703,211,208 B of binaries, branch (a) resolved, the 62 `REQUIRES: slang` lit tests running and green, and no seed exclusion needed. `T-U-image-14` asserts branch (a) against those figures |
| **The `-gline-tables-only` delta and the per-probe slowdown at image level** | `03-LLD.md` §15 item 8 | **W-04b**, the one comparison image FR-03.6 already needs. `T-U-image-06` is **skipped with the skip recorded** until it exists, never reported as a pass |
| **Stage 7's token counts**, which are a design limitation and not a pending measurement | `03-LLD.md` §15 item 9, §3.8 | nothing settles it short of editing `issue_task.py:124`, which FR-12.1's hunk equality forbids. `T-U-repair-23` asserts that the null is recorded with its reason and that zero is never written, and that is the whole of what a test can do here |
| **The two Vertex prices**, aggregator-sourced 2026-09-14 and `[UNVERIFIED]` against Google's page | `03-LLD.md` §9.1, §9.5, §15 item 6 | reading Google's own pricing page and rewriting the two figures **before** the commit that lands `budget.yaml`. No test can settle it, and none pretends to: `T-U-ledger-10` asserts the **arithmetic** against whatever the committed prices are, and `T-N-nfr08-02` asserts the results artefact prints the prices it used |
| **Whether the mocked loop matches the live one** | §0.3, `03-LLD.md` §15 item 7 | `T-S-pilot-01`, the first live request. Everything below T3 runs against CHIA's own fake `genai.Client`, which is the same fake CHIA validates its backend with, and no further offline evidence exists to gather |

**A-21 is closed and this plan no longer treats it as open.** M9 counted 487 closed and 101 open
`label:bug` issues on 2026-09-13, so FR-05.2's "the full history" is a real corpus, ADR-D-05's
fallback to the 24-month fix-commit set is not taken, and `T-U-msyn-05` asserts the figure. What
remains is sufficiency, whether 487 reports synthesise a **strong** set, which only F-05's own run
answers and which no number in either document depends on.

---

### 16.5 The backend fold-in, 2026-09-14

`design/ADR/ADR-D-03-model-backend.md` gained a superseding section on 2026-09-14 and it was folded
into `01-FRD.md` §1.8, `02-HLD.md` §0.2 and `03-LLD.md` §0, §1.4, §2.7, §3.5.1, §3.7, §3.8, §9,
§11.2, §12.1, §13 and §14.6 on the same day. **Seventeen tests were added and none was withdrawn.**
Every test whose behaviour changed keeps its identifier, as in §16.2.

| The change | Where the design carries it | Tests added or changed |
|---|---|---|
| The `vertex` backend in express mode, `gemini-3.8-flash` at every agent stage; no `gemini-3.1-pro-preview`, `claude-opus-5` or `claude-sonnet-5` default anywhere | `03-LLD.md` §3.5.1 | **`T-U-gen-23`** added; `T-U-driver-28` added; `T-U-byaml-01` extended |
| The **live-call interlock**, `BUGLOOP_ALLOW_LIVE_MODEL`, refusing in the construction path | `03-LLD.md` §3.5.1, §13.1 check 12 | **`T-U-gen-21`**, **`T-U-gen-22`**, **`T-U-layout-08`**, **`T-U-driver-27`** added; §0.5 and §15 gained the tier rule |
| `llm_turn`, because `QueryResult` carries no usage and a remote dispatch would drop the counts | `03-LLD.md` §3.5.1 | **`T-U-gen-24`**, **`T-U-gen-25`** added; `T-U-ledger-08` rewritten |
| The model layer is mocked the way CHIA mocks it, not with a new double | §0.3, the `fake_vertex` fixture | the `fixtures/vertex/` row of §13; every `gen` backend test |
| Four `budget.yaml` keys: `model_id`, `campaign_spend_cap_usd` and the two prices; `budget.py`'s sixth check | `03-LLD.md` §9.1, §9.2, §9.5 | **`T-U-budget-12`**, **`T-U-budget-13`** added; `T-U-budget-01` now 27 keys; the `budget/bad_prices/` fixture |
| The ledger prices tokens and stops on the USD cap | `03-LLD.md` §3.11 | **`T-U-ledger-10`**, **`T-U-ledger-11`** added; `T-N-nfr08-01` extended and **`T-N-nfr08-02`** added |
| The key is an environment variable, not a mount, and never job metadata | `03-LLD.md` §11.2, §12.1, §13.3, §13.4 | **`T-U-cluster-08`** added; `T-U-cluster-05`, `T-U-cluster-07`, `T-U-submit-01` extended; **`T-N-nfr06-02`** added and `T-N-nfr06-01` extended |
| Stage 7 cannot run on the campaign backend, and says so | `03-LLD.md` §3.8 | **`T-U-repair-20`** added; `T-U-driver-28` covers `stages_metered` |
| The loop's home is the team repository, with a sync script | `03-LLD.md` §1.4, `02-HLD.md` §8.2 | **`T-U-layout-09`** added; the `repo/chia_stub/` fixture |

**Two things this fold-in deliberately did not do.** It did **not** rename
`turn_cost.tokens_in`/`tokens_out`/`cost_usd` or `observed`'s three to `prompt_tokens`,
`output_tokens` and `usd`: `03-LLD.md` §2.2's own rule makes removing a declared dict key a **MAJOR**
bump, which would take the contract to 3.0, invalidate every committed fixture and move
`T-U-schema-01`'s two incompatible instances again, for a naming preference. The three keys are
re-stated at their meanings instead, `tokens_in` being prompt tokens, `tokens_out` output tokens and
`cost_usd` US dollars, and the contract stays at **2.0**. ~~It also did **not** add a `vertex` branch to
`examples/circt_issue_solver/issue_task.py`, which FR-12.1 pins byte for byte; that branch is offered
upstream and `T-U-repair-20` asserts the work-around instead.~~ **That second half is withdrawn the
same day by §16.6**: the branch is added, FR-12.1's acceptance becomes hunk equality, and
`T-U-repair-20` is rewritten to assert the decision rather than the work-around. The first half, the
key names and the contract version, stands.

---

### 16.6 The image build and the repair-backend decision, 2026-09-14

Two drivers, both later the same day than §16.5. `analysis/measurements/2026-09-14-image-build.md`
is the W-04 image build, which returned measured numbers where §1.22 asserted reference figures from
a different commit and a different target set. The architect's addendum to
`design/ADR/ADR-D-03-model-backend.md` puts **stage 7 on the campaign backend** by one additive
nineteen-line branch in `issue_task.py`. They are folded into `01-FRD.md` §1.9, `02-HLD.md` §0.3 and
`03-LLD.md` §1.2, §1.4, §2.5, §2.7, §3.8, §4.11, §4.11.1, §6.2, §13.1, §14.2, §14.4 and §14.6.
**Four tests were added, eight rewritten, and none withdrawn.** Every rewritten test keeps its
identifier, as in §16.2.

| The change | Where the design carries it | Tests added or changed |
|---|---|---|
| FR-12.1 becomes **hunk equality**: one additive `elif backend == "vertex":` arm, 19 insertions, 0 deletions | `01-FRD.md` FR-12.1, `03-LLD.md` §3.8 | `T-U-repair-07` **rewritten** from a `sha256` comparison to a parsed-diff comparison; **`T-U-repair-21`** added for the patch applying cleanly to `16c35e92` and for the sync script's idempotence |
| The branch builds the express client, project and location nulled, timeout in milliseconds | `03-LLD.md` §3.8's diff block | **`T-U-repair-22`** added, mocked with CHIA's own fake `genai.Client`, with three negative controls including the real `ValueError` |
| Stage 7 runs on `vertex`, `--repair-backend` defaults to `vertex`, `stages_metered["stage_7"]` is **true** | `03-LLD.md` §3.8, §13.1 | `T-U-repair-20` **rewritten** and now exercises both directions; `T-U-driver-28` **rewritten** for the default and the fallback |
| Stage 7's tokens stay **unobservable**, and the ledger records null rather than zero | `03-LLD.md` §3.8, §14.4, `01-FRD.md` FR-14.6 | **`T-U-repair-23`** added; `T-U-ledger-08` **rewritten** to assert `metered` true beside null tokens |
| The assertion baseline is re-based to **19** objects, 536 of 555 referencing | `01-FRD.md` FR-03.5 | `T-U-image-05` **rewritten**; the `image/baseline_objects.txt` fixture re-recorded |
| The lit evidence is now the image's own, and A-20's second half is W-04b | `01-FRD.md` A-20 | `T-U-image-06` **rewritten**, and **skipped with the skip recorded** until the second image exists |
| The campaign's pin is `eade0de61bc5` with `firtool-1.159.0`, six targets | `01-FRD.md` FR-03.7 | `T-U-image-07` **rewritten** |
| The interlock now has **two** construction paths to cover, so `repair_adapt` calls `require_live_model` before the chain and `bugloop_repair` carries the two environment variables | `03-LLD.md` §3.5.1, §3.8, §12.1, §13.1 check 12 | `T-U-layout-08` **rewritten** for two gated paths rather than one forbidden one; `T-U-repair-22` carries the refusal assertions |
| The seven Dockerfile deviations of `03-LLD.md` §4.11 | `03-LLD.md` §4.11, §4.11.1 | **`T-U-image-19`** added |

**One thing this fold-in deliberately did not do.** It did **not** add a fifth key to
`LedgerEntry.observed` for the token-capture reason. `_DICT_KEYS[("LedgerEntry", "observed")]` is
exactly four keys, `T-U-schema-08` asserts that an extra key fails as loudly as a missing one, and
`03-LLD.md` §2.2 makes adding a declared key a **MAJOR** bump to 3.0, which would invalidate every
committed fixture for a diagnostic string. The reason lives on `RepairResult.token_capture`, which is
the loop's own object and not a member of the seven-schema seam, and the contract stays at **2.0**.

### 16.7 Errata from implementation, 2026-09-14

`W-02` wrote §1.1's and §1.2's tests and `W-03` froze the package they test. Five places where this
plan and the committed tests differ are recorded here. **Four tests were added and no identifier
moved**: §1.1 is its 23 plus `T-U-schema-24` to `T-U-schema-27`, the four rules `BudgetFile`'s
`budget.yaml` keys brought (`03-LLD.md` §16), so `contract/schema.py` is 27 tests and
`contract/fixtures/` is still 3.

| The item | What the committed tests do | Why |
|---|---|---|
| `T-U-schema-20`'s wording | the `1.0` payload it rejects is a **complete** one, and a payload short of `diff` and `test_files` is asserted to raise `E002_MISSING_FIELD` **first** | §1.1's row says a `1.0` payload is rejected "before any key is read". That holds for `validate`, which checks the version first, and not for `from_json`, whose order is `E009`, then `json.loads`, then the missing-field check, then construction and `validate`. A short `1.0` payload therefore raises `E002` and never reaches `check_version`. The test asserts both orders rather than the one sentence, and `T-U-schema-01` keeps the `E001` pair on complete documents |
| `contract/fixtures/malformed/` | every malformed case is derived inside `test_schema.py` from the committed valid instance by the one edit §13 describes, and nothing malformed is committed | `T-U-fixt-01` validates **every** file under `contract/fixtures/`, so a committed malformed document would fail it by construction. The derivation is the same one edit either way; only its home moves, from a second committed document to the line of the test that needs it. §13's `malformed/` and `roundtrip/` rows describe fixtures this package does not commit, and `contract/fixtures/README.md` says so at the directory |
| The module for `T-U-fixt-*` | `circt_bug_loop/tests/test_fixtures.py` | §1.2 heads its table `contract/fixtures/` and names no test module, while §1.3 names `tests/test_layout.py` for `T-U-layout-*`. The three fixture tests walk the committed set and belong beside the schema tests, not inside them: `test_schema.py` tests the validator and `test_fixtures.py` tests the set the validator is pointed at |
| The tier markers | `pytest.ini` registers `t0`, `t1`, `t2` and `t3` **and** `needs_sdk`, `needs_image` and `needs_cluster`; a module states its tier with `pytestmark` | §0.5's table gives T1, T2 and T3 a `needs_*` marker and T0 none, and §14's matrix and §15's order select by tier. Both sets are therefore needed, the `t<N>` marker to select a tier and the `needs_*` marker to name the resource, and `--strict-markers` rejects an unregistered one, so all seven are registered with one line each |
| The `conftest.py` interlock | a session-scoped autouse fixture **asserts** that `BUGLOOP_ALLOW_LIVE_MODEL` is absent from the environment and fails the run if it is set | §0.5 has `conftest.py` delete the variable and set `GEMINI_API_KEY` to the synthetic value in `fixtures/secrets/known_values.txt`, so that `generate_task.build_llm` raises `LiveModelRefused` on any unmocked path. Neither the fixture nor `build_llm` exists yet, so there is nothing to set a key for and no refusal to reach. Refusing to start is strictly stronger than deleting the variable, and it is replaced by §0.5's rule verbatim when the secrets fixture and `build_llm` land; `T-U-layout-08` is the test that will then assert the fixture's own effect |
