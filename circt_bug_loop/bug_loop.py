"""B12, the campaign driver, and B1's `build_image` (03-LLD.md 3.11, 4.11.1, 13.1).

The driver is a program and not a node: it parses argv, runs the twelve
pre-flight checks, builds the one `RunManifest`, opens both stores, sequences
the two arm windows one after the other, logs every returned `CounterBlock`,
reconciles against CHIA's own `issues.db` and renders the results.

Three things this module does differently from 03-LLD.md 13.1, each recorded in
design/reviews/implementation-errata-log.md and each for one reason:

  * the stage nodes are reached through `Stages`, a record of nine callables,
    and dispatched through `Dispatch`, which is `chia_remote` under Ray and the
    node's own undecorated body without it. That is what makes one whole
    iteration runnable at T0 with no cluster, which is what W-17's join needs
    before it wires the real nodes together.
  * `--dry-run` still dispatches nothing: it stops after the manifest, exactly
    as 13.1's table says. The in-process path above is `campaign_drive`'s
    `remote=False`, which the driver never takes on its own.
  * the path constants are derived from the IMPORTED `chia` module and never
    from this file's ancestors, because the flow lives at two different depths
    in two trees (1.4). `chia.__path__[0]`, not `chia.__file__`, which is None
    for a namespace package.
"""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import logging
import os
import random
import shutil
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
from circt_bug_loop.contract.schema import (BudgetFile, CounterBlock, FeedbackBundle,
                                            LedgerEntry, ProbeSpec, RunCommit,
                                            RunManifest, SeedRecord)
from circt_bug_loop.store import (PARTIAL, CandidateRecord, ImageSpec, LoopStore,
                                  validate_candidate, write_artefact)

logger = logging.getLogger("circt_bug_loop")

# ---------------------------------------------------------------------------
# The four path constants (13.1)
# ---------------------------------------------------------------------------

#: The flow directory, in either tree. Nothing here walks past it.
FLOW_DIR = Path(__file__).resolve().parent
#: The INSTALLED chia package. `chia.__file__` is None for a namespace package.
_CHIA_PKG = Path(chia.__path__[0]).resolve()
#: Its checkout, if it is one; `examples/` sits beside the package there.
_CHIA_ROOT = _CHIA_PKG.parent
_ISSUE_SOLVER = _CHIA_ROOT / "examples" / "circt_issue_solver"

#: 13.1's `py_modules` entries, in its order, shipped by the driver's own
#: `ray.init`. Fifteen and not the table's fourteen: `llm.py` is the join's own
#: module (3.5.1, architect decision 3) and every stage that reaches a model
#: imports it, so a CHIA checkout that shipped the other fourteen would ship no
#: backend at all. See `runtime_env` below for the one substitution this tree
#: forces on the list.
_PY_MODULES = [
    str(FLOW_DIR / "probe_task.py"),
    str(FLOW_DIR / "generate_task.py"),
    str(FLOW_DIR / "llm.py"),
    str(FLOW_DIR / "triage_task.py"),
    str(FLOW_DIR / "repair_adapter.py"),
    str(FLOW_DIR / "gate.py"),
    str(FLOW_DIR / "store.py"),
    str(FLOW_DIR / "corpus.py"),
    str(FLOW_DIR / "pin_select.py"),
    str(FLOW_DIR / "ddmin.py"),
    str(FLOW_DIR / "mutators"),
    str(FLOW_DIR / "contract"),
    str(_CHIA_PKG),
    str(_ISSUE_SOLVER / "issue_task.py"),
    str(_ISSUE_SOLVER / "circt_util.py"),
]
_RUNTIME_ENV_EXCLUDES = ["**/__pycache__", "**/*.pyc"]

#: Defaults for 13.1's argument table.
DEFAULT_BUDGET = str(FLOW_DIR / "budget.yaml")
DEFAULT_CLUSTER_YAML = str(FLOW_DIR / "cluster_single.yaml")
DEFAULT_CLONE = str(Path.home() / ".cache" / "circt")
DEFAULT_TOKEN_FILE = str(Path.home() / ".config" / "circt_bug_loop" / "github_token")
DEFAULT_ARTEFACT_ROOT = os.environ.get("BUGLOOP_ARTEFACTS", "")
DEFAULT_IMAGE_TAG = os.environ.get("BUGLOOP_IMAGE_TAG", "")
DEFAULT_REGISTRY = "ghcr.io/ucb-bar"
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

#: B1's two build parameters that are neither argv nor budget.yaml: the six
#: targets ADR-D-13 branch (a) builds and FR-03.4's flag string, both as the
#: measured image at `eade0de61bc5` carries them (W-04).
IMAGE_TARGETS = ("circt-opt", "firtool", "circt-translate", "arcilator",
                 "circt-reduce", "circt-verilog")
IMAGE_FLAG_STRING = "-O3 -UNDEBUG -gline-tables-only"

#: Step 3's evidence that the pin equality check RAN, which is distinct from
#: its passing: the Dockerfile prints this on the `then` branch and
#: `PIN CHECK FAILED` and `exit 1` on the other, so a build whose log carries
#: neither has lost the layer (FR-03.2).
PIN_CHECK_LINE = "PIN CHECK PASSED"

#: The statuses at which a probe carries on to stage 4 (FR-06.9, 3.6).
_FIRING_STATUSES = ("assertion", "fatal_error", "crash")

#: Which stage id each dispatched callable's counters belong to (3.11).
_STAGE_OF = {"generate_seeded": "stage_2", "generate_mutation": "stage_2",
             "probe_execute": "stage_3", "oracle_primary": "stage_4",
             "oracle_differential": "stage_4", "reduce_case": "stage_5",
             "dedup_and_screen": "stage_6", "triage_report": "stage_6",
             "repair_adapt": "stage_7", "gate_decide": "gate"}

#: Which stage id each of A3's two agent turns occupies, which is
#: `generate_task._TURN_STAGE` read from the other side: the generator is one
#: node and two stages, so its occupancy is charged as two ledger entries and
#: not as one (3.11, FR-14.8).
_TURN_OF = {"seed_read": "stage_1", "probe_write": "stage_2"}


class PreflightFailed(Exception):
    """One pre-flight check refused the run. Carries the check's name (13.1)."""

    def __init__(self, check: str, detail: str):
        self.check = check
        self.detail = detail
        super().__init__(f"{check}: {detail}")


class ImageBuildError(Exception):
    """A step of `build_image` failed. Carries the step's name (4.11.1)."""

    def __init__(self, step: str, detail: str):
        self.step = step
        self.detail = detail
        super().__init__(f"{step}: {detail}")


class BuildTimeout(Exception):
    """`build_image` exceeded its whole-sequence timeout (4.11.1)."""

    def __init__(self, timeout_seconds: int):
        self.timeout_seconds = timeout_seconds
        super().__init__(f"the image build exceeded {timeout_seconds} s")


# ---------------------------------------------------------------------------
# Placement, and the runtime environment
# ---------------------------------------------------------------------------


def _head_node_id() -> str:
    """Return the Ray node id of the process calling this, which is the head.

    Called only from the driver and from head nodes, after ray.init(), so the
    current node IS the head. It is the value NodeAffinitySchedulingStrategy
    takes, and the value a ChiaTool's task_options takes to place its server on
    the head (3.5's SourceReadTool).

    Returns:
        the node id as a hex string.
    Worker:
        the caller's; it reads the runtime context and dispatches nothing.
    Raises:
        RuntimeError from Ray if called before ray.init().
    """
    return ray.get_runtime_context().get_node_id()


def _head_options() -> dict:
    """Return the scheduling_strategy dict that pins a task to the head."""
    return {"scheduling_strategy":
            NodeAffinitySchedulingStrategy(node_id=_head_node_id(), soft=False)}


def runtime_env() -> dict:
    """Return the `runtime_env` the driver's own `ray.init` ships (13.1).

    13.1's `_PY_MODULES` names nine loose files under the flow directory, which
    is right in a CHIA checkout where the example's modules import each other by
    bare name. In the team repository the same modules are a package and import
    each other as `circt_bug_loop.<module>`, which a loose file cannot satisfy,
    so where `__init__.py` is present the flow's own nine entries are replaced by
    the package DIRECTORY and the other five travel unchanged. Both forms ship
    the same code; only the import path differs.

    Returns:
        {"py_modules": list[str], "excludes": list[str]}.
    Worker:
        the driver's; it reads the filesystem and dispatches nothing.
    Raises:
        nothing.
    """
    if not (FLOW_DIR / "__init__.py").exists():
        return {"py_modules": list(_PY_MODULES), "excludes": list(_RUNTIME_ENV_EXCLUDES)}
    outside = [m for m in _PY_MODULES if not m.startswith(str(FLOW_DIR) + os.sep)]
    return {"py_modules": [str(FLOW_DIR)] + outside,
            "excludes": list(_RUNTIME_ENV_EXCLUDES)}


