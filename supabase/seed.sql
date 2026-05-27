-- ============================================================
-- LBC Hub — Seed admin initial
-- À exécuter APRÈS schema.sql ET rls.sql
-- L'user auth doit déjà exister (créé via Dashboard → Authentication → Users)
-- ============================================================

-- Profil admin (Tristan)
insert into public.profiles(id, username, avatar_color, role)
values (
  'bcc4170c-49b9-410f-9f47-782e096ab513'::uuid,
  'tristan',
  'hsl(280, 65%, 55%)',
  'admin'
)
on conflict (id) do update set role = 'admin';

-- Première invitation (token à partager avec le premier ami)
insert into public.invitations(created_by)
values ('bcc4170c-49b9-410f-9f47-782e096ab513'::uuid)
returning token;
