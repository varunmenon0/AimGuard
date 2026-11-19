from scripts.acquire_legitimate_cohort import select_labels
from scripts.audit_replay_identities import PUBLIC_INDIVIDUAL_DESKTOP


def rows():
    return [dict(match_id='m',steamid=str(PUBLIC_INDIVIDUAL_DESKTOP+n),isCheater='0')
            for n in (100,1000,2000,3000)]


def test_selection_caps_each_match_and_stops_at_remaining_target():
    source=rows(); participants=[r['steamid'] for r in source]
    assert len(select_labels(source,participants,50))==2
    assert len(select_labels(source,participants,1))==1
    assert select_labels(source,participants,0)==[]
    assert select_labels(source,participants,50)==select_labels(list(reversed(source)),participants,50)


def test_only_explicit_legitimate_labels_map_to_exact_accounts():
    source=rows(); source[0]['isCheater']='1'
    selected=select_labels(source,[r['steamid'] for r in source],50)
    assert all(r['isCheater']=='0' for r in selected)
    assert source[0]['steamid'] not in {r['exact_steamid'] for r in selected}
    assert select_labels(source,['11','12'],50)==[]


def test_rounded_identity_collisions_are_excluded_and_duplicate_rows_not_recounted():
    token='76561199000000001'
    assert select_labels([dict(match_id='m',steamid=token,isCheater='0')],
                         [token,'76561199000000002'],50)==[]
    source=rows()[:1]
    assert len(select_labels(source+source,[source[0]['steamid']],50))==1
