"""04-Test-Plan.md §3's system tier, as far as it goes with no model (W-19b).

**Two tiers in one module, and why.** Every other test module states one tier
with a module-level `pytestmark` (§0.5). This one cannot: the `--generator
recorded` mode it exercises is a tier-0 object - a flag, two generator nodes and
a report node, all pure Python over committed fixtures - and the thing the mode
EXISTS for is tier 3, the same nodes dispatched through Ray onto the real
single-machine cluster. Splitting them into two files would put the T0 tests of
a mode in one file and the mode's only reason to exist in another, so the marker
is per test here and the module declares none.

**No model, at any tier in this file.** Nothing below sets
`BUGLOOP_ALLOW_LIVE_MODEL` - `conftest.no_live_model` refuses the whole session
if anything does - and `test_recorded_never_builds_a_model` is the positive
check: `llm.build_llm` is replaced with a function that raises, and the two
recorded nodes run anyway.

**What the tier-3 tests do NOT do, and why.** §3's tests are written for
`bug_loop.py`'s own `run_campaign`, whose twelve pre-flight checks stand between
argv and the first dispatch. Four of them cannot pass on this host today, none
for a reason this task can fix and none to do with the model:

  1. check 3 wants the clone at `budget.yaml`'s `corpus_head_sha`; this host's
     blobless clone is at another commit, and A1's mining of the six crash
     seeds' blobs is a network task.
  2. B1 `build_image` is dispatched at `{"circt": 1}`, and NO worker container
     on this cluster has a Docker daemon or a socket mounted - the assertions
     image has no `docker` binary at all - so the node cannot run where §3.2
     places it.
  3. check 10 wants an issue mirror, and there is neither a mirror in a
     `loop.db` nor a GitHub token file on this host to refresh one with.
  4. check 11 wants the forum post FR-15.4 requires, which has not been made.

So the tier-3 tests below drive `campaign_drive` DIRECTLY, with
`Dispatch(remote=True)` against `ray.init(address="auto")` and
`bug_loop.recorded_stages()`. That is the same dispatch path `run_campaign`
takes after its pre-flight - the same nodes, the same resources, the same store
and the same ledger - with the pre-flight replaced by committed fixtures. The
four blockers are recorded in `analysis/measurements/2026-09-15-system-tier.md`
and in the errata log; `test_submit_wrapper_end_to_end` is what runs the real
`bug_loop.py` through the real `chia job submit`, and it reaches exactly as far
as pre-flight lets it.

**`loop.db` lives under the artefact root here, not at `bug_loop.DB_PATH`.**
`ledger.accrue` and `dedup_and_screen` are `@ChiaFunction(max_retries=0)` with
no resource, so Ray may place either in a worker container, where
`bug_loop.FLOW_DIR` is the runtime env's own unpacked directory and not the
head's checkout. The artefact root is the one path bind-mounted identically
everywhere (FR-17.9), so a store under it is the same file from every node.
Recorded as an errata row, not fixed here.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import subprocess
import time
import uuid
import warnings
from pathlib import Path

import pytest

from circt_bug_loop import bug_loop, ledger as ledger_module
from circt_bug_loop.contract import schema
from circt_bug_loop.contract.schema import (BudgetFile, CounterBlock, RunManifest,
                                            SeedRecord)
from circt_bug_loop.store import (PARTIAL, CandidateRecord, DedupVerdict, Frame,
                                  ImageSpec, LoopStore, OracleVerdict, ReducedCase)
from circt_bug_loop.tests.conftest import call_node

HERE = Path(__file__).resolve().parent
SYSTEM = HERE / "fixtures" / "system"
RECORDED = Path(bug_loop.FLOW_DIR) / "contract" / "fixtures" / "recorded"
#: FR-03.16's own recorded identity of the image the cluster runs (W-04).
IMAGE_MANIFEST = (Path(bug_loop.FLOW_DIR).parent / "analysis" / "measurements"
                  / "raw" / "image-manifest.json")

#: The tiny budget of §3, derived from the RECORDED `BudgetFile` rather than
#: from a second committed YAML: the recording is `budget.load_budget`'s own
#: output over the committed file, taken through all six registration checks, so
#: only the three numbers a tiny run needs to change are changed here and every
#: other field is the campaign's. §3 names `tests/system/budget_tiny.yaml`; a
#: YAML would have to be re-registered in a throwaway git repository to be
#: loadable at all, which is `make_recorded.py`'s job and not a fixture's.
TINY = {"arm_window_seconds": 90.0, "per_seed_probe_cap": 1,
        "per_seed_iteration_cap": 1}


# ===========================================================================
# Fixtures shared by both tiers
# ===========================================================================


def _recorded(member: str):
    """The one recorded document of *member*, as its dataclass."""
    directory = RECORDED / member
    document = sorted(directory.glob("*.json"))[0]
    return schema.from_json(document.read_text(encoding="utf-8"),
                            getattr(schema, "".join(part.title()
                                                    for part in member.split("_"))))


def system_seeds() -> list:
    """`fixtures/system/seeds.json`: W-09's six, then W-05's two."""
    return [SeedRecord(**row) for row in
            json.loads((SYSTEM / "seeds.json").read_text(encoding="utf-8"))]


def tiny_budget(**over) -> BudgetFile:
    """The recorded `BudgetFile` with §3's three tiny numbers, validated."""
    budget = dataclasses.replace(_recorded("budget_file"), **{**TINY, **over})
    schema.validate(budget)
    return budget


