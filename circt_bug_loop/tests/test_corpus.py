"""`corpus.py` (A1, F-01): the mine, the `RUN:` normalisation and the SDK map.

`04-Test-Plan.md` §1's `corpus` table. The tier-0 half runs against the
recorded fixtures of `fixtures/corpus/`, every one of which is a real `RUN:`
line of a real CIRCT test file or a real `SeedRecord` the builder emitted; each
test names the file it came from. The tier-1 half mines the blobless clone
reset to `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` and reproduces FR-01.1's
counts, and skips cleanly when no such clone is at hand.

`fixtures/corpus/README.md` records where every fixture came from and how to
make the pinned clone the tier-1 tests want.
"""
import json
import os
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path

import pytest

from circt_bug_loop import corpus
from circt_bug_loop.contract import schema

#: This module's own fixture root. Reached from `__file__` and never above it,
#: which is `conftest.py`'s rule: the flow lives at two depths (`03-LLD.md`
#: §1.4) and only paths inside the test tree are the same in both.
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "corpus"
RUNLINES = FIXTURES / "runlines"

#: PIN §1's repo state, which is where `analysis/pin_window_raw.json` was
#: computed and the one HEAD at which FR-01.1's counts are asserted rather than
#: recorded.
CORPUS_HEAD_SHA = "d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2"
SINCE = "2024-09-11"

#: `budget.yaml`'s `artefact_inline_cap_bytes` (`04-Test-Plan.md` T-U-corpus-23).
INLINE_CAP_BYTES = 262144

#: Calling a `@ChiaFunction` locally runs it in-process, but CHIA's profiler
#: still asks Ray whether a collector actor exists, and that question starts a
#: local Ray instance the first time. Ray's own startup emits a `FutureWarning`
#: about accelerator environment variables and leaks two `/dev/null` handles
#: that surface later as `ResourceWarning`s, which pytest re-raises as
#: `PytestUnraisableExceptionWarning`; under `-W error` all three would fail
#: whichever tier-1 test happened to call a node first. They are Ray's notices
#: about Ray, so the node-calling tests ignore exactly those three classes and
#: nothing else. No test here opens a file of its own.
_RAY_WARNING = pytest.mark.filterwarnings(
    "ignore::FutureWarning", "ignore::ResourceWarning",
    "ignore::pytest.PytestUnraisableExceptionWarning")


def logical_line(name: str) -> str:
    """The one logical `RUN:` line of the named `runlines/` fixture."""
    text = (RUNLINES / f"{name}.txt").read_text(encoding="utf-8")
    lines = corpus.extract_run_lines(text)
    assert len(lines) == 1, f"{name}.txt holds {len(lines)} logical lines"
    return lines[0]


def recorded_seed(name: str) -> schema.SeedRecord:
    """One recorded `SeedRecord` of `seeds/`, read back through the contract."""
    text = (FIXTURES / "seeds" / f"{name}.json").read_text(encoding="utf-8")
    return schema.from_json(text, schema.SeedRecord)


def filtered_187() -> list[dict]:
    """The 187 rows derived from `analysis/pin_window_raw.json` by PIN §2."""
    return json.loads((FIXTURES / "filtered_187.json").read_text(encoding="utf-8"))[
        "candidates"]


# --------------------------------------------------------------------------
# Tier 0: the pure functions, against real RUN: lines.
# --------------------------------------------------------------------------

@pytest.mark.t0
def test_T_U_corpus_06():
    """T-U-corpus-06 (FR-01.2, FR-01.3): the acceptance line, verbatim.

    `test/Conversion/HWToLLVM/convert_aggregates.mlir:1` at `f2b15a44ec70`, the
    commit FR-01.2's acceptance criterion names. Two notes, both errata
    candidates and neither a defect here: the real line carries TWO spaces
    before `--convert-hw-to-llvm`, where the requirement quotes one, so the
    verbatim text is asserted against the file rather than against the prose;
    and `f2b15a44ec70` is one of PIN's 1,103 shape candidates and NOT one of
    the 187, its subject "[HWToLLVM] Use correctly typed constant attributes"
    carrying no bug-ish word.
    """
    line = logical_line("pipe_plain")
    assert line == ("circt-opt %s --split-input-file  "
                    "--convert-hw-to-llvm=spill-arrays-early=false | FileCheck %s")
    tool, argv, polarity, shape, env, notes = corpus.normalise_run_line(line)
    assert tool == "circt-opt" and argv == [
        "%s", "--split-input-file", "--convert-hw-to-llvm=spill-arrays-early=false"]
    assert (polarity, shape, env) == ("expect_zero", "plain", {})
    assert notes["dropped_tail"] == "| FileCheck %s"
    # FR-01.3 reads the tool off the line. The source path of this commit is
    # `lib/Conversion/HWToLLVM/HWToLLVM.cpp` and nothing here looks at it.
    assert corpus.classify_entry_tool(corpus.entry_tool_of_line(line)) == "circt-opt"


@pytest.mark.t0
def test_T_U_corpus_07():
    """T-U-corpus-07 (FR-01.10 step 1): the `not` wrapper and `not --crash`.

    Both fixtures are `test/Conversion/ExportVerilog/verilog-errors-prop.mlir`
    lines 3 and 10, which are the corpus's only two `not`-wrapped lines (M1: 2
    lines on 1 seed). `not --crash` occurs nowhere in the corpus, so that third
    case is constructed inline rather than pretended to be recorded.
    """
    for name, expected in (("not_plain", ["-export-verilog", "%s"]),
                           ("not_quoted", ["-export-split-verilog=dir-name=%t",
                                           "%s"])):
        tool, argv, polarity, _shape, _env, notes = corpus.normalise_run_line(
            logical_line(name))
        assert (tool, argv, polarity) == ("circt-opt", expected, "expect_nonzero")
        assert notes["not_crash"] is False

    _t, _a, polarity, _s, _e, _n = corpus.normalise_run_line(
        logical_line("pipe_plain"))
    assert polarity == "expect_zero"

    tool, argv, polarity, _shape, _env, notes = corpus.normalise_run_line(
        "not --crash circt-opt %s --lower-seq-to-sv")
    assert (tool, argv) == ("circt-opt", ["%s", "--lower-seq-to-sv"])
    assert polarity == "expect_nonzero" and notes["not_crash"] is True


