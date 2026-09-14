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

## W-07 / follow-ups (2026-09-14): `pin_select.py`, W-09 #3, W-06 #1
| # | Finding | Owed to |
|---|---|---|
| 1 | **§3.4's signature cannot reach `main`.** `select_release_pinned_main(clone_path, timeout_seconds=600)` walks `HEAD`, which §4.11.1's table spells for every pin-walk command, but the head's blobless clone is detached at `corpus_head_sha` while A1 holds it (FR-01.11), and `HEAD` is then the corpus head and not `main`. Implemented with a keyword-only `ref: str = "HEAD"`, and the acceptance run passes `origin/main` | 03 §3.4, §4.11.1 |
| 2 | `corpus._walk_pins` gained the same `ref="HEAD"` parameter, and `pin_select.py` **imports** `_Git`, `_read_tags` and `_walk_pins` across the module boundary rather than copying them, which is what §4.11.1 listing §3.3's and §3.4's commands once means. Any `test_layout.py` rule about private names must exempt these three | 03 §3.3, §3.4; 04 layout |
| 3 | **Two refusals, not one.** §3.4 names `PinSelectError("no_match")` only, and T-U-pin-05 raises it on an empty tag list; the shared `corpus._read_tags` already separates that case, and the operator's next action differs (a clone fetched without `--tags`, not a `main` that drifted), so an empty tag map raises `PinSelectError("no_tags")` naming the refspec and the walk never starts | 03 §3.4, 04 §1.5 T-U-pin-05 |
| 4 | FR-02.5's "24 months" has no number. Implemented as `pin_select.WINDOW_DAYS = 730`, measured from the **head commit's own date** and not from now, so the window a run examines is a property of the clone rather than of the day the run happens | 01 FR-02.5, 03 §3.4 |
| 5 | **F-02's preconditions name a network the code does not use.** F-02 says "network access to the `llvm/circt` git remote and the GitHub releases API"; the selector reads a local clone only, and takes releases from `for-each-ref refs/tags/firtool-*`, never from the releases API. The fetch is the operator's, before the run | 01 F-02 preconditions |
| 6 | F-02's ACs are written against the clone "at `b792c772`", which is this host's clone's detached HEAD and one first-parent commit behind `origin/main`. Both ACs hold at either point (the pin `e297b52ec9d8` has no release at both), but the lag differs: 7 commits from `b792c772`, 8 from `origin/main` | 01 F-02 ACs |
| 7 | **The eight fields do not land in the manifest as eight.** §3.4 says B12 "writes all eight fields into the `RunManifest`"; `RunManifest.run_commit` is `list[RunCommit]`, so the returned `run_commit` string must be wrapped, and `resolved_utc` has no manifest field at all. Seven map, one wraps, one has nowhere to go | 03 §3.4, §2.4 |
| 8 | `lag_days` is returned unrounded; W-04's 4.807 is `round(lag_days, 3)`. The tier-1 test asserts the rounded figure and the raw one against the two `%ct` values | 03 §3.4, measurements W-04 §1 |
| 9 | **The pin fixtures are recorded git output, not rows of `pin_window_raw.json`.** Plan §13 gives `fixtures/pin/` four files derived from that JSON; the fixtures are at `tests/fixtures/pin_select/` and each replays the six git commands of §4.11.1 verbatim, because the recorded form exercises `corpus._read_tags` and `_walk_pins` and a parsed-window fixture would step over exactly the code §3.4 says A2 shares with A1. `make_fixtures.py` is committed beside them, which is §13's own rule | 04 §13, §1.5 |
| 10 | Test ids: T-U-pin-02's criterion (the lag against `rev-list --first-parent --count`) is discharged **inside** the one tier-1 test, T-U-pin-08, rather than as a second live test; T-U-pin-09 (every window released) and T-U-pin-10 (the `_chia_options` row, the six argument vectors, §3.1's paragraphs) are new. Nine ids over eleven pytest items, T-U-pin-07 being parameterised over three fixtures | 04 §1.5 |
| 11 | W-09 #3 **discharged**. `_PROBE_ONLY_OPTIONS` is four spellings, not two. The reach is measured, not assumed: 46 of M1's 331 corpus `RUN:` lines spell one of the two options with a single dash (`raw/m1-per-runline.csv`). New ids T-U-corpus-37 (three recorded lines) and T-U-corpus-38 (`crashes/assertion_02/argv.json` fed back through the function) | 03 §3.3/§4.2, 04 §1 corpus |
| 12 | W-06 #1 **discharged**. `load_budget`, `accrue` and `artefact_write` carry `@ChiaFunction(max_retries=0)` again and their tests call `conftest.call_node`. `test_corpus.py`'s tier-1 tests were calling `build_corpus` and `resolve_sites` through the wrapper and carried a `_RAY_WARNING` mark to silence what Ray's startup then raised under `-W error`; both are gone, and the module is 7 s faster | 03 §3.2, 04 §0.4 |
| 13 | `conftest.py` gains one session finaliser, `no_local_ray`, asserting `ray.is_initialized()` is false at session end and naming `call_node` in the message; it stands down when `BUGLOOP_CLUSTER` or `CHIA_LIVE_CLUSTER` is set, the two tiers that legitimately hold a Ray. §0.4 should name both `call_node` and this check, since §0.4 as written (a plain call to the wrapper) is what the check now forbids | 04 §0.4 |
