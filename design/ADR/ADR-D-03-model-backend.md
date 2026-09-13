# ADR-D-03: Which model backend each agent stage uses

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation. User's explicit words: *"for model cant u use
sonnet and opus fresh subagent? ... cant it be done at the last?"*
**Resolves:** `01-FRD.md` §8 D-03.

## Context

D-03 recommends (d): one backend and one model per run, set by the cluster YAML, defaulting to
`opencode` with `google-vertex/gemini-3.1-pro-preview`, because the credits pay for Gemini and only
the Gemini backends report per-phase usage. C-20 prices per-stage configurability at two LLM worker
types, a backend being a cluster and not a flag. The user asks for Opus and Sonnet, and whether the
campaign choice can be deferred. Both answers are yes, and they are two questions.

## Decision

**The backend is a per-run choice made in the cluster YAML**, one backend per run, as (d) has it.

**Development and test default: CHIA's `claude` backend**, the Claude Code CLI
(`chia:chia/models/claude.py:338-345`; `772-815` builds
`claude --print --model <id> --dangerously-skip-permissions -p -`), inside
`ghcr.io/ucb-bar/chia-claude-code` with the user's `~/.claude` login mounted
(`chia:examples/circt_issue_solver/cluster.yaml:29-36`). No API key is needed.

**Within one backend the model id is set per agent stage**, which C-20 does not price, because one
backend is one image, one mount and one `llm` resource name: `claude-opus-5` for stages 1 and 2,
`claude-sonnet-5` for stage 6 `[DEFAULT]`, and `claude-opus-5` for stage 7 `[DEFAULT]`. A model id is
configuration, not a prompt, so FR-12.9 is untouched. Both ids are
`[UNVERIFIED until the CLI accepts the id]`.

**The campaign backend is fixed in the pre-registration commit (F-14), not now:** `opencode` with
`google-vertex/gemini-3.1-pro-preview` if the hackathon credits have arrived by that date, otherwise
the `claude` backend.

## Consequences

- **FRD:** D-03's per-run single backend stands; its per-stage prohibition narrows to cross-backend
  choice. FR-14.6's ledger is empty under `claude`, so FR-14.8 marks those stages unmetered.
- **The `claude` backend reports no per-phase token usage**
  (`chia:examples/circt_issue_solver/circt_issue_loop.py:132-134`, whose comment names `antigravity`
  and `opencode` as the reporting backends). This is why D-04's unit is wall-clock.
- **A subscription rate limit was observed on 2026-09-13.** The campaign must not share the
  `~/.claude` login with interactive work while it runs.
- **HLD:** one `llm` worker type, one image per run, a per-stage model id in the run configuration.

## Follow-up measurements

One command settles both ids before any stage runs:
`claude --print --model claude-opus-5 -p - <<< 'reply ok'`, repeated for `claude-sonnet-5`. In
`analysis/measurements/`.

## Superseding decision, 2026-09-14 (architect, on the user's delegation)

**Context.** The user supplied a Google Cloud API key (stored at `~/.config/bugloop/gemini.env`, mode 600; never printed, never in a URL). Verified 2026-09-14: the AI Studio endpoint is disabled on the key's project (403), but **Vertex AI express mode accepts the key**: `genai.Client(vertexai=True, api_key=...)` from `google-genai` 2.8.0 in the head environment returned `OK` from both `gemini-3.1-pro-preview` and `gemini-3.8-flash`, with `usage_metadata` token counts. CHIA's `vertex` backend builds exactly that client (`chia:chia/models/vertex.py:406-410`: `genai.Client(vertexai=True, project=self.project, location=self.location, **self.client_kwargs)`), so `VertexGeminiLLM(model=..., client_kwargs={"api_key": os.environ["GEMINI_API_KEY"]})` with `project=None, location=None` is express mode with no code change to CHIA. Its `prompt` is a `@ChiaFunction(resources={"vertex_creds": 0.01})` (`vertex.py:271`) that drives ChiaTools over MCP client-side, like the other API backends.

