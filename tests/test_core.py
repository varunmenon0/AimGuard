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


def test_jerk_uses_acceleration_midpoint_times_on_irregular_samples():
    dt = np.array([.01, .02, .04, .01, .03, .02, .01])
    speed = np.array([1., 2., 4., 8., 16., 32., 64.])
    time = np.r_[0, np.cumsum(dt)]
    yaw = np.r_[0, np.cumsum(speed * dt)]
    velocity_times = (time[:-1] + time[1:]) / 2
    acceleration = np.diff(speed) / np.diff(velocity_times)
    acceleration_times = (velocity_times[:-1] + velocity_times[1:]) / 2
    jerk = np.diff(acceleration) / np.diff(acceleration_times)
    assert extract_features(time, yaw, np.zeros(8))['p95_jerk'] == pytest.approx(np.percentile(abs(jerk), 95))


@pytest.mark.parametrize('bad', [np.zeros((8, 1)), np.array(1.)])
def test_requires_one_dimensional_samples(bad):
    with pytest.raises(ValueError, match='one-dimensional'):
        extract_features(bad, bad, bad)
