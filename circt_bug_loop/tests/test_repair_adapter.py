"""`04-Test-Plan.md` §1's `repair` rows: `repair_adapter.py` (B8), F-12."""
from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import types
from pathlib import Path

import pytest

from circt_bug_loop import llm, repair_adapter
from circt_bug_loop.contract import schema
from circt_bug_loop.repair_adapter import (BUILD_JOBS, CFG_KEYS, LOCAL_ID_BASE,
                                           LOCAL_ID_MAX, PHASE_TIMEOUTS,
                                           PROMPT_FILES, RepairRefused,
                                           as_github_issue, build_cfg,
                                           failing_phase, issue_solver_dir,
                                           mint_local_id, repair_adapt,
                                           repro_script, stage7_observed)
from circt_bug_loop.store import (CandidateRecord, LoopStore, OracleVerdict,
                                  ReducedCase, Report)
from circt_bug_loop.tests.conftest import call_node
from circt_bug_loop.tests.test_bug_loop import budget_file

pytestmark = pytest.mark.t0

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPAIR = FIXTURES / "repair"
POLARITY = REPAIR / "repro_polarity"
VERDICTS = REPAIR / "verdicts"

#: W-10 put the shared `run_manifest/` fixtures under `triage/` (its erratum 19).
MANIFEST = FIXTURES / "triage" / "run_manifest" / "calibration_two.json"

#: A synthetic value. No test reads a real key and no fixture carries one.
FAKE_KEY = "synthetic-not-a-real-api-key"


def _manifest(tmp_path):
    manifest = schema.from_json(MANIFEST.read_text(), schema.RunManifest)
    manifest.artefact_root = str(tmp_path / "artefacts")
    return manifest


def _candidate(tmp_path, **over):
    fields = dict(
        candidate_id="cand-0001", probe_id="p-01", run_manifest_id="r" * 32,
        arm="seeded", run_commit="c" * 40, image_digest="sha256:" + "0" * 64,
        oracle_class="assertion", frame_tuple=["a", "b", "c", "d", "e"],
        frames_resolved=5, frames_with_location=5, out_of_scope_root=False,
        contaminated_symbol=False, contaminated_file=False,
        contamination_lower_bound="seed_commit", triage_class="bug",
        artefact_dir=str(tmp_path / "probe"),
        assertion_text='op && "null op"',
        assertion_site="/workspace/circt/lib/Dialect/HW/HWOps.cpp:412")
    fields.update(over)
    return CandidateRecord(**fields)


def _verdict(*, repro=None):
    return OracleVerdict(
        probe_id="p-01", fired=True, oracle_class="assertion",
        assertion_text='op && "null op"',
        assertion_site="/workspace/circt/lib/Dialect/HW/HWOps.cpp:412",
        fatal_message=None, frames=[], prologue_dropped=0, frames_resolved=0,
        frames_with_location=0, fingerprint_frame=None, out_of_scope_root=False,
        repro_command=repro or ("/workspace/circt/build/bin/circt-opt "
                                "--lower-seq-to-sv /art/probe/input.mlir"),
        flag_string="-O3 -UNDEBUG -gline-tables-only",
        tool_version_output="CIRCT firtool-1.143.0")


def _reduced(path):
    return ReducedCase(
        probe_id="p-01", reducer="circt-reduce", reduced=True, fixpoint=True,
        budget_truncated=False, reason=None, lift=None, path=str(path),
        size_before_bytes=200, size_after_bytes=67, size_before_ops=6,
        size_after_ops=2, wall_seconds=12.5, interestingness_calls=56,
        recheck_class="assertion", recheck_assertion_text='op && "null op"',
        recheck_assertion_site="HWOps.cpp:412", recheck_matches=True)


def _report(path=REPAIR / "report.md"):
    return Report(
        candidate_id="cand-0001", path=str(path), template="primary",
        title="circt-opt crashes in LowerTypes on a zero-width aggregate",
        classification="bug", classification_reason="An assertion fired.",
        rendered_sha256="a" * 64,
        assisted_by="circt_bug_loop:vertex:gemini-3.8-flash",
        fields_present=["reduced_case", "repro_command"])


class _Recorder:
    """The `issue_task` module the repair worker imports, recording its call."""

    def __init__(self, result, *, overwrite=None):
        self.calls = []
        self.result = result
        self.overwrite = overwrite

    def run_issue_remote(self, issue_md, number, cfg, resume=None,
                         assess_only=False):
        self.calls.append({"issue_md": issue_md, "number": number, "cfg": cfg})
        if self.overwrite is not None:
            # The reproduce turn's prompt tells the agent to write <repro_path> itself and the prompt may not be edited (FR-12.9), so both branches of `repro_overwritten` are driven from here (T-U-repair-19).
            Path(cfg["repro_path"]).write_text(self.overwrite, encoding="utf-8")
        return dict(self.result)


