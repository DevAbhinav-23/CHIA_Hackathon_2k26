"""The one versioned seam between the supply half and the apparatus half."""
from __future__ import annotations

import dataclasses
import json
import typing
from dataclasses import dataclass
from typing import Any, Literal, Optional, Protocol

CONTRACT_VERSION = "2.3"          # MAJOR.MINOR; the single source of the string

Arm = Literal["seeded", "mutation"]
LedgerArm = Literal["seeded", "mutation", "shared"]
Polarity = Literal["expect_zero", "expect_nonzero"]
Shape = Literal["plain", "split_file", "unsupported"]
#: FR-06.9's seven, plus `tool_unavailable` at contract 2.1 (W-20b).
BuildStatus = Literal["clean_exit", "parse_error", "assertion", "fatal_error",
                      "crash", "timeout", "oom", "tool_unavailable"]
OracleClass = Literal["assertion", "fatal_error", "crash", "differential"]
LimitHit = Literal["wall", "cpu", "address_space"]
Scope = Literal["arm_window", "stage"]
Mode = Literal["discovery", "calibration"]
SeedSet = Literal["187", "171"]
Deployment = Literal["single_machine", "gcp"]
Unit = Literal["wall_clock_seconds"]

# The stage ids of 00-README.md, fixed there and not renameable.
_STAGE_IDS = ("stage_1", "stage_2", "stage_3", "stage_4", "stage_5",
              "stage_6", "stage_7", "gate")

#: The stages that run a MODEL turn.
_TOOL_LOOP_STAGES = ("stage_1", "stage_2", "stage_6", "stage_7")

# 03-LLD.md 2.1's table, as a tuple so a test can assert the set is closed.
ERROR_CODES = ("E001_MAJOR_MISMATCH", "E002_MISSING_FIELD", "E003_WRONG_TYPE",
               "E004_BAD_ENUM", "E005_CONDITIONAL_REQUIRED",
               "E006_CONDITIONAL_FORBIDDEN", "E007_BAD_DICT_KEYS",
               "E008_CAP_EXCEEDED", "E009_UNKNOWN_SCHEMA", "E010_TOOL_MISMATCH")


