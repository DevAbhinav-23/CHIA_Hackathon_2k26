# Seed, generate, reduce, repair, gate — abstract and short forms

## Where it goes

| Venue | What is due | Deadline |
|---|---|---|
| A³ workshop (MICRO 2026), HotCRP `agentic-arch-2026.hotcrp.com` | Abstract registration | Site shows "Registration deadline: Tuesday Sep 15, 2026, 7:59:59 AM EDT" = **Sep 14 AoE** |
| A³ workshop, same HotCRP | Paper: "2–4 pages (excluding references)", "Double-column ACM/IEEE style" | **Sep 21 AoE** |
| CHIA hackathon short-term funding form (Google Form) | Optional paragraph field "Project description/overview" — instructions ask for overview, methodology, expected results and cost estimate details — plus a required "Total estimated compute cost expected in USD" | **closes Sep 13** |
| CHIA hackathon final submission | "A 4-page paper plus your open-sourced loop and its results" | **Sep 24 AoE** |

The hackathon page states that its paper "does not preclude future conference or workshop publication". Confirm with the organisers that one work may go to both the workshop and the hackathon before depending on it.

The HotCRP site states no abstract length limit. The version below targets 250 words.

## Title

**Seed, generate, reduce, repair, gate: a closed CIRCT bug loop**

## Authors

Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla — IIIT Hyderabad

## Abstract

CIRCT is an open-source compiler that turns hardware descriptions into Verilog, the language from which physical circuits are built, so a defect in it can silently change a shipped chip. Agents that repair CIRCT take their work from the project's issue tracker, which bounds throughput by what users report and maintainers review: 82 bug-labelled issues were filed in the past year and 65 closed, while 101 stay open at a median age of 911 days. Attention, not supply, is the binding constraint.

We propose a loop that makes its own supply. From 187 mined CIRCT fix commits, 171 rebuildable against an exact prebuilt compiler SDK, an agent reads each fix, states the root-cause class it repaired, and writes fresh inputs in the language that seed's test uses. The oracle — the rule deciding whether an input has found a bug — is a crash or failed CIRCT assertion, an internal consistency check that CHIA's build flags compile out and that we restore. Running CIRCT's simulator against an established independent one is a secondary, report-only oracle. `circt-reduce` shrinks each candidate, deduplication drops repeats, CHIA's existing repair phases are entered through a local-report supply node, and a gate withholds anything unreproduced, unminimal or already known, with a named team member approving every filing.

Evaluation runs the seeded generator against a mutation fuzzer at equal pre-registered budget under identical tools, oracles and gate. The headline is distinct, maintainer-confirmed bugs; zero is reportable. The artifact is the loop as composable CHIA blocks.

## Short version (≤ 100 words)

CIRCT compiles hardware descriptions into Verilog, so a defect can silently change a shipped chip. Repair agents feed on its issue tracker, and that tracker is attention-bound: 82 bug-labelled issues filed in a year, 65 closed, 101 still open at a median age of 911 days. We build a CHIA loop that makes its own supply. An agent turns 187 mined fix commits into new inputs, restored CIRCT assertions catch them, `circt-reduce` shrinks them, CHIA's repair phases run, and a gate withholds everything a human has not approved. Headline: distinct, maintainer-confirmed bugs against a mutation-fuzzer arm at equal pre-registered budget.

## Form version (≤ 180 words) — Google Form "Project description/overview"

**Overview.** CIRCT compiles hardware descriptions into Verilog; a defect can silently change a shipped chip. Agentic repair loops draw work from CIRCT's issue tracker, so throughput is bounded by what users report and maintainers review — 82 bug-labelled issues filed in a year, 65 closed, 101 still open at a median age of 911 days. We build a CHIA loop that manufactures its own supply of bugs and withholds the ones it cannot stand behind.

**Methodology.** An agent reads each of 187 mined CIRCT fix commits (171 rebuildable against an exact prebuilt SDK), states the root-cause class, and generates inputs in that seed's own input language. Crashes and restored CIRCT assertions are the oracle; `circt-reduce` minimises; CHIA's repair phases run via a local-report entry; a gate requires a human approval before any filing.

**Expected results.** Distinct maintainer-confirmed CIRCT bugs, seeded arm versus a mutation-fuzzer arm at equal budget. Zero is a reportable outcome.

**Cost.** The budget — GPU-hours, input cap, filing cap — is set in the pre-registered budget file committed to the public loop repository before the campaign starts.

## Suggested HotCRP topic

Infrastructure & Methodology: benchmarks and metrics for agentic hardware-design tasks; debugging agent trajectories in design flows.

---

Every number above is sourced in problem-statement-FINAL.md, Appendix A.