class _CirctUtil:
    """CHIA's own worker helpers, recorded."""

    def __init__(self, *, reset_ok=True, build_ok=True):
        self.reset_ok, self.build_ok = reset_ok, build_ok
        self.reset_calls, self.build_calls = [], []

    def circt_write_files(self, files, base_dir):
        os.makedirs(base_dir, exist_ok=True)
        for relative, content in files.items():
            target = Path(base_dir, relative)
            target.write_text(content, encoding="utf-8")
            if relative.endswith(".sh"):
                target.chmod(0o755)
        return {"written": sorted(files)}

    def circt_git_reset(self, ref, timeout_seconds=300):
        self.reset_calls.append(ref)
        return {"success": self.reset_ok, "log": f"HEAD is now at {ref[:7]}"}

    def circt_ninja_build(self, targets, num_cpus=1):
        self.build_calls.append({"targets": tuple(targets), "num_cpus": num_cpus})
        return {"success": self.build_ok, "log_tail": "ninja: no work to do."}


def _recording_interlock(monkeypatch):
    """Record every `require_live_model` call, and run the REAL one."""
    recorder = types.SimpleNamespace(calls=[])
    real = llm.require_live_model

    def require_live_model(purpose, **kwargs):
        recorder.calls.append({"purpose": purpose,
                               "need_key": kwargs.get("need_key", True)})
        return real(purpose, **kwargs)

    monkeypatch.setattr(repair_adapter, "require_live_model", require_live_model)
    return recorder


def _bin_dir(tmp_path, manifest, *, match=True):
    """A directory of stand-in tool binaries, hashed into the `ImageSpec`."""
    directory = tmp_path / "bin"
    directory.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for tool in manifest.image_spec["targets"]:
        target = directory / tool
        target.write_text(f"#!/bin/sh\necho {tool}\n", encoding="utf-8")
        hashes[tool] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest.image_spec["tool_hashes"] = (
        hashes if match else {tool: "0" * 64 for tool in hashes})
    return str(directory)


#: The interlock's ALLOW mapping, handed to `repair_adapt` as `env=`.
ALLOW_ENV = {"BUGLOOP_ALLOW_LIVE_MODEL": "1", "GEMINI_API_KEY": FAKE_KEY}


def _attempt(tmp_path, monkeypatch, *, verdict="fixed.json", candidate=None,
             manifest=None, chain=None, util=None, overwrite=None,
             cfg=None, match=True, env=None):
    """Drive one whole attempt with every CHIA edge replaced by a recorder."""
    generate = _recording_interlock(monkeypatch)
    manifest = manifest or _manifest(tmp_path)
    candidate = candidate or _candidate(tmp_path)
    bin_dir = _bin_dir(tmp_path, manifest, match=match)
    chain = chain or _Recorder(json.loads((VERDICTS / verdict).read_text()),
                               overwrite=overwrite)
    util = util or _CirctUtil()
    monkeypatch.setitem(sys.modules, "issue_task", chain)
    monkeypatch.setitem(sys.modules, "circt_util", util)
    case = tmp_path / "reduced.mlir"
    shutil.copyfile(REPAIR / "case.mlir", case)
    # The COMPLETE cfg the head assembles since K3/K6.
    local_id = LOCAL_ID_BASE + 7
    chain_cfg = {**build_cfg(candidate, manifest, local_id=local_id,
                             budget=budget_file(), report_text="a report"),
                 "repair_enabled": True,
                 **dict(cfg or {"repair_backend": "vertex"})}
    # `{"result", "counters"}` since the join (W-17).
    out = call_node(
        repair_adapt, _report(), candidate, _reduced(case), _verdict(), manifest,
        chain_cfg,
        local_id=local_id, input_path="/art/probe/input.mlir",
        created_utc="2026-09-14T00:00:00+00:00", bin_dir=bin_dir,
        chia_artifact_dir=str(issue_solver_dir() / "issue_logs"
                              / f"issue_{local_id}"),
        env=dict(ALLOW_ENV if env is None else env))
    assert out["counters"].stage == "stage_7"
    return types.SimpleNamespace(result=out["result"], counters=out["counters"],
                                 logs=out.get("logs"), chain=chain, util=util,
                                 manifest=manifest, candidate=candidate,
                                 generate=generate, bin_dir=bin_dir)


def _loop_store(tmp_path, count=3):
    """A `loop.db` carrying *count* candidate rows, for the identifier tests."""
    store = LoopStore(str(tmp_path / "loop.db"))
    store.insert("run", {
        "run_manifest_id": "r" * 32, "mode": "discovery", "seed_set": "187",
        "manifest_json": "{}", "budget_file_sha": "x", "cluster_yaml_sha": "y",
        "artefact_root": str(tmp_path), "started_utc": "2026-09-14T00:00:00+00:00",
        "ended_utc": None})
    for index in range(count):
        store.insert("probe", {
            "probe_id": f"p-{index:02d}", "run_manifest_id": "r" * 32,
            "seed_sha": "a" * 40, "arm": "seeded", "iteration": index,
            "tool": "circt-opt", "argv_json": "[]", "polarity": "expect_zero",
            "shape": "plain", "input_path": "in.mlir", "mutator_id": None,
            "mutator_seed_int": None, "source_test_path": None, "spec_json": "{}",
            "artefact_dir": str(tmp_path)})
        store.insert("candidate", {
            "candidate_id": f"cand-{index:04d}", "local_id": None,
            "probe_id": f"p-{index:02d}", "run_manifest_id": "r" * 32,
            "arm": "seeded", "run_commit": "c" * 40,
            "image_digest": "sha256:" + "0" * 64, "oracle_class": "assertion",
            "assertion_text": "a", "assertion_site": "b",
            "frame_tuple_json": "[]", "out_of_scope_root": 0,
            "contaminated_symbol": 0, "contaminated_file": 0,
            "contamination_lower_bound": "seed_commit", "triage_class": "bug",
            "held_reason": None, "taxonomy_bucket": None,
            "artefact_dir": str(tmp_path), "created_utc": "2026-09-14T00:00:00+00:00"})
    return store


