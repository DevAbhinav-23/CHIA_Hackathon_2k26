"""A4's frozen mutator set: the loader, the digest check and the runner (8.1)."""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Optional

#: 8.1's four languages.
LANGUAGES = ("mlir", "fir", "sv", "any")

#: What a derived mutant seed is masked to (W-19b finding 2).
SEED_INT_MASK = 2 ** 63 - 1

#: 8.1's `kind` values, and the seven named replacement operations.
KINDS = ("text", "line", "argv")
NUMERIC_OPERATIONS = ("flip", "zero", "max", "off_by_one")
SEQUENCE_OPERATIONS = ("duplicate", "delete", "swap")
NAMED_OPERATIONS = NUMERIC_OPERATIONS + SEQUENCE_OPERATIONS

#: What `max` writes.
MAX_INT = 2 ** 31 - 1

#: 8.1's id rule, checked here and again by the synthesis (8.3 step 4).
ID = re.compile(r"^[a-z0-9]+(\.[a-z0-9_]+){2,}$")

_INTEGER = re.compile(r"\d+")
_LANGUAGE_BY_SUFFIX = {".mlir": "mlir", ".fir": "fir", ".sv": "sv",
                       ".svh": "sv", ".v": "sv"}

DIRECTORY = Path(__file__).resolve().parent
DEVELOPMENT_SET = DIRECTORY / "set_dev.json"

#: `set_v<n>.json`, and nothing else.
_FROZEN_NAME = re.compile(r"^set_v(\d+)\.json$")


def frozen_sets() -> list:
    """Every frozen set beside this module, oldest version first (8.1)."""
    found = [(int(match.group(1)), path) for path in DIRECTORY.glob("set_v*.json")
             for match in [_FROZEN_NAME.match(path.name)] if match]
    return [path for _version, path in sorted(found)]


#: The frozen set the campaign runs.
FROZEN_SETS = frozen_sets()
FROZEN_SET = FROZEN_SETS[-1] if FROZEN_SETS else DIRECTORY / "set_v1.json"
SET_PATH = FROZEN_SET if FROZEN_SET.exists() else DEVELOPMENT_SET


class MutatorError(Exception):
    """One mutator could not be applied."""

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
    """Load one mutator set and refuse it unless it is the one the run names."""
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
    """Apply one frozen mutator to one input text, deterministically."""
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
    """Return the set's mutators for one language, sorted by id (8.2 rule 2)."""
    return sorted((mutator for mutator in mutator_set.get("mutators", [])
                   if mutator.get("language") in (language, "any")),
                  key=lambda mutator: mutator.get("id", ""))


def mutant_seed_int(seed_sha: str, test_path: str, mutator_id: str,
                    iteration: int, index: int) -> int:
    """Derive one mutant's RNG seed, which the ProbeSpec records (8.2 rule 5)."""
    digest = hashlib.sha256(
        f"{seed_sha}|{test_path}|{mutator_id}|{iteration}|{index}".encode("utf-8"))
    return int.from_bytes(digest.digest()[:8], "big") & SEED_INT_MASK


def mutate_seed(seed, iteration: int, cap: int, mutator_set: dict,
                argv: Optional[list] = None) -> tuple:
    """Produce up to *cap* mutants for one seed, deterministically."""
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
