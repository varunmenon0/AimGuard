# Shared errors and false-positive-first development

Offline scope remains demo analysis. Current development diagnostics contain 16 cheating-labeled and 39 legitimate cases in 53 connected participant groups. Neither the existing linear model (13 TP, 3 FN, 5 FP, 34 TN) nor the fixed nonlinear comparison meets the low-false-positive objective.

## What the shared errors show

All five legitimate false flags receive their largest positive margin contribution from pre-shot horizontal error or yaw-minus-bearing velocity. These describe accurate horizontal aim and tracking; they do not establish cheating. Four are dominated by low horizontal error, while one is dominated by relative velocity. Speed/acceleration is not the principal positive contribution in these five decisions.

The strongest legitimate flag scores 0.891, above eleven of the sixteen cheating-labeled cases. Its three nearest training feature neighbours include two cheating cases and another legitimate false flag. The three missed cheating cases have nearest legitimate neighbours at standardized log-feature distances of approximately 0.31, 0.91 and 0.30. These descriptive comparisons indicate feature overlap, not causal explanations or proof about player behavior.

Chronological summaries also overlap. One missed cheating-labeled case has half-match scores 0.827 and 0.001; a legitimate false flag has 0.262 and 0.960. A whole-match median can conceal temporal differences, but merely flagging a high-scoring stretch would also flag legitimate play. Half-match scores are descriptive applications of the existing outer fold model, not independent predictions or aimbot activation annotations. No half-based classifier or label has been introduced.

A post-hoc look at the existing grouped scores shows that a common cutoff including the fourteenth cheating case (score 0.4353) would still include the same five legitimate flags. This is a description of inspected scores, not a selected deployment cutoff. Raising the cutoff above every observed legitimate score would leave only five cheating cases. Threshold adjustment does not fix the ordering of overlapping cases.

## Conservative policy experiment

A single fixed policy was specified before fitting:

1. Hold out an entire participant component as the outer test group.
2. Within the remaining cases, generate inner leave-one-participant-component-out scores using the unchanged four-feature, log1p, training-scaled, C=1 balanced logistic model.
3. Set the outer cutoff to the maximum legitimate inner out-of-group score. Flag strictly above this cutoff. Incomplete inner calibration abstains instead of substituting fitted training scores.
4. Fit the unchanged classifier on all outer training cases and score the untouched outer test group.

Outer held-out labels and features cannot enter inner calibration, scaling, or fitting. No cutoff grid, feature search, parameter search or full-pool fit is performed. This policy has no population FPR guarantee: the inner training models differ from the final outer refit, and the legitimate sample is small.

Result: **TP5, FN11, FP1, TN38, zero abstentions**. The strongest legitimate outlier remains flagged because, when it is held out, training data do not represent that outlier well enough. This does not meet the intended false-positive/recall goals; the policy is not promoted or frozen. The former independent frozen evaluation remains unchanged.

## Why the base rate matters

As an illustration, assume 1% of players cheat and recall is 81.25%. The fraction of flags identifying cheating would be:

| Population FPR | Fraction of flags identifying cheating |
| --- | ---: |
| 10% | 7.6% |
| 1% | 45.1% |
| 0.1% | 89.1% |

These are arithmetic scenarios, not measured deployment prevalence or performance. Even a small-looking FPR may leave admins reviewing mostly legitimate players.

For independent representative legitimate cases with zero false flags, a one-sided exact 95% upper bound at 1% requires 299 cases; at 0.1%, 2,995. This follows `(1-FPR)^n <= 0.05`. Current inspected grouped-CV cases are not independent binomial trials, and cannot establish either bound.

## Reproduce locally

```sh
python -m aimguard.error_audit \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  --output outputs/xguardian/shared-error-audit-v3
python -m scripts.render_error_audit outputs/xguardian/shared-error-audit-v3
```

Use a new output directory. Source identities, manifest/report/tracking/telemetry/event receipts and reproduced original grouped scores are checked. Protocol is saved before calibration. All outer/inner training identities, parameters, scores and cutoffs are recorded. Explanations use fold identity matched by case ID; prediction order need not equal manifest order. Each explanatory score must reproduce the original held-out score, and a case cannot appear in its explanatory training neighbours. The local HTML report links errors to existing trajectory reviews. Raw data and generated reports remain local.

No new reliable cheat-specific signal has been established by this audit. Horizontal nearest-opponent selection, unvalidated visibility/eye/head geometry, recoil, coarse cheating labels, and whole-match aggregation remain limits. Future feature work must distinguish the shared legitimate errors from cheating cases, and any candidate needs a new untouched evaluation with enough legitimate controls. Lowering the threshold to claim fourteen detections would not satisfy the low-false-positive requirement.
