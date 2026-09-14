# `fixtures/image/`

| Path | What it is | How it was made |
|---|---|---|
| `lit_show_tests.txt` | `lit --no-progress-bar --show-tests /workspace/circt/build/test`, stdout. | **Recorded**, 2026-09-14, inside `chia-circt-assert:eade0de61bc5`, exit status 0. 1,390 tests under the `-- Available Tests --` heading. |
| `lit_notes.txt` | The same run's stderr: nine `Did not find circt-capi-*` notes and one `contained no tests` warning. | **Recorded** in the same run. None of them is fatal, which is the point: FR-03.17 blocks publication on a `fatal: unable to parse config file` line and on a non-zero exit, and on neither of these. |
| `lit_fatal.txt` | The failing half. | **Constructed** from `lit_notes.txt` by replacing its last line with lit's own `fatal: unable to parse config file` line, which is what an unresolved `mlir_src_root` produces. No image in this project has ever produced it: the measured one resolves `/opt/circt-sdk` (W-04). |
