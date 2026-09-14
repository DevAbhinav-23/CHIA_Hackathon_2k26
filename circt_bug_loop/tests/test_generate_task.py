"""`generate_task.py` (A3, A4, the backend glue): `04-Test-Plan.md` §1.6.

`T-U-gen-01` to `-10`, `-14`, and `-19` to `-25`; the tool rows `-11` to `-18`
are in `test_tools.py`, which W-13's brief asks for as a module of its own.

**No model runs in any of these, and that is enforced rather than intended.**
The five backend tests use `conftest.fake_vertex`, which is CHIA's own
`chia/models/tests/test_vertex.py` recipe, and the seeded arm's two turns are
driven by the recorded-shaped transcripts of `fixtures/generate/` replayed
through a `dispatch_turn` substitute, so `_turn` itself, the prompts, the
emitter, the two `ChiaTool`s and `corpus.resolve_sites` are all the real ones.

**`BUGLOOP_ALLOW_LIVE_MODEL` is never set by anything in this file**, not even
inside `monkeypatch`, which is stricter than §1.6's own sentence and is what
the work-plan brief asks for. The allow path is exercised by substituting the
NAME the interlock reads, `generate_task._LIVE_MODEL_ENV`, with the stub below:
the refusal, the key check and the express construction all run, and the real
variable stays absent from this process for the whole session (`T-U-layout-08`,
and `conftest.no_live_model` asserts it).
"""
import ast
import inspect
import json
import os
import re
import textwrap
from pathlib import Path

import pytest

from circt_bug_loop import generate_task
from circt_bug_loop.contract import schema
from circt_bug_loop.generate_task import (LiveModelRefused, ProbeWriteTool,
                                          SourceReadTool, build_llm, emit_specs,
                                          generate_mutation, generate_seeded,
                                          llm_turn)
from circt_bug_loop.tests.conftest import (call_node, vertex_call_part,
                                           vertex_response, vertex_text_part)
# The throwaway git repository and the no-Ray tool construction are shared with
# the tool tests rather than built twice.
from circt_bug_loop.tests.test_tools import (throwaway_repo,  # noqa: F401
                                             tool_servers)

pytestmark = pytest.mark.filterwarnings(
    "ignore::pydantic_settings.exceptions.IncompleteFieldDefinitionWarning")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TURNS = FIXTURES / "generate" / "turns"
SEEDS = FIXTURES / "corpus" / "seeds"

#: The variable name the interlock reads is substituted with this one wherever
#: a test needs the ALLOW path. Nothing in this tree sets the real name.
INTERLOCK_STUB = "BUGLOOP_TEST_INTERLOCK_STUB"

#: A synthetic key, which is not a credential and never leaves this process.
SYNTHETIC_KEY = "bugloop-synthetic-not-a-real-key"

MODEL_ID = "gemini-3.8-flash"


def transcript(name: str) -> str:
    """One constructed turn text of `fixtures/generate/turns/`."""
    return (TURNS / f"{name}.md").read_text(encoding="utf-8")


def seed() -> schema.SeedRecord:
    """The corpus's nine-test-file seed, read back through the contract."""
    return schema.from_json((SEEDS / "nine_test_files.json").read_text(
        encoding="utf-8"), schema.SeedRecord)


def empty_feedback(iteration: int = 0) -> schema.FeedbackBundle:
    """The bundle A5 builds for a first iteration: no entries, not abandoned."""
    return schema.FeedbackBundle(run_manifest_id="run-1", seed_sha=seed().seed_sha,
                                 arm="seeded", iteration=iteration, entries=[],
                                 abandoned=False, terminating_condition=None)


def allow_live_model(monkeypatch, key: str = SYNTHETIC_KEY) -> str:
    """Open the interlock through a STUB variable name, never the real one."""
    monkeypatch.setattr(generate_task, "_LIVE_MODEL_ENV", INTERLOCK_STUB)
    monkeypatch.setenv(INTERLOCK_STUB, "1")
    monkeypatch.setenv("GEMINI_API_KEY", key)
    return key


