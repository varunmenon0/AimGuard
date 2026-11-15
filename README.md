# AimGuard v0.5 — Shot Timing and Direction Analysis

An offline CS2 telemetry prototype. It segments active rounds and player lives,
matches player combat events, and describes view-angle movement around shots.
It does not classify players as cheating and is not a deployable anti-cheat.

## Setup

Python 3.12 is used for local validation. From this repository:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
```

On macOS/Linux, use `python3 -m venv .venv` and `source .venv/bin/activate`.

## Analyze the existing Cache replay

Find a player's SteamID with the existing diagnostic command:

```sh
python -m aimguard.cs2 data/raw/your-end-vs-damajuana-m1-cache.dem --list-players
```

Run the current firearm analysis (the selected player below was used in earlier validation):

```sh
python -m aimguard.gameplay data/raw/your-end-vs-damajuana-m1-cache.dem --steamid 76561199104430312 --tickrate 64 --output outputs/v05/slender
```

Optional settings: `--pre-seconds 0.5`, `--post-seconds 0.5`,
`--shot-gap-seconds 0.5`, and `--max-plots 10`. Use `--max-plots 0` to skip plots.
Timing is an explicit assumption: verify the demo's tick rate before interpreting
rates or durations. No additional demo download or classifier training is needed.

Outputs:

- `telemetry.csv`: selected-player samples, including excluded rows, round and
  segment IDs, active flags, and exclusion reasons. Invalid angles are preserved
  as boundaries rather than removed and joined across. Angles are exported as
  float64 to preserve parser precision for derivative recalculation.
- `events.json`: selected-player shots, incoming/outgoing damage, and deaths,
  with explicit player roles and exact string SteamIDs. Segment `-1` means an
  event is outside a valid active segment.
- `report.json`: features for every published window, skipped groups and reasons,
  sample coverage, life-state verification, unusual round events, configuration,
  source SHA-256, feature version, and dependency versions.
- `engagement_XXXX.png`: close-up yaw, pitch, and speed plots with shot markers;
  the first ten windows are plotted by default. The report lists generated plots.

Generated data and outputs are ignored by Git. Use a separate output directory
for each player or configuration to keep analyses distinct.

## Segmentation rules

- `round_start` closes any preceding active interval and enters freeze time.
  `round_freeze_end` opens active play. `round_end` closes it; its tick is excluded.
  No freeze-end means that round is excluded. Events are not paired by list index.
- A freeze-end without a start opens a flagged inferred round. Duplicate
  freeze-ends are reported and ignored. Missing round ends close at the next
  start or recording end and are reported. For simultaneous transitions, an end
  is processed before a start, then a freeze-end.
- Life state `0` and positive health are required for alive samples. Known
  states `1` and `2` are excluded even when older demos retain positive health.
  Reports count these retained-health samples and include the state/health
  distribution. Positive health on playing teams with an unknown finite state
  fails verification. Other unknown or nonfinite samples are excluded.
- Only teams `2` and `3`, positive health, valid life state `0`, finite required
  telemetry, and pitch within [-90, 90] are eligible during active play.
- Victim death events exclude the death tick, even with delayed health updates.
  A death latch clears only after an observed non-alive to alive transition or
  a new active round. Killing another player does not end the selected player's life.
- Invalid samples, ineligible periods, round changes, and recording gaps over
  250 ms split segments. Duplicate ticks keep the last input observation using a
  stable sort. Unlocatable invalid tick values cause an error.

## Shot-centered windows and features

New analyses default to `--weapon-mode firearms`. The explicit firearm list
excludes knives, utility, tasers, and unknown/missing weapon names. Use
`--weapon-mode all` to include all weapon-fire events for diagnostics. Filtering
occurs before shot grouping, and weapon changes split groups. Each window records
its normalized weapon name. Reports record excluded event counts by weapon,
and events.json records the selection flag independently of active-life coverage.

Version 0.4 added `movement_context` alongside the existing full-window features.
`--near-shot-seconds` defaults to 0.1 seconds. A speed interval is near a shot
when its ending tick is within that radius of any grouped shot. Remaining
intervals are surrounding movement. Acceleration requires two consecutive speed
intervals in the same category, and jerk requires three. Disjoint periods are
never joined to calculate derivatives. Samples at category boundaries may
therefore contribute to full-window derivatives only. Empty categories report
null measurements and zero sample counts. Covered durations and counts are
included for interpretation.

This timing radius is configurable and has not been validated as a detection
threshold. Replay reviews shade near-shot periods and show both summaries.
Older reports still open with their original full-window measurements.

Version 0.5 adds `shot_time_profile` for each window. Every near-shot speed
interval references its nearest grouped shot; equal-distance ties reference the
earlier shot. Before, at, and after categories are disjoint. The profile includes
before/after p95 speed, at-shot median speed, a log1p before/after speed difference,
near-shot stop fraction, mean turn angle, axis reversal rates, and the signed
offset of the first near-shot speed peak. Stationary motion has no peak timing.
These are movement descriptions; target error and recoil are not reconstructed.

Direction features use adjacent intervals within near-shot periods. Axis
reversals require both steps to be at least 0.05 degrees. Turn angles require
nonzero adjacent yaw/pitch steps. Rates use covered near-shot duration, and
missing observations remain null. Review pages display these measurements
alongside their shot markers and original summaries.


Nearby selected-player `weapon_fire` events are grouped within each segment;
successive shots at most `--shot-gap-seconds` apart belong to one group.
Pre/post context is clipped to that segment. Groups with fewer than eight samples
or without samples bracketing their shots are explicitly skipped. Padded windows
from distinct groups may overlap; their statistics are not independent trials.

Each window contains mean/p95 angular speed, mean absolute speed acceleration,
p95 absolute speed jerk, path efficiency, mean turn angle (radians), speed CV, and
near-stop fraction (speed below 2 deg/s). Angular movement uses the Euclidean
yaw/pitch coordinate approximation, not mouse input or target-relative error.
Acceleration and jerk describe scalar speed changes, not vector acceleration.
Yaw wrapping and irregular sample intervals are handled by the extractor.

Two additional counts describe adjacent yaw/pitch steps reversing sign when both
steps are at least 0.05 degrees. These are descriptive reversal counts, not
verified aim corrections. Damage and kill event counts describe the selected
player's events inside the window, not causal attribution to a particular shot.

Weapon fire demonstrates shooting activity, not an encounter with a visible
enemy. Positions are retained for future context but visibility, enemy targeting,
weapon-specific recoil compensation, and target acquisition are not implemented.

## Other entry points

- `python -m aimguard.cs2 DEMO --steamid ID --output outputs/cs2` retains the older
  unfiltered whole-replay diagnostic workflow. Its fixed windows use absolute
  tick bins and one shared preceding sample to retain boundary movement. It
  does not apply gameplay filtering.
- `python -m aimguard.demo --output outputs/synthetic_report.json` retains the
  separate synthetic classifier smoke test. Its intentionally different synthetic
  styles and session split do not establish real-world detection performance.
- `scripts/inspect_demo.py` is the existing local property/event inspection script.

## Validation and next steps

### Batch replay validation

Create a JSON array of jobs (see `examples/replay-validation.json`). Each job
requires `demo`, an exact string `steamid`, and an explicit numeric `tickrate`.
Demo paths are relative to the manifest file. Add jobs for additional matches
or players; duplicate replay-path/player pairs are rejected.

```sh
python -m aimguard.batch examples/replay-validation.json --output outputs/validation/cache-three-players --max-plots 3
```

The destination must be new, preventing stale results from being mistaken for
fresh analysis. Each job exports the usual analysis artifacts in its own folder.
`summary.md` compares coverage and window counts; `summary.json` also records
excluded event counts, round anomalies, skipped groups, errors, and individual
window violations. One failed job does not stop the remaining jobs.

The validator checks every exported window for active samples, one round and
segment, no selected-player death crossings or recording gaps, shot matching,
sample bounds, and finite features. A nonzero exit code indicates analysis errors
or validation violations. Empty active coverage, zero shooting windows, and round
event anomalies produce warnings requiring review; warnings alone exit zero.
Inspect the representative plots manually, including sharp turns and clipped
windows. Passing structural checks does not establish detection accuracy.

The included manifest selects three players from the one locally available
Cache replay. That exercises multiple players but is still only one match.
Distinct replay contents are counted by SHA-256 so copies cannot inflate match
coverage. Additional replay files are needed for cross-match validation.

### Review a player's shooting windows

To go from a demo to a review report in one command, run:

```sh
python -m aimguard.replay data/raw/your-end-vs-damajuana-m1-cache.dem --tickrate 64 --output outputs/review/cache
```

Choose a player from the numbered list, then open the printed `review.html` path.
Use `--steamid` to select a player directly for scripted runs. Verify the tick
rate for your recording and choose a new output folder for each run.

After analyzing a replay, pass the player's output folder to the review command.
For a batch run, use one of the `job_XXXX` folders.

```sh
python -m aimguard.review outputs/v05/slender
```

Open the resulting `review.html` in a browser. Use the window selector or
Previous and Next to inspect yaw, pitch, angular speed, and shot markers. The
report contains every published window, even if PNG export was disabled. It
works offline and embeds selected-player telemetry, so share it only where you
would share the underlying analysis. Use `--output` to choose a new filename
when rebuilding a report.

### Experimental player/match baseline

`aimguard.baseline` freezes a two-feature logistic regression from development
reports and evaluates it against a separately reserved manifest. It aggregates
median near-shot p95 speed and mean absolute speed acceleration per selected
player/match, using the existing 100 ms firearm configuration. Scaling is fitted
on development cases only, with log1p input transformation, class balancing,
C=1, and a fixed 0.5 cutoff. Scores are uncalibrated.

The following commands require the locally acquired case manifests and reports,
which are excluded from Git. Choose new destinations when reproducing a run.
The historical first evaluation uses commit `8b4748e` and its version-0.4 reports.
Current extraction changes require newly generated reports of the matching
feature version before freezing a new model.

```sh
python -m aimguard.baseline freeze outputs/xguardian/study-validation/study-cases.json outputs/xguardian/firearm-context-validation --output outputs/baseline-demo/frozen
python -m aimguard.baseline evaluate outputs/baseline-demo/frozen data/external/xguardian/additional-evaluation-manifest-v2.json --output outputs/baseline-demo/evaluation
```

The evaluation manifest has a `cases` array with exact string SteamIDs, match
IDs, labels, demo paths and hashes, and label-file paths and hashes. Its adjacent
`.sha256` receipt must match. Model JSON and its checksum record the scaler,
coefficients, cutoff, development inputs, code hashes, and dependency versions
before reserved feature extraction. A start receipt records those hashes for
each evaluation. Duplicate/development-overlapping targets, matches, and demo
hashes are rejected. Processing errors produce explicit abstentions.

`evaluation.json` records individual predictions, confusion counts, analysis
coverage, and exact binomial intervals. Rate denominators include successfully
analyzed cases, with abstentions reported separately. The first local run flagged
1/4 cheating-labeled cases and 3/6 scored legitimate cases, with one additional
legitimate case abstaining. These results motivate further development and more
representative data. See VALIDATION.md for limits and evaluation-set usage.

### Development comparisons

The expanded local development manifest contains the six study cases and the
11 cases already evaluated by baseline v1. All 17 cases are development evidence.
The comparison command checks report identities and extraction settings, exports
case summaries and provenance hashes, and compares cases within shared weapons.

```sh
python -m scripts.compare_development data/external/xguardian/development-v2-manifest.json outputs/xguardian/development-v2-analysis --output outputs/xguardian/development-v2-comparison
```

The command requires firearm-filtered reports with identical feature versions,
timing settings, and assumed tick rates. Shared-weapon tables weight cases
equally and display combinations with at least five eligible windows per case
and at least two cases per label. These display cutoffs do not establish
sufficient sample size for detection. The resulting comparisons are descriptive.

### Automatic test execution

GitHub Actions runs `python -m pytest -q` on pushes and pull requests using
Python 3.12 on Linux. Tests use small fixtures and do not require private demos.
Real replay validation remains a separate local command.

Tests cover death-event lag, respawn, round transitions, missing/duplicate events,
invalid samples, gaps, exact event identity matching, stable deduplication,
window-boundary movement, and irregular-timestamp jerk.

The existing Cache replay was validated with demoparser2 0.42.0, NumPy 2.5.4,
pandas 3.1.1, and Matplotlib 3.11.2. Each report records its actual runtime versions.

Next, visually review the shot windows and excluded periods, then add target
positions/visibility and weapon context. A real labeled dataset, splits by player
and match, calibrated scores, and false-positive estimates are prerequisites for
detection evaluation. Live server ingestion, model inference, player-level risk
aggregation, and review tooling remain future work.

Never automatically punish players from this prototype. Keep unnecessary player
identifiers out of shared artifacts; provide review and appeal mechanisms before
any deployment.

### Grouped development model diagnostics

Compare two fixed recipes on the explicitly designated development pool:

```sh
python -m aimguard.development_models data/external/xguardian/development-v2-manifest.json outputs/xguardian/development-v2-analysis --output outputs/xguardian/development-model-diagnostics
python -m scripts.render_development_diagnostics outputs/xguardian/development-model-diagnostics
```

Matches sharing any participant, including transitive links, stay together.
Each prediction holds out an entire participant group; scaling and model fitting
use the remaining groups only. Cases, rather than windows, are training rows.
The command records input/code hashes, dependency versions, group membership,
fold scalers, coefficients, and predictions. It requires local demos to verify
checksums and participant identities. Choose a new output directory for each run.

The 17-case development run formed 15 groups. Speed/acceleration found 5/8
cheating-labeled cases with 2/9 false flags; timing/direction found 4/8 with 1/9
false flags. These are exploratory diagnostics on previously inspected data,
not fresh held-out accuracy estimates. Neither recipe is selected for deployment.

### Development error review queue

```sh
python -m aimguard.error_review data/external/xguardian/development-v2-manifest.json outputs/xguardian/development-v2-analysis outputs/xguardian/development-model-diagnostics-v2 --output outputs/xguardian/error-review
```

This verifies the diagnostic manifest/report hashes, preserves both models'
predictions, and generates a local index linking trajectory viewers for all
cases. The queue includes error categories, weapon mix, eligible measurements,
and windows with damage or kills. Shared misses are listed first. All cases
start as unreviewed: combat counts and match labels do not establish why a model
failed or which ticks contain cheating. The viewer shows recorded aim charts,
not rendered CS2 gameplay. Choose a new output directory for each run.

### Horizontal opponent alignment diagnostics

```sh
python -m aimguard.target_geometry data/external/xguardian/development-v2-manifest.json outputs/xguardian/development-v2-analysis --output outputs/xguardian/target-geometry
python -m scripts.render_target_geometry outputs/xguardian/target-geometry
```

This separate development command verifies local demo/report identities and
extracts all players' positions at published firearm shot ticks and approximately
100 ms earlier. It computes horizontal bearing minus recorded yaw for alive
opponents on the other playing team. Exact ticks are required; missing samples
are not interpolated. Duplicate player/tick identities fail verification.

For the nearest horizontal candidate at the shot, the before/after comparison
keeps that same opponent. It does not switch to whichever opponent was nearest
earlier. Pre-shot pairs must fall within the published window and have valid
alive players with unchanged teams. The report records coverage and exclusions,
assumed timing, input hashes, and per-opponent measurements.

This is a geometry diagnostic, not a new detector. It does not determine the
intended target, visibility, head/hitbox alignment, recoil-corrected bullet
direction, or continuous tracking. Opponents already dead at the shot tick are
excluded, including lethal-tick state changes. Existing feature versions and
model outputs remain unchanged. All generated identity data remains local.
Parser fields are documented by [demoparser2](https://github.com/LaihoE/demoparser#list-of-fields-the-parser-supports).

### Fixed-opponent tracking and event association

```sh
python -m aimguard.target_tracking data/external/xguardian/development-v2-manifest.json outputs/xguardian/development-v2-analysis --output outputs/xguardian/target-tracking
python -m scripts.render_target_tracking outputs/xguardian/target-tracking
```

This development diagnostic follows fixed opponents through each published
firearm window. It retains separate nearest horizontal candidates at the first
shot and its exact preceding tick, plus any recipients of positive damage from the selected player with the same
weapon, segment, and window. These sources stay separate; multiple recipients
produce separate tracks. A damage recipient is not a per-bullet target annotation.

Horizontal error and yaw/bearing velocities use exact consecutive replay ticks.
Missing/invalid samples, non-alive states, team changes, and recorded death events
break the trajectory. A death event excludes that player through the window end,
even if health/state updates lag. Rates never bridge a recording gap. Near-shot
rate summaries require both supporting samples within 100 ms of a grouped shot.
Stationary or insufficient rate observations produce null correlations.

The local viewer lets you choose a window and fixed opponent, with shot and
recipient-specific damage markers. JSON records each association source, damage
event, trajectory, coverage, input hashes, code hashes, and runtime versions.
Re-extraction must reproduce the saved shooter's inputs at original float32
coordinate precision. Choose a new output folder for each extraction run.

The first-shot candidate belonged to the damage-recipient set in 274/480 eligible
development windows. This is agreement between different association methods,
not target-identification accuracy: opponents can change during a burst.
Visibility, vertical/hitbox geometry, recoil, lag compensation, and subtick timing
remain unresolved. No classifier or detection threshold changes in this command.

### Audit target-association disagreements

```sh
python -m aimguard.association_audit data/external/xguardian/development-v2-manifest.json outputs/xguardian/development-v2-analysis outputs/xguardian/target-tracking --output outputs/xguardian/association-audit
```

Use newly extracted tracking reports containing both shot-tick and pre-shot
candidates, and run the tracking renderer first. The audit verifies source input
hashes, window identities, and matching damage events. It compares both candidate
choices with damage recipients without using damage events to select a geometric
candidate. Report counts distinguish agreement, pairwise ordering changes,
interrupted/missing geometry, and comparisons without a later pre-damage sample.
Pairwise ordering compares only the fixed candidate and recipient, not all enemies.

Selecting at a lethal shot's tick can exclude the victim because that tick already
records death. The exact preceding tick provides a separate candidate without
that post-shot state. In the current development pool, window-level event
agreement is 438/485 for the preceding-tick candidate versus 274/480 at the shot.
These are association diagnostics, not intended-target accuracy or cheating
sensitivity. Original counts and detector predictions remain preserved.

The local audit index links to exact window/opponent selections in the tracking
viewers using `#w=WINDOW_INDEX&t=TRACK_INDEX`. Invalid indices fall back to the
first selection. Damage occurrences in overlapping windows are reported separately
from distinct source damage records; neither is treated as an independent trial.

