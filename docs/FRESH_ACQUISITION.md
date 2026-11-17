# Metadata-only fresh replay acquisition

`scripts.acquire_fresh_cases` obtains a bounded local sample from XGuardian's
public raw archive, using original `isCheater` labels and participant metadata.
It never requests aim/position properties, computes trajectory measurements, or
runs the frozen classifier. Source prediction columns are excluded when loading
label tables. The candidate pool remains uninspected until a separate reservation
and evaluation step.

The current acquisition plan targets eight cheating-labeled and 16 legitimate
selected player/matches. Selection is archive order, with cheating-label priority
until that quota is filled and deterministic hash order within a label. It rejects
all recorded inspected participants and all participants in previously accepted
matches. Each source label ID must map uniquely among the replay's exact IDs.
Rounded IDs are never converted back to invented exact SteamIDs.

```sh
python -m scripts.acquire_fresh_cases \
  outputs/xguardian/tracking-baseline-v2/frozen \
  --label-table data/external/xguardian/selected/Experiments/5.2_Detection_Performace/overall_performance/TrainValTest/aggregated_predictions_train_cleaned.csv \
  --label-table data/external/xguardian/selected/Experiments/5.2_Detection_Performace/overall_performance/TrainValTest/aggregated_predictions_val_cleaned.csv \
  --label-table data/external/xguardian/selected/Experiments/5.2_Detection_Performace/overall_performance/TrainValTest/aggregated_predictions_test_cleaned.csv \
  --cache data/external/xguardian/raw-part1-acquisition-prefix.zst \
  --prefetch data/external/xguardian/raw-prefetch \
  --output data/external/xguardian/fresh-candidates-v1 \
  --cheating 8 --legitimate 16 --limit-gib 16
```

Use a new output directory. The cache is a growing prefix of the sequential
Zstandard-compressed tar archive, not a collection of independently seekable
files. Existing bytes/range chunks are reused. Four bounded download workers
append byte ranges, checking final HTTP 206/Content-Range responses and exact
sizes. The cache cap includes bytes acquired in earlier runs; incomplete nested
members at the cap do not count as selected cases. Curl and zstandard are needed
for acquisition; neither changes the frozen model's features or parameters.

`plan.json` records quotas, cache cap, frozen model/source hashes, selection rule,
and uninspected status before extraction. `acquisition.json` records inventory,
selected/rejected cases and progress. `candidates.json` is compatible with the
reservation workflow in [TRACKING_EVALUATION.md](TRACKING_EVALUATION.md).

Each extracted nested ZIP passes CRC checks; demo and label-source hashes are
recorded. A partial multi-part archive cannot be verified against its full-file
checksum, so the tool does not claim that check. Candidate files and receipts
stay under ignored local data directories. Public data source:
[XGuardian raw data, part 1](https://zenodo.org/records/17838584).

The sample is an archive-order convenience sample, not a random representative
sample. Labels identify cheating for a selected player/match, without aimbot
activation annotations. Original source IDs are rounded; uniqueness within the
replay is a mapping check, not recovery of the original unrounded annotation.
No source-model predictions or current-model scores may be used to replace
selected cases. Review metadata integrity, then bind the final cohort to the
frozen model before running evaluation once.

Future acquisition runs also read the frozen model's reservation registry. Every
registered participant/match is excluded, including cohorts already evaluated or
reserved but not yet scored. The acquisition plan records those receipt hashes.
This avoids rediscovering a consumed cohort while keeping the frozen model
immutable. The first recorded cohort used acquisition commit `54d3068`; this
registry exclusion was added afterward and does not alter its selection/results.

## Cache-only development controls

Use `--purpose development --cached-only --cheating 0 --legitimate 16` with a new output directory to select legitimate development controls from bytes already cached. One label quota may be zero, but their total must be positive. Cached-only mode caps the reader at the existing cache length and makes no download request. An incomplete final archive member is not counted. Record the actual selected count rather than substituting cases based on scores.

Development acquisition writes `development_candidates`, not evaluation candidates. Before feature extraction, validate source hashes and full replay participant identities against existing development/reservation exclusions. Register these participants for future exclusion with purpose `development_only_participant_exclusion_not_evaluation`; this receipt does not authorize an evaluation or claim a fresh holdout. After extraction, explicitly mark the development manifest as inspected. Raw demos, metadata, receipts and extracted artifacts remain ignored local files.

The first cache-only development run requested 16 legitimate cases and recovered 14 complete cases before the cached prefix ended. No additional bytes were downloaded.

## Later phase-clean expansion

See [DATA_EXPANSION.md](DATA_EXPANSION.md) for the metadata-first split and phase-clean development extension. The bounded attempt recovered fourteen additional participant-disjoint matches before transfer timeouts: eight entered development and six legitimate controls remain unextracted/unscored. The original acquisition target was not reached. The six controls are not a complete cheating-detection evaluation set.
