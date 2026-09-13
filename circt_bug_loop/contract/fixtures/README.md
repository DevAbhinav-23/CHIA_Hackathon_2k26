# `contract/fixtures/`

Committed instances of the seam, one document per file, at `CONTRACT_VERSION` 2.0. This directory is
the enforcement point for the compatibility rule (`02-HLD.md` §2.13, `03-LLD.md` §2.2): a MAJOR bump
fails `tests/test_fixtures.py` until the set is re-recorded.

## Every instance here is CONSTRUCTED, not recorded

`04-Test-Plan.md` §0.6 rule 2 and §13 require the `<schema>/` set to be **recorded** by
`bug_loop.py --record-fixtures` on a real run. No run exists on 2026-09-14 and `bug_loop.py` does not
exist either, so `05-Work-Plan.md` §2.1 writes them constructed now and **replaces** them with
recorded instances at W-17, in a commit of its own. That replacement commit may change fixture
contents and may not change the schema.

Until W-17 lands, every file under this directory is hand-constructed through the dataclasses of
`contract/schema.py`, passed through `validate()`, and written with `to_json()`, so the bytes are
canonical by construction. None of them is evidence of anything a run did.

| Directory | File | Shape |
|---|---|---|
| `seed_record/` | `exact_pin_01.json` | `sdk_exact` true, so `bumps_away` is null; one run line, one source path, one test file |
| `budget_file/` | `complete_01.json` | every field of `BudgetFile`, the four keys `03-LLD.md` §9.1 added on 2026-09-14 included, at §9.5's values; `acceptance` carrying §9.3's seven keys |
| `probe_spec/` | `seeded_01.json` | the seeded arm: the three mutation fields null, `turn_cost` metered |
| `probe_spec/` | `mutation_01.json` | the mutation arm: the three mutation fields set, `turn_cost.turn` null and unmetered |
| `probe_result/` | `assertion_01.json` | `oracle_class` `assertion`, so both assertion fields set; reduced text with its path |
| `feedback_bundle/` | `iteration_01.json` | two nested `FeedbackEntry`s, one fired and one not; not abandoned |
| `ledger_entry/` | `arm_window_01.json` | the one `scope` `arm_window` entry an arm writes, `observed` populated on the `vertex` backend |
| `run_manifest/` | `discovery_01.json` | `mode` `discovery`, so one `run_commit` with a null `seed_sha`; all four declared dicts closed |

The `malformed/` and `roundtrip/` subtrees `05-Work-Plan.md` §2.1 also names are not files here:
`tests/test_schema.py` derives every malformed case from the valid instance above it by the same one
edit the plan describes, and round-trips the eight instances above rather than a second copy of them.
A malformed document committed here would contradict `T-U-fixt-01`, which validates **every** file
under this directory.
