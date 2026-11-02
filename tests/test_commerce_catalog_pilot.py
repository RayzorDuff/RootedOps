import sys
import unittest
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/commerce'))
from ecwid_migrate import plan
from migrate_reviewed import select_catalog
from ecwid_csv import convert


class PilotSelectionTests(unittest.TestCase):
    def test_catalog_only_export_does_not_assert_empty_order_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'products.csv'
            path.write_text('name;sku;product_id;description;price\nExample;00001;7;Description;9.95\n')
            source=convert(path,None,'synthetic')
        self.assertEqual(source['products'][0]['sku'],'00001')
        self.assertFalse(source['_csv_manifest']['orders_export_supplied'])
        self.assertEqual(list(source['_csv_manifest']['files']),['products.csv'])
        self.assertEqual(source['orders'],[])

    def test_variation_selection_keeps_entire_family_and_export_identity(self):
        source=plan({'store_id':'synthetic','products':[
            {'id':1,'sku':'PARENT','_combinations':[{'id':2,'sku':'SMALL'},{'id':3,'sku':'LARGE'}]},
            {'id':4,'sku':'OTHER'}]})
        original=list(source['products'])
        selected=select_catalog(source,['ecwid:synthetic:product:1:variation:2'])
        self.assertEqual([p['content']['item'] for p in selected['products']],['PARENT','SMALL','LARGE'])
        self.assertEqual(selected['source_sha256'],source['source_sha256'])
        selected['products'][0]['content']['public_title']='Changed'
        self.assertEqual(source['products'],original)

    def test_missing_identity_and_orphan_refused(self):
        source=plan({'store_id':'synthetic','products':[{'id':1,'sku':'PARENT',
            '_combinations':[{'id':2,'sku':'SMALL'}]}]})
        with self.assertRaisesRegex(ValueError,'Unknown'):select_catalog(source,['missing'])
        source['products']=source['products'][1:]
        with self.assertRaisesRegex(ValueError,'no source template'):
            select_catalog(source,['ecwid:synthetic:product:1:variation:2'])


if __name__=='__main__':unittest.main()
