#!/usr/bin/env bash
# Make a fresh clone of this repository runnable. Idempotent: safe to re-run.
#
# It creates .venv, installs requirements.txt, clones CHIA at the pin into
# ~/.cache/chia-src, applies upstream/vertex-usage.patch to that checkout's
# WORKING TREE (never committed), installs it editable, and prints the two test
# commands. It does no network work beyond the two clones and pip, starts no
# cluster, builds no image and makes no model call.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${BUGLOOP_VENV:-$REPO/.venv}"
# Hard-coded and not configurable: circt_bug_loop/tests/test_upstream_patches.py
# and test_layout.py read this exact path, and skip 17 t0 tests without it.
CHIA_SRC="$HOME/.cache/chia-src"
CHIA_PIN="16c35e92aaaf9511c6453bf94cd5cf589698f4e3"
CHIA_URL="https://github.com/ucb-bar/chia"

say() { printf '==> %s\n' "$*"; }

# 1. Interpreter. CHIA requires >= 3.10; 3.10.19 is what the numbers were measured on.
PY="${BUGLOOP_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3.10 python3.11 python3.12 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
       && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
      PY="$candidate"; break
    fi
  done
fi
[ -n "$PY" ] || { echo "no python >= 3.10 found; set BUGLOOP_PYTHON" >&2; exit 1; }
say "interpreter: $("$PY" -c 'import sys; print(sys.executable, sys.version.split()[0])')"

# 2. Virtual environment.
if [ ! -x "$VENV/bin/python" ]; then
  say "creating $VENV"
  "$PY" -m venv "$VENV"
fi
VPY="$VENV/bin/python"
"$VPY" -m pip install --quiet --upgrade pip

# 3. CHIA at the pin. Cloned, never pulled: the pin is the contract.
if [ ! -d "$CHIA_SRC/.git" ]; then
  say "cloning CHIA into $CHIA_SRC"
  mkdir -p "$(dirname "$CHIA_SRC")"
  git clone --quiet "$CHIA_URL" "$CHIA_SRC"
fi
if [ "$(git -C "$CHIA_SRC" rev-parse HEAD)" != "$CHIA_PIN" ]; then
  say "checking out $CHIA_PIN"
  git -C "$CHIA_SRC" fetch --quiet origin "$CHIA_PIN" 2>/dev/null || git -C "$CHIA_SRC" fetch --quiet
  git -C "$CHIA_SRC" checkout --quiet "$CHIA_PIN"
fi

# 4. The one local modification. Uncommitted on purpose: test_layout.py clones
# CHIA_SRC and asserts the committed tree is still upstream's.
if grep -q 'thoughts_token_count' "$CHIA_SRC/chia/models/vertex.py"; then
  say "vertex-usage.patch already applied"
else
  say "applying upstream/vertex-usage.patch to $CHIA_SRC (working tree only)"
  git -C "$CHIA_SRC" apply -p1 "$REPO/upstream/vertex-usage.patch"
fi

# 5. Install: the pinned closure first, then CHIA itself without re-resolving it.
say "installing requirements.txt"
"$VPY" -m pip install --quiet -r "$REPO/requirements.txt"
say "installing CHIA editable from $CHIA_SRC"
"$VPY" -m pip install --quiet -e "$CHIA_SRC" --no-deps

# 6. Prove the import the driver relies on, and say where it landed.
"$VPY" - <<'PY'
# chia is a namespace package: __file__ is None, __path__ is not.
import pathlib, chia
print(f"==> chia imports from {pathlib.Path(chia.__path__[0]).resolve()}")
PY

cat <<EOF

Done. Run the tests with:

  $VENV/bin/python -m pytest circt_bug_loop/tests -q -m t0
  $VENV/bin/python -m pytest circt_bug_loop/tests -q -m "not t2 and not t3"

The first needs nothing further. The second additionally wants a blobless
llvm/circt clone and the prebuilt CIRCT SDK; without them its extra tests skip.
Beyond the tests, read docs/RUN.md.
EOF
