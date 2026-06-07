"""Helpers de parsing purs (sans I/O) — faciles à tester."""
import re
import unicodedata

_AD_ID_RE = re.compile(r"/(\d{6,})(?:\.htm)?/?(?:\?|$)")


def extract_ad_id(url: str) -> str | None:
    """Extrait l'ID numérique stable d'une URL d'annonce Leboncoin."""
    if not url:
        return None
    m = _AD_ID_RE.search(url)
    return m.group(1) if m else None


def clean_price(price_text: str) -> float:
    """Parse un prix au format français (espaces fines, € , virgule décimale)."""
    cleaned = unicodedata.normalize("NFKD", price_text or "")
    cleaned = re.sub(r"[^\d.,]", "", cleaned)
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


_CATEGORY_AD_RE = re.compile(r"/ad/([a-z0-9_]+)/\d", re.IGNORECASE)
_CATEGORY_LEGACY_RE = re.compile(r"leboncoin\.fr/([a-z0-9_]+)/\d+\.htm", re.IGNORECASE)


def extract_category(url: str) -> str | None:
    """Extrait le slug de catégorie d'une URL d'annonce LBC ('/ad/<cat>/<id>')."""
    if not url:
        return None
    m = _CATEGORY_AD_RE.search(url)
    if m:
        return m.group(1).lower()
    m = _CATEGORY_LEGACY_RE.search(url)
    return m.group(1).lower() if m else None


def extract_model_name(title: str) -> str | None:
    """Extrait le modèle précis du titre (ex: 'ASUS ZenBook UX433F', 'MacBook Pro 16').

    Pattern : marque courante + code modèle (alphanumériques avec tirets/espaces).
    Retourne None si incertain pour éviter des faux positifs.
    """
    if not title:
        return None
    title = title.strip()
    # Marques communes : ASUS, Lenovo, Apple/Mac, Dell, HP, Acer, MSI, Toshiba, Sony, etc.
    # Pattern : (Marque) (Gamme?) (Modèle=alphanumériques+tirets)
    patterns = [
        r"(ASUS|Asus)\s+((?:ZenBook|VivoBook|ExpertBook|ROG|TUF)\s+)?([A-Z0-9\-]+)",
        r"(Lenovo|LENOVO)\s+((?:ThinkPad|IdeaPad|Yoga|Legion)\s+)?([A-Z0-9\-]+)",
        r"(Apple|MacBook|Mac)\s+((?:Pro|Air|M[0-9])\s+)*([0-9]+[\"]*)",
        r"(Dell|DELL)\s+((?:XPS|Inspiron|Latitude)\s+)?([A-Z0-9\-]+)",
        r"(HP|Hewlett[\s\-]Packard)\s+((?:Pavilion|Envy|EliteBook)\s+)?([A-Z0-9\-]+)",
        r"(Acer|ACER)\s+((?:Aspire|Swift|Nitro)\s+)?([A-Z0-9\-]+)",
        r"(MSI|Toshiba|Sony|Samsung)\s+([A-Z0-9\-]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, title, re.IGNORECASE)
        if m:
            # Retourner marque + modèle (ignorer la gamme intermédiaire)
            groups = m.groups()
            model_part = groups[-1].strip() if groups[-1] else ""
            if len(groups) >= 2:
                # Marque + Modèle direct (pas de gamme)
                if len(groups) == 2:
                    return f"{groups[0]} {model_part}".strip()
                # Marque + Gamme + Modèle
                elif groups[1]:
                    return f"{groups[0]} {groups[1].strip()} {model_part}".strip()
                else:
                    return f"{groups[0]} {model_part}".strip()
    return None
