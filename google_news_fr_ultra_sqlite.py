#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Google News FR - ULTRA RECALL SQLite, parallèle, sans console lourde

Objectif :
- Maximiser le rappel Google News RSS français.
- Ne pas saturer la console Windows.
- Dédupliquer au fil de l'eau.
- Écrire en continu dans SQLite.
- Exporter CSV propres à la fin.
- À la relance, reprendre la dernière base et chercher seulement les nouveaux créneaux horaires.
- Détecter les requêtes saturées et lancer une vague adaptative de sous-requêtes.

IMPORTANT :
Google News RSS n'est pas une API exhaustive. Ce script maximise le rappel,
mais ne peut pas garantir 100 % de tous les articles français publiés.

Lancement conseillé :
    python google_news_fr_ultra_sqlite.py --days 2 --mode ultra --concurrency 50

Si erreurs HTTP / ralentissements :
    python google_news_fr_ultra_sqlite.py --days 2 --mode ultra --concurrency 20

Sur un sujet :
    python google_news_fr_ultra_sqlite.py --query "agriculture OR pesticides" --days 2 --mode ultra --concurrency 50
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import html as html_lib
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone, time as dt_time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus, urlparse

try:
    import aiohttp
except ImportError:
    print("Module manquant: aiohttp. Lance: python -m pip install aiohttp")
    sys.exit(1)

try:
    import feedparser
except ImportError:
    print("Module manquant: feedparser. Lance: python -m pip install feedparser")
    sys.exit(1)

try:
    from dateutil import tz
except ImportError:
    print("Module manquant: python-dateutil. Lance: python -m pip install python-dateutil")
    sys.exit(1)

try:
    from langdetect import detect
except Exception:
    detect = None


PARIS_TZ = tz.gettz("Europe/Paris")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GoogleNewsFRUltraSQLite/1.0)",
    "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}

# Sources à exclure totalement des résultats exportés.
# Filtre sur le nom de source, le domaine source et le lien Google News.
EXCLUDED_SOURCE_PATTERNS = ["vietnam.vn"]

TOPICS = [
    "NATION", "WORLD", "BUSINESS", "TECHNOLOGY",
    "ENTERTAINMENT", "SPORTS", "SCIENCE", "HEALTH"
]

# Taxonomie volontairement large : macro-actu + longue traîne locale.
THEME_TERMS = [
    # général
    "France", "actualité", "information", "info", "direct", "reportage", "interview",
    "enquête", "analyse", "portrait", "témoignage", "communiqué",

    # politique / institutions
    "politique", "gouvernement", "ministre", "Assemblée nationale", "Sénat",
    "Matignon", "Élysée", "président", "Premier ministre", "député", "sénateur",
    "préfet", "préfecture", "maire", "élu", "opposition", "majorité",
    "loi", "décret", "réforme", "amendement", "budget", "impôts",
    "élection", "municipales", "européennes", "législatives", "sondage",

    # économie / entreprises
    "économie", "entreprise", "industrie", "emploi", "chômage", "inflation",
    "pouvoir d'achat", "salaire", "syndicat", "grève", "commerce", "banque",
    "assurance", "immobilier", "bourse", "startup", "PME", "TPE",
    "licenciement", "plan social", "recrutement", "investissement", "usine",
    "fermeture d'usine", "ouverture d'usine", "redressement judiciaire",
    "liquidation judiciaire", "tribunal de commerce",

    # tech / numérique
    "technologie", "numérique", "intelligence artificielle", "IA", "startup",
    "cybersécurité", "cyberattaque", "piratage", "données personnelles",
    "arnaque", "escroquerie", "phishing", "usurpation d'identité",
    "rançongiciel", "fraude en ligne", "réseaux sociaux",

    # justice / sécurité / faits divers
    "justice", "police", "gendarmerie", "tribunal", "procès", "plainte",
    "enquête judiciaire", "faits divers", "accident", "incendie", "agression",
    "meurtre", "homicide", "violences", "disparition", "drogue", "prison",
    "cambriolage", "vol", "braquage", "rixe", "bagarre", "agression sexuelle",
    "viol", "tentative de meurtre", "noyade", "collision", "accident mortel",
    "explosion", "disparition inquiétante", "appel à témoins", "interpellation",
    "garde à vue", "condamné", "condamnation", "relaxe", "mise en examen",
    "procureur", "cour d'assises", "tribunal correctionnel", "appel du jugement",
    "avocat", "prison ferme", "bracelet électronique",

    # société
    "société", "éducation", "école", "université", "étudiant", "logement",
    "transport", "SNCF", "RATP", "métro", "train", "retraite", "famille",
    "pauvreté", "précarité", "aide sociale", "handicap", "dépendance",
    "immigration", "asile", "discrimination", "égalité", "laïcité",
    "religion", "culte", "église", "mosquée", "synagogue",

    # vie locale / collectivités
    "mairie", "conseil municipal", "commune", "intercommunalité",
    "département", "région", "budget municipal", "travaux publics",
    "marché local", "association", "bénévoles", "vie associative",
    "fête locale", "cérémonie", "patrimoine local", "urbanisme",
    "permis de construire", "chantier", "rénovation", "centre-ville",

    # santé
    "santé", "hôpital", "médecin", "médicament", "maladie", "épidémie",
    "vaccin", "psychologie", "handicap", "EHPAD", "Ehpad",
    "urgences", "désert médical", "médecin généraliste", "clinique",
    "maternité", "infirmier", "pharmacie", "sécurité sociale",

    # environnement / agriculture / énergie
    "écologie", "climat", "météo", "canicule", "inondation", "sécheresse",
    "énergie", "nucléaire", "électricité", "agriculture", "agriculteurs",
    "pesticides", "eau", "biodiversité", "forêt", "pollution",
    "qualité de l'air", "eau potable", "nappes phréatiques", "décharge",
    "éolienne", "parc éolien", "photovoltaïque", "méthanisation",
    "centrale solaire", "gaz", "carburant",

    # météo / risques naturels
    "vigilance orange", "vigilance rouge", "orage", "neige", "verglas",
    "tempête", "crue", "inondations", "feu de forêt", "séisme",
    "fortes chaleurs", "alerte météo",

    # agriculture / agroalimentaire
    "élevage", "viticulture", "vigneron", "céréales", "lait", "porc",
    "volaille", "abattoir", "coopérative agricole", "agroalimentaire",
    "pêche", "ostréiculture", "bio", "label rouge", "sécurité alimentaire",
    "rappel produit", "fraude alimentaire", "grande distribution",
    "supermarché", "hypermarché", "prix alimentaires",

    # consommation / auto / logement
    "consommation", "consommateur", "UFC Que Choisir", "automobile",
    "voiture", "permis de conduire", "radar", "sécurité routière",
    "route coupée", "autoroute", "trafic routier", "stationnement",
    "vélo", "trottinette", "mobilité douce", "loyer", "logement social",
    "HLM", "copropriété", "squat", "expulsion",

    # éducation locale
    "collège", "lycée", "école primaire", "cantine scolaire",
    "harcèlement scolaire", "rectorat", "Parcoursup", "apprentissage",

    # culture / loisirs / tourisme
    "culture", "cinéma", "musique", "festival", "livre", "télévision",
    "concert", "exposition", "théâtre", "spectacle", "médiathèque",
    "tourisme", "hôtel", "restaurant", "camping", "plage",
    "station de ski", "patrimoine", "monument", "musée",

    # sport national + local
    "sport", "football", "rugby", "tennis", "cyclisme", "basket",
    "handball", "volley", "natation", "athlétisme", "club sportif",
    "championnat", "match nul", "victoire", "défaite", "entraîneur",
    "mercato", "coupe de France",

    # défense / international
    "armée", "militaire", "défense", "base militaire", "gendarme",
    "réserviste", "opération militaire", "Europe", "Union européenne",
    "Ukraine", "Russie", "États-Unis", "Trump", "Chine", "Moyen-Orient",
    "Israël", "Gaza", "Iran", "Afrique",
]

