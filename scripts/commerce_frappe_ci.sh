#!/usr/bin/env bash
# Run only inside the disposable CI image/network. No live site is accepted.
set -euo pipefail
cd /home/frappe/frappe-bench
[[ "${COMMERCE_NATIVE_CI:-}" == 1 ]]
[[ ! -e sites/commerce-test.local/site_config.json ]]
ln -s /opt/rootedops_commerce apps/rootedops_commerce
./env/bin/pip install --no-deps -e apps/rootedops_commerce
printf '\nrootedops_commerce\n' >> sites/apps.txt
bench set-config -g redis_cache redis://127.0.0.1:6379
bench set-config -g redis_queue redis://127.0.0.1:6379
bench new-site commerce-test.local --db-host 127.0.0.1 --db-port 3306 --db-root-username root \
  --db-root-password synthetic-ci-only --admin-password synthetic-ci-only --mariadb-user-host-login-scope='%'
bench --site commerce-test.local install-app erpnext
bench --site commerce-test.local install-app rootedops_commerce
bench --site commerce-test.local set-config allow_tests true
bench version
bench --site commerce-test.local run-tests --app rootedops_commerce
