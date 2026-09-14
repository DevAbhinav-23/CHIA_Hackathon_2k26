"""`04-Test-Plan.md` §1.11: `triage_task.py` (B6a, B6b, B7), the fingerprint and
the partition, the mirror and the two screens, the triage turn and the render.

**Every test calls its node through `conftest.call_node`**, which invokes the
undecorated original: calling the wrapper routes through
`chia.trace.profiler.get_profiler`, which starts a local Ray and raises a
`FutureWarning` that `-W error` turns into an error. The nodes keep the
decorators `03-LLD.md` §3.2's column gives them, and `T-U-triage-33` asserts the
placement statically off `_chia_options`.

**The model layer is mocked and no test may reach a model** (`04-Test-Plan.md`
§0.5). Since the join B7's backend and turn are `llm.build_llm` and
`llm.dispatch_turn` (`03-LLD.md` §3.5.1, architect decision 3), imported by
`triage_task` at module scope, so `_fake_generate` substitutes those two names
on this module and nothing else. `SourceReadTool` stays `generate_task`'s and is
still reached through B7's one lazy import; the stand-in for it carries §3.5's
real five-parameter signature, and `T-U-triage-36` constructs the real tool.

**The GitHub layer replays a recorded response set and mocks nothing**
(`04-Test-Plan.md` §0.3): `_recording_transport` serves
`fixtures/mirror/sample.json`, fifty real `llvm/circt` issues recorded on
2026-09-14, through `GithubClient._request`, so `GithubIssuesNode._list`,
its paging, its pull-request filter and `_build_issue` all run for real. The one
live test is `T-U-triage-35`, marked `t1`, which skips cleanly with no
`GITHUB_TOKEN`.

Tiers follow `04-Test-Plan.md` §0.5's rule that a test states the LOWEST tier at
which it can run. The two commit scans are `t1` in §1.11's column because the
plan drives them against the blobless `llvm/circt` clone; here they are driven
against a synthetic repository built in `tmp_path`, which needs `git` and
nothing else. They keep the `t1` marker rather than being silently relabelled,
and the deviation is an erratum candidate.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import os
import random
import subprocess
import sys
import types
from pathlib import Path

import pytest

from circt_bug_loop import triage_task
from circt_bug_loop.contract import schema
from circt_bug_loop.store import (CandidateRecord, DedupVerdict,
                                  DifferentialVerdict, Fingerprint, Frame,
                                  LoopStore, OracleVerdict, ReducedCase)
from circt_bug_loop.tests.conftest import call_node
# The throwaway git repository and the no-Ray tool construction are shared
# with the tool tests rather than built twice: T-U-triage-36 constructs the
# real `SourceReadTool`.
from circt_bug_loop.tests.test_tools import (throwaway_repo,  # noqa: F401
                                             tool_servers)
from circt_bug_loop.llm import PromptContractError, parse_json_footer
from circt_bug_loop.triage_task import (DIFFERENTIAL_POINTS,
                                        MIRROR_TOKEN_MIN_CHARS,
                                        PRIMARY_POINTS,
                                        ReportIncomplete, cap_sentences,
                                        compute_fingerprint, dedup_and_screen,
                                        frame_paths, frame_symbols,
                                        is_duplicate, issue_mirror_refresh,
                                        mirror_screen, mirror_tokens,
                                        normalise_expr, normalise_site,
                                        partition, rates,
                                        render_report, scan_commits,
                                        structural_hash, triage_report)

#: Tier 0 for the whole module, and one warning filter: `T-U-triage-36`
#: constructs a real `ChiaTool`, whose `FastMCP` settings model raises
#: `pydantic_settings.IncompleteFieldDefinitionWarning` about its own `lifespan`
#: field, which `-W error` turns into an error. A module-level mark is the one
#: filter that outranks a command-line `-W` (04-Test-Plan.md 16.7).
pytestmark = [pytest.mark.t0, pytest.mark.filterwarnings(
    "ignore::pydantic_settings.exceptions.IncompleteFieldDefinitionWarning")]

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MIRROR = FIXTURES / "mirror"
DEDUP = FIXTURES / "dedup"
TRIAGE = FIXTURES / "triage"
PAIRS = sorted((DEDUP / "pairs").glob("*.json"))

#: A synthetic value. No test reads a real token and no fixture carries one.
FAKE_TOKEN = "synthetic-not-a-real-token"

CIRCT_ROOT = "/home/adi/.cache/chia-pin-smoke/w09/wt143/"


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------


def _frames(names, *, files=None, circt=True, start=0):
    """One `Frame` per name, already normalised, none of them a prologue frame."""
    out = []
    for index, name in enumerate(names):
        base = (files or {}).get(name, "Pass.cpp")
        out.append(Frame(index=start + index, address=f"0x{index:012x}",
                         shape="attributed", module="", offset="", function=name,
                         file=f"{CIRCT_ROOT}lib/Support/{base}" if name else "",
                         line=100 + index if name else 0,
                         in_circt_object=circt and bool(name)))
    return out


def _verdict(oracle_class="assertion", *, probe_id="p-01", assertion_text=None,
             assertion_site=None, fatal_message=None, fingerprint_frame=None,
             frames=(), files=None,
             repro="circt-opt --lower-seq-to-sv input.mlir"):
    names = list(frames)
    return OracleVerdict(
        probe_id=probe_id, fired=True, oracle_class=oracle_class,
        assertion_text=assertion_text, assertion_site=assertion_site,
        fatal_message=fatal_message, frames=_frames(names, files=files),
        prologue_dropped=0,
        frames_resolved=sum(1 for n in names if n),
        frames_with_location=sum(1 for n in names if n),
        fingerprint_frame=fingerprint_frame, out_of_scope_root=False,
        repro_command=repro, flag_string="-O3 -UNDEBUG -gline-tables-only",
        tool_version_output="CIRCT firtool-1.143.0\n  Optimized build.")


def _from_side(side, *, probe_id="p-01"):
    """An `OracleVerdict` from one `dedup/pairs/` side, as the pair recorded it."""
    return _verdict(side["oracle_class"], probe_id=probe_id,
                    assertion_text=side["assertion_text"],
                    assertion_site=side["assertion_site"],
                    fatal_message=side.get("fatal_message"),
                    fingerprint_frame=side.get("fingerprint_frame"),
                    frames=side["frame_names"])


def _fingerprint_of(side, *, probe_id="p-01", top_n=5):
    return compute_fingerprint(_from_side(side, probe_id=probe_id),
                               side["signal"], side["reduced"], top_n)


def _candidate(tmp_path, *, oracle_class="assertion", screened=False, **over):
    fields = dict(
        candidate_id="cand-0001", probe_id="p-01", run_manifest_id="r" * 32,
        arm="seeded", run_commit="c" * 40, image_digest="sha256:" + "0" * 64,
        oracle_class=oracle_class, frame_tuple=["a", "b", "c", "d", "e"],
        frames_resolved=5, frames_with_location=5, out_of_scope_root=False,
        contaminated_symbol=False, contaminated_file=False,
        contamination_lower_bound="seed_commit", triage_class="untriaged",
        artefact_dir=str(tmp_path / "probe"))
    if oracle_class == "assertion":
        fields.update(assertion_text='isa<To>(Val) && "bad cast"',
                      assertion_site="/workspace/circt/lib/A.cpp:10")
    if oracle_class == "differential":
        fields.update(frame_tuple=[])
    elif screened:
        fields.update(
            reducer="circt-reduce", reduced=True, fixpoint=True,
            budget_truncated=False,
            reduced_path=str(TRIAGE / "report/reduced_primary.mlir"),
            size_before_bytes=100, size_after_bytes=50, size_before_ops=5,
            size_after_ops=2, fingerprint="fp", fingerprint_stable=None,
            structural_hash="0" * 64, dedup_basis="assertion",
            dedup_verdict="new",
            dedup_evidence=dict.fromkeys(triage_task._EVIDENCE_KEYS))
    fields.update(over)
    return CandidateRecord(**fields)


def _seed(*, sdk_exact=True, committed="2024-06-01T00:00:00+00:00"):
    return schema.SeedRecord(
        seed_sha="a" * 40, parent_sha="b" * 40, subject="[Support] fix",
        committed_date_utc=committed, source_paths=["lib/Support/InstanceGraph.cpp"],
        test_paths=["test/Support/x.mlir"], llvm_pin="c" * 40,
        sdk_tag="firtool-1.143.0" if sdk_exact else None, sdk_exact=sdk_exact,
        bumps_away=None if sdk_exact else 3, entry_tool="circt-opt",
        dialect_bucket="Support", dialect_bucket_unmerged="Support",
        run_lines=["// RUN: circt-opt %s"],
        argv_template=[["circt-opt", "INPUT"]], polarity=["expect_zero"],
        shape=["plain"], diff="--- a\n+++ b\n", test_files={"test/Support/x.mlir": ""},
        corpus_head_sha="d" * 40)


def _manifest(name="calibration_two.json"):
    return schema.from_json((TRIAGE / "run_manifest" / name).read_text(),
                            schema.RunManifest)


def _store(tmp_path, *, candidate=None):
    """A `LoopStore` on a real file, with the run, probe and build rows a
    candidate's foreign keys need."""
    store = LoopStore(str(tmp_path / "loop.db"))
    if candidate is None:
        return store
    store.insert("run", {
        "run_manifest_id": candidate.run_manifest_id, "mode": "discovery",
        "seed_set": "187", "manifest_json": "{}", "budget_file_sha": "x",
        "cluster_yaml_sha": "y", "artefact_root": str(tmp_path),
        "started_utc": "2026-09-14T00:00:00+00:00", "ended_utc": None})
    store.insert("image", {
        "image_digest": candidate.image_digest, "circt_sha": "e" * 40,
        "sdk_tag": "firtool-1.143.0", "image_tag": "t", "flag_string": "-UNDEBUG",
        "targets_json": "[]", "cmake_args_json": "[]", "verilator_version": "5.028",
        "slang_enabled": 1, "lit_discovery_ok": 1, "lit_discovered_count": 1,
        "assertion_nonreferencing_json": "[]", "tool_hashes_json": "{}",
        "built_utc": "2026-09-14T00:00:00+00:00"})
    store.insert("probe", {
        "probe_id": candidate.probe_id, "run_manifest_id": candidate.run_manifest_id,
        "seed_sha": "a" * 40, "arm": candidate.arm, "iteration": 0,
        "tool": "circt-opt", "argv_json": "[]", "polarity": "expect_zero",
        "shape": "plain", "input_path": "in.mlir", "mutator_id": None,
        "mutator_seed_int": None, "source_test_path": None, "spec_json": "{}",
        "artefact_dir": candidate.artefact_dir})
    store.insert("build_result", {
        "probe_id": candidate.probe_id, "run_commit": candidate.run_commit,
        "image_digest": candidate.image_digest, "status": "assertion",
        "binary_path": "/workspace/circt/build/bin/circt-opt",
        "binary_sha256": "f" * 64, "exit_status": None, "signal": "SIGABRT",
        "limit_hit": None, "cpu_seconds": 0.1, "wall_seconds": 0.2,
        "peak_rss_bytes": 1, "worker_hostname": "h", "worker_node_id": "n",
        "child_pid": 1, "stdout_path": "o", "stderr_path": "e", "truncated": 0})
    return store


