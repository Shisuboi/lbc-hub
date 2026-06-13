"""Worker d'enrichissement : draine pending_enrichment, exécute la cascade, écrit dans Supabase.

Découplé du scrape (2e coroutine sous --auto). Écrit l'opportunité dès le triage (jamais brute),
met à jour après vérif puis photo. Résilient :
- QuotaExhausted → on s'arrête, les items restent en file (dégradation gracieuse, §6 de la spec) ;
- réponse LLM malformée → on ne boucle pas à l'infini (bump retry / skip) ;
- garde anti-poison → un item échouant trop de fois est abandonné pour ne pas bloquer la file ;
- scam_risk "high" → rétrograde un 🔴 en 🟡 (spec §4 : un signal d'arnaque fort peut rétrograder).
"""
import asyncio
from datetime import date
from engine.parse import extract_category, extract_model_name
from engine.comparator import lbc_category_from_url
from engine.cascade import triage_batch, verify_one, photo_one
from engine.supa import merge_enrichment
from engine.geo import fill_latlon
from engine.router import QuotaExhausted
from engine.telegram import send_opportunity

_MAX_PENDING_RETRIES = 5

# ── Quota state (module-level, reset automatiquement le lendemain) ────────────
_quota_exhausted_day: str = ""


def quota_paused() -> bool:
    """True si les quotas IA ont été épuisés aujourd'hui."""
    return _quota_exhausted_day == date.today().isoformat()


def _mark_quota_exhausted() -> None:
    global _quota_exhausted_day
    _quota_exhausted_day = date.today().isoformat()
    print("🔴 [quota] Quotas IA épuisés pour aujourd'hui — enrichissement en pause jusqu'à minuit.")


# ── Plafond journalier de recherches comparatives LBC (module-level, reset le lendemain) ──
# {jour-iso: nombre de recherches faites}. Borne le risque Datadome même en cas de pic de
# nouveaux modèles. Défaut configurable via settings["comparator_daily_cap"].
_comparator_count: dict = {}


def _comparator_quota_left(cap: int) -> bool:
    """True s'il reste du quota de recherches comparatives aujourd'hui."""
    if cap <= 0:
        return False
    return _comparator_count.get(date.today().isoformat(), 0) < cap


def _bump_comparator_count() -> None:
    day = date.today().isoformat()
    _comparator_count[day] = _comparator_count.get(day, 0) + 1


def _ad_from_payload(payload: dict) -> dict:
    return {
        "ad_id": payload.get("ad_id"),
        "title": payload.get("title"),
        "price": payload.get("price"),
        "url": payload.get("url"),
        "image_url": payload.get("image_url"),
        "city": payload.get("location_city"),
        "description": payload.get("description"),
        "category": extract_category(payload.get("url") or ""),
    }


