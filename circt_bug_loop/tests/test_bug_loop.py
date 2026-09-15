"""`bug_loop.py`: argv, the twelve pre-flight refusals, the manifest, the loop."""
import hashlib
import dataclasses
import inspect
import json
import os
import socket
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

# `-W error` turns FastMCP's own IncompleteFieldDefinitionWarning into an error on every ChiaTool construction.
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
    """A throwaway repository whose `budget.yaml` commit carries the registration tag."""
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
    # The set `budget.MUTATOR_SET` resolves to, not a spelled version.
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


def test_T_U_driver_01(tmp_path: Path):
    """T-U-driver-01 (FR-14.2): check 1 accepts a registered file, refuses a later one."""
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
    """T-U-driver-02 (FR-05.2): check 2 refuses a set the registration tag cannot reach."""
    repo = registered_repo(tmp_path, mutator_after=True)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_02_mutator_set_earlier(
            repo_root=str(repo), flow_dir=str(repo / "circt_bug_loop"))
    assert raised.value.check == "mutator_set_earlier"

    # An unregistered repository has nothing to be earlier than.
    untagged = registered_repo(tmp_path / "untagged", mutator_after=True, tag=None)
    bug_loop.check_02_mutator_set_earlier(
        repo_root=str(untagged), flow_dir=str(untagged / "circt_bug_loop"))


def test_T_U_driver_03():
    """T-U-driver-03 (FR-01.11): check 3 names both SHAs on a difference."""
    bug_loop.check_03_clone_head(clone_path="/clone", corpus_head_sha="a" * 40,
                                 head_sha="a" * 40)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_03_clone_head(clone_path="/clone", corpus_head_sha="a" * 40,
                                     head_sha="b" * 40)
    assert "a" * 40 in str(raised.value) and "b" * 40 in str(raised.value)


def test_T_U_driver_04(tmp_path: Path):
    """T-U-driver-04 (FR-17.9): check 4 refuses a missing, an empty and an unwritable root."""
    bug_loop.check_04_artefact_root_head(artefact_root=str(tmp_path))
    for root in ("", str(tmp_path / "absent")):
        with pytest.raises(bug_loop.PreflightFailed) as raised:
            bug_loop.check_04_artefact_root_head(artefact_root=root)
        assert raised.value.check == "artefact_root_head"


def test_T_U_driver_05(tmp_path: Path):
    """T-U-driver-05 (FR-17.9): check 5 names the worker and the path, as `artefact_root_unmounted`."""
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
    """T-U-driver-06 (FR-03.17): check 6 refuses an image whose lit discovery failed."""
    bug_loop.check_06_image_lit_discovery(image_spec=image_spec("ok"))
    for spec in (None, image_spec("lit_broken")):
        with pytest.raises(bug_loop.PreflightFailed) as raised:
            bug_loop.check_06_image_lit_discovery(image_spec=spec)
        assert raised.value.check == "image_lit_discovery"


def test_T_U_driver_07():
    """T-U-driver-07 (FR-06.1): check 7 names the worker, the tool and both hashes."""
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
    """T-U-driver-08 (FR-03.15): check 8 refuses a changed Verilator, naming both."""
    spec = image_spec("ok")
    bug_loop.check_08_verilator_version(
        image_spec=spec, observed={"bugloop_circt": spec.verilator_version})
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_08_verilator_version(
            image_spec=spec, observed={"bugloop_circt": "Verilator 5.030"})
    assert "5.030" in str(raised.value)
    assert spec.verilator_version in str(raised.value)


def test_T_U_driver_09():
    """T-U-driver-09 (FR-02.1 to FR-02.4): check 9 requires all seven pin fields."""
    assert set(bug_loop.PIN_FIELDS) == set(_PIN) - {"resolved_utc"}
    bug_loop.check_09_pin_stamped(pin=_PIN)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_09_pin_stamped(pin={**_PIN, "pin_tag": None})
    assert "pin_tag" in str(raised.value)


def test_T_U_driver_10():
    """T-U-driver-10 (FR-10.9): check 10 refuses no mirror and an incomplete one."""
    bug_loop.check_10_issue_mirror(mirror=_MIRROR, refresh_requested=False)
    with pytest.raises(bug_loop.PreflightFailed):
        bug_loop.check_10_issue_mirror(mirror=None, refresh_requested=False)
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_10_issue_mirror(
            mirror={**_MIRROR, "incomplete_reason": "GithubRequestError"},
            refresh_requested=True)
    assert "GithubRequestError" in str(raised.value)


def test_T_U_driver_11():
    """T-U-driver-11 (FR-20.1): check 11 records the forum post and refuses nothing; the first filing is where the post is required."""
    assert bug_loop.check_11_forum_post(forum_post_url="https://x/1",
                                        forum_post_date="2026-09-18") == "posted"
    assert bug_loop.check_11_forum_post(forum_post_url=None, forum_post_date="2026-09-18",
                                        filings_total=10) == "unposted"
    assert bug_loop.check_11_forum_post(forum_post_url=None, forum_post_date=None,
                                        filings_total=0) == "exempt"
    source = inspect.getsource(bug_loop.run_campaign)
    assert "filings_total=budget.filings_total" in source
    assert "required at approval" in bug_loop.NO_FORUM_POST
    manifest = inspect.getsource(bug_loop.build_manifest)
    assert "forum_post_url=args.forum_post_url or NO_FORUM_POST" in manifest
    assert "forum_post_date=args.forum_post_date or NO_FORUM_POST" in manifest


def test_T_U_driver_27():
    """T-U-driver-27 (NFR-06): check 12, the interlock and the key."""
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

    # W-18: the head is checked only where a turn would be BUILT there.
    unset = bug_loop.interlock_probe(env={})
    bug_loop.check_12_live_model(workers={"bugloop_llm": probe})
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_12_live_model(head=unset, workers={"bugloop_llm": probe})
    assert "head" in str(raised.value)
    # And an empty worker map is a refusal and not a pass.
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_12_live_model(workers={})
    assert "llm" in str(raised.value)
    # The driver decides by asking Ray, not by a flag.
    assert "head=None if ray.is_initialized() else interlock_probe()" in \
        inspect.getsource(bug_loop.run_campaign)


def test_T_U_driver_28a():
    """T-U-driver-28 (13.1): the checks are named functions, in order."""
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


def test_T_U_driver_12():
    """T-U-driver-12 (FR-19.3): every argument of 13.1's table parses with its default."""
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
    """T-U-driver-13 (FR-19.3): one flag swaps the arm, and `both` is sequential."""
    for arm in ("seeded", "mutation", "both"):
        assert bug_loop.build_parser().parse_args(
            ["--mode", "discovery", "--arm", arm]).arm == arm
    assert budget_file().arm_order == ["seeded", "mutation"]


