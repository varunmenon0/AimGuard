from scripts.inventory_evaluation_data import classify, walk_records


def label(steamid, positive=False):
    return dict(steamid=steamid, isCheater='1' if positive else '0',
                source_label_file='source.csv', source_label_sha256='source-hash')


def test_previously_used_match_cannot_supply_new_targets():
    status, _, targets = classify(['76561199000000001'], set(), True,
                                  [label('76561199000000001')])
    assert status == 'previously_used_match'
    assert targets == []


def test_any_participant_overlap_excludes_whole_match_including_short_ids():
    status, overlap, targets = classify(['76561199000000001', '11'], {'11'}, False,
                                        [label('76561199000000001')])
    assert status == 'participant_overlap'
    assert overlap == ['11']
    assert targets == []


def test_ambiguous_rounded_label_never_becomes_an_exact_player_label():
    players = ['76561199000000001', '76561199000000002']
    status, _, targets = classify(players, set(), False, [label(players[0])])
    assert status == 'no_uniquely_resolved_source_label'
    assert targets == []


def test_only_uniquely_labeled_players_are_returned():
    players = ['76561199000000001', '76561199000001000']
    status, _, targets = classify(players, set(), False, [label(players[0], True)])
    assert status == 'metadata_eligible_not_yet_reserved'
    assert len(targets) == 1
    assert targets[0]['steamid'] == players[0]
    assert targets[0]['label'] == 'cheating'
    assert list(walk_records({'cases': [dict(participants=players)]}))[1]['participants'] == players
