#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

TOP_100_MEDIA_DOMAINS = {
    'lemonde.fr','lefigaro.fr','liberation.fr','mediapart.fr','lesechos.fr','latribune.fr','lopinion.fr','la-croix.com','humanite.fr','valeursactuelles.com',
    'marianne.net','lepoint.fr','lexpress.fr','nouvelobs.com','lejdd.fr','parismatch.com','francetvinfo.fr','tf1info.fr','bfmtv.com','cnews.fr',
    'rtl.fr','europe1.fr','franceinter.fr','radiofrance.fr','rfi.fr','france24.com','publicsenat.fr','lcp.fr','20minutes.fr','huffingtonpost.fr',
    'slate.fr','konbini.com','brut.media','numerama.com','01net.com','clubic.com','zdnet.fr','usine-digitale.fr','journaldunet.com','next.ink',
    'capital.fr','challenges.fr','bfmbusiness.bfmtv.com','boursorama.com','investir.lesechos.fr','agefi.fr','courrierinternational.com','ouest-france.fr','sudouest.fr','ladepeche.fr',
    'lavoixdunord.fr','leparisien.fr','actu.fr','dna.fr','estrepublicain.fr','ledauphine.com','leprogres.fr','lamontagne.fr','midilibre.fr','nicematin.com',
    'varmatin.com','corsematin.com','laprovence.com','ouest-france.fr','letelegramme.fr','lanouvellerepublique.fr','republicain-lorrain.fr','bienpublic.com','estrepublicain.fr','lyoncapitale.fr',
    'marsactu.fr','mediacites.fr','rue89strasbourg.com','francebleu.fr','rmc.bfmtv.com','sports.orange.fr','lequipe.fr','sofoot.com','eurosport.fr','automobile-magazine.fr',
    'science-et-vie.com','futura-sciences.com','sciencesetavenir.fr','pourlascience.fr','reporterre.net','vert.eco','novethic.fr','usinenouvelle.com','batiactu.com','lemoniteur.fr',
    'lequotidiendumedecin.fr','egora.fr','santemagazine.fr','doctissimo.fr','telerama.fr','premiere.fr','allocine.fr','lesinrocks.com','madmoizelle.com','elle.fr','geo.fr','caminteresse.fr'
}

NATIONAL_GROUP = 'Presse nationale'
LOCAL_GROUP = 'Presse locale et régionale'
PARIS_TZ = ZoneInfo('Europe/Paris')


def env(name: str, default: str = '') -> str:
    return os.environ.get(name, default).strip()


def require(name: str) -> str:
    value = env(name)
    if not value:
        raise SystemExit(f'Variable manquante: {name}')
    return value


