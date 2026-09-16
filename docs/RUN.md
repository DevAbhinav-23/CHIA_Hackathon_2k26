# Running this repository on a new machine

Three levels, each a superset of the one before.

* **A. Tests.** A fresh clone, a Python 3.10 venv and one CHIA checkout. No
  CIRCT binary, no clone of CIRCT, no Docker, no network at run time, no model
  call, no cost. This is what `scripts/setup.sh` gets you, and it is enough to
  read and change the loop.
* **B. Inspecting a past run.** Adds the team's `loop.db`, and for the corpus
  and the pre-flight checks a blobless `llvm/circt` clone and a read-only GitHub
  token.
* **C. A live campaign.** Adds Docker and a ~1.9 GB assertions-on CIRCT image,
  `ssh localhost` with an agent, a Ray cluster, and a Gemini key. It spends
  money.

Everything below was run on Linux with Python 3.10.19. Nothing here needs root.

---

## A. Tests only

```sh
git clone https://github.com/DevAbhinav-23/CHIA_Hackathon_2k26
cd CHIA_Hackathon_2k26
./scripts/setup.sh
```

`scripts/setup.sh` is idempotent — re-running it is a no-op once everything is
in place — and it does exactly this:

1. Finds a Python >= 3.10 (`BUGLOOP_PYTHON=/path/to/python` overrides the
   search) and creates `.venv`.
2. Clones `https://github.com/ucb-bar/chia` into **`~/.cache/chia-src`** and
   checks out `16c35e92`. The path is not configurable: `test_upstream_patches.py`
   and `test_layout.py` read it literally, and 17 `t0` tests skip without it.
3. Applies `upstream/vertex-usage.patch` to that checkout's **working tree** and
   never commits it. `test_layout.py` clones `~/.cache/chia-src` and asserts the
   *committed* tree is still upstream's, so a committed patch would fail it.
4. `pip install -r requirements.txt`, then `pip install -e ~/.cache/chia-src --no-deps`.
   The requirements file is the pinned closure from the machine the README's
   numbers were measured on; installing CHIA with `--no-deps` afterwards keeps
   those pins.

Then:

```sh
.venv/bin/python -m pytest circt_bug_loop/tests -q -m t0
.venv/bin/python -m pytest circt_bug_loop/tests -q -m "not t2 and not t3"
```

Measured on a fresh clone, 2026-09-16:

| selection | after `setup.sh` | with the CIRCT clone and SDK too |
|---|---|---|
| `-m t0` | 686 passed, 1 skipped | same |
| `-m "not t2 and not t3"` | 689 passed, 32 skipped | 720 passed, 1 skipped |

The one skip that never goes away without a token is
`test_triage_task.py::…` — "no GITHUB_TOKEN"; see level B. Without
`~/.cache/chia-src`, `-m t0` drops to 669 passed and 18 skipped, which is the
signal that step 2 did not happen.

What the markers cost (`pytest.ini` defines them):

| marker | needs |
|---|---|
| `t0` | this repository and Python 3.10, plus `~/.cache/chia-src` for the 17 patch tests |
| `t1` | a blobless `llvm/circt` clone, or the prebuilt CIRCT SDK / assertions build |
| `t2` | the assertions-on image and a Docker daemon |
| `t3` | the single-machine cluster |

`t1` tests that cannot find their resource **skip**; they do not fail. Point them
at what you have with `BUGLOOP_CORPUS_CLONE` (a clone) and `BUGLOOP_BIN_DIR` (a
directory holding `circt-opt`), otherwise they look under `~/.cache/circt` and
`~/.cache/chia-pin-smoke/…`.

### Does the installed CHIA need the vertex patch?

For the tests, **no**: the whole suite passes against pristine `16c35e92`,
because the tests apply `upstream/vertex-usage.patch` to a throwaway copy
themselves. For a **live** run, **yes**: `circt_bug_loop/llm.py`'s `build_llm`
passes `turn_budget_usd`, `final_tool_names` and `final_tool_iterations` to
`VertexGeminiLLM`, and upstream's `__init__` accepts none of them —

