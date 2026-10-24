"""Mock-only acquisition tests. No LabJack SDK or hardware is required."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('t7_capture',Path(__file__).with_name('t7_capture.py'))
t7=importlib.util.module_from_spec(spec)
spec.loader.exec_module(t7)


class MockClock:
    def __init__(self): self.now=100.
    def __call__(self): return self.now
    def sleep(self,seconds): self.now+=seconds


class MockLJM:
    def __init__(self,clock,rate=49.8,fail_read=None):
        self.clock,self.rate,self.fail_read=clock,rate,fail_read
        self.calls=[];self.reads=0;self.voltage=.05
    def writeLibraryConfigS(self,*args): self.calls.append(('library',args))
    def openS(self,*args): self.calls.append(('open',args));return 17
    def getHandleInfo(self,h): return (7,1,470123456,0,0,64)
    def namesToAddresses(self,n,names): return ([0,4,8,12],[3]*4)
    def eWriteNames(self,h,n,names,values): self.calls.append(('config',dict(zip(names,values))))
    def eWriteName(self,h,name,value):
        self.calls.append(('write',name,value,self.clock()))
        if name=='DAC0':self.voltage=value
    def eStreamStart(self,h,scans,n,addresses,rate):
        self.scans=scans
        self.calls.append(('start',scans,n,addresses,rate));return self.rate
    def eStreamRead(self,h):
        if self.reads==self.fail_read:raise RuntimeError('mock buffer full')
        values=[]
        for j in range(self.scans):
            row=[1.25,3.,self.voltage,2.5]
            if self.reads==0 and j==2:row=[-9999.]*4
            if self.reads==0 and j==3:row[1]=-9999.
            values.extend(row)
        self.clock.now+=self.scans/self.rate
        backlogs=(3,4) if self.reads==0 else (0,0)
        self.reads+=1
        return values,*backlogs
    def eStreamStop(self,h): self.calls.append(('stop',))
    def close(self,h): self.calls.append(('close',))


class T7CaptureTests(unittest.TestCase):
    def test_dry_run_never_imports_sdk_or_opens_device(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(t7.importlib,'import_module',side_effect=AssertionError('SDK import')):
            result=t7.capture(Path(temp)/'not_created')
            self.assertEqual(result['mode'],'DRY_RUN')
            self.assertFalse(result['hardware_accessed'])
            self.assertFalse((Path(temp)/'not_created').exists())
            self.assertEqual(result['requested_scan_rate_Hz'],50)
            self.assertEqual(result['stream_resolution_index'],7)

    def test_actual_rate_gap_rows_and_backlog_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=MockClock();sdk=MockLJM(clock)
            result=t7.capture(temp,identifier='470123456',execute=True,duration_s=12,ljm_module=sdk,clock=clock,sleep=clock.sleep)
            self.assertEqual(result['status'],'CAPTURE_COMPLETED')
            self.assertEqual(result['actual_scan_rate_Hz'],49.8)
            with (Path(temp)/'raw_slow_volts.csv').open() as stream:
                rows=list(csv.DictReader(stream))
            self.assertEqual(len(rows),600)
            self.assertEqual([int(r['sample_index']) for r in rows],list(range(600)))
            self.assertAlmostEqual(float(rows[-1]['time_s']),599/49.8)
            self.assertNotAlmostEqual(float(rows[-1]['time_s']),599/50,places=2)
            self.assertEqual(rows[2]['raw_force_V'],'-9999')
            self.assertEqual(rows[3]['raw_displacement_V'],'-9999')
            self.assertEqual(result['dummy_values'],5)
            self.assertEqual(result['rows_with_gaps'],2)
            self.assertEqual(result['max_device_scan_backlog'],3)
            self.assertEqual(result['max_ljm_scan_backlog'],4)
            self.assertTrue(result['backlog_nonzero'])
            self.assertTrue(result['quality_requires_review'])
            self.assertNotIn('force_N',rows[0])
            self.assertFalse(result['physical_calibration_verified'])
            self.assertIn(('stop',),sdk.calls)
            self.assertEqual(sdk.calls[-1],('close',))

    def test_marker_outputs_are_bounded_and_hold_at_least_requested_width(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=MockClock();sdk=MockLJM(clock)
            result=t7.capture(temp,identifier='470123456',execute=True,duration_s=12,ljm_module=sdk,clock=clock,sleep=clock.sleep)
            writes=[c for c in sdk.calls if c[0]=='write']
            self.assertTrue(all(c[1]=='DAC0' and c[2] in (.05,1.) for c in writes))
            starts=[];widths=[]
            for command in result['marker_commands']:
                if command['reason'].startswith('pulse_start_'):
                    starts.append(command['host_monotonic_since_stream_start_s'])
                if command['reason'].startswith('pulse_end_'):
                    widths.append(command['host_monotonic_since_stream_start_s']-starts[-1])
            self.assertEqual(result['marker_pulse_commands_completed'],len(result['configuration']['marker_pulses']))
            self.assertTrue(result['marker_schedule_complete'])
            self.assertTrue(all(width>=.3 for width in widths))
            self.assertGreater(max(widths)-min(widths),.1)
            self.assertFalse(result['marker_observed_in_both_records'])

    def test_read_error_keeps_partial_rows_and_resets_marker_before_close(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=MockClock();sdk=MockLJM(clock,fail_read=3)
            result=t7.capture(temp,identifier='470123456',execute=True,duration_s=12,ljm_module=sdk,clock=clock,sleep=clock.sleep)
            self.assertEqual(result['status'],'CAPTURE_FAILED')
            self.assertEqual(result['rows'],15)
            self.assertEqual(result['error']['message'],'mock buffer full')
            self.assertTrue(result['quality_requires_review'])
            self.assertEqual([c for c in sdk.calls if c[0]=='write'][-1][2],.05)
            self.assertEqual(sdk.calls[-2:], [('stop',),('close',)])
            self.assertTrue((Path(temp)/'t7_capture.json').is_file())

    def test_slow_dac_write_does_not_shorten_high_plateau(self):
        class DelayedWriteLJM(MockLJM):
            def eWriteName(self,h,name,value):
                if value==1.:
                    self.clock.now+=.2
                super().eWriteName(h,name,value)
        with tempfile.TemporaryDirectory() as temp:
            clock=MockClock();sdk=DelayedWriteLJM(clock)
            t7.capture(temp,identifier='470123456',execute=True,duration_s=12,ljm_module=sdk,clock=clock,sleep=clock.sleep)
            writes=[c for c in sdk.calls if c[0]=='write']
            pending=None;measured=[]
            for _,_,value,at in writes:
                if value==1.:pending=at
                elif pending is not None:
                    measured.append(at-pending);pending=None
            self.assertGreater(len(measured),3)
            self.assertTrue(all(width>=.3 for width in measured))

    def test_execute_requires_exact_serial_and_preserves_existing_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            for serial in (None,'ANY','0','address'):
                with self.subTest(serial=serial),self.assertRaises(ValueError):
                    t7.capture(temp,identifier=serial,execute=True,ljm_module=object())
            (Path(temp)/'raw_slow_volts.csv').write_text('old evidence')
            with self.assertRaises(ValueError):
                t7.capture(temp,identifier='470123456',execute=True,ljm_module=object())
            self.assertEqual((Path(temp)/'raw_slow_volts.csv').read_text(),'old evidence')

    def test_unexpected_opened_device_is_closed_without_output_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            clock=MockClock();sdk=MockLJM(clock)
            sdk.getHandleInfo=lambda handle:(7,1,470000000,0,0,64)
            result=t7.capture(temp,identifier='470123456',execute=True,duration_s=12,ljm_module=sdk,clock=clock,sleep=clock.sleep)
            self.assertEqual(result['status'],'CAPTURE_FAILED')
            self.assertFalse(any(c[0] in ('write','config','start') for c in sdk.calls))
            self.assertEqual(sdk.calls[-1],('close',))

    def test_continuous_nonuniform_cadence_has_no_long_interior_gap(self):
        plan=t7.configuration_plan(180)
        pulses=plan['marker_pulses']
        starts=[p['planned_onset_s'] for p in pulses]
        gaps=[b-a for a,b in zip(starts,starts[1:])]
        self.assertGreater(len(pulses),100)
        self.assertLessEqual(max(gaps),2)
        self.assertGreater(max(gaps)-min(gaps),.5)
        for window_start in range(171):
            # Every 10-second window has markers outside its central six
            # seconds; actual readbacks must still validate this in hardware.
            self.assertTrue(any(window_start<=s<=window_start+2 for s in starts))
            self.assertTrue(any(window_start+8<=s<=window_start+10 for s in starts))

    def test_planned_six_pulse_identity_is_unique_and_has_end_margin(self):
        for duration in (30,180,7200):
            with self.subTest(duration=duration):
                plan=t7.configuration_plan(duration)
                pulses=plan['marker_pulses']
                starts=[round(p['planned_onset_s']*1000) for p in pulses]
                widths=[round(p['minimum_high_s']*1000) for p in pulses]
                signatures=[(tuple(widths[i:i+6]),tuple(starts[j+1]-starts[j] for j in range(i,i+5)))
                            for i in range(len(pulses)-5)]
                self.assertEqual(len(signatures),len(set(signatures)))
                self.assertGreaterEqual(plan['final_planned_low_margin_s'],1.)
                self.assertLessEqual(plan['nominal_marker_max_leading_edge_gap_s'],2.)
                self.assertTrue(all(starts[i+1]-starts[i]-widths[i]>=300 for i in range(len(pulses)-1)))

    def test_overdue_reads_and_writes_preserve_high_and_low_minima(self):
        class DelayedLJM(MockLJM):
            def eWriteName(self,h,name,value):
                self.clock.now+=.11 if value==1. else .07
                super().eWriteName(h,name,value)
            def eStreamRead(self,h):
                result=super().eStreamRead(h)
                self.clock.now+=.9 if self.reads%7==0 else .015
                return result
        with tempfile.TemporaryDirectory() as temp:
            clock=MockClock();sdk=DelayedLJM(clock)
            result=t7.capture(temp,identifier='470123456',execute=True,duration_s=30,
                              ljm_module=sdk,clock=clock,sleep=clock.sleep)
            transitions=[]
            for command in sdk.calls:
                if command[0]=='write' and (not transitions or command[2]!=transitions[-1][0]):
                    transitions.append((command[2],command[3]))
            self.assertGreater(len(transitions),10)
            for (_,previous),(_,current) in zip(transitions,transitions[1:]):
                self.assertGreaterEqual(current-previous,.3-1e-12)
            self.assertFalse(result['marker_observed_in_both_records'])


if __name__=='__main__':unittest.main()
