-- supabase/migrations/2026-05-29-pipeline-foundation.sql
-- Phase A — Fondation du pipeline de revente.
-- À exécuter dans Supabase Dashboard → SQL Editor → New query.

-- ===== WATCHLIST SEARCHES =====
create table if not exists public.watchlist_searches (
    id              uuid primary key default gen_random_uuid(),
    owner_id        uuid not null references public.profiles(id) on delete cascade,
    title           text not null,
    criteria        text default '',
    source_url      text not null,
    platform        text not null default 'leboncoin'
                    check (platform in ('leboncoin','ebay','vinted','other')),
    geo_postal      text,
    geo_radius_km   int,
    price_max       float,
    price_min       float,
    exclude_keywords text default '',
    min_margin_eur  float,
    min_margin_pct  float,
    active          boolean not null default true,
    created_at      timestamptz not null default now()
);
create index if not exists watchlist_owner_idx  on public.watchlist_searches(owner_id);
create index if not exists watchlist_active_idx on public.watchlist_searches(active) where active;

-- ===== OPPORTUNITIES =====
-- Champs IA nullable (remplis en Phase B). Upsert sur ad_id (idempotent).
create table if not exists public.opportunities (
    id                uuid primary key default gen_random_uuid(),
    ad_id             text not null unique,
    source_search_id  uuid references public.watchlist_searches(id) on delete set null,
    platform          text not null default 'leboncoin',
    title             text,
    price             float,
    url               text,
    image_url         text,
    location_city     text,
    location_postal   text,
    lat               float,
    lon               float,
    category          text check (category in ('urgent','interesting','passable')),
    resale_score      float,
    est_market_price  float,
    est_margin_eur    float,
    est_margin_pct    float,
    max_buy_price     float,
    is_lot            boolean,
    lot_unit_price    float,
    lot_notes         text,
    signals           jsonb,
    explanation       text,
    photo_verdict     text,
    price_dropped     boolean default false,
    previous_price    float,
    model_used        text,
    status            text not null default 'active',
    first_seen_at     timestamptz,
    scraped_at        timestamptz,
    created_at        timestamptz not null default now()
);
create index if not exists opp_created_idx  on public.opportunities(created_at desc);
create index if not exists opp_category_idx on public.opportunities(category);
create index if not exists opp_search_idx   on public.opportunities(source_search_id);

-- ===== RLS =====
alter table public.watchlist_searches enable row level security;
alter table public.opportunities enable row level security;

-- watchlist : tout membre authentifié lit (recherches partagées au groupe) ;
-- chacun n'écrit/édite que les siennes.
drop policy if exists "watchlist_select_all" on public.watchlist_searches;
create policy "watchlist_select_all" on public.watchlist_searches
    for select using (auth.role() = 'authenticated');
drop policy if exists "watchlist_insert_own" on public.watchlist_searches;
create policy "watchlist_insert_own" on public.watchlist_searches
    for insert with check (auth.uid() = owner_id);
drop policy if exists "watchlist_update_own" on public.watchlist_searches;
create policy "watchlist_update_own" on public.watchlist_searches
    for update using (auth.uid() = owner_id);
drop policy if exists "watchlist_delete_own" on public.watchlist_searches;
create policy "watchlist_delete_own" on public.watchlist_searches
    for delete using (auth.uid() = owner_id);

-- opportunities : lecture par tout membre authentifié ; AUCUNE écriture via anon/JWT
-- (seul le moteur écrit, et il passe par service_role qui bypass RLS).
drop policy if exists "opp_select_all" on public.opportunities;
create policy "opp_select_all" on public.opportunities
    for select using (auth.role() = 'authenticated');
