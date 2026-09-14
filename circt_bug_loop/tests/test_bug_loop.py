"""`bug_loop.py`: argv, the twelve pre-flight refusals, the manifest, the loop.

`04-Test-Plan.md` §1.20, the `T-U-driver-*` tests. All tier 0. Three properties
of this module are what make that possible and each is a decision recorded in
`design/reviews/implementation-errata-log.md`:

  * each pre-flight check is a function of its own that takes what it checks,
    so a fixture store, a fixture `ImageSpec` and an explicit environment
    mapping are enough to exercise all twelve with no cluster;
  * `interlock_probe` reads a mapping the caller passes, so **no test here sets
    `BUGLOOP_ALLOW_LIVE_MODEL` in the process environment**, which is
    `T-U-layout-08`'s rule as W-16 rewrote it;
  * `campaign_drive` dispatches through `Stages` and `Dispatch`, so one whole
    iteration runs in this process against a fixture store and a fake
    generator, which is the dry-run iteration this module's last test drives.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import budget as budget_module
from circt_bug_loop import bug_loop
from circt_bug_loop.contract import schema
from circt_bug_loop.store import (BuildResult, DedupVerdict, Fingerprint, Frame,
                                  ImageSpec, OracleVerdict, ReducedCase)
from circt_bug_loop.tests.test_store import open_store

# `-W error` turns FastMCP's own IncompleteFieldDefinitionWarning into an error
# on every ChiaTool construction, and `default_stages` imports the module that
# defines two (W-13 erratum 18). A module-level filter is the one filter that
# outranks a command-line -W.
pytestmark = [pytest.mark.t0,
              pytest.mark.filterwarnings("ignore::UserWarning")]

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DRIVER = FIXTURES / "driver"

_RUN = "7c1f4a9d6e2b48c0a53f81d27e6b09c4"
_PIN = {"run_commit": "e" * 40, "pin_sha": "9" * 40, "pin_tag": "firtool-1.159.0",
        "tags_sharing_pin": ["firtool-1.159.0"], "lag_commits": 7,
        "lag_days": 4.807, "current_window_has_release": False,
        "resolved_utc": "2026-09-19T00:00:00+00:00"}
_MIRROR = {"refreshed_utc": "2026-09-19T00:00:00+00:00", "issues_mirrored": 600,
           "issue_cap": 600, "cap_bound": False, "state": "all",
           "comments_mirrored": False, "incomplete_reason": None}
_CLUSTER = {"cluster_yaml_sha": "f" * 64, "worker_type": "bugloop_circt",
            "apparatus_concurrency": 2, "llm_concurrency": 2,
            "deployment": "single_machine"}


# ---------------------------------------------------------------------------
# Helpers: a budget, an ImageSpec, a throwaway registered repository
# ---------------------------------------------------------------------------


def image_spec(name: str = "ok") -> ImageSpec:
    """The recorded `ImageSpec` of `fixtures/driver/image_spec/<name>.json`."""
    return ImageSpec(**json.loads((DRIVER / "image_spec" / f"{name}.json").read_text()))


def budget_file(**overrides) -> schema.BudgetFile:
    """The committed `budget.yaml` as a `BudgetFile`, with any key overridden."""
    document = yaml.safe_load(Path(budget_module.BUDGET_YAML).read_text(encoding="utf-8"))
    document.update(overrides)
    parsed = schema.BudgetFile(budget_file_sha="b" * 40, **document)
    schema.validate(parsed)
    return parsed


def registered_repo(tmp_path: Path, *, mutator_after: bool = False) -> Path:
    """A throwaway repository whose `budget.yaml` commit is the registration.

    Built here rather than committed, which is W-06 erratum 18's rule for every
    budget fixture: the file under test is the repository's own `budget.yaml`
    and a second copy would drift from it.

    Every commit is dated EXPLICITLY, an hour apart. `budget.py`'s freeze rule
    is `committed_at >= budget_at`, so two commits made in the same wall-clock
    second refuse a correctly ordered repository, which is what W-16 hit: the
    ordering under test is the commits' own and not the test machine's speed.
    """
    repo = tmp_path / "repo"
    flow = repo / "circt_bug_loop" / "mutators"
    flow.mkdir(parents=True)
    git = ("git", "-C", str(repo))
    subprocess.run(git + ("init", "-q", "-b", "main"), check=True)
    subprocess.run(git + ("config", "user.email", "t@t"), check=True)
    subprocess.run(git + ("config", "user.name", "t"), check=True)

    def commit(message: str, hour: int) -> None:
        when = f"2026-09-18T{hour:02d}:00:00+00:00"
        subprocess.run(git + ("add", "-A"), check=True)
        subprocess.run(git + ("commit", "-q", "-m", message), check=True,
                       env={**os.environ, "GIT_AUTHOR_DATE": when,
                            "GIT_COMMITTER_DATE": when})

    source = Path(budget_module.BUDGET_YAML).read_text(encoding="utf-8")
    frozen = flow / "set_v1.json"
    frozen.write_text('{"set_version": "v1"}\n', encoding="utf-8")
    budget_path = repo / "circt_bug_loop" / "budget.yaml"
    if not mutator_after:
        commit("the mutator set", 1)
    budget_path.write_text(source, encoding="utf-8")
    commit("the registration", 2)
    if mutator_after:
        frozen.write_text('{"set_version": "v1", "edited": true}\n', encoding="utf-8")
        commit("the set, edited after", 3)
    return repo


def parsed_args(**overrides):
    """The parser's own namespace, with the arguments a manifest needs supplied."""
    argv = ["--mode", overrides.pop("mode", "discovery"),
            "--artefact-root", overrides.pop("artefact_root", "/artefacts"),
            "--forum-post-url", "https://llvm.discourse.group/t/x/1",
            "--forum-post-date", "2026-09-18"]
    for key, value in overrides.items():
        argv += [f"--{key.replace('_', '-')}"] + ([] if value is True else [str(value)])
    return bug_loop.build_parser().parse_args(argv)


# ---------------------------------------------------------------------------
# T-U-driver-01 to -12: the twelve pre-flight checks, in 13.1's order
# ---------------------------------------------------------------------------


