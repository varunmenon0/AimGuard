"""Grouped cross-fitted multi-family review-priority score; not a cheating probability."""
import argparse
from datetime import datetime,timezone
import json
import importlib.metadata
from pathlib import Path

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest,write_json
from aimguard.error_audit import metrics
from aimguard.response_timing import case_response

FAMILIES=('movement','tracking','burst','response')
PARAMETERS=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)


def fit_linear(values,labels):
    x=np.asarray(values,dtype=float);y=np.asarray(labels)
    if x.ndim!=2 or not np.isfinite(x).all() or len(x)!=len(y) or set(y)!={0,1}:raise ValueError('Need finite aligned training matrix and two classes')
    scaler=StandardScaler().fit(x);model=LogisticRegression(**PARAMETERS).fit(scaler.transform(x),y)
    return dict(scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),coefficients=model.coef_[0].tolist(),intercept=float(model.intercept_[0]))


def margin(model,values):
    return float(np.dot((np.asarray(values)-model['scaler_mean'])/model['scaler_scale'],model['coefficients'])+model['intercept'])


def fit_families(rows):
    models={}
    for family in FAMILIES:
        eligible=[r for r in rows if r['families'][family] is not None]
        models[family]=fit_linear([r['families'][family] for r in eligible],[int(r['label']=='cheating') for r in eligible]) if len({r['label'] for r in eligible})==2 else None
    return models


def family_margins(models,row):
    return [margin(models[f],row['families'][f]) if models[f] is not None and row['families'][f] is not None else None for f in FAMILIES]


def meta_rows(values,means):
    # Missing margins use training-only means and separate missingness indicators.
    return [[means[i] if v is None else v for i,v in enumerate(row)]+[int(v is None) for v in row] for row in values]


def fit_stack(rows):
    if len({r['group'] for r in rows})<3:raise ValueError('Need at least three training groups for cross-fitting')
    cross={};inner=[]
    for group in sorted({r['group'] for r in rows}):
        train=[r for r in rows if r['group']!=group];held=[r for r in rows if r['group']==group];models=fit_families(train)
        if len({r['label'] for r in train})<2:raise ValueError('Single-class cross-fit training partition')
        for r in held:cross[r['case_id']]=family_margins(models,r)
        inner.append(dict(train_case_ids=[r['case_id'] for r in train],held_out_case_ids=[r['case_id'] for r in held],models=models))
    values=[cross[r['case_id']] for r in rows]
    means=[float(np.mean([v[i] for v in values if v[i] is not None])) if any(v[i] is not None for v in values) else 0. for i in range(4)]
    x=meta_rows(values,means);meta=fit_linear(x,[int(r['label']=='cheating') for r in rows])
    return dict(meta_model=meta,imputation_means=means,family_models=fit_families(rows),inner_folds=inner,
        cross_fitted_margins=[dict(case_id=r['case_id'],margins=v) for r,v in zip(rows,values)])


def stack_score(model,row):
    values=family_margins(model['family_models'],row);available=sum(v is not None for v in values)
    if available<2:return dict(status='abstained',flagged=None,error='Fewer than two available evidence families',family_margins=values)
    x=meta_rows([values],model['imputation_means'])[0];meta=model['meta_model'];terms=((np.asarray(x)-meta['scaler_mean'])/meta['scaler_scale'])*meta['coefficients'];score=float(expit(meta['intercept']+sum(terms)))
    return dict(status='scored',flagged=bool(score>=.5),baseline_score=score,priority_score=100*score,family_margins=values,meta_inputs=x,contributions=terms.tolist())


def evaluate(rows):
    ids=[r['case_id'] for r in rows]
    if len(set(ids))!=len(ids) or any(r['label'] not in ('cheating','legitimate') for r in rows):raise ValueError('Need unique cases with known labels')
    predictions=[];folds=[]
    for group in sorted({r['group'] for r in rows}):
        train=[r for r in rows if r['group']!=group];held=[r for r in rows if r['group']==group];model=fit_stack(train)
        folds.append(dict(train_case_ids=[r['case_id'] for r in train],held_out_case_ids=[r['case_id'] for r in held],model=model))
        predictions.extend(dict(case_id=r['case_id'],label=r['label'],**stack_score(model,r)) for r in held)
    order={cid:i for i,cid in enumerate(ids)};predictions.sort(key=lambda r:order[r['case_id']]);return dict(predictions=predictions,folds=folds,metrics=metrics(predictions))


