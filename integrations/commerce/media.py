#!/usr/bin/env python3
"""Archive reviewed HTTPS product image URLs with checksums; no auth is sent."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from ecwid_migrate import private_write


def media_urls(source):
    urls = set()
    for product in source.get('products', []):
        for record in [product] + product.get('_combinations', []):
            for key in ('imageUrl','originalImageUrl','thumbnailUrl','smallThumbnailUrl','hdThumbnailUrl'):
                if record.get(key):urls.add(record[key])
            for image in record.get('galleryImages', []):
                for key in ('url','originalImageUrl','imageUrl','thumbnailUrl'):
                    if image.get(key):urls.add(image[key])
    return sorted(urls)


def validate_url(url, allowed_hosts):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('Media must use credential-free HTTPS on port 443')
    if parsed.hostname not in allowed_hosts:
        raise ValueError('Media host requires explicit review: ' + str(parsed.hostname))
    # Fail closed for internal/local media URLs. Only explicitly reviewed CDN hosts
    # are allowed; redirects are rejected rather than bypassing this validation.
    addresses = socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Media host resolves to non-public address')


def archive(source, output, allowed_hosts):
    output = Path(output);output.mkdir(mode=0o700,parents=True,exist_ok=True)
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):raise ValueError('Review redirected media URL explicitly')
    opener = build_opener(NoRedirect)
    manifest = []
    for url in media_urls(source):
        validate_url(url,allowed_hosts)
        with opener.open(Request(url,headers={'User-Agent':'RootedOps-Commerce-Archive/0.1'}),timeout=60) as response:
            content = response.read(50*1024*1024+1)
            if len(content)>50*1024*1024:raise ValueError('Media exceeds 50 MiB limit')
            content_type = response.headers.get('Content-Type','')
        checksum=hashlib.sha256(content).hexdigest()
        path=output/checksum
        if path.exists():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=checksum:raise ValueError('Corrupt existing archive blob')
        else:
            import os
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(content)
        manifest.append({'url':url,'sha256':checksum,'bytes':len(content),'content_type':content_type,'file':checksum})
        private_write(output/'manifest.json',manifest)
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--allow-host',action='append',required=True)
    a=p.parse_args();archive(json.loads(a.source.read_text()),a.output,set(a.allow_host))
