"""Offline approval-policy gates for Woo receipt and MP -> ERP dispatch."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"integrations/commerce"))
from tax_policy import validate_policy, load_policy, require_approved_item, SOURCE_SHA
from orders import normalize_woo
from inbox import deliver_one


def policy_doc():
    classes = {"FOOD%03d" % i: "grocery_food" for i in range(40)}
    classes.update({"SUP%03d" % i: "cultivation_supply" for i in range(78)})
    classes["TSHIRT"] = "other_reviewed"
    blocked = ["POS%03d" % i for i in range(13)]
    return {"schema_version":1,"source_sha256":SOURCE_SHA,"store_id":"95802503",
            "reviewer":"Owner","review_csv_sha256":"review-hash",
            "item_classes":classes,"blocked_item_codes":blocked,
            "excluded_pos":{x:{"reason":"Generic amount button","source_product_id":str(i)}
                            for i,x in enumerate(blocked)},
            "class_counts":{"grocery_food":40,"cultivation_supply":78,"other_reviewed":1},
            "applies_taxes":False}


def webhook(item="FOOD000"):
    raw=json.dumps({"id":123,"status":"processing","date_modified_gmt":"2026-11-03T00:00:00",
            "currency":"USD","payment_method":"clover","line_items":[
              {"id":1,"variation_id":0,"product_id":100,
               "sku":item,"quantity":1}],"refunds":[],"total":"10.00"}).encode()
    signature=base64.b64encode(hmac.digest(b"s"*32,raw,"sha256")).decode()
    return raw,signature


class TaxPolicyIngressTests(unittest.TestCase):
    def test_approved_policy_count_and_collision_enforced(self):
        d=policy_doc()
        policy=validate_policy(d)
        self.assertEqual(len(policy["approved"]),119)
        self.assertEqual(len(policy["blocked"]),13)
        self.assertEqual(require_approved_item("FOOD000",policy),"grocery_food")
        with self.assertRaisesRegex(ValueError,"Generic POS"):
            require_approved_item("POS000",policy)
        d["item_classes"]["POS000"]="grocery_food"
        with self.assertRaises(ValueError):validate_policy(d)

    def test_private_file_required_and_no_checkout_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/"private"
            folder.mkdir(mode=0o700)
            file=folder/"map.json"
            file.write_text(json.dumps(policy_doc()))
            file.chmod(0o600)
            self.assertEqual(len(load_policy(file)["approved"]),119)
            file.chmod(0o644)
            with self.assertRaisesRegex(ValueError,"private file"):
                load_policy(file)

    def test_authenticated_woo_product_gate(self):
        policy=validate_policy(policy_doc())
        mappings={"100":{"sku":"FOOD000","erp_item_code":"FOOD000","ecommerce_id":99}}
        raw,sig=webhook()
        event=normalize_woo(raw,sig,["s"*32],"shop-test.danks.store",
                            mappings,{"clover":"clover"},tax_policy=policy)
        self.assertEqual(event["lines"][0]["erp_item_code"],"FOOD000")
        mappings["100"]={"sku":"POS000","erp_item_code":"POS000","ecommerce_id":98}
        raw,sig=webhook("POS000")
        with self.assertRaisesRegex(ValueError,"Generic POS"):
            normalize_woo(raw,sig,["s"*32],"shop-test.danks.store",
                          mappings,{"clover":"clover"},tax_policy=policy)

    def test_queue_block_before_mp_erp_side_effects(self):
        policy=validate_policy(policy_doc())
        inbox=Mock()
        inbox.claim.return_value={"payload":{
            "site_key":"shop-test.danks.store",
            "lines":[{"erp_item_code":"POS000"}]},
            "mp_receipt":None,"erp_receipt":None}
        mp=Mock();erp=Mock()
        self.assertTrue(deliver_one(inbox,mp,erp,tax_policies={
            "shop-test.danks.store":policy}))
        mp.assert_not_called()
        erp.assert_not_called()
        inbox.fail.assert_called_once()

    def test_read_only_without_runtime_opt_in_keeps_legacy_contract(self):
        # Historical order events don't retroactively acquire unknown tax policy.
        p=Path(ROOT/"integrations/commerce/runtime.py").read_text()
        self.assertIn("load_policy(row['tax_classification_file'])",p)
        self.assertIn("tax_policies=tax_policies",p)
        self.assertNotIn("commerce_tax_quote_required=True",p)


if __name__=="__main__":unittest.main()
