module {
  hw.module @c1(in %v_0 : i4, in %v_1 : i4, in %v_2 : i4, in %v_3 : i4, in %i : i2, out o : i4) {
    %0 = hw.array_create %v_3, %v_2, %v_1, %v_0 : i4
    %1 = hw.array_get %0[%i] : !hw.array<4xi4>, i2
    hw.output %1 : i4
  }
  om.class @Agg_Class(%basepath: !om.basepath) {
    om.class.fields 
  }
}
module {
  hw.module @c2(in %v : !hw.array<4xi4>, in %i : i2, out o : i4) {
    %0 = hw.array_get %v[%i] : !hw.array<4xi4>, i2
    hw.output %0 : i4
  }
  om.class @Agg_Class(%basepath: !om.basepath) {
    om.class.fields 
  }
}
