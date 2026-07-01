#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

DASHBOARD = r'''<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google News FR - Live Dashboard</title>
  <script src="supabase_config.js"></script>
  <style>
    :root { --bg:#f6f5f1; --surface:#fff; --ink:#171717; --muted:#69655d; --line:#dedbd2; --accent:#0f766e; --focus:rgba(15,118,110,.18); }
    *{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;letter-spacing:0}
    button,input,select{font:inherit}.app{min-height:100vh;display:grid;grid-template-columns:304px minmax(0,1fr)}
    .side{position:sticky;top:0;height:100vh;padding:28px 22px;background:#20231f;color:#f8f6ef;border-right:1px solid rgba(255,255,255,.08);display:flex;flex-direction:column;gap:24px}
    .brand{display:grid;gap:8px}.brand small{color:#b9b5a9;font-size:12px;text-transform:uppercase;letter-spacing:.14em}h1{margin:0;font-size:25px;line-height:1.08;font-weight:760}.updated{color:#c9c4b8;font-size:13px;line-height:1.45}
    .sideStats{display:grid;gap:10px}.stat{border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.055);border-radius:8px;padding:14px}.stat .num{font-size:28px;line-height:1;font-weight:780}.stat .label{margin-top:6px;color:#c9c4b8;font-size:12px}.sideFoot{margin-top:auto;color:#aaa396;font-size:12px;line-height:1.5}
    main{padding:26px 30px 44px;min-width:0}.topbar{display:grid;grid-template-columns:minmax(240px,1fr) 210px 220px 170px;gap:10px;align-items:center;margin-bottom:16px}.searchBox,.filterBox{position:relative}.filterIcon{position:absolute;left:12px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:13px;pointer-events:none}
    .searchBox input,select{width:100%;height:48px;border:1px solid var(--line);border-radius:8px;background:var(--surface);outline:none}.searchBox input{padding:0 44px 0 16px}.searchBox input:focus,select:focus{border-color:var(--accent);box-shadow:0 0 0 4px var(--focus)}.filterBox select{padding-left:34px}.kbd{position:absolute;right:12px;top:50%;transform:translateY(-50%);color:var(--muted);font-size:12px;border:1px solid var(--line);border-radius:6px;padding:2px 6px;background:#faf9f5}
    .summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:16px}.metric{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:16px;min-width:0}.metric b{display:block;font-size:22px;line-height:1.1}.metric span{display:block;margin-top:6px;color:var(--muted);font-size:12px}
    .workspace{display:grid;grid-template-columns:minmax(0,1fr) 280px;gap:16px;align-items:start}.panel,.rail{background:var(--surface);border:1px solid var(--line);border-radius:8px}.panelHead{min-height:54px;padding:14px 16px;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:12px}.panelHead h2{margin:0;font-size:15px;font-weight:720}.panelHead p{margin:0;color:var(--muted);font-size:13px}.list{display:grid}
    .article{display:grid;grid-template-columns:118px minmax(0,1fr);gap:16px;padding:16px;border-bottom:1px solid var(--line)}.article:last-child{border-bottom:0}.date{color:var(--muted);font-size:12px;line-height:1.45;white-space:nowrap}.title{margin:0 0 8px;font-size:17px;line-height:1.3;font-weight:720}.title a{color:var(--ink);text-decoration:none}.title a:hover{color:var(--accent)}.dek{margin:0 0 10px;color:#4d4942;font-size:14px;line-height:1.45}.meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center;color:var(--muted);font-size:12px}.pill{display:inline-flex;min-height:24px;align-items:center;border:1px solid var(--line);border-radius:999px;padding:3px 8px;color:#4c4942;background:#fbfaf6;overflow-wrap:anywhere}.empty{padding:42px 16px;text-align:center;color:var(--muted)}
    .pager{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 16px;border-top:1px solid var(--line)}.pager button{border:1px solid var(--line);background:var(--surface);border-radius:8px;height:38px;padding:0 14px;cursor:pointer}.pager button:hover:not(:disabled){border-color:var(--accent);color:var(--accent)}.pager button:disabled{opacity:.45;cursor:default}.rail{padding:16px;display:grid;gap:18px}.rail h3{margin:0 0 10px;font-size:13px;text-transform:uppercase;color:var(--muted);letter-spacing:.08em}.barRow{display:grid;gap:6px;margin:10px 0}.barLabel{display:flex;justify-content:space-between;gap:10px;font-size:12px;color:#3d3a35}.bar{height:8px;border-radius:999px;background:#f0efea;overflow:hidden}.bar span{display:block;height:100%;background:var(--accent);border-radius:inherit}.chipList{display:flex;flex-wrap:wrap;gap:7px}.chip{border:1px solid var(--line);background:#fbfaf6;border-radius:999px;padding:6px 9px;font-size:12px;color:#3d3a35;cursor:pointer}.chip:hover{border-color:var(--accent);color:var(--accent)}
    @media(max-width:1040px){.app{grid-template-columns:1fr}.side{position:relative;height:auto}.workspace{grid-template-columns:1fr}}@media(max-width:760px){main{padding:16px}.topbar,.summary{grid-template-columns:1fr}.article{grid-template-columns:1fr;gap:8px}.date{white-space:normal}}
  </style>
</head>
<body>
<div class="app"><aside class="side"><div class="brand"><small>Veille Google News</small><h1>France Ultra Recall</h1><div class="updated" id="updatedAt">Base Supabase live</div></div><div class="sideStats"><div class="stat"><div class="num" id="statArticles">-</div><div class="label">articles uniques</div></div><div class="stat"><div class="num" id="statSources">-</div><div class="label">sources distinctes</div></div><div class="stat"><div class="num" id="statMatches">-</div><div class="label">résultats filtrés</div></div></div><div class="sideFoot">Dashboard connecté à Supabase. La collecte tourne chaque heure via GitHub Actions.</div></aside>
<main><div class="topbar"><div class="searchBox"><input id="searchInput" type="search" placeholder="Rechercher un mot clé, une source, un sujet..." autocomplete="off" autofocus><span class="kbd">⌘K</span></div><div class="filterBox"><span class="filterIcon">◇</span><select id="sourceFilter"><option value="">Tous les médias</option></select></div><div class="filterBox"><span class="filterIcon">◇</span><select id="groupFilter"><option value="">Tous les groupes</option></select></div><select id="sortMode"><option value="newest">Plus récents</option><option value="oldest">Plus anciens</option><option value="source">Source A-Z</option></select></div>
<section class="summary"><div class="metric"><b id="metricPeriod">-</b><span>période couverte</span></div><div class="metric"><b id="metricLast">-</b><span>dernier article</span></div><div class="metric"><b id="metricDb">Supabase</b><span>base active</span></div><div class="metric"><b id="metricPage">20</b><span>articles par page</span></div></section>
<div class="workspace"><section class="panel"><div class="panelHead"><div><h2>Articles</h2><p id="resultLine">Chargement...</p></div></div><div class="list" id="articleList"><div class="empty">Chargement des articles...</div></div><div class="pager"><button id="prevBtn">Précédent</button><span id="pageInfo">Page 1</span><button id="nextBtn">Suivant</button></div></section><aside class="rail"><section><h3>Top sources</h3><div id="topSources"></div></section><section><h3>Mots rapides</h3><div class="chipList" id="quickTerms"></div></section></aside></div></main></div>
<script>
const CFG = window.SUPABASE_CONFIG || {};
const API = (CFG.url || '').replace(/\/$/, '') + '/rest/v1';
const KEY = CFG.anonKey || '';
const PAGE_SIZE = 20;
const fmt = new Intl.NumberFormat('fr-FR');
let page = 1, total = 0;
const $ = id => document.getElementById(id);
const esc = v => String(v || '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
function compactDate(value){ if(!value)return '-'; const [d,t='']=String(value).replace('T',' ').split(' '); const bits=d.split('-'); if(bits.length!==3)return value; return `${bits[2]}/${bits[1]}/${bits[0]} ${t.slice(0,5)}`.trim(); }
async function supa(path, opts={}){ const res = await fetch(API + path, { ...opts, headers:{ apikey:KEY, Authorization:'Bearer '+KEY, ...(opts.headers||{}) }}); if(!res.ok) throw new Error(await res.text()); return res; }
function applyParams(base){ const params = new URLSearchParams(); params.set('select', base.select); if(base.order) params.set('order', base.order); const source=$('sourceFilter').value, group=$('groupFilter').value, q=$('searchInput').value.trim(); if(source) params.set('source','eq.'+source); if(group) params.set('media_group','eq.'+group); if(q){ const pat='*'+q.replace(/[,*()]/g,' ')+'*'; params.set('or', `(title.ilike.${pat},summary.ilike.${pat},source.ilike.${pat},source_domain.ilike.${pat},media_group.ilike.${pat})`); } return params.toString(); }
async function loadStats(){ const r=await supa('/article_stats?select=*'); const stats=(await r.json())[0]||{}; $('statArticles').textContent=fmt.format(stats.total_articles||0); $('statSources').textContent=fmt.format(stats.total_sources||0); $('metricPeriod').textContent=stats.first_article&&stats.last_article?`${compactDate(stats.first_article).slice(0,10)} → ${compactDate(stats.last_article).slice(0,10)}`:'-'; $('metricLast').textContent=compactDate(stats.last_article); $('updatedAt').textContent='Mis à jour automatiquement'; }
async function loadFilters(){ const [srcRes, grpRes, topRes] = await Promise.all([supa('/media_sources?select=source&order=source.asc'), supa('/media_groups?select=media_group,count'), supa('/top_sources?select=source,count')]); const sources=await srcRes.json(); $('sourceFilter').innerHTML='<option value="">Tous les médias</option>'+sources.map(s=>`<option value="${esc(s.source)}">${esc(s.source)}</option>`).join(''); const order=['Presse nationale','Presse locale et régionale','TV / radio','Économie','Tech / numérique','Médias spécialisés','Outre-mer','Portails / agrégateurs','Autres médias']; const groups=(await grpRes.json()).sort((a,b)=>order.indexOf(a.media_group)-order.indexOf(b.media_group)); $('groupFilter').innerHTML='<option value="">Tous les groupes</option>'+groups.map(g=>`<option value="${esc(g.media_group)}">${esc(g.media_group)} (${fmt.format(g.count)})</option>`).join(''); const top=await topRes.json(); const max=top.length?top[0].count:1; $('topSources').innerHTML=top.slice(0,10).map(r=>`<div class="barRow"><div class="barLabel"><span>${esc(r.source)}</span><b>${fmt.format(r.count)}</b></div><div class="bar"><span style="width:${Math.max(4,Math.round((r.count/max)*100))}%"></span></div></div>`).join(''); }
async function loadArticles(){ const sort=$('sortMode').value; const order=sort==='oldest'?'published.asc':sort==='source'?'source.asc,published.desc':'published.desc'; const qs=applyParams({ select:'published,date,hour,source,source_domain,media_group,title,summary,link,occurrences_in_feeds,first_query_kind,first_query_label', order }); const from=(page-1)*PAGE_SIZE, to=from+PAGE_SIZE-1; const r=await supa('/articles?'+qs, { headers:{ Prefer:'count=exact', Range:`${from}-${to}` }}); const range=r.headers.get('content-range')||'0-0/0'; total=Number(range.split('/')[1]||0); const rows=await r.json(); $('statMatches').textContent=fmt.format(total); $('resultLine').textContent=`${fmt.format(total)} résultat${total>1?'s':''}`; render(rows); }
function render(rows){ if(!rows.length){ $('articleList').innerHTML='<div class="empty">Aucun article ne correspond à cette recherche.</div>'; } else { $('articleList').innerHTML=rows.map(a=>`<article class="article"><div class="date">${compactDate(a.published)}<br>${esc(a.hour||'')}</div><div><h3 class="title"><a href="${esc(a.link)}" target="_blank" rel="noopener noreferrer">${esc(a.title)}</a></h3>${a.summary?`<p class="dek">${esc(a.summary)}</p>`:''}<div class="meta"><span class="pill">${esc(a.source||'Source inconnue')}</span>${a.source_domain?`<span>${esc(a.source_domain)}</span>`:''}<span>${esc(a.media_group||'Autres médias')}</span><span>${esc(a.first_query_kind||'')}</span><span>${fmt.format(a.occurrences_in_feeds||1)} apparition${Number(a.occurrences_in_feeds||1)>1?'s':''}</span></div></div></article>`).join(''); } const maxPage=Math.max(1,Math.ceil(total/PAGE_SIZE)); page=Math.min(page,maxPage); $('pageInfo').textContent=`Page ${page} / ${maxPage}`; $('prevBtn').disabled=page<=1; $('nextBtn').disabled=page>=maxPage; }
function refresh(){ page=1; loadArticles().catch(e=>{$('articleList').innerHTML='<div class="empty">Erreur Supabase: '+esc(e.message)+'</div>';}); }
$('searchInput').addEventListener('input',()=>{ clearTimeout(window._t); window._t=setTimeout(refresh,350); }); $('sourceFilter').addEventListener('change',refresh); $('groupFilter').addEventListener('change',refresh); $('sortMode').addEventListener('change',refresh); $('prevBtn').addEventListener('click',()=>{ if(page>1){page--;loadArticles();}}); $('nextBtn').addEventListener('click',()=>{ if(page<Math.ceil(total/PAGE_SIZE)){page++;loadArticles();}}); window.addEventListener('keydown',e=>{ if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('searchInput').focus();}}); const quick=['politique','justice','incendie','accident','santé','économie','agriculture','cyberattaque','météo','école']; $('quickTerms').innerHTML=quick.map(t=>`<button class="chip" data-term="${esc(t)}">${esc(t)}</button>`).join(''); document.querySelectorAll('.chip').forEach(b=>b.addEventListener('click',()=>{$('searchInput').value=b.dataset.term;refresh();}));
Promise.all([loadStats(), loadFilters()]).then(loadArticles).catch(e=>{$('articleList').innerHTML='<div class="empty">Configuration Supabase manquante ou invalide.</div>'; console.error(e);});
</script>
</body>
</html>
'''


def require_env(name: str) -> str:
    value = os.environ.get(name, '').strip()
    if not value:
        raise SystemExit(f"Variable manquante: {name}")
    return value


def main() -> None:
    if PUBLIC.exists():
        shutil.rmtree(PUBLIC)
    PUBLIC.mkdir(parents=True)
    supabase_url = require_env('SUPABASE_URL').rstrip('/')
    anon_key = require_env('SUPABASE_ANON_KEY')
    (PUBLIC / 'index.html').write_text(DASHBOARD, encoding='utf-8')
    (PUBLIC / 'dashboard_google_news.html').write_text(DASHBOARD, encoding='utf-8')
    config = 'window.SUPABASE_CONFIG = ' + json.dumps({'url': supabase_url, 'anonKey': anon_key}, ensure_ascii=False) + ';\n'
    (PUBLIC / 'supabase_config.js').write_text(config, encoding='utf-8')
    (PUBLIC / 'status.json').write_text(json.dumps({'generated_at_utc': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'backend': 'supabase'}, indent=2), encoding='utf-8')
    (PUBLIC / '.nojekyll').write_text('', encoding='utf-8')
    print(f"Supabase site prepared in {PUBLIC}")


if __name__ == '__main__':
    main()
