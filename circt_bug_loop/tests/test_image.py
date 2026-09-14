"""The Dockerfile and the `ImageSpec` it emits (`03-LLD.md` §1.2, §4.11, §4.11.1).

`04-Test-Plan.md` §1.22, the `T-U-image-*` tests, under the name §1.3's
exemption list carries since W-16 (`test_image_spec.py` -> `test_image.py`).

The unit under test is an image, so most of the plan's rows are tier 2. Two
things make a tier-0 half real anyway and this module is built on both: the
Dockerfile is a committed text whose seven deviations can be read off it, and
the image W-04 published left a recorded manifest,
`analysis/measurements/raw/image-manifest.json`, taken from a freshly started
container of the published image (FR-03.16). Every tier-0 test below reads one
of those two; every tier-2 test starts a container from
`chia-circt-assert:eade0de61bc5` and is skipped, never passed, without it.

Nothing here builds an image. `build_image`'s own argument list, its tag rule
and its lit-discovery parser are `T-U-driver-24` and `T-U-driver-25` in
`test_bug_loop.py`, at tier 0 and with no daemon.
"""
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


# ---------------------------------------------------------------------------
# Tier 0: the recorded manifest, and the Dockerfile's own text
# ---------------------------------------------------------------------------


@pytest.mark.t0
def test_T_U_image_10():
    """T-U-image-10 (FR-03.10): the recorded manifest fills every `ImageSpec` field.

    The `ImageSpec` is built from W-04's own manifest rather than from a
    fixture written by hand, so the record under test is the one the published
    image produced, and the eight keys of §2.11 are the ones that reach
    `RunManifest.image_spec`. Fixture: `raw/image-manifest.json`. Tier 0.
    """
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
    """T-U-image-16 (FR-03.16): the recorded hashes name every target, and only paths in the build tree.

    The hashes' own provenance is asserted too: the manifest records that it was
    computed from a freshly started container of the published image, which is
    §5.2's rule and is what stops a hash being taken from a build tree that no
    worker will ever run. Fixture: `raw/image-manifest.json`. Tier 0.
    """
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
    """T-U-image-04, -14, -15 (FR-03.4, FR-03.14, FR-03.15): the flags, slang and Verilator.

    Read off the recorded manifest: the flag string is FR-03.4's exactly, the
    image is ADR-D-13 branch (a) with slang from source, and one Verilator
    version serves the campaign. Fixture: `raw/image-manifest.json`. Tier 0.
    """
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
    """T-U-image-19 (FR-03.3, FR-03.4, FR-03.14): §4.11's seven deviations, off the file.

    Six of the seven are readable in the Dockerfile itself; the seventh, the
    absent `--progress=plain`, is asserted on `build_image`'s argument list,
    which is where the flag would have been. The two `same RUN` deviations are
    asserted as one `RUN` and not as two nearby lines, because a separate layer
    is exactly what they exist to avoid. Fixture:
    `upstream/dockerfiles/ChiaCirctAssertDockerfile`. Tier 0.
    """
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
    """T-U-image-01, -18 (FR-03.1, FR-03.2): three fetch commands, and no `git init`.

    `git init` on the base's already-populated clone prints "Reinitialized" and
    the `git remote add` after it fails, aborting the layer, so both are
    asserted absent; the second fetch is what makes `${CIRCT_VER}` a name
    `ls-tree` can resolve, which is what the pin check needs. Fixture: the
    Dockerfile. Tier 0.
    """
    text = dockerfile()
    assert "git init" not in text and "git remote add" not in text
    for command in (
            "git -C /workspace/circt fetch --depth 1 origin ${CIRCT_SHA}",
            "git -C /workspace/circt fetch --depth 1 origin tag ${CIRCT_VER}",
            "git -C /workspace/circt checkout --detach ${CIRCT_SHA}"):
        assert command in text, command
    assert "checkout --detach FETCH_HEAD" not in text
    assert "ls-tree ${CIRCT_VER} llvm" in text or "ls-tree" in text


# ---------------------------------------------------------------------------
# Tier 2: the published image itself
# ---------------------------------------------------------------------------


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_16_reproduces():
    """T-U-image-16 (FR-03.16): the recorded hashes reproduce in a fresh container.

    One container, six `sha256sum`s, compared against the committed manifest.
    This is the check pre-flight 7 makes on every worker before a campaign
    starts, run here against the image that manifest was taken from. Tier 2.
    """
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
    """T-U-image-07 (FR-03.7): every target exists in the image and runs `--version`.

    The target list is read from the recorded manifest and is a parameter, not
    a constant. Tier 2.
    """
    for name, entry in manifest()["tool_hashes"].items():
        done = in_image(entry["path"], "--version")
        assert done.returncode == 0, (name, done.stderr[-400:])
        assert "LLVM version" in done.stdout, name


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_03_12_sdk_strip():
    """T-U-image-03, -12 (FR-03.3, FR-03.12): the strip holds and LLVM's assertions stay off.

    Tier 2.
    """
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
    """T-U-image-04 (FR-03.4): the flags in the build tree, and the debug section.

    `CMakeCache.txt` carries the flag string, no compile command carries
    `-DNDEBUG`, and `circt-opt` carries `.debug_line`, which is what makes the
    symboliser able to resolve file and line. Tier 2.
    """
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
    """T-U-image-05 (FR-03.5): every target references `__assert_fail`.

    The set comparison against the committed baseline of non-referencing
    objects needs the build tree's object list, which is `T-U-image-05`'s other
    half and W-04's own measurement; what runs here is the six binaries' own
    undefined-symbol check, which is the part a container answers in seconds.
    Tier 2.
    """
    for name, entry in manifest()["tool_hashes"].items():
        done = in_image("bash", "-c", f"nm -u {entry['path']} | grep -c __assert_fail")
        assert done.stdout.strip() == "1", (name, done.stdout)


@pytest.mark.t2
@pytest.mark.needs_image
@needs_image
def test_T_U_image_17_lit_discovery():
    """T-U-image-17 (FR-03.17): lit discovers the tree with no configuration error.

    `mlir_src_root` points at the SDK, discovery exits 0, `circt-tblgen` tests
    are among what it lists, and no `fatal: unable to parse config file` line
    appears. It is `build_image` step 4, run against the published image, and
    the parser it feeds is `T-U-driver-25`'s. Tier 2.
    """
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
    """T-U-image-08, -09, -19 (FR-03.8, FR-03.9): lit, ssh, rsync, and the ENV block.

    `lit` at the one path `circt_warm_build` checks; `ssh` and `rsync`, which
    CHIA's own CIRCT base does not carry; and the five `BUGLOOP_*` variables,
    readable from inside a running container, which is what lets a report state
    the commit and the flag string without re-deriving them. Tier 2.
    """
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
    """T-U-image-01 (FR-03.1): the image's own checkout is the commit it claims.

    Tier 2.
    """
    recorded = manifest()
    head = in_image("git", "-C", "/workspace/circt", "rev-parse", "HEAD")
    assert head.stdout.strip() == recorded["circt_sha"]
    pin = in_image("git", "-C", "/workspace/circt", "ls-tree", "HEAD", "llvm")
    assert recorded["llvm_pin"] in pin.stdout
