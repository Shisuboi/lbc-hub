# LBC Hub — Check-list de tests Phase 1

Tous les tests à dérouler **dans l'ordre** après un `git pull`. Si une étape casse, stop et debug avant de continuer.

---

## 0. Setup machine

```bash
cd lbc-hub
pip install -r requirements.txt
```

- [ ] Pip s'installe sans erreur (playwright, aiohttp, pytest, pytest-asyncio, pytest-aiohttp)
- [ ] `playwright install chromium` si jamais fait sur cette machine

---

## 1. Préalables Supabase (Dashboard manuel)

Aller sur https://supabase.com/dashboard/project/pfkuphmpzhdmfwaifywj

- [ ] **Auth → Providers → Email**
  - "Enable Email provider" : **ON**
  - "Enable email signups" : **OFF** (les signups passent uniquement par les invitations)
- [ ] **Auth → URL Configuration**
  - Site URL = `http://localhost:8080` (pour tester en dev)
  - Redirect URLs contient : `http://localhost:8080/**` + `https://shisuboi.github.io/lbc-hub/**`
- [ ] **Auth → Users → tristanfranceschetti@gmail.com → Edit user**
  - Définir un mdp (ou demander un magic link via "Send magic link")
- [ ] **Database → Replication**
  - Cocher la table `public.searches` (sinon Realtime ne marchera pas)

---

## 2. Tests pytest backend

```bash
python -m pytest tests/ -v
```

- [ ] 3 tests passent : `test_ping_returns_ok`, `test_cors_headers_on_get`, `test_cors_preflight_options`

---

## 3. Lancer le serveur

```bash
python server.py
```

- [ ] Affiche "✨ Le serveur Leboncoin Scraper & IA est lancé !"
- [ ] `curl http://localhost:8080/api/ping` renvoie `{"status":"ok"}`

---

## 4. Tests Section 4 — Pages auth

Ouvrir Chrome / Edge sur `http://localhost:8080/`

- [ ] Page login s'affiche (titre "Connexion", formulaire email + mdp)
- [ ] Login avec ton compte admin → redirige vers `/hub`
  - Le `/hub` plantera si la DB n'a pas encore de search — c'est OK, on charge des données à l'étape 5

---

## 5. Tests Section 5 — Page /hub feed

### Préparer données dans SQL Editor Supabase

```sql
-- Recherche de test (notez l'id retourné)
insert into public.searches(user_id, title, criteria, source_url, platform, model_name, model_type, listing_count, best_score, min_price, scraped_at)
values (
  (select id from public.profiles where username = 'tristan'),
  'Test : laptops gaming', 'RTX 4060, 16Go, < 800€',
  'https://www.leboncoin.fr/recherche?text=laptop', 'leboncoin',
  'claude-3.5-sonnet', 'cloud', 2, 88, 750,
  now() - interval '2 hours'
) returning id;
```

```sql
-- Listings (remplacer <SEARCH_ID> par l'id retourné ci-dessus)
insert into public.listings(search_id, titre, prix, url, note_sur_100, caracteristiques, explication, match_criteres)
values
  ('<SEARCH_ID>'::uuid, 'MSI Katana 15 — RTX 4060', 750, 'https://example.com/1', 88, 'i7-13620H, RTX 4060, 16Go RAM, SSD 512Go', 'Excellent rapport qualité/prix', true),
  ('<SEARCH_ID>'::uuid, 'Lenovo Legion 5 Pro', 1200, 'https://example.com/2', 72, 'Ryzen 7, RTX 4070, 32Go', 'Très bon mais cher', false);
```

### Vérifications visuelles

Sur `http://localhost:8080/hub` :

- [ ] Carte avec bandeau **violet** ✨ (modèle cloud)
- [ ] Badge 🟠 LBC
- [ ] Date relative "il y a 2 h"
- [ ] Badges : "2 annonces", "⭐ 88/100", "💰 750 €"
- [ ] Avatar coloré + pseudo `@tristan`

### Test Realtime (deux onglets)

- Onglet A : `/hub` ouvert
- Onglet B : SQL Editor, exécuter une 2e insertion search :

```sql
insert into public.searches(user_id, title, criteria, source_url, platform, model_name, model_type, listing_count, best_score, min_price, scraped_at)
values (
  (select id from public.profiles where username = 'tristan'),
  'Realtime test', '', null, 'leboncoin', 'gemma3:4b', 'local', 5, 72, 200,
  now()
);
```

- [ ] La nouvelle carte apparaît en haut de l'onglet A **sans refresh** (animation slideIn, bandeau gris pour modèle local)

---

## 6. Tests Section 6 — Page /search/:id

- [ ] Click sur la carte du feed → navigue vers `/search/<id>`
- [ ] Header avec bandeau violet, auteur + plateforme + date "scrapé le …"
- [ ] 2 listing-cards (MSI ✅ 88, Lenovo ⚠️ 72)
- [ ] Filtre texte `MSI` → 1 / 2 annonces (compteur en haut à droite)
- [ ] Score ≥ 75 → masque Lenovo (72)
- [ ] Tri prix croissant → MSI (750 €) avant Lenovo (1200 €)
- [ ] Bouton "← Retour au hub" → revient sur `/hub` **sans refresh** (SPA)

---

## 7. Tests Section 7 — Scraper + Publish

### Test 7a — Scrape live (Ollama requis)

