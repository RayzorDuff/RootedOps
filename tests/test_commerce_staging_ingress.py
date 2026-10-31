import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commerce_staging_ingress import backend_address,render

class StagingIngressTests(unittest.TestCase):
    def fixture(self):
        return {'Config':{'Labels':{'com.docker.compose.project':'dank-store-test','com.docker.compose.service':'dank-wordpress'}},'State':{'Running':True},'Image':'reviewed','NetworkSettings':{'Networks':{'dank-store-test_default':{'IPAddress':'172.30.1.3','NetworkID':'fixture'}}}}
    def test_internal_reviewed_backend(self):
        self.assertEqual(backend_address(self.fixture(),{'Internal':True,'Id':'fixture'},'reviewed'),'172.30.1.3')
    def test_external_network_or_drift_refused(self):
        for network in ({'Internal':False,'Id':'fixture'},{'Internal':True,'Id':'other'}):
            with self.assertRaises(ValueError):backend_address(self.fixture(),network,'reviewed')
        c=self.fixture();c['NetworkSettings']['Networks']['external']={}
        with self.assertRaises(ValueError):backend_address(c,{'Internal':True,'Id':'fixture'},'reviewed')
    def test_wrong_application_or_image_refused(self):
        c=self.fixture();c['Config']['Labels']['com.docker.compose.project']='production'
        with self.assertRaises(ValueError):backend_address(c,{'Internal':True,'Id':'fixture'},'reviewed')
        with self.assertRaises(ValueError):backend_address(self.fixture(),{'Internal':True,'Id':'fixture'},'new-image')
    def test_address_injection_and_public_targets_refused(self):
        for value in ('8.8.8.8','127.0.0.1','0.0.0.0','172.30.1.3; include other;'):
            with self.assertRaises(ValueError):render(value)

if __name__=='__main__':unittest.main()
