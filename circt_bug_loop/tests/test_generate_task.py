"""`generate_task.py` (A3): `04-Test-Plan.md` §1.6."""
import ast
import dataclasses
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
# The throwaway git repository and the no-Ray tool construction are shared with the tool tests rather than built twice.
from circt_bug_loop.tests.test_tools import (throwaway_repo,  # noqa: F401
                                             tool_servers)

pytestmark = pytest.mark.filterwarnings(
    "ignore::pydantic_settings.exceptions.IncompleteFieldDefinitionWarning")

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TURNS = FIXTURES / "generate" / "turns"
SEEDS = FIXTURES / "corpus" / "seeds"

#: The variable name the interlock reads is substituted with this one wherever a test needs the ALLOW path.
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
    """Replay recorded turn text through the one call that reaches a model."""
    def install(turns: list) -> dict:
        state = {"calls": [], "pending": list(turns)}

        def _dispatch(system_message, user_message, tools, *, stage,
                      timeout_seconds, model_id, guard=None,
                      max_tool_iterations=None):
            turn = state["pending"].pop(0)
            state["calls"].append({"prompt": user_message, "tools": list(tools),
                                   "system_message": system_message,
                                   "timeout_seconds": timeout_seconds,
                                   "model_id": model_id, "stage": stage,
                                   "max_tool_iterations": max_tool_iterations})
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


@pytest.mark.t0
def test_T_U_gen_01_the_tool_list_is_exactly_the_two_tools(replay, config,
                                                           tool_servers):  # noqa: F811
    """T-U-gen-01 (FR-04.4): `[source_read, probe_write]`, and no BashTool."""
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
    """T-U-gen-03 (FR-04.2): `emit_specs` raises E010; `validate` accepts the same spec."""
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
    """T-U-gen-05 (FR-04.1): a site that resolves stands, one that does not is counted."""
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
    # The stage-1 spend is still returned for the ledger to charge.
    assert result["logs"]["usage"]["seed_read"]["tokens_in"] == 11
    assert Path(result["logs"]["llm_probe_write.prompt.md"]).is_file()
    assert result["counters"].failed == 1 and result["counters"].completed == 0


@pytest.mark.t0
def test_a_raising_turn_leaves_its_type_message_and_traceback(replay, config):
    """D-1 (pilot 4): what raised is on disk and in the result, not lost with the turn."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": "", "raises": RuntimeError("backend said no")}])
    result = run_seeded(config)

    assert result["failure_detail"] == "RuntimeError: backend said no"
    recorded = (Path(config["artefact_dir"]) / generate_task.TURN_FAILED_FILE
                ).read_text(encoding="utf-8").splitlines()
    assert recorded[:2] == ["RuntimeError", "backend said no"]
    assert any('raise turn["raises"]' in line for line in recorded[2:]), (
        "the traceback names the frame that raised")
    assert len(recorded[2:]) <= generate_task.FAILURE_TRACEBACK_LINES


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
    """T-U-gen-14 (FR-04.2): the declared argv is ignored, the template wins."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_argv"),
             "files": probe_files(["array_element.mlir"])}])
    result = run_seeded(config)

    spec, = result["specs"]
    assert spec.argv == ["-lower-handshake-to-hw", spec.input_path]
    assert "--mlir-print-ir-after-all" not in spec.argv
    # `--split-input-file` is in the seed's own template and is stripped.
    assert "--split-input-file" in seed().argv_template[0]
    assert not any(token.startswith("--split-input-file") for token in spec.argv)


@pytest.mark.t0
def test_T_U_gen_19_both_tools_are_stopped_in_a_finally(replay, config,
                                                        monkeypatch, tool_servers):  # noqa: F811
    """T-U-gen-19 (FR-19.1): no live tool server survives a turn, or a raising turn."""
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

    # A stop() that itself raises is swallowed, which is CHIA's own choice at the same place.
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
    """T-U-gen-20 (FR-04.4): the source tool on the head, the writer here."""
    replay([{"text": transcript("seed_read_ok")},
            {"text": transcript("probe_write_ok"),
             "files": probe_files(["array_element.mlir", "array_zero.mlir"])}])
    run_seeded(config)

    source_read, probe_write = tool_servers
    assert source_read.task_options == config["head_options"]
    assert probe_write.task_options == config["here_options"]
    assert source_read.task_options != probe_write.task_options


