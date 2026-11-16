# Post-evaluation false-flag diagnosis

The frozen candidate's fresh evaluation flagged 8/8 cheating-labeled cases and
11/16 legitimate cases. These outcomes remain unchanged. The consumed cohort can
now inform development, but cannot serve as a fresh holdout again.

## Explain the frozen computation

```sh
python -m aimguard.failure_analysis \
  outputs/xguardian/tracking-baseline-v2/frozen \
  data/external/xguardian/development-v2-manifest.json \
  outputs/xguardian/development-v2-analysis \
  outputs/xguardian/target-tracking-v4 \
  outputs/xguardian/tracking-baseline-v2/evaluation \
  --output outputs/xguardian/tracking-baseline-v2/failure-analysis

python -m scripts.render_failure_analysis \
  outputs/xguardian/tracking-baseline-v2/failure-analysis
```

The diagnostic verifies source receipts and reconstructs every evaluation score:

`margin = intercept + sum(coefficient * ((log1p(feature) - frozen_mean) / frozen_scale))`

The logistic transform produces the frozen score. Positive feature terms push the
margin toward a flag. Terms are relative to the frozen scaler's baseline; they
explain arithmetic, not causal behavior or cheating. Full-model development scores
are training explanations, not out-of-fold performance estimates.

The report compares equally weighted case-level feature distributions, retains
all evaluation decisions, and links all 24 trajectory viewers. Shared-weapon
summaries require five jointly eligible windows per case/weapon and two cases per
cohort. They are descriptive, not replacement classifier inputs or controlled
causal comparisons. No fitting, threshold sweep, feature selection, or revision
of historical predictions occurs in this command.

## Prepare the expanded inspected pool

```sh
python -m scripts.prepare_expanded_development \
  outputs/xguardian/tracking-baseline-v2/frozen \
  data/external/xguardian/development-v2-manifest.json \
  outputs/xguardian/development-v2-analysis \
  outputs/xguardian/target-tracking-v4 \
  data/external/xguardian/fresh-reserved-v2.json \
  outputs/xguardian/tracking-baseline-v2/evaluation \
  --output outputs/xguardian/development-v3
```

This creates an explicitly inspected development manifest: 41 cases, including
16 cheating labels and 25 legitimate labels, in 39 full-participant components.
Existing reports/tracking records are linked locally rather than copied or
modified. Source checksums, identities, unique targets/matches/demos, and preserved
labels are checked before output. Incomplete scored extraction is not silently
dropped. A receipt records group membership and source hashes. Original frozen
and evaluation artifacts remain intact.

## Repeat the fixed development comparison

```sh
python -m aimguard.tracking_models \
  outputs/xguardian/development-v3/manifest.json \
  outputs/xguardian/development-v3/analysis \
  outputs/xguardian/development-v3/tracking \
  --output outputs/xguardian/development-v3-models

python -m scripts.render_development_diagnostics \
  outputs/xguardian/development-v3-models
```

The existing recipes, C=1, cutoff 0.5, and eligibility rules remain fixed. Entire
participant components stay together and scaling/fitting use training groups
only. Cases are training rows; windows are not independent labels.

This comparison is development feedback after inspecting the failed evaluation.
It is not a new held-out result and does not supersede the original 11/16 false
flags. No new full-pool model is frozen or selected automatically. Better
development counts require confirmation on another genuinely fresh cohort.

## Additional inspected development cohorts

`python -m scripts.prepare_expanded_development` accepts `--additional-manifest`, `--additional-analysis` and `--additional-tracking` together. The manifest must explicitly identify inspected development data with participant identities and labels. Demo/report/telemetry/event hashes and tracking identities are checked before staging links. Duplicate case, match, selected-player or demo identities are rejected; connected participant groups are recomputed over the combined pool. Extension source hashes are retained in the pool receipt. These cases do not become a new holdout.
