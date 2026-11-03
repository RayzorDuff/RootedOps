"""Offline recurring inventory state, idempotence and failure regression tests."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import commerce_woo_recurring as c

def example():
    rows=[]
    woo={}
    for mp,sku,ecwid in c.EXPECTED:
        row={"mp_id":mp,"sku":sku,"ecwid_id":ecwid,"physical":0,"qty":0}
        rows.append(row)
        woo[mp]={"id":mp+1000,"qty":0,"row":row}
    return sorted(rows,key=lambda r:r["mp_id"]),woo

class RecurringTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=c.connect(Path(self.tmp.name)/"state.sqlite3",create=True)
        self.rows,self.woo=example()
        c.bootstrap(self.db,self.rows,self.woo)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_idempotent_noop(self):
        self.assertEqual(c.preview(self.db,self.rows,self.woo),[])
        self.assertEqual(c.pending(self.db),0)
        self.assertEqual(len(c.state_map(self.db)),24)

    def test_source_change_staged_then_ack(self):
        row=dict(self.rows[0],physical=3,qty=3)
        newer=[row]+self.rows[1:]
        changed=c.preview(self.db,newer,self.woo)
        self.assertEqual(len(changed),1)
        c.one_write.snapshot=newer
        with patch.object(c,"source",return_value=newer),patch.object(c,"owned_product",
            side_effect=[{"stock_quantity":0},{"stock_quantity":3}]),patch(
            "ecwid_migrate.api",return_value={"id":self.woo[row["mp_id"]]["id"]}) as request:
            c.one_write(self.db,*changed[0],"TEST",None)
        self.assertEqual(request.call_count,1)
        self.assertEqual(c.pending(self.db),0)
        self.assertEqual(c.state_map(self.db)[row["mp_id"]]["revision"],2)
        self.woo[row["mp_id"]]["qty"]=3
        self.assertEqual(c.preview(self.db,newer,self.woo),[])

    def test_uncertain_http_stops_replay(self):
        row=dict(self.rows[0],physical=1,qty=1)
        newer=[row]+self.rows[1:]
        ch=c.preview(self.db,newer,self.woo)[0]
        c.one_write.snapshot=newer
        with patch.object(c,"source",return_value=newer),patch.object(c,"owned_product",
            return_value={"stock_quantity":0}),patch(
            "ecwid_migrate.api",side_effect=RuntimeError("network lost")):
            with self.assertRaisesRegex(RuntimeError,"network lost"):
                c.one_write(self.db,*ch,"TEST",None)
        self.assertEqual(c.pending(self.db),1)
        with self.assertRaisesRegex(ValueError,"unresolved attempt"):
            c.preview(self.db,newer,self.woo)

    def test_recover_confirmed_remote_write(self):
        row=dict(self.rows[0],physical=2,qty=2)
        newer=[row]+self.rows[1:]
        ch=c.preview(self.db,newer,self.woo)[0]
        c.one_write.snapshot=newer
        with patch.object(c,"source",return_value=newer),patch.object(c,"owned_product",
            side_effect=[{"stock_quantity":0},RuntimeError("response lost")]),patch(
            "ecwid_migrate.api",return_value={"id":self.woo[row["mp_id"]]["id"]}):
            with self.assertRaisesRegex(RuntimeError,"response lost"):
                c.one_write(self.db,*ch,"TEST",None)
        self.assertEqual(c.pending(self.db),1)
        self.woo[row["mp_id"]]["qty"]=2
        c.reconcile(self.db,newer,self.woo)
        self.assertEqual(c.pending(self.db),0)
        self.assertEqual(c.state_map(self.db)[row["mp_id"]]["revision"],2)
        self.assertEqual(c.preview(self.db,newer,self.woo),[])

    def test_reject_drift_before_write(self):
        newer=[dict(self.rows[0],physical=1,qty=1)]+self.rows[1:]
        ch=c.preview(self.db,newer,self.woo)[0]
        c.one_write.snapshot=newer
        with patch.object(c,"source",return_value=self.rows),patch("ecwid_migrate.api") as request:
            with self.assertRaisesRegex(ValueError,"MP source changed"):
                c.one_write(self.db,*ch,"TEST",None)
        request.assert_not_called()
        self.assertEqual(c.pending(self.db),0)

    def test_reject_external_stock_drift(self):
        self.woo[self.rows[0]["mp_id"]]["qty"]=9
        with self.assertRaisesRegex(ValueError,"Woo target diverged"):
            c.preview(self.db,self.rows,self.woo)

if __name__=="__main__":
    unittest.main()