@pytest.mark.t0
def test_T_U_corpus_08():
    """T-U-corpus-08 (FR-01.10 step 2): the `env` wrapper and its assignments.

    `integration_test/circt-test/basic-circt-bmc.mlir:1`, the corpus's own
    spelling of the wrapper and the only `env` line in either test tree. It
    spells the two wrappers in the order `env ... not ...`, which is the
    reverse of FR-01.10's step order, so this fixture is also what says the
    stripping is order-free while the recording is not.
    """
    tool, argv, polarity, shape, env, _notes = corpus.normalise_run_line(
        logical_line("env"))
    assert env == {"Z3LIB": "%libz3"}
    assert polarity == "expect_nonzero"
    assert tool == "circt-test" and shape == "plain"
    assert argv[:2] == ["%S/basic.mlir", "-d"]
    assert corpus.classify_entry_tool(tool) == "other"


@pytest.mark.t0
def test_T_U_corpus_09():
    """T-U-corpus-09 (FR-01.10 step 3): `split-file`, the corpus's only one.

    `test/Dialect/Arc/inline-arcs.mlir:1`. M1 measured exactly 1 such line over
    the corpus and this is it. Erratum candidate: after the wrapper is dropped
    the remainder, `%s %t`, is not a tool invocation at all, so `tool` is `%s`
    and the argv is meaningless; the seed's real invocations are the sibling
    `RUN:` lines that read `%t/<part>`. `shape=split_file` is the flag that
    says so, and is what FR-01.10 asks this step to record.
    """
    tool, argv, _polarity, shape, _env, _notes = corpus.normalise_run_line(
        logical_line("splitfile"))
    assert shape == "split_file"
    assert (tool, argv) == ("%s", ["%t"])


@pytest.mark.t0
def test_T_U_corpus_10():
    """T-U-corpus-10 (FR-01.10 step 4): the first UNQUOTED pipe, and no other.

    `pipe_plain` is the acceptance line; `pipe_quoted` is
    `test/Dialect/FIRRTL/Reduction/issue-3555.mlir:3`, whose first `|` sits
    inside a single-quoted `/bin/sh -c` script and whose second is the real
    `| FileCheck %s`. A scanner that split on the first `|` would truncate the
    line mid-argument and lose `--keep-best=0 --include root-port-pruner`.
    M1: 234 of 331 lines carry a pipe.
    """
    _t, _a, _p, _s, _e, notes = corpus.normalise_run_line(logical_line("pipe_plain"))
    assert notes["dropped_tail"] == "| FileCheck %s"

    line = logical_line("pipe_quoted")
    tool, argv, _polarity, shape, _env, notes = corpus.normalise_run_line(line)
    assert tool == "circt-reduce" and shape == "plain"
    assert notes["dropped_tail"] == "| FileCheck %s"
    assert argv[-3:] == ["--keep-best=0", "--include", "root-port-pruner"]
    assert any("| grep -q" in token for token in argv), (
        "the quoted pipe survives inside its own argument")


@pytest.mark.t0
def test_T_U_corpus_11():
    """T-U-corpus-11 (FR-01.10 step 5): `%s`, `%t` and `%S`.

    Three real lines: `test/circt-verilog/redundant-files.sv:1` at seed
    `9f021153418e`, the one corpus line carrying `%s` twice before the pipe;
    `test/Dialect/Arc/insert-runtime.mlir:1`; and
    `test/Dialect/LLHD/Transforms/mem2reg-scaling.mlir:7`, which carries `%S`
    and `%t` and no `%s` (M1: 52 lines use `%t`, 10 use `%S`). Unbound, the
    three stay as themselves so `argv_template` remains a template; bound, the
    substitution is textual, so `%t.1.mlir` becomes `<probe dir>/t.1.mlir`.
    """
    _t, argv, _p, _s, _e, notes = corpus.normalise_run_line(
        logical_line("subst_s_twice"))
    assert argv == ["%s", "%s"] and notes["substitutions"] == {"%s": 2}

    _t, argv, _p, _s, _e, notes = corpus.normalise_run_line(logical_line("subst_s"))
    assert argv[0] == "%s" and notes["substitutions"] == {"%s": 1}

    line = logical_line("subst_S")
    _t, argv, _p, _s, _e, notes = corpus.normalise_run_line(line)
    assert notes["substitutions"] == {"%S": 1, "%t": 1}
    assert argv[0] == "%S/mem2reg-scaling.py"

    subs = {"s": "/probe/input.mlir", "t": "/probe/t", "S": "/probe"}
    _t, argv, _p, _s, _e, notes = corpus.normalise_run_line(line, subs=subs)
    assert argv[0] == "/probe/mem2reg-scaling.py"
    assert argv[-1] == "/probe/t.1.mlir"
    assert notes["substitutions"] == {"%S": 1, "%t": 1}

    _t, argv, _p, _s, _e, _n = corpus.normalise_run_line(
        logical_line("subst_s_twice"), subs=subs)
    assert argv == ["/probe/input.mlir", "/probe/input.mlir"]


