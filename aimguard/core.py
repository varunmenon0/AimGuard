"""Trajectory features from server-observable view angles. All angles are degrees."""
import numpy as np

FEATURE_NAMES = ["mean_speed", "p95_speed", "mean_accel", "p95_jerk", "path_efficiency", "mean_turn", "speed_cv", "stop_fraction"]

def angle_delta(degrees):
    return (np.asarray(degrees) + 180.0) % 360.0 - 180.0

def extract_features(timestamps, yaw, pitch):
    t, y, p = [np.asarray(a, dtype=float) for a in (timestamps, yaw, pitch)]
    if not (len(t) == len(y) == len(p)) or len(t) < 8:
        raise ValueError("Need at least 8 equal-length samples")
    if not (np.isfinite(t).all() and np.isfinite(y).all() and np.isfinite(p).all()):
        raise ValueError("Nonfinite samples")
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError("Timestamps must increase strictly")
    if np.any(dt > 0.25):
        raise ValueError("Large telemetry gap; segment before extracting features")
    dy, dp = angle_delta(np.diff(y)), np.diff(p)
    steps = np.column_stack((dy, dp))
    speed = np.linalg.norm(steps, axis=1) / dt
    accel = np.diff(speed) / ((dt[1:] + dt[:-1]) / 2)
    jerk = np.diff(accel) / ((dt[2:] + dt[:-2]) / 2)
    total = np.linalg.norm(steps, axis=1).sum()
    net = np.linalg.norm(steps.sum(axis=0))
    a, b = steps[:-1], steps[1:]
    denom = np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1)
    valid = denom > 1e-9
    turns = np.arccos(np.clip(np.sum(a[valid]*b[valid], axis=1)/denom[valid], -1, 1)) if valid.any() else np.array([0.0])
    return dict(zip(FEATURE_NAMES, map(float, [
        speed.mean(), np.percentile(speed,95), np.abs(accel).mean(),
        np.percentile(np.abs(jerk),95) if len(jerk) else 0,
        net/max(total,1e-9), turns.mean(),
        speed.std()/max(speed.mean(),1e-9), np.mean(speed < 2.0)
    ])))
