# `circt_bug_loop/data/`

Committed measurements the FLOW reads, as distinct from fixtures the tests read.

## `labelled_pairs.json`

FR-10.2's hand-labelled duplicate-pair set: twenty-two pairs of recorded
failures, eleven judged `duplicate` and eleven `distinct`, at least four per
rule and five R4, each with the justification and the instant it was labelled.
The labels are human judgements made before any fingerprint was computed over
them; `triage_task.rates` measures the collision and false-merge rates by
fingerprinting both sides and comparing the verdict to the label, and A-05
closes on the two numbers that fall out (W-10 erratum 20).

It lives HERE and not under `tests/fixtures/` because
`results.render_results` takes it as a parameter on every campaign
(`03-LLD.md` §14.4's fourteenth refusal). W-19b measured what its absence
costs: `run_campaign` called the node as `render_results(store, manifest)`,
`_dedup_rates`'s gap fired on every run, `ResultsIncomplete` went uncaught, and
a campaign ran both four-hour arm windows and then died with a traceback
instead of writing its results artefact. `runtime_env` ships the package and
not `tests/`, so a set under `tests/` could not have reached a worker either.

`results.load_labelled_pairs()` is the reader. The tests read the same file.

**A labelled pair is only measurable against a store that holds fingerprints
for both of its sides.** These twenty-two are fingerprinted from W-09's six
recorded failures and from §3.7.1's own ten-run measurement, so a campaign's
own store does not hold them and the artefact refuses with exactly that
complaint, by name, rather than with a traceback. That refusal is honest and is
the architect's to close: either the set is re-labelled over a pilot's own
confirmed candidates, which §10 asks for and no run has produced yet, or the
rates are reported as a project measurement beside the artefact rather than
inside it.
