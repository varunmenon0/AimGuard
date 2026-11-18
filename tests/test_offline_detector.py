import copy
import importlib.metadata
import json
import platform
from pathlib import Path
import pytest
from aimguard import offline_detector as module
from aimguard.baseline import digest


def frozen(tmp_path):
    p=tmp_path/'model';p.mkdir()
    b=dict(model_kind='phase_clean_offline_review',schema_version=1,feature_version=module.FEATURE_VERSION,phase_policy=module.PHASE_POLICY,threshold=.75,feature_names=module.TRACKING_RECIPES['speed_and_tracking']['features'],configuration=module.EXPECTED_CONFIGURATION,hyperparameters=module.PARAMETERS,tickrate=64,python_version=platform.python_version(),code_sha256={n:digest(Path(module.__file__).with_name(n)) for n in module.CODE_FILES},dependencies={n:importlib.metadata.version(n) for n in module.DEPENDENCIES},scaler_mean=[0]*4,scaler_scale=[1]*4,coefficients=[0]*4,intercept=0)
    def save():
        (p/'model.json').write_text(json.dumps(b));(p/'model.sha256').write_text(digest(p/'model.json')+'\n')
    save();return p,b,save


def test_frozen_loader_rejects_recipe_source_and_dependency_changes(tmp_path):
    p,b,save=frozen(tmp_path);assert module.load(p)['threshold']==.75
    b['threshold']=.5;save()
    with pytest.raises(ValueError,match='recipe'):module.load(p)
    b['threshold']=.75;b['code_sha256']['offline_detector.py']='bad';save()
    with pytest.raises(ValueError,match='source changed'):module.load(p)
    b['code_sha256']['offline_detector.py']=digest(module.__file__);b['dependencies']['numpy']='wrong';save()
    with pytest.raises(ValueError,match='dependency'):module.load(p)


def test_holdout_consumed_before_extraction_and_cannot_repeat_even_after_error(tmp_path,monkeypatch):
    model=tmp_path/'model';model.mkdir();(model/'model.json').write_text('{}')
    hold=tmp_path/'holdout.json';hold.write_text(json.dumps(dict(cases=[dict(case_id='H1',label='legitimate',demo='one',steamid='1'),dict(case_id='H2',label='legitimate',demo='two',steamid='2')])))
    monkeypatch.setattr(module,'load',lambda p:dict(reserved_holdout_sha256=digest(hold)))
    monkeypatch.setattr(module,'validate_holdout',lambda *a:None);calls=[]
    def predict(m,d,s,o):
        assert hold.with_suffix('.consumed.json').exists();calls.append(s)
        if s=='1':raise ValueError('extraction failed')
        return dict(status='not_flagged',score=.1,flagged=False)
    monkeypatch.setattr(module,'predict',predict)
    r=module.evaluate_once(model,hold,tmp_path/'out')
    assert calls==['1','2'] and r['summary']['unresolved']==1 and r['summary']['legitimate_scored']==1
    with pytest.raises(ValueError,match='consumed'):module.evaluate_once(model,hold,tmp_path/'different')
    assert not (tmp_path/'different').exists()


def test_negative_only_summary_does_not_claim_detection_or_zero_population_risk():
    rows=[dict(status='not_flagged',flagged=False,label='legitimate') for _ in range(6)]
    r=module.summarize(rows)
    assert r['cheating_scored']==0 and r['false_flags']==0
    assert r['conditional_one_sided_95_upper_fpr']==pytest.approx(1-.05**(1/6))


def test_metadata_overlap_rejected_without_features(tmp_path,monkeypatch):
    demo=tmp_path/'a.dem';demo.write_bytes(b'a');labels=tmp_path/'labels';labels.write_text('source')
    case=dict(features_inspected=False,label='legitimate',steamid='1',demo=str(demo),demo_sha256=digest(demo),source_label_file=str(labels),source_label_sha256=digest(labels),participants=['1','2'])
    manifest=dict(role='future_phase_evaluation_holdout',features_inspected=False,fresh_holdout=True,cases=[case])
    monkeypatch.setattr(module,'participant_ids',lambda p:['1','2'])
    with pytest.raises(ValueError,match='overlap'):module.validate_holdout(dict(excluded_participants=['2'],training=[]),manifest)


def test_insufficient_evidence_remains_unresolved_and_unlabeled(tmp_path,monkeypatch):
    demo=tmp_path/'a.dem';demo.write_bytes(b'a');model=tmp_path/'model';model.mkdir();(model/'model.json').write_text('{}')
    monkeypatch.setattr(module,'load',lambda p:dict(tickrate=64))
    report=dict(source_sha256=digest(demo),engagement_count=0,data_quality=dict(round_event_anomalies=[]))
    def analyze(d,s,o,**kwargs):o.mkdir();(o/'report.json').write_text(json.dumps(report));return report
    monkeypatch.setattr(module,'analyze_demo',analyze);monkeypatch.setattr(module,'verify_live',lambda *a:None);monkeypatch.setattr(module,'speed_features',lambda r:None)
    def extract(case,directory):assert case['label']=='unlabeled';return dict(windows=[])
    monkeypatch.setattr(module,'extract_case',extract);monkeypatch.setattr(module,'case_features',lambda *a:(None,dict(eligible_windows=0)))
    r=module.predict(model,demo,'1',tmp_path/'prediction')
    assert r['status']=='insufficient_evidence' and r['flagged'] is None and r['score'] is None
    assert (tmp_path/'prediction/result.html').exists()
    with pytest.raises(ValueError,match='new output'):module.predict(model,demo,'1',tmp_path/'prediction')
