# W-19a: the single-machine cluster, brought up and proved without the driver

**Run date** 2026-09-14 (IST), on `cachyos-x8664`. **Scope** `T-U-cluster-01`, the tier-3
bring-up of `circt_bug_loop/cluster_single.yaml` (03-LLD.md §12.1), with `chia up`,
`chia down`, the five containers and four trivial CHIA nodes. **The driver is not in
this run**: `bug_loop.py` is being fixed in parallel and nothing here imports it.

**No model call was made.** `BUGLOOP_ALLOW_LIVE_MODEL` was never set, in this shell or in
any container. `GEMINI_API_KEY` was exported as the literal string
`placeholder-not-a-key`; `~/.config/bugloop/gemini.env` was never read. Every check on the
credential below is a **count or a boolean** — no value is printed anywhere in this file
or in the raw logs.

## 0. Verdict

The cluster comes up, all five workers join, the three resources are exactly `llm: 2`,
`circt: 2`, `repair: 1`, four CHIA nodes dispatch to the right worker types, the six tool
binaries hash to the manifest (FR-03.16), and the cluster tears down clean.

It did **not** come up as the file stood. Four defects had to be fixed first, three in the
YAML and one in the head environment, and each would have stopped the campaign on its
first `chia up`. Two further conditions of this host — the head Python and the machine's
memory — are recorded in §7 as owed decisions rather than fixed here.

| | |
|---|---|
| `chia up` wall (successful, attempt 2) | **36 s** |
| `chia down` wall | **177 s** |
| `chia up` wall (attempt 1, failed) | 25 s to first failure |
| `chia down` after the failed attempt | 129 s |

## 1. The operator's shell

```
source ~/.cache/chia-venv-py31019/bin/activate     # NOT ~/.cache/chia-venv; see §3.4
source ~/.config/bugloop/cluster.env
export BUGLOOP_HEAD_ENV=$HOME/.cache/chia-venv-py31019/bin/activate
export SSH_AUTH_SOCK=/run/user/1000/w19a-ssh-agent.sock   # see §3.3
export GEMINI_API_KEY=placeholder-not-a-key
unset BUGLOOP_ALLOW_LIVE_MODEL
cd ~/Projects/CHIA_Hackathon_2k26
```

`cluster.env` supplies `CHIA_HEAD=cachyos-x8664`, `BUGLOOP_ARTEFACTS=/home/adi/bugloop-artefacts`,
`BUGLOOP_IMAGE_TAG=eade0de61bc5`.

## 2. Pre-flight

CHIA has no `--version`; the checkout is the version.

| Check | Result |
|---|---|
| `chia` CLI | `~/.cache/chia-venv-py31019/bin/chia`, subcommands `up down viz firesim-* status list job ray viz-profile` |
| chia source revision | `16c35e92aaaf9511c6453bf94cd5cf589698f4e3` (2026-09-04), the revision 03-LLD.md §1.2 pins |
| Ray / Python (head) | 2.54.0 / 3.10.19 |
| `load_config('circt_bug_loop/cluster_single.yaml')` | returns a `ClusterConfig`; three node types, `head_ip=cachyos-x8664`, `ssh_user=adi`, the three head commands expanded to the activate script |
| ports 6379, 8265 | both free |
| `docker ps -a` for `circt_bug_loop*` | none |
| `ghcr.io/ucb-bar/chia:latest` | present locally |
| `ghcr.io/ucb-bar/chia-circt-assert:eade0de61bc5` | **absent**, and `docker pull` answers `error from registry: denied` |
| `chia-circt-assert:eade0de61bc5` | present locally (the W-04 build) |
| disk | `/` 90% used, 9.0 G free; `/home` 39%, 460 G free |
| ssh agent | **none running**; `SSH_AUTH_SOCK` unset |

Two of those rows are the first two defects, found before the first `chia up` rather than
by it.

## 3. The four fixes

### 3.1 The assertions image is local and cannot be pulled (YAML, `bugloop_circt` and `bugloop_repair`)

