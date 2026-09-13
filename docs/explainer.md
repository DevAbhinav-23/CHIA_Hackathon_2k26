# The CIRCT bug loop, explained

## 1. What CIRCT does, in plain words

Chips are not drawn by hand. A designer writes a circuit's behaviour in a programming-like language, and a compiler turns that into Verilog, the lower-level description silicon-layout tools accept. CIRCT is such a compiler, open-source, from the LLVM project; its inputs are FIRRTL, the form the Chisel hardware language produces, and SystemVerilog.

A CIRCT bug that crashes the compiler is an inconvenience: the designer sees it and works around it. A bug that makes CIRCT emit *wrong Verilog* is far worse, because the output looks fine and can reach fabrication before anyone notices. These are silent bugs, and they are why compiler-correctness work exists.

## 2. What CHIA is, and what its CIRCT loop already does

CHIA is the agent framework this hackathon is built around; an agent here is a large language model wired into a program that can read files, run commands, and decide what to do next. CHIA's CIRCT example, `circt_issue_solver`, chains phases: assess → reproduce → fix → verify → (regression repair) → writeup. It picks an open GitHub issue, judges whether it is a real bug, writes a reproduction script whose contract is "exit 0 **iff** fixed", attempts a fix, reruns the full test gate, and writes the pull-request description it *would* submit. It never touches GitHub: the README states "No GitHub writes — both flows only read."

Run on 16 randomly selected CIRCT issues, it fixed 5, and 3 became merged pull requests — at about an hour of human review per issue.

## 3. What the hackathon judges, and what is due

The hackathon is judged by the program committee of the A³ workshop at MICRO 2026. The prize is for the most creative agentic loop, so the loop is the deliverable, not a dataset or benchmark. Due 2026-09-24 AoE: "A 4-page paper plus your open-sourced loop and its results."

## 4. The problem, from the numbers

CHIA's CIRCT loop, like every repair agent of its kind, eats from the issue tracker — a queue other people fill. Over the past year CIRCT received 82 issues labelled `bug` and closed 65, so it is neither short of reported bugs nor ignoring them. What is not happening is the backlog draining: 101 bug-labelled issues are open, median age 911 days.

The binding constraint is maintainer attention, not bug supply; an agent that drains the queue faster does not relieve it. What would relieve it is bugs arriving already minimised, already checked against what is known, already carrying a candidate fix — and a loop that files nothing else. Each past fix is also a clue: a commit correcting one wrong assumption in a compiler pass usually leaves siblings elsewhere. CIRCT ships no in-tree fuzzing infrastructure, so nothing hunts them automatically.

## 5. The loop, stage by stage

**Seed (data).** We mined 187 commits from CIRCT's last two years that look like bug fixes. For 171 an exactly matching prebuilt package of the LLVM libraries CIRCT needs still exists, so they rebuild cheaply. Each carries a diff and the fixer's regression test.

**Generate (agent).** The agent reads a seed's diff and test, states the root-cause class, names other places in CIRCT where the same mistake could live, and writes inputs probing them. Inputs follow the seed's language: its test line says which tool it drives, and about 127 of the 187 seeds are unreachable from FIRRTL.

**Oracle (tool).** The oracle decides whether an input found a bug, and the primary one is unambiguous: the compiler crashed, or an internal assertion failed. A weaker second oracle runs the same design through CIRCT's simulator and through Verilator, an established independent one, and flags disagreement; it only produces reports.

**Reduce (tool).** A crashing input is usually large and mostly irrelevant. `circt-reduce`, which CIRCT ships, deletes parts of it and keeps each deletion while the crash persists, until what remains reads in a minute.

**Triage (tool, then agent).** Many crashes are the same crash. Candidates are grouped by assertion text and source location, by symbolised stack frames, and by a structural hash of the reduced input. Survivors are checked against CIRCT's open and closed issues and later commits; an agent then classifies each as a real bug, an invalid input, or a known issue, and writes the report a maintainer would read.

**Repair (agent).** CHIA's phase chain runs unchanged; the only addition is a new entry point, reading our local report instead of a GitHub issue. Repair is scoped to crashes and assertion failures, where correct behaviour is not in dispute.

**Gate (tool plus human).** The gate requires reproduction at the exact commit we built, a minimised input, a legal input, and no duplicate. Its verdict is report, report plus patch, or nothing. A named team member approves every filing, under a per-day cap.

