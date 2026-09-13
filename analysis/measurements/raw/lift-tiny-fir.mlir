module {
  firrtl.circuit "Top" {
    firrtl.module @Top(in %clock: !firrtl.clock, in %a: !firrtl.uint<8>, in %b: !firrtl.uint<8>, out %o: !firrtl.uint<8>) attributes {convention = #firrtl<convention scalarized>} {
      %acc = firrtl.reg interesting_name %clock : !firrtl.clock, !firrtl.uint<8>
      %0 = firrtl.add %a, %b : (!firrtl.uint<8>, !firrtl.uint<8>) -> !firrtl.uint<9>
      %1 = firrtl.tail %0, 1 : (!firrtl.uint<9>) -> !firrtl.uint<8>
      %s = firrtl.node interesting_name %1 : !firrtl.uint<8>
      firrtl.matchingconnect %acc, %s : !firrtl.uint<8>
      firrtl.matchingconnect %o, %acc : !firrtl.uint<8>
    }
  }
}
