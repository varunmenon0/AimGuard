# Cross-fitted multi-family evidence score

This experiment implements the user's proposed multi-factor review-priority score. It groups existing measurements instead of treating correlated inputs as independent proofs. The resulting score is not a calibrated cheating probability or an activation label.

## Evidence and missingness

Four families are used: movement (original speed/acceleration), pre-shot tracking (alignment error/relative rate), same-weapon burst co-variation, and pre-shot response timing. Original movement/tracking values use log1p; signed burst/response features are left untransformed. These are complementary hypotheses, not independent sensors. Burst data are unavailable for D-1A and R-008 under the fixed five-burst rule; missingness remains explicit. Encounter visibility and actual intended targets are not newly verified or added.

Each family has its own training-scaled balanced logistic model, C=1. A second balanced logistic model learns group-score weights from margins plus four missingness indicators, with training-only scaling. Family coefficients and meta weights are learned without a hyperparameter grid. Every outer participant group is excluded from all training, imputation and fitting. Inside each outer training set, group-separated cross-fitting produces the margins used to train the meta model; fitted family training scores are not substituted for these margins. Families are then refitted on outer training data only for the outer prediction.

Missing margins use the mean of available cross-fitted training margins plus an explicit indicator. That is a learned missingness representation, not clean evidence. A case with fewer than two available family models abstains. The present dataset has at least three available families for every case, so all 63 receive scores. Correlation is handled through joint regularized fitting, not a claim of statistical independence or guaranteed elimination of double-counting.

Score equals 100 times the final logistic output. At the fixed 50-point boundary it produces a development flag; no cutoff is chosen from inspected outcomes. No review band or new firm-positive policy is silently introduced.

## Result

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original model | 14 | 3 | 6 | 40 | 0 |
| Multi-family score | 11 | 6 | 9 | 37 | 0 |

The new score worsens detection and false flags, so it is not adopted or frozen. The original, strict and agreement-policy results remain unchanged. Neither source labels nor the six reserved controls are changed or consumed.

A post-fit descriptive ranking check also worsens: average precision 0.828 → 0.668; among the top ten ranked inspected cases, original scores retrieve nine cheating labels/one legitimate label, versus seven/three for the new score. These review budgets are descriptive, not selected thresholds or an independent evaluation. The original top-ten result must not become a claimed 9/17-at-1/46 deployable policy by selecting its cutoff on this same pool.

The four families were derived from previously investigated measurements and already-inspected cases; combining them does not create new ground truth or a fresh holdout. A small meta-training pool and overlapping features remain limitations. This result rejects the fixed scoring recipe, not every possible multi-factor architecture. Adding more channels is not itself evidence of stronger discrimination.

## Reproduce

```sh
python -m aimguard.evidence_score \
  outputs/xguardian/expanded-phase-pool-v2 \
  outputs/xguardian/burst-recoil-v2 \
  --output outputs/xguardian/evidence-score-v2
MPLCONFIGDIR=/private/tmp/aimguard-mpl python -m scripts.render_evidence_score \
  outputs/xguardian/evidence-score-v2
```

Use a new output directory. protocol.json records the fixed architecture, dependencies and source/code hashes. inputs.json retains every family and coverage. comparison.json stores all outer and inner partitions, fitted family/meta parameters, cross-fitted margins, imputation means, explicit inputs and eight contribution terms per scored case. report.md lists scores and availability. ranking.json/png provide the post-fit ranking comparison. All artifacts stay local and ignored; no game viewer, raw demo parsing or new download is required by this workflow.
