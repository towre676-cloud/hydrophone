"""Single-file offline audition using recovered Gen2 playNote, not a hardware driver."""
from pathlib import Path
import json,re
ROOT=Path(__file__).resolve().parent
core=(ROOT/'gen2_core.mjs').read_text()
core=re.sub(r'\nexport \{[^}]+\};\s*$', '',core)
score=(ROOT/'output/instrument_score.json').read_text()
template='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fusion / recovered Dyletsky audition</title>
<style>body{margin:0;background:#101c23;color:#e9f2f2;font:17px/1.65 system-ui}main{max-width:1040px;margin:0 auto;padding:42px 26px}h1{font-size:40px;line-height:1.1;margin:12px 0 22px}p{max-width:900px}.tag{color:#6ed6d8;font-size:13px;letter-spacing:.15em}button{font:600 16px system-ui;padding:13px 20px;margin:8px 8px 8px 0;border:0;border-radius:8px;background:#70d5c6;color:#10222a;cursor:pointer}button[disabled]{opacity:.5}table{border-collapse:collapse;width:100%;font-size:15px;table-layout:fixed}td,th{overflow-wrap:anywhere}td,th{text-align:left;padding:11px;border-bottom:1px solid #3b515c}th{color:#88dadd}.panel{background:#192c36;padding:24px;border-radius:14px;margin:25px 0}.status{color:#f3cc86;min-height:27px}a{color:#88dadd}small{color:#b3c4cb}#progress{width:100%;accent-color:#70d5c6}</style>
<main><div class="tag">FUSION INSTRUMENT / SOFTWARE INTEGRATION 0.2</div><h1>Dyletsky supplies the score.<br>The object supplies the response.</h1>
<p>This offline audition uses the recovered Gen2 43-row tuning and note-selection rules, then its original Web Audio note synthesizer. The saved score retains eight software voices, spelled notes, five visited phrase types, local memory and phrase memory. Its deterministic scheduler is a new headless adaptation. Room rendering, drones and percussion are preserved in the archive but are not performed here.</p>
<div class="panel"><button id="play">Play saved score</button><button id="stop" disabled>Stop</button><button id="save">Save score JSON</button><p class="status" id="status">Software audition only. No hardware connection.</p><progress id="progress" value="0" max="1"></progress><small id="event"></small></div>
<p>The physical plan mixes the score into one common exciter input. Four strings provide four manually tuned resonant voices; this does not create seventeen independently tuned resonators. Musical energy values are heuristic score features, not joules. Measured force, displacement and hydrophone data remain separate.</p>
<h2>Four fixed-string calibration targets</h2><table><thead><tr><th>Spelling</th><th>Target Hz</th><th>Offset cents</th><th>Source</th></tr></thead><tbody id="targets"></tbody></table>
<p><small>The v6 37-row comparison engine is also preserved and verified in the package. It has different spelling rules and interval targets; the two systems are not silently combined. The 68-event seeded Gen2 demonstration visits four distinct spellings, rather than all seventeen available labels. This is a wiring and replay demonstration, not a claim of musical diversity or physical performance.</small></p></main>
<script>
const engine=(()=>{__CORE__\nreturn {playNote,setSeed};})();
const score=__SCORE__;
const targets=document.querySelector('#targets');score.calibration_targets.forEach(t=>{const r=document.createElement('tr');[t.spelling+t.octave,t.target_Hz.toFixed(6),t.offset_cents.toFixed(6),t.engine_id+' / '+t.strategy].forEach(v=>{const d=document.createElement('td');d.textContent=v;r.append(d)});targets.append(r)});
let ctx=null,timers=[],started=0,duration=0,raf=0;
function stop(){timers.forEach(clearTimeout);timers=[];cancelAnimationFrame(raf);if(ctx){ctx.close();ctx=null}document.querySelector('#play').disabled=false;document.querySelector('#stop').disabled=true;document.querySelector('#status').textContent='Stopped. Hardware execution remains disabled.'}
function progress(){if(!ctx)return;const t=ctx.currentTime-started;document.querySelector('#progress').value=Math.min(1,t/duration);if(t<duration)raf=requestAnimationFrame(progress);else stop()}
document.querySelector('#play').onclick=async()=>{stop();const Audio=window.AudioContext||window.webkitAudioContext;if(!Audio){document.querySelector('#status').textContent='Web Audio unavailable in this browser.';return}ctx=new Audio();await ctx.resume();engine.setSeed(score.seed);const master=ctx.createGain(),lim=ctx.createDynamicsCompressor();master.gain.value=.15;lim.threshold.value=-12;lim.ratio.value=12;master.connect(lim);lim.connect(ctx.destination);started=ctx.currentTime;duration=Math.max(...score.events.map(e=>e.start_s+e.duration_s))+.5;document.querySelector('#play').disabled=true;document.querySelector('#stop').disabled=false;document.querySelector('#status').textContent='Playing recovered Gen2 note synthesis locally. No actuator commands.';for(const e of score.events){timers.push(setTimeout(()=>{if(!ctx)return;engine.playNote(ctx,master,e.target_Hz,e.previous_Hz,e.voice_type,e.source_amplitude,e.duration_s,e.phrase,e.source_pan,e.normalized_energy,e.energy_sigma,e.inverse_trace);document.querySelector('#event').textContent=e.voice_name+' / '+e.spelling+e.octave+' / '+e.target_Hz.toFixed(3)+' Hz / '+e.phrase},e.start_s*1000))}progress()};
document.querySelector('#stop').onclick=stop;
document.querySelector('#save').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(score,null,2)],{type:'application/json'}));a.download='instrument_score.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
globalThis.fusionAuditionCheck={schema:score.schema,eventCount:score.events.length,sourceSynthesis:typeof engine.playNote==='function',hardwareEnabled:false};
</script></html>'''
html=template.replace('__CORE__',core).replace('__SCORE__',score)
out=ROOT/'output/Dyletsky_Fusion_Audition.html';out.write_text(html)
assert '<script src' not in html and 'fetch(' not in html
print(json.dumps({'html':str(out),'bytes':out.stat().st_size,'external_dependencies':0}))
