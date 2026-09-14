#!/usr/bin/env bash
# Submit the circt_bug_loop driver as a job via `chia job submit`, so its driver
# logs appear in the dashboard and via `chia job logs <id>` (NFR-09). Running the
# driver directly registers a DRIVER-type job whose stdout the job server does
# NOT capture; only a SUBMISSION job gets retrievable logs
# (chia:examples/circt_issue_solver/fix_issues_submit.sh:5-9).
#
# THE ONE DIFFERENCE FROM CHIA'S WRAPPER IS THE TOKEN, AND ONLY THE TOKEN.
# CHIA's own wrapper injects GITHUB_TOKEN through the job's runtime-env env_vars,
# and its own comment records that the value is then stored in the job's
# runtime_env metadata and is visible in `chia job` output and the dashboard. The
# loop's driver reads the token from a 0600 file on the head instead (NFR-06,
# section 11.1), so no token appears below.
#
# --runtime-env-json ITSELF IS KEPT. A `chia job submit` SUBMISSION job does not
# inherit the submitting shell's environment, which is precisely why CHIA's
# wrapper forwards anything at all; removing the flag with the token would leave
# bug_loop.py's --artefact-root and --image-tag defaults resolving to nothing
# inside the job process, FR-17.9's single artefact root with no value at run
# time, and pre-flight checks 4 and 5 checking the wrong path. The three
# variables below are NOT secrets: two are a path and a tag this repository's own
# README prints, and the third is a GCP project id CHIA's own wrapper forwards
# for the same reason (chia:examples/circt_issue_solver/circt_issue_loop.py:71-72).
#
# GEMINI_API_KEY IS NOT FORWARDED EITHER, and that is the second half of the same
# rule (11.2 step 4, added 2026-09-14). The model credential reaches the llm
# workers through `docker run -e ...` at `chia up`, expanded from the operator's
# shell by CHIA's config loader; a runtime_env value would instead be stored in
# the job's metadata and shown by `chia job` and the dashboard. Nor is
# BUGLOOP_ALLOW_LIVE_MODEL forwarded: it is a cluster-level interlock, set in the
# operator's shell beside the key, and a job that could set it would be a job
# that could switch the loop live.
#
# THE HEAD ENVIRONMENT. cluster_single.yaml activates ${BUGLOOP_HEAD_ENV} in
# every head_* command, and the YAML cannot default it, so the default lives
# here: the driver's job must run from the same interpreter `ray start --head`
# ran from, or it imports a chia the cluster does not have. Exported and not
# merely read, so a `chia up` run from this shell afterwards sees the same
# value. It is NOT forwarded through --runtime-env-json: it is a path on the
# head and not a job parameter, and the three keys below are the whole set.
set -euo pipefail

ADDR="${RAY_JOB_ADDR:-http://localhost:8265}"
FLOW_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export BUGLOOP_HEAD_ENV="${BUGLOOP_HEAD_ENV:-$HOME/.cache/chia-venv/bin/activate}"
PYBIN="${BUGLOOP_PY:-$(dirname "$BUGLOOP_HEAD_ENV")/python}"
CHIABIN="${BUGLOOP_CHIA:-chia}"

: "${BUGLOOP_ARTEFACTS:?set BUGLOOP_ARTEFACTS to the bind-mounted artefact root}"
: "${BUGLOOP_IMAGE_TAG:?set BUGLOOP_IMAGE_TAG to the assertions-on image tag}"

ENV_JSON="$("$PYBIN" - <<'PY'
import json, os
env = {"BUGLOOP_ARTEFACTS": os.environ["BUGLOOP_ARTEFACTS"],
       "BUGLOOP_IMAGE_TAG": os.environ["BUGLOOP_IMAGE_TAG"]}
gcp = os.environ.get("GOOGLE_CLOUD_PROJECT")
if gcp:
    env["GOOGLE_CLOUD_PROJECT"] = gcp
print(json.dumps({"env_vars": env}))
PY
)"

WAIT_FLAG=()
[ "${NO_WAIT:-0}" = "1" ] && WAIT_FLAG=(--no-wait)

exec "$CHIABIN" job submit \
  --address "$ADDR" \
  --runtime-env-json "$ENV_JSON" \
  "${WAIT_FLAG[@]}" \
  -- "$PYBIN" "$FLOW_DIR/bug_loop.py" "$@"
