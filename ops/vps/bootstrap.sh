#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/google-news-fr}"
APP_USER="${APP_USER:-google-news}"
REPO_URL="${REPO_URL:-https://github.com/MaximeQuille/google-news-fr-dashboard.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash ops/vps/bootstrap.sh"
  exit 1
fi

apt-get update
apt-get install -y git python3 python3-venv python3-pip curl ca-certificates rsync jq

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

mkdir -p "$APP_DIR" "$APP_DIR/state" /var/log/google-news-fr /etc/google-news-fr
chown -R "$APP_USER:$APP_USER" "$APP_DIR" /var/log/google-news-fr

if [ ! -d "$APP_DIR/app/.git" ]; then
  sudo -u "$APP_USER" git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR/app"
else
  sudo -u "$APP_USER" git -C "$APP_DIR/app" fetch origin "$REPO_BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR/app" checkout "$REPO_BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR/app" pull --ff-only origin "$REPO_BRANCH"
fi

sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" -m pip install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/app/requirements.txt"

if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/app/ops/env.vps.example" "$APP_DIR/.env"
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "Created $APP_DIR/.env. Fill it before enabling timers."
fi

cp "$APP_DIR/app/ops/systemd/"*.service /etc/systemd/system/
cp "$APP_DIR/app/ops/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload

echo "Bootstrap complete."
echo "Next:"
echo "  1. Fill $APP_DIR/.env"
echo "  2. sudo systemctl enable --now google-news-collect.timer google-news-email-queue.timer"
echo "  3. sudo -u $APP_USER $APP_DIR/app/ops/vps/run_hourly.sh"
