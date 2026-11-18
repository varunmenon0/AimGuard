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

## Fixed-opponent tracking and damage association

Continuous sampled horizontal trajectories now supplement the two-endpoint
geometry diagnostic. For each published firearm window, separate tracks retain
the nearest valid opponent at the first shot and each matching damage recipient.
Damage links require exact attacker identity, positive health damage, matching
weapon, segment, and window bounds. Per-event ticks and recipient IDs are kept.
Multiple recipients stay separate; no bullet-to-target attribution is invented.

Across 17 development cases and 1,316 windows, 1,495 of 1,528 tracks have at least
one consecutive valid interval. There are 477 windows with one matching damage
recipient and nine with multiple recipients. Of 480 damage windows with an
available first-shot geometric candidate, 274 candidates belong to the window's
damage-recipient set. This agreement count is not target-identification accuracy:
the first shot may concern a different opponent from later damage events.
The original two-endpoint counts and all prior model predictions are preserved.

Tracks retain fixed identities rather than following the nearest opponent at
each sample. Angular derivatives require consecutive valid ticks and unchanged
teams. Missing samples, invalid positions, non-alive states, and zero horizontal
distance interrupt tracks. Death events from the full replay latch exclusion
through window end, including retained-health/state lag. No gaps are interpolated.
Near-shot interval summaries require both endpoints inside the configured 100 ms
radius. Velocities use wrapped angular steps; correlations are null for constant
or insufficient observations. Bearing velocity includes both players' translation.

New tests cover perfect synthetic tracking, yaw wrap, stationary correlation,
missing ticks/players, fixed identities, death lag, team changes, precise event
association, float-ID rejection, float32 CSV round trips, and near-shot boundaries.
All 120 tests pass. Generated viewer scripts were executed against a mock DOM
through all 1,316 windows and 1,528 opponent selections, checking finite chart
coordinates. This is programmatic navigation verification, not browser visual QA.
Embedded metadata escaping and summary identity checks also have automated tests.

Saved local artifacts include per-sample errors/velocities, segment boundaries,
association sources, damage events, coverage, dependency versions, and source/input
hashes. The initial extraction stopped when comparing rounded CSV coordinates
with float32 parser values; comparison now reconstructs the original float32
precision, without accepting arbitrary coordinate tolerances. A subsequent run
added explicit damage-event markers with unchanged summary counts. No model was
trained, no detection threshold changed, and these inspected development cases
remain unsuitable for fresh held-out performance claims. Visibility, vertical
geometry, hitboxes, recoil, lag/subtick timing, and intended-target validation
remain prerequisites for interpreting these tracks as detection evidence.

## Association audit and pre-shot candidate correction

The audit verifies saved tracking/report/telemetry/event hashes, case/window
identities, and every positive same-weapon damage link. Across 17 development
cases it finds 847 window damage occurrences representing 836 distinct source
damage records. Repeated occurrences in overlapping windows remain explicit.

For each geometric/event disagreement, it compares the original fixed candidate
and recipient at the candidate's anchor and exactly one tick before damage.
Pairwise ordering changes require uninterrupted tracks for both players. The
audit does not infer visibility, intended target, or individual bullet assignment.
It distinguishes absent initial geometry, absent exact pre-damage geometry,
interrupted tracks, numeric ties, and insufficient temporal comparison. Numeric
tie tolerance is 1e-6 degrees and is not a detection cutoff.

An initial audit found 178 occurrences where the recipient was killed on the
first shot's tick and there was no later pre-damage comparison. Including six
occurrences with no initial candidate gives 184 first-shot disagreement
occurrences with same-tick damage and a recorded kill. Alive-only selection at
that tick can exclude the victim, revealing a post-shot death-state selection
bias rather than evidence that the player was aiming at another opponent.

A separate geometric candidate is now chosen at the exact preceding tick,
without looking at damage recipients. At assumed 64 Hz this is 15.625 ms before
the first shot tick. Missing ticks remain unavailable; no fallback/interpolation
is used. Shot-tick candidates and their original counts remain preserved.
Both selections and all associated fixed tracks are retained side by side.

Window-level candidate/event agreement is 438/485 for the preceding-tick anchor,
versus the preserved 274/480 at the shot tick. Coverage differs, so these are not
paired accuracy estimates. Across the same 847 damage occurrences, initial
agreement is 719 with the pre-shot anchor and 557 with the shot-tick anchor.
For pre-shot disagreements, 29 show uninterrupted pairwise ordering reversal,
six retain the original candidate as horizontally closer, 49 lack the initial
pair, 24 lack the pre-damage pair, 15 have no later pre-damage comparison, four
lack a candidate, and one has an interruption. No initial ranking inconsistencies
were found. These classifications describe geometry and timing, not causes of
cheating or verified target switches.

Retaining the additional candidates produces 1,554 tracks, with 1,521 having
consecutive valid samples, across the same 1,316 windows. Viewer deep links
select exact window/opponent indices. Programmatic mock-DOM checks exercised
all 1,316 windows and 1,554 tracks, all 13 audit example links, and three invalid
index cases. No browser visual verification is claimed. Tests cover the lethal
shot bias, both audit anchors, uninterrupted ordering changes, unavailable exact
ticks, numeric ties, malformed tracks, source checksum rejection before output,
and an end-to-end audit fixture. All 133 tests pass.

Original extraction/model evaluation artifacts are unchanged. No classifier or
threshold was changed; improved association agreement is not improved cheat
detection. Visibility, vertical/hitbox geometry, recoil, and lag/subtick timing
remain unresolved. All replay data, identities, and generated audit reports stay
local and excluded from Git.

## Fixed pre-shot tracking development comparison

Four fixed recipes were compared using the same 17 development cases and 15
connected participant components. Protocol choices were recorded before feature
loading and fitting. The original speed/acceleration and timing/direction scores
reproduce their earlier values exactly. The new recipes are pre-shot tracking
alone and original speed/acceleration with those tracking measurements appended.

The geometric opponent is selected at the exact tick before the first shot,
without consulting damage recipients. Features use the contiguous segment ending
at that tick, restricted to the preceding 200 ms: median absolute horizontal
error and median absolute yaw-minus-bearing velocity. At least eight valid
consecutive intervals are required per window, and five eligible windows per
case. Rates at the first included sample are excluded because they can depend
on an observation outside the period. Per-window medians are summarized by a
case median. No hits-only filter or post-shot tracking samples are used.

Of 1,316 windows, 1,300 meet eligibility; each case has 30–143 eligible windows.
All 17 cases are scored with no abstentions. Missing coverage would produce an
explicit abstention, with ineligible cases excluded from training rather than
imputed. Original participant components remain intact even if a case abstains.
All fitting/scaling uses eligible training groups only. New nonnegative features
use log1p. Balanced logistic regression C=1 and cutoff 0.5 are unchanged. There
was no parameter, feature-subset, threshold, or eligibility search in this run.

| Recipe | True positives | Missed cheating labels | False positives | True negatives |
| --- | ---: | ---: | ---: | ---: |
| Speed/acceleration | 5 | 3 | 2 | 7 |
| Timing/direction | 4 | 4 | 1 | 8 |
| Pre-shot tracking | 6 | 2 | 3 | 6 |
| Speed plus tracking | 6 | 2 | 0 | 9 |

The combined recipe catches E-09/E-11 and clears E-01/E-08 relative to the original
speed recipe, but newly misses D-2A. E-05 remains missed. D-3A scores 0.4790, near
the fixed 0.5 cutoff. This is a promising development tradeoff, not demonstrated
robustness or zero false-positive risk. All cases influenced prior development;
source labels do not specify aimbot activation. Nine legitimate cases are too
few to establish a reliable low false-positive rate. CV training folds overlap,
so independent binomial confidence intervals are not reported.

New tests verify independence from damage recipient/post-shot tracking values,
contiguous support and exact endpoints, window/case eligibility, rate boundaries,
abstention denominators, missing-group handling, and checksum mismatch rejection
before fitting. All 141 tests pass. Saved hashes, identical original scores,
original group membership, and complete group isolation were independently
checked across all four recipes. The four-panel static chart was visually
inspected. Generated reports/data stay local; no browser visual QA is claimed.

This is the appropriate checkpoint to stop tuning these cases. The combined
recipe is a candidate for a new freeze-and-evaluate workflow before acquiring
fresh labeled evaluation cases. No full-pool deployment model or new frozen
four-feature bundle was created in this experiment. Historical frozen baseline
artifacts and all earlier diagnostics remain preserved. Fresh cases, rather than
further threshold adjustment on these 17, are needed for the next performance claim.

## Frozen four-feature candidate and fresh-evaluation workflow

A new workflow freezes the combined speed/pre-shot-tracking candidate without
changing its features, cutoff, or eligibility. Its canonical tracking extractor
is shared by development and future evaluation. Re-extraction of all 17 local
development cases reproduced their complete saved tracking records and feature
vectors exactly, including all 1,300 eligible windows. The model is fitted on
those 17 development cases after verification; training scores are not reported
as detection performance. Exported logistic scores reproduce fitted scores to
1e-12. The prior grouped development comparison remains unchanged.

The frozen bundle records scaler, coefficients, cutoff, extraction configuration,
64 Hz timing assumption, eligibility, feature order, Python/dependency versions,
and hashes of all feature/scoring source modules. Load-time checks reject code,
runtime, checksum, or protocol drift. The local model is stored separately from
the original two-feature frozen baseline. No real fresh evaluation has run.

Participant exclusions include all 17 development demos and three previously
inspected tournament demos. The union of player-info and full identity-only tick
streams identifies 170 development participants and 181 excluded participants
in total. One older demo has an empty player-info table; identity-only ticks
recover its participants without requesting aim or position fields. Complete
identity streams also include disconnected/replaced players. Recomputed group
memberships are identical to the original 15 components, so this check does not
change the recorded development comparison.

Metadata-only reservation verifies demo/source-label hashes and exact targets.
It rejects any shared participant with recorded inspected data or between
reserved evaluation matches, as well as duplicate targets, matches, and demos.
A per-model registry prevents re-reserving the same participants under another
filename. Uninspected status is an explicit caller declaration, not proof of
non-use or annotation correctness. Label precision and cheat-subtype caveats
remain applicable.