§12.1 wrote `image: "ghcr.io/ucb-bar/chia-circt-assert:${BUGLOOP_IMAGE_TAG}"` with
`pull_before_run: True`. W-04 built that image locally and never published it, so:

- `docker pull ghcr.io/ucb-bar/chia-circt-assert:eade0de61bc5` → `error from registry: denied`,
  and `DockerManager` runs the pull through `SSHClient.run` with `check=True`
  (`chia:chia/cluster/docker.py:34-37`), so `chia up` raises before the first container; and
- CHIA appends `--pull=never` to every `docker run` (`chia:chia/cluster/docker.py:56-61`),
  so even with the pull skipped the registry-qualified name cannot resolve on this head.

**Fix**: both circt-side types now name the image the way W-04 built it and every artefact
of this project records it — `chia-circt-assert:${BUGLOOP_IMAGE_TAG}` — and set
`pull_before_run: False`. Only the *location* changes. The tag still comes from
`${BUGLOOP_IMAGE_TAG}`, and the driver's own check is a suffix match against the manifest's
tag (`bug_loop.py:2058`, `image_spec.image_tag.endswith(args.image_tag)`), which both
spellings satisfy. `bugloop_llm` keeps `ghcr.io/ucb-bar/chia:latest` and keeps its pull:
that image is published.

### 3.2 `/etc/passwd` is not writable in the llm image (YAML, `bugloop_llm`)

Attempt 1, both llm workers:

```
[chia] ERROR [cachyos-x8664] stderr: bash: line 2: /etc/passwd: Permission denied
[chia] ERROR Worker cachyos-x8664 (bugloop_llm-0) FAILED
```

The first `run_setup_commands` line appends a passwd entry for the numeric uid, and CHIA
runs the setup block under `set -e`, so a failing first line fails the worker. Measured:

| image | `/etc/passwd` | uid 1000 is |
|---|---|---|
| `ghcr.io/ucb-bar/chia:latest` | `-rw-r--r-- root root` | `ray` — already has the entry |
| `chia-circt-assert:eade0de61bc5` | `-rw-rw-rw- root root` | `ubuntu` |

So the line can only ever have worked on the circt side. **Fix**: `|| true` on the
`bugloop_llm` line only; the other two types keep the bare form. Nothing is lost — uid 1000
in that image is already `ray` and already has the entry the line would add. The warning
still appears in the `chia up` log on both llm workers, now as an INFO line, and both
workers reach `ready`.

### 3.3 `-v $SSH_AUTH_SOCK:/ssh-agent` needs a live agent (operator, not the YAML)

The option is written unbraced on purpose: `_expand_env_vars` substitutes only `${VAR}`
and leaves `$VAR` alone (`chia:chia/cluster/config.py:300-304`), so it expands in the
remote `bash --login`. CHIA opens that shell with `ssh -A`
(`chia:chia/cluster/ssh.py:36-38`), so a **local** agent is forwarded and the remote value
is a real socket. Verified directly:

```
$ ssh -A ... localhost 'bash --login -c "echo SOCK=[\$SSH_AUTH_SOCK]"'      # no local agent
SOCK=[]
$ SSH_AUTH_SOCK=… ssh -A ... localhost 'bash --login -c "echo SOCK=[\$SSH_AUTH_SOCK]"'
SOCK=[/home/adi/.ssh/agent/s.33NJfY7haf.sshd.X0CykIYUSu]
```

With no agent the option becomes `-v :/ssh-agent` and `docker run` rejects it. **Fix**: an
`ssh-agent` was started on the head (`ssh-agent -a /run/user/1000/w19a-ssh-agent.sock`,
no keys added) and `SSH_AUTH_SOCK` exported before `chia up`. No YAML change; the
requirement is now stated in the file's header so the operator cannot miss it.

### 3.4 The head Python does not match the images' (head environment, not the YAML)

Attempt 1, all three worker types, at `ray start --address=...`:

```
RuntimeError: Version mismatch: The cluster was started with:
    Ray: 2.54.0
    Python: 3.10.21
This process on node 10.202.182.66 was started with:
    Ray: 2.54.0
    Python: 3.10.19
```

