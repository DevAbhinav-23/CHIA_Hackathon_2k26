"""The one neutral module both halves import (03-LLD.md 3.5.1, 7.1, 1.1).

Five things live here and nothing else does: `MODEL_BACKEND`, the constant
`RunManifest.backend` records; `require_live_model`, the live-call interlock;
`build_llm`, the ONLY place in the loop's own modules that names
`VertexGeminiLLM`; `llm_turn` with `dispatch_turn`, the one node every model
turn of the campaign goes through; and 7.1's output-contract parser,
`parse_json_footer`.

**Why a module of its own.** `02-HLD.md` §2's seam divides the flow into a
supply half and an apparatus half, and 05-Work-Plan.md §2.3 forbids the
apparatus half importing the supply half. These five began in
`generate_task.py`, which is the supply half (A3, A4), so `triage_task.py` (B7)
and `repair_adapter.py` (B8) could reach them only through a function-local
import, and 7.1's "one function, shared by all four" parser acquired a second
copy in `triage_task.py`. This module is NEITHER half, so both may import it at
module scope and the parser is one function again (architect decision 3,
2026-09-15; LLD §16.2, §3.5.1).

`require_live_model` takes an explicit `env` mapping, which is the other half of
the same decision: `04-Test-Plan.md` `T-U-layout-08` (1) forbids any test outside
`tests/system/` to put `BUGLOOP_ALLOW_LIVE_MODEL` into the process environment,
and the allow path still has to be exercised against the real refusal, the real
key check and the real express construction. An injected mapping is the only
shape that does both (architect decision 2).
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import socket
import time
from typing import Mapping, Optional

import ray
from chia.base.ChiaFunction import ChiaFunction, get

from circt_bug_loop.contract.schema import CounterBlock

# ---------------------------------------------------------------------------
# 3.5.1 The backend, the interlock and the turn
# ---------------------------------------------------------------------------

#: RunManifest.backend. One backend per run (C-20), named here and in no other
#: module of the loop.
MODEL_BACKEND = "vertex"

_LIVE_MODEL_ENV = "BUGLOOP_ALLOW_LIVE_MODEL"
_API_KEY_ENV = "GEMINI_API_KEY"


class LiveModelRefused(RuntimeError):
    """A real model backend was asked for without the live-call interlock set."""


def require_live_model(purpose: str, *, need_key: bool = True,
                       env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Refuse to set up a live model turn unless the interlock allows one.

    Returns:
        str, the stripped API key, when *need_key*; None otherwise.
    Worker:
        the caller's; wherever a live turn is about to be set up, which is
        `build_llm` below and `repair_adapter.repair_adapt` before it invokes
        CHIA's own chain (3.8).
    Raises:
        LiveModelRefused when BUGLOOP_ALLOW_LIVE_MODEL is not exactly "1", or
        when *need_key* and GEMINI_API_KEY is unset, empty or unexpanded.
        Nothing else. No network call is made here.
    """
    # `env` defaults to the process environment, which is what every caller in
    # the flow passes; a test hands in a mapping instead, so the allow path runs
    # against this same code without the real variable ever being set
    # (architect decision 2, T-U-layout-08 (1)).
    if env is None:
        env = os.environ
    # Exactly "1". An unset variable, an empty one and an unexpanded "${...}"
    # all fail this, which is the safe direction.
    if env.get(_LIVE_MODEL_ENV) != "1":
        raise LiveModelRefused(
            f"refusing to set up a live model turn for {purpose}: "
            f"set {_LIVE_MODEL_ENV}=1 to allow a real model request "
            "(03-LLD.md 3.5.1; ADR-D-03, superseding section and addendum)")
    if not need_key:
        return None
    key = (env.get(_API_KEY_ENV) or "").strip()
    # An UNEXPANDED reference is a literal, not an empty value: CHIA's loader
    # substitutes ${VAR} from os.environ and leaves the text alone when the
    # variable is unset (chia:chia/cluster/config.py:304), so a container
    # brought up without the key holds the reference itself as its value.
    # Catching it here turns a 403 from Vertex into a refusal on the head.
    if not key or key.startswith("${"):
        raise LiveModelRefused(
            f"{_API_KEY_ENV} is unset, empty or an unexpanded reference on "
            f"{socket.gethostname()}: the cluster YAML passes it with -e and the "
            "operator sources ~/.config/bugloop/gemini.env before `chia up` (11.2)")
    return key