Evaluation repeats preflight checks and writes exclusive central start receipts
before feature extraction. Reservations are consumed even when analysis fails
or the process is interrupted; copying a manifest does not bypass consumption.
There is no fitting during evaluation. Scored cases and abstentions are recorded
individually, with coverage, confusion counts, exact binomial intervals, and
independence limitations. Source sampling can induce dependence despite disjoint
recorded participant IDs.

Tests exercise four-feature export, protocol/code/dependency drift, all-player
and cross-evaluation overlap rejection, source tampering, reservation registry
reuse, copied manifests, interruption/failure consumption, receipt ordering,
metadata-only identity recovery, and a scored pipeline with fitting prohibited.
A synthetic freeze fixture also verifies full export/loading and exact feature
provenance. Usage is documented separately in docs/TRACKING_EVALUATION.md; the
README remains free of the removed validation/next-steps section. All models,
registries, demos, identities, and generated receipts stay local and ignored.

All 157 automated tests pass for this milestone. The actual frozen bundle also
passes checksum/runtime loading and all 17 extraction-equivalence receipts.
Fresh evaluation remains pending; no independent detection result is claimed.

## First fresh evaluation of the frozen tracking candidate

The README's obsolete classification/deployment sentence was removed separately.
The four-feature model and all extraction/scoring settings remained frozen during
new data selection and evaluation.

A metadata-only acquisition plan targeted eight cheating-labeled and 16 legitimate
selected player/matches from archive order, with a 16 GiB compressed-cache cap.
The quota completed after scanning 123 archive members and growing the cached
prefix to 11.08 GiB. Three candidates were rejected for participant overlap.
Nested ZIP CRCs, selected ZIP/demo hashes, exact participant IDs, and source-label
mappings were verified. Original source `isCheater` labels were used; source-model
prediction columns and aim features were not used for selection. Label IDs remain
rounded, with unique mappings within each replay and no conflicting encoded
source-label groups found. This is an archive-order convenience sample.

All 24 fresh matches contain 241 distinct recorded participants, disjoint from
each other and all 181 previously inspected participants. The frozen-model-bound
reservation and registry receipts preceded feature extraction. The selected cases
were not replaced after scoring. The full evaluation completed once at the fixed
0.5 cutoff, without fitting, threshold search, or eligibility changes.

| Source label | Flagged | Unflagged | Abstained |
| --- | ---: | ---: | ---: |
| Cheating | 8 | 0 | 0 |
| Legitimate | 11 | 5 | 0 |

All 24 cases were scored. Cheating-label recall is 8/8 (100%; exact 95% interval
63.1–100%). The false-positive rate is 11/16 (68.75%; exact 95% interval
41.3–89.0%). These intervals assume independent outcomes; sampling and source
limitations remain. Labels describe cheating in a player/match, without confirmed
aimbot subtype or assisted-tick annotations. These counts do not establish
population-wide or aimbot-specific performance.

The development result of zero false flags did not generalize. The frozen
candidate overflags legitimate cases and is unsuitable as a detector at the
current cutoff. These results do not isolate overfitting, distribution shift,
label limitations, or measurement issues as the sole cause. They are preserved
as a failed low-false-positive generalization test, not explained away or used to
retune the reported evaluation.

The run produced 1,273 structurally valid firearm windows, of which 1,220 met
pre-shot tracking eligibility. All cases retain round-event warnings. Independent
recomputation reproduced every case identity/label, four-feature vector, exported
score, and fixed-cutoff flag. The model checksum/runtime still match the frozen
bundle. No model or cutoff was changed after observing outcomes.

The local report shows all cases, confusion counts, abstentions, source hashes,
and uncertainty. Renderer tests reject inconsistent receipts/metrics/flags and
escape analysis error text. The cohort is marked consumed in both the per-model
reservation registry and a local usage receipt. Historical uninspected manifests
remain snapshots; tuning on this feedback makes these cases development data.
Future acquisition now honors registry participants/matches to prevent
rediscovering a used cohort. The initial acquisition code remains reproducible at
commit `54d3068`; the subsequent registry improvement does not alter its results.

All 166 automated tests pass. Raw demos, identities, models, selection plans,
registries, and generated evaluation reports remain local and ignored by Git.
Further work should investigate the false flags and improve legitimate-case
coverage/measurement specificity before freezing another candidate. A new fresh
cohort will be needed for the next independent performance claim.

## False-flag arithmetic and feature/context diagnosis

A post-evaluation diagnostic verifies model/source receipts and reconstructs all
24 frozen scores from standardized log1p feature contributions and the intercept.
This explains the model's arithmetic, not a causal reason for player behavior.
The frozen candidate, threshold, and fresh evaluation remain unchanged.

The original nine legitimate cases have median near-shot acceleration 300.517,
versus 462.999 in the 16 newly inspected legitimate cases. Median pre-shot
horizontal error is 4.5731 degrees versus 2.7748 degrees. Both differences push
this fitted model toward more flags. The mean legitimate margin shifts from
-1.3910 to +0.1416: acceleration contributes approximately +0.8397 of this change,
horizontal error +0.7051, speed +0.2098, and relative velocity -0.2219. These are
observed sample differences and an exact arithmetic decomposition, not a single
proven cause of generalization failure.

Acceleration is the largest positive feature term in seven false flags; tighter
horizontal alignment is largest in four. Seven of the 11 false flags lie inside
the original legitimate minimum/maximum range on every feature, so simple
marginal range checks would not reject them. Predictive feature overlap remains.

The difference persists in descriptive shared-weapon summaries. For AK-47, nine
eligible legitimate cases in each cohort have median case/window acceleration
276.959 versus 534.037 and horizontal error 6.620 versus 3.037 degrees. These
summaries require five jointly eligible windows per case and two cases per
cohort, with equal case weighting. They are not the original mixed-weapon model
inputs. This observation does not establish causality or fully control weapon,
skill, range, visibility, or recoil; weapon mix alone is not a sufficient
explanation for the observed difference.

Local reports include feature distributions, margin shifts, every preserved
evaluation decision, and 24 trajectory viewers. Scientific charts were visually
inspected. Viewer scripts passed mock-DOM navigation through 1,273 windows and
1,478 tracks with finite coordinates. No browser visual QA is claimed.

## Expanded inspected development pool and fixed comparison

The original 17 cases and consumed 24-case evaluation are now explicitly combined
into development data: 41 cases, with 16 cheating labels and 25 legitimate labels,
in 39 connected full-participant components. Verified local links reuse existing
artifacts without copying/relabeling demos or modifying the frozen evaluation.
All targets, matches, and demo hashes are unique; source receipts preserve the
original case identities. The prior fresh cohort is not a reusable holdout.

The four existing recipes were compared once with unchanged C=1, cutoff 0.5,
transformations and eligibility rules. Whole components are held out; all
scaling/fitting uses eligible training groups only. All cases scored.

| Recipe | True positives | Missed cheating labels | False positives | True negatives |
| --- | ---: | ---: | ---: | ---: |
| Speed/acceleration | 11 | 5 | 8 | 17 |
| Timing/direction | 10 | 6 | 3 | 22 |
| Pre-shot tracking | 13 | 3 | 3 | 22 |
| Speed plus tracking | 13 | 3 | 3 | 22 |

These are post-feedback development diagnostics, not independent improvements or
revised evaluation estimates. Tracking alone and speed plus tracking have the
same aggregate counts; the additional speed features have not demonstrated an
aggregate benefit here. The remaining three legitimate false flags are still
material, and neither recipe is selected or frozen as a replacement. Broader
legitimate coverage changes development behavior but does not establish a reliable
low false-positive rate. A new fresh evaluation will be required after further
development; the original frozen 8/8 and 11/16 result remains the recorded failure.

All 175 tests pass, including contribution reconstruction, cohort/label separation,
receipt rejection before output, shared-weapon identity checks, explicit inspected
pool roles, immutable source reuse, and duplicate/checksum rejection. Exact pool
membership, all 39 full-participant groups, complete per-case predictions and
fold separation were independently verified. No historical model, threshold,
reserved manifest or prediction changed. Guides are in docs/FAILURE_ANALYSIS.md;
all generated data, identities and charts remain local and ignored by Git.

## Negative acquisition-dynamics development experiment

A separate experimental module evaluates pre-shot concentration/settling without
changing any frozen extractor or classifier. The fixed hypothesis is that a
concentrated player-supported angle closure followed by lower relative motion
might be more specific than ordinary precision/acceleration alone.

Features use the same geometrically selected opponent and a contiguous segment
ending exactly one tick before the first shot, restricted to 500 ms and at least
16 intervals. Positive observed error reduction is capped by the reduction a yaw
step would create with bearing held fixed. Opponent motion alone does not create
a supported acquisition. A qualifying transition needs net closure and total
supported closure of at least three degrees. Concentration is the largest
supported interval divided by total supported closure. Settling ratio uses the
median relative speed strictly after that interval, divided by its relative
speed, requiring three later pre-shot intervals. First peak ties choose the
earlier interval. Missing settling is never imputed as zero.

The case recipe requires five valid windows and three usable transitions. It
uses transition fraction, median concentration and median settling ratio; a
second recipe appends these to original tracking features. All choices were
saved before fitting. C=1, balanced logistic regression, log1p, training-only
scaling, cutoff 0.5, and the same 39 participant components remain fixed. These
are unvalidated engineering cutoffs, not calibrated detection thresholds.

There are 2,508 valid pre-shot windows, 613 qualifying transitions and 560 with
observable settling. Every one of the 41 cases meets coverage; none abstains.

| Recipe | True positives | Missed cheating labels | False positives | True negatives |
| --- | ---: | ---: | ---: | ---: |
| Pre-shot tracking, unchanged reference | 13 | 3 | 3 | 22 |
| Speed plus tracking, unchanged reference | 13 | 3 | 3 | 22 |
| Acquisition dynamics | 13 | 3 | 4 | 21 |
| Tracking plus dynamics | 13 | 3 | 5 | 20 |

Concentration medians are 0.14996 for cheating labels and 0.15196 for legitimate
labels; settling ratio medians are 0.17586 and 0.16276. These sample summaries
strongly overlap. The fixed new recipes do not improve the development confusion
counts, adding false flags without more cheating-label flags. Neither is adopted,
selected or frozen. No threshold/eligibility search followed these outcomes.
This is inspected development feedback, not another independent evaluation.

