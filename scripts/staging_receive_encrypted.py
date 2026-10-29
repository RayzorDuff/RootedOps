#!/usr/bin/env python3
"""Temporary ciphertext-only receiver for authorized staging backup uploads.

No read/download route, no arbitrary filenames, no decryption key. Only the exact
preapproved SHA-256 blob is accepted, once. Run on a disposable staging server.
"""
import argparse
from email.parser import BytesParser
from email.policy import default
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import os
from pathlib import Path
import re
import time
import ssl


def receive_payload(body,content_type,expected_digest):
    if len(body)>20*1024*1024:raise ValueError('Upload too large')
    message=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
    parts=[p for p in message.iter_parts() if p.get_param('name',header='content-disposition')=='backup']
    if len(parts)!=1:raise ValueError('Exactly one backup file required')
    payload=parts[0].get_payload(decode=True)
    if not payload or hashlib.sha256(payload).hexdigest()!=expected_digest:
        raise ValueError('Ciphertext checksum mismatch')
    return payload


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sha256',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--port',type=int,default=8080)
    p.add_argument('--certfile');p.add_argument('--keyfile')
    a=p.parse_args()
    if bool(a.certfile)!=bool(a.keyfile):p.error('Both TLS certificate and key paths are required')
    if not re.fullmatch('[a-f0-9]{64}',a.sha256):p.error('Invalid expected digest')
    a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def do_GET(self):
            if self.path!='/':self.send_error(404);return
            body=b'<html><body><h1>Staging encrypted backup transfer</h1><form method="post" enctype="multipart/form-data"><input type="file" name="backup" required><button type="submit">Upload encrypted backup</button></form></body></html>'
            self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(body)
        def do_POST(self):
            if self.path!='/':self.send_error(404);return
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=20*1024*1024:raise ValueError('Invalid upload size')
                payload=receive_payload(self.rfile.read(length),self.headers.get('Content-Type',''),a.sha256)
                fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as f:f.write(payload)
            except (ValueError,FileExistsError):self.send_error(400,'Upload rejected');return
            body=b'Ciphertext received and checksum verified.'
            self.send_response(200);self.send_header('Content-Type','text/plain');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=HTTPServer(('0.0.0.0',a.port),Handler)
    if a.certfile:
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(a.certfile,a.keyfile)
        server.socket=context.wrap_socket(server.socket,server_side=True)
    server.timeout=900
    print('Ciphertext-only receiver ready',flush=True)
    deadline=time.monotonic()+900
    while not a.output.exists() and time.monotonic()<deadline:
        server.timeout=max(1,deadline-time.monotonic())
        server.handle_request()
    server.server_close()

if __name__=='__main__':main()
