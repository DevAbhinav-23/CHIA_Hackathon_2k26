"""Both cluster YAMLs (`03-LLD.md` §12), the `T-U-cluster-*` tests of §1.24."""
import os
from pathlib import Path

import pytest
import yaml

from circt_bug_loop import bug_loop

pytestmark = pytest.mark.t0

FLOW = Path(bug_loop.FLOW_DIR)
SINGLE = FLOW / "cluster_single.yaml"
GCP = FLOW / "cluster_gcp.yaml"

#: A synthetic key of the `AQ.` shape `T-N-nfr06-02`'s pattern is written against.
SYNTHETIC_KEY = "AQ." + "0123456789abcdef0123456789abcdef"

#: §12.1's three worker types, their resource names and their container counts.
TYPES = {"bugloop_llm": ("llm", 2), "bugloop_circt": ("circt", 2),
         "bugloop_repair": ("repair", 1)}


def raw(path: Path) -> dict:
    """The file as YAML, before CHIA expands anything."""
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@pytest.fixture
def loader_env(monkeypatch, tmp_path):
    """The operator's shell at `chia up`, minus the interlock (see the module docstring)."""
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
    """T-U-cluster-02 (FR-12.11): three worker types, three resource names, 2/2/1."""
    types = raw(SINGLE)["available_node_types"]
    assert set(types) == set(TYPES)
    for name, (resource, count) in TYPES.items():
        assert types[name]["resources"] == {resource: 1}, name
        assert types[name]["max_workers"] == count, name
    assert raw(SINGLE)["max_workers"] == sum(c for _, c in TYPES.values())


def test_T_U_cluster_03():
    """T-U-cluster-03 (FR-14.5): the cluster is fixed-size on every type."""
    document = raw(SINGLE)
    for name, node in document["available_node_types"].items():
        assert node["min_workers"] == node["max_workers"], name
    assert document["min_workers"] == document["max_workers"]


def test_T_U_cluster_04():
    """T-U-cluster-04 (FR-17.9): the limits, the mount and `--user` on all three."""
    types = raw(SINGLE)["available_node_types"]
    for name in TYPES:
        options = types[name]["docker"]["run_options"]
        assert "--user $(id -u):$(id -g)" in options, name
    # FR-17.9's one artefact root is on ALL THREE types, which is what pre-flight check 5 probes.
    for name in TYPES:
        options = types[name]["docker"]["run_options"]
        assert "-v ${BUGLOOP_ARTEFACTS}:${BUGLOOP_ARTEFACTS}" in options, name
    for name in ("bugloop_circt", "bugloop_repair"):
        options = types[name]["docker"]["run_options"]
        assert any(o.startswith("--cpus=") for o in options), name
        assert any(o.startswith("--memory=") for o in options), name
    llm = types["bugloop_llm"]["docker"]["run_options"]
    assert not [o for o in llm if o.startswith(("--cpus", "--memory"))]
    assert "NFR-05's outer level" in SINGLE.read_text(encoding="utf-8")


def test_T_U_cluster_05():
    """T-U-cluster-05 (FR-03.8): the setup lines, and no credential."""
    types = raw(SINGLE)["available_node_types"]
    for name in ("bugloop_circt", "bugloop_repair"):
        lines = types[name]["docker"]["run_setup_commands"]
        assert sum(1 for line in lines if line.startswith("git config")) == 3, name
        assert any("/etc/passwd" in line for line in lines), name
        assert not [line for line in lines if "pip install lit" in line], name
    llm = types["bugloop_llm"]["docker"]["run_setup_commands"]
    assert len(llm) == 2 and any("ssh-keyscan" in line for line in llm)
    assert not [line for line in llm if ".claude" in line]

    # Over the DOCUMENT and not the text.
    for path in (SINGLE, GCP):
        document = yaml.safe_dump(raw(path))
        for forbidden in ("GITHUB_TOKEN", "~/.claude", "~/.gemini",
                          "~/.config/gcloud", "AQ.", "AIza", "ghp_"):
            assert forbidden not in document, (path.name, forbidden)
        for line in document.splitlines():
            if "GEMINI_API_KEY" in line:
                assert "${GEMINI_API_KEY}" in line, line


