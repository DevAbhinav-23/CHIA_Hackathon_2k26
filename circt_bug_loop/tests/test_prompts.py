"""`prompts/` and the shared footer parser: `04-Test-Plan.md` §1.23.

`T-U-prompt-01` to `-08`. The artefacts under test are four Markdown files and
one function, so `03-LLD.md` §1.3 exempts this module from the source-to-test
mapping by name (`T-U-layout-01`'s exemption list). All tier 0: nothing here
runs a model, a tool or a git command.

**The parser is `llm.parse_json_footer`.** §7.1 calls it "one function, shared by
all four"; until the join it had two copies, one in each half, and the join put
it in `llm.py`, which is neither half (architect decision 3). These tests are
what make "one function" assertable: they call it by that one name and assert
the two halves' modules re-export nothing of their own.

**Where the fixtures come from.** The malformed footers are derived here from a
well-formed one by the single edit each names, which is the derivation
`04-Test-Plan.md` §16.7 already chose for `contract/fixtures/malformed/`: a
committed file per reason would be four files that can drift from the one rule
they illustrate. The two-block case is `fixtures/triage/turns/`'s recorded-shape
transcript, read where B7 put it rather than copied (W-14's erratum 19).
"""
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
# §8.3's prompt is rendered INSIDE A7, so A7's own mirror and its unregistered
# repository are borrowed rather than built twice (§13's rule that a fixture has
# one home).
from circt_bug_loop.tests.test_mutator_synth import (mirror,  # noqa: F401
                                                     unregistered_repo)

pytestmark = pytest.mark.t0

PROMPTS = Path(generate_task.PROMPTS)
FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: §1.1's four prompt files, and the section of `03-LLD.md` that gives each in
#: full. There is no fifth: a prompt with no section is a prompt nobody reviewed.
#:
#: §8.3's is VERSIONED, and that is the one exception (W-12c, errata row 36). A
#: frozen mutator set is write-once, so the text that produced its bytes may not
#: be edited afterwards: `mutator_synth.md` stays exactly as `set_v1.json` was
#: synthesised from it, and `mutator_synth_v2.md` is the amended text `set_v2`
#: comes from. Both answer to §8.3 and `mutator_synth.prompt_path` pairs each
#: with its `set_version`.
PROMPT_FILES = {"seed_read.md": "7.2", "probe_write.md": "7.3",
                "report_write.md": "7.4", "mutator_synth.md": "8.3",
                "mutator_synth_v2.md": "8.3"}

#: The `set_version` each §8.3 prompt file synthesises, which is what selects it.
SYNTH_VERSIONS = {"mutator_synth.md": "v1", "mutator_synth_v2.md": "v2"}

#: The two variables §7.3 and §8.3 DECLARE and no prompt text carries, named
#: here because `04-Test-Plan.md` §16.7 names them: both are supplied by their
#: caller anyway, so `safe_substitute` leaves nothing unbound either way, and
#: removing the declarations is a `03-LLD.md` change this revision did not make.
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
    """Record the keyword arguments every `Template.safe_substitute` is given.

    The four renderers are three different functions in three modules and one of
    them builds its mapping in a branch, so what each SUPPLIES is read from the
    call and never from the source: a static reading would miss the branch and
    would pass on a variable the branch does not bind.
    """

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
    """§7.4's stage-6 prompt, rendered for one candidate class.

    B7's own records are `test_triage_task.py`'s and are borrowed rather than
    built twice; the `DedupVerdict` is three fields and is built here.
    """
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


# ---------------------------------------------------------------------------
# T-U-prompt-01, -02: the shared footer parser
# ---------------------------------------------------------------------------


def test_T_U_prompt_01_the_last_block_wins():
    """T-U-prompt-01 (FR-04.8, FR-11.8): two fenced blocks, the second parses.

    CHIA's own rule for its DECISION footer: a model that reconsiders mid-answer
    leaves both blocks and the final one is the answer
    (`chia:examples/circt_issue_solver/issue_task.py:28-29`). The recorded-shape
    transcript is B7's, read where it was recorded. Fixture:
    `triage/turns/report_write_two_blocks.jsonl`. Tier 0.
    """
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
    """T-U-prompt-02 (FR-04.8, FR-11.8): each malformed footer names its reason.

    Four reasons and no fifth, none retried inside the turn and none repaired by
    guessing: a footer the parser had to guess at is a number the report could
    not be trusted with. Each case is the well-formed footer with the one edit
    its reason names. Fixture: derived inline (§16.7's rule). Tier 0.
    """
    with pytest.raises(PromptContractError) as raised:
        parse_json_footer(text, ("classification", "reason"))
    assert str(raised.value) == reason

    # Nothing is retried and nothing is repaired: the parser is pure and one
    # call with the same text raises the same reason.
    with pytest.raises(PromptContractError) as again:
        parse_json_footer(text, ("classification", "reason"))
    assert str(again.value) == reason


