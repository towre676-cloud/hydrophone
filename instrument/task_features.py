"""Hash-bound extraction for the registered clay-history tuning task.

This is a measurement adapter, not a natural-pitch estimator, calibration
laboratory, or validation of the history-to-action hypothesis. External free-
decay pitch records and scoped installed qualification are mandatory inputs.
"""
from __future__ import annotations

import csv
from fractions import Fraction as F
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import struct
import wave

from computing.acquisition import audit_run
from evaluation.protocol import bind_contract, digest, exact, read_json
from .analyze import _qr_fit
from .run import _bound_file
from .probe import load_probe


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extractor_revision():
    root = Path(__file__).resolve().parents[1]
    files = ('instrument/task_features.py', 'instrument/analyze.py',
             'instrument/run.py', 'instrument/probe.py', 'instrument/episode.py',
             'instrument/drive.py', 'evaluation/render.py',
             'computing/acquisition.py', 'evaluation/protocol.py')
    return 'task-features/1:' + digest({name: _sha(root/name) for name in files})


def _positive(value, label, allow_zero=False):
    number = exact(value)
    if number < 0 or (number == 0 and not allow_zero):
        raise ValueError(label + ' must be positive' if not allow_zero else label + ' must be nonnegative')
    return number


def _identity(value, label):
    if not isinstance(value, str) or not value.strip() or value in ('PENDING', 'REPLACE'):
        raise ValueError('Missing qualified identity: ' + label)
    return value


def _finite_float(value, label):
    try:
        result = float(value)
    except (ValueError, OverflowError, TypeError) as exc:
        raise ValueError(label + ' cannot be represented as finite numerical data') from exc
    if not math.isfinite(result):
        raise ValueError(label + ' must remain finite')
    return result


@lru_cache(maxsize=8)
def _ln_bounds(value):
    """Exact positive atanh-series enclosure of ln(value), 1<=value<=2."""
    if not F(1) <= value <= F(2):
        raise ValueError('Logarithm reduction failed')
    t = (value-1)/(value+1)
    power, square, total, terms = t, t*t, F(0), 40
    for k in range(terms):
        total += power/(2*k+1)
        power *= square
    low = 2*total
    # All omitted terms are positive; replacing their odd denominators with
    # the first omitted denominator gives this geometric-series majorant.
    return low, low+2*power/((2*terms+1)*(1-square))


