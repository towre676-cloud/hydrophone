"""Fit measured clock markers; never promote fit residuals into proved bounds."""
import csv
from fractions import Fraction as F
import json
from pathlib import Path
from .probe import sha256


def fraction(value, name):
    if isinstance(value, bool):
        raise ValueError(name + ' must be finite')
    try:
        return F(str(value))
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise ValueError(name + ' must be finite') from exc


def fit_clock(marker_path, *, source_key='logger_time_s', declared_error_s,
              source_pick_error_s, audio_pick_error_s, method):
    """Exact rational OLS affine map audio=offset+(1+drift)*source.

    Three or more paired markers diagnose departure from one affine map.
    Caller-supplied error must cover observed residual plus marker picking
    error. Between-marker clock deviation remains an unverified assumption.
    """
    if source_key not in ('logger_time_s', 'drive_time_s'):
        raise ValueError('Source clock must be logger_time_s or drive_time_s')
    error = fraction(declared_error_s, 'declared_error_s')
    source_error = fraction(source_pick_error_s, 'source_pick_error_s')
    audio_error = fraction(audio_pick_error_s, 'audio_pick_error_s')
    if min(error, source_error, audio_error) < 0 or not isinstance(method, str) or not method.strip():
        raise ValueError('Need nonnegative declared errors and explicit marker method')
    path = Path(marker_path)
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
            or not {source_key, 'audio_time_s'} <= set(reader.fieldnames)):
            raise ValueError('Marker CSV needs unique source/audio columns')
        pairs = [(fraction(row[source_key], source_key), fraction(row['audio_time_s'], 'audio_time_s')) for row in reader]
    if len(pairs) < 3 or any(x < 0 or y < 0 for x,y in pairs):
        raise ValueError('Need at least three nonnegative paired marker times')
    if any(x1 >= x2 or y1 >= y2 for (x1,y1),(x2,y2) in zip(pairs, pairs[1:])):
        raise ValueError('Both marker clocks must be strictly increasing')
    count = len(pairs)
    xm = sum(x for x,y in pairs)/count; ym = sum(y for x,y in pairs)/count
    slope = sum((x-xm)*(y-ym) for x,y in pairs)/sum((x-xm)**2 for x,y in pairs)
    offset = ym-slope*xm
    residuals = [y-offset-slope*x for x,y in pairs]
    maximum = max(abs(r) for r in residuals)
    required = maximum+audio_error+abs(slope)*source_error
    if slope <= 0 or error < required:
        raise ValueError('Declared map error does not cover residual and marker-picking allowance')
    return {'schema': 'hydrophone.clock-map/1', 'source_key': source_key,
        'offset_s': str(offset), 'drift_rate': str(slope-1), 'sync_residual_s': str(error),
        'method': method, 'paired_markers': len(pairs),
        'source_interval_s': [str(pairs[0][0]), str(pairs[-1][0])],
        'audio_marker_interval_s': [str(pairs[0][1]), str(pairs[-1][1])],
        'max_observed_residual_s': str(maximum),
        'residuals_s': [str(r) for r in residuals],
        'source_pick_error_s_declared': str(source_error),
        'audio_pick_error_s_declared': str(audio_error),
        'minimum_observed_marker_allowance_s': str(required),
        'source_markers_name': path.name, 'source_markers_sha256': sha256(path),
        'between_marker_bound_verified': False,
        'qualification': 'AFFINE_FIT_WITH_DECLARED_BOUND_NOT_A_CLOCK_CERTIFICATE'}


def read_clock(path, source_key):
    from .run import load_json
    result = load_json(path)
    if result.get('schema') != 'hydrophone.clock-map/1' or result.get('source_key') != source_key:
        raise ValueError('Clock map schema/source mismatch')
    slope = 1+fraction(result['drift_rate'], 'drift_rate')
    error = fraction(result['sync_residual_s'], 'sync_residual_s')
    if slope <= 0 or error < 0 or not result.get('method'):
        raise ValueError('Invalid clock map')
    fraction(result['offset_s'], 'offset_s')
    a,b = [fraction(t,'clock interval') for t in result['source_interval_s']]
    if not 0 <= a < b or result.get('paired_markers', 0) < 3:
        raise ValueError('Clock map requires a measured marker bracket')
    if error < fraction(result['minimum_observed_marker_allowance_s'], 'marker allowance'):
        raise ValueError('Clock map bound contradicts marker diagnostics')
    path = Path(path).resolve()
    name = result['source_markers_name']
    if not isinstance(name, str) or Path(name).is_absolute():
        raise ValueError('Raw marker file path must be relative')
    markers = (path.parent/name).resolve()
    if not markers.is_relative_to(path.parent) or not markers.is_file() or sha256(markers) != result['source_markers_sha256']:
        raise ValueError('Raw clock marker file missing, outside directory, or SHA256 mismatch')
    replay = fit_clock(markers, source_key=source_key, declared_error_s=result['sync_residual_s'],
        source_pick_error_s=result['source_pick_error_s_declared'],
        audio_pick_error_s=result['audio_pick_error_s_declared'], method=result['method'])
    if result != replay:
        raise ValueError('Clock map disagrees with independent raw-marker replay')
    return result


def mapped_window(clock, start, end):
    """Return nominal ADC window and reject use outside the marker bracket."""
    slope = 1+fraction(clock['drift_rate'], 'drift_rate')
    offset = fraction(clock['offset_s'], 'offset_s')
    error = fraction(clock['sync_residual_s'], 'sync_residual_s')
    a,b = [fraction(t,'source interval') for t in clock['source_interval_s']]
    start,end = fraction(start,'start'), fraction(end,'end')
    if not a <= start < end <= b:
        raise ValueError('Analysis would extrapolate beyond measured clock markers')
    return float(offset+slope*start), float(offset+slope*end), float(error)