def test_T_U_driver_17(tmp_path):
    """T-U-driver-17 (FR-12.1): `runtime_env` ships the STAGED package."""
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
    """T-U-driver-17 (K7): checks 13 and 14 read the staged files."""
    unpatched = tmp_path / "issue_task.py"
    unpatched.write_text("def _turn():\n    pass\n", encoding="utf-8")
    patched = tmp_path / "patched.py"
    patched.write_text(
        f"    {bug_loop.VERTEX_BRANCH}\n"
        + "".join(f"        {bound}'x']\n" for bound in bug_loop.VERTEX_BRANCH_BOUNDS),
        encoding="utf-8")
    # W-18d: the branch without its two bounds is a stale staging, not a run.
    stale = tmp_path / "stale.py"
    stale.write_text(f"    {bug_loop.VERTEX_BRANCH}\n", encoding="utf-8")

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
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.check_13_vertex_branch(issue_task_path=str(stale),
                                        repair_backend="vertex",
                                        repair_enabled=True)
    assert raised.value.check == "vertex_branch"
    assert "turn_budget_usd" in str(raised.value)

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
    """T-U-driver-23 (FR-19.3): `--print-config` prints both databases and no secret."""
    status = bug_loop.main(["--mode", "discovery", "--print-config"])
    printed = capsys.readouterr().out
    assert status == 0
    config = json.loads(printed)
    assert config["loop_db"].endswith("loop.db")
    assert config["issues_db"].endswith("issues.db")
    for key in (bug_loop.API_KEY_ENV, bug_loop.LIVE_MODEL_ENV, "GITHUB_TOKEN"):
        assert key not in printed


def test_T_U_driver_21():
    """T-U-driver-21 (FR-14.1): the calibration draw is reproducible and writes nothing."""
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


def test_T_U_driver_24():
    """T-U-driver-24 (FR-03.7): the tag, and the digest beside it."""
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
    # The five inputs other than the commit share a tag and differ in the digest.
    assert bug_loop.image_tag(bug_loop.image_manifest(**base, slang=False)) == tag


def test_T_U_driver_24b(monkeypatch):
    """T-U-driver-24 (K1): B1 is a head node, it never pushes, and --dry-run inspects."""
    from circt_bug_loop.bug_loop import ImageBuildError

    assert bug_loop.build_image._chia_options == {"max_retries": 0}
    assert "circt_bug_loop.bug_loop.build_image" in bug_loop.HEAD_NODES
    # Read off the parsed body and not the text, the docstring naming the step that was removed.
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

    # And the Dockerfile it would have built from exists in THIS tree.
    dockerfile, context = bug_loop.dockerfile_and_context()
    assert Path(dockerfile).is_file()
    assert dockerfile == str(Path(bug_loop.FLOW_DIR).parent / "upstream"
                             / "dockerfiles" / bug_loop.DOCKERFILE_NAME)
    assert context == str(Path(bug_loop.FLOW_DIR).parent)


def test_T_U_driver_25a():
    """T-U-driver-25 (FR-03.4): step 2's argument list, and no `--progress=plain`."""
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
    """T-U-driver-25 (FR-03.17): step 4 reads FR-03.17's two figures off lit's own output."""
    shown = (FIXTURES / "image" / "lit_show_tests.txt").read_text(encoding="utf-8")
    notes = (FIXTURES / "image" / "lit_notes.txt").read_text(encoding="utf-8")
    ok, count = bug_loop.lit_discovery(0, notes + shown)
    assert ok is True and count == 1390
    assert bug_loop.lit_discovery(1, notes + shown)[0] is False
    fatal = (FIXTURES / "image" / "lit_fatal.txt").read_text(encoding="utf-8")
    assert bug_loop.lit_discovery(0, fatal)[0] is False


def manifest(**overrides) -> schema.RunManifest:
    """One built `RunManifest`, from the producers 13.1's table names."""
    args = overrides.pop("args", None) or parsed_args()
    return bug_loop.build_manifest(
        args=args, budget=overrides.pop("budget", None) or budget_file(),
        pin=_PIN, image_spec=image_spec("ok"), mirror=_MIRROR, cluster=_CLUSTER,
        mutator_set_sha="1" * 64, run_manifest_id=_RUN,
        started_utc="2026-09-19T00:00:00+00:00", **overrides)


def test_T_U_driver_28b():
    """T-U-driver-28 (FR-14.8): every manifest field comes from its named producer."""
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


def test_T_U_driver_28b_the_generator_side_holds_no_circt_slot():
    """T-U-driver-28 (FR-04.4): A3 and its writer actor are off the `circt` pool - one slot held for a whole seed iteration is what wedged campaign 2's gate re-run."""
    from circt_bug_loop import generate_task

    cfg = bug_loop.generator_cfg(manifest(), budget_file(), clone_path="/clone",
                                 iteration=0)
    assert cfg["here_options"] == bug_loop.HERE_OPTIONS == {"num_cpus": 0}
    assert cfg["here_options"] is not bug_loop.HERE_OPTIONS, "the caller gets a copy"
    assert "circt" not in cfg["here_options"].get("resources", {})
    assert generate_task.generate_seeded._chia_options == {"max_retries": 0}
    assert "circt_bug_loop.generate_task.generate_seeded" in bug_loop.HEAD_NODES
    assert bug_loop.generate_recorded_seeded._chia_options == {"max_retries": 0}


def test_T_U_driver_28c():
    """T-U-driver-28 (FR-14.8): `stages_metered` follows the arm and the repair backend."""
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
    """T-U-driver-28 (FR-02.7): `run_commit` is one entry per mode, not one shape."""
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
    """T-U-driver-29 (12.1): the cluster YAML produces four manifest fields."""
    monkeypatch.setenv("CHIA_HEAD", "127.0.0.1")
    monkeypatch.setenv("BUGLOOP_ARTEFACTS", str(tmp_path))
    monkeypatch.setenv("BUGLOOP_IMAGE_TAG", "deadbeefcafe")
    monkeypatch.setenv("USER", "tester")
    summary = bug_loop.cluster_summary(str(bug_loop.FLOW_DIR / "cluster_single.yaml"))
    assert summary["worker_type"] == "bugloop_circt"
    assert summary["apparatus_concurrency"] == 2 and summary["llm_concurrency"] == 2
    assert summary["deployment"] == "single_machine"
    assert len(summary["cluster_yaml_sha"]) == 64


def test_T_U_driver_20(tmp_path: Path):
    """T-U-driver-20 (FR-17.4): four counters, no fifth, two nodes of one stage sum."""
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


def test_T_U_driver_15(tmp_path: Path):
    """T-U-driver-15 (FR-04.3): every recorded instance is validated first and named by its id."""
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


