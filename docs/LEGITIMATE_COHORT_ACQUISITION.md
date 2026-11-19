# Bounded legitimate-player acquisition

The public raw archive contains many matches, but a replay's other players are
not automatically labeled legitimate. The local source tables identify 5,136
legitimate player-in-match label rows across 2,867 matches. Of these, 1,485
matches have at least two legitimate-player labels. These are metadata counts,
not verified fresh cases or independent observations.

This acquisition targets 50 unseen individually labeled legitimate players,
with at most two per match. A complete cohort therefore needs at least 25
participant-disjoint match groups. Using multiple labels per demo saves data
transfer and parsing while retaining match groups for later evaluation.

```bash
.venv/bin/python -m scripts.acquire_legitimate_cohort \
  --output data/external/xguardian/legitimate-cohort-v2 \
  --cache data/external/xguardian/raw-part1-acquisition-prefix.zst \
  --prefetch data/external/xguardian/raw-prefetch \
  --target 50 --limit-gib 20 --extraction-gib 24

.venv/bin/python -m scripts.report_legitimate_cohort \
  data/external/xguardian/legitimate-cohort-v2

.venv/bin/python -m scripts.register_legitimate_cohort \
  data/external/xguardian/legitimate-cohort-v2
```

Existing outputs are not overwritten. The cache limit applies to the total
compressed prefix, including the roughly 14.14 GiB already present at the
recorded run's start. The first batch may append at most roughly 5.86 GiB.
New extracted ZIP/demo files have a separate 24 GiB cap. Download ranges have
their HTTP status, content range and byte length verified. Optional parallel
range prefetch stays inside the same prefix limit. A partial compressed prefix
does not verify the full published archive checksum.

The raw source is [XGuardian raw data part 1](https://zenodo.org/records/17838584),
whose full file is about 48.3 GB. The acquisition streams a bounded prefix,
verifies nested ZIP CRCs, and hashes selected demos. It records transfer/budget
limits and errors explicitly; partial acquisition never means target complete.

## Selection before scoring

Selection follows archive order. Known local matches and every prior inspected
or reserved human-account identity are excluded. For each otherwise eligible
match, snapshot and complete controller identity streams are compared, all
account identities are preserved, and short local IDs require corroborating
bot metadata. Cross-match human overlap excludes the entire match.

Only source rows explicitly labeled legitimate can supply targets. Rounded
source tokens must uniquely match exact account IDs inside that replay. Order
eligible rows by SHA256(match ID + source token), take up to two, and stop at
the player target. No trajectories, scores, model fitting or skill-based
selection are used. Skill-level annotations are not available in these tables.

The verifier checks exact labels and hashes, reproduces metadata-only target
selection, and rejects duplicate, ungrouped or shared-account cases. Same-match
players remain in one group; no player-level independent binomial confidence
bound should be inferred from them. Archive convenience sampling also limits
population claims.

The generated manifest is explicitly a set of **unreserved, unscored grouped
candidates**. Before another acquisition batch, register its participants for
exclusion with the final command so it cannot be selected twice. This only adds
an acquisition exclusion receipt; it does not consume an evaluation or authorize
scoring with a historical model. Before scoring, bind a separate
single-use group-aware evaluation protocol to the unchanged frozen model and
0.75 cutoff. Preserve the historical development and two consumed small
evaluations. Keep raw files, local model artifacts and generated reports local
and ignored.

## Recorded collection

The first bounded slice reached its 20 GiB compressed-prefix cap with **33
legitimate-player labels from 22 matches**. Its `ReadError: unexpected end of
data` records the intentional truncated prefix, not target completion. The
incomplete terminal ZIP was marked `.partial`; it supplies no selected case.
Verified cases were registered for acquisition exclusion before continuing.

A second slice requested the remaining 17 players, extending the prefix cap
to 24 GiB and using a separate 16 GiB extracted-file cap:

```bash
.venv/bin/python -m scripts.acquire_legitimate_cohort \
  --output data/external/xguardian/legitimate-cohort-v3 \
  --cache data/external/xguardian/raw-part1-acquisition-prefix.zst \
  --prefetch data/external/xguardian/raw-prefetch \
  --target 17 --limit-gib 24 --extraction-gib 16

.venv/bin/python -m scripts.report_legitimate_cohort \
  data/external/xguardian/legitimate-cohort-v3

.venv/bin/python -m scripts.register_legitimate_cohort \
  data/external/xguardian/legitimate-cohort-v3

.venv/bin/python -m scripts.collect_legitimate_cohorts \
  data/external/xguardian/legitimate-cohort-v2 \
  data/external/xguardian/legitimate-cohort-v3 \
  --output outputs/xguardian/legitimate-cohort-50-v1
```

The second slice completed its target with **17 labels from 11 more matches**.
Combined: **50 unique labeled legitimate players from 33 participant-disjoint
matches**, containing 330 distinct account participants. Seventeen matches
contribute two targets and sixteen contribute one. All other players remain
unlabeled for this test. Qualified collection IDs preserve the original
per-slice case IDs and group provenance without modifying source manifests.

The compressed prefix grew by about 8.83 GiB to 22.97 GiB, below the second
slice's 24 GiB cap. New extracted ZIP/demo/partial files total about 10.58 GiB
across the two slices, within their respective bounds. Parallel prefetch
stopped with acquisition; unused verified ranges may remain cached locally.

Independent verification checked all 33 selected demo/ZIP hashes and ZIP CRCs,
every target's explicit source label and unique exact-ID mapping, no prior
analysis report references, exclusion registration and both frozen runtimes.
The complete local report and verification are in
`outputs/xguardian/legitimate-cohort-50-v1`.

**This collection has not been scored and is not yet reserved for evaluation.**
No model, cutoff, training feature or historical evaluation was changed. The
next step is a separately bound single-use group-aware evaluation, reporting
both player flags and match groups, with errors/insufficient evidence explicit.
The group count and convenience sampling must remain visible in any performance
claim; fifty players are not fifty independent matches.
