"""The two patches `upstream/` carries against CHIA, applied and exercised.

`upstream/issue_task-vertex-branch.patch` and `upstream/vertex-usage.patch` are
edits to CHIA's own files, not to this tree, so nothing else in this suite can
see them break. The driver stages both into the shipped package at startup
(`red-team-code-disposition.md` rows K3/K11), which means a patch that has gone
stale against CHIA is a campaign that will not start. These tests apply both to
a throwaway copy of the two files taken from `~/.cache/chia-src` at the pinned
commit, and then run the patched `vertex.py` against a fake `google.genai`
client to assert the two behaviours the patch exists for:

* **K11** — `thoughts_token_count` and `tool_use_prompt_token_count` are billed
  and are separate fields from `candidates_token_count` / `prompt_token_count`;
  unpatched CHIA sums neither, so every priced turn is understated.
* **K10** — a turn that raises after N `generate_content` calls leaves
  `_last_metadata` empty, and a caller that defaults a missing count to 0 then
  prices that turn at 0.0. The patch finalises the counts in a `finally`.

The patched module is imported from the temporary copy under a private name:
the installed `chia` is never written to and never shadowed. Tier 0 (a local
`git show`, a fake client; no network, no model, no clone of our own), skipped
when the CHIA checkout is absent.
"""
import ast
import importlib.util
import subprocess
from pathlib import Path

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
    """The patched `chia/models/vertex.py`, imported under a private name.

    Module-scoped: applying the patch and importing the module once is enough,
    and every test here constructs its own `VertexGeminiLLM`.
    """
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
    """Patch `genai.Client` so the loop consumes *replies* in order.

    A reply that is an exception instance is raised instead of returned, which
    is what `conftest.fake_vertex` and CHIA's own `_install_fake_genai` cannot
    do and is exactly the case K10 is about. Returns the call log.
    """
    from google import genai

    calls = []

    class _FakeModels:
        def generate_content(self, *, model, contents, config):
            calls.append(model)
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
    """T-U-upstream-01 (FR-19.2, K3/K11): both patches apply at the pinned commit.

    `--check` first, so a stale patch is reported as such and not as a
    half-applied file, and the patched `vertex.py` then parses. Fixture: the
    two files from `~/.cache/chia-src` at `16c35e92`. Tier 0.
    """
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
    """T-U-upstream-02 (K11): the two billed fields CHIA does not sum reach `_last_metadata`.

    One mocked `generate_content` whose usage sets all four counts. Unpatched,
    `thoughts_token_count` and `tool_use_prompt_token_count` are dropped on the
    floor and the turn is priced short by both. Fixture: a fake `genai.Client`.
    Tier 0.
    """
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
    """T-U-upstream-03 (K10): a turn that raises still reports what it consumed.

    The first reply is a `function_call` for a tool that was never advertised,
    which drives the loop around a second time without any MCP server; the
    second `generate_content` raises. The counts observed before the raise
    survive, so the ledger prices a failed turn from a real measurement instead
    of defaulting the absent counts to zero. The exception still propagates.
    Fixture: a fake `genai.Client`. Tier 0.
    """
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
    """Two replies: a tool call whose RESULT is huge, then a second answer.

    The first grows the conversation past any small ceiling, which is the
    quadratic growth errata row 38 is about; the second is what a loop with no
    ceiling goes on to send. A fresh list per call, because the fake client
    pops from the one it is given.
    """
    return [
        _response(types.Part(function_call=types.FunctionCall(
            name="calc__run", args={"x": "y" * 400_000})),
            _usage(prompt=10, candidates=5, thoughts=7, tool_use=3)),
        _response(types.Part(text="NEVER SENT"), _usage(prompt=1)),
    ]


@pytest.mark.t0
def test_T_U_upstream_04_the_turn_budget_stops_the_loop_mid_way(monkeypatch,
                                                                patched_vertex):
    """T-U-upstream-04 (errata row 38): the ceiling fires BEFORE the call it refuses.

    W-18 measured the cost of not having this: three turns made 14, 21 and 37
    `generate_content` calls, each re-sending the whole conversation, and cost
    19.7x, 32.3x and 64.1x what the caller had authorised. Here the first call
    is allowed, its tool result grows the conversation, and the second is
    refused before it is sent - so the money it would have cost is not spent -
    while `_last_metadata` still reports what the first one billed (K10).
    Fixture: a fake `genai.Client`. Tier 0.
    """
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

    # The same conversation with NO ceiling runs to the end, which is CHIA's
    # own behaviour and is what a `turn_budget_usd` of None preserves.
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
    """T-U-upstream-05 (errata row 38): `prompt()` propagates it, it does not retry.

    `prompt()` resets the accumulated counts at the top of every attempt, so a
    retry would restart the whole tool loop with a clean slate and spend the
    money the ceiling just refused - three times over, `retries` being 3. The
    refusal therefore sits with the other never-retry errors. The profiler is
    stubbed because `prompt` is a `@ChiaFunction` and `get_profiler()` starts a
    local Ray where none is running (`04-Test-Plan.md` §0.4). Fixture: a fake
    `genai.Client`. Tier 0.
    """
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
    """T-U-upstream-06 (errata row 37): a Ray call that never returns is given up on.

    MEASURED, W-12c: with `/tmp/ray/ray_current_cluster` naming a cluster that
    is down, `ray.get_runtime_context()` retries the GCS five seconds at a time
    and the `try/except` around it cannot catch a call that does not return. The
    first live attempt of the project sat twelve minutes inside it and was
    killed, taking that turn's token counts with it. All four callers are on
    error paths, so a 429 met on such a machine hung the whole campaign.
    Fixture: a `ray.get_runtime_context` that never returns. Tier 0.
    """
    import threading
    import time

    released = threading.Event()

    def _never():
        released.wait(30)
        raise AssertionError("the bound should have answered long before this")

    llm = patched_vertex.VertexGeminiLLM(model="gemini-3.8-flash")

    # First guard: a process with no Ray in it does not ask Ray anything.
    # Without it the call blocks sixty seconds and then Ray's own client calls
    # QuickExit - "Failed to connect to GCS within 60 seconds ... The program
    # will terminate." - which no worker thread can be rescued from. MEASURED,
    # W-18b, while writing this test: it killed the pytest process.
    monkeypatch.setattr(patched_vertex.ray, "is_initialized", lambda: False)
    monkeypatch.setattr(patched_vertex.ray, "get_runtime_context",
                        lambda: pytest.fail("asked Ray with no Ray running"))
    assert llm._get_node_id() == "unknown"

    # Second guard, for a cluster that dies UNDER a live driver, where the
    # first does not apply: the call is given up on rather than waited out.
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
