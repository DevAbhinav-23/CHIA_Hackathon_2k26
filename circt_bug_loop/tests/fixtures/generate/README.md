# `fixtures/generate/` — what each file is and where it came from

`04-Test-Plan.md` §13's row for `generate_task.py`. Everything here is
**constructed** and is marked as such, which is this directory's whole
difference from `fixtures/corpus/` and `fixtures/crashes/`: no model has been
run against this design, no `BUGLOOP_ALLOW_LIVE_MODEL` has ever been set, and a
transcript nobody recorded may not be passed off as a recording. W-18's pilot is
the first run that produces real ones, and it replaces these.

Each file is the **final text of one turn**, which is what `QueryResult.result`
carries and what `generate_task.parse_json_footer` reads. `04-Test-Plan.md`
§1.6 names them `.jsonl`; a `.jsonl` in `03-LLD.md` §6.5 is the raw session
transcript, which is a different artefact, so these carry the extension of what
they hold (erratum).

| File | What it exercises | Test |
|---|---|---|
| `turns/seed_read_ok.md` | stage 1's two output keys, with three sibling sites: one that resolves, one whose file does not exist, one whose symbol does not | `T-U-gen-05` |
| `turns/probe_write_ok.md` | stage 2's contract, two probes, both written | `T-U-gen-04`, `T-U-gen-08` |
| `turns/probe_write_10.md` | ten probes against a cap of three | `T-U-gen-02` |
| `turns/probe_write_wrongtool.md` | one probe declaring a tool that is not the seed's `entry_tool` | `T-U-gen-03` |
| `turns/probe_write_argv.md` | one probe declaring an argument vector of its own, which the emitter ignores | `T-U-gen-14` |
| `turns/probe_write_badfooter.md` | a stage-2 turn with no fenced json block at all, after files were written | `T-U-gen-07` |

The seed every one of these is replayed against is
`fixtures/corpus/seeds/nine_test_files.json`, which is **recorded**: it is the
corpus's nine-test-file seed, `3b30c823b829`, whose entry tool is `circt-opt`
and whose first argv template carries `--split-input-file`, so the emitter's
option strip and its `%s` binding are both exercised on a real seed rather than
on a constructed one.

The source tree the sibling sites resolve against is the throwaway git
repository `tests/test_tools.py` builds, two files and one commit, which is what
lets `T-U-gen-05` run `corpus.resolve_sites` for real at tier 0.
