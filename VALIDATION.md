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

## First frozen baseline evaluation

A player/match baseline was fitted using only the six study development cases.
Inputs were median per-window near-shot p95 speed and mean absolute speed
acceleration, at the existing 100 ms firearm setting. The log1p transformation,
development-only StandardScaler, class-balanced logistic regression with C=1,
and cutoff 0.5 were fixed before evaluating the 11 reserved cases. There was no
hyperparameter search or evaluation-driven threshold change.

The frozen model SHA-256 was
`0803119ac6aa815d5781a089399d727a7007850a72430590900c4f7369fee011`.
Model JSON includes development report hashes, extraction code hashes, and
dependency versions. Evaluation wrote a start receipt before feature extraction.

Ten cases were scored and one legitimate-labeled case abstained:

| Outcome | Count |
| --- | ---: |
| Cheating-labeled target flagged | 1 |
| Cheating-labeled target missed | 3 |
| Legitimate-labeled target falsely flagged | 3 |
| Legitimate-labeled target unflagged | 3 |
| Legitimate-labeled target abstained | 1 |

Among successfully analyzed cases, detection was 1/4 (25%, exact 95% interval
0.6%–80.6%) and false positives were 3/6 (50%, interval 11.8%–88.2%). The intervals
assume independent outcomes and do not account for source-label uncertainty or
shared non-target participants. This convenience sample is small.

The first three legitimate-labeled targets scored higher than all four
cheating-labeled targets. The separation observed in the development cases did
not generalize reliably with these speed/acceleration summaries. The development
sample contained only two legitimate cases, both selected XGuardian false-positive
examples. Weapon mix, targets, and recoil remain uncontrolled.

The abstention involved 1,599 positive-health life-state-2 samples on playing
teams, including 1,154 within active-round intervals. This was diagnosed after
evaluation. The frozen extractor and predictions were retained, and that case
remains an abstention in the recorded run.

The source labels indicate cheating within a selected player's match, without
cheat subtype or activation ticks. Source IDs were rounded, with unique mappings
to exact replay IDs recorded in acquisition manifests. This evaluation does not
establish aimbot-specific sensitivity. Scores are uncalibrated.

All 82 automated tests pass, including model export/checksum verification,
development/evaluation overlap rejection before extraction, frozen configuration
checks, missing-feature handling, and explicit abstention denominators. The
original reservation manifests remain historical snapshots; a local usage receipt
records that these 11 cases have now been evaluated. Further tuning using this
feedback requires fresh cases for a new held-out performance claim.

## Retained-health life-state correction

Version 0.4.1 excludes known non-alive states 1 and 2 even when a demo retains
positive health. Such samples split active segments and are counted explicitly.
Positive health on playing teams with an unknown state still fails verification.

The previously abstaining legitimate case now yields 53 firearm windows with no
structural violations. All 1,599 retained-health non-alive samples remain excluded.
The original frozen baseline results were preserved. No revised detection rate
was computed from this extraction fix. All 84 tests pass, including both known
non-alive states and segment-boundary preservation.

## Temporal movement development, version 0.5

The six study cases and the 11 previously evaluated cases were explicitly
combined into a development pool. It contains 17 distinct selected targets and
matches, with eight cheating labels and nine legitimate labels. No case in this
pool is treated as a fresh held-out evaluation case.

All 17 cases were reprocessed with firearm selection, a 100 ms shot radius,
0.5-second padding, and assumed 64 Hz timing. The resulting 1,316 windows passed
structural validation. All cases retain round-event warnings. The previously
abstaining case contributes 53 windows with retained-health non-alive samples
excluded. Original baseline-v1 artifacts and metrics were preserved.

The extractor adds nearest-shot before/at/after speed summaries, a before/after
log speed difference, near-shot stop fraction, turn angle, axis reversal rates,
and signed peak timing. Categories partition the near-shot speed intervals.
Tests cover ties, disjoint periods, stationary movement, missing observations,
yaw wrapping, and retained-health life states. Current and legacy report scripts
passed programmatic rendering and navigation checks; local-file browser policy
prevents automated visual browser verification.

The development comparison exports six temporal distributions, case summaries,
report/manifest hashes, and 36 shared-weapon comparisons. Shared-weapon summaries
weight cases equally. Display eligibility requires five eligible windows per
case and two cases per label. These are reporting choices, with no detection
threshold or accuracy claim.