async def enrich_once(brain, supa, router, settings, searches_by_id, image_fetch, batch_size=15, telegram=None, desc_fetch=None, comparator_fetch=None) -> int:
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
        _mark_quota_exhausted()
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
            "explanation": t.get("reason", ""),  # raison du triage, même pour passable
        })
        print(f"  ✓ Triage {ad_id}: {t['category']} (score={t['score']}) — {t.get('reason', '')[:40]}…")
        # Géocodage best-effort : remplit lat/lon depuis la ville (cache → BAN). Pour la proximité.
        await fill_latlon(brain, supa.session, payload)
        try:
            await supa.insert_opportunity(payload)  # écriture post-triage (jamais brute)
        except Exception:
            brain.queue_outbox(payload)  # Supabase down → outbox (résilience Phase A)

        # vérif des candidates
        if t["dig_deeper"] or t["score"] >= threshold:
            # Description page annonce (best-effort, avant vérif pour enrichir le prompt).
            if desc_fetch and not ad.get("description"):
                try:
                    desc = await desc_fetch(ad.get("url", ""))
                    if desc:
                        ad["description"] = desc
                        item["payload"]["description"] = desc
                except Exception as exc:
                    print(f"[desc] fetch échoué pour {ad_id} ({type(exc).__name__}) — on continue sans")

            # Recherche inconnue/supprimée → on retombe sur les seuils par défaut de la
            # config (PAS sur 0 : sinon toute marge positive promeut en 🔴 une fois Pro activé).
            search = searches_by_id.get(item["search_id"]) or {
                "min_margin_eur": settings.get("default_min_margin_eur", 30.0),
                "min_margin_pct": settings.get("default_min_margin_pct", 30.0),
            }

            # Comparateur LBC ciblé : si l'annonce a un modèle identifiable, qu'il n'a pas été
            # cherché récemment et qu'on est sous le plafond/jour, on relance une recherche LBC du
            # MODÈLE, et on verse les prix trouvés dans market_observations (le grounding existant
            # s'en sert ensuite). Best-effort : un échec (captcha, timeout) ne casse pas la vérif.
            model_name = extract_model_name(ad.get("title", ""))
            cap = int(settings.get("comparator_daily_cap", 100))
            if (comparator_fetch and model_name and brain.model_lookup_due(model_name)
                    and _comparator_quota_left(cap)):
                category = lbc_category_from_url(search.get("source_url"))
                print(f"🔍 [comparateur] Recherche LBC du modèle « {model_name} » "
                      f"(catégorie {category or 'toutes'})…")
                try:
                    comparables = await comparator_fetch(model_name, category)
                except Exception as exc:
                    # vrai échec (captcha/timeout) → on traite comme « tenté, 0 résultat » : on
                    # posera le cooldown pour ne pas marteler LBC avec un modèle qui plante.
                    print(f"[comparateur] échec recherche « {model_name} » "
                          f"({type(exc).__name__}: {exc}) — vérif sur les données existantes")
                    comparables = []
                if comparables is None:
                    # None = le scrape principal tenait le verrou, la recherche n'a PAS eu lieu.
                    # On NE pose PAS le cooldown 3 j (sinon le modèle serait gelé sans données) et
                    # on ne consomme pas de quota → réessai au prochain cycle.
                    print(f"  ⏳ [comparateur] « {model_name} » reporté (scrape en cours) — "
                          f"réessai au prochain cycle.")
                else:
                    _bump_comparator_count()
                    for c in comparables:
                        if c.get("price"):
                            brain.record_market_obs(
                                extract_category(c.get("url") or "") or ad.get("category"),
                                float(c["price"]), c.get("city"), model_name=model_name)
                    print(f"  ✓ [comparateur] {len(comparables)} comparable(s) enregistré(s) "
                          f"pour « {model_name} ».")
                    brain.mark_model_lookup(model_name)  # cooldown (succès OU échec réel)

            try:
                ia = await verify_one(ad, search, router, brain, urgent_score_threshold=threshold)
            except QuotaExhausted:
                _mark_quota_exhausted()
                brain.delete_pending(item["id"])  # déjà écrit au triage ; on n'insiste pas
                written += 1
                break  # quota fini : on arrête le lot, le reste attend
            except Exception as exc:  # vérif malformée : l'annonce reste 🟡, on continue
                print(f"[enrich] verify échoué pour {ad_id} ({type(exc).__name__}) — reste au triage")
                brain.delete_pending(item["id"])
                written += 1
                continue

            payload = merge_enrichment(payload, ia)
            cat = payload.get("category", "?")
            score = payload.get("resale_score", "?")
            margin = payload.get("est_margin_eur")
            print(f"  ✓ Vérif {ad_id}: {cat} (score={score}, marge={margin}€)")

            # photo sur les 🔴 uniquement
            if payload.get("category") == "urgent" and ad.get("image_url") and image_fetch:
                try:
                    img = await image_fetch(ad["image_url"])
                    photo = await photo_one(ad, img, router)
                    payload = merge_enrichment(payload, photo)
                    print(f"  📸 Photo {ad_id}: {photo.get('verdict', '?')} (scam_risk={photo.get('scam_risk', '?')})")
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

            # Notification Telegram 🔴 (best-effort, après vérif/photo finale)
            if telegram and payload.get("category") == "urgent":
                ad_id_str = payload.get("ad_id", "")
                if ad_id_str and not brain.is_telegram_sent(ad_id_str):
                    # On ne marque « notifiée » QUE si l'envoi a réussi : sinon un échec
                    # transitoire (400 parse / réseau) bloquerait à jamais la notification.
                    if await send_opportunity(telegram, payload):
                        brain.mark_telegram_sent(ad_id_str)

        brain.delete_pending(item["id"])
        written += 1
    return written


async def enrichment_worker(brain, supa, router, settings, fetch_searches, image_fetch,
                            stop_event, pause: float = 5.0, max_loops=None, telegram=None,
                            desc_fetch=None, comparator_fetch=None) -> None:
    """Boucle du worker. `fetch_searches` → {search_id: {min_margin_eur, min_margin_pct}}."""
    loops = 0
    while not stop_event.is_set():
        try:
            searches_by_id = await fetch_searches()
            await enrich_once(brain, supa, router, settings, searches_by_id, image_fetch,
                              telegram=telegram, desc_fetch=desc_fetch,
                              comparator_fetch=comparator_fetch)
        except Exception as exc:
            print(f"[enrich] erreur cycle: {exc}")
        loops += 1
        if max_loops is not None and loops >= max_loops:
            return
        if pause:
            await asyncio.sleep(pause)
