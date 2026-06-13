"""Grounding prix marché : nourrit l'IA de vrais comparables locaux (pas de prix 'de tête').

Source = table market_observations du cerveau. Stratégie :
  1. Cherche par modèle exact (ex: "ASUS ZenBook UX433F") → haute précision
  2. Fallback catégorie large (ex: "informatique") → approximation
Démarrage à froid = échantillon vide → médiane None (l'IA estime avec prudence).
"""
from statistics import median, quantiles

# Dispersion max (IQR/médiane) d'un grounding 'model' pour être jugé FIABLE (ancrage prix d'un 🔴).
# Au-delà, la distribution est trop étalée : le libellé de modèle mélange des versions de prix très
# différents (ex. "MacBook Air 13" = Intel 2015 ~100€ ET M3 2024 ~1200€) → médiane non fiable.
MAX_DISPERSION_FOR_CONFIDENCE = 0.6


def _price_dispersion(prices: list, med: float) -> float | None:
    """IQR/médiane : resserrement de la distribution (0 = prix identiques, >1 = très étalé)."""
    if med <= 0 or len(prices) < 4:
        return None
    q = quantiles(prices, n=4)  # [Q1, Q2(médiane), Q3]
    return (q[2] - q[0]) / med


def _price_floor(prices: list) -> float | None:
    """Plancher du marché = 1ᵉʳ décile (P10) des prix réels du modèle.

    Représente le prix de la génération/version la moins chère. Un prix sous ce plancher est une
    affaire quelle que soit la génération (utilisé pour autoriser un 🔴 même si la distribution
    globale est trop large pour ancrer une médiane fiable)."""
    if len(prices) < 5:
        return None
    return float(quantiles(prices, n=10)[0])


def market_grounding(brain, categorie: str | None, model_name: str | None = None) -> dict:
    """Retourne {median_price, sample_size, min_price, max_price[, grounding_level, price_dispersion]}.

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
            med = float(median(prices))
            return {
                "median_price": med,
                "sample_size": len(prices),
                "min_price": min(prices),
                "max_price": max(prices),
                "grounding_level": "model",
                "price_dispersion": _price_dispersion(prices, med),
                "price_floor": _price_floor(prices),
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


def is_grounding_confident(grounding: dict, max_dispersion: float = MAX_DISPERSION_FOR_CONFIDENCE) -> bool:
    """True si le grounding ancre un prix FIABLE pour un 🔴 : niveau 'model' ET distribution resserrée.

    Une dispersion élevée (IQR/médiane) trahit un libellé de modèle trop large qui mélange des
    générations/versions de prix très différents → la médiane n'est plus un ancrage valable → pas de 🔴.
    Le grounding 'category' (toutes annonces d'une catégorie) n'est jamais assez précis pour un 🔴.
    """
    if grounding.get("grounding_level") != "model":
        return False
    disp = grounding.get("price_dispersion")
    return disp is not None and disp <= max_dispersion
