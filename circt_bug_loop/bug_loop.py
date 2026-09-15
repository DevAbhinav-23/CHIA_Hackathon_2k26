"""B12, the campaign driver, and B1's `build_image` (03-LLD.md 3.11)."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import os
import random
import shutil
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import chia
import ray
from chia.base.ChiaFunction import ChiaFunction, get
from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

from circt_bug_loop import budget as budget_module
from circt_bug_loop import ledger as ledger_module
from circt_bug_loop.circt_core import CIRCT_BIN_DIR
from circt_bug_loop.contract import schema
from circt_bug_loop.generate_task import STALE_AT_BUILD
from circt_bug_loop.contract.schema import (BudgetFile, CounterBlock, FeedbackBundle,
                                            LedgerEntry, ProbeSpec, RunCommit,
                                            RunManifest, SeedRecord)
from circt_bug_loop.store import (PARTIAL, CandidateRecord, ImageSpec, LoopStore,
                                  Report, utc_now, validate_candidate,
                                  write_artefact, write_turn_failure)

logger = logging.getLogger("circt_bug_loop")


#: The flow directory, in either tree. Nothing here walks past it.
FLOW_DIR = Path(__file__).resolve().parent
#: The INSTALLED chia package. `chia.__file__` is None for a namespace package.
_CHIA_PKG = Path(chia.__path__[0]).resolve()
#: Its checkout, if it is one; `examples/` sits beside the package there.
_CHIA_ROOT = _CHIA_PKG.parent
_ISSUE_SOLVER = _CHIA_ROOT / "examples" / "circt_issue_solver"

#: The staged package the workers run, and the ONLY thing `runtime_env` ships (W6).
SHIPPED_DIR = FLOW_DIR / "_shipped"

#: The four `py_modules` entries `stage_shipped` writes, in Ray's own order.
SHIPPED_MODULES = ("circt_bug_loop", "chia", "issue_task.py", "circt_util.py")

#: What is left behind when the flow package is staged.
_STAGE_EXCLUDES = ("tests", "_shipped", "__pycache__", "*.pyc",
                   "loop.db", "loop.db-shm", "loop.db-wal")
_RUNTIME_ENV_EXCLUDES = ["**/__pycache__", "**/*.pyc"]

#: The two upstream patches the staged copy carries.
VERTEX_BRANCH = 'elif backend == "vertex":'
#: The two bounds that branch hands the backend, which a stale staged copy lacks.
VERTEX_BRANCH_BOUNDS = ("max_tool_iterations=cfg[", "turn_budget_usd=cfg[")
#: `turn_budget_usd` is W-18b's addition to the same patch (errata row 38),
#: `tool_config` is W-18e's - a staged copy without it forces its final answer
#: the way pilot 3 measured returning nothing - `final_tool_names` is D-3's:
#: without it stage 2 never gets the phase in which it can only write - and
#: `rate_limit_retries` is D-8's: without it one 429 ends the turn the way
#: pilot 7 measured; `executed and continued` is W-23's: without it a truncated
#: response that carried tool calls ends the turn the way campaign 1 measured.
#: Each names a piece of the CURRENT patch, so a copy carrying an OLDER one is
#: re-patched, and refused when it cannot be.
VERTEX_USAGE_FIELDS = ("thoughts_token_count", "tool_use_prompt_token_count",
                       "turn_budget_usd", "NODE_ID_TIMEOUT_SECONDS",
                       "tool_config", "final_tool_names", "rate_limit_retries",
                       "executed and continued", "cached_content_token_count")

#: Defaults for 13.1's argument table.
DEFAULT_BUDGET = str(FLOW_DIR / "budget.yaml")
DEFAULT_CLUSTER_YAML = str(FLOW_DIR / "cluster_single.yaml")
DEFAULT_CLONE = str(Path.home() / ".cache" / "circt")
DEFAULT_TOKEN_FILE = str(Path.home() / ".config" / "circt_bug_loop" / "github_token")
DEFAULT_ARTEFACT_ROOT = os.environ.get("BUGLOOP_ARTEFACTS", "")
DEFAULT_IMAGE_TAG = os.environ.get("BUGLOOP_IMAGE_TAG", "")
DEFAULT_BASE_IMAGE = "ghcr.io/ucb-bar/chia-circt:latest"

#: loop.db, at 6.1's path, and CHIA's own unchanged issues.db beside its example.
DB_PATH = str(FLOW_DIR / "loop.db")
ISSUES_DB_PATH = str(_ISSUE_SOLVER / "issues.db")

#: 13.4's two interlock variables, named once.
LIVE_MODEL_ENV = "BUGLOOP_ALLOW_LIVE_MODEL"
API_KEY_ENV = "GEMINI_API_KEY"

#: The two backends whose stage-7 turns the loop cannot meter (3.8, FR-14.8).
_METERED_REPAIR_BACKEND = "vertex"

#: The four repair backends 13.1's table offers.
REPAIR_BACKENDS = ("vertex", "claude", "antigravity", "opencode")

#: B1's two build parameters that are neither argv nor budget.yaml.
IMAGE_TARGETS = ("circt-opt", "firtool", "circt-translate", "arcilator",
                 "circt-reduce", "circt-verilog")
IMAGE_FLAG_STRING = "-O3 -UNDEBUG -gline-tables-only"

#: Step 3's evidence that the pin equality check RAN, which is distinct from its passing.
PIN_CHECK_LINE = "PIN CHECK PASSED"

#: The statuses at which a probe carries on to stage 4 (FR-06.9, 3.6).
_FIRING_STATUSES = ("assertion", "fatal_error", "crash")

#: The status at which a probe stops WITHOUT the differential being asked (N9).
_UNDECIDED_STATUS = "tool_unavailable"

#: Which stage id each dispatched callable's counters belong to (3.11).
_STAGE_OF = {"generate_seeded": "stage_2", "generate_mutation": "stage_2",
             "probe_execute": "stage_3", "oracle_primary": "stage_4",
             "oracle_differential": "stage_4", "reduce_case": "stage_5",
             "dedup_and_screen": "stage_6", "triage_report": "stage_6",
             "repair_adapt": "stage_7", "gate_decide": "gate",
             # The gate's own two `{"circt": 1}` nodes (N8).
             "gate_rerun": "gate", "gate_validate": "gate"}

#: Which stage id each of A3's two agent turns occupies.
_TURN_OF = {"seed_read": "stage_1", "probe_write": "stage_2"}


class PreflightFailed(Exception):
    """One pre-flight check refused the run."""

    def __init__(self, check: str, detail: str):
        self.check = check
        self.detail = detail
        super().__init__(f"{check}: {detail}")


class ImageBuildError(Exception):
    """A step of `build_image` failed."""

    def __init__(self, step: str, detail: str):
        self.step = step
        self.detail = detail
        super().__init__(f"{step}: {detail}")


class BuildTimeout(Exception):
    """`build_image` exceeded its whole-sequence timeout (4.11.1)."""

    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds
        super().__init__(f"the image build exceeded {timeout_seconds} s")


#: What `ray start` writes and `chia down` leaves behind.
RAY_CURRENT_CLUSTER = "/tmp/ray/ray_current_cluster"


def clear_stale_ray_cluster(path: str = RAY_CURRENT_CLUSTER) -> Optional[str]:
    """Remove *path* when it names a cluster that is not running (errata row 37)."""
    if ray.is_initialized():
        return None
    try:
        address = Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not address:
        address = "(empty)"
    host, _, port = address.rpartition(":")
    if host and port.isdigit():
        probe = socket.socket()
        probe.settimeout(1.0)
        try:
            if probe.connect_ex((host, int(port))) == 0:
                return None               # the cluster answers; the file is true
        finally:
            probe.close()
    try:
        os.unlink(path)
    except OSError:
        return None
    return address


def _head_node_id() -> str:
    """Return the Ray node id of the process calling this, which is the head."""
    return ray.get_runtime_context().get_node_id()


def head_options(node_id: str) -> dict:
    """Return the scheduling_strategy dict that pins a task to the head."""
    return {"scheduling_strategy":
            NodeAffinitySchedulingStrategy(node_id=node_id, soft=False)}


#: What a generator-side tool actor is placed at: one CPU and NO cluster resource.
HERE_OPTIONS = {"num_cpus": 1}


#: Every node of 3.2 that MUST run on the head, by `<module>.<name>` (K4).
HEAD_NODES = frozenset({
    "circt_bug_loop.bug_loop.build_image",
    "circt_bug_loop.bug_loop.generate_recorded_seeded",
    "circt_bug_loop.budget.load_budget",
    "circt_bug_loop.corpus.build_corpus",
    "circt_bug_loop.corpus.resolve_sites",
    "circt_bug_loop.feedback.build_feedback",
    "circt_bug_loop.gate.gate_decide",
    "circt_bug_loop.generate_task.generate_seeded",
    "circt_bug_loop.ledger.accrue",
    "circt_bug_loop.mutator_synth.synthesise_mutators",
    "circt_bug_loop.pin_select.select_release_pinned_main",
    "circt_bug_loop.results.render_results",
    "circt_bug_loop.store.artefact_write",
    "circt_bug_loop.triage_task.dedup_and_screen",
    "circt_bug_loop.triage_task.issue_mirror_refresh",
})


#: What `__module__` is for a node DEFINED IN THIS FILE when the file is run as a script.
_MAIN_MODULE = "circt_bug_loop.bug_loop"


def node_key(fn: Callable) -> str:
    """`<module>.<name>` for one node, which is how `HEAD_NODES` names it."""
    module = getattr(fn, "__module__", "") or ""
    if module == "__main__":
        module = _MAIN_MODULE
    return f"{module}.{getattr(fn, '__name__', '')}"


def _stage_ignore(directory: str, names: list) -> set:
    """`shutil.copytree`'s ignore callback for `_STAGE_EXCLUDES`."""
    import fnmatch

    return {name for name in names
            if any(fnmatch.fnmatch(name, pattern) for pattern in _STAGE_EXCLUDES)}


def _apply_patch(patch: Path, cwd: Path, strip: int) -> None:
    """Apply *patch* under *cwd*, which is the staging directory and not a checkout."""
    proc = subprocess.run(
        ["git", "apply", f"-p{strip}", str(patch)], cwd=str(cwd),
        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(cwd.resolve().parent)},
        capture_output=True, timeout=120)
    if proc.returncode != 0:
        raise PreflightFailed(
            "shipped_package",
            f"{patch.name} did not apply to the staged copy: "
            f"{proc.stderr.decode('utf-8', errors='backslashreplace').strip()}")


def stage_shipped(*, upstream: Optional[str] = None,
                  target: Optional[str] = None) -> dict:
    """Build the staged package the workers import, patched, at every start-up."""
    root = Path(target or SHIPPED_DIR)
    patches = Path(upstream or (FLOW_DIR.parent / "upstream"))
    if not _ISSUE_SOLVER.is_dir():
        raise PreflightFailed(
            "shipped_package",
            f"{_ISSUE_SOLVER} does not exist: CHIA's example directory ships "
            "beside the package in a checkout and not in a wheel (13.1)")

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    shutil.copytree(FLOW_DIR, root / "circt_bug_loop", ignore=_stage_ignore)
    shutil.copytree(_CHIA_PKG, root / "chia", ignore=_stage_ignore)
    # CHIA is an implicit namespace package upstream (`chia/__init__.py` does not exist).
    (root / "chia" / "__init__.py").touch()
    for name in ("issue_task.py", "circt_util.py"):
        shutil.copyfile(_ISSUE_SOLVER / name, root / name)

    applied = []
    vertex = root / "chia" / "models" / "vertex.py"
    issue_task = root / "issue_task.py"
    if not all(field in vertex.read_text(encoding="utf-8")
               for field in VERTEX_USAGE_FIELDS):
        _apply_patch(patches / "vertex-usage.patch", root, 1)
        applied.append("vertex-usage.patch")
    if VERTEX_BRANCH not in issue_task.read_text(encoding="utf-8"):
        _apply_patch(patches / "issue_task-vertex-branch.patch", root, 3)
        applied.append("issue_task-vertex-branch.patch")

    return {"root": str(root), "issue_task": str(issue_task), "vertex": str(vertex),
            "applied": applied,
            "py_modules": [str(root / name) for name in SHIPPED_MODULES]}


def runtime_env(shipped: Optional[dict] = None) -> dict:
    """Return the `runtime_env` the driver's own `ray.init` ships (13.1)."""
    staged = shipped or stage_shipped()
    return {"py_modules": list(staged["py_modules"]),
            "excludes": list(_RUNTIME_ENV_EXCLUDES)}


class Dispatch:
    """How the driver reaches a stage node: through Ray, or in this process."""

    def __init__(self, *, remote: bool = True, options: Optional[dict] = None,
                 head_node_id: Optional[str] = None):
        """Take the dispatch mode, the `.options()` override and the head's id."""
        self.remote = remote
        self.options = dict(options or {})
        self.head_node_id = head_node_id

    def head_options(self) -> dict:
        """The pinning options for a `HEAD_NODES` member, resolved once."""
        if self.head_node_id is None:
            self.head_node_id = _head_node_id()
        return head_options(self.head_node_id)

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        """Run one stage node and return what it returned."""
        if self.remote and hasattr(fn, "chia_remote"):
            options = dict(self.options)
            if node_key(fn) in HEAD_NODES:
                options.update(self.head_options())
            handle = fn.options(**options) if options else fn
            return get(handle.chia_remote(*args, **kwargs))
        return getattr(fn, "_chia_original", fn)(*args, **kwargs)


def image_manifest(circt_sha: str, sdk_tag: str, targets, flag_string: str,
                   *, slang: bool = True,
                   base_image: str = DEFAULT_BASE_IMAGE) -> dict:
    """Return 4.11.1's six-key hash manifest, the thing the image tag digests."""
    return {"circt_sha": circt_sha, "sdk_tag": sdk_tag,
            "targets": sorted(targets), "flag_string": flag_string,
            "slang": bool(slang), "base_image": base_image}


def manifest_digest(manifest: dict) -> str:
    """SHA-256 over 4.11.1's six-key manifest, which is 3.2's idempotency key."""
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")).hexdigest()


def image_tag(manifest: dict) -> str:
    """Return `<IMAGE_NAME>:<CIRCT_SHA[:12]>`, the Dockerfile's own scheme."""
    return f"{IMAGE_NAME}:{manifest['circt_sha'][:12]}"


