# Frozen mixed-label evaluation with match groups

This workflow preserves the unscored 50-player legitimate collection and adds
explicit cheating-labeled targets before evaluating the unchanged offline
model at cutoff 0.75. It does not train or tune a model.

Two positive source labels occur inside the existing 33 unscored control
matches. They are added to those same match groups, not counted as separate
independent matches. The cache also supplied a positive from a separate unused
match. A bounded positive-only acquisition seeks additional participant-disjoint
matches using source labels and identity metadata only. Targets are never
chosen by prediction score or visual impressions of suspicious behavior.

Positive source labels describe generic cheating in a player/match. They do
not confirm active aimbot use, cheat subtype or activation intervals. The
negative targets retain their own explicit legitimate labels even when another
player in the match has a cheating label. No labels are inferred for teammates.

## Acquisition and preparation

Run from the repository root, using a new output directory for each acquisition:

```bash
.venv/bin/python -m scripts.acquire_cheating_cohort \
  --output data/external/xguardian/cheating-cohort-cached-v1 \
  --cache data/external/xguardian/raw-part1-acquisition-prefix.zst \
  --prefetch data/external/xguardian/raw-prefetch \
  --target 8 --limit-gib 28 --extraction-gib 16 --cached-only

.venv/bin/python -m aimguard.evaluation_cohorts register-positive \
  data/external/xguardian/cheating-cohort-cached-v1

.venv/bin/python -m scripts.acquire_cheating_cohort \
  --output data/external/xguardian/cheating-cohort-v1 \
  --cache data/external/xguardian/raw-part1-acquisition-prefix.zst \
  --prefetch data/external/xguardian/raw-prefetch \
  --target 7 --limit-gib 28 --extraction-gib 16

.venv/bin/python -m aimguard.evaluation_cohorts register-positive \
  data/external/xguardian/cheating-cohort-v1

.venv/bin/python -m aimguard.evaluation_cohorts build \
  outputs/xguardian/legitimate-cohort-50-v1 \
  --positive data/external/xguardian/cheating-cohort-cached-v1 \
  --positive data/external/xguardian/cheating-cohort-v1 \
  --output outputs/xguardian/mixed-grouped-v1
```

Acquisition follows archive order, one uniquely source-labeled positive per
new match, with fixed SHA256(match + source token) ordering. It rejects prior
and reserved account identities. The cached-only run cannot append new remote
bytes. Prefix limits are total cached bytes, not a guarantee of reaching the
requested target. Nested ZIP CRCs and demo hashes are checked; the full raw
archive checksum is not claimed for a partial prefix.

Metadata exclusion registration protects subsequent acquisitions; it is not
authorization to evaluate with a historical model. Preparation independently
checks replay identities, raw controller/snapshot agreement, local bot metadata,
exact targets, explicit source labels and cross-group account disjointness.
All original 50 legitimate targets remain unchanged. Multiple targets sharing
one demo retain a single group.

## Single-use evaluation

```bash
.venv/bin/python -m aimguard.grouped_evaluation reserve \
  outputs/xguardian/offline-v06/frozen \
  outputs/xguardian/mixed-grouped-v1/collection.json \
  --output data/external/xguardian/mixed-grouped-v1 \
  --registry data/external/xguardian/grouped-evaluation-registry-v1

.venv/bin/python -m aimguard.grouped_evaluation evaluate \
  outputs/xguardian/offline-v06/frozen \
  data/external/xguardian/mixed-grouped-v1/reservation.json \
  --output outputs/xguardian/mixed-grouped-v1/evaluation
```

Reservation binds the exact model, cutoff, collection, input receipts and new
evaluation runtime before extraction. A canonical per-replay ledger prevents
normal reuse with a different positive subset, different target or renamed
manifest. All participants from earlier reservations are excluded. These are
workflow guards, not an adversarial guarantee against deleting the registry.

Consumption is recorded exclusively before any trajectories are extracted.
Errors, insufficient evidence and interrupted runs consume the cohort too.
The scorer receives only demo, exact target ID and model; source labels are
joined after it returns. Per-case failures are saved and later cases continue.
Historical metadata snapshots remain immutable and are superseded by usage
receipts after evaluation.

Report player-level counts by source class, unresolved cases, and match-level
legitimate flags separately. A cheating-player flag in a mixed match does not
count as a false flag against its legitimate controls. Any conditional bound
is calculated for legitimate match groups, not by treating same-match players
as independent trials. Convenience sampling, limited positives and uncertain
cheat subtype restrict conclusions. This class-selected sample cannot establish
real-world precision or cheating prevalence. Scores remain uncalibrated review
priorities. Raw demos, model files and generated artifacts remain local.

## Recorded one-time run

**This cohort has now been consumed. Do not run the commands as a fresh test.**
The source metadata's uninspected declarations are historical snapshots,
superseded by the canonical consumption receipt and evaluation-usage.json.

The cached-only acquisition supplied one fresh positive. The bounded extension
reached its 28 GiB prefix cap and supplied two more, below the requested seven.
Together with the two explicitly labeled positives inside the original control
matches, the test contained **50 legitimate and five cheating-labeled players
across 36 participant-disjoint match groups**, with 360 account participants.
The 50 controls and their 33 match groups were preserved exactly. Positive
selection was metadata-only; every available selected positive was included.
No outcome-based case selection or threshold search followed.

The original frozen model SHA
`1cc9bb01d21983c1926cd8434bfc63815d9b07343a5a7f19e56401b39286bdda`
and cutoff **0.75** remained unchanged:

| Source class | Scored | Flagged | Not flagged | Unresolved |
| --- | ---: | ---: | ---: | ---: |
| Legitimate | 50 | 1 | 49 | 0 |
| Cheating | 5 | 4 | 1 | 0 |

This is **one false flag among 50 controls** and **four of five generic
cheating labels flagged** in this sample. It is not an established 80% active
aimbot detection rate or a demonstrated 2% population false-positive rate.
All 55 cases scored successfully, with 2,178 live windows and 2,138 eligible
tracking windows. All retain round-event warnings in their evidence reports.

The false flag is B1-F-013, score .9654372. The unflagged positive is
P-SHARED-002, score .6149253. Positive scores in case order are
.9709485/.6149253/.9864527/.8954352/.9487071. No model or cutoff adjustment was
made after observing them. These two cases are the concrete follow-up review
targets; this consumed dataset cannot be reused as a fresh evaluation after
any resulting model changes.

One of 33 legitimate match groups had a false flag. The conditional one-sided
exact 95% upper bound for any flag among the selected legitimate controls in a
match group is about **13.6%**. This is a group statistic under independence,
representativeness and correct-label assumptions, not a player-level FPR bound.
Convenience sampling does not establish those assumptions. The evaluation
deliberately selected classes; the 50:5 ratio is not population prevalence and
does not support a real-world precision claim.

Independent verification reproduced every score and signed contribution from
the frozen coefficients/scaler, verified all 36 demo/ZIP hashes and ZIP CRCs,
the unchanged original controls, unlabeled tracking inputs, participant
disjointness, model/input/report receipts, consumption-before-extraction
ordering, and acquisition exclusions. A renamed reservation repeat was blocked
before creating an output or extracting features. Both frozen runtimes remain
intact. Local results, per-case HTML evidence and verification are under
`outputs/xguardian/mixed-grouped-v1/evaluation`.
