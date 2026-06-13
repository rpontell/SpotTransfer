#!/bin/sh
set -eu

if [ -z "${FRONTEND_URL:-}" ] && [ -n "${FLY_APP_NAME:-}" ]; then
    export FRONTEND_URL="https://${FLY_APP_NAME}.fly.dev"
fi

exec gunicorn \
    -w "${WEB_CONCURRENCY:-1}" \
    --timeout "${GUNICORN_TIMEOUT:-600}" \
    --graceful-timeout 30 \
    -b 127.0.0.1:5000 \
    main:app
