#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import google_news_fr_ultra_sqlite as app  # noqa: E402

ARTICLE_COLUMNS = [
    "uid", "published", "date", "hour", "source", "source_domain", "title", "summary",
    "canonical_title", "link", "first_query_kind", "first_query_label", "first_query_day",
    "all_query_labels", "occurrences_in_feeds", "created_at",
]
ATTEMPT_COLUMNS = [
    "id", "wave", "kind", "label", "base_query", "day", "date_from", "date_to", "status",
    "raw_entries", "kept_before_dedup", "error", "url", "query", "finished_at",
]


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Variable manquante: {name}")
    return value.rstrip("/")


def headers(service_key: str, prefer: str | None = None) -> dict[str, str]:
    out = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        out["Prefer"] = prefer
    return out


def request_json(method: str, url: str, service_key: str, **kwargs):
    last_error = ""
    extra_headers = kwargs.pop("headers", {})
    for attempt in range(4):
        resp = requests.request(method, url, headers={**headers(service_key), **extra_headers}, timeout=120, **kwargs)
        if resp.status_code < 400:
            if resp.text:
                return resp.json()
            return None
        last_error = f"Supabase error {resp.status_code}: {resp.text[:1000]}"
        if resp.status_code not in {500, 502, 503, 504}:
            break
        time.sleep(2 * (attempt + 1))
    raise SystemExit(last_error)


def paged_get(base_url: str, service_key: str, table: str, select: str, order: str | None = None, page_size: int = 1000):
    offset = 0
    while True:
        params = [f"select={select}", f"limit={page_size}", f"offset={offset}"]
        if order:
            params.append(f"order={order}")
        url = f"{base_url}/rest/v1/{table}?" + "&".join(params)
        rows = request_json("GET", url, service_key)
        if not rows:
            break
        yield from rows
        if len(rows) < page_size:
            break
        offset += page_size


def ensure_parent(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return app.init_db(db_path)


def pull(db_path: Path):
    supabase_url = env("SUPABASE_URL")
    service_key = env("SUPABASE_SERVICE_ROLE_KEY")
    conn = ensure_parent(db_path)
    conn.execute("DELETE FROM articles")
    conn.execute("DELETE FROM attempts")
    conn.execute("DELETE FROM query_plan")
    conn.commit()

    article_sql = f"""
        INSERT OR REPLACE INTO articles({','.join(ARTICLE_COLUMNS)})
        VALUES({','.join('?' for _ in ARTICLE_COLUMNS)})
    """
    count = 0
    batch = []
    select = ",".join(ARTICLE_COLUMNS)
    for row in paged_get(supabase_url, service_key, "articles", select, order="published.desc"):
        batch.append(tuple(row.get(col) for col in ARTICLE_COLUMNS))
        if len(batch) >= 1000:
            conn.executemany(article_sql, batch)
            conn.commit()
            count += len(batch)
            batch.clear()
    if batch:
        conn.executemany(article_sql, batch)
        conn.commit()
        count += len(batch)

    attempt_sql = f"""
        INSERT OR REPLACE INTO attempts({','.join(ATTEMPT_COLUMNS)})
        VALUES({','.join('?' for _ in ATTEMPT_COLUMNS)})
    """
    attempts = 0
    batch = []
    select = ",".join(ATTEMPT_COLUMNS)
    for row in paged_get(supabase_url, service_key, "attempts", select, order="id.asc"):
        batch.append(tuple(row.get(col) for col in ATTEMPT_COLUMNS))
        if len(batch) >= 1000:
            conn.executemany(attempt_sql, batch)
            conn.commit()
            attempts += len(batch)
            batch.clear()
    if batch:
        conn.executemany(attempt_sql, batch)
        conn.commit()
        attempts += len(batch)

    conn.close()
    print(f"Pulled {count} articles and {attempts} attempts into {db_path}")


def chunks(rows: list[dict], size: int = 500):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


def clean_value(value):
    return "" if value is None else value


def push_articles(conn: sqlite3.Connection, supabase_url: str, service_key: str):
    cols = ARTICLE_COLUMNS
    rows_iter = conn.execute(f"SELECT {','.join(cols)} FROM articles ORDER BY published DESC")
    total = 0
    batch = []
    url = f"{supabase_url}/rest/v1/articles?on_conflict=uid"
    for row in rows_iter:
        item = {col: clean_value(row[idx]) for idx, col in enumerate(cols)}
        item["media_group"] = app.classify_media_group(item.get("source", ""), item.get("source_domain", ""))
        batch.append(item)
        if len(batch) >= 250:
            request_json("POST", url, service_key, data=json.dumps(batch), headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
            total += len(batch)
            batch.clear()
            print(f"Pushed articles: {total}")
    if batch:
        request_json("POST", url, service_key, data=json.dumps(batch), headers={"Prefer": "resolution=ignore-duplicates,return=minimal"})
        total += len(batch)
    print(f"Pushed articles total: {total}")


def push_attempts(conn: sqlite3.Connection, supabase_url: str, service_key: str):
    cols = [c for c in ATTEMPT_COLUMNS if c != "id"]
    rows = [
        {col: clean_value(value) for col, value in zip(cols, row)}
        for row in conn.execute(f"SELECT {','.join(cols)} FROM attempts ORDER BY id ASC")
    ]
    if not rows:
        print("No attempts to push")
        return
    request_json("DELETE", f"{supabase_url}/rest/v1/attempts?id=not.is.null", service_key, headers={"Prefer": "return=minimal"})
    total = 0
    url = f"{supabase_url}/rest/v1/attempts"
    for batch in chunks(rows, 1000):
        request_json("POST", url, service_key, data=json.dumps(batch), headers={"Prefer": "return=minimal"})
        total += len(batch)
    print(f"Replaced attempts total: {total}")


def push(db_path: Path):
    supabase_url = env("SUPABASE_URL")
    service_key = env("SUPABASE_SERVICE_ROLE_KEY")
    conn = app.init_db(db_path)
    push_articles(conn, supabase_url, service_key)
    push_attempts(conn, supabase_url, service_key)
    conn.close()


def stats():
    supabase_url = env("SUPABASE_URL")
    service_key = env("SUPABASE_SERVICE_ROLE_KEY")
    rows = request_json("GET", f"{supabase_url}/rest/v1/article_stats?select=total_articles,total_sources,first_article,last_article", service_key)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Sync local SQLite with Supabase")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_pull = sub.add_parser("pull")
    p_pull.add_argument("--db", required=True)
    p_push = sub.add_parser("push")
    p_push.add_argument("--db", required=True)
    sub.add_parser("stats")
    args = parser.parse_args()
    if args.cmd == "pull":
        pull(Path(args.db))
    elif args.cmd == "push":
        push(Path(args.db))
    elif args.cmd == "stats":
        stats()


if __name__ == "__main__":
    main()
