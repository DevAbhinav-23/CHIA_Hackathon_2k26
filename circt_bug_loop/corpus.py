"""A1, feature F-01: mine `llvm/circt` and emit the loop's seed corpus.

`03-LLD.md` §3.3 is normative for the callables, §4.12's table for the git
commands and `01-FRD.md` F-01 for the behaviour. The mining rule itself is
`analysis/pin-window-analysis.md` §2 lines 74-79, quoted verbatim by FR-01.1 and
reproduced in `_SUBJECT_RE` and `mining_filter` below.

**What is reused and how.** `analysis/pin_window.py` and
`analysis/measurements/m1_runlines.py` are scripts, not modules: both run their
whole analysis at import time and the second writes files, so neither can be
imported. The pieces this module needs are therefore **copied**, each with the
line it came from: the subject regex (`pin_window.py:107-108`), the file-shape
filter (`pin_window.py:131-137`), the `--name-status` parse
(`pin_window.py:114-124`), the pin walk (`pin_window.py:60-77`), the window
numbering and the nearest-tag rule (`pin_window.py:80-99`, `142-163`), the
`RUN:` continuation joiner and the entry-tool regex
(`m1_runlines.py:run_lines`, `m1_runlines.py:TOOLS` and `entry_tool`) and the
language map (`m1_runlines.py:LANG`). Nothing else is taken, and no analysis
file is imported at run time.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from chia.base.ChiaFunction import ChiaFunction

from circt_bug_loop.contract.schema import (CounterBlock, Polarity, SeedRecord,
                                            Shape, validate)

#: The `llvm` submodule path, from CIRCT's own `.gitmodules` (PIN §1).
SUBMODULE = "llvm"

#: The refspec FR-01.8 names. Passed as ONE element of an argument list, never
#: through a shell, which is what makes FR-01.8's failure mode unreachable here.
TAG_REFSPEC = "refs/tags/firtool-*"

#: `analysis/pin_window.py:107-108`, verbatim. PIN §2's "Candidate (filtered)".
_SUBJECT_RE = re.compile(r"\b(fix|fixes|fixed|bug|crash|assert|assertion|segfault|"
                         r"regression|ice|infinite loop|null|uaf|use-after-free)\b",
                         re.I)

#: PIN §2's "Candidate (shape filter)" directories (`pin_window.py:109-110`).
_SRC_DIRS = ("lib/", "include/")
_TEST_DIRS = ("test/", "integration_test/")

#: FR-01.3's closed set. Anything else is `other`.
_ENTRY_TOOLS = ("circt-opt", "firtool", "circt-verilog", "circt-translate",
                "arcilator")

#: `m1_runlines.py:TOOLS`, copied: every tool name CIRCT's `test/` tree invokes.
#: FR-01.2's "the first CIRCT tool name each line invokes" is this list searched
#: over the line's first pipeline segment, and FR-01.3 then maps the answer into
#: the six values above. The list is wider than those six deliberately: a seed
#: entering through `circt-reduce` or `circt-lec` is then classified `other`
#: knowingly, rather than by failing to recognise the name at all.
_TOOLS = ("circt-opt", "firtool", "circt-verilog", "circt-translate", "arcilator",
          "circt-reduce", "circt-lec", "circt-bmc", "circt-test", "circt-synth",
          "circt-as", "circt-dis", "circt-lsp-server", "hlstool", "kanagawatool",
          "esi-tester", "om-linker", "firld", "circt-capi-.*", "handshake-runner",
          "ibistool", "circt-cocotb-driver.py", "circt-rtl-sim.py")
_TOOL_RE = re.compile(r"(?<![\w./-])(" + "|".join(_TOOLS) + r")(?![\w-])")

#: FR-01.4's one special prefix: the unmerged bucketing keeps it whole, the
#: normative dialect-level one replaces it with the dialect under it.
_DIALECT_INCLUDE = "include/circt/Dialect"

#: §3.3 step 6's shell constructs, and §3.3 step 5's untouched substitution.
_UNSUPPORTED_CONSTRUCTS = (";", "&&", "`", "$(", "%{")

#: §3.3's "one normalisation the probe argv needs and the seed record does not".
#: Four spellings and not two: LLVM's own option parser accepts one dash or two
#: for every long option, and CIRCT's tests write both. 46 of M1's 331 corpus
#: `RUN:` lines carry a single-dash form (`raw/m1-per-runline.csv`), among them
#: the one `tests/fixtures/crashes/assertion_02/` was mined from, whose
#: `-verify-diagnostics` survived into its `argv.json` and turned the emitted
#: diagnostic into exit status 0 (errata W-09 #3).
_PROBE_ONLY_OPTIONS = ("--split-input-file", "-split-input-file",
                       "--verify-diagnostics", "-verify-diagnostics")

#: `m1_runlines.py:LANG`, copied. The probe language is the test file's own
#: extension and nothing else.
_LANGUAGES = {".mlir": ".mlir", ".fir": ".fir", ".sv": ".sv", ".v": ".sv",
              ".svh": ".sv", ".vh": ".sv"}

#: The second slang entry point (§4.5): `circt-translate` registers
#: `--import-verilog` only under `CIRCT_SLANG_FRONTEND_ENABLED`, so a line
#: carrying it needs a slang build whatever else it says (M1's D-13 cross-check,
#: and §5.3's `sv_seeds_excluded`).
_SLANG_OPTION = "--import-verilog"


class CorpusError(Exception):
    """Raised by build_corpus. Carries a stable reason so tests assert on it.

    The two reasons are FR-01.8's `no_tags` and FR-01.11's `head_moved`; both
    are preconditions that make a run meaningless, so B12 exits non-zero on
    either and the run does not start (`02-HLD.md` §6).
    """

    def __init__(self, reason: str, message: str):
        self.reason = reason
        super().__init__(f"{reason}: {message}")


# --------------------------------------------------------------------------
# The pure functions: no git, no clone, no model. Tier 0 in full.
# --------------------------------------------------------------------------

def extract_run_lines(text: str) -> list[str]:
    """Return every lit `RUN:` line of *text*, verbatim, continuations grouped.

    An entry is the text following `RUN:` on one physical line, stripped; a line
    whose text ends in `\\` absorbs the next physical line, and the entry then
    carries both, backslashes retained, joined by a newline. That is FR-01.2's
    "verbatim" for a construct that has no single-line spelling, and step 0 of
    `normalise_run_line` is what folds it back into one logical line. The
    continuation rule is `m1_runlines.py:run_lines`, which is how M1 counted 331
    logical lines over the corpus.

    Returns:
        a list of strings, one per logical `RUN:` line, in file order.
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing.
    """
    out: list[str] = []
    pending: list[str] | None = None
    for physical in text.splitlines():
        if pending is not None:
            # A continuation line: drop its comment marker and its own `RUN:`
            # prefix if it repeats one, which CIRCT's tests do.
            body = physical.strip().lstrip("/;#*! ").strip()
            body = re.sub(r"^RUN:\s*", "", body)
            pending.append(body)
            if not body.endswith("\\"):
                out.append("\n".join(pending))
                pending = None
            continue
        match = re.search(r"RUN:\s*(.*)$", physical)
        if not match:
            continue
        body = match.group(1).strip()
        if body.endswith("\\"):
            pending = [body]
        else:
            out.append(body)
    if pending is not None:                       # a dangling continuation
        out.append("\n".join(pending))
    return out


def _split_at_unquoted_pipe(text: str) -> tuple[str, str]:
    """Split *text* at its first `|` that is outside quotes (§3.3 step 4).

    The scanner is two-state over `'` and `"`, so a pipe inside a quoted
    FileCheck pattern does not truncate the line.
    """
    quote: str | None = None
    for i, char in enumerate(text):
        if quote is not None:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == "|":
            return text[:i].rstrip(), text[i:]
    return text, ""


def normalise_run_line(
        line: str, *, subs: Optional[dict[str, str]] = None
) -> tuple[str, list[str], Polarity, Shape, dict[str, str], dict]:
    """Turn one verbatim lit RUN: line into a tool, an argv and its properties.

    The six steps of `03-LLD.md` §3.3 are performed in that order. *subs* binds
    lit's substitutions when the caller has a probe directory to bind them to:
    keys `s`, `t` and `S` for FR-01.10's `%s`, `%t` and `%S`. With *subs* unset,
    which is how `build_corpus` calls it, the three are left as themselves, so
    the emitted `argv_template` stays a template and the probe emitter binds
    them (§7.3). Substitution is textual, not token-wise, because lit's `%t` is
    a prefix and `%t.dir` must become `<probe dir>/t.dir`.

    Returns:
        (tool, argv, polarity, shape, env, notes). `argv` EXCLUDES the tool,
        which is §4.1's splat and §4.2's worked example. `env` maps NAME to
        VALUE for a stripped `env` wrapper. `notes` carries §3.3's five keys:
        lines_joined (int), not_crash (bool), dropped_tail (str), substitutions
        (dict of placeholder to count) and unsupported_construct (str or None).
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing. An unparseable line returns shape="unsupported" with the
        construct recorded, which excludes the seed rather than aborting.
    """
    notes: dict = {"lines_joined": 1, "not_crash": False, "dropped_tail": "",
                   "substitutions": {}, "unsupported_construct": None}
    env: dict[str, str] = {}

    # Step 0 - join lit's `\` continuations into one logical line and strip a
    # `// RUN:` or `; RUN:` prefix that a caller passed through unstripped.
    physical = line.split("\n")
    notes["lines_joined"] = len(physical)
    body = " ".join(part.strip().rstrip("\\").strip() for part in physical).strip()
    body = re.sub(r"^[/;#*!\s]*RUN:\s*", "", body)

    # Steps 1 and 2 - the `not` and `env` wrappers. FR-01.10 orders them `not`
    # then `env`, but CIRCT's own tree spells the other order too
    # (integration_test/circt-test/basic-circt-bmc.mlir is `env NAME=V not
    # circt-test ...`), so both are stripped until neither leads. Stripping is
    # order-free; what each step records is not, and each still records its own.
    polarity: Polarity = "expect_zero"
    while True:
        tokens = body.split(None, 1)
        if not tokens:
            break
        head = tokens[0]
        if head == "not":
            polarity = "expect_nonzero"
            body = tokens[1] if len(tokens) > 1 else ""
            rest = body.split(None, 1)
            if rest and rest[0] == "--crash":
                notes["not_crash"] = True
                body = rest[1] if len(rest) > 1 else ""
            continue
        if head == "env":
            body = tokens[1] if len(tokens) > 1 else ""
            while True:
                rest = body.split(None, 1)
                if not rest or "=" not in rest[0] or rest[0].startswith("-"):
                    break
                name, _, value = rest[0].partition("=")
                env[name] = value
                body = rest[1] if len(rest) > 1 else ""
            continue
        break

    # Step 3 - the `split-file` wrapper.
    shape: Shape = "plain"
    tokens = body.split(None, 1)
    if tokens and tokens[0] == "split-file":
        shape = "split_file"
        body = tokens[1] if len(tokens) > 1 else ""

    # Step 4 - drop everything from the first unquoted pipe.
    body, tail = _split_at_unquoted_pipe(body)
    notes["dropped_tail"] = tail

    # Step 5 - resolve lit's substitutions. `%S` before `%s` is unnecessary (the
    # two differ in case) but the order is fixed so the recorded counts are too.
    bindings = {"%S": (subs or {}).get("S"), "%s": (subs or {}).get("s"),
                "%t": (subs or {}).get("t")}
    for placeholder, value in bindings.items():
        count = body.count(placeholder)
        if count:
            notes["substitutions"][placeholder] = count
            if value is not None:
                body = body.replace(placeholder, value)

    # Step 6 - any surviving shell construct, or a `%{...}` step 5 left alone.
    # The scan is over the whole line and not over its tokens: FR-01.10 says
    # "still carrying", and a `;` inside a quoted option value is still a `;`
    # this loop will not run under a shell.
    for construct in _UNSUPPORTED_CONSTRUCTS:
        if construct in body:
            notes["unsupported_construct"] = construct
            shape = "unsupported"
            break

    try:
        argv = shlex.split(body)
    except ValueError as exc:                     # an unbalanced quote
        notes["unsupported_construct"] = f"unbalanced quote: {exc}"
        return "", [], polarity, "unsupported", env, notes
    if not argv:
        notes["unsupported_construct"] = notes["unsupported_construct"] or "empty"
        return "", [], polarity, "unsupported", env, notes
    return argv[0], argv[1:], polarity, shape, env, notes


def strip_probe_only_options(argv: list[str]) -> tuple[list[str], list[str]]:
    """Remove the two options that mean nothing for a single probing input.

    `--verify-diagnostics` makes the tool succeed when it emits the diagnostics
    an `expected-*` comment predicted, and a generated input carries none;
    `--split-input-file` makes the tool process independent chunks, under which
    `circt-reduce` can delete nothing. Each is removed in all four spellings
    the tests use: one dash or two, bare or `=`-valued, because `circt-opt`
    takes `--split-input-file[=<string>]` and `--verify-diagnostics=<value>`
    (§4.2, verified) and LLVM's parser takes either dash count.

    Returns:
        (surviving_argv, removed_tokens), both in the input's order.
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing.
    """
    kept, removed = [], []
    for token in argv:
        if any(token == opt or token.startswith(opt + "=")
               for opt in _PROBE_ONLY_OPTIONS):
            removed.append(token)
        else:
            kept.append(token)
    return kept, removed


def entry_tool_of_line(line: str) -> str:
    """Return the first CIRCT tool name *line* invokes, or "" if it invokes none.

    `m1_runlines.py:entry_tool`, copied, minus its `(downstream)` annotation:
    the search is over the line's first pipeline segment, so `| FileCheck` and
    every other downstream filter is out of scope, and it is a search rather
    than a look at the first token because CIRCT's own tests wrap the tool in
    `not`, in `env`, in `split-file ... &&` and in `%python`. The line handed in
    is the VERBATIM one, which is what M1 counted, so what this produces is
    comparable with M1's table seed for seed.

    Returns:
        one of `_TOOLS`, or "" when the line invokes no CIRCT tool at all.
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing.
    """
    match = _TOOL_RE.search(line.split("|")[0]) or _TOOL_RE.search(line)
    return match.group(1) if match else ""


def classify_entry_tool(tool: str) -> str:
    """Map one `RUN:` line's tool name into FR-01.3's closed six-value set."""
    return tool if tool in _ENTRY_TOOLS else "other"


def dialect_buckets(path: str) -> tuple[str, str]:
    """Bucket one `lib/` or `include/` path under both rules of FR-01.4.

    Returns:
        (dialect_bucket, dialect_bucket_unmerged). The first is normative: a
        path under `include/circt/Dialect/<X>` buckets as `<X>`. The second
        keeps `include/circt/Dialect` whole, which is FINAL Appendix A's rule.
        Every other path buckets as its third component under both.
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing.
    """
    parts = path.split("/")
    if path.startswith(_DIALECT_INCLUDE + "/") and len(parts) > 3:
        return parts[3], _DIALECT_INCLUDE
    bucket = parts[2] if len(parts) > 2 else parts[-1]
    return bucket, bucket


def parse_name_status(text: str) -> dict[str, list[tuple[str, str]]]:
    """Parse `git log --first-parent --name-status --format=COMMIT %H` output.

    `analysis/pin_window.py:114-124`, copied. A rename or copy line carries two
    paths and the DESTINATION is the one kept, which is what `parts[-1]` means.

    Returns:
        commit SHA -> list of (status, path), in git's order.
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing.
    """
    files: dict[str, list[tuple[str, str]]] = {}
    current = None
    for line in text.splitlines():
        if line.startswith("COMMIT "):
            current = line.split()[1]
            files[current] = []
        elif line and line[0] in "AMDRTC" and "\t" in line and current is not None:
            parts = line.split("\t")
            files[current].append((parts[0], parts[-1]))
    return files


def mining_filter(files: list[tuple[str, str]]) -> Optional[tuple[list[str], list[str]]]:
    """Apply PIN §2's shape filter to one commit's `--name-status` entries.

    The rule, quoted by FR-01.1 and normative in that form: a first-parent
    commit touching 1-2 files under `lib/` or `include/` AND adding or modifying
    at least 1 file under `test/` or `integration_test/`. "Adding or modifying"
    is `pin_window.py:135`'s `st in ("A", "M", "R", "C")`.

    Returns:
        (source_paths, test_paths) when the commit passes, None when it does
        not. Both lists are in git's own order and neither is ever collapsed
        (FR-01.12).
    Worker:
        pure; no resource, no git, no model.
    Raises:
        nothing.
    """
    src = [p for _, p in files if p.startswith(_SRC_DIRS)]
    test = [p for st, p in files
            if p.startswith(_TEST_DIRS) and st in ("A", "M", "R", "C")]
    if not (1 <= len(src) <= 2 and len(test) >= 1):
        return None
    return src, test


def subject_matches(subject: str) -> bool:
    """Say whether a commit subject matches PIN §2's bug-ish word list."""
    return bool(_SUBJECT_RE.search(subject))


