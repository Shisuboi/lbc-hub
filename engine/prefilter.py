"""Pré-filtre par règles, sans IA. Évite d'écrire du bruit dans Supabase."""


def passes_prefilter(ad: dict, search: dict) -> bool:
    price = ad.get("price") or 0.0
    if price <= 0:
        return False

    price_max = search.get("price_max")
    if price_max is not None and price > float(price_max):
        return False

    raw_excludes = search.get("exclude_keywords") or ""
    excludes = [w.strip().lower() for w in raw_excludes.split(",") if w.strip()]
    title = (ad.get("title") or "").lower()
    if any(word in title for word in excludes):
        return False

    return True
