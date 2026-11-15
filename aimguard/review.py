"""Build a self-contained HTML review report from one gameplay analysis."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from aimguard.core import angle_delta


def build_review(directory, output):
    report = json.loads((directory / 'report.json').read_text())
    player = pd.read_csv(directory / 'telemetry.csv', usecols=['tick', 'segment_id', 'yaw', 'pitch'])
    rate = report['assumed_tickrate_hz']
    windows = []
    for window in report['engagements']:
        part = player.loc[player['segment_id'].eq(window['segment_id']) &
                          player['tick'].between(window['start_tick'], window['end_tick'])]
        if len(part) != window['samples']:
            raise ValueError(f"Telemetry does not match window {window['engagement_id']}")
        tick, yaw, pitch = (part[key].to_numpy() for key in ('tick', 'yaw', 'pitch'))
        first_shot = window['shot_ticks'][0]
        speed = np.hypot(angle_delta(np.diff(yaw)), np.diff(pitch)) / (np.diff(tick) / rate)
        windows.append({
            **window, 'time': ((tick - first_shot) / rate).tolist(),
            'shots': [(shot - first_shot) / rate for shot in window['shot_ticks']],
            'yaw': np.rad2deg(np.unwrap(np.deg2rad(yaw))).tolist(),
            'pitch': pitch.tolist(), 'speed': [None, *speed.tolist()],
        })
    data = dict(player=report['steamid'], replay=Path(report['source']).name,
                rate=rate, quality=report['data_quality'], windows=windows,
                near_shot_seconds=report.get('configuration', {}).get('near_shot_seconds'))
    payload = json.dumps(data, allow_nan=False).replace('<', r'\u003c')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as handle:
        handle.write(PAGE.replace('__REPORT_DATA__', payload))


PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AimGuard replay review</title>
<style>
body{margin:0;background:#f4f5f2;color:#172723;font:16px system-ui,sans-serif}
main{max-width:920px;margin:auto;padding:32px 20px}
h1{margin-bottom:8px} h2{font-size:1.1rem} p{line-height:1.5}
section{background:white;border:1px solid #d9dfd9;border-radius:12px;padding:20px;margin-top:16px}
.controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
button,select{font:inherit;padding:7px;border:1px solid #9aa9a0;border-radius:6px;background:white}
svg{display:block;width:100%;height:auto} svg text{font:12px system-ui;fill:#263b33}
dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
dt{font-size:.85rem;color:#455b52} dd{margin:2px 0 0;font-variant-numeric:tabular-nums}
</style>
<main>
<h1>AimGuard replay review</h1>
<p id="context"></p>
<p id="coverage"></p>
<section id="review">
<div class="controls">
<label for="window">Shooting window</label>
<select id="window"></select>
<button id="prev" type="button">Previous</button>
<button id="next" type="button">Next</button>
</div>
<p id="detail"></p>
<p>Red markers show weapon fire. Time is relative to the first shot.</p>
<div id="plots"></div>
<section id="shot-time-profile" hidden></section>
<section id="movement-context" hidden></section>
<h2>Full-window movement features</h2>
<dl id="features"></dl>
</section>
<p>Features describe recorded movement around shots. They do not assign a cheating verdict.</p>
</main>
<script id="report-data" type="application/json">__REPORT_DATA__</script>
<script>
const data = JSON.parse(document.getElementById('report-data').textContent);
const byId = id => document.getElementById(id);
const select = byId('window');
byId('context').textContent = data.replay + ' · Player ' + data.player + ' · Assumed ' + data.rate + ' Hz';
const q = data.quality;
byId('coverage').textContent = data.windows.length + ' windows · ' + q.active_samples.toLocaleString()
  + ' active samples · ' + q.round_event_anomalies.length + ' round event warnings';
const profileLabels = {pre_shot_p95_speed: 'Before-shot p95 speed (degrees/s)', on_shot_median_speed: 'At-shot median speed (degrees/s)', post_shot_p95_speed: 'After-shot p95 speed (degrees/s)', pre_post_speed_log_ratio: 'Before/after speed log ratio', near_shot_stop_fraction: 'Near-shot stop fraction', near_shot_mean_turn: 'Near-shot mean turn (radians)', near_shot_yaw_reversals_per_second: 'Near-shot yaw reversals/s', near_shot_pitch_reversals_per_second: 'Near-shot pitch reversals/s', near_shot_peak_offset_seconds: 'Near-shot speed peak offset (seconds)'};
const metricLabels = {mean_speed: 'Mean speed (degrees/s)', p95_speed: '95th percentile speed (degrees/s)', mean_accel: 'Mean absolute speed acceleration (degrees/s²)', p95_jerk: '95th percentile absolute speed jerk (degrees/s³)', covered_seconds: 'Covered time (seconds)'};
const number = new Intl.NumberFormat(undefined, {maximumSignificantDigits: 5});
function plot(w, values, label) {
  let low = Infinity, high = -Infinity;
  for (const value of values) if (value !== null) {
    low = Math.min(low, value);
    high = Math.max(high, value);
  }
  if (low === high) { low -= 0.5; high += 0.5; }
  const first = w.time[0], last = w.time[w.time.length - 1];
  const x = t => 78 + 680 * (t - first) / (last - first);
  const y = v => 122 - 86 * (v - low) / (high - low);
  const points = values.flatMap((v, i) => v === null ? [] : [x(w.time[i]) + ',' + y(v)]).join(' ');
  const radius = data.near_shot_seconds;
  const bands = radius ? w.shots.map(t => {
    const left = x(Math.max(first, t - radius)), right = x(Math.min(last, t + radius));
    return '<rect x="' + left + '" y="36" width="' + (right - left) + '" height="86" fill="#dceee6"/>';
  }).join('') : '';
  const shots = w.shots.map(t => '<line x1="' + x(t) + '" x2="' + x(t)
    + '" y1="36" y2="122" stroke="#b23940" opacity=".55"/>').join('');
  return '<svg viewBox="0 0 780 155" role="img" aria-label="' + label + '">'
    + '<text x="78" y="20">' + label + '</text><path d="M78 36V122H758" fill="none" stroke="#9aa9a0"/>'
    + '<text x="4" y="41">' + number.format(high) + '</text><text x="4" y="122">' + number.format(low)
    + '</text>' + bands + shots + '<polyline points="' + points + '" fill="none" stroke="#14654e" stroke-width="2"/>'
    + '<text x="78" y="144">' + number.format(first) + ' s</text><text x="758" y="144" text-anchor="end">'
    + number.format(last) + ' s</text></svg>';
}
function render() {
  const i = select.selectedIndex, w = data.windows[i];
  byId('prev').disabled = i === 0;
  byId('next').disabled = i === data.windows.length - 1;
  byId('detail').textContent = 'Round ' + w.round_id + ' · Ticks ' + w.start_tick + '–' + w.end_tick
    + (w.weapon ? ' · ' + w.weapon : '') + ' · ' + w.shot_count + (w.shot_count === 1 ? ' shot' : ' shots');
  byId('plots').innerHTML = plot(w, w.yaw, 'Yaw (degrees, unwrapped)')
    + plot(w, w.pitch, 'Pitch (degrees)') + plot(w, w.speed, 'Angular speed (degrees/s)');
  const profile = byId('shot-time-profile');
  profile.hidden = !w.shot_time_profile;
  profile.replaceChildren();
  if (w.shot_time_profile) {
    const title = document.createElement('h2'), note = document.createElement('p'), list = document.createElement('dl');
    title.textContent = 'Direction and shot timing';
    note.textContent = 'Before, at, and after refer to the nearest shot. Positive peak timing means after that shot. A dash indicates no eligible observations.';
    for (const [key, label] of Object.entries(profileLabels)) {
      const group = document.createElement('div'), term = document.createElement('dt'), detail = document.createElement('dd');
      term.textContent = label;
      const value = w.shot_time_profile[key];
      detail.textContent = value === null ? '—' : number.format(value);
      group.append(term, detail);
      list.append(group);
    }
    profile.append(title, note, list);
  }
  const context = byId('movement-context');
  context.hidden = !w.movement_context;
  context.replaceChildren();
  if (w.movement_context) {
    const title = document.createElement('h2');
    title.textContent = 'Movement within ' + Math.round(data.near_shot_seconds * 1000) + ' ms of shots and surrounding movement';
    const note = document.createElement('p');
    note.textContent = 'Green shading marks the near-shot periods. Derivatives use consecutive intervals within each category. A dash indicates no eligible samples.';
    context.append(title, note);
    for (const [region, stats] of Object.entries(w.movement_context)) {
      const label = document.createElement('h3'), list = document.createElement('dl');
      label.textContent = region === 'near_shot' ? 'Near shots' : 'Surrounding movement';
      for (const [key, value] of Object.entries(stats)) {
        const group = document.createElement('div'), term = document.createElement('dt'), detail = document.createElement('dd');
        term.textContent = metricLabels[key] || key.replaceAll('_', ' ');
        detail.textContent = value === null ? '—' : number.format(value);
        group.append(term, detail);
        list.append(group);
      }
      context.append(label, list);
    }
  }
  byId('features').replaceChildren(...Object.entries(w.features).map(([key, value]) => {
    const group = document.createElement('div'), term = document.createElement('dt'), detail = document.createElement('dd');
    term.textContent = metricLabels[key] || key.replaceAll('_', ' ');
    detail.textContent = number.format(value);
    group.append(term, detail);
    return group;
  }));
}
if (data.windows.length) {
  for (const w of data.windows) select.add(new Option('Window ' + (w.engagement_id + 1) + ' · Round ' + w.round_id));
  select.addEventListener('change', render);
  byId('prev').onclick = () => { select.selectedIndex--; render(); };
  byId('next').onclick = () => { select.selectedIndex++; render(); };
  render();
} else {
  byId('review').textContent = 'No shooting windows were published for this player.';
}
</script>
</html>
"""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('analysis', type=Path, help='Folder containing report.json and telemetry.csv')
    parser.add_argument('--output', type=Path, help='New HTML file (default: review.html in the analysis folder)')
    args = parser.parse_args(argv)
    output = args.output or args.analysis / 'review.html'
    try:
        build_review(args.analysis, output)
    except (OSError, ValueError, KeyError) as exc:
        parser.error(str(exc))
    print(output)


if __name__ == '__main__':
    main()
