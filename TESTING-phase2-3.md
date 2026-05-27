# LBC Hub — Check-list de tests Phase 2 + 3 (v1.1.0 → v1.6.0)

Tutoriel pas-à-pas pour valider tout ce qui a été ajouté **après** le tag `v1.0.0-phase1`.
Si quelque chose casse à une étape, stop et debug avant de continuer.

---

## 0. Sync code + redémarrage server local

Sur le PC où tu lances le scraper :

```bash
cd C:\Users\Tristan\Documents\lbc
git pull --tags
```

- [ ] Si tu avais `server.py` en train de tourner → ferme la fenêtre et relance :
  ```bash
  python server.py
  ```
  - Vérification rapide : `curl http://localhost:8080/api/ping` renvoie `{"status":"ok"}`.

- [ ] Tests pytest backend toujours verts :
  ```bash
  python -m pytest tests/ -q
  ```
  Attendu : `3 passed`.

---

## 1. Préalables Supabase (Dashboard manuel) — IMPORTANT

Avant de tester quoi que ce soit, il faut **appliquer les 2 migrations DB** que les fonctionnalités Phase 3 attendent.

### 1.1 — Recréer l'admin si tu l'as perdu lors des tests Phase 1

⚠️ Si tu n'es pas sûr que `tristanfranceschetti@gmail.com` existe encore en tant qu'admin (cf. l'incident pendant la Section 11 de Phase 1) :

1. Dashboard → Auth → Users → vérifie qu'il est listé
2. Sinon : `Add user` → email = `tristanfranceschetti@gmail.com` + mdp solide + ✅ Auto Confirm Email
3. SQL Editor :

```sql
insert into public.profiles (id, username, role, avatar_color)
select id, 'tristan', 'admin', '#a855f7'
from auth.users
where email = 'tristanfranceschetti@gmail.com'
on conflict (id) do update set role = 'admin', username = 'tristan';
```

- [ ] Vérification :
  ```sql
  select id, username, role from public.profiles where username = 'tristan';
  ```
  → 1 ligne, `role = 'admin'`.

### 1.2 — Migration : table `favorites` (pour Phase 3)

Sur SQL Editor, exécute le contenu de `supabase/migrations/2026-05-27-favorites.sql` :

```sql
create table if not exists public.favorites (
    user_id    uuid not null references auth.users(id) on delete cascade,
    search_id  uuid not null references public.searches(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, search_id)
);

create index if not exists favorites_user_idx   on public.favorites(user_id);
create index if not exists favorites_search_idx on public.favorites(search_id);

alter table public.favorites enable row level security;

drop policy if exists "favorites_select_own" on public.favorites;
create policy "favorites_select_own"
  on public.favorites for select to authenticated
  using (auth.uid() = user_id);

drop policy if exists "favorites_insert_own" on public.favorites;
create policy "favorites_insert_own"
  on public.favorites for insert to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "favorites_delete_own" on public.favorites;
create policy "favorites_delete_own"
  on public.favorites for delete to authenticated
  using (auth.uid() = user_id);
```

- [ ] Pas d'erreur ; aucune ligne retournée (c'est du DDL).

### 1.3 — Migration : colonne `expired_at` sur `listings`

```sql
alter table public.listings
    add column if not exists expired_at timestamptz;

create index if not exists listings_expired_idx
    on public.listings(expired_at)
    where expired_at is not null;

drop policy if exists "listings_update_authenticated" on public.listings;
create policy "listings_update_authenticated"
  on public.listings for update
  to authenticated
  using (true)
  with check (true);
```

- [ ] Pas d'erreur.
- [ ] Sanity check :
  ```sql
  select column_name from information_schema.columns
  where table_schema='public' and table_name='listings' and column_name='expired_at';
  ```
  → 1 ligne.

### 1.4 — Vérifie les bonnes URLs côté Auth

Auth → URL Configuration :
- **Site URL** = `https://shisuboi.github.io/lbc-hub` (prod) ou `http://localhost:8080` (si tu testes en local)
- Redirect URLs garde toujours :
  - `https://shisuboi.github.io/lbc-hub/*`
  - `http://localhost:8080/*`
  - `http://localhost:8080/**`