def test_T_U_driver_18(tmp_path: Path):
    """T-U-driver-18 (FR-12.10): a loop repair row with no CHIA counterpart is marked."""
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


def probe_spec(probe_id: str, arm: str = "seeded", **overrides) -> schema.ProbeSpec:
    """One `ProbeSpec` a fake generator returns, valid at the seam on either arm."""
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
    """Ten stand-in stages: the sequencing is real and the tools are not."""
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
        # The recorded stderr of a real firing and a real clean exit, classified by the real `classify_build`.
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
        # B6b's own three rows, through B6b's own writer.
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
                 "fixing_commit", "post_pin_file_touches", "rescreened_from")))
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
             *, limits, top_n, bin_dir, minimal_case_lines):
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
    """Drive one whole campaign into a throwaway `loop.db`, with no Ray."""
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
            # FR-10.2's labelled set is the project's own external measurement (W-12).
            "labelled_pairs": results_module.load_labelled_pairs()}


def test_T_U_driver_30(tmp_path: Path, capsys):
    """T-U-driver-30 (FR-14.5): one whole iteration, both arms, no Ray."""
    run = mini_campaign(tmp_path)
    loop, outcome, counters = run["store"], run["outcome"], run["counters"]

    # Both arms ran, in budget.yaml's order, one after the other.
    assert list(outcome["arms"]) == ["seeded", "mutation"]
    assert all(a["started"] for a in outcome["arms"].values())
    assert all(a["stop_reason"] == "seed_set_exhausted"
               for a in outcome["arms"].values())

    # One seed record per arm.
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
    """T-U-driver-31 (FR-18.10): the window stops an arm, and the USD cap stops both."""
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


def test_T_U_driver_32(tmp_path: Path):
    """T-U-driver-32 (FR-17.2): the driver's own store renders."""
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
    # FR-18.11: nothing is MARKED.
    assert "**MARKED**" not in rendered


def test_T_U_driver_33(tmp_path: Path):
    """T-U-driver-33 (FR-17.2): every table of §6.4, in its order."""
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

    # The differential candidates are report-only.
    differential = loop.query(
        "SELECT c.candidate_id, r.template FROM candidate c "
        "JOIN report r USING (candidate_id) WHERE c.oracle_class = 'differential'")
    assert len(differential) == 2
    assert {row["template"] for row in differential} == {"differential"}
    assert loop.query_one(
        "SELECT COUNT(*) AS n FROM gate_decision g JOIN candidate c "
        "USING (candidate_id) WHERE c.oracle_class = 'differential'")["n"] == 0

    # §6.4 rule 4: the gate's decision and the candidate's bucket agree.
    for row in loop.query("SELECT g.taxonomy_bucket AS gated, c.taxonomy_bucket "
                          "AS carried FROM gate_decision g "
                          "JOIN candidate c USING (candidate_id)"):
        assert row["gated"] == row["carried"] == "new_bug"

    # FR-17.8: the marker is gone from every probe directory that completed.
    for row in loop.query("SELECT artefact_dir FROM probe_result"):
        assert Path(row["artefact_dir"]).is_dir()
        assert not (Path(row["artefact_dir"]) / "PARTIAL").exists()
    # A5's bundle is on disk at the path its row carries.
    for row in loop.query("SELECT path FROM feedback"):
        assert Path(row["path"]).is_file()
        assert not (Path(row["path"]).parent / "PARTIAL").exists()
    stage_3 = loop.query("SELECT arm, amount FROM ledger_entry "
                         "WHERE scope = 'stage' AND stage = 'stage_3'")
    assert len(stage_3) == 4 and {row["arm"] for row in stage_3} == {"seeded",
                                                                     "mutation"}
    # A3 is one node and two stages.
    assert loop.query_one("SELECT COUNT(*) AS n FROM ledger_entry "
                          "WHERE scope = 'stage' AND stage = 'stage_1'")["n"] == 2
    assert loop.query_one("SELECT stage FROM ledger_entry WHERE arm = 'shared' "
                          "AND stage = 'synthesis'")["stage"] == "synthesis"


def test_T_U_driver_34(tmp_path: Path, monkeypatch):
    """T-U-driver-34 (FR-17.3): under Ray every write goes through the node."""
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
    # The column cache is per process and the schema is fixed, so a later store reuses an earlier one's read.
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
    """T-U-driver-35 (FR-12.10): the loop's repair row before CHIA's."""
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

    # A repair that never came back leaves the row it opened.
    refused_root = tmp_path / "refused"
    refused_root.mkdir()
    other = mini_campaign(refused_root, repair_enabled=True)
    refused = other["store"].query_one("SELECT status, chia_row_seen FROM repair")
    assert refused["status"] == "dispatched" and refused["chia_row_seen"] == 0


def test_T_U_driver_36_the_spend_guard_is_wired_and_stops_the_arm(tmp_path: Path):
    """T-U-driver-36 (W1): the pre-authorisation reaches the turn, and binds."""
    from circt_bug_loop.llm import SpendCapRefused, SpendGuard

    seen = []

    def generate(seed, feedback, remaining, cfg):
        guard = cfg["spend_guard"]
        seen.append({"iteration": cfg["iteration"], "guard": guard,
                     "snapshot_spent": remaining.spent})
        # What A3 does with a refusal: FR-04.8's blanket catch records it.
        try:
            guard.authorise({"prompt": "x" * 3000, "system_message": "",
                             "tools": [object()],
                             "max_tool_iterations": cfg["max_tool_iterations"]
                             ["stage_2"]})
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
    assert (guard.in_flight_usd, guard.settled_usd) == (0.0, 0.0)
    # D-5: the driver keeps no second sum of its own — the ledger's is the bill
    # `accrue` priced from the turn's own tokens, the guard's is settled plus in
    # flight, and `_spend_refused` only reads the failure the generator recorded.
    assert bug_loop._spend_refused("turn_failed:SpendCapRefused") is True
    assert bug_loop._spend_refused("turn_failed:PromptContractError") is False


