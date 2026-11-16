"""Server-flag phase gate for inspected development windows; preserve legacy artifacts."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import digest,report_features,write_json
from aimguard.tracking_models import case_features,with_abstentions

WARMUP='is_warmup_period'
STARTED='CCSGameRulesProxy.CCSGameRules.m_bHasMatchStarted'


def global_phase(frame):
    """Global flags repeat across players; conflicting/missing states remain unknown."""
    result={}
    for tick,rows in frame.groupby('tick',sort=True):
        if not np.isfinite(tick) or tick%1:raise ValueError('Phase ticks must be finite integers')
        state={}
        for name in (WARMUP,STARTED):
            values=rows[name].dropna().unique() if name in rows else []
            state[name]=bool(values[0]) if len(values)==1 and isinstance(values[0],(bool,np.bool_)) else None
        result[int(tick)]=state
    return result


def window_phase(ticks,states):
    ticks=list(ticks)
    if not ticks or any(type(t) is not int for t in ticks) or any(b<=a for a,b in zip(ticks,ticks[1:])):
        raise ValueError('Window phase ticks must be unique increasing integers')
    counts=Counter()
    for tick in ticks:
        state=states.get(tick,{})
        if state.get(WARMUP) is True:counts['warmup']+=1
        elif state.get(STARTED) is False:counts['match_not_started']+=1
        elif state.get(WARMUP) is False and state.get(STARTED) is True:counts['live']+=1
        else:counts['unknown']+=1
    status='live' if counts['live']==len(ticks) else ('warmup' if counts['warmup'] else ('match_not_started' if counts['match_not_started'] else 'unknown'))
    return dict(status=status,samples=len(ticks),sample_states=dict(counts))


def compare(pool,baseline_directory,output):
    from demoparser2 import DemoParser
    pool,baseline_directory,output=map(Path,(pool,baseline_directory,output))
    manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    baseline=json.loads((baseline_directory/'comparison.json').read_text());protocol=json.loads((baseline_directory/'protocol.json').read_text())
    inputs=json.loads((baseline_directory/'inputs.json').read_text())
    if (manifest.get('role')!='development' or not manifest.get('features_inspected') or receipt['manifest_sha256']!=digest(pool/'manifest.json')
        or protocol['manifest_sha256']!=digest(pool/'manifest.json') or baseline['protocol_sha256']!=digest(baseline_directory/'protocol.json')
        or baseline['inputs_sha256']!=digest(baseline_directory/'inputs.json') or inputs['groups']!=receipt['groups']
        or protocol['threshold']!=.5 or protocol['hyperparameters']!=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)):
        raise ValueError('Inspected phase-audit source receipt mismatch')
    cases=manifest['cases'];ids=[c['case_id'] for c in cases]
    members=[cid for rows in receipt['groups'].values() for cid in rows]
    if len(ids)!=len(set(ids)) or len(members)!=len(set(members)) or set(ids)!=set(members):raise ValueError('Group identity mismatch')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='phase_checked_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        recipes=dict(legacy_speed_and_tracking=protocol['recipes']['speed_and_tracking'],phase_checked_speed_and_tracking=protocol['recipes']['speed_and_tracking']),
        cases=[dict(case_id=cid) for cid in ids],source_properties=[WARMUP,STARTED],threshold=.5,hyperparameters=protocol['hyperparameters'],
        rule='Keep a window only if every supporting original telemetry sample explicitly has warmup=false and match-started=true. Missing/conflicting states are unknown; do not assume live.',
        manifest_sha256=digest(pool/'manifest.json'),baseline_sha256=digest(baseline_directory/'comparison.json'),
        code_sha256={n:digest(Path(__file__).with_name(n)) for n in ('phase_audit.py','baseline.py','tracking_models.py','development_models.py')},
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','pandas','scikit-learn','demoparser2')},
        note='Server phase quality gate, not a behavior filter or cutoff search. Legacy reports and frozen model are not overwritten. Future extraction must explicitly apply this phase gate.'))
    vectors=[];rows=[]
    for index,case in enumerate(cases,1):
        directory=pool/'analysis'/f'job_{index:04d}';path=pool/'tracking'/f'case_{index:04d}.json'
        report=json.loads((directory/'report.json').read_text());tracking=json.loads(path.read_text());expected=receipt['cases'][index-1]
        if (expected['case_id']!=case['case_id'] or digest(directory/'report.json')!=expected['report_sha256']
            or digest(path)!=expected['tracking_sha256'] or report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256']
            or digest(case['demo'])!=case['demo_sha256'] or tracking['summary']['case_id']!=case['case_id'] or tracking['summary']['label']!=case['label']):
            raise ValueError('Phase audit case identity/hash mismatch')
        for name in ('report.json','telemetry.csv','events.json'):
            if digest(directory/name)!=tracking['input_sha256'][name]:raise ValueError('Phase audit canonical checksum mismatch')
        telemetry=pd.read_csv(directory/'telemetry.csv',usecols=['tick','segment_id','active'])
        if telemetry.tick.duplicated().any() or not np.isfinite(telemetry.tick).all() or (telemetry.tick%1).any():raise ValueError('Invalid phase support ticks')
        windows=report['engagements'];supports=[]
        if len(windows)!=len(tracking['windows']):raise ValueError('Phase source window counts mismatch')
        for w,t in zip(windows,tracking['windows']):
            if any(w[k]!=t[k] for k in ('engagement_id','shot_ticks','round_id','weapon')):raise ValueError('Phase window identity mismatch')
            part=telemetry.loc[telemetry.segment_id.eq(w['segment_id']) & telemetry.tick.between(w['start_tick'],w['end_tick'])]
            if len(part)!=w['samples'] or not part.active.all():raise ValueError('Phase support differs from published window')
            supports.append([int(tick) for tick in part.tick])
        requested=sorted({tick for ticks in supports for tick in ticks})
        frame=DemoParser(case['demo']).parse_ticks([WARMUP,STARTED],ticks=requested)
        states=global_phase(frame);kept=[];tracks=[];details=[];counts=Counter()
        for w,t,ticks in zip(windows,tracking['windows'],supports):
            phase=window_phase(ticks,states);counts[phase['status']]+=1
            details.append(dict(engagement_id=w['engagement_id'],first_shot_tick=w['shot_ticks'][0],round_id=w['round_id'],**phase))
            if phase['status']=='live':kept.append(w);tracks.append(t)
        values=None;coverage={}
        if kept:
            target,coverage=case_features(tracks,report['assumed_tickrate_hz'])
            if target is not None:
                speed,_=report_features(dict(report,engagements=kept));values=[*speed,*target]
        vectors.append(values)
        row=dict(case_id=case['case_id'],label=case['label'],features=values,window_counts=dict(counts),windows=details,coverage=coverage,
            missing_properties=[name for name in (WARMUP,STARTED) if name not in frame.columns],demo_sha256=case['demo_sha256'],report_sha256=digest(directory/'report.json'),tracking_sha256=digest(path))
        rows.append(row);write_json(output/f'case_{index:04d}.json',row)
        print(f"{case['case_id']}: {counts['live']}/{len(windows)} live; {counts['warmup']} warmup; {counts['unknown']} unknown",flush=True)
    by_case={cid:int(g) for g,group in receipt['groups'].items() for cid in group};groups=[by_case[cid] for cid in ids]
    write_json(output/'inputs.json',dict(cases=rows,groups=receipt['groups']))
    candidate=with_abstentions(vectors,[int(c['label']=='cheating') for c in cases],groups,ids,'log1p')
    for row in candidate['predictions']:
        if row['status']=='abstained' and row.get('error','').startswith('Fewer than'):row['error']='Fewer than five eligible phase-verified live pre-shot windows'
    result=dict(cases=len(cases),participant_groups=len(set(groups)),models=dict(legacy_speed_and_tracking=baseline['models']['speed_and_tracking'],phase_checked_speed_and_tracking=candidate),
        protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        interpretation='Inspected development phase-quality comparison. Legacy results preserved. No new frozen/deployed model or independent performance claim.')
    write_json(output/'comparison.json',result)
    lines=['# Server-flag phase-quality audit','','All supporting samples must be explicitly live. No unknown state is assumed live. Legacy source artifacts are unchanged.','',
        '| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,model in result['models'].items():
        c=model['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {model['metrics']['abstentions']} |")
    total=Counter()
    for row in rows:total.update(row['window_counts'])
    lines+=['',str(dict(total)),'','This is a source-data quality gate, not the rejected stable-alignment exclusion idea. No new cheating activation labels or model promotion.']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('pool',type=Path);parser.add_argument('baseline_directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv);compare(args.pool,args.baseline_directory,args.output)


if __name__=='__main__':main()
