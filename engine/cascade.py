"""Cascade IA : stages purs (triage groupé, vérif, photo) + calcul marge/gate 🔴.

Le batching (10-20 annonces → 1 appel triage) vit dans enrichment_worker ; ici on expose
des fonctions de stage qui prennent un 'router' injecté (LLMRouter ou fake) → testables.
"""
from engine.parse import extract_model_name
from engine.prompts import (
    TRIAGE_SCHEMA, VERIFY_SCHEMA, PHOTO_SCHEMA,
    build_triage_prompt, build_verify_prompt, build_photo_prompt,
)
from engine.grounding import market_grounding, is_grounding_confident

# En dessous de cette marge %, une annonce n'est pas une "affaire" de revente convaincante, même
# si le vendeur produit n'a pas fixé de seuil → on plafonne le score affiché (cf. _reconcile_score).
MIN_MARGIN_PCT_FOR_FULL_SCORE = 10.0


def _reconcile_score(refined_score: float, margin_eur: float, margin_pct: float,
                     min_margin_pct: float) -> float:
    """Aligne le score AFFICHÉ sur la marge RÉELLE calculée, pas seulement sur l'avis du LLM.

    Le LLM crache parfois un score élevé (95) en surestimant le marché alors que, prix marché
    effectif à l'appui, la marge est négative voire nulle. Un tel score trompeur remonterait en tête
    de feed une non-affaire. Règle :
    - marge négative (prix ≥ marché) → ce n'est PAS une affaire → score écrasé (→ passable) ;
    - marge positive mais sous le seuil crédible → plafond modéré (interesting bas) ;
    - marge confortable → on conserve le score du LLM.
    """
    if margin_eur < 0:
        return min(refined_score, 25.0)
    floor_pct = max(min_margin_pct, MIN_MARGIN_PCT_FOR_FULL_SCORE)
    if margin_pct < floor_pct:
        return min(refined_score, 55.0)
    return refined_score


def compute_margin_and_category(
    price: float, est_market_price: float, refined_score: float,
    min_margin_eur: float, min_margin_pct: float,
    tier_rank: int, min_urgent_rank: int, urgent_score_threshold: float,
    grounding_confident: bool = True, market_floor: float | None = None,
    market_median: float | None = None,
) -> dict:
    """Calcule marge €/%, prix max d'achat, score réconcilié, et la catégorie finale (gate 🔴).

    Prix marché EFFECTIF utilisé pour la marge et la gate :
    - `grounding_confident` (distribution resserrée) → on fait confiance à l'estimation (médiane) ;
    - sinon, si un `market_floor` (plancher = 1ᵉʳ décile des prix réels du modèle) est connu → on
      n'ancre QUE sur ce plancher (`min(estimation, plancher)`) : un 🔴 ne peut alors se déclencher
      que si le prix bat même la génération la moins chère → « affaire quelle que soit la version » ;
    - sans modèle (pas de plancher) → pas éligible au 🔴 (plafond 🟡). Dans ce cas non-ancré, si une
      `market_median` réelle est connue, elle BORNE le prix marché (`min(estimation, médiane)`) :
      garde-fou anti-hallucination contre les prix internes périmés (et trop hauts) du LLM.
    Un 🔴 notifie + dit « fonce » : il exige soit un ancrage fiable, soit un prix sous le plancher.

    Le `resale_score` retourné est RÉCONCILIÉ avec la marge (cf. _reconcile_score) : un score LLM
    élevé sur une marge négative/faible est plafonné. La gate 🔴 reste basée sur le score LLM brut
    (elle exige déjà une marge ≥ seuil, donc un score élevé n'y survit qu'avec une vraie marge).
    """
    price = float(price or 0.0)
    est = float(est_market_price or 0.0)

    if grounding_confident:
        eff = est                                   # ancrage médiane fiable
        eligible = True
    elif market_floor is not None:
        eff = min(est, float(market_floor))         # large : on ne value jamais au-dessus du plancher
        eligible = True
    else:
        eff = est                                   # pas de modèle → pas d'ancrage → pas de 🔴
        eligible = False
        if market_median is not None:               # anti-hallucination : jamais au-dessus du marché réel
            eff = min(eff, float(market_median))

    margin_eur = round(eff - price, 2)
    margin_pct = round((margin_eur / price * 100.0), 2) if price > 0 else 0.0
    required = max(min_margin_eur, price * min_margin_pct / 100.0)
    max_buy = round(eff - required, 2)

    final_score = _reconcile_score(refined_score, margin_eur, margin_pct, min_margin_pct)

    margin_ok = margin_eur >= min_margin_eur and margin_pct >= min_margin_pct
    score_ok = refined_score >= urgent_score_threshold
    tier_ok = tier_rank >= min_urgent_rank
    if score_ok and margin_ok and tier_ok and eligible:
        category = "urgent"
    elif final_score >= 50:
        category = "interesting"
    else:
        category = "passable"

    return {
        "est_market_price": round(eff, 2),
        "est_margin_eur": margin_eur,
        "est_margin_pct": margin_pct,
        "max_buy_price": max_buy,
        "resale_score": final_score,
        "category": category,
    }


