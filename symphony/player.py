"""A self-contained listening room for an actual rendered performance."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import mimetypes
from pathlib import Path
import shutil
import subprocess
import wave


def _overview(path, bins=240):
    """Small waveform preview from real PCM bytes; absent for compressed input."""
    try:
        with wave.open(str(path), "rb") as stream:
            frames, channels, width = stream.getnframes(), stream.getnchannels(), stream.getsampwidth()
            rate = stream.getframerate()
            if width not in (2, 3, 4) or not frames:
                return [], None
            result = []
            for index in range(bins):
                begin, end = frames * index // bins, frames * (index + 1) // bins
                stream.setpos(begin)
                raw = stream.readframes(end - begin)
                stride = max(1, (end - begin) // 64) * channels * width
                samples = [abs(int.from_bytes(raw[i:i + width], "little", signed=True))
                           for i in range(0, len(raw) - width + 1, stride)]
                result.append(round(max(samples, default=0) / 2 ** (8 * width - 1), 4))
            peak = max(result, default=1) or 1
            return [v / peak for v in result], frames / rate
    except (wave.Error, EOFError, OSError):
        return [], None


def _compressed_duration(path):
    """Use the renderer's optional FFmpeg toolchain for compressed-file duration."""
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    try:
        result = subprocess.run([executable, "-v", "error", "-show_entries", "format=duration",
                                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                                capture_output=True, text=True, timeout=15, check=True)
        duration = float(result.stdout.strip())
        return duration if math.isfinite(duration) and duration > 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def generate_player(score, audio_path, output_path, *, midi_path=None):
    """Embed audio, score animation and optional MIDI in one portable HTML file."""
    if score.get("schema") != "symphony.score/1":
        raise ValueError("Expected symphony.score/1")
    audio = Path(audio_path)
    if not audio.is_file():
        raise ValueError("Rendered audio is required for the listening room")
    audio_bytes = audio.read_bytes()
    if len(audio_bytes) < 16:
        raise ValueError("Nonempty rendered audio is required for the listening room")
    events = []
    for event in score.get("events", []):
        values = [float(event[key]) for key in ("start_s", "duration_s", "midi_pitch")]
        if not all(math.isfinite(value) for value in values) or values[0] < 0 or values[1] <= 0:
            raise ValueError("Invalid performed event")
        velocity = float(event.get("velocity", 0.7))
        events.append({"t": values[0], "d": values[1], "p": values[2],
                       "i": str(event.get("instrument", "strings")),
                       "v": velocity / 127 if velocity > 1 else velocity,
                       "r": str(event.get("role", ""))})
    if not events:
        raise ValueError("A listening room requires performed events")
    events.sort(key=lambda event: event["t"])
    waveform, duration = _overview(audio)
    duration = duration or _compressed_duration(audio) or max(event["t"] + event["d"] for event in events)
    sections = []
    for section in score.get("sections", []):
        if not isinstance(section, dict) or "start_s" not in section:
            continue
        start = float(section["start_s"])
        if start >= duration:
            continue
        sections.append({"t": max(0, start),
                         "e": min(duration, float(section.get("end_s", duration))),
                         "name": str(section.get("title", section.get("name", section.get("label", "Movement"))))})
    sections.sort(key=lambda section: section["t"])
    if not sections:
        sections = [{"t": 0, "e": duration, "name": "A continuous performance"}]
    instruments = list(dict.fromkeys(event["i"] for event in events))
    payload = {"events": events, "sections": sections, "instruments": instruments,
               "duration": duration, "waveform": waveform}
    encoded = json.dumps(payload, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    mime = mimetypes.guess_type(audio.name)[0] or "audio/wav"
    audio_data = base64.b64encode(audio_bytes).decode("ascii")
    audio_uri = "data:" + mime + ";base64," + audio_data
    title = html.escape(str(score.get("title", "Where the water remembers")))
    subtitle = html.escape(str(score.get("subtitle", "An original orchestral performance")))
    midi_link = ""
    if midi_path is not None:
        midi = Path(midi_path)
        if not midi.is_file():
            raise ValueError("Requested MIDI download does not exist")
        midi_link = '<a class="download" download="' + html.escape(midi.name, quote=True) + '" href="data:audio/midi;base64,' + base64.b64encode(midi.read_bytes()).decode("ascii") + '">Download MIDI <span>↗</span></a>'
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    page = _PAGE.replace("__TITLE__", title).replace("__SUBTITLE__", subtitle)
    page = page.replace("__DATA__", encoded).replace("__AUDIO_URI__", audio_uri)
    page = page.replace("__AUDIO_NAME__", html.escape(audio.name, quote=True)).replace("__MIDI_LINK__", midi_link)
    page = page.replace("__NOTE_COUNT__", f"{len(events):,}").replace("__SECTION_COUNT__", str(len(instruments)))
    output.write_text(page, encoding="utf-8")
    return {"schema": "symphony.listening-room/1", "path": str(output), "self_contained": True,
            "audio_embedded": True, "audio_sha256": hashlib.sha256(audio_bytes).hexdigest(),
            "events": len(events), "sections": len(instruments), "duration_s": duration,
            "midi_embedded": midi_path is not None,
            "controls": ["play_pause", "restart", "seek", "volume", "playback_speed", "loop"],
            "physical_hardware_control": False}


_PAGE = r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · Hydrophone</title>
<style>
:root{color-scheme:dark;--ink:#07151d;--panel:#0c202b;--line:#ffffff17;--cream:#f0e6ce;--muted:#90a8ac;--gold:#e8c783;--teal:#72c4be}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 76% -12%,#29454b 0,transparent 51%),radial-gradient(ellipse at 10% 80%,#0d2b37 0,transparent 55%),#07151d;color:var(--cream);font-family:Inter,ui-sans-serif,system-ui,sans-serif;min-height:100vh}button,input,select{font:inherit}button,a,input,select{-webkit-tap-highlight-color:transparent}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--gold);outline-offset:5px}button{cursor:pointer}main{max-width:1440px;margin:auto;padding:32px 44px 35px}.mast{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:23px}.brand{font-size:12px;letter-spacing:.23em;display:flex;gap:13px;align-items:center}.sigil{width:29px;height:29px;color:var(--gold)}.edition{font-size:10px;letter-spacing:.16em;color:var(--muted)}header{padding:45px 0 30px;display:flex;justify-content:space-between;gap:40px;align-items:flex-end}.eyebrow{color:var(--gold);font-size:10px;letter-spacing:.23em;text-transform:uppercase;margin-bottom:15px}h1{font-family:Georgia,'Times New Roman',serif;font-size:clamp(35px,4.1vw,65px);font-weight:400;letter-spacing:-.035em;line-height:1.06;margin:0;max-width:1000px}.subtitle{color:var(--muted);font-size:13px;line-height:1.6;margin:16px 0 0}.stats{display:flex;gap:32px;padding-bottom:4px;flex-shrink:0}.stats strong{font-family:Georgia,serif;font-size:24px;font-weight:400;display:block}.stats span{display:block;color:var(--muted);font-size:9px;letter-spacing:.14em;text-transform:uppercase;margin-top:7px}.stage{height:340px;position:relative;border:1px solid var(--line);border-radius:18px 18px 0 0;overflow:hidden;background:radial-gradient(ellipse at 50% 20%,#163744 0%,#0b202b 64%,#091b24 100%)}canvas{display:block;width:100%;height:100%}.stage-top{position:absolute;top:24px;left:27px;right:27px;display:flex;justify-content:space-between;align-items:flex-start;pointer-events:none}.now{font-family:Georgia,serif;font-size:21px;margin-top:7px;letter-spacing:-.01em}.tiny{font-size:9px;letter-spacing:.19em;color:var(--muted);text-transform:uppercase}.live{display:flex;align-items:center;gap:8px;color:var(--teal);font-size:10px;letter-spacing:.05em}.live i{width:5px;height:5px;border-radius:50%;background:currentColor;box-shadow:0 0 14px currentColor}.stage-note{position:absolute;bottom:20px;left:27px;color:#91a9ae;font-size:10px;letter-spacing:.06em}.stage-time{position:absolute;bottom:19px;right:27px;color:#bdd0d0;font:11px ui-monospace,monospace}.transport{border:1px solid var(--line);border-top:0;border-radius:0 0 18px 18px;background:#0c202acc;padding:23px 26px;backdrop-filter:blur(15px)}.controls{display:flex;align-items:center;gap:18px}.play{width:56px;height:56px;border:0;border-radius:50%;background:var(--gold);color:#112029;display:grid;place-items:center;flex-shrink:0;box-shadow:0 0 40px #e8c78313}.play:hover{background:#f6dba4}.play svg{width:21px;height:21px}.plain{color:var(--muted);border:0;background:none;padding:8px;display:grid;place-items:center}.plain:hover{color:var(--cream)}.plain svg{width:17px;height:17px}.seek-wrap{flex:1;position:relative;height:50px;min-width:100px}.waveform{position:absolute;inset:0;pointer-events:none;opacity:.7}.seek{position:absolute;left:0;top:0;width:100%;height:50px;margin:0;appearance:none;background:transparent;cursor:pointer}.seek::-webkit-slider-runnable-track{height:1px;background:#d9c89a30}.seek::-moz-range-track{height:1px;background:#d9c89a30}.seek::-webkit-slider-thumb{appearance:none;background:var(--gold);height:36px;width:2px;border-radius:0;margin-top:-17px;box-shadow:0 0 15px #e8c78350}.seek::-moz-range-thumb{background:var(--gold);height:36px;width:2px;border:0;border-radius:0}.clock{font:10px ui-monospace,monospace;color:#a5b9bc;white-space:nowrap;min-width:91px;text-align:center}.right-controls{display:flex;align-items:center;gap:16px;padding-left:6px}.volume{width:72px;accent-color:var(--gold);height:3px}.speed{background:#ffffff07;border:1px solid var(--line);color:var(--muted);font-size:10px;border-radius:6px;padding:7px 8px}.loop[aria-pressed=true]{color:var(--gold)}.timeline{display:flex;gap:6px;margin-top:20px}.chapter{height:27px;flex:1;border:0;border-radius:4px;background:#ffffff04;text-align:left;overflow:hidden;color:#7b979f;font-size:9px;letter-spacing:.04em;padding:0 10px;white-space:nowrap;text-overflow:ellipsis;transition:background .2s,color .2s}.chapter:hover{background:#ffffff0c}.chapter.active{background:#e8c78310;color:var(--gold)}.below{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:20px;margin-top:22px}.score-panel,.ensemble{border:1px solid var(--line);border-radius:14px;background:#0c20264d;overflow:hidden}.panel-title{font-size:9px;letter-spacing:.17em;text-transform:uppercase;color:var(--muted);display:flex;justify-content:space-between;padding:18px 20px 0}.score-canvas{height:152px;margin-top:6px}.ensemble{padding-bottom:14px}.instruments{display:grid;grid-template-columns:1fr 1fr;gap:11px 13px;padding:22px 20px 4px}.instrument{font-size:10px;color:#6c8992;display:flex;gap:8px;align-items:center;transition:color .15s}.instrument .dot{width:4px;height:4px;border-radius:50%;background:currentColor;opacity:.4}.instrument.active{color:var(--gold)}.instrument.active .dot{opacity:1;box-shadow:0 0 8px currentColor}footer{display:flex;justify-content:space-between;align-items:center;gap:20px;padding-top:28px;color:#67858f;font-size:10px;line-height:1.7}.downloads{display:flex;gap:24px;flex-shrink:0}.download{color:#9eb6b9;text-decoration:none}.download:hover{color:var(--cream)}.download span{color:var(--gold);padding-left:8px}.error{display:none;color:#e9b39c;font-size:12px;padding-top:14px}.sr{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:900px){main{padding:24px}header{display:block;padding-top:33px}.stats{margin-top:25px}.stage{height:320px}.right-controls{gap:10px}.volume{width:45px}.below{grid-template-columns:1fr}.ensemble .instruments{grid-template-columns:repeat(4,1fr)}footer{align-items:flex-start}.edition{display:none}}
@media(max-width:600px){main{padding:18px 14px}.mast{padding-bottom:18px}.brand{font-size:10px}.stage{height:290px}.stage-top{left:20px;top:20px}.now{font-size:18px}.transport{padding:18px 15px}.controls{gap:10px}.play{width:46px;height:46px}.clock{min-width:75px;font-size:9px}.volume,.volume-icon,.speed{display:none}.right-controls{gap:0;padding:0}.timeline{gap:3px}.chapter{font-size:8px;padding:0 6px}.stats{gap:25px}.stats strong{font-size:21px}.ensemble .instruments{grid-template-columns:repeat(3,1fr)}footer{display:block;padding-top:22px}.downloads{margin-top:15px}.stage-note{font-size:8px;left:20px}.live{font-size:8px}.stage-time{right:20px}.panel-title{padding:17px 16px 0}h1{font-size:39px}.subtitle{font-size:12px}}
</style></head><body><main>
<nav class="mast"><div class="brand"><svg class="sigil" viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M3 16c4-13 8 13 12 0s8 13 14 0M3 24c4-13 8 13 12 0s8 13 14 0M3 8c4-13 8 13 12 0s8 13 14 0" stroke="currentColor" stroke-width="1.2"/></svg>HYDROPHONE <span style="color:#597985">/</span> LISTENING ROOM</div><div class="edition">AN INSTRUMENT FOR REMEMBERING</div></nav>
<header><div><div class="eyebrow">An original orchestral work</div><h1>__TITLE__</h1><p class="subtitle">__SUBTITLE__</p></div><div class="stats"><div><strong>__SECTION_COUNT__</strong><span>Orchestral voices</span></div><div><strong>__NOTE_COUNT__</strong><span>Performed notes</span></div></div></header>
<section class="stage" aria-label="Orchestra visualization"><canvas id="stage"></canvas><div class="stage-top"><div><div class="tiny">Now playing</div><div class="now" id="chapterName">A moment before the first note</div></div><div class="live"><i></i><span id="state">READY TO LISTEN</span></div></div><div class="stage-note">A living score · light follows the performed notes</div><div class="stage-time" id="stageClock">00:00</div></section>
<section class="transport" aria-label="Playback controls"><div class="controls"><button id="play" class="play" aria-label="Play"><svg id="playIcon" viewBox="0 0 24 24" fill="currentColor"><path d="M8 4v16l13-8z"/></svg></button><button id="restart" class="plain" aria-label="Restart"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 10a8 8 0 1 1 1 8M4 4v6h6"/></svg></button><div class="seek-wrap"><canvas id="waveform" class="waveform"></canvas><label class="sr" for="seek">Playback position</label><input id="seek" class="seek" type="range" min="0" max="1" value="0" step="0.01"></div><span class="clock" id="clock">00:00 / 00:00</span><div class="right-controls"><svg class="volume-icon" style="width:15px;height:15px;color:#90a8ac" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4zM16 8c3 2 3 6 0 8M19 5c5 4 5 10 0 14"/></svg><label class="sr" for="volume">Volume</label><input id="volume" class="volume" type="range" min="0" max="1" step="0.01" value="0.8"><label class="sr" for="speed">Playback speed</label><select id="speed" class="speed"><option value="0.75">0.75×</option><option value="0.9">0.9×</option><option value="1" selected>1×</option><option value="1.1">1.1×</option><option value="1.25">1.25×</option></select><button id="loop" class="plain loop" aria-label="Loop performance" aria-pressed="false"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 9V6h14l3 3-3 3M20 15v3H6l-3-3 3-3"/></svg></button></div></div><div class="timeline" id="chapters" aria-label="Musical sections"></div><div id="error" class="error" role="alert"></div></section>
<div class="below"><section class="score-panel" aria-label="Live score"><div class="panel-title"><span>The unfolding score</span><span id="voiceCount">0 active notes</span></div><div class="score-canvas"><canvas id="score"></canvas></div></section><section class="ensemble"><div class="panel-title"><span>Inside the orchestra</span></div><div class="instruments" id="instruments"></div></section></div>
<footer><div>Original composition · digital orchestral performance<br>MIDI downloads use standard note tuning.</div><div class="downloads"><a id="audioDownload" class="download" download="__AUDIO_NAME__" href="#">Download audio <span>↗</span></a>__MIDI_LINK__</div></footer>
<audio id="audio" preload="metadata" src="__AUDIO_URI__"></audio>
</main><script>
"use strict";
const data=__DATA__;
const audio=document.getElementById('audio'),play=document.getElementById('play'),seek=document.getElementById('seek');
document.getElementById('audioDownload').href=audio.src;
const fmt=t=>{t=Math.max(0,Math.floor(t||0));return String(Math.floor(t/60)).padStart(2,'0')+':'+String(t%60).padStart(2,'0')};
const instrumentNames={violin:'First violins',violin2:'Second violins',viola:'Violas',cello:'Cellos',bass:'Double basses',contrabass:'Double basses',horn:'Horns',trumpet:'Trumpets',flute:'Flutes',oboe:'Oboes',clarinet:'Clarinets',bassoon:'Bassoons'};
const pretty=s=>instrumentNames[s]||s.replaceAll('_',' ').replace(/\b\w/g,c=>c.toUpperCase());
const colors=['#e8c783','#72c4be','#c9a6cb','#e8ae8c','#84aacd','#d6d4b0','#b1c589','#b8a0d2','#e5b899','#7fbbbd','#d9c178','#95aabd','#c99d99','#aab78a','#b5c9c6'];
const color=i=>colors[data.instruments.indexOf(i)%colors.length];
let total=data.duration;audio.volume=.8;
const instruments=document.getElementById('instruments');const lights={};
data.instruments.forEach(name=>{const node=document.createElement('div');node.className='instrument';const dot=document.createElement('i');dot.className='dot';node.append(dot,document.createTextNode(pretty(name)));instruments.append(node);lights[name]=node});
const chapters=document.getElementById('chapters');const chapterButtons=data.sections.map((s,i)=>{const b=document.createElement('button');b.className='chapter';b.textContent=s.name;b.title=s.name;b.addEventListener('click',()=>{audio.currentTime=s.t;update()});chapters.append(b);return b});
play.addEventListener('click',async()=>{if(audio.paused){try{await audio.play()}catch(e){const box=document.getElementById('error');box.textContent='Playback could not start. Try the audio download below in your music player.';box.style.display='block'}}else audio.pause()});
document.getElementById('restart').addEventListener('click',()=>{audio.currentTime=0;update()});
document.getElementById('volume').addEventListener('input',e=>audio.volume=Number(e.target.value));
document.getElementById('speed').addEventListener('change',e=>audio.playbackRate=Number(e.target.value));
document.getElementById('loop').addEventListener('click',e=>{audio.loop=!audio.loop;e.currentTarget.setAttribute('aria-pressed',String(audio.loop))});
seek.addEventListener('input',()=>{audio.currentTime=Number(seek.value);update()});
audio.addEventListener('loadedmetadata',()=>{if(Number.isFinite(audio.duration))total=audio.duration;seek.max=String(total);update()});
audio.addEventListener('error',()=>{const box=document.getElementById('error');box.textContent='This browser could not decode the embedded performance. Use Download audio to open it in a music player.';box.style.display='block'});
['play','pause','ended'].forEach(type=>audio.addEventListener(type,()=>{document.getElementById('playIcon').innerHTML=audio.paused?'<path d="M8 4v16l13-8z"/>':'<path d="M6 4h4v16H6zM15 4h4v16h-4z"/>';play.setAttribute('aria-label',audio.paused?'Play':'Pause');document.getElementById('state').textContent=audio.paused?'PAUSED':'PERFORMING';update()}));
seek.max=String(total);
const canvasIds=['stage','score','waveform'];const contexts={};let last=-1;
function resize(){canvasIds.forEach(id=>{const c=document.getElementById(id),rect=c.getBoundingClientRect(),ratio=Math.min(2,window.devicePixelRatio||1);c.width=Math.max(1,Math.round(rect.width*ratio));c.height=Math.max(1,Math.round(rect.height*ratio));contexts[id]={c,ctx:c.getContext('2d'),w:rect.width,h:rect.height,ratio}});last=-1}
window.addEventListener('resize',resize);resize();
function setup(id){const q=contexts[id];q.ctx.setTransform(q.ratio,0,0,q.ratio,0,0);q.ctx.clearRect(0,0,q.w,q.h);return q}
function activeAt(t){return data.events.filter(e=>e.t<=t&&e.t+e.d>t)}
function update(){const t=audio.currentTime||0;document.getElementById('clock').textContent=fmt(t)+' / '+fmt(total);document.getElementById('stageClock').textContent=fmt(t);seek.value=String(t);let found=0;data.sections.forEach((s,i)=>{if(t>=s.t)found=i});document.getElementById('chapterName').textContent=data.sections[found]?.name||'A continuous performance';chapterButtons.forEach((b,i)=>b.classList.toggle('active',i===found))}
function drawStage(t,active){const{ctx,w,h}=setup('stage');const compact=w<600;const cx=w*.5,cy=h*.77,rx=w*.34,ry=h*.5;ctx.lineWidth=1;for(let ring=0;ring<5;ring++){ctx.beginPath();ctx.ellipse(cx,cy,rx*(.5+ring*.15),ry*(.5+ring*.15),0,Math.PI,Math.PI*2);ctx.strokeStyle='#91b2ba0b';ctx.stroke()}const energy={};active.forEach(e=>energy[e.i]=(energy[e.i]||0)+e.v*Math.sin(Math.PI*Math.min(1,(t-e.t)/Math.max(.01,e.d))));data.instruments.forEach((name,i)=>{const angle=Math.PI+(i+.5)/data.instruments.length*Math.PI;const x=cx+Math.cos(angle)*rx,y=cy+Math.sin(angle)*ry*.77;const e=Math.min(1,(energy[name]||0)/3);for(let seat=0;seat<(compact?3:5);seat++){const delta=seat-(compact?1:2),sx=x+delta*(compact?4:9),sy=y+Math.abs(delta)*(compact?3:4);ctx.beginPath();ctx.arc(sx,sy,(compact?1.8:2.5)+e*(compact?1.4:2),0,Math.PI*2);ctx.fillStyle=e?color(name):'#48616b';ctx.globalAlpha=.35+.65*e;ctx.shadowColor=color(name);ctx.shadowBlur=e*20;ctx.fill()}ctx.globalAlpha=1;ctx.shadowBlur=0;ctx.fillStyle=e?'#e3d7bd':'#62818c';ctx.font='9px system-ui';ctx.textAlign='center';if(!compact)ctx.fillText(pretty(name),x,y+24)});ctx.beginPath();ctx.ellipse(cx,cy+5,16,4,0,0,Math.PI*2);ctx.fillStyle='#e8c7830c';ctx.fill();ctx.strokeStyle='#e8c78372';ctx.lineWidth=1.3;ctx.beginPath();ctx.moveTo(cx-4,cy-8);ctx.lineTo(cx,cy-26);ctx.lineTo(cx+5,cy-8);ctx.moveTo(cx-12,cy-22);ctx.quadraticCurveTo(cx,cy-10,cx+13,cy-24);ctx.stroke();const motion=audio.paused?0:Math.sin(t*1.8);ctx.beginPath();ctx.moveTo(cx+12,cy-23);ctx.lineTo(cx+24+motion*3,cy-37+motion*5);ctx.strokeStyle='#e8c783';ctx.stroke();const wash=ctx.createRadialGradient(cx,cy-50,0,cx,cy-50,150);wash.addColorStop(0,'#71c4bd09');wash.addColorStop(1,'#71c4bd00');ctx.fillStyle=wash;ctx.fillRect(0,0,w,h)}
function drawScore(t){const{ctx,w,h}=setup('score');const before=2,span=16,lo=32,hi=96;for(let p=36;p<=96;p+=12){const y=h-12-(p-lo)/(hi-lo)*(h-22);ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.strokeStyle='#a4c4cb0c';ctx.stroke()}data.events.forEach(e=>{if(e.t+e.d<t-before||e.t>t+span-before)return;const x=(e.t-t+before)/span*w,nw=Math.max(2,e.d/span*w),y=h-12-(e.p-lo)/(hi-lo)*(h-22);ctx.fillStyle=color(e.i);ctx.globalAlpha=e.t<=t&&e.t+e.d>t?.95:.22+e.v*.2;ctx.beginPath();if(ctx.roundRect)ctx.roundRect(x,y-2,nw,3.2,1.6);else ctx.rect(x,y-2,nw,3.2);ctx.fill()});ctx.globalAlpha=1;ctx.beginPath();ctx.moveTo(before/span*w,3);ctx.lineTo(before/span*w,h);ctx.strokeStyle='#ead6aa65';ctx.stroke()}
function drawWave(t){const{ctx,w,h}=setup('waveform');const bins=data.waveform.length;if(!bins)return;const step=w/bins;data.waveform.forEach((v,i)=>{const bh=Math.max(2,Math.pow(v,.65)*(h-6));ctx.fillStyle=i/bins<=t/total?'#e8c78396':'#708c963d';ctx.fillRect(i*step,h/2-bh/2,Math.max(1,step*.52),bh)})}
function frame(){const t=audio.currentTime||0;if(t!==last||last<0){const active=activeAt(t);drawStage(t,active);drawScore(t);drawWave(t);const names=new Set(active.map(e=>e.i));data.instruments.forEach(name=>lights[name].classList.toggle('active',names.has(name)));document.getElementById('voiceCount').textContent=active.length+' active note'+(active.length===1?'':'s');update();last=t}requestAnimationFrame(frame)}update();frame();
</script></body></html>'''
