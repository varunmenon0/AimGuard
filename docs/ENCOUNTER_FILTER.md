# Stable-prealignment exclusion and repeated encounter support

This experiment tests the proposed idea of skipping already-aligned encounters and examining evidence across multiple rounds. The test is reversible and isolated from the original detector. No stable geometric configuration is assumed to establish legitimate behavior.

## One fixed hypothesis

Exclude a window only if all three exact pre-shot snapshots (one tick before firing, 100 ms earlier and 200 ms earlier) meet these conditions:

- The same geometric opponent is nearest in all three snapshots.
- Absolute horizontal error is at most 3 degrees in every snapshot.
- Runner-up separation is at least 3 degrees in every snapshot, or only one valid opponent exists.

Unknown or ambiguous geometry is retained. These are sampled conditions, not proof of uninterrupted alignment between samples. The 3-degree engineering choices are unvalidated, recorded before fitting and not searched to remove known false flags.

Retained windows use the original component-wise speed/acceleration and pre-shot tracking medians. A case needs at least five eligible retained tracking windows spanning three different rounds. This provides a repeat-support requirement; rounds are not asserted to be statistically independent events. Cases without support abstain instead of becoming legitimate classifications.

The same participant components, training-only scaling, log1p, C=1 balanced logistic regression and cutoff 0.5 are used. The filtered recipe is fitted inside each training fold; the original historical predictions are copied unchanged. There is no full-pool fit, cutoff search, parameter search or source-label-based window selection.

## Result: reject the exclusion rule

All 55 inspected development cases are included. The rule removes 1,259 of 3,323 windows. Median removed fraction per cheating-labeled case is 56.2%, versus 25.9% per legitimate case. In total, it removes 764/1,403 cheating-labeled-case windows and 495/1,920 legitimate-case windows.

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original speed + tracking | 13 | 3 | 5 | 34 | 0 |
| Filtered, repeated-round support | 9 | 7 | 17 | 22 | 0 |

Every case retains at least ten eligible windows across at least five rounds, so the worse result is not hidden by abstentions or failure to satisfy the repeat-support requirement. Exclusion removes considerably more observations from cheating-labeled cases, reducing useful separation in these measurements. Assisted aim can also remain stably aligned, so discarding this configuration can remove relevant evidence.

The original baseline is retained; the filter is not adopted. The conservative cutoff remains inactive. This result rejects this particular filter/aggregation/refitting recipe; it does not establish that all repeated-event methods fail. All results are post-feedback development diagnostics, not fresh population performance estimates. The original independent frozen evaluation remains unchanged.

## Reproduce locally

```sh
python -m aimguard.candidate_audit \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  --all-cases --output outputs/xguardian/candidate-ambiguity-all-v2
python -m aimguard.encounter_filter \
  outputs/xguardian/development-v4 \
  outputs/xguardian/development-v4-models \
  outputs/xguardian/candidate-ambiguity-all-v2 \
  --output outputs/xguardian/encounter-filter-v3
python -m scripts.render_development_diagnostics outputs/xguardian/encounter-filter-v3
```

Use new output directories. The filter requires every development case in manifest order, not the earlier selected error sample. Case/source hashes, snapshot ticks, original candidate identities, labels and full participant-group membership are checked. Window selection reasons and round support are preserved alongside predictions and coverage. All raw/generated data remains ignored and local.

## Event-level human observation workflow

The experiment creates a review template covering all 3,323 original windows, including excluded windows. Every row starts pending. The CSV contains replay identity/hash, exact start/first-shot/end ticks, round and player, but omits source match labels and model scores. It never labels a removed window legitimate or an included window suspicious automatically.

```sh
python -m aimguard.event_review render \
  outputs/xguardian/encounter-filter-v3 outputs/xguardian/development-v4
```

Open `event-review.html` in the local output directory. Start with its 42-event first pass: the first chronological encounter in each of three different rounds for the fixed 14 error/control cases. This selected sample is for review, not accuracy estimation. All 3,323 windows remain available. Per-case tables link directly to the selected window and geometric-opponent trajectory. Charts are server-observable telemetry, not rendered CS2 gameplay, and cannot establish visibility or intended target. Rendered gameplay review remains a separate human activity; none is claimed completed here.

Download/copy `event-review-template.csv` to a new annotations file, preserving all rows and immutable metadata. Editable columns are:

| Field | Accepted values or content |
| --- | --- |
| review_status | pending, reviewed |
| review_source | unreviewed, telemetry_only, browser_reconstruction, rendered_gameplay |
| observed_behavior | unreviewed, ordinary_preaim, aim_correction, tracking, unclear |
| assistance_assessment | unreviewed, not_assessable, no_clear_evidence, suspicious |
| evidence_reference | Specific demo/tick, screenshot or clip reference |
| evidence_note | Explanation of the observation and its limits |
| reviewer | Reviewer identity |

Reviewed rows require a source, behavior, assessment, reviewer, evidence reference and note. Browser reconstruction rows must use not_assessable for assistance; source-specific counts distinguish them from rendered gameplay. Pending rows must retain unreviewed categorical values. Use not_assessable/unclear when evidence is inadequate; suspicious does not mean confirmed cheat activation. Review source/evidence are reviewer attestations, not independently verified facts.

```sh
python -m aimguard.event_review validate \
  outputs/xguardian/encounter-filter-v3 \
  /path/to/annotations.csv \
  --output /path/to/new-observations.json
```

Validation checks original queue/template receipts, exact event coverage, unique identities, immutable metadata, accepted categories and completed-observation provenance. It writes human observations separately, sets training_labels_created=false and leaves cheat-activation ground truth unset. Nothing is fed into training automatically. The initial all-pending template validates as zero observations, not thousands of negative labels.
