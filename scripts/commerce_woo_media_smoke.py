#!/usr/bin/env python3
"""Synthetic binary upload and installed core/Yoast SEO-hook proof; no checkout."""
import base64
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/commerce'))
from ecwid_migrate import api
from media_upload import upload_request


def fixture_png():
    def chunk(kind,data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    pixels=(b'\x00'+b'\x30\x80\x40'*24)*24
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',24,24,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')


def run(environment):
    p=environment.resolve();private=p/'private'
    if (p/'TEST_ENVIRONMENT').read_text().strip()!='rootedops-full-test':raise ValueError('Isolated environment required')
    baseline=json.loads((private/'woo-native-smoke.json').read_text())
    if baseline.get('fixture_only') is not True:raise ValueError('Synthetic catalog receipt required')
    c=json.loads((private/'wordpress-credentials.json').read_text())
    auth='Basic '+base64.b64encode((c['username']+':'+c['application_password']).encode()).decode()
    root='https://shop-test.danks.store';blob=fixture_png();sha=hashlib.sha256(blob).hexdigest()
    receipt=private/'woo-native-media.json'
    old=json.loads(receipt.read_text()) if receipt.exists() else None
    found=api(root+'/wp-json/wp/v2/media?slug=rootedops-synthetic-fixture',auth)
    if old:
        if old['sha256']!=sha or not any(m['id']==old['media_id'] for m in found):raise ValueError('Media receipt drift')
        media_id=old['media_id']
    else:
        if found:raise ValueError('Unowned synthetic media slug')
        uploaded=upload_request(root+'/wp-json/wp/v2/media',auth,blob,{'Content-Type':'image/png','Content-Disposition':'attachment; filename="rootedops-synthetic-fixture.png"'})
        media_id=uploaded['id']
        if uploaded['mime_type']!='image/png' or uploaded['media_details']['width']!=24 or uploaded['media_details']['height']!=24:raise ValueError('Uploaded raster mismatch')
        receipt.write_text(json.dumps({'media_id':media_id,'sha256':sha}));receipt.chmod(0o600)
    product=api(root+'/wp-json/wc/v3/products/'+str(baseline['simple_id']),auth)
    if product['sku']!='SYN-ROOTEDOPS-SIMPLE' or product['status']!='draft':raise ValueError('Synthetic draft ownership drift')
    metadata={m['key']:m['value'] for m in product['meta_data']}
    if metadata.get('_rootedops_source_key')!='synthetic:staging:SIMPLE':raise ValueError('Unowned product')
    updated=api(root+'/wp-json/wc/v3/products/'+str(product['id']),auth,'PUT',{'images':[{'id':media_id}]})
    if [i['id'] for i in updated['images']]!=[media_id]:raise ValueError('Woo media identity mismatch')
    php='$GLOBALS["wp_query"]=new WP_Query(["p"=>'+str(product['id'])+',"post_type"=>"product","post_status"=>"draft"]); if (!is_product()) { throw new Exception("Synthetic product query missing"); } $title=apply_filters("pre_get_document_title","Fallback"); $yoast=apply_filters("wpseo_title","Fallback"); $desc=apply_filters("wpseo_metadesc","Fallback"); ob_start(); rootedops_commerce_seo_head(); $head=ob_get_clean(); if ($title!=="Synthetic staging fixture" || $yoast!==$title || $desc!=="Synthetic SEO verification only" || strpos($head,esc_attr($desc))===false) { throw new Exception("SEO hook mismatch"); } echo json_encode(["native_hooks"=>true,"yoast_installed"=>defined("WPSEO_VERSION"),"browser_page_tested"=>false]);'
    compose=['docker','compose','--env-file',str(p/'.env'),'-f',str(p/'dank.yml'),'-f',str(private/'wordpress-offline.yml')]
    a=subprocess.run(compose+['run','--rm','--no-deps','dank-wordpress-cli','--user='+c['username'],'eval',php],stdin=subprocess.DEVNULL,capture_output=True,text=True)
    if a.returncode:
        log=private/'woo-seo-probe.log';log.write_text(a.stdout+a.stderr);log.chmod(0o600)
        raise RuntimeError('SEO probe failed; inspect private diagnostics')
    seo=json.loads(a.stdout)
    report={'media_id':media_id,'sha256':sha,'binary_upload':True,'woo_image_id_verified':True,'seo':seo,
            'synthetic_only':True,'erp_media_upload_tested':False,'checkout_tested':False}
    path=private/'woo-native-media-seo.json';path.write_text(json.dumps(report,indent=2));path.chmod(0o600)
    print(json.dumps(report))


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('environment',type=Path)
    run(p.parse_args().environment)
