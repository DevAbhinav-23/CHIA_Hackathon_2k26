#!/usr/bin/env bash
# Fetch the blobless `llvm/circt` clone the tier-1 tests read (04-Test-Plan.md 13).
#
# The clone is NOT committed: 400 MB of someone else's history is not a fixture,
# and every tier-1 test that needs it skips cleanly without it. What IS committed
# is this script and the SHA below, so a fresh checkout gets the same tree the
# measurements were taken against and a different one is a loud failure rather
# than a quiet drift.
#
#   tests/fixtures/fetch_clone.sh [destination]
#
# The destination defaults to $BUGLOOP_CORPUS_CLONE, then to
# ~/.cache/chia-pin-smoke/circt, which is where this host's clone already is;
# an existing clone is fetched and re-checked rather than re-cloned.
set -euo pipefail

# The corpus head of `budget.yaml`, at which FR-01.1's counts of 187 and 171
# hold. It is READ from the committed file and not repeated here, so the two
# cannot disagree (FR-14.1).
FLOW="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HEAD_SHA="$(sed -n 's/^corpus_head_sha: *"\{0,1\}\([0-9a-f]\{40\}\).*/\1/p' \
            "$FLOW/budget.yaml")"
[ -n "$HEAD_SHA" ] || { echo "no corpus_head_sha in $FLOW/budget.yaml" >&2; exit 1; }

DEST="${1:-${BUGLOOP_CORPUS_CLONE:-$HOME/.cache/chia-pin-smoke/circt}}"
REMOTE="https://github.com/llvm/circt.git"

if [ ! -d "$DEST/.git" ]; then
  # --filter=blob:none: the corpus builder reads trees and a few blobs by name,
  # never a checkout of every blob, and the difference is 400 MB against 7 GB.
  git clone --filter=blob:none "$REMOTE" "$DEST"
fi

git -C "$DEST" fetch --filter=blob:none origin
# QUOTED, so the shell does not glob the refspec against the working directory,
# which is the one way this line goes wrong and does so silently.
git -C "$DEST" fetch origin 'refs/tags/firtool-*:refs/tags/firtool-*'
git -C "$DEST" checkout --detach -q "$HEAD_SHA"

ACTUAL="$(git -C "$DEST" rev-parse HEAD)"
[ "$ACTUAL" = "$HEAD_SHA" ] || {
  echo "HEAD is $ACTUAL and budget.yaml's corpus head is $HEAD_SHA" >&2; exit 1; }
TAGS="$(git -C "$DEST" for-each-ref --format='%(refname)' 'refs/tags/firtool-*' | wc -l)"
echo "$DEST at $ACTUAL, $TAGS firtool-* tags"
