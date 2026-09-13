#!/bin/bash
# W-04: build the assertions-on CIRCT image.
set -u
CTX=$HOME/Projects/chia-bugloop
OUT=/home/adi/Projects/chia-hackathon/analysis/measurements/raw
SHA=eade0de61bc5a0d2ba1b9da951b69efcab19f8ce
VER=firtool-1.159.0
TAG=chia-circt-assert:${SHA:0:12}
cd "$CTX" || exit 1
date -Is > "$OUT/image-build.start"
T0=$SECONDS
docker build -f dockerfiles/ChiaCirctAssertDockerfile \
  -t "$TAG" \
  --build-arg CIRCT_SHA="$SHA" \
  --build-arg CIRCT_VER="$VER" \
  --build-arg BUILD_JOBS=8 \
  . > "$OUT/image-build.log" 2>&1
RC=$?
WALL=$((SECONDS-T0))
date -Is > "$OUT/image-build.end"
echo "rc=$RC wall=${WALL}s tag=$TAG" | tee "$OUT/image-build.rc"
