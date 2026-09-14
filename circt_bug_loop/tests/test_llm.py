"""`llm.py`, the one neutral module: `04-Test-Plan.md` §1.6 (03-LLD.md §3.5.1).

`T-U-gen-21` to `-25`, moved here from `test_generate_task.py` at the join with
the code they test: the interlock, the express-mode construction, the turn node
that brings the token counts home, and the tool loop, all offline. The two
generators stay in `test_generate_task.py` and the two `ChiaTool`s in
`test_tools.py`; §7.1's footer parser is `test_prompts.py`'s, which is where
`04-Test-Plan.md` §1.23 puts it.

**`BUGLOOP_ALLOW_LIVE_MODEL` is never set by anything in this file**, not even
inside `monkeypatch`, and neither is a stand-in name for it. The allow path is
exercised by handing `require_live_model` and `build_llm` an explicit `env`
mapping, which is architect's decision 2: the refusal, the key check and the
express construction all run against the real code, and the real variable stays
absent from this process for the whole session (`T-U-layout-08` (1), which the
join un-`xfail`s, and `conftest.no_live_model`, which asserts it).
"""
import ast
import inspect
import os
import textwrap
from pathlib import Path

import pytest

from circt_bug_loop import llm as llm_module
from circt_bug_loop.generate_task import ProbeWriteTool, SourceReadTool
from circt_bug_loop.llm import LiveModelRefused, build_llm, llm_turn
from circt_bug_loop.tests.conftest import (call_node, vertex_call_part,
                                           vertex_response, vertex_text_part)
# The throwaway git repository and the no-Ray tool construction are shared with
# the tool tests rather than built twice.
from circt_bug_loop.tests.test_tools import (throwaway_repo,  # noqa: F401
                                             tool_servers)

pytestmark = pytest.mark.filterwarnings(
    "ignore::pydantic_settings.exceptions.IncompleteFieldDefinitionWarning")

#: A synthetic key, which is not a credential and never leaves this process.
SYNTHETIC_KEY = "bugloop-synthetic-not-a-real-key"

MODEL_ID = "gemini-3.8-flash"

#: The interlock's ALLOW mapping. It is handed to `require_live_model` and to
#: `build_llm` as `env=`, so the refusal, the key check and the express
#: construction all run against the real code with the real variable absent from
#: this process (architect decision 2; `T-U-layout-08` (1) has no carve-out).
ALLOW_ENV = {"BUGLOOP_ALLOW_LIVE_MODEL": "1", "GEMINI_API_KEY": SYNTHETIC_KEY}


@pytest.fixture
def allow_worker_env(monkeypatch):
    """Let `llm_turn` build its client, without setting the real variable.

    Since K2 the turn node reads the LLM WORKER's own environment through
    `llm.worker_env`, which takes no argument precisely so that no request can
    carry a key (W7). Substituting that one function is how a test reaches the
    allow path while `BUGLOOP_ALLOW_LIVE_MODEL` stays absent from this process.
    """
    monkeypatch.setattr(llm_module, "worker_env", lambda: dict(ALLOW_ENV))


def turn_request(prompt: str, tools, *, stage: str = "stage_2",
                 timeout_seconds: int = 2400) -> dict:
    """The request `dispatch_turn` builds, for a test that calls the node."""
    return {"system_message": "be terse", "prompt": prompt,
            "tools": llm_module.tool_endpoints(tools), "stage": stage,
            "timeout_seconds": timeout_seconds, "model_id": MODEL_ID}


# ---------------------------------------------------------------------------
# 3.5.1 The backend, the interlock and the turn
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_gen_21_the_interlock_refuses_without_the_variable(monkeypatch):
    """T-U-gen-21 (NFR-08, NFR-06): five spellings refuse, and nothing is built.

    `google.genai.Client` is a sentinel that fails this test if it is called at
    all, so the assertion is that no client was BUILT and not merely that no
    request was sent. Only the exact string "1" proceeds.
    """
    from google import genai

    monkeypatch.setattr(genai, "Client", lambda **kwargs: pytest.fail(
        "a client was constructed with the interlock closed"))

    # (1) The DEFAULT env, which is the process environment: the variable is
    # absent for every tier below T3 and nothing in this tree sets it.
    assert llm_module._LIVE_MODEL_ENV not in os.environ
    with pytest.raises(LiveModelRefused) as raised:
        build_llm("system", 2400, MODEL_ID)
    assert llm_module._LIVE_MODEL_ENV in str(raised.value)
    assert "3.5.1" in str(raised.value)

    # (2) The four other spellings, through an explicit mapping, so that nothing
    # here writes the name into a process environment at all.
    name = llm_module._LIVE_MODEL_ENV
    for spelling in ("", "0", "true", "${" + name + "}"):
        with pytest.raises(LiveModelRefused):
            build_llm("system", 2400, MODEL_ID,
                      env={name: spelling, "GEMINI_API_KEY": SYNTHETIC_KEY})

    # (3) The one spelling that proceeds, against the same real function.
    assert llm_module.require_live_model("test", env=ALLOW_ENV) == SYNTHETIC_KEY
    assert llm_module.require_live_model(
        "test", need_key=False, env={name: "1"}) is None


