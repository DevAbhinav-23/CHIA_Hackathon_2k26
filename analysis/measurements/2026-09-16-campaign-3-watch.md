# Campaign 3 (full corpus) — watch log

## Registration

- Tag: `registration/campaign-3`
- Commit: `a65331b` "bugloop: register campaign 3: window 150000 s, cap USD 175 per job, whole corpus"
- Registered budget (`circt_bug_loop/budget.yaml`): `arm_window_seconds: 150000.0`, `campaign_spend_cap_usd: 175.0`
- Gate before launch: `720 passed, 1 skipped, 16 deselected` (`-m "not t2 and not t3"`), 0 failed.
  One stale test literal was updated as part of registration: `circt_bug_loop/tests/test_ledger.py:190`,
  `window.per_arm_window["seeded"]` 14400.0 -> 150000.0 (the assertion needs a value at or above the
  committed window). No other code changed.

## Launch

- Launch time: 2026-09-16 00:31 IST = 2026-09-15 19:01 UTC
- Cluster: `circt_bug_loop/cluster_single.yaml`, 5 containers (2 llm, 2 circt, 1 repair)
- Common flags: `--mode discovery --generator model --no-repair --clone ~/.cache/chia-pin-smoke/circt --budget circt_bug_loop/budget.yaml`

| job id | arm / shard | run manifest id | seeds in shard |
|---|---|---|---|
| `raysubmit_cW8jPuXb25WsD3Wf` | seeded, shard 0/2 | `f0b2ef10e17849f4b4ae45510024f96a` | 94 |
| `raysubmit_sKZprKtnd2uyj7yv` | seeded, shard 1/2 | `db45ab7bb42f4ca3aba5985c94468dec` | 93 |
| `raysubmit_zFmMa2xyu5uWuWSL` | mutation | `91e58983716b46e2902c01cc7cde10ab` | 187 |

`--no-repair` is the architect's decision: stage 7 blocks a shard for up to 45 minutes per new candidate
and produced no fix in three attempts. Repair stays off for the whole campaign.

### Expectation

- About 2.25 seeds/hour/shard.
- The USD 175 per-job cap is expected to stop each seeded shard at about 35 seeds (~15 h).
- The mutation job should finish within ~20 minutes by `seed_set_exhausted`.

### Pre-flight

This build does not emit numbered `check_NN` pre-flight lines to stdout; the observable pass evidence is
that each job wrote its run manifest under `~/bugloop-artefacts/<run id>/` and proceeded to stage 2, with
no `refused` or error line in the logs. All three jobs cleared this. Check 11 (forum post) records
`unposted`, as expected — nothing is filed anywhere.

### Observations at launch (documented, not acted on)

- Shard split reports 94 + 93 = 187 seeds, and the mutation job also reports a seed set of 187. The
  campaign registration note says 184 eligible seeds. The discrepancy is recorded here only; no code or
  configuration was changed.
- `dedup_verdict` and `gate_decision` carry no `run_manifest_id` column (they key on `candidate_id`), so
  the per-run counts below are obtained by joining those tables to `candidate`.

## 2026-09-16 00:36 IST / 2026-09-15 19:07 UTC

- Job states: shard 0/2 RUNNING, shard 1/2 RUNNING, mutation SUCCEEDED.
- mutation (`91e58983`) terminal already, 4 min 26 s wall: `stop_reason: seed_set_exhausted`,
  reported `probes: 1154`, `seeds: 187`, `seconds: 266.408645`.
- Probe table: `91e58983` mutation — 96 distinct seed_sha, 1154 probes. The two seeded runs have written
  no probe rows yet (still in their first stage-2 generation).
- Candidates: none for any run. Dedup verdicts: none. Gate decisions: none.
- Metered spend: no `ledger_entry` rows with billed turns for any of the three runs yet (the mutation arm
  completed without a metered model turn recorded).
- Host: /tmp 1 % used, free memory 4548 MB, 5 containers up.
- Anomalies: none.

## 2026-09-16 00:38 IST / 2026-09-15T19:08:40Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
f0b2ef10|seeded|1|5
-- candidates
run|cands
f0b2ef10|2
-- spend
run|spend_usd|turns
f0b2ef10|1.94|2
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|2
-- gate
run|decision|n
f0b2ef10|nothing|2
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 1% used, free memory 4365 MB, containers 5.

Anomalies: none.

