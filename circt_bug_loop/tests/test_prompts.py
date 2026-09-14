"""`prompts/` and the shared footer parser: `04-Test-Plan.md` §1.23."""
import inspect
import json
import re
from pathlib import Path
from string import Template

import pytest

from circt_bug_loop import (generate_task, llm, mutator_synth, mutators,
                            triage_task)
from circt_bug_loop.contract import schema
from circt_bug_loop.llm import PromptContractError, parse_json_footer
# §8.3's prompt is rendered INSIDE A7.
from circt_bug_loop.tests.test_mutator_synth import (mirror,  # noqa: F401
                                                     unregistered_repo)

pytestmark = pytest.mark.t0

PROMPTS = Path(generate_task.PROMPTS)
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: §1.1's four prompt files, and the section of `03-LLD.md` that gives each in full.
PROMPT_FILES = {"seed_read.md": "7.2", "probe_write.md": "7.3",
                "report_write.md": "7.4", "mutator_synth.md": "8.3",
                "mutator_synth_v2.md": "8.3"}

#: The `set_version` each §8.3 prompt file synthesises, which is what selects it.
SYNTH_VERSIONS = {"mutator_synth.md": "v1", "mutator_synth_v2.md": "v2"}

#: The two variables §7.3 and §8.3 DECLARE and no prompt text carries.
DECLARED_UNUSED = {"probe_write.md": {"probe_dir"},
                   "mutator_synth.md": {"issue_digest"},
                   "mutator_synth_v2.md": {"issue_digest"}}

#: FR-04.6's five per-turn files, by the suffix each takes (§6.5, W-13 #13).
TURN_SUFFIXES = (".prompt.md", ".md", ".stderr", ".jsonl", ".usage.json")


def prompt_text(name: str) -> str:
    """One committed prompt file's text."""
    return (PROMPTS / name).read_text(encoding="utf-8")


def declared(text: str) -> set:
    """Every `$name` and `${name}` a prompt file carries, as `Template` reads them."""
    return {match.group("named") or match.group("braced")
            for match in Template.pattern.finditer(text)
            if match.group("named") or match.group("braced")}


class _Capture:
    """Record the keyword arguments every `Template.safe_substitute` is given."""

    def __init__(self, monkeypatch):
        self.supplied: set = set()
        original = Template.safe_substitute

        def recording(inner, *args, **kwargs):
            self.supplied |= set(kwargs)
            for mapping in args:
                self.supplied |= set(mapping)
            return original(inner, *args, **kwargs)

        monkeypatch.setattr(Template, "safe_substitute", recording)


def seed() -> schema.SeedRecord:
    """The corpus's nine-test-file seed, read back through the contract."""
    return schema.from_json(
        (FIXTURES / "corpus" / "seeds" / "nine_test_files.json").read_text(
            encoding="utf-8"), schema.SeedRecord)


def _render_report(oracle_class: str) -> str:
    """§7.4's stage-6 prompt, rendered for one candidate class."""
    from circt_bug_loop.store import DedupVerdict
    from circt_bug_loop.tests.test_triage_task import (_candidate, _manifest,
                                                       _verdict)

    dedup = DedupVerdict(probe_id="p-01", verdict="new",
                         evidence=dict.fromkeys(triage_task._EVIDENCE_KEYS))
    return triage_task._render_prompt(
        _candidate(Path("/tmp"), oracle_class=oracle_class), None,
        _verdict(oracle_class, assertion_text='isa<To>(Val) && "bad cast"',
                 assertion_site="/workspace/circt/lib/A.cpp:10"),
        dedup, None, _manifest(), {"model_id": "gemini-3.8-flash"})


def footer(body: str) -> str:
    """A turn's text ending in one fenced json block carrying *body*."""
    return f"Some prose about the input.\n\n```json\n{body}\n```\n"