@pytest.mark.t0
@pytest.mark.parametrize("name,construct", [
    ("unsupported_semicolon", ";"),
    ("unsupported_and", "&&"),
    ("unsupported_backtick", "`"),
    ("unsupported_dollarparen", "$("),
    ("unsupported_brace", "%{"),
])
def test_T_U_corpus_12(name: str, construct: str):
    """T-U-corpus-12 (FR-01.10 step 6): the five shell constructs.

    Two are real: `&&` from
    `test/Conversion/ExportVerilog/verilog-errors-prop.mlir:9` (M1: 5 lines)
    and `;` from `test/Dialect/Arc/insert-runtime.mlir:2`. Three are
    constructed, because no `RUN:` line in either test tree at `b792c772`
    carries a backtick, a `$(` or a `%{` (M1 measured 0 for `%{`; the other two
    were searched for here and found nowhere).

    Erratum candidate on the `;` case: that line's semicolon sits inside a
    quoted option value, `extra-args='debug;bar'`, and the line is perfectly
    runnable. FR-01.10 step 6 says "still carrying a `;`" and this
    implementation says exactly that, so the line is rejected conservatively;
    the cost is one seed, `27fdf5525cdc` keeping its other lines.
    """
    _tool, _argv, _polarity, shape, _env, notes = corpus.normalise_run_line(
        logical_line(name))
    assert shape == "unsupported"
    assert notes["unsupported_construct"] == construct


@pytest.mark.t0
def test_T_U_corpus_13():
    """T-U-corpus-13 (FR-01.10 step 0): lit's `\\` continuations.

    `test/Conversion/ImportVerilog/proximate-source-locations.sv:1-2`, two
    physical lines that are one logical one. The verbatim `run_lines` entry
    keeps both, because FR-01.2 says verbatim and a continuation has no
    single-line spelling; step 0 folds them and records how many it folded.
    """
    text = (RUNLINES / "cont.txt").read_text(encoding="utf-8")
    assert len(text.splitlines()) == 2
    lines = corpus.extract_run_lines(text)
    assert len(lines) == 1 and "\n" in lines[0] and "\\" in lines[0]

    tool, argv, _polarity, shape, _env, notes = corpus.normalise_run_line(lines[0])
    assert notes["lines_joined"] == 2
    assert (tool, shape) == ("circt-verilog", "plain")
    assert argv == ["--ir-moore", "-mlir-print-debuginfo", "%s"]
    assert notes["dropped_tail"] == "| FileCheck %s --check-prefix=DEFAULT"


@pytest.mark.t0
def test_T_U_corpus_14():
    """T-U-corpus-14 (FR-01.10): `strip_probe_only_options`, both spellings.

    The bare pair is taken off the acceptance line itself; the `=`-valued pair
    is constructed from §4.2's verified `--split-input-file[=<string>]` and
    `--verify-diagnostics=<value>`. M1's reach: 29.9% and 28.3% of seeds.
    """
    _t, argv, _p, _s, _e, _n = corpus.normalise_run_line(logical_line("pipe_plain"))
    kept, removed = corpus.strip_probe_only_options(argv)
    assert kept == ["%s", "--convert-hw-to-llvm=spill-arrays-early=false"]
    assert removed == ["--split-input-file"]

    kept, removed = corpus.strip_probe_only_options(
        ["%s", "--split-input-file=// -----", "--verify-diagnostics=only-expected",
         "--verify-diagnostics", "--canonicalize"])
    assert kept == ["%s", "--canonicalize"]
    assert removed == ["--split-input-file=// -----",
                       "--verify-diagnostics=only-expected", "--verify-diagnostics"]

    kept, removed = corpus.strip_probe_only_options(["%s", "--split-input-files"])
    assert kept == ["%s", "--split-input-files"] and removed == []


@pytest.mark.t0
@pytest.mark.parametrize("fixture,survivors,taken", [
    ("single_dash_verify", ["--sv-trace-iverilog", "%s"],
     ["-verify-diagnostics"]),
    ("single_dash_both", ["-convert-core-to-fsm", "%s"],
     ["-verify-diagnostics", "-split-input-file"]),
    ("mixed_dash", ["-pass-pipeline=builtin.module(lower-firrtl-to-hw)", "%s"],
     ["-verify-diagnostics", "--split-input-file"]),
])
def test_T_U_corpus_37(fixture: str, survivors: list, taken: list):
    """T-U-corpus-37 (FR-01.10): the single-dash spellings, on real RUN: lines.

    LLVM's option parser takes one dash or two for every long option and
    CIRCT's tests write both, so `-verify-diagnostics` is `--verify-diagnostics`
    and must be stripped alike; the same for `-split-input-file`. 46 of M1's
    331 corpus `RUN:` lines carry a single-dash form
    (`analysis/measurements/raw/m1-per-runline.csv`), which is not an edge case
    (errata W-09 #3). The three lines are recorded verbatim:

    - `single_dash_verify`: `test/Dialect/SV/sv-trace-iverilog-errors.mlir`
      line 1 at `88d9a5ad7a3a`, the seed `fixtures/crashes/assertion_02/` was
      mined from;
    - `single_dash_both`: `test/Conversion/CoreToFSM/errors.mlir` line 1 at
      `838a8bb29106`, carrying both options single-dashed;
    - `mixed_dash`: `test/Conversion/FIRRTLToHW/lower-to-hw.mlir` line 1 at
      `3f65acfd617b`, carrying one of each dash count in the same line.
    """
    _t, argv, _p, _s, _e, _n = corpus.normalise_run_line(logical_line(fixture))
    kept, removed = corpus.strip_probe_only_options(argv)
    assert kept == survivors
    assert removed == taken


@pytest.mark.t0
def test_T_U_corpus_38():
    """T-U-corpus-38 (FR-01.10): the survivor recorded in `crashes/assertion_02/`.

    That fixture's `argv.json` is what the two-spelling strip let through, and
    its `-verify-diagnostics` is what turned the diagnostic the tool emitted
    into exit status 0 at the seed commit, which is a probe whose oracle reads
    the wrong outcome. The recorded argv is fed back through the function: the
    option is taken now and nothing else is. The `=`-valued single-dash forms
    are asserted beside it against §4.2's two verified value shapes, with
    `-split-input-files` as the control that a prefix is not a match.
    """
    argv = json.loads((FIXTURES.parent / "crashes" / "assertion_02"
                       / "argv.json").read_text(encoding="utf-8"))
    assert "-verify-diagnostics" in argv
    kept, removed = corpus.strip_probe_only_options(argv[1:])
    assert kept == ["--sv-trace-iverilog", "input.mlir"]
    assert removed == ["-verify-diagnostics"]

    kept, removed = corpus.strip_probe_only_options(
        ["%s", "-split-input-file=// -----", "-verify-diagnostics=only-expected",
         "-split-input-files", "-canonicalize"])
    assert kept == ["%s", "-split-input-files", "-canonicalize"]
    assert removed == ["-split-input-file=// -----",
                       "-verify-diagnostics=only-expected"]


