# Phase-clean error investigation

This is an explanation of saved v0.6 development predictions, not a new detector or evaluation. All 55 cases were already inspected. The underlying result remains TP13/FN3/FP6/TN33 with no abstentions. No fitting, cutoff change, exclusion filter or relabeling is performed.

## Method

Reconstruct the four-feature log-odds contribution terms with each case's own held-out fold, including the intercept. Find nearby correctly classified training cases using that fold's standardized log1p feature space. Label and correctness are used explicitly to select descriptive controls; these controls are not independent validation evidence. Report the nearest correct control overall and separately by label.

Recompute feature medians for each round and weapon subset with the existing minimum of five eligible tracking windows. Apply the whole-case held-out fold descriptively. These context scores overlap, are not calibrated probabilities or new predictions, and cannot establish cheat activation. Missing coverage remains unavailable, not a low score. Saved report/tracking/input receipts, feature vectors and whole-case predictions must reconstruct before output is accepted.

## Findings

| Case | Error | Whole-case score | Nearest correctly classified control | Distance |
| --- | --- | ---: | --- | ---: |
| D-2A | Miss | 0.099 | L-009, legitimate | 0.323 |
| D-3A | False flag | 0.751 | R-023, cheating | 0.692 |
| E-05 | Miss | 0.105 | E-07, legitimate | 0.558 |
| R-002 | False flag | 0.894 | E-10, cheating | 0.509 |
| R-009 | False flag | 0.598 | R-015, legitimate | 0.455 |
| R-012 | False flag | 0.514 | L-010, legitimate | 0.536 |
| R-020 | Miss | 0.468 | L-010, legitimate | 0.450 |
| L-002 | False flag | 0.712 | E-09, cheating | 0.385 |
| L-013 | False flag | 0.556 | R-006, legitimate | 0.534 |

Distances are descriptive, with no validated similarity cutoff. The overlap is in the current four measurements, not proof that the players' underlying actions are equivalent.

Small pre-shot horizontal error supplies the largest positive term in five of the six false flags; D-3A instead has relative angular rate as its largest positive term. The classifier rewards precision that legitimate players also exhibit. D-2A's relative-rate term is strongly negative, while E-05's error term is strongly negative. These explain the model's decisions without establishing whether the source labels identify active aimbot use at any particular moment.

Context does not supply an obvious safe fix:

- D-3A exceeds 0.5 in four of seven scorable rounds. Its AWP and SSG08 subsets also score highly, so repeated high scores can occur in a legitimate case.
- R-002 scores 0.959 on both Glock and silenced M4 subsets. The false flag is not confined to a sniper weapon.
- L-002's AWP subset scores 0.985, but missed R-020's AWP subset also scores 0.925. Excluding a weapon category would discard evidence from both labels.
- D-2A has one of four scorable rounds above 0.5; E-05 has two of ten; R-020 has five of thirteen. Whole-match medians can obscure within-match variation, but isolated high context scores do not demonstrate activation or a reliable detection rule.
- Only 33/39 legitimate cases and 16/16 cheating cases have a scorable round. R-012 has none. A new round-vote policy would change coverage and requires explicit abstention handling and a separate, fixed development experiment.

The next useful work is a bounded event comparison across errors and matched controls, separating geometric candidate selection from actual visibility and intended targets. Existing browser reconstructions can provide limited context, but cannot certify visibility or activation. Avoid repeating the rejected stable-alignment filter or treating simple persistence/weapon exclusions as established improvements.

## Reproduce

```sh
python -m aimguard.phase_errors \
  outputs/xguardian/v06-development-v1/comparison \
  outputs/xguardian/v06-development-v1/analysis \
  --output outputs/xguardian/v06-errors-v2
```

Use a new output directory. Local audit.json contains all 55 cases, 9 errors, feature contributions, correctly classified controls, coverage and round/weapon context scores. report.md and index.html provide readable results. Demos and generated artifacts remain local and ignored. Historical decisions and frozen model remain unchanged.