@pytest.mark.t0
@pytest.mark.parametrize("value", [None, "", "   ", "${GEMINI_API_KEY}"])
def test_T_U_gen_22_the_interlock_refuses_without_a_usable_key(monkeypatch, value):
    """T-U-gen-22 (NFR-06, NFR-08): the key is checked, named, and never printed.

    The unexpanded-reference case is the operational one: CHIA's config loader
    leaves `${VAR}` as literal text when the variable is unset
    (`chia:chia/cluster/config.py:304`), so a container brought up without the
    key holds the reference as its value, and without this branch the failure
    would surface as a 403 from Vertex instead of a refusal on the head.
    """
    import socket

    from google import genai

    monkeypatch.setattr(genai, "Client", lambda **kwargs: pytest.fail(
        "a client was constructed without a usable key"))
    env = {"BUGLOOP_ALLOW_LIVE_MODEL": "1"}
    if value is not None:
        env["GEMINI_API_KEY"] = value

    with pytest.raises(LiveModelRefused) as raised:
        build_llm("system", 2400, MODEL_ID, env=env)
    message = str(raised.value)
    assert "GEMINI_API_KEY" in message and socket.gethostname() in message
    if value:
        assert value.strip() not in message or not value.strip(), (
            "the raised message must not echo the key's value")


@pytest.mark.t0
def test_T_U_gen_23_express_mode_construction(monkeypatch, fake_vertex):
    """T-U-gen-23 (FR-14.6): one api key, no project, no location, timeout in ms.

    The negative half is the point: a `VertexGeminiLLM` constructed WITHOUT the
    two assignments has `location == "us-central1"`, and building a real
    `genai.Client` from that pair raises `ValueError` naming "mutually
    exclusive", asserted against `google-genai` itself so that a CHIA release
    fixing the default makes this test fail loudly rather than silently.
    """
    from chia.models.vertex import VertexGeminiLLM

    install, capture = fake_vertex
    key = SYNTHETIC_KEY
    llm = build_llm("be terse", 2400, MODEL_ID, env=ALLOW_ENV)

    assert isinstance(llm, VertexGeminiLLM)
    assert llm.model == MODEL_ID
    assert llm.project is None and llm.location is None
    assert llm.client_kwargs == {"api_key": key,
                                 "http_options": {"timeout": 2400 * 1000}}

    install([vertex_response([vertex_text_part("PONG")], in_tok=1, out_tok=1)])
    llm.prompt("ping", [])
    assert capture["client_kwargs"] == {"vertexai": True, "project": None,
                                        "location": None, "api_key": key,
                                        "http_options": {"timeout": 2400000}}

    # The negative half, against google-genai itself.
    monkeypatch.undo()
    from google import genai

    unfixed = VertexGeminiLLM(model=MODEL_ID, project=None, location=None)
    assert unfixed.location == "us-central1"
    with pytest.raises(ValueError) as raised:
        genai.Client(vertexai=True, project=None, location=unfixed.location,
                     api_key=SYNTHETIC_KEY)
    assert "mutually exclusive" in str(raised.value)