Tests cover abrupt versus smooth closure, opponent-only motion, stationary
alignment, missing late settling, interrupted/noninteger samples, post-shot and
other-opponent independence, yaw wrap, case coverage and baseline protocol
rejection before fitting. All 184 tests pass. A synthetic exact-zero expectation
was changed to a floating tolerance for approximately 1e-13-degree arithmetic
roundoff; it does not affect the three-degree transition cutoff. A second run
also adds receipt/label/group guards, reproducing all model predictions, scaler
statistics and coefficients exactly. Baseline records and all full-participant
fold boundaries were independently checked. Saved hashes match current source.

The original frozen model still loads without code/runtime drift and its fresh
8/8 cheating flags and 11/16 legitimate false flags are preserved. No new full-pool
model or independent success claim is produced. Usage and interpretation are in
docs/ACQUISITION_DYNAMICS.md. All replay data, identities and generated artifacts
remain local and ignored by Git.

## Sampled combat evidence and 3D field feasibility audit

A fixed post-evaluation sample covers R-002/R-014/R-013 false flags, legitimate
unflagged comparisons R-001/R-003, and cheating-labeled flagged R-017. Each provides
three chronological windows with matching positive damage at/after the first shot
and three without, totaling 36. Earlier padding damage is separate. This is a
selected diagnostic sample, not an accuracy estimate.

Every selected case's frozen score, replay/report/tracking/telemetry checksums,
exact damage links and original horizontal candidates reproduce. Sparse field
extraction matches saved shooter X/Y/Z, yaw/pitch, health, state and team values
at source precision. There are 33 comparable exact pre-first-shot snapshots;
three R-013 shooter samples are absent from both saved telemetry and sparse
extraction. Missing samples are not interpolated or declared legitimate evidence.

All six demos omit the requested view-offset vector/axis columns. Recoil,
crouch, scoped/weapon, spotted/mask, head-constraint and hitbox-set fields are
returned. Head-constraint vectors are mostly zero with occasional nonzero values;
no measured world eye/head or hitbox coordinates were validated. Column omission
and observed zeros remain distinct statuses. Neither spotted fields nor hitbox
indices are promoted to visibility or head-position ground truth.

A separate body-origin ray proxy includes recorded Z and pitch using the documented
Source SDK view-vector convention. It is not eye-to-head/hitbox aim error and uses
no invented eye/head heights or guessed recoil correction. It changes the nearest
candidate in one of 33 comparable snapshots, in unflagged control R-003. For 18
damage-bearing windows, initial candidate/event-recipient set agreement is 14/18
for horizontal ranking and 15/18 for the origin proxy. These are not intended-target
accuracy figures. The sample does not establish vertical ambiguity as the false-
flag cause and does not justify changing classifier inputs.

The renderer keeps all 36 game-review bookmarks explicitly pending. Eye/head
geometry and visibility remain unverified; attempts to promote the proxy audit
into validated geometry are rejected. No rendered CS2 gameplay was opened; the
standard application/Steam locations checked did not contain CS2. A local review
template records demo paths and precise ticks for later rendered-gameplay review.
No model, threshold or recorded outcome changed.

Tests cover Source-convention vertical proxy geometry, yaw/height ranking,
coincident/invalid origins, death states and missing samples, exact property
omission versus observed zero, padding-aware window selection, source receipt
rejection, HTML escaping, checksum validation and pending-review semantics.
All 194 automated tests pass. Six case receipts, plan/source hashes, 36 pending
bookmarks and frozen runtime integrity were independently verified. Details are
in docs/MEASUREMENT_AUDIT.md; all observations and identities remain local.


## Offline context experiment and expanded legitimate controls

Scope remains offline demo detection; live integration is not a development milestone.
A fixed weapon-family/grouped-shot normalization experiment was recorded before fitting on the 41 inspected development cases. References use legitimate training cases only, equal case weights and fixed sparse fallbacks; scaling and C=1 balanced logistic regression are fitted within each participant-group fold. The same joint-window/log-aggregation control gave TP13/FN3/FP3/TN22; context centering gave TP11/FN5/FP5/TN20, with no abstentions. This negative experiment is not adopted or frozen. See docs/WEAPON_CONTEXT.md.

Cache-only acquisition then selected 14 additional legitimate matches, short of the requested 16 because the existing compressed prefix ended. All selected nested ZIPs passed CRC checks, demo/source hashes and full participant exclusions. No additional bytes were downloaded. All 14 extractions completed with round-event warnings and no structural violations. These cases are explicitly inspected development data and registered for participant exclusion from future acquisition/evaluation, not a new holdout.

The combined pool contains 55 cases (16 cheating, 39 legitimate) in 53 connected participant components. Repeating the four existing recipes with group-held-out training and no threshold search produced:

| Recipe | TP | FN | FP | TN | Abstentions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Speed/acceleration | 10 | 6 | 14 | 25 | 0 |
| Timing/direction | 10 | 6 | 8 | 31 | 0 |
| Pre-shot tracking | 13 | 3 | 6 | 33 | 0 |
| Speed + tracking | 13 | 3 | 5 | 34 | 0 |

These are post-feedback development diagnostics, not fresh performance estimates. False flags remain too frequent for the intended goal. The previous independent frozen result (TP8/FN0/FP11/TN5) remains unchanged. Frozen model and runtime hashes were rechecked; cached archive length is unchanged. All demos, identities, models, receipts and generated reports remain local and ignored by Git.

All 204 tests pass, including fold-local context references, cache-only zero-download behavior, single-label development acquisition and extension manifest guards. Local reports are in outputs/xguardian/weapon-context-v1 and outputs/xguardian/development-v4-models.


## Fixed nonlinear model capacity check

One RBF support-vector recipe tested nonlinear interactions of the same four speed/tracking measurements on the inspected 55-case, 53-participant-component development pool. Log1p, scaling, balanced class weights and kernel width use training groups only. C=1 and decision cutoff zero were fixed before fitting; no calibration, parameter/feature/cutoff search or full-pool fit occurred. Decision margins are not probabilities.

The copied linear baseline remains TP13/FN3/FP5/TN34. The fixed RBF recipe gave TP12/FN4/FP5/TN34, zero abstentions. It missed one additional cheating-labeled case and retained the same five legitimate false flags; it is not adopted or frozen. Local output includes error/decision-change links for trajectory review. No claim is made that changing model family resolves the measurement or labeling limits.

All 55 saved decision margins independently reconstruct from the recorded training scaler, gamma, support cases, dual coefficients and intercept. Baseline predictions are unchanged and frozen runtime integrity passes. All 218 tests pass, including participant leakage, margin reconstruction, missing/single-class coverage, constant inputs and tampered development receipt rejection. See docs/NONLINEAR_MODELS.md. The previous independent frozen result remains unchanged.


## Shared errors and false-positive-first policy audit

The existing 55-case/53-participant-component development results were independently reproduced before explanation or new calibration. All five shared legitimate false flags have their largest positive margin contribution from horizontal pre-shot error (four) or relative yaw-minus-bearing velocity (one). The strongest legitimate score, 0.891, exceeds eleven of sixteen cheating-labeled scores. The three false negatives have nearest legitimate training neighbours at standardized log-feature distances approximately 0.31, 0.91 and 0.30. These describe classifier arithmetic and overlap, not causal behavior or intended-target ground truth.

Chronological half-match summaries show differing distributions: missed cheating case E-05 scores 0.827/0.001 while legitimate false flag L-002 scores 0.262/0.960. Same-fold descriptive half scores are not independent predictions or aimbot activation annotations. Merely selecting high-scoring stretches would also select legitimate play. A post-hoc common cutoff that includes the fourteenth cheating case at 0.4353 retains all five false flags; this is not a newly selected policy.

One fixed conservative operating-policy experiment sets each outer test component's cutoff to the maximum legitimate inner out-of-group score computed entirely within outer training data, then flags strictly above that cutoff. Scaling and all fitting stay within their training folds; incomplete inner coverage abstains rather than substituting fitted scores. No cutoff/parameter/feature search or full-pool model fit occurs. Result: TP5/FN11/FP1/TN38, zero abstentions. The strongest legitimate outlier remains flagged because outer training calibration does not represent it adequately. Inner and outer models differ, so the policy has no population FPR guarantee. It is not adopted or frozen.

Illustrative base-rate arithmetic with 1% cheating prevalence and 81.25% recall gives flag precision 7.6% at 10% FPR, 45.1% at 1% FPR and 89.1% at 0.1% FPR. These are assumed scenarios, not measured deployment performance. To support a one-sided exact 95% upper FPR bound at 1% with zero observed errors requires 299 independent representative legitimate cases; at 0.1%, 2,995. Current inspected grouped-CV counts do not establish either bound.

All 55 explanatory scores reproduce original held-out scores and each case is excluded from its explanatory training neighbours. All 53 nested outer folds and recorded inner calibration cutoffs were independently checked. Explanations match folds by case identity, never positional prediction order. All 231 tests pass, covering outer/inner leakage, calibration/decision reconstruction, missing-class abstention, ties, base-rate/sample-size arithmetic, invalid inputs, explanatory training contamination, chronological source alignment and escaped/receipt-checked rendering. Source hashes and frozen runtime integrity pass. No prior frozen or diagnostic predictions changed. See docs/ERROR_AUDIT.md; local report is outputs/xguardian/shared-error-audit-v3/index.html.


## Repeated correction consistency experiment

The rejected conservative cutoff remains inactive. A new fixed measurement experiment tests repeated pre-shot correction shape and cross-window gain consistency, rather than imposing a stricter flag threshold. It inherits the contiguous 500 ms, 16-interval and three-degree player-supported closure checks from acquisition dynamics. Opponent-only movement, static precision, discontinuities and signed-error branch crossings do not qualify. Signed relative angular velocity is regressed through the origin against previous signed horizontal error. Positive-gain fit R-squared, relative gain MAD and positive-fit fraction form three case features. Five valid windows and three positive fits are required; missing coverage abstains rather than assigning a legitimate label. Poor fits are retained, not filtered by a searched quality cutoff.

