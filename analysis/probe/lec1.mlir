hw.module @mulByTwo(in %in: i32, out out: i32) {
  %two = hw.constant 2 : i32
  %res = comb.mul %in, %two : i32
  hw.output %res : i32
}
hw.module @add(in %in: i32, out out: i32) {
  %res = comb.add %in, %in : i32
  hw.output %res : i32
}
