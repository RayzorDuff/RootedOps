"""Provider-neutral commerce tax quote acceptance, no Frappe or network required."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path

APP=Path(__file__).resolve().parents[1]/"erpnext/apps/rootedops_commerce"
sys.path.insert(0,str(APP))
from rootedops_commerce.tax_contract import validate_quote, validate_erp_taxes


def sample():
    order=[
      {"item_code":"GROCERY-1","qty":2,"rate":"10.00"},
      {"item_code":"CULTIVATION-1","qty":1,"rate":"20.00"},
    ]
    quote={
      "schema_version":1,"provider":"authorized-tax-provider",
      "quote_id":"quote-abc123","source_order":"order-456",
      "currency":"USD","channel":"market","location_ref":"Boardwalk Park, Windsor, CO",
      "jurisdiction_evidence":"address-bound-2026-11-02",
      "collection_status":"collect",
      "lines":[
        {"line_index":0,"item_code":"GROCERY-1","tax_class":"grocery_food",
         "quantity":2,"line_total":"20.00"},
        {"line_index":1,"item_code":"CULTIVATION-1","tax_class":"cultivation_supply",
         "quantity":1,"line_total":"20.00"},
      ],
      "components":[
        {"line_index":0,"authority":"Windsor","jurisdiction_id":"US-CO-WINDSOR",
         "account_head":"Windsor Sales Tax - DML","taxability":"taxable_groceries_local",
         "taxable_base":"20.00","rate_percent":"3.65","tax_amount":"0.73"},
        {"line_index":1,"authority":"Windsor","jurisdiction_id":"US-CO-WINDSOR",
         "account_head":"Windsor Sales Tax - DML","taxability":"taxable_merchandise",
         "taxable_base":"20.00","rate_percent":"3.65","tax_amount":"0.73"},
        {"line_index":1,"authority":"Colorado","jurisdiction_id":"US-CO-STATE",
         "account_head":"Colorado State Sales Tax Payable - DML",
         "taxability":"taxable_merchandise","taxable_base":"20.00",
         "rate_percent":"2.9","tax_amount":"0.58"},
      ],
      "tax_total":"2.04","calculated_total":"42.04"
    }
    return order,quote


class TaxQuoteTests(unittest.TestCase):
    def test_calculation_and_exact_erp_tax_liability(self):
        order,quote=sample()
        taxes=validate_quote(quote,order,"USD","42.04")
        self.assertEqual(len(taxes),2)
        self.assertEqual(
          {x["account_head"]:x["tax_amount"] for x in taxes},
          {"Colorado State Sales Tax Payable - DML":"0.58",
           "Windsor Sales Tax - DML":"1.46"})
        self.assertTrue(validate_erp_taxes(taxes,taxes))

    def test_market_remittance_cannot_offset_quote(self):
        order,quote=sample()
        quote["remittances"]=[{"amount":"1.46","recipient":"Windsor market manager"}]
        with self.assertRaisesRegex(ValueError,"separate remittance"):
            validate_quote(quote,order,"USD","42.04")

    def test_pending_nexus_fails_closed(self):
        order,quote=sample()
        quote["collection_status"]="pending"
        with self.assertRaisesRegex(ValueError,"defer order staging"):
            validate_quote(quote,order,"USD","42.04")

    def test_other_state_not_required_without_claiming_item_exemption(self):
        order,quote=sample()
        quote["channel"]="shipping"
        quote["location_ref"]="Verified ship-to, out of state"
        quote["collection_status"]="not_required"
        quote["components"]=[]
        quote["tax_total"]="0.00"
        quote["calculated_total"]="40.00"
        self.assertEqual(validate_quote(quote,order,"USD","40.00"),[])

    def test_rejects_boolean_rate_tampering(self):
        order,quote=sample()
        quote["components"][0]["rate_percent"]=True
        with self.assertRaises(ValueError):
            validate_quote(quote,order,"USD","42.04")

    def test_rejects_tax_arithmetic_and_line_tampering(self):
        order,quote=sample()
        quote["components"][0]["tax_amount"]="0.74"
        with self.assertRaisesRegex(ValueError,"arithmetic mismatch"):
            validate_quote(quote,order,"USD","42.04")
        order,quote=sample()
        quote["lines"][0]["tax_class"]="unclassified"
        with self.assertRaisesRegex(ValueError,"Unreviewed item"):
            validate_quote(quote,order,"USD","42.04")
        order,quote=sample()
        quote["lines"][0]["quantity"]=3
        with self.assertRaisesRegex(ValueError,"quantity mismatch"):
            validate_quote(quote,order,"USD","42.04")

    def test_rejects_duplicate_jurisdiction_and_wrong_account(self):
        order,quote=sample()
        quote["components"].append(deepcopy(quote["components"][0]))
        with self.assertRaisesRegex(ValueError,"Duplicate jurisdiction"):
            validate_quote(quote,order,"USD","42.04")
        order,quote=sample()
        expected=validate_quote(quote,order,"USD","42.04")
        wrong=deepcopy(expected)
        wrong[0]["account_head"]="Payroll Tax Payable - DML"
        with self.assertRaisesRegex(ValueError,"exactly match"):
            validate_erp_taxes(expected,wrong)

    def test_no_tax_default_or_unvalidated_origin(self):
        order,quote=sample()
        quote["default_rate"]="6%"
        with self.assertRaisesRegex(ValueError,"default tax"):
            validate_quote(quote,order,"USD","42.04")

    def test_order_service_uses_exact_tax_contract_with_no_activation(self):
        source=(APP/"rootedops_commerce/order_service.py").read_text()
        self.assertIn("validate_quote(",source)
        self.assertIn("validate_erp_taxes(",source)
        self.assertIn("commerce_tax_account_map",source)
        self.assertIn("commerce_tax_quote_required",source)
        self.assertIn("'tax_quote':event.get('tax_quote')",source)
        self.assertNotIn("frappe.db.commit()",source)

if __name__=="__main__":
    unittest.main()
