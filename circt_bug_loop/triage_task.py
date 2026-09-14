"""B6a, B6b and B7: the issue mirror, the fingerprint, the two screens, the
triage turn and the report render (03-LLD.md 3.7, F-10, F-11, F-15).

Three nodes and one pure renderer. `issue_mirror_refresh` is the only writer of
`issue_mirror` and the only caller that reaches api.github.com; `dedup_and_screen`
makes no request at all and reads the mirror as a table, which is FR-10.3's
network-trace criterion held by construction. `triage_report` is the one model
turn of the apparatus half and every number in what it renders is substituted
from the record (FR-11.4).

Head placement for B6a and B6b (K5, 3.2): both walk the head's blobless clone
and the head-pinned `loop.db`, and neither runs a CIRCT binary, so neither takes
a `circt` slot. B7 keeps `{"circt": 1}` for the node and `{"llm": 1.0}` for the
turn itself, which `llm.llm_turn` declares.

Two deviations from 03-LLD.md, each recorded in
`design/reviews/implementation-errata-log.md` rather than absorbed:

  * `generate_task` is imported INSIDE `_run_turn` and not at module scope, for
    the one name B7 still needs from the supply half: `SourceReadTool`, which
    3.5 puts in that module. 3.5.1's backend, turn and parser moved to `llm.py`
    at the join, which is neither half, so those three are imported at module
    scope below and the parser is one function again (architect decision 3).
  * `dedup_and_screen`'s signature carries no `BuildResult`, so 3.7.1's
    `signal_name` is read from `build_result.signal` by `probe_id` through the
    store that the node already opens for the mirror screen.
"""
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
from typing import Literal, Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import (CounterBlock, RunManifest,
                                            SeedRecord)
from circt_bug_loop.llm import (PromptContractError,  # noqa: F401
                                dispatch_turn, parse_json_footer)
from circt_bug_loop.probe_task import _normalise_function, strip_prologue
from circt_bug_loop.store import (CandidateRecord, DedupVerdict,
                                  DifferentialVerdict, Fingerprint, LoopStore,
                                  OracleVerdict, ReducedCase, Report,
                                  validate_candidate, write_artefact)

#: 03-LLD.md 9.4's two implementation constants of this module.
TRIAGE_REASON_MAX_SENTENCES = 4
MIRROR_TOKEN_MIN_CHARS = 8

#: The label CIRCT's own policy forbids an AI tool to act on
#: (`circt:docs/AIToolPolicy.md:24`), read by FR-13.9's refusal out of
#: `DedupVerdict.evidence["issue_labels"]`.
GOOD_FIRST_ISSUE = "good first issue"

#: 3.7.1's build prefix. A frame path under it is made relative to it; any other
#: absolute path keeps its last two components, which is what lets FR-10.6's
#: cross-run query match two images built in different directories.
BUILD_PREFIX = "/workspace/circt/"

#: 7.4's stage-6 prompt, beside this module (1.1). `cfg["report_write"]`
#: overrides it, which is how the driver passes the copy it already loaded.
PROMPTS = Path(__file__).resolve().parent / "prompts"

#: B7's system message. 3.7.4 fixes the turn, the tool and the timeout and does
#: not name a system message; CHIA's own chain has `prompts/system.md` and stage
#: 6 has no such file in 1.1's list, so it is one line here.
TRIAGE_SYSTEM_MESSAGE = (
    "You write CIRCT bug reports from tool output. You state observed behaviour "
    "only, you never restate a number, and you end with one fenced json block.")

#: The literal 7.4 binds the six primary variables to for a `differential`
#: candidate, so that `safe_substitute` leaves no unbound `$name` behind (W23).
NOT_APPLICABLE = "not applicable to a differential candidate"

#: 7.4.1's prior-art point: the driver a differential report names (FR-08.7).
ARC_TESTS = "circt/arc-tests"

#: The top-level source directories a CIRCT frame path is made relative to, for
#: 3.7.2's pathspecs. A path under none of them falls back to a basename glob.
_SRC_ROOTS = ("lib/", "include/", "tools/", "test/", "frontends/",
              "integration_test/")

#: 6.5's write, as the plain function and not as B10b's node: a plain call to a
#: `ChiaFunction` wrapper routes through `chia.trace.profiler`, which starts a
#: local Ray, and the node's own return is `{"path", "counters"}` while what a
#: report needs is the path. The artefact root is bind-mounted at the identical
#: path on every worker (FR-17.9), so the write lands in the same place.
_artefact_write = write_artefact

