# W-12: the mutator synthesis (A7), and the two rules that stop it

**Run date** 2026-09-16 (IST), on `cachyos-x8664`, in-process on the head through
`~/.cache/chia-venv-py31019/bin/python`. **Scope** component A7, FR-05.2,
ADR-D-05, disposition row K8: refresh the issue mirror, synthesise the frozen
mutator set from the closed `label:bug` history, freeze it as
`circt_bug_loop/mutators/set_v1.json`, and make it the project's **first live
model call** under a cap of USD 5.

## 0. Verdict

> **Superseded in part by §9, "The live pass (W-12b)", appended 2026-09-14.**
> The architect took way (2) of §7: the pre-registration is an annotated tag.
> B1 and B2 are gone, the turn was dispatched, and the set is frozen. Sections 0
> to 8 are left exactly as they were written before the money was spent.

**No live model call was made, and USD 0.00 was spent.** The synthesis was taken
as far as it can be taken without one: the mirror is refreshed, the corpus is
selected and counted, the prompt renders over the real 487 issues, the turn's
whole round trip runs against a mocked backend, the footer parses, the set
writes, and `mutators.load_set` accepts it against its own digest. The live turn
was not dispatched because **two committed rules refuse it**, both of them by
design and neither of them fixable inside this task:

| | The rule | What it does today |
|---|---|---|
| **B1** | §8.3 step 1 / §8.1 rule 3: `synthesise_mutators` refuses once a `budget.yaml` commit exists | `registration_commit` returns `1a26fc8`, so **the synthesis raises `already_registered` before any turn** |
| **B2** | §8.1 rule 2, `budget._check_frozen_set`: the set's last commit must **predate** the budget file's | `budget.yaml` was last committed **2026-09-14T16:02:08+05:30**, so a `set_v1.json` committed now makes `load_budget` raise and **no campaign can start** |

K8 says the synthesis is "frozen **before** pre-registration". `budget.yaml`
landed at `6e0b110` (W-06) and was touched again at `1a26fc8` (W-20b), and
FR-14.3 says the commit that lands that file **is** the registration — so the
ordering K8 assumed was already spent before W-12 was reached, while the work
plan still carries W-22 "pre-registration" as a future task. The code and the
plan disagree about when registration happened, and that disagreement, not the
money and not the model, is what stops A7.

Bypassing B1 needs one substitution of `registration_commit`. That is what the
dry pass below does, and it costs nothing; doing it for a **write-once freeze
paid for with a live turn** is an ordering decision for the architect, because
whichever way B2 is resolved decides whether the frozen bytes are usable at all.

Everything else W-12 owes is done, and two defects that would have made the live
turn's output wrong or unusable were found **before** the money was spent.

## 1. The issue corpus (step 1)

`triage_task.issue_mirror_refresh`, called through `_chia_original` on the head
at the committed cap, into a store of this task's own.