def language_of(path: str) -> str:
    """Return the probe language of a test path, by extension (`m1_runlines`)."""
    return _LANGUAGES.get(os.path.splitext(path)[1], "other")


# --------------------------------------------------------------------------
# The git layer and the two nodes.
# --------------------------------------------------------------------------

class _Git:
    """Every git call of §4.12, against one clone, under one overall deadline.

    `capture_output=True, text=True, check=True` plus a per-call timeout is the
    shape `analysis/pin_window.py:29-31` already uses. Nothing here takes a
    shell and every argument is one element of an argument list. `calls` counts
    the subprocesses launched, which is what `T-U-corpus-22` asserts on.
    """

    def __init__(self, clone_path: str, timeout_seconds: int):
        self.clone_path = clone_path
        self.deadline = time.monotonic() + timeout_seconds
        self.calls = 0

    def _remaining(self) -> float:
        return max(1.0, self.deadline - time.monotonic())

    def __call__(self, *args: str) -> str:
        self.calls += 1
        return subprocess.run(["git", "-C", self.clone_path, *args],
                              capture_output=True, text=True, check=True,
                              timeout=self._remaining()).stdout

    def batch(self, specs: list[str]) -> dict[str, Optional[str]]:
        """Read many blobs in ONE `git cat-file --batch` (§3.3, M1's method)."""
        self.calls += 1
        proc = subprocess.run(["git", "-C", self.clone_path, "cat-file", "--batch"],
                              input=("\n".join(specs) + "\n").encode(),
                              capture_output=True, timeout=self._remaining())
        out, pos, blobs = proc.stdout, 0, {}
        for spec in specs:
            newline = out.find(b"\n", pos)
            if newline < 0:
                blobs[spec] = None
                continue
            # `errors="backslashreplace"` and NOT "replace", and the keyword
            # form and not the positional one: the destructive decoder maps
            # every undecodable byte to one U+FFFD and a seed text that went
            # through it cannot be written back as the bytes CIRCT parsed
            # (W-08 erratum 20; T-U-schema-18 asserts the rule over the tree).
            header = out[pos:newline].decode(
                "utf-8", errors="backslashreplace").split()
            pos = newline + 1
            if len(header) == 3 and header[1] == "blob":
                size = int(header[2])
                blobs[spec] = out[pos:pos + size].decode(
                    "utf-8", errors="backslashreplace")
                pos += size + 1
            else:                                 # "missing" / "dangling"
                blobs[spec] = None
        return blobs