@pytest.mark.t0
def test_T_U_corpus_25():
    """T-U-corpus-25 (FR-01.1): PIN §2's shape filter, in both directions.

    1-2 files under `lib/` or `include/`, AND at least one ADDED or MODIFIED
    file under `test/` or `integration_test/`. A test file that is only
    DELETED does not count, which is `pin_window.py:135`'s status set.
    """
    passes = corpus.mining_filter([("M", "lib/Dialect/HW/HWOps.cpp"),
                                   ("M", "test/Dialect/HW/basic.mlir")])
    assert passes == (["lib/Dialect/HW/HWOps.cpp"], ["test/Dialect/HW/basic.mlir"])

    assert corpus.mining_filter([("M", "lib/a.cpp"), ("M", "lib/b.cpp"),
                                 ("A", "integration_test/c.mlir")]) is not None
    assert corpus.mining_filter([("M", "lib/a.cpp"), ("M", "lib/b.cpp"),
                                 ("M", "lib/c.cpp"), ("M", "test/d.mlir")]) is None
    assert corpus.mining_filter([("M", "test/d.mlir")]) is None
    assert corpus.mining_filter([("M", "lib/a.cpp")]) is None
    assert corpus.mining_filter([("M", "lib/a.cpp"), ("D", "test/d.mlir")]) is None
    assert corpus.mining_filter([("M", "lib/a.cpp"), ("R100", "test/d.mlir")]) is None


@pytest.mark.t0
def test_T_U_corpus_26():
    """T-U-corpus-26 (FR-01.1): PIN §2's subject rule, on word boundaries."""
    for subject in ("[FIRRTL] Fix a crash in the inliner",
                    "[HW] fixes #123", "Repair an assertion failure",
                    "[Moore] regression in the parser", "avoid a use-after-free",
                    "[Arc] Handle NULL operand"):
        assert corpus.subject_matches(subject), subject
    for subject in ("[HWToLLVM] Use correctly typed constant attributes",
                    "[FIRRTL] Add a prefixes option", "NFC: tidy the header",
                    "[Seq] Suffix the clock name"):
        assert not corpus.subject_matches(subject), subject


@pytest.mark.t0
def test_T_U_corpus_27():
    """T-U-corpus-27 (FR-01.4): both bucketings, rule by rule."""
    assert corpus.dialect_buckets("include/circt/Dialect/FIRRTL/FIRRTLOps.h") == (
        "FIRRTL", "include/circt/Dialect")
    assert corpus.dialect_buckets("lib/Dialect/FIRRTL/FIRRTLOps.cpp") == (
        "FIRRTL", "FIRRTL")
    assert corpus.dialect_buckets("lib/Conversion/MooreToCore/MooreToCore.cpp") == (
        "MooreToCore", "MooreToCore")
    assert corpus.dialect_buckets("include/circt/Support/LLVM.h") == (
        "Support", "Support")
    # A path shallower than three components buckets as its own last component
    # rather than raising, which is what keeps a stray `lib/Foo.cpp` countable.
    assert corpus.dialect_buckets("lib/Foo.cpp") == ("Foo.cpp", "Foo.cpp")


@pytest.mark.t0
def test_T_U_corpus_28():
    """T-U-corpus-28 (FR-01.1): `--name-status`, rename destinations included."""
    parsed = corpus.parse_name_status(
        "COMMIT aaa\n"
        "M\tlib/Dialect/HW/HWOps.cpp\n"
        "A\ttest/Dialect/HW/new.mlir\n"
        "R100\ttest/Dialect/HW/old.mlir\ttest/Dialect/HW/renamed.mlir\n"
        "\n"
        "COMMIT bbb\n"
        "D\tlib/Dialect/HW/Gone.cpp\n")
    assert parsed == {
        "aaa": [("M", "lib/Dialect/HW/HWOps.cpp"),
                ("A", "test/Dialect/HW/new.mlir"),
                ("R100", "test/Dialect/HW/renamed.mlir")],
        "bbb": [("D", "lib/Dialect/HW/Gone.cpp")]}


@pytest.mark.t0
def test_T_U_corpus_29():
    """T-U-corpus-29 (FR-09.9): the probe language is the test file's extension."""
    assert corpus.language_of("test/Dialect/HW/basic.mlir") == ".mlir"
    assert corpus.language_of("test/firtool/basic.fir") == ".fir"
    for path in ("a.sv", "a.v", "a.svh", "a.vh"):
        assert corpus.language_of(path) == ".sv"
    for path in ("a.py", "a.aig", "a.c", "noextension"):
        assert corpus.language_of(path) == "other"


@pytest.mark.t0
def test_T_U_corpus_30():
    """T-U-corpus-30 (FR-01.7): pin windows, and the nearest-tag rule.

    Constructed history, oldest pin last, because a `--first-parent` log is
    newest first. Window ids are assigned oldest to newest, so a difference IS
    a count of LLVM bumps; an exact match takes the OLDEST tag sharing the pin,
    and a non-exact one takes the nearest by bumps, ties broken by days.
    """
    from datetime import datetime, timezone

    def when(day):
        return datetime(2025, 1, day, tzinfo=timezone.utc)

    commits = [{"llvm": "cc"}, {"llvm": "bb"}, {"llvm": "bb"}, {"llvm": "aa"}]
    window_of = corpus._pin_windows(commits)
    assert window_of == {"aa": 0, "bb": 1, "cc": 2}

    tags = [{"tag": "firtool-1.0.0", "date": when(1), "llvm": "aa"},
            {"tag": "firtool-1.0.1", "date": when(2), "llvm": "aa"},
            {"tag": "firtool-1.2.0", "date": when(9), "llvm": "cc"}]
    exact = corpus._match_sdk("aa", when(3), tags, window_of)
    assert exact == {"exact": True, "bumps": None, "tag": "firtool-1.0.0"}

    near = corpus._match_sdk("bb", when(5), tags, window_of)
    assert near["exact"] is False and near["bumps"] == 1
    assert near["tag"] == "firtool-1.0.1"          # 1 bump either way, 3 d vs 4 d