def test_a_failed_generator_turn_is_kept_on_the_seed_record(tmp_path: Path):
    """D-1 (pilot 4): the driver keeps what the generator caught, under the stage that raised."""
    def generate(seed, feedback, remaining, cfg):
        return {"specs": [], "logs": {"wall_seconds": {"seed_read": 71.5,
                                                       "probe_write": 0.2}},
                "counters": schema.CounterBlock(stage="stage_2", started=1,
                                                completed=0, failed=1, seconds=0.3),
                "failure": "turn_failed:MaxOutputTokensError",
                "failure_detail": "MaxOutputTokensError: response truncated"}

    stages = dataclasses.replace(fake_stages(), generate_seeded=generate,
                                 generate_mutation=generate)
    run = mini_campaign(tmp_path, stages=stages)

    record = run["outcome"]["seeds"][0]
    assert record["verdicts"] == {"stage_2": {
        "failure": "turn_failed:MaxOutputTokensError",
        "failure_detail": "MaxOutputTokensError: response truncated"}}
    assert record["terminating_condition"] == "no_probe_written"
    # A turn that raised before stage 2 started is filed under stage 1.
    assert bug_loop._failed_stage({"wall_seconds": {"seed_read": 71.5}}) == "stage_1"

    # D-3 (pilot 5): and the store keeps it, so `results.md` can count it.
    rows = run["store"].query("SELECT * FROM turn_failure ORDER BY arm")
    assert [r["arm"] for r in rows] == ["mutation", "seeded"]
    for row in rows:
        assert row["run_manifest_id"] == run["manifest"].run_manifest_id
        assert row["seed_sha"] == run["seed"].seed_sha
        assert row["iteration"] == 1 and row["stage"] == "stage_2"
        assert row["kind"] == "turn_failed:MaxOutputTokensError"
        assert row["detail"] == "MaxOutputTokensError: response truncated"


def test_a_stale_seed_names_itself_and_takes_no_probe(tmp_path: Path):
    """Pilot 4 D-2: the arm stops on the seed, under its own terminating condition."""
    def generate(seed, feedback, remaining, cfg):
        assert "probe_limits" in cfg and cfg["bin_dir"], "A4 can run the seed's test"
        return {"specs": [], "logs": {},
                "counters": schema.CounterBlock(stage="stage_2", started=0,
                                                completed=0, failed=0, seconds=0.1),
                "failure": bug_loop.STALE_AT_BUILD,
                "failure_detail": "circt-opt rejects this seed's own test"}

    stages = dataclasses.replace(fake_stages(), generate_mutation=generate)
    run = mini_campaign(tmp_path, stages=stages)

    mutation, = [s for s in run["outcome"]["seeds"] if s["arm"] == "mutation"]
    assert mutation["terminating_condition"] == bug_loop.STALE_AT_BUILD
    assert mutation["probes"] == []
    assert mutation["verdicts"]["stage_2"]["failure"] == bug_loop.STALE_AT_BUILD
    # The seeded arm is untouched by its sibling's staleness.
    seeded, = [s for s in run["outcome"]["seeds"] if s["arm"] == "seeded"]
    assert seeded["terminating_condition"] == "iteration_cap"

    # D-3 (pilot 5): the stale seed is a row of its own, and the arm that ran
    # writes none - `results.md` is built from the store and not from `outcome`.
    rows = run["store"].query("SELECT * FROM turn_failure")
    assert [(r["arm"], r["kind"]) for r in rows] == [
        ("mutation", bug_loop.STALE_AT_BUILD)]
    assert rows[0]["detail"] == "circt-opt rejects this seed's own test"


def test_T_U_driver_37_the_snapshot_is_rebuilt_every_iteration(tmp_path: Path):
    """T-U-driver-37 (W10): each iteration reads its own `LedgerSnapshot`."""
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

    # A seed with no probes ends at `no_probe_written` after one iteration, so the per-arm count here is one.
    source = inspect.getsource(bug_loop.drive_seed)
    body = source.split("for iteration in range")[1]
    assert "budget_module.snapshot(" in body, (
        "the snapshot is built inside the iteration loop (W10)")
    assert "budget_module.snapshot(" not in source.split("for iteration in range")[0]
    assert handed and all(s.arm in ("seeded", "mutation") for s in handed)
    assert len({id(s) for s in handed}) == len(handed), "one object per iteration"


def test_T_U_driver_38_checks_seven_and_eight_ask_the_workers(tmp_path: Path):
    """T-U-driver-38 (FR-06.1): the observations are the workers' own."""
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

    # A tool the worker cannot read leaves no entry.
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

    # And the cluster YAML says WHICH types are asked.
    cluster = bug_loop.cluster_summary(str(Path(bug_loop.FLOW_DIR)
                                           / "cluster_single.yaml"))
    assert cluster["image_worker_types"] == ["bugloop_circt", "bugloop_repair"]
    assert "bugloop_llm" not in cluster["image_worker_types"]


def test_T_U_driver_39_recorded_mode_needs_no_credential(monkeypatch, capsys):
    """T-U-driver-39 (W4): `--generator recorded` skips check 12 entirely."""
    import inspect as _inspect

    source = _inspect.getsource(bug_loop.run_campaign)
    guarded = source.split('if args.generator == "recorded":')[1]
    assert "check_12_live_model" not in guarded.split("else:")[0]
    assert "check_12_live_model" in guarded.split("else:")[1]
    # And `repair_enabled` is already false in the mode.
    args = bug_loop.build_parser().parse_args(
        ["--mode", "discovery", "--generator", "recorded"])
    assert bug_loop.repair_enabled(args) is False
    assert bug_loop.resolved_config(args)["repair_enabled"] is False


def test_T_U_driver_40_the_probe_record_carries_the_reason_it_stopped(tmp_path: Path):
    """T-U-driver-40 (FR-16): `stopping_reason` is the PROBE's, not stage 3's."""
    run = mini_campaign(tmp_path)
    rows = run["store"].query(
        "SELECT probe_result.stopping_stage, probe_result.stopping_reason, "
        "probe_result.build_status FROM probe_result WHERE run_manifest_id = ?",
        (_RUN,))
    assert rows, "the campaign wrote no probe_result row"
    reached = {(row["stopping_stage"], row["stopping_reason"]) for row in rows}
    # The fake stages take some probes to the gate and some down the differential path.
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
    """T-U-driver-41 (W-19b #4): the set has a non-test home and the driver reads it."""
    # results_module is imported at module scope

    assert results_module.LABELLED_PAIRS.is_file()
    assert results_module.LABELLED_PAIRS.parent.name == "data"
    assert "tests" not in results_module.LABELLED_PAIRS.parts
    pairs = results_module.load_labelled_pairs()
    assert len(pairs) >= 20
    assert {p["label"] for p in pairs} == {"duplicate", "distinct"}
    # W-12: a side is the RECORDED FAILURE and not a candidate id.
    assert all(isinstance(p["a"], dict) and isinstance(p["b"], dict) for p in pairs)
    assert all({"candidate_id", "oracle_class", "frame_names"} <= set(p[side])
               for p in pairs for side in ("a", "b"))

    # The driver catches the refusal.
    source = inspect.getsource(bug_loop.run_campaign)
    assert "load_labelled_pairs()" in source
    assert "except results_module.ResultsIncomplete" in source
    assert "results_refused.txt" in source
    assert "return 3" in source

    # And the labelled set no longer causes a refusal on a store that holds no fingerprint for either side.
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
    """T-U-driver-42 (W-19b #7, FR-11.6): `Assisted-by:` follows `stages_metered`."""
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
    """T-U-driver-43 (W-19b #6, FR-02.7): the eligibility rule, and the refusal."""
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

    # And the draw is FROM the eligible set.
    with pytest.raises(ValueError) as raised:
        bug_loop.draw_calibration(corpus_head_sha="d7e9", sample_size=20,
                                  exact_pin_shas=eligible)
    assert "eligible" in str(raised.value)

    # The driver refuses a calibration run whose registered sample is all ineligible.
    source = inspect.getsource(bug_loop.run_campaign)
    assert 'PreflightFailed(\n            "calibration_sample"' in source
    assert "NOT_CALIBRATABLE" in source