def _utc(unix: str) -> datetime:
    return datetime.fromtimestamp(int(unix), tz=timezone.utc)


def _read_tags(git: _Git) -> list[dict]:
    """§4.12 rows 3 and 4: every `firtool-*` tag with its date and `llvm` pin."""
    listing = git("for-each-ref", "--format=%(refname:short)\t%(creatordate:unix)",
                  "--sort=creatordate", TAG_REFSPEC)
    if not listing.strip():
        raise CorpusError(
            "no_tags",
            f"git for-each-ref returned nothing for {TAG_REFSPEC!r}. The clone "
            "has no firtool releases, or the refspec was eaten by a shell glob: "
            "quote it (PIN §1's reproduction note). It is passed here as one "
            "element of an argument list, so no shell of this process can eat it.")
    tags = []
    for line in listing.splitlines():
        name, date = line.split("\t")
        entry = git("ls-tree", name, SUBMODULE).strip()
        if not entry:
            continue
        tags.append({"tag": name, "date": _utc(date), "llvm": entry.split()[2]})
    return tags


def _walk_pins(git: _Git, ref: str = "HEAD") -> list[dict]:
    """§4.12 rows 5 to 7: the first-parent history with the pin at each commit.

    `analysis/pin_window.py:52-77`, copied. In a `--first-parent` log each entry
    is the previous entry's first parent, which is where `parent_sha` comes from
    without a further git command.

    *ref* is the walk's starting point and defaults to `HEAD`, which is the
    table's own spelling and the only one A1 uses: FR-01.11 pins the clone to
    `corpus_head_sha` first, so `HEAD` is the corpus head by construction. A2
    passes `origin/main` instead, because its clone is not detached (§3.4).
    """
    commits = []
    for line in git("log", "--first-parent", "--format=%H\t%ct\t%s",
                    ref).splitlines():
        sha, when, subject = line.split("\t", 2)
        commits.append({"sha": sha, "date": _utc(when), "subject": subject})

    bumps, current = {}, None
    for line in git("log", "--first-parent", "--raw", "--no-abbrev",
                    "--format=COMMIT %H", ref, "--", SUBMODULE).splitlines():
        if line.startswith("COMMIT "):
            current = line.split()[1]
        elif line.startswith(":160000"):
            parts = line.replace("\t", " ").split()
            bumps[current] = (parts[2], parts[3])

    pin = git("ls-tree", ref, SUBMODULE).split()[2]
    for i, commit in enumerate(commits):
        commit["llvm"] = pin
        if commit["sha"] in bumps:
            old, new = bumps[commit["sha"]]
            assert new == pin, f"pin walk desync at {commit['sha']}"
            pin = old
        commit["parent_llvm"] = pin
        commit["parent_sha"] = commits[i + 1]["sha"] if i + 1 < len(commits) else ""
    return commits


