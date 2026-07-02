type Json = Record<string, unknown>;

type AlertFilter = {
  id: string;
  created_at?: string | null;
  email: string;
  label?: string | null;
  keywords?: unknown;
  match_mode?: string | null;
  scope?: string | null;
  active?: boolean;
  last_checked_at?: string | null;
  first_test_sent_at?: string | null;
  schedule_type?: string | null;
  schedule_hour?: number | null;
  schedule_weekday?: number | null;
  last_schedule_checked_at?: string | null;
  last_email_kind?: string | null;
};

type Article = {
  uid?: string | null;
  published?: string | null;
  source?: string | null;
  source_domain?: string | null;
  media_group?: string | null;
  title?: string | null;
  summary?: string | null;
  canonical_title?: string | null;
  first_query_kind?: string | null;
  first_query_label?: string | null;
  first_query_day?: string | null;
  all_query_labels?: string | null;
  link?: string | null;
};

const TZ = "Europe/Paris";
const NATIONAL_GROUP = "Presse nationale";
const LOCAL_GROUP = "Presse locale et régionale";
const TOP_100_MEDIA_DOMAINS = new Set([
  "lemonde.fr","lefigaro.fr","liberation.fr","mediapart.fr","lesechos.fr","latribune.fr","lopinion.fr","la-croix.com","humanite.fr","valeursactuelles.com",
  "marianne.net","lepoint.fr","lexpress.fr","nouvelobs.com","lejdd.fr","parismatch.com","francetvinfo.fr","tf1info.fr","bfmtv.com","cnews.fr",
  "rtl.fr","europe1.fr","franceinter.fr","radiofrance.fr","rfi.fr","france24.com","publicsenat.fr","lcp.fr","20minutes.fr","huffingtonpost.fr",
  "slate.fr","konbini.com","brut.media","numerama.com","01net.com","clubic.com","zdnet.fr","usine-digitale.fr","journaldunet.com","next.ink",
  "capital.fr","challenges.fr","bfmbusiness.bfmtv.com","boursorama.com","investir.lesechos.fr","agefi.fr","courrierinternational.com","ouest-france.fr","sudouest.fr","ladepeche.fr",
  "lavoixdunord.fr","leparisien.fr","actu.fr","dna.fr","estrepublicain.fr","ledauphine.com","leprogres.fr","lamontagne.fr","midilibre.fr","nicematin.com",
  "varmatin.com","corsematin.com","laprovence.com","letelegramme.fr","lanouvellerepublique.fr","republicain-lorrain.fr","bienpublic.com","lyoncapitale.fr",
  "marsactu.fr","mediacites.fr","rue89strasbourg.com","francebleu.fr","rmc.bfmtv.com","sports.orange.fr","lequipe.fr","sofoot.com","eurosport.fr","automobile-magazine.fr",
  "science-et-vie.com","futura-sciences.com","sciencesetavenir.fr","pourlascience.fr","reporterre.net","vert.eco","novethic.fr","usinenouvelle.com","batiactu.com","lemoniteur.fr",
  "lequotidiendumedecin.fr","egora.fr","santemagazine.fr","doctissimo.fr","telerama.fr","premiere.fr","allocine.fr","lesinrocks.com","madmoizelle.com","elle.fr","geo.fr","caminteresse.fr"
]);

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-alert-cron-secret",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const SUPABASE_URL = (Deno.env.get("SUPABASE_URL") || "").replace(/\/$/, "");
const SERVICE_KEY =
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ||
  JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}").default ||
  "";
const RESEND_API_KEY = Deno.env.get("RESEND_API_KEY") || "";
const ALERT_EMAIL_FROM = Deno.env.get("ALERT_EMAIL_FROM") || "Google News FR <onboarding@resend.dev>";
const ALERT_CRON_SECRET = Deno.env.get("ALERT_CRON_SECRET") || "";
const REST_URL = `${SUPABASE_URL}/rest/v1`;

