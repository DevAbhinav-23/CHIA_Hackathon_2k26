"""B6a, B6b and B7: the issue mirror, the fingerprint, the two screens, the triage turn and the report render (03-LLD.md 3.7)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from types import SimpleNamespace
from typing import Literal, Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import (CounterBlock, RunManifest,
                                            SeedRecord)
from circt_bug_loop.llm import (PromptContractError,  # noqa: F401
                                dispatch_turn, parse_json_footer, tool_iterations)
from circt_bug_loop.probe_task import (_last_pass, _normalise_function,
                                       generalise_types, strip_prologue,
                                       verifier_detail)
from circt_bug_loop.store import (CandidateRecord, DedupVerdict,
                                  DifferentialVerdict, Fingerprint, LoopStore,
                                  OracleVerdict, ReducedCase, Report,
                                  validate_candidate, write_artefact)

#: 03-LLD.md 9.4's two implementation constants of this module.
TRIAGE_REASON_MAX_SENTENCES = 4
MIRROR_TOKEN_MIN_CHARS = 8

#: The label CIRCT's own policy forbids an AI tool to act on (`circt:docs/AIToolPolicy.md:24`).
GOOD_FIRST_ISSUE = "good first issue"

#: 3.7.1's build prefix.
BUILD_PREFIX = "/workspace/circt/"

#: 7.4's stage-6 prompt, beside this module (1.1).
PROMPTS = Path(__file__).resolve().parent / "prompts"

#: B7's system message.
TRIAGE_SYSTEM_MESSAGE = (
    "You write CIRCT bug reports from tool output. You state observed behaviour "
    "only, you never restate a number, and you end with one fenced json block.")

#: The literal 7.4 binds the six primary variables to for a `differential` candidate.
NOT_APPLICABLE = "not applicable to a differential candidate"

#: 7.4.1's prior-art point: the driver a differential report names (FR-08.7).
ARC_TESTS = "circt/arc-tests"

#: The top-level source directories a CIRCT frame path is made relative to.
_SRC_ROOTS = ("lib/", "include/", "tools/", "test/", "frontends/",
              "integration_test/")

#: 6.5's write, as the plain function and not as B10b's node.
_artefact_write = write_artefact

_SENTENCE_END = re.compile(r"(?<=[.!?])(?:\s+|$)")
_SSA = re.compile(r"%[A-Za-z0-9_$.\-]+")
_SYMBOL = re.compile(r"@[A-Za-z0-9_$.\-]+")
_LOC = re.compile(r"loc\([^()]*(?:\([^()]*\)[^()]*)*\)")
_COMMIT = re.compile(r"^__C__ (?P<sha>[0-9a-f]{7,40}) (?P<date>\S+)$")
_HUNK = re.compile(r"^@@ [^@]*@@ ?(?P<context>.*)$")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: The twelve declared keys of `DedupVerdict.evidence` (2.9, D-16, D-17).
_EVIDENCE_KEYS = ("matched_key", "matched_token", "issue_number", "issue_url",
                  "issue_state", "issue_labels", "fixing_commit",
                  "duplicate_of_candidate_id", "post_pin_file_touches",
                  "rescreened_from", "generic_text_match", "op_only_match")

#: Headers whose assertions are MLIR's or LLVM's and name no CIRCT code (D-16).
GENERIC_ASSERTION_ROOTS = ("include/mlir/", "include/llvm/", "llvm/Support/")

#: The generic assertion texts campaign 2 and pilot 1 mis-matched on (D-16).
GENERIC_ASSERTIONS = (
    "succeeded( ConcreteT::verifyInvariants(getDefaultDiagnosticEmitFn(ctx), "
    "args...))",
    'isa<To>(Val) && "cast<Ty>() argument of incompatible type!"')

#: How many file-level post-pin shas D-11's evidence carries.
POST_PIN_FILE_TOUCH_MAX = 5


class ReportIncomplete(Exception):
    """A substitution point the chosen template declares is absent (FR-11.3)."""


def normalise_expr(text: str) -> str:
    """Collapse whitespace runs in an assertion expression and strip the ends."""
    return " ".join((text or "").split())


def normalise_site(site: str) -> str:
    """Drop an assertion site's build prefix, keeping the line number verbatim."""
    path, sep, line = (site or "").rpartition(":")
    if not sep or not line.isdigit():
        path, line, sep = site or "", "", ""
    if path.startswith(BUILD_PREFIX):
        path = path[len(BUILD_PREFIX):]
    elif path.startswith("/"):
        path = "/".join([p for p in path.split("/") if p][-2:])
    return f"{path}:{line}" if sep else path


_GENERIC_TEXTS = frozenset(normalise_expr(text) for text in GENERIC_ASSERTIONS)


def structural_hash(text: str) -> str:
    """Hash a reduced case with every name that reduction can rewrite removed."""
    normalised = _LOC.sub("loc(_)", text or "")
    normalised = _SSA.sub("%_", normalised)
    normalised = _SYMBOL.sub("@_", normalised)
    return hashlib.sha256(" ".join(normalised.split()).encode("utf-8")).hexdigest()


def compute_fingerprint(verdict: OracleVerdict, signal: Optional[str],
                        reduced_text: str, top_n: int, *,
                        pass_name: str = "") -> Fingerprint:
    """Compute G-43's primary fingerprint and its three evidence fields."""
    stripped = strip_prologue(list(verdict.frames))
    names = [_normalise_function(frame.function) for frame in stripped]
    resolved = sum(1 for frame in stripped if frame.function)
    tuple_evidence = names[:top_n]

    if verdict.oracle_class == "verifier_error" and verdict.verifier_op:
        # D-13: the op, the invariant with every concrete type generalised to
        # `T`, and the pass that produced the op. Two probes that break the same
        # invariant on the same op with different aggregate types are one bug.
        basis = "verifier"
        value = (f"{verdict.verifier_op}\n"
                 f"{generalise_types(verdict.verifier_message or '')}\n"
                 f"{pass_name}")
    elif verdict.oracle_class == "assertion" and verdict.assertion_text:
        basis = "assertion"
        value = (f"{normalise_expr(verdict.assertion_text)}\n"
                 f"{normalise_site(verdict.assertion_site or '')}")
    elif verdict.fingerprint_frame:
        basis, value = "frames", f"{signal or ''}\n{verdict.fingerprint_frame}"
    elif resolved >= top_n:
        basis, value = "frames", "\n".join(tuple_evidence)
    else:
        basis, value = "insufficient", None

    return Fingerprint(probe_id=verdict.probe_id, basis=basis, value=value,
                       frame_tuple=tuple_evidence,
                       structural_hash=structural_hash(reduced_text),
                       fingerprint_stable=None)


