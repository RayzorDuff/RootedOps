"""Offline tax classification and provider contract regression checks."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"integrations/commerce"))
import commerce_tax_classification as classification
from tax_adapter import build_request, get_quote

SOURCE_SHA=classification.EXPECTED_SOURCE_SHA

def products():
    return {f"SKU{i:03d}":{
        "id":i, "name":f"Product {i}", "sku":f"SKU{i:03d}",
        "enabled":i%2==0,"categoryIds":[160254004],
        "_combinations":[]}
        for i in range(132)}

def order():
    return {"external_order_id":"O-123","provider":"woocommerce",
            "site_key":"shop-test.danks.store","currency":"USD",
            "channel":"delivery","transaction_date":"2026-11-03",
            "location":{"street1":"100 Main St","city":"Johnstown",
               "state":"CO","postal_code":"80534","country":"US"},
            "lines":[{"item_code":"SKU000","quantity":2,"unit_price":"12.00"}]}


class TaxClassificationTests(unittest.TestCase):
    def test_prepare_requires_explicit_review_and_is_private(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"private"
            file=root/"tax-review.csv"
            result=classification.prepare(products(),file)
            self.assertEqual(result["products"],132)
            self.assertFalse(result["complete"])
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            with file.open(newline="") as input_file:
                data=list(csv.DictReader(input_file))
            self.assertEqual(len(data),132)
            self.assertTrue(all(not x["tax_class"] for x in data))
            with self.assertRaisesRegex(ValueError,"Refusing to overwrite"):
                classification.prepare(products(),file)

    def test_approval_requires_every_classified_source_item_and_note(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"private"
            review=folder/"review.csv"
            classification.prepare(products(),review)
            with self.assertRaisesRegex(ValueError,"Unreviewed or invalid"):
                classification.approve(products(),review,folder/"map.json","Owner")
            with review.open(newline="") as f:
                rows=list(csv.DictReader(f))
            for row in rows:
                row["tax_class"]="grocery_food" if int(row["ecwid_product_id"])%2==0 else "cultivation_supply"
                row["review_note"]="Reviewed from source product purpose"
            with review.open("w",newline="") as f:
                out=csv.DictWriter(f,fieldnames=list(rows[0]))
                out.writeheader();out.writerows(rows)
            result=classification.approve(products(),review,folder/"map.json","Owner")
            self.assertEqual(result["approved"],132)
            artifact=json.loads((folder/"map.json").read_text())
            self.assertEqual(artifact["source_sha256"],SOURCE_SHA)
            self.assertEqual(len(artifact["item_classes"]),132)
            self.assertEqual(artifact["class_counts"],{"cultivation_supply":66,"grocery_food":66,"other_reviewed":0})

    def test_generic_pos_exclusion_is_explicit_and_not_a_tax_exemption(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"private"
            review=folder/"review.csv"
            catalog=products()
            catalog["SKU000"]["name"]="1 Dollar Mushroom Item (NOTAX)"
            classification.prepare(catalog,review)
            with review.open(newline="") as fh:
                rows=list(csv.DictReader(fh))
            for row in rows:
                row["review_note"]="Owner-confirmed culinary food or reviewed cultivation supplies"
                row["tax_class"]="grocery_food"
                if row["item_code"]=="SKU000":
                    row["tax_class"]=""
                    row["review_status"]="excluded_pos"
                    row["review_note"]="Generic dollar amount not a specific sale; block"
            with review.open("w",newline="") as fh:
                writer=csv.DictWriter(fh,fieldnames=list(rows[0]))
                writer.writeheader();writer.writerows(rows)
            result=classification.approve(catalog,review,folder/"map.json","Owner")
            self.assertEqual(result["approved"],131)
            self.assertEqual(result["blocked"],1)
            approved=json.loads((folder/"map.json").read_text())
            self.assertEqual(approved["blocked_item_codes"],["SKU000"])
            self.assertNotIn("SKU000",approved["item_classes"])
            self.assertNotIn("SKU000",approved["class_counts"])
            catalog["SKU000"]["name"]="Fresh Oyster Mushrooms"
            with self.assertRaisesRegex(ValueError,"Unreviewed or invalid"):
                classification.approve(catalog,review,folder/"reject.json","Owner")

    def test_generic_pos_exclusion_must_not_be_in_class_map(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/"private"
            review=folder/"review.csv"
            catalog=products()
            catalog["SKU000"]["name"]="10 Dollar Mushroom Item"
            classification.prepare(catalog,review)
            with review.open(newline="") as fh:
                rows=list(csv.DictReader(fh))
            for row in rows:
                row["tax_class"]="cultivation_supply"
                row["review_note"]="Owner-reviewed cultivation item"
                if row["item_code"]=="SKU000":
                    row["review_status"]="excluded_pos"
            with review.open("w",newline="") as fh:
                writer=csv.DictWriter(fh,fieldnames=list(rows[0]))
                writer.writeheader();writer.writerows(rows)
            with self.assertRaisesRegex(ValueError,"conflicts"):
                classification.approve(catalog,review,folder/"reject.json","Owner")

    def test_source_checksum_is_exact(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.json"
            source.write_text('{"store_id":"95802503","products":[]}')
            with self.assertRaisesRegex(ValueError,"source hash changed"):
                classification.load_source(source)

    def test_tax_request_requires_real_address_and_approved_sku(self):
        req=build_request(order(),{"SKU000":"grocery_food"},SOURCE_SHA)
        self.assertEqual(req["lines"][0]["tax_class"],"grocery_food")
        self.assertEqual(len(req["request_sha256"]),64)
        changed=order()
        changed["location"]["street1"]="PO Box 1"
        # P.O. Box is not a valid physical destination even with digits.
        # A provider must perform ultimate geocoding/address verification.
        changed["location"]["street1"]="Johnstown"
        with self.assertRaisesRegex(ValueError,"Physical street"):
            build_request(changed,{"SKU000":"grocery_food"},SOURCE_SHA)
        with self.assertRaisesRegex(ValueError,"Missing owner-reviewed"):
            build_request(order(),{"SKU000":""},SOURCE_SHA)

    def test_unknown_destination_and_freight_fail_closed(self):
        changed=order()
        changed["shipping_total"]="5.00"
        with self.assertRaisesRegex(ValueError,"Shipping/discount"):
            build_request(changed,{"SKU000":"grocery_food"},SOURCE_SHA)
        with self.assertRaisesRegex(ValueError,"source snapshot changed"):
            build_request(order(),{"SKU000":"grocery_food"},"wrong")

    def test_provider_transport_must_be_configured_and_quote_bound(self):
        req=build_request(order(),{"SKU000":"grocery_food"},SOURCE_SHA)
        with self.assertRaisesRegex(ValueError,"No configured"):
            get_quote(req,"chosen-provider")
        def response(input_req):
            return {"provider":"chosen-provider","source_order":"O-123",
                    "request_sha256":input_req["request_sha256"],
                    "currency":"USD","channel":"delivery",
                    "jurisdiction_evidence":"reviewed-address-jurisdiction",
                    "collection_status":"collect",
                    "lines":[{"line_index":0,"item_code":"SKU000",
                              "tax_class":"grocery_food","quantity":"2"}]}
        self.assertEqual(get_quote(req,"chosen-provider",response)["provider"],"chosen-provider")
        with self.assertRaisesRegex(ValueError,"provider/order identity"):
            get_quote(req,"imposter",response)
        with self.assertRaisesRegex(ValueError,"not bound"):
            get_quote(req,"chosen-provider",lambda r:dict(response(r),request_sha256="bad"))
        with self.assertRaisesRegex(ValueError,"line identity"):
            get_quote(req,"chosen-provider",lambda r:dict(response(r),lines=[
                dict(response(r)["lines"][0],tax_class="cultivation_supply")]))

if __name__=="__main__":
    unittest.main()