def build_argv(dockerfile: str, tag: str, manifest: dict, context: str) -> list:
    """Return 4.11.1 step 2's `docker build` argument list, in its order."""
    return ["docker", "build", "-f", dockerfile, "-t", tag,
            "--build-arg", f"CIRCT_SHA={manifest['circt_sha']}",
            "--build-arg", f"CIRCT_VER={manifest['sdk_tag']}",
            "--build-arg", f"TOOL_TARGETS={' '.join(manifest['targets'])}",
            "--build-arg", f"CXX_FLAGS_RELEASE={manifest['flag_string']}",
            "--build-arg", f"SLANG={'ON' if manifest['slang'] else 'OFF'}",
            "--build-arg", f"BASE_IMAGE={manifest['base_image']}",
            context]


#: B1's Dockerfile, by name. It lives at two paths in the two trees of 1.4.
DOCKERFILE_NAME = "ChiaCirctAssertDockerfile"

#: The image's repository name, which is the Dockerfile's own.
IMAGE_NAME = "chia-circt-assert"


def dockerfile_and_context() -> tuple:
    """B1's Dockerfile and its build context, in whichever tree this is (1.4)."""
    for root, relative in ((FLOW_DIR.parent, Path("upstream") / "dockerfiles"),
                           (_CHIA_ROOT, Path("dockerfiles"))):
        candidate = root / relative / DOCKERFILE_NAME
        if candidate.is_file():
            return str(candidate), str(root)
    raise ImageBuildError(
        "dockerfile",
        f"{DOCKERFILE_NAME} is neither at {FLOW_DIR.parent}/upstream/dockerfiles "
        f"nor at {_CHIA_ROOT}/dockerfiles; run upstream/sync-to-chia.sh, or run "
        "the driver from this repository")


def parse_hash_manifest(document: dict) -> dict:
    """Flatten a recorded image manifest's `tool_hashes` to name -> SHA-256."""
    flat = {}
    for name, value in document["tool_hashes"].items():
        if isinstance(value, str):
            flat[name] = value
        elif isinstance(value, dict):
            flat[name] = value["sha256"]
        else:
            raise TypeError(f"tool_hashes[{name!r}] is {type(value).__name__}, "
                            "neither a hex string nor a mapping")
    return flat


def lit_discovery(exit_status: Optional[int], output: str) -> tuple:
    """Read FR-03.17's two figures off one `lit --show-tests` run."""
    lines = output.splitlines()
    ok = exit_status == 0 and not any("fatal: unable to parse config file" in line
                                      for line in lines)
    started = False
    count = 0
    for line in lines:
        if line.strip().startswith("-- Available Tests --"):
            started = True
            continue
        if started and line.strip():
            count += 1
    return ok, count


def _run(argv: list, *, timeout: int, cwd: Optional[str] = None) -> dict:
    """Run one command with no shell and return its status and both streams."""
    try:
        proc = subprocess.run(argv, capture_output=True, cwd=cwd, timeout=timeout)
    except subprocess.TimeoutExpired as error:
        raise BuildTimeout(timeout) from error
    return {"rc": proc.returncode,
            "stdout": proc.stdout.decode("utf-8", errors="backslashreplace"),
            "stderr": proc.stderr.decode("utf-8", errors="backslashreplace")}


def _in_container(tag: str, command: list, *, timeout: int) -> dict:
    """Run *command* in a freshly started container from *tag* (5.2)."""
    return _run(["docker", "run", "--rm", tag] + command, timeout=timeout)


@ChiaFunction(max_retries=0)
def build_image(circt_sha: str, sdk_tag: str, targets: tuple, flag_string: str,
                dockerfile: str, *, slang: bool = True,
                base_image: str = DEFAULT_BASE_IMAGE,
                context: str = ".", artefact_dir: Optional[str] = None,
                baseline_objects: Optional[list] = None,
                inspect_only: bool = False,
                timeout_seconds: int = 10800) -> dict:
    """Build and check the assertions-on CIRCT image, or reuse the one that exists.

    Returns:
        {"image_spec": ImageSpec, "reused": bool, "counters": CounterBlock};
        reused is True exactly when step 1 short-circuited.
    Worker:
        head.
    Raises:
        ImageBuildError(step, detail) for a failure at any step, "reuse" among
        them when *inspect_only* and no image carries the tag.
    """
    started = time.monotonic()
    manifest = image_manifest(circt_sha, sdk_tag, targets, flag_string,
                              slang=slang, base_image=base_image)
    tag = image_tag(manifest)
    deadline = started + timeout_seconds

    existing = _run(["docker", "image", "inspect", tag], timeout=60)
    if existing["rc"] == 0:
        spec = _image_spec(tag, manifest, targets, timeout=int(deadline - time.monotonic()),
                           artefact_dir=artefact_dir, baseline=baseline_objects)
        return {"image_spec": spec, "reused": True,
                "counters": _counter_block("image", 1, 1, 0, started)}
    if inspect_only:
        raise ImageBuildError(
            "reuse", f"no image is tagged {tag!r} and --dry-run never builds "
            f"one: build it first, or point the run at the commit whose image "
            f"this host holds")

    try:
        build = _run(build_argv(dockerfile, tag, manifest, context),
                     timeout=int(deadline - time.monotonic()))
        log = build["stdout"] + build["stderr"]
        if build["rc"] != 0:
            raise ImageBuildError("build", log[-4000:])
        if PIN_CHECK_LINE.lower() not in log.lower():
            raise ImageBuildError("pin", "the pin equality check did not run")
        spec = _image_spec(tag, manifest, targets,
                           timeout=int(deadline - time.monotonic()),
                           artefact_dir=artefact_dir, baseline=baseline_objects,
                           build_log=log)
    except (ImageBuildError, BuildTimeout):
        _run(["docker", "image", "rm", "-f", tag], timeout=120)
        raise
    return {"image_spec": spec, "reused": False,
            "counters": _counter_block("image", 1, 1, 0, started)}


