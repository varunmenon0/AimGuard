# Bounded rendered-gameplay comparison pack

The next evidence step requires actual CS2 playback. No CS2 or Steam installation was found in the standard local application/library locations, and the user confirmed no installation is available. No native gameplay has been rendered or visually reviewed by this workflow. The user-provided browser viewer has since been tested for reconstructed spatial-context review; see BROWSER_REVIEW.md. Its source is tracked separately and does not automatically satisfy native visibility/POV verification. The full ten-event native comparison remains pending.

## Ten short intervals

The builder combines the five source-attributed bookmarks with one comparison from each of the five falsely flagged legitimate players. Comparison selection is fixed: prefer the exact weapon, otherwise weapon family, otherwise any firearm; within that priority choose the earliest eligible matching kill. Kill events must match the selected shooter, weapon, alive segment and window. Canonical pre-shot tracking coverage is required. Selection uses no window-level model score.

The current pack contains three exact-weapon and two family matches. Eight unique demos cover ten planned intervals, each eight seconds before and four seconds after its event. Normal-speed playback totals about two minutes, excluding demo loading, player selection and repeats. This is a selected diagnostic comparison, not an accuracy evaluation.

Review aliases are shuffled with a fixed seed. Source labels, model scores and selection roles are omitted from the reviewer-facing HTML/CSV. The investigator's private key retains provenance and pair identities; the study is not claimed fully blinded. All ten reviews start pending.

## Build and transfer

```sh
python -m aimguard.gameplay_pack build \
  outputs/xguardian/development-v4 \
  outputs/xguardian/source-anchors-v3 \
  outputs/xguardian/encounter-filter-v3 \
  --output outputs/xguardian/gameplay-review-v2
```

Use a new output directory. The default is metadata-only: it contains bookmarks, the annotation template, setup instructions and per-review command text, but no duplicate demo copies. `pack.json` lists the eight existing source files, safe D01.dem-style destination aliases and SHA-256 hashes. The required demo files total 935,148,773 bytes. Copying only the metadata folder will not make demos playable on another machine.

To create a self-contained local transfer folder, repeat with a new output directory and `--include-demos`. Only the eight unique selected demos are copied, and each copy is hash-verified. The original source files are untouched. Raw demos, player identities and generated packages remain ignored local files; nothing is uploaded or sent to another person.

The builder verifies source/manifest/anchor/queue receipts, report/tracking/telemetry/event hashes, raw demo hashes, selected player identity, matching replay kills and unique encounter IDs. It does not fit or score models.

## Perform the review on a CS2 machine

Open the local `index.html`, then follow `SETUP.md` and `commands/Rxx.txt`.

1. Put the aliased demo files in the CS2 `game/csgo/replays/aimguard/` directory.
2. Load a demo with the provided `playdemo` instruction. Wait for loading before issuing the separate `demo_gototick` instruction.
3. Select the indicated player in first-person through demo controls, disable X-Ray, and check the expected event tick. The package deliberately avoids guessing a spectator account-ID conversion or auto-select command.
4. Watch the complete interval at normal speed first. Repeat slowly as needed. Record visible information and plausible ordinary explanations, including recoil, sound, teammates and common angles. Missing sound/context does not prove illicit knowledge.
5. Save an observation only after recording the playback build, verified POV/X-Ray state, reviewer, evidence reference and explanatory notes. If playback or view verification fails, mark unavailable and explain why.

The command names and loading/seek separation follow [CS Demo Manager's implementation](https://github.com/akiver/cs-demo-manager/blob/main/src/node/counter-strike/json-actions-file/json-actions-file-generator.ts); console setup is described by [Steam Support](https://help.steampowered.com/en/faqs/view/4700-D10E-26BE-DDDD). These instructions have not been runtime-tested here. No game plugin, live integration or automatic playback completion is installed or claimed.

## Import observations separately

Edit a copy of `review-template.csv`, preserving all ten rows and immutable identity/tick fields. `playback_status` accepts pending, reviewed or unavailable. A reviewed row requires `pov_confirmed=yes`, `xray_disabled=yes`, a game build, accepted behavior/visibility/assessment categories, reviewer and evidence. Unavailable playback remains pending in the underlying event queue; it never becomes a legitimate or negative example.

```sh
python -m aimguard.gameplay_pack import \
  outputs/xguardian/gameplay-review-v2 \
  outputs/xguardian/encounter-filter-v3 \
  /path/to/completed-review.csv \
  --output /path/to/new-observation-output
```

The importer verifies pack/queue/template/private-key receipts and maps aliases back to original event identities. It produces a separate full-queue observation file, then uses the existing event-review validator. Reviewer reports about playback and evidence are attestations, not independently verified facts. Suspicious behavior is not confirmed cheat activation. No model inputs, training labels or original queue files are changed automatically.

The original pending sheet validates as zero reviewed, with all 3,323 original queue events still pending. Current detector results and the rejected-filter status remain unchanged. Tests cover interval boundaries, deterministic weapon matching, event/identity constraints, pending/unavailable semantics, explicit rendered-view requirements, evidence/category validation and source receipt rejection.
