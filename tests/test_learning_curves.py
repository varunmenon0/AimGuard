import json
import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from aimguard.learning_curves import curve,rates,PARAMETERS,run


def sample():
    return np.arange(32,dtype=float).reshape(8,4)+1,[0,1]*4,['a','a','b','b','c','c','d','d'],list('ABCDEFGH')


def test_group_isolation_nested_sizes_and_reproducible_full_fit():
    x,y,g,ids=sample();points=curve(x,y,g,ids,fractions=(.5,1.),repeats=2)
    lookup=dict(zip(ids,g))
    assert len(points[0]['runs'])==2 and len(points[1]['runs'])==1
    for small,full in zip(points[0]['runs'][0]['folds'],points[1]['runs'][0]['folds']):
        assert set(small['train_case_ids'])<=set(full['train_case_ids'])
        assert not {lookup[c] for c in small['train_case_ids']}&{lookup[c] for c in small['held_out_case_ids']}
        indices=[ids.index(cid) for cid in full['train_case_ids']];test=[ids.index(cid) for cid in full['held_out_case_ids']]
        scaler=StandardScaler().fit(np.log1p(x[indices]));model=LogisticRegression(**PARAMETERS).fit(scaler.transform(np.log1p(x[indices])),np.array(y)[indices])
        assert np.allclose(scaler.mean_,full['scaler_mean'])
        assert np.allclose(model.predict_proba(scaler.transform(np.log1p(x[test])))[:,1],full['held_out_scores'])
    assert points==curve(x,y,g,ids,fractions=(.5,1.),repeats=2)


def test_held_group_changes_do_not_affect_its_training_parameters():
    x,y,g,ids=sample();a=curve(x,y,g,ids,fractions=(1.,),repeats=1)[0]['runs'][0]['folds'][0]
    x[:2]*=100;b=curve(x,y,g,ids,fractions=(1.,),repeats=1)[0]['runs'][0]['folds'][0]
    assert a['scaler_mean']==b['scaler_mean'] and a['coefficients']==b['coefficients']
    assert a['held_out_scores']!=b['held_out_scores']


def test_single_class_prefix_abstains_without_resampling():
    x,y,g,ids=sample();g=list('abcdefgh');y=[0]*7+[1]
    points=curve(x,y,g,ids,fractions=(.2,1.),repeats=1)
    assert points[0]['runs'][0]['held_out']['abstained']==8
    assert all(f['status']=='abstained_single_training_class' for f in points[0]['runs'][0]['folds'])
    assert points[-1]['runs'][0]['held_out']['abstained']==1


def test_rates_report_class_denominators_and_missing_evidence():
    r=rates([1,1,0,0],[.8,np.nan,.6,.1])
    assert r==dict(recall=1.,false_positive_rate=.5,scored=3,abstained=1,cheating_scored=1,legitimate_scored=2)
    assert rates([1,0],[np.nan,np.nan])['recall'] is None


def test_invalid_inputs_and_tampered_receipt(tmp_path):
    x,y,g,ids=sample()
    for kwargs in [dict(repeats=0),dict(fractions=(1.,.2)),dict(fractions=(0.,))]:
        with pytest.raises(ValueError):curve(x,y,g,ids,**kwargs)
    x[0,0]=np.nan
    with pytest.raises(ValueError):curve(x,y,g,ids)
    for name,value in [('comparison.json',{'inputs_sha256':'wrong'}),('inputs.json',{}),('protocol.json',{})]:
        (tmp_path/name).write_text(json.dumps(value))
    with pytest.raises(ValueError,match='receipt'):run(tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()