class ContractError(Exception):
    """Raised by validate()."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _major(version: str) -> str:
    """MAJOR half of a MAJOR.MINOR version string."""
    return version.split(".", 1)[0]


def check_version(instance_version: str) -> None:
    """Raise E001 unless *instance_version*'s MAJOR equals this package's."""
    if _major(instance_version) != _major(CONTRACT_VERSION):
        raise ContractError(
            "E001_MAJOR_MISMATCH",
            f"instance contract_version {instance_version!r} is incompatible "
            f"with package CONTRACT_VERSION {CONTRACT_VERSION!r}")


def canonical_json(document: Any) -> str:
    """Serialise ANY json-able value in the canonical shape, and nothing else."""
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False,
                      separators=(",", ": ")) + "\n"


def to_json(obj: Any) -> str:
    """Serialise a contract instance to canonical JSON text."""
    return canonical_json(dataclasses.asdict(obj))


def from_json(text: str, cls: type) -> Any:
    """Parse canonical JSON text into *cls*, then validate it."""
    if cls not in _MEMBERS:
        raise ContractError("E009_UNKNOWN_SCHEMA", f"{cls!r} is not a contract member")
    payload = json.loads(text)
    names = {f.name for f in dataclasses.fields(cls)}
    missing = sorted(names - set(payload))
    if missing:
        raise ContractError("E002_MISSING_FIELD",
                            f"{cls.__name__} payload lacks {missing}")
    obj = cls(**{k: v for k, v in payload.items() if k in names})
    validate(obj)
    return obj


@dataclass(kw_only=True)
class SeedRecord:
    """One mined CIRCT fix commit and everything both arms need from it."""
    contract_version: str = CONTRACT_VERSION
    seed_sha: str
    parent_sha: str
    subject: str
    committed_date_utc: str                 # ISO 8601 with an explicit offset
    source_paths: list[str]                 # under lib/ or include/, git order
    test_paths: list[str]                   # under test/ or integration_test/, git order, never collapsed
    llvm_pin: str                           # 40 hex characters
    sdk_tag: Optional[str] = None           # firtool-* or None
    sdk_exact: bool
    bumps_away: Optional[int] = None        # None when sdk_exact is True
    entry_tool: Literal["circt-opt", "firtool", "circt-verilog",
                        "circt-translate", "arcilator", "other"]
    dialect_bucket: str                     # FR-01.4's dialect-level rule, normative
    dialect_bucket_unmerged: str            # FR-01.4's second rule, for FINAL Appendix A
    run_lines: list[str]                    # verbatim RUN: lines, joined continuations
    argv_template: list[list[str]]          # one normalised argv per run line
    polarity: list[Polarity]                # one per run line
    shape: list[Shape]                      # one per run line
    diff: str                               # 2.0: the seed commit's diff of its source_paths
    test_files: dict[str, str]              # 2.0: test_paths -> full text at the seed commit
    corpus_head_sha: str


@dataclass(kw_only=True)
class BudgetFile:
    """The parsed, committed budget.yaml."""
    contract_version: str = CONTRACT_VERSION
    budget_file_sha: str                    # the commit that landed this file
    arm_window_seconds: float
    arm_order: list[Arm]
    model_id: str                           # one model for every agent stage
    campaign_spend_cap_usd: float           # a CAP, not the budget (G-48, ADR-D-04)
    price_usd_per_m_input_tokens: float     # the ledger's own arithmetic, 9.1
    price_usd_per_m_output_tokens: float    # the backend reports tokens, no price
    generated_inputs_per_day: int
    filings_per_day: int
    filings_total: int
    campaign_start_utc: str
    campaign_end_utc: str
    corpus_head_sha: str
    fingerprint_top_n: int
    calibration_sample_size: int
    calibration_sample_shas: list[str]
    per_seed_probe_cap: int
    per_seed_iteration_cap: int
    probe_wall_seconds: int
    probe_address_space_bytes: int
    probe_cpu_seconds: int
    probe_output_byte_cap: int
    reduction_wall_seconds: int
    reduction_sigkill_grace_seconds: int
    issue_mirror_issue_cap: int
    filing_poll_window_seconds: int
    artefact_inline_cap_bytes: int
    max_tool_iterations: dict               # keys in _TOOL_LOOP_STAGES (2.2)
    minimal_case_lines: int                 # FR-13.3's threshold (2.2)
    acceptance: dict                        # keys in 9.3


@dataclass(kw_only=True)
class ProbeSpec:
    """One probing input plus the exact invocation that consumes it."""
    contract_version: str = CONTRACT_VERSION
    probe_id: str
    run_manifest_id: str
    seed_sha: str
    arm: Arm
    iteration: int
    input_filename: str
    input_path: str                         # always set; absolute, under the artefact root
    tool: str
    argv: list[str]
    polarity: Polarity
    shape: Shape
    expected_outcome: str
    turn_cost: dict                         # keys in 2.7
    input_text: Optional[str] = None        # conditional, 2.12's cap rule; see below
    mutator_id: Optional[str] = None        # conditional on arm
    mutator_seed_int: Optional[int] = None  # conditional on arm
    source_test_path: Optional[str] = None  # conditional on arm
    differential: Optional[dict] = None     # keys in 2.7; None when FR-08.1 excludes the probe


@dataclass(kw_only=True)
class ProbeResult:
    """One per probing input, always produced, whatever the outcome."""
    contract_version: str = CONTRACT_VERSION
    probe_id: str
    run_manifest_id: str
    seed_sha: str
    arm: Arm
    iteration: int
    build_status: BuildStatus
    oracle_fired: bool
    stopping_stage: Literal["stage_3", "stage_4", "stage_5", "stage_6", "stage_7", "gate"]
    stopping_reason: str
    artefact_dir: str
    exit_status: Optional[int] = None
    signal: Optional[str] = None            # e.g. "SIGABRT"; never set together with a timeout
    limit_hit: Optional[LimitHit] = None
    oracle_class: Optional[OracleClass] = None      # non-null iff oracle_fired
    assertion_text: Optional[str] = None
    assertion_site: Optional[str] = None    # "<file>:<line>", normalised per 3.7.2
    reduced_text: Optional[str] = None      # conditional, 2.12's cap rule
    reduced_path: Optional[str] = None


@dataclass(kw_only=True)
class FeedbackEntry:
    """One per ProbeResult of the previous iteration."""
    probe_id: str
    stopped_at_stage: str
    reason: str
    oracle_class: Optional[str] = None
    oracle_summary: Optional[str] = None    # assertion text with its file:line, or the top frames
    reduced_text: Optional[str] = None      # conditional, 2.12's cap rule
    reduced_from_bytes: Optional[int] = None
    reduced_to_bytes: Optional[int] = None
    error_line: Optional[str] = None        # the probe's first `error:` line (2.3)


@dataclass(kw_only=True)
class FeedbackBundle:
    """What the seeded arm reads at the start of its next iteration."""
    contract_version: str = CONTRACT_VERSION
    run_manifest_id: str
    seed_sha: str
    arm: Arm
    iteration: int
    entries: list[FeedbackEntry]
    abandoned: bool
    terminating_condition: Optional[str] = None
    abandon_reason: Optional[str] = None    # conditional on abandoned

    def __post_init__(self) -> None:
        self.entries = [e if isinstance(e, FeedbackEntry) else FeedbackEntry(**e)
                        for e in self.entries]


@dataclass(kw_only=True)
class LedgerEntry:
    """One charge against the budget, or one observation of it."""
    contract_version: str = CONTRACT_VERSION
    entry_id: str
    run_manifest_id: str
    arm: LedgerArm
    scope: Scope
    stage: str
    unit: Unit
    amount: float
    metered: bool
    observed: dict                          # keys in 2.7
    timestamp_utc: str
    stop_reason: Optional[str] = None


@dataclass(kw_only=True)
class RunCommit:
    """One run commit."""
    commit: str
    seed_sha: Optional[str] = None          # None in discovery, set per seed in calibration


@dataclass(kw_only=True)
class RunManifest:
    """The identity of one run, stamped on every artefact of both halves."""
    contract_version: str = CONTRACT_VERSION
    run_manifest_id: str
    mode: Mode
    seed_set: SeedSet
    run_commit: list[RunCommit]
    pin_sha: str
    pin_tag: str
    tags_sharing_pin: list[str]
    lag_commits: int
    lag_days: float
    current_window_has_release: bool
    corpus_head_sha: str
    image_spec: dict                        # keys in 2.7
    assertion_baseline_count: int
    budget_unit: Unit
    arm_window_seconds: float
    arm_order: list[Arm]
    budget_file_sha: str
    cluster_yaml_sha: str
    deployment: Deployment
    worker_type: str
    apparatus_concurrency: int
    llm_concurrency: int
    artefact_root: str
    backend: str
    model_ids: dict                         # keys in 2.7
    stages_metered: dict                    # keys in 2.7
    mutator_set_sha: str
    x_policy: str
    issue_mirror: dict                      # keys in 2.7
    local_id_range: list[int]
    forum_post_url: str
    forum_post_date: str
    confirmation_cutoff_date: str
    differential_driver: dict               # keys in 2.7
    started_utc: str
    calibration_sample: Optional[list[str]] = None
    sv_seeds_excluded: Optional[list[str]] = None
    shard: Optional[str] = None             # "K/N" when --shard narrowed the corpus (2.3)
    ended_utc: Optional[str] = None

    def __post_init__(self) -> None:
        self.run_commit = [c if isinstance(c, RunCommit) else RunCommit(**c)
                           for c in self.run_commit]


@dataclass(kw_only=True)
class LedgerSnapshot:
    """What a generator may know about its own budget, and nothing else."""
    arm: Arm
    unit: Unit
    spent: float
    cap: float


class Generator(Protocol):
    """The driver's call into a generator."""

    def __call__(self, seed: SeedRecord, feedback: FeedbackBundle,
                 remaining: LedgerSnapshot) -> list[ProbeSpec]:
        ...


