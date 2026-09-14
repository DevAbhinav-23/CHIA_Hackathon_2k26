#!/usr/bin/env python3
"""W-09: turn one confirmed attempt piece into a committed crash fixture.

Writes the six files of 04-Test-Plan.md 5.2 into <dest>/<class>_<nn>/, taking
every value from the recorded run rather than from anything hand-typed: the
input piece, the argv the runner actually executed (rewritten to the fixture's
own relative paths), the stderr verbatim, and w09_oracle.py's classification.

usage: w09_mkfixture.py --attempt <dir> --piece parent-p00 --name crash_01
                        --dest <fixtures/crashes> --why <one paragraph>
"""
import argparse, json, os, re, shutil, sys

ROOT = os.path.dirname(os.path.abspath(__file__))


def llvm_pin(parent_sha, seed_sha):
    """The seed's parent_llvm out of analysis/pin_window_raw.json."""
    raw = os.path.join(ROOT, "..", "pin_window_raw.json")
    for c in json.load(open(raw))["candidates"]:
        if c["sha"] == seed_sha:
            return c["parent_llvm"]
    return None


def main():
    ap = argparse.ArgumentParser()
    for f in ("attempt", "piece", "name", "dest", "why"):
        ap.add_argument("--" + f, required=True)
    a = ap.parse_args()

    pdir = os.path.join(a.attempt, a.piece)
    meta = json.load(open(os.path.join(a.attempt, "meta.json")))
    run = json.load(open(os.path.join(pdir, "run.json")))
    orc = json.load(open(os.path.join(pdir, "oracle.json")))
    if not orc["fired"]:
        sys.exit(f"{pdir} did not fire; refusing to record it")

    out = os.path.join(a.dest, a.name)
    os.makedirs(out, exist_ok=True)
    src_in = [f for f in os.listdir(pdir) if f.startswith("input.")][0]
    ext = src_in.split(".", 1)[1]
    shutil.copyfile(os.path.join(pdir, src_in), os.path.join(out, "input." + ext))
    shutil.copyfile(os.path.join(pdir, "stderr.txt"), os.path.join(out, "stderr.txt"))

    # 5.2: the full argument vector, tool first, prlimit prefix excluded.  The
    # absolute binary and input paths are the mining host's; the fixture carries
    # the tool by name and the input by its own filename.
    argv = [meta["target"]] + ["input." + ext if v.startswith(pdir) else v
                               for v in run["argv"][1:]]
    json.dump(argv, open(os.path.join(out, "argv.json"), "w"), indent=1)

    json.dump({"circt_sha": meta["parent"], "parent_of": meta["seed"],
               "sdk_tag": meta["sdk_tag"],
               "llvm_pin": llvm_pin(meta["parent"], meta["seed"]),
               "source": "seed"},
              open(os.path.join(out, "commit.json"), "w"), indent=1)

    rc = run["rc"]
    json.dump({"class": orc["status"],
               "assertion_text": orc["assertion_text"],
               "assertion_site": orc["assertion_site"],
               "fingerprint_frame": orc["fingerprint_frame"],
               # Recorded since W-09 finding 2: the inlined-group scope rule is
               # what this field measures, so it needs a regression guard of its
               # own rather than being reconstructible only from the trace.
               "out_of_scope_root": orc["out_of_scope_root"],
               "prologue_dropped": orc["prologue_dropped"],
               "top_frames": orc["top_frames"],
               "exit_status": rc if (rc is not None and rc >= 0) else None,
               "signal": orc["signal"]},
              open(os.path.join(out, "expected.json"), "w"), indent=1)

    site = orc["assertion_site"] or orc["first_circt_frame"] or ""
    open(os.path.join(out, "README.md"), "w").write(
        f"# `{a.name}`\n\n{a.why.strip()}\n\n"
        f"Mined by `analysis/measurements/w09_attempt.sh` on 2026-09-14 from seed "
        f"`{meta['seed'][:12]}` (`{meta['test_path']}`), observed at its first parent "
        f"`{meta['parent'][:12]}` built against `{meta['sdk_tag']}`; the same input at the "
        f"seed commit does not fire. Tool `{meta['target']}`, class `{orc['status']}`, "
        f"signal `{orc['signal']}`.\n\n"
        f"`stderr.txt`, `expected.json:assertion_site` and the frame paths carry the mining "
        f"host's build prefix (`{meta['worktree']}` for CIRCT sources, "
        f"`{meta['sdk']}` for the SDK), not the image's `/workspace/circt/` and "
        f"`/opt/circt-sdk/`. 03-LLD.md 3.7.1 strips the build prefix before the site enters a "
        f"fingerprint, so the prefix is evidence and never a compared value; the relative site "
        f"is `{re.sub(re.escape(meta['worktree']) + '/', '', site)}`.\n")
    print(out)


if __name__ == "__main__":
    main()
