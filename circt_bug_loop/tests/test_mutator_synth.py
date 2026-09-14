"""`mutator_synth.py` (A7): `04-Test-Plan.md` §1.8, `T-U-msyn-01` to `-09`.

The turn is mocked at the one call that reaches a model, `dispatch_turn`, and
the three constructed transcripts of `fixtures/synth/` are what it returns; the
refusal, the query, the six drop checks, the provenance and the write-once
freeze are all the real code. No model runs, no GitHub request is made, and
`BUGLOOP_ALLOW_LIVE_MODEL` is never set: `build_llm` is substituted alongside
the turn, so the interlock is never even reached.

The mirror is a real `loop.db` built through `store.LoopStore` and filled with
constructed rows at M9's two measured counts, 487 closed `label:bug` issues and
101 open ones. The counts are the measurement; the rows are not recordings and
`fixtures/synth/README.md` says so.
"""
import json
import subprocess
from pathlib import Path

import pytest

from circt_bug_loop import generate_task, mutator_synth, mutators
from circt_bug_loop.mutator_synth import (MutatorSynthError, synthesise_mutators)
from circt_bug_loop.store import LoopStore
from circt_bug_loop.tests.conftest import call_node

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "synth"

#: M9, measured 2026-09-13: the full closed `label:bug` history of llvm/circt,
#: and the open ones it is counted against (`03-LLD.md` §8.3 step 2).
CLOSED_BUG_ISSUES = 487
OPEN_BUG_ISSUES = 101

MODEL_ID = "gemini-3.8-flash"


def transcript(name: str) -> str:
    """One constructed synthesis turn of `fixtures/synth/turns/`."""
    return (FIXTURES / "turns" / f"{name}.md").read_text(encoding="utf-8")


@pytest.fixture
def mirror(tmp_path) -> str:
    """A real `loop.db` whose `issue_mirror` holds M9's two counts."""
    path = str(tmp_path / "loop.db")
    store = LoopStore(path)
    rows = []
    for number in range(1, CLOSED_BUG_ISSUES + OPEN_BUG_ISSUES + 1):
        closed = number <= CLOSED_BUG_ISSUES
        rows.append({
            "issue_number": number,
            "title": f"[HW] crash on a zero-width value ({number})",
            "body": f"circt-opt asserts on a zero-width operand, case {number}.",
            "labels_json": json.dumps(["bug", "HW"] if closed else ["bug"]),
            "state": "closed" if closed else "open",
            "url": f"https://github.com/llvm/circt/issues/{number}",
            "mirrored_utc": "2026-09-13T00:00:00+00:00"})
    # One closed issue that is NOT a bug, so the label filter has something to
    # exclude rather than merely something to pass.
    rows.append({"issue_number": 9001, "title": "docs typo",
                 "body": "a docs typo", "labels_json": json.dumps(["docs"]),
                 "state": "closed", "url": "https://example.invalid/9001",
                 "mirrored_utc": "2026-09-13T00:00:00+00:00"})
    store.insert_many("issue_mirror", rows)
    return path


@pytest.fixture
def unregistered_repo(tmp_path) -> str:
    """A git repository with no `budget.yaml` commit: the pre-registration is absent."""
    root = tmp_path / "repo"
    root.mkdir()
    (root / "README.md").write_text("not registered\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=b", "-c", "user.email=b@l", "commit", "-q", "-m", "one")
    return str(root)


def _git(root, *args) -> str:
    """Run one git argument vector in *root*."""
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True, timeout=60).stdout.strip()


@pytest.fixture
def turn(monkeypatch):
    """Return the one recorded turn text from the one call that reaches a model."""
    def install(text: str) -> dict:
        state = {"calls": []}
        monkeypatch.setattr(generate_task, "build_llm",
                            lambda system, timeout, model: {"model": model,
                                                            "timeout": timeout})

        def _dispatch(llm, user_message, tools):
            state["calls"].append({"prompt": user_message, "tools": list(tools),
                                   "llm": llm})
            return {"result": text, "stream": text, "stderr": "", "success": True,
                    "usage": {"tokens_in": 900, "tokens_out": 300,
                              "num_turns": 1, "model": MODEL_ID}}

        monkeypatch.setattr(generate_task, "dispatch_turn", _dispatch)
        return state

    return install


def run(mirror: str, repo: str, tmp_path, set_version: str = "v1") -> dict:
    """One synthesis, through the undecorated node (04-Test-Plan.md 0.4)."""
    return call_node(synthesise_mutators, mirror, repo, set_version,
                     ("mlir", "fir", "sv"), 20,
                     {"model_id": MODEL_ID, "set_dir": str(tmp_path / "sets"),
                      "mirror_refreshed_utc": "2026-09-13T00:00:00+00:00",
                      "synthesised_utc": "2026-09-15T12:00:00+00:00"})


