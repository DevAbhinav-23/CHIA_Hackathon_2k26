# `fixtures/synth/` — three constructed synthesis turns

`04-Test-Plan.md` §1.8. Everything here is **constructed**, for the same reason
`fixtures/generate/` is: A7 has not been run, no model has been called against
this design, and a transcript nobody recorded may not be passed off as one.

| File | What it exercises | Test |
|---|---|---|
| `turns/mutator_synth_ok.md` | three well-formed mutators, one per language shape, which the freeze then writes | `T-U-msyn-02`, `-03`, `-05`, `-08` |
| `turns/mutator_synth_drops.md` | one surviving entry and eight that each fail exactly one of step 4's checks | `T-U-msyn-07` |
| `turns/mutator_synth_bad.md` | a turn with no fenced json block, which freezes nothing | `T-U-msyn-04` |

**The mirror is not a file here.** §8.3 step 2 reads `issue_mirror` out of
`loop.db`, so the tests build a real database through `store.LoopStore` and
insert rows into the real table: the 487 closed `label:bug` issues and the 101
open ones that M9 measured on 2026-09-13 are **constructed rows at those two
counts**, which is what `issues_used == 487` and the `state = 'closed'` filter
need, and no row of them is presented as a recorded issue. `fixtures/mirror/`,
which holds recorded GitHub payloads, belongs to B6a and W-10 and is not read
from here.