`~/.cache/chia-venv`, which `cluster.env` and `bug_loop_submit.sh` both name as the head
environment, is **Python 3.10.21**. Both images ship **3.10.19** — CHIA's own quickstart
says so (`conda create -n chia_env python=3.10.19`, "matching the Python in the Docker
images"). Ray compares at patch level by default
(`ray/_private/utils.py:1301-1316`, `RAY_DEFAULT_PYTHON_VERSION_MATCH_LEVEL`, default
`"patch"`), so **no worker could ever have joined this cluster**. The head came up, the
five containers started, and every one of them failed at the join.

**Fix**: a head environment at the images' Python was built for this run —

```
uv python install 3.10.19
uv venv --python 3.10.19 ~/.cache/chia-venv-py31019
uv pip install --python ~/.cache/chia-venv-py31019/bin/python -e ~/.cache/chia-src
```

— giving Python 3.10.19, Ray 2.54.0 and chia editable, and `BUGLOOP_HEAD_ENV` was pointed
at its activate script. `~/.cache/chia-venv` was **not modified**: `bug_loop.py` is being
worked on against it in parallel. Setting `RAY_DEFAULT_PYTHON_VERSION_MATCH_LEVEL=minor`
would demote the error to a warning and was deliberately **not** used — it would prove a
cluster that Ray itself does not consider consistent.

This is not a YAML defect and it is not fixed in the repository. §7.1 records what is
owed.

### 3.5 What the fixes did not change

`test_cluster_yaml.py` — the eight `T-U-cluster-*` tier-0 tests — **passes unchanged**
after all three YAML edits. No test was edited. In particular `T-U-cluster-08`'s assertion
that `bugloop_llm`'s image is `ghcr.io/ucb-bar/chia:latest` still holds (only the circt-side
images moved), and `T-U-cluster-05`'s count of two llm setup lines still holds (`|| true`
does not add a line).

## 4. Bring-up

Attempt 2, with §3.1–§3.4 applied: **rc=0 in 36 s**, no `[chia] ERROR` and no
`[chia] WARNING` line, `Head node ready` plus five `Worker … ready`.

```
circt_bug_loop_circt_adi-0    chia-circt-assert:eade0de61bc5
circt_bug_loop_circt_adi-1    chia-circt-assert:eade0de61bc5
circt_bug_loop_llm_adi-0      ghcr.io/ucb-bar/chia:latest
circt_bug_loop_llm_adi-1      ghcr.io/ucb-bar/chia:latest
circt_bug_loop_repair_adi-0   chia-circt-assert:eade0de61bc5
```

`chia status` / `ray status`, six active nodes (the head plus the five workers), no pending
nodes and no recent failures:

```
 0.0/80.0 CPU        0.0/2.0 circt      0.0/2.0 llm       0.0/1.0 repair
 0.0/1.0 GPU         0B/57.62GiB memory                   0B/24.69GiB object_store_memory
```

`llm: 2`, `circt: 2`, `repair: 1` — exactly §12.1's counts, and `llm` totals **2** and not
4, which is the `llm: 1`-per-container decision the file's header defends.

Dashboard on 8265:

```
$ curl -s localhost:8265/api/version
{"version": "4", "ray_version": "2.54.0", "ray_commit": "48bd1f8f…",
 "session_name": "session_2026-09-14_12-11-15_383888_1081806"}
$ curl -s -o /dev/null -w '%{http_code}' localhost:8265/     → 200
```

## 5. Inside the containers

`docker exec` into each of the five. Every credential row is a **count**.

### `bugloop_circt` (both containers, identical results)

| Check | `…circt_adi-0` | `…circt_adi-1` |
|---|---|---|
| container user | `uid=1000(ubuntu) gid=1000(ubuntu)` | same |
| `circt-opt --version` | `LLVM version 24.0.0git` / `Optimized build.` / **`CIRCT eade0de`** | same |
| artefact root `/home/adi/bugloop-artefacts` | mounted, owned `ubuntu:ubuntu`, `touch` then `rm` **OK** | same |
| `prlimit --version` | `prlimit from util-linux 2.39.3` | same |
| `verilator --version` | `Verilator 5.020 2024-01-01 rev (Debian 5.020-1)` | same |
| `lit --version` | `lit 23.1.1` | same |
| `env \| grep -c GEMINI` | **0** | **0** |
| `env \| grep -c BUGLOOP_ALLOW_LIVE_MODEL` | 0 | 0 |

