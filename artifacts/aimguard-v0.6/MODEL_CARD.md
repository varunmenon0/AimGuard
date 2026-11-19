# AimGuard v0.6 inference package

This directory is included in Git so a fresh clone can score a replay without
access to the author's training files. The JSON model contains four logistic
regression coefficients, intercept, log1p/standardization parameters, the fixed
0.75 review threshold, and the original source/runtime checksums. No pickle or
executable model file is used.

The package is an inference-only export of research artifact
`1cc9bb01d21983c1926cd8434bfc63815d9b07343a5a7f19e56401b39286bdda`.
It preserves every inference parameter exactly. Its file checksum differs
because training-player identities, per-case training vectors, participant
exclusions, local paths and holdout reservations have been removed. This is a
distribution export, not retraining or a new detector candidate. `PACKAGE.json`
records the source, model and parameter checksums. The original research artifact
and evaluation receipts remain local and unchanged.

## Intended use

Offline review of one selected player in a **64 Hz CS2 `.dem`** recording. The
features combine near-shot angular speed and acceleration with pre-shot
horizontal opponent alignment and relative motion. The app displays decisions,
window coverage, curves and feature contributions for human review.

The score is uncalibrated review priority, not the probability of cheating. A
non-flag does not establish legitimate play. Insufficient evidence is unresolved.
Geometric opponent candidates do not prove visibility or intended target.

## Development and measured results

The model was fitted on 63 development players: 46 labeled legitimate and 17
labeled cheating. Its preprocessing and 0.75 threshold were fixed before the
latest reserved evaluation was consumed.

That evaluation scored 55 players from 36 match groups: **4/5 cheating-labeled
players flagged**, **1/50 legitimate players falsely flagged**, and no unresolved
cases. These are observed small-cohort results (80% detection, 2% false positives),
not established population rates. Some players share a match and are not
independent samples. XGuardian's generic cheating labels do not identify active
aimbot intervals or prove that aim assistance was the cheat subtype.

See [the final error audit](../../docs/FINAL_ERROR_AUDIT.md) for the false flag,
missed positive, and rejected last tuning candidate. Repeated scoring or package
verification does not constitute fresh evaluation.

## Runtime and reproducibility

Use **Python 3.12.10** and [the pinned runtime](../../requirements-runtime.txt).
The unchanged detector verifies 16 source files, six dependency versions, Python,
configuration, feature recipe, threshold and model checksum before inference.
Do not relax these checks to make a different runtime appear compatible.

The package supports the `score` command and local interface. Research-only
freeze/evaluation commands require the original local artifacts and participant
reservations; this package cannot establish an untouched evaluation split.

## Files and license

| File | Purpose |
| --- | --- |
| `model.json` | Inference parameters and runtime/source receipt |
| `model.sha256` | SHA-256 of `model.json` |
| `PACKAGE.json` | Export provenance and parameter checksum |

The model parameters and AimGuard code are distributed under the repository's
[MIT license](../../LICENSE). No CS2 recordings or dataset annotations are
redistributed. The underlying research dataset is credited in the project
documentation; obtain recordings separately under their source terms.
