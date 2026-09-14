"""Both cluster YAMLs (`03-LLD.md` §12), the `T-U-cluster-*` tests of §1.24.

`T-U-cluster-01` is the tier-3 bring-up and lives with the cluster suite; every
test here is tier 0 and reads the two committed files, once as YAML and once
through `chia.cluster.config.load_config`, which is the loader `chia up` uses.

**No test here sets `BUGLOOP_ALLOW_LIVE_MODEL`.** `T-U-cluster-07` as written
asks for it "set to a dummy"; `T-U-layout-08` as W-16 rewrote it forbids any
test outside `tests/system/` from putting that name into the process
environment, and the two cannot both be obeyed. Leaving it unset is also the
stronger check: it is exactly the second half of `T-U-cluster-08`, the loader
leaving `${VAR}` as literal text, and the file loads either way (errata row 12).
"""
import os
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import bug_loop

pytestmark = pytest.mark.t0

FLOW = Path(bug_loop.FLOW_DIR)
SINGLE = FLOW / "cluster_single.yaml"
GCP = FLOW / "cluster_gcp.yaml"

#: A synthetic key of the `AQ.` shape `T-N-nfr06-02`'s pattern is written
#: against. It authenticates against nothing and is never a real credential.
SYNTHETIC_KEY = "AQ." + "0123456789abcdef0123456789abcdef"

#: §12.1's three worker types, their resource names and their container counts.
TYPES = {"bugloop_llm": ("llm", 2), "bugloop_circt": ("circt", 2),
         "bugloop_repair": ("repair", 1)}


