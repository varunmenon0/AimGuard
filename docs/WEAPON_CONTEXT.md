# Weapon and grouped-shot context experiment

This is an offline development experiment on 41 inspected cases (16 source-labeled cheating, 25 legitimate), held out by 39 connected participant groups. It does not replace the frozen detector.

Four joint window measurements are log-transformed: near-shot speed and acceleration, pre-shot horizontal error and relative velocity. Weapon family and single/multiple grouped shots define fixed contexts. Grouped shot count does not establish firing mode or recoil state.

Inside each training fold, legitimate case medians define context reference vectors. Each case/context needs five windows and each reference needs two cases; sparse references fall back to weapon family and then global legitimate case medians. Cases carry equal weight. References, scaling and balanced logistic regression (C=1, cutoff 0.5) use training cases only. No threshold or recipe search was performed.

| Recipe | TP | FN | FP | TN |
| --- | ---: | ---: | ---: | ---: |
| Existing speed + tracking | 13 | 3 | 3 | 22 |
| Same joint-window log aggregation without context | 13 | 3 | 3 | 22 |
| Weapon/shot-count centering | 11 | 5 | 5 | 20 |

All cases were scored. The context recipe performed worse and is retained as a negative result. Historical fresh evaluation remains unchanged.

Local reproduction (after preparing the inspected development-v3 pool and its model comparison):

```sh
python -m aimguard.context_models outputs/xguardian/development-v3 outputs/xguardian/development-v3-models --output outputs/xguardian/weapon-context-v1
```

The output directory must be new. Protocol, input hashes, fold references, coverage and predictions are recorded locally. Tests cover family mapping, case weighting, sparse fallback, held-out exclusion and insufficient coverage.
