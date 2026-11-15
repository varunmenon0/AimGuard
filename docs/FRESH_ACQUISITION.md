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
