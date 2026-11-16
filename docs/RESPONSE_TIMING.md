# Pre-shot response timing experiment

This rejected development experiment tests new temporal evidence rather than another classifier on the same four summaries. It does not replace the baseline or claim an achieved detection fix.

## Fixed measurement

For the fixed geometric opponent selected at the tick before the first shot, retain consecutive same-segment yaw/bearing angular rates in the preceding 500 ms, ending exactly one tick before the shot. The first rate requires its preceding sample inside the retained segment. No post-shot sample, interpolation or alternate-opponent selection is used.

Compare Pearson correlations of yaw rate at tick t with opponent bearing rate at t, t minus 100 ms, and t plus 100 ms. The lag is rounded to the nearest replay tick (six ticks at 64 Hz). All three comparisons use the same central ticks, with at least eight triplets. Each series must have standard deviation at least 1 degree/second; otherwise this measurement is unavailable. These are fixed, unvalidated coverage choices, not optimized cheat criteria. Constant angle holding cannot become zero-delay evidence.

Three case measurements are medians across at least five eligible windows: zero-lag correlation, zero minus delayed correlation, and zero minus leading correlation. Append them to the original four log1p features; keep correlations signed and untransformed. Use training-only scaling, balanced logistic regression C=1, cutoff 0.5 and the same 53 participant groups. No lag, cutoff, feature or hyperparameter search is performed.

This geometric lead/lag correlation is not causal response latency or raw mouse input. Opponent bearing includes shooter translation; endpoint opponent selection does not verify visibility, actual intended target or cheat activation. All 55 cases have already been inspected, so grouped results are development diagnostics only.

## Result

1,496 windows have response coverage. All 55 cases retain at least five; no case abstains.

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase-clean baseline | 13 | 3 | 6 | 33 | 0 |
| Baseline plus response timing | 12 | 4 | 9 | 30 | 0 |

All six original false flags persist. D-3B, R-013 and R-015 become additional false flags, while R-022 becomes a miss. Median case zero-lag correlation is approximately 0.0097 for cheating labels and 0.0143 for legitimate labels. These medians are descriptive, not a statistical separation test. This fixed temporal signal did not improve discrimination and is rejected. Source labels and current/historical models remain unchanged.

## Reproduce

```sh
python -m aimguard.response_timing \
  outputs/xguardian/v06-development-v1/comparison \
  --output outputs/xguardian/response-timing-v2
```

Use a new output directory. protocol.json records choices, dependencies and code/source hashes before fitting. inputs.json retains the new vectors and coverage; comparison.json saves original predictions and candidate fold parameters; report.md summarizes results. Tracking inputs are verified against saved hashes and original tracking features. No demo parsing or viewing is required. All generated outputs stay local and ignored by Git; no model is frozen or deployed.