- [ ] Site URL alignée avec l'environnement que tu vas tester.

---

## 2. Test Admin UI — v1.1.0-admin

URL : `https://shisuboi.github.io/lbc-hub/admin` (ou `http://localhost:8080/admin`)

### 2.1 — Visibilité du lien

- [ ] Connecte-toi avec **ton compte admin** (`tristanfranceschetti@gmail.com`)
- [ ] Dans le header en haut, après "🔍 Scraper", tu vois **"🛠️ Admin"** (uniquement parce que ton profil a `role = 'admin'`)
- [ ] Logue-toi avec un compte non-admin (un compte secondaire que tu crées pour le test) → le lien "🛠️ Admin" doit **disparaître**

### 2.2 — Page admin

Reconnecte-toi en admin, clique sur "🛠️ Admin" :

- [ ] Page s'affiche avec deux cartes :
  - **"📨 Inviter un ami"** avec les 2 étapes numérotées + bouton "✨ Générer un lien d'invitation"
  - **"📜 Invitations existantes"** avec un tableau (Token / Créée / Statut)

### 2.3 — Génération d'invitation

- [ ] Clique **"✨ Générer un lien d'invitation"**
- [ ] Apparition d'une zone verte avec :
  - "✅ Invitation créée — expire le …"
  - Un champ texte avec une URL complète `https://shisuboi.github.io/lbc-hub/invite/<UUID>`
  - Bouton **"📋 Copier"**
- [ ] Clique **Copier** → le bouton passe à "✅ Copié !" pendant ~2 secondes
- [ ] L'URL est bien dans ton presse-papier (Ctrl+V dans une autre app pour vérifier)

### 2.4 — Liste des invitations

- [ ] Le tableau s'est mis à jour automatiquement et inclut la nouvelle invitation
- [ ] Statut affiché : **"Active"** (badge vert)
- [ ] Si tu as déjà testé des invitations consommées → tu vois aussi du **"Utilisée par @username"** (badge bleu) ou **"Expirée"** (badge rouge)

### 2.5 — Vérification sécurité RLS

Sans te déconnecter, ouvre la console DevTools (F12) → onglet Console et tape :

```js
await window.supabase.createClient(
  'https://pfkuphmpzhdmfwaifywj.supabase.co',
  // remplace par ta vraie anon key — ou prends celle de js/supabase-client.js
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
).from('invitations').insert({}).select()
```

- [ ] (Optionnel) Si tu fais ce test depuis un compte **non-admin**, ça doit échouer avec une erreur RLS. Si tu es admin, ça crée une invitation. Pas indispensable de tester.

---

## 3. Test Scraper sans Ollama — v1.2.0-d01

URL : `http://localhost:8080/scraper` (le scraper requiert que `server.py` tourne en local)

### 3.1 — UI nettoyée

- [ ] Plus de dropdown **"Modèle IA (Ollama)"**
- [ ] Plus de case **"♻️ Ré-analyser les annonces déjà scrapées"**
- [ ] Le formulaire Configuration contient uniquement : **URL Leboncoin, Pages Max, Délai Scraping, Critères de recherche**
- [ ] Bouton principal s'appelle **"⚡ Lancer le scraping"** (et plus "Lancer l'Analyse")

### 3.2 — Lancement scrape

- [ ] Remplis l'URL d'une recherche LBC légère (1-2 pages max, ex : un terme spécifique), critères dans le textarea
- [ ] Clique **"Lancer le scraping"**
- [ ] Chromium s'ouvre (mode non-headless), tu vois le scrape se dérouler en live dans la console à droite
- [ ] Si Datadome bloque, résous le Captcha dans Chromium puis clique le bouton de reprise (comme avant)
- [ ] À la fin :
  - Status passe à **"Scrape terminé"** (badge vert)
  - Le scraper N'EST PAS resté sur "Analyse IA" (c'est ça qui change avec D-01)
  - Apparition d'un nouveau panneau **"🤖 Étape suivante : analyser via Claude.ai"** dans la sidebar Configuration

### 3.3 — Étape Claude.ai

Dans le panneau "🤖 Étape suivante" :

