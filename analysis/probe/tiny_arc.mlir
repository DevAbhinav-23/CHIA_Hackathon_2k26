module {
  hw.module @Top(in %clock : !seq.clock, in %a : i8, in %b : i8, out o : i8) {
    %acc = seq.firreg %0 clock %clock {firrtl.random_init_start = 0 : ui64} : i8
    %0 = comb.add bin %a, %b {sv.namehint = "s"} : i8
    hw.output %acc : i8
  }
func.func @main() {
  %c0 = arith.constant 0 : i1
  %c1 = arith.constant 1 : i1
  %ck0 = seq.to_clock %c0
  %ck1 = seq.to_clock %c1
  %a0 = arith.constant 7 : i8
  %b0 = arith.constant 200 : i8
  %lb = arith.constant 0 : index
  %ub = arith.constant 4 : index
  %st = arith.constant 1 : index
  arc.sim.instantiate @Top as %model {
    arc.sim.set_input %model, "a" = %a0 : i8, !arc.sim.instance<@Top>
    arc.sim.set_input %model, "b" = %b0 : i8, !arc.sim.instance<@Top>
    scf.for %i = %lb to %ub step %st {
      arc.sim.set_input %model, "clock" = %ck1 : !seq.clock, !arc.sim.instance<@Top>
      arc.sim.step %model : !arc.sim.instance<@Top>
      arc.sim.set_input %model, "clock" = %ck0 : !seq.clock, !arc.sim.instance<@Top>
      arc.sim.step %model : !arc.sim.instance<@Top>
      %o = arc.sim.get_port %model, "o" : i8, !arc.sim.instance<@Top>
      arc.sim.emit "o", %o : i8
    }
  }
  return
}
}
