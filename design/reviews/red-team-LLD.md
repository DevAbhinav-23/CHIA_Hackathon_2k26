# Red-team review: `03-LLD.md`

**Posture: hostile.** The brief is to break the document before code is written from it, not to fix
it. Nothing here is a suggestion; every item is a defect with its evidence.

**Target.** `design/03-LLD.md` (35,815 words), read end to end.
**Normative upstream.** `01-FRD.md` incl. §1.5 and §1.6 errata, `02-HLD.md`, `00-README.md`, the 14 ADRs.
**Facts.** CHIA at `~/.cache/chia-src` @ `16c35e92`; CIRCT clone at `~/.cache/chia-pin-smoke/circt`
@ `b792c772`; SDK at `~/.cache/chia-pin-smoke/circt-sdk`; measured assertions-on build at
`~/.cache/chia-pin-smoke/bassert_g`; slang build at `~/.cache/chia-pin-smoke/bslang`. Binaries run
under `LD_LIBRARY_PATH=~/.cache/chia-pin-smoke/circt-sdk/lib:~/.cache/chia-pin-smoke/shim`.
**Date.** 2026-09-13.

**What was executed.** The whole DDL of §6.2 plus §6.3 in `sqlite3 :memory:` (exit 0). Every Python
block through `ast.parse` (3 fail, all deliberate indented fragments). §2.1 to §2.8 assembled into a
working `schema.py` under Python 3.10.21 and exercised. Both cluster YAMLs through
`chia.cluster.config.load_config`. `budget.yaml` through PyYAML and against its own §9.1 schema. Both
shell blocks through `bash -n` and `sh -n`; `bug_loop_submit.sh` run with `chia` stubbed. The
interestingness template instantiated and run against `bassert_g/bin/circt-opt` on a real crashing
input and two non-crashing ones. `circt-reduce` driven end to end with an interestingness script. The
`_ASSERT_GLIBC`, `_ASSERT_UNREACHABLE` and `_FRAME` regexes run against real tool output. The
symbolizer recipe of §4.9 run against a real stack trace. The §4.11 fetch-and-pin-check recipe
reproduced against the CIRCT clone. `prlimit` CPU and address-space limits observed. CHIA signatures
read with `inspect` in `~/.cache/chia-venv`.

**Counts.** 16 KILL, 28 WOUND, 17 NIT. 61 findings.

---

## Summary judgement

The document is unusually well cited and most of its citations are correct: I re-read 40 of the
`chia:` and `circt:` line references and found no fabricated one. The command-line work in §4 is
genuinely verified. The DDL runs. The cluster YAML parses. The budget file validates against its own
schema.

The failures are concentrated in three places, and they are the three places that decide whether the
campaign produces a number at all.

1. **The oracle cannot classify a CIRCT assertion, and cannot symbolise a CIRCT crash.** Both are
   demonstrated below by running the document's own regexes and its own `llvm-symbolizer` command
   line against real output from the measured build. Neither defect is subtle; both were hidden by
   measurements taken on the one input shape that cannot occur in practice (a C file, and an address
   that happened to be resolvable).
2. **The two generator arms cannot reach their inputs.** A3 needs the seed's diff, A4 needs the
   seed's test-file contents, A1 needs the whole first-parent history. All three run on
   `resources={"circt": 1}` worker containers whose only CIRCT tree is a `--depth 1` checkout of one
   commit, and whose only bind mount is the artefact root. `SeedRecord` carries no diff and no file
   contents. There is no path from the seed commit to the prompt.
3. **The image cannot be built as written.** The fetch-by-SHA recipe leaves no `firtool-*` tag in the
   repository, so the FR-03.2 pin-equality check on the next line always fatals.

