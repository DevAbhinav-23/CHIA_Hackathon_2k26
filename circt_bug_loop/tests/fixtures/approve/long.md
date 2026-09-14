# circt-opt crashes in LowerTypes on a zero-width aggregate

## What happens
`circt-opt --lower-seq-to-sv` fails an assertion on the reduced input below.

## Reduced input
```mlir
hw.module @bugloop(in %a : i4, out b : i4) {
  %0 = comb.add %a, %b : i4    // operation 0 of the reduced case
  %1 = comb.add %a, %b : i4    // operation 1 of the reduced case
  %2 = comb.add %a, %b : i4    // operation 2 of the reduced case
  %3 = comb.add %a, %b : i4    // operation 3 of the reduced case
  %4 = comb.add %a, %b : i4    // operation 4 of the reduced case
  %5 = comb.add %a, %b : i4    // operation 5 of the reduced case
  %6 = comb.add %a, %b : i4    // operation 6 of the reduced case
  %7 = comb.add %a, %b : i4    // operation 7 of the reduced case
  %8 = comb.add %a, %b : i4    // operation 8 of the reduced case
  %9 = comb.add %a, %b : i4    // operation 9 of the reduced case
  %10 = comb.add %a, %b : i4    // operation 10 of the reduced case
  %11 = comb.add %a, %b : i4    // operation 11 of the reduced case
  %12 = comb.add %a, %b : i4    // operation 12 of the reduced case
  %13 = comb.add %a, %b : i4    // operation 13 of the reduced case
  %14 = comb.add %a, %b : i4    // operation 14 of the reduced case
  %15 = comb.add %a, %b : i4    // operation 15 of the reduced case
  %16 = comb.add %a, %b : i4    // operation 16 of the reduced case
  %17 = comb.add %a, %b : i4    // operation 17 of the reduced case
  %18 = comb.add %a, %b : i4    // operation 18 of the reduced case
  %19 = comb.add %a, %b : i4    // operation 19 of the reduced case
  %20 = comb.add %a, %b : i4    // operation 20 of the reduced case
  %21 = comb.add %a, %b : i4    // operation 21 of the reduced case
  %22 = comb.add %a, %b : i4    // operation 22 of the reduced case
  %23 = comb.add %a, %b : i4    // operation 23 of the reduced case
  %24 = comb.add %a, %b : i4    // operation 24 of the reduced case
  %25 = comb.add %a, %b : i4    // operation 25 of the reduced case
  %26 = comb.add %a, %b : i4    // operation 26 of the reduced case
  %27 = comb.add %a, %b : i4    // operation 27 of the reduced case
  %28 = comb.add %a, %b : i4    // operation 28 of the reduced case
  %29 = comb.add %a, %b : i4    // operation 29 of the reduced case
  %30 = comb.add %a, %b : i4    // operation 30 of the reduced case
  %31 = comb.add %a, %b : i4    // operation 31 of the reduced case
  %32 = comb.add %a, %b : i4    // operation 32 of the reduced case
  %33 = comb.add %a, %b : i4    // operation 33 of the reduced case
  %34 = comb.add %a, %b : i4    // operation 34 of the reduced case
  %35 = comb.add %a, %b : i4    // operation 35 of the reduced case
  %36 = comb.add %a, %b : i4    // operation 36 of the reduced case
  %37 = comb.add %a, %b : i4    // operation 37 of the reduced case
  %38 = comb.add %a, %b : i4    // operation 38 of the reduced case
  %39 = comb.add %a, %b : i4    // operation 39 of the reduced case
  %40 = comb.add %a, %b : i4    // operation 40 of the reduced case
  %41 = comb.add %a, %b : i4    // operation 41 of the reduced case
  %42 = comb.add %a, %b : i4    // operation 42 of the reduced case
  %43 = comb.add %a, %b : i4    // operation 43 of the reduced case
  %44 = comb.add %a, %b : i4    // operation 44 of the reduced case
  %45 = comb.add %a, %b : i4    // operation 45 of the reduced case
  %46 = comb.add %a, %b : i4    // operation 46 of the reduced case
  %47 = comb.add %a, %b : i4    // operation 47 of the reduced case
  %48 = comb.add %a, %b : i4    // operation 48 of the reduced case
  %49 = comb.add %a, %b : i4    // operation 49 of the reduced case
  %50 = comb.add %a, %b : i4    // operation 50 of the reduced case
  %51 = comb.add %a, %b : i4    // operation 51 of the reduced case
  %52 = comb.add %a, %b : i4    // operation 52 of the reduced case
  %53 = comb.add %a, %b : i4    // operation 53 of the reduced case
  %54 = comb.add %a, %b : i4    // operation 54 of the reduced case
  %55 = comb.add %a, %b : i4    // operation 55 of the reduced case
  %56 = comb.add %a, %b : i4    // operation 56 of the reduced case
  %57 = comb.add %a, %b : i4    // operation 57 of the reduced case
  %58 = comb.add %a, %b : i4    // operation 58 of the reduced case
  %59 = comb.add %a, %b : i4    // operation 59 of the reduced case
  %60 = comb.add %a, %b : i4    // operation 60 of the reduced case
  %61 = comb.add %a, %b : i4    // operation 61 of the reduced case
  %62 = comb.add %a, %b : i4    // operation 62 of the reduced case
  %63 = comb.add %a, %b : i4    // operation 63 of the reduced case
  %64 = comb.add %a, %b : i4    // operation 64 of the reduced case
  %65 = comb.add %a, %b : i4    // operation 65 of the reduced case
  %66 = comb.add %a, %b : i4    // operation 66 of the reduced case
  %67 = comb.add %a, %b : i4    // operation 67 of the reduced case
  %68 = comb.add %a, %b : i4    // operation 68 of the reduced case
  %69 = comb.add %a, %b : i4    // operation 69 of the reduced case
  %70 = comb.add %a, %b : i4    // operation 70 of the reduced case
  %71 = comb.add %a, %b : i4    // operation 71 of the reduced case
  %72 = comb.add %a, %b : i4    // operation 72 of the reduced case
  %73 = comb.add %a, %b : i4    // operation 73 of the reduced case
  %74 = comb.add %a, %b : i4    // operation 74 of the reduced case
  %75 = comb.add %a, %b : i4    // operation 75 of the reduced case
  %76 = comb.add %a, %b : i4    // operation 76 of the reduced case
  %77 = comb.add %a, %b : i4    // operation 77 of the reduced case
  %78 = comb.add %a, %b : i4    // operation 78 of the reduced case
  %79 = comb.add %a, %b : i4    // operation 79 of the reduced case
  %80 = comb.add %a, %b : i4    // operation 80 of the reduced case
  %81 = comb.add %a, %b : i4    // operation 81 of the reduced case
  %82 = comb.add %a, %b : i4    // operation 82 of the reduced case
  %83 = comb.add %a, %b : i4    // operation 83 of the reduced case
  %84 = comb.add %a, %b : i4    // operation 84 of the reduced case
  %85 = comb.add %a, %b : i4    // operation 85 of the reduced case
  %86 = comb.add %a, %b : i4    // operation 86 of the reduced case
  %87 = comb.add %a, %b : i4    // operation 87 of the reduced case
  %88 = comb.add %a, %b : i4    // operation 88 of the reduced case
  %89 = comb.add %a, %b : i4    // operation 89 of the reduced case
  %90 = comb.add %a, %b : i4    // operation 90 of the reduced case
  %91 = comb.add %a, %b : i4    // operation 91 of the reduced case
  %92 = comb.add %a, %b : i4    // operation 92 of the reduced case
  %93 = comb.add %a, %b : i4    // operation 93 of the reduced case
  %94 = comb.add %a, %b : i4    // operation 94 of the reduced case
  %95 = comb.add %a, %b : i4    // operation 95 of the reduced case
  %96 = comb.add %a, %b : i4    // operation 96 of the reduced case
  %97 = comb.add %a, %b : i4    // operation 97 of the reduced case
  %98 = comb.add %a, %b : i4    // operation 98 of the reduced case
  %99 = comb.add %a, %b : i4    // operation 99 of the reduced case
  %100 = comb.add %a, %b : i4    // operation 100 of the reduced case
  %101 = comb.add %a, %b : i4    // operation 101 of the reduced case
  %102 = comb.add %a, %b : i4    // operation 102 of the reduced case
  %103 = comb.add %a, %b : i4    // operation 103 of the reduced case
  %104 = comb.add %a, %b : i4    // operation 104 of the reduced case
  %105 = comb.add %a, %b : i4    // operation 105 of the reduced case
  %106 = comb.add %a, %b : i4    // operation 106 of the reduced case
  %107 = comb.add %a, %b : i4    // operation 107 of the reduced case
  %108 = comb.add %a, %b : i4    // operation 108 of the reduced case
  %109 = comb.add %a, %b : i4    // operation 109 of the reduced case
  %110 = comb.add %a, %b : i4    // operation 110 of the reduced case
  %111 = comb.add %a, %b : i4    // operation 111 of the reduced case
  %112 = comb.add %a, %b : i4    // operation 112 of the reduced case
  %113 = comb.add %a, %b : i4    // operation 113 of the reduced case
  %114 = comb.add %a, %b : i4    // operation 114 of the reduced case
  %115 = comb.add %a, %b : i4    // operation 115 of the reduced case
  %116 = comb.add %a, %b : i4    // operation 116 of the reduced case
  %117 = comb.add %a, %b : i4    // operation 117 of the reduced case
  %118 = comb.add %a, %b : i4    // operation 118 of the reduced case
  %119 = comb.add %a, %b : i4    // operation 119 of the reduced case
  hw.output %a : i4
}
```

## Build identity
Built with -UNDEBUG, so the compiler's internal checks are on.

## Fingerprint
op && "null op"
LowerTypes.cpp:412

Assisted-by: circt_bug_loop:vertex:gemini-3.8-flash
