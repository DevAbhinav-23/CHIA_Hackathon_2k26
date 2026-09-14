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
