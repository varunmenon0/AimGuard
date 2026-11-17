"""Append newly registered development cases; never read held-out trajectory inputs."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path

import numpy as np

from aimguard.baseline import digest,write_json,evaluation_metrics
from aimguard.phase_development import speed_features,verify_live
from aimguard.target_tracking import extract_case
from aimguard.tracking_models import case_features,with_abstentions


def expand(base,base_analysis,cohorts,analysis,output):
    base,base_analysis,cohorts,analysis,output=map(Path,(base,base_analysis,cohorts,analysis,output))
    old=json.loads((base/'comparison.json').read_text());source=json.loads((base/'inputs.json').read_text());protocol=json.loads((base/'protocol.json').read_text())
    manifest=json.loads((cohorts/'development.json').read_text());registration=json.loads((cohorts/'registration.json').read_text())
    if (old['inputs_sha256']!=digest(base/'inputs.json') or old['protocol_sha256']!=digest(base/'protocol.json')
        or protocol['role']!='inspected_v06_development' or protocol['threshold']!=.5
        or protocol['hyperparameters']!=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0) or source['groups']!=protocol['groups']
        or manifest['role']!='development' or manifest['features_inspected'] is not False
        or registration['development_manifest_sha256']!=digest(cohorts/'development.json')
        or registration['holdout_manifest_sha256']!=digest(cohorts/'holdout.json')):raise ValueError('Expansion source receipts differ')
    new=manifest['cases'];old_ids={r['case_id'] for r in source['cases']}
    if not new or len({c['case_id'] for c in new})!=len(new) or any(c['case_id'] in old_ids or c['partition']!='development' for c in new):raise ValueError('Development case identities differ')
    registered=[c for c in registration['cases'] if c['partition']=='development']
    if registered!=new:raise ValueError('Development registration differs')
    hold=[c for c in registration['cases'] if c['partition']=='holdout']
    if {p for c in new for p in c['participants']}&{p for c in hold for p in c['participants']}:raise ValueError('Holdout participant overlap')
    batch=json.loads((analysis/'summary.json').read_text())
    if batch['feature_version']!='0.6.0' or batch['counts']['error'] or len(batch['jobs'])!=len(new):raise ValueError('New phase batch incomplete')
    output.mkdir(parents=True,exist_ok=False)
    for name in ('analysis','tracking','new-tracking'):(output/name).mkdir()
    groups=dict(source['groups'])
    for c in new:
        key='new-'+c['case_id']
        if key in groups:raise ValueError('Group key collision')
        groups[key]=[c['case_id']]
    write_json(output/'protocol.json',dict({k:protocol[k] for k in ('role','feature_version','phase_policy','threshold','hyperparameters','recipe','dependencies')},recorded_at_utc=datetime.now(timezone.utc).isoformat(),groups=groups,
        base_comparison_sha256=digest(base/'comparison.json'),development_manifest_sha256=digest(cohorts/'development.json'),
        holdout_manifest_sha256=digest(cohorts/'holdout.json'),registration_sha256=digest(cohorts/'registration.json'),
        code_sha256={n:digest(Path(__file__).with_name(n)) for n in ('expand_phase_pool.py','phase_development.py','phase_gameplay.py','target_tracking.py','tracking_models.py','development_models.py')},
        note='Expanded inspected development only; original source labels preserved. New cohort holdout has no extracted features and is not scored. No model promoted.'))
    rows=[]
    for i,row in enumerate(source['cases'],1):
        directory=base_analysis/f'job_{i:04d}';track=base/'tracking'/f'case_{i:04d}.json'
        if digest(directory/'report.json')!=row['report_sha256'] or digest(track)!=row['tracking_sha256']:raise ValueError('Base canonical inputs changed')
        (output/'analysis'/f'job_{i:04d}').symlink_to(directory.resolve(),target_is_directory=True)
        (output/'tracking'/f'case_{i:04d}.json').symlink_to(track.resolve());rows.append(row)
    for i,c in enumerate(new,1):
        directory=analysis/f'job_{i:04d}';report=json.loads((directory/'report.json').read_text());job=batch['jobs'][i-1]
        if (job['steamid']!=c['steamid'] or job['source_sha256']!=c['demo_sha256']
            or report['steamid']!=c['steamid'] or report['source_sha256']!=c['demo_sha256']):raise ValueError('New report identity differs')
        speed=speed_features(report);verify_live(directory,report);tracking=extract_case(c,directory)
        trackpath=output/'new-tracking'/f'case_{i:04d}.json';write_json(trackpath,tracking)
        target,coverage=case_features(tracking['windows'],report['assumed_tickrate_hz'])
        vector=[*speed,*target] if speed is not None and target is not None else None
        index=len(rows)+1
        (output/'analysis'/f'job_{index:04d}').symlink_to(directory.resolve(),target_is_directory=True)
        (output/'tracking'/f'case_{index:04d}.json').symlink_to(trackpath.resolve())
        rows.append(dict(case_id=c['case_id'],label=c['label'],features=vector,coverage=coverage,windows=report['engagement_count'],
            phase_exclusions=report['data_quality']['phase_excluded_previously_active'],report_sha256=digest(directory/'report.json'),tracking_sha256=digest(trackpath)))
        print(f"{i}/{len(new)} {c['case_id']}: {coverage['eligible_windows']} eligible windows",flush=True)
    write_json(output/'inputs.json',dict(cases=rows,groups=groups))
    write_json(output/'new-development-inspected.json',dict(manifest,cases=[dict(c,features_inspected=True) for c in new],features_inspected=True,fresh_holdout=False,
        note='Only development partition extracted. Original metadata manifest remains immutable; holdout remains uninspected.'))
    by_case={cid:g for g,cs in groups.items() for cid in cs};ids=[r['case_id'] for r in rows]
    model=with_abstentions([r['features'] for r in rows],[int(r['label']=='cheating') for r in rows],[by_case[cid] for cid in ids],ids,'log1p')
    subsets={}
    for name,wanted in [('original_cases',old_ids),('new_development_cases',{c['case_id'] for c in new})]:
        metrics=evaluation_metrics([r for r in model['predictions'] if r['case_id'] in wanted])
        for metric in ('detection_rate','false_positive_rate','precision','accuracy'):metrics[metric].pop('exact_95_interval',None)
        metrics['diagnostic_only']=True;subsets[name]=metrics
    result=dict(metrics_by_origin=subsets,cases=len(rows),participant_groups=len(groups),models=dict(v06_speed_and_tracking=model),
        original_55_baseline=old['models']['v06_speed_and_tracking'],
        protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        note='Expanded grouped development diagnostics. New cases are development feedback, not fresh held-out evidence. Separate metadata holdout remains untouched.')
    write_json(output/'comparison.json',result)
    lines=['# Expanded phase-clean development pool','','| Cohort | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,metrics in [('Historical original 55',old['models']['v06_speed_and_tracking']['metrics']),*subsets.items(),('Expanded combined',model['metrics'])]:
        c=metrics['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {metrics['abstentions']} |")
    lines+=['','Development diagnostics only. Original-case/new-case rows use expanded training folds; historical baseline uses its original training folds. Holdout is not scored. Different totals have different denominators; no automatic promotion.']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','base_analysis','cohorts','analysis'):p.add_argument(name,type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);expand(a.base,a.base_analysis,a.cohorts,a.analysis,a.output)


if __name__=='__main__':main()
