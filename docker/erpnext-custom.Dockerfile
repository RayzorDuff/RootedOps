ARG ERPNEXT_IMAGE_TAG=version-16
ARG ERPNEXT_HRMS_BRANCH=version-16
ARG ERPNEXT_ESS_BRANCH=version-16

FROM frappe/erpnext:${ERPNEXT_IMAGE_TAG}

USER root
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

USER frappe
WORKDIR /home/frappe/frappe-bench

RUN rm -rf apps/hrms apps/employee_self_service && \
    git clone --depth 1 --branch "${ERPNEXT_HRMS_BRANCH:-version-16}" https://github.com/frappe/hrms.git apps/hrms && \
    git clone --depth 1 --branch "${ERPNEXT_ESS_BRANCH:-version-16}" https://github.com/nesscale-com/employee_self_service.git apps/employee_self_service && \

./env/bin/pip install --no-cache-dir -e apps/hrms apps/employee_self_service
