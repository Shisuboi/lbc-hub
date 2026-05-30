"""Worker d'enrichissement : draine pending_enrichment, exécute la cascade, écrit dans Supabase.

Découplé du scrape (2e coroutine sous --auto). Écrit l'opportunité dès le triage (jamais brute),
met à jour après vérif puis photo. Résilient :
- QuotaExhausted → on s'arrête, les items restent en file (dégradation gracieuse, §6 de la spec) ;
- réponse LLM malformée → on ne boucle pas à l'infini (bump retry / skip) ;
- garde anti-poison → un item échouant trop de fois est abandonné pour ne pas bloquer la file ;
- scam_risk "high" → rétrograde un 🔴 en 🟡 (spec §4 : un signal d'arnaque fort peut rétrograder).
"""
import asyncio
from engine.parse import extract_category
from engine.cascade import triage_batch, verify_one, photo_one
from engine.supa import merge_enrichment
from engine.router import QuotaExhausted

_MAX_PENDING_RETRIES = 5


def _ad_from_payload(payload: dict) -> dict:
    return {
        "ad_id": payload.get("ad_id"),
        "title": payload.get("title"),
        "price": payload.get("price"),
        "url": payload.get("url"),
        "image_url": payload.get("image_url"),
        "city": payload.get("location_city"),
        "category": extract_category(payload.get("url") or ""),
    }


async def enrich_once(brain, supa, router, settings, searches_by_id, image_fetch, batch_size=15) -> int:
    """Traite un lot. Retourne le nombre d'opportunités écrites (post-triage). 0 si rien/quota."""
    raw = brain.peek_pending(limit=batch_size)
    # Garde anti-poison : un item ayant échoué trop de fois est abandonné (file jamais bloquée).
    items = []
    for it in raw:
        if it["retries"] >= _MAX_PENDING_RETRIES:
            brain.delete_pending(it["id"])
        else:
            items.append(it)
    if not items:
        return 0

    ads = [_ad_from_payload(it["payload"]) for it in items]
    by_id = {it["payload"]["ad_id"]: it for it in items}
    threshold = settings.get("urgent_score_threshold", 75.0)

    try:
        triaged = await triage_batch(ads, router, brain)
    except QuotaExhausted:
        return 0  # rien consommé, tout reste en file
    except Exception as exc:  # réponse LLM malformée / inattendue : on reporte sans boucler
        print(f"[enrich] triage échoué ({type(exc).__name__}: {exc}) — lot reporté")
        for it in items:
            brain.bump_pending_retry(it["id"])
        return 0

    written = 0
    for ad in ads:
        ad_id = ad["ad_id"]
        item = by_id[ad_id]
        t = triaged.get(ad_id)
        if t is None:
            brain.delete_pending(item["id"])  # pas de verdict du triage → on abandonne l'item
            continue

        payload = merge_enrichment(item["payload"], {
            "category": t["category"], "resale_score": t["score"],
        })
        try:
            await supa.insert_opportunity(payload)  # écriture post-triage (jamais brute)
        except Exception:
            brain.queue_outbox(payload)  # Supabase down → outbox (résilience Phase A)

        # vérif des candidates
        if t["dig_deeper"] or t["score"] >= threshold:
            # Recherche inconnue/supprimée → on retombe sur les seuils par défaut de la
            # config (PAS sur 0 : sinon toute marge positive promeut en 🔴 une fois Pro activé).
            search = searches_by_id.get(item["search_id"]) or {
                "min_margin_eur": settings.get("default_min_margin_eur", 30.0),
                "min_margin_pct": settings.get("default_min_margin_pct", 30.0),
            }
            try:
                ia = await verify_one(ad, search, router, brain, urgent_score_threshold=threshold)
            except QuotaExhausted:
                brain.delete_pending(item["id"])  # déjà écrit au triage ; on n'insiste pas
                written += 1
                break  # quota fini : on arrête le lot, le reste attend
            except Exception as exc:  # vérif malformée : l'annonce reste 🟡, on continue
                print(f"[enrich] verify échoué pour {ad_id} ({type(exc).__name__}) — reste au triage")
                brain.delete_pending(item["id"])
                written += 1
                continue

            payload = merge_enrichment(payload, ia)

            # photo sur les 🔴 uniquement
            if payload.get("category") == "urgent" and ad.get("image_url") and image_fetch:
                try:
                    img = await image_fetch(ad["image_url"])
                    photo = await photo_one(ad, img, router)
                    payload = merge_enrichment(payload, photo)
                    # Règle de rétrogradation : un signal d'arnaque fort retire le 🔴 (spec §4).
                    if photo.get("scam_risk") == "high":
                        payload["category"] = "interesting"
                except QuotaExhausted:
                    pass  # déjà 🔴 sans photo, acceptable
                except Exception as exc:
                    print(f"[enrich] photo échouée pour {ad_id} ({type(exc).__name__})")

            try:
                await supa.insert_opportunity(payload)  # mise à jour post-vérif/photo
            except Exception:
                brain.queue_outbox(payload)

        brain.delete_pending(item["id"])
        written += 1
    return written


async def enrichment_worker(brain, supa, router, settings, fetch_searches, image_fetch,
                            stop_event, pause: float = 5.0, max_loops=None) -> None:
    """Boucle du worker. `fetch_searches` → {search_id: {min_margin_eur, min_margin_pct}}."""
    loops = 0
    while not stop_event.is_set():
        try:
            searches_by_id = await fetch_searches()
            await enrich_once(brain, supa, router, settings, searches_by_id, image_fetch)
        except Exception as exc:
            print(f"[enrich] erreur cycle: {exc}")
        loops += 1
        if max_loops is not None and loops >= max_loops:
            return
        if pause:
            await asyncio.sleep(pause)
