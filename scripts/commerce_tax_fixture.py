#!/usr/bin/env python3
"""Install an isolated native tax component fixture on test2, never a live rate.

Run under test2-console-lock with sudo -n; see doc/commerce-tax-architecture.md.
No invoice is saved/submitted and no real product/customer is classified.
"""
import argparse
import json
from pathlib import Path

from commerce_catalog_audit import native
from commerce_catalog_batch import guarded_environment
from ecwid_migrate import private_write

NATIVE = r'''
import json, frappe
from frappe.utils import today
from erpnext.accounts.doctype.tax_rule.tax_rule import get_tax_template
frappe.init(site='erp-test2.danks.store'); frappe.connect(); frappe.set_user('Administrator')
try:
 assert frappe.conf.maintenance_mode and frappe.conf.pause_scheduler
 company='Dank Mushrooms, LLC'
 category='TEST2 CO JOHNSTOWN COMPONENTS ONLY'
 def ensure(dt, filters, values):
  name=frappe.db.exists(dt, filters)
  if name:
   d=frappe.get_doc(dt,name)
   for k,v in values.items():
    if isinstance(v,list):
     assert [{x:y.get(x) for x in v[0]} for y in d.get(k)]==v, (dt,k,'fixture drift')
    else: assert d.get(k)==v, (dt,k,'fixture drift')
   return d
  return frappe.get_doc(dict(values,doctype=dt)).insert()
 cat=ensure('Tax Category',{'title':category},{'title':category,'disabled':0})
 accounts=[]
 for label,rate in [('State',2.9),('Johnstown',3.5)]:
  account_name='TEST2 CO '+label+' Tax Components'
  d=ensure('Account',{'company':company,'account_name':account_name},
   {'account_name':account_name,'company':company,'parent_account':'Duties and Taxes - DML',
    'account_type':'Tax','is_group':0,'account_currency':'USD'})
  accounts.append((d.name,rate))
 template=ensure('Sales Taxes and Charges Template',{'company':company,'title':category},
  {'title':category,'company':company,'tax_category':cat.name,'is_default':0,'disabled':0,
   'taxes':[{'charge_type':'On Net Total','account_head':a,'description':'TEST2 component only: '+a,'rate':r} for a,r in accounts]})
 rule=ensure('Tax Rule',{'company':company,'tax_category':cat.name},
  {'tax_type':'Sales','company':company,'tax_category':cat.name,'sales_tax_template':template.name,
   'use_for_shopping_cart':0,'priority':1})
 # An exclusive category, not a city/ZIP wildcard, prevents automatic storefront use.
 assert get_tax_template(today(),{'company':company,'tax_category':cat.name,'tax_type':'Sales'})==template.name
 items={}
 for label,state in [('GROCERY',0),('MERCH',2.9)]:
  title='TEST2 CO '+label+' COMPONENTS ONLY'
  itt=ensure('Item Tax Template',{'company':company,'title':title},
   {'title':title,'company':company,'disabled':0,
    'taxes':[{'tax_type':accounts[0][0],'tax_rate':state},{'tax_type':accounts[1][0],'tax_rate':3.5}]})
  code='TEST2-TAX-'+label
  item=ensure('Item',{'item_code':code},{'item_code':code,'item_name':code,
   'item_group':'RootedOps Test2 Commerce Fixtures','stock_uom':'Nos','is_stock_item':0,
   'is_sales_item':1,'is_purchase_item':0,
   'taxes':[{'item_tax_template':itt.name,'tax_category':cat.name}]})
  items[label]=(item.name,itt.name)
 customer=ensure('Customer',{'customer_name':'RootedOps Tax Acceptance Fixture'},
  {'customer_name':'RootedOps Tax Acceptance Fixture','customer_type':'Individual',
   'customer_group':'Individual','territory':'All Territories'})
 results=[]
 for labels,expected in [(['GROCERY'],3.5),(['MERCH'],6.4),(['GROCERY','MERCH'],9.9)]:
  invoice=frappe.get_doc({'doctype':'Sales Invoice','docstatus':0,'company':company,'customer':customer.name,
   'posting_date':today(),'due_date':today(),'currency':'USD','conversion_rate':1,
   'tax_category':cat.name,'taxes_and_charges':template.name,'is_pos':0,
   'remarks':'TEST2 incomplete jurisdiction components only. NOT a destination quote.',
   'items':[{'item_code':items[x][0],'qty':1,'rate':100,'item_tax_template':items[x][1]} for x in labels],
   'taxes':[{'charge_type':'On Net Total','account_head':a,'description':a,'rate':r} for a,r in accounts]})
  invoice.set_missing_values(); invoice.calculate_taxes_and_totals()
  assert round(invoice.total_taxes_and_charges,2)==expected, invoice.as_dict()
  assert invoice.docstatus==0 and not invoice.name
  results.append({'items':labels,'net':invoice.net_total,'component_tax':invoice.total_taxes_and_charges,
   'components':[{'account':x.account_head,'amount':x.tax_amount} for x in invoice.taxes],
   'saved':False,'submitted':False})
 # No real product or Customer may be silently enrolled by the fixture.
 assert frappe.db.count('Item Tax',{'tax_category':cat.name})==2
 assert not frappe.db.count('Customer',{'tax_category':cat.name})
 frappe.db.commit()
 print(json.dumps({'category':cat.name,'template':template.name,'rule':rule.name,'scenarios':results,
  'complete_destination_rate':False,'live_collection_enabled':False}))
except Exception:
 frappe.db.rollback(); raise
finally: frappe.destroy()
'''


def run(environment):
    _, private = guarded_environment(environment)
    (private / 'tax-readiness').mkdir(mode=0o700, exist_ok=True)
    result = native(NATIVE, {})
    private_write(private / 'tax-readiness/native-components.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('environment', type=Path)
    run(parser.parse_args().environment)