All 55 cases in 53 full participant components are covered, with 3,219 valid windows and 826 qualifying positive-gain fits. Fixed C=1 balanced logistic regression, training-fold scaling, log1p and cutoff 0.5 yield TP13/FN3/FP7/TN32 for consistency alone and TP13/FN3/FP6/TN33 when appended to the two tracking features. Both have zero abstentions. The copied existing speed/tracking recipe remains TP13/FN3/FP5/TN34. Median case gain variation is 0.419 for cheating labels and 0.424 for legitimate labels; median fit R-squared is 0.0134 and 0.0. The particular response-shape hypothesis did not improve specificity, so neither recipe is adopted or frozen. No eligibility, feature-subset, parameter or cutoff search was performed.

Every window measurement/exclusion is saved locally. All 110 new predictions independently reconstruct from saved feature vectors, fold scalers, coefficients and intercepts. Prior predictions are unchanged and frozen runtime integrity passes. All 239 tests pass, including known synthetic gain recovery, opponent-only/static closure rejection, pre-shot-only invariance, cross-window dispersion, insufficient-coverage abstention, constant-response unavailability, gaps and angle wrapping. See docs/CORRECTION_CONSISTENCY.md. This remains post-feedback development work, not a fresh evaluation or established cheat-specific signal.


## Candidate ambiguity diagnostic

A fixed post-feedback sample covers all five shared legitimate false flags, all three current linear-model misses and six controls (three unflagged legitimate and three flagged cheating-labeled). All 853 windows from 14 cases are included. Sparse replay extraction requests the exact pre-first-shot tick and snapshots 100/200 ms earlier, restricted to original windows. All valid opposing players are ranked; missing comparisons remain unavailable and single-opponent snapshots do not invent runner-up gaps. Replay/report/tracking/telemetry/event checksums, shooter source precision and window identities are checked. All 853 canonical endpoint choices reproduce, with 847 valid candidates and six matching unavailable endpoints.

The false-flag cases have median runner-up gaps 7.75–18.88° and nearest-identity stability 83.3–93.9% at 200 ms. Median-of-case summaries are 10.46°/85.7% for false flags, 18.53°/95.1% for misses, 14.89°/95.8% for legitimate controls and 19.88°/89.7% for cheating controls. This descriptive selected sample does not support frequent near-tie candidate switching as the main shared error explanation. No ambiguity filter, threshold search or classifier change is introduced. Stable horizontal selection does not establish intended target or visibility and does not rule out individual ambiguous windows.

All 247 tests pass, including exact-tick/tie ranking, death/team/life-state filtering, fixed-identity comparisons, missing-pair denominators, single-opponent gaps, duplicate rejection and escaped/receipt-checked rendering. All 853 candidate identities, receipt hashes and frozen runtime integrity were independently verified. Local HTML includes per-case/per-window review tables and links to existing trajectories. See docs/CANDIDATE_AUDIT.md. All raw/generated data remains local; historical decisions and rejected-policy status are unchanged.


## Target-independent two-axis pre-shot shape

A fixed new experiment measures the shooter's own view-angle path without opponent or damage selection. The original alive segment must provide 16 contiguous intervals ending one tick before firing, within 500 ms and the original window. Missing/non-active/non-alive/invalid-angle samples break continuity. Existing core path efficiency, mean direction change, speed CV and stop fraction are aggregated by case median, with at least five eligible windows. Stationary aim is retained with the core's defined measurements rather than treated as cheating. Source identities and report/telemetry/event/tracking checksums are checked before extraction.

Across all 55 cases/53 participant groups, 3,240 windows are eligible and 83 excluded; every case is covered. Fixed training-fold scaling, log1p, C=1 balanced logistic regression and cutoff 0.5 produce TP11/FN5/FP11/TN28 for shape alone and TP13/FN3/FP5/TN34 when appended to existing speed/tracking. No case abstains. The latter equals the original aggregate counts but corrects R-009 while introducing legitimate false flag L-005, and recovers R-020 while missing R-024. There is no demonstrated net specificity/recall improvement, so neither recipe is adopted or frozen. No feature/eligibility/parameter/cutoff search was performed. The conservative cutoff remains inactive.

All 110 new predictions independently reconstruct from case vectors, fold scalers, coefficients and intercepts. Prior baseline decisions are identical and frozen runtime integrity passes. All 255 tests pass, including two-axis straight/reversing/stationary trajectories, yaw wrap, post-shot invariance, alive-segment/gap handling, insufficient coverage and duplicate/tickrate guards. See docs/PRE_SHOT_SHAPE.md; local diagnostic output is outputs/xguardian/pre-shot-shape-v1. Data/models/reports remain local. This is inspected development feedback, not new independent accuracy evidence.


## Stable-prealignment exclusion, repeat support and event review

Tested the proposed exclusion idea on all 55 inspected cases, using new exact sparse snapshots for every original window. All 3,323 endpoint candidate selections reproduce canonical extraction (3,293 available and 30 matching unavailable). Protocol/sample/source hashes and exact snapshot ticks are checked. One fixed rule excludes windows with the same nearest opponent, error at most three degrees and runner-up gap at least three degrees (or a sole opponent) at all three pre-shot/100/200 ms snapshots. Unknown/ambiguous contexts are retained. This is a sampled geometric proxy, not proof of ordinary legitimate aim. Three-degree choices were recorded before fitting without eligibility/cutoff search.

Retained cases require five eligible tracking windows spanning three different rounds. Round counts are support constraints, not a claim of statistically independent encounters. Original component-wise speed/tracking medians are recomputed on retained windows and the same C=1/log1p/training-scaled balanced classifier is fitted within whole participant-group folds at cutoff 0.5. The rule excludes 1,259 windows: 764/1,403 windows in cheating-labeled cases and 495/1,920 in legitimate cases. Median removed fraction per case is 56.2% versus 25.9%.

Result: TP9/FN7/FP17/TN22, no abstentions, compared with unchanged original TP13/FN3/FP5/TN34. Every case retains at least ten eligible windows across at least five rounds. Worse performance is therefore not disguised by missing decisions. Stable alignment can also occur with assisted aim; this exclusion removes useful evidence and is rejected. Original baseline is retained; no frozen detector, threshold or historical evaluation changes. The conservative cutoff remains inactive.

The event-level review workflow includes all 3,323 original windows, including excluded ones, and a manageable first pass of 42 chronological events across three rounds in each of 14 fixed error/control cases. Source labels and model scores are omitted from the editable CSV and viewer presentation. Every event starts pending. Exact demo identity/hash, player, round and tick boundaries are immutable on annotation import. Reviewed observations require accepted categorical values, reviewer, evidence reference and note; unsupported claims such as confirmed cheat activation are rejected. Review source/evidence remain reviewer attestations. Validation creates separate human observations, never automatic training labels or cheat-activation ground truth. Initial template check returns zero reviewed and 3,323 pending.

All 273 tests pass, including stable/changed/ambiguous/missing selection, sole-opponent versus tie semantics, component-wise feature reproduction, multi-round support, coverage abstention, window/candidate identities, post-shot/damage invariance, annotation metadata/coverage/category/provenance guards and label-omitting exact-window review links. All 55 new decisions independently reconstruct; original decisions, source hashes and frozen runtime integrity pass. All data/models/generated outputs remain local. See docs/ENCOUNTER_FILTER.md; final local outputs are candidate-ambiguity-all-v2 and encounter-filter-v3, including event-review.html.


## Published source-case attribution and focused event references

The rejected exclusion rule remains inactive. Reviewed the supplied artifact's study/adversarial metadata, source paper and author case descriptions. Added separate source-attributed subtype evidence for D-1A (author-described aimbot), D-1B (aimbot plus wallhack) and D-2B (wallhack-only). Original 55 binary labels remain identical; no positive is removed or relabeled. Other positive subtypes stay unknown. D-2B is already flagged, so this finding does not explain the current three misses or improve the original TP13/FN3/FP5/TN34 development result. Generic cheating metrics are not newly validated aimbot-specific recall.

A source-provenance trap was caught before finalization: the author viewer's frame numbers are split-CSV row indices, not replay ticks, and twenty-elimination batches can include multiple players. Resetting a selected player's row indices yields plausible but wrong event references. The exploratory per-player mapping output was invalidated. Final extraction scans 145 cached positive split CSV members, verifies ZIP member identity/CRC/size and preserves complete batch row indices. Rounded identities require a unique exact replay-participant encoding. Four event references are disambiguated by copied-image CRC/size metadata; one has a unique matching batch. Ambiguous source matches fail rather than being guessed. Image-copy metadata is not claimed as cryptographic equality or rendered review.

Five final references match recorded replay death events: D-1A kill 96360, D-1B kills 102387/102462/103056, and D-2B kill 52221. Each links to an existing canonical window and seven saved two-axis samples around the event. All five rendered-gameplay reviews are pending. No controlled activation labels, event-level ground truth or training labels are created. Source descriptions remain attributed case narratives, and the mappings remain provisional review aids.

All 285 tests pass. Checks cover data-only range parsing, full-batch row units, rounded-identity ambiguity, source-window consistency, mixed/gapped/missing events, ambiguous batch selection, archive copy identity and cache CRC/truncation. All 55 original labels, source hashes, five raw event references, local links and frozen runtime integrity were independently verified. Small public source snapshots/scripts were saved locally; no raw demos or whole datasets were newly downloaded. See docs/SOURCE_ANCHORS.md; final local review index is outputs/xguardian/source-anchors-v3/index.html. Historical outcomes and all pending human observations remain unchanged.


## Ten-interval rendered-gameplay comparison pack

Actual gameplay review is pending: standard local application/Steam locations contain no CS2/Steam installation, and the user confirmed no installation is available. No rendered review is claimed. Built a bounded package containing the five source-attributed references and one eligible kill encounter from each of five falsely flagged legitimate players. Fixed control matching prefers exact weapon, then family, then earliest eligible kill; the actual pack has three exact and two family matches. Source/player/weapon/segment/window identity and pre-shot tracking coverage are checked. There is no window-score selection or model fitting.

The ten unique encounters use eight unique demos, with eight seconds before and four seconds after each event (about two minutes of normal-speed footage). Reviewer aliases are shuffled deterministically; source labels, model scores and roles are omitted from reviewer-facing files. A private selection key preserves provenance without claiming full blinding. Default output is metadata-only and references 935,148,773 bytes of existing demos; optional include-demos export copies only the eight unique files and verifies hashes. No demos were copied unnecessarily or uploaded. The original input files remain intact.

