module {
  hw.module @Agg(in %v_0 : i4, in %v_1 : i4, in %v_2 : i4, in %v_3 : i4, in %i : i2, out o : i4) {
    %v_0_0 = hw.wire %v_0 sym @sym  name "v_0" : i4
    %v_1_1 = hw.wire %v_1 sym @sym_0  name "v_1" : i4
    %v_2_2 = hw.wire %v_2 sym @sym_1  name "v_2" : i4
    %v_3_3 = hw.wire %v_3 sym @sym_2  name "v_3" : i4
    %0 = hw.array_create %v_3_3, %v_2_2, %v_1_1, %v_0_0 : i4
    %1 = hw.array_get %0[%i] : !hw.array<4xi4>, i2
    hw.output %1 : i4
  }
  om.class @Agg_Class(%basepath: !om.basepath) {
    om.class.fields 
  }
}