_SENTENCE_END = re.compile(r"(?<=[.!?])(?:\s+|$)")
_SSA = re.compile(r"%[A-Za-z0-9_$.\-]+")
_SYMBOL = re.compile(r"@[A-Za-z0-9_$.\-]+")
_LOC = re.compile(r"loc\([^()]*(?:\([^()]*\)[^()]*)*\)")
_COMMIT = re.compile(r"^__C__ (?P<sha>[0-9a-f]{7,40}) (?P<date>\S+)$")
_HUNK = re.compile(r"^@@ [^@]*@@ ?(?P<context>.*)$")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: The eight declared keys of `DedupVerdict.evidence` (2.9). The set is closed
#: and `store.validate_candidate` compares it exactly, so every verdict builds
#: the whole dict and leaves the keys it cannot fill as None.
_EVIDENCE_KEYS = ("matched_key", "matched_token", "issue_number", "issue_url",
                  "issue_state", "issue_labels", "fixing_commit",
                  "duplicate_of_candidate_id")


class ReportIncomplete(Exception):
    """A substitution point the chosen template declares is absent (FR-11.3)."""


# ---------------------------------------------------------------------------
# 3.7.1 The primary fingerprint
# ---------------------------------------------------------------------------


def normalise_expr(text: str) -> str:
    """Collapse whitespace runs in an assertion expression and strip the ends.

    Nothing else changes, and in particular the `&& "message"` tail is KEPT:
    3.7.1 makes it the most discriminating part of the expression, so two
    different asserts on one condition stay two different bugs.

    Returns:
        str, the normalised expression.
    Worker:
        pure.
    Raises:
        nothing.
    """
    return " ".join((text or "").split())


def normalise_site(site: str) -> str:
    """Drop an assertion site's build prefix, keeping the line number verbatim.

    A path under `BUILD_PREFIX` is made relative to it; any other absolute path
    keeps only its last two components; a relative path is untouched. The line
    number is kept exactly as G-43 says, because it is what separates two
    asserts in one function.

    Returns:
        str, "<path>:<line>", or the input unchanged when it carries no line.
    Worker:
        pure.
    Raises:
        nothing.
    """
    path, sep, line = (site or "").rpartition(":")
    if not sep or not line.isdigit():
        path, line, sep = site or "", "", ""
    if path.startswith(BUILD_PREFIX):
        path = path[len(BUILD_PREFIX):]
    elif path.startswith("/"):
        path = "/".join([p for p in path.split("/") if p][-2:])
    return f"{path}:{line}" if sep else path


def structural_hash(text: str) -> str:
    """Hash a reduced case with every name that reduction can rewrite removed.

    SSA value names, `@symbol` names, `loc(...)` suffixes and whitespace runs
    are normalised before hashing. The symbol clause is load-bearing:
    `circt-reduce` renames modules during reduction, `hw.module @top` becoming
    `hw.module private @Foo`, so without it one reduced case hashed differently
    depending on how far the reducer got (NIT 9).

    It is EVIDENCE and never a merge key (FR-10.1, FR-10.2): no path in this
    module compares two candidates by it.

    Returns:
        str, the hex SHA-256 digest.
    Worker:
        pure.
    Raises:
        nothing.
    """
    normalised = _LOC.sub("loc(_)", text or "")
    normalised = _SSA.sub("%_", normalised)
    normalised = _SYMBOL.sub("@_", normalised)
    return hashlib.sha256(" ".join(normalised.split()).encode("utf-8")).hexdigest()


def compute_fingerprint(verdict: OracleVerdict, signal: Optional[str],
                        reduced_text: str, top_n: int) -> Fingerprint:
    """Compute G-43's primary fingerprint and its three evidence fields.

    The strip precedes every use of a frame (K3). For an `assertion` the value
    is the normalised expression, a newline and the normalised site; for a
    `crash` or a `fatal_error` it is the signal name, a newline and
    `OracleVerdict.fingerprint_frame`, which B3 already computed as the first
    stripped frame in a CIRCT object with a resolved line, its function name and
    its file basename and no line number. Where no stripped frame qualifies the
    basis falls back to the top-*top_n* tuple of normalised names; where fewer
    than *top_n* frames resolve at all the basis is `insufficient` and the value
    is None (FR-10.8). The top-N tuple is recorded as evidence in every case.

    `fingerprint_stable` is None here and stays None until the gate's question-1
    re-run sets it (3.9); an unstable fingerprint is reported and never merged.

    Returns:
        Fingerprint, with probe_id, basis, value, frame_tuple, structural_hash
        and fingerprint_stable=None.
    Worker:
        pure; called inside B6b, which is a head node.
    Raises:
        nothing.
    """
    stripped = strip_prologue(list(verdict.frames))
    names = [_normalise_function(frame.function) for frame in stripped]
    resolved = sum(1 for frame in stripped if frame.function)
    tuple_evidence = names[:top_n]

    if verdict.oracle_class == "assertion" and verdict.assertion_text:
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
    """Report whether two candidates are duplicates under FR-10.2, and nothing else.

    Exact string equality of the primary fingerprint, and no similarity measure,
    no threshold and no other key. The structural hash and the frame tuple take
    no part. Identity makes it reflexive even where the basis is `insufficient`,
    whose value is None and equals nothing, so the relation is reflexive,
    symmetric and transitive over any set.

    Returns:
        bool.
    Worker:
        pure.
    Raises:
        nothing.
    """
    if left.probe_id == right.probe_id:
        return True
    return left.value is not None and left.value == right.value


