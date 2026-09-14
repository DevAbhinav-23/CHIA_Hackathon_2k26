I wrote ten inputs with write_probe.

```json
{
  "probes": [
    {
      "filename": "probe_01.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 1 reaches the element-type assertion"
    },
    {
      "filename": "probe_02.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 2 reaches the element-type assertion"
    },
    {
      "filename": "probe_03.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 3 reaches the element-type assertion"
    },
    {
      "filename": "probe_04.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 4 reaches the element-type assertion"
    },
    {
      "filename": "probe_05.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 5 reaches the element-type assertion"
    },
    {
      "filename": "probe_06.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 6 reaches the element-type assertion"
    },
    {
      "filename": "probe_07.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 7 reaches the element-type assertion"
    },
    {
      "filename": "probe_08.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 8 reaches the element-type assertion"
    },
    {
      "filename": "probe_09.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 9 reaches the element-type assertion"
    },
    {
      "filename": "probe_10.mlir",
      "site": "lib/Dialect/HW/HWTypes.cpp:parseHWArray",
      "expected_outcome": "input 10 reaches the element-type assertion"
    }
  ]
}
```
