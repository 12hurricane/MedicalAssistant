# Stage 1: Build Flutter Web App
FROM ghcr.io/cirruslabs/flutter:3.27.1 AS builder

WORKDIR /app

# Copy dependency configs and resolve
COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

# Copy source code and build optimized web release bundle
COPY . .
RUN flutter build web --release

# Stage 2: Minimal hardened Nginx runtime
FROM nginx:1.25-alpine

# envsubst is included in the gettext package (not installed by default in alpine)
RUN apk add --no-cache gettext

# Remove default configuration
RUN rm /etc/nginx/conf.d/default.conf

# Install template (env vars substituted at startup) and entrypoint
COPY nginx.conf.template /etc/nginx/conf.d/default.conf.template
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy compiled Flutter web release bundle
COPY --from=builder /app/build/web /usr/share/nginx/html

# Railway injects $PORT — expose 80 as a safe default for local Docker
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://localhost/ || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
