# LBC DealFinder Hub — Phase 1 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformer l'outil LBC DealFinder local en plateforme communautaire privée (hub partagé sur Supabase + GitHub Pages), avec auth invite-only, feed temps réel et publish-from-local.

**Architecture:** Frontend SPA modulaire (vanilla JS + ES6 modules) hébergé sur GitHub Pages → Supabase (PostgreSQL + Auth + Realtime via SDK JS) ↔ server.py local (Playwright + Ollama, headers CORS + Private Network). Le serveur local ne touche jamais Supabase ; le publish est fait directement par le frontend via le JWT de session.

**Tech Stack:**
- Frontend : HTML/CSS/Vanilla JS (ES6 modules), Supabase JS SDK v2 (CDN), routing history API maison
- Backend hébergé : Supabase (free tier) — auth email/password, PostgreSQL, Realtime, Row Level Security
- Backend local : Python 3.11+ / aiohttp / Playwright / Ollama (existant, ajout CORS + /api/ping)
- Tests : pytest pour endpoints serveur Python (CORS + ping)
- Déploiement : GitHub Pages (branche `gh-pages`), URL `https://<user>.github.io/lbc-hub`

**Décisions tech validées :**
1. SPA dans `index.html` avec routing JS (history API, GitHub Pages avec fallback 404→index.html)
2. Scraper accessible depuis le site hébergé (Chrome/Edge supportent HTTPS→localhost en mixed content ; Firefox/Safari requièrent workaround documenté dans `/install`)
3. Tests pragmatiques : pytest pour endpoints serveur uniquement ; tests manuels guidés pour frontend
4. Hébergement GitHub Pages sous-domaine `github.io` (pas de domaine custom)

**Amendements post-brainstorm :**
- A1 — **Date scraping** : `searches.scraped_at` (= moment du scraping capturé par server.py) est LA date affichée partout. `created_at` = date d'insertion Supabase, pour logs uniquement.
- A2 — **Multi-plateforme** : `url_lbc` renommé en `source_url` (générique) + champ `platform text` ajouté (`'leboncoin'|'ebay'|'vinted'|'other'`). Badge plateforme sur les feed cards.
- A3 — **Sync cross-machines** : `CLAUDE.md` commité dans le repo pour reconstruire le contexte Claude sur n'importe quelle machine. Config `.claude/settings.json` aussi dans le repo.

---

## Vue d'ensemble des sections

| Section | Sujet | Tâches |
|---|---|---|
| 1 | Setup Supabase (projet, tables, RLS, auth) | 6 |
| 2 | Server.py — CORS + /api/ping + tests pytest | 5 |
| 3 | Refactor frontend en SPA modulaire | 6 |
| 4 | Pages auth (login, invite/:token) | 5 |
| 5 | Page /hub (feed) | 5 |
| 6 | Page /search/:id | 4 |
| 7 | Page /scraper (adapt index actuel) + bouton Publier | 6 |
| 8 | Page /install statique | 2 |
| 9 | Déploiement GitHub Pages | 4 |
| **Total** | | **43** |

---

## File Structure cible

```
lbc/
├── server.py                      [MODIFIÉ — CORS middleware + /api/ping]
├── tests/
│   └── test_server.py             [NOUVEAU — pytest endpoints]
├── index.html                     [MODIFIÉ — shell SPA]
├── style.css                      [MODIFIÉ — styles hub/login/feed]
├── app.js                         [SUPPRIMÉ — découpé en modules]
├── js/
│   ├── main.js                    [NOUVEAU — entrypoint, router init]
│   ├── router.js                  [NOUVEAU — history API, route matching]
│   ├── supabase-client.js         [NOUVEAU — instance Supabase + helpers]
│   ├── auth.js                    [NOUVEAU — login/logout/session]
│   ├── pages/
│   │   ├── login.js               [NOUVEAU]
│   │   ├── invite.js              [NOUVEAU]
│   │   ├── hub.js                 [NOUVEAU]
│   │   ├── search.js              [NOUVEAU]
│   │   ├── scraper.js             [NOUVEAU — ex-app.js adapté]
│   │   └── install.js             [NOUVEAU]
│   ├── components/
│   │   ├── header.js              [NOUVEAU — topbar avec user menu]
│   │   ├── feed-card.js           [NOUVEAU — carte de recherche feed]
│   │   └── listing-card.js        [NOUVEAU — carte annonce (déplacé de app.js)]
│   └── lib/
│       ├── publish.js             [NOUVEAU — push vers Supabase]
│       ├── server-ping.js         [NOUVEAU — détection server.py local]
│       └── colors.js              [NOUVEAU — génération avatar colors]
├── supabase/
│   ├── schema.sql                 [NOUVEAU — création tables + indexes]
│   ├── rls.sql                    [NOUVEAU — Row Level Security policies]
│   └── seed.sql                   [NOUVEAU — admin user initial]
├── 404.html                       [NOUVEAU — redirect vers / pour SPA]
├── .github/workflows/deploy.yml   [NOUVEAU — auto-deploy GitHub Pages]
└── docs/superpowers/
    ├── specs/2026-05-26-lbc-hub-platform-design.md  [EXISTANT]
    └── plans/2026-05-27-lbc-hub-mvp-phase1.md       [CE FICHIER]
```

---

## Section 1 — Setup Supabase

### Task 1.1 : Création du projet Supabase

**Files:**
- Create: `supabase/README.md` (documentation des étapes manuelles)

- [ ] **Step 1: Créer un compte Supabase et un nouveau projet**

