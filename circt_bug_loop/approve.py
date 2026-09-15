"""B9c, `bugloop-approve`: the one interface a human touches (`03-LLD.md` §13.2)."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from circt_bug_loop.store import LoopStore, latest, utc_now
from circt_bug_loop.contract.schema import canonical_json
from circt_bug_loop.triage_task import GOOD_FIRST_ISSUE

#: §9.4, FR-13.17, fixed by ADR-D-02.
PREFILL_URL_CHAR_LIMIT = 6000

#: FR-20.1: the method is posted to CIRCT's forum before the first filing; the run records it.
FORUM_FIELDS = ("forum_post_url", "forum_post_date")

#: `llvm/circt` has no `.github/ISSUE_TEMPLATE/` directory.
REPO = "llvm/circt"
ISSUE_NEW_URL = f"https://github.com/{REPO}/issues/new"
ISSUE_PATH_PREFIX = f"/{REPO}/issues/"

#: The two decisions that can reach a human. Anything else is `nothing`.
FILEABLE = ("report", "report_plus_patch")

#: What `refuse` writes into `candidate.held_reason`.
REFUSED_PREFIX = "human_refused:"
AWAITING = "awaiting_approval"

_HAND_FILING = """\
The pre-filled URL would be {length} characters, over the {limit}-character limit
of FR-13.17, so GitHub cannot be handed this body in a link. File it by hand:

  1. open {new}
  2. title:  {title}
  3. body:   paste the whole of {path}
  4. record the URL here:  python -m circt_bug_loop.approve filed {candidate} <url>

The body already carries the primary fingerprint, which is what the poll of
FR-13.16 matches on, and the `Assisted-by:` trailer FR-20.3 requires.
"""

_LICENCE_PROMPT = """\
FR-20.5: a patch offered with a report must be licensable under Apache-2.0 with
LLVM exceptions, and the confirmation is recorded against this report and never
defaulted. The patch is on screen above. Confirm? [yes/no] """


#: Now, UTC, ISO-8601.
_utc = utc_now


def load_budget_caps(path: str) -> dict:
    """FR-13.8's two caps, read from the pre-registered `budget.yaml`."""
    import yaml

    budget = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return {key: int(budget[key]) for key in
            ("filings_per_day", "filings_total", "filing_poll_window_seconds")}


def load_case(store: LoopStore, candidate_id: str) -> dict:
    """Every row one candidate's approval view needs, in one dict."""
    candidate = store.query_one("SELECT * FROM candidate WHERE candidate_id = ?",
                                (candidate_id,))
    if candidate is None:
        raise LookupError(f"no candidate row for {candidate_id!r}")
    probe_id = candidate["probe_id"]
    return {
        "candidate": candidate,
        "report": store.query_one("SELECT * FROM report WHERE candidate_id = ?",
                                  (candidate_id,)),
        # D-11: the LATEST gate and dedup rows, which `--rescreen` appends to.
        "gate": latest(store, "gate_decision", candidate_id),
        "repair": store.query_one("SELECT * FROM repair WHERE candidate_id = ?",
                                  (candidate_id,)),
        "reduced": store.query_one("SELECT * FROM reduced_case WHERE probe_id = ?",
                                   (probe_id,)),
        "dedup": latest(store, "dedup_verdict", candidate_id),
        "fingerprint": store.query_one(
            "SELECT * FROM fingerprint WHERE candidate_id = ?", (candidate_id,)),
        "filing": store.query_one("SELECT * FROM filing WHERE candidate_id = ?",
                                  (candidate_id,)),
    }


def run_manifest(store: LoopStore, run_id: str) -> dict:
    """The run's stored RunManifest, as a dict."""
    row = store.query_one("SELECT manifest_json FROM run WHERE run_manifest_id = ?",
                          (run_id,))
    return json.loads((row or {}).get("manifest_json") or "{}")


def forum_posted(manifest: dict) -> bool:
    """True when both forum fields hold a real value (FR-20.1)."""
    return all(isinstance(manifest.get(k), str) and manifest[k]
               and not manifest[k].startswith("none") for k in FORUM_FIELDS)


def record_forum_post(store: LoopStore, run_id: str, url: str, date: str) -> None:
    """Write the forum post's URL and date into the run's manifest (FR-20.1)."""
    manifest = run_manifest(store, run_id)
    manifest.update(forum_post_url=url, forum_post_date=date)
    store.update("run", {"run_manifest_id": run_id},
                 {"manifest_json": canonical_json(manifest)})


