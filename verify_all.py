"""Verify the imported design and runnable computing layer without hardware."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parent

def run(args,cwd=ROOT):
    subprocess.run([str(x) for x in args],cwd=cwd,check=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--node',help='Optional Node executable for recovered-source parity replay')
    p.add_argument('--numerical',action='store_true',help='Also run independent algebra and passive model; needs numpy scipy matplotlib')
    args=p.parse_args()
    package=ROOT/'design/fusion_design'
    lines=(package/'MANIFEST.sha256').read_text().splitlines()
    for line in lines:
        digest,name=line.split('  ',1)
        if hashlib.sha256((package/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Imported design digest mismatch: '+name)
    run([sys.executable,'-m','unittest','discover','-s','tests','-v'])
    with tempfile.TemporaryDirectory(prefix='hydrophone-replay-') as tmp:
        base=Path(tmp)
        run([sys.executable,'-m','instrument','demo','--output-dir',base/'raw_demo'])
        core=base/'dyletsky';shutil.copytree(package/'dyletsky',core)
        run([sys.executable,core/'fusion_bridge.py','--score',core/'output/instrument_score.json'])
        if args.node:
            run([args.node,core/'verify_extraction.mjs'])
            run([args.node,core/'verify_audition.mjs'])
        if args.numerical:
            run([sys.executable,core/'verify_algebra.py'])
            model=base/'model';shutil.copytree(package/'model',model)
            run([sys.executable,model/'passive_instrument_model.py'])
    print(json.dumps({'status':'PASS','imported_payload_hashes':len(lines),
        'node_parity_replayed':bool(args.node),'numerical_replayed':args.numerical,
        'hardware_commands_issued':0,'physical_measurements_made':0}))

if __name__=='__main__':main()
