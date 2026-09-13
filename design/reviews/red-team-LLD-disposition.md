# Disposition: `red-team-LLD.md`

**Date: 2026-09-14.** Every one of the review's 61 findings, what was done about it, and where.
`03-LLD.md` is revised throughout; `02-HLD.md` §0.1 carries the five errata the review forced against
it; `01-FRD.md` §1.7 carries the eight it forced against the FRD; `00-README.md` carries the contract
version. Nothing is deferred and nothing is disputed without a command and its output.

**Dispositions used.** **Fixed** means the document now says something different and the new claim was
executed. **Fixed, verified** means the same and the command and output are recorded in the LLD beside
the claim. **Accepted with a decision** means the finding was right and the fix required a choice the
review did not make; the choice and its reasoning are recorded here and in the LLD. **Rejected** means
the finding is wrong, with the check that says so.

**What was executed for this revision**, all on 2026-09-14 against the same authorities the LLD names
(CHIA at `~/.cache/chia-src` @ `16c35e92`, the CIRCT clone at `~/.cache/chia-pin-smoke/circt` @
`b792c772`, the measured assertions-on build at `~/.cache/chia-pin-smoke/bassert_g`, the SDK at
`~/.cache/chia-pin-smoke/circt-sdk`): a C++ and a C assertion sample compiled and matched against the
new `_ASSERT_GLIBC`; three real `circt-opt` crashes produced and 466 frames parsed with the new
`_FRAME`; `llvm-symbolizer` run both the old way and the new; the prologue strip and the fingerprint
frame measured over ten runs of one input; the whole image fetch-and-pin recipe reproduced against a
purpose-built upstream and the two `ls-tree` commands against the real clone; `prlimit --cpu` measured
at soft-equals-hard and at soft-below-hard, with `os.wait4` rusage; the three `SourceReadTool` git
commands run against the real clone; the interestingness template assembled from the document and run
on four inputs and then handed to `circt-reduce`; the whole DDL in `sqlite3 :memory:`; all 54 Python
blocks through `ast.parse`; both cluster YAMLs through `chia.cluster.config.load_config`;
`budget.yaml` against its own §9.1 schema; every shell block through `sh -n` or `bash -n`.

---

## KILL