class Supabase:
    def __init__(self) -> None:
        self.url = require('SUPABASE_URL').rstrip('/') + '/rest/v1'
        self.headers = {
            'apikey': require('SUPABASE_SERVICE_ROLE_KEY'),
            'Authorization': 'Bearer ' + require('SUPABASE_SERVICE_ROLE_KEY'),
            'Content-Type': 'application/json',
        }

    def get(self, path: str) -> Any:
        res = requests.get(self.url + path, headers=self.headers, timeout=60)
        res.raise_for_status()
        return res.json()

    def get_all(self, path: str, page_size: int = 1000, max_rows: int = 100000) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        sep = '&' if '?' in path else '?'
        while offset < max_rows:
            batch = self.get(f'{path}{sep}limit={page_size}&offset={offset}')
            if not batch:
                break
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return rows

    def patch(self, table: str, query: str, payload: dict[str, Any]) -> None:
        headers = {**self.headers, 'Prefer': 'return=minimal'}
        res = requests.patch(f'{self.url}/{table}?{query}', headers=headers, data=json.dumps(payload), timeout=60)
        res.raise_for_status()

    def post(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        headers = {**self.headers, 'Prefer': 'resolution=ignore-duplicates,return=minimal'}
        res = requests.post(f'{self.url}/{table}', headers=headers, data=json.dumps(rows), timeout=60)
        res.raise_for_status()


def smtp_ready() -> bool:
    return all(env(k) for k in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD'))


def normalize_keywords(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = [value]
    if not isinstance(value, list):
        return []
    keywords = []
    for item in value:
        word = str(item).strip().lower()
        if word:
            keywords.append(word)
    return keywords[:12]


def article_text(article: dict[str, Any]) -> str:
    return f"{article.get('title') or ''} {article.get('summary') or ''}".lower()


def scope_match(article: dict[str, Any], scope: str) -> bool:
    if scope == 'top_100':
        return (article.get('source_domain') or '').lower() in TOP_100_MEDIA_DOMAINS
    if scope == 'national':
        return article.get('media_group') == NATIONAL_GROUP
    if scope == 'local':
        return article.get('media_group') == LOCAL_GROUP
    return True


def keyword_match(article: dict[str, Any], keywords: list[str], mode: str) -> bool:
    text = article_text(article)
    if mode == 'all':
        return all(k in text for k in keywords)
    return any(k in text for k in keywords)


def fmt_date(value: str | None) -> str:
    if not value:
        return ''
    return value.replace('T', ' ')[:16]


def build_email(
    alert_filter: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    subject: str | None = None,
    intro: str = 'Articles détectés:',
    empty_text: str = 'Aucun article correspondant sur cette période.',
) -> EmailMessage:
    label = alert_filter.get('label') or 'Alerte Google News FR'
    if subject is None:
        subject = f"{len(rows)} nouvel article{'s' if len(rows) > 1 else ''} - {label}"
    sender = env('SMTP_FROM') or env('SMTP_USERNAME')
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = alert_filter['email']

    lines = [subject, '', intro]
    html_rows = []
    if not rows:
        lines.extend(['', empty_text])
        html_rows.append(f"""
          <tr>
            <td style="padding:18px;border-bottom:1px solid #e5e1d8;color:#4b463f;line-height:1.45">{html.escape(empty_text)}</td>
          </tr>""")
    for article in rows:
        title = article.get('title') or 'Sans titre'
        source = article.get('source') or 'Source inconnue'
        published = fmt_date(article.get('published'))
        link = article.get('link') or '#'
        summary = article.get('summary') or ''
        lines.extend(['', f"- {title}", f"  {source} - {published}", f"  {link}"])
        html_rows.append(f"""
          <tr>
            <td style="padding:16px;border-bottom:1px solid #e5e1d8">
              <div style="font-size:12px;color:#6b665c;margin-bottom:6px">{html.escape(source)} · {html.escape(published)}</div>
              <a href="{html.escape(link)}" style="font-size:17px;line-height:1.35;color:#0f766e;font-weight:700;text-decoration:none">{html.escape(title)}</a>
              {f'<p style="margin:8px 0 0;color:#4b463f;line-height:1.45">{html.escape(summary)}</p>' if summary else ''}
            </td>
          </tr>""")
    msg.set_content('\n'.join(lines))
    msg.add_alternative(f"""
    <html><body style="margin:0;background:#f7f6f2;font-family:Arial,sans-serif;color:#171717">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f7f6f2;padding:24px">
        <tr><td align="center"><table role="presentation" width="680" cellspacing="0" cellpadding="0" style="max-width:680px;background:#fff;border:1px solid #dedbd2;border-radius:8px;overflow:hidden">
          <tr><td style="background:#20231f;color:#f8f6ef;padding:22px"><div style="font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#c9c4b8">Google News FR</div><h1 style="margin:8px 0 0;font-size:24px">{html.escape(subject)}</h1><p style="margin:10px 0 0;color:#d9d3c5;line-height:1.45">{html.escape(intro)}</p></td></tr>
          {''.join(html_rows)}
        </table></td></tr>
      </table>
    </body></html>
    """, subtype='html')
    return msg


def send_message(msg: EmailMessage) -> None:
    host = require('SMTP_HOST')
    port = int(env('SMTP_PORT', '587'))
    username = require('SMTP_USERNAME')
    password = require('SMTP_PASSWORD')
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=60) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=60) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(username, password)
            smtp.send_message(msg)


def quote_value(value: str) -> str:
    return quote(value, safe='')


def parse_iso_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None


def parse_article_time(value: str | None) -> datetime | None:
    dt = parse_iso_time(value)
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(PARIS_TZ).replace(tzinfo=None)
    return dt


def checkpoint_to_article_time(value: str | None) -> datetime | None:
    dt = parse_iso_time(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(PARIS_TZ).replace(tzinfo=None)


def article_time_query(value: datetime) -> str:
    return value.replace(tzinfo=None).isoformat(timespec='seconds')


def floor_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def ceil_hour(value: datetime) -> datetime:
    floored = floor_hour(value)
    return floored if value == floored else floored + timedelta(hours=1)


def completed_hour_end(now_dt: datetime) -> datetime:
    return floor_hour(now_dt.astimezone(PARIS_TZ).replace(tzinfo=None))


def hourly_window(alert_filter: dict[str, Any], now_dt: datetime) -> tuple[datetime, datetime] | None:
    end = completed_hour_end(now_dt)
    checkpoint = checkpoint_to_article_time(alert_filter.get('last_checked_at') or alert_filter.get('created_at'))
    if checkpoint is None:
        start = end - timedelta(hours=1)
    elif alert_filter.get('last_email_kind') in {'hourly', 'daily', 'weekly'}:
        start = floor_hour(checkpoint)
    else:
        start = ceil_hour(checkpoint)
    if start >= end:
        return None
    return start, end


def scheduled_window(alert_filter: dict[str, Any], now_dt: datetime) -> tuple[datetime, datetime] | None:
    schedule_type = alert_filter.get('schedule_type') or 'hourly'
    if schedule_type == 'hourly':
        return hourly_window(alert_filter, now_dt)
    local_now = now_dt.astimezone(PARIS_TZ).replace(tzinfo=None)
    hour = int(alert_filter.get('schedule_hour') or 8)
    end = local_now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if schedule_type == 'weekly':
        end = end - timedelta(days=(end.weekday() - int(alert_filter.get('schedule_weekday') or 0)) % 7)
    if local_now < end:
        return None
    last_checked = checkpoint_to_article_time(alert_filter.get('last_schedule_checked_at') or alert_filter.get('last_checked_at') or alert_filter.get('created_at'))
    if last_checked and floor_hour(last_checked) >= end:
        return None
    default_delta = timedelta(days=7 if schedule_type == 'weekly' else 1)
    start = last_checked if last_checked and last_checked < end else end - default_delta
    if start >= end:
        return None
    return start, end


def window_label(start: datetime, end: datetime) -> str:
    if start.date() == end.date():
        return f'{start:%d/%m/%Y %H:%M} - {end:%H:%M}'
    return f'{start:%d/%m/%Y %H:%M} - {end:%d/%m/%Y %H:%M}'


def matching_articles(articles: list[dict[str, Any]], alert_filter: dict[str, Any], keywords: list[str]) -> list[dict[str, Any]]:
    return [
        article for article in articles
        if scope_match(article, alert_filter.get('scope') or 'all')
        and keyword_match(article, keywords, alert_filter.get('match_mode') or 'any')
    ]


def local_period_key(value: datetime, schedule_type: str) -> str:
    local = value.astimezone(PARIS_TZ)
    if schedule_type == 'weekly':
        year, week, _ = local.isocalendar()
        return f'{year}-W{week:02d}'
    return local.strftime('%Y-%m-%d')


def schedule_due(alert_filter: dict[str, Any], now_dt: datetime) -> bool:
    schedule_type = alert_filter.get('schedule_type') or 'hourly'
    if schedule_type == 'hourly':
        return True
    local_now = now_dt.astimezone(PARIS_TZ)
    hour = int(alert_filter.get('schedule_hour') or 8)
    if local_now.hour < hour:
        return False
    if schedule_type == 'weekly' and local_now.weekday() != int(alert_filter.get('schedule_weekday') or 0):
        return False
    last_checked = parse_iso_time(alert_filter.get('last_schedule_checked_at'))
    if last_checked is None:
        return True
    return local_period_key(last_checked, schedule_type) != local_period_key(now_dt, schedule_type)


def schedule_label(alert_filter: dict[str, Any]) -> str:
    schedule_type = alert_filter.get('schedule_type') or 'hourly'
    if schedule_type == 'daily':
        return 'daily'
    if schedule_type == 'weekly':
        return 'weekly'
    return 'hourly'


def mark_schedule_checked(supa: Supabase, alert_filter: dict[str, Any], now: str) -> None:
    try:
        supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {'last_schedule_checked_at': now})
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ''
        if exc.response is not None and exc.response.status_code in {400, 404} and 'last_schedule_checked_at' in body:
            print('Colonne last_schedule_checked_at manquante: lancez le SQL Supabase alertes mis à jour.')
            return
        raise


def update_last_email(supa: Supabase, alert_filter: dict[str, Any], now: str, count: int, kind: str) -> None:
    try:
        supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {
            'last_email_sent_at': now,
            'last_email_article_count': count,
            'last_email_kind': kind,
        })
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ''
        if exc.response is not None and exc.response.status_code in {400, 404} and (
            'last_email_sent_at' in body or 'last_email_article_count' in body or 'last_email_kind' in body
        ):
            print('Colonnes last_email_* manquantes: lancez le SQL Supabase alertes mis à jour.')
            return
        raise