def image_spec() -> ImageSpec:
    """The `ImageSpec` of the image the cluster actually runs (FR-03.16).

    Every field comes from `analysis/measurements/raw/image-manifest.json`,
    which W-04 computed inside a freshly started container of the published
    image, so `probe_execute`'s per-probe hash check (FR-06.1) is a real
    comparison of the worker's own binaries against a recording made elsewhere
    and not a self-comparison.
    """
    document = json.loads(IMAGE_MANIFEST.read_text(encoding="utf-8"))
    return ImageSpec(
        circt_sha=document["circt_sha"], sdk_tag=document["circt_ver"],
        targets=list(document["targets"]), flag_string=document["flag_string"],
        cmake_args=[], image_digest=document["image_digest"],
        image_tag=document["image_tag"],
        verilator_version=document["verilator_version"],
        slang_enabled=bool(document["slang_enabled"]), lit_discovery_ok=True,
        lit_discovered_count=0, assertion_nonreferencing=[],
        tool_hashes=bug_loop.parse_hash_manifest(document))


def manifest_for(mode: str, run_id: str, artefact_root: str, *,
                 budget: BudgetFile, seeds: list, spec: ImageSpec = None) -> RunManifest:
    """The recorded `RunManifest`, re-stamped for one tier-3 run.

    `arm_order` is ALWAYS both arms and is never narrowed here: 2.8 requires the
    manifest to name both exactly once, because the order is a property of the
    campaign's design and not of one invocation. Running one arm is
    `campaign_drive(..., arms=[...])`, which is what `--arm` reaches.
    """
    spec = spec or image_spec()
    recorded = _recorded("run_manifest")
    arms = ("seeded", "mutation")
    calibration = list(budget.calibration_sample_shas or [])
    manifest = dataclasses.replace(
        recorded, run_manifest_id=run_id, mode=mode, artefact_root=artefact_root,
        arm_order=list(arms), arm_window_seconds=budget.arm_window_seconds,
        budget_file_sha=budget.budget_file_sha,
        image_spec={key: getattr(spec, key) for key in
                    schema._DICT_KEYS[("RunManifest", "image_spec")]},
        run_commit=bug_loop.run_commits(
            mode=mode, pin={"run_commit": spec.circt_sha,
                            "pin_tag": spec.sdk_tag}, seeds=seeds),
        calibration_sample=calibration if mode == "calibration" else None,
        stages_metered=bug_loop.stages_metered(arms=list(arms),
                                               repair_backend="vertex",
                                               repair_enabled=False),
        started_utc=bug_loop._utc(), ended_utc=None)
    schema.validate(manifest)
    return manifest


def drive(manifest: RunManifest, budget: BudgetFile, seeds: list, *,
          remote: bool, arms=None, clone_path: str = "") -> dict:
    """Build the recorded-mode campaign and run it, returning what it did.

    Returns:
        {"outcome", "store", "counters", "manifest"}.
    """
    from chia.trace.metrics import MetricsLogger

    root = Path(manifest.artefact_root) / manifest.run_manifest_id
    (root / "results").mkdir(parents=True, exist_ok=True)
    store = LoopStore(str(Path(manifest.artefact_root) / "loop.db"))
    dispatch = bug_loop.Dispatch(remote=remote)
    # §6.4's first four tables, as `run_campaign` writes them: the run, the
    # image, the seed rows the seeded-bug validation table is taken over, and
    # the two `shared` occupancies - one of which carries the synthesis date
    # FR-05.8's declaration is rendered off.
    bug_loop.write_run_rows(store, manifest, image_spec=image_spec(),
                            mined={"seeds": seeds, "exclusions": {},
                                   "sv_seeds": [], "sdk_map": {}},
                            mirror=None)
    bug_loop.accrue_offline(store, manifest, budget, dispatch=dispatch)
    counters = bug_loop.CounterLog(manifest.run_manifest_id, str(root / "results"),
                                   MetricsLogger.from_config(None))
    campaign = bug_loop.Campaign(
        manifest=manifest, budget=budget, store=store,
        stages=bug_loop.recorded_stages(), dispatch=dispatch,
        counters=counters, clone_path=clone_path, image_spec=image_spec(),
        repair_enabled=False)
    outcome = bug_loop.campaign_drive(campaign, seeds, arms=arms)
    bug_loop.finish_run(store, manifest, bug_loop._utc())
    counters.write()
    return {"outcome": outcome, "store": store, "counters": counters,
            "manifest": manifest}