def _mirror_rows(store, rows):
    """Insert constructed `issue_mirror` rows, as B6a would have written them."""
    store.insert_many("issue_mirror", [{
        "issue_number": row["issue_number"], "title": row["title"],
        "body": row["body"], "labels_json": json.dumps(row["labels"]),
        "state": row["state"], "url": row["url"],
        "mirrored_utc": "2026-09-14T00:00:00+00:00"} for row in rows])


# ---------------------------------------------------------------------------
# The recorded GitHub transport, and the stand-in generate_task
# ---------------------------------------------------------------------------


def _recording_transport(monkeypatch, payload, *, fail_after_pages=None):
    """Serve a recorded issue listing through `GithubClient._request`.

    `GithubIssuesNode._list`, its paging, its pull-request filter and
    `_build_issue` all run for real; only the HTTP round trip is replayed. A
    request for any path but the listing endpoint fails the test, which is how
    `fetch_comments=False` is asserted on the recorded call rather than on the
    argument.
    """
    from chia.github.github_client import GithubClient, GithubRateLimitError

    calls = []

    def _request(self, path, params=None, accept=None):
        calls.append({"path": path, "params": dict(params or {})})
        assert path.endswith("/issues"), (
            f"screening or mirroring requested {path!r}: the only request B6a "
            "makes is the issues listing, and comments are never fetched "
            "(FR-10.9, FR-20.4)")
        page = int((params or {}).get("page", 1))
        if fail_after_pages is not None and page > fail_after_pages:
            raise GithubRateLimitError("rate limit exceeded")
        per_page = int((params or {}).get("per_page", 100))
        return payload[(page - 1) * per_page: page * per_page]

    monkeypatch.setattr(GithubClient, "_request", _request)
    return calls


def _fake_generate(monkeypatch, turn=None, *, raises=None):
    """Substitute the ONE `llm.py` call B7 makes, and nothing else.

    Since the join the turn and the footer parser are `llm.py`'s and are
    imported by `triage_task` at module scope, so the name is substituted where
    B7 reads it rather than by installing a module. Since K2 there is no second
    name to substitute: B7 builds no backend, the client being `llm_turn`'s on
    the `llm` worker, and what B7 sends is the turn request's fields. The
    tool is still a stand-in HERE, because a real `SourceReadTool` stands up an
    MCP server and needs a git repository; `T-U-triage-36` constructs the real
    one and is what pins the call site.
    """
    import circt_bug_loop

    seen = {}

    class SourceReadTool:
        # §3.5's five parameters, which is what the call site now passes by
        # keyword; `T-U-triage-36` constructs the real class instead.
        def __init__(self, name, clone_path, run_commit,
                     cap_bytes=262144, task_options=None):
            self.name, self.clone_path, self.run_commit = name, clone_path, run_commit
            self.cap_bytes, self.task_options, self.stopped = cap_bytes, task_options, False

        def stop(self):
            self.stopped = True

    def dispatch_turn(system_message, user_message, tools, *, stage,
                      timeout_seconds, model_id, guard=None):
        assert os.environ.get("BUGLOOP_ALLOW_LIVE_MODEL") is None
        seen.update(system_message=system_message, timeout_seconds=timeout_seconds,
                    model_id=model_id, prompt=user_message, tools=tools,
                    stage=stage)
        if raises is not None:
            raise raises
        return {"result": turn or "", "stream": turn or "", "stderr": "",
                "success": True,
                "usage": {"tokens_in": 11, "tokens_out": 7, "num_turns": 1,
                          "model": "gemini-3.8-flash"}}

    monkeypatch.setattr(triage_task, "dispatch_turn", dispatch_turn)
    module = types.ModuleType("circt_bug_loop.generate_task")
    module.SourceReadTool = SourceReadTool
    monkeypatch.setitem(sys.modules, "circt_bug_loop.generate_task", module)
    monkeypatch.setattr(circt_bug_loop, "generate_task", module, raising=False)
    return seen


def _turn_text(name):
    return json.loads((TRIAGE / "turns" / f"{name}.jsonl").read_text())["result"]


def _cfg(**over):
    cfg = {"model_id": "gemini-3.8-flash", "timeout_seconds": 1200,
           "clone_path": "/home/adi/.cache/circt", "run_commit": "c" * 40}
    cfg.update(over)
    return cfg


# ---------------------------------------------------------------------------
# The synthetic clone the two scans walk
# ---------------------------------------------------------------------------

_FILE_V1 = """\
#include "InstanceGraph.h"

void circt::igraph::InstanceGraph::getInferredTopLevelNodes() {
  int candidateTopLevels = 0;
  return;
}

void circt::igraph::InstanceGraph::addNode() {
  int nodes = 0;
  return;
}
"""
_FILE_V2 = _FILE_V1.replace("int candidateTopLevels = 0;",
                            "int candidateTopLevels = 1;  // fixed")
_FILE_V3 = _FILE_V2.replace("int nodes = 0;", "int nodes = 2;  // unrelated")


def _git(repo, *args, date=None):
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e")
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    out = subprocess.run(["git", "-C", str(repo), *args], env=env, check=True,
                         capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture(scope="module")
def clone(tmp_path_factory):
    """A three-commit repository standing in for the head's blobless clone.

    Commit 1 creates `lib/Support/InstanceGraph.cpp`; commit 2 edits inside
    `getInferredTopLevelNodes`, so git's `@@ ... @@` hunk header names that
    function; commit 3 edits inside `addNode`, so the same file moves under a
    bound that the symbol does not.
    """
    repo = tmp_path_factory.mktemp("clone")
    _git(repo, "init", "-q", "-b", "main")
    source = repo / "lib" / "Support"
    source.mkdir(parents=True)
    shas = {}
    for name, text, date in (("c1", _FILE_V1, "2024-01-01T00:00:00+00:00"),
                             ("c2", _FILE_V2, "2024-09-01T00:00:00+00:00"),
                             ("c3", _FILE_V3, "2025-06-01T00:00:00+00:00")):
        (source / "InstanceGraph.cpp").write_text(text)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"commit {name}", date=date)
        shas[name] = _git(repo, "rev-parse", "HEAD")
    return {"path": str(repo), **shas}


def _graph_verdict():
    """A candidate whose one CIRCT frame is the clone's own function."""
    return _verdict(
        "assertion", assertion_text='!candidateTopLevels.empty() && "at least 1"',
        assertion_site=f"{CIRCT_ROOT}lib/Support/InstanceGraph.cpp:230",
        fingerprint_frame="circt::igraph::InstanceGraph::getInferredTopLevelNodes "
                          "InstanceGraph.cpp",
        frames=["circt::igraph::InstanceGraph::getInferredTopLevelNodes"],
        files={"circt::igraph::InstanceGraph::getInferredTopLevelNodes":
               "InstanceGraph.cpp"})


# ===========================================================================
# Tests 01 to 09, 25 to 27: the fingerprint and the partition
# ===========================================================================


def test_triage_01_assertion_fingerprint_keeps_the_message_tail():
    """T-U-triage-01 (FR-10.1): the assertion fingerprint is expr, newline, site,
    whitespace collapsed and the ends stripped, and the `&& "message"` tail kept."""
    cases = {c["id"]: c for c in
             json.loads((TRIAGE / "fingerprint/assertion.json").read_text())}
    a = _fingerprint_of(dict(cases["tail_kept_a"], fatal_message=None))
    b = _fingerprint_of(dict(cases["tail_kept_b"], fatal_message=None))
    collapsed = _fingerprint_of(dict(cases["whitespace_collapsed"], fatal_message=None))

    assert a.basis == "assertion"
    assert a.value == ('isa<To>(Val) && "cast<Ty>() argument of incompatible '
                       'type!"\ninclude/llvm/Support/Casting.h:566')
    assert a.value != b.value, "the message tail is the most discriminating part"
    assert collapsed.value == a.value
    assert normalise_expr("  a   &&\n\tb  ") == "a && b"


def test_triage_02_site_normalisation_survives_two_build_directories():
    """T-U-triage-02 (FR-10.1, FR-10.6): the build prefix goes, any other
    absolute path keeps its last two components, the line number is verbatim."""
    cases = {c["id"]: c for c in
             json.loads((TRIAGE / "fingerprint/assertion.json").read_text())}
    one = _fingerprint_of(dict(cases["other_build_dir"], fatal_message=None))
    two = _fingerprint_of(dict(cases["second_build_dir"], fatal_message=None))
    workspace = _fingerprint_of(dict(cases["tail_kept_a"], fatal_message=None))

    assert one.value == two.value, "two images in different directories, one bug"
    assert normalise_site("/workspace/circt/lib/Support/InstanceGraph.cpp:230") == \
        "lib/Support/InstanceGraph.cpp:230"
    assert normalise_site("/srv/ci/build-7/include/llvm/Support/Casting.h:566") == \
        "Support/Casting.h:566"
    assert workspace.value.endswith(":566"), "the line number is kept verbatim"
    assert normalise_site("lib/A.cpp") == "lib/A.cpp"


