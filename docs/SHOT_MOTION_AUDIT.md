# Shot-timing support and recoil-field audit

This measurement audit follows the proposed second-stage corroboration approach. It first checks what the current movement measurements contain, before claiming a recoil detector or corrected aiming trajectory. All 63 development cases and 3,321 phase-clean windows are included. The six reserved controls remain untouched.

## Existing measurement support

The original speed/acceleration features use recorded yaw/pitch intervals ending within 100 ms of **any grouped shot**, including shot/post-shot motion. Acceleration requires two adjacent eligible speed intervals. On the six current false flags, 77–90% of the selected speed intervals end at or after the group's first shot. This does not establish recoil causation: those periods also contain ordinary aiming, target movement and subsequent shots.

| False flag | Speed intervals at/after first shot | Original median speed | Strict pre-first median speed |
| --- | ---: | ---: | ---: |
| D-3A | 1,954/2,524 | 12.02 | 6.12 |
| R-002 | 1,080/1,224 | 33.41 | 18.64 |
| R-009 | 1,747/1,942 | 35.76 | 25.12 |
| L-002 | 1,125/1,419 | 27.72 | 7.82 |
| L-013 | 768/924 | 50.79 | 21.95 |
| N-002 | 1,113/1,275 | 74.17 | 24.72 |

Speed is degrees/second. Strict pre-first measurements require every derivative support sample in [first shot minus 100 ms, first shot), not just the derivative endpoint. Missing support remains unavailable; there is no interpolation. Recorded tick spacing is retained. A pre-first period is not guaranteed recoil-free, particularly after earlier shots outside the current group.

## Observed recoil fields

For each false flag, probe exact selected-player ticks ±16 around the first shot in its first three chronological windows. aim_punch_angle and shots_fired are returned for all six demos, with 98–99 rows per case. All six have nonzero observed punch values. Extracted yaw/pitch reproduce canonical telemetry at float32 source precision; missing returned ticks remain explicit.

Returned punch values do not establish whether punch is already represented in recorded view angles, the required correction sign/scale, or an actual bullet/hitbox ray. No guessed subtraction/addition, eye height, head coordinates or visibility inference is applied. This is a bounded field-availability check, not rendered review or a causal recoil explanation.

## Fixed pre-first feature experiment

Replace the original two movement case medians with medians from complete strictly pre-first 100 ms windows. Require five eligible windows, preserving all cases or explicitly abstaining. Keep the original two pre-shot tracking features, participant groups, log1p/training-only scaling, balanced logistic regression C=1 and cutoff 0.5. No radius, feature, threshold or parameter sweep.

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 14 | 3 | 6 | 40 | 0 |
| Pre-first movement | 14 | 3 | 8 | 38 | 0 |

L-013 and N-002 are cleared, but D-3B, E-04, L-011 and N-003 become false flags. Positive-label decisions are unchanged. The variant worsens specificity and is rejected. Changes to first-shot/grouped-shot support and coverage mean this is a measurement-window comparison, not an isolated causal test of recoil. Removing firing-period motion this way does not solve false flags.

Historical/default/strict policies remain unchanged; no candidate is frozen/deployed and no fresh evaluation occurs. The next corroboration work needs a separately validated signal; these observed fields alone do not establish one.

## Reproduce

```sh
python -m aimguard.shot_motion_audit \
  outputs/xguardian/expanded-phase-pool-v2 \
  --output outputs/xguardian/shot-motion-audit-v1
python -m aimguard.pre_first_model \
  outputs/xguardian/expanded-phase-pool-v2 \
  outputs/xguardian/shot-motion-audit-v1 \
  --output outputs/xguardian/pre-first-model-v1
```

Use new output directories. Local audit.json retains every window's timing counts/measurements and bounded recoil-field snapshots. Protocols record source/code hashes and choices before extraction/fitting. The model experiment saves vectors, coverage, fold parameters and predictions. All generated/raw artifacts stay local and ignored; no demo viewer or game client is opened.