## 2026-09-16 01:09 IST / 2026-09-15T19:39:20Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|1|15
f0b2ef10|seeded|2|25
-- candidates
run|cands
f0b2ef10|7
-- spend
run|spend_usd|turns
db45ab7b|1.38|4
f0b2ef10|5.31|7
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|7
-- gate
run|decision|n
f0b2ef10|nothing|7
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 1% used, free memory 4484 MB, containers 5.

Anomalies: none.

## 2026-09-16 01:39 IST / 2026-09-15T20:09:42Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|1|15
f0b2ef10|seeded|2|30
-- candidates
run|cands
f0b2ef10|9
-- spend
run|spend_usd|turns
db45ab7b|2.86|5
f0b2ef10|5.93|9
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|8
f0b2ef10|new|1
-- gate
run|decision|n
f0b2ef10|nothing|8
f0b2ef10|report|1
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 1% used, free memory 5452 MB, containers 5.

Anomalies: none.

## 2026-09-16 02:09 IST / 2026-09-15T20:39:58Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|2|25
f0b2ef10|seeded|3|40
-- candidates
run|cands
f0b2ef10|9
-- spend
run|spend_usd|turns
db45ab7b|4.75|8
f0b2ef10|7.52|12
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|8
f0b2ef10|new|1
-- gate
run|decision|n
f0b2ef10|nothing|8
f0b2ef10|report|1
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 1% used, free memory 4947 MB, containers 5.

Anomalies: none.

## 2026-09-16 02:40 IST / 2026-09-15T21:10:15Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|2|25
f0b2ef10|seeded|3|40
-- candidates
run|cands
f0b2ef10|9
-- spend
run|spend_usd|turns
db45ab7b|4.75|8
f0b2ef10|7.52|12
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|8
f0b2ef10|new|1
-- gate
run|decision|n
f0b2ef10|nothing|8
f0b2ef10|report|1
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 1% used, free memory 4967 MB, containers 5.

Anomalies: none.

### Note at 02:42 IST — Vertex 429 throttling explains the flat 30-minute interval

Both seeded shards sat at the same probe and spend counts across the 02:09 and 02:40 snapshots. The job
logs show the reason: the live model turns are being rate-limited and the backend is backing off, e.g.

```
(llm_turn pid=394) [DEBUG] 429; retry 4/6 in 182.5 seconds
(llm_turn pid=451) [DEBUG] 429; retry 3/6 in 76.6 seconds
```

This is the known intermittent shared-quota 429, not a daily cap; the backend's own retry with backoff is
handling it (retries 1/6 through 4/6 observed, none exhausted). Host load average 1.5, so the machine is
idle-waiting on the API rather than saturated. No action taken: throughput is reduced but both jobs are
alive and progressing between backoffs. Recorded so the seeds/hour figure in the final block is read
against this, not against the 2.25 seeds/hour/shard expectation.

## 2026-09-16 03:10 IST / 2026-09-15T21:40:55Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|2|30
f0b2ef10|seeded|3|44
-- candidates
run|cands
f0b2ef10|10
-- spend
run|spend_usd|turns
db45ab7b|5.46|9
f0b2ef10|8.28|13
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|8
f0b2ef10|new|2
-- gate
run|decision|n
f0b2ef10|nothing|8
f0b2ef10|report|1
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 4930 MB, containers 5.

Anomalies: none.

### Note at 03:12 IST — projected run length is well beyond the 15 h expectation

Measured over the first 2 h 39 m of shard 0/2 (launch 00:31 IST to the 03:10 IST snapshot):

- 3 distinct seeds probed, i.e. about 1.1 seeds/hour, against the 2.25 seeds/hour/shard expectation.
  The shortfall is the Vertex 429 backoff documented above, not stalled work.
- USD 8.28 billed, i.e. about USD 3.1/hour and about USD 2.76 per seed. The registration expectation of
  "USD 175 stops each seeded shard at about 35 seeds" assumed roughly USD 5 per seed.

Extrapolating the observed numbers: the USD 175 per-job cap would not be reached for about 56 h, while the
registered `arm_window_seconds` of 150000 s (41.7 h) is reached first. So each seeded shard is currently
projected to terminate on `arm_window` at roughly 45-50 seeds, around 18:10 IST on 2026-09-17, rather than
on the spend cap at about 35 seeds after ~15 h. If the 429 throttling clears, the seed rate rises toward
the expected 2.25/hour and the spend cap becomes the binding constraint again at roughly 28 h.