```
TypeError: VertexGeminiLLM.__init__() got an unexpected keyword argument 'turn_budget_usd'
```

— so `setup.sh` applies it unconditionally. (The driver separately patches the
package it *ships to workers*: `bug_loop.py` re-applies both patches to the
staged copy unless the fields are already there, and pre-flight check 14
refuses the run if they are not.)

---

## B. Inspecting a past run

### `--print-config` — needs nothing

```sh
.venv/bin/python -m circt_bug_loop.bug_loop --mode discovery --print-config
```

Prints every resolved path, including which `chia` was imported. Useful as a
first check that level A landed.

### `--render <run>` — needs `loop.db`

```sh
.venv/bin/python -m circt_bug_loop.bug_loop --mode discovery --render 460b7b48
```

The results database is **not in the repository** (see below). Put the team's
copy at `circt_bug_loop/loop.db` first; without it the command creates an empty
database and raises `LookupError: no run row for …`. `circt_bug_loop/approve.py`
(`--db <absolute path>`) reads the same file.

### `--dry-run` — needs a clone, an artefact root, an image tag **and a running cluster**

```sh
git clone --filter=blob:none https://github.com/llvm/circt ~/.cache/circt
mkdir -p ~/bugloop-artefacts
.venv/bin/python -m circt_bug_loop.bug_loop --mode discovery --dry-run \
  --clone ~/.cache/circt --artefact-root ~/bugloop-artefacts --image-tag <tag>
```

The clone must carry history past the corpus head
`d7e94049bde30f2cf95f81bf7cc4b6cf26dd18a2`; the corpus mining reads it, and
`--clone` defaults to `~/.cache/circt`. A dry run never builds an image and
never calls a model, but it *does* run the pre-flight checks through Ray, so it
stops at

```
ConnectionError: Could not find any running Ray instance.
```

until level C's `chia up` has been done. In other words `--dry-run` is a level-C
rehearsal, not a level-B one.

### The GitHub token

`--refresh-mirror` builds the issue mirror inside `loop.db` from the CIRCT
tracker, and one `t0` test exercises the same client. Both read a **read-only,
no-scope** token from a file, by default
`~/.config/circt_bug_loop/github_token`, which must be mode 600:

```sh
install -m 600 /dev/null ~/.config/circt_bug_loop/github_token
printf '%s' "<token>" > ~/.config/circt_bug_loop/github_token
```

Never export it; the driver reads the file and nothing forwards it into a job's
environment.

---

## C. A live campaign

Do not start here. Every step below costs time or money, and the loop is
deliberately hard to switch on: no stage can build a model client unless
`BUGLOOP_ALLOW_LIVE_MODEL=1` is set for that run.

**1. The model key.** Copy `config/gemini.env.example` to
`~/.config/bugloop/gemini.env`, `chmod 600`, put your own key on the
`GEMINI_API_KEY` line. Nothing else in this repository is affected by it, and
no key ever goes in the repository. Load it only into the shell that runs
`chia up`:

```sh
set -a; source ~/.config/bugloop/gemini.env; set +a
export BUGLOOP_ALLOW_LIVE_MODEL=1
```

**2. The operator environment.** Copy `config/cluster.env.example` to
`~/.config/bugloop/cluster.env`, fill it in, and source it the same way. It
carries `CHIA_HEAD`, `BUGLOOP_ARTEFACTS`, `BUGLOOP_IMAGE_TAG`,
`BUGLOOP_HEAD_ENV` and `SSH_AUTH_SOCK` — no secrets. `BUGLOOP_HEAD_ENV` must
point at the `activate` of the very venv `ray start --head` runs from, or the
job imports a CHIA the cluster does not have.

**3. Docker and the images.**

