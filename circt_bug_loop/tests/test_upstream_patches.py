"""The two patches `upstream/` carries against CHIA, applied and exercised."""
import ast
import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from google.genai import types

pytestmark = pytest.mark.t0

REPO = Path(__file__).resolve().parents[2]
UPSTREAM = REPO / "upstream"
CHIA_SRC = Path.home() / ".cache" / "chia-src"

#: The CHIA commit both patches are written against (`upstream/README.md`).
COMMIT = "16c35e92"

#: patch file -> the CHIA file it edits, repository-relative.
PATCHES = {
    "issue_task-vertex-branch.patch": "examples/circt_issue_solver/issue_task.py",
    "vertex-usage.patch": "chia/models/vertex.py",
}


def _copy_out(tmp_path: Path) -> Path:
    """Write CHIA's two unpatched files into *tmp_path* at their own paths."""
    if not (CHIA_SRC / ".git").is_dir():
        pytest.skip(f"no CHIA checkout at {CHIA_SRC}")
    for rel in PATCHES.values():
        blob = subprocess.run(
            ["git", "-C", str(CHIA_SRC), "show", f"{COMMIT}:{rel}"],
            capture_output=True)
        assert blob.returncode == 0, blob.stderr.decode()
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob.stdout)
    return tmp_path


def _git_apply(tree: Path, name: str, *flags: str) -> subprocess.CompletedProcess:
    """`git apply` one of `upstream/`'s patches inside *tree* (not a checkout)."""
    return subprocess.run(["git", "apply", *flags, str(UPSTREAM / name)],
                          cwd=tree, capture_output=True, text=True)


@pytest.fixture(scope="module")
def patched_vertex(tmp_path_factory):
    """The patched `chia/models/vertex.py`, imported under a private name."""
    tree = _copy_out(tmp_path_factory.mktemp("chia-at-16c35e92"))
    applied = _git_apply(tree, "vertex-usage.patch")
    assert applied.returncode == 0, applied.stderr
    spec = importlib.util.spec_from_file_location(
        "_bugloop_patched_vertex", tree / PATCHES["vertex-usage.patch"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _usage(prompt=0, candidates=0, thoughts=0, tool_use=0):
    return types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt,
        candidates_token_count=candidates,
        thoughts_token_count=thoughts,
        tool_use_prompt_token_count=tool_use,
        total_token_count=prompt + candidates + thoughts + tool_use,
    )


def _response(part, usage):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(role="model", parts=[part]),
            finish_reason=types.FinishReason.STOP,
        )],
        usage_metadata=usage,
    )


def _install_fake_genai(monkeypatch, replies):
    """Patch `genai.Client` so the loop consumes *replies* in order."""
    from google import genai

    calls = []

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            calls.append({"model": model, "contents": list(contents),
                          "config": config})
            reply = replies.pop(0)
            if isinstance(reply, BaseException):
                raise reply
            return reply

    class _FakeClient:
        def __init__(self, **kwargs):
            self.models = _FakeModels()

    monkeypatch.setattr(genai, "Client", lambda **kwargs: _FakeClient(**kwargs))
    return calls


@pytest.mark.t0
def test_T_U_upstream_01_both_patches_apply(tmp_path: Path):
    """T-U-upstream-01 (FR-19.2): both patches apply at the pinned commit."""
    tree = _copy_out(tmp_path)
    for name in PATCHES:
        checked = _git_apply(tree, name, "--check")
        assert checked.returncode == 0, f"{name}: {checked.stderr}"
        applied = _git_apply(tree, name)
        assert applied.returncode == 0, f"{name}: {applied.stderr}"

    vertex = (tree / PATCHES["vertex-usage.patch"]).read_text(encoding="utf-8")
    ast.parse(vertex)
    issue_task = (tree / PATCHES["issue_task-vertex-branch.patch"]).read_text(
        encoding="utf-8")
    ast.parse(issue_task)
    assert 'elif backend == "vertex":' in issue_task
    # The patch is additive: it touches neither existing sum.
    assert vertex.count('meta["input_tokens"] +=') == 1
    assert vertex.count('meta["output_tokens"] +=') == 1


