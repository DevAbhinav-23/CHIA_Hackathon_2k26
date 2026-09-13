#!/usr/bin/env bash
# Build the paper. Exits non-zero on any LaTeX error.
set -euo pipefail
cd "$(dirname "$0")"

OPTS="-interaction=nonstopmode -halt-on-error -file-line-error"

pdflatex $OPTS main.tex
bibtex main
pdflatex $OPTS main.tex
pdflatex $OPTS main.tex

if grep -qE '^(\./)?.*:[0-9]+: ' main.log; then
  echo "LaTeX reported errors:" >&2
  grep -E '^(\./)?.*:[0-9]+: ' main.log >&2
  exit 1
fi

cp main.pdf circt-bug-loop-paper-v3.pdf
echo "pages: $(pdfinfo circt-bug-loop-paper-v3.pdf | awk '/^Pages:/{print $2}')"
echo "wrote circt-bug-loop-paper-v3.pdf"
