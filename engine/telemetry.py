"""Télémétrie du moteur : publie un heartbeat de la recherche active dans Supabase.

Best-effort : ne doit JAMAIS faire planter le scraping. Lit les stats du Brain local
et les pousse dans `scrape_heartbeats` (lue en temps réel par la page /watchlist).
"""
import asyncio
import time
from datetime import datetime, timezone


def _iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def build_heartbeat_payload(brain, search_id: str, now: int | None = None) -> dict:
    """Construit la ligne `scrape_heartbeats` pour une recherche, à partir du Brain local."""
    now = int(now if now is not None else time.time())
    return {
        "search_id": search_id,
        "heartbeat_at": _iso(now),
        "last_pass_at": _iso(brain.last_pass_at(search_id)),
        "new_ads_per_min": round(brain.new_ads_rate(search_id, now=now), 2),
        "ads_seen_total": brain.ads_seen_total(search_id),
        "blocked_recent": brain.blocked_recent(search_id, now=now),
    }


async def heartbeat_worker(brain, supa, stop_event, interval: float = 15.0, max_loops=None) -> None:
    """Tick périodique : pour chaque recherche active, upsert sa télémétrie. Best-effort.

    `supa` doit exposer `fetch_active_searches()` et `upsert_heartbeat(payload)`.
    `max_loops` (tests) limite le nombre de tours ; None = infini.
    """
    loops = 0
    while not stop_event.is_set():
        try:
            searches = await supa.fetch_active_searches()
            now = int(time.time())
            for s in searches:
                sid = s.get("id")
                if not sid:
                    continue
                payload = build_heartbeat_payload(brain, sid, now)
                try:
                    await supa.upsert_heartbeat(payload)
                except Exception as exc:
                    print(f"[heartbeat] upsert échoué ({type(exc).__name__}) — best-effort, on continue")
        except Exception as exc:
            print(f"[heartbeat] erreur cycle: {type(exc).__name__}: {exc}")
        loops += 1
        if max_loops is not None and loops >= max_loops:
            return
        if interval:
            await asyncio.sleep(interval)
