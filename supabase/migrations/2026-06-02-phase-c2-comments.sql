-- ============================================================================
-- 2026-06-02 — Phase C-2 / Commentaires par item (opportunité)
-- Best practices Supabase : RLS avec (select auth.uid()) wrappé, index FK,
-- realtime activé, replica identity full pour que les events UPDATE/DELETE
-- transportent l'ancien opportunity_id (nécessaire au filtrage realtime côté client).
-- ============================================================================
create table if not exists public.item_comments (
    id              uuid primary key default gen_random_uuid(),
    opportunity_id  uuid not null references public.opportunities(id) on delete cascade,
    user_id         uuid not null references public.profiles(id) on delete cascade,
    body            text not null check (char_length(body) between 1 and 2000),
    edited_at       timestamptz,
    created_at      timestamptz not null default now()
);
create index if not exists item_comments_opp_idx  on public.item_comments (opportunity_id, created_at);
create index if not exists item_comments_user_idx on public.item_comments (user_id);

alter table public.item_comments enable row level security;

-- Lecture : tous les membres connectés
drop policy if exists "item_comments_select_all" on public.item_comments;
create policy "item_comments_select_all" on public.item_comments
    for select to authenticated using (true);

-- Insertion : uniquement en son propre nom
drop policy if exists "item_comments_insert_own" on public.item_comments;
create policy "item_comments_insert_own" on public.item_comments
    for insert to authenticated with check ((select auth.uid()) = user_id);

-- Édition : uniquement son propre commentaire
drop policy if exists "item_comments_update_own" on public.item_comments;
create policy "item_comments_update_own" on public.item_comments
    for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

-- Suppression : le sien, OU n'importe lequel si admin
drop policy if exists "item_comments_delete_own_or_admin" on public.item_comments;
create policy "item_comments_delete_own_or_admin" on public.item_comments
    for delete to authenticated using (
        (select auth.uid()) = user_id
        or exists (
            select 1 from public.profiles p
            where p.id = (select auth.uid()) and p.role = 'admin'
        )
    );

-- Realtime : diffuser INSERT/UPDATE/DELETE de cette table
alter table public.item_comments replica identity full;
alter publication supabase_realtime add table public.item_comments;