def test_T_U_cluster_06():
    """T-U-cluster-06 (NFR-10): the GCP skeleton names the same three worker types."""
    nodes = raw(GCP)["gcp_nodes"]
    assert set(nodes) - {"project", "zone"} == set(TYPES)
    text = GCP.read_text(encoding="utf-8")
    assert "identical to cluster_single.yaml" in text
    assert "DEFERRED under ADR-D-14" in text
    assert "${BUGLOOP_GCP_HEAD_IP}" in text


def test_T_U_cluster_07(loader_env):
    """T-U-cluster-07 (NFR-10): both files load through `chia.cluster.config.load_config`."""
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
    """T-U-cluster-08 (NFR-06): the LLM type, and what the loader does with `${...}`."""
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
    """T-U-cluster-09 (NFR-10): the head activates one real environment."""
    from chia.cluster.config import load_config

    document = raw(SINGLE)
    head = (document["head_setup_commands"]
            + document["head_start_ray_commands"])
    assert len(head) == 3
    assert all(command.startswith("source ${BUGLOOP_HEAD_ENV}")
               for command in head), head
    # No command activates a conda environment or sources a login shell.
    commands = [c for key, value in document.items()
                if key.endswith(("_commands", "setup_commands"))
                for c in (value or [])]
    commands += [c for node in document["available_node_types"].values()
                 for c in (node.get("run_setup_commands") or [])]
    assert not [c for c in commands if "conda" in c or "bashrc" in c]

    # Expanded by CHIA's own loader from the operator's shell.
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

    # The submit wrapper is where the default lives.
    submit = (FLOW / "bug_loop_submit.sh").read_text(encoding="utf-8")
    assert 'export BUGLOOP_HEAD_ENV="${BUGLOOP_HEAD_ENV:-' in submit
    assert 'PYBIN="${BUGLOOP_PY:-$(dirname "$BUGLOOP_HEAD_ENV")/python}"' in submit
    assert "BUGLOOP_HEAD_ENV" not in submit.split("ENV_JSON=")[1].split("PY\n)")[0]


def test_T_U_cluster_10(loader_env):
    """T-U-cluster-10 (NFR-06): only `llm` and `repair` carry the credential."""
    from chia.cluster.config import load_config

    keyed = {}
    for name, node in load_config(str(SINGLE)).node_types.items():
        options = " ".join(node.docker.run_options)
        keyed[name] = ("GEMINI_API_KEY" in options,
                       bug_loop.LIVE_MODEL_ENV in options)
    assert keyed == {"bugloop_llm": (True, True), "bugloop_repair": (True, True),
                     "bugloop_circt": (False, False)}


def test_T_U_cluster_11(loader_env):
    """W-23: only the repair type runs the chowned variant of the same image."""
    from chia.cluster.config import load_config

    nodes = load_config(str(SINGLE)).node_types
    assert nodes["bugloop_circt"].docker.image == "chia-circt-assert:eade0de61bc5"
    assert nodes["bugloop_repair"].docker.image == \
        "chia-circt-assert:eade0de61bc5-u1000"
    for name in ("bugloop_circt", "bugloop_repair"):
        assert nodes[name].docker.pull_before_run is False, name

    # The pre-flight accepts the variant and still refuses another commit.
    sha = "eade0de61bc5a0d2ba1b9da951b69efcab19f8ce"
    assert bug_loop.tag_matches_pin("eade0de61bc5", sha)
    assert bug_loop.tag_matches_pin("eade0de61bc5-u1000", sha)
    for wrong in ("eade0de61bc5-", "eade0de61bc", "deadbeefcafe",
                  "deadbeefcafe-u1000", "eade0de61bc5a", ""):
        assert not bug_loop.tag_matches_pin(wrong, sha), wrong

    # Both circt-side types still carry the image name the hash check probes.
    summary = bug_loop.cluster_summary(str(SINGLE))
    assert summary["image_worker_types"] == ["bugloop_circt", "bugloop_repair"]
