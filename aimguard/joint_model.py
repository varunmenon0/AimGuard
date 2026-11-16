"""One shrinkage Gaussian interaction model on inspected phase-clean vectors."""
import argparse
from datetime import datetime,timezone
import importlib.metadata
import json
from pathlib import Path

import numpy as np
from scipy.special import expit
from sklearn.covariance import LedoitWolf
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler

from aimguard.baseline import digest,evaluation_metrics,write_json
from aimguard.tracking_models import TRACKING_RECIPES

EIGENVALUE_FLOOR=1e-6


def fit_joint(values,labels):
    """Called only on selected training rows; equal class priors match balanced baseline."""
    x=np.asarray(values,dtype=float);y=np.asarray(labels)
    if x.ndim!=2 or x.shape[1]!=4 or not np.isfinite(x).all() or (x<0).any() or y.shape!=(len(x),) or set(y)!={0,1}:
        raise ValueError('Need finite four-feature training rows and two classes')
    if any((y==label).sum()<2 for label in (0,1)):raise ValueError('Need two training cases per class for covariance')
    scaler=StandardScaler().fit(np.log1p(x));prepared=scaler.transform(np.log1p(x));classes=[]
    for label in (0,1):
        estimator=LedoitWolf().fit(prepared[y==label]);covariance=estimator.covariance_
        eigenvalues,eigenvectors=np.linalg.eigh(covariance)
        covariance=(eigenvectors*np.maximum(eigenvalues,EIGENVALUE_FLOOR))@eigenvectors.T
        classes.append(dict(label=label,mean=estimator.location_.tolist(),covariance=covariance.tolist(),
            shrinkage=float(estimator.shrinkage_),prior=.5))
    return dict(scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),classes=classes)


def joint_margin(bundle,values):
    x=np.asarray(values,dtype=float)
    if x.ndim!=2 or x.shape[1]!=4 or not np.isfinite(x).all() or (x<0).any():raise ValueError('Need finite nonnegative four-feature rows')
    mean=np.asarray(bundle['scaler_mean']);scale=np.asarray(bundle['scaler_scale'])
    if mean.shape!=(4,) or scale.shape!=(4,) or not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale<=0).any() or [c['label'] for c in bundle['classes']]!=[0,1]:raise ValueError('Invalid scaler or class order')
    prepared=(np.log1p(x)-mean)/scale;density=[]
    for cls in bundle['classes']:
        covariance=np.asarray(cls['covariance']);mean=np.asarray(cls['mean'])
        if covariance.shape!=(4,4) or mean.shape!=(4,) or not np.isfinite(covariance).all() or not np.isfinite(mean).all() or not np.allclose(covariance,covariance.T) or cls['prior']!=.5:raise ValueError('Invalid class distribution')
        try:np.linalg.cholesky(covariance)
        except np.linalg.LinAlgError as error:raise ValueError('Class covariance must be positive definite') from error
        sign,logdet=np.linalg.slogdet(covariance)
        if sign<=0:raise ValueError('Class covariance must be positive definite')
        delta=prepared-cls['mean'];quadratic=np.einsum('ij,ji->i',delta,np.linalg.solve(covariance,delta.T))
        density.append(-.5*(logdet+quadratic)+np.log(cls['prior']))
    return density[1]-density[0]


