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

THE REGULAR-EXPRESSION ENGINE IS PYTHON 3.10's `re`, AND NOTHING ELSE. Every
pattern is compiled by `re.compile(pattern)` and a pattern that raises
`re.error` is DROPPED, not repaired. Python's `re` is not PCRE:

  - A LOOK-BEHIND MUST BE FIXED WIDTH. `(?<=depth\s*=>\s*)` is REFUSED with
    `look-behind requires fixed-width pattern`, because `\s*` has no fixed
    width. Write `depth\s*=>\s*(\d+)` and use a capture group instead of
    looking behind at all, or use a fixed-width look-behind such as `(?<=%)`.
  - There is no `\K`, no possessive quantifier (`a*+`), no atomic group
    (`(?>...)`), no recursion (`(?R)`, `(?1)`), no conditional (`(?(1)a|b)`),
    no `\p{...}` Unicode property, and no branch reset (`(?|...)`).
  - `re.error` for any other reason - an unbalanced bracket, an unknown escape,
    a bad group name - drops the mutator just the same.

Prefer a capture group to a look-behind everywhere. It costs nothing: the
replacement may be a back-reference template, so the text you did not want to
change can simply be written back out.

THE THREE KINDS, AND THE SHAPE OF `replacement` FOR EACH. `replacement` is
never empty; an empty one is dropped.

  - `kind: "text"`, `mutates_argv: false`. The pattern is matched against the
    WHOLE test file and one match is chosen. `replacement` is either a literal
    or back-reference template expanded against that match (`\1`, `\g<name>`),
    or ONE of the four numeric operations `flip`, `zero`, `max`, `off_by_one`,
    which act on the first integer group of the match. It may NOT be one of the
    sequence operations.
  - `kind: "line"`, `mutates_argv: false`. The pattern is matched against each
    LINE and one matching line is chosen. `replacement` must be exactly one of
    the three sequence operations `duplicate`, `delete`, `swap`, which
    duplicate that line, delete it, or exchange it with the following one. A
    line mutator's replacement may be nothing else.
  - `kind: "argv"`, `mutates_argv: true`. The pattern is matched against each
    TOKEN of the tool's argument vector - the flags after `circt-opt`,
    `firtool` or `circt-verilog` on the test's RUN line - and one matching token
    is chosen. `replacement` is either one of the three sequence operations,
    which duplicate, delete or reorder that token, or a literal string that
    REPLACES the matched token (for example `--allow-unregistered-dialect`).

WRITE AT LEAST TWO `argv` MUTATORS AND AT LEAST TWO `line` MUTATORS, and spread
the set across the four language values `mlir`, `fir`, `sv` and `any`. A
mutator whose `language` is `any` runs against a test file of any of the three
languages and is the only kind that does. A set of one kind in one language
exercises one path of the baseline and measures the rest not at all.

For each mutator give: a dotted id of the form language.target.operation, which
must match `^[a-z0-9]+(\.[a-z0-9_]+){2,}$` - lower case, at least three
dot-separated segments, no capitals and no hyphens; the language it applies to,
one of mlir, fir, sv, any; the kind, one of text, line or argv; `mutates_argv`,
true for an argv mutator and false for the other two; a one-clause description;
the pattern; the replacement as described above; and the issue numbers that
suggested it.

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
     "derived_from": [10588]},
    {"id": "mlir.region.line_duplicate", "language": "mlir", "kind": "line",
     "mutates_argv": false, "description": "duplicate one operation line",
     "pattern": "^\\s*%\\w+\\s*=\\s*\\w+\\.", "replacement": "duplicate",
     "derived_from": [10588]},
    {"id": "any.argv.flag_delete", "language": "any", "kind": "argv",
     "mutates_argv": true, "description": "drop one pass or option flag",
     "pattern": "^--", "replacement": "delete", "derived_from": [10588]}
  ]
}
```
