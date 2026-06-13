"""Routeur multi-modèles : choisit le modèle par stage, compte les quotas, bascule, gate 🔴.

Reçoit un provider injecté (engine.llm_client.GeminiClient ou un fake) → testable sans réseau.
Extensible : un futur provider local (Ollama) ou Groq s'ajoute sans toucher la cascade.
"""
from engine.db import quota_day

# Rang de capacité croissant — sert au gate 🔴 (seul tier >= min peut déclarer urgent).
TIER_RANKS = {"flash-lite": 1, "flash": 2, "pro": 3}

# Plafonds journaliers par défaut (free tier). Configurables via .env plus tard si besoin.
_DEFAULT_CAPS = {
    "gemini-3.1-flash-lite": 1500,
    "gemini-3.5-flash": 1500,
    "gemini-3.1-pro-preview": 100000,  # payant (crédits Cloud) : pas de cap free
}


class QuotaExhausted(Exception):
    """Plus aucun modèle disponible pour ce stage aujourd'hui."""


def _tier_of(model_id: str) -> int:
    if "pro" in model_id:
        return TIER_RANKS["pro"]
    if "flash-lite" in model_id:
        return TIER_RANKS["flash-lite"]
    return TIER_RANKS["flash"]


class LLMRouter:
    def __init__(self, provider, settings: dict, brain):
        self.provider = provider
        self.settings = settings
        self.brain = brain
        self.caps = dict(_DEFAULT_CAPS)
        # Plafond dur d'appels au Pro payant/jour (sécurité coût). 0/None = pas de plafond.
        pro_cap = settings.get("pro_daily_cap")
        pro_model = settings.get("pro_model")
        if pro_cap and pro_model:
            self.caps[pro_model] = pro_cap
        self.min_urgent_rank = TIER_RANKS.get(settings.get("min_tier_for_urgent", "pro"), 3)

    def _candidates(self, stage: str) -> list[str]:
        """Modèles candidats pour un stage, par ordre de préférence."""
        s = self.settings
        if stage == "triage":
            return [s["triage_model"]]
        if stage == "photo":
            return [s["photo_model"]]
        if stage == "verify":
            if s.get("pro_enabled"):
                return [s["pro_model"], s["verify_model"]]
            return [s["verify_model"]]
        raise ValueError(f"stage inconnu: {stage}")

    async def generate(self, stage: str, prompt: str, schema: dict, image_bytes=None):
        """Retourne (data, model_id, tier_rank). Lève QuotaExhausted si tout est épuisé."""
        day = quota_day()
        provider_name = getattr(self.provider, "name", "gemini")
        for model_id in self._candidates(stage):
            cap = self.caps.get(model_id, 1500)
            if self.brain.usage_count(provider_name, model_id, day) >= cap:
                continue  # ce modèle est épuisé aujourd'hui → on tente le suivant
            data, tokens = await self.provider.generate_json(model_id, prompt, schema, image_bytes)
            self.brain.inc_usage(provider_name, model_id, day, tokens=tokens or 0)
            return data, model_id, _tier_of(model_id)
        raise QuotaExhausted(f"stage={stage} : tous les modèles épuisés")

