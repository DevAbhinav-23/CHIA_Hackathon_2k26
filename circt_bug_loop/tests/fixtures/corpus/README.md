# `fixtures/corpus/` — what each file is and where it came from

`04-Test-Plan.md` §11's row for this directory. Nothing here is hand-written
except the four constructed `RUN:` lines named below, and each of those is
constructed because M1 measured **zero** occurrences of its shape over the
corpus. Everything else is recorded: a real line of a real CIRCT test file, or
a real `SeedRecord` `corpus.build_corpus` emitted.

## `runlines/` — one real `RUN:` line per shape of FR-01.10

Each file holds the **physical** line or lines of the named test file, comment
marker included, exactly as `git show <rev>:<path>` prints them, so
`corpus.extract_run_lines` is exercised on the same text lit reads. Recorded
2026-09-14 from the blobless clone with

```sh
git -C <clone> show <rev>:<path> | sed -n '<first>,<last>p'
```

| File | Source path | Commit |
|---|---|---|
| `not_plain.txt` | `test/Conversion/ExportVerilog/verilog-errors-prop.mlir` line 3 | `b792c772819d` |
| `not_quoted.txt` | `test/Conversion/ExportVerilog/verilog-errors-prop.mlir` line 10 | `b792c772819d` |
| `env.txt` | `integration_test/circt-test/basic-circt-bmc.mlir` line 1 | `b792c772819d` |
| `splitfile.txt` | `test/Dialect/Arc/inline-arcs.mlir` line 1 | `b792c772819d` |
| `pipe_plain.txt` | `test/Conversion/HWToLLVM/convert_aggregates.mlir` line 1 | `f2b15a44ec70` |
| `pipe_quoted.txt` | `test/Dialect/FIRRTL/Reduction/issue-3555.mlir` line 3 | `b792c772819d` |
| `subst_s.txt` | `test/Dialect/Arc/insert-runtime.mlir` line 1 | `b792c772819d` |
| `subst_s_twice.txt` | `test/circt-verilog/redundant-files.sv` line 1 | `9f021153418e` |
| `subst_S.txt` | `test/Dialect/LLHD/Transforms/mem2reg-scaling.mlir` line 7 | `b792c772819d` |
| `unsupported_and.txt` | `test/Conversion/ExportVerilog/verilog-errors-prop.mlir` line 9 | `b792c772819d` |
| `unsupported_semicolon.txt` | `test/Dialect/Arc/insert-runtime.mlir` line 2 | `b792c772819d` |
| `cont.txt` | `test/Conversion/ImportVerilog/proximate-source-locations.sv` lines 1-2 | `b792c772819d` |
| `single_dash_verify.txt` | `test/Dialect/SV/sv-trace-iverilog-errors.mlir` line 1 | `88d9a5ad7a3a` |
| `single_dash_both.txt` | `test/Conversion/CoreToFSM/errors.mlir` line 1 | `838a8bb29106` |
| `mixed_dash.txt` | `test/Conversion/FIRRTLToHW/lower-to-hw.mlir` line 1 | `3f65acfd617b` |
| `unsupported_backtick.txt` | constructed | none |
| `unsupported_dollarparen.txt` | constructed | none |
| `unsupported_brace.txt` | constructed | none |

`b792c772819d` is the clone's own HEAD, the commit RT4 §2 W2 and `03-LLD.md`
§3.3 both quote. `f2b15a44ec70` is the commit FR-01.2's acceptance criterion
names, and `9f021153418e` is the one corpus seed whose line carries `%s` twice
before the pipe.

**The three single-dash lines.** LLVM's option parser takes one dash or two for
every long option, and 46 of M1's 331 corpus `RUN:` lines spell
`-verify-diagnostics` or `-split-input-file` with one
(`analysis/measurements/raw/m1-per-runline.csv`); `corpus.strip_probe_only_options`
knew only the two-dash forms until errata W-09 #3. `single_dash_verify.txt` is
the `RUN:` line of the seed `fixtures/crashes/assertion_02/` was mined from,
whose surviving `-verify-diagnostics` is recorded in that fixture's `argv.json`;
`single_dash_both.txt` carries both options single-dashed; `mixed_dash.txt`
carries one of each dash count in one line. `88d9a5ad7a3a`, `838a8bb29106` and
`3f65acfd617b` are those lines' own seed commits.

**The three constructed lines.** M1 measured 0 lines carrying `%{`, and a
search of the whole `test/` and `integration_test/` trees at `b792c772` finds
no `RUN:` line carrying a backtick or a `$(` either. FR-01.10 step 6 names all
three, so each has a fixture and each is marked as constructed rather than
passed off as recorded. The `;` and `&&` cases are real and are the two files
above them.

## `seeds/` — five recorded `SeedRecord`s at contract 2.0

Emitted by `corpus.build_corpus` against the clone reset to
`d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2` with `--since 2024-09-11`, then
written with the contract's own `to_json`, so each file is canonical and
`schema.from_json` reads it back. Five shapes, one per file:

| File | Seed | What it is for |
|---|---|---|
| `nine_test_files.json` | `3b30c823b829` | FR-01.12: the 9-test-file seed, the corpus maximum |
| `sdk_inexact.json` | `a197d6e076c1` | FR-01.7: `sdk_exact=false`, `bumps_away=1`, `sdk_tag=null` |
| `no_run_line.json` | `0da0bde46833` | FR-01.9: a `.py` test, no `RUN:` line, empty `run_lines` |
| `unsupported_shape.json` | `2fdae8fcfef5` | FR-01.10: every line `unsupported`, here on `&&` |
| `not_wrapper.json` | `337c72727242` | FR-01.10: the corpus's only `not`-wrapped lines, 2 of them |

## `filtered_187.json`

The acceptance set of FR-01.1, derived from `analysis/pin_window_raw.json` by
PIN §2's subject rule and nothing else: the 187 filtered candidates with the
`src` and `test` path lists and the pin match `pin_window.py` computed for each.
It is committed instead of the 687 kB raw file because the tests need the 187
rows and no other part of it. Re-derivable with the regex at
`analysis/pin_window.py:107-108` over `raw["candidates"]`.

## The clone the tier-1 tests want

Not committed, and not fetched by any test. `test_corpus.py` looks at
`$BUGLOOP_CORPUS_CLONE`, then at `~/.cache/chia-pin-smoke/w05/corpus-head`,
then at `~/.cache/circt`, and **skips** unless one of them is a git repository
whose `HEAD` is exactly `d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2`. To make
one from an existing blobless clone without moving that clone's own HEAD,

```sh
git -C <clone> worktree add --no-checkout --detach \
    ~/.cache/chia-pin-smoke/w05/corpus-head d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2
```

`--no-checkout` is deliberate: every command `corpus.py` runs addresses objects,
never the working tree, so checking out 30,000 files would buy nothing and would
cost a full blob fetch. From nothing at all,

```sh
git clone --filter=blob:none https://github.com/llvm/circt <clone>
git -C <clone> fetch origin 'refs/tags/firtool-*:refs/tags/firtool-*'   # quoted
git -C <clone> checkout --detach d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2
```

The quoting of the refspec is PIN §1's reproduction note and FR-01.8's failure
mode: `fish` and `zsh` expand it and `git` then silently matches nothing.
