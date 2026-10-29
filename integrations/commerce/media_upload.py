"""Upload verified archived image blobs to explicitly approved staging hosts.

Receipts make completed uploads repeatable. A crash after a remote response but
before receipt persistence can leave an orphan; reconcile by checksum filename
before retry. No production hostname or redirect is accepted.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from ecwid_migrate import private_write


def verified_blob(root, row):
    sha=row['sha256']
    if len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha) or row['file']!=sha:
        raise ValueError('Manifest must use checksum blob filenames')
    path=Path(root)/sha
    if path.is_symlink():raise ValueError('Media symlink rejected')
    content=path.read_bytes()
    if not content or len(content)>50*1024*1024 or hashlib.sha256(content).hexdigest()!=sha or len(content)!=row['bytes']:
        raise ValueError('Archived media checksum/size mismatch')
    signatures={'image/png':lambda b:b.startswith(b'\x89PNG\r\n\x1a\n'),
                'image/jpeg':lambda b:b.startswith(b'\xff\xd8\xff'),
                'image/gif':lambda b:b.startswith((b'GIF87a',b'GIF89a')),
                'image/webp':lambda b:b.startswith(b'RIFF') and b[8:12]==b'WEBP'}
    mime=row['content_type'].split(';')[0].strip().lower()
    if mime not in signatures or not signatures[mime](content):
        raise ValueError('Unsupported/mismatched raster image; SVG/HTML are not uploaded')
    return content,mime


def upload_request(url,authorization,body,headers):
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('Upload redirect rejected')
    request=Request(url,data=body,headers=dict(headers,Authorization=authorization),method='POST')
    with build_opener(NoRedirect).open(request,timeout=120) as response:
        return json.load(response)


def upload(manifest,blob_dir,receipt_path,erp_url,shop_url,erp_auth,shop_auth,request=upload_request):
    for url,host in ((erp_url,'erp-test.danks.store'),(shop_url,'shop-test.danks.store')):
        p=urlsplit(url)
        if p.scheme!='https' or p.hostname!=host or p.port not in (None,443) or p.username or p.password or p.query or p.fragment or p.path not in ('','/'):
            raise ValueError('Uploads require exact approved HTTPS staging origins')
    verified=[(row,*verified_blob(blob_dir,row)) for row in manifest] # Preflight all files.
    path=Path(receipt_path)
    receipts=json.loads(path.read_text()) if path.exists() else {}
    scope=erp_url.rstrip('/')+'|'+shop_url.rstrip('/')
    if receipts and receipts.get('scope')!=scope:raise ValueError('Receipt destination drift')
    receipts.setdefault('scope',scope);receipts.setdefault('blobs',{})
    result=[]
    for row,content,mime in verified:
        sha=row['sha256'];record=receipts['blobs'].setdefault(sha,{})
        filename=sha+'.'+{'image/png':'png','image/jpeg':'jpg','image/gif':'gif','image/webp':'webp'}[mime]
        if not record.get('erp_file_url'):
            boundary='rootedops'+sha
            body=(f'--{boundary}\r\nContent-Disposition: form-data; name="is_private"\r\n\r\n0\r\n'
                  f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                  f'Content-Type: {mime}\r\n\r\n').encode()+content+f'\r\n--{boundary}--\r\n'.encode()
            reply=request(erp_url.rstrip('/')+'/api/method/upload_file',erp_auth,body,
                          {'Content-Type':'multipart/form-data; boundary='+boundary})
            file_url=reply['message']['file_url']
            if not file_url.startswith('/files/') or '..' in file_url:raise ValueError('Unexpected ERP File URL')
            record['erp_file_url']=file_url;private_write(path,receipts)
        if not record.get('woocommerce_media_id'):
            reply=request(shop_url.rstrip('/')+'/wp-json/wp/v2/media',shop_auth,content,
                          {'Content-Type':mime,'Content-Disposition':f'attachment; filename="{filename}"'})
            if type(reply['id']) is not int or reply['id']<=0:raise ValueError('Invalid Woo media identity')
            record['woocommerce_media_id']=reply['id'];private_write(path,receipts)
        result.append(dict(row,**record))
    return result
