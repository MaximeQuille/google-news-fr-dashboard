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

if [ -z "${GITHUB_TOKEN:-}" ] || [ -z "${GITHUB_REPOSITORY:-}" ]; then
  echo "GITHUB_TOKEN or GITHUB_REPOSITORY missing: skipping GitHub Pages publish."
  exit 0
fi

cd "$APP_ROOT"
"$VENV/bin/python" scripts/prepare_supabase_pages.py

tmp_remote="https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
(
  cd public
  rm -rf .git
  git init
  git checkout -b gh-pages
  git config user.name "google-news-vps"
  git config user.email "google-news-vps@users.noreply.github.com"
  git add .
  git commit -m "Update dashboard $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  git push --force "$tmp_remote" gh-pages
)
