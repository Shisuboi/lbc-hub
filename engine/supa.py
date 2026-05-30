"""Pont vers Supabase via REST PostgREST (clé service_role).

Phase A : on écrit des opportunités BRUTES (champs IA = null). La Phase B enrichira.
"""
import aiohttp


def build_opportunity_payload(
    ad: dict,
    search: dict,
    event: str,
    scraped_at_iso: str,
    previous_price: float | None = None,
) -> dict:
    """Construit la ligne `opportunities` à upserter. Champs IA laissés à null (Phase B)."""
    return {
        "ad_id": ad["ad_id"],
        "source_search_id": search.get("id"),
        "platform": search.get("platform", "leboncoin"),
        "title": ad.get("title"),
        "price": ad.get("price"),
        "url": ad.get("url"),
        "image_url": ad.get("image_url"),
        "location_city": ad.get("city"),
        "location_postal": ad.get("postal"),
        "category": None,
        "resale_score": None,
        "est_market_price": None,
        "est_margin_eur": None,
        "est_margin_pct": None,
        "max_buy_price": None,
        "is_lot": None,
        "signals": None,
        "explanation": None,
        "photo_verdict": None,
        "price_dropped": event == "price_drop",
        "previous_price": previous_price if event == "price_drop" else None,
        "model_used": None,
        "status": "active",
        "scraped_at": scraped_at_iso,
    }