Action manuelle (dashboard https://supabase.com) :
1. Sign up avec email
2. New Project → Nom : `lbc-hub`, région : `Frankfurt (eu-central-1)`, mot de passe DB fort (à conserver dans un password manager)
3. Attendre 2 min provisioning

- [ ] **Step 2: Récupérer les credentials API**

Dans Settings → API :
- `Project URL` (ex: `https://xxxxx.supabase.co`)
- `anon public key` (clé publique safe pour frontend)
- `service_role key` (SECRÈTE — jamais dans le frontend, juste pour admin SQL)

- [ ] **Step 3: Documenter dans supabase/README.md**

Créer `supabase/README.md` avec :
```markdown
# Supabase Setup

## Project credentials
- URL : `https://xxxxx.supabase.co`
- Anon key : voir `js/supabase-client.js`
- Service role key : stockée hors-repo (password manager)

## Activation auth invite-only
Dashboard → Authentication → Providers → Email :
- Enable Email provider : ON
- Confirm email : OFF (pas de SMTP en free tier)
- Secure email change : ON

Dashboard → Authentication → URL Configuration :
- Site URL : `https://<github-user>.github.io/lbc-hub`
- Redirect URLs (ajouter) :
  - `https://<github-user>.github.io/lbc-hub/*`
  - `http://localhost:8080/*` (dev)

Dashboard → Authentication → Providers → Email → "Enable new user signups" : **OFF**
(force tout signup à passer par notre flow d'invitation custom).

## Application du schéma
SQL Editor → coller le contenu de `schema.sql` → Run
SQL Editor → coller le contenu de `rls.sql` → Run
SQL Editor → coller le contenu de `seed.sql` (après avoir édité l'email admin) → Run
```

- [ ] **Step 4: Commit**

```bash
git add supabase/README.md
git commit -m "docs(supabase): document setup steps for hosted project"
```

---

### Task 1.2 : Schéma SQL — tables users/searches/listings

**Files:**
- Create: `supabase/schema.sql`

- [ ] **Step 1: Écrire le fichier schema.sql**

Créer `supabase/schema.sql` :
```sql
-- ===== EXTENSIONS =====
create extension if not exists "pgcrypto";

-- ===== PROFILES (extension de auth.users) =====
-- Supabase gère auth.users automatiquement ; on stocke les méta-données métier ici.
create table public.profiles (
    id            uuid primary key references auth.users(id) on delete cascade,
    username      text unique not null check (char_length(username) between 3 and 24 and username ~ '^[a-z0-9_]+$'),
    avatar_color  text not null,
    role          text not null default 'user' check (role in ('user', 'admin')),
    created_at    timestamptz not null default now()
);

create index profiles_username_idx on public.profiles(username);

-- ===== INVITATIONS =====
create table public.invitations (
    token         uuid primary key default gen_random_uuid(),
    created_by    uuid references public.profiles(id) on delete set null,
    used_by       uuid references public.profiles(id) on delete set null,
    used_at       timestamptz,
    expires_at    timestamptz not null default (now() + interval '7 days'),
    created_at    timestamptz not null default now()
);

create index invitations_unused_idx on public.invitations(token) where used_at is null;

-- ===== SEARCHES =====
create table public.searches (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references public.profiles(id) on delete cascade,
    title         text not null check (char_length(title) between 1 and 120),
    criteria      text not null default '',
    source_url    text,                                         -- [A2] générique (pas url_lbc)
    platform      text not null default 'leboncoin'             -- [A2] 'leboncoin'|'ebay'|'vinted'|'other'
                  check (platform in ('leboncoin', 'ebay', 'vinted', 'other')),
    model_name    text not null,
    model_type    text not null check (model_type in ('cloud', 'local')),
    listing_count int  not null default 0,
    best_score    float,
    min_price     float,
    scraped_at    timestamptz,                                  -- [A1] date du scraping (affichée partout)
    created_at    timestamptz not null default now()            -- date d'insertion Supabase (logs uniquement)
);

create index searches_created_at_idx on public.searches(created_at desc);
create index searches_user_id_idx    on public.searches(user_id);

-- ===== LISTINGS =====
create table public.listings (
    id               uuid primary key default gen_random_uuid(),
    search_id        uuid not null references public.searches(id) on delete cascade,
    titre            text not null,
    prix             float,
    url              text,
    note_sur_100     float,
    caracteristiques text,
    explication      text,
    match_criteres   boolean,
    created_at       timestamptz not null default now()
);

create index listings_search_id_idx on public.listings(search_id);
create index listings_note_idx      on public.listings(note_sur_100 desc);
```

- [ ] **Step 2: Appliquer le schéma dans Supabase (manuel)**

Dashboard Supabase → SQL Editor → New Query → coller le contenu de `schema.sql` → Run.
Vérifier dans Table Editor que les 4 tables apparaissent : `profiles`, `invitations`, `searches`, `listings`.

- [ ] **Step 3: Commit**

```bash
git add supabase/schema.sql
git commit -m "feat(supabase): add schema for profiles/invitations/searches/listings"
```

---

### Task 1.3 : Row Level Security policies

**Files:**
- Create: `supabase/rls.sql`

- [ ] **Step 1: Écrire le fichier rls.sql**

Créer `supabase/rls.sql` :
```sql
-- ===== ENABLE RLS =====
alter table public.profiles    enable row level security;
alter table public.invitations enable row level security;
alter table public.searches    enable row level security;
alter table public.listings    enable row level security;

-- ===== PROFILES =====
-- Tous les users authentifiés peuvent lire tous les profils (pour afficher pseudos/avatars dans le feed)
create policy "profiles_select_authenticated"
  on public.profiles for select
  to authenticated
  using (true);

-- Un user peut updater son propre profil uniquement (sauf le rôle, géré côté SQL)
create policy "profiles_update_own"
  on public.profiles for update
  to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id and role = (select role from public.profiles where id = auth.uid()));

-- L'insertion est gérée par trigger (cf. seed.sql) lors du signup
create policy "profiles_insert_self"
  on public.profiles for insert
  to authenticated
  with check (auth.uid() = id);

-- ===== INVITATIONS =====
-- Seul l'admin peut lire toutes les invitations
create policy "invitations_admin_select"
  on public.invitations for select
  to authenticated
  using ((select role from public.profiles where id = auth.uid()) = 'admin');

-- Seul l'admin peut créer des invitations
create policy "invitations_admin_insert"
  on public.invitations for insert
  to authenticated
  with check ((select role from public.profiles where id = auth.uid()) = 'admin');

-- Tout le monde (même non authentifié) peut lire UNE invitation par son token (pour la validation côté frontend)
-- On utilise un RPC sécurisé pour ça (cf. validate_invitation function ci-dessous), pas une policy permissive.

-- ===== SEARCHES =====
-- Tous les users authentifiés peuvent lire toutes les recherches (feed public au sein du groupe)
create policy "searches_select_authenticated"
  on public.searches for select
  to authenticated
  using (true);

-- Un user peut publier des recherches en son nom uniquement
create policy "searches_insert_own"
  on public.searches for insert
  to authenticated
  with check (auth.uid() = user_id);

-- Un user peut supprimer ses propres recherches ; admin peut tout supprimer
create policy "searches_delete_own_or_admin"
  on public.searches for delete
  to authenticated
  using (
    auth.uid() = user_id
    or (select role from public.profiles where id = auth.uid()) = 'admin'
  );

-- ===== LISTINGS =====
-- Lecture libre pour authentifiés (cascade depuis searches)
create policy "listings_select_authenticated"
  on public.listings for select
  to authenticated
  using (true);

-- Insertion uniquement si la search parente appartient au user courant
create policy "listings_insert_via_own_search"
  on public.listings for insert
  to authenticated
  with check (
    exists (select 1 from public.searches s where s.id = search_id and s.user_id = auth.uid())
  );

-- ===== RPC : valider et consommer une invitation =====
create or replace function public.validate_invitation(invitation_token uuid)
returns table (valid boolean, message text)
language plpgsql
security definer
set search_path = public
as $$
declare
  inv record;
begin
  select * into inv from public.invitations where token = invitation_token;
  if inv is null then
    return query select false, 'Invitation introuvable';
    return;
  end if;
  if inv.used_at is not null then
    return query select false, 'Invitation déjà utilisée';
    return;
  end if;
  if inv.expires_at < now() then
    return query select false, 'Invitation expirée';
    return;
  end if;
  return query select true, 'OK';
end;
$$;

grant execute on function public.validate_invitation(uuid) to anon, authenticated;

-- ===== RPC : finaliser le signup avec token + username =====
create or replace function public.consume_invitation(invitation_token uuid, new_username text)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  inv record;
  current_user_id uuid;
  avatar text;
begin
  current_user_id := auth.uid();
  if current_user_id is null then
    raise exception 'Not authenticated';
  end if;

  -- Verrouille la ligne d'invitation pour éviter double-usage
  select * into inv from public.invitations where token = invitation_token for update;
  if inv is null then raise exception 'Invitation introuvable'; end if;
  if inv.used_at is not null then raise exception 'Invitation déjà utilisée'; end if;
  if inv.expires_at < now() then raise exception 'Invitation expirée'; end if;

  -- Génère une couleur d'avatar (HSL aléatoire)
  avatar := 'hsl(' || floor(random()*360)::text || ', 65%, 55%)';

  -- Crée le profil
  insert into public.profiles(id, username, avatar_color, role)
  values (current_user_id, new_username, avatar, 'user');

  -- Marque l'invitation comme consommée
  update public.invitations
    set used_by = current_user_id, used_at = now()
    where token = invitation_token;

  return json_build_object('username', new_username, 'avatar_color', avatar);
end;
$$;

grant execute on function public.consume_invitation(uuid, text) to authenticated;
```

- [ ] **Step 2: Appliquer le RLS dans Supabase (manuel)**

Dashboard → SQL Editor → coller `rls.sql` → Run.
Vérifier dans Authentication → Policies que chaque table a ses policies activées.

- [ ] **Step 3: Commit**

```bash
git add supabase/rls.sql
git commit -m "feat(supabase): add RLS policies + invitation RPCs"
```

---

### Task 1.4 : Seed admin initial

**Files:**
- Create: `supabase/seed.sql`

- [ ] **Step 1: Créer le user admin via Dashboard**

Dashboard → Authentication → Users → "Add user" → Create new user :
- Email : `tristanfranceschetti@gmail.com` (le user actuel)
- Password : fort, à conserver
- "Auto Confirm User" : ON

Récupérer l'UUID de l'user créé (visible dans la liste).

- [ ] **Step 2: Écrire seed.sql**

Créer `supabase/seed.sql` (remplacer `<ADMIN_UUID>` par la valeur réelle) :
```sql
-- Création du profil admin (l'user auth.users doit déjà exister via Dashboard)
insert into public.profiles(id, username, avatar_color, role)
values (
  '<ADMIN_UUID>'::uuid,
  'tristan',
  'hsl(280, 65%, 55%)',
  'admin'
)
on conflict (id) do update set role = 'admin';

-- Première invitation de test (sera affichée dans le dashboard)
insert into public.invitations(created_by) values ('<ADMIN_UUID>'::uuid);
```

- [ ] **Step 3: Appliquer le seed**

Dashboard → SQL Editor → coller `seed.sql` (avec UUID réel) → Run.
Vérifier dans Table Editor → `profiles` qu'une ligne existe avec `role = 'admin'`.

- [ ] **Step 4: Commit (avec UUID anonymisé)**

Avant commit, remplacer l'UUID réel par `<ADMIN_UUID>` (placeholder) dans le fichier pour ne pas exposer l'UUID dans Git :
```bash
git add supabase/seed.sql
git commit -m "feat(supabase): add admin seed template"
```

---

### Task 1.5 : Désactiver les inscriptions publiques

- [ ] **Step 1: Action manuelle Supabase**

Dashboard → Authentication → Providers → Email :
- "Enable new user signups" : **OFF**

Ainsi les invitations seront créées côté admin via `auth.admin.createUser` (via dashboard ou edge function), et seul le consume_invitation RPC liera l'auth.users au profil. En réalité pour MVP simple : l'admin créera les comptes auth via dashboard, puis l'utilisateur recevra un magic link de password reset pour définir son mdp et entrera son username via le RPC consume_invitation.

**Workflow invitation simplifié pour MVP :**
1. Admin clique "Générer invitation" dans `/admin` (Phase 2) ou via dashboard Supabase
2. Admin crée un user dans Auth Dashboard avec email du futur invité
3. Supabase envoie un magic link → l'invité définit son mdp
4. À la première connexion, l'invité voit `/onboarding?token=...` et choisit son username

Pour la **Phase 1 MVP, on simplifie encore** : le admin crée l'user via dashboard, lui communique mdp + token d'invitation par canal externe (Signal, etc.), et l'invité va sur `/invite/<token>` après login pour finaliser son profil.

- [ ] **Step 2: Vérifier**

Tenter un signup depuis l'URL `https://<projet>.supabase.co/auth/v1/signup` → doit retourner 422 "Signups not allowed for this instance".

---

### Task 1.6 : Activer Supabase Realtime sur `searches`

- [ ] **Step 1: Action manuelle Supabase**

Dashboard → Database → Replication → activer la replication sur la table `public.searches` (INSERT events).

- [ ] **Step 2: Vérifier**

Plus tard, depuis le frontend, on testera avec :
```js
supabase.channel('searches').on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'searches' }, payload => console.log(payload)).subscribe();
```
Une fois un INSERT manuel fait dans Table Editor, le log doit apparaître.

---

## Section 2 — Server.py : CORS + /api/ping + tests

### Task 2.1 : Setup pytest

**Files:**
- Create: `tests/__init__.py` (vide)
- Create: `tests/test_server.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Ajouter pytest aux requirements**

Lire `requirements.txt`, puis ajouter :
```
pytest>=8.0
pytest-asyncio>=0.23
aiohttp[client]>=3.9
```

- [ ] **Step 2: Installer**

```bash
pip install -r requirements.txt
```

- [ ] **Step 3: Créer tests/__init__.py vide**

```bash
mkdir tests
touch tests/__init__.py
```

(Sur Windows PowerShell : `ni tests/__init__.py -ItemType File`)

- [ ] **Step 4: Commit**

```bash
git add requirements.txt tests/__init__.py
git commit -m "chore: add pytest deps for server tests"
```

---

### Task 2.2 : Test du endpoint /api/ping (TDD : failing test)

**Files:**
- Create: `tests/test_server.py`

- [ ] **Step 1: Écrire le test failing**

Créer `tests/test_server.py` :
```python
import pytest
from aiohttp import web
import server


@pytest.fixture
async def client(aiohttp_client):
    app = server.create_app()
    return await aiohttp_client(app)


async def test_ping_returns_ok(client):
    resp = await client.get('/api/ping')
    assert resp.status == 200
    data = await resp.json()
    assert data == {'status': 'ok'}
```

Note : ce test assume une factory `server.create_app()` qui crée et retourne l'app aiohttp. Si le code actuel construit l'app inline dans `main()`, il faudra refactor en première étape (cf. Task 2.4).

- [ ] **Step 2: Lancer pytest — doit FAIL**

```bash
pytest tests/test_server.py::test_ping_returns_ok -v
```
Expected : FAIL (soit AttributeError sur `create_app`, soit 404 sur `/api/ping`).

- [ ] **Step 3: Commit (red phase)**

```bash
git add tests/test_server.py
git commit -m "test(server): add failing test for /api/ping endpoint"
```

---

### Task 2.3 : Test du CORS headers (TDD : failing test)

**Files:**
- Modify: `tests/test_server.py`

- [ ] **Step 1: Ajouter test CORS**

Ajouter à `tests/test_server.py` :
```python
async def test_cors_headers_on_get(client):
    resp = await client.get('/api/ping')
    assert resp.headers.get('Access-Control-Allow-Origin') == '*'
    assert resp.headers.get('Access-Control-Allow-Private-Network') == 'true'


async def test_cors_preflight_options(client):
    resp = await client.options('/api/ping', headers={
        'Origin': 'https://example.github.io',
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Private-Network': 'true',
    })
    assert resp.status in (200, 204)
    assert resp.headers.get('Access-Control-Allow-Origin') == '*'
    assert resp.headers.get('Access-Control-Allow-Private-Network') == 'true'
    assert 'GET' in resp.headers.get('Access-Control-Allow-Methods', '')
```

- [ ] **Step 2: Lancer pytest — doit FAIL**

```bash
pytest tests/test_server.py -v
```
Expected : 3 tests, tous en FAIL.

- [ ] **Step 3: Commit**

```bash
git add tests/test_server.py
git commit -m "test(server): add failing tests for CORS + private network headers"
```

---

### Task 2.4 : Refactor server.py — extraire create_app()

**Files:**
- Modify: `server.py` (autour des lignes 855-880, fonction main)

- [ ] **Step 1: Localiser le bloc actuel**

Lire `server.py` à partir de la ligne 855. Le bloc actuel ressemble probablement à :
```python
async def main():
    app = web.Application()
    app.router.add_get('/', index_handler)
    # ... 10 routes
    runner = web.AppRunner(app)
    # ...
```

- [ ] **Step 2: Extraire create_app()**

Modifier `server.py` pour séparer la construction de l'app de son lancement :
```python
def create_app() -> web.Application:
    """Build aiohttp app — used both by main() and by tests."""
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get('/', index_handler)
    app.router.add_get('/index.html', index_handler)
    app.router.add_get('/style.css', style_handler)
    app.router.add_get('/app.js', app_handler)
    app.router.add_post('/api/start', start_handler)
    app.router.add_post('/api/resume', resume_handler)
    app.router.add_post('/api/stop', stop_handler)
    app.router.add_get('/api/models', models_handler)
    app.router.add_get('/api/scraped-info', scraped_info_handler)
    app.router.add_get('/api/events', events_handler)
    app.router.add_post('/api/import-results', import_handler)
    app.router.add_get('/api/ping', ping_handler)
    # Catch-all OPTIONS pour les preflights CORS
    app.router.add_route('OPTIONS', '/{path:.*}', options_handler)
    return app


async def main():
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()
    print("[OK] Server running at http://localhost:8080")
    # Garder process vivant
    while True:
        await asyncio.sleep(3600)
```

- [ ] **Step 3: Vérifier que le serveur tourne toujours**

```bash
python server.py
```
Ouvrir `http://localhost:8080` — l'app actuelle doit s'afficher comme avant (les nouveaux handlers seront ajoutés à la task suivante).

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "refactor(server): extract create_app() factory for testability"
```

---

### Task 2.5 : Implémenter /api/ping + middleware CORS

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Ajouter le middleware CORS et les handlers**

Ajouter en haut de `server.py` (après les imports, avant les autres handlers) :
```python
# === CORS / PRIVATE NETWORK ACCESS ===

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Allow-Private-Network': 'true',
    'Access-Control-Max-Age': '86400',
}

@web.middleware
async def cors_middleware(request, handler):
    if request.method == 'OPTIONS':
        return web.Response(status=204, headers=CORS_HEADERS)
    response = await handler(request)
    for k, v in CORS_HEADERS.items():
        response.headers[k] = v
    return response


async def options_handler(request):
    return web.Response(status=204, headers=CORS_HEADERS)


async def ping_handler(request):
    return web.json_response({'status': 'ok'})
```

- [ ] **Step 2: Lancer les tests — tous doivent passer**

```bash
pytest tests/test_server.py -v
```
Expected : 3 tests, tous PASS.

- [ ] **Step 3: Tester manuellement**

```bash
python server.py
```
Dans un autre terminal :
```bash
curl -i http://localhost:8080/api/ping
curl -i -X OPTIONS http://localhost:8080/api/ping -H "Origin: https://example.com"
```
Vérifier que les headers CORS apparaissent dans les deux réponses.

- [ ] **Step 4: Commit**

```bash
git add server.py
git commit -m "feat(server): add CORS middleware + /api/ping endpoint"
```

---

## Section 3 — Refactor frontend en SPA modulaire

### Task 3.1 : Créer le shell HTML SPA

**Files:**
- Modify: `index.html` (réécriture quasi-complète)
- Backup: `index.html.scraper-backup` (sauvegarde du HTML actuel pour réutiliser dans pages/scraper.js)

- [ ] **Step 1: Sauvegarder l'index.html actuel**

```bash
cp index.html index.html.scraper-backup
```

(Cette sauvegarde servira à la Task 7.1 pour recopier le markup du scraper dans `js/pages/scraper.js`.)

- [ ] **Step 2: Réécrire index.html en shell SPA**

Remplacer **tout** le contenu de `index.html` par :
```html
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LBC DealFinder Hub</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="style.css">
</head>
<body>
    <div class="bg-glow bg-glow-1"></div>
    <div class="bg-glow bg-glow-2"></div>

    <div class="app-container">
        <header class="app-header" id="appHeader">
            <!-- Injecté par js/components/header.js -->
        </header>

        <main id="appRoot" class="app-body">
            <!-- Page courante injectée par le router -->
            <div class="page-loading">⏳ Chargement…</div>
        </main>
    </div>

    <!-- Supabase SDK via CDN -->
    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.min.js"></script>
    <script type="module" src="js/main.js"></script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add index.html index.html.scraper-backup
git commit -m "refactor(frontend): convert index.html to SPA shell"
```

---

### Task 3.2 : Supabase client module

**Files:**
- Create: `js/supabase-client.js`

- [ ] **Step 1: Écrire le module**

Créer le dossier `js/` puis le fichier `js/supabase-client.js` :
```javascript
// js/supabase-client.js
// Singleton client Supabase. La clé anon est PUBLIQUE (safe pour frontend).

const SUPABASE_URL = 'https://xxxxx.supabase.co';        // REMPLACER par l'URL réelle
const SUPABASE_ANON_KEY = 'eyJhbGciOi...';                // REMPLACER par la anon key réelle

if (!window.supabase) {
    throw new Error('Supabase SDK not loaded. Check the <script> tag in index.html.');
}

export const supa = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    auth: {
        persistSession: true,
        autoRefreshToken: true,
        storage: window.localStorage,
    },
});