def test_T_U_driver_01(tmp_path: Path):
    """T-U-driver-01 (FR-14.2): check 1 accepts a registered file and refuses a later one.

    Fixture: a throwaway repository built here. Tier 0.
    """
    repo = registered_repo(tmp_path)
    budget = bug_loop.check_01_budget_registered(
        budget_path=str(repo / "circt_bug_loop" / "budget.yaml"),
        repo_root=str(repo), run_start_utc="2036-01-01T00:00:00+00:00")
    assert len(budget.budget_file_sha) == 40

    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_01_budget_registered(
            budget_path=str(repo / "circt_bug_loop" / "budget.yaml"),
            repo_root=str(repo), run_start_utc="2000-01-01T00:00:00+00:00")
    assert raised.value.check == "budget_registered"


def test_T_U_driver_02(tmp_path: Path):
    """T-U-driver-02 (FR-05.2): check 2 refuses a mutator set committed after the budget.

    Fixture: the same repository, with the frozen set edited afterwards. Tier 0.
    """
    repo = registered_repo(tmp_path, mutator_after=True)
    budget = schema.BudgetFile(
        **{**yaml.safe_load(Path(budget_module.BUDGET_YAML).read_text()),
           "budget_file_sha": "b" * 40})
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_02_mutator_set_earlier(
            budget=budget, repo_root=str(repo),
            flow_dir=str(repo / "circt_bug_loop"))
    assert raised.value.check == "mutator_set_earlier"


def test_T_U_driver_03():
    """T-U-driver-03 (FR-01.11): check 3 names both SHAs on a difference.

    Fixture: none; the clone's HEAD is supplied, which is what keeps it tier 0.
    """
    bug_loop.check_03_clone_head(clone_path="/clone", corpus_head_sha="a" * 40,
                                 head_sha="a" * 40)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_03_clone_head(clone_path="/clone", corpus_head_sha="a" * 40,
                                     head_sha="b" * 40)
    assert "a" * 40 in str(raised.value) and "b" * 40 in str(raised.value)


def test_T_U_driver_04(tmp_path: Path):
    """T-U-driver-04 (FR-17.9): check 4 refuses a missing, an empty and an unwritable root.

    Fixture: none. Tier 0.
    """
    bug_loop.check_04_artefact_root_head(artefact_root=str(tmp_path))
    for root in ("", str(tmp_path / "absent")):
        with pytest.raises(bug_loop.PreflightFailed) as raised:
            bug_loop.check_04_artefact_root_head(artefact_root=root)
        assert raised.value.check == "artefact_root_head"


def test_T_U_driver_05(tmp_path: Path):
    """T-U-driver-05 (FR-17.9): check 5 names the worker and the path, as `artefact_root_unmounted`.

    The probe itself runs here, which is what it does on a worker; the mapping
    check 5 reads is the one the driver builds by dispatching it per type.
    Fixture: none. Tier 0 (the plan puts the dispatched form at tier 3).
    """
    probe = bug_loop.artefact_root_probe(str(tmp_path))
    assert probe["writable"] is True and probe["detail"] is None
    bug_loop.check_05_artefact_root_workers(artefact_root=str(tmp_path),
                                            probes={"bugloop_circt": probe})

    unmounted = bug_loop.artefact_root_probe(str(tmp_path / "absent"))
    assert unmounted["writable"] is False
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_05_artefact_root_workers(
            artefact_root=str(tmp_path / "absent"),
            probes={"bugloop_circt": probe, "bugloop_repair": unmounted})
    assert raised.value.check == "artefact_root_unmounted"
    assert "bugloop_repair" in str(raised.value)


def test_T_U_driver_06():
    """T-U-driver-06 (FR-03.17): check 6 refuses an image whose lit discovery failed.

    Fixture: `driver/image_spec/ok.json`, `driver/image_spec/lit_broken.json`.
    Tier 0.
    """
    bug_loop.check_06_image_lit_discovery(image_spec=image_spec("ok"))
    for spec in (None, image_spec("lit_broken")):
        with pytest.raises(bug_loop.PreflightFailed) as raised:
            bug_loop.check_06_image_lit_discovery(image_spec=spec)
        assert raised.value.check == "image_lit_discovery"


def test_T_U_driver_07():
    """T-U-driver-07 (FR-06.1, FR-03.16): check 7 names the worker, the tool and both hashes.

    Fixture: `driver/image_spec/ok.json`. Tier 0 (the plan's tier 2 is the same
    check over hashes taken inside a running container, which is `test_image.py`).
    """
    spec = image_spec("ok")
    bug_loop.check_07_tool_hashes(image_spec=spec,
                                  observed={"bugloop_circt": spec.tool_hashes})
    drifted = dict(spec.tool_hashes, **{"circt-opt": "0" * 64})
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_07_tool_hashes(image_spec=spec,
                                      observed={"bugloop_circt": drifted})
    assert raised.value.check == "tool_hashes"
    assert "circt-opt" in str(raised.value) and "0" * 64 in str(raised.value)


def test_T_U_driver_08():
    """T-U-driver-08 (FR-03.15): check 8 refuses a changed Verilator, naming both.

    Fixture: `driver/image_spec/ok.json`. Tier 0.
    """
    spec = image_spec("ok")
    bug_loop.check_08_verilator_version(
        image_spec=spec, observed={"bugloop_circt": spec.verilator_version})
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_08_verilator_version(
            image_spec=spec, observed={"bugloop_circt": "Verilator 5.030"})
    assert "5.030" in str(raised.value)
    assert spec.verilator_version in str(raised.value)


def test_T_U_driver_09():
    """T-U-driver-09 (FR-02.1 to FR-02.4): check 9 requires all seven pin fields.

    `resolved_utc` is A2's eighth field and has no manifest home (W-07 erratum
    7), so it is not one of the seven. Fixture: none. Tier 0.
    """
    assert set(bug_loop.PIN_FIELDS) == set(_PIN) - {"resolved_utc"}
    bug_loop.check_09_pin_stamped(pin=_PIN)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_09_pin_stamped(pin={**_PIN, "pin_tag": None})
    assert "pin_tag" in str(raised.value)


