-- ============================================================================
-- 2026-05-27 — Phase 3 / Badge "annonce expirée"
-- ============================================================================
-- Ajoute une colonne expired_at sur listings. N'importe quel user authentifié
-- peut basculer ce flag (on est entre potes, pas de risque de vandalisme).
-- ============================================================================

alter table public.listings
    add column if not exists expired_at timestamptz;

create index if not exists listings_expired_idx
    on public.listings(expired_at)
    where expired_at is not null;

-- Politique UPDATE : tout user authentifié peut éditer une annonce
-- (seul usage prévu : flipper expired_at). RLS empêche l'INSERT/DELETE
-- depuis ce rôle — seul publish.js peut insérer via le compte de l'auteur.
drop policy if exists "listings_update_authenticated" on public.listings;
create policy "listings_update_authenticated"
  on public.listings for update
  to authenticated
  using (true)
  with check (true);
