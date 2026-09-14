"""A4's frozen mutator set: the loader, the digest check and the runner (8.1, 8.2).

Three things and no fourth: `load_set`, which reads one canonical-JSON set and
compares its digest to the one `RunManifest.mutator_set_sha` names (8.1 rule 1);
`apply`, one deterministic mutator against one input text; and `mutate_seed`,
the round-robin over a seed's changed test files that produces up to the cap.

**No model runs here at any point and none can** (FR-05.1): nothing in this
module imports a backend, and the arm's whole input is `SeedRecord.test_files`
plus the set, which is what contract 2.0 bought (K6). The only file this module
reads is the set itself, and `apply` and `mutate_seed` read no file at all.

Three deviations from 03-LLD.md, each recorded in
`design/reviews/implementation-errata-log.md`:

  * `mutate_seed` returns `(mutants, no_ops, failures)` and not the bare list
    8.2's signature gives, because FR-05.6 requires the no-op count to be
    reported and FR-05.7 requires a failure to be attributed to its id, and
    neither has anywhere else to go.
  * Each mutant is a FIVE-tuple, the fifth member being the replacement argv of
    an argv mutator or None. FR-05.5 gives an argv mutator a replacement
    argument vector and 8.2's four-tuple has no slot for it.
  * `apply` takes the loaded set as a keyword argument, defaulting to this
    module's own. 8.2's three-argument signature cannot find a mutator by id
    without one, and a module-level set that a test cannot substitute would
    make the raising-mutator case of FR-05.7 untestable.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Optional

#: 8.1's four languages. A mutator runs against inputs of its own language, or
#: of any language when it declares `any`.
LANGUAGES = ("mlir", "fir", "sv", "any")

#: What a derived mutant seed is masked to (W-19b finding 2). SQLite's INTEGER
#: is a SIGNED 64-bit value and `mutant_seed_int` derived an unsigned one, so
#: half of every mutation arm's probes raised `OverflowError` on their way into
#: the store and stopped the campaign.
SEED_INT_MASK = 2 ** 63 - 1

#: 8.1's `kind` values, and the seven named replacement operations.
KINDS = ("text", "line", "argv")
NUMERIC_OPERATIONS = ("flip", "zero", "max", "off_by_one")
SEQUENCE_OPERATIONS = ("duplicate", "delete", "swap")
NAMED_OPERATIONS = NUMERIC_OPERATIONS + SEQUENCE_OPERATIONS

#: What `max` writes. A width or a bound bug sits at a representable boundary
#: far more often than at an arbitrary large number, and this is the boundary
#: every 32-bit signed count in an MLIR attribute has.
MAX_INT = 2 ** 31 - 1

#: 8.1's id rule, checked here and again by the synthesis (8.3 step 4).
ID = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+){2,}$")

_INTEGER = re.compile(r"\d+")
_LANGUAGE_BY_SUFFIX = {".mlir": "mlir", ".fir": "fir", ".sv": "sv",
                       ".svh": "sv", ".v": "sv"}

DIRECTORY = Path(__file__).resolve().parent
DEVELOPMENT_SET = DIRECTORY / "set_dev.json"

#: `set_v<n>.json`, and nothing else: the development set is `set_dev.json` and
#: does not match, which is what keeps it out of this resolution entirely.
_FROZEN_NAME = re.compile(r"^set_v(\d+)\.json$")


def frozen_sets() -> list:
    """Every frozen set beside this module, oldest version first (8.1).

    Ordered by the INTEGER in the name and not by the string, so `set_v10.json`
    sorts after `set_v9.json` rather than between `set_v1` and `set_v2`.

    Returns:
        list[Path], possibly empty before A7 has ever run.
    Worker:
        the caller's; one directory listing and no read.
    Raises:
        nothing.
    """
    found = [(int(match.group(1)), path) for path in DIRECTORY.glob("set_v*.json")
             for match in [_FROZEN_NAME.match(path.name)] if match]
    return [path for _version, path in sorted(found)]


#: The frozen set the campaign runs, and the development set that stands in for
#: it until A7 has been run. A frozen set wins wherever one exists, so a campaign
#: can never pick up the development set by accident, and the NEWEST frozen set
#: wins among them (W-12c): a later synthesis supersedes an earlier one, and the
#: earlier file stays committed because it is the record of what an earlier run
#: measured, not because any run should still draw from it. Only `set_v<n>.json`
#: is resolved; `load_set(path)` takes any path a caller names explicitly, which
#: is how an older set is replayed.
FROZEN_SETS = frozen_sets()
FROZEN_SET = FROZEN_SETS[-1] if FROZEN_SETS else DIRECTORY / "set_v1.json"
SET_PATH = FROZEN_SET if FROZEN_SET.exists() else DEVELOPMENT_SET


class MutatorError(Exception):
    """One mutator could not be applied. Carries the id it is attributed to."""

    def __init__(self, mutator_id: str, cause: str):
        self.mutator_id = mutator_id
        self.cause = cause
        super().__init__(f"{mutator_id}: {cause}")


class MutatorSetError(Exception):
    """A mutator set is unreadable, unfrozen, or not the one the run names."""


def language_of(path: str, default: str = "mlir") -> str:
    """Return the input language one test path is written in, by its extension."""
    return _LANGUAGE_BY_SUFFIX.get(Path(path).suffix, default)


def set_sha256(path=None) -> str:
    """Return the SHA-256 of a mutator set's bytes, which is what a run names."""
    return hashlib.sha256(Path(path or SET_PATH).read_bytes()).hexdigest()


