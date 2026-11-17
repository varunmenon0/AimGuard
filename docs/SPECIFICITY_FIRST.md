# Specificity-first operating policy

The user explicitly prioritizes avoiding legitimate flags over detecting most cheating-labeled cases, accepting fewer than ten detections among seventeen positives. This supersedes the earlier objection to conservative cutoffs. Source subtype uncertainty remains; this policy evaluates binary source labels, not confirmed active aimbots.

Revisit the existing nested conservative recipe on the expanded phase-clean development pool. Keep the four features, training-only log1p/scaling, balanced logistic regression C=1 and original 61 participant groups. For each outer held-out group, generate inner leave-one-group-out scores from outer training cases only. Set the cutoff to the largest legitimate inner score, then flag strictly above it after refitting on outer training cases. Incomplete calibration abstains. Outer held-out features/labels cannot select the cutoff. No cutoff grid, arbitrary case exclusion or feature search is performed.

## Result on inspected development cases

| Policy | Detected / cheating labels | False flags / legitimate labels | Abstentions |
| --- | ---: | ---: | ---: |
| Existing cutoff 0.5 | 14/17 | 6/46 | 0 |
| Training-only conservative cutoff | 6/17 | 1/46 | 0 |

R-002 remains a legitimate false flag. Five previous false flags are corrected, at the cost of eight additional misses. This is closer to the user's desired tradeoff but is not a solution: 1/46 is still 2.17% observed false positives on inspected cases, not evidence of near-zero population FPR. No case-specific blacklist, manually fitted threshold above held-out negatives, or all-abstain policy is introduced.

Training-only calibration cannot guarantee zero errors on new legitimate behavior. Inner models differ from the final outer refit, and the small negative pool does not represent all legitimate play. These overlapping grouped diagnostics have no independent binomial confidence claim. Existing subtype descriptions and historical results are unchanged.

The result is a development candidate, not a frozen/deployed replacement. The six reserved legitimate controls remain unextracted/unscored, and must not select a new cutoff. The next diagnostic is the surviving outlier's failure mode, not a special exemption for its identity or a hidden tuning loop. Any candidate needs a frozen single-use evaluation protocol and more independent legitimate cases before a low population FPR claim.

## Reproduce

```sh
python -m aimguard.specificity_policy \
  outputs/xguardian/expanded-phase-pool-v2 \
  --output outputs/xguardian/specificity-first-v1
```

Use a new output directory. Source receipts and fixed protocol are checked/saved before calibration. All inner/outer case IDs, scalers, coefficients, scores and cutoffs remain in local comparison.json; report.md provides the summary. No demos are parsed/viewed, no reserved-control files are read and no original artifacts are overwritten.
