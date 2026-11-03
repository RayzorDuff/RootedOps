#!/usr/bin/env python3
"""One-way archived image import: production ERP File + draft Woo staging Media.

A separate native transport is intentional: ERP is on the production host,
while WooCommerce is only shop-test. Never uses staging_origin or bypasses it.
No product, stock, tax, order, invoice or payment writes.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integrations/commerce"))
from ecwid_migrate import private_write
from media_upload import verified_blob

ERP_SITE = "erp.danks.store"
SHOP = "dank-store-test-dank-wordpress-1"
STORE_ID = "95802503"
MIMES = {"image/jpeg": "jpg", "image/png": "png",
         "image/webp": "webp", "image/gif": "gif"}

# Frappe's installed API handles EXIF normalization and physical deduplication.
ERP_PY = r"""
import sys,json,base64,hashlib,frappe
from frappe.utils.file_manager import save_file,get_content_hash
from frappe.core.doctype.file.file import strip_exif_data
a=json.load(sys.stdin)
frappe.init(site='erp.danks.store');frappe.connect()
try:
 frappe.set_user('Administrator')
 assert frappe.local.site=='erp.danks.store'
 blob=base64.b64decode(a['blob'],validate=True)
 assert hashlib.sha256(blob).hexdigest()==a['sha256']
 assert a['filename'].startswith(a['sha256']+'.')
 normalized=(strip_exif_data(blob,'image/jpeg')
             if a['filename'].endswith('.jpg') and frappe.get_system_settings('strip_exif_metadata_from_uploaded_images')
             else blob)
 matches=frappe.get_all('File',filters={'content_hash':get_content_hash(normalized),'is_private':0},
                        fields=['name','file_url'],order_by='creation asc')
 if matches:
  doc=frappe.get_doc('File',matches[0].name)
  stored=doc.get_content()
  if isinstance(stored,str):stored=stored.encode()
  assert hashlib.sha256(stored).digest()==hashlib.sha256(normalized).digest()
  url=doc.file_url
 else:
  doc=save_file(a['filename'],blob,None,None,is_private=0)
  url=doc.file_url
 assert url.startswith('/files/') and '..' not in url
 frappe.db.commit()
 print(json.dumps({'file_url':url}))
except BaseException:
 frappe.db.rollback();raise
finally:frappe.destroy()
"""

# WP accepts input via stdin, not via CLI argv; no passwords or public REST APIs.
WP_PHP = r"""
require '/var/www/html/wp-load.php';
require_once ABSPATH.'wp-admin/includes/image.php';
require_once ABSPATH.'wp-admin/includes/file.php';
require_once ABSPATH.'wp-admin/includes/media.php';
$input=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
$sha=$input['sha256'];$mime=$input['mime'];$filename=$input['filename'];
$bytes=base64_decode($input['blob'],true);
if (!preg_match('/^[a-f0-9]{64}$/D',$sha) ||
    !preg_match('/^[a-f0-9]{64}\\.(jpg|png|webp|gif)$/D',$filename) ||
    $bytes===false || hash('sha256',$bytes)!==$sha) { throw new Exception('Invalid image identity'); }
if (get_option('woocommerce_coming_soon')!=='yes' ||
    get_option('woocommerce_calc_taxes')!=='no' ||
    (int)wp_count_posts('product')->publish!==0 ||
    count(WC()->payment_gateways()->get_available_payment_gateways())!==0) {
    throw new Exception('Staging safety controls changed');
}
$webhooks=get_posts(['post_type'=>'shop_webhook','post_status'=>'publish','numberposts'=>1]);
if (count($webhooks)) { throw new Exception('Active Woo webhooks exist'); }
$hits=get_posts(['post_type'=>'attachment','post_status'=>'inherit','numberposts'=>-1,
                 'meta_key'=>'_rootedops_media_sha256','meta_value'=>$sha,'fields'=>'ids']);
