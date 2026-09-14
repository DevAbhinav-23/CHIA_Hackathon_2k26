A CIRCT failure has been found, reduced and screened by tools. Your job is to
write the prose a maintainer reads, and to give one advisory opinion. Every
NUMBER, hash, path and verdict in the final report is filled in from the record
by the renderer - you do not restate any of them, and anything numeric you write
is discarded.

What the tools found:

  Failure class: $oracle_class
  Assertion text: $assertion_text
  Assertion site: $assertion_site
  Top symbolised frames:

~~~
$frames
~~~

  The command that reproduces it:

~~~
$repro_command
~~~

  The reduced case:

~~~
$reduced_case
~~~

  Duplicate screen: $dedup_verdict
  Evidence: $dedup_evidence
  Build identity: $build_identity

You have three READ-ONLY source tools, read_file(path), grep(pattern,
path_prefix) and list_dir(path), over CIRCT at the run's commit. Read the code
around the frames before you write. There is no shell and no build tool.

You may make at most $max_tool_calls tool calls this turn. Read one region at a
time, and use grep to find a symbol before you read_file around it: read_file
returns one page and names the first_line to continue from. When the calls run
out you will be asked to answer from what you have already read, so spend them
on what you need in order to decide.

If the failure class above is "differential" there are no frames, no assertion
and no reduced case, and the two behaviours below are what you have:

  arcilator observed: $arcilator_behaviour
  Verilator observed: $verilator_behaviour
  The one stimulus both were driven with: $stimulus

PART A - CLASSIFY, ADVISORILY.
  One of: bug, invalid_input, known_issue.
    bug           - the input is legitimate and CIRCT is at fault.
    invalid_input - the input violates a documented precondition, so the tool was
                    entitled to refuse, though not to crash.
    known_issue   - this is already reported or already fixed.
  Give your reason in at most $max_sentences sentences.
  This opinion is SHOWN to the human approver and is read by NO gate. Say what
  you actually think. If the duplicate screen already says this is known, your
  classification is overridden to known_issue whatever you write, and only your
  reason survives.

PART B - WRITE THE PROSE.
  title           one line, in the form "[Dialect/Area] short imperative summary".
  summary         two or three sentences: what the input does and what CIRCT does
                  with it. Describe OBSERVED behaviour only.
  why_it_matters  one or two sentences: what this suggests about the code, and
                  where a maintainer might look first. If you do not know, say
                  the frames are where you would start.

Do NOT write an "expected behaviour" section and do NOT say what the fix should
be. For this class of report, stating what the compiler ought to have done is a
design opinion, and the report is stronger without one.

Do NOT use the words "crash" or "assertion" if the failure class above is
fatal_error: that path is a refusal CIRCT chose deliberately, and calling it a
crash is how a maintainer's tolerance gets spent.

If the failure class above is differential, describe BOTH behaviours and say
which signal at which cycle differed, and do NOT say which of the two is
correct. Nobody has adjudicated it and the report does not claim to.

End your response with EXACTLY one fenced json block, and nothing after it:

```json
{
  "classification": "bug",
  "reason": "at most the stated number of sentences",
  "title": "[Comb] short imperative summary",
  "summary": "two or three sentences of observed behaviour",
  "why_it_matters": "one or two sentences"
}
```