def is_duplicate(left: Fingerprint, right: Fingerprint) -> bool:
    """Report whether two candidates are duplicates under FR-10.2, and nothing else."""
    if left.probe_id == right.probe_id:
        return True
    return left.value is not None and left.value == right.value


def partition(fingerprints: list) -> list:
    """Partition candidates into duplicate classes, independent of arrival order."""
    blocks: dict = {}
    singletons: list = []
    for item in fingerprints:
        if item.value is None or item.fingerprint_stable is not True:
            singletons.append(frozenset({item.probe_id}))
        else:
            blocks.setdefault(item.value, set()).add(item.probe_id)
    out = [frozenset(members) for members in blocks.values()] + singletons
    return sorted(out, key=lambda block: min(block))


def rates(pairs: list) -> dict:
    """Measure FR-10.2's collision and false-merge rates over labelled pairs."""
    distinct = [p for p in pairs if p["label"] == "distinct"]
    duplicate = [p for p in pairs if p["label"] == "duplicate"]
    collisions = sum(1 for p in distinct if is_duplicate(p["a"], p["b"]))
    false_merges = sum(1 for p in duplicate if not is_duplicate(p["a"], p["b"]))
    return {"collision_rate": collisions / len(distinct) if distinct else 0.0,
            "false_merge_rate": false_merges / len(duplicate) if duplicate else 0.0,
            "collisions": collisions, "distinct_pairs": len(distinct),
            "false_merges": false_merges, "duplicate_pairs": len(duplicate)}


def labelled_fingerprint(side: dict, top_n: int) -> Fingerprint:
    """One side of an FR-10.2 labelled pair, fingerprinted from the pair's own record."""
    verdict = SimpleNamespace(
        probe_id=side["candidate_id"], oracle_class=side["oracle_class"],
        assertion_text=side.get("assertion_text"),
        assertion_site=side.get("assertion_site"),
        fingerprint_frame=side.get("fingerprint_frame"),
        # `strip_prologue` reads a frame's function and its module, and a labelled side records the names alone.
        frames=[SimpleNamespace(function=name, module="")
                for name in side["frame_names"]])
    return compute_fingerprint(verdict, side.get("signal"),
                               side.get("reduced", ""), top_n)


def verifier_tokens(verdict: OracleVerdict) -> tuple:
    """A verifier candidate's op and its constraint phrase, normalised as the fingerprint is (D-17)."""
    return (verdict.verifier_op or "",
            generalise_types(verifier_detail(verdict.verifier_message or "")[2]
                             or ""))


def mirror_tokens(verdict: OracleVerdict) -> list:
    """The screen's tokens for one candidate, per oracle class, and nothing else."""
    function = (verdict.fingerprint_frame or "").rsplit(" ", 1)[0]
    if verdict.oracle_class == "verifier_error":
        found = list(verifier_tokens(verdict))
    elif verdict.oracle_class == "assertion":
        found = [verdict.assertion_text, verdict.assertion_site]
    elif verdict.oracle_class == "crash":
        found = [function]
    elif verdict.oracle_class == "fatal_error":
        found = [function, verdict.fatal_message]
    else:
        found = []
    out: list = []
    for token in found:
        if token and len(token) >= MIRROR_TOKEN_MIN_CHARS and token not in out:
            out.append(token)
    return out


def mirror_screen(store: LoopStore, tokens: list) -> Optional[dict]:
    """Query the local mirror once per token and pick the issue that decides."""
    hits: list = []
    for order, token in enumerate(tokens):
        for row in store.query(
                "SELECT issue_number, state, url, labels_json FROM issue_mirror "
                "WHERE instr(title || ' ' || body, ?) > 0 ORDER BY issue_number",
                (token,)):
            labels = json.loads(row["labels_json"])
            hits.append({"matched_token": token,
                         "issue_number": row["issue_number"],
                         "issue_url": row["url"], "issue_state": row["state"],
                         "issue_labels": labels,
                         "_rank": (0 if GOOD_FIRST_ISSUE in labels else 1,
                                   0 if row["state"] == "open" else 1,
                                   order, row["issue_number"])})
    if not hits:
        return None
    best = min(hits, key=lambda hit: hit["_rank"])
    return {key: best[key] for key in
            ("matched_token", "issue_number", "issue_url", "issue_state",
             "issue_labels")}


def generic_assertion(verdict: OracleVerdict) -> bool:
    """Whether the assertion is MLIR's or LLVM's, so its text names no CIRCT code (D-16)."""
    if verdict.oracle_class != "assertion":
        return False
    site = (verdict.assertion_site or "").replace("\\", "/")
    return (any(root in site for root in GENERIC_ASSERTION_ROOTS)
            or normalise_expr(verdict.assertion_text or "") in _GENERIC_TEXTS)


def circt_frame_tokens(verdict: OracleVerdict) -> list:
    """The top CIRCT frame's whole function and its file, and not the bare last component."""
    function, _, basename = (verdict.fingerprint_frame or "").rpartition(" ")
    return [token for token in (function, basename) if token]


def mirror_carries(store: LoopStore, issue_number: int, token: str) -> bool:
    """Whether one mirrored issue's own title or body carries *token*."""
    return bool(token) and store.query_one(
        "SELECT 1 AS hit FROM issue_mirror WHERE issue_number = ? "
        "AND instr(title || ' ' || body, ?) > 0", (issue_number, token)) is not None


def mirror_corroborates(store: LoopStore, issue_number: int, tokens: list) -> bool:
    """Whether the matched issue's own text carries one of the candidate's frame tokens."""
    return any(mirror_carries(store, issue_number, token) for token in tokens)


def verifier_corroborates(store: LoopStore, issue_number: int,
                          verdict: OracleVerdict) -> bool:
    """Whether the matched issue carries BOTH the op and the constraint phrase (D-17)."""
    return all(mirror_carries(store, issue_number, token)
               for token in verifier_tokens(verdict))


