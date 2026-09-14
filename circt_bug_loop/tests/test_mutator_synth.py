"""`mutator_synth.py` (A7): `04-Test-Plan.md` §1.8, `T-U-msyn-01` to `-10`."""
import json
import subprocess
from pathlib import Path

import pytest

from circt_bug_loop import llm, mutator_synth, mutators
from circt_bug_loop.mutator_synth import (MutatorSynthError, synthesise_mutators)
from circt_bug_loop.store import LoopStore
from circt_bug_loop.tests.conftest import call_node

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "synth"

#: M9, measured 2026-09-13.
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
    # One closed issue that is NOT a bug.
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

        def _dispatch(system_message, user_message, tools, *, stage,
                      timeout_seconds, model_id, guard=None):
            state["calls"].append({"prompt": user_message, "tools": list(tools),
                                   "system_message": system_message,
                                   "timeout_seconds": timeout_seconds,
                                   "model_id": model_id, "stage": stage})
            return {"result": text, "stream": text, "stderr": "", "success": True,
                    "usage": {"tokens_in": 900, "tokens_out": 300,
                              "num_turns": 1, "model": MODEL_ID}}

        monkeypatch.setattr(llm, "dispatch_turn", _dispatch)
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


@pytest.mark.t0
def test_T_U_msyn_01_a_registered_campaign_refuses_before_any_turn(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-01 (FR-05.2): step 1 is first, and the turn count for it is zero."""
    state = turn(transcript("mutator_synth_ok"))
    root = Path(unregistered_repo)
    (root / "circt_bug_loop").mkdir()
    (root / "circt_bug_loop" / "budget.yaml").write_text("arm_window_seconds: 1\n",
                                                         encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=b", "-c", "user.email=b@l", "commit", "-q",
         "-m", "budget.yaml lands, and registers nothing")

    assert mutator_synth.registration_commit(unregistered_repo) == ""
    assert run(mirror, unregistered_repo, tmp_path)["mutators_written"]
    assert len(state["calls"]) == 1

    _git(root, "-c", "user.name=b", "-c", "user.email=b@l", "tag", "-a",
         "registration/campaign-01", "-m", "the pre-registration")
    registration = _git(root, "rev-parse", "registration/campaign-01^{commit}")
    assert mutator_synth.registration_commit(unregistered_repo) == registration

    state["calls"].clear()
    with pytest.raises(MutatorSynthError) as raised:
        run(mirror, unregistered_repo, tmp_path, set_version="v2")
    assert raised.value.reason == "already_registered"
    assert raised.value.detail == registration
    assert state["calls"] == [], "a turn was dispatched before the refusal"
    assert [p.name for p in (tmp_path / "sets").iterdir()] == ["set_v1.json"]


@pytest.mark.t0
def test_T_U_msyn_02_the_provenance_comes_from_the_run_and_never_from_the_model(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-02 (FR-05.2): five fields, all filled from the run."""
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
    # None of the five is anything the model wrote.
    assert "llvm/circt" not in transcript("mutator_synth_ok")


@pytest.mark.t0
def test_T_U_msyn_03_the_declaration_names_its_input_its_date_and_its_digest(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-03 (FR-05.8): the one place the mutation arm sees bug reports."""
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

    with pytest.raises(llm.PromptContractError) as raised:
        run(mirror, unregistered_repo, tmp_path)
    assert str(raised.value) == "no_block"
    assert not list((tmp_path / "sets").iterdir())


@pytest.mark.t0
def test_T_U_msyn_05_the_freeze_is_canonical_json_and_records_the_count(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-05 (FR-05.2): 2.3's canonical form, and A-21's measured 487."""
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
    # 8.1's `frozen`, which A7 is the only thing that sets (W-12).
    assert document["frozen"] is True
    assert result["counters"].stage == "synthesis"
    # The written set is loadable by the arm that will run it.
    loaded = mutators.load_set(result["path"], expected_sha=result["set_sha256"])
    assert [mutator["id"] for mutator in loaded["mutators"]] == [
        "mlir.attr.int.off_by_one", "sv.range.msb.zero", "any.line.duplicate"]


@pytest.mark.t0
def test_T_U_msyn_06_the_input_is_the_mirror_and_the_prompt_carries_it(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-06 (FR-05.2): the closed bug rows, ordered, and no request."""
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
    """T-U-msyn-07 (FR-05.2): eight failures, eight drops, one survivor."""
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
    """T-U-msyn-08 (FR-05.2): a second call raises and leaves the file untouched."""
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


@pytest.mark.t0
def test_T_U_msyn_10_the_prompt_is_versioned_with_the_set_it_freezes(
        mirror, unregistered_repo, turn, tmp_path):
    """T-U-msyn-10 (FR-05.2): `set_v2` renders `mutator_synth_v2.md`."""
    assert mutator_synth.prompt_path("v2").name == "mutator_synth_v2.md"
    assert mutator_synth.prompt_path("v1").name == "mutator_synth.md"
    assert mutator_synth.prompt_path("v99").name == "mutator_synth.md"

    state = turn(transcript("mutator_synth_ok"))
    run(mirror, unregistered_repo, tmp_path, set_version="v2")
    prompt = state["calls"][0]["prompt"]
    assert "python 3.10's `re`" in prompt.lower(), "v2's own text reached the turn"
    assert "$issues" not in prompt and "$issue_count" not in prompt