def _image_spec(tag: str, manifest: dict, targets, *, timeout: int,
                artefact_dir: Optional[str], baseline: Optional[list],
                build_log: str = "") -> ImageSpec:
    """Steps 4 to 7: lit discovery, versions, hashes and assertion objects."""
    lit = _in_container(tag, ["lit", "--no-progress-bar", "--show-tests",
                              "/workspace/circt/build/test"], timeout=timeout)
    ok, discovered = lit_discovery(lit["rc"], lit["stdout"] + lit["stderr"])
    if artefact_dir:
        Path(artefact_dir).mkdir(parents=True, exist_ok=True)
        Path(artefact_dir, "lit_discovery.txt").write_text(
            lit["stdout"] + lit["stderr"], encoding="utf-8")
        # The six build inputs and their digest.
        Path(artefact_dir, "image_manifest.json").write_text(
            json.dumps({**manifest, "image_tag": tag,
                        "manifest_digest": manifest_digest(manifest)},
                       indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not ok:
        raise ImageBuildError("lit_discovery", (lit["stderr"] or lit["stdout"])[-4000:])

    versions = []
    for target in targets:
        out = _in_container(tag, [f"/workspace/circt/build/bin/{target}", "--version"],
                            timeout=timeout)
        if out["rc"] != 0:
            raise ImageBuildError("tool_versions",
                                  f"{target} --version exited {out['rc']}")
        versions.append(f"{target}: {out['stdout'].strip()}")
    verilator = _in_container(tag, ["verilator", "--version"], timeout=timeout)
    if verilator["rc"] != 0:
        raise ImageBuildError("tool_versions", "verilator --version exited "
                              f"{verilator['rc']}")

    hashes = {}
    for target in targets:
        out = _in_container(tag, ["sha256sum", f"/workspace/circt/build/bin/{target}"],
                            timeout=timeout)
        if out["rc"] != 0:
            raise ImageBuildError("hash_manifest", f"{target}: {out['stderr'][-400:]}")
        hashes[target] = out["stdout"].split()[0]

    nonreferencing = _assertion_objects(tag, targets, timeout=timeout)
    if baseline is not None and set(nonreferencing) != set(baseline):
        difference = sorted(set(nonreferencing) ^ set(baseline))
        raise ImageBuildError("assertion_objects",
                              f"non-referencing objects differ by {difference}")

    # `.RepoDigests` is empty for an image that was never pushed.
    digest = _run(["docker", "image", "inspect", "--format={{.Id}}", tag],
                  timeout=60)
    return ImageSpec(
        circt_sha=manifest["circt_sha"], sdk_tag=manifest["sdk_tag"],
        targets=list(targets), flag_string=manifest["flag_string"],
        cmake_args=[], image_digest=digest["stdout"].strip() or tag,
        manifest_digest=manifest_digest(manifest),
        image_tag=tag, verilator_version=verilator["stdout"].strip(),
        slang_enabled=manifest["slang"], lit_discovery_ok=ok,
        lit_discovered_count=discovered,
        assertion_nonreferencing=nonreferencing, tool_hashes=hashes)


#: W-04's own object scan (`analysis/measurements/w04_verify_in_image.sh:38-45`).
_OBJECT_SCAN = r'''
find /workspace/circt/build -path "*obj.CIRCT*.dir*" -name "*.o" | sort |
while read -r o; do
  nm --undefined-only "$o" 2>/dev/null | grep -q __assert_fail ||
    echo "${o#/workspace/circt/build/}"
done'''


def _assertion_objects(tag: str, targets, *, timeout: int) -> list:
    """FR-03.5's two halves: every target binary, then the objects behind them."""
    binaries = _in_container(
        tag, ["sh", "-c",
              "for t in " + " ".join(targets) + "; do "
              "nm -u /workspace/circt/build/bin/$t | grep -c __assert_fail || true; "
              "done"], timeout=timeout)
    if binaries["rc"] != 0:
        raise ImageBuildError("assertion_objects", binaries["stderr"][-4000:])
    missing = [target for target, line in zip(targets, binaries["stdout"].split())
               if line.strip() in ("0", "")]
    if missing:
        raise ImageBuildError(
            "assertion_objects",
            f"{missing} do not reference __assert_fail: the image was built "
            f"with assertions compiled out (FR-03.5)")

    objects = _in_container(tag, ["sh", "-c", _OBJECT_SCAN], timeout=timeout)
    if objects["rc"] != 0:
        raise ImageBuildError("assertion_objects", objects["stderr"][-4000:])
    return sorted(objects["stdout"].split())


def _git(repo_root: str, *args: str, timeout: int = 60) -> str:
    """One `git -C <repo_root> ...` read, no shell, stripped stdout."""
    proc = subprocess.run(["git", "-C", repo_root, *args], capture_output=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise PreflightFailed("git", proc.stderr.decode(
            "utf-8", errors="backslashreplace").strip())
    return proc.stdout.decode("utf-8", errors="backslashreplace").strip()


def check_01_budget_registered(*, budget_path: str, repo_root: str,
                               run_start_utc: str, campaign: bool = False,
                               exact_pin_shas=None) -> BudgetFile:
    """Check 1: budget.yaml is committed, earlier than the run, and registered."""
    try:
        return budget_module.load_budget._chia_original(
            budget_path, repo_root, run_start_utc=run_start_utc,
            campaign=campaign, exact_pin_shas=exact_pin_shas)["budget"]
    except budget_module.BudgetError as error:
        raise PreflightFailed("budget_registered", str(error)) from error


def check_02_mutator_set_earlier(*, repo_root: str,
                                 flow_dir: str = str(FLOW_DIR)) -> None:
    """Check 2: the registration tag reaches the mutator set's commit (FR-05.2)."""
    tag, registered = budget_module.registration(repo_root)
    if not tag:
        return
    try:
        budget_module._check_frozen_set(repo_root, flow_dir, tag, registered)
    except budget_module.BudgetError as error:
        raise PreflightFailed("mutator_set_earlier", str(error)) from error


#: What `RunManifest.forum_post_url` and `forum_post_date` record for a run that CANNOT FILE (W-18).
NO_FORUM_POST = "none: not posted before the run; required at approval (FR-20.1)"

#: FR-01.1's mining window: twenty-four months of `main`, ending at the corpus head.
CORPUS_WINDOW_MONTHS = 24


def corpus_since(clone_path: str, corpus_head_sha: str) -> str:
    """The date FR-01.1's window opens on, as `build_corpus` wants it (W-18)."""
    when = _git(clone_path, "log", "-1", "--format=%cI", corpus_head_sha)
    head = datetime.fromisoformat(when[:-1] + "+00:00" if when.endswith("Z") else when)
    years = CORPUS_WINDOW_MONTHS // 12
    try:
        opened = head.replace(year=head.year - years)
    except ValueError:                      # 29 February, in a year that has one
        opened = head.replace(year=head.year - years, day=28)
    return opened.date().isoformat()


def check_03_clone_head(*, clone_path: str, corpus_head_sha: str,
                        head_sha: Optional[str] = None) -> None:
    """Check 3: the clone's HEAD equals `corpus_head_sha`, naming both (FR-01.11)."""
    actual = head_sha if head_sha is not None else _git(clone_path, "rev-parse", "HEAD")
    if actual != corpus_head_sha:
        raise PreflightFailed(
            "clone_head", f"{clone_path} is at {actual!r}, and budget.yaml's "
            f"corpus_head_sha is {corpus_head_sha!r}")


def check_04_artefact_root_head(*, artefact_root: str) -> None:
    """Check 4: the artefact root exists and is writable on the head (FR-17.9)."""
    root = Path(artefact_root or "")
    if not artefact_root:
        raise PreflightFailed("artefact_root_head",
                              "no artefact root: pass --artefact-root or set "
                              "BUGLOOP_ARTEFACTS")
    if not root.is_dir():
        raise PreflightFailed("artefact_root_head", f"{artefact_root} is not a directory")
    probe = root / f".bugloop_write_check_{uuid.uuid4().hex}"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        raise PreflightFailed("artefact_root_head",
                              f"{artefact_root} is not writable: {error}") from error


def artefact_root_probe(artefact_root: str) -> dict:
    """Write and remove one file under *artefact_root*, and report only whether it worked."""
    import socket

    path = Path(artefact_root) / f".bugloop_write_check_{uuid.uuid4().hex}"
    try:
        path.write_text("", encoding="utf-8")
        path.unlink()
    except OSError as error:
        return {"writable": False, "worker": socket.gethostname(), "detail": str(error)}
    return {"writable": True, "worker": socket.gethostname(), "detail": None}


def check_05_artefact_root_workers(*, artefact_root: str, probes: dict) -> None:
    """Check 5: the artefact root is writable on every worker type (FR-17.9)."""
    for worker_type, result in sorted(probes.items()):
        if not result.get("writable"):
            raise PreflightFailed(
                "artefact_root_unmounted",
                f"{worker_type} cannot write {artefact_root}: "
                f"{result.get('detail')}")


def check_06_image_lit_discovery(*, image_spec: ImageSpec) -> None:
    """Check 6: the image exists and its `lit_discovery_ok` is true (FR-03.17)."""
    if image_spec is None:
        raise PreflightFailed("image_lit_discovery", "no ImageSpec: the image was "
                              "neither built nor recorded")
    if not image_spec.lit_discovery_ok:
        raise PreflightFailed(
            "image_lit_discovery",
            f"{image_spec.image_tag} discovered {image_spec.lit_discovered_count} "
            "tests and lit_discovery_ok is false; publication is blocked (FR-03.17)")


def check_07_tool_hashes(*, image_spec: ImageSpec, observed: dict) -> None:
    """Check 7: every tool binary's SHA-256 on every worker matches (FR-06.1)."""
    for worker_type, hashes in sorted(observed.items()):
        for tool, expected in sorted(image_spec.tool_hashes.items()):
            actual = hashes.get(tool)
            if actual != expected:
                raise PreflightFailed(
                    "tool_hashes",
                    f"{worker_type}: {tool} hashes {actual!r}, and the ImageSpec "
                    f"records {expected!r}")


def check_08_verilator_version(*, image_spec: ImageSpec, observed: dict) -> None:
    """Check 8: every CIRCT worker's Verilator is the image's (FR-03.15)."""
    for worker_type, version in sorted(observed.items()):
        if version != image_spec.verilator_version:
            raise PreflightFailed(
                "verilator_version",
                f"{worker_type} reports {version!r}, and the ImageSpec records "
                f"{image_spec.verilator_version!r}")


#: The seven `select_release_pinned_main` fields that become manifest fields.
PIN_FIELDS = ("run_commit", "pin_sha", "pin_tag", "tags_sharing_pin",
              "lag_commits", "lag_days", "current_window_has_release")


def check_09_pin_stamped(*, pin: dict) -> None:
    """Check 9: the pin selector ran and every pin field is stamped (FR-02.1 to 02.4)."""
    missing = [f for f in PIN_FIELDS if pin.get(f) is None]
    if missing:
        raise PreflightFailed("pin_stamped",
                              f"the pin selector returned no {sorted(missing)}")


def check_10_issue_mirror(*, mirror: Optional[dict], refresh_requested: bool) -> None:
    """Check 10: the mirror is refreshed, or an existing one is reused (FR-10.9)."""
    if mirror is None:
        raise PreflightFailed(
            "issue_mirror",
            "no issue mirror for this campaign and no --refresh-mirror; "
            "FR-10.9 screens every candidate against one")
    if mirror.get("incomplete_reason"):
        raise PreflightFailed(
            "issue_mirror",
            f"the refresh stopped at {mirror['incomplete_reason']!r} after "
            f"{mirror.get('issues_mirrored')} issues (FR-10.7)")
    if not refresh_requested and not mirror.get("issues_mirrored"):
        raise PreflightFailed("issue_mirror",
                              "the existing mirror holds no issue; pass "
                              "--refresh-mirror to rebuild it")


def check_11_forum_post(*, forum_post_url: Optional[str],
                        forum_post_date: Optional[str],
                        filings_total: Optional[int] = None) -> str:
    """Check 11: record whether the method's forum post exists; FR-20.1 is enforced at approval, before the first filing, so this never refuses a run."""
    if forum_post_url and forum_post_date:
        return "posted"
    return "unposted" if filings_total else "exempt"


def interlock_probe(*, env=None, need_key: bool = True) -> dict:
    """Report whether the live-model interlock and the key are set, and NEVER their values."""
    source = os.environ if env is None else env
    key = (source.get(API_KEY_ENV) or "").strip()
    return {"interlock_ok": source.get(LIVE_MODEL_ENV) == "1",
            "key_ok": bool(key) and not key.startswith("${") if need_key else True}


def check_12_live_model(*, workers: dict, head: Optional[dict] = None) -> None:
    """Check 12: the interlock and the key are set, and agree, wherever a turn is built."""
    if not workers:
        raise PreflightFailed(
            "live_model",
            "no llm worker to check: a live run reaches a model through an "
            "`llm` container and this cluster advertises none (K2, FR-14.5)")
    for where, result in ([("head", head)] if head is not None else []) \
            + sorted(workers.items()):
        if not result.get("interlock_ok"):
            raise PreflightFailed(
                "live_model", f"{where}: {LIVE_MODEL_ENV} is not exactly '1'")
        if not result.get("key_ok"):
            raise PreflightFailed(
                "live_model", f"{where}: {API_KEY_ENV} is empty or unexpanded")


def tool_probe(bin_dir: str, targets: tuple) -> dict:
    """Hash every tool binary on THIS worker and report Verilator's version."""
    import socket
    import subprocess as sp

    hashes, unreadable = {}, []
    for target in targets:
        path = os.path.join(bin_dir, target)
        digest = hashlib.sha256()
        try:
            with open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block)
        except OSError as error:
            unreadable.append(f"{target}: {error}")
            continue
        hashes[target] = digest.hexdigest()
    try:
        version = sp.run(["verilator", "--version"], capture_output=True,
                         timeout=120).stdout.decode(
                             "utf-8", errors="backslashreplace").strip()
    except (OSError, sp.SubprocessError) as error:
        version = f"unavailable: {error}"
    return {"worker": socket.gethostname(), "tool_hashes": hashes,
            "verilator_version": version, "unreadable": unreadable}


def tool_probes(dispatch: Dispatch, resources: dict, bin_dir: str,
                targets: tuple) -> dict:
    """Dispatch `tool_probe` once per image-bearing worker type (W2)."""
    node = ChiaFunction(max_retries=0)(tool_probe)
    probes = {}
    for worker_type, resource in sorted(resources.items()):
        probes[worker_type] = Dispatch(
            remote=dispatch.remote, options={"resources": dict(resource)},
            head_node_id=dispatch.head_node_id).call(node, bin_dir, targets)
    return probes


def check_15_entrypoint_imports(*, flow_dir: str = str(FLOW_DIR),
                                python: Optional[str] = None) -> None:
    """Check 15 (W-19b #3): the driver's own entrypoint can import its package."""
    parent = str(Path(flow_dir).resolve().parent)
    proc = subprocess.run(
        [python or sys.executable, "-c",
         "import circt_bug_loop, circt_bug_loop.bug_loop"],
        env={**os.environ, "PYTHONPATH": parent},
        capture_output=True, timeout=300, cwd="/")
    if proc.returncode != 0:
        message = proc.stderr.decode("utf-8", errors="backslashreplace").strip()
        raise PreflightFailed(
            "entrypoint_import",
            f"`import circt_bug_loop` fails with PYTHONPATH={parent}: "
            f"{message.splitlines()[-1] if message else 'no message'}")


def check_13_vertex_branch(*, issue_task_path: str, repair_backend: str,
                           repair_enabled: bool) -> str:
    """Check 13 (K7): the backend the SHIPPED `issue_task.py` can actually run."""
    text = Path(issue_task_path).read_text(encoding="utf-8")
    present = VERTEX_BRANCH in text
    if repair_enabled and repair_backend == _METERED_REPAIR_BACKEND and not present:
        raise PreflightFailed(
            "vertex_branch",
            f"{issue_task_path} carries no {VERTEX_BRANCH!r}: stage 7 would run "
            f"CHIA's else-branch backend while the manifest recorded "
            f"{_METERED_REPAIR_BACKEND!r} (K7). Re-stage the package, or run "
            "with --no-repair")
    if present:
        missing = [bound for bound in VERTEX_BRANCH_BOUNDS if bound not in text]
        if missing:
            raise PreflightFailed(
                "vertex_branch",
                f"{issue_task_path}'s vertex branch passes {sorted(missing)} to "
                f"nothing: every phase of stage 7 would run with the backend's "
                f"own defaults and no money ceiling (K7, W-18d). Re-stage the "
                "package")
    return repair_backend


def check_14_vertex_usage_patch(*, vertex_path: str, metered: bool) -> None:
    """Check 14 (K11): the shipped `vertex.py` counts the two billed fields."""
    if not metered:
        return
    text = Path(vertex_path).read_text(encoding="utf-8")
    missing = [field for field in VERTEX_USAGE_FIELDS if field not in text]
    if missing:
        raise PreflightFailed(
            "vertex_usage_patch",
            f"{vertex_path} sums {sorted(missing)} nowhere: every priced turn "
            "and the USD cap would be understated by the tokens the model "
            "thinks (K11). Re-stage the package")


#: The pre-flight checks in 13.1's order, cheapest first, named for the log.
PREFLIGHT_CHECKS = (
    "budget_registered", "mutator_set_earlier", "clone_head",
    "artefact_root_head", "artefact_root_unmounted", "image_lit_discovery",
    "tool_hashes", "verilator_version", "pin_stamped", "issue_mirror",
    "forum_post", "live_model", "vertex_branch", "vertex_usage_patch",
    "entrypoint_import")


def cluster_summary(cluster_yaml: str) -> dict:
    """Return the four manifest fields the cluster YAML produces, plus its digest."""
    from chia.cluster.config import load_config

    config = load_config(cluster_yaml)
    digest = hashlib.sha256(Path(cluster_yaml).read_bytes()).hexdigest()
    by_resource = {}
    for name, node_type in config.node_types.items():
        for resource in node_type.resources:
            by_resource[resource] = (name, node_type.num_workers)
    circt = by_resource.get("circt")
    llm = by_resource.get("llm")
    if circt is None or llm is None:
        raise KeyError(f"{cluster_yaml} declares no "
                       f"{'circt' if circt is None else 'llm'} worker type")
    return {"cluster_yaml_sha": digest, "worker_type": circt[0],
            "apparatus_concurrency": circt[1], "llm_concurrency": llm[1],
            "deployment": "gcp" if "gcp" in Path(cluster_yaml).name
                          else "single_machine",
            "image_worker_types": sorted(
                name for name, node_type in config.node_types.items()
                if IMAGE_NAME in (getattr(node_type.docker, "image", "") or ""))}


def model_ids(*, model_id: str, repair_backend: str,
              repair_model: Optional[str] = None) -> dict:
    """Return 2.7's four `"<backend>:<model id>"` strings (13.1)."""
    if not model_id:
        raise ValueError("budget.yaml's model_id is empty")
    backend = _model_backend()
    campaign = f"{backend}:{model_id}"
    repair = f"{repair_backend}:{repair_model or model_id}"
    return {"generate_seeded": campaign, "triage_report": campaign,
            "mutator_synthesis": campaign, "repair_adapt": repair}


def stages_metered(*, arms, repair_backend: str, repair_enabled: bool,
                   model_turns: bool = True) -> dict:
    """Return one bool per stage id: whether the loop can meter that stage (FR-14.8)."""
    seeded = "seeded" in tuple(arms)
    metered = {stage: True for stage in schema._STAGE_IDS}
    metered["stage_1"] = seeded and model_turns
    metered["stage_2"] = seeded and model_turns
    metered["stage_6"] = bool(model_turns)
    metered["stage_7"] = (bool(repair_enabled) and bool(model_turns)
                          and repair_backend == _METERED_REPAIR_BACKEND)
    return metered


def _model_backend() -> str:
    """The campaign backend, read from `llm.py`'s own constant (3.5.1)."""
    from circt_bug_loop import llm

    return llm.MODEL_BACKEND


def differential_driver() -> dict:
    """Return FR-08.11's four keys from B4's own recorded deviation (3.6.3)."""
    from circt_bug_loop import probe_task

    recorded = probe_task.DIFFERENTIAL_DRIVER
    if "; " not in recorded:
        raise ValueError(f"probe_task.DIFFERENTIAL_DRIVER is not "
                         f"'<obstacle>; <deviation>': {recorded!r}")
    obstacle, deviation = recorded.split("; ", 1)
    return {"source": "probe_task.gen_arc_harness and probe_task.gen_verilator_tb, "
                      "generated per probe from the extracted port list",
            "commit": "",
            "deviation": deviation,
            "obstacle": obstacle.removeprefix("deviation: ")}


def run_commits(*, mode: str, pin: dict, seeds=()) -> list:
    """Return FR-02.7's `run_commit` list for *mode*, one entry or one per seed."""
    if mode == "discovery":
        return [RunCommit(commit=pin["run_commit"], seed_sha=None)]
    if not seeds:
        raise ValueError("calibration mode with no sampled seed")
    return [RunCommit(commit=s.parent_sha, seed_sha=s.seed_sha) for s in seeds]


def build_manifest(*, args, budget: BudgetFile, pin: dict, image_spec: ImageSpec,
                   mirror: dict, cluster: dict, mutator_set_sha: str,
                   run_manifest_id: str, started_utc: str,
                   repair_backend: Optional[str] = None,
                   calibration_seeds=(), assertion_baseline_count: int = 0,
                   sv_seeds_excluded=None, shard: Optional[str] = None) -> RunManifest:
    """Build the run's one `RunManifest`, every field from its named producer."""
    from circt_bug_loop import probe_task, repair_adapter

    arms = tuple(budget.arm_order) if args.arm == "both" else (args.arm,)
    backend = repair_backend or args.repair_backend
    manifest = RunManifest(
        run_manifest_id=run_manifest_id,
        mode=args.mode,
        seed_set="171" if args.mode == "calibration" else "187",
        run_commit=run_commits(mode=args.mode, pin=pin, seeds=calibration_seeds),
        pin_sha=pin["pin_sha"], pin_tag=pin["pin_tag"],
        tags_sharing_pin=list(pin["tags_sharing_pin"]),
        lag_commits=pin["lag_commits"], lag_days=pin["lag_days"],
        current_window_has_release=pin["current_window_has_release"],
        corpus_head_sha=budget.corpus_head_sha,
        image_spec={k: getattr(image_spec, k)
                    for k in schema._DICT_KEYS[("RunManifest", "image_spec")]},
        assertion_baseline_count=assertion_baseline_count,
        budget_unit="wall_clock_seconds",
        arm_window_seconds=budget.arm_window_seconds,
        arm_order=list(budget.arm_order),
        budget_file_sha=budget.budget_file_sha,
        cluster_yaml_sha=cluster["cluster_yaml_sha"],
        deployment=cluster["deployment"], worker_type=cluster["worker_type"],
        apparatus_concurrency=cluster["apparatus_concurrency"],
        llm_concurrency=cluster["llm_concurrency"],
        artefact_root=args.artefact_root,
        backend=_model_backend(),
        model_ids=model_ids(model_id=budget.model_id,
                            repair_backend=backend,
                            repair_model=args.repair_model),
        stages_metered=stages_metered(
            arms=arms, repair_backend=backend,
            repair_enabled=repair_enabled(args),
            model_turns=getattr(args, "generator", "model") != "recorded"),
        mutator_set_sha=mutator_set_sha,
        x_policy=probe_task.X_POLICY,
        issue_mirror={k: mirror[k]
                      for k in schema._DICT_KEYS[("RunManifest", "issue_mirror")]},
        local_id_range=[repair_adapter.LOCAL_ID_BASE, repair_adapter.LOCAL_ID_MAX],
        forum_post_url=args.forum_post_url or NO_FORUM_POST,
        forum_post_date=args.forum_post_date or NO_FORUM_POST,
        confirmation_cutoff_date=budget.campaign_end_utc[:10],
        differential_driver=differential_driver(),
        started_utc=started_utc,
        calibration_sample=(sorted(s.seed_sha for s in calibration_seeds)
                            if args.mode == "calibration" else None),
        sv_seeds_excluded=sv_seeds_excluded,
        shard=shard)
    schema.validate(manifest)
    return manifest


def _counter_block(stage: str, started: int, completed: int, failed: int,
                   since: float) -> CounterBlock:
    """One CounterBlock for a unit of work that began at *since* (monotonic)."""
    return CounterBlock(stage=stage, started=started, completed=completed,
                        failed=failed, seconds=round(time.monotonic() - since, 6))


class CounterLog:
    """FR-17.4's per-stage counters, accumulated per (run, arm, stage) on the head."""

    def __init__(self, run_manifest_id: str, results_dir: Optional[str] = None,
                 metrics=None):
        """Take the run id, where counters.json goes, and the metrics logger."""
        self.run_manifest_id = run_manifest_id
        self.results_dir = results_dir
        self.metrics = metrics
        self.totals: dict = {}
        self.violations: list = []
        self._step = 0

    def record(self, arm: str, block: CounterBlock, *, synthesised: bool = False) -> None:
        """Fold one block into this run's totals and log it."""
        if block.stage not in schema._COUNTER_STAGES:
            raise ValueError(f"CounterBlock.stage {block.stage!r} is outside "
                             f"{sorted(schema._COUNTER_STAGES)}")
        if block.started != block.completed + block.failed:
            self.violations.append(
                f"counters_unbalanced:{arm}:{block.stage}:"
                f"{block.started}!={block.completed}+{block.failed}")
        if synthesised:
            self.violations.append(f"counters_missing:{arm}:{block.stage}")
        key = f"{arm}/{block.stage}"
        total = self.totals.setdefault(
            key, {"started": 0, "completed": 0, "failed": 0, "seconds": 0.0})
        for name in ("started", "completed", "failed"):
            total[name] += getattr(block, name)
        total["seconds"] = round(total["seconds"] + block.seconds, 6)
        self._step += 1
        if self.metrics is not None:
            for name in ("started", "completed", "failed", "seconds"):
                self.metrics.log_scalar(
                    f"{self.run_manifest_id}/{key}/{name}",
                    float(getattr(block, name)), self._step)
        self.write()

    def write(self) -> Optional[str]:
        """Rewrite `results/counters.json` with the running totals."""
        if not self.results_dir:
            return None
        Path(self.results_dir).mkdir(parents=True, exist_ok=True)
        path = Path(self.results_dir) / "counters.json"
        path.write_text(json.dumps(
            {"run_manifest_id": self.run_manifest_id, "totals": self.totals,
             "violations": self.violations},
            sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(path)


#: Which field names an instance of each member, for the recorded file's name.
_FIXTURE_ID = {"SeedRecord": "seed_sha", "BudgetFile": "budget_file_sha",
               "ProbeSpec": "probe_id", "ProbeResult": "probe_id",
               "LedgerEntry": "entry_id", "RunManifest": "run_manifest_id"}


class FixtureRecorder:
    """`--record-fixtures`: write every produced instance after validate accepts it."""

    def __init__(self, directory: Optional[str]):
        """Take the recording directory, or None to record nothing."""
        self.directory = directory
        self.written: list = []

    def record(self, instance) -> Optional[str]:
        """Validate *instance* and write it under its schema's directory."""
        if not self.directory:
            return None
        schema.validate(instance)
        name = type(instance).__name__
        if name == "FeedbackBundle":
            ident = f"{instance.seed_sha}_{instance.arm}_{instance.iteration}"
        else:
            ident = getattr(instance, _FIXTURE_ID[name])
        folder = Path(self.directory) / _snake(name)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{ident}.json"
        path.write_text(schema.to_json(instance), encoding="utf-8")
        self.written.append(str(path))
        return str(path)


def _snake(name: str) -> str:
    """`RunManifest` to `run_manifest`, which is the fixture directory's name."""
    out = []
    for index, char in enumerate(name):
        if char.isupper() and index:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


#: Each table's column list.
_TABLE_COLUMNS: dict = {}

#: What `_row` treats as "the record does not carry this column".
_ABSENT = object()


def table_columns(store: LoopStore, table: str) -> tuple:
    """Return *table*'s columns, in the order §6.2's DDL declares them."""
    if table not in _TABLE_COLUMNS:
        rows = store.query("SELECT name FROM pragma_table_info(?)", (table,))
        if not rows:
            raise KeyError(f"loop.db holds no table {table!r}")
        _TABLE_COLUMNS[table] = tuple(row["name"] for row in rows)
    return _TABLE_COLUMNS[table]


def _cell(value):
    """One SQLite cell from one Python value: a bool is an INTEGER (§6.2)."""
    return int(value) if isinstance(value, bool) else value


def _json_cell(value) -> str:
    """A `_json` column's text: JSON with sorted keys, dataclasses expanded."""
    if isinstance(value, list):
        value = [dataclasses.asdict(item) if dataclasses.is_dataclass(item) else item
                 for item in value]
    return json.dumps(value, sort_keys=True)


def _row(store: LoopStore, table: str, record=None, **extra) -> dict:
    """Build one row of *table* from *record*, column by declared column."""
    row = {}
    for column in table_columns(store, table):
        if column in extra:
            row[column] = _cell(extra[column])
            continue
        name = column[:-5] if column.endswith("_json") else column
        value = (record.get(name, _ABSENT) if isinstance(record, dict)
                 else getattr(record, name, _ABSENT))
        if value is _ABSENT:
            continue
        row[column] = _json_cell(value) if column.endswith("_json") else _cell(value)
    return row


#: Now, UTC, ISO-8601.
_utc = utc_now


def write_run_rows(store: LoopStore, manifest: RunManifest, *,
                   image_spec: ImageSpec, mined: Optional[dict] = None,
                   mirror: Optional[dict] = None,
                   registration: tuple = ("", "")) -> None:
    """Write everything §6.4 puts in the store before the first probe is dispatched."""
    run_id = manifest.run_manifest_id
    if store.query_one("SELECT 1 FROM run WHERE run_manifest_id = ?",
                       (run_id,)) is None:
        store.insert("run", _row(store, "run", manifest,
                                 manifest_json=schema.to_json(manifest)))
        if registration[0]:
            store.insert("registration", {"run_manifest_id": run_id,
                                          "registration_tag": registration[0],
                                          "registration_commit": registration[1]})
    if store.query_one("SELECT 1 FROM image WHERE image_digest = ?",
                       (image_spec.image_digest,)) is None:
        store.insert("image", _row(store, "image", image_spec, built_utc=_utc()))

    seeds = list((mined or {}).get("seeds") or ())
    if seeds:
        exclusions = dict((mined or {}).get("exclusions") or {})
        # ADR-D-13 branch (b) only.
        excluded_sv = (set() if image_spec.slang_enabled
                       else set((mined or {}).get("sv_seeds") or ()))
        rows = []
        for seed in seeds:
            reason = exclusions.get(seed.seed_sha) or (
                "sv_frontend_unavailable" if seed.seed_sha in excluded_sv else None)
            rows.append(_row(store, "seed", seed, run_manifest_id=run_id,
                             record_json=schema.to_json(seed),
                             exclusion_reason=reason,
                             eligible_seeded=reason is None,
                             eligible_mutation=reason is None))
        store.insert_many("seed", rows)
    sdk_map = dict((mined or {}).get("sdk_map") or {})
    if sdk_map:
        store.insert_many("sdk_map", [
            {"run_manifest_id": run_id, "sdk_tag": tag,
             "seed_shas_json": json.dumps(list(shas), sort_keys=True)}
            for tag, shas in sorted(sdk_map.items())])

    if mirror is not None and store.query_one(
            "SELECT 1 FROM issue_mirror_meta WHERE run_manifest_id = ?",
            (run_id,)) is None:
        store.insert("issue_mirror_meta",
                     _row(store, "issue_mirror_meta", mirror, run_manifest_id=run_id))


def finish_run(store: LoopStore, manifest: RunManifest, ended_utc: str) -> None:
    """Stamp the run's end on its own row, which is the last write of a campaign."""
    store.update("run", {"run_manifest_id": manifest.run_manifest_id},
                 {"ended_utc": ended_utc})


def write_probe(store: LoopStore, spec: ProbeSpec, artefact_dir: str) -> None:
    """Write the `probe` row, before the probe that fills the rest of its tables."""
    store.insert("probe", _row(store, "probe", spec,
                               spec_json=schema.to_json(spec),
                               artefact_dir=artefact_dir))


def write_build_result(store: LoopStore, build) -> None:
    """Write stage 3's `build_result` row, the evidence, as soon as B2 returns."""
    store.insert("build_result", _row(store, "build_result", build))


def write_probe_result(store: LoopStore, result, artefact_dir: str) -> None:
    """Write the `probe_result` row, once, when the probe has stopped."""
    store.insert("probe_result", _row(store, "probe_result", result,
                                      result_json=schema.to_json(result),
                                      artefact_dir=artefact_dir))


def write_oracle_verdict(store: LoopStore, verdict) -> None:
    """Write stage 4's `oracle_verdict` row, frames and all."""
    store.insert("oracle_verdict", _row(store, "oracle_verdict", verdict))


def write_differential_verdict(store: LoopStore, verdict) -> None:
    """Write B4's `differential_verdict` row, whatever the verdict is (FR-08.9)."""
    store.insert("differential_verdict",
                 _row(store, "differential_verdict", verdict))


def write_reduced_case(store: LoopStore, reduced) -> None:
    """Write stage 5's `reduced_case` row, an unreduced case included (FR-09.12)."""
    store.insert("reduced_case", _row(store, "reduced_case", reduced))


def write_candidate(store: LoopStore, candidate: CandidateRecord) -> None:
    """Write one `candidate` row the screen never sees: a differential one."""
    validate_candidate(candidate)
    store.insert("candidate", _row(store, "candidate", candidate,
                                   created_utc=_utc()))


def write_report(store: LoopStore, report) -> None:
    """Write stage 6's `report` row, an unrendered report included (FR-11.8)."""
    store.insert("report", _row(store, "report", report))


def write_repair_dispatch(store: LoopStore, candidate_id: str, local_id: int, *,
                          repro_dir: str, backend: str) -> None:
    """FR-12.10: the loop's row and the candidate's local id, before CHIA's."""
    store.transaction([
        ("UPDATE candidate SET local_id = ? WHERE candidate_id = ?",
         (local_id, candidate_id)),
        ("INSERT INTO repair (candidate_id, local_id, status, lit_unusable, "
         "lit_failures_json, chia_row_seen, repro_dir, repro_overwritten, "
         "restore_ok, restore_hashes_match, restore_log, backend, token_capture) "
         "VALUES (?, ?, 'dispatched', 0, '[]', 0, ?, 0, 0, 0, '', ?, "
         "'unavailable_remote_dispatch')",
         (candidate_id, local_id, repro_dir, backend)),
    ])


def write_repair_result(store: LoopStore, result) -> None:
    """Complete the `repair` row from what B8 returned, leaving `chia_row_seen`."""
    fields = _row(store, "repair", result)
    for column in ("candidate_id", "chia_row_seen"):
        fields.pop(column, None)
    store.update("repair", {"candidate_id": result.candidate_id}, fields)


def write_gate_decision(store: LoopStore, decision) -> None:
    """§6.4 rule 4's second batch: the decision row and the candidate's bucket."""
    from circt_bug_loop.gate import answers

    store.transaction([
        ("INSERT INTO gate_decision (candidate_id, answers_json, "
         "stopped_at_question, decision, taxonomy_bucket, decided_utc) "
         "VALUES (?, ?, ?, ?, ?, ?)",
         (decision.candidate_id, json.dumps(answers(decision), sort_keys=True),
          decision.stopped_at_question, decision.decision,
          decision.taxonomy_bucket, _utc())),
        ("UPDATE candidate SET taxonomy_bucket = ?, held_reason = ? "
         "WHERE candidate_id = ?",
         (decision.taxonomy_bucket, decision.held_reason, decision.candidate_id)),
    ])


def write_feedback(store: LoopStore, bundle: FeedbackBundle, path: str) -> None:
    """Write the iteration's `feedback` row and A5's bundle beside it (§6.5)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(schema.to_json(bundle), encoding="utf-8")
    store.insert("feedback", _row(store, "feedback", bundle, path=path))


@dataclasses.dataclass(kw_only=True)
class Stages:
    """The ten stage callables `campaign_drive` dispatches, as one record."""
    generate_seeded: Any
    generate_mutation: Any
    probe_execute: Any
    oracle_primary: Any
    oracle_differential: Any
    reduce_case: Any
    dedup_and_screen: Any
    triage_report: Any
    repair_adapt: Any
    gate_decide: Any

    def generator(self, arm: str):
        """Return the generator this arm runs: A3 for seeded, A4 for mutation."""
        return self.generate_seeded if arm == "seeded" else self.generate_mutation


def default_stages() -> Stages:
    """Return the ten real nodes, imported here so a T0 test need not import them."""
    from circt_bug_loop import gate, generate_task, probe_task, repair_adapter, triage_task

    return Stages(generate_seeded=generate_task.generate_seeded,
                  generate_mutation=generate_task.generate_mutation,
                  probe_execute=probe_task.probe_execute,
                  oracle_primary=probe_task.oracle_primary,
                  oracle_differential=probe_task.oracle_differential,
                  reduce_case=probe_task.reduce_case,
                  dedup_and_screen=triage_task.dedup_and_screen,
                  triage_report=triage_task.triage_report,
                  repair_adapt=repair_adapter.repair_adapt,
                  gate_decide=gate.gate_decide)


#: `--generator recorded`'s first source.
RECORDED_SPEC_DIR = FLOW_DIR / "contract" / "fixtures" / "recorded" / "probe_spec"

#: The mutator id a REPLAYED test file carries on the mutation arm.
RECORDED_MUTATOR_ID = "recorded.replay.identity"

#: What `recorded_report` writes where the agent's three prose fields would be.
NO_TURN_PROSE = ("NO MODEL TURN WAS MADE. This run was driven with "
                 "`--generator recorded`, so stage 6's agent turn did not "
                 "happen and this field is the driver's own sentence and not "
                 "an agent's. The classification is `untriaged`, which is what "
                 "FR-11.8 gives a candidate whose turn did not produce one.")


def recorded_inputs(seed: SeedRecord, cap: int) -> list:
    """The probing inputs `--generator recorded` replays for one seed, in order."""
    out = []
    for document in sorted(RECORDED_SPEC_DIR.glob("*.json")):
        try:
            spec = json.loads(document.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if spec.get("seed_sha") == seed.seed_sha and spec.get("input_text"):
            out.append((spec["input_text"], spec.get("source_test_path") or "",
                        f"recorded ProbeSpec {spec.get('probe_id')} replayed"))
    for path, text in sorted(seed.test_files.items()):
        out.append((text, path, f"{path} replayed unchanged at the run commit"))
    return out[:max(0, cap)]


#: SQLite's INTEGER is SIGNED 64-bit, so `probe.mutator_seed_int` holds at most 2**63.
SQLITE_MAX_INT = (1 << 63) - 1


def _seed_int(text: str) -> int:
    """A deterministic RNG seed for a replayed input, inside SQLite's range."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8],
                          "big") & SQLITE_MAX_INT


def _recorded_generation(seed: SeedRecord, cfg: dict, arm: str) -> dict:
    """Build one seed's recorded `ProbeSpec`s for one arm, through A3/A4's builder."""
    from circt_bug_loop.generate_task import _spec, iteration_dir as generator_dir

    started = time.monotonic()
    iteration = int(cfg["iteration"])
    cap_bytes = int(cfg.get("artefact_inline_cap_bytes", 262144))
    probe_root = str(Path(generator_dir(cfg, seed.seed_sha, iteration)) / "probes")
    mutation = arm == "mutation"
    specs: list = []
    failure = None
    try:
        for index, (text, source, expected) in enumerate(
                recorded_inputs(seed, int(cfg["per_seed_probe_cap"]))):
            specs.append(_spec(
                seed=seed, arm=arm, iteration=iteration,
                run_manifest_id=cfg["run_manifest_id"], probe_dir=probe_root,
                text=text, tool=seed.entry_tool, expected_outcome=expected,
                turn_cost={"turn": None, "wall_seconds": 0.0, "metered": False,
                           "tokens_in": None, "tokens_out": None,
                           "cost_usd": None},
                key=f"recorded:{index}", cap_bytes=cap_bytes,
                mutator_id=RECORDED_MUTATOR_ID if mutation else None,
                mutator_seed_int=_seed_int(text) if mutation else None,
                source_test_path=(source or seed.test_paths[0]) if mutation else None))
    except Exception as error:                      # noqa: BLE001 - FR-04.8
        failure = f"recorded_generator_failed:{type(error).__name__}:{error}"
    return {"specs": specs, "logs": {"usage": {}, "wall_seconds": {}},
            "failure": failure,
            "counters": CounterBlock(stage="stage_2", started=1,
                                     completed=0 if failure else 1,
                                     failed=1 if failure else 0,
                                     seconds=time.monotonic() - started)}


@ChiaFunction(max_retries=0)
def generate_recorded_seeded(seed: SeedRecord, feedback: FeedbackBundle,
                             remaining, cfg: dict) -> dict:
    """A3's signature and placement, with recorded inputs and no turn (W-19b).

    Returns:
        A3's shape: {"specs", "logs", "failure", "counters"}.
    Worker:
        head, A3's own; it runs no CIRCT tool and holds no `circt` slot.
    Raises:
        nothing.
    """
    return _recorded_generation(seed, cfg, "seeded")


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def generate_recorded_mutation(seed: SeedRecord, feedback: FeedbackBundle,
                               remaining, cfg: dict) -> dict:
    """A4's signature and placement, with recorded inputs and no mutator set."""
    return _recorded_generation(seed, cfg, "mutation")


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def recorded_report(candidate: CandidateRecord, reduced, verdict, dedup,
                    manifest: RunManifest, cfg: dict, artefact_dir: str, *,
                    differential=None) -> dict:
    """B7's signature and placement, rendering 7.4.1's template with no turn.

    Returns:
        B7's shape: {"report": Report, "logs", "failure", "counters"}.
    Worker:
        `{"circt": 1}`, B7's own; no `{"llm": 1}` turn is dispatched.
    Raises:
        nothing.
    """
    from circt_bug_loop.triage_task import (ReportIncomplete, assisted_by_model,
                                            render_report)

    started = time.monotonic()
    validate_candidate(candidate)
    template = "differential" if candidate.oracle_class == "differential" else "primary"
    classification = "untriaged"
    if dedup is not None and dedup.verdict in ("known_open_issue",
                                               "known_closed_issue",
                                               "fixed_post_pin"):
        classification = "known_issue"
    logs = {"usage": {}, "no_turn": True, "generator": "recorded"}
    try:
        rendered = render_report(template, candidate, reduced, verdict, differential,
                                 dedup, manifest,
                                 dict.fromkeys(("title", "summary",
                                                "why_it_matters"), NO_TURN_PROSE))
    except (ReportIncomplete, ValueError) as error:
        return {"report": Report(
                    candidate_id=candidate.candidate_id, path="", template=template,
                    title="", classification="untriaged", classification_reason="",
                    rendered_sha256="",
                    assisted_by=assisted_by_model(manifest) or "none",
                    fields_present=[]),
                "logs": logs, "failure": f"report_incomplete:{error}",
                "counters": CounterBlock(stage="stage_6", started=1, completed=0,
                                         failed=1,
                                         seconds=time.monotonic() - started)}
    path = str(Path(artefact_dir) / "report.md")
    write_artefact(artefact_dir, "report.md", rendered.encode("utf-8"))
    from circt_bug_loop.triage_task import DIFFERENTIAL_POINTS, PRIMARY_POINTS

    points = PRIMARY_POINTS if template == "primary" else DIFFERENTIAL_POINTS
    return {"report": Report(
                candidate_id=candidate.candidate_id, path=path, template=template,
                title=NO_TURN_PROSE, classification=classification,
                classification_reason=NO_TURN_PROSE,
                rendered_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
                assisted_by=assisted_by_model(manifest) or "none",
                fields_present=list(points)),
            "logs": logs, "failure": None,
            "counters": CounterBlock(stage="stage_6", started=1, completed=1,
                                     failed=0, seconds=time.monotonic() - started)}


def recorded_stages() -> Stages:
    """`default_stages()` with the two model-bearing nodes replaced (W-19b)."""
    return dataclasses.replace(default_stages(),
                               generate_seeded=generate_recorded_seeded,
                               generate_mutation=generate_recorded_mutation,
                               triage_report=recorded_report)


def probe_limits(budget: BudgetFile) -> dict:
    """Return the six per-probe and per-reduction limits budget.yaml fixes."""
    return {"probe_wall_seconds": budget.probe_wall_seconds,
            "probe_address_space_bytes": budget.probe_address_space_bytes,
            "probe_cpu_seconds": budget.probe_cpu_seconds,
            "probe_output_byte_cap": budget.probe_output_byte_cap,
            "reduction_wall_seconds": budget.reduction_wall_seconds,
            "reduction_sigkill_grace_seconds": budget.reduction_sigkill_grace_seconds}


def generator_cfg(manifest: RunManifest, budget: BudgetFile, *, clone_path: str,
                  iteration: int, artefact_dir: Optional[str] = None,
                  head_options: Optional[dict] = None,
                  here_options: Optional[dict] = None) -> dict:
    """Return the `cfg` A3 and A4 read, built from the manifest and the budget."""
    return {"model_id": budget.model_id,
            "per_seed_probe_cap": budget.per_seed_probe_cap,
            "iteration": iteration,
            "run_manifest_id": manifest.run_manifest_id,
            "artefact_root": manifest.artefact_root,
            "artefact_dir": artefact_dir,
            "artefact_inline_cap_bytes": budget.artefact_inline_cap_bytes,
            "clone_path": clone_path,
            "run_commit": manifest.run_commit[0].commit,
            "timeout_seconds": budget.probe_wall_seconds * 40,
            "price_usd_per_m_input_tokens": budget.price_usd_per_m_input_tokens,
            "price_usd_per_m_output_tokens": budget.price_usd_per_m_output_tokens,
            "mutator_set_path": None,
            "mutator_set_sha": manifest.mutator_set_sha,
            # A4 runs the seed's own test before it mutates it (FR-01.9, W-19c).
            "probe_limits": probe_limits(budget),
            "head_options": head_options,
            "here_options": here_options or dict(HERE_OPTIONS),
            "max_tool_iterations": dict(budget.max_tool_iterations)}


def empty_feedback(manifest: RunManifest, seed: SeedRecord, arm: str,
                   iteration: int) -> FeedbackBundle:
    """Return the bundle the first iteration of a seed reads: no entries at all."""
    return FeedbackBundle(run_manifest_id=manifest.run_manifest_id,
                          seed_sha=seed.seed_sha, arm=arm, iteration=iteration,
                          entries=[], abandoned=False)


def iteration_dir(manifest: RunManifest, seed_sha: str, iteration: int) -> str:
    """Return 6.5's `<root>/<run>/seed_<sha>/iter_<n>`, one seed's one iteration."""
    return str(Path(manifest.artefact_root) / manifest.run_manifest_id
               / f"seed_{seed_sha}" / f"iter_{iteration}")


def probe_dir(manifest: RunManifest, seed_sha: str, iteration: int,
              probe_id: str) -> str:
    """Return 6.5's `<root>/<run>/seed_<sha>/iter_<n>/probe_<id>` for one probe."""
    return str(Path(iteration_dir(manifest, seed_sha, iteration))
               / f"probe_{probe_id}")


def _candidate(spec: ProbeSpec, build, verdict, reduced, manifest: RunManifest,
               artefact_dir: str, top_n: int) -> CandidateRecord:
    """Assemble the pre-dedup candidate the screen fills in and validates (2.9)."""
    from circt_bug_loop.probe_task import _normalise_function, strip_prologue

    assertion = verdict.oracle_class == "assertion"
    frames = strip_prologue(list(verdict.frames))
    return CandidateRecord(
        candidate_id=f"c-{spec.probe_id}", probe_id=spec.probe_id,
        run_manifest_id=manifest.run_manifest_id, arm=spec.arm,
        run_commit=manifest.run_commit[0].commit,
        image_digest=manifest.image_spec["image_digest"],
        oracle_class=verdict.oracle_class,
        frame_tuple=[_normalise_function(f.function) for f in frames][:top_n],
        frames_resolved=verdict.frames_resolved,
        frames_with_location=verdict.frames_with_location,
        out_of_scope_root=verdict.out_of_scope_root,
        contaminated_symbol=False, contaminated_file=False,
        contamination_lower_bound="seed_commit" if spec.arm == "seeded" else "run_commit",
        triage_class="untriaged", artefact_dir=artefact_dir,
        assertion_text=verdict.assertion_text if assertion else None,
        assertion_site=verdict.assertion_site if assertion else None,
        repro_command=verdict.repro_command,
        reducer=reduced.reducer, reduced=reduced.reduced,
        fixpoint=reduced.fixpoint, budget_truncated=reduced.budget_truncated,
        reduced_path=reduced.path, size_before_bytes=reduced.size_before_bytes,
        size_after_bytes=reduced.size_after_bytes,
        size_before_ops=reduced.size_before_ops,
        size_after_ops=reduced.size_after_ops)


def _occupancies(stage: str, block: CounterBlock, out) -> list:
    """The (stage, seconds, usage) occupancies one dispatched call produced."""
    logs = out.get("logs") if isinstance(out, dict) else None
    usage = (logs or {}).get("usage") if isinstance(logs, dict) else None
    if not isinstance(usage, dict) or not usage:
        return [(stage, block.seconds, {})]
    if "tokens_in" in usage:                      # one turn, reported flat (B7)
        return [(stage, block.seconds, usage)]
    walls = logs.get("wall_seconds") or {}
    turns = [(turn, u) for turn, u in sorted(usage.items()) if turn in _TURN_OF]
    if not turns:
        return [(stage, block.seconds, {})]
    charged, spent = [], 0.0
    for turn, turn_usage in turns:
        if _TURN_OF[turn] == stage:
            continue                              # the node's own stage takes the rest
        seconds = float(walls.get(turn) or 0.0)
        spent += seconds
        charged.append((_TURN_OF[turn], seconds, turn_usage or {}))
    own = next((u for turn, u in turns if _TURN_OF[turn] == stage), {})
    charged.append((stage, block.seconds - spent, own or {}))
    return charged


class Campaign:
    """One run's state: the manifest, the budget, the stores and the dispatch."""

    def __init__(self, *, manifest: RunManifest, budget: BudgetFile,
                 store: LoopStore, stages: Stages, dispatch: Dispatch,
                 counters: CounterLog, recorder: Optional[FixtureRecorder] = None,
                 clone_path: str = "", image_spec=None, repair_enabled: bool = True,
                 seed_map: Optional[dict] = None, now: Optional[Callable] = None,
                 bin_dir: str = CIRCT_BIN_DIR,
                 head_options: Optional[dict] = None,
                 repair_backend: str = _METERED_REPAIR_BACKEND):
        """Take everything a stage call needs, and compute nothing else."""
        self.head_options = head_options
        self.repair_backend = repair_backend
        self.manifest = manifest
        self.budget = budget
        self.store = store
        self.stages = stages
        self.dispatch = dispatch
        self.counters = counters
        self.recorder = recorder or FixtureRecorder(None)
        self.clone_path = clone_path
        self.image_spec = image_spec
        self.repair_enabled = repair_enabled
        self.limits = probe_limits(budget)
        self.seed_map = seed_map or {}
        self.now = now or time.monotonic
        self.bin_dir = bin_dir

    def cfg(self, *, iteration: int, artefact_dir: Optional[str] = None,
            spend_usd: Optional[float] = None) -> dict:
        """This run's `generator_cfg`, carrying the head placement K4 needs."""
        cfg = generator_cfg(self.manifest, self.budget,
                            clone_path=self.clone_path, iteration=iteration,
                            artefact_dir=artefact_dir,
                            head_options=self.head_options)
        cfg["spend_guard"] = self.spend_guard(
            self.spend_usd() if spend_usd is None else spend_usd)
        cfg["bin_dir"] = self.bin_dir
        return cfg

    def spend_usd(self) -> float:
        """This run's campaign spend, read from the ledger right now."""
        return float(ledger_module.aggregate(
            self.manifest.run_manifest_id, self.store.db_path).spend_usd)

    def spend_guard(self, spend_usd: float):
        """W1's pre-authorisation record, at *spend_usd*."""
        from circt_bug_loop.llm import SpendGuard

        return SpendGuard(
            cap_usd=float(self.budget.campaign_spend_cap_usd),
            spend_usd=float(spend_usd),
            price_usd_per_m_input_tokens=self.budget.price_usd_per_m_input_tokens,
            price_usd_per_m_output_tokens=self.budget.price_usd_per_m_output_tokens)

    def call(self, name: str, fn: Callable, *args, **kwargs):
        """Dispatch one stage, fold its counters in, charge it, and return its result."""
        started = self.now()
        arm = kwargs.pop("_arm", "shared")
        key = kwargs.pop("_key", "")
        stage = _STAGE_OF[name]
        try:
            out = self.dispatch.call(fn, *args, **kwargs)
        except Exception:
            block = _counter_block(stage, 1, 0, 1, started)
            self.counters.record(arm, block, synthesised=True)
            self.charge(arm, name, block, None, key)
            raise
        block = out.get("counters") if isinstance(out, dict) else None
        if isinstance(block, CounterBlock):
            self.counters.record(arm, block)
        else:
            block = _counter_block(stage, 1, 1, 0, started)
            self.counters.record(arm, block, synthesised=True)
        self.charge(arm, name, block, out, key)
        return out

    def charge(self, arm: str, name: str, block: CounterBlock, out, key: str) -> None:
        """Append this call's stage occupancy to the ledger, one entry per stage."""
        run_id = self.manifest.run_manifest_id
        for stage, seconds, usage in _occupancies(_STAGE_OF[name], block, out):
            entry = LedgerEntry(
                entry_id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{run_id}/{arm}/stage/{stage}/{name}/{key}").hex,
                run_manifest_id=run_id, arm=arm, scope="stage", stage=stage,
                unit="wall_clock_seconds", amount=max(0.0, round(seconds, 6)),
                metered=bool(self.manifest.stages_metered.get(stage, True)),
                # The four money fields are contract 2.2's and are the TURN's own.
                observed={"cpu_seconds": None,
                          "tokens_in": usage.get("tokens_in"),
                          "tokens_out": usage.get("tokens_out"),
                          "cached_tokens": usage.get("cached_tokens"),
                          "cost_usd": None,
                          "authorised_usd": usage.get("authorised_usd"),
                          "ceiling_usd": usage.get("ceiling_usd"),
                          "billed_usd": usage.get("billed_usd"),
                          "calls": usage.get("calls")},
                timestamp_utc=_utc(), stop_reason=None)
            self.recorder.record(entry)
            self.dispatch.call(ledger_module.accrue, entry, self.store.db_path,
                               self.budget)


def drive_probe(campaign: Campaign, spec: ProbeSpec, seed: SeedRecord) -> dict:
    """Run one probing input through stages 3 to the gate, and record what happened."""
    out = {"probe_id": spec.probe_id, "arm": spec.arm, "seed_sha": spec.seed_sha,
           "iteration": spec.iteration, "stages": [], "verdicts": {},
           "stopping_stage": "stage_3", "stopping_reason": "not_run",
           "probe_result": None, "candidate_id": None}
    artefact_dir = probe_dir(campaign.manifest, spec.seed_sha, spec.iteration,
                             spec.probe_id)
    write_artefact(artefact_dir, PARTIAL, b"")
    write_probe(campaign.store, spec, artefact_dir)
    try:
        return _drive_probe(campaign, spec, seed, out, artefact_dir)
    finally:
        _close_probe(campaign, out, artefact_dir)


def _close_probe(campaign: Campaign, out: dict, artefact_dir: str) -> None:
    """Write the probe's own row and clear its PARTIAL marker (FR-17.8)."""
    result = out["probe_result"]
    if result is None:
        return
    result.stopping_stage = out["stopping_stage"]
    result.stopping_reason = out["stopping_reason"]
    write_probe_result(campaign.store, result, artefact_dir)
    write_artefact(artefact_dir, PARTIAL, None, store=campaign.store)


def _drive_probe(campaign: Campaign, spec: ProbeSpec, seed: SeedRecord, out: dict,
                 artefact_dir: str) -> dict:
    """`drive_probe`'s body, under the marker its caller wrote (§6.5)."""
    def stop(stage: str, reason: str) -> dict:
        out["stopping_stage"] = stage
        out["stopping_reason"] = reason
        return out

    try:
        executed = campaign.call("probe_execute", campaign.stages.probe_execute,
                                 spec, campaign.image_spec, campaign.limits,
                                 artefact_dir, _arm=spec.arm, _key=spec.probe_id)
    except Exception as error:
        out["stages"].append("stage_3")
        return stop("stage_3", f"stage_3_error:{type(error).__name__}")
    build, result = executed["build_result"], executed["probe_result"]
    out["stages"].append("stage_3")
    out["verdicts"]["stage_3"] = build.status
    out["probe_result"] = result
    campaign.recorder.record(result)
    write_build_result(campaign.store, build)
    if build.status == _UNDECIDED_STATUS:
        return stop("stage_3", result.stopping_reason)
    if build.status not in _FIRING_STATUSES:
        return _drive_differential(campaign, spec, build, result, out,
                                   artefact_dir, stop)

    try:
        verdict = campaign.call("oracle_primary", campaign.stages.oracle_primary,
                                build, campaign.image_spec, artefact_dir,
                                _arm=spec.arm, _key=spec.probe_id)["verdict"]
    except Exception as error:
        out["stages"].append("stage_4")
        return stop("stage_4", f"stage_4_error:{type(error).__name__}")
    out["stages"].append("stage_4")
    out["verdicts"]["stage_4"] = verdict.oracle_class or "not_fired"
    write_oracle_verdict(campaign.store, verdict)
    if not verdict.fired:
        return stop("stage_4", "oracle_did_not_fire")
    result.oracle_fired = True
    result.oracle_class = verdict.oracle_class
    result.assertion_text = verdict.assertion_text
    result.assertion_site = verdict.assertion_site
    result.stopping_stage = "stage_4"

    try:
        reduced = campaign.call("reduce_case", campaign.stages.reduce_case, spec,
                                verdict, campaign.limits, artefact_dir,
                                _arm=spec.arm, _key=spec.probe_id)["reduced"]
    except Exception as error:
        out["stages"].append("stage_5")
        return stop("stage_5", f"stage_5_error:{type(error).__name__}")
    out["stages"].append("stage_5")
    out["verdicts"]["stage_5"] = reduced.reducer if reduced.reduced else "unreduced"
    result.reduced_path = reduced.path
    result.stopping_stage = "stage_5"
    write_reduced_case(campaign.store, reduced)

    candidate = _candidate(spec, build, verdict, reduced, campaign.manifest,
                           artefact_dir, campaign.budget.fingerprint_top_n)
    out["candidate_id"] = candidate.candidate_id
    try:
        screen = campaign.call("dedup_and_screen", campaign.stages.dedup_and_screen,
                               candidate, seed, verdict, campaign.clone_path,
                               campaign.store.db_path,
                               campaign.budget.fingerprint_top_n, _arm=spec.arm,
                               _key=spec.probe_id)
    except Exception as error:
        out["stages"].append("stage_6")
        return stop("stage_6", f"stage_6_error:{type(error).__name__}")
    out["stages"].append("stage_6")
    dedup = screen["dedup"]
    out["verdicts"]["stage_6"] = dedup.verdict
    candidate = dataclasses.replace(
        candidate, fingerprint=screen["fingerprint"].value,
        fingerprint_stable=screen["fingerprint"].fingerprint_stable,
        structural_hash=screen["fingerprint"].structural_hash,
        dedup_basis=screen["fingerprint"].basis, dedup_verdict=dedup.verdict,
        dedup_evidence=dedup.evidence,
        contaminated_symbol=screen["contaminated_symbol"],
        contaminated_file=screen["contaminated_file"],
        contamination_lower_bound=screen["contamination_lower_bound"])
    result.stopping_stage = "stage_6"

    try:
        report = campaign.call(
            "triage_report", campaign.stages.triage_report, candidate, reduced,
            verdict, dedup, campaign.manifest,
            campaign.cfg(iteration=spec.iteration),
            artefact_dir, _arm=spec.arm, _key=spec.probe_id)
    except Exception as error:
        return stop("stage_6", f"stage_6_error:{type(error).__name__}")
    out["verdicts"]["report"] = report.get("failure") or "rendered"
    write_report(campaign.store, report["report"])

    repair = _drive_repair(campaign, spec, candidate, reduced, verdict, dedup,
                           report, out, result)

    try:
        decision = campaign.call("gate_decide", campaign.stages.gate_decide,
                                 candidate, reduced, dedup, repair,
                                 campaign.manifest, campaign.store.db_path,
                                 limits=campaign.limits,
                                 top_n=campaign.budget.fingerprint_top_n,
                                 bin_dir=campaign.bin_dir,
                                 minimal_case_lines=campaign.budget.minimal_case_lines,
                                 _arm=spec.arm, _key=spec.probe_id)["decision"]
    except Exception as error:
        out["stages"].append("gate")
        return stop("gate", f"gate_error:{type(error).__name__}")
    out["stages"].append("gate")
    out["verdicts"]["gate"] = decision.decision
    result.stopping_stage = "gate"
    write_gate_decision(campaign.store, decision)
    return stop("gate", decision.taxonomy_bucket or decision.decision)


def _report_text(report) -> str:
    """The rendered report a repair turn carries, or "" when none was written."""
    try:
        return Path(report.path).read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return ""


def _drive_repair(campaign: Campaign, spec: ProbeSpec, candidate: CandidateRecord,
                  reduced, verdict, dedup, report: dict, out: dict, result):
    """Stage 7 for one NEW candidate, the loop's own row written before CHIA's."""
    if not campaign.repair_enabled:
        return None
    # A known or duplicate candidate is already somebody's issue: repairing it
    # buys nothing and is the most expensive stage of the loop.
    if getattr(dedup, "verdict", None) != "new":
        out["verdicts"]["stage_7"] = f"skipped:{getattr(dedup, 'verdict', None)}"
        return None
    from circt_bug_loop.repair_adapter import (build_cfg, issue_solver_dir,
                                               mint_local_id)

    repair = None
    try:
        local_id = mint_local_id(campaign.store, candidate.candidate_id)
        write_repair_dispatch(
            campaign.store, candidate.candidate_id, local_id,
            repro_dir=str(Path(campaign.manifest.artefact_root)
                          / campaign.manifest.run_manifest_id / "repair"
                          / str(local_id)),
            backend=campaign.manifest.model_ids["repair_adapt"].partition(":")[0])
        solver = issue_solver_dir()
        cfg = {**build_cfg(candidate, campaign.manifest, local_id=local_id,
                           budget=campaign.budget,
                           report_text=_report_text(report["report"]),
                           spend_usd=campaign.spend_usd(),
                           issue_solver=solver),
               # The two keys the LOOP reads.
               "repair_enabled": campaign.repair_enabled,
               "repair_backend": campaign.repair_backend}
        repair = campaign.call(
            "repair_adapt", campaign.stages.repair_adapt, report["report"],
            candidate, reduced, verdict, campaign.manifest, cfg,
            local_id=local_id, input_path=reduced.path or spec.input_path,
            chia_artifact_dir=str(solver / "issue_logs" / f"issue_{local_id}"),
            _arm=spec.arm, _key=spec.probe_id)["result"]
        out["verdicts"]["stage_7"] = repair.status
        write_repair_result(campaign.store, repair)
    except Exception as error:
        out["verdicts"]["stage_7"] = f"refused:{type(error).__name__}"
    out["stages"].append("stage_7")
    result.stopping_stage = "stage_7"
    return repair


def _drive_differential(campaign: Campaign, spec: ProbeSpec, build, result,
                        out: dict, artefact_dir: str, stop) -> dict:
    """B4, for the probes FR-08.1 admits, and the report-only candidate it can make."""
    from circt_bug_loop.probe_task import differential_applicable

    applicable, _reason = differential_applicable(spec)
    if not applicable:
        return stop("stage_3", result.stopping_reason)
    try:
        verdict = campaign.call(
            "oracle_differential", campaign.stages.oracle_differential, spec,
            build, campaign.image_spec, artefact_dir, limits=campaign.limits,
            bin_dir=campaign.bin_dir, _arm=spec.arm, _key=spec.probe_id)["verdict"]
    except Exception as error:
        out["stages"].append("stage_4")
        return stop("stage_4", f"stage_4_error:{type(error).__name__}")
    out["stages"].append("stage_4")
    out["verdicts"]["differential"] = verdict.verdict
    write_differential_verdict(campaign.store, verdict)
    result.stopping_stage = "stage_4"
    if verdict.verdict not in ("diverge", "diverge_x_policy"):
        return stop("stage_4", f"differential:{verdict.verdict}")

    candidate = CandidateRecord(
        candidate_id=f"c-{spec.probe_id}", probe_id=spec.probe_id,
        run_manifest_id=campaign.manifest.run_manifest_id, arm=spec.arm,
        run_commit=campaign.manifest.run_commit[0].commit,
        image_digest=campaign.manifest.image_spec["image_digest"],
        oracle_class="differential", frame_tuple=[], frames_resolved=0,
        frames_with_location=0, out_of_scope_root=False,
        contaminated_symbol=False, contaminated_file=False,
        contamination_lower_bound="seed_commit" if spec.arm == "seeded"
                                  else "run_commit",
        triage_class="untriaged", artefact_dir=artefact_dir)
    write_candidate(campaign.store, candidate)
    out["candidate_id"] = candidate.candidate_id
    try:
        report = campaign.call(
            "triage_report", campaign.stages.triage_report, candidate, None, None,
            None, campaign.manifest,
            campaign.cfg(iteration=spec.iteration),
            artefact_dir, differential=verdict, _arm=spec.arm, _key=spec.probe_id)
    except Exception as error:
        return stop("stage_6", f"stage_6_error:{type(error).__name__}")
    out["stages"].append("stage_6")
    out["verdicts"]["report"] = report.get("failure") or "rendered"
    write_report(campaign.store, report["report"])
    result.stopping_stage = "stage_6"
    return stop("stage_6", f"differential:{verdict.verdict}")


def drive_seed(campaign: Campaign, seed: SeedRecord, arm: str, *,
               deadline: Optional[float] = None) -> dict:
    """Run one seed's iterations on one arm: generate, then every probe it wrote."""
    out = {"seed_sha": seed.seed_sha, "arm": arm, "iterations": 0, "probes": [],
           "verdicts": {}, "terminating_condition": "iteration_cap"}
    bundle = empty_feedback(campaign.manifest, seed, arm, 1)
    snapshot = None
    for iteration in range(1, campaign.budget.per_seed_iteration_cap + 1):
        if deadline is not None and campaign.now() >= deadline:
            out["terminating_condition"] = "arm_window"
            return out
        # PER ITERATION, not once per seed (W10).
        aggregate = ledger_module.aggregate(campaign.manifest.run_manifest_id,
                                            campaign.store.db_path)
        snapshot = budget_module.snapshot(aggregate, arm, campaign.budget)
        cfg = campaign.cfg(iteration=iteration, spend_usd=aggregate.spend_usd)
        try:
            generated = campaign.call(
                f"generate_{arm}", campaign.stages.generator(arm), seed, bundle,
                snapshot, cfg, _arm=arm, _key=f"{seed.seed_sha}:{iteration}")
        except Exception as error:
            out["terminating_condition"] = f"generator_failed:{type(error).__name__}"
            return out
        if generated.get("failure"):
            stage = _failed_stage(generated.get("logs"))
            out["verdicts"][stage] = {
                "failure": generated["failure"],
                "failure_detail": generated.get("failure_detail")}
            write_turn_failure(
                campaign.store, campaign.manifest.run_manifest_id, seed.seed_sha,
                arm, iteration, stage, generated["failure"],
                generated.get("failure_detail"))
        if _spend_refused(generated.get("failure")):
            out["terminating_condition"] = "campaign_spend_cap"
            return out
        out["iterations"] = iteration
        specs = list(generated.get("specs", []))
        for spec in specs:
            campaign.recorder.record(spec)
        results = []
        for spec in specs:
            probe = drive_probe(campaign, spec, seed)
            out["probes"].append(probe)
            if probe["probe_result"] is not None:
                results.append(probe["probe_result"])
        if not specs:
            # A4 skips a seed whose own test its entry tool no longer accepts.
            out["terminating_condition"] = (
                generated["failure"] if generated.get("failure") == STALE_AT_BUILD
                else "no_probe_written")
            return out
        bundle = _next_feedback(campaign, results, bundle, seed, iteration,
                                [s.probe_id for s in specs], snapshot,
                                len(out["probes"]))
        campaign.recorder.record(bundle)
        write_feedback(campaign.store, bundle,
                       str(Path(iteration_dir(campaign.manifest, seed.seed_sha,
                                              bundle.iteration)) / "feedback.json"))
        if bundle.abandoned:
            out["terminating_condition"] = "abandoned"
            return out
    return out


def _failed_stage(logs) -> str:
    """The stage of the LAST turn a failed generator started; `logs` keeps its order."""
    turns = list(((logs or {}).get("wall_seconds") or {}))
    return _TURN_OF.get(turns[-1] if turns else "", "stage_2")


def _spend_refused(failure: Optional[str]) -> bool:
    """Whether a stage's recorded failure is W1's pre-authorisation refusing."""
    return bool(failure) and failure.endswith("SpendCapRefused")


def _next_feedback(campaign: Campaign, results: list, previous: FeedbackBundle,
                   seed: SeedRecord, iteration: int, dispatched: list,
                   snapshot, probes_this_seed: int) -> FeedbackBundle:
    """A5's bundle for the next iteration, imported at the call site (1.3 rule 2)."""
    from circt_bug_loop import feedback as feedback_module

    return campaign.dispatch.call(
        feedback_module.build_feedback, results, previous, seed.seed_sha,
        iteration + 1, dispatched,
        run_manifest_id=campaign.manifest.run_manifest_id,
        budget=campaign.budget, remaining=snapshot,
        probes_this_seed=probes_this_seed)["bundle"]


def campaign_drive(campaign: Campaign, seeds: list, *, arms=None) -> dict:
    """Run the arms one after the other, each for the same window W (FR-14.5)."""
    order = list(arms if arms is not None else campaign.manifest.arm_order)
    out = {"arms": {}, "seeds": [], "counters": campaign.counters.totals,
           "violations": campaign.counters.violations, "stopped": None}
    for arm in order:
        if out["stopped"] == "campaign_spend_cap":
            out["arms"][arm] = {"stop_reason": "campaign_spend_cap", "seconds": 0.0,
                                "seeds": 0, "probes": 0, "started": False}
            continue
        started = campaign.now()
        deadline = started + campaign.budget.arm_window_seconds
        reason = None
        seeds_run = probes_run = 0
        for seed in seeds:
            reason = _arm_stop(campaign, arm, deadline)
            if reason:
                break
            record = drive_seed(campaign, seed, arm, deadline=deadline)
            out["seeds"].append(record)
            seeds_run += 1
            probes_run += len(record["probes"])
            # W1: a turn refused by the pre-authorisation stops the arm HERE.
            if record["terminating_condition"] == "campaign_spend_cap":
                reason = "campaign_spend_cap"
                break
        reason = reason or _arm_stop(campaign, arm, deadline) or "seed_set_exhausted"
        seconds = round(campaign.now() - started, 6)
        out["arms"][arm] = {"stop_reason": reason, "seconds": seconds,
                            "seeds": seeds_run, "probes": probes_run,
                            "started": True}
        _accrue_arm_window(campaign, arm, seconds, reason)
        if reason == "campaign_spend_cap":
            out["stopped"] = reason
    return out


def _arm_stop(campaign: Campaign, arm: str, deadline: float) -> Optional[str]:
    """The binding stop condition for *arm* right now, or None (FR-18.10)."""
    ledger = ledger_module.aggregate(campaign.manifest.run_manifest_id,
                                     campaign.store.db_path)
    reason = ledger_module.stop_reason(ledger, arm, campaign.budget)
    if reason is not None:
        return reason
    return "arm_window" if campaign.now() >= deadline else None


def accrue_offline(store: LoopStore, manifest: RunManifest, budget: BudgetFile, *,
                   dispatch: Dispatch, recorder: Optional[FixtureRecorder] = None,
                   image_seconds: float = 0.0) -> None:
    """Charge the run's two `shared` occupancies: B1's build and A7's synthesis."""
    from circt_bug_loop import mutators

    synthesised = (mutators.load_set().get("synthesised_utc")
                   or manifest.started_utc)
    for stage, amount, when in (("image", float(image_seconds or 0.0), _utc()),
                                (results_stage(), 0.0, synthesised)):
        entry = LedgerEntry(
            entry_id=uuid.uuid5(uuid.NAMESPACE_URL,
                                f"{manifest.run_manifest_id}/shared/stage/"
                                f"{stage}").hex,
            run_manifest_id=manifest.run_manifest_id, arm="shared", scope="stage",
            stage=stage, unit="wall_clock_seconds", amount=amount, metered=False,
            observed={"cpu_seconds": None, "tokens_in": None, "tokens_out": None,
                      "cached_tokens": None, "cost_usd": None,
                      "authorised_usd": None, "ceiling_usd": None,
                      "billed_usd": None, "calls": None},
            timestamp_utc=when, stop_reason=None)
        if store.query_one("SELECT 1 FROM ledger_entry WHERE entry_id = ?",
                           (entry.entry_id,)) is not None:
            continue
        if recorder is not None:
            recorder.record(entry)
        dispatch.call(ledger_module.accrue, entry, store.db_path, budget)


def results_stage() -> str:
    """The stage name the offline synthesis is charged under (`results.py`'s own)."""
    from circt_bug_loop.results import SYNTHESIS_STAGE

    return SYNTHESIS_STAGE


def _accrue_arm_window(campaign: Campaign, arm: str, seconds: float,
                       reason: str) -> None:
    """Write the arm's one `arm_window` ledger entry, which is FR-14.4's rule."""
    entry = LedgerEntry(
        entry_id=f"{campaign.manifest.run_manifest_id}-{arm}-arm_window",
        run_manifest_id=campaign.manifest.run_manifest_id, arm=arm,
        scope="arm_window", stage="stage_3", unit="wall_clock_seconds",
        amount=float(seconds), metered=True,
        observed={"cpu_seconds": None, "tokens_in": None, "tokens_out": None,
                  "cached_tokens": None, "cost_usd": None, "authorised_usd": None,
                  "ceiling_usd": None, "billed_usd": None, "calls": None},
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        stop_reason=reason)
    campaign.recorder.record(entry)
    campaign.dispatch.call(ledger_module.accrue, entry, campaign.store.db_path,
                           campaign.budget)


def reconcile(store: LoopStore, issues_db: str) -> dict:
    """Mark every loop repair row whose CHIA counterpart never appeared (FR-12.10)."""
    import sqlite3

    rows = store.query("SELECT candidate_id, local_id FROM repair")
    if not rows:
        return {"seen": 0, "missing": [], "issues_db": issues_db}
    present = set()
    if Path(issues_db).exists():
        conn = sqlite3.connect(f"file:{issues_db}?mode=ro", uri=True)
        try:
            present = {r[0] for r in conn.execute("SELECT number FROM issues")}
        except sqlite3.Error:
            present = set()
        finally:
            conn.close()
    missing = []
    for row in rows:
        seen = row["local_id"] in present
        store.update("repair", {"candidate_id": row["candidate_id"]},
                     {"chia_row_seen": int(seen)})
        if not seen:
            missing.append(row["local_id"])
    return {"seen": len(rows) - len(missing), "missing": sorted(missing),
            "issues_db": issues_db}


def build_parser() -> argparse.ArgumentParser:
    """Return 13.1's argument parser, with that table's defaults."""
    parser = argparse.ArgumentParser(prog="bug_loop.py",
                                     description="The closed CIRCT bug loop.")
    parser.add_argument("--mode", required=True, choices=("discovery", "calibration"))
    parser.add_argument("--arm", default="both", choices=("seeded", "mutation", "both"))
    parser.add_argument("--budget", default=DEFAULT_BUDGET)
    parser.add_argument("--cluster-yaml", default=DEFAULT_CLUSTER_YAML)
    parser.add_argument("--clone", default=DEFAULT_CLONE)
    parser.add_argument("--artefact-root", default=DEFAULT_ARTEFACT_ROOT)
    parser.add_argument("--github-token-file", default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--repair-backend", default="vertex", choices=REPAIR_BACKENDS)
    parser.add_argument("--repair-model", default=None)
    parser.add_argument("--no-repair", action="store_true")
    parser.add_argument("--generator", default="model",
                        choices=("model", "recorded"))
    parser.add_argument("--seed-sha", action="append", default=None, metavar="SHA")
    parser.add_argument("--shard", default=None, metavar="K/N")
    parser.add_argument("--image-tag", default=DEFAULT_IMAGE_TAG)
    parser.add_argument("--resume", default=None, metavar="RUN_MANIFEST_ID")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--refresh-mirror", action="store_true")
    parser.add_argument("--draw-calibration", action="store_true")
    parser.add_argument("--record-fixtures", default=None, metavar="DIR")
    parser.add_argument("--print-config", action="store_true")
    parser.add_argument("--forum-post-url", default=None)
    parser.add_argument("--forum-post-date", default=None)
    parser.add_argument("--chia-root", default=str(_CHIA_ROOT))
    return parser


#: Why a seed cannot be calibrated by a run whose image is built at one commit (W-19b #6).
NOT_CALIBRATABLE = "not_calibratable_in_deployment"


def calibratable(seeds, pin_sha: str) -> tuple:
    """Split *seeds* into those a run pinned at *pin_sha* can calibrate, and the rest."""
    eligible = sorted(s.seed_sha for s in seeds
                      if s.sdk_exact and s.llvm_pin == pin_sha)
    chosen = set(eligible)
    return eligible, sorted(s.seed_sha for s in seeds if s.seed_sha not in chosen)


def tag_matches_pin(tag: str, circt_sha: str) -> bool:
    """Whether *tag* names this run's CIRCT commit, bare or with a `-<variant>`.

    A variant is the SAME build re-tagged - `…-u1000` is the assertions image
    with `/workspace/circt` chowned to the uid the workers run as (W-23) - so it
    carries the run's own tool binaries and `check_07_tool_hashes` still proves
    it. A tag naming any other commit is still refused.
    """
    prefix = circt_sha[:12]
    return tag == prefix or (tag.startswith(f"{prefix}-") and len(tag) > len(prefix) + 1)


def parse_shard(value: Optional[str]) -> Optional[tuple]:
    """Parse `--shard K/N` into `(K, N)`, or None when no shard was asked for."""
    if not value:
        return None
    index, slash, count = str(value).partition("/")
    if (not slash or not index.isdigit() or not count.isdigit()
            or int(count) < 1 or not 0 <= int(index) < int(count)):
        raise PreflightFailed(
            "shard",
            f"--shard {value!r} is not K/N with N >= 1 and 0 <= K < N: the "
            "shards of one N partition the corpus and every seed is in exactly "
            "one of them")
    return int(index), int(count)


def seed_shard(seeds: list, shard: Optional[tuple]) -> list:
    """Keep shard K of N by POSITION in the corpus order, which is already fixed."""
    if shard is None:
        return list(seeds)
    index, count = shard
    return [seed for position, seed in enumerate(seeds) if position % count == index]


def seed_subset(seeds: list, named: list, corpus_head_sha: str) -> list:
    """Narrow *seeds* to the SHAs *named*, in the order they were named (W-18)."""
    order = {sha: index for index, sha in enumerate(dict.fromkeys(named))}
    present = {seed.seed_sha for seed in seeds}
    absent = sorted(sha for sha in order if sha not in present)
    if absent:
        raise PreflightFailed(
            "seed_subset",
            f"--seed-sha names {len(absent)} seed(s) the corpus at "
            f"{corpus_head_sha[:12]} does not hold: {absent}")
    return sorted((seed for seed in seeds if seed.seed_sha in order),
                  key=lambda seed: order[seed.seed_sha])


def draw_calibration(*, corpus_head_sha: str, sample_size: int,
                     exact_pin_shas: list) -> list:
    """Draw the calibration sample from the eligible seeds, reproducibly (ADR-D-01)."""
    if len(exact_pin_shas) < sample_size:
        raise ValueError(f"{len(exact_pin_shas)} eligible seeds cannot yield a "
                         f"sample of {sample_size}")
    return sorted(random.Random(corpus_head_sha).sample(sorted(exact_pin_shas),
                                                        sample_size))


def resolved_config(args) -> dict:
    """Return what `--print-config` prints: every resolved path, and no secret."""
    return {"mode": args.mode, "arm": args.arm, "budget": args.budget,
            "cluster_yaml": args.cluster_yaml, "clone": args.clone,
            "artefact_root": args.artefact_root, "image_tag": args.image_tag,
            "loop_db": DB_PATH, "issues_db": ISSUES_DB_PATH,
            "github_token_file": args.github_token_file,
            "model_credential_dir": str(Path.home() / ".config" / "bugloop"),
            "chia_package": str(_CHIA_PKG), "issue_solver": str(_ISSUE_SOLVER),
            "repair_backend": args.repair_backend,
            "generator": args.generator,
            "seed_sha": list(args.seed_sha or []),
            "shard": args.shard,
            "repair_enabled": repair_enabled(args)}


def repair_enabled(args) -> bool:
    """Whether stage 7 runs: `--no-repair` and `--generator recorded` both stop it."""
    return not args.no_repair and args.generator != "recorded"


def check_issue_solver(chia_root: str) -> None:
    """Refuse a checkout whose `examples/circt_issue_solver/` is not beside chia."""
    solver = Path(chia_root) / "examples" / "circt_issue_solver" / "issue_task.py"
    if not solver.exists():
        raise PreflightFailed(
            "issue_solver",
            f"{solver} does not exist: CHIA's example directory is not beside "
            f"the installed package. Pass --chia-root <a CHIA checkout>.")


def worker_probes(dispatch: Dispatch, artefact_root: str, resources: dict) -> dict:
    """Dispatch `artefact_root_probe` once per worker type and collect the booleans."""
    node = ChiaFunction(max_retries=0)(artefact_root_probe)
    probes = {}
    for worker_type, resource in sorted(resources.items()):
        probes[worker_type] = Dispatch(
            remote=dispatch.remote, options={"resources": dict(resource)},
            head_node_id=dispatch.head_node_id).call(node, artefact_root)
    return probes


def interlock_probes(dispatch: Dispatch, resources: dict) -> dict:
    """Dispatch `interlock_probe` once per worker type that runs a model turn."""
    node = ChiaFunction(max_retries=0)(interlock_probe)
    probes = {}
    for worker_type, resource in sorted(resources.items()):
        probes[worker_type] = Dispatch(
            remote=dispatch.remote, options={"resources": dict(resource)},
            head_node_id=dispatch.head_node_id).call(node)
    return probes


def run_campaign(args, out) -> int:
    """The whole run: twelve checks, the manifest, both arms, the reconciliation."""
    from chia.cluster.config import load_config
    from chia.trace.metrics import MetricsLogger

    from circt_bug_loop import corpus, mutators, pin_select, triage_task

    started_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repo_root = str(FLOW_DIR.parent)

    check_issue_solver(args.chia_root)
    check_15_entrypoint_imports()
    # Before anything is dispatched.
    shipped = stage_shipped()
    # A run that reports a result is a campaign and needs the registration tag.
    budget = check_01_budget_registered(
        budget_path=args.budget, repo_root=repo_root, run_start_utc=started_utc,
        campaign=not (args.dry_run or args.generator == "recorded"))
    registration = budget_module.registration(repo_root)
    check_02_mutator_set_earlier(repo_root=repo_root)
    check_03_clone_head(clone_path=args.clone,
                        corpus_head_sha=budget.corpus_head_sha)
    check_04_artefact_root_head(artefact_root=args.artefact_root)

    cluster = cluster_summary(args.cluster_yaml)
    config = load_config(args.cluster_yaml)
    resources = {name: dict(node_type.resources)
                 for name, node_type in config.node_types.items()}
    stale = clear_stale_ray_cluster()
    if stale is not None:
        print(f"pre-flight: removed a stale {RAY_CURRENT_CLUSTER} naming "
              f"{stale}, which no cluster answers (errata row 37)", file=out)
    ray.init(address="auto", runtime_env=runtime_env(shipped),
             ignore_reinit_error=True)
    # The driver IS the head (13.1's B12 row).
    dispatch = Dispatch(remote=True, head_node_id=_head_node_id())

    check_05_artefact_root_workers(
        artefact_root=args.artefact_root,
        probes=worker_probes(dispatch, args.artefact_root, resources))

    pin = dispatch.call(pin_select.select_release_pinned_main, args.clone,
                        ref="origin/main")
    check_09_pin_stamped(pin=pin)

    dockerfile, context = dockerfile_and_context()
    built = dispatch.call(build_image, pin["run_commit"], pin["pin_tag"],
                          IMAGE_TARGETS, IMAGE_FLAG_STRING, dockerfile,
                          context=context, inspect_only=args.dry_run)
    image_spec = built["image_spec"]
    if args.image_tag and not tag_matches_pin(args.image_tag,
                                              image_spec.circt_sha):
        raise PreflightFailed(
            "image_tag", f"--image-tag {args.image_tag!r} is not the CIRCT SHA "
            f"prefix this run pinned, {image_spec.circt_sha[:12]!r} "
            f"({image_spec.image_tag!r}), with or without a `-<variant>` "
            f"suffix: the cluster would run a different image from the one "
            "this run records")
    check_06_image_lit_discovery(image_spec=image_spec)
    # W2: the observations are the WORKERS' own.
    observations = tool_probes(
        dispatch,
        {name: resources[name] for name in cluster["image_worker_types"]},
        CIRCT_BIN_DIR, IMAGE_TARGETS)
    check_07_tool_hashes(
        image_spec=image_spec,
        observed={name: probe["tool_hashes"] for name, probe in observations.items()})
    check_08_verilator_version(
        image_spec=image_spec,
        observed={name: probe["verilator_version"]
                  for name, probe in observations.items()})

    store = LoopStore(DB_PATH)
    mirror = _mirror(store, budget, args, dispatch, triage_task)
    check_10_issue_mirror(mirror=mirror, refresh_requested=args.refresh_mirror)
    check_11_forum_post(forum_post_url=args.forum_post_url,
                        forum_post_date=args.forum_post_date,
                        filings_total=budget.filings_total)
    # W4: `--generator recorded` exists so the whole dispatch path can be exercised with no model turn and no credential.
    if args.generator == "recorded":
        print("generator recorded: check 12 is skipped, no turn is made and no "
              "credential is needed anywhere", file=out)
    else:
        model_resources = {name: resource for name, resource in resources.items()
                           if "llm" in resource
                           or ("repair" in resource and repair_enabled(args))}
        check_12_live_model(
            # The head is checked only where a turn would be built there, and under Ray it never is.
            head=None if ray.is_initialized() else interlock_probe(),
            workers=interlock_probes(dispatch, model_resources))
    repair_backend = check_13_vertex_branch(
        issue_task_path=shipped["issue_task"],
        repair_backend=args.repair_backend,
        repair_enabled=repair_enabled(args))
    check_14_vertex_usage_patch(vertex_path=shipped["vertex"],
                                metered=args.generator != "recorded")
    print(f"shipped package at {shipped['root']}; patches applied: "
          + (", ".join(shipped["applied"]) or "none, both already upstream"),
          file=out)

    mined = dispatch.call(corpus.build_corpus, args.clone, budget.corpus_head_sha,
                          corpus_since(args.clone, budget.corpus_head_sha),
                          budget.artefact_inline_cap_bytes)
    seeds = list(mined["seeds"])
    # W-18: a PILOT drives a named subset of the corpus.
    if args.seed_sha:
        seeds = seed_subset(seeds, args.seed_sha, budget.corpus_head_sha)
        print(f"--seed-sha: {len(seeds)} of {len(mined['seeds'])} mined seeds, "
              "in the order named", file=out)
    # W-23: the seeded arm split over machines, the corpus order already fixed.
    shard = parse_shard(args.shard)
    if shard is not None:
        seeds = seed_shard(seeds, shard)
        print(f"--shard {args.shard}: {len(seeds)} seeds, every {shard[1]}th "
              f"from position {shard[0]}", file=out)
    # FR-02.7, as W-19b #6 leaves it.
    eligible, _ineligible = calibratable(seeds, pin["pin_sha"])
    sample = [s for s in (budget.calibration_sample_shas or []) if s in eligible]
    if args.mode == "calibration" and not sample:
        raise PreflightFailed(
            "calibration_sample",
            f"none of the {len(budget.calibration_sample_shas or [])} registered "
            f"calibration seeds has the run's pin {pin['pin_sha'][:12]}: "
            f"{len(eligible)} of {len(seeds)} mined seeds are eligible at all, so "
            f"every sampled seed is {NOT_CALIBRATABLE} and a calibration run "
            "would measure detection at the wrong commit (FR-02.7, W-19b #6)")
    if args.mode == "calibration":
        mined = {**mined, "exclusions": {
            **dict(mined.get("exclusions") or {}),
            **{sha: NOT_CALIBRATABLE for sha in _ineligible}}}
    manifest = build_manifest(
        args=args, budget=budget, pin=pin, image_spec=image_spec, mirror=mirror,
        cluster=cluster, mutator_set_sha=mutators.set_sha256(),
        repair_backend=repair_backend,
        run_manifest_id=args.resume or uuid.uuid4().hex, started_utc=started_utc,
        calibration_seeds=[s for s in seeds if s.seed_sha in sample],
        shard=args.shard or None,
        sv_seeds_excluded=(None if image_spec.slang_enabled
                           else list(mined["sv_seeds"])))
    run_root = Path(args.artefact_root) / manifest.run_manifest_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "manifest.json").write_text(schema.to_json(manifest), encoding="utf-8")
    shutil.copyfile(args.budget, run_root / "budget.yaml")

    recorder = FixtureRecorder(args.record_fixtures)
    recorder.record(manifest)
    recorder.record(budget)
    # 6.4's first four tables, before a stage can reference one of them, and before --dry-run returns.
    write_run_rows(store, manifest, image_spec=image_spec, mined=mined,
                   mirror=mirror, registration=registration)
    accrue_offline(store, manifest, budget, dispatch=dispatch, recorder=recorder,
                   image_seconds=getattr(built.get("counters"), "seconds", 0.0))
    print(f"manifest {manifest.run_manifest_id} at {run_root}", file=out)
    if args.dry_run:
        print("--dry-run: every pre-flight check ran and nothing was dispatched",
              file=out)
        return 0

    # The blobless backfill, once, before the first screen and the first turn.
    subprocess.run(["git", "-C", args.clone, "backfill", "--sparse"],
                   capture_output=True, timeout=1800)
    counters = CounterLog(manifest.run_manifest_id,
                          str(run_root / "results"),
                          MetricsLogger.from_config(None))
    recorded = args.generator == "recorded"
    print(f"generator {args.generator}: stage 2 and stage 6 are "
          + ("the recorded nodes and no model is reached; stage 7 is off"
             if recorded else "the live nodes"), file=out)
    campaign = Campaign(manifest=manifest, budget=budget, store=store,
                        stages=recorded_stages() if recorded else default_stages(),
                        dispatch=dispatch,
                        counters=counters, recorder=recorder,
                        clone_path=args.clone, image_spec=image_spec,
                        repair_enabled=repair_enabled(args),
                        repair_backend=repair_backend,
                        head_options=dispatch.head_options())
    arms = None if args.arm == "both" else [args.arm]
    outcome = campaign_drive(campaign, seeds, arms=arms)
    outcome["reconciliation"] = reconcile(store, ISSUES_DB_PATH)
    finish_run(store, manifest, _utc())

    from circt_bug_loop import results as results_module

    # W-19b #4: the artefact is rendered AFTER the ledger and the store are complete.
    (run_root / "results").mkdir(parents=True, exist_ok=True)
    try:
        rendered = results_module.render_results(
            store, manifest,
            labelled_pairs=results_module.load_labelled_pairs(),
            fingerprint_top_n=budget.fingerprint_top_n)["rendered"]
    except results_module.ResultsIncomplete as refusal:
        (run_root / "results" / "results_refused.txt").write_text(
            "\n".join(refusal.missing) + "\n", encoding="utf-8")
        print(f"the results artefact refused to render; "
              f"{len(refusal.missing)} element(s) named in "
              f"{run_root / 'results' / 'results_refused.txt'}", file=out)
        print(json.dumps(outcome["arms"], sort_keys=True, indent=2), file=out)
        return 3
    (run_root / "results" / "results.md").write_text(rendered, encoding="utf-8")
    print(json.dumps(outcome["arms"], sort_keys=True, indent=2), file=out)
    return 0


def _mirror(store: LoopStore, budget: BudgetFile, args, dispatch: Dispatch,
            triage_task) -> Optional[dict]:
    """Refresh the issue mirror, or return the existing one's meta row (FR-10.9)."""
    existing = store.query_one(
        "SELECT refreshed_utc, issues_mirrored, issue_cap, cap_bound, state, "
        "comments_mirrored FROM issue_mirror_meta ORDER BY refreshed_utc DESC")
    if existing and not args.refresh_mirror:
        return {**existing, "cap_bound": bool(existing["cap_bound"]),
                "comments_mirrored": bool(existing["comments_mirrored"]),
                "incomplete_reason": None}
    if not args.refresh_mirror:
        rows = store.query_one(
            "SELECT COUNT(*) AS mirrored, MAX(mirrored_utc) AS refreshed "
            "FROM issue_mirror")
        if rows and rows["mirrored"]:
            cap = int(budget.issue_mirror_issue_cap)
            return {"refreshed_utc": rows["refreshed"],
                    "issues_mirrored": int(rows["mirrored"]),
                    "issue_cap": cap, "cap_bound": int(rows["mirrored"]) >= cap,
                    # The table can hold nothing else.
                    "state": "all", "comments_mirrored": False,
                    "incomplete_reason": None}
    return dispatch.call(triage_task.issue_mirror_refresh, "llvm/circt",
                         budget.issue_mirror_issue_cap, args.github_token_file,
                         store.db_path)


def main(argv: Optional[list] = None, out=None) -> int:
    """Parse argv, run the pre-flight checks, build the manifest, drive the campaign."""
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.print_config:
        print(json.dumps(resolved_config(args), sort_keys=True, indent=2), file=out)
        return 0
    if args.draw_calibration:
        from circt_bug_loop import corpus, pin_select

        budget = budget_module.load_budget._chia_original(
            args.budget, str(FLOW_DIR.parent))["budget"]
        mined = corpus.build_corpus._chia_original(
            args.clone, budget.corpus_head_sha,
            corpus_since(args.clone, budget.corpus_head_sha),
            budget.artefact_inline_cap_bytes)
        # The draw is from the ELIGIBLE seeds since W-20b (W-19b #6).
        pin = pin_select.select_release_pinned_main._chia_original(
            args.clone, ref="origin/main")
        eligible, ineligible = calibratable(mined["seeds"], pin["pin_sha"])
        print(f"pin {pin['pin_sha']}: {len(eligible)} of {len(mined['seeds'])} "
              f"seeds are calibratable, {len(ineligible)} are "
              f"{NOT_CALIBRATABLE}", file=out)
        if len(eligible) < budget.calibration_sample_size:
            print(f"no sample of {budget.calibration_sample_size} can be drawn "
                  f"(FR-02.7, W-19b #6)", file=sys.stderr)
            return 2
        print("\n".join(draw_calibration(
            corpus_head_sha=budget.corpus_head_sha,
            sample_size=budget.calibration_sample_size,
            exact_pin_shas=eligible)), file=out)
        return 0
    try:
        return run_campaign(args, out)
    except PreflightFailed as error:
        print(f"pre-flight refused the run: {error}", file=sys.stderr)
        return 2
    except (ImageBuildError, BuildTimeout, OSError, ValueError) as error:
        print(f"the run stopped: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":            # pragma: no cover - the program's entry
    sys.exit(main())
