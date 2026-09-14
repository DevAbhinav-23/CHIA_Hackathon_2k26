"""`llm.py`, the one neutral module: `04-Test-Plan.md` §1.6 (03-LLD.md §3.5.1)."""
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
# The throwaway git repository and the no-Ray tool construction are shared with the tool tests rather than built twice.
from circt_bug_loop.tests.test_tools import (throwaway_repo,  # noqa: F401
                                             tool_servers)

pytestmark = pytest.mark.filterwarnings(
    "ignore::pydantic_settings.exceptions.IncompleteFieldDefinitionWarning")

#: A synthetic key, which is not a credential and never leaves this process.
SYNTHETIC_KEY = "bugloop-synthetic-not-a-real-key"

MODEL_ID = "gemini-3.8-flash"

#: The interlock's ALLOW mapping.
ALLOW_ENV = {"BUGLOOP_ALLOW_LIVE_MODEL": "1", "GEMINI_API_KEY": SYNTHETIC_KEY}


@pytest.fixture
def allow_worker_env(monkeypatch):
    """Let `llm_turn` build its client, without setting the real variable."""
    monkeypatch.setattr(llm_module, "worker_env", lambda: dict(ALLOW_ENV))


def turn_request(prompt: str, tools, *, stage: str = "stage_2",
                 timeout_seconds: int = 2400) -> dict:
    """The request `dispatch_turn` builds, for a test that calls the node."""
    return {"system_message": "be terse", "prompt": prompt,
            "tools": llm_module.tool_endpoints(tools), "stage": stage,
            "timeout_seconds": timeout_seconds, "model_id": MODEL_ID}


@pytest.mark.t0
def test_T_U_gen_21_the_interlock_refuses_without_the_variable(monkeypatch):
    """T-U-gen-21 (NFR-08): five spellings refuse, and nothing is built."""
    from google import genai

    monkeypatch.setattr(genai, "Client", lambda **kwargs: pytest.fail(
        "a client was constructed with the interlock closed"))

    # (1) The DEFAULT env, which is the process environment.
    assert llm_module._LIVE_MODEL_ENV not in os.environ
    with pytest.raises(LiveModelRefused) as raised:
        build_llm("system", 2400, MODEL_ID)
    assert llm_module._LIVE_MODEL_ENV in str(raised.value)
    assert "3.5.1" in str(raised.value)

    # (2) The four other spellings.
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
    """T-U-gen-22 (NFR-06): the key is checked, named, and never printed."""
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
    """T-U-gen-23 (FR-14.6): one api key, no project, no location, timeout in ms."""
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
    """T-U-gen-24 (FR-14.6): the token counts return with the result."""
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
    # Read off the parsed body, not the text.
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
    """K2/W7: the request is ten fields, none of them an LLM and none a key."""
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
                         "timeout_seconds", "model_id", "max_tool_iterations",
                         "max_output_tokens", "final_tool_names",
                         "final_tool_iterations"}
    # No guard, so no ceiling is sent either: the key is absent, not null.
    assert "turn_budget_usd" not in seen
    assert seen["tools"] == [] and seen["stage"] == "synthesis"
    assert seen["timeout_seconds"] == 1200 and seen["model_id"] == MODEL_ID
    # No value anywhere in the request is the key, and nothing in it is an LLM.
    assert SYNTHETIC_KEY not in repr(seen)
    assert capture["client_kwargs"]["api_key"] == SYNTHETIC_KEY


@pytest.mark.t0
def test_T_U_gen_24c_a_circt_worker_reaches_no_model(monkeypatch):
    """K2: `llm_turn` refuses on a worker whose environment has no interlock."""
    monkeypatch.setattr(llm_module, "worker_env", lambda: {})
    with pytest.raises(LiveModelRefused):
        call_node(llm_turn, turn_request("ping", []))


