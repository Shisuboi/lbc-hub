"""Boucle autonome : ordonnancement round-robin, dédup des recherches, traitement."""
import asyncio
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qsl, urlencode
from engine.prefilter import passes_prefilter
from engine.supa import build_opportunity_payload

# Paramètres d'URL volatils à ignorer pour la déduplication des recherches.
_VOLATILE_PARAMS = {"sort", "page", "order"}


def normalize_search_url(url: str) -> str:
    """Forme canonique d'une URL de recherche : host minuscule, params triés, volatils retirés.

    Retourne "" pour une URL absente/vide (recherche non scrapable)."""
    if not url:
        return ""
    p = urlparse(url.strip())
    host = p.netloc.lower()
    params = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _VOLATILE_PARAMS]
    params.sort()
    query = urlencode(params)
    path = p.path.rstrip("/")
    return f"{p.scheme.lower()}://{host}{path}" + (f"?{query}" if query else "")


def dedup_searches(searches: list[dict]) -> list[dict]:
    """Garde une seule recherche par URL normalisée (deux membres, même recherche = 1 scrape).

    Les recherches sans source_url exploitable sont ignorées."""
    seen: set[str] = set()
    out: list[dict] = []
    for s in searches:
        key = normalize_search_url(s.get("source_url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


async def process_search(scrape_fn, brain, sink, search: dict) -> dict:
    """Scrape une recherche, déduplique, écrit les opportunités neuves/baissées dans `sink`.

    scrape_fn: coroutine(url) -> list[ad]   (injectée → testable sans navigateur)
    sink: destination d'écriture (Phase A = client Supa direct ; Phase B = LocalSink).
          Doit exposer `insert_opportunity(payload)`.
    """
    counts = {"new": 0, "price_drop": 0, "seen": 0, "filtered": 0}
    ads = await scrape_fn(search.get("source_url", ""))
    scraped_at_iso = datetime.now(timezone.utc).isoformat()

    for ad in ads:
        if not ad.get("ad_id"):
            continue
        if not passes_prefilter(ad, search):
            counts["filtered"] += 1
            continue
        event = brain.upsert_ad(ad["ad_id"], float(ad.get("price") or 0.0))
        if event == "seen":
            counts["seen"] += 1
            continue
        prev = brain.previous_price(ad["ad_id"]) if event == "price_drop" else None
        payload = build_opportunity_payload(ad, search, event, scraped_at_iso, previous_price=prev)
        await safe_insert(brain, sink, payload)
        counts[event] += 1

    brain.log_scrape(search.get("id", "?"), "ok", new_ads=counts["new"])
    # Log détaillé
    print(f"  📊 Scrape {search.get('title', '?')}: trouvé={len(ads)} | "
          f"nouveau={counts['new']} | baisse_prix={counts['price_drop']} | "
          f"vu={counts['seen']} | filtré={counts['filtered']}")
    return counts


async def run_engine(brain, supa, sink, scrape_fn, stop_event, cycle_pause: float = 60.0, max_cycles=None) -> None:
    """Boucle round-robin.

    `supa` : source des recherches actives + flush de l'outbox (vrai client Supabase).
    `sink` : destination d'écriture du scrape (Phase A = `supa` lui-même ; Phase B = LocalSink).
    `max_cycles` (tests) limite le nombre de tours ; None = infini.
    """
    cycle = 0
    while not stop_event.is_set():
        try:
            searches = dedup_searches(await supa.fetch_active_searches())
            await flush_outbox(brain, supa)
            for s in searches:
                if stop_event.is_set():
                    break
                try:
                    await process_search(scrape_fn, brain, sink, s)
                except Exception as exc:  # un échec sur une recherche n'arrête pas le moteur
                    brain.log_scrape(s.get("id", "?"), f"error: {exc}")
        except Exception as exc:
            print(f"[engine] cycle error: {exc}")

        cycle += 1
        if max_cycles is not None and cycle >= max_cycles:
            return
        if cycle_pause:
            await asyncio.sleep(cycle_pause)


async def safe_insert(brain, supa, payload: dict) -> bool:
    """Tente l'upsert ; en cas d'échec réseau, met en file d'attente (outbox). Retourne True si envoyé."""
    try:
        await supa.insert_opportunity(payload)
        return True
    except Exception:
        brain.queue_outbox(payload)
        return False


async def flush_outbox(brain, supa) -> int:
    """Rejoue les opportunités en attente. Retourne le nombre rejoué avec succès."""
    sent = 0
    for item in brain.peek_outbox(limit=200):
        try:
            await supa.insert_opportunity(item["payload"])
            brain.delete_outbox(item["id"])
            sent += 1
        except Exception:
            break  # toujours hors ligne : on réessaiera au prochain cycle
    return sent