def _pin_windows(commits: list[dict]) -> dict[str, int]:
    """Number the maximal contiguous same-pin ranges oldest to newest (PIN §2).

    A window id difference IS the number of LLVM bumps apart, which is what
    FR-01.7's `bumps_away` counts (`analysis/pin_window.py:80-99`). A pin that
    recurs in two non-contiguous windows keeps the OLDEST id, which is
    `pin_window.py:101-103`'s `setdefault`.
    """
    order: list[str] = []
    for commit in reversed(commits):              # oldest -> newest
        if not order or order[-1] != commit["llvm"]:
            order.append(commit["llvm"])
    window_of: dict[str, int] = {}
    for i, pin in enumerate(order):
        window_of.setdefault(pin, i)              # first (oldest) match
    return window_of


def _match_sdk(parent_pin: str, commit_date: datetime, tags: list[dict],
               window_of: dict[str, int]) -> dict:
    """FR-01.7's pairing: exact tag, else the nearest by LLVM bumps then days.

    `analysis/pin_window.py:142-163`, copied. The bug state is the FIRST PARENT,
    so the pin matched is the parent's and never the seed's own (PIN §2). Where
    several tags share the pin the oldest by tag date wins, which is
    `pin_window.py:147-149`.
    """
    exact = sorted((t for t in tags if t["llvm"] == parent_pin),
                   key=lambda t: t["date"])
    if exact:
        return {"exact": True, "bumps": None, "tag": exact[0]["tag"]}
    here = window_of.get(parent_pin)
    best = None
    for tag in tags:
        there = window_of.get(tag["llvm"])
        if there is None or here is None:
            continue
        distance = abs(there - here)
        days = abs((tag["date"] - commit_date).total_seconds() / 86400.0)
        if best is None or (distance, days) < (best[0], best[1]):
            best = (distance, days, tag["tag"])
    if best is None:
        return {"exact": False, "bumps": None, "tag": None}
    return {"exact": False, "bumps": best[0], "tag": best[2]}


