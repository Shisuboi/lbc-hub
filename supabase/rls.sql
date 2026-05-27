-- ============================================================
-- LBC Hub — Row Level Security policies + RPCs
-- À exécuter APRÈS schema.sql
-- ============================================================

-- ===== ACTIVER RLS =====
alter table public.profiles    enable row level security;
alter table public.invitations enable row level security;
alter table public.searches    enable row level security;
alter table public.listings    enable row level security;

-- ===== PROFILES =====
create policy "profiles_select_authenticated"
  on public.profiles for select to authenticated
  using (true);

create policy "profiles_insert_self"
  on public.profiles for insert to authenticated
  with check (auth.uid() = id);

create policy "profiles_update_own"
  on public.profiles for update to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id
    and role = (select role from public.profiles where id = auth.uid()));

-- ===== INVITATIONS =====
create policy "invitations_admin_select"
  on public.invitations for select to authenticated
  using ((select role from public.profiles where id = auth.uid()) = 'admin');

create policy "invitations_admin_insert"
  on public.invitations for insert to authenticated
  with check ((select role from public.profiles where id = auth.uid()) = 'admin');

-- ===== SEARCHES =====
create policy "searches_select_authenticated"
  on public.searches for select to authenticated
  using (true);

create policy "searches_insert_own"
  on public.searches for insert to authenticated
  with check (auth.uid() = user_id);

create policy "searches_delete_own_or_admin"
  on public.searches for delete to authenticated
  using (
    auth.uid() = user_id
    or (select role from public.profiles where id = auth.uid()) = 'admin'
  );

-- ===== LISTINGS =====
create policy "listings_select_authenticated"
  on public.listings for select to authenticated
  using (true);

create policy "listings_insert_via_own_search"
  on public.listings for insert to authenticated
  with check (
    exists (
      select 1 from public.searches s
      where s.id = search_id and s.user_id = auth.uid()
    )
  );

-- ===== RPC : valider une invitation (accessible sans être connecté) =====
create or replace function public.validate_invitation(invitation_token uuid)
returns table (valid boolean, message text)
language plpgsql security definer set search_path = public
as $$
declare inv record;
begin
  select * into inv from public.invitations where token = invitation_token;
  if inv is null then
    return query select false, 'Invitation introuvable';
    return;
  end if;
  if inv.used_at is not null then
    return query select false, 'Invitation déjà utilisée';
    return;
  end if;
  if inv.expires_at < now() then
    return query select false, 'Invitation expirée';
    return;
  end if;
  return query select true, 'OK';
end;
$$;

grant execute on function public.validate_invitation(uuid) to anon, authenticated;

-- ===== RPC : finaliser le signup (choisir username + consommer invitation) =====
create or replace function public.consume_invitation(invitation_token uuid, new_username text)
returns json
language plpgsql security definer set search_path = public
as $$
declare
  inv             record;
  current_user_id uuid;
  avatar          text;
begin
  current_user_id := auth.uid();
  if current_user_id is null then
    raise exception 'Not authenticated';
  end if;

  -- Verrouille la ligne pour éviter double-usage concurrent
  select * into inv from public.invitations
    where token = invitation_token for update;

  if inv is null        then raise exception 'Invitation introuvable'; end if;
  if inv.used_at is not null then raise exception 'Invitation déjà utilisée'; end if;
  if inv.expires_at < now() then raise exception 'Invitation expirée'; end if;

  -- Couleur avatar aléatoire (HSL)
  avatar := 'hsl(' || floor(random() * 360)::text || ', 65%, 55%)';

  -- Crée le profil
  insert into public.profiles(id, username, avatar_color, role)
  values (current_user_id, new_username, avatar, 'user');

  -- Marque l'invitation consommée
  update public.invitations
    set used_by = current_user_id, used_at = now()
    where token = invitation_token;

  return json_build_object('username', new_username, 'avatar_color', avatar);
end;
$$;

grant execute on function public.consume_invitation(uuid, text) to authenticated;
