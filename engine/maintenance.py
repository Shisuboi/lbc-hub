"""Tâches de maintenance du moteur autonome (exécutées au démarrage --auto).

Actuellement : purge des opportunités > PURGE_DAYS jours, sauf celles en favori.
Extensible pour de futures tâches (recalcul stats, flush outbox…).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


async def purge_old_opportunities(supa, days: int) -> int:
    """Supprime de Supabase les opportunités de plus de `days` jours (hors favoris).

    Retourne le nombre de lignes supprimées.
    Lève une exception en cas d'erreur réseau (l'appelant décide de la gestion).
    """
    threshold = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Étape 1 : IDs protégés (en favori)
    url_fav = f"{supa.base}/rest/v1/item_favorites"
    async with supa.session.get(
        url_fav, params={"select": "opportunity_id"}, headers=supa._headers()
    ) as resp:
        resp.raise_for_status()
        favs = await resp.json()

    protected_ids = [f["opportunity_id"] for f in favs]

    # Étape 2 : DELETE opportunités trop vieilles
    url_del = f"{supa.base}/rest/v1/opportunities"
    params: dict = {"created_at": f"lt.{threshold}"}
    if protected_ids:
        params["id"] = f"not.in.({','.join(protected_ids)})"

    headers = supa._headers({"Prefer": "count=exact"})
    async with supa.session.delete(url_del, params=params, headers=headers) as resp:
        resp.raise_for_status()
        cr = resp.headers.get("Content-Range", "*/0")  # ex. "*/42"
        try:
            n = int(cr.split("/")[-1])
        except (ValueError, IndexError):
            n = 0

    return n


async def run_maintenance(supa, cfg: dict) -> None:
    """Point d'entrée maintenance au démarrage du moteur --auto.

    Best-effort : une erreur est loguée mais ne bloque pas le démarrage.
    """
    days = int(str(cfg.get("PURGE_DAYS", "30")))
    try:
        n = await purge_old_opportunities(supa, days)
        print(f"[maintenance] purge : {n} opportunité(s) supprimée(s) (>{days}j, hors favoris)")
    except Exception as exc:
        print(f"[maintenance] purge échouée (non bloquant) : {exc}")