def _run_repro(script: Path, tool: Path, case: Path) -> int:
    """Write *script* beside *case*, point it at *tool*, and run it."""
    directory = case.parent
    text = repro_script(_verdict(repro=f"{tool} --lower-seq-to-sv /art/in.mlir"),
                        input_path="/art/in.mlir", case_name=case.name)
    (directory / script.name).write_text(text, encoding="utf-8")
    return subprocess.run(["sh", str(directory / script.name)],
                          capture_output=True, text=True).returncode


def test_repair_01_local_id_is_base_plus_rowid_and_disjoint(tmp_path):
    """T-U-repair-01 (FR-12.2): `LOCAL_ID_BASE + rowid`, in the declared range, unique, monotonic, and disjoint from every key in a real CHIA `issues.db`."""
    store = _loop_store(tmp_path, count=3)
    minted = [mint_local_id(store, f"cand-{index:04d}") for index in range(3)]

    assert minted == [LOCAL_ID_BASE + 1, LOCAL_ID_BASE + 2, LOCAL_ID_BASE + 3]
    assert minted == sorted(minted) and len(set(minted)) == len(minted)
    assert all(LOCAL_ID_BASE <= value <= LOCAL_ID_MAX for value in minted)

    conn = sqlite3.connect(REPAIR / "issues.db")
    existing = {row[0] for row in conn.execute("SELECT issue_number FROM attempts")}
    conn.close()
    assert existing, "the fixture issues.db carries real llvm/circt keys"
    assert max(existing) < LOCAL_ID_BASE, (
        "the range floor is above the tracker's own numbers by construction")
    assert not existing & set(minted)

    with pytest.raises(LookupError):
        mint_local_id(store, "cand-9999")


def test_repair_02_github_issue_has_eleven_fields(tmp_path):
    """T-U-repair-02 (FR-12.2): every required field of `chia:chia/github/state_def.py:11-24` is populated, and `url` is `local://`."""
    import dataclasses

    from chia.github.state_def import GithubIssue

    issue = as_github_issue(_report(), _candidate(tmp_path), LOCAL_ID_BASE + 7,
                            "2026-09-14T00:00:00+00:00")
    required = [f.name for f in dataclasses.fields(GithubIssue)
                if f.default is dataclasses.MISSING
                and f.default_factory is dataclasses.MISSING]
    assert len(required) == 11
    for name in required:
        value = getattr(issue, name)
        assert value is not None or name == "closed_at", name
    assert issue.comments == []
    assert issue.number == LOCAL_ID_BASE + 7
    assert issue.url.startswith("local://circt_bug_loop/")
    assert "github.com" not in issue.url
    assert issue.body == (REPAIR / "report.md").read_text()
    assert issue.labels == ["circt-bug-loop", "arm:seeded"]
    assert issue.to_markdown().startswith("# Issue #")


def test_repair_03_repro_exits_non_zero_on_a_still_crashing_tool(tmp_path):
    """T-U-repair-03 (FR-12.3): the generated `repro.sh` exits **non-zero** against a fixture binary that still crashes on the reduced case."""
    case = tmp_path / "case.mlir"
    shutil.copyfile(REPAIR / "case.mlir", case)
    assert _run_repro(tmp_path / "repro.sh", POLARITY / "crashing.sh", case) != 0


def test_repair_04_repro_exits_zero_on_a_diagnosing_tool(tmp_path):
    """T-U-repair-04 (FR-12.3): the same script exits **0** against a binary patched to emit an ordinary diagnostic and exit non-zero, which is the case the naive `exit_code == 0` script gets wrong and which FR-12.3 exists for."""
    case = tmp_path / "case.mlir"
    shutil.copyfile(REPAIR / "case.mlir", case)
    assert _run_repro(tmp_path / "repro.sh", POLARITY / "diagnosing.sh", case) == 0


def test_repair_03b_the_script_drops_the_probe_input_and_is_shell_clean(tmp_path):
    """The candidate replaces the probe's own input, the script names no placeholder, and `sh -n` parses it (§3.8)."""
    text = repro_script(_verdict(), input_path="/art/probe/input.mlir",
                        case_name="case.mlir")
    assert "/art/probe/input.mlir" not in text
    assert "--lower-seq-to-sv" in text and "case.mlir" in text
    for placeholder in ("@TOOL@", "@ARGS@", "@CASE@"):
        assert placeholder not in text, "no placeholder survives into a script"
    script = tmp_path / "repro.sh"
    script.write_text(text, encoding="utf-8")
    assert subprocess.run(["sh", "-n", str(script)]).returncode == 0
    with pytest.raises(ValueError):
        repro_script(_verdict(repro="  "), input_path="x", case_name="case.mlir")


