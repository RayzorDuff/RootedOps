ARG ERPNEXT_IMAGE_TAG=version-16
ARG ERPNEXT_HRMS_BRANCH=version-16

FROM frappe/erpnext:${ERPNEXT_IMAGE_TAG}

USER root
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

USER frappe
WORKDIR /home/frappe/frappe-bench

RUN branch="${ERPNEXT_HRMS_BRANCH:-version-16}" && \
    if [ ! -d apps/hrms ]; then \
      git clone --depth 1 --branch "$branch" https://github.com/frappe/hrms.git apps/hrms; \
    fi && \

./env/bin/pip install --no-cache-dir -e apps/hrms
