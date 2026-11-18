# Supplemental frozen-model evaluation

This protocol evaluates the seven cases admitted by the short-ID identity audit
without modifying the frozen model, its 0.75 cutoff, or the original consumed
six-control reservation. The original evaluator continues to reject other
manifests; this separate evaluator explicitly binds the supplemental cases.

Run from the repository root with the existing local model and audit artifacts:

```bash
.venv/bin/python -m aimguard.supplemental_evaluation reserve \
  outputs/xguardian/offline-v06/frozen \
  outputs/xguardian/short-id-audit-v1 \
  --output data/external/xguardian/supplemental-evaluation-v1 \
  --registry data/external/xguardian/supplemental-evaluation-registry-v1

.venv/bin/python -m aimguard.supplemental_evaluation evaluate \
  outputs/xguardian/offline-v06/frozen \
  data/external/xguardian/supplemental-evaluation-v1/reservation.json \
  --output outputs/xguardian/supplemental-evaluation-v1
```

**The recorded cohort is consumed. These commands document the run, not a fresh
evaluation to repeat.** Raw data, local models and generated receipts are not
included in Git.

## Reservation and one-time use

Reservation validates the complete audit, exact replay and source-label hashes,
original consumed-control receipt, and the unchanged frozen runtime. It repeats
the full snapshot/controller identity checks with bot metadata, preserves all
account identities, rejects account overlap, and independently reproduces the
fixed one-target-per-match source-label selection.

The reservation pins the model hash, cutoff, supplemental runtime, identity
proofs, source metadata and prior exclusions. A content-derived cohort key is
independent of model name, manifest filename, demo path and case order. Its
canonical registry record also excludes these participants from later
supplemental reservations. A metadata-only exclusion receipt is added to the
existing acquisition registry, without authorizing legacy-model evaluation.

Evaluation verifies the canonical reservation and every bound runtime/source
hash and repeats metadata checks. It writes an exclusive consumption receipt
before any trajectory extraction. Errors, insufficient evidence and interrupted
runs consume the cohort too. Copying/renaming the reservation and selecting a
new output path cannot restore freshness. Normal workflow guards are not an
adversarial guarantee against deleting or deliberately replacing the registry.

Each player is passed to the unchanged frozen scorer without its source label.
Labels are attached only after prediction returns. Case errors are saved and
later cases continue. Missing evidence is unresolved, never a correct negative.
Each successful case has the existing HTML result and trajectory evidence.

## Interpretation

This is a small archive-order convenience sample with six legitimate source
labels and one generic cheating source label. The positive has no verified
active-aimbot annotation. One positive cannot establish detection performance;
six negatives cannot establish a low population false-positive rate. Conditional
statistical bounds assume representative independent correctly labeled cases,
which the convenience sample does not establish. Keep this cohort separate from
development results and the earlier six-control evaluation.

## Recorded one-time results

The unchanged model `1cc9bb01d21983c1926cd8434bfc63815d9b07343a5a7f19e56401b39286bdda`
was used at cutoff 0.75. This supplemental cohort is now consumed.

| Case | Source label | Score | Decision |
| --- | --- | ---: | --- |
| I-001 | Legitimate | .0237 | Not flagged |
| I-002 | Legitimate | .6574 | Not flagged |
| I-003 | Legitimate | .4772 | Not flagged |
| I-004 | Legitimate | .2269 | Not flagged |
| I-005 | Cheating | .9111 | Flag for review |
| I-006 | Legitimate | .7175 | Not flagged |
| I-007 | Legitimate | .0867 | Not flagged |

Result: **0/6 legitimate false flags; 1/1 cheating-labeled case flagged**.
All seven were scored, with no extraction errors or insufficient-evidence
outcomes. There are 374 live windows, 365 eligible for tracking features.
All seven retain round-event warnings, visible in the evidence reports.
No model, source recipe or threshold was changed after seeing these results.

Even with zero observed legitimate errors, the conditional one-sided exact 95%
upper false-positive bound for six independent representative cases is about
39.3%. Convenience sampling further limits interpretation. Do not present the
single positive as an established 100% detection rate, confirmed active-aimbot
detection, or pool development results into an independent evaluation metric.

The local evaluation directory contains per-case HTML evidence, labeled
results, report and verification. Independent checks reproduced every score
directly from frozen coefficients/scalers, checked contributions, source/model
hashes and consumption-before-extraction ordering, verified acquisition
exclusions, and confirmed a renamed reservation fails before new extraction.
Both historical frozen runtimes still pass integrity checks.
