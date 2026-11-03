#!/usr/bin/env python3
"""Read-only installed ERPNext v16 sales-tax configuration inventory.

No fixtures, migration, template activation, or database writes. The live
ERPNext site runs payroll, so this tool makes only ordinary SELECT queries.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ERP_READ=r"""
import frappe,json,sys
frappe.init(site="erp.danks.store")
frappe.connect()
frappe.set_user("Administrator")
try:
 def rows(doctype,fields,filters=None,limit=100):
  if not frappe.db.exists("DocType",doctype):
   return {"available":False,"rows":[]}
  columns={d.fieldname for d in frappe.get_meta(doctype).fields}
  columns.update({"name","creation","modified","owner"})
  wanted=[f for f in fields if f in columns]
  if "name" not in wanted:wanted.insert(0,"name")
  return {"available":True,"fields":wanted,
          "rows":frappe.get_all(doctype,fields=wanted,filters=filters or {},
                   order_by="name asc",limit_page_length=limit)}
 def count(doctype):
  return frappe.db.count(doctype) if frappe.db.exists("DocType",doctype) else None
 companies=rows("Company",["name","abbr","default_currency","country"],limit=30)
 dml=[c for c in companies["rows"] if c["name"]=="Dank Mushrooms" or
     c.get("abbr")=="DML"]
 if len(dml)!=1:raise ValueError("Expected exactly one Dank Mushrooms company")
 company=dml[0]["name"]
 acct_fields=["name","account_name","account_number","account_type","root_type",
              "is_group","disabled","company"]
 accounts=rows("Account",acct_fields,{"company":company},limit=2000)
 tax_accounts=[x for x in accounts["rows"]
    if x.get("account_type")=="Tax" or
       any(term in (x.get("account_name") or "").lower()
           for term in ("sales tax","tax payable","tax collected","output tax"))]
 tax_categories=rows("Tax Category",["name","title","disabled"])
 sales_templates=rows("Sales Taxes and Charges Template",
    ["name","title","company","tax_category","is_default","disabled"],
    {"company":company},limit=200)
 item_templates=rows("Item Tax Template",
    ["name","title","company","tax_category","disabled"],
    {"company":company},limit=200)
 rules=rows("Tax Rule",["name","tax_type","company","tax_category",
     "sales_tax_template","priority","disabled","use_for_shopping_cart",
     "billing_city","billing_state","shipping_city","shipping_state",
     "from_date","to_date"],limit=300)
 if rules["available"]:
  rules["rows"]=[x for x in rules["rows"] if x.get("company") in (None,"",company)]
 account_settings={}
 if frappe.db.exists("DocType","Accounts Settings"):
  meta=frappe.get_meta("Accounts Settings")
  for field in meta.fields:
   if (field.fieldname and
       any(token in field.fieldname for token in ("tax","address","shipping")) and
       field.fieldtype in ("Check","Select","Data","Link")):
    account_settings[field.fieldname]=frappe.db.get_single_value(
      "Accounts Settings",field.fieldname)
 tax_meta={}
 for dt in ("Sales Taxes and Charges Template","Sales Taxes and Charges",
            "Item Tax Template","Item Tax Template Detail","Tax Rule",
            "Tax Category"):
  if not frappe.db.exists("DocType",dt):continue
  tax_meta[dt]=[{"fieldname":f.fieldname,"fieldtype":f.fieldtype,
                 "options":f.options}
    for f in frappe.get_meta(dt).fields
    if f.fieldname and f.fieldtype in
      ("Link","Table","Select","Check","Float","Percent","Currency","Data","Date","Int")]
 protected={d:count(d) for d in
   ("Sales Order","Sales Invoice","Payment Entry","Stock Entry","Bin")}
 output={"site":frappe.local.site,"app":"rootedops_commerce",
    "company":company,"company_abbr":dml[0].get("abbr"),
    "companies":companies["rows"],"accounts":tax_accounts,
    "tax_categories":tax_categories,"sales_templates":sales_templates,
    "item_templates":item_templates,"tax_rules":rules,
    "accounts_settings":account_settings,"doctype_fields":tax_meta,
    "catalog_counts":{d:count(d) for d in
      ("Item","Commercial Product Content","Commerce Channel Mapping",
       "Item Price")},
    "protected_counts":protected,
    "writes":False}
 print(json.dumps(output,default=str))
finally:
 frappe.db.rollback()
 frappe.destroy()
"""

def inspect(deployment):
    env=deployment/".env"
    compose=deployment/"docker/docker-compose.yml"
    if not env.is_file() or not compose.is_file():
        raise ValueError("Installed RootedOps deployment and local .env required")
    cmd=["docker","compose","--env-file",str(env),"-f",str(compose),
         "exec","-T","-w","/home/frappe/frappe-bench/sites",
         "erpnext-backend","/home/frappe/frappe-bench/env/bin/python","-c",ERP_READ]
    process=subprocess.run(cmd,capture_output=True,text=True)
    if process.returncode:
        raise RuntimeError("Read-only ERPNext tax inventory failed: "+process.stderr[-1600:])
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Unexpected ERPNext tax inventory output") from exc

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(inspect(args.repo_root.resolve()),indent=2))

if __name__=="__main__":
    main()
