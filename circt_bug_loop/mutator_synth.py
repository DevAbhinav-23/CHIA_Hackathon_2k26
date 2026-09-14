"""A7: the offline, once, pre-registration mutator synthesis and freeze (8.3).

Not imported by the campaign, and it refuses to run at all once a
pre-registration commit exists (8.1 rule 3), so a running campaign cannot
synthesise a mutator even by accident. Its input is the issue mirror B6a built
in `loop.db` and nothing else: no GitHub request is made here, for the same
reason 3.7.3's screen makes none (FR-10.3, NFR-04).

Two deviations from 03-LLD.md, both recorded in
`design/reviews/implementation-errata-log.md`:

  * The mirror is read through a read-only `sqlite3` connection and not through
    `store.LoopStore`. 1.3's layout rule (2) forbids a supply-half module to
    import a `store.py` name, and A7 only ever reads one table.
  * 8.3 step 2's column is `number`; the table's column is `issue_number`
    (6.2), and the query here uses the column that exists.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import time
from pathlib import Path
from string import Template
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop import llm, mutators
from circt_bug_loop.contract.schema import CounterBlock

#: 8.3's prompt, beside this module (1.1). `cfg["mutator_synth"]` overrides it.
PROMPTS = Path(__file__).resolve().parent / "prompts"

#: A7's system message; 8.3 fixes the prompt, the turn and the timeout and does
#: not name one, and this turn is given no tool at all.
SYNTH_SYSTEM_MESSAGE = (
    "You design small mechanical input mutators for a compiler fuzzing "
    "baseline. You never write a diagnosis, and you end with one fenced json "
    "block.")

#: The five checks of step 4, each of which DROPS an entry rather than repairing
#: it, plus the duplicate-id check that needs the whole set to decide.
_REQUIRED = ("id", "language", "kind", "mutates_argv", "pattern", "replacement")


class MutatorSynthError(Exception):
    """The synthesis refused: it is registered, the mirror is empty, or the set exists."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _git(repo_root: str, *args: str) -> str:
    """Run one git argument vector in *repo_root* and return its stdout."""
    done = subprocess.run(["git", "-C", repo_root, *args], capture_output=True,
                          text=True, errors="backslashreplace", timeout=300,
                          check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def registration_commit(repo_root: str) -> str:
    """Return the commit that landed `budget.yaml`, or "" when there is none.

    That commit IS the pre-registration (FR-14.3), so its existence is the one
    fact step 1 needs. Two pathspecs and not one path: the loop lives at
    `circt_bug_loop/` in the team repository and at `examples/circt_bug_loop/`
    in a CHIA checkout (1.4), and a module here may not walk above its own
    directory to work out which, so the question asked of git is "a file called
    budget.yaml, at the root or at any depth" (erratum: 8.3 step 1 gives one
    bare path, which is right in only one of the two trees).
    """
    return _git(repo_root, "log", "-1", "--format=%H", "--",
                "budget.yaml", "*/budget.yaml")


def read_mirror(db_path: str) -> list:
    """Return every closed `label:bug` issue of the mirror, ordered by number.

    Step 2's input and the only one: the mirror is a table B6a filled, and this
    function makes no request of its own.

    Returns:
        list[dict], each carrying issue_number, title and body.
    Worker:
        head; `loop.db` is head-pinned (6.1) and this connection is read-only.
    Raises:
        sqlite3.Error when the database cannot be read.
    """
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT issue_number, title, body, labels_json FROM issue_mirror "
            "WHERE state = 'closed' AND instr(labels_json, '\"bug\"') > 0 "
            "ORDER BY issue_number").fetchall()
    finally:
        connection.close()
    issues = []
    for row in rows:
        try:
            labels = json.loads(row["labels_json"])
        except ValueError:
            labels = []
        if "bug" in labels:
            issues.append({"issue_number": row["issue_number"],
                           "title": row["title"], "body": row["body"]})
    return issues


def render_issues(issues: list) -> str:
    """Render 8.3's `$issues`: one `== #<number> <title>` block per issue."""
    return "\n\n".join(f"== #{issue['issue_number']} {issue['title']}\n"
                       f"{issue['body']}" for issue in issues)


def issue_digest(issues: list) -> str:
    """SHA-256 over the sorted issue numbers, newline joined (8.1, 8.3 step 5)."""
    numbers = sorted(int(issue["issue_number"]) for issue in issues)
    return hashlib.sha256("\n".join(str(n) for n in numbers).encode("utf-8")).hexdigest()


def check_entry(entry: dict, seen: set) -> Optional[str]:
    """Return the name of the step-4 check *entry* fails, or None if it passes.

    Six checks, each of which DROPS the entry: a missing field, an id that is
    not 8.1's dotted form or that repeats, a language or a kind outside its
    set, a `mutates_argv` that disagrees with `kind == "argv"` (FR-05.5), a
    pattern that will not compile, and a replacement that is neither a literal,
    a back-reference template, nor one of the seven named operations. Nothing
    is repaired and nothing failing is kept.
    """
    if not isinstance(entry, dict) or any(key not in entry for key in _REQUIRED):
        return "missing_field"
    identifier = entry.get("id")
    if not isinstance(identifier, str) or not mutators.ID.match(identifier):
        return "bad_id"
    if identifier in seen:
        return "duplicate_id"
    if entry.get("language") not in mutators.LANGUAGES:
        return "bad_language"
    if entry.get("kind") not in mutators.KINDS:
        return "bad_kind"
    if bool(entry.get("mutates_argv")) != (entry.get("kind") == "argv"):
        return "bad_mutates_argv"
    try:
        re.compile(entry.get("pattern", ""))
    except re.error:
        return "bad_pattern"
    replacement = entry.get("replacement")
    if not isinstance(replacement, str) or not replacement:
        return "bad_replacement"
    if entry.get("kind") == "line" and replacement not in mutators.SEQUENCE_OPERATIONS:
        return "bad_replacement"
    if entry.get("kind") == "text" and replacement in mutators.SEQUENCE_OPERATIONS:
        return "bad_replacement"
    return None