def partition(fingerprints: list) -> list:
    """Partition candidates into duplicate classes, independent of arrival order.

    A `Fingerprint` whose value is None, and one whose `fingerprint_stable` is
    anything but True, is its own singleton: an unstable fingerprint is REPORTED
    and never merged (3.7.1), and a candidate whose gate re-run has not happened
    carries None and is likewise not merged. Nothing therefore merges before the
    gate has run, which is why B6b's own candidate-to-candidate query asks the
    store for a fingerprint already found stable (FR-10.6 makes it cross-run).

    Returns:
        list[frozenset[str]] of probe ids, sorted by each block's least member,
        so two shuffles of one input give the same list.
    Worker:
        pure.
    Raises:
        nothing.
    """
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
    """Measure FR-10.2's collision and false-merge rates over labelled pairs.

    A pair is `{"label": "duplicate"|"distinct", "a": Fingerprint,
    "b": Fingerprint}`. The collision rate is distinct-labelled pairs whose
    fingerprints are equal over all distinct-labelled pairs; the false-merge
    rate is duplicate-labelled pairs whose fingerprints differ over all
    duplicate-labelled pairs. Neither is thresholded: 04-Test-Plan.md 10's
    acceptance is that both are measured and reported (A-05).

    Returns:
        {"collision_rate": float, "false_merge_rate": float,
         "collisions": int, "distinct_pairs": int,
         "false_merges": int, "duplicate_pairs": int}
    Worker:
        pure.
    Raises:
        nothing.
    """
    distinct = [p for p in pairs if p["label"] == "distinct"]
    duplicate = [p for p in pairs if p["label"] == "duplicate"]
    collisions = sum(1 for p in distinct if is_duplicate(p["a"], p["b"]))
    false_merges = sum(1 for p in duplicate if not is_duplicate(p["a"], p["b"]))
    return {"collision_rate": collisions / len(distinct) if distinct else 0.0,
            "false_merge_rate": false_merges / len(duplicate) if duplicate else 0.0,
            "collisions": collisions, "distinct_pairs": len(distinct),
            "false_merges": false_merges, "duplicate_pairs": len(duplicate)}


# ---------------------------------------------------------------------------
# 3.7.3 The issue-mirror screen
# ---------------------------------------------------------------------------


def mirror_tokens(verdict: OracleVerdict) -> list:
    """The screen's tokens for one candidate, per oracle class, and nothing else.

    `assertion` yields two, the expression and the `file:line` exactly as the
    verdict records them; `crash` yields one, the fingerprint frame's function
    name without its file; `fatal_error` yields two, that function name and the
    `LLVM ERROR:` message verbatim; `differential` yields none, and such a
    candidate never reaches this stage (FR-08.10). A token shorter than
    `MIRROR_TOKEN_MIN_CHARS` is dropped, because `fold` or `parse` alone would
    match hundreds of issues and the screen would answer `known_issue` for every
    candidate.

    Returns:
        list[str], in the order the table gives them, duplicates removed.
    Worker:
        pure.
    Raises:
        nothing.
    """
    function = (verdict.fingerprint_frame or "").rsplit(" ", 1)[0]
    if verdict.oracle_class == "assertion":
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
    """Query the local mirror once per token and pick the issue that decides.

    The predicate is `instr(title || ' ' || body, :token) > 0`, case-sensitive,
    with ANY token matching ANY issue producing a hit. It is over-inclusive by
    design (3.7.3): there is no scoring, no threshold and no similarity measure
    anywhere in it, a false match costs a report rather than a wrong filing, and
    the human at the gate sees the matched token and the issue number.

    Selection, where more than one issue matched: an issue carrying
    `GOOD_FIRST_ISSUE` first, then an `open` issue over a `closed` one because
    an open issue is the one a maintainer would be told about twice, then token
    order, then issue number. The label comes first because FR-13.9 refuses a
    filing that matched ANY such issue and `DedupVerdict.evidence`'s eight keys
    can carry the labels of one issue only.

    No GitHub request is made here, which is FR-10.3's network-trace criterion.

    Returns:
        None on no match, else {"matched_token", "issue_number", "issue_url",
        "issue_state", "issue_labels"}.
    Worker:
        {"num_cpus": 0.1} per query, the store's own; B6b is a head node.
    Raises:
        sqlite3.Error from the query. It makes no request, so it raises no
        GitHub error.
    """
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


