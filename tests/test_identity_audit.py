import pytest

from scripts.audit_replay_identities import (
    PUBLIC_INDIVIDUAL_DESKTOP, account_id, check_disjoint, choose_target, identity_evidence,
)


A = str(PUBLIC_INDIVIDUAL_DESKTOP + 100)
B = str(PUBLIC_INDIVIDUAL_DESKTOP + 1000)


def test_account_fields_distinguish_local_numbers_and_other_account_types():
    assert account_id(A)
    for invalid in ('11', '12', '0', str(PUBLIC_INDIVIDUAL_DESKTOP),
                    str(PUBLIC_INDIVIDUAL_DESKTOP + (1 << 52)), float(A), '7.65e16'):
        assert not account_id(invalid)


def test_snapshot_local_ids_require_bot_corroboration_and_absence_from_controller():
    result = identity_evidence([A, '11'], [A], 1)
    assert result['account_participants'] == [A]
    assert result['local_non_account_ids'] == ['11']
    with pytest.raises(ValueError, match='corroborating'):
        identity_evidence([A, '11'], [A], 0)
    with pytest.raises(ValueError, match='controller'):
        identity_evidence([A, '11'], [A, '11'], 2)
    with pytest.raises(ValueError, match='Unsupported'):
        identity_evidence([A, '999999999999'], [A], 10)


def test_full_identity_stream_preserves_replaced_or_disconnected_accounts():
    result = identity_evidence([A, '12'], [A, B], 1)
    assert result['account_participants'] == sorted([A, B])
    with pytest.raises(ValueError, match='overlap'):
        check_disjoint(result['account_participants'], {B}, set())
    with pytest.raises(ValueError, match='overlap'):
        check_disjoint([A], set(), {A})
    check_disjoint([A], {B}, set())


def test_target_selection_is_metadata_only_one_per_match_and_order_invariant():
    rows = [dict(match_id='match', steamid=A, isCheater='0'),
            dict(match_id='match', steamid=B, isCheater='1')]
    assert choose_target(rows, [A, B])['exact_steamid'] == B
    assert choose_target(list(reversed(rows)), [A, B]) == choose_target(rows, [A, B])
    # Rounded source tokens that collide with two exact accounts remain unusable.
    large = '76561199000000001'
    with pytest.raises(ValueError, match='uniquely'):
        choose_target([dict(match_id='m', steamid=large, isCheater='1')],
                      [large, '76561199000000002'])