def generate(seed: SeedRecord, feedback: FeedbackBundle,
             remaining: LedgerSnapshot) -> list[ProbeSpec]:
    """The interface's canonical signature, declared beside the schemas it uses."""
    raise NotImplementedError


@dataclass(kw_only=True)
class CounterBlock:
    """FR-17.4's per-stage counters, returned by every node and logged by B12."""
    stage: str          # one of _STAGE_IDS, or one of the ten shared names in
                        # _COUNTER_STAGES below
    started: int        # units of work this node began: probes, seeds, issues
    completed: int      # of those, the ones that returned a record
    failed: int         # of those, the ones that did not; started == completed + failed
    seconds: float      # this node's own wall clock, start to return


#: The eight stage ids, plus a name for every node of 3.2 that is not one of the eight.
_COUNTER_STAGES = _STAGE_IDS + ("image", "corpus", "pin", "mirror", "synthesis",
                                "feedback", "budget", "ledger", "artefact",
                                "results")

_MEMBERS = (SeedRecord, BudgetFile, ProbeSpec, ProbeResult, FeedbackBundle,
            LedgerEntry, RunManifest)

_DICT_KEYS = {
    ("ProbeSpec", "turn_cost"): {"turn", "wall_seconds", "tokens_in", "tokens_out",
                                 "cost_usd", "metered"},
    ("ProbeSpec", "differential"): {"stimulus_id", "reset_protocol", "sample_point",
                                    "cycles", "port_list_sha"},
    ("BudgetFile", "max_tool_iterations"): set(_TOOL_LOOP_STAGES),
    # The four money fields are contract 2.2's (W-18b); `cached_tokens` is
    # contract 2.3's (W-23) and is a SUBSET of `tokens_in`, never a summand.
    ("LedgerEntry", "observed"): {"cpu_seconds", "tokens_in", "tokens_out", "cost_usd",
                                  "authorised_usd", "ceiling_usd", "billed_usd",
                                  "calls", "cached_tokens"},
    ("RunManifest", "image_spec"): {"circt_sha", "sdk_tag", "targets", "flag_string",
                                    "image_digest", "verilator_version", "slang_enabled",
                                    "tool_hashes"},
    ("RunManifest", "issue_mirror"): {"refreshed_utc", "issues_mirrored", "issue_cap",
                                      "cap_bound", "state", "comments_mirrored"},
    ("RunManifest", "differential_driver"): {"source", "commit", "deviation", "obstacle"},
    ("RunManifest", "model_ids"): {"generate_seeded", "triage_report", "repair_adapt",
                                   "mutator_synthesis"},
    ("RunManifest", "stages_metered"): set(_STAGE_IDS),
}