The artefact mount is the same host directory at the same absolute path in every container
(FR-17.9), and `--user $(id -u):$(id -g)` is what makes it writable from both sides: the
probe file was created as uid 1000 and removed again.

### `bugloop_llm` and `bugloop_repair`

| Check | `…llm_adi-0` | `…llm_adi-1` | `…repair_adi-0` |
|---|---|---|---|
| container user | `uid=1000(ray)` | `uid=1000(ray)` | `uid=1000(ubuntu)` |
| `env \| grep -c GEMINI_API_KEY` | **1** | **1** | **1** |
| key non-empty (boolean) | true | true | true |
| `env \| grep -c BUGLOOP_ALLOW_LIVE_MODEL` | 1 | 1 | 1 |
| that variable's value | **empty** | **empty** | **empty** |
| `circt-opt --version` | — | — | `CIRCT eade0de` |
| artefact root writable | — | — | `touch`+`rm` OK |

So the credential reaches exactly the three containers §11.2 says it should and none of
the two it should not. The last row is a finding, not a pass — see §7.2.

## 6. Four trivial CHIA nodes

`ray.init(address="auto")`, three `@ChiaFunction`s, `probe` dispatched twice.

| dispatch | resource | node id | result |
|---|---|---|---|
| `probe()` #1 | `{"circt": 1}` | `852d0a3287f7` | `CIRCT eade0de` |
| `probe()` #2 | `{"circt": 1}` | `b2d3b6e57603` | `CIRCT eade0de` |
| `repair_probe()` | `{"repair": 1}` | `4fe18f727de6` | `CIRCT eade0de` |
| `llm_probe()` | `{"llm": 1}` | `55087abaf40a` | `gemini_key_set=True` |

**The two circt probes landed on two different workers** — `llm: 1`/`circt: 1` per
container means two circt tasks cannot share one, which is what makes
`apparatus_concurrency` equal to the `bugloop_circt` count. Every node reports
`socket.gethostname()` as `cachyos-x8664`: CHIA runs every container with `--net=host`, so
the hostname is the machine's and the Ray node id is the only thing that distinguishes a
worker. The six alive nodes carried `{"llm":1}`, `{"llm":1}`, `{"circt":1}`, `{"circt":1}`,
`{"repair":1}` and `{}` (the head).

### 6.1 Hash manifest, FR-03.16, in the running cluster

`sha256sum` of the six tool binaries inside `circt_bug_loop_circt_adi-0`, against
`analysis/measurements/raw/image-manifest.json`:

| binary | |
|---|---|
| `circt-opt`, `firtool`, `circt-translate`, `arcilator`, `circt-reduce`, `circt-verilog` | **all six MATCH** |

The manifest was computed on 2026-09-13 from a freshly started container; the binaries a
running `bugloop_circt` worker would actually invoke are byte-identical to it.

## 7. What this run found and did not fix

### 7.1 The head environment is Python 3.10.21 and must be 3.10.19 [owed]

§3.4. `~/.config/bugloop/cluster.env` and `bug_loop_submit.sh` both point at
`~/.cache/chia-venv`, which cannot run this cluster. Two further mismatches in the same
place: `cluster.env` sets `BUGLOOP_HEAD_ENV=/home/adi/.cache/chia-venv`, the venv
**directory**, where §12.1 and `bug_loop_submit.sh` both want the **activate script** —
`source` of a directory fails, and the wrapper's
`PYBIN="$(dirname "$BUGLOOP_HEAD_ENV")/python"` resolves to `/home/adi/.cache/python`. Both
were overridden in this shell. The project has to decide whether `~/.cache/chia-venv` is
rebuilt at 3.10.19 or `~/.cache/chia-venv-py31019` becomes the head environment; either
way `cluster.env` and the wrapper's default need the activate-script path.

