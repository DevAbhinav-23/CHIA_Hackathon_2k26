# Submission checklist

Two deadlines are open and two have passed. Both open ones take the same work.
<!-- all four rows: docs/abstract.md, "Where it goes" table -->

| Venue | What is due | Deadline |
|---|---|---|
| CHIA hackathon, final submission | "A 4-page paper plus your open-sourced loop and its results" | **2026-09-24 AoE** |
| A³ workshop (MICRO 2026), HotCRP `agentic-arch-2026.hotcrp.com` | Paper, "2-4 pages (excluding references)", "Double-column ACM/IEEE style" | **2026-09-21 AoE** |
| A³ workshop, abstract registration, same HotCRP | Abstract | Sep 14 AoE, **passed** |
| CHIA hackathon, short-term funding form | Project description and a compute-cost figure | Sep 13, **closed** |

## Done

| Item | Evidence |
|---|---|
| The 4-page paper, built | `paper/circt-bug-loop-paper-v4.pdf`, 4 pages, 0 overfull boxes, IEEEtran double column, source `paper/main.tex` |
| Abstract, three lengths, every number sourced | `docs/abstract.md` |
| The loop, open source, in the public team repo | `circt_bug_loop/`, at `https://github.com/DevAbhinav-23/CHIA_Hackathon_2k26` |
| Its results, rendered by the loop itself, per run | `~/bugloop-artefacts/f1e4fef5db314bef8d187bceca8f6a80/results/results.md` and the sibling shard's; aggregate in `paper/main.tex` Table II |
| Campaign 2 and campaign 3 records | `analysis/measurements/2026-09-15-campaign-2.md`, `analysis/measurements/2026-09-16-campaign-3.md`; regenerate with `python analysis/measurements/campaign_aggregate.py` |
| Two campaigns measured: 52 seeds, 758 probes, 84 candidates, 17 distinct new fingerprints, **15 through the gate**, 0 filed | store `circt_bug_loop/loop.db`, runs `f1e4fef5`, `73effefc`, `f0b2ef10`, `db45ab7b` |
| Test suite green at HEAD | 719 passed, 1 skipped, of 736 collected: `python -m pytest circt_bug_loop/tests -q -m "not t2 and not t3"` |
| Every run pre-registered before it ran | annotated tags `registration/pilot-1` to `-8`, `registration/campaign-1`, `registration/campaign-2`, `registration/campaign-3` (`git tag -l`) |
| The design set, gated and red-teamed | `design/00-README.md`, `design/reviews/` |
| The measurement record behind every number | `analysis/measurements/`, `analysis/pin-window-analysis.md` |
| What goes upstream to CHIA, written and tested | `upstream/README.md`; branch `bugloop` of the CHIA checkout at `~/Projects/chia-bugloop`, 11 commits, `PR-DESCRIPTION.md`, `UPSTREAM-CHECKLIST.md` |
| The forum post FR-20.1 requires, drafted | `docs/forum-post.md` |
| Entry points for a judge | `README.md`, `docs/explainer.md`, `docs/HANDOFF.md` |

## Pending

### Human authors

1. **Post the method to CIRCT's forum**, on LLVM Discourse under an author's own account and name. Nothing can be filed before it (FR-20.1). Draft: `docs/forum-post.md`.
2. **Approve the fifteen candidates**, one command each, cap 3 a day: `python -m circt_bug_loop.approve --db <abs loop.db> approve <id> --by "<name>" --forum-post-url <url> --forum-post-date <date>`. Campaign 2: `c-p-a2cb61b8d0aa`, `c-p-075cf1d70f3a`, `c-p-356e9e6e061d`. Campaign 3, shard `db45ab7b`: `c-p-9e7eceaadf12`, `c-p-4f35dc62470e`, `c-p-372f1e9ed476`, `c-p-3d0f9c33ee0a`, `c-p-31a7a300f2e2`, `c-p-a3a1556793d7`, `c-p-509c5aa72a94`, `c-p-4b9f84841ec3`, `c-p-f0ca5e81cf0d`. Campaign 3, shard `f0b2ef10`: `c-p-a52c6ed44c29`, `c-p-4d7a36e3ce15`, `c-p-8f95e19612ec`. Ready-to-run lines are in `analysis/measurements/2026-09-16-campaign-3.md`. <!-- latest gate decision = report: store query in that record -->
3. **File the issues** on `llvm/circt` (`approve … url` prints the pre-filled GitHub URL) and record each issue URL back into the run with the `filed` subcommand. The registered caps are 3 filings a day and 10 per run, so the fifteen cannot all be filed under one run's registration.
4. **Submit the paper to the A³ HotCRP by 2026-09-21 AoE**, and ask the chairs first whether a paper may still be submitted with no registered abstract, that registration having closed on Sep 14 AoE.
5. **Submit to the hackathon by 2026-09-24 AoE**: the paper, the repository and its results. Confirm with the organisers that one work may go to both the workshop and the hackathon; the hackathon page says its paper "does not preclude future conference or workshop publication", which is not the same statement. <!-- docs/abstract.md, note under the table -->
6. **GCP.** No form is owed: the short-term funding one closed on Sep 13. The Gemini API key was echoed into an agent transcript on 2026-09-14 (redacted from the one session file that held it; never in the repo). The user decided on 2026-09-15 not to rotate it: it is short-lived and auto-expires after the project.

### Architect

7. **Refresh the paper after the filings.** Table II's `Filed` row reads 0 in both campaign columns and the limitations open on "nothing has been filed at the time of writing"; both become the filed count and the issue numbers once step 3 lands.
8. **Push the upstream PR.** The CHIA checkout's `origin` is `ucb-bar/chia` itself, so a fork remote is needed first, and CHIA's `AGENTS.md` requires `Signed-off-by` on every commit. Blockers are listed in `~/Projects/chia-bugloop/UPSTREAM-CHECKLIST.md`.
