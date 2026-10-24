#!/usr/bin/env python3
"""Offline-first LabJack T7 slow-voltage capture; marker DAC0 is the only output.

Dry run (no SDK import/device access):
  python hardware/electronics/t7_capture.py --duration 30
Explicit hardware capture, after wiring/limits have been checked:
  python hardware/electronics/t7_capture.py --execute --identifier SERIAL \
      --duration 30 --output-dir results/t7_slow_run_001

Install the official native LJM library for the host, then the optional Python
wrapper with ``python -m pip install labjack-ljm``. Nothing is installed by this
script. Primary API/example sources checked 24 October 2026:
https://support.labjack.com/docs/ljm-software-installer-downloads-t4-t7-t8-digit
https://github.com/labjack/labjack-ljm-python/blob/master/Examples/More/Stream/stream_basic.py
https://support.labjack.com/docs/estreamstart-ljm-user-s-guide
https://support.labjack.com/docs/estreamread-ljm-user-s-guide
https://support.labjack.com/docs/a-1-1-stream-data-rates-t-series-datasheet

This emits raw device-calibrated VOLTAGES, not force/displacement SI values.
Use a separately validated end-to-end calibration conversion before importing
force_N/displacement_m. Nominal gain/sensitivity are not an accuracy certificate.
Wire through the labelled breakout: InAmp OUTA -> force filter -> AIN0;
OUTA must NOT also connect directly to AIN0. OUTB stays isolated from AIN1.
AIN2 is filtered optical displacement, AIN4 unfiltered marker readback,
AIN6 excitation monitor. Clock alignment does not remove sensor filter delays.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib
import json
import math
from pathlib import Path
import random
import sys
import time

CHANNELS = ("AIN0", "AIN2", "AIN4", "AIN6")
COLUMNS = ("raw_force_V", "raw_displacement_V", "raw_marker_V", "raw_excitation_V")
REQUESTED_RATE = 50.0
LOW, HIGH = 0.05, 1.0
DUMMY = -9999.0


def configuration_plan(duration_s=30.0, scans_per_read=5):
    if isinstance(duration_s, bool):
        raise ValueError("duration must be finite seconds between 12 and 7200")
    duration = float(duration_s)
    if not math.isfinite(duration) or not 12 <= duration <= 7200:
        raise ValueError("duration must be finite seconds between 12 and 7200")
    if isinstance(scans_per_read, bool) or not isinstance(scans_per_read, int) or not 1 <= scans_per_read <= 10:
        raise ValueError("scans_per_read must be an integer from 1 to 10")
    # Integer-ms seeded cadence; no repeated planned six-pulse signature.
    # Actual readbacks must still reject ambiguous clock correspondences.
    final_onset = round(duration*1000)-1400
    for attempt in range(32):
        seed = 20261024+attempt
        rng = random.Random(seed)
        sequence = []
        onset = 400
        while onset < final_onset-950:
            width = rng.choice((350,450,550,650))
            sequence.append((onset,width))
            onset += rng.choice((1100,1300,1500,1700,1900))
        gap = final_onset-sequence[-1][0]
        if gap>1900:
            sequence.append((round((sequence[-1][0]+final_onset)/2),350))
        sequence.append((final_onset,350))
        signatures = [(tuple(w for _,w in sequence[i:i+6]),
                       tuple(sequence[j+1][0]-sequence[j][0] for j in range(i,i+5)))
                      for i in range(len(sequence)-5)]
        if len(signatures)==len(set(signatures)):
            break
    else:
        raise ValueError('could not produce a unique six-pulse planned marker cadence')
    pulses = [('pre' if t<3000 else 'post' if t>=(duration-3)*1000 else 'mid',t/1000,w/1000)
              for t,w in sequence]
    maximum_gap = max((b[0]-a[0])/1000 for a,b in zip(sequence,sequence[1:]))
    return {"schema":"hydrophone.t7-capture-plan/1", "mode":"DRY_RUN",
            "hardware_accessed":False, "scan_list":list(CHANNELS),
            "raw_voltage_columns":list(COLUMNS), "range_V":10.0,
            "negative_channel":199, "stream_resolution_index":7,
            "stream_settling_us":0, "stream_clock_source":0,
            "stream_trigger_index":0, "requested_scan_rate_Hz":REQUESTED_RATE,
            "scans_per_read":scans_per_read, "duration_s":duration,
            "sample_time_rule":"sample_index / actual eStreamStart scan rate; scan channels are sequential",
            "marker_output":"DAC0", "marker_low_V":LOW, "marker_high_V":HIGH,
            "minimum_marker_low_s":.3,
            "nominal_marker_max_leading_edge_gap_s":maximum_gap,
            "marker_pattern_seed":seed,
            "planned_six_pulse_signatures_unique":True,
            "marker_identity_scope":"Unique planned six-pulse widths/gaps only; require actual readback correspondence and reject ambiguous matches",
            "final_planned_low_margin_s":duration-(sequence[-1][0]+sequence[-1][1])/1000,
            "marker_pulses":[{"phase":p,"planned_onset_s":t,"minimum_high_s":w} for p,t,w in pulses],
            "marker_timing":"Host-issued commands are diagnostic only; use actual AIN4/audio readbacks for alignment",
            "sync_pick_allowance_s":.02,
            "nominal_interchannel_delay_s":.000670,
            "wiring":"Labelled breakout: OUTA -> force filter -> AIN0 only; OUTB isolated; AIN2 laser through filter; AIN4 marker; AIN6 excitation",
            "filter_setting":"Force/laser DC-coupled 5 Hz Butterworth candidate; qualify per-channel response/delay",
            "physical_conversion_enabled":False,
            "calibration_followup":"Convert raw voltage only with a separately validated, serial-bound, end-to-end force/displacement calibration and validity/error bounds; retain this CSV unchanged",
            "actuator_drive_enabled":False}


def _digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def capture(output_dir, *, identifier=None, execute=False, duration_s=30.0,
            scans_per_read=5, ljm_module=None, clock=time.monotonic, sleep=time.sleep):
    """Return a plan unless execute=True; tests may inject a mock LJM and clock.

    Live capture writes every returned scan, including dummy values, without
    compressing the sample-index time axis. Backlog is reported independently
    from skipped samples: a nonzero buffer does not prove data loss.
    """
    plan = configuration_plan(duration_s, scans_per_read)
    if not execute:
        return plan
    if not isinstance(identifier, str) or not identifier.isdigit() or int(identifier) <= 0:
        raise ValueError("--execute requires an explicit positive numeric T7 serial --identifier")
    out = Path(output_dir)
    names = ('raw_slow_volts.csv', 't7_capture.json', 't7_blocks.jsonl')
    if any((out/name).exists() for name in names):
        raise ValueError("capture output already exists; choose a fresh output directory")
    ljm = ljm_module if ljm_module is not None else importlib.import_module('labjack.ljm')
    out.mkdir(parents=True, exist_ok=True)
    receipt = {"schema":"hydrophone.t7-capture/1", "mode":"EXECUTE",
               "hardware_accessed":False, "identifier_requested":identifier,
               "configuration":plan, "status":"CAPTURE_FAILED",
               "rows":0, "dummy_values":0, "rows_with_gaps":0,
               "nonfinite_values":0, "max_device_scan_backlog":0,
               "max_ljm_scan_backlog":0, "backlog_nonzero":False,
               "backlog_increasing":False, "marker_commands":[],
               "cleanup_errors":[], "physical_conversion_enabled":False,
               "physical_calibration_verified":False,
               "clock_alignment_verified":False,
               "actuator_drive_enabled":False}
    handle = None
    active = False
    verified_target = False
    epoch = None
    pulse_index = 0
    high_since = None
    low_since = None
    last_backlogs = (0,0)
    raw_path, blocks_path = out/names[0], out/names[2]

    def marker(volts, reason):
        ljm.eWriteName(handle, 'DAC0', volts)
        receipt['marker_commands'].append({
            "voltage_V":volts, "reason":reason,
            "host_monotonic_since_stream_start_s":None if epoch is None else clock()-epoch,
            "issued_after_returned_scan_count":receipt['rows'],
            "time_scope":"host diagnostic, not a device sample timestamp"})

    def service_marker():
        nonlocal pulse_index, high_since, low_since
        now = clock()
        if high_since is not None:
            pulse = plan['marker_pulses'][pulse_index]
            if now-high_since >= pulse['minimum_high_s']:
                marker(LOW, 'pulse_end_'+pulse['phase'])
                high_since = None
                low_since = clock()
                pulse_index += 1
            return
        if pulse_index < len(plan['marker_pulses']):
            pulse = plan['marker_pulses'][pulse_index]
            elapsed_scans = receipt['rows']/receipt['actual_scan_rate_Hz']
            if (elapsed_scans >= pulse['planned_onset_s'] and low_since is not None
                    and now-low_since >= plan['minimum_marker_low_s']):
                marker(HIGH, 'pulse_start_'+pulse['phase'])
                # Start the minimum-width timer after the SDK write returns;
                # command latency must not shorten the requested high plateau.
                high_since = clock()
                low_since = None

    try:
        # Calibrated in LJM terminology means device voltage calibration only.
        ljm.writeLibraryConfigS('LJM_STREAM_AIN_BINARY', 0)
        handle = ljm.openS('T7', 'ANY', identifier)
        receipt['hardware_accessed'] = True
        info = ljm.getHandleInfo(handle)
        receipt['device_info'] = list(info)
        if info[0] != 7 or str(info[2]) != identifier:
            raise ValueError("opened device type/serial does not match explicit T7 selection")
        verified_target = True
        scan_addresses = ljm.namesToAddresses(len(CHANNELS), list(CHANNELS))[0]
        config_names = ['STREAM_TRIGGER_INDEX','STREAM_CLOCK_SOURCE',
                        'STREAM_RESOLUTION_INDEX','STREAM_SETTLING_US']
        config_values = [0,0,7,0]
        for name in CHANNELS:
            config_names.extend([name+'_RANGE', name+'_NEGATIVE_CH'])
            config_values.extend([10.0,199])
        ljm.eWriteNames(handle,len(config_names),config_names,config_values)
        marker(LOW, 'initial_low')
        low_since = clock()
        actual = ljm.eStreamStart(handle, scans_per_read, len(CHANNELS), scan_addresses, REQUESTED_RATE)
        active = True
        if not math.isfinite(actual) or actual <= 0:
            raise ValueError("LJM returned an invalid actual scan rate")
        receipt['actual_scan_rate_Hz'] = actual
        epoch = clock()
        target_rows = math.ceil(plan['duration_s']*actual)
        receipt['target_minimum_rows'] = target_rows
        with raw_path.open('w',newline='',encoding='utf-8') as raw, blocks_path.open('w',encoding='utf-8') as blocks:
            writer = csv.writer(raw)
            writer.writerow(['sample_index','time_s',*COLUMNS,'row_has_gap','gap_channels',
                             'invalid_channels','read_index','device_scan_backlog','ljm_scan_backlog'])
            read_index = 0
            while receipt['rows'] < target_rows:
                service_marker()
                data, device_backlog, library_backlog = ljm.eStreamRead(handle)
                if len(data)%len(CHANNELS) or not data:
                    raise ValueError("LJM returned an empty or incomplete interleaved scan block")
                backlogs = (int(device_backlog), int(library_backlog))
                if min(backlogs) < 0:
                    raise ValueError("LJM returned a negative backlog")
                receipt['backlog_nonzero'] |= any(backlogs)
                receipt['backlog_increasing'] |= any(a>b for a,b in zip(backlogs,last_backlogs))
                receipt['max_device_scan_backlog'] = max(receipt['max_device_scan_backlog'],backlogs[0])
                receipt['max_ljm_scan_backlog'] = max(receipt['max_ljm_scan_backlog'],backlogs[1])
                first_index = receipt['rows']
                dummy_count = 0
                for at in range(0,len(data),len(CHANNELS)):
                    values = [float(v) for v in data[at:at+len(CHANNELS)]]
                    gaps = [name for name,v in zip(CHANNELS,values) if v==DUMMY]
                    invalid = [name for name,v in zip(CHANNELS,values) if not math.isfinite(v)]
                    index = receipt['rows']
                    writer.writerow([index,format(index/actual,'.17g'),
                                     *[format(v,'.17g') for v in values],int(bool(gaps)),
                                     '|'.join(gaps),'|'.join(invalid),read_index,*backlogs])
                    receipt['rows'] += 1
                    receipt['dummy_values'] += len(gaps)
                    dummy_count += len(gaps)
                    receipt['rows_with_gaps'] += bool(gaps)
                    receipt['nonfinite_values'] += len(invalid)
                blocks.write(json.dumps({'read_index':read_index,'first_sample_index':first_index,
                    'scans_returned':len(data)//len(CHANNELS),'dummy_values':dummy_count,
                    'device_scan_backlog':backlogs[0],'ljm_scan_backlog':backlogs[1],
                    'host_read_return_s':clock()-epoch,'host_time_is_sample_timestamp':False})+'\n')
                raw.flush()
                blocks.flush()
                last_backlogs = backlogs
                read_index += 1
        receipt['status'] = 'CAPTURE_COMPLETED'
    except (Exception,KeyboardInterrupt) as exc:
        receipt['error'] = {"type":type(exc).__name__,"message":str(exc)}
        receipt['status'] = 'CAPTURE_INTERRUPTED' if isinstance(exc,KeyboardInterrupt) else 'CAPTURE_FAILED'
    finally:
        if handle is not None:
            if verified_target:
                try:
                    if high_since is not None:
                        remaining = (plan['marker_pulses'][pulse_index]['minimum_high_s']
                                     -(clock()-high_since))
                        if remaining>0:
                            sleep(remaining)
                    marker(LOW, 'cleanup_low')
                except Exception as exc:
                    receipt['cleanup_errors'].append('DAC0 low: '+str(exc))
            if active:
                try:
                    ljm.eStreamStop(handle)
                except Exception as exc:
                    receipt['cleanup_errors'].append('stream stop: '+str(exc))
            try:
                ljm.close(handle)
            except Exception as exc:
                receipt['cleanup_errors'].append('close: '+str(exc))
    receipt['marker_pulse_commands_completed'] = pulse_index
    receipt['marker_schedule_complete'] = pulse_index == len(plan['marker_pulses'])
    receipt['marker_observed_in_both_records'] = False
    receipt['quality_requires_review'] = bool(receipt['status']!='CAPTURE_COMPLETED'
        or receipt['dummy_values'] or receipt['nonfinite_values']
        or receipt['backlog_nonzero'] or receipt['cleanup_errors'] or not receipt['marker_schedule_complete'])
    receipt['raw_files'] = {p.name:{'path':p.name,'sha256':_digest(p)}
                            for p in [raw_path,blocks_path] if p.is_file()}
    receipt['timing_scope'] = 'Index/accepted nominal device scan rate; oscillator error, scan skew and marker/path delays remain to be bounded'
    receipt['physical_readiness'] = False
    (out/names[1]).write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--identifier',help='Exact numeric T7 serial; required with --execute')
    parser.add_argument('--duration',type=float,default=30.0)
    parser.add_argument('--scans-per-read',type=int,default=5)
    parser.add_argument('--output-dir',type=Path,default=Path('results/t7_slow_run'))
    args = parser.parse_args(argv)
    try:
        result = capture(args.output_dir,identifier=args.identifier,execute=args.execute,
                         duration_s=args.duration,scans_per_read=args.scans_per_read)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 2 if result.get('status') in ('CAPTURE_FAILED','CAPTURE_INTERRUPTED') else 0
    except (ValueError,OSError,ImportError) as exc:
        print(json.dumps({'status':'REJECTED','error':str(exc),'hardware_accessed':False}),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