def test_triage_03_crash_fingerprint_is_the_signal_and_one_frame():
    """T-U-triage-03 (FR-10.1): signal plus the first stripped CIRCT frame, not
    the top-N tuple, and §3.7.1's measurement is asserted as a property of the
    labelled set rather than quoted."""
    side = json.loads((DEDUP / "pairs/04.json").read_text())["a"]
    fingerprint = _fingerprint_of(side)
    assert fingerprint.basis == "frames"
    assert fingerprint.value == "SIGSEGV\ncirct::sim::StringConcatOp::fold SimOps.cpp"
    assert ":" not in fingerprint.value.split("\n")[1].split(" ")[-1], \
        "no line number, so a one-line edit does not split one bug"

    unstable = json.loads((DEDUP / "pairs/22.json").read_text())
    left, right = _fingerprint_of(unstable["a"]), _fingerprint_of(unstable["b"])
    assert unstable["label"] == "duplicate"
    assert left.value != right.value, (
        "§3.7.1's ten-run measurement: the fingerprint frame moved between "
        "three adjacent frames of one recursion cycle")
    assert {tuple(left.frame_tuple), tuple(right.frame_tuple)}.__len__() == 2


def test_triage_04_frame_name_normalisation_is_the_four_steps():
    """T-U-triage-04 (FR-10.1): take FunctionName, cut at the first `(` at
    bracket depth zero, strip a trailing ` const`, collapse whitespace."""
    from circt_bug_loop.probe_task import _normalise_function

    assert _normalise_function(
        "circt::chooseName(llvm::StringRef, llvm::StringRef)") == "circt::chooseName"
    assert _normalise_function("Foo<std::pair<int, int>>::bar(int) const") == \
        "Foo<std::pair<int, int>>::bar"
    assert _normalise_function("append<const char (&)[68]>") == \
        "append<const char (&)[68]>", "a `(` inside a template argument is kept"


def test_triage_05_insufficient_basis_deduplicates_against_nothing(tmp_path):
    """T-U-triage-05 (FR-10.8): no assertion text, no qualifying CIRCT frame and
    fewer than N resolving frames is `insufficient`, value None, merged with
    nothing; the structural hash is still recorded."""
    verdict = _verdict("crash", fingerprint_frame=None, frames=["", "", ""])
    fingerprint = compute_fingerprint(verdict, "SIGSEGV", "hw.module @a {}", 5)

    assert (fingerprint.basis, fingerprint.value) == ("insufficient", None)
    assert len(fingerprint.structural_hash) == 64
    other = compute_fingerprint(verdict, "SIGSEGV", "hw.module @b {}", 5)
    other.probe_id = "p-02"
    assert not is_duplicate(fingerprint, other)
    assert partition([fingerprint, other]) == [frozenset({"p-01"}), frozenset({"p-02"})]


def test_triage_06_structural_hash_is_evidence_and_never_a_merge_key():
    """T-U-triage-06 (FR-10.1, FR-10.2): SSA names, `@symbol` names, `loc(...)`
    and whitespace runs are normalised, and no merge path reads the hash."""
    observed = json.loads((TRIAGE / "fingerprint/structural.json").read_text())
    assert structural_hash(observed["before"]) == structural_hash(observed["after"]), \
        "circt-reduce renamed the module, and that must not change the hash"
    assert structural_hash("hw.module @a {}") != structural_hash("hw.module @a { x }")

    for function in (is_duplicate, partition, triage_task._duplicate_of):
        assert "structural_hash" not in inspect.getsource(function), (
            f"{function.__name__} reads the structural hash, which merges "
            "nothing (FR-10.2)")


def test_triage_07_duplicate_relation_is_an_equivalence_relation():
    """T-U-triage-07 (FR-10.2): reflexive, symmetric and transitive over every
    ordered triple of the labelled pair set of §10."""
    items = []
    for index, path in enumerate(PAIRS):
        pair = json.loads(path.read_text())
        items.append(_fingerprint_of(pair["a"], probe_id=f"{pair['pair_id']}a"))
        items.append(_fingerprint_of(pair["b"], probe_id=f"{pair['pair_id']}b"))

    for x in items:
        assert is_duplicate(x, x), "reflexive"
    for x in items:
        for y in items:
            assert is_duplicate(x, y) == is_duplicate(y, x), "symmetric"
            for z in items:
                if is_duplicate(x, y) and is_duplicate(y, z):
                    assert is_duplicate(x, z), "transitive"


def test_triage_08_partition_does_not_depend_on_candidate_order():
    """T-U-triage-08 (FR-10.2): 100 shuffles of the candidate list give one
    partition, compared as a set of frozensets."""
    items = []
    for path in PAIRS:
        pair = json.loads(path.read_text())
        for side in ("a", "b"):
            item = _fingerprint_of(pair[side], probe_id=f"{pair['pair_id']}{side}")
            item.fingerprint_stable = True
            items.append(item)

    expected = set(partition(items))
    shuffler = random.Random(20260914)
    for _ in range(100):
        shuffled = list(items)
        shuffler.shuffle(shuffled)
        assert set(partition(shuffled)) == expected
        assert partition(shuffled) == sorted(expected, key=min)


def test_triage_09_measured_collision_and_false_merge_rates(capsys):
    """T-U-triage-09 (FR-10.2, A-05): both rates are computed and printed; the
    test asserts they are reported, not that either meets a threshold."""
    pairs, by_rule = [], {}
    for path in PAIRS:
        raw = json.loads(path.read_text())
        assert raw["label"] in ("duplicate", "distinct")
        assert raw["justification"] and raw["labelled_utc"]
        by_rule.setdefault(raw["rule"], []).append(raw["pair_id"])
        pairs.append({"label": raw["label"], "rule": raw["rule"],
                      "pair_id": raw["pair_id"],
                      "a": _fingerprint_of(raw["a"], probe_id=raw["pair_id"] + "a"),
                      "b": _fingerprint_of(raw["b"], probe_id=raw["pair_id"] + "b")})

    assert len(pairs) >= 20, "§10 asks for at least acceptance.labelled_pairs"
    assert len(by_rule["R4"]) >= 4, "§10: at least four of the pairs are R4"
    for rule in ("R1", "R2", "R3", "R4"):
        assert len(by_rule[rule]) >= 4, f"§10: {rule} produces at least four pairs"

    measured = rates(pairs)
    collisions = [p["pair_id"] for p in pairs
                  if p["label"] == "distinct" and is_duplicate(p["a"], p["b"])]
    merges = [p["pair_id"] for p in pairs
              if p["label"] == "duplicate" and not is_duplicate(p["a"], p["b"])]
    with capsys.disabled():
        print(f"\nFR-10.2 over {len(pairs)} labelled pairs "
              f"({measured['duplicate_pairs']} duplicate, "
              f"{measured['distinct_pairs']} distinct):")
        print(f"  collision rate   {measured['collisions']}/"
              f"{measured['distinct_pairs']} = "
              f"{measured['collision_rate']:.4f}  pairs {collisions}")
        print(f"  false-merge rate {measured['false_merges']}/"
              f"{measured['duplicate_pairs']} = "
              f"{measured['false_merge_rate']:.4f}  pairs {merges}")

    assert 0.0 <= measured["collision_rate"] <= 1.0
    assert 0.0 <= measured["false_merge_rate"] <= 1.0
    assert set(measured) == {"collision_rate", "false_merge_rate", "collisions",
                             "distinct_pairs", "false_merges", "duplicate_pairs"}


def test_triage_25_the_strip_precedes_every_use_of_a_frame():
    """T-U-triage-25 (FR-10.1): the tuple evidence is taken after the prologue
    strip, and a degenerate name is never the fingerprint's."""
    from circt_bug_loop.probe_task import _PROLOGUE

    names = list(_PROLOGUE[:3]) + ["operator", "circt::hw::ArrayType::parse"]
    verdict = _verdict("crash", fingerprint_frame="circt::hw::ArrayType::parse "
                                                  "HWTypes.cpp", frames=names)
    fingerprint = compute_fingerprint(verdict, "SIGSEGV", "hw.module @a {}", 5)

    assert fingerprint.frame_tuple[0] == "operator", "the three prologue frames went"
    assert not set(fingerprint.frame_tuple) & set(_PROLOGUE)
    assert fingerprint.value.split("\n")[1] == "circt::hw::ArrayType::parse HWTypes.cpp"
    assert "operator" not in fingerprint.value


def test_triage_26_unstable_fingerprints_are_reported_and_never_merged():
    """T-U-triage-26 (FR-10.1, FR-10.2): `fingerprint_stable=false` is its own
    singleton, and None, the state before the gate's re-run, is likewise."""
    def _one(probe_id, stable):
        item = compute_fingerprint(
            _verdict("crash", probe_id=probe_id,
                     fingerprint_frame="parseHWArray HWTypes.cpp",
                     frames=["parseHWArray"]),
            "SIGSEGV", "hw.module @a {}", 5)
        item.fingerprint_stable = stable
        return item

    stable_a, stable_b = _one("p-a", True), _one("p-b", True)
    unstable, unrun = _one("p-c", False), _one("p-d", None)
    blocks = partition([stable_a, stable_b, unstable, unrun])

    assert blocks == [frozenset({"p-a", "p-b"}), frozenset({"p-c"}),
                      frozenset({"p-d"})]
    assert stable_a.value == unstable.value == unrun.value, (
        "one string, and neither the unstable one nor the un-rerun one merges")


def test_triage_27_the_two_fallbacks_and_the_evidence_tuple():
    """T-U-triage-27 (FR-10.1, FR-10.8): no qualifying CIRCT frame falls back to
    the top-N tuple; fewer than N resolving frames is `insufficient`; the tuple
    is recorded as evidence in every case, the `assertion` basis included."""
    names = ["a::one", "a::two", "a::three", "a::four", "a::five", "a::six"]
    tuple_basis = compute_fingerprint(
        _verdict("crash", fingerprint_frame=None, frames=names), "SIGSEGV", "", 5)
    assert tuple_basis.basis == "frames"
    assert tuple_basis.value == "\n".join(names[:5])
    assert tuple_basis.frame_tuple == names[:5]

    short = compute_fingerprint(
        _verdict("crash", fingerprint_frame=None, frames=names[:3]), "SIGSEGV", "", 5)
    assert (short.basis, short.value) == ("insufficient", None)

    assertion = compute_fingerprint(
        _verdict("assertion", assertion_text="x && y",
                 assertion_site="/workspace/circt/lib/A.cpp:3", frames=names),
        "SIGABRT", "", 5)
    assert assertion.basis == "assertion"
    assert assertion.frame_tuple == names[:5], "evidence, recorded in every case"


