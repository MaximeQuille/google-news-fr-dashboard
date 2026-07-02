#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/google-news-fr}"
APP_ROOT="$APP_DIR/app"
VENV="$APP_DIR/venv"

if [ -f "$APP_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$APP_DIR/.env"
  set +a
fi

cd "$APP_ROOT"
"$VENV/bin/python" scripts/send_queued_gmail.py --limit "${ALERT_QUEUE_LIMIT:-200}"
