#!/usr/bin/env python3
"""Native stopped-volume restore regression; disposable GitHub Actions only."""
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import yaml
from full_restore import Recovery
from commerce_restore import Restore


def main():
    if os.environ.get('GITHUB_ACTIONS')!='true':
        raise SystemExit('Run only on a disposable GitHub Actions runner')
    subprocess.run(['docker','pull','alpine:3.20'],check=True)
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);backup=root/'backup';(backup/'volumes').mkdir(parents=True)
        data=b'synthetic restored fixture\n'
        with tarfile.open(backup/'volumes/synthetic.tgz','w:gz') as archive:
            entry=tarfile.TarInfo('synthetic.txt');entry.size=len(data)
            archive.addfile(entry,io.BytesIO(data))
        for full,name in ((True,'rootedops-volume-ci'),(False,'commerce-test')):
            env=root/name;env.mkdir();(env/'.env').touch()
            config={'name':name,'services':{
                'fixture':{'image':'alpine:3.20','command':['sh','-c','exit 99'],
                    'depends_on':['unrelated'],'volumes':['state:/fixture']},
                'unrelated':{'image':'alpine:3.20','command':['sh','-c','exit 98']}},
                'volumes':{'state':None},'networks':{'default':{'internal':True}}}
            (env/('core.yml' if full else 'compose.yml')).write_text(yaml.safe_dump(config))
            restore=Recovery(env,backup) if full else Restore(env,backup,{})
            dc=restore.commands['core'] if full else restore.compose
            if subprocess.check_output(dc+['ps','-aq'],text=True).strip():raise RuntimeError('Fixture project must be fresh')
            if subprocess.check_output(['docker','volume','ls','-q','--filter','label=com.docker.compose.project='+name],text=True).strip():
                raise RuntimeError('Fixture volumes must be absent before testing')
            try:
                if full:restore.volume('core','fixture','/fixture','synthetic.tgz')
                else:restore.volume('fixture','/fixture','synthetic.tgz')
                cid=subprocess.check_output(dc+['ps','-aq','fixture'],text=True).strip()
                container=json.loads(subprocess.check_output(['docker','inspect',cid],text=True))[0]
                assert container['State']['Status']=='created',container['State']
                assert not subprocess.check_output(dc+['ps','-aq','unrelated'],text=True).strip()
                mount=next(m for m in container['Mounts'] if m['Destination']=='/fixture')
                restored=subprocess.check_output(['docker','run','--rm','--network','none','-v',mount['Name']+':/source:ro','alpine:3.20','cat','/source/synthetic.txt'])
                assert restored==data
            finally:
                subprocess.run(dc+['down','--volumes'],check=True)
    print('Both restore paths recover exact fixture bytes with app/dependencies never started')


if __name__=='__main__':main()
