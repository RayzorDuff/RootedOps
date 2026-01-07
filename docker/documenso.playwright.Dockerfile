FROM documenso/documenso:latest
#FROM mcr.microsoft.com/playwright:v1.57.0-nobl

# Documenso runs as a non-root user (commonly nodejs).
# We need root to install OS deps (curl + playwright deps).
USER root

# Install prerequisites for downloading/unpacking browsers + basic tooling
# Works on both Alpine (apk) and Debian/Ubuntu (apt-get).
RUN if command -v apk >/dev/null 2>&1; then \
      apk add --no-cache \
        curl \
        bash \
        ca-certificates \
        nss \
        freetype \
        harfbuzz \
        ttf-freefont \
        font-noto \
        udev \
        chromium \
        chromium-swiftshader \
        mesa \
        libstdc++ \
        libc6-compat \
        unzip \
        tar \
        xz \
      ; \
    elif command -v apt-get >/dev/null 2>&1; then \
      apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        fonts-liberation \
        libnss3 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcups2 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        xdg-utils \
        unzip \
        tar \
        xz-utils \
      && rm -rf /var/lib/apt/lists/* ; \
    else \
      echo "No supported package manager found" && exit 1; \
    fi

# Set the Playwright cache location to match
ENV PLAYWRIGHT_BROWSERS_PATH=/home/nodejs/.cache/ms-playwright

# Switch back to the app user. Many Documenso images use "nodejs".
# If your image uses a different user, adjust accordingly.
USER nodejs

# Ensure Playwright caches browsers where Documenso expects them
ENV PLAYWRIGHT_BROWSERS_PATH=/home/nodejs/.cache/ms-playwright

# Install Chromium (Playwright-managed) + required deps
# --with-deps installs OS libraries Playwright needs on Debian/Ubuntu-based images.
RUN npx playwright install

# Verify binary exists during build (fail fast)
RUN test -f /home/nodejs/.cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell
