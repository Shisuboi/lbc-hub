# LBC DealFinder Hub — Design Spec
**Date :** 26 mai 2026  
**Statut :** Approuvé pour implémentation

---

## 1. Vision

Transformer LBC DealFinder AI (outil local mono-utilisateur) en une **plateforme communautaire privée** où un groupe d'amis partage ses recherches Leboncoin analysées par IA. Chaque utilisateur scrape en local, publie ses résultats sur un hub hébergé, et tout le monde peut consulter les meilleures affaires trouvées par le groupe.

**Principe fondamental :** le scraping reste toujours local (Playwright est indétectable depuis une vraie machine, pas depuis un serveur). Le hub hébergé ne scrape jamais lui-même.

---

## 2. Architecture

```
[Machine utilisateur]
  ├── Navigateur → ouvre lbcdeals.fr (frontend hébergé)
  │     ├── Hub / Feed (lecture seule, pas besoin du serveur local)
  │     ├── Scraper (nécessite server.py local sur :8080)
  │     └── Import JSON Claude.ai (workflow existant)
  └── server.py (Python local, port 8080)
        ├── Playwright scraping + Ollama
        ├── Headers CORS + Access-Control-Allow-Private-Network: true  ← CRITIQUE
        └── Endpoint POST /api/publish → pousse vers Supabase

[Supabase — hébergé, gratuit]
  ├── Auth (email + password, invitations uniquement)
  ├── PostgreSQL (users, searches, listings)
  └── Realtime (feed mis à jour sans refresh)

[Frontend hébergé — GitHub Pages ou Vercel, gratuit]
  └── HTML/CSS/JS statique connecté à Supabase via SDK JS
```

### Point critique CORS
Le frontend HTTPS appelle `http://localhost:8080`. Le navigateur bloque les mixed-content par défaut. Solution : `server.py` doit renvoyer les headers suivants sur **toutes** ses réponses :
```
Access-Control-Allow-Origin: https://lbcdeals.fr (ou * en dev)
Access-Control-Allow-Private-Network: true
```
Sans ces headers, le bouton Scraper ne fonctionnera jamais depuis le site hébergé.

---

## 3. Stack technique

| Composant | Technologie | Coût |
|---|---|---|
| Frontend | HTML/CSS/JS (existant adapté) | Gratuit |
| Hébergement frontend | GitHub Pages ou Vercel | Gratuit |
| Auth + Base de données | Supabase (PostgreSQL) | Gratuit (free tier) |
| Temps réel | Supabase Realtime | Inclus |
| Scraper local | Python + Playwright + aiohttp (existant) | Gratuit |
| IA locale | Ollama (existant) | Gratuit |
| IA cloud | Claude.ai (import JSON manuel, existant) | Abonnement utilisateur |

---

## 4. Pages & Navigation

### Accessibles sans compte
- `/` — Page de connexion (redirect si non connecté)
- `/install` — Guide d'installation (accessible publiquement pour les amis)
- `/invite/:token` — Création de compte via lien d'invitation