@pytest.mark.parametrize("oracle_class", ["differential", "fatal_error"])
def test_repair_05_refused_by_class(tmp_path, monkeypatch, oracle_class):
    """T-U-repair-05 (FR-08.10): `differential` and `fatal_error` are refused with the reason recorded, before the chain is invoked at all."""
    over = {"oracle_class": oracle_class, "assertion_text": None,
            "assertion_site": None}
    if oracle_class == "differential":
        over["frame_tuple"] = []
    with pytest.raises(RepairRefused) as refused:
        _attempt(tmp_path, monkeypatch, candidate=_candidate(tmp_path, **over))
    assert refused.value.reason == f"oracle_class_{oracle_class}"


def test_repair_06_refused_out_of_scope_root(tmp_path, monkeypatch):
    """T-U-repair-06 (FR-12.5): an out-of-scope root never invokes the chain."""
    chain = _Recorder({"status": "fixed"})
    with pytest.raises(RepairRefused) as refused:
        _attempt(tmp_path, monkeypatch, chain=chain,
                 candidate=_candidate(tmp_path, out_of_scope_root=True))
    assert refused.value.reason == "out_of_scope_root"
    assert chain.calls == []


def test_repair_06b_no_repair_refuses_before_the_interlock(tmp_path, monkeypatch):
    """§3.8 consequence 4: `--no-repair` leaves F-12's rows empty with `repair_disabled` as the stated reason, and asks for no credential at all."""
    chain = _Recorder({"status": "fixed"})
    with pytest.raises(RepairRefused) as refused:
        _attempt(tmp_path, monkeypatch, chain=chain, env={},
                 cfg={"repair_backend": "vertex", "repair_enabled": False})
    assert refused.value.reason == "repair_disabled"
    assert chain.calls == []


def _chia_checkout():
    root = Path(repair_adapter.chia.__path__[0]).resolve().parent
    if not (root / ".git").exists():
        pytest.skip("CHIA is not an editable checkout on this host")
    return root