# ---------------------------------------------------------------------------
# 3.7.2 The two commit scans
# ---------------------------------------------------------------------------


def frame_paths(verdict: OracleVerdict) -> list:
    """The candidate's source paths, as git pathspecs against the clone.

    Frames in a CIRCT object with a file, plus the assertion site's file. A path
    under one of `_SRC_ROOTS` is made relative to that root, which is the repo
    path; anything else falls back to a `:(glob)**/<basename>` pathspec, so a
    header that the build copied elsewhere still selects its file.

    Returns:
        list[str], sorted and deduplicated; empty when no frame carries a file.
    Worker:
        pure.
    Raises:
        nothing.
    """
    files = [frame.file for frame in verdict.frames
             if frame.in_circt_object and frame.file]
    if verdict.assertion_site:
        # The RAW site, not the normalised one: normalisation keeps two path
        # components, which is what a fingerprint wants and what a pathspec
        # cannot use.
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
    """The candidate's function names, for 3.7.2's symbol-level match.

    Each stripped frame's normalised function name and its last `::` component,
    because git writes the hunk header's context in either spelling. The
    assertion site's own function is among them by construction: the trace
    passes through it.

    Returns:
        set[str], empty for a trace with no resolved CIRCT frame.
    Worker:
        pure.
    Raises:
        nothing.
    """
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
    """Read one commit's committer date from the clone, as strict ISO 8601.

    4.12 bounds both scans by a date, and `CandidateRecord.run_commit` and the
    seed's own commit are SHAs, so this is the one conversion between them.

    Returns:
        str, `%cI`.
    Worker:
        head; the blobless clone at `--clone` is the only tree holding 24 months
        of `main` (K5).
    Raises:
        subprocess.CalledProcessError when the commit is not in the clone, and
        subprocess.TimeoutExpired past *timeout*.
    """
    out = subprocess.run(["git", "-C", clone_path, "log", "-1", "--format=%cI",
                          commit], capture_output=True, text=True, check=True,
                         timeout=timeout)
    return out.stdout.strip()


def scan_commits(clone_path: str, since: str, paths: list, *,
                 timeout: int = 900) -> list:
    """Walk `main` from *since* to the clone head over *paths*, one command.

    4.12's line, which is the command the M4 measurement used:

        git -C <clone> log --first-parent -p --unified=0 --no-renames \\
            --format=__C__ %H %cI --since <lower bound> -- <the paths>

    Symbol level reads the identifier git puts in the `@@ ... @@ <context>` hunk
    header, which is the precise rule; the crude `\\b(\\w+)\\s*\\(` rule over the
    `+`/`-` lines is NOT used, and the difference is measured: 77.0% against
    79.1% flagged over the corpus (M4).

    Returns:
        list[dict], one per commit in walk order, each
        {"sha": str, "date": str, "contexts": list[str]}.
    Worker:
        head, for the same reason as `commit_date`.
    Raises:
        subprocess.CalledProcessError from git, and subprocess.TimeoutExpired
        past *timeout*. An empty *paths* returns [] without running git, because
        `git log -- ` with no pathspec would walk the whole history.
    """
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
    """Drop the bound commit itself, which `--since <its own date>` includes.

    Both windows are open at the bottom: FR-10.4 scans commits made AFTER the
    run's commit and FR-15.1 fixes made after the seed's, and `git log --since`
    takes a date and keeps a commit stamped exactly at it.
    """
    return [c for c in commits if bound is None or c["sha"] != bound]


def touches_symbol(commit: dict, symbols: set) -> bool:
    """Report whether a commit's hunk-header contexts name one of *symbols*.

    This is FR-15.1's symbol level, and the identifier is read from the context
    git itself writes after the `@@ ... @@` marker, never from the changed lines.
    An empty symbol set matches nothing, which keeps a trace with no resolved
    CIRCT frame out of the contamination count rather than in all of it.

    Returns:
        bool.
    Worker:
        pure; the git call already happened in `scan_commits`.
    Raises:
        nothing.
    """
    if not symbols:
        return False
    for context in commit["contexts"]:
        if symbols & set(_WORD.findall(context)):
            return True
    return False


# ---------------------------------------------------------------------------
# B6a, the issue mirror
# ---------------------------------------------------------------------------