def _bump(counter: dict, key: str) -> None:
    counter[key] = counter.get(key, 0) + 1


@ChiaFunction(max_retries=0)
def build_corpus(clone_path: str, corpus_head_sha: str, since: str,
                 inline_cap_bytes: int, timeout_seconds: int = 1800) -> dict:
    """Mine llvm/circt by PIN section 2's rule and emit the loop's seed corpus.

    Returns:
        {"seeds": list[SeedRecord], "sdk_map": dict[str, list[str]],
         "counts": {"filtered": int, "exact_pin": int, "no_run_line": int,
                    "unsupported_shape": int, "seed_text_over_cap": int,
                    "missing_blobs": int, "run_lines": int, "test_files": int,
                    "tags": int, "git_calls": int, "polarity": dict, "shape": dict,
                    "entry_tool": dict, "entry_tool_seeds": dict,
                    "language": dict, "dialect_bucket": dict,
                    "dialect_bucket_unmerged": dict, "other_tool_shas": list},
         "exclusions": {seed_sha: reason}, one of no_run_line,
             unsupported_shape or seed_text_over_cap,
         "nearest_tag": {seed_sha: tag}, the non-exact seeds only (FR-01.7),
         "sv_seeds": list[str], the seeds ADR-D-13 branch (b) excludes (§5.3),
         "inputs": {"clone_head_sha": str, "since": str, "git_version": str},
         "counters": CounterBlock}
    Worker:
        head - it runs git against the head's blobless clone, which is the only
        repository in the deployment holding 24 months of main (K5).
    Raises:
        CorpusError("no_tags") when for-each-ref returns nothing for
            refs/tags/firtool-*, with the refspec and the quoting note (FR-01.8);
        CorpusError("head_moved") when the clone's HEAD differs from
            corpus_head_sha, naming both (FR-01.11);
        ContractError from contract.validate when a record built here is not a
            valid SeedRecord, which is a defect here and never in the clone;
        ValueError when `since` is not an ISO 8601 date;
        subprocess.CalledProcessError or subprocess.TimeoutExpired from git.
    """
    started_at = time.monotonic()
    git = _Git(clone_path, timeout_seconds)

    head = git("rev-parse", "HEAD").strip()
    if head != corpus_head_sha:
        raise CorpusError(
            "head_moved",
            f"the clone at {clone_path} is at HEAD {head} but the corpus is "
            f"pinned at {corpus_head_sha}; reset it with "
            f"`git -C {clone_path} checkout --detach {corpus_head_sha}` before "
            "mining, or a different corpus is mined (FR-01.11)")
    git_version = subprocess.run(["git", "--version"], capture_output=True,
                                 text=True, check=True, timeout=60).stdout.strip()

    tags = _read_tags(git)
    commits = _walk_pins(git)
    window_of = _pin_windows(commits)
    name_status = parse_name_status(
        git("log", "--first-parent", "--name-status", "--format=COMMIT %H", "HEAD"))

    since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
    mined = []
    for commit in commits:
        if commit["date"] < since_dt or not subject_matches(commit["subject"]):
            continue
        shaped = mining_filter(name_status.get(commit["sha"], []))
        if shaped is not None:
            mined.append((commit, shaped[0], shaped[1]))

    # One batched read for every changed test file of every mined seed: the
    # blobs serve FR-01.2's RUN: extraction and FR-05.1's starting inputs at
    # once, and a blobless clone does one lazy fetch pass instead of hundreds.
    specs = [f"{c['sha']}:{p}" for c, _, tests in mined for p in tests]
    blobs = git.batch(specs) if specs else {}

    counts: dict = {"filtered": len(mined), "exact_pin": 0, "no_run_line": 0,
                    "unsupported_shape": 0, "seed_text_over_cap": 0,
                    "missing_blobs": 0, "run_lines": 0, "test_files": len(specs),
                    "tags": len(tags), "git_calls": 0,
                    "polarity": {}, "shape": {}, "entry_tool": {},
                    "entry_tool_seeds": {}, "language": {}, "dialect_bucket": {},
                    "dialect_bucket_unmerged": {}, "other_tool_shas": []}
    seeds: list[SeedRecord] = []
    sdk_map: dict[str, list[str]] = {}
    exclusions: dict[str, str] = {}
    nearest_tag: dict[str, str] = {}
    sv_seeds: list[str] = []

    for commit, source_paths, test_paths in mined:
        sha = commit["sha"]
        test_files = {}
        for path in test_paths:
            text = blobs.get(f"{sha}:{path}")
            if text is None:                      # absent at the seed commit,
                counts["missing_blobs"] += 1      # or unfetchable while offline
                text = ""
            test_files[path] = text

        run_lines: list[str] = []
        argv_template: list[list[str]] = []
        polarity: list[Polarity] = []
        shape: list[Shape] = []
        tools: list[str] = []
        for path in test_paths:
            for line in extract_run_lines(test_files[path]):
                _tool, argv, pol, shp, _env, _notes = normalise_run_line(line)
                run_lines.append(line)
                argv_template.append(argv)
                polarity.append(pol)
                shape.append(shp)
                tools.append(entry_tool_of_line(line))
                if tools[-1] == "circt-verilog" or (
                        tools[-1] == "circt-translate" and _SLANG_OPTION in line):
                    if sha not in sv_seeds:
                        sv_seeds.append(sha)
                _bump(counts["polarity"], pol)
                _bump(counts["shape"], shp)
        counts["run_lines"] += len(run_lines)

        # FR-01.3 wants ONE value per seed and does not say which line's tool a
        # multi-tool seed takes, so it is the first line's, in test_paths order.
        # M1's per-tool seed membership is counted beside it, because that is
        # the table FR-01.3's acceptance compares against and it does not sum
        # to 187: 27 seeds enter through more than one tool.
        entry_tool = classify_entry_tool(tools[0]) if tools else "other"
        if entry_tool == "other":
            counts["other_tool_shas"].append(sha)
        _bump(counts["entry_tool"], entry_tool)
        for tool in sorted(set(tools) - {""}):
            _bump(counts["entry_tool_seeds"], tool)
        for language in sorted({language_of(p) for p in test_paths}):
            _bump(counts["language"], language)

        bucket, unmerged = dialect_buckets(source_paths[0])
        _bump(counts["dialect_bucket"], bucket)
        _bump(counts["dialect_bucket_unmerged"], unmerged)

        match = _match_sdk(commit["parent_llvm"], commit["date"], tags, window_of)
        if match["exact"]:
            counts["exact_pin"] += 1
            sdk_map.setdefault(match["tag"], []).append(sha)
        elif match["tag"] is not None:
            nearest_tag[sha] = match["tag"]       # FR-01.7's nearest, by date

        # §3.3's sixth command: the seed's diff of its lib/ and include/ paths
        # only, the test half being in test_files already.
        diff = git("show", "--format=", "--unified=3", "--no-renames", sha,
                   "--", *source_paths)

        # The cap is measured, never applied: bound_text would return None and
        # `diff` and `test_files` are REQUIRED fields (contract 2.0, §2.4). A
        # truncated diff in a prompt is a worse input than no seed, so an
        # over-cap seed is excluded from BOTH arms and counted instead.
        text_bytes = len(diff.encode("utf-8")) + sum(
            len(t.encode("utf-8")) for t in test_files.values())
        if text_bytes > inline_cap_bytes:
            counts["seed_text_over_cap"] += 1
            exclusions[sha] = "seed_text_over_cap"
        elif not run_lines:
            counts["no_run_line"] += 1
            exclusions[sha] = "no_run_line"
        elif all(s == "unsupported" for s in shape):
            counts["unsupported_shape"] += 1
            exclusions[sha] = "unsupported_shape"

        record = SeedRecord(
            seed_sha=sha,
            parent_sha=commit["parent_sha"],
            subject=commit["subject"],
            committed_date_utc=commit["date"].isoformat(),
            source_paths=source_paths,
            test_paths=test_paths,
            llvm_pin=commit["parent_llvm"],
            sdk_tag=match["tag"] if match["exact"] else None,
            sdk_exact=match["exact"],
            bumps_away=match["bumps"],
            entry_tool=entry_tool,
            dialect_bucket=bucket,
            dialect_bucket_unmerged=unmerged,
            run_lines=run_lines,
            argv_template=argv_template,
            polarity=polarity,
            shape=shape,
            diff=diff,
            test_files=test_files,
            corpus_head_sha=corpus_head_sha)
        validate(record)
        seeds.append(record)

    counts["git_calls"] = git.calls
    return {"seeds": seeds, "sdk_map": sdk_map, "counts": counts,
            "exclusions": exclusions, "nearest_tag": nearest_tag,
            "sv_seeds": sv_seeds,
            "inputs": {"clone_head_sha": head, "since": since,
                       "git_version": git_version},
            "counters": CounterBlock(stage="corpus", started=len(mined),
                                     completed=len(seeds),
                                     failed=len(mined) - len(seeds),
                                     seconds=time.monotonic() - started_at)}


