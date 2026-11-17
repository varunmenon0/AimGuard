# Same-weapon burst dynamics experiment

This fixed development experiment extends the shot-level field audit to longer time-grouped firing sequences. It does not establish a physical recoil correction or an achieved reduction in false flags.

## Definition and measurement

Within each published live engagement, split consecutive shots at gaps exceeding 200 ms. Retain groups of at least three shots. These are same-weapon burst proxies, not verified automatic firing or continuous trigger presses. Require every exact tick from first shot minus one through last shot plus two to remain in the same live segment, with an unchanged matching equipped weapon. No interpolation or guessed punch correction is used. Re-extracted view angles must reproduce canonical telemetry at float32 precision.

Compute recorded pitch/yaw view increments V and punch-component0/1 increments P, with wrapped yaw differences. Require at least eight intervals and nonzero view/punch energy. Measurements are opposing projection gain `-sum(V·P)/sum(P²)`, relative fitted residual `sum((V+gain*P)²)/sum(V²)`, and global component cosine. These describe co-variation, not raw mouse input, actual compensation, bullet direction or activation. Residual equals `1-cosine²`; these are related representations, not three independent signals.

Take componentwise case medians over at least five valid bursts. Append the three signed measurements to the original four log1p features, then fit training-only scaling and balanced logistic regression C=1/cutoff0.5 in the existing participant groups. No threshold, burst gap, feature or parameter sweep. Baseline and new features are correlated; no independent-evidence multiplication is performed. Weapon context is held constant within each burst, but no cross-weapon calibration is claimed.

## Coverage and outcome

1,493 candidate burst proxies yield 1,326 valid measurements. There are 144 outside-live-segment exclusions, 19 insufficient-variation exclusions and four changed/mismatched-weapon exclusions. D-1A and R-008 have only four valid bursts each, below the minimum, and abstain. This notably loses coverage for one of the two author-described aimbot cases; missing coverage must not appear as a successful clean classification.

A matched baseline is refitted using the original four features on the same eligible cases/groups, so changes in the eligible training pool do not masquerade as feature effects.

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original full pool | 14 | 3 | 6 | 40 | 0 |
| Original features, matched coverage | 13 | 3 | 6 | 39 | 2 |
| Original plus burst features | 13 | 3 | 6 | 39 | 2 |

Both matched models score sixteen cheating-labeled and forty-five legitimate cases. Added features clear R-009, L-013 and N-002 but newly flag R-005, R-012 and N-001. Covered positive-label decisions are unchanged. There is no aggregate specificity gain, and full-pool coverage worsens. The variant is not adopted or frozen.

The remaining default/strict results and six reserved legitimate controls are unchanged. These are inspected development diagnostics, not independent aimbot-specific performance. The finding rejects this measurement/aggregation/model recipe; it does not prove that all temporal recoil analysis is ineffective. Swapping false flags is insufficient justification for another fitted cutoff on these same cases.

## Reproduce

```sh
python -m aimguard.burst_recoil \
  outputs/xguardian/expanded-phase-pool-v2 \
  --output outputs/xguardian/burst-recoil-v2
```

Use a new output directory. Protocol records source/code hashes, dependencies and fixed choices before extraction. Case JSON files retain observed fields, every burst measurement or exclusion, and weapon coverage. inputs.json retains signed/mixed-transform vectors and groups; comparison.json saves original/matched/candidate fold models. report.md provides the summary. No game client/viewer is opened; raw/generated artifacts remain local and ignored. The earlier v1 run lacked the separately refitted matched-coverage baseline; v2 is the final comparison.