class Dispatch:
    """How the driver reaches a stage node: through Ray, or in this process.

    Under Ray a node is dispatched with `.options(**overrides).chia_remote(...)`
    and collected with CHIA's own `get`. Without Ray the node's undecorated body
    runs here, which is `04-Test-Plan.md` 0.4's plain call and is what makes one
    whole iteration runnable at T0. The decorator stays on every node either
    way, so 3.2's placement table is unchanged.
    """

    def __init__(self, *, remote: bool = True, options: Optional[dict] = None):
        """Take the dispatch mode and the per-call `.options()` override."""
        self.remote = remote
        self.options = dict(options or {})

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        """Run one stage node and return what it returned.

        Returns:
            whatever *fn* returns.
        Worker:
            the node's own, declared by its decorator; this method chooses only
            between dispatching it and running it here.
        Raises:
            whatever *fn* raises, and whatever Ray re-raises from the worker.
        """
        if self.remote and isinstance(fn, ChiaFunction):
            handle = fn.options(**self.options) if self.options else fn
            return get(handle.chia_remote(*args, **kwargs))
        return getattr(fn, "_chia_original", fn)(*args, **kwargs)


# ---------------------------------------------------------------------------
# B1, build_image (4.11.1)
# ---------------------------------------------------------------------------


def image_manifest(circt_sha: str, sdk_tag: str, targets, flag_string: str,
                   *, slang: bool = True,
                   base_image: str = DEFAULT_BASE_IMAGE) -> dict:
    """Return 4.11.1's six-key hash manifest, the thing the image tag digests.

    `targets` is sorted here and only here: the argument order the caller chose
    must not change the tag, and the UNSORTED list is what step 2 passes and
    what `ImageSpec.targets` records, that being FR-03.7's parameter.

    Returns:
        {"circt_sha", "sdk_tag", "targets", "flag_string", "slang",
         "base_image"}.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
    return {"circt_sha": circt_sha, "sdk_tag": sdk_tag,
            "targets": sorted(targets), "flag_string": flag_string,
            "slang": bool(slang), "base_image": base_image}


def image_tag(registry: str, manifest: dict) -> str:
    """Return `<registry>/chia-circt-assert:<first 12 hex of the manifest digest>`.

    Returns:
        str, the tag, which is 3.2's idempotency key made addressable.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        TypeError from json.dumps on a manifest holding a non-serialisable value.
    """
    digest = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        .encode("utf-8")).hexdigest()
    return f"{registry}/chia-circt-assert:{digest[:12]}"


def build_argv(dockerfile: str, tag: str, manifest: dict, context: str) -> list:
    """Return 4.11.1 step 2's `docker build` argument list, in its order.

    No `--progress=plain`: it is a BuildKit flag, a host with the legacy builder
    only rejects the whole build with rc 125 before anything runs, and the
    legacy builder's output is already the per-step plain text the flag asked
    for (4.11 deviation 7). No shell, as everywhere else here.

    Returns:
        list[str], ready for subprocess.Popen.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        KeyError when *manifest* is not `image_manifest`'s six keys.
    """
    return ["docker", "build", "-f", dockerfile, "-t", tag,
            "--build-arg", f"CIRCT_SHA={manifest['circt_sha']}",
            "--build-arg", f"CIRCT_VER={manifest['sdk_tag']}",
            "--build-arg", f"TOOL_TARGETS={' '.join(manifest['targets'])}",
            "--build-arg", f"CXX_FLAGS_RELEASE={manifest['flag_string']}",
            "--build-arg", f"SLANG={'ON' if manifest['slang'] else 'OFF'}",
            "--build-arg", f"BASE_IMAGE={manifest['base_image']}",
            context]


def parse_hash_manifest(document: dict) -> dict:
    """Flatten a recorded image manifest's `tool_hashes` to name -> SHA-256.

    The recorded form (`analysis/measurements/raw/image-manifest.json`) maps a
    tool to `{"path", "sha256"}`, because the path is what a re-hash inside a
    fresh container has to be told; `ImageSpec.tool_hashes` is the flat map, and
    FR-06.1's comparison is against that. A value that is already a plain hex
    string passes through, so the flattening is idempotent.

    Returns:
        dict[str, str], one entry per target.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        KeyError when the document carries no `tool_hashes`; TypeError when an
        entry is neither a string nor a mapping carrying `sha256`.
    """
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
    """Read FR-03.17's two figures off one `lit --show-tests` run.

    A non-zero exit, or ANY `fatal: unable to parse config file` line, is not a
    discovery: it means `lit.site.cfg.py` did not resolve `mlir_src_root` and
    the suite the image ships cannot be run at all. Both block publication.

    Returns:
        (ok: bool, discovered: int), the count being the number of lines lit
        listed under its `-- Available Tests --` heading.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
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


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def build_image(circt_sha: str, sdk_tag: str, targets: tuple, flag_string: str,
                dockerfile: str, registry: str, *, slang: bool = True,
                push: bool = True, base_image: str = DEFAULT_BASE_IMAGE,
                context: str = ".", artefact_dir: Optional[str] = None,
                baseline_objects: Optional[list] = None,
                timeout_seconds: int = 10800) -> dict:
    """Build, check and publish the assertions-on CIRCT image, or reuse it.

    4.11.1's eight steps in its order, stopping at the first failure: tag and
    reuse; `docker build` with the six build arguments; the pin check's own line
    in the build log; FR-03.17's lit discovery; every target's `--version`; the
    hash manifest from a FRESHLY STARTED container and never from the build
    tree; FR-03.5's non-referencing `obj.CIRCT` objects compared as a SET
    against the committed baseline; and the push, which nothing reaches unless
    every step above passed, so a partial build leaves no image under the
    requested tag.

    Returns:
        {"image_spec": ImageSpec, "reused": bool, "counters": CounterBlock},
        where reused is True exactly when step 1 short-circuited.
    Worker:
        {"circt": 1} - it needs a Docker daemon and the CIRCT worker type is the
        one that has one. It holds the slot for the whole build, which is why B1
        runs once, before the arms, and never inside an arm window.
    Raises:
        ImageBuildError(step, detail) for a failure at any of steps 2 to 8, with
            *step* the name above and *detail* the command's stderr tail.
        BuildTimeout(timeout_seconds) when the whole sequence exceeds its
            timeout; the partial image is not pushed and the local tag is
            removed, so a later run does not find a half-built image under the
            key it would have reused.
    """
    started = time.monotonic()
    manifest = image_manifest(circt_sha, sdk_tag, targets, flag_string,
                              slang=slang, base_image=base_image)
    tag = image_tag(registry, manifest)
    deadline = started + timeout_seconds

    existing = _run(["docker", "image", "inspect", tag], timeout=60)
    if existing["rc"] == 0:
        spec = _image_spec(tag, manifest, targets, timeout=int(deadline - time.monotonic()),
                           artefact_dir=artefact_dir, baseline=baseline_objects)
        return {"image_spec": spec, "reused": True,
                "counters": _counter_block("image", 1, 1, 0, started)}

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
        if push:
            pushed = _run(["docker", "push", tag],
                          timeout=int(deadline - time.monotonic()))
            if pushed["rc"] != 0:
                raise ImageBuildError("publish", pushed["stderr"][-4000:])
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

    digest = _run(["docker", "image", "inspect",
                   "--format={{index .RepoDigests 0}}", tag], timeout=60)
    return ImageSpec(
        circt_sha=manifest["circt_sha"], sdk_tag=manifest["sdk_tag"],
        targets=list(targets), flag_string=manifest["flag_string"],
        cmake_args=[], image_digest=digest["stdout"].strip() or tag,
        image_tag=tag, verilator_version=verilator["stdout"].strip(),
        slang_enabled=manifest["slang"], lit_discovery_ok=ok,
        lit_discovered_count=discovered,
        assertion_nonreferencing=nonreferencing, tool_hashes=hashes)


#: W-04's own object scan (`analysis/measurements/w04_verify_in_image.sh:38-45`),
#: which measured 555 `obj.CIRCT` objects, 536 referencing and 19 not. One
#: container and one `nm` per object; the paths are printed relative to the
#: build directory, which is the shape `image/baseline_objects.txt` records.
_OBJECT_SCAN = r'''
find /workspace/circt/build -path "*obj.CIRCT*.dir*" -name "*.o" | sort |
while read -r o; do
  nm --undefined-only "$o" 2>/dev/null | grep -q __assert_fail ||
    echo "${o#/workspace/circt/build/}"
done'''


def _assertion_objects(tag: str, targets, *, timeout: int) -> list:
    """FR-03.5's two halves: every target binary, then the objects behind them.

    Step 7 is `nm -u` over each target binary for `__assert_fail`, which must be
    present in all of them, and the list of `obj.CIRCT` objects that do not
    reference it, which is what the committed baseline is compared against as a
    set. A binary without the symbol is an assertions-off build and stops the
    publication here rather than at the first probe that does not fire.
    """
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


# ---------------------------------------------------------------------------
# The twelve pre-flight checks (13.1), each stopping the run
# ---------------------------------------------------------------------------


