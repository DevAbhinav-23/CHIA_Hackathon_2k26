You are writing probing inputs for CIRCT, from the root-cause class and the
sibling sites of the previous turn. Each input is one small program that, if the
class of mistake really does apply at a site, makes the compiler crash or fire
one of its own assertions.

Seed: $seed_sha
Root-cause class: $root_cause_class

Sibling sites you named:

~~~
$sibling_sites
~~~

What the previous iteration's inputs did, if there was one:

~~~
$feedback
~~~

Write AT MOST $cap inputs. The language is fixed by the seed and is $language;
the tool that will consume them is fixed too and is $entry_tool, invoked with
this argument template, where INPUT is the file you write:

~~~
$argv_template
~~~

Rules that are not negotiable.

  1. Use the write_probe tool to write each input. It takes a bare file name and
     the file's content, and it writes into this iteration's probe directory. It
     will refuse a name with a directory part.
  2. Each input must be SELF-CONTAINED and as small as you can make it. Aim for
     something a maintainer can read in one screen. A large input that crashes
     is worth less than a small one, because the reducer has to shrink it anyway
     and a reduction that changes the failure is thrown away.
  3. Each input must be VALID for its language as far as you can make it. The
     interesting failures are the ones where valid input breaks the compiler; an
     input the parser rejects is recorded as a parse error and tells nobody
     anything.
  4. Target a specific sibling site. For each input, say which one.
  5. You cannot run the compiler and there is nothing here that would let you:
     your only tools are write_probe and the three read-only source tools. What
     your inputs do is measured by the apparatus, not reported by you.

State for each input what you expect to happen, in one clause, in the compiler's
own terms: which pass or which check you expect to break, not "it will crash".
Your expectation is recorded and compared with what actually happened; being
wrong is informative and is not penalised.

Write the files FIRST, then end your response with EXACTLY one fenced json block
describing what you wrote, and nothing after it. Name only files you actually
wrote successfully; a name in this block with no file behind it is dropped and
counted.

```json
{
  "probes": [
    {"filename": "extract_width.mlir",
     "site": "lib/Dialect/Comb/CombFolds.cpp:foldExtract",
     "expected_outcome": "the width assertion in foldExtract fires"}
  ]
}
```