def frame_paths(verdict: OracleVerdict) -> list:
    """The candidate's source paths, as git pathspecs against the clone."""
    files = [frame.file for frame in verdict.frames
             if frame.in_circt_object and frame.file]
    if verdict.assertion_site:
        # The RAW site, not the normalised one.
        files.append(verdict.assertion_site.rpartition(":")[0])
    out = set()
    for path in files:
        norm = path.replace("\\", "/")
        for root in _SRC_ROOTS:
            index = norm.find("/" + root)
            if index >= 0:
                out.add(norm[index + 1:])
                break
            if norm.startswith(root):
                out.add(norm)
                break
        else:
            out.add(":(glob)**/" + os.path.basename(norm))
    return sorted(out)


def frame_symbols(verdict: OracleVerdict) -> set:
    """The candidate's function names, for 3.7.2's symbol-level match."""
    out = set()
    for frame in strip_prologue(list(verdict.frames)):
        if not frame.in_circt_object:
            continue
        name = _normalise_function(frame.function)
        if not name or name == "operator":
            continue
        out.add(name)
        out.add(name.rsplit("::", 1)[-1])
    return out


def commit_date(clone_path: str, commit: str, *, timeout: int = 60) -> str:
    """Read one commit's committer date from the clone, as strict ISO 8601."""
    out = subprocess.run(["git", "-C", clone_path, "log", "-1", "--format=%cI",
                          commit], capture_output=True, text=True, check=True,
                         timeout=timeout)
    return out.stdout.strip()


def scan_commits(clone_path: str, since: str, paths: list, *,
                 timeout: int = 900) -> list:
    """Walk `main` from *since* to the clone head over *paths*, one command."""
    if not paths:
        return []
    out = subprocess.run(
        ["git", "-C", clone_path, "log", "--first-parent", "-p",
         "--unified=0", "--no-renames", "--format=__C__ %H %cI",
         f"--since={since}", "--"] + list(paths),
        capture_output=True, text=True, check=True, timeout=timeout)
    commits: list = []
    for line in out.stdout.splitlines():
        header = _COMMIT.match(line)
        if header:
            commits.append({"sha": header.group("sha"),
                            "date": header.group("date"), "contexts": []})
            continue
        hunk = _HUNK.match(line)
        if hunk and commits:
            commits[-1]["contexts"].append(hunk.group("context"))
    return commits


def _after(commits: list, bound: Optional[str]) -> list:
    """Drop the bound commit itself, which `--since <its own date>` includes."""
    return [c for c in commits if bound is None or c["sha"] != bound]


def touches_symbol(commit: dict, symbols: set) -> bool:
    """Report whether a commit's hunk-header contexts name one of *symbols*."""
    if not symbols:
        return False
    for context in commit["contexts"]:
        if symbols & set(_WORD.findall(context)):
            return True
    return False


#: GitHub's own pagination ceiling on the issues-listing endpoint (C-22).
MIRROR_PAGE_CEILING = 100

#: The status a refused page answers with.
_CEILING_STATUS = "422"


def mirror_walk(node, direction: str, cap: int, seen: set) -> tuple:
    """Page llvm/circt's issue listing in ONE direction, dropping pull requests."""
    from chia.github.github_client import GithubError, GithubRequestError

    path = f"/repos/{node.owner}/{node.name}/issues"
    issues: list = []
    pages = 0
    ceiling_hit = False
    reason = None
    for page in range(1, MIRROR_PAGE_CEILING):
        if len(seen) >= cap:
            break
        try:
            items = node._request(path, params={
                "state": node.state, "sort": "created", "direction": direction,
                "per_page": node._PER_PAGE, "page": page})
        except GithubError as error:
            # Only the ceiling's own 422 is the ceiling.
            if (isinstance(error, GithubRequestError)
                    and str(error).startswith(_CEILING_STATUS)):
                ceiling_hit = True
            else:
                reason = type(error).__name__
            break
        pages += 1
        if not isinstance(items, list) or not items:
            break
        for item in items:
            # /issues conflates issues and pull requests.
            if item.get("pull_request") is not None:
                continue
            number = item.get("number")
            if number in seen:
                continue
            seen.add(number)
            issues.append(node._build_issue(item, fetch_comments=False))
            if len(seen) >= cap:
                break
        if len(items) < node._PER_PAGE:
            break
    else:
        # Every reachable page was fetched and the listing had not ended.
        ceiling_hit = True
    return issues, pages, ceiling_hit, reason


@ChiaFunction(max_retries=0)
def issue_mirror_refresh(repo: str, issue_cap: int, token_path: str,
                         db_path: str) -> dict:
    """Mirror llvm/circt's open and closed issues into loop.db, once per run.

    Returns:
        {"refreshed_utc": str, "issues_mirrored": int, "issue_cap": int, "cap_bound": bool, "state": "all", "comments_mirrored": False, "incomplete_reason": str | None, "ceiling_hit": bool, "pages": int, "issues_added": int, "counters": CounterBlock}.
    Worker:
        head - GithubIssuesNode is documented head-node only.
    Raises:
        nothing it does not catch.
    """
    from chia.github.github_issues_node import GithubIssuesNode

    started_at = time.monotonic()
    token = Path(token_path).read_text().strip()
    node = GithubIssuesNode(repo, token=token, state="all")
    del token
    refreshed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    reason = None
    seen: set = set()
    issues: list = []
    pages = 0
    ceiling_hit = False
    for direction in ("desc", "asc"):
        found, walked, ceiling_hit, reason = mirror_walk(
            node, direction, issue_cap, seen)
        issues.extend(found)
        pages += walked
        # The second direction earns its requests only where the first ran out of reachable pages with the cap unfilled and nothing failed.
        if reason or not ceiling_hit or len(seen) >= issue_cap:
            break

    store = LoopStore(db_path)
    if issues:
        store.transaction([
            ("INSERT OR REPLACE INTO issue_mirror (issue_number, title, body, "
             "labels_json, state, url, mirrored_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
             (issue.number, issue.title, issue.body,
              json.dumps(issue.labels, sort_keys=True), issue.state, issue.url,
              refreshed))
            for issue in issues])
    mirrored = store.query_one("SELECT COUNT(*) AS n FROM issue_mirror")["n"]
    return {"refreshed_utc": refreshed, "issues_mirrored": mirrored,
            "issue_cap": issue_cap, "cap_bound": len(seen) >= issue_cap,
            "state": "all", "comments_mirrored": False,
            "incomplete_reason": reason, "ceiling_hit": ceiling_hit,
            "pages": pages, "issues_added": len(issues),
            "counters": CounterBlock(
                stage="mirror", started=len(seen), completed=len(issues),
                failed=len(seen) - len(issues),
                seconds=time.monotonic() - started_at)}


