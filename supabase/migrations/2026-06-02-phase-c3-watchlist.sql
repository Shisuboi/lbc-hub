-- Phase C-3 : télémétrie watchlist (scrape_heartbeats) + RPC "une seule active" + override admin.
-- À appliquer À LA MAIN dans Supabase > SQL Editor (convention projet).

-- 1) Table de télémétrie (volatile). Écrite UNIQUEMENT par le moteur via service_role.
create table if not exists public.scrape_heartbeats (
  search_id        uuid primary key references public.watchlist_searches(id) on delete cascade,
  heartbeat_at     timestamptz not null,
  last_pass_at     timestamptz,
  new_ads_per_min  float default 0,
  ads_seen_total   int   default 0,
  blocked_recent   int   default 0,
  updated_at       timestamptz not null default now()
);

alter table public.scrape_heartbeats enable row level security;

-- Lecture pour tous les membres authentifiés. AUCUNE policy d'écriture → seul service_role écrit.
drop policy if exists "heartbeats_select_authenticated" on public.scrape_heartbeats;
create policy "heartbeats_select_authenticated"
  on public.scrape_heartbeats for select
  to authenticated using (true);

-- Realtime : ⚠️ si "is already member of publication", ignorer l'erreur (déjà ajoutée).
alter publication supabase_realtime add table public.scrape_heartbeats;

-- 2) RPC : une seule recherche active à la fois (atomique).
create or replace function public.set_active_watchlist(p_search_id uuid)
returns void language plpgsql security definer as $$
begin
  update public.watchlist_searches set active = false where active;
  update public.watchlist_searches set active = true  where id = p_search_id;
end; $$;

-- 3) Override admin sur update/delete de watchlist_searches (en plus des policies own existantes).
drop policy if exists "watchlist_update_admin" on public.watchlist_searches;
create policy "watchlist_update_admin"
  on public.watchlist_searches for update to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));

drop policy if exists "watchlist_delete_admin" on public.watchlist_searches;
create policy "watchlist_delete_admin"
  on public.watchlist_searches for delete to authenticated
  using (exists (select 1 from public.profiles p where p.id = auth.uid() and p.role = 'admin'));