def build_llm(system_message: str, timeout_seconds: int, model_id: str, *,
              env: Optional[Mapping[str, str]] = None):
    """Build the campaign backend, refusing to reach the network unbidden.

    Returns:
        VertexGeminiLLM, configured for Vertex AI express mode: one API key, no
        project and no location.
    Worker:
        the `llm` worker: `llm_turn` below is the only caller in the flow, and
        it calls this on the worker its own decorator placed it on. No other
        worker type needs the key or the interlock (K2), and the object never
        crosses a task boundary, so the key is not a Ray task argument (W7).
    Raises:
        LiveModelRefused, from `require_live_model` above. Nothing else. No
        network call is made here: constructing the backend opens no connection.
    """
    from chia.models.vertex import VertexGeminiLLM

    key = require_live_model(f"{MODEL_BACKEND}:{model_id}", env=env)
    llm = VertexGeminiLLM(
        model=model_id,
        system_message=system_message,
        timeout_seconds=timeout_seconds,
        project=None,
        location=None,
        # api_key: express mode. http_options.timeout: MILLISECONDS, and the
        # only thing that bounds the request, because VertexGeminiLLM stores
        # timeout_seconds and never reads it (chia:chia/models/vertex.py:219,
        # 240, and nowhere else).
        client_kwargs={"api_key": key,
                       "http_options": {"timeout": int(timeout_seconds * 1000)}},
    )
    # Express mode takes an API key and NO project and NO location. CHIA's
    # constructor defaults location to "us-central1" and project to
    # $GOOGLE_CLOUD_PROJECT (chia:chia/models/vertex.py:242-247), and
    # google-genai raises ValueError("Project/location and API key are mutually
    # exclusive in the client initializer.") on that pair. Two assignments, and
    # CHIA is unchanged.
    llm.project = None
    llm.location = None
    return llm


@dataclasses.dataclass(frozen=True)
class ToolEndpoint:
    """Where one `ChiaTool`'s MCP server answers, and nothing else about it.

    This is what crosses to the `llm` worker in a tool's place. CHIA's backend
    reads exactly these off a tool object - `tool.hostname`, `tool.name` and
    `getattr(tool, "port", 8000)` to build
    `http://{hostname}:{port}/{name}/mcp` (`chia:chia/models/vertex.py:426-428`),
    and `node_id` for its own `_last_metadata["tools"]` record (`:291-295`) -
    so a record of four strings serves the turn exactly as the live object does,
    without shipping a FastMCP server's whole state through the object store.
    """

    name: str
    hostname: str
    port: int
    node_id: Optional[str] = None


def tool_endpoints(tools) -> list:
    """The `ToolEndpoint` of every tool in *tools*, in order.

    Returns:
        list[ToolEndpoint]; an empty list for a turn with no tools.
    Worker:
        the caller's, which is where the tool servers were started.
    Raises:
        AttributeError when a tool was never started, `hostname` being None
        until `__post_init__` has run.
    """
    return [ToolEndpoint(name=tool.name, hostname=tool.hostname,
                         port=getattr(tool, "port", 8000),
                         node_id=getattr(tool, "node_id", None))
            for tool in tools or []]


#: What CHIA's Vertex backend caps ONE `generate_content` call's output at
#: (`chia:chia/models/vertex.py:226`), which is the quantity the pre-authorised
#: worst case of W1 is written against.
MAX_OUTPUT_TOKENS = 16000