def send_initial_test(supa: Supabase, alert_filter: dict[str, Any], keywords: list[str], now: str) -> bool:
    stats_rows = supa.get('/article_stats?select=last_article')
    last_article = parse_article_time((stats_rows[0] if stats_rows else {}).get('last_article'))
    if last_article is None:
        supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {'first_test_sent_at': now, 'last_checked_at': now})
        return False
    window_start = last_article - timedelta(hours=1)
    test_articles = supa.get(
        '/articles?select=uid,published,source,source_domain,media_group,title,summary,link&published=gt.'
        + quote_value(article_time_query(window_start))
        + '&published=lte.'
        + quote_value(article_time_query(last_article))
        + '&order=published.desc&limit=8000'
    )
    rows = matching_articles(test_articles, alert_filter, keywords)[:80]
    label = alert_filter.get('label') or 'Alerte Google News FR'
    send_message(build_email(
        alert_filter,
        rows,
        subject=f'Test filtre actif - {label}',
        intro='Mail de validation: voici les articles qui auraient correspondu sur la dernière heure disponible de la base.',
        empty_text='Le filtre est actif, mais aucun article ne correspondait sur la dernière heure disponible.',
    ))
    supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {'first_test_sent_at': now, 'last_checked_at': now})
    update_last_email(supa, alert_filter, now, len(rows), 'test')
    return True