def raw(path: Path) -> dict:
    """The file as YAML, before CHIA expands anything."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture
def loader_env(monkeypatch, tmp_path):
    """The operator's shell at `chia up`, minus the interlock (see the module docstring).

    One literal name per line rather than a loop, so `T-U-layout-08`'s `ast`
    walk can read every variable this file sets without resolving a loop.
    """
    monkeypatch.setenv("CHIA_HEAD", "127.0.0.1")
    monkeypatch.setenv("BUGLOOP_ARTEFACTS", str(tmp_path))
    monkeypatch.setenv("BUGLOOP_IMAGE_TAG", "eade0de61bc5")
    monkeypatch.setenv("USER", "tester")
    monkeypatch.setenv("GEMINI_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("BUGLOOP_GCP_HEAD_IP", "10.0.0.2")
    monkeypatch.setenv("BUGLOOP_GCP_PROJECT", "bugloop-project")
    monkeypatch.delenv(bug_loop.LIVE_MODEL_ENV, raising=False)
    return SYNTHETIC_KEY


def test_T_U_cluster_02():
    """T-U-cluster-02 (FR-12.11): three worker types, three resource names, 2/2/1.

    `llm: 1` per container and not `llm: 2`, so the concurrent-prompt cap is the
    container count, which is what `RunManifest.llm_concurrency` records.
    Fixture: none. Tier 0.
    """
    types = raw(SINGLE)["available_node_types"]
    assert set(types) == set(TYPES)
    for name, (resource, count) in TYPES.items():
        assert types[name]["resources"] == {resource: 1}, name
        assert types[name]["max_workers"] == count, name
    assert raw(SINGLE)["max_workers"] == sum(c for _, c in TYPES.values())


def test_T_U_cluster_03():
    """T-U-cluster-03 (FR-14.5): the cluster is fixed-size on every type.

    `min_workers == max_workers` is what makes `apparatus_concurrency` a
    constant of the campaign rather than a number the autoscaler chooses, and
    both arms run from this one file at this one concurrency.
    Fixture: none. Tier 0.
    """
    document = raw(SINGLE)
    for name, node in document["available_node_types"].items():
        assert node["min_workers"] == node["max_workers"], name
    assert document["min_workers"] == document["max_workers"]


def test_T_U_cluster_04():
    """T-U-cluster-04 (FR-17.9, NFR-05): the limits, the mount and `--user` on all three.

    `bugloop_llm` carrying no `--cpus` and no `--memory` is deliberate and the
    file's own comment says why. Fixture: none. Tier 0.
    """
    types = raw(SINGLE)["available_node_types"]
    for name in TYPES:
        options = types[name]["docker"]["run_options"]
        assert "--user $(id -u):$(id -g)" in options, name
    for name in ("bugloop_circt", "bugloop_repair"):
        options = types[name]["docker"]["run_options"]
        assert any(o.startswith("--cpus=") for o in options), name
        assert any(o.startswith("--memory=") for o in options), name
        assert "-v ${BUGLOOP_ARTEFACTS}:${BUGLOOP_ARTEFACTS}" in options, name
    llm = types["bugloop_llm"]["docker"]["run_options"]
    assert not [o for o in llm if o.startswith(("--cpus", "--memory"))]
    assert "NFR-05's outer level" in SINGLE.read_text(encoding="utf-8")


def test_T_U_cluster_05():
    """T-U-cluster-05 (FR-03.8, NFR-06, NFR-07): the setup lines, and no credential.

    The one credential in either file is the literal reference
    `${GEMINI_API_KEY}`, asserted as a reference by pattern and never resolved
    here. Fixture: none. Tier 0.
    """
    types = raw(SINGLE)["available_node_types"]
    for name in ("bugloop_circt", "bugloop_repair"):
        lines = types[name]["docker"]["run_setup_commands"]
        assert sum(1 for line in lines if line.startswith("git config")) == 3, name
        assert any("/etc/passwd" in line for line in lines), name
        assert not [line for line in lines if "pip install lit" in line], name
    llm = types["bugloop_llm"]["docker"]["run_setup_commands"]
    assert len(llm) == 2 and any("ssh-keyscan" in line for line in llm)
    assert not [line for line in llm if ".claude" in line]

    # Over the DOCUMENT and not the text: `cluster_single.yaml`'s header comment
    # names GITHUB_TOKEN to say that it appears in no key, and a grep over the
    # raw text would fail on the sentence that states the rule.
    for path in (SINGLE, GCP):
        document = yaml.safe_dump(raw(path))
        for forbidden in ("GITHUB_TOKEN", "~/.claude", "~/.gemini",
                          "~/.config/gcloud", "AQ.", "AIza", "ghp_"):
            assert forbidden not in document, (path.name, forbidden)
        for line in document.splitlines():
            if "GEMINI_API_KEY" in line:
                assert "${GEMINI_API_KEY}" in line, line


def test_T_U_cluster_06():
    """T-U-cluster-06 (NFR-10): the GCP skeleton names the same three worker types.

    It is a SKELETON: §12.2 leaves `available_node_types` as a comment saying
    "identical to cluster_single.yaml except the artefact mount", so the three
    types appear under `gcp_nodes` and the images are in that comment rather
    than in a key (errata row 13). What the test can assert is the three names,
    the deferral being recorded, and that no loop code reads either file's node
    names. Fixture: none. Tier 0.
    """
    nodes = raw(GCP)["gcp_nodes"]
    assert set(nodes) - {"project", "zone"} == set(TYPES)
    text = GCP.read_text(encoding="utf-8")
    assert "identical to cluster_single.yaml" in text
    assert "DEFERRED under ADR-D-14" in text
    assert "${BUGLOOP_GCP_HEAD_IP}" in text


def test_T_U_cluster_07(loader_env):
    """T-U-cluster-07 (NFR-10): both files load through `chia.cluster.config.load_config`.

    The GCP file's `provider.head_ip` placeholder is what makes the second half
    true: `load_config` raises `KeyError 'head_ip'` on a file without one, and
    parsing is not readiness. Fixture: none. Tier 0.
    """
    from chia.cluster.config import ClusterConfig, load_config

    single = load_config(str(SINGLE))
    assert isinstance(single, ClusterConfig)
    assert {name: (node.resources, node.num_workers)
            for name, node in single.node_types.items()} == {
                name: ({resource: 1}, count)
                for name, (resource, count) in TYPES.items()}

    gcp = load_config(str(GCP))
    assert isinstance(gcp, ClusterConfig) and gcp.head_ip == "10.0.0.2"


def test_T_U_cluster_08(loader_env, monkeypatch):
    """T-U-cluster-08 (NFR-06, FR-12.11): the LLM type, and what the loader does with `${...}`.

    Loaded twice: with the key set the value is substituted, and with it unset
    the literal `${GEMINI_API_KEY}` survives into the container's environment,
    which is why `build_llm` refuses a key beginning `${`. Fixture: none
    (the synthetic key is this module's own constant). Tier 0.
    """
    from chia.cluster.config import load_config

    llm = load_config(str(SINGLE)).node_types["bugloop_llm"]
    assert llm.docker.image == "ghcr.io/ucb-bar/chia:latest"
    env_lines = [o for o in llm.docker.run_options if o.startswith("-e ")]
    assert env_lines == [f"-e GEMINI_API_KEY={SYNTHETIC_KEY}",
                         "-e BUGLOOP_ALLOW_LIVE_MODEL=${BUGLOOP_ALLOW_LIVE_MODEL}",
                         "-e SSH_AUTH_SOCK=/ssh-agent"]
    assert not [o for o in llm.docker.run_options if ".claude" in o]

    monkeypatch.delenv("GEMINI_API_KEY")
    unexpanded = load_config(str(SINGLE)).node_types["bugloop_llm"]
    assert "-e GEMINI_API_KEY=${GEMINI_API_KEY}" in unexpanded.docker.run_options
    assert bug_loop.LIVE_MODEL_ENV not in os.environ


def test_T_U_cluster_09(monkeypatch, loader_env, tmp_path):
    """T-U-cluster-09 (NFR-10, FR-19.8): the head activates one real environment.

    New id (W-17's ninth fix, errata row 25). §12.1 wrote `source ~/.bashrc &&
    conda activate circtbugloop` and no machine of this project has that
    environment, so every head command would have failed at `chia up` and the
    cluster would have come up with Ray started from the system python. The
    three head commands now activate `${BUGLOOP_HEAD_ENV}`, which the operator
    sets to their own environment's activate script; YAML has no defaulting
    form, so an unset variable survives as the literal and `chia up` fails
    loudly rather than starting the wrong interpreter. `bug_loop_submit.sh`
    holds the default, so the driver's job and the head's Ray are one
    environment. Fixture: none. Tier 0.
    """
    from chia.cluster.config import load_config

    document = raw(SINGLE)
    head = (document["head_setup_commands"]
            + document["head_start_ray_commands"])
    assert len(head) == 3
    assert all(command.startswith("source ${BUGLOOP_HEAD_ENV}")
               for command in head), head
    # No command activates a conda environment or sources a login shell. The
    # word survives in two COMMENTS, one naming the worker image's own lit path
    # and one naming what this replaced, so the check is over the commands.
    commands = [c for key, value in document.items()
                if key.endswith(("_commands", "setup_commands"))
                for c in (value or [])]
    commands += [c for node in document["available_node_types"].values()
                 for c in (node.get("run_setup_commands") or [])]
    assert not [c for c in commands if "conda" in c or "bashrc" in c]

    # Expanded by CHIA's own loader from the operator's shell, and left as the
    # literal when the shell has no value, which is the same rule the model key
    # travels by (T-U-cluster-08).
    activate = tmp_path / "venv" / "bin" / "activate"
    activate.parent.mkdir(parents=True)
    activate.write_text("# a head environment\n", encoding="utf-8")
    monkeypatch.setenv("BUGLOOP_HEAD_ENV", str(activate))
    loaded = load_config(str(SINGLE))
    assert loaded.head_setup_commands == [f"source {activate}"]
    assert all(str(activate) in command
               for command in loaded.head_start_ray_commands)

    monkeypatch.delenv("BUGLOOP_HEAD_ENV")
    unexpanded = load_config(str(SINGLE))
    assert unexpanded.head_setup_commands == ["source ${BUGLOOP_HEAD_ENV}"]

    # The submit wrapper is where the default lives, and it derives the job's
    # own interpreter from it rather than trusting whatever `python` resolves to.
    submit = (FLOW / "bug_loop_submit.sh").read_text(encoding="utf-8")
    assert 'export BUGLOOP_HEAD_ENV="${BUGLOOP_HEAD_ENV:-' in submit
    assert 'PYBIN="${BUGLOOP_PY:-$(dirname "$BUGLOOP_HEAD_ENV")/python}"' in submit
    assert "BUGLOOP_HEAD_ENV" not in submit.split("ENV_JSON=")[1].split("PY\n)")[0]


def test_T_U_cluster_10(loader_env):
    """T-U-cluster-10 (K2, NFR-06): only `llm` and `repair` carry the credential.

    New id, W-20b. K2 measured the other side of this: the seeded arm and stage
    6 built their backend on the `circt` worker, which carries neither variable,
    so every seeded generation and every triage report refused. Since the fix
    the only node that constructs a client is `llm.llm_turn` at `{"llm": 1.0}`,
    and stage 7's chain is CHIA's own on `{"repair": 1}`; every other type must
    therefore see neither name, and a YAML that gave one to `bugloop_circt`
    would be handing a key to the containers that run generated input.
    Fixture: none. Tier 0.
    """
    from chia.cluster.config import load_config

    keyed = {}
    for name, node in load_config(str(SINGLE)).node_types.items():
        options = " ".join(node.docker.run_options)
        keyed[name] = ("GEMINI_API_KEY" in options,
                       bug_loop.LIVE_MODEL_ENV in options)
    assert keyed == {"bugloop_llm": (True, True), "bugloop_repair": (True, True),
                     "bugloop_circt": (False, False)}
