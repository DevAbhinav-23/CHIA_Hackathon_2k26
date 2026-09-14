# Repair smoke, 2026-09-15: stage 7 runs, and stops at the assess turn

Pilot 8's fired candidate `c-p-4b1c72262db2` (the `assertion` at
`Casting.h:566`) down `bug_loop._drive_repair` itself, dedup verdict forced to
`new` by `analysis/measurements/repair_smoke.py`, cap 10.00, wall 2400 s,
cluster `cluster_single.yaml`. The store was COPIED first: pilot 8's own rows
are untouched.

STAGE 7 RAN END TO END FOR THE FIRST TIME, in 173.6 s of its 2400 - 170 of them
the one assess turn, the warm build and the reset inside it - and neither the
wall nor the cap stopped it: assess answered `UNCLEAR` and the chain
skipped repro, fix, regression and writeup by its own rule. A zero-spend
rehearsal ran first, same script and cluster with the interlock at 0, refusing
at `RayTaskError(LiveModelRefused)` in 2.3 s: the dispatch path, placement on
`{"repair": 1}` included, proved before a turn was paid for.

## 1. What ran, and when

| UTC | |
|---|---|
| 21:01:31 | driver starts; `mint_local_id` gives 900000004 |
| 21:01:33 | `repro.sh` and `case.mlir` written under `repair/900000004` |
| 21:01:33 | `circt_warm_build`, `circt_git_reset`, then the assess turn |
| 21:04:23 | chain returns `unclear`; `repro.sh` re-hashed, UNCHANGED |
| 21:04:24 | `_restore` resets, cleans, and its rebuild FAILS |

## 2. The build, which is a defect

`_restore`'s `ninja -C /workspace/circt/build -j 4` FAILED. CMake re-ran and
died inside slang's `FetchContent`: `configure_file ... Operation not
permitted`, twice, then `slang version: 11.0.+` and `VERSION "11.0." format
invalid`. `restore_ok` is false; `restore_hashes_match` is TRUE, so every tool
binary is still the image's and no verdict downstream is at risk. The same
command runs first as `circt_warm_build`, unchecked, so the assess turn
probably read a tree whose build could not be regenerated either. Probed after:
the `_deps` directory is world-writable, so this is no permission bit.

## 3. Tool calls, which the chain does not report per phase

| server | port | HTTP requests |
|---|---|---|
| `bash_900000004` | 8000 | 23 (22 `200`, 1 `202`) |
| `build_900000004` | 8001 | 0 |
| `lit_900000004` | 8002 | 0 |

`run_issue_remote` returns per-phase logs and `_as_repair_result` keeps none,
so this access log is the only count there is; the same drop loses the assess
turn's `REASON:` text, so the loop records `status = unclear` and NOT WHY.

NO PATCH WAS PRODUCED: `diff_path`, `diff_added`, `diff_removed`, `fixed`,
`build_ok` and every `lit_` field are null, and `lit_unusable` and
`repro_overwritten` are false, the two `repro.sh` hashes being equal.

## 4. The money, which cannot be read here

| | |
|---|---|
| ceiling, one phase | 6.484763 |
| `authorised_usd`, 5 x ceiling | 32.423815 |
| `billed_usd`, `calls`, tokens | null |
| 429s | 1, retry 1 of 6 after 20.8 s, cleared |
| `TurnBudgetExceeded`, exceptions | none |

The ledger row is `metered = 0` by the manifest's own `stages_metered`, so none
of this reaches the campaign cap, and the authorisation stands at 32.42 for
five phases of which four never happened. BILLING IS UNOBSERVABLE FOR THIS
STAGE BY DESIGN: the chain dispatches its own turns and the counting copy of
the model object dies with the worker (`token_capture =
unavailable_remote_dispatch`). THE ARCHITECT MUST READ THE GOOGLE BILLING PAGE
for what this cost; no figure here is a bill.

## 5. Two deviations, both forced

`PYTHONPATH=circt_bug_loop/_shipped` shadows the installed `chia` and
`stage_shipped` then refuses, the staged copy having no
`examples/circt_issue_solver`; the run used the repository root, which is what
`bug_loop_submit.sh` puts on a job's path. The `BudgetFile` came from
`<artefacts>/<run>/budget.yaml`, the copy pilot 8 ran with, because `load_budget`
now refuses `circt_bug_loop/budget-pilot.yaml`, committed past
`registration/campaign-1` at 8e4fd26.
