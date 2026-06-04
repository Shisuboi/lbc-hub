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


# Colonnes IA de `opportunities` qu'on autorise à écrire depuis la cascade.
_AI_COLUMNS = (
    "category", "resale_score", "est_market_price", "est_margin_eur", "est_margin_pct",
    "max_buy_price", "is_lot", "lot_unit_price", "lot_notes", "signals", "explanation",
    "photo_verdict", "model_used",
)


def merge_enrichment(payload: dict, ia: dict) -> dict:
    """Fusionne les résultats de la cascade dans le payload d'opportunité (colonnes connues only)."""
    out = dict(payload)
    for col in _AI_COLUMNS:
        if col in ia:
            out[col] = ia[col]
    return out


class Supa:
    """Client REST minimal vers PostgREST (Supabase) avec la clé service_role."""

    def __init__(self, base_url: str, service_key: str, session: aiohttp.ClientSession):
        self.base = base_url.rstrip("/")
        self.key = service_key
        self.session = session

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    async def fetch_active_searches(self) -> list[dict]:
        url = f"{self.base}/rest/v1/watchlist_searches"
        params = {"active": "eq.true", "select": "*"}
        async with self.session.get(url, params=params, headers=self._headers()) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def insert_opportunity(self, payload: dict) -> None:
        """Upsert sur ad_id (idempotent même si le cerveau SQLite est perdu)."""
        url = f"{self.base}/rest/v1/opportunities"
        params = {"on_conflict": "ad_id"}
        headers = self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
        async with self.session.post(url, params=params, json=payload, headers=headers) as resp:
            resp.raise_for_status()

    async def upsert_heartbeat(self, payload: dict) -> None:
        """Upsert de la télémétrie de scrape (clé search_id). Appelée en best-effort."""
        url = f"{self.base}/rest/v1/scrape_heartbeats"
        params = {"on_conflict": "search_id"}
        headers = self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
        async with self.session.post(url, params=params, json=payload, headers=headers) as resp:
            resp.raise_for_status()

    async def create_contact_from_telegram(self, opportunity_id: str, first_name: str) -> bool:
        """Insère un signal de contact via Telegram (service_role, bypass RLS).

        Retourne True si créé, False si déjà actif (conflit 409 sur l'index unique).
        Lève une exception pour toute autre erreur HTTP.
        """
        url = f"{self.base}/rest/v1/item_comments"
        payload = {
            "opportunity_id": opportunity_id,
            "user_id": None,
            "body": f"🤝 {first_name} s'en occupe (via Telegram)",
            "type": "contact",
        }
        headers = self._headers({"Prefer": "return=minimal"})
        async with self.session.post(url, json=payload, headers=headers) as resp:
            if resp.status == 409:
                return False
            resp.raise_for_status()
            return True