#: GitHub's own pagination ceiling on the issues-listing endpoint (C-22).
#: MEASURED 2026-09-14 by `T-U-triage-35` with a token: of 100 requests the
#: first 99 answered 200 and the hundredth answered **422**, so pages 1 to 99
#: are reachable and one direction sees at most 9,900 numbered items, issues and
#: pull requests together. Two directions therefore cover 19,800, which is more
#: than `llvm/circt` has issued.
MIRROR_PAGE_CEILING = 100

#: The status a refused page answers with, which `GithubClient._error_message`
#: puts at the head of the message it raises `GithubRequestError` with
#: (`chia:chia/github/github_client.py:180`, `192`). Any other 4xx is a real
#: failure and is re-raised.
_CEILING_STATUS = "422"


def mirror_walk(node, direction: str, cap: int, seen: set) -> tuple:
    """Page llvm/circt's issue listing in ONE direction, dropping pull requests.

    `GithubIssuesNode.recent` cannot be used for this: `_list` hard-codes
    `direction: "desc"` (`chia:chia/github/github_issues_node.py:152`) and takes
    no parameter, and CHIA is not modified (FR-12.1). Its two halves that matter
    are reused instead, `_request` for the HTTP round trip and `_build_issue`
    for the record, so a test that replays a recorded response set through
    `GithubClient._request` exercises this walk exactly as it exercises CHIA's.

    Returns:
        (issues, pages, ceiling_hit, reason): the `GithubIssue`s this direction
        added, how many pages were fetched, whether the walk stopped at GitHub's
        pagination ceiling rather than at the end of the listing or at the cap,
        and the class name of the error that stopped it, or None. *seen* is
        mutated: it holds every issue number taken so far, in either direction,
        which is what makes the union deduplicated by number.
    Worker:
        the caller's, which is B6a's, which is the head.
    Raises:
        nothing. Every `GithubError` stops this direction and is returned as
        `reason`, so a rate limit half way through leaves the pages already
        fetched in the caller's hands rather than discarding them, which is
        what the one-direction walk did.
    """
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
            # Only the ceiling's own 422 is the ceiling: any other 4xx, and a
            # rate limit, is a failure the run is told about (FR-10.7).
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
            # /issues conflates issues and pull requests; the mirror is issues,
            # which is `_list`'s own rule and the reason 600 rows cost 35 pages.
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
        # Every reachable page was fetched and the listing had not ended: the
        # next page is the one GitHub refuses.
        ceiling_hit = True
    return issues, pages, ceiling_hit, reason