@ChiaFunction(max_retries=0)
def dedup_and_screen(candidate: CandidateRecord, seed: SeedRecord,
                     verdict: OracleVerdict, clone_path: str, db_path: str,
                     top_n: int, *, rescreened_from: Optional[str] = None) -> dict:
    """Fingerprint one candidate, screen it, and flag contamination both ways.

    Returns:
        {"fingerprint": Fingerprint, "dedup": DedupVerdict, "contaminated_symbol": bool, "contaminated_file": bool, "contamination_lower_bound": str, "fixing_commits": list[str], "post_pin_file_touches": list[str], "counters": CounterBlock}, the counters counting one candidate at stage_6, `dedup_unavailable` being the failed one (3.11).
    Worker:
        head - both commit scans walk 24 months of main in the head's blobless clone.
    Raises:
        ValueError on a `differential` candidate.
    """
    started_at = time.monotonic()
    if candidate.oracle_class == "differential":
        raise ValueError(
            f"candidate {candidate.candidate_id!r} is 'differential' and never "
            "reaches stage 6's dedup (FR-08.10); the caller dispatched it")

    store = LoopStore(db_path)
    signal_row = store.query_one(
        "SELECT signal FROM build_result WHERE probe_id = ?", (candidate.probe_id,))
    reduced_text = _read_text(candidate.reduced_path)
    fingerprint = compute_fingerprint(
        verdict, (signal_row or {}).get("signal"), reduced_text, top_n,
        pass_name=probe_pass_name(store, candidate.probe_id))

    # FR-10.4, the post-pin fix: a fix names one of the frame's own functions,
    # and a file-level touch is not a fix (D-11).
    paths = frame_paths(verdict)
    symbols = frame_symbols(verdict)
    fixing: list = []
    file_touches: list = []
    scan_failure = None
    try:
        post_pin = _after(scan_commits(
            clone_path, commit_date(clone_path, candidate.run_commit), paths),
            candidate.run_commit)
        for commit in post_pin:
            target = fixing if touches_symbol(commit, symbols) else file_touches
            target.append(commit["sha"])
    except (OSError, subprocess.SubprocessError) as error:
        scan_failure = f"post_pin_scan:{type(error).__name__}"

    # FR-15.1 and FR-15.5, contamination.
    exact = bool(getattr(seed, "sdk_exact", False))
    lower_bound = "seed_commit" if exact else "run_commit"
    contaminated_symbol = contaminated_file = False
    try:
        since = (seed.committed_date_utc if exact
                 else commit_date(clone_path, candidate.run_commit))
        window = _after(scan_commits(clone_path, since, paths),
                        None if exact else candidate.run_commit)
        contaminated_file = bool(window)
        contaminated_symbol = any(touches_symbol(c, symbols) for c in window)
    except (OSError, subprocess.SubprocessError) as error:
        scan_failure = scan_failure or f"contamination_scan:{type(error).__name__}"

    evidence = dict.fromkeys(_EVIDENCE_KEYS)
    evidence["post_pin_file_touches"] = file_touches[:POST_PIN_FILE_TOUCH_MAX] or None
    evidence["rescreened_from"] = rescreened_from
    mirrored = store.query_one("SELECT COUNT(*) AS n FROM issue_mirror")["n"]
    hit = mirror_screen(store, mirror_tokens(verdict)) if mirrored else None
    # D-16: a generic MLIR or LLVM assertion identifies no issue on its own.
    if hit is not None and generic_assertion(verdict) and not mirror_corroborates(
            store, hit["issue_number"], circt_frame_tokens(verdict)):
        evidence["generic_text_match"] = hit["issue_number"]
        hit = None
    # D-17: an issue that names the op and not the invariant is another bug.
    if (hit is not None and fingerprint.basis == "verifier"
            and not verifier_corroborates(store, hit["issue_number"], verdict)):
        evidence["op_only_match"] = hit["issue_number"]
        hit = None
    duplicate_of = _duplicate_of(store, candidate, fingerprint)

    if not mirrored:
        verdict_name = "dedup_unavailable"
        evidence["matched_key"] = "issue_mirror_empty"
    elif hit is not None:
        verdict_name = ("known_open_issue" if hit["issue_state"] == "open"
                        else "known_closed_issue")
        evidence.update(hit)
    elif duplicate_of is not None:
        verdict_name = "duplicate_of_candidate"
        evidence["matched_key"] = fingerprint.value
        evidence["duplicate_of_candidate_id"] = duplicate_of
    elif fixing:
        verdict_name, evidence["fixing_commit"] = "fixed_post_pin", fixing[0]
    elif scan_failure is not None:
        verdict_name = "dedup_unavailable"
        evidence["matched_key"] = scan_failure
    else:
        verdict_name = "new"

    dedup = DedupVerdict(probe_id=candidate.probe_id, verdict=verdict_name,
                         evidence=evidence)
    screened = _screened(candidate, fingerprint, dedup, contaminated_symbol,
                         contaminated_file, lower_bound)
    validate_candidate(screened)
    _write_rows(store, screened, fingerprint, dedup)
    return {"fingerprint": fingerprint, "dedup": dedup,
            "contaminated_symbol": contaminated_symbol,
            "contaminated_file": contaminated_file,
            "contamination_lower_bound": lower_bound, "fixing_commits": fixing,
            "post_pin_file_touches": file_touches,
            "counters": CounterBlock(
                stage="stage_6", started=1,
                completed=int(dedup.verdict != "dedup_unavailable"),
                failed=int(dedup.verdict == "dedup_unavailable"),
                seconds=time.monotonic() - started_at)}


def probe_pass_name(store: LoopStore, probe_id: str) -> str:
    """The last pass one probe's own argv names, or "" (D-13's third component)."""
    row = store.query_one("SELECT argv_json FROM probe WHERE probe_id = ?",
                          (probe_id,))
    return _last_pass(json.loads(row["argv_json"])) if row else ""


