# Combat evidence and field-availability audit

This is a small post-evaluation telemetry audit, not a detection experiment or
rendered gameplay annotation. Models, thresholds and historical outcomes remain
unchanged. It checks what can actually be measured before adding more features.

## Fixed sample and evidence

The sample contains three false flags (R-002 high score, R-014 high acceleration,
R-013 near the cutoff), two legitimate unflagged comparisons (R-001/R-003), and
the first cheating-labeled flagged case (R-017). Each replay contributes the first
three windows with matching positive damage at/after its first shot and the first
three without. Damage in earlier padding is recorded separately. This selected
sample cannot estimate accuracy or generalization.

```sh
python -m aimguard.measurement_audit \
  outputs/xguardian/tracking-baseline-v2/frozen \
  data/external/xguardian/fresh-reserved-v2.json \
  outputs/xguardian/tracking-baseline-v2/evaluation \
  --output outputs/xguardian/measurement-audit

python -m scripts.render_measurement_audit \
  outputs/xguardian/measurement-audit
```

Choose a new extraction directory. The plan records selection, property probes,
source code and evaluation hashes before extraction. Replay/report/tracking and
telemetry checksums, case identities, exact damage links, frozen scores and
original horizontal candidates are verified. Sparse audit extraction reproduces
saved shooter coordinates, angles and states at source precision. Exact missing
samples remain missing rather than being interpolated.

## Observed availability and geometry limits

Position X/Y/Z, recorded yaw/pitch, recoil, crouch, scoped/weapon, spotted/mask,
head-constraint and hitbox-set fields were probed. In all six demos, the requested
`m_vecViewOffset` vector/axis columns were omitted. Column omission is different
from a returned zero vector. Head-constraint vectors are mostly zero with some
nonzero observations; neither these nor a hitbox-set index establish measured
world eye/head coordinates. No fixed eye height or head coordinate is invented.

The [demoparser field reference](https://github.com/LaihoE/demoparser#list-of-fields-the-parser-supports)
documents angle, position, recoil, crouch and spotted aliases. Raw field probes
are observations of these demos/API, not a claim that all CS2 recordings lack
other useful geometry.

The body-origin proxy uses the view-vector convention in
[Valve's Source SDK math implementation](https://github.com/ValveSoftware/source-sdk-2013/blob/master/src/mathlib/mathlib_base.cpp):
negative pitch points upward. A 3D angular separation is computed against the ray
between recorded body origins. This is explicitly a proxy, not eye-to-head,
hitbox or recoil-corrected bullet geometry, and it does not itself validate CS2
camera semantics. Spotted fields are retained as raw observations, not promoted
to independently validated line-of-sight evidence.

## Recorded findings

There are 36 sampled windows and 33 comparable exact pre-first-shot snapshots.
Three snapshots in R-013 have no shooter row at the requested tick in either
saved telemetry or sparse extraction. They remain unavailable. All six replay
extractions reproduce saved shooter values at queried ticks.

The body-origin proxy changes the nearest-opponent ranking in one of 33 comparable
snapshots, in unflagged comparison R-003. In the 18 windows with post-first-shot
damage, the initial horizontal candidate belongs to the damage-recipient set in
14 windows, versus 15 for the origin proxy. These are event agreement counts,
not intended-target accuracy; the first shot and later damage can concern
different players. This small sample does not show vertical ranking ambiguity
explaining the false flags, and does not justify substituting the proxy into the
classifier.

Measured eye/head geometry and validated visibility remain unavailable in this
audit. Recoil values are recorded but no guessed correction is applied. No CS2
rendered gameplay was opened; CS2 was not found at the standard application/
Steam installation locations checked on this machine.

## Complete the rendered-gameplay review

The local index exports `review-bookmarks.csv` and `review-template.json` with
all 36 window bookmarks, demo paths, first-shot/damage ticks and pending review
fields. Use a machine capable of playing these demos to examine target identity,
visibility, vertical alignment, hit location and recoil. Keep uncertain entries
uncertain; telemetry/radar observations are not substitutes for visual evidence.
All rendered-review fields remain pending. The renderer rejects attempts to
present this unvalidated proxy audit as validated eye/head geometry.

Only after that evidence should a new geometry representation be proposed for a
controlled development experiment. Another fresh cohort is required for future
independent performance claims. Demos, fields, identities and bookmarks remain
local and excluded from Git.
