import copy
import pytest
from scripts.prepare_metadata_cohorts import split_cases


def cases():
    return [dict(steamid=str(i),match_id=str(i),demo_sha256=str(i),participants=[str(i)],label=label,features_inspected=False) for i,label in enumerate(['cheating','legitimate','legitimate','cheating','legitimate'],1)]


def test_label_stratified_alternation_uses_source_order_without_mutation():
    original=cases();before=copy.deepcopy(original);dev,hold=split_cases(original)
    assert [c['steamid'] for c in dev]==['1','2','5']
    assert [c['steamid'] for c in hold]==['3','4']
    assert original==before
    assert all(c['features_inspected'] is False and c['partition']=='holdout' for c in hold)
    assert len({c['case_id'] for c in dev+hold})==5


def test_overlap_duplicate_or_inspected_candidates_rejected():
    for key in ('steamid','match_id','demo_sha256','participants'):
        c=cases();c[1][key]=c[0][key]
        with pytest.raises(ValueError):split_cases(c)
    c=cases();c[0]['features_inspected']=True
    with pytest.raises(ValueError):split_cases(c)
    c=cases();c[0]['label']='unknown'
    with pytest.raises(ValueError):split_cases(c)


def test_registration_excludes_both_partitions_without_scoring(tmp_path,monkeypatch):
    import json
    from scripts import prepare_metadata_cohorts as module
    from scripts.acquire_fresh_cases import recorded_exclusions
    from aimguard.baseline import digest
    model=tmp_path/'model';model.mkdir();(model/'reservations').mkdir();(model/'model.json').write_text('{}')
    manifest=tmp_path/'candidates.json';manifest.write_text(json.dumps(dict(role='evaluation_candidates',features_inspected=False,cases=cases())))
    monkeypatch.setattr(module,'load_model',lambda path:{})
    calls=[]
    def validate(bundle,selected,previous):calls.append((selected,previous));return selected
    monkeypatch.setattr(module,'validate_candidates',validate)
    before=digest(model/'model.json');dev,hold=module.prepare(model,manifest,tmp_path/'cohorts')
    assert len(calls)==1 and len(dev)+len(hold)==5 and digest(model/'model.json')==before
    held=json.loads((tmp_path/'cohorts/holdout.json').read_text())
    assert held['role']=='future_phase_evaluation_holdout' and held['features_inspected'] is False
    blocked,matches,receipts=recorded_exclusions(dict(excluded_participants=[],development=[]),model)
    assert blocked==set('12345') and matches==set('12345') and len(receipts)==1
    assert not (model/'reservations/.lock').exists()
    with pytest.raises(FileExistsError):module.prepare(model,manifest,tmp_path/'cohorts')
