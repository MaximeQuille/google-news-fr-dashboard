#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
STATE = PUBLIC / "state"


def latest_output_dir(root: Path) -> Path:
    candidates = [
        p for p in root.glob("sortie_google_news_fr_ULTRA_*")
        if p.is_dir() and (p / "google_news_fr_ultra.sqlite").exists()
    ]
    if not candidates:
        raise SystemExit("Aucun dossier sortie_google_news_fr_ULTRA_* avec SQLite trouvé.")
    return max(candidates, key=lambda p: p.name)


def copy_required(src: Path, dst: Path) -> None:
    if not src.exists():
        raise SystemExit(f"Fichier manquant: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def main() -> None:
    out_dir = latest_output_dir(ROOT)
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True)
    STATE.mkdir(parents=True)

    html_src = ROOT / "dashboard_google_news.html"
    data_src = ROOT / "dashboard_google_news_data.js"
    if not html_src.exists():
        html_src = out_dir / "dashboard_google_news.html"
    if not data_src.exists():
        data_src = out_dir / "dashboard_google_news_data.js"

    copy_required(html_src, PUBLIC / "index.html")
    copy_required(html_src, PUBLIC / "dashboard_google_news.html")
    copy_required(data_src, PUBLIC / "dashboard_google_news_data.js")
    copy_required(out_dir / "google_news_fr_ultra.sqlite", STATE / "google_news_fr_ultra.sqlite")

    status = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_output_dir": out_dir.name,
        "files": {
            "index": "index.html",
            "dashboard": "dashboard_google_news.html",
            "data": "dashboard_google_news_data.js",
            "sqlite_state": "state/google_news_fr_ultra.sqlite",
        },
    }
    (PUBLIC / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Site préparé dans {PUBLIC}")


if __name__ == "__main__":
    main()
