import copy
import numpy as np
import pytest
from scipy.special import expit

from aimguard.phase_errors import explain, neighbours, contexts
from aimguard.phase_gameplay import FEATURE_VERSION, PHASE_POLICY
from aimguard.baseline import EXPECTED_CONFIGURATION


def fold():
    return dict(scaler_mean=[0,1,2,3],scaler_scale=[1,2,3,4],coefficients=[1,-2,3,-4],intercept=.3,
        held_out_case_ids=['A'],train_case_ids=['B','C'])


def test_contributions_reconstruct_score_without_mutating_inputs():
    f=fold();original=copy.deepcopy(f);v=[1,2,3,4];r=explain(v,f)
    assert r['score']==pytest.approx(expit(.3+sum(r['contributions'])))
    assert np.allclose(r['contributions'],np.array([1,-2,3,-4])*(np.log1p(v)-[0,1,2,3])/[1,2,3,4])
    assert f==original
    for bad in ([1,2,3],[-1,2,3,4],[float('nan'),2,3,4]):
        with pytest.raises(ValueError):explain(bad,f)
    f['scaler_scale'][0]=0
    with pytest.raises(ValueError):explain(v,f)


def test_neighbours_use_only_correct_training_controls_with_fold_scaling():
    inputs={k:dict(features=v) for k,v in dict(A=[1,2,3,4],B=[1,2,3,4],C=[2,3,4,5],D=[1,2,3,4]).items()}
    ps={k:dict(status='scored',label='legitimate',flagged=False) for k in inputs}
    ps['B']['flagged']=True
    r=neighbours('A',inputs,ps,fold())
    assert [x['case_id'] for x in r['nearest']]==['C']
    assert r['nearest_by_label']['cheating'] is None
    ps['B']['flagged']=False
    assert neighbours('A',inputs,ps,fold())['nearest'][0]['distance']==0
    f=fold();f['train_case_ids'].append('A')
    with pytest.raises(ValueError):neighbours('A',inputs,ps,f)


def test_context_requires_identity_and_does_not_score_insufficient_coverage(monkeypatch):
    from aimguard import phase_errors as module
    windows=[dict(engagement_id=i,shot_ticks=[i*10],round_id=1,weapon='ak47',movement_context=dict(near_shot=dict(p95_speed=2,mean_accel=3))) for i in range(2)]
    report=dict(feature_version=FEATURE_VERSION,phase_policy=PHASE_POLICY,configuration=dict(EXPECTED_CONFIGURATION),structural_violations=[],engagements=windows,assumed_tickrate_hz=64)
    tracking=dict(windows=copy.deepcopy(windows))
    monkeypatch.setattr(module,'case_features',lambda *args:(None,dict(eligible_windows=2)))
    rows=contexts(report,tracking,fold())
    assert len(rows)==2 and all(r['explanation'] is None for r in rows)
    monkeypatch.setattr(module,'case_features',lambda *args:([4,5],dict(eligible_windows=5)))
    assert contexts(report,tracking,fold())[0]['explanation']['features']==[2,3,4,5]
    tracking['windows'][0]['weapon']='awp'
    with pytest.raises(ValueError,match='identity'):contexts(report,tracking,fold())


def test_audit_rejects_tampered_comparison_before_output(tmp_path):
    import json
    from aimguard.phase_errors import audit
    comparison=tmp_path/'comparison';comparison.mkdir()
    for name,value in [('comparison.json',{'inputs_sha256':'wrong'}),('protocol.json',{}),('inputs.json',{})]:
        (comparison/name).write_text(json.dumps(value))
    with pytest.raises(ValueError,match='receipt'):audit(comparison,tmp_path/'analysis',tmp_path/'out')
    assert not (tmp_path/'out').exists()
