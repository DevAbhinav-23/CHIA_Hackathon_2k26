hw.module @mulByTwo(in %in: i32, out out: i32) {
  %two = hw.constant 2 : i32
  %res = comb.mul %in, %two : i32
  hw.output %res : i32
}
hw.module @addThree(in %in: i32, out out: i32) {
  %three = hw.constant 3 : i32
  %res = comb.mul %in, %three : i32
  hw.output %res : i32
}
