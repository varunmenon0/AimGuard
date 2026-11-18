"""Fixed three-to-one class-total loss weighting on phase-clean development data."""
import argparse
from datetime import datetime,timezone
import json
import importlib.metadata
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest,write_json
from aimguard.error_audit import metrics

LEGITIMATE_CLASS_MULTIPLIER=3.


def training_weights(labels):
    y=np.asarray(labels)
    if y.ndim!=1 or set(y)!={0,1}:raise ValueError('Both binary training classes required')
    weights=np.array([len(y)/(2*np.sum(y==label)) for label in y])
    weights*=np.where(y==0,LEGITIMATE_CLASS_MULTIPLIER,1.)
    return weights/weights.mean()


def evaluate(values,labels,groups,ids):
    x=np.asarray(values,dtype=float);y=np.asarray(labels);g=np.asarray(groups)
    if x.shape!=(len(ids),4) or not np.isfinite(x).all() or (x<0).any() or y.shape!=(len(ids),) or g.shape!=(len(ids),) or not set(y).issubset({0,1}) or len(set(ids))!=len(ids) or len(set(g))<2:raise ValueError('Need aligned finite four-feature cases and participant groups')
    x=np.log1p(x);predictions=[];folds=[]
    for number,(train,test) in enumerate(LeaveOneGroupOut().split(x,y,g),1):
        record=dict(fold=number,train_case_ids=[ids[i] for i in train],held_out_case_ids=[ids[i] for i in test])
        if len(set(y[train]))<2:
            record['status']='abstained_single_training_class';predictions.extend(dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',status='abstained',error='Training fold has one class') for i in test)
        else:
            weights=training_weights(y[train]);scaler=StandardScaler().fit(x[train]);model=LogisticRegression(C=1,solver='lbfgs',max_iter=1000,random_state=0).fit(scaler.transform(x[train]),y[train],sample_weight=weights);scores=model.predict_proba(scaler.transform(x[test]))[:,1]
            record.update(status='scored',sample_weights=weights.tolist(),training_labels=y[train].tolist(),scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),coefficients=model.coef_[0].tolist(),intercept=float(model.intercept_[0]))
            predictions.extend(dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',status='scored',baseline_score=float(s),flagged=bool(s>=.5)) for i,s in zip(test,scores))
        folds.append(record)
    order={cid:i for i,cid in enumerate(ids)};predictions.sort(key=lambda r:order[r['case_id']]);return dict(predictions=predictions,folds=folds,metrics=metrics(predictions))


def run(pool,output):
    pool,output=map(Path,(pool,output));base=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text());p=json.loads((pool/'protocol.json').read_text())
    if base['inputs_sha256']!=digest(pool/'inputs.json') or base['protocol_sha256']!=digest(pool/'protocol.json') or p['role']!='inspected_v06_development' or p['threshold']!=.5 or source['groups']!=p['groups']:raise ValueError('Source receipts differ')
    rows=source['cases'];ids=[r['case_id'] for r in rows];members=[cid for cs in source['groups'].values() for cid in cs]
    if len(ids)!=len(set(ids)) or len(members)!=len(set(members)) or set(ids)!=set(members) or any(r['features'] is None or r['label'] not in ('cheating','legitimate') for r in rows):raise ValueError('Need complete unique development cases and exact group partition')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_cost_sensitive_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),legitimate_class_multiplier=LEGITIMATE_CLASS_MULTIPLIER,
        weighting='Start with inverse-frequency balanced weights in outer training data, multiply legitimate weights by3, normalize mean weight to1. Class-total loss weights are3:1; total sample weight stays n.',
        features=p['recipe']['features'],C=1,threshold=.5,analytical_original_threshold=LEGITIMATE_CLASS_MULTIPLIER/(1+LEGITIMATE_CLASS_MULTIPLIER),
        analytical_control_note='Added as a cost-equivalent control after the initial weighted fit; cutoff is derived from the fixed cost ratio, not chosen from held-out scores.',
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','scipy','scikit-learn')},transform='log1p then unweighted training-only StandardScaler',
        source_sha256={n:digest(pool/n) for n in ('inputs.json','protocol.json','comparison.json')},code_sha256=digest(__file__),
        note='One fixed objective change, no cost/cutoff/feature search. Weighted scores are not calibrated cheating probabilities. No holdout use or model promotion.'))
    g={cid:key for key,cs in source['groups'].items() for cid in cs};model=evaluate([r['features'] for r in rows],[int(r['label']=='cheating') for r in rows],[g[cid] for cid in ids],ids)
    threshold=LEGITIMATE_CLASS_MULTIPLIER/(1+LEGITIMATE_CLASS_MULTIPLIER)
    control_predictions=[dict(r,flagged=bool(r['baseline_score']>=threshold)) if r['status']=='scored' else dict(r) for r in base['models']['v06_speed_and_tracking']['predictions']]
    control=dict(predictions=control_predictions,metrics=metrics(control_predictions),threshold=threshold,note='Original model, analytically derived cost-ratio cutoff; no refit or cutoff search.')
    result=dict(models=dict(original=base['models']['v06_speed_and_tracking'],cost_ratio_threshold=control,cost_sensitive=model),protocol_sha256=digest(output/'protocol.json'),promotion_status='development_only_not_frozen');write_json(output/'comparison.json',result)
    lines=['# Fixed cost-sensitive training experiment','','| Model | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.pool,a.output)