@pytest.mark.t1
def test_repair_07_the_patch_is_one_additive_hunk(tmp_path):
    """T-U-repair-07, T-U-repair-21 (FR-12.1): `git apply --check` accepts the patch at `16c35e92`, the applied diff is **one hunk, 21 insertions and 0 deletions** over **one** path, and the patched file parses."""
    root = _chia_checkout()
    patch = Path(__file__).resolve().parents[2] / "upstream" / "issue_task-vertex-branch.patch"
    assert subprocess.run(["git", "-C", str(root), "apply", "--check", str(patch)],
                          capture_output=True).returncode == 0

    work = tmp_path / "chia"
    work.mkdir()
    target = work / "examples" / "circt_issue_solver"
    target.mkdir(parents=True)
    subprocess.run(["git", "-C", str(work), "init", "-q"], check=True)
    baseline = subprocess.run(
        ["git", "-C", str(root), "show", "16c35e92:examples/circt_issue_solver/issue_task.py"],
        capture_output=True, text=True, check=True).stdout
    (target / "issue_task.py").write_text(baseline, encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(work), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "baseline"], check=True)
    subprocess.run(["git", "-C", str(work), "apply", str(patch)], check=True)

    numstat = subprocess.run(["git", "-C", str(work), "diff", "--numstat"],
                             capture_output=True, text=True, check=True).stdout.split()
    assert numstat == ["21", "0", "examples/circt_issue_solver/issue_task.py"]
    diff = subprocess.run(["git", "-C", str(work), "diff", "-U0"],
                          capture_output=True, text=True, check=True).stdout
    assert diff.count("\n@@") == 1, "exactly one hunk"
    added = [line[1:] for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    from_patch = [line[1:] for line in patch.read_text().splitlines()
                  if line.startswith("+") and not line.startswith("+++")]
    assert added == from_patch
    ast.parse((target / "issue_task.py").read_text())
    assert 'elif backend == "vertex":' in "\n".join(added)


@pytest.mark.t1
def test_repair_08_the_six_prompts_are_byte_identical(tmp_path):
    """T-U-repair-08 (FR-12.9): every prompt the adapter passes is byte-identical to CHIA's own at `16c35e92`, compared against the file `build_cfg` read."""
    root = _chia_checkout()
    cfg = build_cfg(_candidate(tmp_path), _manifest(tmp_path),
                    local_id=LOCAL_ID_BASE + 7, budget=budget_file())
    for key, name in PROMPT_FILES.items():
        recorded = subprocess.run(
            ["git", "-C", str(root), "show",
             f"16c35e92:examples/circt_issue_solver/prompts/{name}"],
            capture_output=True, text=True, check=True).stdout
        assert cfg[key] == recorded, name


def test_repair_16_every_one_of_the_eighteen_cfg_keys(tmp_path):
    """T-U-repair-16 (FR-12.1): the key set is exactly the eighteen `run_issue_remote` reads, with §3.8's table's own values."""
    manifest = _manifest(tmp_path)
    cfg = build_cfg(_candidate(tmp_path), manifest, local_id=LOCAL_ID_BASE + 7,
                    budget=budget_file(), report_text="a report")

    assert set(cfg) == set(CFG_KEYS) and len(CFG_KEYS) == 18
    assert cfg["tool_targets"] == tuple(manifest.image_spec["targets"])
    assert cfg["require_repro"] is True
    # FOUR since W-19b, and the cluster YAML's `bugloop_repair --cpus` matches it.
    assert cfg["build_jobs"] == BUILD_JOBS == 4
    assert cfg["timeouts"] == PHASE_TIMEOUTS
    assert cfg["vertex"] == {"project": os.environ.get("GOOGLE_CLOUD_PROJECT"),
                             "location": "global"}
    assert cfg["repro_path"] == os.path.join(cfg["repro_dir"], "repro.sh")
    prompts = issue_solver_dir() / "prompts"
    for key, name in PROMPT_FILES.items():
        assert cfg[key] == (prompts / name).read_text(), key


def test_repair_09_the_tag_is_the_candidates_own_commit(tmp_path, monkeypatch):
    """T-U-repair-09 (FR-02.7): `cfg["tag"]` is `candidate.run_commit` and `circt_git_reset` is called with it, against a **calibration** manifest whose `run_commit[0]` is another seed's commit (K14)."""
    run = _attempt(tmp_path, monkeypatch)
    other = run.manifest.run_commit[0].commit

    assert run.manifest.mode == "calibration" and len(run.manifest.run_commit) == 2
    assert other != run.candidate.run_commit
    assert run.chain.calls[0]["cfg"]["tag"] == run.candidate.run_commit
    assert run.util.reset_calls == [run.candidate.run_commit]
    assert other not in run.util.reset_calls
    assert "firtool-1.148.0" not in run.util.reset_calls
    assert "HEAD" not in run.util.reset_calls


def test_repair_15_phase_timeouts_are_chias_own(tmp_path, monkeypatch):
    """T-U-repair-15 (FR-12.1): `PHASE_TIMEOUTS` is CHIA's dict verbatim and the chain is invoked with it unaltered."""
    assert PHASE_TIMEOUTS == {"assess": 1800, "repro": 1800, "fix": 7200,
                              "regression": 3600, "writeup": 1200}
    run = _attempt(tmp_path, monkeypatch)
    assert run.chain.calls[0]["cfg"]["timeouts"] == PHASE_TIMEOUTS


def test_repair_20_stage_seven_runs_on_the_campaign_backend(tmp_path, monkeypatch):
    """T-U-repair-20 (FR-12.1): `cfg["backend"]` is the backend half of `model_ids["repair_adapt"]` and `cfg["model"]` its model-id half; on a default run the pair is `vertex:gemini-3.8-flash` and equals `manifest.backend`, and under the fallback the pair diverges."""
    run = _attempt(tmp_path, monkeypatch)
    cfg = run.chain.calls[0]["cfg"]
    assert cfg["backend"] == run.manifest.backend == "vertex"
    assert cfg["model"] == "gemini-3.8-flash"
    assert run.manifest.model_ids["repair_adapt"] == "vertex:gemini-3.8-flash"
    assert run.manifest.stages_metered["stage_7"] is True
    assert run.result.backend == "vertex"

    fallback = _manifest(tmp_path)
    fallback.model_ids["repair_adapt"] = "claude:claude-opus-4-6"
    fallback.stages_metered["stage_7"] = False
    other = _attempt(tmp_path, monkeypatch, manifest=fallback,
                     cfg={"repair_backend": "claude"})
    assert other.chain.calls[0]["cfg"]["backend"] == "claude"
    assert other.chain.calls[0]["cfg"]["model"] == "claude-opus-4-6"
    assert other.result.backend == "claude"


def test_repair_20b_a_backend_disagreement_is_refused(tmp_path, monkeypatch):
    """`stages_metered["stage_7"]` reads the manifest and the chain reads the flag; a run in which the two disagree would make the ledger false."""
    with pytest.raises(ValueError, match="stage_7"):
        _attempt(tmp_path, monkeypatch, cfg={"repair_backend": "claude"})


def test_repair_20c_the_generators_cfg_is_refused_by_name(tmp_path, monkeypatch):
    """K3, K6: an incomplete cfg refuses loudly, and `build_cfg` is the head's."""
    from circt_bug_loop import bug_loop

    manifest = _manifest(tmp_path)
    generator_cfg = bug_loop.generator_cfg(
        manifest, budget_file(), clone_path=str(tmp_path), iteration=1)
    assert "repair_backend" not in generator_cfg
    assert set(CFG_KEYS) & set(generator_cfg) == {"max_tool_iterations"}, \
        "the per-stage caps are the one name both cfgs carry, by different shape"

    _recording_interlock(monkeypatch)
    monkeypatch.setitem(sys.modules, "circt_util", _CirctUtil())
    case = tmp_path / "reduced.mlir"
    shutil.copyfile(REPAIR / "case.mlir", case)
    with pytest.raises(ValueError) as raised:
        call_node(repair_adapt, _report(), _candidate(tmp_path), _reduced(case),
                  _verdict(), manifest,
                  {"repair_backend": "vertex", **generator_cfg},
                  local_id=LOCAL_ID_BASE + 7, input_path="/art/probe/input.mlir",
                  env=dict(ALLOW_ENV))
    message = str(raised.value)
    assert "build_cfg" in message
    # Every one CHIA reads is named as missing, none of them silently; the
    # per-stage caps are present under the same name in the generator's own
    # dict shape, and are refused for that instead.
    for key in CFG_KEYS - {"max_tool_iterations"}:
        assert key in message, key

    # And `build_cfg` reads the six prompt bodies from a directory only the head has.
    solver = issue_solver_dir()
    assert (solver / "prompts").is_dir()
    assert solver.parent.name == "examples"
    node = inspect.getsource(repair_adapt._chia_original)
    assert "build_cfg(" not in node, "B8 must not assemble its own cfg (K6)"


@pytest.mark.parametrize("name,status", [
    ("fixed.json", "fixed"), ("attempted.json", "attempted"),
    ("no_repro.json", "no_repro"), ("unclear.json", "unclear"),
    ("not_a_bug.json", "not_a_bug"), ("error.json", "error")])
def test_repair_10_all_six_statuses_round_trip(tmp_path, monkeypatch, name, status):
    """T-U-repair-10 (FR-12.7): every one of CHIA's six statuses becomes a `RepairResult`, with the failing phase named where a phase failed."""
    run = _attempt(tmp_path, monkeypatch, verdict=name)
    recorded = json.loads((VERDICTS / name).read_text())

    assert run.result.status == status
    assert run.result.failing_phase == failing_phase(recorded["logs"])
    assert run.result.local_id == LOCAL_ID_BASE + 7
    assert run.result.candidate_id == "cand-0001"
    if status in ("unclear", "error"):
        assert run.result.failing_phase == "assess"
    if status == "fixed":
        assert (run.result.fixed, run.result.lit_ok) == (True, True)
        assert run.result.diff_added == 2 and run.result.diff_removed == 1
        assert Path(run.result.diff_path).read_text() == recorded["diff"]


def test_repair_11_a_red_lit_gate_attaches_no_patch(tmp_path, monkeypatch):
    """T-U-repair-11 (FR-12.8): `lit_ok=false` with the failing test names, which is what stops the gate returning `report_plus_patch`."""
    run = _attempt(tmp_path, monkeypatch, verdict="lit_red.json")
    assert run.result.lit_ok is False and run.result.lit_unusable is False
    assert run.result.lit_failed == 2
    assert run.result.lit_failures == ["CIRCT :: Dialect/HW/basic.mlir",
                                       "CIRCT :: Conversion/HWToSV/lower.mlir"]
    assert not (run.result.fixed and run.result.lit_ok)


def test_repair_12_zero_discovered_is_unusable_not_red(tmp_path, monkeypatch):
    """T-U-repair-12 (FR-12.8): a lit run reporting `passed == 0 and failed == 0` over a non-empty path list records `lit_unusable` and NOT `lit_ok=false`; an absent gate is not a red one, and the caller stops the run on the field."""
    run = _attempt(tmp_path, monkeypatch, verdict="lit_zero.json")
    assert run.result.lit_unusable is True
    assert run.result.lit_ok is None
    assert run.result.lit_passed == 0 and run.result.lit_failed == 0
    assert "FR-03.17" in inspect.getdoc(repair_adapter._as_repair_result)


def test_repair_13_the_restore_is_three_things(tmp_path, monkeypatch):
    """T-U-repair-13 (FR-12.11): reset, rebuild, **and** a re-hash of every tool binary against `ImageSpec.tool_hashes`; `restore_ok` is the conjunction."""
    run = _attempt(tmp_path, monkeypatch)
    targets = tuple(run.manifest.image_spec["targets"])
    assert run.util.reset_calls == [run.candidate.run_commit]
    assert run.util.build_calls == [{"targets": targets, "num_cpus": BUILD_JOBS}]
    assert run.result.restore_hashes_match is True
    assert run.result.restore_ok is True
    assert "re-hash against ImageSpec.tool_hashes: match" in run.result.restore_log

    dirty = _attempt(tmp_path, monkeypatch, match=False)
    assert dirty.result.restore_hashes_match is False
    assert dirty.result.restore_ok is False
    assert "MISMATCH" in dirty.result.restore_log

    failed = _attempt(tmp_path, monkeypatch, util=_CirctUtil(build_ok=False))
    assert failed.result.restore_ok is False
    assert "ninja" in failed.result.restore_log


def test_repair_13b_the_restore_runs_on_a_failing_attempt_too(tmp_path, monkeypatch):
    """FR-12.11: "after every attempt, whatever its outcome"."""
    class _Boom(_Recorder):
        def run_issue_remote(self, *args, **kwargs):
            raise RuntimeError("the chain died mid-fix")

    util = _CirctUtil()
    with pytest.raises(RuntimeError, match="mid-fix"):
        _attempt(tmp_path, monkeypatch, chain=_Boom({}), util=util)
    assert util.reset_calls and util.build_calls


def test_repair_18_the_repro_dir_is_outside_the_circt_tree(tmp_path, monkeypatch):
    """T-U-repair-18 (FR-12.3): `cfg["repro_dir"]` is `<artefact_root>/<run>/repair/<local_id>/` and neither it nor `repro_path` lies under `/workspace/circt`, which the chain's own `git clean -fd` clears because `.circtissues` is untracked and matches nothing in `.gitignore`."""
    run = _attempt(tmp_path, monkeypatch)
    cfg = run.chain.calls[0]["cfg"]
    expected = os.path.join(run.manifest.artefact_root,
                            run.manifest.run_manifest_id, "repair",
                            str(LOCAL_ID_BASE + 7))

    assert cfg["repro_dir"] == expected == run.result.repro_dir
    assert not cfg["repro_dir"].startswith("/workspace/circt")
    assert not cfg["repro_path"].startswith("/workspace/circt")
    assert ".circtissues" not in cfg["repro_dir"]
    directory = Path(cfg["repro_dir"])
    assert (directory / "repro.sh").exists() and (directory / "case.mlir").exists()
    assert (directory / "case.mlir").read_text() == (REPAIR / "case.mlir").read_text()
    assert os.stat(directory / "repro.sh").st_mode & 0o111, "circt_write_files chmods"


def test_repair_19_repro_overwritten_is_measured_both_ways(tmp_path, monkeypatch):
    """T-U-repair-19 (FR-12.3): `sha256` before the chain and again after, both written beside the script, and `repro_overwritten` set on a difference."""
    same = _attempt(tmp_path, monkeypatch)
    directory = Path(same.result.repro_dir)
    before = (directory / "repro.sh.sha256.before").read_text().strip()
    after = (directory / "repro.sh.sha256.after").read_text().strip()

    assert same.result.repro_overwritten is False
    assert before == after == hashlib.sha256(
        (directory / "repro.sh").read_bytes()).hexdigest()

    rewritten = _attempt(tmp_path / "second", monkeypatch,
                         overwrite="#!/bin/sh\nexit 0\n")
    where = Path(rewritten.result.repro_dir)
    assert rewritten.result.repro_overwritten is True
    assert (where / "repro.sh.sha256.before").read_text().strip() != (
        where / "repro.sh.sha256.after").read_text().strip()


def test_repair_17_the_chain_is_called_inline(tmp_path, monkeypatch):
    """T-U-repair-17 (FR-12.1): the call site is the bare name `run_issue_remote(issue_md, local_id, cfg)` and never `.chia_remote`, so the chain and the three tools it stands up land on the `repair:1` worker."""
    source = Path(repair_adapter.__file__).read_text()
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "run_issue_remote"]
    assert len(calls) == 1
    assert [arg.id for arg in calls[0].args] == ["issue_md", "local_id", "chain_cfg"]
    assert "run_issue_remote.chia_remote" not in source
    assert ".options(" not in source

    run = _attempt(tmp_path, monkeypatch)
    assert len(run.chain.calls) == 1
    assert run.chain.calls[0]["number"] == LOCAL_ID_BASE + 7
    assert run.chain.calls[0]["issue_md"].startswith("# Issue #900000007:")
    assert repair_adapt._chia_options["resources"] == {"repair": 1}