| # | Disposition | Where |
|---|---|---|
| K1 | **Fixed, verified.** `_ASSERT_GLIBC`'s `func` group becomes `.+?`, bounded on the right by the literal `: Assertion \``. Matched against a compiled C++ file with a namespaced `const` member function (`int circt::Foo::get(int) const`), against the C control, and against the absolute-path shape a CIRCT probe produces. | `03-LLD.md` §3.6.1 |
| K2 | **Fixed, verified.** `_FRAME` now captures `(<module>+0x<offset>)` and the second, print-time-attributed shape, with `Frame.shape` recording which. `circt_symbolize(frames)` groups by module and makes one `--obj=<module>` call per module with that module's offsets. `frames_with_location` is `line > 0 and in_circt_object`, with `in_circt_object` defined for both shapes. `out_of_scope_root` is the first frame after the prologue strip not in a CIRCT object. Both recipes were run against a real trace: the old resolves nothing, the new resolves SDK function names with no file and no line. The SDK's no-debug-information consequence is stated and is an FRD erratum. | `03-LLD.md` §2.9, §3.6.2, §3.10, §4.9; `01-FRD.md` §1.7 FR-07.4 |
| K3 | **Fixed, verified.** `strip_prologue` drops the named handler frames and unresolved libc frames; measured, it removes exactly four from a real trace. The crash and fatal-error fingerprint becomes the signal name plus the first stripped frame in a CIRCT object, function name and file basename, no line. `Fingerprint.fingerprint_stable` is set by the gate re-run and an unstable fingerprint is reported, never merged. `@TOP_FRAME@` is that same frame. Measured over ten runs of one input: nine distinct top-5 tuples, three distinct fingerprint frames, and the guard still discriminates because the `grep` is over the whole trace. | `03-LLD.md` §2.9, §3.7.1, §3.9, §6.2, §10.2; `01-FRD.md` §1.7 FR-10.1 |
| K4 | **Fixed, verified.** The recipe fetches into the base's existing repository: `fetch --depth 1 origin <sha>`, `fetch --depth 1 origin tag <ver>`, `checkout --detach <sha>`. Reproduced end to end against a purpose-built upstream shaped like `llvm/circt`, including the `remote origin already exists` failure of the old first line, the `[new tag]` line of the second fetch, and the pin check passing and failing. | `03-LLD.md` §4.11 |
| K5 | **Fixed, verified.** A1, A2 and B6b move to the head and read the head's blobless clone; `corpus.resolve_sites` is added there for FR-04.1's site check. No worker mount is added and no clone is copied. | `03-LLD.md` §3.2, §3.3, §3.4, §3.5, §3.7, §4.12, §14.1; `02-HLD.md` §0.1, §1.1, §1.2, §1.3, §3 |
| K6 | **Fixed.** `SeedRecord` gains required `diff` and `test_files`; contract MAJOR bump to 2.0. A1 fills both on the head with one `git show` and the batched `cat-file`. A3 and A4 then need no git. | `03-LLD.md` §2.1, §2.4, §3.3, §7.2, §8.2; `02-HLD.md` §2.3, §2.4; `00-README.md`; `01-FRD.md` §1.7 FR-01.1, FR-05.1 |
| K7 | **Fixed, verified.** The screen is defined: a token set per oracle class, a case-sensitive substring match with SQLite `instr` over `title || ' ' || body`, any token against any issue, `known_open_issue` or `known_closed_issue` by the issue's state, evidence carrying the token, number, URL, state and labels. Over-inclusive by design and said to be. The query was run against the DDL with a seeded row. | `03-LLD.md` §3.7.3, §6.3, §9.4 |
| K8 | **Fixed, verified.** `prlimit --cpu=<soft>:<soft+5>` so `SIGXCPU` is delivered and names the limit; `os.wait4` for the child's rusage; `limit_hit` derived in `circt_exec_probe` and nowhere else; `wall` and `cpu` classify `timeout`, `address_space` classifies `oom`, never `crash`. Measured: `--cpu=1` returns 137 (SIGKILL), `--cpu=1:3` and `--cpu=1:6` return 152 (SIGXCPU), `--as=<small>` returns 1 with `MemoryError` and no signal. | `03-LLD.md` §2.9, §3.6, §3.10, §4.1, §6.2, §9.4 |
| K9 | **Accepted with a decision, verified by reading.** `resume` cannot carry FR-12.3: it requires a diff and jumps past assess, reproduce **and** fix (`issue_task.py:39-56`, `178-190`), and F-12 needs the fix turn. The alternative is taken: `cfg["repro_dir"]` moves under the artefact root, outside the tree `git clean -fd` reaches, which needs no change to `issue_task.py` because the directory is only ever `cfg["repro_dir"]`/`cfg["repro_path"]`. The reproduce turn may still overwrite the script, the prompt cannot be edited, and the **issue body can**, so the report names the pre-written script and the adapter hashes the file before and after and records `repro_overwritten`. FR-12.3's polarity half stays guaranteed through `require_repro`; its "confirms rather than invents" half becomes reported per attempt, and the LLD says so. | `03-LLD.md` §2.9, §3.8, §6.2, §6.5, §12.1 |
| K10 | **Fixed.** The check moves to `emit_specs`, which holds the seed, with a new error `E010_TOOL_MISMATCH` in the same closed code vocabulary. | `03-LLD.md` §2.1, §3.5; `01-FRD.md` §1.7 FR-04.2 |
| K11 | **Fixed.** The FRD is amended at FR-16.2 with the one-signature reasoning stated; the HLD's claim to have amended it is withdrawn and replaced by a pointer. | `01-FRD.md` §1.7 FR-16.2; `02-HLD.md` §0.1, §2.1; `03-LLD.md` §2.5 |
| K12 | **Fixed.** `BuildResult` gains `worker_hostname`, `worker_node_id` and `child_pid`, written by `probe_execute` from `socket.gethostname()`, the Ray runtime context and the child's pid; three columns added; `gate_decide` reads them for the soft anti-affinity and `q1_same_worker`. | `03-LLD.md` §2.9, §3.9, §3.10, §6.2 |
| K13 | **Fixed.** `--runtime-env-json` is restored carrying `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG` and, when set, `GOOGLE_CLOUD_PROJECT`. The token stays out of it. The JSON is built by Python so a path with a space or a quote cannot break the argument. | `03-LLD.md` §11.1, §13.3, §13.4 |
| K14 | **Fixed.** Every reader uses `CandidateRecord.run_commit`: §3.7.2's two scans, §3.8's `cfg["tag"]` and restore, §3.9's question 1, §4.8's three checks. Two tests build a two-entry calibration manifest and assert the second seed's candidate scans from its own commit. | `03-LLD.md` §3.7, §3.7.2, §3.8, §3.9, §4.8 |
| K15 | **Fixed, verified.** The template carries `@CLASS_BLOCK@` and exactly one of three blocks is substituted; a table binds all eleven placeholders; the script `cd`s into its temporary directory with the candidate absolutised first; a subshell with its own stderr suppresses the shell's `Segmentation fault` line. Assembled from the document's own blocks and run: 0 on the recorded crash, 1 on a clean input, 1 on a **different** crash, 1 on a parse error, zero stderr bytes in all four. | `03-LLD.md` §10.2 |
| K16 | **Fixed, verified.** `_ASSERT_UNREACHABLE` loses its dead `msg` group and is anchored; for this class `assertion_text` is the preceding stderr line plus the matched line without its `!`, and `assertion_site` is the location pair or `None`. Tested against a synthetic two-line sample in LLVM's format and against the two degenerate forms. | `03-LLD.md` §3.6.1, §3.6.2 |

