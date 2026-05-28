# Section 1 — Actions Supabase Dashboard à faire (sur le PC fixe)

> Toutes les actions manuelles côté **Supabase Dashboard** à réaliser **avant** de tester
> les Sections 6 (Favoris) et 8 (Annonces expirées) de `TESTING-phase2-3.md`.
>
> Tant que ces étapes ne sont pas faites :
> - Section 6 (favoris) : l'étoile ⭐ s'affiche mais ne persiste rien (try/catch silencieux)
> - Section 8 (expirées) : le bouton "🚫 Marquer expirée" plante avec `column "expired_at" does not exist`
>
> Les autres sections (2, 3, 4, 5, 7) peuvent être testées sans ces migrations,
> tant que la **Site URL** (étape 1.4) matche l'environnement testé.

---

## 1.1 — (Si besoin) Recréer le profil admin

⚠️ À faire **uniquement si** `tristanfranceschetti@gmail.com` n'apparaît plus en `role='admin'`
(incident possible suite à la Section 11 de Phase 1).

1. **Auth → Users** : vérifier que l'email existe. Sinon **Add user** → email + mdp solide + ✅ Auto Confirm Email
2. **SQL Editor → New query** :

```sql
insert into public.profiles (id, username, role, avatar_color)
select id, 'tristan', 'admin', '#a855f7'
from auth.users
where email = 'tristanfranceschetti@gmail.com'
on conflict (id) do update set role = 'admin', username = 'tristan';
```

3. Vérification :

```sql
select id, username, role from public.profiles where username = 'tristan';
```

Attendu : **1 ligne, `role = 'admin'`**.

---

## 1.2 — Migration : table `favorites`

**Pourquoi** : Section 6 — sans cette table, les boutons ⭐ sont silencieux.

**SQL Editor → New query → Run** :

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

**Attendu** : "Success. No rows returned".

**Sanity check** (nouvelle requête) :

```sql
select tablename from pg_tables where schemaname='public' and tablename='favorites';
```

→ 1 ligne `favorites`.

---

## 1.3 — Migration : colonne `expired_at` sur `listings`

**Pourquoi** : Section 8 — sans cette colonne, le toggle "🚫 Marquer expirée" plante.
La policy UPDATE autorise tout user authentifié à flagger une annonce (volontaire,
on est entre potes).

**SQL Editor → New query → Run** :

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

**Attendu** : pas d'erreur.

**Sanity check** :

```sql
select column_name from information_schema.columns
where table_schema='public' and table_name='listings' and column_name='expired_at';
```

→ 1 ligne, `expired_at`.

---

## 1.4 — Vérifier les URLs Auth

**Authentication → URL Configuration** :

- **Site URL** :
  - Si test en **prod** → `https://shisuboi.github.io/lbc-hub`
  - Si test en **local** → `http://localhost:8080`
- **Redirect URLs** (les 3 doivent être présentes) :
  - `https://shisuboi.github.io/lbc-hub/*`
  - `http://localhost:8080/*`
  - `http://localhost:8080/**`

**Attendu** : Site URL alignée avec l'environnement testé + les 3 Redirect URLs présentes.

---

## Une fois tout coché

Reviens dans la conversation et dis "Supabase OK" — on enchaîne sur les Sections 6 et 8
qui dépendaient de ces migrations.
