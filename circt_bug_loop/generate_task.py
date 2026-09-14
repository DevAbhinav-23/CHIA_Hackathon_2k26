"""A3, A4 and the two agent-facing tools (03-LLD.md 3.5)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from string import Template
from typing import Optional

import ray
from chia.base.ChiaFunction import ChiaFunction, get
from chia.base.tools.ChiaTool import ChiaTool

from circt_bug_loop import corpus, mutators
from circt_bug_loop.contract.schema import (ContractError, CounterBlock,
                                            FeedbackBundle, LedgerSnapshot,
                                            ProbeSpec, SeedRecord, bound_text,
                                            validate)
from circt_bug_loop.llm import (MODEL_BACKEND, LiveModelRefused,  # noqa: F401
                                PromptContractError, build_llm, dispatch_turn,
                                llm_turn, parse_json_footer, require_live_model,
                                tool_iterations)

#: 7.2 and 7.3 live beside this module (1.1).
PROMPTS = Path(__file__).resolve().parent / "prompts"

#: A3's system message.
GENERATE_SYSTEM_MESSAGE = (
    "You look for compiler bugs in CIRCT by reading its source and writing small "
    "inputs. You never claim a result you did not observe, and you end every "
    "response with one fenced json block.")

#: FR-17.8's marker, spelled here: a supply-half module may not import `store.py`.
_PARTIAL = "PARTIAL"

#: A3's two turns, by artefact-file name, to the stage id their `CounterBlock` carries.
_TURN_STAGE = {"seed_read": "stage_1", "probe_write": "stage_2"}


#: 3.2's tool row: 60 s [DEFAULT] per git call, enforced by subprocess.
SOURCE_READ_TIMEOUT_SECONDS = 60

#: What ONE `read_file` or `grep` may return, which is what the turn's
#: pre-authorisation prices a tool result at (`llm.TOOL_OUTPUT_TOKENS_CAP`).
SOURCE_READ_CAP_BYTES = 65536


def _truncate(text: str, cap_bytes: int) -> str:
    """Cap one tool return at *cap_bytes*, stating the truncation in the text."""
    data = text.encode("utf-8")
    if len(data) <= cap_bytes:
        return text
    head = data[:cap_bytes].decode("utf-8", errors="backslashreplace")
    return f"{head}\n... [truncated at {cap_bytes} bytes of {len(data)}]"


def _outside(path: str) -> bool:
    """Say whether *path* is not a plain repository-relative path."""
    return path.startswith("/") or ".." in path.split("/")


class SourceReadTool(ChiaTool):
    """MCP tool: read CIRCT's source at the run's commit."""

    def __init__(self, name: str, clone_path: str, run_commit: str,
                 cap_bytes: int = 262144,
                 read_cap_bytes: int = SOURCE_READ_CAP_BYTES,
                 task_options: Optional[dict] = None):
        """Bind one clone and one commit, and register the three read methods."""
        super().__init__(name, task_options=task_options)
        self.clone_path = str(clone_path)
        self.run_commit = str(run_commit)
        self.cap_bytes = int(cap_bytes)
        self.read_cap_bytes = int(read_cap_bytes)
        self.mcp.add_tool(self.read_file, name=f"{name}_read_file")
        self.mcp.add_tool(self.grep, name=f"{name}_grep")
        self.mcp.add_tool(self.list_dir, name=f"{name}_list_dir")
        super().__post_init__()

    def _git(self, *args: str) -> tuple[int, str, str]:
        """Run one git argument vector against the bound clone, with no shell."""
        try:
            done = subprocess.run(
                ["git", "-C", self.clone_path, *args],
                capture_output=True, text=True, errors="backslashreplace",
                timeout=SOURCE_READ_TIMEOUT_SECONDS, check=False)
        except (OSError, subprocess.SubprocessError) as error:
            return 1, "", str(error)
        return done.returncode, done.stdout, done.stderr

    def _page(self, lines: list) -> tuple:
        """The leading lines of *lines* that fit the read cap, and how many did not."""
        kept, size = [], 0
        for line in lines:
            size += len(line.encode("utf-8")) + 1
            if size > self.read_cap_bytes and kept:
                break
            kept.append(line)
        return kept, len(lines) - len(kept)

    def read_file(self, path: str, first_line: int = 1) -> str:
        """Return one CIRCT source file's text at the run's commit, one page at a time.

        path is repository-relative, for example lib/Dialect/HW/HWTypes.cpp.
        Returns the file's lines from first_line (1 by default) up to
        65536 bytes; when more remain the text ends
        '... [truncated: continue with first_line=N of M lines]', and calling
        again with that first_line returns the next page. A path that does not
        exist at that commit, or a first_line past the end of the file, returns
        a one-line string beginning 'Error:'.
        """
        if _outside(path):
            return f"Error: {path!r} is not a repository-relative path"
        try:
            start = int(first_line)
        except (TypeError, ValueError):
            return f"Error: first_line must be a line number, got {first_line!r}"
        if start < 1:
            return f"Error: first_line must be 1 or more, got {start}"
        code, out, err = self._git("show", f"{self.run_commit}:{path}")
        if code != 0:
            return f"Error: {err.strip() or 'no such path at the run commit'}"
        lines = out.splitlines()
        if start > len(lines):
            return (f"Error: first_line {start} is past the end of {path!r}, "
                    f"which has {len(lines)} lines")
        kept, dropped = self._page(lines[start - 1:])
        text = "\n".join(kept)
        if dropped:
            text += (f"\n... [truncated: continue with first_line={start + len(kept)}"
                     f" of {len(lines)} lines]")
        return text

    def grep(self, pattern: str, path_prefix: str) -> str:
        """Search CIRCT's source at the run's commit for a fixed string.

        pattern is a literal, not a regular expression; path_prefix limits the
        search, for example lib/Dialect/HW. Returns matching lines as
        '<path>:<line>:<text>', capped at 65536 bytes and saying how many
        further matches were dropped, or 'Error:' if nothing matched.
        """
        if _outside(path_prefix):
            return f"Error: {path_prefix!r} is not a repository-relative path"
        code, out, err = self._git("grep", "-n", "-F", "--", pattern,
                                   self.run_commit, "--", path_prefix)
        if not out.strip():
            # git grep exits 1 on "no match", which is an answer and not a failure.
            return (f"Error: no match for {pattern!r} under {path_prefix!r}"
                    if code in (0, 1) else f"Error: {err.strip()}")
        # `git grep <rev>` prefixes every line with `<rev>:`.
        prefix = f"{self.run_commit}:"
        lines = [line[len(prefix):] if line.startswith(prefix) else line
                 for line in out.splitlines()]
        kept, dropped = self._page(lines)
        text = "\n".join(kept)
        if dropped:
            text += (f"\n... [truncated: {dropped} further matches of {len(lines)}; "
                     "narrow path_prefix or the pattern]")
        return text

    def list_dir(self, path: str) -> str:
        """List one directory's entries in CIRCT at the run's commit.

        path is repository-relative; '' lists the repository root. Returns one
        name per line, or a one-line string beginning 'Error:'.
        """
        if _outside(path):
            return f"Error: {path!r} is not a repository-relative path"
        code, out, err = self._git("ls-tree", "--name-only",
                                   f"{self.run_commit}:{path}")
        if code != 0:
            return f"Error: {err.strip() or 'no such directory at the run commit'}"
        return _truncate(out, self.cap_bytes)


class ProbeWriteTool(ChiaTool):
    """MCP tool: write one probing-input file into this iteration's probe directory."""

    def __init__(self, name: str, probe_dir: str,
                 task_options: Optional[dict] = None):
        """Bind one probe directory and register the one write method."""
        super().__init__(name, task_options=task_options)
        os.makedirs(probe_dir, exist_ok=True)
        self.probe_dir = os.path.realpath(probe_dir)
        self.mcp.add_tool(self.write_probe, name=f"{name}_write_probe")
        super().__post_init__()

    def write_probe(self, filename: str, content: str) -> str:
        """Write one probing input under this iteration's probe directory.

        filename is a bare file name with no directory part and no '..'.
        Returns the absolute path written, or a one-line error string beginning
        'Error:' if the name is rejected or the write fails. Writing the same
        name twice overwrites with identical bytes.
        """
        if os.path.sep in filename or filename in ("", ".", ".."):
            return f"Error: filename must be a bare file name, got {filename!r}"
        dest = os.path.realpath(os.path.join(self.probe_dir, filename))
        if os.path.commonpath([dest, self.probe_dir]) != self.probe_dir:
            return f"Error: {filename!r} resolves outside the probe directory"
        try:
            with open(dest, "w", encoding="utf-8") as handle:
                handle.write(content)
        # ValueError as well as OSError (N3/N5).
        except (OSError, ValueError) as error:
            return f"Error: {error}"
        return dest