### Accessibles avec compte
- `/hub` — Feed principal (page d'accueil après connexion)
- `/search/:id` — Page dédiée d'une recherche (URL partageable)
- `/profile/:username` — Historique des recherches d'un utilisateur
- `/scraper` — L'outil de scraping (outil actuel adapté)

### Admin uniquement (rôle `admin` dans Supabase)
- `/admin` — Gérer les utilisateurs, générer des invitations, supprimer des recherches

---

## 5. Modèle de données

### Table `users` (gérée par Supabase Auth)
```sql
id          uuid PRIMARY KEY
email       text UNIQUE
username    text UNIQUE        -- pseudo affiché (@alex)
avatar_color text              -- couleur générée à l'inscription
role        text DEFAULT 'user' -- 'user' | 'admin'
created_at  timestamptz
```

### Table `searches`
```sql
id           uuid PRIMARY KEY
user_id      uuid REFERENCES users(id)
title        text               -- "Laptops gaming RTX 4060"
criteria     text               -- critères saisis par l'utilisateur
url_lbc      text               -- URL de recherche Leboncoin d'origine
model_name   text               -- "Claude 3.5 Sonnet" | "gemma3:4b" | etc.
model_type   text               -- 'cloud' | 'local'
listing_count int
best_score   float
min_price    float
created_at   timestamptz
```

### Table `listings`
```sql
id             uuid PRIMARY KEY
search_id      uuid REFERENCES searches(id) ON DELETE CASCADE
titre          text
prix           float
url            text
note_sur_100   float
caracteristiques text
explication    text
match_criteres boolean
created_at     timestamptz
```

---

## 6. Flux principaux

### Flux A — Scrape local → publication
1. Utilisateur ouvre `/scraper` (connecté)
2. Le frontend tente un `GET http://localhost:8080/api/ping` — si réponse OK, le bouton "Lancer l'analyse" est actif ; sinon, un bandeau "Démarrez server.py" s'affiche
3. Scraping + analyse IA se déroulent normalement (workflow existant)
4. À la fin, un bouton **"📤 Publier sur le hub"** apparaît
5. L'utilisateur saisit un titre court (ex: "Laptops gaming RTX 4060") — optionnel, un titre auto est généré sinon
6. Le frontend a déjà tous les résultats en mémoire (dans `allResults`, rempli via SSE). L'utilisateur clique "Publier" → le frontend appelle le **SDK Supabase JS directement** avec le JWT de session pour insérer dans `searches` puis `listings`. `server.py` n'intervient pas dans cette étape.
7. La recherche apparaît dans le feed en temps réel pour tous

### Flux B — Import JSON Claude.ai → publication
1. Utilisateur ouvre `/scraper`
2. Clique "📥 Importer résultats IA (JSON)" (workflow existant)
3. Sélectionne son fichier JSON → résultats affichés
4. Bouton **"📤 Publier sur le hub"** disponible immédiatement (server.py non nécessaire pour ce flux)
5. Même étape de titre puis push Supabase via SDK JS

### Flux C — Consultation hub
1. Utilisateur ouvre `/hub`
2. Feed chronologique des recherches, temps réel via Supabase Realtime
3. Tri disponible : **Récent** (défaut) / **Meilleure note globale** / **Prix le plus bas**
4. Clic sur une carte → navigation vers `/search/:id`
5. Page de recherche : toutes les annonces notées, filtres (note min, recherche texte), tri local

---

## 7. Design des cartes du feed

Bandeau coloré en haut de chaque carte pour signaler immédiatement le type de modèle IA :

- **Bandeau violet** (`rgba(168,85,247)`) + "✨ [Nom modèle] — modèle cloud (précision élevée)"
- **Bandeau gris discret** + "⚡ [Nom modèle] — modèle local"

Informations visibles sur chaque carte :
- Bandeau modèle + date sur la même ligne (en haut)
- Avatar coloré + pseudo utilisateur
- Titre de la recherche
- Badges : nombre d'annonces, meilleure note, prix minimum

**Avertissement affiché en bas du feed (une seule fois) :**
> 💡 *Les notes d'un modèle cloud (Claude, GPT-4) sont généralement plus précises que celles d'un modèle local. Tenez-en compte en comparant des recherches entre elles.*

---

## 8. Modifications de server.py

Changements minimaux à apporter au serveur Python existant :

1. **Headers CORS** — ajouter sur toutes les réponses :
   ```python
   'Access-Control-Allow-Origin': '*'  # ou domaine précis en prod
   'Access-Control-Allow-Private-Network': 'true'
   ```

2. **Endpoint GET `/api/ping`** — retourne `{"status": "ok"}`, permet au frontend de détecter si le serveur local tourne

3. **Le publish** — entièrement côté frontend JS via le SDK Supabase (le serveur local n'a pas besoin de connaître Supabase ni d'avoir un endpoint `/api/publish`). Une fois l'analyse terminée, `allResults` est déjà en mémoire dans le navigateur — un clic "Publier" pousse directement vers Supabase avec le JWT de l'utilisateur connecté.

Aucune autre modification structurelle de server.py requise.

---

## 9. Installation pour les amis

### Ce qui est fourni (lien Google Drive)
Un ZIP contenant :
```
lbc-dealfinder/
  ├── server.py
  ├── requirements.txt
  ├── install.bat       (Windows — double-clic)
  ├── install.sh        (Mac/Linux)
  └── README-rapide.txt
```

### install.bat (Windows)
```bat
@echo off
echo Installation de LBC DealFinder...
python --version >nul 2>&1 || (echo Python non trouve. Installe Python 3.11+ depuis python.org && pause && exit)
pip install -r requirements.txt
playwright install chromium
echo.
echo Installation terminee ! Lance server.py puis ouvre lbcdeals.fr
pause
```

### Page /install sur le site
Guide pas-à-pas intégré au site, accessible sans compte :
1. Télécharger le ZIP (bouton lien Google Drive)
2. Extraire et double-cliquer `install.bat`
3. Lancer `python server.py` (garder la fenêtre ouverte)
4. Ouvrir le site et se connecter avec le compte créé via le lien d'invitation

---

## 10. Gestion des accès (invite-only)

- **Inscriptions publiques désactivées** dans Supabase (paramètre dashboard)
- Seul l'admin peut générer des liens d'invitation depuis `/admin`
- Un lien d'invitation = un token UUID unique, usage unique, expiration 7 jours
- L'invité clique le lien → formulaire de création de compte (pseudo + mot de passe)

---

## 11. Roadmap par phases

### Phase 1 — Hub MVP (priorité)
- [ ] Setup Supabase (auth, tables, RLS)
- [ ] Adaptation frontend : auth (login, session), feed `/hub`, page `/search/:id`
- [ ] Ajout CORS + `/api/ping` dans server.py
- [ ] Bouton "Publier" dans le workflow scraper et import JSON
- [ ] Page `/install` statique
- [ ] Déploiement GitHub Pages

### Phase 2 — Expérience amis
- [ ] Profils utilisateurs `/profile/:username`
- [ ] Panel admin `/admin` (invitations, modération)
- [ ] Tri du feed (récent / meilleure note / prix)
- [ ] Temps réel Supabase (feed live)

### Phase 3 — Qualité de vie
- [ ] Badge "annonce peut-être expirée" (si > 7 jours)
- [ ] Favoris (sauvegarder une annonce)
- [ ] Notifications (nouvelle recherche publiée)

---

## 12. Ce qui NE change PAS

- Le scraping Playwright reste identique
- L'analyse Ollama locale reste identique  
- Le workflow import JSON Claude.ai reste identique
- Le design visuel (dark theme, cartes annonces) reste identique
- Le serveur Python local reste optionnel (seulement pour scraper)
