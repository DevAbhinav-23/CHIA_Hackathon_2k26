FIRRTL version 4.0.0
circuit Top :
  public module Top :
    input clock : Clock
    input a : UInt<8>
    input b : UInt<8>
    output o : UInt<8>

    reg acc : UInt<8>, clock
    node s = tail(add(a, b), 1)
    connect acc, s
    connect o, acc
