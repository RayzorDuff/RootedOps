#!/usr/bin/env bash
set -euo pipefail

restart=true
verify_only=false
case "${1:-}" in
  "") ;;
  --no-restart) restart=false ;;
  --verify-only) verify_only=true ;;
  *) echo "Usage: bash scripts/erpnext-repair-commerce-imports.sh [--no-restart|--verify-only]" >&2; exit 2 ;;
esac

python=/home/frappe/frappe-bench/env/bin/python
services=(erpnext-backend erpnext-scheduler erpnext-queue-short erpnext-queue-long)
sudo -v

verify_import() {
  sudo docker exec "$1" "$python" -c '
from pathlib import Path
import rootedops_commerce

expected = Path("/home/frappe/frappe-bench/apps/rootedops_commerce").resolve()
actual = Path(rootedops_commerce.__file__).resolve()
if not actual.is_relative_to(expected):
    raise SystemExit(f"Unexpected commerce import location: {actual}")
'
}

for service in "${services[@]}"; do
  if verify_import "$service" >/dev/null 2>&1; then
    echo "$service: commerce import already works."
    continue
  fi

  if "$verify_only"; then
    verify_import "$service"
    exit 1
  fi

  sudo docker exec -u 0 "$service" "$python" -c '
import importlib.util
from pathlib import Path
import sysconfig

source = Path("/home/frappe/frappe-bench/apps/rootedops_commerce")
if not (source / "rootedops_commerce" / "__init__.py").is_file():
    raise SystemExit(f"Commerce source is missing from the shared app volume: {source}")
if importlib.util.find_spec("rootedops_commerce") is not None:
    raise SystemExit("Commerce resolves to an existing package; inspect the import error before changing it.")
registration = Path(sysconfig.get_path("purelib")) / "rootedops-commerce-volume.pth"
with registration.open("x") as stream:
    stream.write(str(source) + "\n")
registration.chmod(0o644)
'
  verify_import "$service"
  echo "$service: registered and verified commerce from the shared app volume."
  if "$restart"; then
    sudo docker restart "$service" >/dev/null
    verify_import "$service"
    echo "$service: restarted and verified."
  fi
done
