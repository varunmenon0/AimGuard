# Fixed nonlinear offline development comparison

The existing four-feature logistic model assumes an additive decision boundary after log transformation and scaling. This experiment tests one RBF support-vector classifier on exactly the same case measurements and participant folds. It checks whether nonlinear feature interactions help, without introducing new geometric assumptions.

The recipe is fixed: log1p, training-fold StandardScaler, RBF kernel, C=1, balanced training-class weights, and gamma=1/(four times the training-scaled variance), falling back to 1 for constant training data. The flag cutoff is decision margin zero. No probability calibration, parameter search, feature search, cutoff search or full-pool model fit is performed. Margins are not cheating probabilities.

## Local reproduction

After preparing the inspected development pool and canonical tracking comparison:

```sh
python -m aimguard.nonlinear_models \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  --output outputs/xguardian/nonlinear-v2
```

Use a new output directory. The command checks manifest/baseline receipts, recorded full-participant group membership, source report/telemetry/event and tracking hashes, labels, identities and reproduced tracking features. Missing window coverage abstains explicitly. Protocol and inputs are saved before fitting; each fold records training/held-out cases, scaler statistics, kernel width, support-vector case IDs, dual coefficients and intercept. These permit independent reconstruction of every decision margin. The existing linear predictions are copied unchanged.

## Result

55 inspected cases, 16 cheating labels and 39 legitimate labels, in 53 connected participant groups:

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing linear speed + tracking | 13 | 3 | 5 | 34 | 0 |
| Fixed RBF speed + tracking | 12 | 4 | 5 | 34 | 0 |

The nonlinear recipe missed one additional cheating-labeled case and corrected none of the five false flags. It is not adopted or frozen. This result does not establish that nonlinear models cannot work; this fixed recipe did not improve the development outcome. Additional parameter searches on this small inspected pool would risk misleading gains.

The local report includes errors and changed decisions, with links to existing trajectory review pages. The same five legitimate cases were flagged by both models. Source labels identify cheating at player/match level, without aimbot activation annotations. Visibility, intended target, eye/head geometry and recoil limits remain unresolved. These are development diagnostics after inspecting prior outcomes; the historical independent frozen evaluation remains unchanged.

Tests check held-out group exclusion from scaling/kernel/support vectors, independent reconstruction of decision margins, coverage and single-class abstention, constant input handling, invalid data, and tampered/uninspected source rejection. The 55 real development margins were independently reproduced to numerical precision, and frozen runtime integrity was rechecked. All raw and generated artifacts remain local.
