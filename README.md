# AimGuard v0.5 — Shot Timing and Direction Analysis

An offline CS2 replay-analysis and aim-cheat detection research prototype. It segments active rounds and player lives,
matches player combat events, and describes view-angle movement around shots.

## Setup

Use Python 3.12. From this repository:

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

Run the current firearm analysis:

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

## License

[MIT](LICENSE) © 2026 Varun Menon.
