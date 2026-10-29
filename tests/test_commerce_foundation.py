import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'erpnext/apps/rootedops_commerce'))
from rootedops_commerce.contract import mapping_key, compose_projection
spec = importlib.util.spec_from_file_location('migration', ROOT / 'integrations/commerce/ecwid_migrate.py')
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class CommerceTests(unittest.TestCase):
    def source(self):
        return {'store_id': '95802503', 'products': [{'id': 42, 'sku': 'BLUE', 'name': 'Blue',
                'description': '<p>Culture</p>', 'seoTitle': 'Blue SEO', 'price': 12.5,
                'imageUrl': 'https://example.org/image.png', '_combinations': []}],
                'customers': [{'id': 9, 'email': 'synthetic@example.org'}],
                'orders': [{'id': 'TEST-1', 'paymentStatus': 'PAID', 'total': 12.5}],
                'categories': [{'id': 3, 'name': 'Cultures'}]}

    def test_source_preserved_and_history_has_no_side_effects(self):
        source = self.source()
        result = migration.plan(source)
        self.assertEqual(result['errors'], [])
        self.assertEqual(json.loads(result['products'][0]['content']['source_payload'])['product'], source['products'][0])
        self.assertEqual(result['products'][0]['woocommerce']['status'], 'draft')
        self.assertNotIn('stock_quantity', result['products'][0]['woocommerce'])
        self.assertEqual([r['record_type'] for r in result['archives']], ['customer','order','category','profile'])
        self.assertEqual(json.loads(result['archives'][1]['payload']), source['orders'][0])
        self.assertEqual(migration.plan(source), result)

    def test_duplicate_missing_sku_blocks_apply(self):
        source = self.source();source['products'] += [{'id': 43, 'sku': 'BLUE'}, {'id': 44}]
        result = migration.plan(source)
        self.assertEqual(len(result['errors']), 2)
        with self.assertRaises(ValueError):
            migration.apply_erp(result, 'https://erp-test.danks.store', 'unused', {})

    def test_variants_have_separate_identity_and_parent(self):
        source = self.source();source['products'][0]['_combinations'] = [{'id': 8, 'sku': 'BLUE-20', 'options': [{'name': 'Size', 'value': '20 ml'}]}]
        result = migration.plan(source)
        self.assertEqual(result['products'][1]['item']['parent_sku'], 'BLUE')
        self.assertTrue(result['products'][1]['source_key'].endswith(':variation:8'))
        self.assertEqual(result['products'][1]['mapping']['external_variation_id'], '8')

    def test_mapping_identity_is_unambiguous_and_scoped(self):
        self.assertNotEqual(mapping_key('a','b:c','d'), mapping_key('a','b','c:d'))
        self.assertNotEqual(mapping_key('ecwid','one','1'),mapping_key('ecwid','two','1'))
        self.assertEqual(mapping_key(' Ecwid ','one','1'), mapping_key('ecwid','one','1'))
        with self.assertRaises(ValueError):mapping_key('', 'one', '1')

    def test_inventory_boundary(self):
        c={'item':'BLUE','channel_overrides':[]};m={'item':'BLUE','mushroomprocess_ecommerce_id':'5','provider':'woocommerce','site_key':'test'}
        i={'erp_item_code':'BLUE','ecommerce_id':5,'desired_quantity':4}
        self.assertEqual(compose_projection(c,m,i)['quantity'],4)
        for q in (-1, 1.5, True, '4'):
            with self.assertRaises(ValueError):compose_projection(c,m,dict(i,desired_quantity=q))
        with self.assertRaises(ValueError):compose_projection(c,m,dict(i,erp_item_code='WRONG'))

    def test_pagination_detects_incomplete_and_duplicate(self):
        responses = iter([{'total':2,'items':[{'id':1}]},{'total':2,'items':[]}])
        with self.assertRaises(ValueError):migration.pages(lambda _: next(responses), 'products')
        with self.assertRaises(ValueError):migration.pages(lambda _: {'total':2,'items':[{'id':1},{'id':1}]},'products')

    def test_permission_api_has_no_guest_or_bypass(self):
        code=(ROOT/'erpnext/apps/rootedops_commerce/rootedops_commerce/api.py').read_text()
        self.assertNotIn('allow_guest',code);self.assertNotIn('ignore_permissions',code)
        self.assertIn('check_permission("read")',code)

