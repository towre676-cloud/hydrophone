"""Bound between-sample motion from calibrated samples and a supplied speed cap.

The cap must apply uniformly to the *physical quantity being sampled*, not be
an RMS or merely the largest sampled velocity. No band-limit assumption or
unmeasured velocity bound is inferred. This may bound a measured residual
trace used in motion.py, subject to its separate instrument/out-of-band scope.
"""
from __future__ import annotations
import argparse
import csv
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
try:
    from .motion import positive, number
except ImportError:  # Direct script execution from its own directory.
    from motion import positive, number


def bound_trace(path, *, speed_bound_m_per_s, speed_bound_evidence_id,
                max_sample_gap_s, data_origin, configuration_id):
    if data_origin not in ('physical_measurement_declared','synthetic_demo'):
        raise ValueError('Trace origin must be explicit')
    if not configuration_id or not speed_bound_evidence_id:
        raise ValueError('Configuration and independent speed-bound evidence are required')
    speed=positive(speed_bound_m_per_s,'uniform physical speed bound',zero=True)
    allowed_gap=positive(max_sample_gap_s,'maximum permitted sample gap')
    times=[]; sample_uppers=[]
    path=Path(path)
    with path.open(newline='',encoding='utf-8-sig') as source:
        reader=csv.DictReader(source,strict=True)
        required={'time_s','displacement_m','displacement_error_m'}
        if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames) or not required<=set(reader.fieldnames):
            raise ValueError('Trace CSV requires unique time_s,displacement_m,displacement_error_m')
        for row in reader:
            t=number(row['time_s'],'SI timestamp')
            if times and t<=times[-1]:raise ValueError('Trace times must strictly increase')
            times.append(t)
            sample_uppers.append(abs(number(row['displacement_m'],'calibrated displacement'))+
                                 positive(row['displacement_error_m'],'displacement error',zero=True))
    if len(times)<2:raise ValueError('Trace needs at least two samples')
    gap=max(b-a for a,b in zip(times,times[1:]))
    if gap>allowed_gap:raise ValueError('Trace exceeds its declared maximum sample gap')
    upper=max(sample_uppers)+speed*gap/2
    return {'schema':'hydrophone.sampled-motion-peak-bound/1','evidence_type':data_origin,
            'configuration_id':configuration_id,'source_csv_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'time_interval_SI_s':[str(times[0]),str(times[-1])],'sample_count':len(times),
            'sample_peak_with_error_upper_m':str(max(sample_uppers)),
            'maximum_sample_gap_s':str(gap),'supplied_uniform_speed_bound_m_per_s':str(speed),
            'speed_bound_evidence_id':speed_bound_evidence_id,
            'between_sample_allowance_m':str(speed*gap/2),'conditional_continuous_peak_upper_m':str(upper),
            'hardware_execution_enabled':False,'evidence_authenticity_verified':False,
            'scope':'first through last sample only; conditional on complete timing/sample errors and a uniform physical speed bound',
            'limitations':['Largest sampled velocity, decoder range, RMS or a data-sheet noise floor is not automatically a uniform physical speed bound.',
                           'Filtered displacement samples do not cover physical motion rejected by the sensor/filter.',
                           'A residual trace needs a residual-speed bound; known-tone speed may be added to a total-speed bound conservatively.',
                           'No extrapolation before first/after last sample and no removal of an unknown wet-equilibrium offset.']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('trace',type=Path);p.add_argument('--speed-bound-m-per-s',required=True)
    p.add_argument('--speed-bound-evidence-id',required=True);p.add_argument('--max-sample-gap-s',required=True)
    p.add_argument('--data-origin',required=True);p.add_argument('--configuration-id',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('Output exists; preserve prior trace-bound receipts')
    result=bound_trace(a.trace,speed_bound_m_per_s=a.speed_bound_m_per_s,
                      speed_bound_evidence_id=a.speed_bound_evidence_id,max_sample_gap_s=a.max_sample_gap_s,
                      data_origin=a.data_origin,configuration_id=a.configuration_id)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'conditional_continuous_peak_upper_m':result['conditional_continuous_peak_upper_m'],
                      'hardware_execution_enabled':False}))


if __name__=='__main__':main()