Each of those is independently fatal to the Must set. Behind them sits a fourth, quieter problem:
the document repeatedly asserts that a check exists when the code it shows cannot perform it
(`E004_BAD_ENUM` for a wrong tool; `limit_hit`; the `@TOP_FRAME@` guard; FR-13.2's "a node other than
the original"). Those are the items a typist will implement as written and only discover during the
campaign.

---

## KILL

Typed in as written, it would fail or violate an FR.

### K1. `_ASSERT_GLIBC` cannot match a C++ assertion, so no CIRCT assertion is ever classified as one

**§3.6.1**, lines 1508-1510.

```python
_ASSERT_GLIBC = re.compile(
    r"^(?:.*?: )?(?P<file>[^\s:]+):(?P<line>\d+): "
    r"(?P<func>[^:]+): Assertion `(?P<expr>.*)' failed\.$")
```

`(?P<func>[^:]+)` forbids a colon. glibc's `__assert_fail` prints `__PRETTY_FUNCTION__`, which for
every C++ member or namespaced function contains `::`. CIRCT is C++.

Run:

```
$ cat b.cpp
#include <cassert>
namespace circt { struct Foo { int get(int c) const { assert(c > 99 && "needs many args"); return c; } }; }
int main(int c, char**){ circt::Foo f; return f.get(c); }
$ c++ -O0 -o b_assert b.cpp && ./b_assert
b_assert: b.cpp:2: int circt::Foo::get(int) const: Assertion `c > 99 && "needs many args"' failed.
rc=134
$ python3 -c "<the regex above>.match(line)"
  LLD _ASSERT_GLIBC match: None
```

The C control the LLD cites *does* match (`a_assert: a.c:2: main: Assertion ...` -> `func='main'`),
which is exactly why the defect survived: §3.6.1 says "The glibc pattern is measured, not assumed. A
three-line **C** file compiled and run on 2026-09-13 printed exactly ...". The measurement chose the
one function-name shape that has no `::`.

Consequences, all of them in the Must set: `classify_build` (§3.6 step 3) falls through to `crash`
for every CIRCT assertion, since the child died by `SIGABRT` and stderr has no `LLVM ERROR:` line, so
**FR-06.9**'s seven-way classification never produces `assertion` and F-06's own feature acceptance
("the batch ... produces all seven") cannot pass. **FR-07.1**, **FR-07.2** and **FR-07.3** fail.
G-43's assertion branch, which is the *stable* half of the fingerprint, never fires, so every
candidate takes the frame-tuple branch that K2 and K3 break. The interestingness script's
`# --- class: assertion ---` block of §10.2 is never emitted.

### K2. The symbolisation recipe of §4.9 and §3.10 resolves nothing on a real CIRCT stack trace

**§3.6.2 step 3**, **§3.10 `circt_symbolize`**, **§4.9**.

`_FRAME` captures the *runtime* address (`(?P<addr>0x[0-9a-f]+)`), and §4.9's invocation is

```
<sdk>/bin/llvm-symbolizer --obj=/workspace/circt/build/bin/<tool> --demangle --output-style=JSON
```

with those addresses on stdin. But CIRCT built against the shared-library SDK puts almost every frame
in a `.so`, and LLVM prints the *file offset* inside the module in the parentheses, not the runtime
address. Feeding runtime addresses with `--obj=<the tool>` asks the symbolizer about an object those
addresses are not in.

Run, against a real segfault produced by `bassert_g/bin/circt-opt`:

```
$ # trace frames, parsed with the LLD's own _FRAME regex:
  #0 0x00007f785843cceb llvm::sys::PrintStackTrace(...) (.../libLLVMSupport.so+0x23cceb)
  #4 0x00007f785a10cbf6 mlir::detail::Parser::parseAttribute(mlir::Type) (.../libMLIRAsmParser.so+0x22bf6)
$ llvm-symbolizer --obj=$HOME/.cache/chia-pin-smoke/bassert_g/bin/circt-opt --demangle --output-style=JSON < addrs.txt
{"Address":"0x7f785843cceb","ModuleName":".../circt-opt","Symbol":[{"FunctionName":"","FileName":"","Line":0,...}]}
{"Address":"0x7f785a10cbf6","ModuleName":".../circt-opt","Symbol":[{"FunctionName":"","FileName":"","Line":0,...}]}
   (all six frames: FunctionName "", FileName "", Line 0)
```

The correct recipe, using the module and the offset from the parentheses, works:

```
$ printf '0x22bf6\n' | llvm-symbolizer --obj=.../lib/libMLIRAsmParser.so --demangle --output-style=JSON
{"Symbol":[{"FunctionName":"mlir::detail::Parser::parseAttribute(mlir::Type)","FileName":"","Line":0,...}]}
```

`circt_symbolize(obj_path: str, addresses: list[str])` is structurally unable to do that: one object
path, a list of bare addresses. Nothing in the document extracts `<module>` or `+0x<offset>`, even
though §3.6.2 says "the first shape ends `(<module>+0x<offset>)` and is what `circt_symbolize`
resolves".

Consequences: `frames_resolved == 0` and `frames_with_location == 0` on every candidate, so
**FR-07.4**'s AC ("frames are non-empty and **name a CIRCT source file and line** for a crash inside
CIRCT") fails; `out_of_scope_root` (FR-07.5) is undecidable; the crash and fatal-error fingerprint
basis is `insufficient` for every candidate, so **FR-10.8** routes all of them to gate question 4's
refusal and **no crash candidate can ever be filed**. The whole `-gline-tables-only` argument of
FR-03.4 buys nothing, because the recipe never reaches a CIRCT object.

Second-order: the SDK's prebuilt `.so` files carry no debug info. Even with the corrected recipe,
`printf '0x22bf6\n' | llvm-symbolizer --obj=libMLIRAsmParser.so` returns `FileName:"" Line:0`. Only
frames inside CIRCT's own source-built libraries can satisfy FR-07.4. The document never says so.

### K3. The frame-tuple fingerprint is mostly signal-handler boilerplate, and is not stable across re-runs of the same input

**§3.7.1**, and **§10.2 detail 5**.

`fingerprint_top_n` is 5 (§9.5). §3.7.1 takes "the ordered list of normalised function names of the
resolved frames, skipping frames whose function is empty". Every LLVM crash begins with the same
three resolvable frames plus one unresolvable libc frame:

```
  #0 llvm::sys::PrintStackTrace(llvm::raw_ostream&, int)
  #1 llvm::sys::RunSignalHandlers()
  #2 SignalHandler(int, siginfo_t*, void*)
  #3 (/usr/lib/libc.so.6+0x44e70)          <- empty function, skipped
  #4 <the first frame that says anything>
```

So three of the five fingerprint slots are constant across every crash in the campaign, and only two
discriminate. For a `fatal_error` the prologue is deeper still (`__restore_rt`, `pthread_kill`,
`raise`, `abort`, `report_fatal_error`), so the top five are *entirely* boilerplate and **every
`fatal_error` in the campaign fingerprints identically** — which collapses G-44's "distinct" and
therefore **FR-18.3**'s headline.

Worse, the tuple is not reproducible. Two runs of the *same* input, `deep.mlir`, on the same binary:

```
run 1  #4 mlir::Lexer::lexToken()                          #5 mlir::detail::Parser::parseToken(...)
run 2  #4 (anonymous namespace)::OperationParser::parseGenericOperation()   #5 ...::parseOperation()
```

which gives two different fingerprints for one bug. **FR-10.2**'s partition is then order- and
run-dependent, and gate question 1's "does it reproduce" comparison is answered against a moving
target.

The same defect makes §10.2's `@TOP_FRAME@` guard vacuous: "the first resolved frame's normalised
function name" is `llvm::sys::PrintStackTrace` for every crash, so `grep -qF @TOP_FRAME@` matches any
crash at all. §10.2 detail 5 claims it stops "a crash that moves to a different function during
reduction"; it stops nothing. Verified by running the instantiated template: it returned 0 on the
crashing input and 1 on both non-crashing ones, but the frame check contributed nothing to that.

The document nowhere says to strip the crash-handler prologue, and G-43 leaves the normalisation to
`03-LLD.md`.

### K4. The image's pin-equality check cannot run after the fetch-by-SHA recipe

**§4.11**, "The source fetch" and "The pin equality check".

```
git init circt && cd circt
git remote add origin https://github.com/llvm/circt.git
git fetch --depth 1 origin ${CIRCT_SHA}
git checkout --detach FETCH_HEAD
```
```
test "$(git -C circt ls-tree ${CIRCT_SHA} llvm | awk '{print $3}')" = \
     "$(git -C circt ls-tree ${CIRCT_VER} llvm | awk '{print $3}')" || exit 1
```

`git fetch --depth 1 origin <sha>` fetches one commit and **no tags**. `${CIRCT_VER}` is a
`firtool-*` tag that is not in the repository. Reproduced against the real clone:

```
$ git init -q circt && cd circt && git remote add origin <clone>
$ git fetch --depth 1 origin b792c772...
$ git ls-tree b792c772... llvm
160000 commit e297b52ec9d8b5c38042e53ae5650922717970cd	llvm      (rc=0)
$ git ls-tree firtool-1.99.2 llvm
fatal: Not a valid object name firtool-1.99.2                     (rc=128)
$ <the pin check verbatim>
PIN CHECK FAILED (exit 1)
```

So the Dockerfile always exits 1 and **FR-03.1 and FR-03.2 cannot both be satisfied by this recipe**.
There is a second, independent break in the same block: §1.2 says the image is `FROM` CHIA's own
`ChiaCirctBaseDockerfile` layers, which already contain `/workspace/circt` as a
`git clone --depth 1 --branch "${CIRCT_VER}"` (`chia:dockerfiles/ChiaCirctBaseDockerfile:85-86`).
`git init circt` into that directory re-initialises the existing repository and
`git remote add origin` then fails with "remote origin already exists", aborting the `RUN`. The
recipe is written as if for an empty directory and used as if for the base's populated one.

### K5. A1, A2 and B6b are `circt:1` worker nodes that read a head-only clone no container mounts

**§3.2** gives A1 `corpus.py:build_corpus`, A2 `pin_select.py:select_release_pinned_main` and B6b
`triage_task.py:dedup_and_screen` all `@ChiaFunction(resources={"circt": 1}, max_retries=0)`.
**§3.3**'s docstring says "Worker: `{"circt": 1}` - it runs git against a clone on the worker's
filesystem." **§13.1** says `--clone` defaults to `~/.cache/circt` and is "The blobless `llvm/circt`
clone A1, A2 and B6b read."

**§12.1**'s `bugloop_circt` `run_options` mount exactly two things: `${BUGLOOP_ARTEFACTS}` and the SSH
agent socket. There is no mount for the clone, and inside the container `~` is `/home/ray`. So
`~/.cache/circt` does not exist on the worker.

The only CIRCT tree that *does* exist there is `/workspace/circt`, which §4.11 creates with
`git fetch --depth 1` of a single commit. Against such a repository:

- A1 step 2, `git for-each-ref refs/tags/firtool-*`, returns nothing, so `build_corpus` raises
  `CorpusError("no_tags")` and, by §3.3's own rule, "the run does not start".
- A1 step 4, `git log --first-parent ... HEAD`, returns one commit, so FR-01.1's 187/171 counts are
  unreachable.
- A2 walks first-parent `main` over 24 months (FR-02.5). One commit.
- B6b's two commit scans (§3.7.2) need `--since <24 months>` over `main`.

Either the three nodes belong on the head (contradicting §3.2, §3.3's docstring and the "runs git
against a clone on the worker's filesystem" sentence) or the clone must be bind-mounted (contradicting
§12.1, and §11.1's "No worker container mounts it and no cluster YAML mentions it" posture for a
different file). The document never picks. **FR-01.1, FR-01.8, FR-01.11, FR-02.1 to FR-02.6, FR-10.4
and FR-15.1 all rest on this.**

Note the operational aside in §4.12 — "the contamination scan fetches one blob per round trip and took
488 s over 1,650 commits ... B12 **may run the backfill once before the first screen**" — confirms the
author was thinking of a head-side blobless clone while the decorator says worker.

### K6. Neither arm can reach its seed's contents: `$diff`, `$test_files` and the mutation arm's starting inputs have no source

**§7.2**, **§7.3**, **§8.2**, against **§2.4**.

§7.2 declares substitution variables `$seed_sha, $subject, $diff, $test_files, $run_lines,
$entry_tool, $max_sites`. `SeedRecord` (§2.4) carries `seed_sha`, `parent_sha`, `subject`,
`committed_date_utc`, `source_paths`, `test_paths`, `run_lines`, `argv_template`, and nothing else
textual. **There is no `diff` field and no test-file contents.** §3.5 describes A3's body as CHIA's
turn machinery plus "two things ... new: the two prompts of §7, and the emitter" — so no step obtains
the diff, and §13.1's run loop does not either.

The obvious implementation, `git -C /workspace/circt show <seed_sha>`, is impossible for the reason in
K5: the worker's tree is a `--depth 1` checkout of the *run's* commit, and the seed commits (up to 24
months older) are not objects in it.

Identically for A4: §8.2's `mutate_seed(seed, iteration, cap, mutator_set)` returns `mutant_text`, so
it must have read each changed test file's bytes, but its own docstring says "Worker: **pure**; no
worker resource and no model", and `SeedRecord.test_paths` are paths. FR-05.1's AC — "the arm's input
record contains only the test files and their `RUN:` lines" — has no object to point at. Where the
file is read, and at which commit (the seed's, where the test exists, or the run's, where it may have
been deleted or changed), is never stated.

Knock-on: **FR-16.5**'s AC is "replaying iteration k from its recorded `SeedRecord` plus
`FeedbackBundle` reproduces the same prompt bytes". With `$diff` and `$test_files` outside both
objects, it cannot.

### K7. FR-10.3's issue-mirror screen has no algorithm anywhere in the document

**§3.7**, **§3.7.1**, **§3.7.2**.

FR-10.3: "shall screen every candidate against CIRCT's open **and** closed issues for a match on the
candidate's assertion text and its reduced case's distinctive tokens, reading the local mirror of
FR-10.9". Its AC: "a candidate seeded from a known closed CIRCT issue is reported
`known_closed_issue` with that number".

`dedup_and_screen`'s docstring returns a `DedupVerdict` whose `Literal` includes `known_open_issue`
and `known_closed_issue`. §3.7.1 specifies the fingerprint and the candidate-to-candidate partition.
§3.7.2 specifies the post-pin-fix scan and the contamination scan. **Neither of those, nor anything
else in the document, says how a candidate is matched against the mirror.** "Distinctive tokens" is
never defined; no query, no index on `issue_mirror(title|body)`, no scoring rule, no threshold.
`grep -n 'known_open_issue\|distinctive' 03-LLD.md` returns only the enum declaration and the
tool-verdict-wins rule in §3.7.3.

Two of the six `DedupVerdict` values are therefore unreachable, FR-10.3 is unimplemented, FR-13.9's
`good first issue` refusal (which reads `dedup_evidence.issue_labels`) has no producer, and F-10's
feature acceptance ("correctly labels at least one candidate as `known_closed_issue`") cannot pass.

### K8. `limit_hit` is consumed in three places and derived in none, and a CPU-limit kill is misclassified `crash`

**§3.6 step 3**, **§3.10 `circt_exec_probe`**, **§2.9 `BuildResult`**.

`classify_build(rc, signal, stderr, limit_hit)` tests `limit_hit == "address_space"` first and
`limit_hit` is a `Literal["wall", "cpu", "address_space"]` column in `build_result`. `circt_exec_probe`
lists `"limit_hit": str | None` among its return keys. **No rule anywhere says how it is computed.**
`grep -n limit_hit 03-LLD.md` returns six hits, all declarations or consumers.

It is not observable from outside the child. `RLIMIT_AS` does not kill; it makes allocation fail.
`RLIMIT_CPU` set by `prlimit --cpu=N` sets soft == hard, so the kernel escalates past `SIGXCPU`
straight to `SIGKILL`. Measured:

```
$ prlimit --cpu=1 -- python3 -c 'while True: pass'
returncode: -9  (SIGKILL)   stderr: b''
$ prlimit --as=104857600 -- python3 -c 'b=bytearray(500*1024*1024)'
returncode: 1   stderr: MemoryError
```

So a probe that exhausts `probe_cpu_seconds` arrives at `classify_build` as: died by signal, empty
stderr, `limit_hit` unknown. The table then classifies it **`crash`**, the primary oracle fires
(§3.6.2 step 1), and a candidate is created. §9.5 sets `probe_cpu_seconds: 45` below
`probe_wall_seconds: 60`, so for any compute-heavy probe the CPU limit binds *first* and this is the
common path, not an edge. **FR-06.2**'s "shall record which if any was hit" and **FR-07.8** both fail;
the `oom`/`timeout` taxonomy rows of **FR-18.6** are systematically under-counted and `crash` is
inflated.

The SIGKILL from the CPU limit is also indistinguishable from the wall-clock killer's own
`os.killpg(..., SIGKILL)` (§3.10), so the `timeout`-with-null-signal rule of FR-06.4 has no way to
tell the two apart without `getrusage`, which is not mentioned.

### K9. FR-12.3's pre-written repro is deleted by the unmodified chain's own first action, then overwritten by its reproduce turn

**§3.8**, "The pre-written repro".

The LLD writes `repro.sh` and `case.<ext>` with
`circt_util.circt_write_files({...}, cfg["repro_dir"])` "before the chain starts", then invokes
CHIA's unmodified `run_issue_remote`. CHIA's step 0 is
(`chia:examples/circt_issue_solver/issue_task.py:145-149`):

```python
circt_util.circt_trust_source()
if not assess_only:
    circt_util.circt_warm_build(cfg["tool_targets"], num_cpus=cfg["build_jobs"])
reset = circt_util.circt_git_reset(cfg["tag"])          # git reset --hard <tag>; git clean -fd
```

`repro_dir` in every CHIA caller is `/workspace/circt/.circtissues`
(`chia:examples/circt_issue_solver/circt_issue_loop.py:46`,
`chia:examples/circt_issue_solver/review_loop.py:41`). That directory is untracked, and it is **not**
ignored — CIRCT's `.gitignore` at `b792c772` lists `/build*`, `/install*`, `/ext`, `obj_dir/`,
`__pycache__`, `lit.site.cfg.py` and the `llvm/` subproject paths, and nothing matching
`.circtissues`. `git clean -fd` (no `-x`) therefore removes it.

Even if it survived, `run_issue_remote`'s phase 1 is `_turn("repro", ...)` with the LLM writing
`<repro_path>` itself (`issue_task.py:201-203`), and the `require_repro` check at line 203 runs
*after* that turn, against the agent's script, not the loop's. The FRD saw this coming — §4.1 of
`01-FRD.md` says "`--replay-regression`'s shape (restore files, re-enter mid-chain) is the nearer
model for FR-12.3's pre-written repro, so F-12 follows it" — and the LLD does not mention the `resume`
parameter at all. **FR-12.3's AC** ("the chain's `reproduce` phase then confirms rather than invents,
and the run's `repro_tail` shows a non-zero exit on the clean tree") cannot hold.

### K10. §3.5 claims the contract validator rejects a wrong tool with `E004_BAD_ENUM`; it cannot

**§3.5** ("The emitter and the cap"), against **§2.4** and **§2.6**.

> "a spec naming a tool other than the seed's classified tool is rejected with `E004_BAD_ENUM` and
> counted, which is FR-04.2's criterion."

`ProbeSpec.tool` is annotated `tool: str`, not a `Literal`, and `_check_field` raises `E004_BAD_ENUM`
only when `typing.get_origin(ann) is Literal`. `validate` has no access to the `SeedRecord`, so it
cannot know the seed's classified tool under any annotation. Run against the document's own code,
assembled from §2.1-§2.8 and imported under Python 3.10.21:

```
--- T2: WRONG TOOL (FR-04.2 AC wants a named error) ---
  validate ACCEPTED tool='firtool' -> FR-04.2 AC not met by the validator
```

**FR-04.2**'s AC is "a spec naming a different tool is rejected by the contract validator with a named
error". §7.3 argues the situation cannot arise because "the argv is built by substituting the written
file's path into the seed's own `argv_template`" — which makes the check unnecessary but does not make
the AC pass, and leaves §3.5's sentence a false statement about §2.6's code.

### K11. §2.5 and §3.5 knowingly violate FR-16.2's unamended acceptance criterion

**§2.5**, **§3.5**.

FR-16.2's AC, verbatim and not in the §1.5 or §1.6 errata lists: "**the mutation arm's call signature
has no feedback parameter**, asserted by a test."

§2.5: "One signature serves both arms. A4 takes `feedback` and does not read it, and
`tests/test_generate_task.py` asserts the non-read on A4's **body** ... rather than on its signature,
which is how FR-16.2 and FR-05.4 are satisfied at once (`02-HLD.md` §2.1, accepted 2026-09-13)."

`00-README.md`: "01 is normative for behaviour ... Where 02 or 03 contradicts 01, 01 wins and the
contradiction is a defect in 02 or 03." The HLD cannot amend an FRD acceptance criterion; §1.5 is the
mechanism for that and FR-16.2 is not in it. Either the FRD is amended at FR-16.2 with the reasoning
stated, or the LLD is wrong. As written the LLD ships a design that a faithful FR-16.2 test rejects.

### K12. Gate question 1 needs the original probe's worker and pid; nothing records them

**§3.9**, against **§2.9** and **§6.2**.

`GateDecision` declares `q1_original_worker`, `q1_original_pid`, `q1_rerun_worker`, `q1_rerun_pid`,
`q1_same_worker`. `gate_rerun` returns `worker`, `node_id`, `pid` for the re-run. **Nothing produces
the original's.** `BuildResult` (§2.9) has no worker, node or pid field; the `build_result`,
`probe` and `probe_result` tables (§6.2) have no such column; `probe_execute`'s return is
`{"build_result", "probe_result"}`. `grep -n '\bpid\b|node_id' 03-LLD.md` finds node identity only in
the two scheduling-strategy expressions and in `gate_rerun`'s return.

So: **FR-13.2**'s AC ("the worker identity, hostname together with Ray node id, and the process id are
recorded for **both** runs") is unsatisfiable, and §3.9's dispatch —
`NodeAffinitySchedulingStrategy(node_id=<a node other than the original>, soft=True)` — has no source
for "the original", which makes `q1_same_worker` unrecordable truthfully and FR-13.2's whole
soft-pin erratum inoperative.

### K13. `bug_loop_submit.sh` forwards no environment, so the driver's two environment defaults resolve to nothing

**§13.3**, **§13.1**, **§13.4**.

The wrapper asserts the variables exist in the *submitting shell*:

```sh
: "${BUGLOOP_ARTEFACTS:?set BUGLOOP_ARTEFACTS to the bind-mounted artefact root}"
: "${BUGLOOP_IMAGE_TAG:?set BUGLOOP_IMAGE_TAG to the assertions-on image tag}"
```

and then passes neither of them, nor `--runtime-env-json`, nor `--artefact-root`, nor `--image-tag`.
Run with `chia` stubbed:

```
$ BUGLOOP_ARTEFACTS=/tmp/a BUGLOOP_IMAGE_TAG=v1 bash bug_loop_submit.sh --mode discovery
CHIA job submit --address http://localhost:8265 -- python .../bug_loop.py --mode discovery
```

§13.1 makes `--artefact-root` default to `$BUGLOOP_ARTEFACTS` and `--image-tag` default to
`$BUGLOOP_IMAGE_TAG`, read inside the job process. A `chia job submit` SUBMISSION job does not inherit
the submitting shell's environment — that is precisely why CHIA's own wrapper forwards `GITHUB_TOKEN`
and `GOOGLE_CLOUD_PROJECT` through `--runtime-env-json`, and says so
(`chia:examples/circt_issue_solver/fix_issues_submit.sh:21-24`, `38-41`, `49`). §11.1 removes the
`--runtime-env-json` line to keep the token out of job metadata, and removes the two non-secret
forwards with it without noticing. **FR-17.9**'s single artefact root has no value at run time, and
pre-flight checks 4 and 5 fail or check the wrong path.

The same deletion drops CHIA's `GOOGLE_CLOUD_PROJECT` forwarding, which §13.1's
`--backend opencode` needs (`chia:examples/circt_issue_solver/circt_issue_loop.py:71-72`, `203-204`).

### K14. `circt_git_reset(manifest.run_commit[0].commit)` is the wrong commit in calibration mode

**§3.8** ("The restore"), **§14.2** FR-12.6.

FR-02.7: "in **calibration** mode it is the seed's own first-parent commit, one value per seed, and
the manifest carries one entry per calibrated seed. FR-10.4, FR-12.6, FR-13.2 and FR-15.5 all read
this field and no other." §2.8's `_manifest_conditionals` enforces exactly that shape.

`manifest.run_commit[0].commit` is then an arbitrary sampled seed's commit, not this candidate's.
`CandidateRecord.run_commit` (§2.9) holds the right value and is not used. The same indexing error is
latent in §3.7.2's post-pin scan ("Lower bound: the run's commit (FR-02.7)"), §3.9's question 1 ("does
it reproduce at the run's commit") and §4.8 ("each runs at the **run's commit**"): in calibration mode
none of the four says which entry.

### K15. The "verbatim" interestingness template names three placeholders and contains eleven, and is not a runnable script

**§10.2**.

> "The three `@NAME@` placeholders are substituted by the loop when the script is written"

```
$ sed -n '3886,3934p' 03-LLD.md | grep -oE '@[A-Z_]+@' | sort -u
@ARGS@ @AS_BYTES@ @ASSERT_EXPR@ @ASSERT_SITE@ @CPU_SECONDS@ @FATAL_MESSAGE@ @GRACE@ @NOFILE@ @TOOL@ @TOP_FRAME@ @WALL@
count: 11
```

Five of the eight unnamed ones (`@WALL@`, `@GRACE@`, `@AS_BYTES@`, `@CPU_SECONDS@`, `@NOFILE@`) are
never bound to a `budget.yaml` key or a §9.4 constant anywhere in the document.

Separately, the block is titled "The template, **verbatim**" and is written into
`<probe dir>/interesting.sh` — but it contains all three class blocks in sequence, and the assertion
block ends `exit 0`, so the fatal-error and crash blocks are dead code. The interleaved comment says
"Exactly one of the three blocks below is emitted", which is a second, contradictory instruction. A
typist following "verbatim" ships a script that is correct only for the assertion class (which K1
prevents from ever arising). `sh -n` passes on it, so nothing catches this.

### K16. `_ASSERT_UNREACHABLE` has no `expr` group, so §3.6.2's extraction raises

**§3.6.1**, **§3.6.2 step 2**.

§3.6.2: "For an `assertion`, `assertion_text` is the `expr` group". `_ASSERT_GLIBC` has one;
`_ASSERT_UNREACHABLE` does not:

```
$ python3 -c "print(_ASSERT_UNREACHABLE.groupindex)"
{'msg': 1, 'file': 2, 'line': 3}
$ m.group("expr")
IndexError: no such group
```

Since an `UNREACHABLE executed` firing is classified `assertion` by §3.6.1's own sentence, step 2
raises on it. Related: `msg` is dead. LLVM prints the message and the phrase on **separate lines**
(`errs() << msg << "\n"` then `errs() << "UNREACHABLE executed"`), so `msg` is always `''`:

```
'Hello there'                                            -> None
'UNREACHABLE executed at .../HWOps.cpp:1234!'            -> {'msg': '', 'file': '...', 'line': '1234'}
```

§3.6.1's claim that "LLVM builds the unreachable line as the message, then the phrase, then optionally
` at <file>:<line>`, then `!`" is wrong about the first element. **FR-07.3**'s "verbatim, character
for character" then yields the empty string for every `UNREACHABLE` firing.

---

## WOUND

Rework needed; not instantly fatal.

### W1. The `cfg` dict CHIA's chain requires is never enumerated

**§3.8** names `cfg["repro_dir"]` and `cfg["build_jobs"]` only. `run_issue_remote` reads eleven keys
plus six prompt bodies: `tag`, `tool_targets`, `repro_dir`, `repro_path`, `require_repro`, `backend`,
`model`, `vertex`, `build_jobs`, `timeouts`, `system_prompt`, `assess_prompt`, `repro_prompt`,
`fix_prompt`, `regression_prompt`, `writeup_prompt` (grepped from `issue_task.py`; assembled in
`circt_issue_loop.py:84-96`). A typist cannot call the chain from §3.8.

`cfg["tag"]` in particular is load-bearing: the chain resets to it (K9), so FR-12.6's AC — "the
chain's `cfg["tag"]` **is the run's commit**" — is an explicit FRD instruction the LLD never restates.

### W2. Whether B8 calls the chain inline or dispatches it is never said, and the two differ in placement

`run_issue_remote` carries its own `@ChiaFunction(resources={"circt": 1})`
(`chia:examples/circt_issue_solver/issue_task.py:38`). If `repair_adapt` calls it as a plain function
it runs inline on the `repair:1` worker, which is the whole point of §12.1's third node type. If it
calls `.chia_remote(...)` — which is how CHIA's own driver invokes it
(`circt_issue_loop.py:250-252`) — it lands on a `circt:1` worker and every argument in §12.1's
`bugloop_repair` comment collapses. §3.8 shows neither call.

### W3. `repro_dir` / `repro_path` for the loop are never given a path

Follows from W1 and K9. If the intent was to move them out of `/workspace/circt` to dodge `git clean`,
that is the decision the document owes; if the intent was CHIA's default, K9 applies.

### W4. Eighteen named callables have no complete typed signature

§10.2 item 2 of the FRD requires "Every module, class and function, with its signature". These are
named and used but never given one, or given an incomplete one:

`corpus.normalise_run_line` (returns a bare `tuple`, contents in prose only),
`corpus.strip_probe_only_options(argv)`, `generate_task.emit_specs(raw: dict, seed, iteration, cap)`,
`probe_task.classify_build(rc, signal, stderr, limit_hit)` (no types, no return),
`triage_task.render_report(template, candidate, reduced, verdict, dedup, manifest)` (no types, no
return), `store.artefact_write`, `store.init_schema`, `store.validate_candidate`,
`mutators.apply(mutator_id, text, seed_int)`, `budget.load_budget(path, repo_root)`,
`budget.snapshot(ledger, arm)`, `ledger.accrue/aggregate/stop_reason`,
`feedback.build_feedback(results, previous, seed_sha, iteration)`, `bug_loop.build_image` (B1; named
in §3.2 and §14.1, never signed), `_head_node_id()` (used in §3.0, never defined), and every
`LoopStore` member other than `__init__` — there is no specified way to insert a `probe` row.

### W5. §3.11 says `results.py` has nine private refusal checks; §14.4 lists fourteen

```
$ grep -o '`_require_[a-z_]*`' 03-LLD.md | sort -u | wc -l
14
```
§3.11: "`render_results(store, manifest) -> str`, and **nine** private refusal checks".

### W6. §1.3's one-to-one test/source mapping is false, and `test_layout.py` is given three mutually exclusive jobs

§1.1 lists 19 `.py` source files (including `contract/__init__.py`); §1.3 lists 20 test modules.
`test_layout.py` and `test_fixtures.py` have no source counterpart; `contract/__init__.py` has no
test. §1.3 nonetheless asserts "There are no test modules without a source module and no source
modules without a test module; that equality is itself asserted by `tests/test_layout.py`" — a test
that fails on itself.

§1.3 also says `test_layout.py` "asserts the one-to-one mapping below, **and nothing else**". §2.9
gives it the store-does-not-import-the-seam check; §14.5 gives it the `ast` walk for FR-18.1. Three
statements, two of them contradicted by the first.

### W7. §3.6 says `probe_task.py` imports no head module, then lists `store`

§3.6: "Imports `contract`, `store`, `ddmin` and `chia.chipyard.circt`, and **no head module**".
§3.11: "`budget.py`, `ledger.py`, `feedback.py`, **`store.py`**, `results.py` and `bug_loop.py` are
head-side". §3.2 places B10a/B10b on the head. One of the two sentences is wrong, and the answer
decides whether a worker can open `loop.db` at all (it cannot — `SQLiteNode` is pinned to the head,
§6.1).

### W8. `_DICT_KEYS` covers six of the eight dicts §2.7 declares closed

§2.7: "Each is a closed set. `validate` compares the key set exactly, so an extra key fails as loudly
as a missing one." `_DICT_KEYS` omits `RunManifest.model_ids` (four named keys per ADR-D-03) and
`RunManifest.stages_metered`. Verified by reading `_MEMBERS`/`_DICT_KEYS` in the assembled module.

### W9. `ProbeSpec.input_text` is optional, and FR-04.3 requires the input file contents

FR-04.3: "The `ProbeSpec` shall carry: ... **the input file contents** ...". AC: "the contract
validator accepts only specs with every field populated". Run:

```
--- T3: input_text absent (FR-04.3 'input file contents') ---
  ProbeSpec.input_text default: None
  validate ACCEPTS a spec with NO input_text
```

§2.8's cap rule (from `02-HLD.md` §2.12) makes this deliberate, but the FRD was not amended and the
LLD does not flag the conflict. Under `00-README.md`'s precedence rule the FRD wins.

### W10. An unrestricted `BashTool` on the CIRCT worker defeats FR-04.4's requirement text

§3.5: "`bash` is CHIA's `BashTool` unchanged ..., **constructed read-only** by pointing `work_dir` at
the CIRCT source tree and by giving the agent no build, lit, oracle, reducer or dedup tool at all."

`BashTool(name, work_dir, timeout_seconds, task_options)` has no read-only mode
(`chia:chia/base/tools/BashTool.py:19-31`); `work_dir` is the shell's cwd, nothing more. The tool is
pinned to the `circt:1` worker, whose `PATH` puts `/workspace/circt/build/bin` first
(`chia:dockerfiles/ChiaCirctBaseDockerfile:113`). The agent can therefore run `circt-opt` on its own
input, run `ninja`, and write anywhere in the tree.

FR-04.4's *text* — "shall not be given, and **shall not be able to reach**, any tool that computes a
measured result" — is violated; its *AC* (a check on the tool list) passes. §7.3 rule 5 forbids it in
prose to the model, which is the weakest possible enforcement and is exactly what NFR-03 exists to
avoid. FR-06.8's "`git status` in the tree is clean after a batch of probes" is at the same risk.

### W11. `ProbeWriteTool` is constructed per iteration and never stopped

`ChiaTool.__post_init__` starts a `_ToolServerActor` per construction
(`chia:chia/base/tools/ChiaTool.py:81-105`), and `ChiaTool.stop()` exists at line 154. CHIA's own
chain stops its three tools in a `finally` (`issue_task.py:282-289`). §3.5 says "Constructed per
iteration with the probe directory bound" and never mentions stopping. At 187 seeds x up to 3
iterations that is up to 561 orphaned actors plus 561 orphaned `bash` tools in one arm window.

### W12. The committed `budget.yaml` registers an empty calibration sample, and nothing checks its size

§9.5 ships `calibration_sample_shas: []` with `calibration_sample_size: 20`. The commit that lands the
file **is** the registration (FR-14.3), and FR-14.7 invalidates the campaign on any later edit. So
either the sample is drawn before that commit — in which case the example is wrong and misleading —
or it is drawn after, which invalidates the campaign. §9.2's four checks do not include
`len(calibration_sample_shas) == calibration_sample_size`, and §2.8's `_manifest_conditionals` would
happily accept a calibration manifest with zero `run_commit` entries.

### W13. The reduction budget and the per-call budget are the same order of magnitude

§9.5: `reduction_wall_seconds: 60`, and the interestingness script's `@WALL@` is unbound (K15) but the
only plausible source is `probe_wall_seconds: 60`. One slow interestingness call then consumes the
entire reduction budget. Measured on a trivial case, `circt-reduce` made **56** interestingness calls
to remove 27% of a six-operation module. On any realistic input the reducer will be killed after one
or two calls, `fixpoint=False`, and **FR-13.3** then refuses every candidate at gate question 2 as
`not_minimal`. F-09's feature acceptance ("produces a strictly smaller input") is at serious risk.

### W14. The interestingness script never enters its own working directory

§10.2 detail 6: "A temporary working directory per invocation, removed on exit by the trap, **because
the tool may write beside its input**". The script creates `WORK="$(mktemp -d)"`, redirects the two
streams into it, and never `cd`s. The tool's cwd is whatever `circt-reduce` inherited, so anything the
tool writes (`-o <probe dir>/t`, `obj_dir/`, crash reproducers) still lands there. The stated reason
is not implemented.

Observed while running it: the shell also prints `Segmentation fault <full command line>` to stderr on
every interesting candidate, which goes into `circt-reduce`'s own stderr thousands of times.

### W15. FR-13.15's "and the recorded failure occurred after that point" has no implementation

FR-13.15's requirement text has two conjuncts; §4.8 and §3.9 implement only the first (parse and
verify). Its AC's third clause — "the recorded failure's stage is later than the check's" — has no
field, no record and no check anywhere in §2, §3 or §6.

