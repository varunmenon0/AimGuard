"""Audit subtype provenance without turning generic cheating labels into activation truth."""
import argparse
from collections import Counter
import json
from pathlib import Path

from aimguard.baseline import digest,write_json

KINDS={'author_described_aimbot':'author_described_aimbot',
       'author_described_aimbot_and_wallhack':'author_described_aimbot_and_wallhack',
       'author_described_wallhack_only':'author_described_wallhack_only'}


def classify(label,evidence=None):
    if label not in ('cheating','legitimate'):raise ValueError('Unknown original label')
    if label=='legitimate':
        if evidence:raise ValueError('Subtype attribution conflicts with original label')
        kind='source_labeled_legitimate'
    elif evidence:
        kind=KINDS.get(evidence.get('author_description'))
        if kind is None:raise ValueError('Unknown author subtype attribution')
    else:kind='cheating_subtype_unknown'
    return dict(original_label=label,subtype_evidence=kind,activation_status='not_verified',
        verified_activation_intervals=[],eligible_as_confirmed_aimbot_positive=False,
        author_evidence=evidence,
        reason='Published narrative is not verified activation evidence' if evidence else 'Source binary label does not establish aimbot activation')


def require_active_aimbot_training(audit):
    """This audit has no activation evidence; fail rather than reuse binary labels."""
    if audit.get('role')!='aimbot_label_provenance_audit':raise ValueError('Expected subtype provenance audit')
    raise ValueError('Active-aimbot training blocked: this provenance audit contains no verified activation evidence')


def build(pool,original_manifest,new_manifest,anchors,output):
    pool,original_manifest,new_manifest,anchors,output=map(Path,(pool,original_manifest,new_manifest,anchors,output))
    result=json.loads((pool/'comparison.json').read_text());inputs=json.loads((pool/'inputs.json').read_text())
    if result['inputs_sha256']!=digest(pool/'inputs.json') or result['protocol_sha256']!=digest(pool/'protocol.json'):raise ValueError('Pool receipt differs')
    old=json.loads(original_manifest.read_text());new=json.loads(new_manifest.read_text())
    evidence=json.loads((anchors/'anchors.json').read_text());protocol=json.loads((anchors/'protocol.json').read_text())
    if evidence['protocol_sha256']!=digest(anchors/'protocol.json') or protocol['manifest_sha256']!=digest(original_manifest):raise ValueError('Source mapping receipt differs')
    if evidence['training_labels_changed'] is not False or evidence['activation_ground_truth'] is not None:raise ValueError('Unexpected source evidence scope')
    metadata=old['cases']+new['cases'];by_id={c['case_id']:c for c in metadata}
    if len(by_id)!=len(metadata) or set(by_id)!={r['case_id'] for r in inputs['cases']}:raise ValueError('Metadata case identities differ')
    mapped={c['case_id']:c for c in evidence['cases']}
    rows=[]
    for i,row in enumerate(inputs['cases'],1):
        cid=row['case_id'];case=by_id[cid];report_path=pool/'analysis'/f'job_{i:04d}'/'report.json'
        report=json.loads(report_path.read_text())
        if row['label']!=case['label'] or digest(report_path)!=row['report_sha256'] or report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256']:raise ValueError('Case identity/label differs')
        attribution=mapped.get(cid)
        if attribution and (attribution['original_label']!=row['label'] or attribution['aimbot_activation_ground_truth'] is not None):raise ValueError('Source label/activation scope differs')
        rows.append(dict(case_id=cid,demo_sha256=case['demo_sha256'],report_sha256=row['report_sha256'],
            **classify(row['label'],attribution.get('author_case_evidence') if attribution else None)))
    output.mkdir(parents=True,exist_ok=False)
    audit=dict(role='aimbot_label_provenance_audit',cases=rows,counts=dict(Counter(r['subtype_evidence'] for r in rows)),
        confirmed_active_aimbot_positives=0,active_aimbot_training_ready=False,original_labels_changed=False,
        source_sha256={str(p):digest(p) for p in (original_manifest,new_manifest,anchors/'anchors.json',anchors/'protocol.json',pool/'inputs.json',pool/'comparison.json')},
        code_sha256=digest(__file__),
        note='No video, model score or geometric feature is used to infer activation. Wallhack-only and unknown cases are not confirmed aimbot positives or newly assigned legitimate examples. Historical generic-cheating metrics remain unchanged.')
    write_json(output/'audit.json',audit)
    lines=['# Aimbot label provenance audit','','No verified active-aimbot positive examples. Active-aimbot training is not ready. Historical labels/results are unchanged.','',
        '| Positive case | Subtype evidence | Confirmed activation | Eligible confirmed aimbot positive |','| --- | --- | --- | --- |']
    for r in rows:
        if r['original_label']=='cheating':lines.append(f"| {r['case_id']} | {r['subtype_evidence']} | No | No |")
    lines+=['','Counts: '+str(audit['counts']),'','Author descriptions support case-level attribution only. No subtype inference is made for other cases. No unknown or wallhack-only case becomes a legitimate training example.']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return audit


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('pool','original_manifest','new_manifest','anchors'):p.add_argument(name,type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);build(a.pool,a.original_manifest,a.new_manifest,a.anchors,a.output)


if __name__=='__main__':main()
