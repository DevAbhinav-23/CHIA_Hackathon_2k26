module tb;
  logic clock = 0;
  logic [7:0] a = 8'd7, b = 8'd200, o;
  Top dut(.clock(clock), .a(a), .b(b), .o(o));
  initial begin
    for (int i = 0; i < 4; i++) begin
      #1 clock = 1;
      #1 clock = 0;
      $display("o = %02x", o);
    end
    $finish;
  end
endmodule
