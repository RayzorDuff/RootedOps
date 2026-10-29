import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
HELPER=ROOT/'backup/volume-tools.sh'

class BackupTests(unittest.TestCase):
    def validate(self,path):
        return subprocess.run(['bash','-c','source "$1"; validate_volume_archive "$2"','test',str(HELPER),str(path)],capture_output=True,text=True)

    def test_empty_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'empty.tgz'
            with tarfile.open(p,'w:gz') as t:
                info=tarfile.TarInfo('.');info.type=tarfile.DIRTYPE;t.addfile(info)
            self.assertNotEqual(self.validate(p).returncode,0)

    def test_nonempty_and_unsafe_archives(self):
        with tempfile.TemporaryDirectory() as d:
            for name,expected in [('database.sqlite',0),('../outside',1)]:
                p=Path(d)/'data.tgz'
                with tarfile.open(p,'w:gz') as t:
                    info=tarfile.TarInfo(name);info.size=4;t.addfile(info,io.BytesIO(b'test'))
                self.assertEqual(bool(self.validate(p).returncode),bool(expected))

    def test_actual_prefixed_mount_name_is_resolved(self):
        with tempfile.TemporaryDirectory() as d:
            docker=Path(d)/'docker'
            docker.write_text('#!/bin/sh\nprintf \'%s\\n\' \'[{"Destination":"/home/node/.n8n","Type":"volume","Name":"docker_n8n_data"}]\'\n')
            docker.chmod(0o755)
            r=subprocess.run(['bash','-c','source "$1"; DOCKER_BIN="$2"; resolve_mounted_volume n8n /home/node/.n8n','test',str(HELPER),str(docker)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0);self.assertEqual(r.stdout.strip(),'docker_n8n_data')

    def test_restore_validates_before_mutating(self):
        code=(ROOT/'backup/restore-stack.sh').read_text()
        self.assertLess(code.index('for archive in "$BACKUP_DIR"/volumes/*.tgz'),code.index('restore_mounted_volume nocodb'))
        self.assertNotIn('volume create',code)

class EncryptedReceiverTests(unittest.TestCase):
    def test_only_preapproved_ciphertext_is_accepted(self):
        import hashlib,importlib.util
        spec=importlib.util.spec_from_file_location('receiver',ROOT/'scripts/staging_receive_encrypted.py')
        receiver=importlib.util.module_from_spec(spec);spec.loader.exec_module(receiver)
        data=b'synthetic-ciphertext';boundary='test-boundary'
        body=(b'--test-boundary\r\nContent-Disposition: form-data; name="backup"; filename="backup.enc"\r\nContent-Type: application/octet-stream\r\n\r\n'+data+b'\r\n--test-boundary--\r\n')
        digest=hashlib.sha256(data).hexdigest()
        self.assertEqual(receiver.receive_payload(body,'multipart/form-data; boundary='+boundary,digest),data)
        with self.assertRaises(ValueError):receiver.receive_payload(body,'multipart/form-data; boundary='+boundary,'0'*64)
