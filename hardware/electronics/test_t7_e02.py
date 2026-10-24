"""Five-channel and observer integration checks; no hardware/SDK access."""
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('t7_test_helpers',Path(__file__).with_name('test_t7_capture.py'))
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
t7=helpers.t7


class FiveChannelLJM(helpers.MockLJM):
    def namesToAddresses(self,n,names):return ([0,4,8,12,16],[3]*5)
    def eStreamRead(self,handle):
        self.clock.now+=self.scans/self.rate;self.reads+=1
        return [value for _ in range(self.scans) for value in (1.25,3.,self.voltage,2.5,.75)],0,0


class E02Observer(unittest.TestCase):
    def test_fifth_channel_preserves_native_temperature_and_observation_clock(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=helpers.MockClock();sdk=FiveChannelLJM(clock);events=[]
            result=t7.capture(tmp,execute=True,identifier='470123456',duration_s=12,
                profile='E02',ljm_module=sdk,clock=clock,sleep=clock.sleep,observer=events.append)
            self.assertEqual(result['status'],'CAPTURE_COMPLETED')
            self.assertEqual(result['configuration']['scan_list'],['AIN0','AIN2','AIN4','AIN6','AIN8'])
            with (Path(tmp)/'raw_slow_volts.csv').open() as stream:rows=list(csv.DictReader(stream))
            self.assertEqual(rows[0]['raw_temperature_V'],'0.75')
            self.assertNotIn('temperature_C',rows[0])
            self.assertEqual(events[0]['kind'],'start');self.assertEqual(events[-1]['kind'],'end')
            self.assertLessEqual(events[0]['stream_start_host_before_s'],events[0]['stream_start_host_after_s'])
            blocks=[e for e in events if e['kind']=='block']
            self.assertEqual(sum(len(e['rows']) for e in blocks),len(rows))
            self.assertEqual(blocks[0]['rows'][0]['raw_temperature_V'],.75)

    def test_failed_live_observer_retains_native_block_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=helpers.MockClock();sdk=FiveChannelLJM(clock)
            def observer(event):
                if event['kind']=='block':raise RuntimeError('display disconnected')
            result=t7.capture(tmp,execute=True,identifier='470123456',duration_s=12,
                profile='E02',ljm_module=sdk,clock=clock,sleep=clock.sleep,observer=observer)
            self.assertEqual(result['status'],'CAPTURE_FAILED');self.assertEqual(result['rows'],5)
            with (Path(tmp)/'raw_slow_volts.csv').open() as stream:self.assertEqual(len(list(csv.DictReader(stream))),5)
            self.assertTrue(result['observer_errors']);self.assertTrue(result['quality_requires_review'])
            self.assertEqual(sdk.calls[-2:],[('stop',),('close',)])

if __name__=='__main__':unittest.main()
