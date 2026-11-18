# Short-ID replay identity audit

The November 18 inventory excluded seven unused matches solely because their
player-info snapshots reused IDs `11` or `12`. The strict historical inventory
and frozen evaluator are retained unchanged. A separate metadata audit checks
whether those numbers should connect human participants across matches.

```bash
.venv/bin/python -m scripts.audit_replay_identities \
  outputs/xguardian/evaluation-inventory-v2/inventory.json \
  --output outputs/xguardian/short-id-audit-v1
```

The recorded output already exists. The script refuses to overwrite it. Its
conservative prior-output scan may reject a subsequent audit referencing a
previous audit; inspect the existing receipts rather than treating a rerun as
fresh data. Run from the repository root.

## Evidence and policy

For each candidate, the audit reads player-info snapshots, the complete
`CCSPlayerController.m_steamID` identity stream and the `isbot` field of
`player_team` events. No view angles, movement features or model scores are
requested. Exported tick identities must exactly equal the raw controller
identity field. Their union with snapshot identities must reproduce the
complete-file-hash-bound original inventory.

Cross-match account identity recognizes the public individual desktop SteamID64
fields, with a nonzero account number. The upstream parser also defines the
individual SteamID64 base `0x0110000100000000` in its
[event identity implementation](https://github.com/LaihoE/demoparser/blob/main/src/parser/src/second_pass/game_events.rs).
This reference does not replace the installed parser or its pinned runtime.

Every recognized account from either stream is retained, including players
missing from a snapshot. An unfamiliar account format fails closed. A small
non-account ID is treated as local metadata only when it is absent from the
controller identity stream and there are corroborating bot events. The
available parser output does not establish an exact bot-to-short-ID mapping;
the audit deliberately does not assert one. It establishes that `11`/`12` are
not account identities suitable for linking human players across matches.

The human-account exclusion set covers prior frozen-model exclusions, consumed
controls and original user-provided match identities. Candidate matches must
have no account overlap with this set or one another. An additional byte-level
scan of previous output JSON files checks candidate match IDs and complete
replay hashes without using model scores for selection. Any matching output
reference blocks admission; this is a check of recorded local artifacts, not
proof that an unrecorded external inspection never occurred.

Target selection is fixed in the plan before identity parsing: one target per
match, source cheating labels first, then SHA256(match ID + source ID token).
Rounded source IDs must uniquely match exact account IDs within the replay.
Labels are never inferred for other players in the match.

## Recorded results

All seven matches passed; none had unresolved metadata. Their **70 account
participants** are disjoint across matches and from **700 previously excluded
account identities**. The scan checked 1,526 prior output JSON files and found
no candidate references. All seven retain full replay hashes and raw snapshot
records; bot-event counts and controller identity sets are saved separately.

One selected target per match gives **six legitimate source labels and one
generic cheating label**. The eighth provisional label from the inventory
shares a match with another target and is omitted. This preserves seven
participant-disjoint match cases rather than calling eight players independent.

No trajectory features were extracted and no candidate was scored. The
generated manifest is explicitly `identity_audited_candidates_not_reserved`.
It is not a holdout consumption receipt or authorization to bypass the frozen
evaluator, which is bound to the already-consumed original six-case manifest.
Before scoring these candidates, bind a separate single-use evaluation protocol
to the unchanged model, threshold, audited identities and input hashes. Keep
the old cohort, exclusions and results intact.

Seven convenience-sampled matches cannot establish a low population false
positive rate. The lone positive has no verified active-aimbot annotation.
Use these cases as a small additional independent check; further labeled data
will still be needed. Raw demos, candidate manifests and generated receipts
stay local and ignored.

The metadata-stage statements above are historical. The seven selected cases
have since been reserved and consumed by the separate
[supplemental evaluation](SUPPLEMENTAL_EVALUATION.md). They are no longer fresh
or unscored; their original audit metadata remains immutable.
