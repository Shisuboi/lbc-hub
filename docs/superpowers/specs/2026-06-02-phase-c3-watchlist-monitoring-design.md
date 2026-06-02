# Phase C-3 — Watchlist : gestion + monitoring live

> Date : 2026-06-02
> Étend la spec Phase C (`2026-06-01-phase-c-hub-opportunites-design.md` §8 « Watchlist »).
> Statut : design validé, à implémenter.

## 1. Objectif

La page `/watchlist` (aujourd'hui un placeholder) devient l'écran qui montre **ce que le PC
(moteur `--auto`) est en train de scruter**, avec des **stats live**, ET permet de **gérer** les
recherches surveillées (ajout / activation / pause / édition).

Deux dimensions :
1. **Monitoring live** : la recherche active, l'état du PC (en ligne / hors ligne), le débit de
   nouvelles annonces/min, la dernière passe, le cumul d'annonces vues, les blocages récents.
2. **Gestion** : liste de toutes les recherches, ajout, activer (une seule active à la fois),
   mettre en pause, éditer / supprimer (siennes, ou n'importe laquelle si admin).

## 2. Contrainte d'architecture (le « pourquoi » du design)

- Le moteur (`--auto`) n'écrit dans **Supabase** que les `opportunities` (et lit
  `watchlist_searches`). Sa télémétrie de scraping (`scrape_log`) vit dans le **SQLite local**
  du PC (`lbc_brain.sqlite3`).
- Le front (GitHub Pages) **ne lit que Supabase** — il ne peut pas voir le SQLite local.

➡️ Pour afficher des stats live sur le hub partagé, **le moteur doit publier une télémétrie
légère dans Supabase**. C'est l'écart par rapport à la spec Phase C §8 qui disait « aucune
modification moteur nécessaire » (vrai uniquement pour la version *gestion seule*).

### Approche retenue (parmi 3 évaluées)

**Table `scrape_heartbeats` dédiée + heartbeat périodique + temps réel.** Le moteur upsert une
ligne de télémétrie toutes les ~15 s ; le front s'abonne en realtime (même pattern que les
commentaires C-2).

Rejetées :
- **Colonnes sur `watchlist_searches` + polling** : mélange télémétrie volatile et config
  éditable par les membres (churn RLS/realtime, propriété confuse), polling moins live.
- **Endpoint `server.py` lu par le front** : ne marche que pour quelqu'un sur le PC (localhost) ;
  les autres membres du hub ne verraient rien → casse le modèle « hub partagé ».

## 3. Modèle de données

### Supabase — nouvelle table `scrape_heartbeats`

```sql
create table public.scrape_heartbeats (
  search_id        uuid primary key references public.watchlist_searches(id) on delete cascade,
  heartbeat_at     timestamptz not null,   -- dernier "tick" du moteur (~15s)
  last_pass_at     timestamptz,            -- fin de la dernière passe de scrape
  new_ads_per_min  float default 0,        -- moyenne glissante (calculée par le moteur)
  ads_seen_total   int   default 0,        -- cumul d'annonces uniques vues pour cette recherche
  blocked_recent   int   default 0,        -- blocages Datadome récents (fenêtre glissante)
  updated_at       timestamptz not null default now()
);
```

- **Une ligne par recherche**, clé = `search_id`. Le moteur ne met à jour que la recherche
  **active** (une seule tourne à la fois).
- **RLS** : `select` ouvert à tous les membres authentifiés ; **aucune policy d'écriture** → seul
  le moteur écrit via la clé `service_role` (qui bypass RLS, comme pour `opportunities`). Les
  membres ne peuvent jamais fausser la télémétrie.
- **Realtime** : ajouter la table à la publication `supabase_realtime`.

### Supabase — RPC + RLS (repris de la spec Phase C §8, à livrer ici)

```sql
create or replace function public.set_active_watchlist(p_search_id uuid)
returns void language plpgsql security definer as $$
begin
  update public.watchlist_searches set active = false where active;
  update public.watchlist_searches set active = true where id = p_search_id;
end; $$;
```

- `SECURITY DEFINER` → n'importe quel membre peut basculer la recherche active (contrôle
  collaboratif du PC partagé), de façon **atomique** (invariant « ≤ 1 active » garanti).
- Mettre en pause = `update active=false` sur sa propre ligne (RLS update-own).
- **Override admin** : ajouter policies `update`/`delete` sur `watchlist_searches` autorisant un
  profil `role = 'admin'` à éditer/supprimer n'importe quelle recherche.

### Local (SQLite Brain) — `engine/db.py`

- `scrape_log` existe déjà (`search_id, last_run_at, status, blocked_count`). **Ajouter** colonne
  `new_ads INTEGER DEFAULT 0` (auto-créée au démarrage si absente).
- `log_scrape(..., new_ads=n)` stocke le nb d'annonces neuves de la passe.
- ⚠️ `seen_ads` est **global** (clé `ad_id`, sans `search_id` — dédup toutes recherches
  confondues) : il ne permet PAS un cumul par recherche. Le cumul par recherche se dérive donc de
  `scrape_log` (somme des `new_ads` pour ce `search_id`), pas de `seen_ads`.

## 4. Déduction des stats

- **online / offline** = fraîcheur de `heartbeat_at` de la recherche active, calculée **côté
  client** : `< 45 s` → 🟢 en ligne, sinon ⚫ hors ligne (avec « depuis X »).