@pytest.mark.t0
def test_T_U_upstream_02_thinking_tokens_are_counted(monkeypatch, patched_vertex):
    """T-U-upstream-02 (K11): the two billed fields CHIA does not sum reach `_last_metadata`."""
    calls = _install_fake_genai(monkeypatch, [_response(
        types.Part(text="PONG"),
        _usage(prompt=10, candidates=5, thoughts=7, tool_use=3))])

    llm = patched_vertex.VertexGeminiLLM(
        model="gemini-2.0-flash-001", project="p", location="us-central1")
    result = llm._run_generate("ping", [])

    assert result.result == "PONG" and len(calls) == 1
    assert llm._last_metadata == {
        "input_tokens": 10, "output_tokens": 5,
        "thinking_tokens": 7, "tool_use_prompt_tokens": 3, "num_turns": 1,
    }


@pytest.mark.t0
def test_T_U_upstream_03_failed_turn_keeps_its_counts(monkeypatch, patched_vertex):
    """T-U-upstream-03 (K10): a turn that raises still reports what it consumed."""
    boom = RuntimeError("connection reset")
    calls = _install_fake_genai(monkeypatch, [
        _response(types.Part(function_call=types.FunctionCall(name="calc__run",
                                                              args={"x": 21})),
                  _usage(prompt=10, candidates=5, thoughts=7, tool_use=3)),
        boom,
    ])

    llm = patched_vertex.VertexGeminiLLM(
        model="gemini-2.0-flash-001", project="p", location="us-central1")
    with pytest.raises(Exception) as raised:
        llm._run_generate("ping", [])

    assert len(calls) == 2
    assert raised.value is boom or raised.value.__cause__ is boom
    assert llm._last_metadata == {
        "input_tokens": 10, "output_tokens": 5,
        "thinking_tokens": 7, "tool_use_prompt_tokens": 3, "num_turns": 1,
    }


def _budget_replies():
    """Two replies: a tool call whose RESULT is huge, then a second answer."""
    return [
        _response(types.Part(function_call=types.FunctionCall(
            name="calc__run", args={"x": "y" * 400_000})),
            _usage(prompt=10, candidates=5, thoughts=7, tool_use=3)),
        _response(types.Part(text="NEVER SENT"), _usage(prompt=1)),
    ]


@pytest.mark.t0
def test_T_U_upstream_04_the_turn_budget_stops_the_loop_mid_way(monkeypatch,
                                                                patched_vertex):
    """T-U-upstream-04 (errata row 38): the ceiling fires BEFORE the call it refuses."""
    calls = _install_fake_genai(monkeypatch, _budget_replies())

    llm = patched_vertex.VertexGeminiLLM(
        model="gemini-3.8-flash", project="p", location="us-central1",
        turn_budget_usd=0.10)
    with pytest.raises(patched_vertex.TurnBudgetExceeded) as raised:
        llm._run_generate("ping", [])

    assert len(calls) == 1, "the second call was refused, not made"
    error = raised.value
    assert error.budget_usd == 0.10
    assert error.estimate_usd > 0.10 and error.spent_usd >= 0.0
    assert "turn_budget_usd" in error.raw_message
    # K10 still holds: the counts of the call that DID run survive the raise.
    assert llm._last_metadata["input_tokens"] == 10
    assert llm._last_metadata["num_turns"] == 1

    # The same conversation with NO ceiling runs to the end.
    calls = _install_fake_genai(monkeypatch, _budget_replies())
    free = patched_vertex.VertexGeminiLLM(
        model="gemini-3.8-flash", project="p", location="us-central1")
    assert free.turn_budget_usd is None
    assert free._run_generate("ping", []).result == "NEVER SENT"
    assert len(calls) == 2

    # A ceiling the whole conversation fits under changes nothing either.
    calls = _install_fake_genai(monkeypatch, _budget_replies())
    roomy = patched_vertex.VertexGeminiLLM(
        model="gemini-3.8-flash", project="p", location="us-central1",
        turn_budget_usd=1000.0)
    assert roomy._run_generate("ping", []).result == "NEVER SENT"
    assert len(calls) == 2


