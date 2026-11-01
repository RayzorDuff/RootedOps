"""Resolve commerce targets from a matching generated test receipt/environment."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/commerce'))
from staging_origin import staging_pair
from commerce_restore import read_env
from host_recovery import deployment_hosts


def targets(environment):
    if (environment/'TEST_ENVIRONMENT').read_text().strip() != 'rootedops-full-test':
        raise ValueError('Explicit isolated environment required')
    hosts=deployment_hosts(environment)
    if read_env(environment/'.env').get('ERPNEXT_SITE_NAME') != hosts['erpnext']:
        raise ValueError('Receipt/environment hostname mismatch')
    erp,shop=staging_pair('https://'+hosts['erpnext'],'https://'+hosts['dank-wordpress'])
    return {'erp':erp,'shop':shop,'hosts':tuple(hosts[k] for k in ('erpnext','appsmith','n8n','dank-wordpress'))}
