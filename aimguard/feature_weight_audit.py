"""Explain false flags and test one training-only feature-contribution damping rule."""
import argparse
from collections import Counter
import json
from pathlib import Path

import numpy as np
from scipy.special import expit

from aimguard.baseline import digest,write_json
from aimguard.error_audit import metrics

FACTOR=.5


def terms(values,fold):
    return ((np.log1p(values)-fold['scaler_mean'])/fold['scaler_scale'])*fold['coefficients']


def select_feature(inner,inputs):
    """Vote among inner out-of-group legitimate false flags only; no outer case used."""
    folds={cid:f for f in inner['folds'] for cid in f['held_out_case_ids']};votes=Counter()
    for p in inner['predictions']:
        if p['status']!='scored' or p['label']!='legitimate' or not p['flagged']:continue
        contribution=terms(inputs[p['case_id']]['features'],folds[p['case_id']])
        if np.max(contribution)>0:votes[int(np.argmax(contribution))]+=1
    selected=min(votes,key=lambda i:(-votes[i],i)) if votes else None
    return selected,{str(k):v for k,v in sorted(votes.items())}


def damped_score(values,fold,selected):
    contribution=terms(values,fold);adjusted=contribution.copy()
    if selected is not None:adjusted[selected]*=FACTOR
    return float(expit(fold['intercept']+adjusted.sum()))


def run(pool,strict,output):
    pool,strict,output=map(Path,(pool,strict,output));base=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text());p=json.loads((pool/'protocol.json').read_text());s=json.loads((strict/'comparison.json').read_text());sp=json.loads((strict/'protocol.json').read_text())
    if (base['inputs_sha256']!=digest(pool/'inputs.json') or base['protocol_sha256']!=digest(pool/'protocol.json')
        or s['protocol_sha256']!=digest(strict/'protocol.json') or p['role']!='inspected_v06_development'
        or any(sp['source_sha256'][n]!=digest(pool/n) for n in ('inputs.json','protocol.json','comparison.json'))):raise ValueError('Source receipts differ')
    inputs={r['case_id']:r for r in source['cases']};groups={cid:g for g,cs in source['groups'].items() for cid in cs}
    baseline=base['models']['v06_speed_and_tracking'];conservative=s['models']['specificity_first'];bp={r['case_id']:r for r in baseline['predictions']};cp={r['case_id']:r for r in conservative['predictions']}
    if set(bp)!=set(inputs) or set(cp)!=set(inputs):raise ValueError('Prediction identity differs')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_feature_weight_development',factor=FACTOR,threshold=.5,
        features=p['recipe']['features'],selection='Each outer fold: most frequent largest positive contribution among legitimate inner out-of-group false flags; tie lowest feature index; none means no damping.',
        operation='Halve selected standardized log-feature coefficient contribution; keep all other coefficients/intercept unchanged. No refit or cutoff search.',
        source_sha256={str(path):digest(path) for path in (pool/'inputs.json',pool/'comparison.json',pool/'protocol.json',strict/'comparison.json',strict/'protocol.json')},
        code_sha256=digest(__file__),
        caveat='Hypothesis motivated by inspected errors. Training-only selection avoids direct outer-case choice but does not make this a fresh evaluation. Scores after damping are uncalibrated. No model promotion or reserved-control use.'))
    predictions=[];records=[];explanations=[]
    for f in conservative['folds']:
        train=f['train_case_ids'];test=f['held_out_case_ids'];inner=f['inner_calibration']
        if set(train)&set(test) or {groups[c] for c in train}&{groups[c] for c in test} or {r['case_id'] for r in inner['predictions']}!=set(train):raise ValueError('Fold partition differs')
        for sub in inner['folds']:
            if (set(sub['train_case_ids'])|set(sub['held_out_case_ids']))&set(test):raise ValueError('Outer case leaked into selection')
        selected,votes=select_feature(inner,inputs);records.append(dict(held_out_case_ids=test,train_case_ids=train,selected_feature=selected,votes=votes,
            scaler_mean=f['scaler_mean'],scaler_scale=f['scaler_scale'],coefficients=f['coefficients'],intercept=f['intercept']))
        for cid in test:
            original=bp[cid];strict_prediction=cp[cid];contribution=terms(inputs[cid]['features'],f);score=float(expit(f['intercept']+contribution.sum()))
            if original['status']!='scored' or strict_prediction['status']!='scored' or abs(score-original['baseline_score'])>1e-12 or abs(score-strict_prediction['baseline_score'])>1e-12:raise ValueError('Original score differs')
            adjusted=damped_score(inputs[cid]['features'],f,selected)
            predictions.append(dict(case_id=cid,label=original['label'],status='scored',baseline_score=adjusted,flagged=bool(adjusted>=.5)))
            if original['label']=='legitimate' and original['flagged']:
                explanations.append(dict(case_id=cid,features=inputs[cid]['features'],contributions=contribution.tolist(),intercept=f['intercept'],
                    original_score=score,strict_cutoff=f['cutoff'],strict_flagged=strict_prediction['flagged'],
                    selected_feature=selected,selection_votes=votes,damped_score=adjusted,damped_flagged=bool(adjusted>=.5)))
    order={r['case_id']:i for i,r in enumerate(source['cases'])};predictions.sort(key=lambda r:order[r['case_id']]);explanations.sort(key=lambda r:order[r['case_id']])
    candidate=dict(predictions=predictions,folds=records,metrics=metrics(predictions))
    result=dict(models=dict(default=baseline,strict=conservative,damped=candidate),false_flag_explanations=explanations,protocol_sha256=digest(output/'protocol.json'),promotion_status='development_only_not_frozen')
    write_json(output/'comparison.json',result)
    lines=['# Feature-weight false-flag investigation','','Contributions are standardized log-odds terms, not causal explanations of gameplay. Strict policy changes cutoffs only.','',
        '| Case | Speed | Acceleration | Alignment error | Relative rate | Intercept | Default score | Strict cutoff | Strict flag | Damped score |','| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |']
    for r in explanations:lines.append('| '+ ' | '.join([r['case_id'],*[f'{v:+.3f}' for v in r['contributions']],f"{r['intercept']:+.3f}",f"{r['original_score']:.3f}",f"{r['strict_cutoff']:.3f}",str(r['strict_flagged']),f"{r['damped_score']:.3f}"] )+' |')
    lines+=['','| Policy | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('strict',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);run(a.pool,a.strict,a.output)


if __name__=='__main__':main()
