"""Read a hash-bound raw run without converting metadata into physical proof."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from .analyze import analyze_tones


def load_json(path):
    def invalid(value):
        raise ValueError('Nonfinite JSON constant: '+value)
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=invalid)


def _bound_file(root, record):
    value=record.get('path')
    if not isinstance(value,str) or not value or Path(value).is_absolute():
        raise ValueError('Raw input paths must be relative to the run manifest')
    p=(root/value).resolve()
    if not p.is_relative_to(root.resolve()) or not p.is_file():
        raise ValueError('Raw input path escapes the run directory or is missing')
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    if record.get('sha256') != digest:
        raise ValueError('Raw input SHA256 mismatch: '+value)
    return p


def analyze_run(manifest_path):
    from .slow import analyze_slow
    path=Path(manifest_path).resolve(); run=load_json(path)
    if run.get('schema') not in ('fusion.run/1','hydrophone.signal-run/1'):
        raise ValueError('A canonical fusion.run/1 or compact hydrophone.signal-run/1 manifest is required')
    if run.get('data_origin') not in ('synthetic','physical_measurement'):
        raise ValueError('Run must explicitly declare synthetic or physical_measurement')
    if not isinstance(run.get('run_id'),str) or not run['run_id']:
        raise ValueError('A nonempty run_id is required')
    acquisition_audit=None
    canonical=run['schema']=='fusion.run/1'
    if canonical:
        from computing.acquisition import audit_run
        raw=run.get('raw_files')
        if not isinstance(raw,dict):
            raise ValueError('Canonical fusion.run/1 requires raw_files; use hydrophone.signal-run/1 for compact input')
        for role in ('multichannel_audio','slow_force_displacement','drive_command'):
            _bound_file(path.parent,raw[role])
        for role,record in raw.items():
            if role not in ('multichannel_audio','slow_force_displacement','drive_command'):
                _bound_file(path.parent,record)
        acquisition_audit=audit_run(path)
        analysis=run.get('analysis',{})
        cfg=analysis.get('tones')
        if not isinstance(cfg,dict) or not cfg.get('frequencies_Hz'):
            raise ValueError('Canonical run needs explicit analysis.tones.frequencies_Hz')
        cfg=dict(cfg); labels=run['audio']['channel_map']
        for role in ('drive_channel','response_channel','reference_channel'):
            if isinstance(cfg.get(role),str):
                if cfg[role] not in labels:raise ValueError('Unknown audio channel label: '+cfg[role])
                cfg[role]=labels.index(cfg[role])
        audio=dict(raw['multichannel_audio']);audio.update(cfg)
        slow=dict(raw['slow_force_displacement']);slow.update(analysis.get('slow',{}))
        slow.setdefault('time_column','logger_time_s')
    else:
        audio=run.get('audio'); slow=run.get('slow')
    if not isinstance(audio,dict) or not isinstance(slow,dict):
        raise ValueError('Audio and slow raw records are required')
    wav=_bound_file(path.parent,audio); csv=_bound_file(path.parent,slow)
    tone_args={k:audio[k] for k in ('drive_channel','response_channel','reference_channel','frequencies_Hz','start_s','end_s') if k in audio}
    tones=analyze_tones(wav,**tone_args)
    slow_args={k:slow[k] for k in ('displacement_closure_tolerance_m','force_return_tolerance_N','hold_window_s','max_hold_drift_m','force_error_N','displacement_error_m','time_column') if k in slow}
    mechanical=analyze_slow(csv,rod_state=run.get('rod_state','unknown'),
        calibration_declared=run.get('calibration',{}).get('slow_declared',False),**slow_args)
    return {'schema':'fusion.run-analysis/1','run_id':run['run_id'],
        'source_manifest_schema':run['schema'],'acquisition_audit':acquisition_audit,
        'source_manifest_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
        'data_origin_declared':run['data_origin'],
        'specimen_id':run.get('specimen_id'),'history_protocol':run.get('history_protocol'),
        'clock_alignment_declaration':run.get('sync') if canonical else run.get('clock_alignment'),
        'calibration_declaration':run.get('calibration'),
        'slow_pairing_declaration':run.get('slow_pairing_declaration'),
        'source_score_sha256':run.get('source_score_sha256'),
        'audio':tones,'slow':mechanical,
        'evidence_levels':{'raw_bytes_hash_checked':True,'features_computed':True,
            'laboratory_authenticity_verified':False,'clock_alignment_verified':False,
            'pressure_or_force_calibration_verified':False,'physical_model_certified':False},
        'hardware_execution_enabled':False,
        'limitations':['Manifest origin/calibration/clock fields are declarations, not authenticated measurements.',
            'Audio residuals are not deterministic model-error bounds.',
            'Slow sampled writer-port work is not identified clay dissipation.',
            'Force/position rows require qualified time pairing; clock alignment alone does not remove sensor/filter delays.',
            'No finite decision certificate may silently replace synthetic uncertainty with these diagnostics.']}
