# AimGuard v0.4 — Firearm Replay Analysis

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
python -m aimguard.gameplay data/raw/your-end-vs-damajuana-m1-cache.dem --steamid 76561199104430312 --tickrate 64 --output outputs/v04/slender
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
- Positive health must agree with life state `0`; the input's life-state/health
  distribution is included in the report. Positive health on teams 2 or 3 with another finite
  life-state code fails verification instead of silently changing semantics.
  Known states `1` and `2` are non-alive. Unknown or nonfinite samples are excluded.
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

Version 0.4 adds `movement_context` alongside the existing full-window features.
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
python -m aimguard.review outputs/v04/slender
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