@pytest.mark.t0
def test_T_U_gen_24_llm_turn_brings_the_usage_home(monkeypatch, fake_vertex,
                                                   allow_worker_env):
    """T-U-gen-24 (FR-14.6, FR-14.8): the token counts return with the result.

    Two assertions pin WHY the node exists: `QueryResult` carries no usage
    field at all on this backend, and the body calls `llm.prompt(...)` directly
    rather than `llm.prompt.options(...).chia_remote(...)`, because a remote
    dispatch serialises the LLM object and the counts would die with the task.
    """
    import dataclasses

    from chia.base.llm_call import QueryResult

    install, _ = fake_vertex
    install([vertex_response([vertex_text_part("PONG")], in_tok=11, out_tok=7)])

    turn = call_node(llm_turn, turn_request("ping", []))

    assert turn["usage"] == {"tokens_in": 11, "tokens_out": 7, "num_turns": 1,
                             "model": MODEL_ID, "thinking_tokens": 0,
                             "tool_use_prompt_tokens": 0, "observed": True}
    assert turn["result"] == "PONG" and turn["success"] is True
    assert turn["stderr"] == "" and "generate_content" in turn["stream"]

    assert [field.name for field in dataclasses.fields(QueryResult)] == [
        "result", "returncode", "stderr", "stream_result", "success"]
    # Read off the parsed body, not the text: this node's own comment explains
    # the departure and names the spelling it does not use.
    tree = ast.parse(textwrap.dedent(inspect.getsource(llm_turn._chia_original)))
    calls = {ast.unparse(node) for node in ast.walk(tree)
             if isinstance(node, ast.Call)}
    assert "llm.prompt(request['prompt'], list(request.get('tools') or []))" in calls
    attributes = {ast.unparse(node) for node in ast.walk(tree)
                  if isinstance(node, ast.Attribute)}
    assert not [name for name in attributes
                if name.endswith(".chia_remote") or name.endswith(".options")]
    assert llm_turn._chia_options == {"resources": {"llm": 1.0}, "max_retries": 0}


@pytest.mark.t0
def test_T_U_gen_24b_the_turn_request_carries_no_credential(monkeypatch,
                                                            fake_vertex,
                                                            allow_worker_env):
    """K2/W7: the request is seven fields, none of them an LLM and none a key.

    Two halves. The request `dispatch_turn` builds is asserted field by field,
    and the backend it never constructs is asserted by refusing `build_llm`
    everywhere but inside the node: a caller that still built one would fail
    here rather than silently ship a key through the object store.
    """
    install, capture = fake_vertex
    install([vertex_response([vertex_text_part("PONG")], in_tok=2, out_tok=3)])

    seen = {}
    real_turn = llm_turn._chia_original

    def record(request):
        seen.update(request)
        return real_turn(request)

    monkeypatch.setattr(llm_module.llm_turn, "_chia_original", record)
    turn = llm_module.dispatch_turn("be terse", "ping", [], stage="synthesis",
                                    timeout_seconds=1200, model_id=MODEL_ID)

    assert turn["result"] == "PONG"
    assert set(seen) == {"system_message", "prompt", "tools", "stage",
                         "timeout_seconds", "model_id", "max_tool_iterations"}
    # No guard, so no ceiling is sent either: the key is absent, not null.
    assert "turn_budget_usd" not in seen
    assert seen["tools"] == [] and seen["stage"] == "synthesis"
    assert seen["timeout_seconds"] == 1200 and seen["model_id"] == MODEL_ID
    # No value anywhere in the request is the key, and nothing in it is an LLM.
    assert SYNTHETIC_KEY not in repr(seen)
    assert capture["client_kwargs"]["api_key"] == SYNTHETIC_KEY


@pytest.mark.t0
def test_T_U_gen_24c_a_circt_worker_reaches_no_model(monkeypatch):
    """K2: `llm_turn` refuses on a worker whose environment has no interlock.

    This is the `circt` container's own case: `cluster_single.yaml` passes the
    two variables to `bugloop_llm` and `bugloop_repair` and to no other type,
    and the refusal now happens where the client is built, which is the `llm`
    worker, rather than on the caller.
    """
    monkeypatch.setattr(llm_module, "worker_env", lambda: {})
    with pytest.raises(LiveModelRefused):
        call_node(llm_turn, turn_request("ping", []))


@pytest.mark.t0
def test_T_U_gen_24d_tool_endpoints_are_what_the_backend_reads(tmp_path,
                                                               tool_servers,  # noqa: F811
                                                               throwaway_repo):  # noqa: F811
    """K2: the endpoint record carries exactly the four attributes CHIA reads.

    `chia:chia/models/vertex.py` builds `http://{hostname}:{port}/{name}/mcp`
    and records `node_id` beside them; a record of those four therefore serves
    the turn as the live tool object does, and is what may cross to a worker.
    """
    path, head = throwaway_repo
    tool = SourceReadTool(name="src_x", clone_path=path, run_commit=head)
    try:
        endpoint, = llm_module.tool_endpoints([tool])
    finally:
        tool.stop()

    assert (endpoint.name, endpoint.hostname, endpoint.port) == (
        "src_x", tool.hostname, tool.port)
    assert [f.name for f in __import__("dataclasses").fields(endpoint)] == [
        "name", "hostname", "port", "node_id"]