def parse_mutators(answer: dict) -> tuple:
    """Apply step 4's checks to the turn's mutators array.

    Returns:
        (kept, dropped), where kept is the surviving entries in the model's own
        order with 8.1's eight fields and nothing else, and dropped maps a
        failing check's name to the list of ids it dropped.
    Worker:
        pure.
    Raises:
        nothing.
    """
    kept: list = []
    dropped: dict = {}
    seen: set = set()
    for entry in answer.get("mutators") or []:
        failure = check_entry(entry if isinstance(entry, dict) else {}, seen)
        if failure is not None:
            identifier = (entry or {}).get("id") if isinstance(entry, dict) else None
            dropped.setdefault(failure, []).append(identifier)
            continue
        seen.add(entry["id"])
        kept.append({
            "id": entry["id"], "language": entry["language"],
            "kind": entry["kind"], "mutates_argv": bool(entry["mutates_argv"]),
            "description": str(entry.get("description", "")),
            "pattern": entry["pattern"], "replacement": entry["replacement"],
            "derived_from": [int(number) for number in entry.get("derived_from", [])
                             if isinstance(number, int)]})
    return kept, dropped


def _canonical(document: dict) -> str:
    """Canonical JSON by 2.3's rule: sorted keys, two-space indent, one newline."""
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False,
                      separators=(",", ": ")) + "\n"


@ChiaFunction(max_retries=0)
def synthesise_mutators(db_path: str, repo_root: str, set_version: str,
                        languages: tuple, target_count: int, cfg: dict,
                        timeout_seconds: int = 3600) -> dict:
    """Synthesise the frozen mutator set once, offline, before registration.

    Five steps, in this order and no other: refuse if the campaign is already
    registered, so that no model turn is spent discovering it; read the closed
    `label:bug` issues from the mirror; run ONE turn over 8.3's prompt with no
    tool at all; parse the footer and DROP every entry failing one of step 4's
    checks; and freeze the set write-once, with the three provenance fields
    filled from the run and never from the model.

    Returns:
        {"path": str, "set_sha256": str, "mutators_written": int,
         "dropped": dict, "issues_used": int, "counters": CounterBlock}, where
        dropped maps a failing check's name to the list of ids it dropped.
    Worker:
        head; the mirror is a table in the head-pinned `loop.db` (6.1) and the
        turn is dispatched from here at {"llm": 1.0}.
    Raises:
        MutatorSynthError("already_registered", sha) when step 1 finds a
            budget.yaml commit; MutatorSynthError("empty_mirror") when step 2
            returns no row; MutatorSynthError("set_exists", path) when step 5
            finds the file; PromptContractError from 7.1's parser, which
            freezes nothing.
    """
    started = time.monotonic()
    registered = registration_commit(repo_root)
    if registered:
        raise MutatorSynthError("already_registered", registered)

    issues = read_mirror(db_path)
    if not issues:
        raise MutatorSynthError(
            "empty_mirror",
            f"{db_path} holds no closed label:bug issue; a set synthesised "
            "from nothing would freeze successfully and measure nothing")

    target = Path(cfg.get("set_dir") or mutators.DIRECTORY) / f"set_{set_version}.json"
    if target.exists():
        raise MutatorSynthError("set_exists", str(target))

    text = (cfg.get("mutator_synth")
            or (PROMPTS / "mutator_synth.md").read_text(encoding="utf-8"))
    prompt = Template(text).safe_substitute(
        issue_count=len(issues), issue_digest=issue_digest(issues),
        issues=render_issues(issues),
        languages=", ".join(languages), target_count=int(target_count))
    backend = llm.build_llm(SYNTH_SYSTEM_MESSAGE, int(timeout_seconds),
                            cfg["model_id"])
    turn = llm.dispatch_turn(backend, prompt, [])
    answer = llm.parse_json_footer(turn.get("result") or "", ("mutators",))
    kept, dropped = parse_mutators(answer)

    document = {
        "format_version": 1,
        "set_version": set_version,
        "synthesised_utc": cfg.get("synthesised_utc") or time.strftime(
            "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "synthesis_input": {
            "repo": "llvm/circt",
            "query": "closed issues labelled bug, the full history",
            "issues_used": len(issues),
            "mirror_refreshed_utc": cfg.get("mirror_refreshed_utc", ""),
            "issue_numbers_sha256": issue_digest(issues)},
        "synthesis_model": cfg["model_id"],
        "mutators": kept}
    rendered = _canonical(document)
    # WRITE-ONCE, checked again at the write itself: "x" fails on an existing
    # file, so a second call cannot change the digest a manifest already names
    # even if it raced past the check above.
    try:
        with open(target, "x", encoding="utf-8") as handle:
            handle.write(rendered)
    except FileExistsError:
        raise MutatorSynthError("set_exists", str(target)) from None
    return {"path": str(target),
            "set_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            "mutators_written": len(kept), "dropped": dropped,
            "issues_used": len(issues), "usage": turn.get("usage") or {},
            "counters": CounterBlock(stage="synthesis", started=len(issues),
                                     completed=len(kept),
                                     failed=sum(len(ids) for ids in dropped.values()),
                                     seconds=time.monotonic() - started)}


__all__ = ["PROMPTS", "SYNTH_SYSTEM_MESSAGE", "MutatorSynthError",
           "check_entry", "issue_digest", "parse_mutators", "read_mirror",
           "registration_commit", "render_issues", "synthesise_mutators"]