- [ ] Liste numérotée avec 5 étapes claires (Copier → Coller → Joindre brut.json → Récupérer JSON → Importer)
- [ ] Bouton **"📋 Copier le prompt pour Claude.ai"** — clique-le, le prompt est dans ton presse-papier
- [ ] Lien **"télécharger leboncoin_brut.json"** — clique-le, ça lance le download du fichier
- [ ] Ouvre **https://claude.ai**, colle le prompt, joins le fichier `leboncoin_brut.json` téléchargé, envoie
- [ ] Claude renvoie un JSON (tableau d'annonces analysées)
- [ ] Copie le contenu JSON (juste le tableau, sans intro), colle-le dans un fichier `.json` local (ex: `claude-results.json` sur ton bureau)

### 3.4 — Import + Publish

- [ ] Clique **"📥 Importer le JSON Claude.ai"** dans le même panneau
- [ ] Sélectionne `claude-results.json` que tu viens de créer
- [ ] Les résultats analysés s'affichent dans la grille de résultats (à droite)
- [ ] Le panneau **"📤 Publier sur le hub"** apparaît
- [ ] Saisis un titre genre `Test post-D-01` et clique **"Publier sur le hub"**
- [ ] Status passe à **"✅ Publiée !"** avec un lien
- [ ] Clique le lien → tu arrives sur `/search/<id>` avec les bonnes annonces
- [ ] Sur `/hub`, la carte apparaît avec **bandeau violet ✨** (cloud, parce que `inferModelType` détecte "claude")

### 3.5 — Edge case : SSE state preservation

- [ ] Sur `/scraper` avec un scrape récent en `scraped` → **F5**
- [ ] La page se recharge, le panneau "Étape suivante" est **toujours là** (server.py rejoue le scraped event sur reconnect SSE)

---

## 4. Test Hub Sort + Filters — v1.3.0-feed-sort

URL : `https://shisuboi.github.io/lbc-hub/hub`

Pré-requis : au moins 5-6 recherches publiées par toi et idéalement 1-2 autres comptes pour varier les auteurs + plateformes.

### 4.1 — Toolbar visible

- [ ] En haut du feed, juste sous "Hub des recherches", tu vois une **toolbar** avec :
  - Une barre de recherche (placeholder "Filtrer par titre ou pseudo…")
  - Un select **"Trier :"** avec 4 options (Plus récentes, Meilleures notes, Prix croissant/décroissant)
  - Une rangée de chips **"Plateforme :"** : Toutes, 🟠 LBC, 🔵 eBay, etc. (uniquement celles présentes)
  - Une rangée de chips **"Auteur :"** : Tous, @tristan, @autre…
  - Un bouton **"☆ Favoris"** à droite
  - Un compteur en bas "N recherches"

### 4.2 — Tri

- [ ] Sélectionne **"Meilleures notes ⭐"** → les cartes se réordonnent : meilleur score en premier
- [ ] Sélectionne **"Prix croissant 📈"** → cartes triées du moins cher au plus cher
- [ ] Sélectionne **"Prix décroissant 📉"** → inverse
- [ ] Reviens sur **"Plus récentes ⏱️"** (default) → ordre chronologique inverse

### 4.3 — Filtres chips

- [ ] Clique le chip **"🟠 LBC"** → seules les recherches LBC restent (couleur violet/bleu active)
- [ ] Clique **"Toutes"** → tout réapparaît
- [ ] Clique sur un chip auteur (ex `@tristan`) → seules les recherches de cet auteur
- [ ] Compteur en bas se met à jour : "X / total recherches"

### 4.4 — Recherche texte

- [ ] Tape un mot du titre d'une recherche dans la barre de recherche → filtre live au fur et à mesure
- [ ] Tape un pseudo (ex `tristan`) → seules les recherches de ce user
- [ ] Vide le champ → tout revient

### 4.5 — Realtime + filtres

- [ ] Garde `/hub` ouvert avec un filtre actif (ex : plateforme = eBay)
- [ ] Dans un autre onglet, publie une recherche LBC depuis `/scraper` (workflow Claude.ai complet, ou un INSERT SQL pour aller plus vite)
- [ ] Sur `/hub`, la carte n'apparaît **pas** dans le feed visible (parce que filtre eBay), mais le compteur monte de 1
- [ ] Clique "Toutes" → la nouvelle carte apparaît bien

---

## 5. Test Profile Pages — v1.4.0-profiles

### 5.1 — Lien depuis le header

- [ ] Sur n'importe quelle page, clique l'avatar `@tristan` en haut à droite → un dropdown apparaît
- [ ] Clique **"Mon profil"** → tu arrives sur `/profile/tristan` (URL avec ton pseudo)

### 5.2 — Page profil — entête

- [ ] En haut : avatar grand format + `@tristan` + badge **"🛠️ Admin"** (jaune doré, parce que tu es admin)
- [ ] "Membre depuis le 27 mai 2026"
- [ ] 4 stats : Recherches publiées, Annonces analysées, Meilleure note, Dernière activité

### 5.3 — Grille de ses recherches

- [ ] Sous l'entête, titre "📂 Ses recherches"
- [ ] Toutes tes recherches publiées sont là, mêmes cartes que sur le hub
- [ ] Click sur une carte → te mène à `/search/<id>`

### 5.4 — @username cliquable partout

- [ ] Sur `/hub`, clique sur le `@tristan` dans la meta d'une carte → te mène sur son profil (au lieu d'ouvrir la search detail)
- [ ] Sur `/search/<id>`, clique sur `par @tristan` dans le header → te mène sur son profil
- [ ] Le hover sur `@username` change la couleur (bleu accent)