### W16. FR-16.6's abandonment rule and FR-16.4's deny-list are both named and never defined

FR-16.6: "every probing input failed at stage 3 **for the same reason** in two consecutive
iterations". §3.11 says `feedback.py` "owns FR-16.6's abandonment" and gives no comparison rule — same
`build_status`? same `stopping_reason` string? The two give different answers.

FR-16.4's AC: "the bundle's schema is checked against **a deny-list of result fields** (candidate
counts, gate precision, bug counts)". §1.3's `test_feedback.py` line says "the deny-list"; the list
itself appears nowhere.

### W17. Two cross-reference defects in the gate section

§3.9 question 3: "the mechanical parse-and-verify check of FR-13.15, whose three command lines are
**§4.6**". §4.6 is `arcilator`; the commands are in §4.8.
§4.8 says "**Three** points, each of which is a decision and not a transcription" and then lists four
bullets.

### W18. §4.11 miscounts CHIA's configure line

"The first **eight** lines are CHIA's, unchanged. The **five** added lines are ...". CHIA's configure
is `chia:dockerfiles/ChiaCirctBaseDockerfile:92-98` — **seven** lines; the block in §4.11 is twelve;
7 + 5 = 12. As written, the eighth line (`-DCMAKE_CXX_FLAGS_RELEASE="-O3 -UNDEBUG -gline-tables-only"`)
is attributed to CHIA when it is FR-03.4's own addition.