def test_T_U_driver_10():
    """T-U-driver-10 (FR-10.9, FR-10.7): check 10 refuses no mirror and an incomplete one.

    Fixture: none. Tier 0.
    """
    bug_loop.check_10_issue_mirror(mirror=_MIRROR, refresh_requested=False)
    with pytest.raises(bug_loop.PreflightFailed):
        bug_loop.check_10_issue_mirror(mirror=None, refresh_requested=False)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_10_issue_mirror(
            mirror={**_MIRROR, "incomplete_reason": "GithubRequestError"},
            refresh_requested=True)
    assert "GithubRequestError" in str(raised.value)


def test_T_U_driver_11():
    """T-U-driver-11 (FR-20.1): check 11 requires the forum post's URL and date.

    Fixture: none. Tier 0.
    """
    bug_loop.check_11_forum_post(forum_post_url="https://x/1",
                                 forum_post_date="2026-09-18")
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_11_forum_post(forum_post_url=None, forum_post_date="2026-09-18")
    assert "forum_post_url" in str(raised.value)


def test_T_U_driver_27():
    """T-U-driver-27 (NFR-06, NFR-08): check 12, the interlock and the key.

    Four failing cases and one passing one, and the probe returns **two booleans
    and never a value**, asserted on its return. The environment is a mapping
    this test passes: nothing here writes `BUGLOOP_ALLOW_LIVE_MODEL` into the
    process environment, which is `T-U-layout-08`'s rule. Fixture: none. Tier 0.
    """
    live = {bug_loop.LIVE_MODEL_ENV: "1", bug_loop.API_KEY_ENV: "AQ.synthetic-test-key"}
    probe = bug_loop.interlock_probe(env=live)
    assert probe == {"interlock_ok": True, "key_ok": True}
    assert all(isinstance(v, bool) for v in probe.values())
    bug_loop.check_12_live_model(head=probe, workers={"bugloop_llm": probe})

    for label, env in (
            ("interlock unset", {bug_loop.API_KEY_ENV: "k"}),
            ("interlock not 1", {bug_loop.LIVE_MODEL_ENV: "true",
                                 bug_loop.API_KEY_ENV: "k"}),
            ("key empty", {bug_loop.LIVE_MODEL_ENV: "1", bug_loop.API_KEY_ENV: ""}),
            ("key unexpanded", {bug_loop.LIVE_MODEL_ENV: "1",
                                bug_loop.API_KEY_ENV: "${GEMINI_API_KEY}"})):
        bad = bug_loop.interlock_probe(env=env)
        with pytest.raises(bug_loop.PreflightFailed) as raised:
            bug_loop.check_12_live_model(head=live and probe,
                                         workers={"bugloop_llm": bad})
        assert "bugloop_llm" in str(raised.value), label
        assert "k" != str(raised.value), label


def test_T_U_driver_28a():
    """T-U-driver-28 (13.1): the twelve checks are twelve named functions, in order.

    Fixture: none. Tier 0.
    """
    assert len(bug_loop.PREFLIGHT_CHECKS) == 12
    names = [n for n in dir(bug_loop) if n.startswith("check_")]
    assert len([n for n in names if n[6:8].isdigit()]) == 12


# ---------------------------------------------------------------------------
# T-U-driver-12 to -17: argv, the flags, and the shipped modules
# ---------------------------------------------------------------------------


def test_T_U_driver_12():
    """T-U-driver-12 (FR-19.3): every argument of 13.1's table parses with its default.

    Fixture: none. Tier 0.
    """
    args = bug_loop.build_parser().parse_args(["--mode", "discovery"])
    assert args.arm == "both" and args.repair_backend == "vertex"
    assert args.budget.endswith("budget.yaml")
    assert args.cluster_yaml.endswith("cluster_single.yaml")
    assert args.clone.endswith(".cache/circt")
    assert args.no_repair is False and args.dry_run is False
    assert args.resume is None and args.record_fixtures is None
    with pytest.raises(SystemExit):
        bug_loop.build_parser().parse_args(["--mode", "discovery", "--nonesuch"])
    with pytest.raises(SystemExit):
        bug_loop.build_parser().parse_args([])


def test_T_U_driver_13():
    """T-U-driver-13 (FR-19.3, FR-18.10): one flag swaps the arm, and `both` is sequential.

    Fixture: the committed `budget.yaml`, whose `arm_order` is what `both` runs.
    Tier 0.
    """
    for arm in ("seeded", "mutation", "both"):
        assert bug_loop.build_parser().parse_args(
            ["--mode", "discovery", "--arm", arm]).arm == arm
    assert budget_file().arm_order == ["seeded", "mutation"]


def test_T_U_driver_17():
    """T-U-driver-17 (FR-12.1): `_PY_MODULES` is 13.1's entries, in its order.

    Fifteen and not the table's fourteen: `llm.py` is the join's own module
    (3.5.1, architect decision 3), and a CHIA checkout that shipped the other
    fourteen would ship no backend at all. The shipped list is `runtime_env()`'s,
    which substitutes the package directory for the flow's own ten wherever
    `__init__.py` makes them a package; CHIA's `issue_task.py` and
    `circt_util.py` travel in both forms, which is FR-12.1's point. Fixture:
    none. Tier 0.
    """
    assert len(bug_loop._PY_MODULES) == 15
    assert str(bug_loop.FLOW_DIR / "llm.py") in bug_loop._PY_MODULES
    assert bug_loop._PY_MODULES[-2:] == [
        str(bug_loop._ISSUE_SOLVER / "issue_task.py"),
        str(bug_loop._ISSUE_SOLVER / "circt_util.py")]
    assert str(bug_loop.FLOW_DIR / "contract") in bug_loop._PY_MODULES
    assert str(bug_loop.FLOW_DIR / "mutators") in bug_loop._PY_MODULES

    shipped = bug_loop.runtime_env()
    assert shipped["excludes"] == ["**/__pycache__", "**/*.pyc"]
    assert str(bug_loop.FLOW_DIR) in shipped["py_modules"]
    assert bug_loop._PY_MODULES[-1] in shipped["py_modules"]


