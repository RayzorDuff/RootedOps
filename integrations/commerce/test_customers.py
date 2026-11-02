"""Regression for installed WooCommerce protected-user-meta filtering."""
import unittest
from customers import upsert_customer


class CustomerReplay(unittest.TestCase):
    def test_realistic_protected_meta_filter_preserves_replay(self):
        rows=[]
        def request(url,auth,method='GET',payload=None):
            if method=='POST':
                rows.append(dict(payload,id=2,meta_data=[m for m in payload['meta_data'] if not m['key'].startswith('_')]))
                return rows[0]
            return rows[0] if '/customers/2?' in url else rows
        args=('https://shop-test2.danks.store','test','synthetic:customer',{'email':'synthetic@example.invalid'})
        first=upsert_customer(*args,mail_sink_verified=True,request=request)
        again=upsert_customer(*args,mail_sink_verified=True,request=request)
        self.assertEqual(first['external_customer_id'],again['external_customer_id'])
        self.assertTrue(first['created']);self.assertFalse(again['created']);self.assertEqual(len(rows),1)

    def test_unowned_email_still_rejected(self):
        with self.assertRaisesRegex(ValueError,'unowned'):
            upsert_customer('https://shop-test2.danks.store','test','source',{'email':'synthetic@example.invalid'},
                            mail_sink_verified=True,request=lambda *a:[{'id':2,'email':'synthetic@example.invalid','meta_data':[]}])

    def test_missing_write_identity_fails_before_claiming_success(self):
        def request(url,auth,method='GET',payload=None):
            return {'id':2,'meta_data':[]} if method=='POST' or '/customers/2?' in url else []
        with self.assertRaisesRegex(ValueError,'not persisted'):
            upsert_customer('https://shop-test2.danks.store','test','source',{'email':'synthetic@example.invalid'},
                            mail_sink_verified=True,request=request)


if __name__=='__main__':unittest.main()