@pytest.mark.t0
def test_T_U_gen_25_the_tool_loop_runs_offline(monkeypatch, fake_vertex, tmp_path,
                                               allow_worker_env,
                                               tool_servers, throwaway_repo):  # noqa: F811
    """T-U-gen-25 (FR-04.4, FR-19.1): two tools declared, one call, one response.

    The declarations are asserted to have had `$schema`, `additionalProperties`
    and `title` stripped, because the backend removes them and a tool that
    relied on one to constrain the model would be relying on nothing.
    """
    path, head = throwaway_repo
    install, capture = fake_vertex
    install([vertex_response([vertex_call_part("src_x__read_file",
                                               {"path": "README.md"})],
                             in_tok=10, out_tok=5),
             vertex_response([vertex_text_part("done")], in_tok=3, out_tok=4)],
            tool_result_text="circt\n")

    source_read = SourceReadTool(name="src_x", clone_path=path, run_commit=head)
    probe_write = ProbeWriteTool(name="probe_x", probe_dir=str(tmp_path / "probes"))
    turn = call_node(llm_turn, turn_request("look at the tree",
                                            [source_read, probe_write]))

    assert turn["result"] == "done"
    assert turn["usage"]["tokens_in"] == 13 and turn["usage"]["num_turns"] == 2
    assert capture["urls"] == ["http://127.0.0.1:9001/src_x/mcp",
                               "http://127.0.0.1:9001/probe_x/mcp"]
    assert capture["tool_calls"] == [("read_file", {"path": "README.md"})]

    declarations = capture["calls"][0]["config"].tools[0].function_declarations
    assert [declaration.name for declaration in declarations] == [
        "src_x__read_file", "probe_x__read_file"]
    # The three keys the backend strips, asserted against the sanitiser itself:
    # a tool that relied on one of them to constrain the model would be relying
    # on nothing (`chia:chia/models/vertex.py:593-...`).
    from chia.models.vertex import VertexGeminiLLM

    sanitised = VertexGeminiLLM._sanitize_schema(
        {"type": "object", "properties": {}, "title": "x",
         "additionalProperties": False,
         "$schema": "https://json-schema.org/draft/2020-12/schema"})
    for stripped in ("$schema", "additionalProperties", "title"):
        assert stripped not in sanitised

    response = capture["calls"][1]["contents"][-1]
    assert response.role == "user"
    assert response.parts[0].function_response.name == "src_x__read_file"
    assert response.parts[0].function_response.response == {"result": "circt\n"}


# ---------------------------------------------------------------------------
# K10, K11: what a turn's usage says, and what it refuses to say
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_gen_26_the_two_billed_fields_are_counted():
    """K11: thinking is output, the tool-use prompt is input, and both are billed.

    New id, W-20b. `thoughts_token_count` and `tool_use_prompt_token_count` are
    SEPARATE scalars from the two CHIA sums - the SDK's own description of
    `total_token_count` is the sum of all four, verified against the installed
    `google-genai` here - so `campaign_spend_cap_usd` bound late by whatever the
    model thought. The patched backend publishes both under the two names this
    reads; `test_upstream_patches.py` is what proves the patch does, and
    pre-flight check 14 is what proves it is in the file a worker imports.

    The turn is not run: the INSTALLED chia is the unpatched one, and what is
    under test here is the loop's own arithmetic over the patched backend's
    block. Fixture: none. Tier 0.
    """
    from google.genai import types

    # The four are four distinct scalars, asserted against the SDK itself.
    fields = types.GenerateContentResponseUsageMetadata.model_fields
    for name in ("prompt_token_count", "candidates_token_count",
                 "thoughts_token_count", "tool_use_prompt_token_count"):
        assert name in fields, name

    usage = llm_module.turn_usage({
        "input_tokens": 100, "output_tokens": 20, "thinking_tokens": 900,
        "tool_use_prompt_tokens": 7, "num_turns": 3, "model": MODEL_ID})
    assert usage["thinking_tokens"] == 900 and usage["tool_use_prompt_tokens"] == 7
    assert usage["tokens_in"] == 107 and usage["tokens_out"] == 920
    assert usage["observed"] is True
    # The SDK's own `total_token_count` is the sum of the four, so the loop's
    # two now carry all of it and none of it twice.
    assert usage["tokens_in"] + usage["tokens_out"] == 100 + 20 + 900 + 7

    # And the money follows: 900 thinking tokens at the OUTPUT rate is what the
    # loop would otherwise have priced at nothing at all (ADR-D-03).
    from circt_bug_loop import ledger as ledger_module
    from circt_bug_loop.tests.test_bug_loop import budget_file

    budget = budget_file()
    priced = ledger_module.price(usage["tokens_in"], usage["tokens_out"], budget)
    unpatched = ledger_module.price(100, 20, budget)
    assert priced > unpatched * 8

    # The two names are the patch's own, so a rename upstream fails here.
    patch = (Path(llm_module.__file__).resolve().parents[1] / "upstream"
             / "vertex-usage.patch").read_text(encoding="utf-8")
    assert '"thinking_tokens"' in patch and '"tool_use_prompt_tokens"' in patch


