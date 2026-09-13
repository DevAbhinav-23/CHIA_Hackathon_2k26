# Seed, Generate, Reduce, Repair, Gate: a closed CIRCT bug loop

CHIA Hackathon 2026 (A³ workshop @ MICRO 2026). Team: Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla (IIIT Hyderabad).

A CHIA loop that mines past CIRCT fix commits, has an agent write probing inputs for sibling bugs, judges them with an assertions-on crash oracle, reduces, deduplicates, attempts repair through CHIA's existing phase chain, and gates every filing behind a named human.

## Layout

| Path | What |
|---|---|
| `paper/` | The 4-page paper (LaTeX, IEEEtran; `paper/build.sh`); `circt-bug-loop-paper-v3.pdf` is the current build |
| `design/` | The formal design set: `00-README.md` (rules), `01-FRD.md`, `02-HLD.md`, `03-LLD.md`, `04-Test-Plan.md`, `05-Work-Plan.md`, `ADR/` (14 decisions), `reviews/` (three red-team reports and their dispositions) |
| `analysis/` | Empirical basis: LLVM pin-window analysis, 2026-09-13/14 measurements with scripts and raw output |
| `docs/` | Problem statement (`problem-statement-FINAL.md`), handoff notes, abstract, from-basics explainer, archived drafts and reviews |
| `circt_bug_loop/` | The loop itself (a CHIA example directory; see `design/03-LLD.md` §1). Arrives after the design set is signed off |
| `upstream/` | Files proposed to CHIA core for the upstream PR: the assertions-on Dockerfile, its workflow, and the generic CIRCT helpers |

Read `docs/HANDOFF.md` first for state, then `design/00-README.md` for how the documents are gated.

No credentials live in this repository. Runtime state (`loop.db`, artefact roots) is ignored by `.gitignore`.
