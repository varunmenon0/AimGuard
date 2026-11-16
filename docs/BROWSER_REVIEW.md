# Browser reconstruction review

The user-provided [CS2.APP viewer](https://www.cs2.app/demo-viewer) successfully loaded two local research demos. Its UI reported local parsing/no upload; analytics consent was declined. The provider advertises browser-local parsing and a telemetry-based 3D reconstruction. No independent network audit was performed.

## Verified capabilities

Tested 2D/3D switching, player selection, follow/POV mode, timeline seeking, normal-speed playback and 0.25x playback. In 3D, selecting the player and cycling the follow control twice enters its labeled POV mode. Both demos produced reconstructed map/player/shot scenes, and the selected players' expected MAG-7 and AWP eliminations were observed in the kill feed.

This removes the local CS2-installation blocker for spatial-context review. It does not establish equivalence with native CS2 or the player's original client view. Geometry/characters are simplified, player names remain visible beyond geometry, and no X-Ray-off control was found in the inspected controls. Exact visibility, client prediction, smoke/flash fidelity and intended target remain unverified. No reconstructed scene is promoted to a confirmed activation label.

The pilot inspected D-1A at the published-reference encounter and R-002 at its selected AWP encounter. These are two capability examples, not the matched ten-event comparison. In R-002, before/after screenshots keep a similar view angle near cover, consistent with angle holding. This is a descriptive observation, not proof about the cause of its model score. The examples use different weapons and support no comparative accuracy claim.

## Timeline alignment

Do not multiply the displayed clock by 64 and treat that as a raw demo tick. The browser timeline uses a different origin and does not remain globally affine to the raw replay tick sequence. The initial raw-death prefix also differed between the two demos. UI kill-marker positions and local event ordering were used as landmarks, with attacker/victim/weapon kill-feed confirmation. Pixel seeking is approximate; exact-frame verification is not claimed.

The timeline discrepancy led to a separate direct server-flag investigation: the old analysis included warmup windows. That finding is verified from replay game-rule properties, not inferred from the browser renderer. See [PHASE_AUDIT.md](PHASE_AUDIT.md).

## Observation source and limits

`aimguard.event_review` now recognizes `browser_reconstruction` as a source distinct from `telemetry_only` and `rendered_gameplay`. Reviewed browser rows require the existing reviewer/evidence/provenance fields and must use `assistance_assessment=not_assessable`. Behavior observations can describe pre-aim, correction or tracking, but the renderer alone cannot provide an assistance verdict. Import reports source-specific counts and rendered-gameplay counts separately; training labels remain disabled.

Use the general event-review CSV/validator for browser-context observations. The native gameplay-pack importer still requires its original verified build/POV/X-Ray fields; do not fill those as completed merely because the website shows a POV camera. All ten native review intervals and all original human observations remain pending. The two assistant pilot observations are saved separately under ignored local outputs, not inserted as human labels.

Local pilot artifacts include screenshots, UI timeline landmarks, source demo hashes and `review.json`/`index.html` in `outputs/xguardian/browser-viewer-pilot`. Both loaded browser tabs were left available for inspection. No model, source label or threshold changed from browser inspection.
