#!/bin/bash
# W-04b: the assertions-OFF twin of W-04's image. Same Dockerfile, same CIRCT_SHA,
# CIRCT_VER, TOOL_TARGETS, BUILD_JOBS; only CXX_FLAGS_RELEASE differs.
set -u
CTX=$HOME/Projects/chia-bugloop
OUT=/home/adi/Projects/chia-hackathon/analysis/measurements/raw
SHA=eade0de61bc5a0d2ba1b9da951b69efcab19f8ce
VER=firtool-1.159.0
TAG=chia-circt-ndebug:${SHA:0:12}
cd "$CTX" || exit 1
date -Is > "$OUT/w04b-image-build.start"
T0=$SECONDS
docker build -f dockerfiles/ChiaCirctAssertDockerfile \
  -t "$TAG" \
  --build-arg CIRCT_SHA="$SHA" \
  --build-arg CIRCT_VER="$VER" \
  --build-arg CXX_FLAGS_RELEASE="-O3 -DNDEBUG -gline-tables-only" \
  --build-arg BUILD_JOBS=8 \
  . > "$OUT/w04b-image-build.log" 2>&1
RC=$?
WALL=$((SECONDS-T0))
date -Is > "$OUT/w04b-image-build.end"
echo "rc=$RC wall=${WALL}s tag=$TAG" | tee "$OUT/w04b-image-build.rc"