export async function currentUser() {
    const { data: { user } } = await supa.auth.getUser();
    return user;
}

export async function currentProfile() {
    const user = await currentUser();
    if (!user) return null;
    const { data, error } = await supa
        .from('profiles')
        .select('id, username, avatar_color, role')
        .eq('id', user.id)
        .single();
    if (error) {
        console.error('[supabase] profile fetch failed', error);
        return null;
    }
    return data;
}

export function onAuthChange(callback) {
    return supa.auth.onAuthStateChange((event, session) => callback(event, session));
}
```

- [ ] **Step 2: Remplir les credentials**

Éditer le fichier pour mettre les vraies valeurs récupérées au Task 1.1 step 2.

- [ ] **Step 3: Commit (avec credentials anonymisés dans le commit)**

Avant commit, vérifier qu'il n'y a pas de clé SECRÈTE (service_role). La anon key est volontairement publique — safe à commit.
```bash
git add js/supabase-client.js
git commit -m "feat(frontend): add Supabase client singleton"
```

---

### Task 3.3 : Router SPA (history API)

**Files:**
- Create: `js/router.js`

- [ ] **Step 1: Écrire le router**

Créer `js/router.js` :
```javascript
// js/router.js
// Mini-router history API. Routes statiques + 1 paramètre dynamique (:id, :token, :username).

const routes = [];
let notFoundHandler = null;

export function route(pattern, loader) {
    // pattern: '/hub' ou '/search/:id'
    const paramNames = [];
    const regex = new RegExp('^' + pattern.replace(/:([a-zA-Z]+)/g, (_, name) => {
        paramNames.push(name);
        return '([^/]+)';
    }) + '$');
    routes.push({ pattern, regex, paramNames, loader });
}

export function notFound(loader) {
    notFoundHandler = loader;
}

export async function navigate(path, replace = false) {
    if (replace) history.replaceState({}, '', path);
    else history.pushState({}, '', path);
    await render();
}

export async function render() {
    const path = location.pathname;
    // Strip GitHub Pages prefix in prod (/lbc-hub)
    const stripped = path.replace(/^\/lbc-hub/, '') || '/';
    for (const r of routes) {
        const m = stripped.match(r.regex);
        if (m) {
            const params = {};
            r.paramNames.forEach((name, i) => { params[name] = decodeURIComponent(m[i + 1]); });
            const root = document.getElementById('appRoot');
            root.innerHTML = '<div class="page-loading">⏳ Chargement…</div>';
            try {
                await r.loader(params);
            } catch (e) {
                console.error('[router] page load failed', e);
                root.innerHTML = `<div class="error-panel card">❌ Erreur de chargement : ${e.message}</div>`;
            }
            return;
        }
    }
    if (notFoundHandler) await notFoundHandler();
}

export function init() {
    window.addEventListener('popstate', render);
    // Intercept all <a data-link> clicks for SPA navigation
    document.body.addEventListener('click', e => {
        const a = e.target.closest('a[data-link]');
        if (a) {
            e.preventDefault();
            navigate(a.getAttribute('href'));
        }
    });
    render();
}
```

- [ ] **Step 2: Commit**

```bash
git add js/router.js
git commit -m "feat(frontend): add SPA router with history API"
```

---

### Task 3.4 : Auth module

**Files:**
- Create: `js/auth.js`

- [ ] **Step 1: Écrire le module**

Créer `js/auth.js` :
```javascript
// js/auth.js
import { supa, currentProfile } from './supabase-client.js';
import { navigate } from './router.js';

let cachedProfile = null;

export async function loginWithPassword(email, password) {
    const { data, error } = await supa.auth.signInWithPassword({ email, password });
    if (error) throw error;
    cachedProfile = await currentProfile();
    return data;
}

export async function logout() {
    await supa.auth.signOut();
    cachedProfile = null;
    navigate('/');
}

export async function getProfile(force = false) {
    if (!cachedProfile || force) cachedProfile = await currentProfile();
    return cachedProfile;
}

/**
 * Guard pour les pages authentifiées. À appeler en début de loader.
 * Si pas connecté → redirige vers /
 * Si connecté mais pas de profil → redirige vers /invite (l'user doit compléter son inscription)
 */
