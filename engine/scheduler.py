"""Boucle autonome : ordonnancement round-robin, dédup des recherches, traitement."""
from urllib.parse import urlparse, parse_qsl, urlencode

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
