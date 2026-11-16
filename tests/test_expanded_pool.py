import json
from pathlib import Path
import pytest
from aimguard.baseline import digest
import scripts.prepare_expanded_development as module


def sources(tmp_path,monkeypatch,duplicate=False):
    model=tmp_path/'model';model.mkdir();(model/'model.json').write_text('fixture')
    analysis=tmp_path/'analysis';directory=analysis/'job_0001';directory.mkdir(parents=True)
    tracking=tmp_path/'tracking';tracking.mkdir();evaluation=tmp_path/'evaluation';evaluation.mkdir()
    original=dict(case_id='D1',steamid='1',match_id='old',label='legitimate',demo_sha256='oldhash')
    (directory/'report.json').write_text(json.dumps(dict(steamid='1',source_sha256='oldhash')))
    original_track=tracking/'case_0001.json';original_track.write_text(json.dumps(dict(summary=dict(case_id='D1',label='legitimate'))))
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps(dict(role='development',cases=[original])))
    new=dict(case_id='R1',steamid='1' if duplicate else '3',match_id='new',label='cheating',demo_sha256='newhash',participants=['3','4'])
    newdir=evaluation/'case_001';newdir.mkdir()
    (newdir/'report.json').write_text(json.dumps(dict(steamid=new['steamid'],source_sha256='newhash')))
    (newdir/'tracking.json').write_text(json.dumps(dict(summary=dict(case_id='R1',label='cheating'))))
    reserved=tmp_path/'reserved.json';reserved.write_text(json.dumps(dict(cases=[new])))
    row=dict(new,status='scored',report_sha256=digest(newdir/'report.json'),tracking_sha256=digest(newdir/'tracking.json'))
    (evaluation/'evaluation.json').write_text(json.dumps(dict(model_sha256=digest(model/'model.json'),reserved_manifest_sha256=digest(reserved),predictions=[row])))
    bundle=dict(development_manifest_sha256=digest(manifest),development=[dict(original,participants=['1','2'],report_sha256=digest(directory/'report.json'),tracking_sha256=digest(original_track))])
    monkeypatch.setattr(module,'load_model',lambda _:bundle)
    return model,manifest,analysis,tracking,reserved,evaluation


def test_inspected_pool_is_explicitly_development_and_preserves_source_artifacts(tmp_path,monkeypatch):
    args=sources(tmp_path,monkeypatch);output=tmp_path/'pool'
    before=digest(args[2]/'job_0001'/'report.json')
    assert module.prepare(*args,output)==(2,2)
    manifest=json.loads((output/'manifest.json').read_text())
    assert manifest['role']=='development' and manifest['features_inspected'] and not manifest['fresh_holdout']
    assert all(case['role']=='development' and case['features_inspected'] for case in manifest['cases'])
    assert (output/'analysis'/'job_0001').is_symlink()
    assert digest(args[2]/'job_0001'/'report.json')==before
    assert (output/'analysis'/'job_0002'/'tracking.json').exists()


def test_pool_rejects_duplicate_targets_before_writing(tmp_path,monkeypatch):
    args=sources(tmp_path,monkeypatch,duplicate=True);output=tmp_path/'pool'
    with pytest.raises(ValueError,match='Duplicate development steamid'):
        module.prepare(*args,output)
    assert not output.exists()


def test_pool_rejects_changed_source_checksums_before_writing(tmp_path,monkeypatch):
    args=sources(tmp_path,monkeypatch);output=tmp_path/'pool'
    (args[2]/'job_0001'/'report.json').write_text('{}')
    with pytest.raises(ValueError,match='checksum mismatch'):module.prepare(*args,output)
    assert not output.exists()


def test_additional_sources_cannot_be_partial_or_claim_uninspected_data(tmp_path,monkeypatch):
    args=sources(tmp_path,monkeypatch);output=tmp_path/'pool'
    with pytest.raises(ValueError,match='manifest, analysis and tracking together'):
        module.prepare(*args,output,additional_manifest=tmp_path/'extra.json')
    assert not output.exists()
    extra=tmp_path/'extra.json';extra.write_text(json.dumps(dict(role='development_candidates',features_inspected=False,cases=[])))
    with pytest.raises(ValueError,match='explicitly inspected development'):
        module.prepare(*args,output,extra,tmp_path,tmp_path)
    assert not output.exists()