Recorded only. No budget, code or job change was made; the registered window and cap stand as committed.

## 2026-09-16 03:41 IST / 2026-09-15T22:11:40Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|4|50
f0b2ef10|seeded|5|65
-- candidates
run|cands
f0b2ef10|11
-- spend
run|spend_usd|turns
db45ab7b|11.68|15
f0b2ef10|13.56|20
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|9
f0b2ef10|new|2
-- gate
run|decision|n
f0b2ef10|nothing|9
f0b2ef10|report|2
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 4911 MB, containers 5.

Anomalies: none.

## 2026-09-16 04:12 IST / 2026-09-15T22:42:01Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|5|70
f0b2ef10|seeded|6|85
-- candidates
run|cands
f0b2ef10|11
-- spend
run|spend_usd|turns
db45ab7b|16.86|20
f0b2ef10|16.63|25
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|9
f0b2ef10|new|2
-- gate
run|decision|n
f0b2ef10|nothing|9
f0b2ef10|report|2
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 4797 MB, containers 5.

Anomalies: none.

## 2026-09-16 04:42 IST / 2026-09-15T23:12:30Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|6|80
f0b2ef10|seeded|7|105
-- candidates
run|cands
f0b2ef10|13
-- spend
run|spend_usd|turns
db45ab7b|20.84|24
f0b2ef10|20.94|31
-- dedup
run|verdict|n
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|new|3
-- gate
run|decision|n
f0b2ef10|nothing|10
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 5008 MB, containers 5.

Anomalies: none.

## 2026-09-16 05:12 IST / 2026-09-15T23:42:50Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|8|100
f0b2ef10|seeded|9|130
-- candidates
run|cands
db45ab7b|6
f0b2ef10|13
-- spend
run|spend_usd|turns
db45ab7b|25.73|35
f0b2ef10|26.14|38
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|3
db45ab7b|new|3
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|4
db45ab7b|report|2
f0b2ef10|nothing|10
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 4874 MB, containers 5.

Anomalies: none.

## 2026-09-16 05:43 IST / 2026-09-16T00:13:10Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|10|130
f0b2ef10|seeded|11|155
-- candidates
run|cands
db45ab7b|14
f0b2ef10|13
-- spend
run|spend_usd|turns
db45ab7b|31.89|46
f0b2ef10|29.86|45
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|8
db45ab7b|new|6
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|9
db45ab7b|report|5
f0b2ef10|nothing|10
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 4802 MB, containers 5.

Anomalies: none.

## 2026-09-16 06:13 IST / 2026-09-16T00:43:27Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|11|145
f0b2ef10|seeded|12|170
-- candidates
run|cands
db45ab7b|14
f0b2ef10|17
-- spend
run|spend_usd|turns
db45ab7b|33.82|50
f0b2ef10|31.95|49
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|8
db45ab7b|new|6
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|known_closed_issue|4
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|9
db45ab7b|report|5
f0b2ef10|nothing|14
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 4820 MB, containers 5.

Anomalies: none.

## 2026-09-16 06:43 IST / 2026-09-16T01:13:44Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|12|169
f0b2ef10|seeded|13|190
-- candidates
run|cands
db45ab7b|14
f0b2ef10|20
-- spend
run|spend_usd|turns
db45ab7b|40.61|56
f0b2ef10|34.87|54
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|8
db45ab7b|new|6
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|known_closed_issue|7
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|9
db45ab7b|report|5
f0b2ef10|nothing|17
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 2% used, free memory 4498 MB, containers 5.

Anomalies: none.

## 2026-09-16 07:14 IST / 2026-09-16T01:44:00Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|14|189
f0b2ef10|seeded|14|205
-- candidates
run|cands
db45ab7b|14
f0b2ef10|24
-- spend
run|spend_usd|turns
db45ab7b|46.26|62
f0b2ef10|38.49|58
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|8
db45ab7b|new|6
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|9
db45ab7b|report|5
f0b2ef10|nothing|21
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4459 MB, containers 5.

Anomalies: none.

## 2026-09-16 07:44 IST / 2026-09-16T02:14:18Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|14|199
f0b2ef10|seeded|15|220
-- candidates
run|cands
db45ab7b|14
f0b2ef10|24
-- spend
run|spend_usd|turns
db45ab7b|47.65|64
f0b2ef10|42.46|62
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|8
db45ab7b|new|6
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|9
db45ab7b|report|5
f0b2ef10|nothing|21
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4543 MB, containers 5.

