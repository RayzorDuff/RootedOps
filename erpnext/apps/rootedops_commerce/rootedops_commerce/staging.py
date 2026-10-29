"""Bench-only, staging-host-guarded import of an approved offline catalog plan."""
import json
from pathlib import Path
import frappe
from rootedops_commerce.api import import_product


def import_plan(path):
    if frappe.local.site != 'erp-test.danks.store':
        raise ValueError('This helper is restricted to the disposable staging site')
    data=json.loads(Path(path).read_text())
    if data.get('errors'):raise ValueError('Source reconciliation errors must be resolved first')
    if not frappe.db.exists('Item Group','All Item Groups'):
        frappe.get_doc({'doctype':'Item Group','item_group_name':'All Item Groups','is_group':1}).insert()
    if not frappe.db.exists('Item Group','Ecwid Migration'):
        frappe.get_doc({'doctype':'Item Group','item_group_name':'Ecwid Migration',
                        'parent_item_group':'All Item Groups','is_group':0}).insert()
    if not frappe.db.exists('UOM','Nos'):
        frappe.get_doc({'doctype':'UOM','uom_name':'Nos','must_be_whole_number':1}).insert()
    imported=[]
    for product in data['products']:
        if product['item'].get('has_variants') or product['item'].get('parent_sku'):
            raise ValueError('Variant imports require reviewed attributes; this CSV helper imports simple products only')
        payload={'item':{'item_code':product['content']['item'],'item_name':product['content']['public_title'],
                         'item_group':'Ecwid Migration','stock_uom':'Nos'},
                 'content':product['content'],'mapping':product['mapping']}
        imported.append(import_product(json.dumps(payload)))
    archived=0
    for record in data['archives']:
        name=record['source_key']
        if frappe.db.exists('Commerce Source Archive',name):
            existing=frappe.get_doc('Commerce Source Archive',name)
            existing.check_permission('read')
            if existing.payload!=record['payload']:raise ValueError('Source archive drift')
        else:frappe.get_doc(record).insert()
        archived+=1
    # bench execute does not implicitly commit mutations; only after the entire
    # plan succeeds. An exception leaves the migration uncommitted.
    frappe.db.commit()
    return {'products_imported_or_existing':len(imported),'archives_imported_or_existing':archived,
            'price_lists_changed':False,'stock_changed':False,'financial_documents_created':False}


def export_test_catalog(plan_path, output_path):
    """Bench-only private snapshot for staging integration rehearsals."""
    if frappe.local.site != 'erp-test.danks.store':
        raise ValueError('Restricted to the disposable staging site')
    from rootedops_commerce.api import catalog
    import os
    plan=json.loads(Path(plan_path).read_text())
    if plan.get('errors'):raise ValueError('Reconciliation errors')
    result={p['content']['item']:catalog(p['content']['item']) for p in plan['products']}
    fd=os.open(output_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(result,stream,default=str)
    return {'catalog_records_exported':len(result),'canonical_content_changed':False}