Setup and per-event loading/seek instructions explicitly require waiting for demo loading, selecting the indicated first-person POV, disabling X-Ray, checking the event tick and recording the playback build. Instructions are prepared, not runtime-tested here. There is no game plugin or live integration. Annotation import preserves immutable identities/ticks and requires reported build, verified POV/X-Ray state, reviewer, accepted categories, evidence reference and notes. Pending/unavailable playback cannot become a negative training example. Reports remain attestations, and suspicious observations are not confirmed activation labels.

All 298 tests pass. Ten bookmark ranges, eight original demo hashes, unique queue links, HTML/command links and source receipts were independently verified. Initial annotation import produces zero reviewed and all 3,323 original events pending; no training labels are created. Frozen runtime integrity and original detector results remain unchanged. See docs/GAMEPLAY_REVIEW.md; local metadata pack is outputs/xguardian/gameplay-review-v2/index.html. Actual visual comparison remains blocked on access to CS2 playback or rendered clips.


## CS2.APP browser reconstruction pilot

Used the user-supplied browser viewer to load D-1A and R-002, switch to 3D, select the intended player and enter the labeled POV mode. Normal-speed/0.25x playback and timeline seeking were exercised; the intended MAG-7 and AWP kill-feed identities were observed. Screenshots and visible UI timeline landmarks were saved locally. The site advertises local parsing and the UI reported no upload; analytics consent was declined. No independent network audit or native-renderer equivalence test was performed.

The R-002 reconstruction keeps a similar viewing angle near cover across before/after frames, consistent with angle holding but not establishing why the model flags it. Geometry is simplified and player information remains visible beyond geometry. No X-Ray-off control was found in the inspected controls, and original visibility/client prediction/smoke fidelity remain unverified. These two capability examples are not the matched ten-event comparison. The assistant pilot is separate from human annotations: 2 browser context examples, 0 verified native reviews, no activation/training labels. The full native review queue remains pending.

Browser timeline origin and displayed round/time differ from raw replay ticks; a global affine clock conversion was not reliable. Kill landmarks and attacker/victim/weapon feed checks were used instead of assuming elapsed time maps directly to raw ticks. Added a browser_reconstruction observation source with mandatory not_assessable assistance assessment and distinct source/rendered-gameplay counts. Tests reject promotion of reconstructed views into assistance verdicts. See docs/BROWSER_REVIEW.md and local outputs/xguardian/browser-viewer-pilot/index.html. Original detector results remain unchanged by this pilot.

## Explicit server-phase audit after browser alignment

Direct server game-rule properties confirmed warmup contamination in legacy active-round analysis: D-1A tick 788 is warmup=true/match-started=false, while later live examples have the opposite flags. Audited every original supporting telemetry tick across all 55 inspected cases. Global repeated boolean flags are collapsed only when consistent; missing, conflicting or non-boolean flags are unknown. A window passes only when every supporting sample explicitly reports warmup=false and match-started=true. Boundary windows are excluded in full rather than retaining stale partially trimmed features. This supplements original round/life rules and does not claim to resolve every game-phase anomaly.

Found 305 warmup windows and 3,018 phase-passing windows among 3,323, affecting 37 cases. No window has unknown phase in this run. The same four-feature, C=1/log1p/training-scaled classifier at cutoff 0.5, with the same full-participant groups, yields TP13/FN3/FP6/TN33 with zero abstentions on phase-checked inputs. The extra false flag is R-012. R-002 had no warmup windows, so phase contamination cannot explain its error. The original TP13/FN3/FP5/TN34 results are preserved as legacy-protocol outcomes, not silently reinterpreted as live-only performance. Data validity is not selected by whichever protocol has the more flattering count.

The new phase helpers and explicit phase-checked development feature path are implemented. Legacy gameplay/batch source modules remain unchanged for frozen-runtime reproducibility; this audit is not a silent default-extractor upgrade or deployed replacement model. Future model work must explicitly use phase-checked inputs, and a canonical extractor/version migration remains required before changed inputs can be frozen/deployed. No cutoff, eligibility or feature search was performed. The rejected stable-alignment filter remains inactive.

All 310 tests pass. All 55 phase-checked vectors/decisions independently reconstruct, phase counts reproduce, source/pilot screenshot hashes and links pass, legacy predictions are identical and frozen runtime integrity passes. New tests cover global boolean replication, warmup boundaries, explicit match-start, missing/conflicting/string flags, invalid ticks and browser-source separation. See docs/PHASE_AUDIT.md; local phase output is outputs/xguardian/phase-checked-v1. All raw data, screenshots and generated reports remain local and ignored by Git.

## v0.6 extraction with explicit server-phase gating

Added separate phase_gameplay and phase_batch entry points. They intersect existing round/life eligibility with explicit warmup=false and match-started=true flags before engagement grouping, then rebuild segments, event assignments and features. Missing properties fail extraction; unknown samples are excluded. Empty live evidence is reported as insufficient_live_evidence, never a legitimate verdict. Legacy extraction and frozen classifier modules remain unchanged; legacy feature readers reject v0.6 reports.

All 317 tests pass, including phase-boundary regrouping, independence from excluded warmup angles, preserved death latch, missing-phase failure, zero-live-evidence handling, version rejection, exclusive exports and isolated batch failures. A real D-1B batch run rebuilt 96 live windows and excluded 10,834 previously active warmup samples. Independent checks against exported telemetry verified every window is live and confined to one segment, warmup events are unassigned, core features reproduce within 1e-8, runtime hashes match and frozen model integrity still passes. The batch retains its existing round-anomaly warning.

This is an extraction correction, not evidence of improved detection. The earlier drop-whole-window phase audit is a different protocol from regenerated v0.6 engagements. No new model was trained or evaluated on v0.6 reports. Raw demos and generated smoke outputs remain local and ignored. See docs/PHASE_GAMEPLAY.md.

## Full v0.6 development rebuild and fixed grouped comparison

Rebuilt all 55 inspected development cases with phase_batch, producing 3,018 live windows, excluding 230,640 previously active warmup samples, with zero extraction errors or structural window violations. All cases retain existing round-event warnings. Re-extracted geometric opponent tracks for the regenerated windows and evaluated the same four features, log1p, training-only scaling, C=1 balanced logistic regression, cutoff 0.5 and original 53 participant groups. No labels, cutoff, feature recipe or eligibility rules changed.

Result: TP13/FN3/FP6/TN33, no abstentions, versus preserved legacy TP13/FN3/FP5/TN34. R-012 is the only changed flag. False flags: D-3A, R-002, R-009, R-012, L-002, L-013. Misses: D-2A, E-05, R-020. The false-positive fraction of 6/39 remains unsuitable for the intended goal. On these inputs the regenerated vectors match the earlier phase audit, but this does not establish equivalence of the procedures for other boundary cases or improve detection.

Added a separate explicit v0.6 comparison reader with source/protocol/runtime receipt checks and exported live-support validation, preserving frozen legacy modules. All 322 tests pass; five new tests cover explicit version/configuration rejection without input mutation, missing-evidence abstention, live/segment/duplicate support checks, source receipt rejection and fixed-group comparison output. All 55 saved scores independently reproduce from recorded fold parameters; training-only means/scales, participant separation, code/input receipts and frozen runtime integrity pass. No replacement model is frozen or deployed. All demos and generated outputs remain local and ignored. See docs/PHASE_DEVELOPMENT.md and outputs/xguardian/v06-development-v1/comparison/report.md.

## Saved-fold v0.6 errors and matched-control investigation

Added an explanation-only workflow for the 55 phase-clean development cases. It validates saved receipts and reconstructs original feature vectors/scores, then records four-feature log-odds terms, nearby correctly classified training controls in each case's fold-scaled space, and descriptive round/weapon subsets requiring the existing five-window minimum. No fitting, cutoff/filter change, source relabeling or model promotion occurs. Label/correctness-based control selection is explicitly inspected and descriptive, not independent evidence. Context scores are not activation labels or independent decisions.

The six false flags show precision overlap: pre-shot error is the largest positive term in five, relative rate in D-3A. R-002 and L-002 have nearby correctly flagged cheating controls; D-2A and E-05 have nearby correctly classified legitimate controls. D-3A exceeds 0.5 in four of seven scorable rounds, showing that repeated high context scores also occur in legitimate play. R-002's high context scores include Glock and silenced M4, while AWP scores are high for both legitimate L-002 and missed R-020. Only 33/39 legitimate cases have any scorable round, versus 16/16 cheating; R-012 has none. These findings do not validate a persistence/weapon exclusion rule. Original TP13/FN3/FP6/TN33 and historical artifacts are unchanged.

All 326 tests pass. New tests cover contribution reconstruction without mutation, invalid features/scales, correctly classified training-only neighbour selection, held-out identity, context identity/coverage and tampered receipts. Independently verified 55 whole-case explanations, all 421 available context scores, nearest-control ordering, code/source receipts and frozen runtime integrity. See docs/PHASE_ERRORS.md and local outputs/xguardian/v06-errors-v2/index.html. Generated artifacts remain local and ignored. No new rendered gameplay or visibility/activation evidence is claimed.

## Grouped learning curves on saved phase-clean vectors

At the user's request, skipped demo viewing and used only the 55 saved v0.6 case vectors in 53 participant groups. Fixed four features, log1p, training-only scaling, balanced logistic regression C=1 and cutoff 0.5. Leave one participant group out, with nested random whole-group training prefixes at 20/40/60/80/100% of available groups. Ten fixed seeds per reduced size; full size once. Single-class subsets abstain without resampling. No feature/cutoff search, new labels, demo parsing or deployed model change.

Mean training cases 10.3/20.7/32.1/42.5/54.0 yield mean held-out detection 73.6/80.6/83.1/81.9/81.2% and false-positive rates 23.8/16.9/15.6/15.9/15.4%. Smallest-size repeats have 0–3 abstentions; other sizes have none. Rates use scored cases, with class denominators saved. Full-size predictions match every saved baseline score (TP13/FN3/FP6/TN33). Training at full size averages 83.1% detection and 13.2% false positives. Early improvement then limited change and a small final training/held-out gap support investigating current representation/model limitations, but do not prove a permanent plateau or predict a larger/diverse dataset's benefit.