---

## WOUND

| # | Disposition | Where |
|---|---|---|
| W1 | **Fixed.** All sixteen `cfg` keys enumerated in a table with the value the adapter passes and why, including `cfg["tag"] = candidate.run_commit` for FR-12.6. | `03-LLD.md` §3.8 |
| W2 | **Fixed.** B8 calls `run_issue_remote(issue_md, local_id, cfg)` **inline**, not `.chia_remote`, so the chain stays on the `repair:1` worker; `docs/concepts/overview.rst:36-37` is the authority and a test asserts the call site. | `03-LLD.md` §3.8 |
| W3 | **Fixed.** `repro_dir` is `<artefact_root>/<run>/repair/<local_id>/` and `repro_path` is `repro.sh` in it; the artefact tree has the directory. | `03-LLD.md` §3.8, §6.5 |
| W4 | **Fixed.** Every one of the eighteen now has a complete typed signature: `normalise_run_line`, `strip_probe_only_options`, `emit_specs`, `classify_build`, `render_report`, `artefact_write`, `init_schema`, `validate_candidate`, `load_candidate`, `mutators.apply`, `load_budget`, `snapshot`, `accrue`, `aggregate`, `stop_reason`, `build_feedback`, `build_image`, `_head_node_id`, plus every `LoopStore` member including the one that inserts a `probe` row. | `03-LLD.md` §2.9, §3.0, §3.3, §3.5, §3.6, §3.7.4, §3.11, §8.2 |
| W5 | **Fixed.** Fourteen, in both places, with the `grep` that checks it. | `03-LLD.md` §3.11, §14.4 |
| W6 | **Fixed.** §1.3 states the mapping exactly: eighteen source modules with tests, one without logic and without a test, two structural tests without sources; and `test_layout.py`'s three jobs are enumerated, the "and nothing else" withdrawn. | `03-LLD.md` §1.3 |
| W7 | **Fixed.** `probe_task.py` imports the **record dataclasses** from `store`, never `LoopStore`, and never opens `loop.db`; the head writes the rows. Both sentences are now true and the test asserts the direction that matters. | `03-LLD.md` §3.6 |
| W8 | **Fixed.** `_DICT_KEYS` gains `RunManifest.model_ids` and `RunManifest.stages_metered`; the latter's key set is the `_STAGE_IDS` constant, which is `00-README.md`'s own stage list. | `03-LLD.md` §2.1, §2.6, §2.7 |
| W9 | **Accepted with a decision.** The FRD wins, so the FRD is amended: FR-04.3's contents are satisfied inline **or** by the always-populated path, and `_probe_spec_conditionals` enforces the disjunction. Making `input_text` required instead would put a 256 KiB blob in every spec and defeat `02-HLD.md` §2.12's accepted cap rule. | `03-LLD.md` §2.4, §2.8; `01-FRD.md` §1.7 FR-04.3 |
| W10 | **Accepted with a decision.** `BashTool` is withdrawn from stages 1, 2 and 6 and replaced by `SourceReadTool`, a new read-only `ChiaTool` on the head with `read_file`, `grep` and `list_dir`, each one `git` argument vector at the run's commit, no shell. All three commands were run against the real clone. B8 keeps CHIA's `BashTool` unchanged, because FR-12.1 forbids otherwise. | `03-LLD.md` §1.1, §3.5, §7.2, §7.4, §14.1, §14.3; `02-HLD.md` §0.1, §1.1, §1.4, §3, §9; `01-FRD.md` §1.7 FR-04.4 |
| W11 | **Fixed.** Both tools are constructed inside a `try` and stopped in a `finally`, which is CHIA's own shape at `issue_task.py:282-289`. | `03-LLD.md` §3.5 |
| W12 | **Fixed.** The sample is drawn by `bug_loop.py --draw-calibration` and pasted in **before** the pre-registration commit; §9.5 ships a drawn sample marked as an illustration; `budget.py` gains a fifth check, `len(calibration_sample_shas) == calibration_sample_size`; `_manifest_conditionals` additionally requires a calibration manifest's `run_commit` entries to be exactly its sample. | `03-LLD.md` §2.8, §9.2, §9.5, §13.1 |
| W13 | **Fixed.** `reduction_wall_seconds` becomes 600 `[DEFAULT]` with the 56-call measurement as the reason; the interestingness script's per-call wall is `probe_wall_seconds`, and §9.5 says the two are different numbers. What 600 s buys is `[UNVERIFIED]` and is §15 item 5. | `03-LLD.md` §9.1, §9.5, §10.2, §15 |
| W14 | **Fixed, verified.** `cd "$WORK"` added, with the candidate absolutised before it because `circt-reduce` passes a path relative to its own cwd. The observed `Segmentation fault` noise is suppressed by the subshell; both the noise and its absence were measured. | `03-LLD.md` §10.2 |
| W15 | **Fixed.** FR-13.15's second conjunct is answered as `GateDecision.q3_after_parse`, from the recorded fingerprint frame's file and the probe's argv, with no extra process. | `03-LLD.md` §2.9, §3.9, §4.8 |
| W16 | **Fixed.** FR-16.6's "same reason" is the equal multiset of `(build_status, stopping_reason)` pairs over two consecutive iterations, with every result in `{parse_error, timeout, oom}`; FR-16.4's deny-list is written out as `_FEEDBACK_DENY` with the test that uses it. | `03-LLD.md` §3.11 |
| W17 | **Fixed.** §3.9 question 3 now cites §4.8; §4.8 says **four** points. A third, unreported cross-reference defect was found and fixed in the same pass: §3.7.4 cited §7.3.2 for the substitution table, which is §7.4.1. | `03-LLD.md` §3.7.4, §3.9, §4.8 |
| W18 | **Fixed, verified.** Seven CHIA lines plus five added is twelve; `awk 'NR>=92 && NR<=98'` over `ChiaCirctBaseDockerfile` prints seven. The ccache citation is split: `PATH` at line 77, `-DCMAKE_CXX_COMPILER=clang++` at line 97. | `03-LLD.md` §4.11 |
| W19 | **Fixed.** §1.1 gains `pyproject.toml` with its one `[project.scripts]` entry and `.gitignore` with its two lines, and names the two paths the flow writes rather than ships. | `03-LLD.md` §1.1, §13.2 |
| W20 | **Fixed.** `--user $(id -u):$(id -g)` on every worker type, with the ownership reason stated; the `/etc/passwd` line was already on all three. | `03-LLD.md` §12.1; `02-HLD.md` §0.1, §4.1 |
| W21 | **Fixed.** The restore re-hashes every tool binary against `ImageSpec.tool_hashes` and records `restore_hashes_match`; `restore_ok` is the conjunction of reset, build and hashes. Whether a revert-and-rebuild is bit-identical is `[UNVERIFIED]` and is §15 item 4, with the one-build experiment that settles it. | `03-LLD.md` §2.9, §3.8, §6.2, §15 |
| W22 | **Fixed.** `_DEDUP_EVIDENCE_KEYS` and `_DEDUP_EVIDENCE_REQUIRED` are written out and `validate_candidate` enforces them, which gives FR-10.5 an enforcement point for the first time. | `03-LLD.md` §2.9 |
| W23 | **Fixed.** The stage-6 prompt gains three differential variables and a rule binding the six primary ones to a literal for that class, so `safe_substitute` leaves no `$name` behind; §7.4.1 gains a separate twelve-row substitution table for the `differential` template, and the self-contradictory sentence is withdrawn. | `03-LLD.md` §3.7.4, §7.4, §7.4.1 |
| W24 | **Fixed, verified.** `_check_field` accepts an `int` where `float` is annotated and rejects a `bool` where `int` is. `isinstance(5, float)` is `False` and `isinstance(True, int)` is `True`, both run. | `03-LLD.md` §2.3, §2.6 |
| W25 | **Fixed.** `bug_loop.py --refresh-mirror`. | `03-LLD.md` §13.1 |
| W26 | **Fixed.** `artefact_inline_cap_bytes` becomes 262,144 `[DEFAULT]`, one number doing three jobs (the spec's inline copy, a `SourceReadTool` return, a `SeedRecord`'s text), which is why it stays a `budget.yaml` key. | `03-LLD.md` §6.5, §9.1, §9.5 |
| W27 | **Fixed.** A table gives every `RunManifest` field a named producer, by source. | `03-LLD.md` §13.1 |
| W28 | **Fixed, verified.** `provider.head_ip: ${BUGLOOP_GCP_HEAD_IP}` and an `auth` block added; `load_config("cluster_gcp.yaml")` returns a `ClusterConfig` with the two placeholders set. Still marked deferred. | `03-LLD.md` §12.2, §13.4 |