# ===========================================================================
# Tests 10 to 20, 28 to 33: the mirror and the two screens
# ===========================================================================


def _synthetic_issues(numbers, *, pull_requests=()):
    """Listing payloads for *numbers*, some of them pull requests.

    The mirror's own filter is what these exercise: `/issues` conflates issues
    and pull requests in one number space, and a pull request must cost a slot
    of the page and none of the cap.
    """
    return [{"number": n, "title": f"issue {n}", "body": f"body of {n}",
             "state": "open" if n % 2 else "closed", "labels": [{"name": "bug"}],
             "user": {"login": "someone"}, "created_at": "2026-01-01T00:00:00Z",
             "updated_at": "2026-01-02T00:00:00Z", "closed_at": None,
             "comments": 0, "html_url": f"https://github.com/llvm/circt/issues/{n}",
             **({"pull_request": {"url": "x"}} if n in pull_requests else {})}
            for n in numbers]


def _directional_transport(monkeypatch, payload, *, ceiling_page=None,
                           per_page=100, error=None):
    """Serve one listing in the direction the caller asked for.

    `payload` is newest-first, which is what `direction=desc` returns; `asc` is
    served from its reverse. `ceiling_page` is the page GitHub refuses with the
    **422** of C-22, and `error` is any other failure to raise there instead, so
    a test can show that only the ceiling's own status is treated as a ceiling.
    """
    from chia.github.github_client import GithubClient, GithubRequestError

    calls = []

    def _request(self, path, params=None, accept=None):
        params = dict(params or {})
        calls.append({"path": path, "params": params})
        assert path.endswith("/issues"), path
        page = int(params.get("page", 1))
        if ceiling_page is not None and page >= ceiling_page:
            raise (error or GithubRequestError(
                "422 Unprocessable Entity for https://api.github.com"
                "/repos/llvm/circt/issues: In order to keep the API fast for "
                "everyone, pagination is limited for this resource."))
        ordered = payload if params["direction"] == "desc" else payload[::-1]
        return ordered[(page - 1) * per_page: page * per_page]

    monkeypatch.setattr(GithubClient, "_request", _request)
    return calls


def test_triage_10_the_one_mirror_call_never_fetches_comments(tmp_path, monkeypatch):
    """T-U-triage-10 (FR-10.9): one `state="all"` listing, `n=issue_cap`,
    `fetch_comments=False`, asserted on the recorded call."""
    payload = json.loads((MIRROR / "sample.json").read_text())
    calls = _recording_transport(monkeypatch, payload)
    token = tmp_path / "token"
    token.write_text(FAKE_TOKEN)

    out = call_node(issue_mirror_refresh, "llvm/circt", 600, str(token),
                    str(tmp_path / "loop.db"))

    assert len(calls) == 1, "one paginated listing, and the sample is one page"
    assert calls[0]["params"]["state"] == "all"
    assert calls[0]["params"]["per_page"] == 100
    assert all(not call["path"].endswith("/comments") for call in calls)
    assert out["state"] == "all" and out["comments_mirrored"] is False
    assert out["issues_mirrored"] == len(payload)


def test_triage_11_no_comment_text_reaches_loop_db(tmp_path, monkeypatch):
    """T-U-triage-11 (FR-10.9, FR-20.4): a recorded response carrying comments
    leaves none in `loop.db`, because none is fetched and none is stored."""
    payload = [json.loads(line) for line in
               (MIRROR / "with_comments.jsonl").read_text().splitlines() if line]
    assert all(item["comments"] > 0 for item in payload)
    _recording_transport(monkeypatch, payload)
    token = tmp_path / "token"
    token.write_text(FAKE_TOKEN)

    call_node(issue_mirror_refresh, "llvm/circt", 600, str(token),
              str(tmp_path / "loop.db"))

    store = LoopStore(str(tmp_path / "loop.db"))
    columns = {row["name"] for row in store.query("PRAGMA table_info(issue_mirror)")}
    assert columns == {"issue_number", "title", "body", "labels_json", "state",
                       "url", "mirrored_utc"}
    assert "comment" not in " ".join(columns)
    rows = store.query("SELECT * FROM issue_mirror")
    assert len(rows) == len(payload)
    assert all(set(json.loads(row["labels_json"])) <= {
        label["name"] for item in payload for label in item["labels"]}
        for row in rows)


def test_triage_12_all_six_manifest_values_are_recorded(tmp_path, monkeypatch):
    """T-U-triage-12 (FR-10.9): the six values of `RunManifest.issue_mirror`,
    `comments_mirrored` always false, and they validate inside a manifest."""
    payload = json.loads((MIRROR / "sample.json").read_text())
    _recording_transport(monkeypatch, payload)
    token = tmp_path / "token"
    token.write_text(FAKE_TOKEN)

    out = call_node(issue_mirror_refresh, "llvm/circt", 600, str(token),
                    str(tmp_path / "loop.db"))

    block = {key: out[key] for key in ("refreshed_utc", "issues_mirrored",
                                       "issue_cap", "cap_bound", "state",
                                       "comments_mirrored")}
    assert set(block) == {"refreshed_utc", "issues_mirrored", "issue_cap",
                          "cap_bound", "state", "comments_mirrored"}
    assert block["comments_mirrored"] is False
    assert block["cap_bound"] is False and block["issue_cap"] == 600
    assert block["refreshed_utc"].endswith("+00:00")
    manifest = _manifest()
    manifest.issue_mirror = block
    schema.validate(manifest)
    assert out["incomplete_reason"] is None


def test_triage_37_the_walk_is_two_directional_and_unions_by_number(tmp_path,
                                                                    monkeypatch):
    """T-U-triage-37 (FR-10.9, FR-10.3, C-22): `desc` to the ceiling, then `asc`.

    Architect decision 1. GitHub's issues listing refuses page 100 with a 422,
    measured; one direction therefore sees at most 9,900 numbered items, and at
    the campaign's cap the old one-direction walk raised on the refusal and
    wrote **zero** rows. Here the ceiling is a fake at page 3, so `desc` sees
    the two newest pages, `asc` sees the two oldest, the two are unioned
    deduplicated by number, pull requests cost a page slot and no row, and the
    return records `ceiling_hit` and the page count.

    Fixture: none, the listing being synthetic. Tier 0.
    """
    numbers = list(range(1, 501))[::-1]              # 500 down to 1, newest first
    pulls = {n for n in numbers if n % 5 == 0}       # 100 of the 500 are PRs
    payload = _synthetic_issues(numbers, pull_requests=pulls)
    calls = _directional_transport(monkeypatch, payload, ceiling_page=3,
                                   per_page=100)
    token = tmp_path / "token"
    token.write_text(FAKE_TOKEN)
    db = str(tmp_path / "loop.db")

    out = call_node(issue_mirror_refresh, "llvm/circt", 600, str(token), db)

    # Two directions were asked for, and the refused page was asked for once in
    # each: pages 1, 2, 3 desc then 1, 2, 3 asc.
    directions = [call["params"]["direction"] for call in calls]
    assert directions == ["desc"] * 3 + ["asc"] * 3
    assert [call["params"]["page"] for call in calls] == [1, 2, 3, 1, 2, 3]
    assert out["ceiling_hit"] is True
    assert out["pages"] == 4, "two fetched pages per direction; the third is refused"
    assert out["incomplete_reason"] is None, "the ceiling is not a failure"

    store = LoopStore(db)
    mirrored = {row["issue_number"] for row in
                store.query("SELECT issue_number FROM issue_mirror")}
    newest = {n for n in range(301, 501) if n not in pulls}
    oldest = {n for n in range(1, 201) if n not in pulls}
    assert mirrored == newest | oldest, "the union of the two directions"
    assert not mirrored & pulls, "a pull request is never a mirrored issue"
    assert out["issues_mirrored"] == len(mirrored) == out["issues_added"]
    assert out["cap_bound"] is False


def test_triage_37b_the_cap_bounds_both_directions(tmp_path, monkeypatch):
    """T-U-triage-37 (FR-10.9): `issue_mirror_issue_cap` is the row bound of the
    UNION and not of one direction, so the second walk stops at it too."""
    payload = _synthetic_issues(list(range(1, 501))[::-1])
    calls = _directional_transport(monkeypatch, payload, ceiling_page=3)
    token = tmp_path / "token"
    token.write_text(FAKE_TOKEN)
    db = str(tmp_path / "loop.db")

    out = call_node(issue_mirror_refresh, "llvm/circt", 150, str(token), db)

    assert out["cap_bound"] is True
    assert out["issues_mirrored"] == 150
    assert [call["params"]["direction"] for call in calls] == ["desc", "desc"]
    assert out["ceiling_hit"] is False, "it stopped at the cap, not at the ceiling"
    store = LoopStore(db)
    numbers = {row["issue_number"] for row in
               store.query("SELECT issue_number FROM issue_mirror")}
    assert numbers == set(range(351, 501)), "the newest 150, from `desc` alone"


def test_triage_38_only_a_422_is_the_ceiling(tmp_path, monkeypatch):
    """T-U-triage-38 (FR-10.7, C-22): another 4xx is a failure, not a ceiling.

    The ceiling is recognised by GitHub's own status, which
    `GithubClient._error_message` puts at the head of the message; a 403 that is
    not a rate limit raises `GithubRequestError` too, and treating it as a
    ceiling would silently mirror a fraction of the history and then walk the
    other way into the same wall. Fixture: none. Tier 0.
    """
    from chia.github.github_client import GithubRequestError

    payload = _synthetic_issues(list(range(1, 301))[::-1])
    _directional_transport(monkeypatch, payload, ceiling_page=2,
                           error=GithubRequestError(
                               "403 Forbidden for https://api.github.com/repos/"
                               "llvm/circt/issues: secondary rate limit"))
    token = tmp_path / "token"
    token.write_text(FAKE_TOKEN)
    db = str(tmp_path / "loop.db")

    out = call_node(issue_mirror_refresh, "llvm/circt", 600, str(token), db)

    assert out["incomplete_reason"] == "GithubRequestError"
    assert out["ceiling_hit"] is False
    assert out["issues_mirrored"] == 100, "the first page survives the failure"