#: The language a seed's inputs are written in.
_LANGUAGE_BY_TOOL = {"circt-opt": "mlir", "circt-translate": "mlir",
                     "arcilator": "mlir", "firtool": "fir",
                     "circt-verilog": "sv", "other": "mlir"}
_SUFFIX_BY_LANGUAGE = {"mlir": ".mlir", "fir": ".fir", "sv": ".sv"}

#: lit's three substitutions, as 3.3 step 5 spells them.
_SUBSTITUTIONS = ("%S", "%s", "%t")


def seed_language(seed: SeedRecord) -> str:
    """Return the language a seed's probing inputs are written in."""
    for path in seed.test_paths:
        language = mutators.language_of(path, default="")
        if language:
            return language
    return _LANGUAGE_BY_TOOL.get(seed.entry_tool, "mlir")


def _render(text: str, **values) -> str:
    """Substitute into a prompt with `Template.safe_substitute`, never `format`."""
    return Template(text).safe_substitute(**values)


def _prompt_text(cfg: dict, name: str) -> str:
    """Read one prompt, preferring the copy the driver already loaded."""
    return cfg.get(name) or (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def render_test_files(seed: SeedRecord) -> str:
    """Render 7.2's `$test_files`: one `==> <path> <==` block per changed test."""
    return "\n".join(f"==> {path} <==\n{seed.test_files.get(path, '')}"
                     for path in seed.test_paths)


def render_sites(sites: list) -> str:
    """Render 7.3's `$sibling_sites`: one `<file>:<symbol> - <why>` line each."""
    return "\n".join(
        f"{site.get('file', '')}:{site.get('symbol', '')} - {site.get('why', '')}"
        for site in sites) or "none"


def render_feedback(feedback: FeedbackBundle) -> str:
    """Render 7.3's `$feedback` from the previous iteration's ProbeResults."""
    if not feedback.entries:
        return "There was no previous iteration."
    lines = []
    for entry in feedback.entries:
        lines.append(f"{entry.probe_id}: stopped at {entry.stopped_at_stage}, "
                     f"{entry.reason}")
        if entry.oracle_class:
            lines.append(f"  oracle: {entry.oracle_class}"
                         + (f" - {entry.oracle_summary}" if entry.oracle_summary else ""))
        if entry.reduced_text:
            lines.append("  reduced case:")
            lines.extend(f"    {line}" for line in entry.reduced_text.splitlines())
    if feedback.abandoned:
        lines.append(f"This seed is being abandoned: {feedback.abandon_reason}")
    return "\n".join(lines)


def render_argv_template(seed: SeedRecord) -> str:
    """Render 7.3's `$argv_template`, the seed's own argv with INPUT in it."""
    argv = seed_argv_template(seed) if seed.argv_template else []
    return " ".join([seed.entry_tool] + [_bind(token, "INPUT") for token in argv])


def _bind(token: str, path: str) -> str:
    """Bind lit's three substitutions in one argv token to *path*."""
    for placeholder in _SUBSTITUTIONS:
        token = token.replace(placeholder, path)
    return token


def seed_argv_template(seed: SeedRecord) -> list:
    """Return the seed's own argv template, probe-only options stripped."""
    if not seed.argv_template:
        raise ValueError(f"seed {seed.seed_sha} records no RUN: line, so no "
                         "argument vector can be built for it (FR-01.9)")
    argv, _ = corpus.strip_probe_only_options(list(seed.argv_template[0]))
    return argv


def probe_argv(seed: SeedRecord, input_path: str,
               argv_template: Optional[list] = None) -> list:
    """Build one probe's argument vector from the seed's own template."""
    argv = list(argv_template) if argv_template is not None else seed_argv_template(seed)
    bound = [_bind(token, input_path) for token in argv]
    return bound if input_path in bound else bound + [input_path]


def render_seed_read(seed: SeedRecord, cfg: dict) -> str:
    """Render 7.2's stage-1 prompt."""
    return _render(_prompt_text(cfg, "seed_read"),
                   seed_sha=seed.seed_sha,
                   subject=seed.subject,
                   diff=seed.diff,
                   test_files=render_test_files(seed),
                   run_lines="\n".join(seed.run_lines),
                   entry_tool=seed.entry_tool,
                   max_sites=int(cfg["per_seed_probe_cap"]),
                   max_tool_calls=tool_iterations(cfg, "stage_1"))


def render_probe_write(seed: SeedRecord, root_cause_class: str, sites: list,
                       feedback: FeedbackBundle, probe_dir: str,
                       cfg: dict) -> str:
    """Render 7.3's stage-2 prompt from stage 1's answer and the feedback."""
    return _render(_prompt_text(cfg, "probe_write"),
                   seed_sha=seed.seed_sha,
                   root_cause_class=root_cause_class,
                   sibling_sites=render_sites(sites),
                   entry_tool=seed.entry_tool,
                   argv_template=render_argv_template(seed),
                   language=seed_language(seed),
                   probe_dir=probe_dir,
                   cap=int(cfg["per_seed_probe_cap"]),
                   max_tool_calls=tool_iterations(cfg, "stage_2"),
                   feedback=render_feedback(feedback))


#: The three reasons a declared probe is dropped, counted and never repaired.
REJECTION_REASONS = ("no_file_written", "tool_mismatch", "contract_error")


def check_tool(spec: ProbeSpec, seed: SeedRecord) -> None:
    """Raise E010 unless a spec's tool is the seed's classified entry tool."""
    if spec.tool != seed.entry_tool:
        raise ContractError("E010_TOOL_MISMATCH",
                            f"ProbeSpec.tool {spec.tool!r} is not the seed's "
                            f"entry_tool {seed.entry_tool!r} (FR-04.2)")


def probe_id(run_manifest_id: str, seed_sha: str, arm: str, iteration: int,
             key: str) -> str:
    """Return the stable probe id for one emitted input."""
    digest = hashlib.sha256(
        f"{run_manifest_id}|{seed_sha}|{arm}|{iteration}|{key}".encode("utf-8"))
    return f"p-{digest.hexdigest()[:12]}"


def _write(directory: str, relative_path: str, data: str) -> str:
    """Write one artefact under FR-17.8's marker and return its absolute path."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / _PARTIAL
    if not marker.exists():
        marker.touch()
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(data, encoding="utf-8")
    return str(target)


def _spec(*, seed: SeedRecord, arm: str, iteration: int, run_manifest_id: str,
          probe_dir: str, text: str, tool: str, expected_outcome: str,
          turn_cost: dict, key: str, cap_bytes: int,
          mutator_id: Optional[str] = None,
          mutator_seed_int: Optional[int] = None,
          source_test_path: Optional[str] = None,
          argv_template: Optional[list] = None) -> ProbeSpec:
    """Build and validate one ProbeSpec, writing its input into the artefact tree."""
    identifier = probe_id(run_manifest_id, seed.seed_sha, arm, iteration, key)
    artefact_dir = str(Path(probe_dir).parent / f"probe_{identifier}")
    filename = f"input{_SUFFIX_BY_LANGUAGE.get(seed_language(seed), '.mlir')}"
    input_path = _write(artefact_dir, filename, text)
    spec = ProbeSpec(
        probe_id=identifier, run_manifest_id=run_manifest_id,
        seed_sha=seed.seed_sha, arm=arm, iteration=iteration,
        input_filename=filename, input_path=input_path,
        input_text=bound_text(text, input_path, cap_bytes),
        tool=tool, argv=probe_argv(seed, input_path, argv_template),
        polarity=seed.polarity[0], shape=seed.shape[0],
        expected_outcome=expected_outcome, turn_cost=dict(turn_cost),
        mutator_id=mutator_id, mutator_seed_int=mutator_seed_int,
        source_test_path=source_test_path)
    check_tool(spec, seed)
    validate(spec)
    return spec


def emit_specs(raw: dict, seed: SeedRecord, iteration: int, cap: int,
               probe_dir: str, run_manifest_id: str,
               turn_cost: dict, cap_bytes: int = 262144) -> tuple:
    """Turn the stage-2 turn's JSON footer into validated ProbeSpecs."""
    rejections = {reason: 0 for reason in REJECTION_REASONS}
    declared = [entry for entry in (raw.get("probes") or [])
                if isinstance(entry, dict)]
    discarded = max(0, len(declared) - cap)
    specs = []
    for entry in declared[:cap]:
        filename = str(entry.get("filename") or "")
        staged = Path(probe_dir) / filename
        if (not filename or os.path.sep in filename
                or not staged.is_file()):
            rejections["no_file_written"] += 1
            continue
        try:
            spec = _spec(
                seed=seed, arm="seeded", iteration=iteration,
                run_manifest_id=run_manifest_id, probe_dir=probe_dir,
                text=staged.read_text(encoding="utf-8", errors="backslashreplace"),
                # The agent's own `tool`.
                tool=str(entry.get("tool") or seed.entry_tool),
                expected_outcome=str(entry.get("expected_outcome") or ""),
                turn_cost=turn_cost, key=filename, cap_bytes=cap_bytes)
        except ContractError as error:
            reason = ("tool_mismatch" if error.code == "E010_TOOL_MISMATCH"
                      else "contract_error")
            rejections[reason] += 1
            continue
        except (ValueError, OSError):
            rejections["contract_error"] += 1
            continue
        specs.append(spec)
    return specs, discarded, rejections


def iteration_dir(cfg: dict, seed_sha: str, iteration: int) -> str:
    """Return 6.5's `<run>/seed_<seed_sha>/iter_<n>` for one iteration."""
    if cfg.get("artefact_dir"):
        return str(cfg["artefact_dir"])
    return str(Path(cfg["artefact_root"]) / cfg["run_manifest_id"]
               / f"seed_{seed_sha}" / f"iter_{iteration}")


def _turn(stage: str, prompt: str, tools: list, cfg: dict, directory: str,
          logs: dict) -> dict:
    """Run one stage's turn and persist FR-04.6's five files whatever happens."""
    name = f"llm_{stage}"
    logs[f"{name}.prompt.md"] = _write(directory, f"{name}.prompt.md", prompt)
    started = time.monotonic()
    turn: dict = {"result": "", "stream": "", "stderr": "", "success": False,
                  "usage": {}}
    try:
        turn = dispatch_turn(GENERATE_SYSTEM_MESSAGE, prompt, tools,
                             stage=_TURN_STAGE[stage],
                             timeout_seconds=int(cfg.get("timeout_seconds", 2400)),
                             model_id=cfg["model_id"],
                             guard=cfg.get("spend_guard"),
                             max_tool_iterations=(cfg.get("max_tool_iterations")
                                                  or {}).get(_TURN_STAGE[stage]))
        return turn
    finally:
        turn["wall_seconds"] = time.monotonic() - started
        logs.setdefault("usage", {})[stage] = turn.get("usage") or {}
        logs.setdefault("wall_seconds", {})[stage] = turn["wall_seconds"]
        for suffix, data in (
                (".md", turn.get("stream") or ""),
                (".stderr", turn.get("stderr") or ""),
                (".jsonl", turn.get("result") or ""),
                (".usage.json", json.dumps(turn.get("usage") or {},
                                           indent=2, sort_keys=True) + "\n")):
            logs[f"{name}{suffix}"] = _write(directory, f"{name}{suffix}", data)


def _resolve_sites(sites: list, cfg: dict) -> dict:
    """Resolve stage 1's sibling sites against the head's clone (FR-04.1)."""
    args = (cfg["clone_path"], cfg["run_commit"], list(sites))
    options = cfg.get("head_options")
    if ray.is_initialized() and options:
        return get(corpus.resolve_sites.options(**options).chia_remote(*args))
    return corpus.resolve_sites._chia_original(*args)


def _turn_cost(stage: str, logs: dict, cfg: dict) -> dict:
    """Build 2.7's `turn_cost` for one stage's spend, priced where a price exists."""
    usage = (logs.get("usage") or {}).get(stage) or {}
    tokens_in = usage.get("tokens_in")
    tokens_out = usage.get("tokens_out")
    price_in = cfg.get("price_usd_per_m_input_tokens")
    price_out = cfg.get("price_usd_per_m_output_tokens")
    cost = None
    if (tokens_in is not None and tokens_out is not None
            and price_in is not None and price_out is not None):
        cost = (tokens_in / 1e6) * price_in + tokens_out / 1e6 * price_out
    return {"turn": stage, "wall_seconds": (logs.get("wall_seconds") or {}).get(stage, 0.0),
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "cost_usd": cost, "metered": tokens_in is not None}


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def generate_seeded(seed: SeedRecord, feedback: FeedbackBundle,
                    remaining: LedgerSnapshot, cfg: dict) -> dict:
    """Run stages 1 and 2 for one seed and emit the probing inputs they wrote.

    Returns:
        {"specs": list[ProbeSpec], "root_cause_class": str, "sibling_sites": list[dict], "rejected_sites": list[dict], "truncated": int, "rejections": dict, "logs": dict, "failure": str | None, "counters": CounterBlock}.
    Worker:
        {"circt": 1} for the node; each turn is dispatched at {"llm": 1.0}.
    Raises:
        nothing.
    """
    started = time.monotonic()
    iteration = int(cfg.get("iteration", feedback.iteration))
    cap = int(cfg["per_seed_probe_cap"])
    cap_bytes = int(cfg.get("artefact_inline_cap_bytes", 262144))
    directory = iteration_dir(cfg, seed.seed_sha, iteration)
    probe_dir = str(Path(directory) / "probes")
    logs: dict = {"usage": {}, "wall_seconds": {}}
    failure = None
    root_cause_class = ""
    sites: list = []
    rejected: list = []
    specs: list = []
    truncated = 0
    rejections = {reason: 0 for reason in REJECTION_REASONS}

    source_read = probe_write = None
    try:
        source_read = SourceReadTool(
            name=f"src_{seed.seed_sha[:12]}_{iteration}",
            clone_path=cfg["clone_path"], run_commit=cfg["run_commit"],
            cap_bytes=cap_bytes, read_cap_bytes=SOURCE_READ_CAP_BYTES,
            task_options=cfg.get("head_options"))
        probe_write = ProbeWriteTool(
            name=f"probe_{seed.seed_sha[:12]}_{iteration}",
            probe_dir=probe_dir, task_options=cfg.get("here_options"))
        tools = [source_read, probe_write]

        answer = parse_json_footer(
            _turn("seed_read", render_seed_read(seed, cfg), tools, cfg,
                  directory, logs).get("result") or "",
            ("root_cause_class", "sibling_sites"))
        root_cause_class = str(answer["root_cause_class"])
        resolution = _resolve_sites(
            [site for site in answer["sibling_sites"]
             if isinstance(site, dict)][:cap], cfg)
        sites, rejected = resolution["resolved"], resolution["rejected"]

        written = parse_json_footer(
            _turn("probe_write",
                  render_probe_write(seed, root_cause_class, sites, feedback,
                                     probe_dir, cfg),
                  tools, cfg, directory, logs).get("result") or "",
            ("probes",))
        specs, truncated, rejections = emit_specs(
            written, seed, iteration, cap, probe_dir, cfg["run_manifest_id"],
            _turn_cost("probe_write", logs, cfg), cap_bytes)
    except PromptContractError as error:
        failure = f"prompt_contract:{error}"
    except Exception as error:                      # noqa: BLE001 - FR-04.8
        failure = f"turn_failed:{type(error).__name__}"
    finally:
        # CHIA's own chain stops its tools in a finally (chia:examples/circt_issue_solver/issue_task.py:282-289) and A3 does the same: without it, 187 seeds at up to 3 iterations is up to 561 orphaned actors on a fixed-size cluster (W11).
        for tool in (probe_write, source_read):
            if tool is not None:
                try:
                    tool.stop()
                except Exception:                   # noqa: BLE001
                    pass

    return {"specs": specs, "root_cause_class": root_cause_class,
            "sibling_sites": sites, "rejected_sites": rejected,
            "truncated": truncated, "rejections": rejections, "logs": logs,
            "failure": failure,
            "counters": CounterBlock(stage="stage_2", started=1,
                                     completed=0 if failure else 1,
                                     failed=1 if failure else 0,
                                     seconds=time.monotonic() - started)}


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def generate_mutation(seed: SeedRecord, feedback: FeedbackBundle,
                      remaining: LedgerSnapshot, cfg: dict) -> dict:
    """Apply the frozen mutator set to every changed test file of one seed.

    Returns:
        {"specs": list[ProbeSpec], "no_ops": int, "mutator_failures": dict, "logs": dict, "counters": CounterBlock}.
    Worker:
        {"circt": 1}.
    Raises:
        MutatorSetError when the set on disk is not the one the run's manifest names.
    """
    started = time.monotonic()
    iteration = int(cfg["iteration"])
    cap = int(cfg["per_seed_probe_cap"])
    cap_bytes = int(cfg.get("artefact_inline_cap_bytes", 262144))
    directory = iteration_dir(cfg, seed.seed_sha, iteration)
    probe_dir = str(Path(directory) / "probes")
    mutator_set = mutators.load_set(cfg.get("mutator_set_path"),
                                    expected_sha=cfg.get("mutator_set_sha"))
    produced, no_ops, failures = mutators.mutate_seed(
        seed, iteration, cap, mutator_set, seed_argv_template(seed))
    specs = []
    for mutator_id, source_test_path, text, seed_int, argv in produced:
        try:
            specs.append(_spec(
                seed=seed, arm="mutation", iteration=iteration,
                run_manifest_id=cfg["run_manifest_id"], probe_dir=probe_dir,
                text=text, tool=seed.entry_tool,
                expected_outcome=f"{mutator_id} applied to {source_test_path}",
                turn_cost={"turn": None,
                           "wall_seconds": time.monotonic() - started,
                           "tokens_in": None, "tokens_out": None,
                           "cost_usd": None, "metered": False},
                key=f"{mutator_id}|{source_test_path}|{seed_int}",
                cap_bytes=cap_bytes, mutator_id=mutator_id,
                mutator_seed_int=seed_int, source_test_path=source_test_path,
                argv_template=argv))
        except (ContractError, ValueError, OSError) as error:
            failures[mutator_id] = failures.get(mutator_id, 0) + 1
            failures.setdefault("_causes", {})[mutator_id] = str(error)
    return {"specs": specs, "no_ops": no_ops, "mutator_failures": failures,
            "logs": {}, "counters": CounterBlock(
                stage="stage_2", started=len(produced), completed=len(specs),
                failed=len(produced) - len(specs),
                seconds=time.monotonic() - started)}


__all__ = ["GENERATE_SYSTEM_MESSAGE", "PROMPTS",
           "REJECTION_REASONS", "SOURCE_READ_TIMEOUT_SECONDS",
           "ProbeWriteTool", "SourceReadTool", "check_tool", "emit_specs",
           "generate_mutation", "generate_seeded",
           "iteration_dir",
           "probe_argv", "probe_id", "render_argv_template",
           "render_feedback", "render_probe_write", "render_seed_read",
           "render_sites", "render_test_files",
           "seed_argv_template", "seed_language"]
