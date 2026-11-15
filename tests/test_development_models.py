import numpy as np
import pytest

from aimguard.development_models import grouped_predictions, participant_groups


def test_shared_participants_form_transitive_components():
    groups=participant_groups([{'1','2'},{'3','4'},{'2','3'},{'5'}])
    assert groups[0]==groups[1]==groups[2]
    assert groups[3]!=groups[0]
    with pytest.raises(ValueError,match='nonempty'):
        participant_groups([set()])


def test_scaling_uses_training_groups_and_predicts_each_case_once():
    values=np.array([[10000.],[20000.],[3.],[4.],[5.],[6.]])
    labels=np.array([0,1,0,1,0,1])
    groups=np.array([0,0,1,2,3,4])
    ids=list('abcdef')
    result=grouped_predictions(values,labels,groups,ids,'identity')
    first=next(f for f in result['folds'] if f['held_out_case_ids']==['a','b'])
    assert first['scaler_mean']==[4.5]
    for fold in result['folds']:
        assert not set(fold['train_case_ids']) & set(fold['held_out_case_ids'])
    assert sorted(p['case_id'] for p in result['predictions'])==ids
    assert result['metrics']['diagnostic_only']
    assert 'exact_95_interval' not in result['metrics']['accuracy']


def test_single_training_class_is_an_explicit_abstention():
    result=grouped_predictions(np.arange(4.).reshape(-1,1),[0,0,1,1],[0,0,1,1],list('abcd'),'identity')
    assert result['metrics']['abstentions']==4
    assert result['metrics']['scored']==0
    assert result['metrics']['detection_rate']['value'] is None


def test_single_connected_group_cannot_produce_cross_validation():
    with pytest.raises(ValueError,match='two independent participant groups'):
        grouped_predictions([[1.],[2.]],[0,1],[0,0],['a','b'],'identity')


def test_negative_values_are_rejected_for_speed_log_transform():
    with pytest.raises(ValueError,match='nonnegative'):
        grouped_predictions([[-1.],[2.]],[0,1],[0,1],['a','b'],'log1p')
