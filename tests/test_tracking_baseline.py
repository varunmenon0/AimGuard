import json
import platform
from pathlib import Path
import importlib.metadata

import numpy as np
import pandas as pd
import pytest

import aimguard.tracking_baseline as module
from aimguard.baseline import digest


def save_bundle(path,bundle):
    path.mkdir(exist_ok=True)
    (path/'model.json').write_text(json.dumps(bundle))
    (path/'model.sha256').write_text(digest(path/'model.json'))


@pytest.fixture
def model(tmp_path):
    directory=tmp_path/'frozen'
    bundle=dict(schema_version=1,model_kind='speed_and_pre_shot_tracking',python_version=platform.python_version(),
        feature_names=module.FEATURES,feature_version=module.FEATURE_VERSION,threshold=.5,
        configuration=module.EXPECTED_CONFIGURATION,assumed_tickrate_hz=64.,pre_seconds=module.PRE_SECONDS,
        minimum_intervals=module.MIN_INTERVALS,minimum_windows=module.MIN_WINDOWS,
        hyperparameters=module.HYPERPARAMETERS,scaler_mean=[0.]*4,scaler_scale=[1.]*4,
        coefficients=[1.]*4,intercept=-1.,excluded_participants=['10','11'],
        development=[dict(steamid='10',match_id='dev',demo_sha256='development-hash')],additional_inspected_demos=[],
        code_sha256={name:digest(Path(module.__file__).with_name(name)) for name in module.SOURCE_FILES},
        dependencies={name:importlib.metadata.version(name) for name in module.DEPENDENCIES})
    save_bundle(directory,bundle)
    return directory,bundle


def candidate(tmp_path,target='20',match='fresh'):
    demo=tmp_path/f'{match}.dem';demo.write_bytes(match.encode())
    labels=tmp_path/f'{match}.csv';labels.write_text('source labels fixture')
    return dict(steamid=target,match_id=match,label='cheating',features_inspected=False,
        demo=str(demo),demo_sha256=digest(demo),source_label_file=str(labels),source_label_sha256=digest(labels))


def reserve_fixture(tmp_path,model,monkeypatch):
    directory,bundle=model
    case=candidate(tmp_path)
    monkeypatch.setattr(module,'participant_ids',lambda _:['20','21'])
    candidates=tmp_path/'candidates.json'
    candidates.write_text(json.dumps(dict(role='evaluation_candidates',features_inspected=False,cases=[case])))
    reserved=tmp_path/'reserved.json'
    module.reserve(directory,candidates,reserved)
    return directory,reserved,case


def test_export_score_matches_known_four_feature_logistic_formula(model):
    directory,bundle=model
    assert module.load_model(directory)==bundle
    values=[1,2,3,4]
    expected=1/(1+np.exp(-(-1+np.log1p(values).sum())))
    assert module.score(bundle,values)==pytest.approx(expected,abs=1e-12)
    with pytest.raises(ValueError,match='Four finite'):
        module.score(bundle,[1,2,np.nan,4])


@pytest.mark.parametrize('change,expected',[
    ('checksum','checksum'),('code','Frozen code changed'),('dependency','Frozen dependency changed'),('threshold','protocol differs')])
def test_frozen_runtime_and_configuration_changes_fail_before_feature_access(model,change,expected):
    directory,bundle=model
    if change=='checksum':
        (directory/'model.json').write_text('{}')
    else:
        if change=='code':bundle['code_sha256']['gameplay.py']='0'*64
        elif change=='dependency':bundle['dependencies']['numpy']='unknown-version'
        else:bundle['threshold']=.4
        save_bundle(directory,bundle)
    with pytest.raises(ValueError,match=expected):module.load_model(directory)


def test_reservation_rejects_any_development_participant_not_only_target(tmp_path,model,monkeypatch):
    directory,bundle=model
    case=candidate(tmp_path)
    monkeypatch.setattr(module,'participant_ids',lambda _:['20','11'])
    with pytest.raises(ValueError,match='participant overlaps'):
        module.validate_candidates(bundle,[case])


def test_reservation_rejects_shared_evaluation_participant(tmp_path,model,monkeypatch):
    _,bundle=model
    a=candidate(tmp_path,'20','one');b=candidate(tmp_path,'30','two')
    monkeypatch.setattr(module,'participant_ids',lambda demo:['20','99'] if 'one' in str(demo) else ['30','99'])
    with pytest.raises(ValueError,match='share participants'):
        module.validate_candidates(bundle,[a,b])