@ChiaFunction(max_retries=0)
def issue_mirror_refresh(repo: str, issue_cap: int, token_path: str,
                         db_path: str) -> dict:
    """Mirror llvm/circt's open and closed issues into loop.db, once per run.

    **The walk is two-directional** (3.7.3, architect decision 1, C-22). It
    pages `direction=desc` from the newest until the listing ends, the cap is
    reached, or GitHub's pagination ceiling refuses a page with a 422; on the
    ceiling it then pages `direction=asc` from the oldest and unions the two
    deduplicated by issue number. One direction sees at most 9,900 numbered
    items and `llvm/circt`'s newest number on 2026-09-14 was 11,113, so the
    union is the whole history. Before this, one direction at the campaign's cap
    raised on the 422 and wrote **zero** rows: the mirror did not truncate, it
    produced nothing (`T-U-triage-35`, measured).

    Five fields per issue and no text beyond the body: number, title, body,
    labels, state, plus the issue's own URL and the refresh time.
    `fetch_comments` is False by requirement and not by preference: the default
    costs one extra paginated request per issue that has comments (FR-10.9), and
    mirroring no comment at all is what makes FR-20.4 true by construction,
    because no maintainer's words are in the database to reach a prompt.

    Once per run is the driver's rule and not this node's: the signature carries
    no run id and no refresh flag, so B12 calls it once unless `--refresh-mirror`
    and writes `issue_mirror_meta` from what comes back.

    Returns:
        {"refreshed_utc": str, "issues_mirrored": int, "issue_cap": int,
         "cap_bound": bool, "state": "all", "comments_mirrored": False,
         "incomplete_reason": str | None, "ceiling_hit": bool, "pages": int,
         "issues_added": int, "counters": CounterBlock}. The first six are
        `RunManifest.issue_mirror`'s closed key set (2.7); the rest cannot go
        there, that set being compared exactly by `validate` and the contract
        being frozen at 2.0, so the driver copies the six and records the others
        beside them. `incomplete_reason` is FR-10.7's detection point.
    Worker:
        head - GithubIssuesNode is documented head-node only, and the token
        lives on the head and nowhere else (4.3 of 02-HLD.md, section 11 here).
    Raises:
        nothing it does not catch. A GithubRateLimitError marks the mirror
        incomplete with the count reached and screening proceeds against a
        partial mirror, flagged in the return (FR-10.7's detection point); the
        ceiling's own 422 is not an error and is reported as `ceiling_hit`.
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
        # The second direction earns its requests only where the first ran out
        # of reachable pages with the cap unfilled and nothing failed.
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


# ---------------------------------------------------------------------------
# B6b, the fingerprint, the screens and the two scans
# ---------------------------------------------------------------------------


@ChiaFunction(max_retries=0)
def dedup_and_screen(candidate: CandidateRecord, seed: SeedRecord,
                     verdict: OracleVerdict, clone_path: str, db_path: str,
                     top_n: int) -> dict:
    """Fingerprint one candidate, screen it, and flag contamination both ways.

    The run's commit is NOT a parameter: it is `candidate.run_commit`, which is
    the only value that is right in both modes (K14). `RunManifest.run_commit`
    is a list, one entry per calibrated seed, so index 0 is an arbitrary sampled
    seed's commit and is this candidate's only by accident.

    Verdict precedence, which 3.7 fixes nowhere and which this node fixes here:
    an empty mirror is `dedup_unavailable` for every candidate (FR-10.7); then a
    mirror hit, open before closed, because its evidence carries FR-13.9's
    label refusal and nothing downstream can recover it; then a
    candidate-to-candidate duplicate; then a post-pin fix; then `new`.

    A candidate-to-candidate duplicate merges only against a fingerprint the
    gate's re-run already found stable, which is what keeps 3.7.1's "an unstable
    fingerprint is reported, never merged" true of the merge path as well as of
    the results (FR-10.6 makes that query cross-run).

    Returns:
        {"fingerprint": Fingerprint, "dedup": DedupVerdict,
         "contaminated_symbol": bool, "contaminated_file": bool,
         "contamination_lower_bound": str, "fixing_commits": list[str],
         "counters": CounterBlock}, the counters counting one candidate at
        stage_6, `dedup_unavailable` being the failed one (3.11).
    Worker:
        head - both commit scans walk 24 months of main in the head's blobless
        clone, and the issue mirror is a table in loop.db, which is head-pinned
        (K5, K7).
    Raises:
        ValueError on a `differential` candidate, which FR-08.10 keeps out of
        this stage entirely and which reaching it is a caller defect; and
        ContractError from `validate_candidate` on the screened record. An
        undecidable dedup is `dedup_unavailable`, which fails gate question 4
        rather than passing it (FR-10.7), and a git or GitHub failure is caught.
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
        verdict, (signal_row or {}).get("signal"), reduced_text, top_n)

    # FR-10.4, the post-pin fix: file level, lower bound the candidate's own
    # run commit, upper bound the clone head. Over-inclusive by design, because
    # a match makes the candidate fail the gate's novelty question.
    paths = frame_paths(verdict)
    fixing: list = []
    scan_failure = None
    try:
        post_pin = _after(scan_commits(
            clone_path, commit_date(clone_path, candidate.run_commit), paths),
            candidate.run_commit)
        fixing = [commit["sha"] for commit in post_pin]
    except (OSError, subprocess.SubprocessError) as error:
        scan_failure = f"post_pin_scan:{type(error).__name__}"

    # FR-15.1 and FR-15.5, contamination: symbol level, lower bound the seed's
    # own commit date, or the run's commit for the 16 non-exact seeds.
    exact = bool(getattr(seed, "sdk_exact", False))
    lower_bound = "seed_commit" if exact else "run_commit"
    symbols = frame_symbols(verdict)
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
    mirrored = store.query_one("SELECT COUNT(*) AS n FROM issue_mirror")["n"]
    hit = mirror_screen(store, mirror_tokens(verdict)) if mirrored else None
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
            "counters": CounterBlock(
                stage="stage_6", started=1,
                completed=int(dedup.verdict != "dedup_unavailable"),
                failed=int(dedup.verdict == "dedup_unavailable"),
                seconds=time.monotonic() - started_at)}


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
    """The candidate row and its two verdict rows, in one transaction (6.4 rule 4).

    `INSERT OR REPLACE` rather than `INSERT`, because 3.2 gives this node the
    idempotency key `(candidate_id, mirror_refreshed_utc, run_commit)`: a second
    screen of one candidate rewrites its rows rather than raising.
    """
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


# ---------------------------------------------------------------------------
# B7, the triage turn and the report render
# ---------------------------------------------------------------------------

#: 7.4.1's thirteen substitution points, primary template.
PRIMARY_POINTS = ("title", "summary", "observed_behaviour", "reduced_case",
                  "repro_command", "build_identity", "frames", "dedup_evidence",
                  "arm", "contamination", "fingerprint", "why_it_matters",
                  "assisted_by")