def run(pool,bursts,output):
    pool,bursts,output=map(Path,(pool,bursts,output));base=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text());b=json.loads((bursts/'comparison.json').read_text());bi=json.loads((bursts/'inputs.json').read_text());bp=json.loads((bursts/'protocol.json').read_text())
    if (base['inputs_sha256']!=digest(pool/'inputs.json') or base['protocol_sha256']!=digest(pool/'protocol.json')
        or b['inputs_sha256']!=digest(bursts/'inputs.json') or b['protocol_sha256']!=digest(bursts/'protocol.json')
        or bp['source_sha256']['inputs.json']!=digest(pool/'inputs.json') or bp['source_sha256']['comparison.json']!=digest(pool/'comparison.json') or bi['groups']!=source['groups']):raise ValueError('Source evidence receipts differ')
    ids=[r['case_id'] for r in source['cases']];members=[cid for cs in source['groups'].values() for cid in cs]
    if len(set(ids))!=len(ids) or len(set(members))!=len(members) or set(ids)!=set(members):raise ValueError('Invalid case/group partition')
    burst_by={r['case_id']:r for r in bi['cases']}
    if set(burst_by)!=set(ids):raise ValueError('Burst identities differ')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_multi_family_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),families=FAMILIES,
        parameters=PARAMETERS,threshold=.5,minimum_families=2,
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','scipy','pandas','scikit-learn')},
        transforms='log1p movement/tracking; identity burst/response; training-only scaling within each family and meta model',
        method='Outer leave-one-participant-group-out. Inside outer training data, family models cross-fit by group; train meta logistic weights on these out-of-group margins plus missingness flags. Refit families on outer training data only.',
        missing='Training-only mean imputation plus explicit missingness indicators. Missing evidence is not a clean verdict; fewer than two families abstains.',
        source_sha256={str(p):digest(p) for p in (pool/'inputs.json',pool/'comparison.json',pool/'protocol.json',bursts/'inputs.json',bursts/'comparison.json',bursts/'protocol.json')},
        code_sha256={n:digest(Path(__file__).with_name(n)) for n in ('evidence_score.py','response_timing.py','tracking_models.py','development_models.py')},
        note='Fixed architecture, no cutoff/weight/feature search. Correlated families are learned jointly, not multiplied as independent probabilities. Priority score0–100 is uncalibrated, not cheating probability. No holdout use/model promotion.'))
    groups={cid:g for g,cs in source['groups'].items() for cid in cs};rows=[]
    for i,row in enumerate(source['cases'],1):
        trackpath=pool/'tracking'/f'case_{i:04d}.json';track=json.loads(trackpath.read_text())
        if digest(trackpath)!=row['tracking_sha256'] or track['summary']['case_id']!=row['case_id'] or track['summary']['label']!=row['label']:raise ValueError('Tracking identity/hash differs')
        for name,h in track['input_sha256'].items():
            if digest(pool/'analysis'/f'job_{i:04d}'/name)!=h:raise ValueError('Canonical source changed')
        burst=burst_by[row['case_id']]
        if burst['label']!=row['label']:raise ValueError('Burst source label differs')
        response,coverage=case_response(track['windows'],track['assumed_tickrate_hz'])
        raw=row['features'];families=dict(movement=np.log1p(raw[:2]).tolist() if raw is not None else None,tracking=np.log1p(raw[2:]).tolist() if raw is not None else None,burst=burst['burst_features'],response=response)
        rows.append(dict(case_id=row['case_id'],label=row['label'],group=groups[row['case_id']],families=families,response_coverage=coverage,burst_coverage=burst['coverage']))
    write_json(output/'inputs.json',dict(cases=rows,groups=source['groups']))
    model=evaluate(rows);write_json(output/'comparison.json',dict(models=dict(original=base['models']['v06_speed_and_tracking'],evidence_score=model),inputs_sha256=digest(output/'inputs.json'),protocol_sha256=digest(output/'protocol.json'),promotion_status='not_frozen_or_deployed'))
    lines=['# Cross-fitted multi-family review-priority score','','Scores are uncalibrated. No reserved controls used. No threshold search.','', '| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in [('Original',base['models']['v06_speed_and_tracking']),('Evidence score',model)]:
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    lines+=['','| Case | Label | Priority score | Flag at50 | Available families |','| --- | --- | ---: | --- | --- |']
    for p in sorted(model['predictions'],key=lambda r:r.get('priority_score',-1),reverse=True):lines.append(f"| {p['case_id']} | {p['label']} | {p.get('priority_score')} | {p['flagged']} | {sum(v is not None for v in p['family_margins'])} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines[:9]),flush=True);return model


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('bursts',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.pool,a.bursts,a.output)


if __name__=='__main__':main()