- **nouvelles annonces/min** = somme des `new_ads` des passes sur les 10 dernières min ÷ 10,
  calculée **par le moteur** et publiée prête à l'emploi (`new_ads_per_min`). Mesure la **vitesse
  d'apparition de nouvelles annonces sur Leboncoin** pour cette recherche (chaleur du créneau),
  pas la vitesse machine.
- **cumul vues** (`ads_seen_total`) = somme des `new_ads` de `scrape_log` pour cette recherche
  (annonces uniques que cette recherche a fait remonter depuis toujours).
- **dernière passe / blocages** = lus directement de `scrape_log`.

## 5. Changements moteur (`engine/`, best-effort)

La télémétrie ne doit **jamais** faire planter le scraping.

| Fichier | Changement |
|---|---|
| `engine/db.py` | colonne `scrape_log.new_ads` ; `log_scrape(new_ads=…)` ; lectures (toutes sur `scrape_log`) : `new_ads_rate(search_id, window_s=600)`, `ads_seen_total(search_id)` (somme des `new_ads`), `last_pass_at(search_id)`, `blocked_recent(search_id, window_s=600)` |
| `engine/scheduler.py` | `process_search` fait remonter le nb de neuves de la passe → `log_scrape(..., new_ads=n)` (modif ciblée, pas de changement de comportement) |
| `engine/supa.py` | `upsert_heartbeat(payload)` → upsert PostgREST sur `scrape_heartbeats` (clé `search_id`), best-effort : Supabase down → log + skip (pas d'outbox, donnée volatile, la passe suivante corrige) |
| `engine/telemetry.py` (nouveau) | `heartbeat_worker` : coroutine, tick ~15 s — récupère la recherche active, calcule les stats depuis le Brain, `heartbeat_at = now`, upsert |
| `server.py` (mode `--auto`) | lance `heartbeat_worker` comme 3ᵉ tâche, en parallèle de `run_engine` + `enrichment_worker` |

- Le heartbeat est **indépendant des passes** → l'indicateur online reflète que le **process** est
  vivant même au milieu d'un scrape lent.
- Démarré **uniquement** en mode `--auto`. Aucun impact sur le scrape manuel ni l'API HTTP.

## 6. Frontend

### `js/lib/watchlist.js` (nouveau)

- `listSearches()` (toutes, jointes à l'auteur), `createSearch()`, `updateSearch()`,
  `deleteSearch()`.
- `setActive(searchId)` → RPC `set_active_watchlist` ; `pause(searchId)` → `update active=false`.
- `getHeartbeats()` + `subscribeHeartbeats(cb)` → realtime sur `scrape_heartbeats` (pattern
  `comments.js`).

### `js/pages/watchlist.js` (remplace le placeholder)

DA glassmorphism existante (tokens `style.css`). Deux blocs :

1. **Panneau live** (en haut) — la recherche **active** :
   - titre + auteur + lien LBC ;
   - **état PC** : `🟢 PC actif (il y a 8 s)` / `⚫ PC hors ligne (depuis 5 min)` — recalculé par un
     timer client (~5 s) à partir de `heartbeat_at` → bascule en offline tout seul si le PC
     s'arrête ;
   - **nouvelles annonces/min**, **dernière passe**, **cumul vues**, **blocages récents** ;
   - mis à jour en **temps réel** (abonnement `scrape_heartbeats`) ;
   - si aucune recherche active → message « aucune recherche en cours ».

2. **Gestion** (en dessous) — liste de **toutes** les recherches :
   - par ligne : titre, source, auteur, état `✅ en cours` / `⏸️ en pause`, actions **Activer** /
     **Mettre en pause**, **Éditer** / **Supprimer** (siennes, ou n'importe laquelle si admin) ;
   - **formulaire d'ajout** : titre + URL Leboncoin (plateforme déduite) + seuils de marge par
     défaut ;
   - après une action, la liste se rafraîchit ; le panneau live suit via realtime.

### `style.css`

Bloc de styles pour le panneau live + les lignes de gestion, dans la continuité des tokens DA
déjà en place (feed / item / comments).

## 7. Migration Supabase

Un fichier `supabase/migrations/2026-06-02-phase-c3-watchlist.sql` :
- table `scrape_heartbeats` + RLS (`select` membres, pas d'écriture) ;
- ajout `scrape_heartbeats` à la publication `supabase_realtime` ;
- RPC `set_active_watchlist` ;
- policies override admin sur `update`/`delete` de `watchlist_searches`.

⚠️ À appliquer **à la main** dans le SQL Editor (convention projet), comme les migrations
précédentes.

## 8. Tests (convention projet : pas de tests frontend auto)

- **pytest** : couvrir les nouvelles lectures du Brain (`new_ads_rate`, `ads_seen_total`,
  `last_pass_at`, `blocked_recent`) et `log_scrape(new_ads=…)` sur une base SQLite temporaire.
- **E2E manuel** (check-list) :
  - moteur `--auto` lancé → `/watchlist` affiche 🟢 en ligne, débit annonces/min, dernière passe
    qui avance ;
  - couper le moteur → le badge bascule en ⚫ hors ligne tout seul (< 1 min) ;
  - activer une autre recherche → l'invariant ≤ 1 active tient, le panneau live suit ;
  - ajout / édition / suppression ; RLS membre vs admin (un membre ne supprime pas la recherche
    d'un autre, un admin oui) ;
  - non-régression feed / item / dashboard.

## 9. Hors scope

- Ventilation des opportunités par catégorie (🔴/🟡/⚫) sur le panneau live (écartée au cadrage).
- Historique / graphes de débit dans le temps (potentielle Phase D).
- Multi-PC simultanés : le modèle suppose un seul moteur actif (un PC scrape à la fois).