def _git(repo_root: str, *args: str, timeout: int = 60) -> str:
    """One `git -C <repo_root> ...` read, no shell, stripped stdout."""
    proc = subprocess.run(["git", "-C", repo_root, *args], capture_output=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise PreflightFailed("git", proc.stderr.decode(
            "utf-8", errors="backslashreplace").strip())
    return proc.stdout.decode("utf-8", errors="backslashreplace").strip()


def check_01_budget_registered(*, budget_path: str, repo_root: str,
                               run_start_utc: str, exact_pin_shas=None) -> BudgetFile:
    """Check 1: budget.yaml is committed and its commit predates the run (FR-14.2).

    `budget.load_budget` is the one place the six registration checks live, so
    this check runs them rather than restating them; FR-05.2's mutator-set rule
    is check 2 and runs inside the same call (W-06 erratum 6).

    Returns:
        BudgetFile, which every later check and the manifest read.
    Worker:
        head; one subprocess per git read.
    Raises:
        PreflightFailed("budget_registered", detail) wrapping BudgetError.
    """
    try:
        return budget_module.load_budget._chia_original(
            budget_path, repo_root, run_start_utc=run_start_utc,
            exact_pin_shas=exact_pin_shas)["budget"]
    except budget_module.BudgetError as error:
        raise PreflightFailed("budget_registered", str(error)) from error


def check_02_mutator_set_earlier(*, budget: BudgetFile, repo_root: str,
                                 flow_dir: str = str(FLOW_DIR)) -> None:
    """Check 2: the mutator set's last commit predates the budget file's (FR-05.2).

    Returns:
        None.
    Worker:
        head; one subprocess per git read.
    Raises:
        PreflightFailed("mutator_set_earlier", detail).
    """
    try:
        budget_module._check_frozen_set(repo_root, flow_dir, budget.budget_file_sha,
                                        budget_module._last_commit(
                                            repo_root,
                                            budget_module._relative(
                                                str(Path(flow_dir) / "budget.yaml"),
                                                repo_root))[1])
    except budget_module.BudgetError as error:
        raise PreflightFailed("mutator_set_earlier", str(error)) from error


def check_03_clone_head(*, clone_path: str, corpus_head_sha: str,
                        head_sha: Optional[str] = None) -> None:
    """Check 3: the clone's HEAD equals `corpus_head_sha`, naming both (FR-01.11).

    *head_sha* is the value a test supplies instead of running git, which is
    what keeps this check tier 0.

    Returns:
        None.
    Worker:
        head; one `git rev-parse HEAD` against the blobless clone.
    Raises:
        PreflightFailed("clone_head", detail) naming both SHAs.
    """
    actual = head_sha if head_sha is not None else _git(clone_path, "rev-parse", "HEAD")
    if actual != corpus_head_sha:
        raise PreflightFailed(
            "clone_head", f"{clone_path} is at {actual!r}, and budget.yaml's "
            f"corpus_head_sha is {corpus_head_sha!r}")


def check_04_artefact_root_head(*, artefact_root: str) -> None:
    """Check 4: the artefact root exists and is writable on the head (FR-17.9).

    Returns:
        None.
    Worker:
        head; one write and one removal under the root.
    Raises:
        PreflightFailed("artefact_root_head", detail) naming the path.
    """
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
    """Write and remove one file under *artefact_root*, and report only whether it worked.

    Dispatched once per worker type by check 5. It returns a boolean and the
    worker's own name, never the directory listing and never a path it did not
    receive.

    Returns:
        {"writable": bool, "worker": str, "detail": str | None}.
    Worker:
        one per worker type; the check dispatches it at each type's resource.
    Raises:
        nothing; an unwritable root is the returned False.
    """
    import socket

    path = Path(artefact_root) / f".bugloop_write_check_{uuid.uuid4().hex}"
    try:
        path.write_text("", encoding="utf-8")
        path.unlink()
    except OSError as error:
        return {"writable": False, "worker": socket.gethostname(), "detail": str(error)}
    return {"writable": True, "worker": socket.gethostname(), "detail": None}


def check_05_artefact_root_workers(*, artefact_root: str, probes: dict) -> None:
    """Check 5: the artefact root is writable on every worker type (FR-17.9).

    *probes* maps a worker type's name to what `artefact_root_probe` returned on
    it; the driver fills it by dispatching one trivial node per type, and a test
    passes a mapping.

    Returns:
        None.
    Worker:
        head, dispatching one node per worker type.
    Raises:
        PreflightFailed("artefact_root_unmounted", detail) naming the worker
        type and the path, which is FR-17.9's own failure name.
    """
    for worker_type, result in sorted(probes.items()):
        if not result.get("writable"):
            raise PreflightFailed(
                "artefact_root_unmounted",
                f"{worker_type} cannot write {artefact_root}: "
                f"{result.get('detail')}")


def check_06_image_lit_discovery(*, image_spec: ImageSpec) -> None:
    """Check 6: the image exists and its `lit_discovery_ok` is true (FR-03.17).

    Returns:
        None.
    Worker:
        head; it reads the recorded ImageSpec and runs nothing.
    Raises:
        PreflightFailed("image_lit_discovery", detail).
    """
    if image_spec is None:
        raise PreflightFailed("image_lit_discovery", "no ImageSpec: the image was "
                              "neither built nor recorded")
    if not image_spec.lit_discovery_ok:
        raise PreflightFailed(
            "image_lit_discovery",
            f"{image_spec.image_tag} discovered {image_spec.lit_discovered_count} "
            "tests and lit_discovery_ok is false; publication is blocked (FR-03.17)")


def check_07_tool_hashes(*, image_spec: ImageSpec, observed: dict) -> None:
    """Check 7: every tool binary's SHA-256 on every worker matches (FR-06.1).

    *observed* maps a worker type to that worker's own tool-name-to-hash map.

    Returns:
        None.
    Worker:
        head, reading one hash map per worker type.
    Raises:
        PreflightFailed("tool_hashes", detail) naming the worker, the tool and
        both hashes.
    """
    for worker_type, hashes in sorted(observed.items()):
        for tool, expected in sorted(image_spec.tool_hashes.items()):
            actual = hashes.get(tool)
            if actual != expected:
                raise PreflightFailed(
                    "tool_hashes",
                    f"{worker_type}: {tool} hashes {actual!r}, and the ImageSpec "
                    f"records {expected!r}")


def check_08_verilator_version(*, image_spec: ImageSpec, observed: dict) -> None:
    """Check 8: every CIRCT worker's Verilator is the image's (FR-03.15).

    A changed Verilator starts a new campaign, so a difference stops the run
    naming both versions rather than being recorded and carried.

    Returns:
        None.
    Worker:
        head, reading one version string per CIRCT worker type.
    Raises:
        PreflightFailed("verilator_version", detail) naming both.
    """
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
    """Check 9: the pin selector ran and every pin field is stamped (FR-02.1 to 02.4).

    A2 returns eight fields and seven of them are manifest fields; `resolved_utc`
    is the eighth and has no manifest home (W-07 erratum 7), so it is required
    of the return and not of the manifest.

    Returns:
        None.
    Worker:
        head; it reads A2's return and runs nothing.
    Raises:
        PreflightFailed("pin_stamped", detail) naming every missing field.
    """
    missing = [f for f in PIN_FIELDS if pin.get(f) is None]
    if missing:
        raise PreflightFailed("pin_stamped",
                              f"the pin selector returned no {sorted(missing)}")


def check_10_issue_mirror(*, mirror: Optional[dict], refresh_requested: bool) -> None:
    """Check 10: the mirror is refreshed, or an existing one is reused (FR-10.9).

    Returns:
        None.
    Worker:
        head; the mirror is a table in the head-pinned loop.db.
    Raises:
        PreflightFailed("issue_mirror", detail) when neither a refresh nor a
        reusable mirror is available, and when a refresh came back incomplete.
    """
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
                        forum_post_date: Optional[str]) -> None:
    """Check 11: the method's forum post exists before the campaign starts (FR-20.1).

    Returns:
        None.
    Worker:
        head; it reads two argv values and makes no request.
    Raises:
        PreflightFailed("forum_post", detail) naming the missing one.
    """
    missing = [name for name, value in (("forum_post_url", forum_post_url),
                                        ("forum_post_date", forum_post_date))
               if not value]
    if missing:
        raise PreflightFailed(
            "forum_post",
            f"{sorted(missing)} not supplied: FR-20.1 posts the method to "
            "CIRCT's forum before the campaign starts")


def interlock_probe(*, env=None, need_key: bool = True) -> dict:
    """Report whether the live-model interlock and the key are set, and NEVER their values.

    The two rules are `generate_task.require_live_model`'s: the interlock is
    exactly "1", and the key is non-empty and is not an unexpanded `${...}`
    reference, which is what an operator's shell leaves behind when the variable
    the cluster YAML names is itself unset. *env* is the mapping to read, so a
    test passes one explicitly and no test ever sets the real variable
    (architect's decision, 2026-09-14).

    Returns:
        {"interlock_ok": bool, "key_ok": bool} - two booleans and no value.
    Worker:
        one per `llm` worker, and one per `repair` worker where repair is
        enabled; dispatched by check 12 and by nothing else.
    Raises:
        nothing.
    """
    source = os.environ if env is None else env
    key = (source.get(API_KEY_ENV) or "").strip()
    return {"interlock_ok": source.get(LIVE_MODEL_ENV) == "1",
            "key_ok": bool(key) and not key.startswith("${") if need_key else True}


def check_12_live_model(*, head: dict, workers: dict) -> None:
    """Check 12: the interlock and the key are set, and agree, on head and workers.

    *head* and each value of *workers* is what `interlock_probe` returned there,
    which is two booleans; this check never sees a credential. A failure names
    the worker and the variable and stops the run before one turn is dispatched,
    so a campaign cannot discover the misconfiguration eight seeds in.

    Returns:
        None.
    Worker:
        head, dispatching one trivial node per `llm` worker and, where repair is
        enabled, per `repair` worker (3.8, 12.1's two `-e` lines).
    Raises:
        PreflightFailed("live_model", detail) naming the place and the variable.
    """
    for where, result in [("head", head)] + sorted(workers.items()):
        if not result.get("interlock_ok"):
            raise PreflightFailed(
                "live_model", f"{where}: {LIVE_MODEL_ENV} is not exactly '1'")
        if not result.get("key_ok"):
            raise PreflightFailed(
                "live_model", f"{where}: {API_KEY_ENV} is empty or unexpanded")


