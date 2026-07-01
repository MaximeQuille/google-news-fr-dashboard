#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote

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


def build_email(alert_filter: dict[str, Any], rows: list[dict[str, Any]]) -> EmailMessage:
    label = alert_filter.get('label') or 'Alerte Google News FR'
    subject = f"{len(rows)} nouvel article{'s' if len(rows) > 1 else ''} - {label}"
    sender = env('SMTP_FROM') or env('SMTP_USERNAME')
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = alert_filter['email']

    lines = [subject, '', 'Articles détectés:']
    html_rows = []
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
          <tr><td style="background:#20231f;color:#f8f6ef;padding:22px"><div style="font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#c9c4b8">Google News FR</div><h1 style="margin:8px 0 0;font-size:24px">{html.escape(subject)}</h1></td></tr>
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


def main() -> None:
    if not smtp_ready():
        print('SMTP non configuré: étape alertes ignorée sans erreur.')
        return
    supa = Supabase()
    filters = supa.get('/alert_filters?select=*&active=eq.true&order=created_at.asc')
    if not filters:
        print('Aucune alerte active.')
        return
    since_values = [f.get('last_checked_at') or f.get('created_at') for f in filters if f.get('last_checked_at') or f.get('created_at')]
    since = min(since_values) if since_values else datetime.now(timezone.utc).isoformat()
    articles = supa.get('/articles?select=uid,published,source,source_domain,media_group,title,summary,link&published=gt.' + quote_value(since) + '&order=published.asc&limit=8000')
    now = datetime.now(timezone.utc).isoformat()
    sent_filters = 0
    for alert_filter in filters:
        keywords = normalize_keywords(alert_filter.get('keywords'))
        if not keywords or not alert_filter.get('email'):
            supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {'last_checked_at': now})
            continue
        start = alert_filter.get('last_checked_at') or alert_filter.get('created_at') or since
        candidates = [a for a in articles if (a.get('published') or '') > start and scope_match(a, alert_filter.get('scope') or 'all') and keyword_match(a, keywords, alert_filter.get('match_mode') or 'any')]
        if candidates:
            uid_list = ','.join(quote_value(a['uid']) for a in candidates if a.get('uid'))
            delivered = set()
            if uid_list:
                delivered_rows = supa.get('/alert_deliveries?select=article_uid&filter_id=eq.' + quote_value(alert_filter['id']) + '&article_uid=in.(' + uid_list + ')')
                delivered = {r['article_uid'] for r in delivered_rows}
            fresh = [a for a in candidates if a.get('uid') not in delivered][:80]
            if fresh:
                send_message(build_email(alert_filter, fresh))
                supa.post('alert_deliveries', [{'filter_id': alert_filter['id'], 'article_uid': a['uid']} for a in fresh if a.get('uid')])
                sent_filters += 1
        supa.patch('alert_filters', 'id=eq.' + quote_value(alert_filter['id']), {'last_checked_at': now})
    print(f'Alertes traitées: {len(filters)}. Emails envoyés: {sent_filters}.')


if __name__ == '__main__':
    main()
