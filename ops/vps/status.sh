#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/google-news-fr}"

echo "== timers =="
systemctl list-timers 'google-news-*' --no-pager || true
echo
echo "== collect service =="
systemctl status google-news-collect.service --no-pager || true
echo
echo "== email queue service =="
systemctl status google-news-email-queue.service --no-pager || true
echo
echo "== health =="
cat "$APP_DIR/state/health.json" 2>/dev/null || true
echo
echo "== last logs =="
ls -lt /var/log/google-news-fr | head -10 || true
