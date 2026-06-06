-- ============================================================================
-- 2026-06-06 — Nettoyage des tables legacy (Phase A ancienne + invitations)
--
-- Tables supprimées (aucune dépendance frontend depuis Phase C-5) :
--   * transactions  — remplacée par `trades` (Journal de trading Phase D)
--   * favorites     — ancienne, sur search_id (remplacée par item_favorites sur opportunity_id)
--   * listings      — annonces de l'ancien modèle manuel
--   * searches      — recherches de l'ancien modèle manuel
--   * invitations   — flow d'invitation remplacé par self-onboarding (Phase C)
--
-- RPCs supprimées :
--   * validate_invitation, consume_invitation
--
-- ⚠️  Ordre obligatoire : d'abord les tables qui référencent searches
--     (transactions, favorites, listings), ensuite searches, puis invitations.
-- ============================================================================

-- 1. transactions (référence searches.id via FK ON DELETE SET NULL)
drop table if exists public.transactions cascade;

-- 2. favorites ancienne (référence searches.id + listings.id)
--    On la distingue de item_favorites (vivante, sur opportunity_id) par le nom de contrainte.
drop table if exists public.favorites cascade;

-- 3. listings (peut référencer searches.id)
drop table if exists public.listings cascade;

-- 4. searches (table mère legacy)
drop table if exists public.searches cascade;

-- 5. invitations (flow legacy, remplacé par create_self_profile)
drop table if exists public.invitations cascade;

-- 6. RPCs d'invitation legacy
drop function if exists public.validate_invitation(text);
drop function if exists public.consume_invitation(text);