def test_T_U_prompt_01_the_last_block_wins():
    """T-U-prompt-01 (FR-04.8): two fenced blocks, the second parses."""
    text = json.loads((FIXTURES / "triage" / "turns"
                       / "report_write_two_blocks.jsonl").read_text())["result"]
    assert text.count("```json") == 2
    answer = parse_json_footer(text, ("classification", "reason"))
    assert answer["classification"] == "bug", "the SECOND block, not the first"
    assert "invalid_input" in text, "and the first block said otherwise"

    # The rule stated on its own, so it cannot be an accident of the fixture.
    two = footer('{"k": 1}') + footer('{"k": 2}')
    assert parse_json_footer(two, ("k",))["k"] == 2


@pytest.mark.parametrize("text,reason", [
    ("no fence at all, just prose\n", "no_block"),
    ("```json\n{not json,}\n```\n", "not_json"),
    ("```json\n[1, 2, 3]\n```\n", "not_object"),
    ('```json\n{"classification": "bug"}\n```\n', "missing:reason"),
])
def test_T_U_prompt_02_the_four_malformed_footers(text, reason):
    """T-U-prompt-02 (FR-04.8): each malformed footer names its reason."""
    with pytest.raises(PromptContractError) as raised:
        parse_json_footer(text, ("classification", "reason"))
    assert str(raised.value) == reason

    # Nothing is retried and nothing is repaired.
    with pytest.raises(PromptContractError) as again:
        parse_json_footer(text, ("classification", "reason"))
    assert str(again.value) == reason


def test_T_U_prompt_02b_the_parser_is_one_function():
    """T-U-prompt-02 (§7.1): "one function, shared by all four", after the join."""
    assert generate_task.parse_json_footer is parse_json_footer
    assert triage_task.parse_json_footer is parse_json_footer
    assert llm.PromptContractError is triage_task.PromptContractError

    for module in (generate_task, triage_task, mutator_synth):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "def parse_json_footer" not in source, module.__name__
        assert "class PromptContractError" not in source, module.__name__


def test_T_U_prompt_03_rendering_is_safe_substitute_and_never_format():
    """T-U-prompt-03 (FR-16.5): `Template.safe_substitute`, never `str.format`."""
    for renderer in (generate_task._render, triage_task._render_prompt,
                     mutator_synth.synthesise_mutators._chia_original):
        source = inspect.getsource(renderer)
        assert ".format(" not in source, renderer

    braces = "keep {these} and %t and $unbound"
    assert Template(braces).safe_substitute(other="x") == braces

    # And the committed prompts really do carry braces a formatter would choke on.
    assert any("{" in prompt_text(name) for name in PROMPT_FILES)


@pytest.mark.parametrize("name", sorted(PROMPT_FILES))
def test_T_U_prompt_04_every_variable_is_declared_and_supplied(
        name, monkeypatch, tmp_path, mirror, unregistered_repo):  # noqa: F811
    """T-U-prompt-04 (FR-04.1): declared here, supplied there."""
    capture = _Capture(monkeypatch)
    _render_one(name, monkeypatch, tmp_path, mirror, unregistered_repo)

    text = declared(prompt_text(name))
    assert text, f"{name} declares no substitution variable at all"
    unbound = text - capture.supplied
    assert unbound == set(), f"{name} leaves {sorted(unbound)} unbound"
    assert capture.supplied - text == DECLARED_UNUSED.get(name, set())


def test_T_U_prompt_04b_stage_ones_variables_come_from_the_seed_record():
    """T-U-prompt-04 (FR-16.5): §7.2's seven come from the `SeedRecord` alone."""
    record = seed()
    cfg = {"per_seed_probe_cap": 3}
    rendered = generate_task.render_seed_read(record, cfg)

    assert record.seed_sha in rendered and record.subject in rendered
    assert record.diff in rendered
    assert "\n".join(record.run_lines) in rendered
    assert record.entry_tool in rendered
    blocks = generate_task.render_test_files(record)
    assert blocks in rendered
    assert [line for line in blocks.splitlines() if line.startswith("==> ")] == [
        f"==> {path} <==" for path in record.test_paths]
    # Byte-identical on a second render from the same two inputs (FR-16.5).
    assert rendered == generate_task.render_seed_read(seed(), dict(cfg))


