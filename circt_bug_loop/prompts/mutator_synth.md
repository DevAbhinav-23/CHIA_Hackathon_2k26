You are writing a set of MUTATORS for a SystemVerilog, FIRRTL and MLIR fuzzing
baseline against the CIRCT compiler. A mutator is a small, deterministic,
mechanical edit to a test input. It has no understanding of the program it edits
and it is never allowed to acquire any.

Below are $issue_count closed CIRCT issues labelled bug, the full history of
them as of the mirror this synthesis ran against. Read them for ONE thing only:
what kinds of small, mechanical input differences have historically broken this
compiler.

~~~
$issues
~~~

Write about $target_count mutators covering these languages: $languages.

What a good mutator looks like.
  - It is a rewrite, not a generator: it edits an existing valid test into a
    slightly different one.
  - It is deterministic given the input text and an integer seed, and it uses the
    seed only to CHOOSE among candidate sites, never to invent content.
  - It is cheap: a regular expression or a line operation, not a parser.
  - It is plausible: the output should usually still parse. A mutator whose
    output is always rejected by the parser measures nothing.
  - It targets something the issues below show actually breaks CIRCT: widths,
    zero-width values, attribute bounds, symbol references, region and block
    structure, operand counts, self-reference, deep nesting, unusual but legal
    literals.

What a mutator is NOT.
  - It is not a fix, a diagnosis, or a hypothesis about a specific bug.
  - It does not read a commit, a diff, or a root-cause description. The arm that
    uses this set is the BASELINE and at run time it sees only test files.
  - It does not call a model. Once frozen, this set runs with no model at all.

For each mutator give: a dotted id of the form language.target.operation; the
language it applies to; the kind, one of text, line or argv; a one-clause
description; the pattern; the replacement, which is a literal, a back-reference
template, or one of the named operations flip, zero, max, off_by_one, duplicate,
delete, swap; and the issue numbers that suggested it.

Prefer twenty sharp mutators to sixty vague ones. A mutator that fires on every
input and changes nothing meaningful costs the baseline its whole budget.

End your response with EXACTLY one fenced json block, and nothing after it, whose
shape is the mutators array of the frozen set:

```json
{
  "mutators": [
    {"id": "mlir.attr.int.off_by_one", "language": "mlir", "kind": "text",
     "mutates_argv": false, "description": "shift one integer attribute by one",
     "pattern": "(?<![\\w.])(\\d+)\\s*:\\s*i(\\d+)", "replacement": "off_by_one",
     "derived_from": [10588]}
  ]
}
```
