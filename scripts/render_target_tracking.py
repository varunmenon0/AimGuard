"""Create local trajectory viewers from saved tracking diagnostics, without refitting."""
import argparse
import html
import json
from pathlib import Path

PAGE = r'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AimGuard fixed-opponent tracking</title><style>body{font:16px system-ui;max-width:1000px;margin:30px auto;padding:20px;color:#17392b}select{font:inherit;max-width:100%;padding:8px}svg{width:100%;height:auto;background:#fafbf9;border:1px solid #ddd}p{line-height:1.5}pre{white-space:pre-wrap}section{margin:24px 0}table{border-collapse:collapse}td,th{padding:8px;border:1px solid #ddd}</style>
<h1 id="title"></h1><p>Recorded horizontal geometry. Damage association applies to the whole window, not a specific bullet or intended target. Visibility is unknown.</p>
<label>Window <select id="window"></select></label> <label>Opponent <select id="opponent"></select></label>
<p id="context"></p><section id="plots"></section><div id="metrics"></div>
<p>Red vertical markers show shots; purple markers show damage to the selected opponent. Lines break at missing/invalid samples, death events, and team changes. Green is recorded yaw velocity; blue is opponent bearing velocity. Translation affects bearing velocity. This is not a cheating verdict.</p>
<script>
const data=__DATA__;
const windows=document.getElementById('window'), opponents=document.getElementById('opponent');
document.getElementById('title').textContent=data.summary.case_id+' · fixed-opponent trajectories';
data.windows.forEach((w,i)=>windows.add(new Option('Window '+(w.engagement_id+1)+' · '+w.weapon+' · '+w.association,i)));
function chart(track,keys,title,colors){
 const w=data.windows[Number(windows.value)], first=w.shot_ticks[0], rate=data.assumed_tickrate_hz;
 const times=track.ticks.map(t=>(t-first)/rate), vals=keys.flatMap(k=>track[k].filter(v=>v!==null));
 const lo=vals.length?Math.min(...vals):0, hi=vals.length?Math.max(...vals):1, pad=Math.max((hi-lo)*.08,.1);
 const xmin=times[0]??0, xmax=times[times.length-1]??1;
 const x=t=>65+(t-xmin)/Math.max(xmax-xmin,1e-9)*840;
 const y=v=>210-(v-lo+pad)/(hi-lo+2*pad)*180;
 let svg='<svg viewBox="0 0 940 260" role="img" aria-label="'+title+'"><text x="65" y="20">'+title+'</text>';
 for(const tick of w.shot_ticks)svg+='<line x1="'+x((tick-first)/rate)+'" x2="'+x((tick-first)/rate)+'" y1="30" y2="215" stroke="#b64841" stroke-dasharray="3 3"/>';
 for(const event of w.damage_events??[])if(event.opponent_id===track.opponent_id)svg+='<line x1="'+x((event.tick-first)/rate)+'" x2="'+x((event.tick-first)/rate)+'" y1="30" y2="215" stroke="#8757a3" stroke-dasharray="6 3"/>';
 [lo,hi].forEach(v=>svg+='<text x="3" y="'+y(v)+'">'+v.toFixed(2)+'</text>');
 keys.forEach((key,k)=>{let path='',previous=-1;
  track[key].forEach((v,i)=>{if(v===null||track.segment_ids[i]<0){previous=-1;return;}
   path+=(previous===track.segment_ids[i]?'L':'M')+x(times[i]).toFixed(2)+','+y(v).toFixed(2)+' ';previous=track.segment_ids[i];});
  svg+='<path d="'+path+'" fill="none" stroke="'+colors[k]+'" stroke-width="1.5"/>';});
 svg+='<text x="65" y="240">'+xmin.toFixed(3)+' s</text><text x="795" y="240">'+xmax.toFixed(3)+' s</text></svg>';
 return svg;
}
function draw(){
 const w=data.windows[Number(windows.value)]; if(!w)return;
 const track=w.tracks[Number(opponents.value)];
 document.getElementById('context').textContent='Round '+w.round_id+' · '+w.shot_ticks.length+' shots · '+w.damage_recipients.length+' window damage recipients';
 if(!track){document.getElementById('plots').textContent='No candidate available.';document.getElementById('metrics').textContent='';return;}
 document.getElementById('plots').innerHTML=chart(track,['signed_error_degrees'],'Signed horizontal aim error (degrees)',['#17392b'])+chart(track,['yaw_rate_dps','bearing_rate_dps'],'Yaw velocity (green) and opponent bearing velocity (blue), degrees/s',['#147756','#3067ad']);
 const table=document.createElement('table');
 const rows=[['Coverage','Full window','Within 100 ms of shots'],['Valid samples',track.full_window.valid_samples,track.near_shot.valid_samples],['Valid intervals',track.full_window.valid_intervals,track.near_shot.valid_intervals],['Median absolute error (degrees)',track.full_window.median_absolute_error_degrees,track.near_shot.median_absolute_error_degrees],['Median absolute relative velocity (degrees/s)',track.full_window.median_absolute_relative_rate_dps,track.near_shot.median_absolute_relative_rate_dps],['Velocity correlation',track.full_window.yaw_bearing_rate_correlation,track.near_shot.yaw_bearing_rate_correlation]];
 rows.forEach(row=>{const tr=document.createElement('tr');row.forEach(v=>{const td=document.createElement('td');td.textContent=v===null?'Unavailable':(typeof v==='number'?v.toFixed(3):v);tr.appendChild(td);});table.appendChild(tr);});
 document.getElementById('metrics').replaceChildren(table);
}
function changeWindow(){
 const w=data.windows[Number(windows.value)];opponents.replaceChildren();
 if(w)w.tracks.forEach((t,i)=>opponents.add(new Option('Opponent '+(i+1)+' · '+t.association_sources.join(' + '),i)));
 draw();
}
const startup=new URLSearchParams(globalThis.location?.hash.slice(1)??'');
function requestedIndex(name,count){const value=startup.get(name);return value!==null&&/^\d+$/.test(value)&&Number(value)<count?Number(value):0;}
windows.value=String(requestedIndex('w',data.windows.length));
windows.addEventListener('change',changeWindow);opponents.addEventListener('change',draw);changeWindow();
opponents.value=String(requestedIndex('t',data.windows[Number(windows.value)]?.tracks.length??0));draw();
</script></html>'''


def render(directory):
    directory=Path(directory)
    summary=json.loads((directory/'summary.json').read_text())
    cases=summary['cases'];rows=[];links=[]
    for index,case in enumerate(cases,1):
        record=json.loads((directory/f'case_{index:04d}.json').read_text())
        if record['summary']!=case:
            raise ValueError('Tracking summary mismatch')
        payload=json.dumps(record,allow_nan=False).replace('<',r'\u003c')
        (directory/f'case_{index:04d}.html').write_text(PAGE.replace('__DATA__',payload))
        links.append(f'<li><a href="case_{index:04d}.html">{html.escape(case["case_id"])}</a></li>')
        rows.append(f"| {case['case_id']} | {case['label']} | {case['windows']} | {case.get('single_damage_recipient',0)} | {case.get('multiple_damage_recipients',0)} | {case.get('nearest_in_damage_recipients',0)}/{case.get('damage_windows_with_geometric_candidate',0)} | {case.get('pre_shot_nearest_in_damage_recipients',0)}/{case.get('damage_windows_with_pre_shot_candidate',0)} | {case.get('tracks_with_valid_intervals',0)}/{case.get('tracks',0)} |")
    def total(key):return sum(c.get(key,0) for c in cases)
    text='\n'.join(['# Fixed-opponent tracking diagnostics','',
        f"{len(cases)} development cases; {total('tracks_with_valid_intervals')}/{total('tracks')} tracks have consecutive valid samples.",
        f"{total('single_damage_recipient')} windows have one matching damage recipient; {total('multiple_damage_recipients')} have multiple recipients.",
        f"The first-shot geometric candidate belongs to the window damage-recipient set in {total('nearest_in_damage_recipients')}/{total('damage_windows_with_geometric_candidate')} eligible windows.",
        f"The exact pre-first-shot candidate belongs to that set in {total('pre_shot_nearest_in_damage_recipients')}/{total('damage_windows_with_pre_shot_candidate')} eligible windows.",
        'This is an association diagnostic, not target-attribution accuracy: the first shot and later damage may concern different opponents.',
        '', '| Case | Label | Windows | One recipient | Multiple recipients | Shot-tick/event agreement | Pre-shot/event agreement | Usable tracks |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |',*rows,
        '', '## Limits','',*['- '+v for v in summary['limitations']],
        '', 'No detection model or threshold changed. Correlation is unavailable for stationary or insufficient rate observations. Invalid samples and gaps split trajectories rather than being joined.',''])
    (directory/'report.md').write_text(text)
    (directory/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>AimGuard tracking diagnostics</title><style>body{font:16px system-ui;max-width:1100px;margin:30px auto;padding:20px}pre{white-space:pre-wrap}li{display:inline-block;margin:8px}</style><h1>Fixed-opponent tracking</h1><p>Horizontal geometry and window-level event association. Development only; no new detection claims.</p><ul>'+''.join(links)+'</ul><pre>'+html.escape(text)+'</pre>')
    print(text)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    args=parser.parse_args(argv);render(args.directory)


if __name__=='__main__':main()
