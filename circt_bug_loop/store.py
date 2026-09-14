"""loop.db: the LoopStore, its DDL, and every apparatus-internal record.

Nothing here crosses the seam. contract/schema.py is imported for the seven
members that do; the reverse import does not exist and tests/test_layout.py
asserts it.

The DDL below is 03-LLD.md 6.2 and 6.3 verbatim; tests/test_store.py compares
the two texts for equality, so a table that drifts from the design fails rather
than being discovered by a query. LoopStore is 6.1's construction: a SQLiteNode
pinned to the head when Ray is up, and a direct sqlite3 connection carrying the
same PRAGMA defaults when it is not, which is what lets every tier-0 test run
the real statements with no cluster (chia:chia/database/sqlite_node.py:105-143).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import typing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract import schema
from circt_bug_loop.contract.schema import ContractError, CounterBlock

def sha256_file(path: str) -> str:
    """The SHA-256 of one file's bytes, hex, streamed a megabyte at a time.

    One implementation and not three (N3): `probe_task` hashes the tool binary
    it is about to run (FR-06.1) and `repair_adapter` hashes `repro.sh` before
    and after the chain and every tool binary after the restore (FR-12.11), and
    each had spelled the same seven lines.

    Returns:
        str, 64 hex characters.
    Worker:
        the caller's; it reads one file and runs no process.
    Raises:
        OSError when the file cannot be read. A caller for whom an absent file
        is an ANSWER catches it and says so, which is `probe_task`'s case.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    """This moment, as the ISO 8601 string every `*_utc` column carries.

    One implementation and not three (N3): the driver and the approval CLI both
    stamp rows of this store, and a second spelling is a second answer to "what
    is the format" waiting to diverge.
    """
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


#: 03-LLD.md 6.2, the tables, verbatim.
_DDL_TABLES = """\
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS run (
    run_manifest_id     TEXT PRIMARY KEY,
    mode                TEXT NOT NULL CHECK (mode IN ('discovery','calibration')),
    seed_set            TEXT NOT NULL CHECK (seed_set IN ('187','171')),
    manifest_json       TEXT NOT NULL,       -- the whole RunManifest, canonical JSON
    budget_file_sha     TEXT NOT NULL,
    cluster_yaml_sha    TEXT NOT NULL,
    artefact_root       TEXT NOT NULL,
    started_utc         TEXT NOT NULL,
    ended_utc           TEXT
);

CREATE TABLE IF NOT EXISTS seed (
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    seed_sha            TEXT NOT NULL,
    parent_sha          TEXT NOT NULL,
    subject             TEXT NOT NULL,
    committed_date_utc  TEXT NOT NULL,
    llvm_pin            TEXT NOT NULL,
    sdk_tag             TEXT,
    sdk_exact           INTEGER NOT NULL,
    bumps_away          INTEGER,
    entry_tool          TEXT NOT NULL,
    dialect_bucket      TEXT NOT NULL,
    dialect_bucket_unmerged TEXT NOT NULL,
    eligible_seeded     INTEGER NOT NULL,    -- 0 for FR-01.9 and FR-01.10 exclusions
    eligible_mutation   INTEGER NOT NULL,
    exclusion_reason    TEXT,
    record_json         TEXT NOT NULL,       -- the whole SeedRecord, canonical JSON
    PRIMARY KEY (run_manifest_id, seed_sha)
);

CREATE TABLE IF NOT EXISTS sdk_map (
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    sdk_tag             TEXT NOT NULL,
    seed_shas_json      TEXT NOT NULL,
    PRIMARY KEY (run_manifest_id, sdk_tag)
);

