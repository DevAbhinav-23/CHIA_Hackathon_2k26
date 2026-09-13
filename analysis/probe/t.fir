FIRRTL version 4.0.0
circuit Top :
  public module Top :
    input a : UInt<8>
    input b : UInt<8>
    output o : UInt<9>

    node s = add(a, b)
    connect o, s
