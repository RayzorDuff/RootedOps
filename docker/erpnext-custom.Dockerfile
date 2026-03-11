ARG ERPNEXT_IMAGE_TAG=version-16

FROM frappe/erpnext:${ERPNEXT_IMAGE_TAG}

USER root
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*
USER frappe
WORKDIR /home/frappe/frappe-bench