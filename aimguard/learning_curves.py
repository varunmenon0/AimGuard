"""Grouped learning curves on inspected v0.6 development vectors."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest, write_json

FRACTIONS=(.2,.4,.6,.8,1.)
PARAMETERS=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)


def rates(labels, scores):
    labels=np.asarray(labels);scores=np.asarray(scores,dtype=float);valid=np.isfinite(scores)
    positive=valid & (labels==1);negative=valid & (labels==0);flags=scores>=.5
    return dict(recall=float(flags[positive].mean()) if positive.any() else None,
        false_positive_rate=float(flags[negative].mean()) if negative.any() else None,
        scored=int(valid.sum()),abstained=int((~valid).sum()),
        cheating_scored=int(positive.sum()),legitimate_scored=int(negative.sum()))


def curve(values,labels,groups,ids,fractions=FRACTIONS,repeats=10):
    values=np.asarray(values,dtype=float);labels=np.asarray(labels);groups=np.asarray(groups)
    if (values.shape!=(len(ids),4) or not np.isfinite(values).all() or (values<0).any()
        or labels.shape!=(len(ids),) or set(labels)!={0,1} or groups.shape!=(len(ids),)
        or len(set(ids))!=len(ids) or len(set(groups))<3):raise ValueError('Need aligned finite four-feature cases, two classes and three groups')
    if type(repeats) is not int or repeats<1 or not fractions or any(not 0<f<=1 for f in fractions) or list(fractions)!=sorted(set(fractions)):
        raise ValueError('Expected positive repeats and increasing unique fractions in (0,1]')
    prepared=np.log1p(values);unique=sorted(set(groups));points=[]
    for fraction in fractions:
        runs=[]
        for seed in range(1 if fraction==1 else repeats):
            held_scores=np.full(len(ids),np.nan);folds=[];train_rates=[]
            for number,held_group in enumerate(unique):
                available=[g for g in unique if g!=held_group]
                order=np.random.default_rng(np.random.SeedSequence([seed,number])).permutation(len(available))
                count=max(1,int(np.floor(fraction*len(available))))
                chosen=[available[i] for i in order[:count]]
                train=np.flatnonzero(np.isin(groups,chosen));test=np.flatnonzero(groups==held_group)
                record=dict(held_out_case_ids=[ids[i] for i in test],train_case_ids=[ids[i] for i in train],
                    train_groups=len(chosen),train_cases=len(train),train_cheating=int(labels[train].sum()),train_legitimate=int((labels[train]==0).sum()))
                if set(labels[train])!={0,1}:
                    record['status']='abstained_single_training_class'
                else:
                    scaler=StandardScaler().fit(prepared[train]);model=LogisticRegression(**PARAMETERS).fit(scaler.transform(prepared[train]),labels[train])
                    train_scores=model.predict_proba(scaler.transform(prepared[train]))[:,1]
                    scores=model.predict_proba(scaler.transform(prepared[test]))[:,1];held_scores[test]=scores
                    tr=rates(labels[train],train_scores);train_rates.append(tr)
                    record.update(status='scored',scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),
                        coefficients=model.coef_[0].tolist(),intercept=float(model.intercept_[0]),
                        train_scores=train_scores.tolist(),held_out_scores=scores.tolist(),training_rates=tr)
                folds.append(record)
            runs.append(dict(seed=seed,folds=folds,held_out=rates(labels,held_scores),
                training={key:float(np.mean([r[key] for r in train_rates])) if train_rates else None for key in ('recall','false_positive_rate')},
                predictions=[dict(case_id=cid,score=float(score) if np.isfinite(score) else None) for cid,score in zip(ids,held_scores)]))
        summary={}
        for partition in ('training','held_out'):
            summary[partition]={}
            for metric in ('recall','false_positive_rate'):
                nums=[r[partition][metric] for r in runs if r[partition][metric] is not None]
                summary[partition][metric]=dict(mean=float(np.mean(nums)),minimum=float(min(nums)),maximum=float(max(nums))) if nums else None
        points.append(dict(fraction=fraction,train_groups=runs[0]['folds'][0]['train_groups'],
            mean_train_cases=float(np.mean([f['train_cases'] for r in runs for f in r['folds']])),runs=runs,summary=summary))
    return points


def render(output, points):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),layout='constrained')
    x=[p['mean_train_cases'] for p in points]
    for ax,metric,title in zip(axes,('recall','false_positive_rate'),('Cheating cases flagged — higher is better','Legitimate cases falsely flagged — lower is better')):
        for partition,color,label in [('training','#777777','Training fit'),('held_out','#176d9c','Held-out participant groups')]:
            summaries=[p['summary'][partition][metric] for p in points]
            means=[100*s['mean'] if s else np.nan for s in summaries];low=[100*s['minimum'] if s else np.nan for s in summaries];high=[100*s['maximum'] if s else np.nan for s in summaries]
            ax.plot(x,means,'o-',color=color,label=label);ax.fill_between(x,low,high,color=color,alpha=.14)
        ax.set(title=title,xlabel='Mean training cases per fold',ylabel='Percent',ylim=(0,100));ax.grid(alpha=.2);ax.legend(fontsize=9)
    cases=len(points[-1]['runs'][0]['predictions']);groups=len(points[-1]['runs'][0]['folds'])
    fig.suptitle(f'AimGuard learning curves · {cases} inspected cases / {groups} participant groups\nFixed four features, C=1, cutoff 0.5 · bands = subsampling range, not confidence intervals',fontsize=11)
    fig.savefig(output/'learning-curves.png',dpi=170);plt.close(fig)


def run(comparison,output,repeats=10):
    comparison,output=map(Path,(comparison,output));result=json.loads((comparison/'comparison.json').read_text())
    source=json.loads((comparison/'inputs.json').read_text());protocol=json.loads((comparison/'protocol.json').read_text())
    if (result['inputs_sha256']!=digest(comparison/'inputs.json') or result['protocol_sha256']!=digest(comparison/'protocol.json')
        or protocol['role']!='inspected_v06_development' or protocol['threshold']!=.5 or protocol['hyperparameters']!=PARAMETERS
        or source['groups']!=protocol['groups']):raise ValueError('Source comparison receipt/protocol differs')
    rows=source['cases'];ids=[r['case_id'] for r in rows];members=[cid for cs in source['groups'].values() for cid in cs]
    if len(members)!=len(set(members)) or set(ids)!=set(members) or any(r['features'] is None for r in rows):raise ValueError('Need complete eligible vectors and exact group partition')
    group_for={cid:g for g,cs in source['groups'].items() for cid in cs}
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_development_learning_curve',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        fractions=FRACTIONS,repeats=repeats,threshold=.5,hyperparameters=PARAMETERS,features=protocol['recipe']['features'],
        comparison_sha256=digest(comparison/'comparison.json'),inputs_sha256=digest(comparison/'inputs.json'),code_sha256=digest(__file__),
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','scikit-learn','matplotlib')},
        method='Leave one participant group out. Seeded random whole-group training prefixes nested across sizes within seed/fold. Scaling fit only on selected training cases. Single-class subsets abstain without resampling. Full-size run once.',
        caveats='Previously inspected data; not fresh evaluation. Bands show min/max across subsamples, not confidence intervals. Training metrics average folds; held-out metrics pool cases once per repeat. Correlated folds and seeds are not independent evidence. No extrapolation, threshold search or model promotion.'))
    points=curve([r['features'] for r in rows],[int(r['label']=='cheating') for r in rows],[group_for[cid] for cid in ids],ids,repeats=repeats)
    saved={p['case_id']:p for p in result['models']['v06_speed_and_tracking']['predictions']}
    for p in points[-1]['runs'][0]['predictions']:
        if saved[p['case_id']]['status']!='scored' or p['score'] is None or abs(p['score']-saved[p['case_id']]['baseline_score'])>1e-10:raise ValueError('Full-size curve does not reproduce saved baseline')
    write_json(output/'curves.json',dict(points=points,protocol_sha256=digest(output/'protocol.json')));render(output,points)
    lines=['# Grouped learning curves','','Previously inspected development data. Subsampling ranges are not confidence intervals. Rates use scored cases only; abstentions are separate and never counted as legitimate. No demo parsing/viewing or production model changes.','',
        '| Mean training cases | Groups | Held-out detection mean (range) | Held-out false flags mean (range) | Abstentions per repeat |','| ---: | ---: | --- | --- | --- |']
    for point in points:
        cells=[]
        for metric in ('recall','false_positive_rate'):
            s=point['summary']['held_out'][metric];cells.append(f"{s['mean']:.1%} ({s['minimum']:.1%}–{s['maximum']:.1%})" if s else 'unavailable')
        abstentions=[r['held_out']['abstained'] for r in point['runs']]
        lines.append(f"| {point['mean_train_cases']:.1f} | {point['train_groups']} | {' | '.join(cells)} | {min(abstentions)}–{max(abstentions)} |")
    lines+=['','Full-size held-out scores reproduce the saved v0.6 baseline. This curve cannot predict performance beyond the available sample size.']
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return points


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('comparison',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=10)
    a=p.parse_args(argv);run(a.comparison,a.output,a.repeats)


if __name__=='__main__':main()
