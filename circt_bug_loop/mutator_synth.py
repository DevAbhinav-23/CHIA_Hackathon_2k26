"""A7: the offline, once, pre-registration mutator synthesis and freeze (8.3)."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from pathlib import Path
from string import Template
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop import budget, llm, mutators
from circt_bug_loop.contract.schema import CounterBlock, canonical_json

#: 8.3's prompt, beside this module (1.1). `cfg["mutator_synth"]` overrides it.
PROMPTS = Path(__file__).resolve().parent / "prompts"

#: A7's system message; 8.3 fixes the prompt.
SYNTH_SYSTEM_MESSAGE = (
    "You design small mechanical input mutators for a compiler fuzzing "
    "baseline. You never write a diagnosis, and you end with one fenced json "
    "block.")

#: The five checks of step 4.
_REQUIRED = ("id", "language", "kind", "mutates_argv", "pattern", "replacement")


class MutatorSynthError(Exception):
    """The synthesis refused: it is registered, the mirror is empty, or the set exists."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def registration_commit(repo_root: str) -> str:
    """Return the commit the newest `registration/*` tag names, or ""."""
    return budget.registration(repo_root)[1]


def prompt_path(set_version: str) -> Path:
    """The prompt file that synthesises *set_version*: versioned, or 8.3's own."""
    versioned = PROMPTS / f"mutator_synth_{set_version}.md"
    return versioned if versioned.exists() else PROMPTS / "mutator_synth.md"


def read_mirror(db_path: str) -> list:
    """Return every closed `label:bug` issue of the mirror, ordered by number."""
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
    """SHA-256 over the sorted issue numbers, newline joined (8.1)."""
    numbers = sorted(int(issue["issue_number"]) for issue in issues)
    return hashlib.sha256("\n".join(str(n) for n in numbers).encode("utf-8")).hexdigest()


def check_entry(entry: dict, seen: set) -> Optional[str]:
    """Return the name of the step-4 check *entry* fails, or None if it passes."""
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
    """Apply step 4's checks to the turn's mutators array."""
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


#: 2.3's canonical JSON, from the module that defines it.
_canonical = canonical_json


@ChiaFunction(max_retries=0)
def synthesise_mutators(db_path: str, repo_root: str, set_version: str,
                        languages: tuple, target_count: int, cfg: dict,
                        timeout_seconds: int = 3600) -> dict:
    """Synthesise the frozen mutator set once, offline, before registration.

    Returns:
        {"path": str, "set_sha256": str, "mutators_written": int, "dropped": dict, "issues_used": int, "counters": CounterBlock}, where dropped maps a failing check's name to the list of ids it dropped.
    Worker:
        head; the mirror is a table in the head-pinned `loop.db` (6.1) and the turn is dispatched from here at {"llm": 1.0}.
    Raises:
        MutatorSynthError("already_registered", sha) when step 1 finds a `registration/*` tag.
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

    text = cfg.get("mutator_synth") or prompt_path(set_version).read_text(
        encoding="utf-8")
    prompt = Template(text).safe_substitute(
        issue_count=len(issues), issue_digest=issue_digest(issues),
        issues=render_issues(issues),
        languages=", ".join(languages), target_count=int(target_count))
    turn = llm.dispatch_turn(SYNTH_SYSTEM_MESSAGE, prompt, [], stage="synthesis",
                             timeout_seconds=int(timeout_seconds),
                             model_id=cfg["model_id"])
    answer = llm.parse_json_footer(turn.get("result") or "", ("mutators",))
    kept, dropped = parse_mutators(answer)

    document = {
        "format_version": 1,
        "set_version": set_version,
        # 8.1's field, and the one this step exists to set (W-12).
        "frozen": True,
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
    # WRITE-ONCE, checked again at the write itself.
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
           "check_entry", "issue_digest", "parse_mutators", "prompt_path",
           "read_mirror", "registration_commit", "render_issues",
           "synthesise_mutators"]
