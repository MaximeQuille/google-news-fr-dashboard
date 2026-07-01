# Migration Supabase gratuite

Objectif : ne plus stocker la grosse base SQLite dans GitHub Pages.

## Ce que Supabase va stocker

- `articles` : tous les articles, résumés, médias, groupes.
- `attempts` : historique technique utile pour reprendre la collecte.

Le site GitHub Pages reste gratuit, mais il lit maintenant les données depuis Supabase.

## Étape 1 - Créer le projet Supabase

1. Va sur https://supabase.com
2. Crée un compte ou connecte-toi.
3. Clique `New project`.
4. Nom conseillé : `google-news-fr-dashboard`.
5. Choisis la région Europe si disponible.
6. Garde le plan Free.
7. Attends que le projet soit prêt.

## Étape 2 - Créer les tables

1. Dans Supabase, ouvre ton projet.
2. Va dans `SQL Editor`.
3. Clique `New query`.
4. Colle tout le contenu du fichier `supabase/schema.sql`.
5. Clique `Run`.

## Étape 3 - Récupérer les clés

Dans Supabase : `Project Settings` -> `API`.

Il faut :

- `Project URL`
- `anon public` key
- `service_role` key

Attention : `service_role` est secret. Ne jamais le publier dans le code.

## Étape 4 - Ajouter les secrets GitHub

Dans le repo GitHub :

`Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

Ajoute ces 3 secrets :

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

## Étape 5 - Migrer la base actuelle

Sur ton Mac, depuis ce dossier :

```bash
cd /Users/maxime/Desktop/Google_News_FR_ULTRA_Mac_sans_Vietnam
export SUPABASE_URL="https://TON-PROJET.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="TA_SERVICE_ROLE_KEY"
python3 -m pip install -r requirements.txt
python3 scripts/supabase_sync.py push --db sortie_google_news_fr_ULTRA_20260701_125402/google_news_fr_ultra.sqlite
```

## Étape 6 - Pousser le nouveau code GitHub

```bash
git add .
git commit -m "Migrate dashboard storage to Supabase"
git push
```

## Étape 7 - Tester le workflow

Dans GitHub : `Actions` -> `Update Google News dashboard hourly` -> `Run workflow`.

Si tout est vert, la mise à jour horaire tourne via Supabase et GitHub Pages ne contient plus la grosse base SQLite.

## Migration des alertes vers Supabase

Les alertes email ne dépendent plus d'un cron GitHub toutes les 5 minutes. La logique fiable est maintenant dans la Edge Function Supabase `process-alerts`.

### Secrets à ajouter dans GitHub

Dans GitHub : `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`.

Ajoute :

- `SUPABASE_ACCESS_TOKEN` : token personnel Supabase pour déployer la fonction.
- `RESEND_API_KEY` : clé API Resend pour envoyer les emails.
- `ALERT_CRON_SECRET` : long mot de passe aléatoire, identique à celui utilisé dans `supabase/schedule_alerts.sql`.
- `ALERT_EMAIL_FROM` : expéditeur email, par exemple `Google News FR <alertes@ton-domaine.fr>`.

Les secrets déjà présents restent nécessaires :

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`

### Déploiement

Après ajout des secrets, pousse le code sur GitHub ou lance manuellement :

`Actions` -> `Deploy Supabase functions` -> `Run workflow`.

### Cron Supabase

Dans Supabase : `SQL Editor` -> `New query`.

1. Ouvre `supabase/schedule_alerts.sql`.
2. Remplace `YOUR_SUPABASE_ANON_KEY`.
3. Remplace `CHANGE_ME_LONG_RANDOM_SECRET` par la même valeur que `ALERT_CRON_SECRET`.
4. Clique `Run`.

Supabase appellera ensuite la fonction toutes les 5 minutes. Les emails horaires restent envoyés sur des fenêtres propres et complètes, par exemple 14:00 -> 15:00, seulement quand les articles de cette période sont bien arrivés en base.
