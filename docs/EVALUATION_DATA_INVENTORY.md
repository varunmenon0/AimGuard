# Local evaluation data inventory

Run the metadata-only audit from the repository root:

```bash
.venv/bin/python -m scripts.inventory_evaluation_data \
  --output outputs/xguardian/evaluation-inventory-v2
```

Use a new output directory for another inventory. The command hashes local
`data/**/*.dem` files, deduplicates by complete file contents, reads participant
identities, and joins source labels through unique rounded-ID matches. It does
not extract trajectories, score players, fit models, or reserve cases. Cached
identities are reused only for the same complete replay hash. Metadata errors
remain explicit failures, never eligible matches.

Exclusions cover the frozen model's inspected identities, all participants in
the six consumed controls, and the original three user-provided matches. A new
target in a previously used match is excluded too. Short numeric IDs retain the
existing strict exclusion policy.

## Recorded November 18 inventory

| Category | Count |
| --- | ---: |
| Local extracted replay files | 119 |
| Distinct complete-file hashes | 86 |
| Duplicate copies | 33 |
| Previously used distinct matches | 72 |
| Other matches with excluded identity overlap | 14 |
| Metadata errors | 0 |
| Eligible matches under the current strict policy | 0 |

The 72 matches comprise 63 development matches, six consumed controls and three
original user-provided matches. The 116 local ZIP files have no demo entry
without an adjacent extracted replay. The partial compressed raw archive is
not a complete extracted inventory and may contain additional data. This audit
does not claim the public dataset is exhausted.

## Identity issue to investigate before downloading more

Seven of the 14 excluded matches overlap full SteamIDs. The other seven overlap
only short numeric IDs `11` or `12`. These are not full SteamIDs and may be
server/bot identifiers reused across matches. Verify their parser semantics
before changing identity exclusions; they remain excluded in this inventory.

Those seven matches have eight uniquely mapped source-labeled players: seven
legitimate labels and one generic cheating label. They are a provisional
metadata opportunity, not eight independent evaluation cases. Two labels share
a match. Cross-match human overlap, prior feature inspection and identity types
still need a separate review before reservation. No scores were examined, and
a generic cheating label does not establish active aimbot use.

The local source tables cover 2,903 matches. Of those, 2,820 have no extracted
demo here, covering 4,998 legitimate and 330 cheating match/player label rows.
These are acquisition leads, not verified fresh participants or independent
cases. Repeat exclusion and exact identity checks after obtaining raw demos.

Next, investigate short-ID exclusions using identity metadata only. Keep the
model and cutoff frozen, and reserve any eligible participant-disjoint cohort
before scoring it. If too few cases remain, continue bounded archive acquisition.

Local `inventory.json` and `report.md` contain every path, hash, status and
overlap. `availability-notes.json` records supplementary ZIP/source-table checks
and the short-ID diagnostic. All data and generated artifacts remain local and
ignored; the frozen model and six-control evaluation are unchanged.