## 6. Glossary

- **Assertion** — a check the compiler's authors wrote into the source saying something must be true there. Release builds compile them out for speed; left in, a violated assumption halts the program rather than quietly producing wrong output.
- **Crash oracle** — treating a crash or failed assertion as proof of a bug, no opinion needed about the right answer.
- **Differential testing** — running one input through two independent implementations and treating disagreement as a suspected bug.
- **Reducer** — a program that shrinks a failing input while keeping it failing.
- **Deduplication** — deciding two failures are the same bug, so only one report is filed.
- **Gate** — the final stage, whose purpose is to refuse; it throws the loop's own output away.
- **Pre-registration** — committing the budget and success criteria to a public repository *before* the run, so the result cannot be picked afterwards.
- **Contamination** — the risk that the agent "discovers" something memorised from training data because a public fix exists; such candidates are screened out and reported separately.
- **Prebuilt SDK / pin window** — CIRCT builds against one pinned commit of LLVM; a pin window is the stretch of CIRCT history sharing one pin. With a prebuilt package for that pin CIRCT builds in minutes; without one it does not build.

## 7. Why we believe the pieces work

**The corpus rebuilds.** 171 of the 187 seeds have an exactly matching prebuilt package, computed from the repository's history.

**One was actually built.** A stock release SDK compiled CIRCT — 1,027 targets in 939 seconds — and the bug's test failed at the commit before the fix and passed after.

**Assertions are off, and can be switched back on.** Under CHIA's build flags all 620 CIRCT compile commands define `NDEBUG`, and the built `circt-opt` holds no assertion-failure code: a CIRCT built with CHIA's flags is blind to the bugs we want. `-UNDEBUG` restores them — 605 of 605 targets build, 495 of 513 CIRCT object files reference the assertion handler, and CIRCT's tests still pass, 520 of 523.

**The tools exist.** `circt-reduce` ships with CIRCT, the CIRCT organisation publishes a lockstep simulator-against-simulator suite, and CHIA has the repair phases.

**The method has evidence elsewhere.** AFuzz applied the same reference-bug-to-siblings idea to JavaScript engines: 40 bugs in V8 in about a month, and 19 more in two other engines from the V8 seeds. FLEX, a non-agentic neural fuzzer for MLIR — the framework CIRCT is built on — found 80 unknown bugs in 30 days. Neither repairs nor withholds.

## 8. What we do not know yet

Nothing has run end to end: stages are verified one at a time, and no run has gone seed → generate → oracle → reduce → triage → repair → gate. The generator agent does not exist yet, nor the mutation-fuzzer arm it will be measured against. No bug has been found by this loop, and no CIRCT assertion has been seen firing on a generated input. We have no estimate of yield — how many bugs a unit of compute buys here — and no idea how many machine-written reports maintainers will tolerate.

## 9. What a good result looks like

The headline is distinct, maintainer-confirmed bugs inside the pre-registered budget, seeded arm against mutation arm. Confirmed means a maintainer labelled, commented on, or fixed it; our oracle agreeing with itself makes a candidate, not a bug. Supporting numbers: candidates before and after deduplication, reports filed, gate precision (accepted reports divided by reports filed), and repairs merged. Zero is reportable: an account of a seeded generator that found nothing at a stated budget is still a result.

## 10. FAQ

**Why not just run a fuzzer?** That is the control arm; running it is part of the plan. A fuzzer plus a reducer leaves an unattributed pile of crashes — no duplicate check, no patch.

**What does the agent add?** For generation, that is what the head-to-head exists to answer. The rest is not in question: reproduction at a buildable commit, deduplication, an attempted repair, and a gate that discards. CHIA has none of those stages.

**Why not fix the open issues instead?** Because 101 open issues at a median age of 911 days is not a shortage of reported bugs. More unreviewed patches consume the scarce resource.

**Why crashes before wrong-output bugs?** A crash needs no judgement call. A wrong-output bug needs someone to establish the right output, and the simulator comparison that would do that is not yet trustworthy about uninitialised and reset signals.

**Why only one repository?** The seed corpus, the prebuilt-package analysis and the assertion measurement are all CIRCT-specific and took real work; a second target would halve the evidence.

**What if we find nothing?** We report that, with the budget committed in advance and the mutation arm's result. Pre-registration is what makes a null result publishable.
