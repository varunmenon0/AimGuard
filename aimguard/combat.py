"""Explicit weapon selection and interval-based movement summaries."""
import numpy as np

from aimguard.core import angle_delta

FIREARMS = frozenset(('ak47 aug awp bizon cz75a deagle elite famas fiveseven g3sg1 '
                     'galilar glock hkp2000 m249 m4a1 m4a1_silencer mac10 mag7 mp5sd '
                     'mp7 mp9 negev nova p250 p90 revolver sawedoff scar20 sg556 ssg08 '
                     'tec9 ump45 usp_silencer xm1014').split())


def weapon_names(events):
    if 'weapon' not in events:
        return events['event_type'].map(lambda _: 'unknown')
    return events['weapon'].fillna('unknown').astype(str).str.lower().str.removeprefix('weapon_')


def selected_fire(events, mode):
    if mode not in ('firearms', 'all'):
        raise ValueError('weapon_mode must be firearms or all')
    fires = events['event_type'].eq('weapon_fire')
    return fires & (weapon_names(events).isin(FIREARMS) if mode == 'firearms' else True)


def movement_context(trajectory, shot_ticks, tickrate, radius):
    """Classify speed intervals by ending tick without joining disjoint spans.

    Acceleration needs two adjacent intervals in the same category, and jerk
    needs three. Other derivatives at category boundaries remain unassigned.
    """
    ticks = trajectory['tick'].to_numpy(dtype=float)
    dt = np.diff(ticks) / tickrate
    speed = np.hypot(angle_delta(np.diff(trajectory['yaw'])), np.diff(trajectory['pitch'])) / dt
    acceleration = np.diff(speed) / ((dt[1:] + dt[:-1]) / 2)
    jerk = np.diff(acceleration) / ((dt[:-2] + 2 * dt[1:-1] + dt[2:]) / 4)
    shots = np.unique(shot_ticks)
    positions = np.searchsorted(shots, ticks[1:])
    left = shots[np.maximum(positions - 1, 0)]
    right = shots[np.minimum(positions, len(shots) - 1)]
    distance = np.minimum(abs(ticks[1:] - left), abs(ticks[1:] - right)) / tickrate
    near = distance <= radius
    result = {}
    for name, mask in [('near_shot', near), ('surrounding', ~near)]:
        accel_mask = mask[:-1] & mask[1:]
        jerk_mask = mask[:-2] & mask[1:-1] & mask[2:]
        values = speed[mask]
        result[name] = {
            'speed_intervals': int(mask.sum()),
            'covered_seconds': float(dt[mask].sum()),
            'acceleration_samples': int(accel_mask.sum()), 'jerk_samples': int(jerk_mask.sum()),
            'mean_speed': float(values.mean()) if len(values) else None,
            'p95_speed': float(np.percentile(values, 95)) if len(values) else None,
            'mean_accel': float(abs(acceleration[accel_mask]).mean()) if accel_mask.any() else None,
            'p95_jerk': float(np.percentile(abs(jerk[jerk_mask]), 95)) if jerk_mask.any() else None,
        }
    return result
