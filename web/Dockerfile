# 使用了国内镜像，如果不在国内，需自行修改镜像地址。

# Next.js Web Application Dockerfile for HTTPS Development
FROM node:18-alpine AS base

# Install dependencies and mkcert for SSL certificate generation
FROM base AS deps
# Install required packages
RUN apk add --no-cache libc6-compat curl wget
WORKDIR /app

# Install mkcert
RUN wget https://github.com/FiloSottile/mkcert/releases/download/v1.4.4/mkcert-v1.4.4-linux-amd64 \
    && chmod +x mkcert-v1.4.4-linux-amd64 \
    && mv mkcert-v1.4.4-linux-amd64 /usr/local/bin/mkcert

# Copy package files and install dependencies
COPY package*.json ./
RUN npm ci

# Development image with SSL support
FROM base AS runner
WORKDIR /app

# Install mkcert in the final image
RUN apk add --no-cache libc6-compat curl wget nss-tools \
    && wget https://github.com/FiloSottile/mkcert/releases/download/v1.4.4/mkcert-v1.4.4-linux-amd64 \
    && chmod +x mkcert-v1.4.4-linux-amd64 \
    && mv mkcert-v1.4.4-linux-amd64 /usr/local/bin/mkcert

# Copy dependencies and source code
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Set environment variables for development
ENV NODE_ENV development
ENV NEXT_TELEMETRY_DISABLED 1

# Create nextjs user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Generate SSL certificates
RUN mkcert -install && mkcert localhost 127.0.0.1 ::1

# Change ownership of the workspace
RUN chown -R nextjs:nodejs /app

USER nextjs

EXPOSE 3000

ENV PORT 3000
ENV HOSTNAME "0.0.0.0"

# Health check - check if Next.js HTTPS server is responding
HEALTHCHECK --interval=30s --timeout=30s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider --no-check-certificate https://localhost:3000/ || exit 1

# Start Next.js in HTTPS development mode
CMD ["npm", "run", "dev_https"]