def _duplicate_of(store: LoopStore, candidate: CandidateRecord,
                  fingerprint: Fingerprint) -> Optional[str]:
    """The earlier candidate this one duplicates, across runs (FR-10.6)."""
    if fingerprint.value is None:
        return None
    row = store.query_one(
        "SELECT candidate_id FROM fingerprint WHERE value = ? "
        "AND fingerprint_stable = 1 AND candidate_id <> ? "
        "ORDER BY candidate_id", (fingerprint.value, candidate.candidate_id))
    return row["candidate_id"] if row else None


def _screened(candidate: CandidateRecord, fingerprint: Fingerprint,
              dedup: DedupVerdict, contaminated_symbol: bool,
              contaminated_file: bool, lower_bound: str) -> CandidateRecord:
    """*candidate* with this stage's eight fields set, for validation and the row."""
    fields = dict(candidate.__dict__)
    fields.update(fingerprint=fingerprint.value,
                  fingerprint_stable=fingerprint.fingerprint_stable,
                  structural_hash=fingerprint.structural_hash,
                  dedup_basis=fingerprint.basis, dedup_verdict=dedup.verdict,
                  dedup_evidence=dedup.evidence,
                  contaminated_symbol=contaminated_symbol,
                  contaminated_file=contaminated_file,
                  contamination_lower_bound=lower_bound)
    return CandidateRecord(**fields)


def _write_rows(store: LoopStore, candidate: CandidateRecord,
                fingerprint: Fingerprint, dedup: DedupVerdict) -> None:
    """The candidate row and its two verdict rows, in one transaction (6.4 rule 4)."""
    store.transaction([
        ("INSERT OR REPLACE INTO candidate (candidate_id, probe_id, "
         "run_manifest_id, arm, run_commit, image_digest, oracle_class, "
         "assertion_text, assertion_site, frame_tuple_json, out_of_scope_root, "
         "contaminated_symbol, contaminated_file, contamination_lower_bound, "
         "triage_class, held_reason, taxonomy_bucket, artefact_dir, created_utc) "
         "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
         (candidate.candidate_id, candidate.probe_id, candidate.run_manifest_id,
          candidate.arm, candidate.run_commit, candidate.image_digest,
          candidate.oracle_class, candidate.assertion_text,
          candidate.assertion_site, json.dumps(candidate.frame_tuple),
          int(candidate.out_of_scope_root), int(candidate.contaminated_symbol),
          int(candidate.contaminated_file), candidate.contamination_lower_bound,
          candidate.triage_class, candidate.held_reason,
          candidate.taxonomy_bucket, candidate.artefact_dir,
          datetime.now(timezone.utc).isoformat(timespec="seconds"))),
        ("INSERT OR REPLACE INTO fingerprint (candidate_id, basis, value, "
         "fingerprint_stable, frame_tuple_json, structural_hash) "
         "VALUES (?, ?, ?, ?, ?, ?)",
         (candidate.candidate_id, fingerprint.basis, fingerprint.value,
          None if fingerprint.fingerprint_stable is None
          else int(fingerprint.fingerprint_stable),
          json.dumps(fingerprint.frame_tuple), fingerprint.structural_hash)),
        ("INSERT OR REPLACE INTO dedup_verdict (candidate_id, verdict, "
         "evidence_json) VALUES (?, ?, ?)",
         (candidate.candidate_id, dedup.verdict,
          json.dumps(dedup.evidence, sort_keys=True))),
    ])


#: 7.4.1's thirteen substitution points, primary template.
PRIMARY_POINTS = ("title", "summary", "observed_behaviour", "reduced_case",
                  "repro_command", "build_identity", "frames", "dedup_evidence",
                  "arm", "contamination", "fingerprint", "why_it_matters",
                  "assisted_by")

#: 7.4.1's twelve, differential template.
DIFFERENTIAL_POINTS = ("title", "summary", "arcilator_behaviour",
                       "verilator_behaviour", "divergence_point", "stimulus",
                       "x_policy", "prior_art", "build_identity", "arm",
                       "why_it_matters", "assisted_by")

_PRIMARY_TEMPLATE = """\
# $title

$summary

## Observed behaviour

$observed_behaviour

## Reduced case

~~~
$reduced_case
~~~

## Reproducing command

~~~
$repro_command
~~~

## Build identity

$build_identity

## Top symbolised frames

~~~
$frames
~~~

## Duplicate screen

$dedup_evidence

## Primary fingerprint

~~~
$fingerprint
~~~

## Post-seed fix screen

$contamination

## Provenance

Arm: $arm

## Why it matters

$why_it_matters

$assisted_by
"""

_DIFFERENTIAL_TEMPLATE = """\
# $title

$summary

## What arcilator did

$arcilator_behaviour

## What Verilator did

$verilator_behaviour

## Where they first differed

$divergence_point

## The one stimulus both were driven with

$stimulus

## X policy

$x_policy

## Prior art

$prior_art

## Build identity

$build_identity

## Provenance

Arm: $arm

## Why it matters

$why_it_matters

$assisted_by
"""


def render_report(template: Literal["primary", "differential"],
                  candidate: CandidateRecord, reduced: Optional[ReducedCase],
                  verdict: Optional[OracleVerdict],
                  differential: Optional[DifferentialVerdict],
                  dedup: Optional[DedupVerdict], manifest: RunManifest,
                  prose: dict) -> str:
    """Render one report.md from the record, substituting every number itself."""
    if template == "primary":
        points, text = PRIMARY_POINTS, _PRIMARY_TEMPLATE
        values = _primary_values(candidate, reduced, verdict, dedup, manifest)
    elif template == "differential":
        points, text = DIFFERENTIAL_POINTS, _DIFFERENTIAL_TEMPLATE
        values = _differential_values(candidate, differential, manifest)
    else:
        raise ValueError(f"template must be 'primary' or 'differential', "
                         f"not {template!r}")
    values.update({key: prose.get(key) for key in
                   ("title", "summary", "why_it_matters")})
    for point in points:
        if not values.get(point):
            raise ReportIncomplete(point)
    return Template(text).substitute(values)