@pytest.fixture
def config(tmp_path, throwaway_repo) -> dict:  # noqa: F811
    """One iteration's `cfg`, with the throwaway repository as the run's clone."""
    path, head = throwaway_repo
    return {"model_id": MODEL_ID, "per_seed_probe_cap": 3, "iteration": 0,
            "clone_path": path, "run_commit": head,
            "run_manifest_id": "run-1", "timeout_seconds": 2400,
            "artefact_dir": str(tmp_path / "iter_0"),
            "artefact_inline_cap_bytes": 262144,
            "price_usd_per_m_input_tokens": 0.30,
            "price_usd_per_m_output_tokens": 2.50,
            "head_options": {"scheduling_strategy": "head-node"},
            "here_options": {"scheduling_strategy": "this-worker"}}


@pytest.fixture
def replay(monkeypatch, tool_servers):  # noqa: F811
    """Replay recorded turn text through the one call that reaches a model.

    `dispatch_turn` is the ONE function substituted, and nothing else is:
    `_turn` still renders, writes FR-04.6's five files and records the usage,
    the two `ChiaTool`s are constructed and stopped for real, and a turn's
    declared files are written through `write_probe` itself, so a name the tool
    would refuse is refused here too. Since K2 the node builds no backend at
    all - the client is `llm_turn`'s, on the `llm` worker - so the substitute
    receives the turn request's fields and never an LLM.
    """
    def install(turns: list) -> dict:
        state = {"calls": [], "pending": list(turns)}

        def _dispatch(system_message, user_message, tools, *, stage,
                      timeout_seconds, model_id, guard=None):
            turn = state["pending"].pop(0)
            state["calls"].append({"prompt": user_message, "tools": list(tools),
                                   "system_message": system_message,
                                   "timeout_seconds": timeout_seconds,
                                   "model_id": model_id, "stage": stage})
            for name, content in (turn.get("files") or {}).items():
                tools[-1].write_probe(name, content)
            if turn.get("raises") is not None:
                raise turn["raises"]
            text = turn.get("text", "")
            return {"result": text, "stream": f"[stream]\n{text}",
                    "stderr": turn.get("stderr", ""), "success": True,
                    "usage": turn.get("usage", {"tokens_in": 11, "tokens_out": 7,
                                                "num_turns": 1, "model": MODEL_ID})}

        monkeypatch.setattr(generate_task, "dispatch_turn", _dispatch)
        return state

    return install


def probe_files(names, text: str = "hw.module @Top() {}\n") -> dict:
    """The files a stage-2 turn claims to have written, by name."""
    return {name: text for name in names}


def run_seeded(config: dict, feedback=None) -> dict:
    """One A3 iteration, through the undecorated node (04-Test-Plan.md 0.4)."""
    return call_node(generate_seeded, seed(), feedback or empty_feedback(),
                     schema.LedgerSnapshot(arm="seeded", unit="wall_clock_seconds",
                                           spent=0.0, cap=14400.0), config)


