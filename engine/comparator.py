"""Helpers d'URL pour la recherche comparative Leboncoin (prix d'un modèle exact).

Pur (zéro réseau) → testable. La composition « URL + scrape » vit dans server.py (closure
`comparator_fetch`, même patron que `description_fetch`), qui réutilise le Chromium partagé.
"""
from urllib.parse import urlencode, urlparse, parse_qs

_BASE = "https://www.leboncoin.fr/recherche"


def lbc_category_from_url(source_url: str | None) -> str | None:
    """Extrait le paramètre `category` (numérique LBC) d'une URL de recherche, ou None."""
    if not source_url:
        return None
    qs = parse_qs(urlparse(source_url).query)
    vals = qs.get("category")
    return vals[0] if vals else None


def build_comparator_url(model_name: str, category: str | None = None) -> str:
    """URL de recherche LBC pour un modèle donné, scopée à la catégorie si fournie."""
    params = {"text": model_name}
    if category:
        params["category"] = category
    return f"{_BASE}?{urlencode(params)}"