function jsonResponse(body: Json, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

function requireConfig() {
  const missing = [];
  if (!SUPABASE_URL) missing.push("SUPABASE_URL");
  if (!SERVICE_KEY) missing.push("SUPABASE_SERVICE_ROLE_KEY");
  if (!RESEND_API_KEY) missing.push("RESEND_API_KEY");
  if (missing.length) throw new Error(`Configuration manquante: ${missing.join(", ")}`);
}

function restHeaders(extra: HeadersInit = {}): HeadersInit {
  return {
    apikey: SERVICE_KEY,
    Authorization: `Bearer ${SERVICE_KEY}`,
    "Content-Type": "application/json",
    ...extra,
  };
}

function q(value: string): string {
  return encodeURIComponent(value);
}

async function restGet<T>(path: string): Promise<T> {
  const res = await fetch(`${REST_URL}${path}`, { headers: restHeaders() });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function restGetAll<T>(path: string, pageSize = 1000): Promise<T[]> {
  const rows: T[] = [];
  let offset = 0;
  const sep = path.includes("?") ? "&" : "?";
  while (true) {
    const batch = await restGet<T[]>(`${path}${sep}limit=${pageSize}&offset=${offset}`);
    if (!batch.length) break;
    rows.push(...batch);
    if (batch.length < pageSize) break;
    offset += pageSize;
  }
  return rows;
}

async function restPatch(table: string, query: string, payload: Json): Promise<void> {
  const res = await fetch(`${REST_URL}/${table}?${query}`, {
    method: "PATCH",
    headers: restHeaders({ Prefer: "return=minimal" }),
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
}

async function restPost(table: string, rows: Json[]): Promise<void> {
  if (!rows.length) return;
  const res = await fetch(`${REST_URL}/${table}`, {
    method: "POST",
    headers: restHeaders({ Prefer: "resolution=ignore-duplicates,return=minimal" }),
    body: JSON.stringify(rows),
  });
  if (!res.ok) throw new Error(await res.text());
}

function partMap(date: Date): Record<string, string> {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  return Object.fromEntries(parts.map((p) => [p.type, p.value]));
}

function parisLocal(date: Date): string {
  const p = partMap(date);
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
}

function parseLocal(value: string): Date {
  const [d, t = "00:00:00"] = value.replace(" ", "T").slice(0, 19).split("T");
  const [year, month, day] = d.split("-").map(Number);
  const [hour, minute, second] = t.split(":").map(Number);
  return new Date(Date.UTC(year, month - 1, day, hour || 0, minute || 0, second || 0));
}

function localFromPseudo(date: Date): string {
  return date.toISOString().slice(0, 19);
}

function addLocal(value: string, amount: number, unit: "hour" | "day"): string {
  const dt = parseLocal(value);
  dt.setTime(dt.getTime() + amount * (unit === "hour" ? 3600000 : 86400000));
  return localFromPseudo(dt);
}

function floorHour(value: string): string {
  return `${value.slice(0, 13)}:00:00`;
}

function ceilHour(value: string): string {
  const floored = floorHour(value);
  return value === floored ? floored : addLocal(floored, 1, "hour");
}

function localToUtcIso(local: string): string {
  const pseudo = parseLocal(local);
  const offset = offsetMinutesAt(pseudo);
  let utc = new Date(pseudo.getTime() - offset * 60000);
  const corrected = offsetMinutesAt(utc);
  if (corrected !== offset) utc = new Date(pseudo.getTime() - corrected * 60000);
  return utc.toISOString();
}

function offsetMinutesAt(date: Date): number {
  const p = partMap(date);
  const localAsUtc = Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), Number(p.hour), Number(p.minute), Number(p.second));
  return Math.round((localAsUtc - date.getTime()) / 60000);
}

function isoToParisLocal(value?: string | null): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return parisLocal(date);
}

function articleLocal(value?: string | null): string | null {
  if (!value) return null;
  return value.replace(" ", "T").slice(0, 19);
}

function localDate(value: string): string {
  return value.slice(0, 10);
}

function localHour(value: string): number {
  return Number(value.slice(11, 13));
}

function localWeekday(value: string): number {
  const day = parseLocal(value).getUTCDay();
  return day === 0 ? 6 : day - 1;
}

function normalizeKeywords(value: unknown): string[] {
  if (typeof value === "string") {
    try {
      value = JSON.parse(value);
    } catch {
      value = [value];
    }
  }
  if (!Array.isArray(value)) return [];
  return value.map((x) => normalizeText(String(x).trim())).filter(Boolean).slice(0, 12);
}

function normalizeText(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function articleText(article: Article): string {
  return normalizeText([
    article.title,
    article.summary,
    article.canonical_title,
    article.source,
    article.source_domain,
    article.media_group,
    article.first_query_kind,
    article.first_query_label,
    article.first_query_day,
    article.all_query_labels,
    article.link,
  ].filter(Boolean).join(" "));
}

function scopeMatch(article: Article, scope: string): boolean {
  if (scope === "top_100") return TOP_100_MEDIA_DOMAINS.has((article.source_domain || "").toLowerCase());
  if (scope === "national") return article.media_group === NATIONAL_GROUP;
  if (scope === "local") return article.media_group === LOCAL_GROUP;
  return true;
}

function keywordMatch(article: Article, keywords: string[], mode: string): boolean {
  const text = articleText(article);
  return mode === "all" ? keywords.every((k) => text.includes(k)) : keywords.some((k) => text.includes(k));
}

function matchingArticles(articles: Article[], filter: AlertFilter, keywords: string[]): Article[] {
  return articles.filter((article) =>
    scopeMatch(article, filter.scope || "all") &&
    keywordMatch(article, keywords, filter.match_mode || "any")
  );
}

function hourlyWindow(filter: AlertFilter, now: Date): [string, string] | null {
  const end = floorHour(parisLocal(now));
  const checkpoint = isoToParisLocal(filter.last_checked_at || filter.created_at || null);
  let start: string;
  if (!checkpoint) start = addLocal(end, -1, "hour");
  else if (["hourly", "daily", "weekly"].includes(filter.last_email_kind || "")) start = floorHour(checkpoint);
  else start = ceilHour(checkpoint);
  return start < end ? [start, end] : null;
}

function minuteWindow(now: Date): [string, string] {
  const end = floorHour(parisLocal(now));
  return [addLocal(end, -1, "hour"), end];
}

function scheduledWindow(filter: AlertFilter, now: Date): [string, string] | null {
  const scheduleType = filter.schedule_type || "hourly";
  if (scheduleType === "minute") return minuteWindow(now);
  if (scheduleType === "hourly") return hourlyWindow(filter, now);
  const localNow = parisLocal(now);
  const hour = Number(filter.schedule_hour ?? 8);
  let end = `${localDate(localNow)}T${String(hour).padStart(2, "0")}:00:00`;
  if (scheduleType === "weekly") {
    const delta = (localWeekday(end) - Number(filter.schedule_weekday ?? 0) + 7) % 7;
    end = addLocal(end, -delta, "day");
  }
  if (localNow < end) return null;
  const last = isoToParisLocal(filter.last_checked_at || filter.created_at || null);
  if (last && floorHour(last) >= end) return null;
  const fallback = addLocal(end, scheduleType === "weekly" ? -7 : -1, "day");
  const start = last && last < end ? last : fallback;
  return start < end ? [start, end] : null;
}

function periodKey(value: string, scheduleType: string): string {
  if (scheduleType === "weekly") {
    const d = parseLocal(value);
    const day = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() + 4 - day);
    const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
    const week = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
    return `${d.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
  }
  return localDate(value);
}

function scheduleDue(filter: AlertFilter, now: Date): boolean {
  const scheduleType = filter.schedule_type || "hourly";
  if (scheduleType === "minute" || scheduleType === "hourly") return true;
  const localNow = parisLocal(now);
  const hour = Number(filter.schedule_hour ?? 8);
  if (localHour(localNow) < hour) return false;
  if (scheduleType === "weekly" && localWeekday(localNow) !== Number(filter.schedule_weekday ?? 0)) return false;
  const last = isoToParisLocal(filter.last_schedule_checked_at || null);
  if (!last) return true;
  return periodKey(last, scheduleType) !== periodKey(localNow, scheduleType);
}

function windowLabel(start: string, end: string): string {
  const sDate = `${start.slice(8, 10)}/${start.slice(5, 7)}/${start.slice(0, 4)}`;
  const eDate = `${end.slice(8, 10)}/${end.slice(5, 7)}/${end.slice(0, 4)}`;
  const sTime = start.slice(11, 16);
  const eTime = end.slice(11, 16);
  return sDate === eDate ? `${sDate} ${sTime} - ${eTime}` : `${sDate} ${sTime} - ${eDate} ${eTime}`;
}

function fmtDate(value?: string | null): string {
  return (value || "").replace("T", " ").slice(0, 16);
}

function esc(value: unknown): string {
  return String(value || "").replace(/[&<>'"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[c] || c));
}

function buildEmail(filter: AlertFilter, rows: Article[], subject: string, intro: string, emptyText: string) {
  const text = [subject, "", intro];
  const htmlRows: string[] = [];
  if (!rows.length) {
    text.push("", emptyText);
    htmlRows.push(`<tr><td style="padding:18px;border-bottom:1px solid #e5e1d8;color:#4b463f;line-height:1.45">${esc(emptyText)}</td></tr>`);
  }
  for (const article of rows) {
    const title = article.title || "Sans titre";
    const source = article.source || "Source inconnue";
    const published = fmtDate(article.published);
    const link = article.link || "#";
    const summary = article.summary || "";
    text.push("", `- ${title}`, `  ${source} - ${published}`, `  ${link}`);
    htmlRows.push(`<tr><td style="padding:16px;border-bottom:1px solid #e5e1d8">
      <div style="font-size:12px;color:#6b665c;margin-bottom:6px">${esc(source)} · ${esc(published)}</div>
      <a href="${esc(link)}" style="font-size:17px;line-height:1.35;color:#0f766e;font-weight:700;text-decoration:none">${esc(title)}</a>
      ${summary ? `<p style="margin:8px 0 0;color:#4b463f;line-height:1.45">${esc(summary)}</p>` : ""}
    </td></tr>`);
  }
  const html = `<html><body style="margin:0;background:#f7f6f2;font-family:Arial,sans-serif;color:#171717">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f7f6f2;padding:24px">
      <tr><td align="center"><table role="presentation" width="680" cellspacing="0" cellpadding="0" style="max-width:680px;background:#fff;border:1px solid #dedbd2;border-radius:8px;overflow:hidden">
        <tr><td style="background:#20231f;color:#f8f6ef;padding:22px"><div style="font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:#c9c4b8">Google News FR</div><h1 style="margin:8px 0 0;font-size:24px">${esc(subject)}</h1><p style="margin:10px 0 0;color:#d9d3c5;line-height:1.45">${esc(intro)}</p></td></tr>
        ${htmlRows.join("")}
      </table></td></tr>
    </table>
  </body></html>`;
  return { text: text.join("\n"), html };
}

async function sendEmail(to: string, subject: string, text: string, html: string): Promise<void> {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${RESEND_API_KEY}`,
    },
    body: JSON.stringify({ from: ALERT_EMAIL_FROM, to, subject, text, html }),
  });
  if (!res.ok) throw new Error(await res.text());
}