def test_T_U_prompt_02b_the_parser_is_one_function():
    """T-U-prompt-02 (§7.1): "one function, shared by all four", after the join.

    Until W-17 there were two copies, one in `generate_task.py` and one in
    `triage_task.py`, because the apparatus half may not import the supply half
    and the import could only run the other way (errata W-13 #1, W-10 #2). Both
    are gone: the four callers reach `llm.parse_json_footer`, and the name each
    module exposes IS that function and not a second definition. Fixture: none.
    Tier 0.
    """
    assert generate_task.parse_json_footer is parse_json_footer
    assert triage_task.parse_json_footer is parse_json_footer
    assert llm.PromptContractError is triage_task.PromptContractError

    for module in (generate_task, triage_task, mutator_synth):
        source = Path(module.__file__).read_text(encoding="utf-8")
        assert "def parse_json_footer" not in source, module.__name__
        assert "class PromptContractError" not in source, module.__name__


# ---------------------------------------------------------------------------
# T-U-prompt-03, -04: substitution
# ---------------------------------------------------------------------------


def test_T_U_prompt_03_rendering_is_safe_substitute_and_never_format():
    """T-U-prompt-03 (FR-16.5): `Template.safe_substitute`, never `str.format`.

    Every prompt carries MLIR braces and one carries shell braces, so a
    `str.format` render would raise on the first `{` it met; and an undefined
    `$name` survives as itself rather than raising, which is what makes an
    unbound variable a visible defect in the rendered prompt instead of a
    crash. Fixture: the committed prompts. Tier 0.
    """
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
    """T-U-prompt-04 (FR-04.1, FR-11.1, FR-16.5): declared here, supplied there.

    Two directions. No `$name` a prompt file carries is left unbound by its
    caller, which is what makes FR-16.5's prompt-byte replay true rather than
    hoped for; and no variable a caller supplies is unknown to its file, except
    the two `04-Test-Plan.md` §16.7 names, `$probe_dir` and `$issue_digest`,
    which `03-LLD.md` §7.3 and §8.3 declare and no prompt text carries.
    Fixture: the committed prompts and `corpus/seeds/`. Tier 0.
    """
    capture = _Capture(monkeypatch)
    _render_one(name, monkeypatch, tmp_path, mirror, unregistered_repo)

    text = declared(prompt_text(name))
    assert text, f"{name} declares no substitution variable at all"
    unbound = text - capture.supplied
    assert unbound == set(), f"{name} leaves {sorted(unbound)} unbound"
    assert capture.supplied - text == DECLARED_UNUSED.get(name, set())


def test_T_U_prompt_04b_stage_ones_variables_come_from_the_seed_record():
    """T-U-prompt-04 (FR-16.5): §7.2's seven come from the `SeedRecord` alone.

    Six of the seven are seed fields and the seventh, `$max_sites`, is
    `budget.yaml`'s `per_seed_probe_cap`; nothing comes from the filesystem, from
    a tool or from a previous turn. `$diff` is `seed.diff` and `$test_files` is
    `seed.test_files` rendered one `==> <path> <==`-headed block per entry in
    `test_paths` order, which is what makes the stage-1 prompt reproducible from
    the record alone. Before contract 2.0 neither had a source in either object.
    Fixture: `corpus/seeds/nine_test_files.json`. Tier 0.
    """
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
    """T-U-prompt-07 (FR-08.6, FR-11.9, FR-16.5): no `$name` survives either.

    For a `differential` candidate the six primary variables are bound to the
    literal `NOT_APPLICABLE` and the three differential ones come off the
    `DifferentialVerdict`; for a primary candidate the reverse. `safe_substitute`
    leaves an unbound `$name` in place rather than raising, which is why an
    unbound `$frames` in a prompt is a defect and not a blank, and why this test
    reads the RENDERED text and not the mapping. Fixture: the committed prompt.
    Tier 0.
    """
    names = declared(prompt_text("report_write.md"))
    for oracle_class in ("assertion", "differential"):
        rendered = _render_report(oracle_class)
        left = [f"${n}" for n in names if f"${n}" in rendered]
        assert left == [], f"{oracle_class}: {left} survived the render"
    # Both fillings use the literal, in opposite directions: a differential
    # candidate has no assertion text and a primary one has no second simulator.
    differential = _render_report("differential")
    primary = _render_report("assertion")
    assert differential.count(triage_task.NOT_APPLICABLE) > primary.count(
        triage_task.NOT_APPLICABLE)
    assert 'isa<To>(Val) && "bad cast"' in primary
    assert 'isa<To>(Val) && "bad cast"' not in differential