def test_repair_22_the_interlock_gates_stage_seven(tmp_path, monkeypatch):
    """T-U-repair-22 (FR-12.1): `repair_adapt` calls `llm.require_live_model` **before** it invokes the chain."""
    chain = _Recorder({"status": "fixed"})
    with pytest.raises(llm.LiveModelRefused):
        _attempt(tmp_path, monkeypatch, chain=chain, env={})
    assert chain.calls == [], "not one request may be made behind the interlock"

    with pytest.raises(llm.LiveModelRefused, match="GEMINI_API_KEY"):
        _attempt(tmp_path / "b", monkeypatch, chain=chain,
                 env={"BUGLOOP_ALLOW_LIVE_MODEL": "1",
                      "GEMINI_API_KEY": "${GEMINI_API_KEY}"})
    assert chain.calls == []

    fallback = _manifest(tmp_path)
    fallback.model_ids["repair_adapt"] = "claude:claude-opus-4-6"
    run = _attempt(tmp_path / "c", monkeypatch, manifest=fallback,
                   env={"BUGLOOP_ALLOW_LIVE_MODEL": "1"},
                   cfg={"repair_backend": "claude"})
    assert run.generate.calls == [{"purpose": "stage 7 repair of cand-0001",
                                   "need_key": False}]
    assert run.result.status == "fixed"


