"""Chargement de la configuration du moteur autonome depuis un fichier .env.

Aucune dépendance externe : on lit le .env à la main puis on superpose os.environ.
"""
import os

REQUIRED_KEYS = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY")


def load_config(env_path: str = ".env") -> dict:
    cfg: dict = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                cfg[key.strip()] = value.strip()
    # Les variables d'environnement réelles ont priorité sur le fichier.
    for key in REQUIRED_KEYS:
        if key in os.environ:
            cfg[key] = os.environ[key]
    missing = [k for k in REQUIRED_KEYS if not cfg.get(k)]
    if missing:
        raise RuntimeError(f"Clés de config manquantes : {', '.join(missing)}")
    return cfg


def _to_float(value, default: float) -> float:
    """Convertit une valeur en float avec défaut."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value) -> bool:
    """Convertit une valeur en bool (true/1/yes/on → True)."""
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def ai_settings(cfg: dict) -> dict:
    """Extrait/complète les réglages IA depuis la config brute.

    Toutes les clés IA sont optionnelles.
    Pro est activé UNIQUEMENT si BOTH GEMINI_PRO_ENABLED=true ET GEMINI_API_KEY existe.
    """
    return {
        "api_key": cfg.get("GEMINI_API_KEY") or None,
        "triage_model": cfg.get("GEMINI_TRIAGE_MODEL") or "gemini-3.1-flash-lite",
        "verify_model": cfg.get("GEMINI_VERIFY_MODEL") or "gemini-3.1-flash-lite",
        "pro_model": cfg.get("GEMINI_PRO_MODEL") or "gemini-3.1-pro-preview",
        "photo_model": cfg.get("GEMINI_PHOTO_MODEL") or "gemini-3.1-flash-lite",
        "pro_enabled": _to_bool(cfg.get("GEMINI_PRO_ENABLED")) and bool(cfg.get("GEMINI_API_KEY")),
        # Plafond DUR d'appels au modèle Pro (payant) par jour. Défaut conservateur = 50.
        # Au-delà, le routeur retombe sur le modèle gratuit (plafond 🟡, pas de surcoût).
        # Mettre 0 = pas de plafond côté moteur (déconseillé : compter alors sur le quota Cloud).
        "pro_daily_cap": int(_to_float(cfg.get("GEMINI_PRO_DAILY_CAP"), 50)),
        "min_tier_for_urgent": cfg.get("MIN_TIER_FOR_URGENT") or "flash-lite",
        "urgent_score_threshold": _to_float(cfg.get("URGENT_SCORE_THRESHOLD"), 85.0),
        "default_min_margin_eur": _to_float(cfg.get("DEFAULT_MIN_MARGIN_EUR"), 30.0),
        "default_min_margin_pct": _to_float(cfg.get("DEFAULT_MIN_MARGIN_PCT"), 30.0),
        # Plafond journalier de recherches comparatives LBC (anti-captcha). Défaut 100.
        "comparator_daily_cap": int(_to_float(cfg.get("COMPARATOR_DAILY_CAP"), 100)),
    }