All 331 tests pass. Five new tests cover whole-group isolation, nested training sizes, full-fit reconstruction/determinism, held-out perturbation isolation, single-class abstention without resampling, denominator accounting and invalid/tampered inputs. Independently verified 2,165 fitted and 8 single-class abstaining fold records, saved scores/scalers, complete-group selection, nested prefixes, protocol/code receipts and frozen model integrity. The standalone chart was visually checked; bands are subsampling min/max, not confidence intervals. All seeds/folds use previously inspected data and are correlated, not independent trials. See docs/LEARNING_CURVES.md and local outputs/xguardian/learning-curves-v2/learning-curves.png. All generated outputs remain local and ignored.

## Rejected shrinkage joint-distribution model

Tested one fixed model change after the learning-curve investigation: class-conditional Gaussian distributions on the same four log1p/training-scaled phase-clean features, with training-only Ledoit–Wolf covariance shrinkage, equal priors, numerical eigenvalue floor 1e-6 and zero log-density-ratio cutoff. The 55 inspected cases and original 53 participant groups remain unchanged. Protocol/source hashes were written before fitting. No cutoff, feature, parameter or seed search, demo viewing or source relabeling occurred.

Candidate TP13/FN3/FP11/TN28, no abstentions, versus unchanged phase-clean linear TP13/FN3/FP6/TN33. All six existing false flags persist; E-04, R-005, R-013, L-005 and L-010 become additional false flags. R-020 is recovered but R-023 becomes a miss. This candidate is rejected, not an achieved model fix, frozen replacement or fresh performance claim. Current/historical models and evaluation artifacts remain untouched.

All 337 tests pass. Six new tests cover independent Gaussian-density reconstruction, positive covariance/shrinkage, training-only group/scaler/covariance isolation under held-out perturbation, constant inputs, missing evidence, sparse-class abstention and malformed/tampered inputs. Independently rebuilt all 53 training scalers and class covariances and all 55 margins/flags from saved inputs using a separate Gaussian log-density implementation; code/input/protocol receipts and frozen runtime integrity pass. Equal-prior scores are not calibrated real-world cheating probabilities. See docs/JOINT_MODEL.md; complete generated experiment is local outputs/xguardian/joint-model-v2 and remains ignored by Git.

## Rejected pre-shot response timing features

Tested a fixed new measurement using the existing phase-clean tracks, without parsing or viewing demos: correlate player yaw rate against the fixed pre-shot geometric opponent's bearing rate at zero lag, 100 ms delayed and 100 ms leading. Common same-segment support stays strictly before the first shot, within 500 ms, with eight triplets and at least 1 dps standard deviation in each series. Case medians need five windows. Append signed zero correlation and its delayed/leading contrasts to the original four log1p features; retain training-only scaling, C=1 balanced logistic regression, cutoff 0.5 and original 53 participant groups. No lag/feature/cutoff search or labels changed.

1,496 windows support this measurement and all 55 cases retain coverage. Candidate TP12/FN4/FP9/TN30 with no abstentions, versus unchanged phase-clean TP13/FN3/FP6/TN33. All original false flags persist; D-3B, R-013 and R-015 become false flags and R-022 becomes a miss. This candidate is rejected. The measurement is geometric correlation, not causal latency, actual mouse input, visibility, intended target or activation evidence. Current and historical models remain unchanged.

All 342 tests pass. Five new tests recover known immediate/delayed/leading synthetic signals, prove pre-shot-only invariance and no mutation, reject constant/missing/gapped support, enforce five-window aggregation and reject invalid/tampered sources. Independently recomputed all 1,496 window correlations and 55 case aggregates, reproduced all candidate scores/flags and training scales, checked group separation and code/input/protocol receipts, and passed frozen runtime integrity. See docs/RESPONSE_TIMING.md; local outputs/xguardian/response-timing-v2 retain the complete fixed experiment and remain ignored by Git. No new deployed model or fresh generalization claim.

## Metadata-first dataset expansion with untouched legitimate controls

The user authorized a larger reliably source-labeled dataset, keeping raw data local and skipping demo viewing. Targeted 16 cheating and 32 legitimate new player/matches with a 16 GiB total compressed-cache cap. Initial restricted-network attempt failed DNS; authorized network access then hit interrupted transfers. Added bounded curl retry-all-errors handling without relaxing final HTTP range/size checks. Final acquisition stopped on transfer timeouts at about 14.14 GiB, before the cap/quota, recovering fourteen complete eligible cases (one cheating label, thirteen legitimate). This is a partial acquisition, not fulfillment of the original 48-case target or a representative sample. Original rounded-ID/player-match labels are preserved; no activation labels or source predictions are used.

Fixed acquisition-order alternation within labels, before feature inspection, assigned eight development cases (1/7) and six legitimate holdout controls (0/6). Revalidated demo/label hashes and participant metadata against the frozen bundle and all prior registry receipts. All 140 participants are disjoint from prior inspected/reserved cases and from each other across matches. Both partitions are registered for future acquisition exclusion. The controls remain metadata-only and unscored; their lack of cheating cases prevents a complete future detection evaluation. They are reserved for a future phase-clean protocol, not bound to or authorized for legacy model scoring.

Eight new v0.6 extractions publish 303 live windows, exclude 37,750 formerly active warmup samples, and have no extraction errors/structural violations; all retain round-event warnings. New tracks have sufficient coverage. The enlarged inspected development pool contains 63 cases (17 cheating labels, 46 legitimate) and 61 participant groups. Same four-feature/C=1/cutoff 0.5 grouped diagnostic: combined TP14/FN3/FP6/TN40, no abstentions. On the original 55 with expanded training folds: TP13/FN3/FP5/TN34; on the new 8: TP1/FN0/FP1/TN6. R-012 is corrected and N-002 is a new false flag; other original decisions are unchanged. Historical 55 TP13/FN3/FP6/TN33 remains preserved. These are post-inspection development outcomes, not fresh generalization evidence or a frozen/deployed replacement.

Reran fixed grouped learning curves on the 63 vectors: mean training sizes 12.4/24.7/37.2/49.6/62.0 give held-out detection 74.4/78.2/80.6/81.2/82.4% and false-positive rates 18.6/14.1/15.4/15.2/13.0%. Smallest repeats have 0–1 abstentions, other sizes none; rates use scored denominators. Full-size scores reproduce the expanded diagnostic. Bands are subsampling ranges, not confidence intervals; different cohort denominators prevent treating total-count changes as accuracy gains.

All 347 tests pass. New checks cover deterministic source-label alternation without mutation, duplicate/overlapping/inspected case rejection, registration of both partitions, network retry validation and development-only expansion/inspected-copy semantics. Independently verified fourteen demo/label receipts, all 140 participant exclusions, registry checksums, untouched holdout metadata/no holdout reports in the expanded pool, eight new feature vectors, all 63 scores/61 fold scalers/group separation and frozen runtime integrity. Expanded learning-curve fold scores/scalers, full-group separation and nested prefixes independently reproduce; chart visually checked. See docs/DATA_EXPANSION.md. Final local outputs: data/external/xguardian/expansion-cohorts-v1, outputs/xguardian/expansion-development-v1, expanded-phase-pool-v2 and expanded-learning-curves-v1. All raw/generated artifacts remain ignored and local; no demo viewing or upload.

## Explicit aimbot subtype and activation provenance audit

At the user's requirement to verify active aimbot rather than wallhack-only cheating, audited all 63 current development identities against the original/new manifests and receipt-linked published source mapping. Rechecked the original paper/project sources. Two positives have author aimbot descriptions (D-1A aimbot; D-1B aimbot plus wallhack), D-2B is author-described wallhack-only, and the other fourteen positives including N-004 have unknown subtype. There are zero verified activation intervals or confirmed active-aimbot positives. Published narratives do not establish window-level activation. The current 14/17 result remains generic-cheating-label recall, not verified aimbot recall.

Added a separate provenance audit and explicit eligibility/policy: no generic, wallhack-only or author-narrative case becomes a confirmed activation positive; unknown/wallhack cases do not become legitimate negatives. An audit-consumer guard rejects authorizing activation training from this provenance-only artifact. Existing generic-label commands, all original labels/results, frozen model and reserved controls remain unchanged. No demo viewing, model training or fresh evaluation occurred.

All 350 tests pass. New tests preserve binary labels, distinguish narrative subtypes from activation truth, reject conflicting/guessed attributions and block misuse of the audit as activation-training authorization. Independently verified all 63 identity/label mappings, source/code receipts, empty activation/false eligibility fields, guard rejection and frozen runtime integrity. See docs/AIMBOT_LABEL_POLICY.md; the local complete report is outputs/xguardian/aimbot-label-audit-v1/report.md. All generated/raw artifacts stay local and ignored.

## Specificity-first policy under revised user priority

The user explicitly accepts fewer than ten detections among seventeen positives if legitimate flags are avoided, superseding the prior objection to conservative cutoffs. Re-ran the existing fixed nested conservative policy on 63 phase-clean development cases in 61 participant groups. Each outer cutoff is the maximum legitimate inner out-of-group score using outer training cases only; flag strictly above it. Same four features, training-only scaling/log1p and C=1 balanced logistic classifier. No cutoff/feature grid, case exception, source relabeling or held-out-control inspection.

Conservative TP6/FN11/FP1/TN45, zero abstentions, versus existing TP14/FN3/FP6/TN40. Five false flags are corrected at the cost of eight detections. R-002 remains falsely flagged. This is a meaningful change in the requested development tradeoff, not an achieved zero-false-positive detector, population guarantee or independent evaluation. It remains a development candidate; no current/frozen model or historical result is overwritten. Six reserved legitimate controls remain untouched.

All 352 tests pass, including new wrapper checks for tampered receipts, declared group/label routing and preservation of the default result. Existing nested-policy tests remain in force. Independently verified all 63 predictions/strict-cutoff flags, 61 training-only cutoffs and outer scalers, all 3,660 inner fold partitions/exclusion of outer cases, source/code/protocol receipts and frozen integrity. See docs/SPECIFICITY_FIRST.md and local outputs/xguardian/specificity-first-v1/report.md. Raw/generated artifacts remain local and ignored; no demo viewing or fresh evaluation.

## Per-false-flag contribution audit and training-only weight reduction