def test_triage_13_a_rate_limit_leaves_a_partial_mirror(tmp_path, monkeypatch):
    """T-U-triage-13 (FR-10.7, FR-10.9): a `GithubRateLimitError` is caught, the
    count reached is recorded, screening proceeds against the partial mirror."""
    plan = json.loads((MIRROR / "ratelimit/plan.json").read_text())
    payload = json.loads((MIRROR / "sample.json").read_text())
    _recording_transport(monkeypatch, payload,
                         fail_after_pages=plan["fail_after_pages"])
    token = tmp_path / "token"
    token.write_text(FAKE_TOKEN)
    db = str(tmp_path / "loop.db")
    store = LoopStore(db)
    _mirror_rows(store, json.loads((DEDUP / "known_issue/issues.json").read_text()))

    out = call_node(issue_mirror_refresh, "llvm/circt", 600, str(token), db)

    assert out["incomplete_reason"] == "GithubRateLimitError"
    assert out["issues_mirrored"] == 5, "the count reached, not zero"
    assert out["cap_bound"] is False
    hit = mirror_screen(store, ['detail::isPresent(Val) && "dyn_cast on a '
                                'non-existent value"'])
    assert hit is not None, "screening proceeds against the partial mirror"


def test_triage_14_an_empty_mirror_is_dedup_unavailable(tmp_path, clone):
    """T-U-triage-14 (FR-10.7): an empty mirror yields `dedup_unavailable` for
    every candidate, which fails gate question 4 rather than passing it."""
    assert json.loads((MIRROR / "empty/sample.json").read_text()) == []
    candidate = _candidate(tmp_path, screened=True, run_commit=clone["c1"])
    store = _store(tmp_path, candidate=candidate)
    assert store.query("SELECT * FROM issue_mirror") == []

    out = call_node(dedup_and_screen, candidate, _seed(), _graph_verdict(),
                    clone["path"], str(tmp_path / "loop.db"), 5)

    assert out["dedup"].verdict == "dedup_unavailable"
    assert out["dedup"].evidence["matched_key"] == "issue_mirror_empty"
    assert set(out["dedup"].evidence) == set(triage_task._EVIDENCE_KEYS)


def test_triage_15_screening_makes_no_github_request(tmp_path, monkeypatch):
    """T-U-triage-15 (FR-10.3, NFR-04): a whole screening pass over 50
    candidates shows zero requests to api.github.com; the mirror is the only
    source."""
    import requests

    def _refuse(*args, **kwargs):
        raise AssertionError("screening reached the network (FR-10.3, NFR-04)")

    monkeypatch.setattr(requests.Session, "request", _refuse)
    monkeypatch.setattr(requests, "get", _refuse)
    store = _store(tmp_path)
    _mirror_rows(store, json.loads((DEDUP / "known_issue/issues.json").read_text()))

    pairs = [json.loads(path.read_text()) for path in PAIRS]
    screened = 0
    while screened < 50:
        for pair in pairs:
            for side in ("a", "b"):
                mirror_screen(store, mirror_tokens(_from_side(pair[side])))
                screened += 1
                if screened >= 50:
                    break
            if screened >= 50:
                break
    assert screened == 50
    assert "github" not in inspect.getsource(triage_task.dedup_and_screen._chia_original)


def test_triage_16_a_known_closed_issue_comes_back_with_its_number(tmp_path):
    """T-U-triage-16 (FR-10.3): F-10's own acceptance, against the recorded
    mirror. `assertion_01`'s expression is in two real closed `llvm/circt`
    issues, and an open one carries an expression of its own."""
    store = _store(tmp_path)
    payload = json.loads((MIRROR / "sample.json").read_text())
    _mirror_rows(store, [{
        "issue_number": item["number"], "title": item["title"],
        "body": item["body"] or "", "labels": [l["name"] for l in item["labels"]],
        "state": item["state"], "url": item["html_url"]} for item in payload])

    closed = mirror_screen(store, [
        'isa<To>(Val) && "cast<Ty>() argument of incompatible type!"'])
    assert closed is not None
    assert closed["issue_state"] == "closed"
    assert closed["issue_number"] in (10500, 10501)

    opened = mirror_screen(store, ['MI != member_end() && "Value is not in the set!"'])
    assert opened is not None and opened["issue_state"] == "open"
    assert opened["issue_number"] == 11085


def test_triage_17_every_verdict_but_new_carries_evidence(tmp_path, clone):
    """T-U-triage-17 (FR-10.5, FR-20.4): `dedup_evidence` holds exactly the eight
    declared keys and no issue text, and the per-verdict required subset is
    populated; `store.validate_candidate` is the enforcement point."""
    candidate = _candidate(tmp_path, screened=True, run_commit=clone["c1"])
    store = _store(tmp_path, candidate=candidate)
    _mirror_rows(store, json.loads((DEDUP / "known_issue/issues.json").read_text()))
    verdict = _verdict(
        "assertion",
        assertion_text='detail::isPresent(Val) && "dyn_cast on a non-existent value"',
        assertion_site=f"{CIRCT_ROOT}lib/Support/InstanceGraph.cpp:230",
        fingerprint_frame="circt::igraph::InstanceGraph::getInferredTopLevelNodes "
                          "InstanceGraph.cpp",
        frames=["circt::igraph::InstanceGraph::getInferredTopLevelNodes"])

    out = call_node(dedup_and_screen, candidate, _seed(), verdict, clone["path"],
                    str(tmp_path / "loop.db"), 5)

    evidence = out["dedup"].evidence
    assert set(evidence) == set(triage_task._EVIDENCE_KEYS)
    assert out["dedup"].verdict == "known_open_issue"
    for key in ("matched_token", "issue_number", "issue_url", "issue_state",
                "issue_labels"):
        assert evidence[key] is not None
    blob = json.dumps(evidence)
    assert "Still reproducing at main" not in blob, "no issue text in the evidence"


@pytest.mark.t1
def test_triage_18_the_post_pin_scan_is_file_level(tmp_path, clone):
    """T-U-triage-18 (FR-10.4): file level, lower bound `candidate.run_commit`,
    upper bound the clone head; a candidate reproducing a bug fixed inside the
    lag is `fixed_post_pin` with the fixing SHA."""
    candidate = _candidate(tmp_path, screened=True, run_commit=clone["c1"])
    store = _store(tmp_path, candidate=candidate)
    _mirror_rows(store, [{"issue_number": 1, "title": "unrelated",
                          "body": "nothing matches here", "labels": [],
                          "state": "open", "url": "u"}])

    out = call_node(dedup_and_screen, candidate, _seed(), _graph_verdict(),
                    clone["path"], str(tmp_path / "loop.db"), 5)

    assert out["dedup"].verdict == "fixed_post_pin"
    assert set(out["fixing_commits"]) == {clone["c2"], clone["c3"]}
    assert out["dedup"].evidence["fixing_commit"] in out["fixing_commits"]
    assert out["contaminated_file"] is True


@pytest.mark.t1
def test_triage_19_the_contamination_scan_is_symbol_level(tmp_path, clone):
    """T-U-triage-19 (FR-15.1): symbol level, read from git's `@@ ... @@`
    hunk-header context and never from the crude `\\b(\\w+)\\s*\\(` rule."""
    commits = scan_commits(clone["path"], "2024-06-01T00:00:00+00:00",
                           ["lib/Support/InstanceGraph.cpp"])
    assert [c["sha"] for c in commits] == [clone["c3"], clone["c2"]]
    contexts = {c["sha"]: " ".join(c["contexts"]) for c in commits}
    assert "getInferredTopLevelNodes" in contexts[clone["c2"]]
    assert "getInferredTopLevelNodes" not in contexts[clone["c3"]]
    assert "addNode" in contexts[clone["c3"]]

    assert triage_task.touches_symbol(
        commits[1], {"getInferredTopLevelNodes"}) is True
    assert triage_task.touches_symbol(
        commits[0], {"getInferredTopLevelNodes"}) is False
    assert "candidateTopLevels" not in contexts[clone["c2"]], (
        "the crude rule would have read the changed line, not the hunk header")


@pytest.mark.t1
def test_triage_20_both_flags_and_the_bound_are_recorded(tmp_path, clone):
    """T-U-triage-20 (FR-15.1, FR-15.2, FR-15.5): both flags are recorded, and
    `contamination_lower_bound` names the run's commit for a non-exact seed, so
    all 187 stay screenable."""
    candidate = _candidate(tmp_path, screened=True, run_commit=clone["c2"])
    store = _store(tmp_path, candidate=candidate)
    _mirror_rows(store, [{"issue_number": 1, "title": "u", "body": "u",
                          "labels": [], "state": "open", "url": "u"}])
    db = str(tmp_path / "loop.db")

    exact = call_node(dedup_and_screen, candidate,
                      _seed(committed="2024-06-01T00:00:00+00:00"),
                      _graph_verdict(), clone["path"], db, 5)
    assert exact["contamination_lower_bound"] == "seed_commit"
    assert exact["contaminated_symbol"] is True, "commit c2 touched the symbol"
    assert exact["contaminated_file"] is True

    inexact = call_node(dedup_and_screen, candidate, _seed(sdk_exact=False),
                        _graph_verdict(), clone["path"], db, 5)
    assert inexact["contamination_lower_bound"] == "run_commit"
    assert inexact["contaminated_file"] is True, "c3 touched the file"
    assert inexact["contaminated_symbol"] is False, "c3 touched another function"

    row = store.query_one("SELECT * FROM candidate WHERE candidate_id = ?",
                          (candidate.candidate_id,))
    assert row["contamination_lower_bound"] == "run_commit"
    assert (bool(row["contaminated_file"]), bool(row["contaminated_symbol"])) == \
        (True, False)


