hw.module @W(in %a: i4, out o: i4) {
  %w = hw.wire %a sym @s : i4
  hw.output %w : i4
}