Investigated all six default false flags using exact saved held-out folds and compared the same scores to each strict cutoff. Alignment error supplies the largest positive term for R-002/R-009/L-002/L-013; relative rate dominates D-3A and acceleration dominates N-002. Strict clears five only by raising cutoffs; scores/weights are identical. R-002 remains above its own lower training-only cutoff, which excludes that legitimate outlier from calibration.

Tested one fixed reduction rule: choose the most frequently dominant positive feature among legitimate inner out-of-group false flags inside each outer training set; halve only that standardized log-feature coefficient contribution, retaining intercept/other weights and cutoff 0.5. Sixty folds select alignment error and one selects relative rate. No factor/cutoff sweep or case exception. This is a hypothesis informed by inspected cases, not fresh evaluation. Result TP11/FN6/FP4/TN42, no abstentions, versus default TP14/FN3/FP6/TN40 and strict TP6/FN11/FP1/TN45. R-009/L-013 are cleared; D-3A/R-002/L-002/N-002 remain. The change does not meet the requested 14/17 with 1/46 goal and is not adopted/frozen. All original results, labels and reserved controls remain unchanged.

All 355 tests pass. New tests cover training-inner legitimate-false-flag-only selection, unchanged coefficients/intercept, exact selected-term damping, negative-term damping potentially increasing scores, and tampered receipts. Independently verified all 63 adjusted scores/flags, 61 training-only vote selections, six original/strict score reconstructions, source/code/protocol receipts and frozen runtime integrity. See docs/FEATURE_WEIGHT_AUDIT.md and local outputs/xguardian/feature-weight-audit-v1/report.md. No demo viewing, raw downloads or fresh evaluation.

## Shot-motion support audit and rejected strict pre-first movement variant

Audited all 63 phase-clean development cases/3,321 windows, reproducing original near-shot speed/acceleration from canonical telemetry before computing alternative timing measurements. Original intervals are selected within 100 ms of any grouped shot, including firing-period motion. Across six false flags, 77–90% of selected speed intervals end at/after the first shot. N-002's case speed median changes from 74.17 to 24.72 dps under strict pre-first support. This is a timing/coverage finding, not proof that recoil caused any flag.

Sparse selected-player probes around the first three windows of each false flag return aim_punch_angle and shots_fired in all six demos, with nonzero punch observations and 98–99 returned rows per case. Raw yaw/pitch reproduce canonical float32 inputs. Missing ticks stay explicit; no assumed punch correction, eye/head coordinates or visibility is introduced. Recorded punch does not establish how it relates to recorded camera angles or bullet direction. No demo viewing or reserved-control extraction.

Tested one fixed replacement of the first two movement features with complete strict pre-first 100 ms window medians (five-window minimum), keeping the original two tracking features, groups, scaling/log1p and balanced C=1/cutoff0.5 classifier. Result TP14/FN3/FP8/TN38, no abstentions, versus original TP14/FN3/FP6/TN40. L-013 and N-002 are cleared, but D-3B, E-04, L-011 and N-003 become false flags; positive-label flags are unchanged. Variant rejected, no default/strict/frozen model or historical results overwritten. No timing/threshold/feature search or fresh evaluation.

All 359 tests pass. New checks prove shot/post-shot perturbations cannot change pre-first features, all derivative support samples obey the time boundary, unavailable evidence stays null, minimum-window aggregation is enforced and changed original features/invalid ticks fail. Independently recomputed all 3,321 pre-first window features directly from yaw/pitch/ticks, all 63 candidate scores/flags and training scalers/group isolation; frozen integrity passes. See docs/SHOT_MOTION_AUDIT.md; complete local outputs are outputs/xguardian/shot-motion-audit-v1 and pre-first-model-v1. All raw/generated artifacts remain local and ignored.

## Recoil/counter timing validation without guessed correction

Audited all 16,505 published shot references in the 63-case phase-clean pool using exact selected-player yaw/pitch, aim_punch_angle, shots_fired and active_weapon_name at offsets -2..+2. Required same live segment and matching stable weapon; reproduced recorded angles at float32 precision. The exploratory pass caught parser display-name/event-ID mismatch; final explicit normalization distinguishes guns including M4A4/m4a1 and M4A1-S/m4a1_silencer. Exploratory v1 is superseded by v2.

Final support: 16,136 available shots, 342 excluded by live-segment support and 27 weapon-changed/mismatched. All 63 cases return the requested fields. Counter rises at the fire-event tick for 16,123 supported shots (~99.9%); thirteen have no nearby rise and occur in both label classes. Counter resets occur in 1,201 supported five-tick windows. Exceptions are retained, not interpreted as no-shot/silent-aim evidence. Recorded view/punch component cosine has overlapping case ranges across labels (cheating median -0.214, legitimate -0.176), so opposition alone does not establish anti-recoil use. No claimed camera/bullet correction, causal mouse-input inference, classifier fitting, activation labels, model/policy change or reserved-control access.

All 364 tests pass. Five new tests cover event/delayed counter changes, known opposed components, missing/nonfinite/changed-weapon support, null zero-vector cosine, counter resets, yaw wrapping, duplicate ticks and display-name aliases without merging distinct guns. Independently reconstructed all 16,136 available shot deltas/cosines, every published shot identity/availability count, per-case medians and source/code/protocol receipts; frozen runtime integrity passes. All current generic-label/default/strict results remain unchanged. See docs/RECOIL_EVENT_AUDIT.md; final local outputs/xguardian/recoil-event-audit-v2 includes raw probes, summaries and independent verification receipts. No demo viewing, uploads or fresh evaluation.

## Rejected same-weapon burst co-variation features

Extended the validated shot-field audit to fixed time-grouped firing bursts: at least three shots, gaps at most 200 ms, exact consecutive support from first shot-1 through last shot+2, same live segment/weapon, at least eight intervals and nonzero recorded view/punch variation. These are firing-pattern proxies, not inferred trigger mode or physical recoil correction. Computed opposing projection gain, relative projection residual and global recorded-component cosine, requiring five valid bursts per case. Residual/cosine are algebraically related, not independent evidence. Appended signed medians to the original four log1p features; preserved training-only scaling, balanced C=1/cutoff0.5 and participant groups, without a recipe/threshold search.

1,326 eligible measurements from 1,493 burst proxies; exclusions 144 live-segment, 19 insufficient variation, 4 weapon mismatch/change. D-1A and R-008 each have four valid bursts and explicitly abstain. Original full-pool TP14/FN3/FP6/TN40 remains unchanged. A separately refitted matched-coverage baseline and burst-augmented model both yield TP13/FN3/FP6/TN39 with two abstentions. Added features clear R-009/L-013/N-002 but newly flag R-005/R-012/N-001; covered positive flags are unchanged. No aggregate specificity improvement, with reduced coverage including an author-described aimbot case. Candidate rejected; no defaults/strict/frozen models, labels, controls or historical results are changed.

All 368 tests pass. New tests recover known synthetic opposing gain/residual/cosine and orthogonal motion, preserve missing/changed-weapon/constant-support uncertainty, enforce fixed group/weapon/segment boundaries and five-burst case coverage. Independently recomputed all 1,326 projections and case aggregates/coverage, both matched model score sets and training scalers/group separation, source/code/protocol receipts and frozen integrity. See docs/BURST_RECOIL.md; final local outputs/xguardian/burst-recoil-v2 retains all observed fields, measurements and models. No demo viewing, fresh evaluation or reserved-control access. All raw/generated data remain ignored and local.

## Fixed two-stage confirmation with explicit review accounting

Tested the user-approved agreement rule using cached burst-recoil-v2 matched-coverage baseline and burst-augmented predictions. Verified identical training/held-out participant partitions, training scalers and every saved score. Both positive gives a flag; both negative gives not_flagged; either direction of disagreement or missing evidence produces unresolved review with null flagged value. No cutoff search, refitting, new evidence labels or holdout use. Stages are correlated, not independent corroboration or calibrated probability.

Result over all 63 cases: cheating labels 13 flags/3 not_flagged/1 missing review; legitimate labels 3 flags/36 not_flagged/6 disagreement reviews/1 missing review. Legitimate flags D-3A/R-002/L-002; disagreement reviews R-005/R-009/R-012/L-013/N-001/N-002; missing D-1A and R-008. Compared with matched-coverage baseline 13 positive flags/6 legitimate flags/2 missing, agreement retains 13 positive flags and reduces legitimate firm flags to 3 but unresolved cases rise to 8. Compared with original full-pool 14/17 and 6/46, all-case agreement fractions are 13/17 and 3/46, with 8 reviews explicitly retained. Ten legitimate cases are flagged or unresolved; review workload increases. This does not achieve the desired 14/17 with 1/46 or demonstrate population FPR. No default/strict/frozen policy or historical results are overwritten.

All 372 tests pass. New checks cover all agreement/disagreement/missing outcomes, exact cutoff equality, null unresolved verdicts, mismatched identities/scores, matched fold/scaler/score reproduction, participant leakage rejection and tampered receipts. Independently reconstructed all 63 final decisions and label-specific review counts and verified source/code/protocol receipts and frozen integrity. See docs/CONFIRMATION_POLICY.md and local outputs/xguardian/confirmation-policy-v1/report.md. The six reserved controls remain untouched; no parsing/viewing or fresh evaluation. All generated/raw artifacts remain local and ignored.

## Rejected cross-fitted multi-family review-priority score

Implemented the user-approved multi-factor scoring experiment using four families: original movement, pre-shot tracking, same-weapon burst co-variation and response timing. Family logistic models learn feature weights, then a meta logistic model learns joint family-margin and missingness weights. All use balanced C=1 training-only scaling. Outer participant groups are excluded from every fit and imputation; family margins for meta training are produced by inner group cross-fitting. Refit families use only outer training cases. Missing margins use cross-fitted training means plus explicit flags; fewer than two available families abstains. All 63 cases have at least three available families, including explicit missing bursts for D-1A/R-008. Correlated inputs are not multiplied as independent evidence. Scores 0–100 are uncalibrated review priorities, not cheating probabilities.

