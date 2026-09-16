# From Mined Fixes to Gated Repair: Closed-Loop Defect Synthesis for CIRCT

CHIA Hackathon 2026 (A³ workshop @ MICRO 2026). Team: Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla (IIIT Hyderabad).

CIRCT is the LLVM project's hardware compiler, and the agents that repair it draw from an issue queue that only maintainer attention drains. This loop manufactures its own supply and withholds most of it. Seven stages run in order on CHIA: **seed** (one of 187 fix commits mined from 24 months of CIRCT history, with its diff and its test), **generate** (an agent states the root-cause class the fix corrected and writes fresh inputs probing for the same mistake elsewhere), **build** (at release-pinned main, with the compiler's own assertions compiled back in), **judge** (a crash, a failed assertion, or the compiler's verifier refusing its own output; a Verilator differential reports only), **reduce** (`circt-reduce`, with a textual reducer where it dies), **triage** (fingerprint, then screen against a local mirror of the tracker and against commits made since the pin), **repair** (CHIA's phase chain unaltered, entered by a local report), then the **human gate**. The agent acts at three of those stages; every number in the result is produced by a tool.
<!-- 187 seeds over 24 months: analysis/pin-window-analysis.md; the stages and the three agent stages: paper/main.tex II -->

## The result

Two registered campaigns, seeded arm: 52 seeds, 758 probes, 84 candidates, 17 distinct new fingerprints and **15 new bugs through the gate**, three in the Moore-to-core extract lowering and twelve spread across the compiler, among them two segmentation faults and an `om` dialect abort. <!-- analysis/measurements/2026-09-15-campaign-2.md and 2026-09-16-campaign-3.md; paper/main.tex Table II -->
Campaign 3 was stopped by the operator at 43 of 187 seeds after 11.9 hours, well inside its registered window and spend cap. <!-- 2026-09-16-campaign-3.md -->
Mutation arm, sharing the harness, oracles, reducer and gate: 2,308 mutants over two runs, 0 firings, 0 candidates. <!-- runs 460b7b48 and 91e58983 -->
USD 189 at list price for every live model call of the project, pilots and both campaigns together; the real bill is lower by the cached share. <!-- 65.99 + 122.77; paper/main.tex V -->

Nothing has been filed. Filing is a named human's act, and it follows the forum post.

## Where things are

| Path | What |
|---|---|
| `paper/circt-bug-loop-paper-v4.pdf` | The 4-page paper (source `paper/main.tex`, built by `paper/build.sh`) |
| `circt_bug_loop/` | The loop: CHIA nodes and tools, the frozen contract (`contract/FROZEN.md`), the driver `bug_loop.py`, the budget file, the tests |
| `design/00-README.md` | Entry point to the formal design set: FRD, HLD, LLD, test plan, work plan, ADRs, red-team reviews |
| `analysis/measurements/` | Every measurement with its script and raw output: the image build, the crash fixtures, eight pilots, the repair runs |
| `upstream/README.md` | The four files proposed to CHIA core, and why each exists |
| `docs/HANDOFF.md` | The running state of the work, newest entries last; read it first |
| `docs/explainer.md` | The same story for a reader new to CIRCT and to CHIA |

## Running it

On a machine that has never seen this repository run `./scripts/setup.sh` first — it builds `.venv` from `requirements.txt` and the pinned CHIA checkout — and see [`docs/RUN.md`](docs/RUN.md) for the three levels: tests, inspecting a past run, and a live campaign.

Tests: `python -m pytest circt_bug_loop/tests -q -m "not t2 and not t3"` selects 720 of the suite's 736 tests and passes 719 with 1 skipped. Of those, the 686 that `-m t0` selects need no CIRCT binary, no clone, no network and no model; the other 34 want the prebuilt SDK or a blobless `llvm/circt` clone. <!-- measured 2026-09-15 at HEAD under ~/.cache/chia-venv-py31019; markers defined in pytest.ini -->

**Registration.** A run is registered by an annotated git tag `registration/<run>` on the commit that lands its `budget.yaml`. The loop refuses a budget file no such tag names, and refuses a mutator set committed after the tag, so no threshold can be chosen after the fact. <!-- circt_bug_loop/budget.py REGISTRATION_TAGS and registration(); the tags themselves are listed by `git tag -l` -->

**Live-model interlock.** No stage can build a model client unless `BUGLOOP_ALLOW_LIVE_MODEL=1` is set for that run, so a test, a dry run or a mistake cannot reach the model. <!-- circt_bug_loop/llm.py _LIVE_MODEL_ENV; circt_bug_loop/bug_loop.py LIVE_MODEL_ENV -->

**Approval.** Filing is a command a person runs: `python -m circt_bug_loop.approve --db <abs loop.db> approve <candidate> --by "<name>" --forum-post-url <url> --forum-post-date <date>`. Nothing is filed by default, the approver is named in the record, and the command refuses every filing until the method has been posted to CIRCT's forum (FR-20.1). <!-- circt_bug_loop/approve.py FORUM_FIELDS and the FR-20.1 refusal, lines 99 to 161; draft post at docs/forum-post.md -->

No credentials live in this repository. Runtime state (`loop.db`, artefact roots) is ignored by `.gitignore`.
