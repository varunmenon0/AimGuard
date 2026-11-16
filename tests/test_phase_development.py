import copy
import json

import pandas as pd
import pytest

from aimguard.baseline import EXPECTED_CONFIGURATION
from aimguard.phase_development import speed_features, verify_live, compare
from aimguard.phase_gameplay import FEATURE_VERSION, PHASE_POLICY


def report():
    return dict(feature_version=FEATURE_VERSION,phase_policy=PHASE_POLICY,configuration=dict(EXPECTED_CONFIGURATION),
        structural_violations=[],engagements=[dict(start_tick=1,end_tick=2,samples=2,segment_id=0,
        movement_context=dict(near_shot=dict(p95_speed=10,mean_accel=20)))])


def test_explicit_version_and_configuration_without_legacy_spoofing():
    r=report();original=copy.deepcopy(r)
    assert speed_features(r)==[10,20]
    assert r==original
    for key,value in [('feature_version','0.5.0'),('phase_policy','unknown'),('structural_violations',[{}])]:
        bad=copy.deepcopy(r);bad[key]=value
        with pytest.raises(ValueError):speed_features(bad)
    r['configuration']['pre_seconds']=1
    with pytest.raises(ValueError):speed_features(r)


def test_no_evidence_is_not_a_zero_vector():
    r=report();r['engagements']=[]
    assert speed_features(r) is None
    r=report();r['engagements'][0]['movement_context']['near_shot']['p95_speed']=None
    assert speed_features(r) is None


def test_exported_support_must_be_live_contiguous_segment(tmp_path):
    r=report()
    frame=pd.DataFrame(dict(tick=[1,2],active=[True,True],segment_id=[0,0],phase_status=['live','live'],
        phase_warmup=[False,False],phase_match_started=[True,True]))
    def save():frame.to_csv(tmp_path/'telemetry.csv',index=False)
    save();verify_live(tmp_path,r)
    frame.loc[0,'phase_warmup']=True;save()
    with pytest.raises(ValueError,match='Non-live'):verify_live(tmp_path,r)
    frame.loc[0,'phase_warmup']=False;frame.loc[1,'segment_id']=1;save()
    with pytest.raises(ValueError,match='support'):verify_live(tmp_path,r)
    frame.loc[1,'segment_id']=0;frame.loc[1,'tick']=1;save()
    with pytest.raises(ValueError,match='Duplicate'):verify_live(tmp_path,r)


def test_comparison_rejects_unreceipted_sources_before_creating_output(tmp_path):
    pool=tmp_path/'pool';baseline=tmp_path/'baseline';pool.mkdir();baseline.mkdir()
    data={pool/'manifest.json':dict(role='development',features_inspected=True,cases=[]),
        pool/'pool-receipt.json':dict(groups={},manifest_sha256='wrong'),
        baseline/'comparison.json':{},baseline/'protocol.json':{},baseline/'inputs.json':{}}
    for path,value in data.items():path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='receipt'):compare(pool,tmp_path/'analysis',baseline,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_fixed_grouped_comparison_records_new_inputs_and_abstention(tmp_path,monkeypatch):
    from aimguard import phase_development as module
    from aimguard.baseline import digest
    pool=tmp_path/'pool';base=tmp_path/'base';analysis=tmp_path/'analysis'
    for p in (pool,base,analysis):p.mkdir()
    def put(path,value):path.write_text(json.dumps(value))
    cases=[];jobs=[]
    for i,label in enumerate(('cheating','legitimate'),1):
        demo=tmp_path/f'{i}.dem';demo.write_bytes(str(i).encode());sid=str(i)
        cases.append(dict(case_id=f'C{i}',label=label,steamid=sid,demo=str(demo),demo_sha256=digest(demo)))
        jobs.append(dict(steamid=sid,source_sha256=digest(demo)))
        directory=analysis/f'job_{i:04d}';directory.mkdir()
        r=report();r.update(steamid=sid,source_sha256=digest(demo),runtime_sha256={},assumed_tickrate_hz=64,
            engagement_count=1,data_quality=dict(phase_excluded_previously_active={'warmup':3}))
        put(directory/'report.json',r)
    put(pool/'manifest.json',dict(role='development',features_inspected=True,cases=cases))
    groups={'0':['C1'],'1':['C2']}
    put(pool/'pool-receipt.json',dict(groups=groups,manifest_sha256=digest(pool/'manifest.json')))
    put(base/'inputs.json',dict(groups=groups))
    put(base/'protocol.json',dict(manifest_sha256=digest(pool/'manifest.json'),threshold=.5,
        hyperparameters=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0),
        recipes={'speed_and_tracking':{'features':['fixed']}}))
    old={'metrics':{'confusion':dict(true_positive=1,false_negative=0,false_positive=0,true_negative=1),'abstentions':0}}
    put(base/'comparison.json',dict(protocol_sha256=digest(base/'protocol.json'),inputs_sha256=digest(base/'inputs.json'),models={'speed_and_tracking':old}))
    put(analysis/'summary.json',dict(feature_version=FEATURE_VERSION,jobs=jobs,counts={'error':0}))
    monkeypatch.setattr(module,'verify_live',lambda *args:None)
    monkeypatch.setattr(module,'extract_case',lambda case,directory:dict(windows=[case['case_id']]))
    monkeypatch.setattr(module,'case_features',lambda windows,rate:([1,2],{'eligible_windows':5}) if windows==['C1'] else (None,{'eligible_windows':0}))
    result=compare(pool,analysis,base,tmp_path/'out')
    assert result['models']['legacy_speed_and_tracking']==old
    new=result['models']['v06_speed_and_tracking']
    assert new['metrics']['abstentions']==2 # one class/group cannot fit; missing evidence also abstains
    inputs=json.loads((tmp_path/'out/inputs.json').read_text())
    assert inputs['cases'][0]['features']==[10,20,1,2]
    assert inputs['cases'][1]['features'] is None
    assert inputs['groups']==groups