* `docker pull ghcr.io/ucb-bar/chia:latest` — the CHIA worker image.
* The assertions-on CIRCT image, built from
  `upstream/dockerfiles/ChiaCirctAssertDockerfile` by `bug_loop.build_image`,
  which issues

  ```
  docker build -f <dockerfile> -t chia-circt-assert:<tag> \
    --build-arg CIRCT_SHA=… --build-arg CIRCT_VER=… \
    --build-arg TOOL_TARGETS='circt-opt firtool circt-translate arcilator circt-reduce circt-verilog' \
    --build-arg CXX_FLAGS_RELEASE='-O3 -UNDEBUG -gline-tables-only' \
    --build-arg SLANG=ON --build-arg BASE_IMAGE=ghcr.io/ucb-bar/chia-circt:latest <context>
  ```

  The recorded build of the campaign image is
  `analysis/measurements/raw/image-manifest.json` (tag `eade0de61bc5`, 1.9 GB,
  23 layers). **It compiles CIRCT: budget about an hour and a lot of disk.**
* A child image `chia-circt-assert:<tag>-u1000`, which is one layer:

  ```
  FROM chia-circt-assert:<tag>
  RUN chown -R 1000:1000 /workspace/circt
  ```

  The repair worker reconfigures and rebuilds `/workspace/circt` and CMake needs
  to own the tree; only the repair node type uses this tag.

**4. ssh to yourself.** CHIA's cluster layer uses ssh and rsync even with one
machine. `ssh localhost` must succeed with a key, sshd must be running, and an
agent must be live at `$SSH_AUTH_SOCK`:

```sh
eval $(ssh-agent -a /run/user/$(id -u)/bugloop-ssh-agent.sock)
ssh-add ~/.ssh/id_ed25519
ssh localhost true
```

**5. Up.**

```sh
chia up -y circt_bug_loop/cluster_single.yaml
```

**6. Submit.** Run the driver as a job, never directly — a job's stdout is the
only one `chia job logs` can retrieve:

```sh
circt_bug_loop/bug_loop_submit.sh --mode discovery --arm seeded \
  --clone ~/.cache/circt --shard 1/1
```

The wrapper requires `BUGLOOP_ARTEFACTS` and `BUGLOOP_IMAGE_TAG` to be set and
forwards exactly those two (plus `GOOGLE_CLOUD_PROJECT` if set) into the job's
runtime environment. It forwards neither `GEMINI_API_KEY` nor
`BUGLOOP_ALLOW_LIVE_MODEL`: the key reaches the llm workers through `chia up`'s
`docker run -e`, and the interlock is a property of the cluster, not of a job.
Set `NO_WAIT=1` to return immediately.

**7. Watch and stop.**

```sh
chia job logs <id> --follow      # the dashboard is at http://localhost:8265
chia down -y circt_bug_loop/cluster_single.yaml
```

**8. Filing is a person's act.** Nothing is filed by the loop. See the
`approve` command in the README.

---

## What is not in the repository, and why

| Missing | Why | How to get it |
|---|---|---|
| `circt_bug_loop/loop.db` | 465 MB of results and the issue mirror; gitignored | Ask the team for a copy; needed for `--render` and `approve` |
| `~/.cache/chia-src` (CHIA at `16c35e92`) | Upstream's own repository, plus one uncommitted patch of ours | `scripts/setup.sh` |
| A `llvm/circt` clone | Tens of GB even blobless-filtered | `git clone --filter=blob:none https://github.com/llvm/circt ~/.cache/circt` |
| `chia-circt-assert:<tag>` and its `-u1000` child | ~1.9 GB and ~2.4 GB image layers | Build them: level C step 3 |
| The prebuilt CIRCT SDK / assertions build | Build output, gigabytes | Only `t1` tests want it; they skip without it |
| Artefact roots (`artefacts/`, `~/bugloop-artefacts`) | Per-run output, gigabytes, gitignored | Created empty by you; a past run's artefacts come with `loop.db` from the team |
| `~/.config/bugloop/gemini.env` | The model credential | Your own key, from `config/gemini.env.example` |
| `~/.config/circt_bug_loop/github_token` | A read-only token | Your own, mode 600 |