# ---------------------------------------------------------------------------
# The two turns, the emitter and the cap
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_gen_01_the_tool_list_is_exactly_the_two_tools(replay, config,
                                                           tool_servers):  # noqa: F811
    """T-U-gen-01 (FR-04.4, NFR-03): `[source_read, probe_write]`, and no BashTool.

    The withdrawal is what makes FR-04.4's second clause true by construction:
    `BashTool` had no read-only mode and its `PATH` on a `circt` worker put
    `/workspace/circt/build/bin` first (W10).
    """
    state = replay([{"text": transcript("seed_read_ok")},
                    {"text": transcript("probe_write_ok"),
                     "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    run_seeded(config)

    assert len(state["calls"]) == 2
    for call in state["calls"]:
        tools = call["tools"]
        assert [type(tool) for tool in tools] == [SourceReadTool, ProbeWriteTool]
        assert tools == tool_servers, "both turns get the same two objects"

    source = Path(generate_task.__file__).read_text(encoding="utf-8")
    assert "BashTool" not in source
    for word in ("lit", "oracle", "reduce", "dedup", "ninja", "cmake"):
        assert f"{word}Tool" not in source


@pytest.mark.t0
def test_T_U_gen_02_the_cap_keeps_the_first_three_in_emission_order(replay, config):
    """T-U-gen-02 (FR-04.5): cap 3 against 10 declared, and 7 recorded discarded."""
    names = [f"probe_{index:02d}.mlir" for index in range(1, 11)]
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_10"), "files": probe_files(names)}])
    result = run_seeded(config)

    assert result["truncated"] == 7
    assert len(result["specs"]) == 3
    assert [spec.expected_outcome for spec in result["specs"]] == [
        f"input {index} reaches the element-type assertion" for index in (1, 2, 3)]


@pytest.mark.t0
def test_T_U_gen_03_a_wrong_tool_is_the_emitters_E010_and_not_the_validators(
        replay, config):
    """T-U-gen-03 (FR-04.2): `emit_specs` raises E010; `validate` accepts the same spec.

    K10's correction, measured: `ProbeSpec.tool` is annotated `str` and not a
    `Literal`, and `validate` is handed one object with no access to the
    `SeedRecord`, so the check has to live where the seed is.
    """
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_wrongtool"),
             "files": probe_files(["array_element.mlir"])}])
    result = run_seeded(config)

    assert result["specs"] == []
    assert result["rejections"]["tool_mismatch"] == 1
    assert result["failure"] is None, "a rejected spec is not a failed turn"

    accepted = schema.from_json(
        (schema.__file__ and Path(__file__).resolve().parent.parent
         / "contract" / "fixtures" / "probe_spec" / "seeded_01.json").read_text(
            encoding="utf-8"), schema.ProbeSpec)
    accepted.tool = "firtool"
    schema.validate(accepted)                      # the other half of T-U-schema-21
    with pytest.raises(schema.ContractError) as raised:
        generate_task.check_tool(accepted, seed())
    assert raised.value.code == "E010_TOOL_MISMATCH"
    assert "firtool" in str(raised.value) and "circt-opt" in str(raised.value)


@pytest.mark.t0
def test_T_U_gen_04_every_emitted_spec_validates_with_every_field_populated(
        replay, config):
    """T-U-gen-04 (FR-04.3): the contract accepts each spec, input on disk and inline."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_ok"),
             "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    result = run_seeded(config)

    assert len(result["specs"]) == 2
    for spec in result["specs"]:
        schema.validate(spec)
        assert spec.arm == "seeded" and spec.iteration == 0
        assert spec.tool == "circt-opt" and spec.seed_sha == seed().seed_sha
        assert spec.probe_id.startswith("p-") and spec.run_manifest_id == "run-1"
        assert Path(spec.input_path).is_file()
        assert spec.input_text == Path(spec.input_path).read_text(encoding="utf-8")
        assert spec.input_filename == "input.mlir"
        assert spec.polarity == "expect_zero" and spec.shape in ("plain", "split_file")
        assert spec.turn_cost["turn"] == "probe_write"
        assert spec.turn_cost["metered"] is True
        assert spec.turn_cost["tokens_in"] == 11 and spec.turn_cost["tokens_out"] == 7
        assert spec.turn_cost["cost_usd"] == pytest.approx(
            11 / 1e6 * 0.30 + 7 / 1e6 * 2.50)
        assert (spec.mutator_id, spec.mutator_seed_int, spec.source_test_path) == (
            None, None, None)


@pytest.mark.t0
def test_T_U_gen_05_sibling_sites_are_resolved_against_the_run_commit(replay, config):
    """T-U-gen-05 (FR-04.1): a site that resolves stands, one that does not is counted.

    The resolution is `corpus.resolve_sites`, a HEAD node, dispatched rather
    than run inside A3, which sits on a `circt` worker with no clone (K5). Both
    halves are asserted: the outcome here, and the dispatch on the source below.
    """
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_ok"),
             "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    result = run_seeded(config)

    assert [site["symbol"] for site in result["sibling_sites"]] == ["parseHWArray"]
    assert [(site["file"], site["reason"]) for site in result["rejected_sites"]] == [
        ("lib/Dialect/HW/NoSuch.cpp", "no_such_file"),
        ("lib/Dialect/HW/HWTypes.cpp", "no_symbol")]
    assert result["root_cause_class"].startswith("A conversion pattern assumed")

    dispatch = inspect.getsource(generate_task._resolve_sites)
    assert "corpus.resolve_sites" in dispatch and 'cfg.get("head_options")' in dispatch
    body = inspect.getsource(generate_seeded)
    assert "git" not in body and "subprocess" not in body


@pytest.mark.t0
def test_T_U_gen_06_a_failed_turn_is_recorded_charged_and_survived(replay, config):
    """T-U-gen-06 (FR-04.8): the cause is recorded, the spend returned, the run lives."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": "", "raises": RuntimeError("backend said no"),
             "usage": {"tokens_in": 40, "tokens_out": 0, "num_turns": 1,
                       "model": MODEL_ID}}])
    result = run_seeded(config)

    assert result["failure"] == "turn_failed:RuntimeError"
    assert result["specs"] == []
    # The stage-1 spend is still returned for the ledger to charge, and the
    # failed turn's own files are on disk.
    assert result["logs"]["usage"]["seed_read"]["tokens_in"] == 11
    assert Path(result["logs"]["llm_probe_write.prompt.md"]).is_file()
    assert result["counters"].failed == 1 and result["counters"].completed == 0