def _cents_with_arithmetic_bound(ratio):
    """Return compact decimal cents and exact rounded-up numerical error."""
    if ratio <= 0:
        raise ValueError('Pitch ratio must be positive')
    exponent = ratio.numerator.bit_length()-ratio.denominator.bit_length()
    reduced = ratio/(F(2)**exponent)
    if reduced < 1:
        exponent -= 1; reduced *= 2
    if reduced >= 2:
        exponent += 1; reduced /= 2
    lo, hi = _ln_bounds(reduced)
    ln2lo, ln2hi = _ln_bounds(F(2))
    lower, upper = 1200*exponent+1200*lo/ln2hi, 1200*exponent+1200*hi/ln2lo
    scale = 10**12
    units = round((lower+upper)*scale/2)
    center = F(units,scale)
    radius = F(math.ceil(max(abs(center-lower),abs(upper-center))*scale),scale)
    absolute = abs(units)
    text = ('-' if units<0 else '')+str(absolute//scale)+'.'+str(absolute%scale).zfill(12)
    return text.rstrip('0').rstrip('.'), radius


def _save(root, name, value):
    root = Path(root)
    if root.exists():
        raise ValueError('Task extraction output directory must be new')
    root.mkdir(parents=True)
    path = root/name
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    return {'path': str(path), 'sha256': _sha(path), 'record': value}


def _clock_provenance(run,run_path):
    from .synchronize import read_clock
    provenance=run.get('provenance',{})
    present=any(provenance.get(k) for k in ('logger_clock_sha256','drive_clock_sha256'))
    if run.get('data_origin')!='physical_measurement' and not present:
        return
    root=Path(run_path).resolve().parent
    for filename,source_key,digest_key,mapping in [
        ('logger_clock.json','logger_time_s','logger_clock_sha256',run['sync']),
        ('drive_clock.json','drive_time_s','drive_clock_sha256',run['sync'].get('drive_to_audio',{}))]:
        if not provenance.get(digest_key):
            raise ValueError('Physical task source requires sealed clock provenance')
        path=_bound_file(root,{'path':filename,'sha256':provenance[digest_key]})
        clock=read_clock(path,source_key)
        if (any(exact(clock[k])!=exact(mapping.get(k)) for k in ('offset_s','drift_rate','sync_residual_s')) or
            clock['method']!=mapping.get('method')):
            raise ValueError('Sealed clock replay disagrees with raw run mapping')


def _validate_force_port(origin, port, operator_port=None):
    """Reject the disconnected M04 writer as a post-write material reaction port."""
    if not isinstance(port,dict):
        raise ValueError('Task slow force requires an explicitly identified measurement port')
    _identity(port.get('port_validation_id'),'post-write force measurement port')
    if origin == 'synthetic':
        if port.get('measurement_role') != 'synthetic_reaction_trace':
            raise ValueError('Synthetic plumbing must explicitly label its nonphysical force trace')
        return
    if (port.get('measurement_role') != 'permanent_clay_reaction' or
        port.get('connection_state_during_1_2_s') != 'connected'):
        raise ValueError('Physical v1 requires a qualified permanent clay-reaction port; disconnected writer force is only unloaded baseline')
    for key in ('physical_sensor_serial','mount_id'):
        _identity(port.get(key),'permanent force port '+key)
    evidence_ids = port.get('evidence_ids')
    if not isinstance(evidence_ids,list) or not evidence_ids or any(not isinstance(v,str) or not v for v in evidence_ids):
        raise ValueError('Permanent clay-reaction port requires independent qualification evidence identities')
    if operator_port != port:
        raise ValueError('Permanent force port differs from hash-bound installed operator configuration')


def _context(run_path, core_path, qualification_path):
    run_path, core_path, qualification_path = map(Path, (run_path, core_path, qualification_path))
    run, core, q = map(read_json, (run_path, core_path, qualification_path))
    if run.get('schema') != 'fusion.run/1':
        raise ValueError('Task extraction requires canonical fusion.run/1')
    if q.get('schema') != 'hydrophone.task-feature-qualification/1' or q.get('status') != 'qualified_declaration':
        raise ValueError('Task feature qualification is incomplete or disabled')
    origin = run.get('data_origin')
    if origin not in ('synthetic', 'physical_measurement') or q.get('data_origin') != origin:
        raise ValueError('Task qualification and raw data origins must agree')
    if q.get('run_id') != run.get('run_id') or q.get('raw_run_sha256') != _sha(run_path):
        raise ValueError('Task qualification is not bound to this raw run')
    if q.get('experiment_core_sha256') != digest(core):
        raise ValueError('Task qualification uses a different experiment core')
    bound = bind_contract(core, q['binding'], origin)
    binding = bound['binding']
    if binding['calibration_id'] != run.get('calibration_id'):
        raise ValueError('Installed calibration differs from task binding')
    if binding['raw_feature_extractor_revision'] != extractor_revision():
        raise ValueError('Task extractor source revision differs from frozen binding')
    for record in run['raw_files'].values():
        _bound_file(run_path.resolve().parent, record)
    audit = audit_run(run_path)
    _clock_provenance(run,run_path)
    if audit['status'] != 'RECORDED_DATA_CHECKS_PASSED':
        raise ValueError('Raw acquisition quality requires review')
    if run['audio']['sample_rate_Hz'] != core['excitation']['sample_rate_Hz']:
        raise ValueError('Raw sample rate differs from task core')
    command_plan, _, command_path = load_probe(run_path.resolve().parent/'probe.json')
    if (command_plan.get('schema') != 'hydrophone.episode-command/1' or
        command_plan.get('experiment_core_canonical_sha256') != digest(core) or
        _sha(command_path) != audit['sha256']['drive_command']):
        raise ValueError('Actual command/timeline does not implement this bound episode core')
    evidence = q.get('evidence_files', [])
    if not isinstance(evidence, list) or (origin == 'physical_measurement' and not evidence):
        raise ValueError('Physical qualification requires independently supplied evidence files')
    for item in evidence:
        _bound_file(qualification_path.resolve().parent, item)
    if origin == 'physical_measurement' and any('synthetic' in str(v).lower() for v in binding.values()):
        raise ValueError('Synthetic binding cannot be relabelled as physical qualification')
    if origin == 'physical_measurement' and run.get('calibration',{}).get('slow_declared') is not True:
        raise ValueError('Physical force/position needs an installed slow-calibration declaration')
    operator = None
    if origin == 'physical_measurement':
        operator_digest = run.get('provenance',{}).get('operator_metadata_sha256')
        if not isinstance(operator_digest,str):
            raise ValueError('Physical run lacks its hash-bound installed setup record')
        operator_path = _bound_file(run_path.resolve().parent,
            {'path':'operator_metadata.json','sha256':operator_digest})
        operator = read_json(operator_path)
        for name in ('configuration_id','mechanics_revision','electronics_revision'):
            _identity(q.get(name),name)
            if q[name] != operator.get(name) or q[name] != run.get(name):
                raise ValueError('Physical qualification differs from installed setup: '+name)
    epoch = q['episode_epoch']
    offset = exact(epoch['audio_time_at_write_end_s'])
    scale = _positive(epoch['adc_nominal_seconds_per_episode_second'], 'Episode clock scale')
    error = _positive(epoch['total_episode_time_error_bound_s'], 'Episode time error', True)
    if error > exact(binding['clock_error_bound_s']):
        raise ValueError('Episode clock error exceeds bound experiment')
    drive_clock = run['sync'].get('drive_to_audio')
    if not drive_clock:
        raise ValueError('Qualified episode requires the declared DAC/ADC clock relation')
    drive_scale = 1+exact(drive_clock['drift_rate'])
    drive_offset = exact(drive_clock['offset_s'])
    drive_error = _positive(drive_clock['sync_residual_s'], 'DAC clock error', True)
    for t in (F(2),F(4)):
        discrepancy = abs((drive_offset+drive_scale*t-offset)/scale-t)
        if discrepancy+drive_error/scale+error > exact(binding['clock_error_bound_s']):
            raise ValueError('Physical command slot does not match the qualified write-end epoch')
    support = list(map(exact, epoch['qualified_episode_interval_s']))
    if len(support) != 2 or not support[0] <= 0 < 20 <= support[1]:
        raise ValueError('Qualified episode clock must cover the complete task')
    _identity(epoch.get('validation_id'), 'episode epoch')
    if epoch['validation_id'] != binding['synchronization_validation_id']:
        raise ValueError('Episode epoch uses a different synchronization qualification')
    for name in ('time_pairing_validation_id', 'slow_calibration_validation_id', 'temperature_validation_id'):
        _identity(q['slow'].get(name), name)
    if q['slow'].get('alignment_scope') != 'qualified_reconstructed_channel_times':
        raise ValueError('Sequential/filter-delayed slow channels need qualified reconstructed times')
    _validate_force_port(origin,q['slow'].get('force_port'),
        operator.get('conditions',{}).get('force_measurement_port') if operator is not None else None)
    transition = q.get('mode_transition')
    if (not isinstance(transition,dict) or transition.get('before_first_pluck_complete') is not True or
        transition.get('scope') != 'qualified_writer_release_and_required_rod_state_including_settling'):
        raise ValueError('Physical mode transition is unqualified before the first pluck')
    _identity(transition.get('validation_id'),'writer/rod mode transition')
    if exact(transition['completion_including_settling_upper_s']) > 0:
        raise ValueError('Writer/rod transition or settling extends beyond the frozen time-zero pluck')
    if transition.get('writer_state_after') != 'disconnected' or transition.get('rod_state_after') not in ('in','out'):
        raise ValueError('Qualified reader mode must release the writer and declare the rod state')
    if run.get('rod_state') != transition['rod_state_after']:
        raise ValueError('Raw rod state disagrees with qualified mode transition')
    events = transition.get('actual_event_records',[])
    if not isinstance(events,list) or (origin == 'physical_measurement' and not events):
        raise ValueError('Physical mode transition needs hash-bound actual event/timing evidence')
    for item in events:
        _bound_file(qualification_path.resolve().parent,item)
    roles = q['channels']
    names = run['audio']['channel_map']
    for key in ('drive', 'bridge', 'hydrophone', 'pitch'):
        if isinstance(roles[key], bool) or not isinstance(roles[key], int) or not 0 <= roles[key] < len(names):
            raise ValueError('Invalid qualified audio channel: ' + key)
    if len({roles[key] for key in ('drive','bridge','hydrophone')}) != 3:
        raise ValueError('Drive, bridge and hydrophone require distinct physical inputs')
    for key,name in (('drive','drive_loopback_raw'),('bridge','bridge_acceleration_raw'),('hydrophone','hydrophone_raw')):
        if names[roles[key]] != name:
            raise ValueError('Task channel role disagrees with canonical installed channel name: '+key)
    if roles['pitch'] not in (roles['bridge'],roles['hydrophone']):
        raise ValueError('Natural-pitch evidence must use a qualified mechanical/acoustic sensor input')
    wav = _bound_file(run_path.resolve().parent, run['raw_files']['multichannel_audio'])
    return {'run': run, 'core': core, 'q': q, 'binding': binding, 'run_path': run_path,
            'qualification_path': qualification_path, 'wav': wav, 'audit': audit,
            'offset': offset, 'scale': scale, 'time_error': error, 'command_plan':command_plan}


def _window(ctx, start, end, *, support_error=True):
    start, end = exact(start), exact(end)
    if not start < end:
        raise ValueError('Empty task window')
    rate = ctx['run']['audio']['sample_rate_Hz']
    offset, scale, error = ctx['offset'], ctx['scale'], ctx['time_error']
    first = math.ceil((offset + scale*start)*rate)
    stop = math.ceil((offset + scale*end)*rate)
    low = offset+scale*(start-error if support_error else start)
    high = offset+scale*(end+error if support_error else end)
    if low < 0 or high > F(ctx['audit']['audio']['frames'], rate):
        raise ValueError('Task window plus timing allowance leaves actual raw audio support')
    return first, stop


def _digital_tones(ctx):
    """Joint fit without forcing a nonzero denominator in reduced-arm silence."""
    first, stop = _window(ctx, '2.1', '3.9')
    roles, rate = ctx['q']['channels'], ctx['run']['audio']['sample_rate_Hz']
    clock = ctx['run']['sync'].get('drive_to_audio')
    if not clock:
        raise ValueError('Task tone fitting needs an independently qualified DAC/ADC clock map')
    scale = 1 + exact(clock['drift_rate'])
    if scale <= 0:
        raise ValueError('Invalid DAC/ADC clock scale')
    nominal = ctx['core']['excitation']['frequencies_Hz']
    frequencies = [_finite_float(exact(f)/scale, 'ADC tone frequency') for f in nominal]
    if any(not 0 < f < rate/2 for f in frequencies) or len(set(frequencies)) != len(frequencies):
        raise ValueError('Task frequencies alias or coincide on the ADC timebase')
    with wave.open(str(ctx['wav']), 'rb') as stream:
        channels = stream.getnchannels()
        if stream.getsampwidth() != 2:
            raise ValueError('Task extractor currently requires original PCM16 audio')
        stream.setpos(first); pcm = stream.readframes(stop-first)
    if len(pcm) != (stop-first)*channels*2:
        raise ValueError('Truncated task audio window')
    selected = sorted({roles[k] for k in ('drive','bridge','hydrophone')})
    signals = {c: [] for c in selected}
    for frame in struct.iter_unpack('<'+'h'*channels, pcm):
        for channel in selected:
            if frame[channel] in (-32768, 32767):
                raise ValueError('Task channel clips in the pre-action probe window')
            signals[channel].append(frame[channel]/32768.)
    count = stop-first
    if count < 16:
        raise ValueError('Task probe window is too short')
    center = (count-1)/2
    times = [(i-center)/rate for i in range(count)]
    span = center/rate
    columns = [[1.]*count, [t/span for t in times]]
    for frequency in frequencies:
        columns += [[math.cos(math.tau*frequency*t) for t in times],
                    [math.sin(math.tau*frequency*t) for t in times]]
    coefficients, _, condition = _qr_fit(columns, [signals[c] for c in selected])
    phasors = {}
    residuals = {}
    for c, beta in zip(selected, coefficients):
        phasors[c] = [complex(beta[2+2*j], -beta[3+2*j]) for j in range(len(frequencies))]
        residuals[str(c)] = math.sqrt(math.fsum((signals[c][i]-math.fsum(beta[j]*columns[j][i]
            for j in range(len(columns))))**2 for i in range(count))/count)
    return {'phasors': phasors, 'nominal_frequencies': nominal, 'ADC_frequencies_Hz': frequencies,
            'first_frame': first, 'stop_frame': stop, 'selected_pcm_sha256': hashlib.sha256(pcm).hexdigest(),
            'scaled_QR_condition': condition, 'residual_rms_diagnostic_only': residuals}


def _check_probe(ctx, fit, reduced):
    q = ctx['q']['probe_detection']
    _identity(q.get('validation_id'), 'probe presence/omission')
    error = _finite_float(_positive(q['drive_phasor_error_full_scale'], 'Drive phasor error', True), 'Drive phasor error')
    thresholds = q['reduced_max_full_scale'] if reduced else q['full_min_full_scale']
    amplitudes = []
    for f, value in zip(fit['nominal_frequencies'], fit['phasors'][ctx['q']['channels']['drive']]):
        threshold = _finite_float(_positive(thresholds[str(f)], 'Probe detection threshold', reduced), 'Probe detection threshold')
        amplitude = abs(value)
        if (reduced and amplitude+error > threshold) or (not reduced and amplitude-error < threshold):
            raise ValueError('Observed electrical probe presence/omission is unresolved or contradicts assigned arm')
        if not reduced and amplitude-error <= 1/32768:
            raise ValueError('Observed electrical denominator is unresolved under its declared error')
        amplitudes.append(amplitude)
    return {'assigned_reduced_protocol': reduced, 'drive_amplitudes_full_scale': amplitudes,
            'drive_phasor_error_full_scale_declared': error,
            'validation_id': q['validation_id'], 'qualification_authenticity_verified': False}


def _slow_features(ctx):
    run, q = ctx['run'], ctx['q']
    path = _bound_file(ctx['run_path'].resolve().parent, run['raw_files']['slow_force_displacement'])
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        required = {'logger_time_s','force_N','displacement_m','temperature_C'}
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames) or not required <= set(reader.fieldnames):
            raise ValueError('Qualified task slow CSV needs native logger time, force, displacement and room temperature')
        rows = [{k: exact(row[k]) for k in required} for row in reader]
    if len(rows) < 2:
        raise ValueError('Insufficient slow samples')
    sync = run['sync']
    logger_offset, logger_scale = exact(sync['offset_s']), 1+exact(sync['drift_rate'])
    if logger_scale <= 0:
        raise ValueError('Invalid slow/audio clock scale')
    max_gap = _positive(q['slow']['max_sample_gap_s'], 'Maximum slow sample gap')
    if any(not 0 < b['logger_time_s']-a['logger_time_s'] <= max_gap for a,b in zip(rows,rows[1:])):
        raise ValueError('Task slow samples violate their qualified sampling gap')
    results, sources = {}, {}
    windows = [('temperature_C','temperature_C','1','2'), ('displacement_m','displacement_m','1','2'),
               ('slow_force_N','force_N','1.8','2'), ('early_force_N','force_N','1','1.2')]
    for feature, column, start, end in windows:
        start, end = exact(start), exact(end)
        correction = exact(q['slow']['channel_time_correction_s'][column])
        error = _positive(q['slow']['channel_time_error_bound_s'][column], 'Slow channel timing error', True)
        minimum_clock_error = ctx['time_error']+exact(sync['sync_residual_s'])/ctx['scale']
        if error < minimum_clock_error:
            raise ValueError('Slow channel timing bound omits declared epoch/logger clock errors')
        if error > exact(ctx['binding']['clock_error_bound_s']):
            raise ValueError('Slow channel timing error exceeds experiment bound')
        times = [(logger_offset+logger_scale*r['logger_time_s']-ctx['offset'])/ctx['scale']+correction for r in rows]
        if times[0]+error > start or times[-1]-error < end:
            raise ValueError('Actual slow support does not cover qualified task window')
        indexes = [i for i,t in enumerate(times) if start <= t < end]
        if not indexes:
            raise ValueError('No qualified slow sample in task window')
        results[feature] = sum(rows[i][column] for i in indexes)/len(indexes)
        sources[feature] = {'column':column, 'episode_window_s':[str(start),str(end)],
            'row_indices':indexes, 'sample_count':len(indexes), 'mean_rule':'exact arithmetic sample mean, half-open window',
            'first_selected_episode_time_s':str(times[indexes[0]]), 'last_selected_episode_time_s':str(times[indexes[-1]]),
            'channel_time_correction_s_declared':str(correction), 'channel_time_error_bound_s_declared':str(error)}
    results['relaxation_N'] = results.pop('early_force_N')-results['slow_force_N']
    return {key:str(value) for key,value in results.items()}, sources


