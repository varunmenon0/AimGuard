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
