# Purge auto 30j — Design Spec

**Date :** 2026-06-04
**Statut :** validé

## Contexte

Supabase free tier = 500 Mo. La table `opportunities` grossit en continu (moteur tourne 24/7).
Il faut purger les opportunités trop vieilles pour éviter d'atteindre la limite.

## Objectif

Au démarrage du moteur (`server.py --auto`), supprimer de Supabase les opportunités dont
`created_at` dépasse `PURGE_DAYS` jours, **sauf** celles mises en favori par un membre.

## Décisions de design

| Question | Décision |
|---|---|
| Fréquence | Au démarrage du moteur uniquement (option "C") |
| Protection | Favoris (`item_favorites.opportunity_id`) uniquement — pas les commentaires |
| Brain SQLite | Inchangé (`seen_ads` conservé → l'ad ne sera pas re-publiée) |
| Seuil | Configurable via `.env` : `PURGE_DAYS=30` (défaut : 30) |

## Architecture

```
server.py --auto
  └─ await run_maintenance(supa, cfg)        ← nouveau, appelé une fois au boot
  └─ asyncio.gather(
       run_engine(...),
       enrichment_worker(...),
       heartbeat_worker(...),
     )
```

`run_maintenance` est la fonction publique du nouveau module `engine/maintenance.py`.
Elle est idempotente et best-effort : une erreur réseau est loggée mais ne bloque pas le démarrage.

## Module `engine/maintenance.py`

```python
async def run_maintenance(supa: Supa, cfg: Config) -> None:
    """Tâches de maintenance au démarrage du moteur --auto.

    Actuellement : purge des opportunités > PURGE_DAYS jours (sauf favoris).
    Extensible pour de futures tâches (recalcul stats, flush outbox supplémentaire…).
    """
    try:
        n = await purge_old_opportunities(supa, cfg.purge_days)
        print(f"[maintenance] purge: {n} opportunité(s) supprimée(s) (>{cfg.purge_days}j, hors favoris)")
    except Exception as exc:
        print(f"[maintenance] purge échouée (non bloquant) : {exc}")
```

## Logique de purge — `purge_old_opportunities(supa, days)`

Deux appels PostgREST successifs via le client `Supa` (service_role) :

### Étape 1 — Récupérer les IDs protégés

```
GET /rest/v1/item_favorites?select=opportunity_id
```

Retourne une liste de dicts `[{"opportunity_id": "uuid"}, …]`.
Si la liste est vide → pas de filtre d'exclusion au DELETE.

### Étape 2 — Supprimer les vieilles opportunités

Seuil ISO calculé côté Python :
```python
from datetime import datetime, timedelta, timezone
threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
```

Requête DELETE :
```
DELETE /rest/v1/opportunities
  ?created_at=lt.<threshold_iso>
  [&id=not.in.(<uuid1>,<uuid2>,…)]   ← présent uniquement si des favoris existent
```

Header `Prefer: count=exact` pour récupérer le nombre de lignes supprimées via
`Content-Range` (ex. `*/42` → 42 lignes).

Retourne le nombre entier de lignes supprimées.

## Configuration (`engine/config.py`)

Ajouter :
```python
purge_days: int = int(os.getenv("PURGE_DAYS", "30"))
```

`.env.example` :
```
PURGE_DAYS=30   # jours avant purge des opportunités (défaut : 30)
```

## Intégration `server.py`

Dans la fonction de démarrage du mode `--auto` (avant `asyncio.gather`) :

```python
from engine.maintenance import run_maintenance
…
await run_maintenance(supa, cfg)
```

## Tests (`tests/test_engine_maintenance.py`)

| Test | Scénario | Attendu |
|---|---|---|
| `test_purge_no_favorites` | 0 favori | DELETE sans `not.in.`, retourne N |
| `test_purge_with_favorites` | 2 favoris | DELETE avec `id=not.in.(id1,id2)` |
| `test_purge_nothing_to_delete` | 0 ligne à supprimer | Retourne 0, pas d'erreur |
| `test_run_maintenance_resilient` | purge lève une exception | `run_maintenance` ne lève pas, log erreur |

## Fichiers modifiés / créés

| Fichier | Action |
|---|---|
| `engine/maintenance.py` | Créer |
| `engine/config.py` | Modifier (+ `purge_days`) |
| `server.py` | Modifier (appel `run_maintenance` au boot `--auto`) |
| `.env.example` | Modifier (+ `PURGE_DAYS`) |
| `tests/test_engine_maintenance.py` | Créer |

## Hors scope

- Purge du Brain SQLite (`seen_ads`) : conservé intentionnellement
- Notification Telegram : feature suivante
- Recalcul `market_stats` : backlog, s'ajoutera dans `run_maintenance` plus tard
- Purge des tables legacy (`searches`, `listings`, etc.) : nettoyage SQL séparé