@pytest.mark.t0
def test_T_U_driver_44_the_pilots_seed_subset_is_named_ordered_and_refusable():
    """T-U-driver-44 (W-18): `--seed-sha` narrows the DRIVEN list and nothing else."""
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


@pytest.mark.t0
def test_T_U_driver_45_the_corpus_window_opens_two_years_before_the_head(tmp_path):
    """T-U-driver-45 (FR-01.1): `since` is the head's date, two years back."""
    repo = tmp_path / "clone"
    repo.mkdir()
    git = ("git", "-C", str(repo))
    subprocess.run(git + ("init", "-q", "-b", "main"), check=True)
    (repo / "a.txt").write_text("x", encoding="utf-8")
    subprocess.run(git + ("add", "-A"), check=True)
    subprocess.run(git + ("-c", "user.name=t", "-c", "user.email=t@t",
                          "commit", "-q", "-m", "one"), check=True,
                   env={**os.environ, "GIT_AUTHOR_DATE": "2026-09-11T10:36:10+02:00",
                        "GIT_COMMITTER_DATE": "2026-09-11T10:36:10+02:00"})
    head = subprocess.run(git + ("rev-parse", "HEAD"), check=True,
                          capture_output=True, text=True).stdout.strip()

    # The committed corpus head's own window, which is `test_corpus.py`'s SINCE.
    assert bug_loop.corpus_since(str(repo), head) == "2024-09-11"
    assert bug_loop.CORPUS_WINDOW_MONTHS == 24

    # And it is NOT the campaign start, which is what the driver used to pass.
    document = yaml.safe_load(
        Path(budget_module.BUDGET_YAML).read_text(encoding="utf-8"))
    assert document["campaign_start_utc"][:10] > "2024-09-11"
    source = inspect.getsource(bug_loop.run_campaign)
    assert "corpus_since(args.clone, budget.corpus_head_sha)" in source
    assert "budget.campaign_start_utc[:10]" not in source


def test_T_U_driver_46_a_stale_ray_cluster_file_is_removed(tmp_path, monkeypatch):
    """T-U-driver-46 (errata row 37): pre-flight clears what a `chia down` left."""
    monkeypatch.setattr(bug_loop.ray, "is_initialized", lambda: False)
    stale = tmp_path / "ray_current_cluster"

    assert bug_loop.clear_stale_ray_cluster(str(stale)) is None, "no file, no error"

    # A port nothing listens on.
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    dead_port = probe.getsockname()[1]
    probe.close()
    stale.write_text(f"127.0.0.1:{dead_port}\n")
    assert bug_loop.clear_stale_ray_cluster(str(stale)) == f"127.0.0.1:{dead_port}"
    assert not stale.exists()

    # A cluster that answers is load-bearing while it is true.
    live = socket.socket()
    live.bind(("127.0.0.1", 0))
    live.listen(1)
    try:
        stale.write_text(f"127.0.0.1:{live.getsockname()[1]}")
        assert bug_loop.clear_stale_ray_cluster(str(stale)) is None
        assert stale.exists()
    finally:
        live.close()

    # And nothing is removed from under a driver that has already joined one.
    monkeypatch.setattr(bug_loop.ray, "is_initialized", lambda: True)
    stale.write_text(f"127.0.0.1:{dead_port}")
    assert bug_loop.clear_stale_ray_cluster(str(stale)) is None
    assert stale.exists()

    # The pre-flight calls it, and calls it BEFORE ray.init (13.1).
    source = inspect.getsource(bug_loop.run_campaign)
    assert source.index("clear_stale_ray_cluster()") < source.index('ray.init(address="auto"')
    assert bug_loop.RAY_CURRENT_CLUSTER == "/tmp/ray/ray_current_cluster"


def test_T_U_driver_29_stage_seven_runs_only_for_a_new_candidate():
    """T-U-driver-29 (W-18d): the screen's verdict gates the loop's costliest stage."""
    class _Campaign:
        repair_enabled = True

    def _dedup(verdict):
        return DedupVerdict(probe_id="p", verdict=verdict, evidence={})

    for verdict in ("duplicate_of_candidate", "known_open_issue",
                    "known_closed_issue", "fixed_post_pin", "dedup_unavailable"):
        out, result = {"verdicts": {}, "stages": []}, _Stopping()
        assert bug_loop._drive_repair(_Campaign(), None, None, None, None,
                                      _dedup(verdict), {}, out, result) is None
        assert out["verdicts"]["stage_7"] == f"skipped:{verdict}"
        # A stage that did not run is not an occupancy and does not stop the probe.
        assert out["stages"] == [] and result.stopping_stage == "stage_6"

    # --no-repair is still the earlier and quieter refusal: no verdict at all.
    class _NoRepair(_Campaign):
        repair_enabled = False

    out = {"verdicts": {}, "stages": []}
    assert bug_loop._drive_repair(_NoRepair(), None, None, None, None,
                                  _dedup("new"), {}, out, _Stopping()) is None
    assert out["verdicts"] == {}


class _Stopping:
    """Whatever `_drive_repair` records its stopping stage on."""

    def __init__(self):
        self.stopping_stage = "stage_6"


@pytest.mark.t0
def test_T_U_driver_39_the_corpus_shards_partition_the_seed_set():
    """W-23: `--shard K/N` keeps every Nth seed and the shards lose nobody."""
    from types import SimpleNamespace

    seeds = [SimpleNamespace(seed_sha=f"{n:040x}") for n in range(11)]

    assert bug_loop.parse_shard(None) is None
    assert bug_loop.parse_shard("") is None
    assert bug_loop.parse_shard("2/5") == (2, 5)

    # The identity, and the partition.
    assert bug_loop.seed_shard(seeds, None) == seeds
    assert bug_loop.seed_shard(seeds, bug_loop.parse_shard("0/1")) == seeds
    shards = [bug_loop.seed_shard(seeds, (k, 3)) for k in range(3)]
    assert [len(s) for s in shards] == [4, 4, 3]
    assert sorted((s.seed_sha for shard in shards for s in shard)) == \
        sorted(s.seed_sha for s in seeds)
    for first, second in ((0, 1), (0, 2), (1, 2)):
        assert not ({s.seed_sha for s in shards[first]}
                    & {s.seed_sha for s in shards[second]})
    # Position in the FIXED corpus order, not a hash of the sha.
    assert [s.seed_sha for s in shards[1]] == [seeds[i].seed_sha
                                               for i in (1, 4, 7, 10)]

    for bad in ("3/3", "4/3", "-1/3", "1/0", "1", "a/3", "1/b", "1/2/3", "/3"):
        with pytest.raises(bug_loop.PreflightFailed) as raised:
            bug_loop.parse_shard(bad)
        assert raised.value.check == "shard"