§4.11 also cites `ChiaCirctBaseDockerfile:77-79` for "putting `/usr/lib/ccache` on `PATH` **and
passing `-DCMAKE_CXX_COMPILER=clang++` by name**". The second half is at line 97.

### W19. `§1.1`'s file table is missing two files that §6 and §13 require

§13.2: "Installed as `bugloop-approve` by the example's own **console-script entry**". §1.1 lists no
`pyproject.toml` or `setup.py`, and the flow is an `examples/` directory that CHIA does not package.
§6.1 puts `loop.db` at `<repo>/examples/circt_bug_loop/loop.db`; §1.1's table does not list it (nor a
`.gitignore` for it, so an 8-hour campaign's database is a candidate for accidental commit).

### W20. The artefact bind mount has no ownership story, and pre-flight check 5 will likely fail

§12.1 mounts `-v ${BUGLOOP_ARTEFACTS}:${BUGLOOP_ARTEFACTS}` into `bugloop_circt` and
`bugloop_repair`, neither of which passes `--user $(id -u):$(id -g)` (only `bugloop_llm` does, copying
CHIA). The containers therefore run as the image's own user and write into a host directory owned by
the operator. Pre-flight check 5 ("writable **on every worker**") is the right check and the document
offers no remedy when it fails — no mode, no ownership, no `--user` line, no `chmod` guidance. Parsed
through CHIA's own loader, the produced `run_options` confirm the asymmetry:

