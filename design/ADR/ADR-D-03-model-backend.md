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