def _pitch(ctx, path, kind):
    record = read_json(path)
    binding = ctx['binding']
    if (record.get('schema') != 'hydrophone.qualified-free-decay-pitch/1' or
        record.get('data_origin') != ctx['run']['data_origin'] or
        record.get('status') != 'qualified_declaration' or record.get('probe_kind') != 'free_decay_pluck'):
        raise ValueError('Need independently qualified free-decay pitch; a driven line is not natural pitch')
    for key in ('pitch_bound_validation_id','pitch_probe_qualification_id'):
        if record.get(key) != binding[key]:
            raise ValueError('Pitch record qualification changed: '+key)
    if (record.get('raw_audio_sha256') != ctx['run']['raw_files']['multichannel_audio']['sha256'] or
        record.get('run_id') != ctx['run']['run_id'] or record.get('analysis_channel') != ctx['q']['channels']['pitch']):
        raise ValueError('Pitch record is not bound to the selected raw channel/run')
    start,end,pluck = ('0.1','1','0') if kind == 'pre' else ('18.1','20','18')
    expected = list(_window(ctx,start,end))
    if record.get('window_frames') != expected or exact(record.get('pluck_episode_time_s')) != exact(pluck):
        raise ValueError('Pitch window/pluck does not match independent pre-action/outcome epoch')
    _identity(record.get('read_id'),'independent pitch read')
    if record.get('read_role') != kind:
        raise ValueError('Independent pitch read role changed')
    frequency = _positive(record['pitch_Hz_SI'], 'Qualified pitch')
    error = _positive(record['pitch_error_cents'], 'Qualified pitch error', True)
    if record.get('error_scope') != 'complete_pitch_error_including_ADC_clock_nonstationarity_and_estimator':
        raise ValueError('Pitch error record does not cover the complete qualified estimator scope')
    cents, arithmetic_error = _cents_with_arithmetic_bound(frequency/exact(ctx['core']['task']['target_Hz']))
    if error+arithmetic_error > exact(ctx['core']['task']['maximum_qualified_pitch_error_bound_cents']):
        raise ValueError('Qualified pitch error including conversion exceeds task maximum')
    return {'cents':cents,'error_cents':str(error+arithmetic_error),
            'input_pitch_error_cents_declared':str(error),'arithmetic_conversion_error_cents':str(arithmetic_error),
            'read_id':record['read_id'],
            'source_record_sha256':_sha(path),'window_frames':expected,'pluck_episode_time_s':pluck,
            'pitch_Hz_SI':str(frequency),'qualification_authenticity_verified':False}


