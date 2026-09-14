# The CIRCT bug loop, explained

## What the loop is

CIRCT is the LLVM project's open-source hardware compiler: it turns FIRRTL and SystemVerilog into the Verilog that silicon-layout tools accept. A crash in it is an inconvenience, because the designer sees it and works around it. Wrong Verilog is not: the output looks fine and can reach fabrication before anyone notices.

CHIA is the agent framework this hackathon is built around. Its CIRCT example picks an open GitHub issue and chains assess, reproduce, fix, verify and writeup; it reads the tracker and never writes to it. The tracker is also the constraint. CIRCT is neither short of reported bugs nor ignoring them, and its backlog still does not drain, because what is scarce is maintainer attention rather than bug supply. An agent that empties the queue faster does not relieve that.

This loop runs in the other direction. It mines past CIRCT fix commits, has an agent write new inputs probing for sibling bugs of each fix, judges them with an assertions-on crash oracle, reduces what fires, deduplicates it against what is already known, attempts a repair through CHIA's own phase chain, and gates every filing behind a named human. A report it files arrives minimised, screened and carrying a candidate patch; anything else it throws away.

## The seven stages

1. **Seed** — mine bug-fix commits from CIRCT's recent history, keep those whose pinned LLVM build still has a prebuilt package, and carry each one's diff and regression test.
2. **Generate** — an agent reads one seed's diff and test, states the root-cause class, names sibling sites in CIRCT where the same mistake could live, and writes probing inputs in the seed's own language.
3. **Probe** — run each input on the tool its seed drives, inside the assertions-on image, under fixed wall-clock and memory limits.
4. **Oracle** — a crash or a failed internal assertion is the primary verdict; a second, report-only oracle runs the design through CIRCT's simulator and Verilator and flags disagreement.
5. **Reduce** — `circt-reduce` shrinks a firing input while the failure persists, until what remains reads in a minute.
6. **Triage** — group candidates by assertion text, symbolised frames and a structural hash, screen the survivors against open and closed issues and later commits, and have an agent classify each and write the report a maintainer would read.
7. **Repair** — CHIA's phase chain runs unchanged behind a new entry point that reads the local report instead of a GitHub issue, scoped to crashes and assertion failures, where correct behaviour is not in dispute.

The gate then asks four questions of every candidate: reproduction at the exact commit the image was built from, a minimised input, a legal input, and no duplicate. Its verdict is report, report plus patch, or nothing, and a named team member approves each filing under a per-day cap.

## What is measured

The headline is distinct maintainer-confirmed bugs inside a pre-registered budget, seeded arm against a mutation-fuzzer arm that shares the harness, oracles, reducer and gate and differs only in its generator. Confirmed means a maintainer labelled, commented on or fixed it; the loop's own oracle agreeing with itself makes a candidate, not a bug.

Supporting counts: probes written and probes that fired, candidates before and after deduplication, which gate question each candidate stopped at, reports filed, gate precision, and repairs merged.

Money is measured the same way. Every model turn is pre-authorised against a campaign cap before it is dispatched and its authorised, ceiling and billed dollars are written to a ledger, so a run's spend is bounded in advance and reconciled after.

Zero is reportable. An account of a seeded generator that found nothing at a stated budget, against a mutation arm at the same budget, is still a result; pre-registering the budget in the repository beforehand is what makes it publishable.

## What is pending

The full two-arm campaign has not been run: the loop has been exercised end to end only at pilot scale, on a named subset of seeds and a small spend cap. No bug found by this loop has been confirmed by a CIRCT maintainer, and none has been filed. Yield — how many bugs a unit of compute buys here — is unestimated, and so is how many machine-written reports maintainers will tolerate.