def refusal(store: LoopStore, case: dict, caps: dict) -> Optional[str]:
    """The first refusal that applies, or None, checked BEFORE anything is shown."""
    candidate, filing = case["candidate"], case["filing"]
    if filing is not None:
        return (f"{candidate['candidate_id']} was approved by "
                f"{filing['approver']} at {filing['approved_at_utc']}: approval "
                f"is per report and does not repeat (FR-13.13)")

    # Both caps are PER CAMPAIGN RUN (W11).
    run_id = candidate["run_manifest_id"]
    today = _utc()[:10]
    lifetime = store.query_one("SELECT COUNT(*) AS n FROM filing")["n"]
    filed_today = store.query_one(
        "SELECT COUNT(*) AS n FROM filing "
        "JOIN candidate ON candidate.candidate_id = filing.candidate_id "
        "WHERE candidate.run_manifest_id = ? AND filing.approved_at_utc LIKE ?",
        (run_id, f"{today}%"))["n"]
    if filed_today >= caps["filings_per_day"]:
        return (f"the per-UTC-day filing cap is {caps['filings_per_day']} and "
                f"{filed_today} have been approved on {today} in this run: held "
                f"(FR-13.8); {lifetime} across every run, for information")
    total = store.query_one(
        "SELECT COUNT(*) AS n FROM filing "
        "JOIN candidate ON candidate.candidate_id = filing.candidate_id "
        "WHERE candidate.run_manifest_id = ?", (run_id,))["n"]
    if total >= caps["filings_total"]:
        return (f"the total filing cap is {caps['filings_total']} and {total} "
                f"have been approved in this run: held (FR-13.8); {lifetime} "
                f"across every run, for information")

    evidence = json.loads((case["dedup"] or {}).get("evidence_json") or "{}")
    if GOOD_FIRST_ISSUE in (evidence.get("issue_labels") or []):
        return (f"the dedup stage matched issue #{evidence.get('issue_number')}, "
                f"which carries the {GOOD_FIRST_ISSUE!r} label: CIRCT leaves "
                f"those to human newcomers and this loop files nothing against "
                f"one, as an issue, a comment or a fix (FR-13.9, FR-20.2)")

    held = candidate["held_reason"]
    if held and held != AWAITING:
        return (f"{candidate['candidate_id']} is held: {held} - it is not "
                f"presented (FR-11.8)")

    decision = (case["gate"] or {}).get("decision")
    if decision not in FILEABLE:
        return (f"the gate decided {decision!r}: only {' and '.join(FILEABLE)} "
                f"reach a human (FR-13.10)")
    if not forum_posted(run_manifest(store, run_id)):
        return ("no forum post is recorded for this run: FR-20.1 posts the method "
                "to CIRCT's forum before the first filing; post it, then pass "
                "--forum-post-url and --forum-post-date to record it")
    return None


def render_view(case: dict) -> str:
    """FR-13.12's one view: the report, the four answers, the diff, the case."""
    candidate, gate = case["candidate"], case["gate"] or {}
    parts = [f"=== candidate {candidate['candidate_id']} "
             f"({candidate['arm']}, {candidate['oracle_class']}) ===", ""]

    report = case["report"]
    parts += ["--- report ---",
              Path(report["path"]).read_text(encoding="utf-8") if report
              else "(no report was rendered; FR-11.8 holds this candidate)", ""]

    parts.append("--- the four gate answers ---")
    if gate:
        for key, value in json.loads(gate["answers_json"]).items():
            parts.append(f"  {key}: {value}")
        stopped = gate["stopped_at_question"]
        parts += [f"  stopped at question: {stopped if stopped else 'none, all four passed'}",
                  f"  decision: {gate['decision']}",
                  f"  taxonomy bucket: {gate['taxonomy_bucket']}"]
    else:
        parts.append("  (no gate decision recorded)")
    parts.append("")

    repair = case["repair"]
    diff = repair and repair["diff_path"]
    parts += ["--- repair diff ---",
              Path(diff).read_text(encoding="utf-8") if diff
              else "(no patch: " + (f"repair status {repair['status']}"
                                    if repair else "no repair attempt") + ")", ""]

    reduced = case["reduced"]
    parts += ["--- reduced case ---",
              Path(reduced["path"]).read_text(encoding="utf-8") if reduced
              else "(no reduced case)", ""]
    return "\n".join(parts)


def prefill(title: str, body: str) -> tuple:
    """ADR-D-02(c)'s pre-filled issue URL, measured before it is offered."""
    url = f"{ISSUE_NEW_URL}?" + urllib.parse.urlencode({"title": title, "body": body})
    if len(url) > PREFILL_URL_CHAR_LIMIT:
        return None, len(url), (f"prefill_url_{len(url)}_chars_over_"
                                f"{PREFILL_URL_CHAR_LIMIT}")
    return url, len(url), None