if __name__ == '__main__':unittest.main()

class ChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0,str(ROOT/'integrations/commerce'))
        import channel
        cls.channel=channel

    def record(self):
        return migration.plan(CommerceTests().source())['products'][0]

    def test_unowned_sku_cannot_be_overwritten(self):
        calls=[]
        def request(*args):
            calls.append(args)
            return [{'id':2,'sku':'BLUE','status':'draft','meta_data':[]}]
        with self.assertRaises(ValueError):
            self.channel.upsert_draft('https://shop-test.danks.store','unused',self.record(),request=request)
        self.assertEqual(len(calls),1)

    def test_retries_resolve_owned_draft(self):
        r=self.record();calls=[]
        def request(*args):
            calls.append(args)
            if len(calls)==1:return [{'id':2,'sku':'BLUE','status':'draft','meta_data':[{'key':'_rootedops_source_key','value':r['source_key']}]}]
            return {'id':2}
        self.assertEqual(self.channel.upsert_draft('https://shop-test.danks.store','unused',r,request=request),{'id':2})
        self.assertEqual(calls[1][2],'PUT')
        self.assertEqual(calls[1][3]['status'],'draft')
        self.assertNotIn('stock_quantity',calls[1][3])

    def test_variant_requires_reviewed_parent_and_attributes(self):
        r=self.record();r['item']['parent_sku']='PARENT'
        with self.assertRaises(ValueError):self.channel.draft_payload(r)

    def test_no_production_target(self):
        with self.assertRaises(ValueError):
            self.channel.upsert_draft('https://danks.store','unused',self.record())

class StagingTests(unittest.TestCase):
    def test_renderer_isolates_services_and_never_overwrites(self):
        import tempfile
        import yaml
        spec=importlib.util.spec_from_file_location('staging',ROOT/'scripts/commerce_staging.py')
        staging=importlib.util.module_from_spec(spec);spec.loader.exec_module(staging)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'config';staging.render(out)
            result=yaml.safe_load((out/'compose.yml').read_text())
            self.assertEqual(set(result['services']),set(staging.SERVICES))
            for service in result['services'].values():
                for port in service.get('ports',[]):self.assertTrue(port.startswith('127.0.0.1:'))
            self.assertEqual((out/'.env').stat().st_mode & 0o777,0o600)
            self.assertNotIn('45.33.107.185',(out/'.env').read_text())
            with self.assertRaises(ValueError):staging.render(out)

class MediaTests(unittest.TestCase):
    def test_original_gallery_and_variants_are_retained(self):
        sys.path.insert(0,str(ROOT/'integrations/commerce'))
        import media
        source={'products':[{'imageUrl':'https://cdn.example/a','originalImageUrl':'https://cdn.example/original',
            'galleryImages':[{'url':'https://cdn.example/b'}],
            '_combinations':[{'imageUrl':'https://cdn.example/c'}]}]}
        self.assertEqual(len(media.media_urls(source)),4)
        for url in ('http://cdn.example/a','https://user:secret@cdn.example/a','https://other.example/a'):
            with self.assertRaises(ValueError):media.validate_url(url,{'cdn.example'})

class SnapshotConnectorTests(unittest.TestCase):
    def test_join_uses_erp_content_and_operational_quantity(self):
        sys.path.insert(0,str(ROOT/'integrations/commerce'))
        import sync
        row={'ecommerce_id':7,'erp_item_code':'BLUE','desired_quantity':3}
        catalog={'item':{'disabled':False},'content':{'item':'BLUE','publication_status':'Published',
                 'public_title':'Canonical title','channel_overrides':[]}}
        mapping={'item':'BLUE','provider':'woocommerce','site_key':'test','external_sku':'BLUE'}
        record=sync.prepare(row,catalog,mapping)
        self.assertEqual(record['woocommerce']['name'],'Canonical title')
        self.assertEqual(record['woocommerce']['stock_quantity'],3)
        self.assertEqual(record['woocommerce']['status'],'draft')
        catalog['content']['publication_status']='Draft'
        with self.assertRaises(ValueError):sync.prepare(row,catalog,mapping)
