-- ============================================================================
-- 2026-06-01 — Phase 4 / Tableau de bord financier
-- ============================================================================
-- Table `transactions` : chaque user saisit ses achats / ventes d'articles
-- pour suivre son ROI sur la revente. Données STRICTEMENT privées (RLS).
--
-- Bonnes pratiques appliquées (skill supabase-postgres-best-practices) :
--   * RLS : auth.uid() wrappé dans (select auth.uid()) — évalué UNE fois par
--     requête au lieu d'une fois par ligne (~100x plus rapide sur grosses tables).
--   * Index systématique des colonnes FK (user_id, search_id) — Postgres ne les
--     crée pas tout seul ; sans index, les JOIN et ON DELETE CASCADE scannent tout.
--   * Contraintes CHECK pour garantir l'intégrité au niveau base.
-- ============================================================================

create table if not exists public.transactions (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users(id) on delete cascade,
    type        text not null check (type in ('achat', 'vente')),
    label       text not null check (char_length(label) between 1 and 200),
    amount      numeric(10, 2) not null check (amount > 0),
    date        date not null default current_date,
    search_id   uuid references public.searches(id) on delete set null,
    url         text,
    created_at  timestamptz not null default now()
);

-- Index composite : requête type de la page = "mes transactions, triées par date".
-- (user_id, date desc) couvre à la fois le filtre RLS et le tri.
create index if not exists transactions_user_date_idx
    on public.transactions (user_id, date desc);

-- Index sur la FK search_id (JOIN éventuel + ON DELETE SET NULL rapide).
create index if not exists transactions_search_id_idx
    on public.transactions (search_id);

alter table public.transactions enable row level security;

-- ── Policies granulaires, une par opération, réservées aux users authentifiés ──
-- (select auth.uid()) : le planner l'évalue une seule fois (InitPlan), pas par ligne.

drop policy if exists "transactions_select_own" on public.transactions;
create policy "transactions_select_own"
    on public.transactions for select
    to authenticated
    using ((select auth.uid()) = user_id);

drop policy if exists "transactions_insert_own" on public.transactions;
create policy "transactions_insert_own"
    on public.transactions for insert
    to authenticated
    with check ((select auth.uid()) = user_id);

drop policy if exists "transactions_update_own" on public.transactions;
create policy "transactions_update_own"
    on public.transactions for update
    to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

drop policy if exists "transactions_delete_own" on public.transactions;
create policy "transactions_delete_own"
    on public.transactions for delete
    to authenticated
    using ((select auth.uid()) = user_id);
