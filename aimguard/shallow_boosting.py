"""Fixed shallow boosting comparison with exported, independently replayable trees."""
import argparse
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from scipy.special import expit,logit
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.utils.class_weight import compute_sample_weight

from aimguard.baseline import digest,write_json
from aimguard.error_audit import metrics

PARAMETERS=dict(n_estimators=100,learning_rate=.05,max_depth=2,min_samples_leaf=8,subsample=1.,random_state=0)
THRESHOLD=.75


def fit_trees(values,labels):
    x=np.asarray(values,dtype=float);y=np.asarray(labels)
    if x.ndim!=2 or x.shape[1]!=4 or not np.isfinite(x).all() or (x<0).any() or y.shape!=(len(x),) or set(y)!={0,1}:raise ValueError('Need finite four-feature rows and two training classes')
    weights=compute_sample_weight('balanced',y);model=GradientBoostingClassifier(**PARAMETERS).fit(np.log1p(x),y,sample_weight=weights)
    trees=[]
    for estimator in model.estimators_[:,0]:
        t=estimator.tree_;trees.append(dict(left=t.children_left.tolist(),right=t.children_right.tolist(),feature=t.feature.tolist(),threshold=t.threshold.tolist(),value=t.value[:,0,0].tolist()))
    bundle=dict(initial_margin=float(logit(model.init_.class_prior_[1])),learning_rate=PARAMETERS['learning_rate'],trees=trees,sample_weights=weights.tolist())
    if not np.allclose([tree_score(bundle,v) for v in x],model.predict_proba(np.log1p(x))[:,1],rtol=0,atol=1e-12):raise ValueError('Exported trees do not reproduce training scores')
    return bundle


def tree_score(bundle,values):
    # sklearn tree traversal converts prediction input to float32.
    raw=np.asarray(values,dtype=float)
    if raw.shape!=(4,) or not np.isfinite(raw).all() or (raw<0).any():raise ValueError('Need finite nonnegative four-feature prediction')
    x=np.log1p(raw).astype(np.float32)
    margin=bundle['initial_margin']
    for tree in bundle['trees']:
        node=0
        while tree['left'][node]!=-1:
            node=tree['left'][node] if x[tree['feature'][node]]<=tree['threshold'][node] else tree['right'][node]
        margin+=bundle['learning_rate']*tree['value'][node]
    return float(expit(margin))


def evaluate(values,labels,groups,ids):
    x=np.asarray(values,dtype=float);y=np.asarray(labels);g=np.asarray(groups)
    if x.shape!=(len(ids),4) or not np.isfinite(x).all() or (x<0).any() or y.shape!=(len(ids),) or g.shape!=(len(ids),) or not set(y).issubset({0,1}) or len(set(ids))!=len(ids) or len(set(g))<2:raise ValueError('Need aligned unique finite cases and groups')
    predictions=[];folds=[]
    for number,(train,test) in enumerate(LeaveOneGroupOut().split(x,y,g),1):
        fold=dict(fold=number,train_case_ids=[ids[i] for i in train],held_out_case_ids=[ids[i] for i in test])
        if len(set(y[train]))<2:
            fold['status']='abstained_single_training_class';predictions.extend(dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',status='abstained',error='Training fold has one class') for i in test)
        else:
            bundle=fit_trees(x[train],y[train]);fold.update(status='scored',model=bundle)
            for i in test:
                score=tree_score(bundle,x[i]);predictions.append(dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',status='scored',baseline_score=score,flagged=bool(score>=THRESHOLD)))
        folds.append(fold)
    order={cid:i for i,cid in enumerate(ids)};predictions.sort(key=lambda r:order[r['case_id']]);return dict(predictions=predictions,folds=folds,metrics=metrics(predictions))


def run(pool,reference,output):
    pool,reference,output=map(Path,(pool,reference,output));base=json.loads((pool/'comparison.json').read_text());source=json.loads((pool/'inputs.json').read_text());ref=json.loads((reference/'comparison.json').read_text());rp=json.loads((reference/'protocol.json').read_text())
    if base['inputs_sha256']!=digest(pool/'inputs.json') or base['protocol_sha256']!=digest(pool/'protocol.json') or ref['protocol_sha256']!=digest(reference/'protocol.json') or any(rp['source_sha256'][n]!=digest(pool/n) for n in ('inputs.json','comparison.json','protocol.json')):raise ValueError('Source reference receipts differ')
    rows=source['cases'];ids=[r['case_id'] for r in rows];members=[cid for cs in source['groups'].values() for cid in cs]
    if len(set(members))!=len(members) or set(members)!=set(ids) or any(r['features'] is None or r['label'] not in ('cheating','legitimate') for r in rows):raise ValueError('Invalid development partition')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_fixed_shallow_boosting',recorded_at_utc=datetime.now(timezone.utc).isoformat(),parameters=PARAMETERS,threshold=THRESHOLD,
        transform='log1p; no scaling or learned preprocessing before group splitting',weights='Training-only inverse-frequency balanced weights; mean weight1',
        source_sha256={str(p):digest(p) for p in (pool/'inputs.json',pool/'comparison.json',pool/'protocol.json',reference/'comparison.json',reference/'protocol.json')},code_sha256=digest(__file__),
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','scipy','scikit-learn')},
        note='One preset configuration at the existing fixed0.75 cutoff. No hyperparameter/cutoff search. Uncalibrated scores and inspected development data; no holdout access or model promotion.'))
    g={cid:k for k,cs in source['groups'].items() for cid in cs};model=evaluate([r['features'] for r in rows],[int(r['label']=='cheating') for r in rows],[g[cid] for cid in ids],ids)
    result=dict(models=dict(linear_fixed_cutoff=ref['models']['cost_ratio_threshold'],shallow_boosting=model),protocol_sha256=digest(output/'protocol.json'),promotion_status='development_only_not_frozen');write_json(output/'comparison.json',result)
    lines=['# Fixed shallow boosting development comparison','','| Model | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('pool',type=Path);p.add_argument('reference',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.pool,a.reference,a.output)
