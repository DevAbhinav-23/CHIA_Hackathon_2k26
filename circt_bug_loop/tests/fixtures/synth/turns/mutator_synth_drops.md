Here is the set. Some of these I am less sure about than others.

```json
{
  "mutators": [
    {"id": "mlir.attr.int.off_by_one", "language": "mlir", "kind": "text",
     "mutates_argv": false, "description": "the one entry that survives",
     "pattern": "(?<![\\w.])(\\d+)\\s*:\\s*i(\\d+)", "replacement": "off_by_one",
     "derived_from": [10588]},
    {"id": "mlir.pattern.uncompilable", "language": "mlir", "kind": "text",
     "mutates_argv": false, "description": "a pattern that will not compile",
     "pattern": "(unclosed", "replacement": "zero", "derived_from": []},
    {"id": "NotDotted", "language": "mlir", "kind": "text",
     "mutates_argv": false, "description": "an id that is not 8.1's form",
     "pattern": "x", "replacement": "zero", "derived_from": []},
    {"id": "mlir.attr.int.off_by_one", "language": "mlir", "kind": "text",
     "mutates_argv": false, "description": "the same id a second time",
     "pattern": "y", "replacement": "zero", "derived_from": []},
    {"id": "vhdl.attr.int.zero", "language": "vhdl", "kind": "text",
     "mutates_argv": false, "description": "a language outside the set",
     "pattern": "z", "replacement": "zero", "derived_from": []},
    {"id": "mlir.tree.rewrite", "language": "mlir", "kind": "ast",
     "mutates_argv": false, "description": "a kind outside the set",
     "pattern": "z", "replacement": "zero", "derived_from": []},
    {"id": "mlir.argv.undeclared", "language": "mlir", "kind": "argv",
     "mutates_argv": false, "description": "an argv mutator that hides it",
     "pattern": "^--", "replacement": "duplicate", "derived_from": []},
    {"id": "mlir.line.wrong_operation", "language": "mlir", "kind": "line",
     "mutates_argv": false, "description": "a numeric operation on a line kind",
     "pattern": "\\S", "replacement": "off_by_one", "derived_from": []},
    {"id": "mlir.attr.int.nofields", "language": "mlir",
     "description": "an entry missing kind, mutates_argv and replacement",
     "pattern": "q", "derived_from": []}
  ]
}
```