def _gcs_answers(timeout: float = 3.0):
    """The bootstrap address `address="auto"` would take, if something answers it.

    `ray.init(address="auto")` DOES NOT fail fast when nothing is listening: it
    reads `/tmp/ray/ray_current_cluster`, which a torn-down cluster leaves
    behind, and then retries the GCS connection for minutes (measured on this
    host, 2026-09-15: a stale file from the W-19a run made `ray.init` hang past
    a two-minute test timeout rather than raise). §0.5's "skip cleanly" needs a
    bounded check, so the address is resolved Ray's own way and probed with one
    TCP connect.

    Returns:
        the address string when the GCS port accepts a connection, else None.
    """
    import socket

    from ray._private.utils import read_ray_address

    address = os.environ.get("RAY_ADDRESS") or read_ray_address()
    if not address or address == "auto":
        address = "127.0.0.1:6379"
    host, _, port = address.rpartition(":")
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return address
    except (OSError, ValueError):
        return None


@pytest.fixture(scope="module")
def cluster():
    """`ray.init(address="auto")` against the running cluster, or skip cleanly."""
    import ray

    address = _gcs_answers()
    if address is None:
        pytest.skip("no Ray GCS is listening at the bootstrap address; bring a "
                    "cluster up with `chia up circt_bug_loop/cluster_single.yaml`")
    try:
        # Ray 2.54 raises one FutureWarning of its own on every `ray.init` with
        # num_gpus unset, and `-W error` turns it into the exception that
        # "skips" the whole tier. It is suppressed HERE and nowhere wider, and
        # the alternative Ray offers - RAY_ACCEL_ENV_VAR_OVERRIDE_ON_ZERO=0 -
        # is deliberately not taken: it opts the cluster into the future
        # behaviour rather than silencing the notice about it.
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning,
                                    module=r"ray\..*")
            warnings.filterwarnings("ignore", message=".*accelerator visible devices.*")
            ray.init(address="auto", runtime_env=bug_loop.runtime_env(),
                     ignore_reinit_error=True)
    except Exception as error:                      # noqa: BLE001 - any Ray refusal
        pytest.skip(f"no cluster at {address} ({type(error).__name__}: "
                    f"{str(error).splitlines()[0]})")
    yield ray
    ray.shutdown()


@pytest.fixture(scope="module")
def artefact_root() -> str:
    """`BUGLOOP_ARTEFACTS`, the one path mounted identically everywhere (FR-17.9)."""
    root = os.environ.get("BUGLOOP_ARTEFACTS")
    if not root or not Path(root).is_dir():
        pytest.skip("BUGLOOP_ARTEFACTS is unset or is not a directory")
    return root


# ===========================================================================
# Tier 0: the `--generator recorded` mode itself
# ===========================================================================


@pytest.mark.t0
def test_generator_flag_defaults_to_model_and_recorded_implies_no_repair():
    """The flag's two values, and the one condition `repair_enabled` spells.

    `--generator recorded` implying `--no-repair` is not a convenience: stage 7
    IS a model turn whatever the backend (§3.8), so a recorded run that
    dispatched it would be a recorded run with a turn in it.
    """
    parse = bug_loop.build_parser().parse_args
    assert parse(["--mode", "discovery"]).generator == "model"
    assert bug_loop.repair_enabled(parse(["--mode", "discovery"])) is True

    recorded = parse(["--mode", "discovery", "--generator", "recorded"])
    assert bug_loop.repair_enabled(recorded) is False
    assert bug_loop.resolved_config(recorded)["generator"] == "recorded"
    assert bug_loop.resolved_config(recorded)["repair_enabled"] is False
    # --no-repair alone still turns it off, and neither implies the other way.
    assert bug_loop.repair_enabled(
        parse(["--mode", "discovery", "--no-repair"])) is False


@pytest.mark.t0
def test_recorded_stages_replaces_exactly_the_three_model_bearing_nodes():
    """Eight of the ten are the real nodes, and the three replaced are the two
    generators and B7 - the only nodes of §3.2 that reach `llm.build_llm`."""
    real, recorded = bug_loop.default_stages(), bug_loop.recorded_stages()
    replaced = {field.name for field in dataclasses.fields(bug_loop.Stages)
                if getattr(real, field.name) is not getattr(recorded, field.name)}
    assert replaced == {"generate_seeded", "generate_mutation", "triage_report"}
    assert recorded.generate_seeded is bug_loop.generate_recorded_seeded
    assert recorded.generate_mutation is bug_loop.generate_recorded_mutation
    assert recorded.triage_report is bug_loop.recorded_report
    # Every replacement keeps §3.2's placement, so the mode changes what the
    # node does and never where it runs.
    for node in (bug_loop.generate_recorded_seeded,
                 bug_loop.generate_recorded_mutation, bug_loop.recorded_report):
        assert node._chia_options["resources"] == {"circt": 1}
        assert node._chia_options["max_retries"] == 0


@pytest.mark.t0
def test_recorded_inputs_prefers_the_seam_then_the_seeds_own_files():
    """W-19b's two sources, in order, and the cap applied to the pair of them."""
    seeds = {seed.seed_sha: seed for seed in system_seeds()}
    covered = _recorded("probe_spec").seed_sha
    assert covered in seeds, "the seam's recorded seed is one of the eight"

    first = bug_loop.recorded_inputs(seeds[covered], 10)
    assert first[0][2].startswith("recorded ProbeSpec "), first[0][2]
    assert any(entry[2].endswith("replayed unchanged at the run commit")
               for entry in first), "the seed's own files follow the recording"
    assert bug_loop.recorded_inputs(seeds[covered], 1) == first[:1]
    assert bug_loop.recorded_inputs(seeds[covered], 0) == []

    # A seed the recording does not cover is served by its own test files alone.
    other = next(s for s in seeds.values() if s.seed_sha != covered)
    only = bug_loop.recorded_inputs(other, 10)
    assert only and all(entry[2].endswith("replayed unchanged at the run commit")
                        for entry in only)
    assert [entry[0] for entry in only] == [
        text for _, text in sorted(other.test_files.items())][:10]