#: 7.4.1's twelve, differential template. Enforced SEPARATELY and not as one
#: superset: there is no `observed_behaviour` point, because the two behaviour
#: points replace it, and none of `frames`, `reduced_case`, `repro_command`,
#: `dedup_evidence`, `contamination` or `fingerprint`, because a `differential`
#: candidate has none of them (FR-08.10, FR-09.8, FR-13.14).
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
    """Render one report.md from the record, substituting every number itself.

    No number the agent produced reaches the report (FR-11.4): every count,
    size, time, hash, SHA and verdict below is read off the record, and the
    agent's contribution is `title`, `summary` and `why_it_matters` only.

    The two point lists are enforced SEPARATELY: a point the chosen template
    declares and the record cannot fill raises, and the other template's absent
    points are accepted. A `differential` candidate is the one call that passes
    *differential* non-None and *verdict*, *reduced* and *dedup* all None (W23).

    Returns:
        str, the rendered markdown; the caller writes it and hashes it.
    Worker:
        pure; it is called inside B7 and runs no process.
    Raises:
        ReportIncomplete(point) when any substitution point of 7.4.1 that the
        chosen template declares is absent from the record (FR-11.3);
        ValueError on a template name that is neither.
    """
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
    """The model that ACTUALLY ran stage 6, or None when no turn was made.

    Read off `RunManifest.stages_metered["stage_6"]`, which is the run's own
    statement about whether stage 6 was a model turn, and not off `model_ids`,
    which is what the run would have used had it made one.
    """
    if not manifest.stages_metered.get("stage_6", True):
        return None
    return manifest.model_ids["triage_report"]


def assisted_by(manifest: RunManifest) -> str:
    """FR-11.6's trailer: the model that ACTUALLY ran, or a sentence saying none.

    `RunManifest.stages_metered["stage_6"]` is the run's own statement about
    whether stage 6 was a model turn. Under `--generator recorded` it is False
    and no turn was made anywhere, and the rendered report's first line says
    exactly that - while its last line said `Assisted-by: vertex:gemini-3.8-flash`,
    because this was read off `model_ids` in three places with nothing asking
    whether the model had run (W-19b #7). One artefact cannot state both.

    Returns:
        str, the trailer line.
    Worker:
        pure; it reads two manifest fields.
    Raises:
        nothing.
    """
    model = assisted_by_model(manifest)
    if model is None:
        return ("Assisted-by: none. No model turn was made for this report "
                "(FR-11.8); every figure in it is read off the record.")
    return f"Assisted-by: {model}"


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
            for frame in frames[:top_n]) or None,
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
    """The differential template's record-sourced points (7.4.1's second table).

    `stimulus` is 7.4.1's `ProbeSpec.differential` five keys, and `render_report`
    takes no `ProbeSpec`: three come off the `DifferentialVerdict` and two off
    9.4's campaign constants, which is the same data by FR-08.3's rule that one
    stimulus definition serves the whole campaign.
    """
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
    """FR-07.10's observed-behaviour point, in the failure class's own words.

    A `fatal_error` is a refusal CIRCT chose deliberately, so the wording here
    says neither "crash" nor the other word, exactly as 7.4 forbids the agent to
    (W13): calling a deliberate refusal a crash is how a maintainer's tolerance
    gets spent.
    """
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
    """Truncate a classification reason to *limit* sentences, recording that it was.

    Counted by splitting on `.`, `!` and `?` followed by whitespace or the end
    of the string. Truncated rather than rejected (FR-11.1): a reason that is
    too long is still the agent's opinion, and the gate reads none of it.

    Returns:
        (str, bool): the capped text, and whether anything was dropped.
    Worker:
        pure.
    Raises:
        nothing.
    """
    parts = [p for p in _SENTENCE_END.split(text or "") if p.strip()]
    if len(parts) <= limit:
        return (text or "").strip(), False
    return " ".join(part.strip() for part in parts[:limit]), True


