# v0.6 phase-checked extraction

New analyses use `python -m aimguard.phase_gameplay` for one replay/player or `python -m aimguard.phase_batch` for a job manifest. These entry points apply the server-phase gate before shot grouping, event-window links and feature calculation. They produce version 0.6.0 reports and do not run a cheating classifier.

The old v0.5 gameplay and batch modules remain unchanged for historical reproduction and frozen-runtime integrity. The README points new work to v0.6. Old frozen feature readers reject the new report version. There is no automatic old-model conversion, threshold reuse or deployment claim.

## Extraction order

1. Apply the established round, alive, team, angle and death-latch rules.
2. Read the replay's warmup and match-started properties at selected-player sample ticks. Require both columns; missing properties fail before output creation.
3. Keep an otherwise-active sample only when warmup is explicitly false and match-started explicitly true. Unknown or conflicting values exclude the sample. Existing exclusions are never reactivated.
4. Split segments at the newly excluded samples, preserving old life/round/gap boundaries. Reassign event segment IDs; excluded events remain in events.json with segment -1.
5. Regroup firearm shots and recompute every window, padded boundary, derivative, movement context and timing profile from the gated samples. Validate the results before export.

The new path does not merely delete windows from a saved report or reuse features computed with warmup padding. A phase boundary inside a shot group can create separate groups; unavailable samples are not interpolated across it. The ordinary legacy recording-gap policy still applies between recorded samples, and round-event anomalies remain visible rather than being declared repaired.

## Artifacts and failure semantics

Outputs include telemetry.csv with phase_warmup, phase_match_started and phase_status; events.json; report.json; optional plots; and review.html. Data quality counts distinguish legacy active samples, newly excluded phase samples and final active coverage/duration. The raw round-event intervals are named explicitly as before-phase intervals rather than presented as verified live intervals.

Insufficient live evidence produces an explicit status and no cheating/legitimate verdict. The single-demo CLI exits 2 for absent shooting windows. Batch jobs isolate errors and surface insufficient evidence or round-event anomalies as warnings; a failure does not stop later jobs. Reused destinations are rejected.

Window/segment numbering can change when excluded samples are removed. Existing reviews remain bound to their original artifacts; link later reviews using replay hash, player and raw ticks, not old array positions.

The earlier phase-audit comparison (13 TP, 3 FN, 6 FP, 33 TN) discarded entire legacy windows touching excluded phases. v0.6 instead regenerates windows from gated samples. That earlier diagnostic is not a new v0.6 model evaluation and must not be copied over as one. A new compatible model comparison and later fresh evaluation are still required.

## Verified real replay

A real D-1B batch run completed with no structural violations. Active samples decreased from 60,085 to 49,251 after excluding 10,834 formerly active warmup samples; rebuilt windows decreased from 143 legacy windows to 96. All published samples are explicitly live, and exported features reconstruct from the new CSV. The existing round-event warning remains visible. The local smoke output is outputs/xguardian/v06-smoke-v1; no raw files or generated outputs are committed.

Synthetic tests cover mid-group phase exclusions, event reassignment, fresh feature calculation, warmup-angle invariance, death-latch preservation, missing properties, all-warmup insufficient evidence, export/review generation, frozen-version rejection and batch failure isolation. Frozen runtime integrity is checked separately against the unchanged legacy modules.
