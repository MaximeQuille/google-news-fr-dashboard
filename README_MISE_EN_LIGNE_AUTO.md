# Mise en ligne automatique gratuite

Objectif : faire tourner la collecte même quand le Mac est éteint.

Le montage préparé ici utilise :

- GitHub Actions : lance la collecte toutes les heures dans le cloud.
- GitHub Pages : héberge le dashboard HTML gratuitement.
- Branche `gh-pages` : contient uniquement le site publié et la dernière base SQLite utile pour reprendre la collecte.

## Étape 1 - Créer le repo GitHub

1. Va sur https://github.com/new
2. Nom conseillé : `google-news-fr-dashboard`
3. Mets le repo en `Public` si tu veux rester dans le plus gratuit/simple.
4. Ne coche pas README/gitignore/license si GitHub te le demande.
5. Crée le repo.

## Étape 2 - Envoyer le code principal

Dans Terminal, depuis ce dossier :

```bash
cd /Users/maxime/Desktop/Google_News_FR_ULTRA_Mac_sans_Vietnam
git init
git checkout -B main
git add google_news_fr_ultra_sqlite.py medias_domains.txt requirements.txt .gitignore .github scripts README_MISE_EN_LIGNE_AUTO.md
git commit -m "Prepare cloud hourly dashboard"
git remote add origin https://github.com/TON_USER/google-news-fr-dashboard.git
git push -u origin main
```

Remplace `TON_USER` par ton pseudo GitHub.

## Étape 3 - Publier la base actuelle une première fois

Toujours dans Terminal :

```bash
cd /Users/maxime/Desktop/Google_News_FR_ULTRA_Mac_sans_Vietnam
scripts/publish_current_to_github_pages.sh TON_USER/google-news-fr-dashboard
```

Ça pousse `index.html`, `dashboard_google_news_data.js` et `state/google_news_fr_ultra.sqlite` dans la branche `gh-pages`.

## Étape 4 - Activer GitHub Pages

1. Ouvre ton repo GitHub.
2. Va dans `Settings` -> `Pages`.
3. Source : `Deploy from a branch`.
4. Branch : `gh-pages`, dossier `/ (root)`.
5. Sauvegarde.

Après quelques minutes, ton site sera disponible sur une URL du style :

```text
https://TON_USER.github.io/google-news-fr-dashboard/
```

## Étape 5 - Vérifier l'automatisation

Dans GitHub :

1. Va dans l'onglet `Actions`.
2. Ouvre `Update Google News dashboard hourly`.
3. Clique `Run workflow` pour tester tout de suite.
4. Ensuite, GitHub le lancera automatiquement toutes les heures à la minute 17.

## Notes importantes

- Les horaires GitHub Actions sont en UTC et peuvent avoir quelques minutes de retard.
- Le site sera public si le repo est public.
- Le fichier de données et la base SQLite seront aussi publics.
- La branche `gh-pages` est réécrite à chaque publication pour éviter que l'historique grossisse trop vite.
- Si GitHub désactive les workflows après une longue inactivité du repo public, il faudra les réactiver dans l'onglet Actions.
