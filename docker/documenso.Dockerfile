# Build stage
FROM node:20-bookworm AS fetch
WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Clone Documenso
# Pin a tag/commit once you confirm a stable version you like.
RUN git clone https://github.com/documenso/documenso.git ./

# Install deps
RUN corepack enable
RUN npm install -g npm
RUN npm ci --verbose

FROM node:20-bookworm AS build
WORKDIR /app

# Copy built app
COPY --from=fetch /app /app

# Build
RUN npm run build 

# Runtime stage
FROM node:20-bookworm AS runtime
WORKDIR /app

# Playwright/Chromium runtime deps + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    fonts-liberation \
    libnss3 libatk-bridge2.0-0 libatk1.0-0 \
    libcups2 libdrm2 libgbm1 libgtk-3-0 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 \
    xdg-utils \
  && rm -rf /var/lib/apt/lists/*

# Enable pnpm in runtime
RUN corepack enable

# Copy built app
COPY --from=build /app /app

# Install Playwright browsers (glibc-compatible)
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN npx playwright install chromium

# Use a non-root user
RUN useradd -m -u 10001 documenso && chown -R documenso:documenso /app /ms-playwright
USER documenso

EXPOSE 3000
CMD ["pnpm", "start"]
