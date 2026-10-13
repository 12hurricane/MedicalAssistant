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

# Remove default configuration and add production reverse-proxy config
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy compiled Flutter web release bundle
COPY --from=builder /app/build/web /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
