module {
  hw.module @Agg(in %v_0 : i4, in %v_1 : i4, in %v_2 : i4, in %v_3 : i4, in %i : i2, out o : i4) {
    %0 = hw.array_create %v_3, %v_2, %v_1, %v_0 {sv.namehint = "v"} : i4
    %1 = hw.array_get %0[%i] : !hw.array<4xi4>, i2
    hw.output %1 : i4
  }
  om.class @Agg_Class(%basepath: !om.basepath) {
    om.class.fields 
  }
}