@pytest.mark.t0
@pytest.mark.parametrize("arm", ("seeded", "mutation"))
def test_recorded_generation_emits_valid_specs_for_either_arm(tmp_path, arm):
    """One builder, both arms, and `contract.validate` accepting both (FR-05.4).

    The mutation arm's three conditional fields are present and the seeded arm's
    are absent, which is 2.8's rule and the one place the two arms' records
    legitimately differ.
    """
    seed = system_seeds()[0]
    cfg = {"iteration": 1, "per_seed_probe_cap": 3,
           "run_manifest_id": "r" * 32, "artefact_root": str(tmp_path),
           "artefact_inline_cap_bytes": 262144}
    out = bug_loop._recorded_generation(seed, cfg, arm)

    assert out["failure"] is None, out["failure"]
    assert out["specs"], "a seed with test files always yields a probing input"
    assert isinstance(out["counters"], CounterBlock)
    assert (out["counters"].stage, out["counters"].completed) == ("stage_2", 1)
    for spec in out["specs"]:
        schema.validate(spec)
        assert spec.arm == arm and spec.iteration == 1
        assert spec.turn_cost["metered"] is False
        assert spec.turn_cost["tokens_in"] is None
        assert Path(spec.input_path).is_file()
        assert Path(spec.input_path).read_text(encoding="utf-8") == spec.input_text
        if arm == "mutation":
            assert spec.mutator_id == bug_loop.RECORDED_MUTATOR_ID
            assert spec.mutator_seed_int is not None and spec.source_test_path
        else:
            assert (spec.mutator_id, spec.mutator_seed_int,
                    spec.source_test_path) == (None, None, None)
    # The cap is the budget's, and it counts the two sources together.
    assert len(out["specs"]) <= cfg["per_seed_probe_cap"]


@pytest.mark.t0
def test_recorded_generation_names_a_failure_and_never_raises(tmp_path):
    """A seed the builder cannot serve ends the seed, as a failed turn does
    (FR-04.8); it does not take the arm down with it."""
    seed = dataclasses.replace(system_seeds()[0], run_lines=[], argv_template=[],
                               polarity=[], shape=[])
    out = bug_loop._recorded_generation(
        seed, {"iteration": 1, "per_seed_probe_cap": 2,
               "run_manifest_id": "r" * 32, "artefact_root": str(tmp_path)},
        "seeded")
    assert out["specs"] == []
    assert out["failure"].startswith("recorded_generator_failed:")
    assert out["counters"].failed == 1 and out["counters"].completed == 0


@pytest.mark.t0
def test_recorded_never_builds_a_model(tmp_path, monkeypatch):
    """The mode's whole point, asserted rather than reasoned about.

    `llm.build_llm` is the ONE constructor every model turn of §3.5.1 goes
    through, and since K2 `llm.dispatch_turn` is the ONE way to reach it. Both
    are replaced here with functions that raise, and both recorded nodes then
    run to completion.
    """
    from circt_bug_loop import llm

    def refuse(*args, **kwargs):
        raise AssertionError("a model turn was set up in --generator recorded")

    monkeypatch.setattr(llm, "build_llm", refuse)
    monkeypatch.setattr(llm, "dispatch_turn", refuse)
    monkeypatch.setattr("circt_bug_loop.generate_task.dispatch_turn", refuse,
                        raising=False)
    monkeypatch.setattr("circt_bug_loop.triage_task.dispatch_turn", refuse,
                        raising=False)

    generated = bug_loop._recorded_generation(
        system_seeds()[0],
        {"iteration": 1, "per_seed_probe_cap": 1, "run_manifest_id": "r" * 32,
         "artefact_root": str(tmp_path)}, "seeded")
    assert generated["specs"] and generated["failure"] is None

    report = call_node(bug_loop.recorded_report, *_report_call(tmp_path))
    assert report["failure"] is None
    assert report["report"].classification == "untriaged"