---

## NIT

| # | Disposition | Where |
|---|---|---|
| 1 | **Fixed.** The `oom` row requires death by signal as well as the evidence, which is FR-06.7's own wording; the `address_space` clause keeps its own row because `RLIMIT_AS` does not kill. | `03-LLD.md` §3.6 |
| 2 | **Accepted with a decision, verified.** FR-06.9's seven statuses stay closed, so a rejected argv is still `parse_error`; what changes is `stopping_reason`, `tool_rejected_argv` against `tool_rejected_input`, keyed on the literal `does not refer to a registered pass or pass pipeline`, with `results.py` printing the two counts separately. Both diagnostics were run. | `03-LLD.md` §3.6, §14.4 |
| 3 | **Fixed.** `store.load_candidate(store, candidate_id) -> CandidateRecord` joins the five sibling tables back into the object `validate_candidate` checks. | `03-LLD.md` §2.9 |
| 4 | **Fixed, verified.** `CHECK ((value IS NULL) = (basis = 'insufficient'))` on `fingerprint`; the DDL runs. | `03-LLD.md` §6.2 |
| 5 | **Fixed.** `BudgetFile` has no table because its contents are already persisted twice, in the repository and in the artefact copy, and a third copy could disagree with both; `run.budget_file_sha` is what a query needs. | `03-LLD.md` §6.5 |
| 6 | **Fixed.** `_probe_result_conditionals` now ties `assertion_text` and `assertion_site` to `oracle_class == "assertion"`, as `CandidateRecord`'s rules already did. | `03-LLD.md` §2.8 |
| 7 | **Fixed.** The exemption is stated with its reason: the seam is neither half, and FR-16.2 and FR-05.4 make three `ProbeSpec` fields conditional on the arm, so the validator must branch. The walk's exempt list is three names, each with its reason. | `03-LLD.md` §14.5 |
| 8 | **Fixed.** `from_json`'s docstring says the drop is deliberate and is §2.2's MINOR rule, and says why a MAJOR-newer document cannot reach it. | `03-LLD.md` §2.3 |
| 9 | **Fixed.** The structural hash now normalises `@symbol` names as well as SSA values, so a renamed module hashes alike. The other half is answered: a `differential` candidate is never reduced (FR-09.8), so no renamed module reaches `arcilator --jit-entry`. | `03-LLD.md` §3.7.1 |
| 10 | **One fixed, two rejected.** `ChiaFunction.py` becomes `228-232`: `def options` is at 228 and the merge at 232, so the LLD's range ended one line early and the review's "227" is also wrong. The two `sqlite_node.py` citations are **correct as the LLD had them**: `awk 'NR>=33 && NR<=46'` prints the data-guidance paragraph at **35-38** and the write-semantics paragraph at **40-43**, not 36-39 and 41-45. The check is recorded in the LLD. | `03-LLD.md` §3.0 |
| 11 | **Fixed.** §12.1's comment now names both consequences of `git clean -fd` in the same place, the surviving build tree and the deleted `.circtissues`, and points at §3.8. | `03-LLD.md` §12.1 |
| 12 | **Fixed.** `bugloop_llm` has no `--cpus`/`--memory` because it is network-bound and holds no CIRCT tree, so NFR-05's outer level has nothing to protect; the YAML says so. | `03-LLD.md` §12.1 |
| 13 | **Fixed.** §11.2 warns that the campaign writes `skipDangerousModePermissionPrompt` into the operator's real `~/.claude/settings.json` and that the change outlives the run, and names the `HOME` workaround. CHIA's mechanism is unchanged, because changing it would be a change to a CHIA file rather than an addition. | `03-LLD.md` §11.2 |
| 14 | **Fixed.** The `url` refusal is stated on the accept side: scheme `https`, host exactly `github.com`, path beginning `/llvm/circt/issues/` and ending in digits. | `03-LLD.md` §13.2 |
| 15 | **Fixed.** §4.13's `circt-translate` row now records that `bslang/bin` holds no `firtool`, `circt-reduce` or `arcilator`, so branch (a)'s six-target build is unmeasured, which §15 item 2 already said. | `03-LLD.md` §4.13 |
| 16 | **Fixed.** §6.5 is the normative tree and §10.2 now says "per probe" too, with the 1:1 note. | `03-LLD.md` §6.5, §10.2 |
| 17 | **Fixed.** `parse_json_footer`'s docstring gives the three lines: `finditer`, `blocks[-1]`, and why `re.search` would be the opposite rule. | `03-LLD.md` §7.1 |