REGION_TERMS = [
    "Auvergne-Rhône-Alpes", "Bourgogne-Franche-Comté", "Bretagne", "Centre-Val de Loire",
    "Corse", "Grand Est", "Hauts-de-France", "Île-de-France", "Normandie",
    "Nouvelle-Aquitaine", "Occitanie", "Pays de la Loire", "Provence-Alpes-Côte d'Azur",
    "Guadeloupe", "Martinique", "Guyane", "La Réunion", "Mayotte",
    "Paris", "Marseille", "Lyon", "Toulouse", "Nice", "Nantes", "Montpellier",
    "Strasbourg", "Bordeaux", "Lille", "Rennes", "Reims", "Saint-Étienne",
    "Toulon", "Grenoble", "Dijon", "Angers", "Nîmes", "Villeurbanne",
    "Clermont-Ferrand", "Aix-en-Provence", "Brest", "Limoges", "Tours",
    "Amiens", "Metz", "Besançon", "Perpignan", "Orléans", "Mulhouse",
    "Rouen", "Caen", "Nancy", "Argenteuil", "Montreuil", "Avignon",
    "Poitiers", "Dunkerque", "Pau", "Annecy", "La Rochelle", "Calais",
    "Bayonne", "Chambéry", "Lorient", "Quimper", "Valence", "Nevers",
    "Roanne", "Fontainebleau", "Agen", "Albi", "Arras", "Béziers",
    "Bourges", "Brive", "Carcassonne", "Chartres", "Colmar", "Évreux",
    "Laval", "Le Mans", "Mâcon", "Narbonne", "Niort", "Périgueux",
    "Saint-Malo", "Saint-Nazaire", "Tarbes", "Vannes",
    "Ain", "Aisne", "Allier", "Alpes-Maritimes", "Ardèche", "Ardennes", "Ariège",
    "Aube", "Aude", "Aveyron", "Calvados", "Cantal", "Charente", "Charente-Maritime",
    "Cher", "Corrèze", "Côte-d'Or", "Côtes-d'Armor", "Creuse", "Dordogne", "Doubs",
    "Drôme", "Eure", "Eure-et-Loir", "Finistère", "Gard", "Gers", "Gironde",
    "Hérault", "Ille-et-Vilaine", "Indre", "Indre-et-Loire", "Isère", "Jura",
    "Landes", "Loir-et-Cher", "Loire", "Haute-Loire", "Loire-Atlantique", "Loiret",
    "Lot", "Lot-et-Garonne", "Lozère", "Maine-et-Loire", "Manche", "Marne",
    "Haute-Marne", "Mayenne", "Meurthe-et-Moselle", "Meuse", "Morbihan", "Moselle",
    "Nièvre", "Nord", "Oise", "Orne", "Pas-de-Calais", "Puy-de-Dôme",
    "Pyrénées-Atlantiques", "Hautes-Pyrénées", "Pyrénées-Orientales", "Bas-Rhin",
    "Haut-Rhin", "Rhône", "Haute-Saône", "Saône-et-Loire", "Sarthe", "Savoie",
    "Haute-Savoie", "Paris", "Seine-Maritime", "Seine-et-Marne", "Yvelines",
    "Deux-Sèvres", "Somme", "Tarn", "Tarn-et-Garonne", "Var", "Vaucluse",
    "Vendée", "Vienne", "Haute-Vienne", "Vosges", "Yonne", "Territoire de Belfort",
    "Essonne", "Hauts-de-Seine", "Seine-Saint-Denis", "Val-de-Marne", "Val-d'Oise",
]

# Combinaisons locales ultra-productives.
LOCAL_EVENT_TERMS = [
    "accident", "incendie", "agression", "interpellation", "tribunal",
    "condamnation", "garde à vue", "disparition", "cambriolage", "vol",
    "travaux", "mairie", "conseil municipal", "école", "collège",
    "lycée", "hôpital", "urgences", "grève", "manifestation",
    "festival", "concert", "exposition", "match", "club",
    "météo", "orage", "inondation", "route coupée", "commerce",
    "restaurant", "entreprise", "emploi", "immobilier", "agriculture",
]

SATURATION_SPLITTERS = [
    "politique", "économie", "justice", "faits divers", "police", "accident",
    "incendie", "santé", "hôpital", "éducation", "école", "transport",
    "agriculture", "écologie", "météo", "culture", "sport", "entreprise",
    "emploi", "immobilier", "mairie", "conseil municipal", "festival",
    "cyberattaque", "rappel produit", "grève", "manifestation",
]

MEDIA_DOMAINS = [
    # nationaux / TV / radio / pure players
    "lemonde.fr", "lefigaro.fr", "liberation.fr", "lesechos.fr", "la-croix.com",
    "leparisien.fr", "20minutes.fr", "francetvinfo.fr", "bfmtv.com", "cnews.fr",
    "tf1info.fr", "rtl.fr", "europe1.fr", "france24.com", "rfi.fr", "radiofrance.fr",
    "francebleu.fr", "mediapart.fr", "humanite.fr", "marianne.net", "nouvelobs.com",
    "lexpress.fr", "lepoint.fr", "publicsenat.fr", "lcp.fr", "huffingtonpost.fr",
    "slate.fr", "brut.media", "konbini.com", "numerama.com", "clubic.com",
    "01net.com", "usine-digitale.fr", "usinenouvelle.com", "challenges.fr",
    "capital.fr", "latribune.fr", "bfmbusiness.bfmtv.com", "actu.orange.fr",
    "linternaute.com", "journaldunet.com", "actu.fr",

    # PQR / régionaux / départementaux
    "ouest-france.fr", "sudouest.fr", "ladepeche.fr", "lavoixdunord.fr",
    "ledauphine.com", "leprogres.fr", "bienpublic.com", "estrepublicain.fr",
    "republicain-lorrain.fr", "dna.fr", "lalsace.fr", "lanouvellerepublique.fr",
    "centre-presse.fr", "courrier-picard.fr", "paris-normandie.fr", "lamontagne.fr",
    "lepopulaire.fr", "lejdc.fr", "lyonne.fr", "leberry.fr", "midilibre.fr",
    "lindependant.fr", "nicematin.com", "varmatin.com", "monacomatin.mc",
    "corsematin.com", "laprovence.com", "lamarseillaise.fr", "letelegramme.fr",
    "presseocean.fr", "lemainelibre.fr", "courrierdelouest.fr", "charentelibre.fr",
    "larepubliquedespyrenees.fr", "petitbleu.fr", "lejsl.com", "lamanchelibre.fr",
    "lechorepublicain.fr", "lagazettedescommunes.com", "lardennais.fr",
    "union.fr", "vosgesmatin.fr", "lavoixdelain.fr", "lessor38.fr",
    "lessor42.fr", "lessor69.fr", "lepatriote.fr", "le-pays.fr",
    "journaldelbeuf.fr", "actu-juridique.fr", "lereveilnormand.fr",
    "la-chronique-republicaine.fr", "lejournaldevitre.fr", "le-penthièvre.fr",
    "lagazettedemanche.fr", "lechodelabaie.fr", "le-courrier.com",
    "lhebdo-de-charente-maritime.com", "hauteprovenceinfo.com",

    # locaux / urbains / indépendants
    "madeinmarseille.net", "marsactu.fr", "rue89strasbourg.com", "mediacites.fr",
    "lyoncapitale.fr", "lyonmag.com", "tribunedelyon.fr", "toulouse7.com",
    "objectifgard.com", "metropolitain.nantes.fr", "bordeauxactu.fr",
    "brest.maville.com", "rennes.maville.com", "nantes.maville.com",
    "angers.maville.com", "caen.maville.com", "lilleactu.fr", "78actu.fr",
    "94.citoyens.com", "93.citoyens.com", "94citoyens.com", "sortiraparis.com",
    "actuacity.com", "toutlyon.fr", "infodujour.fr", "placegrenet.fr",
    "grenoblealpesmetropole.fr", "info-chalon.com", "creusot-infos.com",
    "macon-infos.com", "zoomdici.fr", "42info.fr", "info-tours.fr",
    "angersinfo.fr", "nantes-infos.fr", "rennes-infos.fr", "infos-dijon.com",

    # outre-mer
    "la1ere.francetvinfo.fr", "clicanoo.re", "zinfos974.com", "domtomnews.com",
    "franceguyane.fr", "martinique.franceantilles.fr", "guadeloupe.franceantilles.fr",
    "tahiti-infos.com", "linfo.re", "ipreunion.com",

    # spécialisés
    "reussir.fr", "terre-net.fr", "agri-mutuel.com", "pleinchamp.com",
    "lavoixdupaysan.fr", "wikiagri.fr", "campagnesetenvironnement.fr",
    "environnement-magazine.fr", "actu-environnement.com", "novethic.fr",
    "batiactu.com", "lemoniteur.fr", "autoactu.com", "caradisiac.com",
    "automobile-magazine.fr", "futura-sciences.com", "sciencesetavenir.fr",
    "santemagazine.fr", "pourquoidocteur.fr", "egora.fr", "hospimedia.fr",
    "aefinfo.fr", "letudiant.fr", "studyrama.com", "banquedesterritoires.fr",
]


def unique(seq):
    seen = set()
    out = []
    for x in seq:
        x = str(x).strip()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


THEME_TERMS = unique(THEME_TERMS)
REGION_TERMS = unique(REGION_TERMS)
LOCAL_EVENT_TERMS = unique(LOCAL_EVENT_TERMS)
SATURATION_SPLITTERS = unique(SATURATION_SPLITTERS)
MEDIA_DOMAINS = unique([d.lower().replace("https://", "").replace("http://", "").split("/")[0] for d in MEDIA_DOMAINS])


def load_extra_domains(path="medias_domains.txt") -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        d = line.lower().replace("https://", "").replace("http://", "").split("/")[0]
        if d:
            out.append(d)
    return unique(out)


def normalize_space(x: str) -> str:
    return re.sub(r"\s+", " ", x or "").strip()


def strip_html(x: str) -> str:
    text = re.sub(r"<.*?>", " ", x or "")
    text = html_lib.unescape(text).replace("\xa0", " ")
    return normalize_space(text)


