import pandas as pd
import pytest
from aimguard.candidate_audit import ranked_snapshot, compare_snapshots, summarize


def player(tick, identity, x, y, yaw=0, team=3, health=100, state=0):
    return dict(tick=tick,steamid=identity,X=x,Y=y,yaw=yaw,team_num=team,health=health,life_state=state)


def test_snapshot_ranks_all_valid_opponents_with_deterministic_ties():
    frame=pd.DataFrame([player(9,'s',0,0,team=2), player(9,'b',10,0),player(9,'a',10,0),player(9,'c',0,10)])
    result=ranked_snapshot(frame,'s',9,[])
    assert [c['opponent_id'] for c in result['candidates']]==['a','b','c']
    assert result['runner_up_gap']==0 and result['nearest_error']==0
    assert result['nearest']=='a'


def test_death_events_teams_and_known_non_alive_state_exclude_candidates():
    frame=pd.DataFrame([player(9,'s',0,0,team=2),player(9,'dead',10,0),player(9,'dying',10,1,state=1),
                        player(9,'friend',10,2,team=2),player(9,'alive',10,10)])
    result=ranked_snapshot(frame,'s',9,[('dead',9)])
    assert result['nearest']=='alive' and result['runner_up_gap'] is None
    assert ranked_snapshot(frame,'s',9,[('s',9)])['status']=='unavailable'


def test_snapshot_uses_exact_tick_and_shortest_wrapped_yaw_difference():
    frame=pd.DataFrame([player(9,'s',0,0,yaw=179,team=2),player(9,'a',-10,-.17455),player(10,'b',10,0)])
    result=ranked_snapshot(frame,'s',9,[])
    assert result['nearest_error']==pytest.approx(2,abs=.001)
    assert ranked_snapshot(frame,'s',8,[])['reason']=='missing_shooter'


def test_changes_and_selection_excess_do_not_switch_endpoint_identity():
    endpoint=dict(status='available',nearest='a',nearest_error=1,candidates=[dict(opponent_id='a',error_degrees=1)])
    earlier=dict(status='available',nearest='b',nearest_error=2,candidates=[dict(opponent_id='b',error_degrees=2),dict(opponent_id='a',error_degrees=7)])
    result=compare_snapshots(endpoint,earlier)
    assert result['same_nearest'] is False and result['endpoint_selection_excess_earlier']==5
    assert result['endpoint_candidate_error_earlier']==7


def test_missing_pair_is_unavailable_not_a_candidate_switch():
    endpoint=dict(status='available',nearest='a')
    earlier=dict(status='available',nearest='b',nearest_error=2,candidates=[dict(opponent_id='b',error_degrees=2)])
    assert compare_snapshots(endpoint,earlier)['status']=='unavailable'
    assert compare_snapshots(endpoint,dict(status='unavailable'))['status']=='unavailable'


def test_summary_keeps_missing_denominators_and_single_candidate_gaps_distinct():
    endpoint=dict(status='available',candidates=[dict(opponent_id='a')],nearest_error=1,runner_up_gap=None)
    available=dict(status='available',same_nearest=True,endpoint_selection_excess_earlier=0)
    windows=[dict(snapshots=[endpoint],comparisons=[available,available]),
             dict(snapshots=[dict(status='unavailable')],comparisons=[dict(status='unavailable')]*2)]
    result=summarize(windows)
    assert result['windows']==2 and result['available_endpoints']==1
    assert result['median_runner_up_gap'] is None and result['runner_up_available']==0
    assert result['lag_0.2']['comparable_windows']==1 and result['lag_0.2']['same_nearest_fraction']==1
    assert summarize([])['median_nearest_error'] is None


def test_duplicate_player_ticks_are_rejected_instead_of_arbitrarily_ranked():
    frame=pd.DataFrame([player(9,'s',0,0,team=2),player(9,'a',10,0),player(9,'a',10,1)])
    with pytest.raises(ValueError,match='duplicate'):ranked_snapshot(frame,'s',9,[])


def test_rendered_review_escapes_fields_and_checks_case_receipts(tmp_path):
    import json
    from aimguard.baseline import digest
    from scripts.render_candidate_audit import render
    def write(name,value): (tmp_path/name).write_text(json.dumps(value))
    write('protocol.json',{})
    record=dict(case_id='C-1',cohort='<script>bad</script>',summary={},review=str(tmp_path/'review.html'),
        windows=[dict(engagement_id=0,first_shot_tick=42,weapon='<img>',snapshots=[dict(status='unavailable')],
            comparisons=[dict(status='unavailable')]*2)])
    write('C-1.json',record)
    write('summary.json',dict(protocol_sha256=digest(tmp_path/'protocol.json'),cases=[dict(case_id='C-1',summary={})],
        case_sha256={'C-1':digest(tmp_path/'C-1.json')}))
    (tmp_path/'report.md').write_text('<script>report</script>')
    render(tmp_path)
    assert '<script>' not in (tmp_path/'index.html').read_text()
    assert '&lt;img&gt;' in (tmp_path/'C-1.html').read_text()
    write('C-1.json',{})
    with pytest.raises(ValueError,match='receipt mismatch'):render(tmp_path)