@pytest.fixture(autouse=True)
def set_directory(tmp_path):
    """The freeze writes into a temporary directory, never into `mutators/`."""
    (tmp_path / "sets").mkdir()
    return tmp_path / "sets"


# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_msyn_01_a_registered_campaign_refuses_before_any_turn(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-01 (FR-05.2): step 1 is first, and the turn count for it is zero.

    The refusal is first so that no model turn is spent discovering it, and the
    fix for it is to synthesise before registering, never to edit the
    registration (FR-14.3, FR-14.7).
    """
    state = turn(transcript("mutator_synth_ok"))
    root = Path(unregistered_repo)
    (root / "circt_bug_loop").mkdir()
    (root / "circt_bug_loop" / "budget.yaml").write_text("arm_window_seconds: 1\n",
                                                         encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=b", "-c", "user.email=b@l", "commit", "-q",
         "-m", "the pre-registration")
    registration = _git(root, "rev-parse", "HEAD")

    assert mutator_synth.registration_commit(unregistered_repo) == registration

    with pytest.raises(MutatorSynthError) as raised:
        run(mirror, unregistered_repo, tmp_path)
    assert raised.value.reason == "already_registered"
    assert state["calls"] == [], "a turn was dispatched before the refusal"
    assert not list((tmp_path / "sets").iterdir())


@pytest.mark.t0
def test_T_U_msyn_02_the_provenance_comes_from_the_run_and_never_from_the_model(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-02 (FR-05.2, FR-05.8): five fields, all filled from the run."""
    turn(transcript("mutator_synth_ok"))
    result = run(mirror, unregistered_repo, tmp_path)
    document = json.loads(Path(result["path"]).read_text(encoding="utf-8"))

    assert document["synthesis_input"] == {
        "repo": "llvm/circt",
        "query": "closed issues labelled bug, the full history",
        "issues_used": CLOSED_BUG_ISSUES,
        "mirror_refreshed_utc": "2026-09-13T00:00:00+00:00",
        "issue_numbers_sha256": mutator_synth.issue_digest(
            [{"issue_number": n} for n in range(1, CLOSED_BUG_ISSUES + 1)])}
    assert document["synthesis_model"] == MODEL_ID
    assert document["synthesised_utc"] == "2026-09-15T12:00:00+00:00"
    # None of the five is anything the model wrote: the turn's own text names
    # neither a repo, nor a count, nor a date.
    assert "llvm/circt" not in transcript("mutator_synth_ok")