@pytest.mark.t0
def test_T_U_corpus_36():
    """T-U-corpus-36 (FR-19.4): §3.1's three paragraphs on both nodes."""
    for node in (corpus.build_corpus, corpus.resolve_sites):
        doc = node.__doc__ or ""
        assert doc.splitlines()[0].endswith("."), node.__name__
        for paragraph in ("Returns:", "Worker:", "Raises:"):
            assert f"\n    {paragraph}\n" in doc, (node.__name__, paragraph)
        assert doc.index("Returns:") < doc.index("Worker:") < doc.index("Raises:")


# --------------------------------------------------------------------------
# Tier 0: the five recorded seeds.
# --------------------------------------------------------------------------

_RECORDED = ("nine_test_files", "sdk_inexact", "no_run_line", "unsupported_shape",
             "not_wrapper")


@pytest.mark.t0
@pytest.mark.parametrize("name", _RECORDED)
def test_T_U_corpus_31(name: str):
    """T-U-corpus-31 (FR-01.1): every recorded seed validates and is canonical."""
    path = FIXTURES / "seeds" / f"{name}.json"
    text = path.read_text(encoding="utf-8")
    record = schema.from_json(text, schema.SeedRecord)
    assert schema.validate(record) is None
    assert schema.to_json(record) == text, f"{path} is not canonical"
    assert record.contract_version == schema.CONTRACT_VERSION
    assert record.corpus_head_sha == CORPUS_HEAD_SHA
    assert len(record.seed_sha) == 40 and len(record.llvm_pin) == 40


@pytest.mark.t0
@pytest.mark.parametrize("name", _RECORDED)
def test_T_U_corpus_32(name: str):
    """T-U-corpus-32 (FR-01.10): the record agrees with the pure functions.

    Re-normalising each recorded verbatim `run_lines` entry reproduces that
    seed's `argv_template`, `polarity` and `shape` entry for entry, which is
    what makes the tier-0 fixtures evidence about the tier-1 mine and not only
    about themselves.
    """
    record = recorded_seed(name)
    assert len(record.run_lines) == len(record.argv_template) == len(
        record.polarity) == len(record.shape)
    for index, line in enumerate(record.run_lines):
        _tool, argv, polarity, shape, _env, _notes = corpus.normalise_run_line(line)
        assert argv == record.argv_template[index], line
        assert polarity == record.polarity[index], line
        assert shape == record.shape[index], line


@pytest.mark.t0
@pytest.mark.parametrize("name", _RECORDED)
def test_T_U_corpus_33(name: str):
    """T-U-corpus-33 (FR-01.12, FR-01.1): `test_files` and `diff`, contract 2.0.

    `test_files` is keyed and ordered by `test_paths` and never collapsed; the
    diff carries the seed's `lib/` and `include/` half and NOT its test half,
    because the test text is already in `test_files` and §7.2's prompt would
    otherwise send it twice.
    """
    record = recorded_seed(name)
    assert list(record.test_files) == record.test_paths
    assert 1 <= len(record.source_paths) <= 2
    assert all(p.startswith(("lib/", "include/")) for p in record.source_paths)
    assert all(p.startswith(("test/", "integration_test/")) for p in record.test_paths)

    changed = {line.split(" b/", 1)[1] for line in record.diff.splitlines()
               if line.startswith("diff --git ")}
    assert changed <= set(record.source_paths), changed
    for path in record.test_paths:
        assert f"diff --git a/{path}" not in record.diff


@pytest.mark.t0
def test_T_U_corpus_34():
    """T-U-corpus-34 (FR-01.7, FR-01.9, FR-01.10, FR-01.12): the five shapes.

    One assertion per recorded seed, each the reason that seed is in the set.
    """
    nine = recorded_seed("nine_test_files")
    assert len(nine.test_paths) == 9 and len(set(nine.test_paths)) == 9

    inexact = recorded_seed("sdk_inexact")
    assert inexact.sdk_exact is False
    assert inexact.sdk_tag is None and inexact.bumps_away == 1

    exact = recorded_seed("not_wrapper")
    assert exact.sdk_exact is True
    assert exact.sdk_tag is not None and exact.bumps_away is None
    assert exact.polarity.count("expect_nonzero") == 2
    assert "unsupported" in exact.shape        # its two `rm -rf %t && mkdir` lines

    empty = recorded_seed("no_run_line")
    assert empty.run_lines == [] and empty.argv_template == []
    assert empty.entry_tool == "other"

    unsupported = recorded_seed("unsupported_shape")
    assert unsupported.shape == ["unsupported"] and unsupported.run_lines


@pytest.mark.t0
def test_T_U_corpus_35():
    """T-U-corpus-35 (FR-01.1, FR-01.7): the committed acceptance set itself.

    `filtered_187.json` is derived from `analysis/pin_window_raw.json` by PIN
    §2's subject rule, so before it is used as an oracle for the mine it is
    checked against the rule it claims to encode.
    """
    rows = filtered_187()
    assert len(rows) == 187
    assert sum(1 for r in rows if r["exact"]) == 171
    inexact = [r for r in rows if not r["exact"]]
    assert len(inexact) == 16 and {r["bumps"] for r in inexact} == {1}
    for row in rows:
        assert len(row["sha"]) == 40
        assert corpus.subject_matches(row["subject"]), row["subject"]
        assert 1 <= len(row["src"]) <= 2 and len(row["test"]) >= 1
        assert all(p.startswith(("lib/", "include/")) for p in row["src"])
        assert all(p.startswith(("test/", "integration_test/")) for p in row["test"])