def test_reservation_rejects_inspected_flags_and_label_source_changes(tmp_path,model,monkeypatch):
    _,bundle=model;case=candidate(tmp_path)
    with pytest.raises(ValueError,match='uninspected status'):
        module.validate_candidates(bundle,[dict(case,features_inspected=True)])
    Path(case['source_label_file']).write_text('changed labels')
    with pytest.raises(ValueError,match='checksum mismatch'):
        module.validate_candidates(bundle,[case])


def test_metadata_reservation_cannot_be_recreated_under_another_name(tmp_path,model,monkeypatch):
    directory,reserved,case=reserve_fixture(tmp_path,model,monkeypatch)
    source=tmp_path/'candidates.json'
    with pytest.raises(ValueError,match='previously inspected'):
        module.reserve(directory,source,tmp_path/'another-reservation.json')
    assert not (tmp_path/'another-reservation.json').exists()
    assert not (directory/'reservations'/'.lock').exists()
    assert digest(reserved)==reserved.with_suffix('.sha256').read_text().strip()


def test_evaluation_records_receipts_before_extraction_and_consumes_failures(tmp_path,model,monkeypatch):
    directory,reserved,case=reserve_fixture(tmp_path,model,monkeypatch)
    output=tmp_path/'evaluation'
    def failed(*args,**kwargs):
        assert (output/'start-receipt.json').exists()
        assert reserved.with_suffix('.started.json').exists()
        assert (directory/'reservations'/f'{digest(reserved)}.started.json').exists()
        raise RuntimeError('broken demo fixture')
    monkeypatch.setattr(module,'analyze_demo',failed)
    result=module.evaluate(directory,reserved,output)
    assert result['metrics']['abstentions']==1
    assert result['metrics']['scored']==0
    with pytest.raises(ValueError,match='already started'):
        module.evaluate(directory,reserved,tmp_path/'second-run')
    assert not (tmp_path/'second-run').exists()


def test_copying_consumed_manifest_does_not_make_it_fresh(tmp_path,model,monkeypatch):
    directory,reserved,case=reserve_fixture(tmp_path,model,monkeypatch)
    monkeypatch.setattr(module,'analyze_demo',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('fixture')))
    module.evaluate(directory,reserved,tmp_path/'evaluation')
    copied=tmp_path/'copied.json';copied.write_bytes(reserved.read_bytes())
    copied.with_suffix('.sha256').write_text(digest(copied))
    with pytest.raises(ValueError,match='already started'):
        module.evaluate(directory,copied,tmp_path/'copied-run')
    assert not (tmp_path/'copied-run').exists()


def test_interrupt_leaves_reservation_consumed(tmp_path,model,monkeypatch):
    directory,reserved,case=reserve_fixture(tmp_path,model,monkeypatch)
    def interrupt(*a,**k):raise KeyboardInterrupt()
    monkeypatch.setattr(module,'analyze_demo',interrupt)
    with pytest.raises(KeyboardInterrupt):module.evaluate(directory,reserved,tmp_path/'interrupted')
    with pytest.raises(ValueError,match='already started'):
        module.evaluate(directory,reserved,tmp_path/'retry')


def test_evaluation_rechecks_participants_and_sources_before_consumption(tmp_path,model,monkeypatch):
    directory,reserved,case=reserve_fixture(tmp_path,model,monkeypatch)
    monkeypatch.setattr(module,'participant_ids',lambda _:['20','11'])
    with pytest.raises(ValueError,match='participant overlaps'):
        module.evaluate(directory,reserved,tmp_path/'blocked')
    assert not reserved.with_suffix('.started.json').exists()
    assert not (tmp_path/'blocked').exists()


def test_scored_pipeline_uses_frozen_features_and_threshold_without_refitting(tmp_path,model,monkeypatch):
    directory,reserved,case=reserve_fixture(tmp_path,model,monkeypatch)
    def analyzed(demo,steamid,output,**settings):
        assert settings['tickrate']==64 and settings['weapon_mode']=='firearms'
        output.mkdir()
        report=dict(feature_version=module.FEATURE_VERSION,configuration=module.EXPECTED_CONFIGURATION,
            engagements=[dict(movement_context=dict(near_shot=dict(p95_speed=1.,mean_accel=10.)))],
            engagement_count=1,data_quality=dict(round_event_anomalies=[]))
        (output/'report.json').write_text(json.dumps(report))
        pd.DataFrame([dict(tick=1,steamid=steamid)]).to_csv(output/'telemetry.csv',index=False)
        (output/'events.json').write_text('[]')
        return report
    monkeypatch.setattr(module,'analyze_demo',analyzed)
    monkeypatch.setattr(module,'validate_windows',lambda *a:[])
    monkeypatch.setattr(module,'extract_case',lambda *a:dict(windows=[]))
    monkeypatch.setattr(module,'case_features',lambda *a:([2.,3.],dict(eligible_windows=5)))
    monkeypatch.setattr(module.LogisticRegression,'fit',lambda *a,**k:pytest.fail('Evaluation must not fit'))
    result=module.evaluate(directory,reserved,tmp_path/'evaluation')
    row=result['predictions'][0]
    assert row['status']=='scored' and row['features']==dict(zip(module.FEATURES,[1.,10.,2.,3.]))
    assert row['baseline_score']==module.score(model[1],[1.,10.,2.,3.])
    assert row['flagged']==(row['baseline_score']>=.5)
    assert result['metrics']['detection_rate']['exact_95_interval'] is not None


