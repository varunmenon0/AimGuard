# Frozen tracking candidate workflow

The four-feature candidate combines near-shot p95 angular speed and mean absolute
speed acceleration with pre-shot horizontal error and relative angular velocity.
It uses log1p, development-fitted scaling, balanced logistic regression C=1, and
cutoff 0.5. This workflow locks that recipe before fresh feature extraction.
The earlier 6/8 cheating flags and 0/9 false flags are development results, not
independent evaluation results or calibrated probabilities.

## Freeze from the recorded comparison

Use Python 3.12 and the same dependency versions as the comparison. Inputs and
outputs below are local and excluded from Git. Choose a new frozen directory.

```sh
python -m aimguard.tracking_baseline freeze \
  data/external/xguardian/development-v2-manifest.json \
  outputs/xguardian/development-v2-analysis \
  outputs/xguardian/target-tracking-v4 \
  outputs/xguardian/tracking-models-v1 \
  --exclude-demo data/raw/your-end-vs-damajuana-m1-cache.dem \
  --exclude-demo data/raw/your-end-vs-damajuana-m2-ancient.dem \
  --exclude-demo data/raw/your-end-vs-damajuana-m3-mirage.dem \
  --output outputs/xguardian/tracking-baseline-v2/frozen
```

Freezing verifies comparison receipts, feature settings, dependencies, and
unchanged feature code. The tracking extractor was refactored into one shared
single-case function. Every development replay must reproduce its complete saved
tracking record and feature values before fitting; a refactor cannot silently
change the candidate. The full model is then fitted on the 17 development cases.
Its training scores are not reported as evaluation performance.

The output contains `model.json`, `model.sha256`, and
`extraction-equivalence.json`. Model JSON records features, eligibility rules,
configuration, timing assumption, scaler, coefficients, cutoff, source hashes,
runtime versions, development provenance, and participant exclusions. Loading
rejects changed code, Python/dependency versions, parameters, or protocol.

Previously inspected demos outside the training pool must also be supplied with
`--exclude-demo`. Identity metadata uses the union of player-info and the complete
identity-only tick stream, including disconnected/replaced players. No view-angle
or position properties are requested for participant checks. This also handles
older demos with empty player-info tables. Exclusions cover every recorded
participant, not just selected targets. They cannot account for undisclosed prior
inspection or alternative accounts.

## Select fresh candidates using metadata only

Do not adjust model settings after looking at evaluation scores. Define a sample
size and selection rule using source metadata before feature inspection. Include
both labels and enough legitimate matches to investigate false flags. Convenience
samples do not establish population-wide accuracy. Keep rounded source-label ID
mapping caveats; hash checks do not independently verify annotation correctness.

Create a local candidate manifest with this structure, replacing placeholders
with real checksums and documented labels:

```json
{
  "role": "evaluation_candidates",
  "features_inspected": false,
  "selection": "Describe the metadata-only sampling rule here",
  "caveats": ["Document label scope, source precision and sampling limitations"],
  "cases": [
    {
      "steamid": "76561198000000001",
      "match_id": "source-match-id",
      "label": "legitimate",
      "features_inspected": false,
      "demo": "fresh-match.dem",
      "demo_sha256": "<SHA-256 of the demo>",
      "source_label_file": "source-labels.csv",
      "source_label_sha256": "<SHA-256 of the source label file>"
    }
  ]
}
```

Demo and label-file paths may be absolute or relative to the candidate manifest.
`features_inspected: false` is an explicit declaration, not proof of non-use.
Labels must be `cheating` or `legitimate`; SteamIDs must be exact positive strings.
Source labels describe a selected player in a match, not assisted ticks.

```sh
python -m aimguard.tracking_baseline reserve \
  outputs/xguardian/tracking-baseline-v2/frozen \
  data/external/xguardian/fresh-candidates.json \
  --output data/external/xguardian/fresh-reserved.json
```

Reservation verifies source hashes, target identity, and complete participant
metadata without extracting movement features. It rejects any participant,
match, or demo overlapping recorded inspected cases, duplicate targets, or shared
participants between evaluation matches. Rejected candidates are not silently
removed or replaced. The caller must record any revised metadata-only selection.

The reserved manifest and adjacent `.sha256` bind cases to the frozen model.
A registry inside the frozen model directory records all reservations and rejects
re-reserving those cases or participants under a different filename. Keep this
registry with the model; do not delete receipts to treat used cases as fresh.

## Evaluate once

```sh
python -m aimguard.tracking_baseline evaluate \
  outputs/xguardian/tracking-baseline-v2/frozen \
  data/external/xguardian/fresh-reserved.json \
  --output outputs/xguardian/tracking-baseline-v2/evaluation
```

Preflight repeats source, runtime, participant, and reservation checks. A central
exclusive start receipt consumes the reservation before feature extraction, with
copies adjacent to the manifest and in the output directory. Copying a manifest
does not bypass the central receipt. Analysis errors and interruptions do not
restore fresh status. An interrupted run requires investigation; its cases must
not be presented as a new untouched evaluation.

Evaluation does not fit or tune anything. It runs the frozen gameplay and tracking
extractors, validates windows, applies the locked coverage rules, and computes
the exported logistic score. Each case writes a prediction or an explicit
abstention. `evaluation.json` contains confusion counts, analysis coverage,
abstentions by label, exact binomial intervals, hashes, and uncertainty notes.
Rates are conditioned on successful analysis; inspect abstentions separately.
All evaluation matches have disjoint recorded participants, but source sampling
can still violate statistical independence assumptions.

After observing results, any further tuning makes those cases development data.
Fresh evidence is needed for another performance claim. This workflow remains
an offline research tool; visibility, vertical/hitbox geometry, recoil, and
lag/subtick corrections remain unresolved. It does not establish aimbot-specific
sensitivity or support automatic enforcement.