Anomalies: none.

## 2026-09-16 08:14 IST / 2026-09-16T02:44:35Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|16|228
f0b2ef10|seeded|17|245
-- candidates
run|cands
db45ab7b|19
f0b2ef10|24
-- spend
run|spend_usd|turns
db45ab7b|50.96|72
f0b2ef10|46.16|69
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|11
db45ab7b|fixed_post_pin|1
db45ab7b|new|7
f0b2ef10|duplicate_of_candidate|10
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|13
db45ab7b|report|5
f0b2ef10|nothing|21
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4544 MB, containers 5.

Anomalies: none.

## 2026-09-16 08:45 IST / 2026-09-16T03:15:05Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|17|244
f0b2ef10|seeded|18|270
-- candidates
run|cands
db45ab7b|23
f0b2ef10|26
-- spend
run|spend_usd|turns
db45ab7b|53.9|77
f0b2ef10|48.81|75
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|15
db45ab7b|fixed_post_pin|1
db45ab7b|new|7
f0b2ef10|duplicate_of_candidate|11
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|17
db45ab7b|report|6
f0b2ef10|nothing|23
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4575 MB, containers 5.

Anomalies: none.

## 2026-09-16 09:15 IST / 2026-09-16T03:45:25Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|19|264
f0b2ef10|seeded|20|290
-- candidates
run|cands
db45ab7b|25
f0b2ef10|26
-- spend
run|spend_usd|turns
db45ab7b|56.47|85
f0b2ef10|52.97|81
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|15
db45ab7b|fixed_post_pin|1
db45ab7b|new|9
f0b2ef10|duplicate_of_candidate|11
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|3
-- gate
run|decision|n
db45ab7b|nothing|17
db45ab7b|report|8
f0b2ef10|nothing|23
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4636 MB, containers 5.

Anomalies: none.

## 2026-09-16 09:45 IST / 2026-09-16T04:15:45Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|20|279
f0b2ef10|seeded|21|315
-- candidates
run|cands
db45ab7b|28
f0b2ef10|41
-- spend
run|spend_usd|turns
db45ab7b|59.34|90
f0b2ef10|58.26|89
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|17
db45ab7b|fixed_post_pin|1
db45ab7b|new|10
f0b2ef10|duplicate_of_candidate|25
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|4
-- gate
run|decision|n
db45ab7b|nothing|19
db45ab7b|report|9
f0b2ef10|nothing|38
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4589 MB, containers 5.

Anomalies: none.

## 2026-09-16 10:16 IST / 2026-09-16T04:46:02Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|20|289
f0b2ef10|seeded|22|330
-- candidates
run|cands
db45ab7b|28
f0b2ef10|41
-- spend
run|spend_usd|turns
db45ab7b|61.15|92
f0b2ef10|60.69|93
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|17
db45ab7b|fixed_post_pin|1
db45ab7b|new|10
f0b2ef10|duplicate_of_candidate|25
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|4
-- gate
run|decision|n
db45ab7b|nothing|19
db45ab7b|report|9
f0b2ef10|nothing|38
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4431 MB, containers 5.

Anomalies: none.

## 2026-09-16 10:46 IST / 2026-09-16T05:16:21Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|20|289
f0b2ef10|seeded|22|330
-- candidates
run|cands
db45ab7b|28
f0b2ef10|41
-- spend
run|spend_usd|turns
db45ab7b|61.15|92
f0b2ef10|60.69|93
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|17
db45ab7b|fixed_post_pin|1
db45ab7b|new|10
f0b2ef10|duplicate_of_candidate|25
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|4
-- gate
run|decision|n
db45ab7b|nothing|19
db45ab7b|report|9
f0b2ef10|nothing|38
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 3% used, free memory 4492 MB, containers 5.

Anomalies: none.

### Note at 10:48 IST — second throttling window, plus transient server errors on shard 1/2

The 10:16 and 10:46 snapshots are byte-identical for both shards (289 and 330 probes, USD 61.15 and
USD 60.69), i.e. 30 minutes with no forward progress. Cause is the same as at 02:42, with an extra
symptom on shard 1/2:

