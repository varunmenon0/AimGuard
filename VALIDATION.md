# v0.3 local validation

Reviewed November 10, 2026 using the existing Cache replay and player
76561199104430312, with an assumed tick rate of 64 Hz.

- Full automated suite: 50 tests passed.
- Fresh replay execution: 97,881 active samples out of 179,341, 23 segments,
  70 published shot-centered windows, and zero skipped groups. One plot was
  regenerated successfully in a temporary output directory.
- Checked all 70 saved windows against exported telemetry and events: every
  window contains active samples from one round and one segment, brackets its
  shots, has finite features, and does not cross a selected-player death event.
- Visually reviewed all ten saved plots. Yaw, pitch, speed, and shot markers
  render clearly. Windows include both single shots and bursts. Some burst
  windows contain sharp turns after firing; these remain descriptive movement
  measurements, with no conclusion about intent or cheating.
- The saved report flags the missing freeze-end round and unmatched round-end
  events rather than assuming all round event lists align.

This validates the local replay workflow and boundary rules on one recording.
It does not verify enemy visibility, target-relative aim, mouse input, recoil
compensation, or detection accuracy. Padded shot windows can overlap. The older
`aimguard.cs2` command remains a separate unfiltered diagnostic workflow.

Replay data and generated outputs remain excluded from version control. Run
the command in README.md to reproduce the analysis locally.

## Batch validation follow-up

The batch workflow was run on three players in the same Cache replay:

| Player | Active samples | Segments | Windows | Boundary violations |
| --- | ---: | ---: | ---: | ---: |
| Slender-r | 97,881 | 23 | 70 | 0 |
| R4N | 94,160 | 23 | 94 | 0 |
| Lcs | 109,834 | 23 | 110 | 0 |

All 274 windows passed the structural checks. All three jobs retain warnings
for the previously observed malformed round-event sequence. The nine generated
representative plots were reviewed: labels and shot markers render clearly,
including stationary aim and burst windows. Stationary samples and sharp turns
are observations, not evidence of cheating or proof of telemetry fidelity.

An earlier batch attempt included extazzy, a player returned by the replay's
player listing. The filtered parser returned identity/tick columns without
gameplay properties; an unfiltered parse contained null gameplay values for
that player's rows. The batch recorded the error and continued. The loader now
reports that case explicitly, with regression tests for both missing properties
and all-null properties. Listing a player does not establish usable gameplay.

The full local suite now has 67 passing tests. Batch tests include corrupt-window
detection, per-job failure isolation, CLI failure exit codes, empty-window
warnings, exact SteamID manifest validation, relative paths, duplicate rejection,
and refusing existing output directories. Automated fixtures do not replace real
replay validation. Only one distinct replay has been evaluated; additional
matches are still required before claiming cross-match reliability.

## v0.4 firearm and movement-context validation

The six locally acquired XGuardian user-study cases were rerun with firearm
selection and a 0.1-second shot-proximity radius. Published window counts were
83, 143, 51, 75, 99, and 98 for cases 1A, 1B, 2A, 2B, 3A, and 3B respectively.
All 549 windows passed the structural validator. All six reports retain round
event warnings. Cases 1A/1B/2A/2B are study-labeled cheating, and cases 3A/3B are
study-labeled legitimate. These selected examples are development data.

Reports retain full-window features and add interval-based speed, acceleration,
and jerk summaries for near-shot and surrounding movement. Derivatives require
adjacent supporting intervals in the same category. Regression tests verify
that separate periods do not create artificial derivatives, empty categories
export nulls, unknown/knife/utility events are excluded, and weapon switches
split groups. Test fixtures now explicitly identify their synthetic AK-47 shots.

The full local suite has 76 passing tests. A separate replay-command run on case
3A exercised all-event mode and a 0.05-second radius. Generated report scripts
passed programmatic checks for context summaries, shading, navigation, and older
report compatibility. Visual browser verification was unavailable because the
browser tool rejected local file URLs.

The older-demo compatibility fix restricts positive-health life-state
verification to playing teams 2 and 3. Unassigned spawn samples remain excluded,
and inconsistent life states on playing teams still raise an error. A regression
test covers unassigned records retaining spawn health.

The configurable 0.1-second radius is an exploratory default. It does not
establish a detection threshold, and these checks do not measure cheat detection
accuracy or reconstruct recoil and target context. Source demos, labels, and
generated analyses remain local and excluded from Git.
