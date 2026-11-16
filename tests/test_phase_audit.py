import pandas as pd
import pytest
from aimguard.phase_audit import global_phase,window_phase,WARMUP,STARTED


def test_global_flags_repeat_across_players_without_becoming_extra_samples():
    frame=pd.DataFrame(dict(tick=[1,1,2,2],**{WARMUP:[True,True,False,False],STARTED:[False,False,True,True]}))
    states=global_phase(frame)
    assert len(states)==2 and states[1]=={WARMUP:True,STARTED:False}
    assert window_phase([1,2],states)==dict(status='warmup',samples=2,sample_states={'warmup':1,'live':1})


def test_live_requires_explicit_false_warmup_and_true_match_start_at_every_tick():
    live={i:{WARMUP:False,STARTED:True} for i in range(3)}
    assert window_phase([0,1,2],live)['status']=='live'
    del live[1]
    result=window_phase([0,1,2],live)
    assert result['status']=='unknown' and result['sample_states']=={'live':2,'unknown':1}


def test_match_not_started_is_excluded_even_when_warmup_is_false():
    states={1:{WARMUP:False,STARTED:False}}
    assert window_phase([1],states)['status']=='match_not_started'


def test_conflicting_missing_and_string_flags_are_not_coerced_to_live():
    for warmup in ([False,True],[None,None],['False','False']):
        frame=pd.DataFrame(dict(tick=[1,1],**{WARMUP:warmup,STARTED:[True,True]}))
        assert window_phase([1],global_phase(frame))['status']=='unknown'
    frame=pd.DataFrame(dict(tick=[1],**{STARTED:[True]}))
    assert window_phase([1],global_phase(frame))['status']=='unknown'


@pytest.mark.parametrize('ticks',[[],[1,1],[2,1],[1.5]])
def test_invalid_support_ticks_fail_instead_of_silently_sorting_or_interpolating(ticks):
    with pytest.raises(ValueError):window_phase(ticks,{})


def test_invalid_parser_tick_fails_and_entire_boundary_window_remains_excluded():
    with pytest.raises(ValueError):global_phase(pd.DataFrame(dict(tick=[1.5],**{WARMUP:[False],STARTED:[True]})))
    states={1:{WARMUP:True,STARTED:True},2:{WARMUP:False,STARTED:True}}
    assert window_phase([1,2],states)['status']=='warmup'
