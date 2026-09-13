module {
  hw.module private @Foo(in %a : i16) {
    %c7_i16 = hw.constant 7 : i16
    %0 = comb.mul bin %a, %c7_i16 : i16
    hw.output
  }
}
