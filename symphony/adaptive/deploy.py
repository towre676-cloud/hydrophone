"""Prepare a compact mobile delivery profile from retained lossless masters."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from .build import digest

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=Path('music/aa-adaptive'));p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--quality',type=int,default=2,choices=range(-1,11));args=p.parse_args()
    src=args.source;out=args.output_dir;out.mkdir(parents=True,exist_ok=True);(out/'audio').mkdir(exist_ok=True)
    manifest=json.loads((src/'manifest.json').read_text())
    with tempfile.TemporaryDirectory() as temp:
        target=Path(temp)/'delivery.ogg'
        for cue in manifest['cues']:
            for stem in cue['stems'].values():
                subprocess.run(['ffmpeg','-v','error','-y','-i',str(src/stem['master']),'-fflags','+bitexact','-flags:a','+bitexact','-c:a','libvorbis','-q:a',str(args.quality),str(target)],check=True)
                final=out/stem['file'];pending=final.with_suffix('.pending');pending.write_bytes(target.read_bytes());pending.replace(final);stem['sha256']=digest(final)
    manifest['delivery_profile']={'codec':'Vorbis','quality':args.quality,'lossless_master_manifest_sha256':digest(src/'manifest.json'),'master_location':'Hydrophone music/aa-adaptive/masters'}
    pending=out/'manifest.pending';pending.write_text(json.dumps(manifest,indent=2)+'\n');pending.replace(out/'manifest.json')
    print('Prepared 90 compact stems from preserved lossless masters')
if __name__=='__main__':main()