if (count($hits)>1) { throw new Exception('Ambiguous archived attachment'); }
if (count($hits)===1) {
    $id=(int)$hits[0]; $path=get_attached_file($id);
    if (!$path || !is_file($path) || hash_file('sha256',$path)!==$sha) {
        throw new Exception('Existing media differs from source hash');
    }
} else {
    // A failed post-insertion receipt can leave an attachment without custom
    // metadata; recover it by deterministic filename and original content hash.
    global $wpdb;
    $like='%/'.$wpdb->esc_like($filename);
    $rows=$wpdb->get_col($wpdb->prepare(
        "SELECT post_id FROM {$wpdb->postmeta} WHERE meta_key='_wp_attached_file' AND meta_value LIKE %s",$like));
    if (count($rows)>1) { throw new Exception('Ambiguous checksum filename'); }
    if (count($rows)===1) {
        $id=(int)$rows[0];$path=get_attached_file($id);
        if (!is_file($path) || hash_file('sha256',$path)!==$sha) {
            throw new Exception('Existing filename has unexpected contents');
        }
    } else {
        $uploaded=wp_upload_bits($filename,null,$bytes);
        if (!empty($uploaded['error'])) { throw new Exception($uploaded['error']); }
        if (hash_file('sha256',$uploaded['file'])!==$sha) { throw new Exception('Upload changed original'); }
        $id=wp_insert_attachment(['post_mime_type'=>$mime,'post_title'=>$sha,
                                  'post_status'=>'inherit'], $uploaded['file']);
        if (is_wp_error($id) || !$id) { throw new Exception('Attachment insert failed'); }
        update_post_meta($id,'_rootedops_media_sha256',$sha);
        wp_update_attachment_metadata($id,wp_generate_attachment_metadata($id,$uploaded['file']));
    }
    update_post_meta($id,'_rootedops_media_sha256',$sha);
}
echo json_encode(['media_id'=>(int)$id],JSON_THROW_ON_ERROR);
"""

def command(argv, payload):
    r=subprocess.run(argv,input=json.dumps(payload),text=True,capture_output=True)
    if r.returncode:
        raise RuntimeError("Native media command failed (exit " + str(r.returncode) +
                           "); review server logs. " + r.stderr[-400:])
    return json.loads(r.stdout)

def preflight(manifest, blobs, expected_sha):
    raw=manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha:
        raise ValueError("Manifest SHA256 mismatch")
    rows=json.loads(raw)
    if len(rows)!=37 or len({r["url"] for r in rows})!=37:
        raise ValueError("Expected 37 unique pilot source URLs")
    verified={}
    for row in rows:
        data,mime=verified_blob(blobs,row)
        sha=row["sha256"]
        if sha in verified and verified[sha][1]!=mime:
            raise ValueError("Conflicting MIME for same checksum")
        verified[sha]=(data,mime)
    if len(verified)!=11:
        raise ValueError("Expected 11 unique pilot media binaries")
    return rows,verified

def guard_live():
    inspect=json.loads(subprocess.check_output(
        ["docker","inspect",SHOP]))[0]
    if (inspect["Config"]["Labels"].get("com.docker.compose.project")!="dank-store-test"
        or not inspect["State"]["Running"]):
        raise ValueError("Unexpected staging container")
    code="""require '/var/www/html/wp-load.php';
echo json_encode(['origin'=>get_option('siteurl'),
 'coming'=>get_option('woocommerce_coming_soon'),
 'tax'=>get_option('woocommerce_calc_taxes'),
 'products'=>(int)wp_count_posts('product')->publish,
 'gateways'=>count(WC()->payment_gateways()->get_available_payment_gateways()),
 'webhooks'=>count(get_posts(['post_type'=>'shop_webhook','post_status'=>'publish','numberposts'=>1]))]);"""
    state=json.loads(subprocess.check_output(["docker","exec",SHOP,"php","-r",code]))
    if state!={"origin":"https://shop-test.danks.store","coming":"yes",
               "tax":"no","products":0,"gateways":0,"webhooks":0}:
        raise ValueError("Staging storefront is not isolated: "+repr(state))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--blob-dir",type=Path,required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--receipt",type=Path,required=True)
    p.add_argument("--apply",action="store_true")
    a=p.parse_args()
    rows,verified=preflight(a.manifest,a.blob_dir,a.sha256)
    if a.receipt.exists():
        receipt=json.loads(a.receipt.read_text())
        if receipt.get("manifest_sha256")!=a.sha256 or receipt.get("scope")!="erp.danks.store|shop-test.danks.store":
            raise ValueError("Receipt identity drift")
    else:
        receipt={"scope":"erp.danks.store|shop-test.danks.store",
                 "manifest_sha256":a.sha256,"blobs":{}}
    summary={"source_urls":len(rows),"unique_verified_blobs":len(verified),
             "previously_receipted":len(receipt["blobs"]),"write_requested":a.apply}
    if not a.apply:
        print(json.dumps(summary,indent=2));return
    if os.geteuid()!=0:
        raise ValueError("Use sudo for the native Docker media transport")
    guard_live()
    if a.receipt.parent.stat().st_mode & 0o077:
        raise ValueError("Receipt parent directory must be private")
    for sha,(data,mime) in sorted(verified.items()):
        guard_live()
        record=receipt["blobs"].setdefault(sha,{})
        payload={"sha256":sha,"filename":sha+"."+MIMES[mime],
                 "mime":mime,"blob":base64.b64encode(data).decode()}
        if not record.get("erp_file_url"):
            response=command(["docker","compose","--env-file",str(ROOT/".env"),
                "-f",str(ROOT/"docker/docker-compose.yml"),"exec","-T",
                "-w","/home/frappe/frappe-bench/sites","erpnext-backend",
                "/home/frappe/frappe-bench/env/bin/python","-c",ERP_PY],payload)
            record["erp_file_url"]=response["file_url"]
            private_write(a.receipt,receipt)
        if not record.get("woocommerce_media_id"):
            response=command(["docker","exec","-i",SHOP,"php","-r",WP_PHP],payload)
            record["woocommerce_media_id"]=response["media_id"]
            private_write(a.receipt,receipt)
    # Expand deduplicated binary receipts to each original source URL.
    mapped=[dict(row,**receipt["blobs"][row["sha256"]]) for row in rows]
    private_write(a.receipt.with_name("uploaded-media.json"),mapped)
    print(json.dumps(dict(summary,uploaded_blobs=len(receipt["blobs"]),
                          mapped_urls=len(mapped)),indent=2))

if __name__=="__main__":
    main()
