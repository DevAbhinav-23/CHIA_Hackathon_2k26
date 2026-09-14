I wrote one input and named the tool I think should consume it.

```json
{
  "probes": [
    {"filename": "array_element.mlir", "tool": "firtool",
     "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
     "expected_outcome": "the element-type assertion fires"}
  ]
}
```
