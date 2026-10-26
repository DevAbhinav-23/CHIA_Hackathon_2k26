#!/usr/bin/env python3
"""Run one argv in a fresh process under a 4 GiB address-space and 60 s wall limit.

Prints one JSON object: exit status, signal name, limit hit, stdout/stderr.
Stdlib only, so it runs on the host and inside the campaigns' image alike.
"""
import json
import resource
import signal
import subprocess
import sys

AS_BYTES, WALL_S = 4 * 2**30, 60


def _limit():
    resource.setrlimit(resource.RLIMIT_AS, (AS_BYTES, AS_BYTES))


def main(argv: list) -> int:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, errors="replace",
                              timeout=WALL_S, preexec_fn=_limit)
        rc, out, err, limit = done.returncode, done.stdout, done.stderr, None
    except subprocess.TimeoutExpired as hit:
        rc, limit = None, "wall"
        out = (hit.stdout or b"").decode(errors="replace") if isinstance(hit.stdout, bytes) else hit.stdout or ""
        err = (hit.stderr or b"").decode(errors="replace") if isinstance(hit.stderr, bytes) else hit.stderr or ""
    sig = signal.Signals(-rc).name if rc is not None and rc < 0 else None
    print(json.dumps({"exit_status": None if sig else rc, "signal": sig, "limit_hit": limit,
                      "stdout": out[-20000:], "stderr": err[-200000:]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