- [ ] Lancer Ollama localement (`ollama serve` ou app desktop)
- [ ] Aller sur `http://localhost:8080/scraper`
- [ ] Banner "Serveur local non détecté" → **absent** (puisqu'on est sur localhost)
- [ ] Liste des modèles Ollama se charge dans le select
- [ ] Saisir une URL LBC légère + critères + modèle léger (qwen2.5:0.5b)
- [ ] Cliquer "Lancer l'Analyse" → suivre les logs en console
- [ ] À la fin (status `completed`) → zone "📤 Publier sur le hub" apparaît
- [ ] Saisir titre "Test publish local" + cliquer Publier
- [ ] Status doit afficher "✅ Publiée ! Voir la recherche"
- [ ] Click le lien → `/search/<id>` avec les bonnes annonces
- [ ] Retour `/hub` → la carte est en haut du feed

### Test 7b — Import JSON

- [ ] Sur `/scraper`, cliquer "📥 Importer résultats IA (JSON)"
- [ ] Choisir le fichier `leboncoin_ia_imported.json` du repo
- [ ] Les résultats s'affichent dans la vue
- [ ] Saisir titre "Test import publish" + cliquer Publier
- [ ] Vérifier dans Supabase Table Editor : `searches.model_type = 'cloud'` (inferModelType l'a déduit)
- [ ] Vérifier sur `/hub` que la carte apparaît

### Vérifications DB (Supabase Table Editor)

- [ ] Table `searches` : `platform = 'leboncoin'`, `scraped_at` rempli, `source_url` rempli si scrape live
- [ ] Table `listings` : `match_criteres` boolean, `note_sur_100` float

---

## 8. Tests Section 8 — Page /install

- [ ] `http://localhost:8080/install` → guide avec 6 étapes numérotées (badges violets)
- [ ] Encadré jaune "Note pour Firefox / Safari" visible
- [ ] Lien "← Retour à la connexion" → vers `/`

⚠️ Le bouton "Télécharger" pointe vers un placeholder (`REMPLACER_PAR_LIEN`). Sera mis à jour à la Task 9.4 (création + upload ZIP).

---

## 9. Tests Section 9 — Déploiement GitHub Pages

### Préalable côté GitHub
- [ ] Vérifier sur https://github.com/Shisuboi/lbc-hub/settings/pages :
  - Source = **GitHub Actions**

### Trigger du déploiement
- [ ] Le workflow `.github/workflows/deploy.yml` se déclenche sur push de `feature/hub-phase1`
- [ ] Aller sur https://github.com/Shisuboi/lbc-hub/actions → le run doit passer en vert (~1 min)

### Tests sur l'URL prod

⚠️ **Avant ça : remettre Site URL Supabase = `https://shisuboi.github.io/lbc-hub`**

- [ ] Aller sur https://shisuboi.github.io/lbc-hub/ → page login
- [ ] Login admin → arrive sur `/lbc-hub/hub` (URL préfixée)
- [ ] Click sur une card → `/lbc-hub/search/<id>`
- [ ] **F5 sur `/lbc-hub/search/<id>`** → page se recharge correctement (via 404.html fallback)
- [ ] Naviguer vers `/lbc-hub/scraper` avec `server.py` lancé localement → ping doit fonctionner (CORS + PNA via Chrome/Edge)

---

## 10. Task 9.4 — ZIP de distribution

```powershell
mkdir release\lbc-dealfinder
copy server.py release\lbc-dealfinder\
copy requirements.txt release\lbc-dealfinder\
copy install.bat release\lbc-dealfinder\
copy install.sh release\lbc-dealfinder\
copy README-rapide.txt release\lbc-dealfinder\
Compress-Archive -Path release\lbc-dealfinder\* -DestinationPath release\lbc-dealfinder.zip -Force
```

- [ ] Upload `release/lbc-dealfinder.zip` sur Google Drive
- [ ] Click droit → Partager → "Anyone with the link" → "Viewer"
- [ ] Copier le lien
- [ ] Remplacer `https://drive.google.com/REMPLACER_PAR_LIEN` dans `js/pages/install.js` (ligne 5) par le lien réel
- [ ] Commit + push → workflow redéploie auto

---

## 11. Test E2E final (deux comptes, depuis l'URL prod)

### Préparer un user secondaire
1. Supabase Dashboard → Auth → Users → "Add user" : `ami@example.com` + mdp temporaire
2. SQL Editor :
   ```sql
   insert into public.invitations(created_by)
   values ((select id from public.profiles where username = 'tristan'))
   returning token;
   ```
3. Récupérer le token retourné

### Flow d'invitation
- [ ] Ouvrir un navigateur privé / autre profil Chrome
- [ ] Aller sur `https://shisuboi.github.io/lbc-hub/invite/<TOKEN>`
- [ ] Redirige vers `/` (login) avec token en sessionStorage
- [ ] Login avec les creds du user secondaire → redirige vers `/invite/<TOKEN>`
- [ ] Choisir un pseudo "alex_42" → arrive sur `/hub`

### Realtime cross-user
- [ ] Onglet admin (chrome principal) sur `/hub`
- [ ] User secondaire publie une recherche depuis son `/scraper`
- [ ] Onglet admin doit voir la nouvelle carte apparaître **sans refresh**
- [ ] Admin clique la carte → voit les listings du user secondaire

---

## 12. Tag de version

Si tous les tests ci-dessus passent :

```bash
git checkout master
git merge feature/hub-phase1
git push
git tag v1.0.0-phase1
git push --tags
```

🎉 Phase 1 livrée.

---

## Notes & troubleshooting

- **Erreur CORS sur localhost** : vérifier que `server.py` tourne et que `Access-Control-Allow-Private-Network: true` est dans les headers (test : `curl -i http://localhost:8080/api/ping`)
- **Login refusé** : vérifier que "Enable Email provider" est ON dans Supabase Auth
- **Realtime ne marche pas** : Database → Replication → cocher `public.searches`
- **404 sur `/hub` après refresh en prod** : 404.html doit être présent à la racine de GitHub Pages
- **Le scraper ne charge pas les modèles Ollama** : Ollama doit être lancé (`ollama serve`)
