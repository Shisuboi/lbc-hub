"""Prompts et schémas JSON (responseSchema Gemini) de la cascade IA.

Règle dure : le triage ne peut PAS classer 'urgent' (schéma limité à interesting/passable).
Seul le vérificateur (tier Pro) promeut en 🔴, côté code (cf. cascade.compute_margin_and_category).
"""

# --- ÉTAGE 1 : triage groupé ---
TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ad_id": {"type": "string"},
                    "category": {"type": "string", "enum": ["interesting", "passable"]},
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                    "dig_deeper": {"type": "boolean"},
                },
                "required": ["ad_id", "category", "score", "reason", "dig_deeper"],
            },
        }
    },
    "required": ["items"],
}

# --- ÉTAGE 2 : vérification approfondie ---
VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "refined_score": {"type": "number"},
        "est_market_price": {"type": "number"},
        "signals": {"type": "array", "items": {"type": "string"}},
        "is_lot": {"type": "boolean"},
        "lot_unit_price": {"type": "number"},
        "lot_notes": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["refined_score", "est_market_price", "explanation"],
}

# --- ÉTAGE 3 : photo (vision) ---
PHOTO_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string"},
        "scam_risk": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["verdict", "scam_risk"],
}


def _grounding_line(grounding: dict) -> str:
    if not grounding or not grounding.get("median_price"):
        return "Prix marché de référence : INCONNU (peu de données, estime avec prudence)."
    return (
        f"Prix marché de référence (médiane de {grounding['sample_size']} annonces réelles) : "
        f"{grounding['median_price']:.0f} €."
    )


def build_triage_prompt(ads: list[dict], grounding: dict) -> str:
    lignes = "\n".join(
        f"- ad_id={a['ad_id']} | {a.get('title','')} | {a.get('price',0):.0f} € | {a.get('city','')}"
        for a in ads
    )
    return (
        "Tu tries des annonces Leboncoin pour de la revente. Pour CHAQUE annonce, donne une "
        "catégorie ('interesting' si ça mérite une analyse approfondie, 'passable' sinon), un "
        "score 0-100, une raison courte, et dig_deeper=true si une vérification fine est utile.\n"
        "IMPORTANT : tu ne déclares JAMAIS une annonce 'urgent' — ce n'est pas ton rôle.\n"
        "MÉFIANCE ANTI-ARNAQUE — tu n'as PAS accès aux photos, tu juges UNIQUEMENT sur le texte. "
        "Sois donc exigeant :\n"
        "- PRIX DÉRISOIRE = PIÈGE : sers-toi de tes CONNAISSANCES du produit. Un prix très en dessous "
        "d'un prix fonctionnel plausible (ex. un PC portable à 8 €, un iPhone à 20 €) n'est PAS une "
        "bonne affaire — c'est presque toujours un objet cassé, vendu POUR PIÈCES, ou une arnaque-appât. "
        "Ne te laisse JAMAIS séduire par la 'marge' énorme qu'un prix dérisoire ferait croire : elle est "
        "ILLUSOIRE. → 'passable', score bas, dig_deeper=false.\n"
        "- INDICES PIÈCES/PANNE dans le titre (pour pièces, pièce détachée, HS, en panne, ne fonctionne "
        "pas, ne s'allume plus, cassé, écran cassé/fissuré, à réparer, défectueux, bloqué iCloud, compte "
        "Google/FRP verrouillé) → forte décote, 'passable'.\n"
        "- TITRE TROP VAGUE/court pour juger (modèle/état/capacité absents) → on ne peut pas évaluer "
        "sérieusement : écarte facilement → 'passable', score bas.\n"
        "- Ne réserve 'interesting' et un bon score QU'AUX annonces dont le prix est CRÉDIBLE (ni "
        "dérisoire ni gonflé) ET le titre assez détaillé pour inspirer confiance. En cas de doute, "
        "préfère 'passable'.\n"
        "ÉCHELLE DE SCORE : 85-100 = excellente affaire crédible (objet sain, prix attractif mais "
        "plausible, titre détaillé) ; 60-84 = correcte, à creuser ; 40-59 = douteuse ; 0-39 = à écarter "
        "(prix dérisoire/suspect, titre vide, pièces/cassé).\n"
        f"{_grounding_line(grounding)}\n\n"
        f"Annonces :\n{lignes}"
    )


def build_verify_prompt(ad: dict, grounding: dict) -> str:
    return (
        "Tu vérifies une annonce Leboncoin pour de la revente. Estime le prix de revente réaliste "
        "(est_market_price) en t'appuyant sur le prix marché ci-dessous, un score affiné 0-100, "
        "les signaux d'opportunité, et si c'est un LOT (is_lot, prix unitaire, notes).\n"
        "Si le prix marché de référence ci-dessous est INCONNU, estime le prix de revente à partir de "
        "tes CONNAISSANCES du modèle/produit exact (gamme, année, capacité, état typique).\n"
        "GARDE-FOU PRIX DÉRISOIRE : si le prix demandé est très en dessous d'un prix fonctionnel "
        "plausible pour cet objet, considère-le comme probablement cassé / pour pièces / arnaque. Dans "
        "ce cas, est_market_price doit refléter sa valeur RÉELLE en l'état (≈ valeur de pièces, souvent "
        "faible), PAS le prix d'un exemplaire sain — sinon la marge calculée serait ILLUSOIRE. Baisse "
        "alors le refined_score et ajoute le signal « prix anormalement bas : suspicion pièces/cassé ».\n"
        "ÉCHELLE DE SCORE : 85-100 = marge réelle élevée et fiable ; 60-84 = correcte ; 40-59 = faible/"
        "incertaine ; 0-39 = pas une affaire (prix dérisoire suspect, objet en l'état).\n"
        f"{_grounding_line(grounding)}\n\n"
        f"Annonce : {ad.get('title','')} | prix demandé {ad.get('price',0):.0f} € | "
        f"{ad.get('city','')} | catégorie {ad.get('category','?')}."
    )


def build_photo_prompt(ad: dict) -> str:
    return (
        "Analyse la photo de cette annonce Leboncoin. Décris l'état réel visible, les incohérences "
        "éventuelles, et évalue le risque d'arnaque (scam_risk low/medium/high). "
        f"Annonce : {ad.get('title','')}."
    )
