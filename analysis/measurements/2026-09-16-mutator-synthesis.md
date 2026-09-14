# W-12: the mutator synthesis (A7), and the two rules that stop it

**Run date** 2026-09-16 (IST), on `cachyos-x8664`, in-process on the head through
`~/.cache/chia-venv-py31019/bin/python`. **Scope** component A7, FR-05.2,
ADR-D-05, disposition row K8: refresh the issue mirror, synthesise the frozen
mutator set from the closed `label:bug` history, freeze it as
`circt_bug_loop/mutators/set_v1.json`, and make it the project's **first live
model call** under a cap of USD 5.

## 0. Verdict

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