#: Characters per token, for the pre-authorisation only. An estimate, used where
#: an OVER-estimate of the token count is the safe direction: a prompt that
#: tokenises to FEWER characters per token than this is authorised for less than
#: it costs, by whatever the ratio is wrong by.
#:
#: **2.0, measured** (W-12c; errata row 34, which recorded it unfixed). W1's own
#: figure was 3, and the project's first live turn billed 619,603 input tokens
#: for a 1,509,080-character prompt - **2.436 characters per token**, so the
#: estimate was 18.8 % low and the authorised USD 0.43727 sat 11.3 % BELOW the
#: USD 0.486733 the turn cost. This is the control that stops the campaign at
#: `campaign_spend_cap_usd`, so the constant must sit below the measurement and
#: not at it: 2.0 over-estimates that same prompt's tokens by 22 %, which is the
#: safe direction, and leaves headroom for a prompt shape tokenising worse than
#: the synthesis's. It is not a second measurement; it is the first one rounded
#: down to the nearest safe value.
CHARS_PER_TOKEN = 2.0


class SpendCapRefused(RuntimeError):
    """A turn was refused because its worst case would reach the USD cap (W1)."""


@dataclasses.dataclass
class SpendGuard:
    """The money a turn is authorised against, BEFORE it is dispatched (W1).

    `ledger.stop_reason` tests spend ALREADY RECORDED, and `_arm_stop` asks it
    once per seed; between two asks a seed can run three iterations of two turns
    each plus five probes' worth of stage-6 and stage-7 chains, so the overshoot
    was a whole seed's spend and was unbounded from above. This is the
    pre-authorisation: every turn, before it is sent, and the arm stops on the
    refusal rather than after the money is gone.

    The worst case is W1's own formula, `(prompt_chars / 3 + max_output_tokens)`
    priced at the two rates. IT BOUNDS ONE `generate_content` CALL: a turn with
    tools runs a loop of up to `max_tool_iterations` (100) of them
    (`chia:chia/models/vertex.py:227`), so for such a turn the authorised figure
    is a FLOOR and not the true worst case. Recorded rather than absorbed; the
    observed spend of the turn that overran still stops the arm at the next
    authorisation, so the overshoot is bounded by one turn and no longer by one
    seed.

    `authorised_usd` accumulates the worst case of every turn this guard has
    let through, so two turns inside one node are authorised against each
    other even though `spend_usd` is only refreshed per iteration (W10).
    """

    cap_usd: float
    spend_usd: float
    price_usd_per_m_input_tokens: float
    price_usd_per_m_output_tokens: float
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    authorised_usd: float = 0.0

    def worst_case_usd(self, prompt: str) -> float:
        """The most one model call on *prompt* can cost, at the two prices."""
        tokens_in = len(prompt or "") / CHARS_PER_TOKEN
        return round(
            tokens_in / 1e6 * self.price_usd_per_m_input_tokens
            + self.max_output_tokens / 1e6 * self.price_usd_per_m_output_tokens, 6)

    def authorise(self, prompt: str) -> float:
        """Authorise one turn on *prompt*, or refuse it.

        Returns:
            float, the worst case that was authorised.
        Worker:
            pure; it reads its own fields.
        Raises:
            SpendCapRefused when the cap would be reached. Nothing is sent.
        """
        worst = self.worst_case_usd(prompt)
        total = self.spend_usd + self.authorised_usd + worst
        if total >= self.cap_usd:
            raise SpendCapRefused(
                f"refusing the turn: USD {self.spend_usd:.4f} spent plus "
                f"{self.authorised_usd:.4f} already authorised plus a worst case "
                f"of {worst:.4f} reaches campaign_spend_cap_usd "
                f"{self.cap_usd:.4f} (FR-18.10, W1)")
        self.authorised_usd += worst
        return worst


def worker_env() -> Mapping[str, str]:
    """The environment `llm_turn` builds its client from: the LLM WORKER's own.

    A function of no arguments and deliberately NOT a field of the turn request
    (K2, W7): a request that could carry an environment could carry a key, and
    the key travelling as a Ray task argument is the unrecorded persistence
    surface W7 names. A test substitutes this name to exercise the allow path
    without ever putting the interlock into a process environment
    (`T-U-layout-08` (1), architect decision 2).
    """
    return os.environ


