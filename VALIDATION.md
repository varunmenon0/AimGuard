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
