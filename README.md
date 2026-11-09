# AimGuard v0.1 — Server-Side Aim Behavior Prototype

A small, runnable **offline proof of concept** for analyzing view-angle telemetry. This is **not** a deployable anti-cheat and has not been validated on real player or cheat data.

## Quick start (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -q
python -m aimguard.demo --output outputs/synthetic_report.json
```

If `py -3` is unavailable, use `python -m venv .venv`.

## What is implemented
- Degree-aware yaw wrap handling, timestamp validation, and gap rejection.
- Eight trajectory features: mean and 95th-percentile speed, mean absolute acceleration, 95th-percentile absolute jerk, path efficiency, average turn angle, speed variation, and near-stop fraction.
- Reproducible synthetic trajectory generator (two deliberately different styles).
- Gradient-boosted classifier and **session-separated** train/test split.
- JSON evaluation report and automated tests.

## What is not implemented
- CS2 demo parsing or live game server ingestion.
- Target visibility, acquisition latency, target-relative tracking, weapon/recoil context.
- Real labeled datasets, calibrated scores, statistically defensible recall/FPR claims.
- Production inference, player-level risk aggregation, review UI, privacy controls.

## Data contract
`extract_features(timestamps, yaw, pitch)` expects three equal-length numeric arrays: monotonic seconds, yaw degrees, and pitch degrees. Missing samples or gaps greater than 250 ms must be segmented upstream. Pitch/yaw are server-observable *only if the game server actually records or exposes them*.

## Next milestone
Add a CS2 demo adapter that exports normalized telemetry with `match_id`, `player_id`, `tick`, `timestamp`, `yaw`, `pitch`, and contextual events. Verify each field against the parser and the server's actual visibility/authority. Then build trajectory plots and collect properly labeled, consented/authorized samples before evaluating any real detection claims.

## Ethics and deployment
Never automatically punish players from this prototype. Synthetic performance is not evidence of real-world performance. Do not store unnecessary player identifiers, and provide review and appeal mechanisms before any deployment.
