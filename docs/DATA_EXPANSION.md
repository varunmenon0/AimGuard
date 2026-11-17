# Metadata-first phase-clean development expansion

Acquire new source-labeled matches before inspecting trajectories or scores. The bounded target is 16 cheating-labeled and 32 legitimate player/matches, split into development and future evaluation partitions. Actual counts depend on the available archive prefix and transfer success. Archive order is a convenience sample, not population sampling; original rounded identity and coarse label caveats remain.

## Acquisition and cohort registration

Use scripts.acquire_fresh_cases with the original three label tables, existing compressed cache and 16 GiB total cache cap. Existing bytes count toward the cap. All inspected and registered participants/matches are excluded; accepted new matches cannot share participants. Nested ZIP CRCs, selected demo hashes and unique source-ID encoding among exact replay participants are checked. Source prediction columns are not loaded. A partial archive is not claimed to pass its full multi-part checksum.

Interrupted HTTP transfers are retried with curl's retry-all-errors option. Response status, range boundaries and exact sizes still must pass; retries never bypass validation. Failed attempts remain separate receipts, not successful cases.

After acquisition completes:

```sh
python -m scripts.prepare_metadata_cohorts \
  outputs/xguardian/tracking-baseline-v2/frozen \
  data/external/xguardian/expansion-candidates-v3/candidates.json \
  --output data/external/xguardian/expansion-cohorts-v1
```

Alternate development then holdout within each label in original acquisition order. This rule is fixed before features are computed. If a label count is odd, development receives the extra case. Checksums and participant metadata are revalidated against the frozen bundle and every registry entry. All accepted participants are registered for future acquisition exclusion under an explicit metadata-cohort purpose.

The holdout is reserved for a future phase-clean model; it is not bound to or authorized for legacy model scoring. Its metadata is allowed for disjointness checks, but trajectories remain unextracted. It must remain separate until a future model and single-use evaluation protocol are frozen. A metadata declaration is not independent proof of prior non-use or representative sampling.

## Development extraction and expansion

Make phase-batch jobs only from development.json, retaining its case order, demo paths, exact string SteamIDs and 64 Hz tickrate. Leave the metadata manifests immutable. Then:

```sh
python -m aimguard.phase_batch outputs/xguardian/expansion-development-jobs.json \
  --output outputs/xguardian/expansion-development-v1/analysis
python -m aimguard.expand_phase_pool \
  outputs/xguardian/v06-development-v1/comparison \
  outputs/xguardian/v06-development-v1/analysis \
  data/external/xguardian/expansion-cohorts-v1 \
  outputs/xguardian/expansion-development-v1/analysis \
  --output outputs/xguardian/expanded-phase-pool-v2
```

New reports must be phase-clean and match registered identities. Tracking is re-extracted only for development cases. The original 55 reports/tracks are hash-checked and linked locally; labels and historical artifacts remain unchanged. Missing coverage abstains rather than dropping a case. New cases are participant-disjoint, each adding its own group. An inspected copy of the new development manifest is saved separately; the original metadata declaration and holdout are not rewritten.

The same four-feature grouped logistic diagnostic is rerun on the expanded pool. This is development feedback, not evaluation on the separate holdout. Full-pool totals have different denominators from the historical 55-case result, so count changes alone are not evidence of improvement. No candidate is automatically frozen or deployed. Saved vectors/groups can feed the existing learning-curve workflow when all cases have eligible evidence.

All demos, labels, manifests, registry receipts, plots and extracted features stay under ignored local data/outputs directories. Only reproducible workflow code, tests and documentation are committed.

## Completed bounded attempt

Zenodo transfers stopped after repeated interruptions/timeouts before the 16 GiB cap or 48-case target was reached. The cache grew from approximately 11.08 to 14.14 GiB. Fourteen complete new cases passed metadata checks: one cheating-labeled and thirteen legitimate. Failed/incomplete transfers are not counted. The deterministic split produced:

| Partition | Cheating labels | Legitimate labels | Extracted/scored |
| --- | ---: | ---: | --- |
| New development | 1 | 7 | Yes |
| Reserved controls | 0 | 6 | No |

All 140 replay participants are disjoint from prior exclusions and across these matches. The six reserved legitimate controls can support a future specificity check, but this is not a complete cheating-detection evaluation set; additional untouched cheating cases are still needed. All original label/identity caveats remain.

Eight development extractions succeeded with 303 live windows, 37,750 formerly active warmup samples excluded and no structural violations. All eight retain existing round-event warnings. All new cases retain at least five tracking windows. Combining them with the preserved original pool yields 63 inspected cases (17 cheating labels, 46 legitimate) in 61 participant groups.

| Diagnostic cohort | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Historical original 55, original folds | 13 | 3 | 6 | 33 | 0 |
| Original 55, expanded training folds | 13 | 3 | 5 | 34 | 0 |
| New 8, expanded training folds | 1 | 0 | 1 | 6 | 0 |
| Expanded 63 combined | 14 | 3 | 6 | 40 | 0 |

R-012 becomes a correct negative; N-002 is a new false flag. The other original flags/misses are unchanged. This modest development change does not establish generalization or meet the low-false-positive goal: the combined false-positive fraction is still 6/46 (13.0%). No reserved-control outcome has been inspected and no replacement model is frozen/deployed.

The same grouped learning-curve procedure was rerun on the expanded vectors. Mean training sizes 12.4/24.7/37.2/49.6/62.0 cases yield held-out detection means 74.4/78.2/80.6/81.2/82.4% and false-positive means 18.6/14.1/15.4/15.2/13.0%. The smallest size has 0–1 abstentions per repeat; the others have none. These are correlated diagnostics on inspected data, not independent estimates or evidence that performance scales to a target sample size. Subsampling bands are ranges, not confidence intervals.

Final local artifacts: expansion-cohorts-v1 under data/external/xguardian, expansion-development-v1/analysis, expanded-phase-pool-v2 and expanded-learning-curves-v1 under outputs/xguardian. Both partitions are registered for future acquisition exclusion; metadata manifests remain immutable and a separate inspected-development copy records extraction. No demo was viewed or uploaded.
