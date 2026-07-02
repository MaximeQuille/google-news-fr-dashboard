# Migration VPS fiable

Objectif: garder le site GitHub Pages actuel, mais sortir le moteur horaire de GitHub Actions.

Le VPS execute:
- collecte Google News toutes les heures;
- rattrapage automatique des dernieres 24h;
- push Supabase;
- traitement des alertes;
- envoi Gmail de la file email;
- publication GitHub Pages.

## Choix recommande

Oracle Cloud Always Free si tu veux gratuit. OVH VPS si tu veux plus simple et payant.

## Etapes cote serveur

1. Creer un VPS Ubuntu 24.04.
2. Se connecter en SSH.
3. Installer le projet:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/MaximeQuille/google-news-fr-dashboard.git /tmp/google-news-fr-dashboard
cd /tmp/google-news-fr-dashboard
sudo bash ops/vps/bootstrap.sh
```

4. Remplir les secrets:

```bash
sudo nano /opt/google-news-fr/.env
```

5. Tester une execution manuelle:

```bash
sudo -u google-news /opt/google-news-fr/app/ops/vps/run_hourly.sh
```

6. Activer les timers:

```bash
sudo systemctl enable --now google-news-collect.timer google-news-email-queue.timer
```

7. Verifier:

```bash
sudo /opt/google-news-fr/app/ops/vps/status.sh
```

## Horaires

Le timer principal tourne vers `HH:07`, avec un leger delai aleatoire. Si le serveur etait eteint, `Persistent=true` rattrape au redemarrage.

Le timer email tourne toutes les 5 minutes pour vider la file Gmail.

## Secrets necessaires

Dans `/opt/google-news-fr/.env`:

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ALERT_CRON_SECRET`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM`
- `GITHUB_REPOSITORY`
- `GITHUB_TOKEN`

`GITHUB_TOKEN` doit etre un token GitHub avec droit d'ecriture sur le repo pour pousser `gh-pages`.

## Logs

Les logs sont dans:

```bash
/var/log/google-news-fr/
```

Etat rapide:

```bash
cat /opt/google-news-fr/state/health.json
```

## Pendant la transition

On peut garder GitHub Actions actif quelques heures, mais idealement on desactive ensuite `Update Google News dashboard hourly` pour eviter deux moteurs en parallele. GitHub Pages reste le site public.
