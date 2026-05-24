# ============================================================
# AI Outbound OS — Frontend Dockerfile
# Multi-stage: Node builder → Nginx runtime
# ============================================================

FROM node:22-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_APP_VERSION=""
ARG VITE_GIT_SHA=""
ENV VITE_APP_VERSION=$VITE_APP_VERSION
ENV VITE_GIT_SHA=$VITE_GIT_SHA
RUN npm run build

# ── Runtime ──────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