CREATE TABLE IF NOT EXISTS image (
    image_digest        TEXT PRIMARY KEY,
    circt_sha           TEXT NOT NULL,
    sdk_tag             TEXT NOT NULL,
    image_tag           TEXT NOT NULL,
    flag_string         TEXT NOT NULL,
    targets_json        TEXT NOT NULL,
    cmake_args_json     TEXT NOT NULL,
    verilator_version   TEXT NOT NULL,
    slang_enabled       INTEGER NOT NULL,
    lit_discovery_ok    INTEGER NOT NULL,    -- FR-03.17
    lit_discovered_count INTEGER NOT NULL,   -- FR-03.17
    assertion_nonreferencing_json TEXT NOT NULL,
    tool_hashes_json    TEXT NOT NULL,
    built_utc           TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS probe (
    probe_id            TEXT PRIMARY KEY,
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    seed_sha            TEXT NOT NULL,
    arm                 TEXT NOT NULL CHECK (arm IN ('seeded','mutation')),
    iteration           INTEGER NOT NULL,
    tool                TEXT NOT NULL,
    argv_json           TEXT NOT NULL,
    polarity            TEXT NOT NULL,
    shape               TEXT NOT NULL,
    input_path          TEXT NOT NULL,
    mutator_id          TEXT,
    mutator_seed_int    INTEGER,
    source_test_path    TEXT,
    spec_json           TEXT NOT NULL,
    artefact_dir        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS probe_result (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    run_manifest_id     TEXT NOT NULL,
    arm                 TEXT NOT NULL,
    iteration           INTEGER NOT NULL,
    build_status        TEXT NOT NULL,
    oracle_fired        INTEGER NOT NULL,
    oracle_class        TEXT,
    stopping_stage      TEXT NOT NULL,
    stopping_reason     TEXT NOT NULL,
    result_json         TEXT NOT NULL,
    artefact_dir        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS build_result (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    run_commit          TEXT NOT NULL,
    image_digest        TEXT NOT NULL REFERENCES image(image_digest),
    status              TEXT NOT NULL,
    binary_path         TEXT NOT NULL,
    binary_sha256       TEXT NOT NULL,
    exit_status         INTEGER,
    signal              TEXT,
    limit_hit           TEXT CHECK (limit_hit IS NULL
                                    OR limit_hit IN ('wall','cpu','address_space')),
    cpu_seconds         REAL NOT NULL,       -- the child's rusage (K8)
    wall_seconds        REAL NOT NULL,
    peak_rss_bytes      INTEGER,
    worker_hostname     TEXT NOT NULL,       -- FR-13.2's pair, original half (K12)
    worker_node_id      TEXT NOT NULL,
    child_pid           INTEGER NOT NULL,
    stdout_path         TEXT NOT NULL,
    stderr_path         TEXT NOT NULL,
    truncated           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS oracle_verdict (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    fired               INTEGER NOT NULL,
    oracle_class        TEXT,
    assertion_text      TEXT,
    assertion_site      TEXT,
    fatal_message       TEXT,
    frames_json         TEXT NOT NULL,
    prologue_dropped    INTEGER NOT NULL,    -- 3.7.1's strip, so the count is auditable
    frames_resolved     INTEGER NOT NULL,
    frames_with_location INTEGER NOT NULL,
    fingerprint_frame   TEXT,                -- "<function> <basename>", NULL when none qualifies
    out_of_scope_root   INTEGER NOT NULL,
    repro_command       TEXT NOT NULL,
    flag_string         TEXT NOT NULL,
    tool_version_output TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS differential_verdict (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    verdict             TEXT NOT NULL,
    reason              TEXT NOT NULL,
    verilator_version   TEXT NOT NULL,
    x_policy            TEXT NOT NULL,
    stimulus_id         TEXT NOT NULL,
    port_list_sha       TEXT NOT NULL,       -- computed by B4 (3.6.3), '' on a harness_failure
    cycles              INTEGER NOT NULL,
    first_divergent_signal TEXT,
    first_divergent_cycle  INTEGER,
    arcilator_value     TEXT,
    verilator_value     TEXT,
    arcilator_trace_path TEXT,
    verilator_trace_path TEXT,
    driver_source       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reduced_case (
    probe_id            TEXT PRIMARY KEY REFERENCES probe(probe_id),
    reducer             TEXT NOT NULL CHECK (reducer IN ('circt-reduce','textual-ddmin','none')),
    reduced             INTEGER NOT NULL,
    fixpoint            INTEGER NOT NULL,
    budget_truncated    INTEGER NOT NULL,
    reason              TEXT,
    lift                TEXT,
    path                TEXT NOT NULL,
    size_before_bytes   INTEGER NOT NULL,
    size_after_bytes    INTEGER NOT NULL,
    size_before_ops     INTEGER NOT NULL,
    size_after_ops      INTEGER NOT NULL,
    wall_seconds        REAL NOT NULL,
    interestingness_calls INTEGER NOT NULL,
    recheck_class       TEXT,
    recheck_assertion_text TEXT,
    recheck_assertion_site TEXT,
    recheck_matches     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate (
    candidate_id        TEXT PRIMARY KEY,
    local_id            INTEGER UNIQUE,      -- LOCAL_ID_BASE + rowid, set at repair time
    probe_id            TEXT NOT NULL UNIQUE REFERENCES probe(probe_id),
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    arm                 TEXT NOT NULL,
    run_commit          TEXT NOT NULL,
    image_digest        TEXT NOT NULL,
    oracle_class        TEXT NOT NULL,
    assertion_text      TEXT,
    assertion_site      TEXT,
    frame_tuple_json    TEXT NOT NULL,
    out_of_scope_root   INTEGER NOT NULL,
    contaminated_symbol INTEGER NOT NULL,
    contaminated_file   INTEGER NOT NULL,
    contamination_lower_bound TEXT NOT NULL,
    triage_class        TEXT NOT NULL,
    held_reason         TEXT,
    taxonomy_bucket     TEXT,
    artefact_dir        TEXT NOT NULL,
    created_utc         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fingerprint (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    basis               TEXT NOT NULL CHECK (basis IN ('assertion','frames','insufficient')),
    value               TEXT,
    fingerprint_stable  INTEGER,             -- set by the gate re-run; NULL until it runs (K3)
    frame_tuple_json    TEXT NOT NULL,       -- evidence, never a merge key
    structural_hash     TEXT NOT NULL,       -- evidence, never a merge key
    -- FR-10.8 as a CHECK rather than as a comment: three sibling columns in this
    -- DDL carry CHECKs and this rule is the one a wrong INSERT would break
    -- silently (NIT 4).
    CHECK ((value IS NULL) = (basis = 'insufficient'))
);

CREATE TABLE IF NOT EXISTS dedup_verdict (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    verdict             TEXT NOT NULL,
    evidence_json       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    path                TEXT NOT NULL,
    template            TEXT NOT NULL CHECK (template IN ('primary','differential')),
    title               TEXT NOT NULL,
    classification      TEXT NOT NULL,
    classification_reason TEXT NOT NULL,
    rendered_sha256     TEXT NOT NULL,
    assisted_by         TEXT NOT NULL,
    fields_present_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repair (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    local_id            INTEGER NOT NULL,
    status              TEXT NOT NULL,
    failing_phase       TEXT,
    reproduced          INTEGER,
    build_ok            INTEGER,
    fixed               INTEGER,
    lit_ok              INTEGER,
    lit_unusable        INTEGER NOT NULL,    -- FR-12.8's erratum
    lit_passed          INTEGER,
    lit_failed          INTEGER,
    lit_failures_json   TEXT NOT NULL,
    diff_path           TEXT,
    diff_added          INTEGER,
    diff_removed        INTEGER,
    chia_artifact_dir   TEXT,
    chia_row_seen       INTEGER NOT NULL DEFAULT 0,   -- set by B12's reconciliation
    repro_dir           TEXT NOT NULL,       -- outside /workspace/circt (K9)
    repro_overwritten   INTEGER NOT NULL,    -- the reproduce turn replaced our script
    restore_ok          INTEGER NOT NULL,
    restore_hashes_match INTEGER NOT NULL,   -- FR-12.11's re-hash (W21)
    restore_log         TEXT NOT NULL,
    backend             TEXT NOT NULL,       -- cfg["backend"], "vertex" by default (3.8)
    token_capture       TEXT NOT NULL        -- why stage 7's tokens are not observed (3.8)
);

CREATE TABLE IF NOT EXISTS gate_decision (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    answers_json        TEXT NOT NULL,       -- the fifteen keys of 02-HLD.md 2.11
    stopped_at_question INTEGER,
    decision            TEXT NOT NULL CHECK (decision IN ('report','report_plus_patch','nothing')),
    taxonomy_bucket     TEXT,
    decided_utc         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS filing (
    candidate_id        TEXT PRIMARY KEY REFERENCES candidate(candidate_id),
    approver            TEXT NOT NULL,
    approved_at_utc     TEXT NOT NULL,
    decision            TEXT NOT NULL,
    licence_confirmed   INTEGER,
    licence_confirmed_at_utc TEXT,
    url_source          TEXT CHECK (url_source IN ('poll','pasted')),
    issue_number        INTEGER,
    issue_url           TEXT,
    prefill_url_length  INTEGER,
    prefill_fallback_reason TEXT,
    confirmed           INTEGER NOT NULL DEFAULT 0,
    confirmed_at_utc    TEXT,
    confirmation_url    TEXT
);

CREATE TABLE IF NOT EXISTS ledger_entry (
    entry_id            TEXT PRIMARY KEY,
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    arm                 TEXT NOT NULL CHECK (arm IN ('seeded','mutation','shared')),
    scope               TEXT NOT NULL CHECK (scope IN ('arm_window','stage')),
    stage               TEXT NOT NULL,
    unit                TEXT NOT NULL CHECK (unit = 'wall_clock_seconds'),
    amount              REAL NOT NULL CHECK (amount >= 0),
    metered             INTEGER NOT NULL,
    observed_json       TEXT NOT NULL,
    timestamp_utc       TEXT NOT NULL,
    stop_reason         TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    run_manifest_id     TEXT NOT NULL REFERENCES run(run_manifest_id),
    seed_sha            TEXT NOT NULL,
    arm                 TEXT NOT NULL,
    iteration           INTEGER NOT NULL,
    path                TEXT NOT NULL,       -- feedback.json in the iteration directory
    abandoned           INTEGER NOT NULL,
    abandon_reason      TEXT,
    terminating_condition TEXT,
    PRIMARY KEY (run_manifest_id, seed_sha, arm, iteration)
);

CREATE TABLE IF NOT EXISTS issue_mirror (
    issue_number        INTEGER PRIMARY KEY,
    title               TEXT NOT NULL,
    body                TEXT NOT NULL,
    labels_json         TEXT NOT NULL,
    state               TEXT NOT NULL CHECK (state IN ('open','closed')),
    url                 TEXT NOT NULL,
    mirrored_utc        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS issue_mirror_meta (
    run_manifest_id     TEXT PRIMARY KEY REFERENCES run(run_manifest_id),
    refreshed_utc       TEXT NOT NULL,
    issues_mirrored     INTEGER NOT NULL,
    issue_cap           INTEGER NOT NULL,
    cap_bound           INTEGER NOT NULL,
    state               TEXT NOT NULL,
    comments_mirrored   INTEGER NOT NULL CHECK (comments_mirrored = 0)
);
"""

#: 03-LLD.md 6.3, the nine indexes, verbatim.
_DDL_INDEXES = """\
CREATE INDEX IF NOT EXISTS ix_probe_run_seed_iter   ON probe(run_manifest_id, seed_sha, iteration);
CREATE INDEX IF NOT EXISTS ix_probe_result_run_arm  ON probe_result(run_manifest_id, arm);
CREATE INDEX IF NOT EXISTS ix_candidate_run_arm     ON candidate(run_manifest_id, arm);
CREATE INDEX IF NOT EXISTS ix_candidate_bucket      ON candidate(taxonomy_bucket);
CREATE INDEX IF NOT EXISTS ix_fingerprint_value     ON fingerprint(value);
CREATE INDEX IF NOT EXISTS ix_ledger_run_arm_scope  ON ledger_entry(run_manifest_id, arm, scope);
CREATE INDEX IF NOT EXISTS ix_ledger_day            ON ledger_entry(substr(timestamp_utc, 1, 10));
CREATE INDEX IF NOT EXISTS ix_mirror_state          ON issue_mirror(state);
CREATE INDEX IF NOT EXISTS ix_filing_confirmed      ON filing(confirmed);
"""

#: The one table 6.2 does NOT declare, and the reason it is a statement of its
#: own rather than a row of `_DDL_TABLES` (errata row 32): `T-U-store-01`
#: compares `_DDL_TABLES` to 03-LLD.md 6.2 for TEXTUAL equality, so a column
#: added to the `run` table there would either fail that comparison or need an
#: edit to a design document W-12 may not make. W-12 turned the pre-registration
#: into an annotated tag, and the architect's decision asks the run to record
#: WHICH registration it was checked against; `RunManifest.budget_file_sha`
#: stays the run's identity and gains nothing, so the contract does not move.
_DDL_REGISTRATION = """\
CREATE TABLE IF NOT EXISTS registration (
    run_manifest_id     TEXT PRIMARY KEY REFERENCES run(run_manifest_id),
    registration_tag    TEXT NOT NULL,
    registration_commit TEXT NOT NULL
);
"""

#: What init_schema runs. executescript takes the whole text at once.
_SCHEMA = _DDL_TABLES + "\n" + _DDL_INDEXES + "\n" + _DDL_REGISTRATION

#: The zero-byte marker of FR-17.8, named once.
PARTIAL = "PARTIAL"

#: SQLiteNode's own connect defaults, mirrored by the direct connection so the
#: two paths differ in dispatch and in nothing else
#: (chia:chia/database/sqlite_node.py:105-143).
_BUSY_TIMEOUT_S = 30.0
_SYNCHRONOUS = "NORMAL"

#: A table or column name is interpolated into SQL, never bound, so it is
#: checked rather than trusted (chia:chia/database/base.py's _IDENT_RE, which
#: cannot be imported here without importing ray).
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: /proc's mount table, a module constant so a test can point the check at a
#: recorded one. WAL corrupts on network storage, so the path is refused rather
#: than warned about (chia:chia/database/sqlite_node.py:29-33).
_MOUNTINFO = "/proc/self/mountinfo"
_NETWORK_FSTYPES = frozenset({"nfs", "nfs4", "cifs", "smbfs", "smb3", "9p",
                              "afs", "ceph", "glusterfs", "fuse.sshfs",
                              "fuse.s3fs", "lustre", "beegfs"})

#: The tables whose rows are a directory's completion record (6.5, FR-17.8).
#: A probe row is written before the probe runs and is therefore not one.
_COMPLETION_TABLES = ("probe_result", "candidate")


@dataclass(kw_only=True)
class SdkMap:
    """Exact-pin seeds grouped by the firtool-* tag their pin matches (FR-01.5)."""
    corpus_head_sha: str
    groups: dict                      # tag -> list[seed_sha]; 38 groups, median 3, max 27


@dataclass(kw_only=True)
class ImageSpec:
    """What B1 built, and the hashes that prove a probe ran it (FR-03.10, FR-03.16)."""
    circt_sha: str
    sdk_tag: str
    targets: list[str]
    flag_string: str
    cmake_args: list[str]             # the full configure line of 4.10, for the record
    image_digest: str
    image_tag: str                    # `chia-circt-assert:<CIRCT_SHA[:12]>` (K1)
    verilator_version: str
    slang_enabled: bool
    lit_discovery_ok: bool            # FR-03.17
    lit_discovered_count: int         # FR-03.17
    assertion_nonreferencing: list[str]   # FR-03.5's named objects, compared as a set
    tool_hashes: dict                 # tool name -> SHA-256 hex of the published binary
    #: SHA-256 over 4.11.1's six-key build manifest. The TAG names the CIRCT
    #: commit alone, which is the Dockerfile's own scheme, so two images of one
    #: commit built with a different SDK tag, target list, flag string, slang
    #: setting or base image share a tag and differ HERE (K1). It is NOT a
    #: column of `image`: 6.2's DDL is frozen against 03-LLD 6.2 by
    #: `T-U-store-01` and the design pass is what adds one, so the digest is
    #: durable as `<artefact_dir>/image_manifest.json`, which B1 writes beside
    #: `lit_discovery.txt` (errata W-20b). Defaulted so a record built from a
    #: stored row, which carries no such column, still constructs.
    manifest_digest: str = ""


@dataclass(kw_only=True)
class BuildResult:
    """One probe execution (FR-06.4, FR-06.5, FR-06.9). Produced by B2."""
    probe_id: str
    run_manifest_id: str
    run_commit: str
    image_digest: str
    status: Literal["clean_exit", "parse_error", "assertion", "fatal_error",
                    "crash", "timeout", "oom", "tool_unavailable"]
    binary_path: str                  # always under /workspace/circt/build/bin
    binary_sha256: str                # checked against ImageSpec.tool_hashes before the run
    argv: list[str]                   # the full argv, prlimit prefix included
    exit_status: Optional[int]        # null when the child died by signal or was killed
    signal: Optional[str]             # "SIG..." from the child's negative return code
    limit_hit: Optional[Literal["wall", "cpu", "address_space"]]
    cpu_seconds: float                # the child's own rusage, ru_utime + ru_stime (K8)
    wall_seconds: float               # non-deterministic, declared as such (NFR-02)
    peak_rss_bytes: Optional[int]     # non-deterministic, observational only
    worker_hostname: str              # socket.gethostname() in the executing worker (K12)
    worker_node_id: str               # ray.get_runtime_context().get_node_id()
    child_pid: int                    # the probe child's pid, for FR-13.2's pair
    stdout_path: str
    stderr_path: str
    stdout_bytes: int
    stderr_bytes: int
    truncated: bool                   # either stream hit the byte cap of FR-06.4


@dataclass(kw_only=True)
class Frame:
    """One stack frame of LLVM's crash trace, resolved (FR-07.4). In OracleVerdict.

    LLVM prints two shapes and 3.6.2 parses both. A `dladdr` frame ends
    "(<module>+0x<offset>)" and carries module and offset, which is what the
    symboliser needs; a print-time-symbolised frame ends "<file>:<line>:<col>"
    and carries no module, because LLVM already resolved it. `shape` records
    which, so no reader has to infer it from an empty field.
    """
    index: int
    address: str                      # "0x..." as printed by LLVM's own trace
    shape: Literal["module_offset", "attributed"]
    module: str                       # the object file; "" on an attributed frame
    offset: str                       # "0x..." within the module; "" on an attributed frame
    function: str                     # demangled and normalised; "" when unresolved
    file: str                         # "" when unresolved
    line: int                         # 0 when unresolved
    in_circt_object: bool             # 3.6.2's predicate; what FR-07.4 and FR-07.5 read


@dataclass(kw_only=True)
class OracleVerdict:
    """The primary oracle's answer for one probe (F-07). Produced by B3."""
    probe_id: str
    fired: bool
    oracle_class: Optional[Literal["assertion", "fatal_error", "crash"]]
    assertion_text: Optional[str]     # verbatim from stderr (FR-07.3)
    assertion_site: Optional[str]     # "<file>:<line>" verbatim from stderr
    fatal_message: Optional[str]      # the text after "LLVM ERROR:"
    frames: list[Frame]               # every frame, in trace order, prologue included
    prologue_dropped: int             # how many leading frames 3.7.1's strip removed
    frames_resolved: int              # frames with a non-empty function name
    frames_with_location: int         # frames with line > 0 AND in_circt_object (3.6.2)
    fingerprint_frame: Optional[str]  # "<function> <basename(file)>", the first stripped
                                      # frame in a CIRCT object with a resolved line
    out_of_scope_root: bool           # the first STRIPPED frame is not in a CIRCT object (FR-07.5)
    repro_command: str                # one line, runnable inside the image (FR-07.6)
    flag_string: str                  # carries the literal -UNDEBUG (FR-07.7)
    tool_version_output: str          # the tool's own --version, which still says "Optimized build."


@dataclass(kw_only=True)
class DifferentialVerdict:
    """arcilator against Verilator for one probe (F-08). Produced by B4."""
    probe_id: str
    verdict: Literal["agree", "diverge", "diverge_x_policy", "not_applicable",
                     "harness_failure"]
    reason: str                       # why not_applicable, or which arm failed
    verilator_version: str            # mandatory on every verdict (FR-03.15)
    x_policy: str
    stimulus_id: str
    port_list_sha: str                # 3.6.3: computed by B4, not by the generator
    cycles: int
    first_divergent_signal: Optional[str]
    first_divergent_cycle: Optional[int]
    arcilator_value: Optional[str]
    verilator_value: Optional[str]
    arcilator_trace_path: Optional[str]
    verilator_trace_path: Optional[str]
    driver_source: str                # "circt/arc-tests" or the recorded deviation (FR-08.11)


@dataclass(kw_only=True)
class ReducedCase:
    """The output of stage 5 (F-09). Produced by B5."""
    probe_id: str
    reducer: Literal["circt-reduce", "textual-ddmin", "none"]
    reduced: bool
    fixpoint: bool
    budget_truncated: bool            # NFR-02's visibility flag
    reason: Optional[str]             # why reduced is False (FR-09.12)
    lift: Optional[Literal["firtool --ir-fir", "firtool --parse-only",
                           "circt-verilog --ir-moore"]]
    path: str                         # the reduced input on disk
    size_before_bytes: int
    size_after_bytes: int
    size_before_ops: int
    size_after_ops: int
    wall_seconds: float
    interestingness_calls: int
    recheck_class: Optional[str]      # the re-run verdict's class (FR-09.3)
    recheck_assertion_text: Optional[str]
    recheck_assertion_site: Optional[str]
    recheck_matches: bool             # False sets reduction_changed_failure (FR-09.7)


@dataclass(kw_only=True)
class Fingerprint:
    """G-43's primary fingerprint plus its three evidence fields (FR-10.1)."""
    probe_id: str
    basis: Literal["assertion", "frames", "insufficient"]
    value: Optional[str]              # the fingerprint; null iff basis is insufficient
    frame_tuple: list[str]            # evidence, recorded even when the basis is assertion
    structural_hash: str              # evidence; never merges two candidates
    fingerprint_stable: Optional[bool]   # set by the gate's re-run (3.9 question 1); None
                                         # until it has run. False is REPORTED, never merged.


@dataclass(kw_only=True)
class DedupVerdict:
    """Whether a candidate is new, and the evidence for whatever it is (F-10)."""
    probe_id: str
    verdict: Literal["new", "duplicate_of_candidate", "known_open_issue",
                     "known_closed_issue", "fixed_post_pin", "dedup_unavailable"]
    evidence: dict                    # keys: matched_key, matched_token, issue_number,
                                      # issue_url, issue_state, issue_labels,
                                      # fixing_commit, duplicate_of_candidate_id


_DEDUP_EVIDENCE_KEYS = {"matched_key", "matched_token", "issue_number", "issue_url",
                        "issue_state", "issue_labels", "fixing_commit",
                        "duplicate_of_candidate_id"}
_DEDUP_EVIDENCE_REQUIRED = {
    "duplicate_of_candidate": ("matched_key", "duplicate_of_candidate_id"),
    "known_open_issue": ("matched_token", "issue_number", "issue_url", "issue_state",
                         "issue_labels"),
    "known_closed_issue": ("matched_token", "issue_number", "issue_url", "issue_state",
                           "issue_labels"),
    "fixed_post_pin": ("fixing_commit",),
    "dedup_unavailable": ("matched_key",),
    "new": (),
}


@dataclass(kw_only=True)
class Report:
    """The issue-shaped artefact a maintainer would read (G-25, FR-11.3)."""
    candidate_id: str
    path: str                         # <probe dir>/report.md
    template: Literal["primary", "differential"]
    title: str
    classification: Literal["bug", "invalid_input", "known_issue", "untriaged"]
    classification_reason: str        # at most 4 sentences [DEFAULT], 3.8.3
    rendered_sha256: str
    assisted_by: str                  # "<tool>:<model>" (FR-11.6, FR-20.3)
    fields_present: list[str]         # every FR-11.3 field the render substituted


@dataclass(kw_only=True)
class RepairResult:
    """CHIA's own chain result, unchanged in shape (FR-12.7). Produced by B8."""
    candidate_id: str
    local_id: int                     # the synthetic identifier of FR-12.2
    status: Literal["fixed", "attempted", "no_repro", "unclear", "not_a_bug", "error"]
    failing_phase: Optional[str]
    reproduced: Optional[bool]
    build_ok: Optional[bool]
    fixed: Optional[bool]
    lit_ok: Optional[bool]
    lit_unusable: bool                # FR-12.8's erratum: zero discovered is not red
    lit_passed: Optional[int]
    lit_failed: Optional[int]
    lit_failures: list[str]
    diff_path: Optional[str]
    diff_added: Optional[int]
    diff_removed: Optional[int]
    chia_artifact_dir: Optional[str]  # CHIA's own issue_logs/issue_<local_id>/
    repro_dir: str                    # 3.8's path, OUTSIDE /workspace/circt (K9)
    repro_overwritten: bool           # the reproduce turn replaced the pre-written script
    restore_ok: bool                  # FR-12.11's reset, rebuild AND re-hash
    restore_hashes_match: bool        # every tool binary re-hashed against ImageSpec (FR-12.11)
    restore_log: str
    backend: str                      # cfg["backend"], "vertex" by default (3.8, 13.1)
    token_capture: str                # why this stage's tokens are or are not observed
    # token_capture is "unavailable_remote_dispatch" on every backend CHIA's
    # chain implements, including vertex: _turn dispatches the turn with
    # chia_remote, so the LLM copy that accumulates _last_metadata dies on the
    # worker and QueryResult carries no usage (3.8, FR-14.6). It is a field of
    # RepairResult and NOT of LedgerEntry.observed, whose four declared keys are
    # frozen by 2.2's rule: adding one would be a MAJOR bump to 3.0.


@dataclass(kw_only=True)
class GateDecision:
    """The four answers and the verdict (F-13). Produced by B9a."""
    candidate_id: str
    q1_reproduce: Optional[bool]
    q1_original_worker: Optional[str]
    q1_rerun_worker: Optional[str]
    q1_original_pid: Optional[int]
    q1_rerun_pid: Optional[int]
    q1_same_worker: Optional[bool]
    q2_minimal: Optional[bool]
    q2_reason: Optional[str]
    q3_valid: Optional[bool]
    q3_validity_basis: Optional[Literal["parsed", "checker_failed"]]
    q3_after_parse: Optional[bool]    # FR-13.15's second conjunct (3.9 question 3)
    q3_exit_status: Optional[int]
    q3_stderr_path: Optional[str]
    q4_new: Optional[bool]
    q4_reason: Optional[str]
    stopped_at_question: Optional[int]
    decision: Literal["report", "report_plus_patch", "nothing"]
    taxonomy_bucket: Optional[Literal["unreproducible", "not_minimal", "invalid_input",
                                      "duplicate", "undecided", "new_bug"]]
    held_reason: Optional[str]


@dataclass(kw_only=True)
class FilingRecord:
    """One human approval, and the filing it authorised (F-13, F-20)."""
    candidate_id: str
    approver: str
    approved_at_utc: str
    decision: Literal["report", "report_plus_patch"]
    licence_confirmed: Optional[bool]     # FR-20.5; None when no patch was offered
    licence_confirmed_at_utc: Optional[str]
    url_source: Optional[Literal["poll", "pasted"]]
    issue_number: Optional[int]
    issue_url: Optional[str]
    prefill_url_length: Optional[int]
    prefill_fallback_reason: Optional[str]
    confirmed: bool                       # G-27: a maintainer acted, evidenced by a URL
    confirmed_at_utc: Optional[str]
    confirmation_url: Optional[str]


@dataclass(kw_only=True)
class BudgetLedger:
    """The aggregate over ledger_entry, as A6b maintains it (F-14)."""
    run_manifest_id: str
    per_arm_window: dict              # arm -> seconds spent on the primary unit
    per_arm_stage: dict               # arm -> {stage -> seconds occupancy}
    shared_stage: dict                # stage -> seconds occupancy, charged to no arm
    inputs_today: dict                # arm -> count, against the per-day safety cap
    filings_today: int                # THIS RUN's, per UTC day (W11)
    filings_total: int                # THIS RUN's (W11)
    spend_usd: float                  # campaign-wide, both arms and shared; 3.11
    per_arm_spend_usd: dict           # arm -> USD, reported beside the window
    stop_reason: dict                 # arm -> the cap or window that stopped it, or None
    #: Every filing the store holds, whatever run approved it. Reported for
    #: information and never compared against a cap: `loop.db` persists across
    #: runs (`--resume` depends on it), so counting lifetime against
    #: `budget.filings_total` stopped every arm of every later campaign at its
    #: very first `_arm_stop` and mined nothing (W11).
    filings_lifetime_total: int = 0


@dataclass(kw_only=True)
class CandidateRecord:
    """One probing input for which an oracle fired (G-23), and every downstream
    verdict about it. 02-HLD.md 5.3 is its field list; this is that list typed.

    Apparatus-internal: it crosses nothing, and ProbeResult carries what the
    generator is allowed to see.
    """
    candidate_id: str
    probe_id: str
    run_manifest_id: str
    arm: Literal["seeded", "mutation"]
    run_commit: str
    image_digest: str
    oracle_class: Literal["assertion", "fatal_error", "crash", "differential"]
    frame_tuple: list[str]
    frames_resolved: int
    frames_with_location: int
    out_of_scope_root: bool
    contaminated_symbol: bool
    contaminated_file: bool
    contamination_lower_bound: Literal["seed_commit", "run_commit"]
    triage_class: Literal["bug", "invalid_input", "known_issue", "untriaged"]
    artefact_dir: str
    assertion_text: Optional[str] = None
    assertion_site: Optional[str] = None
    repro_command: Optional[str] = None
    reducer: Optional[str] = None
    reduced: Optional[bool] = None
    fixpoint: Optional[bool] = None
    budget_truncated: Optional[bool] = None
    reduced_path: Optional[str] = None
    size_before_bytes: Optional[int] = None
    size_after_bytes: Optional[int] = None
    size_before_ops: Optional[int] = None
    size_after_ops: Optional[int] = None
    fingerprint: Optional[str] = None
    fingerprint_stable: Optional[bool] = None
    structural_hash: Optional[str] = None
    dedup_basis: Optional[Literal["assertion", "frames", "insufficient"]] = None
    dedup_verdict: Optional[str] = None
    dedup_evidence: Optional[dict] = None
    gate_answers: Optional[dict] = None
    gate_decision: Optional[str] = None
    taxonomy_bucket: Optional[str] = None
    held_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Connection and placement
# ---------------------------------------------------------------------------


def _ray_initialised() -> bool:
    """Report whether this process is already inside a Ray session.

    Read out of sys.modules rather than by importing ray: a process that has
    never imported ray cannot have initialised it, and importing it here would
    make every tier-0 test pay for a framework the head-side modules do not
    otherwise need.
    """
    ray = sys.modules.get("ray")
    return bool(ray is not None and ray.is_initialized())


def _fstype(path: str) -> str:
    """Return the filesystem type of the mount *path* lands on, or '' if unknown.

    The longest mount point that prefixes *path* wins, which is how the kernel
    resolves it. _MOUNTINFO is a module constant so a test can point this at a
    recorded table instead of the host's.
    """
    try:
        lines = Path(_MOUNTINFO).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    target = os.path.abspath(path)
    best, fstype = -1, ""
    for line in lines:
        fields = line.split()
        if "-" not in fields:
            continue
        point = fields[4]
        after = fields[fields.index("-") + 1:]
        if not after:
            continue
        if target == point or target.startswith(point.rstrip("/") + "/"):
            if len(point) > best:
                best, fstype = len(point), after[0]
    return fstype


def _connect(db_path: str, *, read_only: bool = False) -> sqlite3.Connection:
    """Open one connection carrying SQLiteNode's own PRAGMA defaults.

    WAL, a 30 s busy timeout, synchronous=NORMAL, foreign_keys=ON and
    isolation_level=None so writes take BEGIN IMMEDIATE explicitly, exactly as
    chia:chia/database/sqlite_node.py:105-143 does. This is the whole of the
    no-Ray path: the same statements against the same file, dispatched in
    process instead of as a Ray task.
    """
    conn = sqlite3.connect(db_path, timeout=_BUSY_TIMEOUT_S, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={int(_BUSY_TIMEOUT_S * 1000)}")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA synchronous={_SYNCHRONOUS}")
    if read_only:
        conn.execute("PRAGMA query_only=ON")
    return conn


def _ident(name: str) -> str:
    """Return *name* if it is a plain SQL identifier, else raise ValueError."""
    if not _IDENT.fullmatch(name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    return name


def init_schema(node: Any) -> None:
    """Create every table of 03-LLD.md 6.2 and every index of 6.3, idempotently.

    Plus `registration`, which 6.2 does not declare; see `_DDL_REGISTRATION`.

    *node* is either the SQLiteNode of 6.1, whose init_schema member runs the
    script as a Ray task on the pinned head, or an open sqlite3.Connection,
    which runs it here. Both take the same text, so the schema cannot differ
    between a campaign and a test. Every statement is CREATE ... IF NOT EXISTS,
    so a second call writes nothing.

    Returns:
        None.
    Worker:
        none of its own; the SQLiteNode member it calls declares
        {"num_cpus": 0.1} and is pinned to the head by pin_to_current_node.
    Raises:
        sqlite3.Error from the script, or whatever ray.get re-raises from the
        member call; TypeError if *node* is neither shape.
    """
    if isinstance(node, sqlite3.Connection):
        node.executescript(_SCHEMA)
        return
    member = getattr(node, "init_schema", None)
    if member is None:
        raise TypeError(f"init_schema takes a SQLiteNode or a Connection, not {node!r}")
    from chia.base.ChiaFunction import get
    get(member.chia_remote(_SCHEMA))


class LoopStore:
    """loop.db on the head's local disk, as a SQLiteNode.

    Constructed after ray.init(), because SQLiteNode pins to the current (head)
    Ray node and dispatches its members as Ray tasks. Never on network storage:
    WAL's shared-memory coordination only works between processes on one
    machine (C-14, chia:chia/database/sqlite_node.py:29-33).

    Outside a Ray session there is no node to dispatch to, so the same
    statements run through one direct connection carrying the node's own
    PRAGMA defaults. That is what makes every store test tier 0: the SQL is
    real, the file is real, and only the dispatch is absent.
    """

    def __init__(self, db_path: str) -> None:
        """Open loop.db at *db_path*, pinned to the head, and ensure the schema."""
        db_path = str(db_path)
        if not os.path.isabs(db_path):
            raise ValueError(
                f"db_path must be absolute (it is resolved on the target "
                f"machine's filesystem); got {db_path!r}")
        fstype = _fstype(os.path.dirname(db_path) or "/")
        if fstype in _NETWORK_FSTYPES:
            raise ValueError(
                f"db_path {db_path!r} is on {fstype}, which is network storage; "
                f"WAL can corrupt a database there (C-14)")
        self.db_path = db_path
        self.node = None
        if _ray_initialised():
            from chia.database.sqlite_node import SQLiteNode
            self.node = SQLiteNode(db_path, pin_to_current_node=True)
            init_schema(self.node)
        else:
            conn = _connect(db_path)
            try:
                init_schema(conn)
            finally:
                conn.close()

    # -- dispatch -----------------------------------------------------------

    def _get(self, member: str, *args) -> Any:
        """Run one SQLiteNode member, remotely under Ray and locally without it."""
        if self.node is not None:
            from chia.base.ChiaFunction import get
            return get(getattr(self.node, member).chia_remote(*args))
        return _LOCAL_MEMBERS[member](self.db_path, *args)

    # -- writes -------------------------------------------------------------

    def insert(self, table: str, row: dict) -> None:
        """Insert one row into *table*, one dict key per column.

        The caller renders the canonical-JSON text for the _json columns; this
        member adds no ORM and no coercion.

        Returns:
            None.
        Worker:
            {"num_cpus": 0.1}, the SQLiteNode member's own declaration.
        Raises:
            ValueError on a column name that is not a plain SQL identifier;
            sqlite3.IntegrityError on a primary-key or foreign-key violation.
        """
        self._get("execute", *_insert_sql(table, row))

    def insert_many(self, table: str, rows: list[dict]) -> None:
        """Insert *rows* into *table* in one transaction; an empty list is a no-op.

        Returns:
            None.
        Worker:
            {"num_cpus": 0.1}.
        Raises:
            ValueError on a column name that is not a plain SQL identifier or
            on rows whose key sets differ; sqlite3.IntegrityError as insert.
        """
        if not rows:
            return
        columns = list(rows[0])
        for row in rows:
            if list(row) != columns:
                raise ValueError("insert_many takes rows with one shared column list")
        sql, _ = _insert_sql(table, rows[0])
        self._get("executemany", sql, [tuple(r[c] for c in columns) for r in rows])

    def update(self, table: str, key: dict, fields: dict) -> None:
        """Set *fields* on the rows of *table* that *key* selects.

        Returns:
            None.
        Worker:
            {"num_cpus": 0.1}.
        Raises:
            ValueError on an empty key or field set, or on a name that is not a
            plain SQL identifier; sqlite3.Error from the statement.
        """
        if not fields or not key:
            raise ValueError("update takes a non-empty key and a non-empty field set")
        sets = ", ".join(f"{_ident(c)} = ?" for c in fields)
        where = " AND ".join(f"{_ident(c)} = ?" for c in key)
        self._get("execute", f"UPDATE {_ident(table)} SET {sets} WHERE {where}",
                  tuple(fields.values()) + tuple(key.values()))

    def transaction(self, ops: list) -> None:
        """Run *ops* atomically: BEGIN IMMEDIATE, each op in order, COMMIT.

        6.4's batching member. Each op is the (sql, params) pair
        SQLiteNode.transaction takes, and any error rolls the whole batch back
        (chia:chia/database/sqlite_node.py:377-423).

        Returns:
            None.
        Worker:
            {"num_cpus": 0.1}.
        Raises:
            TypeError on an op that is not a (sql, params) pair;
            sqlite3.Error from any statement, the batch rolled back.
        """
        self._get("transaction", list(ops))

    # -- reads --------------------------------------------------------------

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Return every row *sql* selects, as a list of dicts.

        Returns:
            list[dict], one per row, column name to value.
        Worker:
            {"num_cpus": 0.1}; the connection is opened query_only.
        Raises:
            sqlite3.Error from the statement.
        """
        return self._get("query", sql, params)

    def query_one(self, sql: str, params: tuple = ()) -> Optional[dict]:
        """Return the first row *sql* selects, or None.

        Returns:
            dict or None.
        Worker:
            {"num_cpus": 0.1}; the connection is opened query_only.
        Raises:
            sqlite3.Error from the statement.
        """
        return self._get("query_one", sql, params)


def _insert_sql(table: str, row: dict) -> tuple:
    """Render one INSERT and its parameter tuple for *row* of *table*."""
    columns = [_ident(c) for c in row]
    if not columns:
        raise ValueError("insert takes a non-empty row")
    return (f"INSERT INTO {_ident(table)} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})", tuple(row.values()))


def _local_execute(db_path: str, sql: str, params: tuple = ()) -> None:
    conn = _connect(db_path)
    try:
        _immediate(conn, [(sql, params)])
    finally:
        conn.close()


def _local_executemany(db_path: str, sql: str, seq: list) -> None:
    conn = _connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.executemany(sql, seq)
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        conn.execute("COMMIT")
    finally:
        conn.close()


def _local_transaction(db_path: str, ops: list) -> None:
    conn = _connect(db_path)
    try:
        _immediate(conn, ops)
    finally:
        conn.close()


def _immediate(conn: sqlite3.Connection, ops: list) -> None:
    """BEGIN IMMEDIATE, each op in order, COMMIT; any error rolls the batch back.

    chia:chia/database/sqlite_node.py:146-165 and 377-423, mirrored rather than
    imported so the no-Ray path needs no chia import at all.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        for i, op in enumerate(ops):
            try:
                sql, params = op
            except (TypeError, ValueError):
                raise TypeError(f"ops[{i}] must be a (sql, params) pair; got {op!r}") from None
            if params is None:
                conn.execute(sql)
            elif isinstance(params, list):
                conn.executemany(sql, params)
            elif isinstance(params, (tuple, dict)):
                conn.execute(sql, params)
            else:
                raise TypeError(
                    f"ops[{i}] params must be tuple/dict, list or None; "
                    f"got {type(params).__name__}")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise
    conn.execute("COMMIT")


def _local_query(db_path: str, sql: str, params: tuple = ()) -> list:
    conn = _connect(db_path, read_only=True)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _local_query_one(db_path: str, sql: str, params: tuple = ()) -> Optional[dict]:
    conn = _connect(db_path, read_only=True)
    try:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


#: The five SQLiteNode members LoopStore dispatches, and their in-process twins.
#: init_schema is not among them: it is a module-level function of its own,
#: because both shapes of *node* have to reach the same script.
_LOCAL_MEMBERS = {"execute": _local_execute, "executemany": _local_executemany,
                  "transaction": _local_transaction, "query": _local_query,
                  "query_one": _local_query_one}


# ---------------------------------------------------------------------------
# The artefact tree (6.5, FR-17.7, FR-17.8)
# ---------------------------------------------------------------------------


def _completed(store: "LoopStore", artefact_dir: str) -> bool:
    """Report whether the store holds a completion record for *artefact_dir*."""
    for table in _COMPLETION_TABLES:
        if store.query_one(f"SELECT 1 FROM {table} WHERE artefact_dir = ?",
                           (artefact_dir,)) is not None:
            return True
    return False


@ChiaFunction(max_retries=0)
def artefact_write(artefact_dir: str, relative_path: str, data,
                   *, mode: int = 0o644,
                   store: Optional["LoopStore"] = None) -> dict:
    """Write one file into the artefact tree, and count the write (3.11).

    A four-line wrapper around `write_artefact`, which is 6.5's body unchanged
    and is what every in-process caller uses, because what a caller needs is the
    path. The split exists because 3.11 requires every node of 3.2 to return
    `{"counters": CounterBlock}` and this body has three return statements
    (W-17, errata row 22).

    Returns:
        {"path": str, "counters": CounterBlock}, the path written (or, on a
        removal, the marker's), and one write counted at stage "artefact".
    Worker:
        {"num_cpus": 0.1} on the head; the artefact root is one host directory
        bind-mounted at the identical path on every worker (FR-17.9).
    Raises:
        whatever `write_artefact` raises, unchanged.
    """
    started_at = time.monotonic()
    path = write_artefact(artefact_dir, relative_path, data, mode=mode,
                          store=store)
    return {"path": path,
            "counters": CounterBlock(
                stage="artefact", started=1, completed=1, failed=0,
                seconds=time.monotonic() - started_at)}


def write_artefact(artefact_dir: str, relative_path: str, data,
                   *, mode: int = 0o644, store: Optional["LoopStore"] = None) -> str:
    """Write one file into the artefact tree, under the directory's PARTIAL marker.

    Every other file goes on disk with the marker already present: the marker is
    created here whenever it is absent, which is FR-17.8's "written before the
    stage begins writing anything else into the directory" enforced rather than
    asked for. Nothing is ever deleted, and nothing over
    artefact_inline_cap_bytes is inlined into a row: the return value is the
    path a row carries, and contract.bound_text is the one place the cap itself
    is applied (6.5, FR-17.7).

    relative_path == PARTIAL is the marker protocol and nothing else is. An
    empty *data* writes the zero-byte marker, a None *data* removes it, and the
    removal is refused unless *store* holds a completion record for the
    directory, so a stage that merely passed through cannot clear another
    stage's marker.

    Returns:
        str, the absolute path written (or, on a removal, the marker's path).
    Worker:
        {"num_cpus": 0.1} on the head; the artefact root is one host directory
        bind-mounted at the identical path on every worker (FR-17.9).
    Raises:
        ValueError on a relative artefact_dir, on a relative_path that escapes
        it, on a None *data* outside the marker protocol, or on a marker
        removal with no completion record; OSError from the write itself.
    """
    root = Path(artefact_dir)
    if not root.is_absolute():
        raise ValueError(f"artefact_dir must be absolute; got {artefact_dir!r}")
    # `realpath` and not `normpath` (N6): `normpath` is textual, so a symlink
    # ALREADY INSIDE the artefact directory - one a stage or a reducer put
    # there - is followed on the write and the bytes land wherever it points.
    # The root is resolved too, so a symlinked artefact root still compares.
    resolved_root = Path(os.path.realpath(str(root)))
    target = Path(os.path.realpath(str(root / relative_path)))
    if resolved_root not in target.parents:
        raise ValueError(f"{relative_path!r} escapes {artefact_dir!r}")
    marker = root / PARTIAL

    if relative_path == PARTIAL:
        if data is None:
            if store is None or not _completed(store, str(root)):
                raise ValueError(
                    f"refusing to clear the PARTIAL marker of {artefact_dir!r}: "
                    f"the store holds no completion record for it (FR-17.8)")
            if marker.exists():
                marker.unlink()
            return str(marker)
        if data not in (b"", ""):
            raise ValueError("the PARTIAL marker is a zero-byte file (6.5)")
        root.mkdir(parents=True, exist_ok=True)
        marker.touch()
        os.chmod(marker, mode)
        return str(marker)

    if data is None:
        raise ValueError("artefact_write removes the PARTIAL marker and nothing else")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        marker.touch()
        os.chmod(marker, 0o644)
    target.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    os.chmod(target, mode)
    return str(target)


# ---------------------------------------------------------------------------
# validate_candidate (2.9)
# ---------------------------------------------------------------------------

#: The table of 2.9, as three field groups. "The eleven reducer through
#: reduced_path plus the four size fields" is the prose; the table itself lists
#: nine and nine is what this tuple is.
_REDUCTION_FIELDS = ("reducer", "reduced", "fixpoint", "budget_truncated",
                     "reduced_path", "size_before_bytes", "size_after_bytes",
                     "size_before_ops", "size_after_ops")
_DEDUP_FIELDS = ("fingerprint", "fingerprint_stable", "structural_hash",
                 "dedup_basis", "dedup_verdict", "dedup_evidence")
_GATE_FIELDS = ("gate_answers", "gate_decision", "taxonomy_bucket")

#: Of the dedup group, the four a candidate must carry by the time it reaches
#: the gate. fingerprint is governed by the fingerprint rule (E012) and
#: fingerprint_stable is null until the gate's re-run has run (K3).
_DEDUP_REQUIRED = ("structural_hash", "dedup_basis", "dedup_verdict", "dedup_evidence")

#: The last row of 2.9's table: required in BOTH columns, a differential
#: candidate's frame_tuple being the empty list, which is a value and not a None.
_ALWAYS_REQUIRED = ("frame_tuple", "frames_resolved", "frames_with_location",
                    "out_of_scope_root", "contaminated_symbol", "contaminated_file",
                    "contamination_lower_bound")


def validate_candidate(candidate: "CandidateRecord") -> None:
    """Raise ContractError unless *candidate* satisfies every rule of its class.

    Checks, in this order: the class partition below; the fingerprint rule; the
    assertion-field rule; and the dedup-evidence key set and its per-verdict
    required keys. Returns None on success. It repairs, defaults and coerces
    nothing, and it never reads the database: the caller assembles the object
    with load_candidate() first.

    Called by dedup_and_screen before the candidate row is written, by
    triage_report before the report renders, by gate_decide before question 1,
    and by render_results over every row it counts, so a malformed candidate is
    refused at whichever of the four it reaches first (FR-10.5, FR-10.8,
    FR-13.14).

    Returns:
        None.
    Worker:
        pure; no resource, no process, no database handle.
    Raises:
        ContractError with one of the seven codes of 2.9: E003, E004, E005,
        E006, E011, E012 and E013.
    """
    hints = typing.get_type_hints(CandidateRecord)
    for name, annotation in hints.items():
        value = getattr(candidate, name)
        if value is not None:
            schema._check_field("CandidateRecord", name, value, annotation)

    differential = candidate.oracle_class == "differential"
    groups = (("reduction", _REDUCTION_FIELDS, _REDUCTION_FIELDS),
              ("dedup", _DEDUP_FIELDS, _DEDUP_REQUIRED),
              ("gate", _GATE_FIELDS, ()))
    for label, forbidden, required in groups:
        for name in forbidden:
            value = getattr(candidate, name)
            if differential and value is not None:
                raise ContractError(
                    "E006_CONDITIONAL_FORBIDDEN",
                    f"CandidateRecord.{name} must be None on a 'differential' "
                    f"candidate: the {label} stage is never dispatched")
        if not differential:
            for name in required:
                if getattr(candidate, name) is None:
                    raise ContractError(
                        "E005_CONDITIONAL_REQUIRED",
                        f"CandidateRecord.{name} is required of an "
                        f"{candidate.oracle_class!r} candidate at the gate")

    for name in _ALWAYS_REQUIRED:
        if getattr(candidate, name) is None:
            raise ContractError(
                "E005_CONDITIONAL_REQUIRED",
                f"CandidateRecord.{name} is required of every candidate, "
                f"'differential' included (FR-15.1)")

    if not differential:
        if (candidate.fingerprint is None) != (candidate.dedup_basis == "insufficient"):
            raise ContractError(
                "E012_FINGERPRINT_BASIS",
                f"CandidateRecord.fingerprint is "
                f"{'null' if candidate.fingerprint is None else 'set'} with "
                f"dedup_basis {candidate.dedup_basis!r} (FR-10.8)")

    for name in ("assertion_text", "assertion_site"):
        value = getattr(candidate, name)
        wanted = candidate.oracle_class == "assertion"
        if wanted and value is None:
            raise ContractError(
                "E005_CONDITIONAL_REQUIRED",
                f"CandidateRecord.{name} is required on oracle_class 'assertion'")
        if not wanted and value is not None:
            raise ContractError(
                "E006_CONDITIONAL_FORBIDDEN",
                f"CandidateRecord.{name} must be None on oracle_class "
                f"{candidate.oracle_class!r}")

    evidence = candidate.dedup_evidence
    if evidence is not None:
        if set(evidence) != _DEDUP_EVIDENCE_KEYS:
            difference = sorted(set(evidence) ^ _DEDUP_EVIDENCE_KEYS)
            raise ContractError(
                "E011_BAD_EVIDENCE_KEYS",
                f"CandidateRecord.dedup_evidence keys differ from the declared "
                f"set by {difference}")
        required = _DEDUP_EVIDENCE_REQUIRED.get(candidate.dedup_verdict, ())
        missing = [k for k in required if evidence[k] is None]
        if missing:
            raise ContractError(
                "E013_MISSING_EVIDENCE",
                f"dedup_verdict {candidate.dedup_verdict!r} requires "
                f"{sorted(missing)} in dedup_evidence (FR-10.5)")


def _b(value) -> Optional[bool]:
    """SQLite's INTEGER back to the bool the dataclass declares, NULL to None."""
    return None if value is None else bool(value)


def _j(value):
    """A _json column back to the object it holds, NULL to None."""
    return None if value is None else json.loads(value)


def load_candidate(store: "LoopStore", candidate_id: str) -> "CandidateRecord":
    """Join the six tables that hold one candidate back into one record.

    candidate persists twenty of CandidateRecord's fields and the rest live in
    oracle_verdict, reduced_case, fingerprint, dedup_verdict and gate_decision
    (NIT 3). This is the only reader of those five that returns a
    CandidateRecord, and what validate_candidate is given.

    A differential candidate has no reduced_case, fingerprint, dedup_verdict or
    gate_decision row by construction, so a missing row leaves its fields None,
    which is exactly what 2.9's table requires of that class.

    Returns:
        CandidateRecord, assembled; the caller validates it.
    Worker:
        {"num_cpus": 0.1} per query, on the head.
    Raises:
        LookupError when no candidate row carries *candidate_id*;
        sqlite3.Error from any of the six queries.
    """
    row = store.query_one("SELECT * FROM candidate WHERE candidate_id = ?",
                          (candidate_id,))
    if row is None:
        raise LookupError(f"no candidate row for {candidate_id!r}")
    oracle = store.query_one("SELECT * FROM oracle_verdict WHERE probe_id = ?",
                             (row["probe_id"],)) or {}
    reduced = store.query_one("SELECT * FROM reduced_case WHERE probe_id = ?",
                              (row["probe_id"],)) or {}
    finger = store.query_one("SELECT * FROM fingerprint WHERE candidate_id = ?",
                             (candidate_id,)) or {}
    dedup = store.query_one("SELECT * FROM dedup_verdict WHERE candidate_id = ?",
                            (candidate_id,)) or {}
    gate = store.query_one("SELECT * FROM gate_decision WHERE candidate_id = ?",
                           (candidate_id,)) or {}
    return CandidateRecord(
        candidate_id=row["candidate_id"],
        probe_id=row["probe_id"],
        run_manifest_id=row["run_manifest_id"],
        arm=row["arm"],
        run_commit=row["run_commit"],
        image_digest=row["image_digest"],
        oracle_class=row["oracle_class"],
        frame_tuple=json.loads(row["frame_tuple_json"]),
        frames_resolved=oracle.get("frames_resolved", 0),
        frames_with_location=oracle.get("frames_with_location", 0),
        out_of_scope_root=bool(row["out_of_scope_root"]),
        contaminated_symbol=bool(row["contaminated_symbol"]),
        contaminated_file=bool(row["contaminated_file"]),
        contamination_lower_bound=row["contamination_lower_bound"],
        triage_class=row["triage_class"],
        artefact_dir=row["artefact_dir"],
        assertion_text=row["assertion_text"],
        assertion_site=row["assertion_site"],
        repro_command=oracle.get("repro_command"),
        reducer=reduced.get("reducer"),
        reduced=_b(reduced.get("reduced")),
        fixpoint=_b(reduced.get("fixpoint")),
        budget_truncated=_b(reduced.get("budget_truncated")),
        reduced_path=reduced.get("path"),
        size_before_bytes=reduced.get("size_before_bytes"),
        size_after_bytes=reduced.get("size_after_bytes"),
        size_before_ops=reduced.get("size_before_ops"),
        size_after_ops=reduced.get("size_after_ops"),
        fingerprint=finger.get("value"),
        fingerprint_stable=_b(finger.get("fingerprint_stable")),
        structural_hash=finger.get("structural_hash"),
        dedup_basis=finger.get("basis"),
        dedup_verdict=dedup.get("verdict"),
        dedup_evidence=_j(dedup.get("evidence_json")),
        gate_answers=_j(gate.get("answers_json")),
        gate_decision=gate.get("decision"),
        taxonomy_bucket=row["taxonomy_bucket"],
        held_reason=row["held_reason"],
    )