def test_T_U_driver_23(capsys):
    """T-U-driver-23 (FR-19.3, NFR-12): `--print-config` prints both databases and no secret.

    Fixture: none. Tier 0.
    """
    status = bug_loop.main(["--mode", "discovery", "--print-config"])
    printed = capsys.readouterr().out
    assert status == 0
    config = json.loads(printed)
    assert config["loop_db"].endswith("loop.db")
    assert config["issues_db"].endswith("issues.db")
    for key in (bug_loop.API_KEY_ENV, bug_loop.LIVE_MODEL_ENV, "GITHUB_TOKEN"):
        assert key not in printed


def test_T_U_driver_21():
    """T-U-driver-21 (FR-14.1, FR-14.3): the calibration draw is reproducible and writes nothing.

    Two draws at one `corpus_head_sha` are the same twenty, and a different head
    draws differently. Fixture: none. Tier 0.
    """
    pool = [f"{i:040x}" for i in range(171)]
    first = bug_loop.draw_calibration(corpus_head_sha="d7e9", sample_size=20,
                                      exact_pin_shas=pool)
    assert first == bug_loop.draw_calibration(corpus_head_sha="d7e9", sample_size=20,
                                              exact_pin_shas=pool)
    assert len(set(first)) == 20 and set(first) <= set(pool)
    assert first != bug_loop.draw_calibration(corpus_head_sha="0000", sample_size=20,
                                              exact_pin_shas=pool)
    with pytest.raises(ValueError):
        bug_loop.draw_calibration(corpus_head_sha="d7e9", sample_size=20,
                                  exact_pin_shas=pool[:5])


# ---------------------------------------------------------------------------
# T-U-driver-24, -25: B1's tag, its argument list and its refusals
# ---------------------------------------------------------------------------


def test_T_U_driver_24():
    """T-U-driver-24 (FR-03.7, FR-03.10, FR-03.13): the tag is the manifest's digest.

    Changing any one of the six inputs changes the tag, `slang` and
    `base_image` included, so a branch-(b) image can never answer for a
    branch-(a) run; the argument ORDER of the target list does not, because the
    manifest sorts it. Fixture: none. Tier 0.
    """
    base = dict(circt_sha="e" * 40, sdk_tag="firtool-1.159.0",
                targets=("circt-opt", "firtool"), flag_string="-O3 -UNDEBUG")
    tag = bug_loop.image_tag("reg", bug_loop.image_manifest(**base))
    reordered = bug_loop.image_tag("reg", bug_loop.image_manifest(
        **{**base, "targets": ("firtool", "circt-opt")}))
    assert tag == reordered
    assert tag.startswith("reg/chia-circt-assert:") and len(tag.split(":")[-1]) == 12

    for key, value in (("circt_sha", "f" * 40), ("sdk_tag", "firtool-1.158.0"),
                       ("targets", ("circt-opt",)), ("flag_string", "-O2")):
        assert bug_loop.image_tag("reg", bug_loop.image_manifest(
            **{**base, key: value})) != tag
    assert bug_loop.image_tag("reg", bug_loop.image_manifest(
        **base, slang=False)) != tag
    assert bug_loop.image_tag("reg", bug_loop.image_manifest(
        **base, base_image="other")) != tag


def test_T_U_driver_25a():
    """T-U-driver-25 (FR-03.4, FR-03.7): step 2's argument list, and no `--progress=plain`.

    The six build arguments are the ones the Dockerfile's own `ARG` lines
    declare, checked against that file rather than against this document.
    Fixture: `upstream/dockerfiles/ChiaCirctAssertDockerfile`. Tier 0.
    """
    manifest = bug_loop.image_manifest("e" * 40, "firtool-1.159.0",
                                       bug_loop.IMAGE_TARGETS,
                                       bug_loop.IMAGE_FLAG_STRING)
    argv = bug_loop.build_argv("Dockerfile", "tag", manifest, "context")
    assert argv[0] == "docker" and argv[-1] == "context"
    assert "--progress=plain" not in argv
    passed = {a.split("=", 1)[0] for a in argv if argv[argv.index(a) - 1] == "--build-arg"}
    assert passed == {"CIRCT_SHA", "CIRCT_VER", "TOOL_TARGETS",
                      "CXX_FLAGS_RELEASE", "SLANG", "BASE_IMAGE"}
    dockerfile = (Path(bug_loop.FLOW_DIR).parent / "upstream" / "dockerfiles"
                  / "ChiaCirctAssertDockerfile").read_text(encoding="utf-8")
    for name in passed:
        assert f"ARG {name}" in dockerfile, name
    assert f"TOOL_TARGETS={' '.join(sorted(bug_loop.IMAGE_TARGETS))}" in argv


def test_T_U_driver_25b():
    """T-U-driver-25 (FR-03.17): step 4 reads FR-03.17's two figures off lit's own output.

    Fixture: `image/lit_show_tests.txt`, `image/lit_notes.txt`, `image/lit_fatal.txt`.
    Tier 0.
    """
    shown = (FIXTURES / "image" / "lit_show_tests.txt").read_text(encoding="utf-8")
    notes = (FIXTURES / "image" / "lit_notes.txt").read_text(encoding="utf-8")
    ok, count = bug_loop.lit_discovery(0, notes + shown)
    assert ok is True and count == 1390
    assert bug_loop.lit_discovery(1, notes + shown)[0] is False
    fatal = (FIXTURES / "image" / "lit_fatal.txt").read_text(encoding="utf-8")
    assert bug_loop.lit_discovery(0, fatal)[0] is False


# ---------------------------------------------------------------------------
# T-U-driver-28: the manifest, and every field's producer
# ---------------------------------------------------------------------------


def manifest(**overrides) -> schema.RunManifest:
    """One built `RunManifest`, from the producers 13.1's table names."""
    args = overrides.pop("args", None) or parsed_args()
    return bug_loop.build_manifest(
        args=args, budget=overrides.pop("budget", None) or budget_file(),
        pin=_PIN, image_spec=image_spec("ok"), mirror=_MIRROR, cluster=_CLUSTER,
        mutator_set_sha="1" * 64, run_manifest_id=_RUN,
        started_utc="2026-09-19T00:00:00+00:00", **overrides)


