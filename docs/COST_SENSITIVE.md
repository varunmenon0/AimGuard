# Fixed specificity-oriented loss and operating-point comparison

The next experiment changes the training objective rather than adding measurements. It uses the same 63 phase-clean development cases, four original features and 61 participant groups. All results are inspected development diagnostics; source labels are generic cheating labels, not verified active-aimbot labels.

## Fixed training change

Inside each outer training fold, start with inverse-frequency balanced sample weights. Multiply legitimate-case weights by three, then normalize all weights to mean one. Total weight remains the number of training cases, preserving the scale of C=1 regularization. The legitimate class receives 75% of total loss weight and the cheating class 25%, versus 50/50 for the original model. This is a class-total weighting ratio, not a claim that every individual false positive has exactly three times every individual false negative's cost.

Keep original log1p measurements, unweighted training-only StandardScaler, logistic regression C=1 and decision cutoff 0.5. Labels outside the training fold cannot choose weights or fit any parameters. No cost, feature, C or threshold grid is searched. Single-class training partitions abstain, though none occur in this real run.

## Analytical operating-point reference

After the first weighted fit, added a comparison using the original model with threshold `3/(1+3)=0.75`, derived from the same already-fixed 3:1 ratio. It was not selected by sorting held-out negatives or searching scores. This is an analytical reference for shifting equal-class score odds toward the legitimate class; uncalibrated original scores do not guarantee a probability-calibrated cost optimum. It is not an independently preregistered validation after the initial fit, and the whole pool was already inspected.

| Policy | TP | FN | FP | TN | Abstentions/reviews |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original model at 0.5 | 14 | 3 | 6 | 40 | 0 |
| Original model at fixed 0.75 | 10 | 7 | 1 | 45 | 0 |
| Weighted refit at 0.5 | 10 | 7 | 2 | 44 | 0 |

Weighted training retains false flags D-3A and R-002. The derived-cutoff reference retains only R-002. Neither changes the available evidence or source labels. The original model's ranking is unchanged by a threshold change; this is a different recall/false-flag operating point, not a stronger ranking model.

The fixed 0.75 candidate detects ten of seventeen source positives with one of forty-six legitimate cases falsely flagged, without sending any cases to review or treating missing evidence as clean. It improves detection over the previously recorded strict policy's 6/17 at 1/46 on these inspected cases. It still misses seven positives and does not reach the desired 14/17 with 1/46. One observed false flag among 46 is not evidence of near-zero population FPR.

No existing policy or frozen/deployed model is overwritten. The six reserved legitimate controls remain untouched. A sensible next milestone is to freeze a phase-clean candidate and its single-use evaluation protocol before extracting/scoring those controls; six cases alone cannot establish a low population error rate.

## Reproduce

```sh
python -m aimguard.cost_sensitive \
  outputs/xguardian/expanded-phase-pool-v2 \
  --output outputs/xguardian/cost-sensitive-v2
```

Use a new output directory. protocol.json records the fixed weight ratio, normalization, analytical-control provenance, source/code hashes and dependencies before the final comparison. comparison.json preserves original predictions, weighted training IDs/labels/weights, scalers, coefficients and all decisions. report.md summarizes outcomes. No raw replay parsing/viewing, downloads or reserved-control reads occur. All generated/raw artifacts stay local and ignored.
