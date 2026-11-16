# Server-flag phase-quality audit

Browser timeline alignment exposed a source-quality defect: the legacy active-round/life rules can retain pre-match warmup. Direct replay extraction confirms a D-1A shot at tick 788 has warmup=true and match-started=false, whereas later competitive examples have the opposite flags. This is not the rejected stable-alignment filter.

## Explicit phase gate

The new audit checks every original supporting telemetry tick for every engagement, using `is_warmup_period` and `CCSGameRulesProxy.CCSGameRules.m_bHasMatchStarted`. These global flags repeat across players; repeated rows are collapsed per tick only when boolean values agree. Missing columns, missing ticks, conflicting flags and non-boolean values remain unknown rather than being coerced to live.

A window passes only when every supporting tick explicitly reports warmup=false and match-started=true. Boundary windows touching warmup are excluded in full; they are not silently trimmed while retaining stale trajectory features. This gate supplements the original round/life/firearm rules and does not claim to resolve every round-event anomaly or every game phase.

The module exposes tested phase helpers and creates a phase-checked development feature path. Existing extractor modules and historical artifacts are preserved for frozen-runtime reproducibility. The legacy gameplay/batch commands are not silently upgraded by this audit; further feature work must explicitly use the phase-checked inputs. A future canonical extractor/version migration must retain this guard and keep old frozen inputs incompatible with a changed protocol. No old model is silently applied to altered inputs.

## Results on the inspected pool

All 55 cases and all 3,323 original windows were checked. Warmup affects 37 cases:

| Window status | Count |
| --- | ---: |
| Pass explicit phase gate | 3,018 |
| Warmup | 305 |
| Unknown | 0 |

The phase-checked case vectors use the same component-wise speed/acceleration and pre-shot tracking medians, original participant groups, training-only scaling, log1p, C=1 balanced logistic regression and cutoff 0.5. At least five eligible tracking windows remain required; all cases are covered. There is no parameter, cutoff or feature search.

| Development recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Preserved legacy inputs | 13 | 3 | 5 | 34 | 0 |
| Phase-checked inputs | 13 | 3 | 6 | 33 | 0 |

Cleaning the data does not solve false flags. R-012 becomes an additional false flag; the other errors remain. R-002 had no warmup windows, so warmup contamination cannot explain that specific error. Phase exclusion is a source-validity requirement, not a performance-selected feature, and should not be rolled back simply because this small development count looks worse. Historical outcomes remain truthful descriptions of the legacy protocol; they are not revised into better-looking live-only results.

No replacement model is frozen or deployed, and no new independent evaluation is claimed. The next modeling comparison should use the phase-checked data and continue prioritizing specificity.

## Reproduce

```sh
python -m aimguard.phase_audit \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  --output outputs/xguardian/phase-checked-v1
python -m scripts.render_development_diagnostics outputs/xguardian/phase-checked-v1
```

Use a new output directory. Original replay/report/telemetry/event/tracking checksums and identities are checked, and every window retains source-phase sample counts and status. Missing phase coverage excludes the window; insufficient case coverage abstains rather than assigning a legitimate label. The saved source/runtime hashes and parser versions allow the audit to be reproduced locally. No original files are modified.

Tests cover repeated global fields, warmup/live boundaries, explicit match-start requirements, missing/conflicting/string flags and invalid tick support. Saved predictions can be reconstructed from the phase-checked case vectors and recorded fold coefficients/scalers. The original baseline and frozen runtime remain intact.