@pytest.mark.t0
def test_T_U_gen_24d_tool_endpoints_are_what_the_backend_reads(tmp_path,
                                                               tool_servers,  # noqa: F811
                                                               throwaway_repo):  # noqa: F811
    """K2: the endpoint record carries exactly the four attributes CHIA reads."""
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
    """T-U-gen-25 (FR-04.4): two tools declared, one call, one response."""
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
    # The three keys the backend strips, asserted against the sanitiser itself.
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


@pytest.mark.t0
def test_T_U_gen_26_the_two_billed_fields_are_counted():
    """K11: thinking is output, the tool-use prompt is input, and both are billed."""
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
    # The SDK's own `total_token_count` is the sum of the four.
    assert usage["tokens_in"] + usage["tokens_out"] == 100 + 20 + 900 + 7

    # And the money follows.
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
    """K10: an empty `_last_metadata` yields nulls, so the ledger records no money."""
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


@pytest.mark.t0
def test_T_U_gen_28_every_turn_is_pre_authorised_against_the_cap(monkeypatch):
    """W1: the worst case is computed and refused BEFORE anything is sent."""
    guard = llm_module.SpendGuard(
        cap_usd=5.0, spend_usd=0.0,
        price_usd_per_m_input_tokens=0.75,
        price_usd_per_m_output_tokens=3.75)

    # The formula, arithmetic and all.
    one_call = {"prompt": "x" * 3000, "system_message": "", "tools": [],
                "max_tool_iterations": 6}
    assert guard.iterations(one_call) == 1
    assert guard.worst_case_usd(one_call) == round(
        1500 / 1e6 * 0.75 + llm_module.MAX_OUTPUT_TOKENS / 1e6 * 3.75, 6)
    assert llm_module.MAX_OUTPUT_TOKENS == 16000, "CHIA's own max_tokens default"

    # W-18b, errata row 38, plus the forced final answer's own call.
    with_tool = {**one_call, "tools": [object()]}
    assert guard.iterations(with_tool) == 7, "max_tool_iterations plus the final answer"
    cap = llm_module.TOOL_OUTPUT_TOKENS_CAP
    expected_in = sum(1500 + i * cap for i in range(7))
    assert guard.worst_case_usd(with_tool) == round(
        expected_in / 1e6 * 0.75 + 7 * 16000 / 1e6 * 3.75, 6)
    # It is the thing W-18 measured missing.
    assert guard.worst_case_usd(with_tool) > 10 * guard.worst_case_usd(one_call)

    # D-3 (pilot 5): stage 2's write phase is a SECOND budget of calls, and the
    # pre-authorisation counts it, the reading phase and the final answer.
    writing = {**with_tool, "final_tool_names": ["write_probe"],
               "final_tool_iterations": 4}
    assert guard.iterations(writing) == 6 + 4 + 1
    assert guard.worst_case_usd(writing) > guard.worst_case_usd(with_tool)
    # Neither half of the pair authorises anything on its own.
    assert guard.iterations({**with_tool, "final_tool_iterations": 4}) == 7
    assert guard.iterations({**writing, "final_tool_iterations": 0}) == 7
    # The system message is re-sent on every call and counts.
    assert (guard.worst_case_usd({**one_call, "system_message": "y" * 1000})
            > guard.worst_case_usd(one_call))
    # W-18d: one tool result is bounded by the tool itself, so the price of one
    # is that bound and not a measurement of what an unbounded read returned.
    from circt_bug_loop import generate_task

    assert cap == 32768
    assert cap >= generate_task.SOURCE_READ_CAP_BYTES / llm_module.CHARS_PER_TOKEN
    assert generate_task.SOURCE_READ_CAP_BYTES == 65536

    # W-12c, closing errata row 34.
    assert llm_module.CHARS_PER_TOKEN == 2.0
    measured_chars, measured_tokens = 1509080, 619603
    assert llm_module.CHARS_PER_TOKEN < measured_chars / measured_tokens
    assert measured_chars / llm_module.CHARS_PER_TOKEN > measured_tokens, \
        "an over-estimate of the token count is the safe direction"

    # Authorising accumulates, each turn under its own handle.
    one, first = guard.authorise(one_call)
    assert guard.in_flight_usd == first
    two, _ = guard.authorise(one_call)
    assert guard.in_flight_usd == pytest.approx(2 * first)
    assert one != two

    # And the refusal: a spend already at the cap stops the turn, and nothing is dispatched.
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
    assert tight.in_flight_usd == 0.0, "a refused turn authorises nothing"
    assert tight.settled_usd == 0.0

    # The ceiling handed to the backend is EXACTLY what the guard authorised, never more.
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
    billed = round(10 / 1e6 * 0.75 + 4 / 1e6 * 3.75, 6)
    assert sent["turn_budget_usd"] == out["usage"]["authorised_usd"]
    assert sent["max_tool_iterations"] == 6
    assert roomy.worst_case_usd({**sent, "tools": []}) >= sent["turn_budget_usd"]
    # And the four money fields the ledger row of contract 2.2 carries.
    assert out["usage"]["ceiling_usd"] == out["usage"]["authorised_usd"]
    assert out["usage"]["billed_usd"] == billed
    assert out["usage"]["calls"] == 3
    # D-5: the turn settled to its bill, and holds nothing any more.
    assert out["usage"]["settled_usd"] == billed
    assert (roomy.settled_usd, roomy.in_flight_usd) == (billed, 0.0)


