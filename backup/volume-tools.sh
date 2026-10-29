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
import posixpath,sys,tarfile
archive_name=posixpath.basename(sys.argv[1])
# Frappe creates these two absolute asset links inside the sites volume.
# Allow them only in that archive, at these exact paths and targets.
frappe_asset_links={
    'assets/frappe': '/home/frappe/frappe-bench/apps/frappe/frappe/public',
    'assets/erpnext': '/home/frappe/frappe-bench/apps/erpnext/erpnext/public',
} if archive_name=='erpnext_sites.tgz' else {}
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
                if not (member.issym() and frappe_asset_links.get(name)==member.linkname):
                    raise SystemExit('Unsafe archive link: '+member.name+' -> '+member.linkname)
PY
}

# Redis cache/queue snapshots may legitimately contain no persistent state.
validate_managed_volume_archive() {
  case "${1##*/}" in
    erpnext_redis_cache_data.tgz|erpnext_redis_queue_data.tgz)
      validate_volume_archive "$1" allow-empty ;;
    *) validate_volume_archive "$1" ;;
  esac
}
