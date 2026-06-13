"""Market Researcher : interroge le web (Google Search natif de Gemini) pour estimer les prix.

Remplace les décotes statiques par une analyse marché réelle (neuf / occasion / reconditionné),
mise en cache localement (cf. db.get_market_context). Appelé une fois par recherche, rafraîchi
tous les 3 jours, donc coût négligeable (~3000 tokens, ~1 % de la conso quotidienne).
"""


def build_research_prompt(query_title: str) -> str:
    return (
        "Nous sommes en juin 2026. Fais une recherche web approfondie pour estimer les prix "
        "actuels du marché (neuf, occasion, reconditionné en bon état) pour des produits "
        f"correspondant à la recherche suivante en France : « {query_title} ». "
        "Donne les prix moyens constatés et des repères fiables pour évaluer si une offre est "
        "une bonne affaire (fourchettes par état, modèles concernés, prix planchers/plafonds)."
    )


async def run_market_research(router, query_title: str) -> str:
    """Lance la recherche web et retourne le texte d'analyse marché généré par Gemini."""
    prompt = build_research_prompt(query_title)
    text, _model_id, _tier = await router.generate_text("research", prompt, use_search=True)
    return text
