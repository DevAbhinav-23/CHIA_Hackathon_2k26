module {
  hw.module @Junk1(in %x : i8, out y : i8) {
    %c = hw.constant 1 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk2(in %x : i8, out y : i8) {
    %c = hw.constant 2 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk3(in %x : i8, out y : i8) {
    %c = hw.constant 3 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk4(in %x : i8, out y : i8) {
    %c = hw.constant 4 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk5(in %x : i8, out y : i8) {
    %c = hw.constant 5 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk6(in %x : i8, out y : i8) {
    %c = hw.constant 6 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk7(in %x : i8, out y : i8) {
    %c = hw.constant 7 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk8(in %x : i8, out y : i8) {
    %c = hw.constant 8 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk9(in %x : i8, out y : i8) {
    %c = hw.constant 9 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk10(in %x : i8, out y : i8) {
    %c = hw.constant 10 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk11(in %x : i8, out y : i8) {
    %c = hw.constant 11 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Junk12(in %x : i8, out y : i8) {
    %c = hw.constant 12 : i8
    %r = comb.add bin %x, %c : i8
    hw.output %r : i8
  }
  hw.module @Target(in %p : i16, out q : i16) {
    %k = hw.constant 7 : i16
    %m = comb.mul bin %p, %k : i16
    hw.output %m : i16
  }
}