@pytest.mark.t0
def test_T_U_driver_40_the_shard_is_on_the_manifest_and_in_the_config():
    """W-23: a sharded run records which shard it drove (contract 2.3)."""
    args = bug_loop.build_parser().parse_args(["--mode", "discovery"])
    assert args.shard is None
    assert bug_loop.resolved_config(args)["shard"] is None
    sharded = bug_loop.build_parser().parse_args(
        ["--mode", "discovery", "--shard", "1/4"])
    assert sharded.shard == "1/4"
    assert bug_loop.resolved_config(sharded)["shard"] == "1/4"

    fields = {f.name for f in dataclasses.fields(schema.RunManifest)}
    assert "shard" in fields
    contract_fixtures = Path(schema.__file__).resolve().parent / "fixtures"
    manifest = schema.from_json(
        (contract_fixtures / "run_manifest" / "discovery_01.json").read_text(
            encoding="utf-8"), schema.RunManifest)
    assert manifest.shard is None
    schema.validate(dataclasses.replace(manifest, shard="1/4"))


def _stub_scan(monkeypatch, sha: str, context: str) -> None:
    """One post-pin commit, with the hunk-header context the test wants read."""
    from circt_bug_loop import triage_task

    monkeypatch.setattr(triage_task, "commit_date",
                        lambda *a, **k: "2026-01-01T00:00:00+00:00")
    monkeypatch.setattr(triage_task, "scan_commits",
                        lambda path, since, paths, **k: [
                            {"sha": sha, "date": "2026-02-01T00:00:00+00:00",
                             "contexts": [context]}])


@pytest.mark.t0
def test_T_U_driver_47_rescreen_reruns_the_screen_and_appends_both_rows(
        tmp_path: Path, monkeypatch):
    """T-U-driver-47 (FR-10.4, D-11): `--rescreen` screens a run's candidates again under the current rule, appends a dedup row and a gate row to each, keeps the old ones, and names the reports that are owed a stage-6 turn."""
    import io

    from circt_bug_loop import results as results_module
    from circt_bug_loop import triage_task
    from circt_bug_loop.store import latest

    run = mini_campaign(tmp_path)
    loop, candidate_id = run["store"], "c-p-000000000001"
    sha = "d" * 40
    loop.insert("issue_mirror", {
        "issue_number": 1, "title": "unrelated", "body": "nothing matches here",
        "labels_json": "[]", "state": "open", "url": "u",
        "mirrored_utc": "2026-09-19T00:00:00+00:00"})

    # The state the file-level rule left: both refused, neither report written by a turn.
    evidence = dict.fromkeys(triage_task._EVIDENCE_KEYS)
    evidence["fixing_commit"] = sha
    for refused in (candidate_id, "c-p-100000000001"):
        answers = json.loads(loop.query_one(
            "SELECT answers_json FROM gate_decision WHERE candidate_id = ?",
            (refused,))["answers_json"])
        answers.update(q4_new=False, q4_reason="fixed_post_pin")
        loop.update("dedup_verdict", {"candidate_id": refused},
                    {"verdict": "fixed_post_pin",
                     "evidence_json": json.dumps(evidence, sort_keys=True)})
        loop.update("gate_decision", {"candidate_id": refused},
                    {"answers_json": json.dumps(answers, sort_keys=True),
                     "stopped_at_question": 4, "decision": "nothing",
                     "taxonomy_bucket": "duplicate"})
        loop.update("candidate", {"candidate_id": refused},
                    {"taxonomy_bucket": "duplicate"})
    loop.update("fingerprint", {"candidate_id": candidate_id},
                {"fingerprint_stable": 1})
    report_path = Path(loop.query_one(
        "SELECT path FROM report WHERE candidate_id = ?", (candidate_id,))["path"])
    report_path.write_text(f"{bug_loop.NO_TURN_HEADING} FOR THIS CANDIDATE.\n",
                           encoding="utf-8")
    before = latest(loop, "dedup_verdict", candidate_id)["rowid"]

    # The bump that only touched the file, exactly as ddb3d1bd did.
    _stub_scan(monkeypatch, sha, "void circt::hw::HWModuleOp::somethingElse() {")
    out = io.StringIO()
    assert bug_loop.rescreen(loop, _RUN, clone_path=str(tmp_path), top_n=5,
                             out=out) == 0

    dedups = loop.query("SELECT rowid, * FROM dedup_verdict WHERE candidate_id = ? "
                        "ORDER BY rowid", (candidate_id,))
    assert [row["verdict"] for row in dedups] == ["fixed_post_pin", "new"]
    fresh = json.loads(dedups[-1]["evidence_json"])
    assert fresh["post_pin_file_touches"] == [sha] and fresh["fixing_commit"] is None
    assert fresh["rescreened_from"] == str(before)

    gates = loop.query("SELECT * FROM gate_decision WHERE candidate_id = ? "
                       "ORDER BY rowid", (candidate_id,))
    assert [row["decision"] for row in gates] == ["nothing", "report"]
    assert [row["taxonomy_bucket"] for row in gates] == ["duplicate", "new_bug"]
    reanswered = json.loads(gates[-1]["answers_json"])
    assert (reanswered["q4_new"], reanswered["q4_reason"]) == (True, None)
    assert reanswered["rescreened_from"] == str(before)
    for copied in ("q1_reproduce", "q1_rerun_pid", "q2_minimal", "q3_valid",
                   "q3_stderr_path"):
        assert reanswered[copied] == answers[copied], "questions 1 to 3 are copied"

    # The screen replaces the rows it owns, and neither of these is its own.
    assert loop.query_one("SELECT fingerprint_stable FROM fingerprint "
                          "WHERE candidate_id = ?", (candidate_id,)
                          )["fingerprint_stable"] == 1
    assert loop.query_one("SELECT created_utc FROM candidate WHERE candidate_id = ?",
                          (candidate_id,))["created_utc"] is not None

    printed = out.getvalue()
    assert printed.splitlines()[0].split() == ["candidate", "old", "verdict",
                                               "new", "verdict", "old",
                                               "decision", "new", "decision"]
    row = next(line for line in printed.splitlines() if candidate_id in line)
    assert row.split() == [candidate_id, "fixed_post_pin", "new", "nothing", "report"]
    assert f"{bug_loop.TURN_OWED}: {candidate_id}" in printed

    # FR-18.6 counts the newest row of each, and counts it once: nothing was
    # `new_bug` before the rescreen.
    taxonomy = call_node(results_module.render_results, loop, run["manifest"],
                         labelled_pairs=run["labelled_pairs"])["rendered"]
    assert "| new_bug | 1 |" in taxonomy and "| duplicate | 1 |" in taxonomy