def _provenance(ctx):
    return {'raw_run_sha256':_sha(ctx['run_path']), 'qualification_sha256':_sha(ctx['qualification_path']),
            'raw_audio_sha256':ctx['run']['raw_files']['multichannel_audio']['sha256'],
            'slow_raw_sha256':ctx['run']['raw_files']['slow_force_displacement']['sha256'],
            'experiment_core_sha256':digest(ctx['core'])}


def extract_features(run_path, core_path, qualification_path, pitch_pre_path, episode_metadata_path, output_dir):
    """Extract pre-action fields only; never inspect a post-action pitch record."""
    ctx = _context(run_path, core_path, qualification_path)
    meta = read_json(episode_metadata_path)
    if (meta.get('schema') != 'hydrophone.task-episode-request/1' or
        meta.get('run_id') != ctx['run']['run_id'] or meta.get('data_origin') != ctx['run']['data_origin']):
        raise ValueError('Episode request does not match the raw run')
    condition, history, arm = meta['condition'], meta['write_protocol'], meta['policy_arm']
    if condition not in ctx['core']['conditions'] or history not in ctx['core']['histories'] or arm not in ctx['core']['policy_arms']:
        raise ValueError('Unknown registered task condition/history/arm')
    if ctx['run']['history_protocol'] != history:
        raise ValueError('Raw preparation history differs from assigned episode')
    expected_rod = 'out' if condition == 'rod_disconnected_clay' else 'in'
    if ctx['q']['mode_transition']['rod_state_after'] != expected_rod:
        raise ValueError('Qualified rod mode does not implement assigned experimental condition')
    decision = exact(meta['decision_time_s'])
    if not F(4)+2*exact(ctx['binding']['clock_error_bound_s']) < decision <= exact(ctx['core']['timing_s_relative_to_write_end']['decision_deadline']):
        raise ValueError('Declared decision precedes the pre-action data window boundary')
    costs = meta.get('cost_s')
    if (not isinstance(costs,dict) or set(costs) != set(ctx['core']['cost_components_s']) or
        any(exact(value)<0 for value in costs.values()) or exact(costs['reset_s'])<1):
        raise ValueError('Complete nonnegative cost ledger must charge the actual one-second recording tail to reset')
    reduced = arm == 'fusion_reduced'
    if ctx['command_plan']['protocol_arm'] != ('reduced' if reduced else 'full'):
        raise ValueError('Actual episode timeline differs from assigned acquisition arm')
    expected_command = ctx['binding']['reduced_drive_waveform_sha256' if reduced else 'drive_waveform_sha256']
    if ctx['audit']['sha256']['drive_command'] != expected_command:
        raise ValueError('Actual command hash differs from assigned registered protocol')
    pitch = _pitch(ctx,pitch_pre_path,'pre')
    slow, sources = _slow_features(ctx)
    fit = _digital_tones(ctx)
    detected = _check_probe(ctx,fit,reduced)
    features = {'pre_pitch_cents':pitch['cents'], **slow,
        'condition_code':str({'connected_clay':0,'rod_disconnected_clay':1,'reference_cartridge':2}[condition]),
        'write_code':str(int(history=='H1'))}
    if not reduced:
        index = [exact(f) for f in fit['nominal_frequencies']].index(exact(ctx['core']['task']['target_Hz']))
        denominator = fit['phasors'][ctx['q']['channels']['drive']][index]
        features['bridge_feature'] = format(abs(fit['phasors'][ctx['q']['channels']['bridge']][index]/denominator),'.17g')
        features['water_feature'] = format(abs(fit['phasors'][ctx['q']['channels']['hydrophone']][index]/denominator),'.17g')
    public_fit = {key:value for key,value in fit.items() if key != 'phasors'}
    record = {'schema':'fusion.pre-action-features/1','run_id':ctx['run']['run_id'],
        'execution_scope':'OFFLINE_REPLAY_NOT_PROOF_OF_ONLINE_DECISION',
        'data_origin':ctx['run']['data_origin'],'extractor_revision':extractor_revision(),
        'feature_end_s':'2' if reduced else '4','features':features,
        'pre_action_quality_window_end_s':'4','decision_time_s':str(decision),
        'cost_s':{key:str(exact(value)) for key,value in costs.items()},
        'condition':condition,'write_protocol':history,'policy_arm':arm,
        'pitch_read':pitch,'slow_windows':sources,'probe_fit':public_fit,'probe_detection':detected,
        'slow_force_port':ctx['q']['slow']['force_port'],
        'provenance':{**_provenance(ctx),'episode_request_sha256':_sha(episode_metadata_path)},
        'laboratory_authenticity_verified':False,'physical_claim':False,
        'online_execution_latency_verified':False,
        'archive_quality_audit_scope':'COMPLETE_RAW_RECORD_AFTER_END_NOT_PREDECISION',
        'qualifications':['Input calibration, pitch, synchronization and correction bounds are independently supplied declarations.',
            'Window means are exact arithmetic on selected samples, not a bound on continuous-time averages.',
            'Residual RMS and correlation diagnostics are not deterministic uncertainty bounds.',
            'Declared decision time is checked against pre-action window boundaries; full-file archive audit occurs after capture and did not make that past decision.',
            'Bridge/water features are digital channel ratios, not force-normalized material parameters.',
            'Reduced omission is checked in the same declared probe slot; only full arms export probe features.']}
    return _save(output_dir,'pre_features.json',record)