@pytest.mark.t0
def test_T_U_gen_09_the_mutation_arms_body_does_not_read_its_feedback(  # noqa: D403
        ):
    """T-U-gen-09 (FR-16.2): the identifier appears exactly once, in the parameters."""
    source = inspect.getsource(generate_mutation)
    assert len(re.findall(r"\bfeedback\b", source)) == 1
    assert re.search(r"def generate_mutation\([^)]*\bfeedback\b", source,
                     re.DOTALL), "the one occurrence is the parameter"


@pytest.mark.t0
def test_T_U_gen_10_one_spec_from_each_arm_takes_one_code_path(config, tmp_path):
    """T-U-gen-10 (FR-05.4): one builder, one validator, no arm branch."""
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
    """A4 end to end on the development set: specs, no-ops and attributed failures."""
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


def mutation_snapshot() -> schema.LedgerSnapshot:
    """The mutation arm's remaining allowance, which A4 never reads."""
    return schema.LedgerSnapshot(arm="mutation", unit="wall_clock_seconds",
                                 spent=0.0, cap=14400.0)


def stand_in_tool(tmp_path: Path, exit_status: int) -> dict:
    """A bin dir whose entry tool exits *exit_status*, and the limits it runs under."""
    bin_dir = tmp_path / f"bin{exit_status}"
    bin_dir.mkdir()
    tool = bin_dir / seed().entry_tool
    tool.write_text(f"#!/bin/sh\necho 'the tool rejected this' >&2\n"
                    f"exit {exit_status}\n", encoding="utf-8")
    tool.chmod(0o755)
    return {"bin_dir": str(bin_dir),
            "probe_limits": {"probe_wall_seconds": 60,
                             "probe_address_space_bytes": 4294967296,
                             "probe_cpu_seconds": 45,
                             "probe_output_byte_cap": 1000000}}


@pytest.mark.t0
def test_a_seed_its_entry_tool_now_rejects_is_stale_and_is_not_mutated(config,
                                                                       tmp_path):
    """Pilot 4 D-2: every mutant of a seed that no longer parses inherits the rejection."""
    config.update(stand_in_tool(tmp_path, 1))
    result = call_node(generate_mutation, seed(), empty_feedback(),
                       mutation_snapshot(), config)

    assert result["specs"] == []
    assert result["failure"] == generate_task.STALE_AT_BUILD
    assert seed().test_paths[0] in result["failure_detail"]
    assert config["run_commit"] in result["failure_detail"]
    stderr = (Path(config["artefact_dir"])
              / generate_task.STALE_STDERR_FILE).read_text(encoding="utf-8")
    assert "the tool rejected this" in stderr, "what the tool said is kept"


@pytest.mark.t0
def test_a_seed_that_still_runs_is_mutated_without_lits_own_two_options(config,
                                                                       tmp_path):
    """FR-01.9: a mutant is judged by the oracle, never by diagnostic expectations."""
    config.update(stand_in_tool(tmp_path, 0))
    record = dataclasses.replace(seed(), argv_template=[
        ["%s", "-lower-handshake-to-hw", "--split-input-file",
         "--verify-diagnostics"]])
    result = call_node(generate_mutation, record, empty_feedback(),
                       mutation_snapshot(), config)

    assert result["failure"] is None
    assert len(result["specs"]) == config["per_seed_probe_cap"]
    for spec in result["specs"]:
        assert not any("verify-diagnostics" in token or "split-input-file" in token
                       for token in spec.argv), spec.argv
    # Only the argv is stripped: lit's own annotations stay in the mutant's text.
    assert all("// RUN:" in spec.input_text for spec in result["specs"])


@pytest.mark.t0
def test_the_stage_one_prompt_is_a_pure_function_of_the_seed(config):
    """FR-16.5: every stage-1 variable comes from the `SeedRecord` (7.2)."""
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
