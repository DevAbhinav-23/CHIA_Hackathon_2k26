module {
  moore.module @Top(in %clock : !moore.l1, in %a : !moore.l8, in %b : !moore.l8, out o : !moore.l8) {
    %clock_0 = moore.net name "clock" wire : <l1>
    %a_1 = moore.net name "a" wire : <l8>
    %b_2 = moore.net name "b" wire : <l8>
    %acc = moore.variable : <l8>
    moore.procedure always {
      moore.wait_event {
        %4 = moore.read %clock_0 : <l1>
        moore.detect_event posedge %4 : l1
      }
      %1 = moore.read %a_1 : <l8>
      %2 = moore.read %b_2 : <l8>
      %3 = moore.add %1, %2 : l8
      moore.nonblocking_assign %acc, %3 : l8
      moore.return
    }
    %0 = moore.read %acc : <l8>
    moore.assign %clock_0, %clock : l1
    moore.assign %a_1, %a : l8
    moore.assign %b_2, %b : l8
    moore.output %0 : !moore.l8
  }
}
