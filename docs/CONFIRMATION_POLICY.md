# Two-stage agreement policy

This fixed policy follows the user's request to test confirmation after the burst-feature experiment swapped false flags. It combines saved predictions only, without refitting, changing cutoffs or inspecting reserved controls. The hypothesis is post-feedback development work, not independent evaluation.

## Rule and validation

Use the original-four-feature **matched-coverage baseline** and the burst-augmented model from burst-recoil-v2. Both use identical eligible cases, training/held-out participant groups and cutoff 0.5. The full-pool model's differently trained predictions are retained as a historical reference, not silently mixed into this matched comparison.

- Both stages flag: issue a flag.
- Both stages do not flag: record not_flagged, not a certification of legitimate play.
- Either direction of disagreement: unresolved review.
- Missing evidence in either stage: unresolved review.

Review has no boolean clean/cheating verdict. The implementation verifies training/held-out partitions, participant isolation, training scalers and every saved score before combining decisions. The stages share input features and training data; agreement is correlated, not independent evidence or a calibrated confidence boost.

## Results across all 63 cases

| Source label | Flag | Not flagged | Review: disagreement | Review: missing evidence |
| --- | ---: | ---: | ---: | ---: |
| Cheating | 13 | 3 | 0 | 1 |
| Legitimate | 3 | 36 | 6 | 1 |

Remaining legitimate flags: D-3A, R-002 and L-002. Disagreement reviews: R-005, R-009, R-012, L-013, N-001 and N-002, all source-labeled legitimate. Missing evidence: D-1A (cheating label) and R-008 (legitimate label). The previously detected D-1A is unresolved, not a successful negative. Only 55 of 63 receive non-review decisions.

| Policy | Cheating-labeled flags | Legitimate flags | Unresolved reviews |
| --- | ---: | ---: | ---: |
| Historical full-pool default | 14/17 | 6/46 | 0 |
| Matched-coverage baseline | 13/17 | 6/46 | 2 missing |
| Agreement rule | 13/17 | 3/46 | 8 total |

All-case flag fractions retain every case in the denominator. A reduced 3/46 flag fraction is not proof of 6.5% population FPR, nor proof that the seven legitimate review cases are safe. Ten legitimate cases require flagging or review, versus six flags under the full default. Thus the rule reduces firm false flags while increasing unresolved review workload. It does not meet the 14/17 with 1/46 goal, and is not frozen/deployed as a replacement.

No source labels, historical predictions, default/strict policy or six reserved legitimate controls are changed. No demo is parsed/viewed. Further refinement must not simply pick the remaining three identities to exempt; any new policy needs its own fixed design and eventual frozen evaluation with adequate independent controls.

## Reproduce

```sh
python -m aimguard.confirmation_policy \
  outputs/xguardian/burst-recoil-v2 \
  --output outputs/xguardian/confirmation-policy-v1
```

Use a new output directory. protocol.json preserves the rule and source/code hashes. result.json contains both original scores, triage decision and explicit review/label accounting for every case. report.md provides the table and flagged/review case list. All generated artifacts stay local and ignored by Git.
