`timescale 1ns/1ps
module bugloop_tb;
  reg clock = 0;
  reg [7:0] a = 0;
  wire [7:0] o;
  Top dut (.clock(clock), .a(a), .o(o));
  initial begin
    a = 8'h01
    $display("BUGLOOP 0 o = %h", o);
    $finish;
  end
endmodule
