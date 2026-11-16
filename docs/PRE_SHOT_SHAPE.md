# Target-independent pre-shot trajectory shape

This experiment tests the shooter's two-axis view-angle path before firing, without selecting an opponent. Earlier horizontal accuracy models overflag legitimate play, and candidate-switching diagnostics did not explain the shared errors. The hypothesis is that path shape may distinguish how alignment is achieved rather than how accurately the player aligns.

## Fixed measurements and eligibility

Use the contiguous active segment ending exactly one tick before the first shot, limited to the preceding 500 ms and the original window. Require 16 consecutive intervals, finite yaw/pitch, playable pitch, the original alive segment, positive health and an active playing team. Missing or invalid samples break continuity; they are not interpolated. No opponent identity, damage recipient, hit selection or post-shot observation enters extraction.

Reuse the existing two-axis core extractor without modifying it. The four per-window measurements are path efficiency (net displacement/total path length), mean angle between successive movement steps, speed coefficient of variation, and stop fraction using the existing 2 degrees/second definition. Yaw uses shortest wrapped increments; pitch does not wrap. Stationary aim retains the core's defined values and is not declared suspicious by a separate rule.

A case requires five eligible windows. Case features are medians, with insufficient coverage causing explicit abstention. Models use log1p, training-fold scaling and C=1 balanced logistic regression at cutoff 0.5. Whole connected participant components are held out. One recipe uses shape alone; another appends shape to the existing four speed/tracking measurements. Eligibility, feature list, hyperparameters and cutoff are fixed before fitting; no search is performed.

## Development result

55 inspected cases, 16 cheating labels and 39 legitimate labels, in 53 participant components. There are 3,240 eligible windows and 83 excluded windows; every case has sufficient coverage.

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing speed + tracking | 13 | 3 | 5 | 34 | 0 |
| Pre-shot shape | 11 | 5 | 11 | 28 | 0 |
| Speed + tracking + shape | 13 | 3 | 5 | 34 | 0 |

Unchanged totals in the combined recipe conceal changed cases: legitimate R-009 is corrected but L-005 becomes a false flag; missed cheating case R-020 is recovered but R-024 becomes a miss. The result does not demonstrate an improvement in specificity. Neither new recipe is adopted or frozen. The conservative cutoff remains inactive, and historical frozen evaluation is unchanged.

The combined recipe's overlapping errors also show that adding plausible whole-match movement summaries is not enough. These view angles are server-observable telemetry, not raw mouse input; quantization, player skill and ordinary corrections may create similar shapes. Generic cheating labels do not establish active aimbot use or time-local activation. The negative result does not rule out all trajectory methods, but it provides no evidence supporting this recipe's adoption.

## Reproduce locally

```sh
python -m aimguard.pre_shot_shape \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  --output outputs/xguardian/pre-shot-shape-v1
python -m scripts.render_development_diagnostics outputs/xguardian/pre-shot-shape-v1
```

Use a new output directory. Source identities, report/telemetry/event/tracking hashes, case labels, participant groups and prior comparison receipts are checked. Protocol is recorded before feature extraction/fitting. All window measurements/exclusions, case vectors, training folds, coefficients and scores remain in ignored local outputs. All 110 new predictions independently reconstruct from saved calculations; original predictions and frozen runtime integrity pass verification.

Tests cover known straight and reversing paths, stationary pre-aim, yaw wrapping, pre-shot-only invariance, invalid/missing/alive-segment samples, insufficient intervals/windows, invalid tickrate and duplicate telemetry. Results remain post-feedback development diagnostics, not an independent accuracy estimate.