# --------------------------------------------------------------------------
# Tier 1: the mine itself, against the clone pinned at the corpus HEAD.
# --------------------------------------------------------------------------

def _pinned_clone() -> str:
    """The first candidate path that is a repository at the corpus HEAD, or "".

    `03-LLD.md` §13.1's `--clone` default is `~/.cache/circt`; this host's
    blobless clone is under `~/.cache/chia-pin-smoke` and its own HEAD is a
    later commit, so the worktree `fixtures/corpus/README.md` describes is
    tried first and the environment overrides both.
    """
    for candidate in (os.environ.get("BUGLOOP_CORPUS_CLONE"),
                      "~/.cache/chia-pin-smoke/w05/corpus-head", "~/.cache/circt"):
        if not candidate:
            continue
        path = os.path.expanduser(candidate)
        try:
            head = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"],
                                  capture_output=True, text=True, check=True,
                                  timeout=60).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        if head == CORPUS_HEAD_SHA:
            return path
    return ""


@pytest.fixture(scope="module")
def clone() -> str:
    """A blobless `llvm/circt` clone whose HEAD is exactly the corpus HEAD."""
    path = _pinned_clone()
    if not path:
        pytest.skip(f"no clone at HEAD {CORPUS_HEAD_SHA}; "
                    "see circt_bug_loop/tests/fixtures/corpus/README.md")
    return path


