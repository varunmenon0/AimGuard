import copy
import json
import numpy as np
import pytest
from scipy.stats import multivariate_normal

from aimguard.joint_model import fit_joint,joint_margin,grouped_joint,compare


def sample():
    return np.arange(48,dtype=float).reshape(12,4)+1,np.array([0,1]*6),list('aabbccddeeff'),[str(i) for i in range(12)]


def test_margin_reconstructs_gaussian_log_density_ratio():
    x,y,_,_=sample();bundle=fit_joint(x,y);original=copy.deepcopy(bundle)
    standardized=(np.log1p(x)-bundle['scaler_mean'])/bundle['scaler_scale']
    density=[multivariate_normal.logpdf(standardized,mean=c['mean'],cov=c['covariance']) for c in bundle['classes']]
    assert np.allclose(joint_margin(bundle,x),density[1]-density[0],atol=1e-9)
    assert bundle==original
    assert all(np.linalg.eigvalsh(c['covariance']).min()>0 for c in bundle['classes'])


def test_groups_held_out_from_scaler_and_covariance():
    x,y,g,ids=sample();a=grouped_joint(x,y,g,ids);f=a['folds'][0]
    assert set(f['train_case_ids']).isdisjoint(f['held_out_case_ids'])
    x[:2]*=100;b=grouped_joint(x,y,g,ids)
    assert a['folds'][0]['model']==b['folds'][0]['model']
    assert a['predictions'][0]['decision_margin']!=b['predictions'][0]['decision_margin']
    train=[ids.index(c) for c in f['train_case_ids']]
    assert np.allclose(f['model']['scaler_mean'],np.log1p(x[train]).mean(axis=0))


def test_constant_measurements_are_finite_and_missing_evidence_abstains():
    _,y,g,ids=sample();x=np.ones((12,4));b=fit_joint(x,y)
    assert np.isfinite(joint_margin(b,x)).all()
    values=x.tolist();values[0]=None;r=grouped_joint(values,y,g,ids)
    assert r['predictions'][0]['status']=='abstained' and r['metrics']['abstentions']==1
    assert all(p['status']=='abstained' for p in grouped_joint([None]*12,y,g,ids)['predictions'])


def test_sparse_class_abstains_instead_of_estimating_covariance():
    x,_,g,ids=sample();r=grouped_joint(x,[0]*11+[1],g,ids)
    assert r['metrics']['abstentions']==12
    with pytest.raises(ValueError,match='two training'):fit_joint(x,[0]*11+[1])


def test_invalid_features_and_model_parameters_rejected():
    x,y,g,ids=sample()
    with pytest.raises(ValueError):grouped_joint(x,y,g,['same']*12)
    x[0,0]=-1
    with pytest.raises(ValueError):fit_joint(x,y)
    x[0,0]=1;b=fit_joint(x,y);b['classes'][0]['covariance'][0][0]=-1
    with pytest.raises(ValueError,match='positive definite'):joint_margin(b,x)
    b=fit_joint(x,y);b['scaler_scale'][0]=0
    with pytest.raises(ValueError):joint_margin(b,x)


def test_tampered_phase_comparison_rejected_before_output(tmp_path):
    for name,value in [('comparison.json',{'protocol_sha256':'wrong'}),('protocol.json',{}),('inputs.json',{})]:
        (tmp_path/name).write_text(json.dumps(value))
    with pytest.raises(ValueError,match='receipt'):compare(tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()