def fetch_active_filter_for_request(supa: Supabase, request: dict[str, Any]) -> dict[str, Any] | None:
    rows = supa.get(
        '/alert_filters?select=*&active=eq.true&id=eq.' + quote_value(str(request['filter_id']))
        + '&limit=1'
    )
    return rows[0] if rows else None


def process_test_requests(supa: Supabase, now: str) -> int:
    try:
        requests_rows = supa.get('/alert_test_requests?select=id,filter_id,manage_token&processed_at=is.null&order=created_at.asc&limit=50')
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ''
        if exc.response is not None and exc.response.status_code in {404, 400} and ('alert_test_requests' in body or '42P01' in body):
            print('Table alert_test_requests manquante: lancez le SQL Supabase alertes mis à jour.')
            return 0
        raise
    sent = 0
    for request_row in requests_rows:
        request_id = quote_value(str(request_row['id']))
        try:
            alert_filter = fetch_active_filter_for_request(supa, request_row)
            if not alert_filter:
                supa.patch('alert_test_requests', 'id=eq.' + request_id, {'processed_at': now, 'status': 'not_found'})
                continue
            if 'first_test_sent_at' not in alert_filter:
                supa.patch('alert_test_requests', 'id=eq.' + request_id, {'processed_at': now, 'status': 'schema_missing', 'error': 'first_test_sent_at missing'})
                continue
            keywords = normalize_keywords(alert_filter.get('keywords'))
            if not keywords or not alert_filter.get('email'):
                supa.patch('alert_test_requests', 'id=eq.' + request_id, {'processed_at': now, 'status': 'invalid_filter'})
                continue
            if send_initial_test(supa, alert_filter, keywords, now):
                sent += 1
            supa.patch('alert_test_requests', 'id=eq.' + request_id, {'processed_at': now, 'status': 'sent'})
        except Exception as exc:
            supa.patch('alert_test_requests', 'id=eq.' + request_id, {'processed_at': now, 'status': 'error', 'error': str(exc)[:500]})
            raise
    return sent


