# False-flag feature contributions and weight reduction

This investigation covers all six default-policy false flags in the 63-case phase-clean pool. It uses each case's actual held-out fold and independently reconstructs every original score. Contributions are coefficient times standardized log1p measurement, added to the intercept before the sigmoid. They explain the classifier, not the cause of the player's behavior or cheat activation.

## Each false flag

| Case | Dominant positive contributions (log odds) | Default score | Strict cutoff | Why strict clears or retains it |
| --- | --- | ---: | ---: | --- |
| D-3A | Low relative rate +1.946; small alignment error +1.165 | .743 | .889 | Below the higher cutoff |
| R-002 | Small alignment error +1.782; low relative rate +1.200 | .882 | .759 | Above its training-only cutoff |
| R-009 | Small alignment error +1.050; acceleration +.449 | .589 | .881 | Below the higher cutoff |
| L-002 | Small alignment error +1.219; low relative rate +.649 | .696 | .890 | Below the higher cutoff |
| L-013 | Small alignment error +1.053; acceleration +.373 | .524 | .884 | Below the higher cutoff |
| N-002 | Acceleration +.745; speed +.435 | .528 | .889 | Below the higher cutoff |

Negative terms/intercepts also matter; the complete signed table is saved in the local report. Alignment error is largest in four cases, relative rate in D-3A, and acceleration in N-002. Precision contributes positively because the learned alignment-error coefficient is negative: a measurement below the training mean raises the model's score.

The strict policy does not change feature weights or case scores. It changes the operating cutoff using legitimate inner out-of-group scores. Cutoffs differ by outer training set. R-002 is absent from its own training/calibration set; those remaining legitimate cases yield a lower cutoff, so it survives. This is why setting a single cutoff above every inspected legitimate case would be a misleading replacement for training-only calibration.

## Fixed weight experiment

In each outer fold, use only its saved inner out-of-group predictions. Among legitimate inner false flags, vote for the largest positive feature contribution; choose the most frequent feature (lowest index breaks ties). Halve that feature's coefficient contribution in the outer model. If there are no votes, leave the model unchanged. Keep the original intercept, other coefficients and 0.5 decision cutoff. No manual case exception, refit, damping-factor sweep or cutoff search is performed.

Sixty outer folds select alignment error; one selects relative rate. Halving a negative contribution can raise a score, so damping is not assumed to reduce every case's flag risk. This is an explicit post-fit shrinkage experiment, not input rescaling followed by an equivalent fitted weight. Scores remain uncalibrated. The hypothesis was prompted by already-inspected errors; training-only selection does not turn this into fresh evaluation.

| Policy | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default | 14 | 3 | 6 | 40 | 0 |
| Strict cutoff | 6 | 11 | 1 | 45 | 0 |
| Half selected feature weight | 11 | 6 | 4 | 42 | 0 |

Weight reduction clears R-009 and L-013, but D-3A, R-002, L-002 and N-002 remain flagged. Their adjusted scores are .618, .754, .554 and .508 respectively. It also loses three cheating-label detections. Thus the suggested change helps two default false flags but does not reach 14/17 with 1/46; it is not adopted as a replacement or selected above the strict candidate. No historical labels/models or reserved controls are changed.

A one-feature correction is insufficient here: R-002 has two strong tracking contributions, D-3A is dominated by the other tracking feature, and N-002 mainly reflects speed/acceleration. Further tuning on these same errors risks fitting their identities indirectly. Any future change must preserve training-only selection and undergo a frozen evaluation before generalization claims.

## Reproduce

```sh
python -m aimguard.feature_weight_audit \
  outputs/xguardian/expanded-phase-pool-v2 \
  outputs/xguardian/specificity-first-v1 \
  --output outputs/xguardian/feature-weight-audit-v1
```

Use a new output directory. comparison.json saves all six exact explanations, feature votes, adjusted fold parameters/scores and untouched baseline/strict results. report.md contains the signed contribution table. Source/code/protocol hashes are recorded. No demos are viewed/parsed, no reserved-control data are read and no model is frozen/deployed.
