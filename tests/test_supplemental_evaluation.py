import json
from pathlib import Path

import pandas as pd
import pytest

from aimguard import supplemental_evaluation as module
from aimguard.baseline import digest, write_json
from scripts.audit_replay_identities import PUBLIC_INDIVIDUAL_DESKTOP


def reserved(tmp_path, monkeypatch):
    model = tmp_path/'model'; model.mkdir(); (model/'model.json').write_text('{}')
    cases = [dict(case_id='I1', demo_sha256='demo1', steamid='1', demo='one', label='legitimate'),
             dict(case_id='I2', demo_sha256='demo2', steamid='2', demo='two', label='cheating')]
    key = module.cohort_key(cases); registry = tmp_path/'registry'; (registry/key).mkdir(parents=True)
    source = tmp_path/'source'; source.write_text('metadata')
    record = dict(role=module.ROLE, model_sha256=digest(model/'model.json'), threshold=.75,
        cases=cases, cohort_key=key, registry=str(registry), source_sha256={str(source):digest(source)},
        runtime_sha256={}, excluded_account_participants=[])
    canonical = registry/key/'reservation.json'; write_json(canonical, record)
    copy = tmp_path/'reservation.json'; copy.write_bytes(canonical.read_bytes())
    monkeypatch.setattr(module, 'load', lambda p:dict(threshold=.75))
    monkeypatch.setattr(module, 'validate_cases', lambda *args:None)
    return model, copy, registry/key, source


def test_consumption_precedes_extraction_and_errors_continue_with_copied_reuse_blocked(tmp_path, monkeypatch):
    model, reservation, registry, _ = reserved(tmp_path, monkeypatch)
    calls = []
    def predict(m, demo, steamid, output):
        assert (registry/'consumed.json').exists()
        calls.append(steamid)
        if steamid == '1':
            raise ValueError('extraction failed')
        return dict(status='flag_for_review', score=.9, flagged=True)
    monkeypatch.setattr(module, 'predict', predict)
    result = module.evaluate(model, reservation, tmp_path/'evaluation')
    assert calls == ['1', '2']
    assert result['summary']['unresolved'] == 1
    assert result['summary']['legitimate_scored'] == 0
    assert result['summary']['cheating_flagged'] == 1
    copied = tmp_path/'renamed.json'; copied.write_bytes(reservation.read_bytes())
    with pytest.raises(ValueError, match='consumed'):
        module.evaluate(model, copied, tmp_path/'second-output')
    assert not (tmp_path/'second-output').exists()


def test_changed_sources_or_noncanonical_reservation_fail_before_consumption(tmp_path, monkeypatch):
    model, reservation, registry, source = reserved(tmp_path, monkeypatch)
    source.write_text('changed')
    with pytest.raises(ValueError, match='source/runtime'):
        module.evaluate(model, reservation, tmp_path/'out')
    assert not (registry/'consumed.json').exists()
    source.write_text('metadata')
    record = json.loads(reservation.read_text()); record['cases'][0]['label'] = 'cheating'
    reservation.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='canonical'):
        module.evaluate(model, reservation, tmp_path/'out')
    assert not (registry/'consumed.json').exists()


def test_cohort_key_survives_reordering_and_model_or_path_changes():
    a = dict(demo_sha256='a', steamid='1', label='legitimate', demo='original')
    b = dict(demo_sha256='b', steamid='2')
    assert module.cohort_key([a,b]) == module.cohort_key([b,dict(a,demo='copied',label='cheating')])
    assert module.cohort_key([a,b]) != module.cohort_key([a])


def test_case_validation_retains_full_identity_overlap_and_checks_source_label(tmp_path, monkeypatch):
    import demoparser2
    human = str(PUBLIC_INDIVIDUAL_DESKTOP + 100)
    replacement = str(PUBLIC_INDIVIDUAL_DESKTOP + 1000)
    demo = tmp_path/'replay.dem'; demo.write_bytes(b'demo')
    labels = tmp_path/'labels.csv'
    labels.write_text(f'steamid,match_id,isCheater\n{human},match,0\n')
    class Parser:
        def parse_player_info(self):
            return pd.DataFrame(dict(steamid=[human,'11']))
        def parse_ticks(self, fields):
            return pd.DataFrame({module.CONTROLLER_ID:[human,replacement], 'steamid':[human,replacement]})
        def parse_event(self, name):
            return pd.DataFrame(dict(isbot=[True]))
    monkeypatch.setattr(demoparser2, 'DemoParser', lambda *a:Parser())
    case = dict(case_id='I1', features_inspected=False, label='legitimate', steamid=human,
        demo=str(demo),demo_sha256=digest(demo),match_id='match',source_player_id=human,
        source_label_file=str(labels),source_label_sha256=digest(labels),
        participants=sorted([human,replacement,'11']),account_participants=sorted([human,replacement]),local_non_account_ids=['11'])
    module.validate_cases({}, [case], set())
    with pytest.raises(ValueError, match='overlap'):
        module.validate_cases({}, [case], {replacement})
    with pytest.raises(ValueError, match='source label'):
        module.validate_cases({}, [dict(case,label='cheating')], set())