#: The twelve checks in 13.1's order, cheapest first, named for the log.
PREFLIGHT_CHECKS = (
    "budget_registered", "mutator_set_earlier", "clone_head",
    "artefact_root_head", "artefact_root_unmounted", "image_lit_discovery",
    "tool_hashes", "verilator_version", "pin_stamped", "issue_mirror",
    "forum_post", "live_model")


# ---------------------------------------------------------------------------
# The manifest, and every field's producer (13.1)
# ---------------------------------------------------------------------------


def cluster_summary(cluster_yaml: str) -> dict:
    """Return the four manifest fields the cluster YAML produces, plus its digest.

    Returns:
        {"cluster_yaml_sha", "worker_type", "apparatus_concurrency",
         "llm_concurrency", "deployment"}.
    Worker:
        head; it reads one file through CHIA's own loader.
    Raises:
        chia.cluster.config.ConfigError when the file will not load; KeyError
        when it declares no `circt` or no `llm` worker type.
    """
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
                          else "single_machine"}


def model_ids(*, model_id: str, repair_backend: str,
              repair_model: Optional[str] = None) -> dict:
    """Return 2.7's four `"<backend>:<model id>"` strings (13.1, 3.8).

    Three stages take the pre-registered model on the campaign backend; stage 7
    takes `--repair-backend` and `--repair-model`, which on a default run are
    the same pair, `vertex:<budget.yaml's model_id>`.

    Returns:
        dict with exactly the keys generate_seeded, triage_report, repair_adapt
        and mutator_synthesis.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ValueError on an empty model id, which would put a colon with nothing
        after it into the manifest.
    """
    if not model_id:
        raise ValueError("budget.yaml's model_id is empty")
    backend = _model_backend()
    campaign = f"{backend}:{model_id}"
    repair = f"{repair_backend}:{repair_model or model_id}"
    return {"generate_seeded": campaign, "triage_report": campaign,
            "mutator_synthesis": campaign, "repair_adapt": repair}


def stages_metered(*, arms, repair_backend: str, repair_enabled: bool) -> dict:
    """Return one bool per stage id: whether the loop can meter that stage (FR-14.8).

    Stages 1 and 2 are metered only where the seeded arm runs, no model running
    on the mutation arm at all; stage 7 is metered exactly where its backend is
    the campaign's, which on a default run it is.

    Returns:
        dict whose key set is exactly the contract's `_STAGE_IDS`.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
    seeded = "seeded" in tuple(arms)
    metered = {stage: True for stage in schema._STAGE_IDS}
    metered["stage_1"] = seeded
    metered["stage_2"] = seeded
    metered["stage_7"] = bool(repair_enabled) and repair_backend == _METERED_REPAIR_BACKEND
    return metered


def _model_backend() -> str:
    """The campaign backend, read from `llm.py`'s own constant (3.5.1)."""
    from circt_bug_loop import llm

    return llm.MODEL_BACKEND


def differential_driver() -> dict:
    """Return FR-08.11's four keys from B4's own recorded deviation (3.6.3).

    `circt/arc-tests` was not reused, so `source` names what did drive the
    differential and `commit` is empty. The obstacle and the deviation are the
    two halves of `probe_task.DIFFERENTIAL_DRIVER`, which B4 records verbatim on
    every `DifferentialVerdict`, split at its one semicolon: the manifest and
    the verdict then cannot state different reasons for the same deviation.

    Returns:
        dict with exactly the keys source, commit, deviation and obstacle.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ValueError if the recorded deviation loses its shape, because a manifest
        that silently recorded half of it would satisfy FR-08.11 on paper only.
    """
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
    """Return FR-02.7's `run_commit` list for *mode*, one entry or one per seed.

    Discovery runs at one commit and the entry's `seed_sha` is null; calibration
    runs each sampled seed at its own parent commit, so there is one entry per
    sampled seed and every `seed_sha` is set.

    Returns:
        list[RunCommit].
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ValueError on a calibration mode with no sampled seed, which would make
        the manifest claim a calibration that examined nothing.
    """
    if mode == "discovery":
        return [RunCommit(commit=pin["run_commit"], seed_sha=None)]
    if not seeds:
        raise ValueError("calibration mode with no sampled seed")
    return [RunCommit(commit=s.parent_sha, seed_sha=s.seed_sha) for s in seeds]


def build_manifest(*, args, budget: BudgetFile, pin: dict, image_spec: ImageSpec,
                   mirror: dict, cluster: dict, mutator_set_sha: str,
                   run_manifest_id: str, started_utc: str,
                   calibration_seeds=(), assertion_baseline_count: int = 0,
                   sv_seeds_excluded=None) -> RunManifest:
    """Build the run's one `RunManifest`, every field from its named producer.

    13.1's table is the source for each: argv, A1, A2, A6a, B1, B6a, the cluster
    YAML, 9.4's constants, 3.6.3's differential rule, the image's own acceptance
    run, and the operator. A field with no value stops the run here rather than
    at the first stage that reads it.

    Returns:
        RunManifest, already through `contract.validate`.
    Worker:
        head; it dispatches nothing and reads only what it is handed.
    Raises:
        ContractError from `contract.validate` on any field the seam refuses;
        ValueError from `run_commits` and `model_ids`.
    """
    from circt_bug_loop import probe_task, repair_adapter

    arms = tuple(budget.arm_order) if args.arm == "both" else (args.arm,)
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
                            repair_backend=args.repair_backend,
                            repair_model=args.repair_model),
        stages_metered=stages_metered(arms=arms,
                                      repair_backend=args.repair_backend,
                                      repair_enabled=not args.no_repair),
        mutator_set_sha=mutator_set_sha,
        x_policy=probe_task.X_POLICY,
        issue_mirror={k: mirror[k]
                      for k in schema._DICT_KEYS[("RunManifest", "issue_mirror")]},
        local_id_range=[repair_adapter.LOCAL_ID_BASE, repair_adapter.LOCAL_ID_MAX],
        forum_post_url=args.forum_post_url, forum_post_date=args.forum_post_date,
        confirmation_cutoff_date=budget.campaign_end_utc[:10],
        differential_driver=differential_driver(),
        started_utc=started_utc,
        calibration_sample=(list(budget.calibration_sample_shas)
                            if args.mode == "calibration" else None),
        sv_seeds_excluded=sv_seeds_excluded)
    schema.validate(manifest)
    return manifest


# ---------------------------------------------------------------------------
# The counters, and how the driver logs them (3.11, FR-17.4)
# ---------------------------------------------------------------------------


def _counter_block(stage: str, started: int, completed: int, failed: int,
                   since: float) -> CounterBlock:
    """One CounterBlock for a unit of work that began at *since* (monotonic)."""
    return CounterBlock(stage=stage, started=started, completed=completed,
                        failed=failed, seconds=round(time.monotonic() - since, 6))


