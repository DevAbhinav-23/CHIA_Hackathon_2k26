"""The one neutral module both halves import (03-LLD.md 3.5.1)."""
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


#: RunManifest.backend.
MODEL_BACKEND = "vertex"

_LIVE_MODEL_ENV = "BUGLOOP_ALLOW_LIVE_MODEL"
_API_KEY_ENV = "GEMINI_API_KEY"


class LiveModelRefused(RuntimeError):
    """A real model backend was asked for without the live-call interlock set."""


def require_live_model(purpose: str, *, need_key: bool = True,
                       env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Refuse to set up a live model turn unless the interlock allows one."""
    if env is None:
        env = os.environ
    if env.get(_LIVE_MODEL_ENV) != "1":
        raise LiveModelRefused(
            f"refusing to set up a live model turn for {purpose}: "
            f"set {_LIVE_MODEL_ENV}=1 to allow a real model request "
            "(03-LLD.md 3.5.1; ADR-D-03, superseding section and addendum)")
    if not need_key:
        return None
    key = (env.get(_API_KEY_ENV) or "").strip()
    # An UNEXPANDED reference is a literal, not an empty value.
    if not key or key.startswith("${"):
        raise LiveModelRefused(
            f"{_API_KEY_ENV} is unset, empty or an unexpanded reference on "
            f"{socket.gethostname()}: the cluster YAML passes it with -e and the "
            "operator sources ~/.config/bugloop/gemini.env before `chia up` (11.2)")
    return key


def build_llm(system_message: str, timeout_seconds: int, model_id: str, *,
              env: Optional[Mapping[str, str]] = None,
              max_tool_iterations: Optional[int] = None,
              max_output_tokens: Optional[int] = None,
              turn_budget_usd: Optional[float] = None,
              final_tool_names: Optional[list] = None,
              final_tool_iterations: Optional[int] = None):
    """Build the campaign backend, refusing to reach the network unbidden."""
    from chia.models.vertex import VertexGeminiLLM

    key = require_live_model(f"{MODEL_BACKEND}:{model_id}", env=env)
    extra = {}
    if max_tool_iterations is not None:
        extra["max_tool_iterations"] = int(max_tool_iterations)
    if max_output_tokens is not None:
        extra["max_tokens"] = int(max_output_tokens)
    if turn_budget_usd is not None:
        extra["turn_budget_usd"] = float(turn_budget_usd)
    if final_tool_names:
        extra["final_tool_names"] = list(final_tool_names)
        extra["final_tool_iterations"] = int(final_tool_iterations or 0)
    llm = VertexGeminiLLM(
        model=model_id,
        system_message=system_message,
        timeout_seconds=timeout_seconds,
        project=None,
        location=None,
        **extra,
        client_kwargs={"api_key": key,
                       "http_options": {"timeout": int(timeout_seconds * 1000)}},
    )
    # Express mode takes an API key and NO project and NO location.
    llm.project = None
    llm.location = None
    return llm


@dataclasses.dataclass(frozen=True)
class ToolEndpoint:
    """Where one `ChiaTool`'s MCP server answers, and nothing else about it."""
    name: str
    hostname: str
    port: int
    node_id: Optional[str] = None


def tool_endpoints(tools) -> list:
    """The `ToolEndpoint` of every tool in *tools*, in order."""
    return [ToolEndpoint(name=tool.name, hostname=tool.hostname,
                         port=getattr(tool, "port", 8000),
                         node_id=getattr(tool, "node_id", None))
            for tool in tools or []]


#: What CHIA's Vertex backend caps ONE `generate_content` call's output at.
MAX_OUTPUT_TOKENS = 16000

#: The stages whose cap is not the default. Stage 2 writes up to
#: `per_seed_probe_cap` whole programs plus its json footer in ONE response and
#: MEASURED, campaign 1 seed 1, it was truncated at 16,000 and the turn raised.
#: Every other stage answers in prose or one small json block.
MAX_OUTPUT_TOKENS_BY_STAGE = {"stage_2": 32000}


def stage_max_output_tokens(stage: str) -> int:
    """The output cap one stage's turn is given, and priced at."""
    return int(MAX_OUTPUT_TOKENS_BY_STAGE.get(stage, MAX_OUTPUT_TOKENS))

#: Characters per token, for the pre-authorisation only.
CHARS_PER_TOKEN = 2.0

#: USD per million CACHED input tokens for `gemini-3.8-flash`, VERIFIED
#: 2026-09-15 on https://ai.google.dev/gemini-api/docs/pricing - "$0.075
#: through December 31, 2026. $0.15 starting January 1, 2027." - which is the
#: same page budget.yaml's two registered rates are verified against.
#:
#: NOTHING PRICES ANYTHING AT IT. `cloud.google.com/vertex-ai/generative-ai/
#: pricing` could not be read (its table is not in the fetched document), and
#: budget.yaml registers exactly TWO rates: a third one in the ledger's
#: arithmetic would change a registered campaign parameter after registration
#: (FR-14.7). `cached_tokens` is RECORDED and every input token is still priced
#: at the list rate, so the ledger over-states and never under-states - the safe
#: direction for a cap. `results.md` says so and says how many tokens were cached.
CACHED_INPUT_RATE_USD_PER_M = 0.075

#: The tokens ONE tool result may add to the conversation, which is the read
#: cap of `generate_task.SOURCE_READ_CAP_BYTES` at `CHARS_PER_TOKEN`.
TOOL_OUTPUT_TOKENS_CAP = 32768

_NO_TOOL_ITERATIONS = 1


#: The tool calls one turn may make when no cap is registered for its stage,
#: which is the patched backend's own `max_tool_iterations` default.
DEFAULT_TOOL_ITERATIONS = 100


def tool_iterations(cfg: Mapping, stage: str) -> int:
    """The registered tool-loop cap of *stage*, or the backend's own default."""
    return int((cfg.get("max_tool_iterations") or {}).get(stage)
               or DEFAULT_TOOL_ITERATIONS)


class SpendCapRefused(RuntimeError):
    """A turn was refused because its worst case would reach the USD cap (W1)."""


@dataclasses.dataclass
class SpendGuard:
    """The money a turn is authorised against, BEFORE it is dispatched (W1)."""
    cap_usd: float
    spend_usd: float
    price_usd_per_m_input_tokens: float
    price_usd_per_m_output_tokens: float
    max_output_tokens: int = MAX_OUTPUT_TOKENS
    settled_usd: float = 0.0
    _in_flight: dict = dataclasses.field(default_factory=dict)
    _turns: int = 0

    @property
    def in_flight_usd(self) -> float:
        """What the turns authorised but not yet settled still hold (D-5)."""
        return round(sum(self._in_flight.values()), 6)

    def iterations(self, request: Mapping) -> int:
        """The `generate_content` calls *request* may make: `n` in the formula."""
        if not request.get("tools"):
            return _NO_TOOL_ITERATIONS
        # The reading phase, then the write phase a turn whose deliverable is a
        # tool call asks for, then the final answer: one call more than both.
        write = (int(request.get("final_tool_iterations") or 0)
                 if request.get("final_tool_names") else 0)
        return max(1, int(request.get("max_tool_iterations") or 1)) + write + 1

    def worst_case_usd(self, request: Mapping) -> float:
        """The most the whole turn *request* can cost, at the two prices."""
        n = self.iterations(request)
        prompt_chars = (len(request.get("prompt") or "")
                        + len(request.get("system_message") or ""))
        prompt_tokens = prompt_chars / CHARS_PER_TOKEN
        tokens_in = sum(prompt_tokens + i * TOOL_OUTPUT_TOKENS_CAP
                        for i in range(n))
        # The STAGE's cap, which is the one its backend is built with.
        tokens_out = n * int(request.get("max_output_tokens")
                             or self.max_output_tokens)
        return round(
            tokens_in / 1e6 * self.price_usd_per_m_input_tokens
            + tokens_out / 1e6 * self.price_usd_per_m_output_tokens, 6)

    def authorise(self, request: Mapping) -> tuple:
        """Authorise one turn against settled spend plus what is in flight, or refuse it."""
        worst = self.worst_case_usd(request)
        spent = self.spend_usd + self.settled_usd
        total = spent + self.in_flight_usd + worst
        if total >= self.cap_usd:
            raise SpendCapRefused(
                f"refusing the turn: USD {spent:.4f} spent plus "
                f"{self.in_flight_usd:.4f} in flight plus a worst case "
                f"of {worst:.4f} reaches campaign_spend_cap_usd "
                f"{self.cap_usd:.4f} (FR-18.10, W1)")
        self._turns += 1
        self._in_flight[self._turns] = worst
        return self._turns, worst

    def settle(self, handle: int, billed_usd: Optional[float]) -> float:
        """Settle turn *handle* at its bill, or at its whole authorisation when none was observed.

        A turn that raised after its calls may have been billed for them, so an
        unobserved turn keeps the worst case rather than releasing it (D-5).
        """
        if handle not in self._in_flight:
            raise KeyError(f"turn {handle!r} is not in flight: it settled already")
        authorised = self._in_flight.pop(handle)
        settled = authorised if billed_usd is None else float(billed_usd)
        self.settled_usd = round(self.settled_usd + settled, 6)
        return settled

    def billed_usd(self, usage: Mapping) -> Optional[float]:
        """What a finished turn cost, at this guard's own two prices."""
        tokens_in, tokens_out = usage.get("tokens_in"), usage.get("tokens_out")
        if tokens_in is None or tokens_out is None:
            return None
        return round(tokens_in / 1e6 * self.price_usd_per_m_input_tokens
                     + tokens_out / 1e6 * self.price_usd_per_m_output_tokens, 6)


def worker_env() -> Mapping[str, str]:
    """The environment `llm_turn` builds its client from: the LLM WORKER's own."""
    return os.environ


@ChiaFunction(resources={"llm": 1.0}, max_retries=0)
def llm_turn(request: dict) -> dict:
    """Build the backend HERE and run one model turn, bringing its counts home.

    Returns:
        {"result": str, "stream": str, "stderr": str, "success": bool, "usage": `turn_usage`'s dict, "counters": CounterBlock}.
    Worker:
        {"llm": 1.0}; the MCP tool servers stay where their own task_options put them and.
    Raises:
        LiveModelRefused when this worker carries neither the interlock nor a usable key.
    """
    started = time.monotonic()
    stage = request.get("stage", "stage_2")
    llm = build_llm(request["system_message"], int(request["timeout_seconds"]),
                    request["model_id"], env=worker_env(),
                    max_tool_iterations=request.get("max_tool_iterations"),
                    max_output_tokens=request.get("max_output_tokens"),
                    turn_budget_usd=request.get("turn_budget_usd"),
                    final_tool_names=request.get("final_tool_names"),
                    final_tool_iterations=request.get("final_tool_iterations"))
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
    """One turn's billed token counts, or nulls when none were observed."""
    meta = dict(metadata or {})
    # The patched backend publishes `input_tokens` on every path that ran at all.
    if "input_tokens" not in meta:
        return {"tokens_in": None, "tokens_out": None, "thinking_tokens": None,
                "tool_use_prompt_tokens": None, "cached_tokens": None,
                "num_turns": meta.get("num_turns", 0),
                "model": meta.get("model"), "observed": False}
    thinking = int(meta.get("thinking_tokens") or 0)
    tool_use = int(meta.get("tool_use_prompt_tokens") or 0)
    # A SUBSET of `tokens_in`, already counted in it at the list input rate:
    # this loop prices no third rate, so the ledger is an UPPER BOUND by
    # whatever the cached discount would have been (see CACHED_INPUT_RATE).
    return {"tokens_in": int(meta.get("input_tokens") or 0) + tool_use,
            "tokens_out": int(meta.get("output_tokens") or 0) + thinking,
            "thinking_tokens": thinking, "tool_use_prompt_tokens": tool_use,
            "cached_tokens": int(meta.get("cached_tokens") or 0),
            "num_turns": meta.get("num_turns", 0), "model": meta.get("model"),
            "observed": True}


def dispatch_turn(system_message: str, prompt: str, tools: list, *, stage: str,
                  timeout_seconds: int, model_id: str,
                  guard: Optional[SpendGuard] = None,
                  max_tool_iterations: Optional[int] = None,
                  final_tool_names: Optional[list] = None,
                  final_tool_iterations: int = 0) -> dict:
    """Run one turn at {"llm": 1.0}, which is where 3.5.1 puts every turn."""
    request = {"system_message": system_message, "prompt": prompt,
               "tools": tool_endpoints(tools), "stage": stage,
               "timeout_seconds": int(timeout_seconds), "model_id": model_id,
               "max_tool_iterations": max_tool_iterations,
               "max_output_tokens": stage_max_output_tokens(stage),
               "final_tool_names": list(final_tool_names or []),
               "final_tool_iterations": int(final_tool_iterations)}
    handle = authorised = ceiling = billed = None
    if guard is not None:
        handle, authorised = guard.authorise(request)
        ceiling = authorised
        request["turn_budget_usd"] = ceiling
    failure = None
    try:
        out = (get(llm_turn.chia_remote(request)) if ray.is_initialized()
               else llm_turn._chia_original(request))
        usage = dict(out.get("usage") or {})
        billed = guard.billed_usd(usage) if guard is not None else None
    except BaseException as error:
        failure = error
        raise
    finally:
        # A turn that raised settles at its authorisation, not at nothing (D-5).
        settled = None if guard is None else guard.settle(handle, billed)
        if failure is not None:
            # The settlement dies with this process otherwise and the ledger
            # prices a raised turn at null, which is nothing (D-7).
            try:
                failure.turn_usage = dict(
                    turn_usage(None), authorised_usd=authorised,
                    ceiling_usd=ceiling, billed_usd=None, settled_usd=settled,
                    calls=None, failed=type(failure).__name__)
            except Exception:       # an exception that carries no attributes
                pass
    usage.update(authorised_usd=authorised, ceiling_usd=ceiling,
                 billed_usd=billed, settled_usd=settled,
                 calls=usage.get("num_turns"))
    out["usage"] = usage
    return out


_JSON_BLOCK = re.compile(r"```json\s*\n(?P<body>.*?)\n```", re.DOTALL)


class PromptContractError(Exception):
    """A turn's output did not end in the fenced json block 7.1 demands."""


def parse_json_footer(text: str, required: tuple) -> dict:
    """Parse the LAST fenced json block of a turn's output (7.1)."""
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


__all__ = ["MODEL_BACKEND", "MAX_OUTPUT_TOKENS", "MAX_OUTPUT_TOKENS_BY_STAGE",
           "CHARS_PER_TOKEN", "stage_max_output_tokens",
           "TOOL_OUTPUT_TOKENS_CAP", "DEFAULT_TOOL_ITERATIONS", "tool_iterations",
           "LiveModelRefused", "PromptContractError", "SpendCapRefused",
           "SpendGuard", "ToolEndpoint", "build_llm", "dispatch_turn",
           "llm_turn", "parse_json_footer", "require_live_model",
           "tool_endpoints", "turn_usage", "worker_env"]
