#!/usr/bin/env python3
"""Convert Ecwid's semicolon CSV exports to lossless, offline migration input.

CSV order numbers/customer email identities are explicitly namespaced: they are
not falsely presented as Ecwid API order/customer IDs. No financial replay.
"""
import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from ecwid_migrate import plan, private_write


def read_rows(path, required):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream,delimiter=';')
        if not required.issubset(reader.fieldnames or []):
            raise ValueError('Missing required CSV columns: '+','.join(sorted(required-set(reader.fieldnames or []))))
        rows=list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise ValueError('Malformed CSV row/column count')
    return rows


def decimal_text(value):
    try:
        result=Decimal(value)
        if not result.is_finite():raise ValueError('Nonfinite decimal')
        return format(result,'f')
    except InvalidOperation as error:raise ValueError('Invalid decimal') from error


def convert(products_path,orders_path,store_id):
    products=read_rows(products_path,{'name','sku','product_id','description','price'})
    rows=read_rows(orders_path,{'order_number','email','sku','name','quantity','order_total'})
    output={'schema_version':1,'store_id':str(store_id),'products':[], 'orders':[], 'customers':[], 'categories':[],
            'profile':{'source_format':'ecwid_csv','currency':None},
            '_csv_manifest':{'product_rows':len(products),'order_line_rows':len(rows),
                'files':{Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (products_path,orders_path)},
                'limitations':['Product variation/option definitions are absent; CSV cannot prove combination completeness.',
                  'Image field is only exported media; gallery originals require API/media export.',
                  'CSV customers are derived email identities, not authoritative Ecwid customer IDs.',
                  'Currency is absent and must be reviewed against the store profile.',
                  'Order export date/filter completeness must be verified before retiring Ecwid.']}}
    categories={}
    for row in products:
        if not row['product_id'].strip():raise ValueError('Missing product ID')
        category_ids=[]
        for k in ('category1','category2','category3'):
            if row.get(k):
                key='csv-category:'+hashlib.sha256(row[k].encode()).hexdigest()[:24]
                categories[key]={'id':key,'name':row[k],'identity_kind':'csv_category_path'};category_ids.append(key)
        output['products'].append({'id':row['product_id'],'sku':row['sku'],'name':row['name'],
            'description':row['description'],'shortDescription':row.get('subtitle',''),
            'seoTitle':row.get('seo_title',''),'seoDescription':row.get('seo_description',''),
            'imageUrl':row.get('image',''),'url':row.get('product_url',''),
            'price':decimal_text(row['price']),'enabled':row.get('enabled','').strip().lower()=='yes',
            'quantity':row.get('quantity',''),'categoryIds':category_ids,'_combinations':[],
            '_source_format':'ecwid_csv','_csv_row':row})
    grouped={};customers={}
    for row in rows:
        number=row['order_number'].strip()
        if not number:raise ValueError('Missing source order number')
        grouped.setdefault(number,[]).append(row)
        email=row['email'].strip().lower()
        if email:
            key='csv-email:'+hashlib.sha256(email.encode()).hexdigest()
            # Do not infer consent or merge addresses from historical orders.
            customers[key]={'id':key,'email':email,'identity_kind':'csv_email_hash','source_format':'ecwid_order_csv'}
    for number,lines in grouped.items():
        for field in ('order_total','payment_status_code','fulfillment_status_code','email','timestamp'):
            if len({line.get(field) for line in lines})!=1:
                raise ValueError('Conflicting order-level '+field+' in source order '+number)
        first=lines[0]
        output['orders'].append({'id':'csv-order-number:'+number,'orderNumber':number,'identity_kind':'csv_order_number',
            'email':first['email'],'total':decimal_text(first['order_total']),
            'paymentStatus':first.get('payment_status_code'),'fulfillmentStatus':first.get('fulfillment_status_code'),
            'createDate':first.get('timestamp'), 'items':[{'sku':r['sku'],'name':r['name'],
            'quantity':decimal_text(r['quantity']),'price':decimal_text(r['price']),
            'options_raw':r.get('options',''),'_csv_row':r} for r in lines],
            '_source_format':'ecwid_order_csv'})
    output['customers']=list(customers.values());output['categories']=list(categories.values())
    return output

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--products',required=True);p.add_argument('--orders',required=True)
    p.add_argument('--store-id',required=True);p.add_argument('--output',required=True);p.add_argument('--plan-output',required=True)
    a=p.parse_args();source=convert(a.products,a.orders,a.store_id);private_write(a.output,source)
    result=plan(source);result['csv_manifest']=source['_csv_manifest'];private_write(a.plan_output,result)
    print(json.dumps({'counts':result['counts'],'order_lines':source['_csv_manifest']['order_line_rows'],'errors':result['errors'],
                      'limitations':source['_csv_manifest']['limitations']}))
    raise SystemExit(1 if result['errors'] else 0)