class CounterLog:
    """FR-17.4's per-stage counters, accumulated per (run, arm, stage) on the head.

    One record per RETURNED block, as 3.11 says: the driver reads each return's
    `counters` key, checks `started == completed + failed`, hands the block to
    CHIA's `MetricsLogger`, and rewrites `results/counters.json` on every
    aggregation so that inspecting a running campaign is a file read (NFR-09).
    A node that returns no block has one SYNTHESISED from the driver's own
    timing, and the synthesis is recorded as a named violation rather than
    passed off as the node's own count.
    """

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
        """Fold one block into this run's totals and log it.

        Returns:
            None.
        Worker:
            head; one file rewrite per call, no dispatch.
        Raises:
            ValueError on a block whose stage is outside `_COUNTER_STAGES`,
            which is the one thing a counter may not invent.
        """
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
        """Rewrite `results/counters.json` with the running totals.

        Returns:
            str, the path written, or None when no results directory was given.
        Worker:
            head; one file write.
        Raises:
            OSError from the write.
        """
        if not self.results_dir:
            return None
        Path(self.results_dir).mkdir(parents=True, exist_ok=True)
        path = Path(self.results_dir) / "counters.json"
        path.write_text(json.dumps(
            {"run_manifest_id": self.run_manifest_id, "totals": self.totals,
             "violations": self.violations},
            sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(path)


# ---------------------------------------------------------------------------
# The seam recorder (02-HLD.md 2.13, --record-fixtures)
# ---------------------------------------------------------------------------

#: Which field names an instance of each member, for the recorded file's name.
_FIXTURE_ID = {"SeedRecord": "seed_sha", "BudgetFile": "budget_file_sha",
               "ProbeSpec": "probe_id", "ProbeResult": "probe_id",
               "LedgerEntry": "entry_id", "RunManifest": "run_manifest_id"}


class FixtureRecorder:
    """`--record-fixtures`: write every produced instance after validate accepts it.

    One JSON document per file at `<dir>/<schema>/<id>.json`, which is the
    layout `contract/fixtures/` uses and the layout the join replays from. A
    fixture that does not validate is a defect in its producer, so validation
    runs first and a refusal propagates.
    """

    def __init__(self, directory: Optional[str]):
        """Take the recording directory, or None to record nothing."""
        self.directory = directory
        self.written: list = []

    def record(self, instance) -> Optional[str]:
        """Validate *instance* and write it under its schema's directory.

        Returns:
            str, the path written, or None when recording is off.
        Worker:
            head; one validate and one file write.
        Raises:
            ContractError from `contract.validate`; OSError from the write.
        """
        if not self.directory:
            return None
        schema.validate(instance)
        name = type(instance).__name__
        if name == "FeedbackBundle":
            # The ARM is part of the identity and W-16 left it out: FR-16.2
            # makes the two arms' bundles for one seed and one iteration
            # DIFFERENT documents, the mutation arm's carrying no entries, and
            # without the arm the second one recorded overwrote the first
            # (found by W-17's recording run).
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


# ---------------------------------------------------------------------------
# The rows the driver writes (6.2, 6.4)
# ---------------------------------------------------------------------------

#: Each table's column list, read once per process from the schema `loop.db`
#: was created with. Repeating §6.2's DDL here as tuples would be a second
#: spelling of it, and two spellings of one DDL is how a value gets written
#: into the column beside the one it belongs in.
_TABLE_COLUMNS: dict = {}

#: What `_row` treats as "the record does not carry this column", so that a
#: column whose value is legitimately None is still written as NULL.
_ABSENT = object()


def table_columns(store: LoopStore, table: str) -> tuple:
    """Return *table*'s columns, in the order §6.2's DDL declares them.

    Read through the store's own read path, so the names are the ones the file
    actually carries; `pragma_table_info` is a table-valued function and the
    query goes through `LoopStore.query` like every other read, which is what
    keeps the driver's whole database contact on one path (§6.1).

    Returns:
        tuple[str], one name per column.
    Worker:
        {"num_cpus": 0.1} for the one query, once per table per process.
    Raises:
        KeyError when the schema holds no such table, which is a caller defect
        and never a state of the database.
    """
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
    """A `_json` column's text: JSON with sorted keys, dataclasses expanded.

    `OracleVerdict.frames` is a list of `Frame`s and `frames_json` is one
    column, so the expansion belongs here rather than at each of the callers
    that happen to hold a list of records.
    """
    if isinstance(value, list):
        value = [dataclasses.asdict(item) if dataclasses.is_dataclass(item) else item
                 for item in value]
    return json.dumps(value, sort_keys=True)


def _row(store: LoopStore, table: str, record=None, **extra) -> dict:
    """Build one row of *table* from *record*, column by declared column.

    Every column takes the field of its own name off the record, a `_json`
    column taking the field without that suffix; *extra* overrides any column
    and supplies the ones no record carries, which are the run id on a seed,
    the timestamps, and the canonical-JSON documents of whole members. A column
    neither the record nor *extra* carries is left out of the INSERT, so one
    builder serves a table whose record is partial and the DDL's own defaults
    and NULLs still apply.

    Returns:
        dict, column name to value, in the DDL's order.
    Worker:
        head; it reads the schema through the store and writes nothing.
    Raises:
        KeyError from `table_columns` on a table outside the schema.
    """
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


def _utc() -> str:
    """This moment, as the ISO 8601 string every `_utc` column carries."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_run_rows(store: LoopStore, manifest: RunManifest, *,
                   image_spec: ImageSpec, mined: Optional[dict] = None,
                   mirror: Optional[dict] = None) -> None:
    """Write everything §6.4 puts in the store before the first probe is dispatched.

    In the order the foreign keys fix: the `run` row first, because every other
    table's `run_manifest_id` references it; then the `image`, because
    `build_result.image_digest` references its digest; then A1's `seed` rows and
    its `sdk_map`; then B6a's `issue_mirror_meta`, which is keyed by the run.
    Each is written once, so a `--resume` run finds its own rows and adds none,
    and an image built for an earlier run is not inserted twice.

    Returns:
        None.
    Worker:
        {"num_cpus": 0.1} per statement, on the head where loop.db lives.
    Raises:
        sqlite3.IntegrityError from any row the schema refuses.
    """
    run_id = manifest.run_manifest_id
    if store.query_one("SELECT 1 FROM run WHERE run_manifest_id = ?",
                       (run_id,)) is None:
        store.insert("run", _row(store, "run", manifest,
                                 manifest_json=schema.to_json(manifest)))
    if store.query_one("SELECT 1 FROM image WHERE image_digest = ?",
                       (image_spec.image_digest,)) is None:
        store.insert("image", _row(store, "image", image_spec, built_utc=_utc()))

    seeds = list((mined or {}).get("seeds") or ())
    if seeds:
        exclusions = dict((mined or {}).get("exclusions") or {})
        # ADR-D-13 branch (b) only: under branch (a) the slang entry points are
        # built and those seeds run like any other (§5.3).
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
    """Write the `probe_result` row, once, when the probe has stopped.

    `ProbeResult` is "produced by B2 and completed by the stage the probe
    stopped at" (§2.4), so the row is written at the end and carries the
    stopping stage the probe actually reached. It is also the completion record
    that lets the directory's PARTIAL marker be cleared (§6.5), which is why it
    is the last row of a probe rather than the first.
    """
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
    """Write one `candidate` row the screen never sees: a differential one.

    B6b writes the row of every candidate it screens, in one transaction with
    its `fingerprint` and its `dedup_verdict` (§6.4 rule 4), and FR-08.10 keeps
    a `differential` candidate out of that stage entirely, so this is the head's
    own write and the one place the report-only candidate is persisted (§3.6.3).
    `validate_candidate` runs first, as it does on B6b's path.

    Returns:
        None.
    Worker:
        {"num_cpus": 0.1}, on the head.
    Raises:
        ContractError from `validate_candidate`; sqlite3.IntegrityError on a
        second candidate for one probe, `probe_id` being UNIQUE.
    """
    validate_candidate(candidate)
    store.insert("candidate", _row(store, "candidate", candidate,
                                   created_utc=_utc()))


def write_report(store: LoopStore, report) -> None:
    """Write stage 6's `report` row, an unrendered report included (FR-11.8)."""
    store.insert("report", _row(store, "report", report))


def write_repair_dispatch(store: LoopStore, candidate_id: str, local_id: int, *,
                          repro_dir: str, backend: str) -> None:
    """FR-12.10: the loop's row and the candidate's local id, before CHIA's.

    §6.4 rule 1 puts this write **before** `run_issue_remote`, and B8 runs on a
    `repair` worker holding no `loop.db` handle (§3.8), so the head writes the
    row it can know at dispatch time and `write_repair_result` completes it from
    what came back. The two statements are one transaction because a local id on
    a candidate with no repair row, or the reverse, is a state the
    reconciliation cannot read.

    Returns:
        None.
    Worker:
        {"num_cpus": 0.1}, on the head.
    Raises:
        sqlite3.Error from either statement, the batch rolled back.
    """
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
    """Complete the `repair` row from what B8 returned, leaving `chia_row_seen`.

    An UPDATE and not an INSERT: the row was written before the chain ran
    (§6.4 rule 1), and `chia_row_seen` is the reconciliation's column and is not
    this write's to reset.
    """
    fields = _row(store, "repair", result)
    for column in ("candidate_id", "chia_row_seen"):
        fields.pop(column, None)
    store.update("repair", {"candidate_id": result.candidate_id}, fields)


def write_gate_decision(store: LoopStore, decision) -> None:
    """§6.4 rule 4's second batch: the decision row and the candidate's bucket.

    One transaction, because a `gate_decision` row whose candidate carries a
    different bucket is the disagreement the results artefact would then have to
    resolve. `held_reason` travels with the bucket for the same reason: it is
    the gate's own answer about a candidate it refused to pass.
    """
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
    """Write the iteration's `feedback` row and A5's bundle beside it (§6.5).

    The bundle is on disk as `feedback.json` in the iteration directory and the
    row carries the path, which is §6.5's cap rule applied to the one artefact
    the seeded arm reads back.
    """
    write_artefact(str(Path(path).parent), Path(path).name,
                   schema.to_json(bundle))
    store.insert("feedback", _row(store, "feedback", bundle, path=path))


# ---------------------------------------------------------------------------
# The stage table, and the run loop
# ---------------------------------------------------------------------------


@dataclasses.dataclass(kw_only=True)
class Stages:
    """The ten stage callables `campaign_drive` dispatches, as one record.

    They are a parameter and not an import list so that a test can substitute
    the ones that need a CIRCT binary, a clone or a model, and drive the
    sequencing, the verdicts and the counters with nothing installed. The
    default is every real node, and the join wires them together unchanged.
    """
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
    """Return the ten real nodes, imported here so a T0 test need not import them.

    Returns:
        Stages, one field per node of 3.2 the driver dispatches.
    Worker:
        head; it imports and dispatches nothing.
    Raises:
        ImportError when a stage module is missing, which is a broken checkout.
    """
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


def probe_limits(budget: BudgetFile) -> dict:
    """Return the six per-probe and per-reduction limits budget.yaml fixes.

    Returns:
        dict, the keys `probe_task` and `reduce_case` read.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
    return {"probe_wall_seconds": budget.probe_wall_seconds,
            "probe_address_space_bytes": budget.probe_address_space_bytes,
            "probe_cpu_seconds": budget.probe_cpu_seconds,
            "probe_output_byte_cap": budget.probe_output_byte_cap,
            "reduction_wall_seconds": budget.reduction_wall_seconds,
            "reduction_sigkill_grace_seconds": budget.reduction_sigkill_grace_seconds}


def generator_cfg(manifest: RunManifest, budget: BudgetFile, *, clone_path: str,
                  iteration: int, artefact_dir: Optional[str] = None) -> dict:
    """Return the `cfg` A3 and A4 read, built from the manifest and the budget.

    Returns:
        dict with the sixteen keys 3.5's two generators read.
    Worker:
        head; it reads two records and touches no file.
    Raises:
        nothing.
    """
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
            "mutator_set_sha": manifest.mutator_set_sha}


def empty_feedback(manifest: RunManifest, seed: SeedRecord, arm: str,
                   iteration: int) -> FeedbackBundle:
    """Return the bundle the first iteration of a seed reads: no entries at all.

    A5 builds every later one from the iteration's ProbeResults; the first has
    no previous iteration, and the mutation arm's is empty at every iteration
    because it never reads one (FR-16.2).

    Returns:
        FeedbackBundle with an empty `entries` list.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
    return FeedbackBundle(run_manifest_id=manifest.run_manifest_id,
                          seed_sha=seed.seed_sha, arm=arm, iteration=iteration,
                          entries=[], abandoned=False)


def iteration_dir(manifest: RunManifest, seed_sha: str, iteration: int) -> str:
    """Return 6.5's `<root>/<run>/seed_<sha>/iter_<n>`, one seed's one iteration.

    Returns:
        str, the absolute directory; it is not created here.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
    return str(Path(manifest.artefact_root) / manifest.run_manifest_id
               / f"seed_{seed_sha}" / f"iter_{iteration}")


def probe_dir(manifest: RunManifest, seed_sha: str, iteration: int,
              probe_id: str) -> str:
    """Return 6.5's `<root>/<run>/seed_<sha>/iter_<n>/probe_<id>` for one probe.

    Returns:
        str, the absolute directory; it is not created here, every stage that
        writes into it creating its own.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
    return str(Path(iteration_dir(manifest, seed_sha, iteration))
               / f"probe_{probe_id}")


def _candidate(spec: ProbeSpec, build, verdict, reduced, manifest: RunManifest,
               artefact_dir: str, top_n: int) -> CandidateRecord:
    """Assemble the pre-dedup candidate the screen fills in and validates (2.9).

    `frame_tuple` is built here and not read off the verdict, `OracleVerdict`
    carrying `frames` and no tuple: it is B6b's own two lines, the prologue strip
    that must precede every use of a frame (K3) and B3's name normalisation, at
    the same `fingerprint_top_n`, so the row this candidate writes and the
    `Fingerprint` B6b computes from the same verdict cannot disagree.
    """
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
    """The (stage, seconds, usage) occupancies one dispatched call produced.

    One per call, at the node's own stage, except where the return carries a
    per-turn usage map: A3 is one node running stages 1 and 2 and its two turns
    are two occupancies, the turn's own wall clock against the turn's stage and
    the rest of the call against the node's. The seconds of one call's entries
    therefore always sum to the block's own.

    Returns:
        list[tuple[str, float, dict]], never empty.
    Worker:
        pure; it reads two dicts.
    Raises:
        nothing.
    """
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
    """One run's state: the manifest, the budget, the stores and the dispatch.

    It is a record and not a framework: it holds what every stage call needs and
    nothing a stage could have computed for itself.
    """

    def __init__(self, *, manifest: RunManifest, budget: BudgetFile,
                 store: LoopStore, stages: Stages, dispatch: Dispatch,
                 counters: CounterLog, recorder: Optional[FixtureRecorder] = None,
                 clone_path: str = "", image_spec=None, repair_enabled: bool = True,
                 seed_map: Optional[dict] = None, now: Optional[Callable] = None,
                 bin_dir: str = CIRCT_BIN_DIR):
        """Take everything a stage call needs, and compute nothing else."""
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

    def call(self, name: str, fn: Callable, *args, **kwargs):
        """Dispatch one stage, fold its counters in, charge it, and return its result.

        A node that returns a mapping carrying `counters` has that block
        recorded; one that does not has a block synthesised from this call's own
        timing and the synthesis recorded as a violation (3.11). Either way the
        occupancy is charged to the ledger, a stage that failed having occupied
        the apparatus exactly as one that returned.

        Returns:
            whatever the stage returned.
        Worker:
            the stage's own.
        Raises:
            whatever the stage raises; the caller decides what a failure means.
        """
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
        """Append this call's stage occupancy to the ledger, one entry per stage.

        The occupancy is the block's own seconds and the observation is whatever
        usage the node reported, which A6b prices (§3.11's "a counter is never a
        budget": these are different numbers with different owners and both are
        recorded). A3 is one node and two stages, so a return carrying a
        per-turn usage map is charged as two entries and `_TURN_OF` says which.

        Returns:
            None.
        Worker:
            {"num_cpus": 0.1} per entry, through `ledger.accrue` on the head.
        Raises:
            ContractError or sqlite3.IntegrityError from `accrue`, a repeated
            entry id being a double charge and not a duplicate (§6.4 rule 3).
        """
        run_id = self.manifest.run_manifest_id
        for stage, seconds, usage in _occupancies(_STAGE_OF[name], block, out):
            entry = LedgerEntry(
                entry_id=uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"{run_id}/{arm}/stage/{stage}/{name}/{key}").hex,
                run_manifest_id=run_id, arm=arm, scope="stage", stage=stage,
                unit="wall_clock_seconds", amount=max(0.0, round(seconds, 6)),
                metered=bool(self.manifest.stages_metered.get(stage, True)),
                observed={"cpu_seconds": None,
                          "tokens_in": usage.get("tokens_in"),
                          "tokens_out": usage.get("tokens_out"),
                          "cost_usd": None},
                timestamp_utc=_utc(), stop_reason=None)
            self.recorder.record(entry)
            self.dispatch.call(ledger_module.accrue, entry, self.store.db_path,
                               self.budget)


def drive_probe(campaign: Campaign, spec: ProbeSpec, seed: SeedRecord) -> dict:
    """Run one probing input through stages 3 to the gate, and record what happened.

    The stages run in order and each one's outcome decides whether the next runs
    at all: a probe that exits cleanly stops at stage 3, one whose oracle does
    not fire stops at stage 4, and a `differential` candidate never reaches the
    dedup or the gate at all (FR-08.10, FR-13.14).

    Every stage's record lands in its own table as the stage returns it, in
    §6.4's order, and the probe's own directory carries the PARTIAL marker of
    §6.5 from before the first stage runs until the `probe_result` row that
    completes it exists.

    Returns:
        {"probe_id", "arm", "seed_sha", "iteration", "stages": list[str],
         "verdicts": dict[str, str], "stopping_stage", "stopping_reason",
         "probe_result": ProbeResult | None, "candidate_id": str | None}.
    Worker:
        head, dispatching each stage at its own declared resource.
    Raises:
        nothing. A stage that raises is recorded against the probe as
        `<stage>_error:<exception class>` and the probe stops there, because one
        failed probe is not a failed campaign.
    """
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
    """Write the probe's own row and clear its PARTIAL marker (§6.5, FR-17.8).

    A probe whose stage 3 never returned has no `ProbeResult` to write and its
    marker therefore stays, which is the marker doing its job: the directory
    holds whatever the dead stage had written and nothing is deleted.
    """
    result = out["probe_result"]
    if result is None:
        return
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
            generator_cfg(campaign.manifest, campaign.budget,
                          clone_path=campaign.clone_path, iteration=spec.iteration),
            artefact_dir, _arm=spec.arm, _key=spec.probe_id)
    except Exception as error:
        return stop("stage_6", f"stage_6_error:{type(error).__name__}")
    out["verdicts"]["report"] = report.get("failure") or "rendered"
    write_report(campaign.store, report["report"])

    repair = _drive_repair(campaign, spec, candidate, reduced, verdict, report, out,
                           result)

    try:
        decision = campaign.call("gate_decide", campaign.stages.gate_decide,
                                 candidate, reduced, dedup, repair,
                                 campaign.manifest, campaign.store.db_path,
                                 limits=campaign.limits,
                                 top_n=campaign.budget.fingerprint_top_n,
                                 bin_dir=campaign.bin_dir,
                                 _arm=spec.arm, _key=spec.probe_id)["decision"]
    except Exception as error:
        out["stages"].append("gate")
        return stop("gate", f"gate_error:{type(error).__name__}")
    out["stages"].append("gate")
    out["verdicts"]["gate"] = decision.decision
    result.stopping_stage = "gate"
    write_gate_decision(campaign.store, decision)
    return stop("gate", decision.taxonomy_bucket or decision.decision)