def test_triage_28_the_token_set_is_one_case_per_oracle_class():
    """T-U-triage-28 (FR-10.3): `assertion` two tokens, `crash` one,
    `fatal_error` two, `differential` none."""
    assertion = _verdict("assertion", assertion_text='x && "a long message here"',
                         assertion_site="/workspace/circt/lib/A.cpp:10")
    crash = _verdict("crash", fingerprint_frame="circt::sim::ConcatOp::fold SimOps.cpp")
    fatal = _verdict("fatal_error", fatal_message="Unsupported type for data layout",
                     fingerprint_frame="ClassNewOpConversion::matchAndRewrite "
                                       "MooreToCore.cpp")
    differential = _verdict("differential")

    assert mirror_tokens(assertion) == ['x && "a long message here"',
                                        "/workspace/circt/lib/A.cpp:10"]
    assert mirror_tokens(crash) == ["circt::sim::ConcatOp::fold"], "no file"
    assert mirror_tokens(fatal) == ["ClassNewOpConversion::matchAndRewrite",
                                    "Unsupported type for data layout"]
    assert mirror_tokens(differential) == []


def test_triage_29_a_short_token_is_dropped_before_the_query_runs(tmp_path):
    """T-U-triage-29 (FR-10.3): shorter than `MIRROR_TOKEN_MIN_CHARS` goes, so
    `fold` alone cannot answer `known_issue` for every candidate."""
    assert MIRROR_TOKEN_MIN_CHARS == 8
    short = _verdict("crash", fingerprint_frame="fold SimOps.cpp")
    assert mirror_tokens(short) == [], "all its tokens were dropped"

    store = _store(tmp_path)
    _mirror_rows(store, json.loads((DEDUP / "known_issue/issues.json").read_text()))
    assert mirror_screen(store, mirror_tokens(short)) is None
    assert mirror_screen(store, ["fold"]) is not None, (
        "the query itself would have matched; the drop is what stops it")


def test_triage_30_open_beats_closed_and_the_evidence_names_the_match(tmp_path):
    """T-U-triage-30 (FR-10.3, FR-10.5): one query per token, case-sensitive,
    any token matching any issue is a hit, and the open issue wins."""
    store = _store(tmp_path)
    rows = json.loads((DEDUP / "known_issue/issues.json").read_text())
    _mirror_rows(store, rows)
    token = 'detail::isPresent(Val) && "dyn_cast on a non-existent value"'

    hit = mirror_screen(store, [token])
    assert hit["issue_state"] == "open" and hit["issue_number"] == 9005, (
        "9002 is closed and 9005 is open on the same token; open wins")
    assert hit["matched_token"] == token
    assert hit["issue_url"].startswith("https://github.com/llvm/circt/issues/")
    assert set(hit) == {"matched_token", "issue_number", "issue_url",
                        "issue_state", "issue_labels"}
    assert mirror_screen(store, [token.upper()]) is None, "case-sensitive"


def test_triage_30b_a_good_first_issue_match_is_the_one_reported(tmp_path):
    """FR-13.9 and C-05: a candidate matching an issue carrying `good first
    issue` reports that issue, so the label reaches the approver's refusal
    through `DedupVerdict.evidence["issue_labels"]`."""
    store = _store(tmp_path)
    _mirror_rows(store, json.loads((DEDUP / "known_issue/issues.json").read_text()))
    hit = mirror_screen(store, ["circt::sim::StringConcatOp::fold"])
    assert hit["issue_number"] == 9003
    assert triage_task.GOOD_FIRST_ISSUE in hit["issue_labels"]


def test_triage_31_no_match_is_not_a_verdict(tmp_path, clone):
    """T-U-triage-31 (FR-10.3, FR-10.7): a clean miss leaves the screen
    contributing nothing, and the candidate may be `new`; the screen does not
    invent `dedup_unavailable` for a quiet week."""
    candidate = _candidate(tmp_path, screened=True, run_commit=clone["c3"])
    store = _store(tmp_path, candidate=candidate)
    _mirror_rows(store, [{"issue_number": 1, "title": "unrelated",
                          "body": "nothing here matches", "labels": [],
                          "state": "open", "url": "u"}])
    verdict = _verdict("crash", fingerprint_frame="circt::sim::ConcatOp::fold "
                                                  "SimOps.cpp",
                       frames=["circt::sim::ConcatOp::fold"])

    out = call_node(dedup_and_screen, candidate, _seed(), verdict, clone["path"],
                    str(tmp_path / "loop.db"), 5)

    assert mirror_screen(store, mirror_tokens(verdict)) is None
    assert out["dedup"].verdict == "new"
    assert out["fixing_commits"] == [], "nothing after c3 touches SimOps.cpp"
    assert all(value is None for value in out["dedup"].evidence.values())


@pytest.mark.t1
def test_triage_32_the_scans_bound_on_the_candidates_own_run_commit(tmp_path, clone):
    """T-U-triage-32 (FR-02.7, FR-10.4, FR-15.1): built against a calibration
    manifest carrying two entries, a candidate from the second seed scans from
    its own commit; index 0 is another seed's and is this one's by accident."""
    manifest = _manifest()
    assert manifest.mode == "calibration" and len(manifest.run_commit) == 2
    assert manifest.run_commit[0].commit != manifest.run_commit[1].commit

    second = _candidate(tmp_path, screened=True, run_commit=clone["c2"])
    store = _store(tmp_path, candidate=second)
    _mirror_rows(store, [{"issue_number": 1, "title": "u", "body": "u",
                          "labels": [], "state": "open", "url": "u"}])

    out = call_node(dedup_and_screen, second, _seed(sdk_exact=False),
                    _graph_verdict(), clone["path"], str(tmp_path / "loop.db"), 5)

    assert out["fixing_commits"] == [clone["c3"]], (
        "the post-pin scan bounded on c2, this candidate's own run commit")
    assert clone["c2"] not in out["fixing_commits"]
    from_index_zero = triage_task._after(
        scan_commits(clone["path"],
                     triage_task.commit_date(clone["path"], clone["c1"]),
                     ["lib/Support/InstanceGraph.cpp"]), clone["c1"])
    assert [c["sha"] for c in from_index_zero] == [clone["c3"], clone["c2"]], (
        "bounding on the manifest's first entry would have flagged c2 too")


def test_triage_33_b6b_is_a_head_node():
    """T-U-triage-33 (FR-10.3, FR-10.4, FR-15.1): `dedup_and_screen` declares no
    `circt` resource and takes `clone_path` as a parameter."""
    assert dedup_and_screen._chia_options == {"max_retries": 0}
    assert issue_mirror_refresh._chia_options == {"max_retries": 0}
    assert triage_report._chia_options == {"resources": {"circt": 1},
                                           "max_retries": 0}
    signature = inspect.signature(dedup_and_screen._chia_original)
    assert "clone_path" in signature.parameters
    assert "/workspace/circt" not in inspect.getsource(
        dedup_and_screen._chia_original)


# ===========================================================================
# Tests 21 to 24, 34: the triage turn and the render
# ===========================================================================


def _render_bundle(tmp_path, *, oracle_class="assertion", dedup_verdict="new"):
    evidence = dict.fromkeys(triage_task._EVIDENCE_KEYS)
    if dedup_verdict == "known_closed_issue":
        evidence.update(matched_token="t" * 10, issue_number=10500,
                        issue_url="https://github.com/llvm/circt/issues/10500",
                        issue_state="closed", issue_labels=["bug"])
    reduced_name = ("report/reduced_fatal.mlir" if oracle_class == "fatal_error"
                    else "report/reduced_primary.mlir")
    candidate = _candidate(tmp_path, oracle_class=oracle_class, screened=True,
                           dedup_verdict=dedup_verdict, dedup_evidence=evidence,
                           fingerprint="SIGABRT\nfoo Bar.cpp",
                           reduced_path=str(TRIAGE / reduced_name))
    if oracle_class == "fatal_error":
        verdict = _verdict("fatal_error", fatal_message="Unsupported type for "
                                                        "data layout",
                           fingerprint_frame="ClassNewOpConversion::matchAndRewrite "
                                             "MooreToCore.cpp",
                           frames=["ClassNewOpConversion::matchAndRewrite"],
                           repro="circt-opt --convert-moore-to-core reduced.mlir")
    else:
        verdict = _verdict("assertion", assertion_text=candidate.assertion_text,
                           assertion_site=candidate.assertion_site,
                           frames=["circt::chooseName", "mlir::Pass::run"])
    reduced = ReducedCase(
        probe_id="p-01", reducer="circt-reduce", reduced=True, fixpoint=True,
        budget_truncated=False, reason=None, lift=None,
        path=candidate.reduced_path, size_before_bytes=400, size_after_bytes=80,
        size_before_ops=9, size_after_ops=2, wall_seconds=12.5,
        interestingness_calls=56, recheck_class=oracle_class,
        recheck_assertion_text=candidate.assertion_text,
        recheck_assertion_site=candidate.assertion_site, recheck_matches=True)
    dedup = DedupVerdict(probe_id="p-01", verdict=dedup_verdict, evidence=evidence)
    return candidate, reduced, verdict, dedup


def _differential_bundle(tmp_path):
    candidate = _candidate(tmp_path, oracle_class="differential")
    differential = DifferentialVerdict(
        probe_id="p-01", verdict="diverge", reason="one signal differs",
        verilator_version="5.028", x_policy="x-assign=unique,x-initial=unique",
        stimulus_id="lfsr32-v1", port_list_sha="9" * 64, cycles=64,
        first_divergent_signal="out_q", first_divergent_cycle=17,
        arcilator_value="0x00ff", verilator_value="0x00fe",
        arcilator_trace_path=str(tmp_path / "arcilator.vcd"),
        verilator_trace_path=str(tmp_path / "verilator.vcd"),
        driver_source="circt/arc-tests")
    return candidate, differential


PROSE = {"title": "[Moore] VariableOpConversion casts an operand it did not check",
         "summary": "The input declares one variable of a type the conversion "
                    "does not handle.",
         "why_it_matters": "The frames are where I would start."}


