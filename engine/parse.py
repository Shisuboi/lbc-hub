"""Helpers de parsing purs (sans I/O) — faciles à tester."""
import re
import unicodedata

_AD_ID_RE = re.compile(r"/(\d{6,})(?:\.htm)?/?(?:\?|$)")


def extract_ad_id(url: str) -> str | None:
    """Extrait l'ID numérique stable d'une URL d'annonce Leboncoin."""
    if not url:
        return None
    m = _AD_ID_RE.search(url)
    return m.group(1) if m else None


def clean_price(price_text: str) -> float:
    """Parse un prix au format français (espaces fines, € , virgule décimale)."""
    cleaned = unicodedata.normalize("NFKD", price_text or "")
    cleaned = re.sub(r"[^\d.,]", "", cleaned)
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


_CATEGORY_AD_RE = re.compile(r"/ad/([a-z0-9_]+)/\d", re.IGNORECASE)
_CATEGORY_LEGACY_RE = re.compile(r"leboncoin\.fr/([a-z0-9_]+)/\d+\.htm", re.IGNORECASE)


def extract_category(url: str) -> str | None:
    """Extrait le slug de catégorie d'une URL d'annonce LBC ('/ad/<cat>/<id>')."""
    if not url:
        return None
    m = _CATEGORY_AD_RE.search(url)
    if m:
        return m.group(1).lower()
    m = _CATEGORY_LEGACY_RE.search(url)
    return m.group(1).lower() if m else None