@pytest.mark.t0
def test_T_U_gen_07_a_malformed_footer_emits_nothing_at_all(replay, config):
    """T-U-gen-07 (FR-04.8): zero specs even though the files were written."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_badfooter"),
             "files": probe_files(["array_element.mlir"])}])
    result = run_seeded(config)

    assert result["failure"] == "prompt_contract:no_block"
    assert result["specs"] == []
    written = Path(config["artefact_dir"]) / "probes" / "array_element.mlir"
    assert written.is_file(), "the file was written; the footer is what failed"


@pytest.mark.t0
def test_T_U_gen_08_all_five_files_are_written_for_both_turns(replay, config):
    """T-U-gen-08 (FR-04.6): prompt, stream, raw transcript, stderr, usage."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_ok"),
             "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    run_seeded(config)

    directory = Path(config["artefact_dir"])
    for stage in ("seed_read", "probe_write"):
        for suffix in (".prompt.md", ".md", ".stderr", ".jsonl", ".usage.json"):
            assert (directory / f"llm_{stage}{suffix}").is_file(), stage
    usage = json.loads((directory / "llm_seed_read.usage.json").read_text())
    assert usage == {"tokens_in": 11, "tokens_out": 7, "num_turns": 1,
                     "model": MODEL_ID}
    assert (directory / "PARTIAL").is_file(), "FR-17.8's marker, written first"