@pytest.mark.t0
def test_the_guard_settles_an_authorisation_to_what_the_turn_billed(monkeypatch):
    """D-5 (pilot 6): the cap bounds money SPENT, so an authorisation is reconciled."""
    def guard(cap_usd: float = 6.0):
        one = llm_module.SpendGuard(
            cap_usd=cap_usd, spend_usd=0.0,
            price_usd_per_m_input_tokens=0.075,
            price_usd_per_m_output_tokens=0.30)
        monkeypatch.setattr(one, "worst_case_usd", lambda request: request["worst"])
        return one

    # Pilot 6's own two turns, at pilot 6's own cap: stage 2 is now ADMITTED.
    settling = guard()
    stage_1, authorised = settling.authorise({"worst": 2.729162})
    assert (authorised, settling.in_flight_usd) == (2.729162, 2.729162)
    assert settling.settle(stage_1, 0.605893) == 0.605893
    assert (settling.settled_usd, settling.in_flight_usd) == (0.605893, 0.0)
    stage_2, _ = settling.authorise({"worst": 4.384600})
    assert (settling.in_flight_usd, settling.settled_usd) == (4.3846, 0.605893)
    assert 0.605893 + 4.3846 < settling.cap_usd <= 2.729162 + 4.3846, \
        "the accumulated authorisations are what refused this turn"

    # A turn settles ONCE, and never releases what it never held.
    assert settling.settle(stage_2, 0.5) == 0.5
    with pytest.raises(KeyError):
        settling.settle(stage_2, 0.5)

    # An unobserved turn, and a turn that raised after its calls, keep the lot.
    unobserved = guard()
    handle, worst = unobserved.authorise({"worst": 1.5})
    assert unobserved.settle(handle, None) == worst
    assert (unobserved.settled_usd, unobserved.in_flight_usd) == (1.5, 0.0)

    def explode(request):
        raise RuntimeError("the backend went away mid-turn")

    monkeypatch.setattr(llm_module.llm_turn, "_chia_original", explode)
    raising = llm_module.SpendGuard(
        cap_usd=100.0, spend_usd=0.0, price_usd_per_m_input_tokens=0.075,
        price_usd_per_m_output_tokens=0.30)
    with pytest.raises(RuntimeError):
        llm_module.dispatch_turn("be terse", "ping", [], stage="stage_2",
                                 timeout_seconds=60, model_id=MODEL_ID,
                                 guard=raising)
    assert raising.in_flight_usd == 0.0
    assert raising.settled_usd == raising.worst_case_usd(
        {"prompt": "ping", "system_message": "be terse", "tools": [],
         "max_output_tokens": llm_module.stage_max_output_tokens("stage_2")})

    # And the cap still refuses: settled plus in flight plus the worst case.
    refusing = guard()
    refusing.settle(refusing.authorise({"worst": 3.0})[0], 1.0)
    refusing.authorise({"worst": 2.0})
    with pytest.raises(llm_module.SpendCapRefused) as raised:
        refusing.authorise({"worst": 3.5})
    assert "in flight" in str(raised.value)
    assert refusing.in_flight_usd == 2.0, "a refused turn authorises nothing"