@pytest.mark.t0
def test_T_U_gen_27_an_unobserved_turn_is_null_and_never_zero():
    """K10: an empty `_last_metadata` yields nulls, so the ledger records no money.

    New id, W-20b. `VertexGeminiLLM.prompt` resets `_last_metadata` at the top
    of EVERY attempt and assigns the real counts only at the very end of a
    successful one, so a turn that raised inside the tool loop - after up to
    `max_tool_iterations` = 100 `generate_content` calls - left it empty, and
    `meta.get("input_tokens", 0)` then priced that turn at USD 0.00. A zero is
    a measurement and an absence is not (FR-14.6). Fixture: none. Tier 0.
    """
    from circt_bug_loop import ledger as ledger_module
    from circt_bug_loop.tests.test_bug_loop import budget_file

    for empty in (None, {}, {"model": MODEL_ID}):
        usage = llm_module.turn_usage(empty)
        assert usage["tokens_in"] is None and usage["tokens_out"] is None
        assert usage["thinking_tokens"] is None
        assert usage["tool_use_prompt_tokens"] is None
        assert usage["observed"] is False
        assert ledger_module.price(usage["tokens_in"], usage["tokens_out"],
                                   budget_file()) is None
    # A turn that DID report, even all zeros, is a measurement and prices.
    observed = llm_module.turn_usage({"input_tokens": 0, "output_tokens": 0})
    assert observed["observed"] is True and observed["tokens_in"] == 0
    assert ledger_module.price(0, 0, budget_file()) == 0.0


