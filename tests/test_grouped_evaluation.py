import json
from pathlib import Path

import pandas as pd
import pytest

from aimguard import evaluation_cohorts as cohorts, grouped_evaluation as module
from aimguard.baseline import digest, write_json
from scripts.acquire_cheating_cohort import select_labels
from scripts.audit_replay_identities import PUBLIC_INDIVIDUAL_DESKTOP


def test_positive_acquisition_uses_one_explicit_unique_cheating_label():
    a,b=[str(PUBLIC_INDIVIDUAL_DESKTOP+n) for n in (100,1000)]
    rows=[dict(match_id='m',steamid=a,isCheater='0'),dict(match_id='m',steamid=b,isCheater='1')]
    assert [r['exact_steamid'] for r in select_labels(rows,[a,b],8)]==[b]
    assert select_labels(rows,[a],8)==[]
    assert select_labels(rows,[a,b],0)==[]


def test_mixed_labels_share_a_group_without_classifying_teammates(tmp_path,monkeypatch):
    import demoparser2
    a,b=[str(PUBLIC_INDIVIDUAL_DESKTOP+n) for n in (100,1000)]
    demo=tmp_path/'a.dem';demo.write_bytes(b'demo');labels=tmp_path/'labels.csv'
    labels.write_text(f'steamid,match_id,isCheater\n{a},m,0\n{b},m,1\n')
    class Parser:
        def parse_player_info(self):return pd.DataFrame(dict(steamid=[a,b,'11']))
        def parse_ticks(self,props):return pd.DataFrame({cohorts.CONTROLLER_ID:[a,b],'steamid':[a,b]})
        def parse_event(self,name):return pd.DataFrame(dict(isbot=[True]))
    monkeypatch.setattr(demoparser2,'DemoParser',lambda *a:Parser())
    cases=[dict(case_id=str(i),group_id='G',match_id='m',demo=str(demo),demo_sha256=digest(demo),
        participants=sorted([a,b,'11']),account_participants=sorted([a,b]),local_non_account_ids=['11'],
        features_inspected=False,label=label,steamid=steamid,source_player_id=steamid,
        source_label_file=str(labels),source_label_sha256=digest(labels))
        for i,(steamid,label) in enumerate([(a,'legitimate'),(b,'cheating')])]
    groups=[dict(group_id='G',match_id='m',case_ids=['0','1'],account_participants=sorted([a,b]))]
    cohorts.validate(cases,groups,set())
    with pytest.raises(ValueError,match='overlap'):cohorts.validate(cases,groups,{a})
    bad=[dict(cases[0],label='cheating'),cases[1]]
    with pytest.raises(ValueError,match='source label'):cohorts.validate(bad,groups,set())


def test_group_summary_ignores_positive_flags_for_legitimate_group_fpr_and_keeps_errors():
    rows=[dict(group_id='G',label='legitimate',status='not_flagged',flagged=False) for _ in range(2)]
    rows.append(dict(group_id='G',label='cheating',status='flag_for_review',flagged=True))
    s=module.summary(rows)
    assert s['legitimate_scored']==2 and s['false_flags']==0 and s['cheating_flagged']==1
    assert s['legitimate_match_groups']==1 and s['legitimate_groups_with_flags']==0
    assert s['conditional_one_sided_95_upper_group_flag_rate']==pytest.approx(.95)
    rows[0].update(status='error',flagged=None)
    s=module.summary(rows)
    assert s['unresolved']==1 and s['legitimate_groups_unresolved']==1
    assert s['legitimate_groups_fully_scored']==0 and s['conditional_one_sided_95_upper_group_flag_rate'] is None


def fixture(tmp_path,monkeypatch):
    model=tmp_path/'model';model.mkdir();(model/'model.json').write_text('{}')
    cases=[dict(case_id='N',group_id='G',demo_sha256='demo1',demo='one',steamid='1',label='legitimate'),
           dict(case_id='P',group_id='G',demo_sha256='demo1',demo='one',steamid='2',label='cheating')]
    collection=tmp_path/'collection.json'
    write_json(collection,dict(role=cohorts.ROLE,features_inspected=False,model_sha256=digest(model/'model.json'),
        threshold=.75,preparation_code_sha256=digest('aimguard/evaluation_cohorts.py'),source_sha256={},
        cases=cases,groups=[dict(group_id='G',account_participants=['1','2'])]))
    monkeypatch.setattr(module,'load',lambda *a:dict(threshold=.75))
    monkeypatch.setattr(module,'prior_accounts',lambda *a:set())
    monkeypatch.setattr(module,'validate',lambda *a:None)
    return model,collection,tmp_path/'registry'


def test_replay_reservation_blocks_changed_positive_subsets_before_scoring(tmp_path,monkeypatch):
    model,collection,registry=fixture(tmp_path,monkeypatch)
    module.reserve(model,collection,tmp_path/'reservation',registry)
    m=json.loads(collection.read_text());m['cases']=m['cases'][:1];collection.write_text(json.dumps(m))
    with pytest.raises(ValueError,match='Replay already reserved'):
        module.reserve(model,collection,tmp_path/'different',registry)
    assert not (tmp_path/'different').exists()


def test_grouped_consumption_precedes_unlabeled_scoring_and_survives_errors_and_copies(tmp_path,monkeypatch):
    model,collection,registry=fixture(tmp_path,monkeypatch)
    record=module.reserve(model,collection,tmp_path/'reservation',registry)
    consumed=registry/'cohorts'/record['cohort_key']/'consumed.json';calls=[]
    def predict(m,d,s,o):
        assert consumed.exists();calls.append(s)
        if s=='1':raise ValueError('extraction failed')
        return dict(status='flag_for_review',score=.9,flagged=True)
    monkeypatch.setattr(module,'predict',predict)
    r=module.evaluate(model,tmp_path/'reservation/reservation.json',tmp_path/'evaluation')
    assert calls==['1','2'] and r['summary']['unresolved']==1 and r['summary']['cheating_flagged']==1
    copy=tmp_path/'renamed.json';copy.write_bytes((tmp_path/'reservation/reservation.json').read_bytes())
    with pytest.raises(ValueError,match='consumed'):module.evaluate(model,copy,tmp_path/'repeat')
    assert not (tmp_path/'repeat').exists()


def test_changed_bound_source_fails_before_consumption_or_extraction(tmp_path,monkeypatch):
    model,collection,registry=fixture(tmp_path,monkeypatch)
    source=tmp_path/'source.json';source.write_text('metadata')
    manifest=json.loads(collection.read_text());manifest['source_sha256']={str(source):digest(source)}
    collection.write_text(json.dumps(manifest))
    record=module.reserve(model,collection,tmp_path/'reservation',registry)
    source.write_text('changed metadata')
    monkeypatch.setattr(module,'predict',lambda *a:pytest.fail('Source mismatch reached scoring'))
    with pytest.raises(ValueError,match='source changed'):
        module.evaluate(model,tmp_path/'reservation/reservation.json',tmp_path/'evaluation')
    assert not (registry/'cohorts'/record['cohort_key']/'consumed.json').exists()
    assert not (tmp_path/'evaluation').exists()
