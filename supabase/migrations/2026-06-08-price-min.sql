-- 2026-06-08 — Ajout de price_min aux recherches de la watchlist
-- À appliquer À LA MAIN dans Supabase > SQL Editor.

-- Ajout de la colonne price_min (float, optionnel) sur watchlist_searches
alter table public.watchlist_searches
  add column if not exists price_min float;
