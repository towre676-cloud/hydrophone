"""Deterministic adaptive score; reuses Hydrophone's sample renderer and MIDI writer."""
import argparse
import hashlib
import json
import math
import subprocess
import tempfile
import wave
from pathlib import Path
import numpy as np
from symphony.render import _render_pcm, validate_score, find_soundfont
from symphony.midi import write_midi

RATE = 32000
BPM = 100
BEAT = .6
BAR = 2.4
BARS = 16
FRAMES = round(BARS * BAR * RATE)
# Scale degrees, deliberately shared across every environment.
THEMES = {'ash':[0,2,3,7,5,3,2,0], 'water':[7,5,2,3,0,2,-1,0],
          'aether':[0,7,9,5,7,3,2,0]}
SCALE = [0,2,3,5,7,9,10]
CUES = {
 'exploration':('Roads That Remember','flute','harp',[0,5,3,4], 'water'),
 'settlement':('Lanterns at the Kiln','oboe','harp',[0,3,5,4], 'ash'),
 'interior':('Letters by the Stove','clarinet','celesta',[0,5,1,4], 'ash'),
 'dungeon':('The Well Below Names','bassoon','harp',[0,1,5,4], 'water'),
 'atmospheric':('A Sky of Unspoken Things','flute','celesta',[0,5,3,0], 'aether'),
 'combat':('Clay Against Iron','violin','timpani',[0,5,1,4], 'ash'),
 'boss':('The Furnace Remembers','horn','timpani',[0,1,3,4], 'aether'),
 'victory':('A Name Returned','trumpet','harp',[0,3,4,0], 'water')}

def pitch(degree, octave=62):
    q,r = divmod(degree,7)
    return octave + 12*q + SCALE[r]