def _drive_repair(campaign: Campaign, spec: ProbeSpec, candidate: CandidateRecord,
                  reduced, verdict, report: dict, out: dict, result):
    """Stage 7 for one candidate, the loop's own row written before CHIA's.

    FR-12.10 and §6.4 rule 1: the head mints the identifier, writes it onto the
    candidate and opens the `repair` row, and only then dispatches B8, whose
    worker holds no `loop.db` handle (§3.8). The row is completed from the
    `RepairResult` that comes back; an attempt that never came back leaves the
    row at `dispatched`, which is what the reconciliation then reads.

    Returns:
        RepairResult, or None when repair is disabled or the attempt refused.
    Worker:
        head, dispatching one `{"repair": 1}` node.
    Raises:
        nothing; a refusal is `out["verdicts"]["stage_7"]`.
    """
    if not campaign.repair_enabled:
        return None
    from circt_bug_loop.repair_adapter import mint_local_id

    repair = None
    try:
        local_id = mint_local_id(campaign.store, candidate.candidate_id)
        write_repair_dispatch(
            campaign.store, candidate.candidate_id, local_id,
            # §6.5's repair directory and §3.8's own backend, both derived
            # here because B8 computes them on a worker that cannot write.
            repro_dir=str(Path(campaign.manifest.artefact_root)
                          / campaign.manifest.run_manifest_id / "repair"
                          / str(local_id)),
            backend=campaign.manifest.model_ids["repair_adapt"].partition(":")[0])
        repair = campaign.call(
            "repair_adapt", campaign.stages.repair_adapt, report["report"],
            candidate, reduced, verdict, campaign.manifest,
            generator_cfg(campaign.manifest, campaign.budget,
                          clone_path=campaign.clone_path,
                          iteration=spec.iteration),
            local_id=local_id, input_path=reduced.path or spec.input_path,
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
    """B4, for the probes FR-08.1 admits, and the report-only candidate it can make.

    B4 is not on `probe_execute`'s path and the driver is its only caller
    (§3.6.3), so this is where the applicability rule is asked. It is asked of
    the probes whose primary oracle did not fire: a tool that died has no design
    to simulate, and the crash it died of is stage 4's answer, not stage 4b's.
    A divergence is report-only (FR-08.10) - no reducer, no dedup, no repair and
    no gate - so the driver writes the candidate itself, `dedup_and_screen`
    refusing a `differential` one by design.

    Returns:
        the probe's `out` dict, stopped where the differential left it.
    Worker:
        head, dispatching one `{"circt": 1}` node.
    Raises:
        nothing.
    """
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
            generator_cfg(campaign.manifest, campaign.budget,
                          clone_path=campaign.clone_path, iteration=spec.iteration),
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
    """Run one seed's iterations on one arm: generate, then every probe it wrote.

    The iteration cap is `budget.yaml`'s `per_seed_iteration_cap`; a seed also
    stops when A5 abandons it (FR-16.6) and when the arm's window has expired,
    which is checked between iterations and never inside one, because a probe
    that has started is bounded by its own limits and not by the window.

    Returns:
        {"seed_sha", "arm", "iterations": int, "probes": list[dict],
         "terminating_condition": str}.
    Worker:
        head, dispatching the generator and every stage.
    Raises:
        nothing. A generator that fails ends the seed with
        `terminating_condition="generator_failed:<class>"`.
    """
    out = {"seed_sha": seed.seed_sha, "arm": arm, "iterations": 0, "probes": [],
           "terminating_condition": "iteration_cap"}
    bundle = empty_feedback(campaign.manifest, seed, arm, 1)
    snapshot = budget_module.snapshot(
        ledger_module.aggregate(campaign.manifest.run_manifest_id,
                                campaign.store.db_path), arm, campaign.budget)
    for iteration in range(1, campaign.budget.per_seed_iteration_cap + 1):
        if deadline is not None and campaign.now() >= deadline:
            out["terminating_condition"] = "arm_window"
            return out
        cfg = generator_cfg(campaign.manifest, campaign.budget,
                            clone_path=campaign.clone_path, iteration=iteration)
        try:
            generated = campaign.call(
                f"generate_{arm}", campaign.stages.generator(arm), seed, bundle,
                snapshot, cfg, _arm=arm, _key=f"{seed.seed_sha}:{iteration}")
        except Exception as error:
            out["terminating_condition"] = f"generator_failed:{type(error).__name__}"
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
            out["terminating_condition"] = "no_probe_written"
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


def _next_feedback(campaign: Campaign, results: list, previous: FeedbackBundle,
                   seed: SeedRecord, iteration: int, dispatched: list,
                   snapshot, probes_this_seed: int) -> FeedbackBundle:
    """A5's bundle for the next iteration, imported at the call site (1.3 rule 2).

    A5's arm is read off *snapshot*, which is the only arm-scoped thing a
    generator may see, and `probes_this_seed` is the seed's running probe count,
    which is what FR-16.3's `probe_cap` terminating condition is decided from.
    """
    from circt_bug_loop import feedback as feedback_module

    return campaign.dispatch.call(
        feedback_module.build_feedback, results, previous, seed.seed_sha,
        iteration + 1, dispatched,
        run_manifest_id=campaign.manifest.run_manifest_id,
        budget=campaign.budget, remaining=snapshot,
        probes_this_seed=probes_this_seed)["bundle"]


def campaign_drive(campaign: Campaign, seeds: list, *, arms=None) -> dict:
    """Run the arms one after the other, each for the same window W (FR-14.5).

    The arms are sequential and never overlap, in `budget.yaml`'s `arm_order`,
    from one cluster YAML at one concurrency, which is what makes the wall-clock
    equality mean anything. Each arm stops at the first of: its window; a
    binding safety cap; and the campaign's USD cap, which is campaign-wide and
    stops BOTH arms, so the arm in flight ends and the other never starts
    (FR-18.10, 3.11).

    Returns:
        {"arms": {arm: {"stop_reason", "seconds", "seeds", "probes"}},
         "seeds": list[dict], "counters": dict, "violations": list[str],
         "stopped": str | None}.
    Worker:
        head; it dispatches every stage and runs none of them itself.
    Raises:
        nothing. Every stop is a recorded reason.
    """
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
    """Charge the run's two `shared` occupancies: B1's build and A7's synthesis.

    Neither belongs to an arm and neither runs inside a window, and one of them
    does not run inside the campaign at all. The offline mutator synthesis
    precedes the registration commit (§8.3), so A7 cannot write its own entry -
    `ledger_entry.run_manifest_id` has a foreign key to `run` and no run existed
    when it ran - and it records the date in the frozen set instead. FR-05.8's
    declaration is rendered off this entry's timestamp (§14.4), so the run
    stamps what the set says, and the amount is zero because the frozen set
    records the synthesis date and not its duration.

    Returns:
        None. A run that already carries the two entries adds neither, which is
        what makes `--resume` re-enter here safely.
    Worker:
        {"num_cpus": 0.1} per entry, through `ledger.accrue` on the head.
    Raises:
        sqlite3.IntegrityError on a repeated entry id (§6.4 rule 3).
    """
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
                      "cost_usd": None},
            timestamp_utc=when, stop_reason=None)
        if store.query_one("SELECT 1 FROM ledger_entry WHERE entry_id = ?",
                           (entry.entry_id,)) is not None:
            continue
        if recorder is not None:
            recorder.record(entry)
        dispatch.call(ledger_module.accrue, entry, store.db_path, budget)


