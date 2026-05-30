"""Boucle autonome : ordonnancement round-robin, dédup des recherches, traitement."""
from urllib.parse import urlparse, parse_qsl, urlencode

# Paramètres d'URL volatils à ignorer pour la déduplication des recherches.
_VOLATILE_PARAMS = {"sort", "page", "order"}


def normalize_search_url(url: str) -> str:
    """Forme canonique d'une URL de recherche : host minuscule, params triés, volatils retirés."""
    p = urlparse(url.strip())
    host = p.netloc.lower()
    params = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _VOLATILE_PARAMS]
    params.sort()
    query = urlencode(params)
    path = p.path.rstrip("/")
    return f"{p.scheme.lower()}://{host}{path}?{query}"


def dedup_searches(searches: list[dict]) -> list[dict]:
    """Garde une seule recherche par URL normalisée (deux membres, même recherche = 1 scrape)."""
    seen: set[str] = set()
    out: list[dict] = []
    for s in searches:
        key = normalize_search_url(s.get("source_url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out
