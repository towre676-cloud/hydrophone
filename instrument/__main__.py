from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .run import load_json,analyze_run
from .drive import render_score
from .analyze import analyze_tones

def output(value,path):
    text=json.dumps(value,indent=2,allow_nan=False)+'\n'
    if path:
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
    else:sys.stdout.write(text)

def main():
    parser=argparse.ArgumentParser(description='Offline fusion instrument signals; no hardware commands')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('render');p.add_argument('score');p.add_argument('--wav',required=True);p.add_argument('--output')
    p.add_argument('--score-key',help='Explicit key such as score for a wrapped music CLI result');p.add_argument('--sample-rate',type=int,default=48000);p.add_argument('--peak',type=float,default=.2)
    p=sub.add_parser('tones');p.add_argument('wav');p.add_argument('--frequencies',type=float,nargs='+',required=True)
    p.add_argument('--drive-channel',type=int,default=0);p.add_argument('--response-channel',type=int,default=1)
    p.add_argument('--reference-channel',type=int);p.add_argument('--start',type=float,default=0);p.add_argument('--end',type=float);p.add_argument('--output')
    p=sub.add_parser('slow');p.add_argument('csv');p.add_argument('--position-tolerance',type=float);p.add_argument('--force-tolerance',type=float)
    p.add_argument('--hold-window',type=float,nargs=2);p.add_argument('--hold-drift',type=float);p.add_argument('--force-error',type=float);p.add_argument('--position-error',type=float);p.add_argument('--output')
    p=sub.add_parser('analyze-run');p.add_argument('manifest');p.add_argument('--output')
    p=sub.add_parser('demo');p.add_argument('--output-dir',default='results/instrument_demo')
    args=parser.parse_args()
    try:
        if args.command=='render':
            Path(args.wav).parent.mkdir(parents=True,exist_ok=True)
            score=load_json(args.score)
            if args.score_key:score=score[args.score_key]
            result=render_score(score,args.wav,sample_rate=args.sample_rate,peak=args.peak)
        elif args.command=='tones':
            result=analyze_tones(args.wav,drive_channel=args.drive_channel,response_channel=args.response_channel,
                reference_channel=args.reference_channel,frequencies_Hz=args.frequencies,start_s=args.start,end_s=args.end)
        elif args.command=='slow':
            from .slow import analyze_slow
            result=analyze_slow(args.csv,displacement_closure_tolerance_m=args.position_tolerance,
                force_return_tolerance_N=args.force_tolerance,hold_window_s=args.hold_window,
                max_hold_drift_m=args.hold_drift,force_error_N=args.force_error,displacement_error_m=args.position_error)
        elif args.command=='analyze-run':result=analyze_run(args.manifest)
        else:
            from .demo import demo
            result=demo(args.output_dir)
        output(result,getattr(args,'output',None));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        print(json.dumps({'status':'REJECTED','error':str(e),'hardware_execution_enabled':False}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