---

## The review's single question, answered

**"Where does a worker node get CIRCT history from?"** It does not. A1, A2 and B6b move to the head
and read the head's blobless clone; `SeedRecord` grows `diff` and `test_files` so A3 and A4 need no
history at all; FR-04.1's site check becomes `corpus.resolve_sites`, a head node; and the generator's
source access becomes `SourceReadTool`, whose server is pinned to the head. No cluster YAML gains a
mount, no worker gains a clone, and §11.1's posture that a worker reaches nothing the head holds is
unchanged. The price is one contract MAJOR bump, which `00-README.md`, `02-HLD.md` §2.4 and
`03-LLD.md` §2.1 all carry.

## The review's ten riskiest assumptions, after this revision

| # | Assumption | State now |
|---|---|---|
| 1 | A CIRCT assertion matches `_ASSERT_GLIBC`. | **Resolved.** It does, with `.+?`. Measured both ways. |
| 2 | `llvm-symbolizer --obj=<tool>` resolves the addresses `_FRAME` captures. | **Resolved.** It does not, and the recipe now uses the module and the offset. Measured both ways. |
| 3 | The top-5 frame tuple identifies a bug. | **Resolved against the tuple.** Nine distinct tuples over ten runs of one input; the fingerprint is now the signal plus the first CIRCT frame, three distinct over the same ten, and `fingerprint_stable` reports the rest. |
| 4 | `git fetch --depth 1 origin <sha>` leaves the `firtool-*` tag reachable. | **Resolved.** It does not; a second `fetch ... tag <name>` brings it. Reproduced. |
| 5 | A `circt:1` worker can run A1's five git commands. | **Removed.** A1 is a head node. |
| 6 | The chain's reset leaves `.circtissues` alone. | **Resolved.** It does not; the repro directory moves outside the tree. |
| 7 | `limit_hit` is observable. | **Resolved.** With a soft:hard CPU pair and `os.wait4` it is. Measured. |
| 8 | A `chia job submit` job inherits the submitter's environment. | **Resolved.** It does not; the wrapper forwards the three non-secret variables. |
| 9 | `ninja` after `git reset --hard` reproduces the published binaries byte for byte. | **Still open**, now measured per attempt as `restore_hashes_match` and listed as §15 item 4 with the one-build experiment. |
| 10 | `circt-reduce` gets more than one or two interestingness calls inside `reduction_wall_seconds`. | **Budget raised to 600 s**; what it buys is §15 item 5. A new observation was recorded on the way: on a parser-overflow input `circt-reduce` itself died, so §4.7 now routes a `reducer_aborted` to the textual reducer. |
