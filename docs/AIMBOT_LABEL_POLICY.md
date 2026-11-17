# Aimbot subtype and activation evidence

Generic cheating labels must not be treated as proof of active aimbot use. This policy follows the user's explicit requirement to distinguish aimbots from wallhacks. Existing historical labels and generic-cheating results remain unchanged.

## Audited current pool

The expanded pool has 63 cases, including 17 source-labeled cheating cases. The source-attributed mapping linked to the original manifest supports:

| Cases | Evidence | Confirmed activation intervals |
| --- | --- | --- |
| D-1A | Author-described aimbot, Case C | None |
| D-1B | Author-described aimbot plus wallhack, Case E | None |
| D-2B | Author-described wallhack-only, Case D | None |
| Other 14 positives | Binary cheating label, subtype unknown | None |

The [paper §5.10](https://arxiv.org/html/2601.18068v1) maps user-study 1A/1B/2B to Cases C/E/D. Section 5.7 explicitly describes D as wallhack-only. The [author case website](https://xguardian-anti-cheat.github.io/) supplies the case narratives for C and E. The saved source-anchor receipts bind these descriptions to local identities; they do not create activation ground truth. The paper's adversarial discussion also states that specific cheat functions/configurations were unavailable. Broad use of the term aim-assist in the paper does not make every positive an aimbot case.

The two author-described aimbot cases are useful source-attributed examples, but no inspected training window is verified as having aimbot active. The new N-004 positive remains subtype-unknown. Source-labeled legitimate cases also are not newly certified by this audit.

## Rules for future aimbot-specific work

- Keep original binary labels and provenance immutable. No silent correction of historical metrics.
- Exclude wallhack-only and unknown-subtype cases from **confirmed active-aimbot positives**. They do not become legitimate negatives.
- Keep author narrative, expert-reviewed behavior and instrumented activation as separate evidence levels. Scores, geometric precision, browser reconstructions and suspicious motion cannot certify activation.
- Require a defensible identity/time link for activation evidence: replay hash, exact target identity, interval units/bounds, evidence source and independently documented aimbot configuration/activation records. Match-level author attribution alone is insufficient for tick/window labels.
- Never label every window of an aimbot-described match as activated. Timing and subtype uncertainty must remain explicit.
- Preserve the six reserved legitimate controls and all prior evaluation receipts. No new holdout is consumed by this audit.

There are currently **zero confirmed active-aimbot positive cases** under these requirements, so the existing dataset is not ready for training/evaluating confirmed active-aimbot detection. Existing models remain generic-cheating development baselines. Their 14/17 positive recall is not aimbot-specific recall. Acquiring activation-linked evidence is a data requirement; another classifier does not supply it.

## Reproduce

```sh
python -m aimguard.aimbot_labels \
  outputs/xguardian/expanded-phase-pool-v2 \
  outputs/xguardian/development-v4/manifest.json \
  outputs/xguardian/expanded-phase-pool-v2/new-development-inspected.json \
  outputs/xguardian/source-anchors-v3 \
  --output outputs/xguardian/aimbot-label-audit-v1
```

The local audit/report covers all 63 cases, preserves source hashes and records explicit false eligibility for confirmed active-aimbot positives. The audit consumer guard rejects use of this provenance-only audit to authorize activation training. It is not a replacement for existing generic-label training commands and does not retroactively change them. No demo viewing, new training or evaluation is performed.