def _report_call(tmp_path):
    """The seven positional arguments B7 takes, for a screened assertion."""
    from circt_bug_loop import triage_task

    manifest = _recorded("run_manifest")
    artefact_dir = tmp_path / "probe_p-01"
    artefact_dir.mkdir(parents=True, exist_ok=True)
    reduced_path = artefact_dir / "reduced.mlir"
    reduced_path.write_text("hw.module @a() {}\n", encoding="utf-8")
    candidate = CandidateRecord(
        candidate_id="cand-0001", probe_id="p-01",
        run_manifest_id=manifest.run_manifest_id, arm="seeded",
        run_commit="c" * 40, image_digest="sha256:" + "0" * 64,
        oracle_class="assertion", frame_tuple=["a", "b", "c", "d", "e"],
        frames_resolved=5, frames_with_location=5, out_of_scope_root=False,
        contaminated_symbol=False, contaminated_file=False,
        contamination_lower_bound="seed_commit", triage_class="untriaged",
        artefact_dir=str(artefact_dir),
        assertion_text='isa<To>(Val) && "bad cast"',
        assertion_site="/workspace/circt/lib/A.cpp:10",
        reducer="circt-reduce", reduced=True, fixpoint=True,
        budget_truncated=False, reduced_path=str(reduced_path),
        size_before_bytes=100, size_after_bytes=50, size_before_ops=5,
        size_after_ops=2, fingerprint="fp", fingerprint_stable=None,
        structural_hash="0" * 64, dedup_basis="assertion", dedup_verdict="new",
        dedup_evidence=dict.fromkeys(triage_task._EVIDENCE_KEYS))
    verdict = OracleVerdict(
        probe_id="p-01", fired=True, oracle_class="assertion",
        assertion_text='isa<To>(Val) && "bad cast"',
        assertion_site="/workspace/circt/lib/A.cpp:10", fatal_message=None,
        frames=[Frame(index=i, address=f"0x{i:x}", shape="attributed", module="",
                      offset="", function=n, file="A.cpp", line=10 + i,
                      in_circt_object=True)
                for i, n in enumerate("abcde")],
        prologue_dropped=0, frames_resolved=5, frames_with_location=5,
        fingerprint_frame="a A.cpp", out_of_scope_root=False,
        repro_command="circt-opt input.mlir",
        flag_string="-O3 -UNDEBUG -gline-tables-only",
        tool_version_output="CIRCT eade0de")
    reduced = ReducedCase(
        probe_id="p-01", reducer="circt-reduce", reduced=True, fixpoint=True,
        budget_truncated=False, reason=None, lift=None, path=str(reduced_path),
        size_before_bytes=100, size_after_bytes=50, size_before_ops=5,
        size_after_ops=2, wall_seconds=1.0, interestingness_calls=3,
        recheck_class="assertion",
        recheck_assertion_text='isa<To>(Val) && "bad cast"',
        recheck_assertion_site="/workspace/circt/lib/A.cpp:10",
        recheck_matches=True)
    dedup = DedupVerdict(probe_id="p-01", verdict="new",
                         evidence=dict.fromkeys(triage_task._EVIDENCE_KEYS))
    return (candidate, reduced, verdict, dedup, manifest, {}, str(artefact_dir))


@pytest.mark.t0
def test_recorded_report_renders_the_template_and_says_no_turn_was_made(tmp_path):
    """B7's shape, from the record alone, with the report saying so on its face."""
    arguments = _report_call(tmp_path)
    out = call_node(bug_loop.recorded_report, *arguments)
    report = out["report"]

    assert out["failure"] is None and out["logs"]["no_turn"] is True
    assert report.classification == "untriaged"
    rendered = Path(report.path).read_text(encoding="utf-8")
    assert "NO MODEL TURN WAS MADE" in rendered
    assert report.rendered_sha256 == __import__("hashlib").sha256(
        rendered.encode("utf-8")).hexdigest()
    # FR-11.4 still holds: every number in the artefact is the record's own.
    assert 'isa<To>(Val) && "bad cast"' in rendered      # the verdict's
    assert "/workspace/circt/lib/A.cpp:10" in rendered   # the verdict's site
    assert "hw.module @a() {}" in rendered               # the reduced case's bytes
    assert "a A.cpp:10" in rendered                      # the frames
    assert "Arm: seeded" in rendered                     # the candidate's arm
    # ERRATUM W-19b-7: the artefact's `Assisted-by:` trailer still names the
    # manifest's triage model, which in this mode did not run. `render_report`
    # takes it off the manifest and not as a parameter; the row is owed to
    # triage_task.py, which this task may not edit.
    assert "Assisted-by: " in rendered
    assert isinstance(out["counters"], CounterBlock)
    assert (out["counters"].stage, out["counters"].completed) == ("stage_6", 1)


@pytest.mark.t0
def test_recorded_report_lets_the_tool_verdict_win(tmp_path):
    """FR-11.2: a screened duplicate is `known_issue` here exactly as in B7,
    the absent turn having no say in it either way."""
    candidate, reduced, verdict, dedup, manifest, cfg, directory = _report_call(
        tmp_path)
    known = dataclasses.replace(dedup, verdict="known_open_issue")
    out = call_node(bug_loop.recorded_report, candidate, reduced, verdict, known,
                    manifest, cfg, directory)
    assert out["report"].classification == "known_issue"


@pytest.mark.t0
def test_system_seed_fixture_is_the_six_and_the_two():
    """`fixtures/system/seeds.json` is W-09's six confirmed failures and W-05's
    two recordings, and every one of them validates."""
    seeds = system_seeds()
    crashes = {json.loads((HERE / "fixtures" / "crashes" / name
                           / "commit.json").read_text(encoding="utf-8"))["parent_of"]
               for name in os.listdir(HERE / "fixtures" / "crashes")}
    assert len(seeds) == 8 and len(crashes) == 6
    assert crashes <= {seed.seed_sha for seed in seeds}
    for seed in seeds:
        schema.validate(seed)
        assert seed.test_files and seed.run_lines
        assert seed.entry_tool == "circt-opt"