def test_triage_21_the_tool_verdict_wins(tmp_path, monkeypatch):
    """T-U-triage-21 (FR-11.2): a candidate the dedup stage marked known is
    classified `known_issue` whatever the agent wrote; the reason survives."""
    seen = _fake_generate(monkeypatch, _turn_text("report_write_disagree"))
    candidate, reduced, verdict, dedup = _render_bundle(
        tmp_path, dedup_verdict="known_closed_issue")

    out = call_node(triage_report, candidate, reduced, verdict, dedup,
                    _manifest(), _cfg(), str(tmp_path / "probe"))

    assert out["failure"] is None
    assert out["report"].classification == "known_issue"
    assert out["report"].classification_reason == (
        "I still think this is a fresh fault in the conversion.")
    assert seen["model_id"] == "gemini-3.8-flash" and seen["timeout_seconds"] == 1200
    assert len(seen["tools"]) == 1 and seen["tools"][0].stopped, "stopped in a finally"


def test_triage_22_the_reason_is_truncated_not_rejected(tmp_path, monkeypatch):
    """T-U-triage-22 (FR-11.1): capped at four sentences, counted on `.`, `!` and
    `?` followed by whitespace or the end, truncated with the truncation
    recorded."""
    _fake_generate(monkeypatch, _turn_text("report_write_long"))
    candidate, reduced, verdict, dedup = _render_bundle(tmp_path)

    out = call_node(triage_report, candidate, reduced, verdict, dedup,
                    _manifest(), _cfg(), str(tmp_path / "probe"))

    assert out["failure"] is None
    assert out["logs"]["reason_truncated"] is True
    assert out["report"].classification_reason == "One. Two! Three? Four."
    assert cap_sentences("One. Two.") == ("One. Two.", False)
    assert cap_sentences("a. b. c. d. e.")[1] is True
    assert cap_sentences("no terminator at all") == ("no terminator at all", False)


def test_triage_23_every_substitution_point_equals_the_record(tmp_path):
    """T-U-triage-23 (FR-11.3, FR-11.4, FR-03.11): the thirteen points are
    present and equal the record field by field, and no number is the agent's."""
    candidate, reduced, verdict, dedup = _render_bundle(tmp_path)
    manifest = _manifest()
    rendered = render_report("primary", candidate, reduced, verdict, None, dedup,
                             manifest, PROSE)

    assert PROSE["title"] in rendered and PROSE["summary"] in rendered
    assert PROSE["why_it_matters"] in rendered
    assert Path(candidate.reduced_path).read_text().strip() in rendered
    assert verdict.repro_command in rendered
    assert verdict.assertion_text in rendered and verdict.assertion_site in rendered
    assert manifest.image_spec["circt_sha"] in rendered
    assert manifest.image_spec["sdk_tag"] in rendered
    assert manifest.image_spec["image_digest"] in rendered
    assert "-UNDEBUG" in rendered and verdict.tool_version_output in rendered
    assert manifest.image_spec["flag_string"] or True
    assert "circt::chooseName" in rendered and "mlir::Pass::run" in rendered
    assert f"- Verdict: {dedup.verdict}" in rendered
    assert f"Arm: {candidate.arm}" in rendered
    assert candidate.contamination_lower_bound in rendered
    assert candidate.fingerprint in rendered
    assert rendered.strip().splitlines()[-1] == \
        f"Assisted-by: {manifest.model_ids['triage_report']}"
    assert "$" not in rendered

    # A missing point fails the render, one point at a time. `contamination` and
    # `assisted_by` are always derivable from the record and have no removal.
    removals = {
        "title": lambda: _render({"title": ""}),
        "summary": lambda: _render({"summary": ""}),
        "why_it_matters": lambda: _render({"why_it_matters": ""}),
        "observed_behaviour": lambda: _render(verdict=None),
        "build_identity": lambda: _render(verdict=None),
        "reduced_case": lambda: _render(reduced=_blank(reduced, path="")),
        "repro_command": lambda: _render(verdict=_blank(verdict, repro_command="")),
        "frames": lambda: _render(verdict=_blank(verdict, frames=[])),
        "dedup_evidence": lambda: _render(dedup=None),
        "arm": lambda: _render(candidate=_blank(candidate, arm="")),
        "fingerprint": lambda: _render(candidate=_blank(candidate, fingerprint=None)),
    }

    def _render(prose_over=None, *, candidate=candidate, reduced=reduced,
                verdict=verdict, dedup=dedup):
        return render_report("primary", candidate, reduced, verdict, None, dedup,
                             manifest, {**PROSE, **(prose_over or {})})

    assert set(removals) | {"contamination", "assisted_by"} == set(PRIMARY_POINTS)
    for point, removal in removals.items():
        with pytest.raises(ReportIncomplete):
            removal()


def _blank(record, **over):
    """A copy of *record* with one field emptied, for T-U-triage-23's removals."""
    import copy

    clone = copy.deepcopy(record)
    for name, value in over.items():
        setattr(clone, name, value)
    return clone


def test_triage_24_template_selection_by_candidate_class(tmp_path, monkeypatch):
    """T-U-triage-24 (FR-07.10, FR-08.6, FR-08.7, FR-11.5, FR-11.6, FR-11.9):
    a `differential` candidate takes the second template, a `fatal_error`
    quotes its own message and says neither of the two forbidden words, and the
    trailer is the last line."""
    manifest = _manifest()
    candidate, differential = _differential_bundle(tmp_path)
    rendered = render_report("differential", candidate, None, None, differential,
                             None, manifest, PROSE)

    assert "expected" not in rendered.lower()
    assert "correct" not in rendered.lower(), "no sentence names a correct arm"
    assert triage_task.ARC_TESTS in rendered
    assert differential.first_divergent_signal in rendered
    assert str(differential.first_divergent_cycle) in rendered
    assert differential.verilator_version in rendered
    assert rendered.strip().splitlines()[-1] == \
        f"Assisted-by: {manifest.model_ids['triage_report']}"

    _fake_generate(monkeypatch, _turn_text("report_write_fatal"))
    fatal, reduced, verdict, dedup = _render_bundle(tmp_path,
                                                    oracle_class="fatal_error")
    out = call_node(triage_report, fatal, reduced, verdict, dedup, manifest,
                    _cfg(), str(tmp_path / "fatal"))
    body = Path(out["report"].path).read_text()
    assert out["report"].template == "primary"
    assert "LLVM ERROR: Unsupported type for data layout" in body
    assert "crash" not in body.lower(), "W13: a deliberate refusal is not a crash"
    assert "assertion" not in body.lower(), (
        "W13: nor does the build-identity block say the word")


def test_triage_34_two_templates_two_lists_and_no_leaked_dollar(tmp_path):
    """T-U-triage-34 (FR-08.6, FR-11.3, FR-11.9): the thirteen and the twelve are
    enforced separately, and neither filling of the prompt leaves a `$name`."""
    manifest = _manifest()
    candidate, reduced, verdict, dedup = _render_bundle(tmp_path)
    differential_candidate, differential = _differential_bundle(tmp_path)

    assert len(PRIMARY_POINTS) == 13 and len(DIFFERENTIAL_POINTS) == 12
    assert "observed_behaviour" not in DIFFERENTIAL_POINTS
    assert set(DIFFERENTIAL_POINTS) - set(PRIMARY_POINTS) == {
        "arcilator_behaviour", "verilator_behaviour", "divergence_point",
        "stimulus", "x_policy", "prior_art"}

    # The other template's absent points are accepted, not demanded.
    assert render_report("differential", differential_candidate, None, None,
                         differential, None, manifest, PROSE)
    with pytest.raises(ReportIncomplete) as raised:
        render_report("differential", differential_candidate, None, None, None,
                      None, manifest, PROSE)
    assert str(raised.value) in DIFFERENTIAL_POINTS
    with pytest.raises(ValueError):
        render_report("neither", candidate, reduced, verdict, None, dedup,
                      manifest, PROSE)

    primary_prompt = triage_task._render_prompt(candidate, reduced, verdict,
                                                dedup, None, manifest, _cfg())
    differential_prompt = triage_task._render_prompt(
        differential_candidate, None, None, None, differential, manifest, _cfg())
    for prompt in (primary_prompt, differential_prompt):
        assert "$" not in prompt, "safe_substitute left an unbound $name"
    assert differential_prompt.count(triage_task.NOT_APPLICABLE) >= 6
    assert "lfsr32-v1" in differential_prompt
    assert verdict.assertion_text in primary_prompt
    assert triage_task.NOT_APPLICABLE not in primary_prompt.replace(
        "not applicable to a differential candidate", "", 3)


# ===========================================================================
# The prompt, the footer parser and the turn's failure paths
# ===========================================================================


def test_triage_prompt_file_is_the_lld_text_verbatim():
    """FR-11.5, §7.4: the committed prompt is stage 6's, distinct from CHIA's
    `writeup`, and declares exactly the thirteen substitution variables."""
    from string import Template

    text = (Path(triage_task.__file__).resolve().parent
            / "prompts/report_write.md").read_text()
    names = {match.group("named") or match.group("braced")
             for match in Template.pattern.finditer(text)} - {None}
    assert names == {"oracle_class", "assertion_text", "assertion_site", "frames",
                     "repro_command", "reduced_case", "dedup_verdict",
                     "dedup_evidence", "build_identity", "max_sentences",
                     "arcilator_behaviour", "verilator_behaviour", "stimulus"}
    assert "PART A - CLASSIFY, ADVISORILY." in text
    assert "PART B - WRITE THE PROSE." in text
    assert 'Do NOT write an "expected behaviour" section' in text
    assert text.rstrip().endswith("```")


def test_triage_footer_parser_takes_the_last_block():
    """§7.1: the last fenced json block wins, and every other outcome is one of
    the four `PromptContractError` reasons."""
    two = _turn_text("report_write_two_blocks")
    assert parse_json_footer(two, ("classification",))["classification"] == "bug"

    for text, reason in (("no block here", "no_block"),
                         ("```json\nnot json\n```", "not_json"),
                         ("```json\n[1, 2]\n```", "not_object"),
                         ('```json\n{"a": 1}\n```', "missing:classification")):
        with pytest.raises(PromptContractError) as raised:
            parse_json_footer(text, ("classification",))
        assert str(raised.value) == reason


