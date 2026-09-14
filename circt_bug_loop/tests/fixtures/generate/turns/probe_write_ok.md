I wrote two inputs with write_probe, one per resolved site.

```json
{
  "probes": [
    {"filename": "array_element.mlir",
     "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
     "expected_outcome": "the element-type assertion in parseHWArray fires"},
    {"filename": "array_zero.mlir",
     "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
     "expected_outcome": "a zero-length array is accepted where it should not be"}
  ]
}
```
