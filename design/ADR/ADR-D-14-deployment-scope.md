# ADR-D-14: How far the loop is deployed

**Status:** Accepted, **amended 2026-09-13** after the HLD review (K3).
**Date:** 2026-09-13.
**Decided by:** architect, on the user's delegation; user's explicit words quoted where they exist.
**Resolves:** `01-FRD.md` §8 D-14.

## Context

NFR-10 originally required a GCP cluster as well as a single machine. Neither FINAL nor PAPER asks
for a cloud deployment, so that half is scope the FRD added, competing with the Musts for the days
before C-10's deadline of 2026-09-24 AoE. CHIA supports both: the single-machine pattern already
exists (`chia:examples/circt_issue_solver/cluster.yaml:1-19`, four containers on one host), and
`gcp_nodes` provisions Compute Engine instances during `chia up`
(`chia:chia/cluster/gcp_nodes.py:1-14`; `chia:docs/user_guides/cluster_config_reference.rst:445-460`).

## Decision

Adopt **(b): single machine as a Must, GCP as a Should.**

The single-machine configuration is the Must and is the campaign's configuration. The GCP cluster
**becomes the campaign target only if the hackathon's cloud credits are confirmed by the
pre-registration date `05-Work-Plan.md` names**; otherwise the loop ships single-machine and NFR-10's
second half is recorded as not exercised. The `RunManifest` records which configuration ran, on every
run, so the record is never ambiguous.

This is a scope **addition** being trimmed, not a scope **cut**: `00-README.md`'s no-cuts rule
protects every Must the FRD states, and the GCP half was never one of FINAL's or PAPER's.

Option (c), both as Musts, is rejected: a second cluster and a second system-test configuration,
eleven days out, against features that are all Musts. Option (a), single machine only, is rejected
because ADR-D-03's campaign backend may be `opencode` on Vertex, and the credits arriving is exactly
the condition that would also make the GCP cluster worth having.

## Consequences

- **FRD:** resolved; NFR-10 stands as written, Must plus Should.
- **HLD:** §10.1 item 4 is satisfied by naming **two** cluster YAML skeletons, the single-machine one
  in full detail and the GCP one as a skeleton differing only in the provider section and the
  credentials handling; both carry the same worker types, resource names and images, so the loop code
  is identical under both. The GCP YAML is written only if the date is met.
- **Amendment, the artefact tree is what GCP defers.** The loop's artefacts are produced on workers
  and read on the head, and CHIA has no worker-to-head file transport: `file_mounts` is a
  head-to-host rsync run by `chia up` before the container starts. On the single machine this is
  solved with no new mechanism, by bind-mounting one host directory into every worker container at
  the identical absolute path the head uses (FR-17.9). **On GCP the workers are other machines and a
  host path is not shared, so the GCP deployment additionally needs shared storage, a bucket mounted
  at `artefact_root` on every node and on the head. That work is deferred with GCP under this
  decision.** Nothing in the Must depends on it.
- **Cost:** a configuration field in the manifest, a Should that may never be exercised, and, if it
  is exercised, a storage mount the single-machine configuration never needed.

## Follow-up measurements

None. The gating item is a date: `05-Work-Plan.md` item 10 names the date by which the credits must be
confirmed and what ships if they are not.
