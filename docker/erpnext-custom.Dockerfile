ARG ERPNEXT_IMAGE_TAG=version-16
ARG ERPNEXT_HRMS_BRANCH=version-16
ARG ERPNEXT_ESS_BRANCH=version-16

FROM frappe/erpnext:${ERPNEXT_IMAGE_TAG}
ARG ERPNEXT_HRMS_BRANCH=version-16
ARG ERPNEXT_ESS_BRANCH=version-16

USER root
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /home/frappe/frappe-bench

# Copy local custom app into the image
COPY erpnext/apps/rootedops_payroll /home/frappe/frappe-bench/apps/rootedops_payroll
RUN chown -R frappe /home/frappe/frappe-bench/apps/rootedops_payroll

COPY erpnext/apps/rootedops_commerce /home/frappe/frappe-bench/apps/rootedops_commerce
RUN chown -R frappe /home/frappe/frappe-bench/apps/rootedops_commerce
COPY docker/fetch-frappe-app.sh /usr/local/bin/fetch-frappe-app.sh

USER frappe

# Refresh app repos that are not bundled the way you want
RUN rm -rf apps/hrms apps/employee_self_service && \
    bash /usr/local/bin/fetch-frappe-app.sh apps/hrms https://github.com/frappe/hrms.git "${ERPNEXT_HRMS_BRANCH:-version-16}" && \
    bash /usr/local/bin/fetch-frappe-app.sh apps/employee_self_service https://github.com/nesscale-com/employee_self_service.git "${ERPNEXT_ESS_BRANCH:-version-16}" && \
    ./env/bin/pip install --no-cache-dir -e apps/hrms -e apps/employee_self_service -e apps/rootedops_payroll -e apps/rootedops_commerce