# ---------------------------------------------------------------------------
# W1: the per-turn pre-authorisation
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_gen_28_every_turn_is_pre_authorised_against_the_cap(monkeypatch):
    """W1: the worst case is computed and refused BEFORE anything is sent.

    New id, W-20b. `ledger.stop_reason` tests spend ALREADY RECORDED and
    `_arm_stop` asks it once per seed, so the overshoot was a whole seed's
    spend: three iterations of two turns each plus five probes' stage-6 and
    stage-7 chains. Fixture: none. Tier 0.
    """
    guard = llm_module.SpendGuard(
        cap_usd=5.0, spend_usd=0.0,
        price_usd_per_m_input_tokens=0.75,
        price_usd_per_m_output_tokens=3.75)

    # The formula, arithmetic and all. A turn with NO tool makes exactly one
    # call whatever the iteration cap says: at 2.0 characters per token, 3000
    # characters is 1500 prompt tokens.
    one_call = {"prompt": "x" * 3000, "system_message": "", "tools": [],
                "max_tool_iterations": 6}
    assert guard.iterations(one_call) == 1
    assert guard.worst_case_usd(one_call) == round(
        1500 / 1e6 * 0.75 + llm_module.MAX_OUTPUT_TOKENS / 1e6 * 3.75, 6)
    assert llm_module.MAX_OUTPUT_TOKENS == 16000, "CHIA's own max_tokens default"

    # W-18b, errata row 38: the SAME request with a tool is the whole loop, and
    # the input tokens grow by one tool result per iteration because the loop
    # re-sends the conversation every time.
    with_tool = {**one_call, "tools": [object()]}
    assert guard.iterations(with_tool) == 6
    cap = llm_module.TOOL_OUTPUT_TOKENS_CAP
    expected_in = sum(1500 + i * cap for i in range(6))
    assert guard.worst_case_usd(with_tool) == round(
        expected_in / 1e6 * 0.75 + 6 * 16000 / 1e6 * 3.75, 6)
    # It is the thing W-18 measured missing: the loop's worst case is orders of
    # magnitude above one call's, which is what the old formula bounded.
    assert guard.worst_case_usd(with_tool) > 10 * guard.worst_case_usd(one_call)
    # The system message is re-sent on every call and counts.
    assert (guard.worst_case_usd({**one_call, "system_message": "y" * 1000})
            > guard.worst_case_usd(one_call))
    # The cap is 65536 tokens, which is the LARGEST of the three measurements
    # of one tool result rounded up to the next power of two. Pilot 1's
    # `stage_1` turn: 14 calls, 1.58 M input tokens, a 6,087-character prompt,
    # so 14 * 3044 + 91 * T = 1.58e6 gives T just under 17,000. Pilot 2's two
    # `stage_1` turns, six calls each: 29,378 and 36,286. A constant below any
    # of them is not a cap, which is why 32768 did not survive pilot 2.
    assert cap == 65536
    assert cap > (1.58e6 - 14 * 6087 / 2.0) / 91
    for tokens_in, prompt_chars in ((459484, 6271), (576454, 10722)):
        measured = (tokens_in - 6 * prompt_chars / 2.0) / 15.0
        assert cap > measured, f"{cap} does not cover {measured:.0f}"

    # W-12c, closing errata row 34. The constant must sit BELOW the one ratio
    # ever measured - 1,509,080 prompt characters billed as 619,603 input
    # tokens - so that the estimate OVER-counts tokens and the authorisation
    # over-charges. At 3 it under-charged the only turn it has ever seen by
    # 11.3 %, on the control that stops the campaign at its USD cap.
    assert llm_module.CHARS_PER_TOKEN == 2.0
    measured_chars, measured_tokens = 1509080, 619603
    assert llm_module.CHARS_PER_TOKEN < measured_chars / measured_tokens
    assert measured_chars / llm_module.CHARS_PER_TOKEN > measured_tokens, \
        "an over-estimate of the token count is the safe direction"

    # Authorising accumulates, so two turns in one node bound each other even
    # though `spend_usd` is refreshed only per iteration (W10).
    first = guard.authorise(one_call)
    assert guard.authorised_usd == first
    guard.authorise(one_call)
    assert guard.authorised_usd == pytest.approx(2 * first)

    # And the refusal: a spend already at the cap stops the turn, and nothing
    # is dispatched - `llm_turn` is a sentinel that fails the test if reached.
    monkeypatch.setattr(llm_module.llm_turn, "_chia_original",
                        lambda request: pytest.fail("a refused turn was sent"))
    tight = llm_module.SpendGuard(
        cap_usd=0.01, spend_usd=0.0,
        price_usd_per_m_input_tokens=0.75,
        price_usd_per_m_output_tokens=3.75)
    with pytest.raises(llm_module.SpendCapRefused) as raised:
        llm_module.dispatch_turn("be terse", "ping", [], stage="stage_2",
                                 timeout_seconds=60, model_id=MODEL_ID,
                                 guard=tight)
    assert "campaign_spend_cap_usd" in str(raised.value)
    assert tight.authorised_usd == 0.0, "a refused turn authorises nothing"

    # The ceiling handed to the backend is EXACTLY what the guard authorised,
    # never more: that is the invariant W-18b asks for, and it is an equality.
    sent = {}
    monkeypatch.setattr(llm_module.llm_turn, "_chia_original",
                        lambda request: sent.update(request) or {
                            "result": "", "stream": "", "stderr": "",
                            "success": True,
                            "usage": {"tokens_in": 10, "tokens_out": 4,
                                      "num_turns": 3}})
    roomy = llm_module.SpendGuard(
        cap_usd=100.0, spend_usd=0.0,
        price_usd_per_m_input_tokens=0.75, price_usd_per_m_output_tokens=3.75)
    out = llm_module.dispatch_turn("be terse", "ping", [], stage="stage_2",
                                   timeout_seconds=60, model_id=MODEL_ID,
                                   guard=roomy, max_tool_iterations=6)
    assert sent["turn_budget_usd"] == roomy.authorised_usd
    assert sent["max_tool_iterations"] == 6
    assert roomy.worst_case_usd({**sent, "tools": []}) >= sent["turn_budget_usd"]
    # And the four money fields the ledger row of contract 2.2 carries.
    assert out["usage"]["authorised_usd"] == roomy.authorised_usd
    assert out["usage"]["ceiling_usd"] == roomy.authorised_usd
    assert out["usage"]["billed_usd"] == round(
        10 / 1e6 * 0.75 + 4 / 1e6 * 3.75, 6)
    assert out["usage"]["calls"] == 3
