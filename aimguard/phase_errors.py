"""Explain saved v0.6 errors without fitting models or changing decisions."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path

import numpy as np
from scipy.special import expit

from aimguard.baseline import digest, write_json
from aimguard.phase_development import speed_features
from aimguard.tracking_models import case_features


def explain(values, fold):
    values=np.asarray(values,dtype=float)
    mean=np.asarray(fold['scaler_mean']);scale=np.asarray(fold['scaler_scale']);coef=np.asarray(fold['coefficients'])
    if values.shape!=(4,) or not np.isfinite(values).all() or (values<0).any() or scale.shape!=(4,) or not np.isfinite(scale).all() or (scale<=0).any():
        raise ValueError('Invalid explanation measurements or scale')
    standardized=(np.log1p(values)-mean)/scale;terms=standardized*coef
    if not np.isfinite(terms).all():raise ValueError('Invalid fold parameters')
    margin=float(fold['intercept']+terms.sum())
    if not np.isfinite(margin):raise ValueError('Invalid fold margin')
    return dict(features=values.tolist(),standardized=standardized.tolist(),contributions=terms.tolist(),
        intercept=fold['intercept'],margin=margin,score=float(expit(margin)))


def contexts(report, tracking, fold):
    windows=report['engagements'];tracks=tracking['windows']
    if len(windows)!=len(tracks):raise ValueError('Context window count differs')
    for w,t in zip(windows,tracks):
        if any(w[k]!=t[k] for k in ('engagement_id','shot_ticks','round_id','weapon')):raise ValueError('Context window identity differs')
    rows=[]
    for kind in ('round_id','weapon'):
        for key in sorted({w[kind] for w in windows}):
            indices=[i for i,w in enumerate(windows) if w[kind]==key]
            subset=dict(report,engagements=[windows[i] for i in indices])
            target,coverage=case_features([tracks[i] for i in indices],report['assumed_tickrate_hz'])
            speed=speed_features(subset)
            row=dict(kind=kind,value=key,windows=len(indices),coverage=coverage,explanation=None)
            if speed is not None and target is not None:row['explanation']=explain([*speed,*target],fold)
            rows.append(row)
    return rows


def neighbours(case_id, inputs, predictions, fold):
    if case_id not in fold['held_out_case_ids'] or case_id in fold['train_case_ids']:raise ValueError('Expected held-out case')
    values=explain(inputs[case_id]['features'],fold)['standardized'];rows=[]
    for cid in fold['train_case_ids']:
        p=predictions[cid]
        if p['status']!='scored' or p['flagged']!=(p['label']=='cheating'):continue
        vector=explain(inputs[cid]['features'],fold)['standardized']
        rows.append(dict(case_id=cid,label=p['label'],distance=float(np.linalg.norm(np.asarray(values)-vector))))
    rows.sort(key=lambda r:(r['distance'],r['case_id']))
    return dict(nearest=rows[:3],nearest_by_label={label:next((r for r in rows if r['label']==label),None) for label in ('legitimate','cheating')})


def audit(comparison,analysis,output):
    comparison,analysis,output=map(Path,(comparison,analysis,output))
    result=json.loads((comparison/'comparison.json').read_text());protocol=json.loads((comparison/'protocol.json').read_text())
    source=json.loads((comparison/'inputs.json').read_text())
    if (result['inputs_sha256']!=digest(comparison/'inputs.json') or result['protocol_sha256']!=digest(comparison/'protocol.json')
        or protocol['role']!='inspected_v06_development' or protocol['threshold']!=.5 or source['groups']!=protocol['groups']):raise ValueError('Comparison receipt differs')
    model=result['models']['v06_speed_and_tracking'];predictions={r['case_id']:r for r in model['predictions']}
    inputs={r['case_id']:r for r in source['cases']}
    if len(inputs)!=len(source['cases']) or len(predictions)!=len(model['predictions']) or set(predictions)!=set(inputs):raise ValueError('Case identities differ')
    groups={cid:g for g,cs in source['groups'].items() for cid in cs}
    folds={}
    for fold in model['folds']:
        if set(fold['train_case_ids']) & set(fold['held_out_case_ids']) or {groups[c] for c in fold['train_case_ids']} & {groups[c] for c in fold['held_out_case_ids']}:raise ValueError('Fold leakage')
        for cid in fold['held_out_case_ids']:
            if cid in folds:raise ValueError('Duplicate held-out prediction')
            folds[cid]=fold
    output.mkdir(parents=True,exist_ok=False);rows=[]
    for index,row in enumerate(source['cases'],1):
        cid=row['case_id'];prediction=predictions[cid]
        if row['label']!=prediction['label']:raise ValueError('Case label differs')
        if prediction['status']!='scored':continue
        fold=folds[cid];explanation=explain(row['features'],fold)
        if abs(explanation['score']-prediction['baseline_score'])>1e-12 or prediction['flagged']!=(explanation['score']>=.5):raise ValueError('Saved score differs')
        directory=analysis/f'job_{index:04d}';trackpath=comparison/'tracking'/f'case_{index:04d}.json'
        if digest(directory/'report.json')!=row['report_sha256'] or digest(trackpath)!=row['tracking_sha256']:raise ValueError('Case receipt differs')
        report=json.loads((directory/'report.json').read_text());tracking=json.loads(trackpath.read_text())
        for name,expected in tracking['input_sha256'].items():
            if digest(directory/name)!=expected:raise ValueError('Tracking inputs changed')
        rebuilt_target,coverage=case_features(tracking['windows'],report['assumed_tickrate_hz'])
        rebuilt_speed=speed_features(report)
        if rebuilt_target is None or rebuilt_speed is None or not np.allclose([*rebuilt_speed,*rebuilt_target],row['features'],rtol=0,atol=1e-10):raise ValueError('Feature reconstruction differs')
        error=prediction['flagged']!=(prediction['label']=='cheating')
        rows.append(dict(case_id=cid,label=prediction['label'],flagged=prediction['flagged'],error=error,
            explanation=explanation,controls=neighbours(cid,inputs,predictions,fold),contexts=contexts(report,tracking,fold),
            coverage=coverage,rounds=len({w['round_id'] for w in report['engagements']}),weapons=dict(Counter(w['weapon'] for w in report['engagements'])),
            review=str((directory/'review.html').resolve())))
    write_json(output/'audit.json',dict(cases=rows,features=protocol['recipe']['features'],comparison_sha256=digest(comparison/'comparison.json'),
        code_sha256={n:digest(Path(__file__).with_name(n)) for n in ('phase_errors.py','phase_development.py','tracking_models.py')},
        note='Saved held-out folds only. Contributions are log-odds terms, not causes. Neighbour labels/correctness are inspected descriptive control selection, not independent evidence. Context scores are descriptive reuse of the whole-match fold, not new decisions or activation labels.'))
    names=protocol['recipe']['features'];lines=['# v0.6 error and control investigation','','No fitting, cutoff change or new classification. Contexts overlap and are not independent trials. Contributions explain the saved linear model; they do not establish why a player behaves this way.','',
        '| Error case | Label | Score | Largest positive term | Nearest correct control | Distance |','| --- | --- | ---: | --- | --- | ---: |']
    for row in rows:
        if not row['error']:continue
        e=row['explanation'];terms=e['contributions'];largest=int(np.argmax(terms));nearest=row['controls']['nearest'][0]
        lines.append(f"| {row['case_id']} | {row['label']} | {e['score']:.3f} | {names[largest]} ({terms[largest]:+.3f}) | {nearest['case_id']} ({nearest['label']}) | {nearest['distance']:.3f} |")
    lines+=['','Distances use the explained case’s training-fold scaler. Correct controls are chosen using already-inspected labels and their own out-of-group predictions. No causal or generalization inference follows.','']
    for row in rows:
        if not row['error']:continue
        lines += [f"## {row['case_id']}",'',f"Features: {row['explanation']['features']}. Contributions: {row['explanation']['contributions']}; intercept {row['explanation']['intercept']:.4f}.",
            f"Eligible windows: {row['coverage']['eligible_windows']}; rounds: {row['rounds']}; weapons: {row['weapons']}.",'','| Context | Windows | Eligible | Descriptive score |','| --- | ---: | ---: | ---: |']
        for context in row['contexts']:
            e=context['explanation'];score=f"{e['score']:.3f}" if e else 'insufficient evidence'
            lines.append(f"| {context['kind']}={context['value']} | {context['windows']} | {context['coverage']['eligible_windows']} | {score} |")
        lines+=['',f"Replay analysis: {row['review']}",'']
    text='\n'.join(lines)+'\n';(output/'report.md').write_text(text)
    (output/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>AimGuard error investigation</title><style>body{font:16px system-ui;margin:30px}pre{white-space:pre-wrap;line-height:1.5}</style><pre>'+html.escape(text)+'</pre></html>')
    print(output/'report.md');return rows


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('comparison',type=Path);p.add_argument('analysis',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(argv);audit(a.comparison,a.analysis,a.output)


if __name__=='__main__':main()