def load_set(path=None, *, expected_sha: Optional[str] = None) -> dict:
    """Load one mutator set and refuse it unless it is the one the run names.

    8.1's rule 1, at the one place a set enters the arm: the digest is computed
    over the file's bytes and compared to `RunManifest.mutator_set_sha` BEFORE
    any mutant is produced, so a set edited after registration stops the arm
    rather than quietly changing the baseline. A set that declares itself
    unfrozen is refused outright once a run names a digest, which is what keeps
    the development set out of a campaign (FR-05.2).

    Returns:
        dict, the set document, with a "path" and a "sha256" key added from the
        run rather than from the file.
    Worker:
        the caller's; it reads one committed file and runs no process.
    Raises:
        MutatorSetError when the file is missing or malformed, when its digest
        is not *expected_sha*, or when a run names a digest for a set whose
        "frozen" field is false.
    """
    target = Path(path or SET_PATH)
    try:
        raw = target.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise MutatorSetError(f"{target}: {error}") from None
    if not isinstance(document, dict) or not isinstance(document.get("mutators"), list):
        raise MutatorSetError(f"{target}: a set is an object carrying a mutators array (8.1)")
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None and digest != expected_sha:
        raise MutatorSetError(
            f"{target} hashes to {digest}, and the run names {expected_sha}: "
            "the mutator set is frozen for the whole campaign (FR-05.2, 8.1)")
    if expected_sha is not None and document.get("frozen") is False:
        raise MutatorSetError(
            f"{target} declares itself not frozen and cannot run a registered "
            "campaign: synthesise and freeze a set first (8.3, FR-05.2)")
    return {**document, "path": str(target), "sha256": digest}


def _lookup(mutator_id: str, mutator_set: dict) -> dict:
    """Return one mutator by id, or raise MutatorError for an unknown one."""
    for mutator in mutator_set.get("mutators", []):
        if mutator.get("id") == mutator_id:
            return mutator
    raise MutatorError(mutator_id, "no such mutator in the set")


def _integer_span(match) -> tuple:
    """Return the absolute span of the first integer group of *match*, sign included."""
    spans = [match.span(index) for index, value in enumerate(match.groups(), 1)
             if value and _INTEGER.fullmatch(value)]
    if not spans:
        if _INTEGER.fullmatch(match.group(0)):
            spans = [match.span(0)]
        else:
            raise ValueError("no integer group to operate on")
    start, end = spans[0]
    if start > match.start() and match.string[start - 1] == "-":
        start -= 1
    return start, end


