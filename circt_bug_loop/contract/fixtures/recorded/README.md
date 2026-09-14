# `contract/fixtures/recorded/`

The seam, **recorded**. One document per file, `<schema>/<id>.json`, at
`CONTRACT_VERSION` 2.0, written through `bug_loop.FixtureRecorder` after
`contract.validate` accepted each instance, which is `04-Test-Plan.md` §0.6
rule 2's production rule and `contract/FROZEN.md`'s fixture-replacement rule.

The generator is committed: `tests/fixtures/recorded/make_recorded.py`, which
§13's own rule requires ("`make_fixtures.py` is committed beside them"). Run it
to re-record:

```sh
PYTHONPATH=. python circt_bug_loop/tests/fixtures/recorded/make_recorded.py
```

## What ran

One mini-campaign, **in this process**, with no Ray, no container and no model.
Every instance is the return value of the node `03-LLD.md` names as its
producer, running for real:

| Member | Producer | What is real about it |
|---|---|---|
| `BudgetFile` | `budget.load_budget` | the committed `budget.yaml`, landed in a throwaway registration repository at a fixed date and taken through all six pre-registration checks of §9.2 |
| `SeedRecord` | `corpus.build_corpus` | re-recorded from `tests/fixtures/corpus/seeds/`, which is W-05's own recording against the blobless clone at the corpus head |
| `ProbeSpec` | `generate_task.generate_mutation`, `generate_task.generate_seeded` | A4 for real, and A3 with its two turns **replayed** from `tests/fixtures/generate/turns/` (§0.6, NFR-01): the emitter, the cap, the argv rule, the two `ChiaTool`s and the validator all run and no model does |
| `ProbeResult` | `probe_task.probe_execute` | four real executions of a real `circt-opt` under the `prlimit` prefix, classified by `classify_build` from their own exit status and stderr. **Two of the four fired a real assertion**, which is the one thing a constructed fixture cannot be |
| `FeedbackBundle` | `feedback.build_feedback` | A5 for both arms, so the pair shows FR-16.2's asymmetry: the seeded bundle carries one entry per dispatched probe and the mutation bundle carries none |
| `LedgerEntry` | `ledger.accrue` | three entries covering all three `arm` values and both `scope` values, each priced by A6b and read back out of `loop.db` rather than out of the caller's hand |
| `RunManifest` | `bug_loop.build_manifest` | every field from its named producer: A2's real pin walk over the blobless clone, A6a's budget, B6a's mirror over `tests/fixtures/mirror/`'s fifty recorded issues, the committed cluster YAML's own digest, the mutator set's own digest |

## The three things that are not the pilot's, stated rather than hidden

1. **The `ImageSpec` is this host's measured build and not the published
   image.** Recording inside `chia-circt-assert:<tag>` is tier 2 and is the
   pilot's (`05-Work-Plan.md` W-18). The `image_digest` reads `local-build:` and
   the tool hashes are of the binaries actually executed, so no reader can take
   the recording for one made in a container. The published image's own recorded
   identity is `analysis/measurements/raw/image-manifest.json`.
2. **The mutator set is `set_dev.json`.** A7 has not run and `set_v1.json` does
   not exist (`04-Test-Plan.md` §16.8 item 8). `load_set` refuses an unfrozen set
   to any run that names a digest; the recording names none, and the campaign's
   refusal is left standing.
3. **W-09's six recorded failures are not re-run here.** Each fired against a
   CIRCT build at its own seed's first-parent commit (§5.1's procedure), and no
   build on this host is at any of those six commits, so re-running them would
   record a legalization error and call it a crash. They are replayed where they
   are, `tests/fixtures/crashes/`, through the real `classify_build` and
   `oracle_primary` at tier 0.

## Reproducibility

The run id, the registration commit's date and the artefact root are all fixed,
so a re-recording is a diff of what changed rather than a new set of file names.
Two fields move on every recording and are meant to: `budget_file_sha`, which is
the registration commit, and `issue_mirror.refreshed_utc`, which is the moment
the mirror was walked. Re-recording is a commit, and `T-U-fixt-01` is what
notices that the set and the package have drifted apart.
