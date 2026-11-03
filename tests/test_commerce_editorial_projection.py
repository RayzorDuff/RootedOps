"""Offline tests: staged ERP->Woo editorial projection never changes business state."""
import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations/commerce"))
from editorial_projection import build_plan, sync_staging

SHOP = "https://shop-test2.danks.store"


def fixture():
    content = {
        "item": "sku1", "source_key": "ecwid:95802503:product:1",
        "publication_status": "Draft", "modified": "2026-11-03 10:00:00",
        "public_title": "Canonical product", "short_description": "New short",
        "full_description": "<p>New long</p>",
        "seo_title": "New SEO", "seo_description": "New meta",
    }
    cat = {"content": content, "item": {"item_code": "sku1"}}
    receipt = {"erp_item": "sku1", "source_key": content["source_key"], "woo_id": 17}
    woo = {
        "id": 17, "sku": "sku1", "type": "simple", "status": "draft",
        "catalog_visibility": "hidden", "date_modified_gmt": "2026-11-03T09:00:00",
        "name": "Old product", "description": "Old long", "short_description": "Old short",
        "regular_price": "14.95", "sale_price": "", "price": "14.95",
        "tax_status": "taxable", "tax_class": "", "manage_stock": True,
        "stock_quantity": 0, "stock_status": "outofstock", "backorders": "no",
        "images": [{"id": 20}], "categories": [{"id": 5}],
        "attributes": [], "variations": [], "virtual": False, "downloadable": False,
        "meta_data": [
            {"id": 3, "key": "_rootedops_source_key", "value": content["source_key"]},
            {"id": 4, "key": "_rootedops_seo_title", "value": "Old SEO"},
            {"id": 5, "key": "_rootedops_seo_description", "value": "Old meta"},
            {"id": 6, "key": "_unrelated_config", "value": "retain"}
        ],
    }
    return cat, receipt, woo


class WooFake:
    def __init__(self, woo):
        self.woo = copy.deepcopy(woo)
        self.writes = []

    def __call__(self, url, auth, method="GET", payload=None):
        if not url.startswith(SHOP + "/wp-json/wc/v3/products/17"):
            raise AssertionError("Wrong target")
        if method == "GET":
            return copy.deepcopy(self.woo)
        if method != "PUT":
            raise AssertionError("Unexpected method")
        self.writes.append(copy.deepcopy(payload))
        assert set(payload).issubset({"name", "description", "short_description", "meta_data"})
        for key, value in payload.items():
            if key == "meta_data":
                for m in value:
                    matches = [v for v in self.woo["meta_data"] if v["key"] == m["key"]]
                    if matches:
                        matches[0]["value"] = m["value"]
                    else:
                        self.woo["meta_data"].append(dict(m))
            else:
                self.woo[key] = value
        self.woo["date_modified_gmt"] = "2026-11-03T10:01:00"
        return copy.deepcopy(self.woo)


class StagingEditorialTests(unittest.TestCase):
    def test_preview_is_read_only_and_digest_bound(self):
        cat, receipt, woo = fixture()
        remote = WooFake(woo)
        plan = sync_staging(SHOP, "secret", cat, receipt, request=remote)
        self.assertEqual([], remote.writes)
        self.assertFalse(plan["writes"])
        self.assertEqual(5, len(plan["changed_fields"]))
        self.assertEqual(64, len(plan["digest"]))

    def test_approved_write_touches_only_editorial_fields(self):
        cat, receipt, woo = fixture()
        remote = WooFake(woo)
        plan = sync_staging(SHOP, "secret", cat, receipt, request=remote)
        done = sync_staging(SHOP, "secret", cat, receipt,
                            approve_digest=plan["digest"], request=remote)
        self.assertTrue(done["writes"])
        self.assertEqual(1, len(remote.writes))
        sent = remote.writes[0]
        self.assertEqual(set(sent), {"name", "short_description", "description", "meta_data"})
        self.assertEqual(2, len(sent["meta_data"]))
        self.assertTrue(all("id" in v for v in sent["meta_data"]))
        self.assertEqual("14.95", remote.woo["regular_price"])
        self.assertEqual(0, remote.woo["stock_quantity"])
        self.assertEqual("draft", remote.woo["status"])
        self.assertEqual("retain", [m["value"] for m in remote.woo["meta_data"]
                                    if m["key"] == "_unrelated_config"][0])
        repeated = sync_staging(SHOP, "secret", cat, receipt, request=remote)
        self.assertEqual([], repeated["changed_fields"])

    def test_digest_refuses_changed_destination(self):
        cat, receipt, woo = fixture()
        remote = WooFake(woo)
        plan = sync_staging(SHOP, "secret", cat, receipt, request=remote)
        remote.woo["description"] = "independently edited"
        with self.assertRaisesRegex(ValueError, "fingerprint drift"):
            sync_staging(SHOP, "secret", cat, receipt,
                         approve_digest=plan["digest"], request=remote)
        self.assertEqual([], remote.writes)

    def test_refuse_wrong_owner_published_or_sku(self):
        for change in ({"status": "publish"}, {"catalog_visibility": "visible"},
                       {"sku": "wrong"}, {"type": "variable"}, {"id": 99}):
            cat, receipt, woo = fixture()
            woo.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_plan(cat, receipt, woo)

    def test_refuse_untrusted_receipt_or_published_erp(self):
        cat, receipt, woo = fixture()
        receipt["source_key"] = "wrong"
        with self.assertRaises(ValueError):
            build_plan(cat, receipt, woo)
        cat, receipt, woo = fixture()
        cat["content"]["publication_status"] = "Published"
        with self.assertRaises(ValueError):
            build_plan(cat, receipt, woo)

    def test_duplicate_ownership_metadata_rejected(self):
        cat, receipt, woo = fixture()
        woo["meta_data"].append(dict(woo["meta_data"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate Woo metadata"):
            build_plan(cat, receipt, woo)

    def test_no_public_or_mixed_target(self):
        cat, receipt, woo = fixture()
        remote = WooFake(woo)
        for url in ("https://shop.danks.store", "https://example.com",
                    "http://shop-test2.danks.store"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                sync_staging(url, "secret", cat, receipt, request=remote)
        self.assertEqual([], remote.writes)


if __name__ == "__main__":
    unittest.main()
