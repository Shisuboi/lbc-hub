"""Pré-filtre par règles, sans IA. Évite d'écrire du bruit dans Supabase."""
import re

# Blacklist INTÉGRÉE "pour pièces / en panne / cassé" — écarte gratuitement (étage 0,
# avant l'IA) les annonces d'objets non fonctionnels, même si l'utilisateur n'a rien
# configuré dans exclude_keywords. Cohérent avec les mots-clés du prompt de triage.
# Bornes de mots (\b) sur les tokens risqués pour éviter les faux positifs
# ("cassette", "casserole" ne doivent PAS matcher "cassé").
_FOR_PARTS_RE = re.compile(
    r"pour\s+pi[eè]ces?"
    r"|pi[eè]ces?\s+d[eé]tach"
    r"|\bh\.?\s?s\.?\b"
    r"|en\s+panne"
    r"|\bpanne\b"
    r"|ne\s+fonctionne\s+pas"
    r"|ne\s+s'?\s?allume"
    r"|\bcass[ée]e?s?\b"
    r"|[ée]cran\s+(?:cass|fissur)"
    r"|\bfissur[ée]e?s?\b"
    r"|[àa]\s+r[eé]parer"
    r"|d[eé]fectueux|d[eé]fectueuse"
    r"|bloqu[ée]\s+icloud"
    r"|compte\s+google\s+(?:bloqu[ée]|verrouill[ée])"
    r"|\bfrp\b",
    re.IGNORECASE,
)


def passes_prefilter(ad: dict, search: dict) -> bool:
    price = ad.get("price") or 0.0
    if price <= 0:
        return False

    price_max = search.get("price_max")
    if price_max is not None and price > float(price_max):
        return False

    title_raw = ad.get("title") or ""

    # Blacklist intégrée (objets pour pièces / cassés / en panne).
    if _FOR_PARTS_RE.search(title_raw):
        return False

    # Mots exclus configurés par l'utilisateur sur la recherche (en plus de la blacklist).
    raw_excludes = search.get("exclude_keywords") or ""
    excludes = [w.strip().lower() for w in raw_excludes.split(",") if w.strip()]
    title = title_raw.lower()
    if any(word in title for word in excludes):
        return False

    return True