@ChiaFunction(resources={"llm": 1.0}, max_retries=0)
def llm_turn(request: dict) -> dict:
    """Build the backend HERE and run one model turn, bringing its counts home.

    *request* is what a caller on any worker may send: `system_message`,
    `prompt`, `tools` (a list of `ToolEndpoint`), `stage`, `timeout_seconds` and
    `model_id`. It carries NO credential and no LLM object. The client is
    constructed on this node from this node's own environment, so the interlock
    and the key are needed on the `llm` containers and on no other: the `circt`
    workers that run A3 and B7 reach a model only through this node (K2).

    *request["stage"]* is the caller's, because a turn belongs to the stage that
    asked for it and this node cannot know which: A3 runs two, B7 runs stage 6
    and A7 runs the offline synthesis. It names the `CounterBlock` 3.11 requires
    and nothing else.

    Returns:
        {"result": str, "stream": str, "stderr": str, "success": bool,
         "usage": `turn_usage`'s dict, "counters": CounterBlock}.
    Worker:
        {"llm": 1.0}; the MCP tool servers stay where their own task_options put
        them and are reached over HTTP from here.
    Raises:
        LiveModelRefused when this worker carries neither the interlock nor a
        usable key, and whatever the backend raises. A3, A7 and B7 each catch it
        and record it as their stage's turn failure (FR-04.8, FR-11.8).
    """
    # A DIRECT call, not llm.prompt.options(...).chia_remote(...): the vertex
    # backend accumulates its token counts on the LLM OBJECT
    # (chia:chia/models/vertex.py:479-482, 579) and returns a QueryResult that
    # carries none (chia:chia/base/llm_call.py:15-35), so a remote dispatch
    # would count on a copy that dies with the task and FR-14.6 would be
    # unsatisfiable. This node holds {"llm": 1.0} in that copy's place.
    started = time.monotonic()
    stage = request.get("stage", "stage_2")
    llm = build_llm(request["system_message"], int(request["timeout_seconds"]),
                    request["model_id"], env=worker_env())
    cli = llm.prompt(request["prompt"], list(request.get("tools") or []))
    success = bool(getattr(cli, "success", False))
    return {"result": cli.result, "stream": cli.stream_result, "stderr": cli.stderr,
            "success": success,
            "usage": turn_usage(getattr(llm, "_last_metadata", None)),
            "counters": CounterBlock(stage=stage, started=1,
                                     completed=int(success),
                                     failed=int(not success),
                                     seconds=time.monotonic() - started)}


def turn_usage(metadata) -> dict:
    """One turn's billed token counts, or nulls when none were observed.

    Two defects, one function (K10, K11).

    K11: `thoughts_token_count` and `tool_use_prompt_token_count` are SEPARATE
    scalars from `candidates_token_count` and `prompt_token_count` - the SDK's
    own description of `total_token_count` is the sum of all four - and CHIA
    sums neither, so whatever the model thinks was billed and not counted.
    `upstream/vertex-usage.patch` publishes the two, pre-flight check 14 proves
    the patch is in the file a worker imports, and here thinking is folded into
    the OUTPUT count (ADR-D-03: thinking tokens are billed as output) and the
    tool-use prompt into the INPUT count, so `ledger.price`'s two-price
    arithmetic needs no third rate and no fourth number.

    K10: `_last_metadata` is reset at the top of EVERY attempt and assigned only
    at the very end of a successful one, so a turn that raised inside the tool
    loop - after up to `max_tool_iterations` calls - left it empty, and reading
    it with a ZERO default priced that turn at USD 0.00. A zero is a
    measurement; an absence is not. An empty or missing block yields NULL
    counts, `ledger.price` returns None for them, and the entry carries no
    money at all rather than carrying none.

    Returns:
        {"tokens_in": int | None, "tokens_out": int | None,
         "thinking_tokens": int | None, "tool_use_prompt_tokens": int | None,
         "num_turns": int, "model": str | None, "observed": bool}.
    Worker:
        pure; it reads one mapping.
    Raises:
        nothing.
    """
    meta = dict(metadata or {})
    # The patched backend publishes `input_tokens` on every path that ran at
    # all, including the `finally` of a turn that raised; a block without it is
    # a turn whose counts were never observed.
    if "input_tokens" not in meta:
        return {"tokens_in": None, "tokens_out": None, "thinking_tokens": None,
                "tool_use_prompt_tokens": None, "num_turns": meta.get("num_turns", 0),
                "model": meta.get("model"), "observed": False}
    thinking = int(meta.get("thinking_tokens") or 0)
    tool_use = int(meta.get("tool_use_prompt_tokens") or 0)
    return {"tokens_in": int(meta.get("input_tokens") or 0) + tool_use,
            "tokens_out": int(meta.get("output_tokens") or 0) + thinking,
            "thinking_tokens": thinking, "tool_use_prompt_tokens": tool_use,
            "num_turns": meta.get("num_turns", 0), "model": meta.get("model"),
            "observed": True}


