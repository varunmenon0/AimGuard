import json
from pathlib import Path

import numpy as np
import pytest

from aimguard.baseline import (EXPECTED_CONFIGURATION, digest, evaluation_metrics,
                              freeze, model_score, report_features, evaluate)
from aimguard.gameplay import FEATURE_VERSION


def report(speed=10., acceleration=100.):
    return dict(feature_version=FEATURE_VERSION,configuration=EXPECTED_CONFIGURATION,
                engagements=[dict(movement_context=dict(near_shot=dict(p95_speed=speed,mean_accel=acceleration)))])


def frozen_fixture(tmp_path):
    root=tmp_path/'analysis'
    cases=[]
    for i,(label,speed) in enumerate([('legitimate',1.),('cheating',20.)],1):
        directory=root/f'job_{i:04d}'
        directory.mkdir(parents=True)
        value=dict(report(speed,speed*10),steamid=str(i),source_sha256=str(i)*64)
        (directory/'report.json').write_text(json.dumps(value))
        cases.append(dict(case=str(i),match_id=f'match-{i}',steamid=str(i),
                          demo_sha256=str(i)*64,study_label=label))
    manifest=tmp_path/'development.json'
    manifest.write_text(json.dumps(cases))
    model=tmp_path/'frozen'
    bundle=freeze(manifest,root,model)
    return model,bundle


def test_match_aggregation_and_empty_features_abstain():
    value=report()
    value['engagements']+=[dict(movement_context=dict(near_shot=dict(p95_speed=30.,mean_accel=None)))]
    features,counts=report_features(value)
    assert features==[20.,100.]
    assert counts==dict(p95_speed=2,mean_accel=1)
    value['engagements'][0]['movement_context']['near_shot']['mean_accel']=None
    with pytest.raises(ValueError,match='No eligible'):
        report_features(value)


def test_report_configuration_is_frozen():
    value=report()
    value['configuration']={**EXPECTED_CONFIGURATION,'near_shot_seconds':0.2}
    with pytest.raises(ValueError,match='configuration'):
        report_features(value)


def test_frozen_model_export_and_checksum(tmp_path):
    path,bundle=frozen_fixture(tmp_path)
    assert digest(path/'model.json')==(path/'model.sha256').read_text().strip()
    restored=json.loads((path/'model.json').read_text())
    assert model_score(restored,[1,10])<.5
    assert model_score(restored,[20,200])>.5
    assert bundle['threshold']==.5
    with pytest.raises(ValueError,match='Invalid match features'):
        model_score(bundle,[np.nan,1])


def test_evaluation_rejects_development_overlap_before_extraction(tmp_path,monkeypatch):
    path,bundle=frozen_fixture(tmp_path)
    reserved=tmp_path/'reserved.json'
    reserved.write_text(json.dumps(dict(cases=[dict(label='legitimate',steamid='1',
        match_id='new-match',demo_sha256='9'*64)])))
    reserved.with_suffix('.sha256').write_text(digest(reserved))
    def unexpected(*args,**kwargs):
        raise AssertionError('Reserved data accessed before split validation')
    monkeypatch.setattr('aimguard.baseline.analyze_demo',unexpected)
    with pytest.raises(ValueError,match='development-overlapping'):
        evaluate(path,reserved,tmp_path/'evaluation')
    assert not (tmp_path/'evaluation').exists()


def test_evaluation_rejects_tampered_model(tmp_path):
    path,bundle=frozen_fixture(tmp_path)
    (path/'model.json').write_text('{}')
    with pytest.raises(ValueError,match='checksum mismatch'):
        evaluate(path,tmp_path/'unused.json',tmp_path/'evaluation')


def test_metrics_show_abstentions_and_small_sample_intervals():
    rows=[dict(status='scored',label='cheating',flagged=True),
          dict(status='scored',label='legitimate',flagged=False),
          dict(status='abstained',label='cheating')]
    result=evaluation_metrics(rows)
    assert result['confusion']==dict(true_positive=1,false_positive=0,true_negative=1,false_negative=0)
    assert result['abstentions']==1
    assert result['abstentions_by_label']['cheating']==1
    assert result['detection_rate']['denominator']==1
    assert result['false_positive_rate']['exact_95_interval'][1]>.9
    empty=evaluation_metrics([])
    assert empty['accuracy']['value'] is None
