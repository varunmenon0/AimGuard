import json
import pytest
from aimguard import specificity_policy as module
from aimguard.baseline import digest,evaluation_metrics


def test_rejects_modified_source_before_output(tmp_path):
    for name,v in [('comparison.json',{'inputs_sha256':'wrong'}),('inputs.json',{}),('protocol.json',{})]:
        (tmp_path/name).write_text(json.dumps(v))
    with pytest.raises(ValueError,match='receipt'):module.run(tmp_path,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_uses_declared_groups_and_preserves_default_model(tmp_path,monkeypatch):
    rows=[dict(case_id=str(i),label='cheating' if i==0 else 'legitimate',features=[1,2,3,4]) for i in range(3)]
    groups={str(i):[str(i)] for i in range(3)}
    def put(name,v):(tmp_path/name).write_text(json.dumps(v))
    put('inputs.json',dict(cases=rows,groups=groups))
    put('protocol.json',dict(role='inspected_v06_development',threshold=.5,groups=groups,hyperparameters=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0)))
    predictions=[dict(case_id=str(i),label=r['label'],status='scored',flagged=False,baseline_score=.1) for i,r in enumerate(rows)]
    original=dict(predictions=predictions,metrics=evaluation_metrics(predictions));seen=[]
    put('comparison.json',dict(inputs_sha256=digest(tmp_path/'inputs.json'),protocol_sha256=digest(tmp_path/'protocol.json'),models={'v06_speed_and_tracking':original}))
    def policy(values,labels,g,ids):seen.append((labels,g,ids));return original
    monkeypatch.setattr(module,'low_false_flag_predictions',policy)
    r=module.run(tmp_path,tmp_path/'out')
    assert seen==[([1,0,0],['0','1','2'],['0','1','2'])]
    assert r['models']['default_cutoff']==original
    assert r['promotion_status']=='development_only_not_frozen'