def _numeric(match, operation: str, rng: random.Random) -> str:
    """Apply one numeric operation to the first integer of *match*, in its text."""
    start, end = _integer_span(match)
    value = int(match.string[start:end])
    if operation == "flip":
        new = -value
    elif operation == "zero":
        new = 0
    elif operation == "max":
        new = MAX_INT
    else:                                   # off_by_one
        new = value + rng.choice((1, -1))
    return f"{match.string[:start]}{new}{match.string[end:]}"


def _sequence(items: list, operation: str, index: int) -> list:
    """Apply one sequence operation at *index* of a line or token list."""
    out = list(items)
    if operation == "duplicate":
        out.insert(index + 1, out[index])
    elif operation == "delete":
        del out[index]
    elif index + 1 < len(out):              # swap
        out[index], out[index + 1] = out[index + 1], out[index]
    return out


def apply(mutator_id: str, text: str, seed_int: int, *,
          mutator_set: Optional[dict] = None,
          argv: Optional[list] = None) -> tuple:
    """Apply one frozen mutator to one input text, deterministically.

    Returns:
        (mutant_text, argv) where argv is None unless the mutator declares
        mutates_argv, in which case it is the replacement argument vector
        (FR-05.5). mutant_text equal to *text* is a no-op and the caller counts
        it (FR-05.6).
    Worker:
        pure; `random.Random(seed_int)` is the only source of choice and the
        module-level generator is never seeded (FR-05.3).
    Raises:
        MutatorError(mutator_id, cause) for an unknown id, a pattern that will
        not compile, or a replacement operation the mutator's kind does not
        allow. `mutate_seed` catches it, counts it against the id and continues.
    """
    mutator = _lookup(mutator_id, mutator_set if mutator_set is not None else load_set())
    kind = mutator.get("kind")
    replacement = mutator.get("replacement", "")
    rng = random.Random(seed_int)
    try:
        pattern = re.compile(mutator.get("pattern", ""))
    except re.error as error:
        raise MutatorError(mutator_id, f"pattern will not compile: {error}") from None

    if kind == "text":
        if replacement in SEQUENCE_OPERATIONS:
            raise MutatorError(mutator_id, f"{replacement} is not a text operation")
        matches = list(pattern.finditer(text))
        if not matches:
            return text, None
        match = matches[rng.randrange(len(matches))]
        if replacement in NUMERIC_OPERATIONS:
            try:
                return _numeric(match, replacement, rng), None
            except ValueError as error:
                raise MutatorError(mutator_id, str(error)) from None
        return f"{text[:match.start()]}{match.expand(replacement)}{text[match.end():]}", None

    if kind == "line":
        if replacement not in SEQUENCE_OPERATIONS:
            raise MutatorError(mutator_id, f"{replacement} is not a line operation")
        lines = text.splitlines(keepends=True)
        candidates = [index for index, line in enumerate(lines) if pattern.search(line)]
        if not candidates:
            return text, None
        index = candidates[rng.randrange(len(candidates))]
        if replacement == "duplicate" and not lines[index].endswith("\n"):
            lines[index] += "\n"
        return "".join(_sequence(lines, replacement, index)), None

    if kind == "argv":
        if not mutator.get("mutates_argv"):
            raise MutatorError(mutator_id, "an argv mutator declares mutates_argv (FR-05.5)")
        if argv is None:
            raise MutatorError(mutator_id, "an argv mutator needs the seed's argument vector")
        candidates = [index for index, token in enumerate(argv) if pattern.search(token)]
        if not candidates:
            return text, None
        index = candidates[rng.randrange(len(candidates))]
        if replacement in SEQUENCE_OPERATIONS:
            return text, _sequence(list(argv), replacement, index)
        mutated = list(argv)
        mutated[index] = replacement
        return text, mutated

    raise MutatorError(mutator_id, f"kind {kind!r} is not one of {KINDS}")


def eligible(mutator_set: dict, language: str) -> list:
    """Return the set's mutators for one language, sorted by id (8.2 rule 2).

    Sorted by id and not by position, so which mutator a seed gets does not
    depend on the order the synthesis happened to write the JSON document in.
    """
    return sorted((mutator for mutator in mutator_set.get("mutators", [])
                   if mutator.get("language") in (language, "any")),
                  key=lambda mutator: mutator.get("id", ""))