@ChiaFunction(resources={"circt": 1}, max_retries=0)
def triage_report(candidate: CandidateRecord, reduced: Optional[ReducedCase],
                  verdict: Optional[OracleVerdict], dedup: Optional[DedupVerdict],
                  manifest: RunManifest, cfg: dict, artefact_dir: str,
                  *, differential: Optional[DifferentialVerdict] = None) -> dict:
    """Classify one candidate advisorily and render the report a maintainer reads.

    Two rules make the output safe to report. The TOOL VERDICT WINS: a candidate
    whose `DedupVerdict` is `known_open_issue`, `known_closed_issue` or
    `fixed_post_pin` is classified `known_issue` whatever the agent wrote, and
    the agent's only freedom is the reason text (FR-11.2). And NO NUMBER THE
    AGENT PRODUCED REACHES THE REPORT: `render_report` substitutes every count,
    size, time, hash, SHA and verdict from the record (FR-11.4).

    The turn is 3.5.1's turn: `llm.build_llm` with stage 6's timeout and
    `cfg["model_id"]`, dispatched through `llm.dispatch_turn` with exactly one
    tool, `SourceReadTool`, named for the candidate and stopped in a `finally`
    as A3 does.

    Returns:
        {"report": Report, "logs": dict, "failure": str | None, "counters":
        CounterBlock}. `logs` carries the turn's five FR-04.6 files by path, its
        usage, and `reason_truncated`; the counters count one candidate at
        stage_6, a failed turn being the failed one (3.11).
    Worker:
        {"circt": 1} for the node; the one turn at {"llm": 1.0}.
    Raises:
        nothing. A failed turn yields classification "untriaged" and an empty
        report; the candidate still receives four mechanical gate answers and is
        held with held_reason=no_report if it passes (FR-11.8).
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
        prose = {key: answer[key] for key in ("title", "summary", "why_it_matters")}
    except PromptContractError as error:
        failure = f"prompt_contract:{error}"
    except Exception as error:                      # noqa: BLE001 - FR-11.8
        failure = f"turn_failed:{type(error).__name__}"

    if dedup is not None and dedup.verdict in (
            "known_open_issue", "known_closed_issue", "fixed_post_pin"):
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
    """7.4's prompt, one prompt and two fillings, with no `$name` left unbound.

    For a `differential` candidate the six primary variables are bound to the
    literal `NOT_APPLICABLE` and the three differential variables come off the
    `DifferentialVerdict`, because `safe_substitute` leaves an unbound `$name`
    in place and an unbound `$frames` in a prompt is a defect rather than a
    blank (W23).
    """
    text = cfg.get("report_write") or (PROMPTS / "report_write.md").read_text()
    values = {
        "max_sentences": cfg.get("max_sentences", TRIAGE_REASON_MAX_SENTENCES),
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
    """One 3.5.1 turn on the campaign backend, with `SourceReadTool` and nothing else.

    The turn is `llm.py`'s, which is neither half, so it is imported at module
    scope. `generate_task` is still imported HERE and not there, for the one
    name 3.5 leaves in the supply half: `SourceReadTool`.

    B7 runs on a `circt` worker, which carries neither the key nor the
    interlock. It builds no backend: `llm_turn` constructs the client on the
    `llm` worker from that worker's own environment, and what crosses is the
    system message, the prompt, the tool's endpoint, the stage, the timeout and
    the model id (K2, W7).

    The tool is constructed as 3.5's constructor declares it,
    `(name, clone_path, run_commit, cap_bytes, task_options)`, and by keyword.
    The two positional arguments this call site carried bound `name` to the
    clone path and `clone_path` to the commit and then raised `TypeError` for
    the missing `run_commit`, so no triage turn could ever have run (architect
    decision 4; T-U-triage-36 constructs the real tool).

    The turn goes through `dispatch_turn` and not through `llm_turn` itself: a
    plain call to the decorated wrapper routes through `chia.trace.profiler`,
    which starts a local Ray where none is running, which is what A3's own turn
    avoids the same way (3.5.1, 04-Test-Plan.md 0.4).
    """
    from circt_bug_loop import generate_task

    tool = generate_task.SourceReadTool(
        name=name, clone_path=cfg["clone_path"], run_commit=cfg["run_commit"],
        cap_bytes=int(cfg.get("artefact_inline_cap_bytes", 262144)),
        task_options=cfg.get("head_options"))
    try:
        return dispatch_turn(TRIAGE_SYSTEM_MESSAGE, prompt, [tool],
                             stage="stage_6",
                             timeout_seconds=int(cfg.get("timeout_seconds", 1200)),
                             model_id=cfg["model_id"],
                             guard=cfg.get("spend_guard"))
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
           "GOOD_FIRST_ISSUE", "BUILD_PREFIX", "NOT_APPLICABLE", "ARC_TESTS",
           "PRIMARY_POINTS", "DIFFERENTIAL_POINTS",
           "ReportIncomplete",
           "normalise_expr", "normalise_site", "structural_hash",
           "compute_fingerprint", "is_duplicate", "partition", "rates",
           "MIRROR_PAGE_CEILING", "mirror_tokens", "mirror_screen",
           "mirror_walk", "frame_paths", "frame_symbols",
           "commit_date", "scan_commits", "touches_symbol", "cap_sentences",
           "assisted_by", "assisted_by_model",
           "issue_mirror_refresh", "dedup_and_screen", "triage_report",
           "render_report"]
