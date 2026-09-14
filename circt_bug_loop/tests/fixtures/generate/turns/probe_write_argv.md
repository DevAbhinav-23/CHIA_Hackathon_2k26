I wrote one input, and I have also written down how I would run it.

```json
{
  "probes": [
    {"filename": "array_element.mlir",
     "argv": ["--mlir-print-ir-after-all", "--some-option-nobody-asked-for"],
     "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
     "expected_outcome": "the element-type assertion fires"}
  ]
}
```
