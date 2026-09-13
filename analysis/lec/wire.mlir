hw.module @c1(in %a : i8, out o : i8) { %w = hw.wire %a : i8  hw.output %w : i8 }
hw.module @c2(in %a : i8, out o : i8) { hw.output %a : i8 }