@pytest.mark.t0
def test_T_U_msyn_03_the_declaration_names_its_input_its_date_and_its_digest(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-03 (FR-05.8): the one place the mutation arm sees bug reports.

    FR-05.1 isolates the arm at RUN time, which is the isolation the
    head-to-head needs; D-05 feeds a model bug reports at SYNTHESIS time, which
    is Mut4All's design and is symmetric to the seeded arm's exposure to the
    same project's fixes. The set carries what the results artefact and the
    paper then have to state.
    """
    turn(transcript("mutator_synth_ok"))
    result = run(mirror, unregistered_repo, tmp_path)
    document = json.loads(Path(result["path"]).read_text(encoding="utf-8"))

    assert document["synthesis_input"]["query"].startswith("closed issues labelled bug")
    assert document["synthesised_utc"] and document["synthesis_model"]
    assert result["set_sha256"] == mutators.set_sha256(result["path"])
    assert len(result["set_sha256"]) == 64


@pytest.mark.t0
def test_T_U_msyn_04_a_malformed_footer_freezes_nothing(mirror, unregistered_repo,
                                                        turn, tmp_path):
    """T-U-msyn-04 (FR-05.2): 7.1's parser raises and no file is written."""
    turn(transcript("mutator_synth_bad"))

    with pytest.raises(generate_task.PromptContractError) as raised:
        run(mirror, unregistered_repo, tmp_path)
    assert str(raised.value) == "no_block"
    assert not list((tmp_path / "sets").iterdir())


@pytest.mark.t0
def test_T_U_msyn_05_the_freeze_is_canonical_json_and_records_the_count(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-05 (FR-05.2): 2.3's canonical form, and A-21's measured 487.

    The mirror holds 487 closed and 101 open `label:bug` issues, which is what
    M9 counted, so ADR-D-05's fallback to the 24-month fix-commit set is not
    taken and `issues_used` is the whole closed history.
    """
    turn(transcript("mutator_synth_ok"))
    result = run(mirror, unregistered_repo, tmp_path)

    text = Path(result["path"]).read_text(encoding="utf-8")
    document = json.loads(text)
    assert text == json.dumps(document, sort_keys=True, indent=2,
                              ensure_ascii=False, separators=(",", ": ")) + "\n"
    assert result["issues_used"] == CLOSED_BUG_ISSUES
    assert result["mutators_written"] == 3 and result["dropped"] == {}
    assert Path(result["path"]).name == "set_v1.json"
    assert document["format_version"] == 1 and document["set_version"] == "v1"
    assert result["counters"].stage == "synthesis"
    # The written set is loadable by the arm that will run it.
    loaded = mutators.load_set(result["path"])
    assert [mutator["id"] for mutator in loaded["mutators"]] == [
        "mlir.attr.int.off_by_one", "sv.range.msb.zero", "any.line.duplicate"]


@pytest.mark.t0
def test_T_U_msyn_06_the_input_is_the_mirror_and_the_prompt_carries_it(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-06 (FR-05.2, NFR-04): the closed bug rows, ordered, and no request.

    The query is the only source: nothing here reaches api.github.com, for the
    same reason 3.7.3's screen makes no request either.
    """
    state = turn(transcript("mutator_synth_ok"))
    issues = mutator_synth.read_mirror(mirror)

    assert len(issues) == CLOSED_BUG_ISSUES
    assert [issue["issue_number"] for issue in issues] == sorted(
        issue["issue_number"] for issue in issues)
    assert 9001 not in {issue["issue_number"] for issue in issues}, "labels filter"
    assert CLOSED_BUG_ISSUES + 1 not in {issue["issue_number"] for issue in issues}

    run(mirror, unregistered_repo, tmp_path)
    prompt = state["calls"][0]["prompt"]
    assert f"Below are {CLOSED_BUG_ISSUES} closed CIRCT issues" in prompt
    assert "== #1 [HW] crash on a zero-width value (1)" in prompt
    assert "Write about 20 mutators covering these languages: mlir, fir, sv" in prompt
    assert "$" not in prompt, "no substitution point is left unbound (8.3)"
    assert state["calls"][0]["tools"] == [], "this turn is given no tool at all"


@pytest.mark.t0
def test_T_U_msyn_07_each_check_drops_exactly_its_own_entry(mirror,
                                                            unregistered_repo,
                                                            turn, tmp_path):
    """T-U-msyn-07 (FR-05.2, FR-05.5): eight failures, eight drops, one survivor."""
    turn(transcript("mutator_synth_drops"))
    result = run(mirror, unregistered_repo, tmp_path)

    assert result["dropped"] == {
        "bad_pattern": ["mlir.pattern.uncompilable"],
        "bad_id": ["NotDotted"],
        "duplicate_id": ["mlir.attr.int.off_by_one"],
        "bad_language": ["vhdl.attr.int.zero"],
        "bad_kind": ["mlir.tree.rewrite"],
        "bad_mutates_argv": ["mlir.argv.undeclared"],
        "bad_replacement": ["mlir.line.wrong_operation"],
        "missing_field": ["mlir.attr.int.nofields"]}
    assert result["mutators_written"] == 1
    document = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert [mutator["id"] for mutator in document["mutators"]] == [
        "mlir.attr.int.off_by_one"]
    assert document["mutators"][0]["description"] == "the one entry that survives"


@pytest.mark.t0
def test_T_U_msyn_08_the_freeze_is_write_once(mirror, unregistered_repo, turn,
                                              tmp_path):
    """T-U-msyn-08 (FR-05.2): a second call raises and leaves the file untouched.

    What is reproducible is the REFERENCE and not the synthesis: a model turn is
    not a deterministic function of its prompt, so the digest
    `RunManifest.mutator_set_sha` names can never be allowed to change under a
    run.
    """
    turn(transcript("mutator_synth_ok"))
    first = run(mirror, unregistered_repo, tmp_path)
    before = Path(first["path"]).read_bytes()

    turn(transcript("mutator_synth_drops"))
    with pytest.raises(MutatorSynthError) as raised:
        run(mirror, unregistered_repo, tmp_path)
    assert raised.value.reason == "set_exists"
    assert first["path"] in str(raised.value)
    assert Path(first["path"]).read_bytes() == before


@pytest.mark.t0
def test_T_U_msyn_09_an_empty_mirror_refuses(unregistered_repo, turn, tmp_path):
    """T-U-msyn-09 (FR-05.2): a set synthesised from nothing measures nothing."""
    state = turn(transcript("mutator_synth_ok"))
    empty = str(tmp_path / "empty.db")
    LoopStore(empty)

    with pytest.raises(MutatorSynthError) as raised:
        run(empty, unregistered_repo, tmp_path)
    assert raised.value.reason == "empty_mirror"
    assert state["calls"] == [], "no turn is spent on an empty mirror"
    assert not list((tmp_path / "sets").iterdir())