def assisted_by_model(manifest: RunManifest) -> Optional[str]:
    """The model that ACTUALLY ran stage 6, or None when no turn was made."""
    if not manifest.stages_metered.get("stage_6", True):
        return None
    return manifest.model_ids["triage_report"]


def assisted_by(manifest: RunManifest) -> str:
    """FR-11.6's trailer: the model that ACTUALLY ran, or a sentence saying none."""
    model = assisted_by_model(manifest)
    if model is None:
        return ("Assisted-by: none. No model turn was made for this report "
                "(FR-11.8); every figure in it is read off the record.")
    return f"Assisted-by: {model}"


#: What the primary template's `frames` point says for a class that prints no trace.
_NO_FRAMES = {"verifier_error": "No stack trace: the tool printed a verifier "
                                "diagnostic and exited 1."}


def _primary_values(candidate: CandidateRecord, reduced: Optional[ReducedCase],
                    verdict: Optional[OracleVerdict],
                    dedup: Optional[DedupVerdict],
                    manifest: RunManifest) -> dict:
    """The primary template's record-sourced points (7.4.1's first table)."""
    image = dict(manifest.image_spec)
    top_n = len(candidate.frame_tuple) or 5
    frames = strip_prologue(list(verdict.frames)) if verdict else []
    return {
        "observed_behaviour": _observed(verdict),
        "reduced_case": _read_text(reduced.path if reduced else None).strip(),
        "repro_command": (verdict.repro_command if verdict else None),
        "build_identity": "\n".join([
            f"- CIRCT commit: {image.get('circt_sha')}",
            f"- SDK release: {image.get('sdk_tag')}",
            f"- Image digest: {image.get('image_digest')}",
            f"- Build flags: {(verdict.flag_string if verdict else '')}",
            "- Built with -UNDEBUG, so the compiler's internal checks are on.",
            "- Tool version output:",
            "",
            "~~~",
            (verdict.tool_version_output if verdict else ""),
            "~~~"]),
        "frames": "\n".join(
            f"{_normalise_function(frame.function)} {frame.file}:{frame.line}"
            for frame in frames[:top_n]) or _NO_FRAMES.get(
                candidate.oracle_class),
        "dedup_evidence": _dedup_lines(dedup),
        "arm": candidate.arm,
        "contamination": "\n".join([
            f"- Post-seed fix touching a named function: "
            f"{str(candidate.contaminated_symbol).lower()}",
            f"- Post-seed fix touching a named file: "
            f"{str(candidate.contaminated_file).lower()}",
            f"- Lower bound used: {candidate.contamination_lower_bound}",
            "- This screen is incomplete by construction (FR-15.3): a seed's "
            "siblings may be fixed in commits whose subjects do not name them."]),
        "fingerprint": candidate.fingerprint,
        "assisted_by": assisted_by(manifest),
    }


def _differential_values(candidate: CandidateRecord,
                         differential: Optional[DifferentialVerdict],
                         manifest: RunManifest) -> dict:
    """The differential template's record-sourced points (7.4.1's second table)."""
    from circt_bug_loop.probe_task import RESET_PROTOCOL, SAMPLE_POINT

    image = dict(manifest.image_spec)
    if differential is None:
        return {"arcilator_behaviour": None, "verilator_behaviour": None,
                "divergence_point": None, "stimulus": None, "x_policy": None,
                "prior_art": None, "arm": candidate.arm,
                "build_identity": None,
                "assisted_by": assisted_by(manifest)}
    driver = dict(manifest.differential_driver)
    return {
        "arcilator_behaviour": (
            f"- Value: {differential.arcilator_value}\n"
            f"- Trace: {differential.arcilator_trace_path}"),
        "verilator_behaviour": (
            f"- Value: {differential.verilator_value}\n"
            f"- Trace: {differential.verilator_trace_path}\n"
            f"- Verilator version: {differential.verilator_version}"),
        "divergence_point": (
            f"- Signal: {differential.first_divergent_signal}\n"
            f"- Cycle: {differential.first_divergent_cycle}"),
        "stimulus": "\n".join([
            f"- stimulus_id: {differential.stimulus_id}",
            f"- reset_protocol: {RESET_PROTOCOL}",
            f"- sample_point: {SAMPLE_POINT}",
            f"- cycles: {differential.cycles}",
            f"- port_list_sha: {differential.port_list_sha}"]),
        "x_policy": differential.x_policy,
        "prior_art": (f"- Driver: {ARC_TESTS}\n"
                      f"- Source: {driver.get('source')}\n"
                      f"- Commit: {driver.get('commit')}\n"
                      f"- Deviation: {driver.get('deviation')}"),
        "build_identity": "\n".join([
            f"- CIRCT commit: {image.get('circt_sha')}",
            f"- SDK release: {image.get('sdk_tag')}",
            f"- Image digest: {image.get('image_digest')}",
            f"- Build flags: {image.get('flag_string')}",
            "- Built with -UNDEBUG, so the compiler's internal checks are on."]),
        "arm": candidate.arm,
        "assisted_by": assisted_by(manifest),
    }


def _observed(verdict: Optional[OracleVerdict]) -> Optional[str]:
    """FR-07.10's observed-behaviour point, in the failure class's own words."""
    if verdict is None:
        return None
    if verdict.oracle_class == "assertion":
        return "\n".join([
            "CIRCT fired one of its own assertions.",
            "",
            "~~~",
            verdict.assertion_text or "",
            "~~~",
            "",
            f"Site: {verdict.assertion_site}"])
    if verdict.oracle_class == "fatal_error":
        return "\n".join([
            "CIRCT refused the input through its own fatal-error path and "
            "terminated.",
            "",
            "~~~",
            f"LLVM ERROR: {verdict.fatal_message}",
            "~~~"])
    if verdict.oracle_class == "verifier_error":
        return "\n".join([
            "CIRCT's own verifier refused the output of the pass below: the op "
            "it names is not in the input, the compiler created it, and the "
            "input parses and verifies on its own.",
            "",
            "~~~",
            verdict.verifier_message or "",
            "~~~"])
    return ("CIRCT terminated abnormally on the input below, with no diagnostic "
            "of its own. The symbolised frames are given further down.")