### 5.5 — Profil inexistant

- [ ] Tape manuellement `/profile/utilisateur_qui_nexiste_pas` dans la barre d'URL
- [ ] Tu vois une page d'erreur "Profil introuvable" avec bouton "Retour au Hub"

---

## 6. Test Favoris — v1.5.0-favorites

### 6.1 — Étoile sur les cartes

- [ ] Sur `/hub`, chaque carte a une **☆** (étoile creuse) en haut à droite (à côté de la date)
- [ ] Hover sur l'étoile → fond doré léger + scale-up
- [ ] Clique l'étoile sur une carte → devient **⭐** (étoile pleine dorée avec glow)
- [ ] Re-clique → revient à ☆

### 6.2 — Chip "Favoris"

- [ ] Marque 2-3 recherches en favori
- [ ] Clique le chip **"☆ Favoris"** en haut → le chip passe à **"⭐ Favoris"** (fond doré)
- [ ] Seules les recherches mises en favoris sont affichées dans le feed
- [ ] Click un autre filtre → l'intersection des filtres est appliquée

### 6.3 — Persistance

- [ ] F5 sur `/hub` → tes étoiles ⭐ sont toujours là (lues depuis Supabase au boot)
- [ ] Logue-toi avec un autre compte → cet autre user n'hérite PAS de tes favoris (chacun les siens, RLS isole)

### 6.4 — Étoile sur la page détail

- [ ] Click sur une carte → page `/search/<id>`
- [ ] À côté du titre de la search, gros bouton ☆ ou ⭐
- [ ] Toggle → bascule l'état
- [ ] Retour sur `/hub` → l'étoile sur la carte reflète bien le nouvel état

### 6.5 — Edge case : favori sur search supprimée

- [ ] (Optionnel, destructif) Si tu supprimes une search en DB → la favorite associée disparaît automatiquement (cascade)
- [ ] Aucun "favori fantôme" ne reste affiché

---

## 7. Test Notifications — v1.6.0-phase3 (partie 1)

URL : `/hub` ouvert sur **Chrome ou Edge** (Safari/Firefox supportent moins bien la Notification API).

### 7.1 — Badge de titre

- [ ] Reste sur `/hub` mais **switche d'onglet** (Ctrl+Tab) ou minimise la fenêtre
- [ ] Depuis un autre onglet OU un autre navigateur logué sur un autre compte, publie une recherche
- [ ] Reviens sur l'onglet `/hub` MAIS sans cliquer encore (juste regarde le titre dans la barre des tâches OU titre de tab)
- [ ] Le titre de l'onglet devient **"(1) LBC DealFinder Hub"**
- [ ] Si plusieurs cartes arrivent → "(2)", "(3)", etc.