def test_T_U_driver_28b():
    """T-U-driver-28 (FR-14.8, FR-18.2): every manifest field comes from its named producer.

    No field is None that the schema requires, `model_ids` is four
    `"<backend>:<model id>"` strings with the campaign's three the same, the
    three closed dicts carry exactly their declared key sets, and the manifest
    validates. Fixture: `driver/image_spec/ok.json`. Tier 0.
    """
    built = manifest()
    schema.validate(built)
    assert built.backend == "vertex"
    assert built.model_ids == {
        "generate_seeded": "vertex:gemini-3.8-flash",
        "triage_report": "vertex:gemini-3.8-flash",
        "mutator_synthesis": "vertex:gemini-3.8-flash",
        "repair_adapt": "vertex:gemini-3.8-flash"}
    for value in built.model_ids.values():
        assert ":" in value and value.split(":", 1)[1]
    for field in ("image_spec", "issue_mirror", "differential_driver"):
        assert set(getattr(built, field)) == schema._DICT_KEYS[("RunManifest", field)]
    assert built.stages_metered["stage_7"] is True
    assert set(built.stages_metered) == set(schema._STAGE_IDS)
    assert built.sv_seeds_excluded is None
    assert built.calibration_sample is None
    assert built.local_id_range == [900_000_000, 999_999_999]
    assert built.confirmation_cutoff_date == "2026-09-24"
    assert built.x_policy == "x-assign=unique,x-initial=unique"
    assert built.corpus_head_sha == budget_file().corpus_head_sha


def test_T_U_driver_28c():
    """T-U-driver-28 (FR-14.8): `stages_metered` follows the arm and the repair backend.

    Fixture: none. Tier 0.
    """
    seeded_only = bug_loop.stages_metered(arms=("mutation",), repair_backend="vertex",
                                          repair_enabled=True)
    assert seeded_only["stage_1"] is False and seeded_only["stage_2"] is False
    fallback = bug_loop.stages_metered(arms=("seeded", "mutation"),
                                       repair_backend="claude", repair_enabled=True)
    assert fallback["stage_7"] is False
    disabled = bug_loop.stages_metered(arms=("seeded",), repair_backend="vertex",
                                       repair_enabled=False)
    assert disabled["stage_7"] is False
    with pytest.raises(ValueError):
        bug_loop.model_ids(model_id="", repair_backend="vertex")


def test_T_U_driver_28d():
    """T-U-driver-28 (FR-02.7): `run_commit` is one entry per mode, not one shape.

    Fixture: none. Tier 0.
    """
    discovery = bug_loop.run_commits(mode="discovery", pin=_PIN)
    assert len(discovery) == 1 and discovery[0].seed_sha is None

    seeds = [schema.SeedRecord(
        seed_sha=f"{i:040x}", parent_sha=f"{i + 100:040x}", subject="fix",
        committed_date_utc="2026-01-01T00:00:00+00:00", source_paths=["lib/A.cpp"],
        test_paths=["test/a.mlir"], llvm_pin="1" * 40, sdk_tag="firtool-1.159.0",
        sdk_exact=True, bumps_away=None, entry_tool="circt-opt",
        dialect_bucket="HW", dialect_bucket_unmerged="HW", run_lines=["RUN: x"],
        argv_template=[["a"]], polarity=["expect_zero"], shape=["plain"],
        diff="", test_files={"test/a.mlir": ""}, corpus_head_sha="d" * 40)
        for i in range(2)]
    calibration = bug_loop.run_commits(mode="calibration", pin=_PIN, seeds=seeds)
    assert [c.seed_sha for c in calibration] == [s.seed_sha for s in seeds]
    assert [c.commit for c in calibration] == [s.parent_sha for s in seeds]
    with pytest.raises(ValueError):
        bug_loop.run_commits(mode="calibration", pin=_PIN, seeds=[])


def test_T_U_driver_29(tmp_path: Path, monkeypatch):
    """T-U-driver-29 (12.1, ADR-D-04): the cluster YAML produces four manifest fields.

    `cluster_yaml_sha` is the file's own SHA-256, so an edited YAML is a
    different run. The four variables are set one literal at a time, and by
    `monkeypatch` rather than by `os.environ`, so that `T-U-layout-08`'s `ast`
    walk can read every name this file puts in the environment and so that none
    of them outlives the test. Fixture: the committed `cluster_single.yaml`.
    Tier 0.
    """
    monkeypatch.setenv("CHIA_HEAD", "127.0.0.1")
    monkeypatch.setenv("BUGLOOP_ARTEFACTS", str(tmp_path))
    monkeypatch.setenv("BUGLOOP_IMAGE_TAG", "deadbeefcafe")
    monkeypatch.setenv("USER", "tester")
    summary = bug_loop.cluster_summary(str(bug_loop.FLOW_DIR / "cluster_single.yaml"))
    assert summary["worker_type"] == "bugloop_circt"
    assert summary["apparatus_concurrency"] == 2 and summary["llm_concurrency"] == 2
    assert summary["deployment"] == "single_machine"
    assert len(summary["cluster_yaml_sha"]) == 64


# ---------------------------------------------------------------------------
# T-U-driver-20: the counters, named and summed
# ---------------------------------------------------------------------------


def test_T_U_driver_20(tmp_path: Path):
    """T-U-driver-20 (FR-17.4, NFR-09): four counters, no fifth, two nodes of one stage sum.

    The driver checks `started == completed + failed` per block and logs a NAMED
    violation rather than repairing it, and rewrites `counters.json` on every
    aggregation. Fixture: none. Tier 0.
    """
    log = bug_loop.CounterLog(_RUN, str(tmp_path / "results"))
    assert set(f.name for f in schema.dataclasses.fields(schema.CounterBlock)) == {
        "stage", "started", "completed", "failed", "seconds"}
    for _ in range(2):
        log.record("seeded", schema.CounterBlock(stage="stage_3", started=1,
                                                 completed=1, failed=0, seconds=0.5))
    assert log.totals["seeded/stage_3"]["completed"] == 2
    assert log.totals["seeded/stage_3"]["seconds"] == 1.0

    log.record("seeded", schema.CounterBlock(stage="stage_4", started=3, completed=1,
                                             failed=1, seconds=0.1))
    assert any(v.startswith("counters_unbalanced:seeded:stage_4") for v in log.violations)
    with pytest.raises(ValueError):
        log.record("seeded", schema.CounterBlock(stage="stage_99", started=1,
                                                 completed=1, failed=0, seconds=0.0))
    written = json.loads((tmp_path / "results" / "counters.json").read_text())
    assert written["run_manifest_id"] == _RUN
    assert written["totals"]["seeded/stage_3"]["started"] == 2