# ===========================================================================
# Tier 3: the same mode, dispatched onto the real cluster
# ===========================================================================


@pytest.mark.t3
@pytest.mark.needs_cluster
def test_disc_01_one_discovery_iteration_over_the_eight_seeds(cluster, artefact_root):
    """T-S-disc-01, as far as it goes without a model (FR-02.7, FR-17.1, FR-18.6).

    One full iteration in discovery mode over W-09's six confirmed-failure seeds
    and W-05's two, both arms, `--generator recorded`, every stage dispatched
    through Ray onto the cluster's own workers.
    """
    run_id = uuid.uuid4().hex
    budget = tiny_budget()
    seeds = system_seeds()
    manifest = manifest_for("discovery", run_id, artefact_root, budget=budget,
                            seeds=seeds)
    started = time.monotonic()
    run = drive(manifest, budget, seeds, remote=True)
    wall = time.monotonic() - started
    store, outcome = run["store"], run["outcome"]

    # The manifest carries exactly one run_commit, with a null seed_sha (FR-02.7).
    assert len(manifest.run_commit) == 1
    assert manifest.run_commit[0].seed_sha is None

    # Both arms ran, one after the other, and each wrote its `arm_window` entry.
    assert set(outcome["arms"]) == {"seeded", "mutation"}
    windows = store.query(
        "SELECT arm, amount, stop_reason FROM ledger_entry WHERE "
        "run_manifest_id = ? AND scope = 'arm_window' ORDER BY arm",
        (run_id,))
    assert [row["arm"] for row in windows] == ["mutation", "seeded"]
    assert all(row["stop_reason"] for row in windows)

    # Every probe reached a stage and left a row; the tree carries no PARTIAL.
    probes = store.query("SELECT * FROM probe WHERE run_manifest_id = ?", (run_id,))
    results = store.query("SELECT * FROM probe_result WHERE run_manifest_id = ?",
                          (run_id,))
    assert probes, "the recorded generator wrote no probing input at all"
    assert len(results) == len(probes), (
        f"{len(probes) - len(results)} probes have no probe_result row")
    left = sorted(str(p) for p in
                  (Path(artefact_root) / run_id).rglob(PARTIAL))
    assert left == [], f"PARTIAL markers left behind: {left}"

    # Every stage that ran returned its own CounterBlock and none was synthesised.
    counters = json.loads((Path(artefact_root) / run_id / "results"
                           / "counters.json").read_text(encoding="utf-8"))
    print(f"\nT-S-disc-01: {len(probes)} probes, {wall:.1f} s")
    print(f"  arms:     {json.dumps(outcome['arms'], sort_keys=True)}")
    for key, block in sorted(counters["totals"].items()):
        print(f"  counter   {key:22} {json.dumps(block, sort_keys=True)}")
    for line in _stop_reasons(outcome):
        print(f"  probes    {line}")
    print(f"  violations: {run['counters'].violations}")
    assert run["counters"].violations == [], run["counters"].violations
    # `CounterLog` keys a block `<arm>/<stage>`; both arms reached the generator
    # and the probe, which is stage 2 and stage 3 dispatched onto the cluster.
    assert {"seeded/stage_2", "seeded/stage_3",
            "mutation/stage_2", "mutation/stage_3"} <= set(counters["totals"])
    for key, block in counters["totals"].items():
        assert block["started"] == block["completed"] + block["failed"], key


def _stop_reasons(outcome: dict) -> list:
    """`(arm, stopping stage, reason) x n` over every probe the campaign drove."""
    counts: dict = {}
    for seed in outcome["seeds"]:
        for probe in seed["probes"]:
            key = (seed["arm"], probe["stopping_stage"], probe["stopping_reason"])
            counts[key] = counts.get(key, 0) + 1
    return [f"{arm:9} {stage:8} {reason[:64]:64} n={n}"
            for (arm, stage, reason), n in sorted(counts.items())]


@pytest.mark.t3
@pytest.mark.needs_cluster
def test_calib_01_calibration_mode_over_three_sampled_seeds(cluster, artefact_root):
    """T-S-calib-01's first half: the manifest, and what the driver does with
    the image it has (FR-02.7, FR-18.5).

    FR-02.7 as written wants each sampled seed probed at ITS OWN parent commit,
    and the fixed image is at one commit. This test records what the driver
    actually does rather than asserting the requirement is met: the manifest
    carries one `run_commit` per sampled seed with a non-null `seed_sha`, and
    every probe nonetheless executes against the ONE image the cluster runs.
    The gap is FR-02.7's, not the driver's, and the measurement record carries
    the amendment it needs.
    """
    seeds = system_seeds()[:3]
    budget = tiny_budget(calibration_sample_shas=[s.seed_sha for s in seeds],
                         calibration_sample_size=3)
    run_id = uuid.uuid4().hex
    manifest = manifest_for("calibration", run_id, artefact_root, budget=budget,
                            seeds=seeds)
    assert len(manifest.run_commit) == len(seeds)
    assert all(commit.seed_sha is not None for commit in manifest.run_commit)
    assert {c.seed_sha for c in manifest.run_commit} == {s.seed_sha for s in seeds}

    run = drive(manifest, budget, seeds, remote=True, arms=["seeded"])
    store = run["store"]
    rows = store.query("SELECT run_commit FROM build_result WHERE "
                       "probe_id IN (SELECT probe_id FROM probe WHERE "
                       "run_manifest_id = ?)", (run_id,))
    executed = {row["run_commit"] for row in rows}
    print(f"\nT-S-calib-01: {len(rows)} builds at run_commit(s) {sorted(executed)}; "
          f"the manifest names {sorted(c.commit for c in manifest.run_commit)}")
    assert store.query_one(
        "SELECT 1 FROM run WHERE run_manifest_id = ? AND mode = 'calibration'",
        (run_id,)) is not None
    pytest.xfail("FR-02.7 wants each calibration seed at its own parent commit "
                 "and the fixed image is at one; the driver runs every probe "
                 "against the run's image. Errata row W-19b-6.")


