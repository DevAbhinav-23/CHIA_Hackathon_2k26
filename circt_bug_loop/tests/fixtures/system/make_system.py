"""Record `tests/fixtures/system/seeds.json`, the tier-3 tier's eight seeds (W-19b)."""
from __future__ import annotations

import json
from pathlib import Path

from circt_bug_loop import corpus
from circt_bug_loop.contract.schema import SeedRecord, to_json, validate

HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent
CRASHES = FIXTURES / "crashes"
CORPUS = FIXTURES / "corpus"

#: The value `SeedRecord.diff` carries for a seed assembled here.
DIFF_NOT_MINED = ("DIFF_NOT_MINED: this seed was assembled by "
                  "tests/fixtures/system/make_system.py from the committed "
                  "crash fixture and the committed corpus, not by "
                  "corpus.build_corpus over a clone. The commit's diff needs "
                  "the clone's blobs and is not part of this fixture.")

#: The two ordinary seeds, W-05's own recordings, copied unchanged.
ORDINARY = ("nine_test_files.json", "not_wrapper.json")


def candidates() -> dict:
    """The committed 187-seed corpus, by seed SHA."""
    document = json.loads((CORPUS / "filtered_187.json").read_text(encoding="utf-8"))
    return {row["sha"]: row for row in document["candidates"]}


def crash_seed(directory: Path, row: dict) -> SeedRecord:
    """One `SeedRecord` for one of W-09's six recorded failures."""
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
        # Two of W-09's six are a SPLIT PIECE of their seed's test file.
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