def main(test_requests_only: bool = False) -> None:
    if not smtp_ready():
        print('SMTP non configuré: étape alertes ignorée sans erreur.')
        return
    supa = Supabase()
    try:
        filters = supa.get('/alert_filters?select=*&active=eq.true&order=created_at.asc')
    except requests.HTTPError as exc:
        body = exc.response.text if exc.response is not None else ''
        if exc.response is not None and exc.response.status_code in {404, 400} and ('alert_filters' in body or '42P01' in body):
            print('Tables alertes Supabase non créées: étape alertes ignorée sans erreur.')
            return
        raise
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    current_article_time = now_dt.astimezone(PARIS_TZ).replace(tzinfo=None)
    requested_tests = process_test_requests(supa, now)
    if test_requests_only:
        print(f'Demandes de test traitées. Tests envoyés: {requested_tests}.')
        return
    if requested_tests:
        filters = supa.get('/alert_filters?select=*&active=eq.true&order=created_at.asc')
    if not filters:
        print('Aucune alerte active.')
        return
    if any('first_test_sent_at' not in f for f in filters):
        print('Colonne first_test_sent_at manquante: lancez le SQL Supabase alertes mis à jour.')
        return
    windows = {
        f['id']: scheduled_window(f, now_dt)
        for f in filters
        if f.get('first_test_sent_at') and schedule_due(f, now_dt)
    }
    due_windows = [w for w in windows.values() if w is not None]
    since = min((w[0] for w in due_windows), default=current_article_time - timedelta(hours=1))
    until = max((w[1] for w in due_windows), default=current_article_time)
    articles = []
    if due_windows:
        articles = supa.get_all(
            '/articles?select=uid,published,source,source_domain,media_group,title,summary,link&published=gt.'
            + quote_value(article_time_query(since))
            + '&published=lte.'
            + quote_value(article_time_query(until))
            + '&order=published.asc'
        )
    sent_filters = 0
    sent_tests = requested_tests
    for alert_filter in filters:
        keywords = normalize_keywords(alert_filter.get('keywords'))
        if not keywords or not alert_filter.get('email'):
            supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {'last_checked_at': now})
            continue
        if not alert_filter.get('first_test_sent_at'):
            if send_initial_test(supa, alert_filter, keywords, now):
                sent_tests += 1
            continue
        window = windows.get(alert_filter['id'])
        if window is None:
            continue
        start, end = window
        candidates = [
            a for a in articles
            if (published_at := parse_article_time(a.get('published'))) is not None
            and start < published_at <= end
        ]
        candidates = matching_articles(candidates, alert_filter, keywords)
        if candidates:
            delivered_rows = supa.get('/alert_deliveries?select=article_uid&filter_id=eq.' + quote_value(alert_filter['id']) + '&limit=20000')
            delivered = {r['article_uid'] for r in delivered_rows}
            fresh = [a for a in candidates if a.get('uid') not in delivered][:80]
            if fresh:
                kind = schedule_label(alert_filter)
                label = window_label(start, end)
                subject_label = alert_filter.get('label') or 'Alerte Google News FR'
                send_message(build_email(
                    alert_filter,
                    fresh,
                    subject=f"{len(fresh)} nouvel article{'s' if len(fresh) > 1 else ''} - {subject_label} - {label}",
                    intro=f'Articles détectés sur la fenêtre complète: {label}',
                ))
                supa.post('alert_deliveries', [{'filter_id': alert_filter['id'], 'article_uid': a['uid']} for a in fresh if a.get('uid')])
                update_last_email(supa, alert_filter, now, len(fresh), kind)
                sent_filters += 1
        supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {'last_checked_at': end.replace(tzinfo=PARIS_TZ).astimezone(timezone.utc).isoformat()})
        if (alert_filter.get('schedule_type') or 'hourly') != 'hourly':
            mark_schedule_checked(supa, alert_filter, now)
    print(f'Alertes traitées: {len(filters)}. Tests envoyés: {sent_tests}. Emails envoyés: {sent_filters}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--test-requests-only', action='store_true')
    args = parser.parse_args()
    main(test_requests_only=args.test_requests_only)
