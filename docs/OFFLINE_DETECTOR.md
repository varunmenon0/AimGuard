# Frozen v0.6 offline player review

The offline command accepts a CS2 demo and exact player SteamID, extracts phase-clean gameplay and pre-shot tracking, and produces a review-priority score plus supporting evidence. It uses the original four-feature balanced logistic candidate with fixed cutoff 0.75. The score is uncalibrated and the source task is generic cheating, not verified active-aimbot detection.

## Score a replay/player

With the local frozen artifact available:

```sh
python -m aimguard.offline_detector score \
  outputs/xguardian/offline-v06/frozen \
  path/to/match.dem \
  --steamid 76561199104430312 \
  --output outputs/player-review
```

Use a new output directory. This recipe assumes 64 Hz; other timing assumptions require a separately defined model. Open result.html for the decision, score/threshold, coverage and link to analysis/review.html. prediction.json retains the feature vector, signed model contributions, intercept, warnings and model/source/report/tracking hashes. tracking.json and analysis artifacts retain the underlying evidence.

Decisions are flag_for_review, not_flagged and insufficient_evidence. A flag requests investigation; a non-flag does not certify legitimate play. Missing/insufficient coverage has no score or boolean classification. An extraction failure raises an error instead of issuing a clean verdict. Round-event warnings remain visible.

The input replay is unlabeled during scoring. Known evaluation labels are joined only after inference by the evaluation workflow, never passed into feature selection or fitting.

## Freeze a compatible local model

```sh
python -m aimguard.offline_detector freeze \
  outputs/xguardian/expanded-phase-pool-v2 \
  outputs/xguardian/cost-sensitive-v2 \
  outputs/xguardian/tracking-baseline-v2/frozen \
  --output outputs/xguardian/offline-v06/frozen
```

The freeze command rejects reused destinations; validates source/reference receipts; reproduces all 63 stored vectors from report/tracking inputs; checks demos and participant identities; and recomputes the connected participant partition. It then fits the unchanged balanced C=1/log1p/training-scaled classifier once on the full development pool. Full-fit export must reproduce library scores. The source legacy bundle supplies additional inspected participant exclusions; it is not changed.

The artifact pins 16 local source modules, Python version, dependency versions, phase policy, configuration and threshold. Scoring refuses mismatched code/runtime/recipe or model checksum. Code changes require a newly prepared compatible artifact; never silently rewrite a frozen model. Data/model artifacts are intentionally local and not included in Git. A fresh clone needs the appropriate local training/data artifacts and recorded runtime versions to reproduce this model.

The recorded artifact has 63 development cases (17 cheating labels/46 legitimate) in 61 participant groups. Its model SHA-256 is `1cc9bb01d21983c1926cd8434bfc63815d9b07343a5a7f19e56401b39286bdda`. Historical grouped development at the same recipe/cutoff is 10/17 detected with 1/46 false flags; that is not the full-fit model's independent detection result.

## Single-use reserved evaluation

```sh
python -m aimguard.offline_detector evaluate \
  outputs/xguardian/offline-v06/frozen \
  data/external/xguardian/expansion-cohorts-v1/holdout.json \
  --output outputs/xguardian/offline-v06/holdout-evaluation
```

**This cohort has already been consumed by the recorded run below. Do not run it again as fresh evaluation.** The command will refuse its existing consumption receipt. Copying or renaming data does not make it uninspected again.

The model is bound to the original reservation checksum before extraction. The evaluator validates untouched metadata, demo/label hashes, exact targets and full participants against inspected exclusions and other cohort cases. It writes an exclusive holdout.consumed.json before feature extraction, including cases where extraction later fails. Reuse at the original manifest is blocked even with a new output/model. Each case outcome is saved immediately; errors and insufficient evidence remain unresolved while later cases continue. The original metadata snapshot remains immutable; its historical uninspected declaration is superseded by the consumption receipt.

## Recorded unseen legitimate check

All six reserved legitimate cases were scored once using the frozen artifact:

| Case | Score | Decision | Live windows |
| --- | ---: | --- | ---: |
| H-001 | .0362 | Not flagged | 36 |
| H-002 | .4793 | Not flagged | 51 |
| H-003 | .5102 | Not flagged | 35 |
| H-004 | .6427 | Not flagged | 60 |
| H-005 | .0038 | Not flagged | 27 |
| H-006 | .4985 | Not flagged | 48 |

Result: **0 false flags among 6 scored legitimate cases**, no errors or insufficient-evidence outcomes; 257 live windows. Sixty participants are disjoint from training/previous inspected exclusions and one another across these six matches. All six retain round-event warnings, which are visible in their reports. No model or threshold was adjusted after these results.

This is a small archive-order convenience sample with the original source-label/identity limitations. It does not measure detection because no cheating-labeled case is present. It does not establish zero or near-zero population FPR. Even under independent representative correctly labeled sampling, zero errors in six gives a one-sided exact 95% upper bound around 39.3%; convenience sampling further limits that interpretation.

Local evaluation.json/report.md and per-case result.html retain the results. The verification receipt checks frozen full-fit parameters, all new vectors/scores and report links, disjoint participants, consume-before-extract ordering, consistent model identity and rejection of reuse. A separate development-replay smoke reproduces all four original features end to end; it is not a fresh performance estimate. Historical v0.5 models/evaluations and all earlier development results remain intact. All raw/generated data stay local and ignored; no game client, demo viewer or upload is used.
