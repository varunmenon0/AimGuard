# Fixed shallow boosted-tree experiment

Tested whether feature interactions improve the current linear classifier's ranking and low-false-flag operating point. The four measurements, original binary labels and 61 participant groups remain unchanged across all 63 inspected development cases.

## Fixed recipe

GradientBoostingClassifier with 100 stages, learning rate 0.05, maximum depth 2, minimum eight training samples per leaf, subsample 1 and random seed 0. Use log1p and inverse-frequency balanced sample weights computed only in each training fold. There is no global learned preprocessing, validation-based stopping, hyperparameter sweep or cutoff search. The decision cutoff stays 0.75, matching the fixed linear candidate.

Each fold exports the initial log-odds and every tree's children, feature thresholds and leaf values. Standalone JSON tree traversal reproduces library scores; tree inputs use float32 traversal semantics. No pickle is loaded. Single-class folds abstain; none occur in the real run.

## Result

| Policy | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Linear at 0.75 | 10 | 7 | 1 | 45 | 0 |
| Shallow boosting at 0.75 | 11 | 6 | 3 | 43 | 0 |

The tree recovers E-09 and R-023 but loses R-024, producing one net additional detection. R-002 remains falsely flagged and L-002/N-003 become additional false flags. It does not dominate the linear candidate under the user's low-false-positive priority and is not adopted or frozen.

A post-fit ranking diagnostic also fails to show a benefit: average precision decreases from 0.828 to 0.755. On these inspected held-out scores, the maximum detections attainable with at most one legitimate flag is ten for both models. This is a descriptive hindsight envelope, not a deployed cutoff or fresh evaluation; no envelope threshold is exported or selected. It helps distinguish a ranking limitation from merely using different uncalibrated score scales. Threshold 0.75 is not asserted to have identical probabilistic meaning across learners.

The existing 10/17 with 1/46 development candidate remains unchanged. It is not established population performance, and neither architecture experimentation nor a hindsight envelope meets the desired 14/17 with 1/46. Generic source labels remain distinct from verified aimbot activation. All historical/default/strict/agreement outcomes and six reserved legitimate controls remain untouched.

## Reproduce

```sh
python -m aimguard.shallow_boosting \
  outputs/xguardian/expanded-phase-pool-v2 \
  outputs/xguardian/cost-sensitive-v2 \
  --output outputs/xguardian/shallow-boosting-v2
```

Use a new output directory. protocol.json records the fixed configuration, source/code hashes and dependencies before fitting. comparison.json retains all training/held-out IDs, sample weights, tree arrays and scores. report.md contains counts. The additional local ranking-diagnostic.json was computed after fitting using average_precision_score and roc_curve on saved scores; its one-false-flag envelope is descriptive only. Raw/generated artifacts stay local and ignored; no demo parsing/viewing, new download, model deployment or holdout access.