def test_repair_22b_the_loop_names_vertex_in_one_place_only(tmp_path):
    """T-U-layout-08's second clause, for this module: `repair_adapter.py` names no backend class at all."""
    source = Path(repair_adapter.__file__).read_text()
    assert "VertexGeminiLLM" not in source
    assert "require_live_model" in source


def test_repair_23_stage_sevens_tokens_are_null_with_a_reason(tmp_path, monkeypatch):
    """T-U-repair-23 (FR-12.1): the stage-7 `observed` carries **null** tokens and a **null** `cost_usd`, never zero; the reason lives on `RepairResult.token_capture` and is not a key of `observed`, whose eight declared keys are frozen by §2.2's rule."""
    observed = stage7_observed(12.5)
    assert observed == {"cpu_seconds": 12.5, "authorised_usd": None,
                        "ceiling_usd": None, "billed_usd": None, "calls": None,
                        "tokens_in": None,
                        "tokens_out": None, "cost_usd": None}
    assert set(observed) == schema._DICT_KEYS[("LedgerEntry", "observed")]
    assert "token_capture" not in observed
    assert schema.CONTRACT_VERSION == "2.3"

    run = _attempt(tmp_path, monkeypatch)
    assert run.result.token_capture == "unavailable_remote_dispatch"
    assert run.result.backend == "vertex"

    # The mechanism, on CHIA's own source, so the gap cannot be closed by accident and then silently reopened.
    turn = (issue_solver_dir() / "issue_task.py").read_text()
    assert 'get(llm.prompt.options(resources={"llm": 1.0}).chia_remote(' in turn