@pytest.mark.t0
def test_T_U_gen_14_the_argv_is_the_seeds_and_never_the_agents(replay, config):
    """T-U-gen-14 (FR-04.2, NFR-03): the declared argv is ignored, the template wins."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_argv"),
             "files": probe_files(["array_element.mlir"])}])
    result = run_seeded(config)

    spec, = result["specs"]
    assert spec.argv == ["-lower-handshake-to-hw", spec.input_path]
    assert "--mlir-print-ir-after-all" not in spec.argv
    # `--split-input-file` is in the seed's own template and is stripped,
    # because a single generated input has nothing to split.
    assert "--split-input-file" in seed().argv_template[0]
    assert not any(token.startswith("--split-input-file") for token in spec.argv)


@pytest.mark.t0
def test_T_U_gen_19_both_tools_are_stopped_in_a_finally(replay, config,
                                                        monkeypatch, tool_servers):  # noqa: F811
    """T-U-gen-19 (FR-19.1): no live tool server survives a turn, or a raising turn.

    Without it, 187 seeds at up to 3 iterations is up to 561 orphaned actors
    plus 561 orphaned servers in one arm window, on a cluster whose whole point
    is a fixed size (W11).
    """
    from chia.base.tools.ChiaTool import ChiaTool

    before = len(ChiaTool._tool_registry)
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_ok"),
             "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    run_seeded(config)
    assert len(ChiaTool._tool_registry) == before, "a turn that returned leaked a tool"

    replay([{"text": "", "raises": RuntimeError("backend said no")}])
    assert run_seeded(config)["failure"] == "turn_failed:RuntimeError"
    assert len(ChiaTool._tool_registry) == before, "a turn that raised leaked a tool"

    # A stop() that itself raises is swallowed, which is CHIA's own choice at
    # the same place: a tool that will not stop must not mask the result.
    def _angry_stop(self):
        raise RuntimeError("the actor is gone")

    monkeypatch.setattr(ChiaTool, "stop", _angry_stop)
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_ok"),
             "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    assert run_seeded(config)["failure"] is None


@pytest.mark.t0
def test_T_U_gen_20_the_two_tools_are_placed_on_different_nodes(replay, config,
                                                                tool_servers):  # noqa: F811
    """T-U-gen-20 (FR-04.4, FR-06.8): the source tool on the head, the writer here.

    The clone is the head's, and a write has to land in the filesystem
    namespace the probe directory lives in, so the two differ in every
    construction.
    """
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_ok"),
             "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    run_seeded(config)

    source_read, probe_write = tool_servers
    assert source_read.task_options == config["head_options"]
    assert probe_write.task_options == config["here_options"]
    assert source_read.task_options != probe_write.task_options


# ---------------------------------------------------------------------------
# The mutation arm, and the one code path both arms take
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_gen_09_the_mutation_arms_body_does_not_read_its_feedback(  # noqa: D403
        ):
    """T-U-gen-09 (FR-16.2): the identifier appears exactly once, in the parameters.

    The rule is enforced on the BODY and not on the signature, because FR-05.4
    requires both arms' output to travel one code path and two signatures for
    one `Generator` protocol is a second code path (K11).
    """
    source = inspect.getsource(generate_mutation)
    assert len(re.findall(r"\bfeedback\b", source)) == 1
    assert re.search(r"def generate_mutation\([^)]*\bfeedback\b", source,
                     re.DOTALL), "the one occurrence is the parameter"


@pytest.mark.t0
def test_T_U_gen_10_one_spec_from_each_arm_takes_one_code_path(config, tmp_path):
    """T-U-gen-10 (FR-05.4, FR-18.1): one builder, one validator, no arm branch.

    `arm` is carried into the record and is read by nothing here; the only
    place it decides anything is `contract.validate`'s conditional rule, which
    §14.5 exempts by name.
    """
    both = {}
    for arm in ("seeded", "mutation"):
        extra = {} if arm == "seeded" else {
            "mutator_id": "mlir.attr.int.off_by_one",
            "mutator_seed_int": 42, "source_test_path": seed().test_paths[0]}
        both[arm] = generate_task._spec(
            seed=seed(), arm=arm, iteration=0, run_manifest_id="run-1",
            probe_dir=str(tmp_path / arm / "probes"),
            text="hw.module @Top() {}\n", tool="circt-opt",
            expected_outcome="the assertion fires",
            turn_cost={"turn": None if arm == "mutation" else "probe_write",
                       "wall_seconds": 0.5,
                       "tokens_in": None if arm == "mutation" else 11,
                       "tokens_out": None if arm == "mutation" else 7,
                       "cost_usd": None, "metered": arm == "seeded"},
            key="k", cap_bytes=262144, **extra)
        schema.validate(both[arm])

    assert both["seeded"].argv[:-1] == both["mutation"].argv[:-1]
    assert both["seeded"].tool == both["mutation"].tool
    for source in (inspect.getsource(emit_specs),
                   inspect.getsource(generate_mutation)):
        assert "_spec(" in source, "both arms call the one builder"


@pytest.mark.t0
def test_generate_mutation_emits_validated_specs_with_no_model(config, monkeypatch):
    """A4 end to end on the development set: specs, no-ops and attributed failures.

    FR-05.1's isolation is structural here: the node is handed the same
    `SeedRecord` the seeded arm gets and reads only `test_files`, and nothing
    in `mutators/` can reach a backend.
    """
    from circt_bug_loop import llm as llm_module

    monkeypatch.setattr(llm_module, "build_llm", lambda *a, **k: pytest.fail(
        "the mutation arm built a model backend (FR-05.1)"))
    monkeypatch.setattr(llm_module, "dispatch_turn", lambda *a, **k: pytest.fail(
        "the mutation arm dispatched a model turn (FR-05.1)"))
    result = call_node(generate_mutation, seed(), empty_feedback(),
                       schema.LedgerSnapshot(arm="mutation",
                                             unit="wall_clock_seconds",
                                             spent=0.0, cap=14400.0), config)

    assert len(result["specs"]) == config["per_seed_probe_cap"]
    assert result["mutator_failures"] == {}
    for spec in result["specs"]:
        schema.validate(spec)
        assert spec.arm == "mutation" and spec.mutator_id
        assert spec.source_test_path in seed().test_paths
        assert spec.turn_cost["turn"] is None and spec.turn_cost["metered"] is False
        assert Path(spec.input_path).is_file()


# ---------------------------------------------------------------------------
# 7.2 and 7.3, the two renderings
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_the_stage_one_prompt_is_a_pure_function_of_the_seed(config):
    """FR-16.5: every stage-1 variable comes from the `SeedRecord` (7.2).

    That is what contract 2.0 bought: before it, `$diff` and `$test_files` had
    no source in either object and FR-16.5 was unsatisfiable (K6).
    """
    record = seed()
    rendered = generate_task.render_seed_read(record, config)

    assert rendered == generate_task.render_seed_read(record, config)
    assert "$" not in rendered, "no substitution point is left unbound (7.2)"
    assert record.seed_sha in rendered and record.subject in rendered
    assert record.diff[:60] in rendered
    for path in record.test_paths:
        assert f"==> {path} <==" in rendered
        assert record.test_files[path][:40] in rendered
    assert record.run_lines[0] in rendered
    assert f"{config['per_seed_probe_cap']} OTHER places" in rendered
    assert "read_file(path)" in rendered and "There is no shell" in rendered


@pytest.mark.t0
def test_the_stage_two_prompt_carries_the_feedback_and_the_seeds_argv(config):
    """FR-16.1 and FR-16.5: the bundle renders, and the argv template is the seed's."""
    record = seed()
    bundle = schema.FeedbackBundle(
        run_manifest_id="run-1", seed_sha=record.seed_sha, arm="seeded",
        iteration=1, abandoned=False, terminating_condition=None,
        entries=[schema.FeedbackEntry(
            probe_id="p-000000000001", stopped_at_stage="stage_3",
            reason="parse_error", oracle_class=None, oracle_summary=None,
            reduced_text=None)])
    rendered = generate_task.render_probe_write(
        record, "a class sentence", [{"file": "a.cpp", "symbol": "f", "why": "w"}],
        bundle, "/probes", config)

    assert "p-000000000001: stopped at stage_3, parse_error" in rendered
    assert "a.cpp:f - w" in rendered
    assert "circt-opt -lower-handshake-to-hw INPUT" in rendered
    assert "The language is fixed by the seed and is mlir" in rendered
    assert "Write AT MOST 3 inputs" in rendered
    assert generate_task.render_feedback(
        schema.FeedbackBundle(run_manifest_id="r", seed_sha="s", arm="seeded",
                              iteration=0, entries=[], abandoned=False)
    ) == "There was no previous iteration."
