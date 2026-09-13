module {
  hw.module @Top(in %clock : !seq.clock, in %a : i8, in %b : i8, out o : i8) {
    %acc = seq.firreg %0 clock %clock {firrtl.random_init_start = 0 : ui64} : i8
    %0 = comb.add bin %a, %b {sv.namehint = "s"} : i8
    hw.output %acc : i8
  }
  om.class @Top_Class(%basepath: !om.basepath) {
    om.class.fields 
  }
}
