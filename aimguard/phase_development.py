"""Fixed grouped development comparison on regenerated v0.6 engagements."""
import argparse
from datetime import datetime, timezone
import json
import importlib.metadata
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.baseline import FEATURES, EXPECTED_CONFIGURATION, digest, write_json
from aimguard.phase_gameplay import FEATURE_VERSION, PHASE_POLICY
from aimguard.target_tracking import extract_case
from aimguard.tracking_models import case_features, with_abstentions


def speed_features(report):
    """Explicit v0.6 reader; never disguise inputs as the frozen legacy version."""
    if report.get('feature_version') != FEATURE_VERSION or report.get('phase_policy') != PHASE_POLICY:
        raise ValueError('Expected explicit v0.6 phase-checked report')
    if any(report['configuration'].get(k) != v for k, v in EXPECTED_CONFIGURATION.items()):
        raise ValueError('Configuration differs from the fixed comparison')
    if report.get('structural_violations') != []:
        raise ValueError('Report has missing or failed structural validation')
    result=[]
    for name in FEATURES:
        measurements=[w['movement_context']['near_shot'][name] for w in report['engagements']]
        valid=[float(v) for v in measurements if v is not None and np.isfinite(v) and v>=0]
        if not valid:return None
        result.append(float(np.median(valid)))
    return result


def verify_live(directory, report):
    frame=pd.read_csv(directory/'telemetry.csv')
    if frame.tick.duplicated().any():raise ValueError('Duplicate support ticks')
    active=frame.loc[frame.active.eq(True)]
    if not (active.phase_status.eq('live') & active.phase_warmup.eq(False) & active.phase_match_started.eq(True)).all():
        raise ValueError('Non-live active telemetry')
    for w in report['engagements']:
        part=frame.loc[frame.tick.between(w['start_tick'],w['end_tick'])]
        if len(part)!=w['samples'] or not (part.active.eq(True)&part.segment_id.eq(w['segment_id'])).all():
            raise ValueError('Window support mismatch')


def compare(pool, analysis, baseline, output):
    pool,analysis,baseline,output=map(Path,(pool,analysis,baseline,output))
    manifest=json.loads((pool/'manifest.json').read_text());receipt=json.loads((pool/'pool-receipt.json').read_text())
    old=json.loads((baseline/'comparison.json').read_text());protocol=json.loads((baseline/'protocol.json').read_text())
    old_inputs=json.loads((baseline/'inputs.json').read_text())
    cases=manifest['cases'];ids=[c['case_id'] for c in cases]
    groups=receipt['groups'];members=[cid for group in groups.values() for cid in group]
    if (manifest.get('role')!='development' or not manifest.get('features_inspected')
        or receipt['manifest_sha256']!=digest(pool/'manifest.json')
        or protocol['manifest_sha256']!=digest(pool/'manifest.json')
        or old['protocol_sha256']!=digest(baseline/'protocol.json')
        or old['inputs_sha256']!=digest(baseline/'inputs.json') or old_inputs['groups']!=groups
        or len(ids)!=len(set(ids)) or len(members)!=len(set(members)) or set(ids)!=set(members)
        or protocol['threshold']!=.5 or protocol['hyperparameters']!=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)):
        raise ValueError('Development source/protocol receipt mismatch')
    batch=json.loads((analysis/'summary.json').read_text())
    if batch['feature_version']!=FEATURE_VERSION or len(batch['jobs'])!=len(cases) or batch['counts']['error']:
        raise ValueError('Incomplete v0.6 batch')
    output.mkdir(parents=True,exist_ok=False);(output/'tracking').mkdir()
    write_json(output/'protocol.json',dict(role='inspected_v06_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        feature_version=FEATURE_VERSION,phase_policy=PHASE_POLICY,threshold=.5,hyperparameters=protocol['hyperparameters'],
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','pandas','scikit-learn','demoparser2')},
        recipe=protocol['recipes']['speed_and_tracking'],groups=groups,
        manifest_sha256=digest(pool/'manifest.json'),baseline_sha256=digest(baseline/'comparison.json'),batch_sha256=digest(analysis/'summary.json'),
        code_sha256={n:digest(Path(__file__).with_name(n)) for n in ('phase_development.py','phase_gameplay.py','phase_audit.py','target_tracking.py','target_geometry.py','tracking_models.py','development_models.py','baseline.py','gameplay.py','combat.py','core.py')},
        note='Same fixed recipe and participant folds; regenerated v0.6 inputs. No cutoff/feature search. Inspected development diagnostics, not fresh evaluation or a promoted model.'))
    rows=[];vectors=[]
    for index,(case,job) in enumerate(zip(cases,batch['jobs']),1):
        directory=analysis/f'job_{index:04d}';report=json.loads((directory/'report.json').read_text())
        if (job['steamid']!=case['steamid'] or job['source_sha256']!=case['demo_sha256']
            or report['steamid']!=case['steamid'] or report['source_sha256']!=case['demo_sha256']
            or digest(case['demo'])!=case['demo_sha256']):raise ValueError('Case source identity mismatch')
        for name,expected in report['runtime_sha256'].items():
            if digest(Path(__file__).with_name(name))!=expected:raise ValueError('Extraction runtime changed')
        speed=speed_features(report);verify_live(directory,report)
        tracking=extract_case(case,directory);write_json(output/'tracking'/f'case_{index:04d}.json',tracking)
        target,coverage=case_features(tracking['windows'],report['assumed_tickrate_hz'])
        values=[*speed,*target] if speed is not None and target is not None else None
        vectors.append(values)
        row=dict(case_id=case['case_id'],label=case['label'],features=values,coverage=coverage,
            windows=report['engagement_count'],phase_exclusions=report['data_quality']['phase_excluded_previously_active'],
            report_sha256=digest(directory/'report.json'),tracking_sha256=digest(output/'tracking'/f'case_{index:04d}.json'))
        rows.append(row);print(f"{index}/{len(cases)} {case['case_id']}: {row['windows']} windows; {coverage['eligible_windows']} eligible",flush=True)
    write_json(output/'inputs.json',dict(cases=rows,groups=groups))
    by_case={cid:int(g) for g,group in groups.items() for cid in group}
    model=with_abstentions(vectors,[int(c['label']=='cheating') for c in cases],[by_case[cid] for cid in ids],ids,'log1p')
    result=dict(cases=len(cases),participant_groups=len(groups),models=dict(legacy_speed_and_tracking=old['models']['speed_and_tracking'],v06_speed_and_tracking=model),
        protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        interpretation='Inspected grouped development diagnostics; no fresh performance claim or replacement frozen model.')
    write_json(output/'comparison.json',result)
    lines=['# Regenerated v0.6 development comparison','','| Inputs | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    lines+=['','Inspected development only. Same fixed four features, C=1, cutoff 0.5 and participant groups. No threshold search or model promotion.']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('pool','analysis','baseline'):p.add_argument(name,type=Path)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);compare(a.pool,a.analysis,a.baseline,a.output)


if __name__=='__main__':main()
