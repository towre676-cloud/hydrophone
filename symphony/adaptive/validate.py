"""Validate decoded full-mix transitions and produce an eight-environment audition."""
import json
import argparse
import subprocess
from pathlib import Path
import numpy as np
from .build import RATE, BAR, write_wav, digest, loudness

def decode(path):
    return np.frombuffer(subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','f32le','-']),'<f4').reshape(-1,2)

def main(root=Path('music/aa-adaptive'),master_root=None):
    master_root=master_root or root
    manifest=json.loads((root/'manifest.json').read_text())
    mixes={};assets=[]
    for cue in manifest['cues']:
        parts=[]
        for stem in cue['stems'].values():
            path=root/stem['file'];pcm=decode(path);parts.append(pcm)
            assert digest(path)==stem['sha256'],str(path)+' digest mismatch'
            assert digest(master_root/stem['master'])==stem['master_sha256'],str(path)+' master digest mismatch'
            expected=round(cue['duration_s']*RATE)
            jump=float(np.max(np.abs(pcm[-1]-pcm[0]))) if cue['loop'] else 0
            assets.append({'asset':path.name,'decoded_frames':len(pcm),'expected_frames':expected,
                'loop_jump':jump,'peak':float(np.max(np.abs(pcm))),
                'passed':len(pcm)==expected and np.max(np.abs(pcm))<.99 and jump<.02})
            assert assets[-1]['passed'],str(path)+' failed delivered audio validation'
        mixes[cue['id']]=sum(parts)
    qa=json.loads((master_root/'validation.json').read_text());qa['assets']=assets;qa['all_passed']=all(a['passed'] for a in assets)
    qa['delivered_sha256_rechecked']=True
    (root/'validation.json').write_text(json.dumps(qa,indent=2)+'\n')
    loops=[c for c in manifest['cues'] if c['loop']];n=round(BAR*RATE);ramp=np.linspace(0,1,n)[:,None]
    rows=[]
    for a in loops:
        for b in loops:
            if a['id']==b['id']:continue
            x=mixes[a['id']];y=mixes[b['id']]
            # Handoff is allowed at every bar, including the wrapped last bar.
            peak=0;boundary=0
            for bar in range(16):
                start=bar*n;old=x[start:start+n];new=y[:n]
                z=old*(1-ramp)+new*ramp
                peak=max(peak,float(np.max(np.abs(z))))
                before=x[(start-1)%len(x)];after=y[n]
                boundary=max(boundary,float(np.max(np.abs(z[0]-before))),float(np.max(np.abs(after-z[-1]))))
            rows.append({'from':a['id'],'to':b['id'],'peak':peak,'boundary_step':boundary,'passed':peak<.99 and boundary<.12})
    # Test every delivered short cue over every delivered bed+theme+motion mix.
    event_peaks=[]
    for c in manifest['cues']:
        if c['loop']:continue
        event=mixes[c['id']]*.22
        for loop in loops:
            base=mixes[loop['id']][:len(event)]
            event_peaks.append(float(np.max(np.abs(base+event))))
    report={'schema':'aa.transition-qa/1','directed_transitions':len(rows),'bar_positions_per_transition':16,
        'transition_cases':len(rows)*16,'transitions':rows,'event_overlay_cases':len(event_peaks),
        'max_event_overlay_peak':max(event_peaks),'max_crossfade_peak':max(r['peak'] for r in rows),
        'max_boundary_step':max(r['boundary_step'] for r in rows),
        'all_passed':all(r['passed'] for r in rows) and max(event_peaks)<.99,
        'scope':'Decoded Vorbis, three-stem full-intensity sums, linear bar crossfades. Musical judgment requires listening.'}
    (root/'transition-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    audio=None
    for c in loops[::3]:
        excerpt=mixes[c['id']][:n*8].copy()
        if audio is None:audio=excerpt
        else:
            audio=np.concatenate([audio[:-n],audio[-n:]*(1-ramp)+excerpt[:n]*ramp,excerpt[n:]])
    audio[-RATE:]*=np.linspace(1,0,RATE)[:,None]
    write_wav(root/'audition.wav',audio)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(root/'audition.wav'),'-b:a','192k',str(root/'audition.mp3')],check=True)
    (root/'audition.wav').unlink()
    source_paths=['symphony/adaptive/build.py','symphony/adaptive/validate.py','symphony/adaptive/reproduce.py','symphony/adaptive/deploy.py','symphony/requirements.txt','symphony/render.py','symphony/midi.py','integration/aa/orchestral-soundtrack.js']
    receipt={'schema':'aa.build-receipt/1','source_sha256':{p:digest(Path(p)) for p in source_paths},
        'manifest_sha256':digest(root/'manifest.json'),'audio_validation_sha256':digest(root/'validation.json'),
        'transition_validation_sha256':digest(root/'transition-validation.json'),
        'rebuild':['python assets/symphony/fetch_soundfont.py --native-linux','python -m symphony.adaptive','python -m symphony.adaptive.validate'],
        'ffmpeg_version':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
        'numpy_version':np.__version__,'delivery_profile':manifest.get('delivery_profile',{'quality':5}),
        'original_compositions':'Unmodified; see music/README.md'}
    (root/'build-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='transitions'},indent=2))
    if not report['all_passed']:raise RuntimeError('Transition validation failed')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('music/aa-adaptive'));p.add_argument('--master-root',type=Path);args=p.parse_args();main(args.root,args.master_root)
