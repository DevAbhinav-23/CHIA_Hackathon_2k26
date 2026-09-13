hw.module @c1(in %a : i8, in %b : i8, out o : i8) { %0 = comb.add %a, %b : i8  hw.output %0 : i8 }
hw.module @c2(in %a : i8, in %b : i8, out o : i8) { %0 = comb.add %b, %a : i8  hw.output %0 : i8 }