def dispatch_turn(system_message: str, prompt: str, tools: list, *, stage: str,
                  timeout_seconds: int, model_id: str,
                  guard: Optional[SpendGuard] = None) -> dict:
    """Run one turn at {"llm": 1.0}, which is where 3.5.1 puts every turn.

    A3, A7 and B7 all reach a model through this one line, and none of them
    holds a backend object or a key: what crosses is the request `llm_turn`
    documents. Under Ray the node is dispatched and holds an `llm` slot, which
    is what caps the campaign's concurrent prompts at the container count
    (FR-14.5); with no Ray running there is no cluster to dispatch to and the
    same node runs in this process, which is what a driver-less replay and an
    offline synthesis do.

    *guard* is W1's pre-authorisation and is the LAST thing between the loop and
    a model request: this is the one function every turn of the campaign passes
    through, so it is where a turn can still be refused for free. It is optional
    because the offline mutator synthesis precedes the registration commit and
    has no ledger to be authorised against (8.3).

    Returns:
        `llm_turn`'s dict, whichever way it ran.
    Worker:
        the `llm` worker under Ray; the caller's process without one.
    Raises:
        SpendCapRefused before anything is sent, when *guard* refuses; whatever
        the backend raises, unchanged, after that.
    """
    if guard is not None:
        guard.authorise(prompt)
    request = {"system_message": system_message, "prompt": prompt,
               "tools": tool_endpoints(tools), "stage": stage,
               "timeout_seconds": int(timeout_seconds), "model_id": model_id}
    if ray.is_initialized():
        return get(llm_turn.chia_remote(request))
    return llm_turn._chia_original(request)


# ---------------------------------------------------------------------------
# 7.1 The output contract
# ---------------------------------------------------------------------------

_JSON_BLOCK = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)


class PromptContractError(Exception):
    """A turn's output did not end in the fenced json block 7.1 demands."""


def parse_json_footer(text: str, required: tuple) -> dict:
    """Parse the LAST fenced json block of a turn's output (7.1).

    The last block wins, which is CHIA's own rule for its DECISION footer
    (`chia:examples/circt_issue_solver/issue_task.py:28-29`): a model that
    reconsiders mid-answer leaves both blocks and the final one is the answer.
    `_JSON_BLOCK` is non-greedy, so `finditer` yields every block in order and
    the body is the LAST match's group; `re.search` would yield the first and
    would be the opposite rule.

    Returns:
        dict, the decoded object, carrying every key in *required*.
    Worker:
        pure; it runs in whichever process read the turn's output.
    Raises:
        PromptContractError(reason) with reason one of "no_block", "not_json",
        "not_object" or "missing:<key>". Nothing else.
    """
    blocks = list(_JSON_BLOCK.finditer(text or ""))
    if not blocks:
        raise PromptContractError("no_block")
    try:
        decoded = json.loads(blocks[-1].group("body"))
    except (ValueError, TypeError):
        raise PromptContractError("not_json") from None
    if not isinstance(decoded, dict):
        raise PromptContractError("not_object")
    for key in required:
        if key not in decoded:
            raise PromptContractError(f"missing:{key}")
    return decoded


__all__ = ["MODEL_BACKEND", "MAX_OUTPUT_TOKENS", "CHARS_PER_TOKEN",
           "LiveModelRefused", "PromptContractError", "SpendCapRefused",
           "SpendGuard", "ToolEndpoint", "build_llm", "dispatch_turn",
           "llm_turn", "parse_json_footer", "require_live_model",
           "tool_endpoints", "turn_usage", "worker_env"]