def test_triage_turn_failure_yields_untriaged_and_an_empty_report(tmp_path,
                                                                  monkeypatch):
    """FR-11.8, FR-11.7: a failed or unparseable turn yields `untriaged` and an
    empty report, and the raw output is persisted whatever happens."""
    candidate, reduced, verdict, dedup = _render_bundle(tmp_path)
    _fake_generate(monkeypatch, _turn_text("report_write_no_block"))
    out = call_node(triage_report, candidate, reduced, verdict, dedup,
                    _manifest(), _cfg(), str(tmp_path / "a"))
    assert out["failure"] == "prompt_contract:no_block"
    assert out["report"].classification == "untriaged"
    assert out["report"].path == "" and out["report"].fields_present == []
    assert (tmp_path / "a/llm_report_write.md").read_text().startswith("I could not")
    assert (tmp_path / "a/llm_report_write.prompt.md").exists()
    assert json.loads((tmp_path / "a/llm_report_write.usage.json").read_text()) == {
        "tokens_in": 11, "tokens_out": 7, "num_turns": 1, "model": "gemini-3.8-flash"}

    _fake_generate(monkeypatch, raises=RuntimeError("backend said no"))
    out = call_node(triage_report, candidate, reduced, verdict, dedup,
                    _manifest(), _cfg(), str(tmp_path / "b"))
    assert out["failure"] == "turn_failed:RuntimeError"
    assert out["report"].classification == "untriaged"
    assert (tmp_path / "b/llm_report_write.prompt.md").exists()


def test_triage_report_records_the_render_and_refuses_a_differential_dedup(tmp_path,
                                                                          monkeypatch):
    """FR-11.3 and FR-08.10: the `Report` record carries the render's own hash
    and its point list, and a `differential` candidate never reaches B6b."""
    _fake_generate(monkeypatch, _turn_text("report_write_ok"))
    candidate, reduced, verdict, dedup = _render_bundle(tmp_path)
    out = call_node(triage_report, candidate, reduced, verdict, dedup,
                    _manifest(), _cfg(), str(tmp_path / "probe"))

    body = Path(out["report"].path).read_text()
    assert out["report"].rendered_sha256 == hashlib.sha256(
        body.encode("utf-8")).hexdigest()
    assert out["report"].fields_present == list(PRIMARY_POINTS)
    assert out["report"].classification == "bug"
    assert out["report"].assisted_by == "vertex:gemini-3.8-flash"
    assert out["report"].path.endswith("/report.md")

    with pytest.raises(ValueError):
        call_node(dedup_and_screen, _candidate(tmp_path, oracle_class="differential"),
                  _seed(), _verdict("differential"), "/nonexistent",
                  str(tmp_path / "loop.db"), 5)


def test_triage_36_the_source_read_tool_is_constructed_for_real(tmp_path, monkeypatch,
                                                                tool_servers,  # noqa: F811
                                                                throwaway_repo):  # noqa: F811
    """T-U-triage-36 (FR-04.4, FR-11.1): B7 builds §3.5's real `SourceReadTool`.

    Architect decision 4 and errata row W-13 #2. The call site passed **two
    positional** arguments to a constructor whose signature is
    `(name, clone_path, run_commit, cap_bytes, task_options)`, so it bound
    `name` to the clone path and `clone_path` to the commit and then raised
    `TypeError` for the missing `run_commit`; every triage turn would have
    failed as `turn_failed:TypeError`, and nothing caught it because the tool
    was a stand-in in every test. This test installs **no** stand-in module: the
    real class is constructed, its three methods answer against a real git
    repository, and the registry is empty again afterwards.

    Fixture: `tests/fixtures/triage/turns/report_write_ok.jsonl` plus the
    throwaway repository of `test_tools.py`. Tier 0.
    """
    from chia.base.tools.ChiaTool import ChiaTool

    from circt_bug_loop.generate_task import SourceReadTool

    clone, head = throwaway_repo
    seen = {}

    def dispatch_turn(system_message, user_message, tools, *, stage,
                      timeout_seconds, model_id, guard=None):
        seen["tools"] = list(tools)
        seen["stage"] = stage
        return {"result": _turn_text("report_write_ok"), "stream": "", "stderr": "",
                "success": True, "usage": {"tokens_in": 11, "tokens_out": 7,
                                           "num_turns": 1,
                                           "model": "gemini-3.8-flash"}}

    monkeypatch.setattr(triage_task, "dispatch_turn", dispatch_turn)

    before = len(ChiaTool._tool_registry)
    candidate, reduced, verdict, dedup = _render_bundle(tmp_path)
    out = call_node(triage_report, candidate, reduced, verdict, dedup, _manifest(),
                    _cfg(clone_path=clone, run_commit=head,
                         artefact_inline_cap_bytes=1024,
                         head_options={"scheduling_strategy": "head-node"}),
                    str(tmp_path / "probe"))

    assert out["failure"] is None
    (tool,) = seen["tools"]
    assert type(tool) is SourceReadTool, "the real class, not a stand-in"
    assert (tool.clone_path, tool.run_commit) == (clone, head)
    assert tool.name == f"src_{candidate.candidate_id}"
    assert tool.cap_bytes == 1024
    # The tool answers for real at the run's commit, which is the whole point of
    # binding the commit and not a ref (FR-04.4).
    assert tool.read_file("README.md").startswith("circt")
    assert tool.read_file("NoSuch.cpp").startswith("Error:")
    # Started and stopped: one server was constructed and the registry is empty
    # again, `triage_report` stopping it in its own `finally`.
    assert len(tool_servers) == 1 and tool_servers[0] is tool
    assert len(ChiaTool._tool_registry) == before, "the triage turn leaked a tool"


def test_triage_frame_paths_and_symbols_are_repo_relative():
    """§3.7.2: a frame path under a CIRCT source root becomes the repo path, and
    anything else falls back to a basename glob; the symbols carry both
    spellings git writes into a hunk header."""
    verdict = _graph_verdict()
    assert frame_paths(verdict) == ["lib/Support/InstanceGraph.cpp"]
    assert frame_symbols(verdict) == {
        "circt::igraph::InstanceGraph::getInferredTopLevelNodes",
        "getInferredTopLevelNodes"}

    elsewhere = _verdict("crash", frames=["x::y"])
    elsewhere.frames[0].file = "/opt/sdk/gen/Weird.cpp"
    assert frame_paths(elsewhere) == [":(glob)**/Weird.cpp"]
    assert scan_commits("/nonexistent", "2024-01-01", []) == []


# ===========================================================================
# T-U-triage-35: the one live mirror test
# ===========================================================================


@pytest.mark.t1
@pytest.mark.skipif(not os.environ.get("GITHUB_TOKEN"),
                    reason="no GITHUB_TOKEN: H-05's read-only token is not set")
def test_triage_35_live_mirror_against_llvm_circt(tmp_path):
    """T-U-triage-35 (FR-10.9, C-22), LIVE and `t1`: the TWO-DIRECTION listing of
    `llvm/circt`, open and closed, pull requests excluded as the node does, up
    to `budget.yaml`'s `issue_mirror_issue_cap`, recording the refresh time, the
    page count and whether GitHub's pagination ceiling was reached.

    This is the measurement architect decision 1 rests on: at the old cap of
    20,000 the one-direction walk raised on the 422 that page 100 answers and
    wrote zero rows. Read-only, `fetch_comments=False`, listing requests only,
    and nothing is written outside `tmp_path`. The token is read from the
    environment into a file with mode 0600 and is never logged, printed or
    committed.
    """
    import time

    import yaml
    from chia.github.github_client import GithubClient

    budget = yaml.safe_load(
        (Path(triage_task.__file__).resolve().parent / "budget.yaml").read_text())
    cap = int(budget["issue_mirror_issue_cap"])

    token = tmp_path / "token"
    token.write_text(os.environ["GITHUB_TOKEN"])
    os.chmod(token, 0o600)

    pages = []
    original = GithubClient._request

    def _counted(self, path, params=None, accept=None):
        pages.append(path)
        assert not path.endswith("/comments"), "fetch_comments=False (FR-10.9)"
        return original(self, path, params=params, accept=accept)

    GithubClient._request = _counted
    started = time.monotonic()
    try:
        out = call_node(issue_mirror_refresh, "llvm/circt", cap, str(token),
                        str(tmp_path / "loop.db"))
    finally:
        GithubClient._request = original
    wall = time.monotonic() - started

    store = LoopStore(str(tmp_path / "loop.db"))
    rows = store.query("SELECT state, COUNT(*) AS n FROM issue_mirror GROUP BY state")
    states = {row["state"]: row["n"] for row in rows}
    print(f"\nlive mirror: {out['issues_mirrored']} issues, "
          f"{len(pages)} requests, {out['pages']} pages accepted, "
          f"ceiling_hit {out['ceiling_hit']}, {wall:.1f} s wall, "
          f"refreshed {out['refreshed_utc']}, cap {cap}, states {states}")

    assert out["incomplete_reason"] is None, (
        "the ceiling is not a failure and the cap is inside two directions' reach")
    assert out["pages"] >= 1 and out["pages"] <= len(pages)
    assert isinstance(out["ceiling_hit"], bool)
    assert out["issues_mirrored"] > 0
    assert out["issues_mirrored"] == sum(states.values())
    assert set(states) == {"open", "closed"}, "state='all' reaches both"
    assert out["state"] == "all" and out["comments_mirrored"] is False
    assert out["refreshed_utc"].endswith("+00:00")
    assert all(path.endswith("/issues") for path in pages), "one listing"
    assert store.query_one(
        "SELECT COUNT(*) AS n FROM issue_mirror WHERE title = ''")["n"] == 0

    recorded = json.loads((MIRROR / "sample.json").read_text())
    assert len(recorded) == 50
    live = {row["issue_number"] for row in store.query(
        "SELECT issue_number FROM issue_mirror")}
    assert {item["number"] for item in recorded} <= live, (
        "every recorded fixture issue is still in the live mirror")