Substantial label-group overlap remains. Most case medians for directional
reversal rates are zero. The original blatant study examples show larger turn
angles and more reversals than most additional cheating-labeled cases. The new
measurements have not demonstrated improved held-out detection performance.

The 90-test suite passes. Additional coverage rejects mixed extraction settings
before producing development comparisons. Generated demos, identity metadata,
analysis outputs, and charts remain excluded from Git.

## Participant-grouped development model diagnostics

Two fixed recipes were compared across the expanded 17-case development pool:
original speed/acceleration summaries and four timing/direction summaries
(stop fraction, turn angle, before/after log speed difference, signed peak time).
Connected components of all replay participants produce 15 groups; transitive
participant overlap stays within a group. Each fold holds out one whole group,
with scaling and balanced logistic regression fitted on training groups only.
Case medians are training rows. Both recipes use C=1 and cutoff 0.5, without a
parameter or threshold search. Single-class training folds abstain explicitly.

| Recipe | True positives | Missed cheating labels | False positives | True negatives |
| --- | ---: | ---: | ---: | ---: |
| Speed/acceleration | 5 | 3 | 2 | 7 |
| Timing/direction | 4 | 4 | 1 | 8 |

Both scored all 17 cases. Timing/direction reduced false flags but missed one
additional cheating label. No production winner was selected. The speed recipe
is refitted within each fold and is distinct from the historical frozen model.
Feature choices were informed by this pool; these diagnostics do not establish
improved held-out detection. Overlapping training folds also preclude treating
the predictions as independent binomial trials, so exact confidence intervals
are omitted. Source labels remain generic cheating labels with rounded-ID limits.

Local protocol and comparison artifacts record input/code hashes, dependency
versions, participant components, eligible-window counts, training/held-out case
IDs, scalers, coefficients, and predictions. A second identical run added complete
provenance and chart formatting; it did not change the recipes or cutoff.
The 95-test suite passes, including transitive participant grouping, training-only
scaling, one prediction per case, single-class abstention, and invalid-input checks.
All identity metadata, demo files, diagnostic reports, and plots remain local.

## Development error inspection queue

The saved grouped predictions yield two shared misses, E-05 and E-09. Their
103 and 160 firearm windows include 47 and 89 windows with damage events,
respectively. A lack of recorded combat windows alone does not explain either
miss. These are coverage observations, not causal diagnoses or activation labels.
False flags occur on D-3A for timing/direction and E-01/E-08 for speed/acceleration.

The local review index links all 17 trajectory viewers and records per-case
weapons, damage/kill window counts, eligible measurements, model outcomes, and
provenance. Every case starts with explicit unreviewed status and no causal
explanation. Tests reject altered manifest receipts and unsafe case identifiers
before creating output. No model, threshold, or historical prediction changed.

## Horizontal opponent geometry feasibility

A separate diagnostic processes the same 17 development demos, without fitting
or changing a classifier. Of 6,060 unique published firearm shot ticks, 6,030
have a valid alive opposing-player candidate and 6,007 have an exact paired
pre-shot observation. At assumed 64 Hz, the rounded 100 ms offset is six ticks
(93.75 ms). Opponent geometry is sampled at exact ticks without interpolation.
The nearest candidate by horizontal angular error at the shot is held fixed
when comparing the earlier endpoint. Every opponent candidate is retained in
local per-case JSON, not only the nearest one.

Tests cover cardinal bearings, yaw wrap, zero-distance/invalid positions,
fixed opponent identity across endpoints, teammates, retained-health non-alive
players, missing exact ticks, duplicate player/tick rejection, and team changes.
All 107 tests pass. The generated static chart was visually inspected; no browser
visual verification is claimed. Inputs/code hashes and dependency versions are
recorded locally, with explicit coverage and unavailable reasons.

There is label-group overlap in horizontal alignment. Shared misses E-05 and
E-09 have median nearest-candidate horizontal errors of 13.394 and 2.178 degrees,
respectively. This does not support attributing both failures to one alignment
pattern. The pre-shot comparison includes player translation and is not an
isolated measure of crosshair movement.

These measurements omit vertical aim, hitboxes, eye offsets, visibility,
recoil correction, lag compensation, and subtick timing. A geometrically nearest
opponent may be behind a wall or not the intended target. A lethal shot can
already show the victim as dead at its recorded tick; excluding that candidate
creates coverage bias. Two endpoints do not establish continuous tracking.
Further work must validate target association and trajectory geometry before
using these diagnostics as candidate model features. No improved detection rate
is claimed, and all historical model predictions remain unchanged.