def _dedup_lines(dedup: Optional[DedupVerdict]) -> Optional[str]:
    """FR-10.5's evidence, the verdict plus every evidence key it populated."""
    if dedup is None:
        return None
    lines = [f"- Verdict: {dedup.verdict}"]
    for key in _EVIDENCE_KEYS:
        value = dedup.evidence.get(key)
        if value in (None, [], ""):
            continue
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def cap_sentences(text: str, limit: int = TRIAGE_REASON_MAX_SENTENCES) -> tuple:
    """Truncate a classification reason to *limit* sentences, recording that it was."""
    parts = [p for p in _SENTENCE_END.split(text or "") if p.strip()]
    if len(parts) <= limit:
        return (text or "").strip(), False
    return " ".join(part.strip() for part in parts[:limit]), True


#: The three dedup verdicts FR-11.2 turns into `known_issue` whatever the agent wrote.
_KNOWN_ISSUE_VERDICTS = ("known_open_issue", "known_closed_issue", "fixed_post_pin")

#: What a candidate the screen did not call `new` is classified as, by verdict.
_SCREENED_CLASSIFICATION = {
    "known_open_issue": "known_issue",
    "known_closed_issue": "known_issue",
    "fixed_post_pin": "known_issue",
    "duplicate_of_candidate": "duplicate",
    "dedup_unavailable": "untriaged",
}

#: The prose a report written without a turn carries, in place of an agent's.
NO_TURN_PROSE = (
    "NO MODEL TURN WAS MADE FOR THIS CANDIDATE. The duplicate screen matched it "
    "before stage 6's agent turn, so FR-11.2's tool verdict already decides the "
    "classification and gate question 4 refuses the candidate whatever prose a "
    "model would have written; the turn was skipped and this field is the "
    "driver's own sentence. Every number, size, hash and verdict below is read "
    "off the record exactly as it is for a candidate that did get a turn "
    "(FR-11.4).")


#: The prose a report carries when the driver has stage 6's turn off (D-13).
NO_TURN_PROSE_RECLASSIFIED = (
    "NO MODEL TURN WAS MADE FOR THIS CANDIDATE. `--reclassify` re-judged a "
    "stored probe against contract 2.4's `verifier_error` rule and never sends "
    "a turn, so this field is the driver's own sentence. Every number, size, "
    "hash and verdict below is read off the record exactly as it is for a "
    "candidate that did get a turn (FR-11.4, FR-11.8).")


def turn_skipped() -> tuple:
    """FR-11.8's template report for a driver that is running with no turn (D-13)."""
    prose = dict.fromkeys(("title", "summary", "why_it_matters"),
                          NO_TURN_PROSE_RECLASSIFIED)
    return "untriaged", prose, NO_TURN_PROSE_RECLASSIFIED


def screened_out(dedup: Optional[DedupVerdict]) -> Optional[tuple]:
    """What to record for a candidate the screen already decided, or None."""
    if dedup is None or dedup.verdict == "new":
        return None
    classification = _SCREENED_CLASSIFICATION.get(dedup.verdict, "untriaged")
    prose = dict.fromkeys(("title", "summary", "why_it_matters"), NO_TURN_PROSE)
    return classification, prose, NO_TURN_PROSE


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def triage_report(candidate: CandidateRecord, reduced: Optional[ReducedCase],
                  verdict: Optional[OracleVerdict], dedup: Optional[DedupVerdict],
                  manifest: RunManifest, cfg: dict, artefact_dir: str,
                  *, differential: Optional[DifferentialVerdict] = None) -> dict:
    """Classify one candidate advisorily and render the report a maintainer reads.

    Returns:
        {"report": Report, "logs": dict, "failure": str | None, "counters": CounterBlock}.
    Worker:
        {"circt": 1} for the node; the one turn at {"llm": 1.0}.
    Raises:
        nothing.
    """
    started_at = time.monotonic()
    validate_candidate(candidate)
    template = "differential" if candidate.oracle_class == "differential" else "primary"
    prompt = _render_prompt(candidate, reduced, verdict, dedup,
                            differential, manifest, cfg)
    logs = {"prompt": prompt, "reason_truncated": False, "usage": {}}
    failure = None
    prose: dict = {}
    classification = "untriaged"
    reason = ""
    screened = screened_out(dedup)
    why = dedup.verdict if screened is not None else None
    if screened is None and cfg.get("skip_turn"):
        screened, why = turn_skipped(), "turn_disabled"

    if screened is not None:
        # No turn at all.
        classification, prose, reason = screened
        logs.update({"turn_skipped": why, "success": True,
                     "result": "", "stream": "", "stderr": ""})
    else:
        try:
            turn = _run_turn(prompt, cfg, f"src_{candidate.candidate_id}")
            logs.update({key: turn.get(key) for key in
                         ("result", "stream", "stderr", "success")})
            logs["usage"] = turn.get("usage") or {}
            answer = parse_json_footer(
                turn.get("result") or "",
                ("classification", "reason", "title", "summary", "why_it_matters"))
            classification = answer["classification"]
            reason, logs["reason_truncated"] = cap_sentences(answer["reason"])
            prose = {key: answer[key]
                     for key in ("title", "summary", "why_it_matters")}
        except PromptContractError as error:
            failure = f"prompt_contract:{error}"
        except Exception as error:                  # noqa: BLE001 - FR-11.8
            # The turn was settled before it raised: keep that money (D-7).
            logs["usage"] = getattr(error, "turn_usage", None) or logs["usage"]
            failure = f"turn_failed:{type(error).__name__}"

        if dedup is not None and dedup.verdict in _KNOWN_ISSUE_VERDICTS:
            classification = "known_issue"
        elif failure is not None:
            classification = "untriaged"
        elif classification not in ("bug", "invalid_input", "known_issue"):
            failure = failure or f"prompt_contract:bad_classification:{classification}"
            classification = "untriaged"

    _persist_turn(artefact_dir, logs)
    if failure is not None:
        report = Report(candidate_id=candidate.candidate_id, path="",
                        template=template, title="", classification="untriaged",
                        classification_reason=reason, rendered_sha256="",
                        assisted_by=assisted_by_model(manifest) or "none",
                        fields_present=[])
        return {"report": report, "logs": logs, "failure": failure,
                "counters": CounterBlock(
                    stage="stage_6", started=1, completed=0, failed=1,
                    seconds=time.monotonic() - started_at)}

    rendered = render_report(template, candidate, reduced, verdict, differential,
                             dedup, manifest, prose)
    path = _artefact_write(artefact_dir, "report.md", rendered)
    points = PRIMARY_POINTS if template == "primary" else DIFFERENTIAL_POINTS
    report = Report(
        candidate_id=candidate.candidate_id, path=path, template=template,
        title=prose["title"], classification=classification,
        classification_reason=reason,
        rendered_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        assisted_by=assisted_by_model(manifest) or "none",
        fields_present=list(points))
    return {"report": report, "logs": logs, "failure": None,
            "counters": CounterBlock(
                stage="stage_6", started=1, completed=1, failed=0,
                seconds=time.monotonic() - started_at)}


