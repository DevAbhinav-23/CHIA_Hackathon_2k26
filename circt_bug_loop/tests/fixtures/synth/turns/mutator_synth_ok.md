I read the closed reports and kept the differences that recur in them.

```json
{
  "mutators": [
    {"id": "mlir.attr.int.off_by_one", "language": "mlir", "kind": "text",
     "mutates_argv": false, "description": "shift one integer attribute by one",
     "pattern": "(?<![\\w.])(\\d+)\\s*:\\s*i(\\d+)", "replacement": "off_by_one",
     "derived_from": [10588]},
    {"id": "sv.range.msb.zero", "language": "sv", "kind": "text",
     "mutates_argv": false, "description": "make one packed range's msb zero",
     "pattern": "\\[(\\d+)\\s*:\\s*0\\]", "replacement": "zero",
     "derived_from": [10711, 10588]},
    {"id": "any.line.duplicate", "language": "any", "kind": "line",
     "mutates_argv": false, "description": "repeat one non-blank line",
     "pattern": "\\S", "replacement": "duplicate", "derived_from": []}
  ]
}
```