### 7.2 — Reset du compteur

- [ ] Reclique sur l'onglet `/hub` (mise en focus)
- [ ] Le titre redevient **"LBC DealFinder Hub"** (sans le compteur)

### 7.3 — Notification système

- [ ] Sur `/hub`, en haut à droite des chips, tu vois un bouton **"🔕 Activer notifications"**
- [ ] Clique-le → ton navigateur affiche une popup "Voulez-vous recevoir des notifications de ce site ?"
- [ ] Clique **Autoriser**
- [ ] Le bouton change pour **"🔔 Notifications ON"** (fond bleu/violet actif)
- [ ] Switche d'onglet, publie une nouvelle recherche depuis un autre compte
- [ ] Tu vois apparaître une notification système dans le coin de ton écran : "Nouvelle recherche sur le hub" + "@author a publié ..."

### 7.4 — Notification bloquée

- [ ] (Optionnel) Dans les paramètres du site (cadenas dans l'URL → Permissions), bloque les notifications, refresh `/hub`
- [ ] Le bouton devient **"🔕 Notifications bloquées"** grisé et désactivé

### 7.5 — Pas de notif sur ses propres publications

- [ ] Sur ton compte admin, publie une recherche (depuis ton scraper)
- [ ] Le compteur du titre **ne** s'incrémente **pas**, et **aucune** notification système n'apparaît
- [ ] (On ne s'auto-notifie pas — c'est un anti-spam volontaire)

---

## 8. Test Annonces Expirées — v1.6.0-phase3 (partie 2)

URL : `/search/<id>` d'une recherche avec plusieurs listings.

### 8.1 — Bouton "Marquer expirée"

- [ ] Chaque listing card a maintenant une rangée d'actions en bas :
  - **"Voir l'annonce 🔗"** (comme avant)
  - **"🚫 Marquer expirée"** (nouveau, plus petit)

### 8.2 — Toggle expirée

- [ ] Clique **"🚫 Marquer expirée"** sur une carte
- [ ] La carte se transforme :
  - Bandeau rouge en haut : **"🚫 Annonce expirée / supprimée"**
  - Carte grisée (opacity ~ 0.55) et désaturée
  - Bouton change pour **"↩️ Réactiver"**
- [ ] Au survol, la carte récupère sa luminosité (opacity 0.85)

### 8.3 — Persistance

- [ ] F5 → la carte est toujours marquée expirée
- [ ] Clique **"↩️ Réactiver"** → la carte revient normale, bouton repasse à "🚫 Marquer expirée"

### 8.4 — Visibilité cross-user

- [ ] Avec un autre compte, ouvre la même search detail → vois le même état expiré
- [ ] C'est volontaire : on est dans un groupe d'amis, n'importe qui peut flagger une annonce morte pour les autres

### 8.5 — Edge case : update RLS

- [ ] (Sécurité) Si un user pas auth (page publique imaginaire) essayait d'updater, RLS bloque
- [ ] L'UPDATE est restreint à `to authenticated` — donc un user déconnecté ne peut rien faire

---

## 9. Synthèse / debug rapide si bug

| Symptôme | Cause probable | Fix |
|---|---|---|
| Étoile ⭐ ne sauvegarde rien | Migration 1.2 pas faite | Re-run le SQL de la section 1.2 |
| "🚫 Marquer expirée" affiche `column expired_at does not exist` | Migration 1.3 pas faite | Re-run le SQL de la section 1.3 |
| Lien "🛠️ Admin" pas visible | Profil pas en `role='admin'` | `update profiles set role='admin' where username='tristan';` |
| Notifications système ne marchent pas | Permission bloquée OU Safari/Firefox | Réautoriser dans les params du site, ou utiliser Chrome/Edge |
| Hub vide alors qu'il y a des données | Site URL Supabase mal configurée | Section 1.4 |
| Page `/profile/X` toujours "introuvable" | username avec majuscules | Le code lowercase l'URL automatiquement, mais vérifier que le profile DB est en minuscules |

---

## 10. Si tout passe ✅

Tag stable atteint : **v1.6.0-phase3**.
La prochaine itération éventuelle = Phase 4 (idées listées dans CLAUDE.md).