Fixed 50-point boundary yields TP11/FN6/FP9/TN37, no abstentions, versus original TP14/FN3/FP6/TN40. A descriptive post-fit ranking comparison also worsens: average precision 0.828 versus 0.668; top ten original scores retrieve 9 cheating labels/1 legitimate label, versus 7/3 for the new score. These review-budget counts are not deployment thresholds or fresh evaluation. No threshold/architecture/weight grid or favorable cutoff is selected. Candidate rejected; original/strict/agreement results and all source labels remain unchanged. Six reserved controls are untouched.

All 376 tests pass. New tests verify inner group cross-fitting and exclusion of outer cases, explicit missingness/low-evidence abstention, invariance of fitted models to outer held-out feature/label changes, and identity/group guards. Independently checked 14,884 family training scalers, 61 meta scalers/cross-fit partitions, all 63 final scores/flags and imputation/missingness inputs, source/code/protocol receipts and frozen runtime integrity. The ranking plot was rendered and visually inspected. See docs/EVIDENCE_SCORE.md; final local outputs/xguardian/evidence-score-v2 includes nested fitted parameters, per-group contributions, scores, coverage and ranking artifacts. No raw demo parsing/viewing, downloads, holdout evaluation or frozen/deployed model change. All generated/raw artifacts remain local and ignored.

## Fixed specificity-weighted loss and analytical cutoff reference

Tested a training-objective change on the same 63 phase-clean cases/61 participant groups: multiply legitimate inverse-frequency-balanced training weights by 3 and normalize mean weight to 1. Legitimate/cheating class-total loss weights become 75/25%, retaining total training weight n and C=1 regularization scale. Same four features, unweighted training-only scaler/log1p and cutoff 0.5; no weight/cost/feature grid. Weight selection depends only on each training partition. Candidate weighted refit yields TP10/FN7/FP2/TN44 with no abstentions, versus original TP14/FN3/FP6/TN40. Remaining legitimate flags are D-3A and R-002.

Added an analytical reference after the initial weighted fit: apply the original model at 3/(1+3)=0.75, derived from the already-fixed 3:1 ratio rather than a score/label cutoff search. Result TP10/FN7/FP1/TN45, no abstentions or review cases; R-002 remains the false flag. This is a different operating point with unchanged original ranking, not a stronger ranking model or independently preregistered fresh evaluation. It improves development recall over the prior strict TP6/FN11/FP1/TN45 but does not reach 14/17 with 1/46 or establish low population FPR. Scores are uncalibrated, so the analytical control is not asserted to be a calibrated real-world cost optimum.

All 380 tests pass. Four new tests cover normalized class-total ratios/constant total weight, outer-held-out feature/label isolation of weights/scalers/coefficients, invalid inputs, single-class abstention and tampered source rejection. Independently refitted all 61 weighted fold models and verified weights, training labels/scalers, all 63 weighted and 63 fixed-cutoff decisions, source/code/protocol receipts and frozen integrity. Original/strict/agreement models, historical outcomes and six reserved legitimate controls remain unchanged. No raw parsing/viewing, download or fresh evaluation. See docs/COST_SENSITIVE.md and local outputs/xguardian/cost-sensitive-v2/report.md; all generated/raw data remain ignored and local.

## Rejected fixed shallow boosted-tree classifier

Tested one preset interaction learner on the same four phase-clean measurements, 63 development cases and 61 participant groups: gradient boosting 100 stages, learning rate 0.05, max depth 2, minimum leaf 8, subsample 1, seed 0, log1p and training-only balanced sample weights. Cutoff remains the existing 0.75; no feature/parameter/cutoff sweep or global learned preprocessing. Exported trees are replayable from JSON at sklearn's float32 traversal precision.

At 0.75 the tree yields TP11/FN6/FP3/TN43, no abstentions, versus linear TP10/FN7/FP1/TN45. Tree recovers E-09/R-023, loses R-024, retains R-002 as a false flag and adds L-002/N-003. Rejected under the specificity priority; 10/17 with 1/46 remains the unchanged development candidate. A post-fit descriptive ranking check shows average precision 0.828→0.755 and a maximum of ten detections at at most one legitimate flag for either model. This hindsight envelope is not a selected deployment threshold or independent evaluation and cannot establish the requested 14/17 with 1/46.

All 383 tests pass. New tests verify JSON/library score equivalence, held-out feature/label isolation of weights/trees, invalid inputs and single-class abstention. Independently refitted all 61 library models and verified all 63 held-out scores/flags, balanced weights, participant separation, source/code/protocol receipts and frozen runtime integrity. No default/strict/agreement/frozen model, source label or reserved-control outcome changed. See docs/SHALLOW_BOOSTING.md and local outputs/xguardian/shallow-boosting-v2. No raw parsing/viewing, downloads, holdout evaluation or deployment; all raw/generated artifacts remain local and ignored.

## Frozen phase-clean offline scoring and single-use legitimate holdout

Implemented offline_detector freeze/score/evaluate commands. Freeze validates all 63 development report/tracking/demo receipts, independently re-derives participant connected groups, reproduces all four vectors and fits the unchanged balanced C=1/log1p/StandardScaler classifier on 63 cases in 61 groups. Cutoff0.75 stays fixed. Model SHA-256: 1cc9bb01d21983c1926cd8434bfc63815d9b07343a5a7f19e56401b39286bdda. Artifact pins 16 source modules, Python/dependencies and exact recipe; reused outputs, changed runtime/recipe/model hashes are rejected. A known N-001 development replay passes end-to-end feature-equivalence smoke before holdout use, not as fresh accuracy evidence.

Scoring accepts one demo/exact SteamID, writes a local scorecard and trajectory evidence, preserves warnings/provenance/contributions and uses unlabeled tracking input. Insufficient evidence has null score/flag, not a clean verdict. Extractions fail explicitly. Generic-cheating review scores are not calibrated probabilities or confirmed aimbot activation.

Validated the six reserved legitimate controls' original metadata/demo/label identities and 60 participant exclusions, then consumed the cohort before new feature extraction with a model-bound receipt. Scored all six once: 0/6 false flags, no errors/unresolved cases,257 live windows. Scores .0361688/.4793497/.5102498/.6427021/.0038454/.4985424; all below .75. All six retain round-event warnings. Model/threshold/source recipe remain unchanged after evaluation. This cohort is now consumed, not an untouched future validation set. Negative-only sampling cannot estimate detection, and six convenience-sampled cases cannot establish low population FPR; the conditional independent representative one-sided 95% upper bound is ~39.3% even with zero observed flags. Historical development 10/17 with 1/46 remains separate, not combined into a fresh mixed metric.

All 388 tests pass. New tests cover runtime/recipe/dependency integrity, pre-extraction consumption and blocked reuse despite errors/new output, continued case isolation, metadata participant overlap, zero-error small-sample bounds and insufficient/unlabeled evidence handling without clean substitution. Independently refitted frozen full-fit coefficients/scaler, reproduced all six unseen vectors/scores/flags and report links, verified model identity/timestamp-before-consumption, source receipts and disjoint participants, and confirmed reuse fails before creating another evaluation output. Legacy frozen integrity passes. See docs/OFFLINE_DETECTOR.md; final local outputs/xguardian/offline-v06 contains frozen model, development-smoke, holdout-evaluation and verification.json. Consumption receipt is data/external/xguardian/expansion-cohorts-v1/holdout.consumed.json. All raw/model/generated artifacts remain ignored and local; no viewing, upload or new download.


## Metadata-only local evaluation inventory

Audited all 119 extracted local replay files by complete-file hashes: 86 distinct matches and 33 duplicate copies. All 86 have identity metadata with zero errors. Excluded 72 previously used matches (63 development, six consumed controls and three original user-provided matches) and 14 others with identity overlap. No matches qualify under the current strict policy. Seven overlap full SteamIDs; seven overlap only short numeric IDs 11/12, which may be server/bot identifiers. Those seven contain seven legitimate and one cheating source-label rows across seven matches, not eight independent cases. Their identity semantics and prior inspection need review before any changed policy or fresh reservation; no cases were admitted or scored.

Checked 116 local ZIP files: no demo entry lacks an adjacent extraction. Local label tables cover 2,903 matches, including 2,820 without extracted local demos (4,998 legitimate and 330 cheating label rows); these are acquisition leads, not verified fresh cases. Partial raw archive cache is not claimed exhausted. Added a reproducible metadata-only inventory script and four tests for prior-use exclusions, whole-match identity overlap, ambiguous rounded labels and exact label scope. All 392 tests pass. Both frozen model integrity checks pass; no pinned source, cutoff, model or evaluation changes. Final local inventory is outputs/xguardian/evaluation-inventory-v2, with per-match report and supplementary availability notes. No download, trajectory extraction, scoring or data upload. See docs/EVALUATION_DATA_INVENTORY.md.


## Short-ID identity audit for additional evaluation candidates

Investigated the seven matches excluded solely for player-info snapshot IDs 11/12. Compared all exact snapshot identities to the complete CCSPlayerController.m_steamID stream; exported identity fields must match the controller values and their union must reproduce the hash-bound inventory. The short non-account numbers appear only in snapshots, with corroborating isbot player_team events. Exact bot-to-short-ID mapping is not exposed and is not asserted. Public individual desktop account fields, rather than decimal length or bot names, define cross-match human identity. Unknown identity formats or non-account IDs in the controller stream fail closed. Preserve all account IDs from both streams, including replacements/disconnections.

All seven matches pass, with 70 account participants disjoint from one another and the 700 inspected/consumed account exclusions. Scanned 1,526 prior output JSON files by candidate match IDs/full replay hashes; no prior references. Chose one uniquely source-labeled target per match under a recorded metadata-only rule: six legitimate, one generic cheating. The eighth provisional label shares a match and is omitted. Candidates are explicitly not reserved or scored; separate binding and consumption protocol is required before a new evaluation. Original six-case holdout remains consumed, original strict inventory remains historical, and no legacy or frozen evaluator identity code is modified.

All 396 tests pass. Four new tests cover exact SteamID64 account fields versus short/other types, bot corroboration and controller-stream conflicts, retention/exclusion of snapshot-missing accounts, participant overlap, deterministic one-target selection and ambiguous rounded labels. Independently verified plan/code/input hashes, exact target scope, seven case receipts, 70 unique accounts and both frozen runtimes. Final local outputs/xguardian/short-id-audit-v1 contains audit/verification receipts, report and unscored candidates. See docs/IDENTITY_AUDIT.md. No trajectories/scores extracted, model/threshold change, download or data upload.