@pytest.fixture(scope="module")
def mined(clone: str) -> dict:
    """One real mine at the corpus HEAD, shared by every tier-1 test below."""
    started = time.monotonic()
    result = corpus.build_corpus(clone, CORPUS_HEAD_SHA, SINCE, INLINE_CAP_BYTES)
    result["wall_seconds"] = time.monotonic() - started
    if result["counts"]["missing_blobs"]:
        pytest.skip("the clone could not produce every test blob, which offline "
                    "is a lazy fetch that did not happen, not a mining result")
    return result


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_01(mined: dict):
    """T-U-corpus-01 (FR-01.1): 187 records and 171 non-null tags at the HEAD.

    The two counts hold at `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` and
    nowhere else by right; FR-01.11 is what makes them executable more than
    once. The wall clock and the git-call count are recorded rather than
    asserted tightly, because both are properties of the host's object store.
    """
    seeds = mined["seeds"]
    counts = mined["counts"]
    print(f"\nmined {len(seeds)} seeds in {mined['wall_seconds']:.1f} s, "
          f"{counts['git_calls']} git calls, {counts['tags']} firtool tags, "
          f"{counts['test_files']} test blobs, {counts['run_lines']} RUN: lines")
    assert len(seeds) == 187
    assert sum(1 for s in seeds if s.sdk_tag is not None) == 171
    assert counts["filtered"] == 187 and counts["exact_pin"] == 171
    assert all(schema.validate(s) is None for s in seeds)
    assert mined["counters"].stage == "corpus"
    assert mined["counters"].started == mined["counters"].completed == 187
    assert mined["counters"].failed == 0
    assert set(mined["inputs"]) == {"clone_head_sha", "since", "git_version"}
    assert mined["inputs"]["clone_head_sha"] == CORPUS_HEAD_SHA
    assert mined["inputs"]["since"] == SINCE
    assert mined["inputs"]["git_version"].startswith("git version ")


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_02(mined: dict):
    """T-U-corpus-02 (FR-01.1): the SHA set is PIN's own filtered candidate set.

    Compared as sets against `filtered_187.json`, which is
    `analysis/pin_window_raw.json` reduced by PIN §2's subject rule, and then
    per seed on the two path lists and the pin match, because equal sets with
    different paths would still be a different corpus.
    """
    rows = {row["sha"]: row for row in filtered_187()}
    assert {s.seed_sha for s in mined["seeds"]} == set(rows)
    for seed in mined["seeds"]:
        row = rows[seed.seed_sha]
        assert seed.source_paths == row["src"], seed.seed_sha
        assert seed.test_paths == row["test"], seed.seed_sha
        assert seed.sdk_exact == row["exact"], seed.seed_sha
        if row["exact"]:
            assert seed.sdk_tag == row["tag"]
        else:
            assert mined["nearest_tag"][seed.seed_sha] == row["tag"]
            assert seed.bumps_away == row["bumps"]


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_03(mined: dict):
    """T-U-corpus-03 (FR-01.5): the SdkMap, 38 groups, median 3, maximum 27."""
    sdk_map = mined["sdk_map"]
    sizes = sorted(len(v) for v in sdk_map.values())
    assert len(sdk_map) == 38
    assert statistics.median(sizes) == 3 and max(sizes) == 27
    assert sum(sizes) == 171
    grouped = [sha for shas in sdk_map.values() for sha in shas]
    assert len(grouped) == len(set(grouped))
    assert set(grouped) == {s.seed_sha for s in mined["seeds"] if s.sdk_exact}
    assert all(tag.startswith("firtool-") for tag in sdk_map)


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_04(mined: dict):
    """T-U-corpus-04 (FR-01.7): 16 inexact seeds, every one exactly 1 bump away."""
    inexact = [s for s in mined["seeds"] if not s.sdk_exact]
    assert len(inexact) == 16
    assert {s.bumps_away for s in inexact} == {1}
    assert all(s.sdk_tag is None for s in inexact)
    assert all(mined["nearest_tag"][s.seed_sha].startswith("firtool-")
               for s in inexact)
    assert all(s.bumps_away is None for s in mined["seeds"] if s.sdk_exact)
    assert set(mined["nearest_tag"]) == {s.seed_sha for s in inexact}


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_05(mined: dict):
    """T-U-corpus-05 (FR-01.4): both bucketings, and the 16-way split.

    The dialect-level table is normative and the unmerged one is FINAL Appendix
    A's printed list; both are FR-01.4's acceptance criterion verbatim, and the
    split is how the 16 `include/circt/Dialect` seeds distribute under the
    normative rule.
    """
    counts = mined["counts"]
    dialect = counts["dialect_bucket"]
    for name, n in (("FIRRTL", 42), ("ImportVerilog", 31), ("MooreToCore", 12),
                    ("LLHD", 12), ("Synth", 9), ("Comb", 8), ("Moore", 5),
                    ("ExportVerilog", 5), ("CoreToFSM", 5), ("ESI", 5), ("OM", 4),
                    ("HWToBTOR2", 4), ("RTG", 4), ("HW", 3), ("Arc", 3)):
        assert dialect[name] == n, name
    unmerged = counts["dialect_bucket_unmerged"]
    for name, n in (("FIRRTL", 37), ("ImportVerilog", 31),
                    ("include/circt/Dialect", 16), ("MooreToCore", 12), ("LLHD", 11),
                    ("Comb", 7), ("Synth", 7), ("ExportVerilog", 5),
                    ("CoreToFSM", 5), ("ESI", 5), ("HWToBTOR2", 4), ("RTG", 4),
                    ("OM", 3), ("Moore", 3)):
        assert unmerged[name] == n, name
    assert sum(dialect.values()) == sum(unmerged.values()) == 187

    split = Counter(s.dialect_bucket for s in mined["seeds"]
                    if s.dialect_bucket_unmerged == "include/circt/Dialect")
    assert dict(split) == {"FIRRTL": 5, "Moore": 2, "Synth": 2, "Comb": 1, "HW": 1,
                           "Arc": 1, "SV": 1, "LLHD": 1, "DC": 1, "OM": 1}


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_17(mined: dict):
    """T-U-corpus-17 (FR-01.9): the no-`RUN:`-line seeds, counted and excluded.

    Both are Python scaling scripts the commit also touched, which have no lit
    line of their own. The seeded arm's eligible set is 187 minus the count.
    """
    counts = mined["counts"]
    empty = [s for s in mined["seeds"] if not s.run_lines]
    assert len(empty) == counts["no_run_line"] == 2
    for seed in empty:
        assert mined["exclusions"][seed.seed_sha] == "no_run_line"
        assert seed.argv_template == [] and seed.polarity == [] and seed.shape == []
    eligible = [s for s in mined["seeds"]
                if s.seed_sha not in mined["exclusions"]]
    assert len(eligible) == 187 - len(mined["exclusions"])
    assert counts["unsupported_shape"] == 1 and counts["seed_text_over_cap"] == 0
    assert sorted(Counter(mined["exclusions"].values()).items()) == [
        ("no_run_line", 2), ("unsupported_shape", 1)]


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_18(mined: dict):
    """T-U-corpus-18 (FR-01.12): ordered test paths, and their distribution."""
    distribution = Counter(len(s.test_paths) for s in mined["seeds"])
    assert dict(distribution) == {1: 162, 2: 18, 3: 5, 6: 1, 9: 1}
    assert mined["counts"]["test_files"] == sum(
        len(s.test_paths) for s in mined["seeds"]) == 228
    for seed in mined["seeds"]:
        assert list(seed.test_files) == seed.test_paths


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_20(mined: dict):
    """T-U-corpus-20 (FR-01.3, FR-01.10): every count, against M1's own tables.

    The three tool rows and the four language rows are M1's "seeds per entry
    tool" and "seeds per input language" tables, which count seed MEMBERSHIP
    and do not sum to 187 because a seed may enter through several tools and
    touch several languages. The per-seed partition beside them does sum to
    187 and is recorded rather than asserted against M1: FR-01.3 does not say
    which line's tool a multi-tool seed takes, and M1's report partitions by a
    tool priority order that its own script does not compute.
    """
    counts = mined["counts"]
    assert counts["run_lines"] == 331
    assert counts["polarity"] == {"expect_zero": 329, "expect_nonzero": 2}
    assert counts["shape"] == {"plain": 324, "unsupported": 6, "split_file": 1}
    for tool, n in (("circt-opt", 136), ("circt-translate", 39),
                    ("circt-verilog", 31)):
        assert counts["entry_tool_seeds"][tool] == n, tool
    assert counts["language"] == {".mlir": 146, ".sv": 36, ".fir": 8, "other": 7}
    assert sum(counts["entry_tool"].values()) == 187
    assert set(counts["entry_tool"]) <= {"circt-opt", "firtool", "circt-verilog",
                                         "circt-translate", "arcilator", "other"}
    assert len(counts["other_tool_shas"]) == counts["entry_tool"]["other"]
    print("\nper-seed entry tool partition:", counts["entry_tool"])
    print("seeds ADR-D-13 branch (b) excludes:", len(mined["sv_seeds"]))
    assert len(mined["sv_seeds"]) == 36


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_21(mined: dict, clone: str):
    """T-U-corpus-21 (FR-01.1): `diff` is that git command's output, verbatim.

    Re-run here for one seed with the argument vector §3.3 prescribes, and
    compared byte for byte. The test half is absent from every seed's diff.
    """
    seed = next(s for s in mined["seeds"] if len(s.source_paths) == 2)
    argv = ["git", "-C", clone, "show", "--format=", "--unified=3", "--no-renames",
            seed.seed_sha, "--", *seed.source_paths]
    expected = subprocess.run(argv, capture_output=True, text=True, check=True,
                              timeout=120).stdout
    assert seed.diff == expected and seed.diff
    for record in mined["seeds"]:
        for path in record.test_paths:
            assert f"diff --git a/{path}" not in record.diff
        assert record.diff or not record.source_paths


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_22(mined: dict):
    """T-U-corpus-22 (FR-01.12, FR-05.1): one batched `cat-file`, not 228.

    Asserted by counting the subprocesses the mine launched: one `rev-parse`,
    one `for-each-ref`, one `ls-tree` per tag, two `log` passes, one `ls-tree
    HEAD`, one `log --name-status`, ONE `cat-file --batch` and one `show` per
    seed. A per-file `git show` would add 228 - 1 more.
    """
    counts = mined["counts"]
    assert counts["git_calls"] == 7 + counts["tags"] + counts["filtered"]
    assert counts["test_files"] == 228          # one `show` each would add 227
    assert counts["missing_blobs"] == 0
    for seed in mined["seeds"]:
        assert set(seed.test_files) == set(seed.test_paths)
        assert all(isinstance(text, str) for text in seed.test_files.values())
    assert sum(1 for s in mined["seeds"] for t in s.test_files.values() if t) == 228


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_23(mined: dict, clone: str):
    """T-U-corpus-23 (FR-01.9, FR-17.7): the over-cap exclusion, driven for real.

    At the real cap of 262,144 bytes no seed is over it, so the rule is driven
    by mining the same clone again with a cap of one byte: every seed is then
    excluded for both arms with `seed_text_over_cap`, and NEITHER `diff` nor
    `test_files` is truncated, because both are required fields and
    `bound_text` would return None for them.
    """
    assert mined["counts"]["seed_text_over_cap"] == 0
    capped = corpus.build_corpus(clone, CORPUS_HEAD_SHA, SINCE, 1)
    assert capped["counts"]["seed_text_over_cap"] == 187
    assert set(capped["exclusions"].values()) == {"seed_text_over_cap"}
    assert len(capped["seeds"]) == 187
    by_sha = {s.seed_sha: s for s in mined["seeds"]}
    for seed in capped["seeds"]:
        assert schema.validate(seed) is None
        assert seed.diff == by_sha[seed.seed_sha].diff
        assert seed.test_files == by_sha[seed.seed_sha].test_files


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_19(mined: dict, clone: str):
    """T-U-corpus-19 (FR-01.6): two runs on one clone are byte-identical.

    Byte-identical means the serialised records and every count; the only field
    that may differ is the `CounterBlock`'s own wall clock, which is a
    measurement of the run and not of the corpus.
    """
    again = corpus.build_corpus(clone, CORPUS_HEAD_SHA, SINCE, INLINE_CAP_BYTES)
    first = "".join(schema.to_json(s) for s in mined["seeds"])
    second = "".join(schema.to_json(s) for s in again["seeds"])
    assert first == second
    for key in ("counts", "sdk_map", "exclusions", "nearest_tag", "sv_seeds",
                "inputs"):
        assert mined[key] == again[key], key
    assert again["inputs"]["clone_head_sha"] == CORPUS_HEAD_SHA


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_16(clone: str):
    """T-U-corpus-16 (FR-01.11): a moved HEAD stops the run, naming both SHAs."""
    wrong = "0" * 40
    with pytest.raises(corpus.CorpusError) as caught:
        corpus.build_corpus(clone, wrong, SINCE, INLINE_CAP_BYTES)
    assert caught.value.reason == "head_moved"
    message = str(caught.value)
    assert CORPUS_HEAD_SHA in message and wrong in message
    assert "checkout --detach" in message


