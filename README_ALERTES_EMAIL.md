# Alertes email automatiques

Cette extension ajoute un onglet `Alertes email` au dashboard public.

## 1. SQL Supabase

Dans Supabase > SQL Editor > New query, coller et lancer `supabase/alerts.sql`.

Ce SQL crée:
- `alert_filters`: filtres créés depuis le site public.
- `alert_deliveries`: historique privé pour éviter les doublons.

Le site public peut seulement créer une alerte. Il ne peut pas lire les emails enregistrés.

## 2. Secrets GitHub pour l'envoi email

Dans GitHub > Settings > Secrets and variables > Actions > New repository secret, ajouter:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `SMTP_FROM` optionnel

Exemple Gmail:
- `SMTP_HOST`: `smtp.gmail.com`
- `SMTP_PORT`: `587`
- `SMTP_USERNAME`: l'adresse Gmail
- `SMTP_PASSWORD`: mot de passe d'application Gmail
- `SMTP_FROM`: l'adresse d'envoi

Sans ces secrets, le workflow continue de fonctionner mais ignore simplement l'envoi des alertes.

## 3. Fonctionnement

À chaque passage horaire:
1. GitHub Actions récupère l'état Supabase.
2. Le script collecte les nouveaux articles.
3. La base Supabase est mise à jour.
4. `scripts/send_alert_emails.py` cherche les filtres actifs.
5. Il envoie un email si de nouveaux articles correspondent.
6. Il mémorise les articles envoyés pour éviter les doublons.