def test_T_U_prompt_07_the_stage_six_prompt_has_two_fillings():
    """T-U-prompt-07 (FR-08.6): no `$name` survives either."""
    names = declared(prompt_text("report_write.md"))
    for oracle_class in ("assertion", "differential"):
        rendered = _render_report(oracle_class)
        left = [f"${n}" for n in names if f"${n}" in rendered]
        assert left == [], f"{oracle_class}: {left} survived the render"
    # Both fillings use the literal, in opposite directions.
    differential = _render_report("differential")
    primary = _render_report("assertion")
    assert differential.count(triage_task.NOT_APPLICABLE) > primary.count(
        triage_task.NOT_APPLICABLE)
    assert 'isa<To>(Val) && "bad cast"' in primary
    assert 'isa<To>(Val) && "bad cast"' not in differential


def test_T_U_prompt_08_every_tool_bearing_turn_states_its_budget():
    """T-U-prompt-08 (W-18d): the cap is in the prompt, filled from the stage's own."""
    for name in ("seed_read.md", "probe_write.md", "report_write.md"):
        text = prompt_text(name)
        assert "at most $max_tool_calls tool calls" in text, name
        for instruction in ("grep", "read_file", "first_line",
                            "from what you have already read"):
            assert instruction in text, (name, instruction)

    # Filled from the STAGE's registered cap, not from one number for the run.
    cfg = {"per_seed_probe_cap": 3,
           "max_tool_iterations": {"stage_1": 12, "stage_2": 9, "stage_6": 6}}
    assert "at most 12 tool calls" in generate_task.render_seed_read(seed(), cfg)
    written = generate_task.render_probe_write(
        seed(), "a class", [], schema.FeedbackBundle(
            run_manifest_id="r", seed_sha=seed().seed_sha, arm="seeded",
            iteration=0, entries=[], abandoned=False,
            terminating_condition=None), "/tmp/probe", cfg)
    assert "at most 9 tool calls" in written

    # And with no registered cap it states the backend's own default, never zero.
    assert "at most 100 tool calls" in generate_task.render_seed_read(
        seed(), {"per_seed_probe_cap": 3})


def test_T_U_prompt_05_report_write_is_not_chias_writeup():
    """T-U-prompt-05 (FR-11.5): a separate file, and no `Fixes #<number>` line."""
    text = prompt_text("report_write.md")
    assert not re.search(r"Fixes\s+#", text)
    assert "pull request" not in text.lower()
    for name in PROMPT_FILES:
        assert (PROMPTS / name).is_file()
    assert sorted(p.name for p in PROMPTS.glob("*.md")) == sorted(PROMPT_FILES)


def test_T_U_prompt_06_five_files_per_turn_for_stages_1_2_and_6():
    """T-U-prompt-06 (FR-04.6): the raw output is persisted whatever happens."""
    body = inspect.getsource(generate_task._turn)
    assert "finally:" in body
    for suffix in TURN_SUFFIXES:
        assert suffix in body, suffix

    persisted = inspect.getsource(triage_task._persist_turn)
    for suffix in TURN_SUFFIXES:
        assert f"llm_report_write{suffix}" in persisted, suffix
    assert len(TURN_SUFFIXES) == 5


@pytest.mark.t0
def test_T_U_prompt_09_the_v2_synthesis_prompt_names_the_engine_and_the_kinds():
    """T-U-prompt-09 (FR-05.2): what set_v1 was lost to, said out loud."""
    text = prompt_text("mutator_synth_v2.md")
    lowered = text.lower()

    # The engine, by name, with the construct that was actually refused.
    assert "python 3.10's `re`" in lowered
    assert "look-behind" in lowered and "fixed width" in lowered
    assert "(?<=depth" in text, "the refused example, as the turn wrote it"
    assert "\\K" in text, "and the other PCRE-only forms it must not use"

    # The three kinds, and the two minimums v1 had none of.
    for kind in mutators.KINDS:
        assert f'`{kind}`' in text or f'"{kind}"' in text, kind
    assert "AT LEAST TWO `argv`" in text and "AT LEAST TWO `line`" in text
    for language in mutators.LANGUAGES:
        assert f"`{language}`" in text, language

    # And the replacement rules, which are `mutator_synth.check_entry`'s own.
    assert "never empty" in lowered
    for operation in mutators.SEQUENCE_OPERATIONS:
        assert f"`{operation}`" in text, operation
    for operation in mutators.NUMERIC_OPERATIONS:
        assert f"`{operation}`" in text, operation

    # v1's text is UNTOUCHED: it is the record of the bytes set_v1.json holds.
    assert "python 3.10" not in prompt_text("mutator_synth.md").lower()


