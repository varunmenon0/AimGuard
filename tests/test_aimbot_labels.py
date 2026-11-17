import pytest
from aimguard.aimbot_labels import classify,require_active_aimbot_training


def test_generic_cheating_and_legitimate_labels_never_imply_activation():
    for label in ('cheating','legitimate'):
        r=classify(label)
        assert r['original_label']==label and r['eligible_as_confirmed_aimbot_positive'] is False
        assert r['activation_status']=='not_verified' and r['verified_activation_intervals']==[]


def test_author_aimbot_claims_and_wallhack_claims_remain_separate_from_truth():
    for kind in ('author_described_aimbot','author_described_aimbot_and_wallhack','author_described_wallhack_only'):
        r=classify('cheating',{'author_description':kind})
        assert r['subtype_evidence']==kind and r['eligible_as_confirmed_aimbot_positive'] is False
        assert r['original_label']=='cheating'
    with pytest.raises(ValueError):classify('legitimate',{'author_description':'author_described_aimbot'})
    with pytest.raises(ValueError):classify('cheating',{'author_description':'guessed_from_score'})


def test_provenance_audit_cannot_authorize_active_aimbot_training():
    with pytest.raises(ValueError,match='blocked'):
        require_active_aimbot_training({'role':'aimbot_label_provenance_audit','confirmed_active_aimbot_positives':17})
