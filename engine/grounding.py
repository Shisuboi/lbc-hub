"""Grounding prix marché : nourrit l'IA de vrais comparables locaux (pas de prix 'de tête').

Source = table market_observations du cerveau. Stratégie :
  1. Cherche par modèle exact (ex: "ASUS ZenBook UX433F") → haute précision
  2. Fallback catégorie large (ex: "informatique") → approximation
Démarrage à froid = échantillon vide → médiane None (l'IA estime avec prudence).
"""
from statistics import median


def market_grounding(brain, categorie: str | None, model_name: str | None = None) -> dict:
    """Retourne {median_price, sample_size, min_price, max_price} pour un modèle ou catégorie.

    Priorité : modèle exact (si >= 5 observations) → catégorie large (fallback).
    """
    if not categorie:
        return {"median_price": None, "sample_size": 0, "min_price": None, "max_price": None}

    # Cherche par modèle exact d'abord
    if model_name:
        rows = brain.conn.execute(
            "SELECT prix FROM market_observations WHERE model_name = ? AND prix > 0",
            (model_name,),
        ).fetchall()
        prices = [r["prix"] for r in rows]
        if len(prices) >= 5:  # Seuil de confiance : au moins 5 observations
            return {
                "median_price": float(median(prices)),
                "sample_size": len(prices),
                "min_price": min(prices),
                "max_price": max(prices),
                "grounding_level": "model",
            }

    # Fallback catégorie large
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
        "grounding_level": "category",
    }
