#!/usr/bin/env bash
# Source-only helpers; DOCKER_BIN follows the existing backup script convention.
resolve_mounted_volume() {
  local container="$1" destination="$2"
  $DOCKER_BIN inspect --format '{{json .Mounts}}' "$container" | python3 -c '
import json,sys
mounts=json.load(sys.stdin)
matches=[m for m in mounts if m.get("Destination")==sys.argv[1]]
if len(matches)!=1 or matches[0].get("Type")!="volume" or not matches[0].get("Name"):
    raise SystemExit("Expected exactly one named volume at configured container mount")
print(matches[0]["Name"])
' "$destination"
}

validate_volume_archive() {
  python3 - "$1" "${2:-required}" <<'PY'
import posixpath,re,sys,tarfile
archive_name=posixpath.basename(sys.argv[1])
# Frappe creates these two absolute asset links inside the sites volume.
# Allow them only in that archive, at these exact paths and targets.
frappe_asset_links={
    'assets/frappe': '/home/frappe/frappe-bench/apps/frappe/frappe/public',
    'assets/erpnext': '/home/frappe/frappe-bench/apps/erpnext/erpnext/public',
} if archive_name=='erpnext_sites.tgz' else {}
frappe_app_links={
    'frappe/frappe/public/node_modules': '/home/frappe/frappe-bench/apps/frappe/node_modules',
    'erpnext/erpnext/public/node_modules': '/home/frappe/frappe-bench/apps/erpnext/node_modules',
} if archive_name=='erpnext_apps.tgz' else {}
frappe_nested_asset_links={}
if re.fullmatch(r'erpnext_assets_[0-9]{2}\.tgz',archive_name):
    # These exact public asset links intentionally point into the restored apps
    # volume outside this child archive. No other escaping links are permitted.
    for app in ('frappe','erpnext','hrms','employee_self_service','rootedops_payroll','rootedops_commerce'):
        frappe_nested_asset_links[app]={
            '/home/frappe/frappe-bench/apps/'+app+'/'+app+'/public',
            '../../apps/'+app+'/'+app+'/public',
        }
with tarfile.open(sys.argv[1],'r:gz') as archive:
    members=archive.getmembers()
    if sys.argv[2]!='allow-empty' and not any(m.isfile() and m.size>0 for m in members):
        raise SystemExit('Refusing empty volume archive: no nonempty regular files')
    for member in members:
        name=posixpath.normpath(member.name)
        if member.name.startswith('/') or name=='..' or name.startswith('../'):
            raise SystemExit('Unsafe archive path: '+member.name)
        if member.isdev() or member.isfifo():
            raise SystemExit('Unsafe archive special file')
        if member.issym() or member.islnk():
            target=posixpath.normpath(posixpath.join(posixpath.dirname(name) if member.issym() else '',member.linkname))
            if target.startswith('/') or target=='..' or target.startswith('../'):
                if not (member.issym() and (frappe_asset_links.get(name)==member.linkname or frappe_app_links.get(name)==member.linkname or member.linkname in frappe_nested_asset_links.get(name,set()))):
                    raise SystemExit('Unsafe archive link: '+member.name+' -> '+member.linkname)
PY
}

# Cache, unused standalone Mongo configdb and upload/log directories can be empty.
# Primary MongoDB/Appsmith/n8n/scheduling databases must contain real files.
validate_managed_volume_archive() {
  # A declared assets child may be empty or contain only public asset symlinks.
  if [[ "${1##*/}" =~ ^erpnext_assets_[0-9]{2}\.tgz$ ]]; then
    validate_volume_archive "$1" allow-empty
    return
  fi
  case "${1##*/}" in
    erpnext_redis_cache_data.tgz|erpnext_redis_queue_data.tgz|librechat-data.tgz|librechat-uploads.tgz|librechat-logs.tgz|librechat-kids-data.tgz|librechat-kids-uploads.tgz|librechat-kids-logs.tgz|librechat-mongodb-config.tgz|librechat-kids-mongodb-config.tgz)
      validate_volume_archive "$1" allow-empty ;;
    *) validate_volume_archive "$1" ;;
  esac
}