def _unwrap(annotation: Any) -> Any:
    """Strip Optional[...] down to the one non-None member it wraps."""
    if typing.get_origin(annotation) is typing.Union:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        return args[0] if len(args) == 1 else annotation
    return annotation


def _check_field(cls_name: str, name: str, value: Any, annotation: Any) -> None:
    """Raise E003 or E004 for one non-None field value."""
    ann = _unwrap(annotation)
    if typing.get_origin(ann) is Literal:
        if value not in typing.get_args(ann):
            raise ContractError(
                "E004_BAD_ENUM",
                f"{cls_name}.{name} is {value!r}, not one of {typing.get_args(ann)}")
        return
    base = typing.get_origin(ann) or ann
    if base is float and isinstance(value, int) and not isinstance(value, bool):
        return
    if base is int and isinstance(value, bool):
        raise ContractError("E003_WRONG_TYPE",
                            f"{cls_name}.{name} is bool, expected int")
    if isinstance(base, type) and not isinstance(value, base):
        raise ContractError("E003_WRONG_TYPE",
                            f"{cls_name}.{name} is {type(value).__name__}, "
                            f"expected {base.__name__}")


def validate(obj: Any) -> None:
    """Raise ContractError unless *obj* is a valid instance of its member class."""
    cls = type(obj)
    if cls not in _MEMBERS:
        raise ContractError("E009_UNKNOWN_SCHEMA", f"{cls.__name__} is not a contract member")
    check_version(obj.contract_version)
    hints = typing.get_type_hints(cls)
    for f in dataclasses.fields(cls):
        value = getattr(obj, f.name)
        optional = f.default is None
        if value is None:
            if not optional:
                raise ContractError("E002_MISSING_FIELD", f"{cls.__name__}.{f.name} is None")
            continue
        _check_field(cls.__name__, f.name, value, hints[f.name])
        want = _DICT_KEYS.get((cls.__name__, f.name))
        if want is not None and set(value) != want:
            raise ContractError(
                "E007_BAD_DICT_KEYS",
                f"{cls.__name__}.{f.name} keys {sorted(set(value))} "
                f"differ from {sorted(want)}")
    _CONDITIONALS[cls](obj)


