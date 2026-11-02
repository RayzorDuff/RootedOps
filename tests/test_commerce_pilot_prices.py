import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from commerce_pilot_prices import EXPECTED,pilot_records
from ecwid_migrate import plan


def fixture():
    return {'errors':[],'products':[{'source_key':'ecwid:95802503:product:'+identity,
        'content':{'item':sku},'mapping':{'external_product_id':identity,'external_sku':sku,
            'provider':'ecwid','site_key':'95802503'},'price':rate,'item':{}}
        for identity,(sku,rate) in EXPECTED.items()]}


class PilotPriceTests(unittest.TestCase):
    def test_original_gallery_images_deduplicate_resized_primary(self):
        product={'id':1,'sku':'SYN','imageUrl':'https://cdn.example/resized.jpg',
            'originalImageUrl':'https://cdn.example/original.png',
            'galleryImages':[{'url':'https://cdn.example/original.png'},
                             {'originalImageUrl':'https://cdn.example/second.png','url':'https://cdn.example/second-small.jpg'}]}
        result=plan({'store_id':'synthetic','products':[product]})
        self.assertEqual([r['source_url'] for r in result['products'][0]['content']['gallery']],
                         ['https://cdn.example/original.png','https://cdn.example/second.png'])

    def test_exact_source_rates_and_decimal_equivalence(self):
        source=fixture();source['products'][0]['price']='14.950'
        self.assertEqual(len(pilot_records(source)),3)

    def test_drift_refused_before_transport(self):
        for field,value in [('price','0'),('source_key','different')]:
            source=fixture();source['products'][0][field]=value
            with self.assertRaises(ValueError):pilot_records(source)
        for change in ('sku','variant','duplicate'):
            source=fixture()
            if change=='sku':source['products'][0]['content']['item']='unowned'
            elif change=='variant':source['products'][0]['item']['has_variants']=True
            else:source['products'][1]=copy.deepcopy(source['products'][0])
            with self.assertRaises(ValueError):pilot_records(source)


if __name__=='__main__':unittest.main()
