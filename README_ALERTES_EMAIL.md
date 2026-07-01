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
5. Pour un nouveau filtre, il envoie une seule fois un mail de test avec les articles qui auraient correspondu sur la dernière heure disponible.
6. Ensuite il envoie un email si de nouveaux articles correspondent.
7. Il mémorise les articles envoyés pour éviter les doublons.

## 4. Gestion depuis le dashboard

Les alertes créées depuis le dashboard sont associées à un jeton privé stocké dans le navigateur. Le site peut donc afficher, demander un test et supprimer les alertes créées depuis ce même navigateur sans exposer les emails publiquement.

Le bouton de test ajoute une demande traitée par un workflow dédié toutes les 5 minutes environ. GitHub Pages ne peut pas envoyer un email directement sans exposer les secrets SMTP.
