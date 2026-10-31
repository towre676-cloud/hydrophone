"""Measure actual decoded, summed delivery loudness independently of mastering."""
import argparse
import json
import tempfile
from pathlib import Path
from .validate import decode
from .build import write_wav,loudness

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=Path('music/aa-adaptive'));args=p.parse_args();r=args.root;m=json.loads((r/'manifest.json').read_text());rows=[]
 with tempfile.TemporaryDirectory() as temp:
  f=Path(temp)/'mix.wav'
  for c in m['cues']:
   write_wav(f,sum(decode(r/s['file']) for s in c['stems'].values()));v=loudness(f)
   rows.append({'id':c['id'],'decoded_lufs':float(v['input_i']),'decoded_true_peak_db':float(v['input_tp'])})
 span=[min(v['decoded_lufs'] for v in rows),max(v['decoded_lufs'] for v in rows)]
 report={'schema':'aa.decoded-loudness/1','cues':rows,'lufs_range':span,'spread_lu':span[1]-span[0],'passed':span[1]-span[0]<1 and all(v['decoded_true_peak_db']<-2 for v in rows)}
 (r/'decoded-loudness.json').write_text(json.dumps(report,indent=2)+'\n');print({k:v for k,v in report.items() if k!='cues'});assert report['passed']
if __name__=='__main__':main()
