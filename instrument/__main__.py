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
    parser=argparse.ArgumentParser(description='Fusion instrument signals; device capture requires explicit --execute')
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
    p=sub.add_parser('bench-demo');p.add_argument('--output-dir',required=True)
    p=sub.add_parser('probe');p.add_argument('targets');p.add_argument('--output-dir',required=True)
    p.add_argument('--sample-rate',type=int,default=48000);p.add_argument('--peak',type=float,default=.01);p.add_argument('--plateau',type=float,default=8)
    p=sub.add_parser('episode-commands');p.add_argument('core');p.add_argument('--output-dir',required=True)
    p=sub.add_parser('capture');p.add_argument('probe');p.add_argument('--output-dir',required=True)
    p.add_argument('--device',type=int);p.add_argument('--commissioning-id');p.add_argument('--execute',action='store_true')
    p=sub.add_parser('devices',help='List optional PortAudio devices without starting a stream')
    p=sub.add_parser('clockfit');p.add_argument('markers');p.add_argument('--source-key',choices=['logger_time_s','drive_time_s'],required=True)
    p.add_argument('--error',required=True);p.add_argument('--source-pick-error',required=True);p.add_argument('--audio-pick-error',required=True)
    p.add_argument('--method',required=True);p.add_argument('--output',required=True)
    p=sub.add_parser('align-drive');p.add_argument('probe');p.add_argument('recording');p.add_argument('--output-dir',required=True)
    p.add_argument('--loopback-channel',type=int,default=2);p.add_argument('--min-delay',type=float,default=0)
    p.add_argument('--max-delay',type=float,default=.25);p.add_argument('--error',type=float,default=.001)
    p.add_argument('--source-pick-error',type=float,default=0);p.add_argument('--audio-pick-error',type=float)
    p=sub.add_parser('seal');p.add_argument('capture');p.add_argument('--slow',required=True);p.add_argument('--metadata',required=True)
    p.add_argument('--logger-clock',required=True);p.add_argument('--drive-clock',required=True);p.add_argument('--output-dir',required=True)
    for command in ('task-features','task-outcome'):
        p=sub.add_parser(command);p.add_argument('run');p.add_argument('--core',required=True)
        p.add_argument('--qualification',required=True);p.add_argument('--pitch-record',required=True)
        p.add_argument('--output-dir',required=True)
        if command=='task-features':p.add_argument('--metadata',required=True)
        else:p.add_argument('--action-record',required=True)
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
        elif args.command=='probe':
            from .probe import compile_probe
            result=compile_probe(args.targets,args.output_dir,sample_rate=args.sample_rate,peak=args.peak,plateau_s=args.plateau)
        elif args.command=='episode-commands':
            from .episode import compile_episode_commands
            result=compile_episode_commands(args.core,args.output_dir)
        elif args.command=='capture':
            from .capture import capture_probe
            result=capture_probe(args.probe,args.output_dir,execute=args.execute,device=args.device,commissioning_id=args.commissioning_id)
        elif args.command=='devices':
            try: import sounddevice as sd
            except ImportError: raise ValueError('Install optional hardware/requirements-capture.txt first') from None
            result={'devices':[dict(d) for d in sd.query_devices()],'hardware_commands_issued':0}
        elif args.command=='clockfit':
            from .synchronize import fit_clock
            result=fit_clock(args.markers,source_key=args.source_key,declared_error_s=args.error,
                source_pick_error_s=args.source_pick_error,audio_pick_error_s=args.audio_pick_error,method=args.method)
        elif args.command=='align-drive':
            from .align import align_drive
            result=align_drive(args.probe,args.recording,args.output_dir,loopback_channel=args.loopback_channel,
                min_delay_s=args.min_delay,max_delay_s=args.max_delay,declared_error_s=args.error,
                source_pick_error_s=args.source_pick_error,audio_pick_error_s=args.audio_pick_error)
        elif args.command=='seal':
            from .seal import seal_capture
            result=seal_capture(args.capture,args.slow,args.metadata,args.logger_clock,args.drive_clock,args.output_dir)
        elif args.command=='task-features':
            from .task_features import extract_features
            result=extract_features(args.run,args.core,args.qualification,args.pitch_record,args.metadata,args.output_dir)
        elif args.command=='task-outcome':
            from .task_features import extract_outcome
            result=extract_outcome(args.run,args.core,args.qualification,args.pitch_record,args.action_record,args.output_dir)
        elif args.command=='bench-demo':
            from .bench_demo import demo
            result=demo(args.output_dir)
        else:
            from .demo import demo
            result=demo(args.output_dir)
        output(result,getattr(args,'output',None));return 0
    except (ValueError,OSError,KeyError,TypeError) as e:
        print(json.dumps({'status':'REJECTED','error':str(e),'hardware_execution_enabled':False}),file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