def test_identity_stream_covers_empty_info_and_disconnected_players(monkeypatch):
    import demoparser2
    class Parser:
        def __init__(self,*args):pass
        def parse_player_info(self):return pd.DataFrame({'steamid':pd.Series([],dtype='uint64')})
        def parse_ticks(self,properties):
            assert properties==[]
            return pd.DataFrame({'steamid':pd.Series([76561199000000001,76561199000000002,0],dtype='uint64')})
    monkeypatch.setattr(demoparser2,'DemoParser',Parser)
    assert module.participant_ids('fixture.dem')==['76561199000000001','76561199000000002']


def test_freeze_fits_and_exports_verified_development_features(tmp_path,monkeypatch):
    analysis=tmp_path/'analysis';tracking=tmp_path/'tracking';comparison=tmp_path/'comparison'
    tracking.mkdir();comparison.mkdir();cases=[];prior=[];source_cases=[];records={}
    for index,(label,values) in enumerate([('legitimate',[1.,2.]),('cheating',[10.,20.])],1):
        case_id=f'D{index}';steamid=str(index*10);directory=analysis/f'job_{index:04d}';directory.mkdir(parents=True)
        case=dict(case_id=case_id,steamid=steamid,match_id=case_id,label=label,demo=f'{case_id}.dem',demo_sha256=case_id)
        report=dict(feature_version=module.FEATURE_VERSION,configuration=module.EXPECTED_CONFIGURATION,assumed_tickrate_hz=64.,
            engagements=[dict(movement_context=dict(near_shot=dict(p95_speed=values[0],mean_accel=values[1])))])
        (directory/'report.json').write_text(json.dumps(report))
        record=dict(windows=[dict(values=values)],assumed_tickrate_hz=64.)
        path=tracking/f'case_{index:04d}.json';path.write_text(json.dumps(record));records[case_id]=record
        cases.append(case);prior.append(dict(case_id=case_id,tracking_sha256=digest(path),features=values,eligible_windows=5))
        source_cases.append(dict(case_id=case_id,report_sha256=digest(directory/'report.json')))
    manifest=tmp_path/'development.json';manifest.write_text(json.dumps(dict(role='development',cases=cases)))
    protocol=dict(manifest_sha256=digest(manifest),recipes=dict(speed_and_tracking=module.TRACKING_RECIPES['speed_and_tracking']),
        threshold=.5,pre_seconds=module.PRE_SECONDS,minimum_contiguous_intervals=module.MIN_INTERVALS,
        minimum_eligible_windows=module.MIN_WINDOWS,hyperparameters=module.HYPERPARAMETERS,
        dependencies={name:importlib.metadata.version(name) for name in module.DEPENDENCIES},
        source_code_sha256={name:digest(Path(module.__file__).with_name(name)) for name in module.SOURCE_FILES})
    (comparison/'protocol.json').write_text(json.dumps(protocol))
    (comparison/'inputs.json').write_text(json.dumps(dict(tracking=prior,cases=source_cases)))
    (comparison/'comparison.json').write_text(json.dumps(dict(protocol_sha256=digest(comparison/'protocol.json'),inputs_sha256=digest(comparison/'inputs.json'))))
    monkeypatch.setattr(module,'extract_case',lambda case,*args:records[case['case_id']])
    monkeypatch.setattr(module,'case_features',lambda windows,*args:(windows[0]['values'],dict(eligible_windows=5)))
    monkeypatch.setattr(module,'participant_ids',lambda demo:['10','11'] if 'D1' in str(demo) else ['20','21'])
    output=tmp_path/'frozen';bundle=module.freeze(manifest,analysis,tracking,comparison,output)
    restored=module.load_model(output)
    assert restored==bundle
    assert module.score(bundle,[1,2,1,2])<.5<module.score(bundle,[10,20,10,20])
    assert bundle['excluded_participants']==['10','11','20','21']
    assert json.loads((output/'extraction-equivalence.json').read_text())['cases'][0]['full_record_equal']
