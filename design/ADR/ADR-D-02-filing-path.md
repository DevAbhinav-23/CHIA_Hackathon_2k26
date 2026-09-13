# ADR-D-02: Who files on GitHub after human approval

**Status:** Accepted.
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-02.

## Context

CHIA's GitHub layer is GET-only and has no write method (C-04,
`chia:chia/github/github_client.py:130-134`). CIRCT forbids automated agents taking action without
human approval (C-05, `circt:docs/AIToolPolicy.md:23`). D-02 recommends (c) plus (d) with (a) as the
fallback. FR-18.3's headline is populated from `FilingRecord`s, so an option that loses the
filing-to-report link is not merely inconvenient.

## Decision

Adopt **(c) the tool prepares, the human submits**: the loop renders the report and emits a
pre-filled `?title=&body=` issue URL, which the human opens and presses send on in their own browser
session, under their own account. `llvm/circt` has no `.github/ISSUE_TEMPLATE/` directory, so prefill
is available (verified, FR-13.17).

Adopt **(d) reconciliation** alongside it: after the human files, the loop completes the
`FilingRecord` by polling the read-only `GithubIssuesNode` for a new issue whose body carries the
report's primary fingerprint (G-43), within the `[DEFAULT]` poll window recorded in `budget.yaml`
(FR-13.16). Every filed body therefore carries the fingerprint line. The poll is a GET, so the loop
still performs no write.

Adopt **(a) the human files by hand from the rendered report** as the fallback, triggered when the
pre-filled URL **exceeds 6,000 characters `[DEFAULT]`**, which is the `03-LLD.md` `[DEFAULT]`
FR-13.17 names. The fallback and its reason are recorded against the report id. Where (d)'s poll
finds nothing inside its window, the human pastes the URL into the approval CLI of FR-13.18, the
single interface for both.

## Consequences

- **FRD:** resolved; FR-13.16, FR-13.17 and FR-13.18 stand, with 6,000 characters now fixed. NFR-04
  and NFR-07 hold literally: one read-only credential, no non-GET request anywhere.
- **HLD:** the gate and approval CLI owns URL construction, length measurement, the fallback branch
  and the reconciliation poll; no component holds a write-scoped credential.
- **Cost:** a fingerprint line in every filed body, one poll window per filing, and a copy-and-paste
  per filing on the fallback path.

## Follow-up measurements

None. The URL-length branch is exercised by FR-13.17's own acceptance criterion.
