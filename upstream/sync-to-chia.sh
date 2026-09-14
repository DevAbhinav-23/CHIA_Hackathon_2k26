#!/usr/bin/env bash
# Turn the two team-repository trees into a CHIA checkout (03-LLD.md 1.4).
#
#   circt_bug_loop/   ->  <checkout>/examples/circt_bug_loop/
#   upstream/         ->  the four CHIA-core files plus one patch
#
# It writes nothing in the team repository and it is IDEMPOTENT: running it
# twice leaves the checkout byte-identical, which tests/test_layout.py asserts
# by running it into a temporary copy and diffing. The two steps that could
# repeat themselves are guarded by what they would add: the appended functions
# by their marker line, and the vertex branch by the branch itself.
#
# Usage:
#   upstream/sync-to-chia.sh [--dry-run] <chia-checkout>
#
# --dry-run prints every command it would run and changes nothing, so an
# operator can see the five steps before the first one happens.
set -euo pipefail

DRY_RUN=0
TARGET=""

usage() {
    printf 'usage: %s [--dry-run] <chia-checkout>\n' "$0"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        -h|--help) usage; exit 0 ;;
        --) shift; break ;;
        -*) printf 'unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
        *)
            if [ -n "$TARGET" ]; then
                printf 'one checkout only; got %s and %s\n' "$TARGET" "$1" >&2
                exit 2
            fi
            TARGET="$1"
            ;;
    esac
    shift
done

if [ -z "$TARGET" ]; then
    usage >&2
    exit 2
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPSTREAM="$REPO/upstream"
FLOW="$REPO/circt_bug_loop"

# --- step 0: refuse a target that is not a CHIA checkout --------------------
# Both halves are named, because a directory holding chia/ and no examples/ is
# a wheel's site-packages and not the checkout the pull request is opened from.
for required in "chia" "examples/circt_issue_solver"; do
    if [ ! -d "$TARGET/$required" ]; then
        printf 'refusing %s: it holds no %s/ (03-LLD.md 1.4)\n' "$TARGET" "$required" >&2
        exit 3
    fi
done

run() {
    if [ "$DRY_RUN" = "1" ]; then
        printf 'would run:'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

note() {
    if [ "$DRY_RUN" = "1" ]; then
        printf 'would %s\n' "$1"
    else
        printf '%s\n' "$1"
    fi
}

# --- step 1: the flow itself -----------------------------------------------
# --delete, so a file deleted here is deleted there; the three excludes are
# build products and runtime state, none of which the pull request carries.
run mkdir -p "$TARGET/examples/circt_bug_loop"
run rsync -a --delete \
    --exclude '__pycache__' --exclude '*.pyc' --exclude 'loop.db*' \
    "$FLOW/" "$TARGET/examples/circt_bug_loop/"

# --- step 2: the Dockerfile and its workflow --------------------------------
run mkdir -p "$TARGET/dockerfiles" "$TARGET/.github/workflows"
for file in "$UPSTREAM"/dockerfiles/*; do
    [ -e "$file" ] || continue
    run cp "$file" "$TARGET/dockerfiles/$(basename "$file")"
done
for file in "$UPSTREAM"/.github/workflows/*; do
    [ -e "$file" ] || continue
    run cp "$file" "$TARGET/.github/workflows/$(basename "$file")"
done

# --- step 3: the three generic functions, appended ---------------------------
# 1.2 says chia/chipyard/circt.py is APPENDED to and never edited. The marker is
# what makes a second run a no-op; the `from __future__` line is dropped because
# it is only legal at the top of a file and this text lands at the bottom of
# one.
ADDITIONS="$UPSTREAM/chia-chipyard-circt-additions.py"
MARKER="# --- circt_bug_loop: the three generic CIRCT functions (03-LLD.md 3.10) ---"
CIRCT_PY="$TARGET/chia/chipyard/circt.py"
if grep -qF "$MARKER" "$CIRCT_PY"; then
    note "leave $CIRCT_PY alone: the additions are already there"
elif [ "$DRY_RUN" = "1" ]; then
    note "append $ADDITIONS (below its module docstring) to $CIRCT_PY"
else
    {
        printf '\n\n%s\n' "$MARKER"
        python3 - "$ADDITIONS" <<'PY'
"""Emit the additions file's body: everything below its module docstring.

Three things are dropped and each for one reason. The docstring is the append
INSTRUCTION and not code. `from __future__ import annotations` is legal only at
the top of a file and this text lands at the bottom of one. The file's own
`__all__` is its export list as a standalone module; appended, it would become
the merged module's and would hide every function CHIA already has there from
a star import.
"""
import ast
import sys

source = open(sys.argv[1], encoding="utf-8").read()
lines = source.split("\n")
tree = ast.parse(source)
drop = set()
for index, node in enumerate(tree.body):
    docstring = (index == 0 and isinstance(node, ast.Expr)
                 and isinstance(node.value, ast.Constant)
                 and isinstance(node.value.value, str))
    future = isinstance(node, ast.ImportFrom) and node.module == "__future__"
    exports = (isinstance(node, ast.Assign)
               and any(getattr(t, "id", "") == "__all__" for t in node.targets))
    if docstring or future or exports:
        drop.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
out = [line for number, line in enumerate(lines, start=1) if number not in drop]
sys.stdout.write("\n".join(out).strip("\n") + "\n")
PY
    } >> "$CIRCT_PY"
    printf 'appended the three functions to %s\n' "$CIRCT_PY"
fi

# --- step 4: the TWO additive patches against CHIA's own files ----------------
# Each is guarded by its own marker, so a checkout synced twice is not patched
# twice and a checkout tracking a CHIA that has merged one is left alone (1.4).
#
# The pair belongs together. `issue_task-vertex-branch.patch` is what lets
# stage 7 run the backend the manifest names (K7); `vertex-usage.patch` is what
# makes a turn's thinking tokens countable at all (K11), and a campaign whose
# sync applied only the first would price every turn low by an unknown factor.
# The driver's own `stage_shipped` applies both to the copy it ships and
# pre-flight checks 13 and 14 read that copy; this script is the other half,
# for an operator running the flow from a CHIA checkout.
ISSUE_TASK="$TARGET/examples/circt_issue_solver/issue_task.py"
if grep -qF 'elif backend == "vertex":' "$ISSUE_TASK"; then
    note "leave $ISSUE_TASK alone: the vertex branch is already present"
else
    run git -C "$TARGET" apply --3way "$UPSTREAM/issue_task-vertex-branch.patch"
fi

VERTEX_PY="$TARGET/chia/models/vertex.py"
if [ ! -f "$VERTEX_PY" ]; then
    note "no $VERTEX_PY: this target ships no Vertex backend, nothing to patch"
elif grep -qF 'thoughts_token_count' "$VERTEX_PY"; then
    note "leave $VERTEX_PY alone: the two billed usage fields are already summed"
else
    run git -C "$TARGET" apply --3way "$UPSTREAM/vertex-usage.patch"
fi

if [ "$DRY_RUN" = "1" ]; then
    printf 'dry run: nothing under %s was changed\n' "$TARGET"
else
    printf 'synced %s into %s\n' "$REPO" "$TARGET"
fi