def _require(cond: bool, code: str, message: str) -> None:
    if not cond:
        raise ContractError(code, message)


def _probe_spec_conditionals(o: ProbeSpec) -> None:
    mutation = o.arm == "mutation"
    for name in ("mutator_id", "mutator_seed_int", "source_test_path"):
        value = getattr(o, name)
        if mutation:
            _require(value is not None, "E005_CONDITIONAL_REQUIRED",
                     f"ProbeSpec.{name} is required when arm is 'mutation'")
        else:
            _require(value is None, "E006_CONDITIONAL_FORBIDDEN",
                     f"ProbeSpec.{name} must be None when arm is 'seeded'")
    _require(o.turn_cost["metered"] is (o.turn_cost["tokens_in"] is not None),
             "E005_CONDITIONAL_REQUIRED",
             "ProbeSpec.turn_cost.metered must agree with tokens_in")
    if mutation:
        _require(o.turn_cost["turn"] is None, "E006_CONDITIONAL_FORBIDDEN",
                 "ProbeSpec.turn_cost.turn must be None on the mutation arm")
    _require(o.input_text is not None or bool(o.input_path),
             "E002_MISSING_FIELD",
             "ProbeSpec carries its input inline or by path (FR-04.3, as amended)")


def _probe_result_conditionals(o: ProbeResult) -> None:
    _require((o.oracle_class is not None) == o.oracle_fired,
             "E005_CONDITIONAL_REQUIRED",
             "ProbeResult.oracle_class is non-null exactly when oracle_fired")
    if o.build_status == "timeout":
        _require(o.signal is None, "E006_CONDITIONAL_FORBIDDEN",
                 "a timeout carries a null signal (FR-06.4)")
    if o.reduced_text is not None:
        _require(o.reduced_path is not None, "E005_CONDITIONAL_REQUIRED",
                 "ProbeResult.reduced_text requires reduced_path")
    for name in ("assertion_text", "assertion_site"):
        _require((getattr(o, name) is not None) == (o.oracle_class == "assertion"),
                 "E005_CONDITIONAL_REQUIRED",
                 f"ProbeResult.{name} is non-null exactly on oracle_class 'assertion'")


def _budget_conditionals(o: BudgetFile) -> None:
    """The arm window, the model id and the three money figures (FR-14.1)."""
    _require(o.arm_window_seconds > 0, "E003_WRONG_TYPE",
             "BudgetFile.arm_window_seconds must be positive")
    _require(bool(o.model_id.strip()), "E002_MISSING_FIELD",
             "BudgetFile.model_id must name a model")
    for name in ("campaign_spend_cap_usd", "price_usd_per_m_input_tokens",
                 "price_usd_per_m_output_tokens"):
        _require(0 < getattr(o, name) < float("inf"), "E003_WRONG_TYPE",
                 f"BudgetFile.{name} must be positive and finite")
    # Contract 2.2.
    for stage, cap in sorted(o.max_tool_iterations.items()):
        _require(isinstance(cap, int) and not isinstance(cap, bool) and cap > 0,
                 "E003_WRONG_TYPE",
                 f"BudgetFile.max_tool_iterations[{stage!r}] must be a positive int")
    _require(o.minimal_case_lines > 0, "E003_WRONG_TYPE",
             "BudgetFile.minimal_case_lines must be positive")