# ---------------------------------------------------------------------------
# T-U-prompt-05, -06, -08: what the prompts do and do not say
# ---------------------------------------------------------------------------


def test_T_U_prompt_05_report_write_is_not_chias_writeup():
    """T-U-prompt-05 (FR-11.5): a separate file, and no `Fixes #<number>` line.

    An issue report is not a pull-request description: CHIA's `writeup.md` asks
    for a closing keyword, and a keyword in a report that is filed as an ISSUE
    would ask a maintainer's tracker to close something. Fixture: the committed
    prompt. Tier 0.
    """
    text = prompt_text("report_write.md")
    assert not re.search(r"Fixes\s+#", text)
    assert "pull request" not in text.lower()
    for name in PROMPT_FILES:
        assert (PROMPTS / name).is_file()
    assert sorted(p.name for p in PROMPTS.glob("*.md")) == sorted(PROMPT_FILES)


def test_T_U_prompt_06_five_files_per_turn_for_stages_1_2_and_6():
    """T-U-prompt-06 (FR-04.6, FR-11.7): the raw output is persisted whatever happens.

    FR-04.6 requires five files per turn and §6.5 listed four; the prompt is the
    fifth and takes the name `triage_task` gave it (errata W-13 #13). Both
    producers write the same five suffixes under the same `llm_<stage>` stem, and
    A3's are written in a `finally`, so a turn that raised is as inspectable as
    one that returned. Fixture: none. Tier 0.
    """
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
    """T-U-prompt-09 (FR-05.2, FR-05.5): what set_v1 was lost to, said out loud.

    §8.3's first prompt never named the engine that compiles `pattern`, and the
    model answered with ten variable-width look-behinds PCRE accepts and
    Python's `re` refuses, so step 4 dropped ten of twenty-two mutators for one
    unstated sentence (errata row 33). The v2 file names Python's `re`, gives
    the refused construct as an example, and asks for the two kinds v1 produced
    none of. This test is what stops the sentence being edited back out; it does
    NOT assert the model obeys it, which is §10 of the measurement. Fixture: the
    committed prompt. Tier 0.
    """
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
    """T-U-prompt-08 (FR-04.4, NFR-03): three read methods, and no fourth.

    The stage-1 and stage-2 prompts describe `read_file`, `grep` and `list_dir`
    and no shell, no build tool and no test tool; the string `bash` appears in
    none of the four files. It is true by CONSTRUCTION and not by instruction
    since `BashTool`'s withdrawal, and this test is what keeps the prose from
    drifting back: a prompt that offered a shell would be describing a tool the
    agent is not given. Fixture: the committed prompts. Tier 0.
    """
    for name in PROMPT_FILES:
        text = prompt_text(name).lower()
        assert "bash" not in text, name
        assert "shell" not in text or "no shell" in text, name

    stage_1 = prompt_text("seed_read.md")
    for method in ("read_file", "grep", "list_dir"):
        assert f"{method}(" in stage_1, method
    assert "no shell, no build tool" in stage_1

    # Stage 2's rule 5 is the same statement in the same place, and it is now
    # true BY CONSTRUCTION rather than by instruction: the tool list handed to
    # the turn is `[source_read, probe_write]` and holds nothing that runs a
    # compiler (`T-U-gen-01`).
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
    # 8.3's offline synthesis renders its prompt INSIDE the node, so A7 is run
    # as far as its one turn and the turn is what refuses.
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
