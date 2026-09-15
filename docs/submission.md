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
| The 4-page paper, built | `paper/circt-bug-loop-paper-v3.pdf`, 4 pages, IEEEtran double column, source `paper/main.tex` |
| Abstract, three lengths, every number sourced | `docs/abstract.md` |
| The loop, open source, in the public team repo | `circt_bug_loop/`, at `https://github.com/DevAbhinav-23/CHIA_Hackathon_2k26` |
| Its results, rendered by the loop itself, per run | `~/bugloop-artefacts/f1e4fef5db314bef8d187bceca8f6a80/results/results.md` and the sibling shard's; aggregate in `paper/main.tex` Table II |
| Test suite green at HEAD | 719 passed, 1 skipped, of 736 collected: `python -m pytest circt_bug_loop/tests -q -m "not t2 and not t3"` |
| Every run pre-registered before it ran | annotated tags `registration/pilot-1` to `-8`, `registration/campaign-1`, `registration/campaign-2` (`git tag -l`) |
| The design set, gated and red-teamed | `design/00-README.md`, `design/reviews/` |
| The measurement record behind every number | `analysis/measurements/`, `analysis/pin-window-analysis.md` |
| What goes upstream to CHIA, written and tested | `upstream/README.md`; branch `bugloop` of the CHIA checkout at `~/Projects/chia-bugloop`, 11 commits, `PR-DESCRIPTION.md`, `UPSTREAM-CHECKLIST.md` |
| The forum post FR-20.1 requires, drafted | `docs/forum-post.md` |
| Entry points for a judge | `README.md`, `docs/explainer.md`, `docs/HANDOFF.md` |

## Pending

### Human authors

1. **Post the method to CIRCT's forum**, on LLVM Discourse under an author's own account and name. Nothing can be filed before it (FR-20.1). Draft: `docs/forum-post.md`.
2. **Approve the three candidates**, one command each, cap 3 a day: `python -m circt_bug_loop.approve --db <abs loop.db> approve <id> --by "<name>" --forum-post-url <url> --forum-post-date <date>`, for `c-p-a2cb61b8d0aa`, `c-p-075cf1d70f3a` and `c-p-356e9e6e061d`. <!-- the three: docs/HANDOFF.md 2026-09-15 11:40 and 12:10 entries -->
3. **File the three issues** on `llvm/circt` (`approve … url` prints the pre-filled GitHub URL) and record each issue URL back into the run with the `filed` subcommand.
4. **Submit the paper to the A³ HotCRP by 2026-09-21 AoE**, and ask the chairs first whether a paper may still be submitted with no registered abstract, that registration having closed on Sep 14 AoE.
5. **Submit to the hackathon by 2026-09-24 AoE**: the paper, the repository and its results. Confirm with the organisers that one work may go to both the workshop and the hackathon; the hackathon page says its paper "does not preclude future conference or workshop publication", which is not the same statement. <!-- docs/abstract.md, note under the table -->
6. **GCP.** No form is owed: the short-term funding one closed on Sep 13. The Gemini API key was echoed into an agent transcript on 2026-09-14 (redacted from the one session file that held it; never in the repo). The user decided on 2026-09-15 not to rotate it: it is short-lived and auto-expires after the project.

### Architect

7. **Refresh the paper after the filings.** Table II reads `Filed: 0, awaiting approval` (`paper/main.tex` line 317) and the limitations open on "nothing has been filed at the time of writing"; both become the filed count and the issue numbers once step 3 lands.
8. **Push the upstream PR.** The CHIA checkout's `origin` is `ucb-bar/chia` itself, so a fork remote is needed first, and CHIA's `AGENTS.md` requires `Signed-off-by` on every commit. Blockers are listed in `~/Projects/chia-bugloop/UPSTREAM-CHECKLIST.md`.
