# Disposition of `red-team-code.md` (architect, 2026-09-15)

All 11 kills and 12 wounds accepted. Decisions below are binding for the fix round (W-20b). Nits fixed where one line.

| Id | Decision |
|---|---|
| K1 | `build_image` becomes a **head-side** function (Docker lives on the head); tag scheme is the Dockerfile's `chia-circt-assert:<CIRCT_SHA12>`, with the manifest digest recorded in `ImageSpec` (not in the tag); Dockerfile path `upstream/dockerfiles/ChiaCirctAssertDockerfile` in this repo, build context the repo root; no `docker push`; `--image-tag` compares the SHA prefix; `--dry-run` inspects an existing image and never builds. |
| K2, W7 | The model client is constructed **on the llm worker inside `llm_turn`** from that worker's own environment; `build_llm`/`require_live_model` run there; circt workers never see the key; the LLM object is no longer a Ray task argument. `generate_seeded`/`triage_report` dispatch a turn request (system message, prompt, tool endpoints, stage, timeouts) to `llm_turn`. |
| K3, K6, K7 | The repair `cfg` is assembled **on the head** (`repair_adapter.build_cfg` reads CHIA's example prompts there) and passed complete to `repair_adapt`; the shipped `issue_task.py` is a **patched copy** staged under `circt_bug_loop/_shipped/` at startup by applying `upstream/issue_task-vertex-branch.patch`; a new pre-flight check (13) greps the shipped copy for `elif backend == "vertex":` and refuses otherwise; `RunManifest.model_ids["repair_adapt"]` is derived from that check, not from the flag. |
| K4, K5 | `Dispatch.call` pins every node in a `HEAD_NODES` set to the head's Ray node id with `NodeAffinitySchedulingStrategy(soft=False)` (the `_head_options()` mechanism); `cfg["head_options"]` is populated for `SourceReadTool` and `resolve_sites`; a T1 test asserts the set matches every node whose docstring says `Worker: head`. |
| K8 | Sequenced: W-12 mutator synthesis is the **first live call** (small, bounded: one synthesis turn per batch of issues, cap USD 5), producing `mutators/set_v1.json`, frozen before pre-registration. |
| K9 | `_limit_hit` returns `address_space` only when the child **died by signal** and an allocation literal is present, or when `RLIMIT_AS` was observed exceeded via rusage; a diagnostic containing the phrase is `parse_error`; an assertion whose text contains it is `assertion`. Fixture-driven test over the six crashes with the phrase appended. Exit 127 from the loader classifies `tool_unavailable` (new build status; taxonomy `undecided`). |
| K10 | `llm_turn` prices a turn **only** from counts it observed; a failed or empty `_last_metadata` yields null tokens and null `cost_usd` (never 0), and the ledger marks the entry `observed=False`; the results artefact prints the count of unpriced turns beside the USD total as a lower-bound disclosure. |
| K11 | Ship a **patched copy of CHIA's `chia/models/vertex.py`** in the staged package (`upstream/vertex-usage.patch`: add `thoughts_token_count` and `tool_use_prompt_token_count` to `_last_metadata`) and count thinking tokens as output; pre-flight check 14 verifies the patch is in the shipped copy; both patches proposed upstream. |
| W1, W10 | **Pre-authorisation**: before every model turn the driver computes `worst_case_usd = (prompt_chars/3 + max_output_tokens_incl_thinking) × prices` and refuses the turn when `spend + worst_case ≥ campaign_spend_cap_usd`; the check runs per turn, not per seed; `LedgerSnapshot` is refreshed per iteration. |
| W2 | Checks 7 and 8 take real `worker_probes` observations from every worker type. |
| W3 | `ProbeResult.stopping_reason` is assigned wherever `stopping_stage` is. |
| W4 | `--generator recorded` skips check 12 and requires no key or interlock anywhere. |
| W5 | An undecidable Q3 second conjunct refuses as `undecided` (FR-13.10). |
| W6 | `runtime_env` ships the staged package only (`_shipped/`: loop modules, patched `chia`, patched `issue_task.py`, `circt_util.py`, prompts), never `tests/`, `loop.db*`, fixtures; the staged `chia` gets an `__init__.py` so it shadows the container's install deterministically. |
| W8 | `budget.yaml` header: prices verified on Google's page 2026-09-15 (ADR-D-03). |
| W9 | A T3 test dispatches every node type through Ray on the cluster (W-19b's run). |
| W11 | Filing caps are **per campaign run** (`run_manifest_id` predicate); lifetime total shown to the approver for information. |
| W12 | Keep as the declared fallback; `bug_loop` prints a warning banner when `--repair-backend` is not `vertex`. |
| N1–N10 | Fix N2, N3, N5, N6, N8, N9, N10 in the same round; N4 documented; N7 reworded in the LLD. |

**The single question (project-level hard spend cap).** Google Cloud budgets are alerts, not caps. The loop's own cap, made trustworthy by K10/K11/W1, is the hard stop; the pilot runs with `campaign_spend_cap_usd: 5.0` and `--no-repair`, and the operator confirms the project's billing page against the ledger after the pilot before the campaign. The user is asked to confirm no other workload shares the key's project.

## Additions from W-19b (architect, 2026-09-15)
| Item | Decision |
|---|---|
| `Dispatch` never dispatched (`isinstance(fn, ChiaFunction)` false for every node) | Fixed by W-19b (`hasattr(fn, "chia_remote")`); add a T1 test that a dispatched node runs off-head (node id differs from the driver's) whenever a cluster is present. |
| `mutant_seed_int` is unsigned 64-bit; SQLite INTEGER is signed | Mask to 63 bits (`& (2**63 - 1)`) **before** A7 freezes any set; regenerate the two mutation fixtures; document in §8.2. |
| `render_results` refuses at campaign end (labelled pairs have no way in; `ResultsIncomplete` uncaught) | The driver passes `labelled_pairs` from the committed labelled set (`tests/fixtures/dedup/` or its non-test home under `circt_bug_loop/data/labelled_pairs.json`, moved there) and catches `ResultsIncomplete`, writing the refusal list to the artefact root and exiting non-zero after the ledger and store are complete. |
| Calibration mode unsatisfiable with a fixed image (FR-02.7) | Calibration runs only for seeds whose parent's LLVM pin equals the image's pin: the `circt` worker checks out the parent inside `/workspace/circt` (fetch by SHA), builds the entry tool incrementally with the image's SDK, runs the probe, then restores (`circt_git_reset` + rebuild + hash check). Seeds on other pins are `not_calibratable_in_deployment` and excluded from the sample; the six host-built fixtures remain the oracle/reducer calibration. FRD erratum to FR-02.7 and D-01(d); `calibration_sample_shas` re-drawn from the eligible set. |
| Submitted job could not import its package | Keep W-19b's `PYTHONPATH` in the wrapper; add a pre-flight check that the entrypoint imports `circt_bug_loop` in a subprocess. |
| `Assisted-by:` trailer names a model that did not run | Trailer reflects `stages_metered` and the actual backend per turn; omitted in recorded mode. |
| `test_layout.py` registrations for `test_system.py` and `test_upstream_patches.py` | Done by W-19b; keep. |
