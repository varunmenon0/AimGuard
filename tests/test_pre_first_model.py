import pytest
from aimguard.pre_first_model import pre_features


def test_complete_window_minimum_and_median_do_not_substitute_missing_values():
    ws=[{'pre_first_features':[1,2]} for _ in range(4)]+[{'pre_first_features':[None,3]}]
    assert pre_features(ws)==(None,4)
    ws.append({'pre_first_features':[9,10]})
    assert pre_features(ws)==([1,2],5)