@pytest.mark.t0
def test_T_U_upstream_05_the_budget_refusal_is_never_retried(monkeypatch,
                                                             patched_vertex):
    """T-U-upstream-05 (errata row 38): `prompt()` propagates it, it does not retry."""
    from chia.trace import profiler as profiler_module

    monkeypatch.setattr(profiler_module, "get_profiler",
                        lambda: type("P", (), {"enabled": False})())
    calls = _install_fake_genai(monkeypatch, _budget_replies())
    llm = patched_vertex.VertexGeminiLLM(
        model="gemini-3.8-flash", project="p", location="us-central1",
        turn_budget_usd=0.10)
    assert llm.retries == 3
    with pytest.raises(patched_vertex.TurnBudgetExceeded):
        llm.prompt._chia_original(llm, "ping", [])
    assert len(calls) == 1, "one attempt, not three"


@pytest.mark.t0
def test_T_U_upstream_06_get_node_id_is_bounded(monkeypatch, patched_vertex):
    """T-U-upstream-06 (errata row 37): a Ray call that never returns is given up on."""
    import threading
    import time

    released = threading.Event()

    def _never():
        released.wait(30)
        raise AssertionError("the bound should have answered long before this")

    llm = patched_vertex.VertexGeminiLLM(model="gemini-3.8-flash")

    # First guard: a process with no Ray in it does not ask Ray anything.
    monkeypatch.setattr(patched_vertex.ray, "is_initialized", lambda: False)
    monkeypatch.setattr(patched_vertex.ray, "get_runtime_context",
                        lambda: pytest.fail("asked Ray with no Ray running"))
    assert llm._get_node_id() == "unknown"

    # Second guard, for a cluster that dies UNDER a live driver, where the first does not apply.
    monkeypatch.setattr(patched_vertex, "NODE_ID_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(patched_vertex.ray, "is_initialized", lambda: True)
    monkeypatch.setattr(patched_vertex.ray, "get_runtime_context", _never)
    started = time.monotonic()
    assert llm._get_node_id() == "unknown"
    elapsed = time.monotonic() - started
    released.set()
    assert elapsed < 5.0, f"the call was not bounded: {elapsed:.1f}s"

    # And the real answer still comes back when Ray does answer.
    monkeypatch.setattr(
        patched_vertex.ray, "get_runtime_context",
        lambda: type("Ctx", (), {"get_node_id": staticmethod(lambda: "n0de")})())
    assert llm._get_node_id() == "n0de"
    # The committed bound is ten seconds, which is the patch's own constant.
    patch = (UPSTREAM / "vertex-usage.patch").read_text(encoding="utf-8")
    assert "+NODE_ID_TIMEOUT_SECONDS = 10.0" in patch


def _install_fake_mcp(monkeypatch):
    """One MCP tool server that always answers, so the loop declares a tool."""
    import mcp
    import mcp.client.streamable_http as http

    class _Transport:
        async def __aenter__(self):
            return (None, None, None)

        async def __aexit__(self, *exception):
            return False

    class _Session:
        def __init__(self, read, write):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exception):
            return False

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(
                name="read_file", description="read one file",
                inputSchema={"type": "object",
                             "properties": {"path": {"type": "string"}}})])

        async def call_tool(self, name, arguments):
            return SimpleNamespace(isError=False,
                                   content=[SimpleNamespace(text="SOURCE")])

    monkeypatch.setattr(http, "streamable_http_client", lambda url: _Transport())
    monkeypatch.setattr(mcp, "ClientSession", _Session)
    return SimpleNamespace(name="source", hostname="127.0.0.1", port=8000)


