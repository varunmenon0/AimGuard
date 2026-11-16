# Geometric candidate ambiguity audit

This post-feedback diagnostic asks whether the existing horizontal candidate selection creates false flags by choosing among nearly tied opponents or frequently switching identities just before a shot. It fits no models, introduces no candidate filter, and changes no predictions.

## Fixed diagnostic sample and extraction

The sample contains all five shared legitimate false flags, all three current linear-model false negatives, three fixed unflagged legitimate controls, and three fixed flagged cheating-labeled controls. All windows in each selected case are included: 14 cases and 853 windows. Controls were chosen after prior error inspection; this is a descriptive sample, not a representative performance estimate.

The recorded case order is D-3A, R-002, R-009, L-002, L-013, D-2A, E-05, R-020, R-007, R-012, D-3B, E-10, R-017 and D-1A. The protocol is saved before sparse extraction.

For each first shot, the audit requests exact snapshots one tick before firing and 100/200 ms earlier, rounded to ticks. Earlier snapshots must stay inside the original window. All valid alive opposing players are ranked by absolute horizontal bearing-to-yaw error, with SteamID tie-breaking. Local death events are latched consistently with canonical tracking. No position, angle or missing snapshot is interpolated.

The audit verifies replay/report/tracking/telemetry/event hashes and source identities, reproduces shooter telemetry at source precision, and requires each endpoint candidate to match canonical saved tracking. All 853 selections reproduce, including six matching unavailable endpoints. There are 847 available endpoint candidates.

Measurements include runner-up angular separation, candidate count, whether the endpoint-selected opponent was also nearest earlier, and its earlier excess error over the earlier nearest opponent. Missing opponents/pairs remain unavailable, rather than counted as switches. A single-opponent snapshot has no runner-up gap; that is not a zero gap.

## Findings

For the five legitimate false flags:

| Case | Median runner-up gap | Same nearest opponent 200 ms earlier |
| --- | ---: | ---: |
| D-3A | 9.37° | 93.9% |
| R-002 | 7.75° | 83.3% |
| R-009 | 10.46° | 85.7% |
| L-002 | 18.88° | 90.9% |
| L-013 | 15.63° | 84.6% |

Across these five cases, the median of case-median runner-up gaps is 10.46°, and the median case stability fraction is 85.7%. The three missed cheating cases have corresponding descriptive summaries of 18.53° and 95.1%. Legitimate controls are 14.89°/95.8%; cheating controls are 19.88°/89.7%. These summaries weight cases equally and do not imply significance or target-selection accuracy.

Frequent near-tie switching is not supported as the main shared error explanation in this sample. Most endpoint selections in the false-flag cases were already nearest earlier, and median runner-up gaps are substantial. An ambiguity filter is therefore not adopted based on this audit. No thresholds were searched to remove known legitimate errors.

This does not validate intended targets, visibility, eye/head geometry, or the measured tracking features as cheat-specific evidence. A geometrically stable opponent can still be irrelevant or occluded. Medians do not rule out individual ambiguous windows. The audit narrows one hypothesis rather than proving the true cause of false flags.

## Local reproduction and review

```sh
python -m aimguard.candidate_audit \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  --output outputs/xguardian/candidate-ambiguity-v1
python -m scripts.render_candidate_audit outputs/xguardian/candidate-ambiguity-v1
```

Choose a new output directory. Each case retains ranked candidates, exact ticks, window associations and comparison availability. The receipt-checked HTML index links per-window tables and existing local trajectory reviews. The renderer does not extract, fit or change decisions. Demos, player identities, snapshots and generated reports remain ignored local files.

Tests cover deterministic ties, alive/team/death filtering, exact-tick requirements, angle wrapping, fixed endpoint identity comparisons, missing-pair denominators, single-opponent gaps, duplicate identities, escaped review fields and tampered receipt rejection. All canonical candidate matches and frozen runtime integrity were independently verified. The conservative cutoff and prior rejected temporal recipes remain inactive; historical evaluation is unchanged.


The optional `--all-cases` flag audits every inspected manifest case in manifest order, rather than the fixed selected sample. The explicit case list and selection scope are recorded before extraction. Output case IDs must be unique safe filename identifiers. The encounter-filter experiment requires this complete cohort; the selected 14-case audit cannot be substituted for it.
