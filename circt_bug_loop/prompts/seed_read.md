You are reading one CIRCT bug fix in order to look for the same mistake somewhere
else. You are NOT fixing anything and you are NOT writing any input this turn.

Fix commit: $seed_sha
Subject: $subject
Entry tool for this seed's tests: $entry_tool

The fix, as a diff:

~~~diff
$diff
~~~

The test files it changed:

~~~
$test_files
~~~

The lit RUN: lines in those tests, verbatim:

~~~
$run_lines
~~~

You have three READ-ONLY MCP tools over the CIRCT source at the run's commit:
read_file(path), grep(pattern, path_prefix) and list_dir(path). Use them to read
source, search for a symbol, and read the dialect docs and the op
summary/description fields in the *.td files. There is no shell, no build tool
and no test tool this turn, by design: nothing you can call changes anything or
measures anything.

You may make at most $max_tool_calls tool calls this turn. Read one region at a
time, and use grep to find a symbol before you read_file around it: read_file
returns one page and names the first_line to continue from. When the calls run
out you will be asked to answer from what you have already read, so spend them
on what you need in order to decide.

Do two things, in this order.

PART A - THE ROOT CAUSE CLASS.
  State, in ONE sentence, the KIND of mistake this fix corrected. A class, not an
  instance: "a pass assumed every operand of an operation is of the same width"
  is a class; "commit abc123 fixed FooOp" is not. The sentence must be usable as
  a search key by someone who has never seen this commit.

PART B - SIBLING SITES.
  Name up to $max_sites OTHER places in CIRCT where the same class of mistake
  plausibly still applies. A site is a file path and a symbol in that file, and
  BOTH must exist AT THE BUILD COMMIT, which is the tree you can read right now
  and is not the seed's own commit - check each one with grep before you name it,
  because a site that does not resolve is discarded and wastes the budget that
  produced it.
  Prefer sites that are analogous in structure rather than merely nearby in the
  directory tree: the same pattern in a different dialect is a better sibling
  than the next function down in the same file.
  For each site give one short clause saying why the class applies there.

Be honest about a weak seed. If the fix is a typo, a comment, a test-only change,
or something with no transferable class at all, say so in Part A and return an
EMPTY sibling list. An empty list is a correct answer and is recorded as one; an
invented list is not.

End your response with EXACTLY one fenced json block, and nothing after it:

```json
{
  "root_cause_class": "one sentence, as in Part A",
  "sibling_sites": [
    {"file": "lib/Dialect/Comb/CombFolds.cpp", "symbol": "foldExtract",
     "why": "one short clause"}
  ]
}
```
