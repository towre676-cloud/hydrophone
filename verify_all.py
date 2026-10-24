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
    run([sys.executable,'-m','unittest','discover','-s','hardware/calibration','-p','test_si_conversion.py','-v'])
    run([sys.executable,'-m','unittest','discover','-s','hardware/electronics','-p','test_t7*.py','-v'])
    run([sys.executable,'-m','unittest','discover','-s','hardware/readout','-p','test_*.py','-v'])
    run([sys.executable,'-m','unittest','discover','-s','hardware/commissioning','-p','test_*.py','-v'])
    with tempfile.TemporaryDirectory(prefix='hydrophone-replay-') as tmp:
        base=Path(tmp)
        run([sys.executable,'-m','evaluation','demo','--output-dir',base/'evaluation'])
        run([sys.executable,'-m','evaluation','probe','--wav',base/'history_probe.wav','--output',base/'history_probe.json'])
        run([sys.executable,'-m','evaluation','observability','--output',base/'history_observability.json'])
        run([sys.executable,'-m','instrument','demo','--output-dir',base/'raw_demo'])
        run([sys.executable,'-m','instrument','bench-demo','--output-dir',base/'bench_demo'])
        run([sys.executable,'-m','instrument','episode-commands',ROOT/'experiments/clay_tuning_v1/contract.json','--output-dir',base/'episode_commands'])
        mechanics=base/'mechanics';shutil.copytree(ROOT/'hardware/mechanics',mechanics)
        run([sys.executable,mechanics/'build.py'])
        run([sys.executable,mechanics/'drawing.py'])
        for name in ('params.scad','calculation_receipt.json','cut_list.csv','drill_table.csv','fabrication.svg'):
            if (mechanics/'generated'/name).read_bytes()!=(ROOT/'hardware/mechanics/generated'/name).read_bytes():
                raise ValueError('Mechanical generated file is stale: '+name)
        cad=shutil.which('openscad')
        if cad:run([cad,'-o',base/'assembly.csg',mechanics/'assembly.scad'])
        completion=base/'mechanics_completion';shutil.copytree(ROOT/'hardware/mechanics_completion',completion)
        run([sys.executable,completion/'build.py']);run([sys.executable,completion/'drawing.py'])
        run([sys.executable,completion/'retainers_guard/build.py'])
        generated=('generated/calculation_receipt.json','generated/cut_list.csv','generated/drill_table.csv',
            'generated/turning_table.csv','generated/M04_writer_section.svg',
            'retainers_guard/generated/cut_list.csv','retainers_guard/generated/drill_table.csv',
            'retainers_guard/generated/screening_receipt.json')
        for name in generated:
            if (completion/name).read_bytes()!=(ROOT/'hardware/mechanics_completion'/name).read_bytes():
                raise ValueError('M04 generated file is stale: '+name)
        if cad:run([cad,'-o',base/'M04_assembly.csg',completion/'assembly.scad'])
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
        'mechanical_generated_files_replayed':5,'openscad_syntax_checked':bool(cad),
        'M04_generated_files_replayed':8,
        'hardware_commands_issued':0,'physical_measurements_made':0}))

if __name__=='__main__':main()
