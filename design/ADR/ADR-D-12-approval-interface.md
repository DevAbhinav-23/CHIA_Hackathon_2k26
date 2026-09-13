# ADR-D-12: What the human approval interface is

**Status:** Accepted, **amended 2026-09-13** after the HLD review (W13).
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-12.

## Context

CIRCT forbids automated agents taking action without human approval (C-05,
`circt:docs/AIToolPolicy.md:23`), so a named human approves every filing (FR-13.7). FR-13.12 requires
the human to see the full rendered report, the four gate answers, the repair diff if any, and the
reduced case in one view. D-12 recommends a CLI, with a generated review page if time allows.

## Decision

Adopt **(a) a CLI for the campaign, with (b) the generated static review page if time allows.** The
CLI prints one pending report with the four answers, the diff and the reduced case, and reads a typed
approval naming the approver. A web service (c) is rejected: a service to run, secure and shut down,
for at most a few dozen approvals.

D-12's missing consequence is binding and is already FR-13.18. Under ADR-D-02 the human gives back
two things, an approval and, where FR-13.16's poll found nothing, an issue URL. **The approval CLI is
the single place for both**, recorded against the same report id, so a filing is never two tools'
worth of human interaction. `03-LLD.md` specifies it and `05-Work-Plan.md` lists it as a named
deliverable, it being the only interface a human touches.

Before presenting anything the CLI enforces the per-UTC-day filing cap (FR-13.8), checked before the
human is asked rather than after; the `good first issue` refusal (FR-13.9); and FR-11.8's hold, where
a candidate that passed the gate without a report is held with `held_reason=no_report`.

**Amendment: the CLI also takes FR-20.5's licence confirmation, and the `FilingRecord` records it.**
A patch offered with a report must be licensable under Apache-2.0 with LLVM exceptions, confirmed by
the contributor *at approval time* (`circt:docs/AIToolPolicy.md:29`), and that confirmation had no
home in any schema, so nothing could show it had been given. The CLI asks for it, with the patch on
screen, whenever the decision is `report_plus_patch`; a decline downgrades the decision to `report`
and is recorded; and the `FilingRecord` carries the confirmation, the confirming approver and the
timestamp. A candidate walked away from mid-approval writes nothing at all: it stays held with
`held_reason=awaiting_approval` and the next invocation presents the same report, so an approval is
never partially recorded.

## Consequences

- **FRD:** resolved; FR-13.8, FR-13.12 and FR-13.18 stand unchanged.
- **HLD:** the gate and approval CLI is one component, not two. It reads the loop database and the
  artefact tree, writes `GateDecision` and `FilingRecord`, and is the only component a human drives.
  It runs on the head, not on a `circt` worker, because it is interactive.
- **Cost:** approval happens wherever the head node is, which may not be where the human is. The
  static page of (b) removes that, and is explicitly optional.

## Follow-up measurements

None. FR-13.18's acceptance is one manual walkthrough completing both the approval and the URL without
a second tool.