| | |
|---|---|
| Store | `~/bugloop-artefacts/synthesis/mirror.db` |
| `issue_cap` | **12,000** (`budget.yaml`'s `issue_mirror_issue_cap`) |
| Walk | two-direction, `desc` then `asc`; `ceiling_hit` **true**, so both ran |
| Issues mirrored | **2,652** |
| Pages | **198** |
| Wall | **212.4 s** |
| `cap_bound` | false — the cap was never the binding constraint |
| `incomplete_reason` | none |
| Refreshed | `2026-09-14T10:55:15+00:00` |

Selected for the synthesis, by `mutator_synth.read_mirror` (closed, and
`labels_json` containing `bug`):

| | |
|---|---|
| Closed `label:bug` issues | **487** |
| `issue_numbers_sha256` | `5c78adcea2166c7b768452413409e453502607305e879da2a8e0acba371fa5ae` |
| Rendered `$issues` | **1,506,450 characters** |

**487 is exactly M9's measured count**, independently re-derived here from a
mirror refreshed today. ADR-D-05's fallback to the 24-month fix-commit set is
therefore not taken, and §8.3 step 2's figure needs no erratum.

GitHub was read-only throughout, with the token read from a mode-600 file and
never printed; it is removed at the end of the task.

## 2. The dry pass (step 2)

The same inputs, the same code path, a mocked backend, and **nothing of the loop
faked**: `synthesise_mutators`, the prompt, `dispatch_turn`, `llm_turn`,
`build_llm`, `turn_usage`, the footer parser, the six drop checks and the freeze
all ran for real. Four substitutions, each the one a test makes: CHIA's profiler
(it starts a local Ray), `google.genai.Client` (returning real
`GenerateContentResponse` objects), `llm.worker_env` (architect decision 2 — the
allow path without the interlock in `os.environ`), and `registration_commit`
(B1; the committed tests use a fresh unregistered repository instead).

| | |
|---|---|
| Batches | **1** |
| Prompt | **1,509,080 characters**, the whole of it reaching the backend |
| Footer | parsed; 5 entries in, **4 kept, 1 dropped** (`bad_id`), which is step 4 working |
| Freeze | written, canonical JSON, `load_set(expected_sha=…)` **accepts it** |
| Thinking tokens | counted (**900** in the fake response) — see §5 |

**§8.3 specifies ONE turn, not batches.** Disposition row K8's parenthesis says
"one synthesis turn per batch of issues", but §8.3 fixes a single turn over
`$issue_count` issues, `mutator_synth.py` implements exactly that, and no batch
size or splitting rule is written down anywhere. There is nothing to shrink and
no rule by which to shrink it, and none is needed:

### The pre-authorised worst case for the whole live pass

`llm.SpendGuard.worst_case_usd` over the rendered prompt, at `budget.yaml`'s two
verified prices and `MAX_OUTPUT_TOKENS` = 16,000:

```
(1,509,080 / 3) / 1e6 × 0.75  +  16,000 / 1e6 × 3.75  =  USD 0.43727
```

| | |
|---|---|
| Worst case, whole live pass | **USD 0.43727** |
| Task cap | USD 5.00 |
| Under the cap | **yes, by a factor of 11** |

So neither the batch count nor the issue sample needs shrinking, and §8.3's one
turn stands. The expected *actual* cost is lower still: the worst case charges
all 16,000 output tokens, and a twenty-mutator answer is a small fraction of
that.

## 3. The live pass (step 3)

**Not run.** See §0. Nothing was dispatched, so there is no per-turn usage, no
`cost_usd`, no ledger figure and no SDK `total_token_count` to report, and
`circt_bug_loop/mutators/set_v1.json` does not exist. `mutators.SET_PATH` still
resolves to `set_dev.json`, which `load_set` refuses for any run that names a
digest, so the mutation arm remains unable to run a registered campaign — which
is errata row 24's standing item, unchanged.

## 4. Validation (step 4)

Not applicable to a set that was not frozen. The dry pass discharges the parts
that do not need the live bytes: `load_set(expected_sha=…)` accepts the written
document, and the mutator unit tests and the whole T0 suite are green
(§6). `mutate_seed` over the five recorded corpus seeds is owed and is blocked on
the same live turn.

## 5. Two defects found before the money was spent

### (a) The head's `chia` is unpatched, so thinking tokens would not have counted

`build_llm` imports `chia.models.vertex`. On this head that resolves to
`/home/adi/.cache/chia-src/chia/models/vertex.py`, which contains **none** of
K11's fields — no `thoughts_token_count`, no `tool_use_prompt_token_count`, no
`_usage_meta`. The patched copy exists only in `circt_bug_loop/_shipped/chia/`,
which `runtime_env` ships **to the cluster**; a synthesis run in-process on the
head, which is what W-12 asks for, imports the unpatched one.

`turn_usage` would then have returned `thinking_tokens: 0` and priced the turn
without them, which is precisely the defect K11 exists to fix, on the one turn
whose whole purpose was to be measured.

**The live pass must run with the staged package shadowing the install:**

```
PYTHONPATH=circt_bug_loop/_shipped
```

Verified: with it, `chia.models.vertex` resolves to the staged patched file and
the dry pass reports `thinking_tokens: 900` and `observed: true`. Without it, a
turn's thoughts are billed and not counted. Pre-flight check 14 proves the patch
is in the file **a worker** imports; nothing checks the head, and A7 runs on the
head.

### (b) A7 never wrote §8.1's `frozen` field — **fixed** (`84e0723`)

`synthesise_mutators` wrote `format_version`, `set_version`, the three
provenance fields and the mutators array, and not `frozen`, which §8.1's format
table lists and which is the whole of what distinguishes a frozen set from
`set_dev.json`. `mutators.load_set` refuses a set whose `frozen` **is False**, so
a set carrying no such field at all passed that guard by accident rather than by
being frozen.

This matters more than its size: **the freeze is write-once.** A set frozen
without the field could only be corrected by bumping `set_version` and running
the synthesis — and paying for the model turn — a second time. Found by the dry
pass, fixed before the live pass, asserted by `T-U-msyn-05`.

## 6. Step 5, and the suite

`render_results` required the campaign's store to hold a fingerprint for every
side of FR-10.2's hand-labelled duplicate-pair set. Its sides are recorded
failures labelled by hand **before any fingerprint was computed** and belong to
no campaign, so the gap fired on every real run — and hardest on a campaign that
confirms nothing, which has no such candidate at all. That is the one refusal
`T-S-regen-01` recorded at the end of every run.

Fixed (`51b68ec`): `triage_task.labelled_fingerprint` fingerprints a labelled
side through the **same** `compute_fingerprint` the campaign uses, so the
measurement is of the campaign's fingerprint and not of a second implementation
of it; `load_labelled_pairs` hands the renderer the recorded failures instead of
two candidate ids; `render_results` takes G-43's registered `fingerprint_top_n`
and the driver passes the run's own. **The refusal for a labelled set that is not
supplied at all is kept.**

The fixture store now carries the committed set instead of three pairs invented
to name its own candidates, so `fixtures/results/example.md` prints the project's
real rates — **collision 1/11 = 0.0909, false-merge 1/11 = 0.0909** — which is
what `T-U-triage-09` measures independently over the same 22 pairs, by a
different code path. Two paths, one pair of numbers.

| Suite | Result |
|---|---|
| T0, before this task | 586 passed, 1 skipped, 50 deselected |
| T0, after `51b68ec` and `84e0723` | **586 passed, 1 skipped, 50 deselected** |

No test was lost and none was added purely to pass: `T-U-results-09` and
`T-U-driver-41` now assert the new behaviour and the kept refusal, and
`T-U-msyn-05` asserts `frozen`.

## 7. What W-12 still owes, and the decision it needs

The whole of the remainder is one architect decision. Three ways out of B1 and
B2, none of which a task may take on its own:

1. **Re-land `budget.yaml` as W-22's registration commit, after `set_v1.json`.**
   Fixes B2 exactly, and matches the plan, which still lists W-22 as future
   work. It does **not** fix B1: `registration_commit` asks whether *any* commit
   ever landed the file, and one has.
2. **Key step 1's refusal to the pre-registration itself** — a tag, as
   `contract-2.0` and `contract-2.1` already are — rather than to any
   `budget.yaml` commit. Fixes B1, and leaves §8.1 rule 3's purpose intact: a
   *registered* campaign still cannot synthesise. Needs an FRD/LLD erratum.
3. **Neither** — declare the mutation arm unable to run a registered campaign
   and say so in the results artefact and the paper. This is errata row 24's
   standing consequence and it costs the head-to-head its second arm.

With (1) and (2) taken, the live pass is one command, and it is
**worst case USD 0.44** with `PYTHONPATH=circt_bug_loop/_shipped` set.

## 8. Artefacts

| Path | What |
|---|---|
| `~/bugloop-artefacts/synthesis/mirror.db` | the refreshed mirror, 2,652 issues |
| `~/bugloop-artefacts/synthesis/mirror-refresh.json` | the refresh's own return |
| `~/bugloop-artefacts/synthesis/dry/` | the dry pass's throwaway set and report |

No transcript is recorded because no turn was dispatched. Nothing under
`~/bugloop-artefacts/synthesis/` carries a credential; the mirror holds issue
titles and bodies and nothing else, and comments are never mirrored (FR-20.4).

---

# 9. The live pass (W-12b)

**Run date** 2026-09-14 (IST), same host, same interpreter, in-process on the
head, with `PYTHONPATH=circt_bug_loop/_shipped` set for the reason §5(a) gives.
**Scope** the architect's binding decision on B1/B2, then the project's **first
live model call**.

## 9.0 Verdict

**One turn was dispatched, it succeeded, and USD 0.486733 was spent.**
`circt_bug_loop/mutators/set_v1.json` exists, is frozen, is committed, and
carries **eleven** mutators. Three things went wrong and none of them lost
money: a client-lifetime defect in this task's own recorder sent nothing on the
first attempt, the pre-authorised "worst case" turned out not to be one, and
**eleven of the model's twenty-two mutators were dropped**, ten of them for a
single avoidable cause.

## 9.1 The registration is a tag (B1 and B2, closed)

| | |
|---|---|
| Resolver | `budget.registration(repo_root)` - newest `registration/*` tag, dereferenced to its commit; `("", "")` when there is none |
| A7's rule | `mutator_synth.registration_commit` is that one resolver; `""` means "not registered", and the synthesis runs |
| Campaign rule | `load_budget(..., campaign=True)` refuses a repository with no tag; `--dry-run`, `--generator recorded` and `--draw-calibration` are untouched |
| FR-14.7 | the budget file's own commit must be the tag's commit or an ancestor of it |
| FR-05.2 / §8.1 rule 2 | the mutator set's commit must be the tag's commit or an ancestor of it - **ancestry**, not two `%cI` dates |
| Recorded | a `registration` table row per run, `(run_manifest_id, registration_tag, registration_commit)` |
| Identity | unchanged: `RunManifest.budget_file_sha` is still the commit that lands the file, and the contract did not move |

`RunManifest` has no open `budget` block, so the architect's fallback applied -
except that the `run` table could not gain a column either: `T-U-store-01`
compares `store._DDL_TABLES` to `03-LLD.md` §6.2 for **textual** equality and
W-12b may not edit a design document. The table is therefore a statement of its
own, `_DDL_REGISTRATION`, appended to the schema; §6.2's text is still what
`_DDL_TABLES` holds, to the letter. Errata row 32.

**The repository is still unregistered, deliberately.** No `registration/*` tag
was created: placing it is W-22's job, and it must land **after** `set_v1.json`,
which is now committed at `9bb2896`.

## 9.2 The dry pass, again, after the change

Same four substitutions less one: `registration_commit` is **not** substituted
any more, which was the whole of B1.

| | |
|---|---|
| `registration_commit` on the head | **`""`** - the repository holds no tag, so A7 is legal |
| Issues selected | **487**, digest `5c78adce…` unchanged |
| Prompt reaching the backend | **1,509,080 characters** |
| Drop checks | all six fired (the `drops` transcript), 12 in, 1 kept |
| Freeze | written, `load_set(expected_sha=…)` accepts it, `frozen` true |
| Thinking tokens | **900**, `observed: true` - the staged patched `vertex.py` |

## 9.3 The live turn

One turn. `chia.models.vertex` resolved to
`circt_bug_loop/_shipped/chia/models/vertex.py` and the assertion that K11's
patch is in **this process's** copy ran before anything was dispatched.

| | Ledger (`llm.turn_usage` -> `ledger.price`) | SDK (`usage_metadata`, read off the response) |
|---|---|---|
| Input tokens | **619,603** (`prompt` 619,603 + `tool_use_prompt` 0) | `prompt_token_count` **619,603** |
| Output tokens | **5,875** (`candidates` 2,900 + `thoughts` 2,975) | `candidates_token_count` **2,900** |
| Thinking tokens | **2,975** | `thoughts_token_count` **2,975** |
| Tool-use prompt tokens | **0** | `tool_use_prompt_token_count` `None` |
| | | `total_token_count` **625,478** |
| **cost_usd** | **0.486733** | **0.486733** |

`625,478 = 619,603 + 2,900 + 2,975` exactly, which is the SDK's own definition
of `total_token_count` and the fact K11 rests on. Wall **128.3 s**;
`num_turns` 1; `success` true; `stderr` empty.

**K11, measured on a real turn.** Priced the way unpatched CHIA counts - output
= `candidates_token_count` only - the same turn costs **USD 0.475577**. The
patch is worth **USD 0.011156 on one turn, 2.3 % of it**, and the campaign's
whole money cap is computed the same way.

## 9.4 The money

| | |
|---|---|
| Pre-authorised worst case (W1's formula) | USD **0.43727** |
| Authorised by the guard before dispatch | USD **1.31181** (3 x the above: `vertex`'s own `retries` is 3) |
| **Actually spent, ledger** | USD **0.486733** |
| **Actually spent, SDK-derived** | USD **0.486733** |
| Task hard cap | USD 5.00 |
| Spent on the first, failed attempt | USD **0.00** - no request left the machine |

**W1's "worst case" is not a worst case, and this turn exceeded it.** `SpendGuard`
estimates input tokens at `len(prompt) / 3`. Measured here: 1,509,080 characters
for 619,603 prompt tokens is **2.436 characters per token**, so the estimate was
**18.8 % low**, and the authorised figure was **USD 0.04946 (11.3 %) below** what
the turn cost. `SpendGuard`'s docstring already admits the direction; this is the
first measurement of the size, on the only prompt shape that matters. It is a
defect in the control that is supposed to stop the campaign at
`campaign_spend_cap_usd`, and it under-authorises by roughly a ninth. Errata row
34.

## 9.5 What the model returned, and what survived

**Twenty-two mutators in, eleven kept, eleven dropped.**

| Drop check | Count | Ids |
|---|---|---|
| `bad_pattern` | **10** | `fir.mem.depth_one`, `fir.mem.latency_zero`, `fir.type.vector_size_one`, `fir.shift.amount_zero`, `fir.literal.negate`, `fir.ident.keyword_collision`, `fir.printf.drop_arg`, `mlir.comb.extract_zero`, `sv.sensitivity.complex_expr`, `sv.assign.procedural_wire` |
| `bad_replacement` | **1** | `mlir.sv.reg_sym_drop` (an empty `replacement`, which §8.1 does not allow) |

**All ten `bad_pattern` drops are one cause**: `re.error: look-behind requires
fixed-width pattern`. Every one of them opens with a variable-width look-behind -
`(?<=depth\s*=>\s*)`, `(?<=(?:read|write)-latency\s*=>\s*)`, and so on. Python's
`re` refuses those; PCRE, .NET and Java's `\K`-style engines do not, and §8.3's
prompt never says which engine compiles the pattern. **Nearly half the set was
lost to one unstated sentence.**

The prompt was **left exactly as it was**. The freeze is write-once and the
repository should hold the text that produced these bytes; adding the sentence
now would make `set_v1.json` unreproducible from the committed prompt. Whether
to spend a second turn on a `set_v2` that keeps twenty-one of twenty-two is the
architect's call and is priced at about USD 0.49. Errata row 33.

### The frozen set

| | |
|---|---|
| Path | `circt_bug_loop/mutators/set_v1.json`, committed `9bb2896` |
| `set_sha256` | **`180ca0ebf9c38c3bfd2635f7f778bbdb0c5a6b550f8b615432ab8705cd541e55`** |
| `frozen` | **true** |
| `synthesis_model` | `gemini-3.8-flash` |
| `issues_used` / `issue_numbers_sha256` | 487 / `5c78adce…` (the run's, never the model's) |
| Mutators | **11** |
| By kind | `text` **11**; `line` **0**; `argv` **0** |
| By language | `mlir` **5**, `fir` **5**, `sv` **1**, `any` **0** |

**Two shapes the set does not have.** No `argv` mutator, so FR-05.5's
replacement-argument-vector path is unexercised by the campaign's own set; and
no `any` mutator, so a seed's test file draws only from its own language's
five-or-one. Both are the model's choice over §8.3's prompt, which asks for
neither by name, and both are recorded rather than repaired.

## 9.6 Validation

`load_set(path, expected_sha=set_sha256)` accepts the written document and its
`frozen` is true (8.1 rule 1).

`mutate_seed` over the **five recorded corpus seeds** of
`tests/fixtures/corpus/seeds/`, iteration 0, against the frozen set. Every
derived seed is inside 63 bits (W-19b finding 2), and **no mutator raised**.

| Seed fixture | Test files | Mutants at `per_seed_probe_cap` = 5 | Mutants, cap 20 | No-ops, cap 20 |
|---|---|---|---|---|
| `nine_test_files` | 9 | 5 | 15 | 30 |
| `no_run_line` | 1 | 1 | 1 | 4 |
| `not_wrapper` | 1 | **0** | **0** | 5 |
| `sdk_inexact` | 1 | 1 | 1 | 4 |
| `unsupported_shape` | 1 | 1 | 1 | 4 |
| **Total** | 13 | **8** | **18** | **47** |

| | |
|---|---|
| Failures (FR-05.7) | **0**, on every seed and both caps |
| Seeds outside 63 bits | **0** of 18 |
| No-op rate, cap 20 | **47 / 65 = 72 %** |

The no-op rate and the zero-mutant seed are a property of these five fixtures -
all five are MLIR, so only the five `mlir` mutators are ever eligible - and not
a measurement of the 187-seed corpus. They are recorded because they are the
only evidence available before a pilot, and because a mutation arm whose
per-seed yield at the registered cap is one probe is an arm that will spend its
window on no-ops.

## 9.7 The suite

| Suite | Result |
|---|---|
| T0, before W-12b | 586 passed, 1 skipped, 50 deselected |
| T0, after the tag change | **586 passed, 1 skipped, 50 deselected** |
| T0, with `set_v1.json` present (`SET_PATH` now resolves to the frozen set) | **586 passed, 1 skipped, 50 deselected** |
| `test_mutators.py` alone, against the frozen set | **13 passed** |

No test was lost, none was added to pass, and the three numbered tests that
moved assert the new behaviour: `T-U-msyn-01` (a committed `budget.yaml`
registers nothing; a tag does), `T-U-budget-07` (the three registration states)
and `T-U-budget-08` (an edit after the tag), plus `T-U-driver-01` and `-02`.

## 9.8 What went wrong

1. **The first live attempt sent nothing, and cost nothing.** This task's
   `genai.Client` recorder wrote `self.models = RealClient(**kwargs).models`,
   dropping the client's last reference; CPython collected it at once and closed
   the httpx transport under the `models` object that survived. Six attempts of
   `Cannot send a request, as the client has been closed`, two empty
   transcripts, `observed: false`, **USD 0.00**. It is a defect in the harness
   and not in the loop, and the loop's own behaviour was right throughout: the
   turn was reported unsuccessful, `turn_usage` returned NULL counts rather than
   zeros (K10), and `ledger.price` returned `None` rather than a price. The
   recorder now holds the reference, and it refuses to retry a turn whose counts
   were never observed, a turn that was never sent not being a contract failure.
2. **The pre-authorised worst case was exceeded** - §9.4.
3. **Eleven of twenty-two mutators dropped, ten to one unstated sentence** - §9.5.

## 9.9 Artefacts

| Path | What |
|---|---|
| `~/bugloop-artefacts/synthesis/live/transcript-0.md` | the turn's own text, 7,507 bytes, written before the footer was parsed |
| `~/bugloop-artefacts/synthesis/live/stream-0.log` | the backend's stream log for the same turn |
| `~/bugloop-artefacts/synthesis/live/live-report.json` | every figure in §9.3 to §9.6, machine-readable |
| `~/bugloop-artefacts/synthesis/dry/dry-report.json` | §9.2's dry pass, re-run after the tag change |
| `circt_bug_loop/mutators/set_v1.json` | the frozen set itself |

The API key was never printed, logged or written: the recording client stores no
kwarg, and both `GEMINI_API_KEY` and `BUGLOOP_ALLOW_LIVE_MODEL` existed only
inside the one subshell that ran the pass. Nothing under
`~/bugloop-artefacts/synthesis/` carries a credential.
