# Final bounded error audit: retain the frozen model

The requested last tuning pass is complete. **Keep the existing model and 0.75
cutoff.** One fixed movement-smoothing candidate produced no extra detections
and more false flags in development, so it was rejected. No new model was
exported or promoted. No further tuning is part of this pass.

The latest unseen result remains **4/5 cheating-labeled cases flagged and 1/50
legitimate controls falsely flagged**, with all 55 scored. These are the
observed small-cohort results, not established population rates or confirmed
active-aimbot sensitivity. That cohort remains consumed.

## False flag: B1-F-013

The source-labeled legitimate player's score was .9654372. All 59 windows were
live and eligible. Frozen features reproduce exactly from the saved inputs.

| Feature | Value | Signed log-odds contribution |
| --- | ---: | ---: |
| Near-shot p95 angular speed | 57.4844 deg/s | +.1935 |
| Near-shot mean absolute acceleration | 1853.5384 deg/s² | +1.7009 |
| Median pre-shot absolute horizontal error | .7398 degrees | +2.2928 |
| Median pre-shot absolute relative rate | 9.8643 deg/s | −.1421 |

The main drivers are tight alignment and high acceleration, rather than strong
relative-motion coupling. Acceleration exceeds every case in the 63-case
training pool; horizontal error is below every training legitimate case. The
model extrapolates toward its positive class on this new legitimate example.

Median near-shot held-view fraction is .488. The representative curve shows
held updates interspersed with movement, with a speed spike after firing.
Such recording patterns can amplify measured acceleration; they do not prove
a fixed client update rate, recording fault, recoil causation or assistance.
Across the case, 1602/1897 near-shot acceleration samples occur at or after
the first shot. This timing describes support, not a causal recoil correction.

The geometric candidate agrees with the sole observed damage recipient in
21/22 such windows. Candidate identity changes between the pre-shot and shot
tick in 12/59 windows. Neither statistic establishes visibility or true aim
intention, but there is no obvious widespread identity-association failure.
No geometric exclusion, damage-conditioned detector or case-specific exemption
was added.

## Unflagged positive: P-SHARED-002

The generic cheating-labeled player's score was .6149253. All 60 windows were
live and eligible, with no feature reproduction failure.

| Feature | Value | Signed log-odds contribution |
| --- | ---: | ---: |
| Near-shot p95 angular speed | 32.8576 deg/s | −.0203 |
| Near-shot mean absolute acceleration | 500.8286 deg/s² | +.1479 |
| Median pre-shot absolute horizontal error | 1.6475 degrees | +.8954 |
| Median pre-shot absolute relative rate | 8.7383 deg/s | +.1604 |

These features provide a weaker combined signal than the policy requires.
The candidate agrees with the sole damage recipient in 34/35 such windows;
candidate identity changes at the first shot in 14/60 windows. Median held-view
fraction is .231. The source label does not identify cheat subtype or active
aimbot intervals, so the curves cannot establish why the label is positive or
whether aim assistance was active. The label and verdict remain unchanged.

## The one fixed candidate

Motivated by the repeated view updates, tested a fixed two-tick angular-velocity
average followed by acceleration at its actual one-tick spacing. This replaces
only the two movement features; the two original tracking features remain.
No interpolation, guessed recoil subtraction, lag/feature/threshold grid or
case-specific rule is used.

The comparison uses the original 63 inspected development cases and 61
participant groups, with training-fold log1p/scaling, balanced logistic
regression C=1 and the unchanged .75 cutoff. Nonconsecutive or short windows
are excluded explicitly, leaving 3207/3321 candidate movement windows. Every
case retains at least five windows; no cases abstain. These are matched cases,
with the stricter window support part of the candidate recipe.

| Development inputs | TP | FN | FP | TN | Unresolved |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 10 | 7 | 1 | 45 | 0 |
| Fixed two-tick movement | 10 | 7 | 2 | 44 | 0 |

Original scores reproduce the stored reference exactly. The candidate fails
the recorded non-regression policy. It was not applied to the consumed 55
cases, so no updated test accuracy or correction of these two errors is
claimed. The diagnostic hypothesis was informed by consumed data; even a
favorable development result would require fresh evaluation before promotion.

Early preparation attempts stopped before fitting on unsupported window gaps
and mixed numeric/named group keys. The completed run records explicit support
exclusions and preserves all group identities. This was one completed candidate
comparison, not a parameter search.

## Artifacts and verification

```bash
MPLCONFIGDIR=/private/tmp/aimguard-mpl .venv/bin/python -m aimguard.final_error_audit \
  outputs/xguardian/mixed-grouped-v1/evaluation \
  outputs/xguardian/offline-v06/frozen \
  --output outputs/xguardian/final-error-audit-v1

.venv/bin/python -m aimguard.two_tick_development \
  outputs/xguardian/expanded-phase-pool-v2 \
  outputs/xguardian/cost-sensitive-v2 \
  --output outputs/xguardian/two-tick-development-v3
```

These outputs already exist; use new directories to reproduce diagnostics.
The error audit reads saved reports/tracks/telemetry only. Its representative
curves minimize standardized log-feature distance to each player's case
medians, avoiding a search for the most dramatic window. See the local
`final-error-audit-v1/curves.png`, audit.json and report.md.

All 415 tests pass. Four new tests verify physical units, wrap handling,
held-update behavior, gap rejection and named-group partition integrity.
Independently refitted all 122 original/candidate fold models and verified
training-only scalers, held-group exclusions and every score/decision.
Both frozen runtimes and all consumed-cohort source/runtime receipts remain
unchanged. No replay download, gameplay viewing, label change, fresh evaluation,
consumed-case candidate scoring or model promotion occurred. All generated
artifacts remain local and ignored.
