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


def interval_motion(trajectory, shot_ticks, tickrate):
    """Motion and signed nearest-shot offsets at each interval's ending tick.

    Ties use the earlier shot, giving each interval exactly one reference shot.
    Input trajectory must already be finite, ordered, and confined to a segment.
    """
    ticks = trajectory['tick'].to_numpy(dtype=float)
    dt = np.diff(ticks) / tickrate
    steps = np.column_stack((angle_delta(np.diff(trajectory['yaw'])), np.diff(trajectory['pitch'])))
    speed = np.hypot(steps[:, 0], steps[:, 1]) / dt
    shots = np.unique(shot_ticks)
    positions = np.searchsorted(shots, ticks[1:])
    left = shots[np.maximum(positions - 1, 0)]
    right = shots[np.minimum(positions, len(shots) - 1)]
    left_offset = (ticks[1:] - left) / tickrate
    right_offset = (ticks[1:] - right) / tickrate
    offset = np.where(abs(left_offset) <= abs(right_offset), left_offset, right_offset)
    return dict(dt=dt, steps=steps, speed=speed, shot_offset_seconds=offset)


def movement_context(trajectory, shot_ticks, tickrate, radius):
    """Classify speed intervals by ending tick without joining disjoint spans.

    Acceleration needs two adjacent intervals in the same category, and jerk
    needs three. Other derivatives at category boundaries remain unassigned.
    """
    motion = interval_motion(trajectory, shot_ticks, tickrate)
    dt, speed = motion['dt'], motion['speed']
    acceleration = np.diff(speed) / ((dt[1:] + dt[:-1]) / 2)
    jerk = np.diff(acceleration) / ((dt[:-2] + 2 * dt[1:-1] + dt[2:]) / 4)
    near = abs(motion['shot_offset_seconds']) <= radius
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


def shot_time_profile(trajectory, shot_ticks, tickrate, radius):
    """Descriptive timing and direction features; no target or recoil attribution."""
    motion = interval_motion(trajectory, shot_ticks, tickrate)
    speed, steps, offset = motion['speed'], motion['steps'], motion['shot_offset_seconds']
    near = abs(offset) <= radius
    pre, on, post = near & (offset < 0), near & (offset == 0), near & (offset > 0)
    duration = float(motion['dt'][near].sum())
    adjacent = near[:-1] & near[1:]
    norms = np.linalg.norm(steps, axis=1)
    denominator = norms[:-1] * norms[1:]
    turning = adjacent & (denominator > 1e-9)
    turns = np.arccos(np.clip(np.sum(steps[:-1][turning] * steps[1:][turning], axis=1) /
                             denominator[turning], -1, 1))
    def percentile(mask):
        return float(np.percentile(speed[mask], 95)) if mask.any() else None
    pre_speed, post_speed = percentile(pre), percentile(post)
    near_indices = np.flatnonzero(near)
    peak = int(near_indices[np.argmax(speed[near])]) if len(near_indices) else None
    result = {
        'pre_shot_intervals': int(pre.sum()), 'on_shot_intervals': int(on.sum()),
        'post_shot_intervals': int(post.sum()),
        'pre_shot_p95_speed': pre_speed, 'post_shot_p95_speed': post_speed,
        'on_shot_median_speed': float(np.median(speed[on])) if on.any() else None,
        'pre_post_speed_log_ratio': float(np.log1p(pre_speed) - np.log1p(post_speed))
                                  if pre_speed is not None and post_speed is not None else None,
        'near_shot_stop_fraction': float(np.mean(speed[near] < 2.0)) if near.any() else None,
        'near_shot_mean_turn': float(turns.mean()) if len(turns) else None,
        'near_shot_peak_offset_seconds': float(offset[peak]) if peak is not None and speed[peak] > 1e-9 else None,
        'turning_pairs': int(turning.sum()),
    }
    for column, name in enumerate(('yaw', 'pitch')):
        values = steps[:, column]
        moving = abs(values) >= 0.05
        reversals = int(np.sum(adjacent & moving[:-1] & moving[1:] & (values[:-1] * values[1:] < 0)))
        result[f'near_shot_{name}_reversals'] = reversals
        result[f'near_shot_{name}_reversals_per_second'] = reversals / duration if duration else None
    return result
