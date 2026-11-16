# Phase-clean grouped learning curves

The curves ask whether the current fixed model improves as more of the available development cases are used. They do not estimate performance beyond this pool, establish a sample-size requirement, or evaluate a newly acquired holdout. No demos are parsed or viewed.

## Fixed experiment

Use the saved 55 eligible phase-clean vectors, original labels and 53 participant groups. For each held-out group, select random whole-group training prefixes at 20%, 40%, 60%, 80% and 100% of the other groups. Ten seeds use nested prefixes within each seed/fold, without selecting seeds by performance. The full-size model runs once per fold. Test labels never choose training subsets. Fit log1p plus training-only scaling and balanced logistic regression C=1 at cutoff 0.5; no hyperparameter, feature or cutoff search occurs.

Single-class training subsets abstain without resampling. Report their coverage separately; rates use scored cases only. A held-out case appears once per repeat. Training curves average fold-level training rates; held-out curves pool the held-out cases within each repeat. Seeds and overlapping folds are correlated. Shaded min/max ranges show sensitivity to training subsampling, not confidence intervals, and collapse at the full-size point because only one fit per fold is needed.

## Results

| Mean training cases | Training groups | Held-out detection mean | Held-out false-positive mean | Abstentions per repeat |
| --- | ---: | ---: | ---: | ---: |
| 10.3 | 10 | 73.6% | 23.8% | 0–3 |
| 20.7 | 20 | 80.6% | 16.9% | 0 |
| 32.1 | 31 | 83.1% | 15.6% | 0 |
| 42.5 | 41 | 81.9% | 15.9% | 0 |
| 54.0 | 52 | 81.2% | 15.4% | 0 |

The full-size scores reproduce the saved TP13/FN3/FP6/TN33 baseline. Its training fit averages 83.1% detection and 13.2% false positives, close to held-out performance and still unsatisfactory. Mean training size varies slightly by held-out group because two groups contain two cases.

There is an early improvement, followed by little further change over the larger sizes. This supports investigating limitations of the current features/model and labels alongside collecting data. It does not prove a permanent plateau or show that a substantially larger, more diverse dataset cannot help. The smallest point also has changing scored denominators; interpret it together with abstentions rather than as complete coverage.

For the low-false-positive goal, this curve supplies no evidence that simply adding more examples of the same four measurements will reach the target. More diverse reliably labeled cases and a genuinely untouched grouped evaluation remain valuable, but no gain is promised. The fixed 0.5 operating point is unchanged; these are not ROC or cutoff-selection curves.

## Reproduce

```sh
MPLCONFIGDIR=/private/tmp/aimguard-mpl python -m aimguard.learning_curves \
  outputs/xguardian/v06-development-v1/comparison \
  --output outputs/xguardian/learning-curves-v2
```

Use a new output directory. protocol.json records the fixed design, source hashes, code hash and dependencies before fitting. curves.json saves each subset, fold scaler, coefficients, training/held-out scores, coverage and summary. learning-curves.png is the standalone plot; report.md contains the table. Source comparison receipts are verified and the full-size curve must reproduce every saved baseline score. No replacement model is frozen or deployed. All generated artifacts remain local and ignored by Git.