def issue_number(url: str) -> Optional[int]:
    """The issue number of a `llvm/circt` issue URL, or None if it is not one."""
    parsed = urllib.parse.urlsplit(url)
    tail = parsed.path[len(ISSUE_PATH_PREFIX):] if parsed.path.startswith(
        ISSUE_PATH_PREFIX) else ""
    if (parsed.scheme == "https" and parsed.netloc == "github.com"
            and tail.isdigit()):
        return int(tail)
    return None


def cmd_list(store: LoopStore, args, out) -> int:
    """Every candidate the gate cleared and no `filing` row yet covers."""
    rows = store.query(
        "SELECT c.candidate_id, c.arm, c.oracle_class, c.held_reason, "
        "       g.decision, f.value AS fingerprint "
        "FROM gate_decision g JOIN candidate c USING (candidate_id) "
        "LEFT JOIN fingerprint f USING (candidate_id) "
        "LEFT JOIN filing fl USING (candidate_id) "
        # D-11: one row per candidate, the latest, whatever `--rescreen` appended.
        "WHERE g.rowid = (SELECT MAX(rowid) FROM gate_decision "
        "                 WHERE candidate_id = c.candidate_id) "
        "AND g.decision IN (?, ?) AND fl.candidate_id IS NULL "
        "ORDER BY c.candidate_id", FILEABLE)
    for row in rows:
        finger = (row["fingerprint"] or "").splitlines()
        print(f"{row['candidate_id']}  {row['arm']:<9} {row['oracle_class']:<10} "
              f"{row['decision']:<18} {(finger[0] if finger else '')[:40]:<40} "
              f"{row['held_reason'] or ''}", file=out)
    print(f"{len(rows)} pending", file=out)
    return 0


def cmd_show(store: LoopStore, args, out) -> int:
    """FR-13.12's view, read-only, with nothing written."""
    print(render_view(load_case(store, args.candidate_id)), file=out)
    return 0


def cmd_approve(store: LoopStore, args, out) -> int:
    """Run the refusals, show the view, take the typed approval, write one row."""
    case = load_case(store, args.candidate_id)
    caps = load_budget_caps(args.budget)
    if args.forum_post_url and args.forum_post_date:
        record_forum_post(store, case["candidate"]["run_manifest_id"],
                          args.forum_post_url, args.forum_post_date)
    refused = refusal(store, case, caps)
    if refused:
        print(f"refused: {refused}", file=out)
        return 2

    store.update("candidate", {"candidate_id": args.candidate_id},
                 {"held_reason": AWAITING})
    print(render_view(case), file=out)

    decision = case["gate"]["decision"]
    if input(f"Approve filing {args.candidate_id} as {decision}? "
             f"Type yes to confirm: ").strip().lower() != "yes":
        print("not approved; nothing written", file=out)
        return 1

    licence, licence_at = None, None
    if decision == "report_plus_patch":
        licence = input(_LICENCE_PROMPT).strip().lower() == "yes"
        licence_at = _utc()
        if not licence:
            # FR-20.5: never defaulted.
            decision = "report"
            print("licence declined: the decision is downgraded to 'report' and "
                  "no patch is offered (FR-20.5)", file=out)

    store.insert("filing", {
        "candidate_id": args.candidate_id, "approver": args.by,
        "approved_at_utc": _utc(), "decision": decision,
        "licence_confirmed": None if licence is None else int(licence),
        "licence_confirmed_at_utc": licence_at, "url_source": None,
        "issue_number": None, "issue_url": None, "prefill_url_length": None,
        "prefill_fallback_reason": None, "confirmed": 0,
        "confirmed_at_utc": None, "confirmation_url": None})
    store.update("candidate", {"candidate_id": args.candidate_id},
                 {"held_reason": None})
    print(f"approved by {args.by} as {decision}", file=out)
    return cmd_url(store, args, out)


def cmd_refuse(store: LoopStore, args, out) -> int:
    """Record a human rejection; no filing is possible afterwards."""
    load_case(store, args.candidate_id)
    store.update("candidate", {"candidate_id": args.candidate_id},
                 {"held_reason": f"{REFUSED_PREFIX} {args.reason}"})
    print(f"{args.candidate_id} refused: {args.reason}", file=out)
    return 0


def cmd_url(store: LoopStore, args, out) -> int:
    """Print the pre-filled issue URL, or FR-13.17's hand-filing instruction."""
    case = load_case(store, args.candidate_id)
    report = case["report"]
    if report is None:
        print("no rendered report: nothing to file", file=out)
        return 2
    body = Path(report["path"]).read_text(encoding="utf-8")
    url, length, reason = prefill(report["title"], body)
    if case["filing"] is not None:
        store.update("filing", {"candidate_id": args.candidate_id},
                     {"prefill_url_length": length, "prefill_fallback_reason": reason})
    print(url if url else _HAND_FILING.format(
        length=length, limit=PREFILL_URL_CHAR_LIMIT, new=ISSUE_NEW_URL,
        title=report["title"], path=report["path"],
        candidate=args.candidate_id), file=out)
    return 0


