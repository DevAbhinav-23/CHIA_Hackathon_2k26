hw.module @bug(in %a : i32, out z : i32) {
  %z = comb.divu %a, %pad0 : i32
}
