# Regenerated v0.6 development comparison

This workflow rebuilds engagement groups and features after explicit match-phase gating. It differs from the earlier phase audit, which dropped entire legacy windows touching warmup. Historical reports and frozen models remain unchanged.

The input is the previously inspected 55-case development pool, with its original labels and 53 connected participant groups. This is a development diagnostic, not a fresh test set. Use the same four measurements (speed, acceleration, horizontal pre-shot error and relative angular rate), log1p, training-fold scaling, balanced logistic regression C=1 and cutoff 0.5. No cutoff, feature or eligibility search is performed. Cases with fewer than five eligible tracking windows abstain.

Create a phase-batch jobs JSON in manifest order, containing each case's demo path, exact SteamID string and tickrate. Then run:

```sh
python -m aimguard.phase_batch outputs/xguardian/v06-development-jobs.json \
  --output outputs/xguardian/v06-development-v1/analysis
python -m aimguard.phase_development \
  outputs/xguardian/development-v4 \
  outputs/xguardian/v06-development-v1/analysis \
  outputs/xguardian/development-v4-models \
  --output outputs/xguardian/v06-development-v1/comparison
```

Use new output directories. The comparison validates manifest/baseline receipts and original participant groups, source identities/hashes, extraction runtime hashes, explicit v0.6 version/policy/configuration and exported live window support. Tracking is re-extracted from the demos for the new windows; old window numbers are not reused. Source and code hashes, dependencies, feature vectors, coverage and fold parameters are saved. Legacy feature readers still reject v0.6; this workflow has its own explicit version reader and does not masquerade as a frozen extractor.

Batch round-event warnings remain visible. Structural extraction success does not establish visibility, intended targets or cheat activation. No replacement model is frozen or deployed by this command. Raw replays, tracking and generated reports remain local and ignored by Git.

## Completed development run

The full 55-case extraction completed with zero errors and zero structural window violations. All 55 cases retain existing round-event warnings. It published 3,018 live windows and excluded 230,640 formerly active warmup samples. All cases retain at least five eligible pre-shot tracking windows; there are no abstentions.

| Input protocol | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Preserved legacy | 13 | 3 | 5 | 34 | 0 |
| Regenerated v0.6 | 13 | 3 | 6 | 33 | 0 |

The v0.6 development false-positive fraction is 6/39 (15.4%), which is far above the intended low-false-flag goal. False flags are D-3A, R-002, R-009, R-012, L-002 and L-013. Misses are D-2A, E-05 and R-020. R-012 is the only flag changed from legacy. No improvement in detection is established.

On this pool, regenerated feature vectors match the earlier drop-whole-window phase audit; these remain distinct extraction procedures and need not match on future boundary cases. Every saved prediction was independently reproduced from fold coefficients/scalers. Training-only scaling, participant separation, code/input receipts and legacy frozen-runtime integrity were checked. No source labels changed. These inspected grouped diagnostics are not independent generalization estimates.

The next investigation should compare errors against controls using the phase-clean inputs and remaining review intervals, with browser reconstruction limitations preserved. No model promotion or favorable cutoff search follows from this result.