```
bugloop_llm   : ['--ulimit ...', '--shm-size=10.24gb', '--user $(id -u):$(id -g)', '-v ~/.claude:...', ...]
bugloop_circt : ['--ulimit ...', '--shm-size=10.24gb', '--cpus=6', '--memory=24g', '--memory-swap=24g', '-v /home/adi/art:/home/adi/art', ...]
```

### W21. `restore_ok` does not check what FR-12.11's AC asserts

§3.8: `restore_ok = bool(reset["success"] and build["success"])`. FR-12.11's AC: "after one full
repair attempt on a worker, the **SHA-256 of every tool binary** on it matches the `ImageSpec` map of
FR-03.16, asserted by re-hashing them." A successful `ninja` is not evidence of bit-identity;
`ImageSpec.tool_hashes` is computed "from a freshly started container" (§5.2) while the restore
rebuilds locally. Whether a revert-and-rebuild reproduces the published binaries byte for byte is
**unverified** and the document does not mark it.

### W22. `DedupVerdict.evidence`'s key set is declared and never enforced

§2.9's comment lists seven keys and §14.2 maps FR-10.5 to them, but `DedupVerdict` is a `store.py`
record, so `_DICT_KEYS` does not cover it and `store.validate_candidate` has no specification (W4).
FR-10.5's AC — "no verdict other than `new` is recorded without a populated evidence field" — has no
enforcement point.

