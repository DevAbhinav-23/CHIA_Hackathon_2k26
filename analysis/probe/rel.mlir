module {
  hw.module @Top(in %a : i8, in %b : i8, out o : i9) {
    %false = hw.constant false
    %0 = comb.concat %false, %a : i1, i8
    %1 = comb.concat %false, %b : i1, i8
    %2 = comb.add bin %0, %1 {sv.namehint = "s"} : i9
    hw.output %2 : i9
  }
  om.class @Top_Class(%basepath: !om.basepath) {
    om.class.fields 
  }
}