def results_stage() -> str:
    """The stage name the offline synthesis is charged under (`results.py`'s own).

    One constant, read from the renderer rather than spelled again here: §9
    names the stage nowhere and `results.SYNTHESIS_STAGE` is what the
    declaration looks the entry up by, so a second spelling here would be the
    one way the two could disagree.
    """
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
                  "cost_usd": None},
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        stop_reason=reason)
    campaign.recorder.record(entry)
    campaign.dispatch.call(ledger_module.accrue, entry, campaign.store.db_path,
                           campaign.budget)


# ---------------------------------------------------------------------------
# The end-of-run reconciliation (FR-12.10)
# ---------------------------------------------------------------------------


def reconcile(store: LoopStore, issues_db: str) -> dict:
    """Mark every loop repair row whose CHIA counterpart never appeared (FR-12.10).

    The join key is `local_id`, which B8 minted inside `local_id_range` so that
    a loop row can never collide with a real issue number. A row CHIA has is
    `chia_row_seen = 1`; one it does not is marked `repair_row_missing`, which is
    a recorded fact and not a repair.

    Returns:
        {"seen": int, "missing": list[int], "issues_db": str}.
    Worker:
        head; both databases are on it.
    Raises:
        sqlite3.Error from either query.
    """
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


# ---------------------------------------------------------------------------
# The CLI (13.1)
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Return 13.1's argument parser, with that table's defaults.

    Three arguments 13.1's table does not list are here and each has a reason
    recorded in the errata log: `--forum-post-url` and `--forum-post-date`,
    without which pre-flight check 11's two manifest fields have no producer at
    all, and `--chia-root`, which 13.1's prose already names as the override for
    a checkout whose `examples/` is not beside the installed package.

    Returns:
        argparse.ArgumentParser.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        nothing.
    """
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


def draw_calibration(*, corpus_head_sha: str, sample_size: int,
                     exact_pin_shas: list) -> list:
    """Draw the calibration sample from the exact-pin seeds, reproducibly (ADR-D-01).

    `random.Random(corpus_head_sha)` is seeded by a value already in the budget
    file, so the draw is reproducible from the file itself and is a step of the
    pre-registration rather than of the run. It writes nothing.

    Returns:
        list[str], *sample_size* seed SHAs, sorted so the printed order is
        stable.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ValueError when the exact-pin set is smaller than the sample.
    """
    if len(exact_pin_shas) < sample_size:
        raise ValueError(f"{len(exact_pin_shas)} exact-pin seeds cannot yield a "
                         f"sample of {sample_size}")
    return sorted(random.Random(corpus_head_sha).sample(sorted(exact_pin_shas),
                                                        sample_size))


def resolved_config(args) -> dict:
    """Return what `--print-config` prints: every resolved path, and no secret.

    Returns:
        dict, path names to resolved values.
    Worker:
        head; it reads argv and the environment and dispatches nothing.
    Raises:
        nothing.
    """
    return {"mode": args.mode, "arm": args.arm, "budget": args.budget,
            "cluster_yaml": args.cluster_yaml, "clone": args.clone,
            "artefact_root": args.artefact_root, "image_tag": args.image_tag,
            "loop_db": DB_PATH, "issues_db": ISSUES_DB_PATH,
            "github_token_file": args.github_token_file,
            "model_credential_dir": str(Path.home() / ".config" / "bugloop"),
            "chia_package": str(_CHIA_PKG), "issue_solver": str(_ISSUE_SOLVER),
            "repair_backend": args.repair_backend,
            "repair_enabled": not args.no_repair}


def check_issue_solver(chia_root: str) -> None:
    """Refuse a checkout whose `examples/circt_issue_solver/` is not beside chia.

    B8 needs CHIA's own `issue_task.py` and `circt_util.py` on the repair
    worker's `sys.path` and FR-12.1 forbids copying them, so a wheel install
    with no `examples/` cannot run stage 7. It bites at start-up rather than at
    the first repair attempt.

    Returns:
        None.
    Worker:
        head; one filesystem check.
    Raises:
        PreflightFailed("issue_solver", detail) naming `--chia-root`.
    """
    solver = Path(chia_root) / "examples" / "circt_issue_solver" / "issue_task.py"
    if not solver.exists():
        raise PreflightFailed(
            "issue_solver",
            f"{solver} does not exist: CHIA's example directory is not beside "
            f"the installed package. Pass --chia-root <a CHIA checkout>.")


def worker_probes(dispatch: Dispatch, artefact_root: str, resources: dict) -> dict:
    """Dispatch `artefact_root_probe` once per worker type and collect the booleans.

    *resources* maps a worker type's name to the resource dict its containers
    advertise, which is what places the probe on that type and on no other.

    Returns:
        dict, worker type to what the probe returned there.
    Worker:
        head, dispatching one trivial node per worker type.
    Raises:
        nothing; a probe that cannot write returns False.
    """
    node = ChiaFunction(max_retries=0)(artefact_root_probe)
    probes = {}
    for worker_type, resource in sorted(resources.items()):
        probes[worker_type] = Dispatch(
            remote=dispatch.remote, options={"resources": dict(resource)}
        ).call(node, artefact_root)
    return probes


def interlock_probes(dispatch: Dispatch, resources: dict) -> dict:
    """Dispatch `interlock_probe` once per worker type that runs a model turn.

    Returns:
        dict, worker type to {"interlock_ok", "key_ok"} - booleans and no value.
    Worker:
        head, dispatching one trivial node per `llm` and `repair` worker type.
    Raises:
        nothing.
    """
    node = ChiaFunction(max_retries=0)(interlock_probe)
    probes = {}
    for worker_type, resource in sorted(resources.items()):
        probes[worker_type] = Dispatch(
            remote=dispatch.remote, options={"resources": dict(resource)}
        ).call(node)
    return probes


def run_campaign(args, out) -> int:
    """The whole run: twelve checks, the manifest, both arms, the reconciliation.

    Returns:
        int, 0 on a completed run and non-zero on a refusal.
    Worker:
        head; it dispatches every stage and runs none of them.
    Raises:
        PreflightFailed, which `main` turns into a named message and a status.
    """
    from chia.cluster.config import load_config
    from chia.trace.metrics import MetricsLogger

    from circt_bug_loop import corpus, mutators, pin_select, triage_task

    started_utc = datetime.now(timezone.utc).isoformat(timespec="seconds")
    repo_root = str(FLOW_DIR.parent)

    check_issue_solver(args.chia_root)
    budget = check_01_budget_registered(budget_path=args.budget,
                                        repo_root=repo_root,
                                        run_start_utc=started_utc)
    check_02_mutator_set_earlier(budget=budget, repo_root=repo_root)
    check_03_clone_head(clone_path=args.clone,
                        corpus_head_sha=budget.corpus_head_sha)
    check_04_artefact_root_head(artefact_root=args.artefact_root)

    cluster = cluster_summary(args.cluster_yaml)
    config = load_config(args.cluster_yaml)
    resources = {name: dict(node_type.resources)
                 for name, node_type in config.node_types.items()}
    ray.init(address="auto", runtime_env=runtime_env(), ignore_reinit_error=True)
    dispatch = Dispatch(remote=True)

    check_05_artefact_root_workers(
        artefact_root=args.artefact_root,
        probes=worker_probes(dispatch, args.artefact_root, resources))

    pin = dispatch.call(pin_select.select_release_pinned_main, args.clone,
                        ref="origin/main")
    check_09_pin_stamped(pin=pin)

    built = dispatch.call(build_image, pin["run_commit"], pin["pin_tag"],
                          IMAGE_TARGETS, IMAGE_FLAG_STRING,
                          str(_CHIA_ROOT / "dockerfiles" / "ChiaCirctAssertDockerfile"),
                          DEFAULT_REGISTRY, context=str(_CHIA_ROOT))
    image_spec = built["image_spec"]
    if args.image_tag and not image_spec.image_tag.endswith(args.image_tag):
        raise PreflightFailed(
            "image_tag", f"--image-tag {args.image_tag!r} is not the tag the "
            f"manifest names, {image_spec.image_tag!r}: the cluster would run a "
            "different image from the one this run records")
    check_06_image_lit_discovery(image_spec=image_spec)
    check_07_tool_hashes(image_spec=image_spec,
                         observed={cluster["worker_type"]: image_spec.tool_hashes})
    check_08_verilator_version(
        image_spec=image_spec,
        observed={cluster["worker_type"]: image_spec.verilator_version})

    store = LoopStore(DB_PATH)
    mirror = _mirror(store, budget, args, dispatch, triage_task)
    check_10_issue_mirror(mirror=mirror, refresh_requested=args.refresh_mirror)
    check_11_forum_post(forum_post_url=args.forum_post_url,
                        forum_post_date=args.forum_post_date)
    model_resources = {name: resource for name, resource in resources.items()
                       if "llm" in resource
                       or ("repair" in resource and not args.no_repair)}
    check_12_live_model(head=interlock_probe(),
                        workers=interlock_probes(dispatch, model_resources))

    mined = dispatch.call(corpus.build_corpus, args.clone, budget.corpus_head_sha,
                          budget.campaign_start_utc[:10],
                          budget.artefact_inline_cap_bytes)
    seeds = list(mined["seeds"])
    manifest = build_manifest(
        args=args, budget=budget, pin=pin, image_spec=image_spec, mirror=mirror,
        cluster=cluster, mutator_set_sha=mutators.set_sha256(),
        run_manifest_id=args.resume or uuid.uuid4().hex, started_utc=started_utc,
        calibration_seeds=[s for s in seeds
                           if s.seed_sha in (budget.calibration_sample_shas or [])],
        sv_seeds_excluded=(None if image_spec.slang_enabled
                           else list(mined["sv_seeds"])))
    run_root = Path(args.artefact_root) / manifest.run_manifest_id
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "manifest.json").write_text(schema.to_json(manifest), encoding="utf-8")
    shutil.copyfile(args.budget, run_root / "budget.yaml")

    recorder = FixtureRecorder(args.record_fixtures)
    recorder.record(manifest)
    recorder.record(budget)
    # 6.4's first four tables, before a stage can reference one of them, and
    # before --dry-run returns: a dry run's loop.db is what an operator reads to
    # see what the run would have been taken against.
    write_run_rows(store, manifest, image_spec=image_spec, mined=mined,
                   mirror=mirror)
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
    campaign = Campaign(manifest=manifest, budget=budget, store=store,
                        stages=default_stages(), dispatch=dispatch,
                        counters=counters, recorder=recorder,
                        clone_path=args.clone, image_spec=image_spec,
                        repair_enabled=not args.no_repair)
    arms = None if args.arm == "both" else [args.arm]
    outcome = campaign_drive(campaign, seeds, arms=arms)
    outcome["reconciliation"] = reconcile(store, ISSUES_DB_PATH)
    finish_run(store, manifest, _utc())

    from circt_bug_loop import results as results_module

    rendered = results_module.render_results(store, manifest)["rendered"]
    (run_root / "results").mkdir(parents=True, exist_ok=True)
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
    return dispatch.call(triage_task.issue_mirror_refresh, "llvm/circt",
                         budget.issue_mirror_issue_cap, args.github_token_file,
                         store.db_path)


def main(argv: Optional[list] = None, out=None) -> int:
    """Parse argv, run the pre-flight checks, build the manifest, drive the campaign.

    The three arguments that exit early do so before anything is dispatched:
    `--print-config` prints the resolved paths and exits, `--draw-calibration`
    prints the drawn sample and exits, and `--dry-run` runs every pre-flight
    check and builds the manifest and dispatches no stage, which is how an
    operator confirms a cluster is ready to spend money without spending any.

    Returns:
        int, 0 on success, 2 on a pre-flight refusal and 1 on any other failure.
    Worker:
        head; it is a program and not a node (3.2's B12 row).
    Raises:
        nothing; every refusal is a named message on stderr and a non-zero
        status.
    """
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    if args.print_config:
        print(json.dumps(resolved_config(args), sort_keys=True, indent=2), file=out)
        return 0
    if args.draw_calibration:
        from circt_bug_loop import corpus

        budget = budget_module.load_budget._chia_original(
            args.budget, str(FLOW_DIR.parent))["budget"]
        mined = corpus.build_corpus._chia_original(
            args.clone, budget.corpus_head_sha, budget.campaign_start_utc[:10],
            budget.artefact_inline_cap_bytes)
        print("\n".join(draw_calibration(
            corpus_head_sha=budget.corpus_head_sha,
            sample_size=budget.calibration_sample_size,
            exact_pin_shas=[s.seed_sha for s in mined["seeds"] if s.sdk_exact])),
            file=out)
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
