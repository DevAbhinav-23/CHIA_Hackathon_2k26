# From Mined Fixes to Gated Repair: Closed-Loop Defect Synthesis for CIRCT

CHIA Hackathon 2026, A³ workshop at MICRO 2026 (Athens, 1 November).
Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla, IIIT Hyderabad.

An agentic loop on [CHIA](https://github.com/ucb-bar/chia) that finds bugs in
CIRCT, the LLVM project's hardware compiler. A model reads a past CIRCT bug fix
and writes inputs aimed at the sibling sites where the same mistake may survive.
Fixed tools then build CIRCT with its assertions back on, judge, reduce and
deduplicate every input, and a named person approves every filing. The model
acts at three stages; every verdict comes from a tool.

## Results

**Registered campaigns** (September 2026, Gemini 3.8 Flash through CHIA):
52 seeds, 758 inputs, **15 new CIRCT bugs through the gate**. A mutation
baseline on the same harness and gate wrote 2,308 inputs and found none.
<!-- paper/main.tex Table II; analysis/measurements/2026-09-15-campaign-2.md, 2026-09-16-campaign-3.md -->

**After review** (October 2026, no model calls in the loop):

- All 15 still fail on CIRCT main `4738bd26`, and none matches an issue or a
  fix. <!-- analysis/measurements/2026-10-27-recheck-main.md -->
- A coding agent (Claude Opus) wrote fixes for all 15: 13 patches with
  regression tests; CIRCT's lit suite gives the same results with and without
  them. Not yet submitted. <!-- analysis/measurements/2026-10-27-repairs.md -->
- The mutation baseline, run for its whole window, wrote 115,869 inputs and put
  2 bugs through the gate. <!-- analysis/measurements/2026-10-27-mutation-full-window.md -->
- 18 inputs the loop blamed on the model are compiler bugs, from 3 new root
  causes. <!-- analysis/measurements/2026-10-27-missed-candidates.md -->

Nothing is filed yet. Issue drafts are in `analysis/review/issue-drafts/`;
filing follows the forum post in `docs/forum-post.md`.

## Layout

| Path | What |
|---|---|
| `paper/` | The paper: LaTeX source, `main.pdf`, `build.sh` (git history holds the reviewed version) |
| `poster/` | The A³ poster, 36 × 48 in |
| `circt_bug_loop/` | The loop: CHIA nodes and tools, the frozen contract (`contract/FROZEN.md`), the driver `bug_loop.py`, budget files, tests |
| `design/` | FRD, HLD, LLD, test plan, ADRs and red-team reviews; start at `design/00-README.md` |
| `analysis/measurements/` | Every measurement with its script and raw output |
| `analysis/review/` | Post-review work: numbers, re-check on main, fixes, issue drafts |
| `upstream/` | Four files prepared for CHIA (not yet submitted) |
| `docs/` | `RUN.md` (how to run), `HANDOFF.md` (work log), `forum-post.md`, `problem-statement-FINAL.md` |

## Running it

Run `./scripts/setup.sh`, then follow [`docs/RUN.md`](docs/RUN.md): tests,
inspecting a past run, or a live campaign.

```sh
python -m pytest circt_bug_loop/tests -q -m t0
```

selects the 690 tests (of 740) that need no CIRCT binary, network or model;
689 pass and 1 is skipped. <!-- measured 2026-10-29 under ~/.cache/chia-venv -->

## Safeguards

- **Registration.** A run needs an annotated git tag `registration/<run>` on the
  commit that lands its budget file. The loop refuses any other budget file and
  any mutator set committed after the tag.
- **Live-model interlock.** No stage builds a model client unless
  `BUGLOOP_ALLOW_LIVE_MODEL=1` is set for that run.
- **Approval.** Filing is a command a named person runs, and it refuses until
  the method is posted on CIRCT's forum:
  `python -m circt_bug_loop.approve --db <abs loop.db> approve <candidate> --by "<name>" --forum-post-url <url> --forum-post-date <date>`
- No credentials live here; `loop.db` and artefact roots are git-ignored.

## Results data

The registered campaigns' database and artefacts are assets of the release
`data-2026-09-25` (the post-review runs are not in it):

| Asset | Contents | SHA-256 |
|---|---|---|
| `loop.db.zst` | every probe, verdict, reduced case, fingerprint, gate decision and ledger row (465 MB unpacked) | `91374e8fce46c553e0f6210f58d32833b0e07f33a76e5cdd1178ce19d2c430a3` |
| `artefacts-campaigns-2-3.tar.zst` | inputs, logs and reduced cases of runs `f1e4fef5`, `73effefc`, `f0b2ef10`, `db45ab7b`, `460b7b48`, `91e58983` | `c39a75ddb22127398b23435d13b5300b2edbc34c1c0f384526ad67cfd5d592d5` |

```sh
B=https://github.com/DevAbhinav-23/CHIA_Hackathon_2k26/releases/download/data-2026-09-25
curl -LO $B/loop.db.zst -LO $B/artefacts-campaigns-2-3.tar.zst -LO $B/SHA256SUMS
sha256sum -c SHA256SUMS
zstd -d loop.db.zst -o circt_bug_loop/loop.db
mkdir -p ~/bugloop-artefacts && zstd -dc artefacts-campaigns-2-3.tar.zst | tar -xf - -C ~/bugloop-artefacts
.venv/bin/python analysis/measurements/campaign_aggregate.py    # regenerates the paper's Table II
```
