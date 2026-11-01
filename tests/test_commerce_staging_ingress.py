import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commerce_staging_ingress import backend_address,render,render_http,certificate_name,HOSTS

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

    def test_test2_certificate_and_closed_default(self):
        hosts=tuple(h.replace('-test.','-test2.') for h in HOSTS)
        text=render('172.30.1.3',hosts)
        self.assertIn('/commerce-staging-test2/fullchain.pem',text)
        self.assertIn('if ($host != shop-test2.danks.store)',text)
        self.assertIn('location / { return 403; }',text)
        self.assertNotIn('shop-test.danks.store',text)
        self.assertNotIn('proxy_pass',render_http(hosts))

    def test_browser_requires_explicit_opt_in_and_retains_service_host_gate(self):
        hosts=tuple(h.replace('-test.','-test2.') for h in HOSTS)
        text=render('172.30.1.3',hosts,True)
        self.assertIn('location = /wp-cron.php { return 403; }',text)
        self.assertIn('location = /xmlrpc.php { return 403; }',text)
        self.assertIn('location / {\n  if ($host != shop-test2.danks.store) { return 403; }',text)
        self.assertIn('if ($http_authorization = "") { return 401; }',text)

    def test_production_mixed_or_injected_host_groups_refused(self):
        for hosts in (('shop.danks.store',),HOSTS[:-1]+('shop-test2.danks.store',),HOSTS[:-1]+('shop-test.danks.store; include x;',)):
            with self.assertRaises(ValueError):certificate_name(hosts)
            with self.assertRaises(ValueError):render_http(hosts)
            with self.assertRaises(ValueError):render('172.30.1.3',hosts,True)

if __name__=='__main__':unittest.main()
