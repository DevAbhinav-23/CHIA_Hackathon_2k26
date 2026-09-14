# `fixtures/mutators/` — two constructed sets, and what each is for

`04-Test-Plan.md` §1.7. Both files here are **constructed** and say so in their
own `synthesis_input.query`: a set is the output of A7, A7 has not been run, and
a set nobody synthesised may not be passed off as one. The set the tests
actually mutate with is the committed development set,
`circt_bug_loop/mutators/set_dev.json`, which carries `"frozen": false` for the
same reason and which `mutators.load_set` refuses for any run that names a
digest.

| File | What it exercises | Test |
|---|---|---|
| `raising.json` | one mutator whose pattern will not compile and one whose replacement is a line operation on a `text` mutator; the third is a working one, so the arm can be shown to continue past both | `T-U-mut-04` |
| `noop.json` | one mutator whose pattern matches nothing any CIRCT test carries, so every application is a no-op | `T-U-mut-03` |

`04-Test-Plan.md` §13 names the second `mutators/noop_case/`, a directory; a
no-op needs a set and an input and the input is the recorded nine-test-file
seed, so the fixture is the set alone (erratum).
