-- ============================================================================
-- 2026-06-05 (correctif) — Relation trades → profiles pour PostgREST.
-- La migration initiale faisait pointer trades.user_id vers auth.users(id), ce qui
-- empêchait l'embed `author:profiles(...)` côté frontend :
--   « Could not find a relationship between 'trades' and 'profiles' in the schema cache ».
-- On repointe la FK vers public.profiles(id) (comme item_comments). profiles.id == auth.uid().
-- À exécuter sur une base où la table trades a DÉJÀ été créée.
-- ============================================================================

alter table public.trades drop constraint if exists trades_user_id_fkey;

alter table public.trades
    add constraint trades_user_id_fkey
    foreign key (user_id) references public.profiles(id) on delete cascade;

-- Force PostgREST à recharger son cache de schéma (sinon la relation reste invisible).
notify pgrst, 'reload schema';