def test_T_U_prompt_08_no_prompt_offers_a_shell():
    """T-U-prompt-08 (FR-04.4): three read methods, and no fourth."""
    for name in PROMPT_FILES:
        text = prompt_text(name).lower()
        assert "bash" not in text, name
        assert "shell" not in text or "no shell" in text, name

    stage_1 = prompt_text("seed_read.md")
    for method in ("read_file", "grep", "list_dir"):
        assert f"{method}(" in stage_1, method
    assert "no shell, no build tool" in stage_1

    # Stage 2's rule 5 is the same statement in the same place.
    stage_2 = prompt_text("probe_write.md")
    assert "You cannot run the compiler" in stage_2
    assert "write_probe" in stage_2 and "read-only source tools" in stage_2


def _render_one(name: str, monkeypatch, tmp_path, mirror, repo) -> str:  # noqa: F811
    """Render one prompt through the caller `03-LLD.md` gives it, and nothing else."""
    if name == "seed_read.md":
        return generate_task.render_seed_read(seed(), {"per_seed_probe_cap": 3})
    if name == "probe_write.md":
        return generate_task.render_probe_write(
            seed(), "a null dereference in the folder", [],
            schema.FeedbackBundle(run_manifest_id="r", seed_sha=seed().seed_sha,
                                  arm="seeded", iteration=0, entries=[],
                                  abandoned=False, terminating_condition=None),
            "/artefacts/run/seed/iter_0/probes", {"per_seed_probe_cap": 3})
    if name == "report_write.md":
        return _render_report("assertion")
    # 8.3's offline synthesis renders its prompt INSIDE the node.
    rendered = {}

    def _dispatch(system_message, user_message, tools, *, stage,
                  timeout_seconds, model_id, guard=None):
        rendered["text"] = user_message
        raise PromptContractError("no_block")

    monkeypatch.setattr(llm, "dispatch_turn", _dispatch)
    with pytest.raises(PromptContractError):
        mutator_synth.synthesise_mutators._chia_original(
            mirror, repo, SYNTH_VERSIONS[name], ("mlir", "fir", "sv", "any"), 20,
            {"model_id": "gemini-3.8-flash", "set_dir": str(tmp_path / "sets"),
             "mirror_refreshed_utc": "2026-09-13T00:00:00+00:00"})
    return rendered["text"]


def test_T_U_prompt_10_both_reading_turns_are_told_the_build_commit():
    """T-U-prompt-10 (W-23): the syntax must exist where the tools are built."""
    stage_2 = prompt_text("probe_write.md")
    for phrase in ("THE SOURCE YOU CAN READ IS THE BUILD COMMIT",
                   "must\nexist AT THE BUILD COMMIT",
                   "grep the source for each one before you write it",
                   "may be stale", "does not parse"):
        assert phrase in stage_2, phrase

    stage_1 = prompt_text("seed_read.md")
    assert "BOTH must exist AT THE BUILD COMMIT" in stage_1
    assert "check each one with grep before you name it" in stage_1

    # It survives the render, with the seed's own cap substituted into it.
    written = generate_task.render_probe_write(
        seed(), "a class", [], schema.FeedbackBundle(
            run_manifest_id="r", seed_sha=seed().seed_sha, arm="seeded",
            iteration=0, entries=[], abandoned=False,
            terminating_condition=None), "/tmp/probe", {"per_seed_probe_cap": 4})
    assert "THE SOURCE YOU CAN READ IS THE BUILD COMMIT" in written
    assert "spends one of the 4 inputs this seed gets" in written
    assert "$cap" not in written
    assert "BOTH must exist AT THE BUILD COMMIT" in generate_task.render_seed_read(
        seed(), {"per_seed_probe_cap": 4})
