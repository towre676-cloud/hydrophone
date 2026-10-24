"""Join recorded audio, imported slow data and measured timing declarations."""
import csv
import json
from pathlib import Path
import shutil
import wave
from .probe import load_probe, sha256
from .run import _bound_file, load_json
from .synchronize import fraction, read_clock, mapped_window


def seal_capture(capture_path, slow_path, metadata_path, logger_clock_path,
                 drive_clock_path, output_dir):
    """Create a canonical fusion.run/1 without replacing or editing raw bytes.

    This joins evidence and audits it. It does not certify origin, calibration,
    clock interpolation, model validity or physical memory.
    """
    from computing.acquisition import audit_run
    capture_path = Path(capture_path).resolve()
    capture = load_json(capture_path)
    if (capture.get('schema') != 'hydrophone.capture/1' or
        capture.get('status') != 'COMPLETE_NO_HOST_FLAGS' or
        capture.get('missing_samples') != 0 or capture.get('host_flags') or
        capture.get('callback_error') or capture.get('stream_error') or
        capture.get('frames_received') != capture.get('frames_requested')):
        raise ValueError('Only complete unflagged captures can be sealed')
    probe_path = capture_path.parent/'probe.json'
    if sha256(probe_path) != capture['probe_sha256']:
        raise ValueError('Capture probe SHA256 mismatch')
    plan,_,command = load_probe(probe_path)
    audio = _bound_file(capture_path.parent, capture['raw_files']['multichannel_audio'])
    drive = _bound_file(capture_path.parent, capture['raw_files']['drive_command'])
    if sha256(command) != sha256(drive):
        raise ValueError('Recorded drive command differs from probe')
    if capture['channel_map'] != plan['input_channel_map'] or capture['sample_rate_Hz'] != plan['sample_rate_Hz']:
        raise ValueError('Capture channel/sample-rate metadata contradicts probe')
    with wave.open(str(audio), 'rb') as stream:
        if (stream.getnframes() != plan['frames'] or capture['frames_requested'] != plan['frames'] or
            stream.getsampwidth() != 2 or stream.getnchannels() != len(capture['channel_map']) or
            stream.getframerate() != plan['sample_rate_Hz']):
            raise ValueError('Actual audio format/frame count contradicts capture and probe')
    metadata = load_json(metadata_path)
    for key in ('run_id','specimen_id','history_protocol','calibration_id','validity_domain','rod_state'):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ValueError('Need explicit operator metadata: '+key)
    if metadata.get('data_origin') not in ('synthetic','physical_measurement'):
        raise ValueError('Operator must declare data origin')
    native_records = metadata.get('native_slow_raw_files', [])
    if not isinstance(native_records, list):
        raise ValueError('native_slow_raw_files must be a list of path/SHA256 records')
    native_paths = [(record, _bound_file(Path(metadata_path).resolve().parent, record)) for record in native_records]
    if metadata['data_origin'] == 'physical_measurement':
        for key in ('configuration_id','mechanics_revision','electronics_revision','cartridge_batch',
                    'preparation_order','operator_id','timestamp_utc'):
            if not isinstance(metadata.get(key),str) or not metadata[key].strip() or metadata[key] == 'REPLACE':
                raise ValueError('Physical record requires completed setup identity: '+key)
        if metadata.get('template_status') == 'UNFILLED_NOT_A_PHYSICAL_RECORD' or not native_paths:
            raise ValueError('Physical record requires completed metadata and native slow raw evidence')
        conditions = metadata.get('conditions')
        required = ('tank_state','cartridge_state','water_depth_m','water_temperature_C','room_temperature_C',
            'hydrophone_xyz_m','hydrophone_orientation','bridge_preload_N','string_tuning_before_Hz',
            'string_tuning_after_Hz','elapsed_since_write_s','reader_displacement_peak_m_measured',
            'sensor_mount_id','carrier_zero_position_m')
        if not isinstance(conditions,dict) or any(conditions.get(key) is None for key in required):
            raise ValueError('Physical record requires explicit setup conditions, including applicable unavailable values')
        pairing = metadata.get('slow_pairing')
        if not isinstance(pairing,dict) or any(not pairing.get(key) for key in
                ('scope','per_channel_sample_offsets','filter_configuration','delay_correction_status')):
            raise ValueError('Physical slow record requires channel-offset/filter/pairing declarations')
    labels = capture['channel_map']
    gains = metadata.get('gain_per_channel')
    if (not isinstance(gains, list) or len(gains) != len(labels) or
        any(fraction(g,'gain') <= 0 for g in gains)):
        raise ValueError('Every channel requires a positive operator-declared linear gain')
    for key in ('drive_channel','response_channel','reference_channel'):
        if metadata.get(key) not in labels:
            raise ValueError('Need explicit channel role: '+key)
    if len({metadata[k] for k in ('drive_channel','response_channel','reference_channel')}) != 3:
        raise ValueError('Drive, response and reference must use different channels')
    logger_clock = read_clock(logger_clock_path, 'logger_time_s')
    drive_clock = read_clock(drive_clock_path, 'drive_time_s')
    start,end,error = mapped_window(drive_clock, *plan['fit_dac_window_s'])
    on,off,_ = mapped_window(drive_clock, *plan['stimulus_dac_window_s'])
    duration = capture['frames_received']/capture['sample_rate_Hz']
    if not 0 <= start-error < start < end < end+error <= duration:
        # Zero declared timing error is permitted for explicit synthetic input.
        if error != 0 or not 0 <= start < end <= duration:
            raise ValueError('Mapped fit window/uncertainty leaves audio recording')
    if start-error <= on+error or end+error >= off-error:
        raise ValueError('Timing allowance brings fit window too close to stimulus edges')
    # Require the actual fit interval to be inside the logger marker bracket.
    slope = 1+fraction(logger_clock['drift_rate'],'logger drift')
    offset = fraction(logger_clock['offset_s'],'logger offset')
    la,lb = [fraction(v,'logger marker') for v in logger_clock['source_interval_s']]
    le = fraction(logger_clock['sync_residual_s'],'logger error')
    if not float(offset+slope*la+le) <= start < end <= float(offset+slope*lb-le):
        raise ValueError('Logger clock markers must conservatively bracket the audio fit window')
    gap_limit = fraction(metadata.get('max_slow_gap_s'), 'max_slow_gap_s')
    with Path(slow_path).open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or 'logger_time_s' not in reader.fieldnames:
            raise ValueError('Slow CSV needs unique columns including logger_time_s')
        times = [fraction(row['logger_time_s'],'logger_time_s') for row in reader]
    if gap_limit <= 0 or len(times) < 2 or any(not 0 < b-a <= gap_limit for a,b in zip(times,times[1:])):
        raise ValueError('Slow CSV violates its declared maximum sampling gap')
    if not float(offset+slope*times[0]+le) <= start < end <= float(offset+slope*times[-1]-le):
        raise ValueError('Actual slow sample support must conservatively cover the audio fit window')
    root = Path(output_dir)
    if root.exists():
        raise ValueError('Sealed run output directory must be new')
    root.mkdir(parents=True)
    files = {'multichannel_audio': (audio,'multichannel_audio.wav'),
             'drive_command': (drive,'drive_command.wav'),
             'slow_force_displacement': (Path(slow_path),'slow_force_displacement.csv')}
    for source,name in files.values():
        shutil.copyfile(source, root/name)
    native_saved = []
    for index,(record,source) in enumerate(native_paths):
        name = 'native_slow/'+str(index)+'_'+source.name
        destination = root/name;destination.parent.mkdir(exist_ok=True)
        shutil.copyfile(source,destination)
        native_saved.append({'path':name,'sha256':sha256(destination),'original_path':record['path']})
    for source,name in [(capture_path,'capture.json'),(probe_path,'probe.json'),
        (Path(logger_clock_path),'logger_clock.json'),(Path(drive_clock_path),'drive_clock.json'),
        (Path(metadata_path),'operator_metadata.json')]:
        shutil.copyfile(source, root/name)
    for source_path, clock in [(Path(logger_clock_path), logger_clock), (Path(drive_clock_path), drive_clock)]:
        marker_name = clock['source_markers_name']
        destination = root/marker_name
        if destination.exists():
            if sha256(destination) != clock['source_markers_sha256']:
                raise ValueError('Clock marker filename collision; use distinct source filenames')
        else:
            shutil.copyfile(source_path.parent/marker_name, destination)
    alignment_record = None
    alignment_path = Path(drive_clock_path).parent/'alignment.json'
    if alignment_path.is_file():
        alignment = load_json(alignment_path)
        if (alignment.get('schema') != 'hydrophone.drive-alignment/1' or
            alignment.get('recorded_wav_sha256') != sha256(audio) or
            alignment.get('probe_sha256') != sha256(probe_path) or
            alignment.get('command_sha256') != sha256(drive) or
            alignment.get('clock',{}).get('sha256') != sha256(drive_clock_path) or
            alignment.get('markers',{}).get('sha256') != drive_clock['source_markers_sha256']):
            raise ValueError('Drive alignment provenance contradicts selected capture/clock')
        shutil.copyfile(alignment_path,root/'drive_alignment.json')
        alignment_record = {'path':'drive_alignment.json','sha256':sha256(root/'drive_alignment.json')}
    sync = {k:logger_clock[k] for k in ('offset_s','drift_rate','sync_residual_s','method')}
    sync['drive_to_audio'] = {k:drive_clock[k] for k in ('offset_s','drift_rate','sync_residual_s','method')}
    run = {k:metadata[k] for k in ('run_id','specimen_id','history_protocol','calibration_id','validity_domain','rod_state','data_origin')}
    run.update({'schema':'fusion.run/1',
        'raw_files':{role:{'path':name,'sha256':sha256(root/name)} for role,(source,name) in files.items()},
        'audio':{'sample_rate_Hz':capture['sample_rate_Hz'], 'channel_map':labels,
                 'gain_per_channel':gains,'missing_samples':0},
        'sync':sync, 'calibration':metadata.get('calibration',{}),
        'slow_pairing_declaration':metadata.get('slow_pairing'),
        'source_target_plan_sha256':plan['source_targets_sha256'],
        'analysis':{'tones':{**{k:metadata[k] for k in ('drive_channel','response_channel','reference_channel')},
            'frequencies_Hz':[float(fraction(f,'target frequency')/(1+fraction(drive_clock['drift_rate'],'drive drift')))
                              for f in plan['frequencies_Hz']],
            'start_s':start,'end_s':end},
            'slow':metadata.get('slow_analysis',{})},
        'provenance':{'probe_sha256':sha256(root/'probe.json'),
            'nominal_dac_frequencies_Hz':plan['frequencies_Hz'],
            'capture_sha256':sha256(root/'capture.json'),
            'logger_clock_sha256':sha256(root/'logger_clock.json'),
            'drive_clock_sha256':sha256(root/'drive_clock.json'),
            'operator_metadata_sha256':sha256(root/'operator_metadata.json')},
        'qualifications':['Operator declarations and affine clock bounds are not independently certified.',
            'Source hash identifies recovered target plan, not independently replayed score events.',
            'Signature features do not by themselves establish a clay-memory state.']})
    for index,record in enumerate(native_saved):
        run['raw_files']['native_slow_'+str(index)] = record
    run['provenance']['drive_alignment'] = alignment_record
    path = root/'run.json'
    path.write_text(json.dumps(run,indent=2,allow_nan=False)+'\n')
    try:
        audit = audit_run(path)
        if audit['status'] != 'RECORDED_DATA_CHECKS_PASSED':
            raise ValueError('Sealed recording requires quality review: '+audit['status'])
    except Exception:
        # Preserve diagnostic input bytes; make failure unambiguous and do not
        # leave a canonical run.json that could be mistaken for an accepted run.
        path.rename(root/'REJECTED_run.json')
        raise
    (root/'acquisition_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    return {'schema':'hydrophone.sealed-run/1','run_manifest':str(path),
        'acquisition_audit':audit,'hardware_commands_issued':0,
        'physical_readiness_verified':False}