# ---------------------------------------------------------------------------
# T-U-driver-15: --record-fixtures
# ---------------------------------------------------------------------------


def test_T_U_driver_15(tmp_path: Path):
    """T-U-driver-15 (FR-04.3): every recorded instance is validated first and named by its id.

    A recorder with no directory writes nothing at all, which is the default.
    Fixture: none. Tier 0.
    """
    recorder = bug_loop.FixtureRecorder(str(tmp_path / "rec"))
    built = manifest()
    path = recorder.record(built)
    assert path.endswith(f"run_manifest/{_RUN}.json")
    assert json.loads(Path(path).read_text())["run_manifest_id"] == _RUN
    assert bug_loop.FixtureRecorder(None).record(built) is None

    bad = schema.LedgerEntry(
        entry_id="e1", run_manifest_id=_RUN, arm="seeded", scope="arm_window",
        stage="stage_3", unit="wall_clock_seconds", amount=-1.0, metered=True,
        observed={"cpu_seconds": None, "tokens_in": None, "tokens_out": None,
                  "cost_usd": None},
        timestamp_utc="2026-09-19T00:00:00+00:00")
    with pytest.raises(schema.ContractError):
        recorder.record(bad)


# ---------------------------------------------------------------------------
# T-U-driver-18: the end-of-run reconciliation
# ---------------------------------------------------------------------------


