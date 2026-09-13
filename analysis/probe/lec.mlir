hw.module @A(in %a: i4, in %b: i4, out o: i4) {
  %r = comb.add %a, %b : i4
  hw.output %r : i4
}
hw.module @B(in %a: i4, in %b: i4, out o: i4) {
  %r = comb.add %b, %a : i4
  hw.output %r : i4
}
hw.module @C(in %a: i4, in %b: i4, out o: i4) {
  %r = comb.sub %a, %b : i4
  hw.output %r : i4
}
