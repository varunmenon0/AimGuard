import copy
import pytest
from scripts.report_legitimate_cohort import verify_groups


def fixture():
    groups=[dict(group_id='G1',match_id='m1',case_ids=['A','B'],account_participants=['1','2']),
            dict(group_id='G2',match_id='m2',case_ids=['C'],account_participants=['3','4'])]
    cases=[dict(case_id=cid,group_id=g['group_id'],match_id=g['match_id'],account_participants=g['account_participants'],
                steamid=steamid,demo_sha256=g['match_id'],label='legitimate',features_inspected=False)
           for g in groups for cid,steamid in zip(g['case_ids'],g['account_participants'])]
    return cases,groups


def test_players_in_one_match_share_group_but_cross_match_identity_overlap_rejects():
    cases,groups=fixture();assert verify_groups(cases,groups,set())==4
    with pytest.raises(ValueError,match='prior account overlap'):verify_groups(cases,groups,{'4'})
    bad=copy.deepcopy(groups);bad[1]['account_participants'].append('1')
    with pytest.raises(ValueError,match='overlap'):verify_groups(cases,bad,set())


def test_unlabeled_teammates_and_duplicate_or_ungrouped_cases_never_count():
    cases,groups=fixture()
    bad=copy.deepcopy(cases);bad[0]['label']='unknown'
    with pytest.raises(ValueError,match='label'):verify_groups(bad,groups,set())
    with pytest.raises(ValueError,match='Duplicate'):verify_groups(cases+[cases[0]],groups,set())
    with pytest.raises(ValueError,match='Ungrouped'):verify_groups(cases,groups[:1],set())