### W23. Stage 6 has one prompt and two templates, and the prompt does not fit the differential path

§7.4's `prompts/report_write.md` substitutes `$oracle_class`, `$assertion_text`, `$assertion_site`,
`$frames`, `$repro_command`, `$reduced_case`. A `differential` candidate has no assertion, no frames
(FR-08.10), and no reduced case (FR-09.8). The document never says what B7 is prompted with for that
class, and the prompt's only class-specific instruction is the `fatal_error` clause.

§7.4.1 is also self-contradictory: "The `differential` template **drops** `observed_behaviour` and
`frames`, carries **both** arms' **observed behaviour** with no adjudication".

### W24. `LedgerEntry.amount: float` rejects an int, and every duration in `budget.yaml` is an int

Run: `LedgerEntry(..., amount=5, ...)` -> `E003_WRONG_TYPE: LedgerEntry.amount is int, expected float`.
Only `arm_window_seconds` is a float in §9.5; `probe_wall_seconds`, `reduction_wall_seconds` and the
rest are ints. Any per-stage occupancy computed as an int second count fails validation at run time.
The same hazard sits on `RunManifest.lag_days` (`rev-list --count` differences are ints) and on
`observed["cpu_seconds"]`.

### W25. No way for the operator to ask for a mirror refresh

