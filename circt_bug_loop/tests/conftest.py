"""Shared configuration for the flow's tests (04-Test-Plan.md 0.3)."""
import os
from pathlib import Path

import pytest

from circt_bug_loop.contract import schema

#: `contract/fixtures/`, reached through the imported package rather than by walking up from __file__.
FIXTURES = Path(schema.__file__).resolve().parent / "fixtures"

#: `tests/fixtures/`, which is this package's own and is where §13's `secrets/known_values.txt` lives.
TEST_FIXTURES = Path(__file__).resolve().parent / "fixtures"

_INTERLOCK = "BUGLOOP_ALLOW_LIVE_MODEL"
_API_KEY = "GEMINI_API_KEY"


def known_values() -> dict:
    """§13's three synthetic credential strings, by the variable each shapes."""
    values = {}
    for line in (TEST_FIXTURES / "secrets" / "known_values.txt").read_text(
            encoding="utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        name, value = line.split()
        values[name] = value
    return values


def call_node(fn, *args, **kwargs):
    """Call a `@ChiaFunction`-decorated node's undecorated original, with no Ray."""
    return getattr(fn, "_chia_original", fn)(*args, **kwargs)


@pytest.fixture(scope="session", autouse=True)
def no_live_model() -> None:
    """§0.5's rule, both halves: refuse the interlock, and set a synthetic key."""
    assert _INTERLOCK not in os.environ, (
        f"{_INTERLOCK} is set; tiers T0 to T2 may not reach a model "
        "(04-Test-Plan.md 0.5). Unset it, or run the tier-3 suite deliberately.")
    synthetic = known_values()[_API_KEY]
    previous = os.environ.get(_API_KEY)
    os.environ[_API_KEY] = synthetic
    yield
    if previous is None:
        os.environ.pop(_API_KEY, None)
    else:
        os.environ[_API_KEY] = previous


@pytest.fixture(scope="session", autouse=True)
def no_local_ray():
    """Assert that no test of tiers T0 to T2 started a local Ray (0.4)."""
    yield
    if os.environ.get("BUGLOOP_CLUSTER") or os.environ.get("CHIA_LIVE_CLUSTER"):
        return
    import ray

    assert not ray.is_initialized(), (
        "a test started a local Ray: call every @ChiaFunction node through "
        "conftest.call_node (04-Test-Plan.md 0.4), which calls its "
        "_chia_original and leaves the decorator in place.")


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """The committed contract fixture directory."""
    return FIXTURES


def vertex_text_part(text: str):
    """One text part of a fake Gemini response, built from the real types."""
    from google.genai import types

    return types.Part(text=text)


def vertex_call_part(name: str, args: dict):
    """One `function_call` part, which is what drives the backend's tool loop."""
    from google.genai import types

    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def vertex_response(parts, finish: str = "STOP", in_tok: int = 0, out_tok: int = 0):
    """One real `GenerateContentResponse`, so the token fields are the genuine ones."""
    from google.genai import types

    return types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(role="model", parts=list(parts)),
            finish_reason=getattr(types.FinishReason, finish))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=in_tok, candidates_token_count=out_tok,
            total_token_count=in_tok + out_tok))


class _DisabledProfiler:
    """CHIA's profiler, off: `get_profiler` otherwise starts a local Ray (0.4)."""
    enabled = False

    def add_info(self, info: dict) -> None:
        """Accept and discard, as the disabled profiler does."""


@pytest.fixture
def fake_vertex(monkeypatch):
    """CHIA's own offline vertex harness, as one fixture (04-Test-Plan.md 0.3)."""
    capture = {"calls": [], "client_kwargs": None, "urls": [], "tool_calls": []}
    monkeypatch.setattr("chia.trace.profiler.get_profiler",
                        lambda *a, **k: _DisabledProfiler())

    def install(responses, tool_result_text: str = "42"):
        from types import SimpleNamespace

        import mcp
        import mcp.client.streamable_http as streamable_mod
        from google import genai

        pending = list(responses)

        class _FakeModels:
            def generate_content(self, *, model, contents, config):
                capture["calls"].append({"model": model,
                                         "contents": list(contents),
                                         "config": config})
                return pending.pop(0)

        class _FakeClient:
            def __init__(self, **kwargs):
                capture["client_kwargs"] = kwargs
                self.models = _FakeModels()

        monkeypatch.setattr(genai, "Client", lambda **kwargs: _FakeClient(**kwargs))

        class _FakeStreamCM:
            async def __aenter__(self):
                return (object(), object(), None)

            async def __aexit__(self, *exc):
                return False

        def _fake_streamable(url):
            capture["urls"].append(url)
            return _FakeStreamCM()

        class _FakeSession:
            def __init__(self, read, write):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def initialize(self):
                pass

            async def list_tools(self):
                return SimpleNamespace(tools=[SimpleNamespace(
                    name="read_file", description="read a file",
                    inputSchema={
                        "type": "object", "properties": {},
                        "$schema": "https://json-schema.org/draft/2020-12/schema",
                        "additionalProperties": False, "title": "x"})])

            async def call_tool(self, name, args):
                capture["tool_calls"].append((name, args))
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=tool_result_text)],
                    isError=False)

        monkeypatch.setattr(streamable_mod, "streamable_http_client", _fake_streamable)
        monkeypatch.setattr(mcp, "ClientSession", _FakeSession)
        return capture

    yield install, capture