@pytest.mark.t0
def test_T_U_gen_28b_stage_two_is_priced_at_its_own_output_cap(monkeypatch):
    """W-23: stage 2's turn is built AND authorised at 32,000 output tokens."""
    assert llm_module.stage_max_output_tokens("stage_2") == 32000
    for stage in ("stage_1", "stage_6", "stage_7", "synthesis", "anything"):
        assert llm_module.stage_max_output_tokens(stage) == \
            llm_module.MAX_OUTPUT_TOKENS == 16000, stage

    guard = llm_module.SpendGuard(
        cap_usd=100.0, spend_usd=0.0, price_usd_per_m_input_tokens=0.75,
        price_usd_per_m_output_tokens=3.75)
    request = {"prompt": "x" * 3000, "system_message": "", "tools": [object()],
               "max_tool_iterations": 6}
    n = guard.iterations(request)
    tokens_in = sum(1500 + i * llm_module.TOOL_OUTPUT_TOKENS_CAP for i in range(n))

    # No key: the guard's own default, which is what stage 7 still prices at.
    assert guard.worst_case_usd(request) == round(
        tokens_in / 1e6 * 0.75 + n * 16000 / 1e6 * 3.75, 6)
    # The stage's value, which is the one its backend is built with.
    big = {**request, "max_output_tokens": 32000}
    assert guard.worst_case_usd(big) == round(
        tokens_in / 1e6 * 0.75 + n * 32000 / 1e6 * 3.75, 6)
    assert guard.worst_case_usd(big) > guard.worst_case_usd(request)

    # And the request `dispatch_turn` builds carries the stage's value through
    # to `build_llm`'s `max_tokens`, which is the backend's own cap.
    sent = {}
    monkeypatch.setattr(llm_module.llm_turn, "_chia_original",
                        lambda request: sent.update(request) or {
                            "result": "", "stream": "", "stderr": "",
                            "success": True, "usage": {}})
    roomy = llm_module.SpendGuard(
        cap_usd=100.0, spend_usd=0.0, price_usd_per_m_input_tokens=0.75,
        price_usd_per_m_output_tokens=3.75)
    llm_module.dispatch_turn("be terse", "ping", [], stage="stage_2",
                             timeout_seconds=60, model_id=MODEL_ID, guard=roomy,
                             max_tool_iterations=6)
    assert sent["max_output_tokens"] == 32000
    assert sent["turn_budget_usd"] == roomy.worst_case_usd(
        {**sent, "tools": []})

    sent.clear()
    llm_module.dispatch_turn("be terse", "ping", [], stage="stage_1",
                             timeout_seconds=60, model_id=MODEL_ID)
    assert sent["max_output_tokens"] == 16000

    built = build_llm("be terse", 60, MODEL_ID, env=dict(ALLOW_ENV),
                      max_output_tokens=32000)
    assert built.max_tokens == 32000
    assert build_llm("be terse", 60, MODEL_ID, env=dict(ALLOW_ENV)).max_tokens \
        == 16000, "CHIA's own default when no stage value is passed"
