# Seeded-arm probes booked as "model's fault" whose pass emitted invalid IR, 2026-10-27

Follow-up to `2026-10-27-review-numbers.md` §b (`rejected:by_pass:post-pass IR fails op verifier
(possible missed bug)`: 2 in campaign 1, 15 in campaign 2). Read-only on the loop's data: probe rows from
`circt_bug_loop/loop.db.bak-2026-10-27` (opened `mode=ro&immutable=1`), inputs copied out of
`~/bugloop-artefacts/`. Nothing filed or posted. Raw per-probe results:
`raw/2026-10-27-missed-candidates.tsv`.

**Selection.** Seeded-arm probes of runs f1e4fef5, 73effefc, f0b2ef10, db45ab7b that the loop recorded
as `parse_error/tool_rejected_input`, whose input re-ran with exit 0 in `raw/2026-10-27-validity-rerun.tsv`
(78 probes), and whose own stderr is a verifier diagnostic on IR the pass created (a `see current
operation` note on an op that is not in the input, or a dominance error). That gives **18**: 2 in campaign 1
(as the review) and **16** in campaign 2 (the review says 15). I did not read `review_numbers.py`; the
likely difference is `p-29df22f92ecb`, whose first error line is `type mismatch at index 0 ('i1' != 'i2')`
rather than an `'op' op ...` line. All 18 are analysed below.

**Re-runs.** Each probe's own argv (input path replaced by a copy) with `-o /dev/null`, plus a parse+verify
run of the input alone:
- eade0de6: `docker run --rm --user 1000:1000 --cpus 2 -v <inputs>:/in:ro chia-circt-assert:eade0de61bc5-u1000`,
  `/workspace/circt/build/bin/circt-opt` (CIRCT eade0de);
- main: host build of llvm/circt 4738bd2685 (assertions on), before the fixes;
- branch: the same build with `review-fixes` (`2026-10-27-repairs.md`) applied, head 112cd91f5e.

All 18 inputs parse and verify on eade0de6 and on main (exit 0); all 18 passes then fail verification
with the same first error on both builds. Verdict for all 18: **real compiler bug** (verifier-valid input,
pass emits verifier-invalid IR, no diagnostic from the pass itself).

## Grouped by root cause

| group | probes | pass | root cause (evidence) | vs. the 15 | vs. llvm/circt issues | status on branch |
|---|---|---|---|---|---|---|
| D1 | f1e4fef5 p-079ec96951fc, p-bb09a5afa31a | `--convert-moore-to-core` | `moore.extract %x from -2147483648 : l4 -> l8` -> `hw.bitcast (i0) -> i8`: the `int32_t` overflow of the extract padding | **duplicate by root cause** of c-p-a2cb61b8d0aa (integer path of the same arithmetic; the loop saw a different symptom) | none | fixed by patch 07 (exit 0) |
| D2 | f0b2ef10 p-e910ce141517 | `--convert-moore-to-core` | `moore.dyn_extract %x from %i : i8, i32 -> i32` -> `comb.extract (i8) -> i32` | **duplicate by root cause** of c-p-075cf1d70f3a (result wider than input) | none | fixed by patch 08 (exit 0) |
| D3 | db45ab7b p-29df22f92ecb | `-convert-core-to-fsm` | `i2` state register with reset `%rst`, `%rst` also feeds `comb.xor` -> output: reset replaced by an `i2` constant, `fsm.output` type mismatch | **duplicate by root cause** of c-p-509c5aa72a94 / c-p-f0ca5e81cf0d | none | fixed by patch 12 (exit 0) |
| N1 | db45ab7b p-1cba29431755, p-22cfd150b431, p-4b6b03e0b471, p-522eae1c98df, p-a7b9b80f95b2 | `firrtl-flatten-memory` | memory with **SInt** data and a multi-bit mask (`sint<8>` + `uint<4>`, `sint<16>` + `uint<2>/<4>/<16>`) -> `firrtl.bitcast (uint<N>) -> uint<1>` ("the bitwidth of input (4) and result (1) don't match"). FlattenMemory derives the new mask width from the flattened data leaves (one leaf -> `uint<1>`) and bitcasts the old multi-bit mask into it. Same memory with UInt data: pass skips it, exit 0; with SInt data: fails (checked on main). SInt memories are flattened since #9448 (Jan 2026) | **new** | none matching (searched FlattenMemory/flatten-memory/mask; #9444/#9448 introduced SInt flattening, #10106 fixed mask repeat order) | still fails |
| N2 | f0b2ef10 p-278fdd066ac8, p-72baa2c67835, p-755297ff2188 | `firrtl-infer-domains{mode=infer-all}` | a domain-associated wire or instance inside a `firrtl.when` whose domain comes from an instance later in the parent block: `getDomainInScope` creates the "bounce" domain wire at the current insertion point (inside the `when`) but its `firrtl.domain.define` after the domain's definition in the parent block -> "operand #0 does not dominate this use ... (op in a child region)". The same module without the `when` passes on main | **new** | variant of closed #10116 and #10028 (same symptom, no `when`; their shape passes on main). Not reachable from firtool, which runs InferDomains after ExpandWhens; the pass neither handles nor rejects `when` | still fails |
| N3 | f0b2ef10 p-3d771ef4e1cc, p-533710040afe, p-535f7e9d6475, p-6b395fbd3ddf, p-951093976a8c, p-f3e0c1559a77 | `--synth-lower-word-to-bits` | in a `func.func` (SSACFG region), a lowered op (`comb.and/or/xor/mux`, `synth.aig.and_inv`) uses the result of an op the pass does not lower (`comb.add/sub/shl`): `lowerValueToBits`' default case does `builder.setInsertionPoint(op)`, i.e. extracts the bits **before** their defining op -> "operand #0 does not dominate this use". The same IR in an `hw.module` (graph region) passes on main | **new** | related open #10133 (make Synth passes runnable on any op); closed #10201/#10210 (constants outside an IsolatedFromAbove region) is a different symptom | still fails |

**Count.** 18 probes, all real bugs: **3 new root causes** (N1 5 probes, N2 3, N3 6) and 4 probes that are
other symptoms of root causes already among the 15 (D1-D3, all fixed by the `review-fixes` patches;
verified by re-running them on the branch).

## Caveats

- Root causes for N1-N3 are from reading the pass source plus one-change experiments (UInt vs. SInt data;
  with vs. without `when`; `func.func` vs. `hw.module`); no fix was written or tested for them.
- Reachability: none of N1-N3 was shown to be reachable from a frontend. N1 needs an SInt memory with a
  multi-bit mask (in the FIRRTL spec a ground-type memory has a 1-bit mask; not checked what CIRCT's
  parser or other passes produce),
  N2 needs `when` before InferDomains, N3 needs comb ops outside an `hw.module`. All three are still
  verifier-valid inputs on which a registered pass emits invalid IR.
- Issue search: GitHub search API, unauthenticated, read-only, queries listed in the table; titles and
  bodies of #10116, #10028, #10133, #9444, #9448 read. A non-matching search does not prove no report exists.
