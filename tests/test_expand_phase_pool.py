import json
import pytest
from aimguard.baseline import digest
from aimguard import expand_phase_pool as module


def test_expansion_uses_development_only_and_preserves_original_artifacts(tmp_path,monkeypatch):
    base=tmp_path/'base';cohorts=tmp_path/'cohorts';analysis=tmp_path/'analysis';oldanalysis=tmp_path/'oldanalysis'
    for p in (base,cohorts,analysis,oldanalysis):p.mkdir()
    def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v))
    directory=oldanalysis/'job_0001';put(directory/'report.json',{})
    put(base/'tracking/case_0001.json',{})
    rows=[dict(case_id='old',label='legitimate',features=[1,2,3,4],report_sha256=digest(directory/'report.json'),tracking_sha256=digest(base/'tracking/case_0001.json'))]
    groups={'0':['old']};put(base/'inputs.json',dict(cases=rows,groups=groups))
    put(base/'protocol.json',dict(role='inspected_v06_development',feature_version='0.6.0',phase_policy='explicit-server-phase-v1',threshold=.5,hyperparameters=dict(C=1,class_weight='balanced',solver='lbfgs',max_iter=1000,random_state=0),recipe={},dependencies={},groups=groups))
    put(base/'comparison.json',dict(inputs_sha256=digest(base/'inputs.json'),protocol_sha256=digest(base/'protocol.json'),models={'v06_speed_and_tracking':{'metrics':{'confusion':dict(true_positive=0,false_negative=0,false_positive=0,true_negative=1),'abstentions':0}}}))
    new=[dict(case_id='N-001',steamid='1',demo_sha256='x',label='cheating',partition='development',participants=['1'])]
    hold=[dict(case_id='H-001',steamid='2',demo_sha256='y',label='legitimate',partition='holdout',participants=['2'])]
    put(cohorts/'development.json',dict(role='development',features_inspected=False,cases=new));put(cohorts/'holdout.json',dict(cases=hold))
    put(cohorts/'registration.json',dict(cases=new+hold,development_manifest_sha256=digest(cohorts/'development.json'),holdout_manifest_sha256=digest(cohorts/'holdout.json')))
    put(analysis/'summary.json',dict(feature_version='0.6.0',counts={'error':0},jobs=[dict(steamid='1',source_sha256='x')]))
    put(analysis/'job_0001/report.json',dict(steamid='1',source_sha256='x',assumed_tickrate_hz=64,engagement_count=5,data_quality={'phase_excluded_previously_active':{}}))
    seen=[]
    def extract(c,path):seen.append(c['case_id']);return dict(windows=[])
    monkeypatch.setattr(module,'extract_case',extract);monkeypatch.setattr(module,'verify_live',lambda *a:None)
    monkeypatch.setattr(module,'speed_features',lambda r:[1,2]);monkeypatch.setattr(module,'case_features',lambda *a:([3,4],dict(eligible_windows=5)))
    initial=digest(cohorts/'holdout.json');r=module.expand(base,oldanalysis,cohorts,analysis,tmp_path/'out')
    assert seen==['N-001'] and r['cases']==2 and digest(cohorts/'holdout.json')==initial
    assert (tmp_path/'out/tracking/case_0001.json').is_symlink()
    assert json.loads((cohorts/'development.json').read_text())['features_inspected'] is False
    inspected=json.loads((tmp_path/'out/new-development-inspected.json').read_text())
    assert inspected['features_inspected'] is True and all(c['features_inspected'] is True for c in inspected['cases'])
    registration=json.loads((cohorts/'registration.json').read_text());registration['cases'][1]['participants']=['1'];put(cohorts/'registration.json',registration)
    with pytest.raises(ValueError,match='overlap'):module.expand(base,oldanalysis,cohorts,analysis,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()
