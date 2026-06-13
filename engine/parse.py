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


# Tailles d'écran Apple plausibles (évite de confondre une taille avec une année ≥ 2000
# ou une capacité « 256 Go »). 11→17" portables, 21/24/27" iMac.
_APPLE_SIZES = ("11", "12", "13", "14", "15", "16", "17", "21", "24", "27")
_APPLE_CHIP_RE = re.compile(r"\bM([1-4])\b", re.IGNORECASE)


def _apple_size(title: str, allowed: tuple) -> str | None:
    """Première taille d'écran Apple plausible (mot entier, jamais une année/capacité)."""
    for tok in re.findall(r"\b(\d{1,2})\b", title):
        if tok in allowed:
            return tok
    return None


def _apple_chip(title: str) -> str | None:
    """Puce Apple Silicon (M1..M4) si présente — identifiant de génération le plus fort."""
    mm = _APPLE_CHIP_RE.search(title)
    return f"M{mm.group(1)}" if mm else None


def _extract_apple(title: str) -> str | None:
    """Clé modèle pour les produits Apple (préserve Air/Pro, capte puce M ou taille, ignore
    année/capacité). Renvoie None si ce n'est pas un titre Apple reconnaissable."""
    low = title.lower()

    # iPhone : « iPhone 13 Pro », « iPhone 14 Pro Max », « iPhone SE »
    mm = re.search(r"\biphone\s*(se|\d{1,2})\s*(pro\s*max|pro|plus|mini)?", low)
    if mm:
        num = mm.group(1)
        num = "SE" if num == "se" else num
        variant = (mm.group(2) or "").replace("pro max", "Pro Max").replace("pro", "Pro") \
            .replace("plus", "Plus").replace("mini", "Mini").strip()
        return f"iPhone {num}{(' ' + variant) if variant else ''}"

    # iPad : « iPad Air 4 », « iPad Pro 11 », « iPad 9 »
    mm = re.search(r"\bipad\s*(pro|air|mini)?\s*(\d{1,2})?", low)
    if mm and (mm.group(1) or mm.group(2)):
        line = (mm.group(1) or "").capitalize()
        num = mm.group(2) or ""
        return f"iPad{(' ' + line) if line else ''}{(' ' + num) if num else ''}".strip()

    # Mac mini / Mac Studio : puce comme identifiant
    mm = re.search(r"\bmac\s+(mini|studio)\b", low)
    if mm:
        line = "mini" if mm.group(1) == "mini" else "Studio"
        chip = _apple_chip(title)
        return f"Mac {line}{(' ' + chip) if chip else ''}"

    # iMac : taille (21/24/27) ou puce
    if re.search(r"\bimac\b", low):
        ident = _apple_chip(title) or _apple_size(title, ("21", "24", "27"))
        return f"iMac{(' ' + ident) if ident else ''}"

    # MacBook (Air/Pro/Intel) : puce M prioritaire, sinon taille d'écran
    if re.search(r"\bmac\s?book\b", low):
        line = ""
        if re.search(r"\bair\b", low):
            line = "Air"
        elif re.search(r"\bpro\b", low):
            line = "Pro"
        ident = _apple_chip(title) or _apple_size(title, ("11", "12", "13", "14", "15", "16", "17"))
        parts = ["MacBook"] + ([line] if line else []) + ([ident] if ident else [])
        return " ".join(parts)

    return None


def extract_model_name(title: str) -> str | None:
    """Extrait le modèle précis du titre (ex: 'MacBook Air M1', 'iPhone 13 Pro', 'Lenovo ThinkPad X1').

    Sert à la fois de clé de grounding (médiane par modèle) et de requête de recherche LBC du
    comparateur. Retourne None si incertain pour éviter des faux positifs / recherches vides.
    """
    if not title:
        return None
    title = title.strip()

    # Apple d'abord : ses conventions (Air/Pro, puces M1.., iPhone/iPad/iMac) ne rentrent pas
    # dans le schéma générique « marque + code alphanumérique » ci-dessous.
    apple = _extract_apple(title)
    if apple:
        return apple

    # Autres marques : (Marque) (Gamme?) (Modèle=alphanumériques+tirets)
    patterns = [
        r"(ASUS|Asus)\s+((?:ZenBook|VivoBook|ExpertBook|ROG|TUF)\s+)?([A-Z0-9\-]+)",
        r"(Lenovo|LENOVO)\s+((?:ThinkPad|IdeaPad|Yoga|Legion)\s+)?([A-Z0-9\-]+)",
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