def _feedback_conditionals(o: FeedbackBundle) -> None:
    _require((o.abandon_reason is not None) == o.abandoned,
             "E005_CONDITIONAL_REQUIRED",
             "FeedbackBundle.abandon_reason is non-null exactly when abandoned")


def _ledger_conditionals(o: LedgerEntry) -> None:
    _require(o.amount >= 0.0, "E003_WRONG_TYPE", "LedgerEntry.amount must not be negative")


def _manifest_conditionals(o: RunManifest) -> None:
    if o.mode == "discovery":
        _require(len(o.run_commit) == 1 and o.run_commit[0].seed_sha is None,
                 "E005_CONDITIONAL_REQUIRED",
                 "a discovery manifest carries exactly one run_commit with a null seed_sha")
    else:
        _require(o.run_commit and all(c.seed_sha is not None for c in o.run_commit),
                 "E005_CONDITIONAL_REQUIRED",
                 "a calibration manifest carries one run_commit per sampled seed")
        _require(o.calibration_sample is not None
                 and len(o.run_commit) == len(o.calibration_sample)
                 and {c.seed_sha for c in o.run_commit} == set(o.calibration_sample),
                 "E005_CONDITIONAL_REQUIRED",
                 "a calibration manifest's run_commit entries are exactly its sample")
    _require(set(o.arm_order) == {"seeded", "mutation"} and len(o.arm_order) == 2,
             "E004_BAD_ENUM", "RunManifest.arm_order names both arms exactly once")
    _require(len(o.local_id_range) == 2 and o.local_id_range[0] < o.local_id_range[1],
             "E003_WRONG_TYPE", "RunManifest.local_id_range is an ordered pair")


_CONDITIONALS = {
    SeedRecord: lambda o: _require(
        len(o.argv_template) == len(o.run_lines) == len(o.polarity) == len(o.shape),
        "E005_CONDITIONAL_REQUIRED",
        "SeedRecord's four per-run-line lists must be the same length"),
    BudgetFile: _budget_conditionals,
    ProbeSpec: _probe_spec_conditionals,
    ProbeResult: _probe_result_conditionals,
    FeedbackBundle: _feedback_conditionals,
    LedgerEntry: _ledger_conditionals,
    RunManifest: _manifest_conditionals,
}


def bound_text(text: Optional[str], path: Optional[str], cap: int) -> Optional[str]:
    """Return *text* if it fits under *cap* bytes, else None (the path carries it)."""
    if text is None:
        return None
    if len(text.encode("utf-8")) <= cap:
        return text
    if path is None:
        raise ContractError("E008_CAP_EXCEEDED",
                            f"text of {len(text.encode('utf-8'))} bytes exceeds "
                            f"the {cap}-byte cap and has no companion path")
    return None


__all__ = [
    "CONTRACT_VERSION", "ERROR_CODES", "ContractError", "canonical_json",
    "Arm", "LedgerArm", "Polarity", "Shape", "BuildStatus", "OracleClass",
    "LimitHit", "Scope", "Mode", "SeedSet", "Deployment", "Unit",
    "SeedRecord", "BudgetFile", "ProbeSpec", "ProbeResult", "FeedbackEntry",
    "FeedbackBundle", "LedgerEntry", "RunCommit", "RunManifest",
    "LedgerSnapshot", "CounterBlock", "Generator", "generate",
    "check_version", "validate", "to_json", "from_json", "bound_text",
]