def grouped_joint(values,labels,groups,ids):
    y=np.asarray(labels);g=np.asarray(groups)
    if len(values)!=len(ids) or y.shape!=(len(ids),) or g.shape!=(len(ids),) or not set(y).issubset({0,1}) or len(set(ids))!=len(ids):raise ValueError('Aligned unique cases and binary labels required')
    valid=[i for i,v in enumerate(values) if v is not None]
    if valid:
        matrix=np.asarray([values[i] for i in valid],dtype=float)
        if matrix.shape!=(len(valid),4) or not np.isfinite(matrix).all() or (matrix<0).any():raise ValueError('Invalid measurements')
    predictions=[dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',status='abstained',error='Insufficient eligible windows') for i,v in enumerate(values) if v is None];folds=[]
    if len(set(g[valid]))<2:
        predictions.extend(dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',status='abstained',error='Insufficient eligible groups') for i in valid)
    else:
        for number,(train,test) in enumerate(LeaveOneGroupOut().split(matrix,y[valid],g[valid]),1):
            train_indices=[valid[i] for i in train];test_indices=[valid[i] for i in test]
            record=dict(fold=number,train_case_ids=[ids[i] for i in train_indices],held_out_case_ids=[ids[i] for i in test_indices])
            if any((y[train_indices]==label).sum()<2 for label in (0,1)):
                record['status']='abstained_insufficient_training_class'
                predictions.extend(dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',fold=number,status='abstained',error='Need two training cases per class') for i in test_indices)
            else:
                bundle=fit_joint(matrix[train],y[train_indices]);margins=joint_margin(bundle,matrix[test]);record.update(status='scored',model=bundle)
                predictions.extend(dict(case_id=ids[i],label='cheating' if y[i] else 'legitimate',fold=number,status='scored',
                    decision_margin=float(margin),model_score=float(expit(margin)),flagged=bool(margin>=0)) for i,margin in zip(test_indices,margins))
            folds.append(record)
    order={cid:i for i,cid in enumerate(ids)};predictions.sort(key=lambda p:order[p['case_id']]);metrics=evaluation_metrics(predictions)
    for key in ('detection_rate','false_positive_rate','precision','accuracy'):metrics[key].pop('exact_95_interval',None)
    metrics['diagnostic_only']=True
    return dict(predictions=predictions,folds=folds,metrics=metrics)


def compare(comparison,output):
    comparison,output=map(Path,(comparison,output));baseline=json.loads((comparison/'comparison.json').read_text());protocol=json.loads((comparison/'protocol.json').read_text());inputs=json.loads((comparison/'inputs.json').read_text())
    if (baseline['protocol_sha256']!=digest(comparison/'protocol.json') or baseline['inputs_sha256']!=digest(comparison/'inputs.json')
        or protocol['role']!='inspected_v06_development' or protocol['feature_version']!='0.6.0'
        or protocol['recipe']!=TRACKING_RECIPES['speed_and_tracking'] or protocol['threshold']!=.5
        or protocol['hyperparameters']!=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0) or inputs['groups']!=protocol['groups']):raise ValueError('Phase-clean comparison receipt differs')
    rows=inputs['cases'];ids=[r['case_id'] for r in rows];members=[cid for cs in inputs['groups'].values() for cid in cs]
    if len(set(ids))!=len(ids) or len(set(members))!=len(members) or set(ids)!=set(members) or any(r['label'] not in ('cheating','legitimate') for r in rows):raise ValueError('Case/group identities differ')
    old=baseline['models']['v06_speed_and_tracking']
    if len(old['predictions'])!=len(rows) or {r['case_id']:r['label'] for r in old['predictions']}!={r['case_id']:r['label'] for r in rows}:raise ValueError('Baseline labels differ')
    output.mkdir(parents=True,exist_ok=False)
    write_json(output/'protocol.json',dict(role='inspected_joint_model_development',recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        features=TRACKING_RECIPES['speed_and_tracking']['features'],transform='log1p, training-fold StandardScaler',
        estimator='Separate class Gaussian with training-only LedoitWolf covariance shrinkage',priors=[.5,.5],margin_cutoff=0,eigenvalue_floor=EIGENVALUE_FLOOR,
        comparison_sha256=digest(comparison/'comparison.json'),inputs_sha256=digest(comparison/'inputs.json'),code_sha256=digest(__file__),
        dependencies={n:importlib.metadata.version(n) for n in ('numpy','scipy','scikit-learn')},
        note='One fixed interaction recipe; no cutoff, feature or hyperparameter search. Equal-prior model scores are not calibrated cheating probabilities. Inspected grouped diagnostics, not fresh evaluation or deployment.'))
    write_json(output/'inputs.json',inputs)
    by_case={cid:g for g,cs in inputs['groups'].items() for cid in cs}
    model=grouped_joint([r['features'] for r in rows],[int(r['label']=='cheating') for r in rows],[by_case[cid] for cid in ids],ids)
    result=dict(models=dict(phase_clean_linear=old,shrinkage_joint=model),protocol_sha256=digest(output/'protocol.json'),inputs_sha256=digest(output/'inputs.json'),
        promotion_status='not_frozen_or_deployed')
    write_json(output/'comparison.json',result)
    old_by={r['case_id']:r for r in old['predictions']};changed=[dict(case_id=r['case_id'],label=r['label'],old=old_by[r['case_id']],new=r) for r in model['predictions'] if (r['status'],r.get('flagged'))!=(old_by[r['case_id']]['status'],old_by[r['case_id']].get('flagged'))]
    write_json(output/'changed-cases.json',changed)
    lines=['# Fixed joint-distribution development model','','| Recipe | TP | FN | FP | TN | Abstentions |','| --- | ---: | ---: | ---: | ---: | ---: |']
    for name,m in result['models'].items():
        c=m['metrics']['confusion'];lines.append(f"| {name} | {c['true_positive']} | {c['false_negative']} | {c['false_positive']} | {c['true_negative']} | {m['metrics']['abstentions']} |")
    lines+=['','No fresh performance claim or model promotion.','', 'Changed cases: '+', '.join(c['case_id'] for c in changed)]
    (output/'report.md').write_text('\n'.join(lines)+'\n');print('\n'.join(lines),flush=True);return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('comparison',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv);compare(a.comparison,a.output)


if __name__=='__main__':main()
