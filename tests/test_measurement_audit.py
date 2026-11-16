import numpy as np
import pandas as pd
import pytest
from aimguard.measurement_audit import origin_geometry,probe,select_windows,snapshot


def test_vertical_proxy_differs_from_horizontal_alignment_without_eye_assumptions():
    g=origin_geometry([0,0,0],[10,0,10],0,0)
    assert g['horizontal_error_degrees']==0
    assert g['origin_proxy_angular_error_degrees']==pytest.approx(45)
    assert g['origin_bearing_pitch_degrees']==pytest.approx(-45)
    assert 'proxy' in g['geometry_kind']
    assert origin_geometry([0,0,0],[10,0,10],0,-45)['origin_proxy_angular_error_degrees']==pytest.approx(0,abs=1e-6)


def test_vertical_direction_and_coincident_origins_are_not_invented_head_points():
    g=origin_geometry([0,0,0],[0,0,10],0,-90)
    assert g['horizontal_error_degrees'] is None
    assert g['origin_proxy_angular_error_degrees']==pytest.approx(0)
    assert origin_geometry([1,2,3],[1,2,3],0,0) is None
    with pytest.raises(ValueError):origin_geometry([0,0,np.nan],[1,2,3],0,0)


def row(player,x,y,z,team=3,state=0):
    return dict(tick=10,steamid=player,X=x,Y=y,Z=z,yaw=0.,pitch=0.,health=100,life_state=state,team_num=team)


def test_origin_proxy_rank_can_differ_from_horizontal_with_height_and_excludes_deaths():
    frame=pd.DataFrame([row('1',0,0,0,team=2),row('2',10,0,10),row('3',10,1,0),row('4',1,0,0,state=2)])
    result=snapshot(frame,'1',10,[])
    assert result['nearest_origin_proxy_candidate']=='3'
    assert {r['opponent_id'] for r in result['candidates']}=={'2','3'}
    assert result['eye_to_head_error_degrees'] is None and result['validated_visibility'] is None
    result=snapshot(frame,'1',10,[('3',10)])
    assert result['nearest_origin_proxy_candidate']=='2'


def test_omitted_probe_column_is_missing_not_zero_and_returned_zero_is_observed():
    class Parser:
        def parse_ticks(self,props,ticks):
            frame=pd.DataFrame(dict(tick=[1],steamid=pd.Series([76561199000000001],dtype='uint64')))
            if props[0]=='zero':frame['zero']=[[0.,0.,0.]]
            return frame
    missing,values=probe(Parser(),'missing',[1])
    assert missing['status']=='requested_column_omitted' and values is None
    zero,values=probe(Parser(),'zero',[1])
    assert zero['status']=='returned' and zero['nonnull']==1 and zero['nonzero_numeric_values']==0
    assert (1,'76561199000000001') in values


def test_window_sampling_separates_earlier_padding_damage_from_current_shooting():
    published=[dict(engagement_id=i,weapon='ak47',shot_ticks=[10]) for i in range(3)]
    windows=[dict(published[0],damage_events=[dict(tick=9)]),dict(published[1],damage_events=[dict(tick=10)]),dict(published[2],damage_events=[])]
    selected=select_windows(dict(engagements=published),dict(windows=windows),per_category=1)
    assert [(w[0]['engagement_id'],w[2]) for w in selected]==[(0,'no_damage_at_or_after_first_shot'),(1,'damage_at_or_after_first_shot')]


def test_missing_samples_and_death_latches_have_separate_reasons():
    frame=pd.DataFrame([row('1',0,0,0,team=2),row('2',10,0,0)])
    assert snapshot(frame,'1',9,[])['reason']=='missing_exact_shooter_sample'
    assert snapshot(frame,'1',10,[('1',10)])['reason']=='shooter_death_event_latched'


def test_audit_rejects_wrong_model_receipt_before_creating_output(tmp_path,monkeypatch):
    import json
    import aimguard.measurement_audit as module
    model=tmp_path/'model';model.mkdir();(model/'model.json').write_text('fixture')
    reserved=tmp_path/'reserved.json';reserved.write_text('{}')
    (tmp_path/'evaluation.json').write_text(json.dumps(dict(model_sha256='wrong',reserved_manifest_sha256='wrong')))
    monkeypatch.setattr(module,'load_model',lambda _:dict())
    output=tmp_path/'audit'
    with pytest.raises(ValueError,match='source receipts mismatch'):
        module.audit(model,reserved,tmp_path,output)
    assert not output.exists()