def canonical_title(title: str) -> str:
    x = (title or "").lower()
    x = re.sub(r"[’']", " ", x)
    x = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ0-9]+", " ", x)
    x = re.sub(r"\b(le|la|les|un|une|des|de|du|d|l|à|a|et|en|dans|sur|pour|avec|au|aux)\b", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def article_uid(title: str, source: str, link: str) -> str:
    t = canonical_title(title)
    s = normalize_space(source).lower()
    raw = f"{t}|{s}"
    if not t:
        raw = link or source
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def source_uid(source: str) -> str:
    return hashlib.sha1(normalize_space(source).lower().encode("utf-8", errors="ignore")).hexdigest()


def parse_dt(entry) -> datetime | None:
    for key in ("published", "updated"):
        value = getattr(entry, key, None) or entry.get(key)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(PARIS_TZ)
            except Exception:
                pass

    for key in ("published_parsed", "updated_parsed"):
        value = getattr(entry, key, None) or entry.get(key)
        if value:
            try:
                dt = datetime.fromtimestamp(time.mktime(value), tz=timezone.utc)
                return dt.astimezone(PARIS_TZ)
            except Exception:
                pass

    return None


def source_from_entry(entry) -> tuple[str, str]:
    title = ""
    href = ""

    try:
        title = entry.source.title or ""
    except Exception:
        pass

    try:
        href = entry.source.href or ""
    except Exception:
        pass

    source_obj = entry.get("source")
    if isinstance(source_obj, dict):
        title = title or source_obj.get("title", "")
        href = href or source_obj.get("href", "")

    if not title:
        raw_title = strip_html(entry.get("title", ""))
        if " - " in raw_title:
            title = raw_title.rsplit(" - ", 1)[-1].strip()

    return title or "Source inconnue", href or ""


def title_without_source(title: str, source: str) -> str:
    title = strip_html(title)
    suffix = " - " + source
    if source and title.endswith(suffix):
        return title[:-len(suffix)].strip()
    return title


def domain_from_url(url: str) -> str:
    try:
        return urlparse(url or "").netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_excluded_source(source: str, source_domain: str, link: str) -> bool:
    haystack = " ".join([
        (source or "").lower(),
        (source_domain or "").lower(),
        (link or "").lower(),
    ])
    return any(pattern.lower() in haystack for pattern in EXCLUDED_SOURCE_PATTERNS)


def is_probably_french(title: str, summary: str) -> bool:
    if detect is None:
        return True
    text = strip_html((title or "") + " " + (summary or ""))
    if len(text) < 35:
        return True
    try:
        return detect(text) == "fr"
    except Exception:
        return True


def google_news_search_url(query: str) -> str:
    return "https://news.google.com/rss/search?q={}&hl=fr&gl=FR&ceid=FR:fr".format(quote_plus(query))


def google_news_topic_url(topic: str) -> str:
    return "https://news.google.com/rss/headlines/section/topic/{}?hl=fr&gl=FR&ceid=FR:fr".format(topic)


def date_windows(start_dt: datetime, end_dt: datetime) -> list[tuple[datetime, datetime]]:
    out = []
    cur = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    while cur < end_dt:
        nxt = cur + timedelta(days=1)
        out.append((cur, min(nxt, end_dt)))
        cur = nxt
    return out


def q_with_date(base: str, d0: datetime, d1: datetime) -> str:
    before_day = d1.date()
    if d1.time() != dt_time.min:
        before_day = before_day + timedelta(days=1)
    return f"{base} after:{d0:%Y-%m-%d} before:{before_day:%Y-%m-%d}"


def make_query(kind, label, base_query, d0=None, d1=None, wave=1):
    if kind == "topic":
        url = google_news_topic_url(base_query)
        day = ""
        query = base_query
    else:
        query = q_with_date(base_query, d0, d1)
        url = google_news_search_url(query)
        day = d0.strftime("%Y-%m-%d") if d0 else ""
    return {
        "kind": kind,
        "label": label,
        "base_query": base_query,
        "day": day,
        "date_from": d0.strftime("%Y-%m-%d %H:%M:%S") if d0 else "",
        "date_to": d1.strftime("%Y-%m-%d %H:%M:%S") if d1 else "",
        "wave": wave,
        "url": url,
        "query": query,
    }


def build_queries(args, start_dt, end_dt, wave=1, exact_window=False) -> list[dict]:
    windows = [(start_dt, end_dt)] if exact_window else date_windows(start_dt, end_dt)
    queries = []

    if args.include_topics:
        for topic in TOPICS:
            queries.append(make_query("topic", f"topic:{topic}", topic, wave=wave))

    if args.query:
        for d0, d1 in windows:
            queries.append(make_query("user_query", "user_query", args.query, d0, d1, wave=wave))

    terms = []
    geos = []
    domains = []

    if args.mode in ("balanced", "aggressive", "ultra"):
        if args.mode == "balanced":
            terms = THEME_TERMS[:90]
        elif args.mode == "aggressive":
            terms = THEME_TERMS[:180]
        else:
            terms = THEME_TERMS

        for term in terms:
            for d0, d1 in windows:
                queries.append(make_query("theme", "theme:" + term, term, d0, d1, wave=wave))

    if args.mode in ("aggressive", "ultra"):
        geos = REGION_TERMS if args.mode == "ultra" else REGION_TERMS[:120]
        for geo in geos:
            for d0, d1 in windows:
                queries.append(make_query("geo", "geo:" + geo, geo, d0, d1, wave=wave))

    if args.mode == "ultra" and args.local_combos:
        combo_geos = REGION_TERMS[:args.combo_geo_limit]
        combo_events = LOCAL_EVENT_TERMS[:args.combo_event_limit]
        for geo in combo_geos:
            for ev in combo_events:
                base = f"{ev} {geo}"
                for d0, d1 in windows:
                    queries.append(make_query("local_combo", "local_combo:" + base, base, d0, d1, wave=wave))

    if args.domain_search:
        domains = unique(MEDIA_DOMAINS + load_extra_domains(args.domains_file))
        if args.mode == "balanced":
            domains = domains[:90]
        elif args.mode == "aggressive":
            domains = domains[:160]
        # ultra prend tout.
        for domain in domains:
            for d0, d1 in windows:
                base = "site:" + domain
                queries.append(make_query("domain", "domain:" + domain, base, d0, d1, wave=wave))

    return dedupe_queries(queries, args.max_queries if wave == 1 else 0)


def dedupe_queries(queries, max_queries=0):
    out = []
    seen = set()
    for q in queries:
        if q["url"] in seen:
            continue
        seen.add(q["url"])
        out.append(q)
        if max_queries and max_queries > 0 and len(out) >= max_queries:
            break
    return out


def build_adaptive_queries(saturated_rows, args, existing_urls):
    out = []
    if not args.adaptive:
        return out

    for row in saturated_rows:
        kind = row["kind"]
        if kind == "topic":
            continue
        base = row["base_query"]
        d0s = row["date_from"]
        d1s = row["date_to"]
        if not d0s or not d1s:
            continue
        try:
            d0 = datetime.fromisoformat(d0s).replace(tzinfo=PARIS_TZ)
            d1 = datetime.fromisoformat(d1s).replace(tzinfo=PARIS_TZ)
        except Exception:
            continue

        n = 0
        for splitter in SATURATION_SPLITTERS:
            if splitter.lower() in base.lower():
                continue

            if base.startswith("site:"):
                new_base = f"{base} {splitter}"
            else:
                new_base = f"{base} {splitter}"

            q = make_query("adaptive", "adaptive:" + new_base, new_base, d0, d1, wave=2)
            if q["url"] not in existing_urls:
                out.append(q)
                existing_urls.add(q["url"])
                n += 1
            if n >= args.adaptive_splitters_per_query:
                break

    if args.max_adaptive_queries and args.max_adaptive_queries > 0:
        out = out[:args.max_adaptive_queries]
    return out


def init_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            uid TEXT PRIMARY KEY,
            published TEXT,
            date TEXT,
            hour TEXT,
            source TEXT,
            source_domain TEXT,
            title TEXT,
            summary TEXT,
            canonical_title TEXT,
            link TEXT,
            first_query_kind TEXT,
            first_query_label TEXT,
            first_query_day TEXT,
            all_query_labels TEXT,
            occurrences_in_feeds INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wave INTEGER,
            kind TEXT,
            label TEXT,
            base_query TEXT,
            day TEXT,
            date_from TEXT,
            date_to TEXT,
            status INTEGER,
            raw_entries INTEGER,
            kept_before_dedup INTEGER,
            error TEXT,
            url TEXT,
            query TEXT,
            finished_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wave INTEGER,
            kind TEXT,
            label TEXT,
            base_query TEXT,
            day TEXT,
            date_from TEXT,
            date_to TEXT,
            url TEXT,
            query TEXT
        )
    """)
    article_columns = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
    if "summary" not in article_columns:
        conn.execute("ALTER TABLE articles ADD COLUMN summary TEXT DEFAULT ''")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_date ON articles(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_raw ON attempts(raw_entries)")
    conn.commit()
    return conn


def insert_query_plan(conn, queries):
    conn.executemany("""
        INSERT INTO query_plan(wave, kind, label, base_query, day, date_from, date_to, url, query)
        VALUES(:wave, :kind, :label, :base_query, :day, :date_from, :date_to, :url, :query)
    """, queries)
    conn.commit()


def upsert_articles(conn, rows):
    if not rows:
        return

    conn.executemany("""
        INSERT INTO articles(
            uid, published, date, hour, source, source_domain, title, summary, canonical_title, link,
            first_query_kind, first_query_label, first_query_day, all_query_labels,
            occurrences_in_feeds, created_at
        )
        VALUES(
            :uid, :published, :date, :hour, :source, :source_domain, :title, :summary, :canonical_title, :link,
            :first_query_kind, :first_query_label, :first_query_day, :all_query_labels,
            1, :created_at
        )
        ON CONFLICT(uid) DO UPDATE SET
            summary = CASE
                WHEN COALESCE(articles.summary, '') = '' AND COALESCE(excluded.summary, '') <> ''
                THEN excluded.summary
                ELSE articles.summary
            END,
            occurrences_in_feeds = occurrences_in_feeds + 1,
            all_query_labels = CASE
                WHEN instr(articles.all_query_labels, excluded.first_query_label) = 0
                THEN articles.all_query_labels || ' | ' || excluded.first_query_label
                ELSE articles.all_query_labels
            END
    """, rows)


def update_article_summaries(conn, rows):
    rows = [row for row in rows if row.get("summary")]
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany("""
        UPDATE articles
        SET summary = :summary
        WHERE uid = :uid
          AND COALESCE(summary, '') = ''
          AND COALESCE(:summary, '') <> ''
    """, rows)
    return conn.total_changes - before


def missing_summary_count(conn) -> int:
    try:
        return conn.execute("SELECT COUNT(*) FROM articles WHERE COALESCE(summary, '') = ''").fetchone()[0]
    except sqlite3.OperationalError:
        return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]


def build_summary_backfill_queries(conn, limit: int) -> list[dict]:
    if limit <= 0:
        return []
    rows = conn.execute("""
        SELECT wave, kind, label, base_query, day, date_from, date_to, url, query,
               MAX(finished_at) AS last_finished, MAX(raw_entries) AS max_raw
        FROM attempts
        WHERE COALESCE(url, '') <> ''
          AND COALESCE(error, '') = ''
          AND status = 200
        GROUP BY url
        ORDER BY last_finished DESC, max_raw DESC
        LIMIT ?
    """, (int(limit),)).fetchall()
    keys = ["wave", "kind", "label", "base_query", "day", "date_from", "date_to", "url", "query", "last_finished", "max_raw"]
    out = []
    for row in rows:
        item = dict(zip(keys, row))
        item["wave"] = 90
        out.append({k: item.get(k, "") for k in ["wave", "kind", "label", "base_query", "day", "date_from", "date_to", "url", "query"]})
    return out


def insert_attempt(conn, attempt):
    conn.execute("""
        INSERT INTO attempts(
            wave, kind, label, base_query, day, date_from, date_to, status,
            raw_entries, kept_before_dedup, error, url, query, finished_at
        )
        VALUES(
            :wave, :kind, :label, :base_query, :day, :date_from, :date_to, :status,
            :raw_entries, :kept_before_dedup, :error, :url, :query, :finished_at
        )
    """, attempt)


async def fetch_one(session, sem, qinfo, retries, timeout):
    url = qinfo["url"]
    last_error = ""
    status = 0

    for attempt in range(retries + 1):
        async with sem:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    status = resp.status
                    content = await resp.read()
                    if status == 200:
                        return {**qinfo, "ok": True, "status": status, "content": content, "error": ""}
                    last_error = f"HTTP {status}"
            except Exception as e:
                last_error = repr(e)

        if attempt < retries:
            await asyncio.sleep(0.4 * (attempt + 1))

    return {**qinfo, "ok": False, "status": status, "content": b"", "error": last_error}


def query_filter_window(result, fallback_start, fallback_end):
    d0s = result.get("date_from") or ""
    d1s = result.get("date_to") or ""
    try:
        d0 = datetime.fromisoformat(d0s).replace(tzinfo=PARIS_TZ) if d0s else fallback_start
        d1 = datetime.fromisoformat(d1s).replace(tzinfo=PARIS_TZ) if d1s else fallback_end
        return d0, d1
    except Exception:
        return fallback_start, fallback_end


def process_feed_result(result, start_dt, end_dt, lang_filter=False):
    now_s = datetime.now(PARIS_TZ).strftime("%Y-%m-%d %H:%M:%S")
    filter_start, filter_end = query_filter_window(result, start_dt, end_dt)

    if not result["ok"]:
        attempt = {
            **{k: result.get(k, "") for k in ["wave", "kind", "label", "base_query", "day", "date_from", "date_to", "url", "query"]},
            "status": result.get("status", 0),
            "raw_entries": 0,
            "kept_before_dedup": 0,
            "error": result.get("error", ""),
            "finished_at": now_s,
        }
        return [], attempt

    parsed = feedparser.parse(result["content"])
    entries = getattr(parsed, "entries", []) or []
    rows = []

    for entry in entries:
        published = parse_dt(entry)
        if not published:
            continue
        if not (filter_start <= published < filter_end):
            continue

        source, source_href = source_from_entry(entry)
        raw_title = strip_html(entry.get("title", ""))
        title = title_without_source(raw_title, source)
        summary = strip_html(entry.get("summary", ""))
        link = entry.get("link", "")

        if not title:
            continue
        if lang_filter and not is_probably_french(title, summary):
            continue

        ctitle = canonical_title(title)
        uid = article_uid(title, source, link)
        source_domain = domain_from_url(source_href)

        if is_excluded_source(source, source_domain, link):
            continue

        rows.append({
            "uid": uid,
            "published": published.strftime("%Y-%m-%d %H:%M:%S"),
            "date": published.strftime("%Y-%m-%d"),
            "hour": published.strftime("%H:%M"),
            "source": source,
            "source_domain": source_domain,
            "media_group": classify_media_group(source, source_domain),
            "title": title,
            "summary": summary,
            "canonical_title": ctitle,
            "link": link,
            "first_query_kind": result["kind"],
            "first_query_label": result["label"],
            "first_query_day": result["day"],
            "all_query_labels": result["label"],
            "created_at": now_s,
        })

    attempt = {
        **{k: result.get(k, "") for k in ["wave", "kind", "label", "base_query", "day", "date_from", "date_to", "url", "query"]},
        "status": result.get("status", 200),
        "raw_entries": len(entries),
        "kept_before_dedup": len(rows),
        "error": "",
        "finished_at": now_s,
    }
    return rows, attempt


async def run_summary_backfill(conn, args):
    missing_before = missing_summary_count(conn)
    if not args.summary_backfill or missing_before <= 0 or args.summary_backfill_limit <= 0:
        return 0

    queries = build_summary_backfill_queries(conn, args.summary_backfill_limit)
    if not queries:
        return 0

    connector = aiohttp.TCPConnector(
        limit=max(args.concurrency * 2, 100),
        limit_per_host=max(args.concurrency, 50),
        ssl=False,
        ttl_dns_cache=300,
    )
    sem = asyncio.Semaphore(args.concurrency)
    broad_start = datetime(1970, 1, 1, tzinfo=PARIS_TZ)
    broad_end = datetime.now(PARIS_TZ) + timedelta(days=1)
    started = time.time()
    updated_total = 0

    print(f"\nRattrapage résumés: {len(queries)} anciennes requêtes | articles sans résumé={missing_before}")
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [fetch_one(session, sem, q, args.retries, args.timeout) for q in queries]
        done = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            rows, _attempt = process_feed_result(result, broad_start, broad_end, lang_filter=False)
            updated_total += update_article_summaries(conn, rows)
            done += 1

            if done % args.commit_every == 0:
                conn.commit()
            if done % args.progress_every == 0 or done == len(tasks):
                remaining = missing_summary_count(conn)
                elapsed = time.time() - started
                print(f"  résumés {done}/{len(tasks)} | ajoutés={updated_total} | encore_vides={remaining} | {elapsed:.1f}s")
        conn.commit()

    return updated_total


async def run_wave(conn, queries, args, start_dt, end_dt, wave_name):
    if not queries:
        return []

    connector = aiohttp.TCPConnector(
        limit=max(args.concurrency * 2, 100),
        limit_per_host=max(args.concurrency, 50),
        ssl=False,
        ttl_dns_cache=300,
    )
    sem = asyncio.Semaphore(args.concurrency)
    started = time.time()
    debug_attempts = []

    print(f"\n{wave_name}: {len(queries)} requêtes | concurrence={args.concurrency}")

    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [fetch_one(session, sem, q, args.retries, args.timeout) for q in queries]

        done = 0
        inserted_since_commit = 0

        for coro in asyncio.as_completed(tasks):
            result = await coro
            rows, attempt = process_feed_result(result, start_dt, end_dt, lang_filter=args.lang_filter)

            upsert_articles(conn, rows)
            insert_attempt(conn, attempt)
            debug_attempts.append(attempt)

            inserted_since_commit += len(rows)
            done += 1

            if done % args.commit_every == 0:
                conn.commit()

            if done % args.progress_every == 0 or done == len(tasks):
                elapsed = time.time() - started
                unique_count = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
                raw_sum = conn.execute("SELECT COALESCE(SUM(raw_entries),0) FROM attempts WHERE wave=?", (queries[0]["wave"],)).fetchone()[0]
                print(f"  progression {done}/{len(tasks)} | uniques={unique_count} | raw_wave={raw_sum} | {elapsed:.1f}s")

        conn.commit()

    return debug_attempts


def export_table(conn, sql, path, headers):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in conn.execute(sql):
            w.writerow(row)


def floor_to_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def latest_output_dir(root: Path) -> Path | None:
    candidates = []
    for child in root.glob("sortie_google_news_fr_ULTRA_*"):
        db = child / "google_news_fr_ultra.sqlite"
        if child.is_dir() and db.exists():
            candidates.append(child)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)


def latest_finished_at(conn) -> datetime | None:
    row = conn.execute("SELECT MAX(finished_at) FROM attempts").fetchone()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(row[0]).replace(tzinfo=PARIS_TZ)
    except Exception:
        return None


LOCAL_MEDIA_DOMAINS = {
    "ouest-france.fr", "sudouest.fr", "ladepeche.fr", "lavoixdunord.fr", "ledauphine.com",
    "leprogres.fr", "bienpublic.com", "estrepublicain.fr", "republicain-lorrain.fr", "dna.fr",
    "lalsace.fr", "lanouvellerepublique.fr", "centre-presse.fr", "courrier-picard.fr",
    "paris-normandie.fr", "lamontagne.fr", "lepopulaire.fr", "lejdc.fr", "lyonne.fr",
    "leberry.fr", "midilibre.fr", "lindependant.fr", "nicematin.com", "varmatin.com",
    "corsematin.com", "laprovence.com", "letelegramme.fr", "presseocean.fr", "lemainelibre.fr",
    "courrierdelouest.fr", "charentelibre.fr", "larepubliquedespyrenees.fr", "lejsl.com",
    "lamanchelibre.fr", "lechorepublicain.fr", "lardennais.fr", "union.fr", "vosgesmatin.fr",
    "actu.fr", "francebleu.fr", "ici.fr", "maville.com",
}
NATIONAL_MEDIA_DOMAINS = {
    "lemonde.fr", "lefigaro.fr", "liberation.fr", "lesechos.fr", "la-croix.com", "leparisien.fr",
    "20minutes.fr", "nouvelobs.com", "lexpress.fr", "lepoint.fr", "marianne.net", "humanite.fr",
    "huffingtonpost.fr", "mediapart.fr", "publicsenat.fr", "lcp.fr", "slate.fr",
}
TV_RADIO_DOMAINS = {
    "francetvinfo.fr", "bfmtv.com", "cnews.fr", "tf1info.fr", "rtl.fr", "europe1.fr",
    "france24.com", "rfi.fr", "radiofrance.fr", "francebleu.fr", "ici.fr",
}
ECONOMY_DOMAINS = {
    "lesechos.fr", "challenges.fr", "capital.fr", "latribune.fr", "boursorama.com",
    "bfmbusiness.bfmtv.com", "usinenouvelle.com", "usine-digitale.fr", "journaldunet.com",
}
TECH_DOMAINS = {"numerama.com", "clubic.com", "01net.com", "futura-sciences.com"}
SPECIALIZED_DOMAINS = {
    "letudiant.fr", "studyrama.com", "reussir.fr", "terre-net.fr", "agri-mutuel.com", "pleinchamp.com",
    "actu-environnement.com", "novethic.fr", "batiactu.com", "lemoniteur.fr", "caradisiac.com",
    "autoactu.com", "santemagazine.fr", "pourquoidocteur.fr", "egora.fr", "hospimedia.fr",
    "aefinfo.fr", "banquedesterritoires.fr",
}
OVERSEAS_DOMAINS = {
    "la1ere.francetvinfo.fr", "clicanoo.re", "zinfos974.com", "domtomnews.com", "franceguyane.fr",
    "martinique.franceantilles.fr", "guadeloupe.franceantilles.fr", "tahiti-infos.com", "linfo.re",
    "ipreunion.com",
}
PORTAL_DOMAINS = {"msn.com", "actu.orange.fr", "orange.fr", "linternaute.com", "info.fr"}
LOCAL_HINTS = (
    "maville", "ma ville", "actu ", " actu", "matin", "républicain", "republicain", "dépêche", "depeche",
    "telegramme", "montagne", "dauphiné", "dauphine", "progrès", "progres", "voix du nord",
)


def domain_matches(domain: str, candidates: set[str]) -> bool:
    domain = (domain or "").lower().replace("www.", "")
    return any(domain == candidate or domain.endswith("." + candidate) for candidate in candidates)


def classify_media_group(source: str, source_domain: str) -> str:
    source_l = normalize_space(source).lower()
    domain = (source_domain or "").lower().replace("www.", "")
    if domain_matches(domain, OVERSEAS_DOMAINS):
        return "Outre-mer"
    if domain_matches(domain, TV_RADIO_DOMAINS):
        return "TV / radio"
    if domain_matches(domain, ECONOMY_DOMAINS):
        return "Économie"
    if domain_matches(domain, TECH_DOMAINS):
        return "Tech / numérique"
    if domain_matches(domain, SPECIALIZED_DOMAINS):
        return "Médias spécialisés"
    if domain_matches(domain, PORTAL_DOMAINS):
        return "Portails / agrégateurs"
    if domain_matches(domain, LOCAL_MEDIA_DOMAINS) or any(hint in source_l for hint in LOCAL_HINTS):
        return "Presse locale et régionale"
    if domain_matches(domain, NATIONAL_MEDIA_DOMAINS):
        return "Presse nationale"
    if not domain:
        return "Autres médias"
    return "Autres médias"


DASHBOARD_HTML = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google News FR - Dashboard</title>
  <script src="dashboard_google_news_data.js"></script>
  <style>
    :root {
      --bg: #f6f5f1;
      --surface: #ffffff;
      --surface-2: #f0efea;
      --ink: #171717;
      --muted: #69655d;
      --line: #dedbd2;
      --accent: #0f766e;
      --accent-2: #b45309;
      --danger: #be123c;
      --focus: rgba(15, 118, 110, .18);
      --shadow: 0 18px 55px rgba(31, 35, 34, .12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    button, input, select { font: inherit; }
    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 304px minmax(0, 1fr);
    }
    .side {
      position: sticky;
      top: 0;
      height: 100vh;
      padding: 28px 22px;
      background: #20231f;
      color: #f8f6ef;
      border-right: 1px solid rgba(255,255,255,.08);
      display: flex;
      flex-direction: column;
      gap: 24px;
    }
    .brand { display: grid; gap: 8px; }
    .brand small { color: #b9b5a9; font-size: 12px; text-transform: uppercase; letter-spacing: .14em; }
    h1 { margin: 0; font-size: 25px; line-height: 1.08; font-weight: 760; }
    .updated { color: #c9c4b8; font-size: 13px; line-height: 1.45; }
    .sideStats { display: grid; gap: 10px; }
    .stat {
      border: 1px solid rgba(255,255,255,.1);
      background: rgba(255,255,255,.055);
      border-radius: 8px;
      padding: 14px;
    }
    .stat .num { font-size: 28px; line-height: 1; font-weight: 780; }
    .stat .label { margin-top: 6px; color: #c9c4b8; font-size: 12px; }
    .sideFoot { margin-top: auto; color: #aaa396; font-size: 12px; line-height: 1.5; }
    main { padding: 26px 30px 44px; min-width: 0; }
    .topbar {
      display: grid;
      grid-template-columns: minmax(240px, 1fr) 210px 220px 170px;
      gap: 10px;
      align-items: center;
      margin-bottom: 16px;
    }
    .searchBox, .filterBox { position: relative; }
    .filterIcon {
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--muted);
      font-size: 13px;
      pointer-events: none;
    }
    .searchBox input {
      width: 100%;
      height: 48px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      padding: 0 44px 0 16px;
      outline: none;
      box-shadow: 0 1px 0 rgba(0,0,0,.02);
    }
    .searchBox input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 0 4px var(--focus); }
    .searchBox .kbd {
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--muted);
      font-size: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 2px 6px;
      background: #faf9f5;
    }
    select {
      height: 48px;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      color: var(--ink);
      padding: 0 12px;
      outline: none;
    }
    .filterBox select { padding-left: 34px; }
    .summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 16px;
    }
    .metric {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }
    .metric b { display: block; font-size: 22px; line-height: 1.1; }
    .metric span { display: block; margin-top: 6px; color: var(--muted); font-size: 12px; }
    .workspace {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 280px;
      gap: 16px;
      align-items: start;
    }
    .panel, .rail {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 1px 0 rgba(0,0,0,.02);
    }
    .panelHead {
      min-height: 54px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .panelHead h2 { margin: 0; font-size: 15px; font-weight: 720; }
    .panelHead p { margin: 0; color: var(--muted); font-size: 13px; }
    .list { display: grid; }
    .article {
      display: grid;
      grid-template-columns: 118px minmax(0, 1fr);
      gap: 16px;
      padding: 16px;
      border-bottom: 1px solid var(--line);
    }
    .article:last-child { border-bottom: 0; }
    .date {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
      white-space: nowrap;
    }
    .title {
      margin: 0 0 8px;
      font-size: 17px;
      line-height: 1.3;
      font-weight: 720;
    }
    .title a { color: var(--ink); text-decoration: none; }
    .title a:hover { color: var(--accent); }
    .dek {
      margin: 0 0 10px;
      color: #4d4942;
      font-size: 14px;
      line-height: 1.45;
      max-width: 74rem;
    }
    .meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; color: var(--muted); font-size: 12px; }
    .pill {
      display: inline-flex;
      max-width: 100%;
      min-height: 24px;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 3px 8px;
      color: #4c4942;
      background: #fbfaf6;
      overflow-wrap: anywhere;
    }
    mark { background: rgba(180, 83, 9, .18); color: inherit; border-radius: 4px; padding: 0 2px; }
    .empty { padding: 42px 16px; text-align: center; color: var(--muted); }
    .pager {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 16px;
      border-top: 1px solid var(--line);
    }
    .pager button {
      border: 1px solid var(--line);
      background: var(--surface);
      border-radius: 8px;
      height: 38px;
      padding: 0 14px;
      cursor: pointer;
    }
    .pager button:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
    .pager button:disabled { opacity: .45; cursor: default; }
    .rail { padding: 16px; display: grid; gap: 18px; }
    .rail h3 { margin: 0 0 10px; font-size: 13px; text-transform: uppercase; color: var(--muted); letter-spacing: .08em; }
    .barRow { display: grid; gap: 6px; margin: 10px 0; }
    .barLabel { display: flex; justify-content: space-between; gap: 10px; font-size: 12px; color: #3d3a35; }
    .bar { height: 8px; border-radius: 999px; background: var(--surface-2); overflow: hidden; }
    .bar span { display: block; height: 100%; background: var(--accent); border-radius: inherit; }
    .chipList { display: flex; flex-wrap: wrap; gap: 7px; }
    .chip {
      border: 1px solid var(--line);
      background: #fbfaf6;
      border-radius: 999px;
      padding: 6px 9px;
      font-size: 12px;
      color: #3d3a35;
      cursor: pointer;
    }
    .chip:hover { border-color: var(--accent); color: var(--accent); }
    @media (max-width: 1040px) {
      .app { grid-template-columns: 1fr; }
      .side { position: relative; height: auto; }
      .workspace { grid-template-columns: 1fr; }
    }
    @media (max-width: 760px) {
      main { padding: 16px; }
      .topbar, .summary { grid-template-columns: 1fr; }
      .article { grid-template-columns: 1fr; gap: 8px; }
      .date { white-space: normal; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="side">
      <div class="brand">
        <small>Veille Google News</small>
        <h1>France Ultra Recall</h1>
        <div class="updated" id="updatedAt">Base locale</div>
      </div>
      <div class="sideStats">
        <div class="stat"><div class="num" id="statArticles">0</div><div class="label">articles uniques</div></div>
        <div class="stat"><div class="num" id="statSources">0</div><div class="label">sources distinctes</div></div>
        <div class="stat"><div class="num" id="statMatches">0</div><div class="label">résultats affichés</div></div>
      </div>
      <div class="sideFoot">Dashboard généré automatiquement depuis la base SQLite. Ouvre ce même fichier après chaque relance.</div>
    </aside>
    <main>
      <div class="topbar">
        <div class="searchBox">
          <input id="searchInput" type="search" placeholder="Rechercher un mot clé, une source, un sujet..." autocomplete="off" autofocus>
          <span class="kbd">⌘K</span>
        </div>
        <div class="filterBox">
          <span class="filterIcon" aria-hidden="true">◇</span>
          <select id="sourceFilter"><option value="">Tous les médias</option></select>
        </div>
        <div class="filterBox">
          <span class="filterIcon" aria-hidden="true">◇</span>
          <select id="groupFilter"><option value="">Tous les groupes</option></select>
        </div>
        <select id="sortMode">
          <option value="newest">Plus récents</option>
          <option value="oldest">Plus anciens</option>
          <option value="source">Source A-Z</option>
        </select>
      </div>
      <section class="summary">
        <div class="metric"><b id="metricPeriod">-</b><span>période couverte</span></div>
        <div class="metric"><b id="metricLast">-</b><span>dernier article</span></div>
        <div class="metric"><b id="metricQueries">-</b><span>requêtes lancées</span></div>
        <div class="metric"><b id="metricDb">SQLite</b><span>base active</span></div>
      </section>
      <div class="workspace">
        <section class="panel">
          <div class="panelHead">
            <div><h2>Articles</h2><p id="resultLine">Recherche instantanée dans la base locale</p></div>
          </div>
          <div class="list" id="articleList"><!-- STATIC_ARTICLES --></div>
          <div class="pager">
            <button id="prevBtn">Précédent</button>
            <span id="pageInfo">Page 1</span>
            <button id="nextBtn">Suivant</button>
          </div>
        </section>
        <aside class="rail">
          <section><h3>Top sources</h3><div id="topSources"></div></section>
          <section><h3>Mots rapides</h3><div class="chipList" id="quickTerms"></div></section>
        </aside>
      </div>
    </main>
  </div>
  <script>
    const DATA = window.GN_DASHBOARD_DATA || { stats: {}, articles: [] };
    const articles = DATA.articles || [];
    const stats = DATA.stats || {};
    const fmt = new Intl.NumberFormat('fr-FR');
    const pageSize = 20;
    let page = 1;
    let filtered = [];

    const $ = (id) => document.getElementById(id);
    const norm = (v) => String(v || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const esc = (v) => String(v || '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

    function compactDate(value) {
      if (!value) return '-';
      const [d, t=''] = String(value).split(' ');
      const bits = d.split('-');
      if (bits.length !== 3) return value;
      return `${bits[2]}/${bits[1]}/${bits[0]} ${t.slice(0,5)}`.trim();
    }
    function highlight(text, query) {
      return esc(text);
    }
    function fillBasics() {
      $('statArticles').textContent = fmt.format(stats.total_articles || articles.length);
      $('statSources').textContent = fmt.format(stats.total_sources || 0);
      $('updatedAt').textContent = `Mis à jour le ${compactDate(stats.generated_at || '')}`;
      $('metricPeriod').textContent = stats.first_article && stats.last_article ? `${compactDate(stats.first_article).slice(0,10)} → ${compactDate(stats.last_article).slice(0,10)}` : '-';
      $('metricLast').textContent = compactDate(stats.last_article || '');
      $('metricQueries').textContent = fmt.format(stats.total_attempts || 0);

      const sources = [...new Set(articles.map(a => a.source).filter(Boolean))].sort((a,b) => a.localeCompare(b, 'fr'));
      $('sourceFilter').innerHTML = '<option value="">Tous les médias</option>' + sources.map(s => `<option value="${esc(s)}">${esc(s)}</option>`).join('');
      const groupOrder = ['Presse nationale', 'Presse locale et régionale', 'TV / radio', 'Économie', 'Tech / numérique', 'Médias spécialisés', 'Outre-mer', 'Portails / agrégateurs', 'Autres médias'];
      const groups = [...new Set(articles.map(a => a.media_group || 'Autres médias'))].sort((a,b) => groupOrder.indexOf(a) - groupOrder.indexOf(b));
      $('groupFilter').innerHTML = '<option value="">Tous les groupes</option>' + groups.map(g => `<option value="${esc(g)}">${esc(g)}</option>`).join('');

      const quick = ['politique', 'justice', 'incendie', 'accident', 'santé', 'économie', 'agriculture', 'cyberattaque', 'météo', 'école'];
      $('quickTerms').innerHTML = quick.map(t => `<button class="chip" data-term="${esc(t)}">${esc(t)}</button>`).join('');
      document.querySelectorAll('.chip').forEach(btn => btn.addEventListener('click', () => { $('searchInput').value = btn.dataset.term; page = 1; applyFilters(); }));
    }
    function renderBars() {
      const rows = stats.top_sources || [];
      const max = rows.length ? rows[0].count : 1;
      $('topSources').innerHTML = rows.slice(0, 10).map(r => `
        <div class="barRow">
          <div class="barLabel"><span>${esc(r.source)}</span><b>${fmt.format(r.count)}</b></div>
          <div class="bar"><span style="width:${Math.max(4, Math.round((r.count / max) * 100))}%"></span></div>
        </div>`).join('');
    }
    function applyFilters() {
      const q = norm($('searchInput').value);
      const source = $('sourceFilter').value;
      const group = $('groupFilter').value;
      const sort = $('sortMode').value;
      const terms = q.split(/\s+/).filter(Boolean);
      filtered = articles.filter(a => {
        if (source && a.source !== source) return false;
        if (group && (a.media_group || 'Autres médias') !== group) return false;
        if (!terms.length) return true;
        const hay = norm(`${a.title} ${a.summary || ''} ${a.source} ${a.source_domain} ${a.media_group || ''} ${a.query_kind} ${a.query_label}`);
        return terms.every(t => hay.includes(t));
      });
      filtered.sort((a,b) => {
        if (sort === 'oldest') return String(a.published).localeCompare(String(b.published));
        if (sort === 'source') return String(a.source).localeCompare(String(b.source), 'fr') || String(b.published).localeCompare(String(a.published));
        return String(b.published).localeCompare(String(a.published));
      });
      const maxPage = Math.max(1, Math.ceil(filtered.length / pageSize));
      page = Math.min(page, maxPage);
      renderList();
    }
    function renderList() {
      const q = $('searchInput').value;
      const start = (page - 1) * pageSize;
      const rows = filtered.slice(start, start + pageSize);
      $('statMatches').textContent = fmt.format(filtered.length);
      $('resultLine').textContent = `${fmt.format(filtered.length)} résultat${filtered.length > 1 ? 's' : ''}`;
      if (!rows.length) {
        $('articleList').innerHTML = '<div class="empty">Aucun article ne correspond à cette recherche.</div>';
      } else {
        $('articleList').innerHTML = rows.map(a => `
          <article class="article">
            <div class="date">${compactDate(a.published)}<br>${esc(a.hour || '')}</div>
            <div>
              <h3 class="title"><a href="${esc(a.link)}" target="_blank" rel="noopener noreferrer">${highlight(a.title, q)}</a></h3>
              ${a.summary ? `<p class="dek">${highlight(a.summary, q)}</p>` : ''}
              <div class="meta">
                <span class="pill">${highlight(a.source || 'Source inconnue', q)}</span>
                ${a.source_domain ? `<span>${esc(a.source_domain)}</span>` : ''}
                <span>${esc(a.media_group || 'Autres médias')}</span>
                <span>${esc(a.query_kind || '')}</span>
                <span>${fmt.format(a.occurrences || 1)} apparition${Number(a.occurrences || 1) > 1 ? 's' : ''}</span>
              </div>
            </div>
          </article>`).join('');
      }
      const maxPage = Math.max(1, Math.ceil(filtered.length / pageSize));
      $('pageInfo').textContent = `Page ${page} / ${maxPage}`;
      $('prevBtn').disabled = page <= 1;
      $('nextBtn').disabled = page >= maxPage;
    }
    $('searchInput').addEventListener('input', () => { page = 1; applyFilters(); });
    $('sourceFilter').addEventListener('change', () => { page = 1; applyFilters(); });
    $('groupFilter').addEventListener('change', () => { page = 1; applyFilters(); });
    $('sortMode').addEventListener('change', () => { page = 1; applyFilters(); });
    $('prevBtn').addEventListener('click', () => { page -= 1; renderList(); });
    $('nextBtn').addEventListener('click', () => { page += 1; renderList(); });
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('searchInput').focus(); }
    });
    fillBasics();
    renderBars();
    applyFilters();
  </script>
</body>
</html>
"""


