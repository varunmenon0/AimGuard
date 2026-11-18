import numpy as np
import pytest
from aimguard.cost_sensitive import training_weights,evaluate


def test_class_total_ratio_and_constant_total_weight():
    y=np.array([0]*7+[1]*3);w=training_weights(y)
    assert w.mean()==pytest.approx(1) and w.sum()==pytest.approx(10)
    assert w[y==0].sum()/w[y==1].sum()==pytest.approx(3)
    with pytest.raises(ValueError):training_weights([0,0])


def test_outer_features_labels_do_not_enter_scaling_weights_or_fit():
    x=np.arange(32,dtype=float).reshape(8,4);y=[0,1]*4;g=list('aabbccdd');ids=list('ABCDEFGH')
    a=evaluate(x,y,g,ids);x[:2]+=100;y[:2]=[0,0];b=evaluate(x,y,g,ids)
    assert a['folds'][0]==b['folds'][0]
    assert a['predictions'][0]['baseline_score']!=b['predictions'][0]['baseline_score']


def test_invalid_inputs_and_single_class_folds():
    with pytest.raises(ValueError):evaluate([[np.nan]*4]*3,[0,1,0],list('abc'),list('ABC'))
    r=evaluate(np.ones((4,4)),[0,0,0,1],list('abcd'),list('ABCD'))
    assert r['metrics']['abstentions']==1


def test_source_receipts_fail_before_creating_output(tmp_path):
    import json
    from aimguard.cost_sensitive import run
    for name,v in [('comparison.json',{'inputs_sha256':'wrong'}),('inputs.json',{}),('protocol.json',{})]:
        (tmp_path/name).write_text(json.dumps(v))
    with pytest.raises(ValueError,match='receipts'):run(tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()