def score(kind, variant=0, bars=BARS, ending=False):
    title,lead,color,roots,theme = CUES[kind]
    events=[]
    def note(stem, ins, bar, beat, dur, p, velocity):
        start=(bar*4+beat)*BEAT
        events.append(dict(start_s=round(start,6),duration_s=round(dur*BEAT,6),
            midi_pitch=p,velocity=velocity,instrument=ins,cents=0,stem=stem,
            vibrato_phase_rad=round((bar*7+beat)*.37,6),
            expression=[{'time':0,'value':.65},{'time':.22,'value':1},
                        {'time':.78,'value':.91},{'time':1,'value':.48}]))
    urgent=kind in ('combat','boss')
    for b in range(bars):
        root=roots[(b//2+variant)%4]
        if ending and b >= bars-2: root=4 if b==bars-2 else 0
        # Close voice-leading strings and a grounded bass; long breaths every fourth bar.
        chord=[pitch(root+i,50) for i in (0,2,4)]
        for p in chord: note('bed','strings',b,0,3.6,p,48+(b%4)*3)
        note('bed','cello',b,0,3.5,pitch(root,38),64)
        if urgent: note('bed','bass',b,2,1.7,pitch(root,26),72)
        # Three phrases: statement, answer, then development and return.
        motif=THEMES[theme]
        if variant==1: motif=list(reversed(motif))
        if variant==2: motif=[-x+7 for x in motif]
        if b%4 != 3 or urgent:
            count=4 if urgent else 2
            for j in range(count):
                deg=motif[(b*2+j)%8]
                if b>=8: deg=THEMES['water' if theme!='water' else 'ash'][(b+j)%8]
                if ending and b==bars-1: deg=0
                p=pitch(deg,62 if kind not in ('dungeon','interior') else 50)
                note('theme',lead,b,j*4/count,3.4/count,p,72+int(10*math.sin(math.pi*(b%8)/8)))
        # Independent counter-line; no uncoordinated timing jitter at a loop boundary.
        if b%4==3:
            for j in range(3): note('theme','oboe' if lead!='oboe' else 'flute',b,j, .8,pitch(root+4-j,62),60)
        count=8 if urgent else (4 if kind not in ('atmospheric','interior') else 2)
        for j in range(count):
            if color=='timpani':
                note('motion',color,b,j*4/count,.35,38 if j%2==0 else 45,62+(j%2)*10)
                note('motion','viola',b,j*4/count,.38,pitch(root+[0,4,2,4][j%4],50),60)
            else:
                note('motion',color,b,j*4/count,.8,pitch(root+[0,2,4,6,4,2,0,4][j%8],62),55+j%3*4)
        if kind=='boss' and b%4>=2:
            for p in chord: note('motion','trombone',b,0,1.4,p+12,74)
    return {'schema':'symphony.score/1','title':title+f' / {variant+1}',
            'tempo_bpm':BPM,'events':events,'themes':THEMES,'meter':[4,4],
            'duration_s':bars*BAR,'composition':'original authored thematic transformations'}

def write_wav(path,pcm):
    with wave.open(str(path),'wb') as f:
        f.setnchannels(2);f.setsampwidth(2);f.setframerate(RATE)
        f.writeframes(np.rint(np.clip(pcm,-1,1)*32767).astype('<i2').tobytes())

def loudness(path):
    p=subprocess.run(['ffmpeg','-hide_banner','-i',str(path),'-af',
        'loudnorm=I=-23:TP=-2:LRA=11:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
    return json.loads(p.stderr[p.stderr.rfind('{'):])

def render(events, frames, loop, bank):
    pcm,_=_render_pcm(validate_score({'schema':'symphony.score/1','events':events}),RATE,bank,tail_s=5)
    if loop:
        # Fold the complete release/room tail into the next cycle, preserving all attacks.
        out=np.zeros((frames,2),np.float32)
        for start in range(0,len(pcm),frames):
            part=pcm[start:start+frames]; out[:len(part)]+=part
        # Very short periodic correction removes DC/seam discontinuity without a silent gap.
        n=128; delta=out[-1]-out[0]
        out[-n:]-=np.linspace(0,1,n,dtype=np.float32)[:,None]*delta
        return out
    n=min(3200,len(pcm)//4)
    pcm[-n:]*=np.linspace(1,0,n,dtype=np.float32)[:,None]
    return pcm

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def build(out, events_only=False):
    out.mkdir(parents=True,exist_ok=True)
    for name in ('audio','scores','midi','masters'): (out/name).mkdir(exist_ok=True)
    bank=find_soundfont(); records=[]; checks=[]
    jobs=[(k,v,16,True) for k in CUES for v in range(3)]
    jobs += [(k,0,2,False) for k in ('victory','boss','interior','atmospheric')]
    jobs += [('exploration',0,4,False),('combat',0,4,False)]
    if events_only:
        records=json.loads((out/'manifest.json').read_text())['cues'][:24]
        checks=json.loads((out/'validation.json').read_text())['assets'][:72]
    event_names=['victory_sting','boss_arrival','rest','revelation','chapter_ending','combat_exit']
    with tempfile.TemporaryDirectory() as temp:
        temp=Path(temp)
        for index,(kind,v,bars,loop) in enumerate(jobs):
            if events_only and index<24: continue
            ident=f'{kind}_{v+1}' if loop else event_names[index-24]
            s=score(kind,v,bars,ending=not loop)
            (out/'scores'/f'{ident}.json').write_text(json.dumps(s,indent=2)+'\n')
            write_midi(s,out/'midi'/f'{ident}.mid')
            stems={}
            for stem in ('bed','theme','motion'):
                stems[stem]=render([e for e in s['events'] if e['stem']==stem],round(bars*BAR*RATE),loop,bank)
            length=max(map(len,stems.values()))
            stems={k:np.pad(p,((0,length-len(p)),(0,0))) for k,p in stems.items()}
            mix=sum(stems.values()); write_wav(temp/'measure.wav',mix)
            met=loudness(temp/'measure.wav'); gain=10**((-23-float(met['input_i']))/20)
            peak=float(np.max(np.abs(mix)))*gain
            if peak>.75: gain*=.75/peak
            stem_records={}
            for stem,pcm in stems.items():
                pcm=pcm*gain; wav=temp/f'{stem}.wav'; write_wav(wav,pcm)
                master=out/'masters'/f'{ident}_{stem}.flac'
                audio=out/'audio'/f'{ident}_{stem}.ogg'
                subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),str(temp/'master.flac')],check=True)
                pending=master.with_suffix('.pending');pending.write_bytes((temp/'master.flac').read_bytes());pending.replace(master)
                subprocess.run(['ffmpeg','-v','error','-y','-i',str(wav),'-fflags','+bitexact','-flags:a','+bitexact','-c:a','libvorbis','-q:a','5',str(temp/'delivery.ogg')],check=True)
                pending=audio.with_suffix('.pending');pending.write_bytes((temp/'delivery.ogg').read_bytes());pending.replace(audio)
                # Validate what the game decodes, not just the source WAV.
                raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(audio),'-f','f32le','-'])
                decoded=np.frombuffer(raw,'<f4').reshape(-1,2)
                jump=float(np.max(np.abs(decoded[-1]-decoded[0]))) if loop else 0
                checks.append({'asset':audio.name,'decoded_frames':len(decoded),
                    'expected_frames':length,'loop_jump':jump,'peak':float(np.max(np.abs(decoded))),
                    'passed':len(decoded)==length and np.max(np.abs(decoded))<.99 and jump<.02})
                stem_records[stem]={'file':f'audio/{audio.name}','sha256':digest(audio),
                    'master':f'masters/{master.name}','master_sha256':digest(master)}
            write_wav(temp/'measure.wav',sum(stems.values())*gain)
            measured=loudness(temp/'measure.wav')
            records.append({'id':ident,'category':kind,'title':s['title'],'variant':v,
                'loop':loop,'loop_start_frame':0,'loop_end_frame':length,'sample_rate':RATE,
                'duration_s':length/RATE,'bpm':BPM,'beats_per_bar':4,'bars':bars,
                'key':'D modal minor','stems':stem_records,'lufs':float(measured['input_i']),
                'true_peak_db':float(measured['input_tp']),'event_count':len(s['events'])})
            print(ident,length/RATE,measured['input_i'],flush=True)
    manifest={'schema':'aa.adaptive-score/1','title':'The Unfinished Song — Adaptive Orchestral Book I',
        'bpm':BPM,'bar_s':BAR,'sample_rate':RATE,'themes':THEMES,'cues':records,
        'gameplay_rules':[{'event':'battle.start','category':'combat','priority':80},{'event':'boss.start','category':'boss','priority':90,'sting':'boss_arrival'},{'event':'battle.win','sting':'victory_sting','return':'scene'},{'event':'discovery','sting':'revelation'},{'event':'story.transition','sting':'chapter_ending'},{'event':'rest','sting':'rest'},{'event':'dialogue','action':'duck existing music'},{'event':'pause_or_hidden','action':'pause preserving musical offset'}],
        'intensity_layers':{'calm':{'bed':1,'theme':.65,'motion':.15},
            'alert':{'bed':1,'theme':.85,'motion':.55},'danger':{'bed':1,'theme':1,'motion':1}},
        'transition':{'quantize':'bar','crossfade_s':BAR,'curve':'linear_constant_sum',
            'combat_max_wait_s':BAR,'variant_after_cycles':2,'no_immediate_repeat':True},
        'events':dict(zip(event_names,event_names)),
        'provenance':{'engine':'symphony.render sampled FluidSynth','soundfont_sha256':digest(bank),
            'original_20261024_compositions_modified':False}}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    report={'schema':'aa.audio-qa/1','assets':checks,'all_passed':all(c['passed'] for c in checks),
        'cue_count':len(records),'loop_count':24,'unique_loop_minutes':24*BARS*BAR/60,
        'lufs_range':[min(c['lufs'] for c in records),max(c['lufs'] for c in records)],
        'soundfont_sha256':digest(bank),'numpy':np.__version__}
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    if not report['all_passed']: raise RuntimeError('Audio validation failed; inspect validation.json')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=Path('music/aa-adaptive'))
    p.add_argument('--events-only',action='store_true',help='Rebuild only event endings against an existing book')
    args=p.parse_args();build(args.output_dir,args.events_only)
