import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from instrument.synchronize import fit_clock
from instrument.task_features import _clock_provenance


class TaskClockLineage(unittest.TestCase):
    def fixture(self,root):
        run={'data_origin':'physical_measurement','sync':{},'provenance':{}}
        for stem,key in [('logger','logger_time_s'),('drive','drive_time_s')]:
            markers=root/(stem+'_markers.csv')
            with markers.open('w',newline='') as stream:
                writer=csv.writer(stream);writer.writerow([key,'audio_time_s']);writer.writerows([(0,0),(10,10),(21,21)])
            clock=fit_clock(markers,source_key=key,declared_error_s='.001',source_pick_error_s='0',audio_pick_error_s='.0001',method='synthetic test clock')
            file=root/(stem+'_clock.json');file.write_text(json.dumps(clock))
            run['provenance'][stem+'_clock_sha256']=hashlib.sha256(file.read_bytes()).hexdigest()
            mapping={k:clock[k] for k in ('offset_s','drift_rate','sync_residual_s','method')}
            if stem=='logger':run['sync'].update(mapping)
            else:run['sync']['drive_to_audio']=mapping
        return run

    def test_matching_raw_markers_and_run_clock_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=self.fixture(root);_clock_provenance(run,root/'run.json')
            run['sync']['drive_to_audio']['offset_s']='.1'
            with self.assertRaisesRegex(ValueError,'disagrees'):_clock_provenance(run,root/'run.json')

    def test_marker_bytes_cannot_change_after_sealing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);run=self.fixture(root)
            with (root/'logger_markers.csv').open('a') as stream:stream.write('22,22\n')
            with self.assertRaisesRegex(ValueError,'SHA256'):_clock_provenance(run,root/'run.json')

    def test_physical_clock_provenance_is_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            run={'data_origin':'physical_measurement','sync':{},'provenance':{}}
            with self.assertRaisesRegex(ValueError,'requires sealed clock'):_clock_provenance(run,Path(tmp)/'run.json')
            run['data_origin']='synthetic';_clock_provenance(run,Path(tmp)/'run.json')

if __name__=='__main__':unittest.main()
