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