def test_repair_24_the_node_keeps_its_decorator_and_its_docstring(tmp_path):
    """§3.1, §3.2: the node declares `{"repair": 1}` and its docstring carries the three paragraphs §3.1 obliges every node to state."""
    assert repair_adapt._chia_options["resources"] == {"repair": 1}
    assert repair_adapt._chia_options.get("max_retries") == 0
    doc = inspect.getdoc(repair_adapt)
    for paragraph in ("Returns:", "Worker:", "Raises:"):
        assert paragraph in doc
    assert '{"repair": 1}' in doc


def test_repair_25_stage_seven_carries_its_cap_and_its_ceiling(tmp_path, monkeypatch):
    """T-U-repair-25 (W-18d): the registered stage-7 cap and W1's worst case reach the chain."""
    funds = budget_file()
    report_text = "a report" * 100
    cfg = build_cfg(_candidate(tmp_path), _manifest(tmp_path),
                    local_id=LOCAL_ID_BASE + 7, budget=funds,
                    report_text=report_text)

    assert cfg["max_tool_iterations"] == funds.max_tool_iterations["stage_7"] == 20
    guard = llm.SpendGuard(
        cap_usd=float(funds.campaign_spend_cap_usd), spend_usd=0.0,
        price_usd_per_m_input_tokens=funds.price_usd_per_m_input_tokens,
        price_usd_per_m_output_tokens=funds.price_usd_per_m_output_tokens)
    assert cfg["turn_budget_usd"] == guard.worst_case_usd({
        "system_message": max((cfg[key] for key in PROMPT_FILES), key=len),
        "prompt": report_text, "tools": [True], "max_tool_iterations": 20})

    # A longer report is a dearer turn, and the ceiling follows it.
    dearer = build_cfg(_candidate(tmp_path), _manifest(tmp_path),
                       local_id=LOCAL_ID_BASE + 7, budget=funds,
                       report_text=report_text * 10)
    assert dearer["turn_budget_usd"] > cfg["turn_budget_usd"]

    # The chain is handed both, and the vertex branch passes both on.
    run = _attempt(tmp_path, monkeypatch)
    handed = run.chain.calls[0]["cfg"]
    assert handed["max_tool_iterations"] == 20
    assert handed["turn_budget_usd"] == build_cfg(
        run.candidate, run.manifest, local_id=LOCAL_ID_BASE + 7,
        budget=budget_file(), report_text="a report")["turn_budget_usd"] > 0
    patch = (Path(__file__).resolve().parents[2] / "upstream"
             / "issue_task-vertex-branch.patch").read_text(encoding="utf-8")
    assert '+                max_tool_iterations=cfg["max_tool_iterations"],' in patch
    assert '+                turn_budget_usd=cfg["turn_budget_usd"],' in patch

    # And what the attempt cost is recorded as authorised, never as billed.
    usage = run.logs["usage"]
    assert usage["authorised_usd"] == round(
        len(PHASE_TIMEOUTS) * handed["turn_budget_usd"], 6)
    assert usage["ceiling_usd"] == handed["turn_budget_usd"]
    assert usage["billed_usd"] is None and usage["calls"] is None


def test_repair_26_a_generator_shaped_cap_is_refused(tmp_path, monkeypatch):
    """T-U-repair-26 (K3, K6): a per-stage dict where the chain wants one integer."""
    _recording_interlock(monkeypatch)
    monkeypatch.setitem(sys.modules, "circt_util", _CirctUtil())
    case = tmp_path / "reduced.mlir"
    shutil.copyfile(REPAIR / "case.mlir", case)
    manifest = _manifest(tmp_path)
    cfg = {**build_cfg(_candidate(tmp_path), manifest, local_id=LOCAL_ID_BASE + 7,
                       budget=budget_file(), report_text="a report"),
           "repair_enabled": True, "repair_backend": "vertex",
           "max_tool_iterations": {"stage_7": 20}}
    with pytest.raises(ValueError) as raised:
        call_node(repair_adapt, _report(), _candidate(tmp_path), _reduced(case),
                  _verdict(), manifest, cfg, local_id=LOCAL_ID_BASE + 7,
                  input_path="/art/probe/input.mlir", env=dict(ALLOW_ENV))
    assert "max_tool_iterations" in str(raised.value)