@pytest.mark.t1
@_RAY_WARNING
def test_T_U_corpus_15(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """T-U-corpus-15 (FR-01.8): no tags fails loudly, naming the refspec.

    Driven against a repository with one commit and no tags at all, built here,
    which is the same observable as the shell-glob failure PIN §1 records and
    needs no network. The refspec cannot be eaten here in any case: the second
    assertion reads the argument vector `_Git` builds and finds the glob in one
    element of it, never in a shell word.
    """
    repo = tmp_path / "clone_notags"
    repo.mkdir()

    def run(*args):
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                              text=True, check=True, timeout=60)

    run("init", "-q", "-b", "main")
    run("config", "user.email", "test@example.invalid")
    run("config", "user.name", "corpus test")
    (repo / "README").write_text("no tags here\n", encoding="utf-8")
    run("add", "README")
    run("commit", "-q", "-m", "[HW] Fix a crash")
    head = run("rev-parse", "HEAD").stdout.strip()

    with pytest.raises(corpus.CorpusError) as caught:
        corpus.build_corpus(str(repo), head, SINCE, INLINE_CAP_BYTES)
    assert caught.value.reason == "no_tags"
    message = str(caught.value)
    assert "refs/tags/firtool-*" in message and "quote it" in message

    seen = []
    real = subprocess.run

    def record(argv, **kwargs):
        seen.append(argv)
        return real(argv, **kwargs)

    monkeypatch.setattr(corpus.subprocess, "run", record)
    corpus._Git(str(repo), 60)("for-each-ref", "--format=%(refname:short)",
                               corpus.TAG_REFSPEC)
    assert seen and isinstance(seen[0], list)
    assert seen[0].count(corpus.TAG_REFSPEC) == 1


@pytest.mark.t1
@pytest.mark.needs_sdk
@_RAY_WARNING
def test_T_U_corpus_24(clone: str):
    """T-U-corpus-24 (FR-04.1): `resolve_sites`, the head's one tree query.

    The two commands are argument vectors and neither takes a shell. A site
    whose file and symbol both resolve stands; a bad symbol is `no_symbol`, a
    bad file `no_such_file`. `git grep` exits 1 when it matches nothing, which
    is an answer and not a failure, and the rejection carries it as the former.
    """
    sites = [{"file": "lib/Dialect/HW/HWTypes.cpp", "symbol": "parseHWArray"},
             {"file": "lib/Dialect/HW/HWTypes.cpp", "symbol": "zzzNoSuchSymbol"},
             {"file": "lib/Dialect/HW/NoSuchFile.cpp", "symbol": "anything"}]
    answer = corpus.resolve_sites(clone, CORPUS_HEAD_SHA, sites)
    assert answer["resolved"] == [sites[0]]
    assert [r["reason"] for r in answer["rejected"]] == ["no_symbol", "no_such_file"]
    assert [r["file"] for r in answer["rejected"]] == [s["file"] for s in sites[1:]]
    assert corpus.resolve_sites(clone, CORPUS_HEAD_SHA, []) == {"resolved": [],
                                                               "rejected": []}
