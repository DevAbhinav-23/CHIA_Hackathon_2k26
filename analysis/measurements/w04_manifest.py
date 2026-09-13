#!/usr/bin/env python3
"""FR-03.16: the hash manifest, computed from a FRESHLY STARTED container of the
published image and never from the build tree (03-LLD.md 5.2)."""
import json, subprocess, sys, datetime

TAG = sys.argv[1]
OUT = sys.argv[2]


def dock(script: str) -> str:
    r = subprocess.run(["docker", "run", "--rm", TAG, "bash", "-lc", script],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"container command failed ({r.returncode}): {script}\n{r.stderr}")
    return r.stdout


def host(*a: str) -> str:
    return subprocess.run(a, capture_output=True, text=True, check=True).stdout.strip()


targets = dock('echo -n "$BUGLOOP_TOOL_TARGETS"').split()
bindir = "/workspace/circt/build/bin"

hashes = {}
for line in dock(f'for t in $BUGLOOP_TOOL_TARGETS; do sha256sum {bindir}/$t; done').splitlines():
    h, p = line.split()
    hashes[p.rsplit("/", 1)[1]] = {"path": p, "sha256": h}

sym = dock("sha256sum /opt/circt-sdk/bin/llvm-symbolizer").split()[0]
ver = dock("sha256sum /usr/bin/verilator").split()[0]

manifest = {
    "image_tag": TAG,
    "image_id": host("docker", "image", "inspect", "--format", "{{.Id}}", TAG),
    "image_digest": host("docker", "image", "inspect",
                         "--format", "{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}"
                                     "<not pushed: no RepoDigest>{{end}}", TAG),
    "image_size_bytes": int(host("docker", "image", "inspect", "--format", "{{.Size}}", TAG)),
    "layer_count": len(json.loads(host("docker", "image", "inspect",
                                       "--format", "{{json .RootFS.Layers}}", TAG))),
    "circt_sha": dock('echo -n "$BUGLOOP_CIRCT_SHA"'),
    "circt_sha_in_image": dock("git -C /workspace/circt rev-parse HEAD").strip(),
    "circt_ver": dock('echo -n "$BUGLOOP_CIRCT_VER"'),
    "llvm_pin": dock('git -C /workspace/circt ls-tree $BUGLOOP_CIRCT_SHA llvm').split()[2],
    "flag_string": dock('echo -n "$BUGLOOP_CXX_FLAGS_RELEASE"'),
    "targets": targets,
    "slang_enabled": dock('echo -n "$BUGLOOP_SLANG"') == "ON",
    "slang_version": dock("grep -m1 -rhoE 'slang version [0-9.+]+' "
                          "/workspace/circt/build/CMakeFiles/CMakeConfigureLog.yaml "
                          "2>/dev/null || true").strip()
                     or dock("/workspace/circt/build/bin/circt-verilog --version "
                             "| grep -i slang || true").strip(),
    "verilator_version": dock("verilator --version").strip(),
    "lit_version": dock("lit --version").strip(),
    "python_version": dock("python --version").strip(),
    "ray_version": dock('python -c "import ray; print(ray.__version__)"').strip(),
    "tool_hashes": hashes,
    "aux_hashes": {"llvm-symbolizer": {"path": "/opt/circt-sdk/bin/llvm-symbolizer",
                                       "sha256": sym},
                   "verilator": {"path": "/usr/bin/verilator", "sha256": ver}},
    "computed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "computed_from": "a freshly started container of the published image (FR-03.16)",
}

with open(OUT, "w") as f:
    json.dump(manifest, f, indent=2, sort_keys=False)
    f.write("\n")
print(json.dumps(manifest, indent=2))