async function updateLastEmail(filter: AlertFilter, nowIso: string, count: number, kind: string): Promise<void> {
  await restPatch("alert_filters", `id=eq.${q(filter.id)}`, {
    last_email_sent_at: nowIso,
    last_email_article_count: count,
    last_email_kind: kind,
  });
}

async function sendInitialTest(filter: AlertFilter, keywords: string[], nowIso: string): Promise<boolean> {
  const stats = await restGet<Array<{ last_article?: string | null }>>("/article_stats?select=last_article");
  const lastArticle = articleLocal(stats[0]?.last_article || null);
  if (!lastArticle) {
    await restPatch("alert_filters", `id=eq.${q(filter.id)}`, { first_test_sent_at: nowIso, last_checked_at: nowIso });
    return false;
  }
  const windowStart = addLocal(lastArticle, -1, "hour");
  const articles = await restGetAll<Article>(
    `/articles?select=uid,published,source,source_domain,media_group,title,summary,canonical_title,link,first_query_kind,first_query_label,first_query_day,all_query_labels&published=gt.${q(windowStart)}&published=lte.${q(lastArticle)}&order=published.desc`
  );
  const rows = matchingArticles(articles, filter, keywords);
  const label = filter.label || "Alerte Google News FR";
  const subject = `Test filtre actif - ${label}`;
  const email = buildEmail(
    filter,
    rows,
    subject,
    "Mail de validation: voici les articles qui auraient correspondu sur la dernière heure disponible de la base.",
    "Le filtre est actif, mais aucun article ne correspondait sur la dernière heure disponible."
  );
  await sendEmail(filter.email, subject, email.text, email.html);
  await restPatch("alert_filters", `id=eq.${q(filter.id)}`, { first_test_sent_at: nowIso, last_checked_at: nowIso });
  await updateLastEmail(filter, nowIso, rows.length, "test");
  await markPendingTests(filter.id, nowIso, "sent");
  return true;
}

