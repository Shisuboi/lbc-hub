-- ============================================================================
-- 2026-05-27 — Phase 3 / Favoris
-- ============================================================================
-- Permet à chaque user de marquer des searches en favori.
-- Une favorite = (user_id, search_id) ; pas de duplicates possibles.
-- Cascade : si un user ou une search est supprimée, ses favorites disparaissent.
-- ============================================================================

create table if not exists public.favorites (
    user_id    uuid not null references auth.users(id) on delete cascade,
    search_id  uuid not null references public.searches(id) on delete cascade,
    created_at timestamptz not null default now(),
    primary key (user_id, search_id)
);

create index if not exists favorites_user_idx   on public.favorites(user_id);
create index if not exists favorites_search_idx on public.favorites(search_id);

alter table public.favorites enable row level security;

-- Chaque user gère uniquement ses propres favorites
drop policy if exists "favorites_select_own" on public.favorites;
create policy "favorites_select_own"
  on public.favorites for select
  to authenticated
  using (auth.uid() = user_id);

drop policy if exists "favorites_insert_own" on public.favorites;
create policy "favorites_insert_own"
  on public.favorites for insert
  to authenticated
  with check (auth.uid() = user_id);

drop policy if exists "favorites_delete_own" on public.favorites;
create policy "favorites_delete_own"
  on public.favorites for delete
  to authenticated
  using (auth.uid() = user_id);
