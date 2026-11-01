from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commerce_test2_upgrade import validate_before,validate_after,OLD_API,NEW_API
class InstalledUpgradeTests(unittest.TestCase):
    def state(self):
        return {'module_version':'0.3.0','package_version':'0.3.0','api_sha256':OLD_API,'flit_available':True,'maintenance_mode':1,'pause_scheduler':1,'outgoing':0,'webhooks':0,'notifications':0,'records':{'Item':{'count':1,'sha256':'baseline'}}}
    def target(self):
        s=self.state();s.update(module_version='0.3.1',package_version='0.3.1',api_sha256=NEW_API);return s
    def test_exact_upgrade(self):validate_after(self.state(),self.target())
    def test_unreviewed_source_refused(self):
        for k,v in [('api_sha256','unknown'),('module_version','0.4.0'),('package_version','0.4.0'),('flit_available',False)]:
            s=self.state();s[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):validate_before(s)
    def test_active_integrations_refused(self):
        for k,v in [('maintenance_mode',0),('pause_scheduler',0),('outgoing',1),('webhooks',1),('notifications',1)]:
            s=self.state();s[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):validate_before(s)
    def test_equal_counts_do_not_hide_changed_records(self):
        s=self.target();s['records']['Item']['sha256']='changed'
        with self.assertRaises(ValueError):validate_after(self.state(),s)
    def test_stale_distribution_refused(self):
        s=self.target();s['package_version']='0.3.0'
        with self.assertRaises(ValueError):validate_after(self.state(),s)
