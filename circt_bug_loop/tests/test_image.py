"""The Dockerfile and the `ImageSpec` it emits (`03-LLD.md` §1.2)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from circt_bug_loop import bug_loop
from circt_bug_loop.store import ImageSpec

FLOW = Path(bug_loop.FLOW_DIR)
REPO = FLOW.parent
DOCKERFILE = REPO / "upstream" / "dockerfiles" / "ChiaCirctAssertDockerfile"
MANIFEST_PATH = REPO / "analysis" / "measurements" / "raw" / "image-manifest.json"

#: The image W-04 built and the campaign runs on.
IMAGE = "chia-circt-assert:eade0de61bc5"

#: §2.11's eight keys, the subset of `ImageSpec` that reaches the manifest.
MANIFEST_KEYS = {"circt_sha", "sdk_tag", "targets", "flag_string", "image_digest",
                 "verilator_version", "slang_enabled", "tool_hashes"}


def manifest() -> dict:
    """W-04's recorded hash manifest, as committed."""
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def dockerfile() -> str:
    """The Dockerfile's text."""
    return DOCKERFILE.read_text(encoding="utf-8")


def in_image(*command: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """Run one command in a fresh container of the published image."""
    return subprocess.run(["docker", "run", "--rm", "--entrypoint", "", IMAGE, *command],
                          capture_output=True, text=True, timeout=timeout)


def image_present() -> bool:
    """Whether a Docker daemon is reachable and holds the campaign's image."""
    if shutil.which("docker") is None:
        return False
    found = subprocess.run(["docker", "image", "inspect", IMAGE],
                           capture_output=True, text=True)
    return found.returncode == 0


needs_image = pytest.mark.skipif(not image_present(),
                                 reason=f"no {IMAGE} on this machine (tier 2)")


@pytest.mark.t0
def test_T_U_image_10():
    """T-U-image-10 (FR-03.10): the recorded manifest fills every `ImageSpec` field."""
    recorded = manifest()
    spec = ImageSpec(
        circt_sha=recorded["circt_sha"], sdk_tag=recorded["circt_ver"],
        targets=list(recorded["targets"]), flag_string=recorded["flag_string"],
        cmake_args=[], image_digest=recorded["image_digest"],
        image_tag=recorded["image_tag"],
        verilator_version=recorded["verilator_version"],
        slang_enabled=recorded["slang_enabled"], lit_discovery_ok=True,
        lit_discovered_count=1390, assertion_nonreferencing=[],
        tool_hashes={name: value["sha256"]
                     for name, value in recorded["tool_hashes"].items()})
    assert MANIFEST_KEYS <= {f for f in vars(spec)}
    reached = {key: getattr(spec, key) for key in MANIFEST_KEYS}
    assert set(reached) == MANIFEST_KEYS
    assert all(value not in (None, "") for value in reached.values())


@pytest.mark.t0
def test_T_U_image_16_recorded():
    """T-U-image-16 (FR-03.16): the recorded hashes name every target, and only paths in the build tree."""
    recorded = manifest()
    assert list(recorded["targets"]) == list(bug_loop.IMAGE_TARGETS)
    assert set(recorded["tool_hashes"]) == set(bug_loop.IMAGE_TARGETS)
    for name, entry in recorded["tool_hashes"].items():
        assert entry["path"] == f"/workspace/circt/build/bin/{name}", name
        assert len(entry["sha256"]) == 64 and int(entry["sha256"], 16) >= 0, name
    assert set(recorded["aux_hashes"]) == {"llvm-symbolizer", "verilator"}
    assert "freshly started container" in recorded["computed_from"]


@pytest.mark.t0
def test_T_U_image_04_recorded():
    """T-U-image-04, -14, -15 (FR-03.4): the flags, slang and Verilator."""
    recorded = manifest()
    assert recorded["flag_string"] == bug_loop.IMAGE_FLAG_STRING
    assert "-UNDEBUG" in recorded["flag_string"]
    assert "-DNDEBUG" not in recorded["flag_string"]
    assert recorded["slang_enabled"] is True
    assert recorded["slang_version"].startswith("slang version")
    assert recorded["verilator_version"].startswith("Verilator 5.020")
    assert recorded["circt_sha"] == recorded["circt_sha_in_image"]
    assert recorded["circt_ver"] == "firtool-1.159.0"


@pytest.mark.t0
def test_T_U_image_19_deviations():
    """T-U-image-19 (FR-03.3): §4.11's seven deviations, off the file."""
    text = dockerfile()
    runs = [block.strip() for block in text.split("\nRUN ")[1:]]

    # (1) BASE_IMAGE, the SDK re-installed at CIRCT_VER, FR-03.3's strip re-applied.
    assert text.index("ARG BASE_IMAGE") < text.index("FROM ${BASE_IMAGE}")
    sdk = [run for run in runs if "/opt/circt-sdk" in run]
    assert sdk and "${CIRCT_VER}" in "\n".join(sdk)
    assert "include/circt" in text and "lib/cmake/circt" in text

    # (2) the configure line, with LLVM_PARALLEL_LINK_JOBS=2.
    configure = [run for run in runs if "cmake -B build" in run]
    assert len(configure) == 1
    assert "-DLLVM_PARALLEL_LINK_JOBS=2" in configure[0]
    assert '-DCMAKE_CXX_FLAGS_RELEASE="${CXX_FLAGS_RELEASE}"' in configure[0]

    # (3) the apt line, with clang-tools among its five.
    apt = [run for run in runs if "apt-get install" in run]
    assert len(apt) == 1
    for package in ("verilator", "openssh-client", "rsync", "util-linux", "clang-tools"):
        assert package in apt[0], package

    # (4) and (5) the two same-RUN rules.
    assert configure[0].startswith("rm -rf /workspace/circt/build")
    ninja = [run for run in runs if run.startswith("ninja -C build")]
    assert len(ninja) == 1 and "chmod -R a+rwX" in ninja[0]

    # (6) the ENV block is last, and carries all five variables.
    env = text.rindex("\nENV BUGLOOP_CIRCT_SHA=")
    assert env > text.rindex("\nRUN ")
    for name in ("CIRCT_SHA", "CIRCT_VER", "TOOL_TARGETS", "CXX_FLAGS_RELEASE", "SLANG"):
        assert f"BUGLOOP_{name}=" in text, name

    # (7) no --progress=plain, asserted where the flag would have been.
    argv = bug_loop.build_argv(str(DOCKERFILE), "tag", bug_loop.image_manifest(
        "e" * 40, "firtool-1.159.0", bug_loop.IMAGE_TARGETS,
        bug_loop.IMAGE_FLAG_STRING), ".")
    assert "--progress=plain" not in argv


@pytest.mark.t0
def test_T_U_image_01_fetch_recipe():
    """T-U-image-01, -18 (FR-03.1): three fetch commands, and no `git init`."""
    text = dockerfile()
    assert "git init" not in text and "git remote add" not in text
    for command in (
            "git -C /workspace/circt fetch --depth 1 origin ${CIRCT_SHA}",
            "git -C /workspace/circt fetch --depth 1 origin tag ${CIRCT_VER}",
            "git -C /workspace/circt checkout --detach ${CIRCT_SHA}"):
        assert command in text, command
    assert "checkout --detach FETCH_HEAD" not in text
    assert "ls-tree ${CIRCT_VER} llvm" in text or "ls-tree" in text


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_16_reproduces():
    """T-U-image-16 (FR-03.16): the recorded hashes reproduce in a fresh container."""
    recorded = manifest()["tool_hashes"]
    done = in_image("sha256sum", *[entry["path"] for entry in recorded.values()])
    assert done.returncode == 0, done.stderr
    hashed = {line.split()[1].rsplit("/", 1)[1]: line.split()[0]
              for line in done.stdout.splitlines()}
    assert hashed == {name: entry["sha256"] for name, entry in recorded.items()}


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_07_versions():
    """T-U-image-07 (FR-03.7): every target exists in the image and runs `--version`."""
    for name, entry in manifest()["tool_hashes"].items():
        done = in_image(entry["path"], "--version")
        assert done.returncode == 0, (name, done.stderr[-400:])
        assert "LLVM version" in done.stdout, name


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_03_12_sdk_strip():
    """T-U-image-03, -12 (FR-03.3): the strip holds and LLVM's assertions stay off."""
    stripped = in_image("bash", "-c",
                        "ls -d /opt/circt-sdk/include/circt "
                        "/opt/circt-sdk/lib/cmake/circt 2>&1; true")
    assert "No such file" in stripped.stdout, stripped.stdout
    abi = in_image("grep", "-c", "define LLVM_ENABLE_ABI_BREAKING_CHECKS 0",
                   "/opt/circt-sdk/include/llvm/Config/abi-breaking.h")
    assert abi.returncode == 0 and abi.stdout.strip() == "1"


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_04_in_image():
    """T-U-image-04 (FR-03.4): the flags in the build tree, and the debug section."""
    cache = in_image("grep", "CMAKE_CXX_FLAGS_RELEASE:STRING",
                     "/workspace/circt/build/CMakeCache.txt")
    assert cache.returncode == 0
    assert bug_loop.IMAGE_FLAG_STRING in cache.stdout

    ndebug = in_image("bash", "-c",
                      "grep -c -- -DNDEBUG /workspace/circt/build/compile_commands.json "
                      "|| true")
    assert ndebug.stdout.strip() == "0", ndebug.stdout

    sections = in_image("bash", "-c",
                        "readelf -S /workspace/circt/build/bin/circt-opt | grep -c debug_line")
    assert int(sections.stdout.strip() or 0) >= 1


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_05_assertions_on():
    """T-U-image-05 (FR-03.5): every target references `__assert_fail`."""
    for name, entry in manifest()["tool_hashes"].items():
        done = in_image("bash", "-c", f"nm -u {entry['path']} | grep -c __assert_fail")
        assert done.stdout.strip() == "1", (name, done.stdout)


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_17_lit_discovery():
    """T-U-image-17 (FR-03.17): lit discovers the tree with no configuration error."""
    root = in_image("grep", "mlir_src_root",
                    "/workspace/circt/build/test/lit.site.cfg.py")
    assert root.returncode == 0 and "/opt/circt-sdk" in root.stdout

    done = in_image("/home/ray/anaconda3/envs/py_worker/bin/lit",
                    "--no-progress-bar", "--show-tests",
                    "/workspace/circt/build/test", timeout=600)
    ok, count = bug_loop.lit_discovery(done.returncode, done.stdout + done.stderr)
    assert ok is True and count > 1000, (done.returncode, count)
    assert "Tools/circt-tblgen" in done.stdout


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_08_09_19_environment():
    """T-U-image-08, -09, -19 (FR-03.8): lit, ssh, rsync, and the ENV block."""
    lit = in_image("/home/ray/anaconda3/envs/py_worker/bin/lit", "--version")
    assert lit.returncode == 0
    for command in (("ssh", "-V"), ("rsync", "--version"), ("verilator", "--version")):
        done = in_image(*command)
        assert done.returncode == 0, command

    env = in_image("bash", "-c", "env | grep '^BUGLOOP_' | sort")
    printed = dict(line.split("=", 1) for line in env.stdout.splitlines())
    recorded = manifest()
    assert printed["BUGLOOP_CIRCT_SHA"] == recorded["circt_sha"]
    assert printed["BUGLOOP_CIRCT_VER"] == recorded["circt_ver"]
    assert printed["BUGLOOP_CXX_FLAGS_RELEASE"] == recorded["flag_string"]
    assert printed["BUGLOOP_SLANG"] == "ON"
    assert printed["BUGLOOP_TOOL_TARGETS"].split() == list(recorded["targets"])


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_01_in_image():
    """T-U-image-01 (FR-03.1): the image's own checkout is the commit it claims."""
    recorded = manifest()
    head = in_image("git", "-C", "/workspace/circt", "rev-parse", "HEAD")
    assert head.stdout.strip() == recorded["circt_sha"]
    pin = in_image("git", "-C", "/workspace/circt", "ls-tree", "HEAD", "llvm")
    assert recorded["llvm_pin"] in pin.stdout


@pytest.mark.t0
def test_T_U_image_02_pin_line():
    """T-U-image-02 (FR-03.2): the phrase step 3 looks for is the phrase the file prints."""
    text = dockerfile()
    assert bug_loop.PIN_CHECK_LINE in text
    assert "PIN CHECK FAILED" in text and "exit 1" in text
    passed = text.index(bug_loop.PIN_CHECK_LINE)
    assert text.index("ls-tree ${CIRCT_SHA} llvm") < passed


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_05_objects():
    """T-U-image-05 (FR-03.5): the object scan, and the nineteen W-04 measured."""
    scan = in_image("sh", "-c", bug_loop._OBJECT_SCAN, timeout=900)
    assert scan.returncode == 0, scan.stderr[-400:]
    nonreferencing = sorted(scan.stdout.split())
    assert len(nonreferencing) == 19, nonreferencing
    assert all(name.endswith(".o") and "obj.CIRCT" in name
               for name in nonreferencing), nonreferencing
    assert not [name for name in nonreferencing if name.startswith("/")]

    total = in_image("sh", "-c", 'find /workspace/circt/build -path '
                                 '"*obj.CIRCT*.dir*" -name "*.o" | wc -l')
    assert total.stdout.strip() == "555"
