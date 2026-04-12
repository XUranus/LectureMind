#!/bin/sh
set -e

# Write runtime env-config.js so the React app picks up the correct API URL
# without needing a rebuild. API_PREFIX defaults to /api-proxy (proxied by nginx
# in a typical compose setup) or can be set to an absolute URL.
cat > /usr/share/nginx/html/env-config.js <<EOF
window.__ENV__ = {
  API_PREFIX: "${API_PREFIX:-http://localhost:8000}"
};
EOF

exec nginx -g 'daemon off;'
