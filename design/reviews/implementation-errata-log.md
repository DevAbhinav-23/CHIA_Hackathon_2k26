# Implementation errata log (running; consumed by the pre-red-team errata pass)

Each row: task, what the code does that the design did not say or said differently, and the design section owed a fix. Design files are not edited from this log until the batch pass before W-20.

## W-05 corpus builder (2026-09-14)
| # | Finding | Owed to |
|---|---|---|
| 1 | `build_corpus(clone_path, corpus_head_sha, since, inline_cap_bytes, timeout_seconds=1800) -> dict` (LLD §3.3 signature kept; the work-plan brief's `list[SeedRecord]` form was wrong) | 05 §9 |
| 2 | The git-command table cited as "§4.12" lives unnumbered inside LLD §4.11.1; RUN-line normalisation is §4.1/§4.2, not §4.4 | 03 numbering |
| 3 | FR-01.7 "nearest tag" has no schema field; returned as a top-level `nearest_tag` map; `sdk_tag` null on the 16 inexact seeds | 01 FR-01.7, 03 §3.3 |
| 4 | Multi-tool seeds (27) take the first RUN line's tool in `test_paths` order; M1's per-tool partition is not reconstructible from its script, membership is | 01 FR-01.3, measurements M1 |
| 5 | FR-01.2's acceptance seed `f2b15a44ec70` is not in the 187 (no bug-ish subject word); its RUN line has two spaces where the AC quotes one | 01 FR-01.2 |
| 6 | `split-file` lines carry a meaningless tool/argv; only `shape=split_file` is informative | 03 §4.1 |
| 7 | A quoted `;` inside an option value is rejected by step 6 as written (conservative) | 03 §4.1 |
| 8 | Shell redirects (`>`) survive normalisation as argv tokens (10 lines, 4 seeds) | 03 §4.1 |
| 9 | `env … not …` ordering: strip either wrapper until neither leads | 01 FR-01.10 |
| 10 | Exclusion precedence: `seed_text_over_cap` > `no_run_line` > `unsupported_shape` | 03 §3.3 |
| 11 | No real RUN line carries a backtick or `$(`; those step-6 cases are constructed | 04 corpus tests |
| 12 | Node returns `counters` (CounterBlock), `exclusions`, `nearest_tag`, `sv_seeds` and extra count keys | 03 §3.3 Returns |
| 13 | "Byte-identical output" (T-U-corpus-19) means records plus counts; `CounterBlock.seconds` is wall clock | 04 |
| 14 | `m1_runlines.py`'s `circt-capi-.*` swallowed trailing text; copied as `circt-capi-[\w-]*` | measurements M1 |
| 15 | New test ids T-U-corpus-25..36; `resolve_sites` + T-U-corpus-24 implemented | 04 §1 corpus |
| 16 | Open: W-05b (A-02 subject-proxy precision, 30 seeds), W-05c (A-19 differential applicability); `fetch_clone.sh` and the raw-JSON fixture copy not created (`filtered_187.json` used instead) | 05 |

## W-06 store, budget, ledger (2026-09-14)
| # | Finding | Owed to |
|---|---|---|
| 1 | **Calling a `@ChiaFunction` node directly starts local Ray via the profiler and raises `FutureWarning` under `-W error`.** Architect's decision: nodes stay decorated per LLD §3.2; unit tests call `fn._chia_original` through a `conftest.call_node` helper. W-06 left `load_budget`, `accrue`, `artefact_write` undecorated pending this; re-decorate in the follow-up | 04 §0.4, 03 §3.2 |
| 2 | `snapshot(ledger, arm, budget)`: `BudgetLedger` has no cap field | 03 §3.11 |
| 3 | `accrue(entry, db_path, budget)`: `price` needs the `BudgetFile` | 03 §3.11 |
| 4 | `accrue` never sets `metered` (FR-14.8 flag owned by the caller); T-U-ledger-08/10 written to that reading | 04 ledger tests |
| 5 | `load_budget` takes keyword-only `run_start_utc`, `manifest_budget_file_sha`, `exact_pin_shas` for checks 1, 4, 5 | 03 §3.11, §9.2 |
| 6 | FR-05.2's mutator-set rule runs inside check 1; `_CHECKS` stays six; set path derived from the budget file's directory | 03 §9.2, §8.1 |
| 7 | §9.2 heading says "five checks", body says six | 03 §9.2 |
| 8 | §2.9 "eleven reduction fields" is nine | 03 §2.9 |
| 9 | Not every table carries `run_manifest_id`: 9 do, 10 join via probe/candidate ids, `image` and `issue_mirror` carry neither | 03 §6.2 |
| 10 | "Completion record" = a `probe_result` or `candidate` row whose `artefact_dir` equals the directory (`probe` excluded) | 03 §6.5 |
| 11 | `artefact_write(..., store=)`; marker protocol: `relative_path == "PARTIAL"` with `b""` writes, `None` removes; any other write creates the marker when absent | 03 §2.9, §6.5 |
| 12 | `aggregate` reads `filings_*` from `filing`; `inputs_today` = stage-3 occupancy entries per UTC day per arm; keyword-only `today` | 03 §3.11 |
| 13 | `stop_reason` order fixed: `campaign_spend_cap`, `arm_window`, `generated_inputs_per_day`, `filings_total`, `filings_per_day` (`STOP_REASONS`) | 03 §3.11 |
| 14 | FR-14.4 "one `arm_window` entry per arm per run" enforced in `accrue` (`E005`) | 03 §3.11 |
| 15 | `ledger.py` imports `BudgetLedger` from `store.py`; `test_layout.py` rule (2) must exempt `BudgetLedger` and `LoopStore` | 03 §2.9, 04 layout |
| 16 | `CandidateRecord` has 38 fields, not 41; `candidate` table has 20 columns (correct) | 03 §2.9 |
| 17 | `load_candidate` on a `differential` candidate: `frames_*` 0/0 and null `repro_command` when no `oracle_verdict` row | 03 §2.9 |
| 18 | Fixtures: malformed budget variants derived at test time from the committed `budget.yaml`; throwaway repos built by a Python helper; `secrets/known_values.txt` pending, T-U-store-10 values inline | 04 §13 |
| 19 | Trap: `git log --format=%cI` emits `Z`, rejected by Python 3.10 `fromisoformat`; `budget._iso` normalises | 03 §3.11 |

## W-02/W-03 contract (2026-09-14)
Recorded directly in LLD §16 and test plan §16.7.

## W-09 crash fixtures (2026-09-14): real-output findings, architect's decisions
| # | Finding | Decision | Owed to |
|---|---|---|---|
| 1 | §3.7.1 step 2 cuts at the first depth-zero `(`, so `(anonymous namespace)::X::f` normalises to `""` and is skipped; every trace loses a frame; `fatal_error` fingerprints collapse to `main` | Strip a leading `(anonymous namespace)::` (and any `(anonymous namespace)::` segment) before the cut; keep the qualified name | 03 §3.7.1; probe_task `_normalise_function` |
| 2 | §3.6.2 step 4 `out_of_scope_root` reads only the first `#n` line of frames sharing one address (inlined chain); 3 of 4 mined bugs wrongly out of scope | Frames sharing an address form one group; the group is in scope if any member resolves to a CIRCT source file; the fingerprint frame is the group's deepest CIRCT member | 03 §3.6.2; probe_task `out_of_scope_root` |
| 3 | `strip_probe_only_options` only knows `--verify-diagnostics`/`--split-input-file`; CIRCT tests also write the single-dash forms, which survive into probe argv | Accept both dash spellings (bare and `=`-valued) | 03 §3.3/§4.2; corpus.py |
| 4 | Fixture root is `tests/fixtures/crashes/` (brief and crash_01); plan §5.2/§13 and T-E-input-02 say `fixtures/oracle/<class>_<nn>/` | Keep `crashes/`; amend the plan | 04 §5.2, §13 |
| 5 | Six fixtures (crash_01, assertion_01..04, fatal_error_01), two SDK tags (1.143.0, 1.156.0); `_ASSERT_UNREACHABLE` still unexercised on real output; calibration-mode build costs measured: 14 s to 601 s per parent build | 01 A-01 note; 05 |