def extract_outcome(run_path, core_path, qualification_path, pitch_post_path, action_record_path, output_dir):
    """Package independent future pitch and independently measured action achievement."""
    ctx = _context(run_path,core_path,qualification_path)
    pitch = _pitch(ctx,pitch_post_path,'post')
    action = read_json(action_record_path)
    if (action.get('schema') != 'hydrophone.qualified-manual-action/1' or
        action.get('status') != 'qualified_declaration' or action.get('run_id') != ctx['run']['run_id'] or
        action.get('data_origin') != ctx['run']['data_origin'] or
        action.get('action_qualification_id') != ctx['binding']['action_qualification_id']):
        raise ValueError('Independent action-achievement record is incomplete or mismatched')
    if action.get('action') not in ctx['core']['action_ids']:
        raise ValueError('Unknown actually applied action')
    start,end = list(map(exact,action['measurement_window_episode_s']))
    if not 5 <= start < end <= 17:
        raise ValueError('Action achievement evidence must precede independent outcome window')
    if action.get('window_frames') != list(_window(ctx,str(start),str(end))):
        raise ValueError('Action achievement raw indices do not match its independent measurement window')
    if action.get('raw_audio_sha256') != ctx['run']['raw_files']['multichannel_audio']['sha256']:
        raise ValueError('Action achievement record is not bound to the raw episode')
    _identity(action.get('measurement_id'),'independent action measurement')
    if action['measurement_id'] == pitch['read_id']:
        raise ValueError('Outcome pitch cannot supply its own action achievement')
    achievement = exact(action['realized_action_cents'])
    achievement_error = _positive(action['realized_action_error_cents'],'Action achievement error',True)
    record = {'schema':'fusion.independent-outcome/1','run_id':ctx['run']['run_id'],
        'data_origin':ctx['run']['data_origin'],'outcome_status':'completed',
        'outcome_cents':pitch['cents'],'outcome_error_cents':pitch['error_cents'],
        'outcome_start_s':'18','outcome_end_s':'20','realized_action_cents':str(achievement),
        'realized_action_error_cents':str(achievement_error),'action':action['action'],
        'pitch_bound_validation_id':ctx['binding']['pitch_bound_validation_id'],
        'target_Hz':ctx['core']['task']['target_Hz'],'pitch_read':pitch,
        'action_achievement':{'measurement_id':action['measurement_id'],
            'measurement_window_episode_s':[str(start),str(end)],
            'source_record_sha256':_sha(action_record_path)},
        'provenance':_provenance(ctx),'laboratory_authenticity_verified':False,'physical_claim':False,
        'tail_recording_cost': 'Any post-20s recording padding must be charged to the episode/reset cost ledger.',
        'qualifications':['No pre-action pitch is reused as future outcome.',
            'A qualified external natural-pitch estimate is required; no driven line or fit residual supplies its error.',
            'The evaluator decides action achievement and task success from these records.']}
    return _save(output_dir,'outcome.json',record)
