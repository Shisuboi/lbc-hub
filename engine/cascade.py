"""Cascade IA : stages purs (triage groupé, vérif, photo) + calcul marge/gate 🔴.

Le batching (10-20 annonces → 1 appel triage) vit dans enrichment_worker ; ici on expose
des fonctions de stage qui prennent un 'router' injecté (LLMRouter ou fake) → testables.
"""
from engine.parse import extract_model_name
from engine.prompts import (
    TRIAGE_SCHEMA, VERIFY_SCHEMA, PHOTO_SCHEMA,
    build_triage_prompt, build_verify_prompt, build_photo_prompt,
)
from engine.grounding import market_grounding


def compute_margin_and_category(
    price: float, est_market_price: float, refined_score: float,
    min_margin_eur: float, min_margin_pct: float,
    tier_rank: int, min_urgent_rank: int, urgent_score_threshold: float,
) -> dict:
    """Calcule marge €/%, prix max d'achat, et la catégorie finale (gate 🔴)."""
    price = float(price or 0.0)
    est = float(est_market_price or 0.0)
    margin_eur = round(est - price, 2)
    margin_pct = round((margin_eur / price * 100.0), 2) if price > 0 else 0.0
    required = max(min_margin_eur, price * min_margin_pct / 100.0)
    max_buy = round(est - required, 2)

    margin_ok = margin_eur >= min_margin_eur and margin_pct >= min_margin_pct
    score_ok = refined_score >= urgent_score_threshold
    tier_ok = tier_rank >= min_urgent_rank
    if score_ok and margin_ok and tier_ok:
        category = "urgent"
    elif refined_score >= 50:
        category = "interesting"
    else:
        category = "passable"

    return {
        "est_market_price": est,
        "est_margin_eur": margin_eur,
        "est_margin_pct": margin_pct,
        "max_buy_price": max_buy,
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


async def verify_one(ad: dict, search: dict, router, brain, urgent_score_threshold: float,
                     market_context: str | None = None) -> dict:
    """Étage 2 : vérification fine d'une annonce. Seul un tier >= min peut donner 🔴.

    `market_context` : analyse marché web (Market Researcher), injectée dans le prompt si fournie.
    """
    model = extract_model_name(ad.get("title", ""))
    grounding = market_grounding(brain, ad.get("category"), model_name=model)
    prompt = build_verify_prompt(ad, grounding, market_context=market_context)
    data, model_id, tier_rank = await router.generate("verify", prompt, VERIFY_SCHEMA)

    margin = compute_margin_and_category(
        price=ad.get("price", 0.0),
        est_market_price=data.get("est_market_price", 0.0),
        refined_score=data.get("refined_score", 0.0),
        min_margin_eur=search.get("min_margin_eur") or 0.0,
        min_margin_pct=search.get("min_margin_pct") or 0.0,
        tier_rank=tier_rank, min_urgent_rank=router.min_urgent_rank,
        urgent_score_threshold=urgent_score_threshold,
    )
    return {
        **margin,
        "resale_score": float(data.get("refined_score", 0.0)),
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
