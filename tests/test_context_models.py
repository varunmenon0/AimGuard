import numpy as np
import pytest
from aimguard.combat import FIREARMS
from aimguard.context_models import FAMILIES,family,fit_reference,case_vector,grouped_context,window_rows


def rows(value,n=5,group='rifle',state='multi'):
    return [dict(log_features=[float(value)]*4,family=group,state=state,context=group+':'+state) for _ in range(n)]


def test_family_map_covers_each_allowed_firearm_exactly_once():
    assert set.union(*FAMILIES.values())==FIREARMS
    assert sum(map(len,FAMILIES.values()))==len(FIREARMS)
    assert family('awp')=='sniper' and family('xm1014')=='shotgun'
    with pytest.raises(ValueError,match='Unknown'):family('unknown')


def test_legitimate_reference_weights_cases_not_long_demos_and_excludes_cheating_labels():
    reference=fit_reference([rows(1,100),rows(9,5),rows(1000,50)],[0,0,1])
    assert reference['global_center']==[5.]*4
    assert reference['contexts']['rifle:multi']['center']==[5.]*4
    assert reference['contexts']['rifle:multi']['cases']==2


def test_sparse_context_uses_family_then_global_without_test_fitting():
    reference=fit_reference([rows(1),rows(3)],[0,0])
    vector,fallback=case_vector(rows(10,state='single'),reference)
    assert vector.tolist()==[8.]*4 and fallback=={'family':5}
    vector,fallback=case_vector(rows(10,group='shotgun'),reference)
    assert vector.tolist()==[8.]*4 and fallback=={'global':5}


def test_extreme_held_out_cases_never_enter_reference_or_scaler():
    all_rows=[rows(10000),rows(20000),*map(rows,range(2,8))]
    result=grouped_context(all_rows,[0,1,0,1,0,1,0,1],[0,0,1,2,3,4,5,6],list('abcdefgh'),True)
    fold=next(f for f in result['folds'] if f['held_out_case_ids']==['a','b'])
    assert fold['reference']['global_center']==[4.]*4
    assert fold['scaler_mean']==pytest.approx([.5]*4)
    for fold in result['folds']:assert not set(fold['train_case_ids'])&set(fold['held_out_case_ids'])


def test_short_cases_abstain_and_never_enter_training():
    result=grouped_context([rows(1,4),*map(rows,range(2,8))],[0,1,0,1,0,1,0],list(range(7)),list('abcdefg'),True)
    assert result['metrics']['abstentions']==1 and result['metrics']['scored']==6
    assert result['predictions'][0]['status']=='abstained'
    assert all('a' not in f['train_case_ids'] for f in result['folds'])


def test_window_context_uses_grouped_shot_count_and_identical_joint_features():
    track=dict(engagement_id=0,weapon='ak47',shot_ticks=[20],nearest_before_first_shot='a',
        tracks=[dict(opponent_id='a',ticks=list(range(26)),segment_ids=[0]*26,
            signed_error_degrees=[2.]*26,yaw_rate_dps=[5.]*26,bearing_rate_dps=[2.]*26)])
    published=dict(engagement_id=0,weapon='ak47',shot_ticks=[20],shot_count=1,
        movement_context=dict(near_shot=dict(p95_speed=10.,mean_accel=100.)))
    values,excluded=window_rows(dict(assumed_tickrate_hz=64,engagements=[published]),dict(windows=[track]))
    assert excluded=={} and values[0]['context']=='rifle:single'
    assert values[0]['log_features']==pytest.approx(np.log1p([10,100,2,3]).tolist())
    published['shot_count']=2
    with pytest.raises(ValueError,match='shot count mismatch'):
        window_rows(dict(assumed_tickrate_hz=64,engagements=[published]),dict(windows=[track]))


def test_reference_requires_legitimate_training_and_labels_are_binary():
    with pytest.raises(ValueError,match='No legitimate'):fit_reference([rows(1)],[1])
    with pytest.raises(ValueError,match='binary'):grouped_context([rows(1),rows(2)],[0,2],[0,1],['a','b'],True)
