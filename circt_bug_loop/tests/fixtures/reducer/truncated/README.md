# `reducer/truncated/`

`reduced.mlir` is **empty**, which is what a `--keep-best` output looks like
when the reduction was killed before its first write landed. `circt_reduce_run`
validates the `-o` output only after the reducer process has exited
(FR-09.13, `03-LLD.md` §10.2) and reports `output_valid=False` for it;
`T-U-core-09` and `T-U-probe-36` are the two tests.
