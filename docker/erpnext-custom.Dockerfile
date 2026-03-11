ARG ERPNEXT_IMAGE_TAG=v16.78.0
FROM frappe/erpnext:${ERPNEXT_IMAGE_TAG}

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

USER frappe
WORKDIR /home/frappe/frappe-bench

ARG ERPNEXT_HRMS_BRANCH=version-16
RUN bench get-app --branch "${ERPNEXT_HRMS_BRANCH}" hrms https://github.com/frappe/hrms \
    && python3 - <<'PY'
from pathlib import Path
path = Path('/home/frappe/frappe-bench/sites/apps.txt')
apps = [line.strip() for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
if 'hrms' not in apps:
    apps.append('hrms')
path.write_text('\n'.join(apps) + '\n')
print(path.read_text())
PY
