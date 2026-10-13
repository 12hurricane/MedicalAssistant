# Stage 1: Build Flutter Web App
FROM ghcr.io/cirruslabs/flutter:3.27.1 AS builder

WORKDIR /app

# Copy dependency configs and resolve
COPY pubspec.yaml pubspec.lock ./
RUN flutter pub get

# Copy source code and build optimized web release bundle
COPY . .
RUN flutter build web --release

# Stage 2: Minimal hardened unprivileged Nginx runtime
FROM nginx:1.25-alpine

# envsubst is included in the gettext package (not installed by default in alpine)
RUN apk add --no-cache gettext

# Configure permissions and paths for unprivileged nginx execution (UID 101)
RUN sed -i 's|/var/run/nginx.pid|/tmp/nginx.pid|g' /etc/nginx/nginx.conf && \
    mkdir -p /var/cache/nginx /var/log/nginx /usr/share/nginx/html /etc/nginx/conf.d && \
    chown -R nginx:nginx /var/cache/nginx /var/log/nginx /etc/nginx /usr/share/nginx/html

# Remove default configuration
RUN rm -f /etc/nginx/conf.d/default.conf

# Install template (env vars substituted at startup) and entrypoint
COPY --chown=nginx:nginx nginx.conf.template /etc/nginx/conf.d/default.conf.template
COPY --chown=nginx:nginx docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy compiled Flutter web release bundle from builder stage
COPY --from=builder --chown=nginx:nginx /app/build/web /usr/share/nginx/html

# Run master process as non-root user
USER nginx

# Unprivileged port binding
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:${PORT:-8080}/ || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