### Grouped comparison with pre-shot tracking

```sh
python -m aimguard.tracking_models data/external/xguardian/development-v2-manifest.json outputs/xguardian/development-v2-analysis outputs/xguardian/target-tracking --output outputs/xguardian/tracking-models
python -m scripts.render_development_diagnostics outputs/xguardian/tracking-models
```

This command records fixed recipes before loading features or fitting models.
It compares the two existing recipes, pre-shot tracking alone, and speed plus
tracking. The two tracking features are absolute horizontal aim error and
absolute yaw-minus-opponent-bearing velocity. They summarize the contiguous
recorded segment ending exactly one tick before the first shot, within the
preceding 200 ms. A window needs eight valid intervals; a case needs five eligible
windows. Window medians are aggregated into one equally weighted case row.

Only the geometric candidate selected before the first shot is used. Damage
recipients, hit-only windows, and post-shot tracking samples do not select or
supply the new features. Missing coverage produces explicit abstention rather
than imputation. Models keep the original participant components together, with
training-fold scaling and balanced logistic regression C=1 and cutoff 0.5.
The combined recipe appends tracking measurements to original speed/acceleration;
all four nonnegative features use log1p before training-only scaling.

On the previously inspected 17-case development pool, speed plus tracking flags
6/8 cheating-labeled cases and 0/9 legitimate cases. Tracking alone flags 6/8
with 3/9 false flags. No threshold, eligibility, or parameter search was performed.
This is development evidence, not independent accuracy: feature choices were
informed by this pool, labels are not aimbot-specific, and nine legitimate cases
cannot establish a dependable low false-positive rate.

Protocol and input receipts precede fitting. Outputs retain per-case features,
coverage, hashes, groups, fold training/held-out IDs, scalers, coefficients, and
scores. The generic renderer supports every recorded recipe without refitting.
No deployment model is fitted on the full pool. The historical two-feature
`aimguard.baseline freeze` workflow does not freeze this four-feature candidate;
a matching freeze/evaluation workflow is required before fresh-data evaluation.
