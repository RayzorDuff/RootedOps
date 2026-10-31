import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import yaml

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commerce_wordpress_offline import inspect

class OfflineWordPressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        (self.root/'TEST_ENVIRONMENT').write_text('rootedops-full-test')
        (self.root/'.env').write_text('ERPNEXT_SITE_NAME=erp-test.danks.store\nDANK_WP_DB_PASSWORD='+('a'*32)+'\nDANK_WP_DB_ROOT_PASSWORD='+('b'*32)+'\n')
        self.config={'name':'dank-store-test','networks':{'default':{'internal':True}},'services':{'dank-wordpress':{'image':'wordpress:7.1.4-php8.3-apache','ports':['127.0.0.1:8097:80']},'dank-wordpress-db':{},'dank-wordpress-cli':{}}}
        self.write_config()
        self.archive=self.root/'woo.zip'
        with zipfile.ZipFile(self.archive,'w') as z:z.writestr('woocommerce/woocommerce.php','<?php\n/*\n * Version: 11.2.1\n */')
        self.digest=hashlib.sha256(self.archive.read_bytes()).hexdigest()
    def write_config(self):
        (self.root/'dank.yml').write_text(yaml.safe_dump(self.config))
    def test_verified_fixture_is_accepted_without_mutation(self):
        before=set(self.root.iterdir());inspect(self.root,self.archive,self.digest)
        self.assertEqual(set(self.root.iterdir()),before)
    def test_tamper_and_archive_traversal_refuse(self):
        with self.assertRaisesRegex(ValueError,'SHA256'):inspect(self.root,self.archive,'0'*64)
        with zipfile.ZipFile(self.archive,'a') as z:z.writestr('woocommerce/../../escape.php','synthetic')
        with self.assertRaisesRegex(ValueError,'Unsafe'):inspect(self.root,self.archive,hashlib.sha256(self.archive.read_bytes()).hexdigest())
    def test_public_ports_or_egress_refuse(self):
        self.config['services']['dank-wordpress']['ports']=['0.0.0.0:8097:80'];self.write_config()
        with self.assertRaisesRegex(ValueError,'Loopback'):inspect(self.root,self.archive,self.digest)
        self.config['services']['dank-wordpress']['ports']=[];self.config['networks']['default']['internal']=False;self.write_config()
        with self.assertRaisesRegex(ValueError,'internal'):inspect(self.root,self.archive,self.digest)
    def test_production_hostname_refuses_before_container_commands(self):
        p=self.root/'.env';p.write_text(p.read_text().replace('erp-test.danks.store','erp.danks.store'))
        with self.assertRaisesRegex(ValueError,'hostname'):inspect(self.root,self.archive,self.digest)

if __name__=='__main__':unittest.main()
