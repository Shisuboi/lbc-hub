-- ============================================================================
-- 2026-06-05 — Journal de trading PARTAGÉ (remplace le dashboard privé).
-- Un deal = un cycle Contacté → Acheté → Revendu. Lecture par tout le groupe,
-- écriture réservée à l'auteur ou à un admin.
-- ============================================================================

create table if not exists public.trades (
    id              uuid primary key default gen_random_uuid(),
    -- FK vers profiles (et NON auth.users) : PostgREST joint trades→profiles via cette FK
    -- pour l'embed `author:profiles(...)`. profiles.id == auth.uid() (convention projet).
    user_id         uuid not null references public.profiles(id) on delete cascade,
    opportunity_id  uuid references public.opportunities(id) on delete set null,
    title           text not null check (char_length(title) between 1 and 200),
    status          text not null default 'contacted'
                       check (status in ('contacted', 'bought', 'sold')),
    buy_price       numeric(10,2) check (buy_price is null or buy_price >= 0),
    sell_price      numeric(10,2) check (sell_price is null or sell_price >= 0),
    bought_at       date,
    sold_at         date,
    notes           text,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists trades_user_id_idx       on public.trades (user_id);
create index if not exists trades_opportunity_id_idx on public.trades (opportunity_id);
create index if not exists trades_updated_idx        on public.trades (updated_at desc);

alter table public.trades enable row level security;

drop policy if exists "trades_select_all" on public.trades;
create policy "trades_select_all" on public.trades
    for select to authenticated using (true);

drop policy if exists "trades_insert_own" on public.trades;
create policy "trades_insert_own" on public.trades
    for insert to authenticated
    with check ((select auth.uid()) = user_id);

drop policy if exists "trades_update_own_or_admin" on public.trades;
create policy "trades_update_own_or_admin" on public.trades
    for update to authenticated
    using (
        (select auth.uid()) = user_id
        or exists (select 1 from public.profiles p
                   where p.id = (select auth.uid()) and p.role = 'admin')
    );

drop policy if exists "trades_delete_own_or_admin" on public.trades;
create policy "trades_delete_own_or_admin" on public.trades
    for delete to authenticated
    using (
        (select auth.uid()) = user_id
        or exists (select 1 from public.profiles p
                   where p.id = (select auth.uid()) and p.role = 'admin')
    );

create or replace function public.touch_trades_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

drop trigger if exists trg_trades_touch on public.trades;
create trigger trg_trades_touch before update on public.trades
    for each row execute function public.touch_trades_updated_at();
