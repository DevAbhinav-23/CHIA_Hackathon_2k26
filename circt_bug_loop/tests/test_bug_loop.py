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
import hashlib
import dataclasses
import inspect
import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import budget as budget_module
from circt_bug_loop import bug_loop
from circt_bug_loop import results as results_module
from circt_bug_loop.contract import schema
from circt_bug_loop.store import (BuildResult, DedupVerdict, DifferentialVerdict,
                                  Fingerprint, Frame, ImageSpec, OracleVerdict,
                                  ReducedCase)
from circt_bug_loop.tests.conftest import call_node
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


def registered_repo(tmp_path: Path, *, mutator_after: bool = False,
                    tag: str = "registration/campaign-01") -> Path:
    """A throwaway repository whose `budget.yaml` commit carries the registration tag.

    Built here rather than committed, which is W-06 erratum 18's rule for every
    budget fixture: the file under test is the repository's own `budget.yaml`
    and a second copy would drift from it.

    Every commit is dated EXPLICITLY, an hour apart. The dates no longer decide
    the freeze rule - W-12 made it ancestry under the registration tag - but
    they still decide FR-14.2's "earlier than the run's start", and two commits
    in the same wall-clock second are what W-16 hit.

    *tag* is the annotated `registration/*` tag, placed on the registration
    commit. `None` builds the same repository UNREGISTERED, which is what a dry
    run, the calibration draw and A7 all see (W-12).
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
    # The set `budget.MUTATOR_SET` resolves to, not a spelled version: check 2
    # asks about the file the run's digest is computed over (W-12c).
    frozen = flow / Path(budget_module.MUTATOR_SET).name
    frozen.write_text('{"set_version": "vN"}\n', encoding="utf-8")
    budget_path = repo / "circt_bug_loop" / "budget.yaml"
    if not mutator_after:
        commit("the mutator set", 1)
    budget_path.write_text(source, encoding="utf-8")
    commit("the registration", 2)
    if tag is not None:
        subprocess.run(git + ("tag", "-a", tag, "-m", "W-22"), check=True,
                       env={**os.environ, "GIT_COMMITTER_DATE":
                            "2026-09-18T02:00:00+00:00"})
    if mutator_after:
        frozen.write_text('{"set_version": "vN", "edited": true}\n', encoding="utf-8")
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
    """T-U-driver-01 (FR-14.2, FR-14.3): check 1 accepts a registered file, refuses a later one.

    Since W-12 it also refuses a CAMPAIGN in a repository carrying no
    `registration/*` tag, and lets a dry run and a `--generator recorded` run
    read the same file, which is the whole point of the tag: A7 and the
    calibration draw both run before the registration exists.

    Fixture: a throwaway repository built here. Tier 0.
    """
    repo = registered_repo(tmp_path)
    path = str(repo / "circt_bug_loop" / "budget.yaml")
    budget = bug_loop.check_01_budget_registered(
        budget_path=path, repo_root=str(repo),
        run_start_utc="2036-01-01T00:00:00+00:00", campaign=True)
    assert len(budget.budget_file_sha) == 40

    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_01_budget_registered(
            budget_path=path, repo_root=str(repo),
            run_start_utc="2000-01-01T00:00:00+00:00")
    assert raised.value.check == "budget_registered"

    unregistered = registered_repo(tmp_path / "untagged", tag=None)
    other = str(unregistered / "circt_bug_loop" / "budget.yaml")
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_01_budget_registered(
            budget_path=other, repo_root=str(unregistered),
            run_start_utc="2036-01-01T00:00:00+00:00", campaign=True)
    assert raised.value.check == "budget_registered"
    assert "registration" in str(raised.value)
    assert bug_loop.check_01_budget_registered(
        budget_path=other, repo_root=str(unregistered),
        run_start_utc="2036-01-01T00:00:00+00:00").budget_file_sha


def test_T_U_driver_02(tmp_path: Path):
    """T-U-driver-02 (FR-05.2): check 2 refuses a set the registration tag cannot reach.

    Fixture: the same repository, with the frozen set edited afterwards. Tier 0.
    """
    repo = registered_repo(tmp_path, mutator_after=True)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_02_mutator_set_earlier(
            repo_root=str(repo), flow_dir=str(repo / "circt_bug_loop"))
    assert raised.value.check == "mutator_set_earlier"

    # An unregistered repository has nothing to be earlier than, and check 1
    # has already refused the campaign in it (W-12).
    untagged = registered_repo(tmp_path / "untagged", mutator_after=True, tag=None)
    bug_loop.check_02_mutator_set_earlier(
        repo_root=str(untagged), flow_dir=str(untagged / "circt_bug_loop"))


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

    # W-18: a run whose REGISTERED filing cap is zero is exempt, and nothing
    # else is. FR-20.1 posts the method so maintainers are not met by reports
    # from a system they were never told about, and a run that can file nothing
    # produces no report for anyone to be surprised by. Any positive cap still
    # requires both values, and an unsupplied cap still requires them.
    bug_loop.check_11_forum_post(forum_post_url=None, forum_post_date=None,
                                 filings_total=0)
    for cap in (1, 10, None):
        with pytest.raises(bug_loop.PreflightFailed):
            bug_loop.check_11_forum_post(forum_post_url=None, forum_post_date=None,
                                         filings_total=cap)
    # And the driver passes the budget's own value, not a literal.
    source = inspect.getsource(bug_loop.run_campaign)
    assert "filings_total=budget.filings_total" in source


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

    # W-18: the head is checked only where a turn would be BUILT there. Under
    # Ray it never is - `llm_turn` builds the client on the `llm` worker from
    # that worker's own environment - and 11.2 forbids forwarding the key or the
    # interlock to a submitted driver, so requiring them of the head made the
    # submit wrapper unable to start any live campaign.
    unset = bug_loop.interlock_probe(env={})
    bug_loop.check_12_live_model(workers={"bugloop_llm": probe})
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_12_live_model(head=unset, workers={"bugloop_llm": probe})
    assert "head" in str(raised.value)
    # And an empty worker map is a refusal and not a pass: a live run with no
    # `llm` container has nowhere to build a client.
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_12_live_model(workers={})
    assert "llm" in str(raised.value)
    # The driver decides by asking Ray, not by a flag.
    assert "head=None if ray.is_initialized() else interlock_probe()" in \
        inspect.getsource(bug_loop.run_campaign)


def test_T_U_driver_28a():
    """T-U-driver-28 (13.1, K7, K11): the checks are named functions, in order.

    Twelve until W-20b, fifteen since: check 13 greps the STAGED
    `issue_task.py` for the vertex branch, because `model_ids["repair_adapt"]`
    was a claim about a file nothing had read; check 14 greps the staged
    `vertex.py` for the two billed usage fields, because without them every
    priced turn and the USD cap are low by whatever the model thinks; and
    check 15 imports `circt_bug_loop` in a subprocess with the wrapper's own
    PYTHONPATH, which is the failure that killed the first real
    `chia job submit` before its first line of work. Fixture: none. Tier 0.
    """
    assert len(bug_loop.PREFLIGHT_CHECKS) == 15
    assert bug_loop.PREFLIGHT_CHECKS[-3:] == ("vertex_branch", "vertex_usage_patch",
                                              "entrypoint_import")
    names = [n for n in dir(bug_loop) if n.startswith("check_")]
    numbered = sorted(n for n in names if n[6:8].isdigit())
    assert len(numbered) == 15
    assert [int(n[6:8]) for n in numbered] == list(range(1, 16))

    # Check 15 passes in this tree, and names what failed when it does not.
    assert bug_loop.check_15_entrypoint_imports() is None
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_15_entrypoint_imports(flow_dir="/nonexistent/circt_bug_loop")
    assert raised.value.check == "entrypoint_import"
    assert "ModuleNotFoundError" in str(raised.value)


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


def test_T_U_driver_17(tmp_path):
    """T-U-driver-17 (FR-12.1, K6, K7, W6): `runtime_env` ships the STAGED package.

    13.1's `py_modules` named the flow's loose modules, the installed `chia`
    directory and two of CHIA's example files, and three of those were wrong on
    a worker: the flow's modules are a package here and import each other as
    `circt_bug_loop.<module>`; uploading the flow directory shipped `tests/`
    (3.8 of its 5.8 MB), `fixtures/repair/issues.db` and, at 6.1's path,
    `loop.db` with the mirrored issue corpus in it; and the installed `chia` is
    an implicit namespace package, which MERGES with a container's own install
    rather than shadowing it, and is unpatched.

    Staged into a `tmp_path` here, so the assertions are about what the function
    produces and not about whatever an earlier run left in the tree. Fixture:
    the installed CHIA checkout. Tier 0.
    """
    staged = bug_loop.stage_shipped(target=str(tmp_path / "_shipped"))
    root = Path(staged["root"])
    assert [Path(p).name for p in staged["py_modules"]] == [
        "circt_bug_loop", "chia", "issue_task.py", "circt_util.py"]
    assert all(Path(p).exists() for p in staged["py_modules"])

    # The flow travels as a package, so `circt_bug_loop.llm` is importable.
    for module in ("llm.py", "probe_task.py", "repair_adapter.py"):
        assert (root / "circt_bug_loop" / module).is_file(), module
    for directory in ("contract", "mutators", "prompts"):
        assert (root / "circt_bug_loop" / directory).is_dir(), directory

    # And what is left behind (W6).
    assert not (root / "circt_bug_loop" / "tests").exists()
    assert not list(root.rglob("loop.db*"))
    assert not list(root.rglob("__pycache__"))

    # CHIA shadows rather than merges, and both patches are in the copy.
    assert (root / "chia" / "__init__.py").is_file()
    assert not (Path(bug_loop._CHIA_PKG) / "__init__.py").exists(), (
        "upstream CHIA is a namespace package; that is the reason for the file")
    vertex = (root / "chia" / "models" / "vertex.py").read_text(encoding="utf-8")
    assert all(field in vertex for field in bug_loop.VERTEX_USAGE_FIELDS)
    assert bug_loop.VERTEX_BRANCH in (root / "issue_task.py").read_text(
        encoding="utf-8")
    # The operator's own checkout is untouched by the staging.
    assert bug_loop.VERTEX_BRANCH not in (
        bug_loop._ISSUE_SOLVER / "issue_task.py").read_text(encoding="utf-8")

    shipped = bug_loop.runtime_env()
    assert shipped["excludes"] == ["**/__pycache__", "**/*.pyc"]
    assert shipped["py_modules"] == [
        str(bug_loop.SHIPPED_DIR / name) for name in bug_loop.SHIPPED_MODULES]
    assert not any(p == str(bug_loop.FLOW_DIR) for p in shipped["py_modules"])


def test_T_U_driver_17b(tmp_path):
    """T-U-driver-17 (K7, K11): checks 13 and 14 read the staged files.

    New half, W-20b. Both refusals are exercised against a staged copy with the
    marker removed, which is exactly the state the tree was in before the
    staging existed: `sync-to-chia.sh` applied the branch into a TARGET checkout
    the driver never ran. Fixture: none. Tier 0.
    """
    unpatched = tmp_path / "issue_task.py"
    unpatched.write_text("def _turn():\n    pass\n", encoding="utf-8")
    patched = tmp_path / "patched.py"
    patched.write_text(f"    {bug_loop.VERTEX_BRANCH}\n", encoding="utf-8")

    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_13_vertex_branch(issue_task_path=str(unpatched),
                                        repair_backend="vertex",
                                        repair_enabled=True)
    assert raised.value.check == "vertex_branch"
    # --no-repair and a non-vertex backend both pass: nothing would run it.
    assert bug_loop.check_13_vertex_branch(
        issue_task_path=str(unpatched), repair_backend="vertex",
        repair_enabled=False) == "vertex"
    assert bug_loop.check_13_vertex_branch(
        issue_task_path=str(unpatched), repair_backend="claude",
        repair_enabled=True) == "claude"
    assert bug_loop.check_13_vertex_branch(
        issue_task_path=str(patched), repair_backend="vertex",
        repair_enabled=True) == "vertex"

    thin = tmp_path / "vertex.py"
    thin.write_text('meta["output_tokens"] += 0\n', encoding="utf-8")
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_14_vertex_usage_patch(vertex_path=str(thin), metered=True)
    assert raised.value.check == "vertex_usage_patch"
    assert "thoughts_token_count" in str(raised.value)
    # `--generator recorded` makes no turn at all, so the patch cannot matter.
    assert bug_loop.check_14_vertex_usage_patch(
        vertex_path=str(thin), metered=False) is None
    fat = tmp_path / "fat.py"
    fat.write_text("\n".join(bug_loop.VERTEX_USAGE_FIELDS), encoding="utf-8")
    assert bug_loop.check_14_vertex_usage_patch(
        vertex_path=str(fat), metered=True) is None


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
    """T-U-driver-24 (K1, FR-03.7, FR-03.10, FR-03.13): the tag, and the digest beside it.

    Two naming schemes used to be in the tree and they could not agree: the
    Dockerfile's header says `chia-circt-assert:<CIRCT_SHA[:12]>` and
    `image_tag` returned `<registry>/chia-circt-assert:<manifest digest[:12]>`,
    so step 1's reuse lookup always missed and `--image-tag eade0de61bc5` could
    never match. The TAG is now the Dockerfile's, and the property that used to
    be the tag's - any one of the six inputs changing it, `slang` and
    `base_image` included - is `manifest_digest`'s, which the `ImageSpec`
    records. The argument ORDER of the target list changes neither, the
    manifest sorting it. Fixture: none. Tier 0.
    """
    base = dict(circt_sha="e" * 40, sdk_tag="firtool-1.159.0",
                targets=("circt-opt", "firtool"), flag_string="-O3 -UNDEBUG")
    manifest = bug_loop.image_manifest(**base)
    tag, digest = bug_loop.image_tag(manifest), bug_loop.manifest_digest(manifest)

    assert tag == f"chia-circt-assert:{'e' * 12}"
    assert "/" not in tag, "nothing is pushed, so there is no registry (K1)"
    reordered = bug_loop.image_manifest(**{**base, "targets": ("firtool", "circt-opt")})
    assert bug_loop.image_tag(reordered) == tag
    assert bug_loop.manifest_digest(reordered) == digest

    for key, value in (("circt_sha", "f" * 40), ("sdk_tag", "firtool-1.158.0"),
                       ("targets", ("circt-opt",)), ("flag_string", "-O2")):
        assert bug_loop.manifest_digest(
            bug_loop.image_manifest(**{**base, key: value})) != digest
    assert bug_loop.manifest_digest(
        bug_loop.image_manifest(**base, slang=False)) != digest
    assert bug_loop.manifest_digest(
        bug_loop.image_manifest(**base, base_image="other")) != digest
    # The five inputs other than the commit share a tag and differ in the digest,
    # which is exactly why the digest is recorded rather than folded into a name.
    assert bug_loop.image_tag(bug_loop.image_manifest(**base, slang=False)) == tag


def test_T_U_driver_24b(monkeypatch):
    """T-U-driver-24 (K1): B1 is a head node, it never pushes, and --dry-run inspects.

    New half, W-20b. `build_image` ran at `{"circt": 1}`, inside a container of
    the very image it would build: no docker binary, no socket, and `_run`
    catches only `TimeoutExpired`, so its first line raised `FileNotFoundError`
    out of the node - and `--dry-run` returns AFTER all of that, so the one
    command that is supposed to spend nothing died before printing anything.
    Fixture: none. Tier 0.
    """
    from circt_bug_loop.bug_loop import ImageBuildError

    assert bug_loop.build_image._chia_options == {"max_retries": 0}
    assert "circt_bug_loop.bug_loop.build_image" in bug_loop.HEAD_NODES
    # Read off the parsed body and not the text, the docstring naming the step
    # that was removed: no literal anywhere under `build_image` is a push.
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(
        inspect.getsource(bug_loop.build_image._chia_original)))
    tree.body[0].body.pop(0)                       # the docstring
    assert "push" not in ast.unparse(tree)
    assert not hasattr(bug_loop, "DEFAULT_REGISTRY")

    # --dry-run's path: the tag is inspected and no build is ever started.
    calls = []

    def _no_docker(argv, *, timeout, cwd=None):
        calls.append(list(argv))
        return {"rc": 1, "stdout": "", "stderr": "No such image"}

    monkeypatch.setattr(bug_loop, "_run", _no_docker)
    with pytest.raises(ImageBuildError) as raised:
        bug_loop.build_image._chia_original(
            "e" * 40, "firtool-1.159.0", bug_loop.IMAGE_TARGETS,
            bug_loop.IMAGE_FLAG_STRING, "Dockerfile", inspect_only=True)
    assert raised.value.step == "reuse"
    assert calls == [["docker", "image", "inspect", f"chia-circt-assert:{'e' * 12}"]]

    # And the Dockerfile it would have built from exists in THIS tree, which is
    # the path K1 measured as absent under `~/.cache/chia-src/dockerfiles/`.
    dockerfile, context = bug_loop.dockerfile_and_context()
    assert Path(dockerfile).is_file()
    assert dockerfile == str(Path(bug_loop.FLOW_DIR).parent / "upstream"
                             / "dockerfiles" / bug_loop.DOCKERFILE_NAME)
    assert context == str(Path(bug_loop.FLOW_DIR).parent)


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
#
# The fixtures below are a MINI-CAMPAIGN and not nine stubs. Each fake stage
# returns the record its real node returns AND writes what its real node
# writes: the screen writes the candidate row and its two verdict rows through
# `triage_task._write_rows`, which is B6b's own writer, and stage 3 classifies a
# recorded tool stderr through the real `classify_build`. That is what makes
# `T-U-driver-32` a test of the driver's write path rather than of its own
# fixtures: everything else in `loop.db` afterwards is the driver's.
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


def fake_stages(*, fires: bool = True, repairs: bool = False) -> bug_loop.Stages:
    """Ten stand-in stages: the sequencing is real and the tools are not.

    Every one returns the record shape its real node returns and writes what its
    real node writes, so the driver's own handling of each return, and its own
    write path around them, is what is under test. None of them needs a CIRCT
    binary, a clone, a container or a model, which is what makes the whole
    iteration tier 0.
    """
    seen = []

    def generate(seed, feedback, remaining, cfg):
        seen.append((remaining.arm, cfg["iteration"]))
        prefix = "p-0" if remaining.arm == "seeded" else "p-1"
        return {"specs": [probe_spec(f"{prefix}00000000001", remaining.arm),
                          probe_spec(f"{prefix}00000000002", remaining.arm)],
                "logs": {"usage": {"seed_read": {"tokens_in": 100, "tokens_out": 20},
                                   "probe_write": {"tokens_in": 200,
                                                   "tokens_out": 40}},
                         "wall_seconds": {"seed_read": 0.04, "probe_write": 0.05}},
                "counters": schema.CounterBlock(
                    stage="stage_2", started=1, completed=1, failed=0, seconds=0.1)}

    def execute(spec, image, limits, artefact_dir, **kwargs):
        # The recorded stderr of a real firing and a real clean exit, classified
        # by the real `classify_build`: FR-18.11's regeneration re-reads the file
        # this copies and re-runs that function over it, so a fixture that made
        # up either would make up the regeneration too.
        from circt_bug_loop.probe_task import classify_build

        firing = fires and spec.probe_id.endswith("1")
        capture = FIXTURES / "stderr" / ("assert_glibc.txt" if firing else "clean.txt")
        stderr = Path(bug_loop.write_artefact(
            artefact_dir, "stderr.txt", capture.read_bytes()))
        signal = "SIGABRT" if firing else None
        status, reason = classify_build(None if firing else 0, signal,
                                        stderr.read_text(encoding="utf-8"), None)
        build = BuildResult(
            probe_id=spec.probe_id, run_manifest_id=_RUN, run_commit="e" * 40,
            image_digest=image.image_digest, status=status,
            binary_path="/workspace/circt/build/bin/circt-opt",
            binary_sha256="0" * 64, argv=["circt-opt"],
            exit_status=None if firing else 0,
            signal=signal, limit_hit=None,
            cpu_seconds=0.1, wall_seconds=0.2, peak_rss_bytes=1024,
            worker_hostname="host", worker_node_id="node", child_pid=1,
            stdout_path="/dev/null", stderr_path=str(stderr), stdout_bytes=0,
            stderr_bytes=capture.stat().st_size, truncated=False)
        result = schema.ProbeResult(
            probe_id=spec.probe_id, run_manifest_id=_RUN, seed_sha=spec.seed_sha,
            arm=spec.arm, iteration=spec.iteration, build_status=status,
            oracle_fired=False, stopping_stage="stage_3",
            stopping_reason=reason, artefact_dir=artefact_dir)
        return {"build_result": build, "probe_result": result,
                "counters": schema.CounterBlock(
                    stage="stage_3", started=1, completed=1, failed=0,
                    seconds=0.1)}

    def differential(spec, build, image, artefact_dir, **kwargs):
        return {"counters": schema.CounterBlock(
            stage="stage_4", started=1, completed=1, failed=0, seconds=0.1),
            "verdict": DifferentialVerdict(
            probe_id=spec.probe_id, verdict="diverge",
            reason="the two simulators disagree on one output at cycle 37",
            verilator_version="5.028",
            x_policy="x-assign=unique,x-initial=unique", stimulus_id="stim-01",
            port_list_sha="c" * 64, cycles=128, first_divergent_signal="out_sum",
            first_divergent_cycle=37, arcilator_value="32'h10",
            verilator_value="32'h11",
            arcilator_trace_path=f"{artefact_dir}/arcilator.vcd",
            verilator_trace_path=f"{artefact_dir}/verilator.vcd",
            driver_source="circt/arc-tests")}

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
        # B6b's own three rows, through B6b's own writer: §6.4 rule 4 makes them
        # one transaction and the driver must not write them a second time.
        from circt_bug_loop.store import LoopStore
        from circt_bug_loop.triage_task import _screened, _write_rows

        fingerprint = Fingerprint(
            probe_id=candidate.probe_id, basis="assertion",
            value=f"fp-{candidate.arm}", fingerprint_stable=None,
            frame_tuple=list(candidate.frame_tuple), structural_hash="s" * 64)
        dedup = DedupVerdict(
            probe_id=candidate.probe_id, verdict="new",
            evidence=dict.fromkeys(
                ("matched_key", "matched_token", "issue_number", "issue_url",
                 "issue_state", "issue_labels", "duplicate_of_candidate_id",
                 "fixing_commit")))
        _write_rows(LoopStore(db_path),
                    _screened(candidate, fingerprint, dedup, False, False,
                              "seed_commit"),
                    fingerprint, dedup)
        return {"fingerprint": fingerprint, "dedup": dedup,
                "contaminated_symbol": False, "contaminated_file": False,
                "contamination_lower_bound": "seed_commit", "fixing_commits": [],
                "counters": schema.CounterBlock(
                    stage="stage_6", started=1, completed=1, failed=0,
                    seconds=0.1)}

    def report(candidate, reduced, verdict, dedup, manifest_, cfg, artefact_dir,
               **kwargs):
        from circt_bug_loop.store import Report

        rendered = Report(
            candidate_id=candidate.candidate_id, path=f"{artefact_dir}/report.md",
            template=("differential" if candidate.oracle_class == "differential"
                      else "primary"),
            title=f"circt-opt: {candidate.oracle_class} on a reduced input",
            classification="bug",
            classification_reason="An oracle fired on a reduced input.",
            rendered_sha256="d" * 64,
            assisted_by="circt_bug_loop:vertex:gemini-3.8-flash",
            fields_present=["repro_command"])
        return {"report": rendered, "logs": {"usage": {"tokens_in": 30,
                                                       "tokens_out": 9}},
                "failure": None,
                "counters": schema.CounterBlock(
                    stage="stage_6", started=1, completed=1, failed=0,
                    seconds=0.1)}

    def repair(report_, candidate, reduced, verdict, manifest_, cfg, *,
               local_id, input_path, **kwargs):
        from circt_bug_loop.store import RepairResult

        if not repairs:
            raise RuntimeError("repair is disabled in this dry-run iteration")
        return {"counters": schema.CounterBlock(
            stage="stage_7", started=1, completed=1, failed=0, seconds=0.1),
            "result": RepairResult(
            candidate_id=candidate.candidate_id, local_id=local_id,
            status="fixed", failing_phase=None, reproduced=True, build_ok=True,
            fixed=True, lit_ok=True, lit_unusable=False, lit_passed=1119,
            lit_failed=0, lit_failures=[], diff_path=f"{input_path}.diff",
            diff_added=3, diff_removed=1, chia_artifact_dir=None,
            repro_dir=f"{manifest_.artefact_root}/{manifest_.run_manifest_id}"
                      f"/repair/{local_id}",
            repro_overwritten=True, restore_ok=True, restore_hashes_match=True,
            restore_log="reset, rebuilt and re-hashed", backend="vertex",
            token_capture="unavailable_remote_dispatch")}

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
        oracle_primary=oracle, oracle_differential=differential,
        reduce_case=reduce, dedup_and_screen=screen, triage_report=report,
        repair_adapt=repair, gate_decide=gate)


def seed_record(seed_sha: str = "a" * 40) -> schema.SeedRecord:
    """One mined seed, as A1 returns it, for a campaign of one seed per arm."""
    return schema.SeedRecord(
        seed_sha=seed_sha, parent_sha="b" * 40, subject="fix a crash",
        committed_date_utc="2026-01-01T00:00:00+00:00", source_paths=["lib/A.cpp"],
        test_paths=["test/a.mlir"], llvm_pin="1" * 40, sdk_tag="firtool-1.159.0",
        sdk_exact=True, bumps_away=None, entry_tool="circt-opt",
        dialect_bucket="HW", dialect_bucket_unmerged="HW", run_lines=["RUN: x"],
        argv_template=[["a"]], polarity=["expect_zero"], shape=["plain"],
        diff="", test_files={"test/a.mlir": ""}, corpus_head_sha="d" * 40)


def mini_campaign(tmp_path: Path, *, repair_enabled: bool = False,
                  **overrides) -> dict:
    """Drive one whole campaign into a throwaway `loop.db`, with no Ray.

    The store is the DRIVER's: `write_run_rows` writes the four tables §6.4 puts
    down before the first probe and `campaign_drive` writes the rest as the
    stages return them. Nothing here inserts a row of its own.

    Returns:
        {"store", "manifest", "outcome", "counters", "seed", "labelled_pairs"}.
    """
    loop = open_store(tmp_path)
    built = manifest(args=parsed_args(artefact_root=str(tmp_path)))
    spec = image_spec("ok")
    seed = seed_record()
    bug_loop.write_run_rows(
        loop, built, image_spec=spec,
        mined={"seeds": [seed], "sdk_map": {seed.sdk_tag: [seed.seed_sha]},
               "exclusions": {}, "sv_seeds": []},
        mirror=dict(_MIRROR))
    budget = budget_file(**{"per_seed_iteration_cap": 1,
                            "arm_window_seconds": 600.0,
                            **overrides.pop("budget", {})})
    bug_loop.accrue_offline(loop, built, budget,
                            dispatch=bug_loop.Dispatch(remote=False),
                            image_seconds=3600.0)
    counters = bug_loop.CounterLog(_RUN, str(tmp_path / "results"))
    campaign = bug_loop.Campaign(
        manifest=built, budget=budget, store=loop,
        stages=overrides.pop("stages", None) or fake_stages(),
        dispatch=bug_loop.Dispatch(remote=False), counters=counters,
        recorder=bug_loop.FixtureRecorder(str(tmp_path / "rec")),
        clone_path=str(tmp_path), image_spec=spec, repair_enabled=repair_enabled,
        **overrides)
    outcome = bug_loop.campaign_drive(campaign, [seed])
    bug_loop.finish_run(loop, built, "2026-09-19T09:00:00+00:00")
    return {"store": loop, "manifest": built, "outcome": outcome, "seed": seed,
            "counters": counters,
            # FR-10.2's labelled set is the project's own external measurement
            # (W-12): recorded failures labelled by hand before any fingerprint
            # was computed, belonging to no campaign, so the driver passes the
            # committed set and this store is asked about none of it.
            "labelled_pairs": results_module.load_labelled_pairs()}


def test_T_U_driver_30(tmp_path: Path, capsys):
    """T-U-driver-30 (FR-14.5, FR-17.4, FR-18.10): one whole iteration, both arms, no Ray.

    The seeded arm runs first and the mutation arm after it, each for the same
    window; the two probes of the iteration go through stages 3 to the gate and
    stop where their own verdict puts them; every dispatched stage contributes a
    `CounterBlock`; and the arm's one `arm_window` ledger entry is written with
    its stop reason. Fixture: a throwaway `loop.db`. Tier 0.
    """
    run = mini_campaign(tmp_path)
    loop, outcome, counters = run["store"], run["outcome"], run["counters"]

    # Both arms ran, in budget.yaml's order, one after the other.
    assert list(outcome["arms"]) == ["seeded", "mutation"]
    assert all(a["started"] for a in outcome["arms"].values())
    assert all(a["stop_reason"] == "seed_set_exhausted"
               for a in outcome["arms"].values())

    # One seed record per arm; two probes each; the firing one reached the gate
    # and the clean one went on to the differential, its argv being HW-terminal.
    assert len(outcome["seeds"]) == 2
    seeded = outcome["seeds"][0]
    assert seeded["arm"] == "seeded" and seeded["iterations"] == 1
    assert [p["stopping_stage"] for p in seeded["probes"]] == ["gate", "stage_6"]
    fired, clean = seeded["probes"]
    assert fired["stages"] == ["stage_3", "stage_4", "stage_5", "stage_6", "gate"]
    assert fired["verdicts"] == {"stage_3": "assertion", "stage_4": "assertion",
                                 "stage_5": "circt-reduce", "stage_6": "new",
                                 "report": "rendered", "gate": "report"}
    assert fired["candidate_id"] == "c-p-000000000001"
    assert clean["stages"] == ["stage_3", "stage_4", "stage_6"]
    assert clean["verdicts"]["stage_3"] == "clean_exit"
    assert clean["verdicts"]["differential"] == "diverge"

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


# ---------------------------------------------------------------------------
# T-U-driver-32 to -34: the write path of 6.4
# ---------------------------------------------------------------------------


def test_T_U_driver_32(tmp_path: Path):
    """T-U-driver-32 (FR-17.2, FR-17.6, FR-18.1): the driver's own store renders.

    The store this reads is the one `T-U-driver-30` drove and nothing else: no
    row of it was written by a test helper. `render_results` refuses an artefact
    that is missing any element `03-LLD.md` §14.4 makes mandatory, so a single
    table the driver forgot to write is a refusal here, which is what makes this
    the end-to-end check on §6.4's write path rather than fourteen assertions
    about tables. Fixture: a throwaway `loop.db`. Tier 0.
    """
    from circt_bug_loop.results import render_results

    run = mini_campaign(tmp_path)
    rendered = call_node(render_results, run["store"], run["manifest"],
                         labelled_pairs=run["labelled_pairs"])["rendered"]
    assert "REFUSED" not in rendered
    assert rendered.endswith("\n") and not rendered.endswith("\n\n")
    # The four elements a store with no filings still has to carry.
    for element in ("Distinct confirmed bugs per arm", "Both arm windows",
                    "Divergences observed",
                    "regenerated from its recorded artefacts"):
        assert element in rendered
    # FR-18.11: nothing is MARKED. The recorded stderr reclassifies to the row
    # the driver wrote and the gate's answers decide to the decision it wrote.
    assert "**MARKED**" not in rendered


def test_T_U_driver_33(tmp_path: Path):
    """T-U-driver-33 (FR-17.2, FR-17.8, FR-12.10): every table of §6.4, in its order.

    One row per probe in `probe`, `build_result` and `probe_result`; one
    `oracle_verdict` per firing and one `differential_verdict` per admitted
    clean exit; the candidate rows B6b wrote and the differential ones the head
    wrote; a `report` and a `gate_decision` where the probe reached them; the
    per-stage ledger occupancy of every dispatched stage; and no PARTIAL marker
    left behind, every probe directory having its completion row.
    Fixture: a throwaway `loop.db`. Tier 0.
    """
    run = mini_campaign(tmp_path)
    loop = run["store"]

    def count(table: str) -> int:
        return loop.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]

    assert count("run") == 1 and count("image") == 1
    assert count("seed") == 1 and count("sdk_map") == 1
    assert count("issue_mirror_meta") == 1
    assert count("probe") == count("build_result") == count("probe_result") == 4
    assert count("oracle_verdict") == 2 and count("differential_verdict") == 2
    assert count("reduced_case") == 2
    assert count("candidate") == 4 and count("fingerprint") == 2
    assert count("dedup_verdict") == 2 and count("report") == 4
    assert count("gate_decision") == 2 and count("feedback") == 2
    assert count("repair") == 0 and count("filing") == 0

    # FR-17.6: every row traces to this run, and the run row carries its end.
    assert loop.query_one("SELECT ended_utc FROM run")["ended_utc"] is not None
    for table in ("probe", "probe_result", "candidate", "seed", "sdk_map",
                  "ledger_entry", "issue_mirror_meta"):
        assert loop.query_one(
            f"SELECT COUNT(*) AS n FROM {table} "
            "WHERE run_manifest_id <> ?", (_RUN,))["n"] == 0

    # The differential candidates are report-only: FR-08.10 keeps them out of
    # the reducer, the dedup and the gate, and their report is the other
    # template.
    differential = loop.query(
        "SELECT c.candidate_id, r.template FROM candidate c "
        "JOIN report r USING (candidate_id) WHERE c.oracle_class = 'differential'")
    assert len(differential) == 2
    assert {row["template"] for row in differential} == {"differential"}
    assert loop.query_one(
        "SELECT COUNT(*) AS n FROM gate_decision g JOIN candidate c "
        "USING (candidate_id) WHERE c.oracle_class = 'differential'")["n"] == 0

    # §6.4 rule 4: the gate's decision and the candidate's bucket agree, having
    # been written in one transaction.
    for row in loop.query("SELECT g.taxonomy_bucket AS gated, c.taxonomy_bucket "
                          "AS carried FROM gate_decision g "
                          "JOIN candidate c USING (candidate_id)"):
        assert row["gated"] == row["carried"] == "new_bug"

    # FR-17.8: the marker is gone from every probe directory that completed, and
    # 3.11's stage occupancy is one ledger entry per dispatched stage per probe.
    for row in loop.query("SELECT artefact_dir FROM probe_result"):
        assert Path(row["artefact_dir"]).is_dir()
        assert not (Path(row["artefact_dir"]) / "PARTIAL").exists()
    # A5's bundle is on disk at the path its row carries, and the driver's own
    # write leaves no marker in a directory nothing could clear one from.
    for row in loop.query("SELECT path FROM feedback"):
        assert Path(row["path"]).is_file()
        assert not (Path(row["path"]).parent / "PARTIAL").exists()
    stage_3 = loop.query("SELECT arm, amount FROM ledger_entry "
                         "WHERE scope = 'stage' AND stage = 'stage_3'")
    assert len(stage_3) == 4 and {row["arm"] for row in stage_3} == {"seeded",
                                                                     "mutation"}
    # A3 is one node and two stages, so its turns are charged apart, and the
    # offline synthesis carries the date FR-05.8's declaration reads.
    assert loop.query_one("SELECT COUNT(*) AS n FROM ledger_entry "
                          "WHERE scope = 'stage' AND stage = 'stage_1'")["n"] == 2
    assert loop.query_one("SELECT stage FROM ledger_entry WHERE arm = 'shared' "
                          "AND stage = 'synthesis'")["stage"] == "synthesis"


def test_T_U_driver_34(tmp_path: Path, monkeypatch):
    """T-U-driver-34 (FR-17.3, §6.1): under Ray every write goes through the node.

    `LoopStore` dispatches its members as Ray tasks when a session is running
    and opens one direct connection when it is not (§6.1), and the driver takes
    whichever it is given: every other test here takes the direct path, and this
    one takes the SQLiteNode path against a stub, as `T-U-store-02` does. The
    stub runs the same statements against the same file, so what is asserted is
    that the driver reached the database through the node and nowhere else.
    Fixture: a throwaway `loop.db`. Tier 0.
    """
    import sys
    import types

    from circt_bug_loop import store as store_module

    seen = []

    class _Member:
        def __init__(self, name, run):
            self.name, self.run = name, run

        def chia_remote(self, *args):
            seen.append(self.name)
            return self.run(*args)

    class _SQLiteNode:
        """Every statement, recorded and then run against the same file."""

        def __init__(self, db_path, **kwargs):
            self.db_path = db_path
            self.init_schema = _Member(
                "init_schema", lambda script: _script(db_path, script))
            for member, local in store_module._LOCAL_MEMBERS.items():
                setattr(self, member,
                        _Member(member, lambda *a, _l=local: _l(db_path, *a)))

    def _script(db_path, script):
        import sqlite3

        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(script)
        finally:
            conn.close()

    monkeypatch.setitem(sys.modules, "chia.database.sqlite_node",
                        types.SimpleNamespace(SQLiteNode=_SQLiteNode))
    monkeypatch.setitem(sys.modules, "chia.base.ChiaFunction",
                        types.SimpleNamespace(get=lambda value: value))
    monkeypatch.setattr(store_module, "_ray_initialised", lambda: True)
    # The column cache is per process and the schema is fixed, so a later store
    # reuses an earlier one's read; emptied here, the pragma read takes the same
    # path as the writes and is asserted with them.
    monkeypatch.setattr(bug_loop, "_TABLE_COLUMNS", {})

    loop = store_module.LoopStore(str(tmp_path / "loop.db"))
    assert loop.node is not None
    built = manifest(args=parsed_args(artefact_root=str(tmp_path)))
    seed = seed_record()
    bug_loop.write_run_rows(loop, built, image_spec=image_spec("ok"),
                            mined={"seeds": [seed], "sdk_map": {}, "exclusions": {},
                                   "sv_seeds": []},
                            mirror=dict(_MIRROR))
    bug_loop.write_probe(loop, probe_spec("p-000000000001"),
                         str(tmp_path / "probe"))
    assert {"init_schema", "execute", "executemany", "query", "query_one"} <= set(seen)
    assert loop.query_one("SELECT COUNT(*) AS n FROM probe")["n"] == 1


def test_T_U_driver_35(tmp_path: Path):
    """T-U-driver-35 (FR-12.10, §6.4 rule 1): the loop's repair row before CHIA's.

    The head mints the identifier, stamps it on the candidate and opens the
    `repair` row at `dispatched` BEFORE B8 runs, and completes that same row
    from the `RepairResult`; `chia_row_seen` stays 0 until the reconciliation
    sets it, which is what `T-U-driver-18` then reads.
    Fixture: a throwaway `loop.db`. Tier 0.
    """
    run = mini_campaign(tmp_path, repair_enabled=True,
                        stages=fake_stages(repairs=True))
    loop = run["store"]
    rows = loop.query("SELECT r.*, c.local_id AS candidate_local_id FROM repair r "
                      "JOIN candidate c USING (candidate_id) ORDER BY r.candidate_id")
    assert len(rows) == 2
    for row in rows:
        assert row["local_id"] == row["candidate_local_id"] >= 900_000_000
        assert row["status"] == "fixed" and row["chia_row_seen"] == 0
        assert row["repro_dir"].endswith(f"/repair/{row['local_id']}")
        assert row["backend"] == "vertex" and row["repro_overwritten"] == 1
    assert [p["verdicts"]["stage_7"] for p in run["outcome"]["seeds"][0]["probes"]
            if "stage_7" in p["verdicts"]] == ["fixed"]

    # A repair that never came back leaves the row it opened, which is the whole
    # point of writing it first (FR-12.10).
    refused_root = tmp_path / "refused"
    refused_root.mkdir()
    other = mini_campaign(refused_root, repair_enabled=True)
    refused = other["store"].query_one("SELECT status, chia_row_seen FROM repair")
    assert refused["status"] == "dispatched" and refused["chia_row_seen"] == 0


def test_T_U_driver_36_the_spend_guard_is_wired_and_stops_the_arm(tmp_path: Path):
    """T-U-driver-36 (W1, W10): the pre-authorisation reaches the turn, and binds.

    New id, W-20b. Three things, in one campaign.

    W10: the `LedgerSnapshot` a generator reads was built ONCE per seed and
    handed to every iteration, so a seed's third iteration read a `remaining`
    that predated its first two; it is rebuilt per iteration now, from the same
    `ledger.aggregate` the spend guard is built from.

    W1: the cfg carries `llm.SpendGuard`, so every turn is authorised against
    `campaign_spend_cap_usd` BEFORE it is sent, rather than the cap being tested
    once per seed against spend already recorded.

    And the refusal stops the ARM: a turn the guard refuses is recorded by A3
    as `turn_failed:SpendCapRefused`, which is not a failed seed but the cap
    binding, so `drive_seed` ends with `campaign_spend_cap` and `campaign_drive`
    never starts the other arm.

    Fixture: a throwaway `loop.db`. Tier 0.
    """
    from circt_bug_loop.llm import SpendCapRefused, SpendGuard

    seen = []

    def generate(seed, feedback, remaining, cfg):
        guard = cfg["spend_guard"]
        seen.append({"iteration": cfg["iteration"], "guard": guard,
                     "snapshot_spent": remaining.spent})
        # What A3 does with a refusal: FR-04.8's blanket catch records it.
        try:
            guard.authorise("x" * 3000)
        except SpendCapRefused as error:
            return {"specs": [], "logs": {}, "counters": schema.CounterBlock(
                stage="stage_2", started=1, completed=0, failed=1, seconds=0.1),
                "failure": f"turn_failed:{type(error).__name__}"}
        return {"specs": [], "logs": {}, "counters": schema.CounterBlock(
            stage="stage_2", started=1, completed=1, failed=0, seconds=0.1),
            "failure": None}

    stages = dataclasses.replace(fake_stages(), generate_seeded=generate,
                                 generate_mutation=generate)
    run = mini_campaign(tmp_path, stages=stages,
                        budget={"campaign_spend_cap_usd": 0.001})

    # The guard is real, is the budget's, and refused.
    assert seen, "the generator was never called"
    guard = seen[0]["guard"]
    assert isinstance(guard, SpendGuard)
    assert guard.cap_usd == 0.001
    assert guard.price_usd_per_m_output_tokens == budget_file(
        ).price_usd_per_m_output_tokens

    # The arm stopped on the cap, and the other arm never started (§3.11).
    arms = run["outcome"]["arms"]
    assert arms["seeded"]["stop_reason"] == "campaign_spend_cap"
    assert arms["mutation"]["started"] is False
    assert run["outcome"]["stopped"] == "campaign_spend_cap"
    assert run["outcome"]["seeds"][0]["terminating_condition"] == "campaign_spend_cap"
    # And nothing was spent discovering it: the refusal precedes the request.
    assert guard.authorised_usd == 0.0


def test_T_U_driver_37_the_snapshot_is_rebuilt_every_iteration(tmp_path: Path):
    """T-U-driver-37 (W10): each iteration reads its own `LedgerSnapshot`.

    New id, W-20b. Three iterations of one seed, each recording the object it
    was handed: three distinct snapshots, each carrying the arm's elapsed window
    as of that iteration rather than as of the seed's first. Fixture: a
    throwaway `loop.db`. Tier 0.
    """
    handed = []

    def generate(seed, feedback, remaining, cfg):
        handed.append(remaining)
        return {"specs": [], "logs": {}, "counters": schema.CounterBlock(
            stage="stage_2", started=1, completed=1, failed=0, seconds=0.1),
            "failure": None}

    stages = dataclasses.replace(fake_stages(), generate_seeded=generate,
                                 generate_mutation=generate)
    mini_campaign(tmp_path, stages=stages,
                  budget={"per_seed_iteration_cap": 3})

    # A seed with no probes ends at `no_probe_written` after one iteration, so
    # the per-arm count here is one; what the test pins is that the object is
    # built inside the loop and not before it.
    source = inspect.getsource(bug_loop.drive_seed)
    body = source.split("for iteration in range")[1]
    assert "budget_module.snapshot(" in body, (
        "the snapshot is built inside the iteration loop (W10)")
    assert "budget_module.snapshot(" not in source.split("for iteration in range")[0]
    assert handed and all(s.arm in ("seeded", "mutation") for s in handed)
    assert len({id(s) for s in handed}) == len(handed), "one object per iteration"


def test_T_U_driver_38_checks_seven_and_eight_ask_the_workers(tmp_path: Path):
    """T-U-driver-38 (W2, FR-06.1, FR-03.15): the observations are the workers' own.

    New id, W-20b. Both call sites built `observed` FROM the `ImageSpec` they
    were comparing against, so each compared a value to itself and neither
    could ever fail: FR-06.1's "every tool binary's SHA-256 on every worker"
    and FR-03.15's Verilator check had no pre-flight at all, and the only real
    hash check left was `probe_execute`'s per-probe one, which turns a wrong
    image into `BinaryMismatch` on every probe rather than one refusal at
    start-up. `tool_probe` is the node that asks; this runs it against a
    throwaway bin directory and feeds both checks what it returns.

    Fixture: a throwaway bin directory. Tier 0.
    """
    spec = image_spec("ok")
    directory = tmp_path / "bin"
    directory.mkdir()
    for tool, digest in spec.tool_hashes.items():
        (directory / tool).write_bytes(b"")

    probe = bug_loop.tool_probe(str(directory), tuple(spec.tool_hashes))
    # Every target was readable, and every hash is the FILE's and not the spec's.
    assert probe["unreadable"] == []
    assert set(probe["tool_hashes"]) == set(spec.tool_hashes)
    empty = hashlib.sha256(b"").hexdigest()
    assert set(probe["tool_hashes"].values()) == {empty}
    assert probe["worker"]

    # So check 7 REFUSES on this worker, naming the tool and both hashes...
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_07_tool_hashes(
            image_spec=spec, observed={"bugloop_circt": probe["tool_hashes"]})
    assert raised.value.check == "tool_hashes"
    assert "bugloop_circt" in str(raised.value) and empty in str(raised.value)

    # ...and passes only when the worker's own hashes ARE the recorded ones.
    assert bug_loop.check_07_tool_hashes(
        image_spec=spec, observed={"bugloop_circt": dict(spec.tool_hashes)}) is None

    # A tool the worker cannot read leaves no entry, so check 7 sees None and
    # refuses rather than passing over a missing binary.
    (directory / next(iter(spec.tool_hashes))).unlink()
    gapped = bug_loop.tool_probe(str(directory), tuple(spec.tool_hashes))
    assert len(gapped["unreadable"]) == 1
    with pytest.raises(bug_loop.PreflightFailed):
        bug_loop.check_07_tool_hashes(
            image_spec=spec, observed={"bugloop_circt": gapped["tool_hashes"]})

    # Check 8 takes the same probe's version string, and a difference refuses.
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_08_verilator_version(
            image_spec=spec, observed={"bugloop_circt": "Verilator 4.999"})
    assert raised.value.check == "verilator_version"

    # And the cluster YAML says WHICH types are asked: the ones running the
    # image, read off `docker.image` rather than guessed from a resource name.
    cluster = bug_loop.cluster_summary(str(Path(bug_loop.FLOW_DIR)
                                           / "cluster_single.yaml"))
    assert cluster["image_worker_types"] == ["bugloop_circt", "bugloop_repair"]
    assert "bugloop_llm" not in cluster["image_worker_types"]


def test_T_U_driver_39_recorded_mode_needs_no_credential(monkeypatch, capsys):
    """T-U-driver-39 (W4): `--generator recorded` skips check 12 entirely.

    New id, W-20b. The mode exists so that the whole of `campaign_drive` can be
    exercised ON THE CLUSTER with no model turn and no credential; check 12
    refused the run unless the head AND both llm workers carried
    BUGLOOP_ALLOW_LIVE_MODEL=1 and a usable key, which is the opposite of what
    the mode is for. Fixture: none. Tier 0.
    """
    import inspect as _inspect

    source = _inspect.getsource(bug_loop.run_campaign)
    guarded = source.split('if args.generator == "recorded":')[1]
    assert "check_12_live_model" not in guarded.split("else:")[0]
    assert "check_12_live_model" in guarded.split("else:")[1]
    # And `repair_enabled` is already false in the mode, so no `repair` worker
    # is asked for a key either (§3.8: stage 7 IS a turn, whatever the backend).
    args = bug_loop.build_parser().parse_args(
        ["--mode", "discovery", "--generator", "recorded"])
    assert bug_loop.repair_enabled(args) is False
    assert bug_loop.resolved_config(args)["repair_enabled"] is False


def test_T_U_driver_40_the_probe_record_carries_the_reason_it_stopped(tmp_path: Path):
    """T-U-driver-40 (W3, FR-16): `stopping_reason` is the PROBE's, not stage 3's.

    New id, W-20b. The driver assigned `result.stopping_stage` five times and
    `result.stopping_reason` never, so the column carried stage 3's build
    classification for the life of the probe: a candidate that reached the gate
    carried `assertion_fired`, and `feedback._reason` renders
    `f"{build_status}:{stopping_reason}"` into every `FeedbackEntry`, so the
    model driving the seeded arm's next iteration was told the wrong thing
    about what happened to its last probe - the signal FR-16 exists to carry.
    Fixture: a throwaway `loop.db`. Tier 0.
    """
    run = mini_campaign(tmp_path)
    rows = run["store"].query(
        "SELECT probe_result.stopping_stage, probe_result.stopping_reason, "
        "probe_result.build_status FROM probe_result WHERE run_manifest_id = ?",
        (_RUN,))
    assert rows, "the campaign wrote no probe_result row"
    reached = {(row["stopping_stage"], row["stopping_reason"]) for row in rows}
    # The fake stages take some probes to the gate and some down the
    # differential path; no recorded reason is stage 3's classification, which
    # is the whole of W3.
    assert ("gate", "new_bug") in reached, reached
    assert any(stage != "stage_3" for stage, _ in reached), reached
    for row in rows:
        assert row["stopping_reason"] not in (
            "assertion_fired", "not_run", "tool_rejected_input"), row

    # And what the outcome dict said is what the row says, field for field.
    for seed in run["outcome"]["seeds"]:
        for probe in seed["probes"]:
            row = run["store"].query_one(
                "SELECT stopping_stage, stopping_reason FROM probe_result "
                "WHERE probe_id = ?", (probe["probe_id"],))
            assert row["stopping_stage"] == probe["stopping_stage"]
            assert row["stopping_reason"] == probe["stopping_reason"]


def test_T_U_driver_41_the_labelled_set_is_package_data_and_a_refusal_is_written(
        tmp_path: Path):
    """T-U-driver-41 (W-19b #4): the set has a non-test home and the driver reads it.

    New id, W-20b. `run_campaign` called `render_results(store, manifest)` with
    no way to pass FR-10.2's labelled set at all, `_dedup_rates`'s gap fired on
    every run, `ResultsIncomplete` is a bare `Exception` and `main` caught four
    other classes - so a campaign ran both four-hour arm windows and then died
    with a traceback instead of writing its results artefact. The set is now
    package data, which is also the only place `runtime_env` would ship it
    from. Fixture: `circt_bug_loop/data/labelled_pairs.json`. Tier 0.
    """
    # results_module is imported at module scope

    assert results_module.LABELLED_PAIRS.is_file()
    assert results_module.LABELLED_PAIRS.parent.name == "data"
    assert "tests" not in results_module.LABELLED_PAIRS.parts
    pairs = results_module.load_labelled_pairs()
    assert len(pairs) >= 20
    assert {p["label"] for p in pairs} == {"duplicate", "distinct"}
    # W-12: a side is the RECORDED FAILURE and not a candidate id. The set is an
    # external measurement of the project, so the renderer fingerprints it from
    # the file and asks this run's store about none of it.
    assert all(isinstance(p["a"], dict) and isinstance(p["b"], dict) for p in pairs)
    assert all({"candidate_id", "oracle_class", "frame_names"} <= set(p[side])
               for p in pairs for side in ("a", "b"))

    # The driver catches the refusal, writes it down and exits non-zero, with
    # the ledger and the store already complete.
    source = inspect.getsource(bug_loop.run_campaign)
    assert "load_labelled_pairs()" in source
    assert "except results_module.ResultsIncomplete" in source
    assert "results_refused.txt" in source
    assert "return 3" in source

    # And the labelled set no longer causes a refusal on a store that holds no
    # fingerprint for either side, which is every campaign's. That refusal fired
    # at the end of EVERY run and is the one `T-S-regen-01` recorded; the rates
    # now render from the file. The refusal kept is a set that is not there.
    run = mini_campaign(tmp_path)
    for missing in (
            _render_refusals(results_module, run, pairs),
            _render_refusals(results_module, run, None)):
        assert not any("labelled duplicate-pair set names candidates" in m
                       for m in missing), missing
    assert any("none was supplied" in m
               for m in _render_refusals(results_module, run, None))
    assert not any("duplicate-pair set" in m
                   for m in _render_refusals(results_module, run, pairs))


def _render_refusals(results_module, run, pairs) -> list:
    """Every element one render refuses, or the empty list when it renders."""
    try:
        results_module.render_results._chia_original(
            run["store"], run["manifest"], labelled_pairs=pairs)
    except results_module.ResultsIncomplete as refusal:
        return list(refusal.missing)
    return []


def test_T_U_driver_42_the_trailer_names_no_model_that_did_not_run():
    """T-U-driver-42 (W-19b #7, FR-11.6): `Assisted-by:` follows `stages_metered`.

    New id, W-20b. `render_report` read the trailer off
    `manifest.model_ids['triage_report']` in three places, so a
    `--generator recorded` report whose FIRST line says no model turn was made
    still ended `Assisted-by: vertex:gemini-3.8-flash`. Fixture: none. Tier 0.
    """
    from circt_bug_loop.triage_task import assisted_by, assisted_by_model

    live = manifest(args=parsed_args())
    assert live.stages_metered["stage_6"] is True
    assert assisted_by_model(live) == live.model_ids["triage_report"]
    assert assisted_by(live) == f"Assisted-by: {live.model_ids['triage_report']}"

    recorded = manifest(args=parsed_args(generator="recorded"))
    assert recorded.stages_metered["stage_6"] is False
    assert recorded.stages_metered["stage_1"] is False
    assert recorded.stages_metered["stage_2"] is False
    assert recorded.stages_metered["stage_7"] is False
    assert assisted_by_model(recorded) is None
    trailer = assisted_by(recorded)
    assert trailer.startswith("Assisted-by: none")
    assert "gemini" not in trailer and "vertex" not in trailer


def test_T_U_driver_43_only_seeds_on_the_images_pin_are_calibratable():
    """T-U-driver-43 (W-19b #6, FR-02.7): the eligibility rule, and the refusal.

    New id, W-20b. FR-02.7 wants each sampled seed probed at ITS OWN parent
    commit; a run has one image and `probe_execute` runs and hashes that image's
    binaries, so W-19b measured three calibration seeds whose manifest named
    three different commits producing three `build_result` rows that all
    recorded the image's. The rule is the pin: a seed is eligible exactly when
    its parent's `llvm` gitlink is the run's, because only then can the image's
    own SDK build that parent (FR-03.2's own equality).

    Fixture: none; three constructed seeds. Tier 0.
    """
    pin, other = "1" * 40, "2" * 40
    mine = seed_record("a" * 40)
    mine.llvm_pin, mine.sdk_exact = pin, True
    inexact = seed_record("b" * 40)
    inexact.llvm_pin, inexact.sdk_exact = pin, False
    elsewhere = seed_record("c" * 40)
    elsewhere.llvm_pin, elsewhere.sdk_exact = other, True

    eligible, excluded = bug_loop.calibratable([mine, inexact, elsewhere], pin)
    assert eligible == ["a" * 40]
    assert excluded == ["b" * 40, "c" * 40]
    assert bug_loop.NOT_CALIBRATABLE == "not_calibratable_in_deployment"
    # The empty case, which is this corpus's: 0 of 187 measured 2026-09-15.
    assert bug_loop.calibratable([mine, inexact, elsewhere], "9" * 40) == (
        [], ["a" * 40, "b" * 40, "c" * 40])

    # And the draw is FROM the eligible set, refusing rather than sampling seeds
    # no deployment can probe at their own commit.
    with pytest.raises(ValueError) as raised:
        bug_loop.draw_calibration(corpus_head_sha="d7e9", sample_size=20,
                                  exact_pin_shas=eligible)
    assert "eligible" in str(raised.value)

    # The driver refuses a calibration run whose registered sample is all
    # ineligible, by name and with both counts.
    source = inspect.getsource(bug_loop.run_campaign)
    assert 'PreflightFailed(\n            "calibration_sample"' in source
    assert "NOT_CALIBRATABLE" in source


@pytest.mark.t0
def test_T_U_driver_44_the_pilots_seed_subset_is_named_ordered_and_refusable():
    """T-U-driver-44 (W-18): `--seed-sha` narrows the DRIVEN list and nothing else.

    New id, W-18. A pilot runs a short window over seeds it was designed around,
    and taking the corpus's own first twelve would measure whichever seeds
    `build_corpus` happens to order first. The subset is the named SHAs in the
    named order, a repeat is one seed, and a SHA the corpus does not hold
    REFUSES the run - a pilot that silently drove eleven of twelve would report
    eleven as though twelve had been asked for. Fixture: three `SeedRecord`s
    built here. Tier 0.
    """
    first, second, third = (seed_record("a" * 40), seed_record("b" * 40),
                            seed_record("c" * 40))
    mined = [first, second, third]

    # The named order wins over the corpus's, and a repeat is one seed.
    subset = bug_loop.seed_subset(mined, ["c" * 40, "a" * 40, "c" * 40], "d" * 40)
    assert [seed.seed_sha for seed in subset] == ["c" * 40, "a" * 40]
    assert mined == [first, second, third], "the mined corpus is not narrowed"

    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.seed_subset(mined, ["a" * 40, "9" * 40], "d7e94049" + "0" * 32)
    assert raised.value.check == "seed_subset"
    assert "9" * 40 in str(raised.value) and "d7e94049" in str(raised.value)

    # The flag itself: repeatable, absent by default, and printed by --print-config.
    parsed = bug_loop.build_parser().parse_args(
        ["--mode", "discovery", "--seed-sha", "a" * 40, "--seed-sha", "b" * 40])
    assert parsed.seed_sha == ["a" * 40, "b" * 40]
    assert bug_loop.build_parser().parse_args(["--mode", "discovery"]).seed_sha is None
    assert bug_loop.resolved_config(parsed)["seed_sha"] == ["a" * 40, "b" * 40]
