# Recoil and shot-event field validation

This audit validates recorded field timing before proposing recoil-derived supporting evidence. It covers every published shot in the 63-case phase-clean development pool. No classifier, recoil correction, activation annotation or reserved-control extraction is introduced.

The [parser field reference](https://github.com/LaihoE/demoparser#list-of-fields-the-parser-supports) maps aim_punch_angle to CCSPlayerPawn.m_aimPunchAngle and shots_fired to m_iShotsFired. Those aliases do not establish raw mouse input, rendered camera semantics or actual bullet-ray reconstruction.

## Fixed procedure

Request yaw, pitch, aim_punch_angle, shots_fired and active_weapon_name at each published shot's exact tick and the two ticks on either side, for the selected player only. Require all five samples to remain in the same live segment and to have the event's weapon equipped. Preserve unavailable samples instead of filling or interpreting them as zero. Re-extracted view angles must reproduce canonical float32 telemetry.

Parser weapon names are display strings, whereas event names are internal identifiers. The first exploratory pass rejected many valid pairs because of this mismatch. The final run uses explicit aliases (e.g. AK-47 → ak47, M4A4 → m4a1, M4A1-S → m4a1_silencer), keeping distinct guns separate. This mapping change affects support matching, not any model. The initial v1 output is superseded by v2.

For available support, retain counter deltas, counter resets, view/punch component step magnitudes and their recorded two-component cosine. Wrap yaw differences. Zero vector norm gives an undefined cosine, not zero evidence. The comparison uses pitch/yaw view increments against punch components 0/1 as observed; it does not certify a physical correction, recoil compensation, actual target direction or cheat use. Adjacent shots may share samples; counts/cosines are not independent trials.

## Findings

| Support/result | Count |
| --- | ---: |
| Published shot references | 16,505 |
| Exact live, stable matching-weapon support | 16,136 |
| Outside same live segment | 342 |
| Weapon changed or mismatched | 27 |
| Supported shots with counter rise at fire-event tick | 16,123 |
| Supported shots without a nearby counter rise | 13 |
| Supported windows containing a counter reset | 1,201 |

All 63 cases return the requested fields. About 99.9% of supported shots have a counter increase at the fire-event tick. No supported shot has a positive counter change solely at a different offset in the ±2-tick support. This validates useful tick-level coherence in this dataset, not sub-tick firing order or universal counter behavior.

Thirteen exceptions span both labels and several weapons, including a legitimate N-002 Deagle event. One example has the counter recorded as zero throughout all five ticks despite its published fire event. These observations remain exceptions; absence of a counter rise is not a silent-aim or no-shot rule.

Median case recorded-component cosine is approximately -0.214 for cheating labels and -0.176 for legitimate labels. The case ranges overlap substantially: [-0.805,0] and [-0.707,0.032]. These are descriptive summaries, not a significance test or a detector. The six false flags also span this overlapping region. Opposed motion exists in legitimate play and cannot by itself establish an anti-recoil cheat.

Therefore the audit validates field availability and shot/counter timing, but **does not establish a recoil correction or a new reliable cheat signal**. No classifier is fitted on these values. Generic-label/default, strict and historical outcomes remain unchanged. Any subsequent feature must account for ordinary recoil control, weapon context, sample dependence and validated angle semantics rather than treating opposition or a missing increment as cheating.

## Reproduce

```sh
python -m aimguard.recoil_event_audit \
  outputs/xguardian/expanded-phase-pool-v2 \
  --output outputs/xguardian/recoil-event-audit-v2
```

Use a new output directory. The protocol records source/code hashes, dependencies, properties and fixed support before extraction. Per-case JSON retains observed fields and every shot's availability/derived measurements. summary.json and report.md provide the case summaries; verification.json records independently checked deltas, cosines, counts and the thirteen counter exceptions. Raw/generated artifacts remain local and ignored. No game client or viewer is opened.
