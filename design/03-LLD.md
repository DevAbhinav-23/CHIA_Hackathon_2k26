# 03 Low-Level Design: the closed CIRCT bug loop

**Status: Draft.** Date: 2026-09-14. Normative for structure at the level of modules, classes,
schemas, file formats and command lines. `01-FRD.md` is normative for behaviour and `02-HLD.md` for
component structure; where this document contradicts either, that document wins and the
contradiction is a defect here (`00-README.md`).

Revised **again on 2026-09-14** to fold in the superseding section of
`design/ADR/ADR-D-03-model-backend.md`, the backend decision: CHIA's **`vertex`** backend in Vertex
AI express mode, model **`gemini-3.8-flash`** at every agent stage, the key delivered as an
environment variable, the ledger metering tokens and money, a live-call interlock, and the loop's
home moved to the team repository. `02-HLD.md` §0.2 lists that fold-in across the set; the sections
it changes here are §0, §1.4, §2.7, §3.5, §3.7, §3.8, §9, §11.2, §12.1, §13 and §14.6. No
`gemini-3.1-pro-preview`, `claude-opus-5` or `claude-sonnet-5` default survives in this document.

Revised 2026-09-14 in answer to `design/reviews/red-team-LLD.md`. All 61 of its findings are
dispositioned in `design/reviews/red-team-LLD-disposition.md`. The revision bumps the contract
package to **2.0** (§2.1), moves three nodes to the head (§3.2), and raises six errata against
`01-FRD.md`, carried in that document's §1.7. Every claim the revision adds was executed on
2026-09-14 against the same authorities §0 names, and the command and its output are recorded beside
the claim.

This document answers `01-FRD.md` §10.2's sixteen items and the fourteen the `02-HLD.md` component
list implies, in one order. The standard it is written to: **an engineer types it in without asking a
question.** Where a value is chosen rather than derived it carries `[DEFAULT]` and names its home;
where a fact could not be verified it carries `[UNVERIFIED]` and names the measurement that would
settle it.

## 0. Conventions

**Citations.** `chia:<path>:<lines>` is a path under `~/.cache/chia-src` at commit `16c35e92`.
`circt:<path>:<lines>` is a path under `~/.cache/chia-pin-smoke/circt` at `b792c772`. A tool flag
marked **verified** was obtained by running `--help` on 2026-09-13 against the SDK at
`~/.cache/chia-pin-smoke/circt-sdk` under
`LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim`, or against the
measured assertions-on build at `~/.cache/chia-pin-smoke/bassert_g`, or against the host's own
`verilator`, `prlimit`, `timeout`, `ninja`, `cmake`, `git` and `lit`. **measured** means a figure
from `analysis/measurements/2026-09-13-frd-followups.md` or from a command run while writing this
document.

**Numbers.** Every number comes from `01-FRD.md`, `02-HLD.md`, the measurements, or carries
`[DEFAULT]`. A `[DEFAULT]` that parameterises the **campaign** is a `budget.yaml` key and §9 lists
every one; a `[DEFAULT]` that is an implementation **constant** is fixed in this document and §9.4
lists every one; a `[DEFAULT]` that sizes a **fixture** belongs to `04-Test-Plan.md` and is named
here only where an FR's own acceptance criterion places it in `budget.yaml` as well (FR-14.1's
carve-out, resolved in §9.3).

**Spelling** is British. No em-dashes anywhere, in this document or in any string it specifies.

**Dependencies.** CHIA's own dependencies plus the Python standard library, and nothing else. The
modules used are `argparse`, `dataclasses`, `datetime`, `difflib`, `glob`, `hashlib`, `inspect`,
`itertools`, `json`, `os`, `pathlib`, `random`, `re`, `shlex`, `shutil`, `signal`, `socket`,
`sqlite3`, `string`, `subprocess`, `sys`, `tempfile`, `time`, `typing`, `urllib` and `uuid`, all
standard library, plus `yaml` and `ray`, both already CHIA dependencies, and, from the backend
decision, `google-genai` and `mcp`, which CHIA's `vertex` backend imports lazily
(`chia:chia/models/vertex.py:401-404`) and which are already CHIA dependencies too
(`chia:pyproject.toml:24-35`: `google-genai>=1.64.0`, `mcp==1.27.1`). The loop imports neither
directly; it imports `chia.models.vertex`.
Two **commands** are used that are not Python: `prlimit(1)` and `timeout(1)`, from util-linux and
coreutils respectively, both already in the image's base (§4.9). Invoking a command is not importing
a library, so FR-19.8's dependency list is unchanged and NFR-11 is untouched.

**Reuse is named before anything is written.** Every function below that could have been CHIA's
either is CHIA's or says in one line why it is not. The index of reuse is §14.3.

---

## 1. Repository layout

### 1.1 `examples/circt_bug_loop/`

One directory, a sibling of `examples/circt_issue_solver/`, as `02-HLD.md` §8.2 fixes. Every file,
with its one-line purpose and the components of `02-HLD.md` §1 it holds.

| Path | Purpose | Components |
|---|---|---|
| `README.md` | The flow in CHIA's own README shape: what it does, how to bring the cluster up, how to submit, what it writes, what it never does (NFR-12). | none |
| `bug_loop.py` | The campaign driver. Parses argv, builds the `RunManifest`, opens both stores, runs the pre-flight checks, sequences the two arm windows, reconciles at the end. | B12 |
| `contract/__init__.py` | Re-exports `schema`'s public names so a consumer writes `from contract import ProbeSpec`. | seam |
| `contract/schema.py` | The whole seam: `CONTRACT_VERSION`, the seven dataclasses, the three nested dataclasses, the `Generator` protocol, `validate`, `to_json`, `from_json`, the error codes. Imports nothing outside the standard library. | seam |
| `contract/fixtures/` | Committed recorded instances, `<schema>/<id>.json`, one document per file, the enforcement point for the compatibility rule (`02-HLD.md` §2.13). | seam |
| `corpus.py` | Mines the clone by PIN §2's rule, normalises every `RUN:` line, emits `SeedRecord[]` and the `SdkMap`. | A1 |
| `pin_select.py` | Walks `main` first-parent to the newest commit whose LLVM pin has a `firtool-*` release; reports the lag. | A2 |
| `generate_task.py` | Both generators and the two agent-facing tools: the seeded arm's two turns, the mutation arm's deterministic runner, `ProbeWriteTool`, `SourceReadTool`. | A3, A4, `ProbeWriteTool`, `SourceReadTool` |
| `mutator_synth.py` | The offline, once, pre-registration mutator synthesis and the freeze. Not imported by the campaign. | A7 |
| `mutators/__init__.py` | Loads the frozen set, checks its digest, exposes `apply(mutator_id, text, seed_int)`. | A4's set |
| `mutators/set_v1.json` | The frozen set itself: one JSON document, versioned, digest recorded in the `RunManifest`. | A4's set |
| `probe_task.py` | The four apparatus nodes that touch a probe: execute, judge, differential, reduce. Worker-side; imports no head module. | B2, B3, B4, B5 |
| `ddmin.py` | The textual reducer of FR-09.10: ddmin over lines, standard library only, no CIRCT knowledge. | B5's second reducer |
| `triage_task.py` | The issue mirror, the fingerprint and dedup and contamination screen, the triage turn and the report render. | B6a, B6b, B7 |
| `repair_adapter.py` | The shim that presents a local report to CHIA's unmodified chain, then restores the worker. | B8 |
| `gate.py` | The four mechanical questions, the re-run dispatch, the `GateDecision`. | B9a, B9b |
| `approve.py` | The `bugloop-approve` CLI: one pending report, one human, one approval, one licence confirmation, one URL. | B9c |
| `budget.py` | Loads and validates `budget.yaml`, enforces the pre-registration rule, hands out `LedgerSnapshot`s. | A6a |
| `ledger.py` | Appends `LedgerEntry` rows and maintains the per-arm and per-stage aggregate. | A6b |
| `feedback.py` | Builds the `FeedbackBundle` from an iteration's `ProbeResult`s and owns FR-16.6's abandonment. | A5 |
| `store.py` | `LoopStore`, the loop's `SQLiteNode`; the DDL; every apparatus-internal record dataclass; `artefact_write`. | B10a, B10b |
| `results.py` | Renders the results artefact and refuses to render without every mandatory element. | B11 |
| `prompts/seed_read.md` | Stage 1: read the seed, state the root-cause class, name sibling sites. | A3 |
| `prompts/probe_write.md` | Stage 2: write probing inputs into the probe directory and declare them. | A3 |
| `prompts/report_write.md` | Stage 6: classify advisorily and write the prose half of the report. | B7 |
| `prompts/mutator_synth.md` | Offline: synthesise mutators from the closed `label:bug` history. | A7 |
| `cluster_single.yaml` | The single-machine cluster, NFR-10's Must and the campaign's configuration. | §12.1 |
| `cluster_gcp.yaml` | The GCP skeleton, ADR-D-14's Should, deferred. | §12.2 |
| `env.yml` | The head's conda environment, in CHIA's shape. | none |
| `bug_loop_submit.sh` | The `chia job submit` wrapper, carrying no token in `--runtime-env-json`. | §13.3 |
| `budget.yaml` | The pre-registered budget (F-14). Committed before the campaign; its commit is the registration. | §9 |
| `pyproject.toml` | The example's own packaging: one `[project.scripts]` entry, `bugloop-approve = "approve:main"`, which is how §13.2's CLI is installed. Nothing else; the flow is not a library. | §13.2 |
| `.gitignore` | Two lines, `loop.db` and `loop.db-*`, so an 8-hour campaign's database and its WAL companions cannot be committed by accident. | §6.1 |
| `tests/` | Unit tests for the flow-specific code (FR-19.5); layout mirrors the modules, §1.3. | none |

Two paths the flow **writes** and does not ship: `loop.db` at `<repo>/examples/circt_bug_loop/loop.db`
(§6.1), ignored by the line above, and `issue_logs/`, which is CHIA's own and lives under
`examples/circt_issue_solver/`. Neither is a source file, so neither has a row above (W19).

`ddmin.py` is the one file `02-HLD.md` §8.2 does not name, and it is not a new component: it is
B5's textual reducer, which the HLD places inside B5 and §9 calls "a short standard-library
function". It is a file of its own for one reason: it is the only piece of the apparatus with no
CIRCT knowledge at all, so it is the only piece that can be unit-tested with no CIRCT present, which
is what `04-Test-Plan.md` needs of it. If that reason is rejected, its twenty lines move into
`probe_task.py` and nothing else changes.

### 1.2 The three CHIA additions, plus the fourth

`02-HLD.md` §8.3 counts four, all additions, none a modification of an existing line.

| Path under `~/.cache/chia-src` | Purpose |
|---|---|
| `dockerfiles/ChiaCirctAssertDockerfile` | B1's image. `FROM` CHIA's own `ChiaCirctBaseDockerfile` layers, plus fetch-by-SHA, the pin equality check, `-O3 -UNDEBUG -gline-tables-only`, `-DMLIR_SOURCE_DIR=/opt/circt-sdk` (FR-03.17), the whole target list baked, the slang front end, Verilator, `openssh-client`, `rsync`, `util-linux` and `lit`. §4.10 gives its configure and build lines in full. |
| `.github/workflows/chia-circt-assert.yml` | The workflow CHIA requires for every new Dockerfile (`chia:AGENTS.md:124`). |
| `chia/chipyard/circt.py` | Appended to, never edited: `circt_exec_probe`, `circt_reduce_run`, `circt_symbolize`. §3.10 gives all three. |
| `chia/chipyard/test/test_circt_probe.py` | The tests for those three, in the directory CHIA names (`chia:AGENTS.md:122`; the directory in the tree is `chia/chipyard/test`, singular). |

Nothing else under `chia/` changes. ~~`examples/circt_issue_solver/issue_task.py` and all six of its
prompts stay byte-identical and are checked as such (FR-12.1, FR-12.9).~~ **Corrected 2026-09-14**
(§3.8, `01-FRD.md` §1.9): all six **prompts** stay byte-identical and are checked as such (FR-12.9),
and `issue_task.py` gains **one additive `elif backend == "vertex":` branch in `_turn`**, nineteen
lines, no deletion, carried as `upstream/issue_task-vertex-branch.patch` and checked by hunk equality
against `16c35e92` (FR-12.1, as amended). That makes the CHIA additions **five**, four files plus one
patch, and the fifth is the only one that touches a file CHIA already has under `examples/`.

### 1.3 Test layout, mirroring the modules

`examples/circt_bug_loop/tests/` holds one test module per source module **that holds logic**, named
`test_<module>.py`, so a reader finds a module's tests by name and `04-Test-Plan.md`'s traceability
table has a mechanical target. The mapping is stated exactly, because the earlier "one-to-one"
wording was false and would have been asserted by a test that fails on itself (W6):

- **Eighteen source modules hold logic and each has its test module** below: `bug_loop.py`,
  `contract/schema.py`, `corpus.py`, `pin_select.py`, `generate_task.py`, `mutator_synth.py`,
  `mutators/__init__.py`, `probe_task.py`, `ddmin.py`, `triage_task.py`, `repair_adapter.py`,
  `gate.py`, `approve.py`, `budget.py`, `ledger.py`, `feedback.py`, `store.py`, `results.py`.
- **One source module holds no logic and has no test module of its own**: `contract/__init__.py` is a
  re-export list, and `tests/test_schema.py` imports every public name through it, which is the only
  behaviour it has.
- **Two test modules are structural and have no source counterpart**: `test_layout.py`, which asserts
  the three properties below, and `test_fixtures.py`, which validates the committed fixture set.
- **Five artefacts of §1.1 and §1.2 are not Python modules, each has a named test module, and each is
  exempt from the mapping above by name.** The rule the mapping states is a rule over **source
  modules**, and these five are a Dockerfile, a directory of prompts, two YAML files, a shell script
  and a YAML data file; none of them can have a `test_<module>.py` counterpart under the rule because
  none of them is a module. The exemption is stated here, by name, so that a test asserting the
  mapping does not fail on this document's own file list.

| Artefact | Test module | What it asserts |
|---|---|---|
| `dockerfiles/ChiaCirctAssertDockerfile` and the `ImageSpec` it emits (§1.2, §4.11) | `tests/test_image_spec.py` | the built image and the recorded `ImageSpec`; F-03's requirements, which need a Docker build and have no in-process substitute |
| `prompts/` and the shared JSON-footer parser (§7) | `tests/test_prompts.py` | every substitution variable of §7.2, §7.3, §7.4 and §8.3 is declared in its file and supplied by its caller; the footer parser's four failure reasons |
| `cluster_single.yaml` and `cluster_gcp.yaml` (§12) | `tests/test_cluster_yaml.py` | both files load through `chia.cluster.config.load_config`; the three worker types, the three resource names, `--user` on every type, no credential anywhere |
| `bug_loop_submit.sh` (§13.3) | `tests/test_submit.py` | no token anywhere in it; `--runtime-env-json` carrying exactly the three non-secret variables; the `exec` line |
| `budget.yaml` (§9) | `tests/test_budget_yaml.py` | the committed file against §9.1's schema, and every campaign `[DEFAULT]` marker of `01-FRD.md` resolving to exactly one of its keys |

`tests/test_layout.py` has exactly three jobs and the earlier "and nothing else" is withdrawn:
(1) the mapping above, as the four sets just named rather than as an equality of directory listings,
with the five artefact test modules named in an exemption list the test compares for equality;
(2) the check that no `store.py` name is imported by any supply-half module (§2.9, FR-16.1); and
(3) the `ast` walk of §14.5 for FR-18.1. All three are layout properties of the repository, which is
why they share one module.

**Twenty-five test modules under `tests/`**: eighteen for the source modules that hold logic, two
structural, and five for the artefacts above.

```
tests/
  test_layout.py          the three layout properties above and nothing else
  test_schema.py          contract/schema.py: every validator error code, both serialisers
  test_fixtures.py        contract/fixtures/: every committed fixture validates at its version
  test_corpus.py          corpus.py, including one RUN: line of every shape of FR-01.10
  test_pin_select.py      pin_select.py, including the no-match and multi-tag paths
  test_generate_task.py   generate_task.py: the emitter, the cap, the tool list, the mutation runner
  test_mutators.py        mutators/: determinism, no-ops, a raising mutator, the digest check
  test_mutator_synth.py   mutator_synth.py: the parse, the freeze, the post-registration refusal
  test_probe_task.py      probe_task.py: the seven statuses, the three oracle classes, the limits
  test_ddmin.py           ddmin.py: the fixture of FR-09.10, termination, invocation count
  test_triage_task.py     triage_task.py: fingerprint normalisation, the partition, both screens
  test_repair_adapter.py  repair_adapter.py: the identifier, the repro polarity, the restore
  test_gate.py            gate.py: all four questions, every stopping value, the default to nothing
  test_approve.py         approve.py: the cap, the licence downgrade, the walk-away, the URL
  test_budget.py          budget.py: the schema, the pre-registration rule, the five checks
  test_ledger.py          ledger.py: the three arms, the two scopes, the stop rule
  test_feedback.py        feedback.py: one entry per probe, the abandonment rule, the deny-list
  test_store.py           store.py: the DDL, the write order, the PARTIAL marker, the cap rule
  test_results.py         results.py: every render refusal, and the zero-bug render
  test_bug_loop.py        bug_loop.py: argv, the pre-flight refusals, the reconciliation
  test_image_spec.py      the Dockerfile and the ImageSpec          (artefact, exempt)
  test_prompts.py         prompts/ and the shared footer parser     (artefact, exempt)
  test_cluster_yaml.py    both cluster YAMLs                        (artefact, exempt)
  test_submit.py          bug_loop_submit.sh                        (artefact, exempt)
  test_budget_yaml.py     the committed budget.yaml                 (artefact, exempt)
```

`chia/chipyard/test/test_circt_probe.py` covers the three core additions and is counted separately,
which is FR-19.5's point: a test under the example directory does not discharge a contribution to
`chia/`.

### 1.4 Where the loop actually lives, 2026-09-14 erratum

§1.1 and §1.2 are written in **published** paths, `examples/circt_bug_loop/` and the four files under
`chia/`, because those are the paths the upstream pull request creates and the paths every
`chia:` citation in this document is relative to. The loop is **not developed there**, and this
section is the erratum that says so (`02-HLD.md` §8.2).

| Tree | Path | Holds |
|---|---|---|
| team repository, `https://github.com/DevAbhinav-23/CHIA_Hackathon_2k26`, cloned at `~/Projects/CHIA_Hackathon_2k26` | `circt_bug_loop/` | the loop, with **exactly** §1.1's internal layout: the same file names, the same `contract/`, `mutators/`, `prompts/` and `tests/` subdirectories, in the same relative positions |
| the same repository | `upstream/` | the CHIA-core proposals of §1.2: `ChiaCirctAssertDockerfile`, `chia-circt-assert.yml`, the three generic functions plus their tests **as a patch** against `chia/chipyard/`, and, added 2026-09-14, **`issue_task-vertex-branch.patch`**, the nineteen-line `elif backend == "vertex":` arm for `examples/circt_issue_solver/issue_task.py` (§3.8) |
| the same repository | `upstream/sync-to-chia.sh` | copies `circt_bug_loop/` into a CHIA checkout as `examples/circt_bug_loop/` and applies `upstream/`'s core files |
| CHIA checkout, cloned at `~/Projects/chia-bugloop`, branch `bugloop` | `examples/circt_bug_loop/` and the four files of §1.2 | what the pull request against `ucb-bar/chia` contains, produced only by that script |

`sync-to-chia.sh` takes one argument, the CHIA checkout, and does ~~four~~ **five** things and no
more: refuse unless the target holds `chia/` and `examples/circt_issue_solver/`; `rsync -a --delete
--exclude '__pycache__' --exclude '*.pyc' --exclude 'loop.db*' circt_bug_loop/
<checkout>/examples/circt_bug_loop/`; copy `upstream/ChiaCirctAssertDockerfile` to
`<checkout>/dockerfiles/` and `upstream/chia-circt-assert.yml` to `<checkout>/.github/workflows/`;
`git -C <checkout> apply --3way upstream/chipyard-circt-probe.patch`; and, **added 2026-09-14**,
`git -C <checkout> apply --3way upstream/issue_task-vertex-branch.patch` **unless that branch is
already present**, so that a checkout synced twice is not patched twice and a checkout tracking a
CHIA that has merged the branch is left alone. It writes nothing in the
team repository and it is idempotent: running it twice leaves the checkout byte-identical, which is
what `tests/test_layout.py` asserts by running it into a temporary copy and diffing, and the
already-present guard is what keeps that true for the fifth step.

**The one thing the code can see.** A module that derives CHIA's package directory from its own
location is correct from `examples/circt_bug_loop/` and wrong from `circt_bug_loop/`, where the
repository root is not a CHIA checkout and `../../chia` does not exist. §13.1 therefore derives that
path from the **imported `chia` module** and never from the flow directory's ancestors, and
`tests/test_layout.py` asserts that no module in the flow computes `Path(__file__).parents[2]` or
any longer walk. Nothing else in §1.1, §1.2 or §1.3 changes: the internal layout is the same in both
trees, so every path this document gives below the flow directory is correct in both.

---

## 2. The contract package, and every data object

`02-HLD.md` §2 fixes the members, their fields, what is required and what every declared `dict`
contains. This section fixes the Python, the JSON, the version check and the validator's named
errors, and then gives a dataclass to every remaining object of FRD §2.5 so that none is left
without one.

### 2.1 `contract/schema.py`: header, version and errors

Every dataclass in this package is `@dataclass(kw_only=True)`. Keyword-only construction is what
lets `contract_version` sit first in the declaration while optional fields carry defaults, without
the ordering rule that otherwise forces defaults last; `kw_only` arrived in Python 3.10 and CHIA is
pinned to 3.10.19 (`chia:docs/user_guides/docker_images.rst:28-31`), so it is available and costs
nothing.

```python
"""The one versioned seam between the supply half and the apparatus half.

Seven schemas and one interface (G-47). Standard library only: no serialisation
library, no schema library, no validation library. Imported by both halves and
by nothing outside them.
"""
from __future__ import annotations

import dataclasses
import json
import typing
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol

CONTRACT_VERSION = "2.0"          # MAJOR.MINOR; the single source of the string

Arm = Literal["seeded", "mutation"]
LedgerArm = Literal["seeded", "mutation", "shared"]
Polarity = Literal["expect_zero", "expect_nonzero"]
Shape = Literal["plain", "split_file", "unsupported"]
BuildStatus = Literal["clean_exit", "parse_error", "assertion", "fatal_error",
                      "crash", "timeout", "oom"]
OracleClass = Literal["assertion", "fatal_error", "crash", "differential"]
LimitHit = Literal["wall", "cpu", "address_space"]
Scope = Literal["arm_window", "stage"]
Mode = Literal["discovery", "calibration"]
SeedSet = Literal["187", "171"]
Deployment = Literal["single_machine", "gcp"]
Unit = Literal["wall_clock_seconds"]

# The stage ids of 00-README.md, fixed there and not renameable. They are the
# key set of RunManifest.stages_metered (FR-14.8) and the value set of
# ProbeResult.stopping_stage from stage_3 onward.
_STAGE_IDS = ("stage_1", "stage_2", "stage_3", "stage_4", "stage_5",
              "stage_6", "stage_7", "gate")


class ContractError(Exception):
    """Raised by validate(). Carries a stable code so tests assert on the code."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")
```

The codes are closed. No other code exists, and `04-Test-Plan.md` exercises every one.

| Code | Raised when |
|---|---|
| `E001_MAJOR_MISMATCH` | The instance's `contract_version` MAJOR differs from `CONTRACT_VERSION`'s MAJOR. The message names both versions verbatim. |
| `E002_MISSING_FIELD` | A required field is `None`, or absent from a `from_json` payload. |
| `E003_WRONG_TYPE` | A field's runtime type does not match its annotation, after `Optional` is unwrapped. |
| `E004_BAD_ENUM` | A field annotated `Literal[...]` holds a value outside that set. |
| `E005_CONDITIONAL_REQUIRED` | A conditional field is `None` where its rule requires a value (for example `mutator_id` on `arm == "mutation"`). |
| `E006_CONDITIONAL_FORBIDDEN` | A conditional field holds a value where its rule requires `None` (for example `mutator_id` on `arm == "seeded"`, or any reduction field on `oracle_class == "differential"`). |
| `E007_BAD_DICT_KEYS` | A declared `dict` field's key set differs from the closed set of `02-HLD.md` §2.11. |
| `E008_CAP_EXCEEDED` | A bounded text field exceeds the artefact cap while its companion path field is `None` (§2.12's rule, inverted). |
| `E009_UNKNOWN_SCHEMA` | `from_json` is handed a class that is not a package member. |
| `E010_TOOL_MISMATCH` | A `ProbeSpec`'s `tool` differs from its seed's `entry_tool`. Raised by `generate_task.emit_specs` and by nothing else, because `validate` is handed one object and has no access to the `SeedRecord` the comparison needs. It carries the same exception type and the same code shape as the nine above so a caller catches one class (K10, FR-04.2 as amended in `01-FRD.md` §1.7). |

**The scheme extends past `E010`, and only in one place.** `store.validate_candidate` (§2.9) raises
`E011` to `E013` for the three rules a `CandidateRecord` has and no contract member does. It imports
`ContractError` from this package rather than declaring an exception of its own, so a caller catches
one class across both validators, and the codes are disjoint by construction because this table owns
`E001` to `E010` and §2.9 owns `E011` onwards. `validate` never raises `E011` to `E013` and
`validate_candidate` never raises `E001`, `E007`, `E008`, `E009` or `E010`; §2.9's table says which
codes it does reuse.

**Why the contract is at 2.0.** `SeedRecord` gained two required fields, `diff` and `test_files`
(§2.4), which §2.2's own rule makes a MAJOR bump: "MAJOR moves when a required field is added". The
bump is what pays for K5 and K6, the finding that neither generator arm could reach its seed's
contents. `00-README.md` §"The seam rule" and `02-HLD.md` §2.4 carry the same two fields and the same
version.

### 2.2 The compatibility check

```python
def _major(version: str) -> str:
    """MAJOR half of a MAJOR.MINOR version string."""
    return version.split(".", 1)[0]


def check_version(instance_version: str) -> None:
    """Raise E001 unless *instance_version*'s MAJOR equals this package's.

    The whole compatibility rule: MAJOR equal accepts, anything else rejects,
    with both versions named. No negotiation, no shim, no tolerance window
    (02-HLD.md 2.2).
    """
    if _major(instance_version) != _major(CONTRACT_VERSION):
        raise ContractError(
            "E001_MAJOR_MISMATCH",
            f"instance contract_version {instance_version!r} is incompatible "
            f"with package CONTRACT_VERSION {CONTRACT_VERSION!r}")
```

MINOR moves when a member gains an optional field; MAJOR moves when a required field is added,
removed, renamed or retyped. The place the rule fires is the committed fixture set: `tests/
test_fixtures.py` runs `validate` over every file under `contract/fixtures/`, so a MAJOR bump is a
commit that must also re-record the fixtures and the failing test is what says so.

### 2.3 Serialisation

One rule for every member, so that two equal objects serialise to identical bytes, which is what
FR-01.6's byte-identical acceptance and NFR-02's determinism rest on.

```python
def to_json(obj: Any) -> str:
    """Serialise a contract instance to canonical JSON text.

    Canonical means: keys sorted, two-space indent, no ASCII escaping (so a
    UTF-8 identifier survives as itself), one trailing newline. Two equal
    objects therefore produce identical bytes.
    """
    return json.dumps(dataclasses.asdict(obj), sort_keys=True, indent=2,
                      ensure_ascii=False, separators=(",", ": ")) + "\n"


def from_json(text: str, cls: type) -> Any:
    """Parse canonical JSON text into *cls*, then validate it.

    A payload key the class does not declare is DROPPED, deliberately and
    silently: that is what makes a MINOR-newer document readable by a
    MINOR-older package, which is the whole content of 2.2's MINOR rule. A
    MAJOR-newer document is rejected by check_version before any key is read,
    so the drop can never lose a required field.

    Raises E009 for a class outside the package, E002 for a payload missing a
    field the class declares, and whatever validate() raises.
    """
    if cls not in _MEMBERS:
        raise ContractError("E009_UNKNOWN_SCHEMA", f"{cls!r} is not a contract member")
    payload = json.loads(text)
    names = {f.name for f in dataclasses.fields(cls)}
    missing = sorted(names - set(payload))
    if missing:
        raise ContractError("E002_MISSING_FIELD",
                            f"{cls.__name__} payload lacks {missing}")
    obj = cls(**{k: v for k, v in payload.items() if k in names})
    validate(obj)
    return obj
```

- **Encoding.** Files are written and read as UTF-8 with no byte-order mark, `newline="\n"`.
- **Nested dataclasses** (`FeedbackEntry`, `RunCommit`, `LedgerSnapshot`) round-trip as plain JSON
  objects, which `dataclasses.asdict` produces recursively; `from_json` rebuilds them in the owning
  member's `__post_init__`, which is the only place a nested type is reconstructed.
- **Bytes-like text.** No field is `bytes`. Tool output is not guaranteed UTF-8, so every producer
  decodes it once, at capture, with `text.decode("utf-8", errors="backslashreplace")`. That is
  deterministic, printable, and reversible by inspection, and it is the reason a captured stderr can
  sit in a JSON document at all. `errors="replace"` is not used: it destroys the bytes, and an
  assertion expression carrying a non-UTF-8 identifier would then fingerprint as whatever `replace`
  produced.
- **Floats.** Only `LedgerEntry.amount`, `RunManifest.lag_days`, `RunManifest.arm_window_seconds`,
  `BudgetFile.arm_window_seconds` and the `observed` costs are floats. They are written by
  `json.dumps`'s `repr` and are never compared for equality by any requirement. **An `int` is an
  acceptable value for every one of them**, and §2.6's `_check_field` says so in code: every duration
  the loop computes is a whole number of seconds, `git rev-list --count` differences are `int`, and
  `getrusage` CPU is the one that is genuinely fractional. Measured 2026-09-14,
  `python3 -c 'print(isinstance(5, float))'` prints `False`, so without that clause a per-stage
  occupancy of five seconds would fail `validate` at run time (W24).

### 2.4 The seven members

The field lists are `02-HLD.md` §2.4 to §2.10 verbatim, typed.

```python
@dataclass(kw_only=True)
class SeedRecord:
    """One mined CIRCT fix commit and everything both arms need from it.

    Produced by A1 (corpus.py) on the head. Read by A3, A4, B6b and B12. In the
    package because FR-15.1's screen needs committed_date_utc and it lives
    nowhere else.

    `diff` and `test_files` arrived at contract 2.0 and are what make the record
    self-contained: A3 substitutes them into 7.2's prompt and A4 mutates
    test_files' values, so neither arm needs git, a clone, or the CIRCT tree at
    all (K5, K6). Both are populated by A1 alone, on the head, where the clone
    is. Both are REQUIRED fields, so neither goes through bound_text, which
    returns None: A1 instead measures len(text.encode("utf-8")) against
    budget.yaml's artefact_inline_cap_bytes and marks a seed whose diff or whose
    test files exceed it ineligible for BOTH arms, with
    exclusion_reason="seed_text_over_cap", counted and reported. A truncated
    diff in a prompt would be worse than a missing seed.
    """
    contract_version: str = CONTRACT_VERSION
    seed_sha: str
    parent_sha: str
    subject: str
    committed_date_utc: str                 # ISO 8601 with an explicit offset
    source_paths: list[str]                 # under lib/ or include/, git order
    test_paths: list[str]                   # under test/ or integration_test/, git order, never collapsed
    llvm_pin: str                           # 40 hex characters
    sdk_tag: Optional[str]                  # firtool-* or None
    sdk_exact: bool
    bumps_away: Optional[int]               # None when sdk_exact is True
    entry_tool: Literal["circt-opt", "firtool", "circt-verilog",
                        "circt-translate", "arcilator", "other"]
    dialect_bucket: str                     # FR-01.4's dialect-level rule, normative
    dialect_bucket_unmerged: str            # FR-01.4's second rule, for FINAL Appendix A
    run_lines: list[str]                    # verbatim RUN: lines, joined continuations
    argv_template: list[list[str]]          # one normalised argv per run line
    polarity: list[Polarity]                # one per run line
    shape: list[Shape]                      # one per run line
    diff: str                               # 2.0: the seed commit's diff of its source_paths
    test_files: dict[str, str]              # 2.0: test_paths -> full text at the seed commit
    corpus_head_sha: str


@dataclass(kw_only=True)
class BudgetFile:
    """The parsed, committed budget.yaml. Section 9 is its schema.

    Produced by A6a (budget.py). Read by A6a, A6b, B9c and B12. Its keys are
    exactly FR-14.1's list and no others, which is what makes the
    pre-registration of FR-14.2 mean anything.
    """
    contract_version: str = CONTRACT_VERSION
    budget_file_sha: str                    # the commit that landed this file
    arm_window_seconds: float
    arm_order: list[Arm]
    generated_inputs_per_day: int
    filings_per_day: int
    filings_total: int
    campaign_start_utc: str
    campaign_end_utc: str
    corpus_head_sha: str
    fingerprint_top_n: int
    calibration_sample_size: int
    calibration_sample_shas: list[str]
    per_seed_probe_cap: int
    per_seed_iteration_cap: int
    probe_wall_seconds: int
    probe_address_space_bytes: int
    probe_cpu_seconds: int
    probe_output_byte_cap: int
    reduction_wall_seconds: int
    reduction_sigkill_grace_seconds: int
    issue_mirror_issue_cap: int
    filing_poll_window_seconds: int
    artefact_inline_cap_bytes: int
    acceptance: dict                        # keys in 9.3


@dataclass(kw_only=True)
class ProbeSpec:
    """One probing input plus the exact invocation that consumes it.

    Produced by A3 and A4 (generate_task.py). Consumed by B2, B4 and B5. The
    apparatus cannot tell the arms apart from it except by reading `arm`, which
    FR-18.1 permits it to carry and forbids it to branch on.
    """
    contract_version: str = CONTRACT_VERSION
    probe_id: str
    run_manifest_id: str
    seed_sha: str
    arm: Arm
    iteration: int
    input_filename: str
    input_path: str                         # always set; absolute, under the artefact root
    tool: str
    argv: list[str]
    polarity: Polarity
    shape: Shape
    expected_outcome: str
    turn_cost: dict                         # keys in 2.7
    input_text: Optional[str] = None        # conditional, 2.12's cap rule; see below
    mutator_id: Optional[str] = None        # conditional on arm
    mutator_seed_int: Optional[int] = None  # conditional on arm
    source_test_path: Optional[str] = None  # conditional on arm
    differential: Optional[dict] = None     # keys in 2.7; None when FR-08.1 excludes the probe
```

**`input_text` is optional and `input_path` is not, which is a conflict with FR-04.3 and is resolved
in the FRD rather than here** (W9). FR-04.3's requirement text lists "the input file contents" among
the fields the spec shall carry and its acceptance criterion is "the contract validator accepts only
specs with every field populated"; `02-HLD.md` §2.12's cap rule makes the inline copy conditional on
size. Under `00-README.md` the FRD wins, so the FRD is amended rather than the LLD: `01-FRD.md`
§1.7's erratum at FR-04.3 reads the contents as **carried inline or by the always-populated
`input_path`**, and the validator's criterion becomes "every field populated, `input_text` counted as
populated when `input_path` is". The line that enforces it is in §2.8's `_probe_spec_conditionals`,
where the other conditional rules already live.

```python
@dataclass(kw_only=True)
class ProbeResult:
    """One per probing input, always produced, whatever the outcome.

    Produced by B2 and completed by the stage the probe stopped at. Consumed by
    A5, A6b, B11 and B12. This is the only object that crosses the seam upward,
    and it carries nothing the generator may not see (FR-16.4).
    """
    contract_version: str = CONTRACT_VERSION
    probe_id: str
    run_manifest_id: str
    seed_sha: str
    arm: Arm
    iteration: int
    build_status: BuildStatus
    oracle_fired: bool
    stopping_stage: Literal["stage_3", "stage_4", "stage_5", "stage_6", "stage_7", "gate"]
    stopping_reason: str
    artefact_dir: str
    exit_status: Optional[int] = None
    signal: Optional[str] = None            # e.g. "SIGABRT"; never set together with a timeout
    limit_hit: Optional[LimitHit] = None
    oracle_class: Optional[OracleClass] = None      # non-null iff oracle_fired
    assertion_text: Optional[str] = None
    assertion_site: Optional[str] = None    # "<file>:<line>", normalised per 3.7.2
    reduced_text: Optional[str] = None      # conditional, 2.12's cap rule
    reduced_path: Optional[str] = None


@dataclass(kw_only=True)
class FeedbackEntry:
    """One per ProbeResult of the previous iteration. Nested in FeedbackBundle."""
    probe_id: str
    stopped_at_stage: str
    reason: str
    oracle_class: Optional[str] = None
    oracle_summary: Optional[str] = None    # assertion text with its file:line, or the top frames
    reduced_text: Optional[str] = None      # conditional, 2.12's cap rule
    reduced_from_bytes: Optional[int] = None
    reduced_to_bytes: Optional[int] = None


@dataclass(kw_only=True)
class FeedbackBundle:
    """What the seeded arm reads at the start of its next iteration.

    Produced by A5 (feedback.py) from the iteration's ProbeResults. Consumed by
    A3 only: the mutation arm receives one whose entries list is empty and never
    reads it (FR-16.2, 02-HLD.md 2.1).
    """
    contract_version: str = CONTRACT_VERSION
    run_manifest_id: str
    seed_sha: str
    arm: Arm
    iteration: int
    entries: list[FeedbackEntry]
    abandoned: bool
    terminating_condition: Optional[str] = None
    abandon_reason: Optional[str] = None    # conditional on abandoned

    def __post_init__(self) -> None:
        self.entries = [e if isinstance(e, FeedbackEntry) else FeedbackEntry(**e)
                        for e in self.entries]


@dataclass(kw_only=True)
class LedgerEntry:
    """One charge against the budget, or one observation of it.

    Produced by every node in both halves. Consumed by A6b, B11 and B12. Exactly
    one entry per arm per run carries scope="arm_window" and its amount is that
    arm's spend on the primary unit; every other entry is per-stage occupancy
    and is an observation (G-48, 02-HLD.md 2.9).
    """
    contract_version: str = CONTRACT_VERSION
    entry_id: str
    run_manifest_id: str
    arm: LedgerArm
    scope: Scope
    stage: str
    unit: Unit
    amount: float
    metered: bool
    observed: dict                          # keys in 2.7
    timestamp_utc: str
    stop_reason: Optional[str] = None


@dataclass(kw_only=True)
class RunCommit:
    """One run commit. Nested in RunManifest; FR-02.7 defines it per mode."""
    commit: str
    seed_sha: Optional[str] = None          # None in discovery, set per seed in calibration


@dataclass(kw_only=True)
class RunManifest:
    """The identity of one run, stamped on every artefact of both halves.

    Produced by B12 (bug_loop.py). Consumed by everything. FR-17.6 makes it the
    key by which a row is traced to its image, its commit, its budget file and
    its arm.
    """
    contract_version: str = CONTRACT_VERSION
    run_manifest_id: str
    mode: Mode
    seed_set: SeedSet
    run_commit: list[RunCommit]
    pin_sha: str
    pin_tag: str
    tags_sharing_pin: list[str]
    lag_commits: int
    lag_days: float
    current_window_has_release: bool
    corpus_head_sha: str
    image_spec: dict                        # keys in 2.7
    assertion_baseline_count: int
    budget_unit: Unit
    arm_window_seconds: float
    arm_order: list[Arm]
    budget_file_sha: str
    cluster_yaml_sha: str
    deployment: Deployment
    worker_type: str
    apparatus_concurrency: int
    llm_concurrency: int
    artefact_root: str
    backend: str
    model_ids: dict                         # keys in 2.7
    stages_metered: dict                    # keys in 2.7
    mutator_set_sha: str
    x_policy: str
    issue_mirror: dict                      # keys in 2.7
    local_id_range: list[int]
    forum_post_url: str
    forum_post_date: str
    confirmation_cutoff_date: str
    differential_driver: dict               # keys in 2.7
    started_utc: str
    calibration_sample: Optional[list[str]] = None
    sv_seeds_excluded: Optional[list[str]] = None
    ended_utc: Optional[str] = None

    def __post_init__(self) -> None:
        self.run_commit = [c if isinstance(c, RunCommit) else RunCommit(**c)
                           for c in self.run_commit]
```

### 2.5 The interface, and the read-only ledger view

```python
@dataclass(kw_only=True)
class LedgerSnapshot:
    """What a generator may know about its own budget, and nothing else.

    Four fields, unchanged by the 2026-09-14 backend decision: the money cap is
    the driver's business, not a generator's, so spend_usd is deliberately NOT
    exposed here. The generator cannot reach BudgetLedger, cannot read another
    arm's spend, and cannot read any result field (FR-16.4).
    """
    arm: Arm
    unit: Unit
    spent: float
    cap: float


class Generator(Protocol):
    """The driver's call into a generator. A3 and A4 both implement it."""

    def __call__(self, seed: SeedRecord, feedback: FeedbackBundle,
                 remaining: LedgerSnapshot) -> list[ProbeSpec]:
        ...


def generate(seed: SeedRecord, feedback: FeedbackBundle,
             remaining: LedgerSnapshot) -> list[ProbeSpec]:
    """The interface's canonical signature, declared beside the schemas it uses.

    Never called: it exists so that the signature has one written home in the
    package, as G-47 requires, and so that a type checker binds A3 and A4 to it.
    """
    raise NotImplementedError


@dataclass(kw_only=True)
class CounterBlock:
    """FR-17.4's per-stage counters, returned by every node and logged by B12.

    Four counters and one name, fixed here and nowhere else, because a counter
    set that each node chooses for itself cannot be summed across a run. Every
    node of 3.2 returns exactly one of these, under the key "counters" of its
    own return dict, and the driver logs it on the head (13.1).

    It is NOT a contract member: it is not in _MEMBERS, validate() never sees
    it, and adding it moves neither MAJOR nor MINOR under 2.2's rule, which
    speaks of a member gaining or losing a required field. It lives in this
    package rather than in store.py for one reason: both halves produce one,
    and a supply-half module may not import store.py (FR-16.1, 14.5's walk).
    """
    stage: str          # one of _STAGE_IDS, or "image", "corpus", "pin",
                        # "mirror" or "synthesis" for the five shared stages
    started: int        # units of work this node began: probes, seeds, issues
    completed: int      # of those, the ones that returned a record
    failed: int         # of those, the ones that did not; started == completed + failed
    seconds: float      # this node's own wall clock, start to return


_COUNTER_STAGES = _STAGE_IDS + ("image", "corpus", "pin", "mirror", "synthesis")
```

`CounterBlock.stage` is drawn from `_COUNTER_STAGES` and from nothing else: the eight `_STAGE_IDS` of
`00-README.md`, which are the metered ones FR-14.8 declares, plus the five shared stages that are
charged to no arm (`02-HLD.md` §2.9's `shared` scope). `started == completed + failed` is an
invariant the driver checks per block rather than a convention, and a block that violates it is logged
with the violation named, because a node that lost work silently is exactly what FR-17.4 exists to
surface. The counters are **observations**, never a budget: `seconds` here and `LedgerEntry.amount`
are different numbers with different owners, and §14.3's NFR-09 row says which is which.

One signature serves both arms. A4 takes `feedback` and does not read it, and `tests/
test_generate_task.py` asserts the non-read on A4's **body** (its source contains no reference to the
parameter after binding) rather than on its signature.

**That is a change to FR-16.2's acceptance criterion, and the change is made in the FRD, not here**
(K11). FR-16.2's unamended criterion reads "the mutation arm's call signature has no feedback
parameter, asserted by a test", and `00-README.md` is explicit that `02-HLD.md` cannot amend an FRD
criterion: "Where 02 or 03 contradicts 01, 01 wins and the contradiction is a defect in 02 or 03."
So `01-FRD.md` §1.7 carries an erratum at FR-16.2 replacing the criterion with "the mutation arm's
implementation does not read the feedback argument, asserted by a test on its body", with the
reasoning stated there: FR-05.4 requires the contract validator to accept both arms' output through
**the same code path**, and two signatures for one `Generator` protocol is a second code path at the
one place the design exists to keep single. The behaviour FR-16.2 protects, an unadaptive mutation
arm, is protected exactly as well by a body check and is protected against a wider class of defect,
since a second signature would not stop a body from reaching the bundle by another route.

### 2.6 The validator

```python
_MEMBERS = (SeedRecord, BudgetFile, ProbeSpec, ProbeResult, FeedbackBundle,
            LedgerEntry, RunManifest)

_DICT_KEYS = {
    ("ProbeSpec", "turn_cost"): {"turn", "wall_seconds", "tokens_in", "tokens_out",
                                 "cost_usd", "metered"},
    ("ProbeSpec", "differential"): {"stimulus_id", "reset_protocol", "sample_point",
                                    "cycles", "port_list_sha"},
    ("LedgerEntry", "observed"): {"cpu_seconds", "tokens_in", "tokens_out", "cost_usd"},
    ("RunManifest", "image_spec"): {"circt_sha", "sdk_tag", "targets", "flag_string",
                                    "image_digest", "verilator_version", "slang_enabled",
                                    "tool_hashes"},
    ("RunManifest", "issue_mirror"): {"refreshed_utc", "issues_mirrored", "issue_cap",
                                      "cap_bound", "state", "comments_mirrored"},
    ("RunManifest", "differential_driver"): {"source", "commit", "deviation", "obstacle"},
    ("RunManifest", "model_ids"): {"generate_seeded", "triage_report", "repair_adapt",
                                   "mutator_synthesis"},
    ("RunManifest", "stages_metered"): set(_STAGE_IDS),
}


def _unwrap(annotation: Any) -> Any:
    """Strip Optional[...] down to the one non-None member it wraps."""
    if typing.get_origin(annotation) is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return args[0] if len(args) == 1 else annotation
    return annotation


def _check_field(cls_name: str, name: str, value: Any, annotation: Any) -> None:
    """Raise E003 or E004 for one non-None field value.

    Two deliberate deviations from bare isinstance, both measured rather than
    assumed (W24). An int satisfies a float annotation, because every duration
    the loop computes is a whole number of seconds and isinstance(5, float) is
    False. A bool does NOT satisfy an int annotation, because isinstance(True,
    int) is True and a bool where a count belongs is a defect, not a value.
    """
    ann = _unwrap(annotation)
    if typing.get_origin(ann) is Literal:
        if value not in typing.get_args(ann):
            raise ContractError(
                "E004_BAD_ENUM",
                f"{cls_name}.{name} is {value!r}, not one of {typing.get_args(ann)}")
        return
    base = typing.get_origin(ann) or ann
    if base is float and isinstance(value, int) and not isinstance(value, bool):
        return
    if base is int and isinstance(value, bool):
        raise ContractError("E003_WRONG_TYPE",
                            f"{cls_name}.{name} is bool, expected int")
    if isinstance(base, type) and not isinstance(value, base):
        raise ContractError("E003_WRONG_TYPE",
                            f"{cls_name}.{name} is {type(value).__name__}, "
                            f"expected {base.__name__}")


def validate(obj: Any) -> None:
    """Raise ContractError unless *obj* is a valid instance of its member class.

    Checks, in this order: the MAJOR version; every required field non-None;
    every non-None field's type and Literal membership; every declared dict's
    key set; and the per-class conditional rules of 2.8. Returns None on
    success; it never repairs, defaults or coerces anything.
    """
    cls = type(obj)
    if cls not in _MEMBERS:
        raise ContractError("E009_UNKNOWN_SCHEMA", f"{cls.__name__} is not a contract member")
    check_version(obj.contract_version)
    hints = typing.get_type_hints(cls)
    for f in dataclasses.fields(cls):
        value = getattr(obj, f.name)
        optional = f.default is None
        if value is None:
            if not optional:
                raise ContractError("E002_MISSING_FIELD", f"{cls.__name__}.{f.name} is None")
            continue
        _check_field(cls.__name__, f.name, value, hints[f.name])
        want = _DICT_KEYS.get((cls.__name__, f.name))
        if want is not None and set(value) != want:
            raise ContractError(
                "E007_BAD_DICT_KEYS",
                f"{cls.__name__}.{f.name} keys {sorted(set(value))} "
                f"differ from {sorted(want)}")
    _CONDITIONALS[cls](obj)
```

### 2.7 The declared dicts, key by key

Each is a closed set. `validate` compares the key set exactly, so an extra key fails as loudly as a
missing one. No key may be added without a MINOR bump and none removed without a MAJOR one.

| Dict | Key | Type | Meaning |
|---|---|---|---|
| `ProbeSpec.turn_cost` | `turn` | str or null | The turn id on the seeded arm; **null** on the mutation arm, which runs no model. |
| | `wall_seconds` | float | Wall seconds the turn (or the mutator call) took. |
| | `tokens_in`, `tokens_out` | int or null | **Prompt tokens and output tokens.** On the campaign's `vertex` backend they are the turn's summed `usage_metadata.prompt_token_count` and `candidates_token_count` (`chia:chia/models/vertex.py:479-482`), carried home by §3.5's `llm_turn`. Null only on the `claude` fallback, which reports no per-phase usage. |
| | `cost_usd` | float or null | **US dollars, computed by the ledger and never by the backend**, which reports no price: `tokens_in / 1e6 * price_usd_per_m_input_tokens + tokens_out / 1e6 * price_usd_per_m_output_tokens`, from the two committed `budget.yaml` keys of §9.1. Null exactly when the token counts are. |
| | `metered` | bool | False exactly when the three above are null. |
| `ProbeSpec.differential` | `stimulus_id` | str | Names the one shared stimulus definition both harnesses drive (FR-08.3). |
| | `reset_protocol` | str | The one reset protocol, likewise shared. |
| | `sample_point` | str | The one sampling point, likewise shared. |
| | `cycles` | int | How many cycles both harnesses run. |
| | `port_list_sha` | str | SHA-256 of the canonical port list both harnesses were generated from, hex-digested. It is the one key of the five a **generator cannot know**, because the port list exists only once the design has been lowered to HW and A3 and A4 run before any tool does: they emit the empty string, and B4 computes the digest in `extract_port_list` and records it on `DifferentialVerdict.port_list_sha` (§3.6.3). The key stays in this closed set so that the spec's shape does not change between the two moments. |
| `LedgerEntry.observed` | `cpu_seconds` | float or null | Reported, never budgeted (FR-14.5). |
| | `tokens_in`, `tokens_out` | int or null | As `turn_cost`'s, and **populated** on the campaign backend. Reported, never the primary unit (FR-14.5). |
| | `cost_usd` | float or null | As `turn_cost`'s. It is reported and is not the primary unit, **and it is nonetheless a stop condition**: FR-18.10 stops both arms when the campaign's cumulative `cost_usd` reaches `campaign_spend_cap_usd`. A cap is not a budget; §9.1 says which is which. |
| `RunManifest.image_spec` | `circt_sha` | str | The CIRCT commit the image was built at. |
| | `sdk_tag` | str | The `firtool-*` release the SDK came from. |
| | `targets` | list[str] | FR-03.7's target list, a parameter and not a constant. |
| | `flag_string` | str | `-O3 -UNDEBUG -gline-tables-only`. |
| | `image_digest` | str | The published image's digest. |
| | `verilator_version` | str | One version for the whole campaign (FR-03.15). |
| | `slang_enabled` | bool | Branch (a) or branch (b) of ADR-D-13. |
| | `tool_hashes` | dict[str, str] | Tool name to the SHA-256 of that binary in the published image (FR-03.16). |
| `RunManifest.model_ids` | `generate_seeded`, `triage_report`, `repair_adapt`, `mutator_synthesis` | str | One value per model stage (ADR-D-03), spelled **`"<backend>:<model id>"`**, which is the spelling the `Assisted-by:` trailer of §7.4 already uses. ~~Three~~ **All four** read `vertex:gemini-3.8-flash` under the superseding decision and its addendum; ~~`repair_adapt` reads whatever backend CHIA's unmodified chain actually built, which cannot be `vertex` (§3.8)~~ is **corrected 2026-09-14**: the additive branch of §3.8 makes `vertex` a backend the chain builds, so `repair_adapt` reads it too on a default run and reads `"<fallback>:<its model id>"` only under `--repair-backend`. A difference from `RunManifest.backend` is still what makes `stages_metered["stage_7"]` false, and on a default run there is none. Four keys, closed, and in `_DICT_KEYS` since this revision (W8). |
| `RunManifest.stages_metered` | exactly `_STAGE_IDS`: `stage_1` to `stage_7` and `gate` | bool | FR-14.8's metered-or-not declaration. The key set is `00-README.md`'s own stage list, which no document in the set may rename, so it is a constant rather than a parameter; in `_DICT_KEYS` since this revision (W8). |
| `RunManifest.issue_mirror` | `refreshed_utc`, `issues_mirrored`, `issue_cap`, `cap_bound`, `state`, `comments_mirrored` | str, int, int, bool, str, bool | FR-10.9's six recorded values. `comments_mirrored` is always `false`. |
| `RunManifest.differential_driver` | `source`, `commit`, `deviation`, `obstacle` | str, str, str or null, str or null | FR-08.11: either the reused `circt/arc-tests` driver and its commit, or a named deviation with its obstacle. |

### 2.8 The conditional rules, enforced rather than described

```python
def _require(cond: bool, code: str, message: str) -> None:
    if not cond:
        raise ContractError(code, message)


def _probe_spec_conditionals(o: ProbeSpec) -> None:
    mutation = o.arm == "mutation"
    for name in ("mutator_id", "mutator_seed_int", "source_test_path"):
        value = getattr(o, name)
        if mutation:
            _require(value is not None, "E005_CONDITIONAL_REQUIRED",
                     f"ProbeSpec.{name} is required when arm is 'mutation'")
        else:
            _require(value is None, "E006_CONDITIONAL_FORBIDDEN",
                     f"ProbeSpec.{name} must be None when arm is 'seeded'")
    _require(o.turn_cost["metered"] is (o.turn_cost["tokens_in"] is not None),
             "E005_CONDITIONAL_REQUIRED",
             "ProbeSpec.turn_cost.metered must agree with tokens_in")
    if mutation:
        _require(o.turn_cost["turn"] is None, "E006_CONDITIONAL_FORBIDDEN",
                 "ProbeSpec.turn_cost.turn must be None on the mutation arm")
    _require(o.input_text is not None or bool(o.input_path),
             "E002_MISSING_FIELD",
             "ProbeSpec carries its input inline or by path (FR-04.3, as amended)")


def _probe_result_conditionals(o: ProbeResult) -> None:
    _require((o.oracle_class is not None) == o.oracle_fired,
             "E005_CONDITIONAL_REQUIRED",
             "ProbeResult.oracle_class is non-null exactly when oracle_fired")
    if o.build_status == "timeout":
        _require(o.signal is None, "E006_CONDITIONAL_FORBIDDEN",
                 "a timeout carries a null signal (FR-06.4)")
    if o.reduced_text is not None:
        _require(o.reduced_path is not None, "E005_CONDITIONAL_REQUIRED",
                 "ProbeResult.reduced_text requires reduced_path")
    for name in ("assertion_text", "assertion_site"):
        _require((getattr(o, name) is not None) == (o.oracle_class == "assertion"),
                 "E005_CONDITIONAL_REQUIRED",
                 f"ProbeResult.{name} is non-null exactly on oracle_class 'assertion'")


def _feedback_conditionals(o: FeedbackBundle) -> None:
    _require((o.abandon_reason is not None) == o.abandoned,
             "E005_CONDITIONAL_REQUIRED",
             "FeedbackBundle.abandon_reason is non-null exactly when abandoned")


def _ledger_conditionals(o: LedgerEntry) -> None:
    _require(o.amount >= 0.0, "E003_WRONG_TYPE", "LedgerEntry.amount must not be negative")


def _manifest_conditionals(o: RunManifest) -> None:
    if o.mode == "discovery":
        _require(len(o.run_commit) == 1 and o.run_commit[0].seed_sha is None,
                 "E005_CONDITIONAL_REQUIRED",
                 "a discovery manifest carries exactly one run_commit with a null seed_sha")
    else:
        _require(o.run_commit and all(c.seed_sha is not None for c in o.run_commit),
                 "E005_CONDITIONAL_REQUIRED",
                 "a calibration manifest carries one run_commit per sampled seed")
        _require(o.calibration_sample is not None
                 and len(o.run_commit) == len(o.calibration_sample)
                 and {c.seed_sha for c in o.run_commit} == set(o.calibration_sample),
                 "E005_CONDITIONAL_REQUIRED",
                 "a calibration manifest's run_commit entries are exactly its sample")
    _require(set(o.arm_order) == {"seeded", "mutation"} and len(o.arm_order) == 2,
             "E004_BAD_ENUM", "RunManifest.arm_order names both arms exactly once")
    _require(len(o.local_id_range) == 2 and o.local_id_range[0] < o.local_id_range[1],
             "E003_WRONG_TYPE", "RunManifest.local_id_range is an ordered pair")


_CONDITIONALS = {
    SeedRecord: lambda o: _require(
        len(o.argv_template) == len(o.run_lines) == len(o.polarity) == len(o.shape),
        "E005_CONDITIONAL_REQUIRED",
        "SeedRecord's four per-run-line lists must be the same length"),
    BudgetFile: lambda o: _require(
        o.arm_window_seconds > 0, "E003_WRONG_TYPE",
        "BudgetFile.arm_window_seconds must be positive"),
    ProbeSpec: _probe_spec_conditionals,
    ProbeResult: _probe_result_conditionals,
    FeedbackBundle: _feedback_conditionals,
    LedgerEntry: _ledger_conditionals,
    RunManifest: _manifest_conditionals,
}
```

The cap rule of §2.12 of `02-HLD.md` is enforced by the producer rather than by `validate`, because
`validate` does not know the cap: the cap is a `budget.yaml` key and the package imports nothing.
Each producer calls `contract.bound_text(text, path, cap)`, which returns the text when
`len(text.encode("utf-8")) <= cap` and `None` otherwise, and which raises `E008_CAP_EXCEEDED` when
`path` is `None` and the text is over the cap, because that is the one combination that would lose
the artefact.

```python
def bound_text(text: Optional[str], path: Optional[str], cap: int) -> Optional[str]:
    """Return *text* if it fits under *cap* bytes, else None (the path carries it).

    Raises E008 when the text is over the cap and no path exists, which is the
    one combination that would silently lose an artefact (FR-17.7).
    """
    if text is None:
        return None
    if len(text.encode("utf-8")) <= cap:
        return text
    if path is None:
        raise ContractError("E008_CAP_EXCEEDED",
                            f"text of {len(text.encode('utf-8'))} bytes exceeds "
                            f"the {cap}-byte cap and has no companion path")
    return None
```
### 2.9 The apparatus-internal records, in `store.py`

Fourteen of FRD §2.5's twenty-one objects cross nothing. They live beside the DDL that persists them,
in `store.py`, because a row dataclass and its `CREATE TABLE` drift apart the moment they live in
different files. They are plain `@dataclass(kw_only=True)`; they carry no `contract_version`, they are
never serialised by `contract.to_json`, and no supply-half module imports them, which is FR-16.1's
import check.

```python
"""loop.db: the LoopStore, its DDL, and every apparatus-internal record.

Nothing here crosses the seam. contract/schema.py is imported for the seven
members that do; the reverse import does not exist and tests/test_layout.py
asserts it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass(kw_only=True)
class SdkMap:
    """Exact-pin seeds grouped by the firtool-* tag their pin matches (FR-01.5)."""
    corpus_head_sha: str
    groups: dict                      # tag -> list[seed_sha]; 38 groups, median 3, max 27


@dataclass(kw_only=True)
class ImageSpec:
    """What B1 built, and the hashes that prove a probe ran it (FR-03.10, FR-03.16)."""
    circt_sha: str
    sdk_tag: str
    targets: list[str]
    flag_string: str
    cmake_args: list[str]             # the full configure line of 4.10, for the record
    image_digest: str
    image_tag: str
    verilator_version: str
    slang_enabled: bool
    lit_discovery_ok: bool            # FR-03.17
    lit_discovered_count: int         # FR-03.17
    assertion_nonreferencing: list[str]   # FR-03.5's named objects, compared as a set
    tool_hashes: dict                 # tool name -> SHA-256 hex of the published binary


@dataclass(kw_only=True)
class BuildResult:
    """One probe execution (FR-06.4, FR-06.5, FR-06.9). Produced by B2."""
    probe_id: str
    run_manifest_id: str
    run_commit: str
    image_digest: str
    status: Literal["clean_exit", "parse_error", "assertion", "fatal_error",
                    "crash", "timeout", "oom"]
    binary_path: str                  # always under /workspace/circt/build/bin
    binary_sha256: str                # checked against ImageSpec.tool_hashes before the run
    argv: list[str]                   # the full argv, prlimit prefix included
    exit_status: Optional[int]        # null when the child died by signal or was killed
    signal: Optional[str]             # "SIG..." from the child's negative return code
    limit_hit: Optional[Literal["wall", "cpu", "address_space"]]
    cpu_seconds: float                # the child's own rusage, ru_utime + ru_stime (K8)
    wall_seconds: float               # non-deterministic, declared as such (NFR-02)
    peak_rss_bytes: Optional[int]     # non-deterministic, observational only
    worker_hostname: str              # socket.gethostname() in the executing worker (K12)
    worker_node_id: str               # ray.get_runtime_context().get_node_id()
    child_pid: int                    # the probe child's pid, for FR-13.2's pair
    stdout_path: str
    stderr_path: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool                   # either stream hit the byte cap of FR-06.4


@dataclass(kw_only=True)
class Frame:
    """One stack frame of LLVM's crash trace, resolved (FR-07.4). In OracleVerdict.

    LLVM prints two shapes and 3.6.2 parses both. A `dladdr` frame ends
    "(<module>+0x<offset>)" and carries module and offset, which is what the
    symboliser needs; a print-time-symbolised frame ends "<file>:<line>:<col>"
    and carries no module, because LLVM already resolved it. `shape` records
    which, so no reader has to infer it from an empty field.
    """
    index: int
    address: str                      # "0x..." as printed by LLVM's own trace
    shape: Literal["module_offset", "attributed"]
    module: str                       # the object file; "" on an attributed frame
    offset: str                       # "0x..." within the module; "" on an attributed frame
    function: str                     # demangled and normalised; "" when unresolved
    file: str                         # "" when unresolved
    line: int                         # 0 when unresolved
    in_circt_object: bool             # 3.6.2's predicate; what FR-07.4 and FR-07.5 read


@dataclass(kw_only=True)
class OracleVerdict:
    """The primary oracle's answer for one probe (F-07). Produced by B3."""
    probe_id: str
    fired: bool
    oracle_class: Optional[Literal["assertion", "fatal_error", "crash"]]
    assertion_text: Optional[str]     # verbatim from stderr (FR-07.3)
    assertion_site: Optional[str]     # "<file>:<line>" verbatim from stderr
    fatal_message: Optional[str]      # the text after "LLVM ERROR:"
    frames: list[Frame]               # every frame, in trace order, prologue included
    prologue_dropped: int             # how many leading frames 3.7.1's strip removed
    frames_resolved: int              # frames with a non-empty function name
    frames_with_location: int         # frames with line > 0 AND in_circt_object (3.6.2)
    fingerprint_frame: Optional[str]  # "<function> <basename(file)>", the first stripped
                                      # frame in a CIRCT object with a resolved line
    out_of_scope_root: bool           # the first STRIPPED frame is not in a CIRCT object (FR-07.5)
    repro_command: str                # one line, runnable inside the image (FR-07.6)
    flag_string: str                  # carries the literal -UNDEBUG (FR-07.7)
    tool_version_output: str          # the tool's own --version, which still says "Optimized build."


@dataclass(kw_only=True)
class DifferentialVerdict:
    """arcilator against Verilator for one probe (F-08). Produced by B4."""
    probe_id: str
    verdict: Literal["agree", "diverge", "diverge_x_policy", "not_applicable",
                     "harness_failure"]
    reason: str                       # why not_applicable, or which arm failed
    verilator_version: str            # mandatory on every verdict (FR-03.15)
    x_policy: str
    stimulus_id: str
    port_list_sha: str                # 3.6.3: computed by B4, not by the generator
    cycles: int
    first_divergent_signal: Optional[str]
    first_divergent_cycle: Optional[int]
    arcilator_value: Optional[str]
    verilator_value: Optional[str]
    arcilator_trace_path: Optional[str]
    verilator_trace_path: Optional[str]
    driver_source: str                # "circt/arc-tests" or the recorded deviation (FR-08.11)


@dataclass(kw_only=True)
class ReducedCase:
    """The output of stage 5 (F-09). Produced by B5."""
    probe_id: str
    reducer: Literal["circt-reduce", "textual-ddmin", "none"]
    reduced: bool
    fixpoint: bool
    budget_truncated: bool            # NFR-02's visibility flag
    reason: Optional[str]             # why reduced is False (FR-09.12)
    lift: Optional[Literal["firtool --ir-fir", "firtool --parse-only",
                           "circt-verilog --ir-moore"]]
    path: str                         # the reduced input on disk
    size_before_bytes: int
    size_after_bytes: int
    size_before_ops: int
    size_after_ops: int
    wall_seconds: float
    interestingness_calls: int
    recheck_class: Optional[str]      # the re-run verdict's class (FR-09.3)
    recheck_assertion_text: Optional[str]
    recheck_assertion_site: Optional[str]
    recheck_matches: bool             # False sets reduction_changed_failure (FR-09.7)


@dataclass(kw_only=True)
class Fingerprint:
    """G-43's primary fingerprint plus its three evidence fields (FR-10.1)."""
    probe_id: str
    basis: Literal["assertion", "frames", "insufficient"]
    value: Optional[str]              # the fingerprint; null iff basis is insufficient
    frame_tuple: list[str]            # evidence, recorded even when the basis is assertion
    structural_hash: str              # evidence; never merges two candidates
    fingerprint_stable: Optional[bool]   # set by the gate's re-run (3.9 question 1); None
                                         # until it has run. False is REPORTED, never merged.


@dataclass(kw_only=True)
class DedupVerdict:
    """Whether a candidate is new, and the evidence for whatever it is (F-10)."""
    probe_id: str
    verdict: Literal["new", "duplicate_of_candidate", "known_open_issue",
                     "known_closed_issue", "fixed_post_pin", "dedup_unavailable"]
    evidence: dict                    # keys: matched_key, matched_token, issue_number,
                                      # issue_url, issue_state, issue_labels,
                                      # fixing_commit, duplicate_of_candidate_id


_DEDUP_EVIDENCE_KEYS = {"matched_key", "matched_token", "issue_number", "issue_url",
                        "issue_state", "issue_labels", "fixing_commit",
                        "duplicate_of_candidate_id"}
_DEDUP_EVIDENCE_REQUIRED = {
    "duplicate_of_candidate": ("matched_key", "duplicate_of_candidate_id"),
    "known_open_issue": ("matched_token", "issue_number", "issue_url", "issue_state",
                         "issue_labels"),
    "known_closed_issue": ("matched_token", "issue_number", "issue_url", "issue_state",
                           "issue_labels"),
    "fixed_post_pin": ("fixing_commit",),
    "dedup_unavailable": ("matched_key",),
    "new": (),
}


@dataclass(kw_only=True)
class Report:
    """The issue-shaped artefact a maintainer would read (G-25, FR-11.3)."""
    candidate_id: str
    path: str                         # <probe dir>/report.md
    template: Literal["primary", "differential"]
    title: str
    classification: Literal["bug", "invalid_input", "known_issue", "untriaged"]
    classification_reason: str        # at most 4 sentences [DEFAULT], 3.8.3
    rendered_sha256: str
    assisted_by: str                  # "<tool>:<model>" (FR-11.6, FR-20.3)
    fields_present: list[str]         # every FR-11.3 field the render substituted


@dataclass(kw_only=True)
class RepairResult:
    """CHIA's own chain result, unchanged in shape (FR-12.7). Produced by B8."""
    candidate_id: str
    local_id: int                     # the synthetic identifier of FR-12.2
    status: Literal["fixed", "attempted", "no_repro", "unclear", "not_a_bug", "error"]
    failing_phase: Optional[str]
    reproduced: Optional[bool]
    build_ok: Optional[bool]
    fixed: Optional[bool]
    lit_ok: Optional[bool]
    lit_unusable: bool                # FR-12.8's erratum: zero discovered is not red
    lit_passed: Optional[int]
    lit_failed: Optional[int]
    lit_failures: list[str]
    diff_path: Optional[str]
    diff_added: Optional[int]
    diff_removed: Optional[int]
    chia_artifact_dir: Optional[str]  # CHIA's own issue_logs/issue_<local_id>/
    repro_dir: str                    # 3.8's path, OUTSIDE /workspace/circt (K9)
    repro_overwritten: bool           # the reproduce turn replaced the pre-written script
    restore_ok: bool                  # FR-12.11's reset, rebuild AND re-hash
    restore_hashes_match: bool        # every tool binary re-hashed against ImageSpec (FR-12.11)
    restore_log: str
    backend: str                      # cfg["backend"], "vertex" by default (3.8, 13.1)
    token_capture: str                # why this stage's tokens are or are not observed
    # token_capture is "unavailable_remote_dispatch" on every backend CHIA's
    # chain implements, including vertex: _turn dispatches the turn with
    # chia_remote, so the LLM copy that accumulates _last_metadata dies on the
    # worker and QueryResult carries no usage (3.8, FR-14.6). It is a field of
    # RepairResult and NOT of LedgerEntry.observed, whose four declared keys are
    # frozen by 2.2's rule: adding one would be a MAJOR bump to 3.0.


@dataclass(kw_only=True)
class GateDecision:
    """The four answers and the verdict (F-13). Produced by B9a."""
    candidate_id: str
    q1_reproduce: Optional[bool]
    q1_original_worker: Optional[str]
    q1_rerun_worker: Optional[str]
    q1_original_pid: Optional[int]
    q1_rerun_pid: Optional[int]
    q1_same_worker: Optional[bool]
    q2_minimal: Optional[bool]
    q2_reason: Optional[str]
    q3_valid: Optional[bool]
    q3_validity_basis: Optional[Literal["parsed", "checker_failed"]]
    q3_after_parse: Optional[bool]    # FR-13.15's second conjunct (3.9 question 3)
    q3_exit_status: Optional[int]
    q3_stderr_path: Optional[str]
    q4_new: Optional[bool]
    q4_reason: Optional[str]
    stopped_at_question: Optional[int]
    decision: Literal["report", "report_plus_patch", "nothing"]
    taxonomy_bucket: Optional[Literal["unreproducible", "not_minimal", "invalid_input",
                                      "duplicate", "undecided", "new_bug"]]
    held_reason: Optional[str]


@dataclass(kw_only=True)
class FilingRecord:
    """One human approval, and the filing it authorised (F-13, F-20)."""
    candidate_id: str
    approver: str
    approved_at_utc: str
    decision: Literal["report", "report_plus_patch"]
    licence_confirmed: Optional[bool]     # FR-20.5; None when no patch was offered
    licence_confirmed_at_utc: Optional[str]
    url_source: Optional[Literal["poll", "pasted"]]
    issue_number: Optional[int]
    issue_url: Optional[str]
    prefill_url_length: Optional[int]
    prefill_fallback_reason: Optional[str]
    confirmed: bool                       # G-27: a maintainer acted, evidenced by a URL
    confirmed_at_utc: Optional[str]
    confirmation_url: Optional[str]


@dataclass(kw_only=True)
class BudgetLedger:
    """The aggregate over ledger_entry, as A6b maintains it (F-14)."""
    run_manifest_id: str
    per_arm_window: dict              # arm -> seconds spent on the primary unit
    per_arm_stage: dict               # arm -> {stage -> seconds occupancy}
    shared_stage: dict                # stage -> seconds occupancy, charged to no arm
    inputs_today: dict                # arm -> count, against the per-day safety cap
    filings_today: int
    filings_total: int
    spend_usd: float                  # campaign-wide, both arms and shared; 3.11
    per_arm_spend_usd: dict           # arm -> USD, reported beside the window
    stop_reason: dict                 # arm -> the cap or window that stopped it, or None


@dataclass(kw_only=True)
class CandidateRecord:
    """One probing input for which an oracle fired (G-23), and every downstream
    verdict about it. 02-HLD.md 5.3 is its field list; this is that list typed.

    Apparatus-internal: it crosses nothing, and ProbeResult carries what the
    generator is allowed to see.
    """
    candidate_id: str
    probe_id: str
    run_manifest_id: str
    arm: Literal["seeded", "mutation"]
    run_commit: str
    image_digest: str
    oracle_class: Literal["assertion", "fatal_error", "crash", "differential"]
    frame_tuple: list[str]
    frames_resolved: int
    frames_with_location: int
    out_of_scope_root: bool
    contaminated_symbol: bool
    contaminated_file: bool
    contamination_lower_bound: Literal["seed_commit", "run_commit"]
    triage_class: Literal["bug", "invalid_input", "known_issue", "untriaged"]
    artefact_dir: str
    assertion_text: Optional[str] = None
    assertion_site: Optional[str] = None
    repro_command: Optional[str] = None
    reducer: Optional[str] = None
    reduced: Optional[bool] = None
    fixpoint: Optional[bool] = None
    budget_truncated: Optional[bool] = None
    reduced_path: Optional[str] = None
    size_before_bytes: Optional[int] = None
    size_after_bytes: Optional[int] = None
    size_before_ops: Optional[int] = None
    size_after_ops: Optional[int] = None
    fingerprint: Optional[str] = None
    fingerprint_stable: Optional[bool] = None
    structural_hash: Optional[str] = None
    dedup_basis: Optional[Literal["assertion", "frames", "insufficient"]] = None
    dedup_verdict: Optional[str] = None
    dedup_evidence: Optional[dict] = None
    gate_answers: Optional[dict] = None
    gate_decision: Optional[str] = None
    taxonomy_bucket: Optional[str] = None
    held_reason: Optional[str] = None
```

**`store.validate_candidate`, in full.** It is the one enforcement point for every rule a
`CandidateRecord` has, it is called by B6b, B7, B9a and B11 before each writes or reads a candidate,
and it raises `contract.ContractError` rather than an exception of its own so a caller catches one
class across both validators (§2.1).

```python
def validate_candidate(candidate: CandidateRecord) -> None:
    """Raise ContractError unless *candidate* satisfies every rule of its class.

    Checks, in this order: the class partition below; the fingerprint rule; the
    assertion-field rule; and the dedup-evidence key set and its per-verdict
    required keys. Returns None on success. It repairs, defaults and coerces
    nothing, and it never reads the database: the caller assembles the object
    with load_candidate() first.

    Called by dedup_and_screen before the candidate row is written, by
    triage_report before the report renders, by gate_decide before question 1,
    and by render_results over every row it counts, so a malformed candidate is
    refused at whichever of the four it reaches first (FR-10.5, FR-10.8,
    FR-13.14).

    Returns:
        None.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ContractError with one of the seven codes in the table below.
    """
```

**The per-class conditionals, as a table rather than as prose.** "Reduction fields" is the eleven
`reducer` through `reduced_path` plus the four size fields; "dedup fields" is `fingerprint`,
`fingerprint_stable`, `structural_hash`, `dedup_basis`, `dedup_verdict` and `dedup_evidence`; "gate
fields" is `gate_answers`, `gate_decision` and `taxonomy_bucket`. The column headed **at the gate**
is the state a candidate must be in by the time `gate_decide` is called on it, which is the only
point at which every stage has run.

| Field group | `oracle_class == "differential"` | Any other class, at the gate | Code on a violation |
|---|---|---|---|
| reduction fields (`reducer`, `reduced`, `fixpoint`, `budget_truncated`, `reduced_path`, the four sizes) | every one `None` (FR-09.8: stage 5 is never dispatched) | every one non-`None` (stage 5 always runs, and `reduced=False` with a `reason` is a result, not an absence) | `E006` on a populated one; `E005` on a `None` one |
| dedup fields (`fingerprint`, `fingerprint_stable`, `structural_hash`, `dedup_basis`, `dedup_verdict`, `dedup_evidence`) | every one `None` (F-10 is never entered) | `structural_hash`, `dedup_basis`, `dedup_verdict` and `dedup_evidence` non-`None`; `fingerprint` by the row below; `fingerprint_stable` non-`None` only after question 1 has run | `E006` / `E005` as above |
| gate fields (`gate_answers`, `gate_decision`, `taxonomy_bucket`) | every one `None` (FR-13.14: the gate is never reached) | `None` before `gate_decide`, non-`None` after; `validate_candidate` accepts both, because it is called on both sides of that call | `E006` on a populated one for a `differential` candidate; never `E005` |
| `assertion_text`, `assertion_site` | both `None` | both non-`None` exactly when `oracle_class == "assertion"`, both `None` otherwise | `E005` / `E006` |
| `fingerprint` | `None` | `None` exactly when `dedup_basis == "insufficient"`, non-`None` otherwise (FR-10.8) | `E012` |
| `dedup_evidence` | `None` | key set exactly `_DEDUP_EVIDENCE_KEYS`; every key `_DEDUP_EVIDENCE_REQUIRED[dedup_verdict]` names non-`None` | `E011` / `E013` |
| `contaminated_symbol`, `contaminated_file`, `contamination_lower_bound`, `out_of_scope_root`, `frame_tuple`, `frames_resolved`, `frames_with_location` | non-`None` in **both** columns | non-`None` | `E005` |

The last row is the one worth stating rather than leaving to the reader: the contamination and frame
fields are required of a `differential` candidate too, because FR-15.1's screen runs on every
candidate and `results.py` prints the contamination column over all of them. A `differential`
candidate's `frame_tuple` is the empty list, which is a value and not a `None`.

**The error vocabulary**, extending §2.1's `E001` to `E010` and overlapping it nowhere:

| Code | Raised when |
|---|---|
| `E005_CONDITIONAL_REQUIRED` | reused verbatim from §2.1: a field the table above requires is `None`. The message names `CandidateRecord.<field>` and the class that required it. |
| `E006_CONDITIONAL_FORBIDDEN` | reused verbatim: a field the table above forbids holds a value. The message names the field and the class that forbade it. |
| `E011_BAD_EVIDENCE_KEYS` | `dedup_evidence`'s key set differs from `_DEDUP_EVIDENCE_KEYS`. The message lists the symmetric difference, so a missing key and an extra one are distinguishable in the log. This is the `_DICT_KEYS` check `contract.validate` cannot make, because `DedupVerdict` is a `store.py` record and never crosses the seam (W22). |
| `E012_FINGERPRINT_BASIS` | `(candidate.fingerprint is None) != (candidate.dedup_basis == "insufficient")`. It is the row-level twin of the `CHECK ((value IS NULL) = (basis = 'insufficient'))` §6.2 puts on the `fingerprint` table (NIT 4), so the rule is enforced once in Python and once in SQL and a caller that bypasses either still meets the other. |
| `E013_MISSING_EVIDENCE` | a key `_DEDUP_EVIDENCE_REQUIRED[candidate.dedup_verdict]` names is present in the dict and is `None`. The message names the verdict and every missing key. That is FR-10.5's "no verdict other than `new` is recorded without a populated evidence field", and it has an enforcement point for the first time. |
| `E003_WRONG_TYPE` | reused verbatim: a field's runtime type does not match its annotation. `validate_candidate` runs `contract._check_field` over every field of the dataclass before any rule above, so the two validators disagree about no type. |
| `E004_BAD_ENUM` | reused verbatim: `oracle_class`, `arm`, `triage_class`, `contamination_lower_bound` or `dedup_basis` outside its `Literal`. |

`validate_candidate` is **idempotent and side-effect free**: it is a pure predicate over one object, so
calling it four times on one candidate is the same as calling it once, which is what lets all four
callers call it without coordinating. It has **no timeout of its own**, because it runs no process and
opens no connection: it is bounded by the timeout of whichever node called it, which §3.2 gives per
node. It is not a `@ChiaFunction` and is never dispatched; `load_candidate` is the one that touches the
database, and it is a `LoopStore` query like any other.

**The signatures of `store.py`'s four module-level functions**, which W4 found named and unsigned:

```python
def init_schema(node: SQLiteNode) -> None: ...
def artefact_write(artefact_dir: str, relative_path: str, data: str | bytes,
                   *, mode: int = 0o644) -> str: ...
def validate_candidate(candidate: CandidateRecord) -> None: ...
def load_candidate(store: "LoopStore", candidate_id: str) -> CandidateRecord: ...
```

`load_candidate` is the reassembly NIT 3 asks for: `candidate` persists 20 of `CandidateRecord`'s 41
fields and the rest live in `oracle_verdict`, `reduced_case`, `fingerprint`, `dedup_verdict` and
`gate_decision`, so `validate_candidate` needs one function that joins them back into the object it
validates. It is the only reader of those five tables that returns a `CandidateRecord`, and
`tests/test_store.py` round-trips one candidate of every oracle class through it.

**`LoopStore`'s own members**, likewise unsigned before (W4). They are thin: each is one
`self.node.<member>.chia_remote(...)` collected with `get`, and there is no ORM.

```python
class LoopStore:
    def __init__(self, db_path: str) -> None: ...
    def insert(self, table: str, row: dict) -> None: ...
    def insert_many(self, table: str, rows: list[dict]) -> None: ...
    def update(self, table: str, key: dict, fields: dict) -> None: ...
    def query(self, sql: str, params: tuple = ()) -> list[dict]: ...
    def query_one(self, sql: str, params: tuple = ()) -> dict | None: ...
    def transaction(self, ops: list[tuple[str, tuple]]) -> None: ...
```

`insert` is what writes a `probe` row, which W4 found had no specified path into the database:
`store.insert("probe", {...})`, one dict per column, with the canonical-JSON text already rendered
for the `_json` columns. `transaction` is §6.4's batching member and takes the `(sql, params)` pairs
`SQLiteNode.transaction` takes.

**The object-to-dataclass map**, so that FRD §2.5's twenty-one are visibly complete:

| FRD §2.5 object | Dataclass | Module |
|---|---|---|
| `SeedRecord` | `SeedRecord` | `contract/schema.py` |
| `SdkMap` | `SdkMap` | `store.py` |
| `ImageSpec` | `ImageSpec` | `store.py` |
| `RunManifest` | `RunManifest` | `contract/schema.py` |
| `ProbeSpec` | `ProbeSpec` | `contract/schema.py` |
| `BuildResult` | `BuildResult` | `store.py` |
| `OracleVerdict` | `OracleVerdict` (with nested `Frame`) | `store.py` |
| `DifferentialVerdict` | `DifferentialVerdict` | `store.py` |
| `ReducedCase` | `ReducedCase` | `store.py` |
| `Fingerprint` | `Fingerprint` | `store.py` |
| `DedupVerdict` | `DedupVerdict` | `store.py` |
| `CandidateRecord` | `CandidateRecord` | `store.py` |
| `ProbeResult` | `ProbeResult` | `contract/schema.py` |
| `Report` | `Report` | `store.py` |
| `RepairResult` | `RepairResult` | `store.py` |
| `GateDecision` | `GateDecision` | `store.py` |
| `FilingRecord` | `FilingRecord` | `store.py` |
| `BudgetFile` | `BudgetFile` | `contract/schema.py` |
| `BudgetLedger` | `BudgetLedger` | `store.py` |
| `LedgerEntry` | `LedgerEntry` | `contract/schema.py` |
| `FeedbackBundle` | `FeedbackBundle` (with nested `FeedbackEntry`) | `contract/schema.py` |

Four further dataclasses exist that FRD §2.5 does not name because they are parts rather than
objects: `LedgerSnapshot`, `RunCommit` and `CounterBlock` in the contract package, and `Frame` in
`store.py`. `CounterBlock` is new in this revision and is FR-17.4's counters (§2.5); it is in the
contract package rather than here because both halves produce one and a supply-half module may not
import `store.py`.
---

## 3. Modules, classes and functions

### 3.0 What a `@ChiaFunction` may be given, and what every node here is given

`ChiaFunction.__init__` takes `**kwargs` and forwards every one that is not `None` to
`ray.remote().options()`; its own docstring names `resources`, `num_cpus`, `num_gpus`,
`num_returns`, `max_retries`, `retry_exceptions`, `memory`, `scheduling_strategy`, `max_calls`,
`runtime_env`, `name`, `namespace` and `lifetime` (`chia:chia/base/ChiaFunction.py:97-106`). A
decorator-level option is overridden per call by `.options(**override)`, which returns a handle whose
`.chia_remote()` merges the override on top (`chia:chia/base/ChiaFunction.py:228-232`: `def options`
is at 228 and the merge at 232; the range ended one line early). Results are collected with `get`
(`chia:chia/base/ChiaFunction.py:646`).

**Two of the three citations the review called off by one are correct and stay as they are**, checked
line by line on 2026-09-14 with `awk 'NR>=33 && NR<=46'` over `chia/database/sqlite_node.py`: the
data-guidance paragraph, "Store large artifacts as files and put *paths* in the DB", is lines
**35-38**, and the write-semantics paragraph, "write members are declared with `max_retries=0`", is
lines **40-43**. Only the `ChiaFunction.py` range above needed changing (NIT 10).

Three placements exist and no more (`02-HLD.md` §3).

- **`resources={"circt": 1}`**, CHIA's own tag for a node that touches the CIRCT tree or its binaries
  (`chia:chia/chipyard/circt.py:616`, `661`, `698`; `chia:examples/circt_issue_solver/issue_task.py:38`).
- **`resources={"repair": 1}`**, new, held by exactly one node, B8, for the reason `02-HLD.md` §3
  gives: the chain rebuilds with the agent's diff applied and returns without restoring.
- **head**, which is `@ChiaFunction(max_retries=0)` with no resource tag, dispatched by the driver as
  `.options(scheduling_strategy=NodeAffinitySchedulingStrategy(node_id=_head_node_id(), soft=False))`.
  That is CHIA's own mechanism for pinning to the driver's node
  (`chia:chia/base/cache.py:355-357`; `chia:chia/base/bypass.py:226-229`), and it keeps the node a
  node, satisfying FR-19.1, while landing it where the database, the artefact tree, the clone and the
  token are.

`_head_node_id` is used throughout and is defined once, in `bug_loop.py`, beside the `ray.init()`
that makes it meaningful (W4):

```python
def _head_node_id() -> str:
    """Return the Ray node id of the process calling this, which is the head.

    Called only from the driver and from head nodes, after ray.init(), so the
    current node IS the head. It is the value NodeAffinitySchedulingStrategy
    takes, and the value a ChiaTool's task_options takes to place its server on
    the head (3.5's SourceReadTool).

    Returns:
        the node id as a hex string.
    Worker:
        the caller's; it reads the runtime context and dispatches nothing.
    Raises:
        RuntimeError from Ray if called before ray.init().
    """
    return ray.get_runtime_context().get_node_id()


def _head_options() -> dict:
    """Return the scheduling_strategy dict that pins a task to the head."""
    return {"scheduling_strategy":
            NodeAffinitySchedulingStrategy(node_id=_head_node_id(), soft=False)}
```

`{"llm": 1.0}` is not a node placement: it is applied at the **call site** of a model turn, as CHIA
does it, by `llm.prompt.options(resources={"llm": 1.0}).chia_remote(llm, prompt, tools)`
(`chia:examples/circt_issue_solver/issue_task.py:124`). The decorator on `prompt` itself declares
`resources={"claude_creds": 0.01}` (`chia:chia/models/claude.py:449`), and the call-site override is
what makes the cluster's `llm` slots the concurrency cap.

Every node below carries `max_retries=0`. The three exceptions Ray's own retry would create are the
ones `SQLiteNode` sets the same flag against: a committed but unreturned write, a double ledger
charge, and a mutated CIRCT tree (`chia:chia/database/sqlite_node.py:40-43`,
`chia:chia/database/sqlite_node.py:272`, and the same on every write member). Scheduling stalls are
handled instead by `chia_wait(..., pending_timeout=..., retry=True)`, which re-dispatches a task that
never started and never one that ran (`chia:chia/base/chia_wait.py:48-88`).

### 3.1 Docstring obligations (FR-19.4)

Every added node, tool method and prompt carries a docstring whose first line is one sentence in the
imperative, followed by three named paragraphs in this order and no others.

1. **Returns:** the exact shape, naming the dataclass or the dict keys.
2. **Worker:** the resource the node needs, spelled as the dict it declares.
3. **Raises:** every exception the body can raise, and nothing it cannot.

A `ChiaTool` method's docstring is additionally the text the model reads
(`chia:docs/concepts/overview.rst:49-50`), so it is written for a model: it states the one thing the
tool does, the one argument it takes, and the one failure it can return. `tests/` runs a docstring
check over every public callable in `examples/circt_bug_loop/` and over the three functions added to
`chia/chipyard/circt.py`; a missing paragraph fails it.

### 3.2 The component-to-module map, with resources, timeouts and idempotency keys

Timeouts are `02-HLD.md` §3's values and its three enforcement mechanisms; the idempotency key is the
tuple under which a re-run is a no-op or a safe repeat.

| Id | Module and callable | Decorator | Timeout, enforced by | Idempotency key |
|---|---|---|---|---|
| A1 | `corpus.py:build_corpus` | `@ChiaFunction(max_retries=0)`, **head** | 1800 s `[DEFAULT]`, `subprocess` | `(clone_path, corpus_head_sha, since)`; byte-identical output |
| A1' | `corpus.py:resolve_sites` | `@ChiaFunction(max_retries=0)`, **head** | 300 s `[DEFAULT]`, `subprocess` | `(clone_path, run_commit, tuple(sites))`; a pure query |
| A2 | `pin_select.py:select_release_pinned_main` | `@ChiaFunction(max_retries=0)`, **head** | 600 s `[DEFAULT]`, `subprocess` | `(clone_head_sha, tag_set_sha)` |
| A3 | `generate_task.py:generate_seeded` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | 2400 s `[DEFAULT]`, `turn` | none; a model turn is replayed through bypass, never re-run |
| A4 | `generate_task.py:generate_mutation` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | 600 s `[DEFAULT]`, `subprocess` | `(seed_sha, iteration, mutator_set_sha, mutator_seed_int)` |
| A5 | `feedback.py:build_feedback` | `@ChiaFunction(max_retries=0)`, head | 120 s `[DEFAULT]`, `driver` | `(run_manifest_id, seed_sha, iteration)` |
| A6a | `budget.py:load_budget` | `@ChiaFunction(max_retries=0)`, head | 120 s `[DEFAULT]`, `driver` | `(budget_path, budget_file_sha)` |
| A6b | `ledger.py:accrue` | `@ChiaFunction(max_retries=0)`, head | 120 s `[DEFAULT]`, `driver` | `entry_id`; append-only, so a repeat is detected rather than absorbed |
| A7 | `mutator_synth.py:synthesise_mutators` | `@ChiaFunction(max_retries=0)`, head | 3600 s `[DEFAULT]`, `turn` | none, deliberately: the freeze is write-once and a second call raises (§8.3). Run once, frozen, referenced by SHA |
| B1 | `bug_loop.py:build_image` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | 10800 s `[DEFAULT]`, `subprocess` | the **image tag**, which is the SHA-256 of `(circt_sha, sdk_tag, sorted(targets), flag_string, slang)` (§4.11.1); an existing tag whose `ImageSpec` validates is returned without building |
| B2 | `probe_task.py:probe_execute` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | `probe_wall_seconds` plus 60 s `[DEFAULT]`, `subprocess` | `(run_manifest_id, probe_id)` |
| B3 | `probe_task.py:oracle_primary` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | 600 s `[DEFAULT]`, `subprocess` | `(probe_id, build_result_sha)` |
| B4 | `probe_task.py:oracle_differential` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | 1800 s `[DEFAULT]`, `subprocess`; `extract_port_list`'s own 60 s inside it | `(probe_id, stimulus_id, verilator_version)`; the three §3.6.3 helpers are idempotent on `(port_list_sha, stimulus_seed)` |
| B5 | `probe_task.py:reduce_case` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | `reduction_wall_seconds` plus `reduction_sigkill_grace_seconds`, `subprocess` | `(probe_id, reducer)`; idempotent only at a fixpoint |
| B6a | `triage_task.py:issue_mirror_refresh` | `@ChiaFunction(max_retries=0)`, head | 1800 s `[DEFAULT]`, `turn` | `(repo, issue_cap, run_manifest_id)`; once per run |
| B6b | `triage_task.py:dedup_and_screen` | `@ChiaFunction(max_retries=0)`, **head** | 900 s `[DEFAULT]`, `subprocess` | `(candidate_id, mirror_refreshed_utc, run_commit)` |
| B7 | `triage_task.py:triage_report` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | 1200 s `[DEFAULT]`, `turn` | none in prose; every number is substituted, so a re-render changes no number |
| B8 | `repair_adapter.py:repair_adapt` | `@ChiaFunction(resources={"repair": 1}, max_retries=0)` | CHIA's five phase timeouts, unchanged, `turn` | none; each call is a new attempt, and the loop row is written first |
| B9a | `gate.py:gate_decide` | `@ChiaFunction(max_retries=0)`, head | 900 s `[DEFAULT]`, `driver`; the FR-13.16 poll on `turn` | `(candidate_id, run_manifest_id)` |
| B9b | `gate.py:gate_rerun` | `@ChiaFunction(resources={"circt": 1}, max_retries=0)` | `probe_wall_seconds` plus 60 s `[DEFAULT]`, `subprocess` | deliberately none: a fresh process in a new directory is the point |
| B9c | `approve.py:main` | head program, not a node | none; a human's own pace | `candidate_id`; a second approval is refused with the first's timestamp |
| B10a | `store.py:LoopStore` | `SQLiteNode(path, pin_to_current_node=True)` | `SQLiteNode`'s own 30 s busy timeout | primary key per table |
| B10b | `store.py:artefact_write` | `@ChiaFunction(max_retries=0)`, head | 300 s `[DEFAULT]`, `driver` | `(artefact_dir, relative_path)`; append-only, `PARTIAL` never deleted |
| B11 | `results.py:render_results` | `@ChiaFunction(max_retries=0)`, head | 600 s `[DEFAULT]`, `driver` | `(run_manifest_id, store_sha)`; a pure function of the store |
| B12 | `bug_loop.py:main` | head driver, not a node | the two arm windows, which it meters | `run_manifest_id`; a restart resumes and never re-charges |
| tool | `generate_task.py:ProbeWriteTool` | `ChiaTool`, `task_options` pinning it to A3's worker | none; one file write per call | `(probe_id, relative_path)`; a rewrite is byte-identical |
| tool | `generate_task.py:SourceReadTool` | `ChiaTool`, `task_options` pinning it to the **head** | 60 s `[DEFAULT]` per `git` call, `subprocess` | `(run_commit, method, args)`; a pure query against a fixed commit |

**Three components moved to the head in this revision, and one function is new** (K5, K6, and the
review's single question, "where does a worker node get CIRCT history from?"). A1, A2 and B6b all
need the last 24 months of `main`: A1 for `for-each-ref refs/tags/firtool-*` and the first-parent
walk, A2 for the pin walk over 24 months, B6b for the two commit scans. The only CIRCT tree on a
`circt` worker is `/workspace/circt`, which §4.11 leaves as a one-commit fetch, and §12.1 mounts no
clone; §11.1's posture is that a worker reaches nothing the head holds. So the three read the head's
blobless clone at `~/.cache/circt`, which is where §13.1's `--clone` already pointed and where §4.12's
`git backfill --sparse` note already assumed they were. None of the three runs a CIRCT binary, so
none needs the `circt` resource, and moving them **frees two apparatus slots** that were being held
by git.

The consequence for the arms is what makes the move affordable: `SeedRecord` now carries `diff` and
`test_files` (§2.4), so A3 and A4 need no git at all, and the one remaining query an arm makes
against the tree, FR-04.1's site resolution, is `corpus.resolve_sites` on the head. A3 and A4 keep
`{"circt": 1}` anyway, which is `02-HLD.md` §3's placement and is not a leftover: the two arms must
run at the **same apparatus concurrency** for FR-14.5's wall-clock equality to mean anything, and the
`circt` slot count is what fixes it. Neither arm touches the CIRCT tree.

### 3.3 `corpus.py` (A1, F-01)

```python
@ChiaFunction(max_retries=0)
def build_corpus(clone_path: str, corpus_head_sha: str, since: str,
                 inline_cap_bytes: int, timeout_seconds: int = 1800) -> dict:
    """Mine llvm/circt by PIN section 2's rule and emit the loop's seed corpus.

    Returns:
        {"seeds": list[SeedRecord], "sdk_map": SdkMap,
         "counts": {"filtered": int, "exact_pin": int, "no_run_line": int,
                    "unsupported_shape": int, "seed_text_over_cap": int,
                    "polarity": dict, "shape": dict},
         "inputs": {"clone_head_sha": str, "since": str, "git_version": str}}
    Worker:
        head - it runs git against the head's blobless clone, which is the only
        repository in the deployment holding 24 months of main (K5).
    Raises:
        CorpusError("no_tags") when for-each-ref returns nothing for
            refs/tags/firtool-*, with the refspec and the quoting note (FR-01.8);
        CorpusError("head_moved") when the clone's HEAD differs from
            corpus_head_sha, naming both (FR-01.11).
    """


@ChiaFunction(max_retries=0)
def resolve_sites(clone_path: str, run_commit: str, sites: list[dict],
                  timeout_seconds: int = 300) -> dict:
    """Say which of a turn's sibling sites exist in the tree at the run's commit.

    Returns:
        {"resolved": list[dict], "rejected": list[dict]}, each entry the input
        site plus "reason" on a rejection, one of "no_such_file" or "no_symbol".
    Worker:
        head - the clone is the head's (K5). No model, no CIRCT binary.
    Raises:
        nothing. A git failure marks every site of that call "no_such_file" with
        the git stderr recorded, which rejects rather than accepts.
    """
```

`resolve_sites` is the one query FR-04.1's acceptance criterion needs and the one thing A3 still asks
of the tree; it exists because A3 runs on a `circt` worker and the clone is on the head. Its two
commands, per site, are `git -C <clone> ls-tree -- <run_commit>:<dir> <basename>` for the path and
`git -C <clone> grep -n -F -- <symbol> <run_commit> -- <file>` for the symbol; both are argument
vectors and neither takes a shell. Verified against the real clone on 2026-09-14:

```
$ git -C ~/.cache/chia-pin-smoke/circt grep -n -F -- parseHWArray b792c772 -- lib/Dialect/HW
b792c772...:lib/Dialect/HW/HWTypes.cpp:35:static ParseResult parseHWArray(AsmParser &parser, ...
b792c772...:lib/Dialect/HW/HWTypes.cpp:703:static ParseResult parseHWArray(AsmParser &p, ...
$ git -C ~/.cache/chia-pin-smoke/circt grep -n -F -- zzzNoSuchSymbol b792c772 -- lib/Dialect/HW
  (no output)                                                                     rc=1
```

The caller is B12, at the start of a run, before any probe. On `CorpusError` it exits non-zero and
the run does not start: both are preconditions that make a run meaningless (`02-HLD.md` §6, A1's two
rows).

**The five git commands, in order.** All are `git -C <clone_path>` with `capture_output=True`,
`text=True`, `check=True`, and a per-call `timeout`, which is the shape `analysis/pin_window.py:29-31`
already uses.

1. `git -C <clone> rev-parse HEAD` and compare to `corpus_head_sha`; on a difference, raise
   `head_moved`. FR-01.11's reset is `git -C <clone> checkout --detach <corpus_head_sha>` and is done
   by the caller, not here, so that mining never silently moves a clone.
2. `git -C <clone> for-each-ref --format=%(refname:short)\t%(creatordate:unix) --sort=creatordate refs/tags/firtool-*`
   (`analysis/pin_window.py:40-41`). The refspec is passed as one element of the argument list, so no
   shell expands it; FR-01.8's failure mode is a shell glob eating it, and passing an argument vector
   is why it cannot happen here. An empty result raises `no_tags`.
3. `git -C <clone> ls-tree <tag> llvm` per tag, whose third field is the tag's LLVM pin
   (`analysis/pin_window.py:43-46`).
4. `git -C <clone> log --first-parent --format=%H\t%ct\t%s HEAD` for the ordered first-parent history
   (`analysis/pin_window.py:52`), and
   `git -C <clone> log --first-parent --raw --no-abbrev --format=COMMIT %H HEAD -- llvm` for every
   commit that moved the submodule, whose `:160000` lines carry the old and new gitlink
   (`analysis/pin_window.py:60-67`). The pin at a commit is carried backwards from
   `git -C <clone> ls-tree HEAD llvm` (`analysis/pin_window.py:70`).
5. `git -C <clone> log --first-parent --name-status --format=COMMIT %H HEAD` for the shape filter
   (`analysis/pin_window.py:114`).

The changed test files themselves are read in **one** batched call,
`git -C <clone> cat-file --batch` fed `<sha>:<path>` on stdin, one spec per line, which is how the
measurement read 228 blobs from a blobless clone in 125 s; a per-file `git show` would be 228 round
trips. **Their text is what `SeedRecord.test_files` carries**, keyed by `test_paths`, so the batched
read serves both FR-01.2's `RUN:` extraction and FR-05.1's starting inputs in one pass. The sixth
command, added with contract 2.0, fills `SeedRecord.diff`:

6. `git -C <clone> show --format= --unified=3 --no-renames <seed_sha> -- <source_paths>`, the seed
   commit's diff restricted to the `lib/` and `include/` paths FR-01.1 already records, which is what
   §7.2's `$diff` substitutes. It is restricted to those paths because the test half of the same
   commit is already in `test_files` and would otherwise be sent twice.

A seed whose `diff` or whose `test_files` total more than `artefact_inline_cap_bytes` is marked
ineligible for both arms with `exclusion_reason="seed_text_over_cap"` and counted in
`counts["seed_text_over_cap"]`, because a truncated diff in a prompt is a worse input than no seed.

**The `RUN:`-line normalisation of FR-01.10, step by step.**

```python
def normalise_run_line(line: str) -> tuple[str, list[str], Polarity, Shape,
                                           dict[str, str], dict]:
    """Turn one verbatim lit RUN: line into a tool, an argv and its properties.

    Returns:
        (tool, argv, polarity, shape, env, notes), where notes records what each
        of the six steps below did: lines_joined, not_crash, dropped_tail,
        substitutions and unsupported_construct.
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing. An unparseable line returns shape="unsupported" with the
        construct recorded, which excludes the seed rather than aborting.
    """
```

It performs exactly these six steps, in this order, recording what each did in `notes`.

| Step | What it does | What it records |
|---|---|---|
| 0 | Join lit's `\` continuations into one logical line, then strip the `// RUN:` or `; RUN:` prefix and any leading whitespace. | the number of physical lines joined |
| 1 | If the first token is `not`, drop it and set `polarity = "expect_nonzero"`; otherwise `polarity = "expect_zero"`. `not --crash` also drops the `--crash` token and sets `notes["not_crash"] = True`. | `polarity` |
| 2 | If the first remaining token is `env`, drop it and every following `NAME=VALUE` token, recording them as `env`. | `env`, a dict |
| 3 | If the first remaining token is `split-file`, drop the wrapper and set `shape = "split_file"`; otherwise `shape = "plain"` for now. | `shape` |
| 4 | Drop everything from the first **unquoted** `\|` onwards. Quoting is tracked with a two-state scanner over `'` and `"`, so a pipe inside a quoted `FileCheck` pattern does not truncate the line. This is what removes `\| FileCheck %s` and every other downstream filter. | the dropped tail, verbatim |
| 5 | Resolve lit's substitutions: `%s` to the probe's input path, `%t` to `<probe dir>/t`, `%S` to the probe directory, `%{fs-sep}` and any other `%{...}` left alone (step 6 then rejects the line). `%s` is the only one that may appear more than once. | each substitution made |
| 6 | If the line still carries a `;`, a `&&`, a backtick, a `$(`, or a `%{`, set `shape = "unsupported"`. | the construct found |

After step 6 the first token is the tool and the rest is `argv`. FR-01.3's classification is that
tool name and nothing inferred from a source path. A seed whose every line is `unsupported` is
excluded from both arms and counted; a seed with no `RUN:` line at all gets an empty `run_lines` and
is excluded from the seeded draw (FR-01.9).

**One normalisation the probe argv needs and the seed record does not.** FR-01.2's verbatim line is
kept as the seed's `run_lines`; the argv a `ProbeSpec` carries has `--verify-diagnostics` and
`--split-input-file` **stripped**, because a probing input is one program and neither option means
anything for it: `--verify-diagnostics` makes the tool succeed when it emits the diagnostics an
`expected-*` comment predicted, which a generated input carries none of, and `--split-input-file`
makes the tool process independent chunks, under which `circt-reduce` can delete nothing because every
chunk keeps the failure alive. Both are stripped by
`strip_probe_only_options(argv: list[str]) -> tuple[list[str], list[str]]`, which returns the
surviving argv and the tokens it removed, and which removes a
token equal to either option **and** a token beginning with either followed by `=`, because
`circt-opt` accepts both spellings, `--split-input-file[=<string>]` and `--verify-diagnostics=<value>`
(verified, `SDK circt-opt --help`). The stripped options are recorded in the `ProbeSpec`'s
`expected_outcome` note so the derivation stays visible. Measured over the corpus, this reaches 29.9%
and 28.3% of seeds respectively (M1), so it is not an edge case.

### 3.4 `pin_select.py` (A2, F-02)

```python
@ChiaFunction(max_retries=0)
def select_release_pinned_main(clone_path: str, timeout_seconds: int = 600) -> dict:
    """Return the newest first-parent main commit whose LLVM pin has a release.

    Returns:
        {"run_commit": str, "pin_sha": str, "pin_tag": str,
         "tags_sharing_pin": list[str], "lag_commits": int, "lag_days": float,
         "current_window_has_release": bool, "resolved_utc": str}
    Worker:
        head - it walks 24 months of main in the head's blobless clone, which no
        worker container mounts (K5).
    Raises:
        PinSelectError("no_match") when no first-parent commit inside 24 months
            has a matching release, naming the last window examined (FR-02.5).
    """
```

Equality is of full 40-character SHAs and nothing else: no tolerance, no nearest match, no version
string (FR-02.3). "Newest" is first-parent position, not commit date (FR-02.1). Where several
releases share the chosen pin, the newest by tag date wins and all are recorded (FR-02.6). The lag
is `git -C <clone> rev-list --first-parent --count <chosen>..<head>` for commits and the difference
of the two commit dates for days (FR-02.2). The caller, B12, writes all eight fields into the
`RunManifest` once and never recomputes them, because A2 is idempotent only against a fixed clone.

### 3.5 `generate_task.py` (A3, A4, `ProbeWriteTool`, F-04 and F-05)

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def generate_seeded(seed: SeedRecord, feedback: FeedbackBundle,
                    remaining: LedgerSnapshot, cfg: dict) -> dict:
    """Run stages 1 and 2 for one seed and emit the probing inputs they wrote.

    Returns:
        {"specs": list[ProbeSpec], "root_cause_class": str,
         "sibling_sites": list[dict], "rejected_sites": list[dict],
         "truncated": int, "logs": dict, "failure": str | None}
    Worker:
        {"circt": 1} for the node; each turn is dispatched at {"llm": 1.0}.
    Raises:
        nothing. A turn that times out, errors or returns nothing is recorded in
        "failure", charged to the ledger, and the seed's iteration ends
        (FR-04.8); the run continues with the next seed.
    """
```

The body is CHIA's per-phase turn machinery, reused rather than rewritten: the `_turn` shape of
`chia:examples/circt_issue_solver/issue_task.py:71-136`, ~~the backend selection of
`issue_task.py:81-123`~~ **the backend construction of `build_llm` below**, the transcript capture of
`issue_task.py:126-135`, and `Template(cfg[key]).safe_substitute(**kw)` for rendering
(`issue_task.py:138-141`), which matters because MLIR and shell braces break `str.format`. Three
things are new: the two prompts of §7, the emitter, and the twenty lines of backend glue this
subsection now gives.

#### 3.5.1 The backend, the interlock and the turn (2026-09-14)

`02-HLD.md` §0.2 records the decision and its three measured facts; this is the code. Everything
below lives in `generate_task.py` and is imported by `triage_task.py` (B7) and `mutator_synth.py`
(A7), so there is exactly one backend constructor and exactly one turn node in the flow.

```python
MODEL_BACKEND = "vertex"                  # RunManifest.backend (C-20: one per run)
_LIVE_MODEL_ENV = "BUGLOOP_ALLOW_LIVE_MODEL"
_API_KEY_ENV = "GEMINI_API_KEY"


class LiveModelRefused(RuntimeError):
    """A real model backend was asked for without the live-call interlock set."""


def require_live_model(purpose: str, *, need_key: bool = True) -> "str | None":
    """The interlock, on its own, so every path to a live turn passes it.

    Returns:
        The stripped API key when need_key, else None.
    Worker:
        Wherever a live turn is about to be set up: build_llm below, and
        repair_adapter.repair_adapt before it invokes CHIA's chain (3.8), which
        builds its own backend inside a file this design does not otherwise
        call into.
    Raises:
        LiveModelRefused when BUGLOOP_ALLOW_LIVE_MODEL is not exactly "1", or
        when need_key and GEMINI_API_KEY is unset, empty or unexpanded. Nothing
        else. No network call is made here.
    """
    # Exactly "1". An unset variable, an empty one and an unexpanded "${...}"
    # all fail this, which is the safe direction.
    if os.environ.get(_LIVE_MODEL_ENV) != "1":
        raise LiveModelRefused(
            f"refusing to set up a live model turn for {purpose}: "
            f"set {_LIVE_MODEL_ENV}=1 to allow a real model request "
            "(03-LLD.md 3.5.1; ADR-D-03, superseding section and addendum)")
    if not need_key:
        return None
    key = (os.environ.get(_API_KEY_ENV) or "").strip()
    # An UNEXPANDED reference is a literal, not an empty value: CHIA's loader
    # substitutes ${VAR} from os.environ and leaves the text alone when the
    # variable is unset (chia:chia/cluster/config.py:304), so a container
    # brought up without the key holds the seven characters "${GEMI...".
    # Catching it here turns a 403 from Vertex into a refusal on the head.
    if not key or key.startswith("${"):
        raise LiveModelRefused(
            f"{_API_KEY_ENV} is unset, empty or an unexpanded reference on "
            f"{socket.gethostname()}: the cluster YAML passes it with -e and the "
            "operator sources ~/.config/bugloop/gemini.env before `chia up` (11.2)")
    return key


def build_llm(system_message: str, timeout_seconds: int, model_id: str) -> "VertexGeminiLLM":
    """Build the campaign backend, refusing to reach the network unbidden.

    Returns:
        A VertexGeminiLLM configured for Vertex AI express mode: one API key,
        no project and no location.
    Worker:
        Called on whichever process is about to dispatch a turn; the object it
        returns is serialised to an `llm` worker by llm_turn.
    Raises:
        LiveModelRefused, from require_live_model above. Nothing else. No
        network call is made here: constructing the backend opens no connection.
    """
    from chia.models.vertex import VertexGeminiLLM

    key = require_live_model(f"{MODEL_BACKEND}:{model_id}")
    llm = VertexGeminiLLM(
        model=model_id,
        system_message=system_message,
        timeout_seconds=timeout_seconds,
        project=None,
        location=None,
        # api_key: express mode. http_options.timeout: MILLISECONDS, and the only
        # thing that bounds the request, because VertexGeminiLLM stores
        # timeout_seconds and never reads it (vertex.py:219, 240, and nowhere else).
        client_kwargs={"api_key": key,
                       "http_options": {"timeout": int(timeout_seconds * 1000)}},
    )
    # Express mode takes an API key and NO project and NO location. CHIA's
    # constructor defaults location to "us-central1" and project to
    # $GOOGLE_CLOUD_PROJECT (vertex.py:242-247), and google-genai raises
    # ValueError("Project/location and API key are mutually exclusive in the
    # client initializer.") on that pair. Two assignments, and CHIA is unchanged.
    llm.project = None
    llm.location = None
    return llm


@ChiaFunction(resources={"llm": 1.0}, max_retries=0)
def llm_turn(llm, user_message: str, tools: list) -> dict:
    """Run one model turn on an `llm` worker and bring its token counts home.

    Returns:
        {"result": str, "stream": str, "stderr": str, "success": bool,
         "usage": {"tokens_in": int, "tokens_out": int, "num_turns": int,
                   "model": str | None}}
    Worker:
        {"llm": 1.0}; the MCP tool servers stay where their own task_options
        put them and are reached over HTTP from here.
    Raises:
        whatever the backend raises. A3, A7 and B7 each catch and record it as
        their stage's turn failure (FR-04.8, FR-11.8).
    """
    cli = llm.prompt(user_message, tools)          # direct call: runs in THIS process
    meta = dict(getattr(llm, "_last_metadata", {}) or {})
    return {"result": cli.result, "stream": cli.stream_result, "stderr": cli.stderr,
            "success": bool(getattr(cli, "success", False)),
            "usage": {"tokens_in": meta.get("input_tokens", 0),
                      "tokens_out": meta.get("output_tokens", 0),
                      "num_turns": meta.get("num_turns", 0),
                      "model": meta.get("model")}}
```

**Why `llm_turn` exists at all, in one paragraph, because it is the one place this design departs
from CHIA's own call shape.** CHIA writes
`get(llm.prompt.options(resources={"llm": 1.0}).chia_remote(llm, prompt, tools))`
(`chia:examples/circt_issue_solver/issue_task.py:124`) and reads the usage off the result,
`getattr(cli, "usage", None)` (`issue_task.py:134`). That works for `antigravity`, which returns an
`AntigravityQueryResult` carrying a `usage` field (`chia:chia/models/antigravity.py:213`,
`322-331`). It cannot work for `vertex`: that backend accumulates
`usage_metadata.prompt_token_count` and `candidates_token_count` into `self._last_metadata` on the
**LLM object** (`chia:chia/models/vertex.py:479-482`, `579`) and returns a plain `QueryResult`,
whose fields are `result`, `returncode`, `stderr`, `stream_result` and `success` and nothing else
(`chia:chia/base/llm_call.py:15-35`; `chia:chia/models/vertex.py:586-591`). `chia_remote` and
`.options(...).chia_remote(...)` both dispatch through a Ray trampoline that serialises the
arguments (`chia:chia/base/ChiaFunction.py:172-212`, `228-273`), so the copy that learns the token
counts is the worker's and dies with the task. `llm_turn` holds the same resource at the same
weight, and calls `prompt` **directly**, which for a `@ChiaFunction` "just runs in the caller's own
process and isn't a node" (`chia:docs/concepts/overview.rst:36-37`); the counts are then read in the
process that wrote them. FR-14.6 is satisfiable on the campaign backend only because of those four
lines. `tests/test_generate_task.py` asserts the departure deliberately, so that nobody "restores"
CHIA's spelling and silently zeroes the ledger.

**What the interlock is, and what it is not.** It is a refusal in the **construction** path, so
there is no code path from any stage to Vertex that does not pass it; it is not a flag consulted at
dispatch, which a second call site could forget. `build_llm` is the only place **in the loop's own
modules** that names `VertexGeminiLLM`, asserted by a source search in `tests/test_layout.py`.
**One second construction path exists and is gated rather than forbidden, 2026-09-14 (§3.8).**
`issue_task.py`'s additive `elif backend == "vertex":` arm constructs its own `VertexGeminiLLM`, and
it is CHIA's file, so it cannot carry the loop's interlock and must not be asked to. `repair_adapt`
therefore calls `require_live_model` itself, **before** it invokes the chain, which is why the guard
is a named function rather than four lines inside `build_llm`: with that call, no stage of this loop
reaches a model without passing the same refusal, and without it stage 7 would be the one hole in it. Tiers T0 to T2 of
`04-Test-Plan.md` never set `BUGLOOP_ALLOW_LIVE_MODEL`; they substitute `build_llm` with a factory
returning a `VertexGeminiLLM` whose `genai.Client` is the fake of CHIA's own
`chia/models/tests/test_vertex.py:78-97`, so the whole agent loop, the MCP tool round trip and the
usage accumulation all run offline. The pilot, `05-Work-Plan.md` W-18, is the first run that sets the
variable, and it sets it in the operator's shell before `chia up`, alongside `GEMINI_API_KEY`, so
that both arrive on the `llm` workers by the same mechanism (§11.2, §12.1).

**Three consequences that are easy to lose.**

1. **The model id comes from `budget.yaml`.** `cfg["model_id"]` is `BudgetFile.model_id`,
   `gemini-3.8-flash`, one value for every agent stage, and `RunManifest.model_ids` records
   `"vertex:gemini-3.8-flash"` against `generate_seeded`, `triage_report` and `mutator_synthesis`
   (§2.7). There is no per-stage model selector and there is no `--model` default in the code.
2. **The stage timeout has to be passed twice, and the second is the one that bites.**
   `VertexGeminiLLM` accepts `timeout_seconds`, assigns it
   (`chia:chia/models/vertex.py:219`, `240`) and **never reads it again**: a grep of the module for
   `timeout` returns exactly those two lines, so nothing in the backend bounds the request. The
   constructor argument is still passed, because it is the documented one and because a future CHIA
   release may honour it, and the bound that actually holds is
   `client_kwargs["http_options"]["timeout"]`, which `google-genai` documents as "Timeout for the
   request in milliseconds" and which `genai.Client` receives verbatim through `**client_kwargs`
   (`chia:chia/models/vertex.py:406-411`). **Measured 2026-09-14:**
   `genai.Client(vertexai=True, api_key="<dummy>", http_options={"timeout": 2400000})` in
   `~/.cache/chia-venv` returned a client whose `_http_options.timeout` is `2400000` with `project`
   and `location` both `None`. Without it, `02-HLD.md` §3's `turn` enforcement column would be a
   claim with no mechanism behind it for A3, A7 and B7. `VertexGeminiLLM` also retries three times by
   default and never retries a rate limit, an authentication failure, an invalid request or a blocked
   response (`chia:chia/models/vertex.py:286-339`), which is behaviour FR-04.8 records as a turn
   failure rather than behaviour this design adds; note that the three retries are **inside** the
   one node, so the stage's wall-clock ceiling is up to three times the per-request timeout and
   `02-HLD.md` §3's node-level value is read as the per-request bound.
3. **`max_tokens` stays at CHIA's 16000 default** (`chia:chia/models/vertex.py:226`). A turn that
   hits it raises `MaxOutputTokensError` after one retry, which A3 records as
   `failure="max_output_tokens"` and charges to the ledger like any other failed turn. Raising it is
   a knob this design does not add.

**The tool list handed to both turns is exactly `[source_read, probe_write]`** and FR-04.4's unit test
asserts that literal list. **`BashTool` is not given to stage 1, stage 2 or stage 6** and this
revision withdraws it from all three (W10).

The reason is that FR-04.4 has two clauses and the `BashTool` satisfied only one. Its requirement
text is "shall not be given, and **shall not be able to reach**, any tool that computes a measured
result"; its acceptance criterion is a check on the tool list. `BashTool(name, work_dir,
timeout_seconds, task_options)` has no read-only mode (`chia:chia/base/tools/BashTool.py:19-31`):
`work_dir` is the shell's cwd and nothing more. The tool is pinned to the `circt` worker, whose
`PATH` puts `/workspace/circt/build/bin` first (`chia:dockerfiles/ChiaCirctBaseDockerfile:113`), so
the agent could run `circt-opt` on its own input, run `ninja`, and write anywhere in the tree. §7.3's
rule 5 forbade it in prose to the model, which is the weakest enforcement there is and exactly what
NFR-03 exists to avoid. FR-06.8's "`git status` in the tree is clean after a batch of probes" sat at
the same risk.

**`SourceReadTool`, the replacement, is read-only by construction rather than by instruction.** It is
a plain `ChiaTool` with three methods and no shell anywhere; every method is one `git` argument
vector against the head's blobless clone at the run's commit, so there is no path from it to a
binary, a build, or a write.

```python
class SourceReadTool(ChiaTool):
    """MCP tool: read CIRCT's source at the run's commit. Read-only by construction.

    Constructed per iteration with the clone path and the run's commit bound, and
    pinned by task_options to the HEAD, which is where the clone is (K5). Every
    method is one git argument vector and no method takes a shell, a path outside
    the commit, or a write.
    """

    def __init__(self, name: str, clone_path: str, run_commit: str, cap_bytes: int,
                 task_options: dict | None = None):
        super().__init__(name, task_options=task_options)
        self.clone_path = clone_path
        self.run_commit = run_commit
        self.cap_bytes = cap_bytes
        self.mcp.add_tool(self.read_file, name=f"{name}_read_file")
        self.mcp.add_tool(self.grep, name=f"{name}_grep")
        self.mcp.add_tool(self.list_dir, name=f"{name}_list_dir")
        super().__post_init__()

    def read_file(self, path: str) -> str:
        """Return one CIRCT source file's text at the run's commit.

        path is repository-relative, for example lib/Dialect/HW/HWTypes.cpp.
        Returns the file's text, truncated with a marked tail if it is very
        large, or a one-line string beginning 'Error:' if the path does not
        exist at that commit.
        """

    def grep(self, pattern: str, path_prefix: str) -> str:
        """Search CIRCT's source at the run's commit for a fixed string.

        pattern is a literal, not a regular expression; path_prefix limits the
        search, for example lib/Dialect/HW. Returns matching lines as
        '<path>:<line>:<text>', or 'Error:' if nothing matched.
        """

    def list_dir(self, path: str) -> str:
        """List one directory's entries in CIRCT at the run's commit.

        path is repository-relative; '' lists the repository root. Returns one
        name per line, or a one-line string beginning 'Error:'.
        """
```

The three git commands, each an argument vector, each verified against the real clone on 2026-09-14:

| Method | Command | Verified |
|---|---|---|
| `read_file` | `git -C <clone> show <run_commit>:<path>` | `git -C ~/.cache/chia-pin-smoke/circt show b792c772:lib/Dialect/HW/HWTypes.cpp` returned 41,026 bytes beginning `//===- HWTypes.cpp - HW types code defs ...`; a missing path returned `fatal: path 'lib/Dialect/HW/NoSuch.cpp' does not exist in 'b792c772...'` |
| `grep` | `git -C <clone> grep -n -F -- <pattern> <run_commit> -- <path_prefix>` | the two `parseHWArray` hits of §3.3; `zzzNoSuchSymbol` returned no output and rc=1 |
| `list_dir` | `git -C <clone> ls-tree --name-only <run_commit>:<path>` | `...ls-tree --name-only b792c772:lib/Dialect/HW` returned `CMakeLists.txt`, `ConversionPatterns.cpp`, `CustomDirectiveImpl.cpp`, `HWAttributes.cpp`, ... |

Every return is truncated at `budget.yaml`'s `artefact_inline_cap_bytes` with the truncation stated in
the returned text, so a single `read_file` of a large generated file cannot fill a context window or
the object store. The clone is blobless, so `read_file` and `grep` fetch blobs lazily on a cold
object store; §4.12's `git backfill --sparse` is what B12 runs once to warm it, and it is the same
warm-up B6b's scan needs.

**`SeedReadTool` is still not resurrected.** `02-HLD.md` §1.4 deleted it because it duplicated the
`BashTool` on the same row; with the `BashTool` withdrawn, the row has exactly one occupant and
`SourceReadTool` is it. The count of agent-facing tools this design adds goes from one to two, and
§14.1 and `02-HLD.md` §1.4 both say so.

**The emitter and the cap.**

```python
def emit_specs(raw: dict, seed: SeedRecord, iteration: int, cap: int,
               probe_dir: str, run_manifest_id: str,
               turn_cost: dict) -> tuple[list[ProbeSpec], int, dict]:
    """Turn the stage-2 turn's JSON footer into validated ProbeSpecs.

    Returns:
        (specs, discarded, rejections), where discarded is the count truncated
        past the cap and rejections maps a reason to a count, with the reasons
        "no_file_written", "tool_mismatch" and "contract_error".
    Worker:
        pure; it is called inside A3 and runs no process.
    Raises:
        nothing. Every rejection is counted; a spec that cannot be built is not
        emitted (FR-04.5, FR-04.2).
    """
```

It reads the stage-2 turn's JSON output contract (§7.3), keeps the **first** `cap` entries in the
agent's emission order, and returns the discarded count. Every spec is passed through
`contract.validate` before it leaves the node, **and through one check `validate` cannot make**:

```python
    if spec.tool != seed.entry_tool:
        raise ContractError("E010_TOOL_MISMATCH",
                            f"ProbeSpec.tool {spec.tool!r} is not the seed's "
                            f"entry_tool {seed.entry_tool!r} (FR-04.2)")
```

That is K10's correction and it is not cosmetic. §3.5 previously claimed the check was
`E004_BAD_ENUM` from the contract validator, which is impossible twice over: `ProbeSpec.tool` is
annotated `tool: str` and not a `Literal`, so `_check_field` never reaches the `E004` branch, and
`validate` is handed one object and has no access to the `SeedRecord` the comparison needs. Run
against the document's own code assembled from §2.1 to §2.8 under Python 3.10, the red team measured
`validate ACCEPTED tool='firtool'`. The check therefore lives in the emitter, which does hold the
seed, and `01-FRD.md` §1.7 amends FR-04.2's criterion to name the emitter rather than the validator.
It is a belt on top of a brace: §7.3 builds the argv by substituting the written file's path into the
seed's own `argv_template`, so a mismatch means the emitter itself is broken, and the error says so.

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def generate_mutation(seed: SeedRecord, feedback: FeedbackBundle,
                      remaining: LedgerSnapshot, cfg: dict) -> dict:
    """Apply the frozen mutator set to every changed test file of one seed.

    Returns:
        {"specs": list[ProbeSpec], "no_ops": int,
         "mutator_failures": dict, "logs": {}}
    Worker:
        {"circt": 1}. No model runs here at any point (FR-05.1).
    Raises:
        nothing. A mutator that raises is recorded against its id and the arm
        continues (FR-05.7).
    """
```

`feedback` is accepted and not read. The rule is enforced on the body rather than the signature:
`tests/test_generate_task.py` reads `inspect.getsource(generate_mutation)` and asserts the identifier
`feedback` appears exactly once, in the parameter list. That satisfies FR-16.2 and FR-05.4 together
with one signature and one code path.

**`ProbeWriteTool`**, the second of the two agent-facing tools this design adds, and the only one that writes.

```python
class ProbeWriteTool(ChiaTool):
    """MCP tool: write one probing-input file into this iteration's probe directory.

    Constructed per iteration with the probe directory bound, so the agent
    cannot name a directory at all. Pinned by task_options to the same worker
    as the node that constructed it, so its writes land in the filesystem
    namespace the probe directory lives in.
    """

    def __init__(self, name: str, probe_dir: str, task_options: dict | None = None):
        super().__init__(name, task_options=task_options)
        self.probe_dir = os.path.realpath(probe_dir)
        self.mcp.add_tool(self.write_probe, name=f"{name}_write_probe")
        super().__post_init__()

    def write_probe(self, filename: str, content: str) -> str:
        """Write one probing input under this iteration's probe directory.

        filename is a bare file name with no directory part and no '..'. Returns
        the absolute path written, or a one-line error string beginning
        'Error:' if the name is rejected or the write fails. Writing the same
        name twice overwrites with identical bytes.
        """
```

Its shape is CHIA's own: the constructor calls `super().__init__(name, task_options=task_options)`,
registers with `self.mcp.add_tool(self.write_probe, name=f"{name}_write_probe")`, and ends with
`super().__post_init__()`, which is exactly the contract `ChiaTool` documents
(`chia:chia/base/tools/ChiaTool.py:62-105`) and exactly what `BashTool` does
(`chia:chia/base/tools/BashTool.py:19-31`). It is a plain `ChiaTool` and not an `AsyncJobTool`,
because a single file write does not hold the streamable-HTTP transport for minutes, which is the one
hazard `AsyncJobTool` exists for (`chia:chia/base/tools/AsyncJobTool.py:11-19`); FR-19.1's rule names
five categories of long work and a file write is in none of them.

**The path check is the whole security surface of the tool**, so it is stated as code:

```python
        if os.path.sep in filename or filename in ("", ".", ".."):
            return f"Error: filename must be a bare file name, got {filename!r}"
        dest = os.path.realpath(os.path.join(self.probe_dir, filename))
        if os.path.commonpath([dest, self.probe_dir]) != self.probe_dir:
            return f"Error: {filename!r} resolves outside the probe directory"
```

A rejected write returns the error string to the agent as the tool's result and is recorded in the
turn's transcript; nothing is written. That is FR-06.8's discipline applied at the writing end
(`02-HLD.md` §6, the `ProbeWriteTool` row).

**Both tools are stopped in a `finally`, and the omission was a real leak** (W11).
`ChiaTool.__post_init__` starts a `_ToolServerActor` per construction
(`chia:chia/base/tools/ChiaTool.py:82-105`) and `ChiaTool.stop()` kills it and removes it from the
registry (`chia:chia/base/tools/ChiaTool.py:154-165`). CHIA's own chain stops its three tools in a
`finally` (`chia:examples/circt_issue_solver/issue_task.py:282-289`) and A3 does the same. Without
it, 187 seeds at up to 3 iterations is up to 561 orphaned actors plus 561 orphaned servers in one arm
window, on a cluster whose whole point is a fixed size.

```python
    source_read = probe_write = None
    try:
        source_read = SourceReadTool(name=f"src_{seed.seed_sha[:12]}_{iteration}",
                                     clone_path=cfg["clone_path"],
                                     run_commit=cfg["run_commit"],
                                     cap_bytes=cfg["artefact_inline_cap_bytes"],
                                     task_options=cfg["head_options"])
        probe_write = ProbeWriteTool(name=f"probe_{seed.seed_sha[:12]}_{iteration}",
                                     probe_dir=probe_dir,
                                     task_options=cfg["here_options"])
        ...
    finally:
        for t in (probe_write, source_read):
            if t is not None:
                try:
                    t.stop()
                except Exception:
                    pass
```

`cfg["here_options"]` is the `NodeAffinitySchedulingStrategy(node_id=<this worker>, soft=False)` dict
CHIA builds as `here` (`chia:examples/circt_issue_solver/issue_task.py:67-68`); `cfg["head_options"]`
is the same shape with the head's node id, which is §3.0's head placement. The swallowed exception is
CHIA's own choice at the same place and for the same reason: a tool that will not stop must not mask
the turn's result.

B7's stage-6 turn constructs and stops `SourceReadTool` the same way, and gets no other tool.
### 3.6 `probe_task.py` (B2, B3, B4, B5; F-06 to F-09)

Worker-side. Imports `contract`, `ddmin`, `chia.chipyard.circt`, and **from `store` the record
dataclasses only** (`BuildResult`, `OracleVerdict`, `Frame`, `DifferentialVerdict`, `ReducedCase`,
`ImageSpec`). It never imports `LoopStore` and never opens `loop.db`, which it could not do anyway:
the store is a `SQLiteNode` pinned to the head (§6.1) and WAL's shared-memory coordination is
single-machine (`chia:chia/database/sqlite_node.py:29-33`). Every node here returns its records and
**the head writes the rows**. That resolves the contradiction W7 found between this sentence and
§3.11's "`store.py` is head-side": `store.py` is head-side as a **module with a database in it**, and
worker-side as a **module with dataclasses in it**, and `tests/test_layout.py` asserts the direction
that matters, that no supply-half module imports it at all. The file is shipped through `runtime_env`
`py_modules` exactly as CHIA ships `issue_task.py`
(`chia:examples/circt_issue_solver/circt_issue_loop.py:109-111`).

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def probe_execute(spec: ProbeSpec, image_spec: ImageSpec, limits: dict,
                  artefact_dir: str) -> dict:
    """Run one probing input through its tool, bounded, and classify it seven ways.

    Returns:
        {"build_result": BuildResult, "probe_result": ProbeResult}
    Worker:
        {"circt": 1} - it runs the image's own CIRCT binaries.
    Raises:
        BinaryMismatch(tool, expected_sha, actual_sha) when a tool binary's
            SHA-256 differs from image_spec.tool_hashes. The caller, B12, stops
            the run and names the worker: the tree has been mutated and every
            verdict from that worker is suspect (FR-06.1).
    """
```

The body does four things and nothing else.

1. **Hash check first.** For every distinct binary the argv will invoke, `hashlib.sha256` over the
   file at `/workspace/circt/build/bin/<tool>` compared to `image_spec.tool_hashes[tool]`. A
   mismatch raises before anything runs.
2. **Execute** through `chia.chipyard.circt.circt_exec_probe` (§3.10), which is a direct `execve` of
   an argument list under the `prlimit` prefix, in its own process group, with the process group
   SIGKILLed on the wall-clock expiry (FR-06.3).
3. **Classify** into exactly one of FR-06.9's seven statuses by

   ```python
   def classify_build(rc: int | None, signal: str | None, stderr: str,
                      limit_hit: str | None) -> tuple[str, str]:
       """Return (status, reason) for one finished probe, by 3.6's table alone.

       Returns:
           status is one of FR-06.9's seven; reason is the stopping_reason the
           ProbeResult carries, and is "" for clean_exit.
       Worker:
           pure; it reads four values and runs nothing.
       Raises:
           nothing.
       """
   ```

   whose rule is written once, here, and read by nothing else:

   | Condition, tested in this order | Status |
   |---|---|
   | `limit_hit == "wall"`: the stage killed the child at its own wall-clock limit | `timeout`, with a **null** signal, so it can never be read back as a crash (FR-06.4) |
   | `limit_hit == "cpu"` | `timeout`, likewise with a null signal, and `reason="cpu_limit"` |
   | `limit_hit == "address_space"`, **or** the child died by signal **and** stderr carries one of the three allocation-failure literals | `oom`, never `crash` (FR-06.7) |
   | stderr carries an assertion-failure line (§3.6.1) | `assertion` |
   | stderr carries a line beginning `LLVM ERROR:` | `fatal_error` |
   | the child died by signal | `crash` |
   | `rc != 0` | `parse_error` (G-49), with `reason="tool_rejected_argv"` where the apparatus test below fires and `reason="tool_rejected_input"` otherwise |
   | `rc == 0` | `clean_exit` |

4. **Persist and bound.** stdout and stderr are written to `<artefact_dir>/stdout.txt` and
   `stderr.txt`, truncated at `probe_output_byte_cap` with `truncated=True` recorded; the
   `ProbeResult`'s text fields go through `contract.bound_text`.

The three allocation-failure patterns are fixed verbatim, as FR-06.7 requires `03-LLD.md` to fix
them: the literal strings `std::bad_alloc`, `out of memory` and `LLVM ERROR: out of memory`, matched
case-sensitively as substrings of any stderr line. The third is a strict prefix-extension of the
second, so the second alone would suffice; both are listed because FR-06.7 lists both and because
`LLVM ERROR: out of memory` is a real literal in the SDK's `libLLVMSupport.so` (verified by
`strings`), which means it can arrive without the bare phrase ever appearing on its own line.

**The `oom` row now requires death by signal as well as the evidence**, which is FR-06.7's own
wording, "terminated by signal **and** its stderr carries an allocation-failure line", and which the
earlier table dropped (NIT 1). The difference is not hypothetical: an ordinary diagnostic containing
the phrase "out of memory" would otherwise have been counted `oom` rather than `parse_error`, and
`oom` is a taxonomy row FR-18.6 prints. The `address_space` clause keeps its own row without the
signal, because `RLIMIT_AS` makes allocation fail rather than killing, which is measured below.

**`parse_error` is split by reason rather than by status** (NIT 2). G-49's `parse_error` row swallows
apparatus misconfiguration: a pass name that the seed's `RUN:` line carried and that CIRCT has since
renamed exits non-zero exactly as a rejected input does. Measured on 2026-09-14 against the
assertions-on build, the two are distinguishable by their diagnostics:

```
$ circt-opt --pass-pipeline='builtin.module(definitely-not-a-pass)' ok.mlir -o /dev/null
<unknown>:0: error: MLIR Textual PassPipeline Parser:1:1: error: 'definitely-not-a-pass' does not
refer to a registered pass or pass pipeline                                          rc=1
$ circt-opt bad.mlir -o /dev/null
bad.mlir:1:1: error: custom op 'this' is unknown (tried 'builtin.this' as well)       rc=1
```

FR-06.9's seven statuses are closed and stay closed, so the status is `parse_error` either way; what
changes is `stopping_reason`, which is `tool_rejected_argv` when stderr carries the literal
`does not refer to a registered pass or pass pipeline` and `tool_rejected_input` otherwise, and
`results.py` prints the two counts separately so the `parse_error` row is never read as "the tool
rejected the input" when it means "the loop built an argv the tool would not take".

#### 3.6.1 The three firing patterns, fixed verbatim

FR-07.1 requires this document to fix all three. Each is a Python regular expression applied to
stderr line by line with `re.MULTILINE`.

```python
_ASSERT_GLIBC = re.compile(
    r"^(?:.*?: )?(?P<file>[^\s:]+):(?P<line>\d+): "
    r"(?P<func>.+?): Assertion `(?P<expr>.*)' failed\.$")
_ASSERT_UNREACHABLE = re.compile(
    r"^UNREACHABLE executed(?: at (?P<file>[^\s:]+):(?P<line>\d+))?!$")
_FATAL_ERROR = re.compile(r"^LLVM ERROR: (?P<message>.*)$")
```

**The `func` group is `.+?` and not `[^:]+`, and that one character is the difference between
classifying a CIRCT assertion and never classifying one** (K1). glibc's `__assert_fail` prints
`__PRETTY_FUNCTION__`, which for every C++ member or namespaced function contains `::`, and CIRCT is
C++. `[^:]+` forbids a colon, so the previous pattern matched only the one function-name shape that
has none, which is exactly the shape the C control used. `.+?` is lazy and is bounded on the right by
the literal `: Assertion \``, so it takes the whole signature and stops at the one place the line can
end. Both samples were compiled and run on 2026-09-14:

```
$ cat b.cpp
#include <cassert>
namespace circt { struct Foo { int get(int c) const { assert(c > 99 && "needs many args"); return c; } }; }
int main(int c, char**){ circt::Foo f; return f.get(c); }
$ c++ -O0 -o b_assert b.cpp && ./b_assert ; echo rc=$?
b_assert: b.cpp:2: int circt::Foo::get(int) const: Assertion `c > 99 && "needs many args"' failed.
rc=134
$ ./a_assert ; echo rc=$?            # the three-line C control
a_assert: a.c:2: main: Assertion `c>99 && "needs many args"' failed.
rc=134

$ python3 -c "<_ASSERT_GLIBC above>.match(line).groupdict()"
b.err -> {'file': 'b.cpp', 'line': '2', 'func': 'int circt::Foo::get(int) const',
          'expr': 'c > 99 && "needs many args"'}
a.err -> {'file': 'a.c', 'line': '2', 'func': 'main',
          'expr': 'c>99 && "needs many args"'}
```

and against the shape a CIRCT probe actually produces, an absolute binary path and an absolute source
path in one line:

```
/workspace/circt/build/bin/circt-opt: /workspace/circt/lib/Dialect/Comb/CombFolds.cpp:1234: \
mlir::OpFoldResult circt::comb::ExtractOp::fold(FoldAdaptor): Assertion `lo + width <= inputWidth \
&& "extract out of range"' failed.
 -> {'file': '/workspace/circt/lib/Dialect/Comb/CombFolds.cpp', 'line': '1234',
     'func': 'mlir::OpFoldResult circt::comb::ExtractOp::fold(FoldAdaptor)',
     'expr': 'lo + width <= inputWidth && "extract out of range"'}
```

The optional `(?:.*?: )?` group is the program-name prefix glibc prepends; it is lazy, so it stops at
the first colon-space, and `(?P<file>[^\s:]+)` then forbids a colon inside the path, which is why an
absolute path with no colon in it lands in `file` and not in the prefix. `func` is captured but is
**not** part of the fingerprint: G-43 uses the expression and the site, and a signature that changes
when a parameter type is renamed would break FR-10.6's cross-run query for no gain.

**`_ASSERT_UNREACHABLE` has no `msg` group any more, and its extraction reads the preceding line**
(K16). LLVM builds the unreachable diagnostic in three writes, the message, then the phrase, then
optionally the location (`if (msg) errs() << msg << "\n"; errs() << "UNREACHABLE executed"; if (file)
errs() << " at " << file << ":" << line; errs() << "!\n";`), and the `"\n"` after the message means
the message is on the **preceding line**, never on the same one. The three literals `UNREACHABLE
executed`, ` at ` and `!` are separately present in the SDK's `libLLVMSupport.so` (verified by
`strings` on 2026-09-14), which is the same construction seen from the other side. The old pattern's
`(?P<msg>.*?)` therefore always captured the empty string, and §3.6.2's "for an `assertion`,
`assertion_text` is the `expr` group" raised `IndexError` on this class because the old pattern had
no `expr` group at all.

The extraction is now stated for this class separately, and tested against a synthetic two-line
sample in LLVM's own format:

```
$ python3 -c "<the sample and the pattern>"
'Unhandled dialect in HWOps lowering'
  -> None
'UNREACHABLE executed at /workspace/circt/lib/Dialect/HW/HWOps.cpp:1234!'
  -> {'file': '/workspace/circt/lib/Dialect/HW/HWOps.cpp', 'line': '1234'}
   assertion_text = 'Unhandled dialect in HWOps lowering\nUNREACHABLE executed at
                     /workspace/circt/lib/Dialect/HW/HWOps.cpp:1234'
   assertion_site = '/workspace/circt/lib/Dialect/HW/HWOps.cpp:1234'
'UNREACHABLE executed!'            -> {'file': None, 'line': None}
'UNREACHABLE executed at F.cpp:7!' -> {'file': 'F.cpp', 'line': '7'}
```

So for an `UNREACHABLE executed` firing: `assertion_text` is the **preceding stderr line** followed by
a newline and the matched line with its trailing `!` removed, and where there is no preceding line it
is the matched line alone; `assertion_site` is `<file>:<line>` when the location groups matched, and
`None` otherwise, in which case §3.7.1's fingerprint falls to the frame basis. FR-07.3's "verbatim,
character for character" is satisfied against that pair rather than against an `expr` group this
class does not have, and `01-FRD.md` needs no erratum for it because FR-07.1 already delegates all
three patterns to this document.

A probe matching `_ASSERT_GLIBC` or `_ASSERT_UNREACHABLE` is an `assertion`; one matching only
`_FATAL_ERROR` is a `fatal_error`; the order is fixed by FR-07.2 and is the order `classify_build`
tests in.

#### 3.6.2 B3, the primary oracle

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def oracle_primary(build: BuildResult, image_spec: ImageSpec,
                   artefact_dir: str) -> OracleVerdict:
    """Decide whether the probe found a defect, and say which kind.

    Returns:
        OracleVerdict, with fired False and oracle_class None when it did not.
    Worker:
        {"circt": 1} - it runs llvm-symbolizer against the image's own binary.
    Raises:
        nothing. An unsymbolisable frame is recorded unresolved, not raised.
    """
```

It is a pure function of the stored `BuildResult` plus `llvm-symbolizer` on a fixed binary, so it is
fully idempotent. Four steps.

1. **Fire or not.** `fired` is true for exactly the `crash`, `assertion` and `fatal_error` statuses.
   `timeout` and `oom` never fire (FR-07.8, FR-07.2's precedence clause).
2. **Extract.** For a `_ASSERT_GLIBC` `assertion`, `assertion_text` is the `expr` group and
   `assertion_site` is `<file>:<line>`, both verbatim from stderr, character for character (FR-07.3).
   For a `_ASSERT_UNREACHABLE` `assertion`, both are §3.6.1's pair, because that class has no `expr`
   group and its message is on the preceding line. For a `fatal_error`, `fatal_message` is the text
   after `LLVM ERROR: `.
3. **Symbolise.** LLVM's own crash handler prints a stack trace whose frame lines take one of two
   measured shapes, and `_FRAME` captures **both**, with the module and the offset:

   ```python
   _FRAME = re.compile(
       r"^\s*#(?P<i>\d+)\s+(?P<addr>0x[0-9a-f]+)\s+"
       r"(?:(?P<func>.*?)\s+)?"
       r"(?:\((?P<module>[^()]+)\+(?P<offset>0x[0-9a-f]+)\)"
       r"|(?P<file>[^\s()]+):(?P<line>\d+):(?P<col>\d+))$")
   ```

   A real trace, from `bassert_g/bin/circt-opt` on a deeply nested `!hw.array` type on 2026-09-14,
   rc 139, 466 frames:

   ```
     #0 0x00007faeb3e3cceb llvm::sys::PrintStackTrace(llvm::raw_ostream&, int) (<sdk>/lib/libLLVMSupport.so+0x23cceb)
     #3 0x00007faeb3444e70 (/usr/lib/libc.so.6+0x44e70)
     #8 0x00007faeb5a98121 mlir::detail::Parser::parseDialectSymbolBody(llvm::StringRef&, bool&) (<sdk>/lib/libMLIRAsmParser.so+0x2d121)
    #11 0x0000556446172082 parseHWArray(mlir::AsmParser&, mlir::Attribute&, mlir::Type&) <src>/lib/Dialect/HW/HWTypes.cpp:723:7
   ```

   Frames 0, 3 and 8 are `shape="module_offset"`; frame 11 is `shape="attributed"`, a frame LLVM
   already symbolised at print time. Both shapes occur in one trace, so a parser that handles only one
   loses frames.

   **The offset is what the symboliser needs, and the runtime address is not.** CIRCT built against
   the shared-library SDK puts most frames in a `.so`, and LLVM prints the file offset inside the
   module in the parentheses. §4.9's old invocation fed the runtime addresses with `--obj=<the tool>`,
   which asks the symboliser about an object those addresses are not in. Measured, both ways, on the
   frames above:

   ```
   $ printf '0x2d121\n0x2e689\n' | llvm-symbolizer --obj=<sdk>/lib/libMLIRAsmParser.so \
       --demangle --output-style=JSON
   {"Address":"0x2d121","ModuleName":".../libMLIRAsmParser.so","Symbol":[{"FunctionName":
    "mlir::detail::Parser::parseDialectSymbolBody(llvm::StringRef&, bool&)","FileName":"","Line":0,...}]}
   {"Address":"0x2e689",...,"FunctionName":"mlir::detail::Parser::parseExtendedType()",...}

   $ printf '0x00007faeb5a98121\n0x00007faeb5a99689\n' | llvm-symbolizer \
       --obj=<build>/bin/circt-opt --demangle --output-style=JSON
   {"Address":"0x7faeb5a98121","ModuleName":".../circt-opt","Symbol":[{"FunctionName":"",
    "FileName":"","Line":0,"StartAddress":"",...}]}          <- the old recipe resolves nothing
   ```

   So `circt_symbolize` (§3.10) takes **frames**, groups them by module, and makes one
   `llvm-symbolizer --obj=<module>` call per module with that module's offsets on stdin. An
   `attributed` frame is not symbolised at all: LLVM already did it, and its function, file and line
   are taken verbatim.

   **What is resolvable, and by whom.** The SDK's prebuilt `.so` files carry no debug information, so
   even the corrected recipe returns `FileName:"" Line:0` for them, as the first measurement above
   shows. **Only frames inside CIRCT's own source-built objects can satisfy FR-07.4's "name a CIRCT
   source file and line"**, and this document says so plainly rather than leaving it to be
   rediscovered; `01-FRD.md` §1.7 carries it as an erratum to FR-07.4's acceptance criterion. The
   predicate is one line and is recorded per frame as `Frame.in_circt_object`:

   - a `module_offset` frame is in a CIRCT object when its module is
     `/workspace/circt/build/bin/<tool>` or matches `/workspace/circt/build/lib/libCIRCT*.so*`;
   - an `attributed` frame is in a CIRCT object when its file lies under `/workspace/circt/`, which
     covers both the source tree and the generated `.inc` files under `build/`.

   In the measured build CIRCT's own libraries are static archives, so CIRCT code is linked into the
   tool binary and the module is the binary's path; the `libCIRCT*.so` half of the rule is there for a
   shared-library configuration and costs one alternation.

   `frames_resolved` counts frames with a non-empty function name, which SDK modules do supply.
   `frames_with_location` counts frames that are **both** located and in a CIRCT object, that is
   `line > 0 and in_circt_object`, which is exactly FR-07.4's criterion and is what the
   `-gline-tables-only` of FR-03.4 buys (M2: `Naming.cpp:47` against `??:0:0` without it).

   One operational precondition the design now states: LLVM's crash handler emits the two shapes above
   **only when it can find `llvm-symbolizer`**. Measured with an empty `PATH`, the same crash printed
   a third, column-aligned shape headed `Stack dump without symbol names (ensure you have
   llvm-symbolizer in your PATH ...)`, which `_FRAME` does not match and is not asked to. The image
   puts `/opt/circt-sdk/bin` on `PATH` (`chia:dockerfiles/ChiaCirctBaseDockerfile:77`) and the SDK
   ships `llvm-symbolizer` there, so the precondition holds by construction; B1's acceptance records
   `llvm-symbolizer --version` from inside the published image alongside the tool hashes.
4. **Scope and command.** `out_of_scope_root` is true when, **after §3.7.1's crash-handler prologue is
   stripped**, the first remaining frame is not in a CIRCT object, that is when it lies in an SDK
   module or in libc (FR-07.5). Stripping first is what makes the field mean anything: unstripped, the
   first frame is `llvm::sys::PrintStackTrace` in `libLLVMSupport.so` for every crash in the campaign,
   so every candidate would be out of scope and F-12 would never run. `repro_command` is one line,
   shell-quoted with `shlex.join`, naming the absolute binary path and the probe's argv **without** the
   `prlimit` prefix, so a maintainer can paste it; the limits are the loop's concern, not the report's.

#### 3.6.3 B4, the differential

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def oracle_differential(spec: ProbeSpec, build: BuildResult, image_spec: ImageSpec,
                        artefact_dir: str) -> DifferentialVerdict:
    """Run one design through arcilator and Verilator from one stimulus.

    Returns:
        DifferentialVerdict, always, including not_applicable with its reason.
    Worker:
        {"circt": 1} - both simulators live on the CIRCT image (ADR-D-09).
    Raises:
        nothing. A harness that will not build is harness_failure, never diverge.
    """
```

Applicability is decided **before** either simulator runs, from the entry tool and the requested
output mode alone (FR-08.1): a `firtool` probe requesting `--ir-hw`, `--verilog` or `--split-verilog`,
or a `circt-opt` probe whose pipeline ends in the HW dialect, and nothing else. Everything else is
`not_applicable` with the reason. The count of applicable seeds over the corpus is A-19 and is
`[UNVERIFIED]`; F-08's first implementation task is to run this rule over the corpus and report the
count with the rule that produced it, and the answer decides whether the harness generators are
written at all.

**FR-08.2's two harness generators, specified.** The review found them fixed as argv (§4.6, §4.10)
and nowhere as code: no name, no signature and no port-list extraction rule, so FR-08.2 had no
specification a unit test could be written against. All three functions live in `probe_task.py` beside
`oracle_differential`, which is their only caller, and all three are pure but for the first, which
runs one `circt-opt`.

**The port list, and where it comes from.** Both harnesses must drive the **same** ports in the
**same** order, so the port list is extracted once, from one authority, and handed to both.

```python
@dataclass(kw_only=True)
class Port:
    """One port of the design under test, as the HW dialect declares it."""
    index: int                              # position in the module signature, from 0
    name: str                               # the HW dialect's own port name, verbatim
    direction: Literal["input", "output", "inout"]
    width: int                              # bits; 1 for i1 and for !seq.clock
    mlir_type: str                          # "i8", "!seq.clock", verbatim from the signature
    is_clock: bool                          # mlir_type == "!seq.clock", or name in _CLOCK_NAMES
    is_reset: bool                          # name in _RESET_NAMES and width == 1


_CLOCK_NAMES = ("clk", "clock", "clk_i", "i_clk")        # [DEFAULT], 9.4
_RESET_NAMES = ("rst", "reset", "rst_n", "resetn",
                "areset", "rst_i", "i_rst")              # [DEFAULT], 9.4


def extract_port_list(lifted_hw_path: str,
                      timeout_seconds: int = 60) -> list[Port]:
    """Read the design under test's port signature out of its lifted HW IR.

    Runs ONE command, on the lifted HW-dialect file the probe's own tool
    produced:

        /workspace/circt/build/bin/circt-opt <lifted_hw_path> -o - \\
            --mlir-print-op-generic

    and reads the module_type attribute of the one hw.module that carries no
    sym_visibility = "private". The generic form is used and the pretty form is
    not, because the generic form spells every port as
    `!hw.modty<input <name> : <type>, output <name> : <type>, ...>`, with the
    direction as a word and the order as written, where the pretty form spells
    the same thing as `in %name : type` / `out name : type` and drops the `%`
    on outputs. Verified on 2026-09-14 against the SDK: a two-module file
    printed `module_type = !hw.modty<input x : i2, output q : i2>` with
    `sym_visibility = "private"` on the submodule and no such attribute on the
    top, and a clocked module printed `!hw.modty<input clk : !seq.clock, ...>`.

    Ports are returned in signature order, index 0 first, inputs and outputs
    interleaved exactly as the signature declares them, because that order is
    what the port_list digest is taken over and what both harnesses index.

    Returns:
        list[Port], one per declared port, in signature order.
    Worker:
        {"circt": 1} - it runs the image's own circt-opt. Called inside B4, so
        it takes no slot of its own.
    Raises:
        HarnessError("no_top") when the file holds no hw.module with public
            visibility, or more than one;
        HarnessError("bad_port_type") when a port's type is not iN, !seq.clock
            or !seq.immutable<iN>, which is every aggregate (!hw.array,
            !hw.struct, !hw.inout) and every parameterised width;
        HarnessError("no_clock") when no port satisfies is_clock, because a
            combinational design has no cycle to sample at and FR-08.3's
            protocol has nothing to drive;
        HarnessError("circt_opt_failed") when the command exits non-zero or
            times out, carrying its stderr.
    """
```

`port_list_sha` is `hashlib.sha256` over `contract.to_json` of the `Port` list, hex-digested. It is the
one key of `ProbeSpec.differential`'s five the **generator cannot know**, because the port list exists
only once the design has been lowered to HW and the generator runs before any tool does: A3 and A4
emit the key as the empty string, B4 computes the digest here and records it on
`DifferentialVerdict.port_list_sha`, and §2.7's description of the key says so. Both harnesses are
generated from this one list in one call, so the digest is evidence that they were, not a comparison
between two halves.

**The shared stimulus protocol (FR-08.3), one definition for the whole campaign.** Five fields, four
of them constants of §9.4 and one derived per probe, and nothing else is a knob.

| Field | Value | Why it is fixed here |
|---|---|---|
| `stimulus_id` | `lfsr32-v1` `[DEFAULT]`, `STIMULUS_ID` in §9.4 | Names the definition below. A second definition is a second id and a new constant, never a parameter, because FR-08.3 requires **one** shared definition and a per-probe knob would make two runs incomparable. |
| `reset_protocol` | `hold-8-then-release` `[DEFAULT]`, `RESET_PROTOCOL` in §9.4 | Every reset port is driven to its asserted level for the first 8 cycles and to its deasserted level from cycle 8 onward. A port named `rst_n` or `resetn` is active low and its asserted level is 0; every other reset port is active high. No output is sampled before cycle 8. |
| `sample_point` | `pre-posedge` `[DEFAULT]`, `SAMPLE_POINT` in §9.4 | Every output port is read in the settled interval immediately **before** each rising clock edge, which is the one point at which a two-state and an event-driven simulator agree about a registered value without either being asked to model delta cycles. |
| `cycles` | 64 `[DEFAULT]`, `DIFFERENTIAL_CYCLES` in §9.4 | How many rising edges both harnesses run, reset cycles included, so 56 are sampled. Small enough that the whole comparison is a few thousand text lines and large enough that a pipelined design reaches steady state. |
| `port_list_sha` | computed above | Evidence, per the paragraph above. |

**The stimulus itself is derived and not stored**, which is what makes "one shared definition" a
property of the code rather than of a file both harnesses must find. For cycle `c` and input port `p`
of width `w`, the driven value is the low `w` bits of a 32-bit maximal-length Galois LFSR advanced
one step per `(cycle, port index)` pair, seeded with
`stimulus_seed ^ (port.index * 0x9E3779B1) ^ c`, taken as a plain Python integer and never from
`random`. Clock ports are excluded, because the harness drives the clock; reset ports are excluded,
because the reset protocol drives them. `stimulus_seed` is
`int.from_bytes(hashlib.sha256(f"{probe_id}|{stimulus_id}".encode("utf-8")).digest()[:4], "big")`,
so it is reproducible from the `probe_id` alone and the same integer reaches both generators.

**The X policy (FR-08.4), and the one asymmetry the design admits.** Verilator runs under
`--x-assign unique --x-initial unique` (§4.10), so an uninitialised bit takes a distinct
pseudo-random value; `arcilator` lowers to two-state arithmetic and has no X at all. That asymmetry is
the reason FR-08.9's `diverge_x_policy` bucket exists, and it is the harness's job to make it
**detectable** rather than to hide it: `RunManifest.x_policy` and `DifferentialVerdict.x_policy` both
carry the literal `x-assign=unique,x-initial=unique`, and a divergence confined to cycles before the
first write of the divergent output signal is classified `diverge_x_policy` and excluded from the
candidate count. Neither harness initialises any state the design does not initialise itself; doing so
would make the two agree by construction and delete the class the oracle exists to find.

**The two generators.**

```python
def gen_arc_harness(port_list: list[Port], stimulus_seed: int) -> str:
    """Build the arcilator harness MLIR that drives one design from the stimulus.

    Emits one func.func @bugloop_main around the design's arc.sim.* operations:
    arc.sim.instantiate for the design, arc.sim.set_input per driven input per
    cycle by the LFSR rule above, arc.sim.step per rising edge, and
    arc.sim.get_port per output port at the sample point, each printed as one
    canonical line by the acceptance shape below. The entry name is the
    ARC_JIT_ENTRY constant of 9.4 and not a parameter, because 4.6 passes
    --jit-entry=bugloop_main and a name per probe would be a second knob
    (FR-08.3).

    The returned text is written to <probe dir>/harness.mlir (6.5) and consumed
    by the argv of 4.6.

    Returns:
        the harness as MLIR text, one trailing newline, UTF-8.
    Worker:
        pure; it builds a string, runs no process and reads no file. Called
        inside B4 on its {"circt": 1} node.
    Raises:
        HarnessError("empty_port_list") for a port list with no driven input or
            no sampled output, which has nothing to compare.
    """


def gen_verilator_tb(port_list: list[Port], stimulus_seed: int) -> str:
    """Build the SystemVerilog testbench that drives the same design identically.

    Emits module bugloop_tb: a clock generator at a 2 ns period, one reg per
    input port and one wire per output port, an instance of the design under
    test bound by port NAME and never by position, the same reset protocol, the
    same LFSR values in the same order, and a $display per sampled cycle in the
    acceptance shape below, followed by $finish. The top module name is the
    literal bugloop_tb, which is what 4.10's --top-module names.

    Written to <probe dir>/tb.sv; the design under test is written beside it as
    <probe dir>/dut.sv by the probe's own --verilog or --split-verilog output,
    or by firtool --verilog on the lifted HW IR where the probe's own mode was
    --ir-hw (6.5).

    Returns:
        the testbench as SystemVerilog text, one trailing newline, UTF-8.
    Worker:
        pure; as above.
    Raises:
        HarnessError("empty_port_list"), exactly as gen_arc_harness does and
        for the same reason, so a port list that fails one fails both.
    """
```

**Neither generator has a timeout of its own**, because neither runs a process: both are bounded by
B4's own 1800 s node timeout (§3.2), and the two simulator invocations they feed carry the bounds
§4.6 and §4.10 give. `extract_port_list` does run a process and carries 60 s `[DEFAULT]`
(`PORT_LIST_TIMEOUT_SECONDS`, §9.4), enforced by `subprocess`, because a `circt-opt` that hangs on the
lifted IR must fail the harness rather than the node.

**Idempotency.** All three are idempotent on `(port_list_sha, stimulus_seed)`: the same port list and
the same seed produce byte-identical text, which is what lets `T-N-nfr02-01`'s ten re-runs compare
bytes and what makes a `harness.mlir` in the artefact tree regenerable from the record (NFR-01,
NFR-02). `extract_port_list` is idempotent on the lifted file's contents.

**The acceptance shape, which is what the differ actually compares.** Both harnesses write to
**stdout**, one line per sampled cycle, and nothing else:

```
BUGLOOP <cycle> <port name>=<value> <port name>=<value> ...
```

with `<cycle>` a decimal integer counting rising edges from 0, the ports in signature order restricted
to `direction == "output"`, and `<value>` lowercase hexadecimal, zero-padded to
`ceil(width / 4)` digits, with no `0x` prefix. Any other line either harness prints is ignored by the
differ and kept in the artefact. The differ reads both streams, compares the `BUGLOOP` lines
positionally, and on the first difference records `first_divergent_cycle` from the line's cycle number
and `first_divergent_signal` from the first port name whose value differs on that line, with
`arcilator_value` and `verilator_value` the two hexadecimal strings. Equal line sequences are `agree`.
The VCD files of §4.6 and §4.10 are recorded as evidence and are **not** parsed: a text comparison
needs no VCD reader and cannot disagree with one.

A harness that will not build, will not run, or prints no `BUGLOOP` line at all is
`harness_failure` with the failing arm named, never `diverge` (FR-08.8); so is any `HarnessError`
above, with its reason carried into `DifferentialVerdict.reason`.

**Whether a generated harness compiles and runs is `[UNVERIFIED]` and stays so.** Every flag of §4.6
and §4.10 was verified by running `--help`, and §4.13 records that; what no measurement covers is a
**generated** testbench against a **generated** design, because no generator has been written (A-08)
and A-19 has not yet said whether any seed is differential-applicable at all. The two implementation
tasks that settle it are, in order: A-19's count over the corpus by the applicability rule above, and
FR-08.2's acceptance run of these three functions on the recorded 12-line FIRRTL register-add of
FINAL Appendix A. §15 item 1 carries both.

#### 3.6.4 B5, the reducer

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def reduce_case(spec: ProbeSpec, verdict: OracleVerdict, limits: dict,
                artefact_dir: str) -> ReducedCase:
    """Shrink a firing input under a firing-specific interestingness test.

    Returns:
        ReducedCase, naming the reducer that ran and whether it reached a
        fixpoint; reduced=False with a reason where nothing could run.
    Worker:
        {"circt": 1} - it runs the image's own source-built circt-reduce.
    Raises:
        nothing. A reducer that aborts on its own assertion is recorded
        reducer_aborted and the last valid --keep-best output is kept.
    """
```

The reducer is chosen by input language, by FR-09.9's rule and no other; §4.4 gives the four branches
as argv. The binary is the **source-built** `circt-reduce` at `/workspace/circt/build/bin`, not the
SDK's, because FR-06.1 forbids SDK binaries on the measured path and the reduced case must be parsed
by the build that fired (`02-HLD.md` §9, accepted 2026-09-13). The cost is that its own assertions
are on and it can abort mid-reduction; `reducer_aborted` is that row, and it is not hypothetical.
Measured on 2026-09-14: driving `circt-reduce` with §10.2's assembled script over the recorded
`!hw.array` stack overflow, the **reducer itself** died with rc 139 before producing any output,
because it parses the candidate with the same parser the candidate overflows. A whole class of input
is therefore unreducible by `circt-reduce` by construction, the class whose failure is in the parser,
and §4.7's fourth row already sends it to `textual-ddmin`; the rule is now widened to send a
`reducer_aborted` there as well, on the same run, before the budget is spent.

### 3.7 `triage_task.py` (B6a, B6b, B7; F-10, F-11, F-15)

```python
@ChiaFunction(max_retries=0)
def issue_mirror_refresh(repo: str, issue_cap: int, token_path: str,
                         db_path: str) -> dict:
    """Mirror llvm/circt's open and closed issues into loop.db, once per run.

    Returns:
        {"refreshed_utc": str, "issues_mirrored": int, "issue_cap": int,
         "cap_bound": bool, "state": "all", "comments_mirrored": False}
    Worker:
        head - GithubIssuesNode is documented head-node only, and the token
        lives on the head and nowhere else (4.3 of 02-HLD.md, section 11 here).
    Raises:
        nothing it does not catch. A GithubRateLimitError marks the mirror
        incomplete with the count reached and screening proceeds against a
        partial mirror, flagged in the manifest (FR-10.7's detection point).
    """
```

The one call is `GithubIssuesNode(repo, token=<read from the file>, state="all").recent(n=issue_cap,
fetch_comments=False)`. Every part of that is CHIA's: the constructor takes `state` and
validates it against `open`, `closed` and `all`
(`chia:chia/github/github_issues_node.py:40-52`); `recent` takes `n`, `after` and `fetch_comments`
and delegates to `_list` (`chia:chia/github/github_issues_node.py:58-73`); `_list` does its own
paging at `_PER_PAGE`, which is 100, the maximum the REST API allows
(`chia:chia/github/github_issues_node.py:139-178`; `chia:chia/github/github_client.py:64`); and
`token` is a constructor argument the client prefers over the environment
(`chia:chia/github/github_client.py:85`). `_paginate` is **not** what `_list` calls
(`chia:chia/github/github_client.py:113-128`), which is why FR-10.9's cap is an issue count and never
a page count. `fetch_comments=False` is required, not merely permitted,
and CHIA's own example passes it for the same reason
(`chia:examples/circt_issue_solver/triage.py:61`).

**The mirror stores five fields per issue and no text beyond the body**: number, title, body, labels
and state. It stores no comments at all, which is what makes FR-20.4 true by construction rather than
by inspection: no maintainer's words can reach a prompt through this path, because none are in the
database.

```python
@ChiaFunction(max_retries=0)
def dedup_and_screen(candidate: CandidateRecord, seed: SeedRecord,
                     verdict: OracleVerdict, clone_path: str, db_path: str,
                     top_n: int) -> dict:
    """Fingerprint one candidate, screen it, and flag contamination both ways.

    Returns:
        {"fingerprint": Fingerprint, "dedup": DedupVerdict,
         "contaminated_symbol": bool, "contaminated_file": bool,
         "contamination_lower_bound": str, "fixing_commits": list[str]}
    Worker:
        head - both commit scans walk 24 months of main in the head's blobless
        clone, and the issue mirror is a table in loop.db, which is head-pinned
        (K5, K7).
    Raises:
        nothing. An undecidable dedup is dedup_unavailable, which fails gate
        question 4 rather than passing it (FR-10.7).
    """
```

The run's commit is **not** a parameter: it is `candidate.run_commit`, which `CandidateRecord`
carries and which is the only value that is right in both modes (K14, §3.7.2).

#### 3.7.1 The primary fingerprint, and the normalisation that makes it stable

G-43 gives two cases and FRD §10.2 item 12 asks this document to fix the normalisation. It is fixed
here and nowhere else.

**For an `assertion` firing**, the fingerprint is `f"{expr}\n{site}"` where:

- `expr` is `assertion_text` with runs of whitespace collapsed to one space and leading and trailing
  space stripped, and nothing else changed. The `&& "message"` tail of an LLVM assertion is **kept**:
  it is the most discriminating part of the expression and two different asserts on the same
  condition are two different bugs.
- `site` is `assertion_site` with the build prefix removed: a path beginning `/workspace/circt/` is
  made relative to it, and any other absolute path keeps only its last two components. The line
  number is kept verbatim, as G-43 says. Removing the build prefix is what lets FR-10.6's cross-run
  query work at all, because two images built in different directories would otherwise never match.

**Before any frame is used for anything, the crash-handler prologue is stripped** (K3). Every LLVM
crash begins with the same handler frames, so a fingerprint taken from the raw trace is mostly
boilerplate and the `@TOP_FRAME@` guard of §10.2 is vacuous. `strip_prologue(frames)` drops leading
frames until one survives, dropping a frame whose normalised function name is one of

```python
_PROLOGUE = ("llvm::sys::PrintStackTrace", "llvm::sys::RunSignalHandlers", "SignalHandler",
             "__restore_rt", "pthread_kill", "raise", "abort", "__assert_fail",
             "llvm::report_fatal_error", "llvm::llvm_unreachable_internal")
```

or a frame with **no** resolved function whose module is libc. Measured on the real trace of §3.6.2,
the strip removes exactly four frames and the strip is what the numbers below are taken after:

```
frames: 466   after prologue strip: 462
dropped: ['llvm::sys::PrintStackTrace', 'llvm::sys::RunSignalHandlers', 'SignalHandler', '(libc)']
top-5 raw   : ['llvm::sys::PrintStackTrace', 'llvm::sys::RunSignalHandlers', 'SignalHandler',
               '', 'mlir::Lexer::lexToken']
top-5 strip : ['mlir::Lexer::lexToken', 'mlir::detail::Parser::parseToken',
               'mlir::detail::AsmParserImpl<mlir::DialectAsmParser>::parseLess',
               'circt::hw::ArrayType::parse', 'operator']
```

Three of the five raw slots were constant across every crash the campaign can produce, and for a
`fatal_error`, whose prologue is deeper, all five were, so **every `fatal_error` in the campaign would
have fingerprinted identically** and G-44's "distinct" would have collapsed.

**For a `crash` or a `fatal_error`**, the primary fingerprint is therefore **not** the top-N tuple.
It is

```
f"{signal_name}\n{fingerprint_frame}"
```

where `signal_name` is `BuildResult.signal` (`SIGSEGV`, `SIGABRT`, and so on; `SIGABRT` for a
`fatal_error`) and `fingerprint_frame` is the first frame, **after the strip**, that is in a CIRCT
object with a resolved line, written as its normalised function name and the **basename** of its file
with **no line number**, so a one-line edit inside the same function does not split one bug into two
across runs. A frame whose normalised function name is empty or the degenerate `operator` (what a
lambda reduces to under step 2 below) is skipped, so the name in a fingerprint is always a real
function. Where no stripped frame qualifies, the basis falls back to the top-N tuple of normalised
names, `"\n".join(frame_names[:top_n])`, with `top_n` from `budget.yaml`'s `fingerprint_top_n`, and
where fewer than `top_n` frames resolve at all the basis is `insufficient` (FR-10.8). The top-N tuple
is recorded as `Fingerprint.frame_tuple` evidence in every case, which is what FR-10.1 asks for.

**This is measured, and the measurement is not flattering to either rule.** Ten runs of the *same*
input on the *same* binary, the `!hw.array` stack overflow of §3.6.2:

```
primary fingerprint frame over 10 runs:
    5 x ('parseHWArray', 'HWTypes.cpp')
    3 x ('circt::hw::ArrayType::parse', 'HWTypes.cpp.inc')
    2 x ('generatedTypeParser', 'HWTypes.cpp.inc')
top-5 stripped tuple over 10 runs: 9 distinct
```

Nine distinct top-5 tuples against three distinct fingerprint frames: the new rule is three times
more stable and is still not stable, because a stack overflow hits its guard page at a different point
in the recursion cycle each run and the three names are three adjacent frames of one cycle. The design
does not pretend otherwise. Every candidate carries `Fingerprint.fingerprint_stable`, set by the
gate's question-1 re-run (§3.9) to whether the re-run produced the same fingerprint string, and **an
unstable fingerprint is reported, never merged**: such a candidate is not partitioned with any other,
`results.py` prints the count of unstable fingerprints beside the headline, and FR-10.2's
false-merge rate is measured against the labelled set with that flag visible. A rule that silently
merged three runs of one stack overflow into three bugs, or three different bugs into one, is the
failure FR-18.3's headline cannot survive; a rule that says which candidates it cannot fingerprint
stably is one a reader can price.

A frame's function name is normalised by:

1. taking `llvm-symbolizer`'s `FunctionName`, which under the default `--functions=linkage` is the
   demangled name including its parameter list (measured: `circt::chooseName(llvm::StringRef,
   llvm::StringRef)`);
2. cutting everything from the first `(` that is at bracket depth zero, which removes the parameter
   list;
3. stripping a trailing ` const`;
4. collapsing whitespace.

`--functions=short` is **not** used, although it would do step 2 for us: measured on the
assertions-on build, it returns `??` under `-gline-tables-only`, because a short name needs debug
information the flag does not emit. That is a real trap and it is recorded rather than left to be
rediscovered.

The trade-off of step 2 is stated rather than hidden: two overloads of one function fingerprint
alike, so a crash in each counts once. That is the direction G-43 chooses, "frame function names",
and it errs towards merging, which costs a report rather than producing a wrong filing.

**When there is no fingerprint**, which is a candidate with no assertion text, no qualifying stripped
CIRCT frame and fewer than `top_n` resolvable frames, `basis` is `insufficient`, `value` is `None`,
the candidate deduplicates against nothing, and it fails gate question 4 with that reason (FR-10.8).
Its structural hash is still recorded as evidence and still merges nothing.

**The structural hash**, the second evidence field, is `hashlib.sha256` over the reduced case's text
with every SSA value name (`%[A-Za-z0-9_$.-]+`), every **symbol name** (`@[A-Za-z0-9_$.-]+`), every
location suffix (`loc(...)`) and every run of whitespace normalised, hex-digested. It is recorded on
every candidate and is never the fingerprint (FR-10.1, FR-10.2). Symbol names are normalised because
`circt-reduce` renames modules during reduction (observed by the LLD review:
`hw.module @top` became `hw.module private @Foo`), so without it the same reduced case hashed
differently depending on how far the reducer got (NIT 9). The other half of that observation,
§4.6's `--jit-entry=bugloop_main`, is unaffected: the harness the differential oracle generates is
never reduced, because FR-09.8 keeps a `differential` candidate out of stage 5 entirely, so no
renamed module ever reaches `arcilator --jit-entry`.

**The partition** is `itertools.groupby` over candidates sorted by fingerprint. Two candidates are
duplicates if and only if their fingerprints are equal as strings; equality is reflexive, symmetric
and transitive, so the partition does not depend on the order candidates arrive in, which FR-10.2's
own test asserts.

#### 3.7.2 The two commit scans

One scanner, two windows and two match levels, because the difference is a bound and a match level
and not an algorithm (`02-HLD.md` §1.3).

| Screen | Lower bound | Upper bound | Match level | Requirement |
|---|---|---|---|---|
| post-pin fix | `candidate.run_commit` | clone head | **file**: a later commit touches a source file named in the frames, or the file of the assertion site | FR-10.4 |
| contamination | the seed's `committed_date_utc`, or `candidate.run_commit` for the 16 non-exact seeds | clone head | **symbol**: a later commit's diff touches a function named in the frames, or the function of the assertion site | FR-15.1, FR-15.5 |

**The bound is `candidate.run_commit` and never `manifest.run_commit[0].commit`** (K14). FR-02.7 makes
`RunManifest.run_commit` a **list**, one entry per calibrated seed in calibration mode, so index 0 is
an arbitrary sampled seed's commit and is this candidate's only by accident. `CandidateRecord` carries
the right value per candidate and every reader uses it: this table, §3.8's restore, §3.9's question 1
and §4.8's three checks. `tests/test_triage_task.py` and `tests/test_gate.py` each build a
calibration manifest with two entries and assert that a candidate from the second seed scans from its
own commit.

Both are served by one command, which is the command the M4 measurement used:

```
git -C <clone> log --first-parent -p --unified=0 --no-renames \
    --format=__C__ %H %cI --since <lower bound> -- <the candidate's source paths>
```

Symbol level reads the identifier git puts in the `@@ ... @@ <context>` hunk header, which is the
precise rule; the crude `\b(\w+)\s*\(` rule over `+`/`-` lines is **not** used, and the difference is
measured: 77.0% against 79.1% flagged over the corpus (M4). File level is used for FR-10.4 and only
there, because its window is the lag, at most 100 commits and 16.1 days, where over-inclusiveness is
cheap and deliberate; over FR-15.1's 24 months, file level flags 96.3% of seeds against symbol
level's 77.0%, and a near-constant cannot change what a number means.

`contamination_lower_bound` records which bound was used, so the 16 non-exact seeds stay
distinguishable from the rest in the results (FR-15.5).

#### 3.7.3 The issue-mirror screen, which decides `known_open_issue` and `known_closed_issue`

FR-10.3 requires a screen against CIRCT's open and closed issues "for a match on the candidate's
assertion text and its reduced case's distinctive tokens", reading the local mirror of FR-10.9. The
earlier draft named the two verdicts in a `Literal` and never said how either was reached, which left
two of `DedupVerdict`'s six values unreachable, FR-10.3 unimplemented, FR-13.9's `good first issue`
refusal without a producer, and F-10's own feature acceptance unpassable (K7). It is defined here and
nowhere else.

**The tokens**, per oracle class, and nothing else is a token:

| Class | Tokens |
|---|---|
| `assertion` | the `expr` string exactly as `assertion_text` records it, and the `file:line` exactly as `assertion_site` records it. Two tokens. |
| `crash` | the fingerprint frame's **function name** (§3.7.1), without its file. One token. |
| `fatal_error` | the fingerprint frame's function name, **and** the `LLVM ERROR:` message, that is `fatal_message` verbatim. Two tokens. |
| `differential` | none. A `differential` candidate never reaches this stage (FR-08.10). |

A token shorter than 8 characters `[DEFAULT]` (`MIRROR_TOKEN_MIN_CHARS`, §9.4) is dropped, because
`fold` or `parse` alone would match hundreds of issues and the screen would answer `known_issue` for
every candidate.

**The match** is a case-sensitive substring test over the concatenation of the mirrored title and
body, evaluated in SQLite with `instr`, one query per candidate:

```sql
SELECT issue_number, state, url, labels_json
  FROM issue_mirror
 WHERE instr(title || ' ' || body, :token) > 0
 ORDER BY issue_number
```

run once per token, with **any token matching any issue** producing a hit. The verdict is
`known_open_issue` when the matched issue's `state` is `open` and `known_closed_issue` when it is
`closed`; where tokens match issues in both states the open one wins, because an open issue is the
one a maintainer would be told about twice. `DedupVerdict.evidence` carries `matched_token`,
`issue_number`, `issue_url`, `issue_state` and `issue_labels`, which is what FR-13.9's refusal reads
and what the rendered report shows.

**It is over-inclusive by design and the design says so.** A substring test over an issue body will
match text a maintainer pasted from an unrelated build log, and there is no scoring, no threshold and
no similarity measure anywhere in it, deliberately: FR-10.2 fixes one equivalence relation for
candidate-to-candidate duplicates and this screen is not it, a false match costs a report rather than
a wrong filing, and the human at the gate sees the matched token and the issue number in the evidence
and can overrule by declining. `04-Test-Plan.md` owns F-10's acceptance, which is that at least one
candidate seeded from a known closed CIRCT issue comes back `known_closed_issue` with that number.

**Cost and index.** `issue_mirror_issue_cap` is 20,000, so the table is at most 20,000 rows and a
scan of it is a few milliseconds; `instr` cannot use an index, so §6.3 adds none for this query and
says why. The screen makes **no** GitHub request, which is FR-10.3's network-trace criterion: B6a is
the only writer of the table and it runs once per run, before the first candidate is screened.

#### 3.7.4 B7, the triage turn and the report render

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def triage_report(candidate: CandidateRecord, reduced: ReducedCase,
                  verdict: OracleVerdict, dedup: DedupVerdict,
                  manifest: RunManifest, cfg: dict, artefact_dir: str) -> dict:
    """Classify one candidate advisorily and render the report a maintainer reads.

    Returns:
        {"report": Report, "logs": dict, "failure": str | None}
    Worker:
        {"circt": 1} for the node; the one turn at {"llm": 1.0}.
    Raises:
        nothing. A failed turn yields classification "untriaged" and an empty
        report; the candidate still receives four mechanical gate answers and is
        held with held_reason=no_report if it passes (FR-11.8).
    """
```

Two rules make the output safe to report.

- **The tool verdict wins.** A candidate whose `DedupVerdict` is `known_open_issue`,
  `known_closed_issue` or `fixed_post_pin` is classified `known_issue` whatever the agent wrote; the
  agent's only freedom is the reason text (FR-11.2).
- **No number the agent produced reaches the report.** The agent returns prose fields only (§7.3);
  every count, size, time, hash, SHA and verdict in the rendered `report.md` is substituted from the
  record by

  ```python
  def render_report(template: Literal["primary", "differential"],
                    candidate: CandidateRecord, reduced: ReducedCase | None,
                    verdict: OracleVerdict | None, differential: DifferentialVerdict | None,
                    dedup: DedupVerdict | None, manifest: RunManifest,
                    prose: dict) -> str:
      """Render one report.md from the record, substituting every number itself.

      Returns:
          the rendered markdown; the caller writes it and hashes it.
      Worker:
          pure; it is called inside B7 and runs no process.
      Raises:
          ReportIncomplete(point) when any substitution point of 7.4.1 that the
          chosen template declares is absent from the record (FR-11.3).
      """
  ```

  whose substitution points are enumerated in §7.4.1 and asserted field by field by
  `tests/test_triage_task.py` (FR-11.4). A `differential` candidate is rendered with the second
  template, which has no expected-behaviour field at all (FR-08.6, FR-11.9), and is the one call that
  passes `differential` non-`None` and `verdict`, `reduced` and `dedup` all `None` (W23).

The classification reason is capped at **4 sentences** `[DEFAULT]`, an implementation constant fixed
here (FR-11.1), counted by splitting on `.`, `!` and `?` followed by whitespace or end of string, and
truncated rather than rejected, with the truncation recorded.

**B7's turn is §3.5.1's turn** (2026-09-14). It calls `generate_task.build_llm` with stage 6's
timeout and `cfg["model_id"]`, dispatches through `generate_task.llm_turn`, gets exactly one tool,
`SourceReadTool`, and stops it in a `finally` as A3 does. It therefore inherits the interlock, the
express-mode construction and the usage capture with no code of its own, which is why
`build_llm` and `llm_turn` live in one module and are imported rather than repeated.
`Report.assisted_by` reads `manifest.model_ids["triage_report"]`, which is already spelled
`"<backend>:<model id>"` (§2.7), so §7.4's `Assisted-by:` trailer is that value verbatim rather than
two fields joined at render time.

### 3.8 `repair_adapter.py` (B8, F-12)

```python
@ChiaFunction(resources={"repair": 1}, max_retries=0)
def repair_adapt(report: Report, candidate: CandidateRecord, reduced: ReducedCase,
                 verdict: OracleVerdict, manifest: RunManifest, cfg: dict) -> RepairResult:
    """Present one local report to CHIA's unmodified chain, then restore the worker.

    Returns:
        RepairResult, for every one of CHIA's six statuses, with the failing
        phase named, plus the post-attempt restore result.
    Worker:
        {"repair": 1} - its own worker type, because the chain rebuilds with the
        agent's diff applied and returns without restoring (FR-12.11).
    Raises:
        RepairRefused(reason) for a candidate refused by class or scope, before
        the chain is invoked at all. The caller records the reason and counts it.
        LiveModelRefused when the interlock of 3.5.1 is not set, or when the
        repair backend is vertex and GEMINI_API_KEY is unusable. Checked here
        because CHIA's _turn builds its own backend and cannot carry the loop's
        refusal (3.5.1, 2026-09-14). The caller stops the run.
    """
```

**The refusals come first**, and none of them invokes the chain: `oracle_class` of `differential`
(FR-08.10) or `fatal_error` (FR-12.4), or `out_of_scope_root` true (FR-12.5). Only `crash` and
`assertion` proceed.

**Then the interlock, added 2026-09-14 with the `vertex` branch** (§3.5.1). CHIA's `_turn` builds its
own backend inside CHIA's file, which cannot carry the loop's refusal, so the adapter carries it:

```python
    generate_task.require_live_model(
        f"stage 7 repair of {candidate.candidate_id}",
        need_key=(cfg["repair_backend"] == generate_task.MODEL_BACKEND))
```

unconditionally, before the `cfg` is built and before `run_issue_remote` is called. The gate half,
`BUGLOOP_ALLOW_LIVE_MODEL == "1"`, is checked on **every** repair backend, because the user's rule is
that no live model request of any kind is made before the tiers are green; the key half is checked
only when the repair backend is `vertex`, a `claude` fallback having its own credential and no use for
`GEMINI_API_KEY`. Without this call stage 7 would be the one path to a model that the interlock of
§3.5.1 does not cover, and `--no-repair` would be the only thing standing between an ungreen tree and
a real request. `LiveModelRefused` propagates to B12, which stops the run.

**The synthetic local identifier.** FR-12.2 requires an integer from a declared range disjoint from
GitHub issue numbers, and requires this document to fix the range. It is

```python
LOCAL_ID_BASE = 900_000_000          # [DEFAULT], an implementation constant
LOCAL_ID_MAX  = 999_999_999          # RunManifest.local_id_range = [900000000, 999999999]
```

and a candidate's identifier is `LOCAL_ID_BASE + <its rowid in loop.db's candidate table>`, which is
unique by construction, monotonic, and reproducible from the store. The floor is chosen against the
tracker's own scale: `llvm/circt`'s issue numbers are five digits in 2026 (CHIA's own README works an
example at `--issue 10588`, `chia:examples/circt_issue_solver/fix_issues_submit.sh:14`), GitHub issue numbers
are monotonic per repository, and nine hundred million is four orders of magnitude beyond the
tracker's reach. `tests/test_repair_adapter.py` asserts disjointness against every key in the
existing `issues.db`, which is FR-12.2's own criterion.

**The `GithubIssue`-shaped object.** `db.record` reads `issue.number`, `issue.title` and `issue.url`
off a dataclass with eleven required fields (`chia:examples/circt_issue_solver/db.py:99-111`;
`chia:chia/github/state_def.py:11-24`), and `run_issue_remote` takes `issue_md: str` and
`number: int` (`chia:examples/circt_issue_solver/issue_task.py:39`). The adapter constructs the whole
object, not a string and an integer:

```python
def _as_github_issue(report: Report, candidate: CandidateRecord, local_id: int) -> GithubIssue:
    """Build the GithubIssue-shaped object CHIA's chain and db both read.

    Every one of state_def.GithubIssue's eleven required fields is populated.
    comments is left at its default empty list, which is the only field with a
    default and the only one no CHIA caller reads for this flow.
    """
    return GithubIssue(
        number=local_id,
        title=report.title,
        state="open",
        author="circt_bug_loop",
        created_at=candidate_created_at_utc,
        updated_at=candidate_created_at_utc,
        closed_at=None,
        body=open(report.path).read(),
        labels=["circt-bug-loop", f"arm:{candidate.arm}"],
        url=f"local://circt_bug_loop/{candidate.run_manifest_id}/{candidate.candidate_id}",
        is_pull_request=False,
    )
```

`url` is a `local://` URI and not an `https://` one, deliberately: it is written into CHIA's
`issues.db` and into artefacts, and a plausible-looking GitHub URL for an issue that does not exist
is the kind of thing that later gets pasted somewhere.

**The whole `cfg` dict, because a typist cannot call the chain without it** (W1). `run_issue_remote`
reads sixteen keys, ten values and six prompt bodies, grepped from `issue_task.py` and assembled in
`circt_issue_loop.py:84-96`. The adapter builds every one:

| Key | Value the adapter passes | Why |
|---|---|---|
| `tag` | `candidate.run_commit` | FR-12.6's AC is that `cfg["tag"]` **is** the run's commit; the chain resets to it (`issue_task.py:149`) and `circt_capture_diff` takes the diff against it. `CandidateRecord.run_commit`, not `manifest.run_commit[0]` (K14). |
| `tool_targets` | `tuple(manifest.image_spec["targets"])` | the six FR-03.7 targets, so the chain's warm build and its verify rebuild the same set B1 baked. |
| `repro_dir` | `<artefact_root>/<run>/repair/<local_id>/` | **outside `/workspace/circt`**; see below. |
| `repro_path` | `<repro_dir>/repro.sh` | the same directory; CHIA reads it at `issue_task.py:203`, `207` and `226`. |
| `require_repro` | `True` | so a case that no longer reproduces on the clean tree returns `no_repro` instead of being fixed by accident. |
| `backend` | `cfg["repair_backend"]`, which **defaults to `"vertex"`** and therefore equals `manifest.backend` on a default run (2026-09-14, §13.1) | the chain now implements `vertex` too, by the one additive branch below. The key stays a separate name rather than being wired to `manifest.backend` so that `--repair-backend claude` remains a one-flag fallback for a Vertex outage without a code path of its own. ~~CHIA's chain implements `antigravity`, `opencode` and `claude` and nothing else, so handing it `manifest.backend`, which is `vertex`, would silently build a `ClaudeCodeLLM`~~ is **withdrawn 2026-09-14**. |
| `model` | the model-id half of `manifest.model_ids["repair_adapt"]`, whose backend half equals `cfg["repair_backend"]`; on a default run that pair is **`vertex:gemini-3.8-flash`**, so the value passed is `"gemini-3.8-flash"`, `budget.yaml`'s own `model_id` | the chain takes a bare model id; the manifest keeps the pair (§2.7). |
| `vertex` | `{"project": os.environ.get("GOOGLE_CLOUD_PROJECT"), "location": "global"}` | read only on the `opencode` backend (`circt_issue_loop.py:71-72`); §13.3 forwards the variable. The **`vertex` backend** does not read this key at all: express mode takes an API key and no project and no location, and the branch below nulls both. |
| `build_jobs` | `BUILD_JOBS`, 16 `[DEFAULT]`, §9.4 | CHIA's own value, and the `--cpus=8` of `bugloop_repair` bounds it. |
| `timeouts` | `PHASE_TIMEOUTS`, §9.4, CHIA's five verbatim | FR-12.1: the chain's own timings are not the loop's to change. |
| `system_prompt`, `assess_prompt`, `repro_prompt`, `fix_prompt`, `regression_prompt`, `writeup_prompt` | `(_ISSUE_SOLVER / "prompts" / f"{n}.md").read_text()` for the six names | read from **CHIA's own directory**, so FR-12.9's byte comparison is of the file the adapter actually passed. |

**Stage 7 runs on the campaign backend, by one additive branch** (2026-09-14, `02-HLD.md` §0.3,
`01-FRD.md` §1.9; this supersedes `02-HLD.md` §0.2 fact 3 in full). `run_issue_remote`'s `_turn` reads
`backend = cfg.get("backend", "claude")` and branched to `AntigravityLLM`, `OpenCodeLLM` or
`ClaudeCodeLLM` and nothing else (`chia:examples/circt_issue_solver/issue_task.py:81-123`): there was
no `vertex` arm and there is no hook to supply an LLM object, so `cfg["backend"] = "vertex"` fell
through to the Claude CLI silently. ~~FR-12.1 pins the file byte for byte, so the loop may not add
one~~ is **withdrawn**: FR-12.1's acceptance is now hunk equality, and the loop adds the fourth arm.

**The patch, in full.** It lives at `upstream/issue_task-vertex-branch.patch` (§1.4), is applied by
`upstream/sync-to-chia.sh` into the CHIA checkout, and is proposed upstream as part of the pull
request of §14.6. It inserts nineteen lines between the `opencode` arm and the `else`, and deletes
and alters nothing:

```diff
--- a/examples/circt_issue_solver/issue_task.py
+++ b/examples/circt_issue_solver/issue_task.py
@@ -114,6 +114,25 @@
                 timeout_seconds=cfg["timeouts"][phase],
                 additional_providers=[gemini], config=perms,
             )
+        elif backend == "vertex":
+            # chia.models.vertex: Gemini on Vertex AI in EXPRESS mode, which takes
+            # an API key and NO project and NO location. The constructor defaults
+            # location to "us-central1" and project to $GOOGLE_CLOUD_PROJECT, and
+            # google-genai raises ValueError("Project/location and API key are
+            # mutually exclusive in the client initializer.") on that pair, so
+            # both are nulled after construction. http_options.timeout is in
+            # MILLISECONDS and is the only thing that bounds the request:
+            # VertexGeminiLLM stores timeout_seconds and never reads it again.
+            from chia.models.vertex import VertexGeminiLLM
+            llm = VertexGeminiLLM(
+                model=cfg["model"], system_message=cfg["system_prompt"],
+                timeout_seconds=cfg["timeouts"][phase],
+                client_kwargs={"api_key": os.environ["GEMINI_API_KEY"],
+                               "http_options": {
+                                   "timeout": cfg["timeouts"][phase] * 1000}},
+            )
+            llm.project = None
+            llm.location = None
         else:
             llm = ClaudeCodeLLM(
                 model=cfg["model"], system_message=cfg["system_prompt"],
```

Five things about it, each checkable. **It is additive**: `git diff` against `16c35e92` is one hunk,
19 insertions, 0 deletions, verified 2026-09-14 with `git apply --check`, `git apply`, `ast.parse` on
the result and `git diff --stat`. **It is unreachable for CHIA**: `_turn` selects on a string, CHIA's
own driver sets `CFG["backend"]` only from `BACKEND_DEFAULT_MODEL`, whose keys are exactly `claude`,
`antigravity` and `opencode` (`chia:examples/circt_issue_solver/circt_issue_loop.py:74`, `193`), and
its `--backend` flag takes `choices=sorted(BACKEND_DEFAULT_MODEL)` (`circt_issue_loop.py:176`), so
`"vertex"` is not a value any CHIA caller can produce and CHIA's behaviour on every backend it already
has is bit-for-bit what it was. **It needs no new import at module scope**:
`os` is already imported (`issue_task.py:12`) and `VertexGeminiLLM` is imported inside the branch,
matching the two branches above it. **It carries the express-mode fix**, `llm.project = None` and
`llm.location = None`, which is the same two-line work-around `generate_task.build_llm` uses (§3.5.1)
and which `02-HLD.md` §0.2 fact 1 measured. **And the `http_options` timeout is the only bound that
bites**, for the reason §3.5.1 gives: `VertexGeminiLLM` stores `timeout_seconds` and never reads it,
so the milliseconds value is what holds the phase to `cfg["timeouts"][phase]`. The five phase
timeouts are CHIA's own and unchanged (`PHASE_TIMEOUTS`, §9.4).

Four consequences, all recorded:

1. `cfg["repair_backend"]` is a **named** value, defaulting to **`vertex`** since 2026-09-14, and
   `bug_loop.py --repair-backend` sets it (§13.1). It is no longer a second backend on a default run;
   it is the outage fallback, and `--arm`, the prompts, the gate and the ledger are all unaware of it
   either way.
2. `RunManifest.model_ids["repair_adapt"]` records `"<that backend>:<that model id>"`, which on a
   default run is **`vertex:gemini-3.8-flash`**, equal to the other three. The spelling stays a pair
   so that a fallback run still shows the difference as a value a reader can see.
3. `RunManifest.stages_metered["stage_7"]` is **true** by default, the two backends no longer
   differing. The rule is unchanged, FR-14.8's "false whenever they differ" still holds, and
   `results.py` prints the repair stage's spend as unmetered only on a fallback run.
4. The campaign may still be run with `--no-repair`, in which case F-12's rows are empty with
   `repair_disabled` as the stated reason and no gate answer changes: the gate's four questions read
   no repair field (§3.9).

**Stage 7's tokens are not captured, and this is the honest statement of why** (FR-14.6, §1.9). The
branch builds the backend; it does not change how the turn is dispatched. `_turn` line 124 is
`cli = get(llm.prompt.options(resources={"llm": 1.0}).chia_remote(llm, prompt, tools))`, which
serialises the LLM object through the Ray trampoline (`chia:chia/base/ChiaFunction.py:172-212`,
`228-273`), and `VertexGeminiLLM` accumulates `usage_metadata.prompt_token_count` and
`candidates_token_count` into `self._last_metadata` **on that object**
(`chia:chia/models/vertex.py:479-482`, `579`) rather than onto the returned `QueryResult`, whose five
fields carry no usage (`chia:chia/base/llm_call.py:15-35`). The copy that learns the counts is the
worker's and dies with the task. §3.5.1's `llm_turn` is the fix for the loop's own stages and it is a
**call-site** change: it calls `prompt` directly and reads `_last_metadata` in the process that wrote
it. Line 124 is not in the branch, and editing it would make FR-12.1's hunk-equality acceptance false,
so **the `_last_metadata` route is not reachable for stage 7 without a further edit to CHIA's file**.
Nor is there a second source: `logs[phase]["usage"]` is `getattr(cli, "usage", None)`
(`issue_task.py:134`), which is `None` for a plain `QueryResult`; `circt_issue_loop._persist` writes
`llm_usage` only where that is truthy (`circt_issue_loop.py:132-136`), so the key is simply absent;
and the backend's `stream_result` logs the user message, thinking, responses and tool results and
**no token line** (`chia:chia/models/vertex.py:414-420`, `510-517`, `565`, `574`, `581`), so nothing
can be parsed back out of it. Therefore:

```python
    # repair_adapter.py, when the stage-7 LedgerEntry is accrued
    observed = {"cpu_seconds": elapsed,
                "tokens_in": None, "tokens_out": None, "cost_usd": None}
    # and, on the loop's own object, not on the contract's:
    result.token_capture = "unavailable_remote_dispatch"
```

`LedgerEntry.observed` for stage 7 carries **null** tokens and **null** `cost_usd`, `metered` true,
and `results.py` prints the campaign's USD total as a **lower bound that excludes stage 7** (§14.4).
**The contract is unchanged and stays at 2.0, and the reason lives off it deliberately**:
`_DICT_KEYS[("LedgerEntry", "observed")]` is exactly `cpu_seconds`, `tokens_in`, `tokens_out` and
`cost_usd` (§2.6), an extra key fails validation as loudly as a missing one, and §2.2's rule makes
removing or adding a declared key a **MAJOR** bump to 3.0, which would invalidate every committed
fixture for a diagnostic string. `token_capture` is therefore a field of **`RepairResult`** (§2.9),
which is one of the apparatus-internal records in `store.py` and not a member of the seven-schema
seam of §2.4. Recording zero instead of
null would be worse than either, because zero is a number a reader will add up.

**A second patch would close it, and is not taken.** Changing line 124 to
`cli = llm.prompt(user_message, tools)` plus a `_last_metadata` read would capture the counts, and it
is not proposed, for two reasons and not one: it would make the diff two hunks including a
**deletion**, which is the thing FR-12.1's new acceptance exists to forbid; and it would change
CHIA's behaviour for all four backends, moving the turn off the `llm` worker and into the caller's
process, which is a scheduling change CHIA's own example depends on. The observability gap is
cheaper than that, it is bounded by `--no-repair`, and it is written down.

**B8 calls the chain inline, not through `chia_remote`** (W2). `run_issue_remote` carries its own
`@ChiaFunction(resources={"circt": 1})` (`chia:examples/circt_issue_solver/issue_task.py:38`), and
CHIA's own driver dispatches it (`circt_issue_loop.py:250-252`), which would land it on a `circt`
worker and defeat the whole reason `bugloop_repair` exists. A `@ChiaFunction` called directly "just
runs in the caller's own process and isn't a node"
(`chia:docs/concepts/overview.rst:36-37`), so the adapter writes

```python
    result = run_issue_remote(issue_md, local_id, cfg)
```

and the chain runs on the `repair:1` worker B8 is already on. The `here` scheduling strategy the chain
builds for its own tools (`issue_task.py:67-68`) is then that worker's node id, so the `BashTool`,
`BuildTool` and `LitTool` it stands up land there too, which is exactly what FR-12.11 requires.
`tests/test_repair_adapter.py` asserts the call site is the bare name and not `.chia_remote`.

**The pre-written repro, and why `resume` cannot carry it** (K9, W3). FR-12.3 requires the reduced
case and a `repro.sh` to be in place before the chain starts. Two facts decide how.

First, **`resume` is the wrong shape.** `01-FRD.md` §4.1 pointed at `--replay-regression` as the
nearer model, and it is not: `run_issue_remote(issue_md, number, cfg, resume=...)` takes
`{"diff": <saved fix.diff>, "repro_files": {relpath: content}}`, restores the repro, **re-applies a
diff**, and jumps straight to verify, skipping assess, reproduce **and fix**
(`chia:examples/circt_issue_solver/issue_task.py:39-56` for the contract, `178-190` for the body,
where `circt_apply_diff` returns `status: "error"` on an empty or failing diff). F-12 needs the fix
turn to run; there is no `resume` shape that skips only the reproduce turn.

Second, **CHIA's default `repro_dir` is deleted by the chain's own first action.** It is
`/workspace/circt/.circtissues` in every CHIA caller
(`chia:examples/circt_issue_solver/circt_issue_loop.py:46`), that directory is untracked, and CIRCT's
`.gitignore` at `b792c772` lists `/build*`, `/install*`, `/ext`, `obj_dir/`, `__pycache__`,
`lit.site.cfg.py` and the `llvm/` subproject paths and nothing matching `.circtissues`, so
`git clean -fd` at `issue_task.py:149` removes it.

So the adapter puts the repro directory **outside the CIRCT tree**, under the artefact root, which
`git clean` cannot reach and which §12.1 bind-mounts at the identical path on the repair worker:

```python
    repro_dir = f"{manifest.artefact_root}/{manifest.run_manifest_id}/repair/{local_id}"
    circt_util.circt_write_files({"repro.sh": script_text,
                                  f"case{ext}": reduced_text}, repro_dir)
```

`circt_write_files` is CHIA's own writer and chmods `.sh` files to 0755
(`chia:examples/circt_issue_solver/circt_util.py:107-123`). Nothing in `issue_task.py` requires
`repro_dir` to be inside the tree: it is read at four points and every one is `cfg["repro_dir"]` or
`cfg["repro_path"]`. `issue_task.py` is therefore untouched **by this** (its only change is the
additive `vertex` arm of §3.8, which is elsewhere in the file and in `_turn`), and all six prompts
stay byte-identical (FR-12.1, FR-12.9).

That leaves one honest gap and the design states it rather than hiding it. The reproduce turn still
runs, and its prompt tells the agent to write `<repro_path>` itself (`issue_task.py:202`), so the
agent **may** overwrite the loop's script. The prompt cannot be edited, but the **issue body can**,
because the body is the loop's own `report.md`: it names the absolute path of the pre-written script,
quotes it, and says its job is to confirm rather than invent. The adapter then measures what happened
instead of assuming it: it takes `hashlib.sha256` of `repro.sh` before the chain and again after the
reproduce turn's `circt_run_script` has run, and records `RepairResult.repro_overwritten`. FR-12.3's
"confirms rather than invents" is thereby **reported per attempt rather than guaranteed**, and
`results.py` prints the count; the polarity half of FR-12.3 is guaranteed, because `require_repro` is
`True` and the first `circt_run_script` on the clean tree must exit non-zero for the chain to
continue at all.

The script's polarity is the one FR-12.3 fixes and is not the naive one: exit 0 if and only if the
tool run terminates **without** a crash signal, without an assertion or `UNREACHABLE executed`
message, and without an `LLVM ERROR:` abort, regardless of the tool's own exit status, so that a fix
which turns a crash into a proper diagnostic scores as fixed. §10.2's template is the interestingness
script and is a different file with a different polarity; `repro.sh` is its inverse and §10.2 says so.

**The restore, after every attempt, whatever the outcome** (FR-12.11):

```python
    reset = circt_util.circt_git_reset(candidate.run_commit)
    build = circt_util.circt_ninja_build(tuple(manifest.image_spec["targets"]),
                                         num_cpus=cfg["build_jobs"])
    after = {t: _sha256(f"/workspace/circt/build/bin/{t}")
             for t in manifest.image_spec["targets"]}
    restore_hashes_match = after == manifest.image_spec["tool_hashes"]
    restore_ok = bool(reset["success"] and build["success"] and restore_hashes_match)
```

The reset commit is `candidate.run_commit` (K14). The first two calls are CHIA's own functions
(`chia:examples/circt_issue_solver/circt_util.py:54-77`; `chia:chia/chipyard/circt.py:616-658`); the
third is the loop's and is new in this revision (W21). FR-12.11's acceptance criterion is "after one
full repair attempt on a worker, the SHA-256 of every tool binary on it matches the `ImageSpec` map of
FR-03.16, asserted by re-hashing them", and a successful `ninja` is not evidence of bit-identity: the
`ImageSpec` hashes are computed from a freshly started container (§5.2) while the restore rebuilds
locally, so whether a revert-and-rebuild reproduces the published binaries byte for byte is
**`[UNVERIFIED]`** and is listed in §15. Doing the comparison is what makes the answer a recorded fact
rather than an assumption, and `restore_hashes_match` is the field that carries it. A worker whose
restore fails, for any of the three reasons, is recorded `repair_worker_dirty` and is not used again
in that run, and B8 is disabled for the rest of the run, which costs repair attempts and no verdicts.
If the hash comparison turns out to fail routinely because the rebuild is not reproducible, the
recorded consequence is that the repair worker is single-use per run; that is a cost the campaign can
pay and a silent mismatch is not.

**The write order** is fixed by FR-12.10: the loop's row is written **first**, carrying the local
identifier; CHIA's row follows from CHIA's own unmodified code; B12's end-of-run reconciliation marks
a loop row whose CHIA counterpart never appeared as `repair_row_missing`. That ordering exists
because `SQLiteNode` opens a fresh connection per `chia_remote` call
(`chia:chia/database/sqlite_node.py:21-27`), so one transaction cannot span two database files.

### 3.9 `gate.py` and `approve.py` (B9a, B9b, B9c; F-13, F-20)

```python
@ChiaFunction(max_retries=0)
def gate_decide(candidate: CandidateRecord, reduced: ReducedCase, dedup: DedupVerdict,
                repair: RepairResult | None, manifest: RunManifest,
                db_path: str) -> GateDecision:
    """Ask the four mechanical questions in order and stop at the first no.

    Returns:
        GateDecision, defaulting to "nothing" for any unanswered question.
    Worker:
        head - and it holds NO circt resource, so it can never occupy a slot
        while waiting for one (02-HLD.md 3).
    Raises:
        nothing. Every refusal is a recorded answer, not an exception.
    """
```

The four questions, each answered by a tool and none by a model (FR-13.1, NFR-03):

1. **Does it reproduce at `candidate.run_commit`?** `gate_decide` dispatches `gate_rerun` as a task of
   its own and compares class, assertion text and `file:line`. It enumerates live `circt` node ids
   from `ray.nodes()` filtered to `Alive`, which is CHIA's own way of doing exactly this
   (`chia:chia/base/dispatch_proxy.py:84-97`), and dispatches with
   `NodeAffinitySchedulingStrategy(node_id=<a node other than the original>, soft=True)`. The pin is
   **soft**, so where the preferred node is busy or gone the re-run still happens and
   `same_worker=True` is recorded truthfully (FR-13.2, as amended).

   **"The original" is a recorded value, not an inferred one** (K12). `BuildResult` carries
   `worker_hostname`, `worker_node_id` and `child_pid`, written by `probe_execute` from
   `socket.gethostname()`, `ray.get_runtime_context().get_node_id()` and the child's own pid; §6.2's
   `build_result` table has the three columns. `gate_decide` reads them to fill
   `q1_original_worker`, `q1_original_pid` and to choose a preferred node id, and `gate_rerun`'s
   return fills `q1_rerun_worker` and `q1_rerun_pid`; `q1_same_worker` is
   `original_node_id == rerun_node_id`, which is now computable. Without those three fields FR-13.2's
   "the worker identity, hostname together with Ray node id, and the process id are recorded for
   **both** runs" was unsatisfiable and the soft anti-affinity had no "other" to avoid.

   The re-run also sets **`Fingerprint.fingerprint_stable`**: it recomputes the fingerprint from the
   re-run's own stderr by §3.7.1's rule and compares the string. `False` does not fail question 1,
   which asks only whether the recorded failure reproduces; it is recorded, printed beside the
   headline, and keeps the candidate out of every partition (§3.7.1).
2. **Is the case minimal?** Total over every reducer record F-09 can produce: pass when a reducer ran
   to a fixpoint and the re-check preserved class, text and site; fail as `not_minimal` for
   `reduced=False`, for `reduction_changed_failure`, and for no reducer having run at all, with the
   reason recorded (FR-13.3).
3. **Is the input valid?** The mechanical parse-and-verify check of FR-13.15, whose three command
   lines are **§4.8** (the earlier reference to §4.6, which is `arcilator`, was wrong; W17). Three
   outcomes: **pass** on exit 0; **pass** with `validity_basis=checker_failed` when the check itself
   fires the primary oracle, because the component that would judge validity is then the failing one;
   **fail** as `invalid_input` on a clean non-zero exit with a diagnostic.

   FR-13.15's requirement text has a **second conjunct** that had no implementation (W15): the check
   passes only where the parse succeeded **and the recorded failure occurred after that point**. It
   is answered from fields the record already has, and needs no new run: the recorded failure occurred
   after parsing exactly when its `OracleVerdict.fingerprint_frame` is not inside the parser, that is
   when the frame's file does not lie under `lib/Parser/`, `lib/AsmParser/`, `tools/circt-translate/`
   or CIRCT's own `*Parser*.cpp`, **or** when the check's own exit was 0 while the probe's argv
   carried a pass pipeline, which puts the failure downstream of the parse by construction. The
   answer is recorded as `GateDecision.q3_after_parse: Optional[bool]` and, where it is `False`, the
   question fails as `invalid_input` with `q2_reason`-style text naming the parser frame. That is the
   cheapest thing that answers the conjunct with no extra process, and it is stated here because
   FR-13.15's third acceptance clause, "the recorded failure's stage is later than the check's", had
   no field, no record and no check anywhere in §2, §3 or §6 before this revision.
4. **Is it new?** `new` passes; every other dedup value, `dedup_unavailable` included, fails
   (FR-13.5).

The triage classification is read by none of the four, and `tests/test_gate.py` asserts that changing
it alone changes no answer and no decision (FR-13.4).

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def gate_rerun(repro_command: str, image_spec: ImageSpec, limits: dict,
               artefact_root: str) -> dict:
    """Re-run one reproducing command in a fresh process and a new directory.

    Returns:
        {"status": str, "oracle_class": str | None, "assertion_text": str | None,
         "assertion_site": str | None, "fingerprint": str | None,
         "worker": str, "node_id": str, "pid": int}
    Worker:
        {"circt": 1}.
    Raises:
        BinaryMismatch, exactly as probe_execute does and for the same reason.
    """
```

The working directory is `tempfile.mkdtemp(dir=<artefact_root>/<run>/gate/)`, created per call and
never reused, which with a fresh process and a different worker is what the framework can deliver and
what the question needs: no state carried over from the run that produced the verdict (C-19,
FR-13.2's own rationale).

**`approve.py`** is a program, not a node: `input()` and `print()`, no framework (ADR-D-12). §13.2
gives its commands. It enforces, in this order and before anything is shown to the human: the per-UTC-day
filing cap (FR-13.8); the `good first issue` refusal, read from the `issue_labels` key of the
candidate's `dedup_evidence` (FR-13.9); and FR-11.8's hold. It then shows the full rendered report,
the four answers, the repair diff if any, and the reduced case, in one view (FR-13.12), takes a typed
approval naming the approver, takes FR-20.5's licence confirmation with the patch on screen whenever
the decision is `report_plus_patch`, and records both against the same report id together with the
issue URL where FR-13.16's poll found nothing (FR-13.18). A decline downgrades the decision to
`report` and is recorded. Nothing at all is written until the approval is complete, so a human who
walks away leaves the candidate `held` with `held_reason=awaiting_approval` and the next invocation
presents the same report.

### 3.10 The three functions proposed for `chia/chipyard/circt.py`

FR-19.2 requires generic CIRCT capability to be proposed for this module, with only flow-specific
code in the example directory, which is the split CHIA documents
(`chia:examples/circt_issue_solver/README.md:107-110`). Exactly three functions are generic: none of
them knows anything about seeds, arms, budgets or gates.

```python
@ChiaFunction(resources={"circt": 1})
def circt_exec_probe(tool: str, argv: list[str], *, cwd: str,
                     wall_seconds: int, address_space_bytes: int,
                     cpu_seconds: int, nofile: int = 1024,
                     output_byte_cap: int = 1_000_000) -> dict:
    """Run one CIRCT binary on one input, bounded, with no shell anywhere.

    Builds ["prlimit", "--as=...", "--cpu=<soft>:<hard>", "--nofile=...", "--",
    tool, *argv], starts it in its own process group, and SIGKILLs the group on
    the wall-clock expiry. prlimit sets the limits in its own process and then
    execs the tool, so they are in force from the tool's first instruction. The
    child is reaped with os.wait4, so its rusage comes back with its status.

    Returns:
        {"exit_status": int | None, "signal": str | None, "limit_hit": str | None,
         "cpu_seconds": float, "peak_rss_bytes": int, "wall_seconds": float,
         "stdout": str, "stderr": str, "truncated": bool, "argv": list[str],
         "worker_hostname": str, "worker_node_id": str, "child_pid": int}
    Worker:
        {"circt": 1}.
    Raises:
        FileNotFoundError if tool does not exist; every other failure is a field.
    """
```

**`peak_rss_bytes` comes from the same `os.wait4` call that gives `cpu_seconds`, and it is converted.**
`BuildResult.peak_rss_bytes` existed in §2.9 and as a `build_result` column in §6.2 and had no
producer anywhere: `circt_exec_probe`'s documented return carried no key that could fill it, so the
field was declared and never written. It is `ru_maxrss` from the child's rusage, and on Linux
`ru_maxrss` is in **kilobytes**, not in bytes and not in pages, so the one line is

```python
    peak_rss_bytes = rusage.ru_maxrss * 1024        # ru_maxrss is kB on Linux
```

Measured on 2026-09-14 with `os.fork` plus `os.wait4` around a child allocating a 300 MiB
`bytearray`: `ru_maxrss` came back **312,064**, which is 304.75 MiB read as kilobytes and 0.30 MiB
read as bytes, so the unit is kilobytes and the factor is 1,024. The conversion is done here, at the
one place the raw value is seen, so no reader has to know the platform rule; the multiplication is
named in this paragraph because a silent factor of 1,024 in a reported figure is the kind of thing
that survives into a paper.

The value is **observational and non-deterministic**, exactly as `wall_seconds` is: `BuildResult`
declares it so, NFR-02 exempts it from the determinism comparison, and §11 of `04-Test-Plan.md`
excludes it from the regeneration check. It is `None` for a child that never started, which is the
only case in which `os.wait4` is not reached. Nothing in the loop branches on it; it exists so that an
`oom` row can be read beside the address-space limit that produced it.

**`limit_hit` is derived here, and it is the only place it is derived** (K8). Three consumers read it
and nothing produced it: `classify_build` tests `limit_hit == "address_space"` first, `build_result`
declares it a `Literal["wall", "cpu", "address_space"]` column, and this function listed it among its
return keys. The rule is now three lines, and each rests on a measurement:

| `limit_hit` | Set when | Measured |
|---|---|---|
| `wall` | the caller's own wall-clock killer fired, that is `os.killpg(pgid, SIGKILL)` was reached | the caller knows it fired; nothing is inferred |
| `cpu` | the child's signal is `SIGXCPU`, **or** its rusage CPU is at or above `cpu_seconds` | see the `prlimit` measurement below |
| `address_space` | stderr carries one of §3.6's three allocation-failure literals, or the line `MemoryError` | `prlimit --as=104857600 -- python3 -c 'b=bytearray(500*1024*1024)'` exits **1** with `MemoryError` on stderr and no signal: `RLIMIT_AS` does not kill, it makes allocation fail |
| `None` | none of the above | |

**`--cpu` is passed as a soft:hard pair with `hard = soft + CPU_HARD_MARGIN_SECONDS`**, which is the
whole fix. `prlimit --cpu=N` sets soft equal to hard, and the kernel then escalates straight past
`SIGXCPU` to `SIGKILL`, which is indistinguishable from the wall-clock killer's own `SIGKILL`. With a
hard limit above the soft one the kernel delivers `SIGXCPU` first and the signal names the limit.
Measured on 2026-09-14:

```
$ prlimit --cpu=1   -- python3 -c 'while True: pass' ; echo rc=$?
rc=137                      # 128 + 9, SIGKILL: the limit is not identifiable
$ prlimit --cpu=1:3 -- python3 -c 'while True: pass' ; echo rc=$?
rc=152                      # 128 + 24, SIGXCPU
$ prlimit --cpu=1:6 -- python3 -c 'while True: pass' ; echo rc=$?
rc=152
$ prlimit --cpu=1:6 -- /bin/sh -c 'ulimit -t; ulimit -H -t'
1
6
```

and the parent's own view, through `os.fork` plus `os.wait4`, which is the shape this function uses:

```
prlimit --cpu=1:6 --         signal=SIGXCPU   exit=None  cpu_seconds=1.00
prlimit --cpu=1 --           signal=SIGKILL   exit=None  cpu_seconds=1.00
prlimit --as=104857600 --    signal=None      exit=1     cpu_seconds=0.03
```

`os.wait4` is what makes `cpu_seconds` available at all: `subprocess` does not surface `getrusage`,
and without it the `timeout`-with-null-signal rule of FR-06.4 has no way to tell a CPU kill from a
wall-clock kill. The child is started with `os.fork` plus `os.setsid` plus `os.execvp` rather than
`subprocess.Popen`, for that one reason, and the process-group discipline is unchanged.

`classify_build` then maps `wall` and `cpu` to **`timeout`** and `address_space` to **`oom`**, and a
limit kill is never `crash`. Before this revision a probe that exhausted `probe_cpu_seconds` arrived
as "died by signal, empty stderr, `limit_hit` unknown" and the table classified it `crash`, the
primary oracle fired, and a candidate was created; and §9.5 sets `probe_cpu_seconds` below
`probe_wall_seconds`, so for any compute-heavy probe the CPU limit binds first and that was the common
path rather than an edge. FR-06.2's "shall record which if any was hit" and FR-07.8 both rested on it,
and FR-18.6's `oom` and `timeout` rows were systematically under-counted while `crash` was inflated.

`worker_hostname`, `worker_node_id` and `child_pid` are returned for K12: `socket.gethostname()`,
`ray.get_runtime_context().get_node_id()` and the pid `os.fork` returned. They cost three lines and
they are what FR-13.2's recorded pair is built from.

It is deliberately **not** `circt_run_script`. That function runs `bash <script>`
(`chia:examples/circt_issue_solver/circt_util.py:144-148`), under which SIGABRT reaches the caller as
exit status 134 rather than as a signal, and its timeout path returns `exit_code: -1`, which collides
with the negative return code a signal-terminated child produces. Two implementations, one under a
shell and one not, would give different oracle verdicts for the same probe (FR-06.1). F-12's repro
path, which is CHIA's and stays CHIA's, still uses `circt_run_script`.

The process-group discipline is CHIA's own, copied from `circt_ninja_build`:
`subprocess.Popen(..., start_new_session=True)` then `os.killpg(proc.pid, signal.SIGKILL)` on
`subprocess.TimeoutExpired` (`chia:chia/chipyard/circt.py:640-658`). The signal is read from the
child's **negative return code**, `-N` meaning "terminated by signal N", and is recorded in a field
of its own, separate from the exit status (FR-06.4).

```python
@ChiaFunction(resources={"circt": 1})
def circt_reduce_run(input_path: str, test_script: str, output_path: str, *,
                     test_args: tuple[str, ...] = (), wall_seconds: int = 60,
                     sigkill_grace_seconds: int = 10) -> dict:
    """Run circt-reduce with an interestingness script and an output path.

    Builds ["circt-reduce", input_path, f"--test={test_script}",
    *(f"--test-arg={a}" for a in test_args), "-o", output_path], from
    /workspace/circt/build/bin, in its own process group, killed at
    wall_seconds. --test-must-fail is never passed: the script's polarity is
    exit 0 for interesting (FR-09.2).

    Returns:
        {"success": bool, "returncode": int, "wall_seconds": float,
         "output_valid": bool, "log_tail": str}
    Worker:
        {"circt": 1}.
    Raises:
        nothing.
    """


@ChiaFunction(resources={"circt": 1})
def circt_symbolize(frames: list[dict]) -> list[dict]:
    """Resolve LLVM crash-trace frames against the objects they actually lie in.

    Each input frame is {"index", "address", "shape", "module", "offset",
    "function", "file", "line"} as 3.6.2's _FRAME parsed it. Frames whose shape
    is "module_offset" are GROUPED BY MODULE and resolved with one
    llvm-symbolizer --obj=<module> --demangle --output-style=JSON call per
    module, that module's offsets on stdin; frames whose shape is "attributed"
    are returned unchanged, because LLVM already resolved them at print time and
    there is no module to ask.

    Feeding runtime addresses with --obj=<the tool>, which this function did
    before, asks the symboliser about an object those addresses are not in and
    resolves nothing at all (3.6.2, measured). The offset from the parentheses
    is the value the symboliser wants.

    JSON is used rather than the default line format because the default emits a
    two-line record per address separated by blank lines, which is a parser
    nobody should write twice.

    Returns:
        one dict per input frame, in input order, with the same keys plus
        "in_circt_object"; unresolved fields are "" and 0.
    Worker:
        {"circt": 1} - the objects are the worker's.
    Raises:
        nothing. An unparseable line yields an unresolved record.
    """
```

The JSON output style is measured, not assumed: on 2026-09-13, feeding two addresses produced two
JSON objects, one per line, each carrying `Address`, `ModuleName` and a `Symbol` list whose entries
hold `FunctionName`, `FileName`, `Line` and `Column`. The default LLVM style produced, for the same
input, a function-name line, a `file:line:column` line, and a blank separator per address.

### 3.11 The head modules, briefly

`budget.py`, `ledger.py`, `feedback.py`, `store.py`, `results.py` and `bug_loop.py` are head-side and
pure but for the store. Each exposes exactly the callables its component needs and no helper that is
called once.

| Module | Public callables | Notes |
|---|---|---|
| `budget.py` | `load_budget(path: str, repo_root: str) -> BudgetFile`, `snapshot(ledger: BudgetLedger, arm: Arm) -> LedgerSnapshot` | `load_budget` runs `git -C <repo_root> log -1 --format=%H -- budget.yaml` and `git -C <repo_root> log -1 --format=%cI -- budget.yaml`, refuses an uncommitted or later-committed file (FR-14.2), refuses unequal per-arm values (FR-14.5), and refuses any key outside §9's list. |
| `ledger.py` | `accrue(entry: LedgerEntry, db_path: str) -> None`, `aggregate(run_manifest_id: str, db_path: str) -> BudgetLedger`, `stop_reason(ledger: BudgetLedger, arm: Arm, budget: BudgetFile) -> str \| None`, `price(tokens_in: int, tokens_out: int, budget: BudgetFile) -> float` | `accrue` appends and calls `price` to fill `observed.cost_usd` before it writes, so no row is ever stored with tokens and no money; `aggregate` is a view over `ledger_entry` and sums `observed.cost_usd` across **both** arms and `shared` into `BudgetLedger.spend_usd`; `stop_reason` returns the window, the binding safety cap, **or `campaign_spend_cap` when `aggregate`'s campaign-wide `spend_usd` has reached `budget.campaign_spend_cap_usd`**, else `None`. `price` is `tokens_in / 1e6 * budget.price_usd_per_m_input_tokens + tokens_out / 1e6 * budget.price_usd_per_m_output_tokens`, rounded to six decimal places, and returns `None` when either count is `None`. |
| `feedback.py` | `build_feedback(results: list[ProbeResult], previous: FeedbackBundle \| None, seed_sha: str, iteration: int, dispatched_probe_ids: list[str]) -> FeedbackBundle` | One entry per **dispatched** probe id, so a probe with no `ProbeResult` appears with `reason=result_missing` rather than being absent, which is what keeps A5's set difference honest and is why the dispatched list is a parameter. |
| `store.py` | `LoopStore`, `init_schema`, `artefact_write`, `validate_candidate`, `load_candidate`, every record dataclass | §2.9, §6. |
| `results.py` | `render_results(store: LoopStore, manifest: RunManifest) -> str`, and the **fourteen** private refusal checks listed immediately below | Refuses to render without any element `02-HLD.md` §1.3 lists; §14.4 gives each check its element and its FR, and §14.2 maps each FR to it. |
| `bug_loop.py` | `main() -> int`, `build_image(...) -> ImageSpec` (§4.11.1), `_head_node_id()`, `_head_options()` | §13.1, §4.11.1. `build_image` is B1 and was named in §3.2 and §14.1 without a signature (W4); §4.11.1 now carries it in full, beside the Dockerfile lines it runs. |

**The fourteen refusal checks of `results.py`, named once and here** (W5). The count was "nine" in
this section and "fourteen" in §14.4; **fourteen is the number**, and the disagreement was a miscount
of §14.4's own table rather than a design change. They are, in §14.4's order:

```python
_REFUSALS = (_require_headline, _require_secondaries, _require_validation_table,
             _require_qualifiers, _require_contamination, _require_disclosures,
             _require_lag, _require_cutoff, _require_dedup_rates,
             _require_divergences, _require_mutator_declaration,
             _require_observed_heading, _require_both_windows,
             _require_regeneration_marks)
```

`render_results` calls each in that order and collects every failure before raising, so one render
reports every missing element rather than the first. §14.4 gives each one the element it demands and
the requirement it discharges and adds nothing to this list; `len(_REFUSALS) == 14` is asserted by
`tests/test_results.py`, and `grep -c '^| ' ` over §14.4's table body is the check that the two agree.

**Two rules `feedback.py` owns and neither was defined** (W16).

`FR-16.6`'s abandonment: a seed is abandoned when, for **two consecutive iterations**, every
`ProbeResult` of the iteration has `build_status` in `{"parse_error", "timeout", "oom"}` **and** the
multiset of `(build_status, stopping_reason)` pairs is equal between the two iterations. "The same
reason" is therefore the pair and not the status alone, because `parse_error` covers both a rejected
input and a rejected argv (§3.6) and abandoning a seed for the second would hide an apparatus defect
as a seed property. `abandon_reason` is the repeated pair, rendered as
`"stage_3:<status>:<reason> x<n>"`, and `abandoned` is what stops the seed (FR-16.3's
`terminating_condition` records `abandoned`).

`FR-16.4`'s deny-list, which §1.3's `test_feedback.py` line named and no section contained:

```python
_FEEDBACK_DENY = ("candidate_id", "candidate_count", "candidates", "fingerprint",
                  "dedup_verdict", "dedup_basis", "gate_answers", "gate_decision",
                  "taxonomy_bucket", "q1_reproduce", "q2_minimal", "q3_valid",
                  "q4_new", "precision", "bug_count", "confirmed", "filing",
                  "issue_number", "issue_url", "repair_status", "triage_class")
```

`tests/test_feedback.py` asserts that no field name of `FeedbackBundle` or `FeedbackEntry`, at any
nesting depth, is in that tuple, and that no **value** in a built bundle is a `CandidateRecord`,
`DedupVerdict` or `GateDecision`. It is a deny-list of names rather than a schema, because FR-16.4's
own criterion is "the bundle's schema is checked against a deny-list of result fields (candidate
counts, gate precision, bug counts)", and the three parenthesised examples are the three groups above.

**FR-17.4's per-stage counters, and who logs them** (§2.5 declares the `CounterBlock`; this is the
protocol around it). FR-17.4 was discharged by one sentence, "every node returns a counter dict the
driver logs on the head", which named no counter and fixed no schema, so two nodes could have counted
different things under the same name and the run's totals would have been unaddable.

- **Every node of §3.2 returns exactly one `CounterBlock`**, under the key `"counters"` of its own
  return dict. That is every row of §3.2 bar `B9c` and `B12`, which are programs rather than nodes,
  and bar the two `ChiaTool`s, which are servers. A node whose return is documented in §3 as a bare
  dataclass (`oracle_primary`, `oracle_differential`, `reduce_case`, `repair_adapt`, `gate_decide`)
  returns `(record, counters)` instead, and §3's signature for each says so.
- **Four counters and no fifth**: `started`, `completed`, `failed` and `seconds`. What one unit of
  work is, is fixed per stage and not per node, so two nodes of one stage sum: a probe for
  `stage_3` to `stage_5`, a seed for `stage_1` and `stage_2`, a candidate for `stage_6`, `stage_7`
  and `gate`, an image for `image`, a seed record for `corpus`, a commit walk for `pin`, an issue for
  `mirror`, and a mutator for `synthesis`.
- **B12 logs them on the head** through CHIA's `MetricsLogger`, one record per returned block, keyed
  by `(run_manifest_id, arm, stage)`, and writes the running totals to
  `<artefact_root>/<run>/results/counters.json` on every aggregation so that NFR-09's "inspecting the
  run does not stop it" is served by reading a file. The driver checks
  `started == completed + failed` per block and logs a named violation rather than repairing it.
- **The USD cap is campaign-wide, not per-arm, and that is deliberate** (2026-09-14). The window and
  the safety caps are per-arm and equal, which is what makes the head-to-head fair; the money cap is
  one number for the whole campaign, because it protects a credit balance rather than the
  comparison. So `stop_reason` returns `campaign_spend_cap` for **both** arms at once, the driver
  stops the arm in flight and never starts the other, and `results.py` prints which arm was running
  when it bound and how much of the other arm's window went unspent, exactly as it already does for
  a safety cap (FR-18.10). Splitting the cap in half per arm was considered and rejected: it would
  stop the cheaper arm early for no reason and would make the binding condition depend on the arm
  order, which `budget.yaml` fixes before the data exists.
- **A counter is never a budget.** `CounterBlock.seconds` is this node's own wall clock and
  `LedgerEntry.amount` is the arm's spend on the primary unit; they are different numbers with
  different owners and the two are printed under different headings (§14.4's
  `_require_observed_heading`). No stop rule reads a counter.

There is no `utils.py` and no helper module. Every function above is called from more than one place
or is a component's entry point; anything called once is inlined, which is the rule this design was
written under.
---

## 4. Every tool invocation, as an exact argv

Every option below is spelled as the tool spells it, and every one was checked by running `--help` on
2026-09-13, against the SDK at `~/.cache/chia-pin-smoke/circt-sdk/bin` under
`LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim`, against the
measured assertions-on build at `~/.cache/chia-pin-smoke/bassert_g/bin`, or against the host's own
`verilator`, `prlimit`, `timeout`, `git`, `cmake`, `ninja` and `lit`. §4.13 is the verification
ledger, and it names the one item that could not be verified.

Nothing here is a command **string**. Every invocation is a Python `list[str]` passed to
`subprocess.Popen` with no `shell=True` anywhere in the loop, which is FR-06.1's rule and the reason
`circt_run_script` is not reused for the measured path.

### 4.1 The shape every probe invocation takes

```python
["prlimit",
 f"--as={limits['probe_address_space_bytes']}",
 f"--cpu={limits['probe_cpu_seconds']}:"
 f"{limits['probe_cpu_seconds'] + CPU_HARD_MARGIN_SECONDS}",
 f"--nofile={PROBE_NOFILE}",
 "--",
 "/workspace/circt/build/bin/<tool>", *spec.argv]
```

The `--` is the separator between `prlimit`'s own options and the command it runs; verified on
2026-09-13, `prlimit --as=1073741824 --cpu=5 --nofile=256 -- /bin/sh -c 'ulimit -v; ulimit -t; ulimit -n'`
printed `1048576`, `5` and `256`, so all three limits reach the child. `prlimit`'s own usage line is
`prlimit [options] [--<resource>=<limit>] COMMAND` and its three long options are `-v, --as` (size of
virtual memory), `-t, --cpu` (maximum amount of CPU time in seconds) and `-n, --nofile` (maximum
number of open files), all verified from `prlimit --help`. The long spellings are used, never the
single letters, because `-v` also means `--version` on many tools and the argv is read by people.

**`--cpu` carries a soft:hard pair and not a single value**, which §3.10 measures and explains: with
soft equal to hard the kernel escalates past `SIGXCPU` straight to `SIGKILL` and the limit is not
identifiable, and `limit_hit` is then underivable. `CPU_HARD_MARGIN_SECONDS` is 5 `[DEFAULT]`, §9.4.
Verified on 2026-09-14: `prlimit --cpu=1:6 -- /bin/sh -c 'ulimit -t; ulimit -H -t'` printed `1` and
`6`, and `prlimit --cpu=1:6 -- python3 -c 'while True: pass'` returned 152, which is 128 + 24,
`SIGXCPU`.

`--rss` is never passed. `RLIMIT_RSS` has had no effect on Linux since kernel 2.4.30 and can kill
nothing, which is why FR-06.2's memory limit is an address-space limit.

The wall-clock limit is **not** `prlimit`'s business: it is enforced by the caller, which SIGKILLs the
process group at expiry, so that a probe that stops making progress without consuming CPU is still
killed. `timeout(1)` is used instead of the caller only inside the interestingness script (§10.2),
where there is no Python caller to do it.

### 4.2 `circt-opt`

Verified options, from `SDK circt-opt --help`:

| Option | Help text, verbatim |
|---|---|
| `--pass-pipeline=<string>` | Passes to run with the native compiler |
| `--split-input-file[=<string>]` | Split the input file into chunks using the given or default marker and process each chunk independently |
| `--verify-diagnostics` and `--verify-diagnostics=<value>` | Check that emitted diagnostics match expected-* lines on the corresponding line |
| `--allow-unregistered-dialect` | Allow operation with no registered dialects |
| `-o <filename>` | Output filename |
| `--no-implicit-module` | Disable implicit addition of a top-level module op during parsing |

Note the two spellings of each of the first two: `--split-input-file` takes an **optional** value and
`--verify-diagnostics` exists in both a bare and a valued form. That is why §3.3's
`strip_probe_only_options` removes a token equal to either option and a token beginning with either
plus `=`; stripping only the bare form would leave `--split-input-file=// -----` in a probe argv.

**A probe invocation** is the seed's normalised argv with those two stripped and `%s` bound to the
probe's input path, for example

```
/workspace/circt/build/bin/circt-opt /art/<run>/seed_<sha>/iter_1/probe_<id>/input.mlir \
  --convert-hw-to-llvm=spill-arrays-early=false
```

which is seed `f2b15a44ec70`'s own line (FR-01.2's acceptance) after step 4 dropped
`| FileCheck %s` and after `--split-input-file` was stripped.

### 4.3 `firtool`

Verified, from `SDK firtool --help`, the nine output modes G-04 names; the four this design uses:

| Option | Help text, verbatim |
|---|---|
| `--parse-only` | Emit FIR dialect after parsing, verification, and annotation lowering |
| `--ir-fir` | Emit FIR dialect after pipeline |
| `--ir-hw` | Emit HW dialect |
| `--verilog` | Emit Verilog |

The lift of FR-09.9 branch 2, in the order the branch fixes:

```
/workspace/circt/build/bin/firtool --ir-fir -o <probe dir>/lifted.mlir <probe dir>/input.fir
```

and, where the recorded failure lies inside the pipeline so that `--ir-fir` reproduces the failure
instead of emitting IR,

```
/workspace/circt/build/bin/firtool --parse-only -o <probe dir>/lifted.mlir <probe dir>/input.fir
```

Both lifts were run end to end during the measurements, not merely read out of `--help`: on
`analysis/probe/tiny.fir`, `firtool --parse-only` produced `firrtl.circuit` MLIR and `circt-reduce`
on the result reached `Testing input with /bin/true` and `Initial module has size 634` (M1). Where
both lifts fail, or the failure is in the `.fir` parser itself so that no MLIR ever exists, the
textual reducer runs instead.

### 4.4 `circt-verilog`

Verified, from `SDK circt-verilog --help`:

| Option | Help text, verbatim |
|---|---|
| `--lint-only` | Only lint the input, without elaboration and mapping to CIRCT IR |
| `--parse-only` | Only parse the input syntax and report diagnostics; do not elaborate or map to IR |
| `--import-only` | Parse and elaborate the input and map it to Moore IR, but do not run any lowering passes |
| `--ir-moore` | Run the entire pass manager to just before MooreToCore conversion, and emit the resulting Moore dialect IR |
| `--ir-llhd` | Run the entire pass manager to just before the LLHD pipeline , and emit the resulting LLHD+Core dialect IR |
| `--ir-hw` | Run the MooreToCore conversion and emit the resulting core dialect IR |
| `--format=<value>` | Input file format (auto-detected by default), with `=sv` "Parse as SystemVerilog files" and `=mlir` "Parse as MLIR or MLIRBC file" |
| `-I <dir>` | Additional include search paths |
| `-y <dir>` | Library search paths, which will be searched for missing modules |
| `-D <<macro>=<value>>` | Define `<macro>` to `<value>` (or 1 if `<value>` omitted) in all source files |
| `-o <filename>` | Output filename (`-` for stdout) |

The lift of FR-09.9 branch 3:

```
/workspace/circt/build/bin/circt-verilog --ir-moore -o <probe dir>/lifted.mlir <probe dir>/input.sv
```

also run end to end during the measurements: on `analysis/probe/tiny.sv` it produced `moore.module`
MLIR and `circt-reduce` reached `Initial module has size 765` (M1). The parse-only check used by the
gate is `--import-only`, not `--parse-only`, and §4.8 says why.

**`circt-verilog` reads MLIR, and that is what makes §4.7's `.sv` branch implementable** (§16 item 3
of `04-Test-Plan.md`). The branch's interestingness test is run on the **lifted Moore IR**, not on the
`.sv` file, and the earlier table said "the probe's own tool and argv, on the lifted MLIR" without
saying how a SystemVerilog front end reads MLIR. It does, through `--format=mlir`, and the option is
verified rather than assumed. The `--help` output relied on, taken on 2026-09-14 from the SDK at
`~/.cache/chia-pin-smoke/circt-sdk/bin/circt-verilog` under
`LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim`, and again from
the **source-built slang binary** at `~/.cache/chia-pin-smoke/bslang/bin/circt-verilog`, whose
`--version` prints `CIRCT 5056ff0` and `slang version 11.0.0+0`, is verbatim:

```
  --format=<value>                                     - Input file format (auto-detected by default)
    =sv                                                -   Parse as SystemVerilog files
    =mlir                                              -   Parse as MLIR or MLIRBC file
```

and it was exercised, not merely read, on both binaries: a two-port clocked module lifted with
`circt-verilog --ir-moore -o lifted.mlir tiny.sv` (rc 0, `moore.module @tiny(in %clk : !moore.l1, ...)`)
was fed straight back with `circt-verilog --format=mlir --ir-moore -o /dev/null lifted.mlir`, rc 0,
and likewise with `--import-only` and with `--ir-hw`, rc 0 in every case. Auto-detection also
accepted the file, and `--format=mlir` is passed **explicitly** anyway, so the recorded argv states the
format the run depended on rather than relying on a sniffer that could change.

The trailing double space in `--ir-llhd`'s help text is the tool's own and is reproduced verbatim
rather than tidied, because this table is a transcription.

### 4.5 `circt-translate`

`circt-translate --import-verilog` is the second slang entry point and is registered only under
`#ifdef CIRCT_SLANG_FRONTEND_ENABLED` (`circt:tools/circt-translate/circt-translate.cpp:31-33`).
Verified on the binaries: the measured assertions-on build's
`circt-translate --help | grep -c import-verilog` returns **0** and the SDK's returns **1**. A probe
whose seed enters this way therefore runs, under ADR-D-13 branch (a),

```
/workspace/circt/build/bin/circt-translate --import-verilog <probe dir>/input.sv
```

and under branch (b) does not run at all, because its seed is excluded by configuration (§5.3).

### 4.6 `arcilator`

Verified, from `SDK arcilator --help`:

| Option | Help text, verbatim |
|---|---|
| `--run` | Run the simulation and emit its output |
| `--jit-entry=<string>` | Name of the function containing the simulation to run when output is set to run |
| `--args=<string>` | Arguments to pass to the JIT entry function |
| `--observe-ports` | Make all ports observable |
| `--jit-vcd-file=<filename>` | Create a VCD trace for JIT runs and output it to the specified file |

The differential's arcilator side:

```
/workspace/circt/build/bin/arcilator --run --jit-entry=bugloop_main \
  --observe-ports --jit-vcd-file=<probe dir>/arcilator.vcd <probe dir>/harness.mlir
```

`bugloop_main` is the name of the `func.func` the harness generator emits around the design's
`arc.sim.*` operations, and it is a constant of the generator rather than a parameter, because
FR-08.3 requires one shared stimulus definition and a name per probe would be a second knob.
`--observe-ports` is what makes the sampled values appear in the trace at all.

### 4.7 `circt-reduce`, and the reducer-selection table

Verified, from `SDK circt-reduce --help`:

| Option | Help text, verbatim |
|---|---|
| `--test=<string>` | A command or script to check if output is interesting |
| `--test-arg=<string>` | Additional arguments to the test |
| `--test-must-fail` | Consider an input to be interesting on non-zero exit status. |
| `-o <string>` | Output filename for the reduced test case |
| `--keep-best` | Keep overwriting the output with better reductions |
| `--skip-initial` | Skip checking the initial input for interestingness |
| `--list` | List all available reductions |

**`--keep-best` exists, and it is on by default.** Its declaration is
`keepBest("keep-best", cl::init(true), ...)` (`circt:tools/circt-reduce/circt-reduce.cpp:70-73`), so
the output file is overwritten as reductions improve whether or not the flag is passed. Two
consequences the LLD must carry. First, FR-09.4's "keep the best reduction found so far rather than
discarding the work" is the tool's default behaviour and needs no flag. Second, FR-09.13's truncation
hazard is **always** live: a kill at the wall-clock budget can land mid-write, so the `-o` output is
validated after the reducer process exits and never while it is running. The loop passes
`--keep-best` explicitly anyway, so that the recorded argv states the behaviour the run depended on
rather than relying on a default that could change.

`-o` defaults to `-`, standard output (`circt:tools/circt-reduce/circt-reduce.cpp:65-68`), so it is
always passed. `inputFilename` is `cl::Required` and positional
(`circt:tools/circt-reduce/circt-reduce.cpp:61-63`), which with C-12 is why the tool refuses to start
without both an input and a `--test`.

**The calling convention** is fixed in the tool and the script must match it: the candidate file is
appended as the **last** argument, after the script name and after every `--test-arg`
(`circt:lib/Reduce/Tester.cpp:42-46`). This design passes **no** `--test-arg` at all, so the
candidate is the script's `$1`, which is the simplest convention that satisfies the contract. The
polarity is fixed too: `Tester::isInteresting` returns `result > 0` under `--test-must-fail` and
`result == 0` otherwise (`circt:lib/Reduce/Tester.cpp:57-61`), so a script that exits 0 when the
failure still reproduces is used **without** the flag, which is FR-09.2's one permitted polarity.

The invocation:

```
/workspace/circt/build/bin/circt-reduce <probe dir>/input.mlir \
  --test=<probe dir>/interesting.sh --keep-best -o <probe dir>/reduced.mlir
```

wrapped by the caller in its own process group and killed at `reduction_wall_seconds`.

**The reducer-selection table (FR-09.9), which `ReducedCase.reducer` and `ReducedCase.lift` record:**

| Probe input | Reducer | Lift, if any | Interestingness test runs |
|---|---|---|---|
| MLIR text: every `circt-opt`, `circt-translate` and `arcilator` probe, and any probe whose input is `.mlir` | `circt-reduce` | none | the probe's own tool and argv |
| `.fir`: the `firtool` probes | `circt-reduce` on the lifted MLIR | `firtool --ir-fir`, retried with `firtool --parse-only` where the failure is inside the pipeline | `firtool` on MLIR input |
| `.sv` entered through `circt-verilog` | `circt-reduce` on the lifted MLIR | `circt-verilog --ir-moore` | `circt-verilog --format=mlir <candidate>` plus the **seed's own output-mode flag**, that is the one of `--lint-only`, `--parse-only`, `--import-only`, `--ir-moore`, `--ir-llhd` or `--ir-hw` the probe's argv carried; every other token of the probe's argv is kept |
| `.sv` entered through `circt-translate --import-verilog` | `circt-reduce` on the lifted MLIR | `circt-verilog --ir-moore` | `circt-opt <candidate> -o /dev/null`, the post-parse pipeline the seed's stage implies, which for `--import-verilog` is **empty**: the tool imports and stops, so the only stage after the parse is MLIR's own verifier |
| both lifts fail, or the failure is in the front end's own parser, or `circt-reduce` itself aborted or died on the candidate, or the row above does not reproduce the recorded failure on the lift, or any other input language | `textual-ddmin` (§10.3) | none | the same interestingness script |

**Why the `.sv` row is two rows now.** The third row said "the probe's own tool and argv, on the
lifted MLIR" and `circt-verilog` was assumed to be unable to read MLIR, which made the branch's pass
criterion unstatable (§16 item 3 of `04-Test-Plan.md`). It can, through `--format=mlir`, which §4.4
records verbatim from `--help` and which was run end to end on both the SDK binary and the
source-built slang binary; so a `circt-verilog` probe's interestingness test **is** its own tool and
its own argv, with `--format=mlir` prepended and the input path replaced by the candidate. That keeps
FR-09.1's "the same oracle class, and for an assertion the same expression and the same `file:line`"
a comparison against the **same tool**, which is the whole point of the rule.

`circt-translate` has no such option: its `--help` on the same SDK carries `--import-verilog` and
`--emit-text-format`, which is AIGER's, and no `--format=` at all, checked on 2026-09-14. So a
`circt-translate --import-verilog` probe cannot be re-fed its own lift, and the second row uses
`circt-opt` on the lifted Moore IR instead, which is the post-parse pipeline that entry point implies
and which `circt-opt` accepts: `circt-opt lifted.mlir -o /dev/null` on the Moore IR above returned
rc 0 on both the SDK build and the measured assertions-on build. In practice this row will rarely
fire, because a failure inside `--import-verilog` is a failure inside the importer, so
`circt-verilog --ir-moore` lifts no IR either and the probe falls to the last row; the row exists so
that the case where the lift **does** succeed has a stated test rather than none.

The last row gains a fifth trigger for the same reason: where the row above runs and does not
reproduce the recorded failure on the lift, the lift has changed the failure and the textual reducer
takes it, which is decided on the first interestingness call and costs one call.

Measured, this covers the corpus: 146 seeds of 187 reduce directly, 35 via the `circt-verilog` lift,
4 via the `firtool` lift and 2 are textual only, so 98.9% have a `circt-reduce` path (M1).

### 4.8 The three parse-and-verify commands (FR-13.15)

Gate question 3, spelled as the tools spell it. Each is run under the same `prlimit` prefix as a
probe, and each runs at **`candidate.run_commit`**, against the source-tree binaries. The commit is
the candidate's own and never `manifest.run_commit[0]`, which in calibration mode is an arbitrary
sampled seed's (K14).

```
circt-opt <case> -o /dev/null
firtool --parse-only <case>
circt-verilog --import-only <case>
```

**Four** points, each of which is a decision and not a transcription. The earlier "three" counted the
bullets wrongly (W17).

- **No pass pipeline is passed to `circt-opt`**, so the command parses the input and runs MLIR's own
  verifier and nothing else. That is exactly the question being asked.
- **`--allow-unregistered-dialect` is never passed.** An unregistered dialect means the input is not
  valid CIRCT IR, and allowing it would make question 3 answer a different question (FR-13.15).
- **`-o /dev/null`** is passed so the check writes nothing. `circt-opt`'s `-o` is verified to be
  `Output filename`, and `/dev/null` is a file the container always has.
- **`--import-only` rather than `--parse-only` for `.sv`.** FR-13.15 names `--import-only` and quotes
  its help text; `--parse-only` stops before elaboration, so it would accept SystemVerilog that
  elaboration rejects, which is a weaker question than the one asked.

The three outcomes are §3.9's: exit 0 passes; the check itself firing the primary oracle passes with
`validity_basis=checker_failed`; a clean non-zero exit with a diagnostic fails as `invalid_input`.
§3.9 adds FR-13.15's second conjunct, `q3_after_parse`, which is answered from the recorded frames
rather than from a fourth command.

### 4.9 `prlimit`, `timeout`, `llvm-symbolizer`

**`prlimit`** is §4.1. Its package is `util-linux`, which the stock `ubuntu:24.04` base the image is
built from (`chia:dockerfiles/ChiaCirctBaseDockerfile:30`) already carries: measured 2026-09-13 inside
`ubuntu:24.04`, `dpkg -S /usr/bin/prlimit` resolves to `util-linux`, `dpkg-query` reports
`util-linux 2.39.3-9ubuntu6.6` with `Essential: yes` and `Priority: required`, and
`prlimit --version` prints `prlimit from util-linux 2.39.3`. The image's apt line names `util-linux`
anyway (§4.11), so the dependency is explicit in the Dockerfile rather than inherited silently; the
line is a no-op at build time.

**`timeout`**, from coreutils, used only inside the interestingness script, where no Python caller
exists to kill a process group. Verified options, from `timeout --help`:

| Option | Help text, verbatim |
|---|---|
| `-k, --kill-after=DURATION` | also send a KILL signal if COMMAND is still running this long after the initial signal was sent |
| `-s, --signal=SIGNAL` | specify the signal to be sent on timeout |
| `-f, --foreground` | when not running timeout directly from a shell prompt, allow COMMAND to read from the TTY and get TTY signals; in this mode, children of COMMAND will not be timed out |

The script uses `timeout --signal=TERM --kill-after=<grace> <wall> ...`, which is FR-09.13's
SIGTERM-then-SIGKILL policy exactly. `--foreground` is **not** used: it is the one option that would
stop the tool's own children being timed out, which is the opposite of what is wanted.

**`llvm-symbolizer`**, from the SDK. Verified options, from `SDK llvm-symbolizer --help`:

| Option | Help text, verbatim |
|---|---|
| `--obj=<file>` | Path to object file to be symbolized (if not provided, object file should be specified for each input line) |
| `--demangle` | Demangle function names |
| `--functions=<value>` | Print function name for a given address |
| `--output-style=style` | Specify print style. Supported styles: LLVM, GNU, JSON |
| `--inlines` | Print all inlined frames for a given address |

The invocation is **one call per module named in the trace**, not one call for the whole trace:

```
<sdk>/bin/llvm-symbolizer --obj=<the module the frame lies in> --demangle --output-style=JSON
```

with that module's **file offsets** on stdin, one per line, taken from the `(<module>+0x<offset>)`
tail `_FRAME` captures (§3.6.2). The earlier invocation named `/workspace/circt/build/bin/<tool>` for
every frame and fed the runtime addresses, and resolves nothing: measured on 2026-09-14 against a real
`circt-opt` segfault, all six frames came back `FunctionName:"" FileName:"" Line:0`, while the same
frames against their own modules and offsets came back named. The full pair of runs is in §3.6.2.
`--functions` is left at its default, which is `linkage`:
measured on the assertions-on build, `--functions=linkage` and the default both returned
`circt::chooseName(llvm::StringRef, llvm::StringRef)` with
`.../src/lib/Support/Naming.cpp:47:0`, while `--functions=short` returned `??` for the same address,
because a short name needs debug information `-gline-tables-only` does not emit. `--inlines` is not
passed: an inlined frame would change the frame tuple's length without changing the bug, and G-43's
fingerprint counts frames.

### 4.10 Verilator

Verified against the host's `Verilator 5.052 2026-09-05 rev v5.052`, which is the version FINAL
Appendix A records and the version FR-03.15 pins for the campaign.

| Option | Help text, verbatim |
|---|---|
| `--binary` | Build model binary |
| `--cc` | Create C++ output |
| `--exe` | Link to create executable |
| `--build` | Build model executable/library after Verilation |
| `--main` | Generate C++ main() file |
| `--timing` | Enable timing support |
| `--top-module <topname>` | Name of top-level input module |
| `--Mdir <directory>` | Name of output object directory |
| `-o <executable>` | Name of final executable |
| `-j <jobs>` | Parallelism for --build-jobs/--verilate-jobs |
| `--x-assign <mode>` | Assign non-initial Xs to this value |
| `--x-initial <mode>` | Assign initial Xs to this value |
| `-Wno-fatal` | Disable fatal exit on warnings |
| `--trace-vcd` | Enable VCD waveform creation |

**The accepted modes were obtained from the tool rather than from documentation**, by feeding it an
invalid one: `verilator --lint-only --x-assign bogus --x-initial bogus t.sv` answers

```
%Error: Unknown setting for --x-assign: 'bogus'
        ... Suggest '0', '1', 'fast', or 'unique'
%Error: Unknown setting for --x-initial: 'bogus'
        ... Suggest '0', 'fast', or 'unique'
```

So `--x-assign` takes `0`, `1`, `fast` or `unique`, and `--x-initial` takes `0`, `fast` or `unique`.
The campaign's declared X policy is `--x-assign unique --x-initial unique` `[DEFAULT]`, recorded in
`RunManifest.x_policy` as the literal string `x-assign=unique,x-initial=unique` and in every
`DifferentialVerdict`. `unique` is chosen over `0` because `0` makes Verilator agree with a
zero-initialising simulator by construction, which would hide exactly the class of divergence the
oracle exists to find; `unique` gives each X a distinct pseudo-random value, so a design that depends
on an X diverges loudly and FR-08.9's `diverge_x_policy` bucket has something to catch.

**`--binary` is used**, not `--cc --exe --build`. `--binary` is Verilator's own shorthand for
building a model binary and it implies the `--main`, `--exe`, `--build` and `--timing` that a
generated SystemVerilog testbench with a clock generator needs; spelling the four out would be four
places to get wrong. The invocation:

```
verilator --binary -j 0 -Wno-fatal --timing \
  --x-assign unique --x-initial unique \
  --top-module bugloop_tb --Mdir <probe dir>/obj_dir -o Vbugloop \
  --trace-vcd <probe dir>/tb.sv <probe dir>/dut.sv
```

then `<probe dir>/obj_dir/Vbugloop`, whose stdout is the sampled values the differ reads. `-Wno-fatal`
is required rather than convenient: a generated design routinely trips a style warning, and without
it Verilator exits non-zero on a lint warning and every comparison becomes a `harness_failure`
(FR-08.8) for a reason that has nothing to do with the design.

### 4.11 The image: `cmake`, `ninja`, `git`, `lit`

**The configure line**, which is CHIA's own at `chia:dockerfiles/ChiaCirctBaseDockerfile:92-98` plus
exactly the FRD's additions:

```
cmake -B build -S . -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DLLVM_ENABLE_ASSERTIONS=ON \
      -DMLIR_DIR=/opt/circt-sdk/lib/cmake/mlir \
      -DLLVM_DIR=/opt/circt-sdk/lib/cmake/llvm \
      -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
      -DLLVM_USE_LINKER=lld -DLLVM_CCACHE_BUILD=ON \
      -DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
      -DCMAKE_C_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only" \
      -DMLIR_SOURCE_DIR=/opt/circt-sdk \
      -DCIRCT_SLANG_FRONTEND_ENABLED=ON \
      -DCIRCT_SLANG_BUILD_FROM_SOURCE=ON \
      -DLLVM_PARALLEL_LINK_JOBS=2
```

The first **seven** lines are CHIA's, unchanged: `chia:dockerfiles/ChiaCirctBaseDockerfile:92-98` is
seven lines, and 7 + 6 = 13, which is the block above. The six added lines are FR-03.4's two flag
strings, FR-03.17's lit variable, ADR-D-13 branch (a)'s two slang options, and the link-job cap that
W-04 added (deviation 2 below). ~~7 + 5 = 12~~ is corrected with it; the earlier "eight" attributed
`-DCMAKE_CXX_FLAGS_RELEASE` to CHIA when it is this design's own addition (W18).

- `-DLLVM_ENABLE_ASSERTIONS=ON` is kept although it is ineffective: the SDK's `LLVMConfig.cmake` sets
  `LLVM_ENABLE_ASSERTIONS OFF` and wins (A-10, A-11, measured on the published image in M5). It stays
  because removing a line CHIA passes would be a change to CHIA's base rather than an addition to it.
- `-DMLIR_SOURCE_DIR=/opt/circt-sdk` is FR-03.17, and it is the SDK **root**, not its `include`
  directory: `test/Tools/circt-tblgen/lit.local.cfg` joins `include` on itself
  (`circt:test/Tools/circt-tblgen/lit.local.cfg:14`) and then looks for `mlir/IR/OpBase.td` under the
  result, so the value must be the directory whose `include/mlir/IR/OpBase.td` exists. Verified end
  to end on 2026-09-13: a fresh SDK-based configure carrying the variable produced
  `config.mlir_src_root = "/home/adi/.cache/chia-pin-smoke/circt-sdk"` in `build/test/lit.site.cfg.py`
  and `lit --no-progress-bar --show-tests build/test` then exited 0 with 1,390 tests discovered and no
  discovery error, where the same tree without it leaves `config.mlir_src_root = ""` and lit exits 2
  with zero tests.
- `-DLLVM_PARALLEL_LINK_JOBS=2` is **added 2026-09-14** by W-04 (deviation 2), and is the one line of
  this block the *measured* recipes always carried and the written one did not (`m2_build.sh`,
  `m7_slang_build.sh`). Reason: `-gline-tables-only` nearly triples the binaries, `circt-opt` being
  217,251,208 B in the built image, and eight concurrent `lld` links of binaries that size do not fit
  a 15 GB host with 10 GB already in use. It constrains **ninja's scheduling only**, never reaches the
  compiler, and therefore changes no binary, which is why it can be added without invalidating any
  measurement taken before it.
- `-DLLVM_CCACHE_BUILD=ON` is CHIA's and is kept, although the measurements found it silently unused
  in a standalone CIRCT build against an installed LLVM. CHIA gets ccache by a different route, by
  putting `/usr/lib/ccache` on `PATH` (`chia:dockerfiles/ChiaCirctBaseDockerfile:77`) and passing
  `-DCMAKE_CXX_COMPILER=clang++` by name (`chia:dockerfiles/ChiaCirctBaseDockerfile:97`). The two
  halves are in two places and the earlier single citation covered only the first (W18).

`LD_LIBRARY_PATH=/opt/circt-sdk/lib` must be in force for this line and for the ninja line that
follows, not only at probe time: the SDK's `mlir-tblgen` generates CIRCT's `.inc` files and without
`libz3.so.4` on the loader path the build fails at its first tablegen edge (C-02, as amended; measured
in M2). CHIA's base already sets it image-wide at `ChiaCirctBaseDockerfile:77-79`, before the cmake
and ninja layers, and the assertions-on image inherits that `ENV` rather than re-scoping it.

**The build line:**

```
ninja -C build -j <jobs> circt-opt firtool circt-translate arcilator circt-reduce circt-verilog
```

Six targets, not five: `circt-verilog` joins FR-03.7's list under ADR-D-13 branch (a), and drops out
of it under branch (b), which is why FR-03.7 makes the list a parameter and not a constant. Measured
at `-j12` on a 20-core host, the five targets without slang are 1,082 ninja edges and 582 s under this
flag string, against 621 s for `-DNDEBUG`; the build tree is 1.3 GB against 425 MB, and the five
binaries are 498 MiB against 131 MiB (M2). ~~The slang addition is unmeasured and is A-03's remaining
question.~~ **Measured at image level 2026-09-14 (W-04):** all six targets with slang are **1371**
ninja edges and **972 s** at `-j8` from a cold cache with link jobs capped at 2, the build tree
**1.7 GB**, the six binaries **703,211,208 B (670.6 MiB)**, and the image **1,912,742,097 B** by
`docker image inspect --format '{{.Size}}'` in **23** layers against the base's 17. A-03's remaining
question is now narrower and is the **delta of `-gline-tables-only` alone**, plus a per-probe
slowdown, both of which fall out of the one second image W-04b already needs for FR-03.6.

**The source fetch.** The base image already holds `/workspace/circt` as a shallow clone at the tag,
`git clone --depth 1 --branch "${CIRCT_VER}"` (`chia:dockerfiles/ChiaCirctBaseDockerfile:85-86`),
which cannot check out an arbitrary commit. The recipe therefore **fetches into the repository that
is already there** and never re-initialises it:

```
git -C /workspace/circt fetch --depth 1 origin ${CIRCT_SHA}
git -C /workspace/circt fetch --depth 1 origin tag ${CIRCT_VER}
git -C /workspace/circt checkout --detach ${CIRCT_SHA}
```

Three things are being fixed at once and each was executed on 2026-09-14 against a repository built to
the same shape, an upstream carrying a `llvm` gitlink and two `firtool-*` tags, shallow-cloned at the
older tag exactly as the base does (K4).

**One.** The earlier recipe began `git init circt && cd circt` and `git remote add origin ...`, which
is written for an empty directory and used on the base's populated one:

```
$ git -C circt init          ; # in the directory the base already cloned into
Reinitialized existing Git repository in .../circt/.git/
$ git -C circt remote add origin file://.../up
error: remote origin already exists.                                   rc=3
```

The `RUN` layer aborts there. Fetching into the existing repository needs neither line, because the
base's clone already has `origin`.

**Two.** `git fetch --depth 1 origin <sha>` fetches one commit and **no tags**, so `${CIRCT_VER}` was
not a name the next line could resolve and the pin check always fatalled. The second fetch is what
brings the tag object in, and the `tag <name>` refspec form does exactly that:

```
$ git -C circt fetch --depth 1 origin fe074f4fedbfbfb8110980cc43742eebd4e9c22c
 * branch            fe074f4...        -> FETCH_HEAD                   rc=0
$ git -C circt fetch --depth 1 origin tag firtool-1.99.2
 * [new tag]         firtool-1.99.2 -> firtool-1.99.2                  rc=0
$ git -C circt tag --list
firtool-1.99.0 firtool-1.99.2
```

**Three.** `git checkout --detach ${CIRCT_SHA}` replaces `git checkout --detach FETCH_HEAD`. They are
the same object after the first fetch and different after the second, because `FETCH_HEAD` then names
the tag; naming the SHA is unambiguous under both.

```
$ git -C circt checkout --detach fe074f4fedbfbfb8110980cc43742eebd4e9c22c
HEAD is now at fe074f4                                                  rc=0
```

`git fetch --depth 1 origin <sha>` is the fetch-by-SHA FR-03.1 asks for, and it works where
`--branch <tag>` does not because a tag clone cannot reach a commit the tag does not point at, which
M5 confirmed on the published image.

**The pin equality check**, before `ninja` starts (FR-03.2), unchanged in form and now reachable:

```
test "$(git -C /workspace/circt ls-tree ${CIRCT_SHA} llvm | awk '{print $3}')" = \
     "$(git -C /workspace/circt ls-tree ${CIRCT_VER} llvm | awk '{print $3}')" || exit 1
```

Full 40-character SHAs, no tolerance, no nearest match, no version-string comparison. Executed on the
repository above, both ways:

```
$ git -C circt ls-tree fe074f4... llvm ; git -C circt ls-tree firtool-1.99.2 llvm
160000 commit ac42ec66478f0f34690dc54a5eb52b6e53b8a05c	llvm
160000 commit ac42ec66478f0f34690dc54a5eb52b6e53b8a05c	llvm
$ <the check verbatim>                                  PIN CHECK PASSED (exit 0)
$ <the same check with a SHA whose pin differs>         PIN CHECK FAILED (exit 1)
```

and the same two `ls-tree` commands against the real `llvm/circt` clone at `firtool-1.99.2`, whose
commit is `6f7cba6286df676c84e4e8b2c2d5b2c6281c4bb4`, both print
`160000 commit 6a01ac7d06df875206f746fc982f58c161249285	llvm`. Without the check the failure
surfaces at build target 2 of 1030 with `error: Variable not defined: 'SymbolName'` (C-01).

**One limitation of that reproduction, stated rather than glossed.** The fetch semantics were executed
against a purpose-built upstream of the same shape, not against `llvm/circt` itself, because
`~/.cache/chia-pin-smoke/circt` is a `blob:none` partial clone
(`git config --get remote.origin.partialclonefilter` prints `blob:none`) whose promisor remote is
unreachable offline, so it cannot serve a shallow clone: `git clone --depth 1 --branch <tag>
file://<it>` fails with `could not fetch <blob> from promisor remote` and `fetch-pack: invalid
index-pack output`. What was executed against the real clone is the pair of `ls-tree` commands above,
which is the half of the recipe that reads `llvm/circt`'s own objects. The half executed against the
synthetic upstream is `git`'s behaviour, which does not depend on which repository it is pointed at.

**The apt line** is CHIA's at `ChiaCirctBaseDockerfile:45-52`, extended by ~~four~~ **five** packages:
`openssh-client` and `rsync`, which CHIA's documented image contract requires verbatim and CHIA's own
CIRCT base omits (C-07, FR-03.9); `verilator`, which no CHIA image installs (ADR-D-09 option (a));
`util-linux`, which the base already carries as an essential package and which is named explicitly so
that the Dockerfile states the dependency `prlimit` creates rather than inheriting it (§4.9); and,
**added 2026-09-14** by W-04 (deviation 3), **`clang-tools`**, which carries `clang-scan-deps`.
That fifth is a consequence of FR-03.14 and of nothing this block got wrong: CMake scans C++20
targets for module dependencies, slang builds to C++20, and CHIA's base installs `clang` without the
package holding the scanner, so **every** `_deps/slang-build` `.ddi` edge fails with
`"CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS-NOTFOUND" -format=p1689` and the build stops at ninja edge 280 of
1371. No CHIA image has ever needed it because no CHIA image turns the slang front end on, and M7 did
not hit it because M7's compiler was a full LLVM build tree that ships the scanner beside `clang++`.
Verified separately before the rebuild, on a throwaway container: with `clang-tools` installed a
minimal C++20 CMake project resolves
`CMAKE_CXX_COMPILER_CLANG_SCAN_DEPS:FILEPATH=/usr/bin/clang-scan-deps-18`. Ubuntu ships **only** the
version-suffixed binary, there being no unversioned `/usr/bin/clang-scan-deps`, and CMake finds it
because it searches the compiler's major-version suffix first; so the Dockerfile must name the
package and must **not** assume an unsuffixed name exists.

**Seven deviations from this section, all accepted, 2026-09-14 (W-04, `01-FRD.md` §1.9).** The first
build of this image is recorded in `analysis/measurements/2026-09-14-image-build.md` §6. Two of the
seven are written into the blocks above; the other five are written here, and the numbering is the
report's.

1. **The base is `FROM ghcr.io/ucb-bar/chia-circt:latest` and the SDK is re-installed at
   `${CIRCT_VER}` inside this Dockerfile.** `BASE_IMAGE` is an `ARG`, so a correctly pinned base can
   be substituted later with no Dockerfile edit. §1.2 and this section described an image built on
   CHIA's base **layers**, which implies the base's own `CIRCT_VER`; measured, the published base's
   SDK is **`firtool-1.148.0`, LLVM 23.0.0git**, at source `5dc7f103d714` (2026-05-24). FR-03.2
   requires the SDK tag to be a parameter of **this** image, so the SDK is re-installed here.
   Rebuilding CHIA's base with the right `CIRCT_VER` instead would add its own `ninja circt-opt`,
   about 30 minutes by CHIA's own comment, plus the sbt, JDK, Python and Ray downloads. The **child**
   image is used rather than the base because FR-03.9 wants the `chia` package installed and the
   child is the layer that installs it. **FR-03.3's strip is re-applied to the re-installed SDK**, and
   both paths are verified absent in the built image.
2. `-DLLVM_PARALLEL_LINK_JOBS=2` in the configure line above.
3. `clang-tools` in the apt line above.
4. **`rm -rf /workspace/circt/build` immediately before `cmake -B build -S .`, folded into the same
   `RUN`.** This section gave the configure line and was silent on the base's existing build
   directory. That directory was configured against a different SDK (LLVM 23) and a different source
   commit, and every object in it would be rebuilt anyway because the flag string changed, so removing
   it costs nothing in image size, the base's copy staying in a lower layer either way, and removes a
   class of stale-cache failure. It is in the configure `RUN` and not a `RUN` of its own for the same
   reason as 5.
5. **`chmod -R a+rwX /workspace/circt` is folded into the ninja `RUN`, not a layer of its own.** A
   recursive chmod in a separate layer copies every file of a freshly written 1.7 GB tree up and would
   roughly double the image. CHIA's base has the chmod as its own layer, where it is correct because
   the tree below it is in a lower layer; here it is not. This section did not mention the chmod at
   all, which is the defect.
6. **An `ENV BUGLOOP_*` block is the last layer**, recording `BUGLOOP_CIRCT_SHA`, `BUGLOOP_CIRCT_VER`,
   `BUGLOOP_TOOL_TARGETS`, `BUGLOOP_CXX_FLAGS_RELEASE` and `BUGLOOP_SLANG`. An addition rather than a
   change: it is what makes **FR-03.10 and FR-03.11 answerable from inside a running worker** without
   re-deriving anything, and being last it invalidates no cached layer. It is the input to
   `ImageSpec`, not its replacement; the object itself is §4.11.1's.
7. **`--progress=plain` is dropped from the `docker build` command** (§4.11.1 step 2). It is a
   BuildKit flag, this host has the legacy builder only, `docker buildx version` printing
   `docker: unknown command: docker buildx` with no CLI-plugin directory present, and the CLI rejects
   the build outright with rc 125 before anything runs. The legacy builder's own output is already
   per-step plain text, carrying every `Step n/20` header and every command's full output, which is
   what the flag was asked for. **Not a Dockerfile change**, and no system package was installed to
   work around it.

**Two things this section left as parameters and the build simply names:** `<jobs>` is
`ARG BUILD_JOBS=8`, and `CIRCT_PKG` keeps CHIA's own default
`circt-full-shared-linux-x64.tar.gz`.

**`lit`** is baked exactly once, into the image, at the path CHIA checks,
`/home/ray/anaconda3/envs/py_worker/bin/lit` (`chia:chia/chipyard/circt.py:608`), so that
`circt_warm_build`'s conditional install finds it present and does nothing
(`chia:chia/chipyard/circt.py:679-686`) and the cluster YAML's `run_setup_commands` do not repeat the
install (FR-03.8). The lit invocation itself is CHIA's, unchanged:

```
lit --no-progress-bar --filter-out=circt-tblgen <paths>
```

with `cwd` the build directory, which is exactly what `circt_run_lit` builds
(`chia:chia/chipyard/circt.py:719-726`), and with `<paths>` from
`circt_util.circt_lit_gate_paths()` (`chia:examples/circt_issue_solver/circt_util.py:162-174`). The
image's own acceptance run of FR-03.17 is a different invocation and is discovery only:

```
lit --no-progress-bar --show-tests /workspace/circt/build/test
```

### 4.11.1 `bug_loop.build_image`, B1's callable

`03-LLD.md` named `bug_loop.py:build_image` in §3.2 and §14.1 and gave it a timeout and an idempotency
key, and gave it no signature, no **Returns**, no **Worker** and no **Raises** anywhere in §3, so
every test of §1.22 of `04-Test-Plan.md` was written against the **image** and the **Dockerfile**,
which are specified, and none against the callable, which was not. It is specified here, beside the
lines it runs.

```python
@ChiaFunction(resources={"circt": 1}, max_retries=0)
def build_image(circt_sha: str, sdk_tag: str, targets: tuple[str, ...],
                flag_string: str, dockerfile: str, registry: str,
                *, slang: bool = True, push: bool = True,
                base_image: str = "ghcr.io/ucb-bar/chia-circt:latest",
                timeout_seconds: int = 10800) -> dict:
    """Build, check and publish the assertions-on CIRCT image, or reuse it.

    Runs, in this order and stopping at the first failure:

      1. TAG. Computes the image tag from the hash manifest below and, if an
         image with that tag already exists in *registry* and its recorded
         ImageSpec validates, returns it without building. That is the
         idempotency the 3.2 row promises, made mechanical.
      2. BUILD. subprocess docker build with the 4.11 arguments:
           docker build -f <dockerfile> -t <tag> \\
             --build-arg CIRCT_SHA=<circt_sha> \\
             --build-arg CIRCT_VER=<sdk_tag> \\
             --build-arg TOOL_TARGETS="<space-joined targets>" \\
             --build-arg CXX_FLAGS_RELEASE="<flag_string>" \\
             --build-arg SLANG=<ON|OFF> \\
             --build-arg BASE_IMAGE=<base> <context>
         There is NO --progress=plain (4.11 deviation 7, 2026-09-14): it is a
         BuildKit flag, a host with the legacy builder only rejects the whole
         build with rc 125 before anything runs, and the legacy builder's own
         output is already the per-step plain text the flag was asked for.
         No shell: an argument list to Popen, as everything else here is. The
         Dockerfile's own RUN layers carry the fetch-by-SHA, the tag fetch, the
         pin equality check and the cmake and ninja lines of 4.11; this function
         passes the six arguments those layers read and nothing else; the
         sixth, BASE_IMAGE, is 4.11 deviation 1 and defaults to
         ghcr.io/ucb-bar/chia-circt:latest.
      3. PIN. Reads the build log for the pin check's own line and fails the
         build if the check did not run, which is distinct from the check
         failing: a Dockerfile edit that dropped the layer would otherwise
         publish a mispinned image silently (FR-03.2).
      4. LIT DISCOVERY (FR-03.17). Starts a container from the built tag and
         runs `lit --no-progress-bar --show-tests /workspace/circt/build/test`,
         capturing its exit status and the discovered-test count into
         lit_discovery_ok and lit_discovered_count, and writing the output to
         <artefact_root>/<run>/image/lit_discovery.txt. A non-zero exit or any
         `fatal: unable to parse config file` line sets lit_discovery_ok false
         and BLOCKS PUBLICATION.
      5. TOOL VERSIONS. In the same container, `--version` on every target and
         on llvm-symbolizer and verilator, recorded into tool_version_output
         and verilator_version. A target that will not run its own --version is
         a failed build, not a published image (FR-03.13).
      6. HASH MANIFEST (FR-03.16). sha256 of each target binary under
         /workspace/circt/build/bin, taken in a FRESHLY STARTED container from
         the published image and never from the build tree (5.2), into
         tool_hashes.
      7. ASSERTION OBJECTS (FR-03.5). `nm -u` over each target binary for
         __assert_fail, and the list of non-referencing obj.CIRCT objects into
         assertion_nonreferencing, compared AS A SET against the committed
         baseline; a difference names every differing object and blocks
         publication.
      8. PUBLISH. `docker push <tag>` when push is true, then
         `docker image inspect --format={{index .RepoDigests 0}} <tag>` for
         image_digest. Nothing is pushed if any step above failed, so a partial
         build leaves NO image under the requested tag (FR-03.13).

    Returns:
        {"image_spec": ImageSpec, "reused": bool, "counters": CounterBlock},
        where reused is True exactly when step 1 short-circuited. The ImageSpec
        carries every field of 2.9 and is what RunManifest.image_spec is built
        from.
    Worker:
        {"circt": 1} - it needs a Docker daemon and the CIRCT worker type is the
        one that has one. It holds the slot for the whole build, which is why
        B1 runs once, before the arms, and never inside an arm window.
    Raises:
        ImageBuildError(step, detail) for a failure at any of steps 2 to 8, with
            *step* the name above and *detail* the command's stderr tail. The
            caller, B12, stops the run: every downstream verdict would be taken
            against an image nobody characterised.
        BuildTimeout(timeout_seconds) when the whole sequence exceeds its
            timeout; the partial image is not pushed and the local tag is
            removed, so a later run does not find a half-built image under the
            key it would have reused.
    """
```

**The timeout is 10,800 s `[DEFAULT]`**, enforced by `subprocess` on the whole sequence and not
per step, which is §3.2's row unchanged. It is chosen against the two measurements this document
already carries: 582 s for the five targets under `-O3 -UNDEBUG -gline-tables-only` at `-j12` (M2)
and 841 s with the slang front end at `-j8` (M7), which together with the base image's own layers,
the SDK download and the two lit runs at about 10 s each (M3) sit an order of magnitude inside it. The
margin is deliberate: a cold Docker cache on a machine with fewer cores is the case the number has to
survive, and a build that is slow is not a build that is wrong.

**The idempotency key is the image tag, and the tag is a hash of the manifest.** §3.2's row gives the
key as `(circt_sha, sdk_tag, tuple(targets), flag_string)`; the tag is that tuple made addressable:

```python
    manifest = {"circt_sha": circt_sha, "sdk_tag": sdk_tag,
                "targets": sorted(targets), "flag_string": flag_string,
                "slang": slang, "base_image": base_image}
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")).hexdigest()
    tag = f"{registry}/chia-circt-assert:{digest[:12]}"
```

so two runs that agree on the ~~five~~ **six** inputs name the same tag and the second reuses the first's image,
and two runs that differ in any one of them cannot collide. `slang` is in the manifest because
ADR-D-13's two branches produce different target lists **and** different binaries from the same
sources, and a tag that did not separate them would let a branch-(b) image answer for a branch-(a)
run. `base_image` joined the manifest 2026-09-14 (§4.11 deviation 1): the SDK is re-installed inside
this Dockerfile, so the base no longer determines the SDK tag, but it still determines the compiler,
the apt set and the `chia` package, and two images built on different bases from the same five other
inputs are different images. The `targets` list is sorted before hashing so that the argument order
the caller chose does not change the tag; the **unsorted** list is what step 2 passes and what
`ImageSpec.targets` records, because that is FR-03.7's parameter.

`BUGLOOP_IMAGE_TAG` (§13.4) is this tag, and §12.1's two CIRCT worker types interpolate it, so the
cluster runs exactly the image the manifest names. `build_image` is the one writer of it and
`bug_loop.py --print-config` prints it.

Every command §3.3, §3.4, §3.5 and §3.7.2 issue, in one place, each with the `analysis/pin_window.py`
line it comes from. **Every one runs on the head**, against the blobless clone at `--clone`, because
that is the only repository in the deployment holding 24 months of `main` (K5): `/workspace/circt`
inside a worker is §4.11's one-commit fetch and §12.1 mounts no clone.

| Purpose | Command | Source |
|---|---|---|
| pin the corpus | `git -C <clone> rev-parse HEAD` | FR-01.11 |
| reset the corpus | `git -C <clone> checkout --detach <corpus_head_sha>` | FR-01.11 |
| list releases | `git -C <clone> for-each-ref --format=%(refname:short)\t%(creatordate:unix) --sort=creatordate refs/tags/firtool-*` | `analysis/pin_window.py:40-41` |
| a tag's pin | `git -C <clone> ls-tree <tag> llvm` | `analysis/pin_window.py:43` |
| head's pin | `git -C <clone> ls-tree HEAD llvm` | `analysis/pin_window.py:70` |
| first-parent history | `git -C <clone> log --first-parent --format=%H\t%ct\t%s HEAD` | `analysis/pin_window.py:52` |
| submodule bumps | `git -C <clone> log --first-parent --raw --no-abbrev --format=COMMIT %H HEAD -- llvm` | `analysis/pin_window.py:60-61` |
| shape filter | `git -C <clone> log --first-parent --name-status --format=COMMIT %H HEAD` | `analysis/pin_window.py:114` |
| test blobs, batched | `git -C <clone> cat-file --batch`, fed `<sha>:<path>` on stdin | M1's method |
| the lag, in commits | `git -C <clone> rev-list --first-parent --count <chosen>..<head>` | FR-02.2 |
| both commit scans | `git -C <clone> log --first-parent -p --unified=0 --no-renames --format=__C__ %H %cI --since <bound> -- <paths>` | M4's method, §3.7.2 |
| the seed's diff | `git -C <clone> show --format= --unified=3 --no-renames <seed_sha> -- <source_paths>` | §3.3 step 6, `SeedRecord.diff` |
| a site's file | `git -C <clone> ls-tree -- <run_commit>:<dir> <basename>` | §3.3 `resolve_sites` |
| a site's symbol | `git -C <clone> grep -n -F -- <symbol> <run_commit> -- <file>` | §3.3 `resolve_sites` |
| `SourceReadTool.read_file` | `git -C <clone> show <run_commit>:<path>` | §3.5 |
| `SourceReadTool.list_dir` | `git -C <clone> ls-tree --name-only <run_commit>:<path>` | §3.5 |

One operational note, measured and worth carrying: on a blobless clone the contamination scan fetches
one blob per round trip and took 488 s over 1,650 commits (M4), where
`git -C <clone> backfill --sparse` over a throwaway sparse worktree bulk-fetches the same objects in
7 s. **B12 runs the backfill once, before the first screen and before the first seeded turn**, and
records that it did; the earlier "may run" left it optional, and with `SourceReadTool` and the seed
diffs now reading the same clone the cold-store cost is paid by the agent's first `read_file` rather
than by the first candidate. `git backfill` is present in the host's `git version 2.55.0`
(`git backfill -h` on 2026-09-14 printed its usage line with `--min-batch-size` and `--[no-]sparse`),
and the image's git is not older.

### 4.13 The flag-verification ledger

| Tool | How verified | Result |
|---|---|---|
| `circt-opt` | `SDK circt-opt --help`, 2026-09-13 | every option of §4.2 present, including both spellings of `--split-input-file` and `--verify-diagnostics` |
| `firtool` | `SDK firtool --help`, 2026-09-13; both lifts also run end to end in M1 | all nine output modes present; `--parse-only` and `--ir-fir` behave as documented |
| `circt-verilog` | `SDK circt-verilog --help`, 2026-09-13; `--ir-moore` run end to end in M1; `--format=` re-checked on 2026-09-14 on **both** the SDK binary and the source-built slang binary at `~/.cache/chia-pin-smoke/bslang/bin` (`CIRCT 5056ff0`, `slang version 11.0.0+0`) and exercised on a lifted Moore IR file | every option of §4.4 present, `--format=` included, with `=sv` and `=mlir` its two values. `--format=mlir` accepted the lift under `--ir-moore`, `--import-only` and `--ir-hw`, rc 0 in all three, which is what makes §4.7's `circt-verilog` branch implementable |
| `circt-translate` | `--help` on both the SDK and the measured assertions-on build, 2026-09-13; re-checked for `--format=` on 2026-09-14 | `--import-verilog` present on the SDK, absent from the slang-less build; **no `--format=` option at all**, which is why §4.7's `circt-translate --import-verilog` branch tests with `circt-opt` and not with its own tool. The slang-enabled build of branch (a) is **not** what `bslang` measured: `bslang/bin` holds `circt-verilog` and `circt-translate` and no `firtool`, `circt-reduce` or `arcilator`, so the six-target branch-(a) build remains unmeasured and is §15 item 2 (NIT 15) |
| `arcilator` | `SDK arcilator --help`, 2026-09-13 | every option of §4.6 present |
| `circt-reduce` | `SDK circt-reduce --help`, 2026-09-13, plus the source for the defaults | every option of §4.7 present; `--keep-best` defaults to `true`, `-o` defaults to `-`, input is `cl::Required` |
| `llvm-symbolizer` | `SDK llvm-symbolizer --help`, 2026-09-13, plus three runs comparing `--functions` modes and `--output-style` | `--functions=short` returns `??` under `-gline-tables-only`; JSON style is newline-delimited, one object per address |
| `verilator` | host `verilator --help` and `--version`, 2026-09-13, plus an invalid-mode run to obtain the accepted values | Verilator 5.052; `--x-initial` takes `0`, `fast`, `unique`; `--x-assign` takes `0`, `1`, `fast`, `unique` |
| `prlimit` | host `prlimit --help` and a run through `--`, 2026-09-13, plus `dpkg` inside `ubuntu:24.04` | `--as`, `--cpu`, `--nofile` and `--` all behave as §4.1 needs; `util-linux 2.39.3-9ubuntu6.6`, essential |
| `timeout` | host `timeout --help`, 2026-09-13 | `-k/--kill-after`, `-s/--signal`, `-f/--foreground` present |
| `cmake`, `ninja` | a fresh SDK-based configure and the measured builds | the configure line of §4.11 runs; `-DMLIR_SOURCE_DIR` reaches `lit.site.cfg.py` |
| `circt-opt --mlir-print-op-generic` | run on 2026-09-14 over real HW IR, one module and two, one clocked | the generic form prints `module_type = !hw.modty<input <name> : <type>, output <name> : <type>>` and `sym_visibility = "private"` on a submodule and not on the top, which is §3.6.3's port-list extraction rule |
| `lit` | `lit --show-tests` over a fresh configure, 2026-09-13 | 1,390 tests discovered, exit 0, no discovery error |
| `git` | every command re-run against the clone | all as `analysis/pin_window.py` uses them |

**One item could not be verified and is marked.** Whether the generated Verilator testbench of §4.10
compiles and runs against a **generated** design is `[UNVERIFIED]`: no harness generator has been
written yet (A-08), and A-19 has not yet said whether any seed is differential-applicable at all.
The flags are verified, and so is the one command §3.6.3's port-list rule runs; the harness is not.
F-08's first implementation task is A-19's count, and the second is FR-08.2's acceptance on the
recorded 12-line FIRRTL register-add, and neither has run. Specifying the generators as code (§3.6.3)
narrows what is unverified from "there is no rule" to "the rule has not been executed", and does not
close it.

---

## 5. Binary resolution, per entry tool

C-16 requires this document to state which binary each entry tool resolves to, and FR-06.1 fixes the
rule: the source-tree binaries under `/workspace/circt/build/bin`, never the SDK's prebuilt ones, with
the SHA-256 of each checked against `ImageSpec.tool_hashes` before every probe.

### 5.1 The table

| Entry tool | Measured path | Built from source | Why |
|---|---|---|---|
| `circt-opt` | `/workspace/circt/build/bin/circt-opt` | yes | FR-03.7's target list; CHIA already builds it |
| `firtool` | `/workspace/circt/build/bin/firtool` | yes | FR-03.7; CHIA already warm-builds it (C-21) |
| `circt-translate` | `/workspace/circt/build/bin/circt-translate` | yes | FR-03.7; and under ADR-D-13 branch (a) this is the binary that carries `--import-verilog` |
| `arcilator` | `/workspace/circt/build/bin/arcilator` | yes | FR-03.7; the differential's arcilator side |
| `circt-reduce` | `/workspace/circt/build/bin/circt-reduce` | yes | FR-03.7's one genuinely new target (C-21); B5 uses the source-built one so the reduced case is parsed by the build that fired |
| `circt-verilog` | `/workspace/circt/build/bin/circt-verilog` | yes, under branch (a) only | its ninja target exists only with slang enabled (C-16) |
| `llvm-symbolizer` | `/opt/circt-sdk/bin/llvm-symbolizer` | no, the SDK's | it is a symboliser, not a compiler: it produces no verdict about CIRCT and the SDK ships it (PIN §5.2). Measured to resolve `file:line` against the assertions-on binary under `-gline-tables-only` (M2) |
| `FileCheck`, `not`, `count`, `split-file` | `/opt/circt-sdk/bin/...` | no, the SDK's | they never appear in a probe argv: step 4 of §3.3's normalisation drops everything from the first unquoted pipe, which is where `FileCheck` lives, and steps 1 and 3 drop `not` and `split-file` wrappers |
| `verilator` | `/usr/bin/verilator` | no, apt's | ADR-D-09 option (a); one version for the whole campaign (FR-03.15) |
| `lit` | `/home/ray/anaconda3/envs/py_worker/bin/lit` | no, pip's, baked once | FR-03.8; the path is the one `circt_warm_build` checks (`chia:chia/chipyard/circt.py:608`) |

`PATH` inside the image already puts the source build ahead of the SDK
(`chia:dockerfiles/ChiaCirctBaseDockerfile:113`), but the loop never relies on `PATH`: every argv names
an absolute path, because a `PATH` lookup is a way for a probe to run a binary nobody recorded.

### 5.2 The hash-manifest check

`ImageSpec.tool_hashes` maps a tool name to the SHA-256 of that binary **in the published image**,
computed from a freshly started container rather than from the build tree (FR-03.16). Before every
probe, before every gate re-run, and before every reduction, the running node hashes the binaries its
argv will invoke and compares. A mismatch is `binary_mismatch`, names the tool and both hashes, does
not run the probe, and **stops the run**, because the tree has been mutated and every verdict from
that worker is suspect (`02-HLD.md` §6, B2's first row).

This replaces FR-06.1's withdrawn `--version` check, which could not detect the one mutation the
system actually performs: CHIA's chain rebuilds with the agent's diff applied
(`chia:examples/circt_issue_solver/issue_task.py:223-224`) and returns without restoring
(`issue_task.py:274-286`), and a source edit followed by a rebuild without a reconfigure leaves the
version string unchanged.

### 5.3 What branch (b) changes

Under ADR-D-13's fallback, `circt-verilog` has no target and `circt-translate` has no
`--import-verilog`, so the 36 seeds whose `RUN:` lines enter through either point are excluded from
discovery **by configuration**: `RunManifest.sv_seeds_excluded` carries their SHAs,
`ImageSpec.slang_enabled` is `false`, `ninja`'s target list drops `circt-verilog`, and A1 marks those
seeds ineligible. No oracle, reducer or gate contains a branch on this; it is a configuration field
two components read (ADR-D-13's HLD consequence). The results artefact and the paper state the
exclusion and its size.
---

## 6. The database, and the artefact tree

### 6.1 How `loop.db` is declared, and where

**A `SQLiteNode` is not declared in a cluster YAML.** It is constructed in Python, on the head, after
`ray.init()`. That is verified rather than assumed: no file under `~/.cache/chia-src` mentions
`SQLiteNode` outside `chia/database/`, `chia/database/test/` and four example modules
(`examples/circt_issue_solver/db.py`, `examples/gem5_align/alignment_db.py`,
`examples/gem5_align/gem5_align_loop.py`, `examples/timing_opt/db.py`), and no cluster YAML in
`examples/` names a database node type or a `database` resource. What the cluster YAML contributes is
the head placement the node pins to, which is `head_setup_commands` activating the driver's conda
environment on the host (`chia:examples/circt_issue_solver/cluster.yaml:89-90`).

The construction, which mirrors CHIA's own (`chia:examples/circt_issue_solver/db.py:60-68`):

```python
class LoopStore:
    """loop.db on the head's local disk, as a SQLiteNode.

    Constructed after ray.init(), because SQLiteNode pins to the current (head)
    Ray node and dispatches its members as Ray tasks. Never on network storage:
    WAL's shared-memory coordination only works between processes on one
    machine (C-14, chia:chia/database/sqlite_node.py:29-33).
    """

    def __init__(self, db_path: str):
        self.node = SQLiteNode(db_path, pin_to_current_node=True)
        get(self.node.init_schema.chia_remote(_SCHEMA))
```

`SQLiteNode.__init__` takes `db_path` first and then `placement_group`, `require_colocated`, and the
keyword-only `node_id`, `pin_to_current_node`, `bundle_index`, `reserve_bundle`, `pg_strategy`,
`wait_for_pg`, `pg_ready_timeout_s` and `connect_opts`
(`chia:chia/database/sqlite_node.py:193-207`); `db_path` must be absolute and the constructor raises
`ValueError` otherwise (`chia:chia/database/sqlite_node.py:220-226`). `pin_to_current_node=True` is
the hard NodeAffinity pin FR-17.3 requires, and it is the flag CHIA's own two head-local databases
use. Defaults the loop relies on and does not override: WAL journal mode, a 30 s busy timeout,
`BEGIN IMMEDIATE` write transactions, `synchronous=NORMAL` and `foreign_keys=ON`
(`chia:chia/database/sqlite_node.py:21-27`).

The members used are `init_schema`, `execute`, `executemany`, `transaction`, `query`, `query_one` and
`query_value` (`chia:chia/database/sqlite_node.py:271-470`). Every write member is already
`@ChiaFunction(num_cpus=0.1, max_retries=0)`, so the loop adds no retry policy of its own. No
`spawn_query_tool` is called: no agent in this design may read the database (FR-04.4, NFR-03).

**Two database files, one machine, one join key.** `loop.db` is the loop's, at
`<repo>/examples/circt_bug_loop/loop.db`; `issues.db` is CHIA's, unchanged, at
`<repo>/examples/circt_issue_solver/issues.db`, written only by CHIA's own code. The only value that
crosses is the synthetic local identifier of §3.8 (ADR-D-11).

### 6.2 `loop.db`, table by table

Every table carries `run_manifest_id` so a row traces to its run (FR-17.6), and every table that has
an artefact carries `artefact_dir` so a row traces to disk (FR-17.2). Types are SQLite's; a `TEXT`
column holding JSON is named `_json` so a reader never has to guess.

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS run (
    run_manifest_id     TEXT PRIMARY KEY,
    mode                TEXT NOT NULL CHECK (mode IN ('discovery','calibration')),
    seed_set            TEXT NOT NULL CHECK (seed_set IN ('187','171')),
    manifest_json       TEXT NOT NULL,       -- the whole RunManifest, canonical JSON
    budget_file_sha     TEXT NOT NULL,
    cluster_yaml_sha    TEXT NOT NULL,
    artefact_root       TEXT NOT NULL,
    started_utc         TEXT NOT NULL,
    ended_utc           TEXT
);

CREATE TABLE IF NOT EXISTS seed (
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    seed_sha            TEXT NOT NULL,
    parent_sha          TEXT NOT NULL,
    subject             TEXT NOT NULL,
    committed_date_utc  TEXT NOT NULL,
    llvm_pin            TEXT NOT NULL,
    sdk_tag             TEXT,
    sdk_exact           INTEGER NOT NULL,
    bumps_away          INTEGER,
    entry_tool          TEXT NOT NULL,
    dialect_bucket      TEXT NOT NULL,
    dialect_bucket_unmerged TEXT NOT NULL,
    eligible_seeded     INTEGER NOT NULL,    -- 0 for FR-01.9 and FR-01.10 exclusions
    eligible_mutation   INTEGER NOT NULL,
    exclusion_reason    TEXT,
    record_json         TEXT NOT NULL,       -- the whole SeedRecord, canonical JSON
    PRIMARY KEY (run_manifest_id, seed_sha)
);

CREATE TABLE IF NOT EXISTS sdk_map (
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    sdk_tag             TEXT NOT NULL,
    seed_shas_json      TEXT NOT NULL,
    PRIMARY KEY (run_manifest_id, sdk_tag)
);

CREATE TABLE IF NOT EXISTS image (
    image_digest        TEXT PRIMARY KEY,
    circt_sha           TEXT NOT NULL,
    sdk_tag             TEXT NOT NULL,
    image_tag           TEXT NOT NULL,
    flag_string         TEXT NOT NULL,
    targets_json        TEXT NOT NULL,
    cmake_args_json     TEXT NOT NULL,
    verilator_version   TEXT NOT NULL,
    slang_enabled       INTEGER NOT NULL,
    lit_discovery_ok    INTEGER NOT NULL,    -- FR-03.17
    lit_discovered_count INTEGER NOT NULL,   -- FR-03.17
    assertion_nonreferencing_json TEXT NOT NULL,
    tool_hashes_json    TEXT NOT NULL,
    built_utc           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS probe (
    probe_id            TEXT PRIMARY KEY,
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    seed_sha            TEXT NOT NULL,
    arm                 TEXT NOT NULL CHECK (arm IN ('seeded','mutation')),
    iteration           INTEGER NOT NULL,
    tool                TEXT NOT NULL,
    argv_json           TEXT NOT NULL,
    polarity            TEXT NOT NULL,
    shape               TEXT NOT NULL,
    input_path          TEXT NOT NULL,
    mutator_id          TEXT,
    mutator_seed_int    INTEGER,
    source_test_path    TEXT,
    spec_json           TEXT NOT NULL,
    artefact_dir        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS probe_result (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    run_manifest_id     TEXT NOT NULL,
    arm                 TEXT NOT NULL,
    iteration           INTEGER NOT NULL,
    build_status        TEXT NOT NULL,
    oracle_fired        INTEGER NOT NULL,
    oracle_class        TEXT,
    stopping_stage      TEXT NOT NULL,
    stopping_reason     TEXT NOT NULL,
    result_json         TEXT NOT NULL,
    artefact_dir        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS build_result (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    run_commit          TEXT NOT NULL,
    image_digest        TEXT NOT NULL REFERENCES image(image_digest),
    status              TEXT NOT NULL,
    binary_path         TEXT NOT NULL,
    binary_sha256       TEXT NOT NULL,
    exit_status         INTEGER,
    signal              TEXT,
    limit_hit           TEXT CHECK (limit_hit IS NULL
                                    OR limit_hit IN ('wall','cpu','address_space')),
    cpu_seconds         REAL NOT NULL,       -- the child's rusage (K8)
    wall_seconds        REAL NOT NULL,
    peak_rss_bytes      INTEGER,
    worker_hostname     TEXT NOT NULL,       -- FR-13.2's pair, original half (K12)
    worker_node_id      TEXT NOT NULL,
    child_pid           INTEGER NOT NULL,
    stdout_path         TEXT NOT NULL,
    stderr_path         TEXT NOT NULL,
    truncated           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS oracle_verdict (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    fired               INTEGER NOT NULL,
    oracle_class        TEXT,
    assertion_text      TEXT,
    assertion_site      TEXT,
    fatal_message       TEXT,
    frames_json         TEXT NOT NULL,
    prologue_dropped    INTEGER NOT NULL,    -- 3.7.1's strip, so the count is auditable
    frames_resolved     INTEGER NOT NULL,
    frames_with_location INTEGER NOT NULL,
    fingerprint_frame   TEXT,                -- "<function> <basename>", NULL when none qualifies
    out_of_scope_root   INTEGER NOT NULL,
    repro_command       TEXT NOT NULL,
    flag_string         TEXT NOT NULL,
    tool_version_output TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS differential_verdict (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    verdict             TEXT NOT NULL,
    reason              TEXT NOT NULL,
    verilator_version   TEXT NOT NULL,
    x_policy            TEXT NOT NULL,
    stimulus_id         TEXT NOT NULL,
    port_list_sha       TEXT NOT NULL,       -- computed by B4 (3.6.3), '' on a harness_failure
    cycles              INTEGER NOT NULL,
    first_divergent_signal TEXT,
    first_divergent_cycle  INTEGER,
    arcilator_value     TEXT,
    verilator_value     TEXT,
    arcilator_trace_path TEXT,
    verilator_trace_path TEXT,
    driver_source       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reduced_case (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    reducer             TEXT NOT NULL CHECK (reducer IN ('circt-reduce','textual-ddmin','none')),
    reduced             INTEGER NOT NULL,
    fixpoint            INTEGER NOT NULL,
    budget_truncated    INTEGER NOT NULL,
    reason              TEXT,
    lift                TEXT,
    path                TEXT NOT NULL,
    size_before_bytes   INTEGER NOT NULL,
    size_after_bytes    INTEGER NOT NULL,
    size_before_ops     INTEGER NOT NULL,
    size_after_ops      INTEGER NOT NULL,
    wall_seconds        REAL NOT NULL,
    interestingness_calls INTEGER NOT NULL,
    recheck_class       TEXT,
    recheck_assertion_text TEXT,
    recheck_assertion_site TEXT,
    recheck_matches     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate (
    candidate_id        TEXT PRIMARY KEY,
    local_id            INTEGER UNIQUE,      -- LOCAL_ID_BASE + rowid, set at repair time
    probe_id            TEXT NOT NULL UNIQUE REFERENCES probe(probe_id),
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    arm                 TEXT NOT NULL,
    run_commit          TEXT NOT NULL,
    image_digest        TEXT NOT NULL,
    oracle_class        TEXT NOT NULL,
    assertion_text      TEXT,
    assertion_site      TEXT,
    frame_tuple_json    TEXT NOT NULL,
    out_of_scope_root   INTEGER NOT NULL,
    contaminated_symbol INTEGER NOT NULL,
    contaminated_file   INTEGER NOT NULL,
    contamination_lower_bound TEXT NOT NULL,
    triage_class        TEXT NOT NULL,
    held_reason         TEXT,
    taxonomy_bucket     TEXT,
    artefact_dir        TEXT NOT NULL,
    created_utc         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fingerprint (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    basis               TEXT NOT NULL CHECK (basis IN ('assertion','frames','insufficient')),
    value               TEXT,
    fingerprint_stable  INTEGER,             -- set by the gate re-run; NULL until it runs (K3)
    frame_tuple_json    TEXT NOT NULL,       -- evidence, never a merge key
    structural_hash     TEXT NOT NULL,       -- evidence, never a merge key
    -- FR-10.8 as a CHECK rather than as a comment: three sibling columns in this
    -- DDL carry CHECKs and this rule is the one a wrong INSERT would break
    -- silently (NIT 4).
    CHECK ((value IS NULL) = (basis = 'insufficient'))
);

CREATE TABLE IF NOT EXISTS dedup_verdict (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    verdict             TEXT NOT NULL,
    evidence_json       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    path                TEXT NOT NULL,
    template            TEXT NOT NULL CHECK (template IN ('primary','differential')),
    title               TEXT NOT NULL,
    classification      TEXT NOT NULL,
    classification_reason TEXT NOT NULL,
    rendered_sha256     TEXT NOT NULL,
    assisted_by         TEXT NOT NULL,
    fields_present_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repair (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    local_id            INTEGER NOT NULL,
    status              TEXT NOT NULL,
    failing_phase       TEXT,
    reproduced          INTEGER,
    build_ok            INTEGER,
    fixed               INTEGER,
    lit_ok              INTEGER,
    lit_unusable        INTEGER NOT NULL,    -- FR-12.8's erratum
    lit_passed          INTEGER,
    lit_failed          INTEGER,
    lit_failures_json   TEXT NOT NULL,
    diff_path           TEXT,
    diff_added          INTEGER,
    diff_removed        INTEGER,
    chia_artifact_dir   TEXT,
    chia_row_seen       INTEGER NOT NULL DEFAULT 0,   -- set by B12's reconciliation
    repro_dir           TEXT NOT NULL,       -- outside /workspace/circt (K9)
    repro_overwritten   INTEGER NOT NULL,    -- the reproduce turn replaced our script
    restore_ok          INTEGER NOT NULL,
    restore_hashes_match INTEGER NOT NULL,   -- FR-12.11's re-hash (W21)
    restore_log         TEXT NOT NULL,
    backend             TEXT NOT NULL,       -- cfg["backend"], "vertex" by default (3.8)
    token_capture       TEXT NOT NULL        -- why stage 7's tokens are not observed (3.8)
);

CREATE TABLE IF NOT EXISTS gate_decision (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    answers_json        TEXT NOT NULL,       -- the fifteen keys of 02-HLD.md 2.11
    stopped_at_question INTEGER,
    decision            TEXT NOT NULL CHECK (decision IN ('report','report_plus_patch','nothing')),
    taxonomy_bucket     TEXT,
    decided_utc         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS filing (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    approver            TEXT NOT NULL,
    approved_at_utc     TEXT NOT NULL,
    decision            TEXT NOT NULL,
    licence_confirmed   INTEGER,
    licence_confirmed_at_utc TEXT,
    url_source          TEXT CHECK (url_source IN ('poll','pasted')),
    issue_number        INTEGER,
    issue_url           TEXT,
    prefill_url_length  INTEGER,
    prefill_fallback_reason TEXT,
    confirmed           INTEGER NOT NULL DEFAULT 0,
    confirmed_at_utc    TEXT,
    confirmation_url    TEXT
);

CREATE TABLE IF NOT EXISTS ledger_entry (
    entry_id            TEXT PRIMARY KEY,
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    arm                 TEXT NOT NULL CHECK (arm IN ('seeded','mutation','shared')),
    scope               TEXT NOT NULL CHECK (scope IN ('arm_window','stage')),
    stage               TEXT NOT NULL,
    unit                TEXT NOT NULL CHECK (unit = 'wall_clock_seconds'),
    amount              REAL NOT NULL CHECK (amount >= 0),
    metered             INTEGER NOT NULL,
    observed_json       TEXT NOT NULL,
    timestamp_utc       TEXT NOT NULL,
    stop_reason         TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    seed_sha            TEXT NOT NULL,
    arm                 TEXT NOT NULL,
    iteration           INTEGER NOT NULL,
    path                TEXT NOT NULL,       -- feedback.json in the iteration directory
    abandoned           INTEGER NOT NULL,
    abandon_reason      TEXT,
    terminating_condition TEXT,
    PRIMARY KEY (run_manifest_id, seed_sha, arm, iteration)
);

CREATE TABLE IF NOT EXISTS issue_mirror (
    issue_number        INTEGER PRIMARY KEY,
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    labels_json         TEXT NOT NULL,
    state               TEXT NOT NULL CHECK (state IN ('open','closed')),
    url                 TEXT NOT NULL,
    mirrored_utc        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issue_mirror_meta (
    run_manifest_id     TEXT PRIMARY KEY REFERENCES run(run_manifest_id),
    refreshed_utc       TEXT NOT NULL,
    issues_mirrored     INTEGER NOT NULL,
    issue_cap           INTEGER NOT NULL,
    cap_bound           INTEGER NOT NULL,
    state               TEXT NOT NULL,
    comments_mirrored   INTEGER NOT NULL CHECK (comments_mirrored = 0)
);
```

**The mirror is read-only after its one refresh**, which is a rule rather than a permission: B6a is
the only writer, it runs once per run before the first candidate is screened, and B6b reads it and
makes no GitHub request of its own (FR-10.3's network-trace criterion). The `CHECK
(comments_mirrored = 0)` is the schema stating FR-20.4's boundary: no maintainer's words are in the
database at all, so none can reach a prompt.

### 6.3 Indexes

Nine, each earning its place by a query a requirement makes.

```sql
CREATE INDEX IF NOT EXISTS ix_probe_run_seed_iter   ON probe(run_manifest_id, seed_sha, iteration);
CREATE INDEX IF NOT EXISTS ix_probe_result_run_arm  ON probe_result(run_manifest_id, arm);
CREATE INDEX IF NOT EXISTS ix_candidate_run_arm     ON candidate(run_manifest_id, arm);
CREATE INDEX IF NOT EXISTS ix_candidate_bucket      ON candidate(taxonomy_bucket);
CREATE INDEX IF NOT EXISTS ix_fingerprint_value     ON fingerprint(value);
CREATE INDEX IF NOT EXISTS ix_ledger_run_arm_scope  ON ledger_entry(run_manifest_id, arm, scope);
CREATE INDEX IF NOT EXISTS ix_ledger_day            ON ledger_entry(substr(timestamp_utc, 1, 10));
CREATE INDEX IF NOT EXISTS ix_mirror_state          ON issue_mirror(state);
CREATE INDEX IF NOT EXISTS ix_filing_confirmed      ON filing(confirmed);
```

`ix_fingerprint_value` is the one that carries a requirement rather than a convenience: FR-10.6 makes
fingerprints queryable **across runs**, so the lookup that finds a duplicate from an earlier run is a
point query on this index and not a table scan. `ix_ledger_day` is the per-UTC-day safety caps of
FR-13.8 and FR-14.1, which are counted by calendar day and not by rolling window.

**No index serves §3.7.3's issue-mirror screen, and that is deliberate.** Its predicate is
`instr(title || ' ' || body, :token) > 0`, a substring test on a computed expression, which no
B-tree index can serve; the alternative, an FTS5 virtual table, is a second schema and a tokeniser
whose word-splitting would change what "a match on the assertion text" means. `issue_mirror_issue_cap`
is 20,000, so the scan reads at most 20,000 rows once per token and at most twice per candidate, and
the candidate count in an 8-hour campaign is two orders of magnitude below the point where that
matters. `ix_mirror_state` above serves the state filter, not the match.

### 6.4 Write order, and the two rules that are not conventions

1. **The loop's row is written before CHIA's** (FR-12.10). `repair_adapter` inserts the `candidate`
   row's `local_id` and the `repair` row **before** invoking `run_issue_remote`; CHIA's own
   unmodified `db.record` then writes its `attempts` row. B12's end-of-run reconciliation queries
   `issues.db` for each `local_id` and sets `repair.chia_row_seen`; a loop row whose counterpart
   never appears is marked `repair_row_missing` in `candidate.held_reason`. The order exists because
   `SQLiteNode` opens a fresh connection per `chia_remote` call
   (`chia:chia/database/sqlite_node.py:21-27`), so one transaction cannot span two files.
2. **A candidate row exists before any verdict row that references it.** `fingerprint`,
   `dedup_verdict`, `report`, `repair`, `gate_decision` and `filing` all carry a foreign key to
   `candidate`, and `PRAGMA foreign_keys = ON` is a `SQLiteNode` default, so the order is enforced by
   SQLite rather than by discipline.
3. **`ledger_entry` is append-only.** Nothing updates or deletes a row. A duplicate `entry_id` is a
   primary-key violation, which is how a double charge is detected rather than absorbed.
4. **Multi-row writes that must not tear go through `SQLiteNode.transaction`**, which is
   `BEGIN IMMEDIATE`, each op in order, `COMMIT`, with any error rolling the whole batch back
   (`chia:chia/database/sqlite_node.py:377-423`). Two places use it: the candidate row plus its
   `fingerprint` and `dedup_verdict` rows, and the `gate_decision` row plus the `candidate` row's
   `taxonomy_bucket` update.

### 6.5 The artefact tree, field by field

One path, visible from the head and from every worker at the same absolute path, recorded in
`RunManifest.artefact_root` (FR-17.9). On the single-machine deployment it is one host directory
bind-mounted into every worker container at the identical path (§12.1).

```
<artefact_root>/
  <run_manifest_id>/
    manifest.json                     canonical JSON, the whole RunManifest
    budget.yaml                       a copy of the committed file, for the record
    corpus/
      seeds.json                      canonical JSON, list[SeedRecord]
      sdk_map.json                    canonical JSON, the SdkMap
      counts.json                     FR-01.10's polarity, shape and exclusion counts
    image/
      image_spec.json                 canonical JSON, the ImageSpec
      lit_discovery.txt               FR-03.17's lit --show-tests output
      assertion_objects.txt           FR-03.5's non-referencing object list, one per line
      build.log                       the ninja log tail
    gate/
      <candidate_id>/                 gate_rerun's fresh working directory, one per re-run
        rerun.stdout.txt
        rerun.stderr.txt
    repair/
      <local_id>/                     B8's repro directory, OUTSIDE /workspace/circt (3.8, K9)
        repro.sh                      pre-written by the loop, then possibly rewritten by the turn
        case.<ext>                    the reduced case the script runs
        repro.sh.sha256.before        the hash B8 takes before the chain starts
        repro.sh.sha256.after         the hash B8 takes after the reproduce turn
    seed_<seed_sha>/
      iter_<n>/
        feedback.json                 canonical JSON, the FeedbackBundle A5 built for this iteration
        llm_seed_read.md              the stage-1 turn's streamed transcript
        llm_seed_read.stderr
        llm_seed_read.jsonl           the raw session transcript (.db on the antigravity backend)
        llm_seed_read.usage.json      the backend's reported usage, or {} where it reports none
        llm_probe_write.md            the stage-2 turn, same five files
        llm_probe_write.stderr
        llm_probe_write.jsonl
        llm_probe_write.usage.json
        probe_<probe_id>/
          input.<ext>                 the probing input, verbatim; ext from the tool's language
          spec.json                   canonical JSON, the ProbeSpec
          argv.json                   the full argv actually executed, prlimit prefix included
          stdout.txt                  capped at probe_output_byte_cap
          stderr.txt                  capped at probe_output_byte_cap
          build_result.json
          oracle_verdict.json
          frames.json                 the symbolised frames, one JSON object per frame
          repro.sh                    FR-07.6's reproducing command, executable
          interesting.sh              the interestingness script of section 10.2, executable.
                                      Candidates and probes are 1:1 (candidate.probe_id is
                                      UNIQUE), so section 10.2's "per candidate" and this
                                      tree's "per probe" name the same directory; this tree
                                      is the normative one and 10.2 now says "per probe"
                                      too (NIT 16).
          reduced.<ext>               the reduced case, present iff a reducer produced output
          reduced_case.json
          harness.mlir                the arcilator harness gen_arc_harness wrote (3.6.3)
          dut.sv, tb.sv               the Verilator harness, the design and gen_verilator_tb's bench
          port_list.json              canonical JSON, the Port list extract_port_list returned
          arcilator.out.txt           arcilator's stdout, the BUGLOOP lines the differ compared
          verilator.out.txt           the Verilator binary's stdout, the same shape
          arcilator.vcd               the arcilator trace, evidence, never parsed
          verilator.vcd               the Verilator trace, evidence, never parsed
          differential_verdict.json
          report.md                   the rendered report
          llm_report_write.md         the stage-6 turn, with its four companions as above
          PARTIAL                     present iff the stage that owned this directory died
    results/
      counters.json                   FR-17.4's per-stage CounterBlocks, rewritten on every
                                      aggregation so a running campaign can be read (13.1)
      results.md                      the rendered results artefact
      results.json                    the same numbers, machine-readable
      taxonomy.json                   FR-18.6's six buckets and their counts
      divergences.md                  FR-18.12's list
```

**Formats.** Every `.json` file is canonical JSON by §2.3's rule: UTF-8, no BOM, keys sorted, two-space
indent, one trailing newline. Every `.txt` is UTF-8 text decoded with `errors="backslashreplace"`.
Every `.sh` is `#!/bin/sh` with mode 0755. `.vcd` and `.mlir` are whatever the tool wrote, byte for
byte.

**The `PARTIAL` marker** (FR-17.8) is a zero-byte file named `PARTIAL` written by the stage **before**
it begins writing anything else into a directory, and removed by the stage as its last act. A stage
that crashes therefore leaves the marker behind, together with whatever it had written, and nothing
is deleted. `artefact_write` refuses to remove a marker for a directory whose completion record is
absent from the store, so a marker cannot be cleared by a later stage that merely passed through.

**The cap rule.** Anything larger than `artefact_inline_cap_bytes` is on disk and referenced by path,
never inlined into a row or a task return value (FR-17.7,
`chia:chia/database/sqlite_node.py:35-38`). The three text fields the contract bounds are
`ProbeSpec.input_text`, `ProbeResult.reduced_text` and `FeedbackEntry.reduced_text`, and
`contract.bound_text` is the one place the rule is applied (§2.8). The companion path field is always
populated, so nothing is ever lost by the cap.

**The cap is 262,144 bytes `[DEFAULT]` and was 10,485,760** (W26). Ten megabytes contradicted the
guidance this paragraph itself quotes, `SQLiteNode`'s own "Store large artifacts as files and put
*paths* in the DB; multi-MB blobs inflate the object store and every `get()`"
(`chia:chia/database/sqlite_node.py:35-38`): a 9 MB `input_text` would have passed `bound_text`,
ridden the Ray object store and landed in `probe.spec_json`. 262,144 is 256 KiB, the same order as the
256,000-byte figure CHIA's own example uses for the same decision
(`chia:examples/circt_issue_solver/issue_task.py:268`), and is chosen for that reason rather than
inherited from it: CHIA's figure is one line of one example choosing which repro files to inline in a
return dict, not a framework limit. It is also the cap on a `SourceReadTool` return (§3.5) and on a
`SeedRecord`'s `diff` and `test_files` (§2.4), which is one number doing three jobs and is why it is a
`budget.yaml` key rather than three constants. A probing input above it is on disk and named by
`input_path`, which is exactly what FR-04.3's erratum permits.

**`BudgetFile` has no table, and that is the design rather than an omission** (NIT 5). It is a
contract member because both halves read it (`02-HLD.md` §2.1) and because its `budget_file_sha` is
the pre-registration every stage compares against, but its contents are already persisted twice: the
committed `budget.yaml` in the repository, which is the registration, and the copy of that file at
`<run>/budget.yaml` above, which is the artefact copy. A third copy in a `budget_file` table would be
a row that can disagree with both. What `loop.db` stores instead is the one field a query needs,
`run.budget_file_sha`, which is what FR-14.7's mid-campaign comparison reads.

**Secrets.** Nothing under this tree ever contains a token, a key or a credential (FR-17.5, NFR-06).
The check is a grep of the whole tree for the `GITHUB_TOKEN` value and for any model API key, run by
`04-Test-Plan.md`; §11 is the design that makes it pass by construction rather than by luck.
---

## 7. The prompts, in full

Three prompts drive the three agent stages; a fourth, the offline mutator synthesis, is §8.3. All
four are rendered exactly as CHIA renders its own, with `Template(...).safe_substitute(**kw)` and
never `str.format`, because MLIR and shell braces would break substitution
(`chia:examples/circt_issue_solver/issue_task.py:138-141`):

```python
    def _render(key: str, **kw) -> str:
        return Template(cfg[key]).safe_substitute(**kw)
```

`safe_substitute` leaves an unknown `$name` in place rather than raising, which is the behaviour
wanted: a `$` inside a pasted diff is left alone. The prompts below therefore use `$name` for every
substitution point and contain no other `$` anywhere, including inside their JSON examples.

### 7.1 The output contract, and what happens when it is not met

Every one of the four prompts ends by demanding a single fenced JSON block. The parser is one
function, shared by all four:

```python
_JSON_BLOCK = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)


def parse_json_footer(text: str, required: tuple[str, ...]) -> dict:
    """Parse the LAST fenced json block of a turn's output.

    The last block wins, which is the same rule CHIA's assess parser uses for
    its DECISION footer: a model that reconsiders mid-answer leaves both, and
    the final one is the answer (chia:examples/circt_issue_solver/issue_task.py:28-29).

    _JSON_BLOCK is non-greedy, so finditer yields every block in order and the
    body is the LAST match's group; re.search would yield the first and would be
    the opposite rule. That one line is the whole implementation and is stated
    because "the last block wins" was asserted and not specified (NIT 17):

        blocks = list(_JSON_BLOCK.finditer(text))
        if not blocks: raise PromptContractError("no_block")
        body = blocks[-1].group("body")

    Returns:
        the decoded object, which must be a dict carrying every key in
        *required*.
    Raises:
        PromptContractError(reason) with reason one of "no_block",
        "not_json", "not_object" or "missing:<key>".
    """
```

`PromptContractError` is **not** retried inside the turn and **never** repaired by guessing. What
happens next is per stage and is already a requirement:

- **Stages 1 and 2 (A3).** The iteration for that seed records
  `failure="prompt_contract:<reason>"`, charges the ledger for what the turn spent, and continues
  with the next seed. That is FR-04.8's rule applied to a malformed answer rather than to a backend
  error, and the failure taxonomy counts it. Nothing partial is emitted: a stage-2 turn whose footer
  will not parse yields **zero** `ProbeSpec`s even if files were written, because a spec needs an
  argv the agent has to state.
- **Stage 6 (B7).** The candidate is carried to the gate with `classification="untriaged"` and an
  empty report, receives all four mechanical answers as usual, and is **held** from the human with
  `held_reason=no_report` if it passes. That is FR-11.8 exactly.

The raw turn output is persisted whatever happens (FR-04.6, FR-11.7), so a contract failure is
inspectable rather than merely counted.

### 7.2 `prompts/seed_read.md`, stage 1

Substitution variables: `$seed_sha`, `$subject`, `$diff`, `$test_files`, `$run_lines`,
`$entry_tool`, `$max_sites`. **Every one comes from the `SeedRecord`**, and that is what contract 2.0
bought: `$diff` is `seed.diff`, `$test_files` is `seed.test_files` rendered as one
`==> <path> <==`-headed block per entry in `test_paths` order, `$run_lines` is
`"\n".join(seed.run_lines)`, and the other four are fields the record already had. FR-16.5's
"replaying iteration k from its recorded `SeedRecord` plus `FeedbackBundle` reproduces the same
prompt bytes" is therefore true by construction; before this revision `$diff` and `$test_files` had no
source in either object and FR-16.5 was unsatisfiable (K6).

```markdown
You are reading one CIRCT bug fix in order to look for the same mistake somewhere
else. You are NOT fixing anything and you are NOT writing any input this turn.

Fix commit: $seed_sha
Subject: $subject
Entry tool for this seed's tests: $entry_tool

The fix, as a diff:

~~~diff
$diff
~~~

The test files it changed:

~~~
$test_files
~~~

The lit RUN: lines in those tests, verbatim:

~~~
$run_lines
~~~

You have three READ-ONLY MCP tools over the CIRCT source at the run's commit:
read_file(path), grep(pattern, path_prefix) and list_dir(path). Use them to read
source, search for a symbol, and read the dialect docs and the op
summary/description fields in the *.td files. There is no shell, no build tool
and no test tool this turn, by design: nothing you can call changes anything or
measures anything.

Do two things, in this order.

PART A - THE ROOT CAUSE CLASS.
  State, in ONE sentence, the KIND of mistake this fix corrected. A class, not an
  instance: "a pass assumed every operand of an operation is of the same width"
  is a class; "commit abc123 fixed FooOp" is not. The sentence must be usable as
  a search key by someone who has never seen this commit.

PART B - SIBLING SITES.
  Name up to $max_sites OTHER places in CIRCT where the same class of mistake
  plausibly still applies. A site is a file path and a symbol in that file, and
  BOTH must exist in the tree right now - check each one with grep before you
  name it, because a site that does not resolve is discarded and wastes the
  budget that produced it.
  Prefer sites that are analogous in structure rather than merely nearby in the
  directory tree: the same pattern in a different dialect is a better sibling
  than the next function down in the same file.
  For each site give one short clause saying why the class applies there.

Be honest about a weak seed. If the fix is a typo, a comment, a test-only change,
or something with no transferable class at all, say so in Part A and return an
EMPTY sibling list. An empty list is a correct answer and is recorded as one; an
invented list is not.

End your response with EXACTLY one fenced json block, and nothing after it:

```json
{
  "root_cause_class": "one sentence, as in Part A",
  "sibling_sites": [
    {"file": "lib/Dialect/Comb/CombFolds.cpp", "symbol": "foldExtract",
     "why": "one short clause"}
  ]
}
```
```

**The emitter** requires `root_cause_class` and `sibling_sites`. Every site is resolved before it is
recorded, by dispatching `corpus.resolve_sites` (§3.3) on the head, which runs one
`git -C <clone> ls-tree -- <run_commit>:<dir> <basename>` and one
`git -C <clone> grep -n -F -- <symbol> <run_commit> -- <file>` per site against the head's clone. A
site that fails either check is counted in `rejected_sites` with its reason and discarded, which is
FR-04.1's acceptance criterion. The resolution is dispatched rather than run in place because A3 is on
a `circt` worker and the clone is on the head (K5); it is the one query an arm still makes of the
tree. `$max_sites` is `budget.yaml`'s `per_seed_probe_cap`, because more sibling sites than probes
would be proposals nothing can act on.

### 7.3 `prompts/probe_write.md`, stage 2

Substitution variables: `$seed_sha`, `$root_cause_class`, `$sibling_sites`, `$entry_tool`,
`$argv_template`, `$language`, `$probe_dir`, `$cap`, `$feedback`.

```markdown
You are writing probing inputs for CIRCT, from the root-cause class and the
sibling sites of the previous turn. Each input is one small program that, if the
class of mistake really does apply at a site, makes the compiler crash or fire
one of its own assertions.

Seed: $seed_sha
Root-cause class: $root_cause_class

Sibling sites you named:

~~~
$sibling_sites
~~~

What the previous iteration's inputs did, if there was one:

~~~
$feedback
~~~

Write AT MOST $cap inputs. The language is fixed by the seed and is $language;
the tool that will consume them is fixed too and is $entry_tool, invoked with
this argument template, where INPUT is the file you write:

~~~
$argv_template
~~~

Rules that are not negotiable.

  1. Use the write_probe tool to write each input. It takes a bare file name and
     the file's content, and it writes into this iteration's probe directory. It
     will refuse a name with a directory part.
  2. Each input must be SELF-CONTAINED and as small as you can make it. Aim for
     something a maintainer can read in one screen. A large input that crashes
     is worth less than a small one, because the reducer has to shrink it anyway
     and a reduction that changes the failure is thrown away.
  3. Each input must be VALID for its language as far as you can make it. The
     interesting failures are the ones where valid input breaks the compiler; an
     input the parser rejects is recorded as a parse error and tells nobody
     anything.
  4. Target a specific sibling site. For each input, say which one.
  5. You cannot run the compiler and there is nothing here that would let you:
     your only tools are write_probe and the three read-only source tools. What
     your inputs do is measured by the apparatus, not reported by you.

State for each input what you expect to happen, in one clause, in the compiler's
own terms: which pass or which check you expect to break, not "it will crash".
Your expectation is recorded and compared with what actually happened; being
wrong is informative and is not penalised.

Write the files FIRST, then end your response with EXACTLY one fenced json block
describing what you wrote, and nothing after it. Name only files you actually
wrote successfully; a name in this block with no file behind it is dropped and
counted.

```json
{
  "probes": [
    {"filename": "extract_width.mlir",
     "site": "lib/Dialect/Comb/CombFolds.cpp:foldExtract",
     "expected_outcome": "the width assertion in foldExtract fires"}
  ]
}
```
```

**The emitter** requires `probes`, and per entry `filename`, `site` and `expected_outcome`. The argv
is **not** taken from the agent: it is built by substituting the written file's path into the seed's
own `argv_template`, which is what makes FR-04.2's "tool equals the seed's classified tool" true by
construction rather than by validation. An entry naming a file `ProbeWriteTool` did not write is
dropped and counted. Beyond `$cap` entries the list is truncated, keeping the **first** `cap` in the
agent's emission order, with the truncation and the discarded count recorded (FR-04.5).

### 7.4 `prompts/report_write.md`, stage 6

Substitution variables: `$oracle_class`, `$assertion_text`, `$assertion_site`, `$frames`,
`$repro_command`, `$reduced_case`, `$dedup_verdict`, `$dedup_evidence`, `$build_identity`,
`$max_sentences`, and for a `differential` candidate `$arcilator_behaviour`,
`$verilator_behaviour`, `$stimulus`.

**One prompt, two fillings** (W23). A `differential` candidate has no assertion, no frames (FR-08.10)
and no reduced case (FR-09.8), so the six primary variables above have nothing to substitute; the
prompt is rendered with `Template.safe_substitute`, which leaves an unbound `$name` in place, and an
unbound `$frames` in a prompt is a defect rather than a blank. The rule is therefore explicit: for a
`differential` candidate the six primary variables are bound to the literal string
`"not applicable to a differential candidate"`, the three differential variables are bound from the
`DifferentialVerdict`, and the two `PART A` and `PART B` blocks below are followed by the
differential clause. `tests/test_triage_task.py` renders both fillings and asserts no `$` survives in
either.

```markdown
A CIRCT failure has been found, reduced and screened by tools. Your job is to
write the prose a maintainer reads, and to give one advisory opinion. Every
NUMBER, hash, path and verdict in the final report is filled in from the record
by the renderer - you do not restate any of them, and anything numeric you write
is discarded.

What the tools found:

  Failure class: $oracle_class
  Assertion text: $assertion_text
  Assertion site: $assertion_site
  Top symbolised frames:

~~~
$frames
~~~

  The command that reproduces it:

~~~
$repro_command
~~~

  The reduced case:

~~~
$reduced_case
~~~

  Duplicate screen: $dedup_verdict
  Evidence: $dedup_evidence
  Build identity: $build_identity

You have three READ-ONLY source tools, read_file(path), grep(pattern,
path_prefix) and list_dir(path), over CIRCT at the run's commit. Read the code
around the frames before you write. There is no shell and no build tool.

If the failure class above is "differential" there are no frames, no assertion
and no reduced case, and the two behaviours below are what you have:

  arcilator observed: $arcilator_behaviour
  Verilator observed: $verilator_behaviour
  The one stimulus both were driven with: $stimulus

PART A - CLASSIFY, ADVISORILY.
  One of: bug, invalid_input, known_issue.
    bug           - the input is legitimate and CIRCT is at fault.
    invalid_input - the input violates a documented precondition, so the tool was
                    entitled to refuse, though not to crash.
    known_issue   - this is already reported or already fixed.
  Give your reason in at most $max_sentences sentences.
  This opinion is SHOWN to the human approver and is read by NO gate. Say what
  you actually think. If the duplicate screen already says this is known, your
  classification is overridden to known_issue whatever you write, and only your
  reason survives.

PART B - WRITE THE PROSE.
  title           one line, in the form "[Dialect/Area] short imperative summary".
  summary         two or three sentences: what the input does and what CIRCT does
                  with it. Describe OBSERVED behaviour only.
  why_it_matters  one or two sentences: what this suggests about the code, and
                  where a maintainer might look first. If you do not know, say
                  the frames are where you would start.

Do NOT write an "expected behaviour" section and do NOT say what the fix should
be. For this class of report, stating what the compiler ought to have done is a
design opinion, and the report is stronger without one.

Do NOT use the words "crash" or "assertion" if the failure class above is
fatal_error: that path is a refusal CIRCT chose deliberately, and calling it a
crash is how a maintainer's tolerance gets spent.

If the failure class above is differential, describe BOTH behaviours and say
which signal at which cycle differed, and do NOT say which of the two is
correct. Nobody has adjudicated it and the report does not claim to.

End your response with EXACTLY one fenced json block, and nothing after it:

```json
{
  "classification": "bug",
  "reason": "at most the stated number of sentences",
  "title": "[Comb] short imperative summary",
  "summary": "two or three sentences of observed behaviour",
  "why_it_matters": "one or two sentences"
}
```
```

#### 7.4.1 The rendered report, and its substitution points

`report.md` is rendered by the loop from a fixed template, not by the agent. The template has exactly
these substitution points; `tests/test_triage_task.py` asserts each against the record, which is
FR-11.4's criterion, and `render_report` refuses to render with any of them missing, which is
FR-11.3's.

| Point | Source | FR |
|---|---|---|
| `title` | the agent's prose | FR-11.3 |
| `summary` | the agent's prose | FR-11.3 |
| `observed_behaviour` | `OracleVerdict.oracle_class`, `assertion_text`, `assertion_site`, and for a `fatal_error` the quoted `LLVM ERROR:` message | FR-07.10, FR-11.3 |
| `reduced_case` | the contents of `ReducedCase.path`, verbatim, in a fenced block | FR-11.3 |
| `repro_command` | `OracleVerdict.repro_command` | FR-11.3 |
| `build_identity` | `ImageSpec.circt_sha`, `sdk_tag`, `image_digest`, the literal `-UNDEBUG`, and `OracleVerdict.tool_version_output` | FR-03.11, FR-11.3, C-08 |
| `frames` | `OracleVerdict.frames`, the top `fingerprint_top_n`, as `function file:line` | FR-11.3 |
| `dedup_evidence` | `DedupVerdict.verdict` plus its evidence keys | FR-10.5, FR-11.3 |
| `arm` | `CandidateRecord.arm` | FR-11.3 |
| `contamination` | both flags and the bound used | FR-15.1, FR-15.2 |
| `fingerprint` | `Fingerprint.value` | FR-13.16, which needs it in the filed body |
| `why_it_matters` | the agent's prose | FR-11.3 |
| `assisted_by` | `Assisted-by: <backend>:<model id>`, the last line of the file | FR-11.6, FR-20.3 |

**The `differential` template's substitution points**, stated as their own list because the earlier
sentence was self-contradictory, dropping `observed_behaviour` and carrying "both arms' observed
behaviour" in one clause (W23):

| Point | Source | FR |
|---|---|---|
| `title` | the agent's prose | FR-11.3 |
| `summary` | the agent's prose | FR-11.3 |
| `arcilator_behaviour` | `DifferentialVerdict.arcilator_value` and `arcilator_trace_path` | FR-08.6 |
| `verilator_behaviour` | `DifferentialVerdict.verilator_value` and `verilator_trace_path`, plus `verilator_version` | FR-08.6, FR-03.15 |
| `divergence_point` | `first_divergent_signal` and `first_divergent_cycle` | FR-08.6 |
| `stimulus` | `ProbeSpec.differential`'s five keys | FR-08.3 |
| `x_policy` | `DifferentialVerdict.x_policy` | FR-08.4 |
| `prior_art` | the literal `circt/arc-tests` and `RunManifest.differential_driver` | FR-08.7, FR-08.11 |
| `build_identity` | as the primary template | FR-03.11 |
| `arm` | `CandidateRecord.arm` | FR-11.3 |
| `why_it_matters` | the agent's prose | FR-11.3 |
| `assisted_by` | as the primary template | FR-11.6, FR-20.3 |

There is **no** `observed_behaviour` point, because the two behaviour points above replace it; no
`frames`, `reduced_case`, `repro_command`, `dedup_evidence`, `contamination` or `fingerprint` point,
because a `differential` candidate has none of them (FR-08.10, FR-09.8, FR-13.14); and no
expected-behaviour field at all. `render_report` refuses on a missing point of the template it was
given, so the two lists are enforced separately rather than as one superset. A test asserts the
rendered text contains neither the word "expected" nor any sentence naming a correct arm.

The `Assisted-by:` trailer names the backend and the model id **actually used** for that candidate's
turn, read from `RunManifest.model_ids["triage_report"]`, not the configured default, because CIRCT
requires the disclosure even when the contribution is not substantial
(`circt:docs/AIToolPolicy.md:11`).

---

## 8. The mutator set, and the offline synthesis

### 8.1 The frozen-set format

`mutators/set_v1.json` is one canonical-JSON document. The version is in the file name and in the
document, so a set can never be confused with another by path alone.

```json
{
  "format_version": 1,
  "set_version": "v1",
  "synthesised_utc": "",
  "synthesis_input": {
    "repo": "llvm/circt",
    "query": "closed issues labelled bug, the full history",
    "issues_used": 0,
    "mirror_refreshed_utc": "",
    "issue_numbers_sha256": ""
  },
  "synthesis_model": "",
  "mutators": [
    {
      "id": "mlir.attr.int.flip_sign",
      "language": "mlir",
      "kind": "text",
      "mutates_argv": false,
      "description": "negate one integer attribute literal",
      "pattern": "(?<![\\w.])(-?)(\\d+)\\s*:\\s*i(\\d+)",
      "replacement": "flip",
      "derived_from": [10588, 10711]
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `format_version` | The **format**'s version, bumped when the fields change. |
| `set_version` | The **set**'s version, part of the file name, referenced by `RunManifest.mutator_set_sha`. |
| `synthesised_utc`, `synthesis_model` | When, and by which model id (FR-05.8's declaration). |
| `synthesis_input` | The exact input: the repo, the query, how many issues were used, when the mirror those issues came from was refreshed, and a SHA-256 over the sorted issue numbers so the input set is identifiable without shipping it. |
| `mutators[].id` | Stable, dotted, `<language>.<target>.<operation>`. It is recorded in every `ProbeSpec` and is the key a failure is attributed to (FR-05.7). |
| `mutators[].language` | `mlir`, `fir`, `sv` or `any`. A mutator runs only against inputs of its language. |
| `mutators[].kind` | `text` for a regular-expression rewrite, `line` for a line-level operation (duplicate, delete, swap), `argv` for an argument-vector mutation. |
| `mutators[].mutates_argv` | True only for `kind: argv`; FR-05.5 requires an argument mutator to be declared as such. |
| `mutators[].pattern`, `replacement` | The rewrite. `replacement` is either a literal, a back-reference template, or one of the named operations `flip`, `zero`, `max`, `off_by_one`, `duplicate`, `delete`, `swap`. |
| `mutators[].derived_from` | The issue numbers the synthesis drew this mutator from, for the release (FR-05.2). |

Every value in the document above is a **shape**, not a datum: the one mutator shown, the two issue
numbers it cites and the empty provenance strings are there to fix the field names and their types.
The real file is written by `mutator_synth.py` from the run, and the three provenance fields are
filled from the run rather than from the model.

**The frozen-set rule (FR-05.2), enforced in three places.**

1. `mutators/__init__.py` computes `hashlib.sha256` over the file's bytes at import and compares it to
   `RunManifest.mutator_set_sha`; a mismatch raises before any mutant is produced.
2. `budget.py` refuses to start a campaign whose `mutator_set_sha` names a file whose **last commit**
   does not predate the pre-registration commit, which is the check FR-05.2's acceptance asks for:
   `git -C <repo> log -1 --format=%H -- mutators/set_v1.json` and
   `git -C <repo> log -1 --format=%cI` on both that commit and the budget file's.
3. `mutator_synth.py` refuses to run at all once a pre-registration commit exists, so the campaign
   cannot synthesise new mutators even by accident (`02-HLD.md` §6, A7's second row).

### 8.2 The application algorithm

```python
def mutate_seed(seed: SeedRecord, iteration: int, cap: int,
                mutator_set: dict) -> list[tuple[str, str, str, int]]:
    """Produce up to *cap* mutants for one seed, deterministically.

    Returns:
        a list of (mutator_id, source_test_path, mutant_text, seed_int), in a
        fixed order, with no-ops already dropped.
    Worker:
        pure; no worker resource and no model (FR-05.1, FR-05.3). It reads
        seed.test_files and never the filesystem.
    Raises:
        nothing. A mutator that raises is caught, counted against its id, and
        skipped (FR-05.7).
    """
```

and the one function it calls, which W4 found named and unsigned:

```python
def apply(mutator_id: str, text: str, seed_int: int) -> tuple[str, list[str] | None]:
    """Apply one frozen mutator to one input text, deterministically.

    Returns:
        (mutant_text, argv) where argv is None unless the mutator declares
        mutates_argv, in which case it is the replacement argument vector
        (FR-05.5). mutant_text equal to *text* is a no-op and the caller counts
        it (FR-05.6).
    Worker:
        pure; random.Random(seed_int) is the only source of choice and the
        module-level generator is never seeded (FR-05.3).
    Raises:
        MutatorError(mutator_id, cause) for an unknown id, a pattern that will
        not compile, or a replacement operation the mutator's kind does not
        allow. mutate_seed catches it, counts it against the id and continues.
    """
```

Six rules, in this order, and nothing else.

1. **Which files.** **Every** changed test file of the seed, in the order FR-01.12 records them, and
   never only the first, read from **`seed.test_files`**, which contract 2.0 added for exactly this
   (K6): the value is the file's full text at the seed commit, so the arm needs no git and no clone,
   and FR-05.1's "the arm's input record contains only the test files and their `RUN:` lines" has an
   object to point at. A seed with k test files supplies k starting inputs, and each mutant names the
   file it came from (FR-05.1). Measured over the corpus: 162 seeds changed one test file, 18
   two, 5 three, 1 six and 1 nine, so the plural is not hypothetical.
2. **Which mutators.** Those whose `language` matches the file's extension, or `any`. The eligible
   list is sorted by `id`, so it does not depend on the file's order in the JSON document.
3. **How many mutations per input.** Exactly **one** mutator application per mutant. A mutant is one
   file, one mutator, one seed integer, which is what makes FR-05.3's byte-for-byte reproduction a
   one-line check and what makes a firing attributable to a single mutator. Composition is available
   for free by feeding a mutant back as a starting input, and the design does not do it: a crash from
   a stack of three mutators names none of them.
4. **How many mutants.** `cap` is `budget.yaml`'s `per_seed_probe_cap`, the same cap the seeded arm
   gets (FR-04.5), taken round-robin across the k starting files and then across the sorted mutator
   list, so a seed with nine test files does not spend its whole cap on the first one.
5. **The RNG seeding.** One `random.Random` per mutant, seeded as below.

```python
seed_int = int.from_bytes(
    hashlib.sha256(f"{seed.seed_sha}|{test_path}|{mutator_id}|{iteration}|{k}"
                   .encode("utf-8")).digest()[:8], "big")
```

   Here `k` is the mutant's index within this seed and iteration. The integer is recorded in the
   `ProbeSpec` as `mutator_seed_int`, and `mutators.apply(mutator_id, text, seed_int)` reconstructs
   `random.Random(seed_int)` from it, so re-running the mutator with the recorded integer reproduces
   the input byte for byte (FR-05.3). The seed integer is derived rather than drawn, so the whole arm
   is reproducible from the `SeedRecord` and the frozen set with no state carried between calls, and
   `random.seed()` is never called on the module-level generator.
6. **No-ops and failures.** A mutant byte-identical to its input is a no-op: it is counted, it
   produces no `ProbeSpec`, and it consumes no input-cap budget (FR-05.6). A mutator that raises is
   counted against its `id` and skipped, and the arm continues (FR-05.7).

**The argv.** A mutant keeps the seed's tool and argument vector unless its mutator declares
`mutates_argv`, in which case the mutator returns a new argv alongside the text and the `ProbeSpec`
names the argument mutator (FR-05.5). `tests/test_mutators.py` asserts that every `ProbeSpec` either
matches its seed's argv or names a mutator whose `mutates_argv` is true.

### 8.3 `prompts/mutator_synth.md`, offline, once

Substitution variables: `$issue_count`, `$issue_digest`, `$issues`, `$languages`, `$target_count`.

```markdown
You are writing a set of MUTATORS for a SystemVerilog, FIRRTL and MLIR fuzzing
baseline against the CIRCT compiler. A mutator is a small, deterministic,
mechanical edit to a test input. It has no understanding of the program it edits
and it is never allowed to acquire any.

Below are $issue_count closed CIRCT issues labelled bug, the full history of
them as of the mirror this synthesis ran against. Read them for ONE thing only:
what kinds of small, mechanical input differences have historically broken this
compiler.

~~~
$issues
~~~

Write about $target_count mutators covering these languages: $languages.

What a good mutator looks like.
  - It is a rewrite, not a generator: it edits an existing valid test into a
    slightly different one.
  - It is deterministic given the input text and an integer seed, and it uses the
    seed only to CHOOSE among candidate sites, never to invent content.
  - It is cheap: a regular expression or a line operation, not a parser.
  - It is plausible: the output should usually still parse. A mutator whose
    output is always rejected by the parser measures nothing.
  - It targets something the issues below show actually breaks CIRCT: widths,
    zero-width values, attribute bounds, symbol references, region and block
    structure, operand counts, self-reference, deep nesting, unusual but legal
    literals.

What a mutator is NOT.
  - It is not a fix, a diagnosis, or a hypothesis about a specific bug.
  - It does not read a commit, a diff, or a root-cause description. The arm that
    uses this set is the BASELINE and at run time it sees only test files.
  - It does not call a model. Once frozen, this set runs with no model at all.

For each mutator give: a dotted id of the form language.target.operation; the
language it applies to; the kind, one of text, line or argv; a one-clause
description; the pattern; the replacement, which is a literal, a back-reference
template, or one of the named operations flip, zero, max, off_by_one, duplicate,
delete, swap; and the issue numbers that suggested it.

Prefer twenty sharp mutators to sixty vague ones. A mutator that fires on every
input and changes nothing meaningful costs the baseline its whole budget.

End your response with EXACTLY one fenced json block, and nothing after it, whose
shape is the mutators array of the frozen set:

```json
{
  "mutators": [
    {"id": "mlir.attr.int.off_by_one", "language": "mlir", "kind": "text",
     "mutates_argv": false, "description": "shift one integer attribute by one",
     "pattern": "(?<![\\w.])(\\d+)\\s*:\\s*i(\\d+)", "replacement": "off_by_one",
     "derived_from": [10588]}
  ]
}
```
```

**A7's callable, `mutator_synth.synthesise_mutators`.** It was named in §3.2 and §14.1 with only its
prompt specified here and no signature, returns or raises, so §1.8 of `04-Test-Plan.md` could test the
**frozen set's format** and the **three enforcement points** of §8.1, which are specified, and not the
callable. It is specified here.

```python
@ChiaFunction(max_retries=0)
def synthesise_mutators(db_path: str, repo_root: str, set_version: str,
                        languages: tuple[str, ...], target_count: int,
                        cfg: dict, timeout_seconds: int = 3600) -> dict:
    """Synthesise the frozen mutator set once, offline, before registration.

    Runs OFFLINE and ONCE, is not imported by the campaign, and refuses to run
    at all once a pre-registration commit exists (8.1 point 3). Five steps.

      1. REFUSE IF REGISTERED. `git -C <repo_root> log -1 --format=%H -- budget.yaml`;
         a commit means the campaign is pre-registered (FR-14.3) and this
         function raises. The refusal is first so that no model turn is spent
         discovering it.
      2. READ THE INPUT. SELECT number, title, body FROM issue_mirror WHERE
         state = 'closed' AND the labels_json array contains 'bug', ORDER BY
         number, against the mirror B6a built in loop.db. That is the input set
         and the only one: no GitHub request is made here, for the same reason
         3.7.3's screen makes none. The count is 487, MEASURED on 2026-09-13
         (M9), against 101 open, so FR-05.2's "the full history of closed
         label:bug issues" is a real corpus and ADR-D-05's fallback to the
         24-month fix-commit set is NOT taken. A-21 is counted, not open.
      3. ONE TURN. 8.3's prompt, rendered by Template.safe_substitute with
         issue_count = 487, issues = the rows of step 2 rendered one per
         `== #<number> <title>` block, issue_digest = the sha below,
         languages and target_count as passed, at {"llm": 1.0}, exactly as
         3.5's turns are dispatched. No tool is given to this turn at all.
      4. PARSE AND DROP. 7.1's parse_json_footer with required = ("mutators",),
         then per entry: re.compile(pattern) must not raise; id must match
         ^[a-z0-9]+(\\.[a-z0-9_]+){2,}$ and be unique in the set; language must
         be one of mlir, fir, sv, any; kind must be one of text, line, argv;
         mutates_argv must be True exactly when kind == "argv" (FR-05.5);
         replacement must be a literal, a back-reference template, or one of
         the seven named operations of 8.1. An entry failing any check is
         DROPPED with its id and the failing check recorded in "dropped", never
         repaired and never silently kept.
      5. FREEZE. Writes mutators/set_v1.json as canonical JSON by 2.3's rule,
         with format_version, set_version, and the three PROVENANCE fields
         filled FROM THE RUN and never from the model: synthesised_utc from the
         clock, synthesis_model from cfg["model"], and synthesis_input from
         step 2, whose issues_used is the row count, mirror_refreshed_utc is
         issue_mirror_meta.refreshed_utc, and issue_numbers_sha256 is
         hashlib.sha256 over the sorted issue numbers joined by newlines. The
         model is asked for the mutators array and for nothing else, which is
         why the shape of 8.3's json block is that array alone.

    The freeze is WRITE-ONCE: the function refuses to overwrite an existing
    mutators/set_<set_version>.json, so a re-run bumps set_version or fails, and
    the digest RunManifest.mutator_set_sha names can never change under a run.

    Returns:
        {"path": str, "set_sha256": str, "mutators_written": int,
         "dropped": dict, "issues_used": int, "counters": CounterBlock},
        where dropped maps a failing check's name to the list of ids it dropped.
    Worker:
        head - the mirror is a table in loop.db, which is head-pinned (6.1), and
        the turn is dispatched from here at {"llm": 1.0}.
    Raises:
        MutatorSynthError("already_registered", sha) when step 1 finds a
            budget.yaml commit; the message names it, and the fix is to
            synthesise before registering, never to edit the registration;
        MutatorSynthError("empty_mirror") when step 2 returns no row, because a
            set synthesised from nothing would freeze successfully and measure
            nothing;
        MutatorSynthError("set_exists", path) when step 5 finds the file;
        PromptContractError(reason) from 7.1's parser, which freezes nothing
            (8.1's rule: a malformed footer is not a partial set).
    """
```

**The output set format is §8.1's and is not restated here**: `format_version`, `set_version`, the
three provenance fields, `synthesis_input`'s five keys, and one `mutators` entry per surviving
mutator with the eight fields §8.1 tables. Step 5 writes exactly that document and nothing else, and
`tests/test_mutator_synth.py` compares the written file against §8.1 field by field and type by type.

**The timeout is 3,600 s `[DEFAULT]`**, §3.2's row, enforced on the turn; it is one model turn over a
large prompt and the bound is generous because the function runs once, offline, before the campaign,
so its cost is not the campaign's.

**Idempotency: none, deliberately.** §3.2's row says "run once, frozen, referenced by SHA", and step 5
makes that mechanical rather than conventional: the file is write-once, so a second call with the same
`set_version` raises rather than producing a second set that differs from the one the manifest names.
What is reproducible is the **reference**, not the synthesis: `RunManifest.mutator_set_sha` is the
digest of the file, `mutators/__init__.py` re-checks it at import, and a model turn is not a
deterministic function of its prompt.

`mutator_synth.py` parses the model's block with §7.1's parser, and the input issues come from the
mirror B6a builds, which is why the mirror is built before the pre-registration commit and not only
before the first candidate (ADR-D-05's HLD consequence). What remains open is not the **count** but
the **sufficiency**: whether 487 reports synthesise a strong set is A-21's second half, F-05's own
implementation task answers it, and no number in this document depends on the answer.
---

## 9. `budget.yaml`

### 9.1 The schema

Every key FR-14.1 names, and no key it does not. `budget.py` rejects a file missing any of these and
rejects a file carrying any other top-level key, which together are what make the pre-registration of
FR-14.2 mean something: a free parameter fixed after the data exists defeats it.

| Key | Type | Unit | Default marker | Requirement |
|---|---|---|---|---|
| `arm_window_seconds` | float | wall-clock seconds | `[DEFAULT]` | G-48, FR-14.1, FR-14.5 |
| `arm_order` | list of 2 strings | - | `[DEFAULT]` | G-48, FR-14.1, FR-18.10 |
| `model_id` | string | - | `[DEFAULT]`, `gemini-3.8-flash` | ADR-D-03 superseding, FR-14.1 |
| `campaign_spend_cap_usd` | float | US dollars, whole campaign | `[DEFAULT]`, 200 | ADR-D-03 superseding, FR-14.1, FR-18.10, NFR-08 |
| `price_usd_per_m_input_tokens` | float | USD per million prompt tokens | `[DEFAULT]`, 0.75, `[UNVERIFIED]` | FR-14.1, FR-14.6 |
| `price_usd_per_m_output_tokens` | float | USD per million output tokens | `[DEFAULT]`, 3.75, `[UNVERIFIED]` | FR-14.1, FR-14.6 |
| `generated_inputs_per_day` | int | probing inputs per UTC day, per arm | `[DEFAULT]` | FR-14.1, FR-14.5 |
| `filings_per_day` | int | filings per UTC day | `[DEFAULT]` | FR-13.8, FR-14.1 |
| `filings_total` | int | filings per campaign | `[DEFAULT]` | FR-14.1 |
| `campaign_start_utc` | string, ISO 8601 with offset | - | `[DEFAULT]` | FR-14.1 |
| `campaign_end_utc` | string, ISO 8601 with offset | - | `[DEFAULT]` | FR-14.1 |
| `corpus_head_sha` | string, 40 hex | - | measured | FR-01.11, FR-14.1 |
| `fingerprint_top_n` | int | frames | `[DEFAULT]` | G-43, FR-10.1, FR-14.1 |
| `calibration_sample_size` | int | seeds | `[DEFAULT]`, fixed at 20 by ADR-D-01 | D-01(d), FR-14.1 |
| `calibration_sample_shas` | list of strings | - | drawn once, before the campaign | ADR-D-01 |
| `per_seed_probe_cap` | int | probing inputs per seed per iteration | `[DEFAULT]` | FR-04.5, FR-14.1 |
| `per_seed_iteration_cap` | int | iterations per seed | `[DEFAULT]` | FR-16.3, FR-14.1 |
| `probe_wall_seconds` | int | seconds | `[DEFAULT]` | FR-06.2, FR-14.1 |
| `probe_address_space_bytes` | int | bytes | `[DEFAULT]` | FR-06.2, FR-14.1 |
| `probe_cpu_seconds` | int | seconds | `[DEFAULT]` | FR-06.2, FR-14.1 |
| `probe_output_byte_cap` | int | bytes, per stream | `[DEFAULT]` | FR-06.4, FR-14.1 |
| `reduction_wall_seconds` | int | seconds | `[DEFAULT]`, 600 in the pilot | FR-09.4, FR-14.1 |
| `reduction_sigkill_grace_seconds` | int | seconds | `[DEFAULT]` | FR-09.13, FR-14.1 |
| `issue_mirror_issue_cap` | int | issues | `[DEFAULT]` | FR-10.9, FR-14.1 |
| `filing_poll_window_seconds` | int | seconds | `[DEFAULT]` | FR-13.16, FR-14.1 |
| `artefact_inline_cap_bytes` | int | bytes | `[DEFAULT]`, 262,144 in the pilot | FR-17.7, FR-14.1 |
| `acceptance` | mapping, §9.3 | - | `[DEFAULT]` | the five feature-acceptance criteria that place their sizes here |

**The four keys of 2026-09-14, and why each is a campaign parameter rather than a constant.**
`model_id` is one value for every agent stage, because the superseding decision fixes one model for
the campaign and a per-stage model would be a free parameter in the head-to-head.
`campaign_spend_cap_usd` is the hard money cap the driver stops **both** arms on, `[DEFAULT]` 200
against the user's USD 300 credit, and it is a cap and not the budget: the primary unit is still the
arm window (G-48, ADR-D-04), and §2.7 says so at the field. The two prices exist because the backend
reports tokens and no price (`chia:chia/models/vertex.py:479-482`), so the ledger has to do the
arithmetic, and a price that could be edited after the data exists would put a free parameter in a
reported number. They are the introductory Vertex prices for `gemini-3.8-flash` through 2026-12-31,
**aggregator-sourced on 2026-09-14 and `[UNVERIFIED]` against Google's own pricing page**; ADR-D-03's
superseding section requires that page to be re-read and the figures re-written before the
pre-registration commit, and `05-Work-Plan.md` schedules it. A wrong price moves no measured
quantity: it moves only `cost_usd` and the point at which the USD cap binds, and both are printed
beside the headline with the price they were computed from.

### 9.2 The checks `budget.py` makes before a run starts

1. **Committed, and earlier.** `git -C <repo> log -1 --format=%H%x09%cI -- budget.yaml` must return a
   commit, and that commit's date must precede the run's start. A run against an uncommitted or
   later-committed file exits non-zero naming the offending commit (FR-14.2). The returned SHA is
   `BudgetFile.budget_file_sha` and is the pre-registration (FR-14.3, G-32).
2. **Complete and closed.** Every key of §9.1 present; no other top-level key; every type as declared.
3. **Equal on the unit and on both safety caps.** `arm_window_seconds` is one value and applies to
   both arms by construction, and `arm_order` names each arm exactly once, so FR-14.5's equality is
   structural rather than checked: there is no per-arm value to be unequal. The safety caps are
   likewise single values applying to both arms. That is deliberate: a per-arm shape would have made
   inequality expressible, and a schema that cannot express a violation cannot have one.
4. **Unchanged mid-campaign.** Every stage compares `BudgetFile.budget_file_sha` against
   `RunManifest.budget_file_sha` and refuses to continue on a difference, which invalidates the
   campaign rather than quietly re-basing it (FR-14.7).
5. **The calibration sample is drawn, and is the declared size.**
   `len(calibration_sample_shas) == calibration_sample_size`, and every entry is one of the 171
   exact-pin seeds. The check exists because the sample is part of the pre-registration and the
   earlier §9.5 shipped it empty (W12): the commit that lands `budget.yaml` **is** the registration
   (FR-14.3) and FR-14.7 invalidates the campaign on any later edit, so a sample drawn after that
   commit invalidates the campaign and a sample drawn before it must be in the file. The draw is
   therefore a step of the pre-registration, not of the run: `python -m bug_loop --draw-calibration`
   prints 20 SHAs sampled with `random.Random(<the corpus head SHA>)` from the exact-pin set, which is
   reproducible from a value already in the file, the operator pastes them in, and **then** the file
   is committed. §9.5's example carries a drawn sample for that reason and the twenty SHAs in it are
   an illustration, not the campaign's; the campaign's are drawn once, by that command, before its own
   registration commit.

6. **Both prices are present, positive and finite, and the spend cap is positive.** Added
   2026-09-14. Check 2 already requires every key, so this check is about the **pair**: a file
   carrying one price and not the other would value half the campaign's tokens at zero and the
   ledger would under-report the spend it is meant to stop on, so `budget.py` refuses a file in
   which either price is absent, non-positive, or not a finite float, naming which. It refuses a
   non-positive `campaign_spend_cap_usd` for the same reason, and it refuses a `model_id` that is
   empty. The heading above says five because five is what the LLD review left; the count is
   **six** from 2026-09-14 and `tests/test_budget.py` asserts six.

### 9.3 The acceptance block, and why it exists

FR-14.1 places fixture sizes in `04-Test-Plan.md` and campaign parameters in `budget.yaml`. Five
feature-acceptance criteria sit across that line: they name a sample size **and** say it is recorded
in `budget.yaml` (F-04's "both sample sizes are recorded in `budget.yaml`", F-06's batch size, F-07's
sample size, FR-10.2's labelled pairs, F-16's iteration count). Both homes are honoured, without
duplicating a value: `budget.yaml` carries the **numbers**, under an `acceptance` mapping, because
those FRs put them there; `04-Test-Plan.md` owns the fixtures themselves, the inputs and the expected
outputs, because FR-14.1 puts those there. Nothing is stated twice.

| `acceptance` key | Value | Requirement |
|---|---|---|
| `seed_sample` | 5 `[DEFAULT]` | F-04's feature acceptance |
| `entry_tools` | 3 `[DEFAULT]` | F-04's feature acceptance |
| `probe_batch` | 20 `[DEFAULT]` | F-06's feature acceptance |
| `recorded_failures` | 5 `[DEFAULT]` | F-07's feature acceptance, `04-Test-Plan.md` item 5 |
| `recorded_crashes_for_reduction` | 3 `[DEFAULT]` | F-09's feature acceptance |
| `labelled_pairs` | 20 `[DEFAULT]` | FR-10.2, F-10's feature acceptance |
| `iterations` | 3 `[DEFAULT]` | F-16's feature acceptance |

### 9.4 The implementation constants, which are not in `budget.yaml`

Fixed here, as FR-14.1 directs for the `[DEFAULT]`s that are not campaign parameters. Each is a
module-level constant in the module named.

| Constant | Value | Module | Requirement |
|---|---|---|---|
| `PREFILL_URL_CHAR_LIMIT` | 6,000 `[DEFAULT]` | `approve.py` | FR-13.17, fixed by ADR-D-02 |
| `LOCAL_ID_BASE`, `LOCAL_ID_MAX` | 900,000,000 and 999,999,999 `[DEFAULT]` | `repair_adapter.py` | FR-12.2 |
| `TRIAGE_REASON_MAX_SENTENCES` | 4 `[DEFAULT]` | `triage_task.py` | FR-11.1 |
| `PROBE_NOFILE` | 1,024 `[DEFAULT]` | `probe_task.py` | §4.1; not one of FR-06.2's three limits, so not a campaign parameter. It is `@NOFILE@` in §10.2. |
| `CPU_HARD_MARGIN_SECONDS` | 5 `[DEFAULT]` | `probe_task.py` | §3.10, §4.1: the gap between `prlimit --cpu`'s soft and hard values, which is what makes the kernel deliver `SIGXCPU` before `SIGKILL`. Not a campaign parameter: it changes no measured outcome, only whether the limit is identifiable. |
| `MIRROR_TOKEN_MIN_CHARS` | 8 `[DEFAULT]` | `triage_task.py` | §3.7.3: a token shorter than this is dropped from the issue-mirror screen |
| `BUILD_JOBS` | 16 `[DEFAULT]` | `repair_adapter.py` | CHIA's own value for `cfg["build_jobs"]` (`chia:examples/circt_issue_solver/circt_issue_loop.py:98`), bounded by `bugloop_repair`'s `--cpus=8` |
| `NODE_TIMEOUTS` | `02-HLD.md` §3's table | `bug_loop.py` | `02-HLD.md` §3 |
| `PHASE_TIMEOUTS` | `{"assess": 1800, "repro": 1800, "fix": 7200, "regression": 3600, "writeup": 1200}` | `repair_adapter.py` | CHIA's own, reused verbatim (`chia:examples/circt_issue_solver/circt_issue_loop.py:77`) |
| `PROBE_WALL_MARGIN_SECONDS` | 60 `[DEFAULT]` | `probe_task.py` | the node-level margin over the per-probe wall limit (`02-HLD.md` §3, B2) |
| `X_POLICY` | `x-assign=unique,x-initial=unique` `[DEFAULT]` | `probe_task.py` | FR-08.4, §4.10 |
| `ARC_JIT_ENTRY` | `bugloop_main` | `probe_task.py` | §4.6 |
| `STIMULUS_ID` | `lfsr32-v1` `[DEFAULT]` | `probe_task.py` | §3.6.3, FR-08.3: one shared stimulus definition for the whole campaign. A second definition is a second id and a new constant, never a parameter. |
| `RESET_PROTOCOL` | `hold-8-then-release` `[DEFAULT]` | `probe_task.py` | §3.6.3, FR-08.3 |
| `SAMPLE_POINT` | `pre-posedge` `[DEFAULT]` | `probe_task.py` | §3.6.3, FR-08.3 |
| `DIFFERENTIAL_CYCLES` | 64 `[DEFAULT]` | `probe_task.py` | §3.6.3: rising edges both harnesses run, the 8 reset cycles included. Not a campaign parameter: it sizes a comparison, not a budget, and it is equal for both arms by construction because the apparatus cannot tell them apart. |
| `PORT_LIST_TIMEOUT_SECONDS` | 60 `[DEFAULT]` | `probe_task.py` | §3.6.3: the wall bound on the one `circt-opt` `extract_port_list` runs |
| `_CLOCK_NAMES`, `_RESET_NAMES` | `("clk", "clock", "clk_i", "i_clk")` and `("rst", "reset", "rst_n", "resetn", "areset", "rst_i", "i_rst")` `[DEFAULT]` | `probe_task.py` | §3.6.3: the name fallback where a port's type is not `!seq.clock`. A design whose clock is named otherwise is `harness_failure("no_clock")`, which is a recorded refusal rather than a silent mis-drive. |

### 9.5 A complete `budget.yaml`

Every value below is a `[DEFAULT]` chosen by design except `corpus_head_sha`, which is measured, and
`calibration_sample_size`, which ADR-D-01 fixes at 20. This is a complete, valid file: `budget.py`
accepts it and no key is missing.

```yaml
# budget.yaml - the pre-registration of the CIRCT bug-loop campaign.
#
# THE COMMIT THAT LANDS THIS FILE IS THE REGISTRATION (G-32, FR-14.3). Editing it
# mid-campaign invalidates the campaign (FR-14.7): every stage compares this
# file's commit SHA against the one in the RunManifest and refuses on a
# difference. Every [DEFAULT] in 01-FRD.md resolves to exactly one key here.

# --- the primary budget unit (G-48) -----------------------------------------
# One elapsed wall-clock second of an arm's fixed window W, metered by the
# campaign driver on the head. The arms run SEQUENTIALLY, each for this same W,
# in the order below, on the same fixed-size cluster at the same apparatus
# concurrency. Nothing else is the budget.
arm_window_seconds: 14400.0            # 4 hours per arm, 8 hours for the campaign
arm_order: [seeded, mutation]

# --- the model, and the money cap (ADR-D-03, superseding section 2026-09-14) --
# ONE model id for every agent stage: stages 1, 2 and 6 and the offline mutator
# synthesis. CHIA's vertex backend in Vertex AI express mode. There is no
# per-stage model selector and no --model default in the code.
model_id: gemini-3.8-flash

# The HARD money cap for the whole campaign, both arms together. It is a CAP and
# not the budget: the primary unit is still the arm window above (G-48). The
# driver stops BOTH arms when the cumulative cost_usd of the ledger reaches it
# (FR-18.10's third stop condition), and the results artefact states the spend.
# 200 against the user's USD 300 credit, leaving headroom for the pilot and for
# a re-run.
campaign_spend_cap_usd: 200.0

# The two prices the ledger turns tokens into money with. The backend reports
# usage_metadata token counts and no price, so the arithmetic is the ledger's:
#   cost_usd = tokens_in/1e6 * input_price + tokens_out/1e6 * output_price
# Introductory Vertex pricing for gemini-3.8-flash through 2026-12-31,
# AGGREGATOR-SOURCED 2026-09-14 and [UNVERIFIED] against Google's own pricing
# page, which ADR-D-03 requires to be re-read and these two figures rewritten
# BEFORE the commit that lands this file. budget.py check 6 requires both.
price_usd_per_m_input_tokens: 0.75
price_usd_per_m_output_tokens: 3.75

# --- safety caps, equal for both arms, which bound damage and are not the budget
generated_inputs_per_day: 2000
filings_per_day: 3
filings_total: 10

# --- the campaign's own window ----------------------------------------------
campaign_start_utc: "2026-09-20T00:00:00+00:00"
campaign_end_utc:   "2026-09-24T11:59:00+00:00"

# --- the corpus (FR-01.11) --------------------------------------------------
# Measured, not chosen: this is the HEAD at which analysis/pin_window_raw.json was
# computed, and the SHA at which FR-01.1's counts of 187 and 171 hold.
corpus_head_sha: "d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2"

# --- the fingerprint (G-43) -------------------------------------------------
# The headline metric counts DISTINCT bugs, one per primary fingerprint, and a
# crash fingerprint is this many frame names long. Fixing it here is what stops
# the headline carrying a parameter chosen after the data exists.
fingerprint_top_n: 5

# --- calibration (ADR-D-01, D-01(d)) ----------------------------------------
# DRAWN BEFORE THIS FILE IS COMMITTED, by `bug_loop.py --draw-calibration`, which
# samples 20 of the 171 exact-pin seeds with random.Random(corpus_head_sha). The
# commit that lands this file is the registration, so a sample drawn afterwards
# would invalidate the campaign (FR-14.3, FR-14.7). budget.py check 5 asserts
# len(calibration_sample_shas) == calibration_sample_size.
# The twenty below are an ILLUSTRATION of the shape and not the campaign's draw.
calibration_sample_size: 20
calibration_sample_shas:
  - "0000000000000000000000000000000000000001"
  - "0000000000000000000000000000000000000002"
  - "0000000000000000000000000000000000000003"
  - "0000000000000000000000000000000000000004"
  - "0000000000000000000000000000000000000005"
  - "0000000000000000000000000000000000000006"
  - "0000000000000000000000000000000000000007"
  - "0000000000000000000000000000000000000008"
  - "0000000000000000000000000000000000000009"
  - "0000000000000000000000000000000000000010"
  - "0000000000000000000000000000000000000011"
  - "0000000000000000000000000000000000000012"
  - "0000000000000000000000000000000000000013"
  - "0000000000000000000000000000000000000014"
  - "0000000000000000000000000000000000000015"
  - "0000000000000000000000000000000000000016"
  - "0000000000000000000000000000000000000017"
  - "0000000000000000000000000000000000000018"
  - "0000000000000000000000000000000000000019"
  - "0000000000000000000000000000000000000020"

# --- per-seed caps ----------------------------------------------------------
per_seed_probe_cap: 5                  # FR-04.5, and the mutation arm's cap too
per_seed_iteration_cap: 3              # FR-16.3

# --- per-probe limits (FR-06.2, FR-06.4) ------------------------------------
# Applied to the child by prlimit --as --cpu --nofile, never by the container's
# limits: container limits protect the machine, rlimits classify the probe.
probe_wall_seconds: 60
probe_address_space_bytes: 4294967296  # 4 GiB
probe_cpu_seconds: 45
probe_output_byte_cap: 1000000         # per stream

# --- reduction (FR-09.4, FR-09.13) ------------------------------------------
# 600, not 60. circt-reduce made 56 interestingness calls to remove 27% of a
# SIX-OPERATION module (measured by the LLD review), and each call is bounded by
# probe_wall_seconds, which is 60. At 60 s the reducer got one or two calls on
# any realistic input, every ReducedCase came back fixpoint=false, and FR-13.3
# refused every candidate at gate question 2 as not_minimal. The per-CALL wall is
# probe_wall_seconds and lives in the interestingness script; this key is the
# wall for the WHOLE reduction and they are not the same number.
reduction_wall_seconds: 600
reduction_sigkill_grace_seconds: 10

# --- the issue mirror (FR-10.9) ---------------------------------------------
# An ISSUE cap, not a page cap: GithubIssuesNode.recent takes n and pages
# internally. Comments are never mirrored.
issue_mirror_issue_cap: 20000

# --- filing (FR-13.16) ------------------------------------------------------
filing_poll_window_seconds: 3600

# --- artefacts (FR-17.7) ----------------------------------------------------
# 256 KiB. Larger artefacts go to disk by path. It also caps a SourceReadTool
# return (3.5) and a SeedRecord's diff and test_files (2.4). It was 10 MB, which
# contradicted SQLiteNode's own guidance that this design quotes.
artefact_inline_cap_bytes: 262144

# --- feature-acceptance sample sizes (9.3) ----------------------------------
acceptance:
  seed_sample: 5
  entry_tools: 3
  probe_batch: 20
  recorded_failures: 5
  recorded_crashes_for_reduction: 3
  labelled_pairs: 20
  iterations: 3
```

---

## 10. The interestingness script, and the textual reducer

### 10.1 What the script has to do, and why it has to do it itself

`circt-reduce` imposes neither a time limit nor a memory limit on the script it runs: it calls
`llvm::sys::ExecuteAndWait(..., /*SecondsToWait=*/0, /*MemoryLimit=*/0, ...)`
(`circt:lib/Reduce/Tester.cpp:50-52`), and F-06's per-probe limits do not reach it because the
reducer, not F-06, is the caller (C-18). The script therefore bounds the tool itself (FR-09.13).

The polarity is one and only one: **exit 0 when the recorded failure still reproduces**, non-zero
otherwise, so `--test-must-fail` is never passed (FR-09.2, and `circt:lib/Reduce/Tester.cpp:57-61`,
where `testMustFail` selects `result > 0` over `result == 0`). And the test is specific to the
**recorded firing**, not to a non-zero exit: it requires the same oracle class, and for an assertion
the same normalised expression and the same `file:line` (FR-09.1). A reduction whose intermediate
input crashes differently is rejected, which is the whole point of the stage.

### 10.2 The template, and the one class block each instance carries

Written per probe to `<probe dir>/interesting.sh`, mode 0755 (§6.5; candidates and probes are 1:1, so
"per candidate" named the same directory and "per probe" is the noun this document now uses
throughout, NIT 16). `$1` is the candidate file, which `circt-reduce` appends as the last argument
after the script name and after every `--test-arg` (`circt:lib/Reduce/Tester.cpp:42-46`); no
`--test-arg` is passed, so `$1` is all there is.

**The template carries `@CLASS_BLOCK@` and the loop substitutes exactly one of the three class blocks
into it.** The earlier version was titled "verbatim" and contained all three in sequence, with the
assertion block ending `exit 0`, so the other two were dead code and a typist following "verbatim"
would have shipped a script correct only for the assertion class. `sh -n` passes on it, so nothing
caught it (K15). The three blocks are given below the template, and `tests/test_probe_task.py` asserts
that a written script contains exactly one `# --- class:` line.

**Eleven placeholders, all eleven bound.** The earlier text said three and the block contained eleven,
five of them bound to nothing anywhere in the document:

| Placeholder | Bound to | Home |
|---|---|---|
| `@TOOL@` | the probe's absolute binary path, `/workspace/circt/build/bin/<tool>` | §5.1 |
| `@ARGS@` | the probe's argv with the input path removed, each token `shlex.quote`d | §4.1 |
| `@WALL@` | `budget.yaml`'s `probe_wall_seconds` | §9.1 |
| `@GRACE@` | `budget.yaml`'s `reduction_sigkill_grace_seconds` | §9.1, FR-09.13 |
| `@AS_BYTES@` | `budget.yaml`'s `probe_address_space_bytes` | §9.1 |
| `@CPU_SECONDS@` | `probe_cpu_seconds` and `probe_cpu_seconds + CPU_HARD_MARGIN_SECONDS`, written as `<soft>:<hard>` | §9.1, §9.4, §3.10 |
| `@NOFILE@` | `PROBE_NOFILE`, the §9.4 constant | §9.4 |
| `@ASSERT_EXPR@` | `OracleVerdict.assertion_text`, `shlex.quote`d; assertion block only | §2.9 |
| `@ASSERT_SITE@` | `OracleVerdict.assertion_site`, `shlex.quote`d; assertion block only | §2.9 |
| `@FATAL_MESSAGE@` | `OracleVerdict.fatal_message`, `shlex.quote`d; fatal_error block only | §2.9 |
| `@TOP_FRAME@` | the **function-name half** of `OracleVerdict.fingerprint_frame`, `shlex.quote`d; crash block only | §3.7.1 |

`@WALL@` is the **per-call** wall and `reduction_wall_seconds` is the wall for the whole reduction;
they are different numbers and §9.5 now says so (W13). No `budget.yaml` key is added: `@GRACE@` is
FR-09.13's existing `reduction_sigkill_grace_seconds`, which is exactly the SIGTERM-to-SIGKILL grace
the `timeout` line needs, and `@NOFILE@` is an implementation constant that changes no measured
outcome.

`/bin/sh` is used rather than `bash`, because nothing here needs bash and the script is the one place
a shell is unavoidable.

```sh
#!/bin/sh
# Interestingness test for one recorded CIRCT failure.
# Contract: exit 0 IFF the recorded failure still reproduces on "$1".
# circt-reduce is run WITHOUT --test-must-fail, so 0 means interesting.
set -u

# Absolutise the candidate BEFORE cd: circt-reduce passes it relative to ITS cwd.
CANDIDATE=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK" || exit 1

# Bound the tool ourselves: circt-reduce imposes neither a time nor a memory
# limit on us (C-18). SIGTERM first, SIGKILL after the grace period (FR-09.13).
# The subshell with its own stderr is what keeps the shell's own
# "Segmentation fault <the whole command line>" out of circt-reduce's stderr,
# which it would otherwise print on EVERY interesting candidate.
( exec 2>"$WORK/err"
  timeout --signal=TERM --kill-after=@GRACE@ @WALL@ \
    prlimit --as=@AS_BYTES@ --cpu=@CPU_SECONDS@ --nofile=@NOFILE@ -- \
    @TOOL@ @ARGS@ "$CANDIDATE" >"$WORK/out" ) 2>/dev/null
RC=$?

# 124 is timeout's own "the command timed out". A reduction step that hangs is
# not interesting: it is a different failure.
[ "$RC" -ne 124 ] || exit 1

# Memory exhaustion is not the recorded failure either, whatever it looks like.
grep -qF 'std::bad_alloc' "$WORK/err" && exit 1
grep -qF 'out of memory' "$WORK/err" && exit 1

@CLASS_BLOCK@
```

and exactly one of these three is substituted for `@CLASS_BLOCK@`:

```sh
# --- class: assertion -------------------------------------------------------
grep -qF @ASSERT_EXPR@ "$WORK/err" || exit 1
grep -qF @ASSERT_SITE@ "$WORK/err" || exit 1
exit 0
```

```sh
# --- class: fatal_error -----------------------------------------------------
grep -qF @FATAL_MESSAGE@ "$WORK/err" || exit 1
grep -q '^LLVM ERROR:' "$WORK/err" || exit 1
exit 0
```

```sh
# --- class: crash -----------------------------------------------------------
# A crash is a death by signal, which the shell reports as 128+N. Anything below
# 128, and anything that is timeout's own 124, is a different outcome.
[ "$RC" -gt 128 ] || exit 1
grep -qF @TOP_FRAME@ "$WORK/err" || exit 1
exit 0
```

Seven details that are decisions rather than syntax.

1. **`grep -qF`**, fixed strings, never a regular expression. An assertion expression contains
   `&&`, quotation marks, parentheses and sometimes `*`, all of which are regular-expression
   metacharacters; `-F` is what makes the comparison the string comparison G-43 means. The values
   are shell-quoted with `shlex.quote` when the script is written.
2. **`exit 1` for a timeout.** FR-09.1 requires the same oracle class; a hang is not the recorded
   class, and a reducer that accepted hangs would happily reduce a crash into an infinite loop.
3. **`exit 1` for an allocation failure**, for the same reason and with the same two patterns
   `classify_build` uses, so the script and the classifier can never disagree about what `oom` means.
4. **`$RC -gt 128` for a crash.** The shell reports a signal-terminated child as 128 plus the signal
   number, so `> 128` is the shell-level equivalent of the negative return code Python sees.
   `-eq 134` alone would be wrong: SIGSEGV gives 139 and SIGILL 132.
5. **`@TOP_FRAME@` for a crash** is §3.7.1's **fingerprint frame**, not "the first resolved frame",
   and that is the correction K3 forces. The first resolved frame is `llvm::sys::PrintStackTrace` for
   every crash in the campaign, so the old guard matched any crash at all and stopped nothing. The
   fingerprint frame is the first frame in a CIRCT object after the prologue strip, and the `grep` is
   over the **whole** stderr rather than over the top frame alone, which is what makes it survive the
   frame rotation §3.7.1 measures. Verified on 2026-09-14 by instantiating the crash block for one
   recorded `!hw.array` stack overflow and running it three ways:

   ```
   $ ./interesting.sh c3.mlir   # the recorded crash            rc=0
   $ ./interesting.sh c2.mlir   # a clean input                 rc=1
   $ ./interesting.sh c5.mlir   # a DIFFERENT crash (!hw.struct) rc=1
   ```

   and the guard is what produced the third answer: `parseHWArray` appears 41 or 42 times in each of
   twelve traces of the first input and zero times in the third's.
6. **A temporary working directory per invocation, and the script `cd`s into it.** The stated reason
   for the directory was that "the tool may write beside its input", and the old script created the
   directory, redirected the two streams into it, and never entered it, so the tool's cwd stayed
   whatever `circt-reduce` inherited and anything it wrote still landed there (W14). `cd "$WORK"` is
   the one line that implements the stated reason, and `CANDIDATE` is absolutised before it because
   `circt-reduce` passes the candidate path relative to its own cwd.
7. **The subshell with its own stderr.** Observed while running the instantiated template: without it
   the shell prints `./interesting.sh: line 4: 408911 Segmentation fault <the entire command line>` to
   stderr on every interesting candidate, which at thousands of calls fills `circt-reduce`'s own
   stderr. With it, the same run prints nothing. Both were measured on 2026-09-14.

**After the reducer exits**, and never while it is running, the `-o` output is validated: it must be
non-empty, must parse (for MLIR, by `circt-opt <out> -o /dev/null`), and must still satisfy this same
script. A file that fails any of the three is discarded and the previous good output is kept, which
is FR-09.13's truncation case and is live by default because `--keep-best` defaults to `true`
(§4.7).

### 10.3 The textual reducer, `ddmin.py`

For the probe languages `circt-reduce` cannot open at all: it stops at an MLIR parse diagnostic
before reduction begins on a `.fir` or a `.sv` file, and only reaches `Testing input with ...` on
`.mlir` (C-17, executed). Python standard library only, no added dependency (FR-09.10, FR-19.8).

```python
def ddmin(lines: list[str], interesting, max_calls: int | None = None) -> tuple[list[str], int]:
    """Line-level delta debugging: the smallest 1-minimal subsequence that is interesting.

    *interesting* takes a list of lines and returns True when the recorded
    failure still reproduces; it is the same script circt-reduce would have been
    given (FR-09.1, FR-09.10), invoked through the same wrapper.

    Returns:
        (the reduced lines, the number of interestingness calls spent).
    Worker:
        pure; it knows nothing about CIRCT and takes no worker resource.
    Raises:
        ValueError when the input is not interesting to begin with, which is a
        defect in the caller rather than a reduction outcome.
    """
    if not interesting(lines):
        raise ValueError("ddmin: the input is not interesting to begin with")
    calls = 1
    n = 2
    while len(lines) >= 2:
        chunk = max(1, len(lines) // n)
        subsets = [lines[i:i + chunk] for i in range(0, len(lines), chunk)]
        reduced = False
        for i, subset in enumerate(subsets):          # first, try each subset alone
            calls += 1
            if interesting(subset):
                lines, n, reduced = subset, 2, True
                break
        if not reduced:
            for i in range(len(subsets)):             # then, try each complement
                complement = [x for j, s in enumerate(subsets) if j != i for x in s]
                calls += 1
                if complement and interesting(complement):
                    lines, n, reduced = complement, max(n - 1, 2), True
                    break
        if not reduced:
            if n >= len(lines):
                break                                  # 1-minimal: nothing more to remove
            n = min(len(lines), 2 * n)
        if max_calls is not None and calls >= max_calls:
            break
    return lines, calls
```

**The termination argument**, which FR-09.10's "terminates at a fixpoint" needs and which is short
enough to state in full.

Consider the pair `(len(lines), len(lines) - n)`, ordered lexicographically, with both components
non-negative integers. Each pass through the loop does exactly one of three things.

- **A subset or a complement is interesting.** `lines` is replaced by a **strictly shorter** list: a
  subset has at most `ceil(len/n) < len` elements for `n >= 2`, and a complement has at most
  `len - 1`. So the first component strictly decreases.
- **Nothing is interesting and `n < len(lines)`.** `n` strictly increases, `len(lines)` is unchanged,
  so the second component strictly decreases.
- **Nothing is interesting and `n >= len(lines)`.** The loop breaks.

A lexicographic order on pairs of non-negative integers is well-founded, so no infinite descent
exists and the loop terminates. On exit, either the break fired, in which case every single line has
been tried as a complement and none could be removed, which is exactly 1-minimality, or
`len(lines) < 2`, in which case nothing can be removed at all. The `max_calls` guard is a budget, not
a termination condition, and a reduction stopped by it carries `fixpoint=False` and
`budget_truncated=True` so that NFR-02 keeps a non-reproducible row visible.

**Cost.** ddmin is O(n squared) interestingness calls in the worst case and near-linear in the common
one; `interestingness_calls` is recorded on every `ReducedCase`, which is what FR-09.10's acceptance
asks to be reported. The fixture that exercises it is at least 200 lines `[DEFAULT]` with the failure
depending on 3 of them `[DEFAULT]`, and the expected answer is exactly those three lines
(`04-Test-Plan.md` owns the fixture; `budget.yaml` does not, because it parameterises a test rather
than a run).
---

## 11. Credentials

### 11.1 The GitHub token: the exact path it takes

NFR-07 allows the loop exactly **one** GitHub credential, with public read scope only, and NFR-06
forbids it appearing in any persisted artefact or prompt. Both hold by construction, because the
token never leaves the head machine and is never a value anything writes down.

1. **It lives in one file on the head, outside the repository**, at `~/.config/circt_bug_loop/github_token`,
   mode 0600, owned by the operator. The path is a constant in `bug_loop.py` and is overridable by
   `--github-token-file` for a machine with a different layout. It is outside the repository so that
   no `.gitignore` mistake can commit it and so that `runtime_env`'s `py_modules` upload, which ships
   directories, cannot sweep it up.
2. **Two components read it, and both are head nodes**: B6a's mirror refresh and B9a's filing
   reconciliation poll. That placement is CHIA's own documented one, `GithubIssuesNode` being a
   "Service-pattern node (head-node only, not a Ray task)"
   (`chia:chia/github/github_issues_node.py:31`), and the head driver runs on the host in its own
   conda environment rather than in a container
   (`chia:examples/circt_issue_solver/cluster.yaml:89-90`).
3. **It is passed as a constructor argument, never through the environment**:
   `GithubIssuesNode(repo, token=Path(token_path).read_text().strip(), state="all")`. The client
   prefers the argument over `GITHUB_TOKEN`, `self.token = token if token is not None else
   os.environ.get("GITHUB_TOKEN")` (`chia:chia/github/github_client.py:85`), so the value exists as a
   local string inside one head process and nowhere else.
4. **No worker container mounts it and no cluster YAML mentions it.** §12's two YAMLs carry no
   `GITHUB_TOKEN`, no token path and no `file_mounts` entry for one. A worker cannot reach the
   tracker at all, which is a stronger statement than a policy.
5. **The submit wrapper passes no token.** CHIA's own wrapper injects it through the job's
   runtime-env `env_vars`, and its own comment records the consequence: the value is stored in the
   job's `runtime_env` metadata and is visible in `chia job` output and the dashboard
   (`chia:examples/circt_issue_solver/fix_issues_submit.sh:21-24`, `46-50`). `bug_loop_submit.sh`
   therefore puts **no token** in `--runtime-env-json`, and the driver reads the file itself. That is
   the means NFR-06 asks this document to name. It does still pass `--runtime-env-json`, carrying
   `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG` and, when set, `GOOGLE_CLOUD_PROJECT`, none of which is a
   secret and all three of which the job process needs because a submitted job does not inherit the
   submitting shell's environment (§13.3, K13). Removing the flag along with the token was an
   over-correction that left FR-17.9's artefact root with no value at run time.

Nothing writes the value to disk, to a prompt, to a log or to a database row. FR-17.5's grep of the
artefact tree and NFR-06's extension of it to every prompt file and every transcript therefore pass
because there is nothing to find, not because everything was redacted.

**What this costs.** The mirror and the poll are serialised on the head rather than parallelised
across workers. Both are bounded and neither is on the campaign's critical path: the mirror runs once
per run before the first candidate, and the poll runs once per filing.

**GCP.** The same design, unchanged. `file_mounts` is an rsync to each node's **host**, run by
`chia up` before the container starts
(`chia:docs/user_guides/cluster_config_reference.rst:115-121`), so it would not have delivered a
credential into a container in any case; with the credential on the head, the GCP deployment needs no
credential mechanism of its own (`02-HLD.md` §4.3).

### 11.2 The model backend's credential

**Rewritten 2026-09-14** (ADR-D-03, superseding section; `02-HLD.md` §0.2, §4.3). Under the `claude`
backend this was a directory mount and never a value. Under the `vertex` backend it is a **value**:
one Google Cloud API key, which `VertexGeminiLLM` takes as
`client_kwargs={"api_key": ...}` and passes to `genai.Client(vertexai=True, ...)`
(`chia:chia/models/vertex.py:228`, `250`, `406-411`). So the loop now holds two credentials, the
GitHub read token of §11.1 and this key, and this subsection is the key's exact path. The struck
text below is kept because the `claude` fallback still uses it.

1. **One file on the head, outside every repository.** `~/.config/bugloop/gemini.env`, mode 0600,
   owned by the operator, one line, `GEMINI_API_KEY=...`. It is outside the repository so that no
   `.gitignore` mistake can commit it and so that `runtime_env`'s `py_modules` upload, which ships
   directories, cannot sweep it up. Nothing in the flow opens it by path: it is the operator's file
   and the operator's shell reads it.

2. **The operator sources it before `chia up`.** The README of §1.1 gives the four lines in one
   block, and `bug_loop.py --print-config` prints whether each is set, never a value:

   ```sh
   set -a; . ~/.config/bugloop/gemini.env; set +a
   export CHIA_HEAD=$(hostname)
   export BUGLOOP_ARTEFACTS=$HOME/circt_bug_loop_artefacts
   export BUGLOOP_IMAGE_TAG=<the tag B1 published>
   chia up cluster_single.yaml
   ```

3. **`chia up` expands it into the container's environment and nowhere else.**
   `cluster_single.yaml`'s `bugloop_llm` carries `-e GEMINI_API_KEY=${GEMINI_API_KEY}` in
   `run_options`, and CHIA's config loader substitutes `${VAR}` from `os.environ` over the whole
   parsed document at load, leaving bare `$VAR` alone
   (`chia:chia/cluster/config.py:300-309`, `694-710`, `951-957`). CHIA's own multi-backend test
   cluster passes `OPENAI_API_KEY` and `GOOGLE_CLOUD_PROJECT` exactly this way
   (`chia:chia/models/tests/cluster/all_models.yaml:143-152`), so the mechanism is CHIA's. The
   committed YAML holds the reference and never a key, which is what `tests/test_cluster_yaml.py`
   asserts by pattern rather than by value.

4. **The submit wrapper forwards no credential.** `bug_loop_submit.sh` keeps `--runtime-env-json`
   for exactly three non-secret variables (§13.3) and adds no fourth. `GEMINI_API_KEY` is
   deliberately **not** among them: a `runtime_env` value is stored in the job's metadata and is
   visible in `chia job` output and in the dashboard, which CHIA's own wrapper records as the reason
   (`chia:examples/circt_issue_solver/fix_issues_submit.sh:21-24`). The key reaches the worker
   through `docker run`, which the job never sees.

5. **`build_llm` reads `os.environ` on the process it is already running on** (§3.5.1) and passes
   the value inside the LLM object that `llm_turn` dispatches. That object crosses one Ray
   boundary, head to `llm` worker, and crosses it as a serialised argument rather than as job
   metadata. Nothing writes it to disk, to a prompt, to a log or to a database row, and the five
   per-turn artefact files of §6.5 are the turn's prompt, stream, transcript, stderr and usage, none
   of which contains a `client_kwargs`.

6. **NFR-06's grep covers the key's own value pattern.** FR-17.5 greps the artefact tree; NFR-06
   extends it to every prompt file, every transcript, both databases and the job metadata. From
   2026-09-14 the search set holds, besides the GitHub token's value, the regular expression
   `AQ\.[A-Za-z0-9_-]{30,}|AIza[0-9A-Za-z_-]{30,}`, which is the shape of a Google API key and is
   the pattern the team repository's own pre-commit scan already runs. `04-Test-Plan.md`
   `T-N-nfr06-01` and `T-U-store-10` both search for it, against a **synthetic** key in
   `fixtures/secrets/known_values.txt`; no real credential is ever committed, and no test reads
   `~/.config/bugloop/gemini.env`.

**The live-call interlock, stated here because it is a credential control and not only a test
convention.** A process holding the key can spend the user's credit, so the code refuses to build a
real backend unless `BUGLOOP_ALLOW_LIVE_MODEL=1` (§3.5.1, `build_llm`). The variable is set in the
operator's shell beside the key and travels to the `llm` workers by the same `-e` mechanism, so a
worker that has the key and not the interlock still cannot call Vertex. Tiers T0 to T2 never set it
and `04-Test-Plan.md` asserts that no test in those tiers does.

**What this costs.** The key is in the environment of two `llm` containers for the life of the
cluster, and `docker inspect` on the host shows it. That is a real exposure and it is the smallest
one available: the alternative, a mounted credentials directory, is what CHIA's `opencode` path uses
and needs Application Default Credentials and a GCP project, which the user's key is not.
`chia down` removes the containers and with them the environment.

~~**The `claude` backend's credential**, kept for the fallback.~~ It is a directory mount and never a
value, `-v ~/.claude:/home/ray/.claude`, read-write, because CHIA's own `run_setup_commands` copy
`/home/ray/.claude/.claude.json` to `/home/ray/.claude.json` and write a `settings.json` key inside
the container (`chia:examples/circt_issue_solver/cluster.yaml:36`, `42-43`;
`chia:examples/circt_issue_solver/README.md:63-84`). **A warning the operator is owed** (NIT 13):
read-write means a campaign on the fallback writes into the operator's **real** Claude configuration
directory, setting `skipDangerousModePermissionPrompt` to `true` in `~/.claude/settings.json`, and
that change outlives the campaign; an operator who does not want it should point `HOME` at a
throwaway directory for that `chia up`. A subscription rate limit was observed on 2026-09-13, so a
fallback campaign must not share the login with interactive work. The Claude model ids that ADR-D-03
originally named are **not** carried in this document any more: the fallback runs whatever id the
operator passes to `--repair-backend`'s companion `--repair-model`, and `05-Work-Plan.md`'s H-04,
which was to confirm two ids inside the `chia-claude-code` image, is optional.

## 12. The cluster YAMLs

### 12.1 `cluster_single.yaml`, in full

Derived from `chia:examples/circt_issue_solver/cluster.yaml` and the cluster configuration reference.
Five worker containers on one host, plus the head. Three worker types and no more.

```yaml
# Ray cluster for the closed CIRCT bug loop - SINGLE MACHINE, 5 containers.
#
#   bugloop_llm    : 2 x chia:latest,          llm:1    -> 2 concurrent prompts
#   bugloop_circt  : 2 x chia-circt-assert,    circt:1  -> 2 concurrent probes
#   bugloop_repair : 1 x chia-circt-assert,    repair:1 -> 1 repair attempt
#
# llm:1 per container, not llm:2. The concurrent-prompt cap is then exactly the
# container count, which is what RunManifest.llm_concurrency records and what
# FR-14.5 requires the manifest to name.
#
# bugloop_repair exists because CHIA's phase chain rebuilds WITH THE AGENT'S DIFF
# APPLIED and returns without restoring, and the next task's reset is `git reset
# --hard` then `git clean -fd`, explicitly NOT -x, so the build tree survives. On
# a shared pool every verdict after the first repair attempt could be taken
# against a binary that is not the image's (FR-12.11).
#
# The SAME `git clean -fd` is what deletes CHIA's default repro directory,
# /workspace/circt/.circtissues, which is untracked and not gitignored. That is
# why section 3.8 puts the loop's repro directory under the artefact root
# instead, outside the tree the clean touches (K9). One mechanism, two
# consequences, and the design now names both in the same place.
#
# min_workers == max_workers on all three types, so the cluster is fixed-size and
# apparatus_concurrency is exactly the bugloop_circt count. BOTH ARMS RUN FROM
# THIS ONE YAML AT THIS ONE CONCURRENCY, one after the other, which is what makes
# the wall-clock equality of FR-14.5 mean anything.
#
# Everything runs on ONE machine. The host is read from CHIA_HEAD:
#   set -a; . ~/.config/bugloop/gemini.env; set +a
#   export CHIA_HEAD=$(hostname)
#   export BUGLOOP_ARTEFACTS=$HOME/circt_bug_loop_artefacts
#   export BUGLOOP_IMAGE_TAG=<the tag B1 published>
# before `chia up`. No GITHUB_TOKEN appears anywhere in this file, by design
# (NFR-06, NFR-07): the token lives in one 0600 file on the head and the two
# components that read it are head nodes.
#
# GEMINI_API_KEY DOES appear, as a ${...} REFERENCE and never as a value.
# chia.cluster.config._expand_env_vars substitutes ${VAR} from the operator's
# shell over the whole document at load (chia:chia/cluster/config.py:300-309,
# 694-710, 951-957), so the key lands in the host's `docker run` command and in
# the llm container's environment, and NEVER in `chia job submit` runtime-env
# metadata, which is visible in `chia job` output and the dashboard. CHIA's own
# all_models.yaml passes OPENAI_API_KEY the same way (chia/models/tests/cluster/
# all_models.yaml:143-152). Section 11.2 is normative.
cluster_name: circt_bug_loop

available_node_types:
    bugloop_llm:
        resources: {"llm": 1}
        balance_level: cluster
        min_workers: 2
        max_workers: 2
        docker:
            # The vertex backend is a PYTHON client in the chia package, not a
            # CLI, so the canonical chia base is the whole image requirement:
            # "rayproject/ray:2.54.0-cpu with the chia package pip-installed on
            # top" (chia:docs/user_guides/docker_images.rst:45-49), which brings
            # google-genai>=1.64.0 and mcp==1.27.1 with it
            # (chia:pyproject.toml:24-35). Nothing is layered on at setup.
            image: "ghcr.io/ucb-bar/chia:latest"
            container_name: "circt_bug_loop_llm_${USER}"
            pull_before_run: True
            run_options:
                # No --cpus / --memory here, unlike the other two types, and that
                # is deliberate rather than an omission: this container makes
                # HTTPS calls and holds no CIRCT tree, so NFR-05's outer level
                # has nothing to protect the machine from. The concurrency cap is
                # the llm:1 resource and the container count, which is what
                # RunManifest.llm_concurrency records.
                - --ulimit nofile=65536:65536
                - --shm-size=10.24gb
                - "--user $(id -u):$(id -g)"
                # The ONE credential line. A reference, expanded from the
                # operator's shell at `chia up`; see the header and 11.2.
                - "-e GEMINI_API_KEY=${GEMINI_API_KEY}"
                # The live-call interlock travels with it, so a worker that has
                # the key and not this still cannot reach Vertex (3.5.1). Unset
                # in every tier below T3, and set only for the pilot onward.
                - "-e BUGLOOP_ALLOW_LIVE_MODEL=${BUGLOOP_ALLOW_LIVE_MODEL}"
                - "-v $SSH_AUTH_SOCK:/ssh-agent"
                - "-e SSH_AUTH_SOCK=/ssh-agent"
            run_setup_commands:
                # One line, down from four. The two Claude lines are gone with
                # the CLI: no ~/.claude mount, no .claude.json copy, no
                # skipDangerousModePermissionPrompt write into the operator's
                # real configuration directory.
                - echo "user:x:$(id -u):$(id -g)::/home/ray:/bin/bash" >> /etc/passwd
                - mkdir -p ~/.ssh && ssh-keyscan github.com >> ~/.ssh/known_hosts 2>/dev/null
        compatible_ips: ["${CHIA_HEAD}"]

    bugloop_circt:
        resources: {"circt": 1}
        balance_level: cluster
        min_workers: 2
        max_workers: 2
        docker:
            image: "ghcr.io/ucb-bar/chia-circt-assert:${BUGLOOP_IMAGE_TAG}"
            container_name: "circt_bug_loop_circt_${USER}"
            pull_before_run: True
            run_options:
                - --ulimit nofile=65536:65536
                - --shm-size=10.24gb
                # --user, on EVERY worker type and not only bugloop_llm. The
                # artefact root below is bind-mounted from a host directory the
                # OPERATOR owns; a container running as the image's own user
                # writes into it as that user and pre-flight check 5 fails on the
                # first worker that tries. Matching uid and gid is what makes the
                # mount writable from both sides (FR-17.9).
                - "--user $(id -u):$(id -g)"
                # NFR-05's OUTER level: these protect the worker and the machine.
                # The probe's own rlimits, set by prlimit on its argv, are what
                # classify the probe. A container-level kill removes the worker and,
                # under max_retries=0, fails the task with no probe status at all,
                # which section 6 of 02-HLD.md has a row for.
                - --cpus=6
                - --memory=24g
                - --memory-swap=24g
                # FR-17.9's artefact mount: one host directory, bind-mounted at the
                # IDENTICAL absolute path in every container, so a worker-produced
                # file reaches the head's tree with no copy step and
                # RunManifest.artefact_root means one thing everywhere.
                - "-v ${BUGLOOP_ARTEFACTS}:${BUGLOOP_ARTEFACTS}"
                - "-v $SSH_AUTH_SOCK:/ssh-agent"
                - "-e SSH_AUTH_SOCK=/ssh-agent"
            run_setup_commands:
                - echo "user:x:$(id -u):$(id -g)::/home/ray:/bin/bash" >> /etc/passwd
                - git config --global user.email 'circt_bug_loop@chia' || true
                - git config --global user.name  'circt_bug_loop'       || true
                - git config --global --add safe.directory /workspace/circt || true
                # NO `pip install lit` line. lit is baked into the image exactly
                # once, at /home/ray/anaconda3/envs/py_worker/bin/lit, which is the
                # path circt_warm_build checks, so a conditional install finds it
                # present and does nothing (FR-03.8).
        compatible_ips: ["${CHIA_HEAD}"]

    bugloop_repair:
        resources: {"repair": 1}
        balance_level: cluster
        min_workers: 1
        max_workers: 1
        docker:
            image: "ghcr.io/ucb-bar/chia-circt-assert:${BUGLOOP_IMAGE_TAG}"
            container_name: "circt_bug_loop_repair_${USER}"
            pull_before_run: True
            run_options:
                - --ulimit nofile=65536:65536
                - --shm-size=10.24gb
                - "--user $(id -u):$(id -g)"
                - --cpus=8
                - --memory=32g
                - --memory-swap=32g
                - "-v ${BUGLOOP_ARTEFACTS}:${BUGLOOP_ARTEFACTS}"
                - "-v $SSH_AUTH_SOCK:/ssh-agent"
                - "-e SSH_AUTH_SOCK=/ssh-agent"
                - "-e GEMINI_API_KEY=${GEMINI_API_KEY}"
                - "-e BUGLOOP_ALLOW_LIVE_MODEL=${BUGLOOP_ALLOW_LIVE_MODEL}"
            run_setup_commands:
                - echo "user:x:$(id -u):$(id -g)::/home/ray:/bin/bash" >> /etc/passwd
                - git config --global user.email 'circt_bug_loop@chia' || true
                - git config --global user.name  'circt_bug_loop'       || true
                - git config --global --add safe.directory /workspace/circt || true
        compatible_ips: ["${CHIA_HEAD}"]

provider:
    head_ip: ${CHIA_HEAD}

auth:
    ssh_user: ${USER}

# 2 llm + 2 circt + 1 repair = 5 workers, all on the one machine.
min_workers: 5
max_workers: 5
upscaling_speed: 1.0
idle_timeout_minutes: 5

file_mounts: {}
cluster_synced_files: []
file_mounts_sync_continuously: False
rsync_exclude: ["**/.git", "**/.git/**"]
rsync_filter: [".gitignore"]
initialization_commands: []
setup_commands: []
worker_setup_commands: []

head_setup_commands:
    - "source ~/.bashrc && conda activate circtbugloop"
head_start_ray_commands:
    - "source ~/.bashrc && conda activate circtbugloop && ray stop"
    - "source ~/.bashrc && conda activate circtbugloop && ulimit -c unlimited && ray start --head --port=6379 --include-dashboard=True --dashboard-agent-listen-port=0"
worker_start_ray_commands:
    - ray stop
    - ray start --address=$RAY_HEAD_IP:6379 --dashboard-agent-listen-port=0
```

Every key above is one CHIA documents: `resources`, `balance_level`, `min_workers`, `max_workers`,
`docker.image`, `docker.container_name`, `docker.pull_before_run`, `docker.run_options`,
`docker.run_setup_commands` and `compatible_ips`, with `run_options` documented as "Extra flags passed
to `docker run` (ulimits, shm size, volume mounts, `--user`, env vars, ...)"
(`chia:docs/user_guides/cluster_config_reference.rst:326-329`) and `run_setup_commands` as "Commands
run inside the container after it starts, before the worker's main script"
(`chia:docs/user_guides/cluster_config_reference.rst:330-333`).

**The two SQLite nodes are not in this file, and cannot be.** Both `loop.db` and CHIA's unchanged
`issues.db` are `SQLiteNode`s constructed on the head by the driver after `ray.init()`, with
`pin_to_current_node=True` (§6.1); no CHIA cluster YAML declares a database node type or a `database`
resource, verified across every YAML under `examples/`. What this file contributes to them is the
head placement they pin to, which is `head_setup_commands` activating the driver's environment on the
host. Their paths are `bug_loop.py` constants and are printed by `bug_loop.py --print-config`.

**Two containers on one host are two Ray nodes**, which is what makes FR-13.2's different-worker
preference expressible at all: `chia up` suffixes the container name per worker index
(`chia:chia/cluster/node_setup.py:621-623`) and runs `ray start --address=...` inside each
(`chia:chia/cluster/node_setup.py:542-548`; the two `worker_start_ray_commands` lines above).

### 12.2 `cluster_gcp.yaml`, a skeleton, deferred

Written **only if** the hackathon's cloud credits are confirmed by the date `05-Work-Plan.md` names
(ADR-D-14, NFR-10's Should). It carries the **same three worker types, the same resource names and
the same images**, so no loop code changes between the two, and `RunManifest.deployment` records
which ran.

```yaml
# DEFERRED under ADR-D-14. Written only if the credits are confirmed by the date
# 05-Work-Plan.md names. Same three worker types, same resource names, same
# images as cluster_single.yaml; only the provider section and the artefact tree
# differ.
cluster_name: circt_bug_loop_gcp

# provider.head_ip is required by chia.cluster.config.load_config, which raises
# KeyError 'head_ip' without it, so the placeholder is here and the file parses
# even while the rest is deferred (W28). It resolves from the environment, as
# CHIA_HEAD does in cluster_single.yaml.
provider:
    head_ip: ${BUGLOOP_GCP_HEAD_IP}

auth:
    ssh_user: chia

gcp_nodes:
    project: ${BUGLOOP_GCP_PROJECT}      # required
    zone: us-central1-a                  # the reference's default
    bugloop_circt:
        machine_type: n2-standard-8
        count: 2
        ssh_user: chia
        ssh_public_key: ${HOME}/.ssh/id_ed25519.pub
        ssh_private_key: ${HOME}/.ssh/id_ed25519
        disk_size_gb: 200                # the image is measured at 4.79 GB plus a 1.3 GB build tree
    bugloop_repair:
        machine_type: n2-standard-8
        count: 1
        ssh_user: chia
        ssh_public_key: ${HOME}/.ssh/id_ed25519.pub
        ssh_private_key: ${HOME}/.ssh/id_ed25519
        disk_size_gb: 200
    bugloop_llm:
        machine_type: n2-standard-2
        count: 2
        ssh_user: chia
        ssh_public_key: ${HOME}/.ssh/id_ed25519.pub
        ssh_private_key: ${HOME}/.ssh/id_ed25519
        disk_size_gb: 50

# available_node_types: identical to cluster_single.yaml except that the artefact
# bind mount is replaced, see below.
#
# THE ONE THING GCP DEFERS. Section 4.1's `-v <host>:<same path>` is a
# single-machine mechanism: on GCP the workers are other machines and a host path
# is not shared. The GCP deployment therefore needs shared storage mounted at
# RunManifest.artefact_root on every node AND on the head - a bucket via gcsfuse,
# or a Filestore export - and that work is deferred with GCP under ADR-D-14.
# Nothing in the Must depends on it, and FR-17.9's "a worker that cannot open it
# shall fail the run" is what stops a GCP run starting without it.
```

`project` is required and `zone` defaults to `us-central1-a`; every other key lives under a named node
type (`chia:docs/user_guides/cluster_config_reference.rst:447-470`).

**It parses, and it is still deferred.** With `BUGLOOP_GCP_PROJECT` and `BUGLOOP_GCP_HEAD_IP` set,
`chia.cluster.config.load_config("cluster_gcp.yaml")` returns a `ClusterConfig` rather than raising
`KeyError 'head_ip'`. That is the standard this document is written to, "an engineer types it in
without asking a question", applied to a file §14.1 lists as a deliverable; it does not make the GCP
deployment ready, and the shared-artefact-store question below is still the thing ADR-D-14 defers.
`BUGLOOP_GCP_HEAD_IP` joins §13.4's table as the fifth environment variable, read by this file only.

---

## 13. Entry points, the CLI, and the environment

### 13.1 The campaign driver, `bug_loop.py`

```
usage: bug_loop.py [-h] --mode {discovery,calibration} [--arm {seeded,mutation,both}]
                   [--budget PATH] [--cluster-yaml PATH] [--clone PATH]
                   [--artefact-root PATH] [--github-token-file PATH]
                   [--repair-backend {vertex,claude,antigravity,opencode}]
                   [--repair-model ID] [--no-repair]
                   [--image-tag TAG] [--resume RUN_MANIFEST_ID] [--dry-run]
                   [--refresh-mirror] [--draw-calibration] [--record-fixtures DIR]
                   [--print-config]
```

| Argument | Default | Meaning |
|---|---|---|
| `--mode` | required | `discovery` or `calibration`; `RunManifest.mode`, and every results row names it (ADR-D-01, FR-18.2). |
| `--arm` | `both` | Which arm to run. `both` runs them **sequentially**, in `budget.yaml`'s `arm_order`. This is FR-19.3's "one configuration change, not a code change". |
| `--budget` | `./budget.yaml` | The pre-registered file. Its commit is the registration. |
| `--cluster-yaml` | `./cluster_single.yaml` | Hashed into `RunManifest.cluster_yaml_sha`, because a YAML change mid-campaign invalidates the comparison (ADR-D-04). |
| `--clone` | `~/.cache/circt` | The blobless `llvm/circt` clone A1, A2 and B6b read. |
| `--artefact-root` | `$BUGLOOP_ARTEFACTS` | The one path of FR-17.9; must be the path the YAML bind-mounts. |
| `--github-token-file` | `~/.config/circt_bug_loop/github_token` | §11.1. |
| `--repair-backend`, `--repair-model`, `--no-repair` | **`vertex`**, none, off | **2026-09-14, amended later the same day (§3.8).** The loop's own agent stages take no backend or model flag at all: the backend is `vertex` because the cluster YAML says so (C-20), and the model id is `budget.yaml`'s `model_id` because the pre-registration says so. These three exist only for stage 7. ~~`claude`~~ as the default is **withdrawn**: the additive `elif backend == "vertex":` branch of §3.8 makes CHIA's chain implement the campaign backend, so the default is `vertex` and `--repair-model` defaults to `budget.yaml`'s own `model_id`, `gemini-3.8-flash`. ~~whose chain CHIA implements for three backends and not for `vertex`~~ is withdrawn with it. The other three choices survive as the **outage fallback** named by ADR-D-03, and choosing one is what makes `stages_metered["stage_7"]` false. `--no-repair` runs the campaign with F-12 disabled and `repair_disabled` as the stated reason, and is also the way to run a campaign whose reported USD spend is complete, stage 7's tokens being unobservable (§3.8). ~~`--backend`, `--model`~~ are **withdrawn**: neither had a consumer once the model id moved into the budget file, and a `--model` flag would have been a free parameter that the pre-registration exists to remove. |
| `--image-tag` | `$BUGLOOP_IMAGE_TAG` | The assertions-on image B1 built. |
| `--resume` | none | Reuses a `run_manifest_id`, skips iterations whose records are complete, and refuses to continue if the budget file SHA no longer matches (FR-14.7). |
| `--dry-run` | off | Runs every pre-flight check and the manifest build, and dispatches nothing. |
| `--refresh-mirror` | off | Re-runs B6a even where a mirror for this campaign exists. FR-10.9's acceptance is "a second run in the same campaign reuses the mirror **unless the operator asks for a refresh**" and pre-flight check 10 restates it; this flag is the asking, and without it there was no mechanism (W25). Refreshing rewrites `issue_mirror` and stamps a new `issue_mirror_meta` row, and the manifest records which run's mirror each candidate was screened against. |
| `--draw-calibration` | off | Prints `calibration_sample_size` SHAs sampled from the exact-pin seeds with `random.Random(corpus_head_sha)`, for the operator to paste into `budget.yaml` **before** the pre-registration commit, and exits. It writes nothing (§9.2 check 5, W12). |
| `--record-fixtures` | none | `02-HLD.md` §2.13's recording mode: every instance the half produces is written to the directory after `validate` accepts it. |
| `--print-config` | off | Prints the resolved paths, both database paths, the clone, the model-credential directory §11.2 mounts, and the artefact root, and exits. |

**Eleven pre-flight checks, in this order, each of which stops the run.** They are ordered cheapest
first, so a misconfiguration is caught before an image build is attempted.

1. `budget.yaml` is committed and its commit predates the run's start (FR-14.2).
2. The mutator set's last commit predates the budget file's (FR-05.2, §8.1).
3. The clone's HEAD equals `corpus_head_sha` (FR-01.11).
4. The artefact root exists and is writable **on the head**.
5. The artefact root exists and is writable **on every worker**, checked by dispatching a trivial
   node per worker type that writes and removes one file under it; a failure is
   `artefact_root_unmounted`, names the worker and the path, and stops the run (FR-17.9,
   `02-HLD.md` §6, B10b's third row).
6. The image exists, and its `ImageSpec.lit_discovery_ok` is true (FR-03.17).
7. Every tool binary's SHA-256 on every worker matches `ImageSpec.tool_hashes` (FR-06.1).
8. `verilator --version` on every CIRCT worker equals `ImageSpec.verilator_version`; a difference
   exits non-zero naming both, because a changed Verilator starts a new campaign (FR-03.15).
9. The pin selector runs and the manifest's pin fields are stamped (FR-02.1 to FR-02.4).
10. The issue mirror is refreshed, or an existing one for this campaign is reused (FR-10.9).
11. `RunManifest.forum_post_url` and `forum_post_date` are present, because the method is posted to
    CIRCT's forum before the campaign starts (FR-20.1).
12. **The live-model interlock and the key are set, and agree** (2026-09-14, extended later the same
    day). `BUGLOOP_ALLOW_LIVE_MODEL` is exactly `1` on the head **and** on every `bugloop_llm` worker,
    and `GEMINI_API_KEY` is
    non-empty and not an unexpanded `${...}` reference on both, checked by dispatching a trivial node
    per `llm` worker that returns two booleans and **never the values**. **The `bugloop_repair` worker
    is checked too, on the same two variables, whenever repair is enabled**, because stage 7's backend
    is now constructed there by CHIA's `_turn` and `repair_adapt` gates it with the same interlock
    (§3.8): a repair container without the key would fail with a `KeyError` on
    `os.environ["GEMINI_API_KEY"]` inside CHIA's file rather than with a refusal, which is the failure
    mode this check exists to convert. §12.1's `bugloop_repair` row carries both `-e` lines for that
    reason. Under `--repair-backend claude` only the interlock half is required there. A failure names the worker
    and the variable and stops the run before a single turn is dispatched, so a campaign cannot
    discover the misconfiguration eight seeds in. `--dry-run` runs this check like any other, which
    is how an operator confirms the cluster is ready to spend money without spending any.

**Every `RunManifest` field, and who computes it.** Half the forty had no named producer (W27), which
for a document whose standard is "an engineer types it in" is the same defect as a missing signature.
The table is by source, because most fields share one.

| Source | Fields |
|---|---|
| argv, directly | `mode`, `seed_set`, `artefact_root`, `deployment` (`gcp` when `--cluster-yaml` names the GCP file, else `single_machine`) |
| `generate_task.MODEL_BACKEND` | `backend`, which is the constant `vertex` and not an argument (§3.5.1) |
| generated by B12 | `run_manifest_id` (a `uuid4` hex, or `--resume`'s value), `started_utc`, `ended_utc` |
| A2's eight returned fields | `run_commit`, `pin_sha`, `pin_tag`, `tags_sharing_pin`, `lag_commits`, `lag_days`, `current_window_has_release` |
| A1 | `corpus_head_sha`, and `sv_seeds_excluded` from the seeds A1 marked ineligible under ADR-D-13 branch (b) |
| A6a, from `budget.yaml` | `budget_unit`, `arm_window_seconds`, `arm_order`, `budget_file_sha`, `calibration_sample` (which is `calibration_sample_shas`) |
| B1's `ImageSpec` | `image_spec`, and `mutator_set_sha` from the frozen set's digest |
| B6a's return | `issue_mirror`, its six keys verbatim |
| the cluster YAML | `cluster_yaml_sha` (`hashlib.sha256` of the file B12 was given), `worker_type` (the `circt` type's name), `apparatus_concurrency` (its `max_workers`), `llm_concurrency` (the `llm` type's `max_workers`) |
| §9.4 constants | `local_id_range` (`[LOCAL_ID_BASE, LOCAL_ID_MAX]`), `x_policy` (`X_POLICY`) |
| §3.6.3's rule | `differential_driver`, its four keys, from whether `circt/arc-tests` was reused or a deviation was recorded |
| the image's own acceptance run | `assertion_baseline_count`, the number of firings FR-07.9's control run over the lit corpus produced, which is expected to be zero and is recorded whatever it is |
| `budget.yaml`'s `model_id` plus `--repair-backend` | `model_ids`, one `"<backend>:<model id>"` per model stage: `vertex:<model_id>` for `generate_seeded`, `triage_report` and `mutator_synthesis`, and `"<repair backend>:<repair model>"` for `repair_adapt`, which on a default run is **`vertex:<model_id>` too** (§2.7, §3.8); `stages_metered`, one bool per `_STAGE_IDS` entry, all true but `stage_1` and `stage_2` on the mutation arm, where no model runs, and `stage_7` whenever its backend differs from `backend`, **which on a default run it does not**, so `stages_metered["stage_7"]` is **true** by default (2026-09-14, §3.8) |
| the operator, via pre-flight check 11 | `forum_post_url`, `forum_post_date` |
| `budget.yaml`'s `campaign_end_utc` | `confirmation_cutoff_date`, which is that value's date part (FR-18.8) |

A field with no value at manifest-build time stops the run; `--dry-run` builds the manifest and is
the cheapest way to find out which.

**The run loop.** One manifest, one image, one mirror, then the arms one after the other in
`arm_order`, each for `arm_window_seconds` metered on the head. Inside an arm, seeds are dispatched
across the two `circt` slots with `TrackedRef` and `chia_wait(pending_timeout=..., retry=True)`, which
is CHIA's own fan-out and collect pattern
(`chia:examples/circt_issue_solver/circt_issue_loop.py:252-273`). When the window expires B12 stops
dispatching, waits for in-flight probes to return or to hit their own timeouts, writes the arm's one
`arm_window` ledger entry, and starts the next arm. At the end it runs the reconciliation of
FR-12.10 and renders the results.

**Every collected return carries a `CounterBlock` and B12 logs it as it collects** (§2.5, §3.11,
FR-17.4). The driver reads the `"counters"` key of each return, checks
`started == completed + failed`, hands the block to CHIA's `MetricsLogger` keyed by
`(run_manifest_id, arm, stage)`, and rewrites `<artefact_root>/<run>/results/counters.json` with the
running totals. That file is what NFR-09's "the metrics directory shows per-stage counters **during**
the run" reads, and it is written on every aggregation rather than at the end, so a campaign that is
stopped mid-window still leaves a complete count of what it did.

**`_PY_MODULES`**, which ships the worker modules through the **driver's** `ray.init`, as CHIA does
(`chia:examples/circt_issue_solver/circt_issue_loop.py:105-113`, `204-206`):

**The four path constants, and why three of them are derived from the `chia` module** (2026-09-14,
§1.4). The flow is developed at `circt_bug_loop/` in the team repository and published at
`examples/circt_bug_loop/` in a CHIA checkout, so nothing may walk up from `__file__` to find CHIA:
`FLOW_DIR.parent.parent` is a CHIA checkout in one tree and the team repository's root in the other.

```python
import chia

FLOW_DIR = Path(__file__).resolve().parent            # the flow, in either tree
_CHIA_PKG = Path(chia.__path__[0]).resolve()          # the INSTALLED package
_CHIA_ROOT = _CHIA_PKG.parent                         # its checkout, if it is one
_ISSUE_SOLVER = _CHIA_ROOT / "examples" / "circt_issue_solver"
```

`chia.__path__[0]` and not `chia.__file__`: CHIA ships as a namespace package, so `chia.__file__` is
**`None`** and `Path(chia.__file__)` raises. **Measured 2026-09-14** in `~/.cache/chia-venv`:
`chia.__file__` is `None` and `chia.__path__` is
`_NamespacePath(['/home/adi/.cache/chia-src/chia', ...])`, whose first entry is the package
directory. `_ISSUE_SOLVER` needs `examples/` beside the package, which an editable install of a
checkout gives and a wheel install does not; `bug_loop.py` therefore checks that
`_ISSUE_SOLVER / "issue_task.py"` exists at import and exits with a named error otherwise, naming
`--chia-root` as the override. That is the one place the two-tree layout can bite, and it bites at
start-up rather than at the first repair attempt.

```python
_PY_MODULES = [
    str(FLOW_DIR / "probe_task.py"),
    str(FLOW_DIR / "generate_task.py"),
    str(FLOW_DIR / "triage_task.py"),
    str(FLOW_DIR / "repair_adapter.py"),
    str(FLOW_DIR / "gate.py"),
    str(FLOW_DIR / "store.py"),
    str(FLOW_DIR / "corpus.py"),
    str(FLOW_DIR / "pin_select.py"),
    str(FLOW_DIR / "ddmin.py"),
    str(FLOW_DIR / "mutators"),
    str(FLOW_DIR / "contract"),
    str(_CHIA_PKG),
    str(_ISSUE_SOLVER / "issue_task.py"),
    str(_ISSUE_SOLVER / "circt_util.py"),
]
_RUNTIME_ENV_EXCLUDES = ["**/__pycache__", "**/*.pyc"]
```

`py_modules` takes directories as well as files, which is how `chia` itself ships, so `contract/` and
`mutators/` travel as packages rather than as loose files. The last two entries are the sharp ones
and they are deliberate: **B8 needs CHIA's own `issue_task.py` and `circt_util.py` on the worker's
`sys.path`, from a different example directory**, because FR-12.1 forbids **copying** them and allows
only the one additive branch of §3.8.
One example shipping another's worker modules has no precedent in CHIA's `examples/`, and it is the
price of running the chain as CHIA wrote it. The shipped `issue_task.py` is the **patched** one, which
is what `sync-to-chia.sh` produces and what `T-U-repair-07`'s hunk comparison is taken against.

### 13.2 The approval CLI, `approve.py`

Installed as `bugloop-approve` by the example's own console-script entry, and runnable as
`python approve.py` from the flow directory. The entry needs a packaging file and §1.1 now lists one
(W19): `pyproject.toml` in the flow directory, carrying a `[project.scripts]` line
`bugloop-approve = "approve:main"` and nothing else. `examples/` is not a package CHIA installs, so
the file is installed by `pip install -e examples/circt_bug_loop` on the head only, which is where the
CLI runs; the `python approve.py` spelling works without it and the README gives both. It is the only
interface a human touches (ADR-D-12, FR-13.18).

```
usage: bugloop-approve [-h] --approver NAME [--db PATH] [--artefact-root PATH]
                       {list,show,approve,reject,url,status} ...
```

| Command | Arguments | What it does |
|---|---|---|
| `list` | `[--held] [--pending]` | Prints every candidate whose gate decision is `report` or `report_plus_patch` and which has no `filing` row, one line each: candidate id, arm, oracle class, decision, fingerprint prefix, held reason. |
| `show` | `<candidate_id>` | Prints, in one view (FR-13.12): the full rendered report; the four gate answers with the stopping question; the repair diff if any; and the reduced case. Read-only. |
| `approve` | `<candidate_id>` | Runs the refusals, shows the same view, asks for a typed `yes`, asks for FR-20.5's licence confirmation **with the patch on screen** whenever the decision is `report_plus_patch`, then writes one `filing` row carrying the approver, the timestamp, the decision and the confirmation. Prints the pre-filled issue URL, or the fallback instruction. |
| `reject` | `<candidate_id> --reason TEXT` | Records a human rejection against the candidate. No filing is possible afterwards. |
| `url` | `<candidate_id> <issue_url>` | Records the issue URL where FR-13.16's poll found nothing, against the same report id (FR-13.18). Refuses a URL unless its scheme is `https`, its host **is** `github.com` **and** its path begins `/llvm/circt/issues/` and ends in digits. The conjunction is on the **accept** side; the earlier wording put it on the refuse side, "refuses a URL whose host is not github.com **and** whose path is not under llvm/circt/issues/", which accepts a `github.com` URL with any path at all (NIT 14). |
| `status` | `[<candidate_id>]` | Prints the filing rows and their confirmation state, which is the G-27 numerator's own audit trail. |

**The refusals run before anything is shown**, in this order, each printing why and exiting non-zero:
the per-UTC-day filing cap (FR-13.8, counted from `filing.approved_at_utc` over the current UTC day);
the total cap; the `good first issue` refusal, read from the `issue_labels` key of the candidate's
`dedup_evidence` (FR-13.9); FR-11.8's hold; and a second approval of an already-approved candidate,
which is refused with the first approval's timestamp (FR-13.13).

**The pre-filled URL** (ADR-D-02 option (c)) is

```python
url = ("https://github.com/llvm/circt/issues/new?"
       + urllib.parse.urlencode({"title": report.title, "body": body}))
```

`llvm/circt` has no `.github/ISSUE_TEMPLATE/` directory, so `?title=&body=` prefill is available at
all (verified). If `len(url) > PREFILL_URL_CHAR_LIMIT`, which is 6,000 `[DEFAULT]`, the CLI prints
the fallback instruction instead, the human files by hand from `report.md`, and
`FilingRecord.prefill_fallback_reason` records why (FR-13.17). The filed body always carries the
primary fingerprint, which is what FR-13.16's poll matches on.

**Nothing is written until an approval is complete.** A human who walks away leaves the candidate
`held` with `held_reason=awaiting_approval`, the store unchanged, and the next invocation presenting
the same report, so an approval is never partially recorded (`02-HLD.md` §6, B9c's last row).

### 13.3 `bug_loop_submit.sh`

Same shape as CHIA's wrapper, and with the token line removed **and the three non-secret variables
kept**.

```sh
#!/usr/bin/env bash
# Submit the circt_bug_loop driver as a job via `chia job submit`, so its driver
# logs appear in the dashboard and via `chia job logs <id>` (NFR-09). Running the
# driver directly registers a DRIVER-type job whose stdout the job server does
# NOT capture; only a SUBMISSION job gets retrievable logs
# (chia:examples/circt_issue_solver/fix_issues_submit.sh:5-9).
#
# THE ONE DIFFERENCE FROM CHIA'S WRAPPER IS THE TOKEN, AND ONLY THE TOKEN.
# CHIA's own wrapper injects GITHUB_TOKEN through the job's runtime-env env_vars,
# and its own comment records that the value is then stored in the job's
# runtime_env metadata and is visible in `chia job` output and the dashboard. The
# loop's driver reads the token from a 0600 file on the head instead (NFR-06,
# section 11.1), so no token appears below.
#
# --runtime-env-json ITSELF IS KEPT. A `chia job submit` SUBMISSION job does not
# inherit the submitting shell's environment, which is precisely why CHIA's
# wrapper forwards anything at all; removing the flag with the token would leave
# bug_loop.py's --artefact-root and --image-tag defaults resolving to nothing
# inside the job process, FR-17.9's single artefact root with no value at run
# time, and pre-flight checks 4 and 5 checking the wrong path. The three
# variables below are NOT secrets: two are a path and a tag this repository's own
# README prints, and the third is a GCP project id CHIA's own wrapper forwards
# for the same reason (chia:examples/circt_issue_solver/circt_issue_loop.py:71-72).
#
# GEMINI_API_KEY IS NOT FORWARDED EITHER, and that is the second half of the same
# rule (11.2 step 4, added 2026-09-14). The model credential reaches the llm
# workers through `docker run -e ...` at `chia up`, expanded from the operator's
# shell by CHIA's config loader; a runtime_env value would instead be stored in
# the job's metadata and shown by `chia job` and the dashboard. Nor is
# BUGLOOP_ALLOW_LIVE_MODEL forwarded: it is a cluster-level interlock, set in the
# operator's shell beside the key, and a job that could set it would be a job
# that could switch the loop live.
set -euo pipefail

ADDR="${RAY_JOB_ADDR:-http://localhost:8265}"
FLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYBIN="${BUGLOOP_PY:-python}"
CHIABIN="${BUGLOOP_CHIA:-chia}"

: "${BUGLOOP_ARTEFACTS:?set BUGLOOP_ARTEFACTS to the bind-mounted artefact root}"
: "${BUGLOOP_IMAGE_TAG:?set BUGLOOP_IMAGE_TAG to the assertions-on image tag}"

ENV_JSON="$("$PYBIN" - <<'PY'
import json, os
env = {"BUGLOOP_ARTEFACTS": os.environ["BUGLOOP_ARTEFACTS"],
       "BUGLOOP_IMAGE_TAG": os.environ["BUGLOOP_IMAGE_TAG"]}
gcp = os.environ.get("GOOGLE_CLOUD_PROJECT")
if gcp:
    env["GOOGLE_CLOUD_PROJECT"] = gcp
print(json.dumps({"env_vars": env}))
PY
)"

WAIT_FLAG=()
[ "${NO_WAIT:-0}" = "1" ] && WAIT_FLAG=(--no-wait)

exec "$CHIABIN" job submit \
  --address "$ADDR" \
  --runtime-env-json "$ENV_JSON" \
  "${WAIT_FLAG[@]}" \
  -- "$PYBIN" "$FLOW_DIR/bug_loop.py" "$@"
```

The JSON is built by Python rather than by string concatenation so a path containing a quote or a
space cannot break the argument, and `GOOGLE_CLOUD_PROJECT` is included only when it is set, because
an empty value would make `--repair-backend opencode` fail later rather than at submission. §11.1's posture
is unchanged and is stronger stated precisely: **no secret** goes through `--runtime-env-json`, and
the flag itself is not the hazard.

`chia job submit` proxies to `ray job submit` (`chia:chia/cli/main.py:200-210`), and `chia job stop`
is the one augmented subcommand, taking `--kill-tracked-pids` and `--grace-period`
(`chia:chia/cli/job.py:22-32`). `chia up cluster_single.yaml` and `chia down cluster_single.yaml`
bring the cluster up and down, both taking `-y/--yes`, `-v/--verbose` and `--dry-run`
(`chia:chia/cli/main.py:101-124`).

### 13.4 Environment variables

**Eight from 2026-09-14**, six before it. Every other parameter is a `budget.yaml` key, a CLI
argument or a module constant.

| Variable | Read by | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | `cluster_single.yaml` (as a `${...}` reference), `generate_task.build_llm` on the worker | **The model credential, and the only secret in this table.** Sourced by the operator from `~/.config/bugloop/gemini.env` before `chia up`, expanded into the `bugloop_llm` containers' environment by CHIA's config loader, and read there by `build_llm`. **Never** forwarded through `--runtime-env-json`, never written to any artefact, and covered by NFR-06's grep pattern (§11.2). |
| `BUGLOOP_ALLOW_LIVE_MODEL` | `cluster_single.yaml`, `generate_task.build_llm`, `bug_loop.py` pre-flight check 12 | **The live-call interlock.** `build_llm` refuses to construct a real backend unless this is exactly `1` (§3.5.1). Unset in tiers T0 to T2 of `04-Test-Plan.md`, which mock the model layer; set in the operator's shell for the pilot onward (`05-Work-Plan.md` W-18). Not a secret, and still not forwarded through job metadata, because a job that could set it could switch the loop live. |
| `CHIA_HEAD` | `cluster_single.yaml` | The head's hostname, as CHIA's own example uses it. |
| `BUGLOOP_ARTEFACTS` | both cluster YAMLs, `bug_loop_submit.sh`, `bug_loop.py` | The artefact root, bind-mounted at the identical path in every container (FR-17.9). Forwarded into the job through `--runtime-env-json` env_vars, because a submitted job inherits no environment. |
| `BUGLOOP_IMAGE_TAG` | both cluster YAMLs, `bug_loop_submit.sh`, `bug_loop.py` | The assertions-on image tag B1 published. Forwarded the same way. |
| `GOOGLE_CLOUD_PROJECT` | `bug_loop_submit.sh`, `repair_adapter.py` | The Vertex project CHIA's `opencode` backend needs (`chia:examples/circt_issue_solver/circt_issue_loop.py:71-72`), which is reachable only through `--repair-backend opencode` (§3.8). Forwarded only when set. Not a secret: it is a project id. **It is not read by `generate_task.py` any more**: the loop's own stages run in express mode, which takes an API key and **no** project, and `build_llm` nulls `llm.project` for exactly that reason (§3.5.1). A `GOOGLE_CLOUD_PROJECT` set in an `llm` container is therefore harmless rather than load-bearing. |
| `BUGLOOP_GCP_PROJECT` | `cluster_gcp.yaml` only | The GCP project the cluster is brought up in, site-specific, deferred with GCP. |
| `BUGLOOP_GCP_HEAD_IP` | `cluster_gcp.yaml` only | The head's address, so the file parses; deferred with GCP (§12.2). |

`GITHUB_TOKEN` is deliberately **not** in that table. CHIA's client reads it from the environment when
no constructor argument is given (`chia:chia/github/github_client.py:85`), and the loop always gives
the argument, so the variable is never consulted and never set.
---

## 14. Traceability

### 14.1 Every HLD component to its module and callable

Twenty-six components, twenty-six rows, in `02-HLD.md` §1's order. No component is without a
module and no module is without a component.

| Id | Component | Module | Callable | Section |
|---|---|---|---|---|
| A1 | `seed_corpus_build` | `corpus.py` | `build_corpus`, `normalise_run_line`, `strip_probe_only_options`, `resolve_sites` | §3.3 |
| A2 | `pinned_main_select` | `pin_select.py` | `select_release_pinned_main` | §3.4 |
| A3 | `generate_seeded` | `generate_task.py` | `generate_seeded` | §3.5 |
| A4 | `generate_mutation` | `generate_task.py` | `generate_mutation` | §3.5 |
| A5 | `feedback_bundle_build` | `feedback.py` | `build_feedback` | §3.11 |
| A6a | `budget_load` | `budget.py` | `load_budget`, `snapshot` | §3.11, §9.2 |
| A6b | `ledger_accrue` | `ledger.py` | `accrue`, `aggregate`, `stop_reason` | §3.11 |
| A7 | `mutator_synthesis` | `mutator_synth.py` | `synthesise_mutators` | §8.3 |
| B1 | `image_build` | `bug_loop.py` plus `dockerfiles/ChiaCirctAssertDockerfile` | `build_image` | §4.11, §4.11.1 |
| B2 | `probe_execute` | `probe_task.py` | `probe_execute`, `classify_build` | §3.6 |
| B3 | `oracle_primary` | `probe_task.py` | `oracle_primary`, `strip_prologue` | §3.6.2, §3.7.1 |
| B4 | `oracle_differential` | `probe_task.py` | `oracle_differential`, `extract_port_list`, `gen_arc_harness`, `gen_verilator_tb` | §3.6.3 |
| B5 | `reduce_case` | `probe_task.py`, `ddmin.py` | `reduce_case`, `ddmin` | §3.6.4, §10.3 |
| B6a | `issue_mirror_refresh` | `triage_task.py` | `issue_mirror_refresh` | §3.7 |
| B6b | `dedup_and_contamination_screen` | `triage_task.py` | `dedup_and_screen` | §3.7.1, §3.7.2, §3.7.3 |
| B7 | `triage_report` | `triage_task.py` | `triage_report`, `render_report` | §3.7.4, §7.4 |
| B8 | `repair_adapt` | `repair_adapter.py` | `repair_adapt` | §3.8 |
| B9a | `gate_decide` | `gate.py` | `gate_decide` | §3.9 |
| B9b | `gate_rerun` | `gate.py` | `gate_rerun` | §3.9 |
| B9c | `bugloop-approve` | `approve.py` | `main` | §13.2 |
| B10a | `LoopStore` | `store.py` | `LoopStore`, `init_schema`, `validate_candidate`, `load_candidate` | §2.9, §6.1, §6.2 |
| B10b | `artefact_write` | `store.py` | `artefact_write` | §6.5 |
| B11 | `results_render` | `results.py` | `render_results` and the fourteen `_require_*` checks | §3.11, §14.4 |
| B12 | `campaign_drive` | `bug_loop.py` | `main` | §13.1 |
| tool | `ProbeWriteTool` | `generate_task.py` | `ProbeWriteTool.write_probe` | §3.5 |
| tool | `SourceReadTool` | `generate_task.py` | `SourceReadTool.read_file`, `.grep`, `.list_dir` | §3.5 |

Twenty-six rows now, because `SourceReadTool` is the second agent-facing tool this design adds and
`02-HLD.md` §1.4 carries the same change: the `BashTool` is withdrawn from stages 1, 2 and 6, and the
read-only source row it occupied is now `SourceReadTool`'s (W10). `corpus.resolve_sites` is a fourth
callable of A1 rather than a component of its own, because it is the same module reading the same
clone with the same two commands.

The seam itself, which `02-HLD.md` §2 treats as its own section rather than a component, is
`contract/schema.py` (§2). The three functions proposed for `chia/chipyard/circt.py` belong to no
component and serve B2, B3 and B5 (§3.10).

### 14.2 Every functional requirement to the module and function that implements it

| FR | Module and callable | Where in this document |
|---|---|---|
| FR-01.1 | `corpus.build_corpus` | §3.3 |
| FR-01.2 | `corpus.normalise_run_line` step 0, and `SeedRecord.run_lines` | §3.3, §2.4 |
| FR-01.3 | `corpus.normalise_run_line`, first token after step 6 | §3.3 |
| FR-01.4 | `corpus.build_corpus`, `SeedRecord.dialect_bucket` and `dialect_bucket_unmerged` | §2.4 |
| FR-01.5 | `corpus.build_corpus`, `SdkMap` | §2.9 |
| FR-01.6 | `contract.to_json`'s canonical form, plus `build_corpus`'s recorded `inputs` | §2.3, §3.3 |
| FR-01.7 | `SeedRecord.sdk_exact`, `bumps_away` | §2.4 |
| FR-01.8 | `build_corpus`, `CorpusError("no_tags")`, argument-vector refspec | §3.3 |
| FR-01.9 | `build_corpus`, `seed.eligible_seeded` and `exclusion_reason` | §3.3, §6.2 |
| FR-01.10 | `corpus.normalise_run_line`, the six-step table | §3.3 |
| FR-01.11 | `build_corpus`, `CorpusError("head_moved")`; pre-flight check 3 | §3.3, §13.1 |
| FR-01.12 | `SeedRecord.test_paths`, ordered and never collapsed | §2.4 |
| FR-02.1 | `pin_select.select_release_pinned_main` | §3.4 |
| FR-02.2 | the same, `lag_commits` and `lag_days` | §3.4, §4.12 |
| FR-02.3 | the same, 40-character SHA equality only | §3.4 |
| FR-02.4 | the same, `current_window_has_release` | §3.4, §2.4 |
| FR-02.5 | `PinSelectError("no_match")` | §3.4 |
| FR-02.6 | the same, `tags_sharing_pin` | §3.4 |
| FR-02.7 | `RunManifest.run_commit`, `RunCommit`, and `_manifest_conditionals` | §2.4, §2.8 |
| FR-03.1 | `ChiaCirctAssertDockerfile`'s fetch-by-SHA | §4.11 |
| FR-03.2 | the pin equality check before `ninja` | §4.11 |
| FR-03.3 | CHIA's strip, retained unchanged | §4.11 |
| FR-03.4 | the configure line's `CMAKE_CXX_FLAGS_RELEASE` | §4.11 |
| FR-03.5 | `ImageSpec.assertion_nonreferencing`, compared as a set | §2.9, §6.5 |
| FR-03.6 | the two lit runs and their set equality | §4.11 |
| FR-03.7 | `ImageSpec.targets`, a parameter | §2.9, §4.11 |
| FR-03.8 | the apt line and the baked `lit` path | §4.11, §5.1 |
| FR-03.9 | `openssh-client` and `rsync` in the apt line | §4.11 |
| FR-03.10 | `ImageSpec`, recorded in `RunManifest.image_spec` | §2.7, §2.9 |
| FR-03.11 | `render_report`'s `build_identity` point | §7.4.1 |
| FR-03.12 | nothing enables MLIR or LLVM assertions; the SDK is used as shipped | §4.11 |
| FR-03.13 | `build_image` step 8 pushes nothing when any earlier step failed, and removes the local tag | §4.11.1 |
| FR-03.14 | the two slang options; `ImageSpec.slang_enabled`; `RunManifest.sv_seeds_excluded` | §4.11, §5.3 |
| FR-03.15 | `ImageSpec.verilator_version`; pre-flight check 8; every `DifferentialVerdict` | §2.9, §13.1 |
| FR-03.16 | `ImageSpec.tool_hashes`, hashed from the published image by `build_image` step 6 | §2.9, §4.11.1, §5.2 |
| FR-03.17 | `-DMLIR_SOURCE_DIR=/opt/circt-sdk`; `build_image` step 4 sets `lit_discovery_ok` and blocks publication; pre-flight check 6 | §4.11, §4.11.1, §13.1 |
| FR-04.1 | `prompts/seed_read.md` Part A and Part B; the site resolver | §7.2 |
| FR-04.2 | the argv is built from the seed's `argv_template`, not from the agent; `emit_specs`' `E010_TOOL_MISMATCH` check | §3.5, §7.3 |
| FR-04.3 | `ProbeSpec`, every field required, `input_text` or `input_path` (erratum) | §2.4, §2.8 |
| FR-04.4 | the tool list `[source_read, probe_write]`, asserted literally; `SourceReadTool` read-only by construction | §3.5 |
| FR-04.5 | `emit_specs`'s cap and truncation count | §3.5, §7.3 |
| FR-04.6 | the five per-turn files under the iteration directory | §6.5 |
| FR-04.7 | `SeedRecord.sdk_exact` read by the mode selector, never by the image builder | §2.4 |
| FR-04.8 | `generate_seeded`'s `failure` field; §7.1's stage-1 and stage-2 rule | §3.5, §7.1 |
| FR-04.9 | stage 2 does not validate syntax; `classify_build` records `parse_error` | §3.6 |
| FR-05.1 | `mutate_seed` rule 1, every changed test file | §8.2 |
| FR-05.2 | the frozen-set rule's three enforcement points; `synthesise_mutators` steps 1 and 5, the registration refusal and the write-once freeze | §8.1, §8.3 |
| FR-05.3 | `mutate_seed` rule 5, the derived seed integer | §8.2 |
| FR-05.4 | one `generate` signature, one validator, one code path | §2.5 |
| FR-05.5 | `mutators[].mutates_argv` and the argv assertion | §8.1, §8.2 |
| FR-05.6 | `mutate_seed` rule 6, no-ops counted and unbudgeted | §8.2 |
| FR-05.7 | `mutate_seed` rule 6, failures attributed to an id | §8.2 |
| FR-05.8 | `synthesis_input` and `synthesis_model` in the frozen set, filled from the run by `synthesise_mutators` step 5; `results.py`'s disclosure | §8.1, §8.3, §14.4 |
| FR-06.1 | `circt_exec_probe`'s argument-vector `execve`; the hash check | §3.10, §5.2 |
| FR-06.2 | the `prlimit --as --cpu=<soft>:<hard> --nofile --` prefix; `circt_exec_probe`'s `limit_hit` rule | §4.1, §3.10 |
| FR-06.3 | `start_new_session=True` plus `os.killpg(..., SIGKILL)` | §3.10 |
| FR-06.4 | `BuildResult.exit_status`, `signal`, `truncated`; the timeout's null signal | §2.9, §3.6 |
| FR-06.5 | `BuildResult.run_commit` and `image_digest` | §2.9 |
| FR-06.6 | `classify_build`'s `parse_error` row | §3.6 |
| FR-06.7 | `classify_build`'s `oom` row, death by signal required, and the three verbatim patterns | §3.6 |
| FR-06.8 | the per-probe scratch directory; `ProbeWriteTool`'s path check | §3.5, §6.5 |
| FR-06.9 | `BuildStatus`, a closed `Literal` of seven | §2.1 |
| FR-07.1 | the three patterns of §3.6.1 | §3.6.1 |
| FR-07.2 | `classify_build`'s test order, `oom` first | §3.6 |
| FR-07.3 | `_ASSERT_GLIBC`'s `expr` and `file`/`line` groups; `_ASSERT_UNREACHABLE`'s preceding-line rule | §3.6.1, §3.6.2 |
| FR-07.4 | `circt_symbolize(frames)` by module and offset; `frames_resolved`, `frames_with_location`, `Frame.in_circt_object` | §3.6.2, §3.10 |
| FR-07.5 | `out_of_scope_root`, the first frame after the prologue strip not in a CIRCT object | §3.6.2, §3.7.1 |
| FR-07.6 | `OracleVerdict.repro_command`, `shlex.join`, no `prlimit` prefix | §3.6.2 |
| FR-07.7 | `flag_string` and `tool_version_output` | §2.9 |
| FR-07.8 | `fired` is false for `timeout` and `oom` | §3.6.2 |
| FR-07.9 | the control run over the lit corpus; `ImageSpec.lit_discovery_ok` is its precondition | §4.11 |
| FR-07.10 | `render_report`'s `observed_behaviour`; the prompt's fatal-error clause | §7.4, §7.4.1 |
| FR-08.1 | `oracle_differential`'s applicability rule, decided before either simulator runs | §3.6.3 |
| FR-08.2 | `extract_port_list`, `gen_arc_harness` and `gen_verilator_tb`, with the port-list rule, the acceptance shape and the `[UNVERIFIED]` marker; `harness.mlir`, `dut.sv`, `tb.sv` | §3.6.3, §4.6, §4.10, §6.5 |
| FR-08.3 | `ProbeSpec.differential`'s five keys; the one derived stimulus both generators build from one `stimulus_seed` and one port list | §2.7, §3.6.3 |
| FR-08.4 | `--x-initial unique --x-assign unique`; `RunManifest.x_policy`; the harness initialises no state the design does not | §3.6.3, §4.10 |
| FR-08.5 | `DifferentialVerdict.verdict == "diverge"`; the class never enters repair | §3.8 |
| FR-08.6 | the `differential` report template, with no expected field | §7.4.1 |
| FR-08.7 | the same template names `circt/arc-tests` | §7.4.1 |
| FR-08.8 | `harness_failure` with the failing arm named; every `HarnessError` reason lands there and never in `diverge` | §3.6.3 |
| FR-08.9 | `diverge_x_policy`, excluded from the candidate count | §2.9 |
| FR-08.10 | `CandidateRecord`'s differential conditionals; `results.py`'s divergences list | §2.9, §14.4 |
| FR-08.11 | `DifferentialVerdict.driver_source`; `RunManifest.differential_driver` | §2.7, §2.9 |
| FR-09.1 | the interestingness template's class-specific block | §10.2 |
| FR-09.2 | `--test=` always, `--test-must-fail` never; exit 0 is interesting | §4.7, §10.2 |
| FR-09.3 | `ReducedCase.recheck_*` | §2.9 |
| FR-09.4 | `reduction_wall_seconds`; `--keep-best`, which is on by default | §4.7, §9.5 |
| FR-09.5 | the four size fields | §2.9 |
| ~~FR-09.6~~ | withdrawn in `01-FRD.md`; replaced by FR-09.12 | - |
| FR-09.7 | `recheck_matches` false yields `reduction_changed_failure` | §2.9 |
| FR-09.8 | `reduce_case` is not dispatched for a `differential` candidate | §2.9 |
| FR-09.9 | the reducer-selection table, five rows, with `circt-verilog --format=mlir` for the `circt-verilog` branch | §4.4, §4.7 |
| FR-09.10 | `ddmin.ddmin` | §10.3 |
| FR-09.11 | `ReducedCase.reducer` and `fixpoint` | §2.9 |
| FR-09.12 | `ReducedCase.reduced` false with `reason`; gate question 2 | §2.9, §3.9 |
| FR-09.13 | the `timeout --signal=TERM --kill-after=` wrapper; the post-exit validation | §10.2 |
| FR-10.1 | `Fingerprint`, one value and three evidence fields; the prologue strip and the signal-plus-frame rule | §3.7.1 |
| FR-10.2 | string equality only; `itertools.groupby` over the sorted fingerprints | §3.7.1 |
| FR-10.3 | the token set, the `instr` match and the state rule | §3.7.3 |
| FR-10.4 | the file-level post-pin scan, bounded by `candidate.run_commit` | §3.7.2 |
| FR-10.5 | `DedupVerdict.evidence`, `_DEDUP_EVIDENCE_KEYS` and `_DEDUP_EVIDENCE_REQUIRED`, enforced by `validate_candidate`'s `E011` and `E013` | §2.9 |
| FR-10.6 | `ix_fingerprint_value`, a cross-run point query | §6.3 |
| FR-10.7 | `dedup_unavailable`, which fails gate question 4 | §3.7, §3.9 |
| FR-10.8 | `dedup_basis="insufficient"`, `value` null | §3.7.1 |
| FR-10.9 | `issue_mirror_refresh`; `issue_mirror_meta`'s six columns; `--refresh-mirror` | §3.7, §6.2, §13.1 |
| FR-11.1 | the stage-6 prompt Part A; `TRIAGE_REASON_MAX_SENTENCES` | §7.4, §9.4 |
| FR-11.2 | the tool-verdict override in `triage_report` | §3.7.4 |
| FR-11.3 | `render_report`'s two substitution tables, and its refusal to render without a point of the template it was given | §7.4.1 |
| FR-11.4 | every number substituted from the record; the prompt says so too | §3.7.4, §7.4 |
| FR-11.5 | `prompts/report_write.md`, with no `Fixes #<number>` line | §7.4 |
| FR-11.6 | the `assisted_by` substitution point, the file's last line | §7.4.1 |
| FR-11.7 | the five per-turn files, as FR-04.6 | §6.5 |
| FR-11.8 | `untriaged` plus `held_reason=no_report` | §7.1, §3.7.4 |
| FR-11.9 | the template-selection rule on candidate class | §7.4.1 |
| FR-12.1 | `run_issue_remote` called with one additive backend branch and nothing else changed; the `git diff` **hunk-equality** comparison against `16c35e92`, and `upstream/issue_task-vertex-branch.patch` applying cleanly to it (~~the byte comparison~~, withdrawn 2026-09-14) | §1.2, §1.4, §3.8 |
| FR-12.2 | `LOCAL_ID_BASE`, `_as_github_issue` | §3.8, §9.4 |
| FR-12.3 | the pre-written `repro.sh` under the artefact root, its polarity, and `repro_overwritten` | §3.8 |
| FR-12.4 | the class refusals before the chain | §3.8 |
| FR-12.5 | the `out_of_scope_root` refusal | §3.8 |
| FR-12.6 | `cfg["tag"] = candidate.run_commit`; `circt_git_reset(candidate.run_commit)` | §3.8 |
| FR-12.7 | `RepairResult.status`, CHIA's own six | §2.9 |
| FR-12.8 | `RepairResult.lit_ok` and `lit_unusable` | §2.9, §6.2 |
| FR-12.9 | all six prompts byte-identical, checked | §1.2 |
| FR-12.10 | the write order; `repair.chia_row_seen`; B12's reconciliation | §6.4, §13.1 |
| FR-12.11 | `resources={"repair": 1}`; the post-attempt reset, rebuild and re-hash (`restore_hashes_match`) | §3.2, §3.8 |
| FR-13.1 | `gate_decide`'s four questions, stopping at the first no | §3.9 |
| FR-13.2 | `BuildResult.worker_hostname`, `worker_node_id`, `child_pid`; `gate_rerun` with a soft `NodeAffinitySchedulingStrategy`; `q1_same_worker` | §2.9, §3.9, §6.2 |
| FR-13.3 | question 2's four outcomes | §3.9 |
| FR-13.4 | no gate question reads `triage_class`, asserted | §3.9 |
| FR-13.5 | question 4 reads the dedup verdict only | §3.9 |
| FR-13.6 | `report_plus_patch` on `fixed` and `lit_ok` | §3.9 |
| FR-13.7 | `FilingRecord.approver` and `approved_at_utc` | §2.9, §13.2 |
| FR-13.8 | the per-UTC-day cap, checked before the human is asked | §13.2 |
| FR-13.9 | the `good first issue` refusal from `dedup_evidence.issue_labels`, which §3.7.3 populates | §3.7.3, §13.2 |
| FR-13.10 | `GateDecision.decision` defaults to `nothing` | §3.9 |
| FR-13.11 | every refused candidate is persisted with its failing question | §6.2 |
| FR-13.12 | `bugloop-approve show`'s one view | §13.2 |
| FR-13.13 | a second approval refused with the first's timestamp | §13.2 |
| FR-13.14 | `differential` candidates never reach `gate_decide` | §2.9 |
| FR-13.15 | the three parse-and-verify commands, plus `q3_after_parse` for the second conjunct | §4.8, §3.9 |
| FR-13.16 | B9a's poll on the fingerprint; `FilingRecord.url_source` | §3.9, §7.4.1 |
| FR-13.17 | `PREFILL_URL_CHAR_LIMIT`, 6,000 | §9.4, §13.2 |
| FR-13.18 | `bugloop-approve url`, against the same report id | §13.2 |
| FR-14.1 | `budget.yaml`'s schema, every key, the four of 2026-09-14 included | §9.1, §9.2 check 6 |
| FR-14.2 | `load_budget`'s first check; pre-flight check 1 | §9.2, §13.1 |
| FR-14.3 | `RunManifest.budget_file_sha` | §2.4 |
| FR-14.4 | `LedgerEntry.arm`'s three values and `scope`'s two | §2.4 |
| FR-14.5 | one `arm_window_seconds`; the manifest's four identifying fields | §9.2, §2.4 |
| FR-14.6 | `llm_turn` brings the backend's `usage_metadata` counts home; `ledger.price` turns them into `cost_usd`; `LedgerEntry.observed` carries both | §2.7, §3.5.1, §3.11 |
| FR-14.7 | every stage compares the budget SHA against the manifest's | §9.2 |
| FR-14.8 | `RunManifest.stages_metered`, `stage_7` false whenever the repair backend differs from `RunManifest.backend` | §2.7, §3.8 |
| FR-15.1 | the symbol-level contamination scan, both flags recorded | §3.7.2 |
| FR-15.2 | `contaminated_symbol` on the candidate; the results column | §2.9, §14.4 |
| FR-15.3 | `results.py`'s mandatory disclosure sentence | §14.4 |
| FR-15.4 | `results.py`'s second mandatory disclosure sentence | §14.4 |
| FR-15.5 | `contamination_lower_bound` | §3.7.2 |
| FR-16.1 | `feedback.build_feedback`, one entry per dispatched probe id | §3.11 |
| FR-16.2 | A4 takes the bundle and does not read it, asserted on its body (erratum) | §2.5, §3.5 |
| FR-16.3 | `per_seed_iteration_cap`; `terminating_condition` | §9.1, §2.4 |
| FR-16.4 | `ProbeResult` and `FeedbackEntry` carry no result field; `_FEEDBACK_DENY` | §2.4, §3.11 |
| FR-16.5 | `feedback.json` per iteration; every stage-1 variable comes from the `SeedRecord` | §6.5, §7.2 |
| FR-16.6 | `build_feedback`'s abandonment rule, the `(build_status, stopping_reason)` multiset | §3.11 |
| FR-17.1 | the artefact tree's per-iteration and per-probe directories | §6.5 |
| FR-17.2 | `probe_result` and `candidate`, each with `artefact_dir` | §6.2 |
| FR-17.3 | `SQLiteNode(path, pin_to_current_node=True)`, absolute local path | §6.1 |
| FR-17.4 | `CounterBlock`'s four counters, returned by every node under the key `counters` and logged on the head by B12 | §2.5, §3.11, §13.1 |
| FR-17.5 | nothing writes the token anywhere | §11.1 |
| FR-17.6 | `run_manifest_id` on every table and every directory | §6.2, §6.5 |
| FR-17.7 | `contract.bound_text`, the companion path fields, and the 262,144-byte cap | §2.8, §6.5, §9.5 |
| FR-17.8 | the `PARTIAL` marker, written first and removed last | §6.5 |
| FR-17.9 | the bind mount at the identical path, `--user` on every worker type; pre-flight check 5; the wrapper's env forward | §12.1, §13.1, §13.3 |
| FR-18.1 | `arm` carried everywhere, branched on only in `ledger.py` and `results.py` | §14.5 |
| FR-18.2 | `RunManifest.mode` and `seed_set`; the render refusal | §2.4, §14.4 |
| FR-18.3 | the headline counted per fingerprint, from `filing` rows carrying a URL | §14.4 |
| FR-18.4 | the five secondaries per arm | §14.4 |
| FR-18.5 | the separate seeded-bug validation table | §14.4 |
| FR-18.6 | `taxonomy_bucket`, a closed six; `taxonomy.json` | §2.9, §6.5 |
| FR-18.7 | the render succeeds from an empty confirmation set | §14.4 |
| FR-18.8 | `RunManifest.confirmation_cutoff_date` | §2.4 |
| FR-18.9 | no comparison sentence; the render has no such field | §14.4 |
| FR-18.10 | `ledger.stop_reason`, now three conditions, the window, a safety cap and `campaign_spend_cap`; both windows and the spend printed | §3.11, §9.1, §14.4 |
| FR-18.11 | the regeneration check marks a row rather than reporting it | §14.4 |
| FR-18.12 | `divergences.md` | §6.5, §14.4 |
| FR-19.1 | every stage a `@ChiaFunction`; both added tools are plain `ChiaTool`s, neither in FR-19.1's five `AsyncJobTool` categories | §3.0, §3.5 |
| FR-19.2 | the three functions in `chia/chipyard/circt.py` | §3.10 |
| FR-19.3 | `bug_loop.py --arm`, one flag | §13.1 |
| FR-19.4 | the three-paragraph docstring rule and its check | §3.1 |
| FR-19.5 | `tests/` mirroring the modules, plus `chia/chipyard/test/` | §1.2, §1.3 |
| FR-19.6 | the pull request's commit trailers | §14.6 |
| FR-19.7 | the released archive's six contents | §14.6 |
| FR-19.8 | the dependency list, unchanged; util-linux priced | §0, §4.9 |
| FR-19.9 | no governance file is touched | §14.6 |
| FR-20.1 | `RunManifest.forum_post_url` and `forum_post_date`; pre-flight check 11 | §13.1 |
| FR-20.2 | FR-13.9's refusal plus the released statement | §13.2, §14.4 |
| FR-20.3 | the `assisted_by` trailer on every filed text | §7.4.1 |
| FR-20.4 | no comments are mirrored; `dedup_evidence` carries no issue text | §3.7, §6.2 |
| FR-20.5 | `FilingRecord.licence_confirmed` and its timestamp | §2.9, §13.2 |
| FR-20.6 | no filing exists without a `filing` row, and only `approve` writes one | §13.2 |

### 14.3 Every non-functional requirement

| NFR | Where it is discharged |
|---|---|
| NFR-01 | Every tool stage re-executes from its stored inputs; agent turns replay through CHIA's bypass from the stored transcript. The stored inputs are the artefact tree of §6.5 and the argv of `argv.json`, which is why the full argv is persisted and not just the tool name. |
| NFR-02 | `contract.to_json`'s canonical form (§2.3); the hash check that guarantees the same binaries (§5.2); `budget_truncated` and `fixpoint`, which make a non-reproducible reduction visible (§2.9). `wall_seconds` and `peak_rss_bytes` are declared non-deterministic in `BuildResult` itself. |
| NFR-03 | The agent acts at stages 1, 2 and 6 only; the stage-1 and stage-2 tool list is `[source_read, probe_write]` and stage 6's is `[source_read]`, neither containing a shell (§3.5); `render_report` substitutes every number from the record (§7.4.1); no gate question reads the triage class (§3.9). |
| NFR-04 | The only GitHub calls are `GithubIssuesNode.recent` and the reconciliation poll, both GET through CHIA's GET-only client. There is no write path of any kind and `approve.py` opens a URL for a human rather than calling an API (§13.2). |
| NFR-05 | Two separated levels: the container's `--cpus` and `--memory` in the cluster YAML (§12.1), and the probe's own `prlimit` (§4.1). Only the second produces an `oom` record. |
| NFR-06 | §11 in full, plus the `PARTIAL`-free artefact tree of §6.5 and the tokenless submit wrapper of §13.3. |
| NFR-07 | One credential, read scope, one 0600 file on the head, read by two head nodes (§11.1). |
| NFR-08 | `ledger.stop_reason` stops an arm at its window or at a binding safety cap (§3.11); the post-run reconciliation is B12's (§13.1). |
| NFR-09 | Every node returns a counter dict the driver logs on the head; `bug_loop_submit.sh` makes `chia job logs <id>` work at all (§13.3). |
| NFR-10 | `cluster_single.yaml` in full, `cluster_gcp.yaml` as a deferred skeleton, `RunManifest.deployment` recording which ran (§12). |
| NFR-11 | No added Python dependency; util-linux invoked as a process and not linked (§0, §4.9); the licence confirmation recorded at approval time (§13.2). |
| NFR-12 | The three-paragraph docstring rule (§3.1), the README in CHIA's shape (§1.1), and the workflow beside the Dockerfile (§1.2). |

### 14.4 What `results.py` must render, and what it refuses without

`02-HLD.md` §1.3 enumerates B11's output because FR-18 and three ADRs each add to it. Each element is
a named private check in `results.py`, and a missing one is a render failure rather than an omission.

| Element | Refusal name | Requirement |
|---|---|---|
| the headline, distinct confirmed bugs per arm, from `filing` rows carrying a URL | `_require_headline` | FR-18.3 |
| the five secondaries per arm | `_require_secondaries` | FR-18.4 |
| the separate seeded-bug validation table | `_require_validation_table` | FR-18.5 |
| the mode and the seed set on **every** table | `_require_qualifiers` | FR-18.2, ADR-D-07 |
| the contamination column, and the headline both with and without contaminated candidates | `_require_contamination` | FR-15.2 |
| the two disclosure sentences, incompleteness and the unscreened repair stage | `_require_disclosures` | FR-15.3, FR-15.4 |
| the lag the campaign ran under, beside the headline | `_require_lag` | ADR-D-10 |
| the confirmation cut-off date | `_require_cutoff` | FR-18.8 |
| the collision and false-merge rates, beside the headline they qualify | `_require_dedup_rates` | FR-10.2 |
| the divergences-observed list | `_require_divergences` | FR-18.12 |
| the mutator-synthesis declaration, naming its input, date and frozen-set SHA | `_require_mutator_declaration` | FR-05.8 |
| tokens, cost and CPU time under a heading saying they are not the budget, and, added 2026-09-14, the sentence that the USD total is a **lower bound excluding stage 7**, whose per-turn tokens CHIA's chain does not return (§3.8, FR-14.6) | `_require_observed_heading` | FR-14.5, FR-14.6 |
| both arm windows, with the binding cap and the unspent balance where one bit | `_require_both_windows` | FR-18.10 |
| every row that could not be regenerated, marked rather than reported | `_require_regeneration_marks` | FR-18.11 |

**Fourteen**, which is the number §3.11's `_REFUSALS` tuple now names in order; the earlier "nine" in
§3.11 was a miscount of this very table (W5). The names are listed once, in §3.11; this table adds the
element each one demands and the requirement it discharges, and adds no fifteenth name. Three of the fourteen gained a column in this revision and none gained a check: the
taxonomy table splits `parse_error` by `tool_rejected_input` and `tool_rejected_argv` (§3.6, NIT 2);
`_require_dedup_rates` prints the count of candidates whose `fingerprint_stable` is false beside the
rates it already prints, because an unstable fingerprint qualifies the headline exactly as a collision
does (§3.7.1); and `_require_secondaries` prints the count of repair attempts whose
`repro_overwritten` is true, because FR-12.3's "confirms rather than invents" is reported per attempt
(§3.8).

Two further properties are asserted rather than rendered: the render succeeds from an empty
confirmation set and states the zero (FR-18.7), and the rendered text contains no sentence comparing
the loop's count to FLEX, ISSTA-2024, Nuwa or DESIL (FR-18.9), checked by a name search over the
output.

### 14.5 Where `arm` may be branched on, and the check that keeps it there

FR-18.1 permits the apparatus to **carry** `arm` and forbids it to **branch** on it, except in the
budget ledger and the results table. The check is a search of the apparatus modules for any `if`,
`match`, dictionary dispatch or comparison whose operand is `arm`:

```
tests/test_layout.py: parse probe_task.py, triage_task.py, repair_adapter.py,
gate.py, store.py and ddmin.py with ast, walk every Compare, If, Match and
Subscript node, and assert that no node's operand resolves to a name or an
attribute ending in "arm".
```

`ledger.py` and `results.py` are exempt by name, because those are the two places FR-18.1 permits.
`contract/schema.py` is exempt too, and the reason is now stated rather than left as a silent
omission (NIT 7): `_probe_spec_conditionals` opens with `mutation = o.arm == "mutation"` and must,
because FR-16.2 and FR-05.4 make `mutator_id`, `mutator_seed_int` and `source_test_path` conditional
**on the arm** and the validator is the one place that rule can be enforced. FR-18.1 confines
branching in the **apparatus**, and the seam is neither half; the walk's exempt list is
`ledger.py`, `results.py` and `contract/schema.py`, three names, each with its reason in this
paragraph.
The literal name search the requirement carried before its erratum is not used: `arm` is a required
field of `ProbeSpec` and of `ProbeResult` and a column of two `loop.db` tables, so a name search finds
it throughout any faithful implementation.

### 14.6 The upstream packaging

| Item | Where |
|---|---|
| the two trees, the team repository's `circt_bug_loop/` and `upstream/`, and the `sync-to-chia.sh` that turns them into a CHIA checkout | §1.4 |
| the CHIA-shaped example directory, as that script produces it | §1.1, §1.4 |
| the three generic functions proposed for `chia/chipyard/circt.py`, separated in the pull request's file list | §1.2, §3.10 |
| the new Dockerfile and its workflow | §1.2 |
| tests under `chia/chipyard/test/` for the core additions, distinct from the example's own | §1.2, §1.3 |
| `Assisted-by:` and `Signed-off-by:` on every commit (`chia:AGENTS.md:62-74`), the `Assisted-by:` value being `RunManifest.model_ids`'s own `"<backend>:<model id>"` spelling (§2.7) | the pull request |
| the two proposed `vertex` fixes: express mode's `location` default, **offered and not depended on**, worked around in two lines in §3.5.1; and the missing `vertex` branch in `run_issue_remote`, **offered upstream and applied locally** as `upstream/issue_task-vertex-branch.patch`, nineteen additive lines (2026-09-14, §3.8) | `upstream/`, `02-HLD.md` §8.3, §0.3 |
| **no credential in either tree**, enforced by the team repository's pre-commit scan `git grep -E 'AQ\.[A-Za-z0-9_-]{30,}\|AIza[0-9A-Za-z_-]{30,}'` returning nothing | §11.2 |
| no governance file touched (`chia:AGENTS.md:82`) | the pull request |
| the released archive: the seed corpus with its commit-to-release map, every generated input, every oracle verdict, every reduced case, every repair transcript and every gate decision | the artefact tree of §6.5, which holds all six by construction |

### 14.7 Module index: which requirements each module carries

§14.2 is indexed by requirement, because that is the direction a reviewer checks. This is the same
mapping indexed by module, because that is the direction a builder works in. A requirement appears
against every module that carries part of it, so the column sums to more than 198.

| Module | Component | Functional requirements it carries |
|---|---|---|
| `contract/schema.py` | the seam | FR-01.6, FR-02.7, FR-04.3, FR-05.4, FR-06.9, FR-14.3, FR-14.5, FR-14.8, FR-16.1, FR-16.4, FR-17.4, FR-17.6, FR-17.7 |
| `corpus.py` | A1 | FR-01.1, FR-01.2, FR-01.3, FR-01.4, FR-01.5, FR-01.6, FR-01.7, FR-01.8, FR-01.9, FR-01.10, FR-01.11, FR-01.12, FR-04.1, FR-05.1 |
| `pin_select.py` | A2 | FR-02.1, FR-02.2, FR-02.3, FR-02.4, FR-02.5, FR-02.6 |
| `generate_task.py` | A3, A4, `ProbeWriteTool`, `SourceReadTool`, **`build_llm` and `llm_turn`** | FR-04.1, FR-04.2, FR-04.3, FR-04.4, FR-04.5, FR-04.6, FR-04.7, FR-04.8, FR-04.9, FR-05.1, FR-05.4, FR-06.8, FR-14.6, FR-16.2 |
| `mutators/` | A4's frozen set | FR-05.1, FR-05.3, FR-05.5, FR-05.6, FR-05.7 |
| `mutator_synth.py` | A7 | FR-05.2, FR-05.8 |
| `probe_task.py` | B2, B3, B4, B5 | FR-04.9, FR-06.1, FR-06.2, FR-06.3, FR-06.4, FR-06.5, FR-06.6, FR-06.7, FR-06.8, FR-06.9, FR-07.1, FR-07.2, FR-07.3, FR-07.4, FR-07.5, FR-07.6, FR-07.7, FR-07.8, FR-07.10, FR-08.1, FR-08.2, FR-08.3, FR-08.4, FR-08.5, FR-08.8, FR-08.9, FR-08.11, FR-09.1, FR-09.2, FR-09.3, FR-09.4, FR-09.5, FR-09.7, FR-09.8, FR-09.9, FR-09.11, FR-09.12, FR-09.13 |
| `ddmin.py` | B5's textual reducer | FR-09.10 |
| `triage_task.py` | B6a, B6b, B7 | FR-03.11, FR-07.10, FR-10.1, FR-10.2, FR-10.3, FR-10.4, FR-10.5, FR-10.6, FR-10.7, FR-10.8, FR-10.9, FR-11.1, FR-11.2, FR-11.3, FR-11.4, FR-11.5, FR-11.6, FR-11.7, FR-11.8, FR-11.9, FR-08.6, FR-08.7, FR-15.1, FR-15.2, FR-15.5, FR-20.3, FR-20.4 |
| `repair_adapter.py` | B8 | FR-12.1, FR-12.2, FR-12.3, FR-12.4, FR-12.5, FR-12.6, FR-12.7, FR-12.8, FR-12.9, FR-12.10, FR-12.11 |
| `gate.py` | B9a, B9b | FR-13.1, FR-13.2, FR-13.3, FR-13.4, FR-13.5, FR-13.6, FR-13.10, FR-13.11, FR-13.14, FR-13.15, FR-13.16 |
| `approve.py` | B9c | FR-13.7, FR-13.8, FR-13.9, FR-13.12, FR-13.13, FR-13.17, FR-13.18, FR-20.2, FR-20.5, FR-20.6 |
| `budget.py` | A6a | FR-14.1, FR-14.2, FR-14.5, FR-14.6, FR-14.7 |
| `ledger.py` | A6b | FR-14.4, FR-14.6, FR-14.8, FR-18.1, FR-18.10 |
| `feedback.py` | A5 | FR-16.1, FR-16.3, FR-16.5, FR-16.6 |
| `store.py` | B10a, B10b | FR-08.10, FR-10.5, FR-10.8, FR-12.10, FR-13.14, FR-17.1, FR-17.2, FR-17.3, FR-17.5, FR-17.6, FR-17.7, FR-17.8 |
| `results.py` | B11 | FR-05.8, FR-08.10, FR-10.2, FR-15.2, FR-15.3, FR-15.4, FR-18.1, FR-18.2, FR-18.3, FR-18.4, FR-18.5, FR-18.6, FR-18.7, FR-18.8, FR-18.9, FR-18.10, FR-18.11, FR-18.12, FR-20.2 |
| `bug_loop.py` | B12, B1's driver | FR-02.7, FR-03.10, FR-03.13, FR-03.16, FR-03.17, FR-14.7, FR-17.4, FR-17.9, FR-18.2, FR-19.3, FR-20.1 |
| `dockerfiles/ChiaCirctAssertDockerfile` | B1 | FR-03.1, FR-03.2, FR-03.3, FR-03.4, FR-03.5, FR-03.6, FR-03.7, FR-03.8, FR-03.9, FR-03.10, FR-03.12, FR-03.14, FR-03.15, FR-03.16, FR-03.17, FR-07.9 |
| `chia/chipyard/circt.py` | the three core additions | FR-06.1, FR-06.2, FR-06.3, FR-07.4, FR-09.2, FR-09.4, FR-19.2 |
| `prompts/` | A3's two, B7's one, A7's one | FR-04.1, FR-05.8, FR-11.1, FR-11.5 |
| `cluster_single.yaml`, `cluster_gcp.yaml` | §12 | FR-03.9, FR-12.11, FR-17.9 |
| `bug_loop_submit.sh` | §13.3 | FR-20.6, and NFR-06 and NFR-09 |
| `budget.yaml` | F-14's artefact | FR-14.1 |
| `tests/`, `chia/chipyard/test/` | §1.3 | FR-19.5, and every FR's own acceptance criterion, which `04-Test-Plan.md` owns |

`FR-09.6` appears in no row because `01-FRD.md` withdrew it; FR-09.12 replaced it and carries its
work.

Four requirements are properties of the **design as a whole** rather than of one module, and each
names the check that holds it: FR-18.1's no-branching rule, checked by the `ast` walk of §14.5;
FR-19.1's node-and-tool rule, checked by a search for a bare Ray remote; FR-19.4's docstring rule,
checked over every public callable; and FR-19.8's dependency rule, checked against the list in §0.
FR-19.6, FR-19.7 and FR-19.9 are properties of the pull request and the release, and §14.6 is where
they live.

---

## 15. What this document leaves open

**Nine** things from 2026-09-14, each named so that no reader mistakes silence for a decision. Two
were raised by `design/reviews/red-team-LLD.md`, two by the backend fold-in, and two more, items 8
and 9, by the W-04 image build and the repair-backend decision later the same day; item 2 and item 3
are closed and kept struck through rather than deleted.

1. **The differential harness generators are now specified as code, and no generated harness has been
   compiled.** §3.6.3 gives `extract_port_list`, `gen_arc_harness` and `gen_verilator_tb` their
   signatures, their port-list extraction rule with the `circt-opt` command it runs, the one shared
   stimulus protocol, the X-policy asymmetry and the acceptance shape the differ compares, so FR-08.2
   has a specification a unit test can be written against for the first time. What none of that
   settles is A-08: whether a **generated** testbench compiles and runs against a **generated**
   design. §4.6 and §4.10 fix every flag and both were verified by running `--help`; the port-list
   extraction was verified by running `circt-opt --mlir-print-op-generic` over real HW IR; the
   harnesses themselves were not run, because none has been written and because A-19 has not yet said
   whether any seed is differential-applicable at all. F-08's first implementation task is A-19's
   count by §3.6.3's applicability rule and its second is FR-08.2's acceptance on the recorded 12-line
   FIRRTL register-add of FINAL Appendix A. Marked `[UNVERIFIED]` in §3.6.3 and §4.13.
2. ~~**The slang build is unattempted.**~~ **Closed 2026-09-14 (W-04).** ADR-D-13 resolves to branch
   (a) and branch (b) is not taken: the slang front end built from source, `circt-verilog --version`
   reports `CIRCT eade0de` and `slang version 11.0.385+44dc55f99`, `circt-translate --help` carries
   `--import-verilog`, and the 62 `REQUIRES: slang` lit tests run for the first time, 61 passing and
   one XFAIL, with zero failures. It cost the build one apt package it did not have, `clang-tools`
   for `clang-scan-deps` (§4.11 deviation 3), and the six targets came to 972 s and 703,211,208 B.
   **No seed exclusion is needed**, so `sv_seeds_excluded` is empty. What is still open from A-03 is
   narrower and is item 8 below.
3. ~~**The two Claude model ids are unaccepted.**~~ **Withdrawn as an open item, 2026-09-14.** The
   campaign backend is `vertex` and no Claude model id is a default anywhere in this document, so
   nothing waits on the two acceptance probes. They survive only as an operator concern on the
   `claude` fallback and on `--repair-backend claude`, where the id is whatever the operator passes
   (§11.2), and `05-Work-Plan.md`'s H-04 is optional in consequence.
4. **Whether a revert-and-rebuild reproduces the published binaries byte for byte is unmeasured.**
   FR-12.11's acceptance is a re-hash against `ImageSpec.tool_hashes`, and §3.8 now performs it and
   records `restore_hashes_match`; what nobody has run is the experiment that says whether it comes
   back true. `[UNVERIFIED]`, and the check is: on one worker, hash the six binaries, apply and revert
   a one-line diff, rebuild, re-hash. One incremental build. If it is routinely false, the recorded
   consequence is that the repair worker is single-use per run, which is a cost the campaign can pay;
   the failure mode the design refuses is a silent mismatch (W21).
5. **The reduction budget is now 600 s and the number of interestingness calls that buys is
   unmeasured.** `circt-reduce` made 56 calls to remove 27% of a six-operation module, and each call
   is bounded by `probe_wall_seconds`; at 60 s the reducer got one or two calls and every candidate
   failed gate question 2 as `not_minimal`, which is why §9.5 moved the key. `[UNVERIFIED]` is what
   600 s buys on a realistic seed input: the check is to time one `circt-opt` run on a recorded
   crashing input and divide. F-09's implementation task owns it, and `budget_truncated` is the field
   that makes the answer visible in the results either way (W13).

6. **The two Vertex prices are aggregator-sourced and unverified against Google.**
   `price_usd_per_m_input_tokens` 0.75 and `price_usd_per_m_output_tokens` 3.75 are introductory
   prices for `gemini-3.8-flash` through 2026-12-31, recorded on 2026-09-14 and marked
   `[UNVERIFIED]` in §9.1 and §9.5. What they move is `cost_usd` and the moment the USD cap binds,
   and nothing else: no measured quantity, no headline count, no gate answer. The check is to read
   Google's own Vertex pricing page and rewrite the two figures **before** the commit that lands
   `budget.yaml`, because that commit is the pre-registration. `05-Work-Plan.md` owns the date.
7. **No live model request has been made beyond three one-word probes.** Three calls of about 24
   tokens on 2026-09-14 established that Vertex express mode accepts the key and that both model ids
   answer; nothing since. Everything this document says about the turn, the tool loop and the usage
   counts is therefore established from CHIA's source, from `google-genai` 2.8.0's source, and from
   offline reconstructions of CHIA's own mocked tests, not from a campaign. The interlock of §3.5.1
   is what keeps it that way until `04-Test-Plan.md`'s tiers T0 to T2 are green and the code red team
   has passed, and the pilot is the first run that sets it (`05-Work-Plan.md` W-18).
8. **Added 2026-09-14. The `-gline-tables-only` delta and the per-probe slowdown are still unmeasured
   at image level.** W-04 measured the assertions-on image absolutely, 972 s and 703,211,208 B of
   binaries and 1,912,742,097 B of image, and it did **not** build the comparison image, so no delta
   attributable to the flag exists and neither does a slowdown: the two per-probe figures, 18.55 ms
   and 91.28 ms, are in-container absolutes against host numbers taken at a different commit on a
   different compiler. Both fall out of the one second image FR-03.6 already needs, which is
   `05-Work-Plan.md`'s **W-04b**, about 16 minutes and about 2.5 GB. `[UNVERIFIED]` until it runs.
9. **Added 2026-09-14. Stage 7's token counts are unobservable, and this is a design limitation
   rather than an open measurement.** §3.8 gives the mechanism in full: `_turn`'s remote dispatch at
   `chia:examples/circt_issue_solver/issue_task.py:124` serialises the LLM object, so
   `_last_metadata` never returns, and the only fix is a change to that line, which FR-12.1's
   hunk-equality acceptance forbids and which would move CHIA's turn off the `llm` worker for all four
   backends. What follows is recorded rather than estimated: stage 7's ledger tokens are null, its
   `cost_usd` is null, and the campaign's reported USD total is a **lower bound**, so
   `campaign_spend_cap_usd` bounds the observed stages only. The operator's own project-level budget
   alert and `--no-repair` are the two things that bound the rest, and both are named in §13.1.

~~Seven~~ **Nine** things, then, two of them added on 2026-09-14 and two closed the same day.
Everything else in this document is either cited to CHIA or CIRCT at a path and a line, verified by
running the tool, measured, or marked `[DEFAULT]` with its home named.
