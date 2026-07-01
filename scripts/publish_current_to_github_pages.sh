#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "Usage: scripts/publish_current_to_github_pages.sh owner/repo"
  echo "Exemple: scripts/publish_current_to_github_pages.sh maxime/google-news-fr-dashboard"
  exit 1
fi

REPO="$1"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python scripts/prepare_github_pages.py

cd public
git init
git checkout -B gh-pages
git config user.name "Maxime"
git config user.email "maxime@example.local"
git add .
git commit -m "Initial dashboard publication"
git remote remove origin >/dev/null 2>&1 || true
git remote add origin "https://github.com/${REPO}.git"
git push --force origin gh-pages

echo "Publication initiale envoyée sur la branche gh-pages de ${REPO}."