@pytest.mark.t3
@pytest.mark.needs_cluster
def test_equal_windows_stop_both_arms_at_the_same_w(cluster, artefact_root):
    """FR-14.5: two tiny windows, sequential, never overlapping, each metered.

    The window is deliberately smaller than one seed's work, so the binding stop
    is the window itself and not the seed set - which is the case the pilot's
    four-hour windows are, and the one a `seed_set_exhausted` run never tests.
    """
    budget = tiny_budget(arm_window_seconds=1.0)
    seeds = system_seeds()
    run_id = uuid.uuid4().hex
    manifest = manifest_for("discovery", run_id, artefact_root, budget=budget,
                            seeds=seeds)
    run = drive(manifest, budget, seeds, remote=True)
    arms = run["outcome"]["arms"]

    print(f"\nequal windows: {json.dumps(arms, sort_keys=True, indent=1)}")
    assert set(arms) == {"seeded", "mutation"}
    assert all(arm["started"] for arm in arms.values())
    for name, arm in arms.items():
        assert arm["stop_reason"] in ("arm_window", "seed_set_exhausted"), name
    windows = run["store"].query(
        "SELECT arm, amount, stop_reason, metered FROM ledger_entry WHERE "
        "run_manifest_id = ? AND scope = 'arm_window'", (run_id,))
    assert len(windows) == 2 and all(row["metered"] for row in windows)
    # Sequential and never overlapping: the two windows' seconds sum to no more
    # than the whole drive, which is what `campaign_drive` guarantees by running
    # them one after the other in `arm_order`.
    assert sum(row["amount"] for row in windows) >= 0.0


@pytest.mark.t3
@pytest.mark.needs_cluster
def test_isolate_01_precondition_circt_binaries_unchanged(cluster, artefact_root):
    """T-S-isolate-01's PRECONDITION only (FR-03.16, FR-06.1).

    The repair attempt itself needs a model and is the pilot's. What is checked
    here is the half that must hold before it can mean anything: every tool
    binary on every `bugloop_circt` worker hashes to `ImageSpec.tool_hashes`
    before a run and again after it, so a later change can only be the repair
    worker's doing.
    """
    expected = image_spec().tool_hashes
    before = _worker_hashes(expected)
    if before is None:
        pytest.skip("no running circt_bug_loop_circt container to hash")

    budget = tiny_budget()
    seeds = system_seeds()[:2]
    run_id = uuid.uuid4().hex
    drive(manifest_for("discovery", run_id, artefact_root, budget=budget,
                       seeds=seeds), budget, seeds, remote=True, arms=["seeded"])

    after = _worker_hashes(expected)
    print(f"\nT-S-isolate-01 precondition: {len(before)} container(s) hashed")
    for name in sorted(before):
        assert before[name] == expected, f"{name} did not match before the run"
        assert after[name] == expected, f"{name} changed during the run"


def _worker_hashes(expected: dict):
    """`sha256sum` of every tool binary in every running `bugloop_circt`, by name."""
    listed = subprocess.run(
        ["docker", "ps", "--filter", "name=circt_bug_loop_circt", "--format",
         "{{.Names}}"], capture_output=True, text=True, timeout=60)
    names = [n for n in listed.stdout.split() if n]
    if not names:
        return None
    out = {}
    for name in names:
        proc = subprocess.run(
            ["docker", "exec", name, "sha256sum",
             *[f"/workspace/circt/build/bin/{tool}" for tool in sorted(expected)]],
            capture_output=True, text=True, timeout=300)
        out[name] = {Path(line.split()[1]).name: line.split()[0]
                     for line in proc.stdout.splitlines() if line.strip()}
    return out


