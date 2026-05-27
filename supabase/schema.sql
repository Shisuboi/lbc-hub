-- ============================================================
-- LBC Hub — Schéma de base de données
-- À exécuter dans : Supabase Dashboard → SQL Editor → New query
-- ============================================================

-- ===== EXTENSIONS =====
create extension if not exists "pgcrypto";

-- ===== PROFILES =====
-- Extension de auth.users — stocke les méta-données métier
create table public.profiles (
    id            uuid primary key references auth.users(id) on delete cascade,
    username      text unique not null
                  check (char_length(username) between 3 and 24
                     and username ~ '^[a-z0-9_]+$'),
    avatar_color  text not null,
    role          text not null default 'user'
                  check (role in ('user', 'admin')),
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

create index invitations_unused_idx on public.invitations(token)
    where used_at is null;

-- ===== SEARCHES =====
create table public.searches (
    id            uuid primary key default gen_random_uuid(),
    user_id       uuid not null references public.profiles(id) on delete cascade,
    title         text not null check (char_length(title) between 1 and 120),
    criteria      text not null default '',
    source_url    text,                          -- URL source générique (pas url_lbc)
    platform      text not null default 'leboncoin'
                  check (platform in ('leboncoin', 'ebay', 'vinted', 'other')),
    model_name    text not null,
    model_type    text not null check (model_type in ('cloud', 'local')),
    listing_count int  not null default 0,
    best_score    float,
    min_price     float,
    scraped_at    timestamptz,                   -- Date du scraping (affichée partout)
    created_at    timestamptz not null default now()  -- Date d'insertion (logs uniquement)
);

create index searches_scraped_at_idx on public.searches(scraped_at desc nulls last);
create index searches_created_at_idx on public.searches(created_at desc);
create index searches_user_id_idx    on public.searches(user_id);
create index searches_platform_idx   on public.searches(platform);

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