export async function requireAuth({ requireProfile = true } = {}) {
    const { data: { user } } = await supa.auth.getUser();
    if (!user) {
        navigate('/');
        throw new Error('Not authenticated');
    }
    if (requireProfile) {
        const profile = await getProfile(true);
        if (!profile) {
            navigate('/onboarding');
            throw new Error('Profile not yet created');
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add js/auth.js
git commit -m "feat(frontend): add auth module with login/logout/guard"
```

---

### Task 3.5 : Header component

**Files:**
- Create: `js/components/header.js`

- [ ] **Step 1: Écrire le composant**

Créer `js/components/header.js` :
```javascript
// js/components/header.js
import { supa } from '../supabase-client.js';
import { getProfile, logout } from '../auth.js';
import { navigate } from '../router.js';

export async function renderHeader() {
    const el = document.getElementById('appHeader');
    const { data: { user } } = await supa.auth.getUser();
    const profile = user ? await getProfile() : null;

    if (!user) {
        el.innerHTML = `
            <div class="logo-area">
                <span class="logo-icon">🤖</span>
                <div class="logo-text">
                    <h1>LBC DealFinder <span class="accent-text">Hub</span></h1>
                </div>
            </div>
            <nav class="header-nav">
                <a href="/install" data-link class="btn btn-ghost">Installation</a>
            </nav>
        `;
        return;
    }

    el.innerHTML = `
        <div class="logo-area">
            <a href="/hub" data-link class="logo-link">
                <span class="logo-icon">🤖</span>
                <div class="logo-text">
                    <h1>LBC DealFinder <span class="accent-text">Hub</span></h1>
                </div>
            </a>
        </div>
        <nav class="header-nav">
            <a href="/hub" data-link class="nav-link">🏠 Hub</a>
            <a href="/scraper" data-link class="nav-link">🔍 Scraper</a>
            <div class="user-menu" id="userMenu">
                <button class="user-menu-trigger" id="userMenuBtn">
                    <span class="user-avatar" style="background:${profile?.avatar_color || '#888'}">${(profile?.username || '?')[0].toUpperCase()}</span>
                    <span class="user-name">@${profile?.username || '...'}</span>
                </button>
                <div class="user-menu-dropdown hidden" id="userDropdown">
                    <a href="/profile/${profile?.username}" data-link>Mon profil</a>
                    <button id="btnLogout">Déconnexion</button>
                </div>
            </div>
        </nav>
    `;

    document.getElementById('userMenuBtn').addEventListener('click', () => {
        document.getElementById('userDropdown').classList.toggle('hidden');
    });
    document.getElementById('btnLogout').addEventListener('click', logout);
}
```

- [ ] **Step 2: Commit**

```bash
git add js/components/header.js
git commit -m "feat(frontend): add header component with user menu"
```

---

### Task 3.6 : main.js entrypoint + routes

**Files:**
- Create: `js/main.js`

- [ ] **Step 1: Écrire l'entrypoint**

Créer `js/main.js` :
```javascript
// js/main.js
import { route, notFound, init as initRouter } from './router.js';
import { renderHeader } from './components/header.js';
import { onAuthChange } from './supabase-client.js';

// Routes — chaque page est lazy-loaded
route('/',                  () => import('./pages/login.js').then(m => m.render()));
route('/install',           () => import('./pages/install.js').then(m => m.render()));
route('/invite/:token',     (p) => import('./pages/invite.js').then(m => m.render(p)));
route('/onboarding',        () => import('./pages/invite.js').then(m => m.renderOnboarding()));
route('/hub',               () => import('./pages/hub.js').then(m => m.render()));
route('/scraper',           () => import('./pages/scraper.js').then(m => m.render()));
route('/search/:id',        (p) => import('./pages/search.js').then(m => m.render(p)));

notFound(async () => {
    document.getElementById('appRoot').innerHTML = `
        <div class="error-panel card">
            <h2>Page introuvable</h2>
            <a href="/hub" data-link class="btn btn-primary">Retour au Hub</a>
        </div>`;
});

// Re-render header on every auth change
onAuthChange(() => renderHeader());

await renderHeader();
initRouter();
```

- [ ] **Step 2: Tester manuellement**

```bash
python server.py
```
Ouvrir `http://localhost:8080`. Le router doit charger la page login (mais elle n'existe pas encore → erreur Import). C'est attendu — on la créera à la section suivante.

- [ ] **Step 3: Commit**

```bash
git add js/main.js
git commit -m "feat(frontend): add SPA entrypoint with route definitions"
```

---

## Section 4 — Pages auth

### Task 4.1 : Page login

**Files:**
- Create: `js/pages/login.js`

- [ ] **Step 1: Écrire la page**

Créer `js/pages/login.js` :
```javascript
// js/pages/login.js
import { loginWithPassword } from '../auth.js';
import { supa } from '../supabase-client.js';
import { navigate } from '../router.js';

export async function render() {
    // Si déjà connecté → redirige vers /hub
    const { data: { user } } = await supa.auth.getUser();
    if (user) { navigate('/hub', true); return; }

    document.getElementById('appRoot').innerHTML = `
        <section class="auth-panel">
            <div class="auth-card card">
                <h2>Connexion</h2>
                <p class="muted">Plateforme privée — inscription sur invitation uniquement.</p>
                <form id="loginForm" class="auth-form">
                    <div class="form-group">
                        <label for="emailInput">Email</label>
                        <input type="email" id="emailInput" required autocomplete="email">
                    </div>
                    <div class="form-group">
                        <label for="passwordInput">Mot de passe</label>
                        <input type="password" id="passwordInput" required autocomplete="current-password">
                    </div>
                    <button type="submit" class="btn btn-primary">Se connecter</button>
                    <div id="loginError" class="form-error hidden"></div>
                </form>
                <p class="auth-footer">Besoin d'aide ? <a href="/install" data-link>Guide d'installation</a></p>
            </div>
        </section>
    `;

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = document.getElementById('emailInput').value.trim();
        const password = document.getElementById('passwordInput').value;
        const errorEl = document.getElementById('loginError');
        errorEl.classList.add('hidden');
        try {
            await loginWithPassword(email, password);
            navigate('/hub');
        } catch (err) {
            errorEl.textContent = err.message === 'Invalid login credentials'
                ? 'Email ou mot de passe incorrect'
                : err.message;
            errorEl.classList.remove('hidden');
        }
    });
}
```

- [ ] **Step 2: Tester manuellement**

```bash
python server.py
```
Ouvrir `http://localhost:8080` → formulaire login s'affiche.
Tenter login avec credentials admin → doit naviguer vers `/hub` (qui n'existe pas encore, on créera plus tard).

- [ ] **Step 3: Commit**

```bash
git add js/pages/login.js
git commit -m "feat(auth): add login page"
```

---

### Task 4.2 : Page invite/:token (création de profil après auth)

**Files:**
- Create: `js/pages/invite.js`

- [ ] **Step 1: Écrire la page**

Créer `js/pages/invite.js` :
```javascript
// js/pages/invite.js
// Flow : l'admin a créé le user auth + un token d'invitation. L'utilisateur :
// 1. Se connecte (login.js) avec son mdp fourni
// 2. Va sur /invite/:token pour choisir son username (RPC consume_invitation)

import { supa } from '../supabase-client.js';
import { navigate } from '../router.js';
import { getProfile } from '../auth.js';

export async function render({ token }) {
    const { data: { user } } = await supa.auth.getUser();
    if (!user) {
        // Sauvegarde le token pour après le login
        sessionStorage.setItem('pendingInvite', token);
        navigate('/', true);
        return;
    }

    // Valider le token d'abord
    const { data: validation } = await supa.rpc('validate_invitation', { invitation_token: token });
    const result = Array.isArray(validation) ? validation[0] : validation;
    if (!result || !result.valid) {
        document.getElementById('appRoot').innerHTML = `
            <section class="auth-panel">
                <div class="auth-card card">
                    <h2>❌ Invitation invalide</h2>
                    <p>${result?.message || 'Token introuvable'}</p>
                    <a href="/hub" data-link class="btn">Retour</a>
                </div>
            </section>`;
        return;
    }

    // Si user a déjà un profil, redirige directement
    const profile = await getProfile(true);
    if (profile) { navigate('/hub', true); return; }

    document.getElementById('appRoot').innerHTML = `
        <section class="auth-panel">
            <div class="auth-card card">
                <h2>Bienvenue !</h2>
                <p>Choisis ton pseudo public (3-24 caractères, lettres minuscules, chiffres et _).</p>
                <form id="onboardForm" class="auth-form">
                    <div class="form-group">
                        <label for="usernameInput">Pseudo</label>
                        <input type="text" id="usernameInput" required pattern="[a-z0-9_]{3,24}" placeholder="alex_42">
                    </div>
                    <button type="submit" class="btn btn-primary">Créer mon profil</button>
                    <div id="onboardError" class="form-error hidden"></div>
                </form>
            </div>
        </section>`;

    document.getElementById('onboardForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('usernameInput').value.trim().toLowerCase();
        const errorEl = document.getElementById('onboardError');
        errorEl.classList.add('hidden');
        const { data, error } = await supa.rpc('consume_invitation', {
            invitation_token: token,
            new_username: username,
        });
        if (error) {
            errorEl.textContent = error.message.includes('unique') ? 'Ce pseudo est déjà pris' : error.message;
            errorEl.classList.remove('hidden');
            return;
        }
        sessionStorage.removeItem('pendingInvite');
        navigate('/hub');
    });
}

export async function renderOnboarding() {
    // Cas où l'user est connecté mais sans profil ET sans token actif
    // → cherche un pendingInvite, sinon affiche un message d'erreur
    const token = sessionStorage.getItem('pendingInvite');
    if (token) {
        navigate(`/invite/${token}`, true);
        return;
    }
    document.getElementById('appRoot').innerHTML = `
        <section class="auth-panel">
            <div class="auth-card card">
                <h2>Profil incomplet</h2>
                <p>Aucune invitation active n'est associée à ton compte. Demande à l'admin un lien d'invitation.</p>
            </div>
        </section>`;
}
```

- [ ] **Step 2: Tester manuellement**

Après login admin :
- Aller sur `/invite/<TOKEN_GENERE_VIA_SEED>` (ex: récupérer le token depuis le Table Editor Supabase, table `invitations`)
- L'admin a déjà un profil → doit rediriger vers /hub.
- Tester ensuite la création d'un user secondaire : créer un nouvel user auth dans Dashboard, créer une invitation pour lui, se connecter avec son mdp, aller sur /invite/:token, choisir un pseudo → doit créer le profil.

- [ ] **Step 3: Commit**

```bash
git add js/pages/invite.js
git commit -m "feat(auth): add invite/onboarding page with token validation"
```

---

### Task 4.3 : Couleurs avatar utility

**Files:**
- Create: `js/lib/colors.js`

- [ ] **Step 1: Écrire l'utility**

Créer `js/lib/colors.js` :
```javascript
// js/lib/colors.js
// Génère une couleur HSL déterministe à partir d'un string (username)
// pour avoir des avatars cohérents même si l'avatar_color en DB venait à manquer.

export function colorFromString(s) {
    let hash = 0;
    for (let i = 0; i < s.length; i++) hash = s.charCodeAt(i) + ((hash << 5) - hash);
    return `hsl(${hash % 360}, 65%, 55%)`;
}

export function avatarHtml(profile, size = 32) {
    const color = profile?.avatar_color || colorFromString(profile?.username || '?');
    const initial = (profile?.username || '?')[0].toUpperCase();
    return `<span class="avatar" style="background:${color};width:${size}px;height:${size}px;line-height:${size}px;font-size:${size*0.45}px">${initial}</span>`;
}
```

- [ ] **Step 2: Commit**

```bash
git add js/lib/colors.js
git commit -m "feat(lib): add avatar color utility"
```

---

### Task 4.4 : Styles CSS pour pages auth + header

**Files:**
- Modify: `style.css`

- [ ] **Step 1: Ajouter les styles**

Ajouter à la fin de `style.css` :
```css
/* ===== AUTH PAGES ===== */
.auth-panel { display:flex; justify-content:center; align-items:center; min-height:70vh; padding:40px 20px; }
.auth-card  { max-width:420px; width:100%; padding:32px; }
.auth-card h2 { margin:0 0 8px; }
.auth-card .muted { color:var(--text-muted,#888); margin-bottom:24px; }
.auth-form .form-group { margin-bottom:16px; }
.auth-form label { display:block; margin-bottom:6px; font-weight:500; }
.auth-form input[type=email], .auth-form input[type=password], .auth-form input[type=text] {
    width:100%; padding:10px 14px; border-radius:8px; border:1px solid var(--border-color,#333);
    background:var(--input-bg,#1a1a1a); color:var(--text-color,#fff); font-size:14px;
}
.auth-form .btn { width:100%; margin-top:8px; }
.form-error { background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); color:#fca5a5; padding:10px; border-radius:6px; margin-top:12px; }
.auth-footer { margin-top:20px; text-align:center; font-size:13px; color:var(--text-muted,#888); }
.auth-footer a { color:#a855f7; text-decoration:none; }

/* ===== HEADER NAV ===== */
.header-nav { display:flex; align-items:center; gap:16px; }
.nav-link { color:var(--text-color,#fff); text-decoration:none; padding:8px 14px; border-radius:8px; font-weight:500; }
.nav-link:hover { background:rgba(255,255,255,0.06); }
.user-menu { position:relative; }
.user-menu-trigger { display:flex; align-items:center; gap:8px; background:transparent; border:1px solid var(--border-color,#333); padding:6px 12px 6px 6px; border-radius:24px; color:var(--text-color,#fff); cursor:pointer; }
.user-avatar { display:inline-block; width:28px; height:28px; line-height:28px; text-align:center; border-radius:50%; color:#fff; font-weight:600; font-size:13px; }
.user-menu-dropdown { position:absolute; top:calc(100% + 8px); right:0; background:var(--card-bg,#1e1e1e); border:1px solid var(--border-color,#333); border-radius:8px; padding:8px; min-width:180px; box-shadow:0 8px 24px rgba(0,0,0,0.4); z-index:100; }
.user-menu-dropdown a, .user-menu-dropdown button { display:block; width:100%; text-align:left; padding:8px 12px; color:var(--text-color,#fff); text-decoration:none; background:transparent; border:none; cursor:pointer; border-radius:4px; font-size:14px; }
.user-menu-dropdown a:hover, .user-menu-dropdown button:hover { background:rgba(255,255,255,0.06); }
.hidden { display:none !important; }

/* Page loading state */
.page-loading { text-align:center; padding:60px 20px; color:var(--text-muted,#888); font-size:16px; }
.error-panel { padding:32px; text-align:center; }

/* Avatar component */
.avatar { display:inline-block; border-radius:50%; color:#fff; text-align:center; font-weight:600; vertical-align:middle; }
```

- [ ] **Step 2: Tester visuellement**

Recharger `http://localhost:8080`, vérifier que la page login s'affiche proprement et que le header est cohérent.

- [ ] **Step 3: Commit**

```bash
git add style.css
git commit -m "style: add CSS for auth pages and header nav"
```

---

### Task 4.5 : Workflow admin manuel pour créer une invitation

**Files:**
- Create: `supabase/admin-snippets.md` (doc)

- [ ] **Step 1: Documenter le workflow admin Phase 1**

Créer `supabase/admin-snippets.md` :
```markdown
# Admin Snippets — Phase 1 (pas encore de UI /admin)

## Inviter un ami

1. Dashboard Supabase → Authentication → Users → "Add user" :
   - Email : `ami@example.com`
   - Password : générer un mdp aléatoire fort, le copier
   - Auto Confirm User : ON

2. Dashboard → SQL Editor → New query :
   ```sql
   insert into public.invitations(created_by)
   values ((select id from public.profiles where username = 'tristan'))
   returning token;
   ```

3. Récupérer le `token` retourné.

4. Communiquer à l'ami **par canal sécurisé** (Signal, etc.) :
   - L'URL : `https://<github-user>.github.io/lbc-hub/invite/<TOKEN>`
   - Le mdp temporaire (qu'il pourra changer dans Supabase plus tard via reset password)

5. L'ami ouvre l'URL → se connecte avec son email + mdp → choisit son pseudo → arrive sur le hub.

## Supprimer un user
```sql
delete from auth.users where email = 'ami@example.com';
-- cascade nettoie automatiquement profiles, searches, listings
```

## Lister les invitations actives
```sql
select token, created_at, expires_at, used_at,
       (select username from public.profiles p where p.id = invitations.used_by) as used_by_username
from public.invitations
order by created_at desc;
```
```

- [ ] **Step 2: Commit**

```bash
git add supabase/admin-snippets.md
git commit -m "docs(supabase): document admin snippets for Phase 1 (manual flow)"
```

---

## Section 5 — Page /hub (feed)

### Task 5.1 : Feed card component

**Files:**
- Create: `js/components/feed-card.js`

- [ ] **Step 1: Écrire le composant**

Créer `js/components/feed-card.js` :
```javascript
// js/components/feed-card.js
import { avatarHtml } from '../lib/colors.js';

const dateFr = (iso) => {
    const d = new Date(iso);
    const diffMin = (Date.now() - d.getTime()) / 60000;
    if (diffMin < 1)   return 'à l\'instant';
    if (diffMin < 60)  return `il y a ${Math.floor(diffMin)} min`;
    if (diffMin < 1440) return `il y a ${Math.floor(diffMin/60)} h`;
    return d.toLocaleDateString('fr-FR', { day:'numeric', month:'short', year: d.getFullYear()!==new Date().getFullYear()?'numeric':undefined });
};

export function feedCardHtml(search, profile) {
    const isCloud  = search.model_type === 'cloud';
    const banner   = isCloud
        ? `<div class="model-banner cloud">✨ ${escapeHtml(search.model_name)} — modèle cloud (précision élevée)</div>`
        : `<div class="model-banner local">⚡ ${escapeHtml(search.model_name)} — modèle local</div>`;
    return `
        <a href="/search/${search.id}" data-link class="feed-card card">
            ${banner}
            <div class="feed-card-meta">
                <div class="feed-author">
                    ${avatarHtml(profile, 28)}
                    <span class="feed-author-name">@${escapeHtml(profile?.username || '?')}</span>
                </div>
                <span class="feed-date">${dateFr(search.created_at)}</span>
            </div>
            <h3 class="feed-title">${escapeHtml(search.title)}</h3>
            <div class="feed-badges">
                <span class="badge">${search.listing_count} annonces</span>
                ${search.best_score !== null ? `<span class="badge badge-gold">⭐ ${Math.round(search.best_score)}/100</span>` : ''}
                ${search.min_price !== null ? `<span class="badge badge-emerald">💰 ${Math.round(search.min_price)} €</span>` : ''}
            </div>
        </a>
    `;
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}
```

- [ ] **Step 2: Commit**

```bash
git add js/components/feed-card.js
git commit -m "feat(hub): add feed card component"
```

---

### Task 5.2 : Page /hub — fetch + render

**Files:**
- Create: `js/pages/hub.js`

- [ ] **Step 1: Écrire la page**

Créer `js/pages/hub.js` :
```javascript
// js/pages/hub.js
import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { feedCardHtml } from '../components/feed-card.js';

export async function render() {
    await requireAuth();

    const root = document.getElementById('appRoot');
    root.innerHTML = `
        <section class="hub-panel">
            <div class="hub-header">
                <h2>Hub des recherches</h2>
                <a href="/scraper" data-link class="btn btn-primary">🔍 Nouvelle recherche</a>
            </div>
            <div id="feedGrid" class="feed-grid"></div>
            <div id="feedEmpty" class="empty-state card hidden">
                <h3>Pas encore de recherche publiée</h3>
                <p>Sois le premier à scraper et publier une recherche sur le hub !</p>
                <a href="/scraper" data-link class="btn btn-primary">Lancer une recherche</a>
            </div>
            <p class="hub-disclaimer">💡 <em>Les notes d'un modèle cloud (Claude, GPT-4) sont généralement plus précises que celles d'un modèle local. Tenez-en compte en comparant des recherches entre elles.</em></p>
        </section>
    `;

    // Fetch searches + profiles
    const { data: searches, error } = await supa
        .from('searches')
        .select('id, user_id, title, model_name, model_type, listing_count, best_score, min_price, created_at')
        .order('created_at', { ascending: false })
        .limit(50);

    if (error) {
        document.getElementById('feedGrid').innerHTML = `<div class="error-panel card">Erreur : ${error.message}</div>`;
        return;
    }

    if (!searches || searches.length === 0) {
        document.getElementById('feedEmpty').classList.remove('hidden');
        return;
    }

    // Fetch tous les profils auteurs (un seul appel)
    const userIds = [...new Set(searches.map(s => s.user_id))];
    const { data: profiles } = await supa.from('profiles').select('id, username, avatar_color').in('id', userIds);
    const profileMap = new Map((profiles || []).map(p => [p.id, p]));

    document.getElementById('feedGrid').innerHTML = searches.map(s =>
        feedCardHtml(s, profileMap.get(s.user_id))
    ).join('');
}
```

- [ ] **Step 2: Tester manuellement**

Insérer une search de test via SQL Editor Supabase :
```sql
insert into public.searches(user_id, title, criteria, model_name, model_type, listing_count, best_score, min_price)
values (
  (select id from public.profiles where username = 'tristan'),
  'Test : laptops gaming',
  'RTX 4060, 16Go RAM, < 800€',
  'claude-3.5-sonnet',
  'cloud',
  12,
  87.5,
  650
);
```
Recharger `/hub` → la carte doit apparaître.

- [ ] **Step 3: Commit**

```bash
git add js/pages/hub.js
git commit -m "feat(hub): add feed page with chronological searches"
```

---

### Task 5.3 : Styles CSS feed

**Files:**
- Modify: `style.css`

- [ ] **Step 1: Ajouter les styles**

Ajouter à la fin de `style.css` :
```css
/* ===== HUB / FEED ===== */
.hub-panel { padding:24px; max-width:1200px; margin:0 auto; }
.hub-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:24px; flex-wrap:wrap; gap:12px; }
.hub-header h2 { margin:0; }
.feed-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(300px, 1fr)); gap:16px; }
.feed-card { display:block; padding:0; overflow:hidden; cursor:pointer; transition:transform 0.15s, box-shadow 0.15s; text-decoration:none; color:inherit; }
.feed-card:hover { transform:translateY(-2px); box-shadow:0 12px 32px rgba(0,0,0,0.4); }
.model-banner { padding:8px 16px; font-size:12px; font-weight:600; color:#fff; }
.model-banner.cloud { background:rgba(168,85,247,0.85); }
.model-banner.local { background:rgba(100,100,100,0.6); }
.feed-card-meta { display:flex; justify-content:space-between; align-items:center; padding:12px 16px 4px; font-size:13px; color:var(--text-muted,#aaa); }
.feed-author { display:flex; align-items:center; gap:8px; }
.feed-author-name { font-weight:500; color:var(--text-color,#fff); }
.feed-title { padding:0 16px; margin:8px 0; font-size:16px; font-weight:600; }
.feed-badges { padding:8px 16px 16px; display:flex; gap:8px; flex-wrap:wrap; }
.badge { padding:4px 10px; border-radius:12px; background:rgba(255,255,255,0.06); font-size:12px; font-weight:500; }
.badge-gold { background:rgba(234,179,8,0.15); color:#fbbf24; }
.badge-emerald { background:rgba(16,185,129,0.15); color:#34d399; }
.hub-disclaimer { margin-top:32px; text-align:center; color:var(--text-muted,#888); font-size:13px; }
```

- [ ] **Step 2: Tester visuellement**

Recharger `/hub`. Vérifier que la carte de test a bien le bandeau violet (cloud), le pseudo, la date, et les 3 badges.

- [ ] **Step 3: Commit**

```bash
git add style.css
git commit -m "style: add CSS for hub feed and cards"
```

---

### Task 5.4 : Realtime feed (subscribe aux nouveaux INSERTs)

**Files:**
- Modify: `js/pages/hub.js`

- [ ] **Step 1: Ajouter la subscription Realtime**

Modifier `js/pages/hub.js` — ajouter à la fin de `render()` (après l'innerHTML) :
```javascript
    // === Realtime : insertion d'une nouvelle recherche ===
    const channel = supa.channel('searches-feed')
        .on('postgres_changes',
            { event: 'INSERT', schema: 'public', table: 'searches' },
            async (payload) => {
                const newSearch = payload.new;
                // Fetch le profile auteur
                const { data: profile } = await supa.from('profiles')
                    .select('id, username, avatar_color').eq('id', newSearch.user_id).single();
                const grid = document.getElementById('feedGrid');
                if (!grid) return;
                const div = document.createElement('div');
                div.innerHTML = feedCardHtml(newSearch, profile);
                grid.insertBefore(div.firstElementChild, grid.firstChild);
                document.getElementById('feedEmpty')?.classList.add('hidden');
            })
        .subscribe();

    // Cleanup quand on quitte la page (le router re-render et écrase appRoot)
    // On stocke le channel pour pouvoir l'unsubscribe à la prochaine navigation
    window.__hubChannel?.unsubscribe();
    window.__hubChannel = channel;
```

- [ ] **Step 2: Tester manuellement**

Avoir `/hub` ouvert dans un onglet. Dans un autre onglet, exécuter dans SQL Editor :
```sql
insert into public.searches(user_id, title, model_name, model_type, listing_count, best_score, min_price)
values ((select id from public.profiles where username='tristan'), 'Realtime test', 'gemma3:4b', 'local', 5, 72, 200);
```
Une nouvelle carte doit apparaître en haut du feed sans refresh.

- [ ] **Step 3: Commit**

```bash
git add js/pages/hub.js
git commit -m "feat(hub): add Supabase Realtime subscription for live feed"
```

---

### Task 5.5 : Réécrire l'écran de connexion par défaut quand non authentifié

**Files:**
- Modify: `js/pages/login.js`

- [ ] **Step 1: Gérer le pendingInvite après login**

Modifier la fonction `loginForm.addEventListener('submit', ...)` dans `js/pages/login.js` — remplacer le `navigate('/hub')` final par :
```javascript
            await loginWithPassword(email, password);
            const pendingToken = sessionStorage.getItem('pendingInvite');
            if (pendingToken) {
                navigate(`/invite/${pendingToken}`);
            } else {
                navigate('/hub');
            }
```

- [ ] **Step 2: Tester**

1. Se déconnecter
2. Aller sur `/invite/<TOKEN>` → redirige vers `/` (login)
3. Se connecter → doit revenir sur `/invite/<TOKEN>`

- [ ] **Step 3: Commit**

```bash
git add js/pages/login.js
git commit -m "feat(auth): redirect to pending invite after login"
```

---

## Section 6 — Page /search/:id

### Task 6.1 : Listing card component (déplacé depuis app.js actuel)

**Files:**
- Create: `js/components/listing-card.js`

- [ ] **Step 1: Localiser le rendu actuel des cartes annonce**

Lire `index.html.scraper-backup` et chercher la structure HTML des cartes de résultats (généralement dans `<div class="grid-container" id="resultsGrid">`).
Lire dans le `app.js` original (qui existe encore en backup ou via git history) la fonction qui génère les cards (probablement nommée `renderCards()` ou similaire).

- [ ] **Step 2: Extraire le rendu d'une carte**

Créer `js/components/listing-card.js` :
```javascript
// js/components/listing-card.js
// Extrait du app.js original — rendu d'une annonce avec note, prix, lien, etc.

export function listingCardHtml(listing) {
    const note = Math.round(parseFloat(listing.note_sur_100) || 0);
    const noteClass = note >= 85 ? 'super' : note >= 75 ? 'bonne' : note >= 60 ? 'correcte' : 'low';
    const match = listing.match_criteres ? '✅' : '❌';
    return `
        <div class="result-card card">
            <div class="card-header">
                <div class="score score-${noteClass}">${note}<span>/100</span></div>
                <div class="match-flag">${match}</div>
            </div>
            <h3 class="card-title">${escapeHtml(listing.titre)}</h3>
            <div class="card-price">${listing.prix != null ? `${Math.round(listing.prix)} €` : 'N/A'}</div>
            <div class="card-specs">${escapeHtml(listing.caracteristiques || '')}</div>
            <div class="card-explanation"><em>${escapeHtml(listing.explication || '')}</em></div>
            <a href="${listing.url}" target="_blank" rel="noopener" class="btn btn-secondary">Voir l'annonce →</a>
        </div>
    `;
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}
```

- [ ] **Step 3: Commit**

```bash
git add js/components/listing-card.js
git commit -m "feat(search): extract listing card component"
```

---

### Task 6.2 : Page /search/:id — fetch + render

**Files:**
- Create: `js/pages/search.js`

- [ ] **Step 1: Écrire la page**

Créer `js/pages/search.js` :
```javascript
// js/pages/search.js
import { supa } from '../supabase-client.js';
import { requireAuth } from '../auth.js';
import { listingCardHtml } from '../components/listing-card.js';
import { avatarHtml } from '../lib/colors.js';

export async function render({ id }) {
    await requireAuth();

    const root = document.getElementById('appRoot');
    root.innerHTML = `<div class="page-loading">⏳ Chargement de la recherche…</div>`;

    // Fetch search + author + listings en parallèle
    const [searchResp, listingsResp] = await Promise.all([
        supa.from('searches').select('*').eq('id', id).single(),
        supa.from('listings').select('*').eq('search_id', id).order('note_sur_100', { ascending: false }),
    ]);

    if (searchResp.error || !searchResp.data) {
        root.innerHTML = `<div class="error-panel card"><h2>Recherche introuvable</h2><a href="/hub" data-link class="btn">Retour au hub</a></div>`;
        return;
    }
    const search = searchResp.data;
    const listings = listingsResp.data || [];

    const { data: author } = await supa.from('profiles').select('id, username, avatar_color').eq('id', search.user_id).single();

    const isCloud = search.model_type === 'cloud';
    root.innerHTML = `
        <section class="search-detail">
            <div class="search-header card">
                <a href="/hub" data-link class="back-link">← Retour au hub</a>
                <div class="model-banner ${isCloud ? 'cloud' : 'local'}">
                    ${isCloud ? '✨' : '⚡'} ${escapeHtml(search.model_name)} — modèle ${isCloud ? 'cloud (précision élevée)' : 'local'}
                </div>
                <h2>${escapeHtml(search.title)}</h2>
                <div class="search-author">
                    ${avatarHtml(author, 32)}
                    <span>par <strong>@${escapeHtml(author?.username || '?')}</strong> · ${new Date(search.created_at).toLocaleString('fr-FR')}</span>
                </div>
                ${search.criteria ? `<p class="search-criteria"><strong>Critères :</strong> ${escapeHtml(search.criteria)}</p>` : ''}
                ${search.url_lbc ? `<p><a href="${search.url_lbc}" target="_blank" rel="noopener" class="muted-link">🔗 URL Leboncoin d'origine</a></p>` : ''}
            </div>

            <div class="search-controls card">
                <input type="text" id="searchFilter" placeholder="🔍 Filtrer par titre / spec...">
                <select id="searchSortBy">
                    <option value="note-desc">Meilleures notes ⭐</option>
                    <option value="price-asc">Prix croissant 📈</option>
                    <option value="price-desc">Prix décroissant 📉</option>
                </select>
                <select id="searchMinScore">
                    <option value="0">Toutes notes</option>
                    <option value="60">≥ 60/100</option>
                    <option value="75">≥ 75/100</option>
                    <option value="85">≥ 85/100</option>
                </select>
            </div>

            <div id="listingsGrid" class="grid-container"></div>
        </section>
    `;

    function renderListings() {
        const q       = document.getElementById('searchFilter').value.toLowerCase();
        const sortBy  = document.getElementById('searchSortBy').value;
        const minScore = parseFloat(document.getElementById('searchMinScore').value);

        let filtered = listings.filter(l => {
            const hay = ((l.titre||'') + ' ' + (l.caracteristiques||'')).toLowerCase();
            return hay.includes(q) && (parseFloat(l.note_sur_100) || 0) >= minScore;
        });

        if (sortBy === 'price-asc')  filtered.sort((a,b) => (a.prix??Infinity) - (b.prix??Infinity));
        if (sortBy === 'price-desc') filtered.sort((a,b) => (b.prix??-Infinity) - (a.prix??-Infinity));
        if (sortBy === 'note-desc')  filtered.sort((a,b) => (b.note_sur_100||0) - (a.note_sur_100||0));

        document.getElementById('listingsGrid').innerHTML = filtered.map(listingCardHtml).join('') ||
            '<div class="empty-state card"><p>Aucune annonce ne correspond aux filtres.</p></div>';
    }

    document.getElementById('searchFilter').addEventListener('input', renderListings);
    document.getElementById('searchSortBy').addEventListener('change', renderListings);
    document.getElementById('searchMinScore').addEventListener('change', renderListings);
    renderListings();
}

function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}
```

- [ ] **Step 2: Insérer des listings de test**

```sql
insert into public.listings(search_id, titre, prix, url, note_sur_100, caracteristiques, explication, match_criteres)
values
  ((select id from public.searches order by created_at desc limit 1), 'MSI Katana 15', 750, 'https://example.com/1', 88, 'i7-13620H, RTX 4060, 16Go', 'Excellent rapport q/p', true),
  ((select id from public.searches order by created_at desc limit 1), 'Lenovo Legion', 1200, 'https://example.com/2', 72, 'Ryzen 7, RTX 4070, 32Go', 'Bon mais cher', true);
```

Recharger `/search/<id>` → les 2 cards doivent s'afficher avec filtres fonctionnels.

- [ ] **Step 3: Commit**

```bash
git add js/pages/search.js
git commit -m "feat(search): add search detail page with filters and sort"
```

---

### Task 6.3 : Styles CSS search detail

**Files:**
- Modify: `style.css`

- [ ] **Step 1: Ajouter les styles**

Ajouter à la fin de `style.css` :
```css
/* ===== SEARCH DETAIL ===== */
.search-detail { max-width:1200px; margin:0 auto; padding:24px; }
.search-header { padding:0; overflow:hidden; margin-bottom:20px; }
.search-header .model-banner { display:block; }
.search-header h2 { padding:0 24px; margin:16px 0 8px; }
.search-author { padding:0 24px; display:flex; align-items:center; gap:10px; color:var(--text-muted,#aaa); font-size:14px; }
.search-criteria, .search-header p { padding:0 24px 16px; font-size:14px; }
.back-link { display:inline-block; padding:8px 24px 0; color:var(--text-muted,#888); text-decoration:none; font-size:13px; }
.back-link:hover { color:#a855f7; }
.muted-link { color:var(--text-muted,#888); text-decoration:none; font-size:13px; }
.muted-link:hover { color:#a855f7; }
.search-controls { display:flex; gap:12px; padding:14px 18px; margin-bottom:20px; align-items:center; flex-wrap:wrap; }
.search-controls input[type=text] { flex:1; min-width:200px; padding:8px 12px; border-radius:6px; border:1px solid var(--border-color,#333); background:var(--input-bg,#1a1a1a); color:var(--text-color,#fff); }
.search-controls select { padding:8px 12px; border-radius:6px; border:1px solid var(--border-color,#333); background:var(--input-bg,#1a1a1a); color:var(--text-color,#fff); }
```

- [ ] **Step 2: Tester visuellement, commit**

```bash
git add style.css
git commit -m "style: add CSS for search detail page"
```

---

### Task 6.4 : Vérification cross-page navigation

- [ ] **Step 1: Test manuel complet**

Flow à vérifier :
1. Login admin
2. Arrivée sur `/hub` — vois les 2 cards de test
3. Click sur une card → navigation vers `/search/<id>` (URL change)
4. Click sur "← Retour au hub" → revient sur `/hub`
5. Refresh la page sur `/search/<id>` (F5) → la page se charge directement (le router s'initialise correctement même sans passer par /hub)
6. Copier l'URL `/search/<id>`, ouvrir dans onglet privé → redirige vers `/` (login required) ; après login, revient sur `/search/<id>`

Si étape 6 ne fonctionne pas, ajouter la logique pendingRedirect dans login.js (similaire à pendingInvite) :
```javascript
// Au début de login.js render() — avant le redirect early :
const intended = sessionStorage.getItem('pendingRedirect');
// Et dans requireAuth.js — avant le navigate('/') :
if (location.pathname !== '/' && location.pathname !== '/install') {
    sessionStorage.setItem('pendingRedirect', location.pathname);
}
// Dans le submit handler du login :
const dest = sessionStorage.getItem('pendingRedirect') || '/hub';
sessionStorage.removeItem('pendingRedirect');
navigate(dest);
```

- [ ] **Step 2: Appliquer le fix si nécessaire et commit**

```bash
git add js/auth.js js/pages/login.js
git commit -m "feat(auth): preserve intended URL across login redirect"
```

---

## Section 7 — Page /scraper + Publish

### Task 7.1 : Migrer le markup scraper dans pages/scraper.js

**Files:**
- Create: `js/pages/scraper.js`
- Reference: `index.html.scraper-backup`

- [ ] **Step 1: Créer la page scraper**

Créer `js/pages/scraper.js` (skeleton + injection du markup HTML existant) :
```javascript
// js/pages/scraper.js
// Encapsule l'outil scraper d'origine en tant que page SPA.
import { requireAuth, getProfile } from '../auth.js';
import { checkLocalServer } from '../lib/server-ping.js';
import { publishSearch } from '../lib/publish.js';

// Note : la logique métier (scraping, SSE, modale prompt, import JSON) reste dans ce fichier.
// Le markup HTML est repris quasi à l'identique depuis index.html.scraper-backup mais sans le <header>.

export async function render() {
    await requireAuth();

    const root = document.getElementById('appRoot');
    root.innerHTML = `
        <section class="scraper-page">
            <div class="server-status-banner card hidden" id="serverStatusBanner">
                <span class="warning-icon">⚠️</span>
                <div>
                    <h3>Serveur local non détecté</h3>
                    <p>Le scraper Playwright nécessite <code>server.py</code> lancé sur ton ordinateur. <a href="/install" data-link>Voir le guide</a>.</p>
                </div>
            </div>

            <!-- Reprendre EXACTEMENT le contenu de l'ancien <div class="app-body"> sans le <header> -->
            <div class="scraper-grid">
                <!-- COPIER ICI tout le HTML de la sidebar + main-content depuis index.html.scraper-backup -->
                <!-- Cf. step 2 -->
            </div>

            <!-- Bouton "Publier sur le hub" injecté dynamiquement après l'analyse -->
            <div id="publishArea" class="publish-area hidden">
                <h3>📤 Publier ces résultats sur le hub</h3>
                <input type="text" id="publishTitle" placeholder="Titre de la recherche (ex: Laptops gaming RTX 4060)" maxlength="120">
                <button id="btnPublish" class="btn btn-primary">Publier</button>
                <div id="publishStatus" class="muted"></div>
            </div>
        </section>
    `;

    // Vérifier la disponibilité du server local
    const localOk = await checkLocalServer();
    if (!localOk) {
        document.getElementById('serverStatusBanner').classList.remove('hidden');
    }

    // === BRANCHER LA LOGIQUE D'ORIGINE ===
    // Copier ici tout le contenu du app.js original (le bloc IIFE ou autonome)
    // qui gère form submit, EventSource SSE, modale prompt, import JSON, rendu cards.
    // Cf. step 3.
    initScraperLogic();

    // === BOUTON PUBLIER ===
    initPublishButton();
}

function initScraperLogic() {
    // À remplir au step 3 : reprendre app.js original ici, dans cette fonction.
}

function initPublishButton() {
    document.getElementById('btnPublish').addEventListener('click', async () => {
        const titleEl   = document.getElementById('publishTitle');
        const statusEl  = document.getElementById('publishStatus');
        const btn       = document.getElementById('btnPublish');
        const title = titleEl.value.trim() || `Recherche du ${new Date().toLocaleDateString('fr-FR')}`;
        if (!window.allResults || window.allResults.length === 0) {
            statusEl.textContent = 'Aucun résultat à publier.';
            return;
        }
        btn.disabled = true; statusEl.textContent = '⏳ Publication…';
        try {
            const profile = await getProfile();
            const modelName = window.lastModelUsed || 'inconnu';
            const modelType = (modelName.toLowerCase().includes('claude') || modelName.toLowerCase().includes('gpt') || modelName.toLowerCase().includes('gemini')) ? 'cloud' : 'local';
            const searchId = await publishSearch({
                title,
                criteria: window.lastCriteria || '',
                url_lbc: window.lastUrl || null,
                model_name: modelName,
                model_type: modelType,
                listings: window.allResults,
            });
            statusEl.innerHTML = `✅ Publiée ! <a href="/search/${searchId}" data-link>Voir la recherche</a>`;
        } catch (err) {
            statusEl.textContent = `❌ ${err.message}`;
            btn.disabled = false;
        }
    });
}
```

- [ ] **Step 2: Copier le markup HTML d'origine**

Ouvrir `index.html.scraper-backup` (créé à la task 3.1). Extraire le contenu entre `<div class="app-body">` et son `</div>` fermant, **en retirant le `<aside>` et `<main>` wrappés**. Tout coller dans le placeholder `<!-- COPIER ICI ... -->` de scraper.js (en tant que template literal).

Conseil : le markup étant volumineux (~150 lignes), le déclarer dans une fonction `scraperMarkup()` retournant une string template, et l'utiliser dans le template literal de `render()`.

- [ ] **Step 3: Copier la logique app.js d'origine**

Ouvrir l'ancien `app.js` (toujours présent dans le repo à ce stade, sera supprimé en step 4). Copier le contenu de l'IIFE principale dans `initScraperLogic()` de `scraper.js`. Adapter :
- Exposer `window.allResults`, `window.lastModelUsed`, `window.lastCriteria`, `window.lastUrl` (utilisés par initPublishButton)
- Quand l'analyse se termine (état `completed` ou import JSON terminé), afficher le bouton publier :
  ```js
  document.getElementById('publishArea').classList.remove('hidden');
  ```
- Tous les `document.getElementById('xxx')` continueront de fonctionner car les éléments sont injectés dans le DOM via le template au-dessus.

- [ ] **Step 4: Supprimer le vieux app.js**

```bash
git rm app.js
```

L'ancien fichier devient redondant — toute sa logique est maintenant dans `js/pages/scraper.js`.

- [ ] **Step 5: Retirer la route `/app.js` du server.py**

Modifier `server.py` (autour de la ligne 864) — supprimer `app.router.add_get('/app.js', app_handler)` puisque le frontend utilise désormais des modules ES6 servis depuis `/js/`.

Ajouter une route catch-all pour servir les fichiers de `js/` :
```python
async def static_js_handler(request):
    path = request.match_info['path']
    # Sécurité : empêcher path traversal
    if '..' in path or path.startswith('/'):
        return web.Response(status=403)
    full = os.path.join(os.path.dirname(__file__), 'js', path)
    if not os.path.exists(full) or not full.startswith(os.path.dirname(__file__)):
        return web.Response(status=404)
    return web.FileResponse(full, headers={'Content-Type': 'application/javascript'})
```

Et dans `create_app()` :
```python
app.router.add_get('/js/{path:.*}', static_js_handler)
```

- [ ] **Step 6: Commit**

```bash
git add js/pages/scraper.js server.py
git rm app.js
git commit -m "feat(scraper): migrate scraper UI to SPA page + serve js/ statics"
```

---

### Task 7.2 : Server-ping utility

**Files:**
- Create: `js/lib/server-ping.js`

- [ ] **Step 1: Écrire l'utility**

Créer `js/lib/server-ping.js` :
```javascript
// js/lib/server-ping.js
// Vérifie que server.py local tourne sur localhost:8080 (avec PNA preflight)

export async function checkLocalServer() {
    try {
        const resp = await fetch('http://localhost:8080/api/ping', {
            method: 'GET',
            mode: 'cors',
            cache: 'no-store',
        });
        if (!resp.ok) return false;
        const data = await resp.json();
        return data.status === 'ok';
    } catch (e) {
        return false;
    }
}

export const LOCAL_SERVER_URL = 'http://localhost:8080';
```

- [ ] **Step 2: Tester**

Avec `server.py` lancé, naviguer vers `/scraper` depuis le frontend hébergé local → le banner d'erreur ne doit pas apparaître.
Arrêter `server.py`, recharger `/scraper` → le banner doit apparaître.

- [ ] **Step 3: Commit**

```bash
git add js/lib/server-ping.js
git commit -m "feat(scraper): add local server ping detection"
```

---

### Task 7.3 : Publish library

**Files:**
- Create: `js/lib/publish.js`

- [ ] **Step 1: Écrire la lib**

Créer `js/lib/publish.js` :
```javascript
// js/lib/publish.js
// Publie une recherche + ses listings dans Supabase via le SDK JS.
// Le user doit être authentifié (RLS vérifie auth.uid()).

import { supa } from '../supabase-client.js';

/**
 * @param {{title, criteria, url_lbc, model_name, model_type, listings}} payload
 * @returns {Promise<string>} l'ID de la search créée
 */
export async function publishSearch(payload) {
    const { data: { user } } = await supa.auth.getUser();
    if (!user) throw new Error('Non authentifié');

    const listings = payload.listings || [];
    const notes  = listings.map(l => parseFloat(l.note_sur_100)).filter(n => !isNaN(n));
    const prices = listings.map(l => parseFloat(l.prix)).filter(p => !isNaN(p) && p > 0);
    const best_score = notes.length ? Math.max(...notes) : null;
    const min_price  = prices.length ? Math.min(...prices) : null;

    // 1. Insert la search
    const { data: search, error: e1 } = await supa.from('searches').insert({
        user_id: user.id,
        title: payload.title,
        criteria: payload.criteria || '',
        url_lbc: payload.url_lbc || null,
        model_name: payload.model_name,
        model_type: payload.model_type,
        listing_count: listings.length,
        best_score,
        min_price,
    }).select().single();
    if (e1) throw new Error('Échec création recherche : ' + e1.message);

    // 2. Bulk insert les listings (chunks de 100 pour éviter limit body size)
    if (listings.length) {
        const rows = listings.map(l => ({
            search_id: search.id,
            titre: l.titre || '',
            prix: parseFloat(l.prix) || null,
            url: l.url || null,
            note_sur_100: parseFloat(l.note_sur_100) || null,
            caracteristiques: l.caracteristiques || '',
            explication: l.explication || '',
            match_criteres: !!l.match_criteres,
        }));
        for (let i = 0; i < rows.length; i += 100) {
            const chunk = rows.slice(i, i + 100);
            const { error: e2 } = await supa.from('listings').insert(chunk);
            if (e2) throw new Error('Échec insertion annonces : ' + e2.message);
        }
    }

    return search.id;
}
```

- [ ] **Step 2: Test manuel**

Depuis `/scraper`, scraper une vraie recherche (ou importer un JSON), puis cliquer "Publier" avec un titre → vérifier dans Supabase Table Editor que la search et les listings sont créés.

- [ ] **Step 3: Commit**

```bash
git add js/lib/publish.js
git commit -m "feat(publish): add publishSearch() that pushes to Supabase"
```

---

### Task 7.4 : Exposer modelName et autres méta-données depuis scraper

**Files:**
- Modify: `js/pages/scraper.js` (initScraperLogic)

- [ ] **Step 1: Capturer les méta-données**

Dans le code de `initScraperLogic()` (copié de l'ancien app.js) :

**Lors du submit du form scraper** (et lors de l'import JSON), définir avant le scrape :
```javascript
window.lastModelUsed = document.getElementById('modelSelect').value;
window.lastCriteria  = document.getElementById('criteresInput').value.trim();
window.lastUrl       = document.getElementById('urlInput').value.trim();
```

**Lors de l'import JSON**, après parse :
```javascript
window.lastModelUsed = parsedJson.model_used || 'claude-3.5-sonnet';  // si le JSON le précise
window.lastCriteria  = document.getElementById('criteresInput').value.trim() || '(import JSON)';
window.lastUrl       = parsedJson.source_url || null;
```

**À la fin de l'analyse (status === 'completed')**, afficher le bouton publier :
```javascript
document.getElementById('publishArea').classList.remove('hidden');
```

- [ ] **Step 2: Commit**

```bash
git add js/pages/scraper.js
git commit -m "feat(scraper): expose metadata for publish flow"
```

---

### Task 7.5 : Styles CSS scraper page + publish area

**Files:**
- Modify: `style.css`

- [ ] **Step 1: Ajouter les styles**

Ajouter à la fin de `style.css` :
```css
/* ===== SCRAPER PAGE (re-wrap of existing styles) ===== */
.scraper-page { padding:24px; max-width:1400px; margin:0 auto; }
.scraper-grid { display:grid; grid-template-columns:320px 1fr; gap:20px; }
@media (max-width:900px) { .scraper-grid { grid-template-columns:1fr; } }
.server-status-banner { display:flex; gap:14px; align-items:center; padding:16px; margin-bottom:20px; background:rgba(239,68,68,0.08); border-left:4px solid #ef4444; }
.server-status-banner .warning-icon { font-size:28px; }
.server-status-banner h3 { margin:0 0 4px; }
.server-status-banner p { margin:0; font-size:13px; color:var(--text-muted,#aaa); }
.server-status-banner a { color:#a855f7; }

.publish-area { margin-top:24px; padding:20px; background:rgba(168,85,247,0.06); border:1px solid rgba(168,85,247,0.3); border-radius:12px; }
.publish-area h3 { margin:0 0 12px; }
.publish-area input[type=text] { width:100%; padding:10px 14px; margin-bottom:12px; border-radius:8px; border:1px solid var(--border-color,#333); background:var(--input-bg,#1a1a1a); color:var(--text-color,#fff); }
.publish-area #publishStatus { margin-top:10px; font-size:14px; }
.publish-area #publishStatus a { color:#a855f7; }
```

- [ ] **Step 2: Vérifier visuellement, commit**

```bash
git add style.css
git commit -m "style: add CSS for scraper page and publish area"
```

---

### Task 7.6 : Test end-to-end manuel publish flow

- [ ] **Step 1: Test "scrape local → publish"**

1. `python server.py` (lancé sur localhost:8080)
2. Ouvrir `http://localhost:8080/scraper` dans Chrome
3. Login admin
4. Lancer une analyse Ollama légère sur une URL LBC connue (1 page, modèle qwen2.5:0.5b)
5. Attendre les résultats
6. Saisir un titre "Test publish" → cliquer Publier
7. Vérifier que `#publishStatus` affiche "✅ Publiée ! Voir la recherche"
8. Cliquer le lien → arriver sur `/search/<id>` avec les bonnes annonces

- [ ] **Step 2: Test "import JSON → publish"**

1. Sur `/scraper`, cliquer "📥 Importer résultats IA (JSON)"
2. Sélectionner `leboncoin_ia_imported.json` existant
3. Vérifier les résultats
4. Saisir titre "Test import publish" → Publier
5. Vérifier dans Supabase Table Editor et sur `/hub` que la nouvelle recherche apparaît

- [ ] **Step 3: Test depuis URL hébergée**

Reporter ce test à après la Section 9 (déploiement GitHub Pages).

---

## Section 8 — Page /install statique

### Task 8.1 : Page install

**Files:**
- Create: `js/pages/install.js`

- [ ] **Step 1: Écrire la page**

Créer `js/pages/install.js` :
```javascript
// js/pages/install.js
// Guide d'installation accessible sans compte.

export async function render() {
    document.getElementById('appRoot').innerHTML = `
        <section class="install-page">
            <div class="install-card card">
                <h1>📦 Installation de LBC DealFinder Hub</h1>
                <p class="lead">Pour scraper Leboncoin, tu dois lancer un petit serveur Python sur ton ordi (le scraping ne marche pas depuis le cloud — Leboncoin bloque les serveurs). Une fois le serveur lancé, tout fonctionne depuis ce site.</p>

                <ol class="install-steps">
                    <li>
                        <h3>Télécharger Python 3.11+</h3>
                        <p>Si tu n'as pas Python : <a href="https://www.python.org/downloads/" target="_blank" rel="noopener">python.org/downloads</a> (cocher "Add to PATH" pendant l'install).</p>
                    </li>
                    <li>
                        <h3>Télécharger l'application</h3>
                        <p><a href="https://drive.google.com/REMPLACER_PAR_LIEN" target="_blank" rel="noopener" class="btn btn-primary">📥 Télécharger lbc-dealfinder.zip</a></p>
                        <p class="muted small">Le lien Drive est tenu à jour par l'admin. Si le lien est cassé, demande-lui directement.</p>
                    </li>
                    <li>
                        <h3>Décompresser et installer</h3>
                        <p>Double-clic sur <code>install.bat</code> (Windows) ou exécute <code>./install.sh</code> (Mac/Linux). Cela installe les dépendances Playwright + aiohttp.</p>
                    </li>
                    <li>
                        <h3>Lancer le serveur</h3>
                        <p>Double-clic sur <code>server.py</code> ou dans un terminal : <code>python server.py</code>. <strong>Garde la fenêtre ouverte.</strong></p>
                    </li>
                    <li>
                        <h3>Se connecter</h3>
                        <p>Reviens sur ce site et connecte-toi avec ton compte (créé via le lien d'invitation que tu as reçu).</p>
                    </li>
                </ol>

                <div class="install-warning card">
                    <h3>⚠️ Note pour Firefox / Safari</h3>
                    <p>Chrome et Edge fonctionnent directement. Sur Firefox et Safari, le site bloque les connexions HTTP→localhost (mixed content). <strong>Solution simple : utilise Chrome ou Edge pour le scraper.</strong> Tu peux toujours consulter le hub depuis n'importe quel navigateur.</p>
                </div>

                <p class="install-footer"><a href="/" data-link>← Retour à la connexion</a></p>
            </div>
        </section>
    `;
}
```

- [ ] **Step 2: Styles + commit**

Ajouter à `style.css` :
```css
/* ===== INSTALL PAGE ===== */
.install-page { padding:32px 20px; display:flex; justify-content:center; }
.install-card { max-width:720px; padding:40px; }
.install-card h1 { margin:0 0 16px; }
.install-card .lead { font-size:16px; color:var(--text-muted,#aaa); margin-bottom:32px; }
.install-steps { padding-left:0; list-style:none; counter-reset:step; }
.install-steps li { counter-increment:step; padding-left:48px; position:relative; margin-bottom:24px; }
.install-steps li::before { content:counter(step); position:absolute; left:0; top:0; width:32px; height:32px; line-height:32px; text-align:center; border-radius:50%; background:rgba(168,85,247,0.2); color:#c084fc; font-weight:700; }
.install-steps h3 { margin:4px 0 8px; }
.install-steps p  { margin:0 0 4px; color:var(--text-muted,#bbb); }
.install-steps code { background:rgba(255,255,255,0.08); padding:2px 6px; border-radius:4px; font-family:monospace; }
.install-warning { margin-top:32px; padding:20px; background:rgba(234,179,8,0.06); border-left:4px solid #eab308; }
.install-warning h3 { margin:0 0 8px; }
.install-warning p { margin:0; font-size:14px; }
.install-footer { margin-top:32px; text-align:center; }
.install-footer a { color:#a855f7; text-decoration:none; }
.small { font-size:12px; }
```

```bash
git add js/pages/install.js style.css
git commit -m "feat(install): add installation guide page"
```

---

### Task 8.2 : Préparer le ZIP de distribution

**Files:**
- Create: `install.bat`
- Create: `install.sh`
- Create: `README-rapide.txt`

- [ ] **Step 1: Créer install.bat**

```bat
@echo off
echo === Installation de LBC DealFinder Hub ===
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python non trouve. Installe Python 3.11+ depuis https://python.org/downloads
    pause
    exit /b 1
)
echo [1/2] Installation des dependances Python...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] pip a echoue. Verifie ta connexion internet.
    pause
    exit /b 1
)
echo [2/2] Installation de Chromium pour Playwright...
playwright install chromium
echo.
echo === Installation terminee ! ===
echo.
echo Pour lancer le serveur : double-clic sur server.py ou tape : python server.py
echo Puis ouvre dans Chrome : https://VOTRE-GITHUB-USER.github.io/lbc-hub
pause
```

- [ ] **Step 2: Créer install.sh**

```bash
#!/bin/bash
set -e
echo "=== Installation de LBC DealFinder Hub ==="
if ! command -v python3 &> /dev/null; then
    echo "[ERREUR] python3 non trouvé. Installe Python 3.11+ depuis https://python.org/downloads"
    exit 1
fi
echo "[1/2] Installation des dépendances..."
pip3 install -r requirements.txt
echo "[2/2] Installation de Chromium pour Playwright..."
playwright install chromium
echo
echo "=== Installation terminée ! ==="
echo "Pour lancer : python3 server.py"
echo "Puis ouvre dans Chrome : https://VOTRE-GITHUB-USER.github.io/lbc-hub"
```

```bash
chmod +x install.sh
```

- [ ] **Step 3: Créer README-rapide.txt**

```
LBC DealFinder Hub — Guide rapide
==================================

1. Double-clic sur install.bat (Windows) ou ./install.sh (Mac/Linux)
2. Double-clic sur server.py (ou : python server.py dans un terminal)
3. Ouvre Chrome et va sur : https://VOTRE-GITHUB-USER.github.io/lbc-hub
4. Connecte-toi avec le lien d'invitation reçu

Garde la fenêtre du serveur ouverte tant que tu utilises le scraper.

Problème ? Contacte l'admin.
```

- [ ] **Step 4: Commit**

```bash
git add install.bat install.sh README-rapide.txt
git commit -m "feat(install): add install scripts and quick README for distribution"
```

Note : créer le ZIP manuellement lors du déploiement (Task 9.4).

---

## Section 9 — Déploiement GitHub Pages

### Task 9.1 : Créer le repo GitHub et configurer Pages

- [ ] **Step 1: Créer un repo public**

Sur github.com :
- Nouveau repo : `lbc-hub` (public, sinon Pages payant)
- Ne pas initialiser (on a déjà un repo local)

- [ ] **Step 2: Push le repo local**

```bash
git remote add origin https://github.com/<USER>/lbc-hub.git
git branch -M main
git push -u origin main
```

- [ ] **Step 3: Activer GitHub Pages**

Settings → Pages :
- Source : "GitHub Actions" (pas branch direct, on va utiliser un workflow)

---

### Task 9.2 : Workflow GitHub Actions deploy

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Créer le workflow**

```yaml
name: Deploy GitHub Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: true

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - name: Prepare deploy directory
        run: |
          mkdir -p _site
          cp index.html style.css 404.html _site/
          cp -r js _site/
      - uses: actions/upload-pages-artifact@v3
        with:
          path: _site
      - id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: Commit + push**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Pages deploy workflow"
git push
```

- [ ] **Step 3: Vérifier le run**

Onglet Actions sur GitHub → le workflow doit run et déployer.
URL finale : `https://<USER>.github.io/lbc-hub/`.

---

### Task 9.3 : Page 404 fallback pour SPA

**Files:**
- Create: `404.html`

- [ ] **Step 1: Créer le 404 fallback**

GitHub Pages sert 404.html pour toute route inconnue. On l'utilise pour rediriger vers `index.html` en preservant le path :

Créer `404.html` :
```html
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>LBC Hub</title>
<script>
// Single Page Apps for GitHub Pages
// https://github.com/rafgraph/spa-github-pages
(function(l) {
    if (l.search[1] === '/' ) {
        var decoded = l.search.slice(1).split('&').map(function(s) {
            return s.replace(/~and~/g, '&');
        }).join('?');
        window.history.replaceState(null, null, l.pathname.slice(0, -1) + decoded + l.hash);
    }
}(window.location));
// Redirige immédiatement vers index.html en encodant le path
var pathSegments = window.location.pathname.split('/').filter(Boolean);
var repoName = pathSegments[0] || '';
var subPath = pathSegments.slice(1).join('/');
window.location.replace('/' + repoName + '/?/' + subPath + window.location.search + window.location.hash);
</script>
</head>
<body></body>
</html>
```

Et ajouter au début de `index.html`, juste après `<head>` :
```html
<script>
// Restore SPA route from 404 fallback
(function(l) {
    if (l.search[1] === '/' ) {
        var decoded = l.search.slice(1).split('&').map(function(s){return s.replace(/~and~/g, '&');}).join('?');
        window.history.replaceState(null, null, l.pathname.slice(0, -1) + decoded + l.hash);
    }
}(window.location));
</script>
```

- [ ] **Step 2: Adapter le router au repo prefix**

Le router contient déjà `path.replace(/^\/lbc-hub/, '')` (cf. Task 3.3) — vérifier que le prefix `/lbc-hub` correspond au nom du repo réel. Si différent, ajuster.

- [ ] **Step 3: Commit + push**

```bash
git add 404.html index.html js/router.js
git commit -m "feat(spa): add 404 fallback for GitHub Pages routing"
git push
```

- [ ] **Step 4: Tester le déploiement**

Aller sur `https://<USER>.github.io/lbc-hub/` :
- Page login s'affiche
- Login avec compte admin → arrive sur /hub
- Cliquer sur une recherche → URL `/lbc-hub/search/<id>` fonctionne
- Refresh (F5) sur cette URL → la page se recharge correctement (via 404 fallback)
- Test scraper : depuis le site hébergé HTTPS, naviguer vers `/scraper` avec `server.py` lancé localement → le ping doit fonctionner (Chrome/Edge gèrent HTTPS→http://localhost en exception)

---

### Task 9.4 : Construire le ZIP de distribution

- [ ] **Step 1: Préparer le contenu**

Créer un dossier de release (par exemple `release/lbc-dealfinder/`) contenant :
```
lbc-dealfinder/
├── server.py
├── requirements.txt
├── install.bat
├── install.sh
├── README-rapide.txt
└── scraper_ia.py  (si toujours nécessaire — sinon retirer)
```

- [ ] **Step 2: Zipper**

PowerShell :
```powershell
Compress-Archive -Path release/lbc-dealfinder/* -DestinationPath release/lbc-dealfinder.zip -Force
```

- [ ] **Step 3: Upload sur Google Drive**

- Upload `lbc-dealfinder.zip` sur ton Drive
- Click droit → "Share" → "Anyone with the link" → "Viewer"
- Copier le lien
- Coller le lien dans `js/pages/install.js` (remplacer `REMPLACER_PAR_LIEN`)

- [ ] **Step 4: Re-déployer**

```bash
git add js/pages/install.js
git commit -m "feat(install): update Drive ZIP link"
git push
```

Le workflow GitHub Actions redéploie automatiquement.

---

## Tests finaux et checklist de livraison

### Test E2E complet

- [ ] Admin se déconnecte
- [ ] Admin crée un user de test via Dashboard Supabase (cf. supabase/admin-snippets.md)
- [ ] Admin crée une invitation SQL et copie le token
- [ ] Admin partage l'URL `/invite/<TOKEN>` avec le user de test
- [ ] User de test ouvre l'URL → redirige vers `/` (login)
- [ ] User de test se login → arrive sur `/invite/<TOKEN>`
- [ ] User saisit un pseudo → arrive sur `/hub`
- [ ] User va sur `/scraper`, lance une analyse, publie → la card apparaît dans le feed admin **en temps réel** (via Realtime)
- [ ] Admin clique la card → arrive sur `/search/<id>`, voit les listings du user de test
- [ ] Admin partage l'URL `/search/<id>` à un 3ᵉ user (s'il en avait un) → fonctionne après login

### Performance / sanity

- [ ] Lighthouse audit sur `/hub` : score > 80 en performance
- [ ] Pas d'erreur console côté frontend
- [ ] Pytest passe : `pytest tests/ -v`

### Commit de version

```bash
git tag v1.0.0-phase1
git push --tags
```

---

## Annexe : Variables d'environnement et secrets

- **Supabase anon key** : publique, en clair dans `js/supabase-client.js`
- **Supabase service_role key** : NE JAMAIS COMMIT, à conserver dans un password manager
- **Supabase project URL** : public, en clair dans `js/supabase-client.js`
- **Admin DB password** : password manager
- **Lien Google Drive** : public mais en clair dans `js/pages/install.js`

Aucun `.env` requis pour la Phase 1 (frontend pur côté hébergé, server.py reste local sans secret).

---

## Notes pour l'exécution

1. **Ordre des sections** : suivre l'ordre 1→9 — chaque section dépend de la précédente.
2. **Tests pragmatiques** : seule la Section 2 a des tests automatisés (pytest). Le reste est testé manuellement (le projet est petit, vanilla JS, et les Supabase RPC sont déjà testés par RLS).
3. **Si une étape Supabase manuelle est bloquante** (ex: création de user via Dashboard), demander confirmation au User avant de l'exécuter.
4. **Cred Supabase** : à la Task 3.2, demander au user les vraies clés (URL + anon key) — ne pas inventer de placeholders en prod.
5. **Lien Drive** : à la Task 9.4, demander au user le lien réel — placeholder en attendant.
6. **Subagent dispatching** : les sections 1, 4-5, 6, 8 sont relativement indépendantes une fois que la 2 et la 3 sont faites. Possible de paralléliser après section 3.

---

## Décisions / Évolutions à intégrer en Phase 2

> Section ajoutée pendant l'exécution de la Phase 1 — à transformer en tâches concrètes lors du plan Phase 2.

### D-01 — Retirer l'analyse Ollama locale (date décision : 2026-05-27)

**Contexte** : pour faciliter l'onboarding des amis dans le hub, Tristan veut éliminer la dépendance à Ollama. L'install reste légère (Python + Playwright pour le scraping), mais l'IA d'analyse passe systématiquement par Claude.ai via le workflow "Générer le Prompt" → copie-colle dans Claude.ai → import du JSON.

**Ce qui reste (= Phase 2 conserve)** :
- `server.py` avec Playwright (le scraping LBC reste local pour respecter les ToS et éviter la détection)
- Le workflow "Générer le Prompt pour Claude.ai" (`btnShowPrompt`)
- L'endpoint `POST /api/import-results` + la pipeline d'import JSON côté UI
- Le schéma DB tel quel (la colonne `model_type` reste utile : différencie `cloud` vs `local` historique)

**Ce qu'il faut retirer** :
- `OLLAMA_API_URL`, `DEFAULT_MODEL`, `analyser_description_ia()` dans [server.py](../../server.py)
- L'endpoint `GET /api/models` (liste des modèles Ollama)
- La phase "IA ANALYSIS PHASE" dans `run_pipeline_task()` — `server.py` se contente d'écrire `leboncoin_brut.json` puis renvoie le status `scrape_completed` (à inventer) au lieu de chaîner l'analyse
- L'option "♻️ Ré-analyser les annonces déjà scrapées" (n'a plus de sens sans Ollama local)
- Le `<select>` "Modèle IA (Ollama)" dans la sidebar Configuration de [js/pages/scraper.js](../../js/pages/scraper.js)
- L'helper [js/lib/server-ping.js](../../js/lib/server-ping.js) garde son rôle (détecter le serveur local), mais sa logique de "modèles Ollama chargés" disparaît

**Nouveau flow scraper UI** :
1. User entre URL LBC + critères dans Configuration
2. Bouton "Lancer le Scraping" (renommé depuis "Lancer l'Analyse") → server.py scrape uniquement
3. Quand le scrape est terminé → UI affiche "✅ X annonces brutes prêtes" + bouton **"📋 Copier le prompt pour Claude.ai"** (active automatiquement)
4. User colle dans Claude.ai, récupère le JSON, l'importe → UI affiche les annonces notées
5. Bouton **"📤 Publier sur le hub"** apparaît (avec `model_type: 'cloud'` forcé)

**Impact sur les utilisateurs existants** :
- Les anciennes recherches publiées avec `model_type: 'local'` restent en DB et s'affichent normalement (bandeau gris pour la rétro-compat — à garder dans `feed-card.js`)
- L'UX disclaimer "modèle cloud = précision élevée" devient redondant (toujours cloud) → à retirer aussi

**Estimation** : ~1 demi-journée (suppressions + simplification UI + retest 7a/7b).

**Pré-requis** : Phase 1 stable + Tristan a validé l'expérience de bout-en-bout avec ses amis.
