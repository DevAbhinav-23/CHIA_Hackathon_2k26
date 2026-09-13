# ADR-D-11: Where candidates, fingerprints and filings are stored

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation. User's explicit words: *"if u want sqlite and
stuff yea install its fine."*
**Resolves:** `01-FRD.md` §8 D-11.

## Context

CHIA's example persists one row per issue attempt in `issues.db`, whose schema is issue-shaped
(`issue_number INTEGER NOT NULL`, `pr_writeup`) and keyed by an integer throughout
(`chia:examples/circt_issue_solver/db.py:21-49`). The loop's own objects, candidates, fingerprints,
gate decisions and filings, are not issue-shaped. D-11 recommends a second database.

## Decision

Adopt **(b): a second SQLite database for the loop**, a `SQLiteNode` of its own, pinned to the same
machine as `issues.db` (C-14, `chia:chia/database/sqlite_node.py:13-33`), joined to `issues.db` by
the local integer identifier of FR-12.2. `sqlite3` is in the Python standard library, so this adds no
dependency and FR-19.8's licence check has nothing to check.

CHIA's example keeps its schema and its file: §4.1's Persistence row reads **Not extended**.

Option (c), Postgres, is rejected: a service added to a single-machine deployment that does not need
one (ADR-D-14). Option (a) is rejected on separation, not on FR-12.1, which byte-compares
`issue_task.py` alone and does not by itself forbid a schema change.

D-11's missing consequence is binding and is already FR-12.10. Two SQLite files on one machine, with
`SQLiteNode` opening a fresh connection per `chia_remote` call
(`chia:chia/database/sqlite_node.py:21-27`), means a candidate row and an attempt row cannot be
written in one transaction. **The loop's row is written first, carrying the local identifier; CHIA's
row is then written by CHIA's own unmodified code; a loop row whose CHIA counterpart never appears is
marked `repair_row_missing` by an end-of-run reconciliation pass.** FR-17.8's `PARTIAL` marker does
not cover this, being about directories.

## Consequences

- **FRD:** resolved; FR-12.2, FR-12.10 and §4.1's Persistence row stand unchanged.
- **HLD:** two databases appear in the data-flow diagram, `loop.db` owned by the loop and `issues.db`
  owned unchanged by CHIA's example, with exactly one join key crossing and one reconciliation pass
  owning the dangling case. Every object of §2.4 is assigned to one of them or to the artefact tree.
- **Cost:** two files on one machine, a fixed write order, and a reconciliation pass every run.

## Follow-up measurements

None. FR-12.10's acceptance, killing the chain between the two writes and asserting the reconciliation
names the loop row, is a test rather than a measurement.
