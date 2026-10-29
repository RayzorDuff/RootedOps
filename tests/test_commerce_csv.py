import csv
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'integrations/commerce'))
import ecwid_csv
from ecwid_migrate import plan

class CsvTests(unittest.TestCase):
    def test_semicolons_multiline_html_and_order_lines_are_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            products=Path(d)/'products.csv';orders=Path(d)/'orders.csv'
            rows=[{'product_id':'1','name':'Test; mushroom','sku':'00001','description':'<p>One; two</p>\n<p>More</p>','price':'12.50','enabled':'no','seo_title':'Test SEO'}]
            lines=[{'order_number':'ABC','email':'synthetic@example.invalid','sku':sku,'name':'Test','quantity':'1','price':'12.50','order_total':'25.00','timestamp':'2026-10-29'} for sku in ('00001','00002')]
            for path,data in [(products,rows),(orders,lines)]:
                with path.open('w',newline='',encoding='utf-8-sig') as f:
                    w=csv.DictWriter(f,fieldnames=list(data[0]),delimiter=';');w.writeheader();w.writerows(data)
            source=ecwid_csv.convert(products,orders,'95802503');result=plan(source)
            self.assertEqual(result['errors'],[])
            self.assertEqual(source['products'][0]['sku'],'00001')
            self.assertEqual(source['products'][0]['description'],rows[0]['description'])
            self.assertFalse(source['products'][0]['enabled'])
            self.assertEqual(len(source['orders']),1);self.assertEqual(len(source['orders'][0]['items']),2)
            self.assertTrue(source['orders'][0]['id'].startswith('csv-order-number:'))
            self.assertTrue(source['customers'][0]['id'].startswith('csv-email:'))

    def test_invalid_decimal_is_rejected(self):
        for value in ('NaN','Infinity','not-a-price'):
            with self.assertRaises(ValueError):ecwid_csv.decimal_text(value)
