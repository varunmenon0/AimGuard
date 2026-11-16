# Exploratory pre-shot acquisition dynamics

This is a recorded negative development experiment. It does not replace the
frozen candidate or revise its failed fresh evaluation. All 41 cases have already
been inspected and are development feedback, not a reusable holdout.

## Hypothesis and fixed measurements

The earlier model overflags ordinary acceleration and precise alignment. This
experiment asks whether concentrated alignment changes followed by reduced motion
are more specific measurements than precision alone.

The opponent is selected geometrically at the exact tick before the first shot.
Only a contiguous segment ending at that tick is used, within the preceding
500 ms and with at least 16 intervals. Missing samples, changed segment IDs, and
invalid endpoints prevent coverage; no interpolation or post-shot samples are used.

For each interval, observed closure is the positive reduction in absolute
horizontal error. View-only closure asks how much the recorded yaw step would
reduce the previous error if the opponent bearing were fixed. Player-supported
closure is the minimum of those positive quantities. Opponent movement alone
therefore does not create a qualifying transition, aside from negligible floating
roundoff. This is a geometric construction, not causal attribution to mouse input
or a verified intended target.

A transition requires both net error reduction and total supported closure of at
least three degrees. Concentration is the largest interval's supported closure
divided by the total. Settling ratio is median relative angular speed strictly
after that interval divided by its relative speed. At least three later pre-shot
intervals are required; missing settling remains unavailable rather than zero.
Equal closure peaks select the first interval.

A case needs five valid pre-shot windows and three transitions with observable
settling. Features are transition fraction, median concentration, and median
settling ratio. The combined recipe appends these to the original two tracking
features. Both use log1p, training-fold scaling, balanced logistic regression C=1,
and cutoff 0.5. The engineering cutoffs are unvalidated choices fixed before this
fit; no eligibility, feature-subset, parameter, or threshold search was performed.

## Reproduce

```sh
python -m aimguard.acquisition_dynamics \
  outputs/xguardian/development-v3 \
  outputs/xguardian/development-v3-models \
  --output outputs/xguardian/acquisition-dynamics

python -m scripts.render_development_diagnostics \
  outputs/xguardian/acquisition-dynamics
```

Choose a new output directory. Inputs, source hashes, fixed protocol, feature
vectors, exclusions, group membership, fold scalers/coefficients and predictions
are retained locally. Baseline predictions are copied unchanged from the verified
41-case comparison. Runtime dependencies are recorded. Changed baseline protocols,
case labels, group membership, or source receipts fail verification.

## Recorded result

All 41 cases, in the same 39 participant components, had sufficient coverage.
There are 2,508 valid windows, 613 qualifying transitions and 560 with observable
settling. Every case has at least three usable transitions. No case abstained.

| Recipe | Cheating labels flagged | False flags among legitimate cases |
| --- | ---: | ---: |
| Pre-shot tracking | 13/16 | 3/25 |
| Speed plus tracking | 13/16 | 3/25 |
| Acquisition dynamics | 13/16 | 4/25 |
| Tracking plus dynamics | 13/16 | 5/25 |

Case-level median concentration is 0.14996 for cheating labels and 0.15196 for
legitimate labels. Median settling ratios are 0.17586 and 0.16276, respectively.
These overlapping sample summaries do not demonstrate useful specificity. The
new recipes add false flags without more cheating-label flags in this experiment,
so neither is adopted or frozen. This does not rule out other temporal methods;
it records that these particular measurements/aggregation did not help.

A second run added input/protocol guards and corrected a synthetic test's
exact-zero expectation for floating roundoff. It reproduced all predictions,
scalers and coefficients exactly, with the same feature recipe and cutoffs.
The original frozen fresh evaluation remains 8/8 cheating labels flagged and
11/16 legitimate false flags.

Visibility, vertical/hitbox geometry, recoil, timing and intended-target ambiguity
remain unresolved. Legitimate flicks can also produce rapid alignment and quiet
aim. Cases are not frame-level cheat activation annotations. Another genuinely
fresh cohort will be required for a future performance claim after development.