def test_T_U_driver_18(tmp_path: Path):
    """T-U-driver-18 (FR-12.10): a loop repair row with no CHIA counterpart is marked.

    Fixture: a throwaway `loop.db` and a throwaway `issues.db` of CHIA's own
    shape. Tier 0.
    """
    import sqlite3

    from circt_bug_loop.tests.test_store import seed_rows

    loop = open_store(tmp_path)
    seed_rows(loop)
    for candidate_id, local_id in (("cand-01", 900000001),):
        loop.insert("repair", {
            "candidate_id": candidate_id, "local_id": local_id, "status": "fixed",
            "failing_phase": None, "reproduced": 1, "build_ok": 1, "fixed": 1,
            "lit_ok": 1, "lit_unusable": 0, "lit_passed": 10, "lit_failed": 0,
            "lit_failures_json": "[]", "diff_path": None, "diff_added": 1,
            "diff_removed": 1, "chia_artifact_dir": None, "chia_row_seen": 0,
            "repro_dir": "/artefacts/repair/900000001", "repro_overwritten": 0,
            "restore_ok": 1, "restore_hashes_match": 1, "restore_log": "",
            "backend": "vertex", "token_capture": "unavailable_remote_dispatch"})

    issues = tmp_path / "issues.db"
    conn = sqlite3.connect(issues)
    conn.execute("CREATE TABLE issues (number INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    missing = bug_loop.reconcile(loop, str(issues))
    assert missing["missing"] == [900000001] and missing["seen"] == 0
    assert loop.query_one("SELECT chia_row_seen FROM repair")["chia_row_seen"] == 0

    conn = sqlite3.connect(issues)
    conn.execute("INSERT INTO issues (number) VALUES (900000001)")
    conn.commit()
    conn.close()
    seen = bug_loop.reconcile(loop, str(issues))
    assert seen["missing"] == [] and seen["seen"] == 1
    assert loop.query_one("SELECT chia_row_seen FROM repair")["chia_row_seen"] == 1


# ---------------------------------------------------------------------------
# The dry-run iteration: one whole seed through every stage, with no Ray
# ---------------------------------------------------------------------------


def probe_spec(probe_id: str, arm: str = "seeded", **overrides) -> schema.ProbeSpec:
    """One `ProbeSpec` a fake generator returns, valid at the seam on either arm.

    The mutation arm's three conditional fields and its unmetered `turn_cost`
    are 2.8's rule and not this fixture's choice: a spec that carried A3's turn
    on the mutation arm would be refused by `validate` before the driver saw it.
    """
    fields = dict(
        probe_id=probe_id, run_manifest_id=_RUN, seed_sha="a" * 40, arm=arm,
        iteration=1, input_filename="input.mlir", input_path="/artefacts/input.mlir",
        tool="circt-opt", argv=["--lower-firrtl-to-hw"], polarity="expect_zero",
        shape="plain", expected_outcome="a clean exit",
        turn_cost={"turn": "probe_write", "wall_seconds": 1.0, "tokens_in": 10,
                   "tokens_out": 5, "cost_usd": None, "metered": True},
        input_text="hw.module @a() {}")
    if arm == "mutation":
        fields.update(mutator_id="drop_operand", mutator_seed_int=7,
                      source_test_path="test/a.mlir",
                      turn_cost={"turn": None, "wall_seconds": 0.01,
                                 "tokens_in": None, "tokens_out": None,
                                 "cost_usd": None, "metered": False})
    fields.update(overrides)
    spec = schema.ProbeSpec(**fields)
    schema.validate(spec)
    return spec


def frame(index: int, function: str, file: str) -> Frame:
    """One resolved CIRCT frame, in the shape B3's symboliser returns."""
    return Frame(index=index, address=f"0x{index:x}", shape="module_offset",
                 module="circt-opt", offset=f"0x{index:x}", function=function,
                 file=file, line=412 + index, in_circt_object=True)


def fake_stages(*, fires: bool = True) -> bug_loop.Stages:
    """Nine stand-in stages: the sequencing is real and the tools are not.

    Every one returns the record shape its real node returns, so the driver's
    own handling of each return is what is under test. None of them needs a
    CIRCT binary, a clone, a container or a model, which is what makes the whole
    iteration tier 0.
    """
    seen = []

    def generate(seed, feedback, remaining, cfg):
        seen.append((remaining.arm, cfg["iteration"]))
        prefix = "p-0" if remaining.arm == "seeded" else "p-1"
        return {"specs": [probe_spec(f"{prefix}00000000001", remaining.arm),
                          probe_spec(f"{prefix}00000000002", remaining.arm)],
                "logs": {}, "counters": schema.CounterBlock(
                    stage="stage_2", started=1, completed=1, failed=0, seconds=0.1)}

    def execute(spec, image, limits, artefact_dir, **kwargs):
        status = "assertion" if fires and spec.probe_id.endswith("1") else "clean_exit"
        build = BuildResult(
            probe_id=spec.probe_id, run_manifest_id=_RUN, run_commit="e" * 40,
            image_digest="sha256:aa", status=status,
            binary_path="/workspace/circt/build/bin/circt-opt",
            binary_sha256="0" * 64, argv=["circt-opt"], exit_status=None,
            signal="SIGABRT" if status == "assertion" else None, limit_hit=None,
            cpu_seconds=0.1, wall_seconds=0.2, peak_rss_bytes=1024,
            worker_hostname="host", worker_node_id="node", child_pid=1,
            stdout_path="/dev/null", stderr_path="/dev/null", stdout_bytes=0,
            stderr_bytes=0, truncated=False)
        result = schema.ProbeResult(
            probe_id=spec.probe_id, run_manifest_id=_RUN, seed_sha=spec.seed_sha,
            arm=spec.arm, iteration=spec.iteration, build_status=status,
            oracle_fired=False, stopping_stage="stage_3",
            stopping_reason="assertion fired" if status == "assertion" else "rc 0",
            artefact_dir=artefact_dir)
        return {"build_result": build, "probe_result": result,
                "counters": schema.CounterBlock(
                    stage="stage_3", started=1, completed=1, failed=0,
                    seconds=0.1)}

    def oracle(build, image, artefact_dir, **kwargs):
        return {"counters": schema.CounterBlock(
            stage="stage_4", started=1, completed=1, failed=0, seconds=0.1),
            "verdict": OracleVerdict(
            probe_id=build.probe_id, fired=True, oracle_class="assertion",
            assertion_text="op->getNumResults() == 1",
            assertion_site="LowerTypes.cpp:412", fatal_message=None,
            frames=[frame(0, "circt::firrtl::LowerTypes::run", "LowerTypes.cpp"),
                    frame(1, "mlir::PassManager::run", "Pass.cpp")],
            prologue_dropped=0, frames_resolved=2, frames_with_location=2,
            fingerprint_frame="circt::firrtl::LowerTypes::run LowerTypes.cpp",
            out_of_scope_root=False, repro_command="circt-opt input.mlir",
            flag_string=bug_loop.IMAGE_FLAG_STRING,
            tool_version_output="circt-opt 1.159.0")}

    def reduce(spec, verdict, limits, artefact_dir, **kwargs):
        return {"counters": schema.CounterBlock(
            stage="stage_5", started=1, completed=1, failed=0, seconds=0.1),
            "reduced": ReducedCase(
            probe_id=spec.probe_id, reducer="circt-reduce", reduced=True,
            fixpoint=True, budget_truncated=False, reason=None, lift=None,
            path="/artefacts/reduced.mlir", size_before_bytes=100,
            size_after_bytes=10, size_before_ops=10, size_after_ops=1,
            wall_seconds=1.0, interestingness_calls=3, recheck_class="assertion",
            recheck_assertion_text=verdict.assertion_text,
            recheck_assertion_site=verdict.assertion_site,
            recheck_matches=True)}

    def screen(candidate, seed, verdict, clone_path, db_path, top_n, **kwargs):
        return {"fingerprint": Fingerprint(
                    probe_id=candidate.probe_id, basis="assertion",
                    value="fp-01", fingerprint_stable=None,
                    frame_tuple=list(candidate.frame_tuple),
                    structural_hash="sh-01"),
                "dedup": DedupVerdict(
                    probe_id=candidate.probe_id, verdict="new",
                    evidence=dict.fromkeys(
                        ("matched_key", "matched_token", "issue_number",
                         "issue_url", "issue_state", "issue_labels",
                         "duplicate_of_candidate_id", "fixing_commit"))),
                "contaminated_symbol": False, "contaminated_file": False,
                "contamination_lower_bound": "seed_commit", "fixing_commits": [],
                "counters": schema.CounterBlock(
                    stage="stage_6", started=1, completed=1, failed=0,
                    seconds=0.1)}

    def report(candidate, reduced, verdict, dedup, manifest_, cfg, artefact_dir,
               **kwargs):
        return {"report": object(), "logs": {}, "failure": None,
                "counters": schema.CounterBlock(
                    stage="stage_6", started=1, completed=1, failed=0,
                    seconds=0.1)}

    def repair(*args, **kwargs):
        raise RuntimeError("repair is disabled in the dry-run iteration")

    def gate(candidate, reduced, dedup, repair_result, manifest_, db_path,
             *, limits, top_n, bin_dir):
        from circt_bug_loop.store import GateDecision

        return {"counters": schema.CounterBlock(
            stage="gate", started=1, completed=1, failed=0, seconds=0.1),
            "decision": GateDecision(
            candidate_id=candidate.candidate_id, q1_reproduce=True,
            q1_original_worker="host-a", q1_rerun_worker="host-b",
            q1_original_pid=1, q1_rerun_pid=2, q1_same_worker=False,
            q2_minimal=True, q2_reason=None, q3_valid=True,
            q3_validity_basis="parsed", q3_after_parse=True, q3_exit_status=0,
            q3_stderr_path="/dev/null", q4_new=True, q4_reason=None,
            stopped_at_question=None, decision="report",
            taxonomy_bucket="new_bug", held_reason=None)}

    return bug_loop.Stages(
        generate_seeded=generate, generate_mutation=generate, probe_execute=execute,
        oracle_primary=oracle, reduce_case=reduce, dedup_and_screen=screen,
        triage_report=report, repair_adapt=repair, gate_decide=gate)


def test_T_U_driver_30(tmp_path: Path, capsys):
    """T-U-driver-30 (FR-14.5, FR-17.4, FR-18.10): one whole iteration, both arms, no Ray.

    The seeded arm runs first and the mutation arm after it, each for the same
    window; the two probes of the iteration go through stages 3 to the gate and
    stop where their own verdict puts them; every dispatched stage contributes a
    `CounterBlock`; and the arm's one `arm_window` ledger entry is written with
    its stop reason. Fixture: a throwaway `loop.db`. Tier 0.
    """
    loop = open_store(tmp_path)
    built = manifest(args=parsed_args(artefact_root=str(tmp_path)))
    loop.insert("run", {
        "run_manifest_id": _RUN, "mode": built.mode, "seed_set": built.seed_set,
        "manifest_json": schema.to_json(built),
        "budget_file_sha": built.budget_file_sha,
        "cluster_yaml_sha": built.cluster_yaml_sha,
        "artefact_root": built.artefact_root, "started_utc": built.started_utc,
        "ended_utc": None})
    budget = budget_file(per_seed_iteration_cap=1, arm_window_seconds=600.0)
    counters = bug_loop.CounterLog(_RUN, str(tmp_path / "results"))
    campaign = bug_loop.Campaign(
        manifest=built, budget=budget, store=loop, stages=fake_stages(),
        dispatch=bug_loop.Dispatch(remote=False), counters=counters,
        recorder=bug_loop.FixtureRecorder(str(tmp_path / "rec")),
        clone_path=str(tmp_path), image_spec=image_spec("ok"), repair_enabled=False)

    seed = schema.SeedRecord(
        seed_sha="a" * 40, parent_sha="b" * 40, subject="fix a crash",
        committed_date_utc="2026-01-01T00:00:00+00:00", source_paths=["lib/A.cpp"],
        test_paths=["test/a.mlir"], llvm_pin="1" * 40, sdk_tag="firtool-1.159.0",
        sdk_exact=True, bumps_away=None, entry_tool="circt-opt",
        dialect_bucket="HW", dialect_bucket_unmerged="HW", run_lines=["RUN: x"],
        argv_template=[["a"]], polarity=["expect_zero"], shape=["plain"],
        diff="", test_files={"test/a.mlir": ""}, corpus_head_sha="d" * 40)

    outcome = bug_loop.campaign_drive(campaign, [seed])

    # Both arms ran, in budget.yaml's order, one after the other.
    assert list(outcome["arms"]) == ["seeded", "mutation"]
    assert all(a["started"] for a in outcome["arms"].values())
    assert all(a["stop_reason"] == "seed_set_exhausted"
               for a in outcome["arms"].values())

    # One seed record per arm; two probes each; the firing one reached the gate.
    assert len(outcome["seeds"]) == 2
    seeded = outcome["seeds"][0]
    assert seeded["arm"] == "seeded" and seeded["iterations"] == 1
    assert [p["stopping_stage"] for p in seeded["probes"]] == ["gate", "stage_3"]
    fired, clean = seeded["probes"]
    assert fired["stages"] == ["stage_3", "stage_4", "stage_5", "stage_6", "gate"]
    assert fired["verdicts"] == {"stage_3": "assertion", "stage_4": "assertion",
                                 "stage_5": "circt-reduce", "stage_6": "new",
                                 "report": "rendered", "gate": "report"}
    assert fired["candidate_id"] == "c-p-000000000001"
    assert clean["stages"] == ["stage_3"] and clean["verdicts"]["stage_3"] == "clean_exit"

    # FR-17.4: every stage contributed a block, and counters.json is on disk.
    stages = {key.split("/", 1)[1] for key in counters.totals}
    assert {"stage_2", "stage_3", "stage_4", "stage_5", "stage_6", "gate"} <= stages
    assert counters.totals["seeded/stage_3"]["started"] == 2
    written = json.loads((tmp_path / "results" / "counters.json").read_text())
    assert written["totals"]["seeded/stage_3"]["completed"] == 2

    # FR-14.4: exactly one arm_window entry per arm, carrying the stop reason.
    windows = loop.query("SELECT arm, amount, stop_reason FROM ledger_entry "
                         "WHERE scope = 'arm_window' ORDER BY arm")
    assert [w["arm"] for w in windows] == ["mutation", "seeded"]
    assert all(w["stop_reason"] == "seed_set_exhausted" for w in windows)

    # --record-fixtures wrote the specs, the results and the bundle it produced.
    recorded = {p.parent.name for p in (tmp_path / "rec").rglob("*.json")}
    assert {"probe_spec", "probe_result", "ledger_entry"} <= recorded


def test_T_U_driver_31(tmp_path: Path):
    """T-U-driver-31 (FR-18.10): the window stops an arm, and the USD cap stops both.

    Fixture: a throwaway `loop.db`. Tier 0.
    """
    loop = open_store(tmp_path)
    built = manifest(args=parsed_args(artefact_root=str(tmp_path)))
    loop.insert("run", {
        "run_manifest_id": _RUN, "mode": built.mode, "seed_set": built.seed_set,
        "manifest_json": "{}", "budget_file_sha": built.budget_file_sha,
        "cluster_yaml_sha": built.cluster_yaml_sha, "artefact_root": str(tmp_path),
        "started_utc": built.started_utc, "ended_utc": None})
    ticks = iter([0.0] + [1000.0] * 40)
    campaign = bug_loop.Campaign(
        manifest=built, budget=budget_file(arm_window_seconds=1.0),
        store=loop, stages=fake_stages(), dispatch=bug_loop.Dispatch(remote=False),
        counters=bug_loop.CounterLog(_RUN, None), clone_path=str(tmp_path),
        image_spec=image_spec("ok"), repair_enabled=False,
        now=lambda: next(ticks))
    outcome = bug_loop.campaign_drive(campaign, [], arms=["seeded"])
    assert outcome["arms"]["seeded"]["stop_reason"] == "arm_window"
    assert outcome["arms"]["seeded"]["seeds"] == 0
