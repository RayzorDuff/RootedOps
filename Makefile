.PHONY: version validate release-check prepare-release

version:
	@cat VERSION

validate:
	@bash -n linode_bootstrap.sh backup/*.sh docker/*.sh scripts/commerce_pg_roundtrip.sh
	@python3 -m compileall -q erpnext/apps/rootedops_payroll/rootedops_payroll erpnext/apps/rootedops_commerce/rootedops_commerce erpnext/scripts integrations/commerce scripts/commerce_staging.py scripts/commerce_restore.py

release-check: validate
	@python3 scripts/validate_release.py

prepare-release:
	@if [ -z "$(VERSION)" ]; then echo "Usage: make prepare-release VERSION=x.y.z [RELEASE_DATE=YYYY-MM-DD]"; exit 1; fi
	@python3 scripts/prepare_release.py --version "$(VERSION)" $(if $(RELEASE_DATE),--release-date "$(RELEASE_DATE)",)

.PHONY: commerce-test
commerce-test: validate
	@python3 -m unittest discover -s tests -p "test_commerce*.py" -v