def safe_json_script(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def export_dashboard(conn, out_dir: Path):
    root_dir = out_dir.parent
    generated_at = datetime.now(PARIS_TZ).strftime("%Y-%m-%d %H:%M:%S")
    total_articles = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    total_sources = conn.execute("SELECT COUNT(DISTINCT source) FROM articles").fetchone()[0]
    total_attempts = conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
    first_article, last_article = conn.execute("SELECT MIN(published), MAX(published) FROM articles").fetchone()
    top_sources = [
        {"source": source, "count": count}
        for source, count in conn.execute("""
            SELECT source, COUNT(*) AS n
            FROM articles
            GROUP BY source
            ORDER BY n DESC, source ASC
            LIMIT 12
        """)
    ]
    articles = [
        {
            "published": published,
            "date": date,
            "hour": hour,
            "source": source,
            "source_domain": source_domain,
            "media_group": classify_media_group(source, source_domain),
            "title": title,
            "summary": summary,
            "link": link,
            "occurrences": occurrences,
            "query_kind": query_kind,
            "query_label": query_label,
        }
        for published, date, hour, source, source_domain, title, summary, link, occurrences, query_kind, query_label in conn.execute("""
            SELECT published, date, hour, source, source_domain, title, summary, link,
                   occurrences_in_feeds, first_query_kind, first_query_label
            FROM articles
            ORDER BY published DESC
        """)
    ]
    payload = {
        "stats": {
            "generated_at": generated_at,
            "total_articles": total_articles,
            "total_sources": total_sources,
            "total_attempts": total_attempts,
            "first_article": first_article,
            "last_article": last_article,
            "top_sources": top_sources,
        },
        "articles": articles,
    }

    static_articles = []
    for article in articles[:40]:
        title = html_lib.escape(article.get("title") or "")
        source = html_lib.escape(article.get("source") or "Source inconnue")
        domain = html_lib.escape(article.get("source_domain") or "")
        media_group = html_lib.escape(article.get("media_group") or "Autres médias")
        link = html_lib.escape(article.get("link") or "")
        summary = html_lib.escape(article.get("summary") or "")
        summary_html = f'<p class="dek">{summary}</p>' if summary else ''
        published = html_lib.escape(article.get("published") or "")
        hour = html_lib.escape(article.get("hour") or "")
        static_articles.append(f"""
          <article class="article">
            <div class="date">{published}<br>{hour}</div>
            <div>
              <h3 class="title"><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></h3>
              {summary_html}
              <div class="meta"><span class="pill">{source}</span><span>{domain}</span><span>{media_group}</span></div>
            </div>
          </article>""")
    static_html = "".join(static_articles) or '<div class="empty">Aucun article dans la base.</div>'
    dashboard_html = DASHBOARD_HTML.replace("<!-- STATIC_ARTICLES -->", static_html)
    data_js = "window.GN_DASHBOARD_DATA = " + safe_json_script(payload) + ";\n"
    for target_dir in unique([str(root_dir), str(out_dir)]):
        target = Path(target_dir)
        (target / "dashboard_google_news.html").write_text(dashboard_html, encoding="utf-8")
        (target / "dashboard_google_news_data.js").write_text(data_js, encoding="utf-8")


def export_outputs(conn, out_dir: Path, print_articles: int):
    export_table(
        conn,
        """
        SELECT published, date, hour, source, source_domain, title, summary, link,
               occurrences_in_feeds, first_query_kind, first_query_label,
               first_query_day, all_query_labels
        FROM articles
        ORDER BY published DESC
        """,
        out_dir / "articles_google_news_fr_sans_doublons.csv",
        ["published", "date", "hour", "source", "source_domain", "title", "summary", "link",
         "occurrences_in_feeds", "first_query_kind", "first_query_label",
         "first_query_day", "all_query_labels"]
    )

    export_table(
        conn,
        """
        SELECT source, COUNT(*) AS n
        FROM articles
        GROUP BY source
        ORDER BY n DESC, source ASC
        """,
        out_dir / "comptage_par_source.csv",
        ["source", "count"]
    )

    export_table(
        conn,
        """
        SELECT COALESCE(NULLIF(source_domain,''),'inconnu') AS domain, COUNT(*) AS n
        FROM articles
        GROUP BY domain
        ORDER BY n DESC, domain ASC
        """,
        out_dir / "comptage_par_domaine_source.csv",
        ["source_domain", "count"]
    )

    export_table(
        conn,
        """
        SELECT date, COUNT(*) AS n
        FROM articles
        GROUP BY date
        ORDER BY date ASC
        """,
        out_dir / "comptage_par_jour.csv",
        ["date", "count"]
    )

    export_table(
        conn,
        """
        SELECT first_query_kind, COUNT(*) AS n
        FROM articles
        GROUP BY first_query_kind
        ORDER BY n DESC
        """,
        out_dir / "comptage_par_type_requete.csv",
        ["query_kind", "count"]
    )

    export_table(
        conn,
        """
        SELECT wave, kind, label, base_query, day, date_from, date_to,
               status, raw_entries, kept_before_dedup, error, url, query, finished_at
        FROM attempts
        ORDER BY wave, raw_entries DESC, kind, label
        """,
        out_dir / "debug_requetes.csv",
        ["wave", "kind", "label", "base_query", "day", "date_from", "date_to",
         "status", "raw_entries", "kept_before_dedup", "error", "url", "query", "finished_at"]
    )

    export_table(
        conn,
        """
        SELECT wave, kind, label, base_query, day, date_from, date_to,
               raw_entries, kept_before_dedup, url, query
        FROM attempts
        WHERE raw_entries >= 95
        ORDER BY raw_entries DESC
        """,
        out_dir / "requetes_saturees_a_redecouper.csv",
        ["wave", "kind", "label", "base_query", "day", "date_from", "date_to",
         "raw_entries", "kept_before_dedup", "url", "query"]
    )

    export_dashboard(conn, out_dir)

    # Fichier console-friendly : seulement les N premiers articles si demandé.
    if print_articles > 0:
        export_table(
            conn,
            f"""
            SELECT published, source, title, link
            FROM articles
            ORDER BY published DESC
            LIMIT {int(print_articles)}
            """,
            out_dir / f"apercu_{print_articles}_articles.csv",
            ["published", "source", "title", "link"]
        )


async def async_main(args):
    started_all = time.time()
    now = datetime.now(PARIS_TZ)

    if args.start:
        start_dt = datetime.fromisoformat(args.start).replace(tzinfo=PARIS_TZ)
    else:
        today_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = today_midnight - timedelta(days=max(args.days - 1, 0))

    if args.end:
        end_dt = datetime.fromisoformat(args.end).replace(tzinfo=PARIS_TZ)
    else:
        end_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    root_dir = Path.cwd()
    resumed_from_latest = False
    previous_finished = None

    if args.resume_latest and not args.new_output:
        latest_dir = latest_output_dir(root_dir)
    else:
        latest_dir = None

    if latest_dir:
        out_dir = latest_dir
        db_path = out_dir / "google_news_fr_ultra.sqlite"
        conn = init_db(db_path)
        previous_finished = latest_finished_at(conn)
        if previous_finished:
            resume_start = floor_to_hour(previous_finished) - timedelta(hours=args.repair_last_hours)
            resume_end = floor_to_hour(now)
            if resume_end > resume_start:
                start_dt = resume_start
                end_dt = resume_end
                resumed_from_latest = True
            else:
                start_dt = resume_start
                end_dt = resume_end
                resumed_from_latest = True
        else:
            resumed_from_latest = True
    else:
        out_dir = Path("sortie_google_news_fr_ULTRA_" + now.strftime("%Y%m%d_%H%M%S"))
        out_dir.mkdir(exist_ok=True)
        db_path = out_dir / "google_news_fr_ultra.sqlite"
        conn = init_db(db_path)

    if args.backfill_summaries_only:
        print("\nMode rattrapage résumés uniquement")
        await run_summary_backfill(conn, args)
        export_outputs(conn, out_dir, args.print_articles)
        print(f"Dashboard régénéré : {(out_dir.parent / 'dashboard_google_news.html').resolve()}")
        conn.close()
        return

    if resumed_from_latest and end_dt <= start_dt:
        queries = []
    else:
        queries = build_queries(args, start_dt, end_dt, wave=1, exact_window=resumed_from_latest)
        insert_query_plan(conn, queries)

    print("\n" + "=" * 92)
    print("GOOGLE NEWS FR - ULTRA RECALL SQLITE")
    print("=" * 92)
    print(f"Période          : {start_dt:%Y-%m-%d %H:%M} -> {end_dt:%Y-%m-%d %H:%M} Europe/Paris")
    if resumed_from_latest:
        print("Relance          : incrémentale, sur la dernière base existante")
        if previous_finished:
            print(f"Dernier passage  : {previous_finished:%Y-%m-%d %H:%M} Europe/Paris")
    else:
        print("Relance          : nouvelle base")
    print(f"Mode             : {args.mode}")
    print(f"Requêtes vague 1 : {len(queries)}")
    print(f"Concurrence      : {args.concurrency}")
    print(f"Console          : résumé seulement, pas de listing article par article")
    print(f"Base SQLite      : {db_path.resolve()}")
    print("=" * 92)

    existing_urls = {q["url"] for q in queries}

    if not queries:
        print("\nAucun nouveau créneau horaire complet à collecter pour l'instant.")
        attempts_wave1 = []
        adaptive_queries = []
    else:
        attempts_wave1 = await run_wave(conn, queries, args, start_dt, end_dt, "Vague 1")

        saturated = [a for a in attempts_wave1 if a.get("raw_entries", 0) >= args.saturation_threshold and not a.get("error")]
        print(f"\nRequêtes saturées vague 1 >= {args.saturation_threshold}: {len(saturated)}")

        if args.adaptive and saturated:
            adaptive_queries = build_adaptive_queries(saturated, args, existing_urls)
            insert_query_plan(conn, adaptive_queries)
            print(f"Requêtes adaptatives générées: {len(adaptive_queries)}")
            await run_wave(conn, adaptive_queries, args, start_dt, end_dt, "Vague 2 adaptative")
        else:
            adaptive_queries = []

    await run_summary_backfill(conn, args)

    export_outputs(conn, out_dir, args.print_articles)

    total_unique = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    raw_total = conn.execute("SELECT COALESCE(SUM(raw_entries),0) FROM attempts").fetchone()[0]
    kept_total = conn.execute("SELECT COALESCE(SUM(kept_before_dedup),0) FROM attempts").fetchone()[0]
    sources = conn.execute("SELECT COUNT(DISTINCT source) FROM articles").fetchone()[0]
    saturated_total = conn.execute("SELECT COUNT(*) FROM attempts WHERE raw_entries >= ?", (args.saturation_threshold,)).fetchone()[0]

    print("\n" + "=" * 92)
    print("RÉSULTATS FINAUX")
    print("=" * 92)
    print(f"Temps total              : {time.time() - started_all:.1f}s")
    print(f"Entrées RSS brutes        : {raw_total}")
    print(f"Articles avant dédup      : {kept_total}")
    print(f"Articles SANS DOUBLONS    : {total_unique}")
    print(f"Doublons supprimés approx.: {max(0, kept_total - total_unique)}")
    print(f"Sources distinctes        : {sources}")
    print(f"Requêtes saturées total   : {saturated_total}")
    print(f"Dossier sortie            : {out_dir.resolve()}")
    print(f"CSV principal             : {(out_dir / 'articles_google_news_fr_sans_doublons.csv').resolve()}")
    print("=" * 92)

    print("\nTOP 30 SOURCES")
    for source, count in conn.execute("""
        SELECT source, COUNT(*) AS n
        FROM articles
        GROUP BY source
        ORDER BY n DESC
        LIMIT 30
    """):
        print(f"  {source}: {count}")

    print("\nFichiers utiles créés :")
    print("  - articles_google_news_fr_sans_doublons.csv")
    print("  - comptage_par_source.csv")
    print("  - comptage_par_jour.csv")
    print("  - debug_requetes.csv")
    print("  - requetes_saturees_a_redecouper.csv")
    print("  - google_news_fr_ultra.sqlite")
    print("  - dashboard_google_news.html")

    conn.close()


def parse_args():
    p = argparse.ArgumentParser(description="Google News France - ULTRA recall SQLite sans doublons")
    p.add_argument("--query", default=None, help='Sujet ciblé, ex: "agriculture OR pesticides"')
    p.add_argument("--days", type=int, default=2, help="Nombre de jours calendaires. 2 = depuis minuit hier.")
    p.add_argument("--start", default=None, help="Date début YYYY-MM-DD. Remplace --days.")
    p.add_argument("--end", default=None, help="Date fin exclusive YYYY-MM-DD. Défaut demain 00:00.")
    p.add_argument("--mode", choices=["balanced", "aggressive", "ultra"], default="ultra")
    p.add_argument("--concurrency", type=int, default=50, help="Requêtes simultanées.")
    p.add_argument("--retries", type=int, default=2)
    p.add_argument("--timeout", type=int, default=20)
    p.add_argument("--commit-every", type=int, default=100)
    p.add_argument("--progress-every", type=int, default=100, help="Affichage console toutes les N requêtes.")
    p.add_argument("--max-queries", type=int, default=0, help="Limiter la vague 1 pour test.")
    p.add_argument("--domains-file", default="medias_domains.txt")
    p.add_argument("--no-domain-search", dest="domain_search", action="store_false")
    p.add_argument("--no-topics", dest="include_topics", action="store_false")
    p.add_argument("--lang-filter", action="store_true", help="Active langdetect. Plus strict mais plus lent.")
    p.add_argument("--no-adaptive", dest="adaptive", action="store_false")
    p.add_argument("--saturation-threshold", type=int, default=95)
    p.add_argument("--adaptive-splitters-per-query", type=int, default=10)
    p.add_argument("--max-adaptive-queries", type=int, default=2500)
    p.add_argument("--no-local-combos", dest="local_combos", action="store_false")
    p.add_argument("--combo-geo-limit", type=int, default=90)
    p.add_argument("--combo-event-limit", type=int, default=28)
    p.add_argument("--print-articles", type=int, default=0, help="0 = ne rien lister dans la console.")
    p.add_argument("--no-summary-backfill", dest="summary_backfill", action="store_false", help="Ne tente pas de compléter les résumés manquants sur les anciens articles.")
    p.add_argument("--summary-backfill-limit", type=int, default=1200, help="Nombre max d'anciennes requêtes à relire pour compléter les résumés.")
    p.add_argument("--backfill-summaries-only", action="store_true", help="Complète seulement les résumés puis régénère les exports.")
    p.add_argument("--no-resume-latest", dest="resume_latest", action="store_false", help="Ne reprend pas la dernière base existante.")
    p.add_argument("--repair-last-hours", type=int, default=24, help="À chaque relance, rescanner aussi les N dernières heures complètes pour repêcher les trous sans doublons.")
    p.add_argument("--new-output", action="store_true", help="Force la création d'un nouveau dossier de sortie.")
    p.set_defaults(domain_search=True, include_topics=True, adaptive=True, local_combos=True, resume_latest=True, summary_backfill=True)

    args = p.parse_args()

    if args.concurrency < 1:
        args.concurrency = 1
    if args.concurrency > 100:
        print("Concurrence >100 trop agressive : je force à 100.")
        args.concurrency = 100
    if args.progress_every < 10:
        args.progress_every = 10
    if args.repair_last_hours < 0:
        args.repair_last_hours = 0
    return args


def main():
    args = parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()



