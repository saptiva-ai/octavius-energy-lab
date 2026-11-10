# =========================================
# MULTI-STAGE DOCKERFILE FOR NEXT.JS WEB
# =========================================
# Strategy: Preserve standalone hierarchy, solidify symlinks in builder
ARG UID=1000
ARG GID=1000
FROM oven/bun:1-alpine AS base

WORKDIR /app

# Copy root package files
COPY bun.lock package.json ./
COPY packages/ ./packages/
COPY apps/web/package.json ./apps/web/

# =========================================
# DEPENDENCIES STAGE
# =========================================
FROM base AS deps
RUN bun install --frozen-lockfile

# =========================================
# DEVELOPMENT STAGE (for docker-compose.dev.yml)
# =========================================
FROM base AS dev
ARG UID
ARG GID

# Node REAL para jest: la imagen bun solo trae el fallback-shim de node y
# jest 29 no corre bajo el runtime de bun ("Attempted to assign to readonly
# property"). apk node queda antes del fallback en PATH. (F1 refactor-web)
RUN apk add --no-cache nodejs

# Install dependencies
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules

# Copy web source
COPY apps/web ./apps/web

# Ensure the non-root dev user (UID/GID from compose) can write to the workspace
RUN mkdir -p /app/apps/web/.next && \
    chown -R ${UID}:${GID} /app/apps/web /app/node_modules

WORKDIR /app/apps/web

# Development environment
ENV NODE_ENV=development
EXPOSE 3000

# Default command for development (hot-reload)
CMD ["bun", "run", "dev", "--hostname", "0.0.0.0", "--port", "3000"]

# =========================================
# BUILDER STAGE
# =========================================
FROM base AS builder

# Build arguments
ARG API_BASE_URL=http://backend:8000
ARG NEXT_PUBLIC_API_URL=
ARG NEXT_PUBLIC_APP_NAME="Saptiva Copilot OS"
ARG NEXT_PUBLIC_ENABLE_STREAMING=true
# Tools encendidas y fijas por despliegue (sin chip en el compositor).
ARG NEXT_PUBLIC_DEFAULT_TOOLS=
ARG NODE_ENV=production

ENV API_BASE_URL=$API_BASE_URL \
    NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_APP_NAME=$NEXT_PUBLIC_APP_NAME \
    NEXT_PUBLIC_ENABLE_STREAMING=$NEXT_PUBLIC_ENABLE_STREAMING \
    NEXT_PUBLIC_DEFAULT_TOOLS=$NEXT_PUBLIC_DEFAULT_TOOLS \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1

# Copy node_modules from deps (including devDeps for build)
COPY --from=deps /app/node_modules ./node_modules
COPY --from=deps /app/apps/web/node_modules ./apps/web/node_modules

# Copy web source
COPY apps/web ./apps/web

# Build the project
WORKDIR /app/apps/web
RUN bun run build

# =========================================
# SOLIDIFY STAGE - Resolve symlinks & flatten Bun modules
# =========================================
# This stage converts Bun's module structure to Node.js-compatible format
FROM alpine:3.19 AS solidify

RUN apk add --no-cache coreutils findutils

WORKDIR /app

# Copy standalone output
COPY --from=builder /app/apps/web/.next/standalone /app/standalone-raw

# Step 1: Solidify symlinks (convert to real files)
RUN mkdir -p /app/standalone && \
    cp -rL /app/standalone-raw/. /app/standalone/ 2>/dev/null || \
    (echo "Fallback: selective symlink resolution" && \
     cp -r /app/standalone-raw/. /app/standalone/ && \
     find /app/standalone -type l -exec sh -c 'target=$(readlink -f "$1") && rm "$1" && cp -r "$target" "$1" 2>/dev/null || rm "$1"' _ {} \;) && \
    rm -rf /app/standalone-raw

# Step 2: Flatten Bun's .bun structure to standard Node.js node_modules
# Bun stores: node_modules/.bun/<pkg>@<ver>/node_modules/<pkg>/
# Node expects: node_modules/<pkg>/
RUN for nm_path in $(find /app/standalone -type d -name "node_modules" 2>/dev/null); do \
      bun_dir="$nm_path/.bun"; \
      if [ -d "$bun_dir" ]; then \
        echo "Flattening Bun modules in: $nm_path"; \
        for pkg_ver_dir in "$bun_dir"/*/; do \
          if [ -d "${pkg_ver_dir}node_modules" ]; then \
            for pkg_dir in "${pkg_ver_dir}node_modules"/*/; do \
              pkg_name=$(basename "$pkg_dir"); \
              if [ ! -e "$nm_path/$pkg_name" ]; then \
                cp -r "$pkg_dir" "$nm_path/$pkg_name"; \
              fi; \
            done; \
            for scope_dir in "${pkg_ver_dir}node_modules"/@*/; do \
              if [ -d "$scope_dir" ]; then \
                scope_name=$(basename "$scope_dir"); \
                mkdir -p "$nm_path/$scope_name"; \
                for scoped_pkg in "$scope_dir"/*/; do \
                  scoped_name=$(basename "$scoped_pkg"); \
                  if [ ! -e "$nm_path/$scope_name/$scoped_name" ]; then \
                    cp -r "$scoped_pkg" "$nm_path/$scope_name/$scoped_name"; \
                  fi; \
                done; \
              fi; \
            done; \
          fi; \
        done; \
      fi; \
    done

# Copy static assets
COPY --from=builder /app/apps/web/.next/static /app/static
COPY --from=builder /app/apps/web/public /app/public

# =========================================
# PRODUCTION STAGE
# =========================================
FROM node:20-alpine AS runner

WORKDIR /app
ENV NODE_ENV=production

# Create production user
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Copy solidified standalone (preserving full hierarchy)
# The structure is: /app/standalone/apps/web/server.js with node_modules at various levels
COPY --from=solidify --chown=nextjs:nodejs /app/standalone ./

# Copy static assets to the correct location within the standalone hierarchy
# server.js expects .next/static relative to apps/web/
COPY --from=solidify --chown=nextjs:nodejs /app/static ./apps/web/.next/static
COPY --from=solidify --chown=nextjs:nodejs /app/public ./apps/web/public

# Create cache directory with correct permissions to prevent EACCES errors
# Note: Production override sets user to 1000:1000 (node), not nextjs (1001)
# So we need to set ownership to node:node for cache directory
RUN mkdir -p /app/apps/web/.next/cache/images && \
    chown -R node:node /app/apps/web/.next/cache && \
    chmod -R 755 /app/apps/web/.next/cache

USER nextjs

EXPOSE 3000
ENV PORT=3000 \
    HOSTNAME="0.0.0.0"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000 || exit 1

# Execute from the correct location - server.js is inside apps/web/
CMD ["node", "apps/web/server.js"]