@pytest.mark.t0
def test_T_U_driver_48_rescreen_is_an_argument_of_the_driver(tmp_path: Path):
    """T-U-driver-48 (FR-19.3): `--rescreen` takes a run manifest id, and refuses a run whose candidates the store does not hold."""
    parsed = bug_loop.build_parser().parse_args(
        ["--mode", "discovery", "--rescreen", _RUN])
    assert parsed.rescreen == _RUN
    assert bug_loop.build_parser().parse_args(["--mode", "discovery"]).rescreen is None
    assert bug_loop.rescreen(open_store(tmp_path), _RUN, clone_path=str(tmp_path),
                             top_n=5, out=None) == 2


#: D-13's diagnostic, and the one a PASS writes by hand about a valid input.
_VERIFIER_STDERR = "verifier_error.txt"
_PASS_STDERR = "verifier_error_pass.txt"


class _RecordingDispatch(bug_loop.Dispatch):
    """`Dispatch(remote=False)` that names every node it was asked to run."""

    def __init__(self):
        super().__init__(remote=False)
        self.nodes = []

    def call(self, fn, *args, **kwargs):
        self.nodes.append(getattr(fn, "__name__", str(fn)))
        return super().call(fn, *args, **kwargs)


def _verify_stub(bin_dir: Path) -> str:
    """§4.8's command as a stand-in tool: it refuses an input whose name says so."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    tool = bin_dir / "circt-opt"
    tool.write_text("#!/bin/sh\n"
                    'case "$3" in *invalid*) echo "error: bad" >&2; exit 1 ;; esac\n'
                    "exit 0\n")
    tool.chmod(0o755)
    from circt_bug_loop.probe_task import _sha256

    return _sha256(str(tool))


def _parse_error_run(tmp_path: Path, bin_dir: Path):
    """A stored run of three `parse_error` probes, as campaign 2 left them."""
    loop = open_store(tmp_path)
    built = manifest(args=parsed_args(artefact_root=str(tmp_path)))
    spec_image = image_spec("ok")
    spec_image.tool_hashes = {"circt-opt": _verify_stub(bin_dir)}
    built.image_spec["tool_hashes"] = dict(spec_image.tool_hashes)
    seed = seed_record()
    bug_loop.write_run_rows(
        loop, built, image_spec=spec_image,
        mined={"seeds": [seed], "sdk_map": {seed.sdk_tag: [seed.seed_sha]},
               "exclusions": {}, "sv_seeds": []},
        mirror=dict(_MIRROR))
    cases = (("p-000000000001", _VERIFIER_STDERR, "input.mlir"),
             ("p-000000000002", _PASS_STDERR, "input.mlir"),
             ("p-000000000003", _VERIFIER_STDERR, "invalid.mlir"))
    for probe_id, stderr_name, filename in cases:
        directory = tmp_path / probe_id
        directory.mkdir()
        case = directory / filename
        case.write_text("hw.module @T() {}\n")
        stderr = directory / "stderr.txt"
        stderr.write_text((FIXTURES / "stderr" / stderr_name).read_text())
        spec = probe_spec(probe_id, "seeded", input_filename=filename,
                          input_path=str(case),
                          argv=["--convert-moore-to-core", str(case)])
        bug_loop.write_probe(loop, spec, str(directory))
        bug_loop.write_build_result(loop, BuildResult(
            probe_id=probe_id, run_manifest_id=_RUN, run_commit="e" * 40,
            image_digest=spec_image.image_digest, status="parse_error",
            binary_path=str(bin_dir / "circt-opt"), binary_sha256="0" * 64,
            argv=[str(bin_dir / "circt-opt"), "--convert-moore-to-core", str(case)],
            exit_status=1, signal=None, limit_hit=None, cpu_seconds=0.1,
            wall_seconds=0.2, peak_rss_bytes=1024, worker_hostname="host",
            worker_node_id="node", child_pid=1, stdout_path="/dev/null",
            stderr_path=str(stderr), stdout_bytes=0,
            stderr_bytes=stderr.stat().st_size, truncated=False))
        bug_loop.write_probe_result(loop, schema.ProbeResult(
            probe_id=probe_id, run_manifest_id=_RUN, seed_sha=spec.seed_sha,
            arm="seeded", iteration=spec.iteration, build_status="parse_error",
            oracle_fired=False, stopping_stage="stage_3",
            stopping_reason="tool_rejected_input", artefact_dir=str(directory),
            exit_status=1), str(directory))
    return loop, built, spec_image


def _reclassify_stages(tmp_path: Path) -> bug_loop.Stages:
    """`fake_stages`, with stage 4 and stage 6's render the real nodes (D-13)."""
    from circt_bug_loop import probe_task, triage_task

    stages = fake_stages()

    def reduce(spec, verdict, limits, artefact_dir, **kwargs):
        path = Path(artefact_dir, "reduced.mlir")
        path.write_text("hw.module @T() {}\n")
        return {"counters": schema.CounterBlock(
            stage="stage_5", started=1, completed=1, failed=0, seconds=0.1),
            "reduced": ReducedCase(
            probe_id=spec.probe_id, reducer="circt-reduce", reduced=True,
            fixpoint=True, budget_truncated=False, reason=None, lift=None,
            path=str(path), size_before_bytes=100, size_after_bytes=10,
            size_before_ops=10, size_after_ops=1, wall_seconds=1.0,
            interestingness_calls=3, recheck_class="verifier_error",
            recheck_assertion_text=None, recheck_assertion_site=None,
            recheck_matches=True)}

    def screen(candidate, seed, verdict, clone_path, db_path, top_n, **kwargs):
        from circt_bug_loop.store import LoopStore
        from circt_bug_loop.triage_task import _screened, _write_rows

        fingerprint = triage_task.compute_fingerprint(
            verdict, None, "", top_n, pass_name="convert-moore-to-core")
        dedup = DedupVerdict(
            probe_id=candidate.probe_id, verdict="new",
            evidence=dict.fromkeys(triage_task._EVIDENCE_KEYS))
        _write_rows(LoopStore(db_path),
                    _screened(candidate, fingerprint, dedup, False, False,
                              "seed_commit"), fingerprint, dedup)
        return {"fingerprint": fingerprint, "dedup": dedup,
                "contaminated_symbol": False, "contaminated_file": False,
                "contamination_lower_bound": "seed_commit", "fixing_commits": [],
                "counters": schema.CounterBlock(
                    stage="stage_6", started=1, completed=1, failed=0, seconds=0.1)}

    return dataclasses.replace(
        stages, oracle_primary=probe_task.oracle_primary, reduce_case=reduce,
        dedup_and_screen=screen, triage_report=triage_task.triage_report)


