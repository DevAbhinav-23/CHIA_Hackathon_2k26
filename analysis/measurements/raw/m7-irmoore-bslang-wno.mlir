module {
  moore.module @vector(in %i : !moore.i2, out o : !moore.i5) {
    %0 = moore.extract %i from -1 : i2 -> i5
    moore.output %0 : !moore.i5
  }
  moore.module @packed_array(in %i : !moore.array<2 x i2>, out o : !moore.array<5 x i2>) {
    %0 = moore.extract %i from -1 : array<2 x i2> -> array<5 x i2>
    moore.output %0 : !moore.array<5 x i2>
  }
  moore.module @packed_struct_array(in %i : !moore.array<2 x struct<{hi: i1, lo: i1}>>, out o : !moore.array<5 x struct<{hi: i1, lo: i1}>>) {
    %0 = moore.extract %i from -1 : array<2 x struct<{hi: i1, lo: i1}>> -> array<5 x struct<{hi: i1, lo: i1}>>
    moore.output %0 : !moore.array<5 x struct<{hi: i1, lo: i1}>>
  }
}
