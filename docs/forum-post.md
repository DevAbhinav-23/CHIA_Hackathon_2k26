# Forum post (FR-20.1): draft for a human to post

**Where:** LLVM Discourse, category **CIRCT**
(https://discourse.llvm.org/c/projects-that-want-to-become-official-llvm-projects/circt/40).
**Who posts:** one of the three authors, under their own account and name.
**Then:** give the architect the post URL and its date; they go into the run
manifest through `--forum-post-url` and `--forum-post-date` (pre-flight check 11).
Nothing below is posted by the loop or by any agent.

---

**Title:** Heads-up: a small, human-gated bug-finding campaign against CIRCT (hackathon project)

Hello CIRCT maintainers,

We are three students at IIIT Hyderabad taking part in the CHIA hackathon at
the A³ workshop (MICRO 2026). Before we run anything that could reach your
issue tracker, we want to say what it is, how it will behave, and ask whether
you have objections or preferences.

**What it does.** A loop reads one past CIRCT fix commit at a time (its diff
and the test it touched), asks a model to name the class of mistake that fix
corrected and where else the same assumption might still stand, and writes
small inputs probing for it. Everything after that is ordinary tooling, not the
model: CIRCT is built at release-pinned main (the `firtool-1.159.0` LLVM pin)
with assertions **enabled**, the inputs run through `circt-opt`, `firtool` or
`circt-verilog`, a crash or assertion failure is reduced with `circt-reduce`,
and the result is fingerprinted and checked against your open and closed
issues and against commits since the build point. A second, report-only check
compares arcilator against Verilator on the few designs where both apply.

**How it behaves towards you.**

- Nothing is filed automatically. A named person reads every report and files
  it by hand, or does not. The loop's default is to file nothing.
- At most 3 issues per day and 10 in total, for the whole campaign.
- Every issue carries the reduced input, the exact command line and commit,
  the note that the build has assertions on, and the trailer
  `Assisted-by: <tool>:<model>` per CIRCT's AI tool policy.
- Duplicates are withheld. In our pilot the only failure found (an
  `isa<>` cast assertion in MooreToCore on a `moore.net` of an open array
  type) matched open issue #8508 and was not filed.
- Anything labelled `good first issue` is left alone.
- Your replies are read and answered by a human; nothing you write is fed to
  a model.
- We will not offer patches unless you say you want them; if we do, they are
  for crashes and assertion failures only, reviewed and understood by the
  author, and licensable under Apache-2.0 with LLVM exceptions.

**Timing.** One run of about four hours this week, then filings over the
following days, only after a human has looked at each.

**Two questions.** Would you prefer these as individual issues, or one tracking
issue with the reduced cases attached? Is there a label you would like on them?

Everything, including every input and the reports we decided not to file, will
be public at https://github.com/DevAbhinav-23/CHIA_Hackathon_2k26.

Thanks for your time, and please tell us if you would rather we did not do this.

<poster's name>, for Abhinav Venkata Kota, Adithya Jillellamudi and Priyesh Shukla
