-- ============================================================================
-- 2026-06-01 — Phase C-1 / Favoris sur item (opportunité)
-- Remplace l'ancien favori-sur-recherche (table `favorites`, laissée en place).
-- Best practices Supabase : RLS (select auth.uid()) wrappé, index FK.
-- ============================================================================
create table if not exists public.item_favorites (
    user_id        uuid not null references public.profiles(id) on delete cascade,
    opportunity_id uuid not null references public.opportunities(id) on delete cascade,
    created_at     timestamptz not null default now(),
    primary key (user_id, opportunity_id)
);
create index if not exists item_favorites_user_idx on public.item_favorites (user_id);

alter table public.item_favorites enable row level security;

drop policy if exists "item_fav_select_own" on public.item_favorites;
create policy "item_fav_select_own" on public.item_favorites
    for select to authenticated using ((select auth.uid()) = user_id);

drop policy if exists "item_fav_insert_own" on public.item_favorites;
create policy "item_fav_insert_own" on public.item_favorites
    for insert to authenticated with check ((select auth.uid()) = user_id);

drop policy if exists "item_fav_delete_own" on public.item_favorites;
create policy "item_fav_delete_own" on public.item_favorites
    for delete to authenticated using ((select auth.uid()) = user_id);
