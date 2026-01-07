FROM documenso/documenso:latest

# Documenso runs as a non-root user (commonly nodejs).
# We need root to install OS deps (curl + playwright deps).
USER root

# Install curl (useful for debugging/healthchecks) and Playwright OS deps.
# The safest way is to let Playwright install deps for Chromium.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
  && rm -rf /var/lib/apt/lists/*

# Switch back to the app user. Many Documenso images use "nodejs".
# If your image uses a different user, adjust accordingly.
USER nodejs

# Ensure Playwright caches browsers where Documenso expects them
ENV PLAYWRIGHT_BROWSERS_PATH=/home/nodejs/.cache/ms-playwright

# Install Chromium (Playwright-managed) + required deps
# --with-deps installs OS libraries Playwright needs on Debian/Ubuntu-based images.
RUN npx playwright install --with-deps chromium