@pytest.mark.t0
def test_T_U_upstream_07_an_exhausted_tool_loop_asks_for_an_answer(monkeypatch,
                                                                   patched_vertex):
    """T-U-upstream-07 (W-18e): the exhausted loop is told to answer, and cannot call."""
    tool = _install_fake_mcp(monkeypatch)
    reading = _response(
        types.Part(function_call=types.FunctionCall(name="source__read_file",
                                                    args={"path": "a.cpp"})),
        _usage(prompt=10, candidates=5))
    calls = _install_fake_genai(monkeypatch, [
        reading, reading,
        _response(types.Part(text="FINAL ANSWER"), _usage(prompt=40, candidates=9)),
    ])

    llm = patched_vertex.VertexGeminiLLM(
        model="gemini-3.8-flash", project="p", location="us-central1",
        system_message="be terse", max_tool_iterations=2)
    result = llm._run_generate("ping", [tool])

    # Exactly one call more than the loop's own iterations, and it is the last.
    assert len(calls) == llm.max_tool_iterations + 1 == 3
    assert calls[0]["config"].tools and calls[1]["config"].tools
    # The declarations STAY, so the history's function parts stay valid, and a
    # call is forbidden by the mode instead (W-18e D-1 hypothesis a).
    assert calls[2]["config"].tools, "the final answer keeps the declarations"
    assert (calls[2]["config"].tool_config.function_calling_config.mode
            == types.FunctionCallingConfigMode.NONE)
    assert calls[0]["config"].tool_config is None
    # Same system instruction, same conversation, grown by what the tools
    # returned and by the instruction to answer now.
    assert calls[2]["config"].system_instruction == "be terse"
    assert len(calls[2]["contents"]) > len(calls[0]["contents"])
    last = calls[2]["contents"][-1]
    assert last.role == "user"
    assert last.parts[0].text == (
        "Your tool calls for this turn are exhausted. Answer now, in exactly "
        "the format the instructions require, from what you have already read.")

    # The turn is no longer empty, and it says why it asked and what came back.
    assert result.result == "FINAL ANSWER"
    assert "Reached max_tool_iterations=2; final answer requested" in result.stream_result
    assert ("[DEBUG] final answer: finish=STOP, parts=['text']\n"
            in result.stream_result)
    assert "the final answer was empty" not in result.stream_result
    # The extra call is metered like every other.
    assert llm._last_metadata["num_turns"] == 3
    assert llm._last_metadata["input_tokens"] == 60
    assert llm._last_metadata["output_tokens"] == 19


@pytest.mark.t0
def test_T_U_upstream_08_a_truncated_final_answer_says_so(monkeypatch,
                                                          patched_vertex):
    """T-U-upstream-08 (W-18e): an empty final answer names its finish reason."""
    tool = _install_fake_mcp(monkeypatch)
    reading = _response(
        types.Part(function_call=types.FunctionCall(name="source__read_file",
                                                    args={"path": "a.cpp"})),
        _usage(prompt=10, candidates=5))
    truncated = types.GenerateContentResponse(
        candidates=[types.Candidate(
            content=types.Content(role="model",
                                  parts=[types.Part(text="hmm", thought=True)]),
            finish_reason=types.FinishReason.MAX_TOKENS,
        )],
        usage_metadata=_usage(prompt=40, thoughts=9),
    )
    _install_fake_genai(monkeypatch, [reading, truncated])

    llm = patched_vertex.VertexGeminiLLM(
        model="gemini-3.8-flash", project="p", location="us-central1",
        system_message="be terse", max_tool_iterations=1)
    result = llm._run_generate("ping", [tool])

    assert result.result == ""
    assert ("[DEBUG] final answer: finish=MAX_TOKENS, parts=['thought'] "
            "(truncated at max_output_tokens)\n" in result.stream_result)
    assert "[DEBUG] the final answer was empty" in result.stream_result
