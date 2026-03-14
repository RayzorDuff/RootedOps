# syntax=docker/dockerfile:1.7

ARG NODE_VERSION=20
ARG DOCUMENSO_REF=main

############################
# Builder
############################
FROM node:${NODE_VERSION}-bookworm AS builder

ARG DOCUMENSO_REF

ENV DEBIAN_FRONTEND=noninteractive
ENV CI=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ca-certificates \
    openssl \
    python3 \
    make \
    g++ \
    pkg-config \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN corepack enable

# Clone source in builder only
RUN git clone --depth=1 --branch "${DOCUMENSO_REF}" https://github.com/documenso/documenso.git .

# Install dependencies and build
# If your current Dockerfile uses a different package manager command,
# keep the same command sequence here.
RUN if [ -f pnpm-lock.yaml ]; then \
      corepack prepare pnpm@latest --activate && \
      pnpm install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
      npm ci; \
    elif [ -f yarn.lock ]; then \
      corepack prepare yarn@stable --activate && \
      yarn install --frozen-lockfile; \
    else \
      echo "No supported lockfile found" && exit 1; \
    fi

RUN if [ -f pnpm-lock.yaml ]; then \
      pnpm build; \
    elif [ -f package-lock.json ]; then \
      npm run build; \
    elif [ -f yarn.lock ]; then \
      yarn build; \
    fi

# Prune dev dependencies after build
#RUN if [ -f pnpm-lock.yaml ]; then \
#      pnpm prune --prod; \
#    elif [ -f package-lock.json ]; then \
#      npm prune --omit=dev; \
#    elif [ -f yarn.lock ]; then \
#      yarn install --production --frozen-lockfile; \
#    fi

############################
# Runtime
############################
FROM node:${NODE_VERSION}-bookworm-slim AS runtime

ENV DEBIAN_FRONTEND=noninteractive
ENV NODE_ENV=production
ENV PLAYWRIGHT_BROWSERS_PATH=/home/nodejs/.cache/ms-playwright
ENV TURBO_CACHE_DIR=/home/nodejs/.cache/turbo

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    openssl \
    dumb-init \
    chromium \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libc6 \
    libcairo2 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libfontconfig1 \
    libgbm1 \
    libgcc-s1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libstdc++6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Keep same user/path style as your existing env
RUN useradd -m -u 1001 -s /bin/bash nodejs

# Copy only built app and production deps
COPY --from=builder /src /app

# Remove source-control and caches that should not ship
RUN npm install -g turbo@^1.13.4 && \
    mkdir -p /home/nodejs/.cache/turbo /home/nodejs/.cache/ms-playwright /app/.turbo && \
    chown -R nodejs:nodejs /app /home/nodejs 
RUN rm -rf /app/.git /app/.github /root/.cache /tmp/*

USER nodejs

EXPOSE 3000

ENTRYPOINT ["dumb-init", "--"]

# Keep this aligned with the start command from your current Dockerfile if it differs
CMD ["npm", "--workspace", "@documenso/remix", "run", "start"]
