#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from urllib.parse import quote

import requests


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def require(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(f"Variable manquante: {name}")
    return value


def quote_value(value: str) -> str:
    return quote(value, safe="")


class Supabase:
    def __init__(self) -> None:
        key = require("SUPABASE_SERVICE_ROLE_KEY")
        self.url = require("SUPABASE_URL").rstrip("/") + "/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        }

    def get(self, path: str):
        res = requests.get(self.url + path, headers=self.headers, timeout=60)
        res.raise_for_status()
        return res.json()

    def patch(self, table: str, query: str, payload: dict) -> None:
        res = requests.patch(
            f"{self.url}/{table}?{query}",
            headers={**self.headers, "Prefer": "return=minimal"},
            json=payload,
            timeout=60,
        )
        res.raise_for_status()


def send_message(row: dict) -> None:
    msg = EmailMessage()
    msg["Subject"] = row["subject"]
    msg["From"] = env("SMTP_FROM") or env("SMTP_USERNAME")
    msg["To"] = row["email"]
    msg.set_content(row["text_body"])
    msg.add_alternative(row["html_body"], subtype="html")

    host = require("SMTP_HOST")
    port = int(env("SMTP_PORT", "587"))
    username = require("SMTP_USERNAME")
    password = require("SMTP_PASSWORD")
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=60) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(username, password)
            smtp.send_message(msg)


def main(limit: int) -> None:
    supa = Supabase()
    rows = supa.get(
        "/alert_email_outbox?select=*&sent_at=is.null&status=eq.pending&order=created_at.asc&limit="
        + str(limit)
    )
    sent = 0
    for row in rows:
        row_id = quote_value(str(row["id"]))
        try:
            send_message(row)
            sent += 1
            now = datetime.now(timezone.utc).isoformat()
            supa.patch("alert_email_outbox", "id=eq." + row_id, {"sent_at": now, "status": "sent", "error": None})
            if row.get("filter_id"):
                supa.patch("alert_filters", "id=eq." + quote_value(row["filter_id"]), {
                    "last_email_sent_at": now,
                    "last_email_article_count": int(row.get("article_count") or 0),
                    "last_email_kind": row.get("email_kind"),
                })
        except Exception as exc:
            supa.patch("alert_email_outbox", "id=eq." + row_id, {"status": "error", "error": str(exc)[:500]})
            raise
    print(f"Emails Gmail envoyés depuis la file: {sent}/{len(rows)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    main(args.limit)
