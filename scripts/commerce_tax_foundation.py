#!/usr/bin/env python3
"""Install only verified Colorado state and Johnstown municipal sales-tax components.

Nondefault, disabled native ERPNext templates; no rate for county/district.
Retires unverified legacy 6% SALES default, preserves all historical templates.
Read-only unless --apply. Neither checkout nor existing payroll is changed.
"""
import argparse
import json
from pathlib import Path
import subprocess

ERP=r"""
import frappe,json,sys
data=json.load(sys.stdin)
frappe.init(site="erp.danks.store")
frappe.connect()
frappe.set_user("Administrator")
COMPANY="Dank Mushrooms, LLC"
GROUP="Duties and Taxes - DML"
COMPONENTS=[
 ("Colorado State Sales Tax Payable","CO State 2.9% Component - Incomplete",2.9),
 ("Johnstown Municipal Sales Tax Payable","CO Johnstown 3.5% Component - Incomplete",3.5)]
LEGACY="US ST 6% - DML"
def assert_account(value,parent):
 doc=frappe.get_doc("Account",value)
 assert doc.company==COMPANY and doc.parent_account==parent
 assert not doc.is_group and not doc.disabled
 assert doc.root_type=="Liability" and doc.account_type=="Tax"
def expected_template(name,account,rate):
 doc=frappe.get_doc("Sales Taxes and Charges Template",name)
 assert doc.company==COMPANY and doc.disabled==1 and doc.is_default==0
 assert len(doc.taxes)==1
 tax=doc.taxes[0]
 assert tax.charge_type=="On Net Total" and tax.account_head==account
 assert abs(float(tax.rate)-rate)<0.00001
 assert not tax.included_in_print_rate and not tax.included_in_paid_amount
 assert not doc.tax_category
try:
 assert frappe.db.get_value("Company",COMPANY,"abbr")=="DML"
 group=frappe.get_doc("Account",GROUP)
 assert group.company==COMPANY and group.is_group and group.root_type=="Liability"
 assert frappe.db.exists("Account","Sales Tax Payable - DML")
 legacy=frappe.get_doc("Sales Taxes and Charges Template",LEGACY)
 assert legacy.company==COMPANY
 protected=("Sales Order","Sales Invoice","Payment Entry","Stock Entry","Bin",
            "Salary Slip","Journal Entry","Item","Commercial Product Content",
            "Commerce Channel Mapping","Item Price")
 before={d:frappe.db.count(d) for d in protected if frappe.db.exists("DocType",d)}
 def check_account(label):
  name=label+" - DML"
  if frappe.db.exists("Account",name):
   assert_account(name,GROUP)
   return name,False
  if not data["apply"]:return name,True
  doc=frappe.get_doc({"doctype":"Account","account_name":label,
     "parent_account":GROUP,"company":COMPANY,"account_type":"Tax",
     "is_group":0,"root_type":"Liability"}).insert(ignore_permissions=True)
  assert doc.name==name
  assert_account(name,GROUP)
  return name,True
 components=[]
 for label,title,rate in COMPONENTS:
  account,created=check_account(label)
  template_name=title+" - DML"
  if frappe.db.exists("Sales Taxes and Charges Template",template_name):
   if data["apply"]:expected_template(template_name,account,rate)
   else:
    template=frappe.get_doc("Sales Taxes and Charges Template",template_name)
    assert template.company==COMPANY and template.disabled and not template.is_default
   needs_template=False
  else:
   needs_template=True
   if data["apply"]:
    doc=frappe.get_doc({
      "doctype":"Sales Taxes and Charges Template",
      "title":title,"company":COMPANY,
      "disabled":1,"is_default":0,
      "taxes":[{"charge_type":"On Net Total","account_head":account,
                "rate":rate,"description":"INCOMPLETE COMPONENT - NOT FULL DESTINATION RATE"}]
    }).insert(ignore_permissions=True)
    assert doc.name==template_name
    expected_template(template_name,account,rate)
  components.append({"account":account,"account_created_if_apply":created,
      "template":template_name,"template_created_if_apply":needs_template,
      "component_rate_percent":rate,"disabled":True,"default":False})
 defaults=frappe.get_all("Sales Taxes and Charges Template",
    filters={"company":COMPANY,"is_default":1},
    fields=["name","disabled"],limit_page_length=100)
 assert {x["name"] for x in defaults}.issubset({LEGACY}),defaults
 old_default=bool(legacy.is_default)
 if data["apply"] and old_default:
  legacy.is_default=0
  legacy.save(ignore_permissions=True)
 current=frappe.get_all("Sales Taxes and Charges Template",
    filters={"company":COMPANY,"is_default":1},fields=["name"],limit_page_length=100)
 if data["apply"]:
  assert not current
  after={d:frappe.db.count(d) for d in before}
  assert before==after
  assert frappe.db.count("Tax Rule",{"company":COMPANY})==0
  frappe.db.commit()
 else:
  frappe.db.rollback()
 print(json.dumps({"site":frappe.local.site,"company":COMPANY,
  "apply":data["apply"],"legacy_6_percent_default_before":old_default,
  "legacy_6_percent_default_after":False if data["apply"] else old_default,
  "legacy_templates_preserved":True,"components":components,
  "no_tax_rules_created":True,"no_tax_categories_created":True,
  "no_checkout_activation":True,"full_destination_rate_pending":True,
  "protected_document_counts_before":before,"writes":data["apply"]}))
except BaseException:
 frappe.db.rollback()
 raise
finally:
 frappe.destroy()
"""

def run(root,apply):
    if not (root/".env").is_file() or not (root/"docker/docker-compose.yml").is_file():
        raise ValueError("Installed RootedOps .env and compose file required")
    args=["docker","compose","--env-file",str(root/".env"),"-f",
          str(root/"docker/docker-compose.yml"),"exec","-T","-w",
          "/home/frappe/frappe-bench/sites","erpnext-backend",
          "/home/frappe/frappe-bench/env/bin/python","-c",ERP]
    p=subprocess.run(args,input=json.dumps({"apply":apply}),text=True,capture_output=True)
    if p.returncode:
        raise RuntimeError("ERPNext tax foundation rejected change: "+p.stderr[-1800:])
    try:return json.loads(p.stdout)
    except json.JSONDecodeError as exc:raise RuntimeError("Invalid native Frappe output") from exc

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root",type=Path,required=True)
    parser.add_argument("--apply",action="store_true")
    a=parser.parse_args()
    print(json.dumps(run(a.repo_root.resolve(),a.apply),indent=2))

if __name__=="__main__":
    main()
