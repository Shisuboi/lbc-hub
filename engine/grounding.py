"""Grounding prix marché : nourrit l'IA de vrais comparables locaux (pas de prix 'de tête').

Source = table market_observations du cerveau (alimentée à chaque scrape). Démarrage à froid
= échantillon vide → médiane None (l'IA estime alors avec prudence, marges approximatives).
"""
from statistics import median


def market_grounding(brain, categorie: str | None) -> dict:
    """Retourne {median_price, sample_size, min_price, max_price} pour une catégorie."""
    if not categorie:
        return {"median_price": None, "sample_size": 0, "min_price": None, "max_price": None}
    rows = brain.conn.execute(
        "SELECT prix FROM market_observations WHERE categorie = ? AND prix > 0",
        (categorie,),
    ).fetchall()
    prices = [r["prix"] for r in rows]
    if not prices:
        return {"median_price": None, "sample_size": 0, "min_price": None, "max_price": None}
    return {
        "median_price": float(median(prices)),
        "sample_size": len(prices),
        "min_price": min(prices),
        "max_price": max(prices),
    }
