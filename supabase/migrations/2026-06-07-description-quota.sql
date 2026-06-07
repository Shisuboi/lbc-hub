-- 2026-06-07 — Description annonces + quota IA sur /watchlist
-- À appliquer À LA MAIN dans Supabase > SQL Editor.
--
-- 1. Colonne description sur opportunities : stocke le texte vendeur scrapé sur la page annonce.
-- 2. Colonne enrichment_paused sur scrape_heartbeats : true quand les quotas Gemini sont épuisés.

-- 1) Description vendeur (nullable, texte brut jusqu'à ~1500 chars)
alter table public.opportunities
  add column if not exists description text;

-- 2) Indicateur quota IA épuisé (default false, mis à jour par le heartbeat_worker)
alter table public.scrape_heartbeats
  add column if not exists enrichment_paused boolean default false;
