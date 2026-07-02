#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/google-news-fr}"
APP_ROOT="$APP_DIR/app"
VENV="$APP_DIR/venv"
LOG_DIR="${LOG_DIR:-/var/log/google-news-fr}"
DB_PATH="${DB_PATH:-$APP_ROOT/sortie_google_news_fr_ULTRA_CLOUD/google_news_fr_ultra.sqlite}"
LOCK_FILE="$APP_DIR/state/hourly.lock"
HEALTH_FILE="$APP_DIR/state/health.json"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$LOG_DIR/hourly-$RUN_ID.log"

mkdir -p "$LOG_DIR" "$(dirname "$DB_PATH")" "$APP_DIR/state"
exec > >(tee -a "$LOG_FILE") 2>&1

if [ -f "$APP_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$APP_DIR/.env"
  set +a
fi

finish() {
  local status="$1"
  python3 - "$HEALTH_FILE" "$status" "$LOG_FILE" <<'PY'
import json, sys
from datetime import datetime, timezone
path, status, log_file = sys.argv[1:4]
data = {"last_run_utc": datetime.now(timezone.utc).isoformat(), "status": status, "log_file": log_file}
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
PY
}
trap 'finish failed' ERR

echo "== Google News FR hourly run $RUN_ID =="
echo "App: $APP_ROOT"
echo "DB: $DB_PATH"

(
  flock -n 9 || { echo "Another hourly run is already active."; exit 0; }

  cd "$APP_ROOT"
  git fetch origin "${REPO_BRANCH:-main}"
  git checkout "${REPO_BRANCH:-main}"
  git pull --ff-only origin "${REPO_BRANCH:-main}"

  "$VENV/bin/python" -m pip install -r requirements.txt

  if [ ! -f "$DB_PATH" ]; then
    echo "No local DB found. Pulling current state from Supabase."
    "$VENV/bin/python" scripts/supabase_sync.py pull --db "$DB_PATH"
  fi

  "$VENV/bin/python" google_news_fr_ultra_sqlite.py \
    --days 2 \
    --mode "${COLLECT_MODE:-ultra}" \
    --concurrency "${COLLECT_CONCURRENCY:-35}" \
    --progress-every 500 \
    --repair-last-hours "${COLLECT_REPAIR_LAST_HOURS:-24}" \
    --no-summary-backfill

  "$VENV/bin/python" scripts/supabase_sync.py push --db "$DB_PATH"

  curl -fsS -X POST "${SUPABASE_URL%/}/functions/v1/process-alerts" \
    -H "Content-Type: application/json" \
    -H "apikey: ${SUPABASE_ANON_KEY}" \
    -H "Authorization: Bearer ${SUPABASE_ANON_KEY}" \
    -H "x-alert-cron-secret: ${ALERT_CRON_SECRET}" \
    --data '{"action":"all"}'

  "$APP_ROOT/ops/vps/send_queue.sh"
  "$APP_ROOT/ops/vps/publish_pages.sh"
) 9>"$LOCK_FILE"

finish ok
echo "== Done $RUN_ID =="
