"""Source-lineage enforcement with a mocked byte auditor, not physical data."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_experiment_evaluation as fixtures
from evaluation.evaluate import _verify_physical_sources


class AdapterLineage(unittest.TestCase):
    def fixture(self,root):
        row,registration=fixtures.PhysicalCommandBindingTests().fixture(root,'fusion_full')
        row.update(raw_feature_extractor_revision='task-features/1:TEST_ONLY',condition='connected_clay',
            decision_time_s='4.8',action='hold',cost_s={'reset_s':'1'})
        pre=json.loads((root/'pre.json').read_text());post=json.loads((root/'post.json').read_text())
        pre.update(schema='fusion.pre-action-features/1',extractor_revision=row['raw_feature_extractor_revision'],
            run_id=row['run_id'],data_origin='physical_measurement',provenance={'raw_run_sha256':row['raw_run_sha256']},
            cost_s=row['cost_s'],condition=row['condition'],write_protocol=row['write_protocol'],
            policy_arm=row['policy_arm'],decision_time_s=row['decision_time_s'],pre_action_quality_window_end_s='4')
        post.update(schema='fusion.independent-outcome/1',run_id=row['run_id'],data_origin='physical_measurement',
            provenance={'raw_run_sha256':row['raw_run_sha256']},action=row['action'])
        for name,record,key in [('pre.json',pre,'pre_feature_sha256'),('post.json',post,'outcome_record_sha256')]:
            path=root/name;path.write_text(json.dumps(record));row[key]=hashlib.sha256(path.read_bytes()).hexdigest()
        return row,registration

    def check(self,root,row,reg):
        with patch('computing.acquisition.audit_run',return_value={
            'status':'RECORDED_DATA_CHECKS_PASSED','sha256':{'drive_command':'a'*64,'multichannel_audio':'c'*64}}):
            _verify_physical_sources(row,reg,root,{})

    def test_unchanged_adapter_sources_pass_identity_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();row,reg=self.fixture(root);self.check(root,row,reg)

    def test_real_padding_cost_cannot_be_erased_in_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();row,reg=self.fixture(root)
            row['cost_s']={'reset_s':'0'}
            with self.assertRaisesRegex(ValueError,'cost ledger'):self.check(root,row,reg)

    def test_equivalent_exact_cost_representations_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();row,reg=self.fixture(root)
            row['cost_s']={'reset_s':'1.0'};self.check(root,row,reg)

    def test_source_provenance_and_actual_action_stay_bound(self):
        for name,key,value in [('pre.json','run_id','another-run'),('post.json','action','raise5')]:
            with self.subTest(key=key),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp).resolve();row,reg=self.fixture(root)
                path=root/name;record=json.loads(path.read_text());record[key]=value;path.write_text(json.dumps(record))
                row['pre_feature_sha256' if name=='pre.json' else 'outcome_record_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):self.check(root,row,reg)

if __name__=='__main__':unittest.main()