```
(llm_turn pid=394) [DEBUG] 429; retry 1/6 in 22.7 seconds
(llm_turn pid=451) [DEBUG] 429; retry 2/6 in 40.7 seconds
(llm_turn pid=451) Server error on attempt 1/3, backing off 5s
(llm_turn pid=451) Server error on attempt 2/3, backing off 10s
```

Both jobs remain RUNNING and both retry ladders are still inside their limits (429 retry 2 of 6, server
error attempt 2 of 3); host load average 1.3, so this is API-side, not local. The stall is at 30 minutes,
below the 60-minute documentation threshold at the time of the previous snapshot and well below the
120-minute deadlock threshold that would permit `ray job stop`. No intervention taken.

## 2026-09-16 11:17 IST / 2026-09-16T05:47:13Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|20|289
f0b2ef10|seeded|23|335
-- candidates
run|cands
db45ab7b|28
f0b2ef10|41
-- spend
run|spend_usd|turns
db45ab7b|61.15|92
f0b2ef10|61.16|95
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|17
db45ab7b|fixed_post_pin|1
db45ab7b|new|10
f0b2ef10|duplicate_of_candidate|25
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|4
-- gate
run|decision|n
db45ab7b|nothing|19
db45ab7b|report|9
f0b2ef10|nothing|38
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 4% used, free memory 4287 MB, containers 5.

Anomalies:
- shard-1/2 RUNNING with no new probe row for 61 min

  Evidence for the 61-minute stall on shard 1/2 (job `raysubmit_sKZprKtnd2uyj7yv`), last lines of its log:

  ```
  (llm_turn pid=451, ip=127.0.0.1) [DEBUG] 429; retry 1/6 in 16.3 seconds
  (llm_turn pid=451, ip=127.0.0.1) [DEBUG] 429; retry 2/6 in 39.7 seconds
  (llm_turn pid=451, ip=127.0.0.1) [DEBUG] 429; retry 3/6 in 76.7 seconds
  ```

  Still API-side throttling, job RUNNING, retry ladder not exhausted. Below the 120-minute
  deadlock threshold, so no `ray job stop` was issued.

## 2026-09-16 11:47 IST / 2026-09-16T06:17:58Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|20|289
f0b2ef10|seeded|23|335
-- candidates
run|cands
db45ab7b|28
f0b2ef10|41
-- spend
run|spend_usd|turns
db45ab7b|61.61|93
f0b2ef10|61.16|95
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|17
db45ab7b|fixed_post_pin|1
db45ab7b|new|10
f0b2ef10|duplicate_of_candidate|25
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|4
-- gate
run|decision|n
db45ab7b|nothing|19
db45ab7b|report|9
f0b2ef10|nothing|38
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 4% used, free memory 4373 MB, containers 5.

Anomalies:
- shard-1/2 RUNNING with no new probe row for 91 min

### Note at 11:50 IST — the shard 1/2 stall is throttling, not deadlock

Shard 1/2 has now gone 91 minutes without a new `probe` row, approaching the 120-minute threshold that
would permit `ray job stop`. That threshold exists for a deadlocked run that would otherwise idle out the
41 h window. This run is not idle: across the same interval its ledger advanced from USD 61.15 / 92 billed
turns (10:16) to USD 61.61 / 93 billed turns (11:47), and its log shows the 429 retry ladder still
cycling. The job is making forward progress on model turns; it is simply slow because each turn is being
retried against API throttling, and a probe row is only written once a whole generation turn lands.

Decision: do not stop shard 1/2 even if the probe-row gap crosses 120 minutes, for as long as its billed
turns keep advancing and its retry ladder stays unexhausted, because stopping it would discard completed
work for a condition that is not the deadlock the rule targets. This will be revisited if billed turns
also stop advancing, which would be the real idle signature. Recorded here rather than acted on.

Shard 0/2 is in the same state at a 30-minute gap (335 probes at both 11:17 and 11:47, USD 61.16).

## 2026-09-16 12:18 IST / 2026-09-16T06:48:45Z

