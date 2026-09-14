# `fixtures/layout/`

| Path | What it is | How it was made |
|---|---|---|
| `chia_stub/` | A CHIA checkout with the four paths `upstream/sync-to-chia.sh` touches and nothing else. | **Constructed.** `chia/chipyard/circt.py` holds one function so an append can be shown not to remove it; `examples/circt_issue_solver/issue_task.py` already carries the `elif backend == "vertex":` line, so the script's already-present guard is what the tier-0 idempotency test exercises. The patch applying for real is `T-U-layout-10`, tier 1, against a throwaway `git clone` of `~/.cache/chia-src`. |
