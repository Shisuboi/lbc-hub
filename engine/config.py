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
