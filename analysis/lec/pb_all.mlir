module {
  hw.module @Agg(in %v : !hw.array<4xi4>, in %i : i2, out o : i4) {
    %0 = hw.array_get %v[%i] : !hw.array<4xi4>, i2
    hw.output %0 : i4
  }
  om.class @Agg_Class(%basepath: !om.basepath) {
    om.class.fields 
  }
}