### 7.2 `${BUGLOOP_ALLOW_LIVE_MODEL}` reaches the container **empty**, not as the literal

§12.1's header and `T-U-cluster-08` both reason that CHIA's loader leaves an unset
`${VAR}` as seven literal characters, and that `build_llm` refusing a value beginning `${`
is therefore a live defence. It is not, on this path. The loader does leave the literal —
but the literal then travels into the `docker run` command line and is expanded a *second*
time by the remote `bash --login`, where the variable is also unset, so docker receives
`-e BUGLOOP_ALLOW_LIVE_MODEL=` and the container gets the name with an **empty value**.
Measured in all three keyed containers. The interlock still holds (empty is falsy, and the
count in the circt containers is 0), and the same double expansion applies to
`${GEMINI_API_KEY}`: an operator who forgets the key gets an empty one, not a `${`-prefixed
one. Owed to 03-LLD.md §12.1's header, §11.2, and `T-U-cluster-08`'s docstring.

### 7.3 `--net=host` puts six raylets in one network namespace

Two Ray worker processes died during the dispatches of §6:

```
Failed to start the grpc server. The specified port is 10024 … Address already in use
Failed to start the grpc server. The specified port is 10023 … Address already in use
```

Every container runs `--net=host` (CHIA hard-codes it, `chia:chia/cluster/docker.py:57`)
and every raylet takes the same default worker-port range, `--min_worker_port=10002
--max_worker_port=19999`. The four dispatches all succeeded and `ray status` afterwards
showed six active nodes and no recent failures, so nothing was lost here — but these were
prestarted idle workers colliding at a concurrency of one task per type. Under the
campaign's load the same collision reaches a *task* worker, and the loop's nodes are
`max_retries=0`. `worker_start_ray_commands` is a single cluster-wide list in this schema,
so disjoint per-type ranges are not expressible in the YAML as it stands. Recorded for
W-19b/W-20 rather than fixed.

### 7.4 The container limits exceed the machine

| | |
|---|---|
| host | 20 cores, **15.23 GiB RAM**, 15.23 GiB swap |
| YAML memory limits | `bugloop_circt` 24 g × 2 + `bugloop_repair` 32 g = **80 GiB** |
| YAML cpu limits | 6 + 6 + 8 = 20, plus two unbounded llm containers |
| Ray's advertised totals | **80 CPU**, 57.62 GiB memory, 24.69 GiB object store |

NFR-05's outer memory guards never bind on this host — a limit of 24 g on a 15 GiB machine
cannot stop anything — and Ray's scheduler believes it has 80 CPUs and 57.62 GiB, both
about four times what exists, because it sums per-container limits with no view of the
host. The five containers also request `--shm-size=10.24gb` each for the plasma stores.
Either the campaign runs on a machine that matches §12.1's numbers, or §12.1's numbers come
down to this one; the equal-wall-clock claim of FR-14.5 is a claim about *this* cluster at
*this* concurrency, so the decision belongs to the architect and not here.

### 7.5 Smaller observations

- `ray status` warns `Found multiple active Ray instances: {'cachyos-x8664:6379',
  '10.202.182.66:6379'}` and connects to the IP. It is one cluster reachable under two
  names — the head starts Ray on the hostname and the raylets register the resolved IP.
  Harmless here; `ray.init(address="auto")` picked the same GCS and every dispatch landed.
- `chia down` (177 s) takes **five times** as long as `chia up` (36 s). The teardown does a
  scoped `ray stop` inside each container before stopping it, one SSH session at a time.
- Teardown is clean: five workers torn down, zero `circt_bug_loop*` containers left, 6379
  and 8265 free, no Ray process surviving.
- `chia` has no `--version`; the checkout revision is the only version there is.

## 8. Raw logs

Under the run's scratch directory, not committed: `chia up` attempt 1 and 2, `chia down`
×2, `chia status`/`ray status`, the five containers' checks, the four dispatches, and the
six live hashes. The two commands worth repeating are in §3 and §6.1.
