import json,subprocess,hashlib,tempfile
from pathlib import Path
import numpy as np
from symphony.adaptive.build import score,render,FRAMES,find_soundfont,write_wav,loudness
s=score('exploration',0);bank=find_soundfont()
parts={k:render([e for e in s['events'] if e['stem']==k],FRAMES,True,bank) for k in ('bed','theme','motion')}
with tempfile.TemporaryDirectory() as t:
 p=Path(t)/'mix.wav';mix=sum(parts.values());write_wav(p,mix);met=loudness(p);gain=10**((-23-float(met['input_i']))/20);peak=float(np.max(np.abs(mix)))*gain
 if peak>.75:gain*=.75/peak
 rows=[]
 for k,pcm in parts.items():
  raw=np.rint(np.clip(pcm*gain,-1,1)*32767).astype('<i2').tobytes()
  old=subprocess.check_output(['ffmpeg','-v','error','-i','music/aa-adaptive/masters/exploration_1_'+k+'.flac','-f','s16le','-'])
  rows.append({'stem':k,'pcm_sha256':hashlib.sha256(raw).hexdigest(),'repeat_pcm_byte_identical':raw==old})
 assert all(r['repeat_pcm_byte_identical'] for r in rows)
 Path('music/aa-adaptive/reproducibility.json').write_text(json.dumps({'full_arrangement':'exploration_1','stems':rows,'delivery_repeat_byte_identical':True,'scope':'Same pinned native environment; independent complete rerender of all three stems'},indent=2)+'\n')
print('Independent complete arrangement rerender: 3/3 PCM byte-identical')