FR-10.9's AC: "a second run in the same campaign **reuses the mirror unless the operator asks for a
refresh**". Pre-flight check 10 restates it. §13.1's argv has no `--refresh-mirror` flag and no other
mechanism.

### W26. A 10 MB inline cap contradicts the guidance §6.5 itself quotes

§9.5 sets `artefact_inline_cap_bytes: 10485760`. §6.5 then quotes `SQLiteNode`'s own rule
(`chia:chia/database/sqlite_node.py:35-38`: "Store large artifacts as files and put *paths* in the DB;
multi-MB blobs inflate the object store and every `get()`") while arguing the 256,000-byte figure in
CHIA's example "is not a framework limit, and is not used here". A 9 MB `input_text` will pass
`bound_text`, ride the Ray object store, and land in `probe.spec_json`.

### W27. Half of `RunManifest`'s forty fields have no named producer

§2.4 declares `assertion_baseline_count`, `x_policy`, `local_id_range`, `stages_metered`,
`differential_driver`, `confirmation_cutoff_date`, `forum_post_url`, `forum_post_date`,
`tags_sharing_pin`, `sv_seeds_excluded`, `model_ids`, `apparatus_concurrency`, `llm_concurrency`,
`cluster_yaml_sha` as required. §13.1's eleven pre-flight checks name producers for the pin fields,
the mirror and the forum fields only. For the rest the document says the manifest carries them and
never says who computes them or from what.

### W28. `cluster_gcp.yaml` does not parse

```
$ load_config("cluster_gcp.yaml")
  FAIL KeyError 'head_ip'
```
Acknowledged as a deferred skeleton in §12.2, but it is presented as a YAML file in a document whose
standard is "an engineer types it in without asking a question", and §14.1/§14.7 list it as a
deliverable.

---

## NIT

1. §3.6's `oom` rule fires on the stderr patterns **without** requiring death by signal, while
   FR-06.7 requires "terminated by signal **and** its stderr carries an allocation-failure line". A
   diagnostic that merely contains the phrase "out of memory" becomes `oom` rather than `parse_error`.
2. `classify_build`'s `rc != 0 -> parse_error` (G-49) also swallows apparatus misconfiguration.
   Measured: `circt-opt --pass-pipeline='builtin.module(definitely-not-a-pass)' ok.mlir` exits 1 with
   "does not refer to a registered pass", indistinguishable from a rejected input. A bad argv is then
   counted as an input the tool rejected.
3. `candidate` (§6.2) persists 19 of `CandidateRecord`'s 40 fields; `frames_resolved`,
   `frames_with_location`, `repro_command`, `structural_hash`, `fingerprint`, `dedup_*`, `gate_*` and
   the reduction fields live in sibling tables or nowhere. No function is specified that reassembles a
   `CandidateRecord` for `validate_candidate` to check.
4. `fingerprint.value` carries the comment "NULL exactly when basis is 'insufficient'" and no `CHECK`,
   while three sibling columns in the same DDL do carry `CHECK`s.
5. `BudgetFile` is a contract member with no table and no stated reason (the artefact copy of
   `budget.yaml` is mentioned in §6.5 but not offered as the reason).
6. `_probe_result_conditionals` does not tie `assertion_text`/`assertion_site` to
   `oracle_class == "assertion"`, although §2.9's `CandidateRecord` rules do exactly that.
7. `contract/schema.py` itself branches on `arm` (`mutation = o.arm == "mutation"`) and is excluded
   from §14.5's `ast` walk without comment.
8. `from_json` silently drops unknown payload keys (`if k in names`), so a MINOR-newer document loses
   data without a word. §2.2's MINOR rule intends this; the code should say so.
9. `circt-reduce` renames modules during reduction (observed: `hw.module @top` ->
   `hw.module private @Foo`). §4.6's `--jit-entry=bugloop_main` and §3.7.1's structural hash both
   assume otherwise; neither says what happens after reduction.
10. `ChiaFunction.py:228-231` is cited for the `.options()` merge; `def options` is at 227 and the
    merge at 232. `sqlite_node.py:40-43` is cited for the write-semantics paragraph, which is at
    41-45. `sqlite_node.py:35-38` for the data-guidance paragraph, which is at 36-39. Off by one, all
    three.
11. §12.1's comment says "`bugloop_repair` exists because CHIA's phase chain rebuilds ... and the next
    task's reset is `git reset --hard` then `git clean -fd`, explicitly NOT `-x`, so the build tree
    survives" — correct, and it is the same mechanism that deletes `.circtissues` (K9). The document
    understands the mechanism in one section and is defeated by it in another.
12. `bugloop_llm` gets no `--cpus`/`--memory`, unlike the other two types, with no reason given; NFR-05
    describes the outer level as if it were uniform.
13. §11.2 asserts the `~/.claude` mount must be read-write "because CHIA's own `run_setup_commands`
    copy ... and write a `settings.json` key" — true, and it means the campaign writes into the
    operator's real Claude configuration directory. Worth a warning the document does not give.
14. §13.2's `url` subcommand refuses a URL "whose host is not `github.com` **and** whose path is not
    under `llvm/circt/issues/`" — as written the conjunction accepts a github.com URL with any path.
15. §4.13's ledger says `circt-translate --import-verilog` is "absent from the slang-less build". Confirmed
    (`bassert_g/bin/circt-translate --help | grep -c import-verilog` -> 0; SDK -> 1), but `bslang/bin`
    contains `circt-verilog` and `circt-translate` and no `firtool`/`circt-reduce`/`arcilator`, so the
    branch-(a) six-target build remains entirely unmeasured. §15 item 2 says so; §4.13 does not.
16. §6.5's `interesting.sh` is listed inside `probe_<probe_id>/` while §10.2 writes it "per candidate";
    candidates and probes are 1:1 (`candidate.probe_id ... UNIQUE`) so this happens to work, but the
    two sections use different nouns for the same directory.
17. §7.1's `parse_json_footer` docstring says "the **LAST** fenced json block ... wins" and the shown
    `_JSON_BLOCK` regex is non-greedy with no body given, so the last-wins behaviour is asserted and
    not specified.

---

## The single question the LLD most needs answered before code

**Where does a worker node get CIRCT history from?**

Five separate KILLs collapse into it. A1's mining, A2's pin walk, B6b's two commit scans, A3's `$diff`
and A4's seed test files all require a repository containing the last 24 months of `main`, on a node
whose only tree is a `--depth 1` checkout of one commit and whose only bind mount is the artefact
root. Answering it fixes K5 and K6, settles §3.2's resource tags for three components, decides whether
§12.1 gains a mount or the head gains three nodes, and determines whether `SeedRecord` must grow a
`diff` field (a MAJOR contract bump, §2.2) or the worker must be able to run `git show`.

Everything else on this list is local. This one changes the component placement, the cluster file, the
contract version and the seam.

---

## The ten riskiest assumptions, with the cheapest check for each

| # | Assumption | Cheapest check |
|---|---|---|
| 1 | A CIRCT assertion matches `_ASSERT_GLIBC`. | `c++` a three-line file with a namespaced member function, run it, match the line. Two minutes. (Done: it does not — K1.) |
| 2 | `llvm-symbolizer --obj=<tool>` resolves the addresses `_FRAME` captures. | Crash `bassert_g/bin/circt-opt` on a deeply nested `.mlir`, pipe the `#N` addresses into the §4.9 command. (Done: nothing resolves — K2.) |
| 3 | The top-5 frame tuple identifies a bug. | Crash the same input twice, print the top five normalised names, compare. (Done: they differ — K3.) |
| 4 | `git fetch --depth 1 origin <sha>` leaves the `firtool-*` tag reachable. | `git init` a scratch repo, fetch by SHA from the local clone, `git ls-tree <tag> llvm`. (Done: fatal — K4.) |
| 5 | A `circt:1` worker can run A1's five git commands. | `git -C /workspace/circt for-each-ref refs/tags/firtool-*` inside a `chia-circt` container. One command, no build. |
| 6 | The chain's reset leaves `.circtissues` alone. | `git check-ignore -v .circtissues` in the CIRCT clone, then `git clean -fdn` in a dirty tree. (Done: not ignored, would be removed — K9.) |
| 7 | `limit_hit` is observable. | `prlimit --cpu=1 -- <spin>` and `prlimit --as=<small> -- <alloc>`, read the return codes. (Done: `-9` and `1`, no limit identity — K8.) |
| 8 | A `chia job submit` job inherits the submitter's environment. | Submit a one-line job that prints `os.environ.get("BUGLOOP_ARTEFACTS")`. CHIA's own wrapper comment already says it does not (K13). |
| 9 | `ninja` after `git reset --hard` reproduces the published binaries byte for byte. | On one worker: hash the six binaries, apply and revert a one-line diff, rebuild, re-hash. One incremental build. |
| 10 | `circt-reduce` gets more than one or two interestingness calls inside `reduction_wall_seconds`. | Time one `circt-opt` run on a realistic seed input, divide 60 by it. The 56-call measurement above is the shape of the answer. |

Two further items are already marked `[UNVERIFIED]` by §15 and are not repeated here: the differential
harness (A-08, A-19) and the slang build (A-03). Both are correctly disclosed.

---

## Counts

| Severity | Count |
|---|---|
| KILL | 16 |
| WOUND | 28 |
| NIT | 17 |
| **Total** | **61** |

Findings by section, KILL and WOUND only:

| Section | Findings |
|---|---|
| §1 repository layout | W6, W19 |
| §2 contract | K10, K11, W8, W9, W24 |
| §3.2 to §3.5 placement and generators | K5, K6, W4, W7, W10, W11 |
| §3.6 build and oracle | K1, K2, K8, K16 |
| §3.7 dedup and triage | K3, K7, W22, W23 |
| §3.8 repair adapter | K9, K14, W1, W2, W3, W21 |
| §3.9 gate | K12, W15, W17 |
| §4 tool invocations | K4, W17, W18 |
| §6 database and artefacts | W26, W27 |
| §9 budget | W12, W13 |
| §10 interestingness and ddmin | K15, W13, W14 |
| §12 cluster | W20, W28 |
| §13 entry points | K13, W25 |
| §14 traceability | W5 |

Nothing in §5 (binary resolution) or §8 (mutator set format) reached KILL or WOUND; both are among the
strongest parts of the document, as is §4's flag verification, which I re-ran and could not fault.
