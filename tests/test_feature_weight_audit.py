import numpy as np
import pytest
from aimguard.feature_weight_audit import select_feature,terms,damped_score,run


def fold():return dict(scaler_mean=[0]*4,scaler_scale=[1]*4,coefficients=[1,2,3,4],intercept=-1,held_out_case_ids=['a'])


def test_selection_uses_only_inner_legitimate_false_flags():
    f=fold();inner=dict(folds=[f],predictions=[dict(case_id='a',status='scored',label='legitimate',flagged=True)])
    values={'a':{'features':[1,1,1,1]}}
    assert select_feature(inner,values)==(3,{'3':1})
    inner['predictions'][0]['label']='cheating'
    assert select_feature(inner,values)==(None,{})
    inner['predictions'][0].update(label='legitimate',flagged=False)
    assert select_feature(inner,values)==(None,{})


def test_damping_changes_only_selected_term_and_can_raise_negative_term_score():
    f=fold();v=[1,2,3,4];before=terms(v,f)
    expected=before.copy();expected[2]*=.5
    assert damped_score(v,f,2)==pytest.approx(1/(1+np.exp(-(-1+expected.sum()))))
    assert f['coefficients']==[1,2,3,4]
    assert damped_score(v,f,None)==pytest.approx(1/(1+np.exp(-(-1+before.sum()))))
    f['coefficients'][2]=-3
    assert damped_score(v,f,2)>damped_score(v,f,None)


def test_modified_source_rejected_before_output(tmp_path):
    import json
    for name,v in [('comparison.json',{'inputs_sha256':'wrong'}),('inputs.json',{}),('protocol.json',{})]:
        (tmp_path/name).write_text(json.dumps(v))
    with pytest.raises(ValueError):run(tmp_path,tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()
