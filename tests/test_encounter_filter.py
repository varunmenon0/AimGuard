import copy
import numpy as np
import pytest
from aimguard.baseline import FEATURE_VERSION,EXPECTED_CONFIGURATION
from aimguard.encounter_filter import exclusion_reason,filtered_features


def snapshots(error=1.,gap=10.,candidate='a'):
    return [dict(status='available',nearest=candidate,nearest_error=error,runner_up_gap=gap,
        candidates=[dict(opponent_id=candidate,error_degrees=error),dict(opponent_id='b',error_degrees=error+gap)]) for _ in range(3)]


def sources(rounds=(1,2,3,1,2,3),exclude=()):
    published=[];tracking=[];sampled=[]
    for i,round_id in enumerate(rounds):
        w=dict(engagement_id=i,round_id=round_id,shot_ticks=[20],weapon='ak47',start_tick=0,end_tick=30,
            movement_context=dict(near_shot=dict(p95_speed=10.,mean_accel=100.)))
        published.append(w)
        tracking.append(dict(engagement_id=i,round_id=round_id,shot_ticks=[20],weapon='ak47',nearest_before_first_shot='a',
            tracks=[dict(opponent_id='a',ticks=list(range(26)),segment_ids=[0]*26,signed_error_degrees=[2.]*26,
                yaw_rate_dps=[5.]*26,bearing_rate_dps=[2.]*26)]))
        sampled.append(dict(engagement_id=i,first_shot_tick=20,weapon='ak47',snapshots=snapshots(error=1 if i in exclude else 5)))
    report=dict(feature_version=FEATURE_VERSION,configuration=EXPECTED_CONFIGURATION,engagements=published,assumed_tickrate_hz=64)
    return report,dict(windows=tracking),sampled


def test_only_fully_observed_stable_separated_prealignment_is_excluded():
    assert exclusion_reason(snapshots())=='excluded_stable_sampled_pre_alignment'
    changed=snapshots();changed[1]['nearest']='b'
    assert exclusion_reason(changed)=='retained_alignment_changes'
    assert exclusion_reason(snapshots(error=3.01))=='retained_alignment_changes'
    assert exclusion_reason(snapshots(gap=2.99))=='retained_ambiguous_geometry'
    assert exclusion_reason(snapshots(error=3,gap=3))=='excluded_stable_sampled_pre_alignment'


def test_unknown_geometry_is_retained_and_single_candidate_is_distinct_from_tie():
    unknown=snapshots();unknown[1]=dict(status='unavailable')
    assert exclusion_reason(unknown)=='retained_unknown_context'
    tied=snapshots(gap=0)
    assert exclusion_reason(tied)=='retained_ambiguous_geometry'
    single=snapshots()
    for s in single:s['candidates']=s['candidates'][:1];s['runner_up_gap']=None
    assert exclusion_reason(single)=='excluded_stable_sampled_pre_alignment'


def test_filtered_features_preserve_original_component_median_recipe_and_round_support():
    report,tracking,sampled=sources(exclude=(0,))
    values,coverage=filtered_features(report,tracking,sampled)
    assert values==[10.,100.,2.,3.]
    assert coverage['retained_windows']==5 and coverage['eligible_tracking_windows']==5
    assert coverage['eligible_rounds']==[1,2,3]
    assert coverage['selection_counts']['excluded_stable_sampled_pre_alignment']==1


def test_many_windows_in_one_round_do_not_satisfy_repeated_round_requirement():
    report,tracking,sampled=sources(rounds=(1,)*6)
    values,coverage=filtered_features(report,tracking,sampled)
    assert values is None and coverage['eligible_tracking_windows']==6
    assert coverage['eligible_rounds']==[1] and coverage['abstention_reason']


def test_exclusion_or_missing_tracking_never_becomes_a_legitimate_classification():
    report,tracking,sampled=sources(exclude=(0,1))
    values,coverage=filtered_features(report,tracking,sampled)
    assert values is None and coverage['eligible_tracking_windows']==4
    report,tracking,sampled=sources()
    for w in tracking['windows'][:2]:w['tracks'][0]['segment_ids'][-9:]=[1]*9
    assert filtered_features(report,tracking,sampled)[0] is None


def test_window_and_candidate_identity_mismatches_fail():
    report,tracking,sampled=sources();sampled[0]['engagement_id']=99
    with pytest.raises(ValueError,match='identities'):filtered_features(report,tracking,sampled)
    report,tracking,sampled=sources();sampled[0]['snapshots'][0]['nearest']='b'
    with pytest.raises(ValueError,match='Candidate identity'):filtered_features(report,tracking,sampled)
    with pytest.raises(ValueError,match='counts'):filtered_features(report,tracking,sampled[:-1])


def test_damage_labels_and_post_shot_samples_do_not_choose_exclusion():
    report,tracking,sampled=sources(exclude=(0,));before=filtered_features(report,tracking,sampled)
    for w in tracking['windows']:
        w['damage_recipients']=['b'];w['damage_events']=[dict(tick=24,opponent_id='b')]
        for key in ('signed_error_degrees','yaw_rate_dps','bearing_rate_dps'):
            w['tracks'][0][key][20:]=[None]*6
    assert filtered_features(report,tracking,sampled)==before
