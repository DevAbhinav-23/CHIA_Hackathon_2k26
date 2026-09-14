# Seed, generate, reduce, repair, gate: abstract and short forms

## Where it goes

This abstract is written for two things, and they take the same text: the **CHIA
hackathon final submission** (4-page paper plus the open-sourced loop and its results) and
the **A³ workshop paper**. It is no longer an abstract-registration text: that deadline has
passed.

| Venue | What is due | Deadline | Status on 2026-09-16 |
|---|---|---|---|
| CHIA hackathon final submission | "A 4-page paper plus your open-sourced loop and its results" | **2026-09-24 AoE** | **open**, and this is the target |
| A³ workshop (MICRO 2026), HotCRP `agentic-arch-2026.hotcrp.com` | Paper: "2–4 pages (excluding references)", "Double-column ACM/IEEE style" | **2026-09-21 AoE** | open; the abstract below is the paper's |
| A³ workshop, same HotCRP | Abstract registration | Sep 14 AoE (site: "Tuesday Sep 15, 2026, 7:59:59 AM EDT") | **passed**; ask the chairs whether a paper may still be submitted without a registered abstract |
| CHIA hackathon short-term funding form (Google Form) | Paragraph field "Project description/overview" plus a required total compute-cost figure | closed Sep 13 | **passed** |

The hackathon page states that its paper "does not preclude future conference or workshop
publication". Confirm with the organisers that one work may go to both the workshop and the
hackathon before depending on it.

## Title

**Seed, generate, reduce, repair, gate: a closed CIRCT bug loop**

## Authors

Abhinav Venkata Kota, Adithya Jillellamudi, Priyesh Shukla (IIIT Hyderabad)

## Abstract (about 200 words, quantified)

CIRCT is an open-source compiler that turns hardware descriptions into Verilog, so a defect
in it can corrupt a chip unnoticed. Agents that repair CIRCT take their work from its issue
tracker, which only scarce maintainer attention drains. We built a loop that makes its own supply: an agent reads one of 187 fix
commits mined from 24 months of CIRCT history,
<!-- 187 fix-shaped commits over 24 months: analysis/pin-window-analysis.md, headline table and lines 112-113 -->
171 of them rebuildable against a stock prebuilt compiler SDK,
<!-- 171 of 187 have an exactly matching prebuilt-LLVM SDK: analysis/pin-window-analysis.md line 14 -->
names the class of mistake the fix corrected, and writes fresh inputs probing for it
elsewhere. Fixed tools, not the model, build, judge, minimise, deduplicate and repair; a
named person approves every filing. CHIA's CIRCT image compiles out every internal
consistency check the compiler's authors wrote, so an oracle waiting for one never fires;
<!-- CHIA's published chia-circt image: 606 of 606 compile commands carry -DNDEBUG and circt-opt has 0 undefined __assert_fail: analysis/measurements/2026-09-13-frd-followups.md lines 469-470 and A-10 -->
restored, they reach 536 of 555 compiler objects,
<!-- 536 of 555 obj.CIRCT objects reference the assertion handler: analysis/measurements/2026-09-14-image-build.md 4, FR-03.5 -->
cost 18% of build time,
<!-- +179 s = 18.4% of wall clock against the assertions-off twin: analysis/measurements/2026-09-14-image-build.md, W-04b 1 -->
and leave CHIA's test gate at 1,119 passes and 0 failures, identical with the checks off.
<!-- 1,119 passed / 0 failed of 1,127 considered, identical in both images: analysis/measurements/2026-09-14-image-build.md 5 run 2 and W-04b 3 -->
Six real CIRCT failures, replayed, exposed two defects that would have put three of four
bugs beyond the repair stage.
<!-- 6 confirmed fixtures of 7 attempts: analysis/measurements/2026-09-14-crash-fixtures.md 1; the two frame defects and "three of the four real bugs are out of scope": same file 3.2 and 3.4 -->
We release the loop as CHIA nodes and tools; the pre-registered campaign against a mutation
fuzzer is running, and will report its maintainer-confirmed bug count.

## Short (100 words)

CIRCT compiles hardware descriptions into Verilog; a defect in it can corrupt a chip
unnoticed. Repair agents feed on its issue tracker, which only maintainers drain. Our loop
makes its own supply: an agent reads one of 187 mined CIRCT fixes,
<!-- 187 fix-shaped commits over 24 months: analysis/pin-window-analysis.md -->
names the mistake, and probes for it elsewhere; fixed tools build, judge,
minimise, deduplicate and repair; a person approves every filing. CHIA's CIRCT image
compiles out the compiler's consistency checks, so nothing can fire; restored, they cost
18% of build time and leave CHIA's 1,119-test gate at 0 failures.
<!-- +18.4% wall clock, and 1,119 pass / 0 fail identical with the checks off: analysis/measurements/2026-09-14-image-build.md W-04b 1 and 3 -->
The pre-registered campaign against a mutation fuzzer is running.

## One paragraph for a form (150 words)

CIRCT is the open-source compiler that turns hardware descriptions into Verilog, so a
defect in it can corrupt a chip unnoticed, and the agents that repair it feed on an issue
queue only maintainers drain. We built a loop that manufactures its own supply and
withholds most of it: an agent reads one of 187 CIRCT fix commits mined from 24 months,
171 of them rebuildable against a stock prebuilt compiler SDK,
<!-- 187 mined over 24 months, 171 with an exactly matching prebuilt SDK: analysis/pin-window-analysis.md line 14 -->
names the class of mistake each corrected, and writes fresh inputs probing for it
elsewhere, after which fixed tools build, judge, minimise, deduplicate and repair; a named
person approves every filing. Two preconditions were measured and repaired first: the
compiler's own consistency checks, absent from CHIA's image, are restored at 18% of build
time and 0 new test failures,
<!-- 536 of 555 objects; +18.4% wall clock; 1,119 pass / 0 fail, identical with the checks off: analysis/measurements/2026-09-14-image-build.md 4, W-04b 1 and 3 -->
and the oracle was calibrated on six real CIRCT failures.
<!-- 6 confirmed fixtures of 7 attempts: analysis/measurements/2026-09-14-crash-fixtures.md 1 -->
The pre-registered campaign against a mutation fuzzer is running.

## Suggested HotCRP topic

Infrastructure & Methodology: benchmarks and metrics for agentic hardware-design tasks;
debugging agent trajectories in design flows.

---

Every number above carries its source in an HTML comment beside it. The same numbers, with
the same sources, are in `paper/main.tex`; the wider measurement record is
`analysis/measurements/`, `analysis/pin-window-analysis.md` and
`design/reviews/implementation-errata-log.md`.
