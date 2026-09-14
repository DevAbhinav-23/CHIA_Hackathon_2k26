# `fixtures/differential/`

`04-Test-Plan.md` §13's directory for F-08. Two of the four rows are here; the
other two are not needed by any test that runs.

| Directory | What it is | Drives |
|---|---|---|
| `x_only/` | Two recorded-shape `BUGLOOP` streams in which the only divergence is on `o` and is confined to the two opening sampled cycles, after which both arms agree. That is the observable form of FR-08.9's "confined to cycles before the first write": a register written at cycle 10 differs only while it is uninitialised, and `--x-initial unique` is what makes the two arms differ there. **Constructed**, not recorded: producing a real X divergence needs a design whose register is read before it is written, and no seed in the corpus is one | `T-U-probe-29` |
| `broken_tb/` | A testbench with one missing semicolon and the trivial design it instantiates. Verilator 5.052 refuses it with `%Error: tb.sv:9:5: syntax error, unexpected $display, expecting ';'` and exits 1 without writing `obj_dir/Vbugloop`, which is FR-08.8's "a harness that fails to build". **Constructed** | `T-U-probe-28` |

`port_lists/` and `register_add/` are not here: `T-U-probe-47` and `T-U-probe-48`
construct their five port-list cases inline, and `T-U-probe-50` carries the
clocked accumulator it runs end to end.