Job states:
- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`): RUNNING
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`): RUNNING
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`): SUCCEEDED

```
-- probes
run|arm|seeds|probes
91e58983|mutation|96|1154
db45ab7b|seeded|20|289
f0b2ef10|seeded|23|335
-- candidates
run|cands
db45ab7b|28
f0b2ef10|41
-- spend
run|spend_usd|turns
db45ab7b|61.61|95
f0b2ef10|61.16|96
-- dedup
run|verdict|n
db45ab7b|duplicate_of_candidate|17
db45ab7b|fixed_post_pin|1
db45ab7b|new|10
f0b2ef10|duplicate_of_candidate|25
f0b2ef10|fixed_post_pin|1
f0b2ef10|known_closed_issue|7
f0b2ef10|known_open_issue|4
f0b2ef10|new|4
-- gate
run|decision|n
db45ab7b|nothing|19
db45ab7b|report|9
f0b2ef10|nothing|38
f0b2ef10|report|3
```

Log error lines:
```
== shard-0/2
== shard-1/2
== mutation
    "stop_reason": "seed_set_exhausted"
```

Host: /tmp 4% used, free memory 6088 MB, containers 5.

Anomalies:
- shard-0/2 RUNNING with no new probe row for 61 min
- shard-1/2 RUNNING with no new probe row for 122 min

### Note at 12:22 IST — shard 1/2 past 120 minutes; retry ladder is now exhausting

Shard 1/2 crossed the 122-minute mark with no new `probe` row. Re-checking it against the criterion I set
at 11:50 changes part of the picture:

- Forward progress is still real: billed turns went 93 (11:47) to 95 (12:18), and the log shows a new
  probe actor starting, `probe_b3b407b37bb2_1 started at 127.0.0.1:8001`.
- But the 429 ladder is no longer merely cycling; it now reaches its last rung, and the outer attempt
  loop is failing out:

```
(llm_turn pid=451) [DEBUG] 429; retry 6/6 in 310.4 seconds
(llm_turn pid=451) Unexpected error on attempt 1/3: unhandled errors in a TaskGroup (1 sub-exception)
(llm_turn pid=451) Unexpected error on attempt 3/3: unhandled errors in a TaskGroup (1 sub-exception)
```

So under sustained throttling some generation turns are being abandoned after the full 6-rung backoff and
all 3 outer attempts, and the failure surfaces only as a TaskGroup wrapper — the underlying sub-exception
is not printed. That masking is worth recording as a defect in its own right; per the campaign rules it is
documented here and not fixed.

Decision unchanged: no `ray job stop`. The 120-minute rule targets a deadlocked run idling out the window,
and this run is still starting probes and billing turns, so stopping it would discard completed work for a
condition that is throttling plus lossy retries, not deadlock. The two guard conditions that would force a
stop (billed spend above USD 190; a run that has genuinely gone quiet, billed turns included) are both
unmet: shard 1/2 stands at USD 61.61.

## Final (written after the operator stop)

Operator stop on the user's instruction at 12:24 IST 2026-09-16 (06:54:56 UTC), 11 h 53 min after the
00:31 IST launch. Job states:

- shard-0/2 (`raysubmit_cW8jPuXb25WsD3Wf`, run `f0b2ef10e17849f4b4ae45510024f96a`): was stopped
- shard-1/2 (`raysubmit_sKZprKtnd2uyj7yv`, run `db45ab7bb42f4ca3aba5985c94468dec`): was stopped
- mutation (`raysubmit_zFmMa2xyu5uWuWSL`, run `91e58983716b46e2902c01cc7cde10ab`): SUCCEEDED, `seed_set_exhausted`

Terminating condition for both seeded runs: operator stop, under the USD 175 cap and inside the 150000 s
window.

Totals at stop:

- shard 0: 23 seeds, 335 probes, 41 candidates, 4 `new`, 3 gate `report`, USD 61.16 list, 96 turns.
- shard 1: 20 seeds, 289 probes, 28 candidates, 10 `new`, 9 gate `report`, USD 61.61 list, 95 turns.
- combined: 43 of 187 seeds, 624 probes, 69 candidates, 14 distinct new fingerprints, 12 `report`,
  USD 122.77 list, 191 turns. Other latest dedup verdicts: 42 `duplicate_of_candidate`, 4 `known_open_issue`,
  7 `known_closed_issue`, 2 `fixed_post_pin`.
- mutation: 992 mutants, 592 clean exits, 400 parse errors, 0 firings.

Cluster brought down at 12:33 IST by the architect (`chia down -y circt_bug_loop/cluster_single.yaml`,
0 containers left). No repair attempted (`--no-repair`).

Anomalies stand as documented above (Vertex 429 throttling, shard 1 no new probe for over two hours while
turns still billed, retry ladder exhausting with a masked TaskGroup exception); none fixed, per the user's
instruction.