async function markPendingTests(filterId: string, nowIso: string, status: string, error?: string): Promise<void> {
  await restPatch("alert_test_requests", `filter_id=eq.${q(filterId)}&processed_at=is.null`, {
    processed_at: nowIso,
    status,
    ...(error ? { error: error.slice(0, 500) } : {}),
  });
}

async function processOneTest(filterId: string, nowIso: string): Promise<boolean> {
  const rows = await restGet<AlertFilter[]>(`/alert_filters?select=*&active=eq.true&id=eq.${q(filterId)}&limit=1`);
  const filter = rows[0];
  if (!filter) return false;
  const keywords = normalizeKeywords(filter.keywords);
  if (!keywords.length || !filter.email) {
    await markPendingTests(filterId, nowIso, "invalid_filter");
    return false;
  }
  return await sendInitialTest(filter, keywords, nowIso);
}

async function processPendingTests(nowIso: string): Promise<number> {
  const requests = await restGetAll<{ id: number; filter_id: string }>(
    "/alert_test_requests?select=id,filter_id&processed_at=is.null&order=created_at.asc",
    250
  );
  let sent = 0;
  const seen = new Set<string>();
  for (const request of requests) {
    if (seen.has(request.filter_id)) {
      await restPatch("alert_test_requests", `id=eq.${request.id}`, { processed_at: nowIso, status: "duplicate" });
      continue;
    }
    seen.add(request.filter_id);
    try {
      if (await processOneTest(request.filter_id, nowIso)) sent += 1;
    } catch (error) {
      await restPatch("alert_test_requests", `id=eq.${request.id}`, { processed_at: nowIso, status: "error", error: String(error).slice(0, 500) });
      throw error;
    }
  }
  return sent;
}

