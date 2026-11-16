# Fixed shrinkage joint-distribution model

This is a rejected development experiment, not a replacement detector. Learning curves and saved-fold error explanations suggested investigating feature interactions: the original logistic model adds four standardized log measurements, while correlated speed/acceleration and error/relative-rate combinations could require a different boundary.

## Fixed candidate

Use the same 55 phase-clean cases, four measurements, original binary labels and 53 participant groups. Each leave-one-group-out training fold fits log1p and StandardScaler, then a separate multivariate Gaussian per class. Ledoit–Wolf shrinkage estimates class covariance from training cases only, without a hyperparameter search. Eigenvalues have a fixed numerical floor of 1e-6 in standardized space. Both class priors are 0.5, preserving the balanced baseline's equal-class decision convention rather than claiming realistic cheating prevalence.

The decision margin is log density under the cheating class minus log density under the legitimate class; flag at zero. Its sigmoid is an uncalibrated equal-prior model score, not a real-world cheating probability. Covariance needs at least two training cases per class; otherwise abstain. Missing input evidence also abstains. No cutoff, feature, regularization or seed search is performed. Source receipts and protocol are recorded before fitting; every fold saves training/held-out IDs, scaler, means, covariances and shrinkage.

## Result

| Model | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase-clean linear baseline | 13 | 3 | 6 | 33 | 0 |
| Shrinkage joint model | 13 | 3 | 11 | 28 | 0 |

All six existing false flags persist. E-04, R-005, R-013, L-005 and L-010 become additional false flags. R-020 is recovered but R-023 becomes a miss, leaving recall unchanged. This candidate worsens specificity, so it is rejected. It does not fix the model and must not replace the baseline or revise its historical evaluation. No frozen/deployed model is changed.

The negative result rejects this particular interaction recipe on inspected development data. It does not prove that all interaction models fail. Further searches on these same cases can manufacture apparent gains; any future candidate still requires reliably labeled, untouched grouped evaluation. Current generic cheating labels also do not establish aimbot activation. No demo viewing is required or claimed here.

## Reproduce

```sh
python -m aimguard.joint_model \
  outputs/xguardian/v06-development-v1/comparison \
  --output outputs/xguardian/joint-model-v2
```

Use a new output directory. Local protocol.json, inputs.json, comparison.json, changed-cases.json and report.md preserve the complete experiment. All generated artifacts stay local and ignored; source, tests and documentation are committed. The historical modules and data remain unchanged.