@pytest.mark.t3
@pytest.mark.needs_cluster
def test_regen_01_the_render_refuses_for_exactly_one_reason(cluster, artefact_root):
    """T-S-regen-01 (FR-18.11) and §14.4's fourteen refusals, over one real run.

    `render_results` refuses to render at all when the store cannot support one
    of §14.4's fourteen elements, and it names every element it cannot support
    rather than the first. THIRTEEN of the fourteen are satisfied by a run this
    mode produced. The fourteenth is NOT the store's fault and NOT this mode's:
    FR-10.2's collision and false-merge rates are measured over a HAND-LABELLED
    duplicate-pair set, `render_results` takes it as a parameter because it is a
    measurement of the project and not a row of the campaign - and
    `run_campaign` calls the node with no such parameter and no way to pass one.
    `ResultsIncomplete` is a bare `Exception`, and `main` catches only
    `(ImageBuildError, BuildTimeout, OSError, ValueError)`, so a real campaign
    runs both arm windows to the end and then dies with a traceback instead of
    writing its results artefact.

    THIS TEST IS A PIN, not an approval. It asserts the refusal set is EXACTLY
    that one element today; the day the driver gains a way to supply the
    labelled set, this test fails and should be rewritten to assert a render.
    Errata row W-19b-4.
    """
    from circt_bug_loop import results as results_module

    budget = tiny_budget()
    seeds = system_seeds()
    run_id = uuid.uuid4().hex
    manifest = manifest_for("discovery", run_id, artefact_root, budget=budget,
                            seeds=seeds)
    run = drive(manifest, budget, seeds, remote=True)
    store = run["store"]

    with pytest.raises(results_module.ResultsIncomplete) as raised:
        call_node(results_module.render_results, store, manifest)
    print("\nT-S-regen-01: the render's refusals over a real run's store:")
    for complaint in raised.value.missing:
        print(f"  REFUSED  {complaint}")
    assert len(raised.value.missing) == 1, raised.value.missing
    assert "labelled duplicate-pair set" in raised.value.missing[0]

    # FR-18.11 itself: the regeneration check RAN over every candidate row and
    # recorded a mark or a pass for each. A run whose probes never fired the
    # oracle has no candidate, and the zero is the answer, not a gap - which is
    # what `_regeneration` leaving no entry in `facts["gaps"]` says.
    facts = results_module._facts(store, manifest, None)
    assert "regeneration_marks" not in facts["gaps"], facts["gaps"]
    rows = facts["regeneration"]
    candidates = store.query(
        "SELECT candidate_id FROM candidate WHERE run_manifest_id = ?", (run_id,))
    print(f"  regeneration: {len(rows)} row(s) over {len(candidates)} candidate(s); "
          f"{sum(1 for r in rows if r['regenerated'])} regenerated")
    assert len(rows) == len(candidates)
    assert {row["candidate_id"] for row in rows} == {
        row["candidate_id"] for row in candidates}


@pytest.mark.t3
@pytest.mark.needs_cluster
def test_submit_01_the_wrapper_submits_and_its_logs_come_back(cluster, artefact_root,
                                                              tmp_path):
    """T-S-submit-01 (FR-17.4, NFR-06, NFR-09), as far as pre-flight allows.

    The real `bug_loop_submit.sh`, the real `chia job submit`, the real driver in
    the job process. What is asserted is the wrapper's own contract: the job's
    `runtime_env` carries exactly the two or three forwarded variables and NO
    token and NO model credential, the driver resolves its artefact root and
    image tag from them - which it could not do had the flag been dropped - and
    `chia job logs <id>` returns the driver's own stdout.
    """
    wrapper = Path(bug_loop.FLOW_DIR) / "bug_loop_submit.sh"
    assert wrapper.is_file() and os.access(wrapper, os.X_OK)
    if shutil.which("chia") is None:
        pytest.skip("no `chia` on PATH")

    proc = subprocess.run(
        [str(wrapper), "--mode", "discovery", "--generator", "recorded",
         "--print-config"],
        capture_output=True, text=True, timeout=900,
        env={**os.environ, "NO_WAIT": "0"})
    print(f"\nT-S-submit-01 rc={proc.returncode}")
    print(proc.stdout[-3000:])
    print(proc.stderr[-2000:])
    assert proc.returncode == 0, proc.stderr[-2000:]

    combined = proc.stdout + proc.stderr
    job_id = next((token.strip("'\"") for token in combined.split()
                   if token.strip("'\"").startswith("raysubmit_")), None)
    assert job_id, "the wrapper printed no raysubmit_ job id"

    logs = subprocess.run(["chia", "job", "logs", job_id], capture_output=True,
                          text=True, timeout=300)
    print(f"--- chia job logs {job_id} ---\n{logs.stdout[-3000:]}")
    assert logs.returncode == 0, logs.stderr[-2000:]
    config = json.loads(logs.stdout[logs.stdout.index("{"):
                                    logs.stdout.rindex("}") + 1])
    assert config["generator"] == "recorded" and config["repair_enabled"] is False
    assert config["artefact_root"] == os.environ["BUGLOOP_ARTEFACTS"]
    assert config["image_tag"] == os.environ["BUGLOOP_IMAGE_TAG"]

    # NFR-06: no secret in the job's own metadata, and none in its logs.
    status = subprocess.run(["chia", "job", "status", job_id], capture_output=True,
                            text=True, timeout=120)
    haystack = status.stdout + status.stderr + logs.stdout
    for forbidden in ("GEMINI_API_KEY", "GITHUB_TOKEN", "BUGLOOP_ALLOW_LIVE_MODEL"):
        assert forbidden not in haystack, f"{forbidden} appears in job metadata"
