# Repeated pre-shot correction consistency

This offline development experiment tests a measurement hypothesis: repeated, similarly shaped corrections might distinguish suspicious behavior from accurate legitimate alignment. It does not use the conservative cutoff policy. That policy remains an unadopted experiment.

## Fixed measurement

The fixed geometric opponent and contiguous 500 ms pre-shot segment are inherited from acquisition dynamics. The segment must end exactly one tick before the first shot and contain at least 16 intervals. Missing samples, segment changes and horizontal angle branch crossings are excluded without interpolation.

A transition requires at least three degrees of both net alignment improvement and player-supported closure. Support is the minimum of observed improvement and the improvement the recorded yaw step would produce with opponent bearing held fixed. Opponent-only movement through a stationary crosshair does not qualify. This construction is a geometric proxy; it does not identify actual mouse input or a validated intended target.

For qualifying transitions, signed relative angular velocity is fitted to previous signed horizontal error through the origin. Fit strength is conventional centered R-squared, clipped to [0,1]. Constant-response or zero-error regressions are unavailable rather than perfect fits. Positive gain means a proportional tendency toward alignment. Case features are:

- Median R-squared among positive-gain fits.
- Median absolute deviation of positive gains, divided by their median, measuring cross-window variation.
- Positive-fit count divided by valid pre-shot window count.

At least five valid windows and three positive-gain fits are required per case; insufficient coverage abstains. Fit quality is retained even when poor, rather than selecting favorable windows with a tuned R-squared cutoff. These choices are unvalidated engineering hypotheses fixed before this experiment. No eligibility, parameter, feature-subset or flag-cutoff search is performed.

## Development comparison

Case rows are equally weighted. Complete connected replay-participant groups are held out. Scaling and C=1 balanced logistic regression use training cases only; cutoff stays 0.5. The standalone recipe uses the three new features. The combined recipe appends them to the two pre-shot tracking features. Existing speed/tracking predictions are copied unchanged for context.

All 55 inspected cases have coverage: 3,219 valid pre-shot windows and 826 qualifying positive-gain transitions. Missing coverage therefore does not explain the negative result.

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Existing speed + tracking | 13 | 3 | 5 | 34 | 0 |
| Correction consistency | 13 | 3 | 7 | 32 | 0 |
| Tracking + consistency | 13 | 3 | 6 | 33 | 0 |

Median case gain variation is 0.419 in cheating-labeled cases and 0.424 in legitimate cases. Median case R-squared is 0.0134 versus 0.0: most corrections do not follow this simple proportional-response shape well. The measurements did not produce useful specificity. Both recipes add false flags without improving aggregate cheating-label recall, so neither is adopted or frozen. The historical independent evaluation remains unchanged. This result rejects these particular measurements and aggregation, not all possible temporal approaches.

## Local reproduction

```sh
python -m aimguard.correction_consistency \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  --output outputs/xguardian/correction-consistency-v2
python -m scripts.render_development_diagnostics outputs/xguardian/correction-consistency-v2
```

Use a new output directory. Protocol and source hashes are recorded before fitting. Input receipts include every window's measurement or exclusion, first-shot tick and weapon; coverage, group membership, fold training identities, coefficients and scores are preserved locally. No raw data or generated output is committed.

Tests recover a known synthetic proportional gain, reject opponent-only/static alignment and angle-wrap events, preserve pre-shot-only behavior, handle constant regressions and missing samples, and abstain on insufficient transitions. Source cheating labels remain coarse and do not establish whether aimbot was active. Visibility, eye/head geometry, recoil and intended-target ambiguity remain unresolved. Future candidates require both discrimination on development errors and genuinely untouched evaluation; current results do not justify an operational detector.