def _render_prompt(candidate: CandidateRecord, reduced: Optional[ReducedCase],
                   verdict: Optional[OracleVerdict],
                   dedup: Optional[DedupVerdict],
                   differential: Optional[DifferentialVerdict],
                   manifest: RunManifest, cfg: dict) -> str:
    """7.4's prompt, one prompt and two fillings, with no `$name` left unbound."""
    text = cfg.get("report_write") or (PROMPTS / "report_write.md").read_text()
    values = {
        "max_sentences": cfg.get("max_sentences", TRIAGE_REASON_MAX_SENTENCES),
        "max_tool_calls": tool_iterations(cfg, "stage_6"),
        "oracle_class": candidate.oracle_class,
        "arcilator_behaviour": NOT_APPLICABLE,
        "verilator_behaviour": NOT_APPLICABLE,
        "stimulus": NOT_APPLICABLE,
    }
    if candidate.oracle_class == "differential":
        values.update(dict.fromkeys(
            ("assertion_text", "assertion_site", "frames", "repro_command",
             "reduced_case", "dedup_verdict", "dedup_evidence"), NOT_APPLICABLE))
        if differential is not None:
            values.update(
                arcilator_behaviour=(f"{differential.arcilator_value} "
                                     f"({differential.arcilator_trace_path})"),
                verilator_behaviour=(f"{differential.verilator_value} "
                                     f"({differential.verilator_trace_path})"),
                stimulus=(f"{differential.stimulus_id}, "
                          f"{differential.cycles} cycles"))
    else:
        frames = strip_prologue(list(verdict.frames)) if verdict else []
        values.update(
            assertion_text=verdict.assertion_text if verdict else "",
            assertion_site=verdict.assertion_site if verdict else "",
            frames="\n".join(
                f"{_normalise_function(f.function)} {f.file}:{f.line}"
                for f in frames[:len(candidate.frame_tuple) or 5]),
            repro_command=verdict.repro_command if verdict else "",
            reduced_case=_read_text(reduced.path if reduced else None),
            dedup_verdict=dedup.verdict if dedup else "",
            dedup_evidence=_dedup_lines(dedup) or "")
    image = dict(manifest.image_spec)
    values["build_identity"] = ", ".join(
        f"{key}={image.get(key)}" for key in ("circt_sha", "sdk_tag",
                                              "image_digest", "flag_string"))
    return Template(text).safe_substitute(**values)


def _run_turn(prompt: str, cfg: dict, name: str) -> dict:
    """One 3.5.1 turn on the campaign backend, with `SourceReadTool` and nothing else."""
    from circt_bug_loop import generate_task

    tool = generate_task.SourceReadTool(
        name=name, clone_path=cfg["clone_path"], run_commit=cfg["run_commit"],
        cap_bytes=int(cfg.get("artefact_inline_cap_bytes", 262144)),
        read_cap_bytes=generate_task.SOURCE_READ_CAP_BYTES,
        task_options=cfg.get("head_options"))
    try:
        return dispatch_turn(TRIAGE_SYSTEM_MESSAGE, prompt, [tool],
                             stage="stage_6",
                             timeout_seconds=int(cfg.get("timeout_seconds", 1200)),
                             model_id=cfg["model_id"],
                             guard=cfg.get("spend_guard"),
                             max_tool_iterations=(cfg.get("max_tool_iterations")
                                                  or {}).get("stage_6"))
    finally:
        stop = getattr(tool, "stop", None)
        if callable(stop):
            stop()


def _persist_turn(artefact_dir: str, logs: dict) -> None:
    """FR-11.7: every triage turn persisted in the shape of FR-04.6's five files."""
    files = {"llm_report_write.prompt.md": logs.get("prompt") or "",
             "llm_report_write.md": logs.get("stream") or logs.get("result") or "",
             "llm_report_write.stderr": logs.get("stderr") or "",
             "llm_report_write.jsonl": logs.get("result") or "",
             "llm_report_write.usage.json": json.dumps(
                 logs.get("usage") or {}, indent=2, sort_keys=True) + "\n"}
    for name, data in files.items():
        logs[name] = _artefact_write(artefact_dir, name, data)


def _read_text(path: Optional[str]) -> str:
    """A reduced case or another recorded file, or "" when it is absent."""
    if not path:
        return ""
    try:
        return Path(path).read_text(errors="backslashreplace")
    except OSError:
        return ""


__all__ = ["TRIAGE_REASON_MAX_SENTENCES", "MIRROR_TOKEN_MIN_CHARS",
           "POST_PIN_FILE_TOUCH_MAX",
           "GOOD_FIRST_ISSUE", "BUILD_PREFIX", "NOT_APPLICABLE", "ARC_TESTS",
           "PRIMARY_POINTS", "DIFFERENTIAL_POINTS",
           "ReportIncomplete",
           "normalise_expr", "normalise_site", "structural_hash",
           "compute_fingerprint", "is_duplicate", "partition", "rates",
           "labelled_fingerprint",
           "MIRROR_PAGE_CEILING", "mirror_tokens", "mirror_screen",
           "mirror_walk", "frame_paths", "frame_symbols",
           "GENERIC_ASSERTIONS", "GENERIC_ASSERTION_ROOTS",
           "generic_assertion", "circt_frame_tokens", "mirror_carries",
           "mirror_corroborates", "verifier_tokens", "verifier_corroborates",
           "commit_date", "scan_commits", "touches_symbol", "cap_sentences",
           "assisted_by", "assisted_by_model",
           "issue_mirror_refresh", "dedup_and_screen", "triage_report",
           "render_report", "screened_out", "NO_TURN_PROSE"]
