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
        "Nous sommes en juin 2026. DEUX RÈGLES DE CALIBRAGE ESSENTIELLES :\n"
        "① TES PRIX INTERNES SONT TROP ÉLEVÉS : ton entraînement date de 2023-2024. "
        "Depuis, les prix de l'électronique d'occasion en France ont chuté. "
        "Pour tout appareil électronique grand public, applique une décote sévère à ton "
        "estimation interne : smartphones et tablettes de 2-4 ans → divise ton estimation par 2 à 3 ; "
        "PC portables et Mac de 3-5 ans → divise par 1,5 à 2 ; consoles de 3-5 ans → divise par 1,3 à 1,5. "
        "En cas de doute, penche toujours vers l'estimation basse.\n"
        "② LES PRIX LBC = PRIX DES INVENDUS : les annonces visibles sur LBC sont celles qui ne se "
        "sont pas encore vendues — ce sont les prix les PLUS ÉLEVÉS du marché, pas la valeur réelle. "
        "Les bonnes affaires partent vite et disparaissent. Tiens-en compte dans ton évaluation.\n"
        "RÈGLE ABSOLUE : quand un prix marché de référence issu de vraies annonces LBC est fourni "
        "ci-dessous, il a TOUJOURS priorité sur tes estimations internes — utilise-le comme ancre.\n"
        "Tu tries des annonces Leboncoin pour de la revente. Pour CHAQUE annonce, donne une "
        "catégorie ('interesting' si ça mérite une analyse approfondie, 'passable' sinon), un "
        "score 0-100, une raison courte, et dig_deeper=true si une vérification fine est utile.\n"
        "IMPORTANT : tu ne déclares JAMAIS une annonce 'urgent' — ce n'est pas ton rôle.\n"
        "MÉFIANCE ANTI-ARNAQUE — tu n'as PAS accès aux photos, tu juges UNIQUEMENT sur le texte :\n"
        "- PRIX DÉRISOIRE = PIÈGE : un prix très en dessous d'un prix fonctionnel plausible "
        "(ex. un PC à 8 €, un iPhone à 20 €) → objet cassé/PIÈCES/arnaque, marge ILLUSOIRE. "
        "→ 'passable', score bas, dig_deeper=false.\n"
        "- INDICES PIÈCES/PANNE dans le titre (pour pièces, pièce détachée, HS, en panne, ne fonctionne "
        "pas, ne s'allume plus, cassé, écran cassé/fissuré, à réparer, défectueux, bloqué iCloud, "
        "FRP verrouillé) → 'passable'.\n"
        "- PRIX GONFLÉ AU-DESSUS du marché LBC actuel (rappel : les prix LBC sont déjà les invendus) "
        "→ 'passable'. Critère : prix > marché de référence fourni ci-dessous, ou clairement "
        "au-dessus de ton estimation basse post-calibrage.\n"
        "- INCERTITUDE ≠ MAUVAIS : un titre VAGUE (modèle/état/capacité absents) mais dont le prix "
        "reste PLAUSIBLE n'est PAS une mauvaise annonce — c'est juste que TU N'AS PAS ASSEZ "
        "D'INFOS. Dans ce cas NE PÉNALISE PAS : score moyen (~55-65) et **dig_deeper=true** pour "
        "que l'étape suivante lise la description du vendeur avant de trancher. Ne classe 'passable' "
        "avec dig_deeper=false QUE si l'annonce est EXPLICITEMENT mauvaise (pièces/cassé/HS, prix "
        "dérisoire = arnaque, ou prix gonflé au-dessus du marché). Le doute profite à dig_deeper.\n"
        "- 'interesting' = prix crédible (ni dérisoire ni gonflé), titre détaillé, potentiellement "
        "compétitif. Le triage est un filtre grossier — la marge exacte sera vérifiée à l'étape suivante.\n"
        "ÉCHELLE DE SCORE : 85-100 = clairement sous le marché, objet sain, titre détaillé ; "
        "60-84 = prix attractif ou au marché avec bonnes caractéristiques, à creuser ; "
        "40-59 = prix au marché sans avantage notable (mais si infos manquantes → dig_deeper=true) ; "
        "0-39 = EXPLICITEMENT mauvais : prix gonflé/dérisoire/suspect, pièces/cassé, titre VIDE.\n"
        f"{_grounding_line(grounding)}\n\n"
        f"Annonces :\n{lignes}"
    )


def build_verify_prompt(ad: dict, grounding: dict) -> str:
    return (
        "Nous sommes en juin 2026. CALIBRAGE ESSENTIEL pour estimer est_market_price :\n"
        "① Tes prix internes sont trop élevés : divise ton estimation par 2 à 3 pour les smartphones/"
        "tablettes de 2-4 ans, par 1,5 à 2 pour les PC/Mac de 3-5 ans, par 1,3 à 1,5 pour les consoles. "
        "Penche toujours vers l'estimation basse.\n"
        "② est_market_price = prix auquel l'objet se VENDRA réellement, pas le prix demandé sur LBC. "
        "Les annonces LBC visibles sont des invendus (prix trop élevés). L'acheteur final paiera "
        "15-30 % EN DESSOUS de ce qu'il voit affiché sur LBC. Intègre cette décote dans ton estimation.\n"
        "Si le prix marché de référence ci-dessous est fourni, il a TOUJOURS priorité — utilise-le "
        "comme ancre principale. S'il est INCONNU, estime à partir de tes connaissances du modèle "
        "exact (gamme, année, capacité, état typique) en appliquant le calibrage ci-dessus.\n"
        "Tu vérifies une annonce Leboncoin pour de la revente. Estime le prix de revente réaliste "
        "(est_market_price), un score affiné 0-100, les signaux d'opportunité, et si c'est un LOT "
        "(is_lot, prix unitaire, notes).\n"
        "GARDE-FOU PRIX DÉRISOIRE : prix très bas = probablement cassé/pièces/arnaque. "
        "Dans ce cas est_market_price = valeur pièces (faible), PAS prix sain. Baisse le score, "
        "ajoute signal « prix anormalement bas : suspicion pièces/cassé ».\n"
        "ÉCHELLE DE SCORE — sois STRICT, les scores élevés déclenchent des notifications :\n"
        "  85-100 = EXCELLENTE affaire, TOUS ces critères réunis : (a) marge nette estimée ≥ 30 % "
        "ET ≥ 30 € après achat ; (b) objet clairement fonctionnel (état précisé, pas de doute) ; "
        "(c) prix demandé significativement sous la médiane LBC (> 15 %) ; (d) aucun signal d'arnaque. "
        "Si UN SEUL de ces critères est douteux, le score ne peut PAS dépasser 79.\n"
        "  60-79 = bonne opportunité à creuser, marge réelle probable mais incertaine.\n"
        "  40-59 = marge faible ou trop d'inconnues.\n"
        "  0-39  = pas une affaire (prix dérisoire/gonflé, objet HS, arnaque probable).\n"
        f"{_grounding_line(grounding)}\n\n"
        f"Annonce : {ad.get('title','')} | prix demandé {ad.get('price',0):.0f} € | "
        f"{ad.get('city','')} | catégorie {ad.get('category','?')}."
        + (f"\nDescription vendeur : {ad['description'][:800]}" if ad.get('description') else
           "\nDescription vendeur : non disponible.")
    )


def build_photo_prompt(ad: dict) -> str:
    return (
        "Analyse la photo de cette annonce Leboncoin. Décris l'état réel visible, les incohérences "
        "éventuelles, et évalue le risque d'arnaque (scam_risk low/medium/high). "
        f"Annonce : {ad.get('title','')}."
    )