def cmd_filed(store: LoopStore, args, out) -> int:
    """Record the URL FR-13.16's poll did not find, against the same report id."""
    number = issue_number(args.url)
    if number is None:
        print(f"refused: {args.url!r} is not an https://github.com/{REPO}/issues/"
              f"<number> URL", file=out)
        return 2
    if store.query_one("SELECT 1 FROM filing WHERE candidate_id = ?",
                       (args.candidate_id,)) is None:
        print(f"refused: {args.candidate_id} has no approval, so there is no "
              f"filing to complete (FR-13.7)", file=out)
        return 2
    store.update("filing", {"candidate_id": args.candidate_id},
                 {"issue_url": args.url, "issue_number": number,
                  "url_source": "pasted"})
    print(f"recorded issue #{number} against {args.candidate_id}", file=out)
    return 0


def cmd_poll(store: LoopStore, args, out) -> int:
    """FR-13.16: complete a `FilingRecord` from the read-only issues node."""
    pending = store.query(
        "SELECT f.candidate_id, fp.value AS fingerprint FROM filing f "
        "JOIN fingerprint fp USING (candidate_id) WHERE f.issue_url IS NULL")
    if not pending:
        print("no filing awaits a URL", file=out)
        return 0

    from chia.github.github_issues_node import GithubIssuesNode

    token = Path(args.github_token_file).expanduser().read_text().strip()
    node = GithubIssuesNode(REPO, token=token, state="open")
    del token
    issues = node.recent(n=args.poll_issues, fetch_comments=False)

    matched = 0
    for row in pending:
        finger = row["fingerprint"]
        hit = next((issue for issue in issues
                    if finger and finger in (issue.body or "")), None)
        if hit is None:
            print(f"{row['candidate_id']}: no issue carries its fingerprint; "
                  f"paste the URL with `filed` (FR-13.16)", file=out)
            continue
        store.update("filing", {"candidate_id": row["candidate_id"]},
                     {"issue_url": hit.url, "issue_number": hit.number,
                      "url_source": "poll"})
        matched += 1
        print(f"{row['candidate_id']}: matched issue #{hit.number}", file=out)
    print(f"{matched} of {len(pending)} completed by poll", file=out)
    return 0


_COMMANDS = {"list": cmd_list, "show": cmd_show, "approve": cmd_approve,
             "refuse": cmd_refuse, "url": cmd_url, "filed": cmd_filed,
             "poll": cmd_poll}


def build_parser() -> argparse.ArgumentParser:
    """§13.2's command line, as the parser that implements it."""
    parser = argparse.ArgumentParser(
        prog="bugloop-approve",
        description="approve one CIRCT bug-loop report for filing, and record "
                    "the issue URL (FR-13.18)")
    parser.add_argument("--db", required=True, help="loop.db, absolute")
    parser.add_argument("--budget", default="circt_bug_loop/budget.yaml",
                        help="the pre-registered budget.yaml, for FR-13.8's caps")
    parser.add_argument("--github-token-file",
                        default="~/.config/circt_bug_loop/github_token",
                        help="§11.1's 0600 file; read by `poll` and nothing else")
    parser.add_argument("--poll-issues", type=int, default=100,
                        help="how many open issues `poll` lists")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="every candidate the gate cleared")
    for name in ("show", "approve", "url"):
        subparsers.add_parser(name).add_argument("candidate_id")
    subparsers.choices["approve"].add_argument(
        "--by", required=True, help="the approving human's name (FR-13.7)")
    subparsers.choices["approve"].add_argument(
        "--forum-post-url", help="FR-20.1: the method's forum post, recorded on the run")
    subparsers.choices["approve"].add_argument(
        "--forum-post-date", help="FR-20.1: the post's date, YYYY-MM-DD")
    refuse = subparsers.add_parser("refuse")
    refuse.add_argument("candidate_id")
    refuse.add_argument("--reason", required=True)
    filed = subparsers.add_parser("filed")
    filed.add_argument("candidate_id")
    filed.add_argument("url")
    subparsers.add_parser("poll", help="FR-13.16's fingerprint reconciliation")
    return parser


def main(argv: Optional[list] = None, out=None) -> int:
    """Parse *argv*, run the one command, and return its exit status."""
    args = build_parser().parse_args(argv)
    return _COMMANDS[args.command](LoopStore(args.db), args, out or sys.stdout)


if __name__ == "__main__":       # pragma: no cover - the entry point itself
    sys.exit(main())
