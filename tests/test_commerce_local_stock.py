import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations/commerce'))
spec = importlib.util.spec_from_file_location('local_stock', ROOT / 'scripts/commerce_stock_publish_local.py')
local_stock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local_stock)


class LocalStockTests(unittest.TestCase):
    def config(self):
        return dict(mode='review', woo_origin='https://dankmushrooms.net',
            mp_database='mushroomprocess_bridge', not_before_gmt='2026-11-23T03:02:10',
            automation_enabled=False, published_inventory=[dict(ecommerce_id=n, woo_id=n+100,
                sku=str(n), source_key='source:'+str(n)) for n in range(62,86)])

    def test_wrong_cohort_or_target_is_rejected(self):
        for key,value in [('mode','pilot'),('woo_origin','http://dankmushrooms.net'),
                          ('mp_database','other'),('published_inventory',[])]:
            config=self.config();config[key]=value
            with self.assertRaises(ValueError):local_stock.reviewed_config(config)
        config=self.config();config['published_inventory'][0]['woo_id']=163
        with self.assertRaises(ValueError):local_stock.reviewed_config(config)

    def test_stock_only_run_preserves_manual_accounting_and_records_readback(self):
        config=self.config()
        snapshot=dict(revision=2,products=[dict(woo_id=n+100,available=5,represented={}) for n in range(62,86)])
        receipt=dict(publication=dict(status='published',count=24,revision=2),
            products=[dict(woo_id=n+100,quantity=4,mp_available=5) for n in range(62,86)])
        docker=Mock(return_value=SimpleNamespace(returncode=0,stdout=json.dumps(receipt),stderr=''))
        with TemporaryDirectory() as directory, \
                patch.dict(sys.modules, {'psycopg':SimpleNamespace(connect=Mock()),
                    'psycopg.conninfo':SimpleNamespace(conninfo_to_dict=lambda _: {'dbname':'mushroomprocess_bridge'})}), \
                patch('mp_publication.inventory_snapshot',return_value=snapshot), \
                patch('mp_publication.deliver_dispatches',side_effect=AssertionError('No dispatch delivery')):
            result=local_stock.publish(config,{'COMMERCE_LIVE_MP_DSN':'private-not-for-output'},Path(directory),run=docker)
            self.assertEqual(result,receipt)
            self.assertFalse(config['automation_enabled'])
            self.assertEqual(docker.call_args.args[0][:3],['docker','exec','-i'])
            self.assertNotIn('private-not-for-output',docker.call_args.kwargs['input'])
            self.assertEqual(json.loads((Path(directory)/'last-readback.json').read_text()),receipt)

    def test_failed_woo_write_retains_snapshot_and_does_not_report_success(self):
        docker=Mock(return_value=SimpleNamespace(returncode=1,stdout='',stderr='Woo configuration required'))
        with TemporaryDirectory() as directory, \
                patch.dict(sys.modules, {'psycopg':SimpleNamespace(connect=Mock()),
                    'psycopg.conninfo':SimpleNamespace(conninfo_to_dict=lambda _: {'dbname':'mushroomprocess_bridge'})}), \
                patch('mp_publication.inventory_snapshot',return_value=dict(revision=2,products=[])):
            with self.assertRaises(RuntimeError):
                local_stock.publish(self.config(),{'COMMERCE_LIVE_MP_DSN':'private'},Path(directory),run=docker)
            self.assertTrue((Path(directory)/'last-snapshot.json').exists())
            self.assertFalse((Path(directory)/'last-readback.json').exists())
