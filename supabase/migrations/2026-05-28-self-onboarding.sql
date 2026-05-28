-- ============================================================
-- Self-service onboarding (Option B, v1.8.0)
-- L'admin n'a plus besoin de générer un token d'invitation. Il crée juste
-- le user auth dans Supabase Dashboard et envoie email/mdp à son pote.
-- Au premier login, le pote atterrit sur /onboarding et choisit son pseudo
-- via le RPC ci-dessous (qui crée la ligne dans public.profiles).
--
-- Le RPC consume_invitation est laissé en place pour la rétro-compat
-- des liens /invite/:token déjà envoyés.
-- ============================================================

create or replace function public.create_self_profile(new_username text)
returns json
language plpgsql security definer set search_path = public
as $$
declare
  current_user_id uuid;
  avatar          text;
begin
  current_user_id := auth.uid();
  if current_user_id is null then
    raise exception 'Not authenticated';
  end if;

  -- Empêche la double-création (idempotent côté UX)
  if exists (select 1 from public.profiles where id = current_user_id) then
    raise exception 'Profile already exists';
  end if;

  -- Validation pseudo (3-24, [a-z0-9_]) — identique au check de la table
  if new_username !~ '^[a-z0-9_]{3,24}$' then
    raise exception 'Pseudo invalide (3-24 caractères, lettres minuscules, chiffres ou _)';
  end if;

  -- Même logique d'avatar que consume_invitation
  avatar := 'hsl(' || floor(random() * 360)::text || ', 65%, 55%)';

  insert into public.profiles(id, username, avatar_color, role)
  values (current_user_id, new_username, avatar, 'user');

  return json_build_object('username', new_username, 'avatar_color', avatar);
end;
$$;

grant execute on function public.create_self_profile(text) to authenticated;
