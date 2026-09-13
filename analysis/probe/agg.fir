FIRRTL version 4.0.0
circuit Agg :
  public module Agg :
    input v : UInt<4>[4]
    input i : UInt<2>
    output o : UInt<4>

    connect o, v[i]