@ChiaFunction(max_retries=0)
def resolve_sites(clone_path: str, run_commit: str, sites: list[dict],
                  timeout_seconds: int = 300) -> dict:
    """Say which of a turn's sibling sites exist in the tree at the run's commit.

    Returns:
        {"resolved": list[dict], "rejected": list[dict], "counters":
        CounterBlock}, each site entry the input site plus "reason" on a
        rejection, one of "no_such_file" or "no_symbol". The counters count
        sites, at stage "corpus", A1' being A1's second node (3.11).
    Worker:
        head - the clone is the head's (K5). No model, no CIRCT binary.
    Raises:
        nothing. A git failure marks every site of that call "no_such_file" with
        the git stderr recorded, which rejects rather than accepts.
    """
    started_at = time.monotonic()
    git = _Git(clone_path, timeout_seconds)
    resolved, rejected = [], []
    for site in sites:
        path, symbol = site.get("file", ""), site.get("symbol", "")
        directory, _, basename = path.rpartition("/")
        try:
            listed = git("ls-tree", "--", f"{run_commit}:{directory}", basename)
        except (subprocess.SubprocessError, OSError) as exc:
            rejected.append({**site, "reason": "no_such_file",
                             "stderr": str(getattr(exc, "stderr", "") or exc)})
            continue
        if not listed.strip():
            rejected.append({**site, "reason": "no_such_file", "stderr": ""})
            continue
        try:
            # `git grep` exits 1 on "no match", which is an answer and not a
            # failure, so that one return code is read rather than raised on.
            found = git("grep", "-n", "-F", "--", symbol, run_commit, "--", path)
        except subprocess.CalledProcessError as exc:
            found = exc.stdout or ""
        except (subprocess.SubprocessError, OSError) as exc:
            rejected.append({**site, "reason": "no_such_file",
                             "stderr": str(getattr(exc, "stderr", "") or exc)})
            continue
        if found.strip():
            resolved.append(dict(site))
        else:
            rejected.append({**site, "reason": "no_symbol", "stderr": ""})
    return {"resolved": resolved, "rejected": rejected,
            "counters": CounterBlock(stage="corpus", started=len(sites),
                                     completed=len(resolved),
                                     failed=len(rejected),
                                     seconds=time.monotonic() - started_at)}