**Decision.** Development, tests and the campaign all use CHIA's `vertex` backend in express mode with the user's key. Model id for every agent stage: **`gemini-3.8-flash`** (user's instruction, 2026-09-14: "do not use 3.1 pro use 3.8 flash"). `gemini-3.1-pro-preview` is not used. The `claude` backend remains the fallback for a Vertex outage only. The key reaches the LLM worker container as an environment variable set from the operator's shell at `chia up` (`run_options: -e GEMINI_API_KEY=${GEMINI_API_KEY}`), never through `chia job submit` runtime-env metadata (NFR-06). The LLM worker image becomes `ghcr.io/ucb-bar/chia:latest` (no CLI needed); the prompt node is dispatched with `.options(resources={"llm": 1})` as CHIA's example does.

**Consequences.** Token usage is now observable on the campaign backend, so `LedgerEntry.observed.tokens` is populated for the seeded arm (D-04's primary unit stays wall-clock). No dependence on the user's Claude subscription or its rate limits. The work plan's H-04 (confirming Claude model ids inside the `chia-claude-code` image) becomes optional. HLD §4.1, LLD §11 to §13 and the test plan's NFR-06 secret grep must be updated to name `GEMINI_API_KEY`; that fold-in follows the LLD resync. Cost is charged to the user's Google project, which carries a **USD 300 credit limit** (user, 2026-09-14). Two rules follow. (1) **No live API request of any kind until the code is verified**: tiers T0, T1 and T2 of `04-Test-Plan.md` green with the model layer mocked (as CHIA's own `chia/models/tests/test_vertex.py` mocks it), the code red team passed, and the pilot started deliberately with a tiny pre-registered budget; the only calls made before that were three one-word key-verification probes on 2026-09-14 (about 24 tokens). (2) `budget.yaml` carries a hard spend cap, `campaign_spend_cap_usd` `[DEFAULT]` 200, enforced by the ledger from `usage_metadata` token counts times the per-token prices for `gemini-3.8-flash`: USD 0.75 per million input tokens and USD 3.75 per million output tokens (introductory Vertex pricing through 2026-12-31; aggregator-sourced 2026-09-14, `[UNVERIFIED]` against Google's own pricing page, which must be re-read before the pre-registration commit and the figures written into `budget.yaml`); the driver stops both arms when the cap is reached, and the spend is reported per FR-14.6.

## Addendum, 2026-09-14 (later the same day): stage 7 joins the campaign backend

**Status:** Accepted. **Decided by:** architect, on the user's delegation. **Supersedes** the part of the fold-in that made `--repair-backend claude` the default; nothing else in the superseding decision above moves.

**Context.** The superseding decision put stages 1, 2, 6 and the offline mutator synthesis on CHIA's `vertex` backend and left stage 7, the repair adapter, on a second backend. The reason was FR-12.1, which required `examples/circt_issue_solver/issue_task.py` to be **byte-identical** to CHIA at `16c35e92`, and that file's `_turn` selects among `antigravity`, `opencode` and `claude` and falls through to `ClaudeCodeLLM` for anything else (`chia:examples/circt_issue_solver/issue_task.py:81-123`). Handed `cfg["backend"] = "vertex"` it would have built a Claude client silently. The fold-in therefore defaulted stage 7 to `claude` and declared it unmetered, and wrote the missing branch into `upstream/` as a contribution offered and not depended on.

That left the campaign paying a real price for a rule about a hash. Stage 7 alone needed a second backend, a second credential, a second model id and a second failure mode; it was the only stage that depended on the user's Claude subscription, whose rate limit was already observed on 2026-09-13; and its spend could not be priced by the ledger at all.

**Decision.** **Stage 7 runs on the same `vertex` backend and the same `gemini-3.8-flash` model as every other stage.** The mechanism is one **additive** `elif backend == "vertex":` arm inserted into `_turn` between the `opencode` arm and the `else`: it constructs `VertexGeminiLLM(model=cfg["model"], system_message=cfg["system_prompt"], timeout_seconds=cfg["timeouts"][phase], client_kwargs={"api_key": os.environ["GEMINI_API_KEY"], "http_options": {"timeout": cfg["timeouts"][phase] * 1000}})` and then sets `llm.project = None; llm.location = None`, which is the express-mode work-around the fold-in measured. It is **nineteen lines, no deletion and no altered line**; `os` is already imported at `issue_task.py:12`; and `VertexGeminiLLM` is imported inside the branch exactly as the two arms above it import theirs.

FR-12.1's acceptance changes with it, from a byte comparison to **hunk equality**: `git diff` against CHIA `16c35e92` must show exactly that one hunk and nothing else. Verified 2026-09-14 against `~/.cache/chia-src` at `16c35e92`: `git apply --check` passes, `git apply` then `ast.parse` succeeds, `git diff --stat` reads `1 file changed, 19 insertions(+)`, and `git diff` contains exactly one `@@` header. The patch is `upstream/issue_task-vertex-branch.patch`, `upstream/sync-to-chia.sh` applies it into the CHIA checkout unless it is already present, and it is proposed to `ucb-bar/chia` as part of the same pull request.

`--repair-backend` and `--repair-model` survive with `vertex` as the default; `--no-repair` is unchanged. `claude`, `antigravity` and `opencode` remain reachable as the Vertex-outage fallback, and choosing one is what makes `stages_metered["stage_7"]` false.

**Why, in three reasons.** First, no dependence on the user's Claude subscription: one credential, one rate limit, one outage surface, and the USD 300 Google credit is the only budget the campaign spends. Second, **one backend for all seven stages**, which is what C-20 and the superseding decision were reaching for and what the byte rule prevented: one model id, one price table, one mocking strategy in `04-Test-Plan.md`, and a `RunManifest.model_ids` whose four values now agree. Third, the nineteen lines are a contribution CHIA plainly wants: `vertex` is a backend CHIA ships and its own flagship example cannot select, and the arm is unreachable for every existing CHIA caller, `circt_issue_loop.py` building `CFG["backend"]` only from `BACKEND_DEFAULT_MODEL`, whose keys are exactly the three (`circt_issue_loop.py:74`, `176`, `193`).

**Consequences.**

- `cfg["backend"]` is `"vertex"` and `cfg["model"]` is `"gemini-3.8-flash"`, `budget.yaml`'s own `model_id`. `RunManifest.model_ids["repair_adapt"]` reads `vertex:gemini-3.8-flash`, equal to the other three, and `stages_metered["stage_7"]` is **true** by default.
- **Stage 7's token counts are still not captured, and the design says so rather than reporting zero.** This does not follow from the backend and is not fixed by it. `_turn` dispatches the turn with `get(llm.prompt.options(resources={"llm": 1.0}).chia_remote(llm, prompt, tools))` (`issue_task.py:124`); `chia_remote` serialises the LLM object; and `VertexGeminiLLM` accumulates `usage_metadata` counts into `self._last_metadata` **on that object** (`chia:chia/models/vertex.py:479-482`, `579`) rather than onto the returned `QueryResult`, whose five fields carry no usage (`chia:chia/base/llm_call.py:15-35`). The counting copy dies on the worker. The loop's own stages escape this through `llm_turn`, which calls `prompt` directly and reads `_last_metadata` in the same process (`03-LLD.md` §3.5.1), and that is a **call-site** change: line 124 is outside the additive arm, and editing it would both break hunk equality and move CHIA's turn off the `llm` worker for all four backends. There is no second source either: `logs[phase]["usage"]` is `getattr(cli, "usage", None)`, which is `None` here, `circt_issue_loop._persist` writes `llm_usage` only where that is truthy (`circt_issue_loop.py:132-136`), and the backend's `stream_result` logs no token line. So stage 7's `LedgerEntry.observed` carries **null** `tokens_in`, `tokens_out` and `cost_usd` with `metered` true; the reason, `unavailable_remote_dispatch`, is recorded on `RepairResult.token_capture`, not inside `observed`, whose four declared keys are frozen by the contract's MAJOR-bump rule; and the results artefact prints the campaign's USD figure as a **lower bound excluding stage 7**.
- Therefore `campaign_spend_cap_usd` bounds the **observed** stages only. The operator's project-level budget alert bounds the rest, and `--no-repair` is the way to run a campaign whose reported spend is complete. This is a real residual and is written into `01-FRD.md` §1.9, `03-LLD.md` §15 item 9 and `04-Test-Plan.md` §16.6 rather than left to be discovered.
- The work plan's H-04 stays optional and `--repair-backend claude` stays the only thing that would want it.

**What was rejected.** Changing `issue_task.py:124` to a direct call plus a `_last_metadata` read, which would capture the tokens. It makes the diff two hunks including a deletion, which is precisely what the new acceptance criterion exists to forbid, and it changes CHIA's scheduling for all four backends. The observability gap is the cheaper cost and it is bounded and recorded.