async function processScheduled(now: Date, nowIso: string): Promise<Json> {
  const filters = await restGet<AlertFilter[]>("/alert_filters?select=*&active=eq.true&order=created_at.asc");
  const due = new Map<string, [string, string]>();
  for (const filter of filters) {
    if (!filter.first_test_sent_at || !scheduleDue(filter, now)) continue;
    const window = scheduledWindow(filter, now);
    if (window) due.set(filter.id, window);
  }
  const windows = [...due.values()];
  if (!windows.length) return { filters: filters.length, emails: 0, skipped: "no_due_window" };
  const since = windows.reduce((min, w) => w[0] < min ? w[0] : min, windows[0][0]);
  const until = windows.reduce((max, w) => w[1] > max ? w[1] : max, windows[0][1]);
  const articles = await restGetAll<Article>(
    `/articles?select=uid,published,source,source_domain,media_group,title,summary,canonical_title,link,first_query_kind,first_query_label,first_query_day,all_query_labels&published=gt.${q(since)}&published=lte.${q(until)}&order=published.asc`
  );
  if (!articles.length) {
    return { filters: filters.length, emails: 0, skipped: "no_articles_in_due_windows", window_start: since, window_end: until };
  }
  let emails = 0;
  for (const filter of filters) {
    const keywords = normalizeKeywords(filter.keywords);
    const window = due.get(filter.id);
    if (!keywords.length || !filter.email) {
      await restPatch("alert_filters", `id=eq.${q(filter.id)}`, { last_checked_at: nowIso });
      continue;
    }
    if (!window) continue;
    const [start, end] = window;
    const candidates = matchingArticles(
      articles.filter((article) => {
        const published = articleLocal(article.published || null);
        return published && start < published && published <= end;
      }),
      filter,
      keywords
    );
    const repeatEveryMinute = (filter.schedule_type || "hourly") === "minute";
    if (candidates.length || repeatEveryMinute) {
      const deliveredRows = repeatEveryMinute ? [] : await restGetAll<{ article_uid: string }>(`/alert_deliveries?select=article_uid&filter_id=eq.${q(filter.id)}`);
      const delivered = new Set(deliveredRows.map((row) => row.article_uid));
      const fresh = repeatEveryMinute ? candidates : candidates.filter((article) => article.uid && !delivered.has(article.uid));
      if (fresh.length || repeatEveryMinute) {
        const kind = filter.schedule_type || "hourly";
        const label = windowLabel(start, end);
        const subjectLabel = filter.label || "Alerte Google News FR";
        const subject = `${fresh.length} nouvel article${fresh.length > 1 ? "s" : ""} - ${subjectLabel} - ${label}`;
        const email = buildEmail(filter, fresh, subject, `Articles détectés sur la fenêtre complète: ${label}`, "Aucun article correspondant sur cette période.");
        await sendEmail(filter.email, subject, email.text, email.html);
        if (!repeatEveryMinute) {
          await restPost("alert_deliveries", fresh.filter((a) => a.uid).map((a) => ({ filter_id: filter.id, article_uid: a.uid as string })));
        }
        await updateLastEmail(filter, nowIso, fresh.length, kind);
        emails += 1;
      }
    }
    await restPatch("alert_filters", `id=eq.${q(filter.id)}`, { last_checked_at: localToUtcIso(end) });
    if (!["hourly", "minute"].includes(filter.schedule_type || "hourly")) {
      await restPatch("alert_filters", `id=eq.${q(filter.id)}`, { last_schedule_checked_at: nowIso });
    }
  }
  return { filters: filters.length, emails, window_start: since, window_end: until };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return jsonResponse({ error: "Method not allowed" }, 405);
  try {
    requireConfig();
    const body = await req.json().catch(() => ({}));
    const action = String(body.action || "all");
    const now = new Date();
    const nowIso = now.toISOString();

    if (action === "test") {
      const filterId = String(body.filter_id || "");
      if (!filterId) return jsonResponse({ error: "filter_id missing" }, 400);
      const sent = await processOneTest(filterId, nowIso);
      return jsonResponse({ ok: true, sent });
    }

    const providedSecret = req.headers.get("x-alert-cron-secret") || String(body.secret || "");
    if (!ALERT_CRON_SECRET || providedSecret !== ALERT_CRON_SECRET) {
      return jsonResponse({ error: "Unauthorized" }, 401);
    }

    const tests = action === "scheduled" ? 0 : await processPendingTests(nowIso);
    const scheduled = action === "tests" ? { emails: 0, skipped: "tests_only" } : await processScheduled(now, nowIso);
    return jsonResponse({ ok: true, tests, scheduled });
  } catch (error) {
    return jsonResponse({ ok: false, error: String(error instanceof Error ? error.message : error) }, 500);
  }
});