async def triage_batch(ads: list[dict], router, brain) -> dict:
    """Étage 1 : 1 appel pour N annonces. Retourne {ad_id: {category, score, dig_deeper, reason}}.

    - Enregistre chaque annonce comme observation marché (byproduct), avec modèle exact si détecté.
    - Force category ∈ {interesting, passable} (le triage ne déclare JAMAIS urgent).
    """
    for a in ads:
        if a.get("category") and a.get("price"):
            model = extract_model_name(a.get("title", ""))
            brain.record_market_obs(a["category"], float(a["price"]), a.get("city"), model_name=model)

    grounding = market_grounding(brain, ads[0].get("category") if ads else None,
                                 model_name=extract_model_name(ads[0].get("title", "")) if ads else None)
    prompt = build_triage_prompt(ads, grounding)
    data, _model, _tier = await router.generate("triage", prompt, TRIAGE_SCHEMA)

    out: dict = {}
    for item in data.get("items", []):
        cat = item.get("category")
        if cat not in ("interesting", "passable"):
            cat = "interesting"  # garde-fou : jamais urgent au triage
        out[str(item["ad_id"])] = {
            "category": cat,
            "score": float(item.get("score", 0)),
            "dig_deeper": bool(item.get("dig_deeper", False)),
            "reason": item.get("reason", ""),
        }
    return out


async def verify_one(ad: dict, search: dict, router, brain, urgent_score_threshold: float) -> dict:
    """Étage 2 : vérification fine d'une annonce. Seul un tier >= min peut donner 🔴."""
    model = extract_model_name(ad.get("title", ""))
    grounding = market_grounding(brain, ad.get("category"), model_name=model)
    prompt = build_verify_prompt(ad, grounding)
    data, model_id, tier_rank = await router.generate("verify", prompt, VERIFY_SCHEMA)

    # 🔴 si le prix marché est ancré fiablement (grounding 'model' resserré) → médiane, OU si le prix
    # bat le PLANCHER du marché (1ᵉʳ décile) même quand la distribution est large (affaire quelle que
    # soit la génération). Sans modèle (pas de plancher) → plafond 🟡.
    grounding_confident = is_grounding_confident(grounding)

    # Garde-fou anti-hallucination : ne borne le prix marché par la médiane observée QUE si elle
    # repose sur un échantillon réel (≥5, même barre que le grounding 'model'). Une médiane sur 1-2
    # obs (souvent l'annonce elle-même, enregistrée au triage) n'est pas un comparable fiable.
    market_median = grounding.get("median_price") if (grounding.get("sample_size") or 0) >= 5 else None

    margin = compute_margin_and_category(
        price=ad.get("price", 0.0),
        est_market_price=data.get("est_market_price", 0.0),
        refined_score=data.get("refined_score", 0.0),
        min_margin_eur=search.get("min_margin_eur") or 0.0,
        min_margin_pct=search.get("min_margin_pct") or 0.0,
        tier_rank=tier_rank, min_urgent_rank=router.min_urgent_rank,
        urgent_score_threshold=urgent_score_threshold,
        grounding_confident=grounding_confident,
        market_floor=grounding.get("price_floor"),
        market_median=market_median,
    )
    return {
        **margin,  # inclut resale_score réconcilié avec la marge
        "signals": data.get("signals", []),
        "is_lot": bool(data.get("is_lot", False)),
        "lot_unit_price": data.get("lot_unit_price"),
        "lot_notes": data.get("lot_notes"),
        "explanation": data.get("explanation", ""),
        "model_used": model_id,
    }


async def photo_one(ad: dict, image_bytes: bytes, router) -> dict:
    """Étage 3 : analyse photo (🔴 uniquement). Retourne {photo_verdict, scam_risk}."""
    prompt = build_photo_prompt(ad)
    data, _model, _tier = await router.generate("photo", prompt, PHOTO_SCHEMA, image_bytes=image_bytes)
    return {"photo_verdict": data.get("verdict", ""), "scam_risk": data.get("scam_risk", "low")}
