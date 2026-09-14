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

import json
import os
import re
import socket
from typing import Mapping, Optional

import ray
from chia.base.ChiaFunction import ChiaFunction, get

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
        the caller's; the object it returns is serialised to an `llm` worker by
        `llm_turn`.
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


@ChiaFunction(resources={"llm": 1.0}, max_retries=0)
def llm_turn(llm, user_message: str, tools: list) -> dict:
    """Run one model turn on an `llm` worker and bring its token counts home.

    Returns:
        {"result": str, "stream": str, "stderr": str, "success": bool,
         "usage": {"tokens_in": int, "tokens_out": int, "num_turns": int,
                   "model": str | None}}.
    Worker:
        {"llm": 1.0}; the MCP tool servers stay where their own task_options put
        them and are reached over HTTP from here.
    Raises:
        whatever the backend raises. A3, A7 and B7 each catch it and record it
        as their stage's turn failure (FR-04.8, FR-11.8).
    """
    # A DIRECT call, not llm.prompt.options(...).chia_remote(...): the vertex
    # backend accumulates its token counts on the LLM OBJECT
    # (chia:chia/models/vertex.py:479-482, 579) and returns a QueryResult that
    # carries none (chia:chia/base/llm_call.py:15-35), so a remote dispatch
    # would count on a copy that dies with the task and FR-14.6 would be
    # unsatisfiable. This node holds {"llm": 1.0} in that copy's place.
    cli = llm.prompt(user_message, tools)
    meta = dict(getattr(llm, "_last_metadata", {}) or {})
    return {"result": cli.result, "stream": cli.stream_result, "stderr": cli.stderr,
            "success": bool(getattr(cli, "success", False)),
            "usage": {"tokens_in": meta.get("input_tokens", 0),
                      "tokens_out": meta.get("output_tokens", 0),
                      "num_turns": meta.get("num_turns", 0),
                      "model": meta.get("model")}}


def dispatch_turn(llm, user_message: str, tools: list) -> dict:
    """Run one turn at {"llm": 1.0}, which is where 3.5.1 puts every turn.

    A3, A7 and B7 all reach a model through this one line. Under Ray the node
    is dispatched and holds an `llm` slot, which is what caps the campaign's
    concurrent prompts at the container count (FR-14.5); with no Ray running
    there is no cluster to dispatch to and the same node runs in this process,
    which is what a driver-less replay and an offline synthesis do.

    Returns:
        `llm_turn`'s dict, whichever way it ran.
    Worker:
        the `llm` worker under Ray; the caller's process without one.
    Raises:
        whatever the backend raises, unchanged.
    """
    if ray.is_initialized():
        return get(llm_turn.chia_remote(llm, user_message, tools))
    return llm_turn._chia_original(llm, user_message, tools)


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


__all__ = ["MODEL_BACKEND", "LiveModelRefused", "PromptContractError",
           "build_llm", "dispatch_turn", "llm_turn", "parse_json_footer",
           "require_live_model"]
