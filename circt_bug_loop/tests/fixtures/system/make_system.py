"""Record `tests/fixtures/system/seeds.json`, the tier-3 tier's eight seeds (W-19b).

`04-Test-Plan.md` §13's rule - "`make_fixtures.py` is committed beside them" -
and §0.6 rule 2's production rule as far as it can be kept here: every derived
field below comes from A1's OWN pure functions (`corpus.extract_run_lines`,
`corpus.normalise_run_line`, `corpus.dialect_buckets`) run over committed bytes,
and each record is written only after `contract.validate` accepts it.

WHAT IS REAL AND WHAT IS NOT, stated rather than hidden. These are NOT
`corpus.build_corpus`'s output. A1 mines a blobless clone at
`budget.yaml`'s `corpus_head_sha`; this host's clone is at another commit and
the six crash seeds' blobs are not fetched, so mining them is a network task and
not a fixture. Instead:

  * the SIX crash seeds are assembled from two committed sources - W-09's
    recorded failure set (`tests/fixtures/crashes/<class>_<nn>/`, which holds the
    seed's own test input, its argv and its commit) and the committed 187-seed
    corpus (`tests/fixtures/corpus/filtered_187.json`, which holds the subject,
    the dates, the paths and the SDK pin). Every RUN:-derived field is A1's own
    normalisation of the fixture's own bytes.
  * the TWO ordinary seeds are copied UNCHANGED from
    `tests/fixtures/corpus/seeds/`, which is W-05's own recording of
    `build_corpus` against the blobless clone. Nothing here touches them.
  * `SeedRecord.diff` is a REQUIRED field the clone alone can supply, and it is
    NOT mined here. The six carry `DIFF_NOT_MINED` and say so in the value
    itself, so no reader can take one for A1's. Nothing the tier-3 tests run
    reads it: the only consumer is A3's prompt (§7.2), and `--generator
    recorded` does not run A3.

Run it as a program, from the repository root:

    PYTHONPATH=. python circt_bug_loop/tests/fixtures/system/make_system.py
"""
from __future__ import annotations

import json
from pathlib import Path

from circt_bug_loop import corpus
from circt_bug_loop.contract.schema import SeedRecord, to_json, validate

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
CRASHES = FIXTURES / "crashes"
CORPUS = FIXTURES / "corpus"

#: The value `SeedRecord.diff` carries for a seed assembled here. It is a
#: sentence and not an empty string on purpose: a reader who greps the fixture
#: finds the reason, and a consumer that substituted it into a prompt would
#: substitute the reason too.
DIFF_NOT_MINED = ("DIFF_NOT_MINED: this seed was assembled by "
                  "tests/fixtures/system/make_system.py from the committed "
                  "crash fixture and the committed corpus, not by "
                  "corpus.build_corpus over a clone. The commit's diff needs "
                  "the clone's blobs and is not part of this fixture.")

#: The two ordinary seeds, W-05's own recordings, copied unchanged. Both are
#: `circt-opt` on a `.mlir` test with an exact SDK pin, which is what makes them
#: ordinary: neither names a crash and neither is in W-09's set.
ORDINARY = ("nine_test_files.json", "not_wrapper.json")


def candidates() -> dict:
    """The committed 187-seed corpus, by seed SHA."""
    document = json.loads((CORPUS / "filtered_187.json").read_text(encoding="utf-8"))
    return {row["sha"]: row for row in document["candidates"]}


def crash_seed(directory: Path, row: dict) -> SeedRecord:
    """One `SeedRecord` for one of W-09's six recorded failures.

    *directory* is the fixture's own, and *row* its `filtered_187.json` entry.
    The RUN: lines are read out of the fixture's `input.mlir` and normalised by
    A1's own function, so the tool, the argv template, the polarity and the
    shape are the ones a mined seed would carry.

    Returns:
        SeedRecord, validated.
    Raises:
        ContractError when the assembled record is not a valid one; ValueError
        when the fixture's input carries no RUN: line, which W-09's set does.
    """
    commit = json.loads((directory / "commit.json").read_text(encoding="utf-8"))
    text = (directory / "input.mlir").read_text(encoding="utf-8")
    test_path = next((p for p in row["test"] if p.endswith(".mlir")), row["test"][0])

    lines = corpus.extract_run_lines(text)
    if lines:
        normalised = [corpus.normalise_run_line(line) for line in lines]
        tools = [tool for tool, *_ in normalised]
        argv_template = [argv for _, argv, *_ in normalised]
        polarity = [p for _, _, p, *_ in normalised]
        shape = [s for _, _, _, s, *_ in normalised]
    else:
        # Two of W-09's six are a SPLIT PIECE of their seed's test file - the
        # attempts recorded as "piece 1 of 9" and "piece 8 of 19" - so the piece
        # carries no RUN: line of its own. W-09's own recorded argv is what its
        # runner executed against that piece, and it is used here verbatim, with
        # the input file put back as lit's `%s`: it is the same normalisation,
        # already performed, rather than a second guess at one.
        recorded = json.loads((directory / "argv.json").read_text(encoding="utf-8"))
        tools = [recorded[0]]
        argv_template = [["%s" if a == "input.mlir" else a for a in recorded[1:]]]
        lines = [f"{' '.join(tools + argv_template[0])}"]
        polarity, shape = ["expect_zero"], ["plain"]
    bucket, unmerged = corpus.dialect_buckets(test_path)
    record = SeedRecord(
        seed_sha=commit["parent_of"], parent_sha=commit["circt_sha"],
        subject=row["subject"], committed_date_utc=row["date"],
        source_paths=list(row["src"]), test_paths=[test_path],
        llvm_pin=commit["llvm_pin"],
        sdk_tag=row["tag"] if row["exact"] else None, sdk_exact=bool(row["exact"]),
        bumps_away=row["bumps"], entry_tool=tools[0],
        dialect_bucket=bucket, dialect_bucket_unmerged=unmerged,
        run_lines=list(lines), argv_template=argv_template,
        polarity=polarity, shape=shape,
        diff=DIFF_NOT_MINED, test_files={test_path: text},
        corpus_head_sha=json.loads(
            (CORPUS / "filtered_187.json").read_text(encoding="utf-8"))["corpus_head_sha"])
    validate(record)
    return record


def main() -> None:
    """Write `seeds.json`: the six, then the two, in that order."""
    rows = candidates()
    seeds = [crash_seed(directory, rows[
                 json.loads((directory / "commit.json").read_text(
                     encoding="utf-8"))["parent_of"]])
             for directory in sorted(CRASHES.iterdir()) if directory.is_dir()]
    for name in ORDINARY:
        document = json.loads((CORPUS / "seeds" / name).read_text(encoding="utf-8"))
        record = SeedRecord(**document)
        validate(record)
        seeds.append(record)
    (HERE / "seeds.json").write_text(
        "[\n" + ",\n".join(to_json(seed) for seed in seeds) + "\n]\n",
        encoding="utf-8")
    print(f"{len(seeds)} seeds -> {HERE / 'seeds.json'}")
    for seed in seeds:
        print(f"  {seed.seed_sha[:12]} {seed.entry_tool:16} "
              f"{len(seed.run_lines)} run line(s)  {seed.subject[:56]}")


if __name__ == "__main__":
    main()
