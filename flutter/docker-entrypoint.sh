#!/bin/sh
# Railway entrypoint: substitute env vars into nginx config, then start nginx
# Variables used:
#   PORT        – injected by Railway (default 80 for local Docker)
#   BACKEND_URL – internal Railway URL of the backend service,
#                 e.g. http://backend.railway.internal:8000
#                 Set this in the frontend service's Railway environment variables.

set -e

export PORT="${PORT:-80}"
export BACKEND_URL="${BACKEND_URL:-http://backend:8000}"

# Substitute PORT and BACKEND_URL into the nginx template
# Substitute ONLY our two env vars into the nginx template.
# Passing the explicit list prevents envsubst from expanding nginx's own
# $-variables ($host, $uri, $http_upgrade, $remote_addr, etc.) which would
# silently break the proxy and SPA routing.
envsubst '${PORT} ${BACKEND_URL}' \
  < /etc/nginx/conf.d/default.conf.template \
  > /etc/nginx/conf.d/default.conf

# Validate config before handing off
nginx -t

exec "$@"
