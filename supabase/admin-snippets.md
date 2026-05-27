# Admin Snippets — Phase 1 (pas encore de UI /admin)

## Inviter un ami

1. Dashboard Supabase → **Authentication → Users → "Add user"** :
   - Email : `ami@example.com`
   - Password : générer un mdp aléatoire fort, le copier
   - Auto Confirm User : ON

2. Dashboard → **SQL Editor → New query** :
   ```sql
   insert into public.invitations(created_by)
   values ((select id from public.profiles where username = 'tristan'))
   returning token;
   ```

3. Récupérer le `token` retourné.

4. Communiquer à l'ami **par canal sécurisé** (Signal, etc.) :
   - L'URL : `https://shisuboi.github.io/lbc-hub/invite/<TOKEN>`
   - Le mdp temporaire (qu'il pourra changer plus tard via reset password)

5. L'ami ouvre l'URL → se connecte avec son email + mdp → choisit son pseudo → arrive sur le hub.

## Supprimer un user

```sql
delete from auth.users where email = 'ami@example.com';
-- cascade nettoie automatiquement profiles, searches, listings
```

## Lister les invitations actives

```sql
select token, created_at, expires_at, used_at,
       (select username from public.profiles p where p.id = invitations.used_by) as used_by_username
from public.invitations
order by created_at desc;
```

## Régénérer une invitation expirée pour un ami

```sql
insert into public.invitations(created_by)
values ((select id from public.profiles where username = 'tristan'))
returning token;
```

Puis renvoyer la nouvelle URL `/invite/<TOKEN>` à l'ami.

## Promouvoir un user en admin

```sql
update public.profiles
set role = 'admin'
where username = 'cible';
```