def mutant_seed_int(seed_sha: str, test_path: str, mutator_id: str,
                    iteration: int, index: int) -> int:
    """Derive one mutant's RNG seed, which the ProbeSpec records (8.2 rule 5).

    Derived rather than drawn, so the whole arm is reproducible from the
    `SeedRecord` and the frozen set with no state carried between calls, and
    `random.seed()` is never called on the module-level generator (FR-05.3).

    MASKED TO 63 BITS (W-19b finding 2). `int.from_bytes(digest[:8], "big")` is
    an UNSIGNED 64-bit integer and SQLite's INTEGER is SIGNED, so `write_probe`
    raised `OverflowError` out of `SQLiteNode.execute` - outside `drive_probe`'s
    own `try`, so it propagated through `drive_seed` and `campaign_drive` and
    stopped the whole campaign. Measured: 9998 of 20000 derivations exceeded
    `2**63 - 1`, both committed mutation `ProbeSpec` fixtures were already over
    it, and the expected time to failure in a pilot's mutation arm was the
    SECOND probe. The mask lands before A7 freezes any set, so the mutation
    baseline is defined once, by the masked derivation.
    """
    digest = hashlib.sha256(
        f"{seed_sha}|{test_path}|{mutator_id}|{iteration}|{index}".encode("utf-8"))
    return int.from_bytes(digest.digest()[:8], "big") & SEED_INT_MASK


def mutate_seed(seed, iteration: int, cap: int, mutator_set: dict,
                argv: Optional[list] = None) -> tuple:
    """Produce up to *cap* mutants for one seed, deterministically.

    8.2's six rules and nothing else: EVERY changed test file supplies a
    starting input in `test_paths` order (FR-05.1); the eligible mutators are
    those of the file's language or of `any`, sorted by id; exactly ONE mutator
    application per mutant, so a firing is attributable to a single mutator;
    the cap is taken round-robin across the files and then across the sorted
    mutators; the RNG seed is derived; a no-op is counted and produces nothing.

    Returns:
        (mutants, no_ops, failures), where each mutant is
        (mutator_id, source_test_path, mutant_text, seed_int, argv) with argv
        None unless the mutator declares mutates_argv, and failures maps a
        mutator id to the number of times it raised (FR-05.6, FR-05.7).
    Worker:
        pure; no worker resource and no model (FR-05.1, FR-05.3). It reads
        `seed.test_files` and never the filesystem.
    Raises:
        nothing. A mutator that raises is caught, counted against its id, and
        skipped (FR-05.7).
    """
    files = [(path, seed.test_files[path]) for path in seed.test_paths
             if path in seed.test_files]
    plans = [(path, text, eligible(mutator_set, language_of(path)))
             for path, text in files]
    mutants: list = []
    failures: dict = {}
    no_ops = 0
    index = 0
    depth = max((len(plan[2]) for plan in plans), default=0)
    for position in range(depth):
        for path, text, choices in plans:
            if len(mutants) >= cap:
                return mutants, no_ops, failures
            if position >= len(choices):
                continue
            mutator_id = choices[position]["id"]
            seed_int = mutant_seed_int(seed.seed_sha, path, mutator_id,
                                       iteration, index)
            index += 1
            try:
                mutated, new_argv = apply(mutator_id, text, seed_int,
                                          mutator_set=mutator_set, argv=argv)
            except MutatorError:
                failures[mutator_id] = failures.get(mutator_id, 0) + 1
                continue
            if mutated == text and new_argv is None:
                no_ops += 1
                continue
            mutants.append((mutator_id, path, mutated, seed_int, new_argv))
    return mutants, no_ops, failures


__all__ = ["DEVELOPMENT_SET", "FROZEN_SET", "FROZEN_SETS", "ID", "KINDS",
           "LANGUAGES", "MAX_INT", "NAMED_OPERATIONS", "NUMERIC_OPERATIONS",
           "SEED_INT_MASK", "SEQUENCE_OPERATIONS", "SET_PATH", "MutatorError",
           "MutatorSetError", "apply", "eligible", "frozen_sets", "language_of",
           "load_set", "mutant_seed_int", "mutate_seed", "set_sha256"]
