"""Record the seam: one mini-campaign, in process, through the real nodes.

`04-Test-Plan.md` §0.6 rule 2 and §2's production rule: a fixture is the output
of a real run under `--record-fixtures`, written after `contract.validate`
accepted it, and committed. `05-Work-Plan.md` §2.1 and `contract/FROZEN.md`'s
fixture-replacement rule make W-17 the task that lands them.

**What this script is and is not.** It drives the smallest campaign that
produces one instance of every one of the seven members, IN PROCESS, with no
Ray, no container and no model, and writes each through `bug_loop.FixtureRecorder`
into `contract/fixtures/recorded/`. Every instance below is the return value of
the node `03-LLD.md` names as its producer, running for real:

| Member | Producer | What is real about it |
|---|---|---|
| `BudgetFile` | `budget.load_budget` | the committed `budget.yaml`, landed in a throwaway registration repository and taken through all six pre-registration checks of §9.2 |
| `SeedRecord` | `corpus.build_corpus` | re-recorded from `fixtures/corpus/seeds/`, which is W-05's own recording against the blobless clone at the corpus head |
| `ProbeSpec` | `generate_task.generate_mutation` | A4 for real: the committed mutator set applied to that seed's own test file, no model anywhere near it (FR-05.1) |
| `ProbeResult` | `probe_task.probe_execute` | a real CIRCT binary, executed under the `prlimit` prefix, classified by `classify_build` from its own exit status and stderr |
| `FeedbackBundle` | `feedback.build_feedback` | A5 over those `ProbeResult`s, one entry per dispatched probe |
| `LedgerEntry` | `ledger.accrue` | priced by A6b from the committed file's two prices and read back out of `loop.db` |
| `RunManifest` | `bug_loop.build_manifest` | every field from its named producer: A2's real pin walk over the clone, A6a's budget, B6a's mirror over the recorded response set, the cluster YAML's own digest, the mutator set's own digest |

**The one thing that is not the campaign's.** The `ImageSpec` is this host's
measured assertions-on build and NOT the published image: recording inside
`chia-circt-assert:<tag>` is tier 2 and is the pilot's (`05-Work-Plan.md` W-18),
and a fixture that named the published image's digest while a local binary
produced its stderr would be a recording of something that did not happen. The
`image_digest` says `local-build:` and the tool hashes are the binaries actually
executed. The published image's own recorded identity is
`analysis/measurements/raw/image-manifest.json` and is what the pilot's run will
stamp.

**Tier 1.** It needs the blobless `llvm/circt` clone and an assertions-on CIRCT
build, both of `04-Test-Plan.md` §0.5's tier-1 row. Run it as a program:

    python circt_bug_loop/tests/fixtures/recorded/make_recorded.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

from circt_bug_loop import (budget as budget_module, bug_loop, feedback,
                            generate_task, ledger, mutators, pin_select,
                            probe_task, triage_task)
from circt_bug_loop.contract import schema
from circt_bug_loop.store import ImageSpec, LoopStore

HERE = Path(__file__).resolve().parent
TESTS = HERE.parents[1]
FLOW = Path(bug_loop.FLOW_DIR)
REPO = FLOW.parent

#: Where the recorded set lands: one document per file, under the schema's own
#: directory, exactly as `contract/fixtures/` is laid out (§0.6 rule 2).
OUT = FLOW / "contract" / "fixtures" / "recorded"

#: The tier-1 resources of §0.5, in the order this script prefers them.
CLONES = ("BUGLOOP_CORPUS_CLONE", "~/.cache/chia-pin-smoke/circt", "~/.cache/circt")
#: A directory is only a build if its `circt-opt` RUNS: two of this host's four
#: are linked against a `libz3.so.4` that is not installed, and a probe against
#: one of those records a dynamic loader's exit status and calls it a parse
#: error. `resolve` smoke-tests `--version` for exactly that reason.
BUILDS = ("BUGLOOP_BIN_DIR", "~/.cache/chia-pin-smoke/w09/b156/bin",
          "~/.cache/chia-pin-smoke/w09/b143/bin",
          "~/.cache/chia-pin-smoke/bassert_g/bin",
          "~/.cache/chia-pin-smoke/circt-sdk/bin")

#: The seed the mini-campaign runs, which is W-05's own recording.
SEED_FIXTURE = TESTS / "fixtures" / "corpus" / "seeds" / "nine_test_files.json"
#: A3's two recorded-shape transcripts, replayed rather than re-generated: no
#: model runs anywhere in this recording (§0.6, NFR-01).
TURNS = TESTS / "fixtures" / "generate" / "turns"
#: W-09's six real recorded failures, and the SDK build each was recorded under.
CRASHES = TESTS / "fixtures" / "crashes"
SDKS = "~/.cache/chia-pin-smoke/w09/sdk-{version}/bin"
#: B6a's recorded response set, fifty real `llvm/circt` issues (W-10).
MIRROR_FIXTURE = TESTS / "fixtures" / "mirror" / "sample.json"

#: The run this mini-campaign is, fixed so a re-recording is a diff and not a
#: new set of file names.
RUN_ID = "0f3c1a7e5b294d8ea16c02f47db9e358"
STARTED = "2026-09-14T00:00:00+00:00"
#: The registration commit's date, fixed so `budget_file_sha` is a function of
#: the committed bytes and of nothing else; a wall-clock date would give every
#: re-recording a new `budget_file/<sha>.json`.
REGISTERED_AT = "2026-09-01T00:00:00+00:00"

#: §9.4's limits, at the committed file's values, read from it below.
_LIMIT_KEYS = ("probe_wall_seconds", "probe_address_space_bytes",
               "probe_cpu_seconds", "probe_output_byte_cap",
               "reduction_wall_seconds", "reduction_sigkill_grace_seconds")

#: The probe limits the recorded failures run under, which are the committed
#: file's own; a recorded crash that hit a limit would be a limit's recording.
RECORDED_LIMITS: dict = {}

_IDENTITY = {"GIT_AUTHOR_NAME": "bugloop", "GIT_AUTHOR_EMAIL": "bugloop@invalid",
             "GIT_COMMITTER_NAME": "bugloop", "GIT_COMMITTER_EMAIL": "bugloop@invalid"}


def resolve(candidates: tuple, marker: str, *, runs: bool = False) -> str:
    """The first of *candidates* that exists, an environment name or a path.

    With *runs*, the marker must also EXECUTE: `--version` has to exit 0. A
    CIRCT build whose shared libraries are missing exits 127 from the dynamic
    loader, and a probe against it records that and classifies it, which would
    be a recording of this host's library path and not of CIRCT.
    """
    for candidate in candidates:
        value = os.environ.get(candidate) if candidate.isupper() else candidate
        if not value:
            continue
        path = Path(os.path.expanduser(value))
        if not (path / marker).exists():
            continue
        if not runs:
            return str(path)
        done = subprocess.run([str(path / marker), "--version"],
                              capture_output=True, text=True, timeout=120)
        if done.returncode == 0:
            return str(path)
    raise SystemExit(
        f"tier-1 resource absent: none of {candidates} holds a usable {marker!r}")


def registration_repo(root: Path) -> tuple:
    """Land the committed `budget.yaml` in a throwaway repository (FR-14.3).

    The commit that lands the file IS the registration, so `load_budget` cannot
    run its six checks against a working tree that never had one.
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "circt_bug_loop").mkdir(exist_ok=True)
    target = root / "circt_bug_loop" / "budget.yaml"
    shutil.copyfile(budget_module.BUDGET_YAML, target)
    # A FIXED date, so the registration commit's SHA is a function of the
    # committed bytes alone and re-recording is a diff and not a new file.
    when = REGISTERED_AT
    environment = {**os.environ, **_IDENTITY,
                   "GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when}
    for argv in (["init", "-q", "-b", "main"],
                 ["add", "--", "circt_bug_loop/budget.yaml"],
                 ["commit", "-q", "-m", "land budget.yaml"]):
        subprocess.run(["git", "-C", str(root), *argv], check=True,
                       capture_output=True, text=True, env=environment)
    return str(target), str(root)


def local_image_spec(bin_dir: str, tools: list) -> ImageSpec:
    """This host's measured build, as an `ImageSpec`, saying that it is one.

    Not the published image: see the module docstring. Every field is read off
    the build, and `image_digest` names what it is so no reader can mistake the
    recording for one made inside a container.
    """
    hashes = {tool: hashlib.sha256((Path(bin_dir) / tool).read_bytes()).hexdigest()
              for tool in tools}
    version = subprocess.run([str(Path(bin_dir) / tools[0]), "--version"],
                             capture_output=True, text=True, timeout=60).stdout
    circt_sha = ""
    for line in version.splitlines():
        if "CIRCT" in line:
            circt_sha = line.strip().split()[-1]
    digest = hashlib.sha256(
        json.dumps(hashes, sort_keys=True).encode("utf-8")).hexdigest()
    return ImageSpec(
        circt_sha=circt_sha or "unknown", sdk_tag="", targets=list(tools),
        flag_string="-O3 -UNDEBUG -gline-tables-only", cmake_args=[],
        image_digest=f"local-build:sha256:{digest}",
        image_tag=f"local-build:{Path(bin_dir).parent.name}",
        verilator_version="", slang_enabled=False, lit_discovery_ok=True,
        lit_discovered_count=0, assertion_nonreferencing=[], tool_hashes=hashes)


def mirror_block(db_path: str) -> dict:
    """B6a for real, over the fifty recorded issues of `fixtures/mirror/`.

    The transport is replaced and the node is not: `GithubIssuesNode._list`, its
    paging, its pull-request filter and `_build_issue` all run, which is
    `04-Test-Plan.md` §0.3's rule that a recorded response set is replayed and
    nothing is mocked above it.
    """
    from chia.github.github_client import GithubClient

    payload = json.loads(MIRROR_FIXTURE.read_text(encoding="utf-8"))
    original = GithubClient._request

    def _request(self, path, params=None, accept=None):
        params = dict(params or {})
        page, per_page = int(params.get("page", 1)), int(params.get("per_page", 100))
        ordered = payload if params.get("direction") == "desc" else payload[::-1]
        return ordered[(page - 1) * per_page: page * per_page]

    token = Path(db_path).parent / "token"
    token.write_text("recorded-response-set-no-token-is-used\n", encoding="utf-8")
    GithubClient._request = _request
    try:
        return triage_task.issue_mirror_refresh._chia_original(
            "llvm/circt", 600, str(token), db_path)
    finally:
        GithubClient._request = original


def offline_tools(monkey: list) -> None:
    """Construct `ChiaTool`s with no Ray actor behind them (§0.4).

    `ChiaTool.__post_init__` starts a `_ToolServerActor` and `ray.get`s its
    address, which starts a local Ray. The recorder is not a cluster, so the
    substitute fills the three fields the real one fills and starts nothing;
    the constructor, the path checks and every git call are the real ones. It is
    `tests/test_tools.py`'s own `tool_servers` fixture, as a plain function.
    """
    from chia.base.tools.ChiaTool import ChiaTool, ToolInfo

    original = ChiaTool.__post_init__

    def _post_init(self):
        self.hostname, self.port, self.node_id = "127.0.0.1", 9001, "recorder"
        self.tool_info = ToolInfo(name=self.name, port=self.port,
                                  node_id=self.node_id)
        ChiaTool._tool_registry.append(self.tool_info)

    ChiaTool.__post_init__ = _post_init
    monkey.append(lambda: setattr(ChiaTool, "__post_init__", original))


def replay_turns(monkey: list, texts: list, files: dict) -> None:
    """Replay A3's two turns from the committed transcripts, and reach no model.

    `04-Test-Plan.md` §0.6 and NFR-01 call this replaying an agent turn: the
    emitter, the cap, the argv rule, the two `ChiaTool`s and the validator are
    the code under test and the turn's TEXT is the recording.
    """
    pending = list(texts)
    original_dispatch = generate_task.dispatch_turn

    # Since K2 the node builds no backend at all - the client is `llm_turn`'s,
    # on the `llm` worker - so `dispatch_turn` is the one call to replace and
    # what it receives is the turn request's fields.
    def _dispatch(system_message, user_message, tools, *, stage,
                  timeout_seconds, model_id, guard=None):
        text = pending.pop(0)
        for name, content in (files.pop(text[:24], {}) or {}).items():
            tools[-1].write_probe(name, content)
        return {"result": text, "stream": f"[stream]\n{text}", "stderr": "",
                "success": True,
                "usage": {"tokens_in": 0, "tokens_out": 0, "thinking_tokens": 0,
                          "tool_use_prompt_tokens": 0, "num_turns": 1,
                          "model": "replayed", "observed": True}}

    generate_task.dispatch_turn = _dispatch
    monkey.append(lambda: setattr(generate_task, "dispatch_turn", original_dispatch))


def record(root: Path) -> dict:
    """Run the mini-campaign and write every instance it produced.

    Returns:
        {"recorder": FixtureRecorder, "manifest": RunManifest, ...}, so a caller
        can print what was written and a test can assert over it.
    Worker:
        none; every node runs in this process through its undecorated body,
        which is `04-Test-Plan.md` §0.4's plain-call path.
    Raises:
        SystemExit when a tier-1 resource is absent; ContractError from any
        instance the seam refuses, which is a defect in its producer.
    """
    clone = resolve(CLONES, ".git")
    bin_dir = resolve(BUILDS, "circt-opt", runs=True)
    artefacts = root / "artefacts"
    artefacts.mkdir(parents=True, exist_ok=True)
    recorder = bug_loop.FixtureRecorder(str(OUT))

    # --- A6a, the budget ----------------------------------------------------
    budget_path, repo_root = registration_repo(root / "registration")
    budget = budget_module.load_budget._chia_original(budget_path, repo_root)["budget"]
    recorder.record(budget)

    # --- A1, the seed -------------------------------------------------------
    seed = schema.from_json(SEED_FIXTURE.read_text(encoding="utf-8"),
                            schema.SeedRecord)
    recorder.record(seed)

    # --- A2, the pin, and B1's identity -------------------------------------
    pin = pin_select.select_release_pinned_main._chia_original(clone, ref="origin/main")
    image_spec = local_image_spec(bin_dir, [seed.entry_tool])

    # --- A4, the probing inputs ---------------------------------------------
    cfg = {"model_id": budget.model_id, "per_seed_probe_cap": 2, "iteration": 1,
           "run_manifest_id": RUN_ID, "artefact_root": str(artefacts),
           "artefact_inline_cap_bytes": budget.artefact_inline_cap_bytes,
           "clone_path": clone, "run_commit": pin["run_commit"],
           # No `mutator_set_sha`: `set_v1.json` does not exist, A7 has not
           # run, and `load_set` refuses an unfrozen set to any run that NAMES a
           # digest (8.1 rule 1, `04-Test-Plan.md` §16.8 item 8). The refusal is
           # the campaign's and is left standing; this recording is not a
           # campaign, so it names none and the development set applies.
           "mutator_set_path": str(mutators.SET_PATH)}
    snapshot = schema.LedgerSnapshot(arm="mutation", unit="wall_clock_seconds",
                                     spent=0.0, cap=float(budget.arm_window_seconds))
    empty = schema.FeedbackBundle(run_manifest_id=RUN_ID, seed_sha=seed.seed_sha,
                                  arm="mutation", iteration=0, entries=[],
                                  abandoned=False, terminating_condition=None)
    generated = generate_task.generate_mutation._chia_original(
        seed, empty, snapshot, cfg)
    specs = list(generated["specs"])
    if not specs:
        raise SystemExit("A4 emitted no ProbeSpec: the mutator set produced no mutant")
    for spec in specs:
        recorder.record(spec)

    # --- A3, the seeded arm, from the recorded transcripts -------------------
    undo: list = []
    offline_tools(undo)
    seed_read = (TURNS / "seed_read_ok.md").read_text(encoding="utf-8")
    probe_write = (TURNS / "probe_write_ok.md").read_text(encoding="utf-8")
    declared = json.loads(
        probe_write.split("```json")[-1].rsplit("```", 1)[0])["probes"]
    replay_turns(undo, [seed_read, probe_write],
                 {probe_write[:24]: {entry["filename"]: entry.get("content")
                                     or "hw.module @Top() {}\n"
                                     for entry in declared}})
    try:
        seeded = generate_task.generate_seeded._chia_original(
            seed, empty, snapshot, {**cfg, "arm": "seeded",
                                    "here_options": None, "head_options": None})
    finally:
        for restore in undo:
            restore()
    for spec in seeded["specs"]:
        specs.append(spec)
        recorder.record(spec)

    # --- B2, the probes -----------------------------------------------------
    limits = {key: getattr(budget, key) for key in _LIMIT_KEYS}
    RECORDED_LIMITS.update(limits)
    results, builds = [], []
    for spec in specs:
        directory = artefacts / RUN_ID / f"seed_{seed.seed_sha}" / "iter_1" \
            / f"probe_{spec.probe_id}"
        executed = probe_task.probe_execute._chia_original(
            spec, image_spec, limits, str(directory), bin_dir=bin_dir)
        results.append(executed["probe_result"])
        builds.append(executed["build_result"])
        recorder.record(executed["probe_result"])

    # --- A5, the feedback, both arms -----------------------------------------
    # BOTH, because they differ by rule and not by accident: FR-16.2 empties the
    # mutation arm's bundle and the seeded arm's carries one entry per
    # dispatched probe, and a fixture set with only one of them cannot show
    # that the two halves agree on the shape.
    bundles = []
    for arm in ("seeded", "mutation"):
        remaining = schema.LedgerSnapshot(
            arm=arm, unit="wall_clock_seconds", spent=0.0,
            cap=float(budget.arm_window_seconds))
        ids = [s.probe_id for s in specs if s.arm == arm]
        bundle = feedback.build_feedback._chia_original(
            [r for r in results if r.arm == arm],
            schema.FeedbackBundle(run_manifest_id=RUN_ID, seed_sha=seed.seed_sha,
                                  arm=arm, iteration=1, entries=[],
                                  abandoned=False, terminating_condition=None),
            seed.seed_sha, 2, ids, run_manifest_id=RUN_ID, budget=budget,
            remaining=remaining, probes_this_seed=len(ids))["bundle"]
        bundles.append(bundle)
        recorder.record(bundle)
    bundle = bundles[0]

    # --- B6a, the mirror, and B12's manifest --------------------------------
    store = LoopStore(str(root / "loop.db"))
    mirror = mirror_block(store.db_path)
    cluster = bug_loop.cluster_summary(str(FLOW / "cluster_single.yaml"))
    args = SimpleNamespace(
        mode="discovery", arm="both", artefact_root=str(artefacts),
        repair_backend="vertex", repair_model=None, no_repair=False,
        # W-19b's flag, which `repair_enabled` reads: this run is the `model`
        # one with its two turns replayed, not the recorded-generator mode.
        generator="model",
        forum_post_url="https://llvm.discourse.group/t/circt-bug-loop/0",
        forum_post_date="2026-09-14")
    manifest = bug_loop.build_manifest(
        args=args, budget=budget, pin=pin, image_spec=image_spec, mirror=mirror,
        cluster=cluster, mutator_set_sha=mutators.set_sha256(),
        run_manifest_id=RUN_ID, started_utc=STARTED)
    recorder.record(manifest)

    # --- A6b, the ledger ----------------------------------------------------
    store.insert("run", {
        "run_manifest_id": RUN_ID, "mode": manifest.mode,
        "seed_set": manifest.seed_set, "manifest_json": schema.to_json(manifest),
        "budget_file_sha": manifest.budget_file_sha,
        "cluster_yaml_sha": manifest.cluster_yaml_sha,
        "artefact_root": manifest.artefact_root, "started_utc": STARTED,
        "ended_utc": None})
    # All three `arm` values and both `scope` values, which is what
    # `T-I-ledger-01` reconciles: one `arm_window` per arm (FR-14.4 permits
    # exactly one), and one `shared` entry for the work neither arm owns.
    cpu = round(sum(b.cpu_seconds or 0.0 for b in builds), 6)
    written = []
    for arm, scope, stage, amount, tokens in (
            ("seeded", "arm_window", "stage_3", float(budget.arm_window_seconds), True),
            ("mutation", "arm_window", "stage_3", float(budget.arm_window_seconds), False),
            ("shared", "stage", "corpus", cpu, False)):
        entry = schema.LedgerEntry(
            entry_id=uuid.uuid5(uuid.NAMESPACE_URL,
                                f"{RUN_ID}/{arm}/{scope}/{stage}").hex,
            run_manifest_id=RUN_ID, arm=arm, scope=scope, stage=stage,
            unit="wall_clock_seconds", amount=amount, metered=(scope == "arm_window"),
            # The mutation arm runs no model, so its token counts are null by
            # FR-14.6's own conditional and `accrue` prices them to a null cost.
            observed={"cpu_seconds": cpu,
                      "tokens_in": 4096 if tokens else None,
                      "tokens_out": 512 if tokens else None, "cost_usd": None},
            timestamp_utc=STARTED,
            stop_reason="arm_window" if scope == "arm_window" else None)
        ledger.accrue._chia_original(entry, store.db_path, budget)
        row = store.query_one("SELECT * FROM ledger_entry WHERE entry_id = ?",
                              (entry.entry_id,))
        # Read BACK out of loop.db, so what is recorded is what A6b stored and
        # priced and not what the caller handed it.
        stored = schema.LedgerEntry(
            entry_id=row["entry_id"], run_manifest_id=row["run_manifest_id"],
            arm=row["arm"], scope=row["scope"], stage=row["stage"],
            unit=row["unit"], amount=row["amount"], metered=bool(row["metered"]),
            observed=json.loads(row["observed_json"]),
            timestamp_utc=row["timestamp_utc"], stop_reason=row["stop_reason"])
        recorder.record(stored)
        written.append(stored)
    entry = written[0]

    return {"recorder": recorder, "manifest": manifest, "budget": budget,
            "seed": seed, "specs": specs, "results": results, "bundle": bundle,
            "entry": entry, "image_spec": image_spec, "clone": clone,
            "bin_dir": bin_dir}


def main(argv: list) -> int:
    """Record the set into `contract/fixtures/recorded/` and print what landed."""
    import tempfile

    # A FIXED root, so the artefact paths a recording carries are the same on
    # the next recording and a re-record is a diff of what changed and not of
    # where the temporary directory landed.
    root = Path(argv[0]) if argv else (
        Path(tempfile.gettempdir()) / f"bugloop-recorded-{RUN_ID[:12]}")
    if root.exists():
        shutil.rmtree(root)
    written = record(root)["recorder"].written
    for path in written:
        print(Path(path).relative_to(FLOW))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