@pytest.mark.t0
def test_T_U_driver_49_reclassify_rejudges_a_runs_parse_errors(tmp_path: Path):
    """D-13: `--reclassify` re-judges stored `parse_error` probes and makes no turn."""
    import io

    from circt_bug_loop.store import latest

    bin_dir = tmp_path / "bin"
    loop, built, spec_image = _parse_error_run(tmp_path, bin_dir)
    dispatch = _RecordingDispatch()
    campaign = bug_loop.Campaign(
        manifest=built, budget=budget_file(), store=loop,
        stages=_reclassify_stages(tmp_path), dispatch=dispatch,
        counters=bug_loop.CounterLog(_RUN), clone_path=str(tmp_path),
        image_spec=spec_image, bin_dir=str(bin_dir), repair_enabled=False,
        skip_turn=True)
    out = io.StringIO()
    assert bug_loop.reclassify(campaign, out) == 0

    # Only the probe whose diagnostic is the generated verifier's moved, and
    # §4.8's command was not even dispatched for the one that is a pass's own.
    statuses = {row["probe_id"]: row["status"] for row in
                loop.query("SELECT probe_id, status FROM build_result")}
    assert statuses == {"p-000000000001": "verifier_error",
                        "p-000000000002": "parse_error",
                        "p-000000000003": "parse_error"}
    assert dispatch.nodes.count("probe_verify") == 2, "not for the pass's own"

    # The probe's own row moved with it, in place: its PRIMARY KEY forbids a second.
    rows = loop.query("SELECT * FROM probe_result WHERE probe_id = 'p-000000000001'")
    assert len(rows) == 1
    result = schema.from_json(rows[0]["result_json"], schema.ProbeResult)
    assert result.build_status == "verifier_error" and result.oracle_fired
    assert result.oracle_class == "verifier_error"
    assert result.verifier_op == "comb.extract"
    assert result.verifier_message.startswith("error: 'comb.extract' op")
    assert rows[0]["oracle_class"] == "verifier_error"
    assert rows[0]["stopping_stage"] == "gate"

    # Stage 4's two rows, the candidate, and the `verifier` fingerprint basis.
    assert loop.query_one("SELECT verifier_op FROM verifier_error "
                          "WHERE probe_id = 'p-000000000001'")["verifier_op"] \
        == "comb.extract"
    candidate = loop.query_one("SELECT * FROM candidate")
    assert candidate["oracle_class"] == "verifier_error"
    assert candidate["assertion_text"] is None
    finger = loop.query_one("SELECT basis, value FROM fingerprint")
    assert finger["basis"] == "verifier"
    assert finger["value"].startswith("comb.extract\n")
    assert latest(loop, "gate_decision", candidate["candidate_id"])["decision"] \
        == "report"

    # FR-11.8: the report was rendered from the record, by no model turn at all.
    report = loop.query_one("SELECT path, assisted_by FROM report")
    rendered = Path(report["path"]).read_text(encoding="utf-8")
    assert "NO MODEL TURN WAS MADE FOR THIS CANDIDATE" in rendered
    assert "--reclassify" in rendered
    assert "No stack trace" in rendered
    assert "verifier refused the output of the pass" in rendered
    assert "repair_adapt" not in dispatch.nodes

    printed = out.getvalue()
    header = printed.splitlines()[0]
    assert all(name in header for name in bug_loop._RECLASSIFY_COLUMNS)
    row = printed.splitlines()[1].split()
    assert row == ["a" * 12, "3", "1", "report", "x1"]
    assert "1 of 3 `parse_error` probe(s)" in printed
    assert "no model turn was made" in printed

    # A second pass no longer sees the probe that moved, and charges its own
    # entries for the two it must check again: an invocation is not a retry.
    second = io.StringIO()
    assert bug_loop.reclassify(campaign, second) == 0
    assert "0 of 2 `parse_error` probe(s)" in second.getvalue()
    assert len(loop.query("SELECT 1 FROM ledger_entry WHERE stage = 'stage_3'")) == 3



@pytest.mark.t0
def test_T_U_driver_50_reclassify_is_an_argument_and_needs_the_cluster(tmp_path: Path):
    """D-13: `--reclassify` takes a run id, refuses an empty run and needs `circt`."""
    import io

    parsed = bug_loop.build_parser().parse_args(
        ["--mode", "discovery", "--reclassify", _RUN])
    assert parsed.reclassify == _RUN
    assert bug_loop.build_parser().parse_args(
        ["--mode", "discovery"]).reclassify is None
    assert bug_loop._STAGE_OF["probe_verify"] == "stage_3"

    bin_dir = tmp_path / "bin"
    loop, built, spec_image = _parse_error_run(tmp_path, bin_dir)
    loop.update("build_result", {"status": "parse_error"}, {"status": "clean_exit"})
    campaign = bug_loop.Campaign(
        manifest=built, budget=budget_file(), store=loop,
        stages=fake_stages(), dispatch=bug_loop.Dispatch(remote=False),
        counters=bug_loop.CounterLog(_RUN), clone_path=str(tmp_path),
        image_spec=spec_image, bin_dir=str(bin_dir), repair_enabled=False)
    assert bug_loop.reclassify(campaign, io.StringIO()) == 2
    assert bug_loop.manifest_of(loop, _RUN).run_manifest_id == _RUN
    with pytest.raises(LookupError):
        bug_loop.manifest_of(loop, "no-such-run")


@pytest.mark.t0
def test_reclassify_refuses_to_start_without_a_circt_worker(monkeypatch):
    """D-13: every check it makes runs on a `circt` worker, so it needs one."""
    from circt_bug_loop import gate

    monkeypatch.setattr(bug_loop.ray, "init",
                        lambda **kwargs: (_ for _ in ()).throw(
                            ConnectionError("no cluster at auto")))
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.reclassify_dispatch()
    assert raised.value.check == "cluster" and "no cluster" in str(raised.value)

    monkeypatch.setattr(bug_loop.ray, "init", lambda **kwargs: None)
    monkeypatch.setattr(gate, "live_circt_nodes", lambda: [])
    with pytest.raises(bug_loop.PreflightFailed) as raised:
        bug_loop.reclassify_dispatch()
    assert "resource" in str(raised.value)
