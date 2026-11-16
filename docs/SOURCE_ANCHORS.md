# Published case evidence and replay review anchors

The rejected encounter filter remains inactive. This work adds evidence provenance and focused review references; it does not fit a detector or change labels.

## Evidence scope

The [paper, §5.7/5.10](https://arxiv.org/html/2601.18068v1) maps study 1A/1B to Cases C/E and 2B to Case D. It describes Case D as wallhack-only. The [authors' case website](https://xguardian-anti-cheat.github.io/) describes C as aimbot and E as aimbot plus wallhack. Dataset annotations remain binary per player/match, without subtype or activation labels. The adversarial experiment selects existing cases and does not supply controlled cheat configurations.

These are author descriptions, not newly verified event labels. The local evidence index retains the original labels for all 55 cases. Two positive cases have author-described aimbot behavior, one has a wallhack-only description, and thirteen positives have no subtype attribution in this mapping. Legitimate match labels are unchanged. No unknown positive is relabeled legitimate, and D-2B is not dropped from historical metrics.

The existing binary-cheating development result remains 13 TP, 3 FN, 5 FP and 34 TN. It remains a valid description of that generic label task, not measured aimbot-specific recall. D-2B is already flagged by the current baseline; its subtype does not explain the three current misses. No improvement is claimed.

## Row indices are not replay ticks

The published viewer's frame selector uses row indices embedded in image filenames. Its generation script iterates rows of split CSVs. The splitter groups by player/elimination/match and batches twenty elimination samples per CSV. A batch can contain more than one player. Resetting row indices for one selected player can therefore point at the wrong event, even if the guessed tick happens to be a real kill.

The builder scans the original 145 positive split CSV members directly from the already cached artifact prefix. Each member's ZIP identity, decompression, size and CRC are checked against the saved archive index. It preserves the full batch's row positions. Rounded source identity tokens must match exactly one known participant encoding within the replay; they are never converted into invented exact SteamIDs.

Some frame ranges match multiple batches for the same player. Where available, duplicate image CRC/size metadata identifies the elimination in a copied user-study image path. This disambiguates four bookmarks; the remaining bookmark has one matching batch. CRC/size matching is archive metadata evidence, not cryptographic image equality or visual inspection. Ambiguous matches fail instead of selecting the first one.

Every selected source range must contain contiguous recorded ticks, one elimination, one matching player/match and exactly one kill marker matching the local replay death events. Canonical source/report/tracking/telemetry/event receipts are checked. All five mapped events have overlapping existing analysis windows.

## Focused local bookmarks

| Local case | Author case | Published image frames | Source elimination | Replay kill tick |
| --- | --- | --- | ---: | ---: |
| D-1A | C | 768–863 | 17 | 96360 |
| D-1B | E, display 1 | 1344–1439 | 41 | 102387 |
| D-1B | E, display 2 | 1440–1535 | 42 | 102462 |
| D-1B | E, display 3 | 1536–1631 | 43 | 103056 |
| D-2B | D | 1440–1535 | 16 | 52221 |

The index links exact canonical trajectory windows and shows seven saved yaw/pitch samples around each kill. The source-to-replay references remain provisional review aids: no actual game rendering, visibility validation, expert agreement, controlled activation log or cheat-activation ground truth is claimed. Author claims are attributed rather than promoted to training labels. All five rendered-gameplay review statuses remain pending.

An exploratory output that reset per-player indices was invalidated, and its event JSON renamed to prevent accidental use. Final output is `source-anchors-v3`. The earlier 42-event observation queue stays pending and unchanged.

## Reproduce locally

The artifact prefix/index, frozen bundle, source HTML snapshots and small CRC-verified source-script members must already be present locally. The builder makes no network requests and downloads no demos.

```sh
python -m aimguard.source_anchors \
  outputs/xguardian/development-v4 \
  outputs/xguardian/tracking-baseline-v2/frozen \
  data/external/xguardian \
  --output outputs/xguardian/source-anchors-v3
```

Use a new output directory. Protocol records source snapshots/scripts/cache/index hashes, study mapping, code identity and manifest receipt. All raw identities and generated evidence stay under ignored local directories. No source publisher's code is executed; the small frame-range object is parsed as JSON data without JavaScript evaluation.

Tests cover safe range parsing, full-batch versus per-player row indices, distinct frame/tick units, unique rounded-identity matching, gaps/mixed eliminations/kill-event mismatch, ambiguous-batch rejection, copy-metadata disambiguation and cached-member CRC/truncation checks. Original labels, original decisions and frozen runtime integrity are verified separately. The next use of these bookmarks is evidence review; they are not another evaluation cohort or an automatic labeling source.
