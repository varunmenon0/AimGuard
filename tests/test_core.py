import numpy as np
import pytest
from aimguard.core import angle_delta,extract_features,FEATURE_NAMES
from aimguard.demo import dataset

def test_wrap():
    assert np.allclose(angle_delta([358,-358]),[-2,2])

def test_features():
    t=np.arange(100)/64
    f=extract_features(t,10+30*t,np.zeros(100))
    assert set(f)==set(FEATURE_NAMES)
    assert f['mean_speed']==pytest.approx(30)
    assert f['path_efficiency']==pytest.approx(1)

def test_reject_invalid():
    with pytest.raises(ValueError): extract_features([0]*10,range(10),range(10))

def test_groups():
    X,y,g=dataset(sessions=10,windows=3)
    assert X.shape==(30,len(FEATURE_NAMES))
    assert len(set(g[:21]).intersection(set(g[21:])))==0
